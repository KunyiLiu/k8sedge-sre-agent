from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.models import EvaluationReport


def write_json_report(report: EvaluationReport, output_path: Path | str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")


def render_console_report(report: EvaluationReport) -> str:
    summary = report.summary
    lines = [
        f"Evaluation suite: {report.suite}",
        f"Scenarios: {summary.total} total, {summary.passed} passed, {summary.failed} failed",
        f"Deterministic pass rate: {summary.deterministic_pass_rate:.1%}",
        f"Diagnosis present rate: {summary.diagnosis_present_rate:.1%}",
        f"Tool-selection pass rate: {summary.tool_selection_pass_rate:.1%}",
    ]
    if summary.judge_diagnosis_pass_rate is not None:
        lines.extend(
            [
                f"Judge diagnosis pass rate: {summary.judge_diagnosis_pass_rate:.1%}",
                f"Average reasoning score: {summary.average_reasoning_score:.2f}",
                f"Average evidence-grounding score: {summary.average_evidence_grounding_score:.2f}",
            ]
        )
    lines.append("")
    lines.append("Scenario results:")
    for result in report.results:
        mark = "PASS" if result.deterministic_score.passed else "FAIL"
        lines.append(
            f"- {mark} {result.scenario_id}: "
            f"{result.deterministic_score.tool_selection_reason}"
        )
    return "\n".join(lines)


def report_to_json(report: EvaluationReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2)
