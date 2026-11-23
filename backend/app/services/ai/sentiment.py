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

        if source_type != "ACTUAL":
            raise ValueError("Sentiment requires ACTUAL input text")
        if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Sentiment requires eligible ACTUAL text")

        try:
            from ai.inference_manager import inference_manager
            results = await inference_manager.analyze_sentiment(texts)
        except Exception as exc:
            logger.warning("sentiment_unavailable error=%s", exc)
            raise RuntimeError("UNAVAILABLE: DistilBERT sentiment model is unavailable") from exc

        for result in results:
            # The keyword fallback is a guess, not a model output. Stamping it
            # PREDICTED attributed DistilBERT (and a model_version_id
            # downstream) to a result no model produced.
            is_fallback = bool(result.get("fallback", False))
            result["source_type"] = "FALLBACK" if is_fallback else "PREDICTED"
            result["input_source_type"] = source_type
            result["is_fallback"] = is_fallback
            result["model_name"] = None if is_fallback else "DistilBERT SST-2"
            result["model_version"] = None if is_fallback else result.get("model_used", "unknown")
            result["source_system"] = (
                "keyword_fallback" if is_fallback else (source_system or "customer_text")
            )
            result["source_reference"] = source_reference

        summary = _summarize(results)
        return {"results": results, "summary": summary}


def _summarize(results: list) -> dict:
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    for r in results:
        counts[r.get("label", "neutral")] += 1
    return counts


sentiment_service = SentimentService()
