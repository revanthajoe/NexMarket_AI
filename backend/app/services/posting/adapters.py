"""
Module 8: Social Media Posting System
Adapter pattern: each platform has its own adapter.
All adapters implement SocialPlatformAdapter interface.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


# ─── Base Adapter Interface ───────────────────────────────────────────────────

class PostPayload:
    def __init__(
        self,
        text: str,
        image_url: Optional[str] = None,
        campaign_id: Optional[str] = None,
        platform: Optional[str] = None,
    ):
        self.text = text
        self.image_url = image_url
        self.campaign_id = campaign_id
        self.platform = platform


class PostResult:
    def __init__(
        self,
        success: bool,
        platform_post_id: Optional[str] = None,
        platform_url: Optional[str] = None,
        error: Optional[str] = None,
        raw_response: Optional[dict] = None,
        is_mock: bool = False,
    ):
        self.success = success
        self.platform_post_id = platform_post_id
        self.platform_url = platform_url
        self.error = error
        self.raw_response = raw_response or {}
        self.is_mock = is_mock
        self.posted_at = datetime.utcnow() if success else None


class SocialPlatformAdapter(ABC):
    platform_name: str = "base"

    @abstractmethod
    async def post(self, payload: PostPayload) -> PostResult:
        """Publish content. Must be idempotent."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Returns True if credentials are valid."""
        ...


# ─── Mock Adapter (Demo / Fallback) ──────────────────────────────────────────

class MockAdapter(SocialPlatformAdapter):
    def __init__(self, platform: str):
        self.platform_name = platform

    async def post(self, payload: PostPayload) -> PostResult:
        await asyncio.sleep(0.3)  # simulate network latency
        fake_id = f"mock_{self.platform_name}_{uuid.uuid4().hex[:12]}"
        fake_url = f"https://{self.platform_name}.example.com/posts/{fake_id}"
        logger.info("mock_post_published", platform=self.platform_name, post_id=fake_id)
        return PostResult(
            success=True,
            platform_post_id=fake_id,
            platform_url=fake_url,
            raw_response={"id": fake_id, "url": fake_url, "mode": "mock"},
            is_mock=True,
        )

    async def health_check(self) -> bool:
        return True


# ─── Instagram Adapter (Meta Graph API) ──────────────────────────────────────

class InstagramAdapter(SocialPlatformAdapter):
    platform_name = "instagram"

    def __init__(self, access_token: str, ig_user_id: str):
        self.access_token = access_token
        self.ig_user_id = ig_user_id
        self._base = "https://graph.facebook.com/v19.0"

    async def post(self, payload: PostPayload) -> PostResult:
        import httpx

        if not payload.image_url:
            return PostResult(success=False, error="Instagram requires an image_url")

        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: create media container
            r1 = await client.post(
                f"{self._base}/{self.ig_user_id}/media",
                params={
                    "image_url": payload.image_url,
                    "caption": payload.text,
                    "access_token": self.access_token,
                },
            )
            r1.raise_for_status()
            container_id = r1.json()["id"]

            # Step 2: publish container
            r2 = await client.post(
                f"{self._base}/{self.ig_user_id}/media_publish",
                params={
                    "creation_id": container_id,
                    "access_token": self.access_token,
                },
            )
            r2.raise_for_status()
            post_id = r2.json()["id"]

        url = f"https://www.instagram.com/p/{post_id}/"
        return PostResult(
            success=True,
            platform_post_id=post_id,
            platform_url=url,
            raw_response={"id": post_id},
        )

    async def health_check(self) -> bool:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{self._base}/{self.ig_user_id}",
                    params={"access_token": self.access_token, "fields": "id,name"},
                )
                return r.status_code == 200
        except Exception:
            return False


# ─── Facebook Adapter (Meta Graph API) ───────────────────────────────────────

class FacebookAdapter(SocialPlatformAdapter):
    platform_name = "facebook"

    def __init__(self, access_token: str, page_id: str):
        self.access_token = access_token
        self.page_id = page_id
        self._base = "https://graph.facebook.com/v19.0"

    async def post(self, payload: PostPayload) -> PostResult:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            params = {"message": payload.text, "access_token": self.access_token}
            if payload.image_url:
                params["link"] = payload.image_url
            r = await client.post(f"{self._base}/{self.page_id}/feed", params=params)
            r.raise_for_status()
            post_id = r.json()["id"]

        url = f"https://www.facebook.com/{post_id}"
        return PostResult(success=True, platform_post_id=post_id, platform_url=url)

    async def health_check(self) -> bool:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{self._base}/{self.page_id}",
                    params={"access_token": self.access_token, "fields": "id,name"},
                )
                return r.status_code == 200
        except Exception:
            return False


# ─── LinkedIn Adapter ─────────────────────────────────────────────────────────

class LinkedInAdapter(SocialPlatformAdapter):
    platform_name = "linkedin"

    def __init__(self, access_token: str, author_urn: str):
        self.access_token = access_token
        self.author_urn = author_urn
        self._base = "https://api.linkedin.com/v2"

    async def post(self, payload: PostPayload) -> PostResult:
        import httpx

        body = {
            "author": self.author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": payload.text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self._base}/ugcPosts",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                json=body,
            )
            r.raise_for_status()
            post_id = r.headers.get("x-restli-id", r.json().get("id", ""))

        return PostResult(
            success=True,
            platform_post_id=post_id,
            platform_url=f"https://www.linkedin.com/feed/update/{post_id}/",
            raw_response={"id": post_id},
        )

    async def health_check(self) -> bool:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{self._base}/me",
                    headers={"Authorization": f"Bearer {self.access_token}"},
                )
                return r.status_code == 200
        except Exception:
            return False


# ─── Twitter/X Adapter ───────────────────────────────────────────────────────

class TwitterAdapter(SocialPlatformAdapter):
    platform_name = "twitter"

    def __init__(self, api_key, api_secret, access_token, access_token_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.access_token_secret = access_token_secret

    async def post(self, payload: PostPayload) -> PostResult:
        try:
            import tweepy

            client = tweepy.Client(
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_token_secret,
            )
            text = payload.text[:280]
            response = client.create_tweet(text=text)
            tweet_id = str(response.data["id"])
            return PostResult(
                success=True,
                platform_post_id=tweet_id,
                platform_url=f"https://twitter.com/i/web/status/{tweet_id}",
            )
        except Exception as exc:
            return PostResult(success=False, error=str(exc))

    async def health_check(self) -> bool:
        try:
            import tweepy

            client = tweepy.Client(
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_token_secret,
            )
            client.get_me()
            return True
        except Exception:
            return False
