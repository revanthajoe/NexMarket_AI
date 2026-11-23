"""Sentiment analysis endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import require_app_api_key
from app.models.models import Campaign, SentimentResult
from app.schemas.schemas import SentimentBatchResponse, SentimentRequest
from app.services.ai.sentiment import sentiment_service
from app.services.model_metadata import active_model_version_id

router = APIRouter(prefix="/sentiment", tags=["Sentiment"])


@router.post("/analyze", response_model=SentimentBatchResponse)
async def analyze_sentiment(
    payload: SentimentRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_app_api_key),
):
    if payload.campaign_id is not None:
        campaign = await db.get(Campaign, payload.campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
    if payload.source_type != "ACTUAL":
        raise HTTPException(status_code=422, detail="Sentiment requires ACTUAL input text")
    try:
        analysis = await sentiment_service.analyze(
            payload.texts,
            payload.campaign_id,
            payload.source_type,
            payload.source_system,
            payload.source_reference,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    results = analysis["results"]
    summary = analysis["summary"]

    for r in results:
        record = SentimentResult(
            campaign_id=payload.campaign_id,
            text=r["text"],
            label=r["label"],
            positive_score=r["positive_score"],
            negative_score=r["negative_score"],
            neutral_score=r.get("neutral_score", 0.0),
            confidence=r["confidence"],
            model_used=r["model_used"],
            source_type=r.get("source_type", "UNKNOWN"),
            input_source_type=r.get("input_source_type", payload.source_type),
            source_system=r.get("source_system"),
            source_reference=r.get("source_reference"),
            model_name=r.get("model_name"),
            model_version=r.get("model_version"),
            model_version_id=(
                await active_model_version_id(db, "distilbert")
                if r.get("source_type") == "PREDICTED" else None
            ),
        )
        db.add(record)

    return SentimentBatchResponse(results=results, summary=summary)
