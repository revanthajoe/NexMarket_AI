# n8n Workflow

## Shape: thin trigger-and-poll, not per-platform branching

`n8n/workflows/campaign_pipeline.json` has exactly one `httpRequest` node that
matters for orchestration logic: **Trigger Backend Pipeline**, which calls

```
POST /api/v1/n8n/trigger/campaign
{
  "campaign_id": "...",
  "steps": ["poster","adcopy","evaluate","forecast","optimize","post"],
  "platforms": <passed through from the incoming webhook payload, or omitted>
}
```

The backend runs every step of the pipeline sequentially inside one
`BackgroundTasks` coroutine (`run_pipeline` in
`backend/app/api/v1/endpoints/n8n_webhooks.py`) on its own DB session. n8n's
only other job is to poll:

```
GET /api/v1/n8n/status/{campaign_id}
→ { "campaign_id", "status", "posts": [{ "platform", "status", "is_mock" }] }
```

until `status` leaves `"generating"`. There is no Switch node, no per-platform
branch, and no second call into FastAPI per platform — everything after the
initial trigger is polling.

**Why not branch per platform in n8n?** Nothing else in this workflow (or
this codebase) uses that model, and it would mean the step sequencing
(poster → adcopy → evaluate → forecast → optimize → post, each depending on
the last) exists twice — once in n8n's graph, once in the backend's
`run_pipeline` — with every future change needing both kept in sync. Instead,
the trigger payload gained a `platforms` list, and the backend's own `"post"`
step loops over it, reusing the exact same
`create_posts_for_platforms` / `publish_platforms` helpers the standalone
`/posting/campaign/{id}/publish` endpoint uses (see
[social-media-integration.md](social-media-integration.md)).

## Idempotency

Each step checks for existing rows before running — a poster or ad-copy step
skips generation entirely if the campaign already has one, so re-triggering a
pipeline that partially ran doesn't create duplicate posters/ad-copy rows.

## Per-platform independence in the pipeline

The `"post"` step never `raise`s on a single platform's publish failure — it
used to (publishing to exactly one platform, wrapped in a bare `raise` that
failed the *entire* campaign on that platform's error), which was a real bug
found and fixed in this pass. Now:

```python
target_platforms = platforms or (
    [results["optimization"]["recommended_platform"]]
    if results.get("optimization", {}).get("recommended_platform")
    else [c.preferred_platform]
)
posts = await social_posting_service.create_posts_for_platforms(...)
await social_posting_service.publish_platforms(bg_db, posts, text_content, image_url)
```

A campaign with `platforms: ["instagram", "telegram"]` where only Telegram
succeeds still reaches `status: "posted"` — Instagram's `SocialPost` row is
the only place that failure shows up.

## Failure handling for the pipeline itself

If any *other* step (poster generation, ad copy, optimization) raises, the
outer `except` rolls back only that step's uncommitted work (earlier steps
already committed independently — a poster that cost GPU time is kept even
if a later step fails) and marks `campaign.status = "failed"` on a fresh
session, so the frontend's poll loop can stop and report it.

## Stale-pipeline recovery

`GET /n8n/status/{id}` self-heals a campaign stuck at `"generating"` for more
than `STALE_GENERATING_TIMEOUT_SECONDS` (20 minutes) by marking it `"failed"`
on the next status poll — this covers a dev-server restart mid-pipeline,
which silently kills the background task before it can write any final
status itself.

## Other webhook endpoints

- `POST /n8n/analytics/ingest` — n8n can push analytics events from platform
  APIs it polls independently of the pipeline.
- `POST /n8n/report/trigger` — placeholder that returns a report URL; report
  generation itself is not implemented here.
