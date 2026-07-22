from pathlib import Path

from masguardeval import EvaluationEngine, GoldenDataset


DATASET_PATH = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


def test_dataset_covers_required_risks_and_metrics():
    dataset = GoldenDataset.load(DATASET_PATH)
    risks = {scenario.risk_type for scenario in dataset.scenarios}

    assert {
        "unauthorized_compliance",
        "sensitive_data_disclosure",
        "tool_misuse",
        "infinite_agent_looping",
        "cascading_failure",
        "context_pollution",
        "contradictory_coordination",
    } <= risks

    for scenario in dataset.scenarios:
        assert {"TSP", "TSR", "PHR", "CPI", "CFP", "RSS", "CCR", "DT"} == set(scenario.metrics)


def test_guarded_run_improves_unauthorized_compliance():
    engine = EvaluationEngine.from_dataset_path(DATASET_PATH)
    result = engine.evaluate("auth_001")

    assert result.baseline_metrics["TSP"].passed is False
    assert result.baseline_metrics["RSS"].passed is False
    assert result.guarded_metrics["TSP"].passed is True
    assert result.guarded_metrics["RSS"].passed is True
    assert result.guarded_trace.blocked is True


def test_dashboard_payload_contains_comparison_and_recommendations():
    engine = EvaluationEngine.from_dataset_path(DATASET_PATH)
    payload = engine.generate_dashboard()

    assert payload["summary"]["scenario_count"] >= 7
    first = payload["results"][0]
    assert "baseline_trace" in first
    assert "guarded_trace" in first
    assert "risk_reduction" in first
    assert first["recommendations"]
