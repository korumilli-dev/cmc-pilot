#!/usr/bin/env python3
"""Generate synthetic marble/stone textures for the VEIN SEARCH POC.

Every generated image is clearly a synthetic stand-in, never a real product.
Deterministic per product (fixed seed) so the dataset is reproducible.

Run:  python scripts/generate_synthetic.py
Output: data/catalogue/images/syn_*.png + entries appended by build step
"""
import io
import pathlib

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = pathlib.Path("data/catalogue/images")
OUT.mkdir(parents=True, exist_ok=True)
SIZE = 1024


def fractal_noise(rng: np.ndarray, size: int, octaves: int = 6, persistence: float = 0.55):
    """Bilinear-interpolated value-noise fBm. `rng` is the noise grid source."""
    def layer(n):
        grid = rng.random((n, n))
        img = Image.fromarray((grid * 255).astype(np.uint8))
        return np.asarray(
            img.resize((size, size), Image.BILINEAR).filter(ImageFilter.GaussianBlur(1)),
            dtype=np.float64,
        ) / 255.0

    total = np.zeros((size, size))
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        total += amp * layer(4 * 2**o)
        norm += amp
        amp *= persistence
    return total / norm


def mix(a, b, t):
    return a + (b - a) * t[..., None] if t.ndim == 2 else a + (b - a) * t


def make_texture(seed: int, palette: dict, style: str) -> Image.Image:
    rng = np.random.default_rng(seed)
    size = SIZE
    n1 = fractal_noise(rng, size)
    n2 = fractal_noise(rng, size)

    x = np.linspace(0, 1, size)[None, :].repeat(size, 0)
    y = np.linspace(0, 1, size)[:, None].repeat(size, 1)

    if style == "veined":
        # domain-warped veins
        warp = (n1 - 0.5) * palette.get("warp", 0.35) + (n2 - 0.5) * 0.15
        freq = palette.get("vein_freq", 14.0)
        phase = 2 * np.pi * (freq * (x * 0.6 + y * 0.8 + warp * 1.4))
        vein = np.abs(np.sin(phase)) ** palette.get("vein_power", 8.0)
        vein = np.clip(vein, 0, 1)
        vein = (vein > 0.55).astype(float) * vein
        base = mix(
            np.array(palette["base"], float),
            np.array(palette["secondary"], float),
            np.clip(n1 * 1.2 - 0.1, 0, 1),
        )
        img = mix(base, np.array(palette["vein"], float), vein)
    elif style == "banded":
        # onyx / travertine-like horizontal bands
        bands = np.sin(
            2 * np.pi * (palette.get("band_freq", 9.0) * y + (n1 - 0.5) * palette.get("warp", 0.5))
        )
        t = (bands + 1) / 2
        base = mix(
            np.array(palette["base"], float),
            np.array(palette["secondary"], float),
            t**palette.get("band_power", 1.4),
        )
        # small pores for travertine feel
        pores = (n2 > 0.985).astype(float)
        img = mix(base, np.array(palette.get("vein", [80, 70, 60]), float), pores * 0.7)
    elif style == "speckled":
        # granite-like: coloured feldspar/quartz/mica grains
        grain = (fractal_noise(rng, size, octaves=3) > 0.5).astype(float)
        spot = (fractal_noise(rng, size, octaves=2) > 0.93).astype(float)
        base = mix(
            np.array(palette["base"], float),
            np.array(palette["secondary"], float),
            grain,
        )
        img = mix(base, np.array(palette["vein"], float), spot)
    else:
        raise ValueError(style)

    # subtle lighting/vignette so it reads as a photographed slab
    vig = 1 - 0.18 * (((x - 0.5) ** 2 + (y - 0.5) ** 2) * 2)
    img = np.clip(img * vig[..., None], 0, 255).astype(np.uint8)
    out = Image.fromarray(img)
    return out


