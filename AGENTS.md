# infolang-openai-agents — agent instructions

An OpenAI Agents SDK `Session` implementation backed by InfoLang memory.
Package name: `infolang-openai-agents`, import path `infolang_openai_agents`.

## Architecture

- `src/infolang_openai_agents/session.py` — `InfoLangSession`, implementing
  `agents.memory.session.SessionABC` (`get_items`, `add_items`, `pop_item`,
  `clear_session`) on top of `infolang.AsyncInfoLang`.
- `src/infolang_openai_agents/_envelope.py` — the stored-item wire format:
  wraps each item with a locally generated monotonic sequence key so ordering
  never depends on the InfoLang runtime's unspecified `list_recent` order.

## Contract

Depends on two upstream contracts, both external to this repo:

- The `infolang` Python SDK (`memory.remember_batch`, `memory.list_recent`,
  `memory.forget`, `memory.reset_namespace`) — see
  `infolang-sdk-python`'s `openapi/il-runtime.yaml`.
- The OpenAI Agents SDK's `Session` protocol (`agents.memory.session`) — read
  the installed `agents` package directly when in doubt; don't guess
  signatures from memory, it has changed across `openai-agents` releases.

## Rules

- Every session method must stay async — this backend always talks to
  InfoLang over HTTP via `AsyncInfoLang`.
- Never trust the order `list_recent` returns records in. Always sort by the
  envelope's `seq` key (see `_envelope.py`).
- `get_items`/`pop_item`/`clear_session` must degrade gracefully on an empty
  or not-yet-created namespace (empty list, `None`, no-op respectively) rather
  than raising.

## Commands

```bash
pip install -e ".[dev]"
ruff check .
mypy
pytest
```
