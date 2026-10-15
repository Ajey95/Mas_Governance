from pathlib import Path

from masguardeval import EvaluationEngine, GoldenDataset
from scripts.generate_candidate_dataset import build


ROOT = Path(__file__).resolve().parents[2]


def test_candidate_dataset_has_distinct_executable_variants():
    generated = build()
    dataset = GoldenDataset.load(ROOT / "datasets" / "candidate_scenarios.json")
    assert generated["scenarios"] == dataset.to_dict()["scenarios"]
    assert len(dataset.scenarios) == 35
    assert all(item.provenance == "synthetic_candidate_unadjudicated" for item in dataset.scenarios)
    engine = EvaluationEngine(dataset)
    first = engine.run_baseline(dataset.get("auth_c01"))
    second = engine.run_baseline(dataset.get("auth_c02"))
    assert next(span for span in first.spans if span.span_type == "tool_call").tool_parameters["date"] == "yesterday"
    assert next(span for span in second.spans if span.span_type == "tool_call").tool_parameters["date"] == "this morning"
