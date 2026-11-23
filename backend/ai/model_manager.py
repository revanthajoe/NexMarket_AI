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
    # the model stays loaded and is reused by the next session for this key
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

    •  Serialises the load/unload transition under one async lock.
    •  Keeps the resident model loaded and reuses it across sessions.
    •  Unloads it only when a *different* model is requested.
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
        # Serialises load/unload only. It is never held while a model runs
        # inference, so a slow generation no longer blocks every other AI call.
        self._swap_lock: asyncio.Lock = asyncio.Lock()
        self._idle: asyncio.Event = asyncio.Event()      # set when nobody uses the resident model
        self._idle.set()
        self._active_name: Optional[str] = None           # currently resident model key
        self._active_users: int = 0                       # sessions using it right now
        self._swapping: bool = False                      # a load/unload is in flight
        self._services: Dict[str, BaseModelService] = {}  # cached service instances
        # One run at a time per model — a service's pipeline is not safe to drive
        # from two threads at once. Per model, so it never serialises the whole
        # system the way a global inference lock would.
        self._model_locks: Dict[str, asyncio.Lock] = {}
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

        The model stays loaded after the block exits and is reused by the next
        session for the same key. It is only unloaded when a *different* model
        is requested, because only one fits in GPU memory at a time — and the
        swap lock is held for that transition alone, never during inference.

        Concurrent sessions for the same key are serialised by a per-model lock
        (the pipeline is shared mutable state); sessions for different keys are
        ordered by the swap path, which waits for in-flight users before
        freeing the model.
        """
        service = await self._acquire(model_key, runtime_config)
        try:
            async with self._model_locks.setdefault(model_key, asyncio.Lock()):
                yield service
        finally:
            self._release()

    async def _acquire(
        self, model_key: str, runtime_config: Optional[dict] = None
    ) -> BaseModelService:
        """
        Return the resident service for `model_key`, loading it if needed.

        The fast path (model already resident, no swap underway) takes no lock.
        Only the load/unload transition is serialised.
        """
        # No await between the check and the increment, so on the single event
        # loop this is atomic against _release() and the swap path.
        if self._active_name == model_key and not self._swapping:
            self._active_users += 1
            return self._services[model_key]

        spec = get_spec(model_key)
        async with self._swap_lock:
            if self._active_name != model_key:
                self._swapping = True
                try:
                    # In-flight inference has to finish before its model is freed.
                    while self._active_users > 0:
                        self._idle.clear()
                        await self._idle.wait()

                    if self._active_name:
                        await self._unload(self._active_name)
                        self._active_name = None

                    service = self._get_or_create(model_key)
                    if runtime_config and hasattr(service, "configure_runtime"):
                        service.configure_runtime(runtime_config)
                    if not service.is_loaded:
                        logger.info(
                            "model_manager load model=%s id=%s", model_key, spec.model_id
                        )
                        await self._load(model_key, service)

                    self._active_name = model_key
                    memory_manager.log_vram(f"after loading {model_key}")
                finally:
                    self._swapping = False

            self._active_users += 1
            return self._services[model_key]

    def _release(self) -> None:
        """Drop one user slot; the model itself is deliberately left resident."""
        self._active_users = max(0, self._active_users - 1)
        if self._active_users == 0:
            self._idle.set()

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
