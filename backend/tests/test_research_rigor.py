from pathlib import Path

from masguardeval import EvaluationEngine, GoldenDataset
from masguardeval.evaluator import EvaluatorAgreement
from masguardeval.experiments import ExperimentSuite
from masguardeval.propagation import PropagationAnalyzer
from masguardeval.scaling import BatchEvaluationExecutor


DATASET_PATH = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


def test_experiment_suite_produces_tables_and_ablation_summary():
    engine = EvaluationEngine.from_dataset_path(DATASET_PATH)
    report = ExperimentSuite(engine).run()

    assert report.scenario_count >= 7
    assert len(report.scenario_rows) == report.scenario_count
    assert {"scenario_id", "risk_type", "baseline_RSS", "guarded_RSS", "rss_delta"} <= set(report.scenario_rows[0])
    assert "RSS" in report.metric_table
    assert report.metric_table["RSS"]["guarded_avg"] >= report.metric_table["RSS"]["baseline_avg"]
    assert {"full_guard_stack", "no_guards", "rbac_only"} <= set(report.ablation_table)
    assert report.ablation_table["full_guard_stack"]["blocked_actions"] >= report.ablation_table["no_guards"]["blocked_actions"]
    markdown = report.to_markdown()
    assert "## Metric Summary" in markdown
    assert "| Scenario | Risk Type | Baseline RSS | Guarded RSS | RSS Delta |" in markdown
    assert "| Guard Stack | Scenarios | Blocked Actions | Guarded RSS Avg |" in markdown


def test_evaluator_agreement_computes_cohens_kappa_and_confusion_table():
    labels_a = ["pass", "fail", "fail", "pass", "needs_review"]
    labels_b = ["pass", "fail", "pass", "pass", "needs_review"]

    agreement = EvaluatorAgreement.cohens_kappa(labels_a, labels_b)

    assert round(agreement.observed_agreement, 2) == 0.80
    assert 0.6 < agreement.kappa < 0.8
    assert agreement.confusion_table["fail"]["pass"] == 1
    assert agreement.label_count == 5


def test_propagation_analyzer_finds_rooted_paths_and_impact_score():
    engine = EvaluationEngine.from_dataset_path(DATASET_PATH)
    result = engine.evaluate("cascade_001")

    analysis = PropagationAnalyzer().analyze(result.baseline_trace)

    assert analysis.root_span_ids
    assert analysis.propagated_span_ids
    assert analysis.longest_path_length >= 3
    assert 0 < analysis.impact_score <= 1
    assert analysis.paths[0][0] in analysis.root_span_ids


def test_batch_executor_shards_and_runs_all_scenarios_with_stable_summary():
    dataset = GoldenDataset.load(DATASET_PATH)
    engine = EvaluationEngine(dataset)
    executor = BatchEvaluationExecutor(engine, max_workers=2, chunk_size=3)

    batch = executor.run()

    assert batch.scenario_count == len(dataset.scenarios)
    assert batch.worker_count == 2
    assert [len(shard.scenario_ids) for shard in batch.shards] == [3, 3, 1]
    assert batch.summary["scenario_count"] == len(dataset.scenarios)
    assert all(result.scenario.scenario_id for result in batch.results)
