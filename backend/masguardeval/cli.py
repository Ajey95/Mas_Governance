"""Installed command line interface over the public MASGuardEval SDK."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Callable, Sequence

from . import __version__
from .dataset import GoldenDataset
from .diagnosis_study import (analyze_diagnoses, assign_diagnosis_panels, capture_diagnosis,
                              read_jsonl, reference_template, validate_packet)
from .experiments import ExperimentSuite
from .findings import analyze_trace
from .graph import AgentToolGraphBuilder
from .langsmith_export import LangSmithExporter
from .metrics import recommendations_for
from .models import Scenario, Trace
from .outcome_review import make_outcome_packet
from .runner import EvaluationEngine
from .store import PostgresTraceStore, TraceStore
from .trace_report import build_trace_report, trace_report_markdown


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

    trace_report = commands.add_parser("trace-report", help="Recompute a detailed provenance, evaluation, and observability report for one trace.")
    source = trace_report.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="JSON emitted by run-agent, or a saved run JSON with a scenario snapshot.")
    source.add_argument("--trace-id", help="Saved trace ID from SQLite or MASGUARDEVAL_DATABASE_URL.")
    trace_report.add_argument("--sqlite", type=Path, help="SQLite store when using --trace-id.")
    trace_report.add_argument("--mode", choices=("baseline", "guarded"), help="Select a trace from compare-agent JSON input.")
    trace_report.add_argument("--json-out", type=Path, help="Write the full evidence bundle as JSON.")
    trace_report.add_argument("--md-out", type=Path, help="Write a readable Markdown report.")

    diagnosis_packet = commands.add_parser("diagnosis-packet", help="Prepare condition-masked diagnosis trials and a private trace map.")
    diagnosis_packet.add_argument("--report", type=Path, required=True, help="Paired experiment JSON with baseline and guarded traces.")
    diagnosis_packet.add_argument("--review-out", type=Path, required=True, help="New directory for blinded_trials.jsonl.")
    diagnosis_packet.add_argument("--private-map-out", type=Path, required=True, help="Private map JSON outside the reviewer directory.")
    diagnosis_packet.add_argument("--seed", type=int, default=23)
    diagnosis_packet.add_argument("--trial", type=int, help="Select one repeated trial per scenario for the four-panel timing study.")
    diagnosis_packet.add_argument("--architecture", help="Select one architecture for a four-panel timing study.")

    diagnosis_assign = commands.add_parser("diagnosis-assign", help="Create four blinded reviewer panels without paired-condition carryover.")
    diagnosis_assign.add_argument("--packet", type=Path, required=True)
    diagnosis_assign.add_argument("--private-map", type=Path, required=True)
    diagnosis_assign.add_argument("--out-dir", type=Path, required=True)
    diagnosis_assign.add_argument("--private-manifest-out", type=Path, required=True)
    diagnosis_assign.add_argument("--seed", type=int, default=23)

    diagnosis_review = commands.add_parser("diagnosis-review", help="Time one analyst's blinded span diagnosis for each trial.")
    diagnosis_review.add_argument("--packet", type=Path, required=True, help="Condition-masked blinded_trials.jsonl.")
    diagnosis_review.add_argument("--reviewer-id", required=True)
    diagnosis_review.add_argument("--reviewer-role", required=True)
    diagnosis_review.add_argument("--out", type=Path, required=True, help="New append-only JSONL review file.")
    diagnosis_review.add_argument("--resume", action="store_true", help="Continue only missing trials from an existing hash-matched review file.")

    diagnosis_reference = commands.add_parser("diagnosis-reference-template", help="Make a blank independent diagnosis reference template.")
    diagnosis_reference.add_argument("--packet", type=Path, required=True)
    diagnosis_reference.add_argument("--out", type=Path, required=True)

    diagnosis_analysis = commands.add_parser("diagnosis-analyze", help="Validate two timed reviews per trial against independent reference spans.")
    diagnosis_analysis.add_argument("--packet", type=Path, required=True)
    diagnosis_analysis.add_argument("--private-map", type=Path, required=True)
    diagnosis_analysis.add_argument("--reviews", type=Path, nargs="+", required=True)
    diagnosis_analysis.add_argument("--reference", type=Path, required=True)
    diagnosis_analysis.add_argument("--out", type=Path, required=True)

    run_agent = commands.add_parser("run-agent", help="Run a caller-provided agent adapter through the guarded SDK.")
    run_agent.add_argument("--dataset", type=Path, required=True)
    run_agent.add_argument("--scenario", required=True, help="Scenario ID to run.")
    run_agent.add_argument("--factory", required=True, help="Trusted Python file or module and callable: path.py:create_engine")
    run_agent.add_argument("--out", type=Path, help="Write trace, metrics, and graph JSON instead of stdout.")
    run_agent.add_argument("--sqlite", type=Path, help="Also save the trace to a local SQLite database.")

    compare_agent = commands.add_parser("compare-agent", help="Run a caller agent in isolated baseline and guarded modes.")
    compare_agent.add_argument("--dataset", type=Path, required=True)
    compare_agent.add_argument("--scenario", required=True, help="Scenario ID to compare.")
    compare_agent.add_argument("--factory", required=True, help="Trusted Python file or module and callable: path.py:create_engine")
    compare_agent.add_argument("--allow-unguarded", action="store_true", help="Confirm that all handlers are isolated test tools; baseline skips guards.")
    compare_agent.add_argument("--out", type=Path, help="Write both traces, metrics, graphs and findings as JSON.")
    compare_agent.add_argument("--sqlite", type=Path, help="Also save both traces to a local SQLite database.")

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


def _trace_report(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if not args.json_out and not args.md_out:
        parser.error("trace-report requires --json-out or --md-out")
    destinations = [path.resolve() for path in (args.json_out, args.md_out) if path]
    if len(destinations) != len(set(destinations)):
        parser.error("--json-out and --md-out must be different files")
    if (args.input and args.input.resolve() in destinations) or (args.sqlite and args.sqlite.resolve() in destinations):
        parser.error("Report output cannot overwrite the input run or SQLite store")
    if args.input:
        if args.sqlite:
            parser.error("--sqlite requires --trace-id")
        source_bytes = args.input.read_bytes()
        import hashlib
        record = json.loads(source_bytes)
        source = "file"
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    else:
        dsn = os.environ.get("MASGUARDEVAL_DATABASE_URL")
        if bool(dsn) == bool(args.sqlite):
            parser.error("Supply --sqlite or MASGUARDEVAL_DATABASE_URL, exactly one")
        if args.sqlite is not None and not args.sqlite.is_file():
            parser.error("SQLite trace file does not exist")
        store = PostgresTraceStore(dsn) if dsn else TraceStore(args.sqlite)
        record = store.get(args.trace_id)
        if record is None:
            parser.error("Unknown trace ID")
        source = "postgres" if dsn else "sqlite"
        source_sha256 = None
    if not isinstance(record, dict) or not isinstance(record.get("scenario"), dict):
        parser.error("Input run has no scenario snapshot")
    is_pair = "baseline_trace" in record or "guarded_trace" in record
    if is_pair and not args.mode:
        parser.error("Paired input requires --mode baseline or --mode guarded")
    if args.mode and not is_pair:
        parser.error("--mode requires compare-agent JSON input")
    trace_payload = record.get(f"{args.mode}_trace") if is_pair else record.get("trace", record)
    if not isinstance(trace_payload, dict):
        parser.error("Input run has no trace object")
    report = build_trace_report(
        Scenario.from_dict(record["scenario"]), Trace.from_dict(trace_payload),
        adapter=str(record.get("adapter", "unknown")),
        execution_kind=str(record.get("execution_kind", "unknown")),
        source=source, source_sha256=source_sha256,
    )
    if args.json_out:
        _write(args.json_out, _json(report))
    if args.md_out:
        _write(args.md_out, trace_report_markdown(report))
    print(f"Reported trace {report['provenance']['trace_id']}", file=sys.stderr)


def _diagnosis_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.command == "diagnosis-packet":
        if args.review_out.exists() or args.private_map_out.exists():
            parser.error("Review directory and private map targets must not exist")
        if args.private_map_out.parent.resolve() == args.review_out.resolve():
            parser.error("Keep the private map outside the reviewer directory")
        report = json.loads(args.report.read_text(encoding="utf-8"))
        if report.get("status") not in (None, "complete", "complete_with_protocol_errors"):
            parser.error("Diagnosis packet requires a complete experiment report")
        if args.trial is not None:
            if args.trial < 1:
                parser.error("--trial must be positive")
            report = {**report, "results": [row for row in report.get("results", []) if row.get("trial") == args.trial]}
            if not report["results"]:
                parser.error("No results found for --trial")
        if args.architecture:
            report = {**report, "results": [row for row in report.get("results", []) if row.get("architecture") == args.architecture]}
            if not report["results"]:
                parser.error("No results found for --architecture")
        packet, mapping = make_outcome_packet(report, seed=args.seed)
        validate_packet(packet)
        args.review_out.mkdir(parents=True)
        _write(args.review_out / "blinded_trials.jsonl", "".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in packet))
        _write(args.private_map_out, _json(mapping))
        print(f"Prepared {len(packet)} blinded diagnosis trials", file=sys.stderr)
        return
    if args.command == "diagnosis-assign":
        if args.out_dir.exists() or args.private_manifest_out.exists():
            parser.error("Panel directory and private assignment manifest must not exist")
        if args.private_manifest_out.parent.resolve() == args.out_dir.resolve():
            parser.error("Keep the mode-bearing assignment manifest outside reviewer panels")
        packet = read_jsonl(args.packet)
        mapping = json.loads(args.private_map.read_text(encoding="utf-8"))
        panels, manifest = assign_diagnosis_panels(packet, mapping, seed=args.seed)
        args.out_dir.mkdir(parents=True)
        for name, rows in panels.items():
            _write(args.out_dir / f"{name}.jsonl", "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
        _write(args.private_manifest_out, _json(manifest))
        print("Prepared four blinded diagnosis panels", file=sys.stderr)
        return
    packet = read_jsonl(args.packet)
    packet_by_id = validate_packet(packet)
    if args.out.resolve() == args.packet.resolve():
        parser.error("Diagnosis output cannot overwrite the packet")
    if args.command == "diagnosis-reference-template":
        if args.out.exists():
            parser.error(f"Output already exists: {args.out}")
        rows = reference_template(packet)
        _write(args.out, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
        print(f"Prepared {len(rows)} blank diagnosis reference rows", file=sys.stderr)
        return
    if args.command == "diagnosis-review":
        if not args.reviewer_id.strip() or not args.reviewer_role.strip():
            parser.error("Reviewer ID and role are required")
        if args.out.exists() and not args.resume:
            parser.error(f"Output already exists: {args.out}; use --resume to continue")
        completed: set[str] = set()
        if args.out.exists():
            from .study import canonical_hash
            for prior in read_jsonl(args.out):
                blind_id = prior.get("blind_id")
                if (blind_id not in packet_by_id or blind_id in completed
                        or prior.get("packet_sha256") != canonical_hash(packet_by_id[blind_id])
                        or prior.get("reviewer_id") != args.reviewer_id.strip()):
                    parser.error("Existing diagnosis review does not match this packet and reviewer")
                completed.add(blind_id)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        # Each completed trial is flushed immediately, preserving partial work
        # if a human review session is interrupted.
        with args.out.open("a" if args.resume else "x", encoding="utf-8") as output:
            for row in packet:
                if row["blind_id"] in completed:
                    continue
                record = capture_diagnosis(row, args.reviewer_id, args.reviewer_role)
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                output.flush()
        print(f"Recorded {len(packet) - len(completed)} timed diagnoses in {args.out}", file=sys.stderr)
        return
    if args.out.exists():
        parser.error(f"Output already exists: {args.out}")
    paths = [args.private_map, args.reference, *args.reviews]
    if args.out.resolve() in {path.resolve() for path in paths}:
        parser.error("Diagnosis output cannot overwrite an input")
    mapping = json.loads(args.private_map.read_text(encoding="utf-8"))
    reviews = [row for path in args.reviews for row in read_jsonl(path)]
    references = read_jsonl(args.reference)
    result = analyze_diagnoses(packet, mapping, reviews, references)
    _write(args.out, _json(result))
    print(f"Analyzed {len(result['rows'])} timed diagnoses", file=sys.stderr)


def _agent_factory(spec: str, parser: argparse.ArgumentParser) -> Callable[[GoldenDataset], EvaluationEngine]:
    source, separator, name = spec.rpartition(":")
    if not separator or not source or not name.isidentifier():
        parser.error("--factory must be path.py:callable or module:callable")
    if source.endswith(".py"):
        path = Path(source).resolve()
        if not path.is_file():
            parser.error(f"Factory file does not exist: {path}")
        module_spec = importlib.util.spec_from_file_location("_masguardeval_user_agent", path)
        if module_spec is None or module_spec.loader is None:
            parser.error(f"Cannot load factory file: {path}")
        module = importlib.util.module_from_spec(module_spec)
        # Local sibling imports are useful for a caller-owned integration file.
        sys.path.insert(0, str(path.parent))
        try:
            module_spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
    else:
        module = importlib.import_module(source)
    factory = getattr(module, name, None)
    if not callable(factory):
        parser.error(f"Factory callable not found: {spec}")
    return factory


def _agent_engine(spec: str, dataset: GoldenDataset, parser: argparse.ArgumentParser) -> EvaluationEngine:
    factory = _agent_factory(spec, parser)
    engine = factory(dataset)
    if not isinstance(engine, EvaluationEngine):
        parser.error("Factory must return an EvaluationEngine")
    if engine.dataset is not dataset:
        parser.error("Factory must use the supplied dataset")
    return engine


def _check_agent_paths(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    source = args.factory.rpartition(":")[0]
    inputs = {args.dataset.resolve()}
    if source.endswith(".py"):
        inputs.add(Path(source).resolve())
    if args.out:
        output = args.out.resolve()
        if output in inputs or (args.sqlite and output == args.sqlite.resolve()):
            parser.error("Agent output cannot overwrite the dataset, factory, or SQLite store")
    if args.sqlite and args.sqlite.resolve() in inputs:
        parser.error("SQLite store cannot overwrite the dataset or factory")


def _run_agent(args: argparse.Namespace, dataset: GoldenDataset, parser: argparse.ArgumentParser) -> None:
    _check_agent_paths(args, parser)
    scenario = dataset.get(args.scenario)
    engine = _agent_engine(args.factory, dataset, parser)
    if args.sqlite:
        if engine.trace_store is not None:
            parser.error("Factory already configured a trace store; omit --sqlite")
        engine.trace_store = TraceStore(args.sqlite)
    trace = engine.run_guarded(scenario)
    metrics = engine.compute_metrics(scenario, trace)
    payload = {
        "scenario": scenario.to_dict(),
        "adapter": engine.adapter.name,
        "execution_kind": getattr(engine.adapter, "execution_kind", "custom_adapter"),
        "trace": trace.to_dict(),
        "metrics": {key: value.to_dict() for key, value in metrics.items()},
        "graph": AgentToolGraphBuilder().build(scenario, trace),
        "recommendations": recommendations_for(metrics),
    }
    rendered = _json(payload)
    if args.out:
        _write(args.out, rendered)
        print(f"Wrote guarded agent run JSON to {args.out}", file=sys.stderr)
    else:
        print(rendered, end="")


def _compare_agent(args: argparse.Namespace, dataset: GoldenDataset, parser: argparse.ArgumentParser) -> None:
    if not args.allow_unguarded:
        parser.error("compare-agent requires --allow-unguarded after confirming every tool handler is isolated")
    _check_agent_paths(args, parser)
    scenario = dataset.get(args.scenario)
    factory = _agent_factory(args.factory, parser)
    baseline_engine = factory(dataset)
    guarded_engine = factory(dataset)
    for engine in (baseline_engine, guarded_engine):
        if not isinstance(engine, EvaluationEngine) or engine.dataset is not dataset:
            parser.error("Factory must return an EvaluationEngine using the supplied dataset")
        if engine.trace_store is not None:
            parser.error("compare-agent factory must not configure a trace store; use --sqlite")
    if baseline_engine is guarded_engine or baseline_engine.adapter is guarded_engine.adapter:
        parser.error("Factory must create a fresh adapter and EvaluationEngine for each condition")
    if (baseline_engine.adapter.name != guarded_engine.adapter.name
            or baseline_engine.max_events != guarded_engine.max_events
            or set(baseline_engine.tool_handlers) != set(guarded_engine.tool_handlers)
            or [guard.name for guard in baseline_engine.guards] != [guard.name for guard in guarded_engine.guards]):
        parser.error("Factory returned different agent, tool, or guard configurations across conditions")
    if args.sqlite:
        store = TraceStore(args.sqlite)
        baseline_engine.trace_store = store
        guarded_engine.trace_store = store
    baseline = baseline_engine.run_baseline(scenario)
    guarded = guarded_engine.run_guarded(scenario)
    baseline_metrics = baseline_engine.compute_metrics(scenario, baseline)
    guarded_metrics = guarded_engine.compute_metrics(scenario, guarded)
    metric_change: dict[str, float] = {}
    for key, before in baseline_metrics.items():
        after = guarded_metrics.get(key)
        if after and before.applicable and after.applicable:
            raw = before.score - after.score if key in {"PHR", "CPI", "CFP", "CCR", "DT"} else after.score - before.score
            metric_change[key] = round(raw, 4)
    payload = {
        "scenario": scenario.to_dict(),
        "adapter": baseline_engine.adapter.name,
        "execution_kind": getattr(baseline_engine.adapter, "execution_kind", "custom_adapter"),
        "comparison_scope": "isolated caller-provided tool handlers",
        "baseline_trace": baseline.to_dict(),
        "guarded_trace": guarded.to_dict(),
        "baseline_metrics": {key: item.to_dict() for key, item in baseline_metrics.items()},
        "guarded_metrics": {key: item.to_dict() for key, item in guarded_metrics.items()},
        "metric_change": metric_change,
        "metric_change_scope": "descriptive trace comparison, not measured risk reduction",
        "baseline_graph": AgentToolGraphBuilder().build(scenario, baseline),
        "guarded_graph": AgentToolGraphBuilder().build(scenario, guarded),
        "baseline_findings": analyze_trace(scenario, baseline),
        "guarded_findings": analyze_trace(scenario, guarded),
        "recommendations": recommendations_for(baseline_metrics),
    }
    rendered = _json(payload)
    if args.out:
        _write(args.out, rendered)
        print(f"Wrote paired agent comparison JSON to {args.out}", file=sys.stderr)
    else:
        print(rendered, end="")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            _export(args, parser)
            return 0
        if args.command == "trace-report":
            _trace_report(args, parser)
            return 0
        if args.command in {"diagnosis-packet", "diagnosis-assign", "diagnosis-review", "diagnosis-reference-template", "diagnosis-analyze"}:
            _diagnosis_command(args, parser)
            return 0
        dataset = GoldenDataset.load(args.dataset)
        if args.command == "run-agent":
            _run_agent(args, dataset, parser)
            return 0
        if args.command == "compare-agent":
            _compare_agent(args, dataset, parser)
            return 0
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
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, sqlite3.DatabaseError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
