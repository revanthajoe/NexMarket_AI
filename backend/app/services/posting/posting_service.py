"""
Social Posting Service — orchestrates adapters, retry logic,
scheduling, and DB persistence.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.models import PostLog, SocialPost
from app.services.posting.adapters import (
    FacebookAdapter,
    InstagramAdapter,
    LinkedInAdapter,
    MockAdapter,
    PostPayload,
    PostResult,
    SocialPlatformAdapter,
    TwitterAdapter,
)

logger = get_logger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds


def _get_adapter(platform: str) -> SocialPlatformAdapter:
    """Factory: returns live or mock adapter based on settings and credentials."""
    if settings.SOCIAL_MODE == "mock":
        return MockAdapter(platform)

    if platform == "instagram" and settings.META_ACCESS_TOKEN and settings.META_IG_USER_ID:
        return InstagramAdapter(settings.META_ACCESS_TOKEN, settings.META_IG_USER_ID)

    if platform == "facebook" and settings.META_ACCESS_TOKEN and settings.META_PAGE_ID:
        return FacebookAdapter(settings.META_ACCESS_TOKEN, settings.META_PAGE_ID)

    if platform == "linkedin" and settings.LINKEDIN_ACCESS_TOKEN:
        urn = settings.LINKEDIN_ORG_URN or settings.LINKEDIN_PERSON_URN
        return LinkedInAdapter(settings.LINKEDIN_ACCESS_TOKEN, urn)

    if platform == "twitter" and settings.TWITTER_API_KEY:
        return TwitterAdapter(
            settings.TWITTER_API_KEY,
            settings.TWITTER_API_SECRET,
            settings.TWITTER_ACCESS_TOKEN,
            settings.TWITTER_ACCESS_TOKEN_SECRET,
        )

    # Fallback to mock if credentials missing
    logger.warning("social_credentials_missing_fallback_mock", platform=platform)
    return MockAdapter(platform)


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

    async def health_check_all(self) -> dict[str, bool]:
        platforms = ["instagram", "facebook", "linkedin", "twitter"]
        results = {}
        for p in platforms:
            adapter = _get_adapter(p)
            try:
                results[p] = await adapter.health_check()
            except Exception:
                results[p] = False
        return results

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
