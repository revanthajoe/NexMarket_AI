"""
app/services/ai/brand_kit.py
─────────────────────────────
Brand Kit: manages uploaded logos, custom fonts, product images, contact
details and language settings per campaign.

Asset slots
───────────
  logo            brand/retailer logo (transparent PNG preferred)
  partner_logo    second logo, e.g. the product brand alongside the retailer
  product         product photograph (may have a background)
  product_cutout  pre-cut transparent product PNG used as the brochure hero
  map_image       small location map for the contact footer
  font_regular    optional custom TTF/OTF
  font_bold       optional custom TTF/OTF

`product_cutout` is supplied pre-cut on purpose. Automatic background removal
via rembg is not available here (no onnxruntime, and rembg requires numpy>=2.3
which conflicts irreconcilably with the numpy<2 that torch 2.1.2 needs), so the
cutout is an upload rather than something we compute.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.services.ai import text_shaper

logger = logging.getLogger(__name__)

_BRAND_DIR = Path(settings.POSTER_UPLOAD_DIR).parent / "brand_kits"
_BRAND_DIR.mkdir(parents=True, exist_ok=True)

_IMAGE_EXTS = ["png", "jpg", "jpeg", "webp"]
_FONT_EXTS  = ["ttf", "otf"]

# Valid values for the upload endpoint's asset_type.
ASSET_TYPES = (
    "logo", "partner_logo", "product", "product_cutout",
    "map_image", "font_regular", "font_bold",
)

# Text fields persisted in meta.json alongside language/brand_color_hex.
_META_TEXT_FIELDS = ("phone", "website", "address_en", "address_ta")


class BrandKit:
    """Represents the resolved brand assets for a specific campaign."""

    def __init__(
        self,
        campaign_id: str,
        logo_path: Optional[str] = None,
        partner_logo_path: Optional[str] = None,
        product_image_path: Optional[str] = None,
        product_cutout_path: Optional[str] = None,
        map_image_path: Optional[str] = None,
        font_regular_path: Optional[str] = None,
        font_bold_path: Optional[str] = None,
        language: str = "en",
        brand_color_hex: Optional[str] = None,
        phone: Optional[str] = None,
        website: Optional[str] = None,
        address_en: Optional[str] = None,
        address_ta: Optional[str] = None,
    ):
        self.campaign_id = campaign_id
        self.logo_path = logo_path
        self.partner_logo_path = partner_logo_path
        self.product_image_path = product_image_path
        self.product_cutout_path = product_cutout_path
        self.map_image_path = map_image_path
        self.font_regular_path = font_regular_path
        self.font_bold_path = font_bold_path
        self.language = language
        self.brand_color_hex = brand_color_hex
        self.phone = phone
        self.website = website
        self.address_en = address_en
        self.address_ta = address_ta

    @property
    def kit_dir(self) -> Path:
        d = _BRAND_DIR / self.campaign_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def has_contact_details(self) -> bool:
        """True when there is enough contact info to justify a footer zone."""
        return bool(self.phone or self.address_en or self.website)

    def pick_layout(self) -> str:
        """
        Choose the poster layout tier.

        Both tiers are *designed* layouts rendered by BrochureComposer. There is
        deliberately no tier that falls back to text floating over a photograph.

            "brochure" - every zone including the contact footer
            "designed" - same engine, contact footer omitted (the default)

        This replaced `has_brochure_assets()`, which required a product cutout
        AND contact details. Nothing ever supplied either — across 21 campaign
        kits on disk not one had them, and the dashboard had no way to upload
        them — so that gate was false 100% of the time and every poster silently
        degraded to the bare four-element overlay. The layout engine built for
        this never once ran. Tiers now change how much a zone *has to show*,
        never whether the poster gets a real layout at all.
        """
        if self.product_cutout_path and self.has_contact_details():
            return "brochure"
        return "designed"

    def has_brochure_assets(self) -> bool:
        """Deprecated alias — prefer `pick_layout()`."""
        return self.pick_layout() == "brochure"


def _read_meta(kit_dir: Path) -> dict:
    meta_file = kit_dir / "meta.json"
    if not meta_file.exists():
        return {}
    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("brand_kit meta unreadable campaign_dir=%s error=%s", kit_dir.name, exc)
        return {}


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

    meta = _read_meta(kit_dir)

    # Un-uploaded fonts fall back to the vendored Noto faces rather than Arial.
    # Arial has no Tamil glyphs, so it rendered Tamil as tofu boxes. The composer
    # additionally calls text_shaper.font_for_text() per string, which switches to
    # the Tamil face for Tamil runs; these are just the Latin defaults.
    return BrandKit(
        campaign_id         = campaign_id,
        logo_path           = _find("logo", _IMAGE_EXTS),
        partner_logo_path   = _find("partner_logo", _IMAGE_EXTS),
        product_image_path  = _find("product", _IMAGE_EXTS),
        product_cutout_path = _find("product_cutout", _IMAGE_EXTS),
        map_image_path      = _find("map_image", _IMAGE_EXTS),
        font_regular_path   = _find("font_regular", _FONT_EXTS) or str(text_shaper.FONT_LATIN_REGULAR),
        font_bold_path      = _find("font_bold", _FONT_EXTS) or str(text_shaper.FONT_LATIN_BOLD),
        language            = meta.get("language", "en"),
        brand_color_hex     = meta.get("brand_color_hex"),
        phone               = meta.get("phone"),
        website             = meta.get("website"),
        address_en          = meta.get("address_en"),
        address_ta          = meta.get("address_ta"),
    )


def save_brand_asset(campaign_id: str, asset_type: str, file_bytes: bytes, filename: str) -> str:
    """Save an uploaded brand asset. `asset_type` must be one of ASSET_TYPES."""
    kit_dir = _BRAND_DIR / campaign_id
    kit_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(filename).suffix.lower()
    dest = kit_dir / f"{asset_type}{suffix}"
    dest.write_bytes(file_bytes)
    logger.info("brand_kit saved asset=%s campaign=%s path=%s", asset_type, campaign_id, dest)
    return str(dest)


def save_brand_meta(
    campaign_id: str,
    language: Optional[str] = None,
    brand_color_hex: Optional[str] = None,
    **text_fields,
) -> dict:
    """
    Merge brand metadata into meta.json and return the merged result.

    Merging rather than overwriting is deliberate: the panel can save just the
    language, and a whole-file rewrite would silently wipe the contact details.
    Only keys actually passed are touched, so `None` means "leave unchanged"
    rather than "clear".
    """
    kit_dir = _BRAND_DIR / campaign_id
    kit_dir.mkdir(parents=True, exist_ok=True)

    meta = _read_meta(kit_dir)
    meta.setdefault("language", "en")
    meta.setdefault("brand_color_hex", None)

    if language is not None:
        meta["language"] = language
    if brand_color_hex is not None:
        meta["brand_color_hex"] = brand_color_hex
    for key in _META_TEXT_FIELDS:
        if text_fields.get(key) is not None:
            meta[key] = text_fields[key]

    (kit_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("brand_kit meta saved campaign=%s keys=%s", campaign_id, sorted(meta))
    return meta
