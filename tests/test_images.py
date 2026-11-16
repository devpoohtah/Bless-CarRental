"""Image upload rules. Cloudinary itself is replaced by a fake; nothing leaves the machine."""

import io
from dataclasses import replace

import cloudinary.exceptions
import pytest
from fastapi import UploadFile

from app.core import config
from app.services import images

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 100


def upload_file(data: bytes, name="photo.jpg") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name)


@pytest.fixture
def cloudinary_ready(monkeypatch):
    monkeypatch.setattr(config, "integrations", replace(
        config.integrations, cloudinary_cloud_name="demo", cloudinary_api_key="key", cloudinary_api_secret="secret"))
    calls = []

    def fake_upload(data, **options):
        calls.append((data, options))
        return {"secure_url": "https://res.cloudinary.com/demo/image/upload/v1/bless/cars/x.webp",
                "public_id": "bless/cars/x", "format": "webp"}

    monkeypatch.setattr(images.cloudinary.uploader, "upload", fake_upload)
    return calls


def test_upload_requires_cloudinary_to_be_configured():
    with pytest.raises(images.ImageError, match="not set up"):
        images.upload(upload_file(JPEG), "cars")


@pytest.mark.parametrize("data", [JPEG, PNG, WEBP])
def test_accepts_jpeg_png_and_webp_and_converts_to_webp(cloudinary_ready, data):
    result = images.upload(upload_file(data), "cars")
    assert result.url.startswith("https://") and result.public_id == "bless/cars/x"
    options = cloudinary_ready[0][1]
    assert options["format"] == "webp" and options["folder"] == "bless/cars"
    assert options["transformation"][0]["crop"] == "limit" and options["transformation"][0]["width"] == 1600


def test_rejects_non_images_even_when_named_like_one(cloudinary_ready):
    with pytest.raises(images.ImageError, match="JPEG, PNG or WebP"):
        images.upload(upload_file(b"<?php echo 1; ?>", "evil.jpg"), "cars")
    assert cloudinary_ready == []


def test_rejects_files_over_five_megabytes(cloudinary_ready):
    with pytest.raises(images.ImageError, match="5 MB"):
        images.upload(upload_file(JPEG + b"0" * images.MAX_BYTES), "cars")
    assert cloudinary_ready == []


def test_cloudinary_failure_becomes_a_friendly_error(cloudinary_ready, monkeypatch):
    def boom(data, **options):
        raise cloudinary.exceptions.Error("quota")
    monkeypatch.setattr(images.cloudinary.uploader, "upload", boom)
    with pytest.raises(images.ImageError, match="could not be uploaded"):
        images.upload(upload_file(JPEG), "cars")


def test_delete_is_best_effort(cloudinary_ready, monkeypatch):
    destroyed = []
    monkeypatch.setattr(images.cloudinary.uploader, "destroy", lambda pid, **kw: destroyed.append(pid))
    images.delete(None)
    images.delete("bless/cars/x")
    assert destroyed == ["bless/cars/x"]

    def boom(pid, **kw):
        raise cloudinary.exceptions.Error("down")
    monkeypatch.setattr(images.cloudinary.uploader, "destroy", boom)
    images.delete("bless/cars/x")  # must not raise
