from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import pyomo.environ as pyo

from .data_loader import InputData


@dataclass(frozen=True)
class ModelContext:
    data: InputData
    scenario: dict[str, Any]
    q: dict[str, float]
    option_rows: dict[str, dict[str, Any]]
    processing_rows: dict[str, dict[str, Any]]
    source_collection_distance: dict[tuple[str, str], float]
    collection_echelon_distance: dict[tuple[str, str], float]
    collection_recycling_distance: dict[tuple[str, str], float]
    distance_source: str
    allowed_arc_counts: dict[str, int]
    expansion_capacity: dict[str, float]
    expansion_cost: dict[str, float]


def _records_by(df: pd.DataFrame, key: str) -> dict[str, dict[str, Any]]:
    return {
        str(row[key]): row.to_dict()
        for _, row in df.iterrows()
    }


def build_model(
    data: InputData, scenario: dict[str, Any]
) -> tuple[pyo.ConcreteModel, ModelContext]:
    regions = data.regions.copy()
    options = data.collection_options.copy()
    processing = data.processing_facilities.copy()
    arcs = data.arcs.copy()

    demand_scale = float(scenario["demand_scale"])
    capture_rate = float(scenario["capture_rate"])
    beta = float(scenario["reuse_share"])
    spatial_scheme = str(scenario.get("spatial_weight_scheme", "s3")).lower()
    distance_source = str(scenario.get("distance_source", "proxy")).lower()
    if distance_source not in {"proxy", "osrm"}:
        raise ValueError(f"Unsupported distance_source: {distance_source}")
    road_distance_factor = float(scenario.get("road_distance_factor", 1.0))
    if distance_source == "osrm" and abs(road_distance_factor - 1.0) > 1e-12:
        raise ValueError("road_distance_factor may only be used with proxy distance")
    distance_column = f"{distance_source}_km"
    if distance_column not in arcs.columns:
        raise ValueError(f"Missing distance column: {distance_column}")
    distance_factor = road_distance_factor if distance_source == "proxy" else 1.0
    demand_column = f"retired_battery_tons_{spatial_scheme}"
    if demand_column not in regions.columns:
        demand_column = "retired_battery_tons"
    q = {
        str(row["region_id"]): float(row[demand_column])
        * demand_scale
        * capture_rate
        for _, row in regions.iterrows()
    }

    option_rows = _records_by(options, "option_id")
    processing_rows = _records_by(processing, "facility_id")
    option_to_collection = {
        option_id: str(row["collection_id"])
        for option_id, row in option_rows.items()
    }

    echelon = processing[processing["type"] == "echelon"]["facility_id"].astype(str)
    recycling = processing[processing["type"] == "recycling"][
        "facility_id"
    ].astype(str)
    collection_ids = options["collection_id"].astype(str).unique().tolist()
    option_ids = options["option_id"].astype(str).tolist()
    region_ids = regions["region_id"].astype(str).tolist()
    echelon_ids = echelon.tolist()
    recycling_ids = recycling.tolist()

    sc_arcs = arcs[
        (arcs["origin_type"] == "source")
        & (arcs["destination_type"] == "collection")
    ]
    ce_arcs = arcs[
        (arcs["origin_type"] == "collection")
        & (arcs["destination_type"] == "echelon")
    ]
    cr_arcs = arcs[
        (arcs["origin_type"] == "collection")
        & (arcs["destination_type"] == "recycling")
    ]

    sc_distance = {
        (str(row.origin_id), str(row.destination_id)):
        float(getattr(row, distance_column)) * distance_factor
        for row in sc_arcs.itertuples()
    }
    ce_distance = {
        (str(row.origin_id), str(row.destination_id)):
        float(getattr(row, distance_column)) * distance_factor
        for row in ce_arcs.itertuples()
    }
    cr_distance = {
        (str(row.origin_id), str(row.destination_id)):
        float(getattr(row, distance_column)) * distance_factor
        for row in cr_arcs.itertuples()
    }

    use_radius = bool(scenario["model"]["use_service_radius"])
    radius = scenario["service_radius"]
    x_arcs = [
        (i, option_id)
        for i in region_ids
        for option_id in option_ids
        if (i, option_to_collection[option_id]) in sc_distance
        and (
            not use_radius
            or sc_distance[(i, option_to_collection[option_id])]
            <= float(radius["source_collection"])
        )
    ]
    g_arcs = [
        (option_id, k)
        for option_id in option_ids
        for k in echelon_ids
        if (option_to_collection[option_id], k) in ce_distance
        and (
            not use_radius
            or ce_distance[(option_to_collection[option_id], k)]
            <= float(radius["collection_echelon"])
        )
    ]
    r_arcs = [
        (option_id, l)
        for option_id in option_ids
        for l in recycling_ids
        if (option_to_collection[option_id], l) in cr_distance
        and (
            not use_radius
            or cr_distance[(option_to_collection[option_id], l)]
            <= float(radius["collection_recycling"])
        )
    ]
    allowed_arc_counts = {
        "source_collection": len(
            {(i, option_to_collection[o]) for i, o in x_arcs}
        ),
        "collection_echelon": len(
            {(option_to_collection[o], k) for o, k in g_arcs}
        ),
        "collection_recycling": len(
            {(option_to_collection[o], l) for o, l in r_arcs}
        ),
    }

    annual_cost_per_capacity_ton = 3904.65 * (0.14902948869707533 + 0.04)
    expansion_capacity = {"E2000": 2000.0, "E5000": 5000.0}
    expansion_cost = {
        level: capacity
        * annual_cost_per_capacity_ton
        * float(scenario["p01"]["expansion_cost_factor"])
        for level, capacity in expansion_capacity.items()
    }

    m = pyo.ConcreteModel(name=f"BYD_GD_{scenario['name']}")
    m.I = pyo.Set(initialize=region_ids)
    m.C = pyo.Set(initialize=collection_ids)
    m.O = pyo.Set(initialize=option_ids)
    m.K = pyo.Set(initialize=echelon_ids)
    m.L = pyo.Set(initialize=recycling_ids)
    m.X_ARCS = pyo.Set(dimen=2, initialize=x_arcs)
    m.G_ARCS = pyo.Set(dimen=2, initialize=g_arcs)
    m.R_ARCS = pyo.Set(dimen=2, initialize=r_arcs)
    m.N = pyo.Set(initialize=list(expansion_capacity))

    m.y = pyo.Var(m.O, domain=pyo.Binary)
    m.u = pyo.Var(m.K, domain=pyo.Binary)
    m.v = pyo.Var(m.L, domain=pyo.Binary)
    m.e = pyo.Var(m.N, domain=pyo.Binary)
    m.x = pyo.Var(m.X_ARCS, domain=pyo.NonNegativeReals)
    m.g = pyo.Var(m.G_ARCS, domain=pyo.NonNegativeReals)
    m.r = pyo.Var(m.R_ARCS, domain=pyo.NonNegativeReals)
    m.h = pyo.Var(m.I, domain=pyo.NonNegativeReals)

    incoming_x = {
        option_id: [(i, o) for i, o in x_arcs if o == option_id]
        for option_id in option_ids
    }
    outgoing_g = {
        option_id: [(o, k) for o, k in g_arcs if o == option_id]
        for option_id in option_ids
    }
    outgoing_r = {
        option_id: [(o, l) for o, l in r_arcs if o == option_id]
        for option_id in option_ids
    }
    source_x = {
        i: [(ii, o) for ii, o in x_arcs if ii == i]
        for i in region_ids
    }
    incoming_g = {
        k: [(o, kk) for o, kk in g_arcs if kk == k]
        for k in echelon_ids
    }
    incoming_r = {
        l: [(o, ll) for o, ll in r_arcs if ll == l]
        for l in recycling_ids
    }

    def source_balance_rule(model: pyo.ConcreteModel, i: str):
        return sum(model.x[arc] for arc in source_x[i]) + model.h[i] == q[i]

    m.source_balance = pyo.Constraint(m.I, rule=source_balance_rule)

    def collection_balance_rule(model: pyo.ConcreteModel, option_id: str):
        return sum(model.x[arc] for arc in incoming_x[option_id]) == (
            sum(model.g[arc] for arc in outgoing_g[option_id])
            + sum(model.r[arc] for arc in outgoing_r[option_id])
        )

    m.collection_balance = pyo.Constraint(m.O, rule=collection_balance_rule)

    reuse_split_scope = str(
        scenario["model"].get("reuse_split_scope", "network")
    )
    if reuse_split_scope == "node":
        def reuse_split_rule(model: pyo.ConcreteModel, option_id: str):
            return sum(model.g[arc] for arc in outgoing_g[option_id]) == beta * sum(
                model.x[arc] for arc in incoming_x[option_id]
            )

        def recycle_split_rule(model: pyo.ConcreteModel, option_id: str):
            return sum(model.r[arc] for arc in outgoing_r[option_id]) == (
                1.0 - beta
            ) * sum(model.x[arc] for arc in incoming_x[option_id])

        m.reuse_split = pyo.Constraint(m.O, rule=reuse_split_rule)
        m.recycle_split = pyo.Constraint(m.O, rule=recycle_split_rule)
    elif reuse_split_scope == "network":
        m.reuse_split = pyo.Constraint(
            expr=sum(m.g[arc] for arc in m.G_ARCS)
            == beta * sum(m.x[arc] for arc in m.X_ARCS)
        )
        m.recycle_split = pyo.Constraint(
            expr=sum(m.r[arc] for arc in m.R_ARCS)
            == (1.0 - beta) * sum(m.x[arc] for arc in m.X_ARCS)
        )
    else:
        raise ValueError(
            f"Unsupported reuse_split_scope: {reuse_split_scope}"
        )

    capacity_factor = float(scenario["collection"]["capacity_factor"])
    use_minimum = bool(scenario["model"]["use_minimum_throughput"])

    def collection_capacity_rule(model: pyo.ConcreteModel, option_id: str):
        capacity = (
            float(option_rows[option_id]["capacity_tons"]) * capacity_factor
        )
        return sum(model.x[arc] for arc in incoming_x[option_id]) <= capacity * model.y[
            option_id
        ]

    m.collection_capacity = pyo.Constraint(m.O, rule=collection_capacity_rule)

    def collection_minimum_rule(model: pyo.ConcreteModel, option_id: str):
        minimum = (
            float(
                scenario["collection"].get(
                    "minimum_throughput_tons",
                    option_rows[option_id]["min_throughput_tons"],
                )
            )
            if use_minimum
            else 0.0
        )
        return sum(model.x[arc] for arc in incoming_x[option_id]) >= minimum * model.y[
            option_id
        ]

    m.collection_minimum = pyo.Constraint(m.O, rule=collection_minimum_rule)

    options_by_collection = {
        collection_id: [
            option_id
            for option_id in option_ids
            if option_to_collection[option_id] == collection_id
        ]
        for collection_id in collection_ids
    }

    def collection_exclusive_rule(model: pyo.ConcreteModel, collection_id: str):
        return (
            sum(model.y[o] for o in options_by_collection[collection_id]) <= 1
        )

    m.collection_exclusive = pyo.Constraint(
        m.C, rule=collection_exclusive_rule
    )

    mode_policy = str(scenario["collection"]["mode_policy"])
    m.mode_policy = pyo.ConstraintList()
    for option_id in option_ids:
        mode = option_rows[option_id]["mode"]
        if mode_policy == "self_only" and mode != "self_build":
            m.mode_policy.add(m.y[option_id] == 0)
        elif mode_policy == "entrusted_only" and mode != "entrusted":
            m.mode_policy.add(m.y[option_id] == 0)

    partner_share = float(scenario["partner"]["capacity_share"])
    partner_minimum_factor = float(
        scenario["partner"].get("minimum_factor", 1.0)
    )

    def echelon_capacity_rule(model: pyo.ConcreteModel, k: str):
        capacity = float(processing_rows[k]["capacity_tons"]) * partner_share
        return sum(model.g[arc] for arc in incoming_g[k]) <= capacity * model.u[k]

    m.echelon_capacity = pyo.Constraint(m.K, rule=echelon_capacity_rule)

    def echelon_minimum_rule(model: pyo.ConcreteModel, k: str):
        minimum = (
            float(processing_rows[k]["min_throughput_tons"]) * partner_share
            * partner_minimum_factor
            if use_minimum
            else 0.0
        )
        return sum(model.g[arc] for arc in incoming_g[k]) >= minimum * model.u[k]

    m.echelon_minimum = pyo.Constraint(m.K, rule=echelon_minimum_rule)

    external_recycling = [l for l in recycling_ids if l != "P01"]

    def external_recycling_capacity_rule(model: pyo.ConcreteModel, l: str):
        capacity = float(processing_rows[l]["capacity_tons"]) * partner_share
        return sum(model.r[arc] for arc in incoming_r[l]) <= capacity * model.v[l]

    m.external_recycling_capacity = pyo.Constraint(
        external_recycling, rule=external_recycling_capacity_rule
    )

    def external_recycling_minimum_rule(model: pyo.ConcreteModel, l: str):
        minimum = (
            float(processing_rows[l]["min_throughput_tons"]) * partner_share
            * partner_minimum_factor
            if use_minimum
            else 0.0
        )
        return sum(model.r[arc] for arc in incoming_r[l]) >= minimum * model.v[l]

    m.external_recycling_minimum = pyo.Constraint(
        external_recycling, rule=external_recycling_minimum_rule
    )

    physical_groups: dict[str, list[str]] = {}
    for facility_id in echelon_ids + external_recycling:
        physical_id = str(processing_rows[facility_id].get("physical_id", facility_id))
        physical_groups.setdefault(physical_id, []).append(facility_id)

    shared_physical_ids = [
        physical_id
        for physical_id, role_ids in physical_groups.items()
        if len(role_ids) > 1
    ]
    m.P_SHARED = pyo.Set(initialize=shared_physical_ids)

    def shared_processing_capacity_rule(
        model: pyo.ConcreteModel, physical_id: str
    ):
        role_ids = physical_groups[physical_id]
        echelon_roles = [role_id for role_id in role_ids if role_id in echelon_ids]
        recycling_roles = [
            role_id for role_id in role_ids if role_id in external_recycling
        ]
        shared_capacity = max(
            float(processing_rows[role_id]["shared_capacity_tons"])
            for role_id in role_ids
        ) * partner_share
        return (
            sum(
                model.g[arc]
                for role_id in echelon_roles
                for arc in incoming_g[role_id]
            )
            + sum(
                model.r[arc]
                for role_id in recycling_roles
                for arc in incoming_r[role_id]
            )
            <= shared_capacity
        )

    m.shared_processing_capacity = pyo.Constraint(
        m.P_SHARED, rule=shared_processing_capacity_rule
    )

    p01_capacity = float(processing_rows["P01"]["capacity_tons"]) * float(
        scenario["p01"]["availability"]
    )
    m.p01_capacity = pyo.Constraint(
        expr=sum(m.r[arc] for arc in incoming_r["P01"])
        <= p01_capacity * m.v["P01"]
        + sum(expansion_capacity[n] * m.e[n] for n in m.N)
    )
    m.p01_expansion_choice = pyo.Constraint(
        expr=sum(m.e[n] for n in m.N) <= m.v["P01"]
    )
    if not bool(scenario["p01"]["expansion_enabled"]):
        for n in m.N:
            m.e[n].fix(0)
    if bool(scenario["p01"]["locked"]):
        m.v["P01"].fix(1)

    counts = scenario["facility_count"]
    m.collection_count_min = pyo.Constraint(
        expr=sum(m.y[o] for o in m.O) >= int(counts["collection_min"])
    )
    m.collection_count_max = pyo.Constraint(
        expr=sum(m.y[o] for o in m.O) <= int(counts["collection_max"])
    )
    m.echelon_count_min = pyo.Constraint(
        expr=sum(m.u[k] for k in m.K) >= int(counts["echelon_min"])
    )
    m.echelon_count_max = pyo.Constraint(
        expr=sum(m.u[k] for k in m.K) <= int(counts["echelon_max"])
    )
    m.recycling_count_min = pyo.Constraint(
        expr=sum(m.v[l] for l in m.L) >= int(counts["recycling_min"])
    )
    m.recycling_count_max = pyo.Constraint(
        expr=sum(m.v[l] for l in m.L) <= int(counts["recycling_max"])
    )

    m.emergency_total = pyo.Expression(expr=sum(m.h[i] for i in m.I))
    m.emergency_cap = pyo.Constraint(
        expr=m.emergency_total
        <= float(scenario["emergency"]["max_share"]) * sum(q.values())
    )

    self_fixed_factor = float(scenario["collection"]["self_fixed_factor"])
    self_unit_factor = float(scenario["collection"]["self_unit_factor"])
    entrusted_fixed_factor = float(
        scenario["collection"]["entrusted_fixed_factor"]
    )
    entrusted_unit_factor = float(
        scenario["collection"]["entrusted_unit_factor"]
    )
    partner_fixed_factor = float(scenario["partner"]["fixed_factor"])
    partner_unit_factor = float(scenario["partner"]["unit_factor"])
    echelon_unit_factor = float(
        scenario["partner"].get("echelon_unit_factor", partner_unit_factor)
    )
    recycling_unit_factor = float(
        scenario["partner"].get("recycling_unit_factor", partner_unit_factor)
    )

    def collection_fixed(option_id: str) -> float:
        row = option_rows[option_id]
        factor = (
            self_fixed_factor
            if row["mode"] == "self_build"
            else entrusted_fixed_factor
        )
        return float(row["fixed_cost_yuan_per_year"]) * factor

    def collection_unit(option_id: str) -> float:
        row = option_rows[option_id]
        factor = (
            self_unit_factor
            if row["mode"] == "self_build"
            else entrusted_unit_factor
        )
        return float(row["unit_processing_cost_yuan_per_ton"]) * factor

    def processing_fixed(facility_id: str) -> float:
        row = processing_rows[facility_id]
        if facility_id == "P01":
            factor = float(scenario["p01"]["fixed_factor"])
        else:
            factor = partner_fixed_factor
        return float(row["fixed_cost_yuan_per_year"]) * factor

    def processing_unit(facility_id: str) -> float:
        row = processing_rows[facility_id]
        if facility_id == "P01":
            factor = float(scenario["p01"]["unit_factor"])
        elif row["type"] == "echelon":
            factor = echelon_unit_factor
        elif row["type"] == "recycling":
            factor = recycling_unit_factor
        else:
            factor = partner_unit_factor
        return float(row["unit_processing_cost_yuan_per_ton"]) * factor

    trans = scenario["transport_cost"]
    m.cost_fixed_collection = pyo.Expression(
        expr=sum(collection_fixed(o) * m.y[o] for o in m.O)
    )
    m.cost_fixed_processing = pyo.Expression(
        expr=sum(processing_fixed(k) * m.u[k] for k in m.K)
        + sum(processing_fixed(l) * m.v[l] for l in m.L)
    )
    m.cost_variable_collection = pyo.Expression(
        expr=sum(collection_unit(o) * m.x[i, o] for i, o in m.X_ARCS)
    )
    m.cost_variable_processing = pyo.Expression(
        expr=sum(processing_unit(k) * m.g[o, k] for o, k in m.G_ARCS)
        + sum(processing_unit(l) * m.r[o, l] for o, l in m.R_ARCS)
    )
    m.cost_transport = pyo.Expression(
        expr=sum(
            float(trans["source_collection"])
            * sc_distance[(i, option_to_collection[o])]
            * m.x[i, o]
            for i, o in m.X_ARCS
        )
        + sum(
            float(trans["collection_echelon"])
            * ce_distance[(option_to_collection[o], k)]
            * m.g[o, k]
            for o, k in m.G_ARCS
        )
        + sum(
            float(trans["collection_recycling"])
            * cr_distance[(option_to_collection[o], l)]
            * m.r[o, l]
            for o, l in m.R_ARCS
        )
    )
    m.cost_expansion = pyo.Expression(
        expr=sum(expansion_cost[n] * m.e[n] for n in m.N)
    )
    m.cost_emergency = pyo.Expression(
        expr=float(scenario["emergency"]["unit_cost"]) * m.emergency_total
    )
    m.total_cost = pyo.Objective(
        expr=m.cost_fixed_collection
        + m.cost_fixed_processing
        + m.cost_variable_collection
        + m.cost_variable_processing
        + m.cost_transport
        + m.cost_expansion
        + m.cost_emergency,
        sense=pyo.minimize,
    )

    context = ModelContext(
        data=data,
        scenario=scenario,
        q=q,
        option_rows=option_rows,
        processing_rows=processing_rows,
        source_collection_distance=sc_distance,
        collection_echelon_distance=ce_distance,
        collection_recycling_distance=cr_distance,
        distance_source=distance_source,
        allowed_arc_counts=allowed_arc_counts,
        expansion_capacity=expansion_capacity,
        expansion_cost=expansion_cost,
    )
    return m, context
