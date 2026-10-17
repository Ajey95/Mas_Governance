"""A reproducible, evidence-linked report for one recorded agent run."""

from __future__ import annotations

import hashlib
import html
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from . import __version__
from .findings import analyze_trace
from .graph import AgentToolGraphBuilder
from .metrics import MetricEngine, recommendations_for
from .models import Scenario, Trace


def _digest(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_trace(scenario: Scenario, trace: Trace) -> None:
    if scenario.scenario_id != trace.scenario_id:
        raise ValueError("Scenario and trace IDs do not match")
    positions: dict[str, int] = {}
    for index, span in enumerate(trace.spans):
        if not span.span_id or span.span_id in positions:
            raise ValueError("Trace has an empty or duplicate span ID")
        if span.trace_id != trace.trace_id:
            raise ValueError(f"Span {span.span_id} belongs to a different trace")
        positions[span.span_id] = index
    for index, span in enumerate(trace.spans):
        for label, parent in (("parent", span.parent_span_id),
                              ("causal dependency", span.metadata.get("causal_parent_span_id"))):
            if parent is not None and (not isinstance(parent, str) or positions.get(parent, index) >= index):
                raise ValueError(f"Span {span.span_id} has an invalid {label} span ID")


def build_trace_report(
    scenario: Scenario, trace: Trace, *, adapter: str = "unknown",
    execution_kind: str = "unknown", source: str = "unknown", source_sha256: str | None = None,
) -> dict[str, Any]:
    """Recompute all derived evidence; ignore metrics or graphs in an input wrapper."""
    _check_trace(scenario, trace)
    scenario_snapshot = scenario.to_dict()
    trace_snapshot = trace.to_dict()
    metrics = MetricEngine().compute(scenario, trace)
    graph = AgentToolGraphBuilder().build(scenario, trace)
    findings = analyze_trace(scenario, trace)
    decisions = Counter(span.policy_decision for span in trace.spans if span.span_type == "guard_decision" and span.policy_decision)
    types = Counter(span.span_type for span in trace.spans)
    propagation = graph["span_propagation"]
    warnings = []
    if not trace.completed_at:
        warnings.append("Trace has no completion timestamp; this report may describe a partial run.")
    if propagation["unlinked_propagation_span_ids"]:
        warnings.append("Some propagation annotations have no declared dependency path and cannot support CFP linkage.")
    return {
        "report_kind": "single_trace_provenance_evaluation_observability",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "trace_id": trace.trace_id,
            "scenario_id": scenario.scenario_id,
            "scenario_provenance_label": scenario.provenance,
            "source_case_study": scenario.source_case_study,
            "source": source,
            "source_file_sha256": source_sha256,
            "scenario_snapshot_sha256": _digest(scenario_snapshot),
            "trace_snapshot_sha256": _digest(trace_snapshot),
            "adapter": adapter,
            "execution_kind": execution_kind,
            "masguardeval_version": __version__,
            "hash_scope": "SHA-256 identifies the serialized source and canonical snapshots; it does not verify authorship, approval, or execution authenticity.",
        },
        "observability": {
            "mode": trace.mode,
            "started_at": trace.started_at,
            "completed_at": trace.completed_at,
            "elapsed_ms": trace.elapsed_ms,
            "blocked": trace.blocked,
            "stop_reason": trace.stop_reason,
            "span_count": len(trace.spans),
            "span_types": dict(sorted(types.items())),
            "guard_decisions": dict(sorted(decisions.items())),
            "executed_tool_calls": types["tool_call"],
            "agents": sorted({span.agent for span in trace.spans if span.agent}),
            "tools": sorted({span.tool for span in trace.spans if span.tool}),
            "graph_node_count": len(graph["nodes"]),
            "graph_edge_count": len(graph["edges"]),
            "graph_transition_count": types["graph_transition"],
            "structural_span_edges": len(propagation["edges"]),
            "declared_dependency_edges": len(propagation["dependency_edges"]),
            "candidate_failure_paths": propagation["failure_paths"],
            "unlinked_propagation_span_ids": propagation["unlinked_propagation_span_ids"],
            "timeline": [{
                "span_id": span.span_id, "timestamp": span.timestamp,
                "span_type": span.span_type, "agent": span.agent, "tool": span.tool,
                "policy_decision": span.policy_decision, "failure_label": span.failure_label,
                "parent_span_id": span.parent_span_id,
                "causal_parent_span_id": span.metadata.get("causal_parent_span_id"),
                "latency_ms": span.latency_ms, "token_usage": span.token_usage,
            } for span in trace.spans],
        },
        "evaluation": {
            "metrics": {key: value.to_dict() for key, value in metrics.items()},
            "recommendations": recommendations_for(metrics),
            "findings": findings,
            "scope": "Metrics and findings are recomputed for this single recorded trace; no matched baseline, human task judgment, or causal root-cause claim is inferred.",
        },
        "graph": graph,
        "scenario_snapshot": scenario_snapshot,
        "trace_snapshot": trace_snapshot,
        "warnings": warnings,
    }


