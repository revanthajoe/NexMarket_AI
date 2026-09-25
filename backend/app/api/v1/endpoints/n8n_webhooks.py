"""
n8n Webhook endpoints — n8n calls these to trigger backend operations.
Backend does ALL AI logic; n8n is purely the orchestrator.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import AdCopy, Campaign, Poster, SocialPost
from app.schemas.schemas import N8nTriggerCampaign, N8nWebhookResponse
from app.services.ai.ad_generator import ad_copy_generator
from app.services.ai.lead_prediction import lead_prediction_service
from app.services.ai.lstm_forecast import lstm_forecast_service
from app.services.ai.poster_evaluator import poster_evaluator
from app.services.ai.poster_generator import poster_generator
from app.services.ai.sentiment import sentiment_service
from app.services.optimization.optimizer import campaign_optimizer
from app.services.posting.posting_service import social_posting_service
from app.services.model_metadata import active_model_version_id

router = APIRouter(prefix="/n8n", tags=["n8n Webhooks"])


@router.post("/trigger/campaign", response_model=N8nWebhookResponse)
async def n8n_trigger_campaign(
    payload: N8nTriggerCampaign,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Main entry point called by n8n to kick off the full campaign pipeline.
    Runs all steps async in a background task; each step is idempotent
    (skips if results already exist) to prevent duplicate DB rows.
    """
    campaign = await db.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign.status = "generating"
    # Commit before scheduling: the background task writes the final status on
    # its own session, and this request's post-yield commit would otherwise land
    # afterwards and clobber it back to "generating".
    await db.commit()

    async def run_pipeline(campaign_id: str, steps: list, platforms: list | None):
        import logging
        from app.db.session import AsyncSessionLocal

        log = logging.getLogger(__name__)

        # Use a completely independent session — NullPool guarantees no
        # connection sharing with the request that spawned this task. The SQLite
        # pragmas are applied by the engine's connect listener, so this session
        # gets WAL and the 30s busy timeout without asking.
        async with AsyncSessionLocal() as bg_db:
            try:
                c = await bg_db.get(Campaign, campaign_id)
                if not c:
                    log.error("pipeline_abort campaign_id=%s not found", campaign_id)
                    return

                results: dict = {}

                # ── Poster ────────────────────────────────────────────────
                if "poster" in steps:
                    # Idempotency: skip if poster already exists
                    existing_posters = (await bg_db.execute(
                        select(Poster).where(Poster.campaign_id == campaign_id).limit(1)
                    )).scalars().all()

                    if existing_posters:
                        log.info("pipeline_skip_poster campaign_id=%s already has posters", campaign_id)
                        results["poster_id"] = existing_posters[0].id
                    else:
                        try:
                            gen = await poster_generator.generate(
                                campaign_name=c.name,
                                product_name=c.product_name,
                                description=c.description,
                                offer=c.offer,
                                target_audience=c.target_audience,
                                campaign_goal=c.campaign_goal,
                                brand_style=c.brand_style,
                                platform=c.preferred_platform or "instagram",
                                campaign_id=c.id,
                            )
                            poster = Poster(campaign_id=c.id, **gen)
                            bg_db.add(poster)
                            # Commit, not flush: a flush opens the single SQLite
                            # write transaction and holds it through every
                            # remaining step — minutes of GPU time during which
                            # no other request can write. One short transaction
                            # per step instead, same convention as the poster
                            # endpoint's commit-per-variation.
                            await bg_db.commit()
                            await bg_db.refresh(poster)
                            results["poster_id"] = poster.id
                            log.info("pipeline_poster_done id=%s", poster.id)
                        except Exception as exc:
                            log.error("pipeline_poster_failed: %s", exc, exc_info=True)
                            raise

                    # ── Evaluate ─────────────────────────────────────────
                    if "evaluate" in steps and results.get("poster_id"):
                        try:
                            poster_obj = await bg_db.get(Poster, results["poster_id"])
                            if poster_obj:
                                # Two stacked bugs lived here:
                                #  1. evaluate() already returns the normalized,
                                #     schema-ready dict. Calling normalize() on
                                #     it again read sub-scores from a nested
                                #     "dimensions" key it no longer has, zeroing
                                #     every dimension.
                                #  2. normalize() also returns "fallback", which
                                #     is not a column, so PosterEvaluation(**norm)
                                #     raised TypeError — swallowed by the except
                                #     below, meaning this step never actually
                                #     persisted an evaluation at all.
                                # Build from the model's own columns instead.
                                from app.models.models import PosterEvaluation
                                norm = await poster_evaluator.evaluate(poster_obj.image_url)
                                columns = {c.name for c in PosterEvaluation.__table__.columns}
                                ev = PosterEvaluation(
                                    poster_id=poster_obj.id,
                                    **{k: v for k, v in norm.items() if k in columns},
                                )
                                if norm.get("source_type") == "PREDICTED":
                                    ev.model_version_id = await active_model_version_id(bg_db, "qwen_vl")
                                bg_db.add(ev)
                                await bg_db.commit()
                                log.info("pipeline_evaluate_done poster_id=%s", poster_obj.id)
                        except Exception as exc:
                            log.error("pipeline_evaluate_failed: %s", exc, exc_info=True)

                # ── Ad Copy ───────────────────────────────────────────────
                if "adcopy" in steps:
                    # Idempotency: skip if ad copies already exist
                    existing_copies = (await bg_db.execute(
                        select(AdCopy).where(AdCopy.campaign_id == campaign_id).limit(1)
                    )).scalars().all()

                    if existing_copies:
                        log.info("pipeline_skip_adcopy campaign_id=%s already has copies", campaign_id)
                    else:
                        try:
                            platforms = (
                                [c.preferred_platform]
                                if c.preferred_platform != "all"
                                else ["instagram", "facebook", "telegram", "whatsapp"]
                            )
                            from app.services.ai.brand_kit import get_brand_kit
                            copies = await ad_copy_generator.generate(
                                c.product_name, c.description, c.offer,
                                c.target_audience, c.campaign_goal,
                                platforms=platforms,
                                language=get_brand_kit(c.id).language,
                            )
                            for platform, data in copies.items():
                                is_fallback = data.get("fallback", False)
                                ad = AdCopy(
                                    campaign_id=c.id,
                                    platform=platform,
                                    headline=data.get("headline"),
                                    body=data.get("body", ""),
                                    cta_variants=data.get("cta_variants"),
                                    hashtags=data.get("hashtags"),
                                    fallback=is_fallback,
                                    source_type="FALLBACK" if is_fallback else "PREDICTED",
                                    source_system="template" if is_fallback else "local_qwen",
                                    model_name=None if is_fallback else "Qwen/Qwen2.5-3B-Instruct",
                                    model_version_id=None if is_fallback else await active_model_version_id(bg_db, "qwen_llm"),
                                )
                                bg_db.add(ad)
                            await bg_db.commit()
                            log.info("pipeline_adcopy_done count=%d", len(copies))
                        except Exception as exc:
                            log.error("pipeline_adcopy_failed: %s", exc, exc_info=True)
                            raise

                # ── Optimize ──────────────────────────────────────────────
                if "optimize" in steps:
                    from app.models.models import OptimizationResult
                    existing_opt = (await bg_db.execute(
                        select(OptimizationResult)
                        .where(OptimizationResult.campaign_id == campaign_id)
                        .limit(1)
                    )).scalars().all()

                    if existing_opt:
                        log.info("pipeline_skip_optimize campaign_id=%s already optimized", campaign_id)
                        results["optimization"] = {
                            "recommended_platform": existing_opt[0].recommended_platform,
                            "recommended_time": existing_opt[0].recommended_time,
                            "recommended_budget": existing_opt[0].recommended_budget,
                            "confidence": existing_opt[0].confidence,
                            "reasoning": existing_opt[0].reasoning,
                            "platform_scores": existing_opt[0].platform_scores,
                        }
                    else:
                        try:
                            opt = await campaign_optimizer.optimize(
                                campaign_goal=c.campaign_goal,
                                target_audience=c.target_audience,
                                budget=c.budget,
                            )
                            results["optimization"] = opt
                            
                            opt_record = OptimizationResult(
                                campaign_id=campaign_id,
                                recommended_platform=opt.get("recommended_platform", c.preferred_platform or "instagram"),
                                recommended_time=opt.get("recommended_time"),
                                recommended_budget=opt.get("recommended_budget"),
                                confidence=opt.get("confidence", 0.0),
                                reasoning=opt.get("reasoning"),
                                platform_scores=opt.get("platform_scores"),
                                source_type="RECOMMENDATION",
                                algorithm="Thompson Sampling",
                                policy_version=opt.get("policy_version"),
                                reward_source=opt.get("reward_source", "UNKNOWN"),
                                analytics_reference=f"campaign:{campaign_id}:events",
                            )
                            bg_db.add(opt_record)
                            await bg_db.commit()

                            log.info("pipeline_optimize_done platform=%s", opt.get("recommended_platform"))
                        except Exception as exc:
                            log.error("pipeline_optimize_failed: %s", exc, exc_info=True)
                            raise

                # ── Post ──────────────────────────────────────────────────
                # Publishes to every platform in `platforms` independently —
                # see SocialPostingService.publish_platforms(). This used to
                # publish to exactly one platform (the optimizer's pick, or
                # preferred_platform) and `raise` on failure, which propagated
                # to the outer handler and marked the ENTIRE campaign "failed"
                # even when poster/adcopy/evaluate/forecast/optimize had all
                # succeeded. A platform failing now lives on its own
                # SocialPost.status row, exactly like the standalone
                # /posting/campaign/{id}/publish endpoint — this step must
                # never raise for a publish failure.
                if "post" in steps:
                    target_platforms = platforms or (
                        [results["optimization"]["recommended_platform"]]
                        if results.get("optimization", {}).get("recommended_platform")
                        else [c.preferred_platform]
                    )
                    posts = await social_posting_service.create_posts_for_platforms(
                        bg_db, c.id, target_platforms,
                        ad_copy_id=None, poster_id=results.get("poster_id"),
                    )

                    text_content = f"{c.product_name} — {c.offer}"
                    image_url = None
                    if results.get("poster_id"):
                        poster_obj = await bg_db.get(Poster, results["poster_id"])
                        image_url = poster_obj.image_url if poster_obj else None

                    await social_posting_service.publish_platforms(bg_db, posts, text_content, image_url)
                    log.info("pipeline_post_done platforms=%s", target_platforms)

                # ── Sentiment ─────────────────────────────────────────────
                # Analyse a composite text assembled from the campaign's own
                # copy so even a brand-new campaign (no user reviews yet) gets
                # a meaningful sentiment record.  Idempotent: skipped when a
                # record already exists for this campaign.
                if "sentiment" in steps:
                    from app.models.models import SentimentResult
                    existing_sentiment = (await bg_db.execute(
                        select(SentimentResult)
                        .where(SentimentResult.campaign_id == campaign_id)
                        .limit(1)
                    )).scalars().all()

                    if existing_sentiment:
                        log.info("pipeline_skip_sentiment campaign_id=%s already analysed", campaign_id)
                    else:
                        try:
                            # Build a representative corpus from the campaign fields
                            # so the model has real signal even without user reviews.
                            texts = [
                                t for t in [
                                    c.name,
                                    c.description,
                                    c.offer,
                                    f"{c.product_name} for {c.target_audience}",
                                ] if t
                            ] or [c.name or "campaign"]

                            analysis = await sentiment_service.analyze(texts, campaign_id)
                            for r in analysis["results"]:
                                record = SentimentResult(
                                    campaign_id=campaign_id,
                                    text=r["text"],
                                    label=r["label"],
                                    positive_score=r["positive_score"],
                                    negative_score=r["negative_score"],
                                    neutral_score=r.get("neutral_score", 0.0),
                                    confidence=r["confidence"],
                                    model_used=r["model_used"],
                                )
                                bg_db.add(record)
                            await bg_db.commit()
                            log.info(
                                "pipeline_sentiment_done campaign_id=%s texts=%d summary=%s",
                                campaign_id, len(texts), analysis["summary"],
                            )
                        except Exception as exc:
                            log.error("pipeline_sentiment_failed: %s", exc, exc_info=True)

                # ── Lead Prediction ────────────────────────────────────────
                # Generates a representative lead score derived from the
                # campaign's targeting settings.  Idempotent: skipped when a
                # LeadScore row already exists for this campaign.
                if "lead_prediction" in steps:
                    from app.models.models import LeadScore
                    existing_leads = (await bg_db.execute(
                        select(LeadScore)
                        .where(LeadScore.campaign_id == campaign_id)
                        .limit(1)
                    )).scalars().all()

                    if existing_leads:
                        log.info("pipeline_skip_lead_prediction campaign_id=%s already scored", campaign_id)
                    else:
                        try:
                            # Map campaign fields to lead-predictor feature space.
                            # These are illustrative baseline values; real leads
                            # come from analytics events via the /leads/predict
                            # endpoint once the campaign is live.
                            platform = c.preferred_platform or "instagram"
                            result = await lead_prediction_service.predict(
                                clicks=10,
                                views=200,
                                time_spent_seconds=90,
                                prior_purchases=1,
                                source_platform=platform,
                                device="mobile",
                                age_group="25-34",
                                location_tier=1,
                                campaign_id=campaign_id,
                                lead_identifier="pipeline_baseline",
                            )
                            lead_record = LeadScore(
                                campaign_id=campaign_id,
                                lead_identifier="pipeline_baseline",
                                score=result["score"],
                                purchase_probability=result["purchase_probability"],
                                category=result["category"],
                                feature_importance=result.get("feature_importance", {}),
                                input_features={
                                    "clicks": 10, "views": 200,
                                    "time_spent_seconds": 90,
                                    "prior_purchases": 1,
                                    "source_platform": platform,
                                    "device": "mobile",
                                    "age_group": "25-34",
                                    "location_tier": 1,
                                },
                                source_type=result.get("source_type", "UNKNOWN"),
                                source_system=result.get("source_system"),
                                model_name=result.get("model_name"),
                                model_version=result.get("model_version"),
                                is_fallback=result.get("is_fallback"),
                                model_version_id=(
                                    await active_model_version_id(bg_db, "xgboost")
                                    if result.get("source_type") == "PREDICTED" else None
                                ),
                            )
                            bg_db.add(lead_record)
                            await bg_db.commit()
                            log.info(
                                "pipeline_lead_prediction_done campaign_id=%s score=%.1f category=%s",
                                campaign_id, result["score"], result["category"],
                            )
                        except Exception as exc:
                            log.error("pipeline_lead_prediction_failed: %s", exc, exc_info=True)

                # ── Forecast ───────────────────────────────────────────────
                # Runs the LSTM engagement forecast.  Uses any AnalyticsEvent
                # rows already present (may be empty for a brand-new campaign;
                # the LSTM service handles that gracefully with synthetic
                # baselines).  Idempotent: skipped when a forecast already
                # exists for this campaign.
                if "forecast" in steps:
                    from app.models.models import AnalyticsEvent, EngagementForecast
                    existing_forecast = (await bg_db.execute(
                        select(EngagementForecast)
                        .where(EngagementForecast.campaign_id == campaign_id)
                        .limit(1)
                    )).scalars().all()

                    if existing_forecast:
                        log.info("pipeline_skip_forecast campaign_id=%s already forecasted", campaign_id)
                    else:
                        try:
                            events_r = await bg_db.execute(
                                select(AnalyticsEvent)
                                .where(AnalyticsEvent.campaign_id == campaign_id)
                                .where(AnalyticsEvent.source_type == "ACTUAL")
                                .order_by(AnalyticsEvent.event_date.asc())
                            )
                            history = [
                                {
                                    "likes": e.likes,
                                    "shares": e.shares,
                                    "comments": e.comments,
                                    "ctr": e.ctr,
                                    "reach": e.reach,
                                    "source_type": e.source_type,
                                    "event_date": e.event_date,
                                }
                                for e in events_r.scalars().all()
                            ]
                            forecast_data = await lstm_forecast_service.forecast(
                                campaign_id=campaign_id,
                                analytics_rows=history,
                                horizon_days=7,
                            )
                            forecast_record = EngagementForecast(
                                campaign_id=campaign_id,
                                forecast_horizon_days=7,
                                predicted_likes=forecast_data.get("predicted_likes"),
                                predicted_shares=forecast_data.get("predicted_shares"),
                                predicted_comments=forecast_data.get("predicted_comments"),
                                predicted_ctr=forecast_data.get("predicted_ctr"),
                                predicted_reach=forecast_data.get("predicted_reach"),
                                confidence_intervals=forecast_data.get("confidence_intervals"),
                                model_version=forecast_data.get("model_version", "UNKNOWN"),
                                source_type=forecast_data.get("source_type", "UNKNOWN"),
                                history_source=forecast_data.get("history_source", "UNKNOWN"),
                                source_reference=f"analytics_events:{len(history)}",
                                is_fallback=forecast_data.get("is_fallback"),
                                model_version_id=(
                                    await active_model_version_id(bg_db, "lstm")
                                    if forecast_data.get("source_type") == "FORECAST" else None
                                ),
                            )
                            bg_db.add(forecast_record)
                            await bg_db.commit()
                            log.info(
                                "pipeline_forecast_done campaign_id=%s horizon=7",
                                campaign_id,
                            )
                        except Exception as exc:
                            log.error("pipeline_forecast_failed: %s", exc, exc_info=True)

                # ── Finalise ──────────────────────────────────────────────
                c.status = "posted" if "post" in steps else "ready"
                await bg_db.commit()
                log.info("pipeline_complete campaign_id=%s status=%s", campaign_id, c.status)

            except Exception as exc:
                log.error("pipeline_unhandled_error campaign_id=%s: %s", campaign_id, exc, exc_info=True)
                # Rolls back only the step that failed — earlier steps committed
                # on their own. That is deliberate: a poster that cost minutes of
                # GPU time is kept even if ad copy later fails, and the campaign
                # is still marked "failed" below so the UI stays accurate.
                await bg_db.rollback()
                # Mark campaign as failed so the UI can reflect it
                async with AsyncSessionLocal() as err_db:
                    failed_c = await err_db.get(Campaign, campaign_id)
                    if failed_c:
                        failed_c.status = "failed"
                        await err_db.commit()

    background_tasks.add_task(run_pipeline, payload.campaign_id, payload.steps, payload.platforms)
    return N8nWebhookResponse(
        status="accepted",
        message=f"Campaign pipeline started for {payload.campaign_id}",
        data={"steps": payload.steps},
    )


