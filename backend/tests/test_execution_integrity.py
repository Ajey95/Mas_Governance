from pathlib import Path

from masguardeval import EvaluationEngine, ExperimentSuite, GoldenDataset, MetricEngine, PropagationAnalyzer
from masguardeval.models import ExecutionEvent, Span, Trace


DATASET_PATH = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


def test_blocked_sensitive_read_stops_disclosure_and_records_nonapplicable_metrics():
    result = EvaluationEngine.from_dataset_path(DATASET_PATH).evaluate("data_001")
    assert "Ada" in result.baseline_trace.final_response
    assert "Ada" not in result.guarded_trace.final_response
    assert result.guarded_trace.final_response.startswith("Execution stopped:")
    assert not any(span.span_type == "tool_call" for span in result.guarded_trace.spans)
    assert result.guarded_metrics["RSS"].score == 1
    assert result.guarded_metrics["TSP"].applicable is False
    assert result.guarded_metrics["TSR"].applicable is False
    assert "TSP" not in result.risk_reduction()


def test_cascade_block_stops_downstream_write_and_reviewer():
    result = EvaluationEngine.from_dataset_path(DATASET_PATH).evaluate("cascade_001")
    assert any(span.tool == "mock_file_write" for span in result.baseline_trace.spans)
    assert any(span.agent == "Reviewer" for span in result.baseline_trace.spans)
    assert not any(span.tool == "mock_file_write" for span in result.guarded_trace.spans)
    assert not any(span.agent == "Reviewer" for span in result.guarded_trace.spans)
    assert result.baseline_metrics["CFP"].score == 1
    assert result.guarded_metrics["CFP"].score == 0
    graph = PropagationAnalyzer().analyze(result.baseline_trace)
    assert all(source == next(span for span in result.baseline_trace.spans if span.span_id == target).parent_span_id for source, target in graph.edges)


def test_mock_shell_never_executes_on_host(tmp_path):
    marker = tmp_path / "must_remain.txt"
    marker.write_text("safe", encoding="utf-8")
    class ShellIntentAdapter:
        name = "shell_intent_test"

        def plan(self, scenario, mode):
            return [ExecutionEvent(
                agent="Executor", event_type="tool_call", action="mock_shell",
                user_role=scenario.user_role, tool="mock_shell_execution",
                parameters={"command": f"Remove-Item -LiteralPath '{marker}'"},
            )]

    engine = EvaluationEngine(GoldenDataset.load(DATASET_PATH), adapter=ShellIntentAdapter())
    scenario = engine.dataset.get("tool_001")
    baseline = engine.run_baseline(scenario)
    assert marker.read_text(encoding="utf-8") == "safe"
    assert any("no host command was run" in (span.output or "") for span in baseline.spans)
    assert all(span.token_usage is None for span in baseline.spans)


def test_parameter_hallucination_counts_each_call_once():
    engine = EvaluationEngine.from_dataset_path(DATASET_PATH)
    scenario = engine.dataset.get("tool_001")
    trace = Trace.start(scenario.scenario_id, "baseline")
    trace.add_span(Span.create(trace.trace_id, "tool_call", "Executor", "developer",
                               tool="mock_shell_execution", tool_parameters={"bad_key": 1},
                               metadata={"parameter_hallucination": True}))
    metric = MetricEngine().parameter_hallucination_rate(scenario, trace)
    assert metric.score == 1
    assert len(metric.details["invalid_span_ids"]) == 1


def test_ablation_keeps_registered_tool_handlers():
    engine = EvaluationEngine.from_dataset_path(DATASET_PATH)
    seen = []
    engine.register_tool("mock_background_job_creation", lambda parameters, workspace: seen.append(parameters["job_type"]) or "custom result")
    report = ExperimentSuite(engine).run()
    assert report.ablation_table["full_guard_stack"]["scenario_count"] == 7
    assert len(seen) >= 6
    assert any(span.output == "custom result" for span in report.results[3].baseline_trace.spans)


def test_generator_adapter_receives_tool_feedback_before_next_intent():
    class ReactiveAdapter:
        name = "reactive_test_adapter"

        def plan(self, scenario, mode):
            result = yield ExecutionEvent(
                agent="Retriever", event_type="tool_call", action="read_private_file",
                user_role=scenario.user_role, tool="mock_file_read",
                parameters={"path": "/private/payroll.csv"},
                metadata={"contains_sensitive_context": True},
            )
            yield ExecutionEvent(
                agent="Responder", event_type="agent_step", action="use_tool_result",
                user_role=scenario.user_role, output=f"Observed: {result}",
            )

    engine = EvaluationEngine(GoldenDataset.load(DATASET_PATH), adapter=ReactiveAdapter())
    scenario = engine.dataset.get("data_001")
    baseline = engine.run_baseline(scenario)
    guarded = engine.run_guarded(scenario)
    assert any("Ada" in (span.output or "") for span in baseline.spans if span.agent == "Responder")
    assert guarded.blocked
    assert not any(span.agent == "Responder" and span.span_type == "agent_step" for span in guarded.spans)
