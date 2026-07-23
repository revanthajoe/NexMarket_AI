"""
ai/model_registry.py
──────────────────────
Centralised catalogue of every AI model used by NexMarket.
ModelManager reads this registry — no service hardcodes HF IDs.

ModelSpec fields:
  model_id      – HuggingFace repo ID or local path
  priority      – lower = higher priority in queue (1 = highest)
  use_4bit      – apply NF4 quantization
  model_type    – "causal_lm" | "vision_lm" | "diffusion" | "classifier" | "xgboost" | "lstm"
  trust_remote  – pass trust_remote_code=True (required for Qwen)
  flash_attn    – request flash-attention-2 if available
  description   – human-readable label
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Literal

ModelType = Literal["causal_lm", "vision_lm", "diffusion", "classifier", "xgboost", "lstm"]


@dataclass(frozen=True)
class ModelSpec:
    model_id:     str
    priority:     int          # 1 = highest
    model_type:   ModelType
    use_4bit:     bool = False
    trust_remote: bool = False
    flash_attn:   bool = False
    description:  str  = ""


# ── Registry ──────────────────────────────────────────────────────────────────

REGISTRY: Dict[str, ModelSpec] = {
    # ── Poster Generation (SDXL) ─────────────────────────────── priority 1 ──
    "sdxl": ModelSpec(
        model_id     = "stabilityai/stable-diffusion-xl-base-1.0",
        priority     = 1,
        model_type   = "diffusion",
        use_4bit     = False,       # never quantize diffusion models
        trust_remote = False,
        flash_attn   = False,
        description  = "Stable Diffusion XL — fp16, attention slicing, VAE tiling",
    ),

    # ── Poster Evaluation (Qwen2.5-VL) ───────────────────────── priority 2 ──
    "qwen_vl": ModelSpec(
        model_id     = "Qwen/Qwen2.5-VL-3B-Instruct",
        priority     = 2,
        model_type   = "vision_lm",
        use_4bit     = True,
        trust_remote = True,
        flash_attn   = True,
        description  = "Qwen2.5-VL-3B-Instruct — 4-bit NF4, poster evaluation",
    ),

    # ── Advertisement Generation (Qwen2.5) ───────────────────── priority 3 ──
    "qwen_llm": ModelSpec(
        model_id     = "Qwen/Qwen2.5-3B-Instruct",
        priority     = 3,
        model_type   = "causal_lm",
        use_4bit     = True,
        trust_remote = True,
        flash_attn   = True,
        description  = "Qwen2.5-3B-Instruct — 4-bit NF4, ad copy generation",
    ),

    # ── Sentiment Analysis (DistilBERT) ───────────────────────── priority 4 ──
    "distilbert": ModelSpec(
        model_id     = "distilbert-base-uncased-finetuned-sst-2-english",
        priority     = 4,
        model_type   = "classifier",
        use_4bit     = False,       # lightweight, no quantization needed
        trust_remote = False,
        flash_attn   = False,
        description  = "DistilBERT SST-2 — sentiment classification",
    ),

    # ── Lead Prediction (XGBoost) ─────────────────────────────── priority 5 ──
    "xgboost": ModelSpec(
        model_id     = "local://ml/xgboost_model/lead_model.json",
        priority     = 5,
        model_type   = "xgboost",
        use_4bit     = False,
        trust_remote = False,
        flash_attn   = False,
        description  = "XGBoost lead scoring — synthetic-trained, CPU-only",
    ),

    # ── Engagement Forecasting (LSTM) ─────────────────────────── priority 6 ──
    "lstm": ModelSpec(
        model_id     = "local://ml/lstm/engagement_lstm.pt",
        priority     = 6,
        model_type   = "lstm",
        use_4bit     = False,
        trust_remote = False,
        flash_attn   = False,
        description  = "LSTM engagement forecasting — pure PyTorch, synthetic-trained",
    ),
}


def get_spec(name: str) -> ModelSpec:
    """Fetch a ModelSpec by name; raises KeyError if unknown."""
    if name not in REGISTRY:
        raise KeyError(f"Unknown model key '{name}'. Available: {list(REGISTRY)}")
    return REGISTRY[name]
