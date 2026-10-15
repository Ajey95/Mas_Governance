"""Task-review and frozen holdout gates for an independently run study.

This module verifies the shape and consistency of submitted review records. It
cannot establish that a claimed human author or reviewer is actually human.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from random import Random
from typing import Any

from .dataset import GoldenDataset
from .models import Scenario


RISK_TYPES = {
    "unauthorized_compliance", "sensitive_data_disclosure", "tool_misuse",
    "infinite_agent_looping", "cascading_failure", "context_pollution",
    "contradictory_coordination",
}


def canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(f"Review record on line {line_number} is not an object")
        records.append(record)
    return records


def make_review_packet(dataset: GoldenDataset) -> list[dict[str, Any]]:
    return [
        {"scenario_id": scenario.scenario_id, "scenario_sha256": canonical_hash(scenario.to_dict()),
         "reviewer_id": "", "reviewer_role": "", "decision": "",
         "recorded_at": "", "rationale": ""}
        for scenario in dataset.scenarios
    ]


def _timestamp(value: Any) -> None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError("recorded_at must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("recorded_at must include a timezone")


def _family(scenario: Scenario) -> str:
    families = [tag[7:] for tag in scenario.tags if tag.startswith("family:") and tag[7:]]
    if len(families) != 1:
        raise ValueError(f"{scenario.scenario_id} needs exactly one nonempty family: tag")
    return families[0]


def freeze_study(
    dataset: GoldenDataset,
    reviews: list[dict[str, Any]],
    adjudications: list[dict[str, Any]],
    *, seed: int = 23, holdout_fraction: float = 0.2,
    min_tasks: int = 30, max_tasks: int = 50, require_all_risks: bool = True,
) -> tuple[GoldenDataset, GoldenDataset, dict[str, Any]]:
    if not 0 < holdout_fraction < 0.5:
        raise ValueError("holdout_fraction must be between 0 and 0.5")
    if min_tasks < 1 or max_tasks < min_tasks:
        raise ValueError("invalid task count bounds")
    by_id = {scenario.scenario_id: scenario for scenario in dataset.scenarios}
    for scenario in dataset.scenarios:
        if scenario.provenance != "independent_human_authored":
            raise ValueError(f"{scenario.scenario_id} is not declared independently human authored")
        _family(scenario)
    by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in reviews:
        scenario_id = str(record.get("scenario_id", ""))
        if scenario_id not in by_id:
            raise ValueError(f"Review references unknown scenario {scenario_id}")
        scenario = by_id[scenario_id]
        if record.get("scenario_sha256") != canonical_hash(scenario.to_dict()):
            raise ValueError(f"Review hash mismatch for {scenario_id}")
        if record.get("decision") not in {"approve", "reject"}:
            raise ValueError(f"Review decision invalid for {scenario_id}")
        if not str(record.get("reviewer_id", "")).strip() or not str(record.get("reviewer_role", "")).strip() or not str(record.get("rationale", "")).strip():
            raise ValueError(f"Review identity, role, and rationale required for {scenario_id}")
        _timestamp(record.get("recorded_at"))
        by_scenario[scenario_id].append(record)

    by_adjudication: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in adjudications:
        scenario_id = str(record.get("scenario_id", ""))
        if scenario_id not in by_id:
            raise ValueError(f"Adjudication references unknown scenario {scenario_id}")
        if record.get("scenario_sha256") != canonical_hash(by_id[scenario_id].to_dict()):
            raise ValueError(f"Adjudication hash mismatch for {scenario_id}")
        if record.get("decision") not in {"approve", "reject"}:
            raise ValueError(f"Adjudication decision invalid for {scenario_id}")
        if not str(record.get("adjudicator_id", "")).strip() or not str(record.get("rationale", "")).strip():
            raise ValueError(f"Adjudicator identity and rationale required for {scenario_id}")
        _timestamp(record.get("recorded_at"))
        by_adjudication[scenario_id].append(record)

    accepted: list[Scenario] = []
    rejected: list[str] = []
    for scenario in dataset.scenarios:
        records = by_scenario[scenario.scenario_id]
        reviewers = {str(item["reviewer_id"]) for item in records}
        if len(records) != 2 or len(reviewers) != 2:
            raise ValueError(f"{scenario.scenario_id} needs two distinct independent reviews")
        decisions = {str(item["decision"]) for item in records}
        adjudicators = by_adjudication.get(scenario.scenario_id, [])
        if len(decisions) == 2:
            if len(adjudicators) != 1 or adjudicators[0]["adjudicator_id"] in reviewers:
                raise ValueError(f"{scenario.scenario_id} needs a separate adjudicator for disagreement")
            decision = adjudicators[0]["decision"]
        else:
            if adjudicators:
                raise ValueError(f"{scenario.scenario_id} has unnecessary adjudication")
            decision = next(iter(decisions))
        if decision == "approve":
            accepted.append(scenario)
        else:
            rejected.append(scenario.scenario_id)

    if not min_tasks <= len(accepted) <= max_tasks:
        raise ValueError(f"Accepted task count {len(accepted)} is outside {min_tasks}..{max_tasks}")
    risks = {scenario.risk_type for scenario in accepted}
    if require_all_risks and risks != RISK_TYPES:
        raise ValueError(f"Accepted tasks do not cover every risk category: {sorted(RISK_TYPES - risks)}")
    family_risk: dict[str, str] = {}
    risk_families: dict[str, set[str]] = defaultdict(set)
    for scenario in accepted:
        family = _family(scenario)
        if family in family_risk and family_risk[family] != scenario.risk_type:
            raise ValueError(f"Family {family} spans risk categories")
        family_risk[family] = scenario.risk_type
        risk_families[scenario.risk_type].add(family)
    if any(len(families) < 2 for families in risk_families.values()):
        raise ValueError("Each risk category needs at least two independent task families for a holdout")

    heldout_families: set[str] = set()
    for risk, families in sorted(risk_families.items()):
        family_list = sorted(families)
        Random(f"{seed}:{risk}").shuffle(family_list)
        count = max(1, round(len(family_list) * holdout_fraction))
        heldout_families.update(family_list[:min(count, len(family_list) - 1)])
    development = GoldenDataset([scenario for scenario in accepted if _family(scenario) not in heldout_families])
    heldout = GoldenDataset([scenario for scenario in accepted if _family(scenario) in heldout_families])
    development.validate()
    heldout.validate()
    manifest = {
        "study_status": "frozen_task_set_pending_outcome_labels",
        "origin_claim_verified_by_software": False,
        "seed": seed,
        "holdout_fraction_target": holdout_fraction,
        "accepted_tasks": len(accepted), "rejected_task_ids": rejected,
        "development_tasks": len(development.scenarios), "heldout_tasks": len(heldout.scenarios),
        "development_families": sorted(set(family_risk) - heldout_families),
        "heldout_families": sorted(heldout_families),
        "development_sha256": canonical_hash(development.to_dict()),
        "heldout_sha256": canonical_hash(heldout.to_dict()),
        "reviews_sha256": canonical_hash(reviews),
        "adjudications_sha256": canonical_hash(adjudications),
    }
    return development, heldout, manifest
