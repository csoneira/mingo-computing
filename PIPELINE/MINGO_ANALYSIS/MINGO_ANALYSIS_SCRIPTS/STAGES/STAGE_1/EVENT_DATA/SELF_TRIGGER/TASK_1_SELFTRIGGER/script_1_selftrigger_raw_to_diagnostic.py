#!/usr/bin/env python3
"""Stage-1 self-trigger Task 1: preserve Task-0 data and make QA plots.

The input is a Task-0 ``selftrigger_raw_*.parquet``. This starter task does not
apply coincidence cleaning or otherwise alter event data. It writes a
``selftrigger_cleaned_*.parquet`` for a future parallel self-trigger chain.

Usage mirrors the regular Task-1 script::

    python script_1_selftrigger_raw_to_diagnostic.py STATION [INPUT_FILE]
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import os
from pathlib import Path
import random
import re
import shutil
import sys
import time
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

CURRENT_PATH = Path(__file__).resolve()
REPO_ROOT = next(
    (
        parent
        for parent in CURRENT_PATH.parents
        if (parent / "CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh").is_file()
    ),
    CURRENT_PATH.parents[-1],
)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.debug_plots import (
    plot_debug_histogram_binning_comparison,
    plot_debug_histograms,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.file_selection import select_latest_candidate
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.plot_utils import runtime_plot_directory_name
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.step1_shared import (
    add_topology_task1_channel,
    add_topology_task1_channel_qt,
    add_topology_task1_column,
    add_normalized_count_metadata,
    apply_step1_master_overrides,
    build_events_per_second_metadata,
    prune_redundant_count_metadata,
    save_metadata,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.status_csv import initialize_status_row, update_status_progress


TASK_NAME = "TASK_1_SELFTRIGGER"
INPUT_PREFIX = "selftrigger_raw_"
OUTPUT_PREFIX = "selftrigger_cleaned_"
CHANNEL_COLUMN = re.compile(r"p[1-4]_s[1-4]_e[fb]_[qt]$", re.IGNORECASE)
PLOT_ALIASES = (
    "column_histograms",
    "histogram_binning_comparison",
    "channel_qt_scatter",
    "channel_qt_scatter_physical",
)


def _load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return value


def _load_plot_selection(path: Path) -> set[str]:
    config = _load_yaml(path)
    plots, non_plots = config.get("plots"), config.get("non_plots")
    if not isinstance(plots, list) or not isinstance(non_plots, list):
        raise ValueError(f"{path} must define 'plots' and 'non_plots' lists")
    enabled, disabled = [str(item) for item in plots], [str(item) for item in non_plots]
    if len(enabled) != len(set(enabled)) or len(disabled) != len(set(disabled)):
        raise ValueError(f"Duplicate plot alias in {path}")
    if set(enabled) & set(disabled) or set(enabled) | set(disabled) != set(PLOT_ALIASES):
        raise ValueError(
            f"Plot lists must partition the known aliases {PLOT_ALIASES}; "
            f"enabled={enabled}, disabled={disabled}"
        )
    return set(enabled)


def _load_debug_value_limits(path: Path) -> dict[str, tuple[float, float]]:
    config = _load_yaml(path)
    configured_limits = config.get("value_limits")
    expected_ranges = {"sanity", "physical"}
    if not isinstance(configured_limits, dict) or set(configured_limits) != expected_ranges:
        raise ValueError(f"{path} must define sanity and physical value_limits")
    parsed: dict[str, dict[str, tuple[float, float]]] = {}
    for range_name, limits in configured_limits.items():
        if not isinstance(limits, dict) or set(limits) != {"charge", "time"}:
            raise ValueError(f"{path}: value_limits.{range_name} must define charge and time")
        parsed[range_name] = {}
        for key, pair in limits.items():
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError(
                    f"{path}: value_limits.{range_name}.{key} must be [minimum, maximum]"
                )
            low, high = (float(value) for value in pair)
            if not np.isfinite(low) or not np.isfinite(high) or low >= high:
                raise ValueError(
                    f"{path}: value_limits.{range_name}.{key} must contain finite increasing limits"
                )
            parsed[range_name][key] = (low, high)
    return parsed


def _task_directories(station: int, repo_root: Path) -> dict[str, Path]:
    station_root = (
        repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / f"MINGO{station:02d}"
        / "STAGE_1" / "EVENT_DATA" / "STEP_1"
    )
    task_root = station_root / TASK_NAME
    task0_output = station_root / "TASK_0" / "OUTPUT_FILES"
    input_root = task_root / "INPUT_FILES"
    return {
        "task_root": task_root,
        "task0_output": task0_output,
        "unprocessed": input_root / "UNPROCESSED_DIRECTORY",
        "processing": input_root / "PROCESSING_DIRECTORY",
        "completed": input_root / "COMPLETED_DIRECTORY",
        "error": input_root / "ERROR_DIRECTORY",
        "output": task_root / "OUTPUT_FILES",
        "metadata": task_root / "METADATA",
        "plots": task_root / "PLOTS" / "DEBUG_PLOTS",
    }


def _move(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite staged file: {destination}")
    shutil.move(str(source), str(destination))


def _stage_inputs(
    directories: dict[str, Path],
    explicit_input: str | None,
    *,
    complete_reanalysis: bool,
    station: int,
    selection_mode: str,
) -> None:
    for key in ("unprocessed", "processing", "completed", "error", "output", "metadata", "plots"):
        directories[key].mkdir(parents=True, exist_ok=True)

    if explicit_input:
        source = Path(explicit_input).expanduser().resolve()
        if not source.is_file() or not source.name.startswith(INPUT_PREFIX) or source.suffix.lower() != ".parquet":
            raise ValueError(f"Input must be an existing {INPUT_PREFIX}*.parquet: {source}")
        allowed_roots = (directories["task0_output"].resolve(), directories["unprocessed"].resolve())
        if not any(source == root or root in source.parents for root in allowed_roots):
            raise ValueError(f"Input must come from Task 0 OUTPUT_FILES or this task's UNPROCESSED_DIRECTORY: {source}")
        if source.parent == directories["task0_output"].resolve():
            target = directories["unprocessed"] / source.name
            if not target.exists():
                _move(source, target)
        return

    known = {
        path.name
        for folder in (directories["unprocessed"], directories["processing"], directories["completed"])
        for path in folder.glob(f"{INPUT_PREFIX}*.parquet")
    }
    task0_metadata = directories["task0_output"].parent / "METADATA" / "task_0_metadata_execution.csv"
    confirmed_outputs: set[str] = set()
    if task0_metadata.is_file():
        with task0_metadata.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                recorded_path = str(row.get("selftrigger_raw_output_path", "") or "").strip()
                if recorded_path:
                    confirmed_outputs.add(Path(recorded_path).name)
    for source in directories["task0_output"].glob(f"{INPUT_PREFIX}*.parquet"):
        # Task 0 writes the parquet before appending its metadata row. Requiring
        # that row prevents racing a still-in-progress write in another guide.
        if source.name not in confirmed_outputs:
            continue
        output_name = OUTPUT_PREFIX + source.name[len(INPUT_PREFIX):]
        output_exists = (directories["output"] / output_name).exists()
        if source.name not in known and (complete_reanalysis or not output_exists):
            _move(source, directories["unprocessed"] / source.name)

    # Match regular STEP_1 behavior: when no new or interrupted input is
    # waiting, complete_reanalysis cycles the newest completed input back
    # through processing. Its existing output may then be replaced.
    unprocessed = list(directories["unprocessed"].glob(f"{INPUT_PREFIX}*.parquet"))
    processing = list(directories["processing"].glob(f"{INPUT_PREFIX}*.parquet"))
    if complete_reanalysis and not unprocessed and not processing:
        completed = list(directories["completed"].glob(f"{INPUT_PREFIX}*.parquet"))
        if completed:
            selected = (
                random.choice(completed)
                if selection_mode == "random"
                else Path(select_latest_candidate([path.name for path in completed], station) or completed[0].name)
            )
            if not selected.is_absolute():
                selected = directories["completed"] / selected
            _move(selected, directories["unprocessed"] / selected.name)


def _plot_channel_qt_scatter(
    frame: pd.DataFrame,
    path: Path,
    title: str,
    *,
    charge_limits: tuple[float, float],
    time_limits: tuple[float, float],
) -> bool:
    fig, axes = plt.subplots(4, 4, figsize=(16, 14), sharex=False, sharey=False)
    plotted = False
    for plane in range(1, 5):
        for strip in range(1, 5):
            ax = axes[plane - 1, strip - 1]
            clipped_label_added = False
            for side, color in (("f", "tab:blue"), ("b", "tab:orange")):
                q_col = f"p{plane}_s{strip}_e{side}_q"
                t_col = f"p{plane}_s{strip}_e{side}_t"
                if q_col not in frame or t_col not in frame:
                    continue
                q = pd.to_numeric(frame[q_col], errors="coerce").to_numpy(dtype=float)
                t = pd.to_numeric(frame[t_col], errors="coerce").to_numpy(dtype=float)
                valid = np.isfinite(q) & np.isfinite(t)
                inside_limits = (
                    valid
                    & (q >= charge_limits[0])
                    & (q <= charge_limits[1])
                    & (t >= time_limits[0])
                    & (t <= time_limits[1])
                )
                clipped = valid & ~inside_limits
                if inside_limits.any():
                    ax.scatter(
                        q[inside_limits],
                        t[inside_limits],
                        s=2,
                        alpha=0.2,
                        color=color,
                        label=f"{side.upper()} within limits",
                    )
                    plotted = True
                if clipped.any():
                    ax.scatter(
                        np.clip(q[clipped], *charge_limits),
                        np.clip(t[clipped], *time_limits),
                        s=5,
                        alpha=0.8,
                        color="red",
                        label="Clipped" if not clipped_label_added else "_nolegend_",
                        zorder=3,
                    )
                    clipped_label_added = True
                    plotted = True
            ax.set_title(f"P{plane} S{strip}")
            ax.set_xlabel("Charge")
            ax.set_ylabel("Time")
            ax.set_xlim(*charge_limits)
            ax.set_ylim(*time_limits)
            if ax.collections:
                ax.legend(fontsize=7, loc="best")
            ax.grid(alpha=0.2)
    fig.suptitle(title)
    fig.tight_layout()
    if plotted:
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return plotted


def _data_time_metadata(frame: pd.DataFrame) -> dict[str, object]:
    if "datetime" not in frame.columns:
        return {
            "data_first_datetime": "",
            "data_last_datetime": "",
            "data_duration_seconds": 0,
        }
    timestamps = pd.to_datetime(frame["datetime"], errors="coerce").dropna()
    if timestamps.empty:
        return {
            "data_first_datetime": "",
            "data_last_datetime": "",
            "data_duration_seconds": 0,
        }
    first, last = timestamps.min(), timestamps.max()
    return {
        "data_first_datetime": first.isoformat(),
        "data_last_datetime": last.isoformat(),
        "data_duration_seconds": max(0, int((last - first).total_seconds())),
    }


def _trigger_type_metadata(
    frame: pd.DataFrame,
    *,
    filename_base: str,
    execution_timestamp: str,
    param_hash: str,
    denominator_seconds: int,
) -> dict[str, object]:
    row: dict[str, object] = {
        "filename_base": filename_base,
        "execution_timestamp": execution_timestamp,
        "param_hash": param_hash,
        "count_rate_denominator_seconds": denominator_seconds,
    }
    for column in ("tt_task0_acq", "tt_task0_raw"):
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if values.empty:
            continue
        rounded = values.round()
        values = values.loc[np.isclose(values.to_numpy(dtype=float), rounded.to_numpy(dtype=float))]
        counts = rounded.loc[values.index].astype(int).value_counts().sort_index()
        for trigger_type, count in counts.items():
            count = int(count)
            row[f"{column}_{int(trigger_type)}_count"] = count
            row[f"{column}_{int(trigger_type)}_rate_hz"] = (
                round(count / denominator_seconds, 6) if denominator_seconds > 0 else 0.0
            )
    return row


def process_one(station: int, explicit_input: str | None = None) -> int:
    repo_root = get_repo_root()
    config_root = repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS" / "SUPPORT" / "CONFIG_FILES" / "STAGE_1" / "EVENT_DATA" / "STEP_1" / TASK_NAME
    config = _load_yaml(config_root / "config_task_1_selftrigger.yaml")
    config = apply_step1_master_overrides(config)
    enabled_plots = _load_plot_selection(config_root / "config_plots_task_1_selftrigger.yaml")
    debug_value_limits = _load_debug_value_limits(
        config_root / "config_debug_plot_limits_task_1_selftrigger.yaml"
    )
    selected_stations = config.get("selection", {}).get("stations", [0, 1, 2, 3, 4])
    if station not in {int(item) for item in selected_stations}:
        print(f"Station {station} is disabled by config_task_1_selftrigger.yaml")
        return 0

    directories = _task_directories(station, repo_root)
    complete_reanalysis = bool(config.get("complete_reanalysis", False))
    selection_mode = str(config.get("file_selection_mode", "new")).strip().lower()
    if selection_mode not in {"qa", "new", "random"}:
        raise ValueError(f"Unsupported STEP_1 file_selection_mode: {selection_mode!r}")
    print(
        "Self-trigger Task 1 effective settings: "
        f"complete_reanalysis={complete_reanalysis}, file_selection_mode={selection_mode}, "
        f"create_plots={bool(config.get('create_plots', True))}"
    )
    _stage_inputs(
        directories,
        explicit_input,
        complete_reanalysis=complete_reanalysis,
        station=station,
        selection_mode=selection_mode,
    )
    candidates = list(directories["unprocessed"].glob(f"{INPUT_PREFIX}*.parquet"))
    if not candidates:
        print(f"No {INPUT_PREFIX}*.parquet inputs are ready for MINGO{station:02d}.")
        return 0

    input_path = (
        random.choice(candidates)
        if selection_mode == "random"
        else Path(select_latest_candidate([path.name for path in candidates], station) or candidates[0].name)
    )
    if not input_path.is_absolute():
        input_path = directories["unprocessed"] / input_path
    processing_path = directories["processing"] / input_path.name
    _move(input_path, processing_path)
    basename = processing_path.name[len(INPUT_PREFIX):-len(processing_path.suffix)]
    output_path = directories["output"] / f"{OUTPUT_PREFIX}{basename}.parquet"
    if output_path.exists() and not bool(config.get("force_replacement", False)) and not complete_reanalysis:
        _move(processing_path, directories["completed"] / processing_path.name)
        print(f"Output already exists; archived duplicate input without replacement: {output_path}")
        return 0

    execution_time = datetime.now()
    execution_id = execution_time.strftime("%Y-%m-%d_%H.%M.%S")
    status_path = directories["metadata"] / "task_1_metadata_status.csv"
    status_filename = f"selftrigger_{basename}"
    initialize_status_row(status_path, status_filename, execution_id, completion_fraction=0.05)
    process_start = time.perf_counter()
    read_start = time.perf_counter()
    try:
        working_df = pd.read_parquet(processing_path, engine="pyarrow")
        read_seconds = time.perf_counter() - read_start
        if working_df.empty:
            raise ValueError("Input parquet contains no self-trigger rows")
        working_df = add_topology_task1_channel(working_df)
        working_df = add_topology_task1_column(working_df)
        working_df = add_topology_task1_channel_qt(working_df)
        # Preserve the event data while ensuring this self-trigger branch carries
        # the same Task-1 topology fields as the coincidence branch.
        update_status_progress(status_path, status_filename, execution_id, 0.25)

        plot_directory = directories["plots"] / runtime_plot_directory_name(basename, execution_id)
        saved_plots: list[str] = []
        next_debug_plot_index = 1
        plot_start = time.perf_counter()
        comparison_columns = (
            "p1_s1_ef_q",
            "p1_s1_eb_q",
            "p1_s1_ef_t",
            "p1_s1_eb_t",
        )
        comparison_clip_ranges = {
            column: debug_value_limits["sanity"]["charge" if column.endswith("_q") else "time"]
            for column in comparison_columns
        }
        if bool(config.get("create_plots", True)) and "column_histograms" in enabled_plots:
            selected_columns = [
                str(column) for column in working_df.columns
                if CHANNEL_COLUMN.fullmatch(str(column))
            ]
            selected_columns.extend(
                column for column in (
                    "tt_task0_acq",
                    "tt_task0_raw",
                    "topology_task1_channel",
                )
                if column in working_df.columns
            )
            selected_columns.extend(
                str(column) for column in working_df.select_dtypes(include=["datetime", "datetimetz"]).columns
                if str(column) not in selected_columns
            )
            if selected_columns:
                histogram_clip_ranges = {
                    column: debug_value_limits["sanity"]["charge" if column.lower().endswith("_q") else "time"]
                    for column in selected_columns
                    if CHANNEL_COLUMN.fullmatch(column)
                }
                next_debug_plot_index = plot_debug_histograms(
                    working_df,
                    selected_columns,
                    thresholds=None,
                    title=f"{TASK_NAME} self-trigger column distributions: {processing_path.name}",
                    out_dir=str(plot_directory),
                    fig_idx=next_debug_plot_index,
                    max_cols_per_fig=12,
                    y_scale="log",
                    clip_ranges=histogram_clip_ranges,
                    annotate_omissions=True,
                )
                saved_plots.extend(str(path) for path in sorted(plot_directory.glob("*.png")))
        if bool(config.get("create_plots", True)) and "histogram_binning_comparison" in enabled_plots:
            comparison_path = plot_directory / (
                f"{next_debug_plot_index}_debug_histogram_binning_comparison_{processing_path.stem}.png"
            )
            if plot_debug_histogram_binning_comparison(
                working_df,
                comparison_columns,
                comparison_clip_ranges,
                title=(
                    f"{TASK_NAME} fixed-width vs adaptive quantile binning: "
                    f"P1 S1 front/back charge and time ({processing_path.name})"
                ),
                out_path=str(comparison_path),
                fixed_bins=80,
            ):
                saved_plots.append(str(comparison_path))
                next_debug_plot_index += 1
        scatter_specs = (
            ("channel_qt_scatter", "sanity", "sanity-range"),
            ("channel_qt_scatter_physical", "physical", "physical-range"),
        )
        for alias, limit_key, range_label in scatter_specs:
            if not bool(config.get("create_plots", True)) or alias not in enabled_plots:
                continue
            scatter_path = plot_directory / f"{next_debug_plot_index}_{alias}_{processing_path.stem}.png"
            if _plot_channel_qt_scatter(
                working_df,
                scatter_path,
                f"Self-trigger Task 1 Q-T by plane/strip ({range_label}): {processing_path.name}",
                charge_limits=debug_value_limits[limit_key]["charge"],
                time_limits=debug_value_limits[limit_key]["time"],
            ):
                saved_plots.append(str(scatter_path))
                next_debug_plot_index += 1
        plot_seconds = time.perf_counter() - plot_start

        update_status_progress(status_path, status_filename, execution_id, 0.60)
        temp_output = output_path.with_suffix(".parquet.tmp")
        write_start = time.perf_counter()
        working_df.to_parquet(temp_output, engine="pyarrow", compression="zstd", index=False)
        os.replace(temp_output, output_path)
        parquet_write_seconds = time.perf_counter() - write_start

        completed_path = directories["completed"] / processing_path.name
        _move(processing_path, completed_path)
        elapsed_seconds = time.perf_counter() - process_start
        elapsed_minutes = elapsed_seconds / 60.0
        time_metadata = _data_time_metadata(working_df)
        rate_metadata = build_events_per_second_metadata(working_df)
        denominator_seconds = int(rate_metadata.get("events_per_second_total_seconds", 0) or 0)
        param_hash_value = working_df["param_hash"].iloc[0] if "param_hash" in working_df.columns and len(working_df) else ""
        param_hash = "" if pd.isna(param_hash_value) else str(param_hash_value)
        add_normalized_count_metadata(rate_metadata, denominator_seconds, log_fn=lambda *_: None)
        prune_redundant_count_metadata(rate_metadata, log_fn=lambda *_: None)
        common_metadata = {
            "filename_base": basename,
            "execution_timestamp": execution_id,
            "param_hash": param_hash,
            "station": station,
        }

        save_metadata(
            directories["metadata"] / "task_1_metadata_execution.csv",
            {
                **common_metadata,
                "input_filename": completed_path.name,
                "input_rows": int(len(working_df)),
                "input_columns": int(len(working_df.columns)),
                "output_path": str(output_path),
                "output_rows": int(len(working_df)),
                "output_columns": int(len(working_df.columns)),
                "plot_count": len(saved_plots),
                "execution_time_minutes": round(elapsed_minutes, 4),
                "processing_mode": "selftrigger_passthrough",
                **time_metadata,
            },
            replace_existing_basename=False,
        )
        specific_metadata = {
            **common_metadata,
            "event_rows": int(len(working_df)),
            "column_count": int(len(working_df.columns)),
            "numeric_column_count": int(len(working_df.select_dtypes(include=[np.number]).columns)),
            "plot_count": len(saved_plots),
            "event_rate_hz": rate_metadata.get("events_per_second_global_rate", 0),
            **time_metadata,
        }
        for column in ("tt_task0_acq", "tt_task0_raw"):
            if column in working_df.columns:
                specific_metadata[f"{column}_distinct_values"] = int(working_df[column].nunique(dropna=True))
        save_metadata(
            directories["metadata"] / "task_1_metadata_specific.csv",
            specific_metadata,
            replace_existing_basename=False,
        )
        save_metadata(
            directories["metadata"] / "task_1_metadata_rate_histogram.csv",
            {**common_metadata, **rate_metadata},
            replace_existing_basename=False,
        )
        save_metadata(
            directories["metadata"] / "task_1_metadata_trigger_type.csv",
            _trigger_type_metadata(
                working_df,
                filename_base=basename,
                execution_timestamp=execution_id,
                param_hash=param_hash,
                denominator_seconds=denominator_seconds,
            ),
            replace_existing_basename=False,
        )
        metadata_seconds = time.perf_counter() - process_start - read_seconds - plot_seconds - parquet_write_seconds
        save_metadata(
            directories["metadata"] / "task_1_metadata_profiling.csv",
            {
                **common_metadata,
                "data_read_seconds": round(read_seconds, 4),
                "plot_generation_seconds": round(plot_seconds, 4),
                "parquet_write_seconds": round(parquet_write_seconds, 4),
                "metadata_write_seconds_before_profiling": round(max(0.0, metadata_seconds), 4),
                "total_execution_seconds": round(elapsed_seconds, 4),
            },
            replace_existing_basename=False,
        )
        update_status_progress(status_path, status_filename, execution_id, 1.0)
        print(f"Self-trigger Task 1 complete: {output_path} ({len(working_df)} rows, unchanged)")
        print(f"Input archived: {completed_path}")
        print(f"Runtime PNGs: {plot_directory if saved_plots else 'none generated'}")
        return 0
    except Exception:
        update_status_progress(status_path, status_filename, execution_id, -1.0)
        if processing_path.exists():
            error_path = directories["error"] / processing_path.name
            if not error_path.exists():
                _move(processing_path, error_path)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Pass through Task-0 self-trigger parquet and create diagnostic PNGs.")
    parser.add_argument("station", type=int, choices=range(5), help="Station number 0-4")
    parser.add_argument("input_file", nargs="?", help="Optional Task-0 selftrigger_raw parquet path")
    parser.add_argument("--input-file", dest="input_file_flag", help="Optional Task-0 selftrigger_raw parquet path")
    args = parser.parse_args()
    if args.input_file and args.input_file_flag:
        parser.error("Use either positional input_file or --input-file, not both")
    process_one(args.station, args.input_file_flag or args.input_file)


if __name__ == "__main__":
    main()
