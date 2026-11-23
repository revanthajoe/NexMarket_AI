"""Campaign optimization endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import require_app_api_key
from app.models.models import AnalyticsEvent, Campaign, OptimizationResult
from app.schemas.schemas import OptimizationRead, OptimizationRequest
from app.services.optimization.optimizer import campaign_optimizer

router = APIRouter(prefix="/optimize", tags=["Optimization"])


@router.post("/", response_model=OptimizationRead)
async def optimize_campaign(
    payload: OptimizationRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_app_api_key),
):
    campaign = await db.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Build platform history from analytics
    result = await db.execute(
        select(AnalyticsEvent)
        .where(AnalyticsEvent.campaign_id == payload.campaign_id)
        .where(AnalyticsEvent.source_type == "ACTUAL")
    )
    events = result.scalars().all()

    platform_history: dict = {}
    for e in events:
        if e.platform not in platform_history:
            platform_history[e.platform] = {"ctr": [], "clicks": [], "impressions": []}
        # Every one of these columns is nullable. The Telegram ingestion path,
        # for instance, records impressions and comments but never clicks —
        # summing a None raises TypeError and 500s this endpoint.
        platform_history[e.platform]["ctr"].append(float(e.ctr or 0.0))
        platform_history[e.platform]["clicks"].append(int(e.clicks or 0))
        platform_history[e.platform]["impressions"].append(int(e.impressions or 0))

    # Compute averages
    platform_avg = {}
    for platform, values in platform_history.items():
        impressions = sum(values["impressions"])
        clicks = sum(values["clicks"])
        platform_avg[platform] = {
            "ctr": clicks / impressions if impressions else 0.0,
            "clicks": clicks,
            "impressions": impressions,
        }

    opt = await campaign_optimizer.optimize(
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
        source_type="RECOMMENDATION",
        algorithm="Thompson Sampling",
        policy_version=opt.get("policy_version"),
        reward_source=opt.get("reward_source", "UNKNOWN"),
        analytics_reference=None,
        reward=None,
        bandit_updated=False,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


@router.post("/{optimization_id}/reward", response_model=OptimizationRead)
async def sync_optimization_reward(
    optimization_id: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_app_api_key),
):
    """Update Thompson Sampling only from a matching ACTUAL analytics event."""
    record = await db.get(OptimizationResult, optimization_id)
    if not record:
        raise HTTPException(status_code=404, detail="Optimization result not found")
    if record.bandit_updated:
        return record

    event = (await db.execute(
        select(AnalyticsEvent)
        .where(AnalyticsEvent.campaign_id == record.campaign_id)
        .where(AnalyticsEvent.platform == record.recommended_platform)
        .where(AnalyticsEvent.source_type == "ACTUAL")
        .order_by(AnalyticsEvent.event_date.desc())
        .limit(1)
    )).scalar_one_or_none()
    if event is None:
        record.reward_source = "UNKNOWN"
        record.reward = None
        record.analytics_reference = None
        await db.commit()
        await db.refresh(record)
        return record

    reward = 1.0 if (event.clicks or 0) > 0 else 0.0
    campaign = await db.get(Campaign, record.campaign_id)
    await campaign_optimizer.record_result(
        record.recommended_platform,
        clicked=reward > 0,
        campaign_goal=campaign.campaign_goal if campaign else None,
        target_audience=campaign.target_audience if campaign else None,
    )
    record.reward = reward
    record.reward_source = "ACTUAL"
    record.analytics_reference = f"analytics_event:{event.id}"
    record.bandit_updated = True
    await db.commit()
    await db.refresh(record)
    return record
