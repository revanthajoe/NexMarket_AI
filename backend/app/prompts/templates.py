"""
Prompt templates for poster generation and ad copy.
Keep all prompt text here — services import from this module.
"""
from __future__ import annotations

from typing import Optional


# ─── Poster Generation Prompt ────────────────────────────────────────────────

def build_poster_prompt(
    product_name: str,
    offer: str,
    target_audience: str,
    brand_style: Optional[str],
    campaign_goal: str,
    variation: int = 0,
) -> str:
    style_map = {
        0: "vibrant, bold, modern",
        1: "minimalist, clean, professional",
        2: "dark luxury, premium, elegant",
        3: "playful, colorful, energetic",
    }
    variation_style = style_map.get(variation, "vibrant, bold, modern")
    brand_note = f", {brand_style} brand identity" if brand_style else ""

    return (
        f"Create a professional marketing poster for '{product_name}'. "
        f"Offer: {offer}. Target audience: {target_audience}. "
        f"Campaign goal: {campaign_goal}. "
        f"Style: {variation_style}{brand_note}. "
        f"Include a clear CTA button, product name, offer text, and visually striking background. "
        f"Make it suitable for digital advertising. High quality, 1024x1024."
    )


# ─── Ad Copy Prompt ──────────────────────────────────────────────────────────

AD_COPY_SYSTEM_PROMPT = """You are an expert digital marketing copywriter with 15 years of experience.
You write highly converting, platform-specific ad copy that is engaging, clear, and persuasive.
Always return valid JSON only — no markdown fences, no extra text."""

def build_ad_copy_prompt(
    product_name: str,
    description: str,
    offer: str,
    target_audience: str,
    campaign_goal: str,
    platforms: list[str],
    tone: str = "professional",
) -> str:
    return f"""Create compelling ad copy for the following product:

Product: {product_name}
Description: {description}
Offer: {offer}
Target Audience: {target_audience}
Campaign Goal: {campaign_goal}
Tone: {tone}

Generate copy for these platforms: {', '.join(platforms)}

Return a JSON object with this exact structure:
{{
  "instagram": {{
    "headline": "...",
    "body": "...",
    "cta_variants": ["...", "...", "..."],
    "hashtags": ["...", "...", "..."]
  }},
  "facebook": {{
    "headline": "...",
    "body": "...",
    "cta_variants": ["...", "...", "..."],
    "hashtags": []
  }},
  "linkedin": {{
    "headline": "...",
    "body": "...",
    "cta_variants": ["...", "...", "..."],
    "hashtags": ["...", "...", "..."]
  }},
  "twitter": {{
    "headline": null,
    "body": "...",
    "cta_variants": ["...", "..."],
    "hashtags": ["...", "...", "..."]
  }},
  "email": {{
    "headline": "Subject line here",
    "body": "Full email body here...",
    "cta_variants": ["...", "..."],
    "hashtags": []
  }}
}}

Only include platforms from the requested list: {', '.join(platforms)}.
Make each platform version feel native to that platform."""


# ─── Vision Evaluation Prompt ────────────────────────────────────────────────

VISION_EVALUATION_SYSTEM_PROMPT = """You are an expert UI/UX designer and marketing creative director.
Evaluate marketing posters with deep expertise in visual hierarchy, branding, and advertising effectiveness.
Always return valid JSON only."""

VISION_EVALUATION_USER_PROMPT = """Evaluate this marketing poster on the following criteria.
Score each dimension from 0-100. Be critical and specific.

Return ONLY this JSON structure (no markdown, no extra text):
{
  "overall_score": <0-100>,
  "dimensions": {
    "readability": <0-100>,
    "layout": <0-100>,
    "branding": <0-100>,
    "contrast": <0-100>,
    "cta_visibility": <0-100>,
    "visual_appeal": <0-100>
  },
  "strengths": ["...", "...", "..."],
  "weaknesses": ["...", "...", "..."],
  "suggestions": ["...", "...", "..."],
  "verdict": "excellent|good|needs_improvement|poor"
}"""


# ─── Optimization Prompt ─────────────────────────────────────────────────────

OPTIMIZATION_SYSTEM_PROMPT = """You are a senior digital marketing strategist.
Analyze campaign data and recommend the optimal platform, timing, and budget.
Return valid JSON only."""

def build_optimization_prompt(
    campaign_goal: str,
    target_audience: str,
    platform_history: dict,
    budget: Optional[float],
) -> str:
    return f"""Recommend campaign optimization strategy:

Campaign Goal: {campaign_goal}
Target Audience: {target_audience}
Budget: {budget or 'Not specified'}
Historical Platform Performance: {platform_history}

Return ONLY this JSON:
{{
  "recommended_platform": "instagram|facebook|linkedin|twitter",
  "recommended_time": "HH:MM in target timezone, e.g. 09:00",
  "recommended_budget": <float or null>,
  "confidence": <0.0-1.0>,
  "reasoning": "...",
  "platform_scores": {{
    "instagram": <0-100>,
    "facebook": <0-100>,
    "linkedin": <0-100>,
    "twitter": <0-100>
  }}
}}"""
