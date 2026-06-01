from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models import HealthIssue


class Verdict(str, Enum):
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"


class TerminationStatus(str, Enum):
    COMPLETED = "completed"
    MAX_STEPS = "max_steps"
    ERROR = "error"


class AgentTrace(BaseModel):
    """Captured diagnostic output from an agent run."""

    agent_diagnosis: Optional[str] = None
    agent_tool_sequence: List[str] = Field(default_factory=list)
    agent_thought_chain: List[str] = Field(default_factory=list)
    termination_status: TerminationStatus = TerminationStatus.COMPLETED
    step_count: int = 0
    error: Optional[str] = None
    raw: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _populate_step_count(self) -> "AgentTrace":
        if self.step_count == 0:
            self.step_count = max(len(self.agent_tool_sequence), len(self.agent_thought_chain))
        return self


class GoldenScenario(BaseModel):
    """A labeled incident scenario with expectations for evaluation."""

    id: str
    tags: List[str] = Field(default_factory=list)
    mock_profile: str
    issue: HealthIssue
    expected_diagnosis: str
    expected_primary_tools: List[str]
    allowed_extra_tools: List[str] = Field(default_factory=list)
    forbidden_tools: List[str] = Field(default_factory=list)
    expected_evidence: List[str] = Field(default_factory=list)
    judge_notes: Optional[str] = None
    recorded_agent_result: Optional[AgentTrace] = None

    @field_validator("id")
    @classmethod
    def _id_is_kebab_case(cls, value: str) -> str:
        if not value or value.lower() != value or " " in value:
            raise ValueError("scenario id must be non-empty kebab-case lowercase text")
        return value

    @field_validator("expected_primary_tools")
    @classmethod
    def _expected_tools_not_empty(cls, value: List[str]) -> List[str]:
        if not value:
            raise ValueError("expected_primary_tools must include at least one primary tool")
        return value


class DeterministicScore(BaseModel):
    scenario_id: str
    completed: bool
    diagnosis_present: bool
    tool_selection_verdict: Verdict
    tool_selection_score: int
    tool_selection_reason: str
    forbidden_tools_verdict: Verdict
    forbidden_tools_reason: str
    passed: bool


class JudgeScore(BaseModel):
    diagnosis_score: int = Field(ge=0, le=1)
    diagnosis_verdict: Verdict
    diagnosis_reason: str
    reasoning_score: int = Field(ge=1, le=5)
    reasoning_reason: str
    tool_selection_score: int = Field(ge=0, le=1)
    tool_selection_verdict: Verdict
    tool_selection_reason: str
    evidence_grounding_score: int = Field(ge=1, le=5)
    evidence_grounding_reason: str


class ScenarioResult(BaseModel):
    scenario_id: str
    scenario_tags: List[str]
    issue_type: str
    expected_diagnosis: str
    expected_primary_tools: List[str]
    trace: AgentTrace
    deterministic_score: DeterministicScore
    judge_score: Optional[JudgeScore] = None
    judge_error: Optional[str] = None


class EvaluationSummary(BaseModel):
    total: int
    passed: int
    failed: int
    deterministic_pass_rate: float
    diagnosis_present_rate: float
    tool_selection_pass_rate: float
    judge_diagnosis_pass_rate: Optional[float] = None
    average_reasoning_score: Optional[float] = None
    average_evidence_grounding_score: Optional[float] = None


class EvaluationReport(BaseModel):
    suite: str
    judge_enabled: bool
    summary: EvaluationSummary
    results: List[ScenarioResult]
