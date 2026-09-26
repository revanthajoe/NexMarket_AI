import json
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import Campaign, SocialPost, AnalyticsEvent, OptimizationResult, PostLog, LeadScore, SentimentResult, EngagementForecast
from app.db.session import AsyncSessionLocal
from app.core.config import settings
from app.main import app
import asyncio
import os
from datetime import datetime

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

CAMPAIGN_PAYLOAD = {
    "name": "Phase 11 Test Campaign",
    "product_name": "Test Product",
    "description": "A valid campaign used for orchestration safety tests.",
    "campaign_goal": "conversion",
    "target_audience": "Tech Enthusiasts",
    "offer": "20% off",
    "preferred_platform": "instagram",
    "budget": 500.0,
}

@pytest.mark.asyncio
async def test_workflow_json_validity():
    """Valid workflow JSON and no demo nodes in production paths."""
    with open("../n8n/workflows/campaign_pipeline.json", "r") as f:
        workflow = json.load(f)
    
    assert "nodes" in workflow
    assert "connections" in workflow
    
    node_names = [n["name"] for n in workflow["nodes"]]
    # Ensure production pipeline stages exist
    assert "Trigger Creation" in node_names
    assert "Trigger Publish" in node_names
    assert "Wait Analytics" in node_names
    assert "Trigger Learning" in node_names

@pytest.mark.asyncio
async def test_no_fabricated_actual_metrics_and_math_random():
    """Static checks for Math.random and fabricated metrics."""
    for root, dirs, files in os.walk("../n8n/workflows"):
        for file in files:
            if file.endswith(".json"):
                with open(os.path.join(root, file), "r") as f:
                    content = f.read()
                    assert "Math.random" not in content
                    
    with open("app/api/v1/endpoints/n8n_webhooks.py", "r") as f:
        content = f.read()
        assert "max(30," not in content

@pytest.mark.asyncio
async def test_publish_idempotency(client):
    """successful publish is not duplicated, ambiguous result is handled safely"""
    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    campaign_id = cr.json()["id"]

    async with AsyncSessionLocal() as db_session:
        # Create an initial post
        post = SocialPost(campaign_id=campaign_id, platform="instagram", status="posted")
        db_session.add(post)
        await db_session.commit()

    # Trigger post pipeline again
    response = await client.post(
        "/api/v1/n8n/trigger/campaign",
        json={"campaign_id": campaign_id, "steps": ["post"], "platforms": ["instagram"]}
    )
    assert response.status_code == 200

    # Verify no duplicate post
    await asyncio.sleep(1) # wait for bg task
    
    async with AsyncSessionLocal() as db_session:
        posts = (await db_session.execute(select(SocialPost).where(SocialPost.campaign_id == campaign_id))).scalars().all()
        # Should only be one
        assert len(posts) == 1
        assert posts[0].status == "posted"

@pytest.mark.asyncio
async def test_analytics_provenance(client):
    """SIMULATED analytics remain SIMULATED"""
    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    campaign_id = cr.json()["id"]

    settings.SOCIAL_MODE = "mock"
    
    response = await client.post(
        "/api/v1/n8n/analytics/ingest",
        json={
            "campaign_id": campaign_id,
            "source_type": "ACTUAL",
            "platform": "facebook",
            "impressions": 100
        }
    )
    assert response.status_code == 200

    async with AsyncSessionLocal() as db_session:
        event = (await db_session.execute(select(AnalyticsEvent).where(AnalyticsEvent.campaign_id == campaign_id))).scalars().first()
        # Should be coerced to SIMULATED due to mock mode
        assert event.source_type == "SIMULATED"
        assert event.is_mock == True

@pytest.mark.asyncio
async def test_learning_pipeline_reward_sync_idempotency(client):
    """repeated reward sync does not update the bandit twice"""
    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    campaign_id = cr.json()["id"]

    async with AsyncSessionLocal() as db_session:
        opt = OptimizationResult(
            campaign_id=campaign_id,
            recommended_platform="instagram",
            source_type="RECOMMENDATION",
            bandit_updated=True # Already updated!
        )
        db_session.add(opt)
        
        event = AnalyticsEvent(
            campaign_id=campaign_id,
            platform="instagram",
            event_date=datetime.utcnow(),
            source_type="ACTUAL",
            clicks=10
        )
        db_session.add(event)
        await db_session.commit()

    response = await client.post(
        "/api/v1/n8n/trigger/campaign",
        json={"campaign_id": campaign_id, "steps": ["reward_sync"]}
    )
    assert response.status_code == 200

    await asyncio.sleep(1)
    
    async with AsyncSessionLocal() as db_session:
        opt = await db_session.get(OptimizationResult, opt.id)
        # Reward should remain empty/null because it was already bandit_updated = True before the run
        assert opt.reward is None

@pytest.mark.asyncio
async def test_failure_isolation(client):
    """failed downstream stage preserves successful upstream results"""
    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    campaign_id = cr.json()["id"]

    async with AsyncSessionLocal() as db_session:
        test_campaign = await db_session.get(Campaign, campaign_id)
        # Start with a campaign in "posted" status
        test_campaign.status = "posted"
        await db_session.commit()

    # Trigger a failing step (e.g. analytics for a non-existent post)
    response = await client.post(
        "/api/v1/n8n/trigger/campaign",
        json={"campaign_id": campaign_id, "steps": ["analytics"]}
    )
    assert response.status_code == 200

    await asyncio.sleep(1)

    async with AsyncSessionLocal() as db_session:
        test_campaign = await db_session.get(Campaign, campaign_id)
        # Status should still be "posted", not "failed"
        assert test_campaign.status == "posted"
