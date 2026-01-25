import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { FiRefreshCw } from "react-icons/fi";
import {
  fetchTestMetric,
  type HealthIssue,
  type AgentState,
  type MessageItem
} from "./api";
import "./App.css";

// Severity sort order
const severityOrder: Record<HealthIssue["severity"], number> = { Critical: 0, High: 1, Warning: 2, Info: 3 };

// Simple WebSocket workflow client to manage one connection per issue
class WorkflowWSClient {
  ws: WebSocket | null = null;
  url: string;
  constructor(url: string) {
    this.url = url;
  }
  connect(issue: HealthIssue, handlers: {
    onOpen?: () => void;
    onDiagnostic?: (payload: any) => void;
    onHistory?: (payload: any) => void;
    onAwaitingApproval?: (payload: any) => void;
    onHandoff?: (payload: any) => void;
    onComplete?: (payload: any) => void;
    onError?: (payload: any) => void;
  }) {
    const ws = new WebSocket(this.url);
    this.ws = ws;
    ws.onopen = () => {
      handlers.onOpen?.();
      ws.send(JSON.stringify({ type: "start", issue }));
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        switch (msg.event) {
          case "diagnostic":
            handlers.onDiagnostic?.(msg);
            break;
          case "history":
            handlers.onHistory?.(msg);
            break;
          case "awaiting_approval":
            handlers.onAwaitingApproval?.(msg);
            break;
          case "handoff":
            handlers.onHandoff?.(msg);
            break;
          case "complete":
            handlers.onComplete?.(msg);
            break;
          case "error":
            handlers.onError?.(msg);
            break;
          default:
            break;
        }
      } catch (_) {
        // ignore parse errors
      }
    };
    ws.onerror = () => {
      handlers.onError?.({ error: "WebSocket connection error" });
    };
  }
  intervene(decision: "approve" | "deny" | "handoff", hint?: string) {
    if (!this.ws) return;
    const payload: any = { type: "intervene", decision };
    if (hint) payload.hint = hint;
    this.ws.send(JSON.stringify(payload));
  }
  close() {
    try { this.ws?.close(); } catch (_) {}
    this.ws = null;
  }
}

