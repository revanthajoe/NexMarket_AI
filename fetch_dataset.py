"""
Fetches a curated training subset from RayyanAhmed9477/pexels-advertisement-photography
(Pexels License — free commercial + non-commercial use) without downloading the
full 2.4GB parquet.

The file has 24 row groups of ~539 rows each. We range-read a handful spread
across the file (for category diversity — the source was built from 40
sequential search queries, so consecutive rows cluster by category) and keep
the top-N by aesthetic_score.
"""
import io
import json
from pathlib import Path

import fsspec
import pyarrow.parquet as pq
from PIL import Image

URL = "https://huggingface.co/datasets/RayyanAhmed9477/pexels-advertisement-photography/resolve/main/data/train-00000-of-00001.parquet"
OUT_DIR = Path("data/poster_train")
TRIGGER_WORD = "nxmposter"
N_TARGET = 300
ROW_GROUPS_TO_FETCH = [0, 4, 8, 12, 16, 20]  # spread across the 24 groups
MIN_ASPECT, MAX_ASPECT = 0.5, 2.0            # drop extreme panoramas/strips

OUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"opening remote parquet (range-read only, not full download)...")
fs = fsspec.filesystem("http")
f = fs.open(URL, block_size=1 << 20)
pf = pq.ParquetFile(f)
print(f"total rows={pf.metadata.num_rows}  row_groups={pf.num_row_groups}")

tables = []
for rg in ROW_GROUPS_TO_FETCH:
    print(f"  fetching row group {rg} ...")
    t = pf.read_row_group(rg, columns=["image", "caption_long", "caption_short", "aesthetic_score", "dimensions"])
    tables.append(t)
    print(f"    got {t.num_rows} rows")

import pyarrow as pa
table = pa.concat_tables(tables)
print(f"\ncandidate pool: {table.num_rows} rows")

rows = table.to_pylist()

# Filter: drop unusable aspect ratios before ranking, so a great score on a
# panorama doesn't crowd out a usable square/portrait shot.
def aspect_ok(dims):
    try:
        w, h = map(int, dims.lower().split("x"))
        r = w / h
        return MIN_ASPECT <= r <= MAX_ASPECT
    except Exception:
        return True

rows = [r for r in rows if aspect_ok(r.get("dimensions", "") or "")]
print(f"after aspect filter: {len(rows)}")

rows.sort(key=lambda r: r.get("aesthetic_score", 0) or 0, reverse=True)
selected = rows[:N_TARGET]
print(f"selected top {len(selected)} by aesthetic_score "
      f"(range {selected[-1]['aesthetic_score']:.2f}-{selected[0]['aesthetic_score']:.2f})")

# ── write images + captions ──────────────────────────────────────────────────
manifest = []
for i, row in enumerate(selected):
    img_field = row["image"]
    img_bytes = img_field["bytes"] if isinstance(img_field, dict) else img_field
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")

    stem = f"pexels_{i:04d}"
    img_path = OUT_DIR / f"{stem}.jpg"
    img.save(img_path, format="JPEG", quality=95)

    # caption_long describes composition/lighting/mood - exactly what SDXL
    # needs to learn, since it only ever renders the background visual.
    caption = (row.get("caption_long") or row.get("caption_short") or "").strip()
    caption = f"{TRIGGER_WORD}, {caption}"
    (OUT_DIR / f"{stem}.txt").write_text(caption, encoding="utf-8")

    manifest.append({"file": img_path.name, "caption": caption, "aesthetic_score": row.get("aesthetic_score")})

(OUT_DIR / "_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

print(f"\nwrote {len(selected)} image+caption pairs to {OUT_DIR.resolve()}")
print(f"sample caption:\n  {manifest[0]['caption'][:160]}")
