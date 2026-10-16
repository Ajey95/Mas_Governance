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


def test_trace_report_recomputes_file_run_and_links_observations(tmp_path):
    run = tmp_path / "run.json"
    assert main(["run-agent", "--dataset", str(DATASET), "--scenario", "fictional_tool_boundary",
                 "--factory", f"{FACTORY}:create_engine", "--out", str(run)]) == 0
    # Stored derived values are untrusted; the report must recompute them.
    payload = json.loads(run.read_text(encoding="utf-8"))
    payload["metrics"] = {"TSP": {"score": 999}}
    payload["graph"] = {"edges": []}
    run.write_text(json.dumps(payload), encoding="utf-8")
    json_out, md_out = tmp_path / "detail.json", tmp_path / "detail.md"
    assert main(["trace-report", "--input", str(run), "--json-out", str(json_out),
                 "--md-out", str(md_out)]) == 0
    report = json.loads(json_out.read_text(encoding="utf-8"))
    markdown = md_out.read_text(encoding="utf-8")
    assert report["provenance"]["source"] == "file"
    assert len(report["provenance"]["source_file_sha256"]) == 64
    assert len(report["provenance"]["trace_snapshot_sha256"]) == 64
    assert report["evaluation"]["metrics"]["TSP"]["score"] != 999
    assert report["graph"]["edges"]
    assert report["observability"]["guard_decisions"]["BLOCK"] >= 1
    assert report["evaluation"]["findings"]["findings"][0]["evidence_span_ids"]
    assert "Event timeline" in markdown and "Metric evidence" in markdown
    assert "authorship" in markdown and "no matched baseline" in markdown


def test_trace_report_from_sqlite_and_rejects_mismatched_trace(tmp_path, capsys, monkeypatch):
    run, database = tmp_path / "run.json", tmp_path / "runs.sqlite3"
    assert main(["run-agent", "--dataset", str(DATASET), "--scenario", "fictional_tool_boundary",
                 "--factory", f"{FACTORY}:create_engine", "--out", str(run),
                 "--sqlite", str(database)]) == 0
    trace_id = json.loads(run.read_text(encoding="utf-8"))["trace"]["trace_id"]
    monkeypatch.delenv("MASGUARDEVAL_DATABASE_URL", raising=False)
    report_path = tmp_path / "saved-report.json"
    assert main(["trace-report", "--trace-id", trace_id, "--sqlite", str(database),
                 "--json-out", str(report_path)]) == 0
    assert json.loads(report_path.read_text(encoding="utf-8"))["provenance"]["source"] == "sqlite"
    bad = json.loads(run.read_text(encoding="utf-8"))
    bad["trace"]["scenario_id"] = "different"
    run.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(SystemExit) as failure:
        main(["trace-report", "--input", str(run), "--md-out", str(tmp_path / "bad.md")])
    assert failure.value.code == 2
    assert "Scenario and trace IDs do not match" in capsys.readouterr().err
    assert not (tmp_path / "bad.md").exists()


def test_trace_report_exposes_declared_failure_paths_without_claiming_causality():
    from masguardeval.trace_report import build_trace_report

    dataset = GoldenDataset.load(DATASET.parents[1] / "datasets" / "golden_scenarios.json")
    scenario = dataset.get("cascade_001")
    trace = EvaluationEngine(dataset).evaluate("cascade_001").baseline_trace
    report = build_trace_report(scenario, trace, adapter="reference", source="test")
    propagation = report["graph"]["span_propagation"]
    assert len(report["observability"]["candidate_failure_paths"]) == 3
    assert len(propagation["dependency_edges"]) == 3
    assert report["evaluation"]["metrics"]["CFP"]["score"] == 1.0
    assert "causal root-cause claim" in report["evaluation"]["scope"]


def test_trace_report_does_not_overwrite_its_input(tmp_path):
    source = tmp_path / "run.json"
    source.write_text("keep this input", encoding="utf-8")
    with pytest.raises(SystemExit) as failure:
        main(["trace-report", "--input", str(source), "--json-out", str(source)])
    assert failure.value.code == 2
    assert source.read_text(encoding="utf-8") == "keep this input"


