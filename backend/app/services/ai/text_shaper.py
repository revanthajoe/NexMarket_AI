"""
app/services/ai/text_shaper.py
─────────────────────────────────────────────────────────────────────────────
Complex-script-aware text rendering.

Why this module exists
──────────────────────
PIL cannot shape complex scripts on this build: `PIL.features.check("raqm")` is
False because the Pillow Windows wheel bundles no libraqm/HarfBuzz. Without
shaping, PIL lays glyphs out in *logical* order, which is visibly wrong for
Tamil:

  • U+0BC6..U+0BC8 (ெ ே ை) are **prepositioned** — stored after their consonant
    but drawn to its left. Unshaped, they land on the wrong side.
  • U+0BCA..U+0BCC (ொ ோ ௌ) are **split** vowels that decompose into two glyphs
    straddling the consonant. Unshaped, they never decompose at all.

So this module shapes runs with HarfBuzz (`uharfbuzz`) and rasterizes the
resulting positioned glyphs with FreeType (`freetype-py`), returning a PIL
RGBA image the composer can paste.

Degradation
───────────
If either library is missing, everything falls back to PIL's basic layout and a
warning is logged once. Latin is unaffected by the fallback; Tamil degrades
rather than crashing — the same resilience standard applied to rembg in
`poster_composer.py`.
"""
from __future__ import annotations

import logging
import threading
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Optional

from PIL import Image, ImageChops, ImageFont

logger = logging.getLogger(__name__)

# ── Optional shaping backend ─────────────────────────────────────────────────
try:
    import uharfbuzz as _hb
    import freetype as _ft
    _SHAPING_AVAILABLE = True
except BaseException as exc:  # pragma: no cover - environment dependent
    logger.warning(
        "text_shaper: shaping unavailable (%s). Falling back to PIL basic layout - "
        "Latin is fine, Tamil will render incorrectly.", exc,
    )
    _hb = None
    _ft = None
    _SHAPING_AVAILABLE = False


# ── Font locations ───────────────────────────────────────────────────────────
# Resolved relative to THIS FILE, not the process cwd. Deliberate: SDXL_LORA_PATH
# was configured cwd-relative once before and silently pointed at a non-existent
# backend/backend/... path. Anchoring to __file__ cannot drift.
#   backend/app/services/ai/text_shaper.py -> parents[3] == backend/
_FONT_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"

FONT_LATIN_REGULAR = _FONT_DIR / "NotoSans-Regular.ttf"
FONT_LATIN_BOLD    = _FONT_DIR / "NotoSans-Bold.ttf"
FONT_TAMIL_REGULAR = _FONT_DIR / "NotoSansTamil-Regular.ttf"
FONT_TAMIL_BOLD    = _FONT_DIR / "NotoSansTamil-Bold.ttf"

# Last-resort fallbacks if the vendored fonts are missing. Nirmala is a .ttc
# collection and does cover Tamil; Arial does not (renders tofu).
_SYS_FALLBACK_TAMIL = Path(r"C:\Windows\Fonts\Nirmala.ttc")
_SYS_FALLBACK_LATIN = Path(r"C:\Windows\Fonts\arial.ttf")

# FreeType Face objects carry mutable size state, and poster generation runs in a
# thread-pool executor, so serialise access.
_render_lock = threading.Lock()


def shaping_available() -> bool:
    """True when HarfBuzz + FreeType are usable (i.e. Tamil will render correctly)."""
    return _SHAPING_AVAILABLE


def has_tamil(text: str) -> bool:
    """True if the string contains any Tamil-block codepoint (U+0B80..U+0BFF)."""
    return any("\u0b80" <= ch <= "\u0bff" for ch in text)


def font_for_text(text: str, bold: bool = False) -> str:
    """Pick the vendored font that can actually render `text`."""
    if has_tamil(text):
        primary  = FONT_TAMIL_BOLD if bold else FONT_TAMIL_REGULAR
        fallback = _SYS_FALLBACK_TAMIL
    else:
        primary  = FONT_LATIN_BOLD if bold else FONT_LATIN_REGULAR
        fallback = _SYS_FALLBACK_LATIN

    if primary.exists():
        return str(primary)
    logger.warning("text_shaper: vendored font missing (%s), falling back to %s", primary, fallback)
    return str(fallback)


