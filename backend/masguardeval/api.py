from __future__ import annotations

import json
import os
import threading
import hmac
from pathlib import Path
from queue import Queue

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
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
from .reference_langgraph import run_checkpoint_resume_probe, run_nested_react_probe, run_reference_langgraph


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = Path(os.environ.get("MASGUARDEVAL_DATASET_PATH", str(ROOT / "datasets" / "golden_scenarios.json")))
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
    version="0.2.1",
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


@app.post("/langgraph/nested-probe")
def langgraph_nested_probe(request: Request, blocked_branch: bool = False) -> dict[str, object]:
    """Persist a fictional two-subgraph, two-round guarded ReAct topology probe."""
    result = run_nested_react_probe(engine.dataset.get("auth_001"), request_store(request),
                                    blocked_branch=blocked_branch)
    return {
        "trace_id": result.trace.trace_id,
        "blocked": result.trace.blocked,
        "span_count": len(result.trace.spans),
        "tool_calls": sum(span.span_type == "tool_call" for span in result.trace.spans),
        "checkpoint_id": result.checkpoint_id,
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
