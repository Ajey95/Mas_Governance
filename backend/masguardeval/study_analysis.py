"""Held-out primary-outcome and trace-metric validation for reviewed trials."""

from __future__ import annotations

from collections import defaultdict
from random import Random
from statistics import mean
from typing import Any

from .dataset import GoldenDataset
from .stats import LOWER_IS_BETTER
from .study import canonical_hash
from .protocol import protocol_errors


OUTCOMES = ("task_failure", "prohibited_action")


def _auc(positive_scores: list[float], negative_scores: list[float]) -> float | None:
    if not positive_scores or not negative_scores:
        return None
    wins = sum((1.0 if positive > negative else 0.5 if positive == negative else 0.0)
               for positive in positive_scores for negative in negative_scores)
    return round(wins / (len(positive_scores) * len(negative_scores)), 6)


def _threshold(scores: list[tuple[float, bool]]) -> float | None:
    positives = sum(label for _, label in scores)
    negatives = len(scores) - positives
    if not positives or not negatives:
        return None
    unique = sorted({score for score, _ in scores})
    candidates = unique + [unique[-1] + 1e-9]

    def balanced_accuracy(cutoff: float) -> float:
        sensitivity = sum(score >= cutoff and label for score, label in scores) / positives
        specificity = sum(score < cutoff and not label for score, label in scores) / negatives
        return (sensitivity + specificity) / 2

    return max(candidates, key=lambda cutoff: (balanced_accuracy(cutoff), cutoff))


def _binary_performance(scores: list[tuple[float, bool]], cutoff: float | None) -> dict[str, Any]:
    positives = [score for score, label in scores if label]
    negatives = [score for score, label in scores if not label]
    result: dict[str, Any] = {
        "n": len(scores), "positive_n": len(positives), "negative_n": len(negatives),
        "auc": _auc(positives, negatives), "threshold": cutoff,
        "sensitivity": None, "specificity": None, "balanced_accuracy": None,
    }
    if cutoff is not None and positives and negatives:
        result["sensitivity"] = round(sum(score >= cutoff for score in positives) / len(positives), 6)
        result["specificity"] = round(sum(score < cutoff for score in negatives) / len(negatives), 6)
        result["balanced_accuracy"] = round((result["sensitivity"] + result["specificity"]) / 2, 6)
    return result


def _run_metrics(report: dict[str, Any], *, protocol_valid_only: bool = False) -> dict[str, dict[str, Any]]:
    runs = {}
    for result in report["results"]:
        if protocol_valid_only and protocol_errors(result):
            continue
        for mode in ("baseline", "guarded"):
            trace_id = result[f"{mode}_trace"]["trace_id"]
            if trace_id in runs:
                raise ValueError(f"Duplicate trace ID {trace_id}")
            runs[trace_id] = result[f"{mode}_metrics"]
    return runs


def _checked_outcomes(report: dict[str, Any], labels: dict[str, Any], dataset: GoldenDataset) -> dict[str, dict[str, Any]]:
    if report.get("status") not in {"complete", "complete_with_protocol_errors"}:
        raise ValueError("Experiment report must contain every scheduled pair before analysis")
    expected_ids = {scenario.scenario_id for scenario in dataset.scenarios}
    if set(report["scenario_ids"]) != expected_ids:
        raise ValueError("Experiment scenarios do not match the frozen dataset")
    expected_pairs = len(expected_ids) * len(report["architectures"]) * int(report["trials_per_scenario"])
    keys = {(item["architecture"], item["trial"], item["scenario"]["scenario_id"]) for item in report["results"]}
    if len(report["results"]) != expected_pairs or len(keys) != expected_pairs:
        raise ValueError("Experiment does not contain every scheduled pair exactly once")
    for result in report["results"]:
        if canonical_hash(result["scenario"]) != canonical_hash(dataset.get(result["scenario"]["scenario_id"]).to_dict()):
            raise ValueError("Experiment scenario differs from the frozen dataset")
    metrics = _run_metrics(report)
    by_trace = {row["trace_id"]: row for row in labels["outcomes"]}
    if len(by_trace) != len(labels["outcomes"]) or set(by_trace) != set(metrics):
        raise ValueError("Independent outcome labels must cover each trace exactly once")
    if any(type(row.get(key)) is not bool for row in by_trace.values() for key in OUTCOMES):
        raise ValueError("Outcome labels must be booleans")
    return by_trace


