"""Campaign CRUD endpoints."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import Campaign
from app.schemas.schemas import CampaignCreate, CampaignRead, CampaignSummary

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


@router.post("/", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
async def create_campaign(payload: CampaignCreate, db: AsyncSession = Depends(get_db)):
    campaign = Campaign(**payload.model_dump(exclude={"post_schedule"}))
    db.add(campaign)
    await db.flush()
    await db.refresh(campaign)
    return campaign


@router.get("/", response_model=List[CampaignSummary])
async def list_campaigns(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Campaign).order_by(Campaign.created_at.desc()).limit(100)
    )
    return result.scalars().all()


@router.get("/{campaign_id}", response_model=CampaignRead)
async def get_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.patch("/{campaign_id}/status")
async def update_status(
    campaign_id: str,
    status_val: str,
    db: AsyncSession = Depends(get_db),
):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = status_val
    return {"id": campaign_id, "status": status_val}


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await db.delete(campaign)
