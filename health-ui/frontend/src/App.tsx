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
          case "handoff_approval":
            handlers.onAwaitingApproval?.(msg);
            break;
          case "resume_available":
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
    ws.onclose = () => {
      // Mark closed so callers can decide to reconnect on next click
      this.ws = null;
    };
  }
  intervene(decision: "approve" | "deny" | "handoff", hint?: string) {
    if (!this.ws) return;
    const payload: any = { type: "intervene", decision };
    if (hint) payload.hint = hint;
    this.ws.send(JSON.stringify(payload));
  }
  resume(decision: "yes" | "no" = "yes") {
    if (!this.ws) return;
    const payload: any = { type: "resume", decision };
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

function SolutionCard({ state }: { state?: any | null }) {
  if (!state) return null;
  const keys = Object.keys(state || {});
  const steps: string[] = (state.steps || state.remediation_steps || state.actions || []) as string[];
  const recommendedFixText: string | undefined = typeof state.recommended_fix === "string" ? state.recommended_fix : (typeof state.recommendation === "string" ? state.recommendation : undefined);
  const recommendedFixObj: any | null = (state.recommended_fix && typeof state.recommended_fix === "object") ? state.recommended_fix : null;
  const escalation: any = state.escalation || state.escalation_email || state.email || null;
  const hasRecommended = !!recommendedFixText || !!recommendedFixObj;
  const hasEscalation = !!escalation;
  const summary = (
    hasRecommended
      ? "Recommended fix is provided."
      : hasEscalation
      ? "Escalation is recommended."
      : (state.summary || state.description || state.detail || state.message || "Solution details provided.")
  ) as string;
  return (
    <div className="solution-card">
      <div className="solution-title">Proposed Solution</div>
      <div className="solution-summary">{summary}</div>
      {Array.isArray(steps) && steps.length > 0 && (
        <ol className="solution-steps">
          {steps.map((s, i) => <li key={i}>{s}</li>)}
        </ol>
      )}
      {recommendedFixText ? (
        <div className="recommended-fix">
          <div className="rf-title">Recommended Fix</div>
          <div className="rf-body">{recommendedFixText}</div>
        </div>
      ) : recommendedFixObj ? (
        <div className="recommended-fix">
          <div className="rf-title">Recommended Fix</div>
          {Array.isArray(recommendedFixObj.steps) && recommendedFixObj.steps.length > 0 && (
            <ol className="solution-steps">
              {recommendedFixObj.steps.map((s: string, i: number) => <li key={i}>{s}</li>)}
            </ol>
          )}
          {recommendedFixObj.notes && (
            <div className="rf-body">{recommendedFixObj.notes}</div>
          )}
        </div>
      ) : escalation ? (
        <div className="escalation-block">
          <div className="escalation-title">Escalation</div>
          {escalation.reason && (<div className="escalation-line">Reason: {escalation.reason}</div>)}
          <details className="email-draft">
            <summary>Email Draft</summary>
            <pre>{escalation.email_draft || escalation.body || "No draft provided."}</pre>
          </details>
        </div>
      ) : null}
      {keys.length === 0 && <div className="solution-summary">No additional details.</div>}
    </div>
  );
}

function DiagnosticPanel({ convo, onApprove, onDeny, onHandoff, onResume, hintText, setHintText }: {
  convo: {
    state?: AgentState | null;
    diagnostic: MessageItem[];
    solution: MessageItem[];
    thoughts?: { text: string; ts: number }[];
    actions?: { text: string; ts: number }[];
    awaitingApprovalQuestion?: string | null;
    awaitingApprovalEvent?: string | null;
    awaitingDecisionInFlight?: boolean;
    isLoading?: boolean;
    rootCause?: string | null;
    solutionState?: any | null;
    steps?: { thought?: string; action?: string; ts: number }[];
  } | undefined;
  onApprove: () => void;
  onDeny: () => void;
  onHandoff: () => void;
  onResume?: () => void;
  hintText: string;
  setHintText: (v: string) => void;
}) {
  // Track which option was clicked to blackout others immediately and show working signal
  const [clickedOption, setClickedOption] = useState<"approve" | "deny" | "handoff" | "resume" | null>(null);

  // Reset clicked option when not awaiting or when no decision is in flight
  useEffect(() => {
    const awaitingNow = !!(convo?.awaitingApprovalQuestion) || (convo?.state?.next_action === "await_user_approval");
    const inFlightNow = !!(convo?.awaitingDecisionInFlight);
    if (!awaitingNow || !inFlightNow) {
      setClickedOption(null);
    }
  }, [convo]);

  if (!convo) return null;
  const awaiting = !!convo.awaitingApprovalQuestion || convo.state?.next_action === "await_user_approval";
  const awaitingEvent = convo.awaitingApprovalEvent || "";
  const disabled = !!convo.awaitingDecisionInFlight;
  const lockAll = disabled || clickedOption !== null; // lock and blackout others once an option is clicked
  const glowStyle = lockAll ? { textShadow: "0 0 8px rgba(0,200,255,0.9), 0 0 18px rgba(0,200,255,0.6)" } as const : {} as const;

  const handleOptionClick = (type: "approve" | "deny" | "handoff" | "resume") => {
    setClickedOption(type);
    switch (type) {
      case "approve":
        onApprove();
        break;
      case "deny":
        onDeny();
        break;
      case "handoff":
        onHandoff();
        break;
      case "resume":
        onResume?.();
        break;
    }
  };
  const hasRoot = !!convo.rootCause;
  return (
    <div className="diagnostic-panel dark">
      {convo.isLoading && (
        <div className="loading-strip">
          <div className="spinner" aria-label="Loading" />
          <span>Connecting to diagnostic agent…</span>
        </div>
      )}
      {hasRoot && (
        <div className="root-banner">
          <div className="root-title">CRITICAL: Identified Root Cause</div>
          <div className="root-body">{convo.rootCause}</div>
        </div>
      )}
      <div className="live-analysis">
        <div className="panel-heading">Diagnostic Pipeline</div>
        <div className="pipeline-list">
          {(convo.steps || []).map((s, i) => (
            <div key={i} className="pipeline-card">
              {s.thought && (
                <div className="pipeline-thought">
                  <span className="code-tag">thought</span>
                  <span className="code-text">{s.thought}</span>
                </div>
              )}
              {s.action && (
                <div className="pipeline-action">
                  <span className="code-tag action">action</span>
                  <button className="action-pill" title={s.action}>{s.action}</button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
      {awaiting && (
        <div className="approval-banner dark">
          <div className="question" style={{ marginBottom: 12, ...glowStyle }}>{convo.awaitingApprovalQuestion || "Action requires your decision."}</div>
          <div className="actions" style={{ gap: 8, display: "flex", alignItems: "center", flexWrap: "wrap" }}>
            {awaitingEvent === "handoff_approval" ? (
              <>
                <button
                  className="btn primary"
                  onClick={() => handleOptionClick("approve")}
                  disabled={disabled || lockAll}
                  style={lockAll && clickedOption !== "approve" ? { backgroundColor: "#000", color: "#fff", opacity: 0.6, borderColor: "#000", cursor: "not-allowed" } : undefined}
                >
                  Approve
                </button>
                <button
                  className="btn"
                  onClick={() => handleOptionClick("deny")}
                  disabled={disabled || lockAll}
                  style={lockAll && clickedOption !== "deny" ? { backgroundColor: "#000", color: "#fff", opacity: 0.6, borderColor: "#000", cursor: "not-allowed" } : undefined}
                >
                  Deny
                </button>
                <input
                  className="hint-input"
                  value={hintText}
                  onChange={e => setHintText(e.target.value)}
                  placeholder="Optional hint/reason"
                  disabled={disabled || lockAll}
                  style={lockAll ? { backgroundColor: "#111", color: "#888" } : undefined}
                />
              </>
            ) : awaitingEvent === "awaiting_approval" ? (
              <>
                <button
                  className="btn primary"
                  onClick={() => handleOptionClick("approve")}
                  disabled={disabled || lockAll}
                  style={lockAll && clickedOption !== "approve" ? { backgroundColor: "#000", color: "#fff", opacity: 0.6, borderColor: "#000", cursor: "not-allowed" } : undefined}
                >
                  Approve
                </button>
                <button
                  className="btn"
                  onClick={() => handleOptionClick("deny")}
                  disabled={disabled || lockAll}
                  style={lockAll && clickedOption !== "deny" ? { backgroundColor: "#000", color: "#fff", opacity: 0.6, borderColor: "#000", cursor: "not-allowed" } : undefined}
                >
                  Deny
                </button>
                <button
                  className="btn"
                  onClick={() => handleOptionClick("handoff")}
                  disabled={disabled || lockAll}
                  style={lockAll && clickedOption !== "handoff" ? { backgroundColor: "#000", color: "#fff", opacity: 0.6, borderColor: "#000", cursor: "not-allowed" } : undefined}
                >
                  Manual Handoff
                </button>
              </>
            ) : awaitingEvent === "resume_available" ? (
              <>
                <button
                  className="btn primary"
                  onClick={() => handleOptionClick("resume")}
                  disabled={disabled || lockAll}
                  style={lockAll && clickedOption !== "resume" ? { backgroundColor: "#000", color: "#fff", opacity: 0.6, borderColor: "#000", cursor: "not-allowed" } : undefined}
                >
                  Resume
                </button>
              </>
            ) : (
              <>
                <button
                  className="btn primary"
                  onClick={() => handleOptionClick("approve")}
                  disabled={disabled || lockAll}
                  style={lockAll && clickedOption !== "approve" ? { backgroundColor: "#000", color: "#fff", opacity: 0.6, borderColor: "#000", cursor: "not-allowed" } : undefined}
                >
                  Approve
                </button>
                <button
                  className="btn"
                  onClick={() => handleOptionClick("deny")}
                  disabled={disabled || lockAll}
                  style={lockAll && clickedOption !== "deny" ? { backgroundColor: "#000", color: "#fff", opacity: 0.6, borderColor: "#000", cursor: "not-allowed" } : undefined}
                >
                  Deny
                </button>
              </>
            )}
          </div>
        </div>
      )}
      {convo.solutionState && (
        <SolutionCard state={convo.solutionState} />
      )}
    </div>
  );
}

function App()
{
  const [issues, setIssues] = useState<HealthIssue[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedNamespaces, setExpandedNamespaces] = useState<Record<string, boolean>>({});
  const [threadsByIssue, setThreadsByIssue] = useState<Record<string, { diagThreadId: string; solThreadId?: string | null }>>({});
  const [conversationByIssue, setConversationByIssue] = useState<Record<string, { state?: AgentState | null; diagnostic: MessageItem[]; solution: MessageItem[]; thoughts?: { text: string; ts: number }[]; actions?: { text: string; ts: number }[]; awaitingApprovalQuestion?: string | null; awaitingApprovalEvent?: string | null; awaitingDecisionInFlight?: boolean; isLoading?: boolean; rootCause?: string | null; solutionState?: any | null; steps?: { thought?: string; action?: string; ts: number }[] }>>({});
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
      if (state.next_action === "handoff_to_solution_agent") return { label: "Await Handoff Approval", color: "#f57c00" };
      return { label: "In Progress", color: "#1976d2" };
    }
    if (t.solThreadId) return { label: "Handoff", color: "#1976d2" };
    return { label: "In Progress", color: "#1976d2" };
  };

  const handleCardClick = (issue: HealthIssue) => {
    const key = issue.issueId;
    setSelectedIssueKey(key);
    // Optimistically ensure a convo object exists to avoid blank panel flicker
    setConversationByIssue(prev => ({
      ...prev,
      [key]: prev[key] || { state: null, diagnostic: [], solution: [], thoughts: [], actions: [], awaitingApprovalQuestion: null, awaitingApprovalEvent: null, awaitingDecisionInFlight: false, isLoading: true, rootCause: null, solutionState: null, steps: [] }
    }));
    // Ensure client exists per issue
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const host = window.location.host;
    const url = `${proto}://${host}/api/workflow/ws`;
    const existing = wsClientsRef.current[key];
    if (existing?.ws) {
      try { existing.close(); } catch { /* ignore */ }
      wsClientsRef.current[key] = undefined as any;
    }
    {
      wsClientsRef.current[key] = new WorkflowWSClient(url);
      wsClientsRef.current[key].connect(issue, {
        onOpen: () => {
          setConversationByIssue(prev => ({ ...prev, [key]: { state: null, diagnostic: [], solution: [], thoughts: [], actions: [], awaitingApprovalQuestion: null, awaitingApprovalEvent: null, awaitingDecisionInFlight: false, isLoading: true, rootCause: null, solutionState: null, steps: [] } }));
        },
        onDiagnostic: (msg) => {
          const state: AgentState | null = msg.state || null;
          const thought = state?.thought || "";
          const action = state?.action || "";
          const root = state?.root_cause || null;
          setConversationByIssue(prev => {
            const base = prev[key] || { state: null, diagnostic: [], solution: [], thoughts: [], actions: [], awaitingApprovalQuestion: null, awaitingApprovalEvent: null, awaitingDecisionInFlight: false, rootCause: null, solutionState: null, steps: [] };
            const thoughts = base.thoughts || [];
            const actions = base.actions || [];
            const steps = base.steps || [];
            const thoughtExists = thought ? thoughts.some(t => t.text === thought) : false;
            const actionExists = action ? actions.some(a => a.text === action) : false;
            const stepExists = (thought || action) ? steps.some(s => (s.thought || "") === (thought || "") && (s.action || "") === (action || "")) : false;
            const newThoughts = thought && !thoughtExists ? [...thoughts, { text: thought, ts: Date.now() }] : thoughts;
            const newActions = action && !actionExists ? [...actions, { text: action, ts: Date.now() }] : actions;
            const newSteps = (thought || action) && !stepExists ? [...steps, { thought: thought || undefined, action: action || undefined, ts: Date.now() }] : steps;
            return { ...prev, [key]: { ...base, state, thoughts: newThoughts, actions: newActions, steps: newSteps, awaitingDecisionInFlight: false, isLoading: false, rootCause: root || base.rootCause || null } };
          });
          setThreadsByIssue(prev => ({ ...prev, [key]: { diagThreadId: msg.diag_thread_id, solThreadId: prev[key]?.solThreadId || null } }));
        },
        onHistory: (msg) => {
          const diag = (msg.diag_history || []) as MessageItem[];
          const sol = (msg.sol_history || []) as MessageItem[];
          const derivedThoughts: { text: string; ts: number }[] = [];
          const derivedActions: { text: string; ts: number }[] = [];
          const derivedSteps: { thought?: string; action?: string; ts: number }[] = [];
          let derivedRoot: string | null = null;
          diag.forEach((m: any) => {
            const txt: string = m.text || "";
            try {
              const obj = JSON.parse(txt);
              if (obj && typeof obj === "object") {
                if (obj.thought) derivedThoughts.push({ text: obj.thought, ts: Date.now() });
                if (obj.action) derivedActions.push({ text: obj.action, ts: Date.now() });
                if (obj.thought || obj.action) derivedSteps.push({ thought: obj.thought, action: obj.action, ts: Date.now() });
                if (!derivedRoot && obj.root_cause) derivedRoot = obj.root_cause;
              }
            } catch (_) {
              if (txt) {
                derivedThoughts.push({ text: txt, ts: Date.now() });
                derivedSteps.push({ thought: txt, ts: Date.now() });
              }
            }
          });
          let solutionState: any | null = null;
          const lastSol = sol.length ? sol[sol.length - 1] : null;
          if (lastSol && lastSol.text) {
            try { solutionState = JSON.parse(lastSol.text); } catch (_) { solutionState = { summary: lastSol.text }; }
          }
          setConversationByIssue(prev => ({
            ...prev,
            [key]: {
              ...(prev[key] || { state: null, awaitingApprovalQuestion: null, awaitingApprovalEvent: null, awaitingDecisionInFlight: false, isLoading: false }),
              diagnostic: diag,
              solution: sol,
              thoughts: derivedThoughts,
              actions: derivedActions,
              steps: derivedSteps,
              solutionState: solutionState ?? prev[key]?.solutionState ?? null,
              rootCause: derivedRoot ?? prev[key]?.rootCause ?? null,
              awaitingDecisionInFlight: false,
              isLoading: false,
            },
          }));
          setThreadsByIssue(prev => ({ ...prev, [key]: { diagThreadId: msg.diag_thread_id, solThreadId: msg.sol_thread_id || null } }));
        },
        onAwaitingApproval: (msg) => {
          setConversationByIssue(prev => ({ ...prev, [key]: { ...(prev[key] || { state: null, diagnostic: [], solution: [], thoughts: [], actions: [], solutionState: null, rootCause: null }), awaitingApprovalQuestion: msg.question || "Approve next action?", awaitingApprovalEvent: msg.event || null, awaitingDecisionInFlight: false, isLoading: false } }));
        },
        onHandoff: (msg) => {
          setThreadsByIssue(prev => ({ ...prev, [key]: { ...(prev[key] || { diagThreadId: msg.diag_thread_id }), solThreadId: msg.sol_thread_id } }));
          setConversationByIssue(prev => ({ ...prev, [key]: { ...(prev[key] || {}), awaitingApprovalQuestion: null, awaitingApprovalEvent: null, awaitingDecisionInFlight: false, isLoading: false, solutionState: msg.state || prev[key]?.solutionState || null } }));
        },
        onComplete: (msg) => {
          setThreadsByIssue(prev => ({ ...prev, [key]: { diagThreadId: msg.diag_thread_id, solThreadId: msg.sol_thread_id || prev[key]?.solThreadId || null } }));
          setConversationByIssue(prev => ({ ...prev, [key]: { ...(prev[key] || {}), awaitingDecisionInFlight: false, isLoading: false } }));
        },
        onError: (msg) => {
          console.warn("Workflow error", msg);
        },
      });
    }
  };

  const handleApprove = () => {
    if (!selectedIssueKey) return;
    wsClientsRef.current[selectedIssueKey]?.intervene("approve");
    setConversationByIssue(prev => ({ ...prev, [selectedIssueKey]: { ...(prev[selectedIssueKey] || {}), awaitingDecisionInFlight: true } }));
  };
  const handleDeny = () => {
    if (!selectedIssueKey) return;
    wsClientsRef.current[selectedIssueKey]?.intervene("deny", hintText);
    setHintText("");
    setConversationByIssue(prev => ({ ...prev, [selectedIssueKey]: { ...(prev[selectedIssueKey] || {}), awaitingDecisionInFlight: true } }));
  };
  const handleHandoff = () => {
    if (!selectedIssueKey) return;
    wsClientsRef.current[selectedIssueKey]?.intervene("handoff");
    setConversationByIssue(prev => ({ ...prev, [selectedIssueKey]: { ...(prev[selectedIssueKey] || {}), awaitingDecisionInFlight: true } }));
  };
  const handleResume = () => {
    if (!selectedIssueKey) return;
    wsClientsRef.current[selectedIssueKey]?.resume("yes");
    setConversationByIssue(prev => ({ ...prev, [selectedIssueKey]: { ...(prev[selectedIssueKey] || {}), awaitingDecisionInFlight: true } }));
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
      <div className={selectedIssueKey ? "grid" : "grid single"}>
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
        {selectedIssueKey && (
          <div className="right-pane">
            <DiagnosticPanel
              convo={conversationByIssue[selectedIssueKey]}
              onApprove={handleApprove}
              onDeny={handleDeny}
              onHandoff={handleHandoff}
              onResume={handleResume}
              hintText={hintText}
              setHintText={setHintText}
            />
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