def trace_report_markdown(report: dict[str, Any]) -> str:
    """Render a readable report without copying raw prompt or tool contents."""
    provenance = report["provenance"]
    observation = report["observability"]
    evaluation = report["evaluation"]

    def safe(value: object) -> str:
        return html.escape(str(value if value is not None else "N/A"), quote=False).replace("|", "\\|").replace("`", "\\`").replace("\n", " ").replace("\r", " ")

    lines = [
        "# MASGuardEval trace report", "",
        f"Trace: `{safe(provenance['trace_id'])}`  ",
        f"Scenario: `{safe(provenance['scenario_id'])}`  ",
        f"Generated: {safe(report['generated_at'])}", "",
        "## Provenance", "",
        f"- Source: {safe(provenance['source'])}",
        f"- Source file SHA-256: `{safe(provenance['source_file_sha256'])}`",
        f"- Scenario label (self-declared): {safe(provenance['scenario_provenance_label'])}",
        f"- Source case study: {safe(provenance['source_case_study'])}",
        f"- Scenario snapshot SHA-256: `{safe(provenance['scenario_snapshot_sha256'])}`",
        f"- Trace snapshot SHA-256: `{safe(provenance['trace_snapshot_sha256'])}`",
        f"- Adapter / execution kind: {safe(provenance['adapter'])} / {safe(provenance['execution_kind'])}",
        f"- MASGuardEval version: {safe(provenance['masguardeval_version'])}",
        "", safe(provenance["hash_scope"]), "",
        "## Evaluation", "", safe(evaluation["scope"]), "",
        "| Metric | Score | Reference threshold | Applicable | Reference rule met | Interpretation |",
        "| --- | ---: | ---: | --- | --- | --- |",
    ]
    for metric in evaluation["metrics"].values():
        score = metric["score"] if metric["applicable"] else "N/A"
        threshold = "—" if metric["threshold"] is None else metric["threshold"]
        rule = "—" if metric["passed"] is None else metric["passed"]
        lines.append(f"| {safe(metric['key'])} — {safe(metric['name'])} | {safe(score)} | {safe(threshold)} | {safe(metric['applicable'])} | {safe(rule)} | {safe(metric['interpretation'])} |")
    lines += ["", "### Metric evidence", ""]
    for metric in evaluation["metrics"].values():
        lines.append(f"- **{safe(metric['key'])}** details: `{safe(json.dumps(metric['details'], ensure_ascii=False, sort_keys=True))}`")
    lines += ["", "### Findings", "", safe(evaluation["findings"]["interpretation"]), ""]
    if not evaluation["findings"]["findings"]:
        lines.append("No policy finding was identified in the recorded spans.")
    for finding in evaluation["findings"]["findings"]:
        lines += [
            f"- **{safe(finding['severity'])}: {safe(finding['title'])}**",
            f"  Evidence spans: {', '.join('`' + safe(span_id) + '`' for span_id in finding['evidence_span_ids'])}. Next action: {safe(finding['next_action'])}",
        ]
    lines += ["", "### Recommendations", ""]
    lines += [f"- {safe(item)}" for item in evaluation["recommendations"]] or ["No metric recommendation was generated."]
    lines += ["", "## Observability", "",
              f"- Mode: {safe(observation['mode'])}; started: {safe(observation['started_at'])}; completed: {safe(observation['completed_at'])}",
              f"- Duration: {safe(observation['elapsed_ms'])} ms; blocked: {safe(observation['blocked'])}; stop reason: {safe(observation['stop_reason'])}",
              f"- Spans: {observation['span_count']}; executed tool calls: {observation['executed_tool_calls']}; graph nodes/edges/transitions: {observation['graph_node_count']}/{observation['graph_edge_count']}/{observation['graph_transition_count']}",
              f"- Span types: {safe(json.dumps(observation['span_types'], sort_keys=True))}",
              f"- Guard decisions: {safe(json.dumps(observation['guard_decisions'], sort_keys=True))}",
              f"- Agents: {safe(', '.join(observation['agents']))}; tools: {safe(', '.join(observation['tools']))}",
              f"- Structural span edges: {observation['structural_span_edges']}; declared dependency edges: {observation['declared_dependency_edges']}",
              "", "### Candidate failure dependency paths", ""]
    paths = observation["candidate_failure_paths"]
    lines += ["- " + " → ".join(f"`{safe(span_id)}`" for span_id in path) for path in paths] or ["No declared failure path was observed."]
    lines += ["", "### Observed graph edges", "",
              "| Evidence span | From | To | Kind | Decision |",
              "| --- | --- | --- | --- | --- |"]
    for edge in report["graph"]["edges"]:
        lines.append("| " + " | ".join(safe(edge.get(key)) for key in (
            "span_id", "source", "target", "kind", "decision")) + " |")
    lines += ["", "### Event timeline", "",
              "| Time | Span ID | Type | Agent | Tool | Decision | Failure label | Parent | Dependency |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for event in observation["timeline"]:
        lines.append("| " + " | ".join(safe(event[key]) for key in (
            "timestamp", "span_id", "span_type", "agent", "tool", "policy_decision",
            "failure_label", "parent_span_id", "causal_parent_span_id")) + " |")
    if report["warnings"]:
        lines += ["", "## Warnings", ""] + [f"- {safe(item)}" for item in report["warnings"]]
    lines += ["", "The JSON companion includes the scenario and full raw trace. Review it before sharing; it may contain prompts, tool inputs, or other sensitive content.", ""]
    return "\n".join(lines)
