import { useEffect, useState, useCallback } from "react";
import { FiRefreshCw } from "react-icons/fi";
import { fetchHealthDiagnostic, fetchHealthIssues, type HealthIssue } from "./api";

// Severity order for sorting
const severityOrder: Record<HealthIssue["severity"], number> = { Critical: 0, High: 1, Warning: 2, Info: 3 };

function App() {
  const [issues, setIssues] = useState<HealthIssue[]>([]);
  const [loading, setLoading] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [expandedNamespaces, setExpandedNamespaces] = useState<Record<string, boolean>>({});

  const loadIssues = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchHealthIssues();
      setIssues(data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadIssues();
    const interval = setInterval(loadIssues, 30000);
    return () => clearInterval(interval);
  }, [loadIssues]);

  // Group issues by namespace
  const issuesByNamespace: Record<string, HealthIssue[]> = issues.reduce((acc, issue) => {
    const ns = issue.namespace || "default";
    if (!acc[ns]) acc[ns] = [];
    acc[ns].push(issue);
    return acc;
  }, {} as Record<string, HealthIssue[]>);

  // Sort issues in each namespace
  Object.keys(issuesByNamespace).forEach(ns => {
    issuesByNamespace[ns] = [...issuesByNamespace[ns]].sort((a, b) => {
      const sevA = severityOrder[a.severity] ?? 99;
      const sevB = severityOrder[b.severity] ?? 99;
      if (sevA !== sevB) return sevA - sevB;
      return b.unhealthyTimespan - a.unhealthyTimespan;
    });
  });

  // Toggle expand/collapse for namespace
  const toggleNamespace = (ns: string) => {
    setExpandedNamespaces(prev => ({ ...prev, [ns]: !prev[ns] }));
  };

  const handleCardClick = async (issue: HealthIssue) => {
    setTestResult("Loading...");
    const res = await fetchHealthDiagnostic(issue);
    setTestResult(res);
  };

  return (
    <div style={{ maxWidth: 800, margin: "0 auto", padding: 24, position: "relative" }}>
      <h1 style={{ marginBottom: 32 }}>K8s SRE Agent</h1>
      <button
        onClick={loadIssues}
        disabled={loading}
        style={{ position: "absolute", top: 24, right: 24, background: "none", border: "none", cursor: "pointer", fontSize: 24 }}
        title="Manual Refresh"
      >
        <FiRefreshCw style={{ color: loading ? "#aaa" : "#1976d2", animation: loading ? "spin 1s linear infinite" : undefined }} />
        <span style={{ display: "none" }}>Manual Refresh</span>
      </button>
      <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
      <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
        {Object.entries(issuesByNamespace).map(([ns, nsIssues]) => (
          <div key={ns} style={{ border: "1px solid #e0e0e0", borderRadius: 8, background: "#f7f7fa" }}>
            <div
              style={{ padding: "12px 20px", fontWeight: "bold", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between" }}
              onClick={() => toggleNamespace(ns)}
            >
              <span>Namespace [{ns}] - {nsIssues.length} Issue{nsIssues.length !== 1 ? "s" : ""}</span>
              <span style={{ fontSize: 18 }}>{expandedNamespaces[ns] ? "▼" : "▶"}</span>
            </div>
            {expandedNamespaces[ns] && (
              <div style={{ display: "flex", flexDirection: "column", gap: 16, padding: "0 20px 16px 20px" }}>
                {nsIssues.map((issue, idx) => {
                  let cardColor = "#fafbfc";
                  if (issue.severity === "Critical") cardColor = "#ffebee"; // light red
                  else if (issue.severity === "High") cardColor = "#fff3e0"; // light orange
                  else if (issue.severity === "Warning") cardColor = "#fffde7"; // light yellow
                  return (
                    <div
                      key={idx}
                      onClick={() => handleCardClick(issue)}
                      style={{
                        border: "1px solid #ccc",
                        borderRadius: 8,
                        padding: 16,
                        background: cardColor,
                        cursor: "pointer",
                        boxShadow: "0 2px 8px rgba(0,0,0,0.04)",
                        transition: "box-shadow 0.2s",
                      }}
                    >
                      <div style={{ fontWeight: "bold", color: issue.severity === "Critical" ? "#d32f2f" : issue.severity === "High" ? "#f57c00" : issue.severity === "Warning" ? "#fbc02d" : "#1976d2" }}>
                        {issue.severity} - {issue.issueType} ({issue.resourceType})
                      </div>
                      <div>Resource: {issue.resourceName} {issue.container ? `| Container: ${issue.container}` : ""}</div>
                      <div>Unhealthy Since: {issue.unhealthySince}</div>
                      <div style={{ color: "#555" }}>{issue.message}</div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>
      {testResult && (
        <div style={{ marginTop: 32 }}>
          <h3>Test API Result</h3>
          <pre style={{ background: "#f5f5f5", padding: 12, borderRadius: 6 }}>{typeof testResult === "string" ? testResult : JSON.stringify(testResult, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

export default App;
