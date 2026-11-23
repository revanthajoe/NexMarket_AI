"""Poster generation + evaluation endpoints."""
from __future__ import annotations

import inspect
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import require_app_api_key
from app.db.session import get_db
from app.models.models import Campaign, ModelVersion, Poster, PosterEvaluation, PosterFeedback
from app.schemas.schemas import PosterEvaluationRead, PosterFeedbackCreate, PosterFeedbackRead, PosterGenerateRequest, PosterRead
from app.services.ai.poster_evaluator import poster_evaluator
from app.services.ai.poster_generator import poster_generator
from app.services.model_metadata import active_model_version_id
from app.services.poster_feedback import derive_improvement_instructions
from app.services.sdxl_lora import active_sdxl_runtime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/posters", tags=["Posters"])


@router.get("/campaign/{campaign_id}", response_model=List[PosterRead])
async def list_posters_by_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    result = await db.execute(
        select(Poster)
        .where(Poster.campaign_id == campaign_id)
        .order_by(Poster.version, Poster.variation_index)
    )
    return result.scalars().all()


@router.post("/generate", response_model=List[PosterRead])
async def generate_posters(
    payload: PosterGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_app_api_key),
):
    campaign = await db.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    logger.info(
        "poster_generate_start campaign_id=%s variations=%d",
        payload.campaign_id, payload.variations,
    )

    # Snapshot the campaign fields we need, then release the read transaction.
    # Generation below takes minutes of GPU time per variation, and SQLite only
    # permits one writer — holding this transaction open starves the posting
    # worker and analytics sync and comes back as "database is locked".
    campaign_fields = dict(
        campaign_name=campaign.name,
        product_name=campaign.product_name,
        description=campaign.description,
        offer=campaign.offer,
        target_audience=campaign.target_audience,
        campaign_goal=campaign.campaign_goal,
        brand_style=payload.style_override or campaign.brand_style,
        platform=campaign.preferred_platform or "instagram",
        campaign_id=campaign.id,
    )
    await db.commit()

    results = []
    if settings.IMAGE_PROVIDER == "local":
        sdxl_model_version_id, sdxl_lora_path = await active_sdxl_runtime(db)
    else:
        sdxl_model_version_id, sdxl_lora_path = None, None
    for i in range(payload.variations):
        gen = None
        try:
            gen = await poster_generator.generate(
                **campaign_fields,
                variation=i,
                seed=(payload.seed + i) if payload.seed is not None else None,
                language=payload.language,
                sdxl_model_version_id=sdxl_model_version_id,
                sdxl_lora_path=sdxl_lora_path,
            )
            if gen.get("provider") == "mock" and settings.IMAGE_PROVIDER != "mock":
                raise RuntimeError("Image generation returned a mock poster while IMAGE_PROVIDER is not mock")

            poster = Poster(
                campaign_id=campaign_fields["campaign_id"],
                image_url=gen["image_url"],
                prompt_used=gen["prompt_used"],
                provider=gen["provider"],
                variation_index=i,
                metadata_=gen.get("metadata_"),
                model_version_id=gen.get("model_version_id", sdxl_model_version_id),
            )
            db.add(poster)
            # Commit per variation: one short write transaction each, so a
            # later failure cannot roll back posters already generated.
            await db.commit()
            await db.refresh(poster)
            results.append(poster)
            logger.info(
                "poster_generate_saved poster_id=%s url=%s",
                poster.id, poster.image_url,
            )
        except Exception as exc:
            logger.error(
                "poster_generate_error campaign_id=%s variation=%d error=%s",
                payload.campaign_id, i, exc, exc_info=True,
            )
            # The image already exists on disk if generation got that far — only
            # the DB write failed. Log the path so minutes of GPU output are
            # recoverable instead of being silently orphaned.
            if gen is not None:
                logger.error(
                    "poster_generate_orphaned_image campaign_id=%s variation=%d url=%s",
                    payload.campaign_id, i, gen.get("image_url"),
                )
            # The failure may have been the commit itself, which leaves the
            # session unusable — get_db() commits again on the way out.
            await db.rollback()
            # Each variation costs minutes of GPU time. If earlier ones already
            # succeeded, keep them instead of failing the whole request and
            # throwing that work away.
            if results:
                logger.warning(
                    "poster_generate_partial campaign_id=%s produced=%d/%d",
                    payload.campaign_id, len(results), payload.variations,
                )
                break
            raise HTTPException(status_code=500, detail=f"Poster generation failed: {exc}")

    return results


@router.post("/{poster_id}/evaluate", response_model=PosterEvaluationRead)
async def evaluate_poster(
    poster_id: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_app_api_key),
):
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

    model_version_id = None
    if normalized.get("source_type") == "PREDICTED":
        model_version_id = await active_model_version_id(db, "qwen_vl")

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
        source_type=normalized.get("source_type", "UNKNOWN"),
        source_system=normalized.get("source_system"),
        model_name=normalized.get("model_name"),
        model_version=normalized.get("model_version"),
        is_fallback=normalized.get("is_fallback"),
        model_version_id=model_version_id,
    )
    db.add(evaluation)
    await db.flush()
    await db.refresh(evaluation)
    logger.info("poster_evaluate_saved eval_id=%s score=%s", evaluation.id, evaluation.overall_score)
    return evaluation


@router.get("/{poster_id}/feedback", response_model=List[PosterFeedbackRead])
async def list_feedback(poster_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PosterFeedback).where(PosterFeedback.poster_id == poster_id).order_by(PosterFeedback.created_at.desc())
    )
    return result.scalars().all()


