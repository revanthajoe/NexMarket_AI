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
        0: "vibrant saffron-gold-teal palette, bold Devanagari-inspired typography, modern Indian design",
        1: "minimalist, clean, professional, royal blue and white, contemporary Indian branding",
        2: "premium dark luxury, gold accents, elegant rangoli-inspired patterns, festive Indian aesthetics",
        3: "playful, colorful, energetic, bright marigold and magenta tones, celebratory Indian vibe",
    }
    variation_style = style_map.get(variation, "vibrant, bold, modern Indian design")
    brand_note = f", {brand_style} brand identity" if brand_style else ""

    return (
        f"Create a professional Indian marketing poster for '{product_name}'. "
        f"Offer: {offer}. Target audience: {target_audience}. "
        f"Campaign goal: {campaign_goal}. "
        f"Style: {variation_style}{brand_note}. "
        f"Design for the Indian market — use culturally relevant aesthetics, "
        f"warm and inviting colour palette, and Indian digital advertising style. "
        f"Include a clear CTA button, product name in bold, offer text prominently displayed, "
        f"and a visually striking background. High quality, 1024x1024."
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
    language: str = "en",
) -> str:
    # `language` is a 2-letter code ("ta", "hi", ...) from the dropdown, not a
    # word the model understands — telling it to 'write in "ta"' is
    # meaningless, and it silently defaulted to English. LANGUAGE_NAMES (below,
    # already used by build_brochure_prompt for the same reason) maps the code
    # to a real language name first.
    lang_name = LANGUAGE_NAMES.get(language, LANGUAGE_NAMES["en"])
    return f"""Create compelling ad copy for the following product:

Product: {product_name}
Description: {description}
Offer: {offer}
Target Audience: {target_audience}
Campaign Goal: {campaign_goal}
Tone: {tone}
Language: write ALL headline, body, cta_variants and hashtags text in {lang_name}.

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
  "telegram": {{
    "headline": null,
    "body": "...",
    "cta_variants": ["...", "..."],
    "hashtags": []
  }},
  "whatsapp": {{
    "headline": null,
    "body": "...",
    "cta_variants": ["...", "..."],
    "hashtags": []
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
Compare the poster STRICTLY against the provided campaign context to detect semantic mismatches.
Always return valid JSON only."""


def build_vision_evaluation_prompt(context: str = "") -> str:
    context_block = f"\nCampaign Context:\n{context}\n" if context else ""
    return f"""Evaluate this marketing poster against the campaign context below.
Score each dimension from 0-100. Be critical and specific.
Detect any semantic mismatches (e.g., wrong product category, wrong theme, wrong audience).
{context_block}
Return ONLY this JSON structure (no markdown, no extra text):
{{
  "overall_score": <0-100>,
  "dimensions": {{
        "product_relevance": <0-100>,
        "campaign_relevance": <0-100>,
        "audience_relevance": <0-100>,
        "visual_quality": <0-100>,
        "composition_quality": <0-100>,
        "marketing_quality": <0-100>,
    "readability": <0-100>,
    "layout": <0-100>,
    "branding": <0-100>,
    "contrast": <0-100>,
    "cta_visibility": <0-100>,
    "visual_appeal": <0-100>
  }},
  "strengths": ["...", "...", "..."],
  "weaknesses": ["...", "...", "..."],
  "suggestions": ["...", "...", "..."],
    "generic_template_detected": false,
    "duplicate_content_detected": false,
    "issues": [],
    "recommendations": [],
  "detected_mismatch": [],
  "verdict": "excellent|good|needs_improvement|poor"
}}"""


