"""Prepare condition-masked outcome packets and reconcile independent labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from masguardeval.outcome_review import make_outcome_packet, make_outcome_review_template, reconcile_outcomes
from masguardeval.study import read_jsonl


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare or reconcile blinded trial outcome reviews.")
    commands = parser.add_subparsers(dest="command", required=True)
    packet_command = commands.add_parser("packet")
    packet_command.add_argument("--report", required=True)
    packet_command.add_argument("--review-out", required=True)
    packet_command.add_argument("--private-map-out", required=True)
    packet_command.add_argument("--seed", type=int, default=23)
    reconcile_command = commands.add_parser("reconcile")
    reconcile_command.add_argument("--packet", required=True)
    reconcile_command.add_argument("--private-map", required=True)
    reconcile_command.add_argument("--reviews", nargs="+", required=True)
    reconcile_command.add_argument("--adjudications")
    reconcile_command.add_argument("--out", required=True)
    args = parser.parse_args()

    if args.command == "packet":
        review_dir = Path(args.review_out)
        map_path = Path(args.private_map_out)
        if review_dir.exists() or map_path.exists():
            parser.error("Review output and private map targets must not already exist")
        if map_path.parent.resolve() == review_dir.resolve():
            parser.error("Private condition map must be outside the reviewer directory")
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        packet, mapping = make_outcome_packet(report, seed=args.seed)
        review_dir.mkdir(parents=True)
        map_path.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl(review_dir / "blinded_trials.jsonl", packet)
        template = make_outcome_review_template(packet)
        write_jsonl(review_dir / "reviewer_a_template.jsonl", template)
        write_jsonl(review_dir / "reviewer_b_template.jsonl", template)
        write_json(map_path, mapping)
        print(f"Prepared {len(packet)} condition-masked trials; keep {map_path} private from reviewers")
        return

    packet = read_jsonl(args.packet)
    mapping = json.loads(Path(args.private_map).read_text(encoding="utf-8"))
    reviews = [row for path in args.reviews for row in read_jsonl(path)]
    adjudications = read_jsonl(args.adjudications) if args.adjudications else []
    try:
        result = reconcile_outcomes(packet, mapping, reviews, adjudications)
    except ValueError as exc:
        parser.error(str(exc))
    output = Path(args.out)
    if output.exists():
        parser.error(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, result)
    print(f"Reconciled {len(result['outcomes'])} trials")


if __name__ == "__main__":
    main()
