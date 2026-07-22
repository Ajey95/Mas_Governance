from __future__ import annotations

from pathlib import Path

from .adapters import AgentSystemAdapter, DeterministicWorkspaceAdapter
from .dataset import GoldenDataset
from .guards import Guard, default_guards
from .metrics import MetricEngine, recommendations_for
from .models import EvaluationResult, ExecutionEvent, PolicyDecision, Scenario, Span, Trace


class EvaluationEngine:
    """Public SDK for registering systems, tools, guards, datasets, and running experiments."""

    def __init__(
        self,
        dataset: GoldenDataset,
        adapter: AgentSystemAdapter | None = None,
        guards: list[Guard] | None = None,
        metric_engine: MetricEngine | None = None,
    ) -> None:
        self.dataset = dataset
        self.adapter = adapter or DeterministicWorkspaceAdapter()
        self.guards = guards or default_guards()
        self.metric_engine = metric_engine or MetricEngine()
        self.registered_agents: set[str] = set()
        self.registered_tools: set[str] = set()

    @classmethod
    def from_dataset_path(cls, path: str | Path) -> "EvaluationEngine":
        return cls(GoldenDataset.load(path))

    def register_agent(self, name: str) -> None:
        self.registered_agents.add(name)

    def register_tool(self, name: str) -> None:
        self.registered_tools.add(name)

    def register_guard(self, guard: Guard) -> None:
        self.guards.append(guard)

    def run_baseline(self, scenario: Scenario) -> Trace:
        return self._execute(scenario, mode="baseline")

    def run_guarded(self, scenario: Scenario) -> Trace:
        return self._execute(scenario, mode="guarded")

    def compute_metrics(self, scenario: Scenario, trace: Trace):
        return self.metric_engine.compute(scenario, trace)

    def evaluate(self, scenario_id: str) -> EvaluationResult:
        scenario = self.dataset.get(scenario_id)
        baseline_trace = self.run_baseline(scenario)
        guarded_trace = self.run_guarded(scenario)
        baseline_metrics = self.compute_metrics(scenario, baseline_trace)
        guarded_metrics = self.compute_metrics(scenario, guarded_trace)
        recs = recommendations_for(baseline_metrics)
        return EvaluationResult(
            scenario=scenario,
            baseline_trace=baseline_trace,
            guarded_trace=guarded_trace,
            baseline_metrics=baseline_metrics,
            guarded_metrics=guarded_metrics,
            recommendations=recs,
        )

    def evaluate_all(self) -> list[EvaluationResult]:
        return [self.evaluate(scenario.scenario_id) for scenario in self.dataset.scenarios]

    def generate_dashboard(self) -> dict[str, object]:
        results = [result.to_dict() for result in self.evaluate_all()]
        return {
            "dataset": self.dataset.to_dict(),
            "results": results,
            "summary": self._summary(results),
            "adapter": self.adapter.name,
            "guards": [guard.name for guard in self.guards],
        }

    def _execute(self, scenario: Scenario, mode: str) -> Trace:
        trace = Trace.start(scenario.scenario_id, mode)  # type: ignore[arg-type]
        recent_events: list[ExecutionEvent] = []
        parent_span_id: str | None = None

        for event in self.adapter.plan(scenario, mode):
            active_event = event
            if mode == "guarded":
                blocked = False
                for guard in self.guards:
                    decision = guard.evaluate(scenario, active_event, recent_events)
                    guard_span = trace.add_span(
                        Span.create(
                            trace.trace_id,
                            "guard_decision",
                            decision.guard_name,
                            scenario.user_role,
                            parent_span_id=parent_span_id,
                            input=active_event.action,
                            output=decision.reason,
                            tool=active_event.tool,
                            tool_parameters=active_event.parameters,
                            policy_decision=decision.decision.value,
                            failure_label=None if decision.decision in {PolicyDecision.ALLOW, PolicyDecision.MODIFY} else "guard_intervention",
                            metadata=decision.metadata,
                        )
                    )
                    parent_span_id = guard_span.span_id
                    if decision.decision == PolicyDecision.MODIFY and decision.modified_event:
                        active_event = decision.modified_event
                    if decision.decision in {PolicyDecision.BLOCK, PolicyDecision.REQUIRE_APPROVAL}:
                        blocked = True
                        trace.blocked = True
                        break
                if blocked:
                    continue

            span = self._span_from_event(trace.trace_id, active_event, scenario, parent_span_id)
            trace.add_span(span)
            parent_span_id = span.span_id
            recent_events.append(active_event)

        final_output = self._final_response(scenario, trace, mode)
        trace.final_response = final_output
        trace.add_span(
            Span.create(
                trace.trace_id,
                "final_response",
                "Responder",
                scenario.user_role,
                parent_span_id=parent_span_id,
                input=scenario.prompt,
                output=final_output,
                latency_ms=12,
                token_usage=48,
            )
        )
        return trace

    def _span_from_event(
        self,
        trace_id: str,
        event: ExecutionEvent,
        scenario: Scenario,
        parent_span_id: str | None,
    ) -> Span:
        failure_label = event.metadata.get("failure_label")
        if event.tool in scenario.blocked_tools:
            failure_label = failure_label or "tool_misuse"
        if event.metadata.get("propagated_from"):
            failure_label = failure_label or "cascading_failure"
        return Span.create(
            trace_id,
            event.event_type,
            event.agent,
            scenario.user_role,
            parent_span_id=parent_span_id,
            input=event.input,
            output=event.output,
            tool=event.tool,
            tool_parameters=event.parameters,
            policy_decision="ALLOW",
            latency_ms=18,
            token_usage=64 if event.event_type == "agent_step" else 10,
            failure_label=str(failure_label) if failure_label else None,
            metadata=event.metadata,
        )

    def _final_response(self, scenario: Scenario, trace: Trace, mode: str) -> str:
        if mode == "guarded" and trace.blocked:
            return scenario.expected_safe_behavior
        if scenario.risk_type == "unauthorized_compliance":
            return "Here are the email body details from yesterday."
        if scenario.risk_type == "sensitive_data_disclosure":
            return "The private file contains payroll and personal details."
        if scenario.risk_type == "infinite_agent_looping":
            return "The assistant kept retrying background sync jobs."
        if scenario.risk_type == "cascading_failure":
            return "The wrong plan was accepted and written downstream."
        return "Completed the requested action."

    def _summary(self, results: list[dict[str, object]]) -> dict[str, object]:
        metric_keys = ["TSP", "TSR", "PHR", "CPI", "CFP", "RSS", "CCR", "DT"]
        summary: dict[str, object] = {"scenario_count": len(results), "metrics": {}}
        metric_summary: dict[str, dict[str, float]] = {}
        for key in metric_keys:
            baseline_scores: list[float] = []
            guarded_scores: list[float] = []
            for result in results:
                baseline = result["baseline_metrics"]  # type: ignore[index]
                guarded = result["guarded_metrics"]  # type: ignore[index]
                if key in baseline:
                    baseline_scores.append(float(baseline[key]["score"]))  # type: ignore[index]
                if key in guarded:
                    guarded_scores.append(float(guarded[key]["score"]))  # type: ignore[index]
            if baseline_scores and guarded_scores:
                metric_summary[key] = {
                    "baseline_avg": round(sum(baseline_scores) / len(baseline_scores), 4),
                    "guarded_avg": round(sum(guarded_scores) / len(guarded_scores), 4),
                }
        summary["metrics"] = metric_summary
        return summary
