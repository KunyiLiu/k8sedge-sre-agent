from enum import Enum
from pydantic import BaseModel, model_validator
from typing import Any, Dict, List, Optional, Literal, Union
import hashlib

class ResourceType(str, Enum):
    Pod = "Pod"
    Node = "Node"
    Deployment = "Deployment"
    Other = "Other"

class HealthIssue(BaseModel):
    issueType: str      # e.g., "CrashLoopBackOff", "NodeNotReady", "DeploymentDegraded"
    severity: str       # "Critical", "High", "Warning"
    resourceType: ResourceType
    namespace: Optional[str] = None
    resourceName: str   # Name of the Pod, Node, or Deployment
    container: Optional[str] = None
    unhealthySince: str # Formatted duration, e.g., "02h 15m"
    unhealthyTimespan: int # Duration in seconds
    message: str
    issueId: Optional[str] = None

    def canonical_key(self) -> str:
        ns = (self.namespace or "-").strip().lower()
        rt = (self.resourceType.value if isinstance(self.resourceType, ResourceType) else str(self.resourceType)).strip().lower()
        it = (self.issueType or "-").strip().lower()
        rn = (self.resourceName or "-").strip().lower()
        cn = (self.container or "-").strip().lower()
        return "|".join([it, rt, ns, rn, cn])

    def compute_issue_id(self) -> str:
        key = self.canonical_key().encode("utf-8")
        digest = hashlib.sha1(key).hexdigest()[:12]
        return f"iss-{digest}"

    @model_validator(mode="after")
    def _populate_issue_id(self):
        if not self.issueId:
            self.issueId = self.compute_issue_id()
        return self

class AgentState(BaseModel):
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None  # Changed from str to Dict
    next_action: Literal["continue", "await_user_approval", "handoff_to_solution_agent"]
    root_cause: Optional[str] = None

class MessageItem(BaseModel):
    role: str
    text: str

# Solution response schema for handoff
class Escalation(BaseModel):
    recommended: bool
    reason: Optional[str] = None
    target_team: Optional[str] = None
    severity: Optional[Literal["low", "medium", "high", "critical"]] = None
    email_draft: Optional[str] = None

class SolutionResponse(BaseModel):
    thought: str
    recommended_fix: Optional[Dict[str, Any]] = None
    escalation: Escalation
    risk_level: Literal["low", "medium", "high"]
    assumptions: List[str] = []
    references: List[str] = []

# Generic WebSocket payload used by /workflow/ws
class WebSocketPayload(BaseModel):
    event: Literal[
        "history",
        "diagnostic",
        "awaiting_approval",
        "handoff_approval",
        "resume_available",
        "handoff",
        "complete",
        "error",
    ]
    issueId: Optional[str] = None
    diag_thread_id: Optional[str] = None
    sol_thread_id: Optional[str] = None

    # Content for specific events
    state: Optional[Union[AgentState, SolutionResponse]] = None
    status: Optional[Literal["in_progress", "handoff"]] = None
    diag_history: Optional[List[MessageItem]] = None
    sol_history: Optional[List[MessageItem]] = None
    question: Optional[str] = None