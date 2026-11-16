"""Shared fixtures: one FastAPI TestClient for the session (model load is slow)."""
import pathlib
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    import backend.main as main

    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="session")
def catalogue_images_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1] / "data" / "catalogue" / "images"
