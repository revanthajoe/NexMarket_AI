"""
ai/inference_manager.py
────────────────────────
High-level async interface between FastAPI endpoints and ModelManager.

Every public method:
  1. Acquires the GPU slot via ModelManager.session(key)
  2. Runs inference in executor (blocking I/O won't block event loop)
  3. ModelManager auto-unloads + purges after session exits

FastAPI endpoints should import inference_manager, never services directly.

This is the Dependency Injection boundary:
  API endpoint → InferenceManager → ModelManager → Service
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from ai.model_manager import model_manager
from ai.optimization.bandit_service import bandit_service

logger = logging.getLogger(__name__)


class InferenceManager:
    """
    Singleton facade. Use inference_manager module-level instance below.
    """

    # ─────────────────────────────────────────────────────────────────────────
    # 1. POSTER GENERATION (priority 1 — SDXL)
    # ─────────────────────────────────────────────────────────────────────────

    async def generate_poster(
        self,
        prompt: str,
        product_name: str,
        variation: int = 0,
        negative_prompt: Optional[str] = None,
        width: int = 768,
        height: int = 768,
        seed: Optional[int] = None,
    ) -> dict:
        """Generate one marketing poster image with SDXL."""
        async with model_manager.session("sdxl") as svc:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, lambda: svc.generate(prompt, product_name, variation, negative_prompt, width, height, seed)
            )

    # ─────────────────────────────────────────────────────────────────────────
    # 2. POSTER EVALUATION (priority 2 — Qwen2.5-VL)
    # ─────────────────────────────────────────────────────────────────────────

    async def evaluate_poster(
        self,
        image_url: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        """Evaluate a poster image using Qwen2.5-VL-3B-Instruct."""
        async with model_manager.session("qwen_vl") as svc:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, lambda: svc.evaluate(image_url, system_prompt, user_prompt)
            )

    # ─────────────────────────────────────────────────────────────────────────
    # 3. ADVERTISEMENT GENERATION (priority 3 — Qwen2.5-3B)
    # ─────────────────────────────────────────────────────────────────────────

    async def generate_ad_copy(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
    ) -> dict:
        """Generate platform-specific ad copy with Qwen2.5-3B-Instruct."""
        async with model_manager.session("qwen_llm") as svc:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, lambda: svc.generate_json(system_prompt, user_prompt, temperature)
            )

    async def generate_visual_spec(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
    ) -> dict:
        """Generate structured visual spec with Qwen2.5-3B-Instruct."""
        async with model_manager.session("qwen_llm") as svc:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, lambda: svc.generate_json(system_prompt, user_prompt, temperature)
            )

    # ─────────────────────────────────────────────────────────────────────────
    # 4. SENTIMENT ANALYSIS (priority 4 — DistilBERT)
    # ─────────────────────────────────────────────────────────────────────────

    async def analyze_sentiment(self, texts: List[str]) -> List[dict]:
        """Classify sentiment for a list of texts with DistilBERT."""
        async with model_manager.session("distilbert") as svc:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: svc.analyze(texts))

    # ─────────────────────────────────────────────────────────────────────────
    # 5. LEAD PREDICTION (priority 5 — XGBoost)
    # ─────────────────────────────────────────────────────────────────────────

    async def predict_lead(
        self,
        clicks: int,
        views: int,
        time_spent_seconds: int,
        prior_purchases: int,
        source_platform: str,
        device: str,
        age_group: str,
        location_tier: int,
    ) -> dict:
        """Score a lead with XGBoost."""
        async with model_manager.session("xgboost") as svc:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: svc.predict(
                    clicks, views, time_spent_seconds, prior_purchases,
                    source_platform, device, age_group, location_tier,
                ),
            )

    # ─────────────────────────────────────────────────────────────────────────
    # 6. ENGAGEMENT FORECASTING (priority 6 — LSTM)
    # ─────────────────────────────────────────────────────────────────────────

    async def forecast_engagement(
        self,
        history_array,
        horizon_days: int = 7,
    ) -> dict:
        """Run LSTM engagement forecasting."""
        import numpy as np
        history = np.array(history_array, dtype=np.float32)

        async with model_manager.session("lstm") as svc:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, lambda: svc.forecast(history, horizon_days)
            )

    # ─────────────────────────────────────────────────────────────────────────
    # 7. CAMPAIGN OPTIMIZATION (Thompson Sampling — no GPU)
    # ─────────────────────────────────────────────────────────────────────────

    async def optimize_campaign(
        self,
        campaign_goal: Optional[str] = None,
        budget: Optional[float] = None,
        target_audience: Optional[str] = None,
    ) -> dict:
        """Run Thompson Sampling bandit optimisation (CPU, no model load)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: bandit_service.select_arm(campaign_goal, budget, target_audience),
        )

    async def record_campaign_result(self, platform: str, clicked: bool) -> None:
        """Feed real-world click result back to the bandit."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: bandit_service.record_reward(platform, clicked)
        )

    # ─────────────────────────────────────────────────────────────────────────
    # System status
    # ─────────────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        return model_manager.status()

    async def health_check_all(self) -> dict:
        """Health-check every model (sequential — respects single-GPU rule)."""
        results = {}
        for key in ["distilbert", "xgboost", "lstm"]:  # lightweight first
            results[key] = await model_manager.health_check(key)
        # Heavy models: only check if GPU available
        from ai.device_manager import device_manager
        if device_manager.info.has_cuda or device_manager.info.has_mps:
            for key in ["qwen_llm", "qwen_vl", "sdxl"]:
                results[key] = await model_manager.health_check(key)
        return results


# Module-level singleton
inference_manager = InferenceManager()
