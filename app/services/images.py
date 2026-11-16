"""Image upload to Cloudinary. The API secret stays on the server; the browser only sends
the file to this app, which validates it and uploads with a signed request.

Every image is stored as WebP, resized to fit 1600 px, so uploads stay light.
"""

import logging
from dataclasses import dataclass

import cloudinary
import cloudinary.exceptions
import cloudinary.uploader
from fastapi import UploadFile

from app.core import config
from app.services.errors import FormError

log = logging.getLogger(__name__)

MAX_BYTES = 5 * 1024 * 1024
MAX_SIDE = 1600


class ImageError(FormError):
    """An upload problem the admin can fix."""


@dataclass(frozen=True)
class UploadedImage:
    url: str
    public_id: str


def _is_image(data: bytes) -> bool:
    # Check the bytes, not the client-supplied content type: JPEG, PNG or WebP only.
    return (
        data.startswith(b"\xff\xd8\xff")
        or data.startswith(b"\x89PNG\r\n\x1a\n")
        or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
    )


def _configure() -> None:
    c = config.integrations
    cloudinary.config(cloud_name=c.cloudinary_cloud_name, api_key=c.cloudinary_api_key,
                      api_secret=c.cloudinary_api_secret, secure=True)


def upload(file: UploadFile, folder: str) -> UploadedImage:
    if not config.integrations.cloudinary_ready:
        raise ImageError("Image upload is not set up yet. Add the Cloudinary values to .env.")
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ImageError("The image is larger than 5 MB. Use a smaller file.")
    if not _is_image(data):
        raise ImageError("The file must be a JPEG, PNG or WebP image.")
    _configure()
    try:
        result = cloudinary.uploader.upload(
            data,
            folder=f"bless/{folder}",
            resource_type="image",
            format="webp",
            transformation=[{"width": MAX_SIDE, "height": MAX_SIDE, "crop": "limit", "quality": "auto"}],
        )
    except cloudinary.exceptions.Error:
        log.exception("Cloudinary upload failed")
        raise ImageError("The image could not be uploaded. Try again.") from None
    if result.get("format") != "webp":
        log.warning("Cloudinary stored %s as %s, not webp", result.get("public_id"), result.get("format"))
    return UploadedImage(url=result["secure_url"], public_id=result["public_id"])


def delete(public_id: str | None) -> None:
    """Best effort: a failed delete leaves an orphan image but must not block the admin."""
    if not public_id or not config.integrations.cloudinary_ready:
        return
    _configure()
    try:
        cloudinary.uploader.destroy(public_id, invalidate=True)
    except cloudinary.exceptions.Error:
        log.exception("Could not delete Cloudinary image %s", public_id)
