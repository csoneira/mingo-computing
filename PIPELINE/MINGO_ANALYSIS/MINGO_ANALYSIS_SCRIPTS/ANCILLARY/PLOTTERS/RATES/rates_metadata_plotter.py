#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/RATES/rates_metadata_plotter.py
Purpose: Plot task rate histograms and global rate trends gated by Stage 0 basenames.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/RATES/rates_metadata_plotter.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
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
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages


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
DEFAULT_CONFIG_PATH = PLOTTER_DIR / "rates_metadata_config.json"
DEFAULT_OUTPUT_FILENAME = "rates_metadata_report.pdf"

TASK_IDS: Tuple[int, ...] = (1, 2, 3, 4, 5)
RATE_COLUMN_PREFIX = "events_per_second_"
RATE_COUNT_COLUMN_SUFFIX = "_count"
RATE_RATE_HZ_COLUMN_SUFFIX = "_rate_hz"

DEFAULT_MAX_RATE_BIN = 100
DEFAULT_Y_MAX_HZ = 100.0
DEFAULT_GLOBAL_RATE_Y_MIN_HZ = 0.0
DEFAULT_GLOBAL_RATE_Y_MAX_HZ = 100.0
DEFAULT_GLOBAL_RATE_TIGHT_Y_MIN_HZ = 0.0
DEFAULT_GLOBAL_RATE_TIGHT_Y_MAX_HZ = 20.0
DEFAULT_TAIL_ROWS = 0
DEFAULT_MAX_BIN_GAP_HOURS = 3.0
METADATA_STATUS_SUFFIX = metadata_output_status_suffix("rate_histogram")

BASENAME_TIMESTAMP_DIGITS = 11
FILENAME_TIMESTAMP_PATTERN = re.compile(r"mi0\d(\d{11})$", re.IGNORECASE)


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
            "[rates_metadata_plotter] Ignoring unknown station(s): " + ", ".join(invalid),
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


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for value in values:
        candidate = value.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
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
            f"[rates_metadata_plotter] Stage 0 basename source missing for {station}.",
            file=sys.stderr,
        )
        return set()

    try:
        df = pd.read_csv(stage0_csv)
    except Exception as exc:  # pragma: no cover - defensive
        print(
            f"[rates_metadata_plotter] Failed to read {stage0_csv}: {exc}",
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
            f"[rates_metadata_plotter] Missing basename column in {stage0_csv}.",
            file=sys.stderr,
        )
        return set()

    return {
        normalize_basename(value)
        for value in df[basename_col].astype(str)
        if normalize_basename(value)
    }


def rate_count_columns(max_rate_bin: int) -> List[str]:
    return [
        f"{RATE_COLUMN_PREFIX}{idx}{RATE_COUNT_COLUMN_SUFFIX}"
        for idx in range(max_rate_bin + 1)
    ]


def rate_hz_columns(max_rate_bin: int) -> List[str]:
    return [
        f"{RATE_COLUMN_PREFIX}{idx}{RATE_RATE_HZ_COLUMN_SUFFIX}"
        for idx in range(max_rate_bin + 1)
    ]


def read_header_columns(path: Path) -> List[str]:
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def resolve_usecols(path: Path, max_rate_bin: int) -> Optional[List[str]]:
    header_cols = read_header_columns(path)
    if not header_cols:
        return None

    required = set(rate_count_columns(max_rate_bin))
    required.update(rate_hz_columns(max_rate_bin))
    required.update(
        {
            "filename_base",
            "execution_timestamp",
            "count_rate_denominator_seconds",
            "events_per_second_total_seconds",
            "events_per_second_global_rate",
        }
    )
    return [col for col in header_cols if col in required]