# Keep the static version as a fallback constant
VISION_EVALUATION_USER_PROMPT = build_vision_evaluation_prompt()


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
  "recommended_platform": "instagram|facebook|telegram|whatsapp",
  "recommended_time": "HH:MM in target timezone, e.g. 09:00",
  "recommended_budget": <float or null>,
  "confidence": <0.0-1.0>,
  "reasoning": "...",
  "platform_scores": {{
    "instagram": <0-100>,
    "facebook": <0-100>,
    "telegram": <0-100>,
    "whatsapp": <0-100>
  }}
}}"""


# ─── Brochure Copy Prompt ────────────────────────────────────────────────────
#
# Distinct from the SDXL "visual spec" prompt in poster_generator: that one
# describes a *scene* for the diffusion model, this one writes the *copy* that
# the brochure layout engine typesets. SDXL never draws any of this text.
#
# The second language is keyed `_local` rather than `_ta` so the schema works
# for every language the CTA table supports, not just Tamil.

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "es": "Spanish",
    "fr": "French",
}

# Per-field word budgets. The prompt states these so the model aims for them,
# and normalize_brochure_spec() clamps to them so a model that ignores the
# instruction still cannot overflow its layout zone.
BROCHURE_WORD_BUDGETS = {
    "headline":    6,
    "subheadline": 15,
    "label":       5,
    "value":       5,
    "why_item":    8,
    "why_title":   8,
    "offer":       12,
}

FEATURE_COUNT  = 4
WHY_ITEM_COUNT = 4

VISUAL_LAYOUT_TYPES = (
    "hero_offer",
    "product_focus",
    "split_visual",
    "centered_product",
    "lifestyle_scene",
    "minimal_offer",
)

VISUAL_DESIGN_SPEC_SYSTEM_PROMPT = """You are a senior advertising art director.
Convert arbitrary campaign information into a domain-neutral visual design specification.
Return valid JSON only. Never invent product claims, prices, discounts, features, or brand promises.
The image will be used as visual background art; exact campaign text, offer, CTA, and logo are rendered separately."""


def build_visual_design_prompt(
    product_name: str,
    description: str,
    offer: str,
    target_audience: str,
    campaign_goal: str,
    platform: str,
    aspect_ratio: str,
    brand_style: str = "",
    feedback: str = "",
) -> str:
    feedback_block = f"\nPrevious evaluator feedback to fix:\n{feedback}\n" if feedback else ""
    return f"""Create a visual design specification for this campaign.{feedback_block}

Campaign:
  Product or service: {product_name}
  Description: {description}
  Offer: {offer}
  Target audience: {target_audience}
  Campaign goal: {campaign_goal}
  Platform: {platform}
  Aspect ratio: {aspect_ratio}
  Brand style: {brand_style or 'not specified'}

Priorities, in order:
1. Represent the actual product or service accurately.
2. Make the campaign goal and audience visible through the scene.
3. Use only relevant objects, people, and environments implied by the campaign.
4. Leave clear text-safe areas for deterministic poster composition.
5. Avoid generic website or brochure-template composition.

