"""
Module 8: Social Media Posting System
Adapter pattern: each platform has its own adapter.
All adapters implement SocialPlatformAdapter interface.

Every adapter can do three things:
  * post()          — publish text (+ optional image) to the platform
  * fetch_metrics()  — read back engagement for a published post
  * health_check()   — verify the configured credentials still work
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# Meta processes uploaded media asynchronously; publishing before the container
# reports FINISHED fails with "Media ID is not available".
IG_CONTAINER_POLL_ATTEMPTS = 15
IG_CONTAINER_POLL_INTERVAL = 2  # seconds


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


class PostMetrics:
    """Engagement read back from a platform for one published post."""

    def __init__(
        self,
        impressions: int = 0,
        clicks: int = 0,
        likes: int = 0,
        shares: int = 0,
        comments: int = 0,
        reach: int = 0,
        spend: float = 0.0,
        is_mock: bool = False,
        error: Optional[str] = None,
        unavailable: bool = False,
    ):
        self.impressions = int(impressions)
        self.clicks = int(clicks)
        self.likes = int(likes)
        self.shares = int(shares)
        self.comments = int(comments)
        self.reach = int(reach)
        self.spend = float(spend)
        self.is_mock = is_mock
        self.error = error
        self.unavailable = unavailable

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def ctr(self) -> float:
        return round(self.clicks / self.impressions, 6) if self.impressions else 0.0

    def as_dict(self) -> dict:
        return {
            "impressions": self.impressions,
            "clicks": self.clicks,
            "likes": self.likes,
            "shares": self.shares,
            "comments": self.comments,
            "reach": self.reach,
            "ctr": self.ctr,
            "spend": self.spend,
        }


class SocialPlatformAdapter(ABC):
    platform_name: str = "base"
    # False for MockAdapter — lets callers tell a real integration from a stub.
    is_live: bool = True

    @abstractmethod
    async def post(self, payload: PostPayload) -> PostResult:
        """Publish content. Must be idempotent."""
        ...

    @abstractmethod
    async def fetch_metrics(self, platform_post_id: str) -> PostMetrics:
        """Read engagement back for a previously published post."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Returns True if credentials are valid."""
        ...


def _resolve_local_media(image_url: Optional[str]):
    """
    Map a poster URL back to the file on disk, or None if it isn't ours.

    Lets Telegram upload the bytes directly instead of handing the platform a
    URL it has to fetch — which is what makes Telegram usable in live mode from
    a developer machine, where STATIC_BASE_URL is localhost and unreachable
    from the internet. Returns None (caller falls back to the URL form) rather
    than raising, since a non-local URL is a perfectly valid input.
    """
    if not image_url:
        return None
    try:
        from pathlib import Path

        from app.core.config import settings

        filename = image_url.split("/")[-1].split("?")[0]
        configured_dir = Path(settings.POSTER_UPLOAD_DIR)
        candidates = [configured_dir / filename]
        if not configured_dir.is_absolute():
            backend_root = Path(__file__).resolve().parents[3]
            candidates.append(backend_root / configured_dir / filename)
        return next((candidate for candidate in candidates if candidate.is_file()), None)
    except Exception:
        return None


def _is_local_media_url(image_url: Optional[str]) -> bool:
    """Whether an image URL points at this app's local static media."""
    if not image_url:
        return False
    from app.core.config import settings

    return image_url.startswith(settings.STATIC_BASE_URL) or image_url.startswith("/static/")


def _api_error(resp) -> str:
    """Human-readable message from a platform error response.

    Platform APIs put the useful part in the body; `raise_for_status()` throws it
    away and leaves only the status code, which is useless for debugging a
    rejected token or a malformed caption.
    """
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    if isinstance(body, dict) and "error" in body:
        err = body["error"]
        if isinstance(err, dict):
            return f"{resp.status_code}: {err.get('message', err)}"
    return f"{resp.status_code}: {body}"


# ─── Mock Adapter (Demo / Fallback) ──────────────────────────────────────────

