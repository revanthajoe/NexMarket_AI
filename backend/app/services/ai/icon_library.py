"""
app/services/ai/icon_library.py
─────────────────────────────────────────────────────────────────────────────
A small set of flat icons, drawn with PIL primitives — no external asset
files. Used by BrochureComposer's feature badges and contact footer.

Generic by construction, not paint-specific: every icon maps to a category of
*claim* a marketing feature list makes, not to a product. `shield` fires on
any warranty/guarantee claim whether the campaign sells paint, phones, or
mattresses; `star` on any quality/premium claim; `check` on any trust/
certification claim; `tag` on any price/value/offer claim; `leaf` on any eco/
natural claim. `droplet`/`thermometer`/`crack_shield`/`house` are the only
icons with a physical lean (water/temperature/structural resistance/coverage),
and they still fire on the literal words in the label, not on "is this a paint
campaign" — a waterproof phone case matches `droplet` exactly the same way a
rainproof paint does. `_pick_icon()` always returns something (falling back to
`star`), so a feature that matches nothing still gets a badge, never a blank.
"""
from __future__ import annotations

import re

from PIL import ImageDraw

# ── Keyword -> icon mapping ───────────────────────────────────────────────────
# Checked in this order; first match wins. Keep keyword lists short and
# specific — a keyword list that's too broad starts stealing matches from
# more specific icons below it.
_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("crack_shield", ("crack", "bridg", "structural", "impact resist")),
    ("droplet",      ("water", "rain", "damp", "moist", "leak")),
    ("thermometer",  ("cool", "temperature", "thermal", "heat reflect", "°c", "degree")),
    ("shield",       ("warrant", "guarantee", "protect", "safe", "secure", "assured")),
    ("house",        ("wall", "roof", "coverage", "cover", "area", "home", "interior", "exterior")),
    ("leaf",         ("eco", "natural", "organic", "green", "sustainab", "non-toxic", "cotton")),
    ("check",        ("trust", "certif", "verified", "expert", "support", "rated", "recommend", "iso")),
    ("tag",          ("price", "value", "discount", "off", "free", "save", "emi", "stock", "afford")),
    # "star" is the deliberate final fallback — see module docstring.
]

_VALID_ICONS = frozenset(
    {name for name, _ in _KEYWORDS} | {"star", "phone", "pin", "globe"}
)

# Most keywords above are deliberate PREFIXES — "warrant" must match
# "warranty", "rain" must match "rainproof", "cool" must match "cooler" — so
# only a LEFT word boundary is applied generally. A left boundary alone is
# still what fixes the real bug found while testing this: naive substring
# matching classified "Doctor Recommended" as `leaf`, because "eco" is a
# literal substring of "recommended" (r-ECO-mmended) — with a left boundary,
# "eco" only matches at the *start* of a word, and "recommended" has no word
# boundary before that "eco". A few fragments are short enough to also collide
# at the START of an unrelated word ("iso" starts "isolate"/"isolation"), so
# those get a right boundary too and become whole-word matches.
_EXACT_WORD = {"iso"}


def _compile(keyword: str) -> re.Pattern:
    left  = r"\b" if keyword[0].isalnum() else ""
    right = r"\b" if keyword.lower() in _EXACT_WORD else ""
    return re.compile(left + re.escape(keyword) + right, re.IGNORECASE)


_COMPILED: list[tuple[str, list[re.Pattern]]] = [
    (icon, [_compile(kw) for kw in kws]) for icon, kws in _KEYWORDS
]


def pick_icon(label_en: str) -> str:
    """
    Choose an icon key for a feature label. Always returns a valid icon name.

    Matches against `label_en` specifically — Tamil/other-language text isn't
    keyword-matched, but `normalize_brochure_spec` guarantees `label_en` is
    always populated regardless of campaign language, so this works for every
    supported language without per-language keyword lists.

    Uses word-boundary matching, not plain substring: naive `"eco" in text`
    misfires on "doctor rEComended" — "eco" is a literal substring of
    "recommended". Whole-word matching is what keeps the keyword lists safe to
    keep short.
    """
    text = label_en or ""
    for icon, patterns in _COMPILED:
        if any(p.search(text) for p in patterns):
            return icon
    return "star"


