"""Supply only guarded StructuredTools to a LangChain agent."""

from masguardeval import FrameworkSession, FrameworkToolBlocked, make_langchain_tool

from _common import scenario, tool_specs, verify


def main() -> None:
    reached: list[str] = []
    session = FrameworkSession(scenario(), framework_name="langchain")
    lookup, export = [make_langchain_tool(session, spec) for spec in tool_specs(reached)]
    assert "fictional metadata" in lookup.invoke({"parameters": {"query": "release"}})
    try:
        export.invoke({"parameters": {}})
    except FrameworkToolBlocked:
        pass
    else:
        raise AssertionError("Unapproved export passed the guard")
    verify(session.finish(), reached)


if __name__ == "__main__":
    main()
