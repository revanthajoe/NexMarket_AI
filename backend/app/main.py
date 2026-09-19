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

    # Pre-warm ML models in background (non-blocking)
    import asyncio

    async def warm_models():
        try:
            from app.services.ai.sentiment import _load_pipeline
            _load_pipeline()
        except Exception:
            pass
        try:
            from app.services.ai.lead_prediction import _load_or_train_model
            _load_or_train_model()
        except Exception:
            pass

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
