# Social Media Integration

## Supported platforms

`SUPPORTED_PLATFORMS` in `backend/app/services/posting/posting_service.py`:
Instagram, Facebook, Telegram, WhatsApp. (LinkedIn and Twitter/X adapters
existed briefly during development and were removed — not enough demand to
justify maintaining four platform integrations plus two more.)

## Adapter pattern

Every platform implements the same `SocialPlatformAdapter` interface
(`backend/app/services/posting/adapters.py`):

```python
class SocialPlatformAdapter(ABC):
    async def post(self, payload: PostPayload) -> PostResult: ...
    async def fetch_metrics(self, platform_post_id: str) -> PostMetrics: ...
    async def health_check(self) -> bool: ...
```

`posting_service._get_adapter(platform)` picks the concrete adapter:

- `SOCIAL_MODE=mock` → always `MockAdapter`, regardless of credentials.
- `SOCIAL_MODE=live` but a platform's required env vars aren't all set →
  falls back to `MockAdapter` for that platform only (logged as
  `social_credentials_missing_fallback_mock`), so a campaign can still post
  to platforms that *are* configured.
- Otherwise the real adapter, constructed with that platform's credentials.

## Per-platform credentials

`_credentials_present()` in `posting_service.py` is the single source of
truth for what each platform needs — kept here in sync with it:

| Platform | Required env vars |
|---|---|
| Instagram | `META_ACCESS_TOKEN`, `META_IG_USER_ID` |
| Facebook | `META_ACCESS_TOKEN`, `META_PAGE_ID` |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| WhatsApp | `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_RECIPIENT` |

All of these live in `backend/.env` only — never committed, never sent to the
frontend, never logged. `TelegramAdapter`'s error formatting explicitly
redacts the bot token before it can reach a log line or an API error message.

## Media URLs

Instagram, Facebook, and WhatsApp fetch posted media **server-side** — the
platform's own servers make an outbound request to whatever image URL you
give them, so `http://localhost:8000/...` never works for them. `PUBLIC_MEDIA_BASE_URL`
(falling back to `STATIC_BASE_URL` when unset) must be a URL reachable from
the public internet — a real domain in front of the backend, or a tunnel
(ngrok, etc.) during testing.

Telegram is the one exception: `TelegramAdapter` uploads the image as
multipart form bytes directly, so it never needs a fetchable URL and works
even on `localhost`.

## Independence guarantee

Publishing to several platforms in one call never lets one platform's
failure affect another's. This is a property of two shared methods on
`SocialPostingService` (`backend/app/services/posting/posting_service.py`):

```python
async def create_posts_for_platforms(self, db, campaign_id, platforms, ...):
    """One SocialPost row per platform, already committed as status='posting'."""

async def publish_platforms(self, db, posts, text, image_url=None):
    """Publish each row in turn; a per-platform except swallows failures —
    this must never raise, or one platform's error stops the rest."""
```

Both call sites use these instead of duplicating the loop:

- `POST /posting/campaign/{campaign_id}/publish` — the standalone multi-platform endpoint.
- The n8n pipeline's `"post"` step (`n8n_webhooks.run_pipeline`) — see
  [n8n-workflow.md](n8n-workflow.md).

Each platform's outcome lives entirely on its own `SocialPost.status` row
(`posted` / `failed` / `posting` / `pending` / `scheduled`) — there is no
combined "campaign post status" to be wrong.

## Live vs. mock

`SocialPost.is_mock` and `AnalyticsEvent.is_mock` mark every row produced by
`MockAdapter`, and the frontend renders a `mock` badge wherever that's true
(`PostingTab`'s post-history list). This is the only UI distinction between
live and mock — there is no separate "demo mode" concept to maintain.

## Honesty notes

No platform has been live-verified in this repository — mock mode is the
only path that has actually been exercised end-to-end. Verifying a live
platform requires real credentials and a publicly reachable
`PUBLIC_MEDIA_BASE_URL`, neither of which this repository can supply for you.
