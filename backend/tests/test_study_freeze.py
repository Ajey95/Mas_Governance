from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from masguardeval import GoldenDataset
from masguardeval.study import canonical_hash, freeze_study, make_review_packet


ROOT = Path(__file__).resolve().parents[2]
REFERENCE = GoldenDataset.load(ROOT / "datasets" / "golden_scenarios.json").scenarios[0]


def curated_fixture():
    scenarios = [
        replace(REFERENCE, scenario_id=f"task-{i}", provenance="independent_human_authored", tags=[f"family:{'one' if i < 2 else 'two'}"])
        for i in range(4)
    ]
    dataset = GoldenDataset(scenarios)
    timestamp = datetime.now(timezone.utc).isoformat()
    reviews = [
        {"scenario_id": scenario.scenario_id, "scenario_sha256": canonical_hash(scenario.to_dict()),
         "reviewer_id": reviewer, "reviewer_role": "domain_expert",
         "decision": "approve", "recorded_at": timestamp, "rationale": "Rubric checked"}
        for scenario in scenarios for reviewer in ("reviewer-a", "reviewer-b")
    ]
    return dataset, reviews


def test_freeze_keeps_entire_task_families_on_one_side_and_hashes_outputs():
    dataset, reviews = curated_fixture()
    development, heldout, manifest = freeze_study(
        dataset, reviews, [], min_tasks=4, max_tasks=4, require_all_risks=False,
    )
    assert len(development.scenarios) == len(heldout.scenarios) == 2
    assert set(manifest["development_families"]).isdisjoint(manifest["heldout_families"])
    assert manifest["heldout_sha256"] == canonical_hash(heldout.to_dict())
    assert manifest["origin_claim_verified_by_software"] is False


def test_freeze_rejects_synthetic_candidates_and_changed_tasks():
    candidate = GoldenDataset.load(ROOT / "datasets" / "candidate_scenarios.json")
    assert make_review_packet(candidate)[0]["reviewer_id"] == ""
    with pytest.raises(ValueError, match="not declared independently"):
        freeze_study(candidate, [], [], min_tasks=1, require_all_risks=False)

    dataset, reviews = curated_fixture()
    reviews[0]["scenario_sha256"] = "stale"
    with pytest.raises(ValueError, match="hash mismatch"):
        freeze_study(dataset, reviews, [], min_tasks=4, max_tasks=4, require_all_risks=False)


def test_freeze_requires_distinct_reviewers_and_separate_adjudicator():
    dataset, reviews = curated_fixture()
    reviews[1]["reviewer_id"] = "reviewer-a"
    with pytest.raises(ValueError, match="two distinct"):
        freeze_study(dataset, reviews, [], min_tasks=4, max_tasks=4, require_all_risks=False)

    dataset, reviews = curated_fixture()
    reviews[0]["decision"] = "reject"
    with pytest.raises(ValueError, match="separate adjudicator"):
        freeze_study(dataset, reviews, [], min_tasks=4, max_tasks=4, require_all_risks=False)
    adjudication = {"scenario_id": "task-0", "scenario_sha256": reviews[0]["scenario_sha256"],
                    "adjudicator_id": "reviewer-c", "decision": "approve",
                    "recorded_at": reviews[0]["recorded_at"], "rationale": "Reviewed disagreement"}
    assert freeze_study(dataset, reviews, [adjudication], min_tasks=4, max_tasks=4, require_all_risks=False)[2]["accepted_tasks"] == 4
