"""A bounded fictional graph run for integration verification, not study evidence."""

from __future__ import annotations

from contextlib import nullcontext
from uuid import uuid4

from .frameworks import FrameworkSession, ToolSpec, make_langgraph_tool_node
from .langgraph_runtime import LangGraphRun, private_postgres_checkpointer, run_langgraph_graph
from .models import Scenario
from .store import RunStore


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
