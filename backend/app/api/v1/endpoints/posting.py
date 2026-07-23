"""Social posting endpoints — publish + schedule + status."""
from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import AdCopy, Campaign, Poster, SocialPost
from app.schemas.schemas import PostRequest, PostStatusRead
from app.services.posting.posting_service import social_posting_service

router = APIRouter(prefix="/posting", tags=["Social Posting"])


@router.post("/publish", response_model=PostStatusRead)
async def publish_post(
    payload: PostRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
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
        # Post immediately in background (non-blocking response)
        async def do_post():
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as bg_db:
                sp = await bg_db.get(SocialPost, social_post.id)
                await social_posting_service.publish(bg_db, sp, text, image_url)
                await bg_db.commit()

        background_tasks.add_task(do_post)
        social_post.status = "posting"

    return social_post


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
):
    post = await db.get(SocialPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.status not in ("failed", "pending"):
        raise HTTPException(status_code=400, detail=f"Cannot retry post in status '{post.status}'")

    post.retry_count = 0
    text = "[Retry] " + (post.response_payload or {}).get("text", "NexMarket AI campaign post")

    async def do_retry():
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as bg_db:
            sp = await bg_db.get(SocialPost, post_id)
            await social_posting_service.publish(bg_db, sp, text)
            await bg_db.commit()

    background_tasks.add_task(do_retry)
    post.status = "posting"
    return post


@router.get("/health/platforms")
async def platform_health():
    return await social_posting_service.health_check_all()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _resolve_text(db: AsyncSession, payload: PostRequest) -> str:
    if payload.ad_copy_id:
        ad = await db.get(AdCopy, payload.ad_copy_id)
        if ad:
            return ad.body
    campaign = await db.get(Campaign, payload.campaign_id)
    return f"{campaign.product_name} — {campaign.offer}"


async def _resolve_image(db: AsyncSession, payload: PostRequest):
    if payload.poster_id:
        poster = await db.get(Poster, payload.poster_id)
        if poster:
            return poster.image_url
    return None
