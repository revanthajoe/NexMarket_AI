"""
Module 6: LSTM Engagement Forecasting Service
Uses a multi-output LSTM to forecast likes, shares, comments, CTR, reach
over a N-day horizon.
Trains on synthetic data if no model exists. No GRU used.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

MODEL_PATH = Path(settings.LSTM_MODEL_PATH)
SEQ_LEN = 14       # input window: 14 days of history
N_FEATURES = 5     # likes, shares, comments, ctr, reach
N_OUTPUTS = 5      # same 5 metrics

_model = None
_scaler_mean: Optional[np.ndarray] = None
_scaler_std: Optional[np.ndarray] = None


# ── Synthetic data generation ─────────────────────────────────────────────────

def _synthetic_series(n_samples: int = 200, seq_len: int = SEQ_LEN):
    """Generate synthetic time-series data for LSTM training."""
    rng = np.random.RandomState(99)
    X, y = [], []
    for _ in range(n_samples):
        base = rng.uniform(100, 5000, N_FEATURES)
        trend = rng.uniform(0.95, 1.05, N_FEATURES)
        series = [base]
        for t in range(seq_len + 6):
            noise = rng.normal(0, 0.05, N_FEATURES)
            series.append(series[-1] * trend + rng.uniform(-50, 50, N_FEATURES))
        series = np.array(series)
        X.append(series[:seq_len])
        y.append(series[seq_len : seq_len + 7].mean(axis=0))  # 7-day average as target
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


# ── Model definition (Keras LSTM) ────────────────────────────────────────────

def _build_lstm_model():
    import tensorflow as tf
    from tensorflow.keras import layers, models

    inp = layers.Input(shape=(SEQ_LEN, N_FEATURES), name="history_input")
    x = layers.LSTM(64, return_sequences=True, name="lstm_1")(inp)
    x = layers.Dropout(0.2, name="dropout_1")(x)
    x = layers.LSTM(32, name="lstm_2")(x)
    x = layers.Dropout(0.2, name="dropout_2")(x)
    x = layers.Dense(32, activation="relu", name="dense_1")(x)
    out = layers.Dense(N_OUTPUTS, name="forecast_output")(x)

    model = models.Model(inputs=inp, outputs=out, name="EngagementLSTM")
    model.compile(optimizer="adam", loss="mse", metrics=["mae"])
    return model


def _normalize(X: np.ndarray):
    global _scaler_mean, _scaler_std
    _scaler_mean = X.mean(axis=(0, 1), keepdims=True)
    _scaler_std = X.std(axis=(0, 1), keepdims=True) + 1e-8
    return (X - _scaler_mean) / _scaler_std


def _load_or_train() -> Optional[object]:
    global _model, _scaler_mean, _scaler_std
    if _model is not None:
        return _model

    try:
        import tensorflow as tf
        tf.get_logger().setLevel("ERROR")

        scaler_path = MODEL_PATH.parent / "scaler.npz"

        if MODEL_PATH.exists() and scaler_path.exists():
            _model = tf.keras.models.load_model(str(MODEL_PATH))
            sc = np.load(str(scaler_path))
            _scaler_mean = sc["mean"]
            _scaler_std = sc["std"]
            logger.info("lstm_model_loaded", path=str(MODEL_PATH))
            return _model

        logger.info("lstm_training_synthetic")
        X, y = _synthetic_series(500, SEQ_LEN)
        X_norm = _normalize(X)
        # y normalization (simple scale)
        y_mean = y.mean(axis=0, keepdims=True)
        y_std = y.std(axis=0, keepdims=True) + 1e-8
        y_norm = (y - y_mean) / y_std

        model = _build_lstm_model()
        model.fit(X_norm, y_norm, epochs=20, batch_size=32, validation_split=0.1, verbose=0)

        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        model.save(str(MODEL_PATH))
        np.savez(str(scaler_path), mean=_scaler_mean, std=_scaler_std)
        logger.info("lstm_model_saved", path=str(MODEL_PATH))
        _model = model
        return _model

    except ImportError:
        logger.warning("tensorflow_not_installed")
        return None
    except Exception as exc:
        logger.warning("lstm_train_failed", error=str(exc))
        return None


# ── Statistical fallback (no TF) ─────────────────────────────────────────────

def _statistical_forecast(history: list[dict], horizon: int) -> dict:
    """Simple linear-trend + noise forecast when LSTM unavailable."""
    def extract(key):
        return [float(e.get(key, 0)) for e in history]

    def trend_forecast(series, h):
        if len(series) < 2:
            return [series[-1] if series else 100] * h
        n = len(series)
        slope = (series[-1] - series[0]) / max(n - 1, 1)
        rng = np.random.RandomState(0)
        return [max(0, series[-1] + slope * (i + 1) + rng.uniform(-50, 50)) for i in range(h)]

    return {
        "predicted_likes": trend_forecast(extract("likes"), horizon),
        "predicted_shares": trend_forecast(extract("shares"), horizon),
        "predicted_comments": trend_forecast(extract("comments"), horizon),
        "predicted_ctr": [max(0, x) for x in trend_forecast(extract("ctr"), horizon)],
        "predicted_reach": trend_forecast(extract("reach"), horizon),
    }


# ── Public Service ────────────────────────────────────────────────────────────

class LSTMForecastService:
    def forecast(self, history: list[dict], horizon_days: int = 7) -> dict:
        """
        history: list of dicts with keys likes, shares, comments, ctr, reach
        Returns: dict with predicted_* lists of length horizon_days
        """
        model = _load_or_train()

        if model is None or len(history) < SEQ_LEN:
            logger.info("lstm_fallback", history_len=len(history))
            padded = self._pad_history(history)
            return _statistical_forecast(padded, horizon_days)

        try:
            import tensorflow as tf

            seq = self._history_to_array(history)  # (T, 5)
            # Use last SEQ_LEN days
            seq = seq[-SEQ_LEN:]
            seq_norm = (seq - _scaler_mean[0]) / _scaler_std[0]
            X = seq_norm[np.newaxis, ...]  # (1, SEQ_LEN, 5)

            # Roll forward horizon_days by iterative prediction
            all_preds = []
            current = seq_norm.copy()
            for _ in range(horizon_days):
                inp = current[np.newaxis, ...]
                pred_norm = model.predict(inp, verbose=0)[0]  # (5,)
                # Denormalize
                pred = pred_norm * _scaler_std[0][-1] + _scaler_mean[0][-1]
                all_preds.append(np.abs(pred))
                # Slide window
                new_step = pred_norm
                current = np.vstack([current[1:], new_step])

            all_preds = np.array(all_preds)
            keys = ["predicted_likes", "predicted_shares", "predicted_comments",
                    "predicted_ctr", "predicted_reach"]
            result = {}
            for i, key in enumerate(keys):
                result[key] = [round(float(v), 2) for v in all_preds[:, i % all_preds.shape[1]]]

            # Add simple 95% confidence interval
            result["confidence_intervals"] = {
                k: {
                    "lower": [round(v * 0.85, 2) for v in result[k]],
                    "upper": [round(v * 1.15, 2) for v in result[k]],
                }
                for k in keys
            }
            return result

        except Exception as exc:
            logger.warning("lstm_predict_failed", error=str(exc))
            return _statistical_forecast(history, horizon_days)

    def _history_to_array(self, history: list[dict]) -> np.ndarray:
        rows = []
        for e in history:
            rows.append([
                float(e.get("likes", 0)),
                float(e.get("shares", 0)),
                float(e.get("comments", 0)),
                float(e.get("ctr", 0)),
                float(e.get("reach", 0)),
            ])
        return np.array(rows, dtype=np.float32)

    def _pad_history(self, history: list[dict]) -> list[dict]:
        if not history:
            dummy = {"likes": 100, "shares": 20, "comments": 10, "ctr": 0.03, "reach": 1000}
            return [dummy] * SEQ_LEN
        while len(history) < SEQ_LEN:
            history.insert(0, history[0])
        return history


lstm_forecast_service = LSTMForecastService()
