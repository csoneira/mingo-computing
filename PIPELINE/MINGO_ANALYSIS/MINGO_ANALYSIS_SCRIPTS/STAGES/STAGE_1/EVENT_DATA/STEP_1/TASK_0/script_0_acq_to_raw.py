#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 1 Task 0 (ACQ->RAW) driver.

Ingests one acquisition text file from STAGE_0_TO_1, preserves the existing
Task 1 raw-line parsing/rejection behavior, splits by trigger type, and writes
raw parquet files for Task 1.
"""

from __future__ import annotations

import builtins
from datetime import datetime
import os
from pathlib import Path
import random
import shutil
import sys
import time

import pandas as pd

CURRENT_PATH = Path(__file__).resolve()
REPO_ROOT = None
for parent in CURRENT_PATH.parents:
    if parent.name == "MINGO_ANALYSIS_SCRIPTS":
        REPO_ROOT = parent.parent.parent
        break
if REPO_ROOT is None:
    REPO_ROOT = CURRENT_PATH.parents[-1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.execution_logger import set_station, start_timer
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.debug_plots import plot_debug_histograms
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.file_selection import (
    file_name_in_any_date_range,
    load_date_ranges_from_config,
    newest_order_key,
    select_latest_candidate,
    sync_unprocessed_with_date_range,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.input_file_config import select_input_file_configuration
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.path_config import get_repo_root, resolve_home_path_from_config
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.reprocessing_utils import (
    filter_filenames_by_qa_retry_basenames,
    load_active_qa_retry_basenames,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.selection_config import load_selection_for_paths, station_is_selected
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.simulated_data_utils import resolve_simulated_z_positions
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.status_csv import (
    initialize_status_row,
    rename_status_row,
    update_status_progress,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.step1_shared import (
    add_topology_task1_channel,
    build_step1_cli_parser,
    build_step1_filtered_print,
    build_step1_raw_input_dataframe,
    canonicalize_step1_columns,
    load_step1_task_plot_catalog,
    load_step1_task_config_bundle,
    resolve_step1_effective_task_config,
    resolve_step1_plot_options,
    save_metadata,
    step1_task_plot_enabled,
    validate_step1_input_file_args,
)
from analysis_functions import (
    compute_tt_task0_acq,
    datetime_bounds,
    duration_seconds,
    rate_hz,
    raw_channel_rename_map,
    station_matches_file,
)
from plotting_functions import (
    plot_acquisition_rate_vs_time_by_task_tt_with_histograms,
    plot_acquisition_rate_vs_time_by_trigger_type,
)


task_number = 0
STATION_CHOICES = ("0", "1", "2", "3", "4")
TASK0_PLOT_ALIASES: tuple[str, ...] = (
    "debug_suite",
    "acquisition_rate_vs_time_by_trigger_type",
    "acquisition_rate_vs_time_by_task_tt_with_histograms",
)
task0_plot_status_by_alias: dict[str, str] = {}
TASK0_GATE_TEST_CHARGE_COLUMNS: tuple[str, ...] = tuple(
    f"p{plane}_s{strip}_{end}_q"
    for plane in range(1, 5)
    for strip in range(1, 5)
    for end in ("ef", "eb")
)
TASK0_GATE_TEST_QUANTILES: tuple[float, ...] = tuple(index / 10 for index in range(10))


def safe_move(source_path: str | Path, dest_path: str | Path) -> str:
    return shutil.move(str(source_path), str(dest_path))


def _select_candidate(file_names: list[str], station: str) -> str | None:
    if not file_names:
        return None
    mode = str(config.get("file_selection_mode", "new")).strip().lower()
    if mode == "qa":
        active_qa_basenames = load_active_qa_retry_basenames(station, repo_root=REPO_ROOT)
        qa_file_names = filter_filenames_by_qa_retry_basenames(file_names, active_qa_basenames)
        if qa_file_names:
            file_names = qa_file_names
    if mode == "random":
        return random.choice(file_names)
    order = os.environ.get("DATAFLOW_STEP1_SELECTION_ORDER", "latest").strip().lower()
    if order == "oldest":
        return min(file_names, key=lambda name: newest_order_key(name, station))
    return select_latest_candidate(file_names, station)


def task0_plot_enabled(alias: str) -> bool:
    if not task0_plot_status_by_alias:
        return True
    return step1_task_plot_enabled(alias, task0_plot_status_by_alias, plot_mode)


def build_task0_gate_test_metadata(
    frame: pd.DataFrame,
    *,
    filename_base: str,
    execution_timestamp: str,
    param_hash: str,
    denominator_seconds: int,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "filename_base": filename_base,
        "execution_timestamp": execution_timestamp,
        "param_hash": param_hash,
        "count_rate_denominator_seconds": int(denominator_seconds),
        "gate_test_source_tt_task0_acq": 1234,
        "gate_test_charge_column_count": len(TASK0_GATE_TEST_CHARGE_COLUMNS),
        "gate_test_quantile_count": len(TASK0_GATE_TEST_QUANTILES),
        "gate_test_comparison": "zero_ignored_else_finite_and_greater_than_or_equal_to_nonzero_quantile",
    }
    missing_columns = [
        column for column in TASK0_GATE_TEST_CHARGE_COLUMNS if column not in frame.columns
    ]
    metadata["gate_test_missing_charge_column_count"] = len(missing_columns)
    metadata["gate_test_missing_charge_columns"] = ",".join(missing_columns)

    tt_values = pd.to_numeric(
        frame["tt_task0_acq"] if "tt_task0_acq" in frame.columns else pd.Series(0, index=frame.index),
        errors="coerce",
    )
    if missing_columns:
        source_view = pd.DataFrame()
    else:
        source_view = frame.loc[
            tt_values.eq(1234),
            list(TASK0_GATE_TEST_CHARGE_COLUMNS),
        ].apply(pd.to_numeric, errors="coerce")
    source_tt_1234_count = int(tt_values.eq(1234).sum())
    metadata["gate_test_tt_task0_acq_1234_count"] = source_tt_1234_count
    metadata["gate_test_tt_task0_acq_1234_rate_hz"] = rate_hz(
        source_tt_1234_count,
        denominator_seconds,
    )

    for quantile_index, quantile_fraction in enumerate(TASK0_GATE_TEST_QUANTILES):
        gate_label = f"q{quantile_index:02d}"
        if source_view.empty:
            count = 0
        else:
            nonzero_source_view = source_view.mask(source_view.eq(0))
            thresholds = nonzero_source_view.quantile(quantile_fraction)
            charge_passes = source_view.eq(0) | (
                source_view.notna() & source_view.ge(thresholds, axis="columns")
            )
            # A column containing no nonzero charge has no meaningful threshold,
            # so every zero entry in that column remains ignored.
            gate_mask = charge_passes.all(axis=1)
            count = int(gate_mask.sum())
        metadata[f"gate_test_{gate_label}_quantile"] = quantile_fraction
        metadata[f"gate_test_{gate_label}_count"] = count
        metadata[f"gate_test_{gate_label}_rate_hz"] = rate_hz(count, denominator_seconds)

    return metadata






def _resolve_station_conf_value(
    *,
    config_root: Path,
    station: str,
    start_time: object,
    end_time: object,
) -> float | None:
    input_file_config_path = (
        config_root
        / "STAGE_0"
        / "ONLINE_RUN_DICTIONARY"
        / f"STATION_{station}"
        / f"input_file_mingo0{station}.csv"
    )
    if not input_file_config_path.exists():
        print(f"Task 0 input configuration file does not exist: {input_file_config_path}", force=True)
        return None
    try:
        input_file = pd.read_csv(input_file_config_path, skiprows=1)
    except pd.errors.EmptyDataError:
        print(f"Task 0 input configuration file is empty: {input_file_config_path}", force=True)
        return None
    if input_file.empty:
        print(f"Task 0 input configuration file has no rows: {input_file_config_path}", force=True)
        return None

    selection_result = select_input_file_configuration(
        input_file,
        start_time=start_time,
        end_time=end_time,
    )
    selected_conf = selection_result.selected_conf
    if selected_conf is None:
        print("Task 0 found no selectable input configuration row for channel ordering.", force=True)
        return None
    try:
        return float(selected_conf.get("conf"))
    except (TypeError, ValueError):
        return None


def _apply_task0_raw_channel_ordering(
    frame: pd.DataFrame,
    *,
    station: str,
    conf_value: float | None,
) -> bool:
    if station != "2" or conf_value is None or conf_value >= 2:
        return False
    print("Task 0 applying station 2 configuration<2 Plane 4 channel swap.", force=True)
    swapped = False
    for quantity in ("t", "q"):
        for end in ("ef", "eb"):
            col3 = f"p4_s3_{end}_{quantity}"
            col4 = f"p4_s4_{end}_{quantity}"
            if col3 not in frame.columns or col4 not in frame.columns:
                print(f"Warning: Task 0 cannot swap missing Plane 4 columns: {col3}, {col4}", force=True)
                continue
            frame.loc[:, [col3, col4]] = frame.loc[:, [col4, col3]].to_numpy()
            swapped = True
    return swapped


CLI_PARSER = build_step1_cli_parser("Run Stage 1 STEP_1 TASK_0 (ACQ->RAW).", STATION_CHOICES)
CLI_ARGS = CLI_PARSER.parse_args()
validate_step1_input_file_args(CLI_PARSER, CLI_ARGS)

VERBOSE = bool(os.environ.get("DATAFLOW_VERBOSE")) or CLI_ARGS.verbose
print = build_step1_filtered_print(
    verbose=VERBOSE,
    debug_mode_getter=lambda: False,
    raw_print=builtins.print,
)

start_execution_time_counting = datetime.now()
start_timer(__file__)

task_config_bundle = load_step1_task_config_bundle(
    task_number,
    include_filter_parameter_config=False,
    log_fn=print,
)
config_root = task_config_bundle["config_root"]
config_file_path = task_config_bundle["config_file_path"]
plot_catalog_file_path = task_config_bundle["plot_catalog_file_path"]
parameter_config_file_path = task_config_bundle["parameter_config_file_path"]
plot_parameter_config_file_path = task_config_bundle["plot_parameter_config_file_path"]
fallback_parameter_config_file_path = task_config_bundle["fallback_parameter_config_file_path"]
config = task_config_bundle["config"]

if CLI_ARGS.station is None:
    CLI_PARSER.error("No station provided. Pass <station>.")
station = str(CLI_ARGS.station)
set_station(station)

config = resolve_step1_effective_task_config(
    config,
    station_id=station,
    task_number=task_number,
    config_root=config_root,
    parameter_config_file_path=parameter_config_file_path,
    fallback_parameter_config_file_path=fallback_parameter_config_file_path,
    plot_parameter_config_file_path=plot_parameter_config_file_path,
    use_filter_parameter_config=False,
    log_fn=print,
)
config["_plot_station_id"] = station
config["_plot_task_number"] = task_number
task0_plot_status_by_alias = load_step1_task_plot_catalog(
    plot_catalog_file_path,
    TASK0_PLOT_ALIASES,
    "Task 0",
    log_fn=print,
)
(
    plot_mode,
    create_plots,
    create_essential_plots,
    save_plots,
    create_pdf,
    show_plots,
    create_debug_plots,
) = resolve_step1_plot_options(config)

selection_config = load_selection_for_paths([config_file_path], master_config_root=config_root)
if not station_is_selected(station, selection_config.stations):
    print(f"Station {station} skipped by selection.stations.", force=True)
    sys.exit(0)

repo_root = get_repo_root()
home_path = str(resolve_home_path_from_config(config))
station_directory = repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / f"MINGO0{station}"
base_directory = station_directory / "STAGE_1" / "EVENT_DATA"
task_directory = base_directory / "STEP_1" / f"TASK_{task_number}"
raw_directory = station_directory / "STAGE_0_TO_1"

directories = {
    "unprocessed": task_directory / "INPUT_FILES" / "UNPROCESSED_DIRECTORY",
    "out_of_date": task_directory / "INPUT_FILES" / "OUT_OF_DATE_DIRECTORY",
    "processing": task_directory / "INPUT_FILES" / "PROCESSING_DIRECTORY",
    "completed": task_directory / "INPUT_FILES" / "COMPLETED_DIRECTORY",
    "error": task_directory / "INPUT_FILES" / "ERROR_DIRECTORY",
    "empty": task_directory / "ANCILLARY" / "EMPTY_FILES",
    "rejected": task_directory / "ANCILLARY" / "REJECTED_FILES",
    "metadata": task_directory / "METADATA",
    "output": task_directory / "OUTPUT_FILES",
    "pdf": task_directory / "PLOTS" / "PDF_DIRECTORY",
}
for directory in directories.values():
    directory.mkdir(parents=True, exist_ok=True)

csv_path = directories["metadata"] / f"task_{task_number}_metadata_execution.csv"
csv_path_status = directories["metadata"] / f"task_{task_number}_metadata_status.csv"
csv_path_trigger_type = directories["metadata"] / f"task_{task_number}_metadata_trigger_type.csv"
csv_path_gate_test = directories["metadata"] / f"task_{task_number}_metadata_gate_test.csv"

selected_input_file = CLI_ARGS.input_file_flag or CLI_ARGS.input_file
user_file_selection = bool(selected_input_file)
status_filename_base = Path(selected_input_file).stem if user_file_selection else f"__task{task_number}_startup_station_{station}__"
status_execution_date = initialize_status_row(
    csv_path_status,
    filename_base=status_filename_base,
    completion_fraction=0.0,
)

if not raw_directory.exists():
    raise FileNotFoundError(f"Task 0 raw acquisition directory does not exist: {raw_directory}")

if not user_file_selection:
    known_files = set()
    for key in ("unprocessed", "processing", "completed"):
        known_files.update(p.name for p in directories[key].iterdir() if p.is_file())

    for src in raw_directory.iterdir():
        if not src.is_file() or not src.name.lower().endswith(".dat"):
            continue
        if not station_matches_file(src.name, station):
            continue
        if src.stat().st_size == 0:
            dst = directories["empty"] / src.name
            if dst.exists():
                dst.unlink()
            safe_move(src, dst)
            continue
        if src.name in known_files:
            continue
        dst = directories["unprocessed"] / src.name
        safe_move(src, dst)
        os.utime(dst, None)
        print(f"Moved acquisition file to Task 0 UNPROCESSED: {src.name}")

    sync_unprocessed_with_date_range(
        config=config,
        unprocessed_directory=str(directories["unprocessed"]),
        out_of_date_directory=str(directories["out_of_date"]),
        log_fn=print,
        station_id=station,
        master_config_root=config_root,
    )

    date_ranges = load_date_ranges_from_config(config, station_id=station, master_config_root=config_root)
    candidates_by_source: list[tuple[str, Path, Path | None]] = []
    for source_key in ("unprocessed", "processing"):
        names = [p.name for p in directories[source_key].iterdir() if p.is_file() and p.name.lower().endswith(".dat")]
        if date_ranges:
            names = [name for name in names if file_name_in_any_date_range(name, date_ranges)]
        selected = _select_candidate(names, station)
        if selected:
            src = directories[source_key] / selected
            completed = directories["completed"] / selected
            candidates_by_source.append((selected, src, completed))
            break
    if not candidates_by_source and bool(config.get("complete_reanalysis", False)):
        names = [p.name for p in directories["completed"].iterdir() if p.is_file() and p.name.lower().endswith(".dat")]
        if date_ranges:
            names = [name for name in names if file_name_in_any_date_range(name, date_ranges)]
        selected = _select_candidate(names, station)
        if selected:
            src = directories["completed"] / selected
            completed = directories["completed"] / selected
            candidates_by_source.append((selected, src, completed))

    if not candidates_by_source:
        print("No Task 0 acquisition files to process.", force=True)
        no_file_status_basename = f"__task{task_number}_no_files_station_{station}__"
        if status_filename_base != no_file_status_basename:
            renamed = rename_status_row(
                csv_path_status,
                filename_base=status_filename_base,
                execution_date=status_execution_date,
                new_filename_base=no_file_status_basename,
            )
            if renamed:
                status_filename_base = no_file_status_basename
        update_status_progress(
            csv_path_status,
            filename_base=status_filename_base,
            execution_date=status_execution_date,
            completion_fraction=-1.0,
        )
        sys.exit(0)

    file_name, source_path, completed_file_path = candidates_by_source[0]
    processing_file_path = directories["processing"] / file_name
    if source_path != processing_file_path:
        if processing_file_path.exists():
            processing_file_path.unlink()
        safe_move(source_path, processing_file_path)
else:
    processing_file_path = Path(selected_input_file).expanduser()
    file_name = processing_file_path.name
    completed_file_path = None

if not station_matches_file(file_name, station):
    error_file_path = directories["error"] / file_name
    if processing_file_path.exists() and not user_file_selection:
        safe_move(processing_file_path, error_file_path)
    raise SystemExit(f"File '{file_name}' does not belong to station {station}.")

basename_no_ext = Path(file_name).stem
if status_filename_base != basename_no_ext:
    renamed = rename_status_row(
        csv_path_status,
        filename_base=status_filename_base,
        execution_date=status_execution_date,
        new_filename_base=basename_no_ext,
    )
    if renamed:
        status_filename_base = basename_no_ext
    else:
        print(
            "Warning: unable to rename Task 0 startup status row "
            f"from {status_filename_base} to {basename_no_ext}.",
            force=True,
        )
execution_timestamp = datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
date_execution = datetime.now().strftime("%y-%m-%d_%H.%M.%S")
rejected_file = directories["rejected"] / f"rejected_{basename_no_ext}_{date_execution}.csv"

expected_columns = int(config.get("EXPECTED_COLUMNS_config", 71))
limit_number = config.get("limit_number")
limit_rows = int(limit_number) if config.get("last_file_test", False) and limit_number is not None else None
try:
    acquisition_rate_accumulation_window_seconds = int(
        config.get("acquisition_rate_accumulation_window_seconds", 60)
    )
except (TypeError, ValueError):
    acquisition_rate_accumulation_window_seconds = 60
if acquisition_rate_accumulation_window_seconds <= 0:
    acquisition_rate_accumulation_window_seconds = 60
try:
    acquisition_rate_task_tt_histogram_bins = int(
        config.get("acquisition_rate_task_tt_histogram_bins", 80)
    )
except (TypeError, ValueError):
    acquisition_rate_task_tt_histogram_bins = 80
if acquisition_rate_task_tt_histogram_bins <= 0:
    acquisition_rate_task_tt_histogram_bins = 80

update_status_progress(
    csv_path_status,
    filename_base=status_filename_base,
    execution_date=status_execution_date,
    completion_fraction=0.25,
)

read_df, read_lines, written_lines = build_step1_raw_input_dataframe(
    processing_file_path,
    rejected_file,
    expected_columns,
    limit_rows=limit_rows,
)
if read_df.empty:
    if not user_file_selection and processing_file_path.exists():
        safe_move(processing_file_path, directories["error"] / file_name)
    raise SystemExit("No valid acquisition rows parsed; moved file to ERROR.")

left_limit_time = pd.to_datetime("1-1-2000", format="%d-%m-%Y")
right_limit_time = pd.to_datetime("1-1-2200", format="%d-%m-%Y")
read_df = read_df.loc[read_df["datetime"].between(left_limit_time, right_limit_time)].copy()
read_df = read_df.rename(columns=raw_channel_rename_map())
read_df = read_df.rename(columns={"column_6": "acquisition_type"})
_, simulated_param_hash = resolve_simulated_z_positions(
    basename_no_ext,
    repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / f"MINGO0{station}" / "STAGE_1" / "EVENT_DATA",
    dat_path=processing_file_path,
)
read_df.loc[:, "param_hash"] = str(simulated_param_hash) if simulated_param_hash else ""

coincidence_mask = read_df["acquisition_type"] == 1
self_trigger_mask = read_df["acquisition_type"] == 2
other_trigger_mask = ~(coincidence_mask | self_trigger_mask)
conf_time_source = read_df.loc[coincidence_mask, "datetime"]
if conf_time_source.dropna().empty:
    conf_time_source = read_df["datetime"]
conf_time_source = pd.to_datetime(conf_time_source, errors="coerce").dropna()
task0_conf_value = None
task0_channel_swap_applied = False
if not conf_time_source.empty:
    task0_conf_value = _resolve_station_conf_value(
        config_root=config_root,
        station=station,
        start_time=conf_time_source.iloc[0],
        end_time=conf_time_source.iloc[-1],
    )
    task0_channel_swap_applied = _apply_task0_raw_channel_ordering(
        read_df,
        station=station,
        conf_value=task0_conf_value,
    )
else:
    print("Task 0 channel ordering lookup skipped: no valid acquisition timestamps.", force=True)
read_df = compute_tt_task0_acq(read_df)
read_df = add_topology_task1_channel(read_df)

saved_plot_paths: list[Path] = []
figure_directory: Path | None = None
# FINAL plot block moved out of the runtime flow: acquisition_rate_vs_time_by_trigger_type
pass

# FINAL plot block moved out of the runtime flow: acquisition_rate_vs_time_by_task_tt_with_histograms
pass

if create_debug_plots and task0_plot_enabled("debug_suite"):
    if figure_directory is None:
        figure_directory = (
            task_directory
            / "PLOTS"
            / "FIGURE_DIRECTORY"
            / f"FIGURES_EXEC_ON_{date_execution}"
        )
    debug_plot_directory = figure_directory / "DEBUG_PLOTS"
    debug_plot_directory.mkdir(parents=True, exist_ok=True)
    debug_fig_idx = plot_debug_histograms(
        read_df,
        list(read_df.columns),
        thresholds=None,
        title=f"Task 0 acquisition dataframe: all columns [DEBUG] (station {station})",
        out_dir=str(debug_plot_directory),
        fig_idx=1,
        max_cols_per_fig=20,
        exclude_zeros=True,
        absolute_limit=1e5,
        annotate_omissions=True,
    )
    debug_plot_paths = sorted(debug_plot_directory.glob("*_debug_*.png"))
    saved_plot_paths.extend(debug_plot_paths)
    print(
        f"Task 0 debug suite saved {debug_fig_idx - 1} histogram page(s) "
        f"covering {len(read_df.columns)} column(s).",
        force=True,
    )


coincidence_df = read_df.loc[coincidence_mask].copy()
self_trigger_df = read_df.loc[self_trigger_mask].copy()
coincidence_df = compute_tt_task0_acq(coincidence_df, "tt_task0_raw")
coincidence_df.loc[:, "transferred_task0_acq_to_raw"] = (
    pd.to_numeric(coincidence_df["tt_task0_acq"], errors="coerce").fillna(0).astype(int).astype(str)
    + pd.to_numeric(coincidence_df["tt_task0_raw"], errors="coerce").fillna(0).astype(int).astype(str)
)
coincidence_df = add_topology_task1_channel(coincidence_df)
coincidence_df = canonicalize_step1_columns(coincidence_df)
if not self_trigger_df.empty:
    self_trigger_df = compute_tt_task0_acq(self_trigger_df, "tt_task0_raw")
    self_trigger_df.loc[:, "transferred_task0_acq_to_raw"] = (
        pd.to_numeric(self_trigger_df["tt_task0_acq"], errors="coerce").fillna(0).astype(int).astype(str)
        + pd.to_numeric(self_trigger_df["tt_task0_raw"], errors="coerce").fillna(0).astype(int).astype(str)
    )
    self_trigger_df = add_topology_task1_channel(self_trigger_df)
    self_trigger_df = canonicalize_step1_columns(self_trigger_df)

raw_output_path = directories["output"] / f"raw_{basename_no_ext}.parquet"
selftrigger_output_path = directories["output"] / f"selftrigger_raw_{basename_no_ext}.parquet"

coincidence_df.to_parquet(raw_output_path, engine="pyarrow", compression="zstd", index=False)
print(f"Task 0 coincidence raw parquet saved: {raw_output_path} rows={len(coincidence_df)}", force=True)

if self_trigger_df.empty:
    print("Task 0 self-trigger raw parquet skipped: no self-trigger rows.", force=True)
else:
    self_trigger_df.to_parquet(selftrigger_output_path, engine="pyarrow", compression="zstd", index=False)
    print(f"Task 0 self-trigger raw parquet saved: {selftrigger_output_path} rows={len(self_trigger_df)}", force=True)

coincidence_first, coincidence_last = datetime_bounds(coincidence_df)
self_first, self_last = datetime_bounds(self_trigger_df)
total_first, total_last = datetime_bounds(read_df)
total_duration_seconds = duration_seconds(read_df)
coincidence_duration_seconds = duration_seconds(coincidence_df)
self_trigger_duration_seconds = duration_seconds(self_trigger_df)
execution_time_minutes = (datetime.now() - start_execution_time_counting).total_seconds() / 60.0
metadata_row = {
    "filename_base": basename_no_ext,
    "execution_timestamp": execution_timestamp,
    "original_input_filename": file_name,
    "acquisition_basename": basename_no_ext,
    "param_hash": str(simulated_param_hash) if simulated_param_hash else "",
    "coincidence_raw_output_path": str(raw_output_path),
    "selftrigger_raw_output_path": "" if self_trigger_df.empty else str(selftrigger_output_path),
    "total_parsed_rows": int(len(read_df)),
    "input_read_lines": int(read_lines),
    "input_valid_lines": int(written_lines),
    "coincidence_rows": int(len(coincidence_df)),
    "self_trigger_rows": int(len(self_trigger_df)),
    "other_trigger_rows": int(other_trigger_mask.sum()),
    "total_first_datetime": total_first,
    "total_last_datetime": total_last,
    "coincidence_first_datetime": coincidence_first,
    "coincidence_last_datetime": coincidence_last,
    "self_trigger_first_datetime": self_first,
    "self_trigger_last_datetime": self_last,
    "total_duration_seconds": int(total_duration_seconds),
    "coincidence_duration_seconds": int(coincidence_duration_seconds),
    "self_trigger_duration_seconds": int(self_trigger_duration_seconds),
    "total_event_rate_hz": rate_hz(len(read_df), total_duration_seconds),
    "coincidence_event_rate_hz": rate_hz(len(coincidence_df), coincidence_duration_seconds),
    "self_trigger_event_rate_hz": rate_hz(len(self_trigger_df), self_trigger_duration_seconds),
    "input_valid_line_rate_hz": rate_hz(int(written_lines), total_duration_seconds),
    "total_execution_time_minutes": round(float(execution_time_minutes), 4),
    "raw_channel_order_conf": "" if task0_conf_value is None else task0_conf_value,
    "raw_channel_swap_plane4_3_4_applied": bool(task0_channel_swap_applied),
}
for tt_task0_acq_value, count in read_df["tt_task0_acq"].value_counts(dropna=False).sort_index().items():
    metadata_row[f"tt_task0_acq_{int(tt_task0_acq_value)}_count"] = int(count)
for tt_task0_raw_value, count in coincidence_df["tt_task0_raw"].value_counts(dropna=False).sort_index().items():
    metadata_row[f"tt_task0_raw_{int(tt_task0_raw_value)}_count"] = int(count)
save_metadata(
    csv_path,
    metadata_row,
    preferred_fieldnames=tuple(metadata_row.keys()),
    replace_existing_basename=True,
)

trigger_type_row = {
    "filename_base": basename_no_ext,
    "execution_timestamp": execution_timestamp,
    "param_hash": str(simulated_param_hash) if simulated_param_hash else "",
    "count_rate_denominator_seconds": int(total_duration_seconds),
}
task0_acq_counts = (
    pd.to_numeric(read_df["tt_task0_acq"], errors="coerce")
    .fillna(0)
    .astype(int)
    .value_counts()
)
for tt_value in (0, 1, 2, 3, 4, 12, 13, 14, 23, 24, 34, 123, 124, 134, 234, 1234):
    count = int(task0_acq_counts.get(tt_value, 0))
    trigger_type_row[f"tt_task0_acq_{tt_value}_count"] = count
    trigger_type_row[f"tt_task0_acq_{tt_value}_rate_hz"] = rate_hz(count, total_duration_seconds)
save_metadata(
    csv_path_trigger_type,
    trigger_type_row,
    preferred_fieldnames=tuple(trigger_type_row.keys()),
    replace_existing_basename=True,
)
print(f"Task 0 trigger-type metadata updated at: {csv_path_trigger_type}", force=True)

gate_test_row = build_task0_gate_test_metadata(
    read_df,
    filename_base=basename_no_ext,
    execution_timestamp=execution_timestamp,
    param_hash=str(simulated_param_hash) if simulated_param_hash else "",
    denominator_seconds=total_duration_seconds,
)
if gate_test_row["gate_test_missing_charge_column_count"]:
    print(
        "Warning: Task 0 gate-test metadata cannot evaluate all endpoint-charge gates; "
        f"missing columns: {gate_test_row['gate_test_missing_charge_columns']}",
        force=True,
    )
save_metadata(
    csv_path_gate_test,
    gate_test_row,
    preferred_fieldnames=tuple(gate_test_row.keys()),
    replace_existing_basename=True,
)
print(f"Task 0 gate-test metadata updated at: {csv_path_gate_test}", force=True)

if not user_file_selection and completed_file_path is not None and processing_file_path.exists():
    if completed_file_path.exists():
        completed_file_path.unlink()
    safe_move(processing_file_path, completed_file_path)
    now = time.time()
    os.utime(completed_file_path, (now, now))
    print(f"Task 0 acquisition moved to COMPLETED: {completed_file_path}")

update_status_progress(
    csv_path_status,
    filename_base=status_filename_base,
    execution_date=status_execution_date,
    completion_fraction=1.0,
)
