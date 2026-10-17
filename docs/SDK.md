# Python SDK

Use MASGuardEval as a Python framework inside tests, notebooks, CI jobs, or another agent system.
The supported 0.2.x surface and installed command are in the [package contract](SDK_PUBLIC_API.md).
Runnable fictional integrations for custom agents, LangChain, LangGraph,
AutoGen, and CrewAI are in the [examples](../examples/README.md).

## Install

For another codebase, install the published package:

```powershell
python -m pip install "masguardeval==0.2.1"
```

For development from a repository checkout, use:

```powershell
cd C:\path\to\Mas_Governance
python -m pip install -e backend
```

The package contains the SDK and CLI. The fictional datasets and example
factories shown below live in the Git repository and are not bundled in the
wheel.
The installed command includes guarded custom-agent runs, paired comparisons,
detailed trace reports, and the optional timed diagnosis study workflow.

## Run Your Agent from the CLI

From the repository root, try the trusted fictional factory:

```powershell
masguardeval run-agent --dataset examples/fictional_scenarios.json --scenario fictional_tool_boundary --factory examples/cli_agent_factory.py:create_engine --out reports/my-agent.json --sqlite reports/runs.sqlite3
masguardeval compare-agent --dataset examples/fictional_scenarios.json --scenario fictional_tool_boundary --factory examples/cli_agent_factory.py:create_engine --allow-unguarded --out reports/my-comparison.json --sqlite reports/runs.sqlite3
masguardeval trace-report --input reports/my-agent.json --json-out reports/my-agent-report.json --md-out reports/my-agent-report.md
```

Your `path.py:create_engine` function receives the loaded `GoldenDataset` and
returns an `EvaluationEngine` configured with your adapter and registered tool
handlers. The command runs one scenario **guarded only** and writes the trace,
metric applicability and scores, observed graph, and recommendations. It does
not discover agent tools automatically. The factory is executable Python, so
only load code you trust. See the [CLI contract](SDK_PUBLIC_API.md) and
[fictional factory](../examples/cli_agent_factory.py) for the exact pattern.

`compare-agent` calls the factory twice and requires a fresh engine and adapter
for each condition. It records both traces, graphs, metric applicability, and
findings in one JSON file. `--allow-unguarded` explicitly opts into a baseline
that skips guards; use isolated test handlers and reset any external state the
handlers own. The CLI does not establish matched model sampling or task success.
For detailed per-condition evidence, run `trace-report --input
reports/my-comparison.json --mode baseline` or `--mode guarded` with a JSON or
Markdown output path.

The `trace-report` command produces a detailed single-run provenance,
evaluation, and observability report from the saved output. It recomputes the
metrics and findings from spans, includes evidence IDs and graph dependency
paths, and records scenario/trace hashes. For a run saved only in SQLite, use
the saved trace ID:

```powershell
masguardeval trace-report --trace-id TRACE_ID --sqlite reports/runs.sqlite3 --json-out reports/my-agent-report.json --md-out reports/my-agent-report.md
```

The JSON contains raw trace data, so inspect it before sharing. The report
does not establish independent human validation, a matched baseline, or causal
root cause. See the [CLI contract](SDK_PUBLIC_API.md) for the exact options.

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
- `required_tools` (explicit task obligations; omission means none, not all allowed tools)
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


dataset = GoldenDataset.load("my_scenarios.json")  # Declare my_tool in the scenario's allowed_tools.
engine = EvaluationEngine(dataset=dataset, adapter=MyAgentAdapter())
engine.register_tool("my_tool", lambda parameters, workspace: "tool result")
scenario = dataset.get("my_scenario_id")
trace = engine.run_guarded(scenario)
metrics = engine.compute_metrics(scenario, trace)
```

`run_guarded()` is the safe default for a real handler. Use `evaluate()` only
when both its guarded and unguarded baseline runs execute against isolated test
tools.

### Record a candidate failure dependency

Use a unique `ExecutionEvent.action` for each event. When a later event actually
uses an earlier event's output, set `metadata={"caused_by": earlier_action}`.
The runner resolves the reference to a source span ID and records it as
`causal_parent_span_id`. Missing or repeated action names remain unlinked;
ordinary span nesting does not raise CFP. The link declares an observed
dependency for review, not proven causation.

For a native `FrameworkSession`, `agent_step()` and `message()` return action
tokens that can be passed as `caused_by`. `call()` accepts `caused_by` and an
optional unique `action_id` when a later event must cite that tool result:

```python
plan = session.agent_step("Planner", "plan", output="inspect the fixture")
handoff = session.message("Planner", "Executor", "use this plan", caused_by=plan)
result = session.call("my_tool", {"query": "example"}, agent="Executor",
                      caused_by=handoff, action_id="my-tool-call-1")
session.agent_step("Reviewer", "review", output=result, caused_by="my-tool-call-1")
```

Native framework wrappers do not infer information flow inside uninstrumented
nodes. Record these links explicitly when testing failure propagation; otherwise
the trace and policy decisions remain useful, while CFP cannot attribute a
downstream failure to an earlier one.

If a later failure was independently checked and has no recorded upstream
dependency, set `metadata={"dependency_assessed": True}` on that failure event.
Leave this flag absent when the relationship is unknown. CFP is N/A when a
later failure has neither a resolved link nor this explicit assessment.

### Supply comparable metric evidence

PHR checks recorded tool arguments against the scenario's parameter schema,
including required/extra keys, types, `const`, `enum`, and maximum string
length. Calls without a schema or explicit bad-parameter assessment are
reported as unassessed rather than clean.

CPI needs an explicit Boolean `context_polluted` assessment on each context
span being counted; `sanitized: true` records removal of a known polluted
context. `FrameworkSession.agent_step(..., metadata=...)` and
`message(..., metadata=...)` accept those fields. Do not label unknown context
as clean merely to obtain a score.

CCR compares `agent_step` spans only when adapters record the same
`decision_scope` and `decision_revision` with a `decision_value` for each
agent. The scope must name one concrete proposition and the revision must
identify the same state snapshot. Different revisions are not treated as a
contradiction. Unscoped model text remains unassessed. These annotations are
observations made by the adapter, not independent expert labels.

For actual human diagnosis duration, use the separate
[timed study protocol](PAPER_STUDY_PROTOCOL.md#timed-human-diagnosis). Runtime
DT remains a descriptive first-signal position. Routine allow-guard spans are
excluded, and DT is not used as a paired safety improvement or threshold gate.

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
| `MetricResult` | Score, applicability, exploratory reference threshold/rule result, and evidence details. DT has null threshold and rule result. |
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

### Gate CI on a concrete policy invariant

Metric thresholds are exploratory and are not a substitute for checking the
behavior your application requires. For example, fail if a forbidden tool
reached the executor:

```python
from masguardeval import EvaluationEngine

engine = EvaluationEngine.from_dataset_path("datasets/golden_scenarios.json")
result = engine.evaluate("auth_001")

forbidden = set(result.scenario.blocked_tools)
executed = [span for span in result.guarded_trace.spans if span.span_type == "tool_call"]
if any(span.tool in forbidden for span in executed):
    raise SystemExit("A forbidden tool reached the executor")
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
