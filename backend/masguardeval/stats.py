"""Exploratory paired summaries with scenario-level uncertainty."""

from __future__ import annotations

from collections import defaultdict
from itertools import product
from random import Random
from statistics import mean, stdev
from typing import Any


LOWER_IS_BETTER = {"PHR", "CPI", "CFP", "CCR", "DT"}


def summarize_trials(results: list[dict[str, Any]], *, seed: int = 23, bootstrap_samples: int = 2000) -> dict[str, Any]:
    """Average within task first, so repeated runs do not masquerade as new tasks."""
    groups: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for result in results:
        architecture = str(result["architecture"])
        scenario_id = str(result["scenario"]["scenario_id"])
        for key, baseline in result["baseline_metrics"].items():
            guarded = result["guarded_metrics"].get(key)
            if not guarded or not baseline["applicable"] or not guarded["applicable"]:
                continue
            raw = guarded["score"] - baseline["score"]
            groups[(architecture, key, scenario_id)].append(-raw if key in LOWER_IS_BETTER else raw)

    by_metric: dict[tuple[str, str], list[tuple[str, list[float]]]] = defaultdict(list)
    for (architecture, key, scenario_id), values in groups.items():
        by_metric[(architecture, key)].append((scenario_id, values))

    summary: dict[str, Any] = {}
    for (architecture, key), scenarios in sorted(by_metric.items()):
        scenarios.sort(key=lambda item: item[0])
        task_means = [mean(values) for _, values in scenarios]
        n = len(task_means)
        row: dict[str, Any] = {
            "metric": key, "direction": "positive means guarded improved",
            "scenario_n": n, "trial_pair_n": sum(len(values) for _, values in scenarios),
            "mean_improvement": round(mean(task_means), 6),
            "scenario_sd": round(stdev(task_means), 6) if n > 1 else None,
            "ci_95_scenario_bootstrap": None, "sign_flip_p_two_sided": None,
            "scenario_means": {scenario_id: round(mean(values), 6) for scenario_id, values in scenarios},
        }
        if n > 1:
            rng = Random(f"{seed}:{architecture}:{key}")
            draws = sorted(mean(rng.choices(task_means, k=n)) for _ in range(bootstrap_samples))
            row["ci_95_scenario_bootstrap"] = [round(draws[int(0.025 * (bootstrap_samples - 1))], 6), round(draws[int(0.975 * (bootstrap_samples - 1))], 6)]
            observed = abs(mean(task_means))
            if n <= 16:
                null = [abs(mean(value * sign for value, sign in zip(task_means, signs))) for signs in product((-1, 1), repeat=n)]
            else:
                null = [abs(mean(value * rng.choice((-1, 1)) for value in task_means)) for _ in range(10000)]
            row["sign_flip_p_two_sided"] = round(sum(value >= observed - 1e-12 for value in null) / len(null), 6)
        summary.setdefault(architecture, {})[key] = row
    return {
        "method": "Scenario-clustered descriptive paired analysis. Bootstrap is percentile resampling; sign-flip is unadjusted across metrics.",
        "seed": seed,
        "architectures": summary,
    }
