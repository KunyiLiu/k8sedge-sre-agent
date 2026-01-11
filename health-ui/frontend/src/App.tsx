import { useEffect, useState, useCallback } from "react";
import { FiRefreshCw } from "react-icons/fi";
import {
  fetchHealthDiagnostic,
  fetchHealthIssues,
  type HealthIssue,
  type AgentState,
  type MessageItem,
  getWorkflowHistory,
  interveneWorkflow,
  issueKey,
} from "./api";

// Severity order for sorting
const severityOrder: Record<HealthIssue["severity"], number> = { Critical: 0, High: 1, Warning: 2, Info: 3 };

function App() {
  const [issues, setIssues] = useState<HealthIssue[]>([]);
  const [loading, setLoading] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [expandedNamespaces, setExpandedNamespaces] = useState<Record<string, boolean>>({});
  const [threadsByIssue, setThreadsByIssue] = useState<Record<string, { diagThreadId: string; solThreadId?: string | null }>>({});
  const [conversationByIssue, setConversationByIssue] = useState<Record<string, { state?: AgentState | null; diagnostic: MessageItem[]; solution: MessageItem[] }>>({});
  const [selectedIssueKey, setSelectedIssueKey] = useState<string | null>(null);
  const [hintText, setHintText] = useState<string>("");
  const [liveMode, setLiveMode] = useState<boolean>(false);

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

  const getStatusForIssue = (issue: HealthIssue): { label: string; color: string } => {
    const key = issueKey(issue);
    const t = threadsByIssue[key];
    const convo = conversationByIssue[key];
    if (!t) return { label: "Not Started", color: "#607d8b" };
    const state = convo?.state || null;
    if (state) {
      if (state.next_action === "await_user_approval") return { label: "Awaiting Approval", color: "#f57c00" };
      if (state.next_action === "handoff_to_solution_agent") return { label: "Handed Off", color: "#1976d2" };
      return { label: "In Progress", color: "#1976d2" };
    }
    if (t.solThreadId) return { label: "Solution Running", color: "#1976d2" };
    return { label: "In Progress", color: "#1976d2" };
  };

  // Toggle expand/collapse for namespace
  const toggleNamespace = (ns: string) => {
    setExpandedNamespaces(prev => ({ ...prev, [ns]: !prev[ns] }));
  };

  const handleCardClick = async (issue: HealthIssue) => {
    const key = issueKey(issue);
    setSelectedIssueKey(key);
    setTestResult("Loading...");
    const existing = threadsByIssue[key];
    if (liveMode) {
      // WebSocket live mode
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const host = window.location.host;
      const ws = new WebSocket(`${proto}://${host}/api/workflow/ws`);
      ws.onopen = () => {
        ws.send(JSON.stringify({ type: "start", issue }));
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.event === "step") {
            setConversationByIssue(prev => ({ ...prev, [key]: { ...(prev[key] || { diagnostic: [], solution: [] }), state: msg.state || null } }));
          } else if (msg.event === "awaiting_approval") {
            // UI already provides controls; user actions call intervene REST or could send via ws
          } else if (msg.event === "handoff") {
            setThreadsByIssue(prev => ({ ...prev, [key]: { ...(prev[key] || { diagThreadId: msg.diag_thread_id }), solThreadId: msg.sol_thread_id } }));
          } else if (msg.event === "complete") {
            setThreadsByIssue(prev => ({ ...prev, [key]: { diagThreadId: msg.diag_thread_id, solThreadId: msg.sol_thread_id || null } }));
            setConversationByIssue(prev => ({ ...prev, [key]: { ...(prev[key] || {}), diagnostic: msg.history || [], solution: msg.solution_history || [], state: prev[key]?.state || null } }));
            setTestResult(msg);
            ws.close();
          } else if (msg.event === "error") {
            setTestResult(msg);
          }
        } catch (e) {
          // ignore parse errors
        }
      };
      ws.onerror = () => {
        setTestResult({ error: "WebSocket connection error" });
      };
      return;
    }
    if (existing?.diagThreadId) {
      const hist = await getWorkflowHistory(existing.diagThreadId, existing.solThreadId);
      setConversationByIssue(prev => ({ ...prev, [key]: { state: prev[key]?.state, diagnostic: hist.diagnostic, solution: hist.solution } }));
      setTestResult({ diag_thread_id: existing.diagThreadId, sol_thread_id: existing.solThreadId, history: hist });
      return;
    }
    const res = await fetchHealthDiagnostic(issue);
    const diagThreadId: string = res.diag_thread_id;
    const solThreadId: string | null = res.sol_thread_id || null;
    const state: AgentState | null = res.state || null;
    const diagnostic: MessageItem[] = res.history || [];
    setThreadsByIssue(prev => ({ ...prev, [key]: { diagThreadId, solThreadId } }));
    setConversationByIssue(prev => ({ ...prev, [key]: { state, diagnostic, solution: [] } }));
    setTestResult(res);
  };

  const handleApprove = async () => {
    if (!selectedIssueKey) return;
    const t = threadsByIssue[selectedIssueKey];
    if (!t?.diagThreadId) return;
    const res = await interveneWorkflow(t.diagThreadId, "approve");
    const hist = await getWorkflowHistory(res.diag_thread_id, res.sol_thread_id || null);
    setThreadsByIssue(prev => ({ ...prev, [selectedIssueKey]: { diagThreadId: res.diag_thread_id, solThreadId: res.sol_thread_id || null } }));
    setConversationByIssue(prev => ({ ...prev, [selectedIssueKey]: { state: res.state || null, diagnostic: hist.diagnostic, solution: hist.solution } }));
    setTestResult(res);
  };

  const handleDeny = async () => {
    if (!selectedIssueKey) return;
    const t = threadsByIssue[selectedIssueKey];
    if (!t?.diagThreadId) return;
    const res = await interveneWorkflow(t.diagThreadId, "deny", hintText);
    const hist = await getWorkflowHistory(res.diag_thread_id, res.sol_thread_id || null);
    setThreadsByIssue(prev => ({ ...prev, [selectedIssueKey]: { diagThreadId: res.diag_thread_id, solThreadId: res.sol_thread_id || null } }));
    setConversationByIssue(prev => ({ ...prev, [selectedIssueKey]: { state: res.state || null, diagnostic: hist.diagnostic, solution: hist.solution } }));
    setTestResult(res);
  };

  const handleHandoff = async () => {
    if (!selectedIssueKey) return;
    const t = threadsByIssue[selectedIssueKey];
    if (!t?.diagThreadId) return;
    const res = await interveneWorkflow(t.diagThreadId, "handoff");
    const hist = await getWorkflowHistory(res.diag_thread_id, res.sol_thread_id || null);
    setThreadsByIssue(prev => ({ ...prev, [selectedIssueKey]: { diagThreadId: res.diag_thread_id, solThreadId: res.sol_thread_id || null } }));
    setConversationByIssue(prev => ({ ...prev, [selectedIssueKey]: { state: res.state || null, diagnostic: hist.diagnostic, solution: hist.solution } }));
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
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input type="checkbox" checked={liveMode} onChange={e => setLiveMode(e.target.checked)} />
            Live Mode (WebSocket)
          </label>
        </div>
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
                  const status = getStatusForIssue(issue);
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
                      <div style={{ fontWeight: "bold", color: issue.severity === "Critical" ? "#d32f2f" : issue.severity === "High" ? "#f57c00" : issue.severity === "Warning" ? "#fbc02d" : "#1976d2", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span>
                          {issue.severity} - {issue.issueType} ({issue.resourceType})
                        </span>
                        <span style={{
                          fontSize: 12,
                          padding: "2px 8px",
                          borderRadius: 12,
                          background: "#e3f2fd",
                          color: status.color,
                          border: `1px solid ${status.color}`,
                        }}>
                          {status.label}
                        </span>
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
      {selectedIssueKey && (
        <div style={{ marginTop: 32 }}>
          <h3>Diagnostic Workflow</h3>
          <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 12 }}>
            <button onClick={handleApprove} style={{ padding: "8px 12px" }}>Approve</button>
            <button onClick={handleHandoff} style={{ padding: "8px 12px" }}>Handoff</button>
            <input
              value={hintText}
              onChange={e => setHintText(e.target.value)}
              placeholder="Denial reason or hint"
              style={{ padding: "8px", flex: 1 }}
            />
            <button onClick={handleDeny} style={{ padding: "8px 12px" }}>Deny</button>
          </div>
          <div style={{ marginBottom: 12 }}>
            <h4>Agent State</h4>
            <pre style={{ background: "#f5f5f5", padding: 12, borderRadius: 6 }}>
              {JSON.stringify(conversationByIssue[selectedIssueKey]?.state || null, null, 2)}
            </pre>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div>
              <h4>Diagnostic History</h4>
              <pre style={{ background: "#f5f5f5", padding: 12, borderRadius: 6 }}>
                {JSON.stringify(conversationByIssue[selectedIssueKey]?.diagnostic || [], null, 2)}
              </pre>
            </div>
            <div>
              <h4>Solution History</h4>
              <pre style={{ background: "#f5f5f5", padding: 12, borderRadius: 6 }}>
                {JSON.stringify(conversationByIssue[selectedIssueKey]?.solution || [], null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
      {testResult !== null && (
        <div style={{ marginTop: 24 }}>
          <h4>Debug Result</h4>
          <pre style={{ background: "#f5f5f5", padding: 12, borderRadius: 6 }}>
            {JSON.stringify(testResult, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

export default App;
