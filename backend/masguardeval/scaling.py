from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from .models import EvaluationResult
from .runner import EvaluationEngine


@dataclass(frozen=True)
class EvaluationShard:
    shard_id: int
    scenario_ids: list[str]

    def to_dict(self) -> dict[str, object]:
        return {"shard_id": self.shard_id, "scenario_ids": self.scenario_ids}


@dataclass(frozen=True)
class BatchEvaluationResult:
    scenario_count: int
    worker_count: int
    shards: list[EvaluationShard]
    results: list[EvaluationResult]
    summary: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_count": self.scenario_count,
            "worker_count": self.worker_count,
            "shards": [shard.to_dict() for shard in self.shards],
            "summary": self.summary,
            "results": [result.to_dict() for result in self.results],
        }


class BatchEvaluationExecutor:
    """Chunked executor that can be backed by local threads or external workers."""

    def __init__(self, engine: EvaluationEngine, *, max_workers: int = 4, chunk_size: int = 10) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        self.engine = engine
        self.max_workers = max_workers
        self.chunk_size = chunk_size

    def shard(self) -> list[EvaluationShard]:
        scenarios = [scenario.scenario_id for scenario in self.engine.dataset.scenarios]
        return [
            EvaluationShard(index, scenarios[start : start + self.chunk_size])
            for index, start in enumerate(range(0, len(scenarios), self.chunk_size))
        ]

    def run(self) -> BatchEvaluationResult:
        scenario_ids = [scenario.scenario_id for scenario in self.engine.dataset.scenarios]
        indexed_results: dict[int, EvaluationResult] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(self.engine.evaluate, scenario_id): index
                for index, scenario_id in enumerate(scenario_ids)
            }
            for future in as_completed(futures):
                indexed_results[futures[future]] = future.result()

        results = [indexed_results[index] for index in sorted(indexed_results)]
        summary = self.engine._summary([result.to_dict() for result in results])
        return BatchEvaluationResult(
            scenario_count=len(results),
            worker_count=self.max_workers,
            shards=self.shard(),
            results=results,
            summary=summary,
        )

