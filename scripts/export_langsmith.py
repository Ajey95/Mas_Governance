"""Upload one completed, stored trace to LangSmith on explicit invocation."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from masguardeval.langsmith_export import LangSmithExporter
from masguardeval.models import Scenario, Trace
from masguardeval.store import PostgresTraceStore, TraceStore


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Export one stored MASGuardEval trace to LangSmith.")
    parser.add_argument("--trace-id", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--db", default=str(ROOT / "reports" / "runs.sqlite3"))
    args = parser.parse_args()
    if not os.environ.get("LANGSMITH_API_KEY"):
        parser.error("LANGSMITH_API_KEY must be set")
    store = PostgresTraceStore(os.environ["MASGUARDEVAL_DATABASE_URL"]) if os.environ.get("MASGUARDEVAL_DATABASE_URL") else TraceStore(args.db)
    record = store.get(args.trace_id)
    if record is None:
        parser.error("Unknown trace ID")
    if record["scenario"] is None:
        parser.error("Stored run has no scenario snapshot")
    run_id = LangSmithExporter(args.project).export(Scenario.from_dict(record["scenario"]), Trace.from_dict(record))
    print(f"Exported trace {args.trace_id} to LangSmith run {run_id}")


if __name__ == "__main__":
    main()
