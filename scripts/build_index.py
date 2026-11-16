#!/usr/bin/env python3
"""Build the VEIN SEARCH product catalogue + CLIP embedding index.

Inputs:
  data/raw/wikimedia/index.json   (fetched candidates with provenance)
  data/raw/curated.json           (manual curation decisions)
  data/raw/synthetic_manifest.json(generated textures)
  data/catalogue/images/syn_*.png (already generated)

Outputs:
  data/catalogue/images/          (wm_<pageid>.<ext> copies)
  data/catalogue/products.json    (catalogue records)
  data/catalogue/embeddings.npy   (L2-normalised float32 CLIP embeddings)
"""
import datetime
import hashlib
import json
import pathlib

import sys

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.core.embedder import ImageEmbedder  # noqa: E402

DATA = ROOT / "data"
CAT = DATA / "catalogue"
IMAGES = CAT / "images"
IMAGES.mkdir(parents=True, exist_ok=True)

TODAY = datetime.date.today().isoformat()


def normalise_name(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def main():
    index_list = json.loads((DATA / "raw/wikimedia/index.json").read_text())
    index = {i: m for i, m in enumerate(index_list)}
    curated = json.loads((DATA / "raw/curated.json").read_text())
    synth = json.loads((DATA / "raw/synthetic_manifest.json").read_text())

    products = []

    for pos, entry in enumerate(curated["keep"], start=1):
        meta = index[entry["i"]]
        ext = "jpg" if meta["mime"] == "image/jpeg" else "png"
        src = DATA / "raw/wikimedia" / f"{meta['pageid']}.{ext}"
        assert src.exists(), f"missing {src}"
        # crop/copy into catalogue images (keep <=1024 px)
        img = Image.open(src).convert("RGB")
        img.thumbnail((1024, 1024))
        fname = f"wm_{meta['pageid']}.{ext}"
        img.save(IMAGES / fname, quality=88)

        pid = f"WM-{pos:02d}"
        products.append(
            {
                "id": pid,
                "name": entry["name"],
                "category": entry["category"],
                "colour_family": entry["colour_family"],
                "finish": entry.get("finish"),
                "origin": entry.get("origin"),
                "description": meta["description"] or None,
                "image": fname,
                "is_synthetic": False,
                "provenance": {
                    "source": "Wikimedia Commons",
                    "title": meta["title"],
                    "artist": meta["artist"] or "unknown",
                    "credit": meta["credit"] or None,
                    "license": meta["license"],
                    "license_url": meta["license_url"] or None,
                    "source_page": meta["description_url"],
                    "sha1": meta.get("sha1"),
                    "sha256_local": hashlib.sha256(src.read_bytes()).hexdigest(),
                    "fetched": TODAY,
                },
            }
        )

    for s in synth:
        pid = s["id"]
        products.append(
            {
                "id": pid,
                "name": f"{s['name']} (synthetic sample)",
                "category": f"Synthetic — {s['style']} texture",
                "colour_family": None,
                "finish": "rendered texture",
                "origin": None,
                "description": (
                    f"Synthetic {s['note']} generated deterministically "
                    f"(seed {s['seed']}) for this POC. This is NOT a real stone "
                    "product and does not represent actual CMC inventory."
                ),
                "image": s["file"],
                "is_synthetic": True,
                "provenance": {
                    "source": "Generated",
                    "generator": "scripts/generate_synthetic.py",
                    "seed": s["seed"],
                    "created": TODAY,
                },
            }
        )

    # mark sample-query products (strip shown on the UI as "try a reference")
    ids = {p["id"] for p in products}
    for sid in curated["sample_queries"]:
        if sid in ids:
            next(p for p in products if p["id"] == sid)["sample_query"] = True

    products_path = CAT / "products.json"
    products_path.write_text(json.dumps(products, indent=2, ensure_ascii=False))
    print(f"Catalogue: {len(products)} products -> {products_path}")

    # embed
    print("Loading CLIP (CPU) ...")
    emb = ImageEmbedder()
    vecs = np.zeros((len(products), 512), dtype=np.float32)
    for i, p in enumerate(products):
        vecs[i] = emb.encode_file(IMAGES / p["image"])
        print(f"  [{i+1}/{len(products)}] {p['id']} {p['name'][:45]}")
    out = CAT / "embeddings.npy"
    np.save(out, vecs)
    print(f"Embeddings: {vecs.shape} -> {out}")


if __name__ == "__main__":
    main()
