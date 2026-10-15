# External framework and observability integrations

The native wrappers below route a framework's tool invocation into one `FrameworkSession`. The session checks the scenario guards before calling the registered handler and records the result as a MASGuardEval span. Wrap **every side-effecting tool** supplied to the agent; an original unwrapped tool can bypass the guard. Use an isolated workspace for baseline runs, since baseline mode executes without guard checks.

## Install

Install only the extras you use:

```powershell
python -m pip install -e 'backend[langchain,langgraph,autogen,crewai,postgres,pgvector,langsmith]'
```

`backend[all-integrations]` installs the same set. Each framework package is optional, and importing `masguardeval` does not load them until you create its native tool.

## One scenario, one session

```python
from masguardeval import FrameworkSession, GoldenDataset, ToolSpec

scenario = GoldenDataset.load("datasets/golden_scenarios.json").get("auth_001")
session = FrameworkSession(scenario, mode="guarded", framework_name="my_agent")

# The tool name must occur in scenario.allowed_tools or scenario.blocked_tools.
spec = ToolSpec(
    name="mock_email_search",
    description="Search email in the isolated study workspace. Input: parameters object.",
    handler=lambda parameters, workspace: workspace.execute("mock_email_search", parameters),
)
```

Pass a native wrapper to the corresponding framework:

```python
from masguardeval import (
    make_langchain_tool, make_langgraph_tool_node,
    make_autogen_tool, make_crewai_tool,
)

langchain_tool = make_langchain_tool(session, spec)
# LangChain: create_agent(model=..., tools=[langchain_tool])

langgraph_node = make_langgraph_tool_node(session, [spec])
# LangGraph: graph.add_node("tools", langgraph_node)

autogen_tool = make_autogen_tool(session, spec)
# AutoGen: AssistantAgent(..., tools=[autogen_tool])

crewai_tool = make_crewai_tool(session, spec)
# CrewAI: Agent(..., tools=[crewai_tool])
```

The example shows the four wrapper shapes. In an actual run, create **a separate `FrameworkSession` per framework and per baseline/guarded run**; a session represents one trace. The wrappers accept a single `parameters` object matching `ExecutionEvent.parameters`. The external framework can supply model or agent reasoning; MASGuardEval observes calls sent through these wrappers. When finished, call `trace = session.finish(final_answer)` and then `session.metrics()` or `session.graph()`. If a guard blocks a call, the wrapper raises `FrameworkToolBlocked`; inspect `session.finish()` for the stop reason. If a framework converts tool errors to messages, end its agent loop when that error appears. The guard still prevents that call's handler from executing.

For multi-agent topology, call `session.agent_step(...)` and `session.message(sender, recipient, content)` from the framework's agent and message hooks. Native tool wrappers alone record tool calls; they cannot infer unseen internal agent messages or model tokens.

## LangGraph runtime tracing

For a compiled LangGraph, run it through `run_langgraph_graph` instead of calling
`graph.invoke` directly. The runner consumes LangGraph's runtime stream and
records executed nodes, conditional routes, checkpoint IDs, and interrupt or
resume events. The `thread_id` joins separate MASGuardEval traces across a
pause. Only actual routes are included in the observed graph; unchosen static
branches are not reported as executed.

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from masguardeval import FrameworkSession, run_langgraph_graph

# Keep the same checkpointer across invocations. build_graph creates a fresh
# StateGraph and wraps its tools with the supplied session before compilation.
checkpointer = MemorySaver()
config = {"configurable": {"thread_id": "fictional-case-001"}}
session = FrameworkSession(scenario, mode="guarded", framework_name="langgraph")
first = run_langgraph_graph(build_graph(session, checkpointer), session, initial_state, config=config)
if first.interrupted:
    # Obtain an authorized human decision before resuming the same thread.
    resumed_session = FrameworkSession(scenario, mode="guarded", framework_name="langgraph")
    resumed = run_langgraph_graph(
        build_graph(resumed_session, checkpointer), resumed_session,
        Command(resume=approved_value), config=config,
    )
