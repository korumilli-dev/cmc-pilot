"""Vector store tests with synthetic embedding data."""
import json

import numpy as np
import pytest

from backend.core.store import NumpyVectorStore


@pytest.fixture()
def store(tmp_path):
    rng = np.random.default_rng(42)
    vecs = rng.normal(size=(10, 8)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    products = [{"id": f"P{i}"} for i in range(10)]
    e = tmp_path / "e.npy"
    p = tmp_path / "p.json"
    np.save(e, vecs)
    p.write_text(json.dumps(products))
    return NumpyVectorStore(e, p)


def test_search_returns_k_results(store):
    q = np.ones(8, dtype=np.float32)
    q /= np.linalg.norm(q)
    hits = store.search(q, k=3)
    assert len(hits) == 3


def test_search_similarity_range_and_order(store):
    q = np.ones(8, dtype=np.float32)
    q /= np.linalg.norm(q)
    hits = store.search(q, k=5)
    sims = [h["similarity"] for h in hits]
    assert sims == sorted(sims, reverse=True)
    assert all(-1.0 <= s <= 1.0 for s in sims)


def test_exact_query_returns_itself_first(store):
    target = store.embeddings[7]
    hits = store.search(target, k=1)
    assert hits[0]["id"] == "P7"
    assert hits[0]["similarity"] > 0.9999


def test_count_mismatch_raises(tmp_path):
    vecs = np.ones((4, 4), dtype=np.float32)
    np.save(tmp_path / "e.npy", vecs)
    (tmp_path / "p.json").write_text(json.dumps([{"id": "a"}, {"id": "b"}]))
    with pytest.raises(ValueError):
        NumpyVectorStore(tmp_path / "e.npy", tmp_path / "p.json")


def test_unnormalised_rows_rejected(tmp_path):
    vecs = np.ones((4, 4), dtype=np.float32)
    np.save(tmp_path / "e.npy", vecs)
    (tmp_path / "p.json").write_text(json.dumps([{"id": str(i)} for i in range(4)]))
    with pytest.raises(ValueError):
        NumpyVectorStore(tmp_path / "e.npy", tmp_path / "p.json")
