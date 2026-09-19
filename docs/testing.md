# Testing

## Backend — pytest

```bash
cd backend
.venv\Scripts\python.exe -m pytest -m "not heavy" -v    # fast suite
.venv\Scripts\python.exe -m pytest -m heavy -v           # heavy suite, run separately
```

Always invoke pytest through `backend/.venv`'s interpreter — see
[development.md](development.md) for why a different Python silently breaks
model-loading tests.

### The `heavy` marker

Registered in `pytest.ini`. Tests marked `@pytest.mark.heavy` load SDXL and/or
Qwen2.5-VL onto the GPU — on a 6GB card these cannot share a CUDA context with
the rest of the suite in one process without the allocator fragmenting badly
enough that SDXL falls back to CPU and fp16 matmul fails
(`"addmm_impl_cpu_" not implemented for 'Half'`). Run them in their own
process, separately from everything else.

### Test database isolation

`backend/tests/conftest.py` points the whole test process at a temp-directory
SQLite file (`nexmarket_test.db`) **before** `app.core.config`/`app.db.session`
are ever imported — those modules build the engine from settings at import
time, and `get_settings()` is `@lru_cache`d, so this only works because
conftest.py runs first (pytest imports every `conftest.py` before collecting
test modules). Without this, tests write directly into the real dev
`nexmarket.db` — confirmed damage in this project's history: 389 fake
campaigns from repeated test runs pushed every real campaign out of the
dashboard's `LIMIT 100` query.

### What's covered

70 tests across `backend/tests/test_main.py`, including:

- Health check, campaign CRUD, brand kit.
- Ad copy generation, including that it routes through the shared
  `AI_TEXT_PROVIDER` switch rather than calling the local Qwen path directly
  (a regression guard: `test_adcopy_routes_through_the_shared_text_provider`
  asserts the source no longer calls `inference_manager.generate_ad_copy`).
- Sentiment analysis, lead scoring, LSTM forecasting, campaign optimization.
- Social posting: single-platform publish, the campaign-level multi-platform
  endpoint, and a genuine independence guarantee
  (`test_one_platform_failure_leaves_others_published` /
  `test_campaign_publish_all_platforms_independently`) — one platform's
  failure must never affect another's `SocialPost.status`.
- The n8n pipeline's `"post"` step publishing to multiple platforms
  independently and defaulting `platforms` from the campaign when the n8n
  caller omits it (`test_n8n_post_step_publishes_platforms_independently`,
  `test_n8n_post_step_defaults_platforms_from_campaign`).
- A race-condition regression: a `SocialPost` row's status must be set
  *before* the request's own `db.commit()`, not after — otherwise
  `get_db()`'s trailing commit can revert whatever the background publish
  task already wrote (`test_publish_marks_posted_not_stuck_posting`).
- Model-loading smoke tests for DistilBERT, XGBoost, LSTM, and the Thompson
  Sampling bandit — these exist because loading and shape mistakes (e.g. the
  LSTM needing `(timesteps, 5)` input, not a 1-D array) are easy to get wrong
  silently.

## Frontend — Vitest + React Testing Library

```bash
cd frontend
npm run test
```

Configured via `vitest.config.ts` (jsdom environment, `@/*` alias matching
`tsconfig.json`) and `vitest.setup.ts` (`@testing-library/jest-dom`
matchers). Tests live next to the component they cover, e.g.
`frontend/src/components/campaign/CampaignTabs.test.tsx` for `PostingTab` and
`AdCopyTab` — covering platform-checkbox selection and the resulting
multi-platform publish call, the Post Now button disabling at zero platforms
selected, independent per-row status/mock rendering in the post-history list,
and the ad-copy language-fallback badge.

`global.fetch` is stubbed per test (`vi.stubGlobal`) rather than mocking
`api.ts` itself, so the real request-building logic in `api.ts` is exercised
— no real backend is required to run the suite.

### Why components had to move out of `page.tsx`

Next.js's App Router restricts what a `page.tsx` file may export — importing
`PostingTab`/`AdCopyTab` directly from a test file broke the production build
(`next build` failed type-checking `.next/types/app/.../page.ts` with
`"Property 'AdCopyTab' is incompatible with index signature"`). They were
extracted into `frontend/src/components/campaign/CampaignTabs.tsx`, an
ordinary component module with no export restrictions, and imported back
into `page.tsx`. Any future component that needs direct unit testing should
follow the same pattern rather than living inside a `page.tsx`.
