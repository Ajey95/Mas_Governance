"""Adapt a submitted task draft to the executable mock-workspace schema."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from masguardeval import GoldenDataset
from masguardeval.study_repair import repair_submitted_draft


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.out.resolve() == args.source.resolve():
        parser.error("Output must not overwrite the submitted source file")
    if args.out.exists() or args.manifest.exists():
        parser.error("Output or manifest already exists")
    source_bytes = args.source.read_bytes()
    fixture_bytes = args.fixtures.read_bytes()
    source = json.loads(source_bytes)
    fixture_record = json.loads(fixture_bytes)
    if fixture_record.get("provenance") != "agent_authored_mock_fixture_pending_human_review":
        parser.error("Fixture provenance is missing or unexpected")
    fixed, manifest = repair_submitted_draft(source, fixture_record["fixtures"])
    if len(manifest["fixture_ids"]) != manifest["scenario_count"]:
        parser.error("Every submitted scenario needs an explicit fixture record")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(fixed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        GoldenDataset.load(args.out)
    except Exception:
        args.out.unlink()
        raise
    manifest["source_file_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    manifest["fixture_file_sha256"] = hashlib.sha256(fixture_bytes).hexdigest()
    manifest["output_file_sha256"] = hashlib.sha256(args.out.read_bytes()).hexdigest()
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {manifest['scenario_count']} technically adapted tasks to {args.out}")
    print("Original prompts and rubrics preserved; mock fixtures and policy changes need human review.")


if __name__ == "__main__":
    main()
