from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from masguardeval import EvaluationEngine, GoldenDataset
from masguardeval.live import LiveWorkspaceAdapter
from masguardeval.models import ExecutionEvent
from masguardeval.guards import ParameterValidator, default_guards
from masguardeval.study_repair import repair_submitted_draft
from masguardeval.workspace import MockWorkspace


ROOT = Path(__file__).resolve().parents[2]


def test_repair_converts_runtime_schemas_without_inventing_abac_policy():
    source = json.loads((ROOT / "datasets" / "golden_scenarios.json").read_text(encoding="utf-8"))
    row = source["scenarios"][0]
    row["parameter_schema"] = {"mock_email_search": {"date": {"type": "string"}}}
    row["attribute_policies"] = {"requester_team": {"ops": "may search"}}
    row["provenance"] = "independent_human_authored"
    fixed, manifest = repair_submitted_draft({"scenarios": [row]}, {})
    repaired = fixed["scenarios"][0]
    assert repaired["parameter_schema"]["mock_email_search"] == {
        "allowed_keys": ["date"], "required_keys": [],
        "properties": {"date": {"type": "string"}},
    }
    assert repaired["attribute_policies"] == {}
    assert repaired["provenance"] == "independent_human_authored"
    assert manifest["policy_notes_pending_human_review"][row["scenario_id"]] == row["attribute_policies"]


def test_workspace_fixture_is_isolated_and_observable_in_engine():
    original = GoldenDataset.load(ROOT / "datasets" / "golden_scenarios.json").scenarios[0]
    scenario = replace(original, workspace_fixture={
        "files": {"/workspace/plan.txt": "Target version 3.3"},
        "emails": [{"id": "release-1", "date": "today", "sender": "manager@example.test",
                    "subject": "Release", "body": "Freeze the release"}],
        "memory": {"maintenance_window": "22:00"},
    })
    first = MockWorkspace.from_fixture(scenario.workspace_fixture)
    second = MockWorkspace.from_fixture(scenario.workspace_fixture)
    assert first.execute("mock_file_read", {"path": "plan.txt"}) == "Target version 3.3"
    assert first.execute("mock_file_read", {"path": "/private/payroll.csv"}) == "File not found."
    assert "release-1" in first.execute("mock_email_search", {"date": "today"})
    assert first.execute("mock_email_body_read", {"message_id": "release-1"}) == "Freeze the release"
    first.execute("mock_file_write", {"path": "plan.txt", "content": "changed"})
    assert second.execute("mock_file_read", {"path": "plan.txt"}) == "Target version 3.3"

    class ReadAdapter:
        name = "fixture_read_adapter"

        def plan(self, scenario, mode):
            return [ExecutionEvent(agent="Executor", event_type="tool_call", action="read_plan",
                                   user_role=scenario.user_role, tool="mock_file_read",
                                   parameters={"path": "plan.txt"})]

    engine = EvaluationEngine(GoldenDataset([scenario]), adapter=ReadAdapter(), guards=[])
    assert "Target version 3.3" in [span.output for span in engine.run_baseline(scenario).spans]
    assert "Target version 3.3" in [span.output for span in engine.run_guarded(scenario).spans]


def test_fixture_validation_rejects_incomplete_email_and_resource_path_matches_call():
    original = GoldenDataset.load(ROOT / "datasets" / "golden_scenarios.json").scenarios[0]
    with pytest.raises(ValueError, match="fixture email"):
        GoldenDataset([replace(original, workspace_fixture={"emails": [{"id": "incomplete"}]})]).validate()
    scenario = replace(original, resource_attributes={"/workspace/plan.txt": {"classification": "private"}})
    metadata = LiveWorkspaceAdapter._tool_metadata(scenario, "mock_file_read", {"path": "plan.txt"})
    assert metadata["resource_attributes"] == {"classification": "private"}


def test_blocked_tool_can_also_be_documented_as_high_risk():
    original = GoldenDataset.load(ROOT / "datasets" / "golden_scenarios.json").scenarios[0]
    blocked = original.blocked_tools[0]
    GoldenDataset([replace(original, high_risk_tools=[blocked])]).validate()


def test_parameter_guard_checks_submitted_property_types():
    original = GoldenDataset.load(ROOT / "datasets" / "golden_scenarios.json").scenarios[0]
    scenario = replace(original, parameter_schema={"mock_email_search": {
        "allowed_keys": ["subject_only"], "required_keys": [],
        "properties": {"subject_only": {"type": "boolean"}},
    }})
    event = ExecutionEvent(agent="Executor", event_type="tool_call", action="search",
                           user_role=scenario.user_role, tool="mock_email_search",
                           parameters={"subject_only": "yes"})
    decision = ParameterValidator().evaluate(scenario, event, [])
    assert decision.decision.value == "BLOCK"
    assert decision.metadata["invalid_types"] == {"subject_only": "boolean"}


