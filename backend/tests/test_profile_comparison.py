from copy import deepcopy
from pathlib import Path

import pytest

from masguardeval import EvaluationEngine, GoldenDataset
from masguardeval.profile_comparison import compare_guard_profiles


DATASET = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


def test_profile_comparison_requires_matched_configuration_and_traces():
    result = EvaluationEngine(GoldenDataset.load(DATASET)).evaluate("auth_001").to_dict()
    common = {"status": "complete", "model": "test", "provider": "test", "model_metadata": {},
              "dataset_sha256": "fixed", "scenario_ids": ["auth_001"], "architectures": ["single"],
              "trials_per_scenario": 1, "max_tool_calls": 1, "temperature": 0, "seed": 23,
              "max_output_tokens": 256, "results": [{"architecture": "single", "trial": 1, **result}]}
    left = {**common, "guard_profile": "allowlist"}
    right = deepcopy({**common, "guard_profile": "full"})
    output = compare_guard_profiles(left, right)
    assert output["matched_pair_n"] == 1
    assert output["status"] == "descriptive_unadjudicated_profile_comparison"
    right["model"] = "other"
    with pytest.raises(ValueError, match="model"):
        compare_guard_profiles(left, right)
