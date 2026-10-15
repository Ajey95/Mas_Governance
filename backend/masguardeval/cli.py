"""Installed command line interface over the public MASGuardEval SDK."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .dataset import GoldenDataset
from .experiments import ExperimentSuite
from .langsmith_export import LangSmithExporter
from .models import Scenario, Trace
from .runner import EvaluationEngine
from .store import PostgresTraceStore, TraceStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="masguardeval",
        description="Evaluate fictional agent scenarios and inspect saved traces.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="Validate a scenario dataset without running agents.")
    validate.add_argument("--dataset", type=Path, required=True)

    evaluate = commands.add_parser("evaluate", help="Run the scripted reference adapter.")
    evaluate.add_argument("--dataset", type=Path, required=True)
    evaluate.add_argument("--scenario", help="Scenario ID; omit to evaluate the entire dataset.")
    evaluate.add_argument("--out", type=Path, help="Write JSON to a file instead of stdout.")

    report = commands.add_parser("report", help="Run reference experiments and guard ablations.")
    report.add_argument("--dataset", type=Path, required=True)
    report.add_argument("--json-out", type=Path)
    report.add_argument("--md-out", type=Path)

    export = commands.add_parser("export", help="Explicitly send one saved trace to LangSmith.")
    export.add_argument("--trace-id", required=True)
    export.add_argument("--project", required=True)
    export.add_argument("--sqlite", type=Path, help="SQLite trace file; omit when MASGUARDEVAL_DATABASE_URL is set.")
    return parser


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _json(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _export(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if not os.environ.get("LANGSMITH_API_KEY"):
        parser.error("LANGSMITH_API_KEY is required for export")
    dsn = os.environ.get("MASGUARDEVAL_DATABASE_URL")
    if bool(dsn) == bool(args.sqlite):
        parser.error("Supply --sqlite or MASGUARDEVAL_DATABASE_URL, exactly one")
    if args.sqlite is not None and not args.sqlite.is_file():
        parser.error("SQLite trace file does not exist")
    store = PostgresTraceStore(dsn) if dsn else TraceStore(args.sqlite)
    record = store.get(args.trace_id)
    if record is None:
        parser.error("Unknown trace ID")
    if not record.get("scenario"):
        parser.error("Stored run has no scenario snapshot")
    run_id = LangSmithExporter(args.project).export(
        Scenario.from_dict(record["scenario"]), Trace.from_dict(record)
    )
    print(_json({"trace_id": args.trace_id, "langsmith_run_id": run_id}), end="")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            _export(args, parser)
            return 0
        dataset = GoldenDataset.load(args.dataset)
        if args.command == "validate":
            print(_json({"valid": True, "scenario_count": len(dataset.scenarios)}), end="")
            return 0
        engine = EvaluationEngine(dataset)
        if args.command == "evaluate":
            if args.scenario:
                payload: object = engine.evaluate(args.scenario).to_dict()
            else:
                payload = engine.generate_dashboard()
            rendered = _json(payload)
            if args.out:
                _write(args.out, rendered)
                print(f"Wrote evaluation JSON to {args.out}", file=sys.stderr)
            else:
                print(rendered, end="")
            return 0
        if not args.json_out and not args.md_out:
            parser.error("report requires --json-out or --md-out")
        report = ExperimentSuite(engine).run()
        if args.json_out:
            _write(args.json_out, _json(report.to_dict()))
        if args.md_out:
            _write(args.md_out, report.to_markdown())
        print(f"Evaluated {report.scenario_count} reference scenarios", file=sys.stderr)
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