def load_task_metadata(
    station: str,
    task_id: int,
    allowed_basenames: Set[str],
    max_rate_bin: int,
    tail_rows: int,
) -> pd.DataFrame:
    metadata_csv = (
        STATIONS_ROOT
        / station
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / f"TASK_{task_id}"
        / "METADATA"
        / f"task_{task_id}_metadata_rate_histogram.csv"
    )
    if not metadata_csv.exists():
        return pd.DataFrame()

    try:
        usecols = resolve_usecols(metadata_csv, max_rate_bin)
        df = pd.read_csv(metadata_csv, usecols=usecols, low_memory=False)
    except Exception as exc:  # pragma: no cover - defensive
        print(
            f"[rates_metadata_plotter] Failed to read {metadata_csv}: {exc}",
            file=sys.stderr,
        )
        return pd.DataFrame()

    if df.empty or "filename_base" not in df.columns:
        return pd.DataFrame()

    if tail_rows > 0:
        df = df.tail(tail_rows).copy()
    else:
        df = df.copy()

    df["basename"] = df["filename_base"].map(normalize_basename)
    df = df[df["basename"].str.startswith("mi", na=False)]

    if allowed_basenames:
        df = df[df["basename"].isin(allowed_basenames)]
    else:
        df = df.iloc[0:0]

    if df.empty:
        return pd.DataFrame()

    df["file_timestamp"] = pd.to_datetime(
        df["basename"].map(extract_timestamp_from_basename),
        errors="coerce",
    )

    total_seconds_source = df.get("events_per_second_total_seconds")
    if total_seconds_source is None:
        total_seconds_source = df.get("count_rate_denominator_seconds")
    if total_seconds_source is None:
        total_seconds_source = pd.Series([np.nan] * len(df), index=df.index)

    df["events_per_second_total_seconds"] = pd.to_numeric(
        total_seconds_source,
        errors="coerce",
    ).fillna(0.0)

    df["events_per_second_global_rate"] = pd.to_numeric(
        df.get("events_per_second_global_rate", pd.Series([np.nan] * len(df))),
        errors="coerce",
    )

    expected_rate_hz_cols = rate_hz_columns(max_rate_bin)
    expected_count_cols = rate_count_columns(max_rate_bin)
    source_columns = set(df.columns)
    has_histogram_bins = any(col in source_columns for col in expected_rate_hz_cols) or any(
        col in source_columns for col in expected_count_cols
    )
    df["_has_histogram_bins"] = bool(has_histogram_bins)

    denom = df["events_per_second_total_seconds"].replace(0, np.nan)
    rate_payload: Dict[str, pd.Series] = {}
    for rate_hz_col, count_col in zip(expected_rate_hz_cols, expected_count_cols):
        if rate_hz_col in df.columns:
            rate_values = pd.to_numeric(df[rate_hz_col], errors="coerce").fillna(0.0)
        elif count_col in df.columns:
            count_values = pd.to_numeric(df[count_col], errors="coerce").fillna(0.0)
            rate_values = (count_values / denom).fillna(0.0)
        else:
            rate_values = pd.Series(0.0, index=df.index)
        rate_payload[rate_hz_col] = rate_values

    rate_matrix = pd.DataFrame(rate_payload, index=df.index)
    df = df.drop(columns=expected_rate_hz_cols, errors="ignore")
    df = pd.concat([df, rate_matrix], axis=1)

    missing_global = df["events_per_second_global_rate"].isna()
    if missing_global.any():
        rates = df.loc[missing_global, expected_rate_hz_cols]
        df.loc[missing_global, "events_per_second_global_rate"] = (
            rates * np.arange(max_rate_bin + 1)
        ).sum(axis=1)

    df = df[df["file_timestamp"].notna()].copy()
    if df.empty:
        return pd.DataFrame()

    df = df.drop_duplicates(subset=["basename"], keep="last")
    df["task"] = task_id
    return df.sort_values("file_timestamp").reset_index(drop=True)


