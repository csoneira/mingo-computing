#!/usr/bin/env python3
"""Build an enabled-gate comparison from Fourier-filtered plane efficiencies."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from test_3_configurable_event_gates import (
    write_corrected_rate_reduced_field_comparison,
)


SOURCE_DIRECTORY = "ENABLED_GATE_COMPARISON"
FOURIER_DIRECTORY = "ENVIRONMENT_FREQUENCY_EFFICIENCY_CORRECTION"
OUTPUT_DIRECTORY = "ENABLED_GATE_COMPARISON_FOURIER"


def inferred_title(run_directory: Path) -> str:
    manifest_path = run_directory / "selected_files.csv"
    if not manifest_path.is_file():
        return f"{run_directory.parent.parent.parent.name} | Fourier-filtered efficiencies"
    manifest = pd.read_csv(manifest_path)
    acquired = pd.to_datetime(manifest["acquisition_datetime"], errors="coerce").dropna()
    station = (
        str(manifest["station"].dropna().iloc[0])
        if "station" in manifest and bool(manifest["station"].notna().any())
        else run_directory.parent.parent.parent.name
    )
    if acquired.empty:
        return f"{station} | {len(manifest)} consecutive files"
    return (
        f"{station} | {len(manifest)} consecutive files | "
        f"{acquired.min():%Y-%m-%d %H:%M:%S} to "
        f"{acquired.max():%Y-%m-%d %H:%M:%S}"
    )


def fourier_comparison_frame(
    comparison_path: Path,
    correction_path: Path,
) -> pd.DataFrame:
    comparison = pd.read_csv(comparison_path, dtype={"gate_code": str})
    correction = pd.read_csv(correction_path, dtype={"gate_code": str})
    comparison["window_start"] = pd.to_datetime(
        comparison["window_start"], errors="coerce",
    )
    correction["window_start"] = pd.to_datetime(
        correction["window_start"], errors="coerce",
    )
    if "efficiency_product_mode" not in correction:
        correction["efficiency_product_mode"] = "all_planes"
    if "efficiency_product_plane_numbers" not in correction:
        correction["efficiency_product_plane_numbers"] = "1,2,3,4"

    keys = ["window_start", "gate_code"]
    filtered_columns = [
        *(f"plane_{plane}_efficiency_filtered" for plane in range(1, 5)),
        "filtered_efficiency_product",
        "environment_frequency_corrected_1234_rate_hz",
        "efficiency_product_mode",
        "efficiency_product_plane_numbers",
    ]
    missing = sorted(set(keys + filtered_columns) - set(correction.columns))
    if missing:
        raise ValueError(
            "Fourier efficiency-correction CSV is missing columns: "
            + ", ".join(missing)
        )
    if comparison.duplicated(keys).any() or correction.duplicated(keys).any():
        raise ValueError("Gate/window keys must be unique in both input CSVs")

    derived_columns = [
        "uncorrected_1234_rate_reference_hz",
        "relative_uncorrected_1234_rate",
        "corrected_1234_rate_reference_hz",
        "relative_corrected_1234_rate",
        "reduced_field_td",
    ]
    result = comparison.drop(
        columns=[column for column in derived_columns if column in comparison],
    ).merge(
        correction[keys + filtered_columns],
        on=keys,
        how="left",
        validate="one_to_one",
    )
    if result[filtered_columns].isna().all(axis=1).any():
        unmatched = int(result[filtered_columns].isna().all(axis=1).sum())
        raise ValueError(
            f"{unmatched} enabled-gate comparison row(s) have no Fourier correction"
        )

    for plane in range(1, 5):
        result[f"plane_{plane}_efficiency"] = result.pop(
            f"plane_{plane}_efficiency_filtered"
        )
    result["efficiency_product"] = result.pop("filtered_efficiency_product")
    result["corrected_1234_rate_hz"] = result.pop(
        "environment_frequency_corrected_1234_rate_hz"
    )
    total_rate = pd.to_numeric(result["total_gate_rate_hz"], errors="coerce")
    efficiency_product = pd.to_numeric(
        result["efficiency_product"], errors="coerce",
    )
    result["corrected_total_gate_rate_hz"] = np.divide(
        total_rate.to_numpy(dtype=float),
        efficiency_product.to_numpy(dtype=float),
        out=np.full(len(result), np.nan),
        where=np.isfinite(efficiency_product.to_numpy(dtype=float))
        & (efficiency_product.to_numpy(dtype=float) > 0),
    )
    return result


def efficiency_product_label(comparison: pd.DataFrame) -> str:
    modes = comparison["efficiency_product_mode"].dropna().astype(str).unique()
    if len(modes) != 1:
        raise ValueError("Fourier comparison contains inconsistent efficiency-product modes")
    return (
        "all four plane efficiencies"
        if modes[0] == "all_planes"
        else "squared inner-plane product (plane 2 × plane 3)²"
    )


def write_overlay_plots(
    comparison: pd.DataFrame,
    output_directory: Path,
    title: str,
    window: pd.Timedelta,
) -> tuple[Path, Path]:
    colors = plt.get_cmap("tab10").colors
    gate_codes = list(comparison["gate_code"].drop_duplicates())

    efficiency_path = output_directory / "enabled_gate_plane_efficiencies.png"
    efficiency_figure, efficiency_axes = plt.subplots(
        4, 1, figsize=(16, 14), sharex=True, constrained_layout=True,
    )
    for gate_index, gate_code in enumerate(gate_codes):
        gate_rows = comparison.loc[
            comparison["gate_code"].eq(gate_code)
        ].sort_values("window_start")
        gate_label = str(gate_rows["gate_label"].iloc[0])
        label = f"{gate_label} [{gate_code}]"
        for plane, axis in enumerate(efficiency_axes, 1):
            axis.plot(
                gate_rows["window_start"],
                gate_rows[f"plane_{plane}_efficiency"],
                color=colors[gate_index % len(colors)],
                marker=".",
                markersize=3,
                linewidth=1.1,
                label=label,
            )
    for plane, axis in enumerate(efficiency_axes, 1):
        axis.set(ylabel=f"Plane {plane}\nefficiency", ylim=(-0.02, 1.02))
        axis.grid(True, alpha=0.25)
    efficiency_axes[0].legend(ncols=min(4, len(gate_codes)), fontsize=8)
    efficiency_axes[-1].set_xlabel("Time")
    efficiency_figure.suptitle(
        f"{title}\nFourier-filtered plane efficiency by enabled gate | "
        f"accumulation={window}",
        fontsize=14,
    )
    efficiency_figure.autofmt_xdate()
    efficiency_figure.savefig(efficiency_path, dpi=160)
    plt.close(efficiency_figure)

    metrics_path = output_directory / "enabled_gate_rate_efficiency_product.png"
    metrics_figure, metrics_axes = plt.subplots(
        3, 1, figsize=(16, 12), sharex=True, constrained_layout=True,
    )
    product_label = efficiency_product_label(comparison)
    metric_specs = (
        (
            "corrected_total_gate_rate_hz",
            "Corrected total gate rate [Hz]",
            "Total selected-event rate × (1 / Fourier-filtered efficiency product)",
        ),
        (
            "efficiency_product",
            "Efficiency product",
            f"Product of {product_label}, Fourier-filtered",
        ),
        (
            "corrected_1234_rate_hz",
            "Corrected 1234 rate [Hz]",
            "1234 rate × (1 / Fourier-filtered efficiency product)",
        ),
    )
    for gate_index, gate_code in enumerate(gate_codes):
        gate_rows = comparison.loc[
            comparison["gate_code"].eq(gate_code)
        ].sort_values("window_start")
        gate_label = str(gate_rows["gate_label"].iloc[0])
        label = f"{gate_label} [{gate_code}]"
        for axis, (column, _, _) in zip(
            metrics_axes, metric_specs, strict=True,
        ):
            axis.plot(
                gate_rows["window_start"],
                gate_rows[column],
                color=colors[gate_index % len(colors)],
                marker=".",
                markersize=3,
                linewidth=1.1,
                label=label,
            )
    for axis, (_, ylabel, axis_title) in zip(
        metrics_axes, metric_specs, strict=True,
    ):
        axis.set(ylabel=ylabel, title=axis_title)
        axis.grid(True, alpha=0.25)
    metrics_axes[0].legend(ncols=min(4, len(gate_codes)), fontsize=8)
    metrics_axes[-1].set_xlabel("Time")
    metrics_figure.suptitle(
        f"{title}\nFourier enabled-gate comparison | accumulation={window} | "
        f"efficiency product={product_label} | "
        "rate denominator=observed timestamp-seconds",
        fontsize=14,
    )
    metrics_figure.autofmt_xdate()
    metrics_figure.savefig(metrics_path, dpi=160)
    plt.close(metrics_figure)
    return efficiency_path, metrics_path


def build(run_directory: Path) -> list[Path]:
    run_directory = run_directory.resolve()
    source_path = run_directory / SOURCE_DIRECTORY / "enabled_gate_comparison.csv"
    correction_path = (
        run_directory / FOURIER_DIRECTORY / "filtered_efficiency_correction.csv"
    )
    environment_path = (
        run_directory / "00_ENVIRONMENT_CONTEXT" / "00_environment_data.csv"
    )
    for path in (source_path, correction_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    output_directory = run_directory / OUTPUT_DIRECTORY
    output_directory.mkdir(parents=False, exist_ok=False)
    comparison = fourier_comparison_frame(source_path, correction_path)
    starts = pd.to_datetime(comparison["window_start"], errors="coerce")
    ends = pd.to_datetime(comparison["window_end"], errors="coerce")
    windows = (ends - starts).dropna()
    if windows.empty:
        raise ValueError("Cannot infer the comparison accumulation timespan")
    window = windows.mode().iloc[0]
    title = inferred_title(run_directory)

    efficiency_path, metrics_path = write_overlay_plots(
        comparison, output_directory, title, window,
    )
    comparison, normalized_path = write_corrected_rate_reduced_field_comparison(
        comparison,
        window,
        environment_path if environment_path.is_file() else None,
        output_directory,
        f"{title} | Fourier-filtered efficiencies",
    )
    csv_path = output_directory / "enabled_gate_comparison.csv"
    comparison.to_csv(csv_path, index=False)
    return [efficiency_path, metrics_path, normalized_path, csv_path]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_directory",
        type=Path,
        help="TEST_3_CONFIGURABLE_GATES run directory containing both source CSVs",
    )
    arguments = parser.parse_args()
    for path in build(arguments.run_directory):
        print(path)


if __name__ == "__main__":
    main()
