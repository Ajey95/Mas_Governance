"""Run a compiled LangGraph whose tool node is guarded by MASGuardEval."""

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from masguardeval import FrameworkSession, make_langgraph_tool_node, run_langgraph_graph

from _common import scenario, tool_specs


def main() -> None:
    reached: list[str] = []
    session = FrameworkSession(scenario(), framework_name="langgraph")
    node = make_langgraph_tool_node(session, list(tool_specs(reached)))
    builder = StateGraph(MessagesState)
    builder.add_node("tools", node)
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    graph = builder.compile()
    # Separate graph invocations keep the tool path serial and observable.
    first = run_langgraph_graph(graph, session, {"messages": [AIMessage(content="", tool_calls=[{
        "name": "metadata_lookup", "args": {"parameters": {"query": "release"}}, "id": "lookup-1",
    }])]})
    assert not first.trace.blocked
    # A session represents one trace. Create a second session for the blocked call.
    blocked_reached: list[str] = []
    blocked_session = FrameworkSession(scenario(), framework_name="langgraph")
    blocked_node = make_langgraph_tool_node(blocked_session, list(tool_specs(blocked_reached)))
    blocked_builder = StateGraph(MessagesState)
    blocked_builder.add_node("tools", blocked_node)
    blocked_builder.add_edge(START, "tools")
    blocked_builder.add_edge("tools", END)
    blocked = run_langgraph_graph(blocked_builder.compile(), blocked_session, {"messages": [
        AIMessage(content="", tool_calls=[{
            "name": "private_export", "args": {"parameters": {}}, "id": "export-1",
        }]),
    ]})
    assert reached == ["metadata_lookup"] and blocked_reached == []
    assert blocked.trace.blocked
    assert any(span.policy_decision == "BLOCK" for span in blocked.trace.spans)
    print(f"LangGraph traces {first.trace.trace_id} and {blocked.trace.trace_id}: tool boundary verified")


if __name__ == "__main__":
    main()
