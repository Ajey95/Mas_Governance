# MASGuardEval documentation

MASGuardEval is a reference implementation for testing guard behavior in a mock software workspace. The default agent intentions are scripted; model-driven adapters have completed a local Ollama reference pilot. Seven reference cases and 35 synthetic candidate tasks exercise the runner and eight trace metrics. The dashboard and report commands show actual mock execution and mark metrics N/A when no valid denominator exists.

| Need | Guide |
| --- | --- |
| Install and run | [Quickstart](QUICKSTART.md) |
| Integrate a custom adapter and tool handlers | [Python SDK](SDK.md) |
| Install the library and use its command | [Package and CLI contract](SDK_PUBLIC_API.md) |
| Run external-codebase examples | [Runnable integrations](../examples/README.md) |
| Use LangChain, LangGraph, AutoGen, CrewAI, PostgreSQL, pgvector, or LangSmith | [Integrations](INTEGRATIONS.md) |
| Use HTTP endpoints | [API](API.md) |
| Understand formulas and caveats | [Metrics](METRICS.md) |
| Reproduce reference reports | [Experiments](EXPERIMENTS.md) |
| Understand the design | [Architecture](ARCHITECTURE.md) |
| Assess paper readiness | [Research status](RESEARCH_STATUS.md) |
| Run an independent study | [Paper study protocol](PAPER_STUDY_PROTOCOL.md) |
| Author the study task set | [Study authoring guide](STUDY_AUTHORING_GUIDE.md) |
| Check novelty claims against nearby work | [Related-work audit](RELATED_WORK_AUDIT.md) |

The included synthetic annotation pairs demonstrate the agreement calculation only. See [research status](RESEARCH_STATUS.md) for independent data and validation required for a paper.
