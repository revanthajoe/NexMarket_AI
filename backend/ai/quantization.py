"""
ai/quantization.py
──────────────────
Builds BitsAndBytes 4-bit NF4 quantization configs for transformer models.

Rules:
  • Always NF4 + double-quant
  • Compute dtype fp16
  • Only available on CUDA; returns None on CPU/MPS (load in full precision)
  • SDXL is NEVER quantized (diffusion pipeline, fp16 only)
"""
from __future__ import annotations

import logging
from typing import Optional

import torch

logger = logging.getLogger(__name__)


def get_bnb_4bit_config():
    """
    Return a BitsAndBytesConfig for 4-bit NF4 quantization.
    Returns None if bitsandbytes is unavailable or device is not CUDA.
    """
    try:
        from transformers import BitsAndBytesConfig
        from ai.device_manager import device_manager

        if not device_manager.supports_4bit:
            logger.warning("bnb_4bit_unavailable — device=%s; loading full precision", device_manager.device)
            return None

        config = BitsAndBytesConfig(
            load_in_4bit              = True,
            bnb_4bit_quant_type       = "nf4",
            bnb_4bit_compute_dtype    = torch.float16,
            bnb_4bit_use_double_quant = True,
        )
        logger.debug("bnb_4bit_config_created quant=nf4 compute=fp16 double_quant=True")
        return config

    except ImportError:
        logger.warning("bitsandbytes_not_installed — falling back to full precision")
        return None
    except Exception as exc:
        logger.error("bnb_config_error: %s", exc)
        return None
