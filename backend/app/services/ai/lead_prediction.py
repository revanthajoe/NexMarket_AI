"""
app/services/ai/lead_prediction.py
────────────────────────────────────
Adapter: routes lead scoring to InferenceManager → XGBoostService.
"""
from __future__ import annotations

import logging

from app.core.logging import get_logger

logger = get_logger(__name__)


class LeadPredictionService:

    async def predict(
        self,
        clicks: int,
        views: int,
        time_spent_seconds: int,
        prior_purchases: int,
        source_platform: str,
        device: str,
        age_group: str,
        location_tier: int,
        campaign_id: str = None,
        lead_identifier: str = None,
    ) -> dict:
        logger.info("lead_predict platform=%s device=%s", source_platform, device)

        try:
            from ai.inference_manager import inference_manager
            return await inference_manager.predict_lead(
                clicks, views, time_spent_seconds, prior_purchases,
                source_platform, device, age_group, location_tier,
            )
        except Exception as exc:
            logger.warning("lead_predict_fallback error=%s", exc)
            return _heuristic(clicks, views, time_spent_seconds, prior_purchases)


def _heuristic(clicks, views, time_spent, purchases) -> dict:
    ctr    = clicks / max(views, 1)
    score  = min(100.0, round((ctr * 200 + purchases * 10 + time_spent / 30) / 3, 1))
    cat    = "hot" if score >= 70 else "warm" if score >= 40 else "cold"
    return {"score": score, "purchase_probability": score / 100, "category": cat, "feature_importance": {}}


lead_prediction_service = LeadPredictionService()
