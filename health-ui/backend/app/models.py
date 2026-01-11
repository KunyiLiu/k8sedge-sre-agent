from enum import Enum
from pydantic import BaseModel
from typing import List, Optional, Literal

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

class HumanIntervention(BaseModel):
    diag_thread_id: str
    decision: Literal["approve", "deny", "handoff"]
    hint: Optional[str] = None

class AgentState(BaseModel):
    thought: str
    action: Optional[str] = None
    action_input: Optional[str] = None
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