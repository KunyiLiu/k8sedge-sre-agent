import os
import json
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
 
# In-memory mapping of issueId -> threads (per-process)
# { issueId: { 'diag_thread_id': str, 'sol_thread_id': Optional[str] } }
ISSUE_THREAD_MAP: dict[str, dict] = {}

async def _send_thread_histories(
    ws: WebSocket,
    agents_client: AgentsClient,
    *,
    issue_id: str,
    diag_thread_id: Optional[str],
    sol_thread_id: Optional[str] = None,
):
    diag_history = []
    sol_history = []
    if diag_thread_id:
        try:
            diag_history = await _get_clean_history(agents_client, diag_thread_id)
        except Exception as e:
            logger.warning(f"Failed to load diagnostic history for {diag_thread_id}: {e}")
    if sol_thread_id:
        try:
            sol_history = await _get_clean_history(agents_client, sol_thread_id)
        except Exception as e:
            logger.warning(f"Failed to load solution history for {sol_thread_id}: {e}")
    await ws.send_json({
        "event": "history",
        "issueId": issue_id,
        "diag_thread_id": diag_thread_id,
        "sol_thread_id": sol_thread_id,
        "diag_history": diag_history,
        "sol_history": sol_history,
    })

async def _ask_resume(ws: WebSocket, *, issue_id: str, diag_thread_id: str) -> bool:
    await ws.send_json({
        "event": "resume_available",
        "issueId": issue_id,
        "diag_thread_id": diag_thread_id,
        "question": "Resume previous diagnostic?",
    })
    try:
        msg = await ws.receive_json()
    except WebSocketDisconnect:
        return False
    if msg.get("type") == "resume" and str(msg.get("decision", "")).lower() in ("yes", "true", "y"):
        return True
    return False

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

async def _flush_diag_stream(
    ws: WebSocket,
    diag_agent,
    diag_thread,
    *,
    current_input: str,
    issue_id: str,
):
    buffer = ""
    async for update in diag_agent.run_stream(current_input, thread=diag_thread):
        if update.text is None:
            continue
        
        buffer += update.text
        decoder = json.JSONDecoder()
        while True:
            start = buffer.find("{")
            if start == -1:
                break
            try:
                obj, end = decoder.raw_decode(buffer[start:])
                logger.debug(f"Parsed diagnostic object: {obj}")
                state_flush = AgentState.model_validate(obj)
                await ws.send_json({
                    "event": "diagnostic_partial",
                    "issueId": issue_id,
                    "diag_thread_id": getattr(diag_thread, "service_thread_id", None),
                    "state": state_flush.model_dump(),
                })
                logger.debug(f"Sent diagnostic_partial; thought preview: {state_flush.thought[:50]}...")
                buffer = buffer[start + end:]
            except json.JSONDecodeError:
                logger.debug("Incomplete JSON fragment; waiting for more chunks")
                break
            except Exception as e:
                logger.warning(f"Validation error while parsing stream: {e}")
                buffer = buffer[start + 1:]

async def _emit_diagnostic_state(
    ws: WebSocket,
    *,
    issue_id: str,
    diag_thread,
    state: Optional[AgentState],
):
    await ws.send_json({
        "event": "diagnostic",
        "issueId": issue_id,
        "diag_thread_id": getattr(diag_thread, "service_thread_id", None),
        "state": (state.model_dump() if state else None)
    })

async def _ask_intervention(
    ws: WebSocket,
    *,
    issue_id: str,
    diag_thread_id: str,
    thought: Optional[str] = None,
    event_name: str = "awaiting_approval",
) -> Optional[str]:
    payload = {
        "event": event_name,
        "issueId": issue_id,
        "diag_thread_id": diag_thread_id,
    }
    if thought:
        payload["thought"] = thought
    await ws.send_json(payload)
    try:
        decision_msg = await ws.receive_json()
    except WebSocketDisconnect:
        return None
    if decision_msg.get("type") != "intervene":
        await ws.send_json({
            "event": "error",
            "detail": "Expected intervene message",
            "issueId": issue_id,
            "diag_thread_id": diag_thread_id,
        })
        return None
    return decision_msg.get("decision")

