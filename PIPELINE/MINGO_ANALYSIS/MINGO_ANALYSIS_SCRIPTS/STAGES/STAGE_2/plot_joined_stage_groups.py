#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_2/plot_joined_stage_groups.py
Purpose: Plot grouped time-series panels for joined Stage 2 or Stage 3 station tables.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-03
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_2/plot_joined_stage_groups.py --input-csv PATH --output PATH --config PATH
Inputs: Joined stage CSV and plot config.
Outputs: One PNG with grouped time-series panels.
Notes: Shared by Stage 2 and Stage 3 builders.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Mapping, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import yaml

import sys

CURRENT_PATH = Path(__file__).resolve()
MASTER_ROOT = None
REPO_ROOT = None
for parent in CURRENT_PATH.parents:
    if parent.name == "MINGO_ANALYSIS_SCRIPTS":
        MASTER_ROOT = parent
        REPO_ROOT = parent.parents[2]
        break
if MASTER_ROOT is None:
    MASTER_ROOT = CURRENT_PATH.parents[-1]
if REPO_ROOT is None:
    REPO_ROOT = CURRENT_PATH.parents[-1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))


from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.selection_config import EventMarkerConfig, load_master_event_markers, parse_station_id


DEFAULT_PLOT_CONFIG = {
    "apply_mean_time_filter": True,
    "mean_time_filter_window": "120min",
    "apply_median_time_filter": False,
    "median_time_filter_window": "60min",
    "y_limit_band_percent_around_median": None,
}

DEFAULT_X_AXIS_CONFIG = {
    "tick_frequency": "1W",
}


def parse_time_bound(raw_value: object, *, end_of_day: bool) -> pd.Timestamp | None:
    if raw_value in (None, "", "null", "None"):
        return None

    timestamp = pd.Timestamp(raw_value)
    has_explicit_time = False
    if isinstance(raw_value, str):
        text = raw_value.strip()
        has_explicit_time = any(token in text for token in (" ", "T", ":"))
    elif isinstance(raw_value, pd.Timestamp):
        has_explicit_time = any(
            getattr(raw_value, attribute) != 0
            for attribute in ("hour", "minute", "second", "microsecond", "nanosecond")
        )
    else:
        python_dt = getattr(timestamp, "to_pydatetime", lambda: None)()
        if python_dt is not None:
            has_explicit_time = any(
                getattr(python_dt, attribute, 0) != 0
                for attribute in ("hour", "minute", "second", "microsecond")
            )

    if not has_explicit_time:
        timestamp = timestamp.normalize()
        if end_of_day:
            timestamp = timestamp + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    return timestamp


def load_yaml_mapping(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    return loaded if isinstance(loaded, dict) else {}


def load_plot_config(config_path: Path) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    raw_config = load_yaml_mapping(config_path)
    plot_config = DEFAULT_PLOT_CONFIG.copy()
    plot_config.update(raw_config.get("plot", {}))

    x_axis_config = DEFAULT_X_AXIS_CONFIG.copy()
    x_axis_config.update(raw_config.get("x_axis", {}))
    return raw_config, plot_config, x_axis_config


def parse_event_markers(raw_config: Mapping[str, object]) -> list[dict[str, object]]:
    markers: list[dict[str, object]] = []
    for index, item in enumerate(raw_config.get("event_markers", []), start=1):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"event_markers entry #{index} must be a mapping with 'date' and 'label'."
            )

        raw_date = item.get("date")
        raw_label = item.get("label")
        if raw_date is None or raw_label is None:
            raise ValueError(
                f"event_markers entry #{index} must define both 'date' and 'label'."
            )

        event_time = pd.Timestamp(str(raw_date).strip())
        label = str(raw_label).strip()
        if not label:
            raise ValueError(f"event_markers entry #{index} has an empty label.")

        markers.append({"time": event_time, "label": label})
    return sorted(markers, key=lambda item: item["time"])


def infer_station_from_path(path: Path) -> int | None:
    for part in path.parts:
        station_id = parse_station_id(part)
        if station_id is not None:
            return station_id
    return None


