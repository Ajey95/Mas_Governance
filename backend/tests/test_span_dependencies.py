"""Causal candidates must have declared, inspectable span dependencies."""

from pathlib import Path

from masguardeval import EvaluationEngine, GoldenDataset, MetricEngine
from masguardeval.frameworks import FrameworkSession, ToolSpec
from masguardeval.graph import AgentToolGraphBuilder
from masguardeval.models import ExecutionEvent, Span, Trace
from masguardeval.propagation import PropagationAnalyzer


DATASET = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


def test_nesting_alone_does_not_count_as_failure_propagation():
    scenario = GoldenDataset.load(DATASET).get("cascade_001")
    trace = Trace.start(scenario.scenario_id, "baseline")
    root = trace.add_span(Span.create(trace.trace_id, "agent_step", "Planner", scenario.user_role,
                                      failure_label="source_failure"))
    child = trace.add_span(Span.create(trace.trace_id, "agent_step", "Executor", scenario.user_role,
                                       parent_span_id=root.span_id, failure_label="cascading_failure",
                                       metadata={"propagated_from": "Planner"}))

    analysis = PropagationAnalyzer().analyze(trace)
    assert (root.span_id, child.span_id) in analysis.edges
    assert analysis.dependency_edges == []
    assert analysis.failure_paths == []
    assert analysis.unlinked_propagation_span_ids == [child.span_id]
    assert MetricEngine().cascading_failure_probability(scenario, trace).score == 0


def test_declared_dependency_connects_failure_through_nonfailure_span():
    scenario = GoldenDataset.load(DATASET).get("cascade_001")
    trace = Trace.start(scenario.scenario_id, "baseline")
    root = trace.add_span(Span.create(trace.trace_id, "agent_step", "Planner", scenario.user_role,
                                      failure_label="source_failure"))
    message = trace.add_span(Span.create(trace.trace_id, "inter_agent_message", "Planner", scenario.user_role,
                                         parent_span_id=root.span_id,
                                         metadata={"causal_parent_span_id": root.span_id}))
    failed = trace.add_span(Span.create(trace.trace_id, "tool_call", "Executor", scenario.user_role,
                                        parent_span_id=message.span_id, failure_label="cascading_failure",
                                        metadata={"propagated_from": "Planner", "causal_parent_span_id": message.span_id}))

    analysis = PropagationAnalyzer().analyze(trace)
    assert analysis.dependency_edges == [(root.span_id, message.span_id), (message.span_id, failed.span_id)]
    assert analysis.failure_paths == [[root.span_id, message.span_id, failed.span_id]]
    assert MetricEngine().cascading_failure_probability(scenario, trace).score == 1
    graph = AgentToolGraphBuilder().build(scenario, trace)
    assert graph["span_propagation"]["failure_paths"] == analysis.failure_paths


def test_linked_failures_need_no_adapter_propagation_label():
    scenario = GoldenDataset.load(DATASET).get("cascade_001")
    trace = Trace.start(scenario.scenario_id, "baseline")
    root = trace.add_span(Span.create(trace.trace_id, "agent_step", "Planner", scenario.user_role,
                                      failure_label="source_failure"))
    downstream = trace.add_span(Span.create(trace.trace_id, "agent_step", "Reviewer", scenario.user_role,
                                            failure_label="wrong_decision",
                                            metadata={"causal_parent_span_id": root.span_id}))

    analysis = PropagationAnalyzer().analyze(trace)
    assert analysis.root_span_ids == [root.span_id]
    assert analysis.propagated_span_ids == [downstream.span_id]
    assert analysis.failure_paths == [[root.span_id, downstream.span_id]]
    assert MetricEngine().cascading_failure_probability(scenario, trace).score == 1


def test_runner_persists_resolved_dependency_and_marks_missing_source():
    dataset = GoldenDataset.load(DATASET)
    scenario = dataset.get("cascade_001")

    class DependencyAdapter:
        name = "dependency_test"

        def plan(self, scenario, mode):
            return [
                ExecutionEvent("Planner", "agent_step", "unique_plan", scenario.user_role,
                               metadata={"failure_label": "source_failure"}),
                ExecutionEvent("Planner", "inter_agent_message", "send_plan", scenario.user_role,
                               metadata={"caused_by": "unique_plan", "recipient": "Executor"}),
                ExecutionEvent("Executor", "agent_step", "lost_link", scenario.user_role,
                               metadata={"caused_by": "missing_action", "failure_label": "cascading_failure",
                                         "propagated_from": "Planner"}),
            ]

    trace = EvaluationEngine(dataset, adapter=DependencyAdapter()).run_baseline(scenario)
    plan, message, unlinked = [s for s in trace.spans if s.agent != "Responder"]
    assert message.metadata["causal_parent_span_id"] == plan.span_id
    assert unlinked.parent_span_id is None
    assert unlinked.metadata["causal_reference_status"] == "missing"
    assert MetricEngine().cascading_failure_probability(scenario, trace).score == 0


def test_runner_does_not_guess_which_repeated_action_caused_failure():
    dataset = GoldenDataset.load(DATASET)
    scenario = dataset.get("cascade_001")

    class RepeatedActionAdapter:
        name = "repeated_action_test"

        def plan(self, scenario, mode):
            return [
                ExecutionEvent("Planner", "agent_step", "same_action", scenario.user_role,
                               metadata={"failure_label": "source_failure"}),
                ExecutionEvent("Planner", "agent_step", "same_action", scenario.user_role),
                ExecutionEvent("Executor", "agent_step", "follow_up", scenario.user_role,
                               metadata={"caused_by": "same_action", "failure_label": "cascading_failure"}),
            ]

    trace = EvaluationEngine(dataset, adapter=RepeatedActionAdapter()).run_baseline(scenario)
    failure = next(span for span in trace.spans if span.failure_label == "cascading_failure")
    assert failure.metadata["causal_reference_status"] == "ambiguous"
    assert failure.parent_span_id is None
    assert PropagationAnalyzer().analyze(trace).failure_paths == []


def test_sdk_session_can_link_agent_message_tool_and_review_events():
    scenario = GoldenDataset.load(DATASET).get("cascade_001")
    session = FrameworkSession(scenario, mode="baseline")
    session.register_tool(ToolSpec("mock_file_write", "Fictional file write"))
    plan = session.agent_step("Planner", "plan", metadata={"failure_label": "source_failure"})
    message = session.message("Planner", "Executor", "use this plan", caused_by=plan)
    session.call("mock_file_write", {"path": "/workspace/config.yml", "content": "unsafe: true"},
                 agent="Executor", caused_by=message, action_id="recorded-write")
    session.agent_step("Reviewer", "review", caused_by="recorded-write",
                       metadata={"failure_label": "accepted_bad_change"})

    trace = session.finish("Recorded")
    analysis = PropagationAnalyzer().analyze(trace)
    assert analysis.failure_paths
    root = next(span for span in trace.spans if span.agent == "Planner" and span.failure_label)
    reviewer = next(span for span in trace.spans if span.agent == "Reviewer" and span.failure_label)
    assert all(path[0] == root.span_id for path in analysis.failure_paths)
    assert any(path[-1] == reviewer.span_id for path in analysis.failure_paths)
    assert MetricEngine().cascading_failure_probability(scenario, trace).score == 1
