export type ResourceType = "Pod" | "Node" | "Deployment" | "Other";

export async function fetchTestMetric() {
  const res = await fetch("/api/metrics/test");
  return res.json();
}

export async function fetchHealthDiagnostic(issue: HealthIssue) {
  const res = await fetch("/api/health/diagnostic", {
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