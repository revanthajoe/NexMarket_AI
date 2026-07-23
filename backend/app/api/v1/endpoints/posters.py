"""Poster generation + evaluation endpoints."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import Campaign, Poster, PosterEvaluation
from app.schemas.schemas import PosterEvaluationRead, PosterGenerateRequest, PosterRead
from app.services.ai.poster_evaluator import poster_evaluator
from app.services.ai.poster_generator import poster_generator

router = APIRouter(prefix="/posters", tags=["Posters"])


@router.post("/generate", response_model=List[PosterRead])
async def generate_posters(
    payload: PosterGenerateRequest, db: AsyncSession = Depends(get_db)
):
    campaign = await db.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    results = []
    for i in range(payload.variations):
        gen = await poster_generator.generate(
            product_name=campaign.product_name,
            offer=campaign.offer,
            target_audience=campaign.target_audience,
            campaign_goal=campaign.campaign_goal,
            brand_style=payload.style_override or campaign.brand_style,
            variation=i,
        )
        poster = Poster(
            campaign_id=campaign.id,
            image_url=gen["image_url"],
            prompt_used=gen["prompt_used"],
            provider=gen["provider"],
            variation_index=i,
        )
        db.add(poster)
        await db.flush()
        await db.refresh(poster)
        results.append(poster)

    return results


@router.post("/{poster_id}/evaluate", response_model=PosterEvaluationRead)
async def evaluate_poster(poster_id: str, db: AsyncSession = Depends(get_db)):
    poster = await db.get(Poster, poster_id)
    if not poster:
        raise HTTPException(status_code=404, detail="Poster not found")

    raw = await poster_evaluator.evaluate(poster.image_url)
    normalized = poster_evaluator.normalize(raw)

    evaluation = PosterEvaluation(
        poster_id=poster_id,
        overall_score=normalized["overall_score"],
        readability_score=normalized["readability_score"],
        layout_score=normalized["layout_score"],
        branding_score=normalized["branding_score"],
        contrast_score=normalized["contrast_score"],
        cta_score=normalized["cta_score"],
        visual_appeal_score=normalized["visual_appeal_score"],
        strengths=normalized["strengths"],
        weaknesses=normalized["weaknesses"],
        suggestions=normalized["suggestions"],
        raw_response=normalized["raw_response"],
    )
    db.add(evaluation)
    await db.flush()
    await db.refresh(evaluation)
    return evaluation


@router.get("/{poster_id}/evaluations", response_model=List[PosterEvaluationRead])
async def get_evaluations(poster_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    result = await db.execute(
        select(PosterEvaluation).where(PosterEvaluation.poster_id == poster_id)
    )
    return result.scalars().all()
