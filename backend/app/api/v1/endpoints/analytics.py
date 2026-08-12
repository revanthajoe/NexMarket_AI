"""Analytics dashboard aggregation endpoints."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import (
    AnalyticsEvent,
    Campaign,
    LeadScore,
    SocialPost,
)
from app.schemas.schemas import DashboardSummary

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/dashboard", response_model=DashboardSummary)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    total_campaigns = (await db.execute(select(func.count(Campaign.id)))).scalar() or 0
    active_campaigns = (
        await db.execute(
            select(func.count(Campaign.id)).where(Campaign.status.in_(["generating", "ready", "posted"]))
        )
    ).scalar() or 0
    total_posts = (await db.execute(select(func.count(SocialPost.id)))).scalar() or 0
    successful_posts = (
        await db.execute(
            select(func.count(SocialPost.id)).where(SocialPost.status == "posted")
        )
    ).scalar() or 0
    avg_ctr_row = (await db.execute(select(func.avg(AnalyticsEvent.ctr)))).scalar()
    avg_ctr = round(float(avg_ctr_row or 0.0) * 100, 2)

    total_leads = (await db.execute(select(func.count(LeadScore.id)))).scalar() or 0
    hot_leads = (
        await db.execute(
            select(func.count(LeadScore.id)).where(LeadScore.category == "hot")
        )
    ).scalar() or 0

    return DashboardSummary(
        total_campaigns=total_campaigns,
        active_campaigns=active_campaigns,
        total_posts=total_posts,
        successful_posts=successful_posts,
        avg_engagement_rate=avg_ctr,
        total_leads=total_leads,
        hot_leads=hot_leads,
    )


@router.get("/campaign/{campaign_id}", response_model=List[Dict[str, Any]])
async def get_campaign_analytics(campaign_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AnalyticsEvent)
        .where(AnalyticsEvent.campaign_id == campaign_id)
        .order_by(AnalyticsEvent.event_date.asc())
    )
    events = result.scalars().all()
    return [
        {
            "date": e.event_date.isoformat(),
            "platform": e.platform,
            "impressions": e.impressions,
            "clicks": e.clicks,
            "likes": e.likes,
            "shares": e.shares,
            "comments": e.comments,
            "reach": e.reach,
            "ctr": e.ctr,
            "spend": e.spend,
        }
        for e in events
    ]


