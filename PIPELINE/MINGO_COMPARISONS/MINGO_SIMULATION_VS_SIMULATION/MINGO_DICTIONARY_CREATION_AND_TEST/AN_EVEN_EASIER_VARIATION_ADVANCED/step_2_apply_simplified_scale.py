#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import DEFAULT_CONFIG_PATH, REPO_ROOT, cfg_path, ensure_output_dirs, get_trigger_type_selection, load_config

if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.selection_config import load_master_event_markers, parse_station_id


def _configure_logging() -> None:
    logging.basicConfig(format="[%(levelname)s] STEP_2 - %(message)s", level=logging.INFO, force=True)


def _step2_config(config: dict[str, Any]) -> dict[str, Any]:
    step2_config = config.get("step2", {})
    if not isinstance(step2_config, dict):
        return {}
    return step2_config


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)


def _resolve_efficiency_reference_columns(config: dict[str, Any]) -> list[str]:
    step2_config = _step2_config(config)

    raw_planes = step2_config.get("efficiency_reference_planes", [2, 3])
    if isinstance(raw_planes, str):
        text = raw_planes.strip()
        if not text:
            raw_planes = [2, 3]
        else:
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                decoded = [piece.strip() for piece in text.split(",") if piece.strip()]
            raw_planes = decoded

    if isinstance(raw_planes, (int, float)) and not isinstance(raw_planes, bool):
        raw_planes = [int(raw_planes)]

    if not isinstance(raw_planes, (list, tuple)) or not raw_planes:
        raise ValueError("step2.efficiency_reference_planes must be a non-empty list of plane numbers between 1 and 4.")

    planes: list[int] = []
    for value in raw_planes:
        plane = int(value)
        if plane < 1 or plane > 4:
            raise ValueError(
                "step2.efficiency_reference_planes contains an invalid plane index "
                f"{plane}. Valid values are 1, 2, 3, 4."
            )
        if plane not in planes:
            planes.append(plane)

    return [f"eff_empirical_{plane}" for plane in planes]


def _resolve_efficiency_reference_mode(config: dict[str, Any]) -> str:
    step2_config = _step2_config(config)
    raw_mode = str(step2_config.get("efficiency_reference_mode", "mean_power4")).strip().lower()
    aliases = {
        "mean": "mean_power4",
        "average": "mean_power4",
        "avg": "mean_power4",
        "mean_power4": "mean_power4",
        "product": "product",
        "prod": "product",
    }
    mode = aliases.get(raw_mode, raw_mode)
    if mode not in {"mean_power4", "product"}:
        raise ValueError(
            "step2.efficiency_reference_mode must be one of: mean_power4, product."
        )
    return mode


def _resolve_efficiency_reference_min(config: dict[str, Any]) -> float | None:
    step2_config = _step2_config(config)

    raw_min = step2_config.get("efficiency_reference_min")
    if raw_min in (None, "", "null", "None"):
        return None

    minimum = float(raw_min)
    if minimum < 0.0:
        raise ValueError("step2.efficiency_reference_min must be >= 0.")
    return minimum


def _resolve_efficiency_plot_ylim(config: dict[str, Any]) -> tuple[float | None, float | None]:
    step2_config = _step2_config(config)
    raw_ylim = step2_config.get("efficiency_plot_ylim", [None, 1.0])

    if isinstance(raw_ylim, str):
        text = raw_ylim.strip()
        if not text:
            raw_ylim = [None, 1.0]
        else:
            raw_ylim = json.loads(text)

    if not isinstance(raw_ylim, (list, tuple)) or len(raw_ylim) != 2:
        raise ValueError("step2.efficiency_plot_ylim must be a two-element list like [null, 1.0].")

    limits: list[float | None] = []
    for value in raw_ylim:
        if value in (None, "", "null", "None"):
            limits.append(None)
        else:
            limits.append(float(value))

    bottom, top = limits
    if bottom is not None and top is not None and bottom >= top:
        raise ValueError("step2.efficiency_plot_ylim must satisfy bottom < top when both limits are set.")
    return bottom, top


