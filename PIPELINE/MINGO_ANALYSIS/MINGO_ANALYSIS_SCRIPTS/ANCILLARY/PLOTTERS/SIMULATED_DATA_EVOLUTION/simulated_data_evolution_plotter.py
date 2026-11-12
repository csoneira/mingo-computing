#!/usr/bin/env python3

"""Plot simulated parameter evolution with MASTER-stage color coding."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import warnings
from typing import Dict, List, Optional, Sequence, Tuple

import ast
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import colormaps
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.colors import to_hex


SCRIPT_PATH = Path(__file__).resolve()


_REPO_IMPORT_ROOT = SCRIPT_PATH.parents[6]
if str(_REPO_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_IMPORT_ROOT))
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root

REPO_ROOT = get_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.plot_utils import pdf_save_rasterized_page  # noqa: E402


PLOTTER_DIR = SCRIPT_PATH.parent
PLOTS_DIR = PLOTTER_DIR / "PLOTS"
STATIONS_ROOT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
DEFAULT_SIM_PARAMS = REPO_ROOT / "PIPELINE" / "MINGO_DIGITAL_TWIN" / "SIMULATION_OUTPUTS" / "SIMULATED_DATA" / "step_final_simulation_params.csv"
DEFAULT_OUTPUT = PLOTS_DIR / "simulated_data_evolution_report.pdf"
DEFAULT_CONFIG_PATH = PLOTTER_DIR / "simulated_data_evolution_config.json"
DEFAULT_STATION = "MINGO00"
DEFAULT_MINGO00_STAGE0_SOURCE = "auto"
MINGO00_STAGE0_SOURCE_CHOICES: Tuple[str, ...] = ("live", "history", "auto")
DEFAULT_PARAMS: Tuple[str, ...] = ("execution_time", "cos_n", "flux_cm2_min", "eff_1", "selected_rows")
DEFAULT_POINT_SIZE = 8.0
DEFAULT_ALPHA = 0.55
DEFAULT_EXECUTION_LOG_SCALE_SECONDS = 3600.0
UNTRACKED_STAGE_INDEX = -1
UNTRACKED_STAGE_LABEL = "UNTRACKED (not in STEP 0 history)"
UNTRACKED_STAGE_COLOR = "#bdbdbd"
UNTRACKED_SCATTER_ALPHA_SCALE = 0.05
UNTRACKED_HIST_ALPHA = 0.12
TASK_IDS: Tuple[int, ...] = (1, 2, 3, 4, 5)
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


def configure_matplotlib_style() -> None:
    plt.style.use("seaborn-v0_8-whitegrid")


def now_timestamp_text() -> str:
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


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


def _resolve_path(raw_value: str, config_path: Path) -> Path:
    candidate = Path(raw_value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (config_path.parent / candidate).resolve()


def resolve_runtime_options(
    args: argparse.Namespace,
) -> Tuple[Path, str, str, List[str], float, float, float, Path]:
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)

    sim_params_raw = args.sim_params if args.sim_params is not None else config.get("sim_params")
    station_raw = args.station if args.station is not None else config.get("station")
    output_raw = args.output if args.output is not None else config.get("output")
    params_raw = args.params if args.params is not None else config.get("params")
    stage0_source_raw = (
        args.mingo00_stage0_source
        if args.mingo00_stage0_source is not None
        else config.get("mingo00_stage0_source", DEFAULT_MINGO00_STAGE0_SOURCE)
    )

    if sim_params_raw is None:
        sim_params_path = DEFAULT_SIM_PARAMS
    else:
        sim_params_path = _resolve_path(str(sim_params_raw), config_path)

    station = str(station_raw).strip() if station_raw is not None else DEFAULT_STATION
    mingo00_stage0_source = str(stage0_source_raw).strip().lower()
    if mingo00_stage0_source not in MINGO00_STAGE0_SOURCE_CHOICES:
        allowed = ", ".join(MINGO00_STAGE0_SOURCE_CHOICES)
        raise ValueError(f"'mingo00_stage0_source' must be one of: {allowed}")

    if output_raw is None:
        output_path = DEFAULT_OUTPUT
    else:
        output_path = _resolve_path(str(output_raw), config_path)

    if params_raw is None:
        params = list(DEFAULT_PARAMS)
    elif isinstance(params_raw, list):
        params = [str(value).strip() for value in params_raw if str(value).strip()]
    else:
        raise ValueError("'params' in config must be a list of column names.")
    if not params:
        raise ValueError("At least one plotting parameter must be provided.")

    if args.point_size is not None:
        point_size = float(args.point_size)
    else:
        point_size = float(config.get("point_size", DEFAULT_POINT_SIZE))

    if args.alpha is not None:
        alpha = float(args.alpha)
    else:
        alpha = float(config.get("alpha", DEFAULT_ALPHA))

    if args.execution_log_scale_seconds is not None:
        execution_log_scale_seconds = float(args.execution_log_scale_seconds)
    else:
        execution_log_scale_seconds = float(
            config.get("execution_log_scale_seconds", DEFAULT_EXECUTION_LOG_SCALE_SECONDS)
        )

    return (
        sim_params_path,
        station,
        mingo00_stage0_source,
        params,
        point_size,
        alpha,
        execution_log_scale_seconds,
        output_path,
    )


def normalize_station_token(token: str) -> str:
    clean = token.strip().upper()
    if clean.startswith("MINGO"):
        clean = clean[5:]
    digits = "".join(ch for ch in clean if ch.isdigit())
    if not digits:
        return DEFAULT_STATION
    return f"MINGO{int(digits):02d}"


def normalize_basename(value: object) -> str:
    text = str(value).strip()
    if not text:
        return ""
    return Path(text).stem.strip()


def build_shared_task_color_map() -> Dict[int, str]:
    # Keep task colors aligned with definitive_execution_plotter.
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


def stage_specs_for_station(
    station: str,
    mingo00_stage0_source: str = DEFAULT_MINGO00_STAGE0_SOURCE,
) -> List[StageSpec]:
    root = STATIONS_ROOT / station
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
    specs: List[StageSpec] = [
        StageSpec(
            index=0,
            label=stage0_label,
            color=STAGE0_COLOR,
            csv_path=stage0_csv,
            basename_columns=("basename", "filename_base", "hld_name", "dat_name"),
        )
    ]
    for task_id in TASK_IDS:
        specs.append(
            StageSpec(
                index=task_id,
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
            )
        )
    return specs


def load_stage_basenames(stage: StageSpec) -> set[str]:
    if not stage.csv_path.exists():
        return set()
    try:
        raw = pd.read_csv(stage.csv_path, low_memory=False)
    except Exception as exc:  # pragma: no cover - defensive
        print(
            f"[simulated_data_evolution_plotter] Failed to read {stage.csv_path}: {exc}",
            file=sys.stderr,
        )
        return set()
    column = next((col for col in stage.basename_columns if col in raw.columns), None)
    if column is None:
        return set()
    return {
        normalize_basename(value)
        for value in raw[column].astype(str)
        if normalize_basename(value)
    }


def load_stage_execution_timestamp_map(stage: StageSpec) -> Dict[str, pd.Timestamp]:
    if not stage.csv_path.exists():
        return {}
    try:
        raw = pd.read_csv(stage.csv_path, low_memory=False)
    except Exception as exc:  # pragma: no cover - defensive
        print(
            f"[simulated_data_evolution_plotter] Failed to read {stage.csv_path}: {exc}",
            file=sys.stderr,
        )
        return {}

    basename_col = next((col for col in stage.basename_columns if col in raw.columns), None)
    if basename_col is None or "execution_timestamp" not in raw.columns:
        return {}

    frame = raw[[basename_col, "execution_timestamp"]].copy()
    frame["basename"] = frame[basename_col].map(normalize_basename)
    frame["execution_dt"] = pd.to_datetime(
        frame["execution_timestamp"],
        errors="coerce",
        format="%Y-%m-%d_%H.%M.%S",
    )
    missing_mask = frame["execution_dt"].isna()
    if missing_mask.any():
        frame.loc[missing_mask, "execution_dt"] = pd.to_datetime(
            frame.loc[missing_mask, "execution_timestamp"],
            errors="coerce",
            utc=False,
        )
    frame = frame.dropna(subset=["basename", "execution_dt"])
    if frame.empty:
        return {}

    frame = frame.sort_values(["basename", "execution_dt"]).groupby("basename").tail(1)
    return dict(zip(frame["basename"], frame["execution_dt"]))


def build_chained_stage_sets(stages: Sequence[StageSpec]) -> Dict[int, set[str]]:
    stage_sets: Dict[int, set[str]] = {}
    ordered = sorted(stages, key=lambda stage: stage.index)
    eligible: Optional[set[str]] = None
    for stage in ordered:
        current = load_stage_basenames(stage)
        if eligible is not None:
            current = current.intersection(eligible)
        stage_sets[stage.index] = current
        eligible = current
    return stage_sets


def build_raw_stage_sets(stages: Sequence[StageSpec]) -> Dict[int, set[str]]:
    return {stage.index: load_stage_basenames(stage) for stage in stages}


def add_stage_execution_columns(
    df: pd.DataFrame,
    stages: Sequence[StageSpec],
) -> pd.DataFrame:
    result = df.copy()
    for stage in stages:
        if stage.index < 1:
            continue
        timestamp_map = load_stage_execution_timestamp_map(stage)
        if not timestamp_map:
            continue
        col = f"__task_{stage.index}_execution_dt"
        result[col] = pd.to_datetime(result["basename"].map(timestamp_map), errors="coerce")
    return result


def build_latest_stage_map(
    stages: Sequence[StageSpec],
    stage_sets: Dict[int, set[str]],
) -> Dict[str, int]:
    ordered = sorted(stages, key=lambda stage: stage.index)
    if not ordered:
        return {}

    baseline = stage_sets.get(ordered[0].index, set())
    latest: Dict[str, int] = {basename: ordered[0].index for basename in baseline}
    for stage in ordered[1:]:
        for basename in stage_sets.get(stage.index, set()):
            latest[basename] = stage.index
    return latest


def parse_efficiencies_column(df: pd.DataFrame) -> pd.DataFrame:
    if {"eff_p1", "eff_p2", "eff_p3", "eff_p4"}.issubset(df.columns):
        return df
    if "efficiencies" not in df.columns:
        return df

    eff_series = df["efficiencies"]
    if eff_series.apply(lambda value: isinstance(value, (list, tuple))).any():
        eff_frame = pd.DataFrame(
            eff_series.tolist(),
            columns=["eff_p1", "eff_p2", "eff_p3", "eff_p4"],
        )
    else:
        parsed_rows = []
        for value in eff_series:
            if value is None or (isinstance(value, float) and np.isnan(value)):
                parsed_rows.append([np.nan, np.nan, np.nan, np.nan])
                continue
            if isinstance(value, (list, tuple)):
                parsed_rows.append(list(value[:4]))
                continue
            text = str(value).strip()
            if not text:
                parsed_rows.append([np.nan, np.nan, np.nan, np.nan])
                continue
            try:
                parsed = ast.literal_eval(text)
            except (SyntaxError, ValueError):
                parsed = None
            if isinstance(parsed, (list, tuple)) and len(parsed) >= 4:
                parsed_rows.append(list(parsed[:4]))
            else:
                parts = [part.strip() for part in text.strip("[]").split(",")]
                if len(parts) >= 4:
                    parsed_rows.append(parts[:4])
                else:
                    parsed_rows.append([np.nan, np.nan, np.nan, np.nan])
        eff_frame = pd.DataFrame(parsed_rows, columns=["eff_p1", "eff_p2", "eff_p3", "eff_p4"])

    for col in ("eff_p1", "eff_p2", "eff_p3", "eff_p4"):
        df[col] = pd.to_numeric(eff_frame[col], errors="coerce")
    return df


def normalize_sim_params(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "z_plane_1": "z_p1",
        "z_plane_2": "z_p2",
        "z_plane_3": "z_p3",
        "z_plane_4": "z_p4",
    }
    df = df.rename(columns={old: new for old, new in rename_map.items() if old in df.columns})
    df = parse_efficiencies_column(df)

    if "selected_rows" not in df.columns and "requested_rows" in df.columns:
        df["selected_rows"] = df["requested_rows"]
    for numeric_col in ("selected_rows", "requested_rows", "sample_start_index", "param_set_id"):
        if numeric_col in df.columns:
            df[numeric_col] = pd.to_numeric(df[numeric_col], errors="coerce")

    if "execution_time" in df.columns:
        df["execution_time"] = pd.to_datetime(df["execution_time"], errors="coerce")

    if "file_name" in df.columns:
        df["basename"] = df["file_name"].astype(str).map(normalize_basename)
    elif "basename" in df.columns:
        df["basename"] = df["basename"].astype(str).map(normalize_basename)
    else:
        raise ValueError("Simulation params file must contain 'file_name' or 'basename'.")
    return df


def expand_params(raw_params: Sequence[str], df: pd.DataFrame) -> List[str]:
    expanded: List[str] = []
    for token in raw_params:
        text = str(token).strip()
        if not text:
            continue
        lowered = text.lower()

        if lowered == "efficiencies":
            expanded.extend(["eff_p1", "eff_p2", "eff_p3", "eff_p4"])
            continue
        if lowered in {"z_positions", "z_planes"}:
            expanded.extend(["z_p1", "z_p2", "z_p3", "z_p4"])
            continue

        eff_match = re.match(r"^eff[_\-]?([1-4])$", lowered)
        if eff_match:
            expanded.append(f"eff_p{int(eff_match.group(1))}")
            continue

        z_match = re.match(r"^z[_\-]?p?([1-4])$", lowered)
        if z_match:
            expanded.append(f"z_p{int(z_match.group(1))}")
            continue

        if lowered in {"flux_cm_min", "flux_cm_minute", "flux_cm"}:
            expanded.append("flux_cm2_min")
            continue

        expanded.append(text)

    resolved: List[str] = []
    for col in expanded:
        if col not in df.columns:
            continue
        series = df[col]
        is_numeric = pd.api.types.is_numeric_dtype(series)
        is_datetime = pd.api.types.is_datetime64_any_dtype(series)
        if not (is_numeric or is_datetime):
            continue
        if col not in resolved:
            resolved.append(col)
    return resolved


def _compute_axis_limits(series: pd.Series) -> Optional[Tuple[object, object]]:
    valid = series.dropna()
    if valid.empty:
        return None

    if pd.api.types.is_datetime64_any_dtype(valid):
        low = valid.min()
        high = valid.max()
        if low == high:
            pad = pd.Timedelta(minutes=5)
        else:
            pad = (high - low) / 20
        return low - pad, high + pad

    numeric = pd.to_numeric(valid, errors="coerce").dropna()
    if numeric.empty:
        return None
    low = float(numeric.min())
    high = float(numeric.max())
    if np.isclose(low, high):
        low -= 1.0
        high += 1.0
    else:
        span = high - low
        pad = span * 0.05
        low -= pad
        high += pad
    return low, high


def add_stage_columns(
    df: pd.DataFrame,
    latest_stage_by_basename: Dict[str, int],
    stage_labels: Dict[int, str],
    stage_colors: Dict[int, str],
) -> pd.DataFrame:
    result = df.copy()
    stage_index = (
        result["basename"]
        .map(latest_stage_by_basename)
        .fillna(UNTRACKED_STAGE_INDEX)
        .astype(int)
    )
    result["_stage_index"] = stage_index
    result["_stage_label"] = result["_stage_index"].map(stage_labels).fillna(UNTRACKED_STAGE_LABEL)
    result["_stage_color"] = result["_stage_index"].map(stage_colors).fillna(UNTRACKED_STAGE_COLOR)
    return result


def _stems_from_glob(directory: Path, pattern: str) -> set[str]:
    if not directory.exists():
        return set()
    return {file.stem for file in directory.glob(pattern) if file.is_file()}


def _age_seconds_to_log_recency(age_seconds: np.ndarray, scale_seconds: float) -> np.ndarray:
    age = np.maximum(np.asarray(age_seconds, dtype=float), 0.0)
    return -np.log10((age / float(scale_seconds)) + 1.0)


def _format_age_seconds_label(seconds: float) -> str:
    if seconds <= 1.0:
        return "now"
    if seconds < 3600:
        minutes = int(round(seconds / 60.0))
        return f"-{minutes}m"
    if seconds < 86400:
        hours = int(round(seconds / 3600.0))
        return f"-{hours}h"
    days = int(round(seconds / 86400.0))
    return f"-{days}d"


def prepare_execution_time_recency_view(
    frame: pd.DataFrame,
    param_list: Sequence[str],
    scale_seconds: float,
) -> Tuple[pd.DataFrame, List[str], Dict[str, str], Optional[str], pd.Timestamp]:
    result = frame.copy()
    now_utc = pd.Timestamp.now(tz="UTC")
    recency_col: Optional[str] = None
    plot_params: List[str] = []
    display_labels: Dict[str, str] = {}

    for param in param_list:
        if param == "execution_time":
            recency_col = "__execution_time_log_recency_now"
            execution_utc = pd.to_datetime(result["execution_time"], errors="coerce", utc=True)
            age_seconds = (now_utc - execution_utc).dt.total_seconds().to_numpy(dtype=float)
            result[recency_col] = _age_seconds_to_log_recency(age_seconds, scale_seconds)
            plot_params.append(recency_col)
            display_labels[recency_col] = "execution_time (log recency vs now UTC)"
        else:
            plot_params.append(param)
            display_labels[param] = param

    return result, plot_params, display_labels, recency_col, now_utc


def _plot_diagonal_hist(
    ax: plt.Axes,
    series: pd.Series,
    frame: pd.DataFrame,
    stage_order: Sequence[int],
    stage_colors: Dict[int, str],
) -> None:
    is_datetime = pd.api.types.is_datetime64_any_dtype(series)
    bins = 16
    for stage_index in stage_order:
        mask = frame["_stage_index"] == stage_index
        if not mask.any():
            continue
        values = series.loc[mask].dropna()
        if values.empty:
            continue
        if is_datetime:
            x = mdates.date2num(pd.to_datetime(values).to_numpy(dtype="datetime64[ns]"))
            hist_alpha = UNTRACKED_HIST_ALPHA if stage_index == UNTRACKED_STAGE_INDEX else 0.28
            ax.hist(
                x,
                bins=bins,
                color=stage_colors.get(stage_index, UNTRACKED_STAGE_COLOR),
                alpha=hist_alpha,
                edgecolor="black",
                linewidth=0.3,
            )
            ax.xaxis_date()
        else:
            hist_alpha = UNTRACKED_HIST_ALPHA if stage_index == UNTRACKED_STAGE_INDEX else 0.28
            ax.hist(
                values.to_numpy(),
                bins=bins,
                color=stage_colors.get(stage_index, UNTRACKED_STAGE_COLOR),
                alpha=hist_alpha,
                edgecolor="black",
                linewidth=0.3,
            )


def _apply_recency_ticks(
    ax: plt.Axes,
    axis: str,
    scale_seconds: float,
    label_visible: bool,
) -> None:
    candidate_ages = np.array(
        [
            0,
            60,
            5 * 60,
            15 * 60,
            30 * 60,
            60 * 60,
            2 * 3600,
            6 * 3600,
            12 * 3600,
            24 * 3600,
            2 * 86400,
            4 * 86400,
            7 * 86400,
            14 * 86400,
            30 * 86400,
        ],
        dtype=float,
    )
    tick_positions = _age_seconds_to_log_recency(candidate_ages, scale_seconds)
    lo, hi = (ax.get_xlim() if axis == "x" else ax.get_ylim())
    low, high = min(lo, hi), max(lo, hi)
    mask = (tick_positions >= low - 1e-9) & (tick_positions <= high + 1e-9)

    if not mask.any():
        return

    shown_positions = tick_positions[mask]
    shown_labels = [_format_age_seconds_label(value) for value in candidate_ages[mask]]
    order = np.argsort(shown_positions)
    shown_positions = shown_positions[order]
    shown_labels = [shown_labels[idx] for idx in order]

    if axis == "x":
        ax.set_xticks(shown_positions)
        if label_visible:
            ax.set_xticklabels(shown_labels, rotation=20, ha="right", fontsize=7)
        else:
            ax.tick_params(axis="x", labelbottom=False)
    else:
        ax.set_yticks(shown_positions)
        if label_visible:
            ax.set_yticklabels(shown_labels, fontsize=7)
        else:
            ax.tick_params(axis="y", labelleft=False)


def _scatter_stage_points(
    ax: plt.Axes,
    frame: pd.DataFrame,
    x_col: str,
    y_col: str,
    stage_order: Sequence[int],
    stage_colors: Dict[int, str],
    point_size: float,
    alpha: float,
) -> None:
    for stage_index in stage_order:
        mask = frame["_stage_index"] == stage_index
        if not mask.any():
            continue
        points = frame.loc[mask]
        if stage_index == 0:
            ax.scatter(
                points[x_col],
                points[y_col],
                s=point_size,
                facecolors="none",
                edgecolors="black",
                linewidths=0.45,
                alpha=0.95,
                zorder=3,
            )
            continue
        ax.scatter(
            points[x_col],
            points[y_col],
            s=point_size,
            facecolors=stage_colors.get(stage_index, UNTRACKED_STAGE_COLOR),
            edgecolors="black",
            linewidths=0.2,
            alpha=max(0.02, alpha * UNTRACKED_SCATTER_ALPHA_SCALE)
            if stage_index == UNTRACKED_STAGE_INDEX
            else alpha,
            zorder=3,
        )


def _datetime_locator_and_formatter(series: pd.Series) -> Tuple[mdates.DateLocator, mdates.DateFormatter]:
    valid = pd.to_datetime(series, errors="coerce").dropna()
    if valid.empty:
        return mdates.AutoDateLocator(maxticks=4), mdates.DateFormatter("%Y-%m-%d\n%H:%M")

    span = valid.max() - valid.min()
    span_days = max(float(span.total_seconds()) / 86400.0, 0.0)
    if span_days > 3650:  # >10 years
        return mdates.YearLocator(base=2), mdates.DateFormatter("%Y")
    if span_days > 730:  # >2 years
        return mdates.YearLocator(base=1), mdates.DateFormatter("%Y")
    if span_days > 120:  # >4 months
        return mdates.MonthLocator(interval=2), mdates.DateFormatter("%Y-%m")
    if span_days > 20:  # >3 weeks
        return mdates.DayLocator(interval=7), mdates.DateFormatter("%Y-%m-%d")
    return mdates.AutoDateLocator(maxticks=4), mdates.DateFormatter("%Y-%m-%d\n%H:%M")


def _format_datetime_axes(
    axes: np.ndarray,
    param_list: Sequence[str],
    datetime_indices: Sequence[int],
    datetime_styles: Dict[str, Tuple[mdates.DateLocator, mdates.DateFormatter]],
) -> None:
    if len(datetime_indices) == 0:
        return
    n = len(param_list)
    for i in range(n):
        for j in range(n):
            ax = axes[i, j] if n > 1 else axes
            if j in datetime_indices:
                locator, formatter = datetime_styles.get(
                    param_list[j],
                    (mdates.AutoDateLocator(maxticks=4), mdates.DateFormatter("%Y-%m-%d\n%H:%M")),
                )
                ax.xaxis.set_major_locator(locator)
                ax.xaxis.set_major_formatter(formatter)
                if i == n - 1:
                    ax.tick_params(axis="x", labelrotation=20, labelsize=7)
                elif ax.axison:
                    ax.tick_params(axis="x", labelbottom=False)
            if i in datetime_indices and i != j and ax.axison:
                locator, formatter = datetime_styles.get(
                    param_list[i],
                    (mdates.AutoDateLocator(maxticks=4), mdates.DateFormatter("%Y-%m-%d\n%H:%M")),
                )
                ax.yaxis.set_major_locator(locator)
                ax.yaxis.set_major_formatter(formatter)
                ax.tick_params(axis="y", labelsize=7)


def _add_stage_legend(
    fig: plt.Figure,
    frame: pd.DataFrame,
    stage_order: Sequence[int],
    stage_labels: Dict[int, str],
    stage_colors: Dict[int, str],
) -> None:
    counts = frame["_stage_index"].value_counts().to_dict()
    total = max(len(frame), 1)
    handles: List[Line2D] = []
    labels: List[str] = []
    for stage_index in stage_order:
        count = int(counts.get(stage_index, 0))
        fraction = (count / total) * 100.0
        label = stage_labels.get(stage_index, f"Stage {stage_index}")
        labels.append(f"{label}: {count} ({fraction:.1f}%)")
        if stage_index == 0:
            handle = Line2D(
                [0],
                [0],
                marker="o",
                linestyle="None",
                markerfacecolor="none",
                markeredgecolor="black",
                markeredgewidth=0.8,
                markersize=5.5,
            )
        else:
            handle = Line2D(
                [0],
                [0],
                marker="o",
                linestyle="None",
                markerfacecolor=stage_colors.get(stage_index, UNTRACKED_STAGE_COLOR),
                markeredgecolor="black",
                markeredgewidth=0.3,
                markersize=5.5,
            )
        handles.append(handle)
    fig.legend(
        handles,
        labels,
        loc="upper right",
        bbox_to_anchor=(0.995, 0.995),
        frameon=True,
        fontsize=7,
        title="Latest pipeline stage",
        title_fontsize=8,
    )


def _unique_geometry_vectors(frame: pd.DataFrame) -> List[Tuple[float, float, float, float]]:
    geometry_columns = ["z_p1", "z_p2", "z_p3", "z_p4"]
    if not set(geometry_columns).issubset(frame.columns):
        return []

    geom_frame = frame.loc[:, geometry_columns].apply(pd.to_numeric, errors="coerce")
    geom_frame = geom_frame.dropna(how="any").drop_duplicates().sort_values(geometry_columns)
    return [tuple(float(value) for value in row) for row in geom_frame.to_numpy()]


def _filter_frame_to_geometry(
    frame: pd.DataFrame,
    geometry: Tuple[float, float, float, float],
) -> pd.DataFrame:
    mask = pd.Series(True, index=frame.index)
    for column, value in zip(("z_p1", "z_p2", "z_p3", "z_p4"), geometry):
        mask &= np.isclose(pd.to_numeric(frame[column], errors="coerce"), float(value), atol=1e-9)
    return frame.loc[mask].copy()


def _format_geometry_label(geometry: Tuple[float, float, float, float]) -> str:
    return " / ".join(f"{float(value):g}" for value in geometry) + " mm"


def _format_rate_summary_from_timestamp_column(
    frame: pd.DataFrame,
    timestamp_col: str,
    label: str,
) -> Optional[str]:
    if timestamp_col not in frame.columns:
        return None

    execution_utc = pd.to_datetime(frame[timestamp_col], errors="coerce", utc=True).dropna().sort_values()
    if len(execution_utc) < 2:
        return None

    first_ts = execution_utc.iloc[0]
    last_ts = execution_utc.iloc[-1]
    span_seconds = float((last_ts - first_ts).total_seconds())
    if span_seconds <= 0.0:
        return None

    total_rate_h = float(len(execution_utc) / (span_seconds / 3600.0))

    recent_window = pd.Timedelta(hours=6)
    recent_start = max(first_ts, last_ts - recent_window)
    recent_mask = execution_utc >= recent_start
    recent_count = int(recent_mask.sum())
    recent_span_seconds = float((last_ts - recent_start).total_seconds())
    recent_rate_text = "n/a"
    if recent_count >= 2 and recent_span_seconds > 0.0:
        recent_rate_h = float(recent_count / (recent_span_seconds / 3600.0))
        recent_rate_text = f"{recent_rate_h:.2f} files/h (last 6h)"

    return (
        f"{label} rate ≈ {total_rate_h:.2f} files/h overall"
        f" | {recent_rate_text}"
    )


def plot_stage_colored_parameter_matrix(
    frame: pd.DataFrame,
    param_list: Sequence[str],
    stage_order: Sequence[int],
    stage_labels: Dict[int, str],
    stage_colors: Dict[int, str],
    display_labels: Dict[str, str],
    output_path: Path,
    point_size: float,
    alpha: float,
    execution_recency_col: Optional[str],
    execution_log_scale_seconds: float,
    pdf: Optional[PdfPages] = None,
    page_title_suffix: Optional[str] = None,
) -> None:
    n = len(param_list)
    if n == 0:
        raise ValueError("No plottable parameters were resolved.")

    datetime_indices = [
        idx
        for idx, col in enumerate(param_list)
        if pd.api.types.is_datetime64_any_dtype(frame[col])
    ]
    datetime_styles = {
        param_list[idx]: _datetime_locator_and_formatter(frame[param_list[idx]])
        for idx in datetime_indices
    }
    fig, axes = plt.subplots(
        n,
        n,
        figsize=(2.9 * n + 2.8, 2.9 * n + 2.8),
        dpi=120,
    )
    axes_arr = np.asarray(axes).reshape(n, n)

    axis_limits = {col: _compute_axis_limits(frame[col]) for col in param_list}
    for i in range(n):
        for j in range(n):
            ax = axes_arr[i, j]
            x_col = param_list[j]
            y_col = param_list[i]

            if axis_limits.get(x_col) is not None:
                ax.set_xlim(axis_limits[x_col])
            if i != j and axis_limits.get(y_col) is not None:
                ax.set_ylim(axis_limits[y_col])

            ax.grid(True, linestyle=":", linewidth=0.35, alpha=0.35)
            for spine in ax.spines.values():
                spine.set_visible(True)
                spine.set_linewidth(0.65)
                spine.set_color("black")
            ax.set_box_aspect(1.0)

            if i == j:
                _plot_diagonal_hist(ax, frame[y_col], frame, stage_order, stage_colors)
                ax.set_title(display_labels.get(y_col, y_col), fontsize=9, pad=4)
                ax.autoscale_view(scalex=False, scaley=True)
            elif i > j:
                _scatter_stage_points(
                    ax=ax,
                    frame=frame,
                    x_col=x_col,
                    y_col=y_col,
                    stage_order=stage_order,
                    stage_colors=stage_colors,
                    point_size=point_size,
                    alpha=alpha,
                )
            else:
                ax.axis("off")

            if i < n - 1:
                ax.tick_params(axis="x", labelbottom=False)
            else:
                ax.set_xlabel(display_labels.get(x_col, x_col), fontsize=9)
            if j > 0:
                ax.tick_params(axis="y", labelleft=False)
            else:
                ax.set_ylabel(display_labels.get(y_col, y_col), fontsize=9)
            ax.tick_params(axis="both", which="major", labelsize=8, width=0.8, length=2.8)

    _format_datetime_axes(axes_arr, param_list, datetime_indices, datetime_styles)

    if execution_recency_col is not None:
        for i in range(n):
            for j in range(n):
                ax = axes_arr[i, j]
                if not ax.axison:
                    continue
                if param_list[j] == execution_recency_col:
                    _apply_recency_ticks(
                        ax=ax,
                        axis="x",
                        scale_seconds=execution_log_scale_seconds,
                        label_visible=(i == n - 1),
                    )
                    ax.axvline(0.0, color="red", linestyle="--", alpha=0.25, linewidth=0.8, zorder=10)
                if i > j and param_list[i] == execution_recency_col:
                    _apply_recency_ticks(
                        ax=ax,
                        axis="y",
                        scale_seconds=execution_log_scale_seconds,
                        label_visible=(j == 0),
                    )
                    ax.axhline(0.0, color="red", linestyle="--", alpha=0.25, linewidth=0.8, zorder=10)

    tracked = int((frame["_stage_index"] != UNTRACKED_STAGE_INDEX).sum())
    total = len(frame)
    subtitle = (
        f"Simulated Data Evolution ({total} files) | Tracked in MASTER pipeline: "
        f"{tracked}/{total} ({(tracked / max(total, 1)) * 100.0:.1f}%)"
    )
    title_lines = ["Stage-Colored Simulation Parameter Matrix"]
    if page_title_suffix:
        title_lines.append(page_title_suffix)
    for timestamp_col, label in (
        ("__task_1_execution_dt", "Task 1 completion"),
        ("__task_5_execution_dt", "Task 5 completion"),
    ):
        rate_summary = _format_rate_summary_from_timestamp_column(frame, timestamp_col, label)
        if rate_summary:
            title_lines.append(rate_summary)
    if execution_recency_col is not None:
        title_lines.append(
            f"Execution-time axes use log recency vs now (scale={execution_log_scale_seconds:.0f}s)"
        )
    title_lines.append(subtitle)
    full_title = "\n".join(title_lines)
    title_line_count = full_title.count("\n") + 1
    reserved_top = 0.90 - 0.04 * max(title_line_count - 2, 0)
    top_margin = max(0.78, min(0.90, reserved_top))

    fig.suptitle(full_title, fontsize=11, y=0.99)
    _add_stage_legend(fig, frame, stage_order, stage_labels, stage_colors)
    fig.subplots_adjust(left=0.06, right=0.84, bottom=0.08, top=top_margin, wspace=0.05, hspace=0.05)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if pdf is None:
        with PdfPages(output_path) as pdf_handle:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="AutoDateLocator was unable to pick an appropriate interval.*",
                    category=UserWarning,
                )
                pdf_save_rasterized_page(pdf_handle, fig, dpi=170)
    else:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="AutoDateLocator was unable to pick an appropriate interval.*",
                category=UserWarning,
            )
            pdf_save_rasterized_page(pdf, fig, dpi=170)
    plt.close(fig)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a simulation parameter matrix (mesh-style) where points are "
            "colored by latest MASTER stage (MINGO00 simulation chain)."
        )
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=str(DEFAULT_CONFIG_PATH),
        help=f"JSON config path (default: {DEFAULT_CONFIG_PATH}).",
    )
    parser.add_argument(
        "--sim-params",
        type=str,
        default=None,
        help="Path to step_final simulation params CSV (overrides config/default).",
    )
    parser.add_argument(
        "--station",
        type=str,
        default=None,
        help="Station token used for stage lookup (overrides config/default).",
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
        "--params",
        nargs="+",
        default=None,
        help=(
            "Parameter columns/tokens to include in the matrix. Supports aliases like "
            "'eff_1..eff_4', 'efficiencies', 'z_positions', 'flux_cm_min'. "
            "Overrides config/default."
        ),
    )
    parser.add_argument(
        "--point-size",
        type=float,
        default=None,
        help="Scatter marker size for off-diagonal plots (overrides config/default).",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=None,
        help="Scatter alpha for filled stage markers (overrides config/default).",
    )
    parser.add_argument(
        "--execution-log-scale-seconds",
        type=float,
        default=None,
        help=(
            "Soft-log recency scale (seconds) used when plotting execution_time "
            "(overrides config/default)."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output PDF path (overrides config/default).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    configure_matplotlib_style()

    try:
        (
            sim_params_path,
            station_token,
            mingo00_stage0_source,
            params,
            point_size,
            alpha,
            execution_log_scale_seconds,
            output_path,
        ) = resolve_runtime_options(args)
    except ValueError as exc:
        print(f"[simulated_data_evolution_plotter] {exc}", file=sys.stderr)
        return 1

    if point_size <= 0:
        print("[simulated_data_evolution_plotter] --point-size must be > 0.", file=sys.stderr)
        return 1
    if not (0 < alpha <= 1):
        print("[simulated_data_evolution_plotter] --alpha must be in (0, 1].", file=sys.stderr)
        return 1
    if execution_log_scale_seconds <= 0:
        print(
            "[simulated_data_evolution_plotter] --execution-log-scale-seconds must be > 0.",
            file=sys.stderr,
        )
        return 1

    if not sim_params_path.exists():
        print(
            f"[simulated_data_evolution_plotter] Simulation params CSV not found: {sim_params_path}",
            file=sys.stderr,
        )
        return 1

    station = normalize_station_token(station_token)
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
                    "[simulated_data_evolution_plotter] "
                    f"MINGO00 live registry sync: added={added_count}, removed={removed_count}",
                    file=sys.stderr,
                )
        except Exception as exc:  # pragma: no cover - defensive
            print(
                "[simulated_data_evolution_plotter] "
                f"MINGO00 live registry sync failed: {exc}",
                file=sys.stderr,
            )

    stages = stage_specs_for_station(station, mingo00_stage0_source=mingo00_stage0_source)
    stage_sets = build_chained_stage_sets(stages)
    raw_stage_sets = build_raw_stage_sets(stages)
    latest_stage_by_basename = build_latest_stage_map(stages, stage_sets)

    stage_labels: Dict[int, str] = {UNTRACKED_STAGE_INDEX: UNTRACKED_STAGE_LABEL}
    stage_colors: Dict[int, str] = {UNTRACKED_STAGE_INDEX: UNTRACKED_STAGE_COLOR}
    for stage in stages:
        stage_labels[stage.index] = stage.label
        stage_colors[stage.index] = stage.color
    stage_order = [UNTRACKED_STAGE_INDEX] + [stage.index for stage in sorted(stages, key=lambda s: s.index)]

    try:
        sim_df = pd.read_csv(sim_params_path, low_memory=False)
    except Exception as exc:
        print(
            f"[simulated_data_evolution_plotter] Failed to read {sim_params_path}: {exc}",
            file=sys.stderr,
        )
        return 1

    if sim_df.empty:
        print("[simulated_data_evolution_plotter] Simulation params CSV is empty.", file=sys.stderr)
        return 1

    sim_df = normalize_sim_params(sim_df)
    sim_df = add_stage_columns(sim_df, latest_stage_by_basename, stage_labels, stage_colors)
    sim_df = add_stage_execution_columns(sim_df, stages)

    param_list = expand_params(params, sim_df)
    if not param_list:
        print(
            "[simulated_data_evolution_plotter] No valid numeric/datetime params after expansion.",
            file=sys.stderr,
        )
        return 1

    (
        sim_df,
        plot_param_list,
        display_labels,
        execution_recency_col,
        now_utc,
    ) = prepare_execution_time_recency_view(
        frame=sim_df,
        param_list=param_list,
        scale_seconds=float(execution_log_scale_seconds),
    )

    geometry_vectors = _unique_geometry_vectors(sim_df)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with PdfPages(output_path) as pdf:
            if len(geometry_vectors) > 1:
                plot_stage_colored_parameter_matrix(
                    frame=sim_df,
                    param_list=plot_param_list,
                    stage_order=stage_order,
                    stage_labels=stage_labels,
                    stage_colors=stage_colors,
                    display_labels=display_labels,
                    output_path=output_path,
                    point_size=float(point_size),
                    alpha=float(alpha),
                    execution_recency_col=execution_recency_col,
                    execution_log_scale_seconds=float(execution_log_scale_seconds),
                    pdf=pdf,
                    page_title_suffix=f"All geometries | unique geometries = {len(geometry_vectors)}",
                )
            for geometry in geometry_vectors or [()]:
                if geometry:
                    geometry_frame = _filter_frame_to_geometry(sim_df, geometry)
                    page_suffix = (
                        f"Geometry z = {_format_geometry_label(geometry)} | rows = {len(geometry_frame)}"
                    )
                else:
                    geometry_frame = sim_df
                    page_suffix = "All available rows"
                plot_stage_colored_parameter_matrix(
                    frame=geometry_frame,
                    param_list=plot_param_list,
                    stage_order=stage_order,
                    stage_labels=stage_labels,
                    stage_colors=stage_colors,
                    display_labels=display_labels,
                    output_path=output_path,
                    point_size=float(point_size),
                    alpha=float(alpha),
                    execution_recency_col=execution_recency_col,
                    execution_log_scale_seconds=float(execution_log_scale_seconds),
                    pdf=pdf,
                    page_title_suffix=page_suffix,
                )
    except Exception as exc:
        print(f"[simulated_data_evolution_plotter] Plot failed: {exc}", file=sys.stderr)
        return 1

    stage_counts = sim_df["_stage_index"].value_counts().to_dict()
    ordered_count_summary = ", ".join(
        f"{stage_labels[idx]}={int(stage_counts.get(idx, 0))}"
        for idx in stage_order
    )
    print(f"[simulated_data_evolution_plotter] Saved PDF to {output_path}")
    print(f"[simulated_data_evolution_plotter] Geometry pages: {max(len(geometry_vectors), 1)}")
    print(f"[simulated_data_evolution_plotter] Stage counts: {ordered_count_summary}")

    sim_basenames = set(sim_df["basename"].astype(str))
    live_stage0_set = set(stage_sets.get(0, set()))
    untracked = sim_basenames - live_stage0_set
    raw_task_union: set[str] = set()
    for stage in stages:
        if stage.index <= 0:
            continue
        raw_task_union.update(raw_stage_sets.get(stage.index, set()))

    dt_twin_files = REPO_ROOT / "PIPELINE" / "MINGO_DIGITAL_TWIN" / "SIMULATION_OUTPUTS" / "SIMULATED_DATA" / "FILES"
    station_root = STATIONS_ROOT / station
    stage0_to_1_dir = station_root / "STAGE_0_TO_1"
    task1_input_root = station_root / "STAGE_1" / "EVENT_DATA" / "STEP_1" / "TASK_1" / "INPUT_FILES"
    task1_completed = task1_input_root / "COMPLETED_DIRECTORY"
    task1_processing = task1_input_root / "PROCESSING_DIRECTORY"
    task1_unprocessed = task1_input_root / "UNPROCESSED_DIRECTORY"

    twin_file_names = _stems_from_glob(dt_twin_files, "mi*.dat")
    live_input_names = (
        _stems_from_glob(stage0_to_1_dir, "mi*.dat")
        | _stems_from_glob(task1_completed, "mi*.dat")
        | _stems_from_glob(task1_processing, "mi*.dat")
        | _stems_from_glob(task1_unprocessed, "mi*.dat")
    )

    untracked_in_raw_tasks = untracked.intersection(raw_task_union)
    untracked_in_live_inputs = untracked.intersection(live_input_names)
    untracked_in_twin_files = untracked.intersection(twin_file_names)
    known_untracked = untracked_in_raw_tasks | untracked_in_live_inputs | untracked_in_twin_files
    untracked_unknown = untracked - known_untracked

    print(
        "[simulated_data_evolution_plotter] Untracked audit "
        f"(station={station}, now_utc={now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}):"
    )
    print(
        "[simulated_data_evolution_plotter]  - total_untracked_live="
        f"{len(untracked)}"
    )
    print(
        "[simulated_data_evolution_plotter]  - seen_in_task_metadata_history="
        f"{len(untracked_in_raw_tasks)}"
    )
    print(
        "[simulated_data_evolution_plotter]  - currently_in_station_live_inputs="
        f"{len(untracked_in_live_inputs)}"
    )
    print(
        "[simulated_data_evolution_plotter]  - currently_waiting_in_twin_FILES="
        f"{len(untracked_in_twin_files)}"
    )
    print(
        "[simulated_data_evolution_plotter]  - not_found_in_key_live_or_history_sets="
        f"{len(untracked_unknown)}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
