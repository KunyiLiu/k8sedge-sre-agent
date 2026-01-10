import os
import asyncio
import json
from pathlib import Path
from typing import Annotated
from pydantic import Field
from dotenv import load_dotenv

# Azure AI Agent Framework
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from agent_framework.azure import AzureAIAgentClient
from agent_framework import (
    ChatAgent, 
    SequentialBuilder, 
    WorkflowOutputEvent, 
    FileCheckpointStorage, 
    WorkflowCheckpoint
)

# 1. Get the directory where workflow_test.py is located
current_dir = Path(__file__).resolve().parent

# 2. Go up levels to find the root .env (adjust the .parent calls as needed)
# Based on your path: backend/app/ -> backend/ -> root/
root_env = current_dir.parent.parent / ".env"

# 3. Load specifically from that path
load_dotenv(dotenv_path=root_env)

# --- 1. TOOLS: THE AGENT'S SKILLS ---
def get_pod_details(
    pod_name: Annotated[str, Field(description="The name of the pod to inspect")]
) -> str:
    """Retrieves logs and events for a specific pod. Use this to investigate symptoms."""
    print(f"--- [Skill] Fetching data for {pod_name} ---")
    # Simulation: In Phase 2, this will call the Kubernetes API
    return f"LOGS for {pod_name}: 'java.lang.OutOfMemoryError: Java heap space' observed. Events: 'Back-off restarting failed container'."

def report_root_cause(
    summary: Annotated[str, Field(description="A detailed summary of the identified root cause.")]
) -> str:
    """TERMINAL TOOL: Call this ONLY when the investigation is complete. It hands off to the Solution Agent."""
    print(f"--- [Skill] Root Cause Reported ---")
    return f"[FINAL_DIAGNOSIS]: {summary}"

# --- 2. THE WORKFLOW LOGIC ---
async def main():
    # Setup Azure Client
    endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    if not endpoint:
        raise ValueError("Please set the AZURE_AI_PROJECT_ENDPOINT environment variable.")
    credential = DefaultAzureCredential()
    project_client = AIProjectClient(
        endpoint=endpoint,
        credential=credential
    )

    # Persistence Setup
    checkpoint_dir = "./workflow_state"
    checkpoint_tracker = "checkpoint_id.txt" # Simple file to store the active ID
    os.makedirs(checkpoint_dir, exist_ok=True)
    checkpoint_storage = FileCheckpointStorage(storage_path=checkpoint_dir)

    async with project_client:
        # AGENT 1: The Investigator (ReAct)
        diag_agent = ChatAgent(
            chat_client=AzureAIAgentClient(
                project_client=project_client,
                credential=credential,
                model_deployment_name="gpt-5-mini"
            ),
            model="gpt-5-mini",
            name="Diagnostic_Agent",
            tools=[get_pod_details, report_root_cause],
            instructions=(
                "You are an SRE Diagnostic Agent. Find the root cause of failures.\n"
                "For every step, follow this ReAct loop:\n"
                "1. THOUGHT: Reason about what the data means and what to check next.\n"
                "2. ACTION: Call a tool (get_pod_details).\n"
                "3. OBSERVATION: Analyze the output.\n\n"
                "Once the cause is found, call 'report_root_cause' to end your phase. \n"
                "If you are unsure or missing context, state exactly what information is missing instead of remaining silent."
            ),        
            temperature=1.0,
        )

        # AGENT 2: The Remediator
        sol_agent = ChatAgent(
            chat_client=AzureAIAgentClient(
                project_client=project_client,
                credential=credential,
                model_deployment_name="gpt-5-mini"
            ),
            name="Solution_Agent",
            model="gpt-5-mini",
            instructions="You are a Solution Architect. Based on the [FINAL_DIAGNOSIS], provide a kubectl fix and an escalation email summary. " \
            "If you are unsure or missing context, state exactly what information is missing instead of remaining silent.",
            temperature=1.0,
        )

        # Build the Sequence
        workflow = (SequentialBuilder()
                    .participants([diag_agent, sol_agent])
                    .with_checkpointing(checkpoint_storage)
                    .build())

        # Check for existing state to resume
        if os.path.exists(checkpoint_tracker):
            with open(checkpoint_tracker, 'r') as f:
                last_id = f.read().strip()
            print(f"--- Resuming Workflow: {last_id} ---")
            events = workflow.run_stream(checkpoint_id=last_id,
                                         checkpoint_storage=checkpoint_storage)
        else:
            print("--- Starting New Diagnostic Workflow ---")
            events = workflow.run_stream("Investigate why pod 'auth-service-v2' is crashing.")

        # Process the stream
        async for event in events:
            if isinstance(event, WorkflowOutputEvent):
                # Print the agent's thought process and tool outputs
                if event.data is None:
                    continue
                for msg in event.data:
                    role = msg.author_name or "Assistant"
                    print(f"\n[{role}]: {msg.text}")
                
                # Save the checkpoint ID so we can resume if the script stops
                checkpoints = await checkpoint_storage.list_checkpoints()
                if checkpoints:
                    latest_ckpt = checkpoints[-1]
                    with open(checkpoint_tracker, 'w') as f:
                        f.write(latest_ckpt.checkpoint_id)

        print("\n--- Workflow Completed ---")
        # 1. Remove the checkpoint tracker file
        if os.path.exists(checkpoint_tracker):
            os.remove(checkpoint_tracker) # Clean up on successful finish
        # 2. Optionally, clear the checkpoint storage
        if os.path.exists(checkpoint_dir):
            os.rmdir(checkpoint_dir) # Remove the checkpoint directory

if __name__ == "__main__":
    asyncio.run(main())
