from __future__ import annotations

import json
import os
from typing import Protocol

from app.evaluation.models import AgentTrace, GoldenScenario, JudgeScore


class JudgeClient(Protocol):
    async def complete(self, prompt: str) -> str:
        """Return the raw judge model response text."""


class AzureAIProjectJudgeClient:
    """Judge client backed by Azure AI Project and DefaultAzureCredential."""

    def __init__(self, *, endpoint: str, model_deployment_name: str):
        from agent_framework import ChatAgent
        from agent_framework.azure import AzureAIAgentClient
        from azure.ai.projects.aio import AIProjectClient
        from azure.identity.aio import DefaultAzureCredential

        self._credential = DefaultAzureCredential()
        self._project_client = AIProjectClient(endpoint=endpoint, credential=self._credential)
        self._agent = ChatAgent(
            chat_client=AzureAIAgentClient(
                project_client=self._project_client,
                credential=self._credential,
                model_deployment_name=model_deployment_name,
            ),
            name="Evaluation_Judge",
            instructions=(
                "You are an expert SRE evaluation judge. Return valid JSON only and conform exactly "
                "to the requested schema."
            ),
            response_format=JudgeScore,
            temperature=0.0,
        )

    @classmethod
    def from_env(cls) -> "AzureAIProjectJudgeClient":
        endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
        if not endpoint:
            raise ValueError("AZURE_AI_PROJECT_ENDPOINT is required for Azure AI Project judge evaluation.")
        model_deployment_name = os.environ.get("EVALUATION_JUDGE_MODEL_DEPLOYMENT") or os.environ.get(
            "AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini"
        )
        return cls(endpoint=endpoint, model_deployment_name=model_deployment_name)

    async def complete(self, prompt: str) -> str:
        chunks: list[str] = []
        async for update in self._agent.run_stream(prompt):
            if update.text:
                chunks.append(update.text)
        content = "".join(chunks).strip()
        if not content:
            raise ValueError("Judge model returned an empty response")
        return content

    async def close(self) -> None:
        await self._project_client.close()
        await self._credential.close()


class OpenAIJudgeClient:
    """OpenAI/Azure OpenAI chat-completions judge client configured from env."""

    def __init__(self, *, model: str, azure: bool = False):
        self.model = model
        self.azure = azure
        if azure:
            from openai import AsyncAzureOpenAI

            self.client = AsyncAzureOpenAI(
                api_key=os.environ["AZURE_OPENAI_API_KEY"],
                azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            )
        else:
            from openai import AsyncOpenAI

            self.client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    @classmethod
    def from_env(cls) -> "OpenAIJudgeClient":
        azure_deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
        if azure_deployment:
            required = ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"]
            missing = [name for name in required if not os.environ.get(name)]
            if missing:
                raise ValueError(f"Missing Azure OpenAI judge environment variables: {', '.join(missing)}")
            return cls(model=azure_deployment, azure=True)

        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError(
                "Set OPENAI_API_KEY for OpenAI judging, or set AZURE_OPENAI_DEPLOYMENT, "
                "AZURE_OPENAI_API_KEY, and AZURE_OPENAI_ENDPOINT for Azure OpenAI judging."
            )
        return cls(model=model)

    async def complete(self, prompt: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Judge model returned an empty response")
        return content


def create_judge_client_from_env() -> JudgeClient:
    if os.environ.get("AZURE_AI_PROJECT_ENDPOINT"):
        return AzureAIProjectJudgeClient.from_env()
    return OpenAIJudgeClient.from_env()


def render_judge_prompt(scenario: GoldenScenario, trace: AgentTrace) -> str:
    incident_description = scenario.issue.model_dump_json(indent=2)
    expected_tools = json.dumps(scenario.expected_primary_tools, indent=2)
    agent_tools = json.dumps(trace.agent_tool_sequence, indent=2)
    reasoning_trace = "\n".join(f"{idx + 1}. {thought}" for idx, thought in enumerate(trace.agent_thought_chain))

    return f"""You are an expert SRE evaluating an AI agent's incident diagnosis.

INCIDENT:
{incident_description}

EXPECTED DIAGNOSIS:
{scenario.expected_diagnosis}

EXPECTED PRIMARY TOOLS:
{expected_tools}

EXPECTED EVIDENCE:
{json.dumps(scenario.expected_evidence, indent=2)}

AGENT OUTPUT:
- Diagnosed root cause: {trace.agent_diagnosis or ""}
- Tools called in order: {agent_tools}
- Reasoning trace:
{reasoning_trace}

Evaluate on four dimensions:

1. DIAGNOSIS: Does the agent's root cause semantically match the expected diagnosis?
   Use diagnosis_score 1 for correct, 0 for incorrect.

2. TOOL SELECTION: Did the agent call the expected primary tools in the expected order?
   Use tool_selection_score 1 for correct, 0 for incorrect.

3. REASONING QUALITY: Score 1-5 for clear hypothesis progression and avoidance of unsupported claims.

4. EVIDENCE GROUNDING: Score 1-5 for whether conclusions are grounded in incident facts and tool observations.

Return JSON only with exactly this shape:
{{
  "diagnosis_score": 1,
  "diagnosis_verdict": "CORRECT",
  "diagnosis_reason": "...",
  "reasoning_score": 4,
  "reasoning_reason": "...",
  "tool_selection_score": 1,
  "tool_selection_verdict": "CORRECT",
  "tool_selection_reason": "...",
  "evidence_grounding_score": 4,
  "evidence_grounding_reason": "..."
}}
"""


def parse_judge_response(raw_response: str) -> JudgeScore:
    text = raw_response.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return JudgeScore.model_validate(json.loads(text))


async def judge_trace(
    scenario: GoldenScenario,
    trace: AgentTrace,
    client: JudgeClient,
    *,
    max_format_retries: int = 1,
) -> JudgeScore:
    prompt = render_judge_prompt(scenario, trace)
    last_error: Exception | None = None
    for _ in range(max_format_retries + 1):
        raw = await client.complete(prompt)
        try:
            return parse_judge_response(raw)
        except Exception as exc:  # Formatting/schema retry only; surfaced if repeated.
            last_error = exc
            prompt += "\nYour previous response was invalid JSON for the required schema. Return valid JSON only."
    raise ValueError(f"Judge response did not match schema: {last_error}")