function IssueCard({ issue, status, onClick, rootCause }: {
  issue: HealthIssue;
  status: { label: string; color: string };
  onClick: () => void;
  rootCause?: string | null;
}) {
  const sevClass = issue.severity === "Critical" ? "severity-critical" : issue.severity === "High" ? "severity-high" : issue.severity === "Warning" ? "severity-warning" : "severity-info";
  return (
    <div className={`issue-card ${sevClass}`} onClick={onClick}>
      <div className="issue-card-header">
        <span>{issue.severity} - {issue.issueType} ({issue.resourceType})</span>
        <span className="status-badge" style={{ color: status.color, borderColor: status.color }}>{status.label}</span>
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

function DiagnosticPanel({ convo, onApprove, onDeny, onHandoff, hintText, setHintText }: {
  convo: {
    state?: AgentState | null;
    diagnostic: MessageItem[];
    solution: MessageItem[];
    thoughts?: { text: string; ts: number }[];
    actions?: { text: string; ts: number }[];
    awaitingApprovalQuestion?: string | null;
  } | undefined;
  onApprove: () => void;
  onDeny: () => void;
  onHandoff: () => void;
  hintText: string;
  setHintText: (v: string) => void;
}) {
  if (!convo) return <div className="diagnostic-panel"><div className="placeholder">Select an issue to start diagnosis</div></div>;
  const awaiting = !!convo.awaitingApprovalQuestion || convo.state?.next_action === "await_user_approval";
  return (
    <div className="diagnostic-panel">
      <h3>Diagnostic Workflow</h3>
      {awaiting && (
        <div className="approval-banner">
          <div className="question">{convo.awaitingApprovalQuestion || "Approve next action?"}</div>
          <div className="actions">
            <button className="btn" onClick={onApprove}>Approve</button>
            <button className="btn" onClick={onHandoff}>Handoff</button>
            <input className="hint-input" value={hintText} onChange={e => setHintText(e.target.value)} placeholder="Denial reason or hint" />
            <button className="btn" onClick={onDeny}>Deny</button>
          </div>
        </div>
      )}
      <div className="panel-grid">
        <div>
          <h4>Agent State</h4>
          <pre className="pre-box">{JSON.stringify(convo.state || null, null, 2)}</pre>
        </div>
        <div>
          <h4>Thought Stream</h4>
          <ul className="stream-list">
            {(convo.thoughts || []).map((t, i) => (
              <li key={i}>{t.text}</li>
            ))}
          </ul>
        </div>
      </div>
      <div className="panel-grid">
        <div>
          <h4>Proposed Actions</h4>
          <div className="actions-list">
            {(convo.actions || []).map((a, i) => (
              <button className="action-pill" key={i} title={a.text}>{a.text}</button>
            ))}
          </div>
        </div>
        <div>
          <h4>Diagnostic History</h4>
          <pre className="pre-box">{JSON.stringify(convo.diagnostic || [], null, 2)}</pre>
        </div>
      </div>
      <div className="panel-grid">
        <div>
          <h4>Solution History</h4>
          <pre className="pre-box">{JSON.stringify(convo.solution || [], null, 2)}</pre>
        </div>
      </div>
    </div>
  );
}

function App() {
  const [issues, setIssues] = useState<HealthIssue[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedNamespaces, setExpandedNamespaces] = useState<Record<string, boolean>>({});
  const [threadsByIssue, setThreadsByIssue] = useState<Record<string, { diagThreadId: string; solThreadId?: string | null }>>({});
  const [conversationByIssue, setConversationByIssue] = useState<Record<string, { state?: AgentState | null; diagnostic: MessageItem[]; solution: MessageItem[]; thoughts?: { text: string; ts: number }[]; actions?: { text: string; ts: number }[]; awaitingApprovalQuestion?: string | null; rootCause?: string | null }>>({});
  const [selectedIssueKey, setSelectedIssueKey] = useState<string | null>(null);
  const [hintText, setHintText] = useState<string>("");
  const wsClientsRef = useRef<Record<string, WorkflowWSClient>>({});

  const loadIssues = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchTestMetric();
      setIssues(data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadIssues();
  }, [loadIssues]);

  const issuesByNamespace = useMemo(() => {
    const grouped: Record<string, HealthIssue[]> = {};
    for (const issue of issues) {
      const ns = issue.namespace || "default";
      if (!grouped[ns]) grouped[ns] = [];
      grouped[ns].push(issue);
    }
    Object.keys(grouped).forEach(ns => {
      grouped[ns] = [...grouped[ns]].sort((a, b) => {
        const sevA = severityOrder[a.severity] ?? 99;
        const sevB = severityOrder[b.severity] ?? 99;
        if (sevA !== sevB) return sevA - sevB;
        return b.unhealthyTimespan - a.unhealthyTimespan;
      });
    });
    return grouped;
  }, [issues]);

  const toggleNamespace = (ns: string) => {
    setExpandedNamespaces(prev => ({ ...prev, [ns]: !prev[ns] }));
  };

  const getStatusForIssue = (issue: HealthIssue): { label: string; color: string } => {
    const key = issue.issueId;
    const t = threadsByIssue[key];
    const convo = conversationByIssue[key];
    if (!t) return { label: "Not Started", color: "#607d8b" };
    const state = convo?.state || null;
    if (state) {
      if (state.next_action === "await_user_approval") return { label: "Await User Approval", color: "#f57c00" };
      if (state.next_action === "handoff_to_solution_agent") return { label: "Handoff", color: "#1976d2" };
      return { label: "In Progress", color: "#1976d2" };
    }
    if (t.solThreadId) return { label: "Handoff", color: "#1976d2" };
    return { label: "In Progress", color: "#1976d2" };
  };

  const handleCardClick = (issue: HealthIssue) => {
    const key = issue.issueId;
    setSelectedIssueKey(key);
    // Ensure client exists per issue
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const host = window.location.host;
    const url = `${proto}://${host}/api/workflow/ws`;
    if (!wsClientsRef.current[key]) {
      wsClientsRef.current[key] = new WorkflowWSClient(url);
      wsClientsRef.current[key].connect(issue, {
        onOpen: () => {
          // Reset convo containers on fresh connect
          setConversationByIssue(prev => ({ ...prev, [key]: { state: null, diagnostic: [], solution: [], thoughts: [], actions: [], awaitingApprovalQuestion: null, rootCause: null } }));
        },
        onDiagnostic: (msg) => {
          const state: AgentState | null = msg.state || null;
          const thought = state?.thought || "";
          const action = state?.action || "";
          const root = state?.root_cause || null;
          setConversationByIssue(prev => {
            const base = prev[key] || { state: null, diagnostic: [], solution: [], thoughts: [], actions: [], awaitingApprovalQuestion: null, rootCause: null };
            const thoughts = base.thoughts || [];
            const actions = base.actions || [];
            const newThoughts = thought ? [...thoughts, { text: thought, ts: Date.now() }] : thoughts;
            const newActions = action ? [...actions, { text: action, ts: Date.now() }] : actions;
            return { ...prev, [key]: { ...base, state, thoughts: newThoughts, actions: newActions, rootCause: root || base.rootCause || null } };
          });
          // Track threads
          setThreadsByIssue(prev => ({ ...prev, [key]: { diagThreadId: msg.diag_thread_id, solThreadId: prev[key]?.solThreadId || null } }));
        },
        onHistory: (msg) => {
          const diag = (msg.diag_history || []) as MessageItem[];
          const sol = (msg.sol_history || []) as MessageItem[];
          setConversationByIssue(prev => ({ ...prev, [key]: { ...(prev[key] || { state: null }), diagnostic: diag, solution: sol } }));
          setThreadsByIssue(prev => ({ ...prev, [key]: { diagThreadId: msg.diag_thread_id, solThreadId: msg.sol_thread_id || null } }));
        },
        onAwaitingApproval: (msg) => {
          setConversationByIssue(prev => ({ ...prev, [key]: { ...(prev[key] || { state: null, diagnostic: [], solution: [], thoughts: [], actions: [] }), awaitingApprovalQuestion: msg.question || "Approve next action?" } }));
        },
        onHandoff: (msg) => {
          setThreadsByIssue(prev => ({ ...prev, [key]: { ...(prev[key] || { diagThreadId: msg.diag_thread_id }), solThreadId: msg.sol_thread_id } }));
          // Clear awaiting approval when handoff occurs
          setConversationByIssue(prev => ({ ...prev, [key]: { ...(prev[key] || {}), awaitingApprovalQuestion: null } }));
        },
        onComplete: (msg) => {
          setThreadsByIssue(prev => ({ ...prev, [key]: { diagThreadId: msg.diag_thread_id, solThreadId: msg.sol_thread_id || prev[key]?.solThreadId || null } }));
        },
        onError: (msg) => {
          setConversationByIssue(prev => ({ ...prev, [key]: { ...(prev[key] || { state: null, diagnostic: [], solution: [] }), awaitingApprovalQuestion: null } }));
          console.warn("Workflow error", msg);
        },
      });
    } else {
      // Already connected, do nothing
    }
  };

  const handleApprove = () => {
    if (!selectedIssueKey) return;
    wsClientsRef.current[selectedIssueKey]?.intervene("approve");
  };
  const handleDeny = () => {
    if (!selectedIssueKey) return;
    wsClientsRef.current[selectedIssueKey]?.intervene("deny", hintText);
    setHintText("");
  };
  const handleHandoff = () => {
    if (!selectedIssueKey) return;
    wsClientsRef.current[selectedIssueKey]?.intervene("handoff");
  };

  useEffect(() => {
    return () => {
      // Cleanup all open sockets on unmount
      Object.values(wsClientsRef.current).forEach(c => c.close());
    };
  }, []);

  return (
    <div className="app-container">
      <h1 className="header">K8s SRE Agent</h1>
      <button className="refresh-button" onClick={loadIssues} disabled={loading} title="Manual Refresh">
        <FiRefreshCw />
        <span className="sr-only">Manual Refresh</span>
      </button>
      <div className="grid">
        <div className="left-pane">
          {Object.entries(issuesByNamespace).map(([ns, nsIssues]) => (
            <div key={ns} className="namespace-group">
              <div className="namespace-header" onClick={() => toggleNamespace(ns)}>
                <span>Namespace [{ns}] - {nsIssues.length} Issue{nsIssues.length !== 1 ? "s" : ""}</span>
                <span className="expand-icon">{expandedNamespaces[ns] ? "▼" : "▶"}</span>
              </div>
              {expandedNamespaces[ns] && (
                <div className="namespace-body">
                  {nsIssues.map((issue, idx) => {
                    const status = getStatusForIssue(issue);
                    const key = issue.issueId;
                    const rootCause = conversationByIssue[key]?.rootCause || null;
                    return (
                      <IssueCard
                        key={idx}
                        issue={issue}
                        status={status}
                        rootCause={rootCause}
                        onClick={() => handleCardClick(issue)}
                      />
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
        <div className="right-pane">
          <DiagnosticPanel
            convo={selectedIssueKey ? conversationByIssue[selectedIssueKey] : undefined}
            onApprove={handleApprove}
            onDeny={handleDeny}
            onHandoff={handleHandoff}
            hintText={hintText}
            setHintText={setHintText}
          />
        </div>
      </div>
    </div>
  );
}

export default App;
