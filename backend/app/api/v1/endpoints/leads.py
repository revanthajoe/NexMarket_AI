"""Lead scoring endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import require_app_api_key
from app.models.models import Campaign, LeadScore
from app.schemas.schemas import LeadScoreRead, LeadScoreRequest
from app.services.ai.lead_prediction import lead_prediction_service
from app.services.model_metadata import active_model_version_id

router = APIRouter(prefix="/leads", tags=["Lead Scoring"])


@router.post("/predict", response_model=LeadScoreRead)
async def predict_lead(
    payload: LeadScoreRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_app_api_key),
):
    campaign = await db.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    try:
        result = await lead_prediction_service.predict(**payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    model_version_id = None
    if result.get("source_type") == "PREDICTED":
        model_version_id = await active_model_version_id(db, "xgboost")

    record = LeadScore(
        campaign_id=payload.campaign_id,
        lead_identifier=payload.lead_identifier,
        score=result["score"],
        purchase_probability=result["purchase_probability"],
        category=result["category"],
        feature_importance=result["feature_importance"],
        input_features=payload.model_dump(),
        source_type=result.get("source_type", "UNKNOWN"),
        source_system=result.get("source_system"),
        model_name=result.get("model_name"),
        model_version=result.get("model_version"),
        is_fallback=result.get("is_fallback"),
        model_version_id=model_version_id,
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
