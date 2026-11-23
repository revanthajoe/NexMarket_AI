"""
NexMarket AI — FastAPI Application Entry Point
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.api.v1.endpoints import (
    campaigns,
    posters,
    adcopy,
    posting,
    sentiment,
    leads,
    forecast,
    optimization,
    analytics,
    n8n_webhooks,
    brand_kit,
)

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("nexmarket_starting", env=settings.APP_ENV)

    if (
        settings.APP_ENV == "development"
        and settings.SOCIAL_MODE == "live"
        and len(settings.TELEGRAM_WEBHOOK_SECRET) < 16
    ):
        logger.warning(
            "telegram_webhook_secret_missing_or_weak",
            extra={"message": "Live Telegram mode is enabled without a strong webhook secret"},
        )

    # Ensure upload directory exists
    import os
    os.makedirs(settings.POSTER_UPLOAD_DIR, exist_ok=True)

    if settings.is_sqlite:
        from app.db.session import Base, engine

        # WAL / synchronous / busy_timeout are applied by the engine's "connect"
        # listener in app.db.session, so they are already set on this connection
        # and on every other one the process opens.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    from app.db.session import AsyncSessionLocal
    from app.services.model_metadata import register_runtime_models
    async with AsyncSessionLocal() as metadata_db:
        await register_runtime_models(metadata_db)

    from app.services.posting.posting_service import social_posting_service
    async with AsyncSessionLocal() as posting_db:
        await social_posting_service.fail_unavailable_live_posts(posting_db)

    # Pre-warm ML models in background (non-blocking)
    import asyncio

    async def warm_models():
        # There are no `_load_*` helpers to import — both adapters go through
        # InferenceManager, which loads its model on the first call. The old
        # imports raised ImportError, `pass` swallowed it, and every first
        # sentiment/lead request paid the cold start instead.
        from app.services.ai.lead_prediction import lead_prediction_service
        from app.services.ai.sentiment import sentiment_service

        try:
            await lead_prediction_service.predict(
                clicks=0, views=1, time_spent_seconds=0, prior_purchases=0,
                source_platform="other", device="mobile", age_group="25-34",
                location_tier=1,
            )
        except Exception as exc:
            logger.info("warmup_lead_skipped reason=%s", exc)
        # DistilBERT is warmed last on purpose: only one model stays resident, so
        # the final warm-up is the one that survives, and its load (a HF
        # pipeline) is by far the expensive one. XGBoost just reads a booster file.
        try:
            await sentiment_service.analyze(["warm up"], source_type="ACTUAL")
        except Exception as exc:
            logger.info("warmup_sentiment_skipped reason=%s", exc)

    asyncio.create_task(warm_models())

    # Publishes due scheduled posts and syncs platform engagement.
    from app.services.posting.worker import start_worker
    worker_tasks = start_worker()

    logger.info("nexmarket_started")
    yield
    for task in worker_tasks:
        task.cancel()
    logger.info("nexmarket_shutting_down")


app = FastAPI(
    title="NexMarket AI",
    description="AI-Powered Marketing Automation Platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static Files (poster images) ──────────────────────────────────────────────
import os
os.makedirs(settings.POSTER_UPLOAD_DIR, exist_ok=True)
app.mount("/static/posters", StaticFiles(directory=settings.POSTER_UPLOAD_DIR), name="posters")

# ── API Routers ───────────────────────────────────────────────────────────────
PREFIX = "/api/v1"

app.include_router(campaigns.router, prefix=PREFIX)
app.include_router(posters.router, prefix=PREFIX)
app.include_router(adcopy.router, prefix=PREFIX)
app.include_router(posting.router, prefix=PREFIX)
app.include_router(sentiment.router, prefix=PREFIX)
app.include_router(leads.router, prefix=PREFIX)
app.include_router(forecast.router, prefix=PREFIX)
app.include_router(optimization.router, prefix=PREFIX)
app.include_router(analytics.router, prefix=PREFIX)
app.include_router(n8n_webhooks.router, prefix=PREFIX)
app.include_router(brand_kit.router, prefix=PREFIX)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "env": settings.APP_ENV,
        "social_mode": settings.SOCIAL_MODE,
        "llm_provider": settings.LLM_PROVIDER,
        "image_provider": settings.IMAGE_PROVIDER,
    }
