"""
app/api/v1/endpoints/brand_kit.py
───────────────────────────────────
Brand Kit upload + configuration endpoints.

Routes:
  POST /brand-kit/{campaign_id}/upload   — upload logo / product / cutout / map / fonts
  POST /brand-kit/{campaign_id}/meta     — set language, colour, contact details
  GET  /brand-kit/{campaign_id}          — read current brand kit metadata
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services.ai.brand_kit import get_brand_kit, save_brand_asset, save_brand_meta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/brand-kit", tags=["Brand Kit"])

_MAX_FILE_MB = 10

AssetType = Literal[
    "logo", "partner_logo", "product", "product_cutout",
    "map_image", "font_regular", "font_bold",
]


@router.post("/{campaign_id}/upload")
async def upload_brand_asset(
    campaign_id: str,
    asset_type: AssetType = Form(...),
    file: UploadFile = File(...),
):
    """
    Upload a brand asset.

    `product_cutout` should be a pre-cut transparent PNG — it becomes the
    brochure hero image and is composited as-is (no background removal is
    performed; see the note in services/ai/brand_kit.py).
    """
    content = await file.read()
    if len(content) > _MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(400, f"File too large (max {_MAX_FILE_MB}MB)")

    path = save_brand_asset(campaign_id, asset_type, content, file.filename or f"{asset_type}.bin")
    logger.info("brand_kit_upload campaign=%s type=%s", campaign_id, asset_type)
    return {"status": "ok", "asset_type": asset_type, "path": path}


@router.post("/{campaign_id}/meta")
async def set_brand_meta(
    campaign_id: str,
    language: Optional[str] = Form(None),
    brand_color_hex: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    website: Optional[str] = Form(None),
    address_en: Optional[str] = Form(None),
    address_ta: Optional[str] = Form(None),
):
    """
    Set language code (en/hi/ta/...), brand colour (#RRGGBB) and contact details.

    Fields are merged, not replaced — omitting a field leaves the stored value
    alone, so saving just the language cannot wipe the contact block.
    """
    meta = save_brand_meta(
        campaign_id,
        language=language,
        brand_color_hex=brand_color_hex,
        phone=phone,
        website=website,
        address_en=address_en,
        address_ta=address_ta,
    )
    return {"status": "ok", **meta}


@router.get("/{campaign_id}")
async def get_brand_kit_info(campaign_id: str):
    """Return the current brand kit configuration for a campaign."""
    kit = get_brand_kit(campaign_id)
    return {
        "campaign_id":     campaign_id,
        "logo":            kit.logo_path,
        "partner_logo":    kit.partner_logo_path,
        "product":         kit.product_image_path,
        "product_cutout":  kit.product_cutout_path,
        "map_image":       kit.map_image_path,
        "font_regular":    kit.font_regular_path,
        "font_bold":       kit.font_bold_path,
        "language":        kit.language,
        "brand_color_hex": kit.brand_color_hex,
        "phone":           kit.phone,
        "website":         kit.website,
        "address_en":      kit.address_en,
        "address_ta":      kit.address_ta,
        # Which poster layout this kit currently qualifies for. Surfaced so the
        # dashboard can show *why* a poster looks the way it does, and what to
        # upload to unlock the richer tier, instead of silently downgrading.
        "layout":              kit.pick_layout(),
        "has_contact_details": kit.has_contact_details(),
        "has_brochure_assets": kit.has_brochure_assets(),
    }
