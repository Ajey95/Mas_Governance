"""Condition-masked trial packets and independently reconciled outcome labels."""

from __future__ import annotations

from collections import defaultdict
from random import Random
from typing import Any

from .evaluator import EvaluatorAgreement
from .study import _timestamp, canonical_hash


VISIBLE_SPAN_TYPES = {"agent_step", "tool_call", "inter_agent_message", "memory_operation", "final_response"}


def make_outcome_packet(report: dict[str, Any], *, seed: int = 23) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return review rows and a separate private condition map."""
    rng = Random(seed)
    packet: list[dict[str, Any]] = []
    mapping: list[dict[str, Any]] = []
    used: set[str] = set()
    for result in report.get("results", []):
        scenario = result["scenario"]
        for mode in ("baseline", "guarded"):
            trace = result[f"{mode}_trace"]
            blind_id = f"trial-{rng.getrandbits(96):024x}"
            if blind_id in used:
                raise RuntimeError("Blind ID collision")
            used.add(blind_id)
            packet.append({
                "blind_id": blind_id,
                "scenario_id": scenario["scenario_id"],
                "user_prompt": scenario["prompt"],
                "expected_safe_behavior": scenario["expected_safe_behavior"],
                "blocked_tools": scenario["blocked_tools"],
                "visible_events": [
                    {"span_id": span["span_id"], "parent_span_id": span.get("parent_span_id"),
                     "type": span["span_type"], "agent": span["agent"],
                     "tool": span.get("tool"), "parameters": span.get("tool_parameters"),
                     "output": span.get("output")}
                    for span in trace["spans"] if span["span_type"] in VISIBLE_SPAN_TYPES
                ],
                "final_response": trace["final_response"],
            })
            mapping.append({
                "blind_id": blind_id, "trace_id": trace["trace_id"],
                "scenario_id": scenario["scenario_id"],
                "architecture": result["architecture"], "trial": result["trial"], "mode": mode,
            })
    order = list(range(len(packet)))
    rng.shuffle(order)
    return [packet[i] for i in order], mapping


def make_outcome_review_template(packet: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"blind_id": row["blind_id"], "packet_sha256": canonical_hash(row),
         "reviewer_id": "", "reviewer_role": "", "recorded_at": "",
         "task_failure": None, "prohibited_action": None, "rationale": ""}
        for row in packet
    ]


def reconcile_outcomes(
    packet: list[dict[str, Any]], mapping: list[dict[str, Any]],
    reviews: list[dict[str, Any]], adjudications: list[dict[str, Any]],
) -> dict[str, Any]:
    by_blind = {row["blind_id"]: row for row in packet}
    map_by_blind = {row["blind_id"]: row for row in mapping}
    if len(by_blind) != len(packet) or set(by_blind) != set(map_by_blind) or len(map_by_blind) != len(mapping):
        raise ValueError("Packet and private map do not contain the same unique blind IDs")
    by_review: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in reviews:
        blind_id = str(record.get("blind_id", ""))
        if blind_id not in by_blind:
            raise ValueError(f"Unknown blind ID {blind_id}")
        if record.get("packet_sha256") != canonical_hash(by_blind[blind_id]):
            raise ValueError(f"Outcome packet hash mismatch for {blind_id}")
        if any(type(record.get(key)) is not bool for key in ("task_failure", "prohibited_action")):
            raise ValueError(f"Outcome labels must be booleans for {blind_id}")
        if not all(str(record.get(key, "")).strip() for key in ("reviewer_id", "reviewer_role", "rationale")):
            raise ValueError(f"Reviewer identity, role, and rationale required for {blind_id}")
        _timestamp(record.get("recorded_at"))
        by_review[blind_id].append(record)
    by_adjudication: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in adjudications:
        blind_id = str(record.get("blind_id", ""))
        if blind_id not in by_blind:
            raise ValueError(f"Unknown adjudication blind ID {blind_id}")
        if record.get("packet_sha256") != canonical_hash(by_blind[blind_id]):
            raise ValueError(f"Adjudication packet hash mismatch for {blind_id}")
        if any(type(record.get(key)) is not bool for key in ("task_failure", "prohibited_action")):
            raise ValueError(f"Adjudication labels must be booleans for {blind_id}")
        if not str(record.get("adjudicator_id", "")).strip() or not str(record.get("rationale", "")).strip():
            raise ValueError(f"Adjudicator identity and rationale required for {blind_id}")
        _timestamp(record.get("recorded_at"))
        by_adjudication[blind_id].append(record)

    outcomes = []
    rater_a: dict[str, list[str]] = {"task_failure": [], "prohibited_action": []}
    rater_b: dict[str, list[str]] = {"task_failure": [], "prohibited_action": []}
    for blind_id in sorted(by_blind):
        records = by_review[blind_id]
        reviewers = {str(item["reviewer_id"]) for item in records}
        if len(records) != 2 or len(reviewers) != 2:
            raise ValueError(f"{blind_id} needs two distinct reviewers")
        records.sort(key=lambda row: row["reviewer_id"])
        disagreement = any(records[0][key] != records[1][key] for key in rater_a)
        adjudicator = by_adjudication.get(blind_id, [])
        if disagreement:
            if len(adjudicator) != 1 or adjudicator[0]["adjudicator_id"] in reviewers:
                raise ValueError(f"{blind_id} needs a separate adjudicator")
            final = adjudicator[0]
        else:
            if adjudicator:
                raise ValueError(f"{blind_id} has unnecessary adjudication")
            final = records[0]
        for key in rater_a:
            rater_a[key].append(str(records[0][key]))
            rater_b[key].append(str(records[1][key]))
        outcomes.append({**map_by_blind[blind_id],
                         "task_failure": final["task_failure"],
                         "prohibited_action": final["prohibited_action"],
                         "adjudicated": disagreement})
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in outcomes:
        groups[(row["architecture"], row["mode"])].append(row)
    summary = {
        f"{architecture}:{mode}": {
            "n": len(rows),
            "task_failure_rate": sum(item["task_failure"] for item in rows) / len(rows),
            "prohibited_action_rate": sum(item["prohibited_action"] for item in rows) / len(rows),
        }
        for (architecture, mode), rows in sorted(groups.items())
    }
    agreement = {
        key: EvaluatorAgreement.cohens_kappa(rater_a[key], rater_b[key]).to_dict()
        for key in rater_a
    }
    return {"status": "human_labels_claimed_unverified_identity", "outcomes": outcomes,
            "summary": summary, "inter_rater_agreement": agreement,
            "packet_sha256": canonical_hash(packet), "mapping_sha256": canonical_hash(mapping)}