def test_compare_agent_runs_independent_modes_and_saves_both_traces(tmp_path):
    output, database = tmp_path / "comparison.json", tmp_path / "comparison.sqlite3"
    assert main([
        "compare-agent", "--dataset", str(DATASET), "--scenario", "fictional_tool_boundary",
        "--factory", f"{FACTORY}:create_engine", "--allow-unguarded",
        "--out", str(output), "--sqlite", str(database),
    ]) == 0
    comparison = json.loads(output.read_text(encoding="utf-8"))
    assert comparison["comparison_scope"] == "isolated caller-provided tool handlers"
    assert comparison["baseline_trace"]["mode"] == "baseline"
    assert comparison["guarded_trace"]["mode"] == "guarded"
    assert comparison["baseline_trace"]["trace_id"] != comparison["guarded_trace"]["trace_id"]
    assert comparison["baseline_trace"]["blocked"] is False
    assert comparison["guarded_trace"]["blocked"] is True
    assert [span["tool"] for span in comparison["baseline_trace"]["spans"]
            if span["span_type"] == "tool_call"] == ["metadata_lookup", "private_export"]
    assert [span["tool"] for span in comparison["guarded_trace"]["spans"]
            if span["span_type"] == "tool_call"] == ["metadata_lookup"]
    assert set(comparison["baseline_metrics"]) == set(comparison["guarded_metrics"])
    assert "baseline_graph" in comparison and "guarded_graph" in comparison
    assert "baseline_findings" in comparison and "guarded_findings" in comparison
    assert comparison["metric_change_scope"] == "descriptive trace comparison, not measured risk reduction"
    from masguardeval import TraceStore
    store = TraceStore(database)
    assert store.get(comparison["baseline_trace"]["trace_id"])["mode"] == "baseline"
    assert store.get(comparison["guarded_trace"]["trace_id"])["mode"] == "guarded"


def test_compare_agent_requires_explicit_unguarded_opt_in(tmp_path, capsys):
    output = tmp_path / "comparison.json"
    with pytest.raises(SystemExit) as failure:
        main(["compare-agent", "--dataset", str(DATASET), "--scenario", "fictional_tool_boundary",
              "--factory", f"{FACTORY}:create_engine", "--out", str(output)])
    assert failure.value.code == 2
    assert "--allow-unguarded" in capsys.readouterr().err
    assert not output.exists()


def test_compare_agent_rejects_reused_adapter_before_execution(tmp_path, capsys):
    factory = tmp_path / "same_adapter.py"
    factory.write_text(
        "from masguardeval import EvaluationEngine, ExecutionEvent\n"
        "class Adapter:\n"
        "    name = 'stateful'\n"
        "    def plan(self, scenario, mode):\n"
        "        yield ExecutionEvent(agent='A', event_type='agent_step', action='done', user_role=scenario.user_role)\n"
        "adapter = Adapter()\n"
        "def create_engine(dataset):\n"
        "    return EvaluationEngine(dataset, adapter=adapter)\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as failure:
        main(["compare-agent", "--dataset", str(DATASET), "--scenario", "fictional_tool_boundary",
              "--factory", f"{factory}:create_engine", "--allow-unguarded",
              "--out", str(tmp_path / "comparison.json")])
    assert failure.value.code == 2
    assert "fresh adapter" in capsys.readouterr().err
    assert not (tmp_path / "comparison.json").exists()


def test_trace_report_selects_each_mode_from_paired_comparison(tmp_path):
    comparison, detail = tmp_path / "comparison.json", tmp_path / "baseline-report.json"
    assert main(["compare-agent", "--dataset", str(DATASET), "--scenario", "fictional_tool_boundary",
                 "--factory", f"{FACTORY}:create_engine", "--allow-unguarded",
                 "--out", str(comparison)]) == 0
    assert main(["trace-report", "--input", str(comparison), "--mode", "baseline",
                 "--json-out", str(detail)]) == 0
    report = json.loads(detail.read_text(encoding="utf-8"))
    assert report["provenance"]["trace_id"] == json.loads(comparison.read_text(encoding="utf-8"))["baseline_trace"]["trace_id"]
    assert report["evaluation"]["metrics"]["TSP"]["score"] < 1


def test_agent_cli_rejects_output_collisions_with_inputs(tmp_path, capsys):
    source = tmp_path / "dataset.json"
    source.write_bytes(DATASET.read_bytes())
    original = source.read_bytes()
    with pytest.raises(SystemExit) as failure:
        main(["run-agent", "--dataset", str(source), "--scenario", "fictional_tool_boundary",
              "--factory", f"{FACTORY}:create_engine", "--out", str(source)])
    assert failure.value.code == 2
    assert "overwrite" in capsys.readouterr().err
    assert source.read_bytes() == original


def test_trace_report_rejects_non_object_json_without_traceback(tmp_path, capsys):
    source = tmp_path / "bad.json"
    source.write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit) as failure:
        main(["trace-report", "--input", str(source), "--json-out", str(tmp_path / "report.json")])
    assert failure.value.code == 2
    assert "Input run has no scenario snapshot" in capsys.readouterr().err
    assert not (tmp_path / "report.json").exists()
