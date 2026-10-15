from __future__ import annotations

from dataclasses import dataclass, field

from .adapters import DeterministicWorkspaceAdapter
from .guards import RBACGuard, default_guards
from .models import EvaluationResult
from .runner import EvaluationEngine


@dataclass(frozen=True)
class ExperimentReport:
    scenario_count: int
    scenario_rows: list[dict[str, object]]
    metric_table: dict[str, dict[str, float | int | None]]
    ablation_table: dict[str, dict[str, float | int | None]]
    adapter_name: str
    execution_kind: str
    results: list[EvaluationResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_count": self.scenario_count,
            "adapter_name": self.adapter_name,
            "execution_kind": self.execution_kind,
            "scenario_rows": self.scenario_rows,
            "metric_table": self.metric_table,
            "ablation_table": self.ablation_table,
            "results": [result.to_dict() for result in self.results],
        }

    def to_markdown(self) -> str:
        lines = [
            "# MASGuardEval Experiment Report",
            "",
            f"Adapter: **{self.adapter_name}**; execution kind: **{self.execution_kind}**.",
            "The built-in reference adapter uses scripted intents, not a live LLM." if self.execution_kind == "isolated_mock_workspace" else "Custom adapter provenance must be documented separately.",
            "These outputs describe the recorded runs only. They are not independent human validation.",
            "",
            f"Scenarios evaluated: **{self.scenario_count}**",
            "",
            "## Scenario Results",
            "",
            "| Scenario | Risk Type | Baseline RSS | Guarded RSS | RSS Delta |",
            "|---|---|---:|---:|---:|",
        ]
        for row in self.scenario_rows:
            fmt = lambda value: "N/A" if value is None else f"{float(value):.4f}"
            lines.append(f"| {row['scenario_id']} | {row['risk_type']} | {fmt(row['baseline_RSS'])} | {fmt(row['guarded_RSS'])} | {fmt(row['rss_delta'])} |")

        lines.extend(
            [
                "",
                "## Metric Summary",
                "",
                "| Metric | Baseline Avg (paired n) | Guarded Avg (paired n) | Delta | Applicable baseline / guarded |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for metric, values in self.metric_table.items():
            fmt = lambda value: "N/A" if value is None else f"{float(value):.4f}"
            lines.append(f"| {metric} | {fmt(values['baseline_avg'])} ({values['paired_n']}) | {fmt(values['guarded_avg'])} ({values['paired_n']}) | {fmt(values['delta'])} | {values['baseline_n']} / {values['guarded_n']} |")

        lines.extend(
            [
                "",
                "Delta is guarded minus baseline on the same applicable scenarios; lower scores are safer for PHR, CPI, CFP, CCR, and DT. Applicability counts may differ by run.",
                "",
                "## Guard Ablation",
                "",
                "| Guard Stack | Scenarios | Blocked Runs | Guarded RSS Avg (n) |",
                "|---|---:|---:|---:|",
            ]
        )
        for stack, values in self.ablation_table.items():
            rss_avg = "N/A" if values["guarded_RSS_avg"] is None else f"{float(values['guarded_RSS_avg']):.4f}"
            lines.append(
                f"| {stack} | {values['scenario_count']} | {values['blocked_runs']} | {rss_avg} ({values['rss_n']}) |"
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
            adapter_name=self.engine.adapter.name,
            execution_kind=getattr(self.engine.adapter, "execution_kind", "isolated_mock_workspace" if isinstance(self.engine.adapter, DeterministicWorkspaceAdapter) else "custom_adapter"),
            results=results,
        )

    def _scenario_rows(self, results: list[EvaluationResult]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for result in results:
            baseline_rss = result.baseline_metrics["RSS"].score if result.baseline_metrics["RSS"].applicable else None
            guarded_rss = result.guarded_metrics["RSS"].score if result.guarded_metrics["RSS"].applicable else None
            rows.append(
                {
                    "scenario_id": result.scenario.scenario_id,
                    "risk_type": result.scenario.risk_type,
                    "baseline_RSS": round(baseline_rss, 4) if baseline_rss is not None else None,
                    "guarded_RSS": round(guarded_rss, 4) if guarded_rss is not None else None,
                    "rss_delta": round(guarded_rss - baseline_rss, 4) if baseline_rss is not None and guarded_rss is not None else None,
                    "baseline_blocked": result.baseline_trace.blocked,
                    "guarded_blocked": result.guarded_trace.blocked,
                }
            )
        return rows

    def _metric_table(self, results: list[EvaluationResult]) -> dict[str, dict[str, float | int | None]]:
        metric_keys = ["TSP", "TSR", "PHR", "CPI", "CFP", "RSS", "CCR", "DT"]
        table: dict[str, dict[str, float | int | None]] = {}
        for key in metric_keys:
            baseline_n = sum(key in result.baseline_metrics and result.baseline_metrics[key].applicable for result in results)
            guarded_n = sum(key in result.guarded_metrics and result.guarded_metrics[key].applicable for result in results)
            paired = [result for result in results if key in result.baseline_metrics and key in result.guarded_metrics and result.baseline_metrics[key].applicable and result.guarded_metrics[key].applicable]
            baseline = [result.baseline_metrics[key].score for result in paired]
            guarded = [result.guarded_metrics[key].score for result in paired]
            if baseline_n or guarded_n:
                baseline_avg = sum(baseline) / len(baseline) if baseline else None
                guarded_avg = sum(guarded) / len(guarded) if guarded else None
                table[key] = {
                    "baseline_avg": round(baseline_avg, 4) if baseline_avg is not None else None,
                    "guarded_avg": round(guarded_avg, 4) if guarded_avg is not None else None,
                    "baseline_n": baseline_n,
                    "guarded_n": guarded_n,
                    "paired_n": len(paired),
                    "delta": round(guarded_avg - baseline_avg, 4) if baseline_avg is not None and guarded_avg is not None else None,
                }
        return table

    def _ablation_table(self) -> dict[str, dict[str, float | int | None]]:
        stacks = {
            "no_guards": [],
            "rbac_only": [RBACGuard()],
            "full_guard_stack": default_guards(),
        }
        for index, guard in enumerate(default_guards()):
            stacks[f"without_{guard.name}"] = [candidate for i, candidate in enumerate(default_guards()) if i != index]
        table: dict[str, dict[str, float | int | None]] = {}
        for name, guards in stacks.items():
            ablation_engine = EvaluationEngine(
                dataset=self.engine.dataset,
                adapter=self.engine.adapter,
                guards=guards,
                metric_engine=self.engine.metric_engine,
            )
            ablation_engine.tool_handlers.update(self.engine.tool_handlers)
            results = ablation_engine.evaluate_all()
            blocked = sum(1 for result in results if result.guarded_trace.blocked)
            rss = [result.guarded_metrics["RSS"].score for result in results if result.guarded_metrics["RSS"].applicable]
            table[name] = {
                "scenario_count": len(results),
                "blocked_runs": blocked,
                "rss_n": len(rss),
                "guarded_RSS_avg": round(sum(rss) / len(rss), 4) if rss else None,
            }
        return table
