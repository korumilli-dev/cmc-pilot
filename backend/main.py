"""VEIN SEARCH — AI-powered marble discovery POC. FastAPI application."""
from __future__ import annotations

import pathlib
import time

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.core.catalog import Catalogue, Favourites, UploadError, validate_upload
from backend.core.embedder import ImageEmbedder
from backend.core.store import NumpyVectorStore

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CATALOGUE_IMAGES = DATA / "catalogue" / "images"
FRONTEND = ROOT / "frontend"

SCORE_EXPLANATION = (
    "Similarity is the cosine similarity between image embeddings (range -1 to 1). "
    "It is a visual-likeness ranking, NOT a probability or a match confidence. "
    "The score indicates how visually alike two images are in the model's "
    "embedding space; there is no statistical guarantee attached to it."
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global vector_store, catalogue, favourites
    try:
        vector_store = NumpyVectorStore(
            DATA / "catalogue" / "embeddings.npy",
            DATA / "catalogue" / "products.json",
        )
        catalogue = Catalogue(DATA / "catalogue" / "products.json", CATALOGUE_IMAGES)
        favourites = Favourites(DATA / "favourites.json")
    except FileNotFoundError as e:
        raise RuntimeError(
            "Catalogue index not found. Run: python scripts/build_index.py"
        ) from e
    embedder.model  # warm up model load (first call)
    yield


app = FastAPI(title="VEIN SEARCH", version="0.1.0", docs_url="/api/docs", lifespan=lifespan)

embedder = ImageEmbedder()
vector_store: NumpyVectorStore | None = None
catalogue: Catalogue | None = None
favourites: Favourites | None = None


def product_view(p: dict) -> dict:
    return {
        "id": p["id"],
        "name": p["name"],
        "category": p.get("category"),
        "colour_family": p.get("colour_family"),
        "finish": p.get("finish"),
        "origin": p.get("origin"),
        "description": p.get("description"),
        "image_url": f"/catalogue-images/{p['image']}",
        "is_synthetic": bool(p.get("is_synthetic")),
        "provenance": p.get("provenance"),
    }


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "products": len(catalogue.products) if catalogue else 0,
        "embedding_model": embedder.model_name,
        "vector_store": type(vector_store).__name__ if vector_store else None,
    }


@app.get("/api/products")
def list_products() -> dict:
    return {"products": [product_view(p) for p in catalogue.products]}


@app.get("/api/products/{product_id}")
def get_product(product_id: str) -> dict:
    p = catalogue.by_id(product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    return {"product": product_view(p)}


@app.get("/api/samples")
def sample_queries() -> dict:
    """A few held-out reference images users can try as demo uploads."""
    samples = [p for p in catalogue.products if p.get("sample_query")]
    return {"samples": [product_view(p) for p in samples]}


@app.post("/api/search")
async def search(file: UploadFile = File(...), k: int = 6) -> JSONResponse:
    started = time.perf_counter()
    data = await file.read()
    try:
        validate_upload(data)
    except UploadError as e:
        raise HTTPException(e.status_code, str(e)) from e
    try:
        query_vec = embedder.encode_bytes(data)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Embedding failed: {e}") from e

    k = max(1, min(int(k), 12))
    hits = vector_store.search(query_vec, k=k)
    results = []
    for hit in hits:
        p = catalogue.by_id(hit["id"])
        results.append(
            {
                **product_view(p),
                "similarity": round(hit["similarity"], 4),
            }
        )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return JSONResponse(
        {
            "results": results,
            "meta": {
                "query_filename": file.filename,
                "top_k": k,
                "elapsed_ms": elapsed_ms,
                "model": embedder.model_name,
                "store": type(vector_store).__name__,
                "score_explanation": SCORE_EXPLANATION,
            },
        }
    )


@app.get("/api/favourites")
def get_favourites() -> dict:
    ids = favourites.list()
    products = [product_view(catalogue.by_id(i)) for i in ids if catalogue.by_id(i)]
    return {"favourites": products}


@app.post("/api/favourites/{product_id}")
def add_favourite(product_id: str) -> dict:
    if not catalogue.by_id(product_id):
        raise HTTPException(404, "Product not found")
    added = favourites.add(product_id)
    return {"favourites": favourites.list(), "added": product_id if added else None}


@app.delete("/api/favourites/{product_id}")
def remove_favourite(product_id: str) -> dict:
    removed = favourites.remove(product_id)
    return {"favourites": favourites.list(), "removed": product_id if removed else None}


@app.get("/catalogue-images/{image_name}")
def catalogue_image(image_name: str) -> FileResponse:
    path = (CATALOGUE_IMAGES / pathlib.Path(image_name).name).resolve()
    if not path.is_file() or CATALOGUE_IMAGES.resolve() not in path.parents:
        raise HTTPException(404, "Image not found")
    return FileResponse(path)


app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
