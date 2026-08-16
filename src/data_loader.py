from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


@dataclass(frozen=True)
class InputData:
    regions: pd.DataFrame
    collection_options: pd.DataFrame
    processing_facilities: pd.DataFrame
    arcs: pd.DataFrame
    metadata: dict[str, Any]


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_inputs(processed_dir: Path) -> InputData:
    return InputData(
        regions=pd.read_csv(processed_dir / "regions.csv"),
        collection_options=pd.read_csv(processed_dir / "collection_options.csv"),
        processing_facilities=pd.read_csv(
            processed_dir / "processing_facilities.csv"
        ),
        arcs=pd.read_csv(processed_dir / "arcs.csv"),
        metadata=yaml.safe_load((processed_dir / "metadata.yaml").read_text("utf-8")),
    )


def load_scenarios(config_dir: Path) -> dict[str, dict[str, Any]]:
    baseline = yaml.safe_load((config_dir / "baseline.yaml").read_text("utf-8"))
    overrides = yaml.safe_load((config_dir / "scenarios.yaml").read_text("utf-8"))
    scenarios: dict[str, dict[str, Any]] = {}
    for name, override in overrides["scenarios"].items():
        scenario = deep_merge(baseline, override or {})
        scenario["name"] = name
        scenarios[name] = scenario
    return scenarios
