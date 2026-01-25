export type ResourceType = "Pod" | "Node" | "Deployment" | "Other";

export async function fetchTestMetric() {
  const res = await fetch("/api/metrics/test");
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

