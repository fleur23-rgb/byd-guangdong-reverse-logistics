from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from .data_loader import InputData
from .solve import ScenarioResult, solve_scenario


def run_scenarios(
    data: InputData,
    scenarios: dict[str, dict],
    names: Iterable[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, ScenarioResult]]:
    selected = list(names) if names is not None else list(scenarios)
    results: dict[str, ScenarioResult] = {}
    summaries: list[dict] = []
    for name in selected:
        result = solve_scenario(data, scenarios[name])
        results[name] = result
        summaries.append(result.summary)
    return pd.DataFrame(summaries), results
