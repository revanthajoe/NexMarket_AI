"""
Module 4: Sentiment Analysis Service
Uses DistilBERT (HuggingFace transformers) for fast, reliable sentiment.
Falls back to rule-based VADER-style scoring if model not available.
"""
from __future__ import annotations

import re
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_pipeline = None


def _load_pipeline():
    global _pipeline
    if _pipeline is None:
        try:
            from transformers import pipeline

            _pipeline = pipeline(
                "sentiment-analysis",
                model=settings.SENTIMENT_MODEL,
                truncation=True,
                max_length=512,
            )
            logger.info("sentiment_model_loaded", model=settings.SENTIMENT_MODEL)
        except Exception as exc:
            logger.warning("sentiment_model_load_failed", error=str(exc))
            _pipeline = None
    return _pipeline


# ── Simple keyword-based fallback ────────────────────────────────────────────

_POSITIVE_WORDS = {
    "great", "amazing", "love", "excellent", "fantastic", "wonderful", "good",
    "best", "perfect", "happy", "awesome", "superb", "brilliant", "outstanding",
}
_NEGATIVE_WORDS = {
    "bad", "terrible", "awful", "worst", "hate", "horrible", "poor", "disappointing",
    "useless", "waste", "broken", "fail", "wrong", "slow", "ugly",
}


def _rule_based_sentiment(text: str) -> dict:
    words = set(re.sub(r"[^a-z\s]", "", text.lower()).split())
    pos = len(words & _POSITIVE_WORDS)
    neg = len(words & _NEGATIVE_WORDS)
    total = max(pos + neg, 1)
    pos_score = round(pos / total, 3)
    neg_score = round(neg / total, 3)
    neutral_score = round(max(0, 1 - pos_score - neg_score), 3)

    if pos > neg:
        label, confidence = "positive", pos_score
    elif neg > pos:
        label, confidence = "negative", neg_score
    else:
        label, confidence = "neutral", neutral_score

    return {
        "label": label,
        "positive_score": pos_score,
        "negative_score": neg_score,
        "neutral_score": neutral_score,
        "confidence": confidence,
        "model_used": "rule-based-fallback",
    }


class SentimentService:
    async def analyze(self, text: str, campaign_id: Optional[str] = None) -> dict:
        pipe = _load_pipeline()
        if pipe is None:
            return _rule_based_sentiment(text)

        try:
            result = pipe(text)[0]
            # DistilBERT returns POSITIVE/NEGATIVE
            raw_label = result["label"].lower()
            score = round(float(result["score"]), 4)

            if raw_label == "positive":
                return {
                    "label": "positive",
                    "positive_score": score,
                    "negative_score": round(1 - score, 4),
                    "neutral_score": 0.0,
                    "confidence": score,
                    "model_used": settings.SENTIMENT_MODEL,
                }
            else:
                return {
                    "label": "negative",
                    "positive_score": round(1 - score, 4),
                    "negative_score": score,
                    "neutral_score": 0.0,
                    "confidence": score,
                    "model_used": settings.SENTIMENT_MODEL,
                }
        except Exception as exc:
            logger.warning("sentiment_inference_failed", error=str(exc))
            return _rule_based_sentiment(text)

    async def analyze_batch(self, texts: list[str], campaign_id: Optional[str] = None) -> list[dict]:
        results = []
        for text in texts:
            r = await self.analyze(text, campaign_id)
            r["text"] = text
            results.append(r)
        return results

    def summarize(self, results: list[dict]) -> dict[str, int]:
        summary = {"positive": 0, "negative": 0, "neutral": 0}
        for r in results:
            label = r.get("label", "neutral")
            summary[label] = summary.get(label, 0) + 1
        return summary


sentiment_service = SentimentService()