class MockAdapter(SocialPlatformAdapter):
    is_live = False

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

    async def fetch_metrics(self, platform_post_id: str) -> PostMetrics:
        """Deterministic per post id, so repeated syncs don't make numbers jump.

        Always flagged `is_mock` — callers must label anything derived from it
        rather than presenting it as measured engagement.
        """
        h = hashlib.sha256(platform_post_id.encode()).digest()
        impressions = 500 + h[0] * 12
        reach = int(impressions * 0.7)
        clicks = int(impressions * (0.01 + h[1] / 255 * 0.04))
        return PostMetrics(
            impressions=impressions,
            reach=reach,
            clicks=clicks,
            likes=int(clicks * 1.8),
            shares=h[2] % 20,
            comments=h[3] % 15,
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
            if r1.status_code >= 400:
                return PostResult(success=False, error=f"container: {_api_error(r1)}")
            container_id = r1.json()["id"]

            # Step 2: wait for Meta to finish ingesting the image
            ready = await self._await_container(client, container_id)
            if not ready:
                return PostResult(
                    success=False,
                    error=f"container {container_id} not ready after "
                          f"{IG_CONTAINER_POLL_ATTEMPTS * IG_CONTAINER_POLL_INTERVAL}s",
                )

            # Step 3: publish container
            r2 = await client.post(
                f"{self._base}/{self.ig_user_id}/media_publish",
                params={
                    "creation_id": container_id,
                    "access_token": self.access_token,
                },
            )
            if r2.status_code >= 400:
                return PostResult(success=False, error=f"publish: {_api_error(r2)}")
            post_id = r2.json()["id"]

            # The shortcode (not the media id) is what appears in a public URL.
            permalink = None
            r3 = await client.get(
                f"{self._base}/{post_id}",
                params={"fields": "permalink", "access_token": self.access_token},
            )
            if r3.status_code < 400:
                permalink = r3.json().get("permalink")

        return PostResult(
            success=True,
            platform_post_id=post_id,
            platform_url=permalink or f"https://www.instagram.com/p/{post_id}/",
            raw_response={"id": post_id, "container_id": container_id},
        )

    async def _await_container(self, client, container_id: str) -> bool:
        for _ in range(IG_CONTAINER_POLL_ATTEMPTS):
            r = await client.get(
                f"{self._base}/{container_id}",
                params={"fields": "status_code", "access_token": self.access_token},
            )
            if r.status_code >= 400:
                return False
            status = r.json().get("status_code")
            if status == "FINISHED":
                return True
            if status == "ERROR":
                return False
            await asyncio.sleep(IG_CONTAINER_POLL_INTERVAL)
        return False

    async def fetch_metrics(self, platform_post_id: str) -> PostMetrics:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                insights = await client.get(
                    f"{self._base}/{platform_post_id}/insights",
                    params={
                        "metric": "impressions,reach",
                        "access_token": self.access_token,
                    },
                )
                counts = await client.get(
                    f"{self._base}/{platform_post_id}",
                    params={
                        "fields": "like_count,comments_count",
                        "access_token": self.access_token,
                    },
                )
        except Exception as exc:
            return PostMetrics(error=str(exc))

        if counts.status_code >= 400:
            return PostMetrics(error=_api_error(counts))

        values = {}
        if insights.status_code < 400:
            for row in insights.json().get("data", []):
                vals = row.get("values") or [{}]
                values[row.get("name")] = vals[0].get("value", 0)

        body = counts.json()
        return PostMetrics(
            impressions=values.get("impressions", 0),
            reach=values.get("reach", 0),
            likes=body.get("like_count", 0),
            comments=body.get("comments_count", 0),
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
            if payload.image_url:
                # /photos publishes the image itself. Passing it as `link` on
                # /feed only produces a link preview, which is not a poster post.
                r = await client.post(
                    f"{self._base}/{self.page_id}/photos",
                    params={
                        "url": payload.image_url,
                        "caption": payload.text,
                        "access_token": self.access_token,
                    },
                )
            else:
                r = await client.post(
                    f"{self._base}/{self.page_id}/feed",
                    params={"message": payload.text, "access_token": self.access_token},
                )

            if r.status_code >= 400:
                return PostResult(success=False, error=_api_error(r))
            body = r.json()

        # /photos returns {id, post_id}; /feed returns {id}.
        post_id = body.get("post_id") or body["id"]
        return PostResult(
            success=True,
            platform_post_id=post_id,
            platform_url=f"https://www.facebook.com/{post_id}",
            raw_response=body,
        )

    async def fetch_metrics(self, platform_post_id: str) -> PostMetrics:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                insights = await client.get(
                    f"{self._base}/{platform_post_id}/insights",
                    params={
                        "metric": "post_impressions,post_impressions_unique,post_clicks",
                        "access_token": self.access_token,
                    },
                )
                counts = await client.get(
                    f"{self._base}/{platform_post_id}",
                    params={
                        "fields": "likes.summary(true),comments.summary(true),shares",
                        "access_token": self.access_token,
                    },
                )
        except Exception as exc:
            return PostMetrics(error=str(exc))

        if counts.status_code >= 400:
            return PostMetrics(error=_api_error(counts))

        values = {}
        if insights.status_code < 400:
            for row in insights.json().get("data", []):
                vals = row.get("values") or [{}]
                values[row.get("name")] = vals[0].get("value", 0)

        body = counts.json()
        return PostMetrics(
            impressions=values.get("post_impressions", 0),
            reach=values.get("post_impressions_unique", 0),
            clicks=values.get("post_clicks", 0),
            likes=body.get("likes", {}).get("summary", {}).get("total_count", 0),
            comments=body.get("comments", {}).get("summary", {}).get("total_count", 0),
            shares=(body.get("shares") or {}).get("count", 0),
        )

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


# ─── Telegram Adapter ─────────────────────────────────────────────────────────

class TelegramAdapter(SocialPlatformAdapter):
    """
    Official Telegram Bot API.

    Notably the ONE platform here that works in live mode without a publicly
    reachable server: `sendPhoto` accepts a multipart file upload, so the poster
    is pushed as bytes rather than as a URL Telegram has to fetch. Instagram,
    Facebook and WhatsApp all require a public URL (see PUBLIC_MEDIA_BASE_URL).
    The URL form is kept as a fallback for when the local file cannot be found.
    """

    platform_name = "telegram"

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token.strip()
        self.chat_id = chat_id.strip()
        self._base = f"https://api.telegram.org/bot{self.bot_token}"

    @property
    def _safe_base(self) -> str:
        """Base URL with the token redacted — safe to put in an error message."""
        return "https://api.telegram.org/bot<redacted>"

    async def post(self, payload: PostPayload) -> PostResult:
        import httpx

        if not self.bot_token or not self.chat_id:
            return PostResult(
                success=False,
                error="Telegram requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID",
            )

        local_file = _resolve_local_media(payload.image_url) if payload.image_url else None

        async with httpx.AsyncClient(timeout=30) as client:
            if local_file is not None:
                # Preferred path: upload the bytes directly.
                with open(local_file, "rb") as fh:
                    r = await client.post(
                        f"{self._base}/sendPhoto",
                        data={"chat_id": self.chat_id, "caption": payload.text[:1024]},
                        files={"photo": (local_file.name, fh, "image/png")},
                    )
            elif payload.image_url and not _is_local_media_url(payload.image_url):
                r = await client.post(
                    f"{self._base}/sendPhoto",
                    data={
                        "chat_id": self.chat_id,
                        "photo": payload.image_url,
                        "caption": payload.text[:1024],
                    },
                )
            elif payload.image_url:
                return PostResult(
                    success=False,
                    error="Telegram could not find the local poster file to upload",
                )
            else:
                r = await client.post(
                    f"{self._base}/sendMessage",
                    data={"chat_id": self.chat_id, "text": payload.text},
                )

            if r.status_code >= 400:
                return PostResult(success=False, error=_telegram_error(r))

            body = r.json()

        if not body.get("ok"):
            # Telegram can return HTTP 200 with {"ok": false}.
            return PostResult(success=False, error=str(body.get("description", body)))

        result = body.get("result", {})
        message_id = str(result.get("message_id", ""))
        chat = result.get("chat", {}) or {}
        username = chat.get("username")
        url = f"https://t.me/{username}/{message_id}" if username else None

        return PostResult(
            success=True,
            platform_post_id=message_id,
            platform_url=url,
            raw_response=body,
        )

    async def fetch_metrics(self, platform_post_id: str) -> PostMetrics:
        """
        The Bot API exposes no per-message analytics for ordinary sends — view
        counts exist only for channel posts via a different surface, and there is
        no impressions/clicks concept at all.

        Returns an explicit error rather than zeros: zeros would be indexed by
        the analytics tab as real measurements and silently drag every average
        down, which is exactly the "fabricated statistics" failure this codebase
        already guards against elsewhere with `is_mock`/`fallback` flags.
        """
        return PostMetrics(
            error="Telegram Bot API exposes no per-message engagement metrics",
            unavailable=True,
        )

    async def health_check(self) -> bool:
        import httpx

        if not self.bot_token or not self.chat_id:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                bot = await client.get(f"{self._base}/getMe")
                if bot.status_code != 200 or not bot.json().get("ok", False):
                    return False
                chat = await client.get(
                    f"{self._base}/getChat",
                    params={"chat_id": self.chat_id},
                )
                return chat.status_code == 200 and chat.json().get("ok", False)
        except Exception:
            return False


def _telegram_error(resp) -> str:
    """
    Telegram error text, with the bot token stripped.

    `_api_error()` can echo a request URL, and Telegram puts the bot token in
    the PATH — so the generic helper would leak the credential straight into a
    log line and a stored `error_message` DB column.
    """
    try:
        body = resp.json()
        detail = body.get("description", body)
    except Exception:
        detail = resp.text
    return f"{resp.status_code}: {detail}"


# ─── WhatsApp Business Adapter ────────────────────────────────────────────────

class WhatsAppAdapter(SocialPlatformAdapter):
    """
    Official WhatsApp Business Cloud API.

    Unlike the other adapters this is business MESSAGE DISTRIBUTION, not
    broadcast publishing: there is no public feed, each send targets a specific
    recipient number, and outside a 24-hour customer-service window Meta only
    permits pre-approved message templates.
    """

    platform_name = "whatsapp"

    def __init__(self, access_token: str, phone_number_id: str, recipient: str):
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.recipient = recipient
        self._base = "https://graph.facebook.com/v19.0"

    async def post(self, payload: PostPayload) -> PostResult:
        import httpx

        if payload.image_url:
            body = {
                "messaging_product": "whatsapp",
                "to": self.recipient,
                "type": "image",
                "image": {"link": payload.image_url, "caption": payload.text[:1024]},
            }
        else:
            body = {
                "messaging_product": "whatsapp",
                "to": self.recipient,
                "type": "text",
                "text": {"body": payload.text},
            }

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self._base}/{self.phone_number_id}/messages",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json=body,
            )
            if r.status_code >= 400:
                return PostResult(success=False, error=_api_error(r))
            data = r.json()

        messages = data.get("messages") or []
        if not messages:
            return PostResult(success=False, error=f"no message id in response: {data}")

        return PostResult(
            success=True,
            platform_post_id=messages[0].get("id"),
            platform_url=None,          # WhatsApp messages have no public URL
            raw_response=data,
        )

    async def fetch_metrics(self, platform_post_id: str) -> PostMetrics:
        """
        Delivery/read receipts arrive by webhook callback, not by polling — there
        is no "fetch status for message id" endpoint. Same reasoning as Telegram:
        an explicit error beats zeros that look like real measurements.
        """
        return PostMetrics(
            error="WhatsApp delivery status arrives via webhook, not a metrics read",
        )

    async def health_check(self) -> bool:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{self._base}/{self.phone_number_id}",
                    headers={"Authorization": f"Bearer {self.access_token}"},
                )
                return r.status_code == 200
        except Exception:
            return False
