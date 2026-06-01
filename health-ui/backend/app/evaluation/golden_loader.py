from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from app.evaluation.models import GoldenScenario


SUPPORTED_SUFFIXES = {".json"}


def default_golden_dir() -> Path:
    return Path(__file__).resolve().parent / "golden"


def _scenario_payloads(path: Path) -> Iterable[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                raise ValueError(f"{path} contains a non-object scenario entry")
            yield item
        return
    if isinstance(data, dict):
        yield data
        return
    raise ValueError(f"{path} must contain a scenario object or an array of scenarios")


def load_golden_scenarios(path: Path | str | None = None) -> List[GoldenScenario]:
    """Load golden scenarios from a JSON file or directory of JSON files."""

    source = Path(path) if path else default_golden_dir()
    files: List[Path]
    if source.is_dir():
        files = sorted(p for p in source.rglob("*") if p.suffix.lower() in SUPPORTED_SUFFIXES)
    elif source.is_file() and source.suffix.lower() in SUPPORTED_SUFFIXES:
        files = [source]
    else:
        raise FileNotFoundError(f"No supported golden scenario files found at {source}")

    scenarios: List[GoldenScenario] = []
    seen_ids: set[str] = set()
    for file_path in files:
        for payload in _scenario_payloads(file_path):
            scenario = GoldenScenario.model_validate(payload)
            if scenario.id in seen_ids:
                raise ValueError(f"Duplicate golden scenario id: {scenario.id}")
            seen_ids.add(scenario.id)
            scenarios.append(scenario)

    return scenarios


def filter_scenarios(scenarios: Iterable[GoldenScenario], suite: str) -> List[GoldenScenario]:
    if suite == "full":
        return list(scenarios)
    selected = [scenario for scenario in scenarios if suite in scenario.tags]
    if not selected:
        raise ValueError(f"No scenarios matched suite/tag '{suite}'")
    return selected
