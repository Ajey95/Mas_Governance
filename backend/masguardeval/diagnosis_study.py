"""Timed, condition-masked human diagnosis collection and analysis.

Software checks packet identity and recorded timing, but cannot authenticate a
reviewer or establish that a submitted diagnosis was independently authored.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from random import Random
from statistics import median
from time import monotonic_ns
from typing import Any, Callable

from .study import _timestamp, canonical_hash


def _parsed_timestamp(value: Any) -> datetime:
    _timestamp(value)
    return datetime.fromisoformat(str(value))


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{number} must contain a JSON object")
            rows.append(row)
    return rows


def validate_packet(packet: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not packet:
        raise ValueError("Diagnosis packet is empty")
    by_id: dict[str, dict[str, Any]] = {}
    for row in packet:
        blind_id = row.get("blind_id")
        if not isinstance(blind_id, str) or not blind_id or blind_id in by_id:
            raise ValueError("Diagnosis packet has empty or duplicate blind IDs")
        events = row.get("visible_events")
        if not isinstance(events, list):
            raise ValueError(f"{blind_id} has no visible event list")
        ids = [event.get("span_id") for event in events if isinstance(event, dict)]
        if len(ids) != len(events) or len(set(ids)) != len(ids) or any(not isinstance(item, str) or not item for item in ids):
            raise ValueError(f"{blind_id} has invalid visible span IDs")
        if "mode" in row or "trace_id" in row or any(event.get("type") == "guard_decision" for event in events):
            raise ValueError(f"{blind_id} is not condition masked")
        by_id[blind_id] = row
    return by_id


def reference_template(packet: list[dict[str, Any]]) -> list[dict[str, Any]]:
    validate_packet(packet)
    return [{"blind_id": row["blind_id"], "packet_sha256": canonical_hash(row),
             "reference_status": "", "accepted_span_ids": [],
             "adjudicator_id": "", "recorded_at": "", "rationale": ""} for row in packet]


def assign_diagnosis_panels(
    packet: list[dict[str, Any]], mapping: list[dict[str, Any]], *, seed: int = 23,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Four blinded panels; a reviewer slot sees only one mode of each pair."""
    by_packet = validate_packet(packet)
    by_map = {row["blind_id"]: row for row in mapping}
    if len(by_map) != len(mapping) or set(by_map) != set(by_packet):
        raise ValueError("Diagnosis private map does not match the packet")
    pairs: dict[tuple[str, int, str], dict[str, str]] = defaultdict(dict)
    for row in mapping:
        key = (str(row["architecture"]), int(row["trial"]), str(row["scenario_id"]))
        mode = row["mode"]
        if mode not in {"baseline", "guarded"} or mode in pairs[key]:
            raise ValueError("Diagnosis map must have one baseline and one guarded trial per pair")
        pairs[key][mode] = row["blind_id"]
    if any(set(pair) != {"baseline", "guarded"} for pair in pairs.values()):
        raise ValueError("Diagnosis map has an incomplete condition pair")
    if len({arch for arch, _, _ in pairs}) != 1:
        raise ValueError("Four-panel diagnosis assignment needs one architecture; prepare each architecture separately")
    if len({(arch, scenario_id) for arch, _, scenario_id in pairs}) != len(pairs):
        raise ValueError("Four-panel diagnosis assignment needs one trial per architecture and scenario; select one trial")
    rng = Random(seed)
    panels: dict[str, list[dict[str, Any]]] = {name: [] for name in
                                               ("panel_a_1", "panel_a_2", "panel_b_1", "panel_b_2")}
    assignment = []
    for key, modes in sorted(pairs.items()):
        a_mode = "baseline" if rng.getrandbits(1) == 0 else "guarded"
        b_mode = "guarded" if a_mode == "baseline" else "baseline"
        for panel_name, mode in (("panel_a_1", a_mode), ("panel_a_2", a_mode),
                                 ("panel_b_1", b_mode), ("panel_b_2", b_mode)):
            panels[panel_name].append(by_packet[modes[mode]])
            assignment.append({"panel": panel_name, "blind_id": modes[mode],
                               "mode": mode, "architecture": key[0], "trial": key[1],
                               "scenario_id": key[2]})
    for rows in panels.values():
        rng.shuffle(rows)
    return panels, {"packet_sha256": canonical_hash(packet), "mapping_sha256": canonical_hash(mapping),
                    "seed": seed, "assignments": assignment,
                    "interpretation": "Keep this mode-bearing manifest private. Give each of four independent reviewers only one assigned panel."}


