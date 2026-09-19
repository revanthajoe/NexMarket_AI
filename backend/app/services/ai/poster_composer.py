"""
app/services/ai/poster_composer.py
─────────────────────────────────────────────────────────────────────────────
Enhanced Poster Composition Engine

Capabilities:
  • Responsive text layout  — word-wrap + auto font-size shrink
  • Complex-script text     — all text goes through text_shaper (HarfBuzz), so
                              Tamil and other complex scripts render correctly
  • Dynamic brand assets    — real logo (PNG/transparent), custom TTF fonts
  • Multi-platform aspect   — uses PosterFormat to resize / crop canvas
  • Brand colour theming    — CTA button uses brand_color_hex if provided
  • Product image inlay     — composites a product cutout
  • Gradient overlays       — proportional to canvas size

Text rendering priority:
  1. Brand name (top-left, small)
  2. Campaign headline (above offer, auto-wrap)
  3. Offer (large, gold, auto-wrap)
  4. CTA button (bottom-center, coloured pill)

All text is rasterized by `text_shaper.render_text` rather than PIL's
`ImageDraw.text`. PIL cannot shape complex scripts on this build (no libraqm),
which made Tamil render with mis-ordered vowel signs. See text_shaper.py.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

from app.services.ai import text_shaper

logger = logging.getLogger(__name__)

# rembg calls sys.exit(1) (raising SystemExit, a BaseException) when its
# onnxruntime backend is missing, instead of raising ImportError. Probe once
# at import time so _paste_product can skip the cutout without re-triggering
# that crash (and its stderr spam) on every single poster generation.
try:
    from rembg import remove as _rembg_remove
    _REMBG_AVAILABLE = True
except BaseException as exc:
    logger.warning("poster_composer rembg unavailable, product cutout disabled: %s", exc)
    _rembg_remove = None
    _REMBG_AVAILABLE = False


def _hex_to_rgba(hex_color: Optional[str], default=(220, 38, 38, 255)) -> tuple:
    """Convert '#RRGGBB' to RGBA tuple."""
    if not hex_color:
        return default
    h = hex_color.lstrip("#")
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (r, g, b, 255)
    except Exception:
        return default


def render_cta_pill(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    cta_text: str,
    font_path: str,
    center_x: int,
    pill_bottom_y: int,
    height_ref: int,
    width_ref: int,
    fill: tuple,
) -> int:
    """
    Draw the rounded-rectangle CTA button, horizontally centered on `center_x`
    with its bottom edge (including padding) at `pill_bottom_y`. Shared by
    PosterComposer and BrochureComposer so both render identical CTA styling.

    `height_ref`/`width_ref` are the dimensions the button's proportions scale
    from — normally the canvas H/W, but a composer may pass a zone's own
    height when the button lives inside a sub-band rather than the full canvas.

    Returns the button's total rendered height (including padding), so callers
    can reserve space above it.
    """
    cta_upper = cta_text.upper()
    cta_size  = int(height_ref * 0.036)
    cta_img   = text_shaper.render_text(cta_upper, font_path, cta_size, (255, 255, 255, 255))
    cta_w, cta_h = cta_img.width, cta_img.height

    bpx, bpy = int(width_ref * 0.045), int(height_ref * 0.012)
    cta_x     = center_x - cta_w // 2
    pill_top  = pill_bottom_y - cta_h - 2 * bpy
    text_y    = pill_top + bpy

    draw.rounded_rectangle(
        [cta_x - bpx, pill_top, cta_x + cta_w + bpx, pill_bottom_y],
        radius=int(height_ref * 0.022),
        fill=fill,
    )
    canvas.alpha_composite(cta_img, (max(0, cta_x), max(0, text_y)))
    return pill_bottom_y - pill_top


class PosterComposer:

    def __init__(
        self,
        font_bold_path: Optional[str] = None,
        font_reg_path: Optional[str]  = None,
    ) -> None:
        # None is fine — _font_path() falls back to the vendored Noto faces.
        self.font_bold_path = font_bold_path
        self.font_reg_path  = font_reg_path

    # ── Font helpers ─────────────────────────────────────────────────────────

    def _font_path(self, text: str, bold: bool = False) -> str:
        """
        Resolve the font to use for `text`.

        A custom uploaded font wins for Latin, but Tamil always routes to the
        vendored Tamil face — an uploaded Latin-only TTF would render Tamil as
        tofu, which is exactly the bug this replaced.
        """
        if text_shaper.has_tamil(text):
            return text_shaper.font_for_text(text, bold=bold)
        custom = self.font_bold_path if bold else self.font_reg_path
        return custom or text_shaper.font_for_text(text, bold=bold)

    # ── Text helpers ─────────────────────────────────────────────────────────

    def _wrap_text(self, text: str, font_path: str, size: int, max_width: int) -> list[str]:
        words = text.split()
        if not words:
            return []
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            test = f"{current} {word}"
            if text_shaper.measure_text(test, font_path, size)[0] <= max_width:
                current = test
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _draw_text_block(
        self,
        canvas: Image.Image,
        text: str,
        center_x: int,
        anchor_y: int,           # bottom anchor when draw_up=True, top when False
        max_width: int,
        max_height: int,
        font_bold: bool,
        initial_size: int,
        fill: tuple,
        draw_up: bool = True,    # draw upward from anchor_y
        shadow: bool = True,
    ) -> int:
        """Draw a responsive, shaped text block. Returns the total height rendered."""
        if not text:
            return 0

        font_path = self._font_path(text, bold=font_bold)

        # Shrink until the wrapped block fits within max_height.
        size = initial_size
        while size > 10:
            lines    = self._wrap_text(text, font_path, size, max_width)
            line_h   = text_shaper.measure_text("Ag", font_path, size)[1]
            line_gap = max(3, size // 8)
            if len(lines) * (line_h + line_gap) <= max_height:
                break
            size = max(10, size - 2)

        lines    = self._wrap_text(text, font_path, size, max_width)
        line_h   = text_shaper.measure_text("Ag", font_path, size)[1]
        line_gap = max(3, size // 8)
        total_h  = len(lines) * (line_h + line_gap)

        current_y = (anchor_y - total_h) if draw_up else anchor_y

        for ln in lines:
            img = text_shaper.render_text(ln, font_path, size, fill)
            x   = center_x - img.width // 2
            if shadow:
                shadow_img = text_shaper.render_text(ln, font_path, size, (0, 0, 0, 160))
                canvas.alpha_composite(shadow_img, (max(0, x + 2), max(0, current_y + 2)))
            canvas.alpha_composite(img, (max(0, x), max(0, current_y)))
            current_y += line_h + line_gap

        return total_h

    # ── Logo helper ──────────────────────────────────────────────────────────

    def _paste_logo(self, canvas: Image.Image, logo_path: str, margin: int) -> None:
        """Paste the brand logo (with transparency) into the top-left corner."""
        try:
            logo = Image.open(logo_path).convert("RGBA")
            # Scale logo so its height is ~8% of canvas height, preserving aspect
            max_h = max(40, int(canvas.height * 0.08))
            scale = max_h / logo.height
            new_w = max(1, int(logo.width * scale))
            logo = logo.resize((new_w, max_h), Image.LANCZOS)
            canvas.alpha_composite(logo, (margin, margin))
            logger.debug("poster_composer logo pasted from %s", logo_path)
        except Exception as exc:
            logger.warning("poster_composer logo paste failed: %s", exc)

    # ── Product inlay helper ─────────────────────────────────────────────────

    def _paste_product(
        self,
        canvas: Image.Image,
        product_path: str,
        canvas_w: int,
        canvas_h: int,
        already_transparent: bool = False,
    ) -> None:
        """
        Composite the product image into the right-center of the poster.

        `already_transparent` is the brand kit's pre-cut PNG path — it skips
        rembg entirely, which is the only way this works here (rembg needs
        onnxruntime, absent, plus numpy>=2.3 which conflicts with torch 2.1.2).
        """
        if not already_transparent and not _REMBG_AVAILABLE:
            logger.debug("poster_composer product cutout skipped - rembg unavailable")
            return

        try:
            raw = Image.open(product_path).convert("RGBA")
            cutout = raw if already_transparent else _rembg_remove(raw)

            # Fit into right 40% of canvas, max 55% height
            max_h = int(canvas_h * 0.55)
            scale = max_h / cutout.height
            new_w = int(cutout.width * scale)
            cutout = cutout.resize((new_w, max_h), Image.LANCZOS)

            paste_x = canvas_w - new_w - int(canvas_w * 0.04)
            paste_y = (canvas_h - max_h) // 2
            canvas.alpha_composite(cutout, (paste_x, paste_y))
            logger.debug("poster_composer product cutout pasted")
        except BaseException as exc:
            logger.warning("poster_composer product paste failed: %s", exc)

    # ── Gradient helpers ─────────────────────────────────────────────────────

    def _add_gradient(
        self,
        canvas: Image.Image,
        position: str,      # "bottom" | "top"
        height_pct: float,
        max_alpha: int,
    ) -> None:
        W, H = canvas.size
        gh = int(H * height_pct)
        grad = Image.new("RGBA", (W, gh), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grad)
        for y in range(gh):
            if position == "bottom":
                a = int((y / gh) * max_alpha)
            else:
                a = int((1 - y / gh) * max_alpha)
            gd.line([(0, y), (W, y)], fill=(0, 0, 0, a))

        if position == "bottom":
            canvas.alpha_composite(grad, (0, H - gh))
        else:
            canvas.alpha_composite(grad, (0, 0))

    # ── Main compose ─────────────────────────────────────────────────────────

    def compose(
        self,
        base_image_path: str,
        brand_name: str,
        campaign_name: str,
        offer: str,
        cta: str,
        output_path: str,
        # Brand kit extras (all optional)
        logo_path: Optional[str] = None,
        product_image_path: Optional[str] = None,
        product_cutout_path: Optional[str] = None,
        target_width: int = 1080,
        target_height: int = 1080,
        brand_color_hex: Optional[str] = None,
    ) -> str:
        try:
            with Image.open(base_image_path) as raw:
                img = raw.convert("RGBA")

            # Resize to target platform dimensions using cover crop
            img = self._cover_resize(img, target_width, target_height)
            W, H = img.size

            # Gradients
            self._add_gradient(img, "bottom", 0.50, 230)
            self._add_gradient(img, "top",    0.18, 160)

            # Product image — prefer the pre-cut transparent PNG when present
            if product_cutout_path:
                self._paste_product(img, product_cutout_path, W, H, already_transparent=True)
            elif product_image_path:
                self._paste_product(img, product_image_path, W, H)

            draw   = ImageDraw.Draw(img)
            margin = int(min(W, H) * 0.055)
            cx     = W // 2
            max_w  = W - (margin * 2)
            btn_color = _hex_to_rgba(brand_color_hex)

            # 1. Brand Logo or text (top-left)
            if logo_path:
                self._paste_logo(img, logo_path, margin)
            else:
                bf = self._font_path(brand_name, bold=True)
                brand_img = text_shaper.render_text(
                    brand_name.upper(), bf, int(H * 0.031), (255, 255, 255, 240)
                )
                img.alpha_composite(brand_img, (margin, margin))

            # 2. CTA button (bottom-center)
            cta_font   = self._font_path(cta, bold=True)
            cta_bottom = H - margin
            cta_rendered_h = render_cta_pill(
                img, draw, cta, cta_font, cx, cta_bottom, H, W, btn_color,
            )

            # 3. Offer (responsive, above CTA)
            offer_bottom = cta_bottom - cta_rendered_h - int(H * 0.025)
            offer_h = self._draw_text_block(
                img, offer.upper(), cx, offer_bottom,
                max_w, int(H * 0.20),
                font_bold=True, initial_size=int(H * 0.065),
                fill=(255, 215, 0, 255), draw_up=True,
            )

            # 4. Campaign headline (responsive, above offer)
            headline_bottom = offer_bottom - offer_h - int(H * 0.012)
            self._draw_text_block(
                img, campaign_name.upper(), cx, headline_bottom,
                max_w, int(H * 0.18),
                font_bold=True, initial_size=int(H * 0.042),
                fill=(255, 255, 255, 255), draw_up=True,
            )

            out = img.convert("RGB")
            out.save(output_path, format="PNG", optimize=True)
            logger.info("poster_composer composed %s (%dx%d)", output_path, W, H)
            return output_path

        except Exception as exc:
            logger.error("poster_composer.compose failed: %s", exc, exc_info=True)
            raise

    # ── Utility ──────────────────────────────────────────────────────────────

    @staticmethod
    def _cover_resize(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """Resize + center-crop to fill target dimensions (like CSS object-fit:cover)."""
        iw, ih = img.size
        scale = max(target_w / iw, target_h / ih)
        new_w, new_h = math.ceil(iw * scale), math.ceil(ih * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        top  = (new_h - target_h) // 2
        return img.crop((left, top, left + target_w, top + target_h))


poster_composer = PosterComposer()
