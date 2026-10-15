from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from masguardeval import EvaluationEngine, GoldenDataset
from masguardeval.live import ModelOutput
from masguardeval.outcome_judge import compare_judge_to_humans, council_row, judge_row
from masguardeval.study import canonical_hash


DATASET = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


class FixedClient:
    def __init__(self, value):
        self.value = value
        self.prompts = []

    def complete(self, role, prompt):
        self.prompts.append((role, prompt))
        return ModelOutput(self.value, 22, 3.0, "response-1", "test-model")


def trial():
    from masguardeval.outcome_review import make_outcome_packet

    result = EvaluationEngine(GoldenDataset.load(DATASET)).evaluate("auth_001")
    packet, mapping = make_outcome_packet({"results": [{"architecture": "single", "trial": 1, **result.to_dict()}]})
    return packet, mapping


def test_judge_binds_masked_packet_and_cites_real_spans():
    packet, _ = trial()
    row = packet[0]
    span = row["visible_events"][0]["span_id"]
    client = FixedClient('{"task_failure":true,"prohibited_action":false,"uncertain":false,'
                         f'"evidence_span_ids":["{span}"],"rationale":"Authorized task was incomplete."' + "}")
    record = judge_row(row, client, provider="mock", model="test-model")
    assert record["packet_sha256"] and record["response_id"] == "response-1"
    assert record["evidence_span_ids"] == [span]
    assert "guard_decision" not in client.prompts[0][1]


def test_judge_rejects_hallucinated_evidence_and_council_keeps_failed_votes():
    packet, _ = trial()
    invalid = FixedClient('{"task_failure":false,"prohibited_action":false,"uncertain":false,'
                          '"evidence_span_ids":["invented"],"rationale":"No issue."}')
    with pytest.raises(ValueError, match="unknown span"):
        judge_row(packet[0], invalid, provider="x", model="y")
    valid = FixedClient('{"task_failure":true,"prohibited_action":false,"uncertain":false,'
                        '"evidence_span_ids":[],"rationale":"Task incomplete."}')
    result = council_row(packet[0], [("one", "a", valid, {}), ("two", "b", valid, {}),
                                     ("three", "c", invalid, {})])
    assert result["uncertain"] is False
    assert result["task_failure"] is True and result["prohibited_action"] is False
    assert len(result["votes"]) == 2 and result["failures"][0]["error_type"] == "ValueError"
    assert result["provider_complete"] is False
    repaired = council_row(packet[0], [("one", "a", valid, {}), ("two", "b", valid, {}),
                                       ("three", "c", valid, {})], previous=result)
    assert repaired["provider_complete"] is True
    assert len(repaired["votes"]) == 3 and repaired["failures"] == []
    assert len(valid.prompts) == 3  # the two successful providers were not called again
    with pytest.raises(ValueError, match="does not match"):
        council_row(packet[1], [("one", "a", valid, {}), ("two", "b", valid, {}),
                                ("three", "c", valid, {})], previous=result)


def test_secondary_comparison_requires_human_reconciliation_and_reports_missingness():
    packet, mapping = trial()
    model = FixedClient('{"task_failure":true,"prohibited_action":false,"uncertain":false,'
                        '"evidence_span_ids":[],"rationale":"Task incomplete."}')
    judgment = judge_row(packet[0], model, provider="mock", model="test-model")
    human = {"status": "human_labels_claimed_unverified_identity",
             "packet_sha256": canonical_hash(packet), "mapping_sha256": canonical_hash(mapping), "outcomes": [
        {"trace_id": row["trace_id"], "task_failure": True, "prohibited_action": False}
        for row in mapping
    ]}
    compared = compare_judge_to_humans(packet, mapping, [judgment], human)
    assert compared["missing_model_rows"] == 1
    assert compared["labels"]["task_failure"]["agreement"] == 1
    with pytest.raises(ValueError, match="reconciled"):
        compare_judge_to_humans(packet, mapping, [judgment], {**human, "status": "model_labels"})
    with pytest.raises(ValueError, match="packet and private mapping"):
        compare_judge_to_humans(packet, mapping, [judgment], {**human, "packet_sha256": "wrong"})
