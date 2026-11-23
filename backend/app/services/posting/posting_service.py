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
from app.models.models import (
    AdCopy,
    AnalyticsEvent,
    Campaign,
    Poster,
    PostLog,
    SentimentResult,
    SocialComment,
    SocialPost,
)
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


def available_platforms() -> list[str]:
    """Return publish targets usable in the current live or mock mode."""
    if settings.SOCIAL_MODE != "live":
        return list(SUPPORTED_PLATFORMS)
    return [platform for platform in SUPPORTED_PLATFORMS if _credentials_present(platform)]


def _get_adapter(platform: str) -> SocialPlatformAdapter:
    """Factory: returns live or mock adapter based on settings and credentials."""
    if settings.SOCIAL_MODE == "live":
        if not _credentials_present(platform):
            raise RuntimeError(f"LIVE mode enabled but credentials missing for platform '{platform}'. Silent fallback to mock is prohibited.")
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
        raise RuntimeError(f"LIVE mode enabled but platform '{platform}' is unsupported.")

    # In mock mode, always use MockAdapter
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

    async def fail_unavailable_live_posts(self, db: AsyncSession) -> int:
        """Fail queued rows for live platforms that have no configured credentials."""
        if settings.SOCIAL_MODE != "live":
            return 0

        configured = set(available_platforms())
        unavailable = set(SUPPORTED_PLATFORMS) - configured
        if not unavailable:
            return 0

        rows = (await db.execute(
            select(SocialPost)
            .where(SocialPost.platform.in_(unavailable))
            .where(SocialPost.status.in_(("pending", "posting", "scheduled")))
        )).scalars().all()
        for row in rows:
            row.status = "failed"
            row.error_message = f"Skipped: {row.platform} is not configured for live posting."
            await self._log(db, row.id, "skipped_unconfigured_platform", {"platform": row.platform})
        if rows:
            await db.commit()
            logger.warning("unconfigured_live_posts_failed", count=len(rows), platforms=sorted(unavailable))
        return len(rows)

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
                social_post.source_type = "SIMULATED" if result.is_mock else "ACTUAL"
                social_post.source_system = social_post.platform.upper()
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
        existing_rows = (await db.execute(
            select(SocialPost).where(
                SocialPost.campaign_id == campaign_id,
                SocialPost.platform.in_(platforms),
            )
        )).scalars().all()
        existing_by_platform = {}
        for row in existing_rows:
            if row.poster_id == poster_id and row.ad_copy_id == ad_copy_id:
                existing_by_platform[row.platform] = row
        posts = []
        for platform in platforms:
            existing = existing_by_platform.get(platform)
            if existing is not None:
                # Reuse posted, in-flight, and failed rows. The publish method
                # can safely retry a failed row, while reusing posted/in-flight
                # rows prevents a second platform call after an ambiguous run.
                posts.append(existing)
                continue
            posts.append(SocialPost(
                campaign_id=campaign_id,
                platform=platform,
                ad_copy_id=ad_copy_id,
                poster_id=poster_id,
                status="posting",
            ))
        for sp in posts:
            if sp.id is None:
                db.add(sp)
            else:
                # If we reused an existing row that was failed/pending, mark it posting
                sp.status = "posting"
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
                if sp.status == "posted":
                    logger.info("publish_skip_already_posted post_id=%s platform=%s", sp.id, sp.platform)
                    continue
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
        if metrics.unavailable:
            logger.info(
                "metrics_unavailable",
                platform=social_post.platform,
                post_id=social_post.platform_post_id,
                reason=metrics.error,
            )
            await self._log(db, social_post.id, "metrics_unavailable", {"reason": metrics.error})
            return None
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
        event.source_type = "SIMULATED" if metrics.is_mock else "ACTUAL"
        event.source_system = f"{social_post.platform}_adapter"
        event.source_reference = social_post.platform_post_id
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

    async def ingest_telegram_update(self, db: AsyncSession, update: dict) -> dict:
        """Ingest an update delivered by Telegram's webhook/getUpdates API."""
        from app.services.posting.adapters import TelegramAdapter

        parsed = TelegramAdapter.parse_update(update)
        if parsed.get("kind") not in {"message", "comment", "reaction"}:
            return {"status": "ignored", "reason": "unsupported_update"}

        target_id = parsed.get("parent_message_id") or parsed.get("message_id")
        if not target_id:
            return {"status": "ignored", "reason": "missing_message_id"}

        posts = (await db.execute(
            select(SocialPost)
            .where(SocialPost.platform == "telegram")
            .where(SocialPost.status == "posted")
            .where(SocialPost.platform_post_id == target_id)
        )).scalars().all()
        post = next(
            (candidate for candidate in posts if self._telegram_chat_matches(candidate, parsed.get("chat_id"))),
            None,
        )
        if post is None:
            return {"status": "ignored", "reason": "telegram_post_not_found"}
        if post.is_mock or post.source_type != "ACTUAL":
            return {"status": "ignored", "reason": "simulated_post"}

        if parsed["kind"] == "comment":
            text = (parsed.get("text") or "").strip()
            if not text:
                return {"status": "ignored", "reason": "empty_comment"}
            existing = (await db.execute(
                select(SocialComment)
                .where(SocialComment.social_post_id == post.id)
                .where(SocialComment.platform_comment_id == parsed["message_id"])
            )).scalar_one_or_none()
            if existing is None:
                comment = SocialComment(
                    campaign_id=post.campaign_id,
                    social_post_id=post.id,
                    platform="telegram",
                    platform_comment_id=parsed["message_id"],
                    parent_platform_message_id=parsed["parent_message_id"],
                    text=text,
                    comment_date=parsed.get("event_date"),
                    source_type="ACTUAL",
                    source_system="telegram_bot_api",
                    source_reference=parsed["message_id"],
                    raw_payload=parsed.get("raw"),
                )
                db.add(comment)
                await db.flush()
                sentiment = await self._persist_telegram_sentiment(db, comment)
            else:
                sentiment = False
            await db.commit()
            return {"status": "ok", "comment_id": existing.id if existing else comment.id, "sentiment": sentiment}

        if parsed["kind"] == "message" and any(
            parsed.get(key) is not None for key in ("views", "reactions", "replies")
        ):
            event = (await db.execute(
                select(AnalyticsEvent)
                .where(AnalyticsEvent.social_post_id == post.id)
                .where(AnalyticsEvent.platform == "telegram")
                .order_by(AnalyticsEvent.event_date.desc())
                .limit(1)
            )).scalar_one_or_none()
            if event is None:
                event = AnalyticsEvent(
                    campaign_id=post.campaign_id,
                    social_post_id=post.id,
                    platform="telegram",
                    event_date=parsed.get("event_date") or datetime.utcnow(),
                    source_type="ACTUAL",
                    source_system="telegram_bot_api",
                    source_reference=post.platform_post_id,
                    is_mock=False,
                )
                db.add(event)
            if parsed.get("views") is not None:
                event.impressions = parsed["views"]
            if parsed.get("reactions") is not None:
                event.reactions = parsed["reactions"]
            if parsed.get("replies") is not None:
                event.comments = parsed["replies"]
            event.event_date = parsed.get("event_date") or event.event_date
            event.synced_at = datetime.utcnow()
            await db.commit()
            return {"status": "ok", "analytics": True, "source_type": "ACTUAL"}

        return {"status": "unavailable", "reason": "telegram_update_has_no_aggregate_metrics"}

    @staticmethod
    def _telegram_chat_matches(post: SocialPost, chat_id: Optional[str]) -> bool:
        if not chat_id:
            return True
        payload = post.response_payload or {}
        result = payload.get("result", payload)
        stored_chat_id = ((result.get("chat") or {}).get("id")) if isinstance(result, dict) else None
        return stored_chat_id is None or str(stored_chat_id) == str(chat_id)

    @staticmethod
    async def _persist_telegram_sentiment(db: AsyncSession, comment: SocialComment) -> bool:
        from app.services.ai.sentiment import sentiment_service

        try:
            analysis = await sentiment_service.analyze(
                [comment.text],
                comment.campaign_id,
                source_type="ACTUAL",
                source_system="telegram_comment",
                source_reference=comment.platform_comment_id,
            )
        except (RuntimeError, ValueError):
            return False
        result = analysis["results"][0]
        if result.get("source_type") != "PREDICTED" or result.get("is_fallback"):
            return False
        db.add(SentimentResult(
            campaign_id=comment.campaign_id,
            social_comment_id=comment.id,
            text=comment.text,
            label=result["label"],
            positive_score=result["positive_score"],
            negative_score=result["negative_score"],
            neutral_score=result.get("neutral_score", 0.0),
            confidence=result["confidence"],
            model_used=result["model_used"],
            source_type="PREDICTED",
            input_source_type="ACTUAL",
            source_system="telegram_comment",
            source_reference=comment.platform_comment_id,
            model_name=result.get("model_name", "DistilBERT SST-2"),
            model_version=result.get("model_version"),
        ))
        return True

    async def platform_status(self) -> dict[str, dict]:
        """Per-platform integration state.

        Reports `configured` separately from `healthy`: in mock mode every
        adapter answers True, and showing that as "Operational" told the user a
        platform with no credentials at all was connected.
        """
        results: dict[str, dict] = {}
        for p in SUPPORTED_PLATFORMS:
            configured = _credentials_present(p)
            if settings.SOCIAL_MODE == "live" and not configured:
                results[p] = {"configured": False, "healthy": False, "mode": "live"}
                continue
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
