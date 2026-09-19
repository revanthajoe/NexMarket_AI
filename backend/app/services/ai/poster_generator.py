"""
app/services/ai/poster_generator.py
─────────────────────────────────────────────────────────────────────────────
Context-Aware Multi-Stage Marketing Poster Generator

Pipeline (per variation):
  1. Build campaign context + load brand kit
  2. Qwen2.5-3B  → Structured Visual Design Specification (strict JSON)
  3. SDXL        → Text-free visual asset (platform-correct aspect ratio)
  4. PosterComposer → Real logo/fonts/brand-colour/product-cutout overlaid
  5. Qwen2.5-VL  → Contextual evaluation (score 0-100)
  6. If score < threshold: use evaluator feedback to improve spec → repeat

Improvements vs previous version:
  • Context-prioritised prompting for 8 campaign goal types
  • Variation-seeded style variance (no two identical outputs)
  • Language-aware CTA text
  • Brand kit (logo + custom fonts + brand colour + product image) injected
  • Platform-specific SDXL resolution via PosterFormat
  • Improved Qwen VL evaluation includes full campaign context
  • SDXL negative prompt is campaign-derived (not hardcoded)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.services.ai.brand_kit import get_brand_kit
from app.services.ai.platform_formats import get_format

logger = get_logger(__name__)

_UPLOAD = Path(settings.POSTER_UPLOAD_DIR)
_UPLOAD.mkdir(parents=True, exist_ok=True)


# ── Language-aware CTA strings ──────────────────────────────────────────────

_CTA_MAP: dict[str, dict[str, str]] = {
    "en": {"buy": "SHOP NOW",   "learn": "LEARN MORE",  "offer": "GRAB OFFER", "default": "DISCOVER"},
    "hi": {"buy": "अभी खरीदें", "learn": "और जानें",    "offer": "ऑफर लें",    "default": "जानिए"},
    "ta": {"buy": "இப்போது வாங்கு", "learn": "மேலும் அறி", "offer": "சலுகை பெறு", "default": "கண்டறி"},
    "te": {"buy": "ఇప్పుడు కొనండి", "learn": "మరింత తెలుసుకోండి", "offer": "ఆఫర్ పొందండి", "default": "అన్వేషించండి"},
    "mr": {"buy": "आता खरेदी करा", "learn": "अधिक जाणा", "offer": "ऑफर मिळवा", "default": "शोधा"},
    "es": {"buy": "COMPRA YA",  "learn": "MÁS INFO",   "offer": "OBTENER OFERTA", "default": "DESCUBRIR"},
    "fr": {"buy": "ACHETER",    "learn": "EN SAVOIR +", "offer": "SAISIR L'OFFRE", "default": "DÉCOUVRIR"},
}


def _get_cta(language: str, campaign_goal: str, offer: str) -> str:
    lang_ctas = _CTA_MAP.get(language, _CTA_MAP["en"])
    goal_l = campaign_goal.lower()
    offer_l = offer.lower()
    if any(w in goal_l for w in ("sales", "revenue", "purchase", "conversion")):
        return lang_ctas["buy"]
    if any(w in goal_l for w in ("awareness", "education", "launch", "inform")):
        return lang_ctas["learn"]
    if any(w in offer_l for w in ("free", "off", "%", "discount", "sale")):
        return lang_ctas["offer"]
    return lang_ctas["default"]


# ── Goal-specific visual guidance ────────────────────────────────────────────

_GOAL_VISUAL_HINTS: dict[str, str] = {
    "brand awareness":    "Wide-shot aspirational lifestyle, strong brand identity, clean composition",
    "product launch":     "Hero product close-up, innovation atmosphere, dramatic lighting, launch energy",
    "sales":              "Dynamic promotional feel, urgency, product prominence, vibrant energy",
    "lead generation":    "Professional environment, call-to-action focus, trustworthy tone",
    "engagement":         "Vibrant, fun, shareable, bold colours, emotional connection",
    "education":          "Learning environment, professional students, clean structured layout",
    "retention":          "Warm, familiar brand feel, loyal customer lifestyle context",
    "event promotion":    "Festive atmosphere, celebratory lighting, event energy",
}


def _goal_hint(campaign_goal: str) -> str:
    for key, hint in _GOAL_VISUAL_HINTS.items():
        if key in campaign_goal.lower():
            return hint
    return "Professional marketing composition, product-hero focus"


# ── Variation-seed style phrases (prevents identical outputs) ────────────────

_VARIATION_STYLES = [
    "dramatic studio lighting, dark moody background",
    "bright natural light, outdoor lifestyle setting",
    "minimalist white-space composition, product-focus",
    "luxury premium aesthetic, gold and dark tones",
]


def _derive_seed(campaign_id: Optional[str], variation: int, attempt: int = 1) -> int:
    """
    Deterministic SDXL seed from (campaign_id, variation, attempt).

    Same campaign + variation + attempt always reproduces the same image;
    different variations/attempts still get distinct seeds. Falls back to a
    random component when no campaign_id is available (e.g. ad-hoc previews).
    """
    key = f"{campaign_id or uuid.uuid4().hex}:{variation}:{attempt}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


# ── Poster-phase LLM routing ─────────────────────────────────────────────────
#
# The poster phase runs on Gemini: Qwen2.5-3B at 4-bit cannot write usable Tamil
# (it rendered the brand name "Birla Opus Paints" as "பிறந்த உபோஸ் பின்னர்" —
# "Born Opus After" — and that shipped onto a real poster).
#
# Scoped via AI_TEXT_PROVIDER, which also governs ad copy. Sentiment,
# lead scoring and forecasting keep their local models; they route through
# different inference_manager methods and are untouched.


def _effective_score(eval_result: dict) -> float:
    """
    The score to make retry/approval decisions on.

    A failed evaluation returns `_FALLBACK_EVALUATION`, whose synthetic
    `overall_score` is 72.5 — *above* the 70 approval threshold. Taken at face
    value, an evaluator outage silently "approves" every poster on attempt 1 and
    the improvement retry never fires: the poster looks vetted when nothing
    actually looked at it. The `fallback` flag exists to catch exactly this, so
    treat a fallback as "unknown", never as a pass.
    """
    if eval_result.get("fallback"):
        return -1.0
    return float(eval_result.get("overall_score", 0) or 0)


# The provider switch now lives in text_provider.py, because ad copy routes
# through the same decision and importing a `poster_phase_json` into the ad
# generator would misdescribe what it does. Re-exported here under the old name
# so existing call sites and tests keep working.
from app.services.ai.text_provider import generate_marketing_json as poster_phase_json  # noqa: E402


# ── Brochure copy spec ───────────────────────────────────────────────────────

async def generate_brochure_spec(
    product_name:    str,
    campaign_name:   str,
    description:     str,
    offer:           str,
    target_audience: str,
    campaign_goal:   str,
    language:        str = "en",
    brand_name:      str = "",
) -> dict:
    """
    Produce the bilingual copy the brochure layout typesets.

    Separate from the SDXL visual spec: that describes a *scene* for the
    diffusion model, this is the *text* drawn on top of it. SDXL renders none
    of this.

    The CTA is deliberately not requested from the model — `_CTA_MAP` already
    holds human-authored translations for every supported language, which beats
    a 4-bit 3B model inventing them. It is attached here as `cta`.

    Always returns a valid spec: on model failure the normalizer substitutes
    deterministic copy and sets `fallback: True`.
    """
    from app.prompts.templates import (
        BROCHURE_SYSTEM_PROMPT,
        build_brochure_prompt,
        normalize_brochure_spec,
    )

    ctx = {
        "product_name":  product_name,
        "campaign_name": campaign_name,
        "offer":         offer,
        "language":      language,
    }

    raw = None
    try:
        raw = await poster_phase_json(
            BROCHURE_SYSTEM_PROMPT,
            build_brochure_prompt(
                product_name    = product_name,
                campaign_name   = campaign_name,
                description     = description,
                offer           = offer,
                target_audience = target_audience,
                campaign_goal   = campaign_goal,
                language        = language,
                brand_name      = brand_name,
            ),
        )
    except Exception as exc:
        logger.error("brochure_spec generation failed, using fallback copy: %s", exc)

    spec = normalize_brochure_spec(raw, ctx)
    spec["cta"] = _get_cta(language, campaign_goal, offer)

    if spec["fallback"]:
        logger.warning(
            "brochure_spec fallback=True product=%s language=%s - model output was "
            "unusable; copy is synthetic", product_name, language,
        )
    else:
        logger.info("brochure_spec ok product=%s language=%s", product_name, language)
    return spec


class PosterGeneratorService:

    async def generate(
        self,
        campaign_name:   str,
        product_name:    str,
        description:     str,
        offer:           str,
        target_audience: str,
        campaign_goal:   str,
        brand_style:     Optional[str] = None,
        variation:       int = 0,
        platform:        str = "instagram",
        campaign_id:     Optional[str] = None,
        seed:            Optional[int] = None,
        language:        Optional[str] = None,
    ) -> dict:
        from ai.imagegen.gemini_service import GeminiImageError

        logger.info("poster_generate variation=%d provider=%s platform=%s", variation, settings.IMAGE_PROVIDER, platform)

        if settings.IMAGE_PROVIDER == "local":
            return await self._generate_local(
                campaign_name, product_name, description, offer,
                target_audience, campaign_goal, brand_style or "",
                variation, platform, campaign_id, seed, language,
            )
        elif settings.IMAGE_PROVIDER == "gemini":
            try:
                return await self._generate_gemini(
                    campaign_name, product_name, description, offer,
                    target_audience, campaign_goal, brand_style or "",
                    variation, platform, campaign_id, seed, language,
                )
            except GeminiImageError as exc:
                # STOPGAP, not the design. The poster phase is meant to be
                # Gemini end to end; image generation needs billing enabled on
                # the Google Cloud project, and without it every image model
                # returns quota "limit: 0". Rather than 500, fall back to SDXL
                # so posters keep generating — the moment billing is switched
                # on this branch stops firing and the phase is pure Gemini with
                # no code change.
                #
                # Copy and evaluation still run on Gemini inside _generate_local
                # (AI_TEXT_PROVIDER), so only the pixels come from SDXL.
                logger.warning(
                    "poster_image_stopgap gemini image generation unavailable, rendering with "
                    "SDXL instead. This is a temporary fallback, not the configured design - "
                    "enable billing to restore Gemini image generation. Reason: %s", exc
                )
                result = await self._generate_local(
                    campaign_name, product_name, description, offer,
                    target_audience, campaign_goal, brand_style or "",
                    variation, platform, campaign_id, seed, language,
                )
                # Record the downgrade in the DB row rather than letting a
                # SDXL-rendered poster be assumed to be a Gemini one.
                result.setdefault("metadata_", {}).update({
                    "image_backend":          "sdxl-stopgap",
                    "image_backend_intended": "gemini",
                    "image_fallback_reason":  str(exc),
                })
                return result
        elif settings.IMAGE_PROVIDER == "openai":
            return await self._generate_openai("A placeholder prompt", product_name, variation)
        else:
            raise ValueError(f"Unsupported IMAGE_PROVIDER={settings.IMAGE_PROVIDER!r}")

    # ── Gemini full-poster pipeline ───────────────────────────────────────────

    async def _generate_gemini(
        self,
        campaign_name:   str,
        product_name:    str,
        description:     str,
        offer:           str,
        target_audience: str,
        campaign_goal:   str,
        brand_style:     str,
        variation:       int,
        platform:        str,
        campaign_id:     Optional[str],
        seed:            Optional[int] = None,
        language:        Optional[str] = None,
    ) -> dict:
        """
        Gemini renders the COMPLETE poster, text included.

        The composer stack (PosterComposer / BrochureComposer / text_shaper) is
        deliberately not used here — it exists to typeset text that SDXL cannot
        draw, and Gemini draws it. Everything else is shared with the local
        path: the same brand kit, the same platform formats, the same
        evaluate-and-retry loop.
        """
        from app.prompts.templates import build_gemini_poster_prompt
        from app.services.ai.poster_evaluator import poster_evaluator
        from ai.imagegen.gemini_service import gemini_image_service, GeminiImageError

        # Declared outside the try for the same reason as _generate_local: a
        # later attempt crashing must not discard a good poster an earlier one
        # already produced.
        best_result = None
        best_score  = -1

        try:
            kit      = get_brand_kit(campaign_id or "default")
            language = language or kit.language
            fmt      = get_format(platform)

            goal_visual_hint = _goal_hint(campaign_goal)
            variation_style  = _VARIATION_STYLES[variation % len(_VARIATION_STYLES)]

            # The copy Gemini must render. Reuses the phase-3 spec wholesale:
            # already word-budgeted per field, already bilingual, and the CTA is
            # the human-authored _CTA_MAP string rather than something a model
            # invented. Generated once, not per attempt — a retry is about the
            # *design* being weak, not the copy.
            spec = await generate_brochure_spec(
                product_name    = product_name,
                campaign_name   = campaign_name,
                description     = description,
                offer           = offer,
                target_audience = target_audience,
                campaign_goal   = campaign_goal,
                language        = language,
                brand_name      = product_name,
            )
            logger.info(
                "gemini_poster spec ready campaign_id=%s language=%s fallback=%s",
                campaign_id, language, spec.get("fallback"),
            )

            max_attempts = 2
            threshold    = 70.0
            feedback     = ""

            for attempt in range(1, max_attempts + 1):
                logger.info(
                    "gemini_poster attempt=%d/%d variation=%d", attempt, max_attempts, variation
                )

                prompt = build_gemini_poster_prompt(
                    spec             = spec,
                    brand_name       = product_name,
                    platform         = platform,
                    aspect_ratio     = fmt.aspect_ratio,
                    goal_visual_hint = goal_visual_hint,
                    variation_style  = variation_style,
                    language         = language,
                    brand_color_hex  = kit.brand_color_hex,
                    feedback         = feedback,
                )

                result = await gemini_image_service.generate(
                    prompt       = prompt,
                    product_name = product_name,
                    variation    = variation,
                    width        = fmt.width,
                    height       = fmt.height,
                    seed         = seed,
                )
                image_url = result["image_url"]
                fname     = image_url.split("/")[-1]

                eval_context = (
                    f"Campaign: {campaign_name} | Product: {product_name} | "
                    f"Goal: {campaign_goal} | Audience: {target_audience} | "
                    f"Offer: {offer} | Platform: {platform} | Language: {language}"
                )
                eval_result = await poster_evaluator.evaluate(
                    str(_UPLOAD / fname), context=eval_context
                )
                # A fallback evaluation must not count as a pass — see
                # _effective_score.
                score = _effective_score(eval_result)

                current_result = {
                    "image_url":       image_url,
                    "prompt_used":     prompt,
                    "provider":        "gemini-poster",
                    "variation_index": variation,
                    "metadata_": {
                        "visual_url":  image_url,
                        "evaluation":  eval_result,
                        "attempts":    attempt,
                        "platform":    platform,
                        "format":      f"{fmt.width}x{fmt.height}",
                        "language":    language,
                        # Echoed, not honoured: the Gemini image API takes no
                        # seed, so this does NOT reproduce the image.
                        "seed":        seed,
                        "layout":      "gemini",
                        "model":       settings.GEMINI_IMAGE_MODEL,
                        # Same convention as the local path — a synthetic spec
                        # must never masquerade as real copy in the DB record.
                        "brochure_spec": spec,
                    },
                }

                # `best_result is None` first: when every attempt's evaluation
                # falls back, each score is -1 and a bare `>` comparison would
                # never latch a result, returning None for a poster that was
                # actually rendered.
                if best_result is None or score > best_score:
                    best_score  = score
                    best_result = current_result

                if score >= threshold:
                    logger.info("gemini_poster approved score=%.1f attempt=%d", score, attempt)
                    break

                logger.info(
                    "gemini_poster score=%.1f < %.1f — retrying with evaluator feedback",
                    score, threshold,
                )
                feedback = (
                    f"  Weaknesses: {', '.join(eval_result.get('weaknesses', []))}\n"
                    f"  Suggestions: {', '.join(eval_result.get('suggestions', []))}"
                )

            return best_result

        except GeminiImageError:
            # Let this reach generate(), which falls back to SDXL. Wrapping it
            # in RuntimeError like the branch below would hide the one error
            # type the fallback keys off, turning a recoverable quota block
            # back into a 500.
            if best_result is not None:
                logger.warning(
                    "gemini_poster_degraded variation=%d score=%.1f — keeping earlier "
                    "attempt rather than falling back", variation, best_score,
                )
                return best_result
            raise

        except Exception as exc:
            logger.error("poster_generate_gemini_error variation=%d: %s", variation, exc, exc_info=True)
            if best_result is not None:
                logger.warning(
                    "gemini_poster_degraded variation=%d score=%.1f — returning earlier "
                    "successful attempt despite later failure: %s",
                    variation, best_score, exc,
                )
                return best_result
            raise RuntimeError(f"Poster generation failed for variation {variation}: {exc}") from exc

    # ── Local multi-stage pipeline ────────────────────────────────────────────

    async def _generate_local(
        self,
        campaign_name:   str,
        product_name:    str,
        description:     str,
        offer:           str,
        target_audience: str,
        campaign_goal:   str,
        brand_style:     str,
        variation:       int,
        platform:        str,
        campaign_id:     Optional[str],
        seed:            Optional[int] = None,
        language:        Optional[str] = None,
    ) -> dict:
        # Declared outside the try: a retry attempt exists only to *improve* on
        # an earlier one, so if a later attempt crashes we must still be able to
        # return the good poster an earlier attempt already produced rather than
        # throwing away several minutes of GPU work.
        best_result = None
        best_score  = -1

        try:
            from ai.inference_manager import inference_manager
            from app.services.ai.poster_composer import PosterComposer
            from app.services.ai.poster_evaluator import poster_evaluator

            # ── Brand Kit ──────────────────────────────────────────────────
            kit = get_brand_kit(campaign_id or "default")
            # An explicit per-request language wins over the saved brand kit, so
            # changing the dropdown takes effect without saving the kit first.
            language = language or kit.language

            # ── Platform format ────────────────────────────────────────────
            fmt = get_format(platform)
            logger.info("poster_format platform=%s %dx%d sdxl=%dx%d", fmt.platform, fmt.width, fmt.height, fmt.sdxl_width, fmt.sdxl_height)

            # ── CTA ────────────────────────────────────────────────────────
            cta = _get_cta(language, campaign_goal, offer)

            # ── Build campaign context for Qwen ────────────────────────────
            goal_visual_hint = _goal_hint(campaign_goal)
            variation_style  = _VARIATION_STYLES[variation % len(_VARIATION_STYLES)]

            system_prompt = (
                "You are a senior marketing art director. "
                "Analyse the campaign context carefully and return ONLY strict JSON. "
                "No markdown, no extra explanation."
            )

            def _build_spec_prompt(weaknesses: str = "", suggestions: str = "") -> str:
                feedback_block = ""
                if weaknesses:
                    feedback_block = (
                        f"\nPrevious attempt feedback:\n"
                        f"Weaknesses: {weaknesses}\n"
                        f"Suggestions: {suggestions}\n"
                        f"Address these issues in the new specification.\n"
                    )
                return f"""{feedback_block}
