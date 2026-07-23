"""LSTM Engagement Forecasting endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import AnalyticsEvent, Campaign, EngagementForecast
from app.schemas.schemas import ForecastRead, ForecastRequest
from app.services.ai.lstm_forecast import lstm_forecast_service

router = APIRouter(prefix="/forecast", tags=["Engagement Forecasting"])


@router.post("/", response_model=ForecastRead)
async def create_forecast(
    payload: ForecastRequest, db: AsyncSession = Depends(get_db)
):
    campaign = await db.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Fetch historical analytics events for this campaign
    result = await db.execute(
        select(AnalyticsEvent)
        .where(AnalyticsEvent.campaign_id == payload.campaign_id)
        .order_by(AnalyticsEvent.event_date.asc())
    )
    events = result.scalars().all()

    history = [
        {
            "likes": e.likes,
            "shares": e.shares,
            "comments": e.comments,
            "ctr": e.ctr,
            "reach": e.reach,
        }
        for e in events
    ]

    forecast_data = lstm_forecast_service.forecast(history, payload.horizon_days)

    record = EngagementForecast(
        campaign_id=payload.campaign_id,
        forecast_horizon_days=payload.horizon_days,
        predicted_likes=forecast_data.get("predicted_likes"),
        predicted_shares=forecast_data.get("predicted_shares"),
        predicted_comments=forecast_data.get("predicted_comments"),
        predicted_ctr=forecast_data.get("predicted_ctr"),
        predicted_reach=forecast_data.get("predicted_reach"),
        confidence_intervals=forecast_data.get("confidence_intervals"),
        model_version="v1",
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


@router.get("/campaign/{campaign_id}")
async def get_forecasts(campaign_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EngagementForecast)
        .where(EngagementForecast.campaign_id == campaign_id)
        .order_by(EngagementForecast.created_at.desc())
        .limit(10)
    )
    return result.scalars().all()