def capture_diagnosis(
    row: dict[str, Any], reviewer_id: str, reviewer_role: str, *,
    ask: Callable[[str], str] = input, show: Callable[[str], Any] = print,
    clock_ns: Callable[[], int] = monotonic_ns,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    validate_packet([row])
    if not reviewer_id.strip() or not reviewer_role.strip():
        raise ValueError("Reviewer ID and role are required")
    visible_ids = {event["span_id"] for event in row["visible_events"]}
    ask(f"\nTrial {row['blind_id']}: press Enter when ready to start the diagnosis timer.")
    rendered = json.dumps({"user_prompt": row.get("user_prompt"),
                           "expected_safe_behavior": row.get("expected_safe_behavior"),
                           "blocked_tools": row.get("blocked_tools"),
                           "visible_events": row["visible_events"],
                           "final_response": row.get("final_response")}, indent=2, ensure_ascii=False)
    started_at = now().isoformat()
    start_ns = clock_ns()
    show(rendered)
    while True:
        answer = ask("First visible failure/cause span ID, or 'none': ").strip()
        if answer == "none" or answer in visible_ids:
            break
        show("Enter a visible span ID from this trial, or 'none'.")
    elapsed_ms = round((clock_ns() - start_ns) / 1_000_000, 3)
    answered_at = now().isoformat()
    rationale = ""
    while not rationale:
        rationale = ask("Brief reason for this diagnosis: ").strip()
    return {
        "blind_id": row["blind_id"], "packet_sha256": canonical_hash(row),
        "reviewer_id": reviewer_id.strip(), "reviewer_role": reviewer_role.strip(),
        "candidate_span_id": None if answer == "none" else answer,
        "started_at": started_at, "answered_at": answered_at,
        "elapsed_ms": elapsed_ms, "timing_method": "interactive_monotonic_clock",
        "rationale": rationale,
    }


def _validate_reviews(packet: dict[str, dict[str, Any]], reviews: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for record in reviews:
        blind_id = record.get("blind_id")
        if blind_id not in packet:
            raise ValueError(f"Unknown diagnosis blind ID {blind_id}")
        if record.get("packet_sha256") != canonical_hash(packet[blind_id]):
            raise ValueError(f"Diagnosis packet hash mismatch for {blind_id}")
        reviewer = record.get("reviewer_id")
        if not isinstance(reviewer, str) or not reviewer.strip() or reviewer != reviewer.strip() or not str(record.get("reviewer_role", "")).strip() or not str(record.get("rationale", "")).strip():
            raise ValueError(f"Diagnosis reviewer ID, role, and rationale required for {blind_id}")
        key = (blind_id, reviewer)
        if key in seen:
            raise ValueError(f"Duplicate diagnosis by {reviewer} for {blind_id}")
        seen.add(key)
        candidate = record.get("candidate_span_id")
        visible = {event["span_id"] for event in packet[blind_id]["visible_events"]}
        if candidate is not None and (not isinstance(candidate, str) or candidate not in visible):
            raise ValueError(f"Diagnosis cites a non-visible span for {blind_id}")
        if record.get("timing_method") != "interactive_monotonic_clock":
            raise ValueError(f"Unsupported diagnosis timing method for {blind_id}")
        start = _parsed_timestamp(record.get("started_at"))
        answer = _parsed_timestamp(record.get("answered_at"))
        elapsed = record.get("elapsed_ms")
        if answer < start or isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or not 0 < elapsed <= 3_600_000:
            raise ValueError(f"Invalid diagnosis timing for {blind_id}")
        # Monotonic and UTC clocks need not agree exactly, but large disagreement
        # signals a damaged or manually edited timing record.
        wall_ms = (answer - start).total_seconds() * 1000
        if abs(wall_ms - elapsed) > max(5_000, elapsed * 0.10):
            raise ValueError(f"Diagnosis clocks disagree for {blind_id}")
        by_id[blind_id].append(record)
    if set(by_id) != set(packet) or any(len(by_id[blind_id]) != 2 for blind_id in packet):
        raise ValueError("Diagnosis analysis requires two distinct completed reviewers per trial")
    return by_id


def _validate_references(packet: dict[str, dict[str, Any]], references: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for record in references:
        blind_id = record.get("blind_id")
        if blind_id not in packet or blind_id in by_id:
            raise ValueError(f"Unknown or duplicate diagnosis reference {blind_id}")
        if record.get("packet_sha256") != canonical_hash(packet[blind_id]):
            raise ValueError(f"Diagnosis reference packet hash mismatch for {blind_id}")
        status = record.get("reference_status")
        spans = record.get("accepted_span_ids")
        visible = {event["span_id"] for event in packet[blind_id]["visible_events"]}
        if status not in {"root_present", "no_visible_root", "unscorable"} or not isinstance(spans, list):
            raise ValueError(f"Invalid diagnosis reference status for {blind_id}")
        if (status == "root_present" and (not spans or any(not isinstance(item, str) or item not in visible for item in spans)
                                          or len(spans) != len(set(spans)))) or (status != "root_present" and spans):
            raise ValueError(f"Invalid accepted span IDs for {blind_id}")
        if not str(record.get("adjudicator_id", "")).strip() or not str(record.get("rationale", "")).strip():
            raise ValueError(f"Reference adjudicator and rationale required for {blind_id}")
        _timestamp(record.get("recorded_at"))
        by_id[blind_id] = record
    if set(by_id) != set(packet):
        raise ValueError("Diagnosis references must cover every blinded trial")
    return by_id


def analyze_diagnoses(
    packet: list[dict[str, Any]], mapping: list[dict[str, Any]],
    reviews: list[dict[str, Any]], references: list[dict[str, Any]],
) -> dict[str, Any]:
    by_packet = validate_packet(packet)
    by_map = {row["blind_id"]: row for row in mapping}
    if len(by_map) != len(mapping) or set(by_map) != set(by_packet):
        raise ValueError("Diagnosis private map does not match the packet")
    if len({row.get("trace_id") for row in mapping}) != len(mapping):
        raise ValueError("Diagnosis private map has duplicate trace IDs")
    by_review = _validate_reviews(by_packet, reviews)
    by_reference = _validate_references(by_packet, references)
    for blind_id, records in by_review.items():
        if by_reference[blind_id]["adjudicator_id"] in {record["reviewer_id"] for record in records}:
            raise ValueError("Diagnosis reference adjudicator must be distinct from trial reviewers")
    reviewer_pairs: set[tuple[str, str]] = set()
    for blind_id, records in by_review.items():
        mapping_row = by_map[blind_id]
        for record in records:
            pair_key = (record["reviewer_id"], str(mapping_row["scenario_id"]))
            if pair_key in reviewer_pairs:
                raise ValueError("A diagnosis reviewer saw both conditions of the same pair")
            reviewer_pairs.add(pair_key)
    rows = []
    for blind_id in sorted(by_packet):
        reference = by_reference[blind_id]
        for review in by_review[blind_id]:
            correct = None
            if reference["reference_status"] == "root_present":
                correct = review["candidate_span_id"] in reference["accepted_span_ids"]
            elif reference["reference_status"] == "no_visible_root":
                correct = review["candidate_span_id"] is None
            rows.append({**by_map[blind_id], "blind_id": blind_id,
                         "reviewer_id": review["reviewer_id"],
                         "candidate_span_id": review["candidate_span_id"],
                         "reference_status": reference["reference_status"],
                         "correct": correct, "elapsed_ms": review["elapsed_ms"]})
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[f"{row['architecture']}:{row['mode']}"].append(row)
    summary = {}
    for name, group in sorted(groups.items()):
        scored = [row for row in group if row["correct"] is not None]
        correct = [row for row in scored if row["correct"]]
        summary[name] = {
            "review_n": len(group), "scorable_n": len(scored), "correct_n": len(correct),
            "accuracy": round(len(correct) / len(scored), 6) if scored else None,
            "median_all_elapsed_ms": round(median(row["elapsed_ms"] for row in scored), 3) if scored else None,
            "median_correct_elapsed_ms": round(median(row["elapsed_ms"] for row in correct), 3) if correct else None,
        }
    paired: dict[tuple[str, int, str], dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        paired[(str(row["architecture"]), int(row["trial"]), str(row["scenario_id"]))][str(row["mode"])].append(row)
    paired_rows = []
    for (architecture, trial, scenario_id), conditions in sorted(paired.items()):
        if set(conditions) != {"baseline", "guarded"}:
            raise ValueError("Diagnosis comparison requires both conditions of every pair")
        fully_correct = all(len(conditions[mode]) == 2 and all(row["correct"] is True for row in conditions[mode])
                            for mode in ("baseline", "guarded"))
        difference = (median(row["elapsed_ms"] for row in conditions["baseline"])
                      - median(row["elapsed_ms"] for row in conditions["guarded"])) if fully_correct else None
        paired_rows.append({"architecture": architecture, "trial": trial, "scenario_id": scenario_id,
                            "baseline_correct_n": sum(row["correct"] is True for row in conditions["baseline"]),
                            "guarded_correct_n": sum(row["correct"] is True for row in conditions["guarded"]),
                            "baseline_minus_guarded_ms": round(difference, 3) if difference is not None else None})
    paired_summary = {}
    for architecture in sorted({row["architecture"] for row in paired_rows}):
        group = [row for row in paired_rows if row["architecture"] == architecture]
        complete = [row["baseline_minus_guarded_ms"] for row in group if row["baseline_minus_guarded_ms"] is not None]
        paired_summary[architecture] = {"task_pair_n": len(group), "both_conditions_fully_correct_n": len(complete),
                                        "median_baseline_minus_guarded_ms": round(median(complete), 3) if complete else None}
    return {
        "status": "timed_records_and_reference_claims_checked_identity_not_authenticated",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "packet_sha256": canonical_hash(packet), "mapping_sha256": canonical_hash(mapping),
        "reference_sha256": canonical_hash(references), "reviews_sha256": canonical_hash(reviews),
        "rows": rows, "summary": summary,
        "paired_rows": paired_rows, "paired_summary": paired_summary,
        "actual_diagnosis_time": {
            "unit": "milliseconds", "endpoint": "monotonic time to submitted visible-span answer",
            "median_correct_ms_by_condition": {
                name: values["median_correct_elapsed_ms"] for name, values in summary.items()},
            "paired_correct_baseline_minus_guarded_ms": {
                name: values["median_baseline_minus_guarded_ms"] for name, values in paired_summary.items()},
        },
        "interpretation": "Actual interactive diagnosis duration is recorded with a local monotonic clock, but software cannot verify reviewer identity, uninterrupted attention, or independent reference authorship. Compare conditions only after matched, randomized, blinded human collection and inspect accuracy alongside time.",
    }
