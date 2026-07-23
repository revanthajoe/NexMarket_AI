"""
ai/diffusion/sdxl_service.py
─────────────────────────────
Stable Diffusion XL — Poster generation service.

Memory optimisations applied (all non-negotiable):
  • fp16 weights
  • attention_slicing
  • enable_model_cpu_offload  (layers stream VRAM → CPU as needed)
  • enable_vae_slicing        (VAE decode in slices)
  • enable_vae_tiling         (large image VAE tiling)
  • xformers memory_efficient_attention if available

NOT quantized (4-bit BnB breaks diffusion models).

Lifecycle:
  load()    → build SDXL pipeline, apply all optimisations
  generate()→ run text-to-image → save PNG → return file URL
  unload()  → delete pipeline, purge GPU memory
"""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Optional

import torch

from ai.base_model import BaseModelService
from ai.device_manager import device_manager
from ai import memory_manager
from ai.model_registry import get_spec
from app.core.config import settings

logger = logging.getLogger(__name__)

_SPEC      = get_spec("sdxl")
_UPLOAD    = Path(settings.POSTER_UPLOAD_DIR)
_STEPS     = 20          # inference steps — good quality / speed trade-off
_GUIDANCE  = 7.5         # classifier-free guidance scale


class SDXLService(BaseModelService):

    def __init__(self) -> None:
        super().__init__("sdxl")
        _UPLOAD.mkdir(parents=True, exist_ok=True)

    # ── BaseModelService interface ────────────────────────────────────────────

    def _do_load(self) -> None:
        from diffusers import StableDiffusionXLPipeline

        dtype  = torch.float16 if device_manager.supports_fp16 else torch.float32
        device = device_manager.device

        logger.info("sdxl loading model_id=%s dtype=%s device=%s", _SPEC.model_id, dtype, device)

        pipe = StableDiffusionXLPipeline.from_pretrained(
            _SPEC.model_id,
            torch_dtype      = dtype,
            use_safetensors  = True,
            variant          = "fp16" if dtype == torch.float16 else None,
        )

        # ── Memory optimisations ──────────────────────────────────────────────
        if device_manager.info.has_cuda:
            pipe.enable_model_cpu_offload()          # primary VRAM saver
        else:
            pipe = pipe.to(device)

        try:
            pipe.enable_attention_slicing()
        except Exception:
            pass

        try:
            pipe.enable_vae_slicing()
        except Exception:
            pass

        try:
            pipe.enable_vae_tiling()
        except Exception:
            pass

        try:
            pipe.enable_xformers_memory_efficient_attention()
            logger.debug("sdxl xformers enabled")
        except Exception:
            logger.debug("sdxl xformers not available — using default attention")

        self._pipeline = pipe
        logger.info("sdxl pipeline ready")

    def _do_unload(self) -> None:
        memory_manager.purge(self._pipeline)
        self._pipeline = None

    def health_check(self) -> bool:
        return self._pipeline is not None

    # ── Public inference API ──────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        product_name: str,
        variation: int = 0,
        negative_prompt: Optional[str] = None,
    ) -> dict:
        """
        Generate one poster image.

        Returns:
            {
              "image_url":      "http://localhost:8000/static/posters/<file>.png",
              "prompt_used":    "<prompt>",
              "provider":       "local-sdxl",
              "variation_index": <int>,
            }
        """
        if negative_prompt is None:
            negative_prompt = (
                "low quality, blurry, pixelated, watermark, text errors, "
                "deformed, ugly, bad anatomy, worst quality"
            )

        logger.info("sdxl generating variation=%d", variation)
        memory_manager.log_vram("before_sdxl_inference")

        with torch.no_grad():
            result = self._pipeline(
                prompt          = prompt,
                negative_prompt = negative_prompt,
                num_inference_steps = _STEPS,
                guidance_scale  = _GUIDANCE,
                num_images_per_prompt = 1,
            )

        image   = result.images[0]
        slug    = product_name.replace(" ", "_")[:20]
        fname   = f"{slug}_v{variation}_{uuid.uuid4().hex[:8]}.png"
        fpath   = _UPLOAD / fname
        image.save(fpath, format="PNG")

        url = f"{settings.STATIC_BASE_URL}/posters/{fname}"
        logger.info("sdxl saved path=%s url=%s", fpath, url)
        memory_manager.log_vram("after_sdxl_inference")

        return {
            "image_url":       url,
            "prompt_used":     prompt,
            "provider":        "local-sdxl",
            "variation_index": variation,
        }
