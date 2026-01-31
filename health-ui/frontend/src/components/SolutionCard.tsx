export function SolutionCard({ state }: { state?: any | null }) {
  if (!state) return null;
  const keys = Object.keys(state || {});
  const steps: string[] = (state.steps || state.remediation_steps || state.actions || []) as string[];
  const recommendedFixText: string | undefined = typeof state.recommended_fix === "string"
    ? state.recommended_fix
    : (typeof state.recommendation === "string" ? state.recommendation : undefined);
  const recommendedFixObj: any | null = (state.recommended_fix && typeof state.recommended_fix === "object")
    ? state.recommended_fix
    : null;
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
            <div className="email-draft-header">
              <button
                type="button"
                className="btn btn-ghost copy-button"
                onClick={() => {
                  const text = escalation.email_draft || escalation.body || "";
                  if (!text) return;
                  if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(text).catch(() => {
                      try {
                        const t = document.createElement("textarea");
                        t.value = text;
                        document.body.appendChild(t);
                        t.select();
                        document.execCommand("copy");
                        document.body.removeChild(t);
                      } catch { /* ignore */ }
                    });
                  }
                }}
              >
                Copy
              </button>
              <button
                type="button"
                className="btn btn-ghost open-email-button"
                onClick={() => {
                  const rawBody: string = escalation.email_draft || escalation.body || "";
                  if (!rawBody) return;

                  // Extract subject from the body if present: line starting with "Subject: ..."
                  const subjectMatch = rawBody.match(/^\s*Subject:\s*(.+)$/m);
                  const extractedSubject = subjectMatch ? subjectMatch[1].trim() : undefined;
                  // Remove the subject line from the body for the email body
                  const bodyWithoutSubject = rawBody.replace(/^\s*Subject:.*\r?\n/, "");

                  // Fallback to reason/severity only if no subject is embedded in body
                  const reason: string = escalation.reason || "K8s incident escalation";
                  const severity: string | undefined = escalation.severity;
                  const subjectBase = extractedSubject
                    ? extractedSubject
                    : (severity ? `[${severity.toUpperCase()}] ${reason}` : reason);

                  const subject = encodeURIComponent(subjectBase);
                  const encodedBody = encodeURIComponent(bodyWithoutSubject);
                  const mailto = `mailto:?subject=${subject}&body=${encodedBody}`;
                  try {
                    window.location.href = mailto;
                  } catch {
                    // best-effort only
                  }
                }}
              >
                Open in Email
              </button>
            </div>
            <pre>{escalation.email_draft || escalation.body || "No draft provided."}</pre>
          </details>
        </div>
      ) : null}
      {keys.length === 0 && <div className="solution-summary">No additional details.</div>}
    </div>
  );
}
