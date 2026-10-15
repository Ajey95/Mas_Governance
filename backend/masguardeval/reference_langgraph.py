"""A bounded fictional graph run for integration verification, not study evidence."""

from __future__ import annotations

from contextlib import nullcontext
from typing import TypedDict
from uuid import uuid4

from .frameworks import FrameworkSession, ToolSpec, make_langgraph_tool_node
from .langgraph_runtime import LangGraphRun, private_postgres_checkpointer, run_langgraph_graph
from .models import Scenario
from .store import RunStore


class _ProbeState(TypedDict):
    count: int


class _NestedState(TypedDict):
    step: int
    round: int
    observations: list[str]


def run_nested_react_probe(
    scenario: Scenario, store: RunStore, *, blocked_branch: bool = False,
) -> LangGraphRun:
    """Run bounded, fictional ReAct cycles through two nested conditional graphs.

    This checks topology and the tool guard, not an LLM's reasoning quality.
    """
    try:
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("Install backend[langgraph] for the nested graph probe") from exc
    if scenario.scenario_id != "auth_001":
        raise ValueError("Nested graph probe supports only auth_001")
    session = FrameworkSession(scenario, framework_name="langgraph_nested_probe",
                               trace_store=store, max_events=300)

    def inner_graph(name: str):
        builder = StateGraph(_NestedState)
        builder.add_node("reason", lambda state: {"step": state["step"] + 1})

        def act(state: _NestedState):
            tool = ("mock_email_body_read" if blocked_branch and name == "graph_two"
                    and state["round"] == 1 else "mock_email_search")
            output = session.call(tool, {"date": "yesterday", "subject_only": True},
                                  agent=name)
            return {"observations": state["observations"] + [output]}

        builder.add_node("act", act)
        builder.add_edge(START, "reason")
        builder.add_conditional_edges("reason", lambda state: "act" if state["step"] <= 2 else END)
        builder.add_edge("act", "reason")
        return builder.compile()

    outer = StateGraph(_NestedState)
    outer.add_node("graph_one", inner_graph("graph_one"))
    outer.add_node("reset_budget", lambda state: {"step": 0})
    outer.add_node("graph_two", inner_graph("graph_two"))
    outer.add_node("next_round", lambda state: {"step": 0, "round": state["round"] + 1})
    outer.add_edge(START, "graph_one")
    outer.add_edge("graph_one", "reset_budget")
    outer.add_edge("reset_budget", "graph_two")
    outer.add_edge("graph_two", "next_round")
    outer.add_conditional_edges("next_round", lambda state: "graph_one" if state["round"] < 2 else END)
    graph = outer.compile(checkpointer=MemorySaver())
    return run_langgraph_graph(
        graph, session, {"step": 0, "round": 0, "observations": []},
        config={"configurable": {"thread_id": f"nested-probe-{uuid4()}"}, "recursion_limit": 80},
        final_answer="Fictional nested ReAct graph probe completed.",
    )


def run_reference_langgraph(scenario: Scenario, store: RunStore, *, database_url: str | None = None) -> LangGraphRun:
    try:
        from langchain_core.messages import AIMessage
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.graph import END, START, MessagesState, StateGraph
    except ImportError as exc:
        raise RuntimeError("Install backend[langgraph] for the reference graph") from exc

    if scenario.scenario_id != "auth_001":
        raise ValueError("Reference graph supports only auth_001")
    session = FrameworkSession(scenario, framework_name="langgraph_reference", trace_store=store)
    tools = make_langgraph_tool_node(session, [ToolSpec("mock_email_search", "Search fictional email metadata")])
    builder = StateGraph(MessagesState)
    builder.add_node("search_metadata", tools)
    builder.add_node("summarize", lambda state: {"messages": [AIMessage(content="Fictional metadata search completed.")]})
    builder.add_edge(START, "search_metadata")
    builder.add_edge("search_metadata", "summarize")
    builder.add_edge("summarize", END)
    checkpointer_context = private_postgres_checkpointer(database_url) if database_url else nullcontext(MemorySaver())
    with checkpointer_context as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        return run_langgraph_graph(
            graph, session,
            {"messages": [AIMessage(content="", tool_calls=[{
                "name": "mock_email_search", "args": {"parameters": {"date": "yesterday", "subject_only": True}},
                "id": "reference-search",
            }])]},
            config={"configurable": {"thread_id": f"reference-{uuid4()}"}},
            final_answer="Fictional LangGraph reference run completed.",
        )


def run_checkpoint_resume_probe(scenario: Scenario, store: RunStore, *, database_url: str | None = None) -> tuple[LangGraphRun, LangGraphRun]:
    """Verify resume across separate checkpointer connections using fixed data."""
    try:
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import Command, interrupt
    except ImportError as exc:
        raise RuntimeError("Install backend[langgraph] for the checkpoint probe") from exc

    def build(checkpointer):
        builder = StateGraph(_ProbeState)

        def wait_for_signal(state: _ProbeState):
            increment = interrupt("fictional checkpoint probe")
            return {"count": state["count"] + int(increment)}

        builder.add_node("wait_for_signal", wait_for_signal)
        builder.add_edge(START, "wait_for_signal")
        builder.add_edge("wait_for_signal", END)
        return builder.compile(checkpointer=checkpointer)

    thread_id = f"checkpoint-probe-{uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}
    memory = MemorySaver() if not database_url else None

    def context():
        return private_postgres_checkpointer(database_url) if database_url else nullcontext(memory)

    with context() as checkpointer:
        session = FrameworkSession(scenario, framework_name="langgraph_checkpoint_probe", trace_store=store)
        paused = run_langgraph_graph(build(checkpointer), session, {"count": 1}, config=config)
    if not paused.interrupted:
        raise RuntimeError("Checkpoint probe did not interrupt")
    with context() as checkpointer:
        session = FrameworkSession(scenario, framework_name="langgraph_checkpoint_probe", trace_store=store)
        resumed = run_langgraph_graph(build(checkpointer), session, Command(resume=2), config=config)
    if resumed.interrupted or resumed.state["count"] != 3:
        raise RuntimeError("Checkpoint probe failed to resume")
    return paused, resumed
