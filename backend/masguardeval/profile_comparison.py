"""Descriptive comparison of two matched, independently sampled guard profiles."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from .study import canonical_hash
from .protocol import protocol_errors


MATCHED_KEYS = (
    "model", "provider", "model_metadata", "provider_endpoint", "source_hashes",
    "dataset_sha256", "scenario_ids",
    "architectures", "trials_per_scenario", "max_tool_calls", "temperature", "seed",
    "max_output_tokens",
)


def compare_guard_profiles(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    completed_statuses = {"complete", "complete_with_protocol_errors"}
    if left.get("status") not in completed_statuses or right.get("status") not in completed_statuses:
        raise ValueError("Both experiment reports must contain every scheduled pair")
    if left.get("guard_profile") == right.get("guard_profile"):
        raise ValueError("Reports must use different guard profiles")
    for key in MATCHED_KEYS:
        if left.get(key) != right.get(key):
            raise ValueError(f"Reports differ in matched field {key}")

    def index(report: dict[str, Any]) -> dict[tuple[str, int, str], dict[str, Any]]:
        result = {(row["architecture"], row["trial"], row["scenario"]["scenario_id"]): row
                  for row in report["results"]}
        if len(result) != len(report["results"]):
            raise ValueError("Report contains duplicate task trials")
        return result

    left_rows, right_rows = index(left), index(right)
    if set(left_rows) != set(right_rows):
        raise ValueError("Reports do not contain the same task trials")
    rows = []
    metric_differences: dict[str, list[float]] = defaultdict(list)
    for key in sorted(left_rows):
        a, b = left_rows[key], right_rows[key]
        if a["scenario"] != b["scenario"]:
            raise ValueError("Matched scenario payloads differ")
        a_trace, b_trace = a["guarded_trace"], b["guarded_trace"]
        valid_pair = not protocol_errors(a) and not protocol_errors(b)
        if valid_pair:
            for metric, a_metric in a["guarded_metrics"].items():
                b_metric = b["guarded_metrics"].get(metric)
                if b_metric and a_metric["applicable"] and b_metric["applicable"]:
                    metric_differences[metric].append(float(b_metric["score"]) - float(a_metric["score"]))
        rows.append({
            "architecture": key[0], "trial": key[1], "scenario_id": key[2],
            "risk_type": a["scenario"]["risk_type"],
            "protocol_valid_in_both_profiles": valid_pair,
            left["guard_profile"]: {
                "blocked": a_trace["blocked"],
                "executed_tool_calls": sum(span["span_type"] == "tool_call" for span in a_trace["spans"]),
            },
            right["guard_profile"]: {
                "blocked": b_trace["blocked"],
                "executed_tool_calls": sum(span["span_type"] == "tool_call" for span in b_trace["spans"]),
            },
        })
    return {
        "status": "descriptive_unadjudicated_profile_comparison",
        "model": left["model"], "provider": left["provider"],
        "model_metadata": left.get("model_metadata"),
        "dataset_sha256": left["dataset_sha256"],
        "left_report_content_sha256": canonical_hash(left),
        "right_report_content_sha256": canonical_hash(right),
        "left_profile": left["guard_profile"], "right_profile": right["guard_profile"],
        "matched_pair_n": len(rows),
        "protocol_valid_matched_pair_n": sum(row["protocol_valid_in_both_profiles"] for row in rows),
        "protocol_invalid_pair_ids": [f"{row['architecture']}:{row['trial']}:{row['scenario_id']}"
                                      for row in rows if not row["protocol_valid_in_both_profiles"]],
        "left_blocked_n": sum(row[left["guard_profile"]]["blocked"] for row in rows),
        "right_blocked_n": sum(row[right["guard_profile"]]["blocked"] for row in rows),
        "metric_score_difference_right_minus_left": {
            metric: {"applicable_pair_n": len(values), "mean": round(mean(values), 6)}
            for metric, values in sorted(metric_differences.items())
        },
        "pairs": rows,
        "interpretation": "Independent model calls may differ despite matched configuration. Block counts include all recorded pairs; metric score differences exclude pairs with adapter protocol errors. Neither is an independently judged task outcome.",
    }
