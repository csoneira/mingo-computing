#!/usr/bin/env python3
"""Build per-gate time series for configurable celestial-sphere regions."""
from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from test_3_configurable_event_gates import (
    add_derived_topology_columns,
    assign_gates,
    condition_columns,
    derived_topology_setting,
    derived_column_names,
    efficiency_product_from_frame,
    efficiency_product_setting,
    load_configuration,
    parse_gates,
    topology_source_columns,
)

OUTPUT_DIRECTORY = "ANGULAR_TIME_SERIES"
DEFAULT_CONFIG = Path(__file__).with_name("config_test_3_event_gates.yaml")


def angular_time_series_setting(
    config: dict[str, Any], division_case: str | None = None,
) -> dict[str, Any]:
    raw = config.get("angular_time_series")
    if not isinstance(raw, dict) or not bool(raw.get("enabled", True)):
        raise ValueError("angular_time_series must be an enabled YAML mapping")
    case_name: str | None = None
    division_cases = raw.get("division_cases")
    if division_cases is not None:
        if not isinstance(division_cases, dict) or not division_cases:
            raise ValueError("angular_time_series.division_cases must be a nonempty mapping")
        case_name = str(
            division_case or raw.get("default_division_case", next(iter(division_cases)))
        ).strip()
        case = division_cases.get(case_name)
        if not isinstance(case, dict):
            raise ValueError(f"Unknown angular division case: {case_name!r}")
        raw = {**raw, **case}
    elif division_case is not None:
        raise ValueError("No angular_time_series.division_cases are configured")
    try:
        window = pd.Timedelta(str(raw.get("accumulation_timespan", "10min")))
    except ValueError as exc:
        raise ValueError("Invalid angular_time_series.accumulation_timespan") from exc
    if window <= pd.Timedelta(0) or int(window.value) % 1_000_000_000:
        raise ValueError("angular_time_series accumulation must be positive whole seconds")
    vertical_limit = float(raw.get("vertical_max_theta_degrees", 20.0))
    edges = np.asarray(
        raw.get("azimuth_edges_degrees", [-45, 45, 135, 225, 315]), dtype=float,
    )
    labels = [str(value).strip() for value in raw.get(
        "azimuth_region_labels", ["North", "East", "South", "West"],
    )]
    if not np.isfinite(vertical_limit) or not 0 < vertical_limit < 90:
        raise ValueError("vertical_max_theta_degrees must be in (0, 90)")
    if (
        edges.ndim != 1 or len(edges) < 3 or not np.isfinite(edges).all()
        or not np.all(np.diff(edges) > 0) or not np.isclose(edges[-1] - edges[0], 360.0)
        or len(labels) != len(edges) - 1 or any(not label for label in labels)
    ):
        raise ValueError(
            "azimuth edges must increase across exactly 360 degrees and have one label per sector"
        )
    return {
        "time_column": str(raw.get("time_column", "datetime")).strip(),
        "theta_column": str(raw.get("theta_column", "event_theta")).strip(),
        "phi_column": str(raw.get("phi_column", "event_phi")).strip(),
        "window": window,
        "degrees": bool(raw.get("convert_radians_to_degrees", True)),
        "vertical_limit": vertical_limit,
        "edges": edges,
        "labels": labels,
        "case_name": case_name,
    }


def region_definitions(setting: dict[str, Any]) -> list[dict[str, Any]]:
    limit = setting["vertical_limit"]
    definitions: list[dict[str, Any]] = [{
        "region_code": "vertical",
        "region_label": f"Vertical: θ < {limit:g}°",
        "theta_min_degrees": 0.0,
        "theta_max_degrees": limit,
        "azimuth_min_degrees": np.nan,
        "azimuth_max_degrees": np.nan,
    }]
    for index, (lower, upper) in enumerate(
        zip(setting["edges"][:-1], setting["edges"][1:], strict=True), 1,
    ):
        display_lower = lower % 360.0
        display_upper = upper % 360.0
        wrap_label = " (wrap)" if display_lower >= display_upper else ""
        definitions.append({
            "region_code": f"azimuth_{index}",
            "region_label": (
                f"{setting['labels'][index - 1]}: φ "
                f"[{display_lower:g}°, {display_upper:g}°){wrap_label}"
            ),
            "theta_min_degrees": limit,
            "theta_max_degrees": 90.0,
            "azimuth_min_degrees": display_lower,
            "azimuth_max_degrees": display_upper,
        })
    return definitions


