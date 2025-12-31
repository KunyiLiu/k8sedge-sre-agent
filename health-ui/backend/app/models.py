from pydantic import BaseModel
from typing import Optional

class Metric(BaseModel):
    name: str
    value: float
    timestamp: Optional[str] = None

class HealthStatus(BaseModel):
    status: str
    details: Optional[str] = None
