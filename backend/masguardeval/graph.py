from __future__ import annotations

from typing import Any

from .models import Scenario, Span, Trace
from .propagation import PropagationAnalyzer


class AgentToolGraphBuilder:
    """Build the observed directed agent/tool graph with policy and failure evidence."""

    def build(self, scenario: Scenario, trace: Trace) -> dict[str, Any]:
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        by_span = {span.span_id: span for span in trace.spans}
        propagation = PropagationAnalyzer().analyze(trace)
        roots = set(propagation.root_span_ids)
        propagated = set(propagation.propagated_span_ids)

        def add_agent(name: str) -> str:
            key = f"agent:{name}"
            nodes.setdefault(key, {"id": key, "label": name, "kind": "agent", "is_root_failure": False})
            return key

        def add_tool(name: str) -> str:
            key = f"tool:{name}"
            policy = "blocked" if name in scenario.blocked_tools else "allowed" if name in scenario.allowed_tools else "unlisted"
            nodes.setdefault(key, {"id": key, "label": name, "kind": "tool", "policy": policy, "is_root_failure": False})
            return key

        def add_graph_node(namespace: str, name: str) -> str:
            key = f"graph:{namespace}:{name}"
            nodes.setdefault(key, {"id": key, "label": name, "kind": "graph_node", "namespace": namespace, "is_root_failure": False})
            return key

        for span in trace.spans:
            if span.span_type == "graph_node":
                add_graph_node(str(span.metadata.get("namespace", "")), span.agent)
            if span.span_type == "graph_transition":
                namespace = str(span.metadata.get("namespace", ""))
                source = add_graph_node(namespace, str(span.metadata["source"]))
                target = add_graph_node(namespace, str(span.metadata["target"]))
                edges.append({
                    "id": span.span_id, "source": source, "target": target,
                    "kind": "graph_transition", "span_id": span.span_id,
                    "timestamp": span.timestamp, "decision": None, "guard": None,
                    "failure_label": None, "is_root_failure": False,
                    "is_propagated_failure": False, "parameters": {},
                    "parent_span_id": span.parent_span_id,
                    "step": span.metadata.get("step"),
                })
                continue
            if span.span_type in {"agent_step", "inter_agent_message", "tool_call"} and span.agent != "Adapter":
                add_agent(span.agent)
                if span.span_id in roots:
                    nodes[f"agent:{span.agent}"]["is_root_failure"] = True
            if span.span_type == "tool_call" and span.tool and span.span_id in roots:
                nodes[add_tool(span.tool)]["is_root_failure"] = True
            if span.span_type == "guard_decision":
                if span.policy_decision not in {"BLOCK", "REQUIRE_APPROVAL"} or not span.tool:
                    continue
                source = add_agent(str(span.metadata.get("event_agent") or "Unknown agent"))
                target = add_tool(span.tool)
                kind = "blocked_tool_attempt" if span.policy_decision == "BLOCK" else "approval_required"
            elif span.span_type == "tool_call":
                source = add_agent(span.agent)
                target = add_tool(span.tool or "Unknown tool")
                kind = "tool_call"
            elif span.span_type == "inter_agent_message":
                recipient = span.metadata.get("recipient")
                if not recipient:
                    continue
                source = add_agent(span.agent)
                target = add_agent(str(recipient))
                kind = "inter_agent_message"
            elif span.span_type == "agent_step" and span.parent_span_id:
                parent = by_span.get(span.parent_span_id)
                if not parent or parent.span_type not in {"agent_step", "inter_agent_message"} or parent.agent == span.agent:
                    continue
                source = add_agent(parent.agent)
                target = add_agent(span.agent)
                kind = "control_flow"
            else:
                continue
            edges.append({
                "id": span.span_id,
                "source": source,
                "target": target,
                "kind": kind,
                "span_id": span.span_id,
                "timestamp": span.timestamp,
                "decision": span.policy_decision,
                "guard": span.agent if span.span_type == "guard_decision" else None,
                "failure_label": span.failure_label,
                "is_root_failure": span.span_id in roots,
                "is_propagated_failure": span.span_id in propagated,
                "parameters": span.tool_parameters if span.tool else {},
                "parent_span_id": span.parent_span_id,
            })

        for tool in scenario.allowed_tools + scenario.blocked_tools:
            add_tool(tool)
        return {
            "trace_id": trace.trace_id,
            "scenario_id": scenario.scenario_id,
            "mode": trace.mode,
            "nodes": list(nodes.values()),
            "edges": edges,
            "span_propagation": propagation.to_dict(),
        }
