"""Capture observed LangGraph execution without persisting graph state values.

Use a compiled graph and a FrameworkSession whose tools are wrapped by the
gateway. Graph observations describe topology; only wrapped tools are guarded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .frameworks import FrameworkSession, FrameworkToolBlocked
from .models import Trace


@dataclass(frozen=True)
class LangGraphRun:
    state: Any
    trace: Trace
    interrupted: bool
    checkpoint_id: str | None
    next_nodes: tuple[str, ...]


def _part(chunk: Any) -> tuple[tuple[str, ...], str, Any]:
    """Normalize LangGraph's v1 stream with or without subgraph namespaces."""
    if isinstance(chunk, dict) and {"type", "data"} <= chunk.keys():
        return tuple(chunk.get("ns") or ()), str(chunk["type"]), chunk["data"]
    if isinstance(chunk, tuple) and len(chunk) == 3:
        namespace, mode, data = chunk
        return tuple(namespace), str(mode), data
    if isinstance(chunk, tuple) and len(chunk) == 2:
        mode, data = chunk
        return (), str(mode), data
    raise ValueError("Unexpected LangGraph stream part")


def run_langgraph_graph(
    graph: Any,
    session: FrameworkSession,
    input: Any,
    *,
    config: dict[str, Any] | None = None,
    final_answer: str | None = None,
) -> LangGraphRun:
    """Run a compiled graph and record actual tasks, routes, checkpoints and pauses.

    A checkpointed graph requires ``configurable.thread_id``. Pass a LangGraph
    ``Command(resume=...)`` as input for a later invocation with the same thread.
    Each invocation gets its own MASGuardEval trace; the thread id joins them.
    """
    try:
        from langgraph.types import Command
    except ImportError as exc:
        raise RuntimeError("Install backend[langgraph] to trace a LangGraph run") from exc

    if not callable(getattr(graph, "stream", None)):
        raise TypeError("graph must be a compiled LangGraph with stream()")
    config = config or {}
    configurable = config.get("configurable") or {}
    thread_id = configurable.get("thread_id")
    if getattr(graph, "checkpointer", None) is not None and not thread_id:
        raise ValueError("Checkpointed LangGraph requires configurable.thread_id")

    static_edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}
    emitted_edges: set[tuple[tuple[str, ...], int, str, str]] = set()
    completed: dict[tuple[tuple[str, ...], int], list[str]] = {}
    started: dict[tuple[tuple[str, ...], str], str] = {}
    names: dict[tuple[tuple[str, ...], str], str] = {}
    state: Any = None
    interrupted = False
    checkpoint_id: str | None = None
    next_nodes: tuple[str, ...] = ()

    def meta(namespace: tuple[str, ...], **extra: Any) -> dict[str, Any]:
        return {"namespace": "/".join(namespace), "thread_id": str(thread_id) if thread_id else None, **extra}

    def route(namespace: tuple[str, ...], step: int, source: str, target: str, *, unambiguous: bool = False) -> None:
        if source == target or (not unambiguous and namespace == () and (source, target) not in static_edges):
            return
        key = (namespace, step, source, target)
        if key in emitted_edges:
            return
        emitted_edges.add(key)
        session.observe_graph("graph_transition", target, metadata=meta(namespace, source=source, target=target, step=step))

    if isinstance(input, Command):
        session.observe_graph("graph_interrupt", "resume", metadata=meta((), status="resume_requested"))

    stream = graph.stream(input, config=config, stream_mode=["values", "updates", "debug"], subgraphs=True)
    try:
        for chunk in stream:
            namespace, mode, data = _part(chunk)
            if mode == "values":
                state = data
            elif mode == "updates" and isinstance(data, dict) and "__interrupt__" in data:
                interrupted = True
                session.observe_graph("graph_interrupt", "pause", metadata=meta(namespace, status="paused", count=len(data["__interrupt__"])))
            elif mode != "debug" or not isinstance(data, dict):
                continue
            kind = data.get("type")
            payload = data.get("payload") or {}
            step = int(data.get("step", 0))
            if kind == "task":
                task_id = str(payload.get("id", ""))
                name = str(payload.get("name", ""))
                if name == "__start__":
                    continue
                names[(namespace, task_id)] = name
                prior = completed.get((namespace, step - 1), []) or (["__start__"] if step == 1 else [])
                if len(prior) == 1 or namespace == ():
                    for source in prior:
                        route(namespace, step, source, name, unambiguous=len(prior) == 1)
                value = payload.get("input")
                started[(namespace, task_id)] = session.observe_graph(
                    "graph_node", name,
                    metadata=meta(namespace, status="started", task_id=task_id, step=step,
                                  state_keys=sorted(value) if isinstance(value, dict) else []),
                )
            elif kind == "task_result":
                task_id = str(payload.get("id", ""))
                name = names.get((namespace, task_id), str(payload.get("name", "unknown")))
                errors = payload.get("error")
                interrupts = payload.get("interrupts") or []
                result = payload.get("result") or []
                keys = sorted(str(item[0]) for item in result if isinstance(item, (tuple, list)) and item)
                session.observe_graph(
                    "graph_node", name,
                    metadata=meta(namespace, status="interrupted" if interrupts else "error" if errors else "completed",
                                  task_id=task_id, step=step, result_keys=keys,
                                  error_type=type(errors).__name__ if errors else None,
                                  caused_by=started.get((namespace, task_id))),
                )
                if not errors and not interrupts:
                    completed.setdefault((namespace, step), []).append(name)
            elif kind == "checkpoint":
                checkpoint_config = (payload.get("config") or {}).get("configurable") or {}
                checkpoint_id = checkpoint_config.get("checkpoint_id") or checkpoint_id
                next_nodes = tuple(payload.get("next") or ())
                writes = (payload.get("metadata") or {}).get("writes")
                sources = tuple(writes) if isinstance(writes, dict) else ("__start__",) if step == 0 else ()
                targets = next_nodes or ("__end__",)
                for source in sources:
                    for target in targets:
                        if source != "__start__" or target != "__start__":
                            route(namespace, step + 1, str(source), str(target), unambiguous=len(sources) == 1)
                session.observe_graph(
                    "graph_checkpoint", "checkpoint",
                    metadata=meta(namespace, checkpoint_id=checkpoint_id, step=step,
                                  next_nodes=list(next_nodes),
                                  state_keys=sorted(payload.get("values") or {})),
                )
            if session.trace is not None and session.trace.blocked:
                break
    except FrameworkToolBlocked:
        pass  # The session already contains the guard decision and stop reason.
    except BaseException:
        session.finish("LangGraph execution failed")
        raise
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()

    if not interrupted and not checkpoint_id:
        for (namespace, step), nodes in completed.items():
            if not any(ns == namespace and later > step for ns, later in completed):
                for name in nodes:
                    route(namespace, step + 1, name, "__end__")
    trace = session.finish(final_answer or ("LangGraph interrupted; awaiting resume" if interrupted else "LangGraph completed"))
    return LangGraphRun(state, trace, interrupted, str(checkpoint_id) if checkpoint_id else None, next_nodes)
