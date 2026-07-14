from __future__ import annotations

import itertools
import json
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import pytest

BASE_URL = "https://api.test.infolang.ai"


class FakeRuntime:
    """Minimal in-memory stand-in for the il-runtime memory routes.

    Exercises the exact HTTP shapes ``InfoLangSession`` issues -- ``list_recent``
    via ``GET /v1/memories``, ``remember_batch`` via ``POST /v1/execute``,
    ``forget`` via ``DELETE /v1/memories/{id}`` -- against a real in-memory
    store, so tests cover end-to-end request/response shaping rather than
    mocking ``session.py``'s internals directly.

    ``list_recent`` deliberately returns records in reverse insertion order
    (the opposite of chronological) to prove ``InfoLangSession`` does not rely
    on server-side ordering -- it must reconstruct order from the sequence key
    it wrote into each item's envelope.
    """

    def __init__(self) -> None:
        self._next_id = itertools.count(1)
        self.store: dict[str, dict[str, dict[str, Any]]] = {}
        self.list_recent_calls = 0
        self.execute_calls = 0
        self.forget_calls = 0
        self._poisoned: set[str] = set()

    def list_recent(self, request: httpx.Request) -> httpx.Response:
        self.list_recent_calls += 1
        qs = parse_qs(urlparse(str(request.url)).query)
        namespace = qs.get("namespace", [None])[0]
        limit = int(qs.get("limit", ["10"])[0])
        records = list(self.store.get(namespace, {}).values())
        records = list(reversed(records))[:limit]
        return httpx.Response(200, json={"memories": records})

    def execute(self, request: httpx.Request) -> httpx.Response:
        self.execute_calls += 1
        body = json.loads(request.content)
        op = body["operations"][0]
        assert op["op"] == "remember_batch"
        args = op["args"]
        namespace = args["namespace"]
        results = []
        for item in args["items"]:
            mid = f"m{next(self._next_id)}"
            self.store.setdefault(namespace, {})[mid] = {"id": mid, "text": item["text"]}
            results.append({"id": mid})
        return httpx.Response(
            200,
            json={
                "results": [
                    {"op": "remember_batch", "ok": True, "payload": {"results": results}}
                ]
            },
        )

    def forget(self, request: httpx.Request) -> httpx.Response:
        self.forget_calls += 1
        memory_id = unquote(request.url.path.rsplit("/", 1)[-1])
        if memory_id in self._poisoned:
            # Simulate a race: something else already deleted this record
            # between our list and our delete. Deliberately does NOT remove
            # it from the store, so list_recent's view is unaffected -- only
            # this specific forget() call 404s.
            self._poisoned.discard(memory_id)
            return httpx.Response(404, json={"error": "no such memory"})
        for namespace_store in self.store.values():
            if memory_id in namespace_store:
                del namespace_store[memory_id]
                return httpx.Response(200, json={})
        return httpx.Response(404, json={"error": "no such memory"})

    def seed(self, namespace: str, text: str) -> str:
        """Directly insert a raw record, bypassing remember_batch.

        Used to simulate foreign / corrupted data already present in a
        namespace (not written by this library's envelope format).
        """

        mid = f"m{next(self._next_id)}"
        self.store.setdefault(namespace, {})[mid] = {"id": mid, "text": text}
        return mid

    def poison_forget(self, memory_id: str) -> None:
        """Make the next ``forget()`` for this id 404 without removing it.

        Simulates a race where the record was already deleted by something
        else between our ``list_recent`` read and our ``forget`` call.
        """

        self._poisoned.add(memory_id)

    def register(self, mock: Any) -> None:
        """Wire this store's handlers into an active respx router.

        Pass either the ``respx`` module itself (inside a ``@respx.mock``
        decorated test, calling ``respx.get``/``respx.post``/``respx.delete``
        registers against the currently active default router) or an explicit
        ``respx.MockRouter`` instance.
        """
        mock.get(url__regex=rf"{BASE_URL}/v1/memories(\?.*)?$").mock(
            side_effect=self.list_recent
        )
        mock.post(f"{BASE_URL}/v1/execute").mock(side_effect=self.execute)
        mock.delete(url__regex=rf"{BASE_URL}/v1/memories/.*").mock(side_effect=self.forget)


@pytest.fixture
def runtime() -> FakeRuntime:
    return FakeRuntime()
