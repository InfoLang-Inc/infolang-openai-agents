"""infolang-openai-agents — quickstart.

Wires an OpenAI Agents SDK `Agent` up to InfoLang-backed memory so
conversation history survives across process restarts (or is shared by
whatever else reads that InfoLang namespace).

Run:

    export OPENAI_API_KEY=sk-...
    export INFOLANG_API_KEY=il_live_...
    python examples/quickstart.py
"""

from __future__ import annotations

import asyncio

from agents import Agent, Runner

from infolang_openai_agents import InfoLangSession


async def main() -> None:
    # Credentials resolved from INFOLANG_API_KEY (or pass api_key=... here).
    # session_id "demo-user-42" maps to the InfoLang namespace
    # "oa-session-demo-user-42" by default.
    async with InfoLangSession("demo-user-42") as session:
        agent = Agent(name="Assistant", instructions="Be concise.")

        result = await Runner.run(
            agent,
            "My favorite color is teal. Remember that.",
            session=session,
        )
        print(result.final_output)

        # A second run against the same session recalls the earlier turn --
        # no manual history plumbing required.
        result = await Runner.run(
            agent,
            "What's my favorite color?",
            session=session,
        )
        print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