def merge_event_markers(
    centralized_markers: Sequence[EventMarkerConfig],
    local_markers: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = [
        {"time": marker.time, "label": marker.label}
        for marker in centralized_markers
    ]
    merged.extend({"time": item["time"], "label": str(item["label"])} for item in local_markers)

    deduped: list[dict[str, object]] = []
    seen: set[tuple[pd.Timestamp, str]] = set()
    for item in sorted(merged, key=lambda marker: marker["time"]):
        key = (pd.Timestamp(item["time"]), str(item["label"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append({"time": key[0], "label": key[1]})
    return deduped


def prepare_plot_df(dataframe: pd.DataFrame, plot_config: Mapping[str, object]) -> pd.DataFrame:
    plot_df = dataframe.sort_values("time").reset_index(drop=True).copy()
    if plot_df["time"].isna().any():
        return plot_df

    apply_mean_filter = bool(plot_config.get("apply_mean_time_filter", False))
    apply_median_filter = bool(plot_config.get("apply_median_time_filter", False))
    if apply_mean_filter and apply_median_filter:
        raise ValueError("Choose only one plotting time filter: mean or median.")
    if not apply_mean_filter and not apply_median_filter:
        return plot_df

    numeric_columns = plot_df.select_dtypes(include="number").columns
    if len(numeric_columns) == 0:
        return plot_df

    plot_df = plot_df.set_index("time")
    if apply_mean_filter:
        plot_df[numeric_columns] = plot_df[numeric_columns].rolling(
            str(plot_config["mean_time_filter_window"]),
            min_periods=1,
        ).mean()
    else:
        plot_df[numeric_columns] = plot_df[numeric_columns].rolling(
            str(plot_config["median_time_filter_window"]),
            min_periods=1,
        ).median()
    return plot_df.reset_index()


def apply_time_range_filter(dataframe: pd.DataFrame, raw_config: Mapping[str, object]) -> pd.DataFrame:
    time_range = raw_config.get("time_range", {})
    if not isinstance(time_range, Mapping):
        time_range = {}

    start = parse_time_bound(time_range.get("start"), end_of_day=False)
    end = parse_time_bound(time_range.get("end"), end_of_day=True)
    if start is None and end is None:
        return dataframe
    if start is not None and end is not None and start > end:
        raise ValueError("time_range.start must be <= time_range.end in the plot config.")

    filtered = dataframe.copy()
    if start is not None:
        filtered = filtered.loc[filtered["time"] >= start]
    if end is not None:
        filtered = filtered.loc[filtered["time"] <= end]
    if filtered.empty:
        raise ValueError("The configured plot time_range removed all rows.")
    return filtered.reset_index(drop=True)


def resolve_band_fraction(raw_value: object) -> float | None:
    if raw_value in (None, "", "null"):
        return None
    try:
        numeric = float(raw_value)
    except (TypeError, ValueError):
        return None
    if not pd.notna(numeric) or numeric <= 0:
        return None
    return numeric / 100.0 if numeric > 1.0 else numeric


def compute_axis_limits_from_median_band(
    dataframe: pd.DataFrame,
    columns: Sequence[str],
    band_fraction: float | None,
) -> tuple[float, float] | None:
    if band_fraction is None:
        return None

    lower_limits: list[float] = []
    upper_limits: list[float] = []
    for column in columns:
        if column not in dataframe.columns:
            continue
        series = pd.to_numeric(dataframe[column], errors="coerce").replace([float("inf"), float("-inf")], pd.NA).dropna()
        if series.empty:
            continue
        median_value = float(series.median())
        scale = abs(median_value)
        if scale == 0:
            series_min = float(series.min())
            series_max = float(series.max())
            scale = max(abs(series_max - series_min) / 2.0, 1e-9)
        band = scale * band_fraction
        lower_limits.append(median_value - band)
        upper_limits.append(median_value + band)

    if not lower_limits or not upper_limits:
        return None

    lower = min(lower_limits)
    upper = max(upper_limits)
    if not pd.notna(lower) or not pd.notna(upper) or lower >= upper:
        return None
    return lower, upper


def apply_axis_limit_band(
    axis: plt.Axes,
    dataframe: pd.DataFrame,
    columns: Sequence[str],
    band_fraction: float | None,
) -> None:
    limits = compute_axis_limits_from_median_band(dataframe, columns, band_fraction)
    if limits is None:
        return
    axis.set_ylim(*limits)


def plot_lines(
    axis: plt.Axes,
    dataframe: pd.DataFrame,
    columns: Sequence[str],
    title: str,
    ylabel: str,
    *,
    y_limit_band_fraction: float | None = None,
) -> None:
    present_columns = [column for column in columns if column in dataframe.columns]
    for column in present_columns:
        axis.plot(dataframe["time"], dataframe[column], label=column, linewidth=0.8)
    axis.set_title(title)
    axis.set_ylabel(ylabel)
    apply_axis_limit_band(axis, dataframe, present_columns, y_limit_band_fraction)
    if present_columns:
        axis.legend(fontsize=8, loc="upper right")
    axis.grid(True, alpha=0.25)


def build_time_tick_locator(tick_frequency: object):
    if tick_frequency in (None, "", "none"):
        return None

    offset = pd.tseries.frequencies.to_offset(str(tick_frequency))
    if isinstance(offset, pd.offsets.Minute):
        return mdates.MinuteLocator(interval=offset.n)
    if isinstance(offset, pd.offsets.Hour):
        return mdates.HourLocator(interval=offset.n)
    if isinstance(offset, pd.offsets.Day):
        return mdates.DayLocator(interval=offset.n)
    if isinstance(offset, pd.offsets.Week):
        return mdates.WeekdayLocator(interval=offset.n)

    raise ValueError(
        "Unsupported x-axis tick_frequency. Use None or values like '30min', '6h', '1D', or '1W'."
    )


def configure_time_axis(axis: plt.Axes, tick_frequency: object) -> None:
    axis.set_xlabel("time")
    locator = build_time_tick_locator(tick_frequency)
    if locator is None:
        return
    axis.xaxis.set_major_locator(locator)
    axis.xaxis.set_major_formatter(mdates.AutoDateFormatter(locator))


def add_event_markers(axes: Sequence[plt.Axes], event_markers: Sequence[Mapping[str, object]]) -> None:
    if not event_markers:
        return

    x_limits = [axis.get_xlim() for axis in axes]
    label_levels = [0.98, 0.86, 0.74]
    top_axis = axes[0]
    for index, marker in enumerate(event_markers):
        level = label_levels[index % len(label_levels)]
        for axis in axes:
            axis.axvline(
                marker["time"],
                color="black",
                linestyle="--",
                linewidth=0.9,
                alpha=0.7,
            )
        top_axis.annotate(
            str(marker["label"]),
            xy=(marker["time"], level),
            xycoords=("data", "axes fraction"),
            xytext=(3, 0),
            textcoords="offset points",
            rotation=90,
            va="top",
            ha="left",
            fontsize=8,
            color="black",
            bbox={
                "boxstyle": "round,pad=0.15",
                "facecolor": "white",
                "edgecolor": "none",
                "alpha": 0.7,
            },
        )
    for axis, limits in zip(axes, x_limits):
        axis.set_xlim(limits)


def generate_joined_groups_plot(
    input_csv_path: Path,
    output_path: Path,
    config_path: Path,
    *,
    rate_column: str = "count",
    rate_title: str = "Count",
    rate_ylabel: str = "Rate",
) -> Path:
    raw_config, plot_config, x_axis_config = load_plot_config(config_path)
    station_id = infer_station_from_path(input_csv_path)
    centralized_event_markers = load_master_event_markers(station=station_id)
    local_event_markers = parse_event_markers(raw_config)
    event_markers = merge_event_markers(centralized_event_markers, local_event_markers)
    y_limit_band_fraction = resolve_band_fraction(
        plot_config.get("y_limit_band_percent_around_median")
    )

    dataframe = pd.read_csv(input_csv_path, parse_dates=["time"])
    dataframe = apply_time_range_filter(dataframe, raw_config)
    plot_df = prepare_plot_df(dataframe, plot_config)

    fig, axes = plt.subplots(7, 1, figsize=(16, 20), sharex=True)
    axes = axes.ravel()

    axis = axes[0]
    if "temp_lab" in plot_df.columns:
        axis.plot(plot_df["time"], plot_df["temp_lab"], color="tab:red", label="temp_lab", linewidth=0.8)
    axis.set_title("Lab Temp / Pressure")
    axis.set_ylabel("Temp")
    axis.grid(True, alpha=0.25)
    axis_twin = axis.twinx()
    if "pressure_lab" in plot_df.columns:
        axis_twin.plot(plot_df["time"], plot_df["pressure_lab"], color="tab:blue", label="pressure_lab", linewidth=0.8)
    axis_twin.set_ylabel("Pressure")
    lines = axis.get_lines() + axis_twin.get_lines()
    if lines:
        axis.legend(lines, [line.get_label() for line in lines], fontsize=8, loc="upper right")

    axis = axes[1]
    if "temp_ground" in plot_df.columns:
        axis.plot(plot_df["time"], plot_df["temp_ground"], label="temp_ground", linewidth=0.8)
    if "temp_100mbar" in plot_df.columns:
        axis.plot(plot_df["time"], plot_df["temp_100mbar"], label="temp_100mbar", linewidth=0.8)
    axis.set_title("Ground / 100mbar / Height")
    axis.set_ylabel("Temp")
    axis.grid(True, alpha=0.25)
    axis_twin = axis.twinx()
    if "height_100mbar" in plot_df.columns:
        axis_twin.plot(plot_df["time"], plot_df["height_100mbar"], color="tab:green", label="height_100mbar", linewidth=0.8)
    axis_twin.set_ylabel("Height")
    lines = axis.get_lines() + axis_twin.get_lines()
    if lines:
        axis.legend(lines, [line.get_label() for line in lines], fontsize=8, loc="upper right")

    plot_lines(axes[2], plot_df, ["Q_event_mean"], "Q_event_mean", "Q")
    plot_lines(axes[3], plot_df, [rate_column], rate_title, rate_ylabel, y_limit_band_fraction=y_limit_band_fraction)
    plot_lines(axes[4], plot_df, ["High"], "High", "Rate", y_limit_band_fraction=y_limit_band_fraction)
    plot_lines(
        axes[5],
        plot_df,
        ["Mid-N", "Mid-NE", "Mid-E", "Mid-SE", "Mid-S", "Mid-SW", "Mid-W", "Mid-NW"],
        "Mids",
        "Rate",
        y_limit_band_fraction=y_limit_band_fraction,
    )
    plot_lines(axes[6], plot_df, ["Low-N", "Low-E", "Low-S", "Low-W"], "Lows", "Rate", y_limit_band_fraction=y_limit_band_fraction)

    add_event_markers(axes, event_markers)
    configure_time_axis(axes[-1], x_axis_config.get("tick_frequency"))

    fig.autofmt_xdate()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot grouped time-series panels for a joined stage table.")
    parser.add_argument("--input-csv", required=True, help="Path to the joined CSV file.")
    parser.add_argument("--output", required=True, help="Path to the output PNG.")
    parser.add_argument("--config", required=True, help="Path to the plot YAML config.")
    parser.add_argument("--rate-column", default="count", help="Column to use in the main rate panel.")
    parser.add_argument("--rate-title", default="Count", help="Title to use in the main rate panel.")
    parser.add_argument("--rate-ylabel", default="Rate", help="Y-axis label for the main rate panel.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = generate_joined_groups_plot(
        Path(args.input_csv).expanduser(),
        Path(args.output).expanduser(),
        Path(args.config).expanduser(),
        rate_column=str(args.rate_column),
        rate_title=str(args.rate_title),
        rate_ylabel=str(args.rate_ylabel),
    )
    print(f"Saved {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
