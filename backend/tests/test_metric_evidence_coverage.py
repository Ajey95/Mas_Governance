from dataclasses import replace
from pathlib import Path

from masguardeval import GoldenDataset, MetricEngine, Span, Trace


DATASET = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


def _trace(scenario_id, *spans):
    trace = Trace.start(scenario_id, "baseline")
    for kind, agent, metadata, tool, parameters in spans:
        trace.add_span(Span.create(trace.trace_id, kind, agent, "developer", metadata=metadata,
                                   tool=tool, tool_parameters=parameters))
    trace.finish()
    return trace


def test_phr_uses_guard_schema_for_types_values_and_coverage():
    source = GoldenDataset.load(DATASET).get("auth_001")
    scenario = replace(source, parameter_schema={"safe_tool": {
        "allowed_keys": ["mode", "count"], "required_keys": ["mode", "count"],
        "properties": {"mode": {"type": "string", "enum": ["inspect"]},
                       "count": {"type": "integer"}}}})
    trace = _trace(scenario.scenario_id,
                   ("tool_call", "A", {}, "safe_tool", {"mode": "change", "count": True}),
                   ("tool_call", "A", {}, "unknown_tool", {"anything": 1}),
                   ("tool_call", "A", {}, "safe_tool", {"mode": "inspect", "count": 2}))
    metric = MetricEngine().parameter_hallucination_rate(scenario, trace)
    assert metric.applicable and metric.score == 0.5
    assert metric.details["assessed_span_count"] == 2
    assert len(metric.details["unassessed_span_ids"]) == 1
    assert metric.details["issues_by_span"][trace.spans[0].span_id]["invalid_types"] == {"count": "integer"}
    assert metric.details["issues_by_span"][trace.spans[0].span_id]["invalid_values"] == {"mode": "enum"}


def test_cpi_does_not_treat_unassessed_context_as_clean():
    scenario = GoldenDataset.load(DATASET).get("context_001")
    trace = _trace(scenario.scenario_id,
                   ("agent_step", "A", {}, None, {}),
                   ("inter_agent_message", "B", {"context_polluted": True}, None, {}),
                   ("memory_operation", "C", {"context_polluted": True, "sanitized": True}, None, {}))
    metric = MetricEngine().context_pollution_index(scenario, trace)
    assert metric.applicable and metric.score == 0.5
    assert metric.details["assessed_span_count"] == 2
    assert metric.details["unassessed_span_ids"] == [trace.spans[0].span_id]
    missing = _trace(scenario.scenario_id, ("agent_step", "A", {}, None, {}))
    assert not MetricEngine().context_pollution_index(scenario, missing).applicable


def test_ccr_requires_same_scope_and_revision():
    scenario = GoldenDataset.load(DATASET).get("coord_001")
    trace = _trace(scenario.scenario_id,
                   ("agent_step", "Planner", {"decision_scope": "deploy", "decision_value": "allow", "decision_revision": "r1"}, None, {}),
                   ("agent_step", "Reviewer", {"decision_scope": "deploy", "decision_value": "deny", "decision_revision": "r1"}, None, {}),
                   ("agent_step", "Planner", {"decision_scope": "deploy", "decision_value": "allow", "decision_revision": "r2"}, None, {}),
                   ("agent_step", "Executor", {"decision": "finish"}, None, {}))
    metric = MetricEngine().conflict_contradiction_rate(scenario, trace)
    assert metric.applicable and metric.score == 1.0
    assert metric.details["comparable_decision_count"] == 2
    assert metric.details["unscoped_decision_span_ids"] == [trace.spans[3].span_id]
    no_pair = _trace(scenario.scenario_id,
                     ("agent_step", "A", {"decision_scope": "x", "decision_value": "allow"}, None, {}),
                     ("agent_step", "B", {"decision_scope": "y", "decision_value": "deny"}, None, {}))
    assert not MetricEngine().conflict_contradiction_rate(scenario, no_pair).applicable


def test_cfp_does_not_report_zero_when_multiple_failures_lack_dependency_evidence():
    scenario = GoldenDataset.load(DATASET).get("cascade_001")
    trace = Trace.start(scenario.scenario_id, "baseline")
    trace.add_span(Span.create(trace.trace_id, "agent_step", "Planner", "developer", failure_label="bad_plan"))
    trace.add_span(Span.create(trace.trace_id, "agent_step", "Executor", "developer", failure_label="bad_action"))
    trace.finish()
    metric = MetricEngine().cascading_failure_probability(scenario, trace)
    assert metric.score == 0
    assert not metric.applicable
    assert metric.details["declared_dependency_edge_count"] == 0
