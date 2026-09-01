"""Poster generation + evaluation endpoints."""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import Campaign, Poster, PosterEvaluation
from app.schemas.schemas import PosterEvaluationRead, PosterGenerateRequest, PosterRead
from app.services.ai.poster_evaluator import poster_evaluator
from app.services.ai.poster_generator import poster_generator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/posters", tags=["Posters"])


@router.get("/campaign/{campaign_id}", response_model=List[PosterRead])
async def list_posters_by_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    result = await db.execute(
        select(Poster).where(Poster.campaign_id == campaign_id).order_by(Poster.variation_index)
    )
    return result.scalars().all()


@router.post("/generate", response_model=List[PosterRead])
async def generate_posters(
    payload: PosterGenerateRequest, db: AsyncSession = Depends(get_db)
):
    campaign = await db.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    logger.info(
        "poster_generate_start campaign_id=%s variations=%d",
        payload.campaign_id, payload.variations,
    )

    results = []
    for i in range(payload.variations):
        try:
            gen = await poster_generator.generate(
                campaign_name=campaign.name,
                product_name=campaign.product_name,
                description=campaign.description,
                offer=campaign.offer,
                target_audience=campaign.target_audience,
                campaign_goal=campaign.campaign_goal,
                brand_style=payload.style_override or campaign.brand_style,
                variation=i,
                platform=campaign.preferred_platform or "instagram",
                campaign_id=campaign.id,
                seed=(payload.seed + i) if payload.seed is not None else None,
            )
        except Exception as exc:
            logger.error(
                "poster_generate_error campaign_id=%s variation=%d error=%s",
                payload.campaign_id, i, exc, exc_info=True,
            )
            raise HTTPException(status_code=500, detail=f"Poster generation failed: {exc}")

        poster = Poster(
            campaign_id=campaign.id,
            image_url=gen["image_url"],
            prompt_used=gen["prompt_used"],
            provider=gen["provider"],
            variation_index=i,
            metadata_=gen.get("metadata_")
        )
        db.add(poster)
        await db.flush()
        await db.refresh(poster)
        results.append(poster)
        logger.info(
            "poster_generate_saved poster_id=%s url=%s",
            poster.id, poster.image_url,
        )

    # Commit so created_at is persisted and populated on returned objects
    await db.commit()
    for p in results:
        await db.refresh(p)

    return results


@router.post("/{poster_id}/evaluate", response_model=PosterEvaluationRead)
async def evaluate_poster(poster_id: str, db: AsyncSession = Depends(get_db)):
    poster = await db.get(Poster, poster_id)
    if not poster:
        raise HTTPException(status_code=404, detail="Poster not found")

    logger.info("poster_evaluate_start poster_id=%s url=%s", poster_id, poster.image_url)

    try:
        if poster.metadata_ and "evaluation" in poster.metadata_:
            logger.info("poster_evaluate using cached evaluation from metadata")
            normalized = poster.metadata_["evaluation"]
        else:
            # poster_evaluator.evaluate() already calls normalize() internally;
            # the returned dict is the flat, schema-ready structure — do NOT re-normalize.
            normalized = await poster_evaluator.evaluate(poster.image_url)
    except Exception as exc:
        logger.error(
            "poster_evaluate_error poster_id=%s error=%s", poster_id, exc, exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Poster evaluation failed: {exc}")

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
        raw_response=normalized.get("raw_response", {}),
    )
    db.add(evaluation)
    await db.flush()
    await db.refresh(evaluation)
    logger.info("poster_evaluate_saved eval_id=%s score=%s", evaluation.id, evaluation.overall_score)
    return evaluation


@router.get("/{poster_id}/evaluations", response_model=List[PosterEvaluationRead])
async def get_evaluations(poster_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    result = await db.execute(
        select(PosterEvaluation).where(PosterEvaluation.poster_id == poster_id)
    )
    return result.scalars().all()