# ── Mixed-script segmentation ────────────────────────────────────────────────
#
# A single string can legitimately mix scripts: correct Tamil copy keeps brand
# names in Latin ("10% இலவச Birla Opus Paints"). NotoSansTamil has no Latin
# glyphs and NotoSans has no Tamil, so whichever single font is chosen renders
# the other half as tofu boxes — which is exactly what shipped once the copy
# model stopped mistranslating brand names into Tamil.
#
# So text is split into runs by coverage, and each run is rendered with a font
# that can actually draw it.


def _is_bold_font(font_path: str) -> bool:
    return "bold" in Path(font_path).stem.lower()


@lru_cache(maxsize=4096)
def _font_has_char(font_path: str, ch: str) -> bool:
    """True if `font_path` has a glyph for `ch`. FreeType returns index 0 when not."""
    if not _SHAPING_AVAILABLE:
        return True
    try:
        return _ft_face(font_path).get_char_index(ch) != 0
    except Exception:
        return True


def _runs_with_fonts(text: str, font_path: str) -> list[tuple[str, str]]:
    """
    Split `text` into (run, font_path) pairs.

    The requested font is kept wherever it has coverage; only characters it
    cannot draw are moved to the script-appropriate vendored face. Whitespace is
    treated as coverage-neutral so a space between scripts does not split a run
    into three.
    """
    if not text:
        return []

    bold = _is_bold_font(font_path)
    runs: list[tuple[str, str]] = []
    current: list[str] = []
    current_font: str | None = None

    for ch in text:
        if ch.isspace() and current:
            current.append(ch)
            continue
        if _font_has_char(font_path, ch):
            chosen = font_path
        else:
            chosen = font_for_text(ch, bold=bold)
            # If the fallback cannot draw it either, keep the original font so
            # the glyph is at least consistently rendered (as .notdef) rather
            # than bouncing between faces mid-word.
            if not _font_has_char(chosen, ch):
                chosen = font_path
        if chosen != current_font and current:
            runs.append(("".join(current), current_font))
            current = []
        current_font = chosen
        current.append(ch)

    if current:
        runs.append(("".join(current), current_font or font_path))
    return runs


# ── Font loading (cached) ────────────────────────────────────────────────────

@lru_cache(maxsize=16)
def _font_bytes(font_path: str) -> bytes:
    return Path(font_path).read_bytes()


@lru_cache(maxsize=16)
def _hb_face(font_path: str):
    return _hb.Face(_font_bytes(font_path))


@lru_cache(maxsize=16)
def _ft_face(font_path: str):
    return _ft.Face(font_path)


@lru_cache(maxsize=64)
def _pil_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        return ImageFont.load_default()


# ── Shaping core ─────────────────────────────────────────────────────────────

def _shape(text: str, font_path: str, size: int):
    """
    Run HarfBuzz over `text`.

    Returns (glyph_infos, glyph_positions). HarfBuzz scale is set to size*64 so
    the returned advances/offsets are in 26.6 fixed point (1/64 px) and match
    FreeType's pixel rasterization at the same size.
    """
    hb_font = _hb.Font(_hb_face(font_path))
    hb_font.scale = (size * 64, size * 64)

    buf = _hb.Buffer()
    buf.add_str(text)
    # Infers script/direction/language from the codepoints - this is what selects
    # the Tamil shaper and triggers vowel reordering + split-vowel decomposition.
    buf.guess_segment_properties()
    _hb.shape(hb_font, buf)
    return buf.glyph_infos, buf.glyph_positions


def _glyph_bitmap(ft_face, gid: int) -> tuple[Image.Image | None, int, int]:
    """Rasterize one glyph. Returns (L-mode image or None, bitmap_left, bitmap_top)."""
    ft_face.load_glyph(gid, _ft.FT_LOAD_RENDER)
    slot = ft_face.glyph
    bm   = slot.bitmap
    w, h, pitch = bm.width, bm.rows, bm.pitch

    if w == 0 or h == 0:          # whitespace and other blank glyphs
        return None, slot.bitmap_left, slot.bitmap_top

    # `pitch` is the row stride and is not always equal to `width`, so rows must
    # be sliced out individually rather than handing the raw buffer to frombytes.
    raw  = bytes(bm.buffer)
    rows = b"".join(raw[y * pitch : y * pitch + w] for y in range(h))
    return Image.frombytes("L", (w, h), rows), slot.bitmap_left, slot.bitmap_top


