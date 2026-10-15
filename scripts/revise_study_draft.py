"""Build a versioned proposed repair from the reviewed v2 study draft."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from masguardeval import GoldenDataset
from masguardeval.study_revision import revise_reviewed_draft


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.out.resolve() == args.source.resolve() or args.out.exists() or args.manifest.exists():
        parser.error("Output must be new and must not overwrite the source or an existing manifest")
    source_bytes = args.source.read_bytes()
    source = json.loads(source_bytes)
    revised, manifest = revise_reviewed_draft(source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(revised, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        GoldenDataset.load(args.out)
    except Exception:
        args.out.unlink()
        raise
    manifest["source_file_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    manifest["output_file_sha256"] = hashlib.sha256(args.out.read_bytes()).hexdigest()
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {manifest['revised_scenario_count']} agent-revised and {manifest['unchanged_scenario_count']} unchanged tasks")
    print("All revised tasks need human authorship and hash-bound review before freeze.")


if __name__ == "__main__":
    main()
