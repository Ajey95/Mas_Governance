# MASGuardEval

The Python package and code under [`backend/`](backend/) are available under
the [MIT License](backend/LICENSE). This license does not cover the paper,
study datasets, reviewer records, or other files outside `backend/`.

MASGuardEval is a research **reference implementation** for tracing and testing guard decisions in a software workspace assistant. Seven reference scenarios cover unauthorized access, disclosure, unsafe tools, loops, propagation, polluted context, and conflicting agents. A separate set of 35 synthetic candidate tasks supports pilot experiments.

The default adapter supplies scripted agent intents. A model-driven adapter has completed a local Ollama pilot and a small external OpenAI service smoke; independently adjudicated trials remain outstanding. Reached tools execute in a fresh, in-memory mock workspace; no real email account, file system, or shell command is used. The included results are **not evidence that a real multi-agent LLM is safe**. See [Research status](docs/RESEARCH_STATUS.md) before using results in a paper.

## Current implementation

| Component | State |
| --- | --- |
| Dataset and validation | Seven reference cases plus 35 synthetic, unadjudicated candidate tasks |
| Baseline and guarded runner | Implemented; a block stops later events |
| Mock workspace tools | Implemented; isolated state per run |
| Eight trace metrics | Implemented with applicability flags and evidence counts |
| Guard ablations, causal span graph, agent–tool graph | Implemented for observed traces |
| RBAC, ABAC, high-risk approval | Implemented and tested in mock execution |
| API, SQLite spans, SSE stream, JSON/Markdown reports, responsive dashboard | Implemented; dashboard includes a live event log and per-trace findings report |
| Model-driven single-agent and three-agent adapters | Implemented with mocked-client tests and one local Ollama reference pilot; no paper-grade trial |
| Study review and analysis | Task freeze gate, two-reviewer outcome packets, adjudication, a secondary three-provider model council, held-out metric checks, and matched internal guard profiles implemented; one three-provider council service smoke passed; independent human data pending |
| LangChain, LangGraph, AutoGen, CrewAI | Native guarded tool wrappers implemented and exercised against installed framework packages; LangGraph executed graph routes and PostgreSQL checkpoint pause/resume on Render |
| Installable SDK and CLI | Python wheel and source archive build; the installed `masguardeval` command and all five fictional integration examples passed in a fresh Python environment |
| PostgreSQL, pgvector, LangSmith | Supabase PostgreSQL, pgvector, owner-scoped traces, and deployed checkpoint routes verified; explicit LangSmith exporter implemented but no live export trial without a credential |
| Independent labels, held-out validity study | Not supplied by this repository |

## Run locally (PowerShell)

Use Python 3.10+ and Node.js. From the repository root:

```powershell
python -m pip install -e backend
python -m pytest backend/tests -q
$env:PYTHONPATH = "backend"
python scripts/run_experiments.py
python scripts/run_evaluation.py
python -m uvicorn masguardeval.api:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
npm install
npm run build
npm run dev
```

Open `http://127.0.0.1:5173`. API reference is at `http://127.0.0.1:8000/docs`. The dashboard shows scenario comparisons, an interaction timeline, the observed agent–tool graph, a live event log, saved runs, downloadable trace findings, and authenticated approval requests when configured. The direct local `masguardeval.api:app` entry point is for localhost development and has no user-auth middleware; deploy the `masguardeval.web:app` entry point with the authentication flags described in the deployment guide.

For another codebase, install [`masguardeval` 0.1.0 from PyPI](https://pypi.org/project/masguardeval/0.1.0/)
as a Python package and use the
[`masguardeval` command and SDK contract](docs/SDK_PUBLIC_API.md). The
[runnable examples](examples/README.md) use fictional handlers and need no
external credentials.

The [hosted Render and Supabase path](docs/DEPLOY_RENDER_SUPABASE.md) is live as a private research preview. It uses a shared preview gate followed by individual Supabase Auth accounts. Deployed two-account tests verified owner-scoped runs, graphs, findings, SSE logs, and LangGraph traces. General email onboarding and public-service hardening remain separate operational work.

## Results and definitions

- `reports/experiment_report.md`: scenario and ablation summary from the scripted reference adapter.
- `reports/experiment_report.json`: machine-readable report with trace evidence.
- `reports/latest_evaluation.json`: dashboard payload produced by `run_evaluation.py`.
- `reports/evaluator_agreement.json`: demonstration of Cohen's kappa on **synthetic example labels**, not collected human or judge annotations.

Metric formulas, denominator rules, and limitations are in [Metrics](docs/METRICS.md). `CFP` is retained as an API key but means **observed cascading failure rate**, not an estimated probability. `DT` is a **diagnosis depth proxy**, not measured diagnosis time. An inapplicable metric is marked `applicable: false` and shown as N/A.

## Extend the runner

`EvaluationEngine(dataset, adapter=...)` accepts an adapter that emits `ExecutionEvent` intents. Generator adapters receive event/tool output before choosing the next intent. `register_tool(name, handler)` provides a tool executor; guarded checks run before that handler. Native tool wrappers are available for LangChain, LangGraph, AutoGen, and CrewAI. The built-in tools never touch the host. See the [SDK guide](docs/SDK.md), [integrations](docs/INTEGRATIONS.md), and [architecture](docs/ARCHITECTURE.md).

## Research boundary

The four user-supplied planning documents describe a larger empirical paper. This repository contains the software framework and pilot task set, but publication claims require independently gathered agent trials, held-out and adjudicated tasks, provenance for annotations, human review, metric validation, and comparisons to appropriate baselines. Those cannot be inferred from scripted cases or template-derived candidates. The detailed handoff is in [Research status](docs/RESEARCH_STATUS.md).

A [conference-format working manuscript](paper/MASGuardEval_SAIS27.tex) records the verified method and feasibility pilot with explicit placeholders for the independent study. An eight-page XeTeX PDF was built and visually checked; the manuscript is not submission ready without the independent study.