def _resolve_plot_moving_average(config: dict[str, Any]) -> tuple[bool, int]:
    step2_config = _step2_config(config)
    enabled = _normalize_bool(
        step2_config.get(
            "plot_apply_moving_average",
            step2_config.get("efficiency_plot_apply_moving_average", False),
        )
    )
    kernel = int(
        step2_config.get(
            "plot_moving_average_kernel",
            step2_config.get("efficiency_plot_moving_average_kernel", 5),
        )
    )
    if kernel < 1:
        raise ValueError("step2.plot_moving_average_kernel must be >= 1.")
    return enabled, kernel


def _resolve_scale_factor_smoothing(config: dict[str, Any]) -> dict[str, Any]:
    step2_config = _step2_config(config)
    enabled = _normalize_bool(step2_config.get("apply_scale_factor_smoothing", False))
    method = str(step2_config.get("scale_factor_smoothing_method", "moving_average")).strip().lower()
    kernel = int(step2_config.get("scale_factor_smoothing_kernel", 5))
    if method != "moving_average":
        raise ValueError("step2.scale_factor_smoothing_method currently supports only 'moving_average'.")
    if kernel < 1:
        raise ValueError("step2.scale_factor_smoothing_kernel must be >= 1.")
    return {
        "enabled": enabled,
        "method": method,
        "kernel": kernel,
    }


def _scale_factor_smoothing_label(settings: dict[str, Any]) -> str | None:
    if not bool(settings.get("enabled")):
        return None
    kernel = int(settings.get("kernel", 1))
    if kernel <= 1:
        return None
    return f"moving average n={kernel}"


def _resolve_selected_series_plot_metadata(config: dict[str, Any]) -> dict[str, str]:
    selection = get_trigger_type_selection(config)
    source_column = str(selection["selected_source_rate_column"])
    display_label = str(selection.get("selected_display_label") or source_column)

    if source_column.endswith("_count"):
        return {
            "source_column": source_column,
            "display_label": display_label,
            "quantity_title": "count",
            "y_label": "Count",
            "selected_label": f"Original {display_label}",
            "corrected_label": "Corrected count",
            "scatter_title": "Count vs eff_reference",
        }
    if source_column.endswith("_hz"):
        return {
            "source_column": source_column,
            "display_label": display_label,
            "quantity_title": "rate",
            "y_label": "Rate [Hz]",
            "selected_label": f"Original {display_label}",
            "corrected_label": "Corrected rate",
            "scatter_title": "Rate vs eff_reference",
        }
    return {
        "source_column": source_column,
        "display_label": display_label,
        "quantity_title": "value",
        "y_label": display_label,
        "selected_label": f"Original {display_label}",
        "corrected_label": f"Corrected {display_label}",
        "scatter_title": f"{display_label} vs eff_reference",
    }


def _resolve_station_id(config: dict[str, Any]) -> int | None:
    step5_config = config.get("step5", {})
    if not isinstance(step5_config, dict):
        return None
    return parse_station_id(step5_config.get("station"))


def _load_event_markers(config: dict[str, Any]) -> list[dict[str, object]]:
    station_id = _resolve_station_id(config)
    return [
        {"time": marker.time, "label": marker.label}
        for marker in load_master_event_markers(station=station_id)
    ]


