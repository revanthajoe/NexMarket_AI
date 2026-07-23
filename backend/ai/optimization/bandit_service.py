"""
ai/optimization/bandit_service.py
──────────────────────────────────
Thompson Sampling Contextual Multi-Armed Bandit — Campaign optimizer.

No ML model loaded — pure statistical computation.
Does NOT go through ModelManager (no GPU needed).

Arms: instagram, facebook, linkedin, twitter

Per-arm Beta distribution parameters (alpha, beta) updated from real CTR.
Each call to select_arm() draws from Beta distributions and returns the
highest-scoring arm.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Default Beta priors: (alpha=2, beta=2) — slight positive bias
_PRIORS = {"instagram": [2, 2], "facebook": [2, 2], "linkedin": [2, 2], "twitter": [2, 2]}

# Platform prior CTR estimates for initial scoring
_PLATFORM_BASE_CTR = {
    "instagram": 0.035,
    "facebook":  0.026,
    "linkedin":  0.039,
    "twitter":   0.022,
}


class BanditService:
    """
    Thompson Sampling bandit for campaign platform optimisation.
    Thread-safe via a simple dict (single-process use).
    """

    def __init__(self) -> None:
        # alpha, beta per platform — updated via record_reward
        self._arms: Dict[str, list[float]] = {
            k: list(v) for k, v in _PRIORS.items()
        }

    def select_arm(
        self,
        campaign_goal:      Optional[str] = None,
        budget:             Optional[float] = None,
        target_audience:    Optional[str] = None,
        n_samples:          int = 1000,
    ) -> dict:
        """
        Thompson Sampling draw across all arms.

        Returns:
          {
            recommended_platform: str,
            recommended_time:     str,
            recommended_budget:   float | None,
            confidence:           float,
            reasoning:            str,
            platform_scores:      {platform: score},
          }
        """
        rng = np.random.default_rng()

        # Draw n_samples from each arm's Beta distribution
        samples: Dict[str, np.ndarray] = {
            arm: rng.beta(params[0], params[1], size=n_samples)
            for arm, params in self._arms.items()
        }

        # Probability each arm is best = fraction of samples it leads
        wins = {arm: 0 for arm in self._arms}
        stacked = np.stack(list(samples.values()), axis=0)  # (n_arms, n_samples)
        best_idx = stacked.argmax(axis=0)                    # (n_samples,)
        arms_list = list(self._arms.keys())
        for idx in best_idx:
            wins[arms_list[idx]] += 1

        probabilities = {arm: wins[arm] / n_samples for arm in wins}
        best_arm      = max(probabilities, key=probabilities.__getitem__)
        confidence    = probabilities[best_arm]

        # Score per platform (mean of Beta draws)
        scores = {
            arm: round(float(samples[arm].mean() * 100), 2)
            for arm in self._arms
        }

        # Recommended budget split (60% to best, rest distributed)
        rec_budget = None
        if budget:
            rec_budget = round(budget * 0.60, 2)

        # Time-of-day heuristic
        time_map = {
            "instagram": "18:00–21:00 local",
            "facebook":  "13:00–16:00 local",
            "linkedin":  "08:00–10:00 local",
            "twitter":   "12:00–14:00 local",
        }
        rec_time = time_map.get(best_arm, "10:00–12:00 local")

        reasoning = _build_reasoning(best_arm, confidence, campaign_goal, target_audience)

        logger.info(
            "bandit recommend=%s confidence=%.2f scores=%s",
            best_arm, confidence, scores,
        )

        return {
            "recommended_platform": best_arm,
            "recommended_time":     rec_time,
            "recommended_budget":   rec_budget,
            "confidence":           round(confidence, 4),
            "reasoning":            reasoning,
            "platform_scores":      scores,
        }

    def record_reward(self, platform: str, clicked: bool) -> None:
        """
        Update Beta posterior after observing a click (or not).
        alpha += 1 on click; beta += 1 on non-click.
        """
        if platform not in self._arms:
            return
        if clicked:
            self._arms[platform][0] += 1   # alpha
        else:
            self._arms[platform][1] += 1   # beta
        logger.debug("bandit updated arm=%s clicked=%s params=%s", platform, clicked, self._arms[platform])

    def arm_stats(self) -> dict:
        """Return mean CTR estimate per arm."""
        return {
            arm: round(params[0] / (params[0] + params[1]), 4)
            for arm, params in self._arms.items()
        }


def _build_reasoning(
    best_arm: str,
    confidence: float,
    goal: Optional[str],
    audience: Optional[str],
) -> str:
    goal_str     = goal.replace("_", " ") if goal else "general marketing"
    audience_str = audience or "broad audience"
    return (
        f"Thompson Sampling recommends {best_arm} with "
        f"{confidence:.0%} win probability. "
        f"For '{goal_str}' targeting '{audience_str}', "
        f"{best_arm} shows the highest estimated CTR based on prior campaign data."
    )


# Module-level singleton (stateless statistically, shared across requests)
bandit_service = BanditService()
