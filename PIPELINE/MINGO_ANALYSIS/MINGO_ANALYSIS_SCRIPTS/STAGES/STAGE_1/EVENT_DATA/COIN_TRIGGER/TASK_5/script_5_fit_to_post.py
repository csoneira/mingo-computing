#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/COIN_TRIGGER/TASK_5/script_5_fit_to_post.py
Purpose: !/usr/bin/env python3.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/COIN_TRIGGER/TASK_5/script_5_fit_to_post.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

#%%

from __future__ import annotations

"""
Stage 1 Task 5 (FIT-->CORR) finalisation stage.

Consumes the fit outputs from Task 4, applies the derived corrections to the
event lists, validates the corrected distributions, and emits the Stage 1
deliverables that feed Stage 2. The script oversees QA plotting, execution
metadata tracking, and file lifecycle management so the pipeline finishes with
a coherent, traceable set of corrected datasets per station.
"""
# Standard Library
import builtins
from datetime import datetime
import gc
import math
import os
from pathlib import Path
import random
import re
import shutil
import sys
import time
import warnings
from typing import Dict, Iterable, Optional

# Scientific Computing
import numpy as np
import pandas as pd
from scipy.constants import c

# Plotting
import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

# Image Processing

# Progress Bar
from tqdm import tqdm

import yaml

# Resolve repo root for local imports
CURRENT_PATH = Path(__file__).resolve()
REPO_ROOT = None
for parent in CURRENT_PATH.parents:
    if parent.name == "MINGO_ANALYSIS_SCRIPTS":
        REPO_ROOT = parent.parents[2]
        break
