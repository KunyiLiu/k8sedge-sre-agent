from enum import Enum
from pydantic import BaseModel
from typing import List, Optional

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