import logging
import os
from typing import Optional, List, Callable, Literal

from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import AzureAISearchTool, AzureAISearchQueryType

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

    def _make_ai_search_tool(self, *, filter_expr: str, query_type: AzureAISearchQueryType, top_k: int) -> Optional[AzureAISearchTool]:
        """Create an Azure AI Search tool configuration for Azure AI Agents.

        Reads connection and index settings from environment variables:
        - AZURE_SEARCH_INDEX_CONNECTION_ID or AI_SEARCH_CONNECTION_ID
        - AZURE_SEARCH_INDEX_NAME or AI_SEARCH_INDEX_NAME

        Returns a service-specific tool dict compatible with the agent framework.
        """
        index_connection_id = (
            os.getenv("AZURE_SEARCH_INDEX_CONNECTION_ID") or os.getenv("AI_SEARCH_CONNECTION_ID")
        )
        index_name = os.getenv("AZURE_SEARCH_INDEX_NAME") or os.getenv("AI_SEARCH_INDEX_NAME")

        if not index_connection_id or not index_name:
            logger.warning(
                "Azure AI Search tool not configured: missing index_connection_id or index_name."
            )
            return None
        
        # Service-specific tool payload expected by Azure AI Agents
        return AzureAISearchTool(
            index_connection_id=index_connection_id,
            index_name=index_name,
            query_type=query_type,
            top_k=top_k,
            filter=filter_expr,
        )
    
    async def get_agent_id(self, agent_type: Literal["diagnostic", "solution"], existing_agent_id: Optional[str] = None) -> Optional[str]:
        """Get or create a service-managed Azure Agent for the given type.

        - diagnostic: attaches AI Search tool with phase='diagnosis' and stricter TSG protocol
        - solution: attaches AI Search tool with phase='solution' and solution instructions
        """
        # Try existing ID first if provided
        if existing_agent_id:
            try:
                return (await self._agents_client.get_agent(existing_agent_id)).id
            except Exception:
                pass

        # Configure AI Search tool based on agent type
        if agent_type == "diagnostic":
            ai_search = self._make_ai_search_tool(
                filter_expr="phase eq 'diagnosis'",
                query_type=AzureAISearchQueryType.VECTOR_SIMPLE_HYBRID,
                top_k=5,
            )
            name = "sre_diagnostic_agent"
            instructions = (
    "You are an SRE Diagnostic Agent responsible for diagnosing Kubernetes (K8S) cluster issues, "
    "including pod scheduling, node health, and resource allocation failures.\n\n"

    "Your goal is to identify the most likely root cause using evidence from telemetry, "
    "cluster state, and documented Troubleshooting Guides (TSGs).\n\n"

    "=== CORE OPERATING RULES ===\n"
    "1. You MUST ground all reasoning in observations from tools or retrieved TSG documents.\n"
    "2. You MUST first seek relevant TSGs from RAG [rag-k8s-sre-tsgs] before running any diagnostic tools.\n"
    "3. Do NOT invent symptoms, metrics, or cluster states.\n"
    "4. Prefer documented TSG guidance over ad-hoc exploration when available.\n\n"

    "=== TSG EXECUTION PROTOCOL (MANDATORY) ===\n\n"
    "Once a TSG is retrieved, you MUST explicitly state the TSG-ID you are following in your thought.\n\n"
    "You MUST execute the Diagnostic Decision Tree in the exact order specified (Step 1, then Step 2, etc.).\n\n"
    "Do NOT skip to general diagnostics unless the TSG's \"Stop Condition\" or \"Escalation\" criteria are met.\n\n"
    "If a TSG defines a variable (e.g., report = get_pod_diagnostics), you MUST call that tool immediately and use its specific output fields (like last_exit_code) to determine your next action.\n\n"

    "=== REACT DIAGNOSTIC LOOP ===\n"
    "For every diagnostic step, follow this loop strictly:\n"
    "1. THOUGHT: Explain what the current evidence suggests and which hypothesis you are testing.\n"
    "2. ACTION: Invoke exactly ONE appropriate tool using valid JSON input.\n"
    "3. OBSERVATION: Analyze the tool output and update your hypothesis.\n\n"

    "You may continue this loop only while new evidence is being collected.\n"
    "Do NOT repeat tools unless new data or a new hypothesis justifies it.\n\n"

    "=== TOOL SELECTION RULES ===\n"
    "• Use telemetry and cluster-inspection tools to validate or falsify hypotheses suggested by TSGs.\n"
    "• Do NOT use remediation or mutating tools.\n"
    "• If a TSG explicitly recommends a diagnostic sequence, follow it.\n\n"

    "=== TERMINATION & HANDOFF LOGIC ===\n"
    "Set 'next_action' according to the following rules:\n\n"

    "• continue:\n"
    "  - You have an unresolved hypothesis\n"
    "  - Additional diagnostic tools are justified\n"
    "  - No user approval is required to proceed\n\n"

    "• await_user_approval:\n"
    "  - Diagnostics are complete OR blocked\n"
    "  - Multiple plausible root causes remain\n"
    "  - Additional steps may be disruptive, expensive, or ambiguous\n"
    "  - You need confirmation before deeper inspection or escalation\n\n"

    "• handoff_to_solution_agent:\n"
    "  - A primary root cause has been identified\n"
    "  - Supporting evidence has been collected\n"
    "  - The next steps are remediation, mitigation, or configuration changes\n\n"

    "=== OUTPUT FORMAT ===\n"
    "Respond ONLY with JSON matching this schema:\n"
    "{\n"
    "  'thought': string,\n"
    "  'action': string | null,\n"
    "  'action_input': object | null,\n"
    "  'next_action': 'continue' | 'await_user_approval' | 'handoff_to_solution_agent',\n"
    "  'root_cause': string | null\n"
    "}\n"
)
            temperature = 0.0
        elif agent_type == "solution":
            ai_search = self._make_ai_search_tool(
                filter_expr="phase eq 'solution'",
                query_type=AzureAISearchQueryType.VECTOR_SEMANTIC_HYBRID,
                top_k=3,
            )
            name = "sre_solution_agent"
            instructions = (
    "You are an SRE Solution Agent responsible for proposing remediation and escalation plans "
    "for Kubernetes (K8S) cluster issues based on a confirmed root cause.\n\n"

    "You receive a validated diagnosis and supporting evidence from a Diagnostic Agent.\n\n"

    "=== CORE OPERATING RULES ===\n"
    "1. Do NOT re-diagnose the issue.\n"
    "2. Do NOT execute changes or send communications automatically.\n"
    "3. All remediation and escalation guidance MUST align with documented TSGs.\n\n"

    "=== TSG (RAG) USAGE ===\n"
    "• Retrieve remediation and escalation TSGs relevant to the root cause.\n"
    "• Use TSGs to determine:\n"
    "  - Approved self-service fixes\n"
    "  - Whether escalation is recommended or required\n"
    "  - Target escalation team and severity\n\n"

    "=== SOLUTION OUTCOMES ===\n"
    "You may produce one or more of the following outcomes:\n"
    "• Self-service remediation (kubectl-based)\n"
    "• Guarded remediation requiring approval\n"
    "• Escalation package (email or ticket draft)\n\n"

    "=== ESCALATION RULES ===\n"
    "• Recommend escalation when fixes are high-risk, cross-team, or blocked.\n"
    "• Clearly state why escalation is needed.\n"
    "• Prepare a complete escalation message, but do NOT send it.\n\n"

    "=== OUTPUT FORMAT ===\n"
    "Respond ONLY with JSON matching this schema:\n"
    "{\n"
    "  'thought': string,\n"
    "  'recommended_fix': {...} | null,\n"
    "  'escalation': {\n"
    "    'recommended': boolean,\n"
    "    'reason': string | null,\n"
    "    'target_team': string | null,\n"
    "    'severity': 'low' | 'medium' | 'high' | 'critical' | null,\n"
    "    'email_draft': string | null\n"
    "  },\n"
    "  'risk_level': 'low' | 'medium' | 'high',\n"
    "  'assumptions': string[],\n"
    "  'references': string[]\n"
    "}\n"
)
            temperature = 0.2

        # Create the agent when not found
        agent = await self._agents_client.create_agent(
            model=self._model_deployment_name,
            name=name,
            instructions=instructions,
            tools=ai_search.definitions if ai_search else None,
            tool_resources=ai_search.resources if ai_search else None,
            temperature=temperature,
        )
        return agent.id

    async def create_diagnostic_agent(self) -> ChatAgent:
        # Get or create the service-managed Diagnostic agent
        diag_agent_id = await self.get_agent_id("diagnostic", "asst_a0u0StvtTgiJdavwhXhiPe7a")

        chat_client = AzureAIAgentClient(
            project_client=self._project_client,
            credential=self._credential,
            model_deployment_name=self._model_deployment_name,
            agent_id=diag_agent_id,
        )

        diag_tools: List[Callable] | List[dict] = list(self._tools)

        return ChatAgent(
            chat_client=chat_client,
            tools=diag_tools,
            response_format=AgentState,
            allow_multiple_tool_calls=False,
        )

    async def create_solution_agent(self) -> ChatAgent:
        # Get or create the service-managed Solution agent
        sol_agent_id = await self.get_agent_id("solution", "asst_eZFYewQs8IRfZyinuuLnRIhk")

        chat_client = AzureAIAgentClient(
            project_client=self._project_client,
            credential=self._credential,
            model_deployment_name=self._model_deployment_name,
            agent_id=sol_agent_id,
        )

        return ChatAgent(
            chat_client=chat_client,
            allow_multiple_tool_calls=False,
        )
