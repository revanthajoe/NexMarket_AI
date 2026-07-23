"""
Module 5: Lead Prediction Service (XGBoost)
Predicts lead score (0-100), purchase probability, and hot/warm/cold category.
Trains a synthetic model on first run if no saved model exists.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import numpy as np

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

MODEL_PATH = Path(settings.XGBOOST_MODEL_PATH)

# Feature order — must be consistent across train/inference
FEATURES = [
    "clicks", "views", "time_spent_seconds", "prior_purchases",
    "click_through_rate", "engagement_ratio", "location_tier",
    "age_group_encoded", "device_encoded", "platform_encoded",
]

# Encodings
_DEVICE_MAP = {"desktop": 0, "mobile": 1, "tablet": 2}
_PLATFORM_MAP = {"instagram": 0, "facebook": 1, "linkedin": 2, "twitter": 3, "unknown": 4}
_AGE_MAP = {
    "18-24": 0, "25-34": 1, "35-44": 2, "45-54": 3, "55+": 4
}

_model = None


def _encode_features(data: dict) -> list[float]:
    clicks = float(data.get("clicks", 0))
    views = max(float(data.get("views", 1)), 1)
    time_spent = float(data.get("time_spent_seconds", 0))
    prior = float(data.get("prior_purchases", 0))
    ctr = clicks / views
    engagement = (clicks + prior * 3) / views
    location = float(data.get("location_tier", 1))
    age = float(_AGE_MAP.get(data.get("age_group", "25-34"), 1))
    device = float(_DEVICE_MAP.get(data.get("device", "desktop"), 0))
    platform = float(_PLATFORM_MAP.get(data.get("source_platform", "unknown"), 4))
    return [clicks, views, time_spent, prior, ctr, engagement, location, age, device, platform]


def _generate_synthetic_data(n: int = 1000):
    """Generate synthetic training data for demo/bootstrap."""
    rng = np.random.RandomState(42)
    X = np.column_stack([
        rng.randint(0, 100, n),          # clicks
        rng.randint(100, 5000, n),        # views
        rng.uniform(5, 600, n),           # time_spent_seconds
        rng.randint(0, 10, n),            # prior_purchases
        rng.uniform(0.001, 0.3, n),       # ctr
        rng.uniform(0.001, 0.5, n),       # engagement_ratio
        rng.randint(1, 4, n),             # location_tier
        rng.randint(0, 5, n),             # age_group_encoded
        rng.randint(0, 3, n),             # device_encoded
        rng.randint(0, 5, n),             # platform_encoded
    ]).astype(np.float32)
    # Score is correlated to engagement signals
    y = (
        0.3 * (X[:, 0] / 100)
        + 0.2 * (X[:, 3] / 10)
        + 0.3 * X[:, 4]
        + 0.2 * X[:, 5]
    )
    y = np.clip(y, 0, 1)
    return X, y


def _load_or_train_model():
    global _model
    if _model is not None:
        return _model

    try:
        import xgboost as xgb

        if MODEL_PATH.exists():
            booster = xgb.Booster()
            booster.load_model(str(MODEL_PATH))
            logger.info("xgboost_model_loaded", path=str(MODEL_PATH))
            _model = booster
        else:
            logger.info("xgboost_training_synthetic")
            X, y = _generate_synthetic_data(2000)
            dtrain = xgb.DMatrix(X, label=y, feature_names=FEATURES)
            params = {
                "objective": "reg:squarederror",
                "max_depth": 5,
                "eta": 0.1,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "eval_metric": "rmse",
            }
            booster = xgb.train(params, dtrain, num_boost_round=100, verbose_eval=False)
            MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            booster.save_model(str(MODEL_PATH))
            logger.info("xgboost_model_saved", path=str(MODEL_PATH))
            _model = booster
        return _model
    except ImportError:
        logger.warning("xgboost_not_installed")
        return None


class LeadPredictionService:
    def predict(self, data: dict) -> dict:
        features = _encode_features(data)
        model = _load_or_train_model()

        if model is not None:
            try:
                import xgboost as xgb
                dmat = xgb.DMatrix([features], feature_names=FEATURES)
                raw_score = float(model.predict(dmat)[0])
                score = round(float(np.clip(raw_score, 0, 1)) * 100, 2)
                prob = round(float(np.clip(raw_score, 0, 1)), 4)
                importance = self._get_importance(model)
            except Exception as exc:
                logger.warning("xgb_predict_failed", error=str(exc))
                score, prob, importance = self._rule_based(features)
        else:
            score, prob, importance = self._rule_based(features)

        category = "hot" if score >= 70 else "warm" if score >= 40 else "cold"
        return {
            "score": score,
            "purchase_probability": prob,
            "category": category,
            "feature_importance": importance,
        }

    def _rule_based(self, features: list[float]):
        """Heuristic fallback when XGBoost not available."""
        clicks, views, time_spent, prior, ctr, engagement, *_ = features
        score = min(
            100,
            clicks * 0.5 + prior * 5 + ctr * 30 + engagement * 20 + min(time_spent / 60, 5),
        )
        prob = round(score / 100, 4)
        importance = {f: round(1 / len(FEATURES), 4) for f in FEATURES}
        return round(score, 2), prob, importance

    def _get_importance(self, model) -> dict:
        try:
            scores = model.get_score(importance_type="gain")
            total = max(sum(scores.values()), 1)
            return {k: round(v / total, 4) for k, v in scores.items()}
        except Exception:
            return {}


lead_prediction_service = LeadPredictionService()
