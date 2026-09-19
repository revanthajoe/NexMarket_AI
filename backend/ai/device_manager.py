"""
ai/device_manager.py
────────────────────
Singleton that resolves the best available compute device at startup
and exposes helpers used by every model loader.

Supports:
  • CUDA (NVIDIA GPU)
  • MPS  (Apple Silicon)
  • CPU  (universal fallback)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import torch

logger = logging.getLogger(__name__)


@dataclass
class DeviceInfo:
    device: str                         # "cuda", "mps", "cpu"
    torch_device: torch.device
    has_cuda: bool
    has_mps: bool
    cuda_name: Optional[str] = None
    vram_total_gb: float = 0.0
    vram_free_gb: float = 0.0
    supports_fp16: bool = False
    supports_4bit: bool = False         # bitsandbytes only works on CUDA
    cuda_major: int = 0


class DeviceManager:
    """
    Singleton — call DeviceManager.get() everywhere.
    """
    _instance: Optional["DeviceManager"] = None

    def __new__(cls) -> "DeviceManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._info = cls._instance._probe()
        return cls._instance

    @classmethod
    def get(cls) -> "DeviceManager":
        return cls()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def info(self) -> DeviceInfo:
        return self._info

    @property
    def device(self) -> str:
        return self._info.device

    @property
    def torch_device(self) -> torch.device:
        return self._info.torch_device

    @property
    def supports_4bit(self) -> bool:
        return self._info.supports_4bit

    @property
    def supports_fp16(self) -> bool:
        return self._info.supports_fp16

    def refresh_vram(self) -> tuple[float, float]:
        """Return (total_gb, free_gb) — refreshed from driver."""
        if not self._info.has_cuda:
            return 0.0, 0.0
        props = torch.cuda.get_device_properties(0)
        total = props.total_memory / 1024 ** 3
        free  = (props.total_memory - torch.cuda.memory_allocated(0)) / 1024 ** 3
        self._info.vram_total_gb = total
        self._info.vram_free_gb  = free
        return total, free

    def compute_dtype(self) -> torch.dtype:
        """Best floating-point compute dtype for the device."""
        if self._info.supports_fp16:
            return torch.float16
        return torch.float32

    # ── Internal ──────────────────────────────────────────────────────────────

    def _probe(self) -> DeviceInfo:
        has_cuda = torch.cuda.is_available()
        has_mps  = getattr(torch.backends, "mps", None) is not None \
                   and torch.backends.mps.is_available()

        if has_cuda:
            torch_device = torch.device("cuda")
            device       = "cuda"
            props        = torch.cuda.get_device_properties(0)
            cuda_name    = torch.cuda.get_device_name(0)
            vram_total   = props.total_memory / 1024 ** 3
            vram_free    = vram_total  # assume free at startup
            cuda_major   = props.major
            fp16_ok      = cuda_major >= 7       # Volta+
            bit4_ok      = fp16_ok               # bitsandbytes needs fp16-capable GPU
        elif has_mps:
            torch_device = torch.device("mps")
            device       = "mps"
            cuda_name    = None
            vram_total   = vram_free = 0.0
            cuda_major   = 0
            fp16_ok      = True
            bit4_ok      = False                 # bitsandbytes is CUDA-only
        else:
            torch_device = torch.device("cpu")
            device       = "cpu"
            cuda_name    = None
            vram_total   = vram_free = 0.0
            cuda_major   = 0
            fp16_ok      = False
            bit4_ok      = False

        info = DeviceInfo(
            device        = device,
            torch_device  = torch_device,
            has_cuda      = has_cuda,
            has_mps       = has_mps,
            cuda_name     = cuda_name,
            vram_total_gb = vram_total,
            vram_free_gb  = vram_free,
            supports_fp16 = fp16_ok,
            supports_4bit = bit4_ok,
            cuda_major    = cuda_major,
        )
        logger.info(
            "device_resolved device=%s cuda=%s fp16=%s 4bit=%s vram=%.1fGB",
            device, has_cuda, fp16_ok, bit4_ok, vram_total,
        )
        return info


# Module-level singleton
device_manager = DeviceManager.get()


def model_input_device(model) -> torch.device:
    """
    Device that `model`'s inputs must be placed on.

    Models loaded with device_map="auto" are placed by accelerate, which may
    split them across GPU/CPU or offload them entirely to CPU/disk when VRAM is
    tight. In those cases the global device_manager.device ("cuda") is wrong and
    passing inputs there raises:

        RuntimeError: Expected all tensors to be on the same device

    Prefer the model's own reported device, skipping `meta` (offloaded) params.
    """
    dev = getattr(model, "device", None)
    if isinstance(dev, torch.device) and dev.type != "meta":
        return dev
    for p in model.parameters():
        if p.device.type != "meta":
            return p.device
    return torch.device("cpu")
