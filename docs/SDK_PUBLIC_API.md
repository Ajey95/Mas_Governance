# Python package and CLI contract (0.2.x)

MASGuardEval 0.2.x is an early research SDK. The supported import surface is
the names in `masguardeval.__all__`; direct imports from other modules may
change between minor 0.x releases. Python 3.10+ is supported by package
metadata. `EvaluationEngine`, `GoldenDataset`, `Scenario`, `ExecutionEvent`,
`Trace`, `Span`, and `MetricResult` form the core integration path.

## Execution contract

An adapter yields proposed `ExecutionEvent` intents. A guarded run checks each
tool intent before calling its registered handler. A blocked call never reaches
that handler; the trace records the guard decision and stop reason. A baseline
run intentionally omits those checks and must use isolated test tools. A
generator adapter receives the actual tool feedback before proposing its next
event. `FrameworkSession` provides the same guarded boundary for native tool
objects in LangChain, LangGraph, AutoGen, and CrewAI. A session is for one run;
`finish()` closes it and returns its trace. A blocked native tool raises
`FrameworkToolBlocked`, and the handler is not called.

Only calls sent through this boundary are guarded or traced. A framework's
unwrapped tool or side effect inside a graph node is outside the SDK's control.
Wrap every side-effecting tool and record agent/message hooks if that topology
is needed. The runtime LangGraph helper records executed graph events and
checkpoint IDs, while the native tool node enforces the tool guard.

For candidate failure propagation, adapters can put an earlier unique action
token in `ExecutionEvent.metadata["caused_by"]`. `FrameworkSession.agent_step`
and `message` return tokens; `call` accepts `caused_by` and optional `action_id`.
Resolved tokens persist as source span IDs. Missing or repeated tokens stay
unlinked. Parent-span nesting alone is not a CFP dependency edge.

## Installed command

`[project.scripts]` creates `masguardeval` on install. All commands require
caller-owned input or an explicit trace source; the package does not ship the
research dataset.

The installed 0.2.0 command includes the detailed report, paired custom-agent
comparison, and timed diagnosis workflow shown below.

```powershell
masguardeval validate --dataset examples/fictional_scenarios.json
masguardeval evaluate --dataset examples/fictional_scenarios.json --scenario fictional_tool_boundary --out evaluation.json
masguardeval run-agent --dataset examples/fictional_scenarios.json --scenario fictional_tool_boundary --factory examples/cli_agent_factory.py:create_engine --out agent-run.json --sqlite runs.sqlite3
masguardeval compare-agent --dataset examples/fictional_scenarios.json --scenario fictional_tool_boundary --factory examples/cli_agent_factory.py:create_engine --allow-unguarded --out comparison.json --sqlite runs.sqlite3
masguardeval trace-report --input agent-run.json --json-out trace-report.json --md-out trace-report.md
masguardeval trace-report --input comparison.json --mode baseline --json-out baseline-detail.json
masguardeval trace-report --input comparison.json --mode guarded --json-out guarded-detail.json
masguardeval trace-report --trace-id TRACE_ID --sqlite runs.sqlite3 --json-out saved-report.json --md-out saved-report.md
masguardeval report --dataset examples/fictional_scenarios.json --json-out report.json --md-out report.md
masguardeval diagnosis-packet --report paired-study.json --architecture single --trial 1 --review-out diagnosis_blinded --private-map-out private/diagnosis_map.json
masguardeval diagnosis-assign --packet diagnosis_blinded/blinded_trials.jsonl --private-map private/diagnosis_map.json --out-dir diagnosis_panels --private-manifest-out private/assignment.json
masguardeval diagnosis-reference-template --packet diagnosis_blinded/blinded_trials.jsonl --out private/reference.jsonl
masguardeval diagnosis-review --packet diagnosis_panels/panel_a_1.jsonl --reviewer-id reviewer_a1 --reviewer-role expert --out private/reviewer_a1.jsonl
masguardeval diagnosis-analyze --packet diagnosis_blinded/blinded_trials.jsonl --private-map private/diagnosis_map.json --reviews private/reviewer_a1.jsonl private/reviewer_a2.jsonl private/reviewer_b1.jsonl private/reviewer_b2.jsonl --reference private/reference.jsonl --out private/diagnosis_analysis.json
masguardeval export --trace-id TRACE_ID --project my-study --sqlite runs.sqlite3
```

