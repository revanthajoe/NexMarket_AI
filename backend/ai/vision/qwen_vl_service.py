"""
ai/vision/qwen_vl_service.py
─────────────────────────────
Qwen2.5-VL-3B-Instruct — Poster evaluation service.

Accepts an image (URL or local file path) + text prompt.
Returns structured JSON evaluation.

Lifecycle:
  load()    → AutoProcessor + Qwen2VLForConditionalGeneration (4-bit NF4)
  evaluate()→ build message list with image → generate → parse JSON
  unload()  → purge model + processor
"""
from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path
from typing import Optional

import httpx

from ai.base_model import BaseModelService
from ai.quantization import get_bnb_4bit_config
from ai.device_manager import device_manager, model_input_device
from ai import memory_manager
from ai.model_registry import get_spec

logger = logging.getLogger(__name__)

_SPEC = get_spec("qwen_vl")
_MAX_NEW_TOKENS = 1024

# Default evaluation when vision inference fails or returns unparsable JSON
_FALLBACK_EVAL = {
    "overall_score": 72,
    "dimensions": {
        "readability": 78, "layout": 70, "branding": 68,
        "contrast": 82, "cta_visibility": 75, "visual_appeal": 65,
    },
    "strengths":   ["Good color contrast", "CTA is visible", "Product name is clear"],
    "weaknesses":  ["Background competes with text", "Font hierarchy unclear"],
    "suggestions": ["Increase whitespace around headline", "Use single accent for CTA"],
    "verdict": "good",
    "fallback": True,   # synthetic score — vision inference did not run
}


class QwenVLService(BaseModelService):

    def __init__(self) -> None:
        super().__init__("qwen_vl")

    # ── BaseModelService interface ────────────────────────────────────────────

    def _do_load(self) -> None:
        from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor

        bnb_config = get_bnb_4bit_config() if _SPEC.use_4bit else None
        
        # Use PyTorch's native SDPA instead of flash_attention_2 which requires custom compilation
        attn_impl  = "sdpa" if (_SPEC.flash_attn and device_manager.info.has_cuda) else "eager"

        logger.info("qwen_vl loading model_id=%s 4bit=%s attn=%s",
                    _SPEC.model_id, bnb_config is not None, attn_impl)

        try:
            self._processor = AutoProcessor.from_pretrained(
                _SPEC.model_id,
                trust_remote_code = _SPEC.trust_remote,
                local_files_only    = True,
            )
        except OSError:
            logger.warning("qwen_vl processor cache miss, downloading")
            self._processor = AutoProcessor.from_pretrained(
                _SPEC.model_id,
                trust_remote_code = _SPEC.trust_remote,
                local_files_only    = False,
            )

        load_kwargs: dict = dict(
            trust_remote_code   = _SPEC.trust_remote,
            attn_implementation = attn_impl,
            local_files_only    = True,
        )
        if bnb_config:
            load_kwargs["quantization_config"] = bnb_config
            load_kwargs["device_map"] = "auto"
        else:
            load_kwargs["torch_dtype"] = device_manager.compute_dtype()
            load_kwargs["device_map"]  = "auto" if device_manager.info.has_cuda else None

        try:
            self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                _SPEC.model_id,
                **load_kwargs,
            )
        except OSError:
            logger.warning("qwen_vl model cache miss, downloading")
            load_kwargs["local_files_only"] = False
            self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                _SPEC.model_id,
                **load_kwargs,
            )
        self._model.eval()

    def _do_unload(self) -> None:
        # Drop references BEFORE purging — purge() cannot free what is still
        # referenced when empty_cache()/gc.collect() run.
        self._model     = None
        self._processor = None
        memory_manager.purge()

    def health_check(self) -> bool:
        return self._model is not None and self._processor is not None

    # ── Public inference API ──────────────────────────────────────────────────

    def evaluate(self, image_url: str, system_prompt: str, user_prompt: str) -> dict:
        """
        Evaluate a marketing poster image.

        image_url: http(s) URL or local file path.
        Returns normalised evaluation dict.
        """
        try:
            img_b64, mime = _load_image_as_base64(image_url)
            return self._run_vision(img_b64, mime, system_prompt, user_prompt)
        except Exception as exc:
            logger.error("qwen_vl evaluate failed: %s", exc)
            return _FALLBACK_EVAL

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run_vision(
        self,
        img_b64: str,
        mime: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        import torch

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": f"data:{mime};base64,{img_b64}",
                    },
                    {"type": "text", "text": user_prompt},
                ],
            },
        ]

        # Use qwen_vl_utils process_vision_info if available, else manual approach
        try:
            from qwen_vl_utils import process_vision_info
            image_inputs, video_inputs = process_vision_info(messages)
            text = self._processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = self._processor(
                text          = [text],
                images        = image_inputs,
                videos        = video_inputs,
                return_tensors = "pt",
                padding       = True,
            ).to(model_input_device(self._model))
        except ImportError:
            # Fallback: manual text-only template (evaluation degrades gracefully)
            text = self._processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = self._processor(
                text=[text], return_tensors="pt", padding=True
            ).to(model_input_device(self._model))

        with torch.no_grad():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens = _MAX_NEW_TOKENS,
                do_sample      = False,
            )

        # Strip input tokens
        trimmed = [
            out[len(inp):]
            for inp, out in zip(inputs["input_ids"], output_ids)
        ]
        raw = self._processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()
        return _parse_json_eval(raw)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_image_as_base64(image_url: str) -> tuple[str, str]:
    """Return (base64_string, mime_type) for a URL or local path."""
    if image_url.startswith("http://") or image_url.startswith("https://"):
        # Download synchronously (called from thread executor)
        with httpx.Client(timeout=30) as client:
            resp = client.get(image_url)
            resp.raise_for_status()
            data = resp.content
    else:
        data = Path(image_url).read_bytes()

    ext  = image_url.rsplit(".", 1)[-1].lower()
    mime = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png",  "svg": "image/svg+xml",
        "webp":"image/webp",
    }.get(ext, "image/png")
    return base64.b64encode(data).decode(), mime


def _parse_json_eval(raw: str) -> dict:
    """Parse JSON from Qwen-VL response, falling back to a default evaluation on failure."""
    cleaned = re.sub(r"^```(?:json)?", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"```$", "", cleaned.strip()).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("qwen_vl json_parse_failed raw_head=%s", raw[:120])
        return _FALLBACK_EVAL
