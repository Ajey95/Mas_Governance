from pathlib import Path

from masguardeval import EvaluationEngine, GoldenDataset, guard_profile


DATASET = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


def test_named_comparator_profiles_are_distinct_and_reproducible():
    assert [guard.name for guard in guard_profile("allowlist")] == ["ToolAllowlistGuard"]
    assert [guard.name for guard in guard_profile("access_control")] == [
        "RBACGuard", "ABACGuard", "ToolAllowlistGuard", "ParameterValidator",
    ]
    assert len(guard_profile("full")) > len(guard_profile("access_control"))

    dataset = GoldenDataset.load(DATASET)
    full = EvaluationEngine(dataset, guards=guard_profile("full")).run_guarded(dataset.get("loop_001"))
    allowlist = EvaluationEngine(dataset, guards=guard_profile("allowlist")).run_guarded(dataset.get("loop_001"))
    assert full.blocked and not allowlist.blocked
