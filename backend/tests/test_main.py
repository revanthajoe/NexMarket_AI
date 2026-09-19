"""
Backend test suite — covers all services and endpoints.
Run with: pytest tests/ -v
"""
import asyncio

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


# ── Environment sanity — runs before anything else imports torch ─────────────
#
# torch 2.1.2 is a C-extension built against numpy 1.x's ABI; numpy>=2 breaks
# the boundary between them. This has silently drifted before: something (most
# likely rembg, which requires numpy>=2.3 and is a documented, accepted `pip
# check` conflict) pulled numpy up to 2.4.6 in this venv along with scipy/
# pandas/scikit-learn/xgboost moving with it. `pip check` reported nothing
# wrong — the packages were internally consistent with EACH OTHER, just not
# with the torch pin — and the actual failure only surfaced three minutes into
# an unrelated SDXL scheduler load as `RuntimeError: Numpy is not available`.
#
# A bare `import torch` is not sufficient to catch this: the import succeeds
# and only warns ("Failed to initialize NumPy: _ARRAY_API not found"). The
# boundary itself must be exercised.
def test_numpy_torch_abi_compatible():
    import numpy as np
    import torch

    assert np.__version__.split(".")[0] == "1", (
        f"numpy {np.__version__} is installed; torch 2.1.2 requires numpy<2. "
        f"Reinstall with: pip install \"numpy>=1.26.0,<2.0.0\" --force-reinstall"
    )
    # The actual boundary that broke: torch tensor -> numpy array via the C API.
    result = torch.tensor([1.0, 2.0]).numpy()
    assert list(result) == [1.0, 2.0]


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


# ── Ad Copy ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_adcopy_generate(client):
    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]

    r = await client.post(
        "/api/v1/adcopy/generate",
        json={
            "campaign_id": cid,
            "platforms": ["instagram", "telegram"],
            "tone": "playful",
            "language": "en",
        },
    )
    assert r.status_code == 200
    copies = r.json()
    assert len(copies) >= 1
    assert {c["platform"] for c in copies} <= {"instagram", "telegram"}
    for c in copies:
        assert c["body"]
        assert c["campaign_id"] == cid


@pytest.mark.asyncio
async def test_adcopy_generate_missing_campaign(client):
    r = await client.post(
        "/api/v1/adcopy/generate",
        json={"campaign_id": "does-not-exist", "platforms": ["instagram"]},
    )
    assert r.status_code == 404


# ── Forecasting (LSTM) ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_forecast_create(client):
    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]

    r = await client.post("/api/v1/forecast/", json={"campaign_id": cid, "horizon_days": 7})
    assert r.status_code == 200
    data = r.json()
    assert data["campaign_id"] == cid
    assert data["forecast_horizon_days"] == 7


# ── Analytics time series ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analytics_timeseries(client):
    r = await client.get("/api/v1/analytics/engagement/timeseries?days=14")
    assert r.status_code == 200
    points = r.json()
    assert isinstance(points, list)
    # Must never fabricate data — an empty DB returns an empty series.
    for p in points:
        assert {"date", "impressions", "clicks", "likes", "reach"} <= set(p)


@pytest.mark.asyncio
async def test_analytics_platform_breakdown(client):
    r = await client.get("/api/v1/analytics/engagement/platforms?days=14")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    for row in rows:
        assert {"platform", "impressions", "ctr", "engagement_rate", "is_mock"} <= set(row)
        # CTR must be derived from the summed totals, never > 1.
        assert 0 <= row["ctr"] <= 1


@pytest.mark.asyncio
async def test_analytics_tracking_status(client):
    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]

    r = await client.get(f"/api/v1/analytics/tracking/status?campaign_id={cid}")
    assert r.status_code == 200
    s = r.json()
    assert s["campaign_id"] == cid
    # A brand-new campaign has no events, so the tab must not claim real data.
    assert s["event_count"] == 0
    assert s["has_real_data"] is False
    assert s["last_synced_at"] is None


# ── n8n orchestration ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_n8n_trigger_and_status(client):
    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]

    # Trigger with no steps so nothing heavy runs — this test guards the
    # trigger/poll contract the UI's Run Pipeline button depends on.
    r = await client.post(
        "/api/v1/n8n/trigger/campaign",
        json={"campaign_id": cid, "steps": []},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"

    s = await client.get(f"/api/v1/n8n/status/{cid}")
    assert s.status_code == 200
    body = s.json()
    assert body["campaign_id"] == cid
    assert body["status"] in ("draft", "generating", "ready", "posted", "failed")
    assert isinstance(body["posts"], list)


@pytest.mark.asyncio
async def test_n8n_post_step_publishes_platforms_independently(client, monkeypatch):
    """
    Regression: the n8n-triggered pipeline's "post" step used to publish to
    exactly ONE platform and `raise` on failure — which propagated to the
    outer handler and marked the ENTIRE campaign "failed" even though every
    other step had succeeded. It now publishes to every platform in
    `platforms` independently, via the same `publish_platforms()` the
    standalone /posting/campaign/{id}/publish endpoint uses.
    """
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.models import Campaign, SocialPost
    from app.services.posting import posting_service as ps
    from app.services.posting.adapters import MockAdapter, PostResult

    class FailingAdapter(MockAdapter):
        async def post(self, payload):
            return PostResult(success=False, error="forced failure for test")

    real_get_adapter = ps._get_adapter

    def fake_get_adapter(platform):
        return FailingAdapter(platform) if platform == "instagram" else real_get_adapter(platform)

    monkeypatch.setattr(ps, "_get_adapter", fake_get_adapter)

    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]

    r = await client.post(
        "/api/v1/n8n/trigger/campaign",
        json={"campaign_id": cid, "steps": ["post"], "platforms": ["instagram", "telegram"]},
    )
    assert r.status_code == 200

    async with AsyncSessionLocal() as db:
        campaign = await db.get(Campaign, cid)
        # The campaign itself must NOT be marked failed just because one
        # platform's publish failed.
        assert campaign.status != "failed", (
            f"one platform failing must not fail the whole campaign, got {campaign.status!r}"
        )

        rows = (await db.execute(
            select(SocialPost).where(SocialPost.campaign_id == cid)
        )).scalars().all()
        by_platform = {row.platform: row for row in rows}
        assert set(by_platform) == {"instagram", "telegram"}
        assert by_platform["instagram"].status == "failed"
        assert by_platform["telegram"].status == "posted", (
            "telegram must still publish even though instagram failed"
        )


