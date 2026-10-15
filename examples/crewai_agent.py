"""Supply guarded BaseTools to a CrewAI agent."""

from masguardeval import FrameworkSession, FrameworkToolBlocked, make_crewai_tool

from _common import scenario, tool_specs, verify


def main() -> None:
    reached: list[str] = []
    session = FrameworkSession(scenario(), framework_name="crewai")
    lookup, export = [make_crewai_tool(session, spec) for spec in tool_specs(reached)]
    assert "fictional metadata" in lookup.run(parameters={"query": "release"})
    try:
        export.run(parameters={})
    except FrameworkToolBlocked:
        pass
    else:
        raise AssertionError("Unapproved export passed the guard")
    verify(session.finish(), reached)


if __name__ == "__main__":
    main()
