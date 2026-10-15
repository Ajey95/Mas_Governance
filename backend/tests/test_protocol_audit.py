from pathlib import Path

from masguardeval import EvaluationEngine, GoldenDataset, LiveWorkspaceAdapter
from masguardeval.live import ModelOutput
from masguardeval.protocol import audit_report, protocol_errors


DATASET = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


class InvalidActionClient:
    def complete(self, role, prompt):
        if role == "Planner":
            return ModelOutput('{"plan":"Inspect the request","decision":"plan"}')
        return ModelOutput('{"kind":"answer","tool":null,"parameters":null,"answer":"Need a path"}')


def test_embedded_adapter_error_is_reported_as_protocol_failure():
    dataset = GoldenDataset.load(DATASET)
    result = EvaluationEngine(dataset, adapter=LiveWorkspaceAdapter(InvalidActionClient(), "fake", 1)).evaluate("auth_001")
    pair = {"architecture": "multi", "trial": 1, **result.to_dict()}
    assert {error["mode"] for error in protocol_errors(pair)} == {"baseline", "guarded"}
    report = audit_report({"results": [pair], "incomplete_pair_count": 0, "status": "complete"})
    assert report["status"] == "complete_with_protocol_errors"
    assert report["protocol_failure_pair_count"] == 1
    assert report["protocol_valid_pair_count"] == 0
