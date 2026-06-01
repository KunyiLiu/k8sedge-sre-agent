from __future__ import annotations

from typing import Iterable, List

from app.evaluation.models import (
    AgentTrace,
    DeterministicScore,
    EvaluationSummary,
    GoldenScenario,
    ScenarioResult,
    TerminationStatus,
    Verdict,
)


def normalize_tool_name(tool_name: str) -> str:
    """Normalize tool names while preserving the functions.* convention."""

    value = tool_name.strip()
    if not value:
        return value
    if value.startswith("functions."):
        return value
    return f"functions.{value.split('.')[-1]}"


def expected_tools_in_order(expected: Iterable[str], actual: Iterable[str]) -> bool:
    expected_tools = [normalize_tool_name(tool) for tool in expected]
    actual_tools = [normalize_tool_name(tool) for tool in actual]
    cursor = 0
    for actual_tool in actual_tools:
        if cursor < len(expected_tools) and actual_tool == expected_tools[cursor]:
            cursor += 1
    return cursor == len(expected_tools)


def missing_expected_tools(expected: Iterable[str], actual: Iterable[str]) -> List[str]:
    expected_tools = [normalize_tool_name(tool) for tool in expected]
    actual_tools = [normalize_tool_name(tool) for tool in actual]
    return [tool for tool in expected_tools if tool not in actual_tools]


def forbidden_tools_used(forbidden: Iterable[str], actual: Iterable[str]) -> List[str]:
    forbidden_set = {normalize_tool_name(tool) for tool in forbidden}
    return [tool for tool in (normalize_tool_name(t) for t in actual) if tool in forbidden_set]


def score_scenario(scenario: GoldenScenario, trace: AgentTrace) -> DeterministicScore:
    completed = trace.termination_status == TerminationStatus.COMPLETED and not trace.error
    diagnosis_present = bool((trace.agent_diagnosis or "").strip())
    ordered = expected_tools_in_order(scenario.expected_primary_tools, trace.agent_tool_sequence)
    missing = missing_expected_tools(scenario.expected_primary_tools, trace.agent_tool_sequence)
    forbidden_used = forbidden_tools_used(scenario.forbidden_tools, trace.agent_tool_sequence)

    if ordered:
        tool_verdict = Verdict.CORRECT
        tool_score = 1
        tool_reason = "Agent called the expected primary tools in order."
    else:
        tool_verdict = Verdict.INCORRECT
        tool_score = 0
        if missing:
            tool_reason = f"Missing expected primary tools: {', '.join(missing)}."
        else:
            tool_reason = "Expected primary tools were called, but not in the required order."

    if forbidden_used:
        forbidden_verdict = Verdict.INCORRECT
        forbidden_reason = f"Agent called forbidden tools: {', '.join(forbidden_used)}."
    else:
        forbidden_verdict = Verdict.CORRECT
        forbidden_reason = "Agent did not call forbidden tools."

    passed = completed and diagnosis_present and ordered and not forbidden_used
    return DeterministicScore(
        scenario_id=scenario.id,
        completed=completed,
        diagnosis_present=diagnosis_present,
        tool_selection_verdict=tool_verdict,
        tool_selection_score=tool_score,
        tool_selection_reason=tool_reason,
        forbidden_tools_verdict=forbidden_verdict,
        forbidden_tools_reason=forbidden_reason,
        passed=passed,
    )


def summarize_results(results: List[ScenarioResult]) -> EvaluationSummary:
    total = len(results)
    if total == 0:
        return EvaluationSummary(
            total=0,
            passed=0,
            failed=0,
            deterministic_pass_rate=0.0,
            diagnosis_present_rate=0.0,
            tool_selection_pass_rate=0.0,
        )

    passed = sum(1 for result in results if result.deterministic_score.passed)
    diagnosis_present = sum(1 for result in results if result.deterministic_score.diagnosis_present)
    tool_selection = sum(
        1 for result in results if result.deterministic_score.tool_selection_verdict == Verdict.CORRECT
    )
    judge_scores = [result.judge_score for result in results if result.judge_score is not None]
    judge_diag_rate = None
    avg_reasoning = None
    avg_grounding = None
    if judge_scores:
        judge_diag_rate = sum(1 for score in judge_scores if score.diagnosis_verdict == Verdict.CORRECT) / len(judge_scores)
        avg_reasoning = sum(score.reasoning_score for score in judge_scores) / len(judge_scores)
        avg_grounding = sum(score.evidence_grounding_score for score in judge_scores) / len(judge_scores)

    return EvaluationSummary(
        total=total,
        passed=passed,
        failed=total - passed,
        deterministic_pass_rate=passed / total,
        diagnosis_present_rate=diagnosis_present / total,
        tool_selection_pass_rate=tool_selection / total,
        judge_diagnosis_pass_rate=judge_diag_rate,
        average_reasoning_score=avg_reasoning,
        average_evidence_grounding_score=avg_grounding,
    )
