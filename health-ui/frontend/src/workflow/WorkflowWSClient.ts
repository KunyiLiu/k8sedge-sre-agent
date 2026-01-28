import type { HealthIssue } from "../api";

// Simple WebSocket workflow client to manage one connection per issue
export class WorkflowWSClient {
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
