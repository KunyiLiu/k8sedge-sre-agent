from __future__ import annotations

import json
import os
from typing import Any, Optional

from app.evaluation.models import AgentTrace, GoldenScenario, TerminationStatus
from app.models import AgentState
from app.skills.mock_k8s_diag import create_mock_tools


class DiagnosticTraceGenerator:
    """Generate evaluation traces by running the diagnostic agent headlessly."""

    def __init__(self, factory: Any, *, max_steps: int = 12):
        self._factory = factory
        self._max_steps = max_steps

    @staticmethod
    def _extract_states(buffer: str) -> tuple[list[AgentState], str]:
        states: list[AgentState] = []
        decoder = json.JSONDecoder()
        while True:
            start = buffer.find("{")
            if start == -1:
                return states, buffer
            try:
                obj, end = decoder.raw_decode(buffer[start:])
            except json.JSONDecodeError:
                return states, buffer[start:]
            try:
                states.append(AgentState.model_validate(obj))
                buffer = buffer[start + end :]
            except Exception:
                buffer = buffer[start + 1 :]

    async def generate(self, scenario: GoldenScenario) -> AgentTrace:
        diag_agent = await self._factory.create_diagnostic_agent()
        diag_thread = diag_agent.get_new_thread()
        current_input = (
            f"Investigate the issue {scenario.issue.issueType} for {scenario.issue.resourceType} "
            f"[resourceName={scenario.issue.resourceName}, container={scenario.issue.container}, "
            f"namespace={scenario.issue.namespace}]."
        )

        tool_sequence: list[str] = []
        thought_chain: list[str] = []
        final_root_cause: Optional[str] = None
        raw_states: list[dict] = []

        for step in range(1, self._max_steps + 1):
            buffer = ""
            latest_state: Optional[AgentState] = None
            async for update in diag_agent.run_stream(current_input, thread=diag_thread):
                if update.text is None:
                    continue
                buffer += update.text
                states, buffer = self._extract_states(buffer)
                for state in states:
                    latest_state = state
                    raw_states.append(state.model_dump(mode="json"))
                    if state.thought:
                        thought_chain.append(state.thought)
                    if state.action:
                        tool_sequence.append(state.action)
                    if state.root_cause:
                        final_root_cause = state.root_cause

            if latest_state is None:
                current_input = "Continue."
                continue
            if latest_state.next_action == "handoff_to_solution_agent":
                return AgentTrace(
                    agent_diagnosis=final_root_cause,
                    agent_tool_sequence=tool_sequence,
                    agent_thought_chain=thought_chain,
                    termination_status=TerminationStatus.COMPLETED,
                    step_count=step,
                    raw={"states": raw_states},
                )
            if latest_state.next_action == "await_user_approval":
                current_input = "Action APPROVED. Proceed."
            else:
                current_input = "Continue."

        return AgentTrace(
            agent_diagnosis=final_root_cause,
            agent_tool_sequence=tool_sequence,
            agent_thought_chain=thought_chain,
            termination_status=TerminationStatus.MAX_STEPS,
            step_count=self._max_steps,
            raw={"states": raw_states},
        )


class AzureDiagnosticTraceGenerator(DiagnosticTraceGenerator):
    """Trace generator configured like the FastAPI workflow."""

    def __init__(self, *, endpoint: str, mock_profile: str, max_steps: int = 12, model_deployment_name: Optional[str] = None):
        from app.agents.agent_factory import AgentFactory
        from azure.ai.agents.aio import AgentsClient
        from azure.ai.projects.aio import AIProjectClient
        from azure.identity.aio import DefaultAzureCredential

        self._credential = DefaultAzureCredential()
        self._project_client = AIProjectClient(endpoint=endpoint, credential=self._credential)
        self._agents_client = AgentsClient(endpoint=endpoint, credential=self._credential)
        factory = AgentFactory(
            project_client=self._project_client,
            agents_client=self._agents_client,
            credential=self._credential,
            tools=create_mock_tools(profile=mock_profile),
            model_deployment_name=model_deployment_name or os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini"),
        )
        super().__init__(factory, max_steps=max_steps)

    @classmethod
    def from_env(cls, *, mock_profile: str, max_steps: int = 12) -> "AzureDiagnosticTraceGenerator":
        endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
        if not endpoint:
            raise ValueError("AZURE_AI_PROJECT_ENDPOINT is required to generate diagnostic traces.")
        return cls(endpoint=endpoint, mock_profile=mock_profile, max_steps=max_steps)

    async def close(self) -> None:
        await self._agents_client.close()
        await self._project_client.close()
        await self._credential.close()
