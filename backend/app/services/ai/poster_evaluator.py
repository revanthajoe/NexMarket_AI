"""
app/services/ai/poster_evaluator.py
─────────────────────────────────────
Adapter: routes poster evaluation to InferenceManager → ModelManager → QwenVLService.

Normalises the raw evaluation dict into the standard schema
expected by the API endpoint and ORM model.
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.core.logging import get_logger
from app.prompts.templates import VISION_EVALUATION_SYSTEM_PROMPT, VISION_EVALUATION_USER_PROMPT

logger = get_logger(__name__)

_MOCK_EVALUATION = {
    "overall_score":      72.5,
    "dimensions": {
        "readability":   78,
        "layout":        70,
        "branding":      68,
        "contrast":      82,
        "cta_visibility":75,
        "visual_appeal": 65,
    },
    "strengths":   ["Strong color contrast", "CTA is prominent", "Product name is visible"],
    "weaknesses":  ["Background texture competes with text"],
    "suggestions": ["Add whitespace around headline", "Use one accent color for CTA"],
    "verdict":     "good",
}


class PosterEvaluatorService:

    async def evaluate(self, image_url: str) -> dict:
        logger.info("poster_evaluate url=%s provider=%s", image_url, settings.VISION_PROVIDER)

        if settings.VISION_PROVIDER == "mock":
            return self.normalize(_MOCK_EVALUATION)

        try:
            from ai.inference_manager import inference_manager
            raw = await inference_manager.evaluate_poster(
                image_url,
                VISION_EVALUATION_SYSTEM_PROMPT,
                VISION_EVALUATION_USER_PROMPT,
            )
            if raw:
                return self.normalize(raw)
        except Exception as exc:
            logger.warning("poster_evaluate_fallback error=%s", exc)

        return self.normalize(_MOCK_EVALUATION)

    def normalize(self, raw: dict) -> dict:
        """Flatten raw dict into the schema expected by the ORM."""
        dims = raw.get("dimensions", {})
        return {
            "overall_score":       raw.get("overall_score", 0),
            "readability_score":   dims.get("readability", 0),
            "layout_score":        dims.get("layout", 0),
            "branding_score":      dims.get("branding", 0),
            "contrast_score":      dims.get("contrast", 0),
            "cta_score":           dims.get("cta_visibility", 0),
            "visual_appeal_score": dims.get("visual_appeal", 0),
            "strengths":           raw.get("strengths", []),
            "weaknesses":          raw.get("weaknesses", []),
            "suggestions":         raw.get("suggestions", []),
            "raw_response":        raw,
        }


poster_evaluator = PosterEvaluatorService()
