"""
Load the local parquet file, curate top-N images by aesthetic score,
extract to disk with captions.
"""
import io
import json
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image

PARQUET_PATH = Path("data/train-00000-of-00001.parquet")
OUT_DIR = Path("data/poster_train")
TRIGGER_WORD = "nxmposter"
N_TARGET = 300
MIN_ASPECT, MAX_ASPECT = 0.5, 2.0

OUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"Loading {PARQUET_PATH}...")
table = pq.read_table(PARQUET_PATH)
print(f"Loaded {table.num_rows} rows")

rows = table.to_pylist()

def aspect_ok(dims):
    try:
        w, h = map(int, dims.lower().split("x"))
        r = w / h
        return MIN_ASPECT <= r <= MAX_ASPECT
    except Exception:
        return True

# Filter aspect ratio
rows = [r for r in rows if aspect_ok(r.get("dimensions", "") or "")]
print(f"After aspect filter: {len(rows)}")

# Sort by aesthetic score
rows.sort(key=lambda r: r.get("aesthetic_score", 0) or 0, reverse=True)
selected = rows[:N_TARGET]
print(f"Selected top {len(selected)} by aesthetic_score "
      f"(range {selected[-1]['aesthetic_score']:.2f}-{selected[0]['aesthetic_score']:.2f})")

# Write images + captions
manifest = []
for i, row in enumerate(selected):
    img_field = row["image"]
    img_bytes = img_field["bytes"] if isinstance(img_field, dict) else img_field
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")

    stem = f"pexels_{i:04d}"
    img_path = OUT_DIR / f"{stem}.jpg"
    img.save(img_path, format="JPEG", quality=95)

    caption = (row.get("caption_long") or row.get("caption_short") or "").strip()
    caption = f"{TRIGGER_WORD}, {caption}"
    (OUT_DIR / f"{stem}.txt").write_text(caption, encoding="utf-8")

    manifest.append({
        "file": img_path.name,
        "caption": caption,
        "aesthetic_score": row.get("aesthetic_score")
    })

(OUT_DIR / "_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

print(f"\n✓ Wrote {len(selected)} image+caption pairs to {OUT_DIR.resolve()}")
print(f"Sample caption: {manifest[0]['caption'][:120]}...")
