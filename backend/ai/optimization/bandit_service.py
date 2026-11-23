"""
ai/optimization/bandit_service.py
──────────────────────────────────
Thompson Sampling Contextual Multi-Armed Bandit — Campaign optimizer.

No ML model loaded — pure statistical computation.
Does NOT go through ModelManager (no GPU needed).

Arms: instagram, facebook, telegram, whatsapp

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

# Default Beta priors: (alpha=2, beta=2) — slight positive bias.
#
# Every platform the posting layer supports must be listed here. The arms are
# this dict plus whatever persisted BanditState rows exist, and record_reward()
# ignores any platform missing from it. With only telegram present the bandit
# had a single arm, so select_arm() returned telegram with confidence 1.0 for
# every campaign and never learned from instagram/facebook/whatsapp.
_PRIORS = {
    "instagram": [2, 2],
    "facebook":  [2, 2],
    "telegram":  [2, 2],
    "whatsapp":  [2, 2],
}

# Platform prior CTR estimates for initial scoring
_PLATFORM_BASE_CTR = {
    "telegram":  0.045,
}


class BanditService:
    """
    Thompson Sampling bandit for campaign platform optimisation.
    Persists Beta distributions in PostgreSQL.
    """

    async def _get_arms(self, context_hash: str) -> Dict[str, list[float]]:
        from app.db.session import AsyncSessionLocal
        from app.models.models import BanditState
        from sqlalchemy import select

        arms_state = {}
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(BanditState).where(BanditState.context_hash == context_hash)
            )
            rows = result.scalars().all()
            for row in rows:
                arms_state[row.arm_id] = [row.alpha, row.beta]

        # Fill missing priors
        for arm, prior in _PRIORS.items():
            if arm not in arms_state:
                arms_state[arm] = list(prior)
        return arms_state

    async def select_arm(
        self,
        campaign_goal:      Optional[str] = None,
        budget:             Optional[float] = None,
        target_audience:    Optional[str] = None,
        n_samples:          int = 1000,
        platform_history:   Optional[dict] = None,
    ) -> dict:
        """
        Thompson Sampling draw across all arms.
        """
        context_hash = f"{campaign_goal or 'general'}_{target_audience or 'broad'}"
        arms = await self._get_arms(context_hash)

        rng = np.random.default_rng()
        samples: Dict[str, np.ndarray] = {
            arm: rng.beta(params[0], params[1], size=n_samples)
            for arm, params in arms.items()
        }
        for arm, history in (platform_history or {}).items():
            if arm not in samples or not isinstance(history, dict):
                continue
            observed_ctr = history.get("ctr")
            if not isinstance(observed_ctr, (int, float)):
                continue
            impressions = history.get("impressions")
            weight = 0.5
            if isinstance(impressions, (int, float)) and impressions > 0:
                weight = min(float(impressions) / (float(impressions) + 100.0), 0.9)
            samples[arm] = (samples[arm] * (1.0 - weight)) + (
                float(observed_ctr) * weight
            )

        wins = {arm: 0 for arm in arms}
        stacked = np.stack(list(samples.values()), axis=0)  # (n_arms, n_samples)
        best_idx = stacked.argmax(axis=0)                    # (n_samples,)
        arms_list = list(arms.keys())
        for idx in best_idx:
            wins[arms_list[idx]] += 1

        probabilities = {arm: wins[arm] / n_samples for arm in wins}
        best_arm      = max(probabilities, key=probabilities.__getitem__)
        confidence    = probabilities[best_arm]

        scores = {
            arm: round(float(samples[arm].mean() * 100), 2)
            for arm in arms
        }

        rec_budget = None
        if budget:
            rec_budget = round(budget * 0.60, 2)

        time_map = {
            "instagram": "18:00–21:00 local",
            "facebook":  "13:00–16:00 local",
            "telegram":  "09:00–11:00 local",
            "whatsapp":  "10:00–12:00 local",
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

    async def record_reward(
        self,
        platform: str,
        clicked: bool,
        campaign_goal: Optional[str] = None,
        target_audience: Optional[str] = None
    ) -> None:
        """
        Update Beta posterior in DB after observing a click (or not).
        """
        if platform not in _PRIORS:
            return

        from app.db.session import AsyncSessionLocal
        from app.models.models import BanditState
        from sqlalchemy import select

        context_hash = f"{campaign_goal or 'general'}_{target_audience or 'broad'}"

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(BanditState)
                .where(BanditState.context_hash == context_hash)
                .where(BanditState.arm_id == platform)
            )
            state = result.scalar_one_or_none()

            if not state:
                # Initialize with prior
                prior = _PRIORS[platform]
                state = BanditState(
                    context_hash=context_hash,
                    arm_id=platform,
                    alpha=prior[0],
                    beta=prior[1]
                )
                db.add(state)

            if clicked:
                state.alpha += 1.0
            else:
                state.beta += 1.0

            await db.commit()
            logger.debug("bandit updated arm=%s context=%s clicked=%s alpha=%s beta=%s",
                         platform, context_hash, clicked, state.alpha, state.beta)

    async def arm_stats(self, campaign_goal: Optional[str] = None, target_audience: Optional[str] = None) -> dict:
        """Return mean CTR estimate per arm."""
        context_hash = f"{campaign_goal or 'general'}_{target_audience or 'broad'}"
        arms = await self._get_arms(context_hash)
        return {
            arm: round(params[0] / (params[0] + params[1]), 4)
            for arm, params in arms.items()
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
