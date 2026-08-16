from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from .data_loader import InputData
from .solve import ScenarioResult


def _configure_plotting() -> None:
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def save_results(
    output_dir: Path,
    summary: pd.DataFrame,
    results: dict[str, ScenarioResult],
    data: InputData,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    figures = output_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)

    for filename in ("scenario_summary.csv", "scenario_results.csv"):
        summary.to_csv(
            output_dir / filename, index=False, encoding="utf-8-sig"
        )
    pd.concat(
        [result.costs for result in results.values()], ignore_index=True
    ).to_csv(output_dir / "scenario_costs.csv", index=False, encoding="utf-8-sig")
    pd.concat(
        [result.collections for result in results.values()], ignore_index=True
    ).to_csv(
        output_dir / "scenario_collections.csv", index=False, encoding="utf-8-sig"
    )
    pd.concat(
        [result.processing for result in results.values()], ignore_index=True
    ).to_csv(
        output_dir / "scenario_processing.csv", index=False, encoding="utf-8-sig"
    )
    pd.concat(
        [result.flows for result in results.values()], ignore_index=True
    ).to_csv(output_dir / "scenario_flows.csv", index=False, encoding="utf-8-sig")
    (output_dir / "validation.json").write_text(
        json.dumps(
            {name: result.validation for name, result in results.items()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    _configure_plotting()
    _plot_baseline_costs(results["baseline"], figures)
    _plot_scenario_costs(summary, figures)
    _plot_scale_and_emergency(summary, figures)
    _plot_radius_tradeoff(summary, figures)
    _plot_spatial_weights(summary, figures)
    _plot_minimum_throughput(summary, figures)
    _plot_p01_stress(summary, figures)
    _plot_distance_transport_sensitivity(summary, figures)
    _plot_proxy_osrm_comparison(summary, figures)
    _plot_baseline_network(results["baseline"], data, figures)
    _plot_baseline_network(
        results["proxy_baseline"],
        data,
        figures,
        filename="proxy_baseline_network.png",
        title="proxy复现基准网络节点与正流量运输弧",
    )


def _plot_baseline_costs(result: ScenarioResult, figures: Path) -> None:
    labels = {
        "fixed_collection": "前端固定",
        "fixed_processing": "后端固定",
        "variable_collection": "回收检测",
        "variable_processing": "后端处理",
        "transport": "运输",
        "expansion": "扩容",
        "emergency": "应急外包",
    }
    df = result.costs[result.costs["cost_yuan"] > 1e-6].copy()
    df["label"] = df["cost_item"].map(labels)
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    colors = ["#2E6F95", "#E07A5F", "#3D9970", "#B56576", "#F2CC8F"]
    ax.bar(df["label"], df["cost_yuan"] / 1e6, color=colors[: len(df)])
    ax.set_ylabel("成本（百万元/年）")
    ax.set_title("基准情景年度成本构成")
    ax.grid(axis="y", color="#D9E0E6", linewidth=0.7)
    fig.tight_layout()
    fig.savefig(figures / "baseline_cost_composition.png", dpi=180)
    plt.close(fig)


def _plot_scenario_costs(summary: pd.DataFrame, figures: Path) -> None:
    selected = [
        "baseline",
        "demand_low",
        "demand_high",
        "capture_low",
        "capture_high",
        "transport_low",
        "transport_high",
        "radius_tight",
        "radius_loose",
        "organization_self",
        "organization_entrusted",
        "reuse_low",
        "reuse_high",
        "p01_free",
        "p01_reduced",
    ]
    names = {
        "baseline": "基准",
        "demand_low": "低退役量",
        "demand_high": "高退役量",
        "capture_low": "低承接率",
        "capture_high": "高承接率",
        "transport_low": "低运价",
        "transport_high": "高运价",
        "radius_tight": "紧半径",
        "radius_loose": "宽半径",
        "organization_self": "仅自建",
        "organization_entrusted": "仅委托",
        "reuse_low": "低梯次",
        "reuse_high": "高梯次",
        "p01_free": "P01自由",
        "p01_reduced": "P01折减",
    }
    plot_df = summary[summary["scenario"].isin(selected)].copy()
    plot_df["order"] = plot_df["scenario"].map(
        {name: i for i, name in enumerate(selected)}
    )
    plot_df = plot_df.sort_values("order")
    fig, ax = plt.subplots(figsize=(12, 5.5))
    colors = [
        "#2E6F95" if name == "baseline" else "#7DA7C5"
        for name in plot_df["scenario"]
    ]
    ax.bar(
        [names[name] for name in plot_df["scenario"]],
        plot_df["total_cost_yuan"] / 1e6,
        color=colors,
    )
    ax.set_ylabel("年度总成本（百万元）")
    ax.set_title("核心单因素情景年度总成本比较")
    ax.tick_params(axis="x", rotation=38)
    ax.grid(axis="y", color="#D9E0E6", linewidth=0.7)
    fig.tight_layout()
    fig.savefig(figures / "scenario_total_costs.png", dpi=180)
    plt.close(fig)


def _plot_scale_and_emergency(summary: pd.DataFrame, figures: Path) -> None:
    selected = ["demand_low", "capture_low", "baseline", "capture_high", "demand_high"]
    labels = ["低退役量", "低承接率", "基准", "高承接率", "高退役量"]
    df = summary.set_index("scenario").loc[selected]
    fig, ax1 = plt.subplots(figsize=(9.5, 5.2))
    ax1.bar(
        labels,
        df["unit_cost_yuan_per_intake_ton"],
        color=["#9AB9CF", "#83AFC5", "#2E6F95", "#6FA78E", "#3D9970"],
    )
    ax1.set_ylabel("单位网络进入量成本（元/吨）")
    ax1.set_title("业务规模、单位成本与应急外包比例")
    ax1.grid(axis="y", color="#D9E0E6", linewidth=0.7)
    ax2 = ax1.twinx()
    ax2.plot(
        labels,
        100 * df["emergency_share"],
        color="#B56576",
        marker="o",
        linewidth=2,
    )
    ax2.set_ylabel("应急外包比例（%）")
    fig.tight_layout()
    fig.savefig(figures / "scale_unit_cost_emergency.png", dpi=180)
    plt.close(fig)


def _plot_radius_tradeoff(summary: pd.DataFrame, figures: Path) -> None:
    selected = ["radius_tight", "baseline", "radius_loose"]
    labels = ["紧服务半径", "基准半径", "宽服务半径"]
    df = summary.set_index("scenario").loc[selected]
    fig, ax1 = plt.subplots(figsize=(8.2, 4.8))
    ax1.bar(
        labels,
        df["total_cost_yuan"] / 1e6,
        color=["#B56576", "#2E6F95", "#6FA78E"],
    )
    ax1.set_ylabel("年度总成本（百万元）")
    ax1.set_title("服务半径对成本与应急外包的影响")
    ax1.grid(axis="y", color="#D9E0E6", linewidth=0.7)
    ax2 = ax1.twinx()
    ax2.plot(
        labels,
        100 * df["emergency_share"],
        color="#E07A5F",
        marker="o",
        linewidth=2,
    )
    ax2.set_ylabel("应急外包比例（%）")
    fig.tight_layout()
    fig.savefig(figures / "service_radius_tradeoff.png", dpi=180)
    plt.close(fig)


def _plot_spatial_weights(summary: pd.DataFrame, figures: Path) -> None:
    selected = ["spatial_s1", "spatial_s2", "baseline"]
    labels = ["S1\nGDP+人口", "S2\n综合权重", "S3\nNEV代理"]
    df = summary.set_index("scenario").loc[selected]
    x = range(len(df))
    fig, ax1 = plt.subplots(figsize=(7.4, 4.8))
    ax1.bar(
        x,
        df["total_cost_yuan"] / 1e6,
        color=["#4C78A8", "#F58518", "#54A24B"],
        width=0.58,
    )
    ax1.set_ylabel("总成本（百万元/年）")
    ax1.set_xticks(list(x), labels)
    ax1.grid(axis="y", color="#D9E0E6", linewidth=0.7)
    ax2 = ax1.twinx()
    ax2.plot(
        list(x),
        100 * df["emergency_share"],
        color="#B33F62",
        marker="o",
        linewidth=2,
    )
    ax2.set_ylabel("应急外包比例（%）")
    ax1.set_title("空间权重代理对成本与网络缺口的影响")
    fig.tight_layout()
    fig.savefig(figures / "spatial_weight_sensitivity.png", dpi=180)
    plt.close(fig)


def _plot_minimum_throughput(summary: pd.DataFrame, figures: Path) -> None:
    selected = [
        "collection_minimum_zero",
        "collection_minimum_100",
        "baseline",
        "collection_minimum_500",
    ]
    labels = ["0", "100", "300", "500"]
    df = summary.set_index("scenario").loc[selected]
    x = range(len(df))
    fig, ax1 = plt.subplots(figsize=(7.4, 4.8))
    ax1.bar(
        x,
        df["total_cost_yuan"] / 1e6,
        color="#4C78A8",
        width=0.58,
    )
    ax1.set_xlabel("回收检测与集运中心最低处理量（吨/年）")
    ax1.set_ylabel("总成本（百万元/年）")
    ax1.set_xticks(list(x), labels)
    ax1.grid(axis="y", color="#D9E0E6", linewidth=0.7)
    ax2 = ax1.twinx()
    ax2.plot(
        list(x),
        100 * df["emergency_share"],
        color="#E45756",
        marker="o",
        linewidth=2,
    )
    ax2.set_ylabel("应急外包比例（%）")
    ax1.set_title("最低处理量对成本与网络缺口的影响")
    fig.tight_layout()
    fig.savefig(figures / "minimum_throughput_sensitivity.png", dpi=180)
    plt.close(fig)


def _plot_p01_stress(summary: pd.DataFrame, figures: Path) -> None:
    selected = [
        "p01_stress_no_expand",
        "p01_stress_expand_full",
        "p01_stress_expand",
    ]
    labels = ["不扩容", "全成本扩容可选", "折价扩容可选"]
    df = summary.set_index("scenario").loc[selected]
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    bars = ax.bar(
        labels,
        df["total_cost_yuan"] / 1e6,
        color=["#B56576", "#7DA7C5", "#3D9970"],
    )
    ax.set_ylabel("年度总成本（百万元）")
    ax.set_title("P01低可用能力压力情景的扩容边界")
    ax.set_ylim(
        max(0, float((df["total_cost_yuan"] / 1e6).min()) - 1.0),
        float((df["total_cost_yuan"] / 1e6).max()) + 0.5,
    )
    ax.grid(axis="y", color="#D9E0E6", linewidth=0.7)
    for bar, value in zip(bars, df["total_cost_yuan"] / 1e6):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.08,
            f"{value:.2f}",
            ha="center",
            va="bottom",
        )
    fig.tight_layout()
    fig.savefig(figures / "p01_expansion_boundary.png", dpi=180)
    plt.close(fig)


def _plot_distance_transport_sensitivity(
    summary: pd.DataFrame, figures: Path
) -> None:
    indexed = summary.set_index("scenario")
    distance_scenarios = [
        "road_factor_low",
        "proxy_baseline",
        "baseline",
        "road_factor_high",
    ]
    distance_labels = ["proxy λ=1.1", "proxy λ=1.2", "OSRM", "proxy λ=1.3"]
    transport_scenarios = [
        "transport_low",
        "baseline",
        "transport_high",
        "transport_double",
        "transport_fivefold",
    ]
    transport_labels = ["0.34", "0.49", "0.64", "0.98", "2.45"]
    distance_df = indexed.loc[distance_scenarios]
    transport_df = indexed.loc[transport_scenarios]

    fig, axes = plt.subplots(1, 2, figsize=(12.4, 5.0))
    ax = axes[0]
    bars = ax.bar(
        distance_labels,
        distance_df["total_cost_yuan"] / 1e6,
        color=["#7DA7C5", "#4C78A8", "#3D9970", "#B56576"],
    )
    ax.set_ylabel("年度总成本（百万元）")
    ax.set_title("距离口径与proxy系数")
    ax.grid(axis="y", color="#D9E0E6", linewidth=0.7)
    ax.tick_params(axis="x", rotation=18)
    ax2 = ax.twinx()
    ax2.plot(
        distance_labels,
        distance_df["emergency_tons"],
        color="#E07A5F",
        marker="o",
        linewidth=2,
    )
    ax2.set_ylabel("应急外包量（吨）")
    for bar, value in zip(bars, distance_df["total_cost_yuan"] / 1e6):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.2f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    ax = axes[1]
    ax.plot(
        transport_labels,
        transport_df["total_cost_yuan"] / 1e6,
        color="#2E6F95",
        marker="o",
        linewidth=2,
    )
    ax.set_xlabel("运输单价（元/(吨·km)）")
    ax.set_ylabel("年度总成本（百万元）")
    ax.set_title("OSRM基准下运输价格")
    ax.grid(color="#D9E0E6", linewidth=0.7)
    fig.suptitle("运输价格与距离口径敏感性", y=1.02)
    fig.tight_layout()
    fig.savefig(figures / "distance_transport_sensitivity.png", dpi=180)
    plt.close(fig)


def _plot_proxy_osrm_comparison(summary: pd.DataFrame, figures: Path) -> None:
    df = summary.set_index("scenario").loc[["proxy_baseline", "baseline"]]
    labels = ["proxy基准", "OSRM基准"]
    metrics = [
        ("total_cost_yuan", 1e6, "总成本（百万元）", "年度总成本"),
        ("emergency_tons", 1.0, "吨", "应急外包量"),
        ("collection_count", 1.0, "座", "区域中心数量"),
        ("total_tonne_km", 1e6, "百万吨·km", "总运输周转量"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(9.2, 7.0))
    colors = ["#4C78A8", "#3D9970"]
    for ax, (column, divisor, ylabel, title) in zip(axes.flat, metrics):
        values = df[column] / divisor
        bars = ax.bar(labels, values, color=colors, width=0.58)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(axis="y", color="#D9E0E6", linewidth=0.7)
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value,
                f"{value:.2f}",
                ha="center",
                va="bottom",
                fontsize=9,
            )
    fig.suptitle("proxy基准与OSRM基准结果对比", y=1.01)
    fig.tight_layout()
    fig.savefig(figures / "proxy_osrm_baseline_comparison.png", dpi=180)
    plt.close(fig)


def _plot_baseline_network(
    result: ScenarioResult,
    data: InputData,
    figures: Path,
    filename: str = "baseline_network.png",
    title: str = "OSRM基准网络节点与正流量运输弧",
) -> None:
    region_xy = data.regions.set_index("region_id")[["lon", "lat", "name"]]
    options = data.collection_options.set_index("option_id")
    processing = data.processing_facilities.set_index("facility_id")

    fig, ax = plt.subplots(figsize=(10, 7.5))
    first = result.flows[result.flows["stage"] == "source_collection"]
    second = result.flows[
        result.flows["stage"].isin(
            ["collection_echelon", "collection_recycling"]
        )
    ]
    for row in first.itertuples():
        origin = region_xy.loc[row.origin_id]
        destination = options.loc[row.destination_id]
        ax.plot(
            [origin.lon, destination.lon],
            [origin.lat, destination.lat],
            color="#AAB7C4",
            linewidth=0.4 + min(row.flow_tons / 800, 1.8),
            alpha=0.55,
            zorder=1,
        )
    for row in second.itertuples():
        origin = options.loc[row.origin_id]
        destination = processing.loc[row.destination_id]
        ax.plot(
            [origin.lon, destination.lon],
            [origin.lat, destination.lat],
            color="#D27D60",
            linewidth=0.5 + min(row.flow_tons / 800, 2.0),
            alpha=0.65,
            zorder=1,
        )
    ax.scatter(
        data.regions["lon"],
        data.regions["lat"],
        s=18,
        color="#6C7A89",
        label="来源城市",
        zorder=2,
    )
    if not result.collections.empty:
        ax.scatter(
            result.collections["lon"],
            result.collections["lat"],
            s=72,
            marker="s",
            color="#2E6F95",
            label="启用回收检测节点",
            zorder=3,
        )
    if not result.processing.empty:
        echelon = result.processing[result.processing["type"] == "echelon"]
        recycling = result.processing[result.processing["type"] == "recycling"]
        ax.scatter(
            echelon["lon"],
            echelon["lat"],
            s=85,
            marker="^",
            color="#3D9970",
            label="梯次利用节点",
            zorder=3,
        )
        ax.scatter(
            recycling["lon"],
            recycling["lat"],
            s=90,
            marker="D",
            color="#B56576",
            label="再生利用节点",
            zorder=3,
        )
    ax.set_xlabel("经度")
    ax.set_ylabel("纬度")
    ax.set_title(title)
    ax.legend(frameon=False, loc="best")
    ax.grid(color="#E6EBEF", linewidth=0.6)
    fig.tight_layout()
    fig.savefig(figures / filename, dpi=180)
    plt.close(fig)
