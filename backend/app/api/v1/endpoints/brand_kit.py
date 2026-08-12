"""
app/api/v1/endpoints/brand_kit.py
───────────────────────────────────
Brand Kit upload + configuration endpoints.

Routes:
  POST /brand-kit/{campaign_id}/upload   — upload logo / product image / fonts
  POST /brand-kit/{campaign_id}/meta     — set language, brand colour
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


@router.post("/{campaign_id}/upload")
async def upload_brand_asset(
    campaign_id: str,
    asset_type: Literal["logo", "product", "font_regular", "font_bold"] = Form(...),
    file: UploadFile = File(...),
):
    """Upload a brand asset (logo PNG, product image, or custom font TTF)."""
    content = await file.read()
    if len(content) > _MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(400, f"File too large (max {_MAX_FILE_MB}MB)")

    path = save_brand_asset(campaign_id, asset_type, content, file.filename or f"{asset_type}.bin")
    logger.info("brand_kit_upload campaign=%s type=%s", campaign_id, asset_type)
    return {"status": "ok", "asset_type": asset_type, "path": path}


@router.post("/{campaign_id}/meta")
async def set_brand_meta(
    campaign_id: str,
    language: str = Form("en"),
    brand_color_hex: Optional[str] = Form(None),
):
    """Set language code (en/hi/ta/...) and optional brand colour (#RRGGBB)."""
    save_brand_meta(campaign_id, language, brand_color_hex)
    return {"status": "ok", "language": language, "brand_color_hex": brand_color_hex}


@router.get("/{campaign_id}")
async def get_brand_kit_info(campaign_id: str):
    """Return the current brand kit configuration for a campaign."""
    kit = get_brand_kit(campaign_id)
    return {
        "campaign_id": campaign_id,
        "logo":        kit.logo_path,
        "product":     kit.product_image_path,
        "font_regular": kit.font_regular_path,
        "font_bold":   kit.font_bold_path,
        "language":    kit.language,
        "brand_color_hex": kit.brand_color_hex,
    }
