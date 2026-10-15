from __future__ import annotations

import re
import json
import os
import threading
import hmac
from pathlib import Path
from html import escape
from queue import Queue

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .evaluator import EvaluatorAgreement
from .dataset import GoldenDataset
from .experiments import ExperimentSuite
from .propagation import PropagationAnalyzer
from .runner import EvaluationEngine
from .scaling import BatchEvaluationExecutor
from .store import PostgresTraceStore, ScopedPostgresTraceStore, TraceStore
from .approvals import ApprovalBroker
from .graph import AgentToolGraphBuilder
from .findings import analyze_trace
from .models import Scenario, Trace
from .reference_langgraph import run_checkpoint_resume_probe, run_reference_langgraph


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = Path(os.environ.get("MASGUARDEVAL_DATASET_PATH", str(ROOT / "datasets" / "golden_scenarios.json")))
DOCS_PATH = ROOT / "docs"
DOC_FILES = {
    "README.md": "Docs Home",
    "RESEARCH_STATUS.md": "Research Status",
    "PAPER_STUDY_PROTOCOL.md": "Paper Study Protocol",
    "STUDY_AUTHORING_GUIDE.md": "Study Authoring Guide",
    "RELATED_WORK_AUDIT.md": "Related Work Audit",
    "QUICKSTART.md": "Quickstart",
    "SDK.md": "SDK",
    "INTEGRATIONS.md": "Integrations",
    "API.md": "API Guide",
    "EXAMPLES.md": "Examples",
    "EXPERIMENTS.md": "Experiments",
    "METRICS.md": "Metrics",
    "ARCHITECTURE.md": "Architecture",
    "docs.json": "Docs Site Config",
    "openapi.json": "OpenAPI Schema",
}

trace_store = (
    PostgresTraceStore(os.environ["MASGUARDEVAL_DATABASE_URL"])
    if os.environ.get("MASGUARDEVAL_DATABASE_URL")
    else TraceStore(os.environ.get("MASGUARDEVAL_TRACE_DB", str(ROOT / "reports" / "runs.sqlite3")))
)
engine = EvaluationEngine(GoldenDataset.load(DATASET_PATH), trace_store=trace_store)
preview_engine = EvaluationEngine(engine.dataset)
approval_broker = ApprovalBroker()


def request_store(request: Request):
    if os.environ.get("MASGUARDEVAL_REQUIRE_USER_AUTH") != "1":
        return trace_store
    owner_id = getattr(request.state, "owner_id", None)
    if not owner_id or not isinstance(trace_store, PostgresTraceStore):
        raise HTTPException(status_code=401, detail="Authenticated user scope is required")
    return ScopedPostgresTraceStore(trace_store, owner_id)


class AgreementRequest(BaseModel):
    labels_a: list[str] = Field(min_length=1)
    labels_b: list[str] = Field(min_length=1)


class ApprovalDecisionRequest(BaseModel):
    approve: bool
    reason: str = Field(min_length=1, max_length=500)


def require_approval_auth(authorization: str | None) -> None:
    token = os.environ.get("MASGUARDEVAL_APPROVAL_TOKEN")
    if not token:
        raise HTTPException(status_code=503, detail="Approval API requires MASGUARDEVAL_APPROVAL_TOKEN")
    if not authorization or not hmac.compare_digest(authorization, f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="Invalid approval authorization")

app = FastAPI(
    title="MASGuardEval API",
    version="0.1.0",
    description="Reference evaluation and observability framework. Built-in scenarios use scripted intents and an isolated mock workspace, not live LLM agents.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/scenarios")
def scenarios() -> dict[str, object]:
    return engine.dataset.to_dict()


