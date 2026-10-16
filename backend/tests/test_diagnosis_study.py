from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

import pytest

from masguardeval import EvaluationEngine, GoldenDataset
from masguardeval.diagnosis_study import analyze_diagnoses, assign_diagnosis_panels, capture_diagnosis, reference_template
from masguardeval.outcome_review import make_outcome_packet
from masguardeval.cli import main


DATASET = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


def _packet():
    result = EvaluationEngine(GoldenDataset.load(DATASET)).evaluate("auth_001")
    return make_outcome_packet({"results": [{"architecture": "single", "trial": 1, **result.to_dict()}]})


def _timed_record(row, reviewer, candidate):
    start = datetime(2026, 10, 16, 10, tzinfo=timezone.utc)
    return {"blind_id": row["blind_id"], "packet_sha256": reference_template([row])[0]["packet_sha256"],
            "reviewer_id": reviewer, "reviewer_role": "domain_expert", "candidate_span_id": candidate,
            "started_at": start.isoformat(), "answered_at": (start + timedelta(seconds=2)).isoformat(),
            "elapsed_ms": 2000, "timing_method": "interactive_monotonic_clock", "rationale": "Visible event reviewed"}


def test_capture_measures_until_span_answer_and_keeps_rationale_outside_timer():
    packet, _ = _packet()
    row = packet[0]
    candidate = row["visible_events"][0]["span_id"]
    inputs = iter(["", "invalid", candidate, "Reason"])
    ticks = iter([1_000_000_000, 3_000_000_000])
    start = datetime(2026, 10, 16, 10, tzinfo=timezone.utc)
    times = iter([start, start + timedelta(seconds=2)])
    messages = []
    record = capture_diagnosis(row, "reviewer_a", "expert", ask=lambda _: next(inputs),
                               show=messages.append, clock_ns=lambda: next(ticks), now=lambda: next(times))
    assert record["candidate_span_id"] == candidate
    assert record["elapsed_ms"] == 2000
    assert record["timing_method"] == "interactive_monotonic_clock"
    assert any("visible span ID" in message for message in messages)


def test_analysis_requires_two_reviewers_and_independent_reference():
    packet, mapping = _packet()
    references = reference_template(packet)
    reviews = []
    for index, (row, reference) in enumerate(zip(packet, references)):
        candidate = row["visible_events"][0]["span_id"]
        reference.update(reference_status="root_present", accepted_span_ids=[candidate],
                         adjudicator_id="expert_c", recorded_at="2026-10-16T10:10:00+00:00",
                         rationale="Independent adjudication fixture")
        reviews.extend([_timed_record(row, reviewer, candidate) for reviewer in
                        (("a", "b") if index == 0 else ("c", "d"))])
    result = analyze_diagnoses(packet, mapping, reviews, references)
    assert len(result["rows"]) == 4
    assert all(row["correct"] for row in result["rows"])
    assert all(group["median_correct_elapsed_ms"] == 2000 for group in result["summary"].values())
    assert result["paired_summary"]["single"]["median_baseline_minus_guarded_ms"] == 0
    assert result["actual_diagnosis_time"]["median_correct_ms_by_condition"] == {
        "single:baseline": 2000, "single:guarded": 2000}
    with pytest.raises(ValueError, match="two distinct"):
        analyze_diagnoses(packet, mapping, reviews[:-1], references)
    bad = [*reviews]
    bad[0] = {**bad[0], "packet_sha256": "changed"}
    with pytest.raises(ValueError, match="hash mismatch"):
        analyze_diagnoses(packet, mapping, bad, references)
    bad_ref = [*references]
    bad_ref[0] = {**bad_ref[0], "accepted_span_ids": ["hidden-span"]}
    with pytest.raises(ValueError, match="accepted span"):
        analyze_diagnoses(packet, mapping, reviews, bad_ref)
    overlapping = [*reviews]
    overlapping[2] = {**overlapping[2], "reviewer_id": "a"}
    with pytest.raises(ValueError, match="both conditions"):
        analyze_diagnoses(packet, mapping, overlapping, references)


