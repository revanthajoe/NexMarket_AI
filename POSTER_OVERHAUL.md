# Poster Quality Overhaul — Brochure Template Engine

Forward-looking roadmap. Historical/completed work for the wider project lives in [`update.md`](update.md); this file tracks only the poster redesign.

---

## ⚠️ `gemini-3.5-flash` free tier: 20 requests/day per project

Not a bug — Gemini's `generate_content_free_tier_requests` quota for this model is 20/day. A
testing session can exhaust it, producing `429 RESOURCE_EXHAUSTED`. This is handled
correctly already: `_is_transient()` in `ai/llm/gemini_service.py` does not match
`429`/`RESOURCE_EXHAUSTED` (retrying a quota ceiling cannot help it), so it fails fast and
both the brochure-copy and SDXL visual-spec calls fall through to their deterministic
fallback spec exactly as designed. If poster copy looks synthetic (`fallback: True`)
during heavy testing, check for this before assuming something is broken.

## ⚠️ The server runs from `backend/.venv` — install and test there

```
backend/.venv/Scripts/python.exe -m pip install ...
backend/.venv/Scripts/python.exe -m pytest tests/test_main.py -k "not poster_generation"
```

A bare `python`/`pip` on this machine resolves to the **system** interpreter, not
the venv. That mismatch cost a full debugging cycle: `google-genai` was installed
and the whole suite verified green against system Python, while the server —
running from the venv — still had no Gemini SDK and 500'd with
`No module named 'google'`. The two environments had also drifted to different
`bitsandbytes` (0.45.5 vs 0.43.2) and Pillow (12.3 vs 10.1) versions.

**A green test run proves nothing if it ran in the wrong interpreter.**

---

## Why this exists

The generated posters were rejected against a professional reference (a bilingual Soosai Hardwares × Birla Opus paint brochure). Investigation showed **the gap is architectural, not a model-quality problem** — no amount of LoRA tuning, prompt work, or extra inference steps closes it.

| | Current output | Reference brochure |
|---|---|---|
| Layout zones | 1 (background + text on top) | ~8 distinct zones |
| Source of visuals | SDXL generates everything | ~85% typeset over real assets |
| Product image | AI-generated, illegible packaging | Real photo, legible packaging |
| Logos / map | none | Real assets, composited |
| Text | 3 lines | Bilingual pairs throughout |

`PosterComposer.compose()` drew exactly four things: a logo, a CTA pill, the offer, and the headline. That was the entire design vocabulary.

**SDXL cannot draw legible product packaging, brand logos, maps, or text.** It can only supply the decorative background (~15% of the reference). The pipeline was inverted — asking SDXL to carry the whole visual and treating text as a thin overlay. The fix is to demote SDXL to background art and make the composer a real layout engine.

---

## Status

| Phase | What | Status |
|---|---|---|
| 1 | Text shaping + vendored fonts | ✅ Done |
| 2 | Brand kit — new asset slots + contact fields | ✅ Done (backend); frontend panel pending |
| 3 | LLM brochure copy spec + normalizer | ✅ Done |
| 4 | Brochure layout engine (zone composer) | ✅ Done |
| 5 | Wire-in / routing | ✅ Done |
| 6 | Long-prompt (CLIP 77-token) encoding | ✅ Done |
| 7 | Layout tiers — make the zone engine actually run | ✅ Done |
| 8 | Poster phase → Gemini (copy + evaluation) | ✅ Done |
| 9 | Environment correctness + error-path hardening | ✅ Done |
| 10 | numpy 2.x regression — torch/SDXL/Qwen fully broken | ✅ Done |
| 11 | Icon badges + color-blocked background | ✅ Done |

Tests: **57 passing**, run with `backend/.venv/Scripts/python.exe -m pytest tests/test_main.py -k "not poster_generation"`.

---

## Phase 11 — icon badges + color-blocked background

The layout engine was structurally correct (Phase 7) and the copy was finally readable
(Phase 8), but the visual style still didn't match a professional brochure: plain white
circles with text (no icon), sitting on SDXL's full-bleed "artsy" backdrop with only a
light gradient over it. The user supplied two reference designs — a monsoon-themed
hardware-store flyer and a lifestyle paint ad — and asked for that look. Confirmed with
the user: hand-illustrated decoration (paint splashes, brush/roller graphics, cork-board
framing) is explicitly **out of scope**, since those are product-category-specific
illustrations that don't generalize (a paint splash makes no sense on a phone or shoe
poster), and **the system must keep working for any product category** — this was
re-confirmed explicitly mid-session.

