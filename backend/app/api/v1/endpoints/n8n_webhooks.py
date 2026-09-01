"""
n8n Webhook endpoints — n8n calls these to trigger backend operations.
Backend does ALL AI logic; n8n is purely the orchestrator.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import AdCopy, Campaign, Poster, SocialPost
from app.schemas.schemas import N8nTriggerCampaign, N8nWebhookResponse
from app.services.ai.ad_generator import ad_copy_generator
from app.services.ai.poster_evaluator import poster_evaluator
from app.services.ai.poster_generator import poster_generator
from app.services.optimization.optimizer import campaign_optimizer
from app.services.posting.posting_service import social_posting_service

router = APIRouter(prefix="/n8n", tags=["n8n Webhooks"])


@router.post("/trigger/campaign", response_model=N8nWebhookResponse)
async def n8n_trigger_campaign(
    payload: N8nTriggerCampaign,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Main entry point called by n8n to kick off the full campaign pipeline.
    Runs all steps async in a background task; each step is idempotent
    (skips if results already exist) to prevent duplicate DB rows.
    """
    campaign = await db.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign.status = "generating"

    async def run_pipeline(campaign_id: str, steps: list):
        import logging
        from sqlalchemy import text
        from app.db.session import AsyncSessionLocal

        log = logging.getLogger(__name__)

        # Use a completely independent session — NullPool guarantees no
        # connection sharing with the request that spawned this task.
        async with AsyncSessionLocal() as bg_db:
            # Apply WAL pragmas to this connection as well
            await bg_db.execute(text("PRAGMA journal_mode=WAL"))
            await bg_db.execute(text("PRAGMA busy_timeout=5000"))

            try:
                c = await bg_db.get(Campaign, campaign_id)
                if not c:
                    log.error("pipeline_abort campaign_id=%s not found", campaign_id)
                    return

                results: dict = {}

                # ── Poster ────────────────────────────────────────────────
                if "poster" in steps:
                    # Idempotency: skip if poster already exists
                    existing_posters = (await bg_db.execute(
                        select(Poster).where(Poster.campaign_id == campaign_id).limit(1)
                    )).scalars().all()

                    if existing_posters:
                        log.info("pipeline_skip_poster campaign_id=%s already has posters", campaign_id)
                        results["poster_id"] = existing_posters[0].id
                    else:
                        try:
                            gen = await poster_generator.generate(
                                campaign_name=c.name,
                                product_name=c.product_name,
                                description=c.description,
                                offer=c.offer,
                                target_audience=c.target_audience,
                                campaign_goal=c.campaign_goal,
                                brand_style=c.brand_style,
                                platform=c.preferred_platform or "instagram",
                                campaign_id=c.id,
                            )
                            poster = Poster(campaign_id=c.id, **gen)
                            bg_db.add(poster)
                            await bg_db.flush()
                            await bg_db.refresh(poster)
                            results["poster_id"] = poster.id
                            log.info("pipeline_poster_done id=%s", poster.id)
                        except Exception as exc:
                            log.error("pipeline_poster_failed: %s", exc, exc_info=True)
                            raise

                    # ── Evaluate ─────────────────────────────────────────
                    if "evaluate" in steps and results.get("poster_id"):
                        try:
                            poster_obj = await bg_db.get(Poster, results["poster_id"])
                            if poster_obj:
                                raw = await poster_evaluator.evaluate(poster_obj.image_url)
                                from app.models.models import PosterEvaluation
                                norm = poster_evaluator.normalize(raw)
                                ev = PosterEvaluation(poster_id=poster_obj.id, **norm)
                                bg_db.add(ev)
                                await bg_db.flush()
                                log.info("pipeline_evaluate_done poster_id=%s", poster_obj.id)
                        except Exception as exc:
                            log.error("pipeline_evaluate_failed: %s", exc, exc_info=True)

                # ── Ad Copy ───────────────────────────────────────────────
                if "adcopy" in steps:
                    # Idempotency: skip if ad copies already exist
                    existing_copies = (await bg_db.execute(
                        select(AdCopy).where(AdCopy.campaign_id == campaign_id).limit(1)
                    )).scalars().all()

                    if existing_copies:
                        log.info("pipeline_skip_adcopy campaign_id=%s already has copies", campaign_id)
                    else:
                        try:
                            platforms = (
                                [c.preferred_platform]
                                if c.preferred_platform != "all"
                                else ["instagram", "facebook", "linkedin", "twitter"]
                            )
                            copies = await ad_copy_generator.generate(
                                c.product_name, c.description, c.offer,
                                c.target_audience, c.campaign_goal,
                                platforms=platforms,
                            )
                            for platform, data in copies.items():
                                ad = AdCopy(
                                    campaign_id=c.id,
                                    platform=platform,
                                    headline=data.get("headline"),
                                    body=data.get("body", ""),
                                    cta_variants=data.get("cta_variants"),
                                    hashtags=data.get("hashtags"),
                                )
                                bg_db.add(ad)
                            await bg_db.flush()
                            log.info("pipeline_adcopy_done count=%d", len(copies))
                        except Exception as exc:
                            log.error("pipeline_adcopy_failed: %s", exc, exc_info=True)
                            raise

                # ── Optimize ──────────────────────────────────────────────
                if "optimize" in steps:
                    try:
                        opt = await campaign_optimizer.optimize(
                            campaign_goal=c.campaign_goal,
                            target_audience=c.target_audience,
                            budget=c.budget,
                        )
                        results["optimization"] = opt
                        log.info("pipeline_optimize_done platform=%s", opt.get("recommended_platform"))
                    except Exception as exc:
                        log.error("pipeline_optimize_failed: %s", exc, exc_info=True)
                        raise

                # ── Post ──────────────────────────────────────────────────
                if "post" in steps:
                    try:
                        target_platform = (
                            results.get("optimization", {}).get("recommended_platform")
                            or c.preferred_platform
                        )
                        sp = SocialPost(campaign_id=c.id, platform=target_platform, status="pending")
                        bg_db.add(sp)
                        await bg_db.flush()
                        await bg_db.refresh(sp)

                        text_content = f"{c.product_name} — {c.offer}"
                        image_url = None
                        if results.get("poster_id"):
                            poster_obj = await bg_db.get(Poster, results["poster_id"])
                            image_url = poster_obj.image_url if poster_obj else None

                        await social_posting_service.publish(bg_db, sp, text_content, image_url)
                        log.info("pipeline_post_done platform=%s", target_platform)
                    except Exception as exc:
                        log.error("pipeline_post_failed: %s", exc, exc_info=True)
                        raise

                # ── Finalise ──────────────────────────────────────────────
                c.status = "posted" if "post" in steps else "ready"
                await bg_db.commit()
                log.info("pipeline_complete campaign_id=%s status=%s", campaign_id, c.status)

            except Exception as exc:
                log.error("pipeline_unhandled_error campaign_id=%s: %s", campaign_id, exc, exc_info=True)
                await bg_db.rollback()
                # Mark campaign as failed so the UI can reflect it
                async with AsyncSessionLocal() as err_db:
                    await err_db.execute(text("PRAGMA busy_timeout=5000"))
                    failed_c = await err_db.get(Campaign, campaign_id)
                    if failed_c:
                        failed_c.status = "failed"
                        await err_db.commit()

    background_tasks.add_task(run_pipeline, payload.campaign_id, payload.steps)
    return N8nWebhookResponse(
        status="accepted",
        message=f"Campaign pipeline started for {payload.campaign_id}",
        data={"steps": payload.steps},
    )


