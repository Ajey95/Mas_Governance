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
  token_usage: number;
  failure_label: string | null;
  metadata: Record<string, unknown>;
}

export interface Trace {
  trace_id: string;
  scenario_id: string;
  mode: "baseline" | "guarded";
  started_at: string;
  final_response: string;
  blocked: boolean;
  spans: Span[];
}

export interface MetricResult {
  key: MetricKey;
  name: string;
  score: number;
  passed: boolean;
  threshold: number;
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
}

export interface DashboardPayload {
  dataset: { scenarios: Scenario[] };
  results: EvaluationResult[];
  summary: {
    scenario_count: number;
    metrics: Record<MetricKey, { baseline_avg: number; guarded_avg: number }>;
  };
  adapter: string;
  guards: string[];
}
