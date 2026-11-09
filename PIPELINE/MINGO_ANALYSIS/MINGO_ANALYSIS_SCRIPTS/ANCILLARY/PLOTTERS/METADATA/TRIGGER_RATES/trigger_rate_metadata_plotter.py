#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/METADATA/TRIGGER_RATES/trigger_rate_metadata_plotter.py
Purpose: Plot final trigger-type rates by plane combination across Tasks 1-5.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-04-12
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/METADATA/TRIGGER_RATES/trigger_rate_metadata_plotter.py [options]
Inputs: Task trigger-type metadata CSVs and Stage 0 basename sources.
Outputs: PDF report under PLOTS/.
Notes: Plots only the main final trigger-rate columns, never the *_to_* transition columns.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


SCRIPT_PATH = Path(__file__).resolve()


def detect_repo_root() -> Path:
    for parent in SCRIPT_PATH.parents:
        if (parent / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS").is_dir() and (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file():
            return parent
    raise RuntimeError(f"Could not locate repository root from {SCRIPT_PATH}")


REPO_ROOT = detect_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.plot_utils import pdf_save_rasterized_page  # noqa: E402


STATIONS_ROOT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
PLOTTER_DIR = SCRIPT_PATH.parent
PLOTS_DIR = PLOTTER_DIR / "PLOTS"
DEFAULT_CONFIG_PATH = PLOTTER_DIR / "trigger_rate_metadata_config.json"
DEFAULT_OUTPUT_FILENAME = "trigger_rate_metadata_report.pdf"

TASK_IDS: Tuple[int, ...] = (1, 2, 3, 4, 5)
TASK_FINAL_PREFIX: Dict[int, str] = {
    1: "tt_task1_clean",
    2: "tt_task2_cal",
    3: "tt_task3_list",
    4: "tt_task4_fit",
    5: "tt_task5_post",
}
DEFAULT_TRIGGER_VALUES: Tuple[str, ...] = (
    "1234",
    "123",
    "124",
    "134",
    "234",
    "12",
    "13",
    "14",
    "23",
    "24",
    "34",
)
DEFAULT_LINE_WIDTH = 1.2
DEFAULT_MARKER_SIZE = 10.0
DEFAULT_Y_MIN_HZ = 0.0
DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_ONLY_RE = re.compile(r"^\d{4}-\d{2}$")
YEAR_ONLY_RE = re.compile(r"^\d{4}$")

METADATA_FILENAME_TEMPLATE = "task_{task_id}_metadata_trigger_type.csv"
METADATA_TIMESTAMP_FMT = "%Y-%m-%d_%H.%M.%S"
BASENAME_TIMESTAMP_DIGITS = 11
FILENAME_TIMESTAMP_PATTERN = re.compile(r"mi0\d(\d{11})$", re.IGNORECASE)


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
            "[trigger_rate_metadata_plotter] Ignoring unknown station(s): "
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


def normalize_trigger_values(values: Sequence[object]) -> List[str]:
    normalized: List[str] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        if not all(char in {"1", "2", "3", "4"} for char in text):
            continue
        normalized.append(text)
    deduped = list(dict.fromkeys(normalized))
    return deduped if deduped else list(DEFAULT_TRIGGER_VALUES)


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


def _next_month_start(ts: pd.Timestamp) -> pd.Timestamp:
    if ts.month == 12:
        return pd.Timestamp(year=ts.year + 1, month=1, day=1)
    return pd.Timestamp(year=ts.year, month=ts.month + 1, day=1)


def _next_year_start(ts: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(year=ts.year + 1, month=1, day=1)


def _parse_date_bound(raw_value: object, *, bound_name: str, is_end: bool) -> Optional[pd.Timestamp]:
    if raw_value in (None, ""):
        return None

    text = str(raw_value).strip()
    if not text:
        return None

    if YEAR_ONLY_RE.fullmatch(text):
        parsed = pd.Timestamp(year=int(text), month=1, day=1)
        return _next_year_start(parsed) if is_end else parsed

    if MONTH_ONLY_RE.fullmatch(text):
        parsed = pd.Timestamp(f"{text}-01")
        return _next_month_start(parsed) if is_end else parsed

    if DATE_ONLY_RE.fullmatch(text):
        parsed = pd.Timestamp(text)
        return parsed + pd.Timedelta(days=1) if is_end else parsed

    try:
        parsed = pd.Timestamp(text)
    except Exception as exc:
        raise ValueError(
            f"Invalid {bound_name} date bound: {raw_value!r}. "
            "Use null, YYYY, YYYY-MM, YYYY-MM-DD, or a full timestamp."
        ) from exc

    if pd.isna(parsed):
        raise ValueError(
            f"Invalid {bound_name} date bound: {raw_value!r}. "
            "Use null, YYYY, YYYY-MM, YYYY-MM-DD, or a full timestamp."
        )
    return parsed


def parse_date_range(raw_value: object) -> Optional[Tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]]:
    if raw_value is None:
        return None

    if isinstance(raw_value, dict):
        start_raw = raw_value.get("start")
        end_raw = raw_value.get("end")
    elif isinstance(raw_value, (list, tuple)) and len(raw_value) == 2:
        start_raw, end_raw = raw_value
    else:
        raise ValueError(
            "date_range must be null, a two-item array [start, end], or an object "
            "with {\"start\": ..., \"end\": ...}."
        )

    start = _parse_date_bound(start_raw, bound_name="start", is_end=False)
    end = _parse_date_bound(end_raw, bound_name="end", is_end=True)
    if start is None and end is None:
        return None
    if start is not None and end is not None and start >= end:
        raise ValueError("date_range start must be earlier than end.")
    return start, end


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
            f"[trigger_rate_metadata_plotter] Stage 0 basename source missing for {station}.",
            file=sys.stderr,
        )
        return set()

    try:
        df = pd.read_csv(stage0_csv)
    except Exception as exc:
        print(
            f"[trigger_rate_metadata_plotter] Failed to read {stage0_csv}: {exc}",
            file=sys.stderr,
        )
        return set()

    basename_col = None
    for candidate in ("basename", "filename_base", "hld_name", "dat_name"):
        if candidate in df.columns:
            basename_col = candidate
            break

    if basename_col is None:
        print(
            f"[trigger_rate_metadata_plotter] Missing basename column in {stage0_csv}.",
            file=sys.stderr,
        )
        return set()

    return {
        normalize_basename(value)
        for value in df[basename_col].astype(str)
        if normalize_basename(value)
    }


