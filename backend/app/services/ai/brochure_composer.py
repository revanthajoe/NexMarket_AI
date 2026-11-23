"""
app/services/ai/brochure_composer.py
─────────────────────────────────────────────────────────────────────────────
Zone-based brochure layout engine.

Why this exists — the reference brochure the user rejected the plain poster
against is ~8 layout zones and roughly 85% deterministic typesetting over real
photographic assets (a real product photo, real logos, a real map). SDXL
cannot draw legible packaging, logos, or maps — it can only supply decorative
background art (~15% of the reference). `PosterComposer` asked SDXL to carry
the whole visual; this composer inverts that: SDXL becomes a decorative
backdrop behind six fixed zones, each independently laid out and each
degrading gracefully when its optional asset is missing.

Zone budget — *weights*, not fixed fractions:

    header    9   brand logo (+ partner logo when supplied) on a white strip
    headline 12   bilingual headline pair
    hero     38   product cutout / product photo / backdrop + 4 feature badges
    spec     14   "why us" bilingual bullet strip
    offer    10   offer line + CTA pill
    footer   17   phone / bilingual address / website / map thumbnail

Only the zones that have something to show are laid out, and the remaining
height is redistributed proportionally among them — a campaign with no contact
details gets that 17% folded back into hero and offer rather than rendering an
empty strip. This is what lets the same engine serve both layout tiers
(`BrandKit.pick_layout()`) instead of the all-or-nothing gate that used to keep
it from running at all.

Reuses `_hex_to_rgba`, `_cover_resize`, `_add_gradient`, and `render_cta_pill`
from `poster_composer` rather than reimplementing them, and routes all text
through `text_shaper` exactly as `PosterComposer` already does — Tamil must
render correctly here for the same reason it must there.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from dataclasses import dataclass
from PIL import Image, ImageDraw

from app.services.ai import text_shaper
from app.services.ai.icon_library import draw_icon, pick_icon
from app.services.ai.poster_composer import _hex_to_rgba, render_cta_pill

@dataclass
class PosterCreativeSpec:
    campaign_objective: str
    product_name: str
    target_audience: str

    brand_name: str
    headline: str
    subheadline: str
    supporting_message: str
    offer: str
    cta: str

    visual_subject: str
    visual_style: str
    composition_strategy: str

    color_direction: str
    platform: str
    aspect_ratio: str
    variation_index: int

    # Brand Kit colour for the CTA pill / split panel; empty keeps the default.
    # Separate field because `color_direction` is prose art direction, not a hex.
    brand_color_hex: str = ""

logger = logging.getLogger(__name__)

# ── Zone weights ─────────────────────────────────────────────────────────────
# Relative, not absolute: absent zones drop out and the rest scale up to fill
# the canvas, so the layout never leaves a hole where a zone used to be.
_ZONE_WEIGHTS: dict[str, float] = {
    "header":   0.09,
    "headline": 0.12,
    "hero":     0.38,
    "spec":     0.14,
    "offer":    0.10,
    "footer":   0.17,
}

# Order is layout order, top to bottom.
_ZONE_ORDER = ("header", "headline", "hero", "spec", "offer", "footer")


def _zone_boxes(width: int, height: int, present: set[str]) -> dict[str, tuple[int, int, int, int]]:
    """
    Lay the present zones out top-to-bottom, scaling their weights to fill the
    full canvas height. The last present zone absorbs any rounding remainder so
    the boxes always tile the canvas exactly.
    """
    ordered = [z for z in _ZONE_ORDER if z in present]
    if not ordered:
        raise ValueError("at least one zone must be present")

    total = sum(_ZONE_WEIGHTS[z] for z in ordered)
    boxes: dict[str, tuple[int, int, int, int]] = {}
    y = 0
    for i, name in enumerate(ordered):
        last = i == len(ordered) - 1
        y1 = height if last else y + int(height * (_ZONE_WEIGHTS[name] / total))
        boxes[name] = (0, y, width, y1)
        y = y1
    return boxes

_HEADER_BG  = (255, 255, 255, 255)
_FOOTER_BG  = (25, 28, 38, 255)
_INK_DARK   = (20, 22, 30, 255)
_INK_LIGHT  = (255, 255, 255, 255)
_INK_MUTED  = (210, 214, 224, 255)


class BrochureComposer:

    def __init__(
        self,
        font_bold_path: Optional[str] = None,
        font_reg_path: Optional[str]  = None,
    ) -> None:
        # None is fine — _font_path() falls back to the vendored Noto faces,
        # same convention as PosterComposer.
        self.font_bold_path = font_bold_path
        self.font_reg_path  = font_reg_path

    # ── Font helper (identical policy to PosterComposer) ────────────────────

    def _font_path(self, text: str, bold: bool = False) -> str:
        if text_shaper.has_tamil(text):
            return text_shaper.font_for_text(text, bold=bold)
        custom = self.font_bold_path if bold else self.font_reg_path
        return custom or text_shaper.font_for_text(text, bold=bold)

    # ── Shared text helpers ──────────────────────────────────────────────────

    def _wrap(self, text: str, font_path: str, size: int, max_width: int) -> list[str]:
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

    def _draw_centered(
        self,
        canvas: Image.Image,
        text: str,
        center_x: int,
        top_y: int,
        max_width: int,
        size: int,
        color: tuple,
        bold: bool = True,
    ) -> int:
        """Draw one (possibly wrapped) centered text block. Returns rendered height."""
        if not text:
            return 0
        font_path = self._font_path(text, bold=bold)
        lines = self._wrap(text, font_path, size, max_width)
        line_h = text_shaper.measure_text("Ag", font_path, size)[1]
        gap = max(2, size // 8)
        y = top_y
        for ln in lines:
            img = text_shaper.render_text(ln, font_path, size, color)
            x = center_x - img.width // 2
            canvas.alpha_composite(img, (max(0, x), max(0, y)))
            y += line_h + gap
        return y - top_y

    def _block_height(self, text: str, font_path: str, size: int, max_width: int) -> int:
        """Height the wrapped block will occupy at `size`."""
        lines  = self._wrap(text, font_path, size, max_width)
        line_h = text_shaper.measure_text("Ag", font_path, size)[1]
        gap    = max(2, size // 8)
        return len(lines) * (line_h + gap)

    def _draw_fitted(
        self,
        canvas: Image.Image,
        text: str,
        center_x: int,
        top_y: int,
        max_width: int,
        max_height: int,
        start_size: int,
        color: tuple,
        bold: bool = True,
        floor: int = 9,
    ) -> int:
        """
        Draw a centered block guaranteed to fit inside (max_width, max_height).

        `_draw_centered` alone wraps to however many lines it needs and happily
        runs past the zone: the "why us" strip spilled its fourth item into the
        offer band, and the bilingual offer line was clipped by the canvas edge.
        Shrinking until the wrapped block fits keeps every zone inside its box.
        """
        if not text or max_height <= 0:
            return 0
        font_path = self._font_path(text, bold=bold)
        size = max(floor, start_size)
        while size > floor and self._block_height(text, font_path, size, max_width) > max_height:
            size -= 1
        return self._draw_centered(canvas, text, center_x, top_y, max_width, size, color, bold=bold)

    @staticmethod
    def _rounded_card(img: Image.Image, radius: int) -> Image.Image:
        """
        Round an opaque image's corners.

        Only used for an ordinary (non-cut-out) product photo: a hard rectangle
        dropped into the hero zone reads as a pasting accident, whereas rounded
        corners read as a deliberate card.
        """
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.width - 1, img.height - 1],
                                               radius=max(1, radius), fill=255)
        out = img.copy()
        out.putalpha(mask)
        return out

    def _fit_size(self, text: str, font_path: str, max_width: int, start: int, floor: int = 10) -> int:
        """Shrink `start` until `text` (single line) fits `max_width`."""
        size = start
        while size > floor and text_shaper.measure_text(text, font_path, size)[0] > max_width:
            size -= 2
        return size

    # ── Zone: header ──────────────────────────────────────────────────────────

    def _zone_header(
        self, canvas: Image.Image, draw: ImageDraw.ImageDraw, box, kit, brand_name: str = ""
    ) -> None:
        x0, y0, x1, y1 = box
        draw.rectangle([x0, y0, x1, y1], fill=_HEADER_BG)
        margin = int((y1 - y0) * 0.18)
        logo_h = int((y1 - y0) * 0.64)

        def _paste_logo(path: str, right_aligned: bool) -> None:
            try:
                logo = Image.open(path).convert("RGBA")
                scale = logo_h / logo.height
                w = max(1, int(logo.width * scale))
                logo = logo.resize((w, logo_h), Image.LANCZOS)
                lx = (x1 - margin - w) if right_aligned else (x0 + margin)
                ly = y0 + ((y1 - y0) - logo_h) // 2
                canvas.alpha_composite(logo, (lx, ly))
            except Exception as exc:
                logger.warning("brochure_composer header logo failed path=%s error=%s", path, exc)

        has_logo    = bool(getattr(kit, "logo_path", None))
        has_partner = bool(getattr(kit, "partner_logo_path", None))

        if has_logo and has_partner:
            _paste_logo(kit.logo_path, right_aligned=False)
            _paste_logo(kit.partner_logo_path, right_aligned=True)
        elif has_logo:
            # No partner logo: center the single logo rather than leaving the
            # right side looking like a mistake.
            try:
                logo = Image.open(kit.logo_path).convert("RGBA")
                scale = logo_h / logo.height
                w = max(1, int(logo.width * scale))
                logo = logo.resize((w, logo_h), Image.LANCZOS)
                lx = (x0 + x1) // 2 - w // 2
                ly = y0 + ((y1 - y0) - logo_h) // 2
                canvas.alpha_composite(logo, (lx, ly))
            except Exception as exc:
                logger.warning("brochure_composer header logo failed: %s", exc)
        elif has_partner:
            # A partner/product logo is still valuable when the campaign has
            # no separate retailer logo; do not silently discard it.
            _paste_logo(kit.partner_logo_path, right_aligned=False)
        elif brand_name:
            # No logo uploaded at all — typeset the brand name instead of
            # leaving a blank white band. Most campaigns are in this state, so
            # this is the common path, not an edge case.
            font_path = self._font_path(brand_name, bold=True)
            max_w = (x1 - x0) - 2 * margin
            size  = self._fit_size(
                brand_name.upper(), font_path, max_w, int((y1 - y0) * 0.46)
            )
            text_img = text_shaper.render_text(brand_name.upper(), font_path, size, _INK_DARK)
            canvas.alpha_composite(
                text_img,
                ((x0 + x1) // 2 - text_img.width // 2,
                 y0 + ((y1 - y0) - text_img.height) // 2),
            )

    # ── Zone: headline ────────────────────────────────────────────────────────

    def _zone_headline(self, canvas: Image.Image, box, spec: dict, margin_x: int) -> int:
        x0, y0, x1, y1 = box
        cx = (x0 + x1) // 2
        max_w = (x1 - x0) - 2 * margin_x
        zone_h = y1 - y0

        preferred = spec.get("headline_en", "")
        if spec.get("language") != "en":
            preferred = spec.get("headline_local") or preferred
        y = y0 + int(zone_h * 0.06)
        # Each line is held to its share of the zone. The headline sits directly
        # above the hero, so an unbounded wrap here pushes into the badges.
        y += self._draw_fitted(
            canvas, preferred.upper(), cx, y, max_w,
            int(zone_h * 0.88), int(zone_h * 0.30), _INK_LIGHT,
        )

        return y - y0

    # ── Zone: hero (product + feature badges) ───────────────────────────────

    def _zone_hero(self, canvas: Image.Image, box, kit, spec: dict) -> None:
        x0, y0, x1, y1 = box
        W, H = x1 - x0, y1 - y0
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2

        # Hero subject, centered, capped to the middle third so it never
        # overlaps the badges. Three degrading sources: the pre-cut transparent
        # PNG is ideal, an ordinary uploaded product photo is acceptable (shown
        # in a rounded card so its rectangular edges read as deliberate), and
        # with neither the SDXL backdrop simply shows through between the
        # badges. Never blank, never a crash.
        hero_path = (
            getattr(kit, "product_cutout_path", None)
            or getattr(kit, "product_image_path", None)
        )
        is_cutout = bool(getattr(kit, "product_cutout_path", None))

        if hero_path:
            try:
                hero = Image.open(hero_path).convert("RGBA")
                max_h = int(H * 0.92)
                max_w = int(W * 0.34)
                scale = min(max_h / hero.height, max_w / hero.width)
                new_w, new_h = max(1, int(hero.width * scale)), max(1, int(hero.height * scale))
                hero = hero.resize((new_w, new_h), Image.LANCZOS)
                if not is_cutout:
                    hero = self._rounded_card(hero, radius=int(min(new_w, new_h) * 0.08))
                canvas.alpha_composite(hero, (cx - new_w // 2, cy - new_h // 2))
            except Exception as exc:
                logger.warning("brochure_composer hero image paste failed: %s", exc)

        if not spec.get("show_supporting_features", False):
            return

        # Feature badges: 2 left, 2 right, each a filled circle with bilingual
        # label above a value string — mirrors the reference's "14 YEAR" /
        # "12°C COOLER" pairing.
        features = spec.get("features", [])[:4]
        if not features:
            return

        accent = _hex_to_rgba(spec.get("brand_color_hex"), default=(214, 40, 40, 255))

        if hero_path:
            # Flank the product: two badges left, two right, centre reserved.
            # Diameter is smaller than before (0.22 vs the old 0.30) because
            # the caption now sits BELOW the circle rather than inside it, so
            # each badge needs more total vertical footprint than a bare
            # circle did.
            diameter = int(min(W, H) * 0.22)
            left_x   = x0 + int(W * 0.16)
            right_x  = x1 - int(W * 0.16)
            slot_ys  = [y0 + int(H * 0.22), y0 + int(H * 0.74)]
            for i, feat in enumerate(features):
                self._draw_badge(canvas, left_x if i < 2 else right_x,
                                 slot_ys[i % 2], diameter, feat, accent)
        else:
            # No product to flank. Keeping the flanking positions would leave a
            # large dead void down the middle, which reads as a missing image
            # rather than a design. Spread the badges into a balanced 2x2 that
            # owns the zone, and size them up to fill it. Smaller than before
            # for the same caption-below-circle reason as the flanking case.
            diameter = int(min(W, H) * 0.26)
            col_xs   = [x0 + int(W * 0.28), x1 - int(W * 0.28)]
            row_ys   = [y0 + int(H * 0.26), y0 + int(H * 0.74)]
            for i, feat in enumerate(features):
                self._draw_badge(canvas, col_xs[i % 2], row_ys[i // 2],
                                 diameter, feat, accent)

    def _draw_badge(self, canvas: Image.Image, cx: int, cy: int, diameter: int, feat: dict, accent: tuple) -> None:
        """
        Icon-circle-then-caption, matching the reference layout: a solid
        accent-colored circle holding a single icon (picked by keyword from
        the English label, so this works for any product category — see
        icon_library.py), with the value + label typeset as a caption block
        underneath rather than crammed as text inside the circle.

        `cy` is the circle's center; the caption is drawn below it, so callers
        positioning badges (_zone_hero) must leave room under `cy + r` for the
        caption before the next row starts.
        """
        r = diameter // 2
        draw = ImageDraw.Draw(canvas)
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=accent, outline=(255, 255, 255, 230), width=max(2, diameter // 30),
        )

        label_en    = feat.get("label_en", "")
        label_local = feat.get("label_local", "")
        value       = feat.get("value", "")

        # Match against label + value together: "Extra Paint" / "10% FREE" only
        # carries its "free" (-> tag icon) claim in the value field, so
        # label_en alone would miss it and fall through to the star default.
        draw_icon(draw, pick_icon(f"{label_en} {value}"), cx, cy, int(diameter * 0.52), (255, 255, 255, 255))

        # "14 YEAR" + "Warranty" -> "14 YEAR WARRANTY" as one bold caption line,
        # the local-language label below it — mirrors the reference's
        # value+label-combined-then-translation pattern.
        primary = " ".join(p for p in (value.upper(), label_en.upper()) if p).strip()
        caption_w = max(1, int(diameter * 1.15))
        gap = max(3, diameter // 24)
        y = cy + r + gap

        if primary:
            size = self._fit_size(primary, self._font_path(primary, bold=True), caption_w, int(diameter * 0.19))
            img = text_shaper.render_text(primary, self._font_path(primary, bold=True), size, _INK_LIGHT)
            canvas.alpha_composite(img, (cx - img.width // 2, y))
            y += img.height + max(1, gap // 2)

        if label_local and label_local != label_en:
            size = self._fit_size(label_local, self._font_path(label_local, bold=False), caption_w, int(diameter * 0.15))
            img = text_shaper.render_text(label_local, self._font_path(label_local, bold=False), size, _INK_MUTED)
            canvas.alpha_composite(img, (cx - img.width // 2, y))

    # ── Zone: spec strip ("why us") ──────────────────────────────────────────

    def _zone_spec(self, canvas: Image.Image, draw: ImageDraw.ImageDraw, box, spec: dict, margin_x: int) -> None:
        x0, y0, x1, y1 = box
        cx = (x0 + x1) // 2
        max_w = (x1 - x0) - 2 * margin_x
        zone_h = y1 - y0

        draw.rectangle([x0, y0, x1, y1], fill=(0, 0, 0, 140))

        title = spec.get("why_title_en", "")
        if spec.get("language") != "en":
            title = spec.get("why_title_local") or title
        y = y0 + int(zone_h * 0.08)
        # Title gets at most a third of the zone; the items need the rest.
        y += self._draw_fitted(canvas, title, cx, y, max_w, int(zone_h * 0.34),
                               int(zone_h * 0.24), (255, 215, 0, 255))

        items_en    = spec.get("why_items_en", [])
        items_local = spec.get("why_items_local", [])
        pairs = [
            (en, loc) for en, loc in zip(items_en, items_local)
        ] or [(t, t) for t in items_en]

        if pairs:
            line = "   |   ".join(
                (loc if loc and loc != en else en) if spec.get("language") != "en" else en
                for en, loc in pairs
            )
            y += int(zone_h * 0.04)
            self._draw_fitted(canvas, line, cx, y, max_w, max(1, y1 - y - int(zone_h * 0.06)),
                              int(zone_h * 0.16), _INK_LIGHT, bold=False)

    # ── Zone: offer + CTA ────────────────────────────────────────────────────

    def _zone_offer(self, canvas: Image.Image, draw: ImageDraw.ImageDraw, box, spec: dict, cta: str, margin_x: int) -> None:
        x0, y0, x1, y1 = box
        cx = (x0 + x1) // 2
        max_w = (x1 - x0) - 2 * margin_x
        zone_h = y1 - y0
        accent = _hex_to_rgba(spec.get("brand_color_hex"))

        draw.rectangle([x0, y0, x1, y1], fill=accent)

        offer_en    = spec.get("offer_en", "")
        offer_local = spec.get("offer_local", "")
        preferred_offer = offer_local if spec.get("language") != "en" and offer_local else offer_en
        cta_font    = self._font_path(cta, bold=True)
        # render_cta_pill sizes text as a fraction of `height_ref` — that must
        # be the full canvas height, not this zone's height (~10% of canvas),
        # or the button shrinks to a few illegible pixels.
        canvas_h  = canvas.height
        zone_w    = x1 - x0
        cta_cx    = x1 - margin_x - int(zone_w * 0.14)
        cta_h = render_cta_pill(canvas, draw, cta, cta_font, cta_cx,
                                 y1 - int(zone_h * 0.14), canvas_h, zone_w, _INK_DARK)

        # Reserve the pill's actual footprint rather than a guessed fraction.
        # The pill is sized from the CTA string, so a long CTA (Tamil runs
        # longer than English) grew past a fixed 28% reservation and the offer
        # text was drawn underneath the button.
        cta_text_w = text_shaper.measure_text(cta.upper(), cta_font, int(canvas_h * 0.036))[0]
        pill_left  = cta_cx - cta_text_w // 2 - int(zone_w * 0.045)

        # Both languages, stacked — the offer is the single most persuasive
        # element on a sale poster, so dropping one language here (as an
        # `offer_local or offer_en` fallback would) silently costs half the
        # audience the actual deal. The headline zone already shows both.
        offer_max_w = max(int(zone_w * 0.25), pill_left - (x0 + margin_x) - int(zone_w * 0.03))
        offer_cx    = x0 + margin_x + offer_max_w // 2
        bilingual   = False

        # Split the zone's vertical budget between the two lines and hold each
        # to its share, so a long local offer cannot run off the canvas bottom.
        y = y0 + int(zone_h * (0.10 if bilingual else 0.22))
        en_budget = int(zone_h * (0.42 if bilingual else 0.60))
        if preferred_offer:
            y += self._draw_fitted(
                canvas, preferred_offer.upper(), offer_cx, y, offer_max_w, en_budget,
                int(zone_h * 0.30), (255, 255, 255, 255),
            )
        if bilingual:
            y += int(zone_h * 0.03)
            self._draw_fitted(
                canvas, offer_local, offer_cx, y, offer_max_w,
                max(1, y1 - y - int(zone_h * 0.06)),
                int(zone_h * 0.22), (255, 255, 255, 235),
            )

    # ── Zone: contact footer ─────────────────────────────────────────────────

    def _zone_footer(self, canvas: Image.Image, draw: ImageDraw.ImageDraw, box, kit, margin_x: int) -> None:
        x0, y0, x1, y1 = box
        zone_h = y1 - y0
        draw.rectangle([x0, y0, x1, y1], fill=_FOOTER_BG)

        has_map = bool(getattr(kit, "map_image_path", None))
        map_w = int((x1 - x0) * 0.22) if has_map else 0
        text_x0 = x0 + margin_x
        text_x1 = (x1 - map_w - margin_x) if has_map else (x1 - margin_x)

        lines = []
        if getattr(kit, "phone", None):
            lines.append(("phone", kit.phone))
        addr_local = getattr(kit, "address_ta", None)
        addr_en = getattr(kit, "address_en", None)
        if addr_en or addr_local:
            lines.append(("addr", addr_local or addr_en))
            if addr_local and addr_en and addr_local != addr_en:
                lines.append(("addr_en", addr_en))
        if getattr(kit, "website", None):
            lines.append(("web", kit.website))

        # Content is variable-length (address may or may not have a second
        # language line), so size against how many lines actually exist rather
        # than a fixed fraction - a fixed size overflowed the zone whenever all
        # four fields (phone, bilingual address, website) were present.
        n = max(1, len(lines))
        gap = int(zone_h * 0.03)
        size = min(int(zone_h * 0.16), int((zone_h - (n + 1) * gap) / n / 1.35))
        size = max(size, 10)

        y = y0 + gap
        for key, text in lines:
            font_path = self._font_path(text, bold=(key == "phone"))
            img = text_shaper.render_text(text, font_path, size, _INK_MUTED)
            # Truncate rather than let a single very long line still overflow
            # into the next zone after the size has already been minimized.
            max_line_w = text_x1 - text_x0
            if img.width > max_line_w:
                while text and text_shaper.measure_text(text + "…", font_path, size)[0] > max_line_w:
                    text = text[:-1]
                img = text_shaper.render_text(text + "…", font_path, size, _INK_MUTED)
            canvas.alpha_composite(img, (text_x0, y))
            y += img.height + gap

        if has_map:
            try:
                m = Image.open(kit.map_image_path).convert("RGBA")
                side = min(map_w, zone_h) - int(zone_h * 0.16)
                m = m.resize((side, side), Image.LANCZOS)
                canvas.alpha_composite(m, (x1 - margin_x - side, y0 + (zone_h - side) // 2))
            except Exception as exc:
                logger.warning("brochure_composer footer map paste failed: %s", exc)

    # ── Main compose ─────────────────────────────────────────────────────────

    def compose(self, *args, **kwargs) -> str:
        """Route to the legacy dict spec or the dynamic PosterCreativeSpec."""
        # Keyword args win; positionally it is (spec, base, kit, out). The old
        # `kwargs.get(k) or args[i]` raised IndexError for any falsy but valid
        # value (`kit=None`, a 0 dimension), because `or` then evaluated a
        # positional index a keyword call never supplied.
        spec = kwargs.get("spec", args[0] if args else None)
        if not isinstance(spec, PosterCreativeSpec):
            return self.compose_legacy(*args, **kwargs)

        return self.compose_dynamic(
            **dict(zip(("base_image_path", "kit", "output_path"), args[1:4]), **kwargs)
        )

    def compose_dynamic(
        self,
        spec: PosterCreativeSpec,
        base_image_path: str,
        kit,
        output_path: str,
        target_width: int = 1080,
        target_height: int = 1080,
    ) -> str:
        """Modern dynamic marketing composition engine."""
        try:
            W, H = target_width, target_height
            margin_x = int(W * 0.05)
            
            from app.services.ai.poster_composer import PosterComposer
            with Image.open(base_image_path) as raw:
                img = raw.convert("RGBA")
            img = PosterComposer._cover_resize(img, W, H)
            
            # Product Cutout Overlay
            if kit and kit.product_cutout_path:
                try:
                    with Image.open(kit.product_cutout_path) as raw_cutout:
                        cutout = raw_cutout.convert("RGBA")
                    # Scale cutout to ~60% of canvas
                    target_cutout_h = int(H * 0.6)
                    cutout_scale = target_cutout_h / cutout.height
                    new_cw, new_ch = int(cutout.width * cutout_scale), target_cutout_h
                    cutout = cutout.resize((new_cw, new_ch), Image.LANCZOS)
                    # Center the cutout
                    img.alpha_composite(cutout, ((W - new_cw) // 2, (H - new_ch) // 2))
                except Exception as exc:
                    logger.warning("Failed to paste product cutout: %s", exc)

            overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            # Brand Kit colour for the CTA pill and split panel; unset keeps the
            # composer's own defaults (red pill, dark panel).
            brand_rgba = _hex_to_rgba(spec.brand_color_hex) if spec.brand_color_hex else None

            # Gradient overlays for text contrast
            if spec.composition_strategy in ["offer_focused", "hero_focused", "minimal"]:
                grad_h = int(H * 0.45)
                grad_y = H - grad_h
                for row in range(grad_h):
                    alpha = int(230 * (row / grad_h))
                    draw.line([(0, grad_y + row), (W, grad_y + row)], fill=(10, 12, 18, alpha))
                
                # Top gradient for logo/brand
                top_grad_h = int(H * 0.15)
                for row in range(top_grad_h):
                    alpha = int(180 * (1.0 - (row / top_grad_h)))
                    draw.line([(0, row), (W, row)], fill=(10, 12, 18, alpha))
            
            elif spec.composition_strategy == "split_visual":
                split_h = int(H * 0.35)
                bg_color = brand_rgba[:3] + (240,) if brand_rgba else (25, 28, 38, 240)
                draw.rectangle([0, H - split_h, W, H], fill=bg_color)
            
            # Brand / Logo
            if kit and kit.logo_path:
                try:
                    with Image.open(kit.logo_path) as raw_logo:
                        logo = raw_logo.convert("RGBA")
                    logo_w = min(int(W * 0.25), 250)
                    logo_h = int(logo_w * logo.height / logo.width)
                    logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
                    overlay.alpha_composite(logo, (margin_x, margin_x))
                except Exception as e:
                    logger.warning("Failed to paste logo: %s", e)
            else:
                brand_font = self._font_path(spec.brand_name, bold=True)
                brand_img = text_shaper.render_text(spec.brand_name, brand_font, int(H * 0.035), (255, 255, 255, 255))
                overlay.alpha_composite(brand_img, (margin_x, margin_x))

            # Typography sizes
            hl_size = int(H * 0.08) if spec.composition_strategy == "offer_focused" else int(H * 0.065)
            offer_size = int(H * 0.045)

            # Draw Headline with wrapping
            hl_font = self._font_path(spec.headline, bold=True)
            hl_y = H - int(H * 0.38) if spec.composition_strategy != "split_visual" else H - int(H * 0.32)
            if spec.composition_strategy == "hero_focused":
                hl_y = int(H * 0.12)
                
            # Quick text wrap implementation
            words = spec.headline.upper().split()
            lines = []
            curr_line = ""
            for word in words:
                test_line = f"{curr_line} {word}".strip()
                if text_shaper.measure_text(test_line, hl_font, hl_size)[0] < (W - margin_x * 2):
                    curr_line = test_line
                else:
                    if curr_line: lines.append(curr_line)
                    curr_line = word
            if curr_line: lines.append(curr_line)
            
            current_y = hl_y
            for line in lines:
                line_img = text_shaper.render_text(line, hl_font, hl_size, (255, 255, 255, 255))
                overlay.alpha_composite(line_img, (margin_x, current_y))
                current_y += line_img.height + int(H * 0.01)
            
            # Draw Offer
            offer_font = self._font_path(spec.offer, bold=False)
            offer_y = current_y + int(H * 0.01)
            offer_img = text_shaper.render_text(spec.offer, offer_font, offer_size, (240, 240, 240, 255))
            overlay.alpha_composite(offer_img, (margin_x, offer_y))

            # Draw CTA Pill
            cta_y = offer_y + offer_img.height + int(H * 0.03)
            cta_font = self._font_path(spec.cta, bold=True)
            pill_color = brand_rgba or (220, 40, 40, 255)
            
            cta_text = spec.cta.upper()
            cta_text_size = int(H * 0.035)
            cta_text_w, cta_text_h = text_shaper.measure_text(cta_text, cta_font, cta_text_size)
            
            pill_h = int(cta_text_h * 2.5)
            pill_w = int(cta_text_w + pill_h * 1.5)
            draw.rounded_rectangle([margin_x, cta_y, margin_x + pill_w, cta_y + pill_h], radius=int(pill_h*0.5), fill=pill_color)
            
            cta_img = text_shaper.render_text(cta_text, cta_font, cta_text_size, (255, 255, 255, 255))
            overlay.alpha_composite(cta_img, (margin_x + (pill_w - cta_img.width)//2, cta_y + (pill_h - cta_img.height)//2))
            
            # Contact Footer
            if kit and kit.has_contact_details():
                footer_h = int(H * 0.08)
                footer_y = H - footer_h
                draw.rectangle([0, footer_y, W, H], fill=(20, 22, 28, 240))
                
                contact_parts = []
                if kit.phone: contact_parts.append(kit.phone)
                if kit.website: contact_parts.append(kit.website)
                if kit.address_en: contact_parts.append(kit.address_en)
                
                if contact_parts:
                    contact_text = " • ".join(contact_parts)
                    contact_font = self._font_path(contact_text, bold=False)
                    contact_size = int(footer_h * 0.35)
                    
                    # Truncate if too long
                    while contact_parts and text_shaper.measure_text(contact_text, contact_font, contact_size)[0] > (W - margin_x * 2):
                        contact_parts.pop()
                        contact_text = " • ".join(contact_parts)
                        
                    if contact_text:
                        contact_img = text_shaper.render_text(contact_text, contact_font, contact_size, (200, 200, 200, 255))
                        overlay.alpha_composite(
                            contact_img, 
                            ((W - contact_img.width) // 2, footer_y + (footer_h - contact_img.height) // 2)
                        )

            img.alpha_composite(overlay, (0, 0))
            
            out = img.convert("RGB")
            out.save(output_path, format="PNG", optimize=True)
            logger.info("brochure_composer composed DYNAMIC %s (%dx%d) layout=%s", output_path, W, H, spec.composition_strategy)
            return output_path
            
        except Exception as exc:
            logger.error("brochure_composer.compose_dynamic failed: %s", exc, exc_info=True)
            raise

    def compose_legacy(
        self,
        base_image_path: str,
        spec: dict,
        cta: str,
        kit,
        output_path: str,
        target_width: int = 1080,
        target_height: int = 1080,
        brand_name: str = "",
    ) -> str:
        """
        Compose the full brochure.

        `spec` is the normalized dict from `normalize_brochure_spec` (plus a
        `cta` key already attached by `generate_brochure_spec`, though `cta`
        is also accepted as an explicit argument for callers that resolve it
        separately). `kit` is a `BrandKit` — only optional assets are read,
        so a kit missing partner_logo/map_image degrades those zones rather
        than failing.

        `brand_name` is drawn in the header when no logo has been uploaded, so
        the header band is never blank on a campaign with no brand kit at all.

        The footer is laid out only when the kit actually carries contact
        details; without them its height is redistributed across the remaining
        zones instead of leaving an empty dark strip.

        `base_image_path` (the SDXL backdrop) is no longer the dominant
        visual: the headline+hero span is a deterministic color-blocked panel
        derived from `brand_color_hex`, with the backdrop blended in at low
        opacity purely as texture. A full-bleed "artsy" backdrop with only a
        light gradient over it (the previous approach) read as busy and
        competed with the badges/text — a clean panel reads as designed
        regardless of backdrop quality, which also matters while image
        generation is running on the SDXL background path.
        """
        try:
            W, H = target_width, target_height
            margin_x = int(W * 0.05)

            layout_type = spec.get("layout_type", "hero_offer")
            layout_zones = {
                "hero_offer": {"header", "headline", "hero", "offer"},
                "product_focus": {"header", "headline", "hero", "offer"},
                "split_visual": {"header", "headline", "hero", "offer"},
                "centered_product": {"header", "headline", "hero", "offer"},
                "lifestyle_scene": {"header", "headline", "hero", "offer"},
                "minimal_offer": {"header", "headline", "offer"},
            }
            present = set(layout_zones.get(layout_type, layout_zones["hero_offer"]))
            if kit is not None and getattr(kit, "has_contact_details", lambda: False)():
                present.add("footer")

            boxes = _zone_boxes(W, H, present)

            # White base: the header paints nothing extra behind its logo/text,
            # so it needs the canvas to already be white there. Every other
            # zone (panel, spec, offer, footer) paints its own opaque
            # background over this, so the white only ever shows through
            # inside the header band.
            img = Image.new("RGBA", (W, H), (255, 255, 255, 255))
            draw = ImageDraw.Draw(img)

            panel_top = boxes["headline"][1]
            panel_bottom = boxes.get("hero", boxes["offer"])[3]
            self._paint_gradient_panel(img, 0, panel_top, W, panel_bottom, spec.get("brand_color_hex"))
            self._blend_subtle_texture(img, base_image_path, 0, panel_top, W, panel_bottom)

            self._zone_header(img, draw, boxes["header"], kit, brand_name)
            self._zone_headline(img, boxes["headline"], spec, margin_x)
            if "hero" in boxes:
                self._zone_hero(img, boxes["hero"], kit, spec)
            if "spec" in boxes:
                self._zone_spec(img, draw, boxes["spec"], spec, margin_x)
            self._zone_offer(img, draw, boxes["offer"], spec, cta, margin_x)
            if "footer" in boxes:
                self._zone_footer(img, draw, boxes["footer"], kit, margin_x)

            out = img.convert("RGB")
            out.save(output_path, format="PNG", optimize=True)
            logger.info(
                "brochure_composer composed %s (%dx%d) zones=%s",
                output_path, W, H, ",".join(z for z in _ZONE_ORDER if z in boxes),
            )
            return output_path

        except Exception as exc:
            logger.error("brochure_composer.compose failed: %s", exc, exc_info=True)
            raise

    @staticmethod
    def _shade(rgba: tuple, factor: float) -> tuple:
        """Scale an RGBA color's channels by `factor` (darken when < 1), alpha untouched."""
        r, g, b, a = rgba
        clamp = lambda v: max(0, min(255, int(v)))
        return (clamp(r * factor), clamp(g * factor), clamp(b * factor), a)

    def _paint_gradient_panel(
        self, canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, brand_color_hex: Optional[str]
    ) -> None:
        """
        Fill [x0,y0,x1,y1) with a vertical two-stop gradient — the deterministic
        color-block that replaced the SDXL backdrop as the headline+hero
        background. Derived from the brand color when set (darkened at both
        ends so white badge/headline text stays legible); falls back to the
        same dark-navy tone the footer already uses, so the palette reads as
        one design top to bottom even on a campaign with no brand color.
        """
        if brand_color_hex:
            base = _hex_to_rgba(brand_color_hex)
            top, bottom = self._shade(base, 0.55), self._shade(base, 0.28)
        else:
            top, bottom = (32, 36, 52, 255), _FOOTER_BG

        w, h = x1 - x0, max(1, y1 - y0)
        panel = Image.new("RGBA", (w, h), top)
        pd = ImageDraw.Draw(panel)
        for row in range(h):
            t = row / h
            pd.line([(0, row), (w, row)], fill=tuple(
                int(top[i] + (bottom[i] - top[i]) * t) for i in range(4)
            ))
        canvas.alpha_composite(panel, (x0, y0))

    @staticmethod
    def _blend_subtle_texture(
        canvas: Image.Image, base_image_path: str, x0: int, y0: int, x1: int, y1: int, opacity: float = 0.10
    ) -> None:
        """
        Blend the SDXL backdrop into [x0,y0,x1,y1) at low, fixed opacity
        — texture, not a competing image. Desaturated first: a colorful/high-
        contrast backdrop (SDXL's abstract art in particular) still reads as
        busy at low opacity when its hue fights the panel's own color, because
        bright edge pixels visibly lighten the panel even at a small blend
        fraction. Grayscale keeps only luminance variation — texture without
        color competing against the gradient. Failure (missing/unreadable
        file) just means the gradient panel shows through on its own, which is
        a perfectly fine result by itself, so this never raises.
        """
        from app.services.ai.poster_composer import PosterComposer  # local: avoid import cycle at module load
        try:
            with Image.open(base_image_path) as raw:
                tex = raw.convert("L").convert("RGBA")
            tex = PosterComposer._cover_resize(tex, x1 - x0, y1 - y0)
            tex.putalpha(int(255 * opacity))
            canvas.alpha_composite(tex, (x0, y0))
        except Exception as exc:
            logger.warning("brochure_composer texture blend skipped: %s", exc)


brochure_composer = BrochureComposer()
