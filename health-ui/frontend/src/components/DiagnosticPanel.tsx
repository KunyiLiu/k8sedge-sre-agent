import { useEffect, useState } from "react";
import type { AgentState, MessageItem } from "../api";
import { SolutionCard } from "./SolutionCard";

export function DiagnosticPanel({ convo, onApprove, onDeny, onHandoff, onResume, hintText, setHintText }: {
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
  const [clickedOption, setClickedOption] = useState<"approve" | "deny" | "handoff" | "resume" | null>(null);

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
  const lockAll = disabled || clickedOption !== null;
  const isHandoffEvent = awaitingEvent === "handoff_approval";
  const isHandoffInFlight = isHandoffEvent && disabled;
  const glowStyle = !disabled && awaiting
    ? { textShadow: "0 0 8px rgba(0,200,255,0.9), 0 0 18px rgba(0,200,255,0.6)" } as const
    : {} as const;

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
          <div className="question" style={{ marginBottom: 12, ...glowStyle }}>
            {isHandoffInFlight ? (
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className="spinner spinner-inline" aria-label="Handing off" />
                <span>Handing off to solution agent...</span>
              </span>
            ) : (
              convo.awaitingApprovalQuestion || "Action requires your decision."
            )}
          </div>
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
