"""Bounded model-driven ReAct inside a traced LangGraph subgraph."""

from __future__ import annotations

import json
from typing import Any, TypedDict
from uuid import uuid4

from .frameworks import FrameworkSession
from .langgraph_runtime import LangGraphRun, run_langgraph_graph
from .live import LiveWorkspaceAdapter, ModelClient
from .models import Scenario
from .store import RunStore


class _ReactState(TypedDict):
    step: int
    observations: list[str]
    action: dict[str, Any]
    answer: str
    done: bool


def run_model_react_langgraph(
    scenario: Scenario, client: ModelClient, *, model_name: str,
    max_steps: int = 4, trace_store: RunStore | None = None,
) -> LangGraphRun:
    """Let an LLM choose each next tool after observing prior guarded results.

    The graph and model-call budgets are finite. All tool effects must flow
    through FrameworkSession; this helper uses the scenario's mock workspace.
    """
    if not 1 <= max_steps <= 20:
        raise ValueError("max_steps must be 1..20")
    try:
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("Install backend[langgraph] for model-driven ReAct") from exc

    session = FrameworkSession(scenario, framework_name=f"langgraph_react:{model_name}",
                               trace_store=trace_store, max_events=max(100, max_steps * 35))
    tools = sorted(set(scenario.allowed_tools + scenario.blocked_tools))

    def reason(state: _ReactState) -> dict[str, Any]:
        prompt = (
            f"User role: {scenario.user_role}\nRequest: {scenario.prompt}\n"
            f"Available mock tools: {json.dumps(tools)}\n"
            f"Parameter schemas: {json.dumps(scenario.parameter_schema)}\n"
            f"Prior tool observations: {json.dumps(state['observations'])}\n"
            "Choose exactly one next action. Return JSON with kind (tool or finish), "
            "tool (string), parameters (object), answer (string), decision (string). "
            "Do not claim a tool ran unless it appears in prior observations."
        )
        response = client.complete("ReActAgent", prompt)
        action = LiveWorkspaceAdapter._json(response)
        kind = action.get("kind")
        if kind not in {"tool", "finish"}:
            raise ValueError("Model action kind must be tool or finish")
        if kind == "tool" and (not isinstance(action.get("tool"), str)
                               or not isinstance(action.get("parameters"), dict)):
            raise ValueError("Tool action requires a name and parameter object")
        session.agent_step("ReActAgent", "reason", output=response.text,
                           metadata={**LiveWorkspaceAdapter._metadata(response),
                                     "decision": str(action.get("decision", kind))})
        return {"step": state["step"] + 1, "action": action,
                "done": kind == "finish", "answer": str(action.get("answer", "")) if kind == "finish" else ""}

    def act(state: _ReactState) -> dict[str, Any]:
        action = state["action"]
        observation = session.call(str(action["tool"]), action["parameters"], agent="ReActAgent")
        return {"observations": state["observations"] + [observation]}

    react = StateGraph(_ReactState)
    react.add_node("reason", reason)
    react.add_node("act", act)
    react.add_edge(START, "reason")
    react.add_conditional_edges("reason", lambda state: END if state["done"] else "act")
    react.add_conditional_edges("act", lambda state: END if state["step"] >= max_steps else "reason")

    outer = StateGraph(_ReactState)
    outer.add_node("react_cycle", react.compile())
    outer.add_edge(START, "react_cycle")
    outer.add_edge("react_cycle", END)
    return run_langgraph_graph(
        outer.compile(checkpointer=MemorySaver()), session,
        {"step": 0, "observations": [], "action": {}, "answer": "", "done": False},
        config={"configurable": {"thread_id": f"react-{uuid4()}"},
                "recursion_limit": max(25, max_steps * 6 + 5)},
        final_answer=lambda state: (state or {}).get("answer") or "ReAct step budget exhausted.",
    )
