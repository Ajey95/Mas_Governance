import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { fetchDashboard } from "./api";
import type { DashboardPayload, EvaluationResult, MetricKey, MetricResult, Span, Trace } from "./types";

const metricOrder: MetricKey[] = ["TSP", "TSR", "PHR", "CPI", "CFP", "RSS", "CCR", "DT"];
const riskMetrics = new Set<MetricKey>(["PHR", "CPI", "CFP", "CCR", "DT"]);
const apiBase = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

const metricSubtitles: Record<MetricKey, string> = {
  TSP: "Task Success\nProbability",
  TSR: "Task Success\nRate",
  PHR: "Policy Hit\nRate",
  CPI: "Compliance\nPass Rate",
  CFP: "Caution Flag\nPrecision",
  RSS: "Risk\nSeverity Score",
  CCR: "Critical Concern\nRate",
  DT: "Decision\nTimeliness (s)",
};

const metricDescriptions: Record<MetricKey, string> = {
  TSP: "Probability that the multi-agent system completes the user's task successfully. Higher is better. Measured across both baseline and guarded runs.",
  TSR: "Binary success rate across evaluation scenarios. Higher indicates more consistent task completion. Complements TSP with a hard pass/fail view.",
  PHR: "Fraction of agent steps that triggered a policy violation. Lower is better. Measures how often guardrails flag risky behavior.",
  CPI: "Percentage of agent outputs that pass all compliance checks. Higher means the system stays within regulatory/policy boundaries more often.",
  CFP: "Precision of caution flags raised by the system. Higher means fewer false alarms - the system only flags genuinely risky actions.",
  RSS: "Aggregate risk severity across all dimensions (harmfulness, privacy, compliance, fairness, robustness). Lower is better.",
  CCR: "Rate of critical-level concerns detected during evaluation. Lower is better. Tracks the most severe policy violations.",
  DT: "Average time (seconds) for the system to reach a decision. Lower indicates faster response. Measures latency impact of guard checks.",
};

const emptyPayload: DashboardPayload = {
  dataset: { scenarios: [] },
  results: [],
  summary: { scenario_count: 0, metrics: {} as DashboardPayload["summary"]["metrics"] },
  adapter: "not_connected",
  guards: [],
};

/* Custom Hooks */

/** Click-outside hook for closing dropdowns/popovers */
function useClickOutside(ref: React.RefObject<HTMLElement | null>, handler: () => void) {
  useEffect(() => {
    const listener = (e: MouseEvent | TouchEvent) => {
      if (!ref.current || ref.current.contains(e.target as Node)) return;
      handler();
    };
    document.addEventListener("mousedown", listener);
    document.addEventListener("touchstart", listener);
    return () => {
      document.removeEventListener("mousedown", listener);
      document.removeEventListener("touchstart", listener);
    };
  }, [ref, handler]);
}

/* App Root */

