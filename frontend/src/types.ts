export type MetricKey = "TSP" | "TSR" | "PHR" | "CPI" | "CFP" | "RSS" | "CCR" | "DT";

export interface Scenario {
  scenario_id: string;
  source_case_study: string;
  risk_type: string;
  user_role: string;
  prompt: string;
  expected_safe_behavior: string;
  allowed_tools: string[];
  blocked_tools: string[];
  required_tools: string[];
  authorized_roles: string[];
  metrics: MetricKey[];
  tags: string[];
  provenance?: string;
}

export interface Span {
  span_id: string;
  trace_id: string;
  parent_span_id: string | null;
  timestamp: string;
  span_type: string;
  agent: string;
  role: string;
  input: string | null;
  output: string | null;
  tool: string | null;
  tool_parameters: Record<string, unknown>;
  policy_decision: string | null;
  latency_ms: number;
  token_usage: number | null;
  failure_label: string | null;
  metadata: Record<string, unknown>;
}

export interface Trace {
  trace_id: string;
  scenario_id: string;
  mode: "baseline" | "guarded";
  started_at: string;
  completed_at: string | null;
  elapsed_ms: number | null;
  stop_reason: string | null;
  final_response: string;
  blocked: boolean;
  spans: Span[];
  scenario?: Scenario | null;
}

export interface MetricResult {
  key: MetricKey;
  name: string;
  score: number;
  passed: boolean | null;
  applicable: boolean;
  threshold: number | null;
  interpretation: string;
  details: Record<string, unknown>;
}

export interface EvaluationResult {
  scenario: Scenario;
  baseline_trace: Trace;
  guarded_trace: Trace;
  baseline_metrics: Record<MetricKey, MetricResult>;
  guarded_metrics: Record<MetricKey, MetricResult>;
  risk_reduction: Record<MetricKey, number>;
  recommendations: string[];
  baseline_graph: AgentToolGraph;
  guarded_graph: AgentToolGraph;
}

export interface GraphNode { id: string; label: string; kind: "agent" | "tool" | "graph_node"; namespace?: string; policy?: string; is_root_failure?: boolean }
export interface GraphEdge { id: string; source: string; target: string; kind: string; span_id: string; decision: string | null; failure_label: string | null; is_root_failure: boolean; is_propagated_failure: boolean }
export interface AgentToolGraph {
  trace_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  span_propagation: {
    root_span_ids: string[];
    propagated_span_ids: string[];
    dependency_edges?: { source: string; target: string }[];
    failure_paths?: string[][];
    unlinked_propagation_span_ids?: string[];
    [key: string]: unknown;
  };
}
export interface RunSummary { trace_id: string; scenario_id: string; mode: "baseline" | "guarded"; started_at: string; completed_at: string | null; adapter: string; blocked: boolean }
export interface Finding { kind: string; severity: "high" | "medium" | "info"; title: string; detail: string; evidence_span_ids: string[]; next_action: string }
export interface FindingsReport { trace_id: string; scenario_id: string; status: string; scope: string; summary: { spans: number; executed_tool_calls: number; guard_interventions: number; high_severity_findings: number; blocked: boolean; stop_reason: string | null; final_response: string }; findings: Finding[]; interpretation: string }
export interface ApprovalRequest { request_id: string; trace_id: string; scenario_id: string; agent: string; tool: string | null; parameters: Record<string, unknown>; created_at: string; status: string }

export interface DashboardPayload {
  dataset: { scenarios: Scenario[] };
  results: EvaluationResult[];
  summary: {
    scenario_count: number;
    metrics: Partial<Record<MetricKey, { baseline_avg: number | null; guarded_avg: number | null; baseline_n: number; guarded_n: number }>>;
  };
  adapter: string;
  execution_kind: string;
  guards: string[];
}
