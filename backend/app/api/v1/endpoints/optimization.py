"""Campaign optimization endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import AnalyticsEvent, Campaign, OptimizationResult
from app.schemas.schemas import OptimizationRead, OptimizationRequest
from app.services.optimization.optimizer import optimization_service

router = APIRouter(prefix="/optimize", tags=["Optimization"])


@router.post("/", response_model=OptimizationRead)
async def optimize_campaign(
    payload: OptimizationRequest, db: AsyncSession = Depends(get_db)
):
    campaign = await db.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Build platform history from analytics
    result = await db.execute(
        select(AnalyticsEvent).where(AnalyticsEvent.campaign_id == payload.campaign_id)
    )
    events = result.scalars().all()

    platform_history: dict = {}
    for e in events:
        if e.platform not in platform_history:
            platform_history[e.platform] = {"ctr": [], "clicks": [], "impressions": []}
        platform_history[e.platform]["ctr"].append(e.ctr)
        platform_history[e.platform]["clicks"].append(e.clicks)
        platform_history[e.platform]["impressions"].append(e.impressions)

    # Compute averages
    platform_avg = {
        p: {"ctr": sum(v["ctr"]) / max(len(v["ctr"]), 1)}
        for p, v in platform_history.items()
    }

    opt = await optimization_service.optimize(
        campaign_goal=campaign.campaign_goal,
        target_audience=campaign.target_audience,
        platform_history=platform_avg,
        budget=payload.budget or campaign.budget,
    )

    record = OptimizationResult(
        campaign_id=campaign.id,
        recommended_platform=opt["recommended_platform"],
        recommended_time=opt.get("recommended_time"),
        recommended_budget=opt.get("recommended_budget"),
        confidence=opt.get("confidence", 0),
        reasoning=opt.get("reasoning"),
        platform_scores=opt.get("platform_scores"),
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record
