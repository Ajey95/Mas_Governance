from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from masguardeval import EvaluationEngine, GoldenDataset
from masguardeval.study import canonical_hash
from masguardeval.study_analysis import _auc, _threshold, analyze_study


DATASET = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


def make_report(scenario):
    dataset = GoldenDataset([scenario])
    result = EvaluationEngine(dataset).evaluate(scenario.scenario_id)
    report = {"status": "complete", "model": "test-model", "provider": "test", "model_metadata": {"digest": "test"},
              "architectures": ["single"], "trials_per_scenario": 1, "max_tool_calls": 1,
              "scenario_ids": [scenario.scenario_id], "results": [{"architecture": "single", "trial": 1, **result.to_dict()}]}
    labels = {"outcomes": [
        {"trace_id": result.baseline_trace.trace_id, "task_failure": True, "prohibited_action": True},
        {"trace_id": result.guarded_trace.trace_id, "task_failure": False, "prohibited_action": False},
    ]}
    return dataset, report, labels


def test_auc_ties_and_development_threshold_are_deterministic():
    assert _auc([0.9, 0.5], [0.1, 0.5]) == 0.875
    assert _threshold([(0.9, True), (0.8, True), (0.2, False), (0.1, False)]) == 0.8
    assert _threshold([(0.5, True), (0.5, True)]) is None


def test_heldout_analysis_uses_independent_labels_and_frozen_scenarios():
    reference = GoldenDataset.load(DATASET).get("auth_001")
    dev, dev_report, dev_labels = make_report(replace(reference, scenario_id="development-task"))
    test, test_report, test_labels = make_report(replace(reference, scenario_id="heldout-task"))
    manifest = {"development_sha256": canonical_hash(dev.to_dict()),
                "heldout_sha256": canonical_hash(test.to_dict())}
    analysis = analyze_study(dev_report, dev_labels, dev, test_report, test_labels, test, manifest)
    assert analysis["primary_outcomes"]["heldout"]["single:task_failure"]["mean_absolute_risk_reduction"] == 1
    assert analysis["metric_construct_checks"]
    assert not any(key.startswith("DT:") for key in analysis["metric_construct_checks"])
    assert all(row["development"]["threshold"] == row["heldout"]["threshold"]
               for row in analysis["metric_construct_checks"].values())
    test_labels["outcomes"].pop()
    with pytest.raises(ValueError, match="cover each trace"):
        analyze_study(dev_report, dev_labels, dev, test_report, test_labels, test, manifest)
