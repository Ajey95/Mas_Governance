import { useEffect, useMemo, useRef, useState } from "react";
import { apiBase, decideApproval, fetchApprovals, fetchDashboard, fetchRunHistory, fetchSavedFindings, fetchSavedGraph, fetchSavedRun, runLangGraphReference, runNestedGraphProbe } from "./api";
import { AgentGraph } from "./TraceVisuals";
import type { AgentToolGraph, ApprovalRequest, DashboardPayload, EvaluationResult, FindingsReport, MetricKey, MetricResult, RunSummary, Span, Trace } from "./types";

type View = "overview" | "runs" | "trace" | "findings" | "metrics" | "approvals";
type Mode = "baseline" | "guarded";
const metricKeys: MetricKey[] = ["TSP", "TSR", "PHR", "CPI", "CFP", "RSS", "CCR", "DT"];
const lowerIsBetter = new Set<MetricKey>(["PHR", "CPI", "CFP", "CCR", "DT"]);
const viewNames: Record<View, string> = { overview: "Overview", runs: "Runs & live", trace: "Trace", findings: "Findings", metrics: "Metrics", approvals: "Approvals" };

const humanize = (value: string) => value.replaceAll("_", " ");
const formatTime = (value: string) => new Date(value).toLocaleString();
const duration = (trace: Trace) => trace.elapsed_ms === null ? "N/A" : `${trace.elapsed_ms.toFixed(2)} ms`;
const metricValue = (metric: MetricResult) => metric.applicable ? metric.score.toFixed(3) : "N/A";
function delta(before: MetricResult, after: MetricResult) {
  if (!before.applicable || !after.applicable) return null;
  return (after.score - before.score) * (lowerIsBetter.has(before.key) ? -1 : 1);
}
function saveJson(filename: string, value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
function initialView(): View {
  const hash = window.location.hash.replace("#", "");
  if (hash === "liveLog" || hash === "runHistory") return "runs";
  if (hash === "traces") return "trace";
  return hash in viewNames ? hash as View : "overview";
}
function countTools(trace: Trace) { return trace.spans.filter(span => span.span_type === "tool_call").length; }
function countInterventions(trace: Trace) { return trace.spans.filter(span => ["BLOCK", "MODIFY", "REQUIRE_APPROVAL"].includes(span.policy_decision ?? "")).length; }

export default function App() {
  const [view, setView] = useState<View>(initialView);
  const [payload, setPayload] = useState<DashboardPayload | null>(null);
  const [scenarioId, setScenarioId] = useState("");
  const [mode, setMode] = useState<Mode>("guarded");
  const [selectedSpanId, setSelectedSpanId] = useState("");
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [savedTrace, setSavedTrace] = useState<Trace | null>(null);
  const [savedGraph, setSavedGraph] = useState<AgentToolGraph | null>(null);
  const [liveTrace, setLiveTrace] = useState<Trace | null>(null);
  const [liveGraph, setLiveGraph] = useState<AgentToolGraph | null>(null);
  const [liveSpans, setLiveSpans] = useState<Span[]>([]);
  const [findings, setFindings] = useState<FindingsReport | null>(null);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [approvalToken, setApprovalToken] = useState("");
  const [approvalReason, setApprovalReason] = useState("");
  const [signedInEmail, setSignedInEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [graphRunning, setGraphRunning] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const streamRef = useRef<EventSource | null>(null);

  function navigate(next: View) { setView(next); window.history.replaceState(null, "", `#${next}`); window.scrollTo({ top: 0, behavior: "smooth" }); }
  async function refreshHistory() {
    try { setHistory(await fetchRunHistory()); }
    catch { setHistory([]); }
  }
  async function refreshApprovals() {
    if (!approvalToken) return;
    try { setApprovals(await fetchApprovals(approvalToken)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load approvals"); }
  }
  async function load() {
    setLoading(true); setError("");
    try {
      const data = await fetchDashboard();
      setPayload(data);
      setScenarioId(current => data.results.some(item => item.scenario.scenario_id === current) ? current : data.results[0]?.scenario.scenario_id ?? "");
      await refreshHistory();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load evaluations"); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); return () => streamRef.current?.close(); }, []);
  useEffect(() => { void fetch(`${apiBase}/user-session`).then(response => response.ok ? response.json() : null).then(data => { if (data?.enabled) setSignedInEmail(data.email ?? "Account"); }).catch(() => {}); }, []);
  useEffect(() => { if (!streaming || !approvalToken) return; const timer = window.setInterval(() => void refreshApprovals(), 1500); return () => window.clearInterval(timer); }, [streaming, approvalToken]);
  useEffect(() => { const onHash = () => setView(initialView()); window.addEventListener("hashchange", onHash); return () => window.removeEventListener("hashchange", onHash); }, []);

  function clearActiveRun() { setSavedTrace(null); setSavedGraph(null); setLiveTrace(null); setLiveGraph(null); setFindings(null); setSelectedSpanId(""); }
  async function openSaved(id: string) {
    setError("");
    try {
      const [trace, graph, report] = await Promise.all([fetchSavedRun(id), fetchSavedGraph(id), fetchSavedFindings(id)]);
      setSavedTrace(trace); setSavedGraph(graph); setFindings(report); setLiveTrace(null); setLiveGraph(null);
      setScenarioId(trace.scenario_id); setMode(trace.mode); setSelectedSpanId(""); navigate("trace");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load saved run"); }
  }
  function startStream() {
    if (!scenarioId || streaming) return;
    streamRef.current?.close(); clearActiveRun(); setLiveSpans([]); setStreaming(true); setStatus("Connecting to live run…"); setError(""); navigate("runs");
    const source = new EventSource(`${apiBase}/stream/${encodeURIComponent(scenarioId)}?mode=${mode}`);
    streamRef.current = source;
    source.addEventListener("span", event => {
      const span = JSON.parse((event as MessageEvent).data) as Span;
      setLiveSpans(current => [...current, span]); setStatus(`${span.agent} · ${humanize(span.span_type)}`);
    });
    source.addEventListener("complete", event => {
      const completed = JSON.parse((event as MessageEvent).data) as { trace: Trace; findings: FindingsReport };
      setLiveTrace(completed.trace); setFindings(completed.findings); setStreaming(false);
      setStatus(`Run complete · ${completed.trace.spans.length} events`); source.close();
      void fetchSavedGraph(completed.trace.trace_id).then(setLiveGraph).catch(() => {});
      void refreshHistory(); void refreshApprovals();
    });
    source.addEventListener("error", event => {
      let detail = "Connection failed";
      if (event instanceof MessageEvent) { try { detail = JSON.parse(event.data)?.detail ?? detail; } catch { /* malformed stream error */ } }
      setError(detail); setStatus("Run interrupted"); setStreaming(false); source.close();
    });
  }
  async function runGraph(kind: "reference" | "nested" | "blocked") {
    if (graphRunning) return;
    setGraphRunning(true); setError(""); setStatus("Running graph check…"); navigate("runs");
    try {
      const result = kind === "reference" ? await runLangGraphReference() : await runNestedGraphProbe(kind === "blocked");
      await refreshHistory(); await openSaved(result.trace_id);
      setStatus(kind === "reference" ? "Graph reference completed" : kind === "blocked" ? "Blocked branch recorded" : "Nested route recorded");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Graph check failed"); }
    finally { setGraphRunning(false); }
  }
  async function decide(id: string, approve: boolean) {
    try { await decideApproval(id, approvalToken, approve, approvalReason); await refreshApprovals(); setStatus(approve ? "Request approved" : "Request denied"); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not record decision"); }
  }
  async function signOut() { await fetch(`${apiBase}/user-logout`, { method: "POST" }); window.location.replace(`${apiBase}/user-login`); }

  const result = useMemo(() => payload?.results.find(item => item.scenario.scenario_id === scenarioId), [payload, scenarioId]);
  const referenceTrace = result ? mode === "guarded" ? result.guarded_trace : result.baseline_trace : null;
  const partialTrace: Trace | null = streaming && liveSpans.length ? { trace_id: liveSpans[0].trace_id, scenario_id: scenarioId, mode, started_at: liveSpans[0].timestamp, completed_at: null, elapsed_ms: null, stop_reason: null, final_response: "Run in progress", blocked: false, spans: liveSpans, scenario: result?.scenario } : null;
  const trace = savedTrace ?? liveTrace ?? partialTrace ?? referenceTrace;
  const graph = savedTrace ? savedGraph : liveTrace || streaming ? liveGraph : result ? mode === "guarded" ? result.guarded_graph : result.baseline_graph : null;
  const selectedSpan = trace?.spans.find(span => span.span_id === selectedSpanId) ?? trace?.spans[0];
  const isExample = payload?.execution_kind === "isolated_mock_workspace";
  const scenario = result?.scenario ?? trace?.scenario;
  const findingForTrace = findings?.trace_id === trace?.trace_id ? findings : null;

  return <div className="workbench">
    <aside className="rail">
      <div className="brandMark"><span className="brandSymbol" aria-hidden="true">◇</span><span>MASGuardEval<small>Agent behavior workspace</small></span></div>
      <nav aria-label="Workspace sections">{(["overview", "runs", "trace", "findings", "metrics", "approvals"] as View[]).map(item => <button key={item} className={view === item ? "active" : ""} onClick={() => navigate(item)} aria-current={view === item ? "page" : undefined}><NavIcon name={item} />{viewNames[item]}{item === "approvals" && approvals.length > 0 && <span className="navCount">{approvals.length}</span>}</button>)}</nav>
      <div className="railFoot"><span>Local workspace</span><small>Assess · Trace · Explain</small></div>
    </aside>
    <div className="workarea">
      <header className="masthead"><div><p className="pageKicker">MASGuardEval / {viewNames[view]}</p><h1>{view === "overview" ? "Evaluation workspace" : viewNames[view]}</h1><p className="mastDescription">{view === "overview" ? "See where an agent crossed a boundary, where intervention occurred, and what evidence supports the result." : view === "runs" ? "Run a scenario and follow the events as they arrive." : view === "trace" ? "Follow the execution path from request to outcome." : view === "findings" ? "Review observed issues and the spans behind them." : view === "metrics" ? "Compare trace measures for the selected scenario." : "Review tool requests waiting for a person."}</p></div><div className="headerTools">{isExample && <span className="exampleBadge" title="Scripted example data">Example evaluation</span>}<a href={`${apiBase}/docs`} target="_blank" rel="noreferrer">API docs ↗</a>{signedInEmail && <button className="textButton" onClick={() => void signOut()} title={signedInEmail}>Sign out</button>}</div></header>
      {error && <div className="alert" role="alert"><strong>Could not complete the request.</strong> {error} <button onClick={() => setError("")} aria-label="Dismiss error">×</button></div>}
      {status && <div className="statusLine" role="status"><span className={streaming ? "pulse" : ""} />{status}</div>}
      <main>
        {(view === "overview" || view === "runs" || view === "metrics") && <ScenarioBar result={result} payload={payload} scenarioId={scenarioId} onChange={id => { setScenarioId(id); clearActiveRun(); }} onRefresh={() => void load()} loading={loading} />}
        {view === "overview" && (result ? <>
          <div className="promptBand"><div><span className="fieldLabel">Task prompt</span><p>{result.scenario.prompt}</p></div><div><span className="fieldLabel">Expected boundary</span><p>{result.scenario.expected_safe_behavior}</p></div><div className="promptAction"><button className="primaryButton" onClick={startStream} disabled={streaming}>▶ <span>{streaming ? "Running…" : "Run scenario"}</span></button><small>Creates a saved trace</small></div></div>
          <div className="comparison"><OutcomeCard title="Baseline" subtitle="Without intervention" trace={result.baseline_trace} tone="risk" onInspect={() => { setMode("baseline"); clearActiveRun(); navigate("trace"); }} /><div className="comparisonAxis"><span>→</span><small>Compare<br />execution</small></div><OutcomeCard title="Guarded" subtitle="With intervention" trace={result.guarded_trace} tone="safe" onInspect={() => { setMode("guarded"); clearActiveRun(); navigate("trace"); }} /></div>
          <div className="overviewLower"><div className="overviewEvidence"><div className="sectionHeading"><div><span className="fieldLabel">Execution evidence</span><h2>Follow the decision path</h2></div><button className="inlineLink" onClick={() => navigate("trace")}>Open trace →</button></div><div className="quickPath">{result.guarded_trace.spans.filter(span => ["agent_step", "tool_call", "blocked_tool_attempt", "approval_required", "final_response"].includes(span.span_type) || ["BLOCK", "REQUIRE_APPROVAL"].includes(span.policy_decision ?? "")).slice(0, 7).map((span, index) => <button key={span.span_id} onClick={() => { setMode("guarded"); setSelectedSpanId(span.span_id); navigate("trace"); }}><span className="pathIndex">{String(index + 1).padStart(2, "0")}</span><strong>{span.agent}</strong><span>{span.tool ? humanize(span.tool) : humanize(span.span_type)}</span><Decision value={span.policy_decision} /></button>)}</div></div><div className="insightRail"><span className="fieldLabel">At a glance</span><h3>{result.guarded_trace.blocked ? "Execution stopped at a boundary" : "Guarded run completed"}</h3><p>{result.guarded_trace.stop_reason ?? result.guarded_trace.final_response}</p><div className="hairline" /><strong>Inspect the evidence</strong><p>Open the trace to see the selected event, its parent, decision, and tool parameters.</p><button className="secondaryButton" onClick={() => navigate("trace")}>View trace →</button><div className="hairline" /><button className="inlineLink" onClick={() => navigate("metrics")}>Compare eight measures →</button></div></div>
        </> : <EmptyState loading={loading} error={error} />)}
        {view === "runs" && <div className="runsLayout"><section className="surface"><div className="sectionHeading"><div><span className="fieldLabel">New run</span><h2>Watch a scenario</h2></div></div><p className="sectionIntro">Stream the selected task and inspect each event as it is recorded.</p><div className="runControls"><div className="modeSwitch" aria-label="Run mode"><button className={mode === "guarded" ? "active" : ""} onClick={() => setMode("guarded")}>Guarded</button><button className={mode === "baseline" ? "active" : ""} onClick={() => setMode("baseline")}>Baseline</button></div><button className="primaryButton" onClick={startStream} disabled={streaming || !scenarioId}>{streaming ? "Running…" : "Start live run"}</button></div><div className="liveList" role="log" aria-label="Live events">{liveSpans.length ? liveSpans.map((span, index) => <button key={span.span_id} onClick={() => { setSelectedSpanId(span.span_id); navigate("trace"); }}><time>{new Date(span.timestamp).toLocaleTimeString()}</time><span className="pathIndex">{String(index + 1).padStart(2, "0")}</span><strong>{span.agent}</strong><span>{humanize(span.span_type)}{span.tool ? ` · ${humanize(span.tool)}` : ""}</span><Decision value={span.policy_decision} /></button>) : <div className="blankState">Live events will appear here when a run starts.</div>}</div></section><aside className="runsSide"><section className="surface"><div className="sectionHeading"><div><span className="fieldLabel">History</span><h2>Saved runs</h2></div><button className="inlineLink" onClick={() => void refreshHistory()}>Refresh</button></div><div className="savedRuns">{history.length ? history.map(run => <button key={run.trace_id} onClick={() => void openSaved(run.trace_id)}><span className={`runDot ${run.blocked ? "halted" : ""}`} /><span><strong>{humanize(run.scenario_id)}</strong><small>{formatTime(run.started_at)} · {run.mode} · {humanize(run.adapter)}</small></span><span aria-hidden="true">→</span></button>) : <p className="blankState">No saved runs yet.</p>}</div></section><section className="surface graphChecks"><span className="fieldLabel">Graph checks</span><h2>Inspect complex routes</h2><p>Run the graph examples to inspect transitions, nested branches, and a blocked route.</p><div><button onClick={() => void runGraph("reference")} disabled={graphRunning}>Graph reference →</button><button onClick={() => void runGraph("nested")} disabled={graphRunning}>Nested route →</button><button onClick={() => void runGraph("blocked")} disabled={graphRunning}>Blocked branch →</button></div>{isExample && <small>These checks use example tasks.</small>}</section></aside></div>}
        {view === "trace" && (trace ? <TraceView trace={trace} graph={graph} selectedSpan={selectedSpan} onSelect={setSelectedSpanId} mode={mode} setMode={next => { setMode(next); clearActiveRun(); }} isSaved={Boolean(savedTrace || liveTrace)} isLive={streaming} onExport={() => saveJson(`${trace.trace_id}.json`, trace)} /> : <EmptyState loading={loading} error={error} />)}
        {view === "findings" && (findingForTrace ? <FindingsView report={findingForTrace} onSelectSpan={id => { setSelectedSpanId(id); navigate("trace"); }} /> : <div className="surface emptyContent"><h2>No report for this trace yet</h2><p>Open a saved run or start a live run to see its findings report.</p><button className="secondaryButton" onClick={() => navigate("runs")}>Go to runs →</button></div>)}
        {view === "metrics" && (result ? <MetricsView result={result} /> : <EmptyState loading={loading} error={error} />)}
        {view === "approvals" && <section className="surface approvalsView"><div className="sectionHeading"><div><span className="fieldLabel">Human decision</span><h2>Pending tool requests</h2></div><span className="countLabel">{approvals.length} pending</span></div><p className="sectionIntro">Requests that need a person’s decision appear here when approval is enabled for this workspace.</p><div className="approvalInputs"><label>Access token<input type="password" autoComplete="off" value={approvalToken} onChange={event => setApprovalToken(event.target.value)} /></label><label>Decision reason<input value={approvalReason} onChange={event => setApprovalReason(event.target.value)} placeholder="Reason for this decision" /></label><button className="secondaryButton" onClick={() => void refreshApprovals()} disabled={!approvalToken}>Load requests</button></div>{approvals.length ? approvals.map(request => <article className="approvalItem" key={request.request_id}><div><span className="fieldLabel">{request.scenario_id}</span><h3>{request.agent} → {request.tool ?? "Tool request"}</h3><pre>{JSON.stringify(request.parameters, null, 2)}</pre></div><div><button className="secondaryButton" onClick={() => void decide(request.request_id, false)}>Deny</button><button className="primaryButton" onClick={() => void decide(request.request_id, true)}>Approve</button></div></article>) : <div className="blankState">{approvalToken ? "No requests waiting for review." : "Enter your access token to load requests."}</div>}</section>}
      </main>
    </div>
  </div>;
}

function NavIcon({ name }: { name: View }) {
  const paths: Record<View, React.ReactNode> = {
    overview: <><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /></>,
    runs: <><path d="m7 4 13 8-13 8z" /></>, trace: <><circle cx="5" cy="4" r="2" /><circle cx="19" cy="12" r="2" /><circle cx="5" cy="20" r="2" /><path d="M5 6v12M7 4h4a4 4 0 0 1 4 4v2M7 20h4a4 4 0 0 0 4-4v-2" /></>,
    findings: <><path d="M5 3h10l4 4v14H5zM15 3v5h4M8 12h8M8 16h6" /></>, metrics: <><path d="M4 19V5M4 19h17M8 15l4-5 3 2 5-7" /></>, approvals: <><path d="M12 3 4 6v6c0 5 3 8 8 10 5-2 8-5 8-10V6zM9 12l2 2 4-4" /></>
  };
  return <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
function Decision({ value }: { value: string | null }) { return value ? <span className={`decisionTag ${value.toLowerCase()}`}>{humanize(value)}</span> : null; }
function EmptyState({ loading, error }: { loading: boolean; error: string }) { return <div className="surface emptyContent"><h2>{loading ? "Loading evaluations…" : error ? "Evaluation unavailable" : "No scenarios available"}</h2><p>{loading ? "Preparing the workspace." : error ? "Check the API connection, then refresh." : "Add scenarios and refresh to begin."}</p></div>; }
function ScenarioBar({ result, payload, scenarioId, onChange, onRefresh, loading }: { result?: EvaluationResult; payload: DashboardPayload | null; scenarioId: string; onChange: (id: string) => void; onRefresh: () => void; loading: boolean }) {
  return <div className="scenarioBar"><label><span className="fieldLabel">Scenario</span><select value={scenarioId} onChange={event => onChange(event.target.value)} disabled={!payload?.results.length}>{payload?.results.map(item => <option key={item.scenario.scenario_id} value={item.scenario.scenario_id}>{humanize(item.scenario.risk_type)} · {item.scenario.scenario_id}</option>)}</select></label><div className="scenarioContext"><span className="fieldLabel">Case</span><strong>{result?.scenario.source_case_study ? humanize(result.scenario.source_case_study) : "—"}</strong></div><div className="scenarioContext"><span className="fieldLabel">Requester role</span><strong>{result ? humanize(result.scenario.user_role) : "—"}</strong></div><button className="quietButton" onClick={onRefresh} disabled={loading}>{loading ? "Refreshing…" : "Refresh comparison ↻"}</button></div>;
}
function OutcomeCard({ title, subtitle, trace, tone, onInspect }: { title: string; subtitle: string; trace: Trace; tone: "risk" | "safe"; onInspect: () => void }) {
  return <article className={`outcome ${tone}`}><div className="outcomeHead"><div><span className="fieldLabel">{subtitle}</span><h2>{title}</h2></div><span className={`outcomeState ${trace.blocked ? "stopped" : "completed"}`}>{trace.blocked ? "Stopped" : "Completed"}</span></div><div className="outcomeNumbers"><div><strong>{trace.spans.length}</strong><span>events</span></div><div><strong>{countTools(trace)}</strong><span>tool calls</span></div><div><strong>{countInterventions(trace)}</strong><span>interventions</span></div><div><strong>{duration(trace)}</strong><span>elapsed</span></div></div><div className="outcomeResponse"><span className="fieldLabel">Final response</span><p>{trace.final_response}</p></div><button className="inlineLink" onClick={onInspect}>Inspect {title.toLowerCase()} trace →</button></article>;
}
function TraceView({ trace, graph, selectedSpan, onSelect, mode, setMode, isSaved, isLive, onExport }: { trace: Trace; graph: AgentToolGraph | null; selectedSpan?: Span; onSelect: (id: string) => void; mode: Mode; setMode: (mode: Mode) => void; isSaved: boolean; isLive: boolean; onExport: () => void }) {
  const graphRich = Boolean(graph?.nodes.some(node => node.kind === "graph_node"));
  const [traceTab, setTraceTab] = useState<"events" | "graph">(graphRich ? "graph" : "events");
  const [eventFilter, setEventFilter] = useState<"all" | "actions" | "graph" | "interventions">("all");
  useEffect(() => { setTraceTab(graphRich ? "graph" : "events"); setEventFilter("all"); }, [trace.trace_id]);
  const shown = trace.spans.map((span, index) => ({ span, index })).filter(({ span }) => eventFilter === "all" || eventFilter === "actions" && ["agent_step", "tool_call", "blocked_tool_attempt", "final_response", "inter_agent_message"].includes(span.span_type) || eventFilter === "graph" && span.span_type.startsWith("graph_") || eventFilter === "interventions" && ["BLOCK", "MODIFY", "REQUIRE_APPROVAL"].includes(span.policy_decision ?? ""));
  return <div className="tracePage"><div className="traceToolbar"><div><span className="fieldLabel">{isLive ? "Live run" : isSaved ? "Saved run" : "Scenario comparison"}</span><h2>{humanize(trace.scenario?.risk_type ?? trace.scenario_id)}</h2><p>{formatTime(trace.started_at)} · {trace.spans.length} events · {duration(trace)}</p></div><div className="traceActions">{!isSaved && !isLive && <div className="modeSwitch"><button className={mode === "baseline" ? "active" : ""} onClick={() => setMode("baseline")}>Baseline</button><button className={mode === "guarded" ? "active" : ""} onClick={() => setMode("guarded")}>Guarded</button></div>}<button className="secondaryButton" onClick={onExport}>Export trace ↓</button></div></div><div className="traceTabs" role="tablist" aria-label="Trace view"><button role="tab" aria-selected={traceTab === "events"} className={traceTab === "events" ? "active" : ""} onClick={() => setTraceTab("events")}>Events</button><button role="tab" aria-selected={traceTab === "graph"} className={traceTab === "graph" ? "active" : ""} onClick={() => setTraceTab("graph")}>Agent graph</button></div><div className="traceContent"><div className="tracePrimary">{traceTab === "events" ? <><div className="eventFilter"><label>Show <select value={eventFilter} onChange={event => setEventFilter(event.target.value as typeof eventFilter)}><option value="all">All events</option><option value="actions">Agent & tool actions</option><option value="graph">Graph activity</option><option value="interventions">Interventions</option></select></label><span>{shown.length} of {trace.spans.length}</span></div><div className="eventList">{shown.length ? shown.map(({ span, index }) => <button key={span.span_id} className={span.span_id === selectedSpan?.span_id ? "selected" : ""} onClick={() => onSelect(span.span_id)}><span className="eventRail"><i />{String(index + 1).padStart(2, "0")}</span><span className="eventBody"><strong>{span.agent}</strong><small>{humanize(span.span_type)}{span.tool ? ` · ${humanize(span.tool)}` : ""}</small></span><Decision value={span.policy_decision} /><time>{span.latency_ms.toFixed(2)} ms</time></button>) : <p className="blankState">No events match this view.</p>}</div></> : <AgentGraph graph={graph} selectedSpanId={selectedSpan?.span_id ?? ""} onSelect={onSelect} />}</div><aside className="inspector"><span className="fieldLabel">Selected event</span>{selectedSpan ? <><h3>{selectedSpan.agent}</h3><p>{humanize(selectedSpan.span_type)}{selectedSpan.tool ? ` · ${humanize(selectedSpan.tool)}` : ""}</p><Decision value={selectedSpan.policy_decision} /><dl><dt>Time</dt><dd>{formatTime(selectedSpan.timestamp)}</dd><dt>Parent event</dt><dd>{selectedSpan.parent_span_id ?? "None"}</dd><dt>Input</dt><dd>{selectedSpan.input ?? "None"}</dd><dt>Output / reason</dt><dd>{selectedSpan.output ?? "None"}</dd>{selectedSpan.failure_label && <><dt>Failure label</dt><dd>{selectedSpan.failure_label}</dd></>}</dl><details><summary>Tool parameters and event metadata</summary><pre>{JSON.stringify({ parameters: selectedSpan.tool_parameters, metadata: selectedSpan.metadata }, null, 2)}</pre></details></> : <p>No events recorded.</p>}<div className="hairline" /><span className="fieldLabel">Outcome</span><p>{trace.final_response}</p>{trace.stop_reason && <p className="stoppedText">Stopped: {trace.stop_reason}</p>}<small className="traceId">Trace {trace.trace_id}</small></aside></div></div>;
}
function FindingsView({ report, onSelectSpan }: { report: FindingsReport; onSelectSpan: (id: string) => void }) {
  return <div className="findingsView"><div className="reportHeader"><div><span className="fieldLabel">Run report</span><h2>{humanize(report.scenario_id)}</h2><p>{humanize(report.status)} · {report.scope}</p></div><button className="secondaryButton" onClick={() => saveJson(`${report.trace_id}-findings.json`, report)}>Download report ↓</button></div><div className="reportNumbers"><div><strong>{report.summary.executed_tool_calls}</strong><span>executed tool calls</span></div><div><strong>{report.summary.guard_interventions}</strong><span>interventions</span></div><div><strong>{report.summary.high_severity_findings}</strong><span>high severity signals</span></div></div>{report.findings.length ? <div className="findingList">{report.findings.map((finding, index) => <article className={`findingItem ${finding.severity}`} key={`${finding.kind}-${index}`}><span className="fieldLabel">{finding.severity} · {humanize(finding.kind)}</span><h3>{finding.title}</h3><p>{finding.detail}</p><div className="findingAction"><strong>Next step</strong><p>{finding.next_action}</p></div>{finding.evidence_span_ids.length > 0 && <div className="evidenceLinks"><span>Evidence events</span>{finding.evidence_span_ids.map(id => <button key={id} onClick={() => onSelectSpan(id)}>{id.slice(0, 10)}… →</button>)}</div>}</article>)}</div> : <div className="surface emptyContent"><h3>No issue recorded in this trace</h3><p>The report did not identify a policy conflict or execution error.</p></div>}<p className="reportNote">{report.interpretation}</p></div>;
}
function MetricsView({ result }: { result: EvaluationResult }) {
  return <div className="metricsView"><div className="reportHeader"><div><span className="fieldLabel">Scenario comparison</span><h2>Eight trace measures</h2><p>Values are calculated from the selected baseline and guarded traces. N/A means this trace has no applicable denominator.</p></div><button className="secondaryButton" onClick={() => saveJson(`${result.scenario.scenario_id}-evaluation.json`, result)}>Export evaluation ↓</button></div><div className="metricTableWrap"><table><thead><tr><th>Measure</th><th>Baseline</th><th>Guarded</th><th>Change</th><th>What it measures</th></tr></thead><tbody>{metricKeys.map(key => { const before = result.baseline_metrics[key]; const after = result.guarded_metrics[key]; const change = delta(before, after); return <tr key={key}><td><strong>{key}</strong><small>{before.name}</small></td><td>{metricValue(before)}</td><td>{metricValue(after)}</td><td className={change === null ? "" : change < 0 ? "negative" : "positive"}>{change === null ? "N/A" : `${change >= 0 ? "+" : ""}${change.toFixed(3)}`}</td><td>{before.interpretation}</td></tr>; })}</tbody></table></div><p className="reportNote">A positive change points in the intended direction for the metric. These are trace measures from the selected scenario, not a population estimate.</p></div>;
}
