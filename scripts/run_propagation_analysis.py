from __future__ import annotations

import argparse
import json
from pathlib import Path

from masguardeval import EvaluationEngine
from masguardeval.propagation import PropagationAnalyzer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "datasets" / "golden_scenarios.json"
DEFAULT_OUT = ROOT / "reports" / "propagation_analysis.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze failure propagation paths for a scenario.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--scenario-id", default="cascade_001")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    engine = EvaluationEngine.from_dataset_path(args.dataset)
    result = engine.evaluate(args.scenario_id)
    analysis = PropagationAnalyzer().analyze(result.baseline_trace)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(analysis.to_dict(), indent=2), encoding="utf-8")
    print(f"Wrote propagation analysis for {args.scenario_id} to {out}")


if __name__ == "__main__":
    main()
