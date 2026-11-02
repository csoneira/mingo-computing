#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/DEFINITIVE_EXECUTION/definitive_execution_plotter.py
Purpose: Generate definitive execution timeline maps for each station.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/DEFINITIVE_EXECUTION/definitive_execution_plotter.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import colormaps
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.cm import ScalarMappable
from matplotlib.colors import BoundaryNorm, ListedColormap, to_hex


SCRIPT_PATH = Path(__file__).resolve()


def detect_repo_root() -> Path:
    for parent in SCRIPT_PATH.parents:
        if (parent / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS").is_dir() and (parent / "CONFIG" / "config_paths.yaml").is_file():
            return parent
    raise RuntimeError(f"Could not locate repository root from {SCRIPT_PATH}")


REPO_ROOT = detect_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.plot_utils import pdf_save_rasterized_page  # noqa: E402


STATIONS_ROOT = REPO_ROOT / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
PLOTTER_DIR = SCRIPT_PATH.parent
PLOTS_DIR = PLOTTER_DIR / "PLOTS"
DEFAULT_OUTPUT_FILENAME = "definitive_execution_map_report.pdf"
DEFAULT_CONFIG_PATH = PLOTTER_DIR / "definitive_execution_config.json"
DEFAULT_LAST_HOURS = 2.0
DEFAULT_POINT_SIZE = 16.0
DEFAULT_MINGO00_STAGE0_SOURCE = "auto"
MINGO00_STAGE0_SOURCE_CHOICES: Tuple[str, ...] = ("live", "history", "auto")
DEFAULT_SHARED_X_STATIONS: Tuple[str, ...] = ("MINGO01", "MINGO02", "MINGO03", "MINGO04")
DEFAULT_FREE_X_STATIONS: Tuple[str, ...] = ("MINGO01",)
DEFAULT_PANEL_HEIGHT_RATIOS: Tuple[float, float, float] = (1.0, 4.0, 1.0)
DEFAULT_MIDDLE_LOG_SCALE_SECONDS = 600.0
NOW_Y_MARGIN_MINUTES = 10.0
ETA_SHORT_WINDOW = timedelta(minutes=10)
ETA_MEDIUM_WINDOW = timedelta(hours=2)

TASK_IDS: Tuple[int, ...] = (1, 2, 3, 4, 5)
BASENAME_TIMESTAMP_DIGITS = 11
FILENAME_TIMESTAMP_PATTERN = re.compile(r"mi0\d(\d{11})$", re.IGNORECASE)
CSV_ROW_BASENAME_PATTERN = re.compile(r"([^\n])(mi0\d{12},)", re.IGNORECASE)
STAGE0_COLOR = "#ffffff"
TASK_COLORMAP_NAME = "rainbow"
TASK_COLOR_SAMPLE_RANGE: Tuple[float, float] = (0.08, 0.82)


@dataclass(frozen=True)
class StageSpec:
    index: int
    label: str
    color: str
    csv_path: Path
    basename_columns: Tuple[str, ...]
    execution_columns: Tuple[str, ...]
    execution_format: Optional[str]
    use_basename_as_execution: bool = False
    use_csv_timestamp_as_execution: bool = False


def build_shared_task_color_map() -> Dict[int, str]:
    # Keep task colors identical across stations and plotters.
    sample_points = np.linspace(
        TASK_COLOR_SAMPLE_RANGE[0],
        TASK_COLOR_SAMPLE_RANGE[1],
        len(TASK_IDS),
    )
    cmap = colormaps[TASK_COLORMAP_NAME]
    return {
        task_id: to_hex(cmap(point))
        for task_id, point in zip(TASK_IDS, sample_points)
    }


TASK_COLORS = build_shared_task_color_map()


def configure_matplotlib_style() -> None:
    plt.style.use("default")


def now_timestamp_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _write_registry_rows_atomic(registry_path: Path, rows: List[Dict[str, str]]) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{registry_path.name}.",
        suffix=".tmp",
        dir=str(registry_path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=("basename", "execution_timestamp"))
            writer.writeheader()
            writer.writerows(rows)
        tmp_path.replace(registry_path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def _load_registry_map(registry_path: Path) -> Dict[str, str]:
    if not registry_path.exists():
        return {}

    rows: Dict[str, str] = {}
    with registry_path.open("r", encoding="ascii", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            basename = (row.get("basename") or "").strip()
            if not basename:
                continue
            execution_timestamp = (row.get("execution_timestamp") or "").strip()
            rows[basename] = execution_timestamp or now_timestamp_text()
    return rows


def _find_ground_truth_basenames(station_root: Path) -> set[str]:
    basenames: set[str] = set()

    stage01 = station_root / "STAGE_0_TO_1"
    for path in stage01.rglob("*"):
        if path.is_file():
            stem = path.stem
            if stem.startswith("mi00"):
                basenames.add(stem)

    step1 = station_root / "STAGE_1" / "EVENT_DATA" / "STEP_1"
    for task_dir in step1.glob("TASK_*"):
        input_root = task_dir / "INPUT_FILES"
        for subdir in input_root.glob("*"):
            if not subdir.is_dir():
                continue
            for path in subdir.glob("*"):
                if path.is_file():
                    stem = path.stem
                    if stem.startswith("mi00"):
                        basenames.add(stem)

    return basenames


def sync_live_registry_with_ground_truth(registry_path: Path, station_root: Path) -> Tuple[int, int]:
    truth = _find_ground_truth_basenames(station_root)
    existing = _load_registry_map(registry_path)

    truth_set = set(truth)
    existing_set = set(existing.keys())
    to_add = sorted(truth_set - existing_set)
    to_remove = sorted(existing_set - truth_set)

    if to_add or to_remove:
        timestamp_now = now_timestamp_text()
        new_rows: List[Dict[str, str]] = []
        for basename in sorted(truth_set):
            new_rows.append(
                {
                    "basename": basename,
                    "execution_timestamp": existing.get(basename, timestamp_now),
                }
            )
        _write_registry_rows_atomic(registry_path, new_rows)

    return len(to_add), len(to_remove)


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
        station = normalize_station_token(token)
        if station is None or station not in available:
            invalid.append(token)
            continue
        selected.append(station)

    if invalid:
        print(
            "[definitive_execution_plotter] Ignoring unknown station(s): "
            + ", ".join(invalid),
            file=sys.stderr,
        )

    return sorted(dict.fromkeys(selected))


def normalize_existing_station_tokens(tokens: Sequence[str]) -> List[str]:
    available = set(list_available_stations())
    selected: List[str] = []
    for token in tokens:
        station = normalize_station_token(str(token))
        if station is None or station not in available:
            continue
        selected.append(station)
    return sorted(dict.fromkeys(selected))


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


def first_existing_column(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def parse_execution_series(series: pd.Series, fmt: Optional[str]) -> pd.Series:
    text = series.astype(str).str.strip()
    if fmt:
        parsed = pd.to_datetime(text, format=fmt, errors="coerce")
        missing = parsed.isna()
        if missing.any():
            parsed.loc[missing] = pd.to_datetime(text[missing], errors="coerce")
        return parsed

    parsed = pd.to_datetime(text, format="%Y-%m-%d_%H.%M.%S", errors="coerce")
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(text[missing], errors="coerce")
    return parsed


def csv_creation_like_timestamp(path: Path) -> Optional[pd.Timestamp]:
    try:
        stat = path.stat()
    except OSError:
        return None

    created = getattr(stat, "st_birthtime", None)
    if created is not None:
        return pd.Timestamp(datetime.fromtimestamp(created))
    return pd.Timestamp(datetime.fromtimestamp(stat.st_mtime))


def _repair_concatenated_basename_rows(raw_text: str) -> str:
    # Some metadata writers occasionally miss a newline between two CSV rows.
    # Insert a row break before a basename token that appears mid-line.
    return CSV_ROW_BASENAME_PATTERN.sub(r"\1\n\2", raw_text)


def _read_csv_with_parser_recovery(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except pd.errors.ParserError:
        raw_text = path.read_text(encoding="utf-8", errors="replace")
        repaired_text = _repair_concatenated_basename_rows(raw_text)

        if repaired_text != raw_text:
            try:
                return pd.read_csv(io.StringIO(repaired_text))
            except pd.errors.ParserError:
                pass

        # Last-resort fallback: keep load alive even with mixed-width rows.
        return pd.read_csv(path, engine="python", on_bad_lines="skip")


def _load_stage_dataframe_with_execution_agg(
    stage: StageSpec,
    *,
    execution_agg: str,
) -> pd.DataFrame:
    if not stage.csv_path.exists():
        return pd.DataFrame(columns=["basename", "file_timestamp", "execution_timestamp"])

    try:
        raw_df = _read_csv_with_parser_recovery(stage.csv_path)
    except Exception as exc:  # pragma: no cover - defensive
        print(
            f"[definitive_execution_plotter] Failed to read {stage.csv_path}: {exc}",
            file=sys.stderr,
        )
        return pd.DataFrame(columns=["basename", "file_timestamp", "execution_timestamp"])

    if raw_df.empty:
        return pd.DataFrame(columns=["basename", "file_timestamp", "execution_timestamp"])

    basename_col = first_existing_column(raw_df.columns, stage.basename_columns)
    if basename_col is None:
        return pd.DataFrame(columns=["basename", "file_timestamp", "execution_timestamp"])

    data = pd.DataFrame()
    data["basename"] = raw_df[basename_col].astype(str).str.strip()
    data["file_timestamp"] = pd.to_datetime(
        data["basename"].map(extract_timestamp_from_basename),
        errors="coerce",
    )

    execution_col = first_existing_column(raw_df.columns, stage.execution_columns)
    if execution_col is None:
        execution_ts = pd.Series(pd.NaT, index=data.index, dtype="datetime64[ns]")
    else:
        execution_ts = parse_execution_series(raw_df[execution_col], stage.execution_format)

    if stage.use_csv_timestamp_as_execution:
        csv_ts = csv_creation_like_timestamp(stage.csv_path)
        if csv_ts is not None:
            execution_ts = execution_ts.fillna(
                pd.Series(csv_ts, index=data.index, dtype="datetime64[ns]")
            )

    if stage.use_basename_as_execution:
        execution_ts = execution_ts.fillna(data["file_timestamp"])

    data["execution_timestamp"] = execution_ts
    data = data[
        data["basename"].ne("")
        & data["file_timestamp"].notna()
        & data["execution_timestamp"].notna()
    ]

    if data.empty:
        return pd.DataFrame(columns=["basename", "file_timestamp", "execution_timestamp"])

    execution_agg_name = str(execution_agg).strip().lower()
    if execution_agg_name not in {"min", "max"}:
        raise ValueError(f"Unsupported execution_agg: {execution_agg}")

    grouped = data.sort_values("execution_timestamp").groupby("basename", as_index=False).agg(
        file_timestamp=("file_timestamp", "first"),
        execution_timestamp=("execution_timestamp", execution_agg_name),
    )
    return grouped


def load_stage_dataframe(stage: StageSpec) -> pd.DataFrame:
    return _load_stage_dataframe_with_execution_agg(stage, execution_agg="max")


def load_stage_first_completion_dataframe(stage: StageSpec) -> pd.DataFrame:
    return _load_stage_dataframe_with_execution_agg(stage, execution_agg="min")


def stage_specs_for_station(
    station: str,
    mingo00_stage0_source: str = DEFAULT_MINGO00_STAGE0_SOURCE,
) -> List[StageSpec]:
    root = STATIONS_ROOT / station
    if station == "MINGO00":
        stage0_history_csv = root / "STAGE_0" / "SIMULATION" / "imported_basenames_history.csv"
        stage0_live_csv = root / "STAGE_0" / "SIMULATION" / "imported_basenames.csv"
        source_choice = (mingo00_stage0_source or DEFAULT_MINGO00_STAGE0_SOURCE).strip().lower()
        if source_choice not in MINGO00_STAGE0_SOURCE_CHOICES:
            source_choice = DEFAULT_MINGO00_STAGE0_SOURCE

        if source_choice == "history" and stage0_history_csv.exists():
            stage0_csv = stage0_history_csv
            stage0_label = "STEP 0 - imported_basenames_history"
        elif source_choice == "auto" and stage0_history_csv.exists():
            stage0_csv = stage0_history_csv
            stage0_label = "STEP 0 - imported_basenames_history"
        else:
            stage0_csv = stage0_live_csv
            stage0_label = "STEP 0 - imported_basenames"
        stage0_execution_columns: Tuple[str, ...] = ("execution_time", "execution_timestamp")
    else:
        stage0_csv = (
            root
            / "STAGE_1"
            / "EVENT_DATA"
            / "STEP_1"
            / "TASK_0"
            / "METADATA"
            / "task_0_metadata_execution.csv"
        )
        stage0_label = "TASK 0 - metadata_execution"
        stage0_execution_columns = ("execution_timestamp",)

    specs: List[StageSpec] = [
        StageSpec(
            index=0,
            label=stage0_label,
            color=STAGE0_COLOR,
            csv_path=stage0_csv,
            basename_columns=("filename_base", "basename", "acquisition_basename", "hld_name", "dat_name"),
            execution_columns=stage0_execution_columns,
            execution_format="%Y-%m-%d_%H.%M.%S" if station != "MINGO00" else None,
            use_csv_timestamp_as_execution=station == "MINGO00",
        ),
    ]

    task_stage_offset = 1
    for task_id in TASK_IDS:
        stage_index = task_stage_offset + (task_id - 1)
        specs.append(
            StageSpec(
                index=stage_index,
                label=f"TASK {task_id} - metadata_execution",
                color=TASK_COLORS[task_id],
                csv_path=root
                / "STAGE_1"
                / "EVENT_DATA"
                / "STEP_1"
                / f"TASK_{task_id}"
                / "METADATA"
                / f"task_{task_id}_metadata_execution.csv",
                basename_columns=("filename_base", "basename", "dat_name", "hld_name"),
                execution_columns=("execution_timestamp",),
                execution_format="%Y-%m-%d_%H.%M.%S",
            )
        )

    return specs


def _empty_stage_dataframe() -> pd.DataFrame:
    return pd.DataFrame(columns=["basename", "file_timestamp", "execution_timestamp"])


def build_station_stage_tables(stages: Sequence[StageSpec]) -> Dict[int, pd.DataFrame]:
    tables: Dict[int, pd.DataFrame] = {}
    ordered_stages = sorted(stages, key=lambda stage: stage.index)
    eligible_basenames: Optional[set[str]] = None

    for stage in ordered_stages:
        if eligible_basenames is not None and not eligible_basenames:
            tables[stage.index] = _empty_stage_dataframe()
            continue

        stage_df = load_stage_dataframe(stage)
        if eligible_basenames is not None and not stage_df.empty:
            stage_df = stage_df[stage_df["basename"].isin(eligible_basenames)]

        if stage_df.empty:
            eligible_basenames = set()
            tables[stage.index] = _empty_stage_dataframe()
            continue

        stage_df = stage_df.sort_values("execution_timestamp").reset_index(drop=True)
        current_stage_basenames = set(stage_df["basename"])
        if eligible_basenames is None:
            # Stage 0 defines the baseline universe of files that are allowed to appear.
            eligible_basenames = current_stage_basenames
        else:
            # A file can only advance if it is present in every previous stage.
            eligible_basenames = current_stage_basenames

        tables[stage.index] = stage_df

    for stage in ordered_stages:
        tables.setdefault(stage.index, _empty_stage_dataframe())
    return tables


def build_station_dataframe(
    stages: Sequence[StageSpec],
    stage_tables: Optional[Dict[int, pd.DataFrame]] = None,
) -> pd.DataFrame:
    empty_columns = [
        "basename",
        "file_timestamp",
        "execution_timestamp",
        "stage_index",
        "stage_label",
        "stage_color",
    ]

    if not stages:
        return pd.DataFrame(columns=empty_columns)

    if stage_tables is None:
        stage_tables = build_station_stage_tables(stages)

    ordered_stages = sorted(stages, key=lambda stage: stage.index)
    rows_by_basename: Dict[str, Dict[str, object]] = {}

    for stage in ordered_stages:
        stage_df = stage_tables.get(stage.index, _empty_stage_dataframe())
        if stage_df is None or stage_df.empty:
            continue

        for row in stage_df.itertuples(index=False):
            existing = rows_by_basename.get(row.basename)
            should_replace = (
                existing is None
                or stage.index > int(existing["stage_index"])
                or (
                    stage.index == int(existing["stage_index"])
                    and row.execution_timestamp > existing["execution_timestamp"]
                )
            )
            if not should_replace:
                continue

            rows_by_basename[row.basename] = {
                "basename": row.basename,
                "file_timestamp": row.file_timestamp,
                "execution_timestamp": row.execution_timestamp,
                "stage_index": stage.index,
                "stage_label": stage.label,
                "stage_color": stage.color,
            }

    if not rows_by_basename:
        return pd.DataFrame(columns=empty_columns)

    result = pd.DataFrame(rows_by_basename.values())
    return result.sort_values(["execution_timestamp", "file_timestamp"]).reset_index(drop=True)


def build_completeness_dataframe(
    stages: Sequence[StageSpec],
    stage_tables: Dict[int, pd.DataFrame],
) -> pd.DataFrame:
    ordered_stages = sorted(stages, key=lambda stage: stage.index)
    if not ordered_stages:
        return pd.DataFrame(columns=["execution_timestamp"])

    stage0_df = stage_tables.get(ordered_stages[0].index, _empty_stage_dataframe())
    denominator = int(stage0_df["basename"].nunique()) if not stage0_df.empty else 0
    if denominator <= 0:
        return pd.DataFrame(columns=["execution_timestamp"])

    time_chunks: List[pd.Series] = []
    for stage in ordered_stages:
        stage_df = stage_tables.get(stage.index, _empty_stage_dataframe())
        if stage_df.empty:
            continue
        ts = pd.to_datetime(stage_df["execution_timestamp"], errors="coerce").dropna()
        if not ts.empty:
            time_chunks.append(ts)

    if not time_chunks:
        return pd.DataFrame(columns=["execution_timestamp"])

    timeline = (
        pd.concat(time_chunks, ignore_index=True)
        .dropna()
        .drop_duplicates()
        .sort_values()
        .reset_index(drop=True)
    )
    if timeline.empty:
        return pd.DataFrame(columns=["execution_timestamp"])

    result = pd.DataFrame({"execution_timestamp": timeline})
    timeline_np = timeline.to_numpy(dtype="datetime64[ns]")
    stage_columns: List[str] = []
    for stage in ordered_stages:
        stage_col = f"stage_{stage.index}"
        stage_columns.append(stage_col)
        stage_df = stage_tables.get(stage.index, _empty_stage_dataframe())
        if stage_df.empty:
            result[stage_col] = 0.0
            continue

        stage_times = (
            pd.to_datetime(stage_df["execution_timestamp"], errors="coerce")
            .dropna()
            .sort_values()
            .to_numpy(dtype="datetime64[ns]")
        )
        if len(stage_times) == 0:
            result[stage_col] = 0.0
            continue

        counts = np.searchsorted(stage_times, timeline_np, side="right")
        result[stage_col] = (counts / float(denominator)) * 100.0

    if stage_columns:
        values = result[stage_columns].to_numpy(dtype=float)
        values = np.minimum.accumulate(values, axis=1)
        values = np.clip(values, 0.0, 100.0)
        result[stage_columns] = values

    return result


def extend_completeness_to_timestamp(
    completeness_df: pd.DataFrame,
    target_timestamp: pd.Timestamp,
) -> pd.DataFrame:
    if completeness_df.empty or "execution_timestamp" not in completeness_df.columns:
        return completeness_df

    y_values = pd.to_datetime(completeness_df["execution_timestamp"], errors="coerce")
    valid = y_values.dropna()
    if valid.empty:
        return completeness_df

    last_idx = valid.index[-1]
    last_ts = pd.Timestamp(valid.iloc[-1])
    target_ts = pd.Timestamp(target_timestamp)

    if last_ts.tzinfo is None and target_ts.tzinfo is not None:
        target_ts = target_ts.tz_localize(None)
    elif last_ts.tzinfo is not None and target_ts.tzinfo is None:
        target_ts = target_ts.tz_localize(last_ts.tzinfo)

    if target_ts <= last_ts:
        return completeness_df

    extension_row = completeness_df.loc[last_idx].copy()
    extension_row["execution_timestamp"] = target_ts
    return pd.concat(
        [completeness_df, pd.DataFrame([extension_row], columns=completeness_df.columns)],
        ignore_index=True,
    )


def _format_eta_duration(delta: pd.Timedelta) -> str:
    total_seconds = max(0, int(round(delta.total_seconds())))
    if total_seconds < 60:
        return "<1 min"

    days, remainder = divmod(total_seconds, 24 * 3600)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    parts: List[str] = []
    if days:
        parts.append(f"{days}d")
    if hours and len(parts) < 2:
        parts.append(f"{hours}h")
    if minutes and len(parts) < 2:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append("<1 min")
    return " ".join(parts)


def _progress_value_at_or_before(
    timestamps: pd.Series,
    progress: pd.Series,
    target_timestamp: pd.Timestamp,
) -> float:
    if timestamps.empty or progress.empty:
        return 0.0

    target_ts = pd.Timestamp(target_timestamp)
    first_ts = pd.Timestamp(timestamps.iloc[0])
    if first_ts.tzinfo is None and target_ts.tzinfo is not None:
        target_ts = target_ts.tz_localize(None)
    elif first_ts.tzinfo is not None and target_ts.tzinfo is None:
        target_ts = target_ts.tz_localize(first_ts.tzinfo)

    idx = int(timestamps.searchsorted(target_ts, side="right") - 1)
    if idx < 0:
        return float(progress.iloc[0])
    return float(progress.iloc[idx])


def _estimate_remaining_from_window(
    progress_start: float,
    progress_end: float,
    elapsed: pd.Timedelta,
) -> Optional[pd.Timedelta]:
    elapsed_seconds = float(elapsed.total_seconds())
    delta_progress = float(progress_end) - float(progress_start)
    if elapsed_seconds <= 0 or delta_progress <= 0:
        return None

    remaining_seconds = elapsed_seconds * (100.0 - float(progress_end)) / delta_progress
    if not np.isfinite(remaining_seconds):
        return None
    return pd.Timedelta(seconds=max(0.0, remaining_seconds))


def _build_window_eta_comment(
    *,
    label: str,
    timestamps: pd.Series,
    progress: pd.Series,
    current_ts: pd.Timestamp,
    current_progress: float,
    first_progress_timestamp: pd.Timestamp,
    window: Optional[timedelta],
) -> str:
    if window is None:
        remaining = _estimate_remaining_from_window(
            0.0,
            current_progress,
            current_ts - first_progress_timestamp,
        )
        if remaining is None:
            return f"ETA using the full final-stage history: unavailable"
        return (
            "ETA using the full final-stage history: "
            f"about {_format_eta_duration(remaining)}"
        )

    window_start = current_ts - window
    anchor_ts = max(window_start, first_progress_timestamp)
    progress_start = _progress_value_at_or_before(
        timestamps,
        progress,
        anchor_ts,
    )
    elapsed = current_ts - anchor_ts
    remaining = _estimate_remaining_from_window(
        progress_start,
        current_progress,
        elapsed,
    )
    if remaining is None:
        return f"ETA using the last {label} final-stage pace: stalled / unavailable"
    return (
        f"ETA using the last {label} final-stage pace: "
        f"about {_format_eta_duration(remaining)}"
    )


def build_eta_progress_series(stages: Sequence[StageSpec]) -> pd.DataFrame:
    ordered_stages = sorted(stages, key=lambda stage: stage.index)
    if not ordered_stages:
        return pd.DataFrame(columns=["execution_timestamp", "progress_pct"])

    stage0_df = load_stage_dataframe(ordered_stages[0])
    denominator = int(stage0_df["basename"].nunique()) if not stage0_df.empty else 0
    if denominator <= 0:
        return pd.DataFrame(columns=["execution_timestamp", "progress_pct"])

    final_stage_df = load_stage_first_completion_dataframe(ordered_stages[-1])
    if final_stage_df.empty:
        return pd.DataFrame(columns=["execution_timestamp", "progress_pct"])

    if not stage0_df.empty:
        allowed_basenames = set(stage0_df["basename"].astype(str))
        final_stage_df = final_stage_df[
            final_stage_df["basename"].astype(str).isin(allowed_basenames)
        ].copy()
    if final_stage_df.empty:
        return pd.DataFrame(columns=["execution_timestamp", "progress_pct"])

    timeline = (
        pd.to_datetime(final_stage_df["execution_timestamp"], errors="coerce")
        .dropna()
        .sort_values()
        .reset_index(drop=True)
    )
    if timeline.empty:
        return pd.DataFrame(columns=["execution_timestamp", "progress_pct"])

    counts = np.arange(1, len(timeline) + 1, dtype=float)
    progress_pct = (counts / float(denominator)) * 100.0
    return pd.DataFrame(
        {
            "execution_timestamp": timeline,
            "progress_pct": np.clip(progress_pct, 0.0, 100.0),
        }
    )


def estimate_time_left_comments(
    completeness_df: pd.DataFrame,
    stages: Sequence[StageSpec],
    current_timestamp: pd.Timestamp,
) -> Tuple[str, str, str]:
    eta_progress_df = build_eta_progress_series(stages)
    if eta_progress_df.empty:
        return (
            "ETA using the last 10 min final-stage pace: unavailable",
            "ETA using the last 2 h final-stage pace: unavailable",
            "ETA using the full final-stage history: unavailable",
        )

    ordered_stages = sorted(stages, key=lambda stage: stage.index)
    final_stage = ordered_stages[-1]
    timestamps = eta_progress_df["execution_timestamp"].reset_index(drop=True)
    progress = (
        pd.to_numeric(eta_progress_df["progress_pct"], errors="coerce")
        .clip(lower=0.0, upper=100.0)
        .reset_index(drop=True)
    )
    current_progress = float(progress.iloc[-1])

    if current_progress >= 99.5:
        return (
            "ETA using the last 10 min final-stage pace: practically finished",
            "ETA using the last 2 h final-stage pace: practically finished",
            "ETA using the full final-stage history: practically finished",
        )

    started_mask = progress > 0.0
    if not started_mask.any():
        unavailable = f"unavailable until {final_stage.label} starts"
        return (
            f"ETA using the last 10 min final-stage pace: {unavailable}",
            f"ETA using the last 2 h final-stage pace: {unavailable}",
            f"ETA using the full final-stage history: {unavailable}",
        )

    first_progress_timestamp = pd.Timestamp(timestamps.loc[started_mask.idxmax()])
    current_ts = pd.Timestamp(current_timestamp)
    if first_progress_timestamp.tzinfo is None and current_ts.tzinfo is not None:
        current_ts = current_ts.tz_localize(None)
    elif first_progress_timestamp.tzinfo is not None and current_ts.tzinfo is None:
        current_ts = current_ts.tz_localize(first_progress_timestamp.tzinfo)

    short_comment = _build_window_eta_comment(
        label="10 min",
        timestamps=timestamps,
        progress=progress,
        current_ts=current_ts,
        current_progress=current_progress,
        first_progress_timestamp=first_progress_timestamp,
        window=ETA_SHORT_WINDOW,
    )
    medium_comment = _build_window_eta_comment(
        label="2 h",
        timestamps=timestamps,
        progress=progress,
        current_ts=current_ts,
        current_progress=current_progress,
        first_progress_timestamp=first_progress_timestamp,
        window=ETA_MEDIUM_WINDOW,
    )
    all_data_comment = _build_window_eta_comment(
        label="full history",
        timestamps=timestamps,
        progress=progress,
        current_ts=current_ts,
        current_progress=current_progress,
        first_progress_timestamp=first_progress_timestamp,
        window=None,
    )

    return short_comment, medium_comment, all_data_comment


def _scatter_stage_points(
    ax: plt.Axes,
    data: pd.DataFrame,
    stages: Sequence[StageSpec],
    point_size: float,
) -> None:
    for stage in stages:
        mask = data["stage_index"] == stage.index
        if not mask.any():
            continue
        stage_points = data.loc[mask]
        if stage.index == 0:
            ax.scatter(
                stage_points["file_timestamp"],
                stage_points["execution_timestamp"],
                s=point_size,
                facecolors="none",
                edgecolors="black",
                linewidths=0.8,
                alpha=0.95,
                zorder=3,
            )
        else:
            ax.scatter(
                stage_points["file_timestamp"],
                stage_points["execution_timestamp"],
                s=point_size,
                facecolors=stage.color,
                edgecolors="none",
                linewidths=0.0,
                alpha=0.9,
                zorder=3,
            )


def _scatter_stage_presence_points(
    ax: plt.Axes,
    data: pd.DataFrame,
    stages: Sequence[StageSpec],
    point_size: float,
) -> None:
    for stage in stages:
        mask = data["stage_index"] == stage.index
        if not mask.any():
            continue
        stage_points = data.loc[mask]
        y_values = np.zeros(len(stage_points), dtype=float)
        if stage.index == 0:
            ax.scatter(
                stage_points["file_timestamp"],
                y_values,
                s=point_size,
                facecolors="none",
                edgecolors="black",
                linewidths=0.8,
                alpha=0.95,
                zorder=3,
            )
        else:
            ax.scatter(
                stage_points["file_timestamp"],
                y_values,
                s=point_size,
                facecolors=stage.color,
                edgecolors="none",
                linewidths=0.0,
                alpha=0.9,
                zorder=3,
            )


def add_stage_colorbar(fig: plt.Figure, axes: Sequence[plt.Axes], stages: Sequence[StageSpec]) -> None:
    colors = [stage.color for stage in stages]
    ticks = [stage.index for stage in stages]
    labels = [stage.label for stage in stages]
    bounds = [ticks[0] - 0.5] + [tick + 0.5 for tick in ticks]
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(bounds, cmap.N)
    mappable = ScalarMappable(norm=norm, cmap=cmap)
    mappable.set_array([])

    cbar = fig.colorbar(
        mappable,
        ax=list(axes),
        boundaries=bounds,
        spacing="uniform",
        drawedges=True,
        ticks=ticks,
        fraction=0.025,
        pad=0.02,
    )
    cbar.ax.invert_yaxis()
    cbar.set_label("Pipeline stage (top earliest -> bottom latest)")
    cbar.ax.set_yticklabels(labels, fontsize=8)
    cbar.ax.text(
        1.45,
        1.01,
        "Earliest stage",
        transform=cbar.ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=8,
    )
    cbar.ax.text(
        1.45,
        -0.03,
        "Latest stage",
        transform=cbar.ax.transAxes,
        ha="left",
        va="top",
        fontsize=8,
    )
    if cbar.solids is not None:
        cbar.solids.set_edgecolor("black")
        cbar.solids.set_linewidth(0.4)


def plot_completeness_fill(
    ax: plt.Axes,
    completeness_df: pd.DataFrame,
    stages: Sequence[StageSpec],
) -> None:
    ax.set_xlim(0.0, 100.0)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.grid(True, axis="x", linestyle="--", linewidth=0.4, alpha=0.65)

    if completeness_df.empty:
        ax.text(
            0.5,
            0.5,
            "No completeness data",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=9,
        )
        return

    ordered_stages = sorted(stages, key=lambda stage: stage.index)
    y_values = pd.to_datetime(completeness_df["execution_timestamp"], errors="coerce")
    if y_values.dropna().empty:
        return

    for idx in range(len(ordered_stages) - 1, -1, -1):
        stage = ordered_stages[idx]
        upper_col = f"stage_{stage.index}"
        if upper_col not in completeness_df.columns:
            continue

        upper = completeness_df[upper_col].to_numpy(dtype=float)
        if idx == len(ordered_stages) - 1:
            lower = np.zeros_like(upper)
        else:
            lower_col = f"stage_{ordered_stages[idx + 1].index}"
            if lower_col not in completeness_df.columns:
                lower = np.zeros_like(upper)
            else:
                lower = completeness_df[lower_col].to_numpy(dtype=float)

        ax.fill_betweenx(
            y_values,
            lower,
            upper,
            facecolor=stage.color,
            edgecolor="black",
            linewidth=0.25,
            alpha=0.95,
            step="post",
            zorder=2,
        )


def completeness_pie_payload(
    completeness_df: pd.DataFrame,
    stages: Sequence[StageSpec],
) -> Tuple[List[str], List[str], List[float]]:
    ordered_stages = sorted(stages, key=lambda stage: stage.index)
    if not ordered_stages:
        return [], [], []
    if completeness_df.empty:
        return [stage.label for stage in ordered_stages], [stage.color for stage in ordered_stages], [0.0] * len(ordered_stages)

    last_row = completeness_df.iloc[-1]
    cumulative: List[float] = []
    for stage in ordered_stages:
        cumulative.append(float(last_row.get(f"stage_{stage.index}", 0.0)))

    if cumulative:
        values = np.asarray(cumulative, dtype=float)
        values = np.clip(values, 0.0, 100.0)
        values = np.minimum.accumulate(values)
        cumulative = values.tolist()

    slices: List[float] = []
    for idx in range(len(ordered_stages)):
        if idx == len(ordered_stages) - 1:
            value = cumulative[idx]
        else:
            value = cumulative[idx] - cumulative[idx + 1]
        slices.append(max(0.0, float(value)))

    total = float(sum(slices))
    if total <= 0:
        return [stage.label for stage in ordered_stages], [stage.color for stage in ordered_stages], [0.0] * len(ordered_stages)

    normalized = [(value / total) * 100.0 for value in slices]
    labels = [stage.label for stage in ordered_stages]
    colors = [stage.color for stage in ordered_stages]
    return labels, colors, normalized


def plot_completeness_pie(
    ax: plt.Axes,
    completeness_df: pd.DataFrame,
    stages: Sequence[StageSpec],
) -> None:
    labels, colors, values = completeness_pie_payload(completeness_df, stages)
    ax.set_title("Completeness split (%)\n(STEP 0 sample only)")
    ax.set_aspect("equal")

    if not values or max(values) <= 0:
        ax.text(
            0.5,
            0.5,
            "No completeness data",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=9,
        )
        return

    ax.pie(
        values,
        colors=colors,
        startangle=90,
        counterclock=False,
        wedgeprops=dict(edgecolor="black", linewidth=0.5),
        autopct=lambda pct: f"{pct:.1f}%" if pct >= 2.0 else "",
        pctdistance=0.75,
        textprops=dict(fontsize=7),
    )


def format_datetime_axes(top_ax: plt.Axes, middle_ax: plt.Axes, bottom_ax: plt.Axes) -> None:
    top_y_formatter = mdates.DateFormatter("%H:%M")
    middle_y_formatter = mdates.DateFormatter("%Y-%m-%d")
    top_ax.yaxis.set_major_formatter(top_y_formatter)
    middle_ax.yaxis.set_major_formatter(middle_y_formatter)

    x_formatter = mdates.DateFormatter("%Y-%m-%d\n%H:%M")
    bottom_ax.xaxis.set_major_formatter(x_formatter)
    bottom_ax.tick_params(axis="x", rotation=0)


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
) -> Tuple[
    List[str],
    float,
    float,
    Path,
    str,
    List[str],
    Tuple[float, float, float],
    float,
]:
    config_path = Path(args.config).expanduser()
    config = load_config(config_path)

    if args.last_hours is not None:
        last_hours = float(args.last_hours)
    else:
        try:
            last_hours = float(config.get("last_hours", DEFAULT_LAST_HOURS))
        except (TypeError, ValueError):
            raise ValueError("'last_hours' in config must be numeric")

    if args.point_size is not None:
        point_size = float(args.point_size)
    else:
        try:
            point_size = float(config.get("point_size", DEFAULT_POINT_SIZE))
        except (TypeError, ValueError):
            raise ValueError("'point_size' in config must be numeric")

    output_raw = args.output
    if output_raw is None:
        config_output = config.get("output")
        output_raw = str(config_output) if config_output is not None else None
    output_path = resolve_output_path(output_raw, config_path)

    if args.mingo00_stage0_source is not None:
        mingo00_stage0_source = str(args.mingo00_stage0_source).strip().lower()
    else:
        raw_source = config.get("mingo00_stage0_source", DEFAULT_MINGO00_STAGE0_SOURCE)
        mingo00_stage0_source = str(raw_source).strip().lower()
    if mingo00_stage0_source not in MINGO00_STAGE0_SOURCE_CHOICES:
        allowed = ", ".join(MINGO00_STAGE0_SOURCE_CHOICES)
        raise ValueError(
            f"'mingo00_stage0_source' must be one of: {allowed}"
        )

    shared_x_raw = config.get("shared_x_stations", list(DEFAULT_SHARED_X_STATIONS))
    free_x_raw = config.get("free_x_stations", list(DEFAULT_FREE_X_STATIONS))

    if not isinstance(shared_x_raw, list):
        raise ValueError("'shared_x_stations' in config must be a list")
    if not isinstance(free_x_raw, list):
        raise ValueError("'free_x_stations' in config must be a list")

    shared_x_stations = normalize_existing_station_tokens([str(item) for item in shared_x_raw])
    free_x_stations = normalize_existing_station_tokens([str(item) for item in free_x_raw])

    config_stations_raw = config.get("stations")
    if args.stations is not None:
        stations = resolve_station_selection(args.stations)
    elif isinstance(config_stations_raw, list) and len(config_stations_raw) > 0:
        stations = resolve_station_selection([str(item) for item in config_stations_raw])
    else:
        grouped_scope = sorted(dict.fromkeys(shared_x_stations + free_x_stations))
        stations = grouped_scope if grouped_scope else list_available_stations()

    selected_set = set(stations)
    shared_effective = sorted(
        set(station for station in shared_x_stations if station in selected_set)
        - set(station for station in free_x_stations if station in selected_set)
    )

    panel_ratios_raw = config.get("panel_height_ratios", list(DEFAULT_PANEL_HEIGHT_RATIOS))
    if not isinstance(panel_ratios_raw, list):
        raise ValueError("'panel_height_ratios' in config must be a list")
    if len(panel_ratios_raw) != 3:
        raise ValueError("'panel_height_ratios' in config must have exactly 3 numeric values")
    try:
        panel_height_ratios = (
            float(panel_ratios_raw[0]),
            float(panel_ratios_raw[1]),
            float(panel_ratios_raw[2]),
        )
    except (TypeError, ValueError):
        raise ValueError("'panel_height_ratios' in config must contain numeric values")
    if any(value <= 0 for value in panel_height_ratios):
        raise ValueError("'panel_height_ratios' values must be > 0")

    try:
        middle_log_scale_seconds = float(
            config.get("middle_log_scale_seconds", DEFAULT_MIDDLE_LOG_SCALE_SECONDS)
        )
    except (TypeError, ValueError):
        raise ValueError("'middle_log_scale_seconds' in config must be numeric")
    if middle_log_scale_seconds <= 0:
        raise ValueError("'middle_log_scale_seconds' in config must be > 0")

    return (
        stations,
        last_hours,
        point_size,
        output_path,
        mingo00_stage0_source,
        shared_effective,
        panel_height_ratios,
        middle_log_scale_seconds,
    )


def compute_shared_x_limits(
    station_data: Dict[str, pd.DataFrame],
    stations_to_share: Sequence[str],
) -> Optional[Tuple[pd.Timestamp, pd.Timestamp]]:
    min_values: List[pd.Timestamp] = []
    max_values: List[pd.Timestamp] = []

    for station in stations_to_share:
        data = station_data.get(station)
        if data is None or data.empty:
            continue
        min_values.append(pd.Timestamp(data["file_timestamp"].min()))
        max_values.append(pd.Timestamp(data["file_timestamp"].max()))

    if not min_values:
        return None

    shared_min = min(min_values)
    shared_max = max(max_values)
    if shared_min == shared_max:
        margin = timedelta(minutes=30)
    else:
        margin = (shared_max - shared_min) / 30
    return shared_min - margin, shared_max + margin


def plot_station_page(
    station: str,
    data: pd.DataFrame,
    completeness_df: pd.DataFrame,
    stages: Sequence[StageSpec],
    pdf: PdfPages,
    last_hours: float,
    point_size: float,
    panel_height_ratios: Tuple[float, float, float],
    middle_log_scale_seconds: float,
    x_limits_override: Optional[Tuple[pd.Timestamp, pd.Timestamp]] = None,
) -> None:
    if data.empty:
        title = (
            f"{station} - Definitive execution map\n"
            "ETA using the last 10 min final-stage pace: unavailable\n"
            "ETA using the last 2 h final-stage pace: unavailable\n"
            "ETA using the full final-stage history: unavailable"
        )
        fig, ax = plt.subplots(figsize=(13, 5))
        fig.suptitle(title, fontsize=14)
        ax.axis("off")
        ax.text(
            0.5,
            0.5,
            "No valid rows found in stage metadata files for this station.",
            ha="center",
            va="center",
            fontsize=11,
        )
        pdf_save_rasterized_page(pdf, fig, dpi=150)
        plt.close(fig)
        return

    x_min = data["file_timestamp"].min()
    x_max = data["file_timestamp"].max()
    y_min = data["execution_timestamp"].min()
    y_max = data["execution_timestamp"].max()
    if y_min.tzinfo is None:
        now = pd.Timestamp.utcnow().tz_localize(None)
    else:
        now = pd.Timestamp.utcnow().tz_convert(y_min.tzinfo)

    completeness_for_plot = extend_completeness_to_timestamp(completeness_df, now)
    short_eta_comment, medium_eta_comment, all_data_eta_comment = estimate_time_left_comments(
        completeness_for_plot,
        stages,
        now,
    )
    title = (
        f"{station} - Definitive execution map\n"
        f"{short_eta_comment}\n"
        f"{medium_eta_comment}\n"
        f"{all_data_eta_comment}"
    )

    fig_width = 16.6
    fig_height = 9.7
    top_ratio = max(float(panel_height_ratios[0]), 1e-6)
    middle_ratio = max(float(panel_height_ratios[1]), 1e-6)
    sum_height_ratios = max(float(sum(panel_height_ratios)), 1e-6)

    # Size the right column so top-right can be square without leaving unused horizontal gap.
    left_col_units = 4.0
    target_right_fraction = (fig_height / fig_width) * (top_ratio / sum_height_ratios)
    target_right_fraction = min(max(target_right_fraction, 0.05), 0.45)
    right_col_units = (target_right_fraction * left_col_units) / max(
        1e-6, (1.0 - target_right_fraction)
    )

    fig = plt.figure(figsize=(fig_width, fig_height), constrained_layout=True)
    grid = fig.add_gridspec(
        3,
        2,
        height_ratios=list(panel_height_ratios),
        width_ratios=[left_col_units, right_col_units],
    )
    ax_zoom = fig.add_subplot(grid[0, 0])
    ax_zoom_comp = fig.add_subplot(grid[0, 1], sharey=ax_zoom)
    ax_full = fig.add_subplot(grid[1, 0], sharex=ax_zoom)
    ax_full_comp = fig.add_subplot(grid[1, 1], sharey=ax_full, sharex=ax_zoom_comp)
    ax_presence = fig.add_subplot(grid[2, 0], sharex=ax_zoom)
    ax_pie = fig.add_subplot(grid[2, 1])
    fig.suptitle(title, fontsize=14)

    _scatter_stage_points(ax_zoom, data, stages, point_size=point_size)
    _scatter_stage_points(ax_full, data, stages, point_size=point_size)
    _scatter_stage_presence_points(ax_presence, data, stages, point_size=point_size)
    plot_completeness_fill(ax_zoom_comp, completeness_for_plot, stages)
    plot_completeness_fill(ax_full_comp, completeness_for_plot, stages)
    plot_completeness_pie(ax_pie, completeness_for_plot, stages)

    # Keep top-right square; make middle-right have the same X size as top-right.
    middle_comp_box_aspect = middle_ratio / top_ratio

    ax_zoom_comp.set_box_aspect(1)
    ax_full_comp.set_box_aspect(middle_comp_box_aspect)
    ax_pie.set_box_aspect(1)
    ax_zoom_comp.set_anchor("W")
    ax_full_comp.set_anchor("W")
    ax_pie.set_anchor("W")

    for ax in (ax_zoom, ax_full):
        ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.65)
        ax.set_ylabel("Execution time")
    ax_presence.grid(True, axis="x", linestyle="--", linewidth=0.4, alpha=0.65)
    ax_presence.set_ylabel("Presence")
    ax_zoom_comp.set_title("Completeness (%) - zoom")
    ax_full_comp.set_title("Completeness (%) - full")
    scope_note = "Scope: STEP 0 chain only (residual files excluded)"
    for ax in (ax_zoom_comp, ax_full_comp):
        ax.text(
            0.01,
            0.99,
            scope_note,
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=7,
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.65),
        )
    ax_zoom_comp.tick_params(axis="x", labelbottom=False)
    ax_zoom_comp.tick_params(axis="y", labelleft=False)
    ax_full_comp.tick_params(axis="y", labelleft=False)
    ax_full_comp.set_xlabel("Completeness (%)")

    ax_zoom.set_title(f"Last {last_hours:g} hours from now (UTC)")
    ax_full.set_title("Full execution history (soft log-scaled by recency)")
    ax_presence.set_title("Presence vs data time (execution-time independent)")
    ax_presence.set_xlabel("Data time (from basename)")
    ax_presence.set_yticks([0])
    ax_presence.set_yticklabels(["present"])
    ax_presence.set_ylim(-0.8, 0.8)

    if x_limits_override is None:
        if x_min == x_max:
            x_margin = timedelta(minutes=30)
        else:
            x_margin = (x_max - x_min) / 30
        x_limits = (x_min - x_margin, x_max + x_margin)
    else:
        x_limits = x_limits_override

    full_y_margin = timedelta(minutes=3)
    zoom_y_margin = timedelta(minutes=1)
    zoom_lower = now - timedelta(hours=last_hours)

    for ax in (ax_zoom, ax_full, ax_presence):
        ax.set_xlim(*x_limits)

    full_y_lower = min(y_min, now) - full_y_margin
    now_visible_upper = now + timedelta(minutes=NOW_Y_MARGIN_MINUTES)
    full_y_upper = max(y_max + timedelta(seconds=1), now_visible_upper)
    ax_full.set_ylim(full_y_lower, full_y_upper)
    zoom_upper = max(y_max + zoom_y_margin, now_visible_upper)
    if zoom_lower >= zoom_upper:
        zoom_lower = zoom_upper - timedelta(minutes=5)
    ax_zoom.set_ylim(zoom_lower, zoom_upper)

    # Middle panel: log-scale by recency (age) so recent executions get more visual space.
    middle_ref_num = mdates.date2num(full_y_upper)
    scale_seconds = float(middle_log_scale_seconds)

    def _middle_y_forward(values):
        arr = np.asarray(values, dtype=float)
        age_seconds = np.maximum(0.0, (middle_ref_num - arr) * 86400.0)
        return -np.log10((age_seconds / scale_seconds) + 1.0)

    def _middle_y_inverse(values):
        arr = np.asarray(values, dtype=float)
        age_seconds = (np.power(10.0, -arr) - 1.0) * scale_seconds
        return middle_ref_num - (age_seconds / 86400.0)

    ax_full.set_yscale("function", functions=(_middle_y_forward, _middle_y_inverse))

    format_datetime_axes(ax_zoom, ax_full, ax_presence)
    for ax in (ax_zoom, ax_full, ax_zoom_comp, ax_full_comp):
        ax.axhline(now, color="red", linestyle="--", alpha=0.3, zorder=10)

    # Re-apply after axis transforms so layout is preserved.
    ax_zoom_comp.set_box_aspect(1)
    ax_full_comp.set_box_aspect(middle_comp_box_aspect)
    ax_pie.set_box_aspect(1)
    ax_zoom_comp.set_anchor("W")
    ax_full_comp.set_anchor("W")
    ax_pie.set_anchor("W")

    stage_counts = data["stage_index"].value_counts().to_dict()
    count_lines = [f"Total files: {len(data)}"]
    for stage in stages:
        count_lines.append(f"{stage.label}: {int(stage_counts.get(stage.index, 0))}")

    ax_full.text(
        0.01,
        0.99,
        "\n".join(count_lines),
        transform=ax_full.transAxes,
        ha="left",
        va="top",
        fontsize=8,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.75),
    )

    add_stage_colorbar(
        fig,
        (ax_zoom, ax_zoom_comp, ax_full, ax_full_comp, ax_presence),
        stages,
    )
    pdf_save_rasterized_page(pdf, fig, dpi=160)
    plt.close(fig)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create per-station definitive execution maps "
            "(file-time on X, execution-time on Y)."
        )
    )
    parser.add_argument(
        "-s",
        "--stations",
        nargs="+",
        metavar="STATION",
        help="Stations to include (e.g. 1, 01, MINGO01). Defaults to all detected stations.",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=str(DEFAULT_CONFIG_PATH),
        help=f"JSON config path (default: {DEFAULT_CONFIG_PATH}).",
    )
    parser.add_argument(
        "--last-hours",
        type=float,
        default=None,
        help="Height of the top zoom panel in hours (overrides config).",
    )
    parser.add_argument(
        "--point-size",
        type=float,
        default=None,
        help="Scatter marker size (overrides config).",
    )
    parser.add_argument(
        "--mingo00-stage0-source",
        choices=MINGO00_STAGE0_SOURCE_CHOICES,
        default=None,
        help=(
            "MINGO00 stage-0 source: 'live' uses imported_basenames.csv, "
            "'history' uses imported_basenames_history.csv, "
            "'auto' prefers history when present."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Optional output PDF path (overrides config).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    configure_matplotlib_style()

    try:
        (
            stations,
            last_hours,
            point_size,
            output_path,
            mingo00_stage0_source,
            shared_x_stations,
            panel_height_ratios,
            middle_log_scale_seconds,
        ) = resolve_runtime_options(args)
    except ValueError as exc:
        print(f"[definitive_execution_plotter] {exc}", file=sys.stderr)
        return 1

    if last_hours <= 0:
        print("[definitive_execution_plotter] --last-hours must be > 0", file=sys.stderr)
        return 1
    if point_size <= 0:
        print("[definitive_execution_plotter] --point-size must be > 0", file=sys.stderr)
        return 1

    if not stations:
        print("[definitive_execution_plotter] No stations found to process.", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)

    station_stages: Dict[str, List[StageSpec]] = {}
    station_data: Dict[str, pd.DataFrame] = {}
    station_completeness: Dict[str, pd.DataFrame] = {}
    for station in stations:
        if station == "MINGO00" and mingo00_stage0_source in ("live", "auto"):
            live_registry_path = (
                STATIONS_ROOT / "MINGO00" / "STAGE_0" / "SIMULATION" / "imported_basenames.csv"
            )
            try:
                added_count, removed_count = sync_live_registry_with_ground_truth(
                    live_registry_path,
                    STATIONS_ROOT / "MINGO00",
                )
                if added_count or removed_count:
                    print(
                        "[definitive_execution_plotter] "
                        f"MINGO00 live registry sync: added={added_count}, removed={removed_count}",
                        file=sys.stderr,
                    )
            except Exception as exc:  # pragma: no cover - defensive
                print(
                    "[definitive_execution_plotter] "
                    f"MINGO00 live registry sync failed: {exc}",
                    file=sys.stderr,
                )

        stages = stage_specs_for_station(station, mingo00_stage0_source=mingo00_stage0_source)
        station_stages[station] = stages
        stage_tables = build_station_stage_tables(stages)
        station_data[station] = build_station_dataframe(stages, stage_tables=stage_tables)
        station_completeness[station] = build_completeness_dataframe(stages, stage_tables)

    shared_x_limits = compute_shared_x_limits(station_data, shared_x_stations)
    shared_x_station_set = set(shared_x_stations)

    with PdfPages(output_path) as pdf:
        for station in stations:
            stages = station_stages[station]
            station_df = station_data[station]
            completeness_df = station_completeness[station]
            x_limits_override = shared_x_limits if station in shared_x_station_set else None
            plot_station_page(
                station=station,
                data=station_df,
                completeness_df=completeness_df,
                stages=stages,
                pdf=pdf,
                last_hours=last_hours,
                point_size=point_size,
                panel_height_ratios=panel_height_ratios,
                middle_log_scale_seconds=middle_log_scale_seconds,
                x_limits_override=x_limits_override,
            )

    print(f"[definitive_execution_plotter] Saved PDF to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
