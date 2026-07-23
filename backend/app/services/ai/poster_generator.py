"""
app/services/ai/poster_generator.py
─────────────────────────────────────
Adapter: routes poster generation requests to InferenceManager → ModelManager → SDXLService.

This file is the API service layer. It handles:
  • Prompt building (via prompts/templates.py)
  • Multiple variation dispatch
  • Mock SVG fallback (no GPU / demo mode)
  • Saving results to disk

Actual ML inference is NOT done here. Delegate to inference_manager.
"""
from __future__ import annotations

import time
import uuid
import logging
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.prompts.templates import build_poster_prompt

logger = get_logger(__name__)

_UPLOAD = Path(settings.POSTER_UPLOAD_DIR)
_UPLOAD.mkdir(parents=True, exist_ok=True)


class PosterGeneratorService:

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
        logger.info("poster_generate variation=%d provider=%s", variation, settings.IMAGE_PROVIDER)

        try:
            from ai.inference_manager import inference_manager
            return await inference_manager.generate_poster(prompt, product_name, variation)
        except Exception as exc:
            logger.warning("poster_generate_fallback error=%s", exc)
            return await self._generate_mock(prompt, product_name, variation)

    async def _generate_mock(self, prompt: str, product_name: str, variation: int) -> dict:
        colors = ["#6366f1", "#8b5cf6", "#06b6d4", "#f59e0b"]
        color  = colors[variation % len(colors)]
        slug   = product_name.replace(" ", "_")[:20]
        fname  = f"mock_{slug}_v{variation}_{int(time.time())}.svg"
        fpath  = _UPLOAD / fname

        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%"   style="stop-color:{color};stop-opacity:1"/>
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

        fpath.write_text(svg, encoding="utf-8")
        url = f"{settings.STATIC_BASE_URL}/posters/{fname}"
        return {"image_url": url, "prompt_used": prompt, "provider": "mock", "variation_index": variation}


poster_generator = PosterGeneratorService()
