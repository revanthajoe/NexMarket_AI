"""
app/services/ai/brand_kit.py
─────────────────────────────
Brand Kit: manages uploaded logos, custom fonts, product images,
and language settings per campaign.
"""
from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_BRAND_DIR = Path(settings.POSTER_UPLOAD_DIR).parent / "brand_kits"
_BRAND_DIR.mkdir(parents=True, exist_ok=True)


class BrandKit:
    """Represents the resolved brand assets for a specific campaign."""

    def __init__(
        self,
        campaign_id: str,
        logo_path: Optional[str] = None,
        product_image_path: Optional[str] = None,
        font_regular_path: Optional[str] = None,
        font_bold_path: Optional[str] = None,
        language: str = "en",
        brand_color_hex: Optional[str] = None,
    ):
        self.campaign_id = campaign_id
        self.logo_path = logo_path
        self.product_image_path = product_image_path
        self.font_regular_path = font_regular_path
        self.font_bold_path = font_bold_path
        self.language = language
        self.brand_color_hex = brand_color_hex

    @property
    def kit_dir(self) -> Path:
        d = _BRAND_DIR / self.campaign_id
        d.mkdir(parents=True, exist_ok=True)
        return d


def get_brand_kit(campaign_id: str) -> BrandKit:
    """Load the brand kit for a campaign from the filesystem."""
    kit_dir = _BRAND_DIR / campaign_id
    kit_dir.mkdir(parents=True, exist_ok=True)

    def _find(name: str, exts: list[str]) -> Optional[str]:
        for ext in exts:
            f = kit_dir / f"{name}.{ext}"
            if f.exists():
                return str(f)
        return None

    logo = _find("logo", ["png", "jpg", "jpeg", "webp"])
    product = _find("product", ["png", "jpg", "jpeg", "webp"])
    font_reg = _find("font_regular", ["ttf", "otf"])
    font_bold = _find("font_bold", ["ttf", "otf"])

    # Fallback to Windows/system fonts if no custom font uploaded
    system_bold = r"C:\Windows\Fonts\arialbd.ttf"
    system_reg  = r"C:\Windows\Fonts\arial.ttf"
    
    # Also try project-level assets/fonts directory
    proj_fonts = Path(settings.POSTER_UPLOAD_DIR).parent / "fonts"
    for pf in proj_fonts.glob("*bold*"):
        if pf.suffix.lower() in (".ttf", ".otf"):
            system_bold = str(pf)
            break
    for pf in proj_fonts.glob("*regular*"):
        if pf.suffix.lower() in (".ttf", ".otf"):
            system_reg = str(pf)
            break

    # Read metadata file if present
    meta_file = kit_dir / "meta.json"
    language = "en"
    brand_color = None
    if meta_file.exists():
        import json
        try:
            meta = json.loads(meta_file.read_text())
            language = meta.get("language", "en")
            brand_color = meta.get("brand_color_hex")
        except Exception:
            pass

    return BrandKit(
        campaign_id=campaign_id,
        logo_path=logo,
        product_image_path=product,
        font_regular_path=font_reg or system_reg,
        font_bold_path=font_bold or system_bold,
        language=language,
        brand_color_hex=brand_color,
    )


def save_brand_asset(campaign_id: str, asset_type: str, file_bytes: bytes, filename: str) -> str:
    """
    Save an uploaded brand asset.
    asset_type: 'logo' | 'product' | 'font_regular' | 'font_bold'
    Returns the saved file path.
    """
    kit_dir = _BRAND_DIR / campaign_id
    kit_dir.mkdir(parents=True, exist_ok=True)
    
    suffix = Path(filename).suffix.lower()
    dest = kit_dir / f"{asset_type}{suffix}"
    dest.write_bytes(file_bytes)
    logger.info("brand_kit saved asset=%s campaign=%s path=%s", asset_type, campaign_id, dest)
    return str(dest)


def save_brand_meta(campaign_id: str, language: str, brand_color_hex: Optional[str] = None) -> None:
    """Save brand metadata (language, colour) to a JSON file."""
    import json
    kit_dir = _BRAND_DIR / campaign_id
    kit_dir.mkdir(parents=True, exist_ok=True)
    meta = {"language": language, "brand_color_hex": brand_color_hex}
    (kit_dir / "meta.json").write_text(json.dumps(meta))
    logger.info("brand_kit meta saved campaign=%s language=%s", campaign_id, language)