def _measure_run(text: str, font_path: str, size: int) -> tuple[int, int, int]:
    """Measure a single-font run. Returns (width, ascender, descender)."""
    with _render_lock:
        ft_face = _ft_face(font_path)
        ft_face.set_pixel_sizes(0, size)
        _, positions = _shape(text, font_path, size)
        width = int(sum(p.x_advance for p in positions) // 64)
        return width, int(ft_face.size.ascender // 64), int(ft_face.size.descender // 64)


def measure_text(text: str, font_path: str, size: int) -> tuple[int, int]:
    """Return the (width, height) `text` will occupy when rendered."""
    if not text:
        return (0, 0)

    if not _SHAPING_AVAILABLE:
        font = _pil_font(font_path, size)
        bb = font.getbbox(text)
        return (bb[2] - bb[0], bb[3] - bb[1])

    width = 0
    ascender = descender = 0
    for run, run_font in _runs_with_fonts(text, font_path):
        w, asc, desc = _measure_run(run, run_font, size)
        width += w
        ascender  = max(ascender, asc)
        descender = min(descender, desc)     # descender is negative
    return (width, max(1, ascender - descender))


def render_text(
    text: str,
    font_path: str,
    size: int,
    color: tuple = (255, 255, 255, 255),
) -> Image.Image:
    """
    Render `text` to a transparent RGBA image, correctly shaped.

    The image height spans the font's full ascender..descender box so that
    multiple runs rendered at the same size share a consistent baseline and can
    be stacked without drifting.
    """
    if not text:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    if not _SHAPING_AVAILABLE:
        return _render_text_pil(text, font_path, size, color)

    try:
        runs = _runs_with_fonts(text, font_path)

        # Measure first so every run can share one baseline. Runs may use
        # different faces with different metrics, so the canvas baseline is the
        # tallest ascender and each run is placed relative to it — otherwise a
        # Latin brand name inside a Tamil line sits visibly off-baseline.
        measured = [(run, rf) + _measure_run(run, rf, size) for run, rf in runs]
        total_w  = sum(m[2] for m in measured)
        baseline = max((m[3] for m in measured), default=size)
        descender = min((m[4] for m in measured), default=0)
        height   = max(1, baseline - descender)
        width    = max(1, total_w + size)

        alpha = Image.new("L", (width, height), 0)
        origin_x = 0

        for run, run_font, run_w, _asc, _desc in measured:
            with _render_lock:
                ft_face = _ft_face(run_font)
                ft_face.set_pixel_sizes(0, size)
                infos, positions = _shape(run, run_font, size)

                pen_x = pen_y = 0
                for info, pos in zip(infos, positions):
                    glyph, left, top = _glyph_bitmap(ft_face, info.codepoint)
                    if glyph is not None:
                        x = origin_x + (pen_x + pos.x_offset) // 64 + left
                        y = baseline - ((pen_y + pos.y_offset) // 64 + top)
                        # `lighter` (max) rather than paste so overlapping marks -
                        # common in Tamil - accumulate instead of clipping each other.
                        layer = Image.new("L", (width, height), 0)
                        layer.paste(glyph, (int(x), int(y)))
                        alpha = ImageChops.lighter(alpha, layer)
                    pen_x += pos.x_advance
                    pen_y += pos.y_advance

            origin_x += run_w

        out = Image.new("RGBA", (width, height), color[:3] + (0,))
        out.putalpha(alpha)
        return out

    except Exception as exc:
        logger.warning("text_shaper: shaping failed for %r (%s), using PIL fallback", text[:40], exc)
        return _render_text_pil(text, font_path, size, color)


def _render_text_pil(text: str, font_path: str, size: int, color: tuple) -> Image.Image:
    """PIL basic-layout fallback. Correct for Latin, wrong for Tamil."""
    from PIL import ImageDraw

    font = _pil_font(font_path, size)
    bb = font.getbbox(text)
    w  = max(1, bb[2] - bb[0] + 4)
    h  = max(1, bb[3] - bb[1] + 4)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((-bb[0] + 2, -bb[1] + 2), text, font=font, fill=color)
    return img
