from __future__ import annotations

import json
from pathlib import Path

from .models import Scenario


class GoldenDataset:
    """JSON-backed golden dataset loader with domain validation."""

    def __init__(self, scenarios: list[Scenario]) -> None:
        self.scenarios = scenarios
        self._by_id = {scenario.scenario_id: scenario for scenario in scenarios}
        if len(self._by_id) != len(scenarios):
            raise ValueError("Duplicate scenario_id values found in golden dataset")

    @classmethod
    def load(cls, path: str | Path) -> "GoldenDataset":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        scenarios = [Scenario.from_dict(item) for item in payload["scenarios"]]
        dataset = cls(scenarios)
        dataset.validate()
        return dataset

    def validate(self) -> None:
        required_metrics = {"TSP", "TSR", "PHR", "CPI", "CFP", "RSS", "CCR", "DT"}
        for scenario in self.scenarios:
            unknown_metrics = set(scenario.metrics) - required_metrics
            if unknown_metrics:
                raise ValueError(f"{scenario.scenario_id} has unknown metrics: {sorted(unknown_metrics)}")
            overlap = set(scenario.allowed_tools) & set(scenario.blocked_tools)
            if overlap:
                raise ValueError(f"{scenario.scenario_id} allows and blocks the same tools: {sorted(overlap)}")

    def get(self, scenario_id: str) -> Scenario:
        try:
            return self._by_id[scenario_id]
        except KeyError as exc:
            raise KeyError(f"Unknown scenario_id: {scenario_id}") from exc

    def to_dict(self) -> dict[str, list[dict[str, object]]]:
        return {"scenarios": [scenario.to_dict() for scenario in self.scenarios]}
