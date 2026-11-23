import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.models import AnalyticsEvent, Campaign, SentimentResult, SocialComment, SocialPost
from app.services.ai.sentiment import sentiment_service
from app.services.posting import posting_service as posting_module
from app.services.posting.adapters import PostResult


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client


async def make_campaign() -> Campaign:
    async with AsyncSessionLocal() as db:
        campaign = Campaign(
            name="Telegram Phase 14",
            product_name="Test Product",
            description="A product for Telegram analytics testing",
            offer="10% off",
            target_audience="Test audience",
            campaign_goal="engagement",
            preferred_platform="telegram",
            status="ready",
        )
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)
        return campaign


async def make_post(campaign: Campaign, *, post_id: str = "42", is_mock: bool = False) -> SocialPost:
    async with AsyncSessionLocal() as db:
        post = SocialPost(
            campaign_id=campaign.id,
            platform="telegram",
            status="posted",
            platform_post_id=post_id,
            is_mock=is_mock,
            source_type="SIMULATED" if is_mock else "ACTUAL",
            source_system="TELEGRAM",
            response_payload={"result": {"chat": {"id": "-1001"}}},
        )
        db.add(post)
        await db.commit()
        await db.refresh(post)
        return post


@pytest.mark.asyncio
async def test_telegram_publish_persists_message_id(client, monkeypatch):
    campaign = await make_campaign()

    class LiveTelegram:
        async def post(self, payload):
            return PostResult(success=True, platform_post_id="telegram-message-99")

        async def fetch_metrics(self, platform_post_id):
            raise AssertionError("Telegram history metrics must not be polled")

        async def health_check(self):
            return True

    monkeypatch.setattr(posting_module, "_get_adapter", lambda platform: LiveTelegram())
    response = await client.post(
        "/api/v1/posting/publish",
        json={"campaign_id": campaign.id, "platform": "telegram"},
    )
    assert response.status_code == 200

    async with AsyncSessionLocal() as db:
        post = await db.get(SocialPost, response.json()["id"])
        assert post.platform_post_id == "telegram-message-99"
        assert post.source_type == "ACTUAL"


@pytest.mark.asyncio
async def test_telegram_actual_message_metrics_keep_unknown_values_null(client):
    campaign = await make_campaign()
    post = await make_post(campaign)

    response = await client.post(
        "/api/v1/posting/telegram/webhook",
        json={
            "update_id": 1,
            "message": {
                "message_id": 42,
                "chat": {"id": -1001},
                "date": 1700000000,
                "views": 123,
                "reactions": {"results": [{"type": {"type": "emoji", "emoji": "👍"}, "count": 4}]},
                "replies": {"replies": 2},
            },
        },
    )
    assert response.json()["status"] == "ok"

    async with AsyncSessionLocal() as db:
        event = (await db.execute(select(AnalyticsEvent).where(AnalyticsEvent.social_post_id == post.id))).scalar_one()
        assert event.source_type == "ACTUAL"
        assert event.impressions == 123
        assert event.reactions == 4
        assert event.comments == 2
        assert event.clicks is None
        assert event.likes is None
        assert event.shares is None
        assert event.reach is None


@pytest.mark.asyncio
async def test_telegram_comment_and_sentiment_are_actual_then_predicted(client, monkeypatch):
    campaign = await make_campaign()
    post = await make_post(campaign)

    async def fake_sentiment(texts, *args, **kwargs):
        assert texts == ["Excellent product"]
        assert kwargs["source_type"] == "ACTUAL"
        return {
            "results": [{
                "text": texts[0], "label": "positive", "positive_score": 0.98,
                "negative_score": 0.01, "neutral_score": 0.01, "confidence": 0.98,
                "model_used": "distilbert", "source_type": "PREDICTED",
                "is_fallback": False, "model_name": "DistilBERT SST-2",
            }],
            "summary": {"positive": 1, "neutral": 0, "negative": 0},
        }

    monkeypatch.setattr(sentiment_service, "analyze", fake_sentiment)
    response = await client.post(
        "/api/v1/posting/telegram/webhook",
        json={
            "update_id": 2,
            "message": {
                "message_id": 77,
                "chat": {"id": -1001},
                "date": 1700000001,
                "text": "Excellent product",
                "reply_to_message": {"message_id": 42},
            },
        },
    )
    assert response.json()["status"] == "ok"

    async with AsyncSessionLocal() as db:
        comment = (await db.execute(select(SocialComment).where(SocialComment.social_post_id == post.id))).scalar_one()
        sentiment = (await db.execute(select(SentimentResult).where(SentimentResult.social_comment_id == comment.id))).scalar_one()
        assert comment.campaign_id == campaign.id
        assert comment.social_post_id == post.id
        assert comment.source_type == "ACTUAL"
        assert sentiment.source_type == "PREDICTED"
        assert sentiment.input_source_type == "ACTUAL"
        assert sentiment.model_name == "DistilBERT SST-2"