@router.get("/status/{campaign_id}", response_model=Dict[str, Any])
async def n8n_campaign_status(campaign_id: str, db: AsyncSession = Depends(get_db)):
    """n8n polls this to check pipeline progress."""
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    posts_r = await db.execute(
        select(SocialPost).where(SocialPost.campaign_id == campaign_id)
    )
    posts = posts_r.scalars().all()

    return {
        "campaign_id": campaign_id,
        "status": campaign.status,
        "posts": [
            {"platform": p.platform, "status": p.status, "is_mock": p.is_mock}
            for p in posts
        ],
    }


@router.post("/analytics/ingest")
async def n8n_ingest_analytics(
    data: Dict[str, Any], db: AsyncSession = Depends(get_db)
):
    """n8n calls this to push analytics events from platform APIs."""
    from app.models.models import AnalyticsEvent
    from datetime import datetime

    event = AnalyticsEvent(
        campaign_id=data["campaign_id"],
        platform=data.get("platform", "unknown"),
        event_date=datetime.fromisoformat(data.get("event_date", datetime.utcnow().isoformat())),
        impressions=data.get("impressions", 0),
        clicks=data.get("clicks", 0),
        likes=data.get("likes", 0),
        shares=data.get("shares", 0),
        comments=data.get("comments", 0),
        reach=data.get("reach", 0),
        ctr=data.get("ctr", 0.0),
        spend=data.get("spend", 0.0),
    )
    db.add(event)
    return {"status": "ok"}


@router.post("/report/trigger")
async def n8n_trigger_report(
    data: Dict[str, Any], db: AsyncSession = Depends(get_db)
):
    """n8n triggers a report generation."""
    campaign_id = data.get("campaign_id")
    return {
        "status": "ok",
        "message": f"Report generation triggered for {campaign_id}",
        "report_url": f"/api/v1/analytics/{campaign_id}/report",
    }