@router.post("/{poster_id}/feedback", response_model=PosterFeedbackRead)
async def add_feedback(
    poster_id: str,
    payload: PosterFeedbackCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_app_api_key),
):
    poster = await db.get(Poster, poster_id)
    if not poster:
        raise HTTPException(status_code=404, detail="Poster not found")

    feedback = PosterFeedback(
        poster_id=poster_id,
        feedback_type=payload.feedback_type,
        feedback_text=payload.feedback_text,
        source=payload.source,
        score=payload.score,
        source_type=payload.source_type,
        source_system=payload.source_system,
        model_name=payload.model_name,
        model_version=payload.model_version,
        is_fallback=payload.is_fallback,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return feedback


@router.post("/{poster_id}/regenerate", response_model=PosterRead)
async def regenerate_poster(
    poster_id: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_app_api_key),
):
    source = await db.get(Poster, poster_id)
    if not source:
        raise HTTPException(status_code=404, detail="Poster not found")

    latest = (await db.execute(
        select(PosterEvaluation)
        .where(PosterEvaluation.poster_id == poster_id)
        .order_by(PosterEvaluation.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    feedback_rows = (await db.execute(
        select(PosterFeedback)
        .where(PosterFeedback.poster_id == poster_id)
        .order_by(PosterFeedback.created_at.desc())
    )).scalars().all()

    weaknesses = []
    suggestions = []
    if latest:
        weaknesses.extend(latest.weaknesses or [])
        suggestions.extend(latest.suggestions or [])
    for item in feedback_rows:
        if item.feedback_text:
            weaknesses.append(item.feedback_text)

    improvement_instruction = derive_improvement_instructions(weaknesses=weaknesses, suggestions=suggestions)
    if not improvement_instruction:
        raise HTTPException(status_code=400, detail="Insufficient feedback for regeneration")

    campaign = await db.get(Campaign, source.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    try:
        if settings.IMAGE_PROVIDER == "local":
            sdxl_model_version_id, sdxl_lora_path = await active_sdxl_runtime(db)
        else:
            sdxl_model_version_id, sdxl_lora_path = None, None
        gen = await poster_generator.generate(
            campaign_name=campaign.name,
            product_name=campaign.product_name,
            description=campaign.description,
            offer=campaign.offer,
            target_audience=campaign.target_audience,
            campaign_goal=campaign.campaign_goal,
            brand_style=campaign.brand_style,
            variation=source.variation_index,
            platform=campaign.preferred_platform or "instagram",
            campaign_id=campaign.id,
            language=(source.metadata_ or {}).get("language"),
            sdxl_model_version_id=sdxl_model_version_id,
            sdxl_lora_path=sdxl_lora_path,
        )
    except Exception as exc:
        logger.error("poster_regenerate_error poster_id=%s error=%s", poster_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Poster regeneration failed: {exc}")

    if not gen or not gen.get("image_url"):
        raise HTTPException(status_code=500, detail="Poster regeneration failed: no image returned")

    next_version = (await db.execute(
        select(Poster.version).where(Poster.campaign_id == source.campaign_id).order_by(Poster.version.desc()).limit(1)
    )).scalar_one_or_none() or 0

    regenerated = Poster(
        campaign_id=source.campaign_id,
        parent_poster_id=source.id,
        image_url=gen["image_url"],
        prompt_used=gen.get("prompt_used"),
        provider=gen.get("provider", source.provider),
        variation_index=source.variation_index,
        version=next_version + 1,
        generation_reason="feedback_regeneration",
        improvement_instruction=improvement_instruction,
        metadata_=gen.get("metadata_", {}),
        model_version_id=gen.get("model_version_id", sdxl_model_version_id),
    )
    db.add(regenerated)
    await db.flush()
    await db.refresh(regenerated)

    try:
        normalized = await poster_evaluator.evaluate(regenerated.image_url)
        model_version_id = None
        if normalized.get("source_type") == "PREDICTED":
            candidate = active_model_version_id(db, "qwen_vl")
            if inspect.isawaitable(candidate):
                candidate = await candidate
            if candidate is not None:
                existing = await db.get(ModelVersion, candidate)
                if existing is not None:
                    model_version_id = candidate

        evaluation = PosterEvaluation(
            poster_id=regenerated.id,
            overall_score=normalized["overall_score"],
            readability_score=normalized["readability_score"],
            layout_score=normalized["layout_score"],
            branding_score=normalized["branding_score"],
            contrast_score=normalized["contrast_score"],
            cta_score=normalized["cta_score"],
            visual_appeal_score=normalized["visual_appeal_score"],
            strengths=normalized.get("strengths") or [],
            weaknesses=normalized.get("weaknesses") or [],
            suggestions=normalized.get("suggestions") or [],
            raw_response=normalized.get("raw_response", {}),
            source_type=normalized.get("source_type", "UNKNOWN"),
            source_system=normalized.get("source_system"),
            model_name=normalized.get("model_name"),
            model_version=normalized.get("model_version"),
            is_fallback=normalized.get("is_fallback"),
            model_version_id=model_version_id,
        )
        db.add(evaluation)
        await db.commit()
        await db.refresh(regenerated)
        logger.info("poster_regenerated poster_id=%s new_version=%s", source.id, regenerated.version)
        return regenerated
    except Exception as exc:
        logger.error("poster_regenerate_eval_error poster_id=%s error=%s", source.id, exc, exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Poster regeneration failed after generation: {exc}")


@router.get("/{poster_id}/evaluations", response_model=List[PosterEvaluationRead])
async def get_evaluations(poster_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PosterEvaluation).where(PosterEvaluation.poster_id == poster_id)
    )
    return result.scalars().all()
