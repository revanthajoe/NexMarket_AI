"""Sentiment analysis endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import SentimentResult
from app.schemas.schemas import SentimentBatchResponse, SentimentRequest
from app.services.ai.sentiment import sentiment_service

router = APIRouter(prefix="/sentiment", tags=["Sentiment"])


@router.post("/analyze", response_model=SentimentBatchResponse)
async def analyze_sentiment(
    payload: SentimentRequest, db: AsyncSession = Depends(get_db)
):
    results = await sentiment_service.analyze_batch(payload.texts, payload.campaign_id)
    summary = sentiment_service.summarize(results)

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
        )
        db.add(record)

    return SentimentBatchResponse(results=results, summary=summary)
