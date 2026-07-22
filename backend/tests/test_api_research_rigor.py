from fastapi.testclient import TestClient

from masguardeval.api import app


client = TestClient(app)


def test_experiment_endpoint_returns_tables_and_ablations():
    response = client.get("/experiments")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario_count"] >= 7
    assert "metric_table" in payload
    assert "ablation_table" in payload
    assert "full_guard_stack" in payload["ablation_table"]


def test_propagation_endpoint_returns_rooted_failure_graph():
    response = client.get("/propagation/cascade_001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["root_span_ids"]
    assert payload["propagated_span_ids"]
    assert payload["longest_path_length"] >= 3


def test_batch_endpoint_returns_scalability_manifest():
    response = client.get("/scalability/batch?max_workers=2&chunk_size=3")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario_count"] >= 7
    assert payload["worker_count"] == 2
    assert [len(shard["scenario_ids"]) for shard in payload["shards"]] == [3, 3, 1]


def test_evaluator_agreement_endpoint_computes_kappa():
    response = client.post(
        "/evaluator/agreement",
        json={"labels_a": ["pass", "fail", "pass"], "labels_b": ["pass", "pass", "pass"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["label_count"] == 3
    assert payload["kappa"] < 1
