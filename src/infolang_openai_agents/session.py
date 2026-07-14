"""``InfoLangSession`` -- an OpenAI Agents SDK ``Session`` backed by InfoLang.

Maps one OpenAI Agents session onto one InfoLang namespace and implements the
four ``Session`` protocol methods (``get_items``, ``add_items``, ``pop_item``,
``clear_session``) on top of the ``infolang`` Python SDK's ``memory`` resource.

See the package README for the full ordering-semantics writeup; the short
version lives in :mod:`infolang_openai_agents._envelope`.
"""

from __future__ import annotations

import contextlib
from typing import Any

from agents.items import TResponseInputItem
from agents.memory.session import SessionABC
from agents.memory.session_settings import SessionSettings
from infolang import AsyncInfoLang
from infolang.errors import NotFoundError

from . import _envelope

DEFAULT_NAMESPACE_PREFIX = "oa-session-"
DEFAULT_MAX_ITEMS = 1000
DEFAULT_SOURCE = "openai-agents-sdk"


class InfoLangSession(SessionABC):
    """Store OpenAI Agents SDK conversation history in InfoLang memory.

    Each session's items live in their own InfoLang namespace: by default
    ``f"{namespace_prefix}{session_id}"`` (pass ``namespace=`` to override
    entirely, e.g. to share one namespace across session ids on purpose).

    Args:
        session_id: Unique identifier for the conversation session.
        client: An existing :class:`infolang.AsyncInfoLang` to reuse (its
            lifecycle is then the caller's responsibility). If omitted, a new
            client is constructed from ``client_kwargs`` (or the
            ``INFOLANG_API_KEY`` / ``INFOLANG_DEV_KEY`` environment) and owned
            by this session -- call :meth:`aclose` (or use ``async with``) to
            release it.
        namespace: Explicit InfoLang namespace to use instead of deriving one
            from ``session_id``.
        namespace_prefix: Prefix used to derive the namespace from
            ``session_id`` when ``namespace`` is not given.
        max_items: Upper bound on how many of a session's most-recent items
            this backend can see in one ``list_recent`` call. This is a real
            cap, not a soft hint -- see the README "Ordering semantics"
            section. Default 1000.
        source: ``source`` tag written on every stored memory, for
            provenance/filtering.
        session_settings: Optional default ``get_items`` limit, matching the
            ``agents`` SDK's other bundled ``Session`` implementations.
        **client_kwargs: Forwarded to ``AsyncInfoLang(...)`` when ``client``
            is not supplied (e.g. ``api_key=``, ``base_url=``).
    """

    def __init__(
        self,
        session_id: str,
        *,
        client: AsyncInfoLang | None = None,
        namespace: str | None = None,
        namespace_prefix: str = DEFAULT_NAMESPACE_PREFIX,
        max_items: int = DEFAULT_MAX_ITEMS,
        source: str = DEFAULT_SOURCE,
        session_settings: SessionSettings | None = None,
        **client_kwargs: Any,
    ) -> None:
        if max_items <= 0:
            raise ValueError("max_items must be positive")
        self.session_id = session_id
        self.session_settings = session_settings
        self.namespace = namespace or f"{namespace_prefix}{session_id}"
        self._max_items = max_items
        self._source = source
        self._owns_client = client is None
        self._client = client if client is not None else AsyncInfoLang(**client_kwargs)

    async def _fetch_records(self) -> list[tuple[str, str, dict[str, Any]]]:
        """Return ``(memory_id, seq, item)`` triples, sorted oldest -> newest.

        Records that aren't well-formed envelopes written by this library
        (foreign data in the namespace, or corruption) are silently skipped,
        mirroring how the bundled ``SQLiteSession`` drops unparsable rows
        instead of failing the whole read.
        """

        raw = await self._client.memory.list_recent(
            namespace=self.namespace, n=self._max_items
        )
        parsed: list[tuple[str, str, dict[str, Any]]] = []
        for record in raw:
            memory_id = _envelope.record_id(record)
            text = _envelope.record_text(record)
            if memory_id is None or text is None:
                continue
            decoded = _envelope.decode(text)
            if decoded is None:
                continue
            seq, item = decoded
            parsed.append((memory_id, seq, item))
        parsed.sort(key=lambda triple: triple[1])
        return parsed

    def _effective_limit(self, limit: int | None) -> int | None:
        if limit is not None:
            return limit
        if self.session_settings is not None:
            return self.session_settings.limit
        return None

    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        """Return this session's items in chronological (oldest-first) order.

        ``limit=None`` returns every item visible to this backend (see
        ``max_items`` in the constructor -- this is capped, not literally
        "all history" for very long sessions). A positive ``limit`` returns
        the latest ``limit`` items, still in chronological order, matching
        the ``Session`` protocol contract.
        """

        records = await self._fetch_records()
        items = [item for _, _, item in records]
        effective_limit = self._effective_limit(limit)
        if effective_limit is not None:
            items = items[-effective_limit:] if effective_limit > 0 else []
        return items  # type: ignore[return-value]

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        """Append items to the session, preserving the given order."""

        if not items:
            return
        seqs = _envelope.alloc_seqs(len(items))
        batch = [
            {"text": _envelope.encode(dict(item), seq), "source": self._source}
            for item, seq in zip(items, seqs, strict=True)
        ]
        await self._client.memory.remember_batch(batch, namespace=self.namespace)

    async def pop_item(self) -> TResponseInputItem | None:
        """Remove and return the most recently added item, or ``None``."""

        records = await self._fetch_records()
        if not records:
            return None
        memory_id, _, item = records[-1]
        # Already gone -- e.g. a concurrent pop_item/clear_session raced us
        # between the list and the delete. Treat as a successful pop of the
        # item we just read rather than raising.
        with contextlib.suppress(NotFoundError):
            await self._client.memory.forget(memory_id, namespace=self.namespace)
        return item  # type: ignore[return-value]

    async def clear_session(self) -> None:
        """Delete every item in this session's namespace. Idempotent."""

        await self._client.memory.reset_namespace(self.namespace)

    async def aclose(self) -> None:
        """Release the underlying InfoLang client, if this session owns it."""

        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> InfoLangSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
