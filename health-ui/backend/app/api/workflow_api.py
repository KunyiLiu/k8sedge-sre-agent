import os
import asyncio
from typing import Annotated
from pydantic import Field, BaseModel
from dotenv import load_dotenv
from fastapi import APIRouter

# Azure AI Agent Framework
from azure.identity.aio import AzureCliCredential
from azure.ai.projects.aio import AIProjectClient
from agent_framework.azure import AzureAIAgentClient
from agent_framework import (
    ChatAgent, 
    SequentialBuilder, 
    WorkflowOutputEvent, 
    FileCheckpointStorage
)

load_dotenv()

# --- 1. TOOLS: THE AGENT'S SKILLS ---
def get_pod_details(
    pod_name: Annotated[str, Field(description="The name of the pod to inspect")]
) -> str:
    return f"LOGS for {pod_name}: 'java.lang.OutOfMemoryError: Java heap space' observed. Events: 'Back-off restarting failed container'."

def report_root_cause(
    summary: Annotated[str, Field(description="A detailed summary of the identified root cause.")]
) -> str:
    return f"[FINAL_DIAGNOSIS]: {summary}"

# --- 2. THE WORKFLOW LOGIC ---
async def run_workflow(pod_name: str) -> str:
    project_client = AIProjectClient(
        endpoint=os.getenv("AZURE_AI_PROJECT_ENDPOINT"),
        credential=AzureCliCredential()
    )
    checkpoint_dir = "./workflow_state"
    os.makedirs(checkpoint_dir, exist_ok=True)
    checkpoint_storage = FileCheckpointStorage(storage_path=checkpoint_dir)
    result = ""
    async with project_client:
        diag_agent = ChatAgent(
            chat_client=AzureAIAgentClient(project_client=project_client),
            name="Diagnostic_Agent",
            tools=[get_pod_details, report_root_cause],
            instructions="You are an SRE Diagnostic Agent. Find the root cause of failures."
        )
        sol_agent = ChatAgent(
            chat_client=AzureAIAgentClient(project_client=project_client),
            name="Solution_Agent",
            instructions="You are a Solution Architect. Based on the [FINAL_DIAGNOSIS], provide a kubectl fix and an escalation email summary."
        )
        workflow = (SequentialBuilder()
                    .participants([diag_agent, sol_agent])
                    .with_checkpointing(checkpoint_storage)
                    .build())
        events = workflow.run_stream(f"Investigate why pod '{pod_name}' is crashing.")
        async for event in events:
            if isinstance(event, WorkflowOutputEvent):
                for msg in event.data:
                    result += f"\n[{msg.author_name or 'Assistant'}]: {msg.text}"
    return result

# --- 3. FASTAPI ROUTER FOR TESTING ---
router = APIRouter()

class WorkflowRequest(BaseModel):
    pod_name: str

@router.post("/workflow/test")
async def workflow_test_api(req: WorkflowRequest):
    result = await run_workflow(req.pod_name)
    return {"result": result}
