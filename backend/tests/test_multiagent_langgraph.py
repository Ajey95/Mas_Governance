import json

import pytest

from masguardeval import GoldenDataset, ModelOutput, TraceStore, run_model_multiagent_langgraph


pytest.importorskip("langgraph")


def scenario():
    from pathlib import Path
    return GoldenDataset.load(Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json").get("auth_001")


class Client:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.roles = []
        self.prompts = []

    def complete(self, role, prompt):
        self.roles.append(role)
        self.prompts.append(prompt)
        return ModelOutput(json.dumps(next(self.replies)), token_usage=7)


def test_multiagent_graph_revises_once_across_nested_subgraphs(tmp_path):
    client = Client([
        {"plan": "Inspect metadata, then summarize.", "decision": "plan"},
        {"kind": "tool", "tool": "mock_email_search", "parameters": {"date": "yesterday", "subject_only": True}, "decision": "inspect"},
        {"decision": "revise", "feedback": "Explain the safe boundary.", "answer": "Draft."},
        {"kind": "finish", "answer": "Only metadata was inspected.", "decision": "done"},
        {"decision": "approve", "feedback": "", "answer": "Only metadata was inspected."},
    ])
    store = TraceStore(tmp_path / "team.sqlite3")
    run = run_model_multiagent_langgraph(scenario(), client, model_name="fake",
                                         max_rounds=2, max_tool_calls_per_round=1,
                                         trace_store=store)
    assert not run.trace.blocked and run.state["round"] == 2
    assert client.roles == ["Planner", "Executor", "Reviewer", "Executor", "Reviewer"]
    assert "Explain the safe boundary." in client.prompts[3]
    assert run.trace.final_response == "Only metadata was inspected."
    assert sum(span.span_type == "tool_call" for span in run.trace.spans) == 1
    namespaces = {span.metadata.get("namespace", "") for span in run.trace.spans}
    assert any("planner_graph" in item for item in namespaces)
    assert any("executor_graph" in item for item in namespaces)
    assert any("reviewer_graph" in item for item in namespaces)
    assert store.get(run.trace.trace_id) is not None


def test_multiagent_guard_block_stops_before_reviewer():
    client = Client([
        {"plan": "Inspect email.", "decision": "plan"},
        {"kind": "tool", "tool": "mock_email_body_read", "parameters": {"date": "yesterday"}, "decision": "inspect"},
    ])
    run = run_model_multiagent_langgraph(scenario(), client, model_name="fake")
    assert run.trace.blocked
    assert client.roles == ["Planner", "Executor"]
    assert any(span.policy_decision == "BLOCK" for span in run.trace.spans)


def test_multiagent_review_loop_stops_at_round_cap():
    client = Client([
        {"plan": "Review.", "decision": "plan"},
        {"kind": "finish", "answer": "First.", "decision": "done"},
        {"decision": "revise", "feedback": "Try again.", "answer": "First draft."},
        {"kind": "finish", "answer": "Second.", "decision": "done"},
        {"decision": "revise", "feedback": "Still revise.", "answer": "Second draft."},
    ])
    run = run_model_multiagent_langgraph(scenario(), client, model_name="fake", max_rounds=2)
    assert client.roles.count("Reviewer") == 2
    assert run.state["round"] == 2
    assert run.trace.final_response == "Model reviewer did not approve within the round budget; no final answer released."
