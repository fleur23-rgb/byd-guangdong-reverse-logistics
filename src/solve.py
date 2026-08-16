from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pandas as pd
import pyomo.environ as pyo

from .data_loader import InputData
from .model import ModelContext, build_model


@dataclass
class ScenarioResult:
    summary: dict[str, Any]
    costs: pd.DataFrame
    collections: pd.DataFrame
    processing: pd.DataFrame
    flows: pd.DataFrame
    validation: dict[str, Any]


def _value(expr: Any) -> float:
    return float(pyo.value(expr))


def solve_scenario(
    data: InputData, scenario: dict[str, Any], tee: bool = False
) -> ScenarioResult:
    model, context = build_model(data, scenario)
    solver = pyo.SolverFactory("highs")
    solver.options["time_limit"] = float(
        scenario["model"]["time_limit_seconds"]
    )
    solver.options["mip_rel_gap"] = float(scenario["model"]["mip_gap"])

    started = time.perf_counter()
    objective_mode = str(
        scenario["model"].get("objective_mode", "lexicographic")
    )
    if objective_mode == "lexicographic":
        model.total_cost.deactivate()
        model.min_emergency = pyo.Objective(
            expr=model.emergency_total, sense=pyo.minimize
        )
        first_results = solver.solve(model, tee=tee)
        first_termination = str(first_results.solver.termination_condition)
        if first_termination not in {"optimal", "feasible", "maxTimeLimit"}:
            raise RuntimeError(
                f"Scenario {scenario['name']} first stage failed: "
                f"{first_results.solver.status}/{first_termination}"
            )
        minimum_emergency = _value(model.emergency_total)
        model.emergency_optimum = pyo.Constraint(
            expr=model.emergency_total <= minimum_emergency + 1e-6
        )
        model.min_emergency.deactivate()
        model.total_cost.activate()
        results = solver.solve(model, tee=tee)
    elif objective_mode == "cost":
        results = solver.solve(model, tee=tee)
    else:
        raise ValueError(f"Unsupported objective_mode: {objective_mode}")
    elapsed = time.perf_counter() - started
    termination = str(results.solver.termination_condition)
    status = str(results.solver.status)
    if termination not in {"optimal", "feasible", "maxTimeLimit"}:
        raise RuntimeError(
            f"Scenario {scenario['name']} failed: {status}/{termination}"
        )

    option_to_collection = {
        option_id: str(row["collection_id"])
        for option_id, row in context.option_rows.items()
    }
    q_total = sum(context.q.values())
    emergency_total = sum(_value(model.h[i]) for i in model.I)
    normal_total = q_total - emergency_total

    collection_rows: list[dict[str, Any]] = []
    for option_id in model.O:
        if _value(model.y[option_id]) < 0.5:
            continue
        throughput = sum(
            _value(model.x[i, o])
            for i, o in model.X_ARCS
            if o == option_id
        )
        row = context.option_rows[option_id]
        capacity = float(row["capacity_tons"]) * float(
            scenario["collection"]["capacity_factor"]
        )
        collection_rows.append(
            {
                "scenario": scenario["name"],
                "distance_source": context.distance_source,
                "option_id": option_id,
                "collection_id": row["collection_id"],
                "city": row["city"],
                "mode": row["mode"],
                "throughput_tons": throughput,
                "capacity_tons": capacity,
                "utilization": throughput / capacity if capacity else 0.0,
                "lon": row["lon"],
                "lat": row["lat"],
            }
        )
    collections = pd.DataFrame(collection_rows)

    processing_rows: list[dict[str, Any]] = []
    for facility_id in list(model.K) + list(model.L):
        selected = (
            _value(model.u[facility_id])
            if facility_id in model.K
            else _value(model.v[facility_id])
        )
        if selected < 0.5:
            continue
        if facility_id in model.K:
            throughput = sum(
                _value(model.g[o, k])
                for o, k in model.G_ARCS
                if k == facility_id
            )
            capacity = float(
                context.processing_rows[facility_id]["capacity_tons"]
            ) * float(scenario["partner"]["capacity_share"])
        else:
            throughput = sum(
                _value(model.r[o, l])
                for o, l in model.R_ARCS
                if l == facility_id
            )
            if facility_id == "P01":
                capacity = float(
                    context.processing_rows[facility_id]["capacity_tons"]
                ) * float(scenario["p01"]["availability"])
                capacity += sum(
                    context.expansion_capacity[n] * _value(model.e[n])
                    for n in model.N
                )
            else:
                capacity = float(
                    context.processing_rows[facility_id]["capacity_tons"]
                ) * float(scenario["partner"]["capacity_share"])
        row = context.processing_rows[facility_id]
        processing_rows.append(
            {
                "scenario": scenario["name"],
                "distance_source": context.distance_source,
                "facility_id": facility_id,
                "name": row["name"],
                "type": row["type"],
                "city": row["city"],
                "existing": int(row["existing"]),
                "throughput_tons": throughput,
                "capacity_tons": capacity,
                "utilization": throughput / capacity if capacity else 0.0,
                "lon": row["lon"],
                "lat": row["lat"],
            }
        )
    processing = pd.DataFrame(processing_rows)

    flow_rows: list[dict[str, Any]] = []
    first_tonne_km = 0.0
    second_tonne_km = 0.0
    for i, option_id in model.X_ARCS:
        amount = _value(model.x[i, option_id])
        if amount <= 1e-7:
            continue
        collection_id = option_to_collection[option_id]
        distance = context.source_collection_distance[(i, collection_id)]
        first_tonne_km += amount * distance
        flow_rows.append(
            {
                "scenario": scenario["name"],
                "distance_source": context.distance_source,
                "stage": "source_collection",
                "origin_id": i,
                "destination_id": option_id,
                "destination_physical_id": collection_id,
                "flow_tons": amount,
                "distance_km": distance,
                "tonne_km": amount * distance,
            }
        )
    for option_id, k in model.G_ARCS:
        amount = _value(model.g[option_id, k])
        if amount <= 1e-7:
            continue
        collection_id = option_to_collection[option_id]
        distance = context.collection_echelon_distance[(collection_id, k)]
        second_tonne_km += amount * distance
        flow_rows.append(
            {
                "scenario": scenario["name"],
                "distance_source": context.distance_source,
                "stage": "collection_echelon",
                "origin_id": option_id,
                "destination_id": k,
                "destination_physical_id": k,
                "flow_tons": amount,
                "distance_km": distance,
                "tonne_km": amount * distance,
            }
        )
    for option_id, l in model.R_ARCS:
        amount = _value(model.r[option_id, l])
        if amount <= 1e-7:
            continue
        collection_id = option_to_collection[option_id]
        distance = context.collection_recycling_distance[(collection_id, l)]
        second_tonne_km += amount * distance
        flow_rows.append(
            {
                "scenario": scenario["name"],
                "distance_source": context.distance_source,
                "stage": "collection_recycling",
                "origin_id": option_id,
                "destination_id": l,
                "destination_physical_id": l,
                "flow_tons": amount,
                "distance_km": distance,
                "tonne_km": amount * distance,
            }
        )
    for i in model.I:
        amount = _value(model.h[i])
        if amount <= 1e-7:
            continue
        flow_rows.append(
            {
                "scenario": scenario["name"],
                "distance_source": context.distance_source,
                "stage": "emergency_outsource",
                "origin_id": i,
                "destination_id": "OUTSOURCE",
                "destination_physical_id": "OUTSOURCE",
                "flow_tons": amount,
                "distance_km": None,
                "tonne_km": None,
            }
        )
    flows = pd.DataFrame(flow_rows)

    radius_by_stage = {
        "source_collection": float(scenario["service_radius"]["source_collection"]),
        "collection_echelon": float(
            scenario["service_radius"]["collection_echelon"]
        ),
        "collection_recycling": float(
            scenario["service_radius"]["collection_recycling"]
        ),
    }
    radius_excesses = [
        float(row.distance_km) - radius_by_stage[row.stage]
        for row in flows.itertuples()
        if row.stage in radius_by_stage
        and bool(scenario["model"]["use_service_radius"])
    ]
    max_radius_excess = max(radius_excesses, default=0.0)

    cost_items = {
        "fixed_collection": _value(model.cost_fixed_collection),
        "fixed_processing": _value(model.cost_fixed_processing),
        "variable_collection": _value(model.cost_variable_collection),
        "variable_processing": _value(model.cost_variable_processing),
        "transport": _value(model.cost_transport),
        "expansion": _value(model.cost_expansion),
        "emergency": _value(model.cost_emergency),
    }
    objective = _value(model.total_cost)
    costs = pd.DataFrame(
        [
            {
                "scenario": scenario["name"],
                "distance_source": context.distance_source,
                "cost_item": item,
                "cost_yuan": amount,
                "share": amount / objective if objective else 0.0,
            }
            for item, amount in cost_items.items()
        ]
    )

    source_residuals = []
    for i in model.I:
        allocated = sum(
            _value(model.x[ii, o])
            for ii, o in model.X_ARCS
            if ii == i
        ) + _value(model.h[i])
        source_residuals.append(context.q[i] - allocated)
    collection_residuals = []
    split_residuals = []
    beta = float(scenario["reuse_share"])
    reuse_total = 0.0
    recycle_total = 0.0
    incoming_total = 0.0
    for option_id in model.O:
        incoming = sum(
            _value(model.x[i, o])
            for i, o in model.X_ARCS
            if o == option_id
        )
        reuse = sum(
            _value(model.g[o, k])
            for o, k in model.G_ARCS
            if o == option_id
        )
        recycle = sum(
            _value(model.r[o, l])
            for o, l in model.R_ARCS
            if o == option_id
        )
        collection_residuals.append(incoming - reuse - recycle)
        incoming_total += incoming
        reuse_total += reuse
        recycle_total += recycle
        if str(scenario["model"].get("reuse_split_scope", "network")) == "node":
            split_residuals.extend(
                [reuse - beta * incoming, recycle - (1 - beta) * incoming]
            )
    if str(scenario["model"].get("reuse_split_scope", "network")) == "network":
        split_residuals.extend(
            [
                reuse_total - beta * incoming_total,
                recycle_total - (1 - beta) * incoming_total,
            ]
        )

    validation = {
        "source_balance_max_abs": max(map(abs, source_residuals), default=0.0),
        "collection_balance_max_abs": max(
            map(abs, collection_residuals), default=0.0
        ),
        "split_balance_max_abs": max(map(abs, split_residuals), default=0.0),
        "objective_reconciliation_abs": abs(objective - sum(cost_items.values())),
        "emergency_within_cap": emergency_total
        <= float(scenario["emergency"]["max_share"]) * q_total + 1e-6,
        "ordinary_unmet_tons": 0.0,
        "positive_flows_within_radius": max_radius_excess <= 1e-6,
        "max_positive_flow_radius_excess_km": max(0.0, max_radius_excess),
    }
    validation["valid"] = (
        validation["source_balance_max_abs"] <= 1e-5
        and validation["collection_balance_max_abs"] <= 1e-5
        and validation["split_balance_max_abs"] <= 1e-5
        and validation["objective_reconciliation_abs"] <= 1e-3
        and validation["emergency_within_cap"]
        and validation["positive_flows_within_radius"]
    )

    self_count = (
        int((collections["mode"] == "self_build").sum())
        if not collections.empty
        else 0
    )
    entrusted_count = (
        int((collections["mode"] == "entrusted").sum())
        if not collections.empty
        else 0
    )
    expansion_level = next(
        (n for n in model.N if _value(model.e[n]) > 0.5), ""
    )
    summary = {
        "scenario": scenario["name"],
        "distance_source": context.distance_source,
        "spatial_weight_scheme": str(
            scenario.get("spatial_weight_scheme", "s3")
        ),
        "road_distance_factor": float(
            scenario.get("road_distance_factor", 1.0)
        ),
        "reuse_split_scope": str(
            scenario["model"].get("reuse_split_scope", "network")
        ),
        "objective_mode": objective_mode,
        "solver_status": status,
        "termination_condition": termination,
        "solve_seconds": elapsed,
        "potential_retired_tons": sum(float(v) for v in context.q.values())
        / float(scenario["capture_rate"])
        if float(scenario["capture_rate"])
        else sum(
            float(v) * float(scenario["demand_scale"])
            for v in data.regions["retired_battery_tons"]
        ),
        "capture_rate": float(scenario["capture_rate"]),
        "network_intake_tons": q_total,
        "reuse_share": beta,
        "reuse_tons": q_total * beta,
        "recycle_tons": q_total * (1 - beta),
        "normal_network_reuse_tons": reuse_total,
        "normal_network_recycle_tons": recycle_total,
        "emergency_tons": emergency_total,
        "emergency_share": emergency_total / q_total if q_total else 0.0,
        "total_cost_yuan": objective,
        "unit_cost_yuan_per_intake_ton": objective / q_total if q_total else 0.0,
        "collection_count": len(collections),
        "self_build_count": self_count,
        "entrusted_count": entrusted_count,
        "echelon_count": (
            int((processing["type"] == "echelon").sum())
            if not processing.empty
            else 0
        ),
        "recycling_count": (
            int((processing["type"] == "recycling").sum())
            if not processing.empty
            else 0
        ),
        "p01_selected": bool(
            not processing.empty
            and (processing["facility_id"] == "P01").any()
        ),
        "p01_expansion_level": expansion_level,
        "first_stage_avg_km": first_tonne_km / normal_total
        if normal_total
        else 0.0,
        "second_stage_avg_km": second_tonne_km / normal_total
        if normal_total
        else 0.0,
        "total_tonne_km": first_tonne_km + second_tonne_km,
        "allowed_source_collection_arcs": context.allowed_arc_counts[
            "source_collection"
        ],
        "allowed_collection_echelon_arcs": context.allowed_arc_counts[
            "collection_echelon"
        ],
        "allowed_collection_recycling_arcs": context.allowed_arc_counts[
            "collection_recycling"
        ],
        "allowed_arc_count": sum(context.allowed_arc_counts.values()),
        "binary_variable_count": sum(
            1
            for var in model.component_data_objects(pyo.Var)
            if var.is_binary()
        ),
        "continuous_variable_count": sum(
            1
            for var in model.component_data_objects(pyo.Var)
            if not var.is_binary()
        ),
        "constraint_count": sum(
            1 for _ in model.component_data_objects(pyo.Constraint, active=True)
        ),
        "validation_passed": validation["valid"],
    }
    return ScenarioResult(
        summary=summary,
        costs=costs,
        collections=collections,
        processing=processing,
        flows=flows,
        validation=validation,
    )
