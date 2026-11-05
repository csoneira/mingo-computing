"""Generate synchronized detector-environment context for Stage-1 product tests."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SENSOR_COLUMNS = (
    "sensors_ext_Temperature_ext", "sensors_ext_RH_ext", "sensors_ext_Pressure_ext",
    "sensors_int_Temperature_int", "sensors_int_RH_int", "sensors_int_Pressure_int",
)
HV_COLUMNS = ("hv_CurrentNeg", "hv_CurrentPos", "hv_HVneg", "hv_HVpos")
RATE_COLUMNS = (
    "rates_Asserted", "rates_Edge", "rates_Accepted",
    "rates_Multiplexer1", "rates_M2", "rates_M3", "rates_M4",
    "rates_CM1", "rates_CM2", "rates_CM3", "rates_CM4",
)
MULTIPLEXER_COLUMNS = ("rates_Multiplexer1", "rates_M2", "rates_M3", "rates_M4")
FLOW_COLUMNS = ("flow_FlowRate1", "flow_FlowRate2", "flow_FlowRate3", "flow_FlowRate4")
DISK_COLUMNS = ("odroid_DiskFill1", "odroid_DiskFill2", "odroid_DiskFillX")
ENVIRONMENT_COLUMNS = SENSOR_COLUMNS + HV_COLUMNS + RATE_COLUMNS + FLOW_COLUMNS + DISK_COLUMNS
REDUCED_FIELD_COLUMN = "derived_ReducedField"
DEFAULT_GAS_GAP_MM = 1.0


def reduced_electric_field(V: Any, d: float, P: Any, T: Any) -> Any:
    """Return E/N in Townsend for V [V], d [mm], P [hPa], and T [°C]."""
    kb = 0.13806  # Boltzmann constant with the unit conversions folded in.
    temperature_kelvin = T + 273.15
    return (kb * V * temperature_kelvin) / (P * d)


def _daily_paths(station_root: Path, start: pd.Timestamp, end: pd.Timestamp) -> list[Path]:
    root = station_root / "STAGE_1_PRODUCTS" / "LOG_DATA" / "OUTPUT_FILES"
    return [
        root / f"{day:%Y}" / f"{day:%m}" / f"lab_logs_{day:%Y_%m_%d}.csv"
        for day in pd.date_range(start.normalize(), end.normalize(), freq="D")
    ]


def load_environment_data(
    station_root: Path,
    start: datetime,
    end: datetime,
    *,
    context_fraction: float = 0.10,
    gas_gap_mm: float = DEFAULT_GAS_GAP_MM,
) -> tuple[pd.DataFrame, list[Path], pd.Timestamp, pd.Timestamp]:
    """Load LAB_LOG products with a fractional time margin around the selection."""
    if not np.isfinite(context_fraction) or context_fraction < 0:
        raise ValueError(
            "Environment-context fraction must be finite and non-negative."
        )
    if not np.isfinite(gas_gap_mm) or gas_gap_mm <= 0:
        raise ValueError("Environment gas-gap width must be finite and positive.")
    duration = (pd.Timestamp(end) - pd.Timestamp(start)) * context_fraction
    left = pd.Timestamp(start) - duration
    right = pd.Timestamp(end) + duration
    source_paths = [path for path in _daily_paths(station_root, left, right) if path.exists()]
    frames: list[pd.DataFrame] = []
    for path in source_paths:
        try:
            frame = pd.read_csv(path, low_memory=False)
        except Exception as error:
            print(f"Warning: could not read environment log product {path}: {error}")
            continue
        if "Time" not in frame:
            print(f"Warning: environment log product has no Time column: {path}")
            continue
        frames.append(frame)

    if frames:
        frame = pd.concat(frames, ignore_index=True, sort=False)
        frame["Time"] = pd.to_datetime(frame["Time"], errors="coerce")
        frame = frame.dropna(subset=["Time"])
        frame = frame.loc[frame["Time"].between(left, right)].copy()
        frame = frame.sort_values("Time").drop_duplicates(subset="Time", keep="last")
    else:
        frame = pd.DataFrame(columns=["Time"])
    for column in ENVIRONMENT_COLUMNS:
        if column not in frame:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    voltage_v = (
        (frame["hv_HVneg"].abs() + frame["hv_HVpos"].abs()) / 2.0 * 1000.0
    )
    frame[REDUCED_FIELD_COLUMN] = reduced_electric_field(
        voltage_v,
        gas_gap_mm,
        frame["sensors_ext_Pressure_ext"].replace(0, np.nan),
        frame["sensors_ext_Temperature_ext"],
    )
    return frame.loc[:, ["Time", *ENVIRONMENT_COLUMNS, REDUCED_FIELD_COLUMN]], source_paths, left, right


def _shade(axis: Any, start: datetime, end: datetime, *, label: bool = False) -> None:
    left, right = pd.Timestamp(start), pd.Timestamp(end)
    if left == right:
        left -= pd.Timedelta(minutes=5)
        right += pd.Timedelta(minutes=5)
    axis.axvspan(
        left, right, color="gold", alpha=0.13, linewidth=0, zorder=0,
        label="selected acquisition block" if label else None,
    )


def _format_axis(axis: Any, start: datetime, end: datetime) -> None:
    locator = mdates.AutoDateLocator(minticks=3, maxticks=10)
    axis.xaxis.set_major_locator(locator)
    axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    axis.grid(True, alpha=0.22)
    axis.set_xlim(pd.Timestamp(start), pd.Timestamp(end))


def _scatter(
    axis: Any,
    frame: pd.DataFrame,
    column: str,
    *,
    label: str,
    color: str,
    filled: bool = True,
    alpha: float = 0.58,
    size: float = 18,
) -> None:
    valid = frame[column].notna()
    if not bool(valid.any()):
        return
    axis.scatter(
        frame.loc[valid, "Time"], frame.loc[valid, column], s=size,
        marker="o", facecolors=color if filled else "none", edgecolors=color,
        linewidths=0.85, alpha=alpha, label=label, zorder=3,
    )


def _empty_note(axis: Any, frame: pd.DataFrame, columns: Iterable[str]) -> None:
    if not any(column in frame and frame[column].notna().any() for column in columns):
        axis.text(
            0.5, 0.5, "No data in this time window", transform=axis.transAxes,
            ha="center", va="center", color="0.4",
        )


def _sensor_panel(
    axis: Any,
    frame: pd.DataFrame,
    external_column: str,
    internal_column: str,
    *,
    color: str,
    ylabel: str,
    title: str,
    start: datetime,
    end: datetime,
) -> None:
    _shade(axis, start, end, label=True)
    _scatter(axis, frame, external_column, label="external", color=color)
    _scatter(
        axis, frame, internal_column, label="internal", color=color, filled=False,
    )
    axis.set_ylabel(ylabel, color=color)
    axis.tick_params(axis="y", colors=color)
    axis.set_title(f"{title} (filled: external; open: internal)")
    axis.legend(loc="best", fontsize=8)
    _empty_note(axis, frame, (external_column, internal_column))
    _format_axis(axis, start, end)


def _simple_panel(
    axis: Any,
    frame: pd.DataFrame,
    columns: Sequence[str],
    labels: Sequence[str],
    colors: Sequence[str],
    ylabel: str,
    title: str,
    start: datetime,
    end: datetime,
) -> None:
    _shade(axis, start, end, label=True)
    for column, label, color in zip(columns, labels, colors):
        _scatter(axis, frame, column, label=label, color=color, alpha=0.66)
    axis.set_ylabel(ylabel)
    axis.set_title(title)
    axis.legend(loc="best", fontsize=8, ncols=min(4, len(columns)))
    _empty_note(axis, frame, columns)
    _format_axis(axis, start, end)


def _reduced_field_panel(axis: Any, frame: pd.DataFrame, start: datetime, end: datetime) -> None:
    _simple_panel(
        axis, frame, (REDUCED_FIELD_COLUMN,), ("Reduced electric field",),
        ("teal",), "E/N [Td]", "Reduced electric field", start, end,
    )


def _figure_one(
    frame: pd.DataFrame, path: Path, title: str, start: datetime, end: datetime,
    view_start: datetime, view_end: datetime,
) -> None:
    fig, axes = plt.subplots(
        8, 1, figsize=(19, 31), sharex=True, constrained_layout=True,
    )
    _sensor_panel(
        axes[0], frame, "sensors_ext_Temperature_ext",
        "sensors_int_Temperature_int", color="red", ylabel="Temperature (°C)",
        title="Temperature", start=start, end=end,
    )
    _sensor_panel(
        axes[1], frame, "sensors_ext_Pressure_ext",
        "sensors_int_Pressure_int", color="green", ylabel="Pressure (hPa)",
        title="Pressure", start=start, end=end,
    )
    _sensor_panel(
        axes[2], frame, "sensors_ext_RH_ext", "sensors_int_RH_int",
        color="blue", ylabel="Relative humidity (%)", title="Humidity",
        start=start, end=end,
    )
    _simple_panel(
        axes[3], frame, ("hv_HVneg", "hv_HVpos"), ("HV −", "HV +"),
        ("crimson", "navy"), "HV", "High voltage", start, end,
    )
    _simple_panel(
        axes[4], frame, ("hv_CurrentNeg", "hv_CurrentPos"),
        ("Current −", "Current +"), ("darkorange", "purple"),
        "Current", "HV current", start, end,
    )
    _reduced_field_panel(axes[5], frame, start, end)
    _simple_panel(
        axes[6], frame,
        ("rates_Asserted", "rates_Edge", "rates_Accepted"),
        ("Asserted", "Edge", "Accepted"),
        ("tab:orange", "tab:purple", "tab:green"),
        "Rate", "Trigger rates", start, end,
    )
    _simple_panel(
        axes[7], frame, FLOW_COLUMNS, ("Flow 1", "Flow 2", "Flow 3", "Flow 4"),
        ("tab:blue", "tab:orange", "tab:green", "tab:red"),
        "Flow rate", "Gas-flow channels", start, end,
    )
    for axis in axes:
        axis.set_xlim(pd.Timestamp(view_start), pd.Timestamp(view_end))
    fig.suptitle(f"{title}\nEnvironment context — overview", fontsize=15)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _figure_two(
    frame: pd.DataFrame, path: Path, title: str, start: datetime, end: datetime,
    view_start: datetime, view_end: datetime,
) -> None:
    fig, axes = plt.subplots(4, 1, figsize=(19, 17), sharex=True, constrained_layout=True)
    _reduced_field_panel(axes[0], frame, start, end)
    _simple_panel(
        axes[1], frame,
        ("rates_Asserted", "rates_Edge", "rates_Accepted"),
        ("Asserted", "Edge", "Accepted"), ("tab:orange", "tab:purple", "tab:green"),
        "Rate", "Trigger rates", start, end,
    )
    _simple_panel(
        axes[2], frame,
        ("rates_Multiplexer1", "rates_M2", "rates_M3", "rates_M4"),
        ("Multiplexer 1", "M2", "M3", "M4"),
        ("tab:blue", "tab:orange", "tab:green", "tab:red"),
        "Rate", "Multiplexer rates", start, end,
    )
    _simple_panel(
        axes[3], frame, ("rates_CM1", "rates_CM2", "rates_CM3", "rates_CM4"),
        ("CM1", "CM2", "CM3", "CM4"),
        ("tab:blue", "tab:orange", "tab:green", "tab:red"),
        "Rate", "Coincidence-matrix rates", start, end,
    )
    for axis in axes:
        axis.set_xlim(pd.Timestamp(view_start), pd.Timestamp(view_end))
    fig.suptitle(f"{title}\nEnvironment context — rates and reduced field", fontsize=15)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _figure_three(
    frame: pd.DataFrame, path: Path, title: str, start: datetime, end: datetime,
    view_start: datetime, view_end: datetime,
) -> None:
    fig, axes = plt.subplots(
        2, 1, figsize=(19, 10), sharex=True, constrained_layout=True,
    )
    _simple_panel(
        axes[0], frame, ("odroid_DiskFill1", "odroid_DiskFill2"),
        ("DiskFill1", "DiskFill2"), ("tab:blue", "tab:orange"),
        "Reported fill value", "Odroid DiskFill1 and DiskFill2", start, end,
    )
    _simple_panel(
        axes[1], frame, ("odroid_DiskFillX",), ("DiskFillX",), ("tab:green",),
        "Reported fill value", "Odroid DiskFillX", start, end,
    )
    for axis in axes:
        axis.set_xlim(pd.Timestamp(view_start), pd.Timestamp(view_end))
    fig.suptitle(f"{title}\nEnvironment context — Odroid storage", fontsize=15)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _reduced_field_vs_multiplexer_scatter(
    frame: pd.DataFrame, path: Path, title: str,
) -> None:
    fig, axes = plt.subplots(
        1, 2, figsize=(20, 8), sharex=True, constrained_layout=True,
    )
    absolute_axis, relative_axis = axes
    labels = ("Multiplexer 1", "Multiplexer 2", "Multiplexer 3", "Multiplexer 4")
    colors = ("tab:blue", "tab:orange", "tab:green", "tab:red")
    markers = ("o", "s", "^", "D")
    plotted = False
    for column, label, color, marker in zip(
        MULTIPLEXER_COLUMNS, labels, colors, markers, strict=True,
    ):
        valid = (
            frame[REDUCED_FIELD_COLUMN].notna()
            & frame[column].notna()
            & np.isfinite(frame[REDUCED_FIELD_COLUMN])
            & np.isfinite(frame[column])
        )
        if not bool(valid.any()):
            continue
        plotted = True
        rates = frame.loc[valid, column]
        mean_rate = float(rates.mean())
        absolute_axis.scatter(
            frame.loc[valid, REDUCED_FIELD_COLUMN], frame.loc[valid, column],
            s=28, marker=marker, color=color, edgecolors="none", alpha=0.55,
            label=f"{label} (n={int(valid.sum()):,})", rasterized=True,
        )
        if np.isfinite(mean_rate) and mean_rate != 0.0:
            relative_axis.scatter(
                frame.loc[valid, REDUCED_FIELD_COLUMN], rates / mean_rate,
                s=28, marker=marker, color=color, edgecolors="none", alpha=0.55,
                label=f"{label} (n={int(valid.sum()):,})", rasterized=True,
            )
    absolute_axis.set(
        xlabel="Reduced electric field E/N [Td]",
        ylabel="Multiplexer rate",
        title="Reduced field versus multiplexer rates",
    )
    relative_axis.set(
        xlabel="Reduced electric field E/N [Td]",
        ylabel="Relative multiplexer rate (Mᵢ / ⟨Mᵢ⟩)",
        title="Reduced field versus relative multiplexer rates",
    )
    relative_axis.axhline(1.0, color="0.35", linewidth=1.2, linestyle="--")
    for axis in axes:
        axis.grid(True, alpha=0.25)
    if plotted:
        for axis in axes:
            axis.legend(loc="best", fontsize=9, ncols=2)
    else:
        for axis in axes:
            axis.text(
                0.5, 0.5, "No synchronized reduced-field/rate data",
                transform=axis.transAxes, ha="center", va="center", color="0.4",
            )
    fig.suptitle(
        f"{title}\nReduced field versus all four multiplexers: absolute and relative rates",
        fontsize=15,
    )
    fig.savefig(path, dpi=160)
    plt.close(fig)


def generate_environment_context(
    station_root: Path,
    start: datetime,
    end: datetime,
    output_dir: Path,
    title: str,
    *,
    context_fraction: float = 0.10,
    gas_gap_mm: float = DEFAULT_GAS_GAP_MM,
) -> list[Path]:
    """Write environment figures plus their exact synchronized source data."""
    frame, sources, left, right = load_environment_data(
        station_root, start, end, context_fraction=context_fraction,
        gas_gap_mm=gas_gap_mm,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    for pattern in ("*.png", "*.csv"):
        for obsolete in output_dir.glob(pattern):
            obsolete.unlink()
    paths = [
        output_dir / "00_environment_data.csv",
        output_dir / "01_environment_overview.png",
        output_dir / "02_rates_and_reduced_field.png",
        output_dir / "03_odroid_disk_fill.png",
        output_dir / "04_reduced_field_vs_multiplexer_rates.png",
    ]
    frame.to_csv(paths[0], index=False)
    _figure_one(frame, paths[1], title, start, end, left, right)
    _figure_two(frame, paths[2], title, start, end, left, right)
    _figure_three(frame, paths[3], title, start, end, left, right)
    _reduced_field_vs_multiplexer_scatter(frame, paths[4], title)
    available = sum(frame[column].notna().any() for column in ENVIRONMENT_COLUMNS)
    print(
        f"Environment context: {len(frame):,} one-minute row(s), "
        f"{available}/{len(ENVIRONMENT_COLUMNS)} requested channels with data, "
        f"{len(sources)} daily source file(s), window={left} to {right} -> {output_dir}"
    )
    return paths
