"""
app/services/ai/lstm_forecast.py
──────────────────────────────────
Adapter: routes forecasting to InferenceManager → LSTMService.
Handles history normalization from DB analytics records.
"""
from __future__ import annotations

import logging
from typing import List

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)


class LSTMForecastService:

    async def forecast(
        self,
        campaign_id: str,
        analytics_rows: List[dict],
        horizon_days: int = 7,
    ) -> dict:
        """
        analytics_rows: list of dicts with keys:
          likes, shares, comments, ctr, reach
        """
        logger.info("lstm_forecast campaign=%s horizon=%d rows=%d",
                    campaign_id, horizon_days, len(analytics_rows))

        history = _rows_to_array(analytics_rows)

        try:
            from ai.inference_manager import inference_manager
            result = await inference_manager.forecast_engagement(history, horizon_days)
            result["campaign_id"] = campaign_id
            return result
        except Exception as exc:
            logger.warning("lstm_forecast_fallback error=%s", exc)
            return _linear_fallback(history, horizon_days, campaign_id)


def _rows_to_array(rows: list) -> np.ndarray:
    """Convert list of analytics row dicts to (T, 5) ndarray."""
    if not rows:
        # Return 14 days of random demo data
        rng = np.random.default_rng(0)
        return rng.uniform(50, 500, (14, 5)).astype(np.float32)

    cols = ["likes", "shares", "comments", "ctr", "reach"]
    arr  = np.array(
        [[row.get(c, 0) for c in cols] for row in rows],
        dtype=np.float32,
    )
    return arr


def _linear_fallback(history: np.ndarray, horizon: int, campaign_id: str) -> dict:
    """Simple linear extrapolation fallback."""
    if len(history) >= 2:
        trend = history[-1] - history[-2]
    else:
        trend = np.zeros(5)
    last = history[-1] if len(history) > 0 else np.zeros(5)

    preds = np.array([last + trend * (i + 1) for i in range(horizon)])
    preds = np.clip(preds, 0, None)
    preds[:, 3] = np.clip(preds[:, 3], 0, 1)

    return {
        "campaign_id":        campaign_id,
        "predicted_likes":    preds[:, 0].tolist(),
        "predicted_shares":   preds[:, 1].tolist(),
        "predicted_comments": preds[:, 2].tolist(),
        "predicted_ctr":      preds[:, 3].tolist(),
        "predicted_reach":    preds[:, 4].tolist(),
        "confidence_intervals": {},
        "model_version":      "linear-fallback",
    }


lstm_forecast_service = LSTMForecastService()