@pytest.mark.asyncio
async def test_n8n_post_step_defaults_platforms_from_campaign(client):
    """No `platforms` field (every caller before this change, including the
    checked-in n8n workflow JSON) must keep publishing to preferred_platform."""
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.models import SocialPost

    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]
    assert CAMPAIGN_PAYLOAD["preferred_platform"] == "instagram"

    r = await client.post(
        "/api/v1/n8n/trigger/campaign",
        json={"campaign_id": cid, "steps": ["post"]},  # no "platforms" key at all
    )
    assert r.status_code == 200

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(SocialPost).where(SocialPost.campaign_id == cid)
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].platform == "instagram"
        assert rows[0].status == "posted"


@pytest.mark.asyncio
async def test_n8n_status_missing_campaign(client):
    r = await client.get("/api/v1/n8n/status/does-not-exist")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_n8n_status_self_heals_stale_generating(client):
    """A campaign left in 'generating' with no update in 20+ minutes is orphaned
    (the pipeline's background task died — e.g. the dev server restarted mid-run)
    rather than merely slow. Nothing else will ever revive it, so the status
    endpoint itself must mark it failed instead of letting a poller spin forever."""
    from datetime import datetime, timedelta

    from app.db.session import AsyncSessionLocal
    from app.models.models import Campaign

    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]

    async with AsyncSessionLocal() as db:
        c = await db.get(Campaign, cid)
        c.status = "generating"
        c.updated_at = datetime.utcnow() - timedelta(minutes=25)
        await db.commit()

    s = await client.get(f"/api/v1/n8n/status/{cid}")
    assert s.status_code == 200
    assert s.json()["status"] == "failed"


# ── Poster Generation ────────────────────────────────────────────────────────

@pytest.mark.heavy
@pytest.mark.asyncio
async def test_poster_generation(client):
    """Provider depends on IMAGE_PROVIDER (.env): 'mock', or 'local-sdxl-composed'
    when the real local SDXL/Qwen pipeline is configured — don't hardcode one.

    Marked `heavy`: with IMAGE_PROVIDER=local this loads Qwen2.5-3B + SDXL +
    Qwen2.5-VL and takes ~12 minutes. On the 6GB dev GPU it must run in its own
    process — sharing one with the other model-loading tests leaves the CUDA
    allocator too fragmented for SDXL, which then falls back to CPU and dies on
    `"addmm_impl_cpu_" not implemented for 'Half'` (fp16 matmul is CPU-only
    unsupported). Run with: pytest -m heavy
    """
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
    assert data["recommended_platform"] in ("instagram", "facebook", "telegram", "whatsapp")
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
async def test_publish_marks_posted_not_stuck_posting(client):
    """
    Regression: the row must not be left at `posting` once the background task
    has published it.

    The endpoint originally assigned `status = "posting"` AFTER committing, so
    the attribute stayed dirty on the request's session and get_db()'s
    post-yield commit reverted the task's `posted`. Rows ended up published
    (platform_post_id populated) but permanently reported as in-flight.
    """
    from app.db.session import AsyncSessionLocal
    from app.models.models import SocialPost

    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]

    r = await client.post(
        "/api/v1/posting/publish",
        json={"campaign_id": cid, "platform": "telegram"},
    )
    assert r.status_code == 200
    post_id = r.json()["id"]

    async with AsyncSessionLocal() as db:
        sp = await db.get(SocialPost, post_id)
        assert sp.platform_post_id, "mock adapter should always return an id"
        assert sp.status == "posted", (
            f"published (id={sp.platform_post_id}) but status stuck at {sp.status!r}"
        )


@pytest.mark.asyncio
async def test_campaign_publish_all_platforms_independently(client):
    """Every supported platform publishes, each with its own row and status."""
    from app.db.session import AsyncSessionLocal
    from app.models.models import SocialPost
    from app.services.posting.posting_service import SUPPORTED_PLATFORMS

    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]

    r = await client.post(
        f"/api/v1/posting/campaign/{cid}/publish",
        json={"platforms": SUPPORTED_PLATFORMS},
    )
    assert r.status_code == 200
    rows = r.json()
    assert {x["platform"] for x in rows} == set(SUPPORTED_PLATFORMS)

    async with AsyncSessionLocal() as db:
        for row in rows:
            sp = await db.get(SocialPost, row["id"])
            assert sp.status == "posted", f"{sp.platform} -> {sp.status}"
            assert sp.platform_post_id.startswith(f"mock_{sp.platform}_")
            assert sp.is_mock is True


