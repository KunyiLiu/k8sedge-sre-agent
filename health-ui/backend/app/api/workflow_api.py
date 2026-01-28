import os
import json
import logging
from typing import Optional, Literal, Any
from dotenv import load_dotenv
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.models import HealthIssue, AgentState, WebSocketPayload, SolutionResponse, MessageItem
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import ListSortOrder
from app.agents.agent_factory import AgentFactory
from agent_framework import ChatAgent
from skills.mock_k8s_diag import create_mock_tools

load_dotenv()

logger = logging.getLogger(__name__)
if not logger.handlers:  # avoid dupes on reload
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.DEBUG)     # or INFO
logger.propagate = False           # prevent double logging via root

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
    payload = WebSocketPayload(
        event="history",
        issueId=issue_id,
        diag_thread_id=diag_thread_id,
        sol_thread_id=sol_thread_id,
        diag_history=[MessageItem(**h) for h in diag_history],
        sol_history=[MessageItem(**h) for h in sol_history],
    )
    await ws.send_json(payload.model_dump())

async def _ask_resume(ws: WebSocket, *, issue_id: str, diag_thread_id: str) -> bool:
    payload = WebSocketPayload(
        event="resume_available",
        issueId=issue_id,
        diag_thread_id=diag_thread_id,
        question="Resume previous diagnostic?",
    )
    await ws.send_json(payload.model_dump())
    try:
        msg = await ws.receive_json()
    except WebSocketDisconnect:
        return False
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning(f"Invalid resume message: {e}")
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

async def _get_clean_history(agents_client: AgentsClient, thread_id: str, user_message_included: bool = False) -> list[dict]:
    history: list[dict] = []
    async for message in agents_client.messages.list(thread_id=thread_id):
        if user_message_included is False and message.role == "user":
            continue
        text = getattr(message, "text", "") or ""
        if getattr(message, "text_messages", None):
            texts = [tm.text.value for tm in message.text_messages if hasattr(tm, "text")]
            text = texts[-1] if texts else text
        history.append({"role": message.role, "text": text})
    history.reverse()
    return history

async def _get_last_message_text(agents_client: AgentsClient, thread_id: str) -> str:
    last_text = ""
    async for message in agents_client.messages.list(thread_id=thread_id, order=ListSortOrder.DESCENDING, limit=1):
        text = getattr(message, "text", "") or ""
        if getattr(message, "text_messages", None):
            texts = [tm.text.value for tm in message.text_messages if hasattr(tm, "text")]
            text = texts[-1] if texts else text
        last_text = text
    return last_text

async def _flush_diag_stream(
    ws: WebSocket,
    diag_agent,
    diag_thread,
    *,
    current_input: str,
    issue_id: str,
):
    buffer = ""
    try:
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
                    payload = WebSocketPayload(
                        event="diagnostic",
                        issueId=issue_id,
                        diag_thread_id=getattr(diag_thread, "service_thread_id", None),
                        state=state_flush,
                    )
                    await ws.send_json(payload.model_dump())
                    logger.debug(f"Sent diagnostic; thought preview: {state_flush.thought[:50]}...")
                    buffer = buffer[start + end:]
                except json.JSONDecodeError:
                    break
                except Exception as e:
                    logger.warning(f"Validation error while parsing stream: {e}")
                    buffer = buffer[start + 1:]
    finally:
        # Preserve any existing solution thread id for this issue, if present
        if diag_thread:
            # Update only the diag_thread_id key to avoid overwriting other stored keys
            if issue_id not in ISSUE_THREAD_MAP:
                ISSUE_THREAD_MAP[issue_id] = {}
            ISSUE_THREAD_MAP[issue_id]["diag_thread_id"] = diag_thread.service_thread_id

            logger.info(f"---UPDATED ISSUE_THREAD_MAP: {ISSUE_THREAD_MAP} for issueId={issue_id} and diag_thread_id={diag_thread.service_thread_id}---")