def test_assignment_keeps_each_reviewer_panel_on_one_condition():
    packet, mapping = _packet()
    panels, manifest = assign_diagnosis_panels(packet, mapping)
    assert set(panels) == {"panel_a_1", "panel_a_2", "panel_b_1", "panel_b_2"}
    assert all(len(rows) == 1 for rows in panels.values())
    assert {entry["mode"] for entry in manifest["assignments"]} == {"baseline", "guarded"}
    assert panels["panel_a_1"][0]["blind_id"] == panels["panel_a_2"][0]["blind_id"]
    assert panels["panel_a_1"][0]["blind_id"] != panels["panel_b_1"][0]["blind_id"]


def test_diagnosis_cli_prepares_blinded_packet_and_analyzes_records(tmp_path):
    result = EvaluationEngine(GoldenDataset.load(DATASET)).evaluate("auth_001")
    experiment = tmp_path / "experiment.json"
    experiment.write_text(json.dumps({"results": [{"architecture": "single", "trial": 1,
                                                  **result.to_dict()}]}), encoding="utf-8")
    review_dir = tmp_path / "reviewer"
    private_map = tmp_path / "private" / "map.json"
    assert main(["diagnosis-packet", "--report", str(experiment), "--architecture", "single", "--trial", "1",
                 "--review-out", str(review_dir), "--private-map-out", str(private_map)]) == 0
    packet = [json.loads(line) for line in (review_dir / "blinded_trials.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(packet) == 2
    assert all("mode" not in row and "trace_id" not in row for row in packet)
    assert all("failure_label" not in event and event["type"] != "guard_decision"
               for row in packet for event in row["visible_events"])
    panel_dir = tmp_path / "panels"
    assert main(["diagnosis-assign", "--packet", str(review_dir / "blinded_trials.jsonl"),
                 "--private-map", str(private_map), "--out-dir", str(panel_dir),
                 "--private-manifest-out", str(tmp_path / "private" / "assignment.json")]) == 0
    refs_path = tmp_path / "references.jsonl"
    assert main(["diagnosis-reference-template", "--packet", str(review_dir / "blinded_trials.jsonl"),
                 "--out", str(refs_path)]) == 0
    references = [json.loads(line) for line in refs_path.read_text(encoding="utf-8").splitlines()]
    review_paths = [tmp_path / f"review-{name}.jsonl" for name in
                    ("panel_a_1", "panel_a_2", "panel_b_1", "panel_b_2")]
    for row, reference in zip(packet, references):
        candidate = row["visible_events"][0]["span_id"]
        reference.update(reference_status="root_present", accepted_span_ids=[candidate],
                         adjudicator_id="reference_expert", recorded_at="2026-10-16T10:10:00+00:00",
                         rationale="Test-only reference")
    refs_path.write_text("".join(json.dumps(row) + "\n" for row in references), encoding="utf-8")
    for path, reviewer in zip(review_paths, ("panel_a_1", "panel_a_2", "panel_b_1", "panel_b_2")):
        assigned = [json.loads(line) for line in (panel_dir / f"{reviewer}.jsonl").read_text(encoding="utf-8").splitlines()]
        path.write_text("".join(json.dumps(_timed_record(row, reviewer, row["visible_events"][0]["span_id"])) + "\n"
                                for row in assigned), encoding="utf-8")
    analysis_path = tmp_path / "diagnosis-analysis.json"
    assert main(["diagnosis-analyze", "--packet", str(review_dir / "blinded_trials.jsonl"),
                 "--private-map", str(private_map), "--reviews", *map(str, review_paths),
                 "--reference", str(refs_path), "--out", str(analysis_path)]) == 0
    assert len(json.loads(analysis_path.read_text(encoding="utf-8"))["rows"]) == 4
