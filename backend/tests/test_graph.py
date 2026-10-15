from pathlib import Path

from fastapi.testclient import TestClient

from masguardeval import EvaluationEngine
from masguardeval.api import app


DATASET = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


def test_agent_tool_graph_marks_executed_and_blocked_edges():
    result = EvaluationEngine.from_dataset_path(DATASET).evaluate("auth_001")
    baseline = result.baseline_graph
    guarded = result.guarded_graph
    assert baseline and guarded
    assert any(edge["kind"] == "tool_call" and edge["target"] == "tool:mock_email_body_read" for edge in baseline["edges"])
    blocked = [edge for edge in guarded["edges"] if edge["kind"] == "blocked_tool_attempt"]
    assert len(blocked) == 1
    assert blocked[0]["source"] == "agent:Executor"
    assert blocked[0]["decision"] == "BLOCK"
    assert not any(edge["kind"] == "tool_call" for edge in guarded["edges"])
    assert {node["id"] for node in guarded["nodes"]} >= {"agent:Executor", "tool:mock_email_body_read"}
    assert "agent:Planner" in {node["id"] for node in guarded["nodes"]}
    assert not any(node["id"].startswith("agent:") and node["label"].endswith("Guard") for node in guarded["nodes"])


def test_graph_contains_message_and_causal_failure_path():
    graph = EvaluationEngine.from_dataset_path(DATASET).evaluate("cascade_001").baseline_graph
    assert graph
    assert any(edge["kind"] == "inter_agent_message" and edge["source"] == "agent:Planner" and edge["target"] == "agent:Executor" for edge in graph["edges"])
    assert graph["span_propagation"]["longest_path_length"] >= 3
    assert any(edge["is_propagated_failure"] for edge in graph["edges"])
    assert any(node["id"] == "agent:Planner" and node["is_root_failure"] for node in graph["nodes"])


def test_graph_api_validates_mode():
    client = TestClient(app)
    assert client.get("/graph/auth_001?mode=guarded").status_code == 200
    assert client.get("/graph/auth_001?mode=unknown").status_code == 422
