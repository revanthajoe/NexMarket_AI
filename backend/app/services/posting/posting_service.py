"""
Social Posting Service — orchestrates adapters, retry logic,
scheduling, and DB persistence.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.models import AdCopy, AnalyticsEvent, Campaign, Poster, PostLog, SocialPost
from app.services.posting.adapters import (
    FacebookAdapter,
    InstagramAdapter,
    MockAdapter,
    PostMetrics,
    PostPayload,
    PostResult,
    SocialPlatformAdapter,
    TelegramAdapter,
    WhatsAppAdapter,
)

logger = get_logger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds

SUPPORTED_PLATFORMS = [
    "instagram", "facebook", "telegram", "whatsapp",
]


def _credentials_present(platform: str) -> bool:
    """True when every secret this platform's live adapter needs is configured."""
    if platform == "instagram":
        return bool(settings.META_ACCESS_TOKEN and settings.META_IG_USER_ID)
    if platform == "facebook":
        return bool(settings.META_ACCESS_TOKEN and settings.META_PAGE_ID)
    if platform == "telegram":
        return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)
    if platform == "whatsapp":
        return bool(
            settings.WHATSAPP_ACCESS_TOKEN
            and settings.WHATSAPP_PHONE_NUMBER_ID
            and settings.WHATSAPP_RECIPIENT
        )
    return False


def _get_adapter(platform: str) -> SocialPlatformAdapter:
    """Factory: returns live or mock adapter based on settings and credentials."""
    if settings.SOCIAL_MODE == "mock":
        return MockAdapter(platform)

    if not _credentials_present(platform):
        # Fallback to mock if credentials missing
        logger.warning("social_credentials_missing_fallback_mock", platform=platform)
        return MockAdapter(platform)

    if platform == "instagram":
        return InstagramAdapter(settings.META_ACCESS_TOKEN, settings.META_IG_USER_ID)

    if platform == "facebook":
        return FacebookAdapter(settings.META_ACCESS_TOKEN, settings.META_PAGE_ID)

    if platform == "telegram":
        return TelegramAdapter(settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID)

    if platform == "whatsapp":
        return WhatsAppAdapter(
            settings.WHATSAPP_ACCESS_TOKEN,
            settings.WHATSAPP_PHONE_NUMBER_ID,
            settings.WHATSAPP_RECIPIENT,
        )

    logger.warning("social_platform_unsupported_fallback_mock", platform=platform)
    return MockAdapter(platform)


async def resolve_post_text(
    db: AsyncSession, campaign_id: str, ad_copy_id: Optional[str] = None
) -> str:
    """Body text for a post: the linked ad copy, else a campaign fallback line."""
    if ad_copy_id:
        ad = await db.get(AdCopy, ad_copy_id)
        if ad:
            return ad.body
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        return ""
    return f"{campaign.product_name} — {campaign.offer}"


async def resolve_post_image(db: AsyncSession, poster_id: Optional[str] = None) -> Optional[str]:
    if poster_id:
        poster = await db.get(Poster, poster_id)
        if poster:
            return poster.image_url
    return None


