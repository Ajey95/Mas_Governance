"""Run small fictional service checks without printing secrets or private trace data."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from masguardeval.dataset import GoldenDataset
from masguardeval.langsmith_export import LangSmithExporter
from masguardeval.models import Span, Trace
from masguardeval.store import PostgresTraceStore
from masguardeval.vector_index import PgVectorScenarioIndex


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(ROOT / "reports" / "live_service_verification.json"))
    parser.add_argument("--langsmith-project", default="masguardeval-smoke")
    args = parser.parse_args()
    output = Path(args.out)
    if output.exists():
        parser.error("Choose a new output file; prior service evidence is immutable")
    scenario = GoldenDataset.load(ROOT / "datasets" / "golden_scenarios.json").scenarios[0]
    trace = Trace.start(scenario.scenario_id, "guarded")
    trace.add_span(Span.create(trace.trace_id, "agent_step", "SmokeVerifier", scenario.user_role,
                               output="Fictional verification event"))
    trace.final_response = "Fictional service check completed"
    trace.finish()
    report = {"checked_at": datetime.now(timezone.utc).isoformat(),
              "scope": "fictional single-run service smoke, not a study result", "services": {}}

    dsn = os.environ.get("MASGUARDEVAL_DATABASE_URL")
    if not dsn:
        report["services"]["postgres"] = {"status": "blocked_missing_database_url"}
        report["services"]["pgvector"] = {"status": "blocked_missing_database_url"}
    else:
        try:
            store = PostgresTraceStore(dsn)
            store.begin(trace, "service_smoke", scenario)
            store.append(trace.spans[0])
            store.finish(trace)
            saved = store.get(trace.trace_id)
            if not saved or len(saved["spans"]) != 1 or saved["scenario_id"] != scenario.scenario_id:
                raise RuntimeError("PostgreSQL trace round trip differed")
            report["services"]["postgres"] = {"status": "verified", "trace_id": trace.trace_id,
                                                  "schema": store.schema}
        except Exception as exc:
            report["services"]["postgres"] = {"status": "failed", "error_type": type(exc).__name__}
        vector_id = "smoke-" + uuid4().hex
        try:
            index = PgVectorScenarioIndex(dsn, dimensions=1536)
            embedding = [1.0] + [0.0] * 1535
            index.upsert(vector_id, embedding, embedding_model="fictional-smoke-v1",
                         scenario_text="Fictional vector service check")
            nearest = index.search(embedding, embedding_model="fictional-smoke-v1", limit=1)
            if not nearest or nearest[0]["scenario_id"] != vector_id:
                raise RuntimeError("pgvector nearest-neighbor round trip differed")
            report["services"]["pgvector"] = {"status": "verified", "dimensions": 1536,
                                                  "extension_schema": index.extension_schema}
        except Exception as exc:
            report["services"]["pgvector"] = {"status": "failed", "error_type": type(exc).__name__}
        try:
            import psycopg
            with psycopg.connect(dsn) as connection:
                vector_table = connection.execute(
                    "select to_regclass('masguardeval.masguardeval_scenario_vectors')"
                ).fetchone()[0]
                if vector_table:
                    connection.execute("delete from masguardeval.masguardeval_scenario_vectors where scenario_id=%s", (vector_id,))
                connection.execute("delete from masguardeval.masguardeval_spans where trace_id=%s", (trace.trace_id,))
                connection.execute("delete from masguardeval.masguardeval_runs where trace_id=%s", (trace.trace_id,))
            report["test_rows_removed"] = True
        except Exception as exc:
            report["test_rows_removed"] = False
            report["cleanup_error_type"] = type(exc).__name__

    if not os.environ.get("LANGSMITH_API_KEY"):
        report["services"]["langsmith"] = {"status": "blocked_missing_api_key"}
    else:
        try:
            run_id = LangSmithExporter(args.langsmith_project).export(scenario, trace)
            report["services"]["langsmith"] = {"status": "verified", "run_id": run_id}
        except Exception as exc:
            report["services"]["langsmith"] = {"status": "failed", "error_type": type(exc).__name__}

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: value["status"] for name, value in report["services"].items()}))


if __name__ == "__main__":
    main()
