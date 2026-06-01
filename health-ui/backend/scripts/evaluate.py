from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

current_dir = Path(__file__).resolve().parent
root_env = current_dir.parent.parent / ".env"


def load_root_env() -> None:
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        if root_env.exists():
            print(
                f"Warning: {root_env} exists but python-dotenv is not installed; "
                "run with uv or install backend dependencies to load it.",
                file=sys.stderr,
            )
        return

    load_dotenv(dotenv_path=root_env)


load_root_env()

from app.evaluation.golden_loader import filter_scenarios, load_golden_scenarios
from app.evaluation.judge import create_judge_client_from_env
from app.evaluation.reporting import render_console_report, write_json_report
from app.evaluation.runner import evaluate_scenarios, load_agent_traces


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run golden-set diagnostic evaluations.")
    parser.add_argument("--golden-dir", type=Path, default=None, help="JSON golden scenario file or directory.")
    parser.add_argument("--suite", default="fast", help="Scenario tag to run, or 'full'.")
    parser.add_argument("--traces", type=Path, default=None, help="Captured agent trace JSON file keyed by scenario id.")
    parser.add_argument("--output", type=Path, default=None, help="Write the full evaluation report as JSON.")
    parser.add_argument("--fail-under-deterministic", type=float, default=1.0, help="Minimum deterministic pass rate.")
    parser.add_argument("--fail-under-tool-selection", type=float, default=1.0, help="Minimum tool-selection pass rate.")
    parser.add_argument("--judge", action="store_true", help="Reserved for LLM-as-judge runs; no client is configured by default.")
    return parser


async def main_async(args: argparse.Namespace) -> int:
    scenarios = filter_scenarios(load_golden_scenarios(args.golden_dir), args.suite)
    traces = load_agent_traces(args.traces) if args.traces else None
    judge_client = create_judge_client_from_env() if args.judge else None
    try:
        report = await evaluate_scenarios(scenarios, suite=args.suite, traces=traces, judge_client=judge_client)
    finally:
        close = getattr(judge_client, "close", None)
        if close:
            await close()

    print(render_console_report(report))
    if args.output:
        write_json_report(report, args.output)

    if report.summary.deterministic_pass_rate < args.fail_under_deterministic:
        return 1
    if report.summary.tool_selection_pass_rate < args.fail_under_tool_selection:
        return 1
    return 0


def main() -> int:
    parser = build_parser()
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
