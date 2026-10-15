"""Compare two complete matched live-run reports descriptively."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from masguardeval.profile_comparison import compare_guard_profiles


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare matched guard profile reports.")
    parser.add_argument("--left", required=True)
    parser.add_argument("--right", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    left = json.loads(Path(args.left).read_text(encoding="utf-8"))
    right = json.loads(Path(args.right).read_text(encoding="utf-8"))
    comparison = compare_guard_profiles(left, right)
    output = Path(args.out)
    if output.exists():
        parser.error(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(comparison, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Compared {comparison['matched_pair_n']} task trials")


if __name__ == "__main__":
    main()
