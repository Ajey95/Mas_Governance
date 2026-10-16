"""The offline reviewer form must bind its exports to exact task versions."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from masguardeval.dataset import GoldenDataset
from masguardeval.study import canonical_hash


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts" / "build_task_review_form.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("build_task_review_form", BUILDER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def embedded_data(html: str) -> dict:
    marker = "const REVIEW_DATA = "
    payload = html.split(marker, 1)[1].split(";\n", 1)[0]
    return json.loads(payload)


def test_review_form_binds_each_row_to_canonical_task_hash():
    dataset_path = ROOT / "datasets" / "golden_scenarios.json"
    dataset = GoldenDataset.load(dataset_path)
    html = load_builder().render_form(dataset_path)
    data = embedded_data(html)

    assert data["dataset_sha256"] == canonical_hash(dataset.to_dict())
    assert len(data["scenarios"]) == len(data["packet"]) == 7
    assert [(row["scenario_id"], row["scenario_sha256"]) for row in data["packet"]] == [
        (scenario.scenario_id, canonical_hash(scenario.to_dict()))
        for scenario in dataset.scenarios
    ]


def test_untrusted_task_text_cannot_close_the_embedded_script(tmp_path):
    payload = json.loads((ROOT / "datasets" / "golden_scenarios.json").read_text(encoding="utf-8"))
    payload["scenarios"][0]["prompt"] = "</script><script>window.pwned=1</script>"
    dataset_path = tmp_path / "tasks.json"
    dataset_path.write_text(json.dumps(payload), encoding="utf-8")

    html = load_builder().render_form(dataset_path)

    assert "</script><script>window.pwned=1" not in html
    assert "\\u003c/script\\u003e" in html
    assert embedded_data(html)["scenarios"][0]["prompt"] == payload["scenarios"][0]["prompt"]
