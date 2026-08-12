"""
app/services/ai/platform_formats.py
─────────────────────────────────────
Platform-aware poster format definitions.
Provides the correct resolution, aspect ratio, and safe margins
for each supported social platform / content type.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PosterFormat:
    platform: str
    content_type: str          # "feed" | "story" | "banner" | "square"
    width: int
    height: int
    aspect_ratio: str          # e.g. "1:1", "9:16", "1.91:1"
    safe_margin_pct: float = 0.06   # % of min(w,h) to use as margin
    sdxl_width: int = 768           # SDXL-friendly generation resolution
    sdxl_height: int = 768

    @property
    def aspect(self) -> float:
        return self.width / self.height


# ── Registry ────────────────────────────────────────────────────────────────

_FORMATS: dict[str, dict[str, PosterFormat]] = {
    "instagram": {
        "feed":  PosterFormat("instagram", "feed",   1080, 1080, "1:1",    sdxl_width=768,  sdxl_height=768),
        "story": PosterFormat("instagram", "story",  1080, 1920, "9:16",   sdxl_width=576,  sdxl_height=1024),
        "portrait": PosterFormat("instagram", "portrait", 1080, 1350, "4:5", sdxl_width=640, sdxl_height=800),
    },
    "facebook": {
        "feed":   PosterFormat("facebook", "feed",   1200,  630, "1.91:1", sdxl_width=1024, sdxl_height=540),
        "story":  PosterFormat("facebook", "story",  1080, 1920, "9:16",   sdxl_width=576,  sdxl_height=1024),
        "square": PosterFormat("facebook", "square", 1080, 1080, "1:1",    sdxl_width=768,  sdxl_height=768),
    },
    "linkedin": {
        "feed":   PosterFormat("linkedin", "feed",   1200,  627, "1.91:1", sdxl_width=1024, sdxl_height=536),
        "square": PosterFormat("linkedin", "square", 1080, 1080, "1:1",    sdxl_width=768,  sdxl_height=768),
    },
    "twitter": {
        "feed":   PosterFormat("twitter", "feed",   1600,  900, "16:9",   sdxl_width=1024, sdxl_height=576),
        "square": PosterFormat("twitter", "square", 1080, 1080, "1:1",    sdxl_width=768,  sdxl_height=768),
    },
}

# Default fallback
_DEFAULT_FORMAT = PosterFormat("all", "square", 1080, 1080, "1:1", sdxl_width=768, sdxl_height=768)


def get_format(platform: str, content_type: str = "feed") -> PosterFormat:
    """
    Return the PosterFormat for the given platform + content_type.
    Falls back to the default (Instagram square feed) if unknown.
    """
    platform = (platform or "instagram").lower().strip()
    content_type = (content_type or "feed").lower().strip()
    
    plat_formats = _FORMATS.get(platform, {})
    fmt = plat_formats.get(content_type) or plat_formats.get("feed")
    return fmt or _DEFAULT_FORMAT


def all_platforms() -> list[str]:
    return list(_FORMATS.keys())


def formats_for_platform(platform: str) -> list[PosterFormat]:
    return list(_FORMATS.get(platform.lower(), {}).values())
