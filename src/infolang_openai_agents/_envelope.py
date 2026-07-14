"""Wire format for conversation items stored in InfoLang memory.

The InfoLang runtime's ``list_recent`` route has no pagination cursor and does
not document a stable ordering guarantee for the records it returns (see
``GET /v1/memories`` in ``openapi/il-runtime.yaml`` in the ``infolang``
SDK repo -- the response schema is ``additionalProperties: true`` with no
``created_at`` / ``order`` contract).

To give :class:`~infolang_openai_agents.session.InfoLangSession` genuine
insertion-order semantics regardless of what order the server hands records
back in, every item is wrapped in a small envelope carrying a locally
generated, strictly monotonic sequence key before it is written with
``remember``/``remember_batch``. Reads sort by that key client-side instead of
trusting server order.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

_ENVELOPE_VERSION = 1

_seq_lock = threading.Lock()
_last_seq_ns = 0


def alloc_seqs(n: int) -> list[str]:
    """Allocate ``n`` sortable, strictly increasing sequence keys.

    Keys are derived from ``time.time_ns()`` with a process-local monotonic
    floor, so two calls from the same process never collide or go backwards
    even if the wall clock hasn't advanced between them. Ordering across
    *different* processes/hosts still relies on wall-clock agreement between
    writers -- fine for the common single-writer-per-session case, but worth
    knowing if multiple processes append to the same session concurrently.
    """

    if n <= 0:
        return []
    global _last_seq_ns
    with _seq_lock:
        base = max(time.time_ns(), _last_seq_ns + 1)
        values = [base + i for i in range(n)]
        _last_seq_ns = values[-1]
    # Zero-padded fixed width so lexicographic and numeric sort agree.
    return [f"{v:020d}" for v in values]


def encode(item: dict[str, Any], seq: str) -> str:
    """Serialize ``item`` plus its sequence key into the stored memory text."""

    return json.dumps(
        {"v": _ENVELOPE_VERSION, "seq": seq, "item": item},
        separators=(",", ":"),
    )


def decode(text: str) -> tuple[str, dict[str, Any]] | None:
    """Parse a stored memory's text back into ``(seq, item)``.

    Returns ``None`` for anything that isn't a well-formed envelope (e.g. a
    memory written by something other than this library, or corrupted data) so
    callers can skip it rather than fail the whole read.
    """

    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    seq = payload.get("seq")
    item = payload.get("item")
    if not isinstance(seq, str) or not isinstance(item, dict):
        return None
    return seq, item


def record_id(record: Any) -> str | None:
    """Extract a memory id from a raw ``list_recent`` record.

    The runtime's ``RecentResponse.memories[]`` schema is untyped
    (``additionalProperties: true``); mirrors the same key fallback the
    ``infolang`` SDK itself uses internally (``id`` / ``memory_id`` / ``i``).
    """

    if not isinstance(record, dict):
        return None
    for key in ("id", "memory_id", "i"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def record_text(record: Any) -> str | None:
    """Extract the stored text from a raw ``list_recent`` record."""

    if not isinstance(record, dict):
        return None
    for key in ("text", "t", "content"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None
