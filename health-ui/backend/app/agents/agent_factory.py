import logging
from typing import Optional, List, Callable

from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.agents.aio import AgentsClient

from agent_framework.azure import AzureAIAgentClient
from agent_framework import ChatAgent

from app.models import AgentState

logger = logging.getLogger(__name__)

class AgentFactory:
    """Centralized factory for creating diagnostic and solution agents."""

    def __init__(
        self,
        project_client: AIProjectClient,
        agents_client: AgentsClient,
        credential: DefaultAzureCredential,
        tools: Optional[List[Callable]] = None,
        model_deployment_name: str = "gpt-4.1-mini",
    ):
        self._project_client = project_client
        self._agents_client = agents_client
        self._credential = credential
        self._tools = tools or []
        self._model_deployment_name = model_deployment_name

    async def create_diagnostic_agent(self) -> ChatAgent:
        chat_client = AzureAIAgentClient(
            project_client=self._project_client,
            credential=self._credential,
            model_deployment_name=self._model_deployment_name,
        )
        try:
            diag_agent_id = (await self._agents_client.get_agent("asst_lMlS3XIxtrbImS0HEsMmiliY")).id
        except Exception:
            diag_agent_id = None

        return ChatAgent(
            chat_client=chat_client,
            id=diag_agent_id,
            name="Diagnostic Agent",
            tools=self._tools,
            response_format=AgentState,
            instructions=(
                "You are an SRE Diagnostic Agent. Find the root cause of failures.\n"
                "Use tools with JSON action_input containing required fields.\n\n"
                "For every step, follow this ReAct loop:\n"
                "1. THOUGHT: Reason about what the data means and what to check next.\n"
                "2. ACTION: Call the appropriate tool with JSON input.\n"
                "3. OBSERVATION: Analyze the output.\n\n"
                "Output JSON in this schema: "
                "{'thought': str, 'action': Optional[str], 'action_input': Optional[str], "
                "'next_action': 'continue' | 'await_user_approval' | 'handoff_to_solution_agent', "
                "'root_cause': Optional[str]}"
            ),
            temperature=0.0,
        )

    async def create_solution_agent(self) -> ChatAgent:
        chat_client = AzureAIAgentClient(
            project_client=self._project_client,
            credential=self._credential,
            model_deployment_name=self._model_deployment_name,
        )
        try:
            sol_agent_id = (await self._agents_client.get_agent("asst_4S7r6vAvX3nBQRGsj8C1RQk2")).id
        except Exception:
            sol_agent_id = None

        return ChatAgent(
            chat_client=chat_client,
            id=sol_agent_id,
            name="Solution Agent",
            instructions="Provide a kubectl fix based on the root cause.",
            temperature=0.2,
        )
