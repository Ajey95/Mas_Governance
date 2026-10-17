from pathlib import Path

from masguardeval import EvaluationEngine, ExperimentSuite, GoldenDataset, MetricEngine, Span, Trace
from masguardeval.models import Scenario
from masguardeval.stats import summarize_trials


DATASET = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


def _span(trace: Trace, kind: str, *, failure: str | None = None,
          decision: str | None = None, metadata: dict | None = None) -> Span:
    span = Span.create(trace.trace_id, kind, "Agent", "developer",
                       failure_label=failure, policy_decision=decision,
                       metadata=metadata)
    trace.add_span(span)
    return span


def test_omitted_required_tools_does_not_turn_allowed_tools_into_obligations():
    source = GoldenDataset.load(DATASET).get("auth_001")
    payload = source.to_dict()
    payload.pop("required_tools")
    scenario = Scenario.from_dict(payload)
    assert scenario.required_tools == []
    trace = Trace.start(scenario.scenario_id, "baseline")
    assert not MetricEngine().tool_selection_recall(scenario, trace).applicable


def test_diagnosis_depth_ignores_allow_guard_bookkeeping_and_is_not_risk_reduction():
    scenario = GoldenDataset.load(DATASET).get("auth_001")
    trace = Trace.start(scenario.scenario_id, "baseline")
    _span(trace, "agent_step")
    signal = _span(trace, "agent_step", failure="bad_action")
    _span(trace, "final_response")
    original = MetricEngine().diagnosis_time(scenario, trace)

    padded = Trace.start(scenario.scenario_id, "guarded")
    _span(padded, "agent_step")
    for _ in range(10):
        _span(padded, "guard_decision", decision="ALLOW")
    _span(padded, "agent_step", failure="bad_action")
    _span(padded, "final_response")
    measured = MetricEngine().diagnosis_time(scenario, padded)
    assert original.score == measured.score == 0.5
    assert measured.details["measured_event_count"] == 3
    assert measured.details["signal_span_id"] == padded.spans[-2].span_id
    assert signal.span_id == original.details["signal_span_id"]
    assert measured.to_dict()["threshold"] is None
    assert measured.to_dict()["passed"] is None
    assert "DT" not in EvaluationEngine.from_dataset_path(DATASET).evaluate("auth_001").risk_reduction()


def test_guard_intervention_is_a_signal_even_without_a_failure_label():
    scenario = GoldenDataset.load(DATASET).get("auth_001")
    trace = Trace.start(scenario.scenario_id, "guarded")
    _span(trace, "agent_step")
    signal = _span(trace, "guard_decision", decision="MODIFY")
    _span(trace, "final_response")
    result = MetricEngine().diagnosis_time(scenario, trace)
    assert result.applicable
    assert result.details["signal_span_id"] == signal.span_id


def test_unrelated_dependency_edge_cannot_certify_missing_failure_dependencies():
    scenario = GoldenDataset.load(DATASET).get("cascade_001")
    trace = Trace.start(scenario.scenario_id, "baseline")
    first = _span(trace, "agent_step", failure="source_failure")
    _span(trace, "agent_step", metadata={"causal_parent_span_id": first.span_id})
    second = _span(trace, "agent_step", failure="independent_failure")
    metric = MetricEngine().cascading_failure_probability(scenario, trace)
    assert not metric.applicable
    assert metric.details["unassessed_failure_span_ids"] == [second.span_id]


def test_explicitly_assessed_independent_failure_allows_zero_propagation():
    scenario = GoldenDataset.load(DATASET).get("cascade_001")
    trace = Trace.start(scenario.scenario_id, "baseline")
    _span(trace, "agent_step", failure="source_failure")
    _span(trace, "agent_step", failure="independent_failure",
          metadata={"dependency_assessed": True})
    metric = MetricEngine().cascading_failure_probability(scenario, trace)
    assert metric.applicable and metric.score == 0.0
    assert metric.details["unassessed_failure_span_ids"] == []


def test_diagnosis_depth_is_excluded_from_directional_trial_statistics():
    result = {
        "architecture": "multi", "scenario": {"scenario_id": "s1"},
        "baseline_metrics": {"DT": {"score": 0.2, "applicable": True}},
        "guarded_metrics": {"DT": {"score": 0.8, "applicable": True}},
    }
    summary = summarize_trials([result])
    assert "DT" not in summary["architectures"].get("multi", {})
    report = ExperimentSuite(EvaluationEngine.from_dataset_path(DATASET)).run()
    assert report.metric_table["DT"]["delta"] is None


def test_inapplicable_metric_has_no_pass_flag():
    scenario = GoldenDataset.load(DATASET).get("auth_001")
    trace = Trace.start(scenario.scenario_id, "baseline")
    measured = MetricEngine().tool_selection_precision(scenario, trace)
    assert measured.applicable is False
    assert measured.to_dict()["passed"] is None
