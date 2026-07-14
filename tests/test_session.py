from __future__ import annotations

import respx
from agents.memory.session_settings import SessionSettings
from infolang import AsyncInfoLang

from infolang_openai_agents import DEFAULT_NAMESPACE_PREFIX, InfoLangSession
from tests.conftest import BASE_URL, FakeRuntime


def _make_session(session_id: str, **kwargs: object) -> InfoLangSession:
    client = AsyncInfoLang.from_api_key("il_live_test", base_url=BASE_URL)
    return InfoLangSession(session_id, client=client, **kwargs)  # type: ignore[arg-type]


# --- namespace derivation ----------------------------------------------------


def test_default_namespace_derivation() -> None:
    session = _make_session("abc123")
    assert session.namespace == f"{DEFAULT_NAMESPACE_PREFIX}abc123"


def test_custom_namespace_prefix() -> None:
    session = _make_session("abc123", namespace_prefix="myapp-")
    assert session.namespace == "myapp-abc123"


def test_explicit_namespace_override() -> None:
    session = _make_session("abc123", namespace="shared-ns")
    assert session.namespace == "shared-ns"


def test_max_items_must_be_positive() -> None:
    import pytest

    with pytest.raises(ValueError):
        _make_session("abc123", max_items=0)


# --- empty session -------------------------------------------------------------


@respx.mock
async def test_get_items_on_empty_session_returns_empty_list(runtime: FakeRuntime) -> None:
    runtime.register(respx)
    session = _make_session("empty-session")

    items = await session.get_items()

    assert items == []
    await session.aclose()


@respx.mock
async def test_pop_item_on_empty_session_returns_none_and_does_not_call_forget(
    runtime: FakeRuntime,
) -> None:
    runtime.register(respx)
    session = _make_session("empty-session")

    popped = await session.pop_item()

    assert popped is None
    assert runtime.forget_calls == 0
    await session.aclose()


# --- add_items / get_items ordering --------------------------------------------


@respx.mock
async def test_add_items_then_get_items_round_trips_in_order(runtime: FakeRuntime) -> None:
    runtime.register(respx)
    session = _make_session("chat-1")

    await session.add_items([{"role": "user", "content": "hello"}])
    await session.add_items([{"role": "assistant", "content": "hi there"}])
    await session.add_items(
        [
            {"role": "user", "content": "how are you"},
            {"role": "assistant", "content": "great, thanks"},
        ]
    )

    items = await session.get_items()

    assert [i["content"] for i in items] == [
        "hello",
        "hi there",
        "how are you",
        "great, thanks",
    ]
    # FakeRuntime.list_recent intentionally hands back reverse-of-insertion
    # order; the assertion above only passes if InfoLangSession re-sorts by
    # its own sequence key rather than trusting server order.
    await session.aclose()


@respx.mock
async def test_add_items_with_empty_list_is_a_no_op(runtime: FakeRuntime) -> None:
    runtime.register(respx)
    session = _make_session("chat-1")

    await session.add_items([])

    assert runtime.execute_calls == 0
    await session.aclose()


@respx.mock
async def test_get_items_limit_returns_latest_n_in_chronological_order(
    runtime: FakeRuntime,
) -> None:
    runtime.register(respx)
    session = _make_session("chat-1")
    await session.add_items([{"role": "user", "content": str(i)} for i in range(5)])

    items = await session.get_items(limit=2)

    assert [i["content"] for i in items] == ["3", "4"]
    await session.aclose()


@respx.mock
async def test_get_items_limit_zero_returns_empty_list(runtime: FakeRuntime) -> None:
    # Regression: a naive `items[-limit:]` slice with limit=0 returns the
    # WHOLE list in Python (since -0 == 0), not an empty one.
    runtime.register(respx)
    session = _make_session("chat-1")
    await session.add_items([{"role": "user", "content": "hello"}])

    items = await session.get_items(limit=0)

    assert items == []
    await session.aclose()


@respx.mock
async def test_get_items_limit_larger_than_history_returns_everything(
    runtime: FakeRuntime,
) -> None:
    runtime.register(respx)
    session = _make_session("chat-1")
    await session.add_items([{"role": "user", "content": "only one"}])

    items = await session.get_items(limit=50)

    assert [i["content"] for i in items] == ["only one"]
    await session.aclose()


