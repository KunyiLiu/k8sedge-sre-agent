import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { FiRefreshCw, FiActivity } from "react-icons/fi";
import {
  fetchTestMetric,
  type HealthIssue,
  type AgentState,
  type MessageItem
} from "./api";
import "./App.css";
import { WorkflowWSClient } from "./workflow/WorkflowWSClient";
import { IssueCard } from "./components/IssueCard";
import { DiagnosticPanel } from "./components/DiagnosticPanel";

// Severity sort order
const severityOrder: Record<HealthIssue["severity"], number> = { Critical: 0, High: 1, Warning: 2, Info: 3 };

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

  // Periodically refresh issues every 15 minutes
  useEffect(() => {
    const interval = setInterval(() => {
      loadIssues();
    }, 15 * 60 * 1000);
    return () => clearInterval(interval);
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

  const getStatusForIssue = (issue: HealthIssue): { label: string; color: string; handingOff?: boolean } => {
    const key = issue.issueId;
    const t = threadsByIssue[key];
    const convo = conversationByIssue[key];
    if (!t && !convo) return { label: "Not Started", color: "#607d8b" };

    // While a handoff approval decision is being processed, show a transient "Handing off" state
    if (convo?.awaitingDecisionInFlight && convo.awaitingApprovalEvent === "handoff_approval") {
      return { label: "Handing off...", color: "#00bcd4", handingOff: true };
    }

    // While a resume decision is being processed, show a transient "Resuming" state
    if (convo?.awaitingDecisionInFlight && convo.awaitingApprovalEvent === "resume_available") {
      return { label: "Resuming...", color: "#00bcd4", handingOff: true };
    }

    // If a solution thread or parsed solution state exists, prefer showing a handoff/solution status
    if (t?.solThreadId || convo?.solutionState) {
      return { label: "Handoff", color: "#1976d2" };
    }

    const state = convo?.state || null;
    if (state) {
      if (state.next_action === "await_user_approval") return { label: "Await User Approval", color: "#f57c00" };
      if (state.next_action === "handoff_to_solution_agent") return { label: "Await Handoff Approval", color: "#f57c00" };
      return { label: "In Progress", color: "#1976d2" };
    }

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
    // Optimistically clear the resume question so the banner disappears
    setConversationByIssue(prev => ({
      ...prev,
      [selectedIssueKey]: {
        ...(prev[selectedIssueKey] || {}),
        awaitingApprovalQuestion: null,
        awaitingApprovalEvent: null,
        awaitingDecisionInFlight: true,
      },
    }));
  };
  useEffect(() => {
    return () => {
      // Cleanup all open sockets on unmount
      Object.values(wsClientsRef.current).forEach(c => c.close());
    };
  }, []);

  useEffect(() => {
    // Build a set of current issueIds from latest API data
    const currentIds = new Set(issues.map(i => i.issueId));

    // If the selected issue no longer exists, clear the selection
    if (selectedIssueKey && !currentIds.has(selectedIssueKey)) {
      setSelectedIssueKey(null);
    }

    // Close WS clients for removed issues and prune state
    const newConvo: typeof conversationByIssue = {};
    const newThreads: typeof threadsByIssue = {};

    Object.keys(wsClientsRef.current).forEach(key => {
      if (!currentIds.has(key)) {
        // issue no longer present -> close and drop client
        try { wsClientsRef.current[key]?.close(); } catch {}
        delete wsClientsRef.current[key];
      }
    });

    Object.entries(conversationByIssue).forEach(([key, value]) => {
      if (currentIds.has(key)) newConvo[key] = value;
    });
    Object.entries(threadsByIssue).forEach(([key, value]) => {
      if (currentIds.has(key)) newThreads[key] = value;
    });

    if (Object.keys(newConvo).length !== Object.keys(conversationByIssue).length) {
      setConversationByIssue(newConvo);
    }
    if (Object.keys(newThreads).length !== Object.keys(threadsByIssue).length) {
      setThreadsByIssue(newThreads);
    }
  }, [issues, selectedIssueKey, conversationByIssue, threadsByIssue]);

  return (
    <div className="app-root">
      <div className="app-container">
        <header className="app-header">
          <div className="app-title-block">
            <span className="app-logo" aria-hidden="true">
              <FiActivity />
            </span>
            <div>
              <h1 className="header">K8s SRE Agent</h1>
              <p className="header-subtitle">Autonomous troubleshooting and guided remediation for your clusters</p>
            </div>
          </div>
          <button className="refresh-button" onClick={loadIssues} disabled={loading} title="Manual Refresh">
            <FiRefreshCw />
            <span className="sr-only">Manual Refresh</span>
          </button>
        </header>
        <div className={selectedIssueKey ? "grid" : "grid single"}>
          <div className="left-pane">
            {Object.entries(issuesByNamespace).map(([ns, nsIssues]) => (
              <div key={ns} className="namespace-group">
                <div className="namespace-header" onClick={() => toggleNamespace(ns)}>
                  <span>
                    Namespace [{ns}] - {nsIssues.length} Issue{nsIssues.length !== 1 ? "s" : ""}
                  </span>
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
                          selected={selectedIssueKey === key}
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
    </div>
  );
}

export default App;
