from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
PROCESSED = ROOT / "data" / "processed"
OUTPUT = ROOT / "web" / "public" / "data" / "model-results.json"


def records(path: Path) -> list[dict]:
    frame = pd.read_csv(path)
    return json.loads(frame.to_json(orient="records", force_ascii=False))


def main() -> None:
    payload = {
        "summary": records(RESULTS / "scenario_summary.csv"),
        "costs": records(RESULTS / "scenario_costs.csv"),
        "collections": records(RESULTS / "scenario_collections.csv"),
        "processing": records(RESULTS / "scenario_processing.csv"),
        "flows": records(RESULTS / "scenario_flows.csv"),
        "regions": records(PROCESSED / "regions.csv"),
        "generated_from": "Public-data research estimates and scenario assumptions; Guangdong is the bundled demonstration case.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
