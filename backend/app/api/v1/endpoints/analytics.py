"""Analytics dashboard aggregation endpoints."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import (
    AdCopy,
    AnalyticsEvent,
    Campaign,
    EngagementForecast,
    LeadScore,
    OptimizationResult,
    Poster,
    PosterEvaluation,
    SentimentResult,
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


@router.get("/{campaign_id}/report", response_model=Dict[str, Any])
async def get_campaign_report(campaign_id: str, db: AsyncSession = Depends(get_db)):
    """
    Full campaign report — aggregates poster evaluation, ad copy, publishing,
    analytics totals, sentiment, lead scoring, forecast, and optimization
    results into a single summary document (Workflow D: Reporting).
    """
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    posters_result = await db.execute(
        select(Poster).where(Poster.campaign_id == campaign_id)
    )
    posters = posters_result.scalars().all()

    evaluations: List[PosterEvaluation] = []
    if posters:
        poster_ids = [p.id for p in posters]
        eval_result = await db.execute(
            select(PosterEvaluation).where(PosterEvaluation.poster_id.in_(poster_ids))
        )
        evaluations = eval_result.scalars().all()

    ad_copies_result = await db.execute(
        select(AdCopy).where(AdCopy.campaign_id == campaign_id)
    )
    ad_copies = ad_copies_result.scalars().all()

    posts_result = await db.execute(
        select(SocialPost).where(SocialPost.campaign_id == campaign_id)
    )
    social_posts = posts_result.scalars().all()

    totals_row = (
        await db.execute(
            select(
                func.coalesce(func.sum(AnalyticsEvent.impressions), 0),
                func.coalesce(func.sum(AnalyticsEvent.clicks), 0),
                func.coalesce(func.sum(AnalyticsEvent.likes), 0),
                func.coalesce(func.sum(AnalyticsEvent.shares), 0),
                func.coalesce(func.sum(AnalyticsEvent.comments), 0),
                func.coalesce(func.sum(AnalyticsEvent.reach), 0),
                func.coalesce(func.avg(AnalyticsEvent.ctr), 0.0),
                func.coalesce(func.sum(AnalyticsEvent.spend), 0.0),
            ).where(AnalyticsEvent.campaign_id == campaign_id)
        )
    ).one()
    (
        total_impressions, total_clicks, total_likes, total_shares,
        total_comments, total_reach, avg_ctr, total_spend,
    ) = totals_row

    sentiment_result = await db.execute(
        select(SentimentResult).where(SentimentResult.campaign_id == campaign_id)
    )
    sentiments = sentiment_result.scalars().all()
    sentiment_breakdown = {"positive": 0, "negative": 0, "neutral": 0}
    for s in sentiments:
        if s.label in sentiment_breakdown:
            sentiment_breakdown[s.label] += 1

    leads_result = await db.execute(
        select(LeadScore).where(LeadScore.campaign_id == campaign_id)
    )
    leads = leads_result.scalars().all()
    lead_breakdown = {"hot": 0, "warm": 0, "cold": 0}
    for l in leads:
        if l.category in lead_breakdown:
            lead_breakdown[l.category] += 1

    forecast_result = await db.execute(
        select(EngagementForecast)
        .where(EngagementForecast.campaign_id == campaign_id)
        .order_by(EngagementForecast.created_at.desc())
        .limit(1)
    )
    latest_forecast = forecast_result.scalar_one_or_none()

    optimization_result = await db.execute(
        select(OptimizationResult)
        .where(OptimizationResult.campaign_id == campaign_id)
        .order_by(OptimizationResult.created_at.desc())
        .limit(1)
    )
    latest_optimization = optimization_result.scalar_one_or_none()

    best_evaluation = max(evaluations, key=lambda e: e.overall_score, default=None)

    return {
        "campaign": {
            "id": campaign.id,
            "name": campaign.name,
            "product_name": campaign.product_name,
            "status": campaign.status,
            "preferred_platform": campaign.preferred_platform,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        },
        "creative": {
            "posters_generated": len(posters),
            "best_poster_score": best_evaluation.overall_score if best_evaluation else None,
            "ad_copies_generated": len(ad_copies),
            "platforms_covered": sorted({a.platform for a in ad_copies}),
        },
        "publishing": {
            "total_posts": len(social_posts),
            "posted": sum(1 for p in social_posts if p.status == "posted"),
            "failed": sum(1 for p in social_posts if p.status == "failed"),
            "pending": sum(1 for p in social_posts if p.status in ("pending", "scheduled", "posting")),
        },
        "analytics_totals": {
            "impressions": int(total_impressions),
            "clicks": int(total_clicks),
            "likes": int(total_likes),
            "shares": int(total_shares),
            "comments": int(total_comments),
            "reach": int(total_reach),
            "avg_ctr": round(float(avg_ctr), 4),
            "spend": round(float(total_spend), 2),
        },
        "sentiment": {
            "total_analyzed": len(sentiments),
            "breakdown": sentiment_breakdown,
        },
        "leads": {
            "total_scored": len(leads),
            "breakdown": lead_breakdown,
        },
        "forecast": {
            "horizon_days": latest_forecast.forecast_horizon_days if latest_forecast else None,
            "predicted_reach": latest_forecast.predicted_reach if latest_forecast else None,
            "predicted_ctr": latest_forecast.predicted_ctr if latest_forecast else None,
        } if latest_forecast else None,
        "optimization": {
            "recommended_platform": latest_optimization.recommended_platform,
            "recommended_time": latest_optimization.recommended_time,
            "recommended_budget": latest_optimization.recommended_budget,
            "confidence": latest_optimization.confidence,
            "reasoning": latest_optimization.reasoning,
        } if latest_optimization else None,
    }


