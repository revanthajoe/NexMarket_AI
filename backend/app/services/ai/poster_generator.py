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
import base64
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

_MOCK_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAFc1mYAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJ0UkGAAAAAAgI0wAAAAAASUVORK5CYII="
)


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
        "description": description,
        "target_audience": target_audience,
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
    spec["language"] = language
    logger.info(
        "brochure_spec_result product=%s fallback=%s headline=%r offer=%r",
        product_name, spec["fallback"], spec.get("headline_en"), spec.get("offer_en"),
    )

    if spec["fallback"]:
        logger.warning(
            "brochure_spec fallback=True product=%s language=%s - model output was "
            "unusable; copy is synthetic", product_name, language,
        )
    else:
        logger.info("brochure_spec ok product=%s language=%s", product_name, language)
    return spec


async def generate_visual_design_spec(
    product_name: str,
    description: str,
    offer: str,
    target_audience: str,
    campaign_goal: str,
    platform: str,
    aspect_ratio: str,
    brand_style: str = "",
    feedback: str = "",
) -> dict:
    """Plan an arbitrary campaign scene without product-specific logic."""
    from app.prompts.templates import (
        VISUAL_DESIGN_SPEC_SYSTEM_PROMPT,
        build_visual_design_prompt,
        normalize_visual_design_spec,
    )

    context = {
        "product_name": product_name,
        "description": description,
        "offer": offer,
        "target_audience": target_audience,
        "campaign_goal": campaign_goal,
    }
    raw = None
    try:
        raw = await poster_phase_json(
            VISUAL_DESIGN_SPEC_SYSTEM_PROMPT,
            build_visual_design_prompt(
                product_name=product_name,
                description=description,
                offer=offer,
                target_audience=target_audience,
                campaign_goal=campaign_goal,
                platform=platform,
                aspect_ratio=aspect_ratio,
                brand_style=brand_style,
                feedback=feedback,
            ),
        )
    except Exception as exc:
        logger.warning("visual_design_spec failed, using neutral fallback: %s", exc)
    spec = normalize_visual_design_spec(raw, context)
    logger.info(
        "visual_design_spec product=%s category=%s layout=%s fallback=%s",
        product_name, spec["product_category"], spec["layout_type"], spec["fallback"],
    )
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
        sdxl_model_version_id: Optional[str] = None,
        sdxl_lora_path: Optional[str] = None,
    ) -> dict:
        logger.info("poster_generate variation=%d provider=%s platform=%s", variation, settings.IMAGE_PROVIDER, platform)

        if settings.IMAGE_PROVIDER == "local":
            return await self._generate_local(
                campaign_name, product_name, description, offer,
                target_audience, campaign_goal, brand_style or "",
                variation, platform, campaign_id, seed, language,
                sdxl_model_version_id, sdxl_lora_path,
            )
        elif settings.IMAGE_PROVIDER == "openai":
            return await self._generate_openai("A placeholder prompt", product_name, variation)
        elif settings.IMAGE_PROVIDER == "mock":
            return await self._generate_mock(product_name, variation)
        else:
            raise ValueError(f"Unsupported IMAGE_PROVIDER={settings.IMAGE_PROVIDER!r}")

    async def _generate_mock(self, product_name: str, variation: int) -> dict:
        """Return a deterministic mock poster payload without heavy model providers."""
        slug = product_name.replace(" ", "_")[:20] or "campaign"
        fname = f"{slug}_mock_v{variation}_{uuid.uuid4().hex[:8]}.png"
        fpath = _UPLOAD / fname
        fpath.write_bytes(_MOCK_PNG_BYTES)
        return {
            "image_url": f"{settings.STATIC_BASE_URL}/posters/{fname}",
            "prompt_used": "mock image generation",
            "provider": "mock",
            "variation_index": variation,
        }

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
        sdxl_model_version_id: Optional[str] = None,
        sdxl_lora_path: Optional[str] = None,
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

            # ── Generation loop ─────────────────────────────────────────────
            max_attempts  = 3
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
            design_spec = await generate_visual_design_spec(
                product_name=product_name,
                description=description,
                offer=offer,
                target_audience=target_audience,
                campaign_goal=campaign_goal,
                platform=platform,
                aspect_ratio=fmt.aspect_ratio,
                brand_style=brand_style,
            )
            logger.info(
                "poster_generate layout=%s campaign_id=%s copy_fallback=%s design_fallback=%s",
                layout, campaign_id, brochure_spec.get("fallback"), design_spec.get("fallback"),
            )

            for attempt in range(1, max_attempts + 1):
                logger.info("poster_generate attempt=%d/%d variation=%d", attempt, max_attempts, variation)

                if attempt > 1:
                    design_spec = await generate_visual_design_spec(
                        product_name=product_name,
                        description=description,
                        offer=offer,
                        target_audience=target_audience,
                        campaign_goal=campaign_goal,
                        platform=platform,
                        aspect_ratio=fmt.aspect_ratio,
                        brand_style=brand_style,
                        feedback=(
                            f"Weaknesses: {weaknesses}\nSuggestions: {suggestions}"
                        ),
                    )

                # Step 2 — Build concise SDXL prompt (keep well under 77 CLIP tokens)
                concept   = design_spec.get("visual_concept", product_name)
                subject   = ", ".join(design_spec.get("primary_subjects", [product_name]))
                env       = design_spec.get("environment", "")
                mood      = design_spec.get("mood", "")
                style     = design_spec.get("style", "commercial advertising")
                comp      = design_spec.get("composition", "")
                colors    = design_spec.get("color_direction", "")
                lighting  = design_spec.get("lighting", "")
                avoid     = design_spec.get("avoid_visual_elements", [])
                category_hint = design_spec.get("product_category", "relevant product category")

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
                        "{product_name} marketing background, {category_hint}, {goal_visual_hint}, "
                        "{colors} palette, {style}, Telegram-safe 16:9 composition, "
                        "clean negative space in the centre and upper third for typeset text, "
                        "quiet lower third, soft geometric depth, no readable text, no focal person, high quality"
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
                        goal_visual_hint=design_spec.get("campaign_goal", campaign_goal),
                        category_hint=category_hint,
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

                # Context-aware negative prompt.
                # If a product cutout is provided, we don't want SDXL drawing competing products or focal subjects.
                # If NO cutout is provided, we want SDXL to draw the product!
                neg_base = (
                    "low quality, blurry, pixelated, oversaturated, grainy, "
                    "watermark, text overlay, signage, menu, poster, label, packaging, screen, "
                    "logos, letters, numbers, words, typography, symbols, "
                    "collage, deformed, distorted, bad anatomy, duplicate, ugly, bad composition"
                )
                
                is_human_campaign = any(w in (category_hint + " " + campaign_goal).lower() 
                                        for w in ["education", "fashion", "lifestyle", "fitness", "health", "apparel", "clothing", "human"])
                if not is_human_campaign:
                    neg_base += ", people, person, face, hands"
                
                if kit.product_cutout_path:
                    neg_base += ", product packaging, bottles, containers, central focal subject"

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
                    lora_path=sdxl_lora_path,
                    model_version_id=sdxl_model_version_id,
                )
                visual_url  = result.get("image_url", "")
                resolved_seed = result.get("seed", attempt_seed)
                visual_fname = visual_url.split("/")[-1]
                visual_path  = _UPLOAD / visual_fname

                # Step 4 — Poster Composition
                final_fname = f"final_a{attempt}_{visual_fname}"
                final_path  = _UPLOAD / final_fname

                from app.services.ai.brochure_composer import PosterCreativeSpec
                # Distribute variations across the strategies
                comp_strategies = ["hero_focused", "offer_focused", "lifestyle", "minimal"]
                comp_strategy = comp_strategies[variation % len(comp_strategies)]
                
                creative_spec = PosterCreativeSpec(
                    campaign_objective=campaign_goal,
                    product_name=product_name,
                    target_audience=target_audience,
                    brand_name=product_name,
                    headline=brochure_spec.get("headline_en", "") or brochure_spec.get("headline", ""),
                    subheadline=brochure_spec.get("subheadline_en", "") or brochure_spec.get("subheadline", ""),
                    supporting_message=brochure_spec.get("why_title_en", "") or brochure_spec.get("why_title", ""),
                    # Offer band and CTA pill are separate elements — passing the
                    # CTA here printed the button label twice and dropped the offer.
                    offer=brochure_spec.get("offer_en") or offer,
                    cta=cta,
                    brand_color_hex=kit.brand_color_hex or "",
                    visual_subject=subject,
                    visual_style=style,
                    composition_strategy=comp_strategy,
                    color_direction=colors,
                    platform=platform,
                    aspect_ratio=fmt.aspect_ratio,
                    variation_index=variation
                )

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda vp=visual_path, fp=final_path: composer.compose(
                        spec=creative_spec,
                        base_image_path=str(vp),
                        kit=kit,
                        output_path=str(fp),
                        target_width=fmt.width,
                        target_height=fmt.height
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
                        "visual_spec":  design_spec,
                        "evaluation":   eval_result,
                        "attempts":     attempt,
                        "platform":     platform,
                        "format":       f"{fmt.width}x{fmt.height}",
                        "language":     language,
                        "seed":         resolved_seed,
                        "layout":       layout,
                        "brand_kit": {
                            "language": language,
                            "logo": bool(kit.logo_path),
                            "partner_logo": bool(kit.partner_logo_path),
                            "product_image": bool(kit.product_image_path),
                            "product_cutout": bool(kit.product_cutout_path),
                            "map_image": bool(kit.map_image_path),
                            "contact_details": kit.has_contact_details(),
                            "brand_color": kit.brand_color_hex,
                        },
                        # Surfaces a synthetic/fallback brochure spec in the DB
                        # record instead of letting it masquerade as real copy —
                        # same convention as poster_evaluator's fallback flag.
                        "brochure_spec": brochure_spec,
                        "sdxl_model_version_id": sdxl_model_version_id,
                        "sdxl_lora_loaded": result.get("lora_loaded", False),
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
