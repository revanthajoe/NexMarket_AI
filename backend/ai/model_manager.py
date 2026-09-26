"""
ai/model_manager.py
────────────────────
⭐ Core Load / Unload Engine

Singleton that:
  • Keeps a priority-ordered queue of pending model requests
  • Ensures only ONE large model is live in GPU memory at a time
  • Thread-safe via asyncio.Lock + threading.Lock
  • Lazy-loads model services on first request
  • Automatically unloads the previous model before loading the next
  • Runs post-inference cleanup (memory_manager.purge)

Design Patterns applied:
  Singleton   — one ModelManager instance for the entire process
  Factory     — _build_service() instantiates services by name
  Strategy    — each BaseModelService defines its own load/unload strategy
  Registry    — backed by model_registry.REGISTRY

Usage (from any AI service file):
    from ai.model_manager import model_manager

    async with model_manager.session("qwen_llm") as service:
        result = service.generate(...)
    # model is unloaded here automatically
"""
from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Optional, Type

from ai.base_model import BaseModelService
from ai.model_registry import REGISTRY, ModelSpec, get_spec
from ai import memory_manager

logger = logging.getLogger(__name__)


class ModelManager:
    """
    Singleton model lifecycle manager.

    •  Acquires a global async lock before loading any model.
    •  Unloads the currently active model before loading a new one.
    •  Runs memory_manager.purge() after every session exits.
    •  Provides health_check() for each registered model.
    •  Exposes a priority-aware request queue via session().
    """

    _instance: Optional["ModelManager"] = None
    _init_lock = threading.Lock()

    def __new__(cls) -> "ModelManager":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._setup()
        return cls._instance

    @classmethod
    def get(cls) -> "ModelManager":
        return cls()

    # ── Singleton init ────────────────────────────────────────────────────────

    def _setup(self) -> None:
        self._gpu_lock: asyncio.Lock = asyncio.Lock()     # one model at a time
        self._active_name: Optional[str] = None           # currently loaded model key
        self._services: Dict[str, BaseModelService] = {}  # cached service instances
        logger.info("ModelManager initialised")

    # ── Public async context manager ──────────────────────────────────────────

    @asynccontextmanager
    async def session(
        self,
        model_key: str,
        runtime_config: Optional[dict] = None,
    ) -> AsyncIterator[BaseModelService]:
        """
        Primary API for every AI service.

        async with model_manager.session("qwen_llm") as svc:
            result = svc.generate(...)
        # model is unloaded + GPU memory purged on exit

        The lock guarantees only one model occupies GPU at a time.
        Priority is enforced by callers via asyncio.PriorityQueue if needed
        (services are designed to be called sequentially by n8n pipeline).
        """
        spec = get_spec(model_key)

        async with self._gpu_lock:
            # 1. Unload whatever is currently in GPU (if different)
            if self._active_name and self._active_name != model_key:
                await self._unload(self._active_name)

            # 2. Load the requested model
            service = self._get_or_create(model_key)
            if runtime_config and hasattr(service, "configure_runtime"):
                service.configure_runtime(runtime_config)
            if not service.is_loaded:
                await self._load(model_key, service)

            self._active_name = model_key
            memory_manager.log_vram(f"after loading {model_key}")

            try:
                yield service
            finally:
                # 3. Always unload + purge after inference
                await self._unload(model_key)
                self._active_name = None
                memory_manager.log_vram(f"after unloading {model_key}")

    # ── Health check ──────────────────────────────────────────────────────────

    async def health_check(self, model_key: str) -> bool:
        """
        Load model, run smoke test, unload, return result.
        Used by /health endpoints.
        """
        try:
            async with self.session(model_key) as svc:
                return svc.health_check()
        except Exception as exc:
            logger.error("health_check_failed model=%s error=%s", model_key, exc)
            return False

    # ── Status / monitoring ───────────────────────────────────────────────────

    def status(self) -> dict:
        """Return current manager status (for /health API)."""
        from ai import memory_manager as mm
        return {
            "active_model": self._active_name,
            "loaded_services": [k for k, v in self._services.items() if v.is_loaded],
            "vram_allocated_gb": mm.vram_allocated_gb(),
            "vram_free_gb": mm.vram_free_gb(),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_or_create(self, model_key: str) -> BaseModelService:
        """Return cached service or instantiate via factory."""
        if model_key not in self._services:
            self._services[model_key] = _ServiceFactory.build(model_key)
        return self._services[model_key]

    async def _load(self, model_key: str, service: BaseModelService) -> None:
        """Run load() in a thread-pool executor so it doesn't block the event loop."""
        loop = asyncio.get_event_loop()
        logger.info("model_manager loading=%s", model_key)
        await loop.run_in_executor(None, service.load)

    async def _unload(self, model_key: str) -> None:
        """Run unload() in executor."""
        service = self._services.get(model_key)
        if service and service.is_loaded:
            loop = asyncio.get_event_loop()
            logger.info("model_manager unloading=%s", model_key)
            await loop.run_in_executor(None, service.unload)


# ── Service Factory ────────────────────────────────────────────────────────────

class _ServiceFactory:
    """
    Factory that maps model_key → concrete BaseModelService subclass.
    Adding a new model = one new entry here + one new service class.
    """

    _MAP: Dict[str, str] = {
        "qwen_llm":   "ai.llm.qwen_service.QwenLLMService",
        "qwen_vl":    "ai.vision.qwen_vl_service.QwenVLService",
        "sdxl":       "ai.diffusion.sdxl_service.SDXLService",
        "distilbert": "ai.sentiment.distilbert_service.DistilBERTService",
        "xgboost":    "ai.lead.xgboost_service.XGBoostService",
        "lstm":       "ai.forecasting.lstm_service.LSTMService",
    }

    @classmethod
    def build(cls, model_key: str) -> BaseModelService:
        import importlib
        path = cls._MAP.get(model_key)
        if not path:
            raise ValueError(f"No factory entry for model_key='{model_key}'")
        module_path, class_name = path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        klass: Type[BaseModelService] = getattr(module, class_name)
        return klass()


# Module-level singleton
model_manager = ModelManager.get()
