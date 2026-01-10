import os
import asyncio
import json
from pathlib import Path
from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Azure AI Agent Framework
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.agents.aio import AgentsClient
from agent_framework.azure import AzureAIAgentClient
from agent_framework import ChatAgent

# 1. SETUP
load_dotenv()

# --- 2. STRUCTURED OUTPUT SCHEMA ---
class AgentState(BaseModel):
    thought: str
    action: Optional[str] = None
    action_input: Optional[str] = None
    next_action: Literal["continue", "await_user_approval", "handoff_to_solution_agent"]
    root_cause: Optional[str] = None

# --- 3. TOOLS ---
def get_pod_details(pod_name: str) -> str:
    """Simulated SRE Tool."""
    print(f"--- [Skill] Fetching data for {pod_name} ---")
    return "LOGS: 'java.lang.OutOfMemoryError'. Events: 'Back-off restarting failed container'."

# --- 4. THREAD & REPORTING UTILITIES ---
async def get_clean_history(agents_client: AgentsClient, thread_id: str) -> List[Dict]:
    """Fetches final messages from Azure for auditing."""
    history = []
    try:
        # Use AgentsClient.messages.list() to get messages
        async for message in agents_client.messages.list(thread_id=thread_id):
            text = ""
            if getattr(message, 'text_messages', None):
                texts = [tm.text.value for tm in message.text_messages if hasattr(tm, 'text')]
                text = texts[-1] if texts else ''
            else:
                text = getattr(message, 'text', '') or ''
            
            history.append({"role": message.role, "text": text})
        
        # Reverse to get chronological order
        history.reverse()
    except Exception as e:
        print(f"Error fetching history: {e}")
    
    return history

def human_gatekeeper(thought: str):
    """Console UI for Human-in-the-Loop."""
    print(f"\n🤖 [AGENT THOUGHT]: {thought}")
    print("-" * 30)
    print("1. APPROVE  | 2. DENY/HINT  | 3. FORCE HANDOFF  | 4. EXIT")
    choice = input("Select (1-4): ").strip()
    return choice

# --- 5. THE ORCHESTRATOR ---
async def main():
    endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    if not endpoint:
        raise ValueError("AZURE_AI_PROJECT_ENDPOINT not set in environment variables.")

    credential = DefaultAzureCredential()
    
    try:
        async with AIProjectClient(endpoint=endpoint, credential=credential) as project_client:
        
            # Create AgentsClient for message operations
            # Extract connection info from project_client
            agents_client = AgentsClient(endpoint=endpoint, credential=credential)
            try:
                diag_chat_client = AzureAIAgentClient(project_client=project_client, credential=credential, model_deployment_name="gpt-4.1-mini")
                sol_chat_client = AzureAIAgentClient(project_client=project_client, credential=credential, model_deployment_name="gpt-4.1-mini")

                try:
                    diag_agent_id = (await agents_client.get_agent("asst_lMlS3XIxtrbImS0HEsMmiliY")).id
                except:
                    diag_agent_id = None

                # Initialize Agents
                diag_agent = ChatAgent(
                    chat_client=diag_chat_client,
                    id=diag_agent_id,
                    name="Diagnostic Agent",
                    tools=[get_pod_details],
                    response_format=AgentState,
                    instructions=(
                        "You are an SRE Diagnostic Agent. Find the root cause of failures.\n"
                        "For every step, follow this ReAct loop:\n"
                        "1. THOUGHT: Reason about what the data means and what to check next.\n"
                        "2. ACTION: Call a tool (get_pod_details).\n"
                        "3. OBSERVATION: Analyze the output.\n\n"
                        "Output json as format:"
                        "{'thought': str, 'action': Optional[str], 'action_input': Optional[str], "
                        "'next_action': 'continue' | 'await_user_approval' | 'handoff_to_solution_agent', "
                        "'root_cause': Optional[str]}"
                    ),
                    temperature=0.0
                )

                sol_agent_id = (await agents_client.get_agent("asst_4S7r6vAvX3nBQRGsj8C1RQk2")).id or None

                sol_agent = ChatAgent(
                    chat_client=sol_chat_client,
                    id=sol_agent_id,
                    name="Solution Agent",
                    instructions="Provide a kubectl fix based on the root cause.",
                    temperature=0.2
                )

                # State Variables
                current_input = "Investigate why pod 'auth-service-v2' is crashing."
                final_diagnosis = None
                step_count = 0
                MAX_STEPS = 4
                
                # Thread Management - create thread using the agents that have the proper client
                diag_thread = diag_agent.get_new_thread()

                print(f"--- Workflow Started --- for thread {diag_thread.service_thread_id}")

                while not final_diagnosis:
                    step_count += 1
                    if step_count > MAX_STEPS:
                        print("⚠️ Step limit reached.")
                        break

                    # --- LIVE EXECUTION ---
                    response_text = ""
                    result = await diag_agent.run(current_input, thread=diag_thread)
                    print(f"ID now: {diag_thread.service_thread_id}")

                    msgs = getattr(result, "messages", [])
                    if msgs:
                        response_text = msgs[-1].text
                        print(f"\n[Diagnostic Agent]: {response_text[:200]}...")

                    # --- STATE TRANSITION LOGIC ---
                    try:
                        state = AgentState.model_validate_json(response_text)
                        print(f"\n[Step {step_count}] Reasoning: {state.thought}")
                    except Exception as e:
                        print(f"JSON Parse Fail: {e}")
                        continue

                    if state.next_action == "handoff_to_solution_agent":
                        final_diagnosis = state.root_cause
                    
                    elif state.next_action == "await_user_approval":
                        choice = human_gatekeeper(state.thought)
                        if choice == "1":
                            current_input = f"Action {state.action} APPROVED. Proceed."
                        elif choice == "2":
                            hint = input("Enter denial reason or hint: ")
                            current_input = f"Action DENIED. Reason/Hint: {hint}"
                        elif choice == "3":
                            final_diagnosis = f"Manual Handoff: {state.thought}"
                        else: 
                            break

                    elif state.next_action == "continue":
                        if state.action == "get_pod_details":
                            obs = get_pod_details(state.action_input or "")
                            current_input = f"Observation: {obs}"

                # --- PHASE 2: SOLUTION & REPORT ---
                if final_diagnosis:
                    print(f"\n✅ ROOT CAUSE: {final_diagnosis}")
                    sol_thread = sol_agent.get_new_thread()

                    result = await sol_agent.run(f"Fix this: {final_diagnosis}", thread=sol_thread)

                    msgs = getattr(result, "messages", [])
                    if msgs:
                        msg_text = msgs[-1].text if hasattr(msgs[-1], 'text') else str(msgs[-1])
                        print(f"\n[Solution Agent]: {msg_text}")

                    # --- FINAL AUDIT LOG ---
                    if sol_thread.service_thread_id and diag_thread.service_thread_id:
                        diag_log = await get_clean_history(agents_client, diag_thread.service_thread_id)
                        sol_log = await get_clean_history(agents_client, sol_thread.service_thread_id)

                        full_report = diag_log + sol_log
                        print("\n--- Final Audit Log Created ---")
                        print(json.dumps(full_report, indent=2))
                        # In production, save 'full_report' to your database/file here.
            finally:
                # 2. THE FIX: Explicitly close the internal chat clients
                # This shuts down the aiohttp connectors
                await diag_chat_client.close()
                await sol_chat_client.close()
                await agents_client.close()
                # Note: project_client is closed automatically by the 'async with' block
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())