"""Driver's license photos for self-drive car rentals.

Private by design. The photo is kept as bytes in its own Firestore collection, keyed by the booking id:
- never inside the bookings document, which the admin browser listens to live (it would download every photo);
- never on a public URL (Cloudinary uploads in images.py are public, so licenses do not go there).

Firestore rules must deny all client access to this collection. Only the backend reads it, and only the
admin-only route /admin/bookings/<id>/license serves it. The photo is deleted when the booking is
completed, rejected or cancelled (see app.services.bookings.change_status).
"""

import io
import logging
from datetime import datetime, timezone

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.db import firebase
from app.db import repositories as repo
from app.services import images
from app.services.errors import FormError

log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # what the customer may send
MAX_PIXELS = 40_000_000  # refuse decompression bombs before decoding
MAX_STORED_BYTES = 900_000  # a Firestore document holds under 1 MiB
# (longest side in px, WebP quality): the first one that fits is kept. A license stays readable at all three.
ATTEMPTS = ((1600, 80), (1400, 65), (1200, 50))
CONTENT_TYPE = "image/webp"


class LicenseError(FormError):
    """An upload problem the customer can fix."""


def _unreadable() -> LicenseError:
    return LicenseError("That file could not be read as a photo. Try another one.")


def prepare(upload: UploadFile) -> bytes:
    """Checks the upload and returns it as a small WebP. Resizing and re-encoding also drops EXIF data (such as
    the GPS position of the photo) and fixes sideways phone photos."""
    data = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise LicenseError("The photo is larger than 5 MB. Use a smaller file.")
    if not images._is_image(data):  # the bytes decide, not the client-supplied name or content type
        raise LicenseError("The license must be a JPEG, PNG or WebP photo.")
    try:
        with Image.open(io.BytesIO(data)) as opened:
            if opened.width * opened.height > MAX_PIXELS:
                raise LicenseError("That photo is too large. Use a smaller one.")
            photo = ImageOps.exif_transpose(opened).convert("RGB")
    except LicenseError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise _unreadable() from None
    for side, quality in ATTEMPTS:
        smaller = photo.copy()
        smaller.thumbnail((side, side))
        out = io.BytesIO()
        smaller.save(out, format="WEBP", quality=quality)
        if out.tell() <= MAX_STORED_BYTES:
            return out.getvalue()
    raise LicenseError("That photo has too much detail to store. Try a simpler photo of the license.")


def save(booking_id: str, front: bytes, back: bytes | None = None) -> None:
    """Store both front and back of the license. Back is optional for backward compat."""
    firebase.get_db().collection(repo.LICENSES).document(booking_id).set({
        "front": front,
        "back": back,
        "content_type": CONTENT_TYPE,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


def load_front(booking_id: str) -> bytes | None:
    doc = firebase.get_db().collection(repo.LICENSES).document(booking_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    # Backward compat: old docs have "data" field, new ones have "front"
    return data.get("front") or data.get("data")


def load_back(booking_id: str) -> bytes | None:
    doc = firebase.get_db().collection(repo.LICENSES).document(booking_id).get()
    return doc.to_dict().get("back") if doc.exists else None


def load(booking_id: str) -> bytes | None:
    """Backward compat: returns front photo."""
    return load_front(booking_id)


def delete(booking_id: str) -> None:
    """Raises if Firestore fails, so a caller never reports a photo as gone when it is not."""
    firebase.get_db().collection(repo.LICENSES).document(booking_id).delete()