@app.get("/evaluate/{scenario_id}")
def evaluate(scenario_id: str, request: Request) -> dict[str, object]:
    try:
        return EvaluationEngine(engine.dataset, trace_store=request_store(request)).evaluate(scenario_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/dashboard")
def dashboard() -> dict[str, object]:
    return preview_engine.generate_dashboard()


@app.get("/runs")
def saved_runs(request: Request, limit: int = 50) -> list[dict[str, object]]:
    try:
        return request_store(request).list(limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/langgraph/reference-run")
def langgraph_reference_run(request: Request) -> dict[str, object]:
    """Persist a bounded fictional graph trace to verify the native integration."""
    result = run_reference_langgraph(
        engine.dataset.get("auth_001"), request_store(request),
        database_url=os.environ.get("MASGUARDEVAL_DATABASE_URL"),
    )
    return {
        "trace_id": result.trace.trace_id,
        "checkpoint_id": result.checkpoint_id,
        "blocked": result.trace.blocked,
        "span_count": len(result.trace.spans),
        "reference_only": True,
    }


@app.post("/langgraph/checkpoint-probe")
def langgraph_checkpoint_probe(request: Request) -> dict[str, object]:
    """Exercise a fictional interrupt/resume across fresh checkpoint connections."""
    paused, resumed = run_checkpoint_resume_probe(
        engine.dataset.get("auth_001"), request_store(request),
        database_url=os.environ.get("MASGUARDEVAL_DATABASE_URL"),
    )
    return {
        "paused_trace_id": paused.trace.trace_id,
        "resumed_trace_id": resumed.trace.trace_id,
        "thread_id": next((span.metadata.get("thread_id") for span in resumed.trace.spans
                           if span.metadata.get("thread_id")), None),
        "checkpoint_id": resumed.checkpoint_id,
        "reference_only": True,
    }


@app.get("/runs/{trace_id}")
def saved_run(trace_id: str, request: Request) -> dict[str, object]:
    run = request_store(request).get(trace_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown trace ID")
    return run


@app.get("/runs/{trace_id}/graph")
def saved_run_graph(trace_id: str, request: Request) -> dict[str, object]:
    run = request_store(request).get(trace_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown trace ID")
    scenario = Scenario.from_dict(run["scenario"]) if run.get("scenario") else engine.dataset.get(run["scenario_id"])
    return AgentToolGraphBuilder().build(scenario, Trace.from_dict(run))


@app.get("/runs/{trace_id}/findings")
def saved_run_findings(trace_id: str, request: Request) -> dict[str, object]:
    run = request_store(request).get(trace_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown trace ID")
    scenario = Scenario.from_dict(run["scenario"]) if run.get("scenario") else engine.dataset.get(run["scenario_id"])
    return analyze_trace(scenario, Trace.from_dict(run))


@app.get("/stream/{scenario_id}")
def stream_scenario(scenario_id: str, request: Request, mode: str = "guarded") -> StreamingResponse:
    if mode not in {"baseline", "guarded"}:
        raise HTTPException(status_code=422, detail="mode must be baseline or guarded")
    try:
        scenario = engine.dataset.get(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    events: Queue[tuple[str, dict[str, object]]] = Queue()
    scoped_engine = EvaluationEngine(engine.dataset, trace_store=request_store(request))

    def run() -> None:
        try:
            listener = lambda span: events.put(("span", span.to_dict()))
            if mode == "guarded":
                owner_id = getattr(request.state, "owner_id", None)
                approval_handler = (lambda trace, event: approval_broker.request(trace, event, owner_id=owner_id)) \
                    if os.environ.get("MASGUARDEVAL_APPROVAL_TOKEN") else None
                trace = scoped_engine.run_guarded(scenario, on_span=listener, approval_handler=approval_handler)
            else:
                trace = scoped_engine.run_baseline(scenario, on_span=listener)
            events.put(("complete", {"trace": trace.to_dict(), "findings": analyze_trace(scenario, trace),
                                     "metrics": {key: value.to_dict() for key, value in scoped_engine.compute_metrics(scenario, trace).items()}}))
        except Exception as exc:
            events.put(("error", {"detail": str(exc)}))

    threading.Thread(target=run, daemon=True).start()

    def emit():
        while True:
            kind, payload = events.get()
            yield f"event: {kind}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            if kind in {"complete", "error"}:
                break

    return StreamingResponse(emit(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/approvals")
def pending_approvals(request: Request, authorization: str | None = Header(default=None)) -> list[dict[str, object]]:
    require_approval_auth(authorization)
    request_store(request)
    return approval_broker.list(status="pending", owner_id=getattr(request.state, "owner_id", None))


@app.post("/approvals/{request_id}")
def decide_approval(
    request_id: str, payload: ApprovalDecisionRequest, request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    require_approval_auth(authorization)
    request_store(request)
    try:
        return approval_broker.decide(request_id, payload.approve, payload.reason,
                                      owner_id=getattr(request.state, "owner_id", None))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown approval request") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/experiments")
def experiments() -> dict[str, object]:
    return ExperimentSuite(preview_engine).run().to_dict()


@app.get("/propagation/{scenario_id}")
def propagation(scenario_id: str) -> dict[str, object]:
    try:
        result = preview_engine.evaluate(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PropagationAnalyzer().analyze(result.baseline_trace).to_dict()


@app.get("/graph/{scenario_id}")
def agent_tool_graph(scenario_id: str, mode: str = "guarded") -> dict[str, object]:
    if mode not in {"baseline", "guarded"}:
        raise HTTPException(status_code=422, detail="mode must be baseline or guarded")
    try:
        result = preview_engine.evaluate(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.baseline_graph if mode == "baseline" else result.guarded_graph


@app.get("/scalability/batch")
def scalability_batch(max_workers: int = 4, chunk_size: int = 10) -> dict[str, object]:
    try:
        return BatchEvaluationExecutor(preview_engine, max_workers=max_workers, chunk_size=chunk_size).run().to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/evaluator/agreement")
def evaluator_agreement(payload: AgreementRequest) -> dict[str, object]:
    try:
        return EvaluatorAgreement.cohens_kappa(payload.labels_a, payload.labels_b).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/project-docs", response_class=HTMLResponse)
def project_docs_home() -> HTMLResponse:
    return project_doc("README.md")


@app.get("/project-docs/{doc_name}", response_class=HTMLResponse)
def project_doc(doc_name: str) -> Response:
    if doc_name not in DOC_FILES:
        raise HTTPException(status_code=404, detail=f"Unknown docs page: {doc_name}")

    path = DOCS_PATH / doc_name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Docs page not found: {doc_name}")

    content = path.read_text(encoding="utf-8")
    if doc_name.endswith(".json"):
        return PlainTextResponse(content, media_type="application/json")

    nav = "".join(
        f'<a class="{ "active" if name == doc_name else "" }" href="/project-docs/{name}">{escape(label)}</a>'
        for name, label in DOC_FILES.items()
    )
    body = _render_markdown(content)
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(DOC_FILES[doc_name])} - MASGuardEval Docs</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #0f172a; background: #f8fafc; }}
    body {{ margin: 0; }}
    .layout {{ display: grid; grid-template-columns: 270px minmax(0, 1fr); min-height: 100vh; }}
    aside {{ border-right: 1px solid #d9e2ea; background: #fff; padding: 24px 18px; position: sticky; top: 0; height: 100vh; }}
    .brand {{ color: #087f7a; font-size: 22px; font-weight: 800; margin-bottom: 28px; }}
    nav {{ display: grid; gap: 6px; }}
    nav a {{ color: #334155; text-decoration: none; border-radius: 7px; padding: 10px 12px; font-weight: 650; }}
    nav a.active, nav a:hover {{ color: #006b68; background: #e6f6f4; }}
    main {{ max-width: 1040px; padding: 34px 46px 80px; }}
    h1 {{ font-size: 34px; line-height: 1.15; margin: 0 0 20px; }}
    h2 {{ font-size: 24px; margin: 34px 0 12px; border-top: 1px solid #e5edf3; padding-top: 24px; }}
    h3 {{ font-size: 18px; margin: 24px 0 10px; }}
    p, li {{ font-size: 15px; line-height: 1.65; }}
    a {{ color: #087f7a; }}
    table {{ width: 100%; border-collapse: collapse; margin: 14px 0 22px; background: #fff; border: 1px solid #d9e2ea; }}
    th, td {{ border-bottom: 1px solid #edf2f6; padding: 10px 12px; text-align: left; vertical-align: top; font-size: 14px; }}
    th {{ background: #f8fafc; color: #334155; }}
    code {{ background: #eef6f6; color: #075e59; border-radius: 4px; padding: 2px 5px; }}
    pre {{ background: #0f172a; color: #e2e8f0; border-radius: 8px; padding: 16px; overflow-x: auto; }}
    pre code {{ background: transparent; color: inherit; padding: 0; }}
    .mermaid {{ background: #fff; border: 1px solid #d9e2ea; border-radius: 8px; padding: 18px; margin: 16px 0 24px; overflow-x: auto; }}
    blockquote {{ border-left: 4px solid #087f7a; margin-left: 0; padding-left: 14px; color: #475569; }}
    @media (max-width: 860px) {{ .layout {{ grid-template-columns: 1fr; }} aside {{ position: static; height: auto; }} main {{ padding: 24px 18px 60px; }} }}
  </style>
</head>
<body>
  <div class="layout">
    <aside>
      <div class="brand">MASGuardEval</div>
      <nav>{nav}</nav>
    </aside>
    <main>{body}</main>
  </div>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{ startOnLoad: true, theme: "base", securityLevel: "loose", themeVariables: {{ primaryColor: "#e6f6f4", primaryTextColor: "#0f172a", primaryBorderColor: "#087f7a", lineColor: "#64748b", secondaryColor: "#eef6f6", tertiaryColor: "#ffffff" }} }});
  </script>
</body>
</html>"""
    )


def _render_markdown(markdown: str) -> str:
    html: list[str] = []
    in_code = False
    code_lang = ""
    in_ul = False
    in_table = False

    def close_lists() -> None:
        nonlocal in_ul, in_table
        if in_ul:
            html.append("</ul>")
            in_ul = False
        if in_table:
            html.append("</tbody></table>")
            in_table = False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                html.append("</div>" if code_lang == "mermaid" else "</code></pre>")
                in_code = False
                code_lang = ""
            else:
                close_lists()
                in_code = True
                code_lang = stripped[3:].strip().lower()
                html.append('<div class="mermaid">' if code_lang == "mermaid" else "<pre><code>")
            continue

        if in_code:
            html.append(escape(line) + "\n")
            continue

        if not stripped:
            close_lists()
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            raw_cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if all(set(cell) <= {"-", ":", " "} for cell in raw_cells):
                continue
            cells = [_inline_markdown(cell) for cell in raw_cells]
            if not in_table:
                close_lists()
                html.append("<table><tbody>")
                in_table = True
            tag = "th" if not any(part.startswith("<tr>") for part in html[-1:]) else "td"
            html.append("<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in cells) + "</tr>")
            continue

        close_lists()

        if stripped.startswith("# "):
            html.append(f"<h1>{_inline_markdown(stripped[2:])}</h1>")
        elif stripped.startswith("## "):
            html.append(f"<h2>{_inline_markdown(stripped[3:])}</h2>")
        elif stripped.startswith("### "):
            html.append(f"<h3>{_inline_markdown(stripped[4:])}</h3>")
        elif stripped.startswith("- "):
            if not in_ul:
                html.append("<ul>")
                in_ul = True
            html.append(f"<li>{_inline_markdown(stripped[2:])}</li>")
        else:
            html.append(f"<p>{_inline_markdown(stripped)}</p>")

    close_lists()
    if in_code:
        html.append("</div>" if code_lang == "mermaid" else "</code></pre>")
    return "\n".join(html)


def _inline_markdown(text: str) -> str:
    escaped = escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)

    def link(match: re.Match[str]) -> str:
        label = match.group(1)
        href = match.group(2)
        target = f"/project-docs/{href}" if href in DOC_FILES else href
        return f'<a href="{escape(target, quote=True)}">{label}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, escaped)
