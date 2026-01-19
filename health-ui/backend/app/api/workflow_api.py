import os
import asyncio
import logging
import json
from typing import Optional, Literal, List, Dict
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Body, Query, WebSocket, WebSocketDisconnect
from app.models import HealthIssue, HumanIntervention, MessageItem, WorkflowResponse, AgentState
from skills.k8s_diag import (
    get_pod_diagnostics,
    get_pod_events,
    get_image_pull_events,
    get_service_account_details,
    get_secret_exists,
    get_workload_yaml,
    get_pod_top_metrics,
    get_pod_scheduling_events,
    get_nodes_overview,
    get_pvc_details,
    get_namespace_resource_quota,
    get_namespace_limit_ranges,
)

from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.agents.aio import AgentsClient
from agent_framework.azure import AzureAIAgentClient
from agent_framework import ChatAgent
from app.agents.agent_factory import AgentFactory

load_dotenv()

logger = logging.getLogger(__name__)

_project_client: Optional[AIProjectClient] = None
_credential: Optional[DefaultAzureCredential] = None
_endpoint: Optional[str] = None

def _get_endpoint() -> str:
    # Prefer existing var, fallback to prior name
    endpoint = os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT") or os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
    if not endpoint:
        logger.error("Azure AI Project endpoint not set (AZURE_EXISTING_AIPROJECT_ENDPOINT / AZURE_AI_PROJECT_ENDPOINT)")
        raise RuntimeError("Azure AI Project endpoint not configured")
    return endpoint

async def get_project_client() -> AIProjectClient:
    global _project_client, _credential, _endpoint
    if _project_client is None:
        _endpoint = _get_endpoint()
        logger.info("Creating AIProjectClient", extra={"endpoint": _endpoint})
        _credential = _credential or DefaultAzureCredential()
        _project_client = AIProjectClient(endpoint=_endpoint, credential=_credential)
    else:
        logger.debug("Reusing cached AIProjectClient")
    return _project_client

async def close_project_client():
    global _project_client, _credential
    if _project_client:
        logger.debug("Closing AIProjectClient")
        await _project_client.close()
        _project_client = None
    if _credential:
        logger.debug("Closing DefaultAzureCredential")
        await _credential.close()
        _credential = None

router = APIRouter()

def get_pod_details(pod_name: str) -> str:
    return "LOGS: 'java.lang.OutOfMemoryError'. Events: 'Back-off restarting failed container'."

# Tool registry for executing actions requested by the diagnostic agent
TOOL_MAP = {
    "get_pod_details": get_pod_details,
    "get_pod_diagnostics": get_pod_diagnostics,
    "get_pod_events": get_pod_events,
    "get_image_pull_events": get_image_pull_events,
    "get_service_account_details": get_service_account_details,
    "get_secret_exists": get_secret_exists,
    "get_workload_yaml": get_workload_yaml,
    "get_pod_top_metrics": get_pod_top_metrics,
    "get_pod_scheduling_events": get_pod_scheduling_events,
    "get_nodes_overview": get_nodes_overview,
    "get_pvc_details": get_pvc_details,
    "get_namespace_resource_quota": get_namespace_resource_quota,
    "get_namespace_limit_ranges": get_namespace_limit_ranges,
}

def _execute_tool(action: Optional[str], action_input: Optional[str]) -> Optional[str]:
    if not action:
        return None
    fn = TOOL_MAP.get(action)
    if not fn:
        return None
    # Expect JSON input with kwargs like {"name": "pod", "namespace": "ns"}
    kwargs = {}
    if action_input:
        try:
            data = json.loads(action_input)
            if isinstance(data, dict):
                kwargs = data
            elif isinstance(data, list):
                # Unpack ordered args if a list is provided
                return fn(*data)  # type: ignore[misc]
            else:
                # Single positional string
                return fn(action_input)  # type: ignore[misc]
        except Exception:
            # Not JSON; pass as single positional arg
            return fn(action_input)  # type: ignore[misc]
    return fn(**kwargs)  # type: ignore[misc]

async def get_clean_history(agents_client: AgentsClient, thread_id: str) -> List[MessageItem]:
    history: List[MessageItem] = []
    try:
        async for message in agents_client.messages.list(thread_id=thread_id):
            text = ""
            if getattr(message, "text_messages", None):
                texts = [tm.text.value for tm in message.text_messages if hasattr(tm, "text")]
                text = texts[-1] if texts else ""
            else:
                text = getattr(message, "text", "") or ""
            history.append(MessageItem(role=message.role, text=text))
        history.reverse()
    except Exception as e:
        print(f"Error fetching history: {e}")
    return history

WORKFLOW_STORE: Dict[str, Dict[str, Optional[str]]] = {}

def issue_key(issue: HealthIssue) -> str:
    ns = issue.namespace or "default"
    container = issue.container or ""
    return f"{ns}:{issue.resourceType}:{issue.resourceName}:{container}"

