import asyncio
from pathlib import Path

import pytest

from masguardeval import (
    FrameworkSession, FrameworkToolBlocked, GoldenDataset, ToolSpec,
    make_autogen_tool, make_crewai_tool, make_langchain_tool, make_langgraph_tool_node,
)


DATASET = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


def test_framework_session_blocks_before_handler_and_records_graph():
    scenario = GoldenDataset.load(DATASET).get("auth_001")
    reached = []
    session = FrameworkSession(scenario, framework_name="test_framework")
    session.register_tool(ToolSpec("mock_email_body_read", "Read email", lambda params, workspace: reached.append(params) or "private"))
    session.agent_step("Planner", "consider_request", output="read email")
    session.message("Planner", "Executor", "try email read")
    with pytest.raises(FrameworkToolBlocked):
        session.call("mock_email_body_read", {"date": "yesterday"}, agent="Executor")
    trace = session.finish()
    assert trace.blocked and reached == []
    assert any(span.policy_decision == "BLOCK" for span in trace.spans)
    assert any(edge["kind"] == "inter_agent_message" for edge in session.graph()["edges"])
    assert session.metrics()["RSS"]["score"] == 1


def test_framework_session_baseline_executes_handler_once_and_returns_feedback():
    scenario = GoldenDataset.load(DATASET).get("auth_001")
    reached = []
    with FrameworkSession(scenario, mode="baseline") as session:
        session.register_tool(ToolSpec("mock_email_body_read", "Read email", lambda params, workspace: reached.append(params) or "real feedback"))
        assert session.call("mock_email_body_read", {"date": "yesterday"}) == "real feedback"
        assert asyncio.run(session.acall("mock_email_body_read", {"date": "today"})) == "real feedback"
        trace = session.finish("Agent final response")
    assert len(reached) == 2
    assert trace.final_response == "Agent final response"
    assert sum(span.span_type == "tool_call" for span in trace.spans) == 2


def test_native_langchain_tool_and_langgraph_node_use_gateway():
    scenario = GoldenDataset.load(DATASET).get("auth_001")
    session = FrameworkSession(scenario, mode="baseline")
    tool = make_langchain_tool(session, ToolSpec("mock_email_body_read", "Read email body"), agent="ChainWorker")
    assert "Private email body" in tool.invoke({"parameters": {"date": "yesterday"}})
    assert any(span.agent == "ChainWorker" and span.span_type == "tool_call" for span in session.finish().spans)

    graph_session = FrameworkSession(scenario, mode="guarded")
    node = make_langgraph_tool_node(graph_session, [ToolSpec("mock_email_body_read", "Read email body")])
    assert node is not None
    wrapped = node.tools_by_name["mock_email_body_read"]
    with pytest.raises(FrameworkToolBlocked):
        wrapped.invoke({"parameters": {"date": "yesterday"}})
    assert graph_session.finish().blocked


def test_langgraph_compiled_graph_executes_wrapped_tool():
    pytest.importorskip("langgraph")
    from langchain_core.messages import AIMessage
    from langgraph.graph import END, START, MessagesState, StateGraph

    scenario = GoldenDataset.load(DATASET).get("auth_001")
    session = FrameworkSession(scenario, mode="baseline")
    node = make_langgraph_tool_node(session, [ToolSpec("mock_email_body_read", "Read email body")])
    graph = StateGraph(MessagesState)
    graph.add_node("tools", node)
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    result = graph.compile().invoke({"messages": [AIMessage(content="", tool_calls=[{
        "name": "mock_email_body_read", "args": {"parameters": {"date": "yesterday"}}, "id": "call-1",
    }])]})
    assert "Private email body" in result["messages"][-1].content
    assert any(span.span_type == "tool_call" for span in session.finish().spans)


def test_autogen_function_tool_runs_through_guard_boundary():
    pytest.importorskip("autogen_core")
    scenario = GoldenDataset.load(DATASET).get("auth_001")
    called = []
    session = FrameworkSession(scenario, mode="baseline")
    tool = make_autogen_tool(session, ToolSpec("mock_email_body_read", "Read email body", lambda params, _: called.append(params) or "ok"))
    assert asyncio.run(tool.run_json({"parameters": {"date": "yesterday"}}, None)) == "ok"
    assert called == [{"date": "yesterday"}]
    assert not session.finish().blocked


def test_crewai_base_tool_runs_through_guard_boundary():
    pytest.importorskip("crewai")
    scenario = GoldenDataset.load(DATASET).get("auth_001")
    called = []
    session = FrameworkSession(scenario, mode="guarded")
    tool = make_crewai_tool(session, ToolSpec("mock_email_body_read", "Read email body", lambda params, _: called.append(params) or "private"))
    with pytest.raises(FrameworkToolBlocked):
        tool.run(parameters={"date": "yesterday"})
    assert called == []
    assert session.finish().blocked