def read_header_columns(path: Path) -> List[str]:
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def build_usecols(path: Path, task_id: int, trigger_values: Sequence[str]) -> List[str]:
    header_cols = read_header_columns(path)
    if not header_cols:
        return []
    prefix = TASK_FINAL_PREFIX[task_id]
    desired = {
        "filename_base",
        "execution_timestamp",
        *(f"{prefix}_{trigger_value}_rate_hz" for trigger_value in trigger_values),
    }
    return [column for column in header_cols if column in desired]


def load_task_metadata(
    station: str,
    task_id: int,
    allowed_basenames: Set[str],
    trigger_values: Sequence[str],
    date_range: Optional[Tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]] = None,
) -> pd.DataFrame:
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

    usecols = build_usecols(metadata_csv, task_id, trigger_values)
    if not usecols:
        return pd.DataFrame()

    try:
        df = pd.read_csv(metadata_csv, usecols=usecols, low_memory=False)
    except Exception as exc:
        print(
            f"[trigger_rate_metadata_plotter] Failed to read {metadata_csv}: {exc}",
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
        df = df.iloc[0:0]

    if df.empty:
        return pd.DataFrame()

    if "execution_timestamp" in df.columns:
        text = df["execution_timestamp"].astype(str).str.strip()
        parsed = pd.to_datetime(text, format=METADATA_TIMESTAMP_FMT, errors="coerce")
        missing = parsed.isna()
        if missing.any():
            parsed.loc[missing] = pd.to_datetime(text[missing], errors="coerce")
        df["execution_timestamp_parsed"] = parsed
    else:
        df["execution_timestamp_parsed"] = pd.NaT

    df["file_timestamp"] = pd.to_datetime(
        df["basename"].map(extract_timestamp_from_basename),
        errors="coerce",
    )
    df = df[df["file_timestamp"].notna()].copy()
    if df.empty:
        return pd.DataFrame()

    if date_range is not None:
        start, end = date_range
        if start is not None:
            df = df[df["file_timestamp"] >= start]
        if end is not None:
            df = df[df["file_timestamp"] < end]
        if df.empty:
            return pd.DataFrame()

    prefix = TASK_FINAL_PREFIX[task_id]
    for trigger_value in trigger_values:
        column = f"{prefix}_{trigger_value}_rate_hz"
        if column not in df.columns:
            df[column] = np.nan
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.sort_values(
        by=["basename", "execution_timestamp_parsed", "file_timestamp"],
        na_position="last",
    )
    df = df.drop_duplicates(subset=["basename"], keep="last")
    return df.sort_values("file_timestamp").reset_index(drop=True)


def station_time_bounds(task_data: Dict[int, pd.DataFrame]) -> Optional[Tuple[pd.Timestamp, pd.Timestamp]]:
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
    lower = pd.Timestamp(combined.min())
    upper = pd.Timestamp(combined.max())
    if lower == upper:
        upper = lower + timedelta(minutes=1)
    return lower, upper


def _series_y_max(values: Sequence[float], y_min_hz: float) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return max(1.0, y_min_hz + 1.0)
    vmax = float(np.nanmax(finite))
    if vmax <= y_min_hz:
        return y_min_hz + 1.0
    return vmax * 1.12


def plot_station_page(
    station: str,
    task_data: Dict[int, pd.DataFrame],
    tasks: Sequence[int],
    trigger_values: Sequence[str],
    pdf: PdfPages,
    line_width: float,
    marker_size: float,
    y_min_hz: float,
    allowed_count: int,
) -> None:
    n_rows = len(trigger_values)
    fig_height = max(12.0, 1.8 * n_rows)
    fig, axes = plt.subplots(
        n_rows,
        1,
        figsize=(16, fig_height),
        sharex=True,
        constrained_layout=True,
    )

    if n_rows == 1:
        axes = [axes]  # type: ignore[list-item]

    cmap = plt.get_cmap("tab10")
    legend_handles: List[Line2D] = []
    x_limits = station_time_bounds(task_data)

    fig.suptitle(
        f"{station} - Main trigger rates by task (clean_remote/imported basenames: {allowed_count})",
        fontsize=13,
    )

    for idx, task_id in enumerate(tasks):
        color = cmap(idx % cmap.N)
        legend_handles.append(
            Line2D([0], [0], color=color, marker="o", markersize=4, linewidth=line_width, label=f"Task {task_id}")
        )

    for row_idx, trigger_value in enumerate(trigger_values):
        ax = axes[row_idx]
        plotted = False
        row_values: List[float] = []

        for idx, task_id in enumerate(tasks):
            df = task_data.get(task_id, pd.DataFrame())
            if df.empty:
                continue
            column = f"{TASK_FINAL_PREFIX[task_id]}_{trigger_value}_rate_hz"
            if column not in df.columns:
                continue

            task_df = df[["file_timestamp", column]].copy()
            task_df[column] = pd.to_numeric(task_df[column], errors="coerce")
            task_df = task_df.dropna(subset=["file_timestamp", column])
            if task_df.empty:
                continue

            task_df = task_df.sort_values("file_timestamp")
            color = cmap(idx % cmap.N)
            ax.plot(
                task_df["file_timestamp"],
                task_df[column],
                color=color,
                linewidth=line_width,
                alpha=0.95,
            )
            ax.scatter(
                task_df["file_timestamp"],
                task_df[column],
                color=color,
                s=marker_size,
                alpha=0.85,
                linewidths=0,
            )
            row_values.extend(task_df[column].to_list())
            plotted = True

        ax.set_ylabel(f"{trigger_value}\nHz", rotation=0, labelpad=18, va="center")
        ax.grid(True, axis="y", alpha=0.25, linestyle="--", linewidth=0.5)
        ax.set_ylim(y_min_hz, _series_y_max(row_values, y_min_hz))

        if x_limits is not None:
            ax.set_xlim(x_limits[0], x_limits[1])

        if not plotted:
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

    axes[-1].set_xlabel("Basename timestamp")
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d\n%H:%M"))
    fig.legend(
        handles=legend_handles,
        loc="upper right",
        ncols=min(len(tasks), 5),
        fontsize=8,
        frameon=True,
    )

    pdf_save_rasterized_page(pdf, fig, dpi=150)
    plt.close(fig)


def plot_station_pair_scatter_page(
    station: str,
    task_data: Dict[int, pd.DataFrame],
    tasks: Sequence[int],
    trigger_values: Sequence[str],
    pdf: PdfPages,
    marker_size: float,
    allowed_count: int,
) -> None:
    n_values = len(trigger_values)
    if n_values == 0:
        return

    fig_size = max(14.0, 1.55 * n_values)
    fig, axes = plt.subplots(
        n_values,
        n_values,
        figsize=(fig_size, fig_size),
        constrained_layout=True,
    )
    if n_values == 1:
        axes = np.array([[axes]])

    cmap = plt.get_cmap("tab10")
    legend_handles: List[Line2D] = []
    for idx, task_id in enumerate(tasks):
        color = cmap(idx % cmap.N)
        legend_handles.append(
            Line2D(
                [0],
                [0],
                color=color,
                marker="o",
                linestyle="",
                markersize=max(3.5, np.sqrt(max(marker_size, 1.0))),
                label=f"Task {task_id}",
            )
        )

    fig.suptitle(
        f"{station} - Trigger-rate pair scatters by task (clean_remote/imported basenames: {allowed_count})",
        fontsize=13,
    )

    prefix_by_task = {task_id: TASK_FINAL_PREFIX[task_id] for task_id in tasks}

    for row_idx, y_trigger in enumerate(trigger_values):
        for col_idx, x_trigger in enumerate(trigger_values):
            ax = axes[row_idx, col_idx]

            if col_idx > row_idx:
                ax.set_axis_off()
                continue

            if row_idx == col_idx:
                ax.set_axis_off()
                ax.text(
                    0.5,
                    0.5,
                    y_trigger,
                    transform=ax.transAxes,
                    ha="center",
                    va="center",
                    fontsize=9,
                    fontweight="bold",
                    color="dimgray",
                )
                continue

            panel_has_points = False
            x_values_all: List[float] = []
            y_values_all: List[float] = []

            for idx, task_id in enumerate(tasks):
                df = task_data.get(task_id, pd.DataFrame())
                if df.empty:
                    continue

                prefix = prefix_by_task[task_id]
                x_col = f"{prefix}_{x_trigger}_rate_hz"
                y_col = f"{prefix}_{y_trigger}_rate_hz"
                if x_col not in df.columns or y_col not in df.columns:
                    continue

                panel_df = df[[x_col, y_col]].copy()
                panel_df[x_col] = pd.to_numeric(panel_df[x_col], errors="coerce")
                panel_df[y_col] = pd.to_numeric(panel_df[y_col], errors="coerce")
                panel_df = panel_df.dropna(subset=[x_col, y_col])
                if panel_df.empty:
                    continue

                color = cmap(idx % cmap.N)
                ax.scatter(
                    panel_df[x_col],
                    panel_df[y_col],
                    color=color,
                    s=max(marker_size, 4.0),
                    alpha=0.65,
                    linewidths=0,
                )
                x_values = panel_df[x_col].to_numpy(dtype=float)
                y_values = panel_df[y_col].to_numpy(dtype=float)
                x_values_all.extend(x_values.tolist())
                y_values_all.extend(y_values.tolist())
                panel_has_points = True

            if panel_has_points:
                finite_x = np.asarray(x_values_all, dtype=float)
                finite_y = np.asarray(y_values_all, dtype=float)
                finite_x = finite_x[np.isfinite(finite_x)]
                finite_y = finite_y[np.isfinite(finite_y)]
                if finite_x.size > 0 and finite_y.size > 0:
                    x_max = max(0.1, float(np.nanmax(finite_x)) * 1.06)
                    y_max = max(0.1, float(np.nanmax(finite_y)) * 1.06)
                    ax.set_xlim(0.0, x_max)
                    ax.set_ylim(0.0, y_max)
            else:
                ax.text(
                    0.5,
                    0.5,
                    "No points",
                    transform=ax.transAxes,
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="dimgray",
                )

            if row_idx == n_values - 1:
                ax.set_xlabel(x_trigger, fontsize=8)
            else:
                ax.set_xticklabels([])

            if col_idx == 0:
                ax.set_ylabel(y_trigger, fontsize=8)
            else:
                ax.set_yticklabels([])

            ax.grid(True, alpha=0.18, linestyle="--", linewidth=0.4)
            ax.tick_params(labelsize=7)

    fig.legend(
        handles=legend_handles,
        loc="upper right",
        ncols=min(len(tasks), 5),
        fontsize=8,
        frameon=True,
    )

    pdf_save_rasterized_page(pdf, fig, dpi=150)
    plt.close(fig)


def default_output_path() -> Path:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    return PLOTS_DIR / DEFAULT_OUTPUT_FILENAME


def load_config(config_path: Path) -> Dict[str, object]:
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a PDF with main trigger rates by task and plane combination."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to JSON config file.",
    )
    parser.add_argument(
        "--stations",
        nargs="+",
        help="Station tokens like 0 1 or MINGO00 MINGO01.",
    )
    parser.add_argument(
        "--tasks",
        nargs="+",
        help="Optional subset of tasks to plot.",
    )
    parser.add_argument(
        "--output",
        help="Optional output PDF path.",
    )
    return parser.parse_args()


