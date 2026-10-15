from __future__ import annotations

from typing import TypedDict

import pytest

from masguardeval import FrameworkSession, GoldenDataset, ToolSpec, TraceStore, make_langgraph_tool_node, run_langgraph_graph
from masguardeval.reference_langgraph import run_checkpoint_resume_probe, run_reference_langgraph


pytest.importorskip("langgraph")
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command, interrupt


def _scenario():
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"
    return GoldenDataset.load(path).get("auth_001")


class NumberState(TypedDict):
    x: int
    secret: str


def test_records_executed_branch_and_checkpoints_without_state_values():
    builder = StateGraph(NumberState)
    builder.add_node("choose", lambda state: {"x": state["x"] + 1})
    builder.add_node("safe", lambda state: {"x": state["x"] + 10})
    builder.add_node("unused", lambda state: {"x": -1})
    builder.add_edge(START, "choose")
    builder.add_conditional_edges("choose", lambda state: "safe" if state["x"] > 0 else "unused")
    builder.add_edge("safe", END)
    builder.add_edge("unused", END)
    graph = builder.compile(checkpointer=MemorySaver())
    session = FrameworkSession(_scenario(), mode="guarded", framework_name="langgraph")
    result = run_langgraph_graph(graph, session, {"x": 1, "secret": "DO_NOT_COPY_STATE"},
                                 config={"configurable": {"thread_id": "branch-test"}})
    assert result.state["x"] == 12
    assert result.checkpoint_id
    assert not result.interrupted
    assert not result.trace.blocked
    assert {span.agent for span in result.trace.spans if span.span_type == "graph_node"} == {"choose", "safe"}
    assert all("DO_NOT_COPY_STATE" not in str(span.to_dict()) for span in result.trace.spans)
    routes = {(edge["source"], edge["target"]) for edge in session.graph()["edges"] if edge["kind"] == "graph_transition"}
    assert ("graph::choose", "graph::safe") in routes
    assert all("unused" not in source + target for source, target in routes)
    assert any(span.span_type == "graph_checkpoint" for span in result.trace.spans)
    assert not any(span.span_type == "guard_decision" for span in result.trace.spans)


def test_records_pause_and_resume_using_same_langgraph_thread():
    builder = StateGraph(NumberState)

    def approve(state):
        value = interrupt("fictional approval")
        return {"x": state["x"] + int(value)}

    builder.add_node("approve", approve)
    builder.add_edge(START, "approve")
    builder.add_edge("approve", END)
    graph = builder.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "resume-test"}}
    paused = run_langgraph_graph(graph, FrameworkSession(_scenario(), framework_name="langgraph"),
                                 {"x": 1, "secret": "private"}, config=config)
    assert paused.interrupted and paused.next_nodes == ("approve",)
    assert any(span.span_type == "graph_interrupt" for span in paused.trace.spans)
    resumed = run_langgraph_graph(graph, FrameworkSession(_scenario(), framework_name="langgraph"),
                                  Command(resume=2), config=config)
    assert resumed.state["x"] == 3
    assert not resumed.interrupted
    assert any(span.metadata.get("status") == "resume_requested" for span in resumed.trace.spans)


def test_guarded_tool_node_stops_graph_before_handler():
    called = []
    session = FrameworkSession(_scenario(), framework_name="langgraph")
    node = make_langgraph_tool_node(session, [ToolSpec(
        "mock_email_body_read", "Read email", lambda params, workspace: called.append(params) or "private",
    )])
    builder = StateGraph(MessagesState)
    builder.add_node("tools", node)
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    graph = builder.compile()
    result = run_langgraph_graph(graph, session, {"messages": [AIMessage(content="", tool_calls=[{
        "name": "mock_email_body_read", "args": {"parameters": {"date": "yesterday"}}, "id": "call-1",
    }])]})
    assert called == []
    assert result.trace.blocked
    assert any(span.policy_decision == "BLOCK" for span in result.trace.spans)


def test_reference_graph_persists_nodes_tool_and_checkpoint(tmp_path):
    store = TraceStore(tmp_path / "runs.sqlite3")
    run = run_reference_langgraph(_scenario(), store)
    saved = store.get(run.trace.trace_id)
    assert saved is not None
    assert run.checkpoint_id
    assert not run.trace.blocked
    assert any(span["span_type"] == "tool_call" for span in saved["spans"])
    assert any(span["span_type"] == "graph_transition" for span in saved["spans"])
    assert {span["agent"] for span in saved["spans"] if span["span_type"] == "graph_node"} == {"search_metadata", "summarize"}


def test_checkpoint_probe_resumes_in_separate_trace(tmp_path):
    store = TraceStore(tmp_path / "runs.sqlite3")
    paused, resumed = run_checkpoint_resume_probe(_scenario(), store)
    assert paused.interrupted and not resumed.interrupted
    assert paused.trace.trace_id != resumed.trace.trace_id
    assert resumed.state["count"] == 3
    assert store.get(paused.trace.trace_id) is not None
    assert store.get(resumed.trace.trace_id) is not None
