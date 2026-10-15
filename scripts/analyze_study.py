"""Analyze frozen development and held-out model trials with independent labels."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from masguardeval import GoldenDataset
from masguardeval.study_analysis import analyze_study


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze independently labelled development and held-out trials.")
    parser.add_argument("--development-dataset", required=True)
    parser.add_argument("--heldout-dataset", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--development-report", required=True)
    parser.add_argument("--heldout-report", required=True)
    parser.add_argument("--development-outcomes", required=True)
    parser.add_argument("--heldout-outcomes", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    for dataset_path, report_path in ((args.development_dataset, args.development_report),
                                      (args.heldout_dataset, args.heldout_report)):
        if load(report_path).get("dataset_sha256") != hashlib.sha256(Path(dataset_path).read_bytes()).hexdigest():
            parser.error(f"Experiment dataset file hash mismatch: {dataset_path}")
    result = analyze_study(
        load(args.development_report), load(args.development_outcomes), GoldenDataset.load(args.development_dataset),
        load(args.heldout_report), load(args.heldout_outcomes), GoldenDataset.load(args.heldout_dataset),
        load(args.manifest),
    )
    output = Path(args.out)
    if output.exists():
        parser.error(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote held-out study analysis to {output}")


if __name__ == "__main__":
    main()