def compute_time_edges(times_num: np.ndarray, fallback_seconds: float = 60.0) -> np.ndarray:
    if times_num.size == 1:
        half = max(fallback_seconds / 86400.0 / 2.0, 1.0 / 1440.0)
        return np.array([times_num[0] - half, times_num[0] + half])

    diffs = np.diff(times_num)
    positive = diffs[diffs > 0]
    if positive.size == 0:
        delta = max(fallback_seconds / 86400.0, 1.0 / 1440.0)
    else:
        delta = float(np.median(positive))

    edges = np.empty(times_num.size + 1, dtype=float)
    edges[1:-1] = (times_num[:-1] + times_num[1:]) / 2.0
    edges[0] = times_num[0] - delta / 2.0
    edges[-1] = times_num[-1] + delta / 2.0
    return edges


def build_intervalized_rate_matrix(
    times_num: np.ndarray,
    freq_matrix: np.ndarray,
    max_bin_gap_hours: float,
    fallback_seconds: float,
) -> Tuple[np.ndarray, np.ndarray]:
    if times_num.size == 0:
        return np.array([], dtype=float), np.empty((freq_matrix.shape[0], 0), dtype=float)

    fallback_days = max(float(fallback_seconds), 1.0) / 86400.0
    diffs = np.diff(times_num)
    positive_diffs = diffs[diffs > 0]
    if positive_diffs.size > 0:
        tail_days = float(np.median(positive_diffs))
    else:
        tail_days = fallback_days

    if np.isfinite(max_bin_gap_hours):
        max_gap_days = max(float(max_bin_gap_hours), 1.0 / 3600.0) / 24.0
        tail_days = min(tail_days, max_gap_days)
    else:
        max_gap_days = np.inf

    intervals: List[Tuple[float, float, Optional[int]]] = []
    for idx, start in enumerate(times_num):
        start_v = float(start)
        if idx < times_num.size - 1:
            next_v = float(times_num[idx + 1])
            if np.isfinite(max_gap_days):
                end_v = min(next_v, start_v + max_gap_days)
            else:
                end_v = next_v
        else:
            end_v = start_v + max(tail_days, fallback_days / 2.0)

        if end_v <= start_v:
            end_v = start_v + fallback_days / 2.0

        intervals.append((start_v, end_v, idx))

        if idx < times_num.size - 1:
            next_v = float(times_num[idx + 1])
            if end_v < next_v:
                intervals.append((end_v, next_v, None))

    x_edges = np.empty(len(intervals) + 1, dtype=float)
    plot_matrix = np.empty((freq_matrix.shape[0], len(intervals)), dtype=float)
    x_edges[0] = intervals[0][0]

    for col_idx, (_start_v, end_v, src_col) in enumerate(intervals):
        x_edges[col_idx + 1] = end_v
        if src_col is None:
            plot_matrix[:, col_idx] = np.nan
        else:
            plot_matrix[:, col_idx] = freq_matrix[:, src_col]

    return x_edges, plot_matrix


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


