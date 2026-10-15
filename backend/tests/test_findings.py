from __future__ import annotations

from pathlib import Path

from masguardeval import GoldenDataset
from masguardeval.findings import analyze_trace
from masguardeval.models import Span, Trace


SCENARIO = GoldenDataset.load(Path(__file__).resolve().parents[2] / "datasets" / "golden_scenarios.json").scenarios[0]


def test_findings_separate_blocked_proposal_from_executed_prohibited_tool():
    tool = SCENARIO.blocked_tools[0]
    trace = Trace.start(SCENARIO.scenario_id, "guarded")
    trace.add_span(Span.create(trace.trace_id, "guard_decision", "Guard", SCENARIO.user_role,
                               tool=tool, policy_decision="BLOCK", output="Outside permission"))
    blocked_report = analyze_trace(SCENARIO, trace)
    assert blocked_report["summary"]["high_severity_findings"] == 0
    assert blocked_report["findings"][0]["kind"] == "guard_intervention"

    trace.add_span(Span.create(trace.trace_id, "tool_call", "Agent", SCENARIO.user_role,
                               tool=tool, policy_decision="ALLOW", output="Mock write recorded"))
    report = analyze_trace(SCENARIO, trace)
    assert report["summary"]["high_severity_findings"] == 1
    assert report["findings"][1]["evidence_span_ids"] == [trace.spans[1].span_id]
    assert "independent review" in report["interpretation"]
