#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/METADATA/FILTER/filter_metadata_plotter.py
Purpose: Generate Stage 1 filter-metadata plots with Stage 0 basename gating.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/METADATA/FILTER/filter_metadata_plotter.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

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
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


SCRIPT_PATH = Path(__file__).resolve()


def detect_repo_root() -> Path:
    for parent in SCRIPT_PATH.parents:
        if (parent / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS").is_dir() and (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file():
            return parent
    raise RuntimeError(f"Could not locate repository root from {SCRIPT_PATH}")


REPO_ROOT = detect_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.plot_utils import (  # noqa: E402
    metadata_output_status_suffix,
    pdf_save_rasterized_page,
)


STATIONS_ROOT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
PLOTTER_DIR = SCRIPT_PATH.parent
PLOTS_DIR = PLOTTER_DIR / "PLOTS"
DEFAULT_CONFIG_PATH = PLOTTER_DIR / "filter_metadata_config.json"
DEFAULT_OUTPUT_FILENAME = "filter_metadata_report.pdf"

TASK_IDS: Tuple[int, ...] = (1, 2, 3, 4, 5)
DEFAULT_LAST_HOURS = 2.0
DEFAULT_PANEL_WIDTH_RATIOS: Tuple[float, float] = (5.0, 1.0)
DEFAULT_MARKER_SIZE = 14.0
DEFAULT_Y_MAX_PERCENT = 10.0
DEFAULT_LEGEND_MIN_PERCENT = 1.0
DEFAULT_MAX_FILL_GAP_HOURS = 3.0
METADATA_STATUS_SUFFIX = metadata_output_status_suffix("filter")

METADATA_FILENAME_TEMPLATE = "task_{task_id}_metadata_filter.csv"
METADATA_TIMESTAMP_FMT = "%Y-%m-%d_%H.%M.%S"
BASENAME_TIMESTAMP_DIGITS = 11
FILENAME_TIMESTAMP_PATTERN = re.compile(r"mi0\d(\d{11})$", re.IGNORECASE)

PURITY_COLUMN = "data_purity_percentage"
EXCLUDED_COLUMNS: Set[str] = {
    "filename_base",
    "basename",
    "execution_timestamp",
    "file_timestamp",
    PURITY_COLUMN,
}


def configure_matplotlib_style() -> None:
    plt.style.use("default")


def normalize_basename(value: object) -> str:
    text = str(value).strip()
    if not text:
        return ""
    return Path(text).stem.strip()


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


def resolve_station_selection(tokens: Sequence[str]) -> List[str]:
    available = list_available_stations()
    if not tokens:
        return available

    selected: List[str] = []
    invalid: List[str] = []
    for token in tokens:
        station = normalize_station_token(str(token))
        if station is None or station not in available:
            invalid.append(str(token))
            continue
        selected.append(station)

    if invalid:
        print(
            "[filter_metadata_plotter] Ignoring unknown station(s): "
            + ", ".join(invalid),
            file=sys.stderr,
        )

    return sorted(dict.fromkeys(selected))


def normalize_existing_station_tokens(tokens: Sequence[object]) -> List[str]:
    available = set(list_available_stations())
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
    if not (0 <= hour <= 23):
        return None
    if not (0 <= minute <= 59):
        return None
    if not (0 <= second <= 59):
        return None

    base = datetime(year, 1, 1)
    return base + timedelta(
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


def first_existing_column(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for value in values:
        candidate = value.strip()
        if not candidate or candidate in seen:
            continue
        ordered.append(candidate)
        seen.add(candidate)
    return ordered


def _station_token_map(station: str) -> Dict[str, str]:
    clean = station.strip()
    tokens: Dict[str, str] = {
        "station": clean,
        "station_lower": clean.lower(),
        "station_upper": clean.upper(),
    }
    digits = "".join(ch for ch in clean if ch.isdigit())
    if digits:
        stripped = digits.lstrip("0") or "0"
        tokens["id"] = stripped
        tokens["id02"] = stripped.zfill(2)
        tokens["mingo_id"] = f"mingo{stripped}"
        tokens["mingo_id02"] = f"mingo{tokens['id02']}"
    return tokens


def _station_file_candidates(
    station: str,
    patterns: Sequence[str],
    fallback: Optional[str] = None,
) -> List[str]:
    tokens = _station_token_map(station)
    generated: List[str] = []
    for pattern in patterns:
        try:
            generated.append(pattern.format(**tokens))
        except KeyError:
            continue
    if fallback:
        generated.append(fallback)
    return _ordered_unique(generated)


def _resolve_station_metadata_file(
    directory: Path,
    station: str,
    patterns: Sequence[str],
    fallback: Optional[str] = None,
) -> Optional[Path]:
    for filename in _station_file_candidates(station, patterns, fallback):
        candidate = directory / filename
        if candidate.exists():
            return candidate
    return None


def load_allowed_basenames(station: str) -> Set[str]:
    root = STATIONS_ROOT / station

    if station == "MINGO00":
        stage0_history_csv = root / "STAGE_0" / "SIMULATION" / "imported_basenames_history.csv"
        stage0_live_csv = root / "STAGE_0" / "SIMULATION" / "imported_basenames.csv"
        stage0_csv = stage0_history_csv if stage0_history_csv.exists() else stage0_live_csv
    else:
        metadata_dir = root / "STAGE_0" / "REPROCESSING" / "STEP_0" / "OUTPUT_FILES"
        stage0_csv = _resolve_station_metadata_file(
            metadata_dir,
            station,
            (
                "clean_remote_database_{id}.csv",
                "clean_remote_database_{id02}.csv",
                "clean_remote_database_{station_lower}.csv",
                "clean_remote_database_{station}.csv",
                "clean_remote_database_{mingo_id}.csv",
                "clean_remote_database_{mingo_id02}.csv",
            ),
        )

    if stage0_csv is None or not stage0_csv.exists():
        print(
            f"[filter_metadata_plotter] Stage 0 basename source missing for {station}.",
            file=sys.stderr,
        )
        return set()

    try:
        df = pd.read_csv(stage0_csv)
    except Exception as exc:  # pragma: no cover - defensive
        print(
            f"[filter_metadata_plotter] Failed to read {stage0_csv}: {exc}",
            file=sys.stderr,
        )
        return set()

    basename_col = first_existing_column(
        df.columns,
        ("basename", "filename_base", "hld_name", "dat_name"),
    )
    if basename_col is None:
        print(
            f"[filter_metadata_plotter] Missing basename column in {stage0_csv}.",
            file=sys.stderr,
        )
        return set()

    basenames = {
        normalize_basename(value)
        for value in df[basename_col].astype(str)
        if normalize_basename(value)
    }
    return basenames


def load_task_metadata(station: str, task_id: int, allowed_basenames: Set[str]) -> pd.DataFrame:
    metadata_csv = (
        STATIONS_ROOT
        / station
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / f"TASK_{task_id}"
        / "METADATA"
        / METADATA_FILENAME_TEMPLATE.format(task_id=task_id)
    )

    if not metadata_csv.exists():
        return pd.DataFrame()

    try:
        df = pd.read_csv(metadata_csv)
    except Exception as exc:  # pragma: no cover - defensive
        print(
            f"[filter_metadata_plotter] Failed to read {metadata_csv}: {exc}",
            file=sys.stderr,
        )
        return pd.DataFrame()

    if df.empty or "filename_base" not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df["basename"] = df["filename_base"].map(normalize_basename)
    df = df[df["basename"].str.startswith("mi", na=False)]

    if allowed_basenames:
        df = df[df["basename"].isin(allowed_basenames)]
    else:
        # User requested clean_remote/imported-only plotting. If baseline is empty, no row is eligible.
        df = df.iloc[0:0]

    if df.empty:
        return pd.DataFrame()

    if "execution_timestamp" in df.columns:
        df["execution_timestamp"] = parse_execution_series(df["execution_timestamp"])
    else:
        df["execution_timestamp"] = pd.NaT

    df["file_timestamp"] = pd.to_datetime(
        df["basename"].map(extract_timestamp_from_basename),
        errors="coerce",
    )

    if PURITY_COLUMN not in df.columns:
        df[PURITY_COLUMN] = float("nan")

    skip_numeric = {"filename_base", "basename", "execution_timestamp", "file_timestamp"}
    for column in df.columns:
        if column in skip_numeric:
            continue
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df[
        df["basename"].ne("")
        & (df["file_timestamp"].notna() | df["execution_timestamp"].notna())
    ]

    if df.empty:
        return pd.DataFrame()

    return df.sort_values("file_timestamp").reset_index(drop=True)


def detect_filter_columns(df: pd.DataFrame) -> List[str]:
    preferred: List[str] = []
    fallback: List[str] = []

    for column in df.columns:
        if column in EXCLUDED_COLUMNS:
            continue

        series = df[column]
        if not pd.api.types.is_numeric_dtype(series):
            continue
        if series.dropna().empty:
            continue

        fallback.append(column)
        lowered = column.lower()
        if "pct" in lowered or "percent" in lowered:
            preferred.append(column)

    return preferred if preferred else fallback


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


def colour_map_for_columns(columns: Sequence[str]) -> Dict[str, str]:
    cmap = plt.get_cmap("tab20")
    mapping: Dict[str, str] = {}
    for idx, column in enumerate(columns):
        mapping[column] = cmap(idx % cmap.N)
    return mapping


def plot_task_axis(
    ax: plt.Axes,
    df: pd.DataFrame,
    x_column: str,
    filter_columns: Sequence[str],
    column_colors: Dict[str, str],
    title: str,
    x_limits: Optional[Tuple[pd.Timestamp, pd.Timestamp]],
    marker_size: float,
    y_max_percent: float,
    legend_min_percent: float,
    max_fill_gap_hours: float,
    show_legend: bool,
    x_tick_format: str,
    x_tick_rotation: float,
) -> None:
    ax.set_title(title, fontsize=10)
    ax.set_ylabel("%")
    ax.set_ylim(0.0, y_max_percent)
    ax.grid(True, axis="y", alpha=0.3, linestyle="--", linewidth=0.5)

    if x_limits is not None:
        ax.set_xlim(*x_limits)

    if df.empty:
        ax.text(
            0.5,
            0.5,
            "No eligible rows",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=9,
            color="dimgray",
        )
        return

    work = df.dropna(subset=[x_column]).sort_values(x_column)
    if work.empty:
        ax.text(
            0.5,
            0.5,
            f"No valid {x_column}",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=9,
            color="dimgray",
        )
        return

    legend_handles: List[object] = []
    legend_labels: List[str] = []
    points_by_column: Dict[str, pd.DataFrame] = {}
    visible_points_by_column: Dict[str, pd.DataFrame] = {}
    for column in filter_columns:
        subset = work[[x_column, column]].dropna(subset=[x_column, column])
        if subset.empty:
            continue
        points_by_column[column] = subset
        visible_subset = subset[
            (subset[column] >= 0.0) & (subset[column] <= y_max_percent)
        ]
        if not visible_subset.empty:
            visible_points_by_column[column] = visible_subset

    plotted = bool(points_by_column)
    visible_plotted = bool(visible_points_by_column)

    purity = pd.to_numeric(work.get(PURITY_COLUMN), errors="coerce")
    if visible_plotted and purity.notna().any():
        purity = purity.clip(lower=0.0, upper=100.0)
        if filter_columns:
            row_with_visible_point = pd.Series(False, index=work.index)
            for column in filter_columns:
                if column not in work.columns:
                    continue
                row_with_visible_point = row_with_visible_point | (
                    work[column].between(0.0, y_max_percent)
                )
        else:
            row_with_visible_point = pd.Series(False, index=work.index)

        fill_x = work.loc[row_with_visible_point, x_column]
        fill_purity = purity.loc[row_with_visible_point]
        fill_valid = fill_x.notna() & fill_purity.notna()
        fill_x = fill_x.loc[fill_valid]
        fill_purity = fill_purity.loc[fill_valid]
        if not fill_x.empty:
            fill_data = pd.DataFrame(
                {
                    "x": pd.to_datetime(fill_x, errors="coerce"),
                    "purity": pd.to_numeric(fill_purity, errors="coerce"),
                }
            ).dropna(subset=["x", "purity"])
            fill_data = fill_data.sort_values("x").reset_index(drop=True)

            filled_purity_chunks: List[pd.Series] = []
            max_gap = pd.Timedelta(hours=max_fill_gap_hours)
            segment_id = (fill_data["x"].diff() > max_gap).cumsum()
            for _, segment in fill_data.groupby(segment_id):
                if len(segment) < 2:
                    continue
                lower = 100.0 - segment["purity"]
                ax.fill_between(
                    segment["x"],
                    lower,
                    100.0,
                    color="green",
                    alpha=0.14,
                    zorder=1,
                )
                filled_purity_chunks.append(segment["purity"])

            if filled_purity_chunks:
                purity_deficit = (
                    100.0 - pd.concat(filled_purity_chunks, ignore_index=True)
                ).dropna()
            else:
                purity_deficit = pd.Series(dtype=float)

            if show_legend and not purity_deficit.empty and float(purity_deficit.max()) > legend_min_percent:
                legend_handles.append(Patch(facecolor="green", edgecolor="none", alpha=0.14))
                legend_labels.append("Purity region (100-purity to 100)")

    for column, subset in points_by_column.items():

        scatter = ax.scatter(
            subset[x_column],
            subset[column],
            s=marker_size,
            alpha=0.9,
            color=column_colors.get(column, "tab:blue"),
            edgecolors="none",
            zorder=3,
        )
        if show_legend and float(subset[column].max()) > legend_min_percent:
            legend_handles.append(scatter)
            legend_labels.append(column)

    if not plotted:
        ax.text(
            0.5,
            0.82,
            "No filter % values",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=8,
            color="dimgray",
        )

    if show_legend and legend_handles:
        ax.legend(
            legend_handles,
            legend_labels,
            loc="upper left",
            bbox_to_anchor=(1.01, 1.0),
            borderaxespad=0.0,
            fontsize=7,
            framealpha=0.85,
        )

    if x_column == "execution_timestamp":
        now = pd.Timestamp.utcnow()
        ax.axvline(now, color="red", linestyle="--", alpha=0.3, zorder=10)

    ax.xaxis.set_major_formatter(mdates.DateFormatter(x_tick_format))
    if x_tick_rotation:
        ax.tick_params(axis="x", labelrotation=x_tick_rotation)
        for tick in ax.get_xticklabels():
            tick.set_horizontalalignment("right")


def build_task_legend(
    df: pd.DataFrame,
    filter_columns: Sequence[str],
    column_colors: Dict[str, str],
    legend_min_percent: float,
    y_max_percent: float,
) -> Tuple[List[object], List[str]]:
    handles: List[object] = []
    labels: List[str] = []

    if df.empty:
        return handles, labels

    visible_filter_points = False
    for column in filter_columns:
        if column not in df.columns:
            continue
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        if series.empty:
            continue
        if series.between(0.0, y_max_percent).any():
            visible_filter_points = True
        if float(series.max()) >= legend_min_percent:
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
            labels.append(column)

    purity = pd.to_numeric(df.get(PURITY_COLUMN), errors="coerce")
    if visible_filter_points and purity.notna().any():
        purity_deficit = (100.0 - purity.clip(lower=0.0, upper=100.0)).dropna()
        if not purity_deficit.empty and float(purity_deficit.max()) >= legend_min_percent:
            handles.insert(0, Patch(facecolor="green", edgecolor="none", alpha=0.14))
            labels.insert(0, "Purity region (100-purity to 100)")

    return handles, labels


def plot_station_page(
    station: str,
    task_data: Dict[int, pd.DataFrame],
    tasks: Sequence[int],
    pdf: PdfPages,
    last_hours: float,
    panel_width_ratios: Tuple[float, float],
    marker_size: float,
    y_max_percent: float,
    legend_min_percent: float,
    max_fill_gap_hours: float,
) -> None:
    n_rows = len(tasks)
    fig_height = max(10.0, 2.15 * n_rows)
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
        f"{station} - Filter metadata by task (clean_remote/imported basenames only){METADATA_STATUS_SUFFIX}",
        fontsize=13,
    )

    left_limits = collect_station_file_bounds(task_data)
    right_limits = collect_station_execution_bounds(task_data, last_hours)
    station_max_fill_gap_hours = 876000.0 if station == "MINGO00" else max_fill_gap_hours

    for row_idx, task_id in enumerate(tasks):
        df = task_data.get(task_id, pd.DataFrame())
        filter_columns = detect_filter_columns(df)
        colors = colour_map_for_columns(filter_columns)

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

        plot_task_axis(
            ax=left_ax,
            df=left_df,
            x_column="file_timestamp",
            filter_columns=filter_columns,
            column_colors=colors,
            title=f"Task {task_id} - Basename timestamp",
            x_limits=left_limits,
            marker_size=marker_size,
            y_max_percent=y_max_percent,
            legend_min_percent=legend_min_percent,
            max_fill_gap_hours=station_max_fill_gap_hours,
            show_legend=False,
            x_tick_format="%Y-%m-%d\n%H:%M",
            x_tick_rotation=0.0,
        )

        right_title = f"Task {task_id} - Exec. time"
        plot_task_axis(
            ax=right_ax,
            df=right_df,
            x_column="execution_timestamp",
            filter_columns=filter_columns,
            column_colors=colors,
            title=right_title,
            x_limits=right_limits,
            marker_size=marker_size,
            y_max_percent=y_max_percent,
            legend_min_percent=legend_min_percent,
            max_fill_gap_hours=station_max_fill_gap_hours,
            show_legend=False,
            x_tick_format="%H:%M",
            x_tick_rotation=45.0,
        )

        if row_idx == n_rows - 1:
            left_ax.set_xlabel("Basename timestamp")
            right_ax.set_xlabel("Execution timestamp")

    pdf_save_rasterized_page(pdf, fig, dpi=150)
    plt.close(fig)


def plot_station_legend_page(
    station: str,
    task_data: Dict[int, pd.DataFrame],
    tasks: Sequence[int],
    pdf: PdfPages,
    legend_min_percent: float,
    y_max_percent: float,
) -> None:
    legend_specs: List[Tuple[int, List[object], List[str]]] = []
    row_weights: List[float] = []

    for task_id in tasks:
        df = task_data.get(task_id, pd.DataFrame())
        filter_columns = detect_filter_columns(df)
        colors = colour_map_for_columns(filter_columns)
        handles, labels = build_task_legend(
            df=df,
            filter_columns=filter_columns,
            column_colors=colors,
            legend_min_percent=legend_min_percent,
            y_max_percent=y_max_percent,
        )
        legend_specs.append((task_id, handles, labels))
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

    fig.suptitle(
        f"{station} - Filter metadata legend{METADATA_STATUS_SUFFIX}",
        fontsize=13,
    )

    for ax, (task_id, handles, labels) in zip(axes, legend_specs):
        ax.axis("off")
        if not handles:
            ax.text(
                0.0,
                0.9,
                f"Task {task_id}: no legend entries above threshold.",
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
            title=f"Task {task_id}",
            title_fontsize=10,
            columnspacing=1.2,
            handletextpad=0.5,
            labelspacing=0.5,
        )
        legend._legend_box.align = "left"

    pdf_save_rasterized_page(pdf, fig, dpi=150)
    plt.close(fig)


def default_output_path() -> Path:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    return PLOTS_DIR / DEFAULT_OUTPUT_FILENAME


def load_config(config_path: Path) -> Dict[str, object]:
    if not config_path.exists():
        return {}

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"Failed to parse config JSON {config_path}: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ValueError(f"Config file must contain a JSON object: {config_path}")
    return loaded


def resolve_output_path(raw_output: Optional[str], config_path: Path) -> Path:
    if not raw_output:
        return default_output_path()
    candidate = Path(raw_output).expanduser()
    if candidate.is_absolute():
        return candidate
    return (config_path.parent / candidate).resolve()


def resolve_runtime_options(
    args: argparse.Namespace,
) -> Tuple[List[str], List[int], float, Tuple[float, float], float, float, float, float, Path]:
    config_path = Path(args.config).expanduser()
    config = load_config(config_path)

    if args.stations is not None:
        stations = resolve_station_selection(args.stations)
    else:
        cfg_stations = config.get("stations", [])
        if not isinstance(cfg_stations, list):
            raise ValueError("'stations' in config must be a list")
        normalized = normalize_existing_station_tokens(cfg_stations)
        stations = normalized if normalized else list_available_stations()

    if args.tasks is not None:
        tasks = normalize_task_selection(args.tasks)
    else:
        cfg_tasks = config.get("tasks", list(TASK_IDS))
        if not isinstance(cfg_tasks, list):
            raise ValueError("'tasks' in config must be a list")
        tasks = normalize_task_selection(cfg_tasks)

    if args.last_hours is not None:
        last_hours = float(args.last_hours)
    else:
        try:
            last_hours = float(config.get("last_hours", DEFAULT_LAST_HOURS))
        except (TypeError, ValueError):
            raise ValueError("'last_hours' in config must be numeric")

    if last_hours <= 0:
        raise ValueError("last_hours must be > 0")

    panel_width_raw = config.get("panel_width_ratios", list(DEFAULT_PANEL_WIDTH_RATIOS))
    if not isinstance(panel_width_raw, list) or len(panel_width_raw) != 2:
        raise ValueError("'panel_width_ratios' in config must be a list of 2 numeric values")

    try:
        panel_width_ratios = (float(panel_width_raw[0]), float(panel_width_raw[1]))
    except (TypeError, ValueError):
        raise ValueError("'panel_width_ratios' in config must contain numeric values")

    if panel_width_ratios[0] <= 0 or panel_width_ratios[1] <= 0:
        raise ValueError("'panel_width_ratios' values must be > 0")

    if args.marker_size is not None:
        marker_size = float(args.marker_size)
    else:
        try:
            marker_size = float(config.get("marker_size", DEFAULT_MARKER_SIZE))
        except (TypeError, ValueError):
            raise ValueError("'marker_size' in config must be numeric")

    try:
        y_max_percent = float(config.get("y_max_percent", DEFAULT_Y_MAX_PERCENT))
    except (TypeError, ValueError):
        raise ValueError("'y_max_percent' in config must be numeric")
    if y_max_percent <= 0:
        raise ValueError("'y_max_percent' in config must be > 0")

    try:
        legend_min_percent = float(
            config.get("legend_min_percent", DEFAULT_LEGEND_MIN_PERCENT)
        )
    except (TypeError, ValueError):
        raise ValueError("'legend_min_percent' in config must be numeric")
    if legend_min_percent < 0:
        raise ValueError("'legend_min_percent' in config must be >= 0")

    try:
        max_fill_gap_hours = float(
            config.get("max_fill_gap_hours", DEFAULT_MAX_FILL_GAP_HOURS)
        )
    except (TypeError, ValueError):
        raise ValueError("'max_fill_gap_hours' in config must be numeric")
    if max_fill_gap_hours <= 0:
        raise ValueError("'max_fill_gap_hours' in config must be > 0")

    output_raw = args.output
    if output_raw is None:
        config_output = config.get("output")
        output_raw = str(config_output) if config_output is not None else None
    output_path = resolve_output_path(output_raw, config_path)

    return (
        stations,
        tasks,
        last_hours,
        panel_width_ratios,
        marker_size,
        y_max_percent,
        legend_min_percent,
        max_fill_gap_hours,
        output_path,
    )


def ensure_output_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate filter metadata report with clean_remote/imported basename gating."
        )
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Path to JSON config (default: {DEFAULT_CONFIG_PATH}).",
    )
    parser.add_argument(
        "--stations",
        nargs="+",
        default=None,
        help="Station selection override (e.g. MINGO00 MINGO01).",
    )
    parser.add_argument(
        "--tasks",
        nargs="+",
        type=int,
        default=None,
        help="Task id override (subset of 1 2 3 4 5).",
    )
    parser.add_argument(
        "--last-hours",
        type=float,
        default=None,
        help="Right-column execution-time window in hours (default from config).",
    )
    parser.add_argument(
        "--marker-size",
        type=float,
        default=None,
        help="Scatter marker size (default from config).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output PDF path override (absolute or config-relative).",
    )
    return parser


