from dataclasses import replace
from pathlib import Path
from threading import Thread
from time import sleep

from fastapi.testclient import TestClient

from masguardeval import ApprovalBroker, ApprovalOutcome, EvaluationEngine, GoldenDataset
from masguardeval.api import app
from masguardeval.models import ExecutionEvent, Trace


DATASET = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


class OneToolAdapter:
    name = "policy_test"

    def __init__(self, resource_tenant: str = "team-a") -> None:
        self.resource_tenant = resource_tenant

    def plan(self, scenario, mode):
        return [ExecutionEvent(
            agent="Worker", event_type="tool_call", action="create_job", user_role=scenario.user_role,
            tool="mock_background_job_creation", parameters={"job_type": "review"},
            metadata={"resource_attributes": {"tenant": self.resource_tenant}},
        )]


def test_abac_blocks_cross_tenant_tool_before_execution():
    dataset = GoldenDataset.load(DATASET)
    scenario = replace(dataset.get("loop_001"),
                       subject_attributes={"tenant": "team-a"},
                       attribute_policies={"mock_background_job_creation": {"match": ["tenant"]}})
    engine = EvaluationEngine(dataset, adapter=OneToolAdapter("team-b"))
    trace = engine.run_guarded(scenario)
    assert trace.blocked
    assert not any(span.span_type == "tool_call" for span in trace.spans)
    assert any(span.agent == "ABACGuard" and span.policy_decision == "BLOCK" for span in trace.spans)


def test_approval_resumes_same_run_without_replaying_prior_events():
    dataset = GoldenDataset.load(DATASET)
    scenario = replace(dataset.get("loop_001"), high_risk_tools=["mock_background_job_creation"])
    engine = EvaluationEngine(dataset, adapter=OneToolAdapter())
    trace = engine.run_guarded(scenario, approval_handler=lambda current, event: True)
    assert not trace.blocked
    assert sum(span.span_type == "tool_call" for span in trace.spans) == 1
    assert any(span.policy_decision == "REQUIRE_APPROVAL" for span in trace.spans)
    assert any(span.agent == "HumanApprovalDecision" and span.policy_decision == "ALLOW" for span in trace.spans)
    denied = engine.run_guarded(scenario, approval_handler=lambda current, event: False)
    assert denied.blocked
    assert not any(span.span_type == "tool_call" for span in denied.spans)
    audited = engine.run_guarded(scenario, approval_handler=lambda current, event: ApprovalOutcome(False, "request-1", "denied", "Unsafe for this tenant"))
    decision = next(span for span in audited.spans if span.agent == "HumanApprovalDecision")
    assert decision.output == "Unsafe for this tenant"
    assert decision.metadata["request_id"] == "request-1"
    assert "Unsafe for this tenant" in audited.stop_reason


def test_approval_broker_and_authenticated_api(monkeypatch):
    broker = ApprovalBroker(timeout_seconds=2)
    trace = Trace.start("loop_001", "guarded")
    event = OneToolAdapter().plan(GoldenDataset.load(DATASET).get("loop_001"), "guarded")[0]
    outcome = []
    thread = Thread(target=lambda: outcome.append(broker.request(trace, event)))
    thread.start()
    for _ in range(100):
        if broker.list("pending"):
            break
        sleep(0.01)
    requests = broker.list("pending")
    assert len(requests) == 1
    broker.decide(requests[0]["request_id"], True, "Approved for test")
    thread.join(timeout=2)
    assert outcome[0].approved
    assert outcome[0].request_id == requests[0]["request_id"]
    assert outcome[0].reason == "Approved for test"

    client = TestClient(app)
    monkeypatch.delenv("MASGUARDEVAL_APPROVAL_TOKEN", raising=False)
    assert client.get("/approvals").status_code == 503
    monkeypatch.setenv("MASGUARDEVAL_APPROVAL_TOKEN", "test-only-secret")
    assert client.get("/approvals").status_code == 401
    assert client.get("/approvals", headers={"Authorization": "Bearer test-only-secret"}).status_code == 200