if REPO_ROOT is None:
    REPO_ROOT = CURRENT_PATH.parents[-1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.config_loader import update_config_with_parameters
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.debug_plots import plot_debug_histograms
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.execution_logger import set_station, start_timer
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.file_selection import (
    filter_expected_artifact_names,
    file_name_in_any_date_range,
    load_date_ranges_from_config,
    select_latest_candidate,
    sync_unprocessed_with_date_range,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.input_file_config import select_input_file_configuration
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import (
    get_repo_root,
    resolve_home_path_from_config,
    resolve_master_config_root_from_config,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.plot_utils import ensure_plot_state
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.selection_config import load_selection_for_paths, station_is_selected
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.step1_rate_plots import create_rate_vs_time_by_task_tt_with_histograms
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.status_csv import (
    delete_status_row,
    initialize_status_row,
    rename_status_row,
    update_status_progress,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.reprocessing_utils import (
    QA_REPROCESSING_METADATA_KEYS,
    apply_qa_reprocessing_context,
    canonical_processing_basename,
    filter_filenames_by_qa_retry_basenames,
    get_reprocessing_value,
    infer_station_number_from_processing_name,
    load_active_qa_retry_basenames,
    load_qa_reprocessing_context_for_file,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.simulated_data_utils import resolve_simulated_z_positions
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.step1_shared import (
    add_normalized_count_metadata,
    add_trigger_type_total_offender_threshold_metadata,
    apply_step1_task_parameter_overrides,
    build_events_per_second_metadata,
    build_step1_cli_parser,
    build_step1_filtered_print,
    canonicalize_step1_columns,
    coerce_nonnegative_float_config,
    coerce_positive_int_config,
    extract_rate_histogram_metadata,
    extract_trigger_type_metadata,
    ensure_plane_xpos_columns,
    is_trigger_type_file_column,
    is_trigger_type_metadata_column,
    is_specific_metadata_excluded_column,
    load_step1_task_config_bundle,
    load_step1_task_plot_catalog,
    normalize_tt_label,
    prune_redundant_count_metadata,
    replicate_joined_metadata_rows,
    resolve_step1_effective_task_config,
    save_metadata,
    select_joined_analysis_file_names,
    set_global_rate_from_tt_rates,
    resolve_step1_plot_options,
    step1_logging_enabled,
    step1_task_plot_enabled,
    validate_step1_input_file_args,
    y_pos,
)
from analysis_functions import (
    _charge_series_is_usable,
    _task5_parse_optional_top_n,
    add_task5_strip_topology_gate_columns,
    TASK5_TOPOLOGY_GATE_COLUMNS,
)
from plotting_functions import _task5_channel_hist_range

task_number = 5
TASK4_CHARGE_SUM_COLUMNS: tuple[str, ...] = (
    "p1_qsum",
    "p2_qsum",
    "p3_qsum",
    "p4_qsum",
)
TASK4_LISTED_FALLBACK_SUBDIRS: tuple[str, ...] = (
    "PROCESSING_DIRECTORY",
    "COMPLETED_DIRECTORY",
    "UNPROCESSED_DIRECTORY",
    "OUT_OF_DATE_DIRECTORY",
)
TASK5_STRIP_Q_COLUMN_RE = re.compile(r"^p[1-4]_s[1-4]_qsum$")
TASK5_PLANE_Q_SUM_COLUMN_RE = re.compile(r"^p[1-4]_qsum$")
POST_TT_COLUMN = "tt_task5_post"
TASK5_INTERNAL_EVENT_ALIASES: tuple[tuple[str, str], ...] = (
    ("event_x", "x"),
    ("event_y", "y"),
    ("event_xp", "xp"),
    ("event_yp", "yp"),
    ("event_s", "s"),
    ("event_t0", "t0"),
    ("event_theta", "theta"),
    ("event_phi", "phi"),
    ("event_x_err", "x_err"),
    ("event_y_err", "y_err"),
    ("event_s_err", "s_err"),
    ("event_t0_err", "t0_err"),
    ("event_theta_err", "theta_err"),
    ("event_phi_err", "phi_err"),
)
TASK5_GATE_CONFIG_DEFAULT_NAME = "config_gates_task_5.yaml"


class Task5GateConfigError(ValueError):
    """Raised when the Task 5 gate configuration is malformed."""


class Task5GateEvaluationError(ValueError):
    """Raised when a Task 5 gate expression cannot be evaluated."""

try:
    import pyarrow as pa
except Exception:  # pragma: no cover - pyarrow is already required for parquet IO here.
    pa = None


def _derive_event_charge_from_dataframe(
    dataframe: pd.DataFrame,
) -> tuple[pd.Series | None, str | None]:
    for column_name in ("event_charge", "tim_event_charge"):
        if column_name not in dataframe.columns:
            continue
        series = pd.to_numeric(dataframe[column_name], errors="coerce")
        if _charge_series_is_usable(series):
            return series.astype(float), column_name

    plane_sum_columns = [
        column_name
        for column_name in dataframe.columns
        if TASK5_PLANE_Q_SUM_COLUMN_RE.fullmatch(str(column_name))
    ]
    if plane_sum_columns:
        plane_sum_series = (
            dataframe.loc[:, plane_sum_columns]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0.0)
            .sum(axis=1)
            .astype(float)
        )
        if _charge_series_is_usable(plane_sum_series):
            return plane_sum_series, "+".join(plane_sum_columns)

    strip_q_columns = [
        column_name
        for column_name in dataframe.columns
        if TASK5_STRIP_Q_COLUMN_RE.fullmatch(str(column_name))
    ]
    if strip_q_columns:
        strip_q_series = (
            dataframe.loc[:, strip_q_columns]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0.0)
            .sum(axis=1)
            .astype(float)
        )
        if _charge_series_is_usable(strip_q_series):
            return strip_q_series, "+".join(strip_q_columns)

    return None, None


def _ensure_task5_internal_event_aliases(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Task 5 still uses short track names internally; outputs are canonicalized before write."""
    for canonical_name, internal_name in TASK5_INTERNAL_EVENT_ALIASES:
        if internal_name not in dataframe.columns and canonical_name in dataframe.columns:
            source = dataframe[canonical_name]
            if isinstance(source, pd.DataFrame):
                source = source.iloc[:, 0]
            dataframe.loc[:, internal_name] = source
    return dataframe


def _load_task5_gate_config(config_path: str | Path) -> list[dict[str, object]]:
    raw_config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    gates_section = raw_config.get("gates")
    if not isinstance(gates_section, dict) or not gates_section:
        raise Task5GateConfigError("Task 5 gate config must define a non-empty top-level 'gates' mapping.")

    seen_bits: set[int] = set()
    gate_definitions: list[dict[str, object]] = []
    for gate_name, gate_config in gates_section.items():
        if not isinstance(gate_config, dict):
            raise Task5GateConfigError(f"Gate '{gate_name}' must be defined as a mapping.")
        if "bit" not in gate_config:
            raise Task5GateConfigError(f"Gate '{gate_name}' is missing its bit index.")
        if "expression" not in gate_config or not str(gate_config["expression"]).strip():
            raise Task5GateConfigError(f"Gate '{gate_name}' is missing its expression.")

        bit = int(gate_config["bit"])
        if bit < 0 or bit > 63:
            raise Task5GateConfigError(f"Gate '{gate_name}' uses bit {bit}; valid bits are 0 through 63.")
        if bit in seen_bits:
            raise Task5GateConfigError(f"Gate '{gate_name}' reuses bit {bit}. Gate bits must be unique.")
        seen_bits.add(bit)

        gate_definitions.append(
            {
                "name": str(gate_name),
                "bit": bit,
                "bit_value": np.uint64(1 << bit),
                "description": str(gate_config.get("description", "") or ""),
                "expression": str(gate_config["expression"]).strip(),
            }
        )
    return gate_definitions


def _evaluate_task5_gate_expression(dataframe: pd.DataFrame, gate_definition: dict[str, object]) -> np.ndarray:
    gate_name = str(gate_definition["name"])
    expression = str(gate_definition["expression"])
    try:
        result = dataframe.eval(expression, engine="python")
    except Exception as exc:
        raise Task5GateEvaluationError(
            f"Failed to evaluate Task 5 gate '{gate_name}' with expression '{expression}': {exc}"
        ) from exc

    if not isinstance(result, pd.Series):
        raise Task5GateEvaluationError(
            f"Task 5 gate '{gate_name}' did not return a pandas Series. "
            "Use a vectorized boolean expression."
        )
    if len(result) != len(dataframe):
        raise Task5GateEvaluationError(
            f"Task 5 gate '{gate_name}' returned {len(result)} rows, expected {len(dataframe)}."
        )
    return result.fillna(False).to_numpy(dtype=bool)


def apply_task5_gates(dataframe: pd.DataFrame, gate_definitions: list[dict[str, object]]) -> pd.DataFrame:
    gate_mask = np.zeros(len(dataframe), dtype=np.uint64)
    gate_labels = np.full(len(dataframe), "none", dtype=object)

    for gate_definition in gate_definitions:
        event_mask = _evaluate_task5_gate_expression(dataframe, gate_definition)
        gate_mask[event_mask] |= np.uint64(gate_definition["bit_value"])
        gate_name = str(gate_definition["name"])
        current_labels = gate_labels[event_mask]
        gate_labels[event_mask] = np.where(
            current_labels == "none",
            gate_name,
            np.char.add(np.char.add(current_labels.astype(str), "|"), gate_name),
        )
        print(f"Task 5 gate '{gate_name}': {int(event_mask.sum())} matching rows.")

    dataframe.loc[:, "gate_mask"] = gate_mask
    dataframe.loc[:, "gate"] = gate_labels
    return dataframe


def _load_event_charge_from_task4_listed(
    station_root: str | Path,
    basename_no_ext: str,
    event_ids: pd.Series,
) -> tuple[pd.Series | None, str | None]:
    if event_ids.empty:
        return None, None

    task4_input_root = (
        Path(station_root)
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / "TASK_4"
        / "INPUT_FILES"
    )

    for subdir_name in TASK4_LISTED_FALLBACK_SUBDIRS:
        candidate_path = task4_input_root / subdir_name / f"listed_{basename_no_ext}.parquet"
        if not candidate_path.exists():
            continue
        try:
            task4_df = pd.read_parquet(
                candidate_path,
                columns=["event_id", *TASK4_CHARGE_SUM_COLUMNS],
            )
        except Exception as exc:
            print(f"Warning: could not load Task 4 charge fallback {candidate_path}: {exc}")
            continue
        if "event_id" not in task4_df.columns:
            continue

        present_charge_columns = [
            column_name
            for column_name in TASK4_CHARGE_SUM_COLUMNS
            if column_name in task4_df.columns
        ]
        if not present_charge_columns:
            continue

        charge_lookup = task4_df.loc[:, ["event_id", *present_charge_columns]].copy()
        charge_lookup["event_charge"] = (
            charge_lookup.loc[:, present_charge_columns]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0.0)
            .sum(axis=1)
            .astype(float)
        )
        charge_lookup = charge_lookup.loc[:, ["event_id", "event_charge"]]
        charge_lookup = charge_lookup.drop_duplicates(subset=["event_id"], keep="last")

        aligned = pd.DataFrame({"event_id": event_ids}).merge(
            charge_lookup,
            on="event_id",
            how="left",
        )["event_charge"]
        if _charge_series_is_usable(aligned):
            return aligned.astype(float), str(candidate_path)

    return None, None


def resolve_event_charge_series(
    dataframe: pd.DataFrame,
    *,
    station_root: str | Path,
    basename_no_ext: str,
) -> tuple[pd.Series | None, str | None]:
    series, source = _derive_event_charge_from_dataframe(dataframe)
    if series is not None:
        return series, source

    if "event_id" in dataframe.columns:
        return _load_event_charge_from_task4_listed(
            station_root,
            basename_no_ext,
            pd.to_numeric(dataframe["event_id"], errors="coerce"),
        )

    return None, None



def task5_plot_enabled(alias: str) -> bool:
    if not task5_plot_status_by_alias:
        return True
    return step1_task_plot_enabled(alias, task5_plot_status_by_alias, plot_mode)


def resolve_task5_plot_alias(save_path: str, alias: str | None = None) -> str | None:
    if alias is not None:
        return alias if alias in TASK5_PLOT_ALIASES else None

    stem = os.path.splitext(os.path.basename(str(save_path)))[0].lower()
    stem = re.sub(r"^\d+_", "", stem)
    if stem in TASK5_PLOT_ALIASES:
        return stem
    return None


def apply_task5_plot_catalog_modes() -> None:
    global create_plots, create_essential_plots, create_debug_plots, save_plots, create_pdf
    if not task5_plot_status_by_alias:
        return
    create_plots = create_plots and task5_plot_enabled("usual_suite")
    create_essential_plots = create_essential_plots and task5_plot_enabled("essential_suite")
    create_debug_plots = create_debug_plots and task5_plot_enabled("debug_suite")
    save_plots = bool(create_plots or create_essential_plots or create_debug_plots)
    create_pdf = False  # Runtime plots are strictly PNG-only; FINAL PDFs are standalone.


def _coerce_config_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _task5_config_float(
    config_obj: dict[str, object],
    primary_key: str,
    *alias_keys: str,
    default: float,
) -> float:
    for key in (primary_key, *alias_keys):
        raw_value = config_obj.get(key)
        if raw_value is None:
            continue
        if isinstance(raw_value, str) and raw_value.strip().lower() in {"", "none", "null"}:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid numeric configuration value for '{key}': {raw_value!r}") from exc
        if not np.isfinite(value):
            raise ValueError(f"Non-finite numeric configuration value for '{key}': {raw_value!r}")
        return value
    return float(default)



def _log_filter_metrics_message(message: str) -> None:
    if FILTER_METRICS_LOGGING_ENABLED:
        print(message)

def safe_move(source_path: str, dest_path: str) -> str:
    """Move *source_path* to *dest_path* with explicit diagnostics on failure."""
    try:
        return shutil.move(source_path, dest_path)
    except OSError as exc:
        print(f"Error moving '{source_path}' to '{dest_path}': {exc}")
        raise


def _track_figure(fig: mpl.figure.Figure) -> mpl.figure.Figure:
    fig_number = getattr(fig, "number", None)
    if fig_number is None:
        return fig
    if fig_number not in _OPEN_FIGURE_IDS:
        _OPEN_FIGURE_IDS.append(fig_number)
    while len(_OPEN_FIGURE_IDS) > MAX_OPEN_FIGURES:
        stale_fig_number = _OPEN_FIGURE_IDS.pop(0)
        _ORIGINAL_PLT_CLOSE(stale_fig_number)
    return fig

def _guarded_figure(*args, **kwargs):
    return _track_figure(_ORIGINAL_PLT_FIGURE(*args, **kwargs))

def _guarded_subplots(*args, **kwargs):
    fig, axes = _ORIGINAL_PLT_SUBPLOTS(*args, **kwargs)
    _track_figure(fig)
    return fig, axes

def _guarded_close(*args, **kwargs):
    target = args[0] if args else kwargs.get("fig", None)
    result = _ORIGINAL_PLT_CLOSE(*args, **kwargs)
    if target in (None, "all"):
        _OPEN_FIGURE_IDS.clear()
    elif isinstance(target, mpl.figure.Figure):
        fig_number = getattr(target, "number", None)
        if fig_number in _OPEN_FIGURE_IDS:
            _OPEN_FIGURE_IDS.remove(fig_number)
    elif isinstance(target, int) and target in _OPEN_FIGURE_IDS:
        _OPEN_FIGURE_IDS.remove(target)
    return result




def save_plot_figure(
    save_path: str,
    fig: mpl.figure.Figure | None = None,
    alias: str | None = None,
    **savefig_kwargs,
) -> None:
    """Save one runtime plot as PNG."""
    plot_alias = resolve_task5_plot_alias(save_path, alias=alias)
    if plot_alias is not None and not task5_plot_enabled(plot_alias):
        return
    target_fig = fig if fig is not None else plt.gcf()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    target_fig.savefig(save_path, **savefig_kwargs)





def _exit_without_status_row(message: str) -> None:
    print(message)
    if status_execution_date is not None:
        deleted = delete_status_row(
            early_status_csv_path,
            filename_base=status_filename_base,
            execution_date=status_execution_date,
        )
        if not deleted:
            print(
                "Warning: unable to delete startup status row "
                f"{status_filename_base} ({status_execution_date})."
            )
    sys.exit(0)



def _expected_input_files(file_names):
    return sorted(
        filter_expected_artifact_names(
            file_names,
            prefix=EXPECTED_INPUT_PREFIX,
            extension=EXPECTED_INPUT_EXTENSION,
        )
    )

def process_file(source_path, dest_path):
    print("Source path:", source_path)
    print("Destination path:", dest_path)

    if source_path == dest_path:
        return True

    if os.path.exists(dest_path):
        print(f"File already exists at destination (removing...)")
        os.remove(dest_path)
        # return False

    print("**********************************************************************")
    print(f"Moving\n'{source_path}'\nto\n'{dest_path}'...")
    print("**********************************************************************")

    safe_move(source_path, dest_path)
    now = time.time()
    os.utime(dest_path, (now, now))
    return True


# Helper: compute trigger types based on positive charge columns
def _task5_tt_charge_columns(columns: list[str]) -> list[str]:
    return [
        col
        for col in columns
        if str(col).lower().endswith("_q")
        or "_qsum" in str(col).lower()
        or "_q_sum" in str(col).lower()
    ]


def compute_tt(df: pd.DataFrame, column_name: str, columns_map: dict[int, list[str]] | None = None) -> pd.DataFrame:
    """Compute trigger type based on planes with positive charge."""
    tt_str = pd.Series("", index=df.index, dtype="object")
    for plane in range(1, 5):
        if columns_map:
            charge_columns = [col for col in columns_map.get(plane, []) if col in df.columns]
        else:
            charge_columns = [
                col
                for col in [
                    f"p{plane}_s1_ef_q",
                    f"p{plane}_s2_ef_q",
                    f"p{plane}_s3_ef_q",
                    f"p{plane}_s4_ef_q",
                    f"p{plane}_s1_eb_q",
                    f"p{plane}_s2_eb_q",
                    f"p{plane}_s3_eb_q",
                    f"p{plane}_s4_eb_q",
                ]
                if col in df.columns
            ]
        charge_columns = _task5_tt_charge_columns(charge_columns)
        if charge_columns:
            charge_values = df.loc[:, charge_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
            has_charge = charge_values.gt(0.0).any(axis=1)
            tt_str = tt_str.where(~has_charge, tt_str + str(plane))
    df.loc[:, column_name] = tt_str.replace("", "0").astype(int)
    return df


def ensure_global_count_keys(prefixes: Iterable[str]) -> None:
    for prefix in prefixes:
        for tt_value in TT_COUNT_VALUES:
            global_variables.setdefault(f"{prefix}_{tt_value}_count", 0)


def _task5_channel_order_key(channel_key: tuple[int, str, int]) -> tuple[int, int, int]:
    plane, side, strip = channel_key
    return (plane, 0 if side == "F" else 1, strip)


def _task5_channel_relation_type(
    channel_a: tuple[int, str, int],
    channel_b: tuple[int, str, int],
) -> str:
    if channel_a == channel_b:
        return "self"
    if channel_a[0] == channel_b[0] and channel_a[2] == channel_b[2]:
        return "same_strip"
    if channel_a[0] == channel_b[0]:
        return "same_plane"
    return "any"


def collect_task5_channel_qt_map(
    df_input: pd.DataFrame,
) -> dict[tuple[int, str, int], dict[str, str]]:
    channel_map: dict[tuple[int, str, int], dict[str, str]] = {}
    for plane in range(1, 5):
        for side in ("F", "B"):
            for strip in range(1, 5):
                side_token = "ef" if side == "F" else "eb"
                q_col = f"p{plane}_s{strip}_{side_token}_q"
                t_col = f"p{plane}_s{strip}_{side_token}_t"
                if q_col in df_input.columns and t_col in df_input.columns:
                    channel_map[(plane, side, strip)] = {"Q": q_col, "T": t_col}
    return channel_map


def _iter_task5_channel_relation_pairs(
    channel_map: dict[tuple[int, str, int], dict[str, str]],
) -> Iterable[tuple[tuple[int, str, int], tuple[int, str, int], str]]:
    ordered_channels = sorted(channel_map, key=_task5_channel_order_key)
    for idx, channel_a in enumerate(ordered_channels):
        yield channel_a, channel_a, "self"
        for channel_b in ordered_channels[idx + 1 :]:
            yield channel_a, channel_b, _task5_channel_relation_type(channel_a, channel_b)


def _task5_load_channel_combination_relation_limits(
    task1_config: dict,
) -> dict[str, dict[str, tuple[float | None, float | None]]]:
    q_side_left_default = float(task1_config.get("Q_side_left_pre_cal_default", 0.0))
    q_side_right_default = float(task1_config.get("Q_side_right_pre_cal_default", 0.0))
    t_side_left_default = float(task1_config.get("T_side_left_pre_cal_default", 0.0))
    t_side_right_default = float(task1_config.get("T_side_right_pre_cal_default", 0.0))
    t_dif_threshold = float(task1_config.get("T_dif_pre_cal_threshold", 20.0))

    base_q_sum_left = float(
        task1_config.get(
            "channel_combination_q_sum_left",
            task1_config.get("plane_combination_q_sum_left", q_side_left_default),
        )
    )
    base_q_sum_right = float(
        task1_config.get(
            "channel_combination_q_sum_right",
            task1_config.get("plane_combination_q_sum_right", q_side_right_default),
        )
    )
    base_q_dif_threshold = float(
        task1_config.get(
            "channel_combination_q_dif_threshold",
            task1_config.get("plane_combination_q_dif_threshold", 200.0),
        )
    )
    base_t_sum_left = float(
        task1_config.get(
            "channel_combination_t_sum_left",
            task1_config.get("plane_combination_t_sum_left", t_side_left_default),
        )
    )
    base_t_sum_right = float(
        task1_config.get(
            "channel_combination_t_sum_right",
            task1_config.get("plane_combination_t_sum_right", t_side_right_default),
        )
    )
    base_t_dif_threshold = float(
        task1_config.get(
            "channel_combination_t_dif_threshold",
            task1_config.get("plane_combination_t_dif_threshold", t_dif_threshold),
        )
    )

    relation_limits: dict[str, dict[str, tuple[float | None, float | None]]] = {}
    for relation_type in TASK5_CHANNEL_COMBINATION_RELATION_TYPES:
        q_sum_left = float(
            task1_config.get(f"channel_combination_{relation_type}_q_sum_left", base_q_sum_left)
        )
        q_sum_right = float(
            task1_config.get(f"channel_combination_{relation_type}_q_sum_right", base_q_sum_right)
        )
        q_dif_abs = float(
            task1_config.get(
                f"channel_combination_{relation_type}_q_dif_threshold",
                base_q_dif_threshold,
            )
        )
        t_sum_left = float(
            task1_config.get(f"channel_combination_{relation_type}_t_sum_left", base_t_sum_left)
        )
        t_sum_right = float(
            task1_config.get(f"channel_combination_{relation_type}_t_sum_right", base_t_sum_right)
        )
        t_dif_abs = float(
            task1_config.get(
                f"channel_combination_{relation_type}_t_dif_threshold",
                base_t_dif_threshold,
            )
        )
        relation_limits[relation_type] = {
            "q_sum": (q_sum_left, q_sum_right),
            "q_dif": (-q_dif_abs, q_dif_abs),
            "t_sum": (t_sum_left, t_sum_right),
            "t_dif": (-t_dif_abs, t_dif_abs),
        }
    return relation_limits


def _task5_load_task1_channel_combination_settings() -> tuple[
    dict[str, dict[str, tuple[float | None, float | None]]],
    dict[str, int | None],
]:
    try:
        task1_config_path = (
            config_root
            / "STAGE_1"
            / "EVENT_DATA"
            / "STEP_1"
            / "TASK_1"
            / "config_task_1.yaml"
        )
        task1_parameter_config_path = (
            config_root
            / "STAGE_1"
            / "EVENT_DATA"
            / "STEP_1"
            / "TASK_1"
            / "config_parameters_task_1.csv"
        )
        task1_fallback_parameter_config_path = (
            config_root
            / "STAGE_1"
            / "EVENT_DATA"
            / "STEP_1"
            / "config_parameters.csv"
        )
        with task1_config_path.open("r", encoding="utf-8") as task1_config_file:
            task1_config = yaml.safe_load(task1_config_file) or {}
        task1_filter_parameter_config_path = task1_config_path.with_name(
            str(task1_config.get("filter_parameter_config_csv", "config_filter_parameters_task_1.csv"))
        )
        if task1_filter_parameter_config_path.exists():
            task1_config = update_config_with_parameters(
                task1_config,
                task1_filter_parameter_config_path,
                station,
            )
        task1_config = apply_step1_task_parameter_overrides(
            config_obj=task1_config,
            station_id=station,
            task_parameter_path=str(task1_parameter_config_path),
            fallback_parameter_path=str(task1_fallback_parameter_config_path),
            task_number=1,
            log_fn=lambda *_args, **_kwargs: None,
        )
        base_top_n = _task5_parse_optional_top_n(
            task1_config.get("channel_combination_plot_top_n", 10),
            10,
        )
        top_n_by_relation = {
            relation_type: _task5_parse_optional_top_n(
                task1_config.get(f"channel_combination_plot_top_n_{relation_type}", base_top_n),
                base_top_n,
            )
            for relation_type in TASK5_CHANNEL_COMBINATION_RELATION_TYPES
        }
        return _task5_load_channel_combination_relation_limits(task1_config), top_n_by_relation
    except Exception as exc:
        print(
            "Warning: failed to load Task 1 channel-combination limits for Task 5 audit: "
            f"{exc}"
        )
        return (
            {
                relation_type: {
                    observable: (None, None)
                    for observable, _ in TASK5_CHANNEL_COMBINATION_OBSERVABLES
                }
                for relation_type in TASK5_CHANNEL_COMBINATION_RELATION_TYPES
            },
            {relation_type: 10 for relation_type in TASK5_CHANNEL_COMBINATION_RELATION_TYPES},
        )


def _task5_resolve_audit_tt_column(df_input: pd.DataFrame) -> str | None:
    for candidate in ("tt_task0_raw", "tt_task1_clean", "tt_task2_cal", "tt_task3_list", "tt_task4_fit", POST_TT_COLUMN):
        if candidate in df_input.columns:
            return candidate
    return None


def collect_task5_channel_combination_payload(
    df_input: pd.DataFrame,
    tt_column: str,
) -> pd.DataFrame:
    if tt_column not in df_input.columns:
        return pd.DataFrame(
            columns=["tt", "combo", "relation_type", "q_sum", "q_dif", "t_sum", "t_dif"]
        )

    channel_map = collect_task5_channel_qt_map(df_input)
    if not channel_map:
        return pd.DataFrame(
            columns=["tt", "combo", "relation_type", "q_sum", "q_dif", "t_sum", "t_dif"]
        )

    tt_series = df_input[tt_column].apply(normalize_tt_label).astype(str)
    payload_rows: list[pd.DataFrame] = []
    for channel_a, channel_b, relation_type in _iter_task5_channel_relation_pairs(channel_map):
        cols_a = channel_map[channel_a]
        cols_b = channel_map[channel_b]
        q_a = pd.to_numeric(df_input[cols_a["Q"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        q_b = pd.to_numeric(df_input[cols_b["Q"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        t_a = pd.to_numeric(df_input[cols_a["T"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        t_b = pd.to_numeric(df_input[cols_b["T"]], errors="coerce").fillna(0).to_numpy(dtype=float)

        if relation_type == "self":
            valid_mask = np.isfinite(q_a) & np.isfinite(t_a) & ((q_a != 0) | (t_a != 0))
            q_sum = q_a
            q_dif = np.zeros_like(q_a, dtype=float)
            t_sum = t_a
            t_dif = np.zeros_like(t_a, dtype=float)
        else:
            valid_mask = (
                np.isfinite(q_a)
                & np.isfinite(q_b)
                & np.isfinite(t_a)
                & np.isfinite(t_b)
                & (q_a != 0)
                & (q_b != 0)
                & (t_a != 0)
                & (t_b != 0)
            )
            q_sum = 0.5 * (q_a + q_b)
            q_dif = 0.5 * (q_a - q_b)
            t_sum = 0.5 * (t_a + t_b)
            t_dif = 0.5 * (t_a - t_b)

        if not np.any(valid_mask):
            continue

        valid_index = df_input.index[valid_mask]
        payload_rows.append(
            pd.DataFrame(
                {
                    "tt": tt_series.loc[valid_index].to_numpy(dtype=str),
                    "combo": (
                        f"P{channel_a[0]}S{channel_a[2]}{channel_a[1]}-"
                        f"P{channel_b[0]}S{channel_b[2]}{channel_b[1]}"
                    ),
                    "relation_type": relation_type,
                    "q_sum": q_sum[valid_mask],
                    "q_dif": q_dif[valid_mask],
                    "t_sum": t_sum[valid_mask],
                    "t_dif": t_dif[valid_mask],
                }
            )
        )

    if not payload_rows:
        return pd.DataFrame(
            columns=["tt", "combo", "relation_type", "q_sum", "q_dif", "t_sum", "t_dif"]
        )
    return pd.concat(payload_rows, ignore_index=True)


def plot_task5_channel_combination_filter_by_tt(
    df_input: pd.DataFrame,
    basename_no_ext_value: str,
    fig_idx_value: int,
    *,
    show_plots: bool,
    save_plots: bool,
    plot_list: list[str] | None,
) -> int:
    channel_map = collect_task5_channel_qt_map(df_input)
    if not channel_map:
        print(
            "Warning: Task 5 channel_combination_filter_by_tt requires the surviving "
            "channel Q*/T* columns to still be present. Re-run with "
            "keep_all_columns_output=true from Task 2 onward."
        )
        return fig_idx_value

    tt_column = _task5_resolve_audit_tt_column(df_input)
    if tt_column is None:
        print("Warning: Task 5 channel_combination_filter_by_tt found no TT column to group by.")
        return fig_idx_value

    relation_limits, top_n_by_relation = _task5_load_task1_channel_combination_settings()
    relation_label_map = {
        "self": "self",
        "same_strip": "same strip",
        "same_plane": "same plane",
        "any": "any",
    }
    observable_labels = {
        observable: label for observable, label in TASK5_CHANNEL_COMBINATION_OBSERVABLES
    }
    payload = collect_task5_channel_combination_payload(df_input, tt_column)
    tt_counts = (
        pd.to_numeric(df_input[tt_column], errors="coerce").fillna(0).astype(int).value_counts()
    )
    ordered_tts = [
        normalize_tt_label(tt_value)
        for tt_value in TT_COUNT_VALUES
        if tt_value >= 10 and int(tt_counts.get(int(tt_value), 0)) > 0
    ]
    if not ordered_tts:
        print(f"Warning: no {tt_column}>=10 populations available for Task 5 channel audit plot.")
        return fig_idx_value

    rng = np.random.default_rng(0)
    for tt_label in ordered_tts:
        for relation_type in TASK5_CHANNEL_COMBINATION_RELATION_TYPES:
            current_tt_all = payload.loc[
                (payload["tt"] == tt_label) & (payload["relation_type"] == relation_type)
            ].copy()
            if current_tt_all.empty:
                continue

            top_n = top_n_by_relation.get(relation_type)
            combo_counts = current_tt_all["combo"].value_counts()
            combo_labels = combo_counts.index.tolist() if top_n is None else combo_counts.index[:top_n].tolist()
            current_tt = current_tt_all.loc[current_tt_all["combo"].isin(combo_labels)].copy()
            if current_tt.empty:
                continue

            n_obs = len(TASK5_CHANNEL_COMBINATION_OBSERVABLES)
            fig, axes = plt.subplots(
                n_obs,
                n_obs,
                figsize=(2.4 * n_obs, 2.4 * n_obs),
                constrained_layout=True,
            )
            combo_color_map = {
                label: plt.get_cmap("turbo")(
                    0.08 + 0.84 * idx / max(1, len(combo_labels) - 1)
                )
                for idx, label in enumerate(combo_labels)
            }
            axis_ranges: dict[str, tuple[float, float]] = {}
            for observable_name, _observable_label in TASK5_CHANNEL_COMBINATION_OBSERVABLES:
                values = pd.to_numeric(
                    current_tt_all.get(observable_name, pd.Series(dtype=float)),
                    errors="coerce",
                ).to_numpy(dtype=float)
                values = values[np.isfinite(values)]
                axis_ranges[observable_name] = _task5_channel_hist_range(
                    values,
                    relation_limits.get(relation_type, {}).get(observable_name, (None, None)),
                )

            any_panel_data = False
            for row_idx, (y_name, y_label) in enumerate(TASK5_CHANNEL_COMBINATION_OBSERVABLES):
                for col_idx, (x_name, x_label) in enumerate(TASK5_CHANNEL_COMBINATION_OBSERVABLES):
                    ax = axes[row_idx, col_idx]
                    if col_idx > row_idx:
                        ax.set_axis_off()
                        continue

                    x_low, x_high = axis_ranges[x_name]
                    if row_idx == col_idx:
                        bins = np.linspace(x_low, x_high, 60)
                        panel_has_data = False
                        for combo_label in combo_labels:
                            values = pd.to_numeric(
                                current_tt.loc[current_tt["combo"] == combo_label, x_name],
                                errors="coerce",
                            ).to_numpy(dtype=float)
                            values = values[np.isfinite(values)]
                            if not values.size:
                                continue
                            panel_has_data = True
                            ax.hist(
                                values,
                                bins=bins,
                                histtype="step",
                                linewidth=1.3,
                                alpha=0.95,
                                color=combo_color_map[combo_label],
                            )
                        if not panel_has_data:
                            ax.set_axis_off()
                            continue
                        any_panel_data = True
                        lower_limit, upper_limit = relation_limits.get(relation_type, {}).get(
                            x_name,
                            (None, None),
                        )
                        if lower_limit is not None:
                            ax.axvline(float(lower_limit), color="red", linestyle="--", linewidth=1.0)
                        if upper_limit is not None:
                            ax.axvline(float(upper_limit), color="red", linestyle="--", linewidth=1.0)
                        ax.set_xlim(x_low, x_high)
                        ax.set_yscale("log", nonpositive="clip")
                        ax.set_ylabel("Counts", fontsize=8)
                        ax.set_title(x_label, fontsize=9)
                    else:
                        y_low, y_high = axis_ranges[y_name]
                        panel_has_data = False
                        for combo_label in combo_labels:
                            combo_df = current_tt.loc[current_tt["combo"] == combo_label]
                            x_values = pd.to_numeric(combo_df[x_name], errors="coerce").to_numpy(dtype=float)
                            y_values = pd.to_numeric(combo_df[y_name], errors="coerce").to_numpy(dtype=float)
                            mask = np.isfinite(x_values) & np.isfinite(y_values)
                            if not np.any(mask):
                                continue
                            x_values = x_values[mask]
                            y_values = y_values[mask]
                            if x_values.size > TASK5_CHANNEL_COMBINATION_SCATTER_MAX_POINTS:
                                selection = rng.choice(
                                    x_values.size,
                                    size=TASK5_CHANNEL_COMBINATION_SCATTER_MAX_POINTS,
                                    replace=False,
                                )
                                x_values = x_values[selection]
                                y_values = y_values[selection]
                            panel_has_data = True
                            ax.scatter(
                                x_values,
                                y_values,
                                s=6,
                                alpha=0.18,
                                color=combo_color_map[combo_label],
                                edgecolors="none",
                                rasterized=True,
                            )
                        if not panel_has_data:
                            ax.set_axis_off()
                            continue
                        any_panel_data = True
                        x_limits = relation_limits.get(relation_type, {}).get(x_name, (None, None))
                        y_limits = relation_limits.get(relation_type, {}).get(y_name, (None, None))
                        if x_limits[0] is not None:
                            ax.axvline(float(x_limits[0]), color="red", linestyle="--", linewidth=0.9)
                        if x_limits[1] is not None:
                            ax.axvline(float(x_limits[1]), color="red", linestyle="--", linewidth=0.9)
                        if y_limits[0] is not None:
                            ax.axhline(float(y_limits[0]), color="red", linestyle="--", linewidth=0.9)
                        if y_limits[1] is not None:
                            ax.axhline(float(y_limits[1]), color="red", linestyle="--", linewidth=0.9)
                        ax.set_xlim(x_low, x_high)
                        ax.set_ylim(y_low, y_high)

                    if row_idx == n_obs - 1:
                        ax.set_xlabel(x_label, fontsize=8)
                    else:
                        ax.set_xticklabels([])
                    if col_idx == 0 and row_idx != col_idx:
                        ax.set_ylabel(y_label, fontsize=8)
                    elif col_idx != 0:
                        ax.set_yticklabels([])
                    ax.grid(alpha=0.12)
                    ax.tick_params(labelsize=6)

            if not any_panel_data:
                plt.close(fig)
                continue

            style_handles = [
                mpl.lines.Line2D(
                    [0],
                    [0],
                    color="red",
                    linestyle="--",
                    linewidth=1.2,
                    label="Task 1 configured limits",
                )
            ]
            combo_handles = [
                mpl.lines.Line2D(
                    [0],
                    [0],
                    color=combo_color_map[label],
                    linestyle="-",
                    linewidth=1.6,
                    label=f"{label} (N={int(combo_counts.get(label, 0))})",
                )
                for label in combo_labels
            ]
            fig.legend(
                handles=style_handles + combo_handles,
                loc="upper center",
                bbox_to_anchor=(0.5, 0.995),
                ncol=min(5, max(2, len(combo_handles) + 1)),
                fontsize=6,
                frameon=False,
                handlelength=1.8,
                columnspacing=0.8,
            )
            combo_mode_label = "all pairs" if top_n is None else f"top {int(top_n)} pairs"
            fig.suptitle(
                f"Task 5 channel-combination state by {tt_column} {tt_label}\n"
                f"{basename_no_ext_value} · {relation_label_map[relation_type]} · "
                f"{combo_mode_label} · post-filter surviving values only",
                fontsize=11,
                y=0.94,
            )
            if save_plots:
                final_filename = (
                    f"{fig_idx_value}_channel_combination_filter_by_tt_"
                    f"{relation_type}_TT_{tt_label}.png"
                )
                fig_idx_value += 1
                save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
                if plot_list is not None:
                    plot_list.append(save_fig_path)
                save_plot_figure(
                    save_fig_path,
                    fig=fig,
                    format="png",
                    dpi=150,
                    alias="channel_combination_filter_by_tt",
                )
            if show_plots:
                plt.show()
            plt.close(fig)

    return fig_idx_value


def record_filter_metric(name: str, removed: float, total: float) -> None:
    """Record percentage removed for a filter."""
    pct = 0.0 if total == 0 else 100.0 * float(removed) / float(total)
    filter_metrics[name] = round(pct, 4)
    _log_filter_metrics_message(
        f"[filter-metrics] {name}: removed {removed} of {total} ({pct:.2f}%)"
    )


def load_reprocessing_parameters_for_file(station_id: str, task_id: str, basename: str) -> pd.DataFrame:
    """Return matching reprocessing parameters for *basename* or an empty frame."""
    station_str = str(station_id).zfill(2)
    table_path = REFERENCE_TABLES_DIR / f"reprocess_files_station_{station_str}_task_{task_id}.csv"
    if not table_path.exists():
        return pd.DataFrame()
    try:
        table_df = pd.read_csv(table_path)
    except Exception as exc:
        print(f"Warning: unable to read reprocessing table {table_path}: {exc}")
        return pd.DataFrame()
    if "filename_base" not in table_df.columns:
        return pd.DataFrame()
    matches = table_df[table_df["filename_base"] == basename]
    return matches.reset_index(drop=True)



def _preferred_parquet_compression() -> str:
    if pa is not None:
        try:
            if pa.Codec.is_available("snappy"):
                return "snappy"
        except Exception:
            pass
    return "zstd"
# I want to chrono the execution time of the script
start_execution_time_counting = datetime.now()
_prof_t0 = time.perf_counter()
_prof = {}

STATION_CHOICES = ("0", "1", "2", "3", "4")
TASK5_PLOT_ALIASES: tuple[str, ...] = (
    "debug_suite",
    "usual_suite",
    "essential_suite",
    "acquisition_rate_vs_time_by_task_tt_with_histograms",
    "charge_tt_task4_fit_1234_per_plane_and_total",
    "theta_phi_definitive_tt_2d",
    "polar_theta_phi_definitive_tt_2d_detail_pre",
    "polar_theta_phi_definitive_tt_2d_detail_angle_correction",
    "polar_theta_phi_definitive_tt_2d_detail_final",
    "theta_efficiency_simple_3v4",
    "channel_combination_filter_by_tt",
)
task5_plot_status_by_alias: dict[str, str] = {}
CLI_PARSER = build_step1_cli_parser("Run Stage 1 STEP_1 TASK_5 (FIT->CORR).", STATION_CHOICES)
CLI_ARGS = CLI_PARSER.parse_args()
validate_step1_input_file_args(CLI_PARSER, CLI_ARGS)

VERBOSE = bool(os.environ.get("DATAFLOW_VERBOSE")) or CLI_ARGS.verbose
print = build_step1_filtered_print(
    verbose=VERBOSE,
    debug_mode_getter=lambda: bool(globals().get("debug_mode", False)),
    raw_print=builtins.print,
)
FILTER_METRICS_LOGGING_ENABLED = step1_logging_enabled("filter_metrics")[0]
MAX_OPEN_FIGURES = 16
_OPEN_FIGURE_IDS: list[int] = []
_ORIGINAL_PLT_FIGURE = plt.figure
_ORIGINAL_PLT_SUBPLOTS = plt.subplots
_ORIGINAL_PLT_CLOSE = plt.close
plt.figure = _guarded_figure
plt.subplots = _guarded_subplots
plt.close = _guarded_close


# Warning Filters
warnings.filterwarnings("ignore", message=".*Data has no positive values, and therefore cannot be log-scaled.*")

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
task5_plot_status_by_alias = load_step1_task_plot_catalog(
    plot_catalog_file_path,
    TASK5_PLOT_ALIASES,
    "Task 5",
    log_fn=print,
)
debug_mode = False

home_path = str(resolve_home_path_from_config(config))
REFERENCE_TABLES_DIR = get_repo_root() / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS" / "SUPPORT" / "CONFIG_FILES" / "METADATA_REPRISE" / "REFERENCE_TABLES"

# -----------------------------------------------------------------------------
# Stuff that could change between mingos --------------------------------------
# -----------------------------------------------------------------------------

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
    log_fn=print,
)
config["_plot_station_id"] = station
config["_plot_task_number"] = task_number
task5_gate_config_path = Path(config_file_path).with_name(
    str(config.get("gate_config_yaml", TASK5_GATE_CONFIG_DEFAULT_NAME))
)
file_selection_mode = str(config.get("file_selection_mode", "new")).strip().lower()
process_only_qa_retry_files = bool(config.get("process_only_qa_retry_files", False))
joined_analysis_files = coerce_positive_int_config(config.get("joined_analysis_files"), default=1)
joined_analysis_time_tolerance_hours = coerce_nonnegative_float_config(
    config.get("joined_analysis_time_tolerance_hours"),
    default=5.0,
)
if process_only_qa_retry_files:
    print(
        "[QA_ONLY] Enabled by STEP_1 shared config: only files present in the active QA retry list will be processed."
    )

selection_config = load_selection_for_paths(
    [config_file_path],
    master_config_root=config_root,
)
if not station_is_selected(station, selection_config.stations):
    print(f"Station {station} skipped by selection.stations.")
    sys.exit(0)

# Cron job switch that decides if completed files can be revisited.
complete_reanalysis = config.get("complete_reanalysis", False)

selected_input_file = CLI_ARGS.input_file_flag or CLI_ARGS.input_file
if selected_input_file:
    user_file_path = selected_input_file
    user_file_selection = True
    print("User provided file path:", user_file_path)
else:
    user_file_selection = False

repo_root = get_repo_root()
early_metadata_directory = (
    repo_root
    / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
    / f"MINGO0{station}"
    / "STAGE_1"
    / "EVENT_DATA"
    / "STEP_1"
    / f"TASK_{task_number}"
    / "METADATA"
)
early_metadata_directory.mkdir(parents=True, exist_ok=True)
early_status_csv_path = early_metadata_directory / f"task_{task_number}_metadata_status.csv"
selected_file_source = "user" if user_file_selection else ""
selected_source_candidates: list[str] = []
joined_input_records: list[dict[str, str]] = []

if user_file_selection:
    early_status_filename_base = (
        Path(user_file_path).name.replace("fitted_", "").replace(".parquet", "")
    )
else:
    early_status_filename_base = f"__task{task_number}_startup_station_{station}__"
status_filename_base = early_status_filename_base
status_execution_date = initialize_status_row(
    early_status_csv_path,
    filename_base=status_filename_base,
    completion_fraction=0.0,
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
apply_task5_plot_catalog_modes()

print("Creating the necessary directories...")

date_execution = datetime.now().strftime("%y-%m-%d_%H.%M.%S")

# Define base working directory
repo_root = get_repo_root()
home_directory = str(repo_root.parent)
station_directory = str(repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / f"MINGO0{station}")
config_file_directory = str(
    config_root
    / "STAGE_0"
    / "ONLINE_RUN_DICTIONARY"
    / f"STATION_{station}"
)
base_directory = str(repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / f"MINGO0{station}" / "STAGE_1" / "EVENT_DATA")
raw_to_list_working_directory = os.path.join(base_directory, f"STEP_1/TASK_{task_number}")

metadata_directory = os.path.join(raw_to_list_working_directory, "METADATA")

raw_directory = f"STEP_1/TASK_{task_number - 1}/OUTPUT_FILES"
raw_working_directory = os.path.join(base_directory, raw_directory)
output_location = os.path.join(
    base_directory,
    "..",
    "..",
    "STAGE_1_PRODUCTS",
    "EVENT_DATA",
    "PARQUET_LAKE",
)

# Define directory paths relative to base_directory
base_directories = {
    "stratos_list_events_directory": os.path.join(home_directory, "STRATOS_XY_DIRECTORY"),

    "base_plots_directory": os.path.join(raw_to_list_working_directory, "PLOTS"),

    "pdf_directory": os.path.join(raw_to_list_working_directory, "PLOTS/PDF_DIRECTORY"),
    "base_figure_directory": os.path.join(raw_to_list_working_directory, "PLOTS/FIGURE_DIRECTORY"),
    "figure_directory": os.path.join(raw_to_list_working_directory, f"PLOTS/FIGURE_DIRECTORY/FIGURES_EXEC_ON_{date_execution}"),

    "ancillary_directory": os.path.join(raw_to_list_working_directory, "ANCILLARY"),

    "empty_files_directory": os.path.join(raw_to_list_working_directory, "ANCILLARY/EMPTY_FILES"),
    "rejected_files_directory": os.path.join(raw_to_list_working_directory, "ANCILLARY/REJECTED_FILES"),
    "temp_files_directory": os.path.join(raw_to_list_working_directory, "ANCILLARY/TEMP_FILES"),

    "unprocessed_directory": os.path.join(raw_to_list_working_directory, "INPUT_FILES/UNPROCESSED_DIRECTORY"),
    "out_of_date_directory": os.path.join(raw_to_list_working_directory, "INPUT_FILES/OUT_OF_DATE_DIRECTORY"),
    "error_directory": os.path.join(raw_to_list_working_directory, "INPUT_FILES/ERROR_DIRECTORY"),
    "processing_directory": os.path.join(raw_to_list_working_directory, "INPUT_FILES/PROCESSING_DIRECTORY"),
    "completed_directory": os.path.join(raw_to_list_working_directory, "INPUT_FILES/COMPLETED_DIRECTORY"),

    "output_directory": output_location,

    "raw_directory": os.path.join(raw_working_directory, "."),

    "metadata_directory": metadata_directory,
}

# Create ALL directories if they don't already exist

for directory in base_directories.values():
    # Skip figure directories at startup; create lazily after selecting a file.
    if directory in (base_directories["base_figure_directory"], base_directories["figure_directory"]):
        continue
    os.makedirs(directory, exist_ok=True)

debug_plot_directory = os.path.join(
    base_directories["base_plots_directory"],
    "DEBUG_PLOTS",
    f"FIGURES_EXEC_ON_{date_execution}",
)

EXPECTED_INPUT_PREFIX = "fitted_"
EXPECTED_INPUT_EXTENSION = ".parquet"
debug_fig_idx = 1

csv_path = os.path.join(metadata_directory, f"task_{task_number}_metadata_execution.csv")
csv_path_specific = os.path.join(metadata_directory, f"task_{task_number}_metadata_specific.csv")
csv_path_rate_histogram = os.path.join(
    metadata_directory,
    f"task_{task_number}_metadata_rate_histogram.csv",
)
csv_path_trigger_type = os.path.join(
    metadata_directory,
    f"task_{task_number}_metadata_trigger_type.csv",
)
csv_path_filter = os.path.join(metadata_directory, f"task_{task_number}_metadata_filter.csv")
csv_path_deep_fiter = os.path.join(
    metadata_directory,
    f"task_{task_number}_metadata_deep_fiter.csv",
)
csv_path_status = os.path.join(metadata_directory, f"task_{task_number}_metadata_status.csv")
csv_path_profiling = os.path.join(metadata_directory, f"task_{task_number}_metadata_profiling.csv")

# Move files from STAGE_0_TO_1 to STAGE_0_TO_1_TO_LIST/STAGE_0_TO_1_TO_LIST_FILES/UNPROCESSED,
# ensuring that only files not already in UNPROCESSED, PROCESSING,
# or COMPLETED are moved:

raw_directory = base_directories["raw_directory"]
unprocessed_directory = base_directories["unprocessed_directory"]
error_directory = base_directories["error_directory"]
stratos_list_events_directory = base_directories["stratos_list_events_directory"]
processing_directory = base_directories["processing_directory"]
completed_directory = base_directories["completed_directory"]
output_directory = base_directories["output_directory"]

empty_files_directory = base_directories["empty_files_directory"]
rejected_files_directory = base_directories["rejected_files_directory"]
temp_files_directory = base_directories["temp_files_directory"]

_t_sec = time.perf_counter()
print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")
print("----------------- Data reading and preprocessing ---------------------")
print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")

# status_csv_path = os.path.join(base_directory, "raw_to_list_status.csv")
# status_timestamp = append_status_row(status_csv_path)

# Ordered list from highest to lowest priority
LEVELS = [
    completed_directory,
    processing_directory,
    unprocessed_directory,
    raw_directory,
]

station_re = re.compile(r'^mi0(\d).*\.dat$', re.IGNORECASE)

seen = set()
for d in LEVELS:
    d = Path(d)
    if not d.exists():
        continue

    current_files = {p.name for p in d.iterdir() if p.is_file()}

    # ────────────────────────────────────────────────────────────────
    # Remove .dat files whose prefix “mi0X” does not match `station`
    # ────────────────────────────────────────────────────────────────
    mismatched = {
        fname for fname in current_files
        if (m := station_re.match(fname)) and int(m.group(1)) != int(station)
    }
    for fname in mismatched:
        fp = d / fname
        try:
            fp.unlink()
            print(f"Removed wrong-station file: {fp}")
        except FileNotFoundError:
            pass

    current_files -= mismatched

    # ────────────────────────────────────────────────────────────────
    # Remove duplicates lower in the hierarchy
    # ────────────────────────────────────────────────────────────────
    duplicates = current_files & seen
    for fname in duplicates:
        fp = d / fname
        try:
            fp.unlink()
            print(f"Removed duplicate: {fp}")
        except FileNotFoundError:
            pass

    seen |= (current_files - duplicates)

# Search in all this directories for empty files and move them to the empty_files_directory
for directory in [raw_directory, unprocessed_directory, processing_directory, completed_directory]:
    files = os.listdir(directory)
    for file in files:
        file_empty = os.path.join(directory, file)
        if os.path.getsize(file_empty) == 0:
            # Ensure the empty files directory exists
            os.makedirs(empty_files_directory, exist_ok=True)

            # Define the destination path for the file
            empty_destination_path = os.path.join(empty_files_directory, file)

            # Remove the destination file if it already exists
            if os.path.exists(empty_destination_path):
                os.remove(empty_destination_path)

            print("Moving empty file:", file)
            safe_move(file_empty, empty_destination_path)
            now = time.time()
            os.utime(empty_destination_path, (now, now))

# Files to move: in STAGE_0_TO_1 but not in UNPROCESSED, PROCESSING, or COMPLETED
raw_files = set(_expected_input_files(os.listdir(raw_directory)))
unprocessed_files = set(_expected_input_files(os.listdir(unprocessed_directory)))
processing_files = set(_expected_input_files(os.listdir(processing_directory)))
completed_files = set(_expected_input_files(os.listdir(completed_directory)))

files_to_move = raw_files - unprocessed_files - processing_files - completed_files

# Move files to UNPROCESSED ---------------------------------------------------------------
for file_name in files_to_move:
    src_path = os.path.join(raw_directory, file_name)
    dest_path = os.path.join(unprocessed_directory, file_name)
    try:
        safe_move(src_path, dest_path)
        now = time.time()
        os.utime(dest_path, (now, now))
        print(f"Move {file_name} to UNPROCESSED directory.")
    except Exception as e:
        print(f"Failed to move {file_name} to UNPROCESSED: {e}")
        error_dest_path = os.path.join(error_directory, file_name)
        try:
            safe_move(src_path, error_dest_path)
            now = time.time()
            os.utime(error_dest_path, (now, now))
            print(f"Moved {file_name} to ERROR directory after UNPROCESSED move failure.")
        except Exception as error_move_exc:
            raise RuntimeError(
                f"Unable to move {file_name} to either UNPROCESSED or ERROR directory."
            ) from error_move_exc

# Erase all files in the figure_directory -------------------------------------------------
figure_directory = base_directories["figure_directory"]
files = os.listdir(figure_directory) if os.path.exists(figure_directory) else []

if files:  # Check if the directory contains any files
    print("Removing all files in the figure_directory...")
    for file in files:
        os.remove(os.path.join(figure_directory, file))

# Define input file path ------------------------------------------------------------------
input_file_config_path = os.path.join(config_file_directory, f"input_file_mingo0{station}.csv")

if os.path.exists(input_file_config_path):
    print("Searching input configuration file:", input_file_config_path)

    # It is a csv
    try:
        input_file = pd.read_csv(input_file_config_path, skiprows=1)
    except pd.errors.EmptyDataError:
        input_file = pd.DataFrame()
        print("Input configuration file is empty.")

    if not input_file.empty:
        print("Input configuration file found and is not empty.")
        exists_input_file = True
    else:
        print("Input configuration file is empty.")
        exists_input_file = False

    # Print the head
    # print(input_file.head())

else:
    exists_input_file = False
    print("Input configuration file does not exist.")

sync_unprocessed_with_date_range(
    config=config,
    unprocessed_directory=base_directories["unprocessed_directory"],
    out_of_date_directory=base_directories["out_of_date_directory"],
    log_fn=print,
    station_id=station,
    master_config_root=config_root,
)
unprocessed_files = _expected_input_files(os.listdir(base_directories["unprocessed_directory"]))
processing_files = _expected_input_files(os.listdir(base_directories["processing_directory"]))
completed_files = _expected_input_files(os.listdir(base_directories["completed_directory"]))
date_ranges = load_date_ranges_from_config(
    config,
    station_id=station,
    master_config_root=config_root,
)
if date_ranges:
    processing_before = len(processing_files)
    completed_before = len(completed_files)
    processing_files = [
        name
        for name in processing_files
        if file_name_in_any_date_range(name, date_ranges)
    ]
    completed_files = [
        name
        for name in completed_files
        if file_name_in_any_date_range(name, date_ranges)
    ]
    skipped_processing = processing_before - len(processing_files)
    skipped_completed = completed_before - len(completed_files)
    if skipped_processing > 0:
        print(
            f"[DATE_RANGE] Ignoring {skipped_processing} out-of-range file(s) in PROCESSING_DIRECTORY.",
            force=True,
        )
    if skipped_completed > 0:
        print(
            f"[DATE_RANGE] Ignoring {skipped_completed} out-of-range file(s) in COMPLETED_DIRECTORY.",
            force=True,
        )
active_qa_retry_basenames: set[str] = set()
if file_selection_mode == "qa":
    active_qa_retry_basenames = load_active_qa_retry_basenames(
        station,
        repo_root=repo_root,
    )
    qa_unprocessed_files = filter_filenames_by_qa_retry_basenames(
        unprocessed_files, active_qa_retry_basenames
    )
    qa_processing_files = filter_filenames_by_qa_retry_basenames(
        processing_files, active_qa_retry_basenames
    )
    qa_completed_files = filter_filenames_by_qa_retry_basenames(
        completed_files, active_qa_retry_basenames
    )
    if qa_unprocessed_files or qa_processing_files or qa_completed_files:
        unprocessed_files = qa_unprocessed_files
        processing_files = qa_processing_files
        completed_files = qa_completed_files
    print(
        "[FILE_SELECTION] mode=qa; QA candidates are preferred with fallback: "
        f"UNPROCESSED={len(qa_unprocessed_files)} "
        f"PROCESSING={len(qa_processing_files)} "
        f"COMPLETED={len(qa_completed_files)}"
    )
elif process_only_qa_retry_files:
    active_qa_retry_basenames = load_active_qa_retry_basenames(
        station,
        repo_root=repo_root,
    )
    unprocessed_files = filter_filenames_by_qa_retry_basenames(
        unprocessed_files,
        active_qa_retry_basenames,
    )
    processing_files = filter_filenames_by_qa_retry_basenames(
        processing_files,
        active_qa_retry_basenames,
    )
    completed_files = filter_filenames_by_qa_retry_basenames(
        completed_files,
        active_qa_retry_basenames,
    )
    print(
        "[QA_ONLY] Active basenames="
        f"{len(active_qa_retry_basenames)} eligible files: "
        f"UNPROCESSED={len(unprocessed_files)} "
        f"PROCESSING={len(processing_files)} "
        f"COMPLETED={len(completed_files)}"
    )
last_file_test = bool(config.get("last_file_test", False))
keep_all_columns_output = _coerce_config_bool(
    config.get("keep_all_columns_output", False),
    default=False,
)

if user_file_selection:
    processing_file_path = user_file_path
    file_name = os.path.basename(user_file_path)
    if (
        process_only_qa_retry_files
        and canonical_processing_basename(file_name) not in active_qa_retry_basenames
    ):
        sys.exit(
            "[QA_ONLY] The selected input file is not present in the active QA retry list: "
            f"{canonical_processing_basename(file_name)}"
        )
else:
    if last_file_test:
        latest_unprocessed = select_latest_candidate(unprocessed_files, station)
        if latest_unprocessed:
            file_name = latest_unprocessed
            selected_file_source = "unprocessed"
            selected_source_candidates = list(unprocessed_files)
            unprocessed_file_path = os.path.join(base_directories["unprocessed_directory"], file_name)
            processing_file_path = os.path.join(base_directories["processing_directory"], file_name)
            completed_file_path = os.path.join(base_directories["completed_directory"], file_name)

            print(f"Processing the newest file in UNPROCESSED: {unprocessed_file_path}")
            print(f"Moving '{file_name}' to PROCESSING...")
            safe_move(unprocessed_file_path, processing_file_path)
            print(f"File moved to PROCESSING: {processing_file_path}")

        else:
            latest_processing = select_latest_candidate(processing_files, station)
            if latest_processing:
                file_name = latest_processing
                selected_file_source = "processing"
                selected_source_candidates = list(processing_files)
                processing_file_path = os.path.join(base_directories["processing_directory"], file_name)
                completed_file_path = os.path.join(base_directories["completed_directory"], file_name)

                print(f"Processing the newest file already in PROCESSING:\n    {processing_file_path}")
                error_file_path = os.path.join(base_directories["error_directory"], file_name)
                print(f"File '{processing_file_path}' is already in PROCESSING. Moving it temporarily to ERROR for analysis...")
                safe_move(processing_file_path, error_file_path)
                processing_file_path = error_file_path
                print(f"File moved to ERROR: {processing_file_path}")

            elif complete_reanalysis and completed_files:
                latest_completed = select_latest_candidate(completed_files, station)
                if latest_completed:
                    file_name = latest_completed
                    selected_file_source = "completed"
                    selected_source_candidates = list(completed_files)
                    processing_file_path = os.path.join(base_directories["processing_directory"], file_name)
                    completed_file_path = os.path.join(base_directories["completed_directory"], file_name)

                    print(f"Reprocessing the newest file in COMPLETED: {completed_file_path}")
                    print(f"Moving '{completed_file_path}' to PROCESSING...")
                    safe_move(completed_file_path, processing_file_path)
                    print(f"File moved to PROCESSING: {processing_file_path}")
                else:
                    _exit_without_status_row("No files to process in COMPLETED after normalization.")
            else:
                _exit_without_status_row(
                    "No files to process in UNPROCESSED, PROCESSING and decided to not reanalyze COMPLETED."
                )

    else:
        if unprocessed_files:
            print("Selecting a random file in UNPROCESSED...")
            file_name = random.choice(unprocessed_files)
            selected_file_source = "unprocessed"
            selected_source_candidates = list(unprocessed_files)
            unprocessed_file_path = os.path.join(base_directories["unprocessed_directory"], file_name)
            processing_file_path = os.path.join(base_directories["processing_directory"], file_name)
            completed_file_path = os.path.join(base_directories["completed_directory"], file_name)

            print(f"Moving '{file_name}' to PROCESSING...")
            safe_move(unprocessed_file_path, processing_file_path)
            print(f"File moved to PROCESSING: {processing_file_path}")

        elif processing_files:
            print("Selecting a random file in PROCESSING...")
            file_name = random.choice(processing_files)
            selected_file_source = "processing"
            selected_source_candidates = list(processing_files)
            processing_file_path = os.path.join(base_directories["processing_directory"], file_name)
            completed_file_path = os.path.join(base_directories["completed_directory"], file_name)

            print(f"Processing the last file in PROCESSING: {processing_file_path}")
            error_file_path = os.path.join(base_directories["error_directory"], file_name)
            print(f"File '{processing_file_path}' is already in PROCESSING. Moving it temporarily to ERROR for analysis...")
            safe_move(processing_file_path, error_file_path)
            processing_file_path = error_file_path
            print(f"File moved to ERROR: {processing_file_path}")

        elif completed_files:
            if complete_reanalysis:
                print("Selecting a random file in COMPLETED...")
                file_name = random.choice(completed_files)
                selected_file_source = "completed"
                selected_source_candidates = list(completed_files)
                completed_file_path = os.path.join(base_directories["completed_directory"], file_name)
                processing_file_path = os.path.join(base_directories["processing_directory"], file_name)

                print(f"Moving '{file_name}' to PROCESSING...")
                safe_move(completed_file_path, processing_file_path)
                print(f"File moved to PROCESSING: {processing_file_path}")
            else:
                _exit_without_status_row(
                    "No files to process in UNPROCESSED, PROCESSING and decided to not reanalyze COMPLETED."
                )

        else:
            _exit_without_status_row("No files to process in UNPROCESSED, PROCESSING, or COMPLETED.")

joined_input_records = [
    {
        "file_name": file_name,
        "processing_file_path": processing_file_path,
        "completed_file_path": completed_file_path if not user_file_selection else "",
        "basename_no_ext": file_name.replace("fitted_", "").replace(".parquet", ""),
    }
]
if (
    not user_file_selection
    and joined_analysis_files > 1
    and selected_file_source in {"unprocessed", "completed"}
):
    joined_file_names = select_joined_analysis_file_names(
        file_name,
        selected_source_candidates,
        station_id=station,
        max_files=joined_analysis_files,
        tolerance_hours=joined_analysis_time_tolerance_hours,
        selection_order=os.environ.get("DATAFLOW_STEP1_SELECTION_ORDER", "latest"),
        log_fn=print,
    )
    source_directory = (
        base_directories["unprocessed_directory"]
        if selected_file_source == "unprocessed"
        else base_directories["completed_directory"]
    )
    for joined_file_name in joined_file_names:
        if joined_file_name == file_name:
            continue
        joined_source_path = os.path.join(source_directory, joined_file_name)
        joined_processing_path = os.path.join(base_directories["processing_directory"], joined_file_name)
        joined_completed_path = os.path.join(base_directories["completed_directory"], joined_file_name)
        if not os.path.exists(joined_source_path):
            print(f"Warning: joined analysis candidate disappeared before move; skipping {joined_source_path}.")
            continue
        if os.path.exists(joined_processing_path):
            print(f"Warning: joined analysis candidate already exists in PROCESSING; skipping {joined_processing_path}.")
            continue
        print(f"Moving joined analysis file to PROCESSING: {joined_source_path} -> {joined_processing_path}")
        safe_move(joined_source_path, joined_processing_path)
        joined_input_records.append(
            {
                "file_name": joined_file_name,
                "processing_file_path": joined_processing_path,
                "completed_file_path": joined_completed_path,
                "basename_no_ext": joined_file_name.replace("fitted_", "").replace(".parquet", ""),
            }
        )
elif joined_analysis_files > 1:
    print(
        "Joined analysis not expanded for this selection "
        f"(source={selected_file_source or 'unknown'}, user_file_selection={user_file_selection})."
    )

# This is for all cases
file_path = processing_file_path

the_filename = os.path.basename(file_path)
print(f"File to process: {the_filename}")

basename_no_ext, file_extension = os.path.splitext(the_filename)
# Take basename of IN_PATH without extension and witouth the 'listed_' prefix
basename_no_ext = the_filename.replace("fitted_", "").replace(".parquet", "")

print(f"File basename (no extension): {basename_no_ext}")
resolved_status_filename_base = basename_no_ext
if status_execution_date is None:
    status_execution_date = initialize_status_row(
        csv_path_status,
        filename_base=resolved_status_filename_base,
        completion_fraction=0.0,
    )
    status_filename_base = resolved_status_filename_base
elif status_filename_base != resolved_status_filename_base:
    renamed = rename_status_row(
        csv_path_status,
        filename_base=status_filename_base,
        execution_date=status_execution_date,
        new_filename_base=resolved_status_filename_base,
    )
    if renamed:
        status_filename_base = resolved_status_filename_base
    else:
        print(
            "Warning: unable to rename startup status row "
            f"from {status_filename_base} to {resolved_status_filename_base}; creating a new row."
        )
        status_execution_date = initialize_status_row(
            csv_path_status,
            filename_base=resolved_status_filename_base,
            completion_fraction=0.0,
        )
        status_filename_base = resolved_status_filename_base
else:
    status_filename_base = resolved_status_filename_base

simulated_z_positions, simulated_param_hash = resolve_simulated_z_positions(
    basename_no_ext,
    Path(base_directory),
    parquet_path=Path(file_path),
)

analysis_date = datetime.now().strftime("%Y-%m-%d")
print(f"Analysis date and time: {analysis_date}")

# Modify the time of the processing file to the current time so it looks fresh
now = time.time()
if os.path.exists(processing_file_path):
    os.utime(processing_file_path, (now, now))
else:
    print(
        f"Warning: processing file path not found for timestamp refresh: {processing_file_path}"
    )

# Check the station number in the datafile
file_station_number = infer_station_number_from_processing_name(basename_no_ext)
if file_station_number is None:
    sys.exit(f"Invalid station number in file '{file_name}'. Exiting.")
if file_station_number != int(station):
    print(f'File station number is: {file_station_number}, it does not match.')
    # Move the file to the ERROR directory
    error_file_path = os.path.join(base_directories["error_directory"], file_name)
    print(f"Moving file '{file_name}' to ERROR directory: {error_file_path}")
    process_file(file_path, error_file_path)
    sys.exit(f"File '{file_name}' does not belong to station {station}. Exiting.")

if status_execution_date is not None:
    update_status_progress(
        csv_path_status,
        filename_base=status_filename_base,
        execution_date=status_execution_date,
        completion_fraction=0.25,
        param_hash=str(simulated_param_hash) if simulated_param_hash else "",
    )

left_limit_time = pd.to_datetime("1-1-2000", format='%d-%m-%Y')
right_limit_time = pd.to_datetime("1-1-2100", format='%d-%m-%Y')

# if limit:
#     print(f'Taking the first {limit_number} rows.')

# Read the data file into a DataFrame
KEY = "df"

# Load dataframe(s)
joined_source_file_column = "__task5_joined_source_file__"
joined_source_basename_column = "__task5_joined_source_basename__"
joined_frames: list[pd.DataFrame] = []
for joined_record in joined_input_records:
    joined_path = joined_record["processing_file_path"]
    joined_frame = pd.read_parquet(joined_path, engine="pyarrow")
    joined_frame = joined_frame.rename(columns=lambda col: col.replace("_diff_", "_dif_"))
    joined_frame = canonicalize_step1_columns(joined_frame)
    joined_frame = _ensure_task5_internal_event_aliases(joined_frame)
    if "event_id" not in joined_frame.columns:
        print(
            "Warning: 'event_id' missing in Task 5 input; reconstructing from "
            f"current row order for {joined_record['file_name']}."
        )
        joined_frame.insert(0, "event_id", np.arange(len(joined_frame), dtype=np.int64))
    event_charge_series, event_charge_source = resolve_event_charge_series(
        joined_frame,
        station_root=station_directory,
        basename_no_ext=joined_record["basename_no_ext"],
    )
    if event_charge_series is not None:
        joined_frame["event_charge"] = event_charge_series
        print(f"Recovered event_charge for TASK_5 using: {event_charge_source}")
    else:
        print(f"[WARN] event_charge could not be reconstructed in TASK_5 for {joined_record['file_name']}.")
    joined_frame.loc[:, joined_source_file_column] = joined_record["file_name"]
    joined_frame.loc[:, joined_source_basename_column] = joined_record["basename_no_ext"]
    joined_frames.append(joined_frame)
    print(f"Fitted dataframe reloaded from: {joined_path} rows={len(joined_frame)}")
if not joined_frames:
    sys.exit("No Task 5 input dataframes were loaded.")
working_df = pd.concat(joined_frames, ignore_index=True, sort=False)
joined_analysis_active = len(joined_input_records) > 1
if joined_analysis_active:
    print(
        "Joined analysis active: "
        f"files={len(joined_input_records)} total_rows={len(working_df)} primary={file_name}"
    )
else:
    working_df = working_df.drop(
        columns=[joined_source_file_column, joined_source_basename_column],
        errors="ignore",
    )
# Ensure param_hash is persisted for downstream tasks.
if "param_hash" not in working_df.columns:
    working_df["param_hash"] = str(simulated_param_hash) if simulated_param_hash else ""
elif simulated_param_hash:
    param_series = working_df["param_hash"]
    missing_hash = param_series.isna()
    try:
        missing_hash |= param_series.astype(str).str.strip().eq("")
    except Exception as exc:
        print(f"Warning: param_hash validation fallback used due to error: {exc}")
    if missing_hash.any():
        working_df.loc[missing_hash, "param_hash"] = str(simulated_param_hash)
if not simulated_param_hash and "param_hash" in working_df.columns:
    try:
        recovered_param_hash_series = working_df["param_hash"].astype(str).str.strip()
        recovered_param_hash_series = recovered_param_hash_series[recovered_param_hash_series.ne("")]
    except Exception as exc:
        print(f"Warning: unable to inspect parquet param_hash column after load: {exc}")
        recovered_param_hash_series = pd.Series(dtype=str)
    if not recovered_param_hash_series.empty:
        recovered_param_hash = recovered_param_hash_series.iloc[0]
        simulated_z_positions, simulated_param_hash = resolve_simulated_z_positions(
            basename_no_ext,
            Path(base_directory),
            param_hash=recovered_param_hash,
        )
        if simulated_param_hash:
            print(f"Recovered simulated param_hash from parquet column: {simulated_param_hash}")

task5_gate_definitions = _load_task5_gate_config(task5_gate_config_path)
print(f"Loaded {len(task5_gate_definitions)} Task 5 gate definition(s) from {task5_gate_config_path}")
working_df = add_task5_strip_topology_gate_columns(working_df)
working_df = apply_task5_gates(working_df, task5_gate_definitions)
working_df.drop(columns=list(TASK5_TOPOLOGY_GATE_COLUMNS), inplace=True)
# print("Columns loaded from parquet:")
# for col in working_df.columns:
#     print(f" - {col}")

if create_debug_plots:
    main_cols: list[str] = []
    for i_plane in range(1, 5):
        main_cols.extend(
            [
                f"p{i_plane}_tsum",
                f"p{i_plane}_tdif",
                f"p{i_plane}_qsum",
                f"p{i_plane}_qdif",
                f"p{i_plane}_ypos",
            ]
        )
    main_cols.extend(
        [
            col
            for col in ("tt_task0_raw", "tt_task1_clean", "tt_task2_cal", "tt_task3_list", "tt_task4_fit", POST_TT_COLUMN)
            if col in working_df.columns
        ]
    )
    main_cols = [col for col in main_cols if col in working_df.columns]
    if main_cols:
        debug_fig_idx = plot_debug_histograms(
            working_df,
            main_cols,
            thresholds=None,
            title=f"Task 5 incoming parquet: main columns [NON-TUNABLE] (station {station})",
            out_dir=debug_plot_directory,
            fig_idx=debug_fig_idx,
            max_cols_per_fig=20,
        )
tt_task4_fit_columns = {
    i_plane: [
        f"p{i_plane}_tsum",
        f"p{i_plane}_tdif",
        f"p{i_plane}_qsum",
        f"p{i_plane}_qdif",
        f"p{i_plane}_ypos",
    ]
    for i_plane in range(1, 5)
}

global_variables = {
    "joined_analysis_files_requested": int(joined_analysis_files),
    "joined_analysis_files_used": int(len(joined_input_records)),
    "joined_analysis_time_tolerance_hours": float(joined_analysis_time_tolerance_hours),
}

TT_COUNT_VALUES: tuple[int, ...] = (
    0, 1, 2, 3, 4, 12, 13, 14, 23, 24, 34, 123, 124, 134, 234, 1234
)

TASK5_CHANNEL_COMBINATION_RELATION_TYPES: tuple[str, ...] = (
    "self",
    "same_strip",
    "same_plane",
    "any",
)
TASK5_CHANNEL_COMBINATION_OBSERVABLES: tuple[tuple[str, str], ...] = (
    ("q_sum", "Q semisum"),
    ("q_dif", "Q semidifference"),
    ("t_sum", "T semisum"),
    ("t_dif", "T semidifference"),
)
TASK5_CHANNEL_COMBINATION_SCATTER_MAX_POINTS = 5000
if simulated_param_hash:
    global_variables["param_hash"] = simulated_param_hash

FILTER_METRIC_NAMES: tuple[str, ...] = (
    "total_rows_removed_pct",
    "data_purity_percentage",
    "all_components_zero_rows_removed_pct",
    "tt_task5_post_lt_10_rows_removed_pct",
)

filter_metrics: dict[str, float] = {}
# Keep tt_task4_fit from Task 4 when present; compute only if missing.
if "tt_task4_fit" not in working_df.columns:
    working_df = compute_tt(working_df, "tt_task4_fit", tt_task4_fit_columns)
else:
    working_df.loc[:, "tt_task4_fit"] = (
        pd.to_numeric(working_df["tt_task4_fit"], errors="coerce")
        .fillna(0)
        .astype(int)
    )

tt_task4_fit_counts_initial = working_df["tt_task4_fit"].value_counts()
for tt_value, count in tt_task4_fit_counts_initial.items():
    tt_label = normalize_tt_label(tt_value)
    global_variables[f"tt_task4_fit_{tt_label}_count"] = int(count)

working_df.loc[:, POST_TT_COLUMN] = (
    pd.to_numeric(working_df["tt_task4_fit"], errors="coerce")
    .fillna(0)
    .astype(int)
)

tt_task5_post_counts_initial = working_df[POST_TT_COLUMN].value_counts()
for tt_value, count in tt_task5_post_counts_initial.items():
    tt_label = normalize_tt_label(tt_value)
    global_variables[f"{POST_TT_COLUMN}_{tt_label}_count"] = int(count)

fig_idx, plot_list = ensure_plot_state(globals())
if task5_plot_enabled("channel_combination_filter_by_tt"):
    print("----------- Task 1 channel-combination audit in Task 5 ------------")
    fig_idx = plot_task5_channel_combination_filter_by_tt(
        working_df,
        basename_no_ext,
        fig_idx,
        show_plots=show_plots,
        save_plots=save_plots,
        plot_list=plot_list,
    )


# ------------
# DECIDED TO KEEP datetime
# ------------
# Change 'Time' column to 'datetime' ------------------------------------------
# if 'Time' in working_df.columns:
#     working_df.rename(columns={'Time': 'datetime'}, inplace=True)
# else:
#     print("Column 'datetime' not found in DataFrame!")

# Original number of events
original_number_of_events = len(working_df)
if status_execution_date is not None:
    update_status_progress(
        csv_path_status,
        filename_base=status_filename_base,
        execution_date=status_execution_date,
        completion_fraction=0.5,
        param_hash=str(global_variables.get("param_hash", "")),
    )

# Round execution time to seconds and format it in YYYY-MM-DD_HH.MM.SS
execution_time = str(start_execution_time_counting).split('.')[0]  # Remove microseconds
print("Execution time is:", execution_time)

ITINERARY_FILE_PATH = (
    repo_root
    / "PIPELINE" / "MINGO_ANALYSIS"
    / "MINGO_ANALYSIS_SCRIPTS"
    / "ANCILLARY"
    / "CALIBRATIONS_AND_LUTS"
    / "TIME_CALIBRATION_ITINERARIES"
    / "itineraries.csv"
)

fast_mode = False
debug_mode = False
last_file_test = config["last_file_test"]

# Accessing all the variables from the configuration
(
    plot_mode,
    create_plots,
    create_essential_plots,
    save_plots,
    create_pdf,
    show_plots,
    create_debug_plots,
) = resolve_step1_plot_options(config)
apply_task5_plot_catalog_modes()

# Charge calibration to fC

# Charge front-back

# Slewing correction

# Y position

# RPC variables

# Alternative

# TimTrack

# Validation

# Pre-cal Front & Back
T_side_left_pre_cal_debug = config.get("T_side_left_pre_cal_debug", -500)
T_side_right_pre_cal_debug = config.get("T_side_right_pre_cal_debug", 500)

T_side_left_pre_cal_default = config.get("T_side_left_pre_cal_default", -200)
T_side_right_pre_cal_default = config.get("T_side_right_pre_cal_default", -100)

T_side_left_pre_cal_ST = config.get("T_side_left_pre_cal_ST", -200)
T_side_right_pre_cal_ST = config.get("T_side_right_pre_cal_ST", -50)

# Pre-cal Sum & Diff

# Post-calibration

# Once calculated the RPC variables
T_sum_RPC_left = _task5_config_float(
    config,
    "T_sum_RPC_left",
    "plane_combination_plane_t_sum_sum_left",
    "plane_combination_same_plane_t_sum_sum_left",
    "plane_combination_self_t_sum_sum_left",
    default=-25.0,
)
T_sum_RPC_right = _task5_config_float(
    config,
    "T_sum_RPC_right",
    "plane_combination_plane_t_sum_sum_right",
    "plane_combination_same_plane_t_sum_sum_right",
    "plane_combination_self_t_sum_sum_right",
    default=25.0,
)

# Alternative fitter filter
det_pos_filter = config["det_pos_filter"]
det_theta_left_filter = config["det_theta_left_filter"]
det_theta_right_filter = config["det_theta_right_filter"]
det_phi_filter_abs = abs(float(config.get("det_phi_filter_abs", config.get("det_phi_right_filter", 3.141592))))
det_phi_right_filter = det_phi_filter_abs
det_phi_left_filter = -det_phi_filter_abs
det_slowness_filter_left = config["det_slowness_filter_left"]
det_slowness_filter_right = config["det_slowness_filter_right"]

# TimTrack filter

# Fitting comparison

# Calibrations

# Pedestal charge calibration

# Front-back charge

# Variables to modify
beta = config.get("beta", 1)
strip_speed_factor_of_c = config.get("strip_speed_factor_of_c", 0.666666667)

# X
strip_length = config.get("strip_length", 300)
narrow_strip = config.get("narrow_strip", 63)
wide_strip = config.get("wide_strip", 98)

# Timtrack parameters
anc_std = config.get("anc_std", 0.075)

n_planes_timtrack = config.get("n_planes_timtrack", 4)

# Plotting options
T_clip_min_debug = config.get("T_clip_min_debug", -500)
T_clip_max_debug = config.get("T_clip_max_debug", 500)
Q_clip_min_debug = config.get("Q_clip_min_debug", -500)
Q_clip_max_debug = config.get("Q_clip_max_debug", 500)
num_bins_debug = config.get("num_bins_debug", 100)

T_clip_min_default = config.get("T_clip_min_default", -300)
T_clip_max_default = config.get("T_clip_max_default", 100)
Q_clip_min_default = config.get("Q_clip_min_default", 0)
Q_clip_max_default = config.get("Q_clip_max_default", 500)
num_bins_default = config.get("num_bins_default", 100)

T_clip_min_ST = config.get("T_clip_min_ST", -300)
T_clip_max_ST = config.get("T_clip_max_ST", 100)
Q_clip_min_ST = config.get("Q_clip_min_ST", 0)
Q_clip_max_ST = config.get("Q_clip_max_ST", 500)

# -----------------------------------------------------------------------------
# Some variables that define the analysis, define a dictionary with the variables:
# 'purity_of_data', etc.
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Variables to not touch unless necessary -------------------------------------
# -----------------------------------------------------------------------------
Q_sum_color = 'orange'
Q_dif_color = 'red'
T_sum_color = 'blue'
T_dif_color = 'green'

pos_filter = det_pos_filter
t0_left_filter = T_sum_RPC_left
t0_right_filter = T_sum_RPC_right
slowness_filter_left = det_slowness_filter_left
slowness_filter_right = det_slowness_filter_right

theta_left_filter = det_theta_left_filter
theta_right_filter = det_theta_right_filter
phi_left_filter = det_phi_left_filter
phi_right_filter = det_phi_right_filter

if create_debug_plots:
    def _emit_param_debug(param_label, columns, thresholds, y_scale="log"):
        cols_present = [col for col in columns if col in working_df.columns]
        if not cols_present:
            return
        debug_thresholds = {col: thresholds for col in cols_present}
        cols_present.sort()
        global debug_fig_idx
        debug_fig_idx = plot_debug_histograms(
            working_df,
            cols_present,
            debug_thresholds,
            title=f"Task 5 pre-filter: {param_label} [tunable] (station {station})",
            out_dir=debug_plot_directory,
            fig_idx=debug_fig_idx,
            y_scale=y_scale,
        )

    _emit_param_debug(
        "det_pos_filter",
        ["det_x", "det_y", "x", "y"],
        [-det_pos_filter, det_pos_filter],
    )
    _emit_param_debug(
        "slowness_filter_left/right",
        ["det_s", "s"],
        [slowness_filter_left, slowness_filter_right],
    )
    _emit_param_debug(
        "theta_left/right_filter",
        ["det_theta", "theta"],
        [theta_left_filter, theta_right_filter],
        y_scale="linear",
    )
    _emit_param_debug(
        "phi_left/right_filter",
        ["det_phi", "phi"],
        [phi_left_filter, phi_right_filter],
    )
    _emit_param_debug(
        "t0_left/right_filter",
        ["t0", "det_t0", "tim_t0"],
        [t0_left_filter, t0_right_filter],
    )

fig_idx, plot_list = ensure_plot_state(globals())



T_F_left_pre_cal = T_side_left_pre_cal_default  #-130
T_F_right_pre_cal = T_side_right_pre_cal_default

T_B_left_pre_cal = T_side_left_pre_cal_default
T_B_right_pre_cal = T_side_right_pre_cal_default

T_F_left_pre_cal_ST = T_side_left_pre_cal_ST  #-115
T_F_right_pre_cal_ST = T_side_right_pre_cal_ST
T_B_left_pre_cal_ST = T_side_left_pre_cal_ST
T_B_right_pre_cal_ST = T_side_right_pre_cal_ST

# Y ---------------------------------------------------------------------------
y_widths = [np.array([wide_strip, wide_strip, wide_strip, narrow_strip]),
            np.array([narrow_strip, wide_strip, wide_strip, wide_strip])]

y_pos_T = [y_pos(y_widths[0]), y_pos(y_widths[1])]
y_width_P1_and_P3 = y_widths[0]
y_width_P2_and_P4 = y_widths[1]
y_pos_P1_and_P3 = y_pos(y_width_P1_and_P3)
y_pos_P2_and_P4 = y_pos(y_width_P2_and_P4)
total_width = np.sum(y_width_P1_and_P3)

c_mm_ns = c/1000000
print(c_mm_ns)

# Miscelanous ----------------------------
muon_speed = beta * c_mm_ns
strip_speed = strip_speed_factor_of_c * c_mm_ns # 200 mm/ns
tdiff_to_x = strip_speed # Factor to transform t_diff to X

# Not-Hardcoded
vc    = beta * c_mm_ns # mm/ns
sc    = 1/vc
ss    = 1/strip_speed # slowness of the signal in the strip
nplan = n_planes_timtrack
lenx  = strip_length
anc_sx = tdiff_to_x * anc_std # 2 cm

T_clip_min = T_clip_min_default
T_clip_max = T_clip_max_default
Q_clip_min = Q_clip_min_default
Q_clip_max = Q_clip_max_default
num_bins = num_bins_default

T_clip_min_ST = T_clip_min_ST
T_clip_max_ST = T_clip_max_ST
Q_clip_min_ST = Q_clip_min_ST
Q_clip_max_ST = Q_clip_max_ST

self_trigger = bool(config.get("self_trigger", False))

fast_mode = False
debug_mode = False
last_file_test = config["last_file_test"]

# Accessing all the variables from the configuration
(
    plot_mode,
    create_plots,
    create_essential_plots,
    save_plots,
    create_pdf,
    show_plots,
    create_debug_plots,
) = resolve_step1_plot_options(config)
apply_task5_plot_catalog_modes()

# Charge calibration to fC

# Charge front-back

# Slewing correction

# Y position

# RPC variables

# Alternative

# TimTrack

# Validation

# Pre-cal Front & Back
T_side_left_pre_cal_debug = config.get("T_side_left_pre_cal_debug", -500)
T_side_right_pre_cal_debug = config.get("T_side_right_pre_cal_debug", 500)

T_side_left_pre_cal_default = config.get("T_side_left_pre_cal_default", -200)
T_side_right_pre_cal_default = config.get("T_side_right_pre_cal_default", -100)

T_side_left_pre_cal_ST = config.get("T_side_left_pre_cal_ST", -200)
T_side_right_pre_cal_ST = config.get("T_side_right_pre_cal_ST", -50)

# Pre-cal Sum & Diff

# Post-calibration

# Once calculated the RPC variables
T_sum_RPC_left = _task5_config_float(
    config,
    "T_sum_RPC_left",
    "plane_combination_plane_t_sum_sum_left",
    "plane_combination_same_plane_t_sum_sum_left",
    "plane_combination_self_t_sum_sum_left",
    default=-25.0,
)
T_sum_RPC_right = _task5_config_float(
    config,
    "T_sum_RPC_right",
    "plane_combination_plane_t_sum_sum_right",
    "plane_combination_same_plane_t_sum_sum_right",
    "plane_combination_self_t_sum_sum_right",
    default=25.0,
)

# Alternative fitter filter
det_pos_filter = config["det_pos_filter"]
det_theta_left_filter = config["det_theta_left_filter"]
det_theta_right_filter = config["det_theta_right_filter"]
det_phi_filter_abs = abs(float(config.get("det_phi_filter_abs", config.get("det_phi_right_filter", 3.141592))))
det_phi_right_filter = det_phi_filter_abs
det_phi_left_filter = -det_phi_filter_abs
det_slowness_filter_left = config["det_slowness_filter_left"]
det_slowness_filter_right = config["det_slowness_filter_right"]

# TimTrack filter

# Fitting comparison

# Calibrations

# Pedestal charge calibration

# Front-back charge

# Variables to modify
beta = config.get("beta", 1)
strip_speed_factor_of_c = config.get("strip_speed_factor_of_c", 0.666666667)

# X
strip_length = config.get("strip_length", 300)
narrow_strip = config.get("narrow_strip", 63)
wide_strip = config.get("wide_strip", 98)

# Timtrack parameters
anc_std = config.get("anc_std", 0.075)

n_planes_timtrack = config.get("n_planes_timtrack", 4)

# Plotting options
T_clip_min_debug = config.get("T_clip_min_debug", -500)
T_clip_max_debug = config.get("T_clip_max_debug", 500)
Q_clip_min_debug = config.get("Q_clip_min_debug", -500)
Q_clip_max_debug = config.get("Q_clip_max_debug", 500)
num_bins_debug = config.get("num_bins_debug", 100)

T_clip_min_default = config.get("T_clip_min_default", -300)
T_clip_max_default = config.get("T_clip_max_default", 100)
Q_clip_min_default = config.get("Q_clip_min_default", 0)
Q_clip_max_default = config.get("Q_clip_max_default", 500)
num_bins_default = config.get("num_bins_default", 100)

T_clip_min_ST = config.get("T_clip_min_ST", -300)
T_clip_max_ST = config.get("T_clip_max_ST", 100)
Q_clip_min_ST = config.get("Q_clip_min_ST", 0)
Q_clip_max_ST = config.get("Q_clip_max_ST", 500)

# -----------------------------------------------------------------------------
# Some variables that define the analysis, define a dictionary with the variables:
# 'purity_of_data', etc.
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Variables to not touch unless necessary -------------------------------------
# -----------------------------------------------------------------------------
Q_sum_color = 'orange'
Q_dif_color = 'red'
T_sum_color = 'blue'
T_dif_color = 'green'

pos_filter = det_pos_filter
t0_left_filter = T_sum_RPC_left
t0_right_filter = T_sum_RPC_right
slowness_filter_left = det_slowness_filter_left
slowness_filter_right = det_slowness_filter_right

theta_left_filter = det_theta_left_filter
theta_right_filter = det_theta_right_filter
phi_left_filter = det_phi_left_filter
phi_right_filter = det_phi_right_filter

fig_idx, plot_list = ensure_plot_state(globals())



T_F_left_pre_cal = T_side_left_pre_cal_default  #-130
T_F_right_pre_cal = T_side_right_pre_cal_default

T_B_left_pre_cal = T_side_left_pre_cal_default
T_B_right_pre_cal = T_side_right_pre_cal_default

T_F_left_pre_cal_ST = T_side_left_pre_cal_ST  #-115
T_F_right_pre_cal_ST = T_side_right_pre_cal_ST
T_B_left_pre_cal_ST = T_side_left_pre_cal_ST
T_B_right_pre_cal_ST = T_side_right_pre_cal_ST

# Y ---------------------------------------------------------------------------
y_widths = [np.array([wide_strip, wide_strip, wide_strip, narrow_strip]),
            np.array([narrow_strip, wide_strip, wide_strip, wide_strip])]

y_pos_T = [y_pos(y_widths[0]), y_pos(y_widths[1])]
y_width_P1_and_P3 = y_widths[0]
y_width_P2_and_P4 = y_widths[1]
y_pos_P1_and_P3 = y_pos(y_width_P1_and_P3)
y_pos_P2_and_P4 = y_pos(y_width_P2_and_P4)
total_width = np.sum(y_width_P1_and_P3)

c_mm_ns = c/1000000
print(c_mm_ns)

# Miscelanous ----------------------------
muon_speed = beta * c_mm_ns
strip_speed = strip_speed_factor_of_c * c_mm_ns # 200 mm/ns
tdiff_to_x = strip_speed # Factor to transform t_diff to X

# Not-Hardcoded
vc    = beta * c_mm_ns # mm/ns
sc    = 1/vc
ss    = 1/strip_speed # slowness of the signal in the strip
nplan = n_planes_timtrack
lenx  = strip_length
anc_sx = tdiff_to_x * anc_std # 2 cm

T_clip_min = T_clip_min_default
T_clip_max = T_clip_max_default
Q_clip_min = Q_clip_min_default
Q_clip_max = Q_clip_max_default
num_bins = num_bins_default

T_clip_min_ST = T_clip_min_ST
T_clip_max_ST = T_clip_max_ST
Q_clip_min_ST = Q_clip_min_ST
Q_clip_max_ST = Q_clip_max_ST

# -----------------------------------------------------------------------------
# Stuff that could change between mingos --------------------------------------
# -----------------------------------------------------------------------------

# Note that the middle between start and end time could also be taken. This is for calibration storage.
if "datetime" in working_df.columns:
    datetime_series = pd.to_datetime(working_df["datetime"], errors="coerce").dropna()
else:
    datetime_series = pd.Series(dtype="datetime64[ns]")
if datetime_series.empty:
    print(
        f"Warning: No valid datetime rows found in {the_filename}; moving file to ERROR and skipping."
    )
    if not user_file_selection:
        error_file_path = os.path.join(base_directories["error_directory"], the_filename)
        print(f"Moving file '{the_filename}' to ERROR directory: {error_file_path}")
        process_file(file_path, error_file_path)
    if status_execution_date is not None:
        update_status_progress(
            csv_path_status,
            filename_base=status_filename_base,
            execution_date=status_execution_date,
            completion_fraction=1.0,
            param_hash=str(global_variables.get("param_hash", "")),
        )
    sys.exit(0)

datetime_value = datetime_series.iloc[0]
end_datetime_value = datetime_series.iloc[-1]

if self_trigger:
    print(self_trigger_df)
    if "datetime" in self_trigger_df.columns:
        datetime_series_st = pd.to_datetime(self_trigger_df["datetime"], errors="coerce").dropna()
    else:
        datetime_series_st = pd.Series(dtype="datetime64[ns]")
    if datetime_series_st.empty:
        print("Warning: Self-trigger dataframe has no valid datetime values; skipping self-trigger timestamp suffix.")
    else:
        datetime_value_st = datetime_series_st.iloc[0]
        end_datetime_value_st = datetime_series_st.iloc[-1]
        datetime_str_st = str(datetime_value_st)
        save_filename_suffix_st = datetime_str_st.replace(' ', "_").replace(':', ".").replace('-', ".")

start_time = datetime_value
end_time = end_datetime_value
datetime_str = str(datetime_value)
save_filename_suffix = datetime_str.replace(' ', "_").replace(':', ".").replace('-', ".")

_prof["s_data_read_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()
print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")
print(f"------------- Starting date is {save_filename_suffix} -------------------") # This is longer so it displays nicely
print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")

# Defining the directories that will store the data
save_full_filename = f"full_list_events_{save_filename_suffix}.txt"
save_filename = f"list_events_{save_filename_suffix}.txt"
save_pdf_filename = f"mingo{str(station).zfill(2)}_task5_{basename_no_ext}_{date_execution}.pdf"

save_pdf_path = os.path.join(base_directories["pdf_directory"], save_pdf_filename)

fig_idx, plot_list = ensure_plot_state(globals())
# FINAL plot block moved out of the runtime flow: charge_tt_task4_fit_1234_per_plane_and_total
pass

reprocessing_parameters = pd.DataFrame()

# -------------------------------------------------------------------------------
# ------------ Input file and data managing to select configuration -------------
# -------------------------------------------------------------------------------

is_simulated_file = basename_no_ext.startswith("mi00")
used_input_file = False

if simulated_z_positions is not None:
    z_positions = np.array(simulated_z_positions, dtype=float)
    found_matching_conf = True
    print(f"Using simulated z_positions from param_hash={simulated_param_hash}")
elif is_simulated_file:
    print("Warning: Simulated file missing param_hash; using default z_positions.")
    found_matching_conf = False
    z_positions = np.array([0, 150, 300, 450])  # In mm
elif exists_input_file:
    used_input_file = True
    selection_result = select_input_file_configuration(
        input_file,
        start_time=start_time,
        end_time=end_time,
    )
    print(selection_result.matching_confs)

    if selection_result.selected_conf is not None:
        if selection_result.reason == "exact_overlap_latest_start":
            print(
                "Warning:\n"
                "Multiple configurations match the date range\n"
                f"{start_time} to {end_time}.\n"
                "Selecting the matching configuration with the most recent start date."
            )
        elif selection_result.reason != "exact":
            print("Warning: No matching configuration for the date range; selecting closest configuration.")
        selected_conf = selection_result.selected_conf
        print(f"Selected configuration: {selected_conf['conf']}")
        z_positions = np.array([selected_conf.get(f"P{i}", np.nan) for i in range(1, 5)])
        found_matching_conf = True
        print(selected_conf['conf'])
    else:
        print("Warning: Input configuration file has no valid selectable rows. Using default z_positions.")
        z_positions = np.array([0, 150, 300, 450])  # In mm
else:
    print("Error: No input file. Using default z_positions.")
    z_positions = np.array([0, 150, 300, 450])  # In mm

# If any of the z_positions is NaN, use default values
if np.isnan(z_positions).any():
    print("Error: Incomplete z_positions in the selected configuration. Using default z_positions.")
    z_positions = np.array([0, 150, 300, 450])  # In mm

# Print the resulting z_positions
z_positions = z_positions - z_positions[0]
print(f"Z positions: {z_positions}")

# Save the z_positions in the metadata file
global_variables['z_p1'] =  z_positions[0]
global_variables['z_p2'] =  z_positions[1]
global_variables['z_p3'] =  z_positions[2]
global_variables['z_p4'] =  z_positions[3]

fast_mode = False
debug_mode = False
last_file_test = config["last_file_test"]

# Accessing all the variables from the configuration
(
    plot_mode,
    create_plots,
    create_essential_plots,
    save_plots,
    create_pdf,
    show_plots,
    create_debug_plots,
) = resolve_step1_plot_options(config)
apply_task5_plot_catalog_modes()

# Charge calibration to fC

# Charge front-back

# Slewing correction

# Y position

# RPC variables

# Alternative

# TimTrack

# Validation

# Pre-cal Front & Back
T_side_left_pre_cal_debug = config.get("T_side_left_pre_cal_debug", -500)
T_side_right_pre_cal_debug = config.get("T_side_right_pre_cal_debug", 500)

T_side_left_pre_cal_default = config.get("T_side_left_pre_cal_default", -200)
T_side_right_pre_cal_default = config.get("T_side_right_pre_cal_default", -100)

T_side_left_pre_cal_ST = config.get("T_side_left_pre_cal_ST", -200)
T_side_right_pre_cal_ST = config.get("T_side_right_pre_cal_ST", -50)

# Pre-cal Sum & Diff

# Post-calibration

# Once calculated the RPC variables
T_sum_RPC_left = _task5_config_float(
    config,
    "T_sum_RPC_left",
    "plane_combination_plane_t_sum_sum_left",
    "plane_combination_same_plane_t_sum_sum_left",
    "plane_combination_self_t_sum_sum_left",
    default=-25.0,
)
T_sum_RPC_right = _task5_config_float(
    config,
    "T_sum_RPC_right",
    "plane_combination_plane_t_sum_sum_right",
    "plane_combination_same_plane_t_sum_sum_right",
    "plane_combination_self_t_sum_sum_right",
    default=25.0,
)

# Alternative fitter filter
det_pos_filter = config["det_pos_filter"]
det_theta_left_filter = config["det_theta_left_filter"]
det_theta_right_filter = config["det_theta_right_filter"]
det_phi_filter_abs = abs(float(config.get("det_phi_filter_abs", config.get("det_phi_right_filter", 3.141592))))
det_phi_right_filter = det_phi_filter_abs
det_phi_left_filter = -det_phi_filter_abs
det_slowness_filter_left = config["det_slowness_filter_left"]
det_slowness_filter_right = config["det_slowness_filter_right"]

# TimTrack filter

# Fitting comparison

# Calibrations

# Pedestal charge calibration

# Front-back charge

# Variables to modify
beta = config.get("beta", 1)
strip_speed_factor_of_c = config.get("strip_speed_factor_of_c", 0.666666667)

# X
strip_length = config.get("strip_length", 300)
narrow_strip = config.get("narrow_strip", 63)
wide_strip = config.get("wide_strip", 98)

# Timtrack parameters
anc_std = config.get("anc_std", 0.075)

n_planes_timtrack = config.get("n_planes_timtrack", 4)

# Plotting options
T_clip_min_debug = config.get("T_clip_min_debug", -500)
T_clip_max_debug = config.get("T_clip_max_debug", 500)
Q_clip_min_debug = config.get("Q_clip_min_debug", -500)
Q_clip_max_debug = config.get("Q_clip_max_debug", 500)
num_bins_debug = config.get("num_bins_debug", 100)

T_clip_min_default = config.get("T_clip_min_default", -300)
T_clip_max_default = config.get("T_clip_max_default", 100)
Q_clip_min_default = config.get("Q_clip_min_default", 0)
Q_clip_max_default = config.get("Q_clip_max_default", 500)
num_bins_default = config.get("num_bins_default", 100)

T_clip_min_ST = config.get("T_clip_min_ST", -300)
T_clip_max_ST = config.get("T_clip_max_ST", 100)
Q_clip_min_ST = config.get("Q_clip_min_ST", 0)
Q_clip_max_ST = config.get("Q_clip_max_ST", 500)

config_files_directory = str(resolve_master_config_root_from_config(config))

angular_corr_directory = (
    config_files_directory + "/STAGE_1/EVENT_DATA/STEP_1/TASK_5/ANGULAR_CORRECTION"
)

# -----------------------------------------------------------------------------
# Some variables that define the analysis, define a dictionary with the variables:
# 'purity_of_data', etc.


T_F_left_pre_cal = T_side_left_pre_cal_default  #-130
T_F_right_pre_cal = T_side_right_pre_cal_default

T_B_left_pre_cal = T_side_left_pre_cal_default
T_B_right_pre_cal = T_side_right_pre_cal_default

T_F_left_pre_cal_ST = T_side_left_pre_cal_ST  #-115
T_F_right_pre_cal_ST = T_side_right_pre_cal_ST
T_B_left_pre_cal_ST = T_side_left_pre_cal_ST
T_B_right_pre_cal_ST = T_side_right_pre_cal_ST

# Y ---------------------------------------------------------------------------
y_widths = [np.array([wide_strip, wide_strip, wide_strip, narrow_strip]),
            np.array([narrow_strip, wide_strip, wide_strip, wide_strip])]

y_pos_T = [y_pos(y_widths[0]), y_pos(y_widths[1])]
y_width_P1_and_P3 = y_widths[0]
y_width_P2_and_P4 = y_widths[1]
y_pos_P1_and_P3 = y_pos(y_width_P1_and_P3)
y_pos_P2_and_P4 = y_pos(y_width_P2_and_P4)
total_width = np.sum(y_width_P1_and_P3)

c_mm_ns = c/1000000
print(c_mm_ns)

# Miscelanous ----------------------------
muon_speed = beta * c_mm_ns
strip_speed = strip_speed_factor_of_c * c_mm_ns # 200 mm/ns
tdiff_to_x = strip_speed # Factor to transform t_diff to X

# Not-Hardcoded
vc    = beta * c_mm_ns # mm/ns
sc    = 1/vc
ss    = 1/strip_speed # slowness of the signal in the strip
nplan = n_planes_timtrack
lenx  = strip_length
anc_sx = tdiff_to_x * anc_std # 2 cm

T_clip_min = T_clip_min_default
T_clip_max = T_clip_max_default
Q_clip_min = Q_clip_min_default
Q_clip_max = Q_clip_max_default
num_bins = num_bins_default

T_clip_min_ST = T_clip_min_ST
T_clip_max_ST = T_clip_max_ST
Q_clip_min_ST = Q_clip_min_ST
Q_clip_max_ST = Q_clip_max_ST

reprocessing_values: dict[str, object] = {}
qa_reprocessing_context = load_qa_reprocessing_context_for_file(
    station,
    basename_no_ext,
    repo_root=repo_root,
)
apply_qa_reprocessing_context(global_variables, qa_reprocessing_context)
if int(qa_reprocessing_context.get("qa_reprocessing_mode", 0) or 0) == 1:
    print("Active QA reprocessing state found for this file.")
    print(
        "QA selectors: "
        f"{qa_reprocessing_context.get('qa_reprocessing_selector_ids', '') or 'none'}"
    )

reprocessing_parameters = load_reprocessing_parameters_for_file(station, str(task_number), basename_no_ext)
if not reprocessing_parameters.empty:
    if int(global_variables.get("qa_reprocessing_mode", 0) or 0) == 1:
        print("Reprocessing parameters found for this file. qa_reprocessing_mode=1.")
    else:
        print("Reprocessing parameters found for this file.")
    # Print only non-NaN entries from the reprocessing table
    non_nan = reprocessing_parameters.dropna(how="all").dropna(axis=1, how="all")
    if non_nan.empty:
        print("Reprocessing parameters found but all values are NaN.")
        columns_with_values: list[str] = []
    else:
        print(non_nan.to_string(index=False))
        columns_with_values = list(non_nan.columns)

    reprocessing_values = {
        column: get_reprocessing_value(reprocessing_parameters, column)
        for column in columns_with_values
    }
    reprocessing_values = {
        key: value for key, value in reprocessing_values.items() if value is not None
    }

# -------------------------------------------------------------------------------
# ------------ Input file and data managing to select configuration -------------
# -------------------------------------------------------------------------------

z_source = "unset"

if simulated_z_positions is not None:
    z_positions = np.array(simulated_z_positions, dtype=float)
    found_matching_conf = True
    print(f"Using simulated z_positions from param_hash={simulated_param_hash}")
    z_source = "simulated_param_hash"
elif is_simulated_file:
    print("Warning: Simulated file missing param_hash; using default z_positions.")
    found_matching_conf = False
    z_positions = np.array([0, 150, 300, 450])  # In mm
    z_source = "simulated_default_missing_param_hash"
elif exists_input_file:
    selection_result = select_input_file_configuration(
        input_file,
        start_time=start_time,
        end_time=end_time,
    )
    print(selection_result.matching_confs)

    if selection_result.selected_conf is not None:
        if selection_result.reason == "exact_overlap_latest_start":
            print(
                "Warning:\n"
                "Multiple configurations match the date range\n"
                f"{start_time} to {end_time}.\n"
                "Selecting the matching configuration with the most recent start date."
            )
        elif selection_result.reason != "exact":
            print("Warning: No matching configuration for the date range; selecting closest configuration.")
        selected_conf = selection_result.selected_conf
        print(f"Selected configuration: {selected_conf['conf']}")
        z_positions = np.array([selected_conf.get(f"P{i}", np.nan) for i in range(1, 5)])
        found_matching_conf = True
        print(selected_conf['conf'])
        z_source = f"input_file_conf_{selected_conf.get('conf')}"
    else:
        print("Warning: Input configuration file has no valid selectable rows. Using default z_positions.")
        z_positions = np.array([0, 150, 300, 450])  # In mm
        z_source = "default_invalid_input_file"
else:
    print("Error: No input file. Using default z_positions.")
    z_positions = np.array([0, 150, 300, 450])  # In mm
    z_source = "default_no_input_file"

# Print the resulting z_positions
z_positions = z_positions - z_positions[0]
print(f"Z positions: {z_positions}")
z_vector_mm = [round(float(value), 3) for value in z_positions.tolist()]
print(
    f"[Z_TRACE] file={basename_no_ext} source={z_source} "
    f"param_hash={simulated_param_hash or 'NA'} z_vector_mm={z_vector_mm}",
    force=True,
)

# Save the z_positions in the metadata file
global_variables['z_p1'] =  z_positions[0]
global_variables['z_p2'] =  z_positions[1]
global_variables['z_p3'] =  z_positions[2]
global_variables['z_p4'] =  z_positions[3]

raw_data_len = len(working_df)
if raw_data_len == 0 and not self_trigger:
    print("No coincidence nor self-trigger events.")
    sys.exit(1)

print("TASK_5 angular segmentation disabled.")



# Final task-rate plot included in the Task 5 PDF.
# FINAL plot block moved out of the runtime flow: acquisition_rate_vs_time_by_task_tt_with_histograms
pass

# -----------------------------------------------------------------------------
# Create and save the PDF -----------------------------------------------------
# -----------------------------------------------------------------------------

_finalize_stage_t0 = _t_sec
figure_directory = base_directories["figure_directory"]

if os.path.exists(figure_directory):
    shutil.rmtree(figure_directory)
_prof["s_pdf_finalize_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()

# Path to save the cleaned dataframe
# Create output directory if it does not exist.
task5_xpos_summary = ensure_plane_xpos_columns(working_df, tdiff_to_x, overwrite=True)
if task5_xpos_summary["source_columns_found"] != 4:
    raise RuntimeError(
        "Task 5 input is missing one or more p#_tdif columns required for plane X: "
        f"{task5_xpos_summary}"
    )
print(f"Task 5 plane X persistence check: {task5_xpos_summary}")
os.makedirs(f"{output_directory}", exist_ok=True)
OUT_PATH = f"{output_directory}/postprocessed_{basename_no_ext}.parquet"
KEY = "df"  # HDF5 key name

# Ensure output directory exists
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

# --- Example: your cleaned DataFrame is called working_df ---
# (Here, you would have your data cleaning code before saving)
# working_df = ...

# Detailed column dumps are only useful while debugging.
if VERBOSE:
    print("Columns in the cleaned dataframe:")
    for col in working_df.columns:
        print(f" - {col}")

# Remove the columns in the form "T*_T_sum_*", "T*_T_dif_*", "Q*_Q_sum_*", "Q*_Q_dif_*", do a loop from 1 to 4
cols_to_remove = []
for i_plane in range(1, 5):
    for strip in range(1, 5):
        cols_to_remove.append(f'p{i_plane}_s{strip}_tsum')
        cols_to_remove.append(f'p{i_plane}_s{strip}_tdif')
        cols_to_remove.append(f'p{i_plane}_s{strip}_qsum')
        cols_to_remove.append(f'p{i_plane}_s{strip}_qdif')
if keep_all_columns_output:
    print(
        "Task 5 keep_all_columns_output enabled: "
        f"retaining {len(cols_to_remove)} strip-summary columns."
    )
else:
    working_df.drop(columns=cols_to_remove, inplace=True, errors='ignore')

if VERBOSE:
    print("Columns in the final dataframe:")
    for col in working_df.columns:
        print(f" - {col}")



component_cols = []
for i_plane in range(1, 5):
    component_cols.extend(
        [
            f"p{i_plane}_tsum",
            f"p{i_plane}_tdif",
            f"p{i_plane}_qsum",
            f"p{i_plane}_qdif",
            f"p{i_plane}_ypos",
        ]
    )
component_cols = [col for col in component_cols if col in working_df.columns]
if component_cols:
    component_data = working_df[component_cols].fillna(0)
    all_zero_mask = (component_data == 0).all(axis=1)
    flagged_all_zero = int(all_zero_mask.sum())
    working_df.loc[:, "filter_task5_all_components_nonzero_pass"] = ~all_zero_mask
    record_filter_metric(
        "all_components_zero_rows_flagged_pct",
        flagged_all_zero,
        len(working_df) if len(working_df) else 0,
    )

print(f"Original number of events in the dataframe: {original_number_of_events}")
if create_debug_plots and POST_TT_COLUMN in working_df.columns:
    debug_fig_idx = plot_debug_histograms(
        working_df,
        [POST_TT_COLUMN],
        {POST_TT_COLUMN: [10]},
        title=f"Task 5 pre-filter: {POST_TT_COLUMN} >= 10 [NON-TUNABLE] (station {station})",
        out_dir=debug_plot_directory,
        fig_idx=debug_fig_idx,
    )
tt_task5_post_total = len(working_df)
tt_task5_post_mask = working_df[POST_TT_COLUMN].notna() & (working_df[POST_TT_COLUMN] >= 10)
working_df.loc[:, "filter_task5_tt_task5_post_pass"] = tt_task5_post_mask.to_numpy(dtype=bool)
record_filter_metric(
    "tt_task5_post_lt_10_rows_flagged_pct",
    tt_task5_post_total - int(tt_task5_post_mask.sum()),
    tt_task5_post_total if tt_task5_post_total else 0,
)

working_df.loc[:, "transferred_task5_fit_to_post"] = (
    pd.to_numeric(working_df["tt_task4_fit"], errors="coerce").fillna(0).astype(int).astype(str)
    + "_"
    + pd.to_numeric(working_df[POST_TT_COLUMN], errors="coerce").fillna(0).astype(int).astype(str)
)

tt_task5_post_counts = working_df[POST_TT_COLUMN].value_counts()
for tt_value, count in tt_task5_post_counts.items():
    tt_label = normalize_tt_label(tt_value)
    global_variables[f"{POST_TT_COLUMN}_{tt_label}_count"] = int(count)

fit_to_post_counts = working_df["transferred_task5_fit_to_post"].value_counts()
for combo_value, count in fit_to_post_counts.items():
    combo_label = normalize_tt_label(combo_value)
    global_variables[f"transferred_task5_fit_to_post_{combo_label}_count"] = int(count)

# Final number of events
final_number_of_events = len(working_df)
print(f"Final number of events in the dataframe: {final_number_of_events}")
record_filter_metric(
    "total_rows_removed_pct",
    original_number_of_events - final_number_of_events,
    original_number_of_events if original_number_of_events else 0,
)

print(
    f"Writing postprocessed parquet: rows={len(working_df)} cols={len(working_df.columns)} -> {OUT_PATH}"
)
if VERBOSE:
    print("Columns before saving fit->corr parquet:")
    for col in working_df.columns:
        print(col)

# Data purity
data_purity = final_number_of_events / original_number_of_events * 100
global_variables['purity_of_data_percentage'] = data_purity

# ------------
# DECIDED TO KEEP datetime
# ------------
# # Change 'datetime' column to 'Time' ------------------------------------------
# if 'datetime' in working_df.columns:
#     working_df.rename(columns={'datetime': 'Time'}, inplace=True)
# else:
#     print("Column 'datetime' not found in DataFrame!")

# End of the execution time
_prof["s_efficiency_s"] = round(time.perf_counter() - _t_sec, 2)
end_time_execution = datetime.now()
execution_time = end_time_execution - start_execution_time_counting
# In minutes
execution_time_minutes = execution_time.total_seconds() / 60

# To save as metadata
filename_base = basename_no_ext
execution_timestamp = datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
data_purity_percentage = data_purity
total_execution_time_minutes = execution_time_minutes
param_hash_value = str(simulated_param_hash) if simulated_param_hash else str(global_variables.get("param_hash", ""))
global_variables["param_hash"] = param_hash_value

# -------------------------------------------------------------------------------
# Filter metadata (ancillary) ---------------------------------------------------
# -------------------------------------------------------------------------------
if status_execution_date is not None:
    update_status_progress(
        csv_path_status,
        filename_base=status_filename_base,
        execution_date=status_execution_date,
        completion_fraction=0.75,
        param_hash=str(global_variables.get("param_hash", "")),
    )

filter_metrics["data_purity_percentage"] = round(float(data_purity_percentage), 4)
filter_row = {
    "filename_base": filename_base,
    "execution_timestamp": execution_timestamp,
    "param_hash": param_hash_value,
}
for name in FILTER_METRIC_NAMES:
    filter_row[name] = filter_metrics.get(name, "")

metadata_filter_csv_path = save_metadata(
    csv_path_filter,
    filter_row,
    preferred_fieldnames=("filename_base", "execution_timestamp", "param_hash", *FILTER_METRIC_NAMES),
)
print(f"Metadata (filter) CSV updated at: {metadata_filter_csv_path}")

deep_fiter_row = {
    "filename_base": filename_base,
    "execution_timestamp": execution_timestamp,
    "param_hash": param_hash_value,
}
for name in sorted(filter_metrics):
    deep_fiter_row[name] = filter_metrics.get(name, "")

metadata_deep_fiter_csv_path = save_metadata(
    csv_path_deep_fiter,
    deep_fiter_row,
    preferred_fieldnames=(
        "filename_base",
        "execution_timestamp",
        "param_hash",
        *sorted(filter_metrics),
    ),
    replace_existing_basename=True,
)
print(f"Metadata (deep_fiter) CSV updated at: {metadata_deep_fiter_csv_path}")

# -------------------------------------------------------------------------------
# Execution metadata ------------------------------------------------------------
# -------------------------------------------------------------------------------

print("----------\nExecution metadata to be saved:")
print(f"Filename base: {filename_base}")
print(f"Execution timestamp: {execution_timestamp}")
print(f"Data purity percentage: {data_purity_percentage:.2f}%")
print(f"Total execution time: {total_execution_time_minutes:.2f} minutes")

execution_metadata_row = {
    "filename_base": filename_base,
    "execution_timestamp": execution_timestamp,
    "param_hash": param_hash_value,
    "data_purity_percentage": round(float(data_purity_percentage), 4),
    "total_execution_time_minutes": round(float(total_execution_time_minutes), 4),
    "joined_analysis_files_used": int(len(joined_input_records)),
}
apply_qa_reprocessing_context(execution_metadata_row, qa_reprocessing_context)

metadata_execution_csv_path = save_metadata(
    csv_path,
    execution_metadata_row,
    preferred_fieldnames=(
        "filename_base",
        "execution_timestamp",
        "param_hash",
        "data_purity_percentage",
        "total_execution_time_minutes",
        "joined_analysis_files_used",
        *QA_REPROCESSING_METADATA_KEYS,
    ),
)
print(f"Metadata (execution) CSV updated at: {metadata_execution_csv_path}")

# -------------------------------------------------------------------------------
# Specific metadata ------------------------------------------------------------
# -------------------------------------------------------------------------------

global_variables.update(build_events_per_second_metadata(working_df))
ensure_global_count_keys(("tt_task4_fit", "tt_task5_post", "transferred_task5_fit_to_post"))
add_normalized_count_metadata(
    global_variables,
    global_variables.get("events_per_second_total_seconds", 0),
)
set_global_rate_from_tt_rates(
    global_variables,
    preferred_prefixes=("tt_task5_post", "tt_task4_fit"),
    log_fn=print,
)
global_variables["filename_base"] = filename_base
global_variables["execution_timestamp"] = execution_timestamp
global_variables["param_hash"] = param_hash_value

rate_histogram_variables = extract_rate_histogram_metadata(global_variables, remove_from_source=True)
metadata_rate_histogram_csv_path = save_metadata(
    csv_path_rate_histogram,
    rate_histogram_variables,
)
print(f"Metadata (rate_histogram) CSV updated at: {metadata_rate_histogram_csv_path}")

prune_redundant_count_metadata(global_variables, log_fn=print)
trigger_type_prefixes = ("tt_task4_fit", "tt_task5_post", "transferred_task5_fit_to_post")
legacy_trigger_type_prefixes: tuple[str, ...] = ()
trigger_type_variables = extract_trigger_type_metadata(
    global_variables,
    trigger_type_prefixes,
    remove_from_source=True,
)
# Keep the denominator in trigger_type so rate_hz values can be converted back to counts.
trigger_type_variables["count_rate_denominator_seconds"] = rate_histogram_variables.get(
    "count_rate_denominator_seconds",
    0,
)
add_trigger_type_total_offender_threshold_metadata(
    trigger_type_variables,
    working_df,
    stage_tt_columns=("tt_task4_fit", "tt_task5_post"),
    denominator_seconds=trigger_type_variables["count_rate_denominator_seconds"],
)
metadata_trigger_type_csv_path = save_metadata(
    csv_path_trigger_type,
    trigger_type_variables,
    drop_field_predicate=lambda column_name: (
        (not is_trigger_type_file_column(column_name, trigger_type_prefixes))
        or is_trigger_type_metadata_column(
            column_name,
            legacy_trigger_type_prefixes,
        )
    ),
)
print(f"Metadata (trigger_type) CSV updated at: {metadata_trigger_type_csv_path}")

print(f"Specific metadata keys to be saved: {len(global_variables)}")
if VERBOSE:
    print("----------\nAll global variables to be saved:")
    for key, value in global_variables.items():
        print(f"{key}: {value}")
    print("----------\n")

print("----------\nSpecific metadata to be saved:")
print(f"Filename base: {filename_base}")
print(f"Execution timestamp: {execution_timestamp}")
print(f"------------- Any other variable interesting -------------")
print("\n----------")
print(
    f"[Z_TRACE] metadata_append filename_base={filename_base} "
    f"param_hash={simulated_param_hash or 'NA'} z_vector_mm={z_vector_mm}",
    force=True,
)

metadata_specific_csv_path = save_metadata(
    csv_path_specific,
    global_variables,
    drop_field_predicate=lambda column_name: (
        is_specific_metadata_excluded_column(column_name)
        or is_trigger_type_metadata_column(
            column_name,
            trigger_type_prefixes + legacy_trigger_type_prefixes,
        )
    ),
)
print(f"Metadata (specific) CSV updated at: {metadata_specific_csv_path}")
_prof["s_metadata_write_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()

# Ensure no figure handles remain open before persistence/final move.
plt.close("all")

if joined_analysis_active and joined_source_file_column in working_df.columns:
    for joined_record in joined_input_records:
        joined_file_name = joined_record["file_name"]
        joined_basename = joined_record["basename_no_ext"]
        joined_out_path = os.path.join(output_directory, f"postprocessed_{joined_basename}.parquet")
        joined_mask = working_df[joined_source_file_column].astype(str).eq(joined_file_name)
        joined_output_df = working_df.loc[joined_mask].drop(
            columns=[joined_source_file_column, joined_source_basename_column],
            errors="ignore",
        )
        joined_output_df = canonicalize_step1_columns(joined_output_df)
        joined_output_df.to_parquet(
            joined_out_path,
            engine="pyarrow",
            compression=_preferred_parquet_compression(),
            index=False,
        )
        print(f"Postprocessed joined-analysis dataframe saved to: {joined_out_path} rows={len(joined_output_df)}")
else:
    output_df = working_df.drop(
        columns=[joined_source_file_column, joined_source_basename_column],
        errors="ignore",
    )
    output_df = canonicalize_step1_columns(output_df)
    output_df.to_parquet(
        OUT_PATH,
        engine="pyarrow",
        compression=_preferred_parquet_compression(),
        index=False,
    )
    print(f"Postprocessed dataframe saved to: {OUT_PATH}")
_prof["s_output_write_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()

# Move the original datafile to COMPLETED -------------------------------------
print("Moving file(s) to COMPLETED directory...")

if user_file_selection == False:
    for joined_record in joined_input_records:
        joined_processing_path = joined_record["processing_file_path"]
        joined_completed_path = joined_record["completed_file_path"]
        if os.path.exists(joined_processing_path):
            safe_move(joined_processing_path, joined_completed_path)
            now = time.time()
            os.utime(joined_completed_path, (now, now))
            print("************************************************************")
            print(f"File moved from\n{joined_processing_path}\nto:\n{joined_completed_path}")
            print("************************************************************")
        else:
            print(f"Warning: processing file not found for completion move: {joined_processing_path}")

if status_execution_date is not None:
    update_status_progress(
        csv_path_status,
        filename_base=status_filename_base,
        execution_date=status_execution_date,
        completion_fraction=1.0,
        param_hash=str(global_variables.get("param_hash", "")),
    )

_prof["s_file_move_s"] = round(time.perf_counter() - _t_sec, 2)
_prof["s_finalize_s"] = round(time.perf_counter() - _finalize_stage_t0, 2)
_prof["filename_base"] = filename_base
_prof["execution_timestamp"] = execution_timestamp
_prof["param_hash"] = param_hash_value
_prof["total_s"] = round(time.perf_counter() - _prof_t0, 2)
save_metadata(csv_path_profiling, _prof)
replicate_joined_metadata_rows(
    [
        csv_path,
        csv_path_specific,
        csv_path_rate_histogram,
        csv_path_trigger_type,
        csv_path_filter,
        csv_path_deep_fiter,
        csv_path_status,
        csv_path_profiling,
    ],
    primary_filename_base=filename_base,
    joined_input_records=joined_input_records,
    log_fn=print,
)
