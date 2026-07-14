# infolang-openai-agents

An [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) `Session`
implementation backed by [InfoLang](https://infolang.ai) semantic memory. Drop
`InfoLangSession` into any `Agent`/`Runner` call and conversation history is
stored in (and recalled from) InfoLang instead of living only in process
memory.

> Repository: `InfoLang-Inc/infolang-openai-agents`. Package:
> `infolang-openai-agents` (PyPI).

## Install

```bash
pip install infolang-openai-agents
```

This pulls in the `infolang` SDK (`>=0.2.0`) and `openai-agents` (`>=0.18.0`)
as dependencies.

## Quickstart

```python
import asyncio

from agents import Agent, Runner
from infolang_openai_agents import InfoLangSession


async def main() -> None:
    # INFOLANG_API_KEY resolved from the environment (or pass api_key="il_live_...").
    # session_id "demo-user-42" maps to the InfoLang namespace
    # "oa-session-demo-user-42" by default.
    async with InfoLangSession("demo-user-42") as session:
        agent = Agent(name="Assistant", instructions="Be concise.")

        result = await Runner.run(
            agent, "My favorite color is teal. Remember that.", session=session
        )
        print(result.final_output)

        # A second run against the same session recalls the earlier turn.
        result = await Runner.run(agent, "What's my favorite color?", session=session)
        print(result.final_output)


asyncio.run(main())
```

A full runnable version is in [`examples/quickstart.py`](examples/quickstart.py).

## How it maps onto InfoLang

- **One session = one InfoLang namespace.** By default the namespace is
  `f"{namespace_prefix}{session_id}"` (`namespace_prefix="oa-session-"`); pass
  `namespace=` to control it directly, e.g. to intentionally share one
  namespace across session ids.
- **Items are written with `remember_batch`.** Each `TResponseInputItem` is
  JSON-serialized and stored as the memory `text`, tagged with
  `source="openai-agents-sdk"` (override via `source=`).
- **Items are read with `list_recent`.** `pop_item`/`get_items` list the
  namespace's memories and delete via `forget`. `clear_session` uses
  `reset_namespace` (list + forget loop until empty).

## Ordering semantics — read this before relying on it

The InfoLang runtime's `GET /v1/memories` (`list_recent`) route has an
**untyped, undocumented response** (`additionalProperties: true` in the
runtime's OpenAPI spec, no `created_at` field, no ordering guarantee, and no
pagination cursor). Two tradeoffs follow directly from that, and this library
handles the first honestly and discloses the second rather than papering over
it:

1. **We do not trust server-side order.** Every item is wrapped in an
   envelope carrying a sequence key generated locally (`time.time_ns()` with a
   process-local monotonic floor, so it never collides or goes backwards
   within one process) before it's written. `get_items`/`pop_item` sort by
   that key, not by whatever order `list_recent` hands records back in. This
   gives genuine insertion-order semantics for the common case: one process
   (or several, on clocks that roughly agree) appending to a session.
   Cross-process ordering under significant clock skew between concurrent
   writers to the *same* session is the one case this doesn't fully solve —
   most agent sessions have a single writer, so this is rarely relevant.

2. **There is a real cap on how much history is visible, `max_items`
   (default 1000).** Because `list_recent` has no pagination cursor, this
   library cannot enumerate more than `max_items` records in one call without
   deleting as it goes (which is exactly what `reset_namespace`/
   `clear_session` does, and why `clear_session` can drain an
   arbitrarily large namespace but reads cannot). If a session accumulates
   more than `max_items` stored items, `get_items(limit=None)` will **not**
   return the full history — only the newest `max_items` are visible, silently
   omitting older ones (they still exist in InfoLang and remain queryable via
   `recall`/`investigate`, just not through this `Session`'s `get_items`).
   Raise `max_items` at construction time if your sessions run long:
   `InfoLangSession(session_id, max_items=5000)`.

3. **`pop_item` and `get_items` cost is `O(session size)`**, not `O(1)`,
   because both need the full (capped) listing to determine "most recent."
   Fine for typical agent conversation lengths; not a good fit for
   extremely chatty sessions with tight latency budgets on every turn.

If your use case needs strict, unbounded, cheap ordering guarantees, the
bundled `agents.memory.SQLiteSession` (backed by an `AUTOINCREMENT` primary
key) will always be more precise than any REST-backed implementation without
a native ordering/cursor primitive. `InfoLangSession` trades that off for
memory that's durable, shared, and recallable outside the `Session` protocol
too (e.g. via `client.recall(...)` for semantic search over the same items).

## Configuration

```python
InfoLangSession(
    session_id: str,
    *,
    client: AsyncInfoLang | None = None,      # reuse an existing client instead of owning one
    namespace: str | None = None,              # override the derived namespace entirely
    namespace_prefix: str = "oa-session-",
    max_items: int = 1000,
    source: str = "openai-agents-sdk",
    session_settings: SessionSettings | None = None,  # default get_items() limit
    **client_kwargs,                            # forwarded to AsyncInfoLang(...) if client= is omitted
)
```

Credentials, when `client=` is not supplied, resolve the same way the
`infolang` SDK always does: `api_key=`/`dev_key=`/`auth=` kwargs, or the
`INFOLANG_API_KEY` / `INFOLANG_DEV_KEY` / `INFOLANG_BASE_URL` environment
variables.

`InfoLangSession` owns (and closes) the `AsyncInfoLang` client it constructs
for itself; use `async with InfoLangSession(...) as session:` or call
`await session.aclose()` explicitly. If you pass `client=`, this session never
closes it — you own that client's lifecycle.

## Development

```bash
pip install -e ".[dev]"
ruff check .
mypy
pytest
```

Unit tests mock the HTTP layer (`respx`) against a small in-memory fake of
the `il-runtime` memory routes and cover all four `Session` methods plus edge
cases: empty session, `pop_item` on an empty session, `clear_session`
idempotency, `get_items(limit=0)`, records not written by this library, and a
concurrent-delete race on `pop_item`.

An optional live smoke test (`tests/test_live_smoke.py`) exercises the real
InfoLang API end to end. It's skipped unless `INFOLANG_API_KEY` is set, only
ever touches namespaces prefixed `ittest-openai-`, and cleans up after itself:

```bash
INFOLANG_API_KEY=il_live_... pytest tests/test_live_smoke.py -v
```

## Links

- [InfoLang docs](https://docs.infolang.ai)
- [InfoLang Python SDK](https://github.com/InfoLang-Inc/infolang-sdk-python)
- [OpenAI Agents SDK — Sessions](https://github.com/openai/openai-agents-python)

## License

Apache-2.0