def classify_regions(theta: pd.Series, phi: pd.Series, setting: dict[str, Any]) -> np.ndarray:
    theta_values = pd.to_numeric(theta, errors="coerce").to_numpy(dtype=float)
    phi_values = pd.to_numeric(phi, errors="coerce").to_numpy(dtype=float)
    if setting["degrees"]:
        theta_values = np.degrees(theta_values)
        phi_values = np.degrees(phi_values)
    wrapped_phi = (phi_values - setting["edges"][0]) % 360.0 + setting["edges"][0]
    valid = (
        np.isfinite(theta_values) & np.isfinite(wrapped_phi)
        & (theta_values >= 0.0) & (theta_values <= 90.0)
    )
    regions = np.full(len(theta_values), None, dtype=object)
    vertical = valid & (theta_values < setting["vertical_limit"])
    regions[vertical] = "vertical"
    inclined = valid & ~vertical
    sector_indices = np.searchsorted(setting["edges"], wrapped_phi, side="right") - 1
    for index in range(len(setting["edges"]) - 1):
        regions[inclined & (sector_indices == index)] = f"azimuth_{index + 1}"
    return regions


def inferred_title(manifest: pd.DataFrame) -> str:
    station = str(manifest["station"].dropna().iloc[0])
    acquired = pd.to_datetime(manifest["acquisition_datetime"], errors="coerce").dropna()
    if acquired.empty:
        return f"{station} | {len(manifest)} selected files"
    return (
        f"{station} | {len(manifest)} consecutive files | "
        f"{acquired.min():%Y-%m-%d %H:%M:%S} to {acquired.max():%Y-%m-%d %H:%M:%S}"
    )


def aggregate(
    manifest: pd.DataFrame, config: dict[str, Any], setting: dict[str, Any],
) -> tuple[list[Any], dict[int, int], dict[tuple[str, int, str], int]]:
    gates = parse_gates(config["gates"])
    topology_setting = derived_topology_setting(config)
    gate_columns: set[str] = set()
    for gate in gates:
        gate_columns.update(condition_columns(gate.condition, location=f"gate[{gate.code}]"))
    columns = list(dict.fromkeys([
        setting["time_column"], setting["theta_column"], setting["phi_column"],
        *(column for column in gate_columns if column not in set(derived_column_names())),
        *topology_source_columns(topology_setting),
    ]))
    window_ns = int(setting["window"].value)
    exposure_bits: dict[int, int] = defaultdict(int)
    counts: dict[tuple[str, int, str], int] = defaultdict(int)

    for file_index, path_value in enumerate(manifest["path"], 1):
        path = Path(str(path_value))
        parquet = pq.ParquetFile(path)
        missing = sorted(set(columns) - set(parquet.schema_arrow.names))
        if missing:
            raise ValueError(f"{path.name} is missing required columns: {', '.join(missing)}")
        file_rows = 0
        for batch in parquet.iter_batches(batch_size=100_000, columns=columns):
            frame = batch.to_pandas()
            add_derived_topology_columns(frame, topology_setting)
            masks = assign_gates(frame, gates)
            timestamps = pd.to_datetime(frame[setting["time_column"]], errors="coerce")
            valid_time = timestamps.notna().to_numpy()
            if not bool(valid_time.any()):
                file_rows += len(frame)
                continue
            timestamp_ns = timestamps.astype("int64").to_numpy()
            window_values = timestamp_ns - timestamp_ns % window_ns
            second_values = timestamp_ns - timestamp_ns % 1_000_000_000
            unique_seconds = np.unique(
                np.column_stack((window_values[valid_time], second_values[valid_time])), axis=0,
            )
            for window_value, second_value in unique_seconds:
                offset = (int(second_value) - int(window_value)) // 1_000_000_000
                exposure_bits[int(window_value)] |= 1 << offset

            regions = classify_regions(
                frame[setting["theta_column"]], frame[setting["phi_column"]], setting,
            )
            valid_region = np.fromiter(
                (value is not None for value in regions), dtype=bool, count=len(regions),
            )
            for gate in gates:
                selected = valid_time & valid_region & masks[gate.code].to_numpy(dtype=bool)
                if not bool(selected.any()):
                    continue
                grouped = pd.DataFrame({
                    "window": window_values[selected], "region": regions[selected],
                }).groupby(["window", "region"], sort=False).size()
                for (window_value, region_code), count in grouped.items():
                    counts[(gate.code, int(window_value), str(region_code))] += int(count)
            file_rows += len(frame)
        print(
            f"Angular regions: processed {file_rows:,} rows from {path.name} "
            f"({file_index}/{len(manifest)})"
        )
    return gates, exposure_bits, counts


