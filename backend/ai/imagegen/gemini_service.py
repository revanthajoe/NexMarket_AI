"""
ai/imagegen/gemini_service.py
──────────────────────────────
Gemini image generation — produces a COMPLETE poster, text included.

Why this exists alongside SDXL: SDXL cannot render legible text. The entire
brochure/composer architecture (see POSTER_OVERHAUL.md) was built to work
around that — SDXL draws decorative art, a deterministic composer typesets
everything else. Gemini renders text inside the image, so on this path the
model produces the finished poster and no composer runs.

Deliberately NOT a BaseModelService: there is no GPU slot to acquire and no
load/unload lifecycle, so routing it through ModelManager.session() would be
ceremony around an HTTP call. It is a plain async client.

The return contract is byte-for-byte the same dict SDXLService.generate()
returns, so callers never branch on which backend ran.
"""
from __future__ import annotations

import logging
import uuid
from io import BytesIO
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_UPLOAD = Path(settings.POSTER_UPLOAD_DIR)

# The API honours a fixed set of ratios, so we ask for the closest one and
# resize to the exact platform pixels afterwards.
_SUPPORTED_RATIOS: dict[str, float] = {
    "1:1": 1.0, "2:3": 2 / 3, "3:2": 1.5, "3:4": 0.75, "4:3": 4 / 3,
    "4:5": 0.8, "5:4": 1.25, "9:16": 9 / 16, "16:9": 16 / 9, "21:9": 21 / 9,
}


def _nearest_aspect_ratio(width: int, height: int) -> str:
    """Closest API-supported ratio string to the requested pixel dimensions."""
    target = width / height
    return min(_SUPPORTED_RATIOS, key=lambda r: abs(_SUPPORTED_RATIOS[r] - target))


class GeminiImageError(RuntimeError):
    """Raised with an actionable message rather than returning a blank image."""


class GeminiImageService:

    def __init__(self) -> None:
        self._client = None
        self._types  = None

    def _get_client(self):
        """
        Return (client, types). `types` comes from here rather than a
        `from google.genai import types` at the top of generate(): that ran
        *before* this guard, so a missing package escaped as a raw
        ModuleNotFoundError and the dashboard showed "No module named 'google'"
        instead of the install instructions below.
        """
        if self._client is not None:
            return self._client, self._types

        if not settings.GEMINI_API_KEY:
            raise GeminiImageError(
                "IMAGE_PROVIDER=gemini requires GEMINI_API_KEY. "
                "Get one from https://aistudio.google.com/apikey and set it in backend/.env"
            )
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise GeminiImageError(
                "IMAGE_PROVIDER=gemini requires the 'google-genai' package. "
                "Install it into the environment the server runs from:\n"
                "  backend/.venv/Scripts/python.exe -m pip install google-genai"
            ) from exc

        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._types  = types
        return self._client, self._types

    async def generate(
        self,
        prompt: str,
        product_name: str,
        variation: int = 0,
        width: int = 1080,
        height: int = 1080,
        seed: Optional[int] = None,
    ) -> dict:
        """
        Generate one finished poster image.

        `seed` is accepted and echoed back to keep the contract identical to
        SDXLService.generate(), but the Gemini image API exposes no seed
        parameter — output is NOT reproducible from it. Callers must not treat
        a persisted seed from this backend as a way to regenerate the image.
        """
        client, types = self._get_client()
        model = settings.GEMINI_IMAGE_MODEL
        ratio = _nearest_aspect_ratio(width, height)

        logger.info(
            "gemini generating model=%s ratio=%s target=%dx%d variation=%d",
            model, ratio, width, height, variation,
        )

        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(aspect_ratio=ratio),
                ),
            )
        except Exception as exc:
            message = str(exc)
            # limit: 0 means the project has *no* image quota at all, which is a
            # billing state, not a rate limit — retrying never clears it. Say so
            # instead of letting the caller burn its retry budget on it.
            if "limit: 0" in message:
                raise GeminiImageError(
                    f"Gemini image generation is not enabled for this API key "
                    f"(quota limit is 0 for {model}). Image generation requires "
                    f"billing enabled on the Google Cloud project — the free tier "
                    f"grants zero image requests. Enable billing at "
                    f"https://aistudio.google.com/apikey, or set IMAGE_PROVIDER=local "
                    f"in backend/.env to use SDXL instead."
                ) from exc
            raise GeminiImageError(f"Gemini image request failed: {exc}") from exc

        image_bytes = self._extract_image(response, model)

        from PIL import Image
        from app.services.ai.poster_composer import PosterComposer

        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        # The API returns the nearest supported ratio, not our exact pixels;
        # reuse the composer's existing cover-resize so framing is consistent
        # with every other poster the app produces.
        if image.size != (width, height):
            image = PosterComposer._cover_resize(image, width, height)

        slug  = product_name.replace(" ", "_")[:20]
        fname = f"gemini_{slug}_v{variation}_{uuid.uuid4().hex[:8]}.png"
        _UPLOAD.mkdir(parents=True, exist_ok=True)
        fpath = _UPLOAD / fname
        image.save(fpath, format="PNG")

        url = f"{settings.STATIC_BASE_URL}/posters/{fname}"
        logger.info("gemini saved path=%s url=%s size=%dx%d", fpath, url, *image.size)

        return {
            "image_url":       url,
            "prompt_used":     prompt,
            "provider":        "gemini-poster",
            "variation_index": variation,
            "seed":            seed,
        }

    @staticmethod
    def _extract_image(response, model: str) -> bytes:
        """
        Pull the image bytes out of the response.

        A refusal comes back as a perfectly valid response carrying only a text
        part, so an empty result here is a content block, not a transport error
        — surface the model's own words rather than an opaque failure.
        """
        candidates = getattr(response, "candidates", None) or []
        text_parts: list[str] = []

        for candidate in candidates:
            content = getattr(candidate, "content", None)
            for part in (getattr(content, "parts", None) or []):
                inline = getattr(part, "inline_data", None)
                if inline and inline.data:
                    return inline.data
                if getattr(part, "text", None):
                    text_parts.append(part.text)

        detail = " ".join(text_parts).strip()
        raise GeminiImageError(
            f"{model} returned no image"
            + (f" — model said: {detail[:300]}" if detail else " and no explanation.")
        )


gemini_image_service = GeminiImageService()
