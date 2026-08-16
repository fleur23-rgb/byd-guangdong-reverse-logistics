# BYD Guangdong Reverse Logistics

This repository contains a public-data-driven mixed-integer linear programming
model for a BYD Guangdong retired traction-battery reverse logistics case.
It follows RELOG's general network-design idea while implementing Chinese
business rules in Python, Pyomo, and HiGHS.

## Scope

- 2025 single-period case
- 21 Guangdong city service-access and source-aggregation regions
- Self-built or entrusted regional collection, testing, and consolidation options
- External echelon-use and recycling partners
- Existing Shanwei P01 recycling facility
- Aggregate exogenous route split for normal-network flows, with a node-level diagnostic alternative
- Shared capacity across functional nodes belonging to the same physical firm
- Lexicographic optimization: minimize emergency outsourcing first, then cost
- Service radii, allowed arcs, fixed scenario capacity, and minimum throughput

The included values are public-data estimates, spatial proxies, literature
calibrations, and scenario assumptions. They are not BYD operational records.

## Reproduce

The repository contains the processed V2.1 case inputs, so the original Excel
workbook is not required for ordinary reproduction.

### macOS and Linux

Create a Python 3.11+ virtual environment and install the pinned dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-lock.txt
```

Run the full scenario matrix from the committed processed inputs:

```bash
python scripts/reproduce_results.py
```

Run tests:

```bash
python -m pytest -q
```

### Windows

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-lock.txt
python scripts/reproduce_results.py
python -m pytest -q
```

### Rebuild inputs from the workbook

To rebuild `data/processed/` from the research workbook, pass its location
explicitly. Quoting the path is recommended when it contains spaces or Chinese
characters:

```bash
python scripts/reproduce_results.py --workbook "/path/to/广东省动力电池闭环供应链论文数据集_V2.1.xlsx"
```

Alternatively, place the workbook at
`data/raw/广东省动力电池闭环供应链论文数据集_V2.1.xlsx` and run:

```bash
python scripts/build_inputs.py
python scripts/reproduce_results.py
```

Outputs are written to `results/`. The baseline uses OSRM `driving/car` road
distances; the proxy-distance baseline is retained as a diagnostic comparison.

## Current verified release

- 49 official OSRM scenarios plus 1 proxy-distance comparison scenario
- 23 automated tests covering inputs, flow balance, route split, allowed arcs,
  facility capacity, shared physical-firm capacity, distance handling, costs,
  emergency outsourcing, and proxy/OSRM consistency
- Python, Pyomo, and the HiGHS MILP solver through `highspy`

The values are research estimates and scenario assumptions, not BYD operational
records. See `data/README.md` for the data scope.
