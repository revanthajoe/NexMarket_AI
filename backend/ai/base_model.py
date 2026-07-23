"""
ai/base_model.py
─────────────────
Abstract base class every AI service must extend.

Contract:
  • load()   – Load model + tokenizer/processor into memory
  • unload() – Remove all references and trigger cleanup
  • is_loaded property
  • health_check() – lightweight smoke test

Services must NOT call load/unload directly — they go through ModelManager.
This base class exists so ModelManager can interact with any service uniformly.
"""
from __future__ import annotations

import abc
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BaseModelService(abc.ABC):
    """
    Base class for all NexMarket AI model services.

    Subclasses must implement:
      _do_load()   – allocate model, tokenizer, processor etc.
      _do_unload() – delete all heavy references
      health_check() – return True if model produces valid output
    """

    def __init__(self, name: str) -> None:
        self._name    = name
        self._loaded  = False
        self._model: Optional[Any]     = None
        self._tokenizer: Optional[Any] = None
        self._processor: Optional[Any] = None
        self._pipeline: Optional[Any]  = None

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        if self._loaded:
            logger.debug("%s already loaded — skipping", self._name)
            return
        logger.info("loading %s", self._name)
        self._do_load()
        self._loaded = True
        logger.info("%s loaded successfully", self._name)

    def unload(self) -> None:
        if not self._loaded:
            return
        logger.info("unloading %s", self._name)
        self._do_unload()
        self._loaded = False
        logger.info("%s unloaded", self._name)

    # ── Abstract interface ────────────────────────────────────────────────────

    @abc.abstractmethod
    def _do_load(self) -> None:
        """Allocate all heavy resources (model, tokenizer, pipeline …)."""

    @abc.abstractmethod
    def _do_unload(self) -> None:
        """
        Delete all heavy references so GC can collect them.
        Must call ai.memory_manager.purge() at the end.
        """

    @abc.abstractmethod
    def health_check(self) -> bool:
        """
        Lightweight verification that the model is usable.
        Should complete within a second or two on any hardware.
        """
