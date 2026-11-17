"""Upload validation tests."""
import pytest

from backend.core.catalog import UploadError, validate_upload


def test_empty_upload_rejected():
    with pytest.raises(UploadError):
        validate_upload(b"")


def test_unsupported_type_rejected():
    with pytest.raises(UploadError) as e:
        validate_upload(b"GIF89a" + b"\x00" * 32)
    assert e.value.status_code == 415


def test_random_bytes_rejected():
    with pytest.raises(UploadError):
        validate_upload(bytes(range(256)) * 16)


def test_too_large_rejected():
    with pytest.raises(UploadError) as e:
        validate_upload(b"\xff\xd8\xff" + b"\x00" * (10 * 1024 * 1024 + 1))
    assert e.value.status_code == 413


def test_jpeg_magic_ok():
    assert validate_upload(b"\xff\xd8\xff\xe0" + b"\x00" * 64) == "image/jpeg"


def test_png_magic_ok():
    assert validate_upload(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64) == "image/png"


def test_webp_magic_ok():
    assert validate_upload(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 64) == "image/webp"


def test_riff_non_webp_rejected():
    with pytest.raises(UploadError):
        validate_upload(b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 64)


def test_heic_magic_ok():
    assert validate_upload(b"\x00\x00\x00\x20ftypheic\x00\x00\x00\x00" + b"\x00" * 32) == "image/heic"


def test_heif_brand_ok():
    assert validate_upload(b"\x00\x00\x00\x20ftypmif1\x00\x00\x00\x00" + b"\x00" * 32) == "image/heic"


def test_mp4_rejected():
    # ftyp box but an iso-media video brand, not a still image
    with pytest.raises(UploadError) as e:
        validate_upload(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00" + b"\x00" * 32)
    assert e.value.status_code == 415
