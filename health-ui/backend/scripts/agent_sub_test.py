import os
import asyncio
from dotenv import load_dotenv
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.agents.aio import AgentsClient

# 1. SETUP
load_dotenv()

async def get_clean_history(agents_client: AgentsClient, thread_id: str):
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

def get_pod_details(pod_name: str) -> str:
    """Simulated SRE Tool."""
    print(f"--- [Skill] Fetching data for {pod_name} ---")
    return "LOGS: 'java.lang.OutOfMemoryError'. Events: 'Back-off restarting failed container'."

async def main():
    endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    if not endpoint:
        raise ValueError("AZURE_AI_PROJECT_ENDPOINT not set in environment variables.")

    credential = DefaultAzureCredential()

    async with AIProjectClient(endpoint=endpoint, credential=credential) as project_client:
        
        # Create AgentsClient for message operations
        # Extract connection info from project_client

        agents_client = AgentsClient(
            endpoint=endpoint,
            credential=credential,
            project_id="proj-SRE-K8s-AI")

        # 1. Get messages to the thread
        history = await get_clean_history(agents_client, "thread_384EVI8bMid0xtUSpcjQA83U")
        print(f"Thread History: {history}")

        # # 2. Create a thread

        thread = await agents_client.threads.create()
        await agents_client.messages.create(
            thread_id=thread.id,
            role="user",
            content="Investigate why pod 'nginx-pod-1234' is crashing."
        )
        print(f"Created Thread ID: {thread.id}")

        run = await agents_client.runs.create_and_process(thread_id=thread.id, agent_id="asst_u5aZbA4S1bCzDf7Kac4Unb1a")

        print(f"Created Run Thread ID: {run.thread_id}")

asyncio.run(main())
