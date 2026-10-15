"""Explicit export of completed MASGuardEval traces to LangSmith.

Export is opt in because trace inputs and tool parameters may contain private data.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .models import Scenario, Trace


class LangSmithExporter:
    def __init__(self, project_name: str, *, client: Any = None, run_tree_cls: Any = None) -> None:
        if not project_name.strip():
            raise ValueError("project_name is required")
        if run_tree_cls is None:
            try:
                from langsmith import RunTree
            except ImportError as exc:
                raise RuntimeError("Install backend[langsmith] to export traces") from exc
            run_tree_cls = RunTree
        self.project_name = project_name
        self.client = client
        self.run_tree_cls = run_tree_cls

    def export(self, scenario: Scenario, trace: Trace) -> str:
        if trace.scenario_id != scenario.scenario_id:
            raise ValueError("Trace and scenario IDs do not match")
        if trace.completed_at is None:
            raise ValueError("Only completed traces can be exported")
        kwargs = {
            "name": f"MASGuardEval {scenario.scenario_id} {trace.mode}",
            "run_type": "chain",
            "inputs": {"prompt": scenario.prompt, "scenario_id": scenario.scenario_id},
            "project_name": self.project_name,
            "start_time": datetime.fromisoformat(trace.started_at),
            "extra": {"metadata": {"masguardeval_trace_id": trace.trace_id, "mode": trace.mode,
                                   "risk_type": scenario.risk_type, "provenance": scenario.provenance}},
        }
        if self.client is not None:
            kwargs["ls_client"] = self.client
        root = self.run_tree_cls(**kwargs)
        root.post()
        nodes: dict[str, Any] = {}
        for span in trace.spans:
            parent = nodes.get(span.parent_span_id, root)
            span_start = datetime.fromisoformat(span.timestamp)
            child = parent.create_child(
                name=span.tool or span.agent,
                run_type="tool" if span.span_type == "tool_call" else "chain",
                inputs={"input": span.input, "parameters": span.tool_parameters},
                start_time=span_start,
                extra={"metadata": {
                    "masguardeval_span_id": span.span_id, "span_type": span.span_type,
                    "agent": span.agent, "role": span.role, "policy_decision": span.policy_decision,
                    "failure_label": span.failure_label, **span.metadata,
                }},
            )
            child.post()
            child.end(outputs={"output": span.output, "latency_ms": span.latency_ms,
                               "token_usage": span.token_usage},
                      end_time=span_start + timedelta(milliseconds=max(0, span.latency_ms)))
            child.patch()
            nodes[span.span_id] = child
        root.end(outputs={"final_response": trace.final_response, "blocked": trace.blocked,
                          "stop_reason": trace.stop_reason, "elapsed_ms": trace.elapsed_ms},
                 end_time=datetime.fromisoformat(trace.completed_at))
        root.patch()
        root.wait()
        return str(root.id)