@respx.mock
async def test_session_settings_default_limit_used_when_no_explicit_limit(
    runtime: FakeRuntime,
) -> None:
    runtime.register(respx)
    session = _make_session("chat-1", session_settings=SessionSettings(limit=1))
    await session.add_items([{"role": "user", "content": "a"}])
    await session.add_items([{"role": "user", "content": "b"}])

    items = await session.get_items()  # no explicit limit -> falls back to settings.limit

    assert [i["content"] for i in items] == ["b"]
    # an explicit limit still overrides session_settings
    items_all = await session.get_items(2)
    assert [i["content"] for i in items_all] == ["a", "b"]
    await session.aclose()


# --- pop_item -------------------------------------------------------------------


@respx.mock
async def test_pop_item_removes_and_returns_most_recent(runtime: FakeRuntime) -> None:
    runtime.register(respx)
    session = _make_session("chat-1")
    await session.add_items([{"role": "user", "content": "first"}])
    await session.add_items([{"role": "user", "content": "second"}])

    popped = await session.pop_item()

    assert popped is not None
    assert popped["content"] == "second"
    assert runtime.forget_calls == 1
    remaining = await session.get_items()
    assert [i["content"] for i in remaining] == ["first"]
    await session.aclose()


@respx.mock
async def test_pop_item_tolerates_already_deleted_memory(runtime: FakeRuntime) -> None:
    """If something else deleted the record between our list and our forget
    (e.g. a racing pop_item/clear_session), forget() 404s. pop_item should
    still return the item it read rather than raising NotFoundError."""

    runtime.register(respx)
    session = _make_session("chat-1")
    await session.add_items([{"role": "user", "content": "only"}])
    memory_id = next(iter(runtime.store[session.namespace]))
    runtime.poison_forget(memory_id)

    popped = await session.pop_item()

    assert popped is not None
    assert popped["content"] == "only"
    assert runtime.forget_calls == 1
    await session.aclose()


# --- clear_session ---------------------------------------------------------------


@respx.mock
async def test_clear_session_removes_all_items(runtime: FakeRuntime) -> None:
    runtime.register(respx)
    session = _make_session("chat-1")
    await session.add_items([{"role": "user", "content": "a"}])
    await session.add_items([{"role": "user", "content": "b"}])

    await session.clear_session()

    assert await session.get_items() == []
    await session.aclose()


@respx.mock
async def test_clear_session_is_idempotent(runtime: FakeRuntime) -> None:
    runtime.register(respx)
    session = _make_session("chat-1")
    await session.add_items([{"role": "user", "content": "a"}])

    await session.clear_session()
    await session.clear_session()  # must not raise on an already-empty namespace

    assert await session.get_items() == []
    await session.aclose()


# --- robustness against foreign / corrupted data -----------------------------


@respx.mock
async def test_get_items_skips_records_it_did_not_write(runtime: FakeRuntime) -> None:
    runtime.register(respx)
    session = _make_session("chat-1")
    runtime.seed(session.namespace, "not json at all")
    runtime.seed(session.namespace, '{"no_seq_or_item": true}')
    # A record with no recognizable id at all (not even "id"/"memory_id"/"i").
    runtime.store.setdefault(session.namespace, {})["orphan"] = {"text": "no id here"}
    await session.add_items([{"role": "user", "content": "real item"}])

    items = await session.get_items()

    assert [i["content"] for i in items] == ["real item"]
    await session.aclose()


# --- client ownership -------------------------------------------------------------


@respx.mock
async def test_aclose_closes_an_owned_client(runtime: FakeRuntime) -> None:
    runtime.register(respx)
    session = InfoLangSession("chat-1", api_key="il_live_test", base_url=BASE_URL)

    await session.aclose()

    assert session._client._transport._client.is_closed  # type: ignore[attr-defined]


@respx.mock
async def test_aclose_does_not_close_an_externally_supplied_client(
    runtime: FakeRuntime,
) -> None:
    runtime.register(respx)
    client = AsyncInfoLang.from_api_key("il_live_test", base_url=BASE_URL)
    session = InfoLangSession("chat-1", client=client)

    await session.aclose()

    assert not client._transport._client.is_closed  # type: ignore[attr-defined]
    await client.aclose()


@respx.mock
async def test_context_manager_closes_owned_client(runtime: FakeRuntime) -> None:
    runtime.register(respx)
    async with InfoLangSession("chat-1", api_key="il_live_test", base_url=BASE_URL) as session:
        await session.get_items()
    assert session._client._transport._client.is_closed  # type: ignore[attr-defined]
