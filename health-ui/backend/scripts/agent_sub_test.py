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


def human_gatekeeper(thought: str) -> str:
    """Console UI for Human-in-the-Loop."""
    print(f"\n🤖 [AGENT THOUGHT]: {thought}")
    print("-" * 30)
    print("1. APPROVE  | 2. DENY/HINT  | 3. FORCE HANDOFF  | 4. EXIT")
    choice = input("Select (1-4): ").strip()
    return choice


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

            # Run diagnostic agent in a loop with optional human approval
            diag_thread = diag_agent.get_new_thread()
            current_input = start_input
            step_count = 0
            max_steps = 12
            while step_count < max_steps:
                step_count += 1
                async for update in diag_agent.run_stream(current_input, thread=diag_thread):
                    print(update, end="")

                # Parse last message into AgentState
                history = await get_clean_history(agents_client, diag_thread.service_thread_id or "")
                last_text = history[-1]["text"] if history else ""
                state = None
                try:
                    state = AgentState.model_validate_json(last_text)
                    print("\nParsed state:", state.model_dump())
                except Exception:
                    print(f"\nNo structured AgentState JSON found in last message: {last_text}")

                # Break if conversation too long (fallback)
                if len(history) >= 50:
                    print("\nStopping: conversation history reached 50 messages.")
                    break

                # Control flow based on state
                if not state:
                    current_input = "Continue."
                    continue

                if state.next_action == "handoff_to_solution_agent":
                    print("\n✅ Diagnostic agent completed successfully and is handing off to solution agent.")
                    sol_agent = await factory.create_solution_agent()
                    sol_thread = sol_agent.get_new_thread()
                    prompt = (
                        f"Provide solution or escalation email for the issue {issue.issueType} for {issue.resourceType} "
                        f"[resourceName={issue.resourceName}, container={issue.container}, namespace={issue.namespace}]. "
                        f"Diagnostic root cause: [{state.root_cause}]. Other evidence: [{state.thought}]"
                    )
                    async for update in sol_agent.run_stream(prompt, thread=sol_thread):
                        print(update, end="")
                    break

                if state.next_action == "await_user_approval":
                    choice = human_gatekeeper(state.thought or "")
                    if choice == "1":
                        current_input = "Action APPROVED. Proceed."
                    elif choice == "2":
                        hint = input("Enter a short hint (optional): ").strip()
                        current_input = f"Action DENIED. Reason/Hint: {hint}"
                    elif choice == "3":
                        current_input = "Manual Handoff requested."
                    else:
                        print("Exiting per user request.")
                        break
                    continue

                # Default: continue the diagnostic loop
                current_input = "Continue."


    finally:
        await agents_client.close()
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
