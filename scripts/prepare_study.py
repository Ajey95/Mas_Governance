"""Create independent review packets and freeze an adjudicated task set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from masguardeval import GoldenDataset
from masguardeval.study import freeze_study, make_review_packet, read_jsonl
from masguardeval.study_intake import AVAILABLE_TOOLS, build_blank_intake, preflight_draft


ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare and freeze independently reviewed study tasks.")
    commands = parser.add_subparsers(dest="command", required=True)
    intake = commands.add_parser("intake", help="Create blank task slots without copying synthetic scenarios.")
    intake.add_argument("--out", required=True)
    intake.add_argument("--tasks-per-risk", type=int, default=5)
    preflight = commands.add_parser("preflight", help="Check an author draft before independent review.")
    preflight.add_argument("--dataset", required=True)
    preflight.add_argument("--out", help="Optional JSON report path.")
    packet = commands.add_parser("packet", help="Generate two blank, separate reviewer record files.")
    packet.add_argument("--dataset", default=str(ROOT / "datasets" / "candidate_scenarios.json"))
    packet.add_argument("--out", required=True)

    freeze = commands.add_parser("freeze", help="Validate reviews and freeze development/heldout JSON files.")
    freeze.add_argument("--dataset", required=True)
    freeze.add_argument("--reviews", nargs="+", required=True)
    freeze.add_argument("--adjudications", help="JSONL file for reviewer disagreements.")
    freeze.add_argument("--out", required=True)
    freeze.add_argument("--seed", type=int, default=23)
    freeze.add_argument("--holdout-fraction", type=float, default=0.2)
    args = parser.parse_args()

    if args.command == "intake":
        output = Path(args.out)
        if output.exists():
            parser.error(f"Output directory already exists: {output}")
        try:
            payload = build_blank_intake(args.tasks_per_risk)
        except ValueError as exc:
            parser.error(str(exc))
        output.mkdir(parents=True)
        write_json(output / "draft_scenarios.json", payload)
        write_json(output / "tool_catalog.json", {"available_mock_tools": sorted(AVAILABLE_TOOLS)})
        (output / "README.md").write_text(
            "# Independent task authoring intake\n\n"
            "These are blank slots, not scenarios or evidence of human work. "
            "Ask authors to write tasks from their own source cases without copying "
            "the bundled reference or synthetic tasks. See `docs/STUDY_AUTHORING_GUIDE.md`.\n\n"
            "Fill the prompts, safe-behavior rubric, source case, roles, and mock tool "
            "policy. Assign exactly one `family:<source-id>` tag per task, with at "
            "least two distinct families in each risk. Change provenance to "
            "`independent_human_authored` only after genuine independent authorship. "
            "Run `preflight` before generating reviewer packets.\n",
            encoding="utf-8",
        )
        print(f"Wrote {len(payload['scenarios'])} blank task slots to {output}")
        return

    if args.command == "preflight":
        try:
            payload = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
            report = preflight_draft(payload, known_datasets=[
                ROOT / "datasets" / "golden_scenarios.json",
                ROOT / "datasets" / "candidate_scenarios.json",
            ])
        except (OSError, ValueError, TypeError) as exc:
            parser.error(str(exc))
        if args.out:
            write_json(Path(args.out), report)
        print(f"{report['status']}: {report['task_count']} tasks; {len(report['issues'])} issues")
        for issue in report["issues"][:20]:
            print(f"- {issue}")
        if len(report["issues"]) > 20:
            print(f"... {len(report['issues']) - 20} more issues; use --out to save the complete report")
        if report["issues"]:
            raise SystemExit(1)
        return

    dataset = GoldenDataset.load(args.dataset)
    output = Path(args.out)
    if output.exists():
        parser.error(f"Output directory already exists: {output}")
    if args.command == "packet":
        packet_rows = make_review_packet(dataset)
        output.mkdir(parents=True)
        write_jsonl(output / "reviewer_a_template.jsonl", packet_rows)
        write_jsonl(output / "reviewer_b_template.jsonl", packet_rows)
        write_jsonl(output / "adjudication_template.jsonl", [
            {"scenario_id": row["scenario_id"], "scenario_sha256": row["scenario_sha256"],
             "adjudicator_id": "", "decision": "", "recorded_at": "", "rationale": ""}
            for row in packet_rows
        ])
        write_json(output / "packet_manifest.json", {
            "source_dataset": str(Path(args.dataset).resolve()),
            "source_provenance": sorted({scenario.provenance for scenario in dataset.scenarios}),
            "task_count": len(packet_rows),
            "warning": "Blank templates are not human reviews. Synthetic candidates remain synthetic even if reviewed without independent task authorship.",
        })
        print(f"Wrote review templates for {len(packet_rows)} tasks to {output}")
        return

    reviews = [record for path in args.reviews for record in read_jsonl(path)]
    adjudications = read_jsonl(args.adjudications) if args.adjudications else []
    try:
        development, heldout, manifest = freeze_study(
            dataset, reviews, adjudications, seed=args.seed,
            holdout_fraction=args.holdout_fraction,
        )
    except ValueError as exc:
        parser.error(str(exc))
    manifest["source_dataset"] = str(Path(args.dataset).resolve())
    output.mkdir(parents=True)
    write_json(output / "development.json", development.to_dict())
    write_json(output / "heldout.json", heldout.to_dict())
    write_json(output / "study_manifest.json", manifest)
    print(f"Frozen {manifest['accepted_tasks']} tasks: {manifest['development_tasks']} development, {manifest['heldout_tasks']} held out")


if __name__ == "__main__":
    main()
