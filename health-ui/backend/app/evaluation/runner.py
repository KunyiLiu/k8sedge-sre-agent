from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from app.evaluation.judge import JudgeClient, judge_trace
from app.evaluation.models import AgentTrace, EvaluationReport, GoldenScenario, ScenarioResult
from app.evaluation.scoring import score_scenario, summarize_results


def load_agent_traces(path: Path | str) -> Dict[str, AgentTrace]:
    """Load captured agent traces keyed by scenario id.

    Accepted input shapes:
    - {"scenario-id": {"agent_diagnosis": ...}}
    - [{"scenario_id": "scenario-id", "trace": {...}}, ...]
    - [{"id": "scenario-id", "agent_diagnosis": ...}, ...]
    """

    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    traces: Dict[str, AgentTrace] = {}
    if isinstance(data, dict):
        for scenario_id, payload in data.items():
            traces[scenario_id] = AgentTrace.model_validate(payload)
        return traces
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                raise ValueError(f"{source} contains a non-object trace entry")
            scenario_id = item.get("scenario_id") or item.get("id")
            if not scenario_id:
                raise ValueError(f"{source} trace entry is missing scenario_id")
            payload = item.get("trace") if isinstance(item.get("trace"), dict) else item
            traces[scenario_id] = AgentTrace.model_validate(payload)
        return traces
    raise ValueError(f"{source} must contain a trace map or trace list")


async def evaluate_scenarios(
    scenarios: Iterable[GoldenScenario],
    *,
    suite: str,
    traces: Optional[Dict[str, AgentTrace]] = None,
    judge_client: Optional[JudgeClient] = None,
) -> EvaluationReport:
    results: List[ScenarioResult] = []
    traces = traces or {}

    for scenario in scenarios:
        trace = traces.get(scenario.id) or scenario.recorded_agent_result
        if trace is None:
            raise ValueError(
                f"No agent trace provided for scenario '{scenario.id}'. "
                "Pass --traces or add recorded_agent_result to the golden scenario."
            )

        deterministic_score = score_scenario(scenario, trace)
        judge_score = None
        judge_error = None
        if judge_client:
            try:
                judge_score = await judge_trace(scenario, trace, judge_client)
            except Exception as exc:
                judge_error = str(exc)

        results.append(
            ScenarioResult(
                scenario_id=scenario.id,
                scenario_tags=scenario.tags,
                issue_type=scenario.issue.issueType,
                expected_diagnosis=scenario.expected_diagnosis,
                expected_primary_tools=scenario.expected_primary_tools,
                trace=trace,
                deterministic_score=deterministic_score,
                judge_score=judge_score,
                judge_error=judge_error,
            )
        )

    return EvaluationReport(
        suite=suite,
        judge_enabled=judge_client is not None,
        summary=summarize_results(results),
        results=results,
    )
