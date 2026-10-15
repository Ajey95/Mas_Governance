import json
import sys
from pathlib import Path
from types import SimpleNamespace

from masguardeval import EvaluationEngine, GoldenDataset, LiveWorkspaceAdapter, SingleAgentWorkspaceAdapter
from masguardeval.live import ModelOutput, OllamaChatClient, OpenAIResponsesClient


DATASET = Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json"


class FakeModel:
    def __init__(self) -> None:
        self.calls = []
        self.single_calls = 0

    def complete(self, role, prompt):
        self.calls.append(role)
        if role == "Planner":
            value = {"plan": "Read the requested file", "decision": "plan"}
        elif role == "Executor":
            value = {"kind": "tool", "tool": "mock_file_read", "parameters": {"path": "/private/payroll.csv"}, "answer": "", "decision": "allow_sensitive_action"}
        elif role == "Reviewer":
            value = {"decision": "finish", "answer": "The file lists Ada.", "rationale": "Tool returned the file."}
        else:
            self.single_calls += 1
            value = ({"kind": "tool", "tool": "mock_file_read", "parameters": {"path": "/private/payroll.csv"}, "answer": "", "decision": "read"}
                     if self.single_calls % 2 else {"kind": "finish", "tool": None, "parameters": {}, "answer": "The file lists Ada.", "decision": "finish"})
        return ModelOutput(json.dumps(value), token_usage=17, latency_ms=12.5)


def test_multi_agent_uses_real_feedback_and_guards_sensitive_tool():
    dataset = GoldenDataset.load(DATASET)
    fake = FakeModel()
    engine = EvaluationEngine(dataset, adapter=LiveWorkspaceAdapter(fake, "fake-model"))
    result = engine.evaluate("data_001")
    assert result.baseline_trace.final_response == "The file lists Ada."
    assert result.guarded_trace.blocked
    assert result.guarded_trace.final_response.startswith("Execution stopped:")
    assert result.guarded_trace.final_response != result.scenario.expected_safe_behavior
    assert any(span.agent == "Planner" and span.token_usage == 17 and span.latency_ms == 12.5 for span in result.baseline_trace.spans)
    assert result.guarded_graph["edges"][-1]["kind"] == "blocked_tool_attempt"
    assert any(edge["kind"] == "inter_agent_message" for edge in result.baseline_graph["edges"])
    assert engine.generate_dashboard()["execution_kind"] == "live_model_agent"


def test_single_agent_feedback_loop():
    dataset = GoldenDataset.load(DATASET)
    fake = FakeModel()
    engine = EvaluationEngine(dataset, adapter=SingleAgentWorkspaceAdapter(fake, "fake-model"))
    trace = engine.run_baseline(dataset.get("data_001"))
    assert trace.final_response == "The file lists Ada."
    assert sum(span.span_type == "tool_call" for span in trace.spans) == 1
    assert fake.calls == ["SingleAgent", "SingleAgent"]


def test_openai_client_uses_responses_without_server_side_storage(monkeypatch):
    calls = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(create=self.create)

        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(status="completed", output_text='{"ok":true}', usage=SimpleNamespace(total_tokens=9))

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    output = OpenAIResponsesClient("pinned-model", api_key="test-only").complete("Planner", "test prompt")
    assert json.loads(output.text) == {"ok": True}
    assert output.token_usage == 9
    assert calls[0]["store"] is False
    assert calls[0]["model"] == "pinned-model"


def test_ollama_client_uses_json_mode_and_records_model_digest(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        if request.full_url.endswith("/api/tags"):
            return FakeResponse({"models": [{"name": "model:test", "digest": "sha256:abc", "details": {"family": "test"}}]})
        return FakeResponse({"done": True, "done_reason": "stop", "model": "model:test", "message": {"content": '{"kind":"finish"}'}, "prompt_eval_count": 12, "eval_count": 8})

    monkeypatch.setattr("masguardeval.live.urlopen", fake_urlopen)
    client = OllamaChatClient("model:test", temperature=0, seed=31)
    assert client.model_metadata()["digest"] == "sha256:abc"
    output = client.complete("Executor", "next action")
    assert output.token_usage == 20 and output.resolved_model == "model:test"
    body = json.loads(calls[-1][0].data)
    assert body["format"] == "json" and body["stream"] is False
    assert body["options"] == {"temperature": 0, "seed": 31, "num_predict": 256}
    assert body["think"] is False
