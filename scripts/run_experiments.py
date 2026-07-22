from __future__ import annotations

import argparse
import json
from pathlib import Path

from masguardeval import EvaluationEngine
from masguardeval.experiments import ExperimentSuite


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "datasets" / "golden_scenarios.json"
DEFAULT_JSON = ROOT / "reports" / "experiment_report.json"
DEFAULT_MD = ROOT / "reports" / "experiment_report.md"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run broad MASGuardEval experiments and ablations.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--json-out", default=str(DEFAULT_JSON))
    parser.add_argument("--md-out", default=str(DEFAULT_MD))
    args = parser.parse_args()

    engine = EvaluationEngine.from_dataset_path(args.dataset)
    report = ExperimentSuite(engine).run()

    json_out = Path(args.json_out)
    md_out = Path(args.md_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    md_out.write_text(report.to_markdown(), encoding="utf-8")
    print(f"Wrote {report.scenario_count} scenario experiment results to {json_out} and {md_out}")


if __name__ == "__main__":
    main()