def draw_icon(draw: ImageDraw.ImageDraw, name: str, cx: int, cy: int, size: int, color: tuple) -> None:
    """
    Draw icon `name` centered at (cx, cy) inside a `size`×`size` box, in `color`.

    Each icon is a simple, bold-stroke flat shape — legible at badge scale
    (roughly 40-70px). Unknown names fall back to `star` rather than raising,
    since a badge must never end up blank because of a typo in a caller.
    """
    if name not in _VALID_ICONS:
        name = "star"
    r = size / 2
    w = max(2, size // 12)  # stroke width, scales with icon size

    if name == "shield":
        pts = [
            (cx, cy - r), (cx + r * 0.8, cy - r * 0.55), (cx + r * 0.8, cy + r * 0.15),
            (cx, cy + r), (cx - r * 0.8, cy + r * 0.15), (cx - r * 0.8, cy - r * 0.55),
        ]
        draw.polygon(pts, outline=color, width=w)
        # Checkmark inside.
        draw.line([(cx - r * 0.35, cy), (cx - r * 0.05, cy + r * 0.3), (cx + r * 0.4, cy - r * 0.35)],
                  fill=color, width=w, joint="curve")

    elif name == "crack_shield":
        pts = [
            (cx, cy - r), (cx + r * 0.8, cy - r * 0.55), (cx + r * 0.8, cy + r * 0.15),
            (cx, cy + r), (cx - r * 0.8, cy + r * 0.15), (cx - r * 0.8, cy - r * 0.55),
        ]
        draw.polygon(pts, outline=color, width=w)
        # Jagged crack line through the middle.
        draw.line([
            (cx - r * 0.4, cy - r * 0.5), (cx - r * 0.1, cy - r * 0.1),
            (cx - r * 0.3, cy + r * 0.15), (cx + r * 0.1, cy + r * 0.55),
        ], fill=color, width=w, joint="curve")

    elif name == "droplet":
        # Teardrop: a triangle top merging into a circle bottom.
        draw.polygon([(cx, cy - r), (cx + r * 0.68, cy + r * 0.15), (cx - r * 0.68, cy + r * 0.15)],
                    outline=color, width=w)
        bottom_r = r * 0.68
        draw.arc([cx - bottom_r, cy - bottom_r * 0.3, cx + bottom_r, cy + bottom_r * 1.7],
                 start=0, end=360, fill=color, width=w)

    elif name == "thermometer":
        stem_w = max(3, int(size * 0.16))
        x0, x1 = cx - stem_w // 2, cx + stem_w // 2
        top, bulb_top = cy - r * 0.85, cy + r * 0.35
        draw.rounded_rectangle([x0, top, x1, bulb_top], radius=stem_w // 2, outline=color, width=w)
        bulb_r = stem_w * 0.9
        draw.ellipse([cx - bulb_r, cy + r * 0.15, cx + bulb_r, cy + r * 0.15 + bulb_r * 2],
                    fill=color, outline=color)
        draw.line([(cx, top + stem_w * 0.6), (cx, cy)], fill=color, width=max(2, w - 1))

    elif name == "house":
        roof = [(cx, cy - r), (cx + r * 0.95, cy - r * 0.05), (cx - r * 0.95, cy - r * 0.05)]
        draw.polygon(roof, outline=color, width=w)
        bx0, by0, bx1, by1 = cx - r * 0.62, cy - r * 0.05, cx + r * 0.62, cy + r * 0.85
        draw.rectangle([bx0, by0, bx1, by1], outline=color, width=w)
        door_w = (bx1 - bx0) * 0.32
        draw.rectangle([cx - door_w / 2, by1 - (by1 - by0) * 0.55, cx + door_w / 2, by1],
                       outline=color, width=max(2, w - 1))

    elif name == "leaf":
        _draw_leaf(draw, cx, cy, r, color, w)

    elif name == "check":
        draw.ellipse([cx - r * 0.9, cy - r * 0.9, cx + r * 0.9, cy + r * 0.9], outline=color, width=w)
        draw.line([(cx - r * 0.42, cy), (cx - r * 0.08, cy + r * 0.38), (cx + r * 0.48, cy - r * 0.32)],
                  fill=color, width=w, joint="curve")

    elif name == "tag":
        pts = [(cx - r * 0.85, cy - r * 0.15), (cx + r * 0.15, cy - r * 0.85),
              (cx + r * 0.85, cy - r * 0.15), (cx - r * 0.15, cy + r * 0.85)]
        draw.polygon(pts, outline=color, width=w)
        hole_r = r * 0.12
        hx, hy = cx - r * 0.35, cy - r * 0.5
        draw.ellipse([hx - hole_r, hy - hole_r, hx + hole_r, hy + hole_r], outline=color, width=max(2, w - 1))

    elif name == "phone":
        _draw_phone(draw, cx, cy, r, color)

    elif name == "pin":
        draw.pieslice([cx - r * 0.75, cy - r, cx + r * 0.75, cy + r * 0.5], start=180, end=360,
                      outline=color, width=w)
        draw.polygon([(cx - r * 0.55, cy + r * 0.02), (cx + r * 0.55, cy + r * 0.02), (cx, cy + r)],
                    outline=color, width=w)
        inner_r = r * 0.22
        draw.ellipse([cx - inner_r, cy - r * 0.35 - inner_r, cx + inner_r, cy - r * 0.35 + inner_r],
                    outline=color, width=max(2, w - 1))

    elif name == "globe":
        draw.ellipse([cx - r * 0.85, cy - r * 0.85, cx + r * 0.85, cy + r * 0.85], outline=color, width=w)
        draw.line([(cx, cy - r * 0.85), (cx, cy + r * 0.85)], fill=color, width=max(2, w - 1))
        draw.ellipse([cx - r * 0.42, cy - r * 0.85, cx + r * 0.42, cy + r * 0.85],
                    outline=color, width=max(2, w - 1))
        draw.line([(cx - r * 0.85, cy), (cx + r * 0.85, cy)], fill=color, width=max(2, w - 1))

    else:  # "star" — deliberate final fallback, see module docstring.
        _draw_star(draw, cx, cy, r, color, w)


def _draw_leaf(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color: tuple, w: int) -> None:
    """A pointed, diagonally-tilted leaf: a lens silhouette (two quadratic
    bezier sides meeting at two tips) with a centre vein and a small stem."""
    tip_a  = (cx - r * 0.7, cy - r * 0.7)
    tip_b  = (cx + r * 0.7, cy + r * 0.7)
    ctrl_1 = (cx + r * 0.95, cy - r * 0.15)
    ctrl_2 = (cx - r * 0.95, cy + r * 0.15)

    def _quad_bezier(p0, p1, p2, steps=14):
        pts = []
        for i in range(steps + 1):
            t = i / steps
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
            pts.append((x, y))
        return pts

    outline = _quad_bezier(tip_a, ctrl_1, tip_b) + _quad_bezier(tip_b, ctrl_2, tip_a)[1:]
    draw.polygon(outline, outline=color, width=w)
    draw.line([tip_a, tip_b], fill=color, width=max(2, w - 1))
    stem_end = (tip_b[0] + r * 0.2, tip_b[1] + r * 0.2)
    draw.line([tip_b, stem_end], fill=color, width=max(2, w - 1))


def _draw_phone(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color: tuple) -> None:
    """Classic flat handset icon: a thick diagonal bar with two round ends."""
    import math
    angle = math.radians(-45)
    half_len = r * 0.65
    dx, dy = math.cos(angle) * half_len, math.sin(angle) * half_len
    p1, p2 = (cx - dx, cy - dy), (cx + dx, cy + dy)
    draw.line([p1, p2], fill=color, width=max(3, int(r * 0.5)))
    end_r = r * 0.32
    for px, py in (p1, p2):
        draw.ellipse([px - end_r, py - end_r, px + end_r, py + end_r], fill=color)


def _draw_star(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color: tuple, w: int) -> None:
    import math
    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        radius = r if i % 2 == 0 else r * 0.42
        points.append((cx + radius * math.cos(angle), cy - radius * math.sin(angle)))
    draw.polygon(points, outline=color, width=w)
