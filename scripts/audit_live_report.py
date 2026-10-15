"""Preserve a raw pilot report and write a protocol-audited copy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from masguardeval.protocol import audit_report
from masguardeval.stats import summarize_trials
from masguardeval.study import canonical_hash


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit adapter protocol failures in an existing live-run report.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out)
    if output.exists():
        parser.error(f"Output already exists: {output}")
    source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    source_hash = canonical_hash(source)
    audited = audit_report(source)
    audited["analysis"] = summarize_trials([row for row in audited["results"] if row["protocol_valid"]])
    audited["analysis_excludes_protocol_failure_pairs"] = True
    audited["audit_source_content_sha256"] = source_hash
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audited, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Audited {len(audited['results'])} pairs: {audited['protocol_failure_pair_count']} protocol failures")


if __name__ == "__main__":
    main()
