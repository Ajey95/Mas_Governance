# Python SDK

Use MASGuardEval as a Python framework inside tests, notebooks, CI jobs, or another agent system.

## Install

```powershell
cd C:\path\to\Mas_Governance
py -3.11 -m pip install -e backend
```

## Evaluate One Scenario

```python
from masguardeval import EvaluationEngine

engine = EvaluationEngine.from_dataset_path("datasets/golden_scenarios.json")
result = engine.evaluate("auth_001")

print(result.scenario.scenario_id)
print(result.baseline_metrics["TSP"].score)
print(result.guarded_metrics["TSP"].score)
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
| `risk_reduction` | Per-metric guarded vs baseline delta. |
| `recommendations` | Guard suggestions for failed baseline metrics. |

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

## Integrate a Custom Agent System

Adapters convert an external agent system into MASGuardEval execution events.

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

## Common Patterns

### Fail CI if guarded execution fails a metric

```python
from masguardeval import EvaluationEngine

engine = EvaluationEngine.from_dataset_path("datasets/golden_scenarios.json")
result = engine.evaluate("auth_001")

failed = [key for key, metric in result.guarded_metrics.items() if not metric.passed]
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
