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
import sys
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
_STEPS     = settings.SDXL_INFERENCE_STEPS   # inference steps — higher = more detail/consistency
_GUIDANCE  = 7.5         # classifier-free guidance scale
_CHUNK     = 75          # tokens per chunk, leaving room for BOS/EOS within the 77 cap


def _chunk_and_encode(prompt: str, tokenizer, text_encoder, device, n_chunks: Optional[int] = None):
    """
    Encode `prompt` past CLIP's 77-token cap by splitting it into 75-token
    chunks and running each through `text_encoder` separately, then
    concatenating along the sequence axis.

    Mirrors diffusers' own StableDiffusionXLPipeline.encode_prompt (read
    directly from the installed 0.30.3 source, pipeline_stable_diffusion_xl.py
    lines 353-464) for the per-chunk step: `output_hidden_states=True`, take
    `hidden_states[-2]` (the penultimate layer, not the final one), and the
    pooled output is `output[0]`.

    `n_chunks`, when given, pads/truncates to exactly that many chunks — used
    to force the negative prompt to match the positive prompt's chunk count,
    since SDXL's classifier-free guidance batches them together and requires
    equal sequence length.

    Returns (embeds, pooled) where embeds has shape (1, n_chunks*77, hidden)
    and pooled is the first chunk's pooled output only — pooled vectors from
    later chunks aren't meaningfully combinable, so only the chunk carrying
    the start of the prompt (the subject, by convention) is used.
    """
    bos_id = tokenizer.bos_token_id
    eos_id = tokenizer.eos_token_id
    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else eos_id
    max_len = tokenizer.model_max_length  # 77 for both SDXL tokenizers

    # Tokenize without truncation to get the full id sequence, then strip
    # whatever special tokens the tokenizer added so chunk boundaries are
    # clean — they're re-added per chunk below.
    full_ids = tokenizer(prompt, truncation=False, add_special_tokens=False).input_ids

    chunks = [full_ids[i:i + _CHUNK] for i in range(0, len(full_ids), _CHUNK)] or [[]]

    if n_chunks is not None:
        if len(chunks) > n_chunks:
            chunks = chunks[:n_chunks]
        while len(chunks) < n_chunks:
            chunks.append([])  # all-pad filler chunk to match the other prompt's length

    embeds_list = []
    pooled = None
    for i, chunk in enumerate(chunks):
        ids = [bos_id] + chunk[: max_len - 2] + [eos_id]
        ids = ids + [pad_id] * (max_len - len(ids))
        input_ids = torch.tensor([ids], device=device)

        output = text_encoder(input_ids, output_hidden_states=True)
        embeds_list.append(output.hidden_states[-2])
        if i == 0:
            pooled = output[0]

    embeds = torch.cat(embeds_list, dim=1)
    return embeds, pooled, len(chunks)


def _encode_long_prompt(pipe, prompt: str, negative_prompt: str, device):
    """
    Build (prompt_embeds, negative_prompt_embeds, pooled_prompt_embeds,
    negative_pooled_prompt_embeds) for prompts that exceed CLIP's 77-token cap.

    SDXL uses two text encoders — tokenizer/text_encoder (CLIP ViT-L, 768-dim)
    and tokenizer_2/text_encoder_2 (OpenCLIP ViT-bigG, 1280-dim). Per diffusers'
    own encode_prompt, each chunk's two encoder outputs are concatenated on the
    *feature* axis (giving 2048-dim) — that happens per chunk here, then chunks
    concatenate on the *sequence* axis, which is what actually lets content
    past token 77 reach the UNet. The pooled embedding is text_encoder_2's
    only, matching diffusers (the loop there overwrites pooled each iteration,
    so only the last encoder's pooled output survives).
    """
    e1, _,      n_pos = _chunk_and_encode(prompt, pipe.tokenizer,   pipe.text_encoder,   device)
    e2, pooled, _      = _chunk_and_encode(prompt, pipe.tokenizer_2, pipe.text_encoder_2, device, n_chunks=n_pos)
    prompt_embeds = torch.cat([e1, e2], dim=-1)

    # Negative prompt must match the positive prompt's chunk count so the two
    # embeddings can be batched together for classifier-free guidance.
    ne1, _,      _ = _chunk_and_encode(negative_prompt, pipe.tokenizer,   pipe.text_encoder,   device, n_chunks=n_pos)
    ne2, npooled, _ = _chunk_and_encode(negative_prompt, pipe.tokenizer_2, pipe.text_encoder_2, device, n_chunks=n_pos)
    negative_prompt_embeds = torch.cat([ne1, ne2], dim=-1)

    return prompt_embeds, negative_prompt_embeds, pooled, npooled


