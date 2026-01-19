import os
import asyncio
import json
from pathlib import Path
from typing import List, Dict, Optional, Literal
from pydantic import BaseModel
from dotenv import load_dotenv

# Azure AI Agent Framework
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.agents.aio import AgentsClient
from app.agents.agent_factory import AgentFactory
from app.models import AgentState

# 1. SETUP
load_dotenv()

# --- 2. STRUCTURED OUTPUT SCHEMA ---
# Using AgentState from app.models to align with backend agents

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
                # Initialize agents via AgentFactory (uses same deployment/config as backend)
                factory = AgentFactory(
                    project_client=project_client,
                    agents_client=agents_client,
                    credential=credential,
                    tools=[get_pod_details],
                    model_deployment_name="gpt-4.1-mini",
                )

                diag_agent = await factory.create_diagnostic_agent()
                sol_agent = await factory.create_solution_agent()

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
                # 2. Cleanup: Explicitly close internal chat clients and agents client
                try:
                    if 'diag_agent' in locals() and getattr(diag_agent, 'chat_client', None):
                        await diag_agent.chat_client.close()
                except Exception:
                    pass
                try:
                    if 'sol_agent' in locals() and getattr(sol_agent, 'chat_client', None):
                        await sol_agent.chat_client.close()
                except Exception:
                    pass
                await agents_client.close()
                # Note: project_client is closed automatically by the 'async with' block
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())