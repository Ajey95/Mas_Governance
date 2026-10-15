import json
from pathlib import Path

import pytest

from masguardeval import EvaluationEngine, ExecutionEvent, GoldenDataset, MetricResult, Scenario, Span, Trace
from masguardeval.cli import main


DATASET = Path(__file__).resolve().parents[2] / "examples" / "fictional_scenarios.json"
FACTORY = DATASET.with_name("cli_agent_factory.py")


def test_public_sdk_types_and_cli_validate(capsys):
    assert all((EvaluationEngine, ExecutionEvent, GoldenDataset, MetricResult, Scenario, Span, Trace))
    assert main(["validate", "--dataset", str(DATASET)]) == 0
    assert json.loads(capsys.readouterr().out) == {"valid": True, "scenario_count": 1}


def test_cli_evaluate_one_and_all(capsys, tmp_path):
    assert main(["evaluate", "--dataset", str(DATASET), "--scenario", "fictional_tool_boundary"]) == 0
    one = json.loads(capsys.readouterr().out)
    assert one["scenario"]["scenario_id"] == "fictional_tool_boundary"
    output = tmp_path / "nested" / "evaluation.json"
    assert main(["evaluate", "--dataset", str(DATASET), "--out", str(output)]) == 0
    assert len(json.loads(output.read_text(encoding="utf-8"))["results"]) == 1


def test_cli_report_writes_both_formats(tmp_path):
    json_out = tmp_path / "report.json"
    md_out = tmp_path / "report.md"
    assert main(["report", "--dataset", str(DATASET), "--json-out", str(json_out),
                 "--md-out", str(md_out)]) == 0
    assert json.loads(json_out.read_text(encoding="utf-8"))["scenario_count"] == 1
    assert "MASGuardEval Experiment Report" in md_out.read_text(encoding="utf-8")


def test_cli_rejects_bad_scenario_and_export_without_credential(capsys, monkeypatch):
    with pytest.raises(SystemExit) as bad_scenario:
        main(["evaluate", "--dataset", str(DATASET), "--scenario", "missing"])
    assert bad_scenario.value.code == 2
    assert "Unknown scenario_id" in capsys.readouterr().err
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    with pytest.raises(SystemExit) as no_key:
        main(["export", "--trace-id", "fictional", "--project", "demo", "--sqlite", "missing.db"])
    assert no_key.value.code == 2
    assert "LANGSMITH_API_KEY is required" in capsys.readouterr().err


def test_run_agent_guards_custom_handler_and_saves_inspectable_trace(tmp_path):
    output = tmp_path / "agent-run.json"
    database = tmp_path / "runs.sqlite3"
    assert main(["run-agent", "--dataset", str(DATASET), "--scenario", "fictional_tool_boundary",
                 "--factory", f"{FACTORY}:create_engine", "--out", str(output),
                 "--sqlite", str(database)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["adapter"] == "fictional_cli_agent"
    assert payload["execution_kind"] == "fictional_custom_adapter"
    assert payload["trace"]["blocked"]
    assert [span["tool"] for span in payload["trace"]["spans"] if span["span_type"] == "tool_call"] == ["metadata_lookup"]
    assert any(edge["kind"] == "blocked_tool_attempt" for edge in payload["graph"]["edges"])
    assert "TSP" in payload["metrics"]
    from masguardeval import TraceStore
    saved = TraceStore(database).get(payload["trace"]["trace_id"])
    assert saved is not None and saved["blocked"]


def test_run_agent_rejects_missing_factory_callable(capsys):
    with pytest.raises(SystemExit) as missing:
        main(["run-agent", "--dataset", str(DATASET), "--scenario", "fictional_tool_boundary",
              "--factory", f"{FACTORY}:not_a_factory"])
    assert missing.value.code == 2
    assert "Factory callable not found" in capsys.readouterr().err
