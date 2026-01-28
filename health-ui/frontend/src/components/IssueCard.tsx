import type { HealthIssue } from "../api";

export function IssueCard({ issue, status, onClick, rootCause }: {
  issue: HealthIssue;
  status: { label: string; color: string; handingOff?: boolean };
  onClick: () => void;
  rootCause?: string | null;
}) {
  const sevClass = issue.severity === "Critical"
    ? "severity-critical"
    : issue.severity === "High"
    ? "severity-high"
    : issue.severity === "Warning"
    ? "severity-warning"
    : "severity-info";

  const severityIcon = issue.severity === "Critical"
    ? "⛔"
    : issue.severity === "High"
    ? "🔥"
    : issue.severity === "Warning"
    ? "⚠️"
    : "ℹ️";

  return (
    <div className={`issue-card ${sevClass}`} onClick={onClick} title="Click to troubleshoot">
      <div className="issue-card-header">
        <span>
          <span aria-hidden="true" style={{ marginRight: 6 }}>{severityIcon}</span>
          <span className="sr-only">{issue.severity} - </span>
          {issue.issueType} ({issue.resourceType})
        </span>
        <span className="status-badge" style={{ color: status.color, borderColor: status.color }}>
          {status.handingOff && (
            <span className="spinner spinner-inline" aria-label="Handing off" />
          )}
          <span>{status.label}</span>
        </span>
      </div>
      <div>Resource: {issue.resourceName} {issue.container ? `| Container: ${issue.container}` : ""}</div>
      <div>Unhealthy Since: {issue.unhealthySince}</div>
      <div className="issue-message">{issue.message}</div>
      {rootCause && (
        <div className="root-cause-highlight">Root Cause: {rootCause}</div>
      )}
    </div>
  );
}
