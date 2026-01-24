from enum import Enum
from pydantic import BaseModel, model_validator
from typing import Any, Dict, List, Optional, Literal
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

class HumanIntervention(BaseModel):
    diag_thread_id: str
    decision: Literal["approve", "deny", "handoff"]
    hint: Optional[str] = None

class AgentState(BaseModel):
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None  # Changed from str to Dict
    next_action: Literal["continue", "await_user_approval", "handoff_to_solution_agent"]
    root_cause: Optional[str] = None

class MessageItem(BaseModel):
    role: str
    text: str

class WorkflowResponse(BaseModel):
    status: Optional[Literal["in_progress", "awaiting_approval", "handoff"]] = None
    diag_thread_id: str
    sol_thread_id: Optional[str] = None
    state: Optional[AgentState] = None
    history: List[MessageItem]