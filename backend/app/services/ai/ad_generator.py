"""
app/services/ai/ad_generator.py
────────────────────────────────
Adapter: routes ad copy generation to InferenceManager → ModelManager → QwenLLMService.

Handles:
  • Platform-specific prompt building
  • JSON response parsing
  • Template fallback if the model call raises (never a mock mode — LLM_PROVIDER
    is always a real provider in this deployment)
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
    "telegram": {
        "headline": None,
        "body": "📢 {product_name} — {offer}\n\nPerfect for {target_audience}.",
        "cta_variants": ["Shop Now", "Learn More"],
        "hashtags": [],
    },
    "whatsapp": {
        "headline": None,
        "body": "Hi! 👋 {product_name} — {offer}. Perfect for {target_audience}. Reply to know more!",
        "cta_variants": ["Get the Deal", "Learn More"],
        "hashtags": [],
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
        language: str = "en",
    ) -> dict[str, dict]:
        logger.info(
            "adcopy_generate platforms=%s provider=%s language=%s",
            platforms, settings.LLM_PROVIDER, language,
        )

        try:
            from app.services.ai.text_provider import generate_marketing_json
            system_prompt = AD_COPY_SYSTEM_PROMPT
            user_prompt   = build_ad_copy_prompt(
                product_name, description, offer, target_audience,
                campaign_goal, platforms, tone, language,
            )
            # Routed through the local Qwen provider, the same path poster copy
            # uses. This keeps ad copy and poster copy on one deterministic
            # provider boundary with the existing template fallback.
            #
            # The retry stays for the local branch, where failure is a
            # stochastic sampling outcome (temperature=0.7, do_sample=True)
            # rather than a deterministic error, and the model is already
            # resident in GPU memory so a second draw is cheap.
            for attempt in (1, 2):
                result = await generate_marketing_json(system_prompt, user_prompt)
                if result:
                    return result
                logger.warning(
                    "adcopy_json_empty attempt=%d/2 provider=%s language=%s platforms=%s — "
                    "the model returned no usable JSON object",
                    attempt, settings.AI_TEXT_PROVIDER, language, platforms,
                )
        except Exception as exc:
            logger.warning("adcopy_fallback error=%s", exc, exc_info=True)

        # Both attempts failed (or the call raised). Falling through to
        # hardcoded English is real campaign data slotted into fake copy in
        # the wrong language — it must never be mistaken for a real result,
        # which is exactly what happened before this flag existed: the
        # fallback template is plausible enough that a failed Tamil request
        # silently came back as fluent-looking English with no visible error.
        logger.warning(
            "adcopy_fallback_used language=%s platforms=%s — returning "
            "placeholder copy, not a real generation result",
            language, platforms,
        )
        return self._generate_fallback(product_name, offer, target_audience, platforms, language)

    def _generate_fallback(self, product_name, offer, target_audience, platforms, language="en") -> dict:
        # Fallback string translations for basic languages
        _translations = {
            "en": {
                "headline": "🚀 {product_name} — {offer}",
                "body": "Discover {product_name} — designed for {target_audience}.\n\n{offer} 🎉\n\nTap the link in bio!",
                "cta": ["Shop Now →", "Get the Deal!", "Claim Your Offer"],
                "tg_body": "📢 {product_name} — {offer}\n\nPerfect for {target_audience}."
            },
            "ta": {
                "headline": "🚀 {product_name} — {offer}",
                "body": "கண்டறியவும் {product_name} — {target_audience}-க்காக உருவாக்கப்பட்டது.\n\n{offer} 🎉",
                "cta": ["இப்போது வாங்கு →", "சலுகையை பெறு!"],
                "tg_body": "📢 {product_name} — {offer}\n\n{target_audience}-க்கு மிகவும் ஏற்றது."
            },
            "hi": {
                "headline": "🚀 {product_name} — {offer}",
                "body": "पेश है {product_name} — {target_audience} के लिए.\n\n{offer} 🎉",
                "cta": ["अभी खरीदें →", "ऑफर लें!"],
                "tg_body": "📢 {product_name} — {offer}\n\n{target_audience} के लिए बेहतरीन."
            },
            "te": {
                "headline": "🚀 {product_name} — {offer}",
                "body": "తెలుసుకోండి {product_name} — {target_audience} కోసం.\n\n{offer} 🎉",
                "cta": ["ఇప్పుడు కొనండి →", "ఆఫర్ పొందండి!"],
                "tg_body": "📢 {product_name} — {offer}\n\n{target_audience} కు సరైనది."
            }
        }
        
        t = _translations.get(language, _translations["en"])
        
        result = {}
        for platform in platforms:
            def fmt(s):
                return s.format(
                    product_name=product_name,
                    offer=offer,
                    target_audience=target_audience,
                ) if s else None

            is_tg = platform in ("telegram", "whatsapp")
            
            result[platform] = {
                "headline":     None if is_tg else fmt(t["headline"]),
                "body":         fmt(t["tg_body"]) if is_tg else fmt(t["body"]),
                "cta_variants": t["cta"],
                "hashtags":     ["#deal", "#offer"],
                "fallback":     True,
            }
        logger.info("adcopy_fallback_generated platforms=%s language=%s", platforms, language)
        return result


ad_copy_generator = AdCopyGeneratorService()
