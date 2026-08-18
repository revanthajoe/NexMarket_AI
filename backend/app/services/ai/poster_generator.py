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
    ) -> dict:
        logger.info("poster_generate variation=%d provider=%s platform=%s", variation, settings.IMAGE_PROVIDER, platform)

        if settings.IMAGE_PROVIDER == "local":
            return await self._generate_local(
                campaign_name, product_name, description, offer,
                target_audience, campaign_goal, brand_style or "",
                variation, platform, campaign_id,
            )
        elif settings.IMAGE_PROVIDER == "openai":
            return await self._generate_openai("A placeholder prompt", product_name, variation)
        else:
            raise ValueError(f"Unsupported IMAGE_PROVIDER={settings.IMAGE_PROVIDER!r}")

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
    ) -> dict:
        try:
            from ai.inference_manager import inference_manager
            from app.services.ai.poster_composer import PosterComposer
            from app.services.ai.poster_evaluator import poster_evaluator

            # ── Brand Kit ──────────────────────────────────────────────────
            kit = get_brand_kit(campaign_id or "default")
            language = kit.language

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
            best_result   = None
            best_score    = -1
            weaknesses    = ""
            suggestions   = ""
            composer = PosterComposer(
                font_bold_path=kit.font_bold_path or r"C:\Windows\Fonts\arialbd.ttf",
                font_reg_path =kit.font_regular_path or r"C:\Windows\Fonts\arial.ttf",
            )

            for attempt in range(1, max_attempts + 1):
                logger.info("poster_generate attempt=%d/%d variation=%d", attempt, max_attempts, variation)

                # Step 1 — Visual Specification via Qwen-LLM
                user_prompt = _build_spec_prompt(weaknesses, suggestions)
                spec = await inference_manager.generate_visual_spec(system_prompt, user_prompt)
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
                    sdxl_template = (
                        "Marketing image for {product_name}, {concept}, main subject: {subject}, setting: {env}, mood: {mood}, "
                        "style: {style}, {comp}, {colors} palette, {lighting}, "
                        "theme: {goal_visual_hint}, brand style: {brand_style}, "
                        "professional marketing photography, high quality, sharp focus"
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
                sdxl_prompt = sdxl_prompt[:380]              # hard cap

                # Context-aware negative prompt
                neg_base = (
                    "low quality, blurry, pixelated, oversaturated, grainy, "
                    "watermark, text overlay, logos, letters, numbers, words, "
                    "deformed, distorted, bad anatomy, duplicate, ugly, bad composition"
                )
                neg_custom = ", ".join(avoid[:5]) if avoid else ""
                neg_prompt = f"{neg_base}, {neg_custom}".strip(", ")

                logger.info("poster_sdxl_prompt (len=%d): %s", len(sdxl_prompt), sdxl_prompt[:120])

                # Step 3 — SDXL image generation (platform aspect ratio)
                result = await inference_manager.generate_poster(
                    prompt=sdxl_prompt,
                    product_name=product_name,
                    variation=variation,
                    negative_prompt=neg_prompt,
                    width=fmt.sdxl_width,
                    height=fmt.sdxl_height,
                )
                visual_url  = result.get("image_url", "")
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
                        brand_name=product_name,
                        campaign_name=campaign_name,
                        offer=offer,
                        cta=cta,
                        output_path=str(fp),
                        logo_path=kit.logo_path,
                        product_image_path=kit.product_image_path,
                        target_width=fmt.width,
                        target_height=fmt.height,
                        brand_color_hex=kit.brand_color_hex,
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
                score = eval_result.get("overall_score", 0)

                current_result = {
                    "image_url":       final_url,
                    "prompt_used":     sdxl_prompt,
                    "provider":        "local-sdxl-composed",
                    "variation_index": variation,
                    "metadata_": {
                        "visual_url":   visual_url,
                        "visual_spec":  spec,
                        "evaluation":   eval_result,
                        "attempts":     attempt,
                        "platform":     platform,
                        "format":       f"{fmt.width}x{fmt.height}",
                        "language":     language,
                    },
                }

                if score > best_score:
                    best_score  = score
                    best_result = current_result

                if score >= threshold:
                    logger.info("poster_approved score=%.1f attempt=%d", score, attempt)
                    break

                logger.info("poster_score=%.1f < %.1f — improving for next attempt", score, threshold)
                weaknesses  = ", ".join(eval_result.get("weaknesses",  []))
                suggestions = ", ".join(eval_result.get("suggestions", []))

            return best_result

        except Exception as exc:
            logger.error("poster_generate_local_error variation=%d: %s", variation, exc, exc_info=True)
            raise RuntimeError(f"Poster generation failed for variation {variation}: {exc}") from exc

    # ── OpenAI DALL-E 3 fallback ─────────────────────────────────────────────

    async def _generate_openai(self, prompt: str, product_name: str, variation: int) -> dict:
        import httpx
        from openai import OpenAI

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
