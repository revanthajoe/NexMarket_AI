"""
Module 1: Poster Generator Service
Supports: OpenAI DALL·E 3, Stability AI, and Mock mode.
Returns image URL + prompt metadata.
"""
from __future__ import annotations

import base64
import os
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.prompts.templates import build_poster_prompt

logger = get_logger(__name__)

UPLOAD_DIR = Path(settings.POSTER_UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class PosterGeneratorService:
    """
    Generates marketing poster images.
    Chooses provider from settings.IMAGE_PROVIDER:
      - openai  → DALL·E 3
      - stability → Stability AI SDXL
      - mock    → returns a pre-rendered placeholder SVG
    """

    async def generate(
        self,
        product_name: str,
        offer: str,
        target_audience: str,
        campaign_goal: str,
        brand_style: Optional[str] = None,
        variation: int = 0,
    ) -> dict:
        prompt = build_poster_prompt(
            product_name, offer, target_audience, brand_style, campaign_goal, variation
        )
        logger.info("poster_generate", provider=settings.IMAGE_PROVIDER, variation=variation)

        try:
            if settings.IMAGE_PROVIDER == "openai" and settings.OPENAI_API_KEY:
                return await self._generate_dalle(prompt, product_name, variation)
            elif settings.IMAGE_PROVIDER == "stability" and settings.STABILITY_API_KEY:
                return await self._generate_stability(prompt, product_name, variation)
            else:
                return await self._generate_mock(prompt, product_name, variation)
        except Exception as exc:
            logger.warning("poster_generate_fallback", error=str(exc))
            return await self._generate_mock(prompt, product_name, variation)

    # ── OpenAI DALL·E 3 ──────────────────────────────────────────────────────

    async def _generate_dalle(self, prompt: str, product_name: str, variation: int) -> dict:
        import openai

        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
            response_format="url",
        )
        image_url = response.data[0].url
        local_url = await self._download_and_save(image_url, product_name, variation)
        return {
            "image_url": local_url,
            "prompt_used": prompt,
            "provider": "openai-dalle3",
            "variation_index": variation,
        }

    # ── Stability AI ─────────────────────────────────────────────────────────

    async def _generate_stability(self, prompt: str, product_name: str, variation: int) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
                headers={
                    "Authorization": f"Bearer {settings.STABILITY_API_KEY}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "text_prompts": [
                        {"text": prompt, "weight": 1},
                        {"text": "low quality, blurry, text errors", "weight": -1},
                    ],
                    "cfg_scale": 7,
                    "height": 1024,
                    "width": 1024,
                    "samples": 1,
                    "steps": 30,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            img_b64 = data["artifacts"][0]["base64"]
            local_url = self._save_base64(img_b64, product_name, variation)
            return {
                "image_url": local_url,
                "prompt_used": prompt,
                "provider": "stability-sdxl",
                "variation_index": variation,
            }

    # ── Mock (SVG Placeholder) ────────────────────────────────────────────────

    async def _generate_mock(self, prompt: str, product_name: str, variation: int) -> dict:
        colors = ["#6366f1", "#8b5cf6", "#06b6d4", "#f59e0b"]
        color = colors[variation % len(colors)]
        slug = product_name.replace(" ", "_")[:20]
        filename = f"mock_{slug}_v{variation}_{int(time.time())}.svg"
        filepath = UPLOAD_DIR / filename

        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{color};stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#1e1b4b;stop-opacity:1"/>
    </linearGradient>
  </defs>
  <rect width="1024" height="1024" fill="url(#bg)"/>
  <rect x="50" y="50" width="924" height="924" fill="none" stroke="white" stroke-width="2" stroke-opacity="0.3"/>
  <text x="512" y="300" font-family="Arial" font-size="64" font-weight="bold" fill="white" text-anchor="middle">
    {product_name[:30]}
  </text>
  <text x="512" y="420" font-family="Arial" font-size="36" fill="rgba(255,255,255,0.85)" text-anchor="middle">
    AI-Generated Marketing Poster
  </text>
  <text x="512" y="520" font-family="Arial" font-size="28" fill="rgba(255,255,255,0.7)" text-anchor="middle">
    Variation {variation + 1}
  </text>
  <rect x="312" y="620" width="400" height="80" rx="40" fill="white" fill-opacity="0.9"/>
  <text x="512" y="670" font-family="Arial" font-size="28" font-weight="bold" fill="{color}" text-anchor="middle">
    Shop Now →
  </text>
  <text x="512" y="820" font-family="Arial" font-size="22" fill="rgba(255,255,255,0.6)" text-anchor="middle">
    [MOCK POSTER — Demo Mode]
  </text>
</svg>"""

        filepath.write_text(svg, encoding="utf-8")
        url = f"{settings.STATIC_BASE_URL}/posters/{filename}"
        logger.info("poster_mock_generated", path=str(filepath), url=url)
        return {
            "image_url": url,
            "prompt_used": prompt,
            "provider": "mock",
            "variation_index": variation,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _download_and_save(self, url: str, product_name: str, variation: int) -> str:
        slug = product_name.replace(" ", "_")[:20]
        filename = f"{slug}_v{variation}_{uuid.uuid4().hex[:8]}.png"
        filepath = UPLOAD_DIR / filename
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
        return f"{settings.STATIC_BASE_URL}/posters/{filename}"

    def _save_base64(self, b64: str, product_name: str, variation: int) -> str:
        slug = product_name.replace(" ", "_")[:20]
        filename = f"{slug}_v{variation}_{uuid.uuid4().hex[:8]}.png"
        filepath = UPLOAD_DIR / filename
        filepath.write_bytes(base64.b64decode(b64))
        return f"{settings.STATIC_BASE_URL}/posters/{filename}"


poster_generator = PosterGeneratorService()