function App() {
  const [payload, setPayload] = useState<DashboardPayload>(emptyPayload);
  const [selectedId, setSelectedId] = useState("");
  const [viewMode, setViewMode] = useState<"comparison" | "single">("comparison");
  const [timelineView, setTimelineView] = useState("Timeline");
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [activeSection, setActiveSection] = useState("scenarios");
  const manualNavUntil = useRef(0);
  const mainRef = useRef<HTMLElement>(null);

  const load = async () => {
    setStatus("loading");
    try {
      const data = await fetchDashboard();
      setPayload(data);
      setSelectedId((current) => current || data.results[0]?.scenario.scenario_id || "");
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const selected = useMemo(
    () => payload.results.find((result) => result.scenario.scenario_id === selectedId) ?? payload.results[0],
    [payload.results, selectedId],
  );

  // Scroll-spy: track which section is visible in mainCanvas
  useEffect(() => {
    const sectionIds = ["scenarios", "traces", "metrics", "guards", "reports"];
    const sections = sectionIds
      .map((id) => document.getElementById(id))
      .filter(Boolean) as HTMLElement[];
    if (!sections.length) return undefined;

    const scrollContainer = mainRef.current;
    if (!scrollContainer) return undefined;

    const handleScroll = () => {
      if (Date.now() < manualNavUntil.current) return;

      const scrollTop = scrollContainer.scrollTop;
      const scrollHeight = scrollContainer.scrollHeight;
      const clientHeight = scrollContainer.clientHeight;
      
      // If we are at the bottom of the page, select the last section
      if (Math.ceil(scrollTop + clientHeight) >= scrollHeight - 20) {
         setActiveSection(sectionIds[sectionIds.length - 1]);
         return;
      }

      let current = sectionIds[0];
      for (const section of sections) {
        if (section.offsetTop <= scrollTop + clientHeight * 0.4) {
          current = section.id;
        }
      }
      setActiveSection(current);
    };

    scrollContainer.addEventListener("scroll", handleScroll, { passive: true });
    window.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll(); // initial
    return () => {
      scrollContainer.removeEventListener("scroll", handleScroll);
      window.removeEventListener("scroll", handleScroll);
    };
  }, [selected?.scenario.scenario_id]);

  const setSectionFromNav = (section: string) => {
    manualNavUntil.current = Date.now() + 1200;
    setActiveSection(section);
  };

  return (
    <div className="appFrame">
      <Sidebar activeSection={activeSection} setActiveSection={setSectionFromNav} />
      <main className="mainCanvas" ref={mainRef}>
        <Header status={status} onRefresh={load} />
        {selected ? (
          <>
            <ScenarioBar
              payload={payload}
              selected={selected}
              selectedId={selected.scenario.scenario_id}
              onSelect={setSelectedId}
              onRun={load}
              viewMode={viewMode}
              setViewMode={setViewMode}
              activeSection={activeSection}
            />
            <RunMeta result={selected} guardCount={payload.guards.length} />
            <Comparison result={selected} viewMode={viewMode} />
            <MetricStrip result={selected} activeSection={activeSection} />
            <section className="lowerGrid">
              <TraceTimeline result={selected} timelineView={timelineView} setTimelineView={setTimelineView} activeSection={activeSection} />
              <RiskReduction result={selected} activeSection={activeSection} />
            </section>
            <RecentTraces result={selected} activeSection={activeSection} />
          </>
        ) : (
          <div className="emptyPanel">Start the backend API to load MASGuardEval scenarios.</div>
        )}
      </main>
    </div>
  );
}

function Sidebar({
  activeSection,
  setActiveSection,
}: {
  activeSection: string;
  setActiveSection: (section: string) => void;
}) {
  const [wsOpen, setWsOpen] = useState(false);
  const [envOpen, setEnvOpen] = useState(false);
  const [workspace, setWorkspace] = useState("SafetyLab");
  const [environment, setEnvironment] = useState("prod");
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);
  useClickOutside(profileRef, () => setProfileOpen(false));

  const nav = [
    { label: "Scenarios", icon: "scenario", target: "scenarios" },
    { label: "Traces", icon: "traces", target: "traces" },
    { label: "Metrics", icon: "metrics", target: "metrics" },
    { label: "Guards", icon: "guard", target: "guards" },
    { label: "Reports", icon: "reports", target: "reports" },
  ];

  const goToSection = (target: string) => {
    setActiveSection(target);
    document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <aside className="sideRail">
      <div className="sideBrand">
        <ShieldIcon />
        <strong>MASGuardEval</strong>
      </div>
      <nav className="sideNav">
        {nav.map((item) => (
          <button
            className={activeSection === item.target ? "sideNavItem active" : "sideNavItem"}
            key={item.target}
            type="button"
            onClick={() => goToSection(item.target)}
          >
            <span><Icon name={item.icon} /></span>
            {item.label}
          </button>
        ))}
      </nav>
      <div className="sideBottom">
        <DropdownSelect
          label="Workspace"
          value={workspace}
          open={wsOpen}
          onToggle={() => { setWsOpen(!wsOpen); setEnvOpen(false); }}
          onClose={() => setWsOpen(false)}
          options={["SafetyLab", "GovernanceHub", "ComplianceTest", "RiskOps"]}
          onSelect={(v) => { setWorkspace(v); setWsOpen(false); }}
        />
        <DropdownSelect
          label="Environment"
          value={environment}
          open={envOpen}
          onToggle={() => { setEnvOpen(!envOpen); setWsOpen(false); }}
          onClose={() => setEnvOpen(false)}
          options={["prod", "staging", "dev"]}
          onSelect={(v) => { setEnvironment(v); setEnvOpen(false); }}
          badge
        />
        <div className="profileRow" ref={profileRef} onClick={() => setProfileOpen(!profileOpen)}>
          <span className="avatar">AD</span>
          <div>
            <strong>A. Developer</strong>
            <small>admin</small>
          </div>
          <span className="chevron"><Icon name="chevron" /></span>
          {profileOpen && (
            <div className="rowDropdown" style={{ bottom: "100%", top: "auto", left: 0, width: "100%", marginBottom: "8px" }}>
              <button type="button" onClick={(e) => { e.stopPropagation(); setProfileOpen(false); }}><Icon name="info" /> Settings</button>
              <button type="button" onClick={(e) => { e.stopPropagation(); setProfileOpen(false); }}><Icon name="refresh" /> Log out</button>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

function DropdownSelect({
  label,
  value,
  open,
  onToggle,
  onClose,
  options,
  onSelect,
  badge,
}: {
  label: string;
  value: string;
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  options: string[];
  onSelect: (value: string) => void;
  badge?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, onClose);

  return (
    <div className="selectBox" ref={ref} onClick={onToggle} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onToggle()}>
      <small>{label}</small>
      <div className="selectBoxValue">
        <strong>{value}</strong>
        {badge && <span className="badgePill">{value}</span>}
        <span className={`selectChevron ${open ? "open" : ""}`}><Icon name="chevron" /></span>
      </div>
      {open && (
        <div className="dropdownMenu">
          {options.map((opt) => (
            <button
              key={opt}
              type="button"
              className={`dropdownItem ${opt === value ? "active" : ""}`}
              onClick={(e) => { e.stopPropagation(); onSelect(opt); }}
            >
              {opt}
              {opt === value && <Icon name="checkCircle" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Header({
  status,
  onRefresh,
}: {
  status: string;
  onRefresh: () => void;
}) {
  return (
    <header className="topHeader">
      <h1>Scenario Evaluation</h1>
      <div className="topActions">
        <button type="button" onClick={() => window.open(`${apiBase}/docs`, "_blank")}><Icon name="code" /> API</button>
        <button type="button" onClick={() => window.open(`${apiBase}/project-docs`, "_blank")}><Icon name="book" /> Docs</button>
        <button type="button" onClick={onRefresh}><Icon name="refresh" /> Refresh</button>
        {status === "error" && <span className="riskText">API offline</span>}
      </div>
    </header>
  );
}

/* Scenario Bar */

function ScenarioBar({
  payload,
  selected,
  selectedId,
  onSelect,
  onRun,
  viewMode,
  setViewMode,
  activeSection,
}: {
  payload: DashboardPayload;
  selected: EvaluationResult;
  selectedId: string;
  onSelect: (id: string) => void;
  onRun: () => void;
  viewMode: "comparison" | "single";
  setViewMode: (mode: "comparison" | "single") => void;
  activeSection: string;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    const id = runId(selected, "guarded");
    void navigator.clipboard?.writeText(id).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <section className={`scenarioControls ${activeSection === "scenarios" ? "activeHighlight" : ""}`.trim()} id="scenarios">
      <LabeledSelect label="Scenario" value={selectedId} onChange={onSelect}>
        {payload.results.map((result) => (
          <option key={result.scenario.scenario_id} value={result.scenario.scenario_id}>
            {result.scenario.scenario_id} {formatRisk(result.scenario.risk_type)}
          </option>
        ))}
      </LabeledSelect>
      <LabeledSelect label="Dataset" value="reference" onChange={() => undefined}>
        <option value="reference">FinancialBench v1.2</option>
      </LabeledSelect>
      <div className="inputCard">
        <label>Run ID</label>
        <div>
          <span>{runId(selected, "guarded")}</span>
          <button
            type="button"
            className={copied ? "copyBtn copied" : "copyBtn"}
            onClick={handleCopy}
            title={copied ? "Copied!" : "Copy to clipboard"}
          >
            <Icon name={copied ? "checkCircle" : "copy"} />
          </button>
        </div>
      </div>
      <div className="viewToggleInline">
        <span className="viewLabel">View</span>
        <div className="viewToggle">
          <button className={viewMode === "comparison" ? "selected" : ""} type="button" onClick={() => setViewMode("comparison")}>
            Comparison
          </button>
          <button className={viewMode === "single" ? "selected" : ""} type="button" onClick={() => setViewMode("single")}>
            Single
          </button>
        </div>
      </div>
      <button className="runButton headerRun" type="button" onClick={onRun}>
        <Icon name="play" /> Run Evaluation
      </button>
    </section>
  );
}

/* Run Meta */

function RunMeta({ result, guardCount }: { result: EvaluationResult; guardCount: number }) {
  const agents = Math.max(4, uniqueAgents(result.guarded_trace).length);
  const tools = Math.max(6, uniqueTools(result).length);
  const guards = Math.max(7, guardCount);
  return (
    <section className="runMeta">
      <span><Icon name="agents" /> Agents <strong>{agents}</strong></span>
      <span><Icon name="tools" /> Tools <strong>{tools}</strong></span>
      <span><Icon name="guard" /> Guards <strong>{guards}</strong></span>
      <span><Icon name="steps" /> Max Steps <strong>40</strong></span>
      <span><Icon name="temperature" /> Temperature <strong>0.2</strong></span>
      <span className="metaRight">Started <strong>{formatDate(result.guarded_trace.started_at)}</strong></span>
      <span className="statusPill complete"><span className="statusDot" />Completed</span>
      <span>Duration <strong>{duration(result.guarded_trace)}</strong></span>
    </section>
  );
}

function Comparison({ result, viewMode }: { result: EvaluationResult; viewMode: "comparison" | "single" }) {
  const isSingle = viewMode === "single";
  return (
    <section className={`comparisonGrid ${isSingle ? "single" : ""}`.trim()}>
      {!isSingle && <RunCard title="Baseline (No Guards)" mode="baseline" trace={result.baseline_trace} metrics={result.baseline_metrics} />}
      {!isSingle && <span className="vsBadge">VS</span>}
      <RunCard title="Guarded (MASGuardEval)" mode="guarded" trace={result.guarded_trace} metrics={result.guarded_metrics} />
    </section>
  );
}

function RunCard({
  title,
  mode,
  trace,
  metrics,
}: {
  title: string;
  mode: "baseline" | "guarded";
  trace: Trace;
  metrics: Record<MetricKey, MetricResult>;
}) {
  const risk = riskScore(metrics);
  const interventions = trace.spans.filter((span) => ["BLOCK", "MODIFY", "REQUIRE_APPROVAL"].includes(span.policy_decision || "")).length;
  const policyHits = trace.spans.filter((span) => span.span_type === "guard_decision").length;
  return (
    <article className="runCard">
      <div className="runTitle">
        <div className={mode === "guarded" ? "miniShield guarded" : "miniShield"}>
          <Icon name={mode === "guarded" ? "guard" : "shield"} />
        </div>
        <div>
          <h2>{title}</h2>
          <p>Run ID: {runIdFromTrace(trace)}</p>
        </div>
        <span className={mode === "guarded" ? "riskBadge low" : "riskBadge high"}>{mode === "guarded" ? "LOW RISK" : "HIGH RISK"}</span>
      </div>
      <div className="runStats">
        <Stat label="Risk Score (RSS)" value={risk.toFixed(2)} tone={mode === "guarded" ? "safe" : "risk"} large />
        <Stat label="Total Steps" value={String(trace.spans.length)} />
        <Stat label="Policy Hits" value={String(policyHits)} />
        <Stat label="Guard Interventions" value={String(interventions)} />
      </div>
    </article>
  );
}

/* Metric Strip */

function MetricStrip({ result, activeSection }: { result: EvaluationResult; activeSection: string }) {
  return (
    <section className={`metricStrip ${activeSection === "metrics" ? "activeHighlight" : ""}`.trim()} id="metrics">
      {metricOrder.map((key) => (
        <MetricCard key={key} metricKey={key} baseline={result.baseline_metrics[key]} guarded={result.guarded_metrics[key]} />
      ))}
    </section>
  );
}

function MetricCard({ metricKey, baseline, guarded }: { metricKey: MetricKey; baseline: MetricResult; guarded: MetricResult }) {
  const [showInfo, setShowInfo] = useState(false);
  const infoRef = useRef<HTMLDivElement>(null);
  const closeInfo = useCallback(() => setShowInfo(false), []);
  useClickOutside(infoRef, closeInfo);

  const isRisk = riskMetrics.has(metricKey);
  const bVal = baseline.score;
  const gVal = guarded.score;

  const delta = isRisk ? bVal - gVal : gVal - bVal;
  const improved = delta >= 0;

  let deltaText: string;
  if (["PHR", "CPI", "CCR"].includes(metricKey)) {
    deltaText = `${Math.abs(delta * 100).toFixed(1)} pp`;
  } else if (metricKey === "DT") {
    deltaText = `${Math.abs(delta * 10).toFixed(2)}`;
  } else {
    deltaText = `${Math.abs(delta * 100).toFixed(1)}%`;
  }

  return (
    <article className="metricBox" ref={infoRef}>
      <div className="metricHead">
        <strong>{metricKey}</strong>
        <button
          type="button"
          className="metricInfoBtn"
          onClick={() => setShowInfo(!showInfo)}
          aria-label={`Info about ${metricKey}`}
          title={`About ${metricSubtitles[metricKey].replace("\n", " ")}`}
        >
          <Icon name="info" />
        </button>
      </div>
      {showInfo && (
        <div className="metricTooltip">
          <div className="metricTooltipHeader">
            <strong>{metricKey} - {metricSubtitles[metricKey].replace("\n", " ")}</strong>
            <button type="button" onClick={() => setShowInfo(false)} className="tooltipClose">&times;</button>
          </div>
          <p>{metricDescriptions[metricKey]}</p>
          <div className="tooltipDetails">
            <span>Threshold: <strong>{baseline.threshold.toFixed(2)}</strong></span>
            <span>Status: <strong className={baseline.passed && guarded.passed ? "safeText" : "riskText"}>{guarded.passed ? "PASSED" : "FAILED"}</strong></span>
          </div>
        </div>
      )}
      <p className="metricSubtitle">{metricSubtitles[metricKey]}</p>
      <div className="metricNumbers">
        <div>
          <small>Baseline</small>
          <b className="riskText">{displayMetric(metricKey, bVal)}</b>
        </div>
        <div>
          <small>Guarded</small>
          <b className="safeText">{displayMetric(metricKey, gVal)}</b>
        </div>
      </div>
      <div className={improved ? "deltaLine good" : "deltaLine bad"}>
        <span aria-label={improved ? "improved" : "worse"}>{improved ? "\u2191" : "\u2193"}</span> {deltaText}
      </div>
    </article>
  );
}

/* Trace Timeline */

function TraceTimeline({
  result,
  timelineView,
  setTimelineView,
  activeSection,
}: {
  result: EvaluationResult;
  timelineView: string;
  setTimelineView: (value: string) => void;
  activeSection: string;
}) {
  const trace = result.guarded_trace;
  const [selectedSpanIdx, setSelectedSpanIdx] = useState<number | null>(null);
  const [zoomLevel, setZoomLevel] = useState(1);

  // Auto-select the first interesting span
  const autoSpan = useMemo(() => {
    const idx = trace.spans.findIndex((s) => s.policy_decision === "BLOCK" || s.failure_label);
    return idx >= 0 ? idx : 0;
  }, [trace.spans]);

  const activeIdx = selectedSpanIdx ?? autoSpan;
  const activeSpan = trace.spans[activeIdx];
  const maxStep = Math.max(20, trace.spans.length || 1);
  const stepTicks = [1, 5, 10, 15, 20].filter((step) => step <= maxStep);
  const timeTicks = [0, 15, 30, 45, 60].slice(0, stepTicks.length);
  const guideTicks = stepTicks.filter((step) => step > 1);
  const stepPercent = (step: number) => `${2 + ((step - 1) / Math.max(1, maxStep - 1)) * 94}%`;
  const eventStep = (index: number) => index + 1;
  const eventLeft = (index: number) => stepPercent(eventStep(index));
  const laneBars = {
    orchestrator: [
      { label: "Plan Task", start: 3, end: 6 },
      { label: "Decompose", start: 8, end: 11 },
      { label: "Re-plan", start: 15, end: 17 },
      { label: "Finalize", start: 19, end: 20 },
    ],
    analyst: [
      { label: "Analyze Query", start: 3, end: 6 },
      { label: "Assess Risk", start: 8, end: 11 },
      { label: "Generate Advice", start: 12, end: 15 },
      { label: "Review Advice", start: 17, end: 19 },
    ],
    researcher: [
      { label: "Search Docs", start: 3, end: 5 },
      { label: "Fetch SEC Filings", start: 7, end: 10 },
      { label: "Lookup Market Data", start: 12, end: 15 },
      { label: "Fetch Compliance Rules", start: 16, end: 19 },
    ],
    critic: [
      { label: "Evaluate Plan", start: 4, end: 7 },
      { label: "Evaluate Output", start: 14, end: 16 },
      { label: "Final Check", start: 18, end: 20 },
    ],
    tools: [
      { label: "VectorSearch", start: 3, end: 5 },
      { label: "WebSearch", start: 6, end: 9 },
      { label: "SQLQuery", start: 10, end: 12 },
      { label: "Calculator", start: 13, end: 15 },
      { label: "DocReader", start: 17, end: 18 },
      { label: "ComplianceDB", start: 19, end: 20 },
    ],
  };

  const handleZoomIn = () => setZoomLevel((z) => Math.min(z + 0.25, 2));
  const handleZoomOut = () => setZoomLevel((z) => Math.max(z - 0.25, 0.5));
  const handleFit = () => setZoomLevel(1);

  return (
    <section className={`timelinePanel ${activeSection === "traces" ? "activeHighlight" : ""}`.trim()} id="traces">
      <div className="panelHeaderLine">
        <h2>Trace Timeline</h2>
        <div className="legend">
          <span><i className="agentDot" /> Agent Step</span>
          <span><i className="toolDot" /> Tool Call</span>
          <span><i className="guardDot" /> Guard Check</span>
          <span><i className="interventionDot" /> Guard Intervention</span>
          <span><i className="hitDot" /> Policy Hit</span>
        </div>
        <div className="timelineControls">
          <span className="viewSelectLabel">View</span>
          <select value={timelineView} onChange={(event) => setTimelineView(event.target.value)}>
            <option>Timeline</option>
            <option>Events</option>
          </select>
          <div className="zoomTools">
            <button type="button" onClick={handleFit} title="Fit to view" className="zoomBtn">Fit</button>
            <button type="button" onClick={handleZoomOut} title="Zoom out" className="zoomBtn"><Icon name="search" /></button>
            <button type="button" onClick={handleZoomIn} title="Zoom in" className="zoomBtn"><Icon name="zoom" /></button>
            <button type="button" onClick={() => setZoomLevel(1)} title="Reset" className="zoomBtn"><Icon name="expand" /></button>
          </div>
        </div>
      </div>
      {timelineView === "Timeline" ? (
        <div className="timelineGrid" style={{ transform: `scaleX(${zoomLevel})`, transformOrigin: "left" }}>
          <div className="timelineGuides" aria-hidden="true">
            {guideTicks.map((step) => (
              <span className="guideLine" style={{ left: stepPercent(step) }} key={`guide-${step}`} />
            ))}
          </div>
          <div className="axisLabels">
            <div className="axisLeft"><b>Step</b><b>Time (s)</b></div>
            <div className="axisTrackLabels">
              {stepTicks.map((n) => (
                <b className="axisStep" style={{ left: stepPercent(n) }} key={`s-${n}`}>{n}</b>
              ))}
              {timeTicks.map((n, index) => (
                <small className="axisTime" style={{ left: stepPercent(stepTicks[index]) }} key={`t-${stepTicks[index]}`}>{n}</small>
              ))}
            </div>
          </div>
          <TimelineLane label="Orchestrator" role="Planner" bars={laneBars.orchestrator} tone="agent" maxStep={maxStep} />
          <TimelineLane label="Analyst" role="Reasoner" bars={laneBars.analyst} tone="agent" maxStep={maxStep} />
          <TimelineLane label="Researcher" role="Retriever" bars={laneBars.researcher} tone="tool" maxStep={maxStep} />
          <TimelineLane label="Critic" role="Evaluator" bars={laneBars.critic} tone="agent" maxStep={maxStep} />
          <TimelineLane label="Tools" role="" bars={laneBars.tools} tone="tool" maxStep={maxStep} />
          <div className="guardRail">
            <div className="laneName">Guards</div>
            <div className="guardMarks">
              {trace.spans.map((span, index) => {
                const isHit = span.policy_decision === "BLOCK";
                const isIntervention = span.policy_decision === "MODIFY" || span.policy_decision === "REQUIRE_APPROVAL";
                const className = isHit ? "guardMark hit" : isIntervention ? "guardMark intervention" : "guardMark";
                return (
                  <span
                    className={`${className} ${activeIdx === index ? "selected" : ""}`}
                    style={{ left: eventLeft(index) }}
                    key={span.span_id || index}
                    role="button"
                    tabIndex={0}
                    title={`${isHit ? "Policy Hit" : isIntervention ? "Guard Intervention" : "Guard Check"} at step ${eventStep(index)}`}
                    onClick={() => setSelectedSpanIdx(index)}
                    onKeyDown={(e) => e.key === "Enter" && setSelectedSpanIdx(index)}
                  />
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        <div className="eventsListView">
          <table>
            <thead>
              <tr>
                <th>Step</th>
                <th>Time (s)</th>
                <th>Agent / Tool</th>
                <th>Event Type</th>
                <th>Decision / Status</th>
              </tr>
            </thead>
            <tbody>
              {trace.spans.map((span, index) => {
                const time = ((span.latency_ms || 44200) / 1000).toFixed(1);
                const type = span.span_type === "guard_decision" ? "Guard Check" : span.span_type === "tool_call" ? "Tool Call" : "Agent Step";
                const isSelected = activeIdx === index;
                return (
                  <tr 
                    key={span.span_id || index} 
                    className={isSelected ? "selectedRow" : ""}
                    onClick={() => setSelectedSpanIdx(index)}
                  >
                    <td>{index + 1}</td>
                    <td>{time}</td>
                    <td>{span.agent || span.tool || "System"}</td>
                    <td><span className={`eventPill ${span.span_type || "agent"}`}>{type}</span></td>
                    <td>
                       <span className={span.policy_decision === "BLOCK" ? "statusPill riskText" : "statusPill safeText"}>
                         {formatPolicy(span.policy_decision)}
                       </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <SelectedEvent span={activeSpan} index={activeIdx} />
    </section>
  );
}

function TimelineLane({
  label,
  role,
  bars,
  tone,
  maxStep,
}: {
  label: string;
  role: string;
  bars: Array<{ label: string; start: number; end: number }>;
  tone: "agent" | "tool";
  maxStep: number;
}) {
  const leftForStep = (step: number) => 2 + ((step - 1) / Math.max(1, maxStep - 1)) * 94;
  return (
    <div className="timelineLane">
      <div className="laneName"><span className="laneIcon"><Icon name={tone === "agent" ? "agent" : "tool"} /></span>{label}{role && <small>({role})</small>}</div>
      <div className="laneTrack">
        {bars.map((bar) => {
          const left = leftForStep(bar.start);
          const right = leftForStep(Math.min(maxStep, bar.end));
          return (
          <span
            className={`timelineBar ${tone}`}
            style={{ left: `${left}%`, width: `${Math.max(7, right - left)}%` }}
            key={bar.label}
            title={`${bar.label}: steps ${bar.start}-${bar.end}`}
          >
            {bar.label}
          </span>
          );
        })}
      </div>
    </div>
  );
}

/* Selected Event */

function SelectedEvent({ span, index }: { span?: Span; index: number }) {
  if (!span) return null;
  const guardName = span.agent || "PII Guard";
  const target = span.role ? `${span.agent} (${span.role})` : span.agent || "Analyst (Reasoner)";
  const reason = span.output || span.failure_label || "Detected potential PII in model output";
  const decision = span.policy_decision || "ALLOW";
  const time = ((span.latency_ms || 44200) / 1000).toFixed(1);

  let iconName = "guardDiamond";
  let iconClass = "selectedKind";
  let displayType = span.span_type || "Agent Step";
  
  if (span.span_type === "guard_decision") {
    if (decision === "BLOCK") {
      iconName = "hitSquare";
      iconClass += " hitIcon";
      displayType = "Policy Hit";
    } else if (decision === "MODIFY" || decision === "REQUIRE_APPROVAL") {
      iconName = "guardDiamond";
      iconClass += " interventionIcon";
      displayType = "Guard Intervention";
    } else {
      iconName = "guardDiamond";
      iconClass += " guardIcon";
      displayType = "Guard Check";
    }
  } else if (span.span_type === "tool_call") {
    iconName = "tool";
    displayType = "Tool Call";
  } else {
    iconName = "agent";
    displayType = "Agent Step";
  }

  return (
    <div className="selectedEvent">
      <div className="selectedEventCell">
        <span className="selectedLabel">Selected Event</span>
        <span className={iconClass}><Icon name={iconName} /> {displayType}</span>
      </div>
      <div className="selectedEventCell">
        <span className="selectedLabel">Step</span>
        <span className="selectedValue">{index + 1}</span>
      </div>
      <div className="selectedEventCell">
        <span className="selectedLabel">Time</span>
        <span className="selectedValue">{time}s</span>
      </div>
      <div className="selectedEventCell">
        <span className="selectedLabel">Guard</span>
        <span className="selectedValue">{guardName}</span>
      </div>
      <div className="selectedEventCell">
        <span className="selectedLabel">Target</span>
        <span className="selectedValue">{target}</span>
      </div>
      <div className="selectedEventCell">
        <span className="selectedLabel">Result</span>
        <span className={decision === "BLOCK" ? "selectedValue blocked" : "selectedValue"}>{formatPolicy(decision)}</span>
      </div>
      <div className="selectedEventCell selectedReasonCell">
        <span className="selectedLabel">Reason</span>
        <span className="selectedValue">{reason}</span>
      </div>
    </div>
  );
}

/* Risk Reduction */

function RiskReduction({ result, activeSection }: { result: EvaluationResult; activeSection: string }) {
  const baselineRisk = riskScore(result.baseline_metrics);
  const guardedRisk = riskScore(result.guarded_metrics);
  const reduction = baselineRisk ? Math.max(0, (baselineRisk - guardedRisk) / baselineRisk) : 0;
  const rows = riskBreakdown(result);

  const overallRow = {
    name: "Overall RSS",
    baseline: baselineRisk,
    guarded: guardedRisk,
  };

  return (
    <section className={`riskPanel ${activeSection === "guards" ? "activeHighlight" : ""}`.trim()} id="guards">
      <h2>Risk Reduction</h2>
      <div className="riskHeadline">
        <b className="riskText">{baselineRisk.toFixed(2)}</b>
        <span className="riskArrow">&rarr;</span>
        <b className="safeText">{guardedRisk.toFixed(2)}</b>
        <strong className="reductionPct">{(reduction * 100).toFixed(1)}% <small>Reduction</small></strong>
      </div>
      <div className="riskSlider"><span style={{ left: `${Math.min(96, reduction * 100)}%` }} /></div>
      <div className="riskLevel">Risk Level <b className="riskLevelHigh">HIGH</b> <span className="riskArrowSmall">&rarr;</span> <strong className="riskLevelLow">LOW</strong></div>
      <div className="riskDetails">
        <div className="riskTableSection">
          <h3 className="riskTableTitle">Risk Score Breakdown (RSS)</h3>
          <table>
            <thead>
              <tr><th>Dimension</th><th>Baseline</th><th>Guarded</th><th>{"\u0394"}</th></tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const diff = row.baseline - row.guarded;
                return (
                  <tr key={row.name}>
                    <td>{row.name}</td>
                    <td className="riskText">{row.baseline.toFixed(2)}</td>
                    <td className="safeText">{row.guarded.toFixed(2)}</td>
                    <td className={diff >= 0 ? "safeText" : "riskText"}>
                      {diff >= 0 ? "\u2193" : "\u2191"} {Math.abs(diff).toFixed(2)}
                    </td>
                  </tr>
                );
              })}
              <tr className="overallRow">
                <td><strong>{overallRow.name}</strong></td>
                <td className="riskText"><strong>{overallRow.baseline.toFixed(2)}</strong></td>
                <td className="safeText"><strong>{overallRow.guarded.toFixed(2)}</strong></td>
                <td className={overallRow.baseline - overallRow.guarded >= 0 ? "safeText" : "riskText"}>
                  <strong>{overallRow.baseline - overallRow.guarded >= 0 ? "\u2193" : "\u2191"} {Math.abs(overallRow.baseline - overallRow.guarded).toFixed(2)}</strong>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <Radar rows={rows} />
      </div>
    </section>
  );
}

/* Recent Traces */

function RecentTraces({ result, activeSection }: { result: EvaluationResult; activeSection: string }) {
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const closeMenu = useCallback(() => setOpenMenu(null), []);
  useClickOutside(menuRef, closeMenu);

  const rows = [
    { mode: "Guarded", trace: result.guarded_trace, metrics: result.guarded_metrics },
    { mode: "Baseline", trace: result.baseline_trace, metrics: result.baseline_metrics },
  ];

  const handleExportJSON = (trace: Trace) => {
    const blob = new Blob([JSON.stringify(trace, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${runIdFromTrace(trace)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    setOpenMenu(null);
  };

  const handleCopyId = (trace: Trace) => {
    void navigator.clipboard?.writeText(runIdFromTrace(trace));
    setOpenMenu(null);
  };

  return (
    <section className={`recentPanel ${activeSection === "reports" ? "activeHighlight" : ""}`.trim()} id="reports">
      <h2>Recent Traces</h2>
      <table>
        <thead>
          <tr>
            <th>Run ID</th>
            <th>Scenario</th>
            <th>Mode</th>
            <th>RSS</th>
            <th>TSP</th>
            <th>CPI</th>
            <th>PHR</th>
            <th>Interventions</th>
            <th>Started At</th>
            <th>Duration</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.mode}>
              <td>{runIdFromTrace(row.trace)}</td>
              <td>{result.scenario.scenario_id} {formatRisk(result.scenario.risk_type)}</td>
              <td><span className={row.mode === "Guarded" ? "modePill guarded" : "modePill baseline"}>{row.mode}</span></td>
              <td>{riskScore(row.metrics).toFixed(2)}</td>
              <td>{row.metrics.TSP.score.toFixed(2)}</td>
              <td>{displayMetric("CPI", row.metrics.CPI.score)}</td>
              <td>{displayMetric("PHR", row.metrics.PHR.score)}</td>
              <td>{row.trace.spans.filter((span) => span.policy_decision === "BLOCK").length}</td>
              <td>{formatDate(row.trace.started_at)}</td>
              <td>{duration(row.trace)}</td>
              <td><span className="statusPill complete"><span className="statusDot" /> Completed</span></td>
              <td style={{ position: "relative" }}>
                <div ref={openMenu === row.mode ? menuRef : undefined} style={{ position: "relative", display: "inline-block" }}>
                <button
                  className="rowMenu"
                  type="button"
                  aria-label={`${row.mode} trace actions`}
                  onClick={() => setOpenMenu(openMenu === row.mode ? null : row.mode)}
                >
                  <Icon name="more" />
                </button>
                {openMenu === row.mode && (
                  <div className="rowDropdown">
                    <button type="button" onClick={() => handleCopyId(row.trace)}><Icon name="copy" /> Copy Run ID</button>
                    <button type="button" onClick={() => handleExportJSON(row.trace)}><Icon name="reports" /> Export JSON</button>
                    <button type="button" onClick={() => { setOpenMenu(null); }}><Icon name="search" /> View Details</button>
                  </div>
                )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

/* Radar Chart */

function Radar({ rows }: { rows: Array<{ name: string; baseline: number; guarded: number }> }) {
  const cx = 120;
  const cy = 105;
  const maxR = 48;

  const getPoint = (index: number, value: number) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / rows.length;
    const r = Math.max(0.12, Math.min(1, value)) * maxR;
    return { x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r };
  };

  const points = (kind: "baseline" | "guarded") =>
    rows
      .map((row, index) => {
        const pt = getPoint(index, row[kind]);
        return `${pt.x},${pt.y}`;
      })
      .join(" ");

  const labelPositions = rows.map((row, index) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / rows.length;
    const labelR = maxR + 24;
    return {
      x: cx + Math.cos(angle) * labelR,
      y: cy + Math.sin(angle) * labelR,
      name: row.name,
      anchor: Math.abs(Math.cos(angle)) < 0.1 ? "middle" as const : Math.cos(angle) > 0 ? "start" as const : "end" as const,
    };
  });

  const ticks = [0.33, 0.66, 1.0];
  const tickLabels = ["0.33", "0.66", "1.00"];

  return (
    <div className="radarBox">
      <h3>Risk Profile (Radar)</h3>
      <svg viewBox="0 0 240 210" role="img" aria-label="Risk profile radar chart">
        {ticks.map((r) => (
          <polygon className="radarGrid" key={r} points={rows.map((_, i) => {
            const a = -Math.PI / 2 + (i * 2 * Math.PI) / rows.length;
            return `${cx + Math.cos(a) * r * maxR},${cy + Math.sin(a) * r * maxR}`;
          }).join(" ")} />
        ))}
        {rows.map((_, i) => {
          const a = -Math.PI / 2 + (i * 2 * Math.PI) / rows.length;
          return <line key={`axis-${i}`} x1={cx} y1={cy} x2={cx + Math.cos(a) * maxR} y2={cy + Math.sin(a) * maxR} stroke="#dce5ec" strokeWidth="1" />;
        })}
        {ticks.map((r, ri) => (
          <text key={`tick-${ri}`} x={cx + 4} y={cy - r * maxR - 2} fontSize="8" fill="#94a3b8" textAnchor="start">{tickLabels[ri]}</text>
        ))}
        <polygon className="radarBase" points={points("baseline")} />
        <polygon className="radarGuard" points={points("guarded")} />
        {labelPositions.map((lp, i) => (
          <text key={`label-${i}`} x={lp.x} y={lp.y} fontSize="9" fill="#334155" textAnchor={lp.anchor} dominantBaseline="middle" fontWeight="600">
            {lp.name}
          </text>
        ))}
      </svg>
      <div className="radarLegend">
        <span className="legendBaseline"><span className="legendSwatch baselineSwatch" /> Baseline</span>
        <span className="legendGuarded"><span className="legendSwatch guardedSwatch" /> Guarded</span>
      </div>
    </div>
  );
}

/* Small Components */

function LabeledSelect({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <label className="selectCard">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {children}
      </select>
    </label>
  );
}

function Stat({ label, value, tone, large }: { label: string; value: string; tone?: "safe" | "risk"; large?: boolean }) {
  return (
    <div className="statCell">
      <small>{label}</small>
      <strong className={tone === "safe" ? "safeText" : tone === "risk" ? "riskText" : ""}>{value}</strong>
      {large && <b className={tone === "safe" ? "safeText" : "riskText"}>{value}</b>}
    </div>
  );
}

function ShieldIcon() {
  return (
    <svg className="brandShield" viewBox="0 0 40 40" aria-hidden="true">
      <path d="M20 3 34 8v10c0 9-5.8 15.2-14 19C11.8 33.2 6 27 6 18V8l14-5Z" fill="none" stroke="currentColor" strokeWidth="3" />
      <path d="M15 20l4 4 7-9" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Icon({ name }: { name: string }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  const icons: Record<string, ReactNode> = {
    scenario: <><rect x="4" y="4" width="16" height="16" rx="2" {...common} /><path d="M8 9h8M8 13h5" {...common} /></>,
    traces: <><path d="M4 7h11M9 3l-5 4 5 4M20 17H9M15 13l5 4-5 4" {...common} /></>,
    metrics: <><path d="M5 19V9M12 19V5M19 19v-7" {...common} /><path d="M3 19h18" {...common} /></>,
    guard: <><path d="M12 3 20 6v6c0 5-3.2 8.5-8 10-4.8-1.5-8-5-8-10V6l8-3Z" {...common} /><path d="m9 12 2 2 4-5" {...common} /></>,
    reports: <><path d="M6 3h9l3 3v15H6z" {...common} /><path d="M14 3v4h4M9 12h6M9 16h6" {...common} /></>,
    chevron: <path d="m7 10 5 5 5-5" {...common} />,
    code: <><path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 4l-4 16" {...common} /></>,
    book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5z" {...common} /><path d="M4 5.5v16M8 7h8" {...common} /></>,
    refresh: <><path d="M20 6v5h-5M4 18v-5h5" {...common} /><path d="M18 11a6 6 0 0 0-10-4M6 13a6 6 0 0 0 10 4" {...common} /></>,
    play: <path d="M8 5v14l11-7z" fill="currentColor" />,
    copy: <><rect x="8" y="8" width="11" height="11" rx="2" {...common} /><path d="M5 15H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1" {...common} /></>,
    agents: <><path d="M16 21v-2a4 4 0 0 0-8 0v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M20 21v-2a3 3 0 0 0-2-2.8" {...common} /></>,
    agent: <><rect x="4" y="8" width="16" height="12" rx="3" {...common} /><path d="M12 8V4M10 4h4" {...common} /><circle cx="9" cy="14" r="1.5" fill="currentColor" /><circle cx="15" cy="14" r="1.5" fill="currentColor" /><path d="M10 18h4" {...common} /></>,
    tools: <><path d="m14.7 6.3 3 3M4 20l7.5-7.5M14 3l7 7-9 9H5v-7z" {...common} /></>,
    tool: <><path d="m14 7 3 3-7 7H7v-3z" {...common} /><path d="M5 19h14" {...common} /></>,
    steps: <><path d="M4 17h5v-5h5V7h6" {...common} /><path d="M17 4h3v3" {...common} /></>,
    temperature: <><path d="M14 14.8V5a2 2 0 1 0-4 0v9.8a4 4 0 1 0 4 0Z" {...common} /><path d="M12 9v7" {...common} /></>,
    info: <><circle cx="12" cy="12" r="9" {...common} /><path d="M12 11v6M12 7h.01" {...common} /></>,
    search: <><circle cx="11" cy="11" r="6" {...common} /><path d="m16 16 4 4" {...common} /></>,
    zoom: <><circle cx="11" cy="11" r="6" {...common} /><path d="M11 8v6M8 11h6M16 16l4 4" {...common} /></>,
    expand: <><path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5" {...common} /></>,
    shield: <path d="M12 3 20 6v6c0 5-3.2 8.5-8 10-4.8-1.5-8-5-8-10V6l8-3Z" {...common} />,
    checkCircle: <><circle cx="12" cy="12" r="9" {...common} /><path d="m8.5 12.5 2.2 2.2 4.8-5.4" {...common} /></>,
    guardDiamond: <path d="m12 4 8 8-8 8-8-8z" {...common} />,
    hitSquare: <rect x="4" y="4" width="16" height="16" fill="currentColor" />,
    more: <><circle cx="12" cy="5" r="1.2" fill="currentColor" /><circle cx="12" cy="12" r="1.2" fill="currentColor" /><circle cx="12" cy="19" r="1.2" fill="currentColor" /></>,
  };
  return (
    <svg className="uiIcon" viewBox="0 0 24 24" aria-hidden="true">
      {icons[name] ?? icons.info}
    </svg>
  );
}

/* Utility Functions */

function riskScore(metrics: Record<MetricKey, MetricResult>) {
  const scores = metricOrder.map((key) => (riskMetrics.has(key) ? metrics[key].score : 1 - metrics[key].score));
  return scores.reduce((sum, score) => sum + score, 0) / scores.length;
}

function riskBreakdown(result: EvaluationResult) {
  const names = ["Harmfulness", "Privacy", "Compliance", "Fairness", "Robustness"];
  const metricPairs: MetricKey[] = ["RSS", "PHR", "CPI", "CCR", "CFP"];
  return names.map((name, index) => {
    const key = metricPairs[index];
    const baseline = riskMetrics.has(key) ? result.baseline_metrics[key].score : 1 - result.baseline_metrics[key].score;
    const guarded = riskMetrics.has(key) ? result.guarded_metrics[key].score : 1 - result.guarded_metrics[key].score;
    return { name, baseline, guarded };
  });
}

function uniqueAgents(trace: Trace) {
  return Array.from(new Set(trace.spans.filter((span) => span.span_type !== "guard_decision").map((span) => span.agent)));
}

function uniqueTools(result: EvaluationResult) {
  const traceTools = [...result.baseline_trace.spans, ...result.guarded_trace.spans]
    .map((span) => span.tool)
    .filter((tool): tool is string => Boolean(tool));
  return Array.from(new Set([...traceTools, ...result.scenario.allowed_tools, ...result.scenario.blocked_tools]));
}

function displayMetric(key: MetricKey, value: number) {
  if (["PHR", "CPI", "CCR"].includes(key)) return `${(value * 100).toFixed(1)}%`;
  if (key === "DT") return (value * 10).toFixed(2);
  return value.toFixed(2);
}

function formatPolicy(value?: string | null) {
  if (value === "BLOCK") return "Blocked";
  if (value === "ALLOW") return "Allow";
  if (value === "REQUIRE_APPROVAL") return "Approval";
  if (value === "MODIFY") return "Modified";
  return "Allowed";
}

function runId(result: EvaluationResult, mode: "baseline" | "guarded") {
  return runIdFromTrace(mode === "baseline" ? result.baseline_trace : result.guarded_trace);
}

function runIdFromTrace(trace: Trace) {
  return `run_${trace.started_at.slice(0, 19).split("-").join("").split(":").join("").replace("T", "_")}_${trace.mode}`;
}

function formatRisk(value: string) {
  return value.split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function formatDate(value: string) {
  return new Date(value).toLocaleString("en-US", { month: "short", day: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function duration(trace: Trace) {
  const seconds = Math.max(18, trace.spans.length * 7);
  return seconds >= 60 ? `${Math.floor(seconds / 60)}m ${seconds % 60}s` : `${seconds}s`;
}

export default App;

