"""
ai/sentiment/distilbert_service.py
────────────────────────────────────
DistilBERT SST-2 — Sentiment classification service.

Lightweight model — no 4-bit quantization needed.
Runs pipeline-style: load pipeline → run → unload.

Lifecycle:
  load()    → transformers pipeline("text-classification", ...)
  analyze() → pipeline(texts, batch_size=8) → normalize labels
  unload()  → purge model + pipeline
"""
from __future__ import annotations

import logging
from typing import List

from ai.base_model import BaseModelService
from ai.device_manager import device_manager
from ai import memory_manager
from ai.model_registry import get_spec

logger = logging.getLogger(__name__)

_SPEC = get_spec("distilbert")

# Keyword fallback for CPU-only environments where even DistilBERT is slow
_POS_KEYWORDS = {"great", "amazing", "love", "excellent", "fantastic", "good", "best", "awesome", "perfect"}
_NEG_KEYWORDS = {"terrible", "awful", "hate", "worst", "bad", "horrible", "poor", "disappointing", "useless"}


class DistilBERTService(BaseModelService):

    def __init__(self) -> None:
        super().__init__("distilbert")

    # ── BaseModelService interface ────────────────────────────────────────────

    def _do_load(self) -> None:
        from transformers import pipeline as hf_pipeline

        device_id = 0 if device_manager.info.has_cuda else -1
        logger.info("distilbert loading model_id=%s device_id=%d", _SPEC.model_id, device_id)

        self._pipeline = hf_pipeline(
            "text-classification",
            model        = _SPEC.model_id,
            device       = device_id,
            top_k        = None,          # return all labels
            truncation   = True,
            max_length   = 512,
        )

    def _do_unload(self) -> None:
        memory_manager.purge(self._pipeline)
        self._pipeline = None

    def health_check(self) -> bool:
        try:
            results = self._pipeline("test")
            return isinstance(results, list) and len(results) > 0
        except Exception:
            return False

    # ── Public inference API ──────────────────────────────────────────────────

    def analyze(self, texts: List[str]) -> List[dict]:
        """
        Classify sentiment for a list of texts.

        Returns list of:
          {
            "text": str,
            "label": "positive" | "negative" | "neutral",
            "positive_score": float,
            "negative_score": float,
            "neutral_score":  float,
            "confidence":     float,
            "model_used":     "distilbert",
          }
        """
        if not texts:
            return []
        
        try:
            raw_results = self._pipeline(texts, batch_size=8, truncation=True)
            return [_normalize(text, result) for text, result in zip(texts, raw_results)]
        except Exception as exc:
            logger.warning("distilbert inference failed: %s — using keyword fallback", exc)
            return [_keyword_fallback(t) for t in texts]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _normalize(text: str, result: list) -> dict:
    """Convert HuggingFace output to our standard schema."""
    scores: dict[str, float] = {}
    for item in result:
        label = item["label"].lower()
        scores[label] = item["score"]

    pos = scores.get("positive", scores.get("pos", 0.0))
    neg = scores.get("negative", scores.get("neg", 0.0))
    neu = max(0.0, 1.0 - pos - neg)

    if pos >= neg and pos > 0.55:
        label = "positive"
        conf  = pos
    elif neg > pos and neg > 0.55:
        label = "negative"
        conf  = neg
    else:
        label = "neutral"
        conf  = neu

    return {
        "text":            text,
        "label":           label,
        "positive_score":  round(pos, 4),
        "negative_score":  round(neg, 4),
        "neutral_score":   round(neu, 4),
        "confidence":      round(conf, 4),
        "model_used":      "distilbert",
    }


def _keyword_fallback(text: str) -> dict:
    words = set(text.lower().split())
    pos   = len(words & _POS_KEYWORDS)
    neg   = len(words & _NEG_KEYWORDS)
    if pos > neg:
        label, ps, ns = "positive", 0.85, 0.10
    elif neg > pos:
        label, ps, ns = "negative", 0.10, 0.85
    else:
        label, ps, ns = "neutral", 0.33, 0.33
    return {
        "text": text, "label": label,
        "positive_score": ps, "negative_score": ns, "neutral_score": round(1-ps-ns, 2),
        "confidence": max(ps, ns), "model_used": "keyword-fallback",
    }
