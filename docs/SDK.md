# Python SDK

Use MASGuardEval as a Python framework inside tests, notebooks, CI jobs, or another agent system.
The supported 0.1.x surface and installed command are in the [package contract](SDK_PUBLIC_API.md).
Runnable fictional integrations for custom agents, LangChain, LangGraph,
AutoGen, and CrewAI are in the [examples](../examples/README.md).

## Install

```powershell
cd C:\path\to\Mas_Governance
python -m pip install -e backend
```

## Evaluate One Scenario

```python
from masguardeval import EvaluationEngine

engine = EvaluationEngine.from_dataset_path("datasets/golden_scenarios.json")
result = engine.evaluate("auth_001")

print(result.scenario.scenario_id)
print(result.baseline_metrics["TSP"].score)
print(result.guarded_metrics["TSP"].score if result.guarded_metrics["TSP"].applicable else "N/A")
print(result.recommendations)
```

## Evaluate Every Scenario

```python
from masguardeval import EvaluationEngine

engine = EvaluationEngine.from_dataset_path("datasets/golden_scenarios.json")
payload = engine.generate_dashboard()

for item in payload["results"]:
    scenario_id = item["scenario"]["scenario_id"]
    reduction = item["risk_reduction"]
    print(scenario_id, reduction)
```

## Result Object

`engine.evaluate()` returns an `EvaluationResult`.

| Field | Description |
| --- | --- |
| `scenario` | Scenario metadata and expected safe behavior. |
| `baseline_trace` | Trace from unguarded execution. |
| `guarded_trace` | Trace from guarded execution. |
| `baseline_metrics` | Metric results for baseline execution. |
| `guarded_metrics` | Metric results for guarded execution. |
| `risk_reduction()` | Per-metric guarded vs baseline improvement where both runs are applicable; serialized as `risk_reduction`. |
| `recommendations` | Guard suggestions for failed baseline metrics. |
| `baseline_graph`, `guarded_graph` | Observed directed agent–tool interactions and linked failure spans. |

## Add a Custom Dataset

Create a JSON file with the same structure as `datasets/golden_scenarios.json`.

```python
from masguardeval import GoldenDataset

dataset = GoldenDataset.load("my_scenarios.json")
print(len(dataset.scenarios))
```

Each scenario should include:

- `scenario_id`
- `risk_type`
- `user_role`
- `prompt`
- `expected_safe_behavior`
- `allowed_tools`
- `blocked_tools`
- `required_tools`
- `parameter_schema`
- `metrics`

Optional `subject_attributes`, `resource_attributes`, `attribute_policies`, `high_risk_tools`, and `sensitive_tools` configure ABAC, approval, and sensitive-action checks. `reference_events` lets a scripted scenario define its own concrete event sequence. Label candidate fixtures with `provenance: synthetic_candidate_unadjudicated` until independent review.

## Integrate a Custom Agent System

Adapters supply pre-execution intents to MASGuardEval. To make a guard effective with an external agent, its tool calls must go through this runner before the real tool side effect; importing an already executed log cannot prevent that side effect. The built-in adapter is scripted and does not use an LLM.

`plan()` may return a list or yield intents one at a time. With a generator, the yielded expression receives the executed event's output. A blocked intent ends iteration without executing the tool or resuming the generator. This supports agents that choose their next action from tool feedback:

```python
def plan(self, scenario, mode):
    result = yield ExecutionEvent(
        agent="Retriever", event_type="tool_call", action="read_file",
        user_role=scenario.user_role, tool="my_tool", parameters={"query": scenario.prompt},
    )
    yield ExecutionEvent(
        agent="Responder", event_type="agent_step", action="answer",
        user_role=scenario.user_role, output=f"Tool returned: {result}",
    )
```

The tool must appear in the scenario allowlist and have a registered handler. When using a real external tool, run baseline experiments inside an isolated test environment because baseline mode intentionally has no guards.

