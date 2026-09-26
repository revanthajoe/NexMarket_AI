"""Analytics dashboard aggregation endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Integer, func, select
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


def _aggregate_source_type(is_mock: bool, has_simulated: bool, has_unknown: bool) -> str:
    if is_mock or has_simulated:
        return "SIMULATED"
    if has_unknown:
        return "UNKNOWN"
    return "ACTUAL"


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


def _window_start(days: int) -> datetime:
    """Midnight `days` ago. Compared against a DateTime column, so it must be a
    datetime — a bare date only happens to work on SQLite's string comparison."""
    days = max(1, min(days, 365))
    start = datetime.utcnow().date() - timedelta(days=days)
    return datetime.combine(start, datetime.min.time())


@router.get("/engagement/timeseries", response_model=List[Dict[str, Any]])
async def get_engagement_timeseries(
    days: int = 14,
    campaign_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Daily engagement totals, optionally scoped to one campaign.
    Returns an empty list when no analytics events have been ingested yet —
    the caller is expected to render an empty state, not fabricate a curve.
    """
    cutoff = _window_start(days)

    # event_date is a timestamp, so group on its date part — otherwise two
    # events on the same day become two separate points on the chart.
    day = func.date(AnalyticsEvent.event_date)

    stmt = (
        select(
            day,
            func.coalesce(func.sum(AnalyticsEvent.impressions), 0),
            func.coalesce(func.sum(AnalyticsEvent.clicks), 0),
            func.coalesce(func.sum(AnalyticsEvent.likes), 0),
            func.coalesce(func.sum(AnalyticsEvent.reach), 0),
            func.max(AnalyticsEvent.is_mock),
            func.max(func.cast(AnalyticsEvent.source_type == "SIMULATED", Integer)),
            func.max(func.cast(AnalyticsEvent.source_type == "UNKNOWN", Integer)),
        )
        .where(AnalyticsEvent.event_date >= cutoff)
        .group_by(day)
        .order_by(day.asc())
    )
    if campaign_id:
        stmt = stmt.where(AnalyticsEvent.campaign_id == campaign_id)

    result = await db.execute(stmt)

    return [
        {
            "date": event_date.isoformat() if hasattr(event_date, "isoformat") else str(event_date),
            "impressions": int(impressions),
            "clicks": int(clicks),
            "likes": int(likes),
            "reach": int(reach),
            "is_mock": bool(is_mock),
            "source_type": _aggregate_source_type(bool(is_mock), bool(has_simulated), bool(has_unknown)),
        }
        for event_date, impressions, clicks, likes, reach, is_mock, has_simulated, has_unknown in result.all()
    ]


@router.get("/engagement/platforms", response_model=List[Dict[str, Any]])
async def get_platform_breakdown(
    days: int = 14,
    campaign_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Per-platform engagement totals over the window, best performer first.

    CTR is recomputed from the summed clicks/impressions rather than averaged
    across rows — averaging per-day CTRs weights a 10-impression day the same as
    a 10,000-impression one.
    """
    cutoff = _window_start(days)

    stmt = (
        select(
            AnalyticsEvent.platform,
            func.coalesce(func.sum(AnalyticsEvent.impressions), 0),
            func.coalesce(func.sum(AnalyticsEvent.clicks), 0),
            func.coalesce(func.sum(AnalyticsEvent.likes), 0),
            func.coalesce(func.sum(AnalyticsEvent.shares), 0),
            func.coalesce(func.sum(AnalyticsEvent.comments), 0),
            func.coalesce(func.sum(AnalyticsEvent.reach), 0),
            func.coalesce(func.sum(AnalyticsEvent.spend), 0.0),
            func.max(AnalyticsEvent.is_mock),
            func.max(AnalyticsEvent.synced_at),
            func.max(func.cast(AnalyticsEvent.source_type == "SIMULATED", Integer)),
            func.max(func.cast(AnalyticsEvent.source_type == "UNKNOWN", Integer)),
        )
        .where(AnalyticsEvent.event_date >= cutoff)
        .group_by(AnalyticsEvent.platform)
    )
    if campaign_id:
        stmt = stmt.where(AnalyticsEvent.campaign_id == campaign_id)

    rows = (await db.execute(stmt)).all()

    breakdown = []
    for (
        platform, impressions, clicks, likes, shares,
        comments, reach, spend, is_mock, synced_at, has_simulated, has_unknown,
    ) in rows:
        impressions = int(impressions)
        clicks = int(clicks)
        breakdown.append({
            "platform": platform,
            "impressions": impressions,
            "clicks": clicks,
            "likes": int(likes),
            "shares": int(shares),
            "comments": int(comments),
            "reach": int(reach),
            "spend": round(float(spend), 2),
            "ctr": round(clicks / impressions, 6) if impressions else 0.0,
            "engagement_rate": (
                round((int(likes) + int(shares) + int(comments)) / impressions, 6)
                if impressions else 0.0
            ),
            "is_mock": bool(is_mock),
            "source_type": _aggregate_source_type(bool(is_mock), bool(has_simulated), bool(has_unknown)),
            "last_synced_at": synced_at.isoformat() if hasattr(synced_at, "isoformat") else synced_at,
        })

    breakdown.sort(key=lambda p: p["impressions"], reverse=True)
    return breakdown


@router.get("/tracking/status", response_model=Dict[str, Any])
async def get_tracking_status(
    campaign_id: Optional[str] = None, db: AsyncSession = Depends(get_db)
):
    """Provenance for whatever the analytics tab is about to render.

    The tab must be able to say where its numbers came from and how stale they
    are, instead of presenting an unlabelled chart of possibly-mock data.
    """
    stmt = select(
        func.count(AnalyticsEvent.id),
        func.max(AnalyticsEvent.synced_at),
        func.max(AnalyticsEvent.event_date),
        func.sum(func.cast(AnalyticsEvent.is_mock, Integer)),
        func.sum(func.cast(AnalyticsEvent.source_type == "ACTUAL", Integer)),
    )
    posts_stmt = select(func.count(SocialPost.id)).where(SocialPost.status == "posted")
    if campaign_id:
        stmt = stmt.where(AnalyticsEvent.campaign_id == campaign_id)
        posts_stmt = posts_stmt.where(SocialPost.campaign_id == campaign_id)

    total, last_synced, last_event, mock_count, actual_count = (await db.execute(stmt)).one()
    published_posts = (await db.execute(posts_stmt)).scalar() or 0

    total = int(total or 0)
    mock_count = int(mock_count or 0)
    actual_count = int(actual_count or 0)

    return {
        "campaign_id": campaign_id,
        "event_count": total,
        "published_posts": published_posts,
        "mock_event_count": mock_count,
        "actual_event_count": actual_count,
        "has_real_data": actual_count > 0,
        "last_synced_at": last_synced.isoformat() if hasattr(last_synced, "isoformat") else last_synced,
        "last_event_at": last_event.isoformat() if hasattr(last_event, "isoformat") else last_event,
    }


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
            "is_mock": e.is_mock,
            "source_type": e.source_type,
            "last_synced_at": e.synced_at.isoformat() if e.synced_at else None,
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