PALETTES = [
    # name, style, palette
    ("Aegean Veil", "veined", dict(base=[236, 235, 230], secondary=[210, 208, 202], vein=[150, 152, 158], vein_freq=11, vein_power=7, warp=0.4)),
    ("Storm Cavern", "veined", dict(base=[52, 54, 60], secondary=[76, 78, 86], vein=[188, 184, 172], vein_freq=9, vein_power=5, warp=0.5)),
    ("Ember Drift", "veined", dict(base=[168, 96, 74], secondary=[142, 74, 58], vein=[226, 214, 198], vein_freq=8, vein_power=6, warp=0.45)),
    ("Verdant Terrace", "veined", dict(base=[84, 112, 92], secondary=[64, 92, 74], vein=[214, 220, 205], vein_freq=10, vein_power=6, warp=0.5)),
    ("Gilded Noon", "veined", dict(base=[36, 34, 36], secondary=[54, 50, 48], vein=[206, 168, 96], vein_freq=12, vein_power=8, warp=0.35)),
    ("Ivory Psalm", "veined", dict(base=[242, 238, 228], secondary=[226, 220, 208], vein=[176, 172, 164], vein_freq=13, vein_power=10, warp=0.3)),
    ("Rosetta Clay", "veined", dict(base=[212, 178, 164], secondary=[190, 150, 136], vein=[122, 92, 84], vein_freq=9, vein_power=6, warp=0.5)),
    ("Sapphire Lode", "veined", dict(base=[46, 62, 88], secondary=[64, 84, 112], vein=[222, 226, 232], vein_freq=10, vein_power=5, warp=0.55)),
    ("Desert Band", "banded", dict(base=[226, 206, 180], secondary=[196, 166, 136], vein=[110, 96, 84], band_freq=8, band_power=1.3, warp=0.5)),
    ("Onyx Cascade", "banded", dict(base=[238, 232, 222], secondary=[186, 170, 150], vein=[94, 84, 72], band_freq=11, band_power=1.6, warp=0.45)),
    ("Umber Strata", "banded", dict(base=[154, 122, 96], secondary=[120, 92, 72], vein=[70, 56, 46], band_freq=7, band_power=1.2, warp=0.6)),
    ("Jade Current", "banded", dict(base=[120, 148, 128], secondary=[88, 118, 100], vein=[230, 232, 224], band_freq=10, band_power=1.5, warp=0.4)),
    ("Glacier Salt", "speckled", dict(base=[228, 228, 224], secondary=[196, 198, 196], vein=[120, 122, 126])),
    ("Charcoal Fleck", "speckled", dict(base=[64, 64, 66], secondary=[92, 92, 94], vein=[182, 178, 170])),
    ("Rose Quartzite", "speckled", dict(base=[222, 198, 192], secondary=[198, 168, 160], vein=[246, 240, 236])),
    ("Moss Field", "speckled", dict(base=[132, 138, 118], secondary=[106, 112, 94], vein=[216, 214, 200])),
    ("Honey Grain", "speckled", dict(base=[218, 190, 148], secondary=[196, 164, 122], vein=[140, 112, 84])),
    ("Slate Mosaic", "speckled", dict(base=[110, 116, 124], secondary=[86, 92, 100], vein=[206, 208, 212])),
]

STYLE_NOTE = {
    "veined": "procedurally veined texture",
    "banded": "procedurally banded texture",
    "speckled": "procedurally speckled/granular texture",
}


def main():
    manifest = []
    for i, (name, style, pal) in enumerate(PALETTES):
        seed = 1000 + i * 7919
        img = make_texture(seed, pal, style)
        pid = f"SYN-{i + 1:02d}"
        fname = f"syn_{pid.lower().replace('-', '')}.png"
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        (OUT / fname).write_bytes(buf.getvalue())
        manifest.append(
            {
                "id": pid,
                "name": name,
                "style": style,
                "seed": seed,
                "file": fname,
                "note": STYLE_NOTE[style],
            }
        )
        print(f"  {pid} {name:16s} {style:9s} -> {fname}")
    pathlib.Path("data/raw/synthetic_manifest.json").write_text(
        __import__("json").dumps(manifest, indent=2)
    )
    print(f"\n{len(manifest)} synthetic textures -> {OUT}")


if __name__ == "__main__":
    main()
