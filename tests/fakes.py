"""A tiny in-memory stand-in for the parts of Firestore the app uses."""

import copy
import itertools


class FakeSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return copy.deepcopy(self._data)


class FakeDocument:
    def __init__(self, store, doc_id):
        self._store = store
        self.id = doc_id

    def get(self):
        return FakeSnapshot(self.id, self._store.get(self.id))

    def set(self, data):
        self._store[self.id] = copy.deepcopy(data)

    def delete(self):
        self._store.pop(self.id, None)


class FakeCollection:
    def __init__(self, store, counter):
        self._store = store
        self._counter = counter

    def document(self, doc_id=None):
        return FakeDocument(self._store, doc_id or f"auto{next(self._counter)}")

    def stream(self):
        return [FakeSnapshot(k, v) for k, v in list(self._store.items())]


class FakeDb:
    def __init__(self):
        self.data: dict[str, dict] = {}
        self._counter = itertools.count(1)

    def collection(self, name):
        return FakeCollection(self.data.setdefault(name, {}), self._counter)
