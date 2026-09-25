"""
app/services/ai/poster_evaluator.py
─────────────────────────────────────
Adapter: routes poster evaluation to the local Qwen-VL inference manager.

Normalises the raw evaluation dict into the standard schema
expected by the API endpoint and ORM model.

"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.core.logging import get_logger
from app.prompts.templates import VISION_EVALUATION_SYSTEM_PROMPT, VISION_EVALUATION_USER_PROMPT

logger = get_logger(__name__)

_FALLBACK_EVALUATION = {
    "overall_score":      0.0,
    "dimensions": {
        "readability":   0,
        "layout":        0,
        "branding":      68,
        "contrast":      82,
        "cta_visibility":75,
        "visual_appeal": 65,
    },
    "strengths":   ["Strong color contrast", "CTA is prominent", "Product name is visible"],
    "weaknesses":  ["Background texture competes with text"],
    "suggestions": ["Add whitespace around headline", "Use one accent color for CTA"],
    "verdict":     "good",
    # Marks the score as synthetic. Without this a broken evaluator silently
    # reports 72.5 — above the 70 approval threshold — so every poster reads as
    # "approved on attempt 1" and the improvement retry never fires.
    "fallback":    True,
}


class PosterEvaluatorService:

    async def evaluate(self, image_url: str, context: str = "") -> dict:
        provider = settings.AI_TEXT_PROVIDER
        logger.info("poster_evaluate url=%s provider=%s", image_url, provider)

        try:
            from app.prompts.templates import (
                VISION_EVALUATION_SYSTEM_PROMPT,
                build_vision_evaluation_prompt,
            )
            user_prompt = build_vision_evaluation_prompt(context)

            from ai.inference_manager import inference_manager
            raw = await inference_manager.evaluate_poster(
                image_url, VISION_EVALUATION_SYSTEM_PROMPT, user_prompt,
            )
            if raw:
                return self.normalize(raw)
        except Exception as exc:
            logger.warning("poster_evaluate_fallback error=%s", exc)

        return self.normalize(_FALLBACK_EVALUATION)

    def normalize(self, raw: dict) -> dict:
        """Flatten raw dict into the schema expected by the ORM."""
        dims = raw.get("dimensions", {})
        issues = raw.get("issues", [])
        recommendations = raw.get("recommendations", [])
        return {
            "overall_score":       raw.get("overall_score", 0),
            "product_relevance_score": dims.get("product_relevance", raw.get("product_relevance", 0)),
            "campaign_relevance_score": dims.get("campaign_relevance", raw.get("campaign_relevance", 0)),
            "audience_relevance_score": dims.get("audience_relevance", raw.get("audience_relevance", 0)),
            "visual_quality_score": dims.get("visual_quality", raw.get("visual_quality", 0)),
            "composition_quality_score": dims.get("composition_quality", raw.get("composition_quality", 0)),
            "marketing_quality_score": dims.get("marketing_quality", raw.get("marketing_quality", 0)),
            "readability_score":   dims.get("readability", 0),
            "layout_score":        dims.get("layout", 0),
            "branding_score":      dims.get("branding", 0),
            "contrast_score":      dims.get("contrast", 0),
            "cta_score":           dims.get("cta_visibility", 0),
            "visual_appeal_score": dims.get("visual_appeal", 0),
            "strengths":           raw.get("strengths", []),
            "weaknesses":          raw.get("weaknesses", []),
            "suggestions":         raw.get("suggestions", []),
            "generic_template_detected": bool(raw.get("generic_template_detected", False)),
            "duplicate_content_detected": bool(raw.get("duplicate_content_detected", False)),
            "issues":              issues if isinstance(issues, list) else [],
            "recommendations":     recommendations if isinstance(recommendations, list) else [],
            "fallback":            bool(raw.get("fallback", False)),
            "source_type":          "FALLBACK" if raw.get("fallback", False) else "PREDICTED",
            "source_system":        "local_qwen_vl",
            "model_name":           None if raw.get("fallback", False) else "Qwen/Qwen2.5-VL-3B-Instruct",
            "model_version":        None,
            "is_fallback":          bool(raw.get("fallback", False)),
            "raw_response":        raw,
        }


poster_evaluator = PosterEvaluatorService()