Return exactly these JSON fields:
{{
  "product": "{product_name}",
  "product_category": "specific category inferred from the description",
  "campaign_goal": "{campaign_goal}",
  "target_audience": "{target_audience}",
  "visual_concept": "one concise campaign-specific scene concept",
  "primary_subjects": ["relevant subject"],
  "secondary_elements": ["relevant supporting element"],
  "environment": "relevant setting",
  "audience_context": "how the audience appears or interacts with the scene",
  "mood": "emotional direction",
  "style": "advertising visual style",
  "color_direction": "colour direction",
  "lighting": "lighting direction",
  "composition": "compositional structure",
  "camera_perspective": "camera or viewpoint",
  "required_visual_elements": ["required relevant element"],
  "avoid_visual_elements": ["website sections", "generic feature grids", "duplicate headings", "unrelated objects"],
  "text_safe_areas": ["top margin", "lower third"],
  "layout_type": "one of: {', '.join(VISUAL_LAYOUT_TYPES)}",
  "visual_position": "where the visual subject belongs",
  "text_position": "where deterministic text belongs",
  "offer_position": "where the exact offer belongs",
  "cta_position": "where the CTA belongs",
  "logo_position": "where an optional logo belongs"
}}"""


def _spec_text(value, fallback: str = "", limit: int = 24) -> str:
    text = " ".join(str(value or fallback).split())
    return " ".join(text.split()[:limit])


def _spec_list(value, fallback: list[str], limit: int = 6) -> list[str]:
    values = value if isinstance(value, list) else fallback
    return [_spec_text(item, limit=12) for item in values if _spec_text(item, limit=12)][:limit] or fallback


def _fallback_visual_design_spec(ctx: dict) -> dict:
    goal = _spec_text(ctx.get("campaign_goal"), "brand awareness")
    goal_lower = goal.lower()
    if any(word in goal_lower for word in ("sales", "conversion", "offer", "promotion")):
        layout = "hero_offer"
    elif any(word in goal_lower for word in ("awareness", "engagement", "launch")):
        layout = "lifestyle_scene"
    elif any(word in goal_lower for word in ("lead", "traffic", "download")):
        layout = "split_visual"
    else:
        layout = "product_focus"
    product = _spec_text(ctx.get("product_name"), "product or service")
    return {
        "product": product,
        "product_category": "campaign-relevant product or service",
        "campaign_goal": goal,
        "target_audience": _spec_text(ctx.get("target_audience"), "intended audience"),
        "visual_concept": f"Campaign-specific visual featuring {product} in a relevant context",
        "primary_subjects": [product],
        "secondary_elements": [],
        "environment": "clean campaign-relevant environment",
        "audience_context": "audience context implied by the campaign description",
        "mood": "clear and confident",
        "style": "contemporary advertising photography",
        "color_direction": "brand-led contrasting palette",
        "lighting": "clean directional light",
        "composition": "clear subject with generous negative space",
        "camera_perspective": "eye-level three-quarter view",
        "required_visual_elements": [product],
        "avoid_visual_elements": ["website sections", "generic feature grids", "duplicate headings", "unrelated objects"],
        "text_safe_areas": ["top margin", "lower third"],
        "layout_type": layout,
        "visual_position": "prominent subject area",
        "text_position": "top margin or open side area",
        "offer_position": "high-contrast lower band",
        "cta_position": "lower edge within safe margin",
        "logo_position": "top corner within safe margin",
        "fallback": True,
    }


def normalize_visual_design_spec(raw, ctx: dict) -> dict:
    """Normalize model output into the domain-neutral design contract."""
    spec = raw if isinstance(raw, dict) and raw else _fallback_visual_design_spec(ctx)
    fallback = not isinstance(raw, dict) or not raw
    result = _fallback_visual_design_spec(ctx)
    scalar_fields = (
        "product", "product_category", "campaign_goal", "target_audience",
        "visual_concept", "environment", "audience_context", "mood", "style",
        "color_direction", "lighting", "composition", "camera_perspective",
        "visual_position", "text_position", "offer_position", "cta_position", "logo_position",
    )
    for field in scalar_fields:
        result[field] = _spec_text(spec.get(field), result[field])
    for field in ("primary_subjects", "secondary_elements", "required_visual_elements", "avoid_visual_elements", "text_safe_areas"):
        result[field] = _spec_list(spec.get(field), result[field])
    layout = _spec_text(spec.get("layout_type"), result["layout_type"], limit=2)
    result["layout_type"] = layout if layout in VISUAL_LAYOUT_TYPES else result["layout_type"]
    result["fallback"] = fallback
    return result


def build_visual_image_prompt(
    spec: dict,
    platform: str,
    aspect_ratio: str,
    brand_style: str = "",
) -> str:
    """Render a visual-only prompt from the normalized design specification."""
    subjects = ", ".join(spec.get("primary_subjects", []))
    secondary = ", ".join(spec.get("secondary_elements", []))
    required = ", ".join(spec.get("required_visual_elements", []))
    avoid = ", ".join(spec.get("avoid_visual_elements", []))
    safe_areas = ", ".join(spec.get("text_safe_areas", []))
    return f"""Create visual background art for a {platform} advertising poster in {aspect_ratio} aspect ratio.
Product or service: {spec.get('product', '')}
Category: {spec.get('product_category', '')}
Campaign goal: {spec.get('campaign_goal', '')}
Target audience: {spec.get('target_audience', '')}
Visual concept: {spec.get('visual_concept', '')}
Primary subjects: {subjects}
Secondary elements: {secondary}
Environment: {spec.get('environment', '')}
Audience context: {spec.get('audience_context', '')}
Mood: {spec.get('mood', '')}
Advertising style: {spec.get('style', '')}
Colour direction: {spec.get('color_direction', '')}
Lighting: {spec.get('lighting', '')}
Composition: {spec.get('composition', '')}
Camera perspective: {spec.get('camera_perspective', '')}
Required visual elements: {required}
Brand style: {brand_style or 'not specified'}
Leave clear negative space for typeset copy in: {safe_areas}

