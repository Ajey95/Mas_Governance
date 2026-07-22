from __future__ import annotations

import argparse
import json
from pathlib import Path

from masguardeval import EvaluationEngine
from masguardeval.scaling import BatchEvaluationExecutor


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "datasets" / "golden_scenarios.json"
DEFAULT_OUT = ROOT / "reports" / "scalability_batch.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run chunked MASGuardEval scenario batches.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--chunk-size", type=int, default=10)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    engine = EvaluationEngine.from_dataset_path(args.dataset)
    batch = BatchEvaluationExecutor(engine, max_workers=args.max_workers, chunk_size=args.chunk_size)
    result = batch.run()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    print(f"Wrote {result.scenario_count} batched scenario results to {out}")


if __name__ == "__main__":
    main()
