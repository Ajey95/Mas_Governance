import { useEffect, useMemo, useRef, useState } from "react";
import { apiBase, decideApproval, fetchApprovals, fetchDashboard, fetchRunHistory, fetchSavedGraph, fetchSavedFindings, fetchSavedRun } from "./api";
import { AgentGraph, InteractionTimeline } from "./TraceVisuals";
import type { AgentToolGraph, ApprovalRequest, DashboardPayload, FindingsReport, MetricKey, MetricResult, RunSummary, Span, Trace } from "./types";

const keys: MetricKey[] = ["TSP", "TSR", "PHR", "CPI", "CFP", "RSS", "CCR", "DT"];
const lowerIsBetter = new Set<MetricKey>(["PHR", "CPI", "CFP", "CCR", "DT"]);
const score = (metric: MetricResult) => metric.applicable ? metric.score.toFixed(3) : "N/A";
function improvement(before: MetricResult, after: MetricResult) {
  if (!before.applicable || !after.applicable) return "N/A";
  const delta = (after.score - before.score) * (lowerIsBetter.has(before.key) ? -1 : 1);
  return `${delta >= 0 ? "+" : ""}${delta.toFixed(3)}`;
}
function elapsed(trace: Trace) {
  return trace.elapsed_ms === null ? "N/A" : `${trace.elapsed_ms.toFixed(3)} ms`;
}
function downloadJson(filename: string, value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function App() {
  const [payload, setPayload] = useState<DashboardPayload | null>(null);
  const [scenarioId, setScenarioId] = useState("");
  const [mode, setMode] = useState<"baseline" | "guarded">("guarded");
  const [selectedSpanId, setSelectedSpanId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [savedTrace, setSavedTrace] = useState<Trace | null>(null);
  const [savedGraph, setSavedGraph] = useState<AgentToolGraph | null>(null);
  const [findings, setFindings] = useState<FindingsReport | null>(null);
  const [liveTrace, setLiveTrace] = useState<Trace | null>(null);
  const [liveGraph, setLiveGraph] = useState<AgentToolGraph | null>(null);
  const [liveSpans, setLiveSpans] = useState<Span[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [streamStatus, setStreamStatus] = useState("");
  const [approvalToken, setApprovalToken] = useState("");
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [approvalReason, setApprovalReason] = useState("Reviewed tool request");
  const streamRef = useRef<EventSource | null>(null);
  async function refreshHistory() { try { setHistory(await fetchRunHistory()); } catch { setHistory([]); } }
  async function refreshApprovals() {
    if (!approvalToken) return;
    try { setApprovals(await fetchApprovals(approvalToken)); } catch (cause) { setError(cause instanceof Error ? cause.message : "Approval lookup failed"); }
  }
  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = await fetchDashboard();
      setPayload(data);
      setSavedTrace(null); setSavedGraph(null); setLiveTrace(null); setLiveGraph(null); setFindings(null);
      setScenarioId(current => data.results.some(item => item.scenario.scenario_id === current)
        ? current : data.results[0]?.scenario.scenario_id ?? "");
      setSelectedSpanId("");
      await refreshHistory();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load the evaluation API.");
    } finally { setLoading(false); }
  }
  useEffect(() => { void load(); return () => streamRef.current?.close(); }, []);
  useEffect(() => { if (!streaming || !approvalToken) return; const timer = window.setInterval(() => void refreshApprovals(), 1500); return () => window.clearInterval(timer); }, [streaming, approvalToken]);
  async function openSaved(id: string) {
    try {
      const [trace, graph, report] = await Promise.all([fetchSavedRun(id), fetchSavedGraph(id), fetchSavedFindings(id)]);
      setSavedTrace(trace); setSavedGraph(graph); setFindings(report); setLiveTrace(null); setLiveGraph(null);
      setScenarioId(trace.scenario_id); setMode(trace.mode); setSelectedSpanId("");
      document.getElementById("traces")?.scrollIntoView({ behavior: "smooth" });
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load saved run"); }
  }
  function startStream() {
    if (!scenarioId || streaming) return;
    streamRef.current?.close();
    setSavedTrace(null); setSavedGraph(null); setLiveTrace(null); setLiveGraph(null); setFindings(null);
    setLiveSpans([]); setStreaming(true); setStreamStatus("Connecting…"); setError("");
    const source = new EventSource(`${apiBase}/stream/${encodeURIComponent(scenarioId)}?mode=${mode}`);
    streamRef.current = source;
    source.addEventListener("span", event => { const span = JSON.parse((event as MessageEvent).data) as Span; setLiveSpans(current => [...current, span]); setStreamStatus(`Streaming · ${span.agent} · ${span.span_type.replaceAll("_", " ")}`); });
    source.addEventListener("complete", event => {
      const completed = JSON.parse((event as MessageEvent).data) as { trace: Trace; findings: FindingsReport };
      const trace = completed.trace;
      setLiveTrace(trace); setFindings(completed.findings); setStreaming(false); setStreamStatus(`Completed · ${trace.spans.length} spans`);
      source.close(); void fetchSavedGraph(trace.trace_id).then(setLiveGraph).catch(() => {}); void refreshHistory(); void refreshApprovals();
    });
    source.addEventListener("error", event => {
      const detail = event instanceof MessageEvent ? JSON.parse(event.data)?.detail : "Connection failed";
      setStreamStatus(`Stream error: ${detail}`); setStreaming(false); source.close();
    });
  }
  async function decide(id: string, approve: boolean) {
    try { await decideApproval(id, approvalToken, approve, approvalReason); await refreshApprovals(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Approval failed"); }
  }
  const result = useMemo(() => payload?.results.find(item => item.scenario.scenario_id === scenarioId), [payload, scenarioId]);
  const referenceTrace = result ? (mode === "guarded" ? result.guarded_trace : result.baseline_trace) : null;
  const trace = savedTrace ?? liveTrace ?? referenceTrace;
  const graph = savedGraph ?? liveGraph ?? (result ? (mode === "guarded" ? result.guarded_graph : result.baseline_graph) : null);
  const selectedSpan = trace?.spans.find(span => span.span_id === selectedSpanId) ?? trace?.spans[0];

  return <div className="app">
    <header className="topbar"><div><div className="brand">◈ MASGuardEval</div><span className="topHint">Software workspace reference evaluation</span></div><nav><a href="#liveLog">Live logs</a><a href="#findings">Findings</a><a href={`${apiBase}/project-docs`}>Documentation</a><a href={`${apiBase}/docs`}>API</a><button onClick={() => void load()} disabled={loading}>{loading ? "Running…" : "Run evaluation"}</button></nav></header>
    <main>
      <div className="intro"><div><p className="eyebrow">REFERENCE EXPERIMENT</p><h1>Agent safety evaluation</h1><p>Compare unguarded and guarded execution of {payload?.results.length ?? "the loaded"} scripted scenarios in an isolated mock workspace.</p></div><div className="modeNotice"><strong>{payload?.execution_kind === "isolated_mock_workspace" ? "Mock execution" : payload?.execution_kind ?? "Waiting for API"}</strong><span>{payload?.adapter ?? "No adapter loaded"}</span><small>Scores describe these runs only. They are not a validated population estimate or evidence from a live LLM.</small></div></div>
      {error && <div className="error" role="alert">API error: {error}. Start the backend and try again.</div>}
      {!result && savedTrace && <section className="panel" id="savedCandidate"><div className="sectionHead"><div><p className="eyebrow">SAVED CANDIDATE RUN</p><h2>{savedTrace.scenario_id} · {savedTrace.mode}</h2></div><button className="actionButton" onClick={() => void load()}>Back to reference dashboard</button></div><p className="muted">{savedTrace.scenario?.prompt ?? "Scenario snapshot unavailable for this older run."}</p><div className="traceMeta"><span>Trace: <code>{savedTrace.trace_id}</code></span><span>Elapsed: {elapsed(savedTrace)}</span></div><h3>Interaction timeline</h3><InteractionTimeline trace={savedTrace} selectedSpanId={selectedSpanId} onSelect={setSelectedSpanId} /><h3>Agent–tool graph</h3><AgentGraph graph={savedGraph} selectedSpanId={selectedSpanId} onSelect={setSelectedSpanId} /><div className="traceGrid"><div className="spanList">{savedTrace.spans.map((span, index) => <button className={`spanRow ${selectedSpanId === span.span_id ? "selected" : ""}`} key={span.span_id} onClick={() => setSelectedSpanId(span.span_id)}><span className="step">{index + 1}</span><span><strong>{span.agent}</strong><small>{span.span_type.replaceAll("_", " ")}</small></span></button>)}</div><SpanDetails span={savedTrace.spans.find(span => span.span_id === selectedSpanId) ?? savedTrace.spans[0]} /></div><div className="finalResponse"><small>Final response</small><p>{savedTrace.final_response}</p></div></section>}
      {!result && !savedTrace && !error && <div className="panel">{loading ? "Loading scenarios…" : "No scenarios available."}</div>}
      {result && <>
        <section className="controls panel"><label>Scenario<select value={scenarioId} onChange={event => { setScenarioId(event.target.value); setSelectedSpanId(""); setSavedTrace(null); setSavedGraph(null); setLiveTrace(null); setLiveGraph(null); }}>{payload?.results.map(item => <option key={item.scenario.scenario_id} value={item.scenario.scenario_id}>{item.scenario.scenario_id} · {item.scenario.risk_type.replaceAll("_", " ")}</option>)}</select></label><div><small>Dataset</small><strong>{result.scenario.provenance === "synthetic_candidate_unadjudicated" ? "Synthetic candidate tasks" : "Reference scenarios"} ({payload?.results.length})</strong></div><div><small>Role</small><strong>{result.scenario.user_role}</strong></div><button onClick={() => downloadJson(`${scenarioId}-evaluation.json`, result)}>Export evaluation JSON</button></section>
        <section className="scenario panel"><div><p className="eyebrow">{result.scenario.source_case_study}</p><h2>{result.scenario.risk_type.replaceAll("_", " ")}</h2><p>{result.scenario.prompt}</p></div><div><small>Expected safe behavior</small><p>{result.scenario.expected_safe_behavior}</p></div></section>
        <section className="runGrid"><RunCard title="Baseline · no guards" trace={result.baseline_trace} /><RunCard title="Guarded" trace={result.guarded_trace} /></section>
        <section className="panel" id="runHistory"><div className="sectionHead"><div><p className="eyebrow">DURABLE OBSERVABILITY</p><h2>Saved runs and live stream</h2></div><button className="actionButton" onClick={startStream} disabled={streaming}>Start {mode} stream</button></div><p className="muted">{streamStatus || "Stream the selected scenario, then inspect each span and the stored trace."}{streaming ? ` · ${liveSpans.length} spans received` : ""}</p><div className="historyList">{history.slice(0, 10).map(run => <button key={run.trace_id} onClick={() => void openSaved(run.trace_id)} className={savedTrace?.trace_id === run.trace_id ? "selected" : ""}><strong>{run.scenario_id} · {run.mode}</strong><small>{new Date(run.started_at).toLocaleString()} · {run.adapter}</small></button>)}</div><div className="approvalPanel"><h3>Human approval</h3><p className="muted">For high-risk tool requests. Configure MASGUARDEVAL_APPROVAL_TOKEN on the API and enter it here to review pending decisions. The token stays in this page session.</p><div className="approvalInputs"><input aria-label="Approval token" type="password" autoComplete="off" placeholder="Approval token" value={approvalToken} onChange={event => setApprovalToken(event.target.value)} /><input aria-label="Decision reason" value={approvalReason} onChange={event => setApprovalReason(event.target.value)} /><button onClick={() => void refreshApprovals()} disabled={!approvalToken}>Refresh requests</button></div>{approvals.map(request => <div className="approvalRequest" key={request.request_id}><div><strong>{request.agent} → {request.tool}</strong><small>{request.scenario_id} · {request.trace_id}</small><pre>{JSON.stringify(request.parameters, null, 2)}</pre></div><button onClick={() => void decide(request.request_id, true)}>Approve</button><button className="deny" onClick={() => void decide(request.request_id, false)}>Deny</button></div>)}</div></section>
        <section className="panel" id="liveLog"><div className="sectionHead"><div><p className="eyebrow">REAL-TIME LOGGING</p><h2>Live event log</h2></div><span>{liveSpans.length} events in this stream</span></div><p className="muted">Start a stream above to watch spans arrive. Select any completed run in Saved runs to inspect its full trace.</p><div className="liveLog" role="log" aria-label="Live agent events">{liveSpans.length ? liveSpans.map((span, index) => <div className="liveLogRow" key={span.span_id}><time>{new Date(span.timestamp).toLocaleTimeString()}</time><strong>{index + 1}. {span.agent}</strong><span>{span.span_type.replaceAll("_", " ")}{span.tool ? ` · ${span.tool}` : ""}</span><em className={span.policy_decision === "BLOCK" ? "blocked" : ""}>{span.policy_decision ?? "observed"}</em><small>{span.output ?? span.input ?? "Event recorded"}</small></div>) : <p className="muted">No stream events yet.</p>}</div></section>
        <section className="panel" id="metrics"><div className="sectionHead"><div><p className="eyebrow">EIGHT TRACE METRICS</p><h2>Metric comparison</h2></div><span>N/A means no applicable denominator in this trace</span></div><div className="tableWrap"><table><thead><tr><th>Metric</th><th>Baseline</th><th>Guarded</th><th>Improvement</th><th>Definition</th></tr></thead><tbody>{keys.map(key => { const before = result.baseline_metrics[key]; const after = result.guarded_metrics[key]; return <tr key={key}><td><strong>{key}</strong><small>{before.name}</small></td><td>{score(before)}</td><td>{score(after)}</td><td className={improvement(before, after).startsWith("-") ? "bad" : "good"}>{improvement(before, after)}</td><td className="definition">{before.interpretation}</td></tr>; })}</tbody></table></div><p className="footnote">Improvement is guarded minus baseline for higher-is-better metrics; baseline minus guarded for lower-is-better metrics. Thresholds are reference rules and require external validation.</p></section>
        <section className="panel" id="traces"><div className="sectionHead"><div><p className="eyebrow">OBSERVED EXECUTION</p><h2>Trace explorer</h2></div><div className="segmented"><button className={mode === "baseline" ? "active" : ""} onClick={() => { setMode("baseline"); setSelectedSpanId(""); setSavedTrace(null); setSavedGraph(null); setLiveTrace(null); setLiveGraph(null); }}>Baseline</button><button className={mode === "guarded" ? "active" : ""} onClick={() => { setMode("guarded"); setSelectedSpanId(""); setSavedTrace(null); setSavedGraph(null); setLiveTrace(null); setLiveGraph(null); }}>Guarded</button></div></div>
          {trace && <><div className="traceMeta"><span>Trace: <code>{trace.trace_id}</code></span><span>Started: {new Date(trace.started_at).toLocaleString()}</span><span>Elapsed: {elapsed(trace)}</span><button onClick={() => downloadJson(`${trace.trace_id}.json`, trace)}>Export trace</button></div><h3>Interaction timeline</h3><InteractionTimeline trace={trace} selectedSpanId={selectedSpan?.span_id ?? ""} onSelect={setSelectedSpanId} /><h3>Agent–tool graph</h3><AgentGraph graph={graph} selectedSpanId={selectedSpan?.span_id ?? ""} onSelect={setSelectedSpanId} /><div className="traceGrid"><div className="spanList">{trace.spans.map((span, index) => <button className={`spanRow ${selectedSpan?.span_id === span.span_id ? "selected" : ""}`} key={span.span_id} onClick={() => setSelectedSpanId(span.span_id)}><span className="step">{index + 1}</span><span><strong>{span.agent}</strong><small>{span.span_type.replaceAll("_", " ")}{span.tool ? ` · ${span.tool}` : ""}</small></span><span className={`decision ${span.policy_decision === "BLOCK" ? "blocked" : ""}`}>{span.policy_decision ?? "—"}</span></button>)}</div><SpanDetails span={selectedSpan} /></div><div className="finalResponse"><small>Final response</small><p>{trace.final_response}</p>{trace.stop_reason && <p className="stopReason">Stopped: {trace.stop_reason}</p>}</div></>}
        </section>
        <section className="panel" id="methods"><p className="eyebrow">METHODS</p><h2>What this run establishes</h2><p>The reference adapter emits fixed intents for each scenario. The runner applies the guard stack, executes reached tools in a fresh in-memory workspace, records observed spans, and computes metrics from those spans. Real agent reliability, metric validity, inter-rater agreement, and generalization require independent experiments.</p><div className="guardList"><strong>Active guards</strong>{payload?.guards.map(guard => <span key={guard}>{guard}</span>)}</div></section>
      </>}
      {trace && findings?.trace_id === trace.trace_id && <FindingsPanel report={findings} />}
    </main>
  </div>;
}

function FindingsPanel({ report }: { report: FindingsReport }) {
  return <section className="panel findingsPanel" id="findings"><div className="sectionHead"><div><p className="eyebrow">TRACE FINDINGS REPORT</p><h2>{report.scenario_id} · {report.status.replaceAll("_", " ")}</h2></div><button className="actionButton" onClick={() => downloadJson(`${report.trace_id}-findings.json`, report)}>Download report</button></div><p className="muted">Trace {report.trace_id} · {report.scope}</p><div className="findingStats"><span><strong>{report.summary.executed_tool_calls}</strong> executed tool calls</span><span><strong>{report.summary.guard_interventions}</strong> guard interventions</span><span><strong>{report.summary.high_severity_findings}</strong> high severity trace signals</span></div>{report.findings.length ? <div className="findingList">{report.findings.map((finding, index) => <article className={`finding ${finding.severity}`} key={`${finding.kind}-${index}`}><small>{finding.severity.toUpperCase()} · {finding.kind.replaceAll("_", " ")}</small><h3>{finding.title}</h3><p>{finding.detail}</p><p><strong>Next step:</strong> {finding.next_action}</p><small>Evidence spans: {finding.evidence_span_ids.join(", ")}</small></article>)}</div> : <p>No policy conflict or execution error was recorded in this trace.</p>}<p className="footnote">{report.interpretation}</p></section>;
}

function RunCard({ title, trace }: { title: string; trace: Trace }) {
  const interventions = trace.spans.filter(span => ["BLOCK", "MODIFY", "REQUIRE_APPROVAL"].includes(span.policy_decision ?? "")).length;
  const tools = trace.spans.filter(span => span.span_type === "tool_call").length;
  return <article className="panel runCard"><div className="sectionHead"><h2>{title}</h2><span className={`state ${trace.blocked ? "blocked" : ""}`}>{trace.blocked ? "Stopped by guard" : "Completed"}</span></div><div className="stats"><div><small>Recorded spans</small><strong>{trace.spans.length}</strong></div><div><small>Executed tool calls</small><strong>{tools}</strong></div><div><small>Interventions</small><strong>{interventions}</strong></div><div><small>Measured elapsed</small><strong>{elapsed(trace)}</strong></div></div><p className="responsePreview">{trace.final_response}</p></article>;
}
function SpanDetails({ span }: { span?: Span }) {
  if (!span) return <div className="spanDetails">No spans recorded.</div>;
  return <div className="spanDetails"><p className="eyebrow">SELECTED SPAN</p><h3>{span.agent} · {span.span_type.replaceAll("_", " ")}</h3><dl><dt>Decision</dt><dd>{span.policy_decision ?? "N/A"}</dd><dt>Tool</dt><dd>{span.tool ?? "N/A"}</dd><dt>Measured latency</dt><dd>{span.latency_ms.toFixed(3)} ms</dd><dt>Parent span</dt><dd><code>{span.parent_span_id ?? "None"}</code></dd><dt>Failure label</dt><dd>{span.failure_label ?? "None"}</dd><dt>Input</dt><dd>{span.input ?? "None"}</dd><dt>Output / reason</dt><dd>{span.output ?? "None"}</dd></dl><details><summary>Parameters and metadata</summary><pre>{JSON.stringify({ parameters: span.tool_parameters, metadata: span.metadata }, null, 2)}</pre></details></div>;
}
export default App;