This is visual scene art only. Do not render text, offer wording, CTA labels, logos, website sections,
feature grids, trust badges, duplicate headings, UI panels, unrelated icons, watermarks, or unrelated objects.
Keep the product/service and audience context visually relevant, with a clean advertising composition."""


def normalize_offer_text(offer: str) -> str:
    """Make common percentage offers compact and poster-friendly."""
    text = " ".join(str(offer or "").split())
    text = text.replace("upto", "up to").replace("UPTO", "UP TO")
    import re
    text = re.sub(r"(\d+)\s*%\s*(?:offer|off)", r"\1% OFF", text, flags=re.IGNORECASE)
    return text.upper() if text else ""

BROCHURE_SYSTEM_PROMPT = """You are a senior bilingual advertising copywriter for Indian retail brands.
You write short, punchy product-brochure copy that fits fixed layout zones.
You never exceed the stated word limits. You always return valid JSON only — no markdown fences, no commentary."""


def build_brochure_prompt(
    product_name: str,
    campaign_name: str,
    description: str,
    offer: str,
    target_audience: str,
    campaign_goal: str,
    language: str = "en",
    brand_name: str = "",
) -> str:
    """Build the user prompt for bilingual brochure copy (English + one local language)."""
    lang_name = LANGUAGE_NAMES.get(language, LANGUAGE_NAMES["en"])
    b = BROCHURE_WORD_BUDGETS

    # An English-only campaign still uses the same schema; the model is told to
    # mirror English into `_local` so downstream layout code needs no branching.
    if language == "en" or language not in LANGUAGE_NAMES:
        local_rule = (
            "This campaign is English-only: copy each English value verbatim into "
            "its matching *_local field."
        )
    else:
        local_rule = (
            f"Every *_local field must be written in {lang_name} script — a real "
            f"translation of its English counterpart, not transliteration, and not English."
        )

    # Brand and product names are proper nouns. Without this the 3B model
    # cheerfully "translates" them — "Birla Opus Paints" came back as
    # "பிறந்த உபோஸ பின்னர்" ("born ... afterwards"), which shipped onto a real
    # poster as the headline. A brand name must survive verbatim in both
    # languages or the poster is advertising something that does not exist.
    proper_noun_rule = (
        f'NEVER translate or transliterate the brand or product name. '
        f'"{brand_name or product_name}" and "{product_name}" must appear EXACTLY '
        f'as written, in Latin script, in every field of both languages.'
    )

    return f"""Write product-brochure copy for the campaign below.

Campaign Context:
  Brand:           {brand_name or product_name}
  Product:         {product_name}
  Campaign:        {campaign_name}
  Description:     {description}
  Offer:           {offer}
  Target Audience: {target_audience}
  Goal:            {campaign_goal}
  Second language: {lang_name}

Rules:
  - {local_rule}
  - {proper_noun_rule}
  - The headline must be a benefit or a hook, NOT the brand name — the brand name
    is already displayed separately in the poster's header.
  - Provide EXACTLY {FEATURE_COUNT} features and EXACTLY {WHY_ITEM_COUNT} "why" items.
  - Each feature needs a short `value` ({b['value']} words max) such as "14 YEAR",
    "12 C COOLER" or "100% SAFE" — a concrete, scannable spec, not a sentence.
  - Word limits, strictly enforced: headline {b['headline']}, subheadline
    {b['subheadline']}, feature label {b['label']}, feature value {b['value']},
    why item {b['why_item']}, why title {b['why_title']}, offer {b['offer']}.
  - Do not invent facts that contradict the description. Do not add a call-to-action;
    it is supplied separately.