Create a visual design specification for a {platform.upper()} marketing poster.

Campaign Context:
  Campaign:        {campaign_name}
  Brand:           {product_name}
  Product:         {product_name}
  Description:     {description}
  Offer:           {offer}
  Target Audience: {target_audience}
  Goal:            {campaign_goal}
  Style Guide:     {brand_style}
  Platform:        {platform} ({fmt.aspect_ratio})
  Language:        {language}

Visual Guidance:
  Goal Strategy:   {goal_visual_hint}
  Variation Style: {variation_style}

Context Priorities (highest first):
  1. Product/Service must be visually prominent
  2. Campaign goal must drive the mood and composition
  3. Target audience context should be reflected
  4. Campaign theme must be clear
  5. Platform aspect ratio: {fmt.aspect_ratio}

Return ONLY this JSON structure:
{{
  "visual_concept": "<15-word scene description — product + environment + mood>",
  "main_subject": "<5 words max — the exact main visual element>",
  "environment": "<5 words — setting/background context>",
  "mood": "<3 words — emotional tone>",
  "style": "<5 words — visual/photographic style>",
  "composition": "<5 words — layout/framing>",
  "color_palette": ["<primary>", "<secondary>", "<accent>"],
  "lighting": "<4 words>",
  "avoid_elements": ["<thing1>", "<thing2>", "<thing3>"]
}}"""

            # ── Generation loop ─────────────────────────────────────────────
            max_attempts  = 2
            threshold     = 70.0
            weaknesses    = ""
            suggestions   = ""
            # get_brand_kit() now defaults these to the vendored Noto faces, so the
            # old `or C:\Windows\Fonts\arial*.ttf` fallbacks are gone: Arial has no
            # Tamil glyphs and rendered Tamil copy as tofu boxes.

            # Every poster gets a real designed layout from BrochureComposer.
            # The tier only decides how many zones have content to show — a
            # campaign with no brand kit at all still gets header/headline/
            # hero/spec/offer, never text floating over a photograph.
            #
            # This replaced a boolean gate that required a product cutout AND
            # contact details. Nothing ever had either, so the gate was false
            # every single time and the layout engine below never ran once.
            layout = kit.pick_layout()

            from app.services.ai.brochure_composer import BrochureComposer
            composer = BrochureComposer(
                font_bold_path=kit.font_bold_path,
                font_reg_path =kit.font_regular_path,
            )
            brochure_spec = await generate_brochure_spec(
                product_name    = product_name,
                campaign_name   = campaign_name,
                description     = description,
                offer           = offer,
                target_audience = target_audience,
                campaign_goal   = campaign_goal,
                language        = language,
                brand_name      = product_name,
            )
            brochure_spec["brand_color_hex"] = kit.brand_color_hex
            cta = brochure_spec["cta"]  # brochure spec already resolved this via _get_cta
            logger.info(
                "poster_generate layout=%s campaign_id=%s spec_fallback=%s",
                layout, campaign_id, brochure_spec.get("fallback"),
            )

            for attempt in range(1, max_attempts + 1):
                logger.info("poster_generate attempt=%d/%d variation=%d", attempt, max_attempts, variation)

                # Step 1 — Visual Specification via Qwen-LLM
                user_prompt = _build_spec_prompt(weaknesses, suggestions)
                # Poster-phase call, so it routes through the same provider as
                # the brochure copy — otherwise this would be the one Qwen call
                # left behind inside a Gemini-only phase.
                #
                # Guarded: this is a network call now, and the fallback spec
                # below only covered a bad *return value*, never an exception.
                # A transient blip (rate limit, safety block, DNS) would
                # otherwise 500 the whole request and discard minutes of GPU
                # work. Same treatment generate_brochure_spec already gives it.
                try:
                    spec = await poster_phase_json(system_prompt, user_prompt)
                except Exception as exc:
                    logger.warning(
                        "poster_visual_spec failed, using deterministic spec: %s", exc
                    )
                    spec = None
                if not spec or not isinstance(spec, dict):
                    spec = {
                        "visual_concept": f"Professional marketing visual for {product_name} — {goal_visual_hint}",
                        "main_subject":   product_name,
                        "environment":    "clean studio background",
                        "mood":          "professional, confident",
                        "style":         "commercial photography",
                        "composition":   "centered product hero",
                        "color_palette": ["vibrant", "modern"],
                        "lighting":      "soft studio light",
                        "avoid_elements": ["cluttered background", "random text", "generic stock"],
                    }

                # Step 2 — Build concise SDXL prompt (keep well under 77 CLIP tokens)
                concept   = spec.get("visual_concept", f"Professional {product_name} marketing visual")
                subject   = spec.get("main_subject", product_name)
                env       = spec.get("environment", "")
                mood      = spec.get("mood", "")
                style     = spec.get("style", "professional commercial photography")
                comp      = spec.get("composition", "")
                colors    = ", ".join(spec.get("color_palette", []))
                lighting  = spec.get("lighting", "")
                avoid     = spec.get("avoid_elements", [])

                template_path = Path(__file__).parent / "sdxl_prompt_template.md"
                if template_path.exists():
                    sdxl_template = template_path.read_text(encoding="utf-8").strip()
                else:
                    # SDXL supplies the ~15% decorative layer *behind* the zone
                    # layout, not the poster. Asking for "marketing photography"
                    # with a main subject is what produced stock photos of people
                    # holding the product, competing with every text zone drawn
                    # on top. What the layout actually needs is a backdrop with
                    # negative space where the zones land.
                    sdxl_template = (
                        "Abstract graphic background for a {product_name} marketing poster, "
                        "{concept}, {env}, {mood} mood, {colors} palette, {lighting}, {style}, "
                        "theme: {goal_visual_hint}, brand style: {brand_style}, "
                        "clean uncluttered centre with generous empty space, "
                        "plain unbusy upper and lower thirds, soft gradient backdrop, "
                        "subtle geometric shapes, no focal subject, poster background plate, high quality"
                    )

                try:
                    sdxl_prompt = sdxl_template.format(
                        product_name=product_name,
                        concept=concept,
                        subject=subject,
                        env=env,
                        mood=mood,
                        style=style,
                        comp=comp,
                        colors=colors,
                        lighting=lighting,
                        goal_visual_hint=goal_visual_hint,
                        brand_style=brand_style
                    )
                except KeyError as e:
                    logger.error("Missing key in SDXL prompt template: %s", e)
                    sdxl_prompt = f"Marketing image for {product_name}, {concept}, professional marketing photography"

                sdxl_prompt = " ".join(sdxl_prompt.split())  # collapse whitespace
                # No character cap here anymore: a character count was never
                # equivalent to CLIP's real 77-*token* limit (that's why
                # prompts were still getting silently truncated by CLIP
                # despite this cap existing), and sdxl_service now handles
                # prompts past 77 tokens correctly via chunked encoding
                # (_encode_long_prompt) instead of relying on truncation to
                # keep them short enough. A generous safety cap remains only
                # to bound worst-case encoding cost, not to approximate 77 tokens.
                sdxl_prompt = sdxl_prompt[:1500]
                sdxl_prompt = f"nxmposter, {sdxl_prompt}"    # LoRA trigger word

                # Context-aware negative prompt. People, faces and product
                # packaging are excluded on purpose: the composer draws the
                # product and all text itself, so anything SDXL renders in
                # those categories can only fight the zones layered on top.
                neg_base = (
                    "low quality, blurry, pixelated, oversaturated, grainy, "
                    "watermark, text overlay, logos, letters, numbers, words, typography, "
                    "people, person, face, hands, product packaging, bottles, containers, "
                    "busy cluttered composition, central focal subject, collage, "
                    "deformed, distorted, bad anatomy, duplicate, ugly, bad composition"
                )
                neg_custom = ", ".join(avoid[:5]) if avoid else ""
                neg_prompt = f"{neg_base}, {neg_custom}".strip(", ")

                logger.info("poster_sdxl_prompt (len=%d): %s", len(sdxl_prompt), sdxl_prompt[:120])

                # Step 3 — SDXL image generation (platform aspect ratio)
                # Same seed base is reused across retry attempts (offset by attempt)
                # so a regeneration with an explicit seed is fully reproducible, while
                # different attempts/variations still get visually distinct results.
                attempt_seed = (seed if seed is not None else _derive_seed(campaign_id, variation)) + (attempt - 1)
                result = await inference_manager.generate_poster(
                    prompt=sdxl_prompt,
                    product_name=product_name,
                    variation=variation,
                    negative_prompt=neg_prompt,
                    width=fmt.sdxl_width,
                    height=fmt.sdxl_height,
                    seed=attempt_seed,
                )
                visual_url  = result.get("image_url", "")
                resolved_seed = result.get("seed", attempt_seed)
                visual_fname = visual_url.split("/")[-1]
                visual_path  = _UPLOAD / visual_fname

                # Step 4 — Poster Composition
                final_fname = f"final_a{attempt}_{visual_fname}"
                final_path  = _UPLOAD / final_fname

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda vp=visual_path, fp=final_path: composer.compose(
                        base_image_path=str(vp),
                        spec=brochure_spec,
                        cta=cta,
                        kit=kit,
                        output_path=str(fp),
                        target_width=fmt.width,
                        target_height=fmt.height,
                        brand_name=product_name,
                    ),
                )

                final_url = f"{settings.STATIC_BASE_URL}/posters/{final_fname}"

                # Step 5 — Vision Evaluation with full campaign context
                eval_context = (
                    f"Campaign: {campaign_name} | Product: {product_name} | "
                    f"Goal: {campaign_goal} | Audience: {target_audience} | "
                    f"Offer: {offer} | Platform: {platform} | Language: {language}"
                )
                eval_result = await poster_evaluator.evaluate(str(final_path), context=eval_context)
                # A fallback evaluation must not count as a pass — see
                # _effective_score.
                score = _effective_score(eval_result)

                current_result = {
                    "image_url":       final_url,
                    "prompt_used":     sdxl_prompt,
                    "provider":        f"local-sdxl-{layout}",
                    "variation_index": variation,
                    "metadata_": {
                        "visual_url":   visual_url,
                        "visual_spec":  spec,
                        "evaluation":   eval_result,
                        "attempts":     attempt,
                        "platform":     platform,
                        "format":       f"{fmt.width}x{fmt.height}",
                        "language":     language,
                        "seed":         resolved_seed,
                        "layout":       layout,
                        # Surfaces a synthetic/fallback brochure spec in the DB
                        # record instead of letting it masquerade as real copy —
                        # same convention as poster_evaluator's fallback flag.
                        "brochure_spec": brochure_spec,
                    },
                }

                # `best_result is None` first: when every attempt's evaluation
                # falls back, each score is -1 and a bare `>` comparison would
                # never latch a result, returning None for a poster that was
                # actually rendered.
                if best_result is None or score > best_score:
                    best_score  = score
                    best_result = current_result

                if score >= threshold:
                    logger.info("poster_approved score=%.1f attempt=%d", score, attempt)
                    break

                if eval_result.get("fallback"):
                    logger.warning(
                        "poster_eval_unavailable attempt=%d — evaluation fell back, so this "
                        "poster is unscored rather than approved", attempt,
                    )
                else:
                    logger.info(
                        "poster_score=%.1f < %.1f — improving for next attempt", score, threshold
                    )
                weaknesses  = ", ".join(eval_result.get("weaknesses",  []))
                suggestions = ", ".join(eval_result.get("suggestions", []))

            return best_result

        except Exception as exc:
            logger.error("poster_generate_local_error variation=%d: %s", variation, exc, exc_info=True)
            # A later attempt failing must not discard an earlier good poster.
            if best_result is not None:
                logger.warning(
                    "poster_generate_degraded variation=%d score=%.1f — returning earlier "
                    "successful attempt despite later failure: %s",
                    variation, best_score, exc,
                )
                return best_result
            raise RuntimeError(f"Poster generation failed for variation {variation}: {exc}") from exc

    # ── OpenAI DALL-E 3 fallback ─────────────────────────────────────────────

    async def _generate_openai(self, prompt: str, product_name: str, variation: int) -> dict:
        import httpx
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "IMAGE_PROVIDER=openai requires the 'openai' package. "
                "Install it with: pip install openai"
            ) from exc

        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY required for IMAGE_PROVIDER=openai")

        client  = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.images.generate(model="dall-e-3", prompt=prompt, size="1024x1024", quality="standard", n=1)
        remote_url = response.data[0].url

        slug  = product_name.replace(" ", "_")[:20]
        fname = f"{slug}_v{variation}_{uuid.uuid4().hex[:8]}.png"
        fpath = _UPLOAD / fname

        async with httpx.AsyncClient() as http:
            r = await http.get(remote_url)
            r.raise_for_status()
            fpath.write_bytes(r.content)

        url = f"{settings.STATIC_BASE_URL}/posters/{fname}"
        return {"image_url": url, "prompt_used": prompt, "provider": "openai-dalle3", "variation_index": variation}


poster_generator = PosterGeneratorService()