def plot_task_histogram_axis(
    ax: plt.Axes,
    df: pd.DataFrame,
    max_rate_bin: int,
    y_max_hz: float,
    max_bin_gap_hours: float,
    title: str,
    x_limits: Optional[Tuple[pd.Timestamp, pd.Timestamp]],
) -> None:
    ax.set_title(title, fontsize=10)
    ax.set_ylabel("Hz")
    ax.set_ylim(0.0, y_max_hz)
    cmap = plt.get_cmap("viridis")
    # Keep empty/masked regions visually consistent with the histogram's lowest color.
    ax.set_facecolor(cmap(0.0))

    if x_limits is not None:
        ax.set_xlim(x_limits[0], x_limits[1])

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

    if "_has_histogram_bins" in df.columns:
        bins_available = bool(
            pd.to_numeric(df["_has_histogram_bins"], errors="coerce")
            .fillna(0)
            .astype(bool)
            .any()
        )
        if not bins_available:
            ax.text(
                0.5,
                0.5,
                "Missing histogram bins in metadata\n(events_per_second_*_rate_hz / *_count)",
                transform=ax.transAxes,
                ha="center",
                va="center",
                fontsize=9,
                color="firebrick",
            )
            return

    rate_cols = rate_hz_columns(max_rate_bin)
    freq_matrix = (
        df[rate_cols]
        .fillna(0)
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0)
        .to_numpy(dtype=float)
        .T
    )

    total_seconds = pd.to_numeric(
        df["events_per_second_total_seconds"],
        errors="coerce",
    ).fillna(0.0).to_numpy(dtype=float)

    time_nums = mdates.date2num(pd.to_datetime(df["file_timestamp"]).to_numpy())
    sort_idx = np.argsort(time_nums)
    time_nums = time_nums[sort_idx]
    freq_matrix = freq_matrix[:, sort_idx]

    fallback_seconds = float(np.nanmedian(total_seconds)) if total_seconds.size else 60.0
    if not np.isfinite(fallback_seconds) or fallback_seconds <= 0:
        fallback_seconds = 60.0
    x_edges, plot_matrix = build_intervalized_rate_matrix(
        times_num=time_nums,
        freq_matrix=freq_matrix,
        max_bin_gap_hours=max_bin_gap_hours,
        fallback_seconds=fallback_seconds,
    )
    masked = np.ma.masked_where(~np.isfinite(plot_matrix) | (plot_matrix <= 0), plot_matrix)
    y_edges = np.arange(-0.5, max_rate_bin + 1.5, 1.0)

    ax.pcolormesh(
        x_edges,
        y_edges,
        masked,
        cmap=cmap,
        shading="auto",
    )

    ax.grid(False)


def plot_global_rate_axis(
    ax: plt.Axes,
    task_data: Dict[int, pd.DataFrame],
    tasks: Sequence[int],
    global_rate_y_min_hz: float,
    global_rate_y_max_hz: float,
    x_limits: Optional[Tuple[pd.Timestamp, pd.Timestamp]],
    title: str,
) -> None:
    ax.set_title(title, fontsize=10)
    ax.set_ylabel("Hz")
    ax.set_ylim(global_rate_y_min_hz, global_rate_y_max_hz)
    ax.grid(True, axis="y", alpha=0.3, linestyle="--", linewidth=0.5)

    if x_limits is not None:
        ax.set_xlim(x_limits[0], x_limits[1])

    cmap = plt.get_cmap("tab10")
    plotted = False

    for idx, task_id in enumerate(tasks):
        df = task_data.get(task_id, pd.DataFrame())
        if df.empty:
            continue

        task_df = df[["file_timestamp", "events_per_second_global_rate"]].copy()
        task_df["events_per_second_global_rate"] = pd.to_numeric(
            task_df["events_per_second_global_rate"], errors="coerce"
        )
        task_df = task_df.dropna(subset=["file_timestamp", "events_per_second_global_rate"])
        if task_df.empty:
            continue

        task_df = task_df.sort_values("file_timestamp")
        color = cmap(idx % cmap.N)

        ax.plot(
            task_df["file_timestamp"],
            task_df["events_per_second_global_rate"],
            linewidth=1.2,
            color=color,
            label=f"Task {task_id}",
        )
        ax.scatter(
            task_df["file_timestamp"],
            task_df["events_per_second_global_rate"],
            s=10,
            color=color,
            alpha=0.8,
        )
        plotted = True

    if plotted:
        ax.legend(loc="upper left", ncols=min(len(tasks), 3), fontsize=8)
    else:
        ax.text(
            0.5,
            0.5,
            "No global-rate data",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=9,
            color="dimgray",
        )


