"""Image embedding module.

Uses CLIP ViT-B/32 (via sentence-transformers) to produce a 512-dim normalised
embedding for any image. CPU-only, no GPU required.

Swap-out point: to move to a different model (e.g. a domain-tuned stone model),
implement the same `ImageEmbedder` interface.
"""
from __future__ import annotations

import io
import pathlib

import numpy as np
from PIL import Image, ImageFile, UnidentifiedImageError

# HEIC/HEIF (iPhone photos) support when pillow-heif is installed
try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:  # pragma: no cover - optional dependency
    HEIF_SUPPORTED = False

# Tolerate truncated uploads instead of crashing the worker
ImageFile.LOAD_TRUNCATED_IMAGES = False
Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard (~40MP)

MODEL_NAME = "clip-ViT-B-32"


class ImageEmbedder:
    """Lazy-loading singleton-style embedder."""

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self.model_name = model_name
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name, device="cpu")
        return self._model

    def preprocess(self, image: Image.Image) -> Image.Image:
        return image.convert("RGB")

    def encode_image(self, image: Image.Image) -> np.ndarray:
        """Return L2-normalised embedding (float32)."""
        im = self.preprocess(image)
        vec = self.model.encode([im], convert_to_numpy=True, normalize_embeddings=True)
        return vec[0].astype(np.float32)

    def encode_bytes(self, data: bytes) -> np.ndarray:
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
        except (UnidentifiedImageError, OSError) as e:
            raise ValueError(f"Could not decode image: {e}") from e
        return self.encode_image(image)

    def encode_file(self, path: str | pathlib.Path) -> np.ndarray:
        return self.encode_bytes(pathlib.Path(path).read_bytes())


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Both vectors must be L2-normalised; cosine sim == dot product."""
    return float(np.dot(a, b))
