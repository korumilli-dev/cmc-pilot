"""End-to-end API tests (loads the real CLIP model — slow on first run)."""
import json

import numpy as np
import pytest


def _img_bytes(catalogue_images_dir, product_id):
    products = json.loads(
        (catalogue_images_dir.parent / "products.json").read_text()
    )
    fname = next(p["image"] for p in products if p["id"] == product_id)
    return (catalogue_images_dir / fname).read_bytes(), products


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["products"] >= 50
    assert "clip" in body["embedding_model"].lower()


def test_products_list(client):
    r = client.get("/api/products")
    assert r.status_code == 200
    products = r.json()["products"]
    assert len(products) >= 50
    ids = [p["id"] for p in products]
    assert len(ids) == len(set(ids))
    # every synthetic product must be clearly labelled
    for p in products:
        if p["is_synthetic"]:
            assert "synthetic" in p["name"].lower()


def test_product_detail(client):
    r = client.get("/api/products/WM-01")
    assert r.status_code == 200
    p = r.json()["product"]
    assert p["provenance"]["source"] == "Wikimedia Commons"
    assert p["provenance"]["license"]


def test_product_404(client):
    assert client.get("/api/products/NOPE").status_code == 404


def test_search_returns_six_sorted(client, catalogue_images_dir):
    data, products = _img_bytes(catalogue_images_dir, "WM-01")
    r = client.post(
        "/api/search",
        files={"file": ("query.jpg", data, "image/jpeg")},
    )
    assert r.status_code == 200
    body = r.json()
    results = body["results"]
    assert len(results) == 6
    sims = [x["similarity"] for x in results]
    assert sims == sorted(sims, reverse=True)
    assert all(-1.0 <= s <= 1.0 for s in sims)
    assert "not a probability" in body["meta"]["score_explanation"].lower()


def test_search_self_match_is_top1(client, catalogue_images_dir):
    """Querying with a catalogue image should rank that image first."""
    data, _ = _img_bytes(catalogue_images_dir, "WM-03")
    r = client.post("/api/search", files={"file": ("q.jpg", data, "image/jpeg")})
    results = r.json()["results"]
    assert results[0]["id"] == "WM-03"


def test_search_invalid_file(client):
    r = client.post(
        "/api/search",
        files={"file": ("x.bin", b"\x00\x01\x02\x03", "application/octet-stream")},
    )
    assert r.status_code == 415


def test_search_missing_file(client):
    r = client.post("/api/search")
    assert r.status_code in (400, 422)


def test_favourites_roundtrip(client):
    r = client.post("/api/favourites/SYN-02")
    assert r.status_code == 200
    assert "SYN-02" in r.json()["favourites"]
    listed = client.get("/api/favourites").json()["favourites"]
    assert any(p["id"] == "SYN-02" for p in listed)
    r = client.delete("/api/favourites/SYN-02")
    assert "SYN-02" in r.json()["removed"]
    listed = client.get("/api/favourites").json()["favourites"]
    assert not any(p["id"] == "SYN-02" for p in listed)


def test_favourite_unknown_product(client):
    assert client.post("/api/favourites/GHOST").status_code == 404


def test_synthetic_search_results_labelled(client, catalogue_images_dir):
    """A synthetic query should return its closest neighbours — including itself."""
    data, _ = _img_bytes(catalogue_images_dir, "SYN-07")
    r = client.post("/api/search", files={"file": ("q.png", data, "image/png")})
    results = r.json()["results"]
    assert results[0]["id"] == "SYN-07"
    assert results[0]["is_synthetic"] is True


def test_catalogue_images_served(client, catalogue_images_dir):
    r = client.get("/catalogue-images/" + json.loads(
        (catalogue_images_dir.parent / "products.json").read_text())[0]["image"])
    assert r.status_code == 200


def test_catalogue_image_traversal_blocked(client):
    assert client.get("/catalogue-images/..%2Ffavourites.json").status_code in (400, 404)