@pytest.mark.asyncio
async def test_telegram_wrong_post_and_mock_post_are_ignored(client):
    campaign = await make_campaign()
    actual_post = await make_post(campaign, post_id="42")
    mock_post = await make_post(campaign, post_id="43", is_mock=True)

    wrong = await client.post(
        "/api/v1/posting/telegram/webhook",
        json={"message": {"message_id": 77, "chat": {"id": -1001}, "text": "wrong", "reply_to_message": {"message_id": "missing"}}},
    )
    assert wrong.json()["status"] == "ignored"

    simulated = await client.post(
        "/api/v1/posting/telegram/webhook",
        json={"message": {"message_id": 78, "chat": {"id": -1001}, "text": "simulated", "reply_to_message": {"message_id": "43"}}},
    )
    assert simulated.json()["reason"] == "simulated_post"

    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(SocialComment).where(SocialComment.social_post_id == actual_post.id))).scalars().all() == []
        assert (await db.execute(select(SocialComment).where(SocialComment.social_post_id == mock_post.id))).scalars().all() == []


@pytest.mark.asyncio
async def test_internal_telegram_poller_ingests_replies_and_advances_offset(monkeypatch):
    from app.services.posting.adapters import TelegramAdapter
    from app.services.posting.worker import poll_telegram_updates_once

    campaign = await make_campaign()
    post = await make_post(campaign)
    adapter = TelegramAdapter("test-token", "-1001")

    async def fake_get_updates(offset=None, timeout_seconds=20):
        assert offset is None
        return [{
            "update_id": 12,
            "message": {
                "message_id": 77,
                "chat": {"id": -1001},
                "date": 1700000001,
                "text": "Excellent product",
                "reply_to_message": {"message_id": int(post.platform_post_id)},
            },
        }]

    async def sentiment_unavailable(*_args, **_kwargs):
        raise RuntimeError("model is loading")

    monkeypatch.setattr(adapter, "get_updates", fake_get_updates)
    monkeypatch.setattr(sentiment_service, "analyze", sentiment_unavailable)
    next_offset = await poll_telegram_updates_once(adapter, None)

    async with AsyncSessionLocal() as db:
        comments = (await db.execute(
            select(SocialComment).where(SocialComment.social_post_id == post.id)
        )).scalars().all()
    assert next_offset == 13
    assert len(comments) == 1
    assert comments[0].text == "Excellent product"
    assert comments[0].source_type == "ACTUAL"

@pytest.mark.asyncio
async def test_live_startup_reconciliation_fails_only_unconfigured_posts(monkeypatch):
    from app.core.config import settings
    from app.services.posting.posting_service import social_posting_service

    campaign = await make_campaign()
    async with AsyncSessionLocal() as db:
        instagram = SocialPost(
            campaign_id=campaign.id, platform="instagram", status="posting",
            source_type="UNKNOWN",
        )
        telegram = SocialPost(
            campaign_id=campaign.id, platform="telegram", status="posting",
            source_type="UNKNOWN",
        )
        db.add_all([instagram, telegram])
        await db.commit()
        instagram_id, telegram_id = instagram.id, telegram.id

    monkeypatch.setattr(settings, "SOCIAL_MODE", "live")
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "test-chat")
    monkeypatch.setattr(settings, "META_ACCESS_TOKEN", "")
    monkeypatch.setattr(settings, "META_IG_USER_ID", "")
    monkeypatch.setattr(settings, "META_PAGE_ID", "")
    monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    monkeypatch.setattr(settings, "WHATSAPP_RECIPIENT", "")

    async with AsyncSessionLocal() as db:
        reconciled = await social_posting_service.fail_unavailable_live_posts(db)
        instagram = await db.get(SocialPost, instagram_id)
        telegram = await db.get(SocialPost, telegram_id)
    assert reconciled == 1
    assert instagram.status == "failed"
    assert "not configured" in instagram.error_message
    assert telegram.status == "posting"