async def _ask_intervention(
    ws: WebSocket,
    *,
    issue_id: str,
    diag_thread_id: str,
    question: Optional[str] = None,
    event_name: Literal["awaiting_approval", "handoff_approval"] = "awaiting_approval",
) -> Optional[str]:
    payload = WebSocketPayload(
        event=event_name,
        issueId=issue_id,
        diag_thread_id=diag_thread_id,
        question=question,
    )
    await ws.send_json(payload.model_dump())
    try:
        decision_msg = await ws.receive_json()
    except WebSocketDisconnect:
        return None
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning(f"Invalid intervention message: {e}")
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
        f"Diagnostic root cause: [{state.root_cause}]. Other evidence: [{state.thought}]. It is recommended to escalate."
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

    # Attempt to parse solution result into SolutionResponse; fallback to detail
    solution_state = None
    try:
        data = json.loads(getattr(result, "text", ""))
        solution_state = SolutionResponse.model_validate(data)
    except Exception as e:
        logger.warning(f"Failed to parse solution response into structured JSON: {e}")

    handoff_payload = WebSocketPayload(
        event="handoff",
        issueId=issue_id,
        diag_thread_id=getattr(diag_thread, "service_thread_id", None),
        sol_thread_id=sol_thread_id,
        state=solution_state,
    )
    try:
        await ws.send_json(handoff_payload.model_dump())
    except Exception as e:
        logger.warning(f"WebSocket send failed for handoff: {e}")
        return
    # Emit updated histories after handoff to allow frontend to render full context
    try:
        await _send_thread_histories(
            ws,
            agents_client,
            issue_id=issue_id,
            diag_thread_id=getattr(diag_thread, "service_thread_id", None),
            sol_thread_id=sol_thread_id,
        )
    except Exception as e:
        logger.warning(f"Failed to send thread histories post-handoff: {e}")
    
    complete_payload = WebSocketPayload(
        event="complete",
        status="handoff",
        issueId=issue_id,
        diag_thread_id=getattr(diag_thread, "service_thread_id", None),
        sol_thread_id=sol_thread_id,
    )
    try:
        await ws.send_json(complete_payload.model_dump())
    except Exception as e:
        logger.warning(f"WebSocket send failed for complete: {e}")
        return

