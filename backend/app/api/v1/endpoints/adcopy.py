"""Ad Copy generation endpoints."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import AdCopy, Campaign
from app.schemas.schemas import AdCopyGenerateRequest, AdCopyRead
from app.services.ai.ad_generator import ad_copy_generator

router = APIRouter(prefix="/adcopy", tags=["Ad Copy"])


@router.post("/generate", response_model=List[AdCopyRead])
async def generate_ad_copy(
    payload: AdCopyGenerateRequest, db: AsyncSession = Depends(get_db)
):
    campaign = await db.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    copies = await ad_copy_generator.generate(
        product_name=campaign.product_name,
        description=campaign.description,
        offer=campaign.offer,
        target_audience=campaign.target_audience,
        campaign_goal=campaign.campaign_goal,
        platforms=payload.platforms,
        tone=payload.tone or "professional",
    )

    results = []
    for platform, data in copies.items():
        ad = AdCopy(
            campaign_id=campaign.id,
            platform=platform,
            headline=data.get("headline"),
            body=data.get("body", ""),
            cta_variants=data.get("cta_variants", []),
            hashtags=data.get("hashtags", []),
            tone=payload.tone,
        )
        db.add(ad)
        await db.flush()
        await db.refresh(ad)
        results.append(ad)

    return results


@router.get("/{campaign_id}", response_model=List[AdCopyRead])
async def get_ad_copies(campaign_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AdCopy).where(AdCopy.campaign_id == campaign_id)
    )
    return result.scalars().all()