def test_parameter_guard_enforces_value_and_call_budget_constraints():
    original = GoldenDataset.load(ROOT / "datasets" / "golden_scenarios.json").scenarios[0]
    scenario = replace(original, parameter_schema={"mock_shell_execution": {
        "allowed_keys": ["command"], "required_keys": ["command"], "max_calls": 1,
        "properties": {"command": {"type": "string", "enum": ["inspect_workspace_state"]}},
    }})
    safe = ExecutionEvent(agent="Executor", event_type="tool_call", action="inspect",
                          user_role=scenario.user_role, tool="mock_shell_execution",
                          parameters={"command": "inspect_workspace_state"})
    unsafe = replace(safe, parameters={"command": "rm -rf /workspace"})
    assert ParameterValidator().evaluate(scenario, safe, []).decision.value == "ALLOW"
    rejected = ParameterValidator().evaluate(scenario, unsafe, [])
    assert rejected.decision.value == "BLOCK"
    assert rejected.metadata["invalid_values"] == {"command": "enum"}
    repeated = ParameterValidator().evaluate(scenario, safe, [safe])
    assert repeated.decision.value == "BLOCK"
    assert repeated.metadata["call_limit_reached"] is True


def test_parameter_guard_enforces_required_boolean_and_memory_size():
    original = GoldenDataset.load(ROOT / "datasets" / "golden_scenarios.json").scenarios[0]
    scenario = replace(original, parameter_schema={
        "mock_email_search": {
            "allowed_keys": ["subject_only"], "required_keys": ["subject_only"],
            "properties": {"subject_only": {"type": "boolean", "const": True}},
        },
        "mock_memory_write": {
            "allowed_keys": ["key", "value"], "required_keys": ["key", "value"],
            "properties": {"key": {"type": "string", "enum": ["report_summary"]},
                           "value": {"type": "string", "max_length": 8}},
        },
    })
    event = ExecutionEvent(agent="Executor", event_type="tool_call", action="search",
                           user_role=scenario.user_role, tool="mock_email_search",
                           parameters={"subject_only": False})
    assert ParameterValidator().evaluate(scenario, event, []).metadata["invalid_values"] == {
        "subject_only": "const"}
    write = replace(event, action="store", tool="mock_memory_write",
                    parameters={"key": "report_summary", "value": "entire record"})
    assert ParameterValidator().evaluate(scenario, write, []).metadata["invalid_values"] == {
        "value": "max_length"}


def test_shell_fixture_responses_are_command_specific():
    workspace = MockWorkspace.from_fixture({"shell_responses": {"inspect_workspace_state": "state: healthy"}})
    assert workspace.execute("mock_shell_execution", {"command": "inspect_workspace_state"}) == "state: healthy"
    assert "Unsupported simulated command" in workspace.execute(
        "mock_shell_execution", {"command": "env"})


def test_guarded_run_stops_second_allowed_simulated_command():
    original = GoldenDataset.load(ROOT / "datasets" / "golden_scenarios.json").scenarios[0]
    scenario = replace(original, allowed_tools=["mock_shell_execution"], blocked_tools=[],
                       high_risk_tools=[], sensitive_tools=[], attribute_policies={},
                       parameter_schema={"mock_shell_execution": {
                           "allowed_keys": ["command"], "required_keys": ["command"], "max_calls": 1,
                           "properties": {"command": {"type": "string", "enum": ["mock_test --suite smoke"]}},
                       }}, workspace_fixture={"shell_responses": {
                           "mock_test --suite smoke": "Simulated test failed"
                       }})

    class RetryAdapter:
        name = "retry_adapter"

        def plan(self, case, mode):
            return [ExecutionEvent(agent="Executor", event_type="tool_call", action="run_test",
                                   user_role=case.user_role, tool="mock_shell_execution",
                                   parameters={"command": "mock_test --suite smoke"}) for _ in range(2)]

    guarded = EvaluationEngine(GoldenDataset([scenario]), adapter=RetryAdapter(),
                               guards=default_guards()).run_guarded(scenario)
    executed = [span for span in guarded.spans if span.span_type == "tool_call"]
    assert len(executed) == 1
    assert guarded.blocked is True
    assert any(span.agent == "ParameterValidator" and span.policy_decision == "BLOCK"
               for span in guarded.spans if span.span_type == "guard_decision")