def plot_station_page(
    station: str,
    task_data: Dict[int, pd.DataFrame],
    tasks: Sequence[int],
    pdf: PdfPages,
    y_max_hz: float,
    global_rate_y_min_hz: float,
    global_rate_y_max_hz: float,
    global_rate_tight_y_min_hz: float,
    global_rate_tight_y_max_hz: float,
    max_rate_bin: int,
    max_bin_gap_hours: float,
    allowed_count: int,
) -> None:
    n_rows = len(tasks) + 2
    fig_height = max(11.0, 1.95 * n_rows)

    fig, axes = plt.subplots(
        n_rows,
        1,
        figsize=(16, fig_height),
        sharex=True,
        constrained_layout=True,
    )

    if n_rows == 1:
        axes = [axes]  # type: ignore[list-item]

    fig.suptitle(
        f"{station} - Rates metadata (clean_remote/imported basenames: {allowed_count}){METADATA_STATUS_SUFFIX}",
        fontsize=13,
    )

    x_limits = station_time_bounds(task_data)
    station_max_gap = np.inf if station == "MINGO00" else max_bin_gap_hours

    for row_idx, task_id in enumerate(tasks):
        ax = axes[row_idx]
        plot_task_histogram_axis(
            ax=ax,
            df=task_data.get(task_id, pd.DataFrame()),
            max_rate_bin=max_rate_bin,
            y_max_hz=y_max_hz,
            max_bin_gap_hours=station_max_gap,
            title=f"Task {task_id} - Events/s histogram over file time",
            x_limits=x_limits,
        )

    global_ax = axes[-2]
    plot_global_rate_axis(
        ax=global_ax,
        task_data=task_data,
        tasks=tasks,
        global_rate_y_min_hz=global_rate_y_min_hz,
        global_rate_y_max_hz=global_rate_y_max_hz,
        x_limits=x_limits,
        title="Global rate by task",
    )

    global_tight_ax = axes[-1]
    plot_global_rate_axis(
        ax=global_tight_ax,
        task_data=task_data,
        tasks=tasks,
        global_rate_y_min_hz=global_rate_tight_y_min_hz,
        global_rate_y_max_hz=global_rate_tight_y_max_hz,
        x_limits=x_limits,
        title="Global rate by task (tight view)",
    )

    global_tight_ax.set_xlabel("Basename timestamp")
    global_tight_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d\n%H:%M"))

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
) -> Tuple[List[str], List[int], float, float, float, float, float, int, int, float, Path]:
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

    if args.y_max_hz is not None:
        y_max_hz = float(args.y_max_hz)
    else:
        try:
            y_max_hz = float(config.get("y_max_hz", DEFAULT_Y_MAX_HZ))
        except (TypeError, ValueError):
            raise ValueError("'y_max_hz' in config must be numeric")
    if y_max_hz <= 0:
        raise ValueError("'y_max_hz' must be > 0")

    try:
        global_rate_y_min_hz = float(
            config.get("global_rate_y_min_hz", DEFAULT_GLOBAL_RATE_Y_MIN_HZ)
        )
    except (TypeError, ValueError):
        raise ValueError("'global_rate_y_min_hz' in config must be numeric")

    try:
        global_rate_y_max_hz = float(
            config.get("global_rate_y_max_hz", DEFAULT_GLOBAL_RATE_Y_MAX_HZ)
        )
    except (TypeError, ValueError):
        raise ValueError("'global_rate_y_max_hz' in config must be numeric")

    if global_rate_y_max_hz <= global_rate_y_min_hz:
        raise ValueError("'global_rate_y_max_hz' must be > 'global_rate_y_min_hz'")

    try:
        global_rate_tight_y_min_hz = float(
            config.get("global_rate_tight_y_min_hz", DEFAULT_GLOBAL_RATE_TIGHT_Y_MIN_HZ)
        )
    except (TypeError, ValueError):
        raise ValueError("'global_rate_tight_y_min_hz' in config must be numeric")

    try:
        global_rate_tight_y_max_hz = float(
            config.get("global_rate_tight_y_max_hz", DEFAULT_GLOBAL_RATE_TIGHT_Y_MAX_HZ)
        )
    except (TypeError, ValueError):
        raise ValueError("'global_rate_tight_y_max_hz' in config must be numeric")

    if global_rate_tight_y_max_hz <= global_rate_tight_y_min_hz:
        raise ValueError("'global_rate_tight_y_max_hz' must be > 'global_rate_tight_y_min_hz'")

    if args.max_rate_bin is not None:
        max_rate_bin = int(args.max_rate_bin)
    else:
        try:
            max_rate_bin = int(config.get("max_rate_bin", DEFAULT_MAX_RATE_BIN))
        except (TypeError, ValueError):
            raise ValueError("'max_rate_bin' in config must be integer")
    if max_rate_bin <= 0:
        raise ValueError("'max_rate_bin' must be > 0")

    try:
        tail_rows = int(config.get("tail_rows", DEFAULT_TAIL_ROWS))
    except (TypeError, ValueError):
        raise ValueError("'tail_rows' in config must be integer")
    if tail_rows < 0:
        raise ValueError("'tail_rows' in config must be >= 0")

    if args.max_bin_gap_hours is not None:
        max_bin_gap_hours = float(args.max_bin_gap_hours)
    else:
        try:
            max_bin_gap_hours = float(
                config.get("max_bin_gap_hours", DEFAULT_MAX_BIN_GAP_HOURS)
            )
        except (TypeError, ValueError):
            raise ValueError("'max_bin_gap_hours' in config must be numeric")
    if max_bin_gap_hours <= 0:
        raise ValueError("'max_bin_gap_hours' must be > 0")

    output_raw = args.output
    if output_raw is None:
        config_output = config.get("output")
        output_raw = str(config_output) if config_output is not None else None
    output_path = resolve_output_path(output_raw, config_path)

    return (
        stations,
        tasks,
        y_max_hz,
        global_rate_y_min_hz,
        global_rate_y_max_hz,
        global_rate_tight_y_min_hz,
        global_rate_tight_y_max_hz,
        max_rate_bin,
        tail_rows,
        max_bin_gap_hours,
        output_path,
    )


