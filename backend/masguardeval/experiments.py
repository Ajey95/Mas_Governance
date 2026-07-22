from __future__ import annotations

from dataclasses import dataclass, field

from .guards import RBACGuard, default_guards
from .models import EvaluationResult
from .runner import EvaluationEngine


@dataclass(frozen=True)
class ExperimentReport:
    scenario_count: int
    scenario_rows: list[dict[str, object]]
    metric_table: dict[str, dict[str, float]]
    ablation_table: dict[str, dict[str, float | int]]
    results: list[EvaluationResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_count": self.scenario_count,
            "scenario_rows": self.scenario_rows,
            "metric_table": self.metric_table,
            "ablation_table": self.ablation_table,
            "results": [result.to_dict() for result in self.results],
        }

    def to_markdown(self) -> str:
        lines = [
            "# MASGuardEval Experiment Report",
            "",
            f"Scenarios evaluated: **{self.scenario_count}**",
            "",
            "## Scenario Results",
            "",
            "| Scenario | Risk Type | Baseline RSS | Guarded RSS | RSS Delta |",
            "|---|---|---:|---:|---:|",
        ]
        for row in self.scenario_rows:
            lines.append(
                "| {scenario_id} | {risk_type} | {baseline_RSS:.4f} | {guarded_RSS:.4f} | {rss_delta:.4f} |".format(
                    scenario_id=row["scenario_id"],
                    risk_type=row["risk_type"],
                    baseline_RSS=float(row["baseline_RSS"]),
                    guarded_RSS=float(row["guarded_RSS"]),
                    rss_delta=float(row["rss_delta"]),
                )
            )

        lines.extend(
            [
                "",
                "## Metric Summary",
                "",
                "| Metric | Baseline Avg | Guarded Avg | Delta |",
                "|---|---:|---:|---:|",
            ]
        )
        for metric, values in self.metric_table.items():
            lines.append(
                f"| {metric} | {values['baseline_avg']:.4f} | {values['guarded_avg']:.4f} | {values['delta']:.4f} |"
            )

        lines.extend(
            [
                "",
                "## Guard Ablation",
                "",
                "| Guard Stack | Scenarios | Blocked Actions | Guarded RSS Avg |",
                "|---|---:|---:|---:|",
            ]
        )
        for stack, values in self.ablation_table.items():
            lines.append(
                f"| {stack} | {values['scenario_count']} | {values['blocked_actions']} | {float(values['guarded_RSS_avg']):.4f} |"
            )
        lines.append("")
        return "\n".join(lines)


class ExperimentSuite:
    """Runs broad scenario experiments and guard-stack ablations."""

    def __init__(self, engine: EvaluationEngine) -> None:
        self.engine = engine

    def run(self) -> ExperimentReport:
        results = self.engine.evaluate_all()
        return ExperimentReport(
            scenario_count=len(results),
            scenario_rows=self._scenario_rows(results),
            metric_table=self._metric_table(results),
            ablation_table=self._ablation_table(),
            results=results,
        )

    def _scenario_rows(self, results: list[EvaluationResult]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for result in results:
            baseline_rss = result.baseline_metrics["RSS"].score
            guarded_rss = result.guarded_metrics["RSS"].score
            rows.append(
                {
                    "scenario_id": result.scenario.scenario_id,
                    "risk_type": result.scenario.risk_type,
                    "baseline_RSS": round(baseline_rss, 4),
                    "guarded_RSS": round(guarded_rss, 4),
                    "rss_delta": round(guarded_rss - baseline_rss, 4),
                    "baseline_blocked": result.baseline_trace.blocked,
                    "guarded_blocked": result.guarded_trace.blocked,
                }
            )
        return rows

    def _metric_table(self, results: list[EvaluationResult]) -> dict[str, dict[str, float]]:
        metric_keys = ["TSP", "TSR", "PHR", "CPI", "CFP", "RSS", "CCR", "DT"]
        table: dict[str, dict[str, float]] = {}
        for key in metric_keys:
            baseline = [result.baseline_metrics[key].score for result in results if key in result.baseline_metrics]
            guarded = [result.guarded_metrics[key].score for result in results if key in result.guarded_metrics]
            if baseline and guarded:
                table[key] = {
                    "baseline_avg": round(sum(baseline) / len(baseline), 4),
                    "guarded_avg": round(sum(guarded) / len(guarded), 4),
                    "delta": round((sum(guarded) / len(guarded)) - (sum(baseline) / len(baseline)), 4),
                }
        return table

    def _ablation_table(self) -> dict[str, dict[str, float | int]]:
        stacks = {
            "no_guards": [],
            "rbac_only": [RBACGuard()],
            "full_guard_stack": default_guards(),
        }
        table: dict[str, dict[str, float | int]] = {}
        for name, guards in stacks.items():
            ablation_engine = EvaluationEngine(
                dataset=self.engine.dataset,
                adapter=self.engine.adapter,
                guards=guards,
                metric_engine=self.engine.metric_engine,
            )
            results = ablation_engine.evaluate_all()
            blocked = sum(1 for result in results if result.guarded_trace.blocked)
            rss = [result.guarded_metrics["RSS"].score for result in results]
            table[name] = {
                "scenario_count": len(results),
                "blocked_actions": blocked,
                "guarded_RSS_avg": round(sum(rss) / len(rss), 4) if rss else 0.0,
            }
        return table