**New: `backend/app/services/ai/icon_library.py`.** Nine flat icons drawn with pure PIL
primitives (no external asset files, no licensing to manage): `shield`, `thermometer`,
`droplet`, `crack_shield`, `house`, `leaf`, `star` (also the fallback), `check`, `tag`,
plus `phone`/`pin`/`globe` for the footer. `pick_icon(label_en)` keyword-matches the
English feature label — generic by construction: `shield` fires on any warranty claim
regardless of product ("14 Year Warranty" for paint, "2 Year Warranty" for electronics),
`tag` on any price/value claim, `check` on any trust/certification claim. Verified with
`test_pick_icon_generalizes_across_product_categories`, which spans paint, electronics,
textiles, food and crafts labels.

**A real bug found and fixed while testing this:** naive substring matching classified
"Doctor Recommended" as `leaf`, because `"eco"` is a literal substring of `"recommended"`
(r-**eco**-mmended). Fixed with word-boundary regex matching — most keywords are
deliberate *prefixes* ("warrant" must still match "warranty"), so only a left boundary is
applied generally; a couple of short fragments ("iso") get both boundaries to stay whole-
word, since "iso" alone would otherwise match inside "isolate".

**`_draw_badge` redesigned:** solid accent-colored circle holding one icon, with the
value+label typeset as a caption block *below* the circle (bilingual when available) —
matching the reference's icon-then-caption pattern instead of cramming text inside the
circle. Badge diameters were reduced (0.30→0.22 flanking a product, 0.38→0.26 in the
2×2 no-product layout) since each badge now needs vertical room for its caption.

**The busy SDXL backdrop is gone from the headline+hero span.** `compose()` no longer
cover-resizes the SDXL/Gemini image across the whole canvas; that span is now a
deterministic vertical gradient panel derived from `brand_color_hex` (or a dark-navy
default matching the footer's existing tone), with the backdrop blended in at only 10%
opacity **after being desaturated to grayscale** — a colorful backdrop still read as busy
at low opacity when its hue fought the panel's color, because bright pixels visibly
lightened the panel even at a small blend fraction; grayscale keeps texture without the
color competing. Header/spec/offer/footer zones are unchanged — they already painted
their own opaque backgrounds and already matched the reference's clean look.

This further reduces SDXL's role from Phase 4's original "~15% decorative background art"
down to a barely-visible texture hint — the more robust choice anyway, since Gemini image
generation is still quota-blocked and SDXL only runs as the stopgap (Phase 8/9); a
color-blocked panel looks intentional regardless of what backdrop is or isn't available.

---

## Phase 10 — numpy silently drifted to 2.x and broke every torch service

A real dashboard generation failed completely. Server logs showed two issues stacked:
Gemini's free tier was exhausted (`429`, expected — see the warning at the top of this
file), which correctly fell back to local SDXL/Qwen — except the local fallback was
*also* broken:

```
RuntimeError: Numpy is not available
```

