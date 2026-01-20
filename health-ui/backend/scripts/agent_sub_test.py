import os
import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.agents.aio import AgentsClient

# Ensure backend directory is on sys.path so 'app' and 'skills' packages can be imported when running this script directly.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agents.agent_factory import AgentFactory
from app.models import HealthIssue, ResourceType, AgentState
from skills.mock_k8s_diag import create_mock_tools


# Setup
load_dotenv()


def format_duration(seconds: int) -> str:
    """Simple duration formatter: returns "HHh MMm" for a given seconds value."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours:02d}h {minutes:02d}m"


async def get_clean_history(agents_client: AgentsClient, thread_id: str):
    """Fetches final messages from Azure for auditing."""
    history = []
    try:
        async for message in agents_client.messages.list(thread_id=thread_id):
            text = ""
            if getattr(message, "text_messages", None):
                texts = [tm.text.value for tm in message.text_messages if hasattr(tm, "text")]
                text = texts[-1] if texts else ""
            else:
                text = getattr(message, "text", "") or ""

            history.append({"role": message.role, "text": text})
        history.reverse()
    except Exception as e:
        print(f"Error fetching history: {e}")
    return history


async def main():
    # Environment
    endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    if not endpoint:
        raise ValueError("AZURE_AI_PROJECT_ENDPOINT not set in environment variables.")

    credential = DefaultAzureCredential()

    try:
        async with AIProjectClient(endpoint=endpoint, credential=credential) as project_client:
            agents_client = AgentsClient(endpoint=endpoint, credential=credential)

            # Mock tools profile to simulate CrashLoopBackOff
            tools = create_mock_tools(profile="crashloop")

            # Build factory and agents
            factory = AgentFactory(
                project_client=project_client,
                agents_client=agents_client,
                credential=credential,
                tools=tools,
            )
            diag_agent = await factory.create_diagnostic_agent()

            # Prepare HealthIssue input
            issue = HealthIssue(
                issueType="CrashLoopBackOff",
                severity="High",
                resourceType=ResourceType.Pod,
                namespace="default",
                resourceName="web-0",
                container="web",
                unhealthySince=format_duration(3600),
                unhealthyTimespan=3600,
                message="Container is in CrashLoopBackOff state."
            )
            start_input = (
                f"Investigate the issue {issue.issueType} for {issue.resourceType} [resourceName={issue.resourceName}, container={issue.container}, namespace={issue.namespace}]."
            )

            # Run diagnostic agent
            diag_thread = diag_agent.get_new_thread()
            result = await diag_agent.run(start_input, thread=diag_thread)
            msgs = getattr(result, "messages", [])
            last_text = msgs[-1].text if msgs else ""
            print("\nLast diagnostic response:\n", last_text)

            # Try to parse as AgentState JSON (if agent followed schema)
            state = None
            try:
                state = AgentState.model_validate_json(last_text)
                print("\nParsed state:", state.model_dump())
            except Exception:
                print("\nNo structured AgentState JSON found in last message.")

            # Fetch and print history
            if diag_thread.service_thread_id:
                history = await get_clean_history(agents_client, diag_thread.service_thread_id)
                print("\nThread History:")
                for h in history:
                    print(f"[{h['role']}] {h['text']}")
            else:
                print("\nNo service-managed thread ID available yet; skipping history fetch.")
    finally:
        await agents_client.close()
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
