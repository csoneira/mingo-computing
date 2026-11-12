#!/usr/bin/env python3

"""Plot STEP_1 noise-control metadata for Tasks 1-3."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D


SCRIPT_PATH = Path(__file__).resolve()


_REPO_IMPORT_ROOT = SCRIPT_PATH.parents[7]
if str(_REPO_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_IMPORT_ROOT))
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root

REPO_ROOT = get_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.plot_utils import (  # noqa: E402
    metadata_output_status_suffix,
    pdf_save_rasterized_page,
)


STATIONS_ROOT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
PLOTTER_DIR = SCRIPT_PATH.parent
PLOTS_DIR = PLOTTER_DIR / "PLOTS"
DEFAULT_CONFIG_PATH = PLOTTER_DIR / "noise_control_metadata_config.json"
DEFAULT_PERCENT_OUTPUT_FILENAME = "noise_control_metadata_report.pdf"
DEFAULT_RATE_OUTPUT_FILENAME = "noise_control_metadata_rate_report.pdf"
DEFAULT_PLANE_COMBINATION_OUTPUT_FILENAME = "noise_control_plane_combination_rate_report.pdf"
DEFAULT_EFFICIENCY_OUTPUT_FILENAMES = {
    1: "task_1_noise_control_efficiency_report.pdf",
    2: "task_2_noise_control_efficiency_report.pdf",
    3: "task_3_noise_control_efficiency_report.pdf",
}

TASK_IDS: Tuple[int, ...] = (1, 2, 3)
DEFAULT_LAST_HOURS = 2.0
DEFAULT_PANEL_WIDTH_RATIOS: Tuple[float, float] = (5.0, 1.0)
DEFAULT_MARKER_SIZE = 14.0
DEFAULT_MAX_FILL_GAP_HOURS = 3.0
DEFAULT_METRIC_MODE = "rate_hz"
DEFAULT_REPORT_KIND = "all"
DEFAULT_EFFICIENCY_Y_MIN = 0.5
METADATA_STATUS_SUFFIX = metadata_output_status_suffix("noise_control")
RATE_DENOMINATOR_COLUMN = "count_rate_denominator_seconds"
METADATA_FILENAME_TEMPLATE = "task_{task_id}_metadata_noise_control.csv"
TRIGGER_TYPE_METADATA_FILENAME_TEMPLATE = "task_{task_id}_metadata_trigger_type.csv"
METADATA_TIMESTAMP_FMT = "%Y-%m-%d_%H.%M.%S"
BASENAME_TIMESTAMP_DIGITS = 11
FILENAME_TIMESTAMP_PATTERN = re.compile(r"mi0\d(\d{11})$", re.IGNORECASE)
SELECTED_OFFENDER_RATE_COLUMN_PATTERN = re.compile(
    r"plane_combination_filter_rows_with_(?P<count>\d+)_selected_offenders_rate_hz$"
)
EFFICIENCY_COLUMN_PATTERN = re.compile(
    r"(?P<prefix>plane|strip)_combination_filter_eff_p(?P<plane>\d+)_selected_offenders_le_(?P<threshold>\d+)$"
)
EXCLUDED_COLUMNS: Set[str] = {
    "filename_base",
    "basename",
    "execution_timestamp",
    "file_timestamp",
    "plot_timestamp",
    "execution_dt",
    "param_hash",
    RATE_DENOMINATOR_COLUMN,
}
DEFAULT_OUTPUTS = {
    "selected_offenders_percent": PLOTS_DIR / DEFAULT_PERCENT_OUTPUT_FILENAME,
    "selected_offenders_rate_hz": PLOTS_DIR / DEFAULT_RATE_OUTPUT_FILENAME,
    "plane_combination_rates": PLOTS_DIR / DEFAULT_PLANE_COMBINATION_OUTPUT_FILENAME,
    **{
        f"task_{task_id}_efficiency_thresholds": PLOTS_DIR / filename
        for task_id, filename in DEFAULT_EFFICIENCY_OUTPUT_FILENAMES.items()
    },
}
PLANE_COMBINATION_RATE_GROUPS: Tuple[Tuple[str, Tuple[Tuple[str, str], ...]], ...] = (
    ("1234", (("1234", "clean_tt_1234_rate_hz"),)),
    ("123, 234", (("123", "clean_tt_123_rate_hz"), ("234", "clean_tt_234_rate_hz"))),
    ("12, 23, 34", (("12", "clean_tt_12_rate_hz"), ("23", "clean_tt_23_rate_hz"), ("34", "clean_tt_34_rate_hz"))),
    ("124, 134", (("124", "clean_tt_124_rate_hz"), ("134", "clean_tt_134_rate_hz"))),
    ("13", (("13", "clean_tt_13_rate_hz"),)),
)
PLANE_COMBINATION_MARKERS = ("o", "s", "^")


def configure_matplotlib_style() -> None:
    plt.style.use("default")


def normalize_station_token(token: str) -> Optional[str]:
    cleaned = token.strip().upper()
    if not cleaned:
        return None
    if cleaned.startswith("MINGO"):
        cleaned = cleaned[5:]
    digits = "".join(ch for ch in cleaned if ch.isdigit())
    if not digits:
        return None
    return f"MINGO{int(digits):02d}"


def list_available_stations() -> List[str]:
    if not STATIONS_ROOT.exists():
        return []
    stations: List[str] = []
    for entry in STATIONS_ROOT.iterdir():
        if entry.is_dir() and re.fullmatch(r"MINGO\d{2}", entry.name.upper()):
            stations.append(entry.name.upper())
    stations.sort()
    return stations


def resolve_station_selection(tokens: Sequence[object]) -> List[str]:
    available = list_available_stations()
    if not tokens:
        return available

    selected: List[str] = []
    for token in tokens:
        station = normalize_station_token(str(token))
        if station is None or station not in available:
            continue
        selected.append(station)
    return sorted(dict.fromkeys(selected))


def normalize_task_selection(values: Sequence[object]) -> List[int]:
    selected: List[int] = []
    for value in values:
        try:
            task_id = int(value)
        except (TypeError, ValueError):
            continue
        if task_id in TASK_IDS:
            selected.append(task_id)
    deduped = sorted(dict.fromkeys(selected))
    return deduped if deduped else list(TASK_IDS)


def normalize_basename(value: object) -> str:
    text = str(value).strip()
    if not text:
        return ""
    return Path(text).stem.strip()


def extract_timestamp_from_basename(value: str) -> Optional[datetime]:
    if not value:
        return None

    stem = Path(value).stem.strip()
    if not stem:
        return None

    try:
        return datetime.strptime(stem, "%Y-%m-%d_%H.%M.%S")
    except ValueError:
        pass

    match = FILENAME_TIMESTAMP_PATTERN.search(stem)
    if match:
        digits = match.group(1)
    else:
        digits = "".join(ch for ch in stem if ch.isdigit())
        if len(digits) < BASENAME_TIMESTAMP_DIGITS:
            return None
        digits = digits[-BASENAME_TIMESTAMP_DIGITS:]

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

    return datetime(year, 1, 1) + timedelta(
        days=day_of_year - 1,
        hours=hour,
        minutes=minute,
        seconds=second,
    )


def parse_execution_series(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    parsed = pd.to_datetime(text, format=METADATA_TIMESTAMP_FMT, errors="coerce")
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(text[missing], errors="coerce")
    return parsed


def series_bounds(series: pd.Series) -> Optional[Tuple[pd.Timestamp, pd.Timestamp]]:
    valid = pd.to_datetime(series, errors="coerce").dropna()
    if valid.empty:
        return None
    lower = pd.Timestamp(valid.min())
    upper = pd.Timestamp(valid.max())
    if lower == upper:
        upper = lower + timedelta(minutes=1)
    return lower, upper


def collect_station_file_bounds(task_data: Dict[int, pd.DataFrame]) -> Optional[Tuple[pd.Timestamp, pd.Timestamp]]:
    chunks: List[pd.Series] = []
    for df in task_data.values():
        if df.empty:
            continue
        chunks.append(pd.to_datetime(df["file_timestamp"], errors="coerce"))
    if not chunks:
        return None
    combined = pd.concat(chunks, ignore_index=True).dropna()
    if combined.empty:
        return None
    return series_bounds(combined)


def collect_station_execution_bounds(
    task_data: Dict[int, pd.DataFrame],
    last_hours: float,
) -> Optional[Tuple[pd.Timestamp, pd.Timestamp]]:
    chunks: List[pd.Series] = []
    for df in task_data.values():
        if df.empty:
            continue
        chunks.append(pd.to_datetime(df["execution_timestamp"], errors="coerce"))
    if not chunks:
        return None
    combined = pd.concat(chunks, ignore_index=True).dropna()
    if combined.empty:
        return None
    end = pd.Timestamp(combined.max())
    start = end - timedelta(hours=last_hours)
    if start == end:
        start = end - timedelta(minutes=1)
    return start, end


def load_config(config_path: Path) -> Dict[str, object]:
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        return {}
    return payload


def _coerce_output_path(output_value: object) -> Path:
    candidate = Path(str(output_value))
    if not candidate.is_absolute():
        candidate = PLOTTER_DIR / candidate
    return candidate


def default_output_path(report_kind: str, metric_mode: Optional[str] = None) -> Path:
    if report_kind == "efficiency_thresholds":
        return DEFAULT_OUTPUTS["task_1_efficiency_thresholds"]
    if report_kind == "plane_combination_rates":
        return DEFAULT_OUTPUTS["plane_combination_rates"]
    if metric_mode == "percent":
        return DEFAULT_OUTPUTS["selected_offenders_percent"]
    return DEFAULT_OUTPUTS["selected_offenders_rate_hz"]


def resolve_output_path(
    output_value: Optional[object],
    *,
    report_kind: str,
    metric_mode: Optional[str] = None,
    task_id: Optional[int] = None,
) -> Path:
    if output_value is None:
        if report_kind == "efficiency_thresholds" and task_id in TASK_IDS:
            return DEFAULT_OUTPUTS[f"task_{task_id}_efficiency_thresholds"]
        return default_output_path(report_kind, metric_mode)
    return _coerce_output_path(output_value)


def resolve_bundle_outputs(config: Dict[str, object]) -> Dict[str, Path]:
    raw_outputs = config.get("outputs", {})
    if not isinstance(raw_outputs, dict):
        raw_outputs = {}
    outputs = {
        key: default_value
        for key, default_value in DEFAULT_OUTPUTS.items()
    }
    for key, raw_value in raw_outputs.items():
        if key not in outputs or raw_value in (None, ""):
            continue
        outputs[key] = _coerce_output_path(raw_value)
    legacy_output = config.get("output")
    if legacy_output not in (None, "") and "selected_offenders_percent" not in raw_outputs:
        outputs["selected_offenders_percent"] = _coerce_output_path(legacy_output)
    return outputs


def load_metadata_csv(metadata_path: Path) -> pd.DataFrame:
    if not metadata_path.exists():
        return pd.DataFrame()

    try:
        df = pd.read_csv(metadata_path)
    except Exception as exc:
        print(f"[noise_control_metadata_plotter] Failed to read {metadata_path}: {exc}", file=sys.stderr)
        return pd.DataFrame()
    if df.empty or "filename_base" not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df["basename"] = df["filename_base"].map(normalize_basename)
    df = df[df["basename"].str.startswith("mi", na=False)]
    if df.empty:
        return pd.DataFrame()

    if "execution_timestamp" in df.columns:
        df["execution_timestamp"] = parse_execution_series(df["execution_timestamp"])
        df["execution_dt"] = df["execution_timestamp"]
    else:
        df["execution_timestamp"] = pd.NaT
        df["execution_dt"] = pd.NaT

    df["file_timestamp"] = pd.to_datetime(
        df["basename"].map(extract_timestamp_from_basename),
        errors="coerce",
    )
    df["plot_timestamp"] = df["file_timestamp"]
    missing = df["plot_timestamp"].isna()
    if missing.any():
        df.loc[missing, "plot_timestamp"] = df.loc[missing, "execution_dt"]

    skip_numeric = {"filename_base", "basename", "execution_timestamp", "file_timestamp", "plot_timestamp", "execution_dt"}
    for column in df.columns:
        if column in skip_numeric:
            continue
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.sort_values(["basename", "execution_dt"]).drop_duplicates(subset=["basename"], keep="last")
    df = df.dropna(subset=["plot_timestamp"]).sort_values("plot_timestamp").reset_index(drop=True)
    return df


def load_task_metadata(station: str, task_id: int) -> pd.DataFrame:
    metadata_path = (
        STATIONS_ROOT
        / station
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / f"TASK_{task_id}"
        / "METADATA"
        / METADATA_FILENAME_TEMPLATE.format(task_id=task_id)
    )
    return load_metadata_csv(metadata_path)


def load_task_trigger_type_metadata(station: str, task_id: int) -> pd.DataFrame:
    metadata_path = (
        STATIONS_ROOT
        / station
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / f"TASK_{task_id}"
        / "METADATA"
        / TRIGGER_TYPE_METADATA_FILENAME_TEMPLATE.format(task_id=task_id)
    )
    return load_metadata_csv(metadata_path)


def detect_metric_columns(df: pd.DataFrame, metric_mode: str) -> Tuple[List[str], str]:
    preferred_suffix = "_pct" if metric_mode == "percent" else "_rate_hz"
    fallback_suffix = "_rate_hz" if metric_mode == "percent" else "_pct"

    def collect_for_suffix(suffix: str) -> List[str]:
        columns: List[tuple[int, str]] = []
        for column in df.columns:
            if column in EXCLUDED_COLUMNS or not column.endswith(suffix):
                continue
            series = pd.to_numeric(df[column], errors="coerce").dropna()
            if series.empty or float(series.abs().sum()) <= 0:
                continue
            match = re.search(r"rows_with_(\d+)_selected_offenders", column)
            order_key = int(match.group(1)) if match else 9999
            columns.append((order_key, column))
        columns.sort()
        return [column for _, column in columns]

    preferred = collect_for_suffix(preferred_suffix)
    if preferred:
        return preferred, metric_mode
    fallback = collect_for_suffix(fallback_suffix)
    return fallback, ("rate_hz" if metric_mode == "percent" else "percent")


def selected_offender_rate_columns(df: pd.DataFrame) -> List[str]:
    columns: List[Tuple[int, str]] = []
    for column in df.columns:
        match = SELECTED_OFFENDER_RATE_COLUMN_PATTERN.fullmatch(column)
        if not match:
            continue
        columns.append((int(match.group("count")), column))
    columns.sort()
    return [column for _, column in columns]


def build_plane_combination_rate_dataframe(noise_df: pd.DataFrame, trigger_df: pd.DataFrame) -> pd.DataFrame:
    if noise_df.empty or trigger_df.empty:
        return pd.DataFrame()

    offender_columns = selected_offender_rate_columns(noise_df)
    offender_columns = [
        column
        for column in offender_columns
        if int(SELECTED_OFFENDER_RATE_COLUMN_PATTERN.fullmatch(column).group("count")) >= 1
    ]
    trigger_columns = sorted(
        {
            column_name
            for _, specs in PLANE_COMBINATION_RATE_GROUPS
            for _, column_name in specs
        }
        & set(trigger_df.columns)
    )
    if not offender_columns or not trigger_columns:
        return pd.DataFrame()

    keep_noise_columns = ["basename", "filename_base", "file_timestamp", "execution_timestamp"] + offender_columns
    keep_noise_columns = [column for column in keep_noise_columns if column in noise_df.columns]
    keep_trigger_columns = ["basename"] + trigger_columns

    merged = noise_df.loc[:, keep_noise_columns].merge(
        trigger_df.loc[:, keep_trigger_columns],
        on="basename",
        how="inner",
    )
    if merged.empty:
        return merged

    merged["selected_offender_total_rate_hz"] = (
        merged[offender_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0).sum(axis=1)
    )
    merged = merged.sort_values("file_timestamp").reset_index(drop=True)
    return merged


def detect_efficiency_columns(df: pd.DataFrame) -> Dict[int, List[str]]:
    columns_by_plane: Dict[int, List[Tuple[int, str]]] = {}
    for column in df.columns:
        match = EFFICIENCY_COLUMN_PATTERN.fullmatch(column)
        if not match:
            continue
        plane = int(match.group("plane"))
        threshold = int(match.group("threshold"))
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        if series.empty:
            continue
        columns_by_plane.setdefault(plane, []).append((threshold, column))

    ordered: Dict[int, List[str]] = {}
    for plane, specs in columns_by_plane.items():
        specs.sort()
        ordered[plane] = [column for _, column in specs]
    return ordered


def colour_map_for_columns(columns: Sequence[str]) -> Dict[str, str]:
    cmap = plt.get_cmap("tab20")
    return {column: cmap(idx % cmap.N) for idx, column in enumerate(columns)}


def efficiency_colour_map_for_columns(columns: Sequence[str]) -> Dict[str, str]:
    threshold_specs: List[Tuple[int, str]] = []
    for column in columns:
        match = EFFICIENCY_COLUMN_PATTERN.fullmatch(column)
        if not match:
            continue
        threshold_specs.append((int(match.group("threshold")), column))

    unique_thresholds = sorted({threshold for threshold, _ in threshold_specs})
    cmap = plt.get_cmap("tab10")
    threshold_colors = {
        threshold: cmap(idx % cmap.N)
        for idx, threshold in enumerate(unique_thresholds)
    }
    return {
        column: threshold_colors[threshold]
        for threshold, column in threshold_specs
    }


def build_plot_segments(df: pd.DataFrame, x_column: str, y_column: str, max_gap_hours: float) -> pd.DataFrame:
    plot_df = df.loc[:, [x_column, y_column]].copy()
    plot_df[y_column] = pd.to_numeric(plot_df[y_column], errors="coerce")
    plot_df = plot_df.dropna(subset=[x_column, y_column]).sort_values(x_column).reset_index(drop=True)
    if plot_df.empty or max_gap_hours <= 0:
        return plot_df

    gaps = plot_df[x_column].diff()
    if gaps.empty:
        return plot_df

    threshold = pd.Timedelta(hours=float(max_gap_hours))
    rows: List[dict[str, object]] = []
    for index, row in plot_df.iterrows():
        if index > 0 and gaps.iloc[index] > threshold:
            rows.append({x_column: pd.NaT, y_column: np.nan})
        rows.append({x_column: row[x_column], y_column: row[y_column]})
    return pd.DataFrame(rows)


def column_label(column_name: str) -> str:
    match = re.search(r"rows_with_(\d+)_selected_offenders", column_name)
    if match:
        return f"{match.group(1)} offender(s)"
    return column_name


def efficiency_column_label(column_name: str) -> str:
    match = EFFICIENCY_COLUMN_PATTERN.fullmatch(column_name)
    if match:
        return f"<= {match.group('threshold')} offender(s)"
    return column_name


def efficiency_report_title(task_id: int) -> str:
    return f"Task {task_id} cumulative three-to-four efficiency vs max selected offenders"


def efficiency_legend_title(task_id: int) -> str:
    return f"Task {task_id} threshold"


def plot_task_axis(
    ax: plt.Axes,
    df: pd.DataFrame,
    x_column: str,
    metric_columns: Sequence[str],
    column_colors: Dict[str, str],
    title: str,
    x_limits: Optional[Tuple[pd.Timestamp, pd.Timestamp]],
    marker_size: float,
    max_fill_gap_hours: float,
    x_tick_format: str,
    x_tick_rotation: float,
    y_label: str,
) -> None:
    ax.set_title(title, fontsize=10)
    ax.set_ylabel(y_label)
    ax.grid(True, axis="y", alpha=0.3, linestyle="--", linewidth=0.5)

    if x_limits is not None:
        ax.set_xlim(*x_limits)

    if df.empty:
        ax.text(0.5, 0.5, "No eligible rows", transform=ax.transAxes, ha="center", va="center", fontsize=9, color="dimgray")
        return

    work = df.dropna(subset=[x_column]).sort_values(x_column)
    if work.empty:
        ax.text(0.5, 0.5, f"No valid {x_column}", transform=ax.transAxes, ha="center", va="center", fontsize=9, color="dimgray")
        return

    ymax = 0.0
    any_plotted = False
    for column in metric_columns:
        subset = work[[x_column, column]].dropna(subset=[x_column, column])
        if subset.empty:
            continue
        any_plotted = True
        color = column_colors.get(column, "tab:blue")
        plot_df = build_plot_segments(work, x_column, column, max_fill_gap_hours)
        ax.plot(
            plot_df[x_column],
            plot_df[column],
            linewidth=1.0,
            alpha=0.85,
            color=color,
            zorder=2,
        )
        ax.scatter(
            subset[x_column],
            subset[column],
            s=marker_size,
            alpha=0.92,
            color=color,
            edgecolors="none",
            zorder=3,
        )
        ymax = max(ymax, float(pd.to_numeric(subset[column], errors="coerce").max()))

    if not any_plotted:
        ax.text(0.5, 0.82, f"No {y_label} values", transform=ax.transAxes, ha="center", va="center", fontsize=8, color="dimgray")
    elif ymax > 0:
        ax.set_ylim(0.0, ymax * 1.1)

    ax.xaxis.set_major_formatter(mdates.DateFormatter(x_tick_format))
    if x_tick_rotation:
        ax.tick_params(axis="x", labelrotation=x_tick_rotation)
        for tick in ax.get_xticklabels():
            tick.set_horizontalalignment("right")


def build_task_legend(
    metric_columns: Sequence[str],
    column_colors: Dict[str, str],
    label_fn=column_label,
) -> Tuple[List[object], List[str]]:
    handles: List[object] = []
    labels: List[str] = []
    for column in metric_columns:
        handles.append(
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="None",
                markersize=5,
                markerfacecolor=column_colors.get(column, "tab:blue"),
                markeredgewidth=0,
                color=column_colors.get(column, "tab:blue"),
            )
        )
        labels.append(label_fn(column))
    return handles, labels


def plot_placeholder_page(pdf: PdfPages, title: str, message: str) -> None:
    fig, ax = plt.subplots(figsize=(11, 8.5), constrained_layout=True)
    ax.axis("off")
    ax.text(0.5, 0.62, title, ha="center", va="center", fontsize=15, fontweight="bold")
    ax.text(0.5, 0.44, message, ha="center", va="center", fontsize=11, color="dimgray")
    pdf_save_rasterized_page(pdf, fig, dpi=150)
    plt.close(fig)


def plot_station_selected_offender_page(
    station: str,
    task_data: Dict[int, pd.DataFrame],
    tasks: Sequence[int],
    pdf: PdfPages,
    *,
    last_hours: float,
    panel_width_ratios: Tuple[float, float],
    marker_size: float,
    max_fill_gap_hours: float,
    metric_mode: str,
) -> None:
    n_rows = len(tasks)
    fig_height = max(9.0, 2.15 * n_rows)
    fig, axes = plt.subplots(
        n_rows,
        2,
        figsize=(16, fig_height),
        sharex="col",
        constrained_layout=True,
        gridspec_kw={"width_ratios": panel_width_ratios},
    )
    if n_rows == 1:
        axes = np.array([axes])

    fig.suptitle(
        f"{station} - Noise control by task ({metric_mode}){METADATA_STATUS_SUFFIX}",
        fontsize=13,
    )

    left_limits = collect_station_file_bounds(task_data)
    right_limits = collect_station_execution_bounds(task_data, last_hours)
    y_label = "%" if metric_mode == "percent" else "Rate [Hz]"

    for row_idx, task_id in enumerate(tasks):
        df = task_data.get(task_id, pd.DataFrame())
        metric_columns, resolved_mode = detect_metric_columns(df, metric_mode)
        colors = colour_map_for_columns(metric_columns)

        left_ax = axes[row_idx, 0]
        right_ax = axes[row_idx, 1]
        left_df = df[df["file_timestamp"].notna()] if not df.empty else df
        right_df = df[df["execution_timestamp"].notna()] if not df.empty else df

        if right_limits is not None and not right_df.empty:
            start, end = right_limits
            right_df = right_df[
                (right_df["execution_timestamp"] >= start)
                & (right_df["execution_timestamp"] <= end)
            ]

        resolved_y_label = "%" if resolved_mode == "percent" else "Rate [Hz]"
        plot_task_axis(
            ax=left_ax,
            df=left_df,
            x_column="file_timestamp",
            metric_columns=metric_columns,
            column_colors=colors,
            title=f"Task {task_id} - Basename timestamp",
            x_limits=left_limits,
            marker_size=marker_size,
            max_fill_gap_hours=max_fill_gap_hours,
            x_tick_format="%Y-%m-%d\n%H:%M",
            x_tick_rotation=0.0,
            y_label=resolved_y_label,
        )
        plot_task_axis(
            ax=right_ax,
            df=right_df,
            x_column="execution_timestamp",
            metric_columns=metric_columns,
            column_colors=colors,
            title=f"Task {task_id} - Exec. time",
            x_limits=right_limits,
            marker_size=marker_size,
            max_fill_gap_hours=max_fill_gap_hours,
            x_tick_format="%H:%M",
            x_tick_rotation=45.0,
            y_label=resolved_y_label,
        )

        if row_idx == n_rows - 1:
            left_ax.set_xlabel("Basename timestamp")
            right_ax.set_xlabel("Execution timestamp")

    pdf_save_rasterized_page(pdf, fig, dpi=150)
    plt.close(fig)


def plot_station_selected_offender_legend_page(
    station: str,
    task_data: Dict[int, pd.DataFrame],
    tasks: Sequence[int],
    pdf: PdfPages,
    metric_mode: str,
) -> None:
    row_weights: List[float] = []
    legend_specs: List[Tuple[int, List[object], List[str], str]] = []
    for task_id in tasks:
        df = task_data.get(task_id, pd.DataFrame())
        metric_columns, resolved_mode = detect_metric_columns(df, metric_mode)
        colors = colour_map_for_columns(metric_columns)
        handles, labels = build_task_legend(metric_columns, colors)
        legend_specs.append((task_id, handles, labels, resolved_mode))
        row_weights.append(max(1.0, 0.45 * max(len(handles), 1)))

    fig_height = max(6.0, 1.2 + sum(row_weights))
    fig, axes = plt.subplots(
        len(tasks),
        1,
        figsize=(14, fig_height),
        constrained_layout=True,
        gridspec_kw={"height_ratios": row_weights},
    )
    if len(tasks) == 1:
        axes = np.array([axes])

    fig.suptitle(f"{station} - Noise control legend{METADATA_STATUS_SUFFIX}", fontsize=13)

    for ax, (task_id, handles, labels, resolved_mode) in zip(axes, legend_specs):
        ax.axis("off")
        if not handles:
            ax.text(
                0.0,
                0.9,
                f"Task {task_id}: no legend entries.",
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=10,
                color="dimgray",
            )
            continue
        ncol = max(1, min(3, int(np.ceil(len(handles) / 10.0))))
        legend = ax.legend(
            handles,
            labels,
            loc="upper left",
            bbox_to_anchor=(0.0, 1.0),
            borderaxespad=0.0,
            fontsize=8,
            framealpha=0.85,
            ncol=ncol,
            title=f"Task {task_id} ({'%' if resolved_mode == 'percent' else 'rate'})",
            title_fontsize=10,
            columnspacing=1.2,
            handletextpad=0.5,
            labelspacing=0.5,
        )
        legend._legend_box.align = "left"

    pdf_save_rasterized_page(pdf, fig, dpi=150)
    plt.close(fig)


def plot_plane_combination_rate_axis(
    ax: plt.Axes,
    df: pd.DataFrame,
    x_column: str,
    combo_specs: Sequence[Tuple[str, str]],
    combo_colors: Dict[str, str],
    offender_norm: Normalize,
    *,
    title: str,
    x_limits: Optional[Tuple[pd.Timestamp, pd.Timestamp]],
    marker_size: float,
    max_fill_gap_hours: float,
    x_tick_format: str,
    x_tick_rotation: float,
) -> None:
    ax.set_title(title, fontsize=10)
    ax.set_ylabel("Clean TT rate [Hz]")
    ax.grid(True, axis="y", alpha=0.3, linestyle="--", linewidth=0.5)

    if x_limits is not None:
        ax.set_xlim(*x_limits)

    if df.empty:
        ax.text(0.5, 0.5, "No eligible rows", transform=ax.transAxes, ha="center", va="center", fontsize=9, color="dimgray")
        return

    work = df.dropna(subset=[x_column]).sort_values(x_column)
    if work.empty:
        ax.text(0.5, 0.5, f"No valid {x_column}", transform=ax.transAxes, ha="center", va="center", fontsize=9, color="dimgray")
        return

    ymax = 0.0
    any_plotted = False
    cmap = plt.get_cmap("viridis")
    for combo_idx, (combo_label, column_name) in enumerate(combo_specs):
        if column_name not in work.columns:
            continue
        subset = work[[x_column, column_name, "selected_offender_total_rate_hz"]].dropna(subset=[x_column, column_name])
        if subset.empty:
            continue
        any_plotted = True
        combo_color = combo_colors.get(combo_label, "tab:blue")
        marker = PLANE_COMBINATION_MARKERS[combo_idx % len(PLANE_COMBINATION_MARKERS)]
        plot_df = build_plot_segments(work, x_column, column_name, max_fill_gap_hours)
        ax.plot(
            plot_df[x_column],
            plot_df[column_name],
            linewidth=1.0,
            alpha=0.85,
            color=combo_color,
            zorder=2,
        )
        ax.scatter(
            subset[x_column],
            subset[column_name],
            c=subset["selected_offender_total_rate_hz"],
            cmap=cmap,
            norm=offender_norm,
            s=marker_size * 1.35,
            alpha=0.95,
            marker=marker,
            edgecolors=combo_color,
            linewidths=0.55,
            zorder=3,
        )
        ymax = max(ymax, float(pd.to_numeric(subset[column_name], errors="coerce").max()))

    if not any_plotted:
        ax.text(0.5, 0.82, "No clean TT rates", transform=ax.transAxes, ha="center", va="center", fontsize=8, color="dimgray")
    elif ymax > 0:
        ax.set_ylim(0.0, ymax * 1.1)

    ax.xaxis.set_major_formatter(mdates.DateFormatter(x_tick_format))
    if x_tick_rotation:
        ax.tick_params(axis="x", labelrotation=x_tick_rotation)
        for tick in ax.get_xticklabels():
            tick.set_horizontalalignment("right")

    handles = [
        Line2D(
            [0],
            [0],
            color=combo_colors.get(combo_label, "tab:blue"),
            linewidth=1.0,
            marker=PLANE_COMBINATION_MARKERS[idx % len(PLANE_COMBINATION_MARKERS)],
            markersize=5,
            markerfacecolor="white",
            markeredgewidth=0.8,
            markeredgecolor=combo_colors.get(combo_label, "tab:blue"),
            linestyle="-",
            label=combo_label,
        )
        for idx, (combo_label, _) in enumerate(combo_specs)
        if _ in work.columns
    ]
    if len(handles) > 1:
        ax.legend(handles=handles, loc="upper left", fontsize=8, framealpha=0.85, ncol=min(3, len(handles)))


def plot_station_plane_combination_rate_page(
    station: str,
    plane_rate_df: pd.DataFrame,
    pdf: PdfPages,
    *,
    last_hours: float,
    panel_width_ratios: Tuple[float, float],
    marker_size: float,
    max_fill_gap_hours: float,
) -> bool:
    if plane_rate_df.empty:
        return False

    fig_height = max(10.0, 2.2 * len(PLANE_COMBINATION_RATE_GROUPS))
    fig, axes = plt.subplots(
        len(PLANE_COMBINATION_RATE_GROUPS),
        2,
        figsize=(16, fig_height),
        sharex="col",
        constrained_layout=True,
        gridspec_kw={"width_ratios": panel_width_ratios},
    )
    if len(PLANE_COMBINATION_RATE_GROUPS) == 1:
        axes = np.array([axes])

    offender_values = pd.to_numeric(plane_rate_df["selected_offender_total_rate_hz"], errors="coerce").dropna()
    if offender_values.empty:
        return False
    offender_min = float(offender_values.min())
    offender_max = float(offender_values.max())
    if offender_min == offender_max:
        offender_max = offender_min + 1e-6
    offender_norm = Normalize(vmin=offender_min, vmax=offender_max)

    fig.suptitle(
        f"{station} - Task 1 clean trigger-type rates by plane combination{METADATA_STATUS_SUFFIX}\n"
        "point colour = total rate of rows with >=1 selected offender",
        fontsize=13,
    )

    left_limits = series_bounds(plane_rate_df["file_timestamp"])
    right_limits = collect_station_execution_bounds({1: plane_rate_df}, last_hours)
    combo_labels = [combo_label for _, specs in PLANE_COMBINATION_RATE_GROUPS for combo_label, _ in specs]
    combo_colors = {
        combo_label: colour
        for combo_label, colour in zip(combo_labels, plt.get_cmap("tab10").colors)
    }

    for row_idx, (group_label, combo_specs) in enumerate(PLANE_COMBINATION_RATE_GROUPS):
        left_ax = axes[row_idx, 0]
        right_ax = axes[row_idx, 1]
        left_df = plane_rate_df[plane_rate_df["file_timestamp"].notna()]
        right_df = plane_rate_df[plane_rate_df["execution_timestamp"].notna()]

        if right_limits is not None and not right_df.empty:
            start, end = right_limits
            right_df = right_df[
                (right_df["execution_timestamp"] >= start)
                & (right_df["execution_timestamp"] <= end)
            ]

        plot_plane_combination_rate_axis(
            left_ax,
            left_df,
            "file_timestamp",
            combo_specs,
            combo_colors,
            offender_norm,
            title=f"{group_label} - Basename timestamp",
            x_limits=left_limits,
            marker_size=marker_size,
            max_fill_gap_hours=max_fill_gap_hours,
            x_tick_format="%Y-%m-%d\n%H:%M",
            x_tick_rotation=0.0,
        )
        plot_plane_combination_rate_axis(
            right_ax,
            right_df,
            "execution_timestamp",
            combo_specs,
            combo_colors,
            offender_norm,
            title=f"{group_label} - Exec. time",
            x_limits=right_limits,
            marker_size=marker_size,
            max_fill_gap_hours=max_fill_gap_hours,
            x_tick_format="%H:%M",
            x_tick_rotation=45.0,
        )

        if row_idx == len(PLANE_COMBINATION_RATE_GROUPS) - 1:
            left_ax.set_xlabel("Basename timestamp")
            right_ax.set_xlabel("Execution timestamp")

    scalar_mappable = plt.cm.ScalarMappable(norm=offender_norm, cmap="viridis")
    scalar_mappable.set_array([])
    cbar = fig.colorbar(scalar_mappable, ax=axes, shrink=0.95, pad=0.01)
    cbar.set_label("Rows with >=1 selected offender [Hz]")

    pdf_save_rasterized_page(pdf, fig, dpi=150)
    plt.close(fig)
    return True


def plot_efficiency_axis(
    ax: plt.Axes,
    df: pd.DataFrame,
    x_column: str,
    metric_columns: Sequence[str],
    column_colors: Dict[str, str],
    title: str,
    x_limits: Optional[Tuple[pd.Timestamp, pd.Timestamp]],
    marker_size: float,
    max_fill_gap_hours: float,
    x_tick_format: str,
    x_tick_rotation: float,
    eff_y_min: float,
) -> None:
    ax.set_title(title, fontsize=10)
    ax.set_ylabel("Efficiency")
    ax.grid(True, axis="y", alpha=0.3, linestyle="--", linewidth=0.5)

    if x_limits is not None:
        ax.set_xlim(*x_limits)

    if df.empty:
        ax.text(0.5, 0.5, "No eligible rows", transform=ax.transAxes, ha="center", va="center", fontsize=9, color="dimgray")
        return

    work = df.dropna(subset=[x_column]).sort_values(x_column)
    if work.empty:
        ax.text(0.5, 0.5, f"No valid {x_column}", transform=ax.transAxes, ha="center", va="center", fontsize=9, color="dimgray")
        return

    ymin = 1.0
    ymax = 0.0
    any_plotted = False
    for column in metric_columns:
        subset = work[[x_column, column]].dropna(subset=[x_column, column])
        if subset.empty:
            continue
        any_plotted = True
        color = column_colors.get(column, "tab:blue")
        plot_df = build_plot_segments(work, x_column, column, max_fill_gap_hours)
        ax.plot(
            plot_df[x_column],
            plot_df[column],
            linewidth=1.0,
            alpha=0.85,
            color=color,
            zorder=2,
        )
        ax.scatter(
            subset[x_column],
            subset[column],
            s=marker_size,
            alpha=0.92,
            color=color,
            edgecolors="none",
            zorder=3,
        )
        numeric = pd.to_numeric(subset[column], errors="coerce")
        ymin = min(ymin, float(numeric.min()))
        ymax = max(ymax, float(numeric.max()))

    if not any_plotted:
        ax.text(0.5, 0.82, "No efficiency values", transform=ax.transAxes, ha="center", va="center", fontsize=8, color="dimgray")
    else:
        lower = min(float(eff_y_min), ymin - 0.02)
        upper = max(1.0, ymax + 0.02)
        if lower >= upper:
            upper = lower + 0.05
        ax.set_ylim(lower, upper)

    ax.xaxis.set_major_formatter(mdates.DateFormatter(x_tick_format))
    if x_tick_rotation:
        ax.tick_params(axis="x", labelrotation=x_tick_rotation)
        for tick in ax.get_xticklabels():
            tick.set_horizontalalignment("right")


def plot_station_efficiency_page(
    station: str,
    task_data: Dict[int, pd.DataFrame],
    pdf: PdfPages,
    *,
    task_id: int,
    last_hours: float,
    panel_width_ratios: Tuple[float, float],
    marker_size: float,
    max_fill_gap_hours: float,
    eff_y_min: float,
) -> bool:
    df = task_data.get(task_id, pd.DataFrame())
    columns_by_plane = detect_efficiency_columns(df)
    if not columns_by_plane:
        return False

    planes = sorted(columns_by_plane)
    fig_height = max(9.0, 2.15 * len(planes))
    fig, axes = plt.subplots(
        len(planes),
        2,
        figsize=(16, fig_height),
        sharex="col",
        constrained_layout=True,
        gridspec_kw={"width_ratios": panel_width_ratios},
    )
    if len(planes) == 1:
        axes = np.array([axes])

    fig.suptitle(
        f"{station} - {efficiency_report_title(task_id)}{METADATA_STATUS_SUFFIX}",
        fontsize=13,
    )

    left_limits = collect_station_file_bounds({task_id: df})
    right_limits = collect_station_execution_bounds({task_id: df}, last_hours)
    color_columns = [
        column
        for plane in planes
        for column in columns_by_plane[plane]
    ]
    colors = efficiency_colour_map_for_columns(color_columns)

    for row_idx, plane in enumerate(planes):
        left_ax = axes[row_idx, 0]
        right_ax = axes[row_idx, 1]
        metric_columns = columns_by_plane[plane]
        left_df = df[df["file_timestamp"].notna()] if not df.empty else df
        right_df = df[df["execution_timestamp"].notna()] if not df.empty else df

        if right_limits is not None and not right_df.empty:
            start, end = right_limits
            right_df = right_df[
                (right_df["execution_timestamp"] >= start)
                & (right_df["execution_timestamp"] <= end)
            ]

        plot_efficiency_axis(
            ax=left_ax,
            df=left_df,
            x_column="file_timestamp",
            metric_columns=metric_columns,
            column_colors=colors,
            title=f"Plane {plane} - Basename timestamp",
            x_limits=left_limits,
            marker_size=marker_size,
            max_fill_gap_hours=max_fill_gap_hours,
            x_tick_format="%Y-%m-%d\n%H:%M",
            x_tick_rotation=0.0,
            eff_y_min=eff_y_min,
        )
        plot_efficiency_axis(
            ax=right_ax,
            df=right_df,
            x_column="execution_timestamp",
            metric_columns=metric_columns,
            column_colors=colors,
            title=f"Plane {plane} - Exec. time",
            x_limits=right_limits,
            marker_size=marker_size,
            max_fill_gap_hours=max_fill_gap_hours,
            x_tick_format="%H:%M",
            x_tick_rotation=45.0,
            eff_y_min=eff_y_min,
        )

        if row_idx == len(planes) - 1:
            left_ax.set_xlabel("Basename timestamp")
            right_ax.set_xlabel("Execution timestamp")

    pdf_save_rasterized_page(pdf, fig, dpi=150)
    plt.close(fig)
    return True


def plot_station_efficiency_legend_page(
    station: str,
    task_data: Dict[int, pd.DataFrame],
    pdf: PdfPages,
    *,
    task_id: int,
) -> bool:
    df = task_data.get(task_id, pd.DataFrame())
    columns_by_plane = detect_efficiency_columns(df)
    if not columns_by_plane:
        return False

    sample_columns = columns_by_plane[sorted(columns_by_plane)[0]]
    color_columns = [
        column
        for plane in sorted(columns_by_plane)
        for column in columns_by_plane[plane]
    ]
    colors = efficiency_colour_map_for_columns(color_columns)
    handles, labels = build_task_legend(
        sample_columns,
        colors,
        label_fn=efficiency_column_label,
    )

    fig, ax = plt.subplots(figsize=(14, 6), constrained_layout=True)
    ax.axis("off")
    fig.suptitle(f"{station} - Task {task_id} efficiency threshold legend{METADATA_STATUS_SUFFIX}", fontsize=13)
    if not handles:
        ax.text(
            0.0,
            0.9,
            "No legend entries.",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=10,
            color="dimgray",
        )
    else:
        ncol = max(1, min(3, int(np.ceil(len(handles) / 8.0))))
        legend = ax.legend(
            handles,
            labels,
            loc="upper left",
            bbox_to_anchor=(0.0, 1.0),
            borderaxespad=0.0,
            fontsize=9,
            framealpha=0.85,
            ncol=ncol,
            title=efficiency_legend_title(task_id),
            title_fontsize=10,
            columnspacing=1.2,
            handletextpad=0.5,
            labelspacing=0.5,
        )
        legend._legend_box.align = "left"

    pdf_save_rasterized_page(pdf, fig, dpi=150)
    plt.close(fig)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot Task 1-3 noise-control metadata.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--stations", nargs="*", default=None)
    parser.add_argument("--tasks", nargs="*", default=None)
    parser.add_argument("--last-hours", type=float, default=None)
    parser.add_argument("--marker-size", type=float, default=None)
    parser.add_argument("--max-gap-hours", type=float, default=None)
    parser.add_argument(
        "--report-kind",
        choices=("all", "selected_offenders", "efficiency_thresholds", "plane_combination_rates"),
        default=None,
    )
    parser.add_argument("--metric-mode", choices=("rate_hz", "percent"), default=None)
    parser.add_argument("--efficiency-y-min", type=float, default=None)
    return parser.parse_args()


def render_selected_offender_report(
    output_path: Path,
    station_task_data: Dict[str, Dict[int, pd.DataFrame]],
    tasks: Sequence[int],
    *,
    last_hours: float,
    panel_width_ratios: Tuple[float, float],
    marker_size: float,
    max_fill_gap_hours: float,
    metric_mode: str,
    allow_placeholder: bool,
) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wrote_any = False
    with PdfPages(output_path) as pdf:
        for station, task_data in station_task_data.items():
            if all(df.empty for df in task_data.values()):
                continue
            plot_station_selected_offender_page(
                station,
                task_data,
                tasks,
                pdf,
                last_hours=last_hours,
                panel_width_ratios=panel_width_ratios,
                marker_size=marker_size,
                max_fill_gap_hours=max_fill_gap_hours,
                metric_mode=metric_mode,
            )
            plot_station_selected_offender_legend_page(
                station,
                task_data,
                tasks,
                pdf,
                metric_mode,
            )
            wrote_any = True

        if not wrote_any and allow_placeholder:
            plot_placeholder_page(
                pdf,
                "Noise-control selected offenders",
                f"No metadata rows found for mode '{metric_mode}'.",
            )
            wrote_any = True

    if not wrote_any:
        print(
            "[noise_control_metadata_plotter] No metadata rows found for selected stations/tasks.",
            file=sys.stderr,
        )
        return False

    print(f"[noise_control_metadata_plotter] Wrote {output_path}")
    return True


def render_efficiency_report(
    output_path: Path,
    station_task_data: Dict[str, Dict[int, pd.DataFrame]],
    *,
    task_id: int,
    last_hours: float,
    panel_width_ratios: Tuple[float, float],
    marker_size: float,
    max_fill_gap_hours: float,
    eff_y_min: float,
    allow_placeholder: bool,
) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wrote_any = False
    with PdfPages(output_path) as pdf:
        for station, task_data in station_task_data.items():
            station_page_written = plot_station_efficiency_page(
                station,
                task_data,
                pdf,
                task_id=task_id,
                last_hours=last_hours,
                panel_width_ratios=panel_width_ratios,
                marker_size=marker_size,
                max_fill_gap_hours=max_fill_gap_hours,
                eff_y_min=eff_y_min,
            )
            if not station_page_written:
                continue
            plot_station_efficiency_legend_page(station, task_data, pdf, task_id=task_id)
            wrote_any = True

        if not wrote_any and allow_placeholder:
            plot_placeholder_page(
                pdf,
                f"Noise-control Task {task_id} efficiency thresholds",
                f"No Task {task_id} cumulative efficiency metadata is available yet.{METADATA_STATUS_SUFFIX}",
            )
            wrote_any = True

    if not wrote_any:
        print(
            "[noise_control_metadata_plotter] No efficiency metadata rows found for selected stations/tasks.",
            file=sys.stderr,
        )
        return False

    print(f"[noise_control_metadata_plotter] Wrote {output_path}")
    return True


def render_plane_combination_rate_report(
    output_path: Path,
    station_task_data: Dict[str, Dict[int, pd.DataFrame]],
    *,
    last_hours: float,
    panel_width_ratios: Tuple[float, float],
    marker_size: float,
    max_fill_gap_hours: float,
    allow_placeholder: bool,
) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wrote_any = False
    with PdfPages(output_path) as pdf:
        for station, task_data in station_task_data.items():
            noise_df = task_data.get(1, pd.DataFrame())
            if noise_df.empty:
                noise_df = load_task_metadata(station, 1)
            trigger_df = load_task_trigger_type_metadata(station, 1)
            plane_rate_df = build_plane_combination_rate_dataframe(noise_df, trigger_df)
            station_page_written = plot_station_plane_combination_rate_page(
                station,
                plane_rate_df,
                pdf,
                last_hours=last_hours,
                panel_width_ratios=panel_width_ratios,
                marker_size=marker_size,
                max_fill_gap_hours=max_fill_gap_hours,
            )
            wrote_any |= station_page_written

        if not wrote_any and allow_placeholder:
            plot_placeholder_page(
                pdf,
                "Noise-control plane-combination rates",
                f"No Task 1 noise-control and trigger-type metadata overlap is available yet.{METADATA_STATUS_SUFFIX}",
            )
            wrote_any = True

    if not wrote_any:
        print(
            "[noise_control_metadata_plotter] No plane-combination rate metadata rows found for selected stations.",
            file=sys.stderr,
        )
        return False

    print(f"[noise_control_metadata_plotter] Wrote {output_path}")
    return True


def main() -> int:
    configure_matplotlib_style()
    args = parse_args()
    config = load_config(args.config)

    stations = resolve_station_selection(args.stations if args.stations is not None else config.get("stations", []))
    tasks = normalize_task_selection(args.tasks if args.tasks is not None else config.get("tasks", list(TASK_IDS)))
    last_hours = float(args.last_hours if args.last_hours is not None else config.get("last_hours", DEFAULT_LAST_HOURS))
    panel_width_raw = config.get("panel_width_ratios", list(DEFAULT_PANEL_WIDTH_RATIOS))
    panel_width_ratios = (float(panel_width_raw[0]), float(panel_width_raw[1]))
    marker_size = float(args.marker_size if args.marker_size is not None else config.get("marker_size", DEFAULT_MARKER_SIZE))
    max_fill_gap_hours = float(args.max_gap_hours if args.max_gap_hours is not None else config.get("max_fill_gap_hours", DEFAULT_MAX_FILL_GAP_HOURS))
    report_kind = str(args.report_kind if args.report_kind is not None else config.get("report_kind", DEFAULT_REPORT_KIND)).strip().lower()
    if report_kind not in {"all", "selected_offenders", "efficiency_thresholds", "plane_combination_rates"}:
        raise ValueError("report_kind must be 'all', 'selected_offenders', 'efficiency_thresholds', or 'plane_combination_rates'")
    metric_mode = str(args.metric_mode if args.metric_mode is not None else config.get("metric_mode", DEFAULT_METRIC_MODE)).strip().lower()
    if metric_mode not in {"rate_hz", "percent"}:
        raise ValueError("metric_mode must be 'rate_hz' or 'percent'")
    eff_y_min = float(
        args.efficiency_y_min
        if args.efficiency_y_min is not None
        else config.get("efficiency_y_min", DEFAULT_EFFICIENCY_Y_MIN)
    )

    if not stations:
        print("[noise_control_metadata_plotter] No stations selected.", file=sys.stderr)
        return 1

    station_task_data = {
        station: {task_id: load_task_metadata(station, task_id) for task_id in tasks}
        for station in stations
    }

    bundle_mode = (
        report_kind == "all"
        and args.output is None
        and args.metric_mode is None
    )
    if bundle_mode:
        outputs = resolve_bundle_outputs(config)
        ok = True
        ok &= render_selected_offender_report(
            outputs["selected_offenders_percent"],
            station_task_data,
            tasks,
            last_hours=last_hours,
            panel_width_ratios=panel_width_ratios,
            marker_size=marker_size,
            max_fill_gap_hours=max_fill_gap_hours,
            metric_mode="percent",
            allow_placeholder=True,
        )
        ok &= render_selected_offender_report(
            outputs["selected_offenders_rate_hz"],
            station_task_data,
            tasks,
            last_hours=last_hours,
            panel_width_ratios=panel_width_ratios,
            marker_size=marker_size,
            max_fill_gap_hours=max_fill_gap_hours,
            metric_mode="rate_hz",
            allow_placeholder=True,
        )
        ok &= render_efficiency_report(
            outputs["task_1_efficiency_thresholds"],
            station_task_data,
            task_id=1,
            last_hours=last_hours,
            panel_width_ratios=panel_width_ratios,
            marker_size=marker_size,
            max_fill_gap_hours=max_fill_gap_hours,
            eff_y_min=eff_y_min,
            allow_placeholder=True,
        )
        ok &= render_efficiency_report(
            outputs["task_2_efficiency_thresholds"],
            station_task_data,
            task_id=2,
            last_hours=last_hours,
            panel_width_ratios=panel_width_ratios,
            marker_size=marker_size,
            max_fill_gap_hours=max_fill_gap_hours,
            eff_y_min=eff_y_min,
            allow_placeholder=True,
        )
        ok &= render_efficiency_report(
            outputs["task_3_efficiency_thresholds"],
            station_task_data,
            task_id=3,
            last_hours=last_hours,
            panel_width_ratios=panel_width_ratios,
            marker_size=marker_size,
            max_fill_gap_hours=max_fill_gap_hours,
            eff_y_min=eff_y_min,
            allow_placeholder=True,
        )
        ok &= render_plane_combination_rate_report(
            outputs["plane_combination_rates"],
            station_task_data,
            last_hours=last_hours,
            panel_width_ratios=panel_width_ratios,
            marker_size=marker_size,
            max_fill_gap_hours=max_fill_gap_hours,
            allow_placeholder=True,
        )
        return 0 if ok else 1

    if report_kind == "all":
        report_kind = "selected_offenders"

    output_path = resolve_output_path(
        args.output,
        report_kind=report_kind,
        metric_mode=metric_mode,
    )
    if report_kind == "selected_offenders":
        ok = render_selected_offender_report(
            output_path,
            station_task_data,
            tasks,
            last_hours=last_hours,
            panel_width_ratios=panel_width_ratios,
            marker_size=marker_size,
            max_fill_gap_hours=max_fill_gap_hours,
            metric_mode=metric_mode,
            allow_placeholder=bool(METADATA_STATUS_SUFFIX),
        )
    elif report_kind == "efficiency_thresholds":
        ok = render_efficiency_report(
            output_path,
            station_task_data,
            task_id=tasks[0] if tasks else 1,
            last_hours=last_hours,
            panel_width_ratios=panel_width_ratios,
            marker_size=marker_size,
            max_fill_gap_hours=max_fill_gap_hours,
            eff_y_min=eff_y_min,
            allow_placeholder=bool(METADATA_STATUS_SUFFIX),
        )
    else:
        ok = render_plane_combination_rate_report(
            output_path,
            station_task_data,
            last_hours=last_hours,
            panel_width_ratios=panel_width_ratios,
            marker_size=marker_size,
            max_fill_gap_hours=max_fill_gap_hours,
            allow_placeholder=bool(METADATA_STATUS_SUFFIX),
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
