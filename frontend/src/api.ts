import type { AgentToolGraph, ApprovalRequest, DashboardPayload, FindingsReport, RunSummary, Trace } from "./types";

export const apiBase = import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

export async function fetchDashboard(): Promise<DashboardPayload> {
  const response = await fetch(`${apiBase}/dashboard`);
  if (!response.ok) {
    throw new Error(`Dashboard request failed: ${response.status}`);
  }
  return response.json();
}

async function getJson<T>(path: string, token?: string): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : undefined });
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

export const fetchRunHistory = () => getJson<RunSummary[]>("/runs?limit=30");
export const fetchSavedRun = (id: string) => getJson<Trace>(`/runs/${encodeURIComponent(id)}`);
export const fetchSavedGraph = (id: string) => getJson<AgentToolGraph>(`/runs/${encodeURIComponent(id)}/graph`);
export const fetchSavedFindings = (id: string) => getJson<FindingsReport>(`/runs/${encodeURIComponent(id)}/findings`);
export const fetchApprovals = (token: string) => getJson<ApprovalRequest[]>("/approvals", token);
export async function decideApproval(id: string, token: string, approve: boolean, reason: string): Promise<void> {
  const response = await fetch(`${apiBase}/approvals/${encodeURIComponent(id)}`, { method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: JSON.stringify({ approve, reason }) });
  if (!response.ok) throw new Error(`Approval decision failed: ${response.status}`);
}
