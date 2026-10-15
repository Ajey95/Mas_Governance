# Python package and CLI contract (0.1.x)

MASGuardEval 0.1.x is an early research SDK. The supported import surface is
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

## Installed command

`[project.scripts]` creates `masguardeval` on install. All commands require
caller-owned input or an explicit trace source; the package does not ship the
research dataset.

```powershell
masguardeval validate --dataset examples/fictional_scenarios.json
masguardeval evaluate --dataset examples/fictional_scenarios.json --scenario fictional_tool_boundary --out evaluation.json
masguardeval report --dataset examples/fictional_scenarios.json --json-out report.json --md-out report.md
masguardeval export --trace-id TRACE_ID --project my-study --sqlite runs.sqlite3
```

`validate` loads the JSON and checks scenario structure. `evaluate` and
`report` use the scripted reference adapter and do not claim model or human
outcomes. `export` requires `LANGSMITH_API_KEY` and exactly one source: the
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
patch 0.1.x release should preserve this documented contract.

On 2026-10-15, a wheel installed into a fresh Windows Python 3.12 environment
outside the checkout. The installed CLI and custom-agent example passed. A
second install of the four framework extras passed `pip check` and all native
examples with LangChain 1.4.6, LangGraph 1.2.15, AutoGen Core 0.7.5, and
CrewAI 1.15.28. CI tests Python 3.10 and 3.12 package installs, plus a Python
3.12 adapter job. These checks exercise fictional local tools, not live model
agents or all possible dependency versions.

The Python package and code under `backend/` are MIT licensed; see
`backend/LICENSE`. This license does not apply to the paper, study datasets,
reviewer records, or other files outside `backend/`. A successful wheel build
does not establish empirical metric validity or paper readiness.

For a tagged `vX.Y.Z` release, `.github/workflows/publish-pypi.yml` checks that
the tag matches the package version, builds and checks both archives, and uses
PyPI Trusted Publishing from GitHub's `pypi` environment. The PyPI project
owner must register `Ajey95/Mas_Governance`, workflow `publish-pypi.yml`, and
environment `pypi` as a trusted publisher before pushing the first release tag.