@pytest.mark.asyncio
async def test_campaign_publish_rejects_unknown_platform(client):
    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]
    r = await client.post(
        f"/api/v1/posting/campaign/{cid}/publish",
        json={"platforms": ["instagram", "myspace"]},
    )
    assert r.status_code == 422
    assert "myspace" in r.json()["detail"]


@pytest.mark.asyncio
async def test_campaign_publish_missing_campaign(client):
    r = await client.post(
        "/api/v1/posting/campaign/does-not-exist/publish",
        json={"platforms": ["telegram"]},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_one_platform_failure_leaves_others_published(client, monkeypatch):
    """
    The core independence guarantee: a platform that fails must not prevent the
    others from publishing. Instagram is forced to fail; Telegram and Facebook
    must still reach `posted`.
    """
    from app.db.session import AsyncSessionLocal
    from app.models.models import SocialPost
    from app.services.posting import posting_service as ps
    from app.services.posting.adapters import MockAdapter, PostResult

    class FailingAdapter(MockAdapter):
        async def post(self, payload):
            return PostResult(success=False, error="forced failure for test")

    real_get_adapter = ps._get_adapter

    def fake_get_adapter(platform):
        if platform == "instagram":
            return FailingAdapter(platform)
        return real_get_adapter(platform)

    monkeypatch.setattr(ps, "_get_adapter", fake_get_adapter)

    # Skip the retry backoff (~14s across 4 attempts). `ps.asyncio` IS the
    # global asyncio module, so the replacement must close over the ORIGINAL
    # sleep — referring to `asyncio.sleep` inside the replacement would call
    # the replacement itself and recurse until RecursionError, which then got
    # swallowed by the endpoint's per-platform except and left the row at
    # `posting` instead of `failed`.
    real_sleep = asyncio.sleep

    async def no_backoff(_seconds):
        await real_sleep(0)

    monkeypatch.setattr(ps.asyncio, "sleep", no_backoff)

    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]

    r = await client.post(
        f"/api/v1/posting/campaign/{cid}/publish",
        json={"platforms": ["instagram", "facebook", "telegram"]},
    )
    assert r.status_code == 200
    by_platform = {x["platform"]: x["id"] for x in r.json()}

    async with AsyncSessionLocal() as db:
        ig = await db.get(SocialPost, by_platform["instagram"])
        assert ig.status == "failed", f"instagram should have failed, got {ig.status}"
        assert ig.error_message

        for ok_platform in ("facebook", "telegram"):
            sp = await db.get(SocialPost, by_platform[ok_platform])
            assert sp.status == "posted", (
                f"{ok_platform} must publish even though instagram failed, "
                f"got {sp.status}"
            )


@pytest.mark.asyncio
async def test_platform_health(client):
    r = await client.get("/api/v1/posting/health/platforms")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_integrations_status(client):
    """`configured` must be reported separately from `healthy` — the mock
    adapter always answers healthy, which alone would claim a live connection
    for platforms that have no credentials at all."""
    r = await client.get("/api/v1/posting/integrations/status")
    assert r.status_code == 200
    status = r.json()
    for platform in ("instagram", "facebook", "telegram", "whatsapp"):
        assert platform in status
        assert set(status[platform]) == {"configured", "healthy", "mode"}
        assert status[platform]["mode"] in ("live", "mock")


@pytest.mark.asyncio
async def test_metrics_sync(client):
    cr = await client.post("/api/v1/campaigns/", json=CAMPAIGN_PAYLOAD)
    cid = cr.json()["id"]

    r = await client.post(f"/api/v1/posting/metrics/sync/{cid}")
    assert r.status_code == 200
    data = r.json()
    assert data["campaign_id"] == cid
    # No posts published yet, so nothing to pull back.
    assert data["posts_checked"] == 0
    assert data["synced"] == 0


@pytest.mark.asyncio
async def test_metrics_sync_missing_campaign(client):
    r = await client.post("/api/v1/posting/metrics/sync/does-not-exist")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_run_scheduled_posts(client):
    r = await client.post("/api/v1/posting/scheduled/run")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert isinstance(r.json()["published"], int)


def test_mock_metrics_are_deterministic():
    """Repeated syncs of the same post must not make the numbers jump around,
    and mock-sourced metrics must stay flagged so callers can label them."""
    import asyncio

    from app.services.posting.adapters import MockAdapter

    adapter = MockAdapter("instagram")
    a = asyncio.run(adapter.fetch_metrics("mock_instagram_abc123"))
    b = asyncio.run(adapter.fetch_metrics("mock_instagram_abc123"))
    c = asyncio.run(adapter.fetch_metrics("mock_instagram_zzz999"))

    assert a.as_dict() == b.as_dict()
    assert a.as_dict() != c.as_dict()
    assert a.is_mock and a.ok
    assert a.ctr == round(a.clicks / a.impressions, 6)


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


# ── Brochure spec normalizer ─────────────────────────────────────────────────
# Pure logic, no GPU/model needed. The brochure layout engine draws a fixed
# number of zones, so these guard the shape contract it relies on.

from app.prompts.templates import (
    FEATURE_COUNT,
    WHY_ITEM_COUNT,
    build_brochure_prompt,
    normalize_brochure_spec,
)