```python
from masguardeval import EvaluationEngine, GoldenDataset
from masguardeval.models import ExecutionEvent


class MyAgentAdapter:
    name = "my_agent_system"

    def plan(self, scenario, mode):
        return [
            ExecutionEvent(
                agent="Planner",
                event_type="agent_step",
                action="plan_task",
                user_role=scenario.user_role,
                input=scenario.prompt,
                output="planned action",
            ),
            ExecutionEvent(
                agent="Executor",
                event_type="tool_call",
                action="call:my_tool",
                user_role=scenario.user_role,
                tool="my_tool",
                parameters={"query": "example"},
            ),
        ]


dataset = GoldenDataset.load("datasets/golden_scenarios.json")
engine = EvaluationEngine(dataset=dataset, adapter=MyAgentAdapter())
engine.register_tool("my_tool", lambda parameters, workspace: "tool result")
result = engine.evaluate("auth_001")
```

## Add a Custom Guard

Guards run before sensitive execution events.

```python
from masguardeval.guards import GuardDecision
from masguardeval.models import PolicyDecision


class BlockDangerousTool:
    name = "BlockDangerousTool"

    def evaluate(self, scenario, event, recent_events):
        if event.tool == "dangerous_tool":
            return GuardDecision(
                PolicyDecision.BLOCK,
                self.name,
                "dangerous_tool is not allowed",
            )
        return GuardDecision(PolicyDecision.ALLOW, self.name, "event allowed")


engine.register_guard(BlockDangerousTool())
```

## SDK Surface

| Object | Purpose |
| --- | --- |
| `GoldenDataset` | Load and validate scenarios. |
| `EvaluationEngine` | Run baseline and guarded evaluations. |
| `ExecutionEvent` | Event emitted by an adapter. |
| `Trace` | Full execution record. |
| `Span` | One trace operation. |
| `GuardDecision` | Guard middleware output. |
| `MetricResult` | Score, threshold, pass/fail, and details. |
| `TraceStore` | SQLite persistence for individual spans and completed traces. |
| `PostgresTraceStore` | PostgreSQL JSONB persistence with the same store contract. |
| `FrameworkSession` and `ToolSpec` | Guarded native tools for LangChain, LangGraph, AutoGen, and CrewAI. |
| `LangSmithExporter` | Explicit upload of a completed trace and its span tree. |
| `PgVectorScenarioIndex` | Optional similarity lookup over supplied scenario embeddings. |
| `AgentToolGraphBuilder` | Directed observed agent/tool graph with typed edges. |
| `LiveWorkspaceAdapter` | Model-driven Planner, Executor, Reviewer adapter. |
| `SingleAgentWorkspaceAdapter` | Matched reason/act/observe comparator. |

To use an external model client, install `backend[live]` and construct `OpenAIResponsesClient` with a pinned model. For a local Ollama pilot, use `OllamaChatClient` or `scripts/run_live_experiment.py --provider ollama`. The runner sends observed tool results back to the adapter generator. The model receives the task and available mock tools, while expected safe behavior stays in the evaluator's rubric. No external model credentials are stored in this project.

See [Integrations](INTEGRATIONS.md) for native framework examples and the PostgreSQL, pgvector, and LangSmith setup.

## Common Patterns

### Fail CI if guarded execution fails a metric

```python
from masguardeval import EvaluationEngine

engine = EvaluationEngine.from_dataset_path("datasets/golden_scenarios.json")
result = engine.evaluate("auth_001")

failed = [key for key, metric in result.guarded_metrics.items() if metric.applicable and not metric.passed]
if failed:
    raise SystemExit(f"Guarded run failed metrics: {failed}")
```

### Save dashboard payload

```python
import json
from masguardeval import EvaluationEngine

engine = EvaluationEngine.from_dataset_path("datasets/golden_scenarios.json")
payload = engine.generate_dashboard()

with open("reports/latest_evaluation.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)
```