def summary_frame(
    gates: list[Any], exposure_bits: dict[int, int],
    counts: dict[tuple[str, int, str], int], definitions: list[dict[str, Any]],
    window: pd.Timedelta,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for gate in gates:
        for window_ns in sorted(exposure_bits):
            observed_seconds = int(exposure_bits[window_ns]).bit_count()
            region_counts = {
                definition["region_code"]: counts.get(
                    (gate.code, window_ns, definition["region_code"]), 0,
                ) for definition in definitions
            }
            classified_count = sum(region_counts.values())
            for definition in definitions:
                count = region_counts[definition["region_code"]]
                rows.append({
                    "window_start": pd.Timestamp(window_ns),
                    "window_end": pd.Timestamp(window_ns) + window,
                    "gate_code": gate.code,
                    "gate_name": gate.name,
                    "gate_label": gate.short_label or gate.name,
                    **definition,
                    "observed_seconds": observed_seconds,
                    "event_count": count,
                    "event_rate_hz": count / observed_seconds if observed_seconds else np.nan,
                    "classified_gate_event_count": classified_count,
                    "angular_fraction": count / classified_count if classified_count else np.nan,
                })
    return pd.DataFrame(rows)


def efficiency_by_angular_window(
    run_directory: Path, config: dict[str, Any], window: pd.Timedelta,
) -> pd.DataFrame:
    source_path = (
        run_directory / "ENABLED_GATE_COMPARISON" / "enabled_gate_comparison.csv"
    )
    if not source_path.is_file():
        raise FileNotFoundError(
            f"Angular efficiency correlation requires {source_path}"
        )
    comparison = pd.read_csv(source_path, dtype={"gate_code": str})
    count_columns = [
        "topology_123_count", "topology_124_count", "topology_134_count",
        "topology_234_count", "topology_1234_count",
    ]
    required = {"window_start", "gate_code", "gate_label", *count_columns}
    missing = sorted(required - set(comparison.columns))
    if missing:
        raise ValueError(
            f"{source_path} is missing required columns: {', '.join(missing)}"
        )
    comparison["window_start"] = pd.to_datetime(
        comparison["window_start"], errors="coerce",
    )
    gates = parse_gates(config["gates"])
    label_to_code = {gate.short_label: gate.code for gate in gates}
    comparison["gate_label"] = comparison["gate_label"].astype("string")
    unknown_labels = sorted(
        set(comparison["gate_label"].dropna()) - set(label_to_code)
    )
    if unknown_labels:
        raise ValueError(
            "Enabled-gate comparison contains gate labels not enabled by the "
            "current config: " + ", ".join(unknown_labels)
        )
    comparison["gate_code"] = comparison["gate_label"].map(label_to_code)
    comparison = comparison.dropna(subset=["window_start", "gate_code"]).copy()
    for column in count_columns:
        comparison[column] = pd.to_numeric(
            comparison[column], errors="coerce",
        ).fillna(0.0)
    comparison["angular_window_start"] = comparison["window_start"].dt.floor(window)
    grouped = comparison.groupby(
        ["gate_code", "angular_window_start"], as_index=False, sort=True,
    )[count_columns].sum()
    detected = grouped["topology_1234_count"]
    missed_columns = {
        1: "topology_234_count",
        2: "topology_134_count",
        3: "topology_124_count",
        4: "topology_123_count",
    }
    for plane, missed_column in missed_columns.items():
        denominator = detected + grouped[missed_column]
        grouped[f"plane_{plane}_efficiency"] = detected.div(
            denominator.where(denominator.gt(0.0))
        )
    product = efficiency_product_setting(config)
    grouped["efficiency_product"] = efficiency_product_from_frame(
        grouped, product["efficiency_product_planes"],
        column_template="plane_{plane}_efficiency",
    )
    grouped["efficiency_product_mode"] = product["efficiency_product_mode"]
    grouped["efficiency_product_plane_numbers"] = ",".join(
        str(plane) for plane in product["efficiency_product_planes"]
    )
    return grouped.rename(columns={"angular_window_start": "window_start"})


def attach_efficiency_product(
    summary: pd.DataFrame, efficiency: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "gate_code", "window_start",
        *(f"plane_{plane}_efficiency" for plane in range(1, 5)),
        "efficiency_product", "efficiency_product_mode",
        "efficiency_product_plane_numbers",
    ]
    result = summary.copy()
    result["gate_code"] = result["gate_code"].astype(str)
    result["window_start"] = pd.to_datetime(result["window_start"], errors="coerce")
    return result.merge(
        efficiency[columns], on=["gate_code", "window_start"], how="left",
        validate="many_to_one",
    )


def region_fraction_ratios(
    summary: pd.DataFrame, definitions: list[dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    group_columns = [
        "window_start", "window_end", "gate_code", "gate_name", "gate_label",
    ]
    definition_pairs = list(combinations(definitions, 2))
    for keys, group in summary.groupby(group_columns, sort=True, dropna=False):
        fractions = group.set_index("region_code")["angular_fraction"]
        product = group.iloc[0]
        for numerator, denominator in definition_pairs:
            numerator_fraction = fractions.get(numerator["region_code"], np.nan)
            denominator_fraction = fractions.get(denominator["region_code"], np.nan)
            ratio = (
                numerator_fraction / denominator_fraction
                if np.isfinite(numerator_fraction)
                and np.isfinite(denominator_fraction)
                and denominator_fraction != 0.0
                else np.nan
            )
            numerator_label = numerator["region_label"].split(":", 1)[0]
            denominator_label = denominator["region_label"].split(":", 1)[0]
            rows.append({
                **dict(zip(group_columns, keys, strict=True)),
                "numerator_region_code": numerator["region_code"],
                "numerator_region_label": numerator["region_label"],
                "numerator_fraction": numerator_fraction,
                "denominator_region_code": denominator["region_code"],
                "denominator_region_label": denominator["region_label"],
                "denominator_fraction": denominator_fraction,
                "ratio_label": f"{numerator_label} / {denominator_label}",
                "regional_fraction_ratio": ratio,
                "efficiency_product": product["efficiency_product"],
                "efficiency_product_mode": product["efficiency_product_mode"],
                "efficiency_product_plane_numbers": (
                    product["efficiency_product_plane_numbers"]
                ),
            })
    return pd.DataFrame(rows)


def write_plots(
    summary: pd.DataFrame, ratios: pd.DataFrame, gates: list[Any],
    definitions: list[dict[str, Any]], output_directory: Path, title: str,
    window: pd.Timedelta,
) -> list[Path]:
    colors = plt.get_cmap("tab10").colors
    ratio_colors = plt.get_cmap("tab20").colors
    paths: list[Path] = []
    for gate in gates:
        gate_rows = summary.loc[summary["gate_code"].eq(gate.code)]
        gate_ratios = ratios.loc[ratios["gate_code"].eq(gate.code)]
        figure, axes = plt.subplots(
            3, 1, figsize=(17, 14), sharex=True, constrained_layout=True,
        )
        for region_index, definition in enumerate(definitions):
            region_rows = gate_rows.loc[
                gate_rows["region_code"].eq(definition["region_code"])
            ].sort_values("window_start")
            style = {
                "color": colors[region_index % len(colors)], "marker": ".",
                "markersize": 3, "linewidth": 1.0, "label": definition["region_label"],
            }
            axes[0].plot(region_rows["window_start"], region_rows["event_rate_hz"], **style)
            axes[1].plot(region_rows["window_start"], region_rows["angular_fraction"], **style)
        for ratio_index, (ratio_label, ratio_rows) in enumerate(
            gate_ratios.groupby("ratio_label", sort=False)
        ):
            ratio_rows = ratio_rows.sort_values("window_start")
            axes[2].plot(
                ratio_rows["window_start"], ratio_rows["regional_fraction_ratio"],
                color=ratio_colors[ratio_index % len(ratio_colors)], marker=".",
                markersize=2.5, linewidth=0.8, label=ratio_label,
            )
        axes[0].set(
            ylabel="Regional event rate [Hz]",
            title="Event rate in each celestial-sphere region",
        )
        axes[1].set(
            ylabel="Fraction of classified gate events",
            title="Regional fraction within the gate",
        )
        axes[2].set(
            xlabel="Time", ylabel="Regional fraction ratio",
            title="Pairwise regional fractions (numerator / denominator)",
        )
        for axis in axes:
            axis.margins(y=0.05)
            axis.grid(True, alpha=0.25)
            axis.legend(loc="best", fontsize=7, ncols=3)
        label = gate.short_label or gate.name
        figure.suptitle(
            f"{title}\nGate {label} [{gate.code}] | {len(definitions)} angular regions | "
            f"accumulation={window}", fontsize=14,
        )
        figure.autofmt_xdate()
        path = output_directory / f"gate_{gate.code}_angular_time_series.png"
        figure.savefig(path, dpi=160)
        plt.close(figure)
        paths.append(path)
    return paths


def correlation_style(
    axis: Any, x_values: pd.Series, y_values: pd.Series, label: str,
    color: Any,
) -> None:
    x = pd.to_numeric(x_values, errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(y_values, errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x = x[valid]
    y = y[valid]
    correlation = np.nan
    if len(x) >= 2 and np.ptp(x) > 0.0 and np.ptp(y) > 0.0:
        correlation = float(np.corrcoef(x, y)[0, 1])
    correlation_text = f"r={correlation:.3f}" if np.isfinite(correlation) else "r=n/a"
    axis.scatter(
        x, y, s=9, alpha=0.28, color=color,
        label=f"{label} ({correlation_text}, n={len(x)})",
    )
    if len(x) >= 2 and np.ptp(x) > 0.0:
        slope, intercept = np.polyfit(x, y, 1)
        fit_x = np.linspace(x.min(), x.max(), 100)
        axis.plot(fit_x, slope * fit_x + intercept, color=color, linewidth=1.2)


def write_efficiency_correlation_plots(
    summary: pd.DataFrame, ratios: pd.DataFrame, gates: list[Any],
    definitions: list[dict[str, Any]], output_directory: Path, title: str,
    window: pd.Timedelta, product: dict[str, Any],
) -> list[Path]:
    colors = plt.get_cmap("tab10").colors
    ratio_colors = plt.get_cmap("tab20").colors
    paths: list[Path] = []
    for gate in gates:
        gate_rows = summary.loc[summary["gate_code"].eq(gate.code)]
        gate_ratios = ratios.loc[ratios["gate_code"].eq(gate.code)]
        figure, axes = plt.subplots(
            2, 1, figsize=(15, 13), sharex=True, constrained_layout=True,
        )
        for region_index, definition in enumerate(definitions):
            region_rows = gate_rows.loc[
                gate_rows["region_code"].eq(definition["region_code"])
            ]
            correlation_style(
                axes[0], region_rows["efficiency_product"],
                region_rows["angular_fraction"], definition["region_label"],
                colors[region_index % len(colors)],
            )
        for ratio_index, (ratio_label, ratio_rows) in enumerate(
            gate_ratios.groupby("ratio_label", sort=False)
        ):
            correlation_style(
                axes[1], ratio_rows["efficiency_product"],
                ratio_rows["regional_fraction_ratio"], ratio_label,
                ratio_colors[ratio_index % len(ratio_colors)],
            )
        axes[0].set(
            ylabel="Fraction of classified gate events",
            title="Regional fractions versus detector efficiency",
        )
        axes[1].set(
            xlabel="Configured plane-efficiency product",
            ylabel="Regional fraction ratio",
            title="Pairwise regional-fraction ratios versus detector efficiency",
        )
        for axis in axes:
            axis.margins(x=0.03, y=0.05)
            axis.grid(True, alpha=0.25)
            axis.legend(loc="best", fontsize=7, ncols=2)
        label = gate.short_label or gate.name
        mode = product["efficiency_product_mode"]
        product_label = product["efficiency_product_label"]
        figure.suptitle(
            f"{title}\nGate {label} [{gate.code}] | accumulation={window} | "
            f"efficiency={mode} ({product_label})", fontsize=14,
        )
        path = (
            output_directory
            / f"gate_{gate.code}_angular_fraction_efficiency_correlation.png"
        )
        figure.savefig(path, dpi=160)
        plt.close(figure)
        paths.append(path)
    return paths


def build(
    run_directory: Path, config_path: Path, division_case: str | None = None,
) -> list[Path]:
    run_directory = run_directory.resolve()
    manifest_path = run_directory / "selected_files.csv"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    config = load_configuration(config_path)
    setting = angular_time_series_setting(config, division_case)
    product = efficiency_product_setting(config)
    output_directory = run_directory / OUTPUT_DIRECTORY
    if setting["case_name"] is not None:
        output_directory = output_directory / setting["case_name"]
    output_directory.mkdir(parents=True, exist_ok=True)
    manifest = pd.read_csv(manifest_path)
    gates, exposure_bits, counts = aggregate(manifest, config, setting)
    definitions = region_definitions(setting)
    summary = summary_frame(gates, exposure_bits, counts, definitions, setting["window"])
    efficiency = efficiency_by_angular_window(run_directory, config, setting["window"])
    summary = attach_efficiency_product(summary, efficiency)
    ratios = region_fraction_ratios(summary, definitions)
    csv_path = output_directory / "angular_time_series.csv"
    summary.to_csv(csv_path, index=False)
    ratio_path = output_directory / "angular_region_fraction_ratios.csv"
    ratios.to_csv(ratio_path, index=False)
    definition_path = output_directory / "angular_regions.csv"
    pd.DataFrame(definitions).to_csv(definition_path, index=False)
    time_plots = write_plots(
        summary, ratios, gates, definitions, output_directory,
        inferred_title(manifest), setting["window"],
    )
    correlation_plots = write_efficiency_correlation_plots(
        summary, ratios, gates, definitions, output_directory,
        inferred_title(manifest), setting["window"], product,
    )
    return [
        csv_path, ratio_path, definition_path, *time_plots, *correlation_plots,
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--division-case")
    arguments = parser.parse_args()
    for path in build(arguments.run_directory, arguments.config, arguments.division_case):
        print(path)


if __name__ == "__main__":
    main()
