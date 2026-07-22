from __future__ import annotations

import argparse
import json
from pathlib import Path

from masguardeval import EvaluationEngine


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "datasets" / "golden_scenarios.json"
DEFAULT_OUT = ROOT / "reports" / "latest_evaluation.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MASGuardEval scenarios and write a JSON report.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    engine = EvaluationEngine.from_dataset_path(args.dataset)
    payload = engine.generate_dashboard()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(payload['results'])} scenario results to {out}")


if __name__ == "__main__":
    main()