# A pipeline that's still "generating" after this long didn't crash cleanly —
# it was orphaned (e.g. the dev server restarted mid-task, which silently
# kills the BackgroundTasks coroutine before it can mark the campaign
# "failed"). Without this the frontend polls forever with nothing to make it
# stop, since nothing else ever updates the row.
STALE_GENERATING_TIMEOUT_SECONDS = 20 * 60


@router.get("/status/{campaign_id}", response_model=Dict[str, Any])
async def n8n_campaign_status(campaign_id: str, db: AsyncSession = Depends(get_db)):
    """n8n polls this to check pipeline progress."""
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status == "generating" and campaign.updated_at:
        age = (datetime.utcnow() - campaign.updated_at).total_seconds()
        if age > STALE_GENERATING_TIMEOUT_SECONDS:
            campaign.status = "failed"
            await db.commit()
            await db.refresh(campaign)

    posts_r = await db.execute(
        select(SocialPost).where(SocialPost.campaign_id == campaign_id)
    )
    posts = posts_r.scalars().all()

    return {
        "campaign_id": campaign_id,
        "status": campaign.status,
        "posts": [
            {"platform": p.platform, "status": p.status, "is_mock": p.is_mock}
            for p in posts
        ],
    }


@router.post("/analytics/ingest")
async def n8n_ingest_analytics(
    data: Dict[str, Any], db: AsyncSession = Depends(get_db)
):
    """n8n calls this to push analytics events from platform APIs."""
    from app.models.models import AnalyticsEvent
    from datetime import datetime

    campaign_id = data.get("campaign_id")
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    source_type = data.get("source_type", "UNKNOWN")
    if source_type not in {"ACTUAL", "SIMULATED", "UNKNOWN"}:
        raise HTTPException(status_code=422, detail="source_type must be ACTUAL, SIMULATED, or UNKNOWN")

    event = AnalyticsEvent(
        campaign_id=campaign_id,
        platform=data.get("platform", "unknown"),
        event_date=datetime.fromisoformat(data.get("event_date", datetime.utcnow().isoformat())),
        impressions=data.get("impressions", 0),
        clicks=data.get("clicks", 0),
        likes=data.get("likes", 0),
        shares=data.get("shares", 0),
        comments=data.get("comments", 0),
        reach=data.get("reach", 0),
        ctr=data.get("ctr", 0.0),
        spend=data.get("spend", 0.0),
        is_mock=source_type == "SIMULATED",
        source_type=source_type,
        source_system=data.get("source_system", "n8n"),
        source_reference=data.get("source_reference"),
        synced_at=datetime.utcnow(),
    )
    db.add(event)
    return {"status": "ok"}


@router.post("/report/trigger")
async def n8n_trigger_report(
    data: Dict[str, Any], db: AsyncSession = Depends(get_db)
):
    """n8n triggers a report generation."""
    campaign_id = data.get("campaign_id")
    return {
        "status": "ok",
        "message": f"Report generation triggered for {campaign_id}",
        "report_url": f"/api/v1/analytics/{campaign_id}/report",
    }