```

In `build_graph`, create and register the guarded tool node before calling
`run_langgraph_graph`. Rebuild with the new session on resume so a resumed
tool call does not reuse a closed session.
The example `MemorySaver` is only for local testing; use a durable LangGraph
checkpointer for deployed pause/resume. The runtime recorder stores state key
names and checkpoint IDs, not state values or LLM tokens. Its graph observation
spans are excluded from the eight research metric denominators, preserving
comparability with runs recorded before this integration. Tool actions remain
guarded at the wrapped tool boundary. A graph node that performs an unwrapped
side effect can still bypass that boundary; instrument every such action.

For production checkpoints, LangGraph provides `PostgresSaver` in
`langgraph-checkpoint-postgres`: create it with the server-side database DSN,
call `setup()` once, and compile the graph with it. On Supabase, restrict the
checkpoint tables to a private schema and service role before storing any
private state. This integration has been tested with `MemorySaver`; a live
Supabase-backed LangGraph checkpoint round trip remains an operational gate.

## PostgreSQL trace storage

Set `MASGUARDEVAL_DATABASE_URL` to a PostgreSQL DSN before starting the API. The API and `scripts/run_live_experiment.py` then use `PostgresTraceStore`; otherwise they use SQLite. The store creates `masguardeval.masguardeval_runs` and `masguardeval.masguardeval_spans` in a dedicated private schema, keeps scenario snapshots and span payloads in JSONB, and exposes the same `begin`, `append`, `finish`, `get`, and `list` methods as SQLite. It enables RLS without client policies. Keep the DSN in a server environment variable, never in a frontend bundle, report, or committed file.

```powershell
$env:MASGUARDEVAL_DATABASE_URL = "postgresql://user:password@localhost:5432/masguardeval"
python -m uvicorn masguardeval.api:app --app-dir backend --reload
```

The database user needs permission to create the schema, tables, and indexes on first use. A PostgreSQL server must already be running. Existing `public.masguardeval_*` tables from an earlier experimental deployment are **not** migrated automatically; copy or migrate them deliberately before switching.

### Supabase deployment database

The hosted [MASGuardEval project](https://supabase.com/dashboard/project/ngwklaaqxqxttiswcnje) was created with the Supabase CLI. The schema is recorded in [`supabase/migrations/20261015085327_masguardeval_bootstrap.sql`](../supabase/migrations/20261015085327_masguardeval_bootstrap.sql); [`deploy/supabase/bootstrap.sql`](../deploy/supabase/bootstrap.sql) is the matching standalone SQL. It creates the private schema, enables pgvector in `extensions`, enables RLS on trace tables, and denies `anon` and `authenticated` direct access. Keep `masguardeval` out of the project's exposed Data API schemas. Use the database connection string from **Connect** in the Supabase dashboard, preferably the session pooler for this long-running Python API. Put it only in the backend host's `MASGUARDEVAL_DATABASE_URL`; the frontend must call the backend API, not connect to Postgres. The Render entry point has a shared preview gate; it is not per-user authentication or tenant isolation. Supabase alone does not host this FastAPI process. [Deployment status](DEPLOY_RENDER_SUPABASE.md) distinguishes verified SQL from the pending application connection trial.

Run a fictional service check after provisioning:

```powershell
$env:PYTHONPATH = "backend"
python scripts/verify_live_services.py --out reports/supabase-verification.json
```

This round-trips one JSONB trace and one 1536-dimensional vector, then removes its own test rows. The JSON report records verified, failed, or blocked for PostgreSQL, pgvector, and LangSmith without storing connection strings or keys. A missing credential is **blocked**, not a passing service test.

## pgvector scenario lookup

The optional `PgVectorScenarioIndex` stores externally computed embeddings for scenario lookup in the private `masguardeval` schema. It does not generate embeddings or affect guard verdicts. The extension must be installed and enabled by a database administrator first; on Supabase use the bootstrap SQL above, which installs it in `extensions`:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

```python
from masguardeval import PgVectorScenarioIndex

index = PgVectorScenarioIndex(dsn, dimensions=1536)
index.upsert("auth_001", embedding, embedding_model="my-pinned-embedding-model", scenario_text=scenario.prompt)
nearest = index.search(query_embedding, embedding_model="my-pinned-embedding-model", limit=5)
```

Vectors must have the configured dimension and finite values. The query filters by the named embedding model, so different vector spaces are not compared.

## LangSmith export

Export is explicit because traces can contain prompts, tool parameters, and outputs. Set `LANGSMITH_API_KEY`, then run:

```powershell
$env:LANGSMITH_API_KEY = "..."
$env:PYTHONPATH = "backend"
python scripts/export_langsmith.py --trace-id TRACE_ID --project masguardeval-study
```

If `MASGUARDEVAL_DATABASE_URL` is set, the command reads PostgreSQL; otherwise it reads `reports/runs.sqlite3` or the path passed with `--db`. It uploads the completed run as a LangSmith root with child runs for each recorded span, preserving original trace/span IDs and guard decisions as metadata. Review and redact data before exporting; the command sends it to the configured LangSmith account.

## Verification scope

The local tests cover guard-before-handler behavior, native wrapper construction, trace storage SQL contract, and LangSmith run-tree mapping. The service-check script records actual remote results separately; a local contract test is never described as a live integration pass.
