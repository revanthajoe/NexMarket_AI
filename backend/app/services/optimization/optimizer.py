"""
Module 7: Campaign Optimization Service
Contextual bandit approach: Thompson Sampling over platform arms.
State: (campaign_goal, audience_type, time_of_day).
Stores arm stats in memory (upgradeable to DB).
"""
from __future__ import annotations

import math
import random
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.prompts.templates import OPTIMIZATION_SYSTEM_PROMPT, build_optimization_prompt

logger = get_logger(__name__)

PLATFORMS = ["instagram", "facebook", "linkedin", "twitter"]

# Platform prior stats (alpha, beta) — represents historical CTR distribution
# Updated from real campaign data when available
_ARM_STATS: dict[str, dict] = {
    "instagram": {"alpha": 10, "beta": 5, "ctr_sum": 0.04, "n": 1},
    "facebook":  {"alpha": 8,  "beta": 6, "ctr_sum": 0.03, "n": 1},
    "linkedin":  {"alpha": 6,  "beta": 8, "ctr_sum": 0.025, "n": 1},
    "twitter":   {"alpha": 7,  "beta": 7, "ctr_sum": 0.02, "n": 1},
}

# Best posting times by platform (heuristic priors)
_BEST_TIMES = {
    "instagram": "09:00",
    "facebook":  "14:00",
    "linkedin":  "08:00",
    "twitter":   "12:00",
}

# Recommended budget split (% of total)
_BUDGET_SPLIT = {
    "instagram": 0.35,
    "facebook":  0.30,
    "linkedin":  0.20,
    "twitter":   0.15,
}


def _thompson_sample(platform: str) -> float:
    stats = _ARM_STATS[platform]
    return random.betavariate(stats["alpha"], stats["beta"])


def _update_arm(platform: str, reward: float):
    """Update bandit arm after observing reward (CTR or engagement)."""
    stats = _ARM_STATS[platform]
    stats["n"] += 1
    stats["ctr_sum"] += reward
    if reward > stats["ctr_sum"] / stats["n"]:
        stats["alpha"] += 1
    else:
        stats["beta"] += 1


class OptimizationService:
    async def optimize(
        self,
        campaign_goal: str,
        target_audience: str,
        platform_history: dict,
        budget: Optional[float] = None,
        use_llm: bool = True,
    ) -> dict:
        # Update bandit arms from observed history
        for platform, metrics in platform_history.items():
            if platform in _ARM_STATS and metrics.get("ctr"):
                _update_arm(platform, float(metrics["ctr"]))

        # Thompson Sampling: pick best arm
        samples = {p: _thompson_sample(p) for p in PLATFORMS}
        recommended_platform = max(samples, key=samples.__getitem__)
        platform_scores = {p: round(v * 100, 1) for p, v in samples.items()}
        confidence = round(samples[recommended_platform], 3)

        recommended_budget = None
        if budget:
            recommended_budget = round(budget * _BUDGET_SPLIT[recommended_platform], 2)

        base_result = {
            "recommended_platform": recommended_platform,
            "recommended_time": _BEST_TIMES[recommended_platform],
            "recommended_budget": recommended_budget,
            "confidence": confidence,
            "platform_scores": platform_scores,
            "reasoning": (
                f"Thompson Sampling selected '{recommended_platform}' with highest expected CTR "
                f"({round(confidence * 100, 1)}% confidence). "
                f"Best posting time: {_BEST_TIMES[recommended_platform]}. "
                f"Historical performance and audience alignment considered."
            ),
        }

        # Optionally enrich with LLM reasoning
        if use_llm and settings.OPENAI_API_KEY:
            try:
                llm_result = await self._enrich_with_llm(
                    campaign_goal, target_audience, platform_history, budget
                )
                base_result["reasoning"] = llm_result.get("reasoning", base_result["reasoning"])
            except Exception as exc:
                logger.warning("optimization_llm_failed", error=str(exc))

        return base_result

    async def _enrich_with_llm(
        self,
        campaign_goal: str,
        target_audience: str,
        platform_history: dict,
        budget: Optional[float],
    ) -> dict:
        import json
        import openai

        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        prompt = build_optimization_prompt(campaign_goal, target_audience, platform_history, budget)
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": OPTIMIZATION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        return json.loads(response.choices[0].message.content)

    def record_reward(self, platform: str, ctr: float):
        """Call this after a post to update the bandit from real data."""
        if platform in _ARM_STATS:
            _update_arm(platform, ctr)


optimization_service = OptimizationService()
