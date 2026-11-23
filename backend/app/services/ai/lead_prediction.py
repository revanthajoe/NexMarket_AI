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
            result = await inference_manager.predict_lead(
                clicks, views, time_spent_seconds, prior_purchases,
                source_platform, device, age_group, location_tier,
            )
            result.update({
                "source_type": "PREDICTED",
                "source_system": "xgboost",
                "model_name": "XGBoost",
                "model_version": "lead_model.json",
                "is_fallback": False,
            })
            return result
        except Exception as exc:
            logger.warning("lead_predict_unavailable error=%s", exc)
            raise RuntimeError("UNAVAILABLE: trained XGBoost lead model is unavailable") from exc


def _heuristic(clicks, views, time_spent, purchases) -> dict:
    ctr    = clicks / max(views, 1)
    score  = min(100.0, round((ctr * 200 + purchases * 10 + time_spent / 30) / 3, 1))
    cat    = "hot" if score >= 70 else "warm" if score >= 40 else "cold"
    return {
        "score": score,
        "purchase_probability": score / 100,
        "category": cat,
        "feature_importance": {},
        "source_type": "FALLBACK",
        "source_system": "heuristic",
        "model_name": None,
        "model_version": None,
        "is_fallback": True,
    }


lead_prediction_service = LeadPredictionService()
