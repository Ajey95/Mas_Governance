from __future__ import annotations

import argparse
import json
import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from masguardeval import (
    EvaluationEngine, GoldenDataset, LiveWorkspaceAdapter, OllamaChatClient, OpenAIResponsesClient,
    SingleAgentWorkspaceAdapter, TraceStore,
    guard_profile,
)
from masguardeval.store import PostgresTraceStore
from masguardeval.stats import summarize_trials
from masguardeval.protocol import audit_report


ROOT = Path(__file__).resolve().parents[1]


def endpoint_identity(value: str) -> str:
    """Keep a provider endpoint in the manifest without URL credentials or query tokens."""
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError("base URL must include a scheme and hostname")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}"


def source_hashes() -> dict[str, str]:
    paths = ["backend/masguardeval/runner.py", "backend/masguardeval/live.py",
             "backend/masguardeval/guards.py", "backend/masguardeval/metrics.py",
             "backend/masguardeval/models.py", "backend/masguardeval/dataset.py",
             "backend/masguardeval/workspace.py"]
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run model-driven agents against isolated mock workspace tools.")
    parser.add_argument("--provider", choices=["openai", "ollama"], default="openai")
    parser.add_argument("--model", required=True, help="Model identifier; OpenAI credentials come from OPENAI_API_KEY.")
    parser.add_argument("--dataset", default=str(ROOT / "datasets" / "golden_scenarios.json"))
    parser.add_argument("--scenario-ids", help="Comma-separated IDs; defaults to every scenario.")
    parser.add_argument("--architectures", default="single,multi", help="Comma-separated single and/or multi.")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--max-tool-calls", type=int, default=4)
    parser.add_argument("--guard-profile", choices=["full", "allowlist", "access_control"], default="full")
    parser.add_argument("--base-url", help="Provider API base URL; defaults to local Ollama or OpenAI.")
    parser.add_argument("--temperature", type=float, default=0.0, help="Ollama sampling temperature.")
    parser.add_argument("--seed", type=int, default=23, help="Ollama sampling seed.")
    parser.add_argument("--max-output-tokens", type=int, default=256, help="Ollama generation budget per response.")
    parser.add_argument("--request-timeout", type=float, default=180, help="Ollama request timeout in seconds.")
    parser.add_argument("--out", default=str(ROOT / "reports" / "live_experiment.json"))
    parser.add_argument("--db", default=str(ROOT / "reports" / "runs.sqlite3"))
    parser.add_argument("--resume", action="store_true", help="Resume a matching partial report without rerunning completed pairs.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on the first failed pair after saving the partial report.")
    args = parser.parse_args()
    if not 1 <= args.trials <= 100:
        parser.error("--trials must be 1..100")
    architectures = [item.strip() for item in args.architectures.split(",") if item.strip()]
    if not architectures or set(architectures) - {"single", "multi"}:
        parser.error("--architectures must contain single and/or multi")

    dataset = GoldenDataset.load(args.dataset)
    scenario_ids = [item.strip() for item in args.scenario_ids.split(",")] if args.scenario_ids else [item.scenario_id for item in dataset.scenarios]
    for scenario_id in scenario_ids:
        dataset.get(scenario_id)
    if args.provider == "ollama":
        client = OllamaChatClient(
            args.model, base_url=args.base_url or "http://127.0.0.1:11434",
            temperature=args.temperature, seed=args.seed,
            max_output_tokens=args.max_output_tokens, timeout=args.request_timeout,
        )
        model_metadata = client.model_metadata()
    else:
        client = OpenAIResponsesClient(args.model, base_url=args.base_url)
        model_metadata = {"name": args.model, "digest": None}
    output = Path(args.out)
    dataset_hash = hashlib.sha256(Path(args.dataset).read_bytes()).hexdigest()
    provider_endpoint = endpoint_identity(
        args.base_url or ("http://127.0.0.1:11434" if args.provider == "ollama" else "https://api.openai.com")
    )
    identity = {
        "model": args.model, "provider": args.provider, "model_metadata": model_metadata,
        "provider_endpoint": provider_endpoint, "source_hashes": source_hashes(),
        "temperature": args.temperature if args.provider == "ollama" else None,
        "seed": args.seed if args.provider == "ollama" else None,
        "max_output_tokens": args.max_output_tokens if args.provider == "ollama" else None,
        "max_tool_calls": args.max_tool_calls,
        "guard_profile": args.guard_profile,
        "architectures": architectures, "trials_per_scenario": args.trials,
        "scenario_ids": scenario_ids, "dataset_sha256": dataset_hash,
    }
    if output.exists():
        if not args.resume:
            parser.error(f"Report already exists: {output}; use --resume for a matching partial run")
        report = json.loads(output.read_text(encoding="utf-8"))
        if any(report.get(key) != value for key, value in identity.items()):
            parser.error("Existing report does not match the requested model, dataset, or run configuration")
    else:
        if args.resume:
            parser.error(f"Cannot resume missing report: {output}")
        report = {
        "experiment_id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "execution_kind": "live_model_agent",
        **identity,
        "dataset": str(Path(args.dataset).resolve()),
        "git_revision": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip() or None,
        "git_worktree_dirty": bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()),
        "results": [], "failure_attempts": [],
        "interpretation": "Unadjudicated model runs. Human labels, task-success judgments, and statistical analysis are separate steps.",
        }
    store = PostgresTraceStore(os.environ["MASGUARDEVAL_DATABASE_URL"]) if os.environ.get("MASGUARDEVAL_DATABASE_URL") else TraceStore(args.db)
    scheduled = {(architecture, trial, scenario_id)
                 for architecture in architectures for trial in range(1, args.trials + 1) for scenario_id in scenario_ids}

    def persist() -> None:
        completed = {(item["architecture"], item["trial"], item["scenario"]["scenario_id"])
                     for item in report["results"]}
        report["scheduled_pair_count"] = len(scheduled)
        report["completed_pair_count"] = len(completed)
        report["incomplete_pair_count"] = len(scheduled - completed)
        report["run_count"] = len(report["results"]) * 2
        report["status"] = "complete" if completed == scheduled else "partial"
        report["updated_at"] = datetime.now(timezone.utc).isoformat()
        audit_report(report)
        report["analysis"] = summarize_trials([row for row in report["results"] if row["protocol_valid"]])
        report["analysis_excludes_protocol_failure_pairs"] = True
        temporary = output.with_name(output.name + ".tmp")
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(output)

    output.parent.mkdir(parents=True, exist_ok=True)
    persist()
    completed = {(item["architecture"], item["trial"], item["scenario"]["scenario_id"])
                 for item in report["results"]}
    try:
        for architecture in architectures:
            adapter_type = SingleAgentWorkspaceAdapter if architecture == "single" else LiveWorkspaceAdapter
            engine = EvaluationEngine(
                dataset, adapter=adapter_type(client, args.model, args.max_tool_calls),
                guards=guard_profile(args.guard_profile), trace_store=store,
            )
            for trial in range(1, args.trials + 1):
                for scenario_id in scenario_ids:
                    if (architecture, trial, scenario_id) in completed:
                        continue
                    try:
                        evaluated = engine.evaluate(scenario_id)
                    except Exception as exc:
                        report["failure_attempts"].append({
                            "architecture": architecture, "trial": trial, "scenario_id": scenario_id,
                            "error_type": type(exc).__name__,
                            "recorded_at": datetime.now(timezone.utc).isoformat(),
                        })
                        persist()
                        print(f"{architecture} trial {trial}/{args.trials} {scenario_id}: failed ({type(exc).__name__})")
                        if args.fail_fast:
                            raise
                        continue
                    report["results"].append({"architecture": architecture, "trial": trial, **evaluated.to_dict()})
                    completed.add((architecture, trial, scenario_id))
                    persist()
                    print(f"{architecture} trial {trial}/{args.trials} {scenario_id}: guarded_blocked={evaluated.guarded_trace.blocked}")
    finally:
        persist()
    print(f"Wrote {report['completed_pair_count']}/{report['scheduled_pair_count']} baseline/guarded pairs to {output}")
    if report["incomplete_pair_count"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