`requirements.txt` pins `numpy>=1.26.0,<2.0.0` specifically because torch 2.1.2 is a
C-extension built against numpy 1.x's ABI. The venv had numpy **2.4.6** anyway, along with
newer-than-pinned `scipy`/`pandas`/`scikit-learn`/`xgboost` that had moved forward with it
— most likely dragged there by `rembg`, which requires `numpy>=2.3` and is already a
documented, *accepted* `pip check` conflict. The accepted trade-off was "a warning we
ignore," not "numpy silently gets upgraded for real and breaks torch." `pip check` reported
nothing wrong, because the whole chain was internally consistent with *itself* — just not
with the torch pin. The failure only surfaced three minutes later, deep inside an unrelated
SDXL scheduler line (`scheduling_euler_discrete.py`'s `torch.from_numpy(timesteps)`),
looking nothing like a numpy version problem.

This broke every torch-based service, not just SDXL: Qwen, Qwen-VL, DistilBERT sentiment,
the LSTM forecaster.

**Fixed:** force-reinstalled the numpy-compatible chain into `backend/.venv` — `numpy
1.26.4`, `scipy 1.13.1`, `pandas 2.2.3`, `scikit-learn 1.5.2`, `xgboost 2.1.4`. Verified
`torch.tensor([1.0, 2.0]).numpy()` succeeds with no `RuntimeError` and no
`_ARRAY_API not found` warning, and confirmed the exact crashing scheduler line now
initializes cleanly.

**Guarded against recurrence:** `pip check` is *not sufficient* to catch this class of
regression — it only checks declared constraints against each other, not against a
C-extension ABI boundary. Added `tests/test_main.py::test_numpy_torch_abi_compatible`,
which exercises the actual boundary (`torch.tensor(...).numpy()`), not just the import, and
runs first in the suite. A comment at the `numpy` pin in `requirements.txt` records the
one-line verification command for after any install that touches this chain.

---

## Phase 9 — the error paths nobody exercised

Four defects, all found by actually running the failing path rather than reasoning about it:

1. **Wrong interpreter** — see the warning at the top of this file.
2. **The friendly dependency guard was unreachable.** Both Gemini services opened their
   methods with `from google.genai import types`, which ran *before* `_get_client()` and
   its `ImportError` handler. A missing package therefore surfaced as
   `No module named 'google'` instead of install instructions. `_get_client()` now
   returns `(client, types)` so the import cannot happen outside the guard.
3. **A fallback evaluation was counting as an approval.** `_FALLBACK_EVALUATION`'s
   synthetic score is **72.5 — above the 70 threshold**. When the evaluator failed, every
   poster "passed" on attempt 1 and the improvement retry never fired: the poster looked
   vetted when nothing had looked at it. `_effective_score()` now maps a `fallback: True`
   result to `-1` so it can never satisfy the gate. (And `best_result is None` is checked
   before the `>` comparison, or an all-fallback run would return `None` for a poster that
   was actually rendered.)
4. **Transient 503s degraded silently.** Gemini returns
   *"this model is currently experiencing high demand"* routinely and it clears in
   seconds — but one blip downgraded a run to synthetic copy or a synthetic score.
   `_call_with_retry` retries transient classes with jittered backoff, while a quota
   `limit: 0` or an unknown model still fails immediately rather than burning three
   attempts on something that cannot succeed.

Also: the visual-spec call is now wrapped. It had a deterministic fallback spec directly
beneath it that only triggered on a bad *return value*, never on an *exception*, so a
network blip 500'd the request and discarded minutes of GPU work.

The `bitsandbytes` pin was relaxed from `==0.43.2` to `>=0.43.2,<0.49` — 0.45.5 is
verified working against torch 2.1.2, and the exact pin would have forced a pointless
downgrade of an environment already running fine.

---

## Phase 8 — the poster phase runs on Gemini

Phase 7 made the layout correct; the *copy* it typeset was still unusable. Qwen2.5-3B
at 4-bit produced `விழுவர் நான்கு மாதம் பெற்றுவர்` as a headline and rendered the brand
name "Birla Opus Paints" as `பிறந்த உபோஸ் பின்னர்` — "Born Opus After". That is a model
capability limit, not a prompting one.

`POSTER_PHASE_PROVIDER=gemini` routes poster **copy** and **evaluation** to
`gemini-3.5-flash`. Deliberately a poster-phase-specific setting rather than the global
`LLM_PROVIDER`: ad copy, sentiment, leads and forecasting keep their local models, and
`test_poster_phase_uses_gemini_but_adcopy_does_not` pins that boundary.

Result: `"இந்த பொங்கலுக்கு உங்கள் இல்லத்தை அழகுபடுத்துங்கள்"` — grammatical Tamil with
the brand name left in Latin. The phase also got ~4× faster (660s → 156s), because Qwen
no longer competes with SDXL for the 6 GB of VRAM.

**Image generation is still SDXL, as a logged stopgap.** Gemini image models return
quota `limit: 0` on this key — a billing state, not a rate limit. The fallback records
`image_backend: "sdxl-stopgap"` in the poster's metadata so a downgrade is never
invisible, and disappears on its own once billing is enabled.

### Three defects the fix exposed

Worth recording because the first was *caused* by getting the copy right:

1. **Mixed-script tofu.** Correct Tamil copy keeps brand names in Latin
   (`10% இலவச Birla Opus Paints`). `NotoSansTamil` has **no Latin glyphs** (verified:
   `get_char_index('B') == 0`), so the single-font render turned the brand name into
   boxes. `text_shaper` now splits text into runs by actual font coverage and renders
   each with a face that can draw it, composited on a shared baseline.
2. **Zones overflowed.** `_draw_centered` wrapped to however many lines it needed, so
   the "why us" strip spilled into the offer band and the bilingual offer ran off the
   canvas. `_draw_fitted` shrinks until the wrapped block fits its box.
3. **Offer text under the CTA pill.** The pill is sized from the CTA string, and a Tamil
   CTA runs longer than English — it outgrew the fixed 28% reservation. The offer's
   width budget is now derived from the pill's measured left edge.

Gemini's vision evaluation also scores honestly: 20-25/100 on the garbled posters, with
the specific mistranslations named. Qwen-VL's vaguer scores were sailing past the 70
approval threshold, so the improvement retry never fired.

---

## Phase 7 — the layout engine was never reachable

Phases 1-6 all landed and were individually verified, and the posters stayed bad
anyway. The reason was a single predicate:

```python
def has_brochure_assets(self) -> bool:        # brand_kit.py, before
    return bool(self.product_cutout_path and (self.phone or self.address_en))
```

Across **21 campaign brand kits on disk, not one** had a `product_cutout`, a
`phone`, or an `address_en` — every `meta.json` held only `language` and
`brand_color_hex` — and the dashboard had no UI to upload any of them. The gate
was therefore false 100% of the time, every poster fell through to
`PosterComposer`'s four-element overlay, and `BrochureComposer` **never executed
once in production**. Phase 4 was built, tested, documented, and dead.

The lesson worth keeping: each phase was verified *in isolation*, and the defect
lived in the wiring between them. A unit test of the composer passes whether or
not anything ever calls it.

**Fixed:**

- `BrandKit.pick_layout()` replaces the boolean and returns `"brochure"` or
  `"designed"` — **both rendered by `BrochureComposer`**. There is deliberately
  no tier that degrades to text over a photograph. `test_pick_layout_never_returns_a_bare_tier`
  enumerates every asset combination to keep it that way.
- Zone heights became **weights, not fixed fractions**. `_zone_boxes()` lays out
  only the zones present and redistributes the rest, so omitting the contact
  footer grows hero and offer instead of leaving an empty strip.
- Zones degrade their *content*: header falls back to the typeset brand name when
  no logo exists, hero falls back cutout → product photo (rounded card) → the
  badges spreading into a balanced 2×2 that owns the zone.
- The offer band now renders **both languages**. It previously did
  `offer_local or offer_en`, silently dropping the English deal on a Tamil
  campaign — the single most persuasive line on the poster.
- SDXL prompts now ask for an abstract backdrop with negative space where the
  zones land, and exclude `people, face, product packaging, central focal
  subject` in the negative prompt. Asking for "marketing photography" with a
  main subject is what produced stock photos competing with every text zone.
- The Brand Kit panel gained the five asset slots and four contact fields, and
  shows which tier the campaign currently earns.

### Two environment regressions found while verifying

Both were silent, and both broke things far from where they appeared:

1. **`uharfbuzz` and `freetype-py` had vanished** from the environment despite
   being pinned. `text_shaper` degrades rather than crashing, so the only signal
   was one log line — and Tamil was rendering incorrectly the whole time.
2. **`bitsandbytes` had drifted to 0.49.2**, which calls
   `torch.library.impl_abstract` — absent until torch 2.2, against the pinned
   torch 2.1.2. transformers imports bitsandbytes lazily, so it surfaced as
   "Failed to import transformers.integrations.bitsandbytes" the first time any
   quantized model loaded, taking down Qwen, Qwen-VL and the whole pipeline.
   The pin was `>=0.43.1` with **no upper bound**, which is what allowed it.
   Now pinned to exactly `0.43.2`, the only version in the window between
   transformers 4.49 (needs `>= 0.43.2` for `.to()` on 4-bit) and torch 2.1.2
   (breaks at `0.49`).

---

## The two blockers, and how they were solved

Both were non-obvious and would otherwise be rediscovered the hard way.

### 1. No Tamil font was reachable

The composer hardcoded Arial, which has **no Tamil glyphs** — Tamil rendered as tofu boxes. No font was vendored in the repo. `Nirmala.ttc` does exist in `C:\Windows\Fonts` (a `.ttc` *collection*, which is why a `.ttf` search missed it), but depending on a specific Windows font install is not reproducible and breaks on any Linux deploy.

**Fixed:** four OFL Noto fonts vendored to `backend/assets/fonts/`. Paths resolve from `Path(__file__).parents[3]`, **not** cwd — deliberately avoiding the `SDXL_LORA_PATH` mistake that once pointed at a non-existent `backend/backend/…`.

### 2. PIL cannot shape complex scripts

`PIL.features.check("raqm")` is **False** — the Pillow Windows wheel ships no libraqm/HarfBuzz. Tamil needs shaping:

- `ெ ே ை` (U+0BC6–U+0BC8) are **prepositioned** — stored *after* their consonant but drawn to its *left*.
- `ொ ோ ௌ` (U+0BCA–U+0BCC) are **split** vowels that decompose into two glyphs straddling the consonant.

Unshaped, PIL lays these out in logical order and the text is visibly wrong. **A Tamil font alone does not fix this.**

**Fixed:** `backend/app/services/ai/text_shaper.py` shapes with `uharfbuzz` and rasterizes with `freetype-py`, returning a PIL RGBA image. Falls back to PIL basic layout with a logged warning if either library is missing — Latin is unaffected, Tamil degrades rather than crashing.

> **Testing note:** do *not* verify reordering by comparing HarfBuzz `cluster` values. HarfBuzz **merges** clusters across reordered glyphs, so equal values are expected and look like failure. The valid signal is glyph **count**: a split vowel like `கொ` (2 codepoints) must emit **3** glyphs.

---

## Phases

### Phase 1 — Text shaping + fonts ✅

| | |
|---|---|
| Files | `backend/app/services/ai/text_shaper.py` (new), `backend/assets/fonts/` (new), `requirements.txt` |
| Deps | `uharfbuzz 0.56.1`, `freetype-py 2.5.1` — pure wheels, neither pulls numpy≥2 |
| API | `render_text()`, `measure_text()`, `shaping_available()`, `has_tamil()`, `font_for_text()` |

`font_for_text()` picks the face by script, so an uploaded Latin-only custom font can never turn Tamil into tofu.

**Verify:** render `மழைக்காலம் வருது!` and compare against the PIL fallback — the shaped version is correct, the fallback visibly corrupts it (`மழகை` for `மழை`).

### Phase 2 — Brand kit ✅ backend / ⬜ frontend

| | |
|---|---|
| Files | `backend/app/services/ai/brand_kit.py`, `backend/app/api/v1/endpoints/brand_kit.py` |

New asset slots: `partner_logo`, `product_cutout`, `map_image`.
New text fields: `phone`, `website`, `address_en`, `address_ta`.

`save_brand_meta` now **merges** instead of overwriting — the previous version rewrote the whole file, so saving just the language would have silently wiped the contact block.

**Remaining:** the frontend Brand Kit panel needs three upload inputs and four text inputs. Until then, upload directly:

```
POST /api/v1/brand-kit/{campaign_id}/upload   asset_type=product_cutout, file=<png>
POST /api/v1/brand-kit/{campaign_id}/meta     phone=..., address_ta=...
```

**Verify:** files land in `backend/assets/brand_kits/<id>/` and read back via `GET /brand-kit/{id}`.

### Phase 3 — Brochure copy spec ✅

| | |
|---|---|
| Files | `backend/app/prompts/templates.py`, `backend/app/services/ai/poster_generator.py` |
| Entry point | `generate_brochure_spec(...)` |

A **separate** prompt from the SDXL visual spec: that one describes a *scene* for the diffusion model, this one writes the *copy* the layout typesets. The SDXL prompt is untouched and still drives background art.

Bilingual keys are `_en` / `_local` rather than `_ta`, so the schema covers every language the CTA table supports (en/hi/ta/te/mr/es/fr) without hardcoding Tamil.

**The CTA is not requested from the model.** `_CTA_MAP` already holds human-authored translations; a 4-bit 3B model inventing Tamil CTA copy is strictly worse than the table that exists.

**The normalizer is the real work.** `normalize_brochure_spec()` guarantees the contract the layout engine depends on, because a 4-bit 3B model routinely returns malformed JSON, wrong array lengths, or drops the second language:

- exactly 4 features and 4 "why" items (pad or truncate)
- every empty `*_local` filled from its `*_en` counterpart — showing English twice beats a blank zone
- every string clamped to a per-field word budget
- deterministic fallback copy when output is unusable, flagged `fallback: True`

That flag matters: a silently-fabricated spec that looks real is exactly the failure that hid a broken evaluator for several runs.

**Verify:** `pytest tests/test_main.py -k brochure` (9 tests, no GPU). For a real check, generate one spec against Qwen for a Tamil campaign and confirm `fallback` is `False` — if it's `True`, inspect the raw JSON before assuming the prompt is fine.

### Phase 4 — Brochure layout engine ✅

`backend/app/services/ai/brochure_composer.py` — zone-based, each zone an independent method taking a bounding box so zones can be reordered or omitted per template.

| Zone | % of canvas height | Content |
|---|---|---|
| Header band | 9% | Two logos on an opaque white strip (one logo centers itself if the partner logo is absent) |
| Headline | 12% | Bilingual pair, auto-shrink |
| Hero | 38% | Transparent product PNG + 4 circular feature badges (2 left / 2 right) |
| Spec strip | 14% | "Why X?" bilingual title + pipe-separated items |
| Offer band | 10% | Offer line + CTA pill |
| Contact footer | 17% | Phone, bilingual address, website, map thumbnail — text auto-sizes to however many of these are actually present |

Reuses `_hex_to_rgba` and `_cover_resize` from `poster_composer.py` directly, and a newly-extracted `render_cta_pill()` helper so both composers render an identical CTA button — extracted from `PosterComposer` rather than duplicated. SDXL's output is cover-resized to fill the whole canvas as a decorative backdrop; the header and footer bands paint over it opaquely, and a vertical alpha gradient keeps the middle band's text legible against whatever art SDXL produced.

**Two bugs caught during the smoke test, both fixed:** the CTA pill was invisible (its text is hardcoded white, so a white pill fill hid it — fixed by using a dark pill fill against the offer band's accent-colored background) and the footer overflowed the canvas when all four contact fields were present (fixed by sizing footer text to the actual line count rather than a fixed fraction, with truncation as a last resort).

**Verified visually** — see the smoke-test render: white header strip with a logo, gradient-backed bilingual headline, four feature badges flanking a product cutout, a black "why us" strip, a red offer band with a working CTA button, and a footer with bilingual address plus website, none of it overflowing the canvas.

### Phase 5 — Wire-in ✅

`get_brand_kit()` defaults to the vendored Noto faces (the Arial default is gone), and `PosterComposer` routes all text through the shaper, so the *existing* poster path already renders Tamil correctly regardless of which composer is used.

`poster_generator._generate_local()` now checks `kit.has_brochure_assets()` once before the generation loop: true routes to `BrochureComposer` (and calls `generate_brochure_spec()` for the bilingual copy, once — not re-generated per retry attempt), false falls back to the original `PosterComposer` path unchanged. Campaigns without the extra brand-kit assets are unaffected. The brochure spec (including its `fallback` flag) and a `layout: "brochure"|"classic"` marker are persisted into `Poster.metadata_` so a synthetic/fallback brochure never masquerades as real copy in the DB record — same convention as `poster_evaluator`'s fallback flag.

### Phase 6 — Long-prompt encoding ✅

The `(92 > 77)` CLIP truncation warning. **The 77 is not configurable** — it is the fixed positional-embedding table size of CLIP's text encoder. Raising it would mean retraining. SDXL has two text encoders (CLIP ViT-L, 768-dim, and OpenCLIP ViT-bigG, 1280-dim) and both are capped.

**What was actually read, not guessed:** the installed `diffusers==0.30.3` source (`pipeline_stable_diffusion_xl.py:encode_prompt`, lines 353-464), to get the exact embedding contract right:
- Per encoder: `text_encoder(input_ids, output_hidden_states=True)`, then take `hidden_states[-2]` — the *penultimate* layer, not the final one.
- The two encoders' per-chunk outputs concatenate on the **feature** axis (768+1280 = 2048).
- `pooled_prompt_embeds` comes **only from `text_encoder_2`** (bigG) — diffusers' own loop overwrites the pooled variable each iteration, so the ViT-L pooled output is computed and discarded.
- The negative prompt is tokenized to the same length as the positive prompt, because SDXL batches them together for classifier-free guidance and the sequence lengths must match.

**Implemented in `backend/ai/diffusion/sdxl_service.py`:** `_chunk_and_encode()` splits a prompt into 75-token chunks (leaving room for BOS/EOS within the 77 cap), re-wraps and pads each chunk, encodes it, and concatenates chunks on the **sequence** axis — this is what actually lets content past token 77 reach the UNet, a separate step from the two-encoder feature-axis concat above. `_encode_long_prompt()` runs this for both encoders and both prompts (positive and negative, forced to the same chunk count).

`generate()` only takes this path when a prompt actually exceeds 77 tokens (checked via `pipe.tokenizer(prompt, truncation=False)`); short prompts — the common case now that phase 4 demoted SDXL to background art — go through the original `prompt=`/`negative_prompt=` call unchanged. The execution device is read via diffusers' own `pipe._execution_device` property rather than a model's `.device` attribute, which is required for correctness under `enable_model_cpu_offload()` — a param's resting device is not the same as the device its offload hook expects inputs on.

Implemented directly rather than adding `compel` (which does the same thing) — the HF stack is deliberately frozen (see trade-offs below) and this codebase has already broken twice on dependency drift; ~100 lines against a pinned, already-read diffusers version was the lower-risk choice.

**Verified without loading the real 6.9GB SDXL pipeline:** 4 unit tests (`test_sdxl_chunk_*`, `test_sdxl_encode_long_prompt_*` in `tests/test_main.py`) exercise the chunking math against tiny fake tokenizer/encoder stand-ins — confirming a short prompt stays at 1 chunk, a 150-word prompt correctly produces `ceil(150/75)=2` chunks and the sequence axis actually grows (154 tokens, not clamped at 77), positive/negative prompts of different lengths still end up with matching shapes, and the final concatenated embedding is the correct 2048-dim (768+1280) with pooled output from the bigG encoder only.

The old `sdxl_prompt[:380]` character cap in `poster_generator.py` is gone — a character count was never equivalent to the real 77-*token* limit, which is exactly why prompts were still being silently truncated by CLIP despite the cap existing. Raised to a generous 1500-character safety bound (worst-case encoding cost, not an approximation of 77 tokens).

**Real-model verification still pending** (needs the actual SDXL pipeline loaded, not just unit tests): generate a poster with a long prompt from the dashboard and confirm the `Token indices sequence length is longer...` warning no longer appears, and that content from the tail of a long prompt visibly influences the image versus the same prompt with that tail deleted.

---

## Assets needed from you

Phase 4's output quality is **gated** on these. Without them the layout engine has empty zones.

| Asset | Notes |
|---|---|
| Transparent product PNG | Pre-cut, no background. Becomes the brochure hero. |
| Partner / second logo | The reference has two (retailer + product brand). |
| Map / location image | Contact footer thumbnail. |
| Contact details | Phone, website, address in English **and** Tamil. |

---

## Accepted trade-offs

**rembg is permanently retired.** It needs `onnxruntime` (absent) *and* `numpy>=2.3`, which conflicts irreconcilably with the `numpy<2` that torch 2.1.2 requires. `pip check` reports this conflict permanently — it is expected and can be ignored. The product cutout is supplied as a pre-cut PNG instead, which sidesteps the whole problem.

It also caused a real outage worth remembering: rembg calls `sys.exit(1)` when onnxruntime is missing, raising `SystemExit` — a `BaseException`, so `except Exception` did not catch it. That escaped past Starlette's error middleware, produced a response with no CORS header, and the frontend's dev port-scan then burned through ports 8001–8005 before surfacing a misleading "cannot connect to backend". One uncaught `BaseException`, three misleading symptoms.

**The Hugging Face stack is frozen.** `diffusers==0.30.3` and `peft==0.13.2` are mid-2024 pins running against much newer `transformers 4.49` / `accelerate`. Upper bounds are set on `accelerate` and `huggingface_hub` so a clean install reproduces the verified-working combination rather than pulling whatever is newest. Do not upgrade these casually — the LoRA path is verified working against exactly this set.
