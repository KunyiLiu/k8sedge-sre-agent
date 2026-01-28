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

  return (
    <div className={`issue-card ${sevClass}`} onClick={onClick}>
      <div className="issue-card-header">
        <span>{issue.severity} - {issue.issueType} ({issue.resourceType})</span>
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
