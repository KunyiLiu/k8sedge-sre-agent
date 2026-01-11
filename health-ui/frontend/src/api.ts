export type ResourceType = "Pod" | "Node" | "Deployment" | "Other";

export async function fetchTestMetric() {
  const res = await fetch("/api/metrics/test");
  return res.json();
}

export async function fetchHealthDiagnostic(issue: HealthIssue) {
  const res = await fetch("/api/workflow/diagnostic", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(issue),
  });
  return res.json();
}

// HealthIssue type for TypeScript
export interface HealthIssue {
  issueType: string;
  severity: "Critical" | "High" | "Warning" | "Info";
  resourceType: ResourceType;
  namespace?: string;
  resourceName: string;
  container?: string;
  unhealthySince: string;
  unhealthyTimespan: number;
  message: string;
}

// Helper to fetch health issues
export async function fetchHealthIssues(): Promise<HealthIssue[]> {
  const res = await fetch("/api/health/issues");
  return res.json();
}

export type NextAction = "continue" | "await_user_approval" | "handoff_to_solution_agent";

export interface AgentState {
  thought: string;
  action?: string | null;
  action_input?: string | null;
  next_action: NextAction;
  root_cause?: string | null;
}

export interface MessageItem { role: string; text: string }

export interface WorkflowStartResponse {
  status: string;
  diag_thread_id: string;
  sol_thread_id?: string | null;
  state?: AgentState | null;
  history: MessageItem[];
}

export interface InterveneResponse {
  diag_thread_id: string;
  sol_thread_id?: string | null;
  state?: AgentState | null;
  history: MessageItem[];
}

export async function getWorkflowHistory(diagThreadId: string, solThreadId?: string | null): Promise<{ diagnostic: MessageItem[]; solution: MessageItem[] }>{
  const url = new URL("/api/workflow/history", window.location.origin);
  url.searchParams.set("diag_thread_id", diagThreadId);
  if (solThreadId) url.searchParams.set("sol_thread_id", solThreadId);
  const res = await fetch(url.toString());
  return res.json();
}

export async function interveneWorkflow(diagThreadId: string, decision: "approve" | "deny" | "handoff", hint?: string): Promise<InterveneResponse> {
  const res = await fetch("/api/workflow/intervene", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ diag_thread_id: diagThreadId, decision, hint }),
  });
  return res.json();
}

export function issueKey(issue: HealthIssue): string {
  const ns = issue.namespace || "default";
  const container = issue.container || "";
  return `${ns}:${issue.resourceType}:${issue.resourceName}:${container}`;
}