def _paired_outcomes(report: dict[str, Any], by_trace: dict[str, dict[str, Any]], *, seed: int) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for result in report["results"]:
        scenario_id = result["scenario"]["scenario_id"]
        architecture = result["architecture"]
        for outcome in OUTCOMES:
            baseline = by_trace[result["baseline_trace"]["trace_id"]][outcome]
            guarded = by_trace[result["guarded_trace"]["trace_id"]][outcome]
            grouped[(architecture, outcome, scenario_id)].append(int(baseline) - int(guarded))
    rows: dict[str, Any] = {}
    architectures = sorted({key[0] for key in grouped})
    for architecture in architectures:
        for outcome in OUTCOMES:
            tasks = {scenario_id: mean(values) for (arch, name, scenario_id), values in grouped.items()
                     if arch == architecture and name == outcome}
            values = list(tasks.values())
            rng = Random(f"{seed}:{architecture}:{outcome}")
            draws = sorted(mean(rng.choices(values, k=len(values))) for _ in range(2000)) if len(values) > 1 else []
            rows[f"{architecture}:{outcome}"] = {
                "scenario_n": len(values), "trial_pair_n": sum(len(grouped[(architecture, outcome, sid)]) for sid in tasks),
                "mean_absolute_risk_reduction": round(mean(values), 6),
                "ci_95_scenario_bootstrap": [round(draws[49], 6), round(draws[1949], 6)] if draws else None,
                "scenario_means": {sid: round(value, 6) for sid, value in sorted(tasks.items())},
            }
    return rows


def _metric_scores(report: dict[str, Any], by_trace: dict[str, dict[str, Any]], outcome: str) -> dict[str, list[tuple[float, bool]]]:
    groups: dict[str, list[tuple[float, bool]]] = defaultdict(list)
    for trace_id, metrics in _run_metrics(report, protocol_valid_only=True).items():
        for key, value in metrics.items():
            if value.get("applicable") and value.get("score") is not None:
                score = float(value["score"])
                groups[key].append((score if key in LOWER_IS_BETTER else 1 - score, by_trace[trace_id][outcome]))
    return groups


def analyze_study(
    development_report: dict[str, Any], development_labels: dict[str, Any], development_dataset: GoldenDataset,
    heldout_report: dict[str, Any], heldout_labels: dict[str, Any], heldout_dataset: GoldenDataset,
    manifest: dict[str, Any], *, seed: int = 23,
) -> dict[str, Any]:
    if manifest.get("development_sha256") != canonical_hash(development_dataset.to_dict()) or manifest.get("heldout_sha256") != canonical_hash(heldout_dataset.to_dict()):
        raise ValueError("Frozen dataset hashes do not match the study manifest")
    for key in ("model", "provider", "model_metadata", "architectures", "trials_per_scenario", "max_tool_calls"):
        if development_report.get(key) != heldout_report.get(key):
            raise ValueError(f"Development and held-out experiments differ in {key}")
    development = _checked_outcomes(development_report, development_labels, development_dataset)
    heldout = _checked_outcomes(heldout_report, heldout_labels, heldout_dataset)
    if set(development) & set(heldout):
        raise ValueError("Development and held-out traces overlap")
    metrics = {}
    for outcome in OUTCOMES:
        dev_scores = _metric_scores(development_report, development, outcome)
        test_scores = _metric_scores(heldout_report, heldout, outcome)
        for metric in sorted(set(dev_scores) | set(test_scores)):
            cutoff = _threshold(dev_scores.get(metric, []))
            metrics[f"{metric}:{outcome}"] = {
                "direction": "higher risk score predicts adverse outcome",
                "development": _binary_performance(dev_scores.get(metric, []), cutoff),
                "heldout": _binary_performance(test_scores.get(metric, []), cutoff),
            }
    return {
        "status": "analysis_of_submitted_labels_identity_not_verified_by_software",
        "primary_outcomes": {
            "development": _paired_outcomes(development_report, development, seed=seed),
            "heldout": _paired_outcomes(heldout_report, heldout, seed=seed),
        },
        "protocol_failure_pairs": {
            "development": sum(bool(protocol_errors(row)) for row in development_report["results"]),
            "heldout": sum(bool(protocol_errors(row)) for row in heldout_report["results"]),
        },
        "metric_construct_checks": metrics,
        "interpretation": "Primary outcomes include independently labelled protocol failures; metric construct checks exclude those pairs. Specify this handling before confirmatory trials. Thresholds are selected on development labels only, and held-out results remain descriptive until reviewer provenance and preregistered analysis are independently verified.",
    }
