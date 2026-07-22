# MASGuardEval Docs

Evaluate multi-agent LLM systems with golden datasets, structured traces, mathematical safety metrics, and guard benchmarking.

MASGuardEval helps answer four practical questions:

- Did the agent system behave safely?
- Which agent, tool, or guard caused the outcome?
- Did a mitigation reduce risk compared with baseline execution?
- Which metric failed, and what guard should be added next?

## Choose Your Path

| Goal | Start here |
| --- | --- |
| Run the project locally | [Quickstart](QUICKSTART.md) |
| Use MASGuardEval as a Python SDK | [SDK guide](SDK.md) |
| Call the backend over HTTP | [API guide](API.md) and live Swagger UI |
| Understand metric formulas | [Metrics reference](METRICS.md) |
| Integrate another agent framework | [Architecture](ARCHITECTURE.md) |
| Copy common examples | [Examples](EXAMPLES.md) |

## Documentation Map

| Document | Use it when |
| --- | --- |
| [Quickstart](QUICKSTART.md) | You need a working local run first. |
| [SDK guide](SDK.md) | You want to embed MASGuardEval in Python tests, CI, or notebooks. |
| [API guide](API.md) | You want to call MASGuardEval from another service or frontend. |
| [Examples](EXAMPLES.md) | You want copy-paste snippets for common workflows. |
| [Metrics reference](METRICS.md) | You need the exact mathematical formulas and pass thresholds. |
| [Architecture](ARCHITECTURE.md) | You need system design, extension points, and scaling notes. |

## What You Can Build

### Evaluation pipeline

Run the same scenario through a baseline system and a guarded system, then compare the results.

```python
from masguardeval import EvaluationEngine

engine = EvaluationEngine.from_dataset_path("datasets/golden_scenarios.json")
result = engine.evaluate("auth_001")

print(result.baseline_metrics["TSP"].score)
print(result.guarded_metrics["TSP"].score)
print(result.recommendations)
```

### API service

Expose evaluations to dashboards, CI jobs, notebooks, or external applications.

```powershell
py -3.11 -m uvicorn masguardeval.api:app --host 127.0.0.1 --port 8000
```

```text
GET http://127.0.0.1:8000/evaluate/auth_001
GET http://127.0.0.1:8000/dashboard
```

### Dashboard

Inspect scenarios, baseline vs guarded metrics, trace timelines, risk reduction, and recent runs.

```powershell
cd frontend
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

## Core Concepts

| Concept | Description |
| --- | --- |
| Scenario | A controlled risk case from the golden dataset. |
| Baseline run | Execution without mitigation guards. |
| Guarded run | Execution with guard middleware enabled. |
| Trace | Full execution record for one scenario run. |
| Span | One agent step, tool call, guard decision, memory operation, or final response. |
| Metric | Formula-based safety measurement computed from trace data. |
| Guard | Middleware that can allow, block, modify, require approval, or log an event. |

## Live API Docs

When the backend is running:

```text
Swagger UI: http://127.0.0.1:8000/docs
ReDoc:      http://127.0.0.1:8000/redoc
```

Use Swagger UI or ReDoc as the human-facing API reference. The checked-in [OpenAPI schema](openapi.json) is the machine-readable contract used by docs tooling and client generation.

## Publishable Docs Site

The docs folder includes [docs.json](docs.json), a Mintlify-style navigation config with a dedicated API Reference tab backed by [openapi.json](openapi.json).

Recommended publishing options:

| Tool | Best fit for this project |
| --- | --- |
| Mintlify | Code-first docs with generated OpenAPI API reference. |
| Docusaurus | Markdown/MDX static docs site owned by the engineering repo. |
| ReadMe | Hosted API explorer and API usage analytics. |
| GitBook | Managed docs for mixed technical and non-technical teams. |

## Documentation Standard

These docs follow a Stripe/GitHub/Docker-style structure and MDN-style writing rules:

- Start with the fastest successful path.
- Keep concepts separate from tasks.
- Use copy-paste code samples.
- Keep API reference backed by OpenAPI.
- Keep metric formulas and implementation notes close together.
- Prefer short sections, direct headings, and scan-friendly tables.
