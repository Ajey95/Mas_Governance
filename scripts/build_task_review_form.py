"""Generate a self-contained, offline form for independent task reviewers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from masguardeval import GoldenDataset
from masguardeval.study import canonical_hash, make_review_packet


TEMPLATE = Path(__file__).with_name("task_review_form.template.html")


def render_form(dataset_path: str | Path) -> str:
    dataset_path = Path(dataset_path)
    dataset = GoldenDataset.load(dataset_path)
    payload = {
        "dataset_name": dataset_path.name,
        "dataset_sha256": canonical_hash(dataset.to_dict()),
        "scenarios": [scenario.to_dict() for scenario in dataset.scenarios],
        "packet": make_review_packet(dataset),
    }
    # The task text is untrusted. Escape HTML-significant characters before
    # embedding JSON inside a script element; the UI also uses textContent.
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = TEMPLATE.read_text(encoding="utf-8")
    marker = "__REVIEW_DATA__"
    if template.count(marker) != 1:
        raise ValueError("Review form template must contain one data marker")
    return template.replace(marker, encoded)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="Final scenario JSON to review")
    parser.add_argument("--out", required=True, help="Standalone HTML output path")
    parser.add_argument("--force", action="store_true", help="Replace an existing generated form")
    args = parser.parse_args()

    output = Path(args.out)
    if output.exists() and not args.force:
        parser.error(f"Output already exists: {output}; pass --force to regenerate")
    html = render_form(args.dataset)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(f"Wrote offline review form: {output}")


if __name__ == "__main__":
    main()