_CTX = {
    "product_name":  "Birla Opus Alldry 14",
    "campaign_name": "Monsoon Protection Drive",
    "offer":         "10% free paints",
    "language":      "ta",
}


def _assert_valid(spec):
    """Every guarantee the layout engine depends on."""
    assert len(spec["features"]) == FEATURE_COUNT
    assert len(spec["why_items_en"]) == WHY_ITEM_COUNT
    assert len(spec["why_items_local"]) == WHY_ITEM_COUNT
    for key in ("headline", "subheadline", "why_title", "offer"):
        assert isinstance(spec[f"{key}_en"], str)
        assert isinstance(spec[f"{key}_local"], str)
    for feat in spec["features"]:
        assert feat["label_en"], "feature label must never be empty"
        assert feat["label_local"], "local label must fall back to English, not stay empty"
    assert spec["headline_en"], "headline has no acceptable empty state"


def test_brochure_spec_empty_input_falls_back():
    spec = normalize_brochure_spec({}, _CTX)
    _assert_valid(spec)
    assert spec["fallback"] is True, "synthetic copy must be flagged, not silently passed off as real"


def test_brochure_spec_none_input_falls_back():
    _assert_valid(normalize_brochure_spec(None, _CTX))


def test_brochure_spec_truncates_excess_features():
    raw = {
        "headline_en": "Protect your home",
        "features": [
            {"label_en": f"Feature {i}", "label_local": f"L{i}", "value": "YES"}
            for i in range(7)
        ],
    }
    spec = normalize_brochure_spec(raw, _CTX)
    _assert_valid(spec)
    assert spec["features"][0]["label_en"] == "Feature 0"


def test_brochure_spec_pads_missing_features():
    raw = {"headline_en": "Protect your home", "features": [
        {"label_en": "Crack Bridging", "value": "PROVEN"},
    ]}
    spec = normalize_brochure_spec(raw, _CTX)
    _assert_valid(spec)
    assert spec["fallback"] is True, "padding means the model under-delivered"


def test_brochure_spec_fills_missing_local_from_english():
    raw = {
        "headline_en": "Monsoon is coming",
        "features": [
            {"label_en": "Crack Bridging", "value": "PROVEN"} for _ in range(FEATURE_COUNT)
        ],
    }
    spec = normalize_brochure_spec(raw, _CTX)
    assert spec["headline_local"] == "Monsoon is coming"
    for feat in spec["features"]:
        assert feat["label_local"] == feat["label_en"]


def test_brochure_spec_accepts_why_items_as_string():
    raw = {
        "headline_en": "Monsoon is coming",
        "why_items_en": "Durable, Heat reflective, Rainproof, Easy to apply",
    }
    spec = normalize_brochure_spec(raw, _CTX)
    _assert_valid(spec)
    assert "Durable" in spec["why_items_en"]


def test_brochure_spec_clamps_word_budgets():
    raw = {"headline_en": " ".join(["word"] * 40)}
    spec = normalize_brochure_spec(raw, _CTX)
    assert len(spec["headline_en"].split()) <= 6


def test_brochure_spec_clean_input_is_not_flagged_fallback():
    raw = {
        "headline_en": "Monsoon is coming",   "headline_local": "மழைக்காலம் வருது",
        "subheadline_en": "Protect your home", "subheadline_local": "உங்கள் வீட்டை பாதுகாக்கவும்",
        "features": [
            {"label_en": "Warranty",  "label_local": "உத்திரவாதம்", "value": "14 YEAR"},
            {"label_en": "Cooler",    "label_local": "குளுமை",      "value": "12 C"},
            {"label_en": "Crack",     "label_local": "வெடிப்பு",     "value": "BRIDGED"},
            {"label_en": "Walls",     "label_local": "சுவர்கள்",      "value": "AND ROOFS"},
        ],
        "why_title_en": "Why Alldry 14?", "why_title_local": "ஏன் ஆல்ட்ரை?",
        "why_items_en":    ["Ultra durable", "Heat reflective", "Rainproof", "Easy application"],
        "why_items_local": ["நீடித்த", "வெப்பத்தை தடுக்கும்", "மழைநீர் தடுப்பு", "எளிதான பயன்பாடு"],
        "offer_en": "10% free paints", "offer_local": "10% இலவச பெயிண்ட்",
    }
    spec = normalize_brochure_spec(raw, _CTX)
    _assert_valid(spec)
    assert spec["fallback"] is False, "well-formed model output must not be flagged"
    assert spec["headline_local"] == "மழைக்காலம் வருது"
    assert spec["language"] == "ta"


def test_brochure_prompt_states_language_and_limits():
    prompt = build_brochure_prompt(
        product_name="Birla Opus", campaign_name="Monsoon", description="Waterproof coating",
        offer="10% off", target_audience="homeowners", campaign_goal="sales", language="ta",
    )
    assert "Tamil" in prompt
    assert "transliteration" in prompt, "must forbid transliteration, else Tamil comes back romanized"
    assert str(FEATURE_COUNT) in prompt


def test_brochure_prompt_protects_the_brand_name():
    """
    The model translated "Birla Opus Paints" into Tamil as "பிறந்த உபோஸ பின்னர்"
    and it shipped onto a real poster as the headline. The prompt must forbid it
    and must keep the brand out of the headline, which the header already shows.
    """
    prompt = build_brochure_prompt(
        product_name="Birla Opus Paints", campaign_name="Pongal", description="Paints",
        offer="10% off", target_audience="homeowners", campaign_goal="sales",
        language="ta", brand_name="Birla Opus Paints",
    )
    assert "NEVER translate or transliterate" in prompt
    assert "Birla Opus Paints" in prompt
    assert "headline must be a benefit" in prompt.lower() or "NOT the brand name" in prompt


