# Monitoring

There is no external monitoring stack (Prometheus, Grafana, Sentry, etc.)
wired into this project. What follows is what actually exists to observe the
system's behavior.

## Logging

`app/core/logging.py` configures `structlog`: JSON output when
`APP_ENV=production`, colored console output otherwise. Every log call
carries structured fields rather than an interpolated string — e.g.
`log.info("pipeline_post_done", platforms=target_platforms)` — so JSON logs
in production stay machine-parseable. `httpx`/`httpcore`/`transformers` are
pinned to `WARNING` to keep routine HTTP and model-loading noise out of the
default log level.

**Never logged, by explicit constraint**: access tokens, bot tokens, API
secrets, the Meta app secret, WhatsApp access tokens, or any Authorization
header. `TelegramAdapter._telegram_error()` specifically redacts the bot
token before an error message can reach a log line — that's the pattern to
follow for any new adapter.

## Health and status endpoints

| Endpoint | What it tells you |
|---|---|
| `GET /health` | Process is up, plus current `social_mode`/`llm_provider`/`image_provider` |
| `GET /posting/health/platforms` | Boolean per platform — is it currently healthy |
| `GET /posting/integrations/status` | Richer per-platform view: configured / healthy / live-or-mock |
| `GET /n8n/status/{campaign_id}` | Pipeline progress + per-platform `SocialPost` status for one campaign |
| `GET /analytics/tracking/status` | Whether analytics ingestion is actively receiving events |

## Provenance flags — telling real data from placeholder data

Two boolean columns exist specifically so the dashboard and API responses
never present fallback/mock output as if it were real:

- `SocialPost.is_mock` / `AnalyticsEvent.is_mock` — set whenever `MockAdapter`
  produced the row (`SOCIAL_MODE=mock`, or a live platform whose credentials
  weren't configured). The frontend renders a `mock` badge wherever this is
  true.
- `AdCopy.fallback` — set when ad-copy generation failed to parse valid JSON
  twice in a row and the row is a hardcoded English placeholder rather than a
  real result in the requested language. The frontend renders a `fallback`
  badge on it.

If you add a new kind of AI-generated or platform-sourced data that can fail
into a placeholder, follow this same convention rather than returning
indistinguishable placeholder data.

## Stale-pipeline detection

`n8n_webhooks.STALE_GENERATING_TIMEOUT_SECONDS` (20 minutes): a campaign
whose status is still `"generating"` past this age gets flipped to `"failed"`
the next time anything polls `/n8n/status/{id}`. This is the only mechanism
that catches a background task killed by a server restart mid-pipeline —
without it, such a campaign stays `"generating"` forever and the frontend
polls indefinitely.

## What would need to be added for real production monitoring

None of the following exist today: request tracing/APM, error aggregation
(e.g. Sentry), metrics export (Prometheus-style `/metrics`), alerting on
failed pipeline runs or platform publish failures, or log shipping to a
central store. The structured `structlog` JSON output in production mode is
the natural integration point for any of these — it just isn't wired to
anything yet.
