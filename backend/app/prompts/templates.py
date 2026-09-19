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
    "subheadline": 10,
    "label":       3,
    "value":       2,
    "why_item":    4,
    "why_title":   4,
    "offer":       6,
}

FEATURE_COUNT  = 4
WHY_ITEM_COUNT = 4

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


# ─── Gemini Full-Poster Prompt ───────────────────────────────────────────────
#
# Fundamentally different from the SDXL prompt in poster_generator. That one
# describes a *scene* and must contain no text, because SDXL cannot render
# legible letters — the composer typesets everything afterwards. Gemini renders
# text inside the image, so this prompt names the exact strings to draw and
# describes a layout, not a photograph. No composer runs on this path.


def build_gemini_poster_prompt(
    spec:             dict,
    brand_name:       str,
    platform:         str,
    aspect_ratio:     str,
    goal_visual_hint: str,
    variation_style:  str,
    language:         str = "en",
    brand_color_hex:  Optional[str] = None,
    feedback:         str = "",
) -> str:
    """
    Build the full-poster prompt from a normalized brochure spec.

    `spec` is the output of normalize_brochure_spec() — already word-budgeted,
    already bilingual, already carrying the human-authored CTA. Every string
    the model must render is quoted verbatim here so it copies rather than
    invents: a generative model asked to "add a headline" writes its own, and
    it will not match the campaign.
    """
    lang_name = LANGUAGE_NAMES.get(language, LANGUAGE_NAMES["en"])
    headline  = spec.get("headline_en", "")
    subhead   = spec.get("subheadline_en", "")
    offer     = spec.get("offer_en", "")
    cta       = spec.get("cta", "")

    # Second-language lines are only requested when they differ from English;
    # for an English campaign the normalizer mirrors *_en into *_local, and
    # asking for a "translation" of identical text just duplicates every line.
    bilingual_block = ""
    if language != "en":
        pairs = [
            ("Headline", spec.get("headline_local", "")),
            ("Offer",    spec.get("offer_local", "")),
        ]
        rendered = "\n".join(
            f'    {label} in {lang_name}: "{value}"' for label, value in pairs if value
        )
        if rendered:
            bilingual_block = (
                f"\nBilingual requirement — render these {lang_name} lines beneath their\n"
                f"English counterparts, in correct {lang_name} script, spelled exactly as given:\n"
                f"{rendered}\n"
            )

    features = spec.get("features") or []
    feature_block = "\n".join(
        f'    - "{f.get("value", "")}" — {f.get("label_en", "")}'
        for f in features[:FEATURE_COUNT]
        if f.get("label_en")
    )

    color_line = (
        f"  Brand colour:    {brand_color_hex} (use as the dominant accent)"
        if brand_color_hex else
        "  Brand colour:    choose a confident palette that suits the product"
    )

    feedback_block = ""
    if feedback:
        feedback_block = (
            f"\nThe previous attempt was judged weak for these reasons. Fix them:\n"
            f"{feedback}\n"
        )

    return f"""Design a finished, production-ready {platform} marketing poster in {aspect_ratio} aspect ratio.
{feedback_block}
Render ALL of the following text INTO the image, spelled exactly as written —
do not paraphrase, do not invent additional copy, do not leave placeholder text:

  Brand name:      "{brand_name}"
  Headline:        "{headline}"
  Subheadline:     "{subhead}"
  Offer:           "{offer}"
  Call to action:  "{cta}" (inside a clearly visible button)
{bilingual_block}
Supporting feature callouts (small, secondary, must not compete with the headline):
{feature_block or "    (none)"}

Design direction:
  Mood / strategy: {goal_visual_hint}
  Visual style:    {variation_style}
{color_line}

Layout requirements:
  - A real graphic-design layout with clear visual hierarchy and structured
    zones — NOT a stock photograph with text laid over it.
  - The brand name sits in a header area; the headline dominates; the offer is
    the most eye-catching element after it; the CTA button anchors the lower third.
  - Keep all text inside a safe margin; nothing clipped by the edges.
  - Every letter must be crisp, correctly spelled and legible at thumbnail size.
  - Leave generous negative space. Do not fill every corner.

Do not include: lorem ipsum, watermarks, signatures, garbled or misspelled text,
duplicated headlines, or any text beyond what is listed above."""


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
    if isinstance(value, (list, tuple)):
        value = " ".join(str(v) for v in value)
    text = " ".join(str(value).split())          # collapse newlines/runs of spaces
    words = text.split(" ")
    if len(words) > budget:
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
    """Deterministic copy built from campaign fields, used when the model gives nothing."""
    b       = BROCHURE_WORD_BUDGETS
    product = _as_text(ctx.get("product_name", "Our Product"), b["headline"])
    offer   = _as_text(ctx.get("offer", ""), b["offer"])
    return {
        "headline_en": product,
        "subheadline_en": _as_text(ctx.get("campaign_name", ""), b["subheadline"]),
        "features": [
            {"label_en": "Trusted Quality",  "value": "ASSURED"},
            {"label_en": "Great Value",      "value": "BEST PRICE"},
            {"label_en": "Wide Range",       "value": "IN STOCK"},
            {"label_en": "Expert Support",   "value": "ON CALL"},
        ],
        "why_title_en": f"Why {product}?",
        "why_items_en": ["Trusted brand", "Great value", "Wide choice", "Expert help"],
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
                                              ctx.get("offer", ""))

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
