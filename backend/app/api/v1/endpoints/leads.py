"""Lead scoring endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import LeadScore
from app.schemas.schemas import LeadScoreRead, LeadScoreRequest
from app.services.ai.lead_prediction import lead_prediction_service

router = APIRouter(prefix="/leads", tags=["Lead Scoring"])


@router.post("/predict", response_model=LeadScoreRead)
async def predict_lead(
    payload: LeadScoreRequest, db: AsyncSession = Depends(get_db)
):
    result = await lead_prediction_service.predict(**payload.model_dump())

    record = LeadScore(
        campaign_id=payload.campaign_id,
        lead_identifier=payload.lead_identifier,
        score=result["score"],
        purchase_probability=result["purchase_probability"],
        category=result["category"],
        feature_importance=result["feature_importance"],
        input_features=payload.model_dump(),
    )
    db.add(record)
    await db.flush()
    return result


@router.get("/campaign/{campaign_id}")
async def get_campaign_leads(campaign_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    result = await db.execute(
        select(LeadScore)
        .where(LeadScore.campaign_id == campaign_id)
        .order_by(LeadScore.created_at.desc())
    )
    leads = result.scalars().all()
    return {
        "leads": leads,
        "total": len(leads),
        "hot": sum(1 for l in leads if l.category == "hot"),
        "warm": sum(1 for l in leads if l.category == "warm"),
        "cold": sum(1 for l in leads if l.category == "cold"),
    }
