from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from masguardeval import EvaluationEngine, GoldenDataset
from masguardeval.outcome_review import make_outcome_packet, make_outcome_review_template, reconcile_outcomes


DATASET = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


def fixture_packet():
    result = EvaluationEngine(GoldenDataset.load(DATASET)).evaluate("auth_001")
    packet, mapping = make_outcome_packet({"results": [{"architecture": "single", "trial": 1, **result.to_dict()}]})
    return packet, mapping


def test_packet_masks_condition_and_keeps_private_mapping_separate():
    packet, mapping = fixture_packet()
    assert len(packet) == len(mapping) == 2
    assert all("mode" not in row and "trace_id" not in row for row in packet)
    assert {row["mode"] for row in mapping} == {"baseline", "guarded"}
    assert all(event["type"] != "guard_decision" for row in packet for event in row["visible_events"])


def test_two_reviewers_and_adjudicator_reconcile_without_inventing_labels():
    packet, mapping = fixture_packet()
    now = datetime.now(timezone.utc).isoformat()
    reviews = [
        {**template, "reviewer_id": reviewer, "reviewer_role": "domain_expert",
         "recorded_at": now, "task_failure": False, "prohibited_action": False,
         "rationale": "Examined visible actions"}
        for template in make_outcome_review_template(packet) for reviewer in ("a", "b")
    ]
    result = reconcile_outcomes(packet, mapping, reviews, [])
    assert len(result["outcomes"]) == 2
    assert result["inter_rater_agreement"]["task_failure"]["kappa"] == 1
    assert all(row["adjudicated"] is False for row in result["outcomes"])

    reviews[0]["task_failure"] = True
    with pytest.raises(ValueError, match="separate adjudicator"):
        reconcile_outcomes(packet, mapping, reviews, [])
    adjudication = {"blind_id": reviews[0]["blind_id"], "packet_sha256": reviews[0]["packet_sha256"],
                    "adjudicator_id": "c", "recorded_at": now, "task_failure": True,
                    "prohibited_action": False, "rationale": "Resolved disagreement"}
    assert sum(item["adjudicated"] for item in reconcile_outcomes(packet, mapping, reviews, [adjudication])["outcomes"]) == 1


def test_outcome_review_rejects_changed_packet_and_duplicate_reviewer():
    packet, mapping = fixture_packet()
    now = datetime.now(timezone.utc).isoformat()
    records = [
        {**template, "reviewer_id": reviewer, "reviewer_role": "expert",
         "recorded_at": now, "task_failure": False, "prohibited_action": False, "rationale": "Reviewed"}
        for template in make_outcome_review_template(packet) for reviewer in ("a", "b")
    ]
    records[0]["packet_sha256"] = "stale"
    with pytest.raises(ValueError, match="hash mismatch"):
        reconcile_outcomes(packet, mapping, records, [])
    records[0]["packet_sha256"] = make_outcome_review_template(packet)[0]["packet_sha256"]
    records[1]["reviewer_id"] = "a"
    with pytest.raises(ValueError, match="two distinct"):
        reconcile_outcomes(packet, mapping, records, [])
