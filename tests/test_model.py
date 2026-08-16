from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pyomo.environ as pyo
import pytest

from src.data_loader import load_inputs, load_scenarios
from src.model import build_model
from src.solve import solve_scenario
from src.validation import validate_inputs


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def data():
    return load_inputs(ROOT / "data" / "processed")


@pytest.fixture(scope="module")
def scenarios():
    return load_scenarios(ROOT / "configs")


@pytest.fixture(scope="module")
def baseline_result(data, scenarios):
    return solve_scenario(data, scenarios["baseline"])


def test_processed_inputs() -> None:
    data = load_inputs(ROOT / "data" / "processed")
    report = validate_inputs(data)
    assert report["valid"], report["errors"]
    assert report["region_count"] == 21
    assert report["collection_location_count"] == 21
    assert report["processing_role_count"] == 24
    assert report["arc_count"] == 945


def test_spatial_weights_preserve_total(data) -> None:
    for scheme in ("s1", "s2", "s3"):
        assert data.regions[f"spatial_weight_{scheme}"].sum() == pytest.approx(1.0)
        assert data.regions[f"retired_battery_tons_{scheme}"].sum() == pytest.approx(
            data.metadata["base_retired_battery_tons"], abs=1e-3
        )


def test_baseline_is_optimal(baseline_result) -> None:
    assert baseline_result.summary["termination_condition"] == "optimal"
    assert baseline_result.summary["network_intake_tons"] > 0


def test_baseline_source_and_collection_balance(baseline_result) -> None:
    assert baseline_result.validation["source_balance_max_abs"] <= 1e-5
    assert baseline_result.validation["collection_balance_max_abs"] <= 1e-5


def test_baseline_normal_network_split_balance(baseline_result) -> None:
    assert baseline_result.summary["reuse_split_scope"] == "network"
    assert baseline_result.validation["split_balance_max_abs"] <= 1e-5


def test_baseline_cost_reconciliation(baseline_result) -> None:
    assert baseline_result.validation["objective_reconciliation_abs"] <= 1e-3
    assert baseline_result.costs["share"].sum() == pytest.approx(1.0)


def test_baseline_emergency_cap(baseline_result) -> None:
    assert baseline_result.validation["emergency_within_cap"]
    assert 0 <= baseline_result.summary["emergency_share"] <= 0.20


def test_collection_activation_capacity_and_minimum(baseline_result) -> None:
    rows = baseline_result.collections
    assert (rows["throughput_tons"] <= rows["capacity_tons"] + 1e-6).all()
    assert (rows["throughput_tons"] >= 300 - 1e-6).all()
    assert rows.groupby("collection_id").size().max() == 1


def test_processing_activation_capacity(baseline_result) -> None:
    rows = baseline_result.processing
    assert (rows["throughput_tons"] <= rows["capacity_tons"] + 1e-6).all()


def test_positive_flows_use_allowed_arcs(data, baseline_result) -> None:
    allowed = set(
        zip(
            data.arcs["origin_id"].astype(str),
            data.arcs["destination_id"].astype(str),
        )
    )
    option_to_collection = (
        data.collection_options.set_index("option_id")["collection_id"]
        .astype(str)
        .to_dict()
    )
    for row in baseline_result.flows.itertuples():
        if row.stage == "emergency_outsource":
            continue
        origin = (
            option_to_collection[row.origin_id]
            if row.stage.startswith("collection_")
            else row.origin_id
        )
        destination = (
            option_to_collection[row.destination_id]
            if row.stage == "source_collection"
            else row.destination_id
        )
        assert (origin, destination) in allowed


def test_shared_physical_enterprise_capacity_is_present(data, scenarios) -> None:
    model, _ = build_model(data, scenarios["baseline"])
    assert len(model.P_SHARED) == 3
    assert len(model.shared_processing_capacity) == 3


def test_legacy_node_split_is_not_cheaper(data, scenarios, baseline_result) -> None:
    legacy = solve_scenario(data, scenarios["split_node_legacy"])
    assert legacy.validation["valid"]
    assert legacy.summary["total_cost_yuan"] >= (
        baseline_result.summary["total_cost_yuan"] - 1e-3
    )


def test_lexicographic_emergency_amount_is_price_invariant(data, scenarios) -> None:
    low = solve_scenario(data, scenarios["emergency_cost_50"])
    high = solve_scenario(data, scenarios["emergency_cost_125"])
    assert low.summary["emergency_tons"] == pytest.approx(
        high.summary["emergency_tons"], abs=1e-5
    )


