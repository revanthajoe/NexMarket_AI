"""
app/services/ai/sentiment.py
──────────────────────────────
Adapter: routes sentiment requests to InferenceManager → DistilBERTService.
"""
from __future__ import annotations

import logging
from typing import List

from app.core.logging import get_logger

logger = get_logger(__name__)


class SentimentService:

    async def analyze(
        self,
        texts: List[str],
        campaign_id: str = None,
        source_type: str = "UNKNOWN",
        source_system: str = None,
        source_reference: str = None,
    ) -> dict:
        logger.info("sentiment_analyze n=%d", len(texts))

        try:
            from ai.inference_manager import inference_manager
            results = await inference_manager.analyze_sentiment(texts)
        except Exception as exc:
            logger.warning("sentiment_fallback error=%s", exc)
            results = [_keyword_fallback(t) for t in texts]

        for result in results:
            model_used = result.get("model_used", "unknown")
            is_fallback = model_used == "keyword-fallback"
            result["source_type"] = "FALLBACK" if is_fallback else "PREDICTED"
            result["input_source_type"] = source_type
            result["source_system"] = source_system or "customer_text"
            result["source_reference"] = source_reference
            result["model_name"] = "DistilBERT SST-2" if not is_fallback else None
            result["model_version"] = model_used if not is_fallback else None
            result["is_fallback"] = is_fallback

        summary = _summarize(results)
        return {"results": results, "summary": summary}


def _keyword_fallback(text: str) -> dict:
    pos_kw = {"great", "amazing", "love", "excellent", "fantastic", "good", "best"}
    neg_kw = {"terrible", "awful", "hate", "worst", "bad", "horrible", "poor"}
    words  = set(text.lower().split())
    pos, neg = len(words & pos_kw), len(words & neg_kw)
    if pos > neg:
        label, ps, ns = "positive", 0.85, 0.10
    elif neg > pos:
        label, ps, ns = "negative", 0.10, 0.85
    else:
        label, ps, ns = "neutral", 0.33, 0.33
    return {
        "text": text, "label": label,
        "positive_score": ps, "negative_score": ns,
        "neutral_score": round(1 - ps - ns, 2),
        "confidence": max(ps, ns), "model_used": "keyword-fallback",
    }


def _summarize(results: list) -> dict:
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    for r in results:
        counts[r.get("label", "neutral")] += 1
    return counts


sentiment_service = SentimentService()