async def _run_solution_and_emit(
    ws: WebSocket,
    agents_client: AgentsClient,
    factory: AgentFactory,
    *,
    issue: HealthIssue,
    state: AgentState,
    issue_id: str,
    diag_thread,
):
    sol_agent = await factory.create_solution_agent()
    sol_thread = sol_agent.get_new_thread()
    prompt = (
        f"Provide solution or escalation email for the issue {issue.issueType} for {issue.resourceType} "
        f"[resourceName={issue.resourceName}, container={issue.container}, namespace={issue.namespace}]. "
        f"Diagnostic root cause: [{state.root_cause}]. Other evidence: [{state.thought}]"
    )
    result = await sol_agent.run(prompt, thread=sol_thread)

    sol_thread_id = getattr(sol_thread, "service_thread_id", None)
    try:
        ISSUE_THREAD_MAP[issue_id] = {
            "diag_thread_id": getattr(diag_thread, "service_thread_id", None),
            "sol_thread_id": sol_thread_id,
        }
    except Exception:
        pass

    await ws.send_json({
        "event": "handoff",
        "issueId": issue_id,
        "diag_thread_id": getattr(diag_thread, "service_thread_id", None),
        "sol_thread_id": sol_thread_id,
        "state": result.text,
    })
    # Show updated histories including the solution thread
    await _send_thread_histories(
        ws,
        agents_client,
        issue_id=issue_id,
        diag_thread_id=getattr(diag_thread, "service_thread_id", None),
        sol_thread_id=sol_thread_id,
    )
    await ws.send_json({
        "event": "complete",
        "status": "handoff",
        "issueId": issue_id,
        "diag_thread_id": getattr(diag_thread, "service_thread_id", None),
        "sol_thread_id": sol_thread_id,
    })

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

        # Use issueId mapping to show history, resume, or start new
        issue_id = issue.issueId or ""
        mapping = ISSUE_THREAD_MAP.get(issue_id) or {}
        existing_diag_id = mapping.get("diag_thread_id")
        existing_sol_id = mapping.get("sol_thread_id")
        diag_thread = None
        current_input = start_input

        if existing_diag_id:
            await _send_thread_histories(
                ws, agents_client,
                issue_id=issue_id,
                diag_thread_id=existing_diag_id,
                sol_thread_id=existing_sol_id,
            )
            if existing_sol_id:
                # If solution thread exists, just show histories and finish
                await ws.send_json({
                    "event": "complete",
                    "status": "handoff",
                    "issueId": issue_id,
                    "diag_thread_id": existing_diag_id,
                    "sol_thread_id": existing_sol_id,
                })
                return
            # Ask to resume diagnostic
            should_resume = await _ask_resume(ws, issue_id=issue_id, diag_thread_id=existing_diag_id)
            if should_resume:
                diag_thread = diag_agent.get_new_thread(service_thread_id=existing_diag_id)
                get_thread = getattr(diag_agent, "get_thread", None)
                if diag_thread is None:
                    diag_thread = diag_agent.get_new_thread()
                    logger.info("Started new diagnostic thread because resume was unavailable")
                else:
                    current_input = "Resume investigation based on the history above."
                    logger.info(f"Resuming diagnostic thread for issueId={issue_id} threadId={existing_diag_id}")
            else:
                await ws.send_json({
                    "event": "complete",
                    "status": "in_progress",
                    "issueId": issue_id,
                    "diag_thread_id": existing_diag_id,
                })
                return
        else:
            diag_thread = diag_agent.get_new_thread()
            logger.info(f"Started new diagnostic thread for issueId={issue_id}")

        # Record/update mapping with diagnostic thread
        if diag_thread:
            ISSUE_THREAD_MAP[issue_id] = {
                "diag_thread_id": diag_thread.service_thread_id,
                "sol_thread_id": existing_sol_id,
            }
        step_count = 0
        max_steps = 12
        
        while step_count < max_steps:
            step_count += 1
            await _flush_diag_stream(
                ws,
                diag_agent,
                diag_thread,
                current_input=current_input,
                issue_id=issue_id,
            )

            history = await _get_clean_history(agents_client, diag_thread.service_thread_id or "")
            last_text = history[-1]["text"] if history else ""
            state: Optional[AgentState] = None
            try:
                state = AgentState.model_validate_json(last_text)
            except Exception:
                state = None
            await _emit_diagnostic_state(
                ws,
                issue_id=issue_id,
                diag_thread=diag_thread,
                state=state,
            )

            if len(history) >= 50:
                await ws.send_json({
                    "event": "complete",
                    "status": "in_progress",
                    "issueId": issue_id,
                    "diag_thread_id": getattr(diag_thread, "service_thread_id", None)
                })
                break

            if not state:
                current_input = "Continue."
                continue

            if state.next_action == "handoff_to_solution_agent":
                decision = await _ask_intervention(
                    ws,
                    issue_id=issue_id,
                    diag_thread_id=getattr(diag_thread, "service_thread_id", None) or "",
                    thought=state.thought,
                    event_name="handoff_approval",
                )
                if decision == "approve":
                    await _run_solution_and_emit(
                        ws,
                        agents_client,
                        factory,
                        issue=issue,
                        state=state,
                        issue_id=issue_id,
                        diag_thread=diag_thread,
                    )
                    break
                elif decision == "deny":
                    current_input = "Handoff DENIED. Continue diagnosis."
                    continue
                else:
                    await ws.send_json({
                        "event": "error",
                        "detail": "Unknown decision or no approval",
                        "issueId": issue_id,
                        "diag_thread_id": getattr(diag_thread, "service_thread_id", None)
                    })
                    break

            if state.next_action == "await_user_approval":
                await ws.send_json({
                    "event": "awaiting_approval",
                    "issueId": issue_id,
                    "diag_thread_id": getattr(diag_thread, "service_thread_id", None),
                    "thought": state.thought
                })
                try:
                    decision_msg = await ws.receive_json()
                except WebSocketDisconnect:
                    break
                if decision_msg.get("type") != "intervene":
                    await ws.send_json({
                        "event": "error",
                        "detail": "Expected intervene message",
                        "issueId": issue_id,
                        "diag_thread_id": getattr(diag_thread, "service_thread_id", None)
                    })
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
                    await ws.send_json({
                        "event": "error",
                        "detail": "Unknown decision",
                        "issueId": issue_id,
                        "diag_thread_id": getattr(diag_thread, "service_thread_id", None)
                    })
                    break
                continue

            current_input = "Continue."

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"Error in workflow_ws: {e}")
        try:
            await ws.send_json({"event": "error", "detail": str(e)})
        except Exception:
            pass
    finally:
        # Proper cleanup with error handling for each client
        cleanup_errors = []
        
        # Close agents_client
        if agents_client:
            try:
                await agents_client.close()
                logger.info("agents_client closed")
            except Exception as e:
                cleanup_errors.append(f"agents_client: {e}")
                logger.error(f"Error closing agents_client: {e}")
        
        # Close project_client
        if project_client:
            try:
                await project_client.close()
                logger.info("project_client closed")
            except Exception as e:
                cleanup_errors.append(f"project_client: {e}")
                logger.error(f"Error closing project_client: {e}")
        
        # Close credential
        if credential:
            try:
                await credential.close()
                logger.info("credential closed")
            except Exception as e:
                cleanup_errors.append(f"credential: {e}")
                logger.error(f"Error closing credential: {e}")
        
        # Close WebSocket
        try:
            await ws.close()
            logger.info("WebSocket closed")
        except Exception as e:
            logger.error(f"Error closing WebSocket: {e}")
        
        if cleanup_errors:
            logger.warning(f"Cleanup completed with errors: {cleanup_errors}")
