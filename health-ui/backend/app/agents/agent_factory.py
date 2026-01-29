import logging
import os
from typing import Optional, List, Callable, Literal

from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import AzureAISearchTool, AzureAISearchQueryType

from agent_framework.azure import AzureAIAgentClient
from agent_framework import ChatAgent

from app.models import AgentState, SolutionResponse

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

    "=== CORE OPERATING RULES ===\n"
    "1. Ground all reasoning in observations from tools or retrieved TSG documents.\n"
    "2. MANDATORY: You MUST first seek relevant TSGs from RAG [rag-k8s-sre-tsgs] before running diagnostic tools.\n"
    "Focus especially on TSG content for the 'diagnosis' phase.\n"
    "3. Do NOT invent symptoms, metrics, or cluster states.\n"
    "4. Prefer documented TSG guidance over ad-hoc exploration.\n\n"

    "=== REACT DIAGNOSTIC LOOP (STRICT SERIAL EXECUTION) ===\n"
    "You operate in a strict single-step loop. Every response MUST follow this sequence:\n"
    "1. THOUGHT: Be concise (1 or 2 sentences); explain what evidence suggests and which hypothesis/TSG step you are testing.\n"
    "2. ACTION: You MUST trigger EXACTLY ONE system function call per response. NEVER batch multiple calls.\n"
    "3. STOP: After triggering a tool, you MUST stop and wait for the observation. Do not proceed until data is returned.\n\n"

    "=== TOOL SELECTION RULES ===\n"
    "• Use telemetry and cluster-inspection tools to validate or falsify hypotheses suggested by TSGs.\n"
    "• Do NOT use remediation or mutating tools.\n"
    "• If a TSG explicitly recommends a diagnostic sequence, follow it.\n\n"

    "=== TERMINATION & HANDOFF LOGIC ===\n"
    "Set 'next_action' according to the following rules (do NOT use the 'action' field for control flow):\n\n"

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
    "Respond ONLY with a JSON object matching this schema:\n"
    "{\n"
    "  'thought': string,\n"
    "  'action': string | null,\n"
    "  'action_input': object | null,\n"
    "  'next_action': 'continue' | 'await_user_approval' | 'handoff_to_solution_agent',\n"
    "  'root_cause': string | null\n"
    "}\n\n"

    "=== EXAMPLES ===\n"
    "Example 1 (Starting a diagnosis):\n"
    "User: 'Investigate the issue CrashLoopBackOff for ResourceType.Pod [resourceName=web-0, container=web, namespace=default].'\n"
    "{ 'thought': 'Pod is in CrashLoopBackOff. Gather diagnostics to check status, restart count, exit code, and container logs.',\n"
    "  'action': 'functions.get_pod_diagnostics',\n"
    "  'action_input': { 'name': 'web-0', 'namespace': 'default' },\n"
    "  'next_action': 'continue',\n"
    "  'root_cause': null }\n\n"


    "Example 2 (Identifying root cause):\n"
    "Observation: 'Logs show OOMKilled.'\n"
    "{\n"
    "  'thought': 'The logs confirm the container was killed due to memory exhaustion. No further diagnostics needed.',\n"
    "  'action': null,\n"
    "  'action_input': null,\n"
    "  'next_action': 'handoff_to_solution_agent',\n"
    "  'root_cause': 'Memory limit reached causing OOMKill.'\n"
    "}"
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
    "• Always query the Kubernetes SRE TSG RAG index [rag-k8s-sre-tsgs] as your primary source of solution guidance.\n"
    "• Focus especially on TSG content for the 'solution' phase (phase = 'solution'), including concrete remediation steps and escalation patterns.\n"
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
    "}\n\n"
    "Notes:\n"
    "- Always ground your recommended_fix, escalation, and risk_level in TSG content retrieved from the [rag-k8s-sre-tsgs] index, focusing on documents for phase = 'solution'.\n\n"
    "Example for input: \"Provide solution or escalation email for the issue CrashLoopBackOff for ResourceType.Pod [resourceName=web-0, container=web, namespace=default]. Diagnostic root cause: [Application crash due to repeated container failures during startup causing CrashLoopBackOff.]. Other evidence: [Pod events show BackOff from restarts with no infrastructure or scheduling errors, indicating the issue is likely application-level. The CrashLoopBackOff is caused by the container repeatedly crashing. I will handoff to the solution agent with the root cause as application crash during initialization causing CrashLoopBackOff.]\"\n"
    "{\n"
    "  \"thought\": \"The root cause is an application crash during container startup causing CrashLoopBackOff. This is an application-level issue with no infrastructure or scheduling errors. According to TSGs, remediation involves checking application logs, validating configuration, and possibly updating the container image or application code. Since this is an application crash, self-service remediation is possible if the user has access to application logs and deployment manifests. Escalation is recommended if the user cannot resolve the application crash or lacks access to modify the deployment or application code.\",\n"
    "  \"recommended_fix\": {\n"
    "    \"steps\": [\n"
    "      \"Use 'kubectl logs web-0 -c web -n default' to check the container logs for error messages during startup.\",\n"
    "      \"Review the application configuration and environment variables for correctness.\",\n"
    "      \"If recent changes were made, consider rolling back to a previous stable version.\",\n"
    "      \"Check resource limits and requests to ensure the container has sufficient resources.\",\n"
    "      \"If the issue persists, rebuild and redeploy the container image after fixing the application code.\",\n"
    "      \"Use 'kubectl describe pod web-0 -n default' to verify no other events indicate underlying issues.\"\n"
    "    ],\n"
    "    \"commands\": [\n"
    "      \"kubectl logs web-0 -c web -n default\",\n"
    "      \"kubectl describe pod web-0 -n default\"\n"
    "    ]\n"
    "  },\n"
    "  \"escalation\": {\n"
    "    \"recommended\": true,\n"
    "    \"reason\": \"The application crash during initialization causing CrashLoopBackOff may require developer intervention to fix the application code or configuration. If the user cannot resolve the issue with self-service steps, escalation to the application development team is necessary.\",\n"
    "    \"target_team\": \"Application Development Team\",\n"
    "    \"severity\": \"medium\",\n"
    "    \"email_draft\": \"Subject: Escalation: Application Crash Causing CrashLoopBackOff for Pod web-0 in Namespace default\\n\\nHello Application Development Team,\\n\\nWe have identified a CrashLoopBackOff issue affecting the pod 'web-0' in the 'default' namespace. The root cause has been diagnosed as an application crash during container startup, leading to repeated container failures.\\n\\nPod events indicate BackOff from restarts without any infrastructure or scheduling errors, confirming this is an application-level problem.\\n\\nAttempts to remediate by checking logs and configuration have not resolved the issue. We recommend your team investigate the application code and container image to identify and fix the root cause of the crash.\\n\\nPlease prioritize this issue as it impacts service availability.\\n\\nThank you,\\nSRE Team\"\n"
    "  },\n"
    "  \"risk_level\": \"medium\",\n"
    "  \"assumptions\": [\n"
    "    \"User has access to kubectl and the cluster namespace 'default'.\",\n"
    "    \"Application logs provide sufficient information to diagnose the crash.\",\n"
    "    \"Application development team has the ability to fix and redeploy the application code.\"\n"
    "  ],\n"
    "  \"references\": [\n"
    "    \"TSG: Kubernetes Pod CrashLoopBackOff Troubleshooting\",\n"
    "    \"TSG: Application-Level Crash Remediation in Kubernetes\",\n"
    "    \"Kubernetes Documentation: Debugging Pods\"\n"
    "  ]\n"
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
        diag_agent_id = await self.get_agent_id("diagnostic", "asst_ZcqeAySf0Vy0p3kNsI9OEYp9")

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
        sol_agent_id = await self.get_agent_id("solution", "asst_PEI6ukfVYs3FuR6wh0HPXH1f")

        chat_client = AzureAIAgentClient(
            project_client=self._project_client,
            credential=self._credential,
            model_deployment_name=self._model_deployment_name,
            agent_id=sol_agent_id,
        )

        return ChatAgent(
            chat_client=chat_client,
            allow_multiple_tool_calls=False,
            response_format=SolutionResponse,
        )
