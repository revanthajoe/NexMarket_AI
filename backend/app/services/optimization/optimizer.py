"""
app/services/optimization/optimizer.py
─────────────────────────────────────────
Adapter: routes campaign optimization to BanditService.
BanditService is not managed by ModelManager (no GPU needed).
"""
from __future__ import annotations

import logging

from app.core.logging import get_logger

logger = get_logger(__name__)


class CampaignOptimizerService:

    async def optimize(
        self,
        campaign_id: str = None,
        campaign_goal: str = None,
        budget: float = None,
        target_audience: str = None,
        platform_history: dict = None,
    ) -> dict:
        logger.info("optimize campaign=%s goal=%s budget=%s", campaign_id, campaign_goal, budget)

        from ai.inference_manager import inference_manager
        result = await inference_manager.optimize_campaign(
            campaign_goal=campaign_goal,
            budget=budget,
            target_audience=target_audience,
            platform_history=platform_history,
        )
        result["campaign_id"] = campaign_id
        result.setdefault("policy_version", "bandit-v1")
        result.setdefault("reward_source", "UNKNOWN")
        return result

    async def record_result(self, platform: str, clicked: bool, campaign_goal: str = None, target_audience: str = None) -> None:
        from ai.inference_manager import inference_manager
        await inference_manager.record_campaign_result(platform, clicked, campaign_goal, target_audience)

campaign_optimizer = CampaignOptimizerService()
