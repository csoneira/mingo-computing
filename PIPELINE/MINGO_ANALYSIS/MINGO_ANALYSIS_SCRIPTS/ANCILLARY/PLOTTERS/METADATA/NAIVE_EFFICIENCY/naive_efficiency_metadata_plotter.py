#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/METADATA/NAIVE_EFFICIENCY/naive_efficiency_metadata_plotter.py
Purpose: Plot Task 2 naive-efficiency metadata time series (counts and per-plane efficiencies).
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-04-16
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/METADATA/NAIVE_EFFICIENCY/naive_efficiency_metadata_plotter.py [options]
Inputs: task_2_metadata_naive_efficiency.csv
Outputs: PNG figures under PLOTS/.
Notes: Plot time is extracted from filename_base (DAQ basename timestamp).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import re

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SCRIPT_PATH = Path(__file__).resolve()
FILENAME_TIMESTAMP_PATTERN = re.compile(r"mi0\d(\d{11})$", re.IGNORECASE)


def detect_repo_root() -> Path:
    for parent in SCRIPT_PATH.parents:
        if (parent / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS").is_dir() and (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file():
            return parent
    raise RuntimeError(f"Could not locate repository root from {SCRIPT_PATH}")


REPO_ROOT = detect_repo_root()
DEFAULT_INPUT_CSV = (
    REPO_ROOT
    / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
    / "MINGO01"
    / "STAGE_1"
    / "EVENT_DATA"
    / "STEP_1"
    / "TASK_2"
    / "METADATA"
    / "task_2_metadata_naive_efficiency.csv"
)
DEFAULT_OUTPUT_DIR = SCRIPT_PATH.parent / "PLOTS"


COUNT_COLUMNS = (
    "good_charge_rows_1234",
    "good_charge_rows_123",
    "good_charge_rows_234",
    "good_charge_rows_124",
    "good_charge_rows_134",
)


def _parse_timestamp_from_filename_base(filename_base: str) -> datetime | None:
    if not filename_base:
        return None

    stem = Path(filename_base).stem.strip()
    if not stem:
        return None

    match = FILENAME_TIMESTAMP_PATTERN.search(stem)
    if match:
        digits = match.group(1)
    else:
        digits = "".join(ch for ch in stem if ch.isdigit())
        if len(digits) < 11:
            return None
        digits = digits[-11:]

    try:
        year = 2000 + int(digits[0:2])
        day_of_year = int(digits[2:5])
        hour = int(digits[5:7])
        minute = int(digits[7:9])
        second = int(digits[9:11])
    except ValueError:
        return None

    if not (1 <= day_of_year <= 366):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return None

    base = datetime(year, 1, 1)
    return base + timedelta(
        days=day_of_year - 1,
        hours=hour,
        minutes=minute,
        seconds=second,
    )


def load_naive_efficiency_dataframe(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    required_columns = {"filename_base", *COUNT_COLUMNS}
    missing_columns = sorted(required_columns.difference(df.columns))
    if missing_columns:
        raise ValueError(
            "Missing required columns in naive-efficiency metadata CSV: "
            + ", ".join(missing_columns)
        )

    for column_name in COUNT_COLUMNS:
        df[column_name] = pd.to_numeric(df[column_name], errors="coerce")

    df["plot_time"] = df["filename_base"].astype(str).map(_parse_timestamp_from_filename_base)

    df = df.dropna(subset=["plot_time"]).copy()
    if df.empty:
        raise ValueError("No valid basename timestamps found in naive-efficiency CSV.")

    df = df.sort_values("plot_time").reset_index(drop=True)
    return df


def add_naive_efficiency_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    four_plane = pd.to_numeric(out["good_charge_rows_1234"], errors="coerce").to_numpy(dtype=float)

    missing_counts_by_plane = {
        1: pd.to_numeric(out["good_charge_rows_234"], errors="coerce").to_numpy(dtype=float),
        2: pd.to_numeric(out["good_charge_rows_134"], errors="coerce").to_numpy(dtype=float),
        3: pd.to_numeric(out["good_charge_rows_124"], errors="coerce").to_numpy(dtype=float),
        4: pd.to_numeric(out["good_charge_rows_123"], errors="coerce").to_numpy(dtype=float),
    }

    valid_denominator = np.isfinite(four_plane) & (four_plane > 0)

    for plane, missing_counts in missing_counts_by_plane.items():
        efficiency = np.full(len(out), np.nan, dtype=float)
        efficiency[valid_denominator] = 1.0 - (
            missing_counts[valid_denominator] / four_plane[valid_denominator]
        )
        out[f"naive_eff_plane_{plane}"] = efficiency

    return out


def configure_matplotlib_style() -> None:
    plt.style.use("default")


def _format_time_axis(ax: plt.Axes) -> None:
    locator = mdates.AutoDateLocator(minticks=4, maxticks=10)
    formatter = mdates.ConciseDateFormatter(locator)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)


def plot_counts_time_series(df: pd.DataFrame, output_path: Path, station_label: str, show: bool) -> None:
    fig, ax = plt.subplots(figsize=(12, 6), constrained_layout=True)

    style = {
        "good_charge_rows_1234": ("1234", "black"),
        "good_charge_rows_123": ("123", "tab:blue"),
        "good_charge_rows_234": ("234", "tab:orange"),
        "good_charge_rows_124": ("124", "tab:green"),
        "good_charge_rows_134": ("134", "tab:red"),
    }

    for column_name, (label, color) in style.items():
        y_values = pd.to_numeric(df[column_name], errors="coerce")
        ax.plot(
            df["plot_time"],
            y_values,
            label=label,
            color=color,
            linewidth=1.3,
            marker="o",
            markersize=2.5,
            alpha=0.9,
        )

    ax.set_title(f"Task 2 naive good-charge counts by topology ({station_label})")
    ax.set_xlabel("Time")
    ax.set_ylabel("Rows")
    ax.grid(True, alpha=0.3)
    ax.legend(title="Topology", ncol=5, fontsize=9)
    _format_time_axis(ax)

    fig.savefig(output_path, dpi=180)
    if show:
        plt.show()
    plt.close(fig)


def plot_efficiency_time_series(df: pd.DataFrame, output_path: Path, station_label: str, show: bool) -> None:
    fig, ax = plt.subplots(figsize=(12, 6), constrained_layout=True)

    style = {
        "naive_eff_plane_1": ("Plane 1 (from 234)", "tab:blue"),
        "naive_eff_plane_2": ("Plane 2 (from 134)", "tab:orange"),
        "naive_eff_plane_3": ("Plane 3 (from 124)", "tab:green"),
        "naive_eff_plane_4": ("Plane 4 (from 123)", "tab:red"),
    }

    for column_name, (label, color) in style.items():
        y_values = pd.to_numeric(df[column_name], errors="coerce")
        ax.plot(
            df["plot_time"],
            y_values,
            label=label,
            color=color,
            linewidth=1.3,
            marker="o",
            markersize=2.5,
            alpha=0.9,
        )

    ax.axhline(1.0, color="black", linestyle="--", linewidth=1.0, alpha=0.6)
    ax.set_title(
        "Task 2 naive per-plane efficiencies: "
        "1 - (three-plane / four-plane) "
        f"({station_label})"
    )
    ax.set_xlabel("Time")
    ax.set_ylabel("Naive efficiency")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9)
    _format_time_axis(ax)

    finite_eff = np.concatenate(
        [
            pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
            for col in style
        ]
    )
    finite_eff = finite_eff[np.isfinite(finite_eff)]
    if finite_eff.size > 0:
        y_min = min(0.0, float(np.nanmin(finite_eff)) - 0.05)
        y_max = max(1.0, float(np.nanmax(finite_eff)) + 0.05)
        if y_max <= y_min:
            y_max = y_min + 0.1
        ax.set_ylim(y_min, y_max)

    fig.savefig(output_path, dpi=180)
    if show:
        plt.show()
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot naive-efficiency metadata time series for Task 2: "
            "(1) topology counts and (2) per-plane naive efficiencies."
        )
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=DEFAULT_INPUT_CSV,
        help=f"Path to task_2_metadata_naive_efficiency.csv (default: {DEFAULT_INPUT_CSV})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for output PNG files (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--station-label",
        type=str,
        default="MINGO01",
        help="Label used in figure titles.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display figures interactively in addition to saving PNG files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_matplotlib_style()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    df = load_naive_efficiency_dataframe(args.input_csv)
    df = add_naive_efficiency_columns(df)

    counts_output_path = output_dir / "naive_efficiency_counts_timeseries.png"
    efficiency_output_path = output_dir / "naive_efficiency_per_plane_timeseries.png"

    plot_counts_time_series(df, counts_output_path, args.station_label, args.show)
    plot_efficiency_time_series(df, efficiency_output_path, args.station_label, args.show)

    print(f"Input rows used: {len(df)}")
    print(f"Saved: {counts_output_path}")
    print(f"Saved: {efficiency_output_path}")


if __name__ == "__main__":
    main()
