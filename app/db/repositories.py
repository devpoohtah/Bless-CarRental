"""Firestore reads and writes. One function set for every collection.

Documents hold the Pydantic model fields without the id; the Firestore document id is the
model id. Dates are stored as ISO strings (model_dump(mode="json")), which Pydantic parses
back on read. A document that fails validation is logged and skipped so one bad hand-edited
record cannot take a whole page down.
"""

import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.db import firebase

log = logging.getLogger(__name__)

CARS = "cars"
TOURS = "tours"
BOOKINGS = "bookings"

M = TypeVar("M", bound=BaseModel)


def _parse(model: type[M], doc) -> M | None:
    try:
        return model(**{**doc.to_dict(), "id": doc.id})
    except ValidationError:
        log.warning("Skipping invalid document %s", doc.reference.path if hasattr(doc, "reference") else doc.id,
                    exc_info=True)
        return None


def list_all(collection: str, model: type[M]) -> list[M]:
    docs = firebase.get_db().collection(collection).stream()
    return [item for item in (_parse(model, doc) for doc in docs) if item is not None]


def get_one(collection: str, doc_id: str, model: type[M]) -> M | None:
    doc = firebase.get_db().collection(collection).document(doc_id).get()
    return _parse(model, doc) if doc.exists else None


def save(collection: str, item: BaseModel, doc_id: str | None = None) -> str:
    """Create (no doc_id: Firestore picks one) or replace a document. Returns its id."""
    col = firebase.get_db().collection(collection)
    ref = col.document(doc_id) if doc_id else col.document()
    ref.set(item.model_dump(mode="json", exclude={"id"}))
    return ref.id


def delete(collection: str, doc_id: str) -> None:
    firebase.get_db().collection(collection).document(doc_id).delete()