def _get_tools_list():
    return [
        get_pod_details,
        get_pod_diagnostics,
        get_pod_events,
        get_image_pull_events,
        get_service_account_details,
        get_secret_exists,
        get_workload_yaml,
        get_pod_top_metrics,
        get_pod_scheduling_events,
        get_nodes_overview,
        get_pvc_details,
        get_namespace_resource_quota,
        get_namespace_limit_ranges,
    ]

async def run_diag_until_wait_or_handoff(diag_agent: ChatAgent, agents_client: AgentsClient, start_input: str, max_steps: int = 4):
    diag_thread = diag_agent.get_new_thread()
    step_count = 0
    final_state: Optional[AgentState] = None
    last_text = ""
    current_input = start_input
    while step_count < max_steps:
        step_count += 1
        result = await diag_agent.run(current_input, thread=diag_thread)
        msgs = getattr(result, "messages", [])
        if msgs:
            last_text = msgs[-1].text
        try:
            final_state = AgentState.model_validate_json(last_text)
        except Exception:
            continue
        if final_state.next_action in ("await_user_approval", "handoff_to_solution_agent"):
            break
        if final_state.next_action == "continue" and final_state.action:
            obs = _execute_tool(final_state.action, final_state.action_input)
            if obs is None:
                current_input = "Observation: (no-op)"
            else:
                current_input = f"Observation: {obs}"
    history = await get_clean_history(agents_client, diag_thread.service_thread_id)
    return {
        "diag_thread_id": diag_thread.service_thread_id,
        "state": final_state,
        "last_text": last_text,
        "step_count": step_count,
        "history": history,
    }

# --- WebSocket workflow with live human intervention ---
@router.websocket("/workflow/ws")
async def workflow_ws(ws: WebSocket):
    await ws.accept()
    agents_client: Optional[AgentsClient] = None
    try:
        # First message should start the workflow and include the issue
        init_msg = await ws.receive_json()
        if init_msg.get("type") != "start" or not init_msg.get("issue"):
            await ws.send_json({"event": "error", "detail": "First message must be type=start with 'issue'"})
            await ws.close()
            return

        issue = HealthIssue(**init_msg["issue"])
        key = issue_key(issue)
        logger.info("WS start_workflow", extra={"issue": issue.model_dump(), "key": key})

        project_client = await get_project_client()
        assert _endpoint and _credential
        agents_client = AgentsClient(endpoint=_endpoint, credential=_credential)

        factory = AgentFactory(project_client=project_client, agents_client=agents_client, credential=_credential, tools=_get_tools_list())
        diag_agent = await factory.create_diagnostic_agent()
        start_input = f"Investigate why {issue.resourceType} '{issue.resourceName}' is unhealthy: {issue.issueType}."
        diag_thread = diag_agent.get_new_thread()
        WORKFLOW_STORE[key] = {"diag_thread_id": diag_thread.service_thread_id, "sol_thread_id": None}

        step_count = 0
        current_input = start_input
        while step_count < 20:
            step_count += 1
            result = await diag_agent.run(current_input, thread=diag_thread)
            msgs = getattr(result, "messages", [])
            last_text = msgs[-1].text if msgs else ""

            state: Optional[AgentState] = None
            try:
                state = AgentState.model_validate_json(last_text)
            except Exception:
                state = None

            await ws.send_json({
                "event": "step",
                "diag_thread_id": diag_thread.service_thread_id,
                "state": (state.model_dump() if state else None),
            })

            if state and state.next_action == "await_user_approval":
                await ws.send_json({"event": "awaiting_approval"})
                try:
                    decision_msg = await ws.receive_json()
                except WebSocketDisconnect:
                    break
                if decision_msg.get("type") != "intervene":
                    await ws.send_json({"event": "error", "detail": "Expected intervene message"})
                    break
                d = decision_msg.get("decision")
                hint = decision_msg.get("hint") or ""
                if d == "approve":
                    current_input = "Action APPROVED. Proceed."
                elif d == "deny":
                    current_input = f"Action DENIED. Reason/Hint: {hint}"
                elif d == "handoff":
                    current_input = "Manual Handoff requested."
                else:
                    await ws.send_json({"event": "error", "detail": "Unknown decision"})
                    break

            elif state and state.next_action == "handoff_to_solution_agent":
                sol_agent = await factory.create_solution_agent()
                sol_thread = sol_agent.get_new_thread()
                root_cause = state.root_cause or ""
                await sol_agent.run(f"Fix this: {root_cause}", thread=sol_thread)
                WORKFLOW_STORE[key]["sol_thread_id"] = sol_thread.service_thread_id
                await ws.send_json({
                    "event": "handoff",
                    "sol_thread_id": sol_thread.service_thread_id,
                })
                break

            else:
                # continue loop; optionally call tools
                if state and state.next_action == "continue" and state.action:
                    obs = _execute_tool(state.action, state.action_input)
                    if obs is None:
                        current_input = "Observation: (no-op)"
                    else:
                        current_input = f"Observation: {obs}"
                else:
                    current_input = "Continue."

        # Final histories
        diag_hist = await get_clean_history(agents_client, diag_thread.service_thread_id)
        sol_hist: List[MessageItem] = []
        sol_tid = WORKFLOW_STORE[key].get("sol_thread_id")
        if sol_tid:
            sol_hist = await get_clean_history(agents_client, sol_tid)

        await ws.send_json({
            "event": "complete",
            "status": "handoff" if sol_tid else "in_progress",
            "diag_thread_id": diag_thread.service_thread_id,
            "sol_thread_id": sol_tid,
            "history": [h.model_dump() for h in diag_hist],
            "solution_history": [h.model_dump() for h in sol_hist],
        })
    except WebSocketDisconnect:
        # client disconnected; nothing else to do
        pass
    except Exception as e:
        try:
            await ws.send_json({"event": "error", "detail": str(e)})
        except Exception:
            pass
    finally:
        if agents_client:
            await agents_client.close()
        await ws.close()

