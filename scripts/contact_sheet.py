#!/usr/bin/env python3
"""Build contact sheets of fetched Wikimedia candidates for curation review."""
import json
import math
import pathlib

from PIL import Image, ImageDraw

RAW = pathlib.Path("data/raw/wikimedia")
OUT = pathlib.Path("data/raw/contact")
OUT.mkdir(parents=True, exist_ok=True)
THUMB = 256
PER_SHEET = 24

index = json.loads((RAW / "index.json").read_text())
cols, rows = 6, 4

for sheet_i in range(math.ceil(len(index) / PER_SHEET)):
    batch = index[sheet_i * PER_SHEET:(sheet_i + 1) * PER_SHEET]
    sheet = Image.new("RGB", (cols * THUMB, rows * (THUMB + 22)), (20, 20, 24))
    d = ImageDraw.Draw(sheet)
    for j, meta in enumerate(batch):
        r, c = divmod(j, cols)
        f = RAW / f"{meta['pageid']}.{meta['title'].rsplit('.', 1)[-1].lower()}"
        if not f.exists():
            f = next(p for p in RAW.glob(f"{meta['pageid']}.*"))
        img = Image.open(f).convert("RGB")
        img.thumbnail((THUMB, THUMB))
        x, y = c * THUMB, r * (THUMB + 22)
        sheet.paste(img, (x + (THUMB - img.width) // 2, y + (THUMB - img.height) // 2))
        label = f"#{sheet_i*PER_SHEET+j}  {meta['license'][:12]}"
        d.text((x + 6, y + THUMB + 4), label, fill=(230, 230, 230))
    name = f"sheet_{sheet_i:02d}.png"
    sheet.save(OUT / name)
    print(f"{name}: items #{sheet_i*PER_SHEET}..#{sheet_i*PER_SHEET+len(batch)-1}")
