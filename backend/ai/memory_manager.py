"""
ai/memory_manager.py
─────────────────────
Handles GPU / system memory cleanup after every model inference.

Public API:
  purge()          – full cleanup: delete refs, empty CUDA cache, GC
  log_vram()       – log current VRAM usage
  vram_free_gb()   – return available VRAM in GB
"""
from __future__ import annotations

import gc
import logging
from typing import Any

import torch

from ai.device_manager import device_manager

logger = logging.getLogger(__name__)


def purge(*objects: Any) -> None:
    """
    Synchronise CUDA, empty the allocator cache, and run GC.

    IMPORTANT: callers must drop their own references BEFORE calling this::

        self._model     = None
        self._tokenizer = None
        memory_manager.purge()

    Passing objects in does NOT free them — a function cannot delete its
    caller's attribute, and holding them as arguments here actively keeps them
    alive across the empty_cache()/gc.collect() below. `*objects` is accepted
    only for backwards compatibility and is deliberately ignored.
    """
    # 2. Move CUDA to synchronise all pending kernels first
    if device_manager.info.has_cuda:
        try:
            torch.cuda.synchronize()
        except Exception:
            pass

    # 3. Empty CUDA cache
    if device_manager.info.has_cuda:
        try:
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        except Exception:
            pass

    # 4. Python garbage collection (two passes)
    gc.collect()
    gc.collect()

    _log_vram_internal()


def log_vram(label: str = "") -> None:
    """Log VRAM usage; no-op if not on CUDA."""
    _log_vram_internal(label)


def vram_free_gb() -> float:
    """Return free VRAM in GB; 999 if not CUDA (unlimited fallback)."""
    if not device_manager.info.has_cuda:
        return 999.0
    free = torch.cuda.memory_reserved(0) - torch.cuda.memory_allocated(0)
    return max(free / 1024 ** 3, 0.0)


def vram_allocated_gb() -> float:
    """Return currently allocated VRAM in GB."""
    if not device_manager.info.has_cuda:
        return 0.0
    return torch.cuda.memory_allocated(0) / 1024 ** 3


# ── Internal ──────────────────────────────────────────────────────────────────

def _log_vram_internal(label: str = "") -> None:
    if not device_manager.info.has_cuda:
        return
    alloc = vram_allocated_gb()
    free  = vram_free_gb()
    total, _ = device_manager.refresh_vram()
    logger.debug(
        "VRAM %s — allocated=%.2fGB free=%.2fGB total=%.2fGB",
        label, alloc, free, total,
    )