def main() -> None:
    configure_matplotlib_style()
    args = parse_args()
    config_path = Path(args.config).expanduser()
    config = load_config(config_path)

    if args.stations is not None:
        stations = resolve_station_selection(args.stations)
    else:
        stations = normalize_existing_station_tokens(config.get("stations", []))
        if not stations:
            stations = list_available_stations()

    if args.tasks is not None:
        tasks = normalize_task_selection(args.tasks)
    else:
        tasks = normalize_task_selection(config.get("tasks", list(TASK_IDS)))

    trigger_values = normalize_trigger_values(config.get("trigger_values", list(DEFAULT_TRIGGER_VALUES)))
    date_range = parse_date_range(config.get("date_range"))
    line_width = float(config.get("line_width", DEFAULT_LINE_WIDTH))
    marker_size = float(config.get("marker_size", DEFAULT_MARKER_SIZE))
    y_min_hz = float(config.get("y_min_hz", DEFAULT_Y_MIN_HZ))
    output_path = resolve_output_path(args.output or config.get("output"), config_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not stations:
        raise SystemExit("No valid stations selected.")

    station_payload: Dict[str, Tuple[Dict[int, pd.DataFrame], int]] = {}
    for station in stations:
        allowed_basenames = load_allowed_basenames(station)
        task_payload: Dict[int, pd.DataFrame] = {}
        for task_id in tasks:
            task_payload[task_id] = load_task_metadata(
                station=station,
                task_id=task_id,
                allowed_basenames=allowed_basenames,
                trigger_values=trigger_values,
                date_range=date_range,
            )
        station_payload[station] = (task_payload, len(allowed_basenames))

    with PdfPages(output_path) as pdf:
        for station in stations:
            task_payload, allowed_count = station_payload[station]
            plot_station_page(
                station=station,
                task_data=task_payload,
                tasks=tasks,
                trigger_values=trigger_values,
                pdf=pdf,
                line_width=line_width,
                marker_size=marker_size,
                y_min_hz=y_min_hz,
                allowed_count=allowed_count,
            )
            plot_station_pair_scatter_page(
                station=station,
                task_data=task_payload,
                tasks=tasks,
                trigger_values=trigger_values,
                pdf=pdf,
                marker_size=marker_size,
                allowed_count=allowed_count,
            )

    print(f"[trigger_rate_metadata_plotter] Wrote {output_path}")


if __name__ == "__main__":
    main()
