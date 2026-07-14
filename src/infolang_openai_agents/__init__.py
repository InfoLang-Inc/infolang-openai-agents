"""InfoLang memory ``Session`` for the OpenAI Agents SDK.

Quickstart::

    from agents import Agent, Runner
    from infolang_openai_agents import InfoLangSession

    session = InfoLangSession("user-42", api_key="il_live_...")
    agent = Agent(name="Assistant", instructions="Be concise.")
    result = await Runner.run(agent, "Remember that my favorite color is teal.", session=session)
"""

from __future__ import annotations

from ._version import __version__
from .session import (
    DEFAULT_MAX_ITEMS,
    DEFAULT_NAMESPACE_PREFIX,
    DEFAULT_SOURCE,
    InfoLangSession,
)

__all__ = [
    "__version__",
    "InfoLangSession",
    "DEFAULT_NAMESPACE_PREFIX",
    "DEFAULT_MAX_ITEMS",
    "DEFAULT_SOURCE",
]
