from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workbook",
        type=Path,
        help="Optional V2.1 workbook path. Omit to use committed processed CSV files.",
    )
    return parser.parse_args()


def run(script: str, *args: str) -> None:
    subprocess.run(
        [PYTHON, str(ROOT / "scripts" / script), *args],
        cwd=ROOT,
        check=True,
    )


def main() -> None:
    args = parse_args()
    if args.workbook is not None:
        run("build_inputs.py", "--workbook", str(args.workbook))
    elif not (ROOT / "data" / "processed" / "regions.csv").exists():
        raise FileNotFoundError(
            "Processed data are missing. Supply --workbook to rebuild them."
        )
    run("run_scenarios.py")


if __name__ == "__main__":
    main()