def test_no_emergency_is_infeasible_under_baseline_minimum(data, scenarios) -> None:
    scenario = deepcopy(scenarios["baseline"])
    scenario["emergency"]["max_share"] = 0.0
    model, _ = build_model(data, scenario)
    result = pyo.SolverFactory("highs").solve(model, load_solutions=False)
    assert str(result.solver.termination_condition) == "infeasible"


def test_discounted_expansion_only_enters_stress_case(data, scenarios) -> None:
    discounted = solve_scenario(data, scenarios["p01_stress_expand"])
    full = solve_scenario(data, scenarios["p01_stress_expand_full"])
    assert discounted.summary["p01_expansion_level"] == "E2000"
    assert full.summary["p01_expansion_level"] == ""


def test_road_distance_factor_scales_distances(data, scenarios) -> None:
    _, base_context = build_model(data, scenarios["proxy_baseline"])
    _, low_context = build_model(data, scenarios["road_factor_low"])
    arc = next(iter(base_context.source_collection_distance))
    assert low_context.source_collection_distance[arc] == pytest.approx(
        base_context.source_collection_distance[arc] * 11 / 12
    )


def test_processing_cost_scenarios_preserve_feasibility(data, scenarios) -> None:
    low = solve_scenario(data, scenarios["processing_cost_low"])
    high = solve_scenario(data, scenarios["processing_cost_high"])
    assert low.validation["valid"]
    assert high.validation["valid"]
    assert low.summary["total_cost_yuan"] < high.summary["total_cost_yuan"]


def test_relaxed_facility_minimum_counts_are_nonbinding(data, scenarios) -> None:
    base = solve_scenario(data, scenarios["baseline"])
    relaxed = solve_scenario(data, scenarios["facility_count_min_relaxed"])
    assert relaxed.validation["valid"]
    assert relaxed.summary["emergency_tons"] == pytest.approx(
        base.summary["emergency_tons"], abs=1e-5
    )


def test_osrm_arc_layer_is_complete(data) -> None:
    required = {"proxy_km", "osrm_km", "osrm_duration_min"}
    assert required.issubset(data.arcs.columns)
    assert len(data.arcs) == 945
    assert data.arcs["arc_id"].is_unique
    assert data.arcs[list(required)].notna().all().all()
    assert (data.arcs[["proxy_km", "osrm_km"]] >= 0).all().all()
    assert (data.arcs["osrm_duration_min"] >= 0).all()


def test_distance_source_switches_distance_values(data, scenarios) -> None:
    _, osrm_context = build_model(data, scenarios["baseline"])
    _, proxy_context = build_model(data, scenarios["proxy_baseline"])
    arc = ("GD01", "C02")
    assert osrm_context.distance_source == "osrm"
    assert proxy_context.distance_source == "proxy"
    assert osrm_context.source_collection_distance[arc] == pytest.approx(141.4812)
    assert proxy_context.source_collection_distance[arc] == pytest.approx(
        125.09932920710673
    )


def test_osrm_allowed_arcs_are_recomputed(data, scenarios) -> None:
    _, osrm_context = build_model(data, scenarios["baseline"])
    _, proxy_context = build_model(data, scenarios["proxy_baseline"])
    assert proxy_context.allowed_arc_counts == {
        "source_collection": 115,
        "collection_echelon": 240,
        "collection_recycling": 110,
    }
    assert osrm_context.allowed_arc_counts == {
        "source_collection": 113,
        "collection_echelon": 241,
        "collection_recycling": 112,
    }


def test_osrm_positive_flows_respect_service_radii(
    baseline_result, scenarios
) -> None:
    assert baseline_result.summary["distance_source"] == "osrm"
    assert baseline_result.validation["positive_flows_within_radius"]
    radii = scenarios["baseline"]["service_radius"]
    for row in baseline_result.flows.itertuples():
        if row.stage == "emergency_outsource":
            continue
        assert row.distance_km <= float(radii[row.stage]) + 1e-6


def test_proxy_baseline_reproduces_committed_reference(data, scenarios) -> None:
    result = solve_scenario(data, scenarios["proxy_baseline"])
    assert result.summary["distance_source"] == "proxy"
    assert result.summary["emergency_tons"] == pytest.approx(
        267.9360595283843, abs=1e-5
    )
    assert result.summary["total_cost_yuan"] == pytest.approx(
        65754214.29524426, abs=1e-2
    )
    assert set(result.collections["city"]) == {"深圳", "梅州", "惠州", "肇庆"}