def main() -> None:
    configure_matplotlib_style()
    args = build_parser().parse_args()

    (
        stations,
        tasks,
        last_hours,
        panel_width_ratios,
        marker_size,
        y_max_percent,
        legend_min_percent,
        max_fill_gap_hours,
        output_path,
    ) = resolve_runtime_options(args)

    if not stations:
        raise RuntimeError("No stations selected or discovered.")

    ensure_output_directory(output_path)

    with PdfPages(output_path) as pdf:
        for station in stations:
            allowed_basenames = load_allowed_basenames(station)
            station_task_data: Dict[int, pd.DataFrame] = {}
            for task_id in tasks:
                station_task_data[task_id] = load_task_metadata(
                    station=station,
                    task_id=task_id,
                    allowed_basenames=allowed_basenames,
                )

            plot_station_page(
                station=station,
                task_data=station_task_data,
                tasks=tasks,
                pdf=pdf,
                last_hours=last_hours,
                panel_width_ratios=panel_width_ratios,
                marker_size=marker_size,
                y_max_percent=y_max_percent,
                legend_min_percent=legend_min_percent,
                max_fill_gap_hours=max_fill_gap_hours,
            )
            plot_station_legend_page(
                station=station,
                task_data=station_task_data,
                tasks=tasks,
                pdf=pdf,
                legend_min_percent=legend_min_percent,
                y_max_percent=y_max_percent,
            )

    print(f"Saved filter metadata report: {output_path}")


if __name__ == "__main__":
    main()
