"""
ai/forecasting/lstm_service.py
───────────────────────────────
Pure-PyTorch LSTM — Engagement forecasting service.

Architecture:
  Input  → LSTM(64) → Dropout(0.2) → LSTM(32) → Dropout(0.2)
         → Linear(32) → Linear(5)

Output features (5):
  [likes, shares, comments, ctr, reach]

Input window: 14 days of the 5 features above.
Forecast horizon: configurable (default 7 days).

Model auto-trains on synthetic data if not saved.
Saved as pure PyTorch state_dict (.pt) — no TensorFlow dependency.

Lifecycle:
    load()    → load state_dict and scaler
  forecast()→ normalise → iterative rollout → denormalise → return
  unload()  → delete model, purge
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn

from ai.base_model import BaseModelService
from ai.device_manager import device_manager
from ai import memory_manager
from ai.model_registry import get_spec

logger = logging.getLogger(__name__)

_SPEC       = get_spec("lstm")
_MODEL_PATH = Path(_SPEC.model_id.replace("local://", ""))
_SCALER_PATH = _MODEL_PATH.with_suffix(".scaler.npz")

_SEQ_LEN    = 14    # input window length (days)
_N_FEATURES = 5     # likes, shares, comments, ctr, reach
_HIDDEN1    = 64
_HIDDEN2    = 32
# ── Model definition ──────────────────────────────────────────────────────────

class _EngagementLSTM(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.lstm1   = nn.LSTM(_N_FEATURES, _HIDDEN1, batch_first=True)
        self.drop1   = nn.Dropout(0.2)
        self.lstm2   = nn.LSTM(_HIDDEN1,    _HIDDEN2, batch_first=True)
        self.drop2   = nn.Dropout(0.2)
        self.fc1     = nn.Linear(_HIDDEN2, 32)
        self.relu    = nn.ReLU()
        self.fc_out  = nn.Linear(32, _N_FEATURES)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, seq_len, n_features)
        out, _ = self.lstm1(x)
        out    = self.drop1(out)
        out, _ = self.lstm2(out)
        out    = self.drop2(out)
        last   = out[:, -1, :]        # take last time step
        return self.fc_out(self.relu(self.fc1(last)))


# ── Service ───────────────────────────────────────────────────────────────────

class LSTMService(BaseModelService):

    def __init__(self) -> None:
        super().__init__("lstm")
        self._model:  Optional[_EngagementLSTM] = None
        self._scaler_mean: Optional[np.ndarray] = None
        self._scaler_std:  Optional[np.ndarray] = None

    # ── BaseModelService interface ────────────────────────────────────────────

    def _do_load(self) -> None:
        if _MODEL_PATH.exists() and _SCALER_PATH.exists():
            logger.info("lstm loading saved weights path=%s", _MODEL_PATH)
            self._model = _EngagementLSTM()
            self._model.load_state_dict(
                torch.load(str(_MODEL_PATH), map_location="cpu", weights_only=True)
            )
            scaler = np.load(str(_SCALER_PATH))
            self._scaler_mean = scaler["mean"]
            self._scaler_std  = scaler["std"]
        else:
            raise RuntimeError(
                "INSUFFICIENT_DATA: LSTM artifact and scaler are required; "
                "synthetic training is disabled"
            )

        self._model = self._model.to(device_manager.torch_device)
        self._model.eval()

    def _do_unload(self) -> None:
        self._model = self._scaler_mean = self._scaler_std = None
        memory_manager.purge()

    def health_check(self) -> bool:
        try:
            dummy = np.zeros((_SEQ_LEN, _N_FEATURES), dtype=np.float32)
            result = self.forecast(dummy, horizon_days=2)
            return "predicted_likes" in result
        except Exception:
            return False

    # ── Public inference API ──────────────────────────────────────────────────

    def forecast(self, history: np.ndarray, horizon_days: int = 7) -> dict:
        """
        Iterative LSTM rollout.

        history: array of shape (T, 5) where T >= SEQ_LEN.
                 Columns: [likes, shares, comments, ctr, reach]
        Returns dict of horizon-length lists for each metric.
        """
        if history.shape[0] < _SEQ_LEN:
            raise ValueError("INSUFFICIENT_DATA: at least 14 actual observations are required")

        # Use the last SEQ_LEN rows
        window = history[-_SEQ_LEN:].copy().astype(np.float32)

        # Normalise
        std_safe = np.where(self._scaler_std == 0, 1.0, self._scaler_std)
        window_n = (window - self._scaler_mean) / std_safe

        predictions: list[np.ndarray] = []

        with torch.no_grad():
            buf = window_n.copy()
            for _ in range(horizon_days):
                x   = torch.tensor(buf[-_SEQ_LEN:], dtype=torch.float32).unsqueeze(0)
                x   = x.to(device_manager.torch_device)
                out = self._model(x).cpu().numpy()[0]          # (5,)
                predictions.append(out)
                # Append prediction to buffer for next step
                buf = np.vstack([buf, out])

        # Denormalise
        preds = np.array(predictions)                          # (horizon, 5)
        preds = (preds * std_safe) + self._scaler_mean

        # Clip negatives
        preds = np.clip(preds, 0, None)
        preds[:, 3] = np.clip(preds[:, 3], 0, 1)              # ctr in [0,1]

        # Confidence intervals (±15%)
        ci = {
            col: {
                "lower": (preds[:, i] * 0.85).tolist(),
                "upper": (preds[:, i] * 1.15).tolist(),
            }
            for i, col in enumerate(["likes", "shares", "comments", "ctr", "reach"])
        }

        return {
            "predicted_likes":    preds[:, 0].tolist(),
            "predicted_shares":   preds[:, 1].tolist(),
            "predicted_comments": preds[:, 2].tolist(),
            "predicted_ctr":      preds[:, 3].tolist(),
            "predicted_reach":    preds[:, 4].tolist(),
            "confidence_intervals": ci,
            "model_version":      "lstm-v1",
        }


