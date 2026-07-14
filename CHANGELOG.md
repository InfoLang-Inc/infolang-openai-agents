# Changelog

All notable changes to `infolang-openai-agents` are documented here. This
project adheres to [Semantic Versioning](https://semver.org).

## [0.1.0] - 2026-07-13

### Added
- Initial release: `InfoLangSession`, an OpenAI Agents SDK `Session`
  implementation backed by InfoLang memory (`infolang.AsyncInfoLang`).
- Maps one session onto one InfoLang namespace
  (`f"{namespace_prefix}{session_id}"` by default, or an explicit
  `namespace=`).
- `get_items`, `add_items`, `pop_item`, `clear_session` implemented on top of
  `remember_batch`, `list_recent`, `forget`, and `reset_namespace`.
- Client-side sequence-key envelope so item ordering does not depend on the
  InfoLang runtime's unspecified `list_recent` order.
- Optional `session_settings=SessionSettings(limit=...)` support, matching the
  `agents` SDK's other bundled `Session` implementations.
- Live smoke test (`tests/test_live_smoke.py`), gated on `INFOLANG_API_KEY`.