@router.websocket("/workflow/ws")
async def workflow_ws(ws: WebSocket):
    await ws.accept()
    project_client: Optional[AIProjectClient] = None
    agents_client: Optional[AgentsClient] = None
    credential: Optional[DefaultAzureCredential] = None
    diag_agent: Optional[ChatAgent] = None
    
    try:
        init_msg = await ws.receive_json()
        if init_msg.get("type") != "start" or not init_msg.get("issue"):
            await ws.send_json({"event": "error", "detail": "First message must be type=start with 'issue'"})
            await ws.close()
            return

        issue = HealthIssue(**init_msg["issue"])
        project_client, agents_client, credential = await _get_clients()

        if issue.issueType == "ImagePullBackOff":
            tools = create_mock_tools(profile="imagepullbackoff")
        else:
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

        logger.info(f"---ISSUE_THREAD_MAP: {ISSUE_THREAD_MAP} for issueId={issue_id}---")

        if existing_diag_id:
            try:
                await _send_thread_histories(
                    ws, agents_client,
                    issue_id=issue_id,
                    diag_thread_id=existing_diag_id,
                    sol_thread_id=existing_sol_id,
                )
            except Exception as e:
                logger.warning(f"Failed to send existing thread histories: {e}")
                # Fallback: send minimal history using last solution message
                last_sol_text = ""
                try:
                    if existing_sol_id:
                        last_sol_text = await _get_last_message_text(agents_client, existing_sol_id)
                except Exception as e2:
                    logger.warning(f"Failed to fetch last solution message: {e2}")
                try:
                    payload = WebSocketPayload(
                        event="history",
                        issueId=issue_id,
                        diag_thread_id=existing_diag_id,
                        sol_thread_id=existing_sol_id,
                        diag_history=[],
                        sol_history=[MessageItem(role="assistant", text=last_sol_text)] if last_sol_text else [],
                    )
                    await ws.send_json(payload.model_dump())
                except Exception as e3:
                    logger.warning(f"Fallback history send failed: {e3}")
            if existing_sol_id:
                # If solution thread exists, just show histories and finish
                payload = WebSocketPayload(
                    event="complete",
                    status="handoff",
                    issueId=issue_id,
                    diag_thread_id=existing_diag_id,
                    sol_thread_id=existing_sol_id,
                )
                try:
                    await ws.send_json(payload.model_dump())
                except Exception as e:
                    logger.warning(f"WebSocket send failed for existing complete: {e}")
                return
            # Ask to resume diagnostic
            should_resume = await _ask_resume(ws, issue_id=issue_id, diag_thread_id=existing_diag_id)
            if should_resume:
                diag_thread = diag_agent.get_new_thread(service_thread_id=existing_diag_id)
                if diag_thread is None:
                    diag_thread = diag_agent.get_new_thread()
                    logger.info("Started new diagnostic thread because resume was unavailable")
                else:
                    current_input = "Resume investigation based on the history above."
                    logger.info(f"Resuming diagnostic thread for issueId={issue_id} threadId={existing_diag_id}")
            else:
                payload = WebSocketPayload(
                    event="complete",
                    status="in_progress",
                    issueId=issue_id,
                    diag_thread_id=existing_diag_id,
                )
                await ws.send_json(payload.model_dump())
                return
        else:
            diag_thread = diag_agent.get_new_thread()
            logger.info(f"Started new diagnostic thread for issueId={issue_id}.")

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

            if len(history) >= 50:
                payload = WebSocketPayload(
                    event="complete",
                    status="in_progress",
                    issueId=issue_id,
                    diag_thread_id=getattr(diag_thread, "service_thread_id", None),
                )
                await ws.send_json(payload.model_dump())
                break

            if not state:
                current_input = "Continue."
                continue

            if state.next_action == "handoff_to_solution_agent":
                decision = await _ask_intervention(
                    ws,
                    issue_id=issue_id,
                    diag_thread_id=getattr(diag_thread, "service_thread_id", None) or "",
                    question=f"Root cause: {state.root_cause} Proceed to handoff to solution agent?",
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
                    payload = WebSocketPayload(
                        event="error",
                        issueId=issue_id,
                        diag_thread_id=getattr(diag_thread, "service_thread_id", None),
                    )
                    await ws.send_json(payload.model_dump())
                    break

            if state.next_action == "await_user_approval":
                d = await _ask_intervention(
                    ws,
                    issue_id=issue_id,
                    diag_thread_id=getattr(diag_thread, "service_thread_id", None) or "",
                    question=f"Current investigation: {state.thought}. Approve next action?",
                    event_name="awaiting_approval",
                )
                if d == "approve":
                    current_input = "Action APPROVED. Proceed."
                    continue
                elif d == "deny":
                    # We can accept an optional hint via a second message if desired in future
                    current_input = "Action DENIED."
                    continue
                elif d == "handoff":
                    current_input = "Manual Handoff requested."
                    continue
                else:
                    payload = WebSocketPayload(
                        event="error",
                        issueId=issue_id,
                        diag_thread_id=getattr(diag_thread, "service_thread_id", None),
                    )
                    await ws.send_json(payload.model_dump())
                    break

            current_input = "Continue."

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"Error in workflow_ws: {e}")
        await ws.send_json({"event": "error", "detail": str(e)})
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
        
        # Close project_client
        if project_client:
            try:
                await project_client.close()
                logger.info("project_client closed")
            except Exception as e:
                cleanup_errors.append(f"project_client: {e}")
        
        # Close credential
        if credential:
            try:
                await credential.close()
                logger.info("credential closed")
            except Exception as e:
                cleanup_errors.append(f"credential: {e}")
        
        # Close WebSocket
        try:
            await ws.close()
            logger.info("WebSocket closed")
        except Exception as e:
            logger.error(f"Error closing WebSocket: {e}")
        
        if cleanup_errors:
            logger.warning(f"Cleanup completed with errors: {cleanup_errors}")
