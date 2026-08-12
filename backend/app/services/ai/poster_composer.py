"""
app/services/ai/poster_composer.py
─────────────────────────────────────────────────────────────────────────────
Enhanced Poster Composition Engine

Capabilities:
  • Responsive text layout  — word-wrap + auto font-size shrink
  • Dynamic brand assets    — real logo (PNG/transparent), custom TTF fonts
  • Multi-platform aspect   — uses PosterFormat to resize / crop canvas
  • Brand colour theming    — CTA button uses brand_color_hex if provided
  • Product image inlay     — optionally composites a product cutout (rembg)
  • Multilingual text       — whatever the caller passes, Pillow renders it
  • Gradient overlays       — proportional to canvas size

Text rendering priority:
  1. Brand name (top-left, small)
  2. Campaign headline (above offer, auto-wrap)
  3. Offer (large, gold, auto-wrap)
  4. CTA button (bottom-center, coloured pill)
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ─── Fallback system fonts (Windows) ────────────────────────────────────────
_SYS_BOLD  = r"C:\Windows\Fonts\arialbd.ttf"
_SYS_REG   = r"C:\Windows\Fonts\arial.ttf"


def _try_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


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


class PosterComposer:

    def __init__(
        self,
        font_bold_path: str = _SYS_BOLD,
        font_reg_path: str  = _SYS_REG,
    ) -> None:
        self.font_bold_path = font_bold_path
        self.font_reg_path  = font_reg_path

    # ── Font helpers ─────────────────────────────────────────────────────────

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        path = self.font_bold_path if bold else self.font_reg_path
        return _try_font(path, max(size, 8))

    # ── Text helpers ─────────────────────────────────────────────────────────

    def _wrap_text(self, draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
        words = text.split()
        if not words:
            return []
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            test = f"{current} {word}"
            bb = draw.textbbox((0, 0), test, font=font)
            if (bb[2] - bb[0]) <= max_width:
                current = test
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _text_block_height(self, draw, lines: list[str], font, line_gap: int = 4) -> int:
        total = 0
        for line in lines:
            bb = draw.textbbox((0, 0), line, font=font)
            total += (bb[3] - bb[1]) + line_gap
        return total

    def _draw_text_block(
        self,
        draw: ImageDraw.ImageDraw,
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
        """Draw responsive text block. Returns the total height rendered."""
        size = initial_size
        font = self._get_font(size, bold=font_bold)

        # Shrink font until block fits in max_height
        while size > 10:
            lines = self._wrap_text(draw, text, font, max_width)
            h = self._text_block_height(draw, lines, font)
            if h <= max_height:
                break
            size = max(10, size - 2)
            font = self._get_font(size, bold=font_bold)

        lines = self._wrap_text(draw, text, font, max_width)
        line_gap = max(3, size // 8)

        total_h = 0
        line_sizes: list[int] = []
        for ln in lines:
            bb = draw.textbbox((0, 0), ln, font=font)
            lh = bb[3] - bb[1]
            line_sizes.append(lh)
            total_h += lh + line_gap

        current_y = (anchor_y - total_h) if draw_up else anchor_y

        for ln, lh in zip(lines, line_sizes):
            bb = draw.textbbox((0, 0), ln, font=font)
            w = bb[2] - bb[0]
            x = center_x - w // 2
            if shadow:
                draw.text((x + 2, current_y + 2), ln, font=font, fill=(0, 0, 0, 160))
            draw.text((x, current_y), ln, font=font, fill=fill)
            current_y += lh + line_gap

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
    ) -> None:
        """
        Remove background from product image and composite it into the
        right-center of the poster for a product-focus layout.
        """
        try:
            from rembg import remove
            raw = Image.open(product_path).convert("RGBA")
            cutout = remove(raw)
            # Fit into right 40% of canvas, max 55% height
            max_h = int(canvas_h * 0.55)
            scale = max_h / cutout.height
            new_w = int(cutout.width * scale)
            cutout = cutout.resize((new_w, max_h), Image.LANCZOS)

            paste_x = canvas_w - new_w - int(canvas_w * 0.04)
            paste_y = (canvas_h - max_h) // 2
            canvas.alpha_composite(cutout, (paste_x, paste_y))
            logger.debug("poster_composer product cutout pasted")
        except Exception as exc:
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

            # Optional: product image composited on right side
            if product_image_path:
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
                brand_font = self._get_font(int(H * 0.031), bold=True)
                draw.text((margin, margin), brand_name.upper(), font=brand_font, fill=(255, 255, 255, 240))

            # 2. CTA button (bottom-center)
            cta_size = int(H * 0.036)
            cta_font = self._get_font(cta_size, bold=True)
            cta_text = cta.upper()
            bb = draw.textbbox((0, 0), cta_text, font=cta_font)
            cta_w, cta_h = bb[2] - bb[0], bb[3] - bb[1]
            cta_x  = cx - cta_w // 2
            cta_y  = H - margin - cta_h - int(H * 0.018)
            bpx, bpy = int(W * 0.045), int(H * 0.018)
            draw.rounded_rectangle(
                [cta_x - bpx, cta_y - bpy, cta_x + cta_w + bpx, cta_y + cta_h + bpy],
                radius=int(H * 0.022),
                fill=btn_color,
            )
            draw.text((cta_x, cta_y), cta_text, font=cta_font, fill=(255, 255, 255, 255))

            # 3. Offer (responsive, above CTA)
            offer_bottom = cta_y - bpy - int(H * 0.025)
            offer_h = self._draw_text_block(
                draw, offer.upper(), cx, offer_bottom,
                max_w, int(H * 0.20),
                font_bold=True, initial_size=int(H * 0.065),
                fill=(255, 215, 0, 255), draw_up=True,
            )

            # 4. Campaign headline (responsive, above offer)
            headline_bottom = offer_bottom - offer_h - int(H * 0.012)
            self._draw_text_block(
                draw, campaign_name.upper(), cx, headline_bottom,
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