class SocialPostingService:
    """
    Manages the full lifecycle of a social post:
    immediate posting, scheduling, retries, and audit logging.
    """

    async def publish(
        self,
        db: AsyncSession,
        social_post: SocialPost,
        text: str,
        image_url: Optional[str] = None,
    ) -> SocialPost:
        """Post immediately with retry logic."""
        adapter = _get_adapter(social_post.platform)
        payload = PostPayload(
            text=text,
            image_url=image_url,
            campaign_id=social_post.campaign_id,
            platform=social_post.platform,
        )

        attempt = 0
        last_error = None

        while attempt <= MAX_RETRIES:
            attempt += 1
            await self._log(db, social_post.id, "attempt_start", {"attempt": attempt})
            social_post.status = "posting"
            await db.flush()

            try:
                result: PostResult = await adapter.post(payload)
            except Exception as exc:
                result = PostResult(success=False, error=str(exc))

            if result.success:
                social_post.status = "posted"
                social_post.platform_post_id = result.platform_post_id
                social_post.platform_url = result.platform_url
                social_post.posted_at = result.posted_at or datetime.utcnow()
                social_post.is_mock = result.is_mock
                social_post.response_payload = result.raw_response
                social_post.retry_count = attempt - 1
                await self._log(db, social_post.id, "posted", {"post_id": result.platform_post_id})
                logger.info(
                    "social_post_published",
                    platform=social_post.platform,
                    post_id=result.platform_post_id,
                    is_mock=result.is_mock,
                )
                return social_post

            last_error = result.error
            social_post.error_message = last_error
            await self._log(db, social_post.id, "attempt_failed", {"error": last_error, "attempt": attempt})
            logger.warning("social_post_attempt_failed", attempt=attempt, error=last_error)

            if attempt <= MAX_RETRIES:
                wait = BACKOFF_BASE ** attempt
                await asyncio.sleep(wait)

        # All retries exhausted
        social_post.status = "failed"
        social_post.retry_count = attempt - 1
        await self._log(db, social_post.id, "failed", {"final_error": last_error})
        logger.error("social_post_failed", platform=social_post.platform, error=last_error)
        return social_post

    async def create_posts_for_platforms(
        self,
        db: AsyncSession,
        campaign_id: str,
        platforms: list[str],
        ad_copy_id: Optional[str] = None,
        poster_id: Optional[str] = None,
    ) -> list[SocialPost]:
        """
        Create one `SocialPost` row per platform, already committed and marked
        `posting`.

        Centralizes an ordering fix that mattered more than it looks: setting
        `status = "posting"` AFTER a commit leaves the attribute dirty on the
        caller's session, and a later commit on that same session (e.g.
        get_db()'s post-yield commit in a request handler) then flushes it —
        silently reverting a background task's `posted` if the task finished
        first. Verified directly: rows sat at `posting` with a populated
        platform_post_id, i.e. published but permanently reported as
        in-flight. Setting status before the commit here means every caller
        gets the fix automatically instead of needing to reproduce the
        ordering by hand.
        """
        posts = [
            SocialPost(
                campaign_id=campaign_id,
                platform=platform,
                ad_copy_id=ad_copy_id,
                poster_id=poster_id,
                status="posting",
            )
            for platform in platforms
        ]
        for sp in posts:
            db.add(sp)
        await db.commit()
        for sp in posts:
            await db.refresh(sp)
        return posts

    async def publish_platforms(
        self,
        db: AsyncSession,
        posts: list[SocialPost],
        text: str,
        image_url: Optional[str] = None,
    ) -> None:
        """
        Publish each already-created `SocialPost` row in turn, on the same
        session.

        This is the independence guarantee itself: one platform's exception —
        or `publish()` exhausting its own retries and returning a `failed`
        result — must never stop the rest from being attempted. Shared by the
        standalone `/posting/campaign/{id}/publish` endpoint and the
        n8n-triggered pipeline's `post` step, so a fix here (like this
        containment, or the status-ordering fix above) applies everywhere at
        once instead of needing to be reimplemented at each call site — which
        is exactly how the n8n pipeline ended up publishing to only one
        platform and failing the whole campaign when that one publish raised.
        """
        for sp in posts:
            try:
                await self.publish(db, sp, text, image_url)
                await db.commit()
            except Exception:
                logger.exception(
                    "publish_platforms_failed post_id=%s platform=%s", sp.id, sp.platform,
                )

    async def schedule(
        self,
        db: AsyncSession,
        social_post: SocialPost,
    ) -> SocialPost:
        """Mark as scheduled — actual posting handled by worker/n8n."""
        social_post.status = "scheduled"
        await self._log(db, social_post.id, "scheduled", {"at": str(social_post.scheduled_at)})
        logger.info("social_post_scheduled", at=str(social_post.scheduled_at))
        return social_post

    async def publish_scheduled_due(self, db: AsyncSession, now: Optional[datetime] = None) -> int:
        """Publish every scheduled post whose time has arrived.

        `schedule()` only parks a post in the `scheduled` state; without this
        runner nothing ever picked those rows back up and they sat there forever.
        Returns the number of posts attempted.
        """
        now = now or datetime.utcnow()
        due = (
            await db.execute(
                select(SocialPost)
                .where(SocialPost.status == "scheduled")
                .where(SocialPost.scheduled_at.isnot(None))
                .where(SocialPost.scheduled_at <= now)
                .order_by(SocialPost.scheduled_at.asc())
            )
        ).scalars().all()

        for sp in due:
            text = await resolve_post_text(db, sp.campaign_id, sp.ad_copy_id)
            image_url = await resolve_post_image(db, sp.poster_id)
            await self.publish(db, sp, text, image_url)

        if due:
            await db.commit()
            logger.info("scheduled_posts_published", count=len(due))
        return len(due)

    async def sync_metrics(self, db: AsyncSession, social_post: SocialPost) -> Optional[PostMetrics]:
        """Pull engagement for one published post and record it as an AnalyticsEvent.

        Upserts on (campaign, platform, day) so re-syncing refreshes the day's
        numbers instead of stacking duplicate rows onto the chart.
        """
        if social_post.status != "posted" or not social_post.platform_post_id:
            return None

        adapter = _get_adapter(social_post.platform)
        metrics = await adapter.fetch_metrics(social_post.platform_post_id)
        if not metrics.ok:
            logger.warning(
                "metrics_fetch_failed",
                platform=social_post.platform,
                post_id=social_post.platform_post_id,
                error=metrics.error,
            )
            await self._log(db, social_post.id, "metrics_failed", {"error": metrics.error})
            return metrics

        today = datetime.utcnow().date()
        existing = (
            await db.execute(
                select(AnalyticsEvent)
                .where(AnalyticsEvent.campaign_id == social_post.campaign_id)
                .where(AnalyticsEvent.platform == social_post.platform)
                .where(func.date(AnalyticsEvent.event_date) == today.isoformat())
            )
        ).scalars().first()

        event = existing or AnalyticsEvent(
            campaign_id=social_post.campaign_id,
            platform=social_post.platform,
        )
        event.event_date = datetime.utcnow()
        event.impressions = metrics.impressions
        event.clicks = metrics.clicks
        event.likes = metrics.likes
        event.shares = metrics.shares
        event.comments = metrics.comments
        event.reach = metrics.reach
        event.ctr = metrics.ctr
        event.is_mock = metrics.is_mock
        event.synced_at = datetime.utcnow()
        if existing is None:
            db.add(event)

        await db.flush()
        await self._log(db, social_post.id, "metrics_synced", metrics.as_dict())
        logger.info(
            "metrics_synced",
            platform=social_post.platform,
            impressions=metrics.impressions,
            is_mock=metrics.is_mock,
        )
        return metrics

    async def sync_campaign_metrics(self, db: AsyncSession, campaign_id: str) -> dict:
        """Refresh analytics for every published post of one campaign."""
        posts = (
            await db.execute(
                select(SocialPost)
                .where(SocialPost.campaign_id == campaign_id)
                .where(SocialPost.status == "posted")
            )
        ).scalars().all()

        synced, failed, mocked = 0, 0, 0
        for sp in posts:
            metrics = await self.sync_metrics(db, sp)
            if metrics is None:
                continue
            if metrics.ok:
                synced += 1
                mocked += 1 if metrics.is_mock else 0
            else:
                failed += 1

        await db.commit()
        return {
            "campaign_id": campaign_id,
            "posts_checked": len(posts),
            "synced": synced,
            "failed": failed,
            "mock_sourced": mocked,
        }

    async def platform_status(self) -> dict[str, dict]:
        """Per-platform integration state.

        Reports `configured` separately from `healthy`: in mock mode every
        adapter answers True, and showing that as "Operational" told the user a
        platform with no credentials at all was connected.
        """
        results: dict[str, dict] = {}
        for p in SUPPORTED_PLATFORMS:
            configured = _credentials_present(p)
            adapter = _get_adapter(p)
            try:
                healthy = await adapter.health_check()
            except Exception:
                healthy = False
            results[p] = {
                "configured": configured,
                "healthy": healthy,
                "mode": "live" if adapter.is_live else "mock",
            }
        return results

    async def health_check_all(self) -> dict[str, bool]:
        """Back-compat boolean view of `platform_status()`."""
        status = await self.platform_status()
        return {p: s["healthy"] for p, s in status.items()}

    async def _log(
        self,
        db: AsyncSession,
        post_id: str,
        event: str,
        detail: Optional[dict] = None,
    ):
        log = PostLog(post_id=post_id, event=event, detail=detail)
        db.add(log)
        await db.flush()


social_posting_service = SocialPostingService()
