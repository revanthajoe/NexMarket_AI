"""
ai/llm/gemini_service.py
─────────────────────────
Gemini text + vision for the poster phase.

Why this exists: Qwen2.5-3B at 4-bit cannot write usable Tamil. It produced
`விழுவர் நான்கு மாதம் பெற்றுவர்` as a headline and rendered the brand name
"Birla Opus Paints" as `பிறந்த உபோஸ் பின்னர்` ("Born Opus After"), which shipped
onto a real poster. That is a model-capability limit, not a prompting one —
Gemini returns grammatical Tamil with the brand name left intact in Latin.

Sits beside qwen_service.py and mirrors its role, but is deliberately NOT a
BaseModelService: there is no GPU slot to acquire and no load/unload lifecycle
for an HTTP call, so routing it through ModelManager.session() would be pure
ceremony.

Scope is the poster phase only. Ad copy, sentiment, lead scoring and forecasting
keep their existing local models.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from io import BytesIO
from pathlib import Path
from typing import Optional

from app.core.config import settings

# Reuse the image service's error type rather than inventing a parallel one —
# the quota/auth failure surface is identical and callers already handle it.
from ai.imagegen.gemini_service import GeminiImageError

logger = logging.getLogger(__name__)

# Gemini accepts far larger images, but poster evaluation only needs to judge
# layout, contrast and legibility — full resolution costs tokens and latency
# without changing the verdict.
_MAX_IMAGE_EDGE = 768

# Gemini returns 503 "this model is currently experiencing high demand" fairly
# routinely, and it clears in seconds. Without a retry a passing blip silently
# downgrades the poster to fallback copy or a synthetic evaluation score, so a
# few seconds of backoff is much cheaper than the degraded output.
_TRANSIENT_MARKERS = ("503", "UNAVAILABLE", "500", "INTERNAL", "deadline", "timeout")
_MAX_ATTEMPTS = 3
_BASE_BACKOFF = 1.5


def _is_transient(exc: Exception) -> bool:
    message = str(exc)
    if "limit: 0" in message:
        return False              # billing state - retrying never clears it
    return any(marker in message for marker in _TRANSIENT_MARKERS)


class GeminiLLMService:

    def __init__(self) -> None:
        self._client = None
        self._types  = None

    def _get_client(self):
        """
        Return (client, types). The `types` module is handed back deliberately:
        callers used to do their own `from google.genai import types` at the top
        of each method, which ran *before* this guard and let a raw
        ModuleNotFoundError escape — so a missing package surfaced to the
        dashboard as "No module named 'google'" instead of the install
        instructions below. Getting both from here makes that impossible.
        """
        if self._client is not None:
            return self._client, self._types

        if not settings.GEMINI_API_KEY:
            raise GeminiImageError(
                "AI_TEXT_PROVIDER=gemini requires GEMINI_API_KEY. "
                "Get one from https://aistudio.google.com/apikey and set it in backend/.env"
            )
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise GeminiImageError(
                "AI_TEXT_PROVIDER=gemini requires the 'google-genai' package. "
                "Install it into the environment the server runs from:\n"
                "  backend/.venv/Scripts/python.exe -m pip install google-genai"
            ) from exc

        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._types  = types
        return self._client, self._types

    # ── Text → JSON ──────────────────────────────────────────────────────────

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
    ) -> dict:
        """
        Return a parsed JSON object.

        `response_mime_type="application/json"` makes the model emit valid JSON
        directly, so none of the fence-stripping and brace-matching the Qwen
        path needs applies here. A non-object response is still rejected rather
        than passed on, because every caller indexes into a dict.
        """
        _, types = self._get_client()
        model = settings.GEMINI_TEXT_MODEL

        response = await self._call_with_retry(
            model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                response_mime_type="application/json",
            ),
        )
        return self._parse_json(response, model)

    # ── Vision → JSON ────────────────────────────────────────────────────────

    async def evaluate_image(
        self,
        image_path: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        """
        Score a rendered poster. `image_path` may be a local path or a
        /static/posters/ URL — the poster generator passes a path, while the
        evaluate endpoint passes the stored URL.
        """
        _, types = self._get_client()
        model = settings.GEMINI_TEXT_MODEL
        blob  = self._load_image_part(image_path, types)

        response = await self._call_with_retry(
            model,
            contents=[blob, user_prompt],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
            ),
        )
        return self._parse_json(response, model)

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _load_image_part(image_path: str, types):
        """Resolve a path-or-URL to a downscaled inline JPEG part."""
        from PIL import Image

        path = Path(image_path)
        if not path.exists():
            # A /static/posters/<name> URL maps onto the upload directory.
            candidate = Path(settings.POSTER_UPLOAD_DIR) / image_path.split("/")[-1]
            if not candidate.exists():
                raise GeminiImageError(f"Poster image not found for evaluation: {image_path}")
            path = candidate

        with Image.open(path) as raw:
            img = raw.convert("RGB")
            img.thumbnail((_MAX_IMAGE_EDGE, _MAX_IMAGE_EDGE))
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85)

        return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")

    @staticmethod
    def _parse_json(response, model: str) -> dict:
        text = (getattr(response, "text", None) or "").strip()
        if not text:
            # A safety block returns a valid response carrying no text; say so
            # instead of failing with an opaque JSON error.
            raise GeminiImageError(f"{model} returned an empty response (possibly content-blocked)")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise GeminiImageError(
                f"{model} returned unparseable JSON: {text[:200]}"
            ) from exc
        if not isinstance(data, dict):
            raise GeminiImageError(f"{model} returned {type(data).__name__}, expected a JSON object")
        return data

    async def _call_with_retry(self, model: str, **kwargs):
        """
        Issue the request, retrying transient failures with jittered backoff.

        Only transient classes are retried — a quota `limit: 0` or a bad model
        name fails immediately rather than burning three attempts on something
        that cannot succeed.
        """
        client, _ = self._get_client()
        last: Exception | None = None

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return await client.aio.models.generate_content(model=model, **kwargs)
            except Exception as exc:
                last = exc
                if attempt == _MAX_ATTEMPTS or not _is_transient(exc):
                    break
                delay = _BASE_BACKOFF * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                logger.warning(
                    "gemini transient failure on %s (attempt %d/%d), retrying in %.1fs: %s",
                    model, attempt, _MAX_ATTEMPTS, delay, str(exc)[:120],
                )
                await asyncio.sleep(delay)

        raise self._as_gemini_error(last, model) from last

    @staticmethod
    def _as_gemini_error(exc: Exception, model: str) -> GeminiImageError:
        message = str(exc)
        # limit: 0 is a billing state, not a rate limit — retrying never clears
        # it, so the message must say what actually has to change.
        if "limit: 0" in message:
            return GeminiImageError(
                f"Gemini quota for {model} is 0 on this API key. Enable billing on the "
                f"Google Cloud project at https://aistudio.google.com/apikey, or set "
                f"AI_TEXT_PROVIDER=local in backend/.env to use the local models."
            )
        return GeminiImageError(f"Gemini request to {model} failed: {exc}")


gemini_llm_service = GeminiLLMService()