# ── Evaluation scoring ───────────────────────────────────────────────────────

def test_fallback_evaluation_never_counts_as_approval():
    """
    _FALLBACK_EVALUATION's synthetic score is 72.5, which is ABOVE the 70
    approval threshold. Taken at face value an evaluator outage silently
    "approves" every poster on attempt 1 and the improvement retry never fires.
    """
    from app.services.ai.poster_evaluator import _FALLBACK_EVALUATION, poster_evaluator
    from app.services.ai.poster_generator import _effective_score

    assert _FALLBACK_EVALUATION["overall_score"] > 70, \
        "guard assumes the synthetic score clears the threshold"

    fell_back = poster_evaluator.normalize(_FALLBACK_EVALUATION)
    assert fell_back["fallback"] is True
    assert _effective_score(fell_back) < 70, "a fallback evaluation must not pass the gate"

    real = poster_evaluator.normalize({"overall_score": 82, "dimensions": {}})
    assert _effective_score(real) == 82


def test_evaluation_dict_persists_without_double_normalizing():
    """
    `evaluate()` already returns the normalized dict. Normalizing it a second
    time reads sub-scores from a nested "dimensions" key it no longer has and
    zeroes every dimension — and the extra "fallback" key is not a column, so
    splatting it into the ORM model raised TypeError. Both happened in the n8n
    pipeline, so that step never persisted an evaluation.
    """
    from app.models.models import PosterEvaluation
    from app.services.ai.poster_evaluator import poster_evaluator

    once = poster_evaluator.normalize({
        "overall_score": 84,
        "dimensions": {"readability": 88, "layout": 80, "branding": 75,
                       "contrast": 90, "cta_visibility": 82, "visual_appeal": 79},
    })
    assert once["readability_score"] == 88

    twice = poster_evaluator.normalize(once)
    assert twice["readability_score"] == 0, "double-normalize must be shown to destroy dimensions"

    # "fallback" is returned but is not a column — splatting it raises.
    columns = {c.name for c in PosterEvaluation.__table__.columns}
    assert "fallback" in once and "fallback" not in columns

    ev = PosterEvaluation(poster_id="p1",
                          **{k: v for k, v in once.items() if k in columns})
    assert ev.readability_score == 88 and ev.overall_score == 84


def test_transient_errors_are_retried_but_quota_is_not():
    """503 clears in seconds; a quota limit of 0 is a billing state that never does."""
    from ai.llm.gemini_service import _is_transient

    assert _is_transient(Exception("503 UNAVAILABLE: high demand")) is True
    assert _is_transient(Exception("500 INTERNAL")) is True
    assert _is_transient(Exception("Quota exceeded ... limit: 0, model: x")) is False
    assert _is_transient(Exception("404 NOT_FOUND: no such model")) is False


def test_gemini_missing_package_raises_actionable_error():
    """
    A missing google-genai must surface install instructions, not a raw
    ModuleNotFoundError. The `types` import used to run before the guard.
    """
    import builtins
    from ai.imagegen.gemini_service import GeminiImageError
    from ai.llm.gemini_service import GeminiLLMService

    svc = GeminiLLMService()
    real_import = builtins.__import__

    def blocked(name, *a, **k):
        if name == "google" or name.startswith("google."):
            raise ImportError("No module named 'google'")
        return real_import(name, *a, **k)

    builtins.__import__ = blocked
    try:
        with pytest.raises(GeminiImageError) as excinfo:
            svc._get_client()
        assert "google-genai" in str(excinfo.value)
    finally:
        builtins.__import__ = real_import


# ── Icon library (badge icons) ───────────────────────────────────────────────
# Feature badges moved from plain circles to icon-in-circle-then-caption
# (matching the reference brochure design). The matcher must generalize across
# product categories, not just paint — this is the test that proves it.

def test_pick_icon_generalizes_across_product_categories():
    from app.services.ai.icon_library import pick_icon

    cases = [
        ("14 Year Warranty", "shield"),           # paint
        ("2 Year Warranty", "shield"),             # electronics
        ("10 Year Guarantee", "shield"),           # mattress
        ("Crack Bridging", "crack_shield"),        # paint
        ("Rainproof", "droplet"),                  # paint
        ("Waterproof Case", "droplet"),            # phone accessory
        ("12 C Cooler", "thermometer"),            # paint
        ("Walls & Roofs", "house"),                # paint
        ("Eco-Friendly", "leaf"),                  # paint / cosmetics
        ("100% Cotton", "leaf"),                   # textiles
        ("ISO Certified", "check"),                # any category
        ("Doctor Recommended", "check"),           # health / food
        ("Best Price", "tag"),                     # any category
        ("EMI Available", "tag"),                  # electronics / furniture
        ("10% Free Paints", "tag"),                # paint
        ("Bluetooth 5.0", "star"),                 # electronics, unmatched -> fallback
        ("Wide Colour Range", "star"),              # paint, unmatched -> fallback
        ("Handmade", "star"),                       # crafts, unmatched -> fallback
    ]
    for label, expected in cases:
        assert pick_icon(label) == expected, f"{label!r} -> expected {expected}"


