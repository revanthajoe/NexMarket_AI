"""
app/services/ai/lstm_forecast.py
──────────────────────────────────
Adapter: routes forecasting to InferenceManager → LSTMService.
Handles history normalization from DB analytics records.
"""
from __future__ import annotations

import logging
import math
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

        eligible_rows = [row for row in analytics_rows if row.get("source_type") == "ACTUAL"]
        if len(eligible_rows) < 14:
            raise ValueError(
                "INSUFFICIENT_DATA: forecast requires at least 14 ACTUAL analytics observations"
            )
        _validate_history(eligible_rows)
        history = _rows_to_array(eligible_rows)

        try:
            from ai.inference_manager import inference_manager
            result = await inference_manager.forecast_engagement(history, horizon_days)
            result["campaign_id"] = campaign_id
            result.update({
                "source_type": "FORECAST",
                "history_source": "ACTUAL",
                "source_system": "lstm",
                "is_fallback": False,
            })
            return result
        except Exception as exc:
            logger.error("lstm_forecast_unavailable error=%s", exc, exc_info=True)
            raise ValueError("UNAVAILABLE: LSTM forecast model is unavailable") from exc


def _rows_to_array(rows: list) -> np.ndarray:
    """Convert list of analytics row dicts to (T, 5) ndarray."""
    if not rows:
        return np.empty((0, 5), dtype=np.float32)

    cols = ["likes", "shares", "comments", "ctr", "reach"]
    arr  = np.array(
        [[row.get(c, 0) for c in cols] for row in rows],
        dtype=np.float32,
    )
    return arr


def _validate_history(rows: list[dict]) -> None:
    previous_timestamp = None
    for row in rows:
        timestamp = row.get("event_date")
        if timestamp is not None:
            if previous_timestamp is not None and timestamp <= previous_timestamp:
                raise ValueError("INVALID_HISTORY: analytics observations must be chronological and unique")
            previous_timestamp = timestamp
        for metric in ("likes", "shares", "comments", "ctr", "reach"):
            value = row.get(metric)
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"INVALID_HISTORY: {metric} must be numeric")


lstm_forecast_service = LSTMForecastService()
