"""
Module 2: Ad Copy Generator Service
Uses LLM (OpenAI / Gemini) to produce platform-specific ad copy.
Falls back to template-based generation in demo mode.
"""
from __future__ import annotations

import json
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.prompts.templates import AD_COPY_SYSTEM_PROMPT, build_ad_copy_prompt

logger = get_logger(__name__)

_DEMO_COPY_TEMPLATE = {
    "instagram": {
        "headline": "🚀 {product_name} — {offer}",
        "body": (
            "Discover {product_name} — designed for {target_audience}.\n\n"
            "{offer} 🎉\n\nDon't miss out. Tap the link in bio to grab yours!"
        ),
        "cta_variants": ["Shop Now →", "Get the Deal!", "Claim Your Offer"],
        "hashtags": ["#deal", "#sale", "#musthave", "#shopnow", "#trending"],
    },
    "facebook": {
        "headline": "{offer} — Limited Time Only!",
        "body": (
            "Hey {target_audience}!\n\n"
            "We're excited to introduce {product_name}.\n\n"
            "{offer}\n\nClick below to learn more and take advantage of this exclusive offer!"
        ),
        "cta_variants": ["Learn More", "Shop Now", "Get Offer"],
        "hashtags": [],
    },
    "linkedin": {
        "headline": "{product_name}: Transforming the way {target_audience} works",
        "body": (
            "We're proud to announce a special offer for our LinkedIn community.\n\n"
            "{product_name} — {offer}\n\n"
            "Join thousands of {target_audience} who are already seeing results. "
            "Click the link to learn more."
        ),
        "cta_variants": ["Learn More", "Connect With Us", "Explore Now"],
        "hashtags": ["#innovation", "#business", "#growth", "#marketing"],
    },
    "twitter": {
        "headline": None,
        "body": "🔥 {product_name} | {offer} — Perfect for {target_audience}! Grab yours before it's gone 👇",
        "cta_variants": ["Shop Now", "Don't Miss Out!"],
        "hashtags": ["#deal", "#sale", "#trending"],
    },
    "email": {
        "headline": "[Exclusive] {offer} on {product_name} — For {target_audience}",
        "body": (
            "Hi there,\n\n"
            "We have an exclusive offer just for you.\n\n"
            "{product_name}\n{offer}\n\n"
            "This offer is available for a limited time only, specifically for {target_audience}.\n\n"
            "Click below to take advantage now.\n\nBest regards,\nThe NexMarket Team"
        ),
        "cta_variants": ["Claim Your Offer", "Shop Now", "View Details"],
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
        logger.info("adcopy_generate", platforms=platforms, provider=settings.LLM_PROVIDER)

        try:
            if settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY:
                return await self._generate_openai(
                    product_name, description, offer, target_audience, campaign_goal, platforms, tone
                )
            elif settings.LLM_PROVIDER == "gemini" and settings.GEMINI_API_KEY:
                return await self._generate_gemini(
                    product_name, description, offer, target_audience, campaign_goal, platforms, tone
                )
            else:
                return self._generate_demo(product_name, offer, target_audience, platforms)
        except Exception as exc:
            logger.warning("adcopy_fallback", error=str(exc))
            return self._generate_demo(product_name, offer, target_audience, platforms)

    # ── OpenAI ────────────────────────────────────────────────────────────────

    async def _generate_openai(
        self, product_name, description, offer, target_audience, campaign_goal, platforms, tone
    ) -> dict:
        import openai

        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        prompt = build_ad_copy_prompt(
            product_name, description, offer, target_audience, campaign_goal, platforms, tone
        )
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": AD_COPY_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        raw = response.choices[0].message.content
        return json.loads(raw)

    # ── Gemini ────────────────────────────────────────────────────────────────

    async def _generate_gemini(
        self, product_name, description, offer, target_audience, campaign_goal, platforms, tone
    ) -> dict:
        import google.generativeai as genai

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            AD_COPY_SYSTEM_PROMPT
            + "\n\n"
            + build_ad_copy_prompt(
                product_name, description, offer, target_audience, campaign_goal, platforms, tone
            )
        )
        resp = model.generate_content(prompt)
        raw = resp.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)

    # ── Demo / Fallback ───────────────────────────────────────────────────────

    def _generate_demo(
        self,
        product_name: str,
        offer: str,
        target_audience: str,
        platforms: list[str],
    ) -> dict:
        result = {}
        for platform in platforms:
            template = _DEMO_COPY_TEMPLATE.get(platform)
            if not template:
                continue
            def fmt(s):
                if s is None:
                    return None
                return s.format(
                    product_name=product_name,
                    offer=offer,
                    target_audience=target_audience,
                )
            result[platform] = {
                "headline": fmt(template["headline"]),
                "body": fmt(template["body"]),
                "cta_variants": template["cta_variants"],
                "hashtags": template["hashtags"],
            }
        logger.info("adcopy_demo_generated", platforms=platforms)
        return result


ad_copy_generator = AdCopyGeneratorService()
