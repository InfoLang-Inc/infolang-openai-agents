"""Optional live smoke test against the real InfoLang API.

Skipped unless ``INFOLANG_API_KEY`` is set -- this is NOT part of the default
``pytest`` run and is excluded from the coverage gate. Only ever touches
namespaces prefixed ``ittest-openai-`` and cleans them up in a ``finally``
block regardless of pass/fail, so it is safe to run against a shared account.

Run it with::

    INFOLANG_API_KEY=il_live_... pytest tests/test_live_smoke.py -v
"""

from __future__ import annotations

import os
import uuid

import pytest

from infolang_openai_agents import InfoLangSession

pytestmark = pytest.mark.skipif(
    not os.environ.get("INFOLANG_API_KEY"),
    reason="live smoke test requires INFOLANG_API_KEY",
)


async def test_live_round_trip() -> None:
    session_id = f"smoke-{uuid.uuid4().hex[:8]}"
    session = InfoLangSession(session_id, namespace_prefix="ittest-openai-")
    try:
        assert await session.get_items() == []

        await session.add_items(
            [
                {"role": "user", "content": "InfoLang live smoke test message one"},
                {"role": "assistant", "content": "InfoLang live smoke test message two"},
            ]
        )

        items = await session.get_items()
        assert [i["content"] for i in items] == [
            "InfoLang live smoke test message one",
            "InfoLang live smoke test message two",
        ]

        popped = await session.pop_item()
        assert popped is not None
        assert popped["content"] == "InfoLang live smoke test message two"

        remaining = await session.get_items()
        assert [i["content"] for i in remaining] == [
            "InfoLang live smoke test message one",
        ]
    finally:
        await session.clear_session()
        await session.aclose()