def test_pick_icon_avoids_substring_false_positives():
    """
    Naive substring matching classified "Doctor Recommended" as `leaf`, because
    "eco" is a literal substring of "recommended" (r-ECO-mmended). Word-boundary
    matching is what keeps short keyword fragments safe to write.
    """
    from app.services.ai.icon_library import pick_icon
    assert pick_icon("Doctor Recommended") != "leaf"


# ── Model-loading smoke tests ────────────────────────────────────────────────
# Verify each non-GPU-heavy model service actually initializes and produces a
# well-formed result. Deliberately NOT marked `heavy`: these are the small
# models (DistilBERT/XGBoost/LSTM) plus a pure-CPU bandit, and they are exactly
# what a numpy/torch ABI break or a missing weights file silently takes out.
# SDXL and Qwen-VL stay out of the fast suite.

def test_smoke_distilbert_loads_and_classifies():
    from ai.sentiment.distilbert_service import DistilBERTService

    svc = DistilBERTService()
    svc.load()
    try:
        assert svc.is_loaded
        results = svc.analyze(["This product is fantastic", "This was terrible"])
        assert len(results) == 2
        labels = [r["label"] for r in results]
        assert "positive" in labels and "negative" in labels
    finally:
        svc.unload()


def test_smoke_xgboost_loads_and_scores():
    from ai.lead.xgboost_service import XGBoostService

    svc = XGBoostService()
    svc.load()
    try:
        assert svc.is_loaded
        out = svc.predict(
            clicks=12, views=180, time_spent_seconds=95, prior_purchases=1,
            source_platform="instagram", device="mobile",
            age_group="25-34", location_tier=1,
        )
        assert 0 <= out["score"] <= 100
        assert 0.0 <= out["purchase_probability"] <= 1.0
        assert out["category"] in ("hot", "warm", "cold")
    finally:
        svc.unload()


def test_smoke_lstm_loads_and_forecasts():
    import numpy as np
    from ai.forecasting.lstm_service import LSTMService

    svc = LSTMService()
    svc.load()
    try:
        assert svc.is_loaded
        # (timesteps, 5) — likes, shares, comments, ctr, reach. A 1-D series is
        # NOT accepted: the scaler is per-feature and broadcasting fails.
        history = np.tile(
            np.linspace(100, 200, 20, dtype=np.float32).reshape(-1, 1), (1, 5)
        )
        out = svc.forecast(history, horizon_days=7)
        # One series per feature, each `horizon_days` long.
        for key in ("predicted_likes", "predicted_shares", "predicted_comments",
                    "predicted_ctr", "predicted_reach"):
            assert len(out[key]) == 7, f"{key} -> {len(out[key])}"
        assert out["model_version"]
    finally:
        svc.unload()


def test_smoke_thompson_sampling_bandit():
    """Pure CPU — no load/unload lifecycle, but still worth pinning."""
    from ai.optimization.bandit_service import BanditService

    svc = BanditService()
    out = svc.select_arm(campaign_goal="sales", budget=500.0,
                         target_audience="homeowners")
    assert out["recommended_platform"] in out["platform_scores"]
    assert 0.0 <= out["confidence"] <= 1.0

    # Reward feedback must actually move the arm's statistics.
    before = svc.arm_stats()[out["recommended_platform"]]
    svc.record_reward(out["recommended_platform"], clicked=True)
    after = svc.arm_stats()[out["recommended_platform"]]
    assert after != before


# ── Marketing-copy provider routing ──────────────────────────────────────────
# AI_TEXT_PROVIDER governs everything that writes marketing copy: poster
# brochure copy, the SDXL scene spec, poster evaluation, AND ad copy.
#
# Ad copy was deliberately EXCLUDED from this switch when it only covered the
# poster phase, and an earlier test asserted that exclusion. That requirement
# was reversed on evidence: Qwen2.5-3B could not emit parseable JSON for Tamil
# ad copy on either attempt, so requests silently returned a hardcoded English
# template. Ad copy now shares the switch by design.

@pytest.mark.asyncio
async def test_ai_text_provider_routes_both_poster_and_adcopy(monkeypatch):
    import ai.inference_manager as im
    import ai.llm.gemini_service as gs
    from app.core.config import settings
    from app.services.ai import text_provider as tp

    monkeypatch.setattr(settings, "AI_TEXT_PROVIDER", "gemini")
    calls: list[str] = []

    async def fake_qwen_spec(system, user, temperature=0.7):
        calls.append("qwen"); return {}

    async def fake_gemini_json(system, user, temperature=0.7):
        calls.append("gemini"); return {}

    monkeypatch.setattr(im.inference_manager, "generate_visual_spec", fake_qwen_spec)
    monkeypatch.setattr(gs.gemini_llm_service, "generate_json", fake_gemini_json)

    await tp.generate_marketing_json("sys", "user")
    assert calls == ["gemini"], f"must route to Gemini, got {calls}"

    # ...and the local setting still reaches Qwen, so the escape hatch works.
    calls.clear()
    monkeypatch.setattr(settings, "AI_TEXT_PROVIDER", "local")
    await tp.generate_marketing_json("sys", "user")
    assert calls == ["qwen"], f"AI_TEXT_PROVIDER=local must use Qwen, got {calls}"


