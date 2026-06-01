import asyncio
import tempfile
import unittest
from pathlib import Path

from app.evaluation.golden_loader import filter_scenarios, load_golden_scenarios
from app.evaluation.judge import parse_judge_response, render_judge_prompt
from app.evaluation.models import AgentTrace, JudgeScore, Verdict
from app.evaluation.reporting import render_console_report
from app.evaluation.runner import evaluate_scenarios
from app.evaluation.scoring import expected_tools_in_order, score_scenario


class EvaluationFrameworkTests(unittest.TestCase):
    def test_loads_default_golden_set(self):
        scenarios = load_golden_scenarios()

        self.assertGreaterEqual(len(scenarios), 20)
        self.assertEqual(len({scenario.id for scenario in scenarios}), len(scenarios))
        self.assertTrue(any(scenario.id == "imagepullbackoff-private-registry-missing-imagepullsecret" for scenario in scenarios))

    def test_filters_by_suite_tag(self):
        scenarios = load_golden_scenarios()

        smoke = filter_scenarios(scenarios, "smoke")

        self.assertGreaterEqual(len(smoke), 1)
        self.assertTrue(all("smoke" in scenario.tags for scenario in smoke))

    def test_rejects_duplicate_scenario_ids(self):
        payload = """[
          {
            "id": "duplicate-id",
            "tags": ["fast"],
            "mock_profile": "profile-a",
            "issue": {
              "issueType": "Pending",
              "severity": "Warning",
              "resourceType": "Pod",
              "namespace": "default",
              "resourceName": "pod-a",
              "container": "app",
              "unhealthySince": "00h 01m",
              "unhealthyTimespan": 60,
              "message": "pending"
            },
            "expected_diagnosis": "diagnosis",
            "expected_primary_tools": ["functions.get_pod_events"]
          },
          {
            "id": "duplicate-id",
            "tags": ["fast"],
            "mock_profile": "profile-b",
            "issue": {
              "issueType": "Pending",
              "severity": "Warning",
              "resourceType": "Pod",
              "namespace": "default",
              "resourceName": "pod-b",
              "container": "app",
              "unhealthySince": "00h 01m",
              "unhealthyTimespan": 60,
              "message": "pending"
            },
            "expected_diagnosis": "diagnosis",
            "expected_primary_tools": ["functions.get_pod_events"]
          }
        ]"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenarios.json"
            path.write_text(payload, encoding="utf-8")

            with self.assertRaises(ValueError):
                load_golden_scenarios(path)

    def test_expected_tools_in_order_allows_extra_tools(self):
        self.assertTrue(
            expected_tools_in_order(
                ["functions.first", "functions.third"],
                ["functions.first", "functions.second", "functions.third"],
            )
        )
        self.assertFalse(
            expected_tools_in_order(
                ["functions.first", "functions.third"],
                ["functions.third", "functions.first"],
            )
        )

    def test_scores_missing_tool_as_failure(self):
        scenario = load_golden_scenarios()[0]
        trace = AgentTrace(
            agent_diagnosis="root cause",
            agent_tool_sequence=[scenario.expected_primary_tools[0]],
            agent_thought_chain=["checked first tool"],
        )

        score = score_scenario(scenario, trace)

        self.assertFalse(score.passed)
        self.assertEqual(score.tool_selection_verdict, Verdict.INCORRECT)

    def test_parse_judge_response_accepts_json_fence(self):
        score = parse_judge_response(
            """```json
{
  "diagnosis_score": 1,
  "diagnosis_verdict": "CORRECT",
  "diagnosis_reason": "matches",
  "reasoning_score": 4,
  "reasoning_reason": "well grounded",
  "tool_selection_score": 1,
  "tool_selection_verdict": "CORRECT",
  "tool_selection_reason": "right order",
  "evidence_grounding_score": 5,
  "evidence_grounding_reason": "uses evidence"
}
```"""
        )

        self.assertIsInstance(score, JudgeScore)
        self.assertEqual(score.diagnosis_verdict, Verdict.CORRECT)

    def test_render_judge_prompt_contains_expected_sections(self):
        scenario = load_golden_scenarios()[0]

        prompt = render_judge_prompt(scenario, scenario.recorded_agent_result)

        self.assertIn("INCIDENT:", prompt)
        self.assertIn("EXPECTED DIAGNOSIS:", prompt)
        self.assertIn("Return JSON only", prompt)

    def test_evaluate_scenarios_uses_recorded_traces(self):
        scenarios = filter_scenarios(load_golden_scenarios(), "smoke")

        report = asyncio.run(evaluate_scenarios(scenarios, suite="smoke"))

        self.assertEqual(report.summary.total, len(scenarios))
        self.assertEqual(report.summary.failed, 0)
        self.assertIn("Evaluation suite: smoke", render_console_report(report))


if __name__ == "__main__":
    unittest.main()
