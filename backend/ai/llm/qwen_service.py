"""
ai/llm/qwen_service.py
───────────────────────
Qwen2.5-3B-Instruct — Ad copy generation service.

Lifecycle:
  load()    → load tokenizer + model with 4-bit NF4 quantization
  generate()→ tokenize prompt → model.generate → decode → return text
  unload()  → delete model + tokenizer → purge GPU memory

ModelManager calls load/unload automatically via session context.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from ai.base_model import BaseModelService
from ai.quantization import get_bnb_4bit_config
from ai.device_manager import device_manager
from ai import memory_manager
from ai.model_registry import get_spec

logger = logging.getLogger(__name__)

_SPEC = get_spec("qwen_llm")

# Maximum new tokens generated per request
_MAX_NEW_TOKENS = 1024


class QwenLLMService(BaseModelService):

    def __init__(self) -> None:
        super().__init__("qwen_llm")

    # ── BaseModelService interface ────────────────────────────────────────────

    def _do_load(self) -> None:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        bnb_config = get_bnb_4bit_config() if _SPEC.use_4bit else None
        
        # Use PyTorch's native SDPA instead of flash_attention_2 which requires custom compilation
        attn_impl = "sdpa" if (_SPEC.flash_attn and device_manager.info.has_cuda) else "eager"

        logger.info("qwen_llm loading model_id=%s 4bit=%s attn=%s",
                    _SPEC.model_id, bnb_config is not None, attn_impl)

        self._tokenizer = AutoTokenizer.from_pretrained(
            _SPEC.model_id,
            trust_remote_code=_SPEC.trust_remote,
        )

        load_kwargs: dict = dict(
            trust_remote_code = _SPEC.trust_remote,
            attn_implementation = attn_impl,
        )
        if bnb_config:
            load_kwargs["quantization_config"] = bnb_config
            load_kwargs["device_map"] = "auto"
        else:
            # CPU / MPS — full precision
            dtype = device_manager.compute_dtype()
            load_kwargs["torch_dtype"] = dtype
            load_kwargs["device_map"]  = "auto" if device_manager.info.has_cuda else None

        self._model = AutoModelForCausalLM.from_pretrained(
            _SPEC.model_id,
            **load_kwargs,
        )
        self._model.eval()

    def _do_unload(self) -> None:
        memory_manager.purge(self._model, self._tokenizer)
        self._model     = None
        self._tokenizer = None

    def health_check(self) -> bool:
        try:
            test = self._run_chat([{"role": "user", "content": "Say OK"}], max_new_tokens=8)
            return bool(test)
        except Exception as exc:
            logger.error("qwen_llm health_check failed: %s", exc)
            return False

    # ── Public inference API ──────────────────────────────────────────────────

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
    ) -> str:
        """
        Generate text given a system + user prompt.
        Returns raw string; callers are responsible for JSON parsing.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]
        return self._run_chat(messages, temperature=temperature)

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
    ) -> dict:
        """
        Generate and parse JSON from Qwen.
        Falls back to {} on parse error.
        """
        raw = self.generate(system_prompt, user_prompt, temperature)
        return _parse_json(raw)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run_chat(
        self,
        messages: list[dict],
        max_new_tokens: int = _MAX_NEW_TOKENS,
        temperature: float  = 0.7,
    ) -> str:
        import torch

        text = self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self._tokenizer(text, return_tensors="pt").to(device_manager.device)

        with torch.no_grad():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens = max_new_tokens,
                temperature    = temperature,
                do_sample      = temperature > 0,
                pad_token_id   = self._tokenizer.eos_token_id,
            )

        # Slice off the input tokens to get only the generated part
        generated = output_ids[0][inputs["input_ids"].shape[1]:]
        return self._tokenizer.decode(generated, skip_special_tokens=True).strip()


# ── JSON parsing helper ────────────────────────────────────────────────────────

def _parse_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON; return {} on failure."""
    # Remove ```json ... ``` fences
    cleaned = re.sub(r"^```(?:json)?", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"```$", "", cleaned.strip())
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("qwen_llm json_parse_failed raw_head=%s", raw[:120])
        return {}