`validate` loads the JSON and checks scenario structure. `evaluate` and
`report` use the scripted reference adapter and do not claim model or human
outcomes. `run-agent` imports a trusted caller-owned `path.py:callable` or
`module:callable`; that callable receives the loaded `GoldenDataset` and must
return an `EvaluationEngine` configured with the caller's adapter and tool
handlers. It runs the selected scenario **guarded only** and emits its trace,
metrics, observed graph, and recommendations. `--sqlite` also saves the trace
for local inspection. A factory is executable Python; only load code you trust,
and route every side-effecting tool through the guarded engine. No unguarded
baseline is launched by this command. A model-driven adapter may make external
calls and must be configured by its owner. See
[`examples/cli_agent_factory.py`](../examples/cli_agent_factory.py) for the
fictional contract.

`compare-agent` loads the same trusted factory once and calls it twice before
execution. Each condition must receive a fresh engine and adapter, matching
agent name, tool names, guard names, and event budget. Each run starts a fresh
mock workspace. `--allow-unguarded` is required because the baseline skips
guards; use only isolated test handlers. A caller-owned model, external store,
or service may still have shared state, so the caller must reset or isolate it.
The output has baseline/guarded traces, metrics, graphs, findings, and a
directional metric change only where both scores apply. This is a descriptive
trace comparison, not independently judged safety or task success.

`trace-report` reads one `run-agent` JSON file with `--input`, a chosen
`--mode` from a `compare-agent` JSON file, or one saved run
with `--trace-id` and either `--sqlite` or `MASGUARDEVAL_DATABASE_URL` (exactly
one store). At least one of `--json-out` and `--md-out` is required. It checks
scenario/trace and span references, then recomputes metrics, findings, and the
observed graph from the recorded spans; it does not trust precomputed fields
in an input file. JSON includes the scenario and full trace snapshots, their
canonical SHA-256 hashes, source file hash where applicable, metric evidence,
graph/dependency paths, and a per-span timeline. Markdown presents the same
interpretation and evidence IDs without copying raw prompt or tool content.
Source hashes identify bytes, not author identity or execution authenticity.
This single-trace report makes no matched baseline, independent task-success,
or causal root-cause claim. Review the JSON for sensitive content before sharing.

The `diagnosis-*` commands prepare blinded paired-run packets, assign four
reviewer panels, collect actual interactive diagnosis duration with a local
monotonic clock, and compare span answers to a separately authored reference.
Each reviewer sees only one condition of a scenario. Complete all four panel
reviews before analysis; `diagnosis-review --resume` continues a partially
completed, hash-matched panel. These commands collect evidence; they do not create
human reviewers, authentic reference labels, or measured time savings by
themselves. See the [timed study protocol](PAPER_STUDY_PROTOCOL.md#timed-human-diagnosis).

`export` requires `LANGSMITH_API_KEY` and exactly one source: the
`--sqlite` file or `MASGUARDEVAL_DATABASE_URL`. It sends trace content to the
selected LangSmith project only on explicit invocation. CLI JSON goes to
stdout unless an output path is supplied; usage and validation failures exit
with status 2.

## Distribution and compatibility

Build the source archive and wheel with `python -m build --sdist --wheel backend`.
Install the wheel into a fresh environment and run the examples before a
release. The `langchain`, `langgraph`, `autogen`, and `crewai` extras are
optional; `langgraph-postgres` is a separate extra for durable checkpointing.
The repository tests against installed framework versions and CI repeats the
integration examples. A new minor 0.x release may change the public API; a
patch 0.2.x release should preserve this documented contract.

On 2026-10-15, a wheel installed into a fresh Windows Python 3.12 environment
outside the checkout. The installed CLI and custom-agent example passed. A
second install of the four framework extras passed `pip check` and all native
examples with LangChain 1.4.6, LangGraph 1.2.15, AutoGen Core 0.7.5, and
CrewAI 1.15.28. CI tests Python 3.10 and 3.12 package installs, plus a Python
3.12 adapter job. These checks exercise fictional local tools, not live model
agents or all possible dependency versions.

Software source, examples, dashboard, website, and usage guides are MIT
licensed; see the repository [license](../LICENSE) and `backend/LICENSE`.
The paper, study datasets, reviewer records, and experimental reports are
outside that scope. A successful wheel build
does not establish empirical metric validity or paper readiness.

The current [PyPI release is 0.2.0](https://pypi.org/project/masguardeval/0.2.0/),
published from tag `v0.2.0` through GitHub's trusted-publisher workflow.
The local FastAPI Swagger UI remains
at `/docs`; the public site does not expose evaluation APIs. Earlier versioned
guides remain historical snapshots; use the guides on `main` for the current
workflow.
