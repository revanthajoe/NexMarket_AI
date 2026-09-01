"""
Backend test suite — covers all services and endpoints.
Run with: pytest tests/ -v
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Health ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


# ── Campaign ──────────────────────────────────────────────────────────────────

CAMPAIGN_PAYLOAD = {
    "name": "Test Summer Sale",
    "product_name": "CloudNotes Pro",
    "description": "AI-powered note-taking app for professionals",
    "offer": "50% off annual subscription",
    "target_audience": "remote workers and students",
    "campaign_goal": "brand_awareness",
    "preferred_platform": "instagram",
    "budget": 500.0,
}


@pytest.mark.asyncio
async def test_create_campaign(client):
    r = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == CAMPAIGN_PAYLOAD["name"]
    assert data["status"] == "draft"
    return data["id"]


@pytest.mark.asyncio
async def test_list_campaigns(client):
    r = await client.get("/api/v1/campaigns/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── Sentiment ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sentiment_analysis(client):
    r = await client.post(
        "/api/v1/sentiment/analyze",
        json={"texts": ["This product is amazing!", "Terrible experience, very bad."]},
    )
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert len(data["results"]) == 2
    assert "summary" in data
    labels = [res["label"] for res in data["results"]]
    assert "positive" in labels
    assert "negative" in labels


# ── Lead Prediction ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lead_prediction(client):
    # Create a campaign first
    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]

    r = await client.post(
        "/api/v1/leads/predict",
        json={
            "campaign_id": cid,
            "lead_identifier": "user_001",
            "clicks": 15,
            "views": 200,
            "time_spent_seconds": 120,
            "prior_purchases": 2,
            "source_platform": "instagram",
            "device": "mobile",
            "age_group": "25-34",
            "location_tier": 1,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert 0 <= data["score"] <= 100
    assert data["category"] in ("hot", "warm", "cold")
    assert 0 <= data["purchase_probability"] <= 1


# ── Poster Generation ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_poster_generation(client):
    """Provider depends on IMAGE_PROVIDER (.env): 'mock', or 'local-sdxl-composed'
    when the real local SDXL/Qwen pipeline is configured — don't hardcode one."""
    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]

    r = await client.post(
        "/api/v1/posters/generate",
        json={"campaign_id": cid, "variations": 1},
    )
    assert r.status_code == 200
    posters = r.json()
    assert len(posters) == 1
    assert "image_url" in posters[0]
    assert posters[0]["provider"] in ("mock", "local-sdxl-composed", "openai-dalle3")


# ── Optimization ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_optimization(client):
    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]

    r = await client.post(
        "/api/v1/optimize/",
        json={"campaign_id": cid, "budget": 500},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["recommended_platform"] in ("instagram", "facebook", "linkedin", "twitter")
    assert 0 <= data["confidence"] <= 1


# ── Dashboard ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dashboard(client):
    r = await client.get("/api/v1/analytics/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert "total_campaigns" in data
    assert "total_posts" in data


# ── Campaign Report (Workflow D) ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_campaign_report(client):
    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]

    r = await client.get(f"/api/v1/analytics/{cid}/report")
    assert r.status_code == 200
    data = r.json()
    assert data["campaign"]["id"] == cid
    assert "creative" in data
    assert "publishing" in data
    assert "analytics_totals" in data
    assert "sentiment" in data
    assert "leads" in data


@pytest.mark.asyncio
async def test_campaign_report_missing_campaign(client):
    r = await client.get("/api/v1/analytics/does-not-exist/report")
    assert r.status_code == 404


# ── Social Posting (mock adapter) ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_social_posting_mock_publish(client):
    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]

    r = await client.post(
        "/api/v1/posting/publish",
        json={"campaign_id": cid, "platform": "instagram"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["campaign_id"] == cid
    assert data["platform"] == "instagram"
    assert data["status"] in ("pending", "posting", "scheduled")


@pytest.mark.asyncio
async def test_platform_health(client):
    r = await client.get("/api/v1/posting/health/platforms")
    assert r.status_code == 200


# ── SDXL seed determinism (pure unit test, no model load) ──────────────────────

def test_poster_seed_is_deterministic():
    """Same (campaign_id, variation, attempt) must always yield the same seed,
    and different variations/attempts must diverge — this is the fix for the
    'poster generation produces different images' issue."""
    from app.services.ai.poster_generator import _derive_seed

    s1 = _derive_seed("campaign-123", variation=0, attempt=1)
    s2 = _derive_seed("campaign-123", variation=0, attempt=1)
    assert s1 == s2, "identical inputs must produce identical seeds"

    s_other_variation = _derive_seed("campaign-123", variation=1, attempt=1)
    assert s_other_variation != s1, "different variations should get different seeds"

    s_other_attempt = _derive_seed("campaign-123", variation=0, attempt=2)
    assert s_other_attempt != s1, "different attempts should get different seeds"

    s_other_campaign = _derive_seed("campaign-456", variation=0, attempt=1)
    assert s_other_campaign != s1, "different campaigns should get different seeds"
