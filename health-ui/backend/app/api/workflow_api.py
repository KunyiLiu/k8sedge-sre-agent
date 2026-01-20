import os
import logging
from typing import Optional
from dotenv import load_dotenv
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.models import HealthIssue, AgentState
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.agents.aio import AgentsClient
from app.agents.agent_factory import AgentFactory
from skills.mock_k8s_diag import create_mock_tools

load_dotenv()

logger = logging.getLogger(__name__)

router = APIRouter()

async def _get_clients() -> tuple[AIProjectClient, AgentsClient, DefaultAzureCredential]:
    endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
    if not endpoint:
        raise RuntimeError("AZURE_AI_PROJECT_ENDPOINT not configured")
    credential = DefaultAzureCredential()
    project_client = AIProjectClient(endpoint=endpoint, credential=credential)
    agents_client = AgentsClient(endpoint=endpoint, credential=credential)
    return project_client, agents_client, credential

async def _get_clean_history(agents_client: AgentsClient, thread_id: str) -> list[dict]:
    history: list[dict] = []
    async for message in agents_client.messages.list(thread_id=thread_id):
        text = getattr(message, "text", "") or ""
        if getattr(message, "text_messages", None):
            texts = [tm.text.value for tm in message.text_messages if hasattr(tm, "text")]
            text = texts[-1] if texts else text
        history.append({"role": message.role, "text": text})
    history.reverse()
    return history

@router.websocket("/workflow/ws")
async def workflow_ws(ws: WebSocket):
    await ws.accept()
    project_client: Optional[AIProjectClient] = None
    agents_client: Optional[AgentsClient] = None
    credential: Optional[DefaultAzureCredential] = None
    try:
        init_msg = await ws.receive_json()
        if init_msg.get("type") != "start" or not init_msg.get("issue"):
            await ws.send_json({"event": "error", "detail": "First message must be type=start with 'issue'"})
            await ws.close()
            return

        issue = HealthIssue(**init_msg["issue"])
        project_client, agents_client, credential = await _get_clients()

        tools = create_mock_tools(profile="crashloop")
        factory = AgentFactory(project_client=project_client, agents_client=agents_client, credential=credential, tools=tools)
        diag_agent = await factory.create_diagnostic_agent()

        start_input = (
            f"Investigate the issue {issue.issueType} for {issue.resourceType} "
            f"[resourceName={issue.resourceName}, container={issue.container}, namespace={issue.namespace}]."
        )

        diag_thread = diag_agent.get_new_thread()
        current_input = start_input
        step_count = 0
        max_steps = 12
        while step_count < max_steps:
            step_count += 1
            async for update in diag_agent.run_stream(current_input, thread=diag_thread):
                # Stream raw chunks to client
                chunk = None
                if update.text:
                    chunk = update.text
                    await ws.send_json({"event": "chunk", "text": chunk})

            # Parse last message as structured state
            history = await _get_clean_history(agents_client, diag_thread.service_thread_id or "")
            last_text = history[-1]["text"] if history else ""
            state: Optional[AgentState] = None
            try:
                state = AgentState.model_validate_json(last_text)
            except Exception:
                state = None
            await ws.send_json({"event": "state", "state": (state.model_dump() if state else None)})

            # Bounds
            if len(history) >= 50:
                await ws.send_json({"event": "complete", "status": "in_progress"})
                break

            if not state:
                current_input = "Continue."
                continue

            if state.next_action == "handoff_to_solution_agent":
                sol_agent = await factory.create_solution_agent()
                sol_thread = sol_agent.get_new_thread()
                prompt = (
                    f"Provide solution or escalation email for the issue {issue.issueType} for {issue.resourceType} "
                    f"[resourceName={issue.resourceName}, container={issue.container}, namespace={issue.namespace}]. "
                    f"Diagnostic root cause: [{state.root_cause}]. Other evidence: [{state.thought}]"
                )
                async for update in sol_agent.run_stream(prompt, thread=sol_thread):
                    chunk = getattr(update, "text", None) or getattr(update, "delta", None) or (update if isinstance(update, str) else None)
                    if chunk:
                        await ws.send_json({"event": "chunk", "text": chunk})
                await ws.send_json({"event": "handoff", "sol_thread_id": sol_thread.service_thread_id})
                await ws.send_json({"event": "complete", "status": "handoff"})
                break

            if state.next_action == "await_user_approval":
                await ws.send_json({"event": "awaiting_approval", "thought": state.thought})
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
                continue

            # Default
            current_input = "Continue."

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"event": "error", "detail": str(e)})
        except Exception:
            pass
    finally:
        try:
            if agents_client:
                await agents_client.close()
            if project_client:
                await project_client.close()
            if credential:
                await credential.close()
        finally:
            await ws.close()