def test_adcopy_routes_through_the_shared_text_provider():
    """
    The fix for non-English ad copy. Ad copy must go through the shared
    provider switch, not call inference_manager (Qwen) directly — calling Qwen
    directly is what produced English output for every requested language.
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "app" / "services" / "ai" / "ad_generator.py").read_text(encoding="utf-8")
    assert "generate_marketing_json" in src
    assert "inference_manager.generate_ad_copy" not in src


def test_legacy_provider_setting_name_still_honoured(monkeypatch):
    """An existing .env setting only POSTER_PHASE_PROVIDER must keep working."""
    from app.core.config import Settings
    monkeypatch.setenv("POSTER_PHASE_PROVIDER", "local")
    monkeypatch.delenv("AI_TEXT_PROVIDER", raising=False)
    assert Settings().AI_TEXT_PROVIDER == "local"

    # An explicit new-name setting wins over the legacy one.
    monkeypatch.setenv("AI_TEXT_PROVIDER", "gemini")
    assert Settings().AI_TEXT_PROVIDER == "gemini"


# ── Layout tier selection ────────────────────────────────────────────────────
# These guard the regression that made every poster look bad for weeks: the old
# `has_brochure_assets()` gate required a product cutout AND contact details.
# No campaign ever had either and the dashboard could not upload them, so the
# gate was false 100% of the time and the zone layout engine never ran once —
# every poster silently fell back to four text elements over a photo. The rule
# now is that there is no such fallback tier at all.

from PIL import Image
from app.services.ai.brand_kit import BrandKit
from app.services.ai.brochure_composer import _zone_boxes, _ZONE_ORDER


def test_empty_brand_kit_still_gets_a_designed_layout():
    """A campaign with nothing uploaded must still get a real layout."""
    assert BrandKit(campaign_id="empty").pick_layout() == "designed"


def test_pick_layout_never_returns_a_bare_tier():
    """No combination of assets may select a non-designed layout."""
    from itertools import product as _iproduct

    for cutout, phone, addr, logo in _iproduct([None, "c.png"], [None, "123"],
                                               [None, "somewhere"], [None, "l.png"]):
        kit = BrandKit(campaign_id="x", product_cutout_path=cutout,
                       phone=phone, address_en=addr, logo_path=logo)
        assert kit.pick_layout() in ("designed", "brochure")


def test_full_assets_unlock_the_brochure_tier():
    kit = BrandKit(campaign_id="x", product_cutout_path="cut.png", phone="+91 99999 99999")
    assert kit.pick_layout() == "brochure"
    assert kit.has_contact_details() is True


def test_cutout_without_contact_stays_designed():
    """The footer needs contact info; a cutout alone must not summon an empty strip."""
    kit = BrandKit(campaign_id="x", product_cutout_path="cut.png")
    assert kit.pick_layout() == "designed"
    assert kit.has_contact_details() is False


def test_zone_boxes_tile_the_canvas_exactly():
    """Absent zones must redistribute their height, never leave a gap."""
    for present in ({"header", "headline", "hero", "spec", "offer"},
                    set(_ZONE_ORDER)):
        boxes = _zone_boxes(1080, 1080, present)
        assert set(boxes) == present
        ordered = [boxes[z] for z in _ZONE_ORDER if z in present]
        assert ordered[0][1] == 0, "first zone must start at the top edge"
        assert ordered[-1][3] == 1080, "last zone must reach the bottom edge"
        for a, b in zip(ordered, ordered[1:]):
            assert a[3] == b[1], "zones must tile with no gap or overlap"


def test_mixed_tamil_latin_renders_both_scripts():
    """
    Correct Tamil copy keeps brand names in Latin ("10% இலவச Birla Opus Paints").
    NotoSansTamil has no Latin glyphs, so a single-font render turned the brand
    name into tofu boxes on a real poster. Runs must split by coverage.
    """
    from app.services.ai import text_shaper as ts
    if not ts.shaping_available():
        pytest.skip("HarfBuzz/FreeType not installed")

    tamil_font = str(ts.FONT_TAMIL_BOLD)
    assert ts._font_has_char(tamil_font, "ஏ") is True
    assert ts._font_has_char(tamil_font, "B") is False, \
        "if the Tamil font gained Latin coverage this guard is obsolete"

    runs = ts._runs_with_fonts("ஏன் Birla Opus Paints?", tamil_font)
    fonts_used = {f for _, f in runs}
    assert len(fonts_used) == 2, f"expected a Tamil run and a Latin run, got {runs}"
    assert any("Birla" in r for r, _ in runs)

    img = ts.render_text("ஏன் Birla Opus Paints?", tamil_font, 40)
    assert img.width > 100 and img.height > 10


def test_zone_text_is_held_inside_its_box():
    """Long bilingual copy must shrink to fit, not spill into the next zone."""
    from app.services.ai.brochure_composer import BrochureComposer
    from app.services.ai import text_shaper as ts
    if not ts.shaping_available():
        pytest.skip("HarfBuzz/FreeType not installed")

    c = BrochureComposer()
    long_line = " | ".join(["நீண்ட கால சிறந்த பொலிவு"] * 4)
    font = c._font_path(long_line, bold=False)

    # The unconstrained wrap is taller than the box it was given...
    assert c._block_height(long_line, font, 40, 900) > 120
    # ...so the fitted draw must shrink until it fits.
    canvas = Image.new("RGBA", (1080, 1080), (0, 0, 0, 255))
    used = c._draw_fitted(canvas, long_line, 540, 100, 900, 120, 40, (255, 255, 255, 255))
    assert 0 < used <= 120, f"drew {used}px into a 120px budget"


def test_dropping_the_footer_grows_the_other_zones():
    """The footer's height is reclaimed, not abandoned."""
    with_footer = _zone_boxes(1080, 1080, set(_ZONE_ORDER))
    without     = _zone_boxes(1080, 1080, set(_ZONE_ORDER) - {"footer"})
    hero_with    = with_footer["hero"][3] - with_footer["hero"][1]
    hero_without = without["hero"][3]    - without["hero"][1]
    assert hero_without > hero_with, "hero must absorb part of the freed footer height"


