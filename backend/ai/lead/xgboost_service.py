"""
ai/lead/xgboost_service.py
───────────────────────────
XGBoost lead scoring service.

CPU-only. Does not occupy GPU memory.
Auto-trains on synthetic data if no saved model exists.

Features (10):
  clicks, views, time_spent_seconds, prior_purchases, ctr,
  engagement_ratio, location_tier, age_bin, device_enc, platform_enc

Lifecycle:
  load()    → load saved model or train from scratch
  predict() → encode features → DMatrix → predict → score + category
  unload()  → delete booster object, run GC
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np
import xgboost as xgb
from sklearn.preprocessing import LabelEncoder

from ai.base_model import BaseModelService
from ai import memory_manager
from ai.model_registry import get_spec

logger = logging.getLogger(__name__)

_SPEC       = get_spec("xgboost")
_MODEL_PATH = Path(_SPEC.model_id.replace("local://", ""))

# Label encoders for categorical features (fitted on training data, fixed here)
_PLATFORMS  = ["instagram", "facebook", "linkedin", "twitter", "email", "other"]
_DEVICES    = ["mobile", "desktop", "tablet"]
_AGE_GROUPS = ["18-24", "25-34", "35-44", "45-54", "55+"]


class XGBoostService(BaseModelService):

    def __init__(self) -> None:
        super().__init__("xgboost")
        self._booster: Optional[xgb.Booster] = None

    # ── BaseModelService interface ────────────────────────────────────────────

    def _do_load(self) -> None:
        if _MODEL_PATH.exists():
            logger.info("xgboost loading saved model path=%s", _MODEL_PATH)
            self._booster = xgb.Booster()
            self._booster.load_model(str(_MODEL_PATH))
        else:
            logger.info("xgboost no saved model — training on synthetic data")
            self._booster = _train_synthetic()
            _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._booster.save_model(str(_MODEL_PATH))
            logger.info("xgboost model saved path=%s", _MODEL_PATH)

    def _do_unload(self) -> None:
        memory_manager.purge(self._booster)
        self._booster = None

    def health_check(self) -> bool:
        try:
            feat = _encode_features(5, 100, 30, 0, "instagram", "mobile", "25-34", 1)
            dm   = xgb.DMatrix(feat.reshape(1, -1))
            pred = self._booster.predict(dm)
            return 0 <= float(pred[0]) <= 1
        except Exception as exc:
            logger.error("xgboost health_check failed: %s", exc)
            return False

    # ── Public inference API ──────────────────────────────────────────────────

    def predict(
        self,
        clicks:              int,
        views:               int,
        time_spent_seconds:  int,
        prior_purchases:     int,
        source_platform:     str,
        device:              str,
        age_group:           str,
        location_tier:       int,
    ) -> dict:
        """
        Return lead scoring prediction:
          { score: 0-100, purchase_probability: 0-1, category: hot|warm|cold,
            feature_importance: {...} }
        """
        feat = _encode_features(
            clicks, views, time_spent_seconds, prior_purchases,
            source_platform, device, age_group, location_tier,
        )
        dm   = xgb.DMatrix(feat.reshape(1, -1), feature_names=_FEATURE_NAMES)
        prob = float(self._booster.predict(dm)[0])
        prob = max(0.0, min(1.0, prob))
        score = round(prob * 100, 1)

        if score >= 70:
            category = "hot"
        elif score >= 40:
            category = "warm"
        else:
            category = "cold"

        importance = self._booster.get_score(importance_type="gain")

        return {
            "score":                score,
            "purchase_probability": round(prob, 4),
            "category":             category,
            "feature_importance":   importance,
        }


# ── Feature engineering ────────────────────────────────────────────────────────

_FEATURE_NAMES = [
    "clicks", "views", "time_spent", "prior_purchases",
    "ctr", "engagement_ratio", "location_tier",
    "age_bin", "device_enc", "platform_enc",
]


def _encode_features(
    clicks: int, views: int, time_spent: int, prior_purchases: int,
    platform: str, device: str, age_group: str, location_tier: int,
) -> np.ndarray:
    ctr              = clicks / max(views, 1)
    engagement_ratio = (clicks + time_spent / 60) / max(views, 1)
    age_bin          = _AGE_GROUPS.index(age_group) if age_group in _AGE_GROUPS else 1
    device_enc       = _DEVICES.index(device)       if device    in _DEVICES    else 0
    platform_enc     = _PLATFORMS.index(platform)   if platform  in _PLATFORMS  else 5

    return np.array([
        clicks, views, time_spent, prior_purchases,
        ctr, engagement_ratio, location_tier,
        age_bin, device_enc, platform_enc,
    ], dtype=np.float32)


# ── Synthetic training ─────────────────────────────────────────────────────────

def _train_synthetic(n: int = 2000) -> xgb.Booster:
    rng = np.random.default_rng(42)

    clicks     = rng.integers(0, 100, n)
    views      = rng.integers(50, 5000, n)
    time_spent = rng.integers(0, 600, n)
    purchases  = rng.integers(0, 10, n)
    platform   = rng.integers(0, len(_PLATFORMS), n)
    device     = rng.integers(0, len(_DEVICES), n)
    age_bin    = rng.integers(0, len(_AGE_GROUPS), n)
    location   = rng.integers(1, 4, n)
    ctr        = clicks / np.maximum(views, 1)
    eng_ratio  = (clicks + time_spent / 60) / np.maximum(views, 1)

    X = np.column_stack([
        clicks, views, time_spent, purchases,
        ctr, eng_ratio, location, age_bin, device, platform,
    ]).astype(np.float32)

    # Label: high engagement + purchases → hot lead
    y = ((ctr > 0.05) & (time_spent > 120) | (purchases > 2)).astype(np.float32)

    dtrain = xgb.DMatrix(X, label=y, feature_names=_FEATURE_NAMES)
    params = {
        "objective":  "binary:logistic",
        "max_depth":  5,
        "eta":        0.1,
        "subsample":  0.8,
        "eval_metric":"logloss",
        "verbosity":  0,
        "nthread":    os.cpu_count() or 4,
    }
    booster = xgb.train(params, dtrain, num_boost_round=120)
    logger.info("xgboost synthetic training complete n=%d", n)
    return booster