class SDXLService(BaseModelService):

    def __init__(self) -> None:
        super().__init__("sdxl")
        _UPLOAD.mkdir(parents=True, exist_ok=True)
        self._runtime_lora_path: Optional[str] = None
        self._runtime_model_version_id: Optional[str] = None
        self._runtime_configured = False
        self._loaded_lora_path: Optional[str] = None

    def configure_runtime(self, runtime_config: dict) -> None:
        """Configure a validated adapter before the next load."""
        self._runtime_configured = True
        self._runtime_lora_path = runtime_config.get("lora_path")
        self._runtime_model_version_id = runtime_config.get("model_version_id")

    # ── BaseModelService interface ────────────────────────────────────────────

    def _do_load(self) -> None:
        from diffusers import StableDiffusionXLPipeline

        dtype  = torch.float16 if device_manager.supports_fp16 else torch.float32
        device = device_manager.device

        logger.info("sdxl loading model_id=%s dtype=%s device=%s", _SPEC.model_id, dtype, device)

        load_kwargs = dict(
            torch_dtype      = dtype,
            use_safetensors  = True,
            variant          = "fp16" if dtype == torch.float16 else None,
        )

        # Reuse the already-cached model. If the cache was corrupted/cleared,
        # allow one re-download by using local_files_only=False initially.
        # After the first successful load it will be cached and stay cached.
        try:
            pipe = StableDiffusionXLPipeline.from_pretrained(
                _SPEC.model_id, local_files_only=True, **load_kwargs,
            )
        except OSError as e:
            logger.warning("sdxl cache miss, re-downloading: %s", e)
            pipe = StableDiffusionXLPipeline.from_pretrained(
                _SPEC.model_id, local_files_only=False, **load_kwargs,
            )
        logger.info("sdxl loaded from local cache")

        # Optional fine-tuned poster LoRA. Absent by default; the base model is
        # used unchanged when the file is not present. Must load BEFORE
        # enable_model_cpu_offload() below: accelerate's offload hooks are
        # installed on the module tree as it exists at that moment, and
        # load_lora_weights() injects new lora_A/lora_B submodules into the
        # attention projections. Loaded after, those new submodules would be
        # left unwrapped by the offload hooks and stay stuck on CPU in fp16,
        # which crashes with "addmm_impl_cpu_" not implemented for 'Half'.
        lora_path = Path(
            self._runtime_lora_path
            if self._runtime_configured and self._runtime_lora_path
            else settings.SDXL_LORA_PATH
            if not self._runtime_configured
            else "__no_validated_lora__"
        )
        if lora_path.exists():
            # diffusers can only apply LoRA when its PEFT backend is active. If
            # `peft` is missing (typically: the server was started on a global
            # Python instead of backend/.venv), fail loudly here and fall back
            # to the base model rather than raising mid-generation.
            from diffusers.utils import USE_PEFT_BACKEND

            if not USE_PEFT_BACKEND:
                logger.error(
                    "sdxl lora NOT loaded - diffusers PEFT backend unavailable "
                    "(peft missing from %s). Falling back to the base model. "
                    "Start the server from backend/.venv to enable the LoRA.",
                    sys.executable,
                )
            else:
                pipe.load_lora_weights(str(lora_path))
                self._loaded_lora_path = str(lora_path.resolve())
                logger.info("sdxl lora loaded path=%s", lora_path)
        else:
            self._loaded_lora_path = None
            logger.info("sdxl lora absent path=%s - using base model", lora_path)

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
        # enable_model_cpu_offload() installs accelerate hooks that retain GPU
        # state, so dropping the reference alone leaves VRAM held. Release the
        # hooks first, then drop the reference, then purge.
        if self._pipeline is not None:
            try:
                self._pipeline.maybe_free_model_hooks()
            except Exception:
                logger.debug("sdxl maybe_free_model_hooks failed", exc_info=True)

        self._pipeline = None
        self._loaded_lora_path = None
        memory_manager.purge()

    def health_check(self) -> bool:
        return self._pipeline is not None

    # ── Public inference API ──────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        product_name: str,
        variation: int = 0,
        negative_prompt: Optional[str] = None,
        width: int = 768,
        height: int = 768,
        seed: Optional[int] = None,
    ) -> dict:
        """
        Generate one poster image.

        `seed` pins the diffusion RNG so the same (prompt, seed) pair always
        reproduces the same image. If omitted, a random seed is drawn and
        returned in the result so the caller can persist it for reproducibility.

        Returns:
            {
              "image_url":      "http://localhost:8000/static/posters/<file>.png",
              "prompt_used":    "<prompt>",
              "provider":       "local-sdxl",
              "variation_index": <int>,
              "seed":           <int>,
            }
        """
        if negative_prompt is None:
            negative_prompt = (
                "low quality, blurry, pixelated, watermark, text errors, "
                "deformed, ugly, bad anatomy, worst quality"
            )

        if seed is None:
            seed = torch.seed() % (2 ** 32)

        logger.info("sdxl generating variation=%d seed=%d", variation, seed)
        memory_manager.log_vram("before_sdxl_inference")

        # Clamp to SDXL-friendly multiples of 8
        safe_w = max(512, (width  // 8) * 8)
        safe_h = max(512, (height // 8) * 8)
        logger.info("sdxl generating %dx%d variation=%d", safe_w, safe_h, variation)

        # With enable_model_cpu_offload, latents are initialised before layers are
        # streamed to GPU, so a CPU generator avoids device-mismatch errors.
        generator_device = "cpu" if device_manager.info.has_cuda else device_manager.device
        generator = torch.Generator(device=generator_device).manual_seed(int(seed))

        # CLIP's 77-token cap is fixed (both SDXL text encoders' positional
        # embedding tables only have 77 slots — not configurable, retraining
        # would be required to raise it). Short prompts take the normal
        # prompt=/negative_prompt= path unchanged; only prompts that actually
        # exceed the cap pay for chunked encoding.
        token_len = len(self._pipeline.tokenizer(prompt, truncation=False).input_ids)
        chunk_count = max(1, (max(0, token_len - 2) + _CHUNK - 1) // _CHUNK)
        logger.info(
            "sdxl prompt_budget tokens=%d chunk_limit=%d chunks=%d steps=%d",
            token_len, self._pipeline.tokenizer.model_max_length, chunk_count, _STEPS,
        )
        with torch.no_grad():
            if token_len > self._pipeline.tokenizer.model_max_length:
                logger.info(
                    "sdxl prompt exceeds 77-token CLIP cap (%d tokens) - using chunked encoding",
                    token_len,
                )
                # _execution_device is diffusers' own answer to "what device do
                # I feed this pipeline's models" — correct whether cpu-offload
                # hooks are active or not, unlike reading a param's .device
                # directly (which reflects where a module sits *at rest*, not
                # where its offload hook expects inputs during forward()).
                prompt_embeds, negative_prompt_embeds, pooled, npooled = _encode_long_prompt(
                    self._pipeline, prompt, negative_prompt, self._pipeline._execution_device,
                )
                result = self._pipeline(
                    prompt_embeds                   = prompt_embeds,
                    negative_prompt_embeds          = negative_prompt_embeds,
                    pooled_prompt_embeds            = pooled,
                    negative_pooled_prompt_embeds   = npooled,
                    num_inference_steps   = _STEPS,
                    guidance_scale        = _GUIDANCE,
                    num_images_per_prompt = 1,
                    width                 = safe_w,
                    height                = safe_h,
                    generator             = generator,
                )
            else:
                result = self._pipeline(
                    prompt                = prompt,
                    negative_prompt       = negative_prompt,
                    num_inference_steps   = _STEPS,
                    guidance_scale        = _GUIDANCE,
                    num_images_per_prompt = 1,
                    width                 = safe_w,
                    height                = safe_h,
                    generator             = generator,
                )

        image   = result.images[0]
        slug    = product_name.replace(" ", "_")[:20]
        fname   = f"{slug}_v{variation}_{uuid.uuid4().hex[:8]}.png"
        fpath   = _UPLOAD / fname
        image.save(fpath, format="PNG")

        url = f"{settings.STATIC_BASE_URL}/posters/{fname}"
        logger.info("sdxl saved path=%s url=%s seed=%d", fpath, url, seed)
        memory_manager.log_vram("after_sdxl_inference")

        return {
            "image_url":       url,
            "prompt_used":     prompt,
            "provider":        "local-sdxl",
            "variation_index": variation,
            "seed":            int(seed),
            "model_version_id": self._runtime_model_version_id,
            "lora_loaded":      bool(self._loaded_lora_path),
        }
