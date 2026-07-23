"""
n8n Webhook endpoints — n8n calls these to trigger backend operations.
Backend does ALL AI logic; n8n is purely the orchestrator.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import AdCopy, Campaign, Poster, SocialPost
from app.schemas.schemas import N8nTriggerCampaign, N8nWebhookResponse
from app.services.ai.ad_generator import ad_copy_generator
from app.services.ai.lstm_forecast import lstm_forecast_service
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
    Runs all steps async; n8n polls /n8n/status/{campaign_id} for progress.
    """
    campaign = await db.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign.status = "generating"

    async def run_pipeline(campaign_id: str, steps: list):
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as bg_db:
            c = await bg_db.get(Campaign, campaign_id)
            results = {}

            if "poster" in steps:
                gen = await poster_generator.generate(
                    c.product_name, c.offer, c.target_audience, c.campaign_goal, c.brand_style
                )
                poster = Poster(campaign_id=c.id, **gen)
                bg_db.add(poster)
                await bg_db.flush()
                results["poster_id"] = poster.id

                if "evaluate" in steps:
                    raw = await poster_evaluator.evaluate(gen["image_url"])
                    from app.models.models import PosterEvaluation
                    norm = poster_evaluator.normalize(raw)
                    ev = PosterEvaluation(poster_id=poster.id, **norm)
                    bg_db.add(ev)
                    await bg_db.flush()

            if "adcopy" in steps:
                copies = await ad_copy_generator.generate(
                    c.product_name, c.description, c.offer,
                    c.target_audience, c.campaign_goal,
                    platforms=[c.preferred_platform] if c.preferred_platform != "all"
                    else ["instagram", "facebook", "linkedin", "twitter"],
                )
                for platform, data in copies.items():
                    ad = AdCopy(
                        campaign_id=c.id, platform=platform,
                        headline=data.get("headline"), body=data.get("body", ""),
                        cta_variants=data.get("cta_variants"), hashtags=data.get("hashtags"),
                    )
                    bg_db.add(ad)
                await bg_db.flush()

            if "optimize" in steps:
                opt = await campaign_optimizer.optimize(
                    campaign_goal=c.campaign_goal, 
                    target_audience=c.target_audience, 
                    budget=c.budget
                )
                results["optimization"] = opt

            if "post" in steps:
                target_platform = results.get("optimization", {}).get(
                    "recommended_platform", c.preferred_platform
                )
                sp = SocialPost(campaign_id=c.id, platform=target_platform, status="pending")
                bg_db.add(sp)
                await bg_db.flush()
                text = f"{c.product_name} — {c.offer}"
                image_url = None
                if results.get("poster_id"):
                    poster_obj = await bg_db.get(Poster, results["poster_id"])
                    image_url = poster_obj.image_url if poster_obj else None
                await social_posting_service.publish(bg_db, sp, text, image_url)

            c.status = "posted" if "post" in steps else "ready"
            await bg_db.commit()

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

    from sqlalchemy import select
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
