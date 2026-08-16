from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_loader import load_inputs, load_scenarios
from src.solve import solve_scenario


def main() -> None:
    data = load_inputs(ROOT / "data" / "processed")
    scenario = load_scenarios(ROOT / "configs")["baseline"]
    result = solve_scenario(data, scenario)
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