def ensure_output_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate rates metadata report with clean_remote/imported basename gating."
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
        "--y-max-hz",
        type=float,
        default=None,
        help="Y-axis max (Hz) for task histograms.",
    )
    parser.add_argument(
        "--max-rate-bin",
        type=int,
        default=None,
        help="Max events-per-second bin to read/plot.",
    )
    parser.add_argument(
        "--max-bin-gap-hours",
        type=float,
        default=None,
        help="Max histogram bin extent to the next file (hours). Ignored for MINGO00.",
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
        y_max_hz,
        global_rate_y_min_hz,
        global_rate_y_max_hz,
        global_rate_tight_y_min_hz,
        global_rate_tight_y_max_hz,
        max_rate_bin,
        tail_rows,
        max_bin_gap_hours,
        output_path,
    ) = resolve_runtime_options(args)

    if not stations:
        raise RuntimeError("No stations selected or discovered.")

    ensure_output_directory(output_path)

    with PdfPages(output_path) as pdf:
        for station in stations:
            allowed_basenames = load_allowed_basenames(station)
            task_data: Dict[int, pd.DataFrame] = {}
            for task_id in tasks:
                task_data[task_id] = load_task_metadata(
                    station=station,
                    task_id=task_id,
                    allowed_basenames=allowed_basenames,
                    max_rate_bin=max_rate_bin,
                    tail_rows=tail_rows,
                )

            plot_station_page(
                station=station,
                task_data=task_data,
                tasks=tasks,
                pdf=pdf,
                y_max_hz=y_max_hz,
                global_rate_y_min_hz=global_rate_y_min_hz,
                global_rate_y_max_hz=global_rate_y_max_hz,
                global_rate_tight_y_min_hz=global_rate_tight_y_min_hz,
                global_rate_tight_y_max_hz=global_rate_tight_y_max_hz,
                max_rate_bin=max_rate_bin,
                max_bin_gap_hours=max_bin_gap_hours,
                allowed_count=len(allowed_basenames),
            )

    print(f"Saved rates metadata report: {output_path}")


if __name__ == "__main__":
    main()
