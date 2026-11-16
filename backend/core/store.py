"""Vector storage & similarity search.

`VectorStore` is the interface; `NumpyVectorStore` is a small, dependency-free
implementation (brute-force cosine similarity over a NumPy matrix). At catalogue
scale (~50-5k items) this is fast (<1ms/query) and needs no extra infrastructure.

Swap-out point: FAISS / pgvector / Qdrant — implement VectorStore, change wiring
in backend/main.py. Embeddings and metadata stay portable.
"""
from __future__ import annotations

import json
import pathlib
from typing import Protocol

import numpy as np


class VectorStore(Protocol):
    def search(self, query_vec: np.ndarray, k: int = 6) -> list[dict]: ...


class NumpyVectorStore:
    """Loads products.json + embeddings.npy and brute-force cosine ranking."""

    def __init__(self, embeddings_path: pathlib.Path, products_path: pathlib.Path):
        data = np.load(embeddings_path)
        if data.ndim != 2 or data.dtype != np.float32:
            raise ValueError("embeddings must be a 2-D float32 array")
        self.embeddings = data
        products = json.loads(products_path.read_text(encoding="utf-8"))
        if len(products) != data.shape[0]:
            raise ValueError(
                f"product count ({len(products)}) != embedding rows ({data.shape[0]})"
            )
        self.products = products
        # rows are L2-normalised at build time; assert cheaply
        norms = np.linalg.norm(data, axis=1)
        if not np.allclose(norms, 1.0, atol=1e-3):
            raise ValueError("embedding rows must be L2-normalised")

    @property
    def dimension(self) -> int:
        return self.embeddings.shape[1]

    def search(self, query_vec: np.ndarray, k: int = 6) -> list[dict]:
        q = query_vec / max(np.linalg.norm(query_vec), 1e-9)
        sims = self.embeddings @ q  # cosine similarity, range [-1, 1]
        order = np.argsort(-sims)[:k]
        return [
            {
                "id": self.products[i]["id"],
                "similarity": float(sims[i]),
            }
            for i in order
        ]
