import os
import asyncio
import json
from typing import Annotated
from pydantic import Field
from dotenv import load_dotenv

# Azure AI Agent Framework
from azure.identity.aio import AzureCliCredential
from azure.ai.projects.aio import AIProjectClient
from agent_framework.azure import AzureAIAgentClient
from agent_framework import (
    ChatAgent, 
    SequentialBuilder, 
    WorkflowOutputEvent, 
    FileCheckpointStorage, 
    WorkflowCheckpoint
)

load_dotenv()

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
    project_client = AIProjectClient(
        endpoint=os.getenv("AZURE_AI_PROJECT_ENDPOINT"),
        credential=AzureCliCredential()
    )

    # Persistence Setup
    checkpoint_dir = "./workflow_state"
    checkpoint_tracker = "checkpoint_id.txt" # Simple file to store the active ID
    os.makedirs(checkpoint_dir, exist_ok=True)
    checkpoint_storage = FileCheckpointStorage(storage_path=checkpoint_dir)

    async with project_client:
        # AGENT 1: The Investigator (ReAct)
        diag_agent = ChatAgent(
            chat_client=AzureAIAgentClient(project_client=project_client),
            name="Diagnostic_Agent",
            tools=[get_pod_details, report_root_cause],
            instructions=(
                "You are an SRE Diagnostic Agent. Find the root cause of failures.\n"
                "For every step, follow this ReAct loop:\n"
                "1. THOUGHT: Reason about what the data means and what to check next.\n"
                "2. ACTION: Call a tool (get_pod_details).\n"
                "3. OBSERVATION: Analyze the output.\n\n"
                "Once the cause is found, call 'report_root_cause' to end your phase."
            )
        )

        # AGENT 2: The Remediator
        sol_agent = ChatAgent(
            chat_client=AzureAIAgentClient(project_client=project_client),
            name="Solution_Agent",
            instructions="You are a Solution Architect. Based on the [FINAL_DIAGNOSIS], provide a kubectl fix and an escalation email summary."
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
            events = workflow.run_stream_from_checkpoint(checkpoint_id=last_id)
        else:
            print("--- Starting New Diagnostic Workflow ---")
            events = workflow.run_stream("Investigate why pod 'auth-service-v2' is crashing.")

        # Process the stream
        async for event in events:
            if isinstance(event, WorkflowOutputEvent):
                # Print the agent's thought process and tool outputs
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
        if os.path.exists(checkpoint_tracker):
            os.remove(checkpoint_tracker) # Clean up on successful finish

if __name__ == "__main__":
    asyncio.run(main())
