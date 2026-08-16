from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = (
    ROOT / "data" / "raw" / "广东省动力电池闭环供应链论文数据集_V2.1.xlsx"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "processed",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.workbook.exists():
        raise FileNotFoundError(
            f"Workbook not found: {args.workbook}. "
            "Pass its location with --workbook or use the committed processed CSV files."
        )
    args.output.mkdir(parents=True, exist_ok=True)

    regions = pd.read_excel(args.workbook, sheet_name="regions_input", header=2)
    spatial = pd.read_excel(
        args.workbook, sheet_name="广东21市模板", header=3
    )
    facilities = pd.read_excel(
        args.workbook, sheet_name="facilities_input", header=3
    )
    arcs = pd.read_excel(args.workbook, sheet_name="network_arcs_input", header=3)
    osrm_arcs = pd.read_excel(args.workbook, sheet_name="道路距离_OSRM", header=3)

    regions = regions.dropna(subset=["region_id"]).copy()
    spatial = spatial.dropna(subset=["城市ID"]).copy()
    facilities = facilities.dropna(subset=["facility_id"]).copy()
    arcs = arcs.dropna(subset=["arc_id"]).copy()
    osrm_arcs = osrm_arcs.dropna(subset=["arc_id"]).copy()

    osrm_columns = [
        "arc_id",
        "origin_id",
        "origin_type",
        "destination_id",
        "destination_type",
        "proxy_km",
        "osrm_km",
        "osrm_duration_min",
        "route_profile",
        "query_date",
        "quality_flag",
    ]
    arcs = arcs.merge(
        osrm_arcs[osrm_columns],
        on="arc_id",
        how="left",
        validate="one_to_one",
        suffixes=("", "_osrm"),
    )
    for endpoint in (
        "origin_id",
        "origin_type",
        "destination_id",
        "destination_type",
    ):
        osrm_endpoint = f"{endpoint}_osrm"
        if not arcs[endpoint].astype(str).equals(arcs[osrm_endpoint].astype(str)):
            raise ValueError(f"OSRM endpoint mismatch in column {endpoint}")
    if arcs[["proxy_km", "osrm_km", "osrm_duration_min"]].isna().any().any():
        raise ValueError("OSRM distance layer is incomplete")
    proxy_gap = (
        pd.to_numeric(arcs["road_proxy_km"])
        - pd.to_numeric(arcs["proxy_km"])
    ).abs().max()
    if float(proxy_gap) > 1e-6:
        raise ValueError(
            f"Proxy distance mismatch between workbook sheets: {proxy_gap:.6f} km"
        )
    arcs = arcs.rename(
        columns={
            "quality_flag": "proxy_quality_flag",
            "quality_flag_osrm": "osrm_quality_flag",
            "query_date": "osrm_query_date",
        }
    )

    spatial_weights = spatial[
        ["城市ID", "S1归一化权重", "S2归一化权重", "S3 BYD代理权重"]
    ].rename(
        columns={
            "城市ID": "region_id",
            "S1归一化权重": "spatial_weight_s1",
            "S2归一化权重": "spatial_weight_s2",
            "S3 BYD代理权重": "spatial_weight_s3",
        }
    )
    regions = regions.merge(spatial_weights, on="region_id", how="left")
    base_total = float(regions["retired_battery_tons"].sum())
    for scheme in ("s1", "s2", "s3"):
        regions[f"retired_battery_tons_{scheme}"] = (
            base_total * regions[f"spatial_weight_{scheme}"]
        )

    collection = facilities[facilities["type"] == "collection"].copy()
    self_options = pd.DataFrame(
        {
            "option_id": collection["facility_id"] + "_S",
            "collection_id": collection["facility_id"],
            "name": collection["name"],
            "city": collection["city"],
            "mode": "self_build",
            "lon": collection["lon"],
            "lat": collection["lat"],
            "capacity_tons": collection["capacity_tons"],
            "min_throughput_tons": collection["min_throughput_tons"],
            "fixed_cost_yuan_per_year": collection[
                "fixed_cost_yuan_per_year"
            ],
            "unit_processing_cost_yuan_per_ton": collection[
                "unit_processing_cost_yuan_per_ton"
            ],
            "parameter_quality": collection["parameter_quality"],
            "notes": "Workbook annualized self-build scenario",
        }
    )
    entrusted_options = self_options.copy()
    entrusted_options["option_id"] = collection["facility_id"] + "_E"
    entrusted_options["mode"] = "entrusted"
    entrusted_options["fixed_cost_yuan_per_year"] *= 0.30
    entrusted_options["unit_processing_cost_yuan_per_ton"] = 1200.0
    entrusted_options["parameter_quality"] = "D-contract scenario"
    entrusted_options["notes"] = (
        "Contract fixed fee is 30% of self-build fixed cost; unit fee is scenario value"
    )
    collection_options = pd.concat(
        [self_options, entrusted_options], ignore_index=True
    ).sort_values(["collection_id", "mode"])

    processing = facilities[facilities["type"].isin(["echelon", "recycling"])].copy()
    processing["physical_id"] = processing["facility_id"].astype(str).map(
        lambda value: re.sub(r"([ER])$", "", value)
        if re.fullmatch(r"P\d+[ER]", value)
        else value
    )
    processing["shared_capacity_tons"] = processing.groupby("physical_id")[
        "capacity_tons"
    ].transform("max")
    processing["raw_fixed_equivalent_yuan_per_year"] = processing[
        "fixed_cost_yuan_per_year"
    ]
    external = processing["existing"].astype(int).eq(0)
    processing.loc[external, "fixed_cost_yuan_per_year"] *= 0.10
    processing.loc[external, "notes"] = (
        processing.loc[external, "notes"].fillna("")
        + "; contract access cost set at 10% of full annualized equivalent"
    )
    processing.loc[processing["facility_id"].eq("P01"), "min_throughput_tons"] = 0

    region_cols = [
        "region_id",
        "name",
        "lon",
        "lat",
        "retired_battery_tons",
        "retired_battery_tons_s1",
        "retired_battery_tons_s2",
        "retired_battery_tons_s3",
        "spatial_weight_s1",
        "spatial_weight_s2",
        "spatial_weight_s3",
        "scenario",
        "quality_flag",
    ]
    arc_cols = [
        "arc_id",
        "origin_id",
        "origin_type",
        "origin_name",
        "destination_id",
        "destination_type",
        "destination_name",
        "proxy_km",
        "osrm_km",
        "osrm_duration_min",
        "route_profile",
        "osrm_query_date",
        "proxy_quality_flag",
        "osrm_quality_flag",
    ]
    processing_cols = [
        "facility_id",
        "physical_id",
        "name",
        "type",
        "lon",
        "lat",
        "capacity_tons",
        "shared_capacity_tons",
        "min_throughput_tons",
        "fixed_cost_yuan_per_year",
        "raw_fixed_equivalent_yuan_per_year",
        "unit_processing_cost_yuan_per_ton",
        "existing",
        "must_open",
        "city",
        "coordinate_quality",
        "parameter_quality",
        "source_url",
        "notes",
    ]

    regions[region_cols].to_csv(
        args.output / "regions.csv", index=False, encoding="utf-8-sig"
    )
    collection_options.to_csv(
        args.output / "collection_options.csv", index=False, encoding="utf-8-sig"
    )
    processing[processing_cols].to_csv(
        args.output / "processing_facilities.csv",
        index=False,
        encoding="utf-8-sig",
    )
    arcs[arc_cols].to_csv(
        args.output / "arcs.csv", index=False, encoding="utf-8-sig"
    )

    metadata = {
        "source_workbook": args.workbook.name,
        "base_retired_battery_tons": float(regions["retired_battery_tons"].sum()),
        "low_retired_battery_tons": 3592.88,
        "high_retired_battery_tons": 23257.32,
        "region_count": int(len(regions)),
        "collection_location_count": int(collection["facility_id"].nunique()),
        "processing_role_count": int(len(processing)),
        "echelon_role_count": int((processing["type"] == "echelon").sum()),
        "recycling_role_count": int((processing["type"] == "recycling").sum()),
        "arc_count": int(len(arcs)),
        "distance_columns": ["proxy_km", "osrm_km"],
        "osrm_duration_column": "osrm_duration_min",
        "osrm_query_date": str(arcs["osrm_query_date"].dropna().iloc[0]),
        "data_scope": "Public-data estimates, proxies, literature calibration, and scenarios",
        "capture_rate_note": "20%, 40%, and 60% are D-level scenario assumptions, not BYD facts",
    }
    (args.output / "metadata.yaml").write_text(
        yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
