"""
app/services/ai/ad_generator.py
────────────────────────────────
Adapter: routes ad copy generation to InferenceManager → ModelManager → QwenLLMService.

Handles:
  • Platform-specific prompt building
  • JSON response parsing
  • Demo template fallback (no model / demo mode)
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.prompts.templates import AD_COPY_SYSTEM_PROMPT, build_ad_copy_prompt

logger = get_logger(__name__)

_DEMO_COPY_TEMPLATE = {
    "instagram": {
        "headline": "🚀 {product_name} — {offer}",
        "body": "Discover {product_name} — designed for {target_audience}.\n\n{offer} 🎉\n\nTap the link in bio!",
        "cta_variants": ["Shop Now →", "Get the Deal!", "Claim Your Offer"],
        "hashtags": ["#deal", "#sale", "#musthave", "#shopnow"],
    },
    "facebook": {
        "headline": "{offer} — Limited Time Only!",
        "body": "Hey {target_audience}!\n\n{product_name} — {offer}\n\nClick below!",
        "cta_variants": ["Learn More", "Shop Now", "Get Offer"],
        "hashtags": [],
    },
    "linkedin": {
        "headline": "{product_name}: Transforming how {target_audience} works",
        "body": "Exciting offer for our LinkedIn community.\n\n{product_name} — {offer}",
        "cta_variants": ["Learn More", "Explore Now"],
        "hashtags": ["#innovation", "#business", "#growth"],
    },
    "twitter": {
        "headline": None,
        "body": "🔥 {product_name} | {offer} — Perfect for {target_audience}! 👇",
        "cta_variants": ["Shop Now", "Don't Miss Out!"],
        "hashtags": ["#deal", "#sale"],
    },
    "email": {
        "headline": "[Exclusive] {offer} on {product_name}",
        "body": "Hi there,\n\n{product_name}\n{offer}\n\nLimited time — act now.\n\nBest,\nNexMarket Team",
        "cta_variants": ["Claim Your Offer", "Shop Now"],
        "hashtags": [],
    },
}


class AdCopyGeneratorService:

    async def generate(
        self,
        product_name: str,
        description: str,
        offer: str,
        target_audience: str,
        campaign_goal: str,
        platforms: list[str],
        tone: str = "professional",
    ) -> dict[str, dict]:
        logger.info("adcopy_generate platforms=%s provider=%s", platforms, settings.LLM_PROVIDER)

        try:
            from ai.inference_manager import inference_manager
            system_prompt = AD_COPY_SYSTEM_PROMPT
            user_prompt   = build_ad_copy_prompt(
                product_name, description, offer, target_audience, campaign_goal, platforms, tone
            )
            result = await inference_manager.generate_ad_copy(system_prompt, user_prompt)
            if result:
                return result
        except Exception as exc:
            logger.warning("adcopy_fallback error=%s", exc)

        return self._generate_demo(product_name, offer, target_audience, platforms)

    def _generate_demo(self, product_name, offer, target_audience, platforms) -> dict:
        result = {}
        for platform in platforms:
            tmpl = _DEMO_COPY_TEMPLATE.get(platform)
            if not tmpl:
                continue

            def fmt(s):
                return s.format(
                    product_name=product_name,
                    offer=offer,
                    target_audience=target_audience,
                ) if s else None

            result[platform] = {
                "headline":     fmt(tmpl["headline"]),
                "body":         fmt(tmpl["body"]),
                "cta_variants": tmpl["cta_variants"],
                "hashtags":     tmpl["hashtags"],
            }
        logger.info("adcopy_demo_generated platforms=%s", platforms)
        return result


ad_copy_generator = AdCopyGeneratorService()
