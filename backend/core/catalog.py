"""Catalogue access + upload validation."""
from __future__ import annotations

import json
import pathlib
from typing import Any

ALLOWED_MIME = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",  # iPhone photos
    "image/heif",
}
MAGIC_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"RIFF", "image/webp"),  # RIFF....WEBP checked more precisely below
)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# ISO-BMFF "ftyp" box: bytes 4-8 == "ftyp", brand at 8-12.
_HEIF_BRANDS = (b"heic", b"heix", b"heim", b"hevc", b"hevx", b"mif1", b"msf1", b"heis")


class UploadError(ValueError):
    """Raised for invalid uploads; maps to HTTP 400/415 in the API layer."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def sniff_mime(data: bytes) -> str | None:
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in _HEIF_BRANDS:
            return "image/heic"
        return None  # other ISO media (mp4, mov …) — not a still image
    for sig, mime in MAGIC_SIGNATURES:
        if data.startswith(sig):
            if mime == "image/webp":
                if data[8:12] == b"WEBP":
                    return mime
                return None
            return mime
    return None


def validate_upload(data: bytes) -> str:
    """Validate raw upload bytes, returns the detected mime type."""
    if len(data) == 0:
        raise UploadError("Empty file.", 400)
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError("File too large (max 10 MB).", 413)
    mime = sniff_mime(data)
    if mime is None:
        raise UploadError(
            "Unsupported file type. Please upload a JPEG, PNG or WebP image.", 415
        )
    return mime


class Catalogue:
    def __init__(self, products_path: pathlib.Path, images_dir: pathlib.Path) -> None:
        self.products_path = products_path
        self.images_dir = images_dir
        self.products: list[dict[str, Any]] = json.loads(
            products_path.read_text(encoding="utf-8")
        )
        self._by_id: dict[str, dict[str, Any]] = {p["id"]: p for p in self.products}

    def by_id(self, product_id: str) -> dict[str, Any] | None:
        return self._by_id.get(product_id)

    def image_path(self, product_id: str) -> pathlib.Path | None:
        product = self.by_id(product_id)
        if not product:
            return None
        path = (self.images_dir / product["image"]).resolve()
        if not path.is_file() or self.images_dir.resolve() not in path.parents:
            return None
        return path


class Favourites:
    """Simple JSON-file persistence (server-side) for the POC."""

    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        if not path.exists():
            path.write_text("[]", encoding="utf-8")

    def _read(self) -> list[str]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _write(self, ids: list[str]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(ids, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def list(self) -> list[str]:
        return self._read()

    def add(self, product_id: str) -> bool:
        ids = self._read()
        if product_id not in ids:
            ids.append(product_id)
            self._write(ids)
            return True
        return False

    def remove(self, product_id: str) -> bool:
        ids = self._read()
        if product_id in ids:
            ids.remove(product_id)
            self._write(ids)
            return True
        return False
