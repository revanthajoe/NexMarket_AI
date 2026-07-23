"""
Module 3: Poster Evaluator Service
Uses Vision LLM (GPT-4o or Gemini) to evaluate poster quality.
Returns structured JSON with scores and recommendations.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.prompts.templates import (
    VISION_EVALUATION_SYSTEM_PROMPT,
    VISION_EVALUATION_USER_PROMPT,
)

logger = get_logger(__name__)

_MOCK_EVALUATION = {
    "overall_score": 72.5,
    "dimensions": {
        "readability": 78,
        "layout": 70,
        "branding": 68,
        "contrast": 82,
        "cta_visibility": 75,
        "visual_appeal": 65,
    },
    "strengths": [
        "Strong color contrast makes text readable",
        "CTA button is prominently placed",
        "Product name is clearly visible",
    ],
    "weaknesses": [
        "Background texture competes with text",
        "Font hierarchy could be improved",
    ],
    "suggestions": [
        "Increase whitespace around the headline",
        "Use a single accent color for the CTA",
        "Add a subtle drop shadow to text for depth",
    ],
    "verdict": "good",
}


class PosterEvaluatorService:
    """
    Evaluates a marketing poster using Vision LLM.
    Accepts either an image URL or a local file path.
    """

    async def evaluate(self, image_url: str) -> dict:
        logger.info("poster_evaluate", url=image_url, provider=settings.VISION_PROVIDER)

        # For mock/SVG images, skip the API call
        if settings.VISION_PROVIDER == "openai" and settings.OPENAI_API_KEY:
            try:
                return await self._evaluate_openai(image_url)
            except Exception as exc:
                logger.warning("vision_eval_fallback", error=str(exc))
                return _MOCK_EVALUATION
        elif settings.VISION_PROVIDER == "gemini" and settings.GEMINI_API_KEY:
            try:
                return await self._evaluate_gemini(image_url)
            except Exception as exc:
                logger.warning("vision_eval_fallback_gemini", error=str(exc))
                return _MOCK_EVALUATION
        else:
            logger.info("poster_evaluate_mock")
            return _MOCK_EVALUATION

    # ── OpenAI GPT-4o Vision ──────────────────────────────────────────────────

    async def _evaluate_openai(self, image_url: str) -> dict:
        import openai

        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        # If it's a local static URL, convert to base64
        content_block = await self._build_image_content(image_url)

        response = await client.chat.completions.create(
            model=settings.VISION_MODEL,
            messages=[
                {"role": "system", "content": VISION_EVALUATION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        content_block,
                        {"type": "text", "text": VISION_EVALUATION_USER_PROMPT},
                    ],
                },
            ],
            max_tokens=1024,
            temperature=0.2,
        )
        raw = response.choices[0].message.content.strip()
        return self._parse_response(raw)

    # ── Gemini Vision ─────────────────────────────────────────────────────────

    async def _evaluate_gemini(self, image_url: str) -> dict:
        import google.generativeai as genai

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")

        img_data = await self._fetch_image_bytes(image_url)
        import PIL.Image
        import io
        img = PIL.Image.open(io.BytesIO(img_data))

        prompt = VISION_EVALUATION_SYSTEM_PROMPT + "\n\n" + VISION_EVALUATION_USER_PROMPT
        resp = model.generate_content([prompt, img])
        raw = resp.text.strip()
        return self._parse_response(raw)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _build_image_content(self, url: str) -> dict:
        """Build OpenAI-compatible image content block."""
        if url.startswith("http://localhost") or url.startswith("/"):
            # Local file — convert to base64
            img_bytes = await self._fetch_image_bytes(url)
            b64 = base64.b64encode(img_bytes).decode()
            mime = "image/png" if url.endswith(".png") else "image/svg+xml"
            return {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            }
        return {"type": "image_url", "image_url": {"url": url}}

    async def _fetch_image_bytes(self, url: str) -> bytes:
        if url.startswith("http"):
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.content
        # Local path
        return Path(url).read_bytes()

    def _parse_response(self, raw: str) -> dict:
        """Clean and parse JSON from LLM response."""
        if raw.startswith("```"):
            parts = raw.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                try:
                    return json.loads(part)
                except Exception:
                    continue
        try:
            return json.loads(raw)
        except Exception:
            logger.warning("vision_parse_failed", raw=raw[:200])
            return _MOCK_EVALUATION

    def normalize(self, raw: dict) -> dict:
        """Normalize raw evaluation to standard output schema."""
        dims = raw.get("dimensions", {})
        return {
            "overall_score": raw.get("overall_score", 0),
            "readability_score": dims.get("readability", 0),
            "layout_score": dims.get("layout", 0),
            "branding_score": dims.get("branding", 0),
            "contrast_score": dims.get("contrast", 0),
            "cta_score": dims.get("cta_visibility", 0),
            "visual_appeal_score": dims.get("visual_appeal", 0),
            "strengths": raw.get("strengths", []),
            "weaknesses": raw.get("weaknesses", []),
            "suggestions": raw.get("suggestions", []),
            "raw_response": raw,
        }


poster_evaluator = PosterEvaluatorService()
