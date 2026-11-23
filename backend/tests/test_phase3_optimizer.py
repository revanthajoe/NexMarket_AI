import pytest

from app.services.optimization.optimizer import CampaignOptimizerService


@pytest.mark.asyncio
async def test_optimizer_forwards_actual_platform_history(monkeypatch):
    from ai import inference_manager as manager_module

    calls = {}

    async def optimize_campaign(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return {"recommended_platform": "telegram"}

    monkeypatch.setattr(manager_module.inference_manager, "optimize_campaign", optimize_campaign)

    history = {"telegram": {"ctr": 0.2, "clicks": 20, "impressions": 100}}
    result = await CampaignOptimizerService().optimize(
        campaign_id="campaign-1",
        campaign_goal="sales",
        target_audience="homeowners",
        platform_history=history,
    )

    assert result["campaign_id"] == "campaign-1"
    assert calls["kwargs"]["platform_history"] == history