Return ONLY this JSON structure:
{{
  "headline_en": "...",        "headline_local": "...",
  "subheadline_en": "...",     "subheadline_local": "...",
  "features": [
    {{"label_en": "...", "label_local": "...", "value": "..."}},
    {{"label_en": "...", "label_local": "...", "value": "..."}},
    {{"label_en": "...", "label_local": "...", "value": "..."}},
    {{"label_en": "...", "label_local": "...", "value": "..."}}
  ],
  "why_title_en": "...",       "why_title_local": "...",
  "why_items_en": ["...", "...", "...", "..."],
  "why_items_local": ["...", "...", "...", "..."],
  "offer_en": "...",           "offer_local": "..."
}}"""


# ── Normalization ────────────────────────────────────────────────────────────
#
# The layout engine draws exactly FEATURE_COUNT badges and WHY_ITEM_COUNT list
# items, so it needs shape guarantees. A 4-bit 3B model does not reliably give
# them: it drops keys, returns 3 or 7 features, emits a string where a list was
# asked for, or silently omits the second language. Everything below coerces
# whatever came back into the exact contract.


def _as_text(value, budget: int) -> str:
    """Coerce any JSON value to a clean single-line string within `budget` words."""
    if value is None:
        return ""
    if budget is not None and budget <= 0:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(v) for v in value)
    text = " ".join(str(value).split())
    words = text.split()
    if budget is not None and len(words) > budget:
        text = " ".join(words[:budget])
    return text.strip()


def _pair(raw: dict, key: str, budget: int, fallback: str = "") -> tuple[str, str]:
    """
    Resolve an `<key>_en` / `<key>_local` pair.

    A missing or empty `_local` falls back to the English string rather than
    staying empty: showing English twice is a far better failure than leaving a
    blank hole in the rendered layout.
    """
    en    = _as_text(raw.get(f"{key}_en"), budget) or _as_text(fallback, budget)
    local = _as_text(raw.get(f"{key}_local"), budget) or en
    return en, local


def _fallback_spec(ctx: dict) -> dict:
    """Deterministic copy built only from supplied campaign fields."""
    b       = BROCHURE_WORD_BUDGETS
    product = _as_text(ctx.get("product_name", "Our Product"), b["headline"])
    description = _as_text(ctx.get("description", ""), b["subheadline"])
    audience = _as_text(ctx.get("target_audience", ""), b["why_item"]) or "your audience"
    offer   = _as_text(normalize_offer_text(ctx.get("offer", "")), b["offer"])
    features = [
        {"label_en": product, "value": "FEATURE"},
        {"label_en": "Campaign offer", "value": offer or "OFFER"},
        {"label_en": "For the audience", "value": audience},
        {"label_en": "Discover more", "value": "CTA"},
    ]
    return {
        "headline_en": description or _as_text(ctx.get("campaign_name", ""), b["headline"]) or product,
        "subheadline_en": description or _as_text(ctx.get("campaign_name", ""), b["subheadline"]),
        "features": features,
        "why_title_en": f"Why {product}?",
        "why_items_en": [product, offer or "Campaign offer", audience, "Learn more"],
        "offer_en": offer,
    }


def normalize_brochure_spec(raw, ctx: Optional[dict] = None) -> dict:
    """
    Coerce a raw LLM response into the exact brochure spec contract.

    Guarantees: every `*_en`/`*_local` pair is a non-empty string, `features` has
    exactly FEATURE_COUNT entries, and `why_items_*` have exactly WHY_ITEM_COUNT.

    `fallback: True` marks output that came from `_fallback_spec` rather than the
    model — the same convention poster_evaluator uses, so a broken generation is
    visible instead of masquerading as real copy.
    """
    ctx = ctx or {}
    b   = BROCHURE_WORD_BUDGETS

    used_fallback = not isinstance(raw, dict) or not raw
    if used_fallback:
        raw = _fallback_spec(ctx)

    headline_en,    headline_local    = _pair(raw, "headline",    b["headline"],
                                              ctx.get("product_name", ""))
    subheadline_en, subheadline_local = _pair(raw, "subheadline", b["subheadline"],
                                              ctx.get("campaign_name", ""))
    why_title_en,   why_title_local   = _pair(raw, "why_title",   b["why_title"], "Why choose us?")
    offer_en,       offer_local       = _pair(raw, "offer",       b["offer"],
                                              normalize_offer_text(ctx.get("offer", "")))

    # A headline is the one field with no acceptable empty state.
    if not headline_en:
        headline_en = headline_local = _as_text(
            ctx.get("product_name", "Our Product"), b["headline"]
        )
        used_fallback = True

    # ── Features: force exactly FEATURE_COUNT well-formed entries ─────────────
    raw_features = raw.get("features")
    if not isinstance(raw_features, list):
        raw_features = []

    features: list[dict] = []
    for item in raw_features[:FEATURE_COUNT]:
        if not isinstance(item, dict):
            continue
        label_en    = _as_text(item.get("label_en"), b["label"])
        label_local = _as_text(item.get("label_local"), b["label"]) or label_en
        value       = _as_text(item.get("value"), b["value"])
        if not label_en:
            continue
        features.append({"label_en": label_en, "label_local": label_local, "value": value})

    if len(features) < FEATURE_COUNT:
        used_fallback = True
        for filler in _fallback_spec(ctx)["features"]:
            if len(features) >= FEATURE_COUNT:
                break
            features.append({
                "label_en":    filler["label_en"],
                "label_local": filler["label_en"],
                "value":       filler["value"],
            })

    # ── Why items: exactly WHY_ITEM_COUNT, both languages ────────────────────
    def _items(key: str) -> list[str]:
        value = raw.get(key)
        if isinstance(value, str):          # model returned a sentence, not a list
            value = [p for p in value.replace("|", ",").split(",") if p.strip()]
        if not isinstance(value, list):
            return []
        return [t for t in (_as_text(v, b["why_item"]) for v in value) if t]

    why_en    = _items("why_items_en")
    why_local = _items("why_items_local")

    if len(why_en) < WHY_ITEM_COUNT:
        why_en += [
            t for t in _fallback_spec(ctx)["why_items_en"] if t not in why_en
        ][: WHY_ITEM_COUNT - len(why_en)]
    why_en = why_en[:WHY_ITEM_COUNT]

    # Pad the local list from English positionally so the two stay aligned.
    why_local = (why_local + why_en[len(why_local):])[:WHY_ITEM_COUNT]

    if normalize_offer_text(ctx.get("offer", "")) and offer_en == _as_text(ctx.get("offer", ""), b["offer"]):
        offer_en = offer_local = normalize_offer_text(ctx["offer"])

    headline_en = _as_text(headline_en, b["headline"])
    headline_local = _as_text(headline_local, b["headline"])
    subheadline_en = _as_text(subheadline_en, b["subheadline"])
    subheadline_local = _as_text(subheadline_local, b["subheadline"])
    why_title_en = _as_text(why_title_en, b["why_title"])
    why_title_local = _as_text(why_title_local, b["why_title"])
    offer_en = _as_text(offer_en, b["offer"])
    offer_local = _as_text(offer_local, b["offer"])
    for feature in features:
        feature["label_en"] = _as_text(feature.get("label_en", ""), b["label"])
        feature["label_local"] = _as_text(feature.get("label_local", feature.get("label_en", "")), b["label"])
        feature["value"] = _as_text(feature.get("value", ""), b["value"])
    why_en = [_as_text(item, b["why_item"]) for item in why_en]
    why_local = [_as_text(item, b["why_item"]) for item in why_local]
    why_en = [item for item in why_en if item][:WHY_ITEM_COUNT]
    why_local = [item for item in why_local if item][:WHY_ITEM_COUNT]

    return {
        "language":           ctx.get("language", "en"),
        "headline_en":        headline_en,
        "headline_local":     headline_local,
        "subheadline_en":     subheadline_en,
        "subheadline_local":  subheadline_local,
        "features":           features[:FEATURE_COUNT],
        "why_title_en":       why_title_en,
        "why_title_local":    why_title_local,
        "why_items_en":       why_en,
        "why_items_local":    why_local,
        "offer_en":           offer_en,
        "offer_local":        offer_local,
        "fallback":           used_fallback,
    }
