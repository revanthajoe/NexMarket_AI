"""
Background posting worker.

Two loops, both started from the app lifespan:

  * scheduler     — publishes `scheduled` posts once `scheduled_at` has passed.
                    Without this nothing ever picked those rows up again.
  * metrics sync  — pulls engagement back from each platform into
                    AnalyticsEvent rows, so the analytics tab reflects what
                    actually happened rather than only what was ingested by hand.

Both are best-effort: an exception in one cycle is logged and the loop keeps
running, because a transient platform outage must not kill the worker.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.models.models import SocialPost
from app.services.posting.posting_service import social_posting_service

logger = get_logger(__name__)


async def _scheduler_loop() -> None:
    from app.db.session import AsyncSessionLocal

    while True:
        await asyncio.sleep(settings.SCHEDULER_INTERVAL_SECONDS)
        try:
            async with AsyncSessionLocal() as db:
                published = await social_posting_service.publish_scheduled_due(db)
                if published:
                    logger.info("scheduler_cycle", published=published)
        except Exception as exc:
            logger.error("scheduler_cycle_failed", error=str(exc))


async def _metrics_loop() -> None:
    from app.db.session import AsyncSessionLocal

    while True:
        await asyncio.sleep(settings.METRICS_SYNC_INTERVAL_SECONDS)
        try:
            async with AsyncSessionLocal() as db:
                campaign_ids = (
                    await db.execute(
                        select(SocialPost.campaign_id)
                        .where(SocialPost.status == "posted")
                        .distinct()
                    )
                ).scalars().all()

                for campaign_id in campaign_ids:
                    await social_posting_service.sync_campaign_metrics(db, campaign_id)

                if campaign_ids:
                    logger.info("metrics_cycle", campaigns=len(campaign_ids))
        except Exception as exc:
            logger.error("metrics_cycle_failed", error=str(exc))


def start_worker() -> list[asyncio.Task]:
    """Start both loops. Returns the tasks so the caller can cancel them."""
    if not settings.SCHEDULER_ENABLED:
        logger.info("posting_worker_disabled")
        return []

    tasks = [
        asyncio.create_task(_scheduler_loop(), name="posting-scheduler"),
        asyncio.create_task(_metrics_loop(), name="posting-metrics-sync"),
    ]
    logger.info(
        "posting_worker_started",
        scheduler_interval=settings.SCHEDULER_INTERVAL_SECONDS,
        metrics_interval=settings.METRICS_SYNC_INTERVAL_SECONDS,
    )
    return tasks
