"""Social posting endpoints — publish + schedule + status."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import Campaign, SocialPost
from app.schemas.schemas import CampaignPublishRequest, PostRequest, PostStatusRead
from app.services.posting.posting_service import (
    SUPPORTED_PLATFORMS,
    resolve_post_image,
    resolve_post_text,
    social_posting_service,
)
from app.core.security import (
    require_app_api_key,
    require_n8n_access,
    require_telegram_webhook_secret,
)

router = APIRouter(prefix="/posting", tags=["Social Posting"])


@router.post("/publish", response_model=PostStatusRead)
async def publish_post(
    payload: PostRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_app_api_key),
):
    campaign = await db.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Build the social post record
    social_post = SocialPost(
        campaign_id=payload.campaign_id,
        platform=payload.platform,
        ad_copy_id=payload.ad_copy_id,
        poster_id=payload.poster_id,
        scheduled_at=payload.scheduled_at,
        status="pending",
    )
    db.add(social_post)
    await db.flush()
    await db.refresh(social_post)

    # Resolve text + image
    text = await _resolve_text(db, payload)
    image_url = await _resolve_image(db, payload)

    if payload.scheduled_at and payload.scheduled_at > datetime.utcnow():
        # Schedule: mark as scheduled, worker picks it up
        await social_posting_service.schedule(db, social_post)
    else:
        # Mark "posting" BEFORE committing. Assigning it after the commit (as
        # this did originally) leaves the attribute dirty on this request's
        # session, and get_db()'s post-yield commit then flushes it — reverting
        # the background task's "posted" if the task got there first. Verified:
        # rows sat at `posting` with a populated platform_post_id, i.e.
        # published but permanently reported as in-flight, which also meant the
        # retry endpoint saw them as unfinished.
        social_post.status = "posting"

        # Commit now so the row is visible to the background task's own DB
        # session — BackgroundTasks can run before get_db()'s post-yield
        # commit, otherwise bg_db.get(SocialPost, ...) races and returns None.
        await db.commit()
        await db.refresh(social_post)

        # Post immediately in background (non-blocking response)
        async def do_post():
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as bg_db:
                sp = await bg_db.get(SocialPost, social_post.id)
                await social_posting_service.publish(bg_db, sp, text, image_url)
                await bg_db.commit()

        background_tasks.add_task(do_post)

    return social_post


@router.post("/campaign/{campaign_id}/publish", response_model=List[PostStatusRead])
async def publish_campaign_to_platforms(
    campaign_id: str,
    payload: CampaignPublishRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_app_api_key),
):
    """
    Publish one campaign to several platforms in a single call.

    Each platform gets its own `SocialPost` row and is published independently,
    so one platform failing cannot fail the others — Instagram can end up
    `failed` while Telegram and Facebook are `posted`. That independence is a
    property of the per-row model and the per-task publish below, not of any
    aggregate status, which is why no combined status is returned.
    """
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    unknown = [p for p in payload.platforms if p not in SUPPORTED_PLATFORMS]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported platform(s): {', '.join(unknown)}. "
                f"Supported: {', '.join(SUPPORTED_PLATFORMS)}"
            ),
        )

    text = await resolve_post_text(db, campaign_id, payload.ad_copy_id)
    image_url = await resolve_post_image(db, payload.poster_id)

    scheduled = bool(payload.scheduled_at and payload.scheduled_at > datetime.utcnow())
    if scheduled:
        posts = [
            SocialPost(
                campaign_id=campaign_id, platform=platform,
                ad_copy_id=payload.ad_copy_id, poster_id=payload.poster_id,
                scheduled_at=payload.scheduled_at, status="pending",
            )
            for platform in payload.platforms
        ]
        for sp in posts:
            db.add(sp)
        await db.flush()
        for sp in posts:
            await db.refresh(sp)
        for sp in posts:
            await social_posting_service.schedule(db, sp)
        return posts

    # create_posts_for_platforms() commits with status="posting" already set —
    # see its docstring for why the ordering (status set before commit) matters.
    posts = await social_posting_service.create_posts_for_platforms(
        db, campaign_id, payload.platforms, payload.ad_copy_id, payload.poster_id,
    )
    post_ids = [sp.id for sp in posts]

    async def publish_all():
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as bg_db:
            sps = []
            for pid in post_ids:
                sp = await bg_db.get(SocialPost, pid)
                if sp is not None:
                    sps.append(sp)
            await social_posting_service.publish_platforms(bg_db, sps, text, image_url)

    background_tasks.add_task(publish_all)
    return posts


@router.get("/campaign/{campaign_id}", response_model=List[PostStatusRead])
async def get_posts_for_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SocialPost)
        .where(SocialPost.campaign_id == campaign_id)
        .order_by(SocialPost.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{post_id}", response_model=PostStatusRead)
async def get_post_status(post_id: str, db: AsyncSession = Depends(get_db)):
    post = await db.get(SocialPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.post("/retry/{post_id}", response_model=PostStatusRead)
async def retry_post(
    post_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_app_api_key),
):
    post = await db.get(SocialPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.status not in ("failed", "pending"):
        raise HTTPException(status_code=400, detail=f"Cannot retry post in status '{post.status}'")

    # Re-resolve the real content. This used to build "[Retry] " plus
    # response_payload["text"] — nothing ever wrote that key, so every retry
    # re-posted the literal placeholder string instead of the campaign copy,
    # and it passed no image_url so the poster was silently dropped.
    text = await resolve_post_text(db, post.campaign_id, post.ad_copy_id)
    image_url = await resolve_post_image(db, post.poster_id)

    # Set the status and COMMIT before scheduling the task, exactly as
    # publish_post() does above. Assigning it after add_task() leaves the
    # attribute dirty on this request's session, so get_db()'s post-yield
    # commit flushes "posting" over the background task's "posted" — the row
    # ends up published but permanently reported as in-flight.
    post.retry_count = 0
    post.status = "posting"
    await db.commit()
    await db.refresh(post)

    async def do_retry():
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as bg_db:
            sp = await bg_db.get(SocialPost, post_id)
            await social_posting_service.publish(bg_db, sp, text, image_url)
            await bg_db.commit()

    background_tasks.add_task(do_retry)
    return post


@router.get("/health/platforms")
async def platform_health():
    """Boolean-per-platform view, kept for existing callers."""
    return await social_posting_service.health_check_all()


@router.get("/integrations/status")
async def integrations_status():
    """Full integration state per platform: configured / healthy / live-or-mock."""
    return await social_posting_service.platform_status()


@router.post("/metrics/sync/{campaign_id}")
async def sync_campaign_metrics(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_n8n_access),
):
    """Pull engagement back from each platform into AnalyticsEvent rows."""
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return await social_posting_service.sync_campaign_metrics(db, campaign_id)


@router.post("/telegram/webhook")
async def telegram_webhook(
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_telegram_webhook_secret),
):
    """Receive Telegram Bot API updates for post metrics and replies."""
    return await social_posting_service.ingest_telegram_update(db, data)


@router.post("/scheduled/run")
async def run_scheduled_posts(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_n8n_access),
):
    """Publish every scheduled post that is now due (called by n8n or the worker)."""
    count = await social_posting_service.publish_scheduled_due(db)
    return {"status": "ok", "published": count}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _resolve_text(db: AsyncSession, payload: PostRequest) -> str:
    return await resolve_post_text(db, payload.campaign_id, payload.ad_copy_id)


async def _resolve_image(db: AsyncSession, payload: PostRequest):
    return await resolve_post_image(db, payload.poster_id)
