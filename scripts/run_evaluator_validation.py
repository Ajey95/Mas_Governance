from __future__ import annotations

import argparse
import json
from pathlib import Path

from masguardeval.evaluator import EvaluatorAgreement


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANNOTATIONS = ROOT / "datasets" / "evaluator_annotations.json"
DEFAULT_OUT = ROOT / "reports" / "evaluator_agreement.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute evaluator agreement with Cohen's Kappa.")
    parser.add_argument("--annotations", default=str(DEFAULT_ANNOTATIONS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    payload = json.loads(Path(args.annotations).read_text(encoding="utf-8"))
    labels_a = [row["human_expert"] for row in payload["annotations"]]
    labels_b = [row["llm_judge"] for row in payload["annotations"]]
    result = EvaluatorAgreement.cohens_kappa(labels_a, labels_b)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    print(f"Wrote evaluator agreement for {result.label_count} labels to {out}")


if __name__ == "__main__":
    main()
