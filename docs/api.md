# API Reference

All routes are prefixed `/api/v1`. Full interactive Swagger UI is served at
`http://localhost:8000/docs` (ReDoc at `/redoc`) whenever the backend is
running — that is the authoritative, always-current source; this file is a
map of what exists and why, not a substitute for it.

## Campaigns — `campaigns.py`

| Method | Path | Notes |
|---|---|---|
| POST | `/campaigns/` | Create a campaign |
| GET | `/campaigns/` | List campaigns (summary) |
| GET | `/campaigns/{id}` | Get one campaign |
| PATCH | `/campaigns/{id}/status` | Update status |
| DELETE | `/campaigns/{id}` | Delete a campaign |

## Posters — `posters.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/posters/campaign/{campaign_id}` | List a campaign's posters |
| POST | `/posters/generate` | Generate 1–4 poster variations |
| POST | `/posters/{poster_id}/evaluate` | Vision-based evaluation |
| GET | `/posters/{poster_id}/evaluations` | List evaluations for a poster |

## Ad Copy — `adcopy.py`

| Method | Path | Notes |
|---|---|---|
| POST | `/adcopy/generate` | Generate copy for one or more platforms; routes through `AI_TEXT_PROVIDER` |
| GET | `/adcopy/{campaign_id}` | List a campaign's ad copies |

## Social Posting — `posting.py`

| Method | Path | Notes |
|---|---|---|
| POST | `/posting/publish` | Publish to one platform |
| POST | `/posting/campaign/{campaign_id}/publish` | Publish to several platforms at once, independently — see [social-media-integration.md](social-media-integration.md) |
| GET | `/posting/campaign/{campaign_id}` | List a campaign's posts |
| GET | `/posting/{post_id}` | Get one post's status |
| POST | `/posting/retry/{post_id}` | Retry a failed/pending post |
| GET | `/posting/health/platforms` | Boolean health per platform |
| GET | `/posting/integrations/status` | Full per-platform state: configured / healthy / live-or-mock |
| POST | `/posting/metrics/sync/{campaign_id}` | Pull engagement back from each platform |
| POST | `/posting/scheduled/run` | Publish everything now due (called by n8n or a worker) |

## Sentiment — `sentiment.py`

| Method | Path | Notes |
|---|---|---|
| POST | `/sentiment/analyze` | Batch sentiment analysis (DistilBERT, or `LLM_PROVIDER`) |

## Leads — `leads.py`

| Method | Path | Notes |
|---|---|---|
| POST | `/leads/predict` | XGBoost lead score + feature importance |
| GET | `/leads/campaign/{campaign_id}` | Leads for a campaign |

## Forecast — `forecast.py`

| Method | Path | Notes |
|---|---|---|
| POST | `/forecast/` | LSTM engagement forecast (1–30 day horizon) |
| GET | `/forecast/campaign/{campaign_id}` | Existing forecasts for a campaign |

## Optimization — `optimization.py`

| Method | Path | Notes |
|---|---|---|
| POST | `/optimize/` | Thompson Sampling platform/time/budget recommendation |

## Analytics — `analytics.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/analytics/dashboard` | Aggregate dashboard summary |
| GET | `/analytics/engagement/timeseries` | Engagement over time |
| GET | `/analytics/engagement/platforms` | Engagement broken down by platform |
| GET | `/analytics/tracking/status` | Whether tracking/analytics ingestion is active |
| GET | `/analytics/campaign/{campaign_id}` | Raw events for one campaign |
| GET | `/analytics/{campaign_id}/report` | Report payload for a campaign |

## Brand Kit — `brand_kit.py`

| Method | Path | Notes |
|---|---|---|
| POST | `/brand-kit/{campaign_id}/upload` | Upload a brand asset (logo, product cutout, ...) |
| POST | `/brand-kit/{campaign_id}/meta` | Merge-update brand kit metadata (language, contact info, ...) |
| GET | `/brand-kit/{campaign_id}` | Get a campaign's brand kit |

## n8n Webhooks — `n8n_webhooks.py`

| Method | Path | Notes |
|---|---|---|
| POST | `/n8n/trigger/campaign` | Kick off the full pipeline in a background task |
| GET | `/n8n/status/{campaign_id}` | Poll pipeline progress + per-platform post status |
| POST | `/n8n/analytics/ingest` | Push an analytics event from an n8n-polled platform API |
| POST | `/n8n/report/trigger` | Trigger report generation (returns a URL; generation itself is out of scope here) |

See [n8n-workflow.md](n8n-workflow.md) for how these two calls relate to the
actual n8n workflow graph.

## Root

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Liveness + current provider settings (`social_mode`, `llm_provider`, `image_provider`) |