def _add_event_markers(
    ax: plt.Axes,
    x_values: pd.Series,
    event_markers: list[dict[str, object]],
) -> None:
    if not event_markers or not pd.api.types.is_datetime64_any_dtype(x_values):
        return

    valid_times = pd.to_datetime(x_values, errors="coerce", utc=True).dropna()
    if valid_times.empty:
        return
    valid_times = valid_times.dt.tz_convert(None)
    min_time = valid_times.min()
    max_time = valid_times.max()

    label_levels = [0.98, 0.86, 0.74]
    for index, marker in enumerate(event_markers):
        event_time = pd.to_datetime(marker["time"], errors="coerce", utc=True)
        if pd.isna(event_time):
            continue
        event_time = event_time.tz_convert(None)
        if event_time < min_time or event_time > max_time:
            continue
        ax.axvline(
            event_time,
            color="black",
            linestyle="--",
            linewidth=0.9,
            alpha=0.7,
        )
        ax.annotate(
            str(marker["label"]),
            xy=(event_time, label_levels[index % len(label_levels)]),
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


def _validate_columns(dataframe: pd.DataFrame, reference_columns: list[str]) -> None:
    required = ["selected_rate_hz", *reference_columns]
    missing = sorted(column for column in required if column not in dataframe.columns)
    if missing:
        raise ValueError(
            "Input data is missing required columns: " + ", ".join(missing)
        )


def _reference_mode_label(reference_columns: list[str], reference_mode: str) -> str:
    selected_planes_label = ", ".join(column.replace("eff_empirical_", "P") for column in reference_columns)
    if reference_mode == "product":
        return f"product({selected_planes_label})"
    return f"mean({selected_planes_label})^4"


def _apply_simplified_scale(
    dataframe: pd.DataFrame,
    reference_columns: list[str],
    reference_mode: str,
) -> pd.DataFrame:
    work = dataframe.copy()
    reference_frame = work[reference_columns].apply(pd.to_numeric, errors="coerce")
    if reference_mode == "product":
        work["eff_reference"] = reference_frame.prod(axis=1, min_count=len(reference_columns))
    else:
        work["eff_reference"] = reference_frame.mean(axis=1)
    work["scale_factor_raw"] = np.where(
        pd.to_numeric(work["eff_reference"], errors="coerce") > 0.0,
        (
            1.0 / work["eff_reference"]
            if reference_mode == "product"
            else 1.0 / (work["eff_reference"] ** 4)
        ),
        np.nan,
    )
    work["scale_factor_smoothed"] = pd.to_numeric(work["scale_factor_raw"], errors="coerce")
    work["scale_factor"] = pd.to_numeric(work["scale_factor_raw"], errors="coerce")
    work["eff_reference_mode"] = reference_mode
    work["corrected_rate_hz"] = work["selected_rate_hz"].astype(float) * work["scale_factor"].astype(float)
    return work


def _apply_scale_factor_smoothing(dataframe: pd.DataFrame, settings: dict[str, Any]) -> pd.DataFrame:
    out = dataframe.copy()
    raw_scale = pd.to_numeric(out["scale_factor_raw"], errors="coerce")
    out["scale_factor_raw"] = raw_scale
    if not bool(settings.get("enabled")) or int(settings.get("kernel", 1)) <= 1:
        out["scale_factor_smoothed"] = raw_scale
        out["scale_factor"] = raw_scale
        return out

    work = out.copy()
    work["__row_id"] = np.arange(len(work), dtype=int)
    ordered = _sort_by_time_axis_for_plotting(work)
    ordered_raw = pd.to_numeric(ordered["scale_factor_raw"], errors="coerce")
    ordered_smoothed = ordered_raw.rolling(
        window=int(settings["kernel"]),
        min_periods=1,
        center=True,
    ).mean()
    ordered_smoothed = ordered_smoothed.where(ordered_raw.notna(), np.nan)

    smoothed = pd.Series(np.nan, index=out.index, dtype=float)
    row_ids = ordered["__row_id"].to_numpy(dtype=int)
    smoothed.iloc[row_ids] = ordered_smoothed.to_numpy(dtype=float)
    out["scale_factor_smoothed"] = smoothed
    out["scale_factor"] = smoothed
    return out


def _filter_by_eff_reference_min(dataframe: pd.DataFrame, minimum: float | None) -> tuple[pd.DataFrame, int]:
    if minimum is None:
        return dataframe.copy(), 0
    keep_mask = dataframe["eff_reference"].astype(float) >= float(minimum)
    filtered = dataframe.loc[keep_mask].copy()
    removed_rows = int((~keep_mask).sum())
    return filtered, removed_rows


def _resolve_time_axis(dataframe: pd.DataFrame) -> tuple[pd.Series, str]:
    if "file_timestamp_utc" in dataframe.columns:
        parsed = pd.to_datetime(dataframe["file_timestamp_utc"], errors="coerce", utc=True)
        if parsed.notna().any():
            return parsed, "file_timestamp_utc"
    if "execution_timestamp_utc" in dataframe.columns:
        parsed = pd.to_datetime(dataframe["execution_timestamp_utc"], errors="coerce", utc=True)
        if parsed.notna().any():
            return parsed, "execution_timestamp_utc"
    return pd.Series(range(len(dataframe)), dtype=float), "row_index"


def _sort_by_time_axis_for_plotting(dataframe: pd.DataFrame) -> pd.DataFrame:
    x_values, x_label = _resolve_time_axis(dataframe)
    if x_label == "row_index":
        return dataframe.reset_index(drop=True).copy()

    work = dataframe.copy()
    work["__plot_time_sort_key"] = x_values
    work = work.sort_values("__plot_time_sort_key", na_position="last").drop(columns="__plot_time_sort_key")
    return work.reset_index(drop=True)


def _prepare_efficiency_plot_frame(
    dataframe: pd.DataFrame,
    reference_columns: list[str],
    *,
    apply_moving_average: bool,
    moving_average_kernel: int,
) -> pd.DataFrame:
    plot_frame = _sort_by_time_axis_for_plotting(dataframe)
    numeric_columns = [*reference_columns, "eff_reference"]
    plot_frame[numeric_columns] = plot_frame[numeric_columns].apply(pd.to_numeric, errors="coerce")
    if not apply_moving_average or moving_average_kernel <= 1:
        return plot_frame

    plot_frame[numeric_columns] = plot_frame[numeric_columns].rolling(
        window=moving_average_kernel,
        min_periods=1,
        center=True,
    ).mean()
    return plot_frame


def _prepare_rate_plot_frame(
    dataframe: pd.DataFrame,
    *,
    apply_moving_average: bool,
    moving_average_kernel: int,
) -> pd.DataFrame:
    plot_frame = _sort_by_time_axis_for_plotting(dataframe)
    numeric_columns = ["selected_rate_hz", "corrected_rate_hz"]
    plot_frame[numeric_columns] = plot_frame[numeric_columns].apply(pd.to_numeric, errors="coerce")
    if not apply_moving_average or moving_average_kernel <= 1:
        return plot_frame

    plot_frame[numeric_columns] = plot_frame[numeric_columns].rolling(
        window=moving_average_kernel,
        min_periods=1,
        center=True,
    ).mean()
    return plot_frame


def _plot_rate_series(
    dataframe: pd.DataFrame,
    output_path: Path,
    *,
    scale_factor_smoothing_label: str | None,
    event_markers: list[dict[str, object]],
    selected_series_meta: dict[str, str],
) -> None:
    plot_frame = _sort_by_time_axis_for_plotting(dataframe)
    numeric_columns = ["selected_rate_hz", "corrected_rate_hz"]
    plot_frame[numeric_columns] = plot_frame[numeric_columns].apply(pd.to_numeric, errors="coerce")
    x_values, x_label = _resolve_time_axis(plot_frame)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(
        x_values,
        plot_frame["selected_rate_hz"].astype(float),
        marker="o",
        markersize=3,
        linewidth=1.4,
        label=selected_series_meta["selected_label"],
    )
    ax.plot(
        x_values,
        plot_frame["corrected_rate_hz"].astype(float),
        marker="o",
        markersize=3,
        linewidth=1.4,
        label=selected_series_meta["corrected_label"],
    )
    title = f"Original and corrected {selected_series_meta['quantity_title']} time series"
    if scale_factor_smoothing_label:
        title += f" | corrected with smoothed scale factor ({scale_factor_smoothing_label})"
    ax.set_title(title)
    ax.set_xlabel(x_label.replace("_", " "))
    ax.set_ylabel(selected_series_meta["y_label"])
    _add_event_markers(ax, x_values, event_markers)
    ax.grid(alpha=0.25)
    ax.legend()
    if pd.api.types.is_datetime64_any_dtype(x_values):
        fig.autofmt_xdate()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _plot_reference_efficiency_series(
    dataframe: pd.DataFrame,
    output_path: Path,
    reference_columns: list[str],
    *,
    reference_mode: str,
    y_limits: tuple[float | None, float | None],
    event_markers: list[dict[str, object]],
) -> None:
    plot_frame = _sort_by_time_axis_for_plotting(dataframe)
    numeric_columns = [*reference_columns, "eff_reference"]
    plot_frame[numeric_columns] = plot_frame[numeric_columns].apply(pd.to_numeric, errors="coerce")
    x_values, x_label = _resolve_time_axis(plot_frame)
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    for idx, column in enumerate(reference_columns):
        ax.plot(
            x_values,
            plot_frame[column].astype(float),
            marker="o",
            markersize=3,
            linewidth=1.2,
            label=column,
            color=colors[idx % len(colors)],
        )
    ax.plot(
        x_values,
        plot_frame["eff_reference"].astype(float),
        marker="o",
        markersize=3,
        linewidth=1.6,
        label="eff_reference",
        color="black",
    )
    title = (
        "Selected empirical efficiencies over time | reference = "
        + _reference_mode_label(reference_columns, reference_mode)
    )
    ax.set_title(title)
    ax.set_xlabel(x_label.replace("_", " "))
    ax.set_ylabel("Empirical efficiency")
    y_min, y_max = y_limits
    ax.set_ylim(bottom=y_min, top=y_max)
    _add_event_markers(ax, x_values, event_markers)
    ax.grid(alpha=0.25)
    ax.legend()
    if pd.api.types.is_datetime64_any_dtype(x_values):
        fig.autofmt_xdate()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _plot_inverse_eff_reference_series(
    dataframe: pd.DataFrame,
    output_path: Path,
    *,
    scale_factor_smoothing_label: str | None,
    event_markers: list[dict[str, object]],
) -> None:
    plot_frame = _sort_by_time_axis_for_plotting(dataframe)
    plot_frame["inv_eff_reference_raw"] = pd.to_numeric(plot_frame["scale_factor_raw"], errors="coerce")
    plot_frame["inv_eff_reference_smoothed"] = pd.to_numeric(plot_frame["scale_factor_smoothed"], errors="coerce")

    x_values, x_label = _resolve_time_axis(plot_frame)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(
        x_values,
        plot_frame["inv_eff_reference_raw"].astype(float),
        marker="o",
        markersize=3,
        linewidth=1.0,
        color="#6a3d9a",
        alpha=0.55,
        label="1 / eff_reference (raw)",
    )
    if scale_factor_smoothing_label:
        ax.plot(
            x_values,
            plot_frame["inv_eff_reference_smoothed"].astype(float),
            marker="o",
            markersize=3,
            linewidth=1.5,
            color="#111111",
            alpha=0.95,
            label=f"1 / eff_reference (smoothed, {scale_factor_smoothing_label})",
        )
    title = "Inverse reference efficiency over time"
    if scale_factor_smoothing_label:
        title += f" | {scale_factor_smoothing_label}"
    ax.set_title(title)
    ax.set_xlabel(x_label.replace("_", " "))
    ax.set_ylabel("1 / eff_reference")
    _add_event_markers(ax, x_values, event_markers)
    ax.grid(alpha=0.25)
    ax.legend()
    if pd.api.types.is_datetime64_any_dtype(x_values):
        fig.autofmt_xdate()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _plot_eff_reference_vs_rates_scatter(
    dataframe: pd.DataFrame,
    output_path: Path,
    *,
    selected_series_meta: dict[str, str],
) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    eff_reference = pd.to_numeric(dataframe["eff_reference"], errors="coerce")
    selected_rate = pd.to_numeric(dataframe["selected_rate_hz"], errors="coerce")
    corrected_rate = pd.to_numeric(dataframe["corrected_rate_hz"], errors="coerce")

    selected_color = "#1f77b4"
    corrected_color = "#ff7f0e"

    ax.scatter(
        eff_reference,
        selected_rate,
        s=14,
        alpha=0.65,
        label=selected_series_meta["selected_label"],
        color=selected_color,
    )
    ax.scatter(
        eff_reference,
        corrected_rate,
        s=14,
        alpha=0.65,
        label=selected_series_meta["corrected_label"],
        color=corrected_color,
    )

    def _add_linear_trend_line(x_values: pd.Series, y_values: pd.Series, color: str, label: str) -> None:
        valid = x_values.notna() & y_values.notna()
        if int(valid.sum()) < 2:
            return
        x = x_values.loc[valid].to_numpy(dtype=float)
        y = y_values.loc[valid].to_numpy(dtype=float)
        x_min = float(np.nanmin(x))
        x_line_end = 1.01
        x_line_start = min(x_min, x_line_end)
        if x_line_end <= x_line_start:
            return
        slope, intercept = np.polyfit(x, y, 1)
        x_line = np.linspace(x_line_start, x_line_end, 120)
        y_line = slope * x_line + intercept
        ax.plot(
            x_line,
            y_line,
            linestyle="--",
            linewidth=1.8,
            color=color,
            label=f"{label}: y = {slope:.3f}x {intercept:+.3f}",
        )

    _add_linear_trend_line(eff_reference, selected_rate, selected_color, "selected trend")
    _add_linear_trend_line(eff_reference, corrected_rate, corrected_color, "corrected trend")
    ax.axvline(1.0, linestyle=":", linewidth=1.5, color="black", label="eff_reference = 1")

    ax.set_title(selected_series_meta["scatter_title"])
    ax.set_xlabel("eff_reference")
    ax.set_ylabel(selected_series_meta["y_label"])
    ax.grid(alpha=0.25)
    ax.legend()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def run(config_path: str | Path | None = None) -> Path:
    _configure_logging()
    ensure_output_dirs()
    config = load_config(config_path)

    input_path = cfg_path(config, "paths", "output_csv")
    output_path = cfg_path(config, "paths", "step2_scaled_output_csv")
    reference_columns = _resolve_efficiency_reference_columns(config)
    reference_mode = _resolve_efficiency_reference_mode(config)
    eff_reference_min = _resolve_efficiency_reference_min(config)
    efficiency_plot_ylim = _resolve_efficiency_plot_ylim(config)
    scale_factor_smoothing = _resolve_scale_factor_smoothing(config)
    scale_factor_smoothing_label = _scale_factor_smoothing_label(scale_factor_smoothing)
    selected_series_meta = _resolve_selected_series_plot_metadata(config)
    event_markers = _load_event_markers(config)

    dataframe = pd.read_csv(input_path, low_memory=False)
    _validate_columns(dataframe, reference_columns)
    scaled = _apply_simplified_scale(dataframe, reference_columns, reference_mode)
    scaled = _apply_scale_factor_smoothing(scaled, scale_factor_smoothing)
    scaled["corrected_rate_hz"] = pd.to_numeric(scaled["selected_rate_hz"], errors="coerce") * pd.to_numeric(
        scaled["scale_factor"],
        errors="coerce",
    )
    scaled, removed_rows = _filter_by_eff_reference_min(scaled, eff_reference_min)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    scaled.to_csv(output_path, index=False)

    plot_path = output_path.parent.parent / "PLOTS" / "step2_01_selected_vs_corrected_rate.png"
    _plot_rate_series(
        scaled,
        plot_path,
        scale_factor_smoothing_label=scale_factor_smoothing_label,
        event_markers=event_markers,
        selected_series_meta=selected_series_meta,
    )
    eff_plot_path = output_path.parent.parent / "PLOTS" / "step2_02_eff_reference_series.png"
    _plot_reference_efficiency_series(
        scaled,
        eff_plot_path,
        reference_columns,
        reference_mode=reference_mode,
        y_limits=efficiency_plot_ylim,
        event_markers=event_markers,
    )
    inv_eff_plot_path = output_path.parent.parent / "PLOTS" / "step2_04_inverse_eff_reference_series.png"
    _plot_inverse_eff_reference_series(
        scaled,
        inv_eff_plot_path,
        scale_factor_smoothing_label=scale_factor_smoothing_label,
        event_markers=event_markers,
    )
    scatter_plot_path = output_path.parent.parent / "PLOTS" / "step2_03_eff_reference_vs_rate_scatter.png"
    _plot_eff_reference_vs_rates_scatter(
        scaled,
        scatter_plot_path,
        selected_series_meta=selected_series_meta,
    )

    logging.info(
        "Wrote simplified scaled output with %d rows to %s",
        len(scaled),
        output_path,
    )
    logging.info("Efficiency reference columns used: %s", reference_columns)
    logging.info(
        "Efficiency reference mode: %s",
        _reference_mode_label(reference_columns, reference_mode),
    )
    if eff_reference_min is not None:
        logging.info(
            "Applied eff_reference minimum %.3f and dropped %d rows below threshold.",
            eff_reference_min,
            removed_rows,
        )
    logging.info("Efficiency-series plot y limits: bottom=%s top=%s", efficiency_plot_ylim[0], efficiency_plot_ylim[1])
    if scale_factor_smoothing_label:
        logging.info("Applied scale-factor smoothing with %s.", scale_factor_smoothing_label)
    logging.info("Wrote reference-efficiency time series plot to %s", eff_plot_path)
    logging.info("Wrote inverse-eff_reference time series plot to %s", inv_eff_plot_path)
    logging.info("Wrote original vs corrected time series plot to %s", plot_path)
    logging.info("Wrote eff_reference vs rates scatter plot to %s", scatter_plot_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply a simplified scale factor based on either mean(selected empirical efficiencies)^4 or their product."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to config JSON file.")
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()
