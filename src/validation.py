from __future__ import annotations

from typing import Any

import pandas as pd

from .data_loader import InputData


def validate_inputs(data: InputData) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if data.regions["region_id"].duplicated().any():
        errors.append("Duplicate region_id values")
    if data.collection_options["option_id"].duplicated().any():
        errors.append("Duplicate collection option_id values")
    if data.processing_facilities["facility_id"].duplicated().any():
        errors.append("Duplicate processing facility_id values")
    if data.arcs["arc_id"].duplicated().any():
        errors.append("Duplicate arc_id values")

    required_arc_columns = {"proxy_km", "osrm_km", "osrm_duration_min"}
    missing_arc_columns = required_arc_columns.difference(data.arcs.columns)
    if missing_arc_columns:
        errors.append(
            "Missing distance columns: " + ", ".join(sorted(missing_arc_columns))
        )
    else:
        if data.arcs[list(required_arc_columns)].isna().any().any():
            errors.append("Distance layer contains missing values")
        if (data.arcs[["proxy_km", "osrm_km"]] < 0).any().any():
            errors.append("Distance layer contains negative distances")
        if (data.arcs["osrm_duration_min"] < 0).any():
            errors.append("OSRM layer contains negative durations")

    region_ids = set(data.regions["region_id"])
    collection_ids = set(data.collection_options["collection_id"])
    processing_ids = set(data.processing_facilities["facility_id"])

    sc = data.arcs[data.arcs["origin_type"] == "source"]
    cp = data.arcs[data.arcs["origin_type"] == "collection"]
    if not set(sc["origin_id"]).issubset(region_ids):
        errors.append("Unknown source endpoint in source-collection arcs")
    if not set(sc["destination_id"]).issubset(collection_ids):
        errors.append("Unknown collection endpoint in source-collection arcs")
    if not set(cp["origin_id"]).issubset(collection_ids):
        errors.append("Unknown collection endpoint in processing arcs")
    if not set(cp["destination_id"]).issubset(processing_ids):
        errors.append("Unknown processing endpoint in processing arcs")

    expected_total = float(data.metadata["base_retired_battery_tons"])
    actual_total = float(data.regions["retired_battery_tons"].sum())
    if abs(expected_total - actual_total) > 1e-4:
        errors.append(
            f"Regional total {actual_total:.6f} differs from metadata {expected_total:.6f}"
        )

    for scheme in ("s1", "s2", "s3"):
        weight_column = f"spatial_weight_{scheme}"
        demand_column = f"retired_battery_tons_{scheme}"
        if weight_column not in data.regions or demand_column not in data.regions:
            errors.append(f"Missing spatial scenario columns for {scheme}")
            continue
        if abs(float(data.regions[weight_column].sum()) - 1.0) > 1e-6:
            errors.append(f"Spatial weights for {scheme} do not sum to one")
        if abs(float(data.regions[demand_column].sum()) - expected_total) > 1e-3:
            errors.append(f"Spatial demand for {scheme} differs from base total")

    required_processing_columns = {"physical_id", "shared_capacity_tons"}
    missing_processing_columns = required_processing_columns.difference(
        data.processing_facilities.columns
    )
    if missing_processing_columns:
        errors.append(
            "Missing processing enterprise columns: "
            + ", ".join(sorted(missing_processing_columns))
        )

    counts = (
        data.arcs.groupby(["origin_type", "destination_type"])
        .size()
        .to_dict()
    )
    expected_counts = {
        ("source", "collection"): 441,
        ("collection", "echelon"): 357,
        ("collection", "recycling"): 147,
    }
    if counts != expected_counts:
        warnings.append(f"Arc counts differ from V2.0 interface: {counts}")

    allowed_counts: dict[str, int] = {}
    changed_count = 0
    if not missing_arc_columns:
        radii = {
            ("source", "collection"): 150.0,
            ("collection", "echelon"): 300.0,
            ("collection", "recycling"): 400.0,
        }
        allowed_masks = {}
        for source in ("proxy", "osrm"):
            mask = pd.Series(False, index=data.arcs.index)
            for (origin_type, destination_type), radius in radii.items():
                arc_type = (
                    data.arcs["origin_type"].eq(origin_type)
                    & data.arcs["destination_type"].eq(destination_type)
                )
                mask |= arc_type & data.arcs[f"{source}_km"].le(radius)
            allowed_masks[source] = mask
            allowed_counts[source] = int(mask.sum())
        changed_count = int((allowed_masks["proxy"] != allowed_masks["osrm"]).sum())
        if allowed_counts != {"proxy": 465, "osrm": 466}:
            errors.append(f"Unexpected baseline allowed-arc counts: {allowed_counts}")
        if changed_count != 7:
            errors.append(
                f"Unexpected proxy/OSRM allowed-state change count: {changed_count}"
            )

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "region_count": len(data.regions),
        "collection_location_count": data.collection_options[
            "collection_id"
        ].nunique(),
        "processing_role_count": len(data.processing_facilities),
        "arc_count": len(data.arcs),
        "baseline_allowed_arc_counts": allowed_counts,
        "distance_allowed_state_changes": changed_count,
        "base_retired_battery_tons": actual_total,
    }


def maximum_absolute_residual(values: pd.Series) -> float:
    return float(values.abs().max()) if not values.empty else 0.0
