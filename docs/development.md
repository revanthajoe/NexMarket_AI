# Development

## Prerequisites

- Python 3.11+
- Node.js 20+
- SQLite (dev default, zero setup) or PostgreSQL 16 (Docker/prod)

## Backend

```bash
cd backend
```

**Always use `backend/.venv`, never a system/global Python.** The pinned
stack (torch 2.1.2+cu121, diffusers 0.30.3, peft 0.13.2, numpy/scipy/pandas/
scikit-learn/xgboost pinned to torch-compatible versions) lives only there.
Running the server on a different interpreter silently drops packages — a
missing `peft` disables diffusers' PEFT backend and poster generation fails
with `"PEFT backend is required for this method."`; an upgraded numpy breaks
torch/SDXL/Qwen entirely. Every command below assumes the venv is active or
invoked explicitly:

```bash
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux

cp .env.example .env              # then fill in whichever provider keys you're using
alembic upgrade head              # applies schema migrations — SQLite dev included
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

If a schema change lands (a new column, a new table), it needs a new Alembic
migration under `backend/alembic/versions/` even for the SQLite dev DB — the
app's startup `Base.metadata.create_all()` only creates missing *tables*, it
does not alter existing ones.

## Frontend

```bash
cd frontend
npm install
npm run dev       # dev server, http://localhost:3000
npm run build     # production build + typecheck — run before shipping any change
npm run test      # Vitest — see testing.md
```

`frontend/src/lib/api.ts` is the only place HTTP calls to the backend should
be made from — it already handles the GET cache, request timeouts, and local
port auto-detection (falls back through 8000–8005 if the configured port
doesn't answer).

## Adding a new component that needs testing

Next.js's App Router only allows specific named exports from a `page.tsx`
file (`default`, `generateStaticParams`, etc.) — the build fails on anything
else with `"Property '<Name>' is incompatible with index signature."` A
component that needs to be imported into a test file cannot live inside a
`page.tsx`; extract it into `frontend/src/components/...` and import it back
into the page, the way `PostingTab`/`AdCopyTab` were extracted into
`components/campaign/CampaignTabs.tsx`.

## Adding a new social platform

1. Add credential fields to `Settings` in `app/core/config.py` and to
   `.env.example` (documented, left blank).
2. Add the platform to `SUPPORTED_PLATFORMS` and to `_credentials_present()` /
   `_get_adapter()` in `app/services/posting/posting_service.py`.
3. Implement a new `SocialPlatformAdapter` subclass in
   `app/services/posting/adapters.py` — `post()`, `fetch_metrics()`,
   `health_check()`. Never return fabricated metrics from `fetch_metrics()`
   if the platform doesn't expose them; return an explicit "not available"
   error instead (see `TelegramAdapter`/`WhatsAppAdapter` for the pattern).
4. Add the platform to `_PLATFORM_PATTERN` in `app/schemas/schemas.py`.
5. Add it to `POSTING_PLATFORMS` in
   `frontend/src/components/campaign/CampaignTabs.tsx`.
6. Never route the platform's credentials to the frontend, and never log them
   — redact tokens in any error message the way `TelegramAdapter._telegram_error()` does.

## Code review posture

Don't add abstractions, config flags, or error handling for cases that can't
happen. Reuse an existing service function rather than re-implementing its
logic at a second call site — the multi-platform publish extraction
(`create_posts_for_platforms` / `publish_platforms`) exists specifically so
the standalone endpoint and the n8n pipeline step don't duplicate that loop.
