import json
from pathlib import Path

from fastapi.testclient import TestClient

from masguardeval import EvaluationEngine, GoldenDataset, TraceStore
from masguardeval.api import app, engine
import masguardeval.api as api_module


DATASET = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


def test_trace_store_persists_complete_runs_and_spans(tmp_path):
    path = tmp_path / "runs.sqlite3"
    evaluator = EvaluationEngine(GoldenDataset.load(DATASET), trace_store=TraceStore(path))
    trace = evaluator.run_guarded(evaluator.dataset.get("auth_001"))
    reopened = TraceStore(path)
    saved = reopened.get(trace.trace_id)
    assert saved
    assert saved["completed_at"] == trace.completed_at
    assert saved["blocked"] is True
    assert saved["scenario"]["scenario_id"] == "auth_001"
    assert len(saved["spans"]) == len(trace.spans)
    assert reopened.list(1)[0]["trace_id"] == trace.trace_id
    assert reopened.get("unknown") is None


def test_stream_emits_ordered_spans_and_persisted_complete_event():
    client = TestClient(app)
    with client.stream("GET", "/stream/auth_001?mode=guarded") as response:
        assert response.status_code == 200
        lines = [line for line in response.iter_lines() if line.startswith("event: ") or line.startswith("data: ")]
    events = []
    for index in range(0, len(lines), 2):
        events.append((lines[index][7:], json.loads(lines[index + 1][6:])))
    assert events[-1][0] == "complete"
    trace = events[-1][1]["trace"]
    assert len([item for item in events if item[0] == "span"]) == len(trace["spans"])
    assert trace["blocked"]
    assert engine.trace_store.get(trace["trace_id"]) is not None
    assert client.get(f"/runs/{trace['trace_id']}").status_code == 200
    saved_graph = client.get(f"/runs/{trace['trace_id']}/graph")
    assert saved_graph.status_code == 200
    assert saved_graph.json()["trace_id"] == trace["trace_id"]
    assert saved_graph.json()["edges"]
    assert client.get("/runs?limit=0").status_code == 422


def test_saved_candidate_graph_uses_stored_scenario_snapshot(tmp_path, monkeypatch):
    candidate = GoldenDataset.load(DATASET.parent / "candidate_scenarios.json")
    store = TraceStore(tmp_path / "candidate.sqlite3")
    trace = EvaluationEngine(candidate, trace_store=store).run_baseline(candidate.get("auth_c02"))
    monkeypatch.setattr(api_module, "trace_store", store)
    response = TestClient(app).get(f"/runs/{trace.trace_id}/graph")
    assert response.status_code == 200
    assert response.json()["scenario_id"] == "auth_c02"


def test_dashboard_preview_does_not_flood_saved_run_history():
    client = TestClient(app)
    before = len(engine.trace_store.list(200))
    assert client.get("/dashboard").status_code == 200
    assert len(engine.trace_store.list(200)) == before
