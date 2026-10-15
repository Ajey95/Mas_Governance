"""Supply guarded FunctionTools to an AutoGen agent."""

import asyncio

from masguardeval import FrameworkSession, FrameworkToolBlocked, make_autogen_tool

from _common import scenario, tool_specs, verify


async def run() -> None:
    reached: list[str] = []
    session = FrameworkSession(scenario(), framework_name="autogen")
    lookup, export = [make_autogen_tool(session, spec) for spec in tool_specs(reached)]
    assert "fictional metadata" in await lookup.run_json({"parameters": {"query": "release"}}, None)
    try:
        await export.run_json({"parameters": {}}, None)
    except FrameworkToolBlocked:
        pass
    else:
        raise AssertionError("Unapproved export passed the guard")
    verify(session.finish(), reached)


if __name__ == "__main__":
    asyncio.run(run())
