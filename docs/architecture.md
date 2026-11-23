# Architecture

## Request flow

```
Browser (Next.js, port 3000)
   │  fetch() — src/lib/api.ts
   ▼
FastAPI backend (port 8000) — app/main.py
   │  routers under /api/v1/*, each a thin HTTP layer over a service in app/services/
   ▼
SQLAlchemy async session (SQLite in dev, PostgreSQL in Docker/prod)
```

n8n is **not** in the request path for anything the frontend does directly — it
is a separate, optional orchestration layer. See
[n8n-workflow.md](n8n-workflow.md) for how it fits in.

## Backend layout

```
backend/app/
├── api/v1/endpoints/   one router per resource — campaigns, posters, adcopy,
│                       posting, sentiment, leads, forecast, optimization,
│                       analytics, n8n_webhooks, brand_kit
├── core/               config.py (Settings, env-driven), logging.py (structlog)
├── db/                 session.py — async engine, WAL pragmas, get_db()
├── models/             SQLAlchemy ORM models (models.py)
├── schemas/            Pydantic v2 request/response schemas (schemas.py)
├── services/
│   ├── ai/             poster_generator, ad_generator, poster_evaluator,
│   │                   text_provider (local Qwen routing), brand_kit,
│   │                   brochure_composer, icon_library, sentiment,
│   │                   lead_prediction, lstm_forecast, model_registry
│   ├── posting/        adapters.py (one class per platform) + posting_service.py
│   │                   (retry, scheduling, DB persistence, the shared
│   │                   multi-platform publish helpers)
│   └── optimization/   Thompson Sampling contextual bandit
├── prompts/            LLM prompt templates
└── main.py             FastAPI app, lifespan (model warm-up, worker startup),
                         CORS, static file mount, router registration
```

Every router is a thin HTTP adapter — the actual logic lives in
`app/services/*`, which is what lets `n8n_webhooks.py` call the same service
functions the standalone endpoints call, instead of re-implementing anything.

## AI model routing

The application uses the local model stack for generated marketing content and
poster evaluation — see
[.env.example](../backend/.env.example) for the full list:

| Setting | Governs | Values |
|---|---|---|
| `AI_TEXT_PROVIDER` | Poster copy, poster scene spec, poster evaluation text, ad copy | `local` (Qwen2.5-3B and Qwen2.5-VL) |
| `LLM_PROVIDER` | Optional legacy LLM setting for unrelated services | `openai` / `local` |
| `VISION_PROVIDER` | Optional legacy vision setting for unrelated services | `openai` / `local` |
| `IMAGE_PROVIDER` | Poster image generation | `openai` / `stability` / `mock` / `local` |

The active poster and ad-copy path is local-only: Qwen2.5-3B produces
structured copy and visual specifications, SDXL generates the image, and
Qwen2.5-VL evaluates the composed poster. Template and evaluation fallbacks
are explicitly marked as `FALLBACK`.

## Database

PostgreSQL is the default database whenever `DATABASE_URL` is configured.
SQLite (`nexmarket.db`) is an explicit opt-in via
`USE_SQLITE_FALLBACK=true`; it uses WAL mode, a 30s busy timeout, and foreign
keys enabled — set once via an engine-level `connect` listener in
`app/db/session.py` so every connection gets them, not just the first one.
Docker/production uses PostgreSQL via the same SQLAlchemy async models;
schema changes are tracked as Alembic migrations under `backend/alembic/versions/`
and must be applied with `alembic upgrade head` (SQLite dev also gets its
schema from `Base.metadata.create_all()` at startup, but that only creates
new tables — it does not add columns to existing ones, so a schema change
still needs a migration even in dev).

## Frontend layout

```
frontend/src/
├── app/                Next.js App Router pages (dashboard, campaign list,
│                       campaign detail with its tabs, campaign creation)
├── components/         shared UI — charts, and (new) components/campaign/
│                       for tab components extracted out of page.tsx so they
│                       can be unit-tested independently
└── lib/api.ts          the one HTTP client — every backend call goes through
                        this file's `api.*` namespaces, including a GET cache,
                        automatic port fallback, and shared timeout handling
```

## Why n8n stays thin

The pipeline (poster → ad copy → evaluate → forecast → optimize → post) runs
entirely inside one FastAPI background task
(`n8n_webhooks.run_pipeline`). n8n's job is only to call
`POST /n8n/trigger/campaign` and then poll `GET /n8n/status/{id}` until it
settles — it does not branch per platform or call FastAPI more than those two
endpoints. This was a deliberate choice over a Switch-node-per-platform
design: nothing else in this codebase uses that model, and duplicating the
pipeline's step sequencing into n8n nodes would mean maintaining the same
logic in two places. See [n8n-workflow.md](n8n-workflow.md).
