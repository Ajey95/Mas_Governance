import json

import pytest

from masguardeval import GoldenDataset, ModelOutput, TraceStore, run_model_react_langgraph


pytest.importorskip("langgraph")


def scenario():
    from pathlib import Path
    return GoldenDataset.load(Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json").get("auth_001")


class Client:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.prompts = []

    def complete(self, role, prompt):
        self.prompts.append(prompt)
        return ModelOutput(json.dumps(next(self.actions)), token_usage=11)


def test_model_reasons_again_after_guarded_observation(tmp_path):
    client = Client([
        {"kind": "tool", "tool": "mock_email_search", "parameters": {"date": "yesterday", "subject_only": True}, "decision": "inspect metadata"},
        {"kind": "finish", "answer": "I inspected the metadata.", "decision": "done"},
    ])
    store = TraceStore(tmp_path / "react.sqlite3")
    run = run_model_react_langgraph(scenario(), client, model_name="fake", trace_store=store)
    assert not run.trace.blocked
    assert run.trace.final_response == "I inspected the metadata."
    assert len(client.prompts) == 2
    assert "Prior tool observations: []" in client.prompts[0]
    assert "Prior tool observations: []" not in client.prompts[1]
    assert sum(span.span_type == "tool_call" for span in run.trace.spans) == 1
    assert any("react_cycle" in span.metadata.get("namespace", "") for span in run.trace.spans)
    assert store.get(run.trace.trace_id) is not None


def test_model_blocked_tool_stops_graph_before_followup():
    client = Client([{"kind": "tool", "tool": "mock_email_body_read", "parameters": {"date": "yesterday"}, "decision": "read body"}])
    run = run_model_react_langgraph(scenario(), client, model_name="fake")
    assert run.trace.blocked
    assert len(client.prompts) == 1
    assert any(span.policy_decision == "BLOCK" for span in run.trace.spans)


def test_model_step_budget_is_hard_cap():
    client = Client([{"kind": "tool", "tool": "mock_email_search", "parameters": {"date": "yesterday", "subject_only": True}}] * 4)
    run = run_model_react_langgraph(scenario(), client, model_name="fake", max_steps=2)
    assert len(client.prompts) == 2
    assert sum(span.span_type == "tool_call" for span in run.trace.spans) == 2
    assert run.trace.final_response == "ReAct step budget exhausted."