@router.post("/workflow/diagnostic", response_model=WorkflowResponse)
async def start_workflow(issue: HealthIssue = Body(...)):
    try:
        project_client = await get_project_client()
        assert _endpoint and _credential
        agents_client = AgentsClient(endpoint=_endpoint, credential=_credential)
        try:
            factory = AgentFactory(project_client=project_client, agents_client=agents_client, credential=_credential, tools=_get_tools_list())
            diag_agent = await factory.create_diagnostic_agent()
            start_input = f"Investigate why {issue.resourceType} '{issue.resourceName}' is unhealthy: {issue.issueType}."
            result = await run_diag_until_wait_or_handoff(diag_agent, agents_client, start_input)
            key = issue_key(issue)
            WORKFLOW_STORE[key] = {"diag_thread_id": result["diag_thread_id"], "sol_thread_id": None}
            status: Optional[str] = None
            if result["state"]:
                if result["state"].next_action == "await_user_approval":
                    status = "awaiting_approval"
                elif result["state"].next_action == "handoff_to_solution_agent":
                    status = "handoff"
                else:
                    status = "in_progress"
            payload = WorkflowResponse(
                status=status or "in_progress",
                diag_thread_id=result["diag_thread_id"],
                sol_thread_id=None,
                state=result["state"],
                history=result["history"],
            )
            if payload.status == "handoff" and result["state"] and result["state"].root_cause:
                sol_agent = await factory.create_solution_agent()
                sol_thread = sol_agent.get_new_thread()
                await sol_agent.run(f"Fix this: {result['state'].root_cause}", thread=sol_thread)
                payload.sol_thread_id = sol_thread.service_thread_id
                WORKFLOW_STORE[key]["sol_thread_id"] = sol_thread.service_thread_id
            return payload
        finally:
            await agents_client.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/workflow/intervene", response_model=WorkflowResponse)
async def human_intervene(data: HumanIntervention):
    try:
        project_client = await get_project_client()
        assert _endpoint and _credential
        agents_client = AgentsClient(endpoint=_endpoint, credential=_credential)
        try:
            factory = AgentFactory(project_client=project_client, agents_client=agents_client, credential=_credential, tools=_get_tools_list())
            diag_agent = await factory.create_diagnostic_agent()
            diag_thread = diag_agent.get_new_thread(service_thread_id=data.diag_thread_id)

            if data.decision == "approve":
                current_input = "Action APPROVED. Proceed."
            elif data.decision == "deny":
                current_input = f"Action DENIED. Reason/Hint: {data.hint or ''}"
            else:
                current_input = "Manual Handoff requested."
            result = await diag_agent.run(current_input, thread=diag_thread)
            msgs = getattr(result, "messages", [])
            last_text = msgs[-1].text if msgs else ""
            state: Optional[AgentState] = None
            try:
                state = AgentState.model_validate_json(last_text)
            except Exception:
                state = None
            sol_thread_id: Optional[str] = None
            if data.decision == "handoff" or (state and state.next_action == "handoff_to_solution_agent"):
                factory = AgentFactory(project_client=project_client, agents_client=agents_client, credential=_credential, tools=_get_tools_list())
                sol_agent = await factory.create_solution_agent()
                sol_thread = sol_agent.get_new_thread()
                root_cause = (state.root_cause if state else "")
                await sol_agent.run(f"Fix this: {root_cause}", thread=sol_thread)
                sol_thread_id = sol_thread.service_thread_id
            history = await get_clean_history(agents_client, data.diag_thread_id)
            return WorkflowResponse(
                status=None,
                diag_thread_id=data.diag_thread_id,
                sol_thread_id=sol_thread_id,
                state=state,
                history=history,
            )
        finally:
            await agents_client.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/workflow/history")
async def workflow_history(diag_thread_id: str = Query(...), sol_thread_id: Optional[str] = Query(None)):
    endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    if not endpoint:
        raise HTTPException(status_code=500, detail="AZURE_AI_PROJECT_ENDPOINT not set")
    credential = DefaultAzureCredential()
    try:
        agents_client = AgentsClient(endpoint=endpoint, credential=credential)
        try:
            diag_log = await get_clean_history(agents_client, diag_thread_id)
            sol_log: List[Dict] = []
            if sol_thread_id:
                sol_log = await get_clean_history(agents_client, sol_thread_id)
            return {"diagnostic": diag_log, "solution": sol_log}
        finally:
            await agents_client.close()
    finally:
        await credential.close()

