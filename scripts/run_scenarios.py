from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_loader import load_inputs, load_scenarios
from src.reporting import save_results
from src.scenarios import run_scenarios


def main() -> None:
    data = load_inputs(ROOT / "data" / "processed")
    scenarios = load_scenarios(ROOT / "configs")
    summary, results = run_scenarios(data, scenarios)
    save_results(ROOT / "results", summary, results, data)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