# ── SDXL long-prompt chunked encoding ────────────────────────────────────────
# Pure tensor-shape logic against fake tokenizer/encoder stand-ins - no need to
# load the real 6.9GB SDXL pipeline to verify the chunking math is correct.
# See ai/diffusion/sdxl_service.py:_chunk_and_encode / _encode_long_prompt.
# Reference semantics read directly from the installed diffusers==0.30.3
# source (pipeline_stable_diffusion_xl.py:encode_prompt).

import torch as _torch

# sdxl_service.py is kept on disk but untracked from git (IMAGE_PROVIDER=gemini
# is the active backend), so a fresh clone will not have it. Import it
# defensively: without the guard, this module-level import fails at *collection*
# and takes down the whole suite, not just the four tests below.
try:
    from ai.diffusion import sdxl_service as _sdxl_service
except ImportError:                                      # pragma: no cover
    _sdxl_service = None

_needs_sdxl = pytest.mark.skipif(
    _sdxl_service is None,
    reason="ai/diffusion/sdxl_service.py is not present (untracked from git)",
)


class _FakeTokenizer:
    bos_token_id = 1
    eos_token_id = 2
    pad_token_id = 0
    model_max_length = 77

    def __call__(self, text, truncation=False, add_special_tokens=True):
        class _Out:
            input_ids = [10 + i for i in range(len(text.split()))]
        return _Out()


class _FakeEncoderOutput:
    def __init__(self, hidden_dim, seq_len, pooled_dim):
        # index -2 must land on the tensor (the "penultimate hidden layer"
        # SDXL actually uses) - three entries so [-2] hits the middle one.
        self.hidden_states = [None, _torch.randn(1, seq_len, hidden_dim), None]
        self._pooled = _torch.randn(1, pooled_dim)

    def __getitem__(self, i):
        assert i == 0
        return self._pooled


class _FakeTextEncoder:
    def __init__(self, hidden_dim, pooled_dim):
        self.hidden_dim, self.pooled_dim = hidden_dim, pooled_dim

    def __call__(self, input_ids, output_hidden_states=True):
        return _FakeEncoderOutput(self.hidden_dim, input_ids.shape[1], self.pooled_dim)


@_needs_sdxl
def test_sdxl_chunk_short_prompt_is_single_chunk():
    tok, enc = _FakeTokenizer(), _FakeTextEncoder(768, 768)
    embeds, _, n_chunks = _sdxl_service._chunk_and_encode(
        "a red bucket of paint on a shelf", tok, enc, device="cpu"
    )
    assert n_chunks == 1
    assert embeds.shape == (1, 77, 768)


@_needs_sdxl
def test_sdxl_chunk_long_prompt_grows_sequence_axis():
    tok, enc = _FakeTokenizer(), _FakeTextEncoder(768, 768)
    long_prompt = " ".join(f"word{i}" for i in range(150))
    embeds, _, n_chunks = _sdxl_service._chunk_and_encode(long_prompt, tok, enc, device="cpu")
    assert n_chunks == 2, "150 words at 75/chunk must produce ceil(150/75)=2 chunks"
    assert embeds.shape == (1, 154, 768), "sequence axis must grow - this is what lets content past token 77 reach the UNet"


@_needs_sdxl
def test_sdxl_chunk_n_chunks_padding_matches_length():
    tok, enc = _FakeTokenizer(), _FakeTextEncoder(768, 768)
    long_embeds, _, n_chunks = _sdxl_service._chunk_and_encode(
        " ".join(f"word{i}" for i in range(150)), tok, enc, device="cpu"
    )
    short_embeds, _, forced_n = _sdxl_service._chunk_and_encode(
        "short negative prompt", tok, enc, device="cpu", n_chunks=n_chunks
    )
    assert forced_n == n_chunks
    assert short_embeds.shape == long_embeds.shape, (
        "positive/negative embeddings must match in sequence length for "
        "classifier-free-guidance batching (torch.cat along the batch axis)"
    )


@_needs_sdxl
def test_sdxl_encode_long_prompt_concatenates_both_encoders():
    tok = _FakeTokenizer()

    class _FakePipe:
        tokenizer      = tok
        tokenizer_2    = _FakeTokenizer()
        text_encoder   = _FakeTextEncoder(768, 768)     # CLIP ViT-L
        text_encoder_2 = _FakeTextEncoder(1280, 1280)   # OpenCLIP ViT-bigG

    long_prompt = " ".join(f"word{i}" for i in range(150))
    pe, npe, pooled, npooled = _sdxl_service._encode_long_prompt(
        _FakePipe(), long_prompt, "blurry, low quality", "cpu"
    )
    assert pe.shape[-1] == 768 + 1280, "feature axis must be the two encoders concatenated (2048-dim)"
    assert pe.shape == npe.shape, "positive/negative must match for CFG torch.cat"
    assert pooled.shape == (1, 1280), "pooled embedding must come from text_encoder_2 (bigG) only, per diffusers' own encode_prompt"
    assert npooled.shape == (1, 1280)
