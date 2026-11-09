#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/COIN_TRIGGER/TASK_3/script_3_cal_to_list.py
Purpose: !/usr/bin/env python3.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/COIN_TRIGGER/TASK_3/script_3_cal_to_list.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

#%%

from __future__ import annotations

"""
Stage 1 Task 3 (CAL-->LIST) transformation.

Takes the calibrated event sample from Task 2, builds the per-hit LIST-level
representation (timing, charge, geometry groupings), applies physics-driven
selection and quality filters, and exports the structured list data required
for the fitting stages. It also manages plotting artefacts, metadata logs, and
file movements so subsequent tasks receive consistent inputs.
"""
# Standard Library
import builtins
from datetime import datetime
import hashlib
import math
import os
from pathlib import Path
import random
import re
import shutil
import sys
import time
import warnings
from itertools import combinations
from typing import Dict, Iterable

# Scientific Computing
import numpy as np
import pandas as pd
from scipy.constants import c
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import curve_fit

# Plotting
import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import seaborn as sns

# Image Processing

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

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.debug_plots import plot_debug_histograms
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.execution_logger import set_station, start_timer
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.file_selection import (
    filter_expected_artifact_names,
    file_name_in_any_date_range,
    load_date_ranges_from_config,
    select_latest_candidate,
    sync_unprocessed_with_date_range,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.input_file_config import (
    select_closest_valid_z_configuration,
    select_input_file_configuration,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import (
    get_repo_root,
    resolve_home_path_from_config,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.plot_utils import ensure_plot_state
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.selection_config import load_selection_for_paths, station_is_selected
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.step1_rate_plots import create_rate_vs_time_by_task_tt_with_histograms
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.tot_charge_calibration import (
    TotChargeCalibration,
    default_tot_charge_calibration_path,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.tot_charge_order_comparison import (
    add_task3_charge_fc_columns,
    calibration_order_arrays,
    plot_calibration_order_comparison,
    plot_calibration_order_scatter,
)
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
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.step1_activation import (
    ACTIVATION_METADATA_DECIMALS,
    compute_conditional_matrices_by_tt,
    compute_conditional_matrix_from_boolean_arrays,
    store_activation_matrices_by_tt_metadata,
    store_activation_matrix_metadata,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.step1_shared import (
    add_normalized_count_metadata,
    add_topology_task2_strip,
    add_topology_task3_plane,
    add_trigger_type_total_offender_threshold_metadata,
    apply_step1_periodic_plot_gate,
    build_events_per_second_metadata,
    build_step1_cli_parser,
    build_step1_filtered_print,
    canonicalize_step1_columns,
    collect_columns,
    coerce_nonnegative_float_config,
    coerce_positive_int_config,
    extract_rate_histogram_metadata,
    extract_trigger_type_metadata,
    ensure_plane_xpos_columns,
    is_trigger_type_file_column,
    is_trigger_type_metadata_column,
    is_specific_metadata_excluded_column,
    load_step1_task_config_bundle,
    normalize_tt_label,
    prune_redundant_count_metadata,
    replicate_joined_metadata_rows,
    resolve_step1_effective_task_config,
    save_metadata,
    select_joined_analysis_file_names,
    select_exact_minimum_vertex_cover,
    set_global_rate_from_tt_rates,
    step1_logging_enabled,
    validate_step1_input_file_args,
    y_pos,
)
from analysis_functions import (
    _count_turns,
    _task3_config_float,
    _task3_optional_float,
    compute_empirical_efficiency_from_tt_counts,
    tt_value_to_planes,
)
from plotting_functions import (
    _task3_plot_quantile_scatter,
    _task3_plot_quantile_hexbin,
)

task_number = 3

try:
    import pyarrow as pa
except Exception:  # pragma: no cover - pyarrow is already required for parquet IO here.
    pa = None

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

def normalize_task3_plot_mode(raw_value: object) -> str:
    if raw_value is None:
        return "none"
    if isinstance(raw_value, bool):
        return "all" if raw_value else "none"

    mode = str(raw_value).strip().lower()
    if mode in {"", "none", "null", "false", "0", "off"}:
        return "none"
    if mode == "debug":
        return "debug"
    if mode in {"usual", "standard", "normal"}:
        return "usual"
    if mode == "essential":
        return "essential"
    if mode in {"all", "true", "1", "on"}:
        return "all"

    raise ValueError(
        "Invalid create_plots value for Task 3. Use one of: null/none, debug, usual, essential, all."
    )

def normalize_task3_plot_catalog_status(raw_value: object) -> str:
    if raw_value is None:
        return "none"
    if isinstance(raw_value, bool):
        return "usual" if raw_value else "none"

    status = str(raw_value).strip().lower()
    if status in {"", "none", "null", "false", "0", "off"}:
        return "none"
    if status in {"true", "1", "on"}:
        return "usual"
    if status in {"debug", "usual", "essential"}:
        return status
    return status

def resolve_task3_plot_options(config_obj: Dict[str, object]) -> tuple[str, bool, bool, bool, bool, bool, bool]:
    station_id = config_obj.get("_plot_station_id")
    task_id = config_obj.get("_plot_task_number")
    if station_id is not None and task_id is not None:
        apply_step1_periodic_plot_gate(
            config_obj, station_id=str(station_id), task_number=int(task_id), log_fn=print
        )
    plot_mode = normalize_task3_plot_mode(config_obj.get("create_plots", None))
    create_plots = plot_mode in {"usual", "all"}
    create_debug_plots = plot_mode in {"debug", "all"}
    create_essential_plots = plot_mode in {"usual", "essential", "all"}
    save_plots = plot_mode != "none"
    create_pdf = False  # Runtime plots are strictly PNG-only; FINAL PDFs are standalone.
    show_plots = False
    return (
        plot_mode,
        create_plots,
        create_essential_plots,
        save_plots,
        create_pdf,
        show_plots,
        create_debug_plots,
    )

def load_task3_plot_catalog(catalog_path: Path) -> dict[str, str]:
    with catalog_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}

    if not isinstance(loaded, dict):
        raise ValueError(f"Task 3 plot catalog must be a mapping: {catalog_path}")

    if "-plot" in loaded or "-not_plot" in loaded:
        plotted = loaded.get("-plot", []) or []
        not_plotted = loaded.get("-not_plot", []) or []
        if not isinstance(plotted, list) or not isinstance(not_plotted, list):
            raise ValueError("Task 3 '-plot' and '-not_plot' must each be YAML lists.")
        plotted = [str(alias) for alias in plotted]
        not_plotted = [str(alias) for alias in not_plotted]
        overlap = sorted(set(plotted) & set(not_plotted))
        if overlap:
            raise ValueError(f"Task 3 aliases cannot appear in both lists: {overlap}")
        selected = set(plotted) & set(TASK3_PLOT_ALIASES)
        unknown = sorted((set(plotted) | set(not_plotted)) - set(TASK3_PLOT_ALIASES))
        if unknown:
            warnings.warn(f"Unknown Task 3 plot aliases ignored: {unknown}", RuntimeWarning)
        return {alias: ("usual" if alias in selected else "none") for alias in TASK3_PLOT_ALIASES}

    raw_plots = loaded.get("plots", {})
    if not isinstance(raw_plots, dict):
        raise ValueError(f"'plots' entry in {catalog_path} must be a mapping.")

    catalog: dict[str, str] = {}
    for alias, raw_entry in raw_plots.items():
        if isinstance(raw_entry, dict):
            raw_status = raw_entry.get("status", "")
        else:
            raw_status = raw_entry
        status = normalize_task3_plot_catalog_status(raw_status)
        if status not in TASK3_PLOT_STATUSES:
            raise ValueError(
                f"Invalid status {raw_status!r} for Task 3 plot alias {alias!r} in {catalog_path}."
            )
        catalog[str(alias)] = status

    unknown_aliases = sorted(alias for alias in catalog if alias not in TASK3_PLOT_ALIASES)
    for alias in unknown_aliases:
        warnings.warn(
            f"Task 3 plot catalog entry {alias!r} is not a known plot alias and will be ignored.",
            RuntimeWarning,
        )
        catalog.pop(alias, None)

    missing_aliases = [alias for alias in TASK3_PLOT_ALIASES if alias not in catalog]
    for alias in missing_aliases:
        # Known aliases missing from the runtime catalog are intentionally not
        # runtime plots; FINAL aliases live in config_final_plots_task_3.yaml.
        catalog[alias] = "none"
    return catalog


def task3_plot_enabled(alias: str) -> bool:
    if alias not in task3_plot_status_by_alias:
        raise KeyError(f"Unknown Task 3 plot alias: {alias}")

    status = task3_plot_status_by_alias[alias]
    current_mode = str(globals().get("plot_mode", "none"))
    if current_mode == "none":
        return False
    if status == "none":
        return False
    if current_mode == "all":
        return True
    if current_mode == "debug":
        return status == "debug"
    if current_mode == "usual":
        return status in {"usual", "essential"}
    if current_mode == "essential":
        return status == "essential"
    return False

def task3_any_plot_enabled(*aliases: str) -> bool:
    return any(task3_plot_enabled(alias) for alias in aliases)





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



def save_plot_figure(save_path: str, fig: mpl.figure.Figure | None = None, **savefig_kwargs) -> None:
    """Save one runtime plot as PNG."""
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


def ensure_global_count_keys(prefixes: Iterable[str]) -> None:
    for prefix in prefixes:
        for tt_value in TT_COUNT_VALUES:
            global_variables.setdefault(f"{prefix}_{tt_value}_count", 0)

def refresh_global_count_metadata(df: pd.DataFrame, column_names: Iterable[str]) -> None:
    prefixes = tuple(f"{column_name}_" for column_name in column_names)
    for key in list(global_variables):
        if key.endswith("_count") and any(key.startswith(prefix) for prefix in prefixes):
            global_variables.pop(key, None)
    for column_name in column_names:
        if column_name not in df.columns:
            continue
        value_counts = df[column_name].value_counts()
        for tt_value, count in value_counts.items():
            tt_label = normalize_tt_label(tt_value)
            global_variables[f"{column_name}_{tt_label}_count"] = int(count)


def record_filter_metric(name: str, removed: float, total: float) -> None:
    """Record percentage removed for a filter."""
    pct = 0.0 if total == 0 else 100.0 * float(removed) / float(total)
    filter_metrics[name] = round(pct, 4)
    _log_filter_metrics_message(
        f"[filter-metrics] {name}: removed {removed} of {total} ({pct:.2f}%)"
    )

def record_activity_metric(name: str, affected: float, total: float, label: str = "affected") -> None:
    """Record a generic percentage metric for non-row-removal filter activity."""
    pct = 0.0 if total == 0 else 100.0 * float(affected) / float(total)
    filter_metrics[name] = round(pct, 4)
    _log_filter_metrics_message(
        f"[filter-metrics] {name}: {label} {affected} of {total} ({pct:.2f}%)"
    )

def _task3_drop_legacy_deep_filter_field(column_name: str) -> bool:
    return (
        column_name.startswith("plane_rpc_window_")
        or column_name in TASK3_DEEP_FILTER_LEGACY_COLUMNS
    )

def build_task3_full_strip_pattern_series(df: pd.DataFrame) -> pd.Series:
    """Encode the four per-plane active-strip labels as one deterministic 16-bit string."""
    pattern_arrays: list[np.ndarray] = []
    for col_name in TASK3_ACTIVE_STRIP_COLUMNS:
        if col_name in df.columns:
            values = df[col_name].fillna("0000").astype(str).to_numpy(copy=False)
        else:
            print(f"Warning: missing active-strip column '{col_name}' while building TASK_3 patterns.")
            values = np.full(len(df), "0000", dtype="<U4")
        pattern_arrays.append(values)

    if not pattern_arrays:
        return pd.Series(dtype="object", index=df.index)

    full_pattern = pattern_arrays[0].copy()
    for values in pattern_arrays[1:]:
        full_pattern = np.char.add(full_pattern, values)
    return pd.Series(full_pattern, index=df.index, dtype="object")

def store_pattern_rates(metadata: dict[str, object], patterns: pd.Series, prefix: str, df: pd.DataFrame) -> None:
    phase_meta = build_events_per_second_metadata(df)
    try:
        denominator = float(phase_meta.get("events_per_second_total_seconds", 0) or 0)
    except (TypeError, ValueError):
        denominator = 0.0

    counts = patterns.value_counts()
    for pattern, count in counts.items():
        rate_hz = round(float(count) / denominator, 6) if denominator > 0 else 0.0
        metadata[f"{prefix}_{pattern}_rate_hz"] = rate_hz


def _task3_plane_charge_arrays(df: pd.DataFrame) -> tuple[list[str], list[np.ndarray]]:
    labels: list[str] = []
    arrays: list[np.ndarray] = []
    for plane in range(1, 5):
        column_name = f"p{plane}_qsum"
        if column_name in df.columns:
            arr = pd.to_numeric(df[column_name], errors="coerce").to_numpy(dtype=float)
        else:
            arr = np.full(len(df), np.nan, dtype=float)
        labels.append(f"P{plane}")
        arrays.append(arr)
    return labels, arrays

def _format_activation_scalar(value: float | None) -> float | str:
    if value is None:
        return ""
    value_float = float(value)
    if not np.isfinite(value_float):
        return ""
    return round(value_float, ACTIVATION_METADATA_DECIMALS)

def _store_activation_scalar(
    activation_meta: dict[str, object],
    scalar_meta: dict[str, object],
    key: str,
    value: object,
) -> None:
    activation_meta[key] = value
    scalar_meta.pop(key, None)

def store_task3_plane_activation_snapshot(
    *,
    activation_meta: dict[str, object],
    scalar_meta: dict[str, object],
    df: pd.DataFrame,
    snapshot_label: str,
    tt_series: pd.Series,
    streamer_high_charge_factor_value: float,
    streamer_threshold_override: float | None = None,
) -> dict[str, object]:
    labels, charge_arrays = _task3_plane_charge_arrays(df)
    signal_arrays = [np.isfinite(arr) & (arr > 0) for arr in charge_arrays]
    signal_matrix, signal_given_counts = compute_conditional_matrix_from_boolean_arrays(
        labels,
        signal_arrays,
    )
    store_activation_matrix_metadata(
        activation_meta,
        f"activation_plane_signal_to_signal_{snapshot_label}",
        labels,
        signal_matrix,
        signal_given_counts,
        group_ids=[0, 1, 2, 3],
    )
    selected_tts, matrices_by_tt, given_counts_by_tt, event_counts_by_tt = (
        compute_conditional_matrices_by_tt(
            tt_series,
            labels,
            signal_arrays,
        )
    )
    store_activation_matrices_by_tt_metadata(
        activation_meta,
        f"activation_plane_signal_to_signal_{snapshot_label}_by_tt",
        labels,
        labels,
        selected_tts,
        matrices_by_tt,
        given_counts_by_tt,
        event_counts_by_tt,
    )

    q_sum_cols = [f"p{plane}_qsum" for plane in range(1, 5)]
    streamer_threshold, _ = select_task3_streamer_threshold(
        df,
        q_sum_cols,
        streamer_threshold_override,
    )
    threshold_key = f"streamer_threshold_selected_{snapshot_label}"
    _store_activation_scalar(
        activation_meta,
        scalar_meta,
        threshold_key,
        _format_activation_scalar(streamer_threshold),
    )

    high_charge_threshold = None
    if streamer_threshold is not None:
        high_charge_threshold = float(streamer_threshold) * float(streamer_high_charge_factor_value)
        _store_activation_scalar(
            activation_meta,
            scalar_meta,
            f"streamer_high_charge_threshold_selected_{snapshot_label}",
            _format_activation_scalar(high_charge_threshold),
        )
    else:
        _store_activation_scalar(
            activation_meta,
            scalar_meta,
            f"streamer_high_charge_threshold_selected_{snapshot_label}",
            "",
        )

    if snapshot_label == "filtered":
        _store_activation_scalar(
            activation_meta,
            scalar_meta,
            "streamer_high_charge_factor",
            _format_activation_scalar(streamer_high_charge_factor_value),
        )
        _store_activation_scalar(
            activation_meta,
            scalar_meta,
            "streamer_threshold_selected",
            activation_meta.get(threshold_key, ""),
        )
        _store_activation_scalar(
            activation_meta,
            scalar_meta,
            "streamer_high_charge_threshold_selected",
            activation_meta.get(f"streamer_high_charge_threshold_selected_{snapshot_label}", ""),
        )

    if streamer_threshold is None or high_charge_threshold is None:
        for plane in range(1, 5):
            _store_activation_scalar(
                activation_meta,
                scalar_meta,
                f"streamer_rate_plane_{snapshot_label}_{plane}",
                "",
            )
            if snapshot_label == "filtered":
                _store_activation_scalar(
                    activation_meta,
                    scalar_meta,
                    f"streamer_rate_plane_{plane}",
                    "",
                )
        return {
            "labels": labels,
            "signal_matrix": signal_matrix,
            "streamer_matrix": np.empty((0, 0), dtype=float),
        }

    streamer_arrays = [np.isfinite(arr) & (arr > float(streamer_threshold)) for arr in charge_arrays]
    high_charge_arrays = [np.isfinite(arr) & (arr > float(high_charge_threshold)) for arr in charge_arrays]
    streamer_matrix = np.empty((0, 0), dtype=float)
    for plane, signal_mask, streamer_mask in zip(range(1, 5), signal_arrays, streamer_arrays):
        n_signal = int(np.sum(signal_mask))
        n_streamer = int(np.sum(streamer_mask))
        rate_key = f"streamer_rate_plane_{snapshot_label}_{plane}"
        _store_activation_scalar(
            activation_meta,
            scalar_meta,
            rate_key,
            _format_activation_scalar(float(n_streamer) / float(n_signal)) if n_signal > 0 else "",
        )
        if snapshot_label == "filtered":
            _store_activation_scalar(
                activation_meta,
                scalar_meta,
                f"streamer_rate_plane_{plane}",
                activation_meta.get(rate_key, ""),
            )

    variant_specs = [
        ("streamer_to_streamer", streamer_arrays, streamer_arrays),
        ("streamer_to_signal", streamer_arrays, signal_arrays),
        ("streamer_to_highcharge", streamer_arrays, high_charge_arrays),
    ]
    for variant_name, source_arrays, target_arrays in variant_specs:
        variant_matrix, variant_given_counts = compute_conditional_matrix_from_boolean_arrays(
            labels,
            source_arrays,
            target_labels=labels,
            target_arrays=target_arrays,
        )
        if variant_name == "streamer_to_streamer":
            streamer_matrix = variant_matrix
        store_activation_matrix_metadata(
            activation_meta,
            f"activation_plane_{variant_name}_{snapshot_label}",
            labels,
            variant_matrix,
            variant_given_counts,
            target_labels=labels,
            group_ids=[0, 1, 2, 3],
        )
        selected_tts, matrices_by_tt, given_counts_by_tt, event_counts_by_tt = (
            compute_conditional_matrices_by_tt(
                tt_series,
                labels,
                source_arrays,
                target_labels=labels,
                target_arrays=target_arrays,
            )
        )
        store_activation_matrices_by_tt_metadata(
            activation_meta,
            f"activation_plane_{variant_name}_{snapshot_label}_by_tt",
            labels,
            labels,
            selected_tts,
            matrices_by_tt,
            given_counts_by_tt,
            event_counts_by_tt,
        )

    return {
        "labels": labels,
        "signal_matrix": signal_matrix,
        "streamer_matrix": streamer_matrix,
    }

def plot_task3_plane_activation_before_after(
    initial_snapshot: dict[str, object],
    filtered_snapshot: dict[str, object],
    fig_idx_value: int,
) -> int:
    labels_initial = initial_snapshot.get("labels", [])
    labels_filtered = filtered_snapshot.get("labels", [])
    matrix_initial = initial_snapshot.get("signal_matrix")
    matrix_filtered = filtered_snapshot.get("signal_matrix")
    if (
        not isinstance(labels_initial, list)
        or not isinstance(labels_filtered, list)
        or labels_initial != labels_filtered
        or not isinstance(matrix_initial, np.ndarray)
        or not isinstance(matrix_filtered, np.ndarray)
        or matrix_initial.size == 0
        or matrix_filtered.size == 0
    ):
        return fig_idx_value

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8), constrained_layout=True)
    last_im = None
    for ax, matrix, title_text in zip(
        axes,
        [matrix_initial, matrix_filtered],
        ["Initial plane activation", "Filtered plane activation"],
    ):
        last_im = ax.imshow(matrix, cmap="viridis", vmin=0, vmax=1, aspect="equal")
        ax.set_xticks(range(len(labels_initial)))
        ax.set_xticklabels(labels_initial, fontsize=9)
        ax.set_yticks(range(len(labels_initial)))
        ax.set_yticklabels(labels_initial, fontsize=9)
        ax.set_title(title_text, fontsize=11)
        ax.set_xlabel("Target plane active")
        ax.set_ylabel("Given plane active")
        for i in range(len(labels_initial)):
            for j in range(len(labels_initial)):
                value = matrix[i, j]
                if np.isfinite(value):
                    text_color = "white" if value > 0.6 else "black"
                    ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=9, color=text_color)

    if last_im is not None:
        fig.colorbar(last_im, ax=axes, label="P(target plane active | given plane active)", shrink=0.85)
    fig.suptitle("Plane activation matrix: initial to filtered", fontsize=13)
    if save_plots:
        final_filename = f"{fig_idx_value}_plane_activation_matrix_before_after.png"
        fig_idx_value += 1
        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, fig=fig, format="png", dpi=150)
    if show_plots:
        plt.show()
    plt.close(fig)
    return fig_idx_value

def compute_qsum_threshold_tt(df: pd.DataFrame, threshold: float) -> pd.Series:
    """Return TT labels using only planes with P*_Q_sum_final > threshold."""
    tt_str = pd.Series("", index=df.index, dtype="object")
    for plane in range(1, 5):
        col_name = f"p{plane}_qsum"
        if col_name not in df.columns:
            continue
        charge_vals = pd.to_numeric(df[col_name], errors="coerce")
        plane_active = charge_vals.gt(float(threshold))
        tt_str = tt_str.where(~plane_active, tt_str + str(plane))
    return tt_str.replace("", "0").astype(int)

def compute_qsum_threshold_full_strip_patterns(df: pd.DataFrame, threshold: float) -> pd.Series:
    """Return full 16-bit strip topology after applying per-plane Q_sum threshold."""
    plane_arrays: list[np.ndarray] = []
    for plane in range(1, 5):
        strip_col = f"active_strips_P{plane}"
        qsum_col = f"p{plane}_qsum"

        if strip_col in df.columns:
            strip_vals = df[strip_col].fillna("0000").astype(str)
            strip_vals = strip_vals.where(strip_vals.str.len() == 4, "0000")
        else:
            strip_vals = pd.Series("0000", index=df.index, dtype="object")

        if qsum_col in df.columns:
            qsum_vals = pd.to_numeric(df[qsum_col], errors="coerce")
            keep_plane = qsum_vals.gt(float(threshold)).to_numpy(dtype=bool)
        else:
            keep_plane = np.zeros(len(df), dtype=bool)

        filtered = np.where(keep_plane, strip_vals.to_numpy(dtype=object), "0000").astype(str)
        plane_arrays.append(filtered)

    if not plane_arrays:
        return pd.Series(dtype="object", index=df.index)

    full_pattern = plane_arrays[0]
    for values in plane_arrays[1:]:
        full_pattern = np.char.add(full_pattern, values)
    return pd.Series(full_pattern, index=df.index, dtype="object")

def compute_qsum_threshold_tsum_window(df: pd.DataFrame, threshold: float) -> tuple[pd.Series, pd.Series]:
    """Compute T_sum coincidence window=max-min across planes with Q_sum > threshold."""
    t_cols = [f"p{plane}_tsum" for plane in range(1, 5)]
    q_cols = [f"p{plane}_qsum" for plane in range(1, 5)]

    t_vals = np.full((len(df), 4), np.nan, dtype=float)
    q_vals = np.full((len(df), 4), np.nan, dtype=float)
    for idx, (t_col, q_col) in enumerate(zip(t_cols, q_cols)):
        if t_col in df.columns:
            t_vals[:, idx] = pd.to_numeric(df[t_col], errors="coerce").to_numpy(dtype=float)
        if q_col in df.columns:
            q_vals[:, idx] = pd.to_numeric(df[q_col], errors="coerce").to_numpy(dtype=float)

    active = np.isfinite(q_vals) & np.isfinite(t_vals) & (q_vals > float(threshold))
    active_counts = active.sum(axis=1)
    masked_t = np.where(active, t_vals, np.nan)

    with np.errstate(all="ignore"):
        t_max = np.nanmax(masked_t, axis=1)
        t_min = np.nanmin(masked_t, axis=1)
    window = t_max - t_min
    window = np.where(active_counts >= 2, window, np.nan)

    return (
        pd.Series(window, index=df.index, dtype=float),
        pd.Series(active_counts, index=df.index, dtype=int),
    )

def classify_full_strip_topology(full_pattern: str) -> tuple[str, str, str]:
    """Classify full strip topology into active-mask and coarse topology class."""
    if not isinstance(full_pattern, str) or len(full_pattern) != 16:
        return "0000", "invalid", ""

    plane_patterns = [full_pattern[idx : idx + 4] for idx in range(0, 16, 4)]
    active_planes: list[int] = []
    strip_path: list[int] = []
    has_multi_strip = False

    for plane_idx, pattern in enumerate(plane_patterns, start=1):
        if pattern == "0000":
            continue
        active_planes.append(plane_idx)
        if pattern.count("1") == 1:
            strip_path.append(pattern.index("1") + 1)
        else:
            has_multi_strip = True

    active_mask = "".join("1" if plane in active_planes else "0" for plane in range(1, 5))
    if not active_planes:
        return active_mask, "empty", ""
    if has_multi_strip:
        return active_mask, "multi_strip", ""

    path_label = "-".join(str(val) for val in strip_path)
    jumps = [abs(strip_path[idx + 1] - strip_path[idx]) for idx in range(len(strip_path) - 1)]
    max_jump = max(jumps) if jumps else 0
    turns = _count_turns(strip_path)
    if turns >= 1:
        return active_mask, "single_strip_zigzag", path_label
    if max_jump >= 2:
        return active_mask, "single_strip_rough", path_label
    return active_mask, "single_strip_smooth", path_label

def compute_source_tt_min_charge(df: pd.DataFrame, source_tt: object) -> pd.Series:
    planes = tt_value_to_planes(source_tt)
    if not planes:
        return pd.Series(np.nan, index=df.index, dtype=float)

    cols = [f"p{plane}_qsum" for plane in planes if f"p{plane}_qsum" in df.columns]
    if not cols:
        return pd.Series(np.nan, index=df.index, dtype=float)

    charge_df = df.loc[:, cols].apply(pd.to_numeric, errors="coerce")
    return charge_df.min(axis=1, skipna=False)


def select_task3_streamer_threshold(
    df: pd.DataFrame,
    q_sum_cols: list[str],
    configured_threshold: float | None = None,
) -> tuple[float | None, str]:
    if configured_threshold is not None and np.isfinite(configured_threshold) and configured_threshold > 0:
        return float(configured_threshold), "config"

    detected_threshold = detect_streamer_threshold(df, q_sum_cols)
    if detected_threshold is not None and np.isfinite(detected_threshold) and detected_threshold > 0:
        return float(detected_threshold), "auto"

    return None, "unavailable"

def compute_task3_charge_topology_codes(
    df: pd.DataFrame,
    streamer_threshold: float,
) -> tuple[pd.Series, dict[int, np.ndarray]]:
    topology_digits_by_plane: dict[int, np.ndarray] = {}
    topology_code_arrays: list[np.ndarray] = []

    for plane in range(1, 5):
        q_sum_col = f"p{plane}_qsum"
        if q_sum_col in df.columns:
            q_sum_values = pd.to_numeric(df[q_sum_col], errors="coerce").to_numpy(dtype=float)
        else:
            q_sum_values = np.full(len(df), np.nan, dtype=float)

        plane_has_charge = np.isfinite(q_sum_values) & (q_sum_values > 0)
        plane_is_streamer = plane_has_charge & (q_sum_values > float(streamer_threshold))
        plane_digits = np.where(plane_is_streamer, 2, np.where(plane_has_charge, 1, 0)).astype(np.int8)

        topology_digits_by_plane[plane] = plane_digits
        topology_code_arrays.append(plane_digits.astype(str))

    if not topology_code_arrays:
        return pd.Series(index=df.index, dtype="object"), topology_digits_by_plane

    topology_code = topology_code_arrays[0]
    for next_digits in topology_code_arrays[1:]:
        topology_code = np.char.add(topology_code, next_digits)

    return pd.Series(topology_code, index=df.index, dtype="object"), topology_digits_by_plane

def compute_task3_tt_from_topology_codes(
    topology_digits_by_plane: dict[int, np.ndarray],
    *,
    streamers_count_as_active: bool,
    exclude_streamer_events: bool = False,
    index: pd.Index,
) -> pd.Series:
    tt_series = pd.Series("", index=index, dtype="object")
    any_streamer = np.zeros(len(index), dtype=bool)

    for plane in range(1, 5):
        plane_digits = topology_digits_by_plane.get(plane)
        if plane_digits is None:
            continue
        any_streamer |= plane_digits == 2
        plane_active = plane_digits >= 1 if streamers_count_as_active else plane_digits == 1
        tt_series = tt_series.where(~plane_active, tt_series + str(plane))

    tt_series = tt_series.replace("", "0")
    if exclude_streamer_events:
        tt_series = tt_series.mask(any_streamer, pd.NA)
    return pd.to_numeric(tt_series, errors="coerce").astype("Int64")

def store_task3_charge_topology_metadata(
    metadata: dict[str, object],
    df: pd.DataFrame,
    topology_codes: pd.Series,
    topology_digits_by_plane: dict[int, np.ndarray],
    tt_reference: pd.Series,
    tt_streamer_as_avalanche: pd.Series,
    tt_streamer_as_invalid: pd.Series,
    tt_streamer_as_invalid_no_transference: pd.Series,
    streamer_threshold: float | None,
) -> None:
    total_events = int(len(df))
    metadata["charge_topology_total_events"] = total_events
    metadata["charge_topology_streamer_threshold_qsum"] = (
        round(float(streamer_threshold), 6)
        if streamer_threshold is not None and np.isfinite(streamer_threshold)
        else ""
    )

    phase_meta = build_events_per_second_metadata(df)
    try:
        denominator_seconds = float(phase_meta.get("events_per_second_total_seconds", 0) or 0)
    except (TypeError, ValueError):
        denominator_seconds = 0.0

    topology_counts = topology_codes.value_counts()
    for topology_code, count in topology_counts.items():
        key_base = f"charge_topology_code_{topology_code}"
        count_int = int(count)
        metadata[f"{key_base}_count"] = count_int
        metadata[f"{key_base}_fraction"] = round(count_int / total_events, 6) if total_events > 0 else ""
        metadata[f"{key_base}_rate_hz"] = round(count_int / denominator_seconds, 6) if denominator_seconds > 0 else 0.0

    any_streamer = np.zeros(total_events, dtype=bool)
    streamer_plane_multiplicity = np.zeros(total_events, dtype=int)
    state_name_by_digit = {
        0: "no_charge",
        1: "avalanche",
        2: "streamer",
    }
    for plane in range(1, 5):
        plane_digits = topology_digits_by_plane.get(plane, np.zeros(total_events, dtype=np.int8))
        plane_is_streamer = plane_digits == 2
        any_streamer |= plane_is_streamer
        streamer_plane_multiplicity += plane_is_streamer.astype(int)

        plane_streamer_count = int(np.count_nonzero(plane_is_streamer))
        metadata[f"streamer_P{plane}"] = (
            round(100.0 * plane_streamer_count / total_events, 6)
            if total_events > 0 and streamer_threshold is not None and np.isfinite(streamer_threshold)
            else ""
        )

        for state_digit, state_name in state_name_by_digit.items():
            state_count = int(np.count_nonzero(plane_digits == state_digit))
            metric_base = f"charge_topology_plane_{plane}_{state_name}"
            metadata[f"{metric_base}_count"] = state_count
            metadata[f"{metric_base}_fraction"] = round(state_count / total_events, 6) if total_events > 0 else ""
            metadata[f"{metric_base}_rate_hz"] = round(state_count / denominator_seconds, 6) if denominator_seconds > 0 else 0.0

    any_streamer_count = int(np.count_nonzero(any_streamer))
    metadata["charge_topology_any_streamer_count"] = any_streamer_count
    metadata["charge_topology_any_streamer_fraction"] = (
        round(any_streamer_count / total_events, 6) if total_events > 0 else ""
    )
    metadata["charge_topology_any_streamer_rate_hz"] = (
        round(any_streamer_count / denominator_seconds, 6) if denominator_seconds > 0 else 0.0
    )

    streamer_free_count = total_events - any_streamer_count
    metadata["charge_topology_global_rate_hz_with_streamers"] = (
        round(any_streamer_count / denominator_seconds, 6) if denominator_seconds > 0 else 0.0
    )
    metadata["charge_topology_global_rate_hz_without_streamers"] = (
        round(streamer_free_count / denominator_seconds, 6) if denominator_seconds > 0 else 0.0
    )

    tt_reference_series = pd.to_numeric(tt_reference, errors="coerce").astype("Int64")
    subset_specs = (
        ("with_streamers", tt_reference_series[any_streamer]),
        ("without_streamers", tt_reference_series[~any_streamer]),
    )
    missing_plane_tt = {1: 234, 2: 134, 3: 124, 4: 123}
    for subset_name, subset_tt_series in subset_specs:
        subset_tt_counts = subset_tt_series.value_counts()
        n_four_subset = int(subset_tt_counts.get(1234, 0))
        metadata[f"charge_topology_tt_1234_count_{subset_name}"] = n_four_subset
        metadata[f"charge_topology_tt_1234_rate_hz_{subset_name}"] = (
            round(n_four_subset / denominator_seconds, 6) if denominator_seconds > 0 else 0.0
        )

        per_plane_efficiency_subset = compute_empirical_efficiency_from_tt_counts(subset_tt_counts)
        for plane in range(1, 5):
            eff_value, eff_error, n_three, _ = per_plane_efficiency_subset.get(
                plane,
                (np.nan, np.nan, 0, n_four_subset),
            )
            tt_missing = missing_plane_tt[plane]
            metadata[f"charge_topology_eff_{subset_name}_plane_{plane}"] = (
                round(float(eff_value), 6) if np.isfinite(eff_value) else ""
            )
            metadata[f"charge_topology_eff_err_{subset_name}_plane_{plane}"] = (
                round(float(eff_error), 6) if np.isfinite(eff_error) else ""
            )
            metadata[f"charge_topology_tt_{tt_missing}_count_{subset_name}_plane_{plane}"] = int(n_three)
            metadata[f"charge_topology_tt_{tt_missing}_rate_hz_{subset_name}_plane_{plane}"] = (
                round(int(n_three) / denominator_seconds, 6) if denominator_seconds > 0 else 0.0
            )

    for multiplicity in range(0, 5):
        multiplicity_count = int(np.count_nonzero(streamer_plane_multiplicity == multiplicity))
        metric_base = f"charge_topology_streamer_plane_multiplicity_{multiplicity}"
        metadata[f"{metric_base}_count"] = multiplicity_count
        metadata[f"{metric_base}_fraction"] = (
            round(multiplicity_count / total_events, 6) if total_events > 0 else ""
        )
        metadata[f"{metric_base}_rate_hz"] = (
            round(multiplicity_count / denominator_seconds, 6) if denominator_seconds > 0 else 0.0
        )

    policy_specs = (
        ("streamer_as_avalanche", tt_streamer_as_avalanche),
        ("streamer_as_invalid", tt_streamer_as_invalid),
        ("streamer_as_invalid_no_transference", tt_streamer_as_invalid_no_transference),
    )
    for policy_name, tt_series in policy_specs:
        excluded_count = int(tt_series.isna().sum())
        metadata[f"charge_topology_excluded_count_{policy_name}"] = excluded_count
        metadata[f"charge_topology_excluded_fraction_{policy_name}"] = (
            round(excluded_count / total_events, 6) if total_events > 0 else ""
        )
        metadata[f"charge_topology_excluded_rate_hz_{policy_name}"] = (
            round(excluded_count / denominator_seconds, 6) if denominator_seconds > 0 else 0.0
        )
        tt_counts = tt_series.value_counts()
        n_four = int(tt_counts.get(1234, 0))
        metadata[f"charge_topology_tt_1234_count_{policy_name}"] = n_four
        metadata[f"charge_topology_tt_1234_rate_hz_{policy_name}"] = (
            round(n_four / denominator_seconds, 6) if denominator_seconds > 0 else 0.0
        )

        per_plane_efficiency = compute_empirical_efficiency_from_tt_counts(tt_counts)
        for plane in range(1, 5):
            eff_value, eff_error, n_three, _ = per_plane_efficiency.get(
                plane,
                (np.nan, np.nan, 0, n_four),
            )
            tt_missing = missing_plane_tt[plane]
            metadata[f"charge_topology_eff_{policy_name}_plane_{plane}"] = (
                round(float(eff_value), 6) if np.isfinite(eff_value) else ""
            )
            metadata[f"charge_topology_eff_err_{policy_name}_plane_{plane}"] = (
                round(float(eff_error), 6) if np.isfinite(eff_error) else ""
            )
            metadata[f"charge_topology_tt_{tt_missing}_count_{policy_name}_plane_{plane}"] = int(n_three)
            metadata[f"charge_topology_tt_{tt_missing}_rate_hz_{policy_name}_plane_{plane}"] = (
                round(int(n_three) / denominator_seconds, 6) if denominator_seconds > 0 else 0.0
            )

def detect_streamer_threshold(
    df: pd.DataFrame,
    q_sum_cols: list[str],
    *,
    sigma: float = 3.0,
    n_bins: int = 300,
    search_start_quantile: float = 60.0,
) -> float | None:
    """Auto-detect the avalanche–streamer valley in the pooled Q_sum spectrum.

    Pools all non-zero Q_sum values across *q_sum_cols*, builds a smoothed
    histogram, and locates the first local minimum after the avalanche peak
    (searched from *search_start_quantile* of the distribution onward).

    Returns the charge value at the valley, or None if detection fails.
    """
    vals_list = []
    for col in q_sum_cols:
        if col not in df.columns:
            continue
        arr = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
        arr = arr[np.isfinite(arr) & (arr > 0)]
        if arr.size:
            vals_list.append(arr)
    if not vals_list:
        return None
    pooled = np.concatenate(vals_list)
    if pooled.size < 200:
        return None

    q_low = float(np.nanpercentile(pooled, 1))
    q_high = float(np.nanpercentile(pooled, 99.9))
    if q_high <= q_low:
        return None

    counts, edges = np.histogram(pooled, bins=n_bins, range=(q_low, q_high))
    centres = 0.5 * (edges[:-1] + edges[1:])
    smoothed = gaussian_filter1d(counts.astype(float), sigma=sigma)

    # Search for the valley starting from the search_start_quantile
    search_start = float(np.nanpercentile(pooled, search_start_quantile))
    start_idx = int(np.searchsorted(centres, search_start))
    start_idx = max(1, min(start_idx, len(smoothed) - 2))

    # Find first local minimum after avalanche peak
    for idx in range(start_idx, len(smoothed) - 1):
        if smoothed[idx] < smoothed[idx - 1] and smoothed[idx] <= smoothed[idx + 1]:
            return float(centres[idx])

    return None

def _task3_tt_charge_columns(columns: list[str]) -> list[str]:
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
                    f"Q{plane}_F_1",
                    f"Q{plane}_F_2",
                    f"Q{plane}_F_3",
                    f"Q{plane}_F_4",
                    f"Q{plane}_B_1",
                    f"Q{plane}_B_2",
                    f"Q{plane}_B_3",
                    f"Q{plane}_B_4",
                ]
                if col in df.columns
            ]
        charge_columns = _task3_tt_charge_columns(charge_columns)
        if charge_columns:
            charge_values = df.loc[:, charge_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
            has_charge = charge_values.gt(0.0).any(axis=1)
            tt_str = tt_str.where(~has_charge, tt_str + str(plane))
    df.loc[:, column_name] = tt_str.replace("", "0").astype(int)
    return df

def collect_task3_plane_final_map(df: pd.DataFrame) -> dict[int, dict[str, str]]:
    """Return the available plane-level final columns grouped by plane."""
    plane_map: dict[int, dict[str, str]] = {}
    for plane in range(1, 5):
        cols = {
            "T_sum": f"p{plane}_tsum",
            "T_dif": f"p{plane}_tdif",
            "Q_sum": f"p{plane}_qsum",
            "Q_dif": f"p{plane}_qdif",
            "Y": f"p{plane}_ypos",
        }
        if all(col in df.columns for col in cols.values()):
            plane_map[plane] = cols
    return plane_map

def snapshot_original_columns_once(
    frame: pd.DataFrame,
    column_names: Iterable[str],
) -> None:
    """Compatibility hook for normalization callbacks.

    Task 3 currently has no downstream consumer for pre-normalization snapshots,
    but the plane-block normalization helpers accept this callback.
    """
    return None

def normalize_task3_plane_component_blocks(
    df_input: pd.DataFrame,
    *,
    snapshot_originals=None,
    apply_changes: bool = True,
) -> dict[str, int]:
    """Zero each final plane block when any core Q/T component is zero."""
    plane_map = collect_task3_plane_final_map(df_input)
    if not plane_map:
        return {
            "rows_affected": 0,
            "values_zeroed": 0,
            "planes_affected": 0,
        }

    plane_keys = sorted(plane_map)
    q_sum_cols = [plane_map[plane]["Q_sum"] for plane in plane_keys]
    q_dif_cols = [plane_map[plane]["Q_dif"] for plane in plane_keys]
    t_sum_cols = [plane_map[plane]["T_sum"] for plane in plane_keys]
    t_dif_cols = [plane_map[plane]["T_dif"] for plane in plane_keys]
    y_cols = [plane_map[plane]["Y"] for plane in plane_keys]

    q_sum_values = df_input.loc[:, q_sum_cols].to_numpy(copy=True)
    q_dif_values = df_input.loc[:, q_dif_cols].to_numpy(copy=True)
    t_sum_values = df_input.loc[:, t_sum_cols].to_numpy(copy=True)
    t_dif_values = df_input.loc[:, t_dif_cols].to_numpy(copy=True)
    y_values = df_input.loc[:, y_cols].to_numpy(copy=True)

    any_core_zero = (
        (q_sum_values == 0)
        | (q_dif_values == 0)
        | (t_sum_values == 0)
        | (t_dif_values == 0)
    )
    all_core_zero = (
        (q_sum_values == 0)
        & (q_dif_values == 0)
        & (t_sum_values == 0)
        & (t_dif_values == 0)
    )
    partial_zero = any_core_zero & ~all_core_zero

    if snapshot_originals is not None:
        changed_cols: list[str] = []
        for idx, should_zero in enumerate(np.any(partial_zero, axis=0)):
            if not should_zero:
                continue
            changed_cols.extend(
                (
                    q_sum_cols[idx],
                    q_dif_cols[idx],
                    t_sum_cols[idx],
                    t_dif_cols[idx],
                    y_cols[idx],
                )
            )
        if changed_cols:
            snapshot_originals(df_input, changed_cols)

    values_zeroed = 0
    for idx in range(len(plane_keys)):
        plane_mask = partial_zero[:, idx]
        if not np.any(plane_mask):
            continue
        values_zeroed += int(np.count_nonzero(q_sum_values[plane_mask, idx]))
        values_zeroed += int(np.count_nonzero(q_dif_values[plane_mask, idx]))
        values_zeroed += int(np.count_nonzero(t_sum_values[plane_mask, idx]))
        values_zeroed += int(np.count_nonzero(t_dif_values[plane_mask, idx]))
        values_zeroed += int(np.count_nonzero(y_values[plane_mask, idx]))

    if apply_changes:
        q_sum_values[any_core_zero] = 0
        q_dif_values[any_core_zero] = 0
        t_sum_values[any_core_zero] = 0
        t_dif_values[any_core_zero] = 0
        y_values[any_core_zero] = 0

        df_input.loc[:, q_sum_cols] = q_sum_values
        df_input.loc[:, q_dif_cols] = q_dif_values
        df_input.loc[:, t_sum_cols] = t_sum_values
        df_input.loc[:, t_dif_cols] = t_dif_values
        df_input.loc[:, y_cols] = y_values
    return {
        "rows_affected": int(np.count_nonzero(np.any(partial_zero, axis=1))),
        "values_zeroed": int(values_zeroed),
        "planes_affected": int(np.count_nonzero(np.any(partial_zero, axis=0))),
    }


def _task3_plane_order_key(plane_key: int) -> tuple[int]:
    return (plane_key,)

def _task3_plane_offender_metric_key(plane_key: int) -> str:
    return f"plane_combination_filter_offender_count_P{plane_key}"

def _task3_selected_offender_cardinality_metric_key(selected_count: int) -> str:
    return f"plane_combination_filter_rows_with_{selected_count}_selected_offenders"

def _task3_selected_offender_cardinality_rate_metric_key(selected_count: int) -> str:
    return f"{_task3_selected_offender_cardinality_metric_key(selected_count)}_rate_hz"

def _task3_noise_control_efficiency_metric_key(plane: int, selected_count_threshold: int) -> str:
    return (
        f"plane_combination_filter_eff_p{plane}_selected_offenders_le_"
        f"{selected_count_threshold}"
    )

def _task3_noise_control_efficiency_metric_names(
    selected_count_thresholds: Iterable[int],
) -> tuple[str, ...]:
    return tuple(
        _task3_noise_control_efficiency_metric_key(plane, selected_count_threshold)
        for selected_count_threshold in selected_count_thresholds
        for plane in sorted(TASK3_THREE_TO_FOUR_MISSING_TRIGGER_BY_PLANE)
    )


def apply_task3_plane_combination_filter(
    df_input: pd.DataFrame,
    *,
    plane_q_sum_sum_left: float,
    plane_q_sum_sum_right: float,
    plane_q_dif_sum_threshold: float,
    plane_t_sum_sum_left: float,
    plane_t_sum_sum_right: float,
    plane_t_dif_sum_threshold: float,
    plane_y_sum_left: float,
    plane_y_sum_right: float,
    detector_q_sum_sum_left: float,
    detector_q_sum_sum_right: float,
    detector_q_sum_dif_threshold: float,
    detector_q_dif_sum_threshold: float,
    detector_q_dif_dif_threshold: float,
    detector_t_sum_sum_left: float,
    detector_t_sum_sum_right: float,
    detector_t_sum_dif_threshold: float,
    detector_t_dif_sum_threshold: float,
    detector_t_dif_dif_threshold: float,
    detector_y_sum_left: float,
    detector_y_sum_right: float,
    detector_y_dif_threshold: float,
    apply_changes: bool = True,
) -> dict[str, object]:
    """
    Apply the final Task 3 plane-consistency filter in one offender pass.

    Same-plane bounds (`plane_combination_plane_*`) create forced offender
    planes. Distinct-plane detector bounds (`plane_combination_detector_*`)
    create failed edges. Per event, forced planes are kept and the exact
    minimum-cardinality additional offender set is selected to cover the
    remaining failed detector edges. Plane blocks are zeroed only once, after
    the combined selection is resolved.
    """
    plane_map = collect_task3_plane_final_map(df_input)
    detector_limit_keys = TASK3_PLANE_COMBINATION_LIMIT_KEYS
    plane_limit_keys = TASK3_PLANE_SELF_LIMIT_KEYS
    plane_observable_keys = tuple(TASK3_PLANE_SELF_OBSERVABLE_LIMIT_KEYS)
    n_rows = len(df_input)
    if not plane_map:
        return {
            "input_rows": n_rows,
            "tracked_plane_count": len(plane_map),
            "valid_pair_observations": 0,
            "failed_pair_any": 0,
            "failed_pair_q_sum_sum": 0,
            "failed_pair_q_sum_dif": 0,
            "failed_pair_q_dif_sum": 0,
            "failed_pair_q_dif_dif": 0,
            "failed_pair_t_sum_sum": 0,
            "failed_pair_t_sum_dif": 0,
            "failed_pair_t_dif_sum": 0,
            "failed_pair_t_dif_dif": 0,
            "failed_pair_y_sum": 0,
            "failed_pair_y_dif": 0,
            **{f"failed_pair_{limit_key}": 0 for limit_key in detector_limit_keys},
            "plane_candidate_observations": {
                observable_key: 0 for observable_key in plane_observable_keys
            },
            "plane_failed_limits": {
                limit_key: 0 for limit_key in plane_limit_keys
            },
            "plane_rows_failed_limits": {
                limit_key: 0 for limit_key in plane_limit_keys
            },
            "plane_rows_affected": 0,
            "detector_rows_affected": 0,
            "rows_affected": 0,
            "values_zeroed": 0,
            "flagged_rows": 0,
            **{f"rows_failed_{limit_key}": 0 for limit_key in detector_limit_keys},
            "selected_offender_planes": 0,
            "rows_with_multiple_offenders": 0,
            "max_failed_pairs_in_row": 0,
            "max_selected_offenders_in_row": 0,
            "selected_offender_cardinality_counts": {
                selected_count: 0
                for selected_count in TASK3_SELECTED_OFFENDER_CARDINALITY_VALUES
            },
            "selected_offender_counts": {
                plane_key: 0 for plane_key in TASK3_PLANE_KEYS
            },
            "selected_offender_count_by_row": pd.Series(0, index=df_input.index, dtype=int),
            "resolution_exact_by_row": pd.Series(True, index=df_input.index, dtype=bool),
            "selected_offender_mask_by_plane": {
                plane_key: pd.Series(False, index=df_input.index, dtype=bool)
                for plane_key in TASK3_PLANE_KEYS
            },
        }

    plane_fail_masks = {
        plane_key: np.zeros(n_rows, dtype=bool)
        for plane_key in TASK3_PLANE_KEYS
    }
    summary = {
        "input_rows": n_rows,
        "tracked_plane_count": len(plane_map),
        "valid_pair_observations": 0,
        "failed_pair_any": 0,
        "failed_pair_q_sum_sum": 0,
        "failed_pair_q_sum_dif": 0,
        "failed_pair_q_dif_sum": 0,
        "failed_pair_q_dif_dif": 0,
        "failed_pair_t_sum_sum": 0,
        "failed_pair_t_sum_dif": 0,
        "failed_pair_t_dif_sum": 0,
        "failed_pair_t_dif_dif": 0,
        "failed_pair_y_sum": 0,
        "failed_pair_y_dif": 0,
        **{f"failed_pair_{limit_key}": 0 for limit_key in detector_limit_keys},
        "plane_candidate_observations": {
            observable_key: 0 for observable_key in plane_observable_keys
        },
        "plane_failed_limits": {
            limit_key: 0 for limit_key in plane_limit_keys
        },
        "plane_rows_failed_limits": {
            limit_key: 0 for limit_key in plane_limit_keys
        },
        "plane_rows_affected": 0,
        "detector_rows_affected": 0,
        "rows_affected": 0,
        "values_zeroed": 0,
        "flagged_rows": 0,
        **{f"rows_failed_{limit_key}": 0 for limit_key in detector_limit_keys},
        "selected_offender_planes": 0,
        "rows_with_multiple_offenders": 0,
        "max_failed_pairs_in_row": 0,
        "max_selected_offenders_in_row": 0,
        "selected_offender_cardinality_counts": {
            selected_count: 0
            for selected_count in TASK3_SELECTED_OFFENDER_CARDINALITY_VALUES
        },
    }
    row_failed_edges: dict[int, list[tuple[int, int, float]]] = {}
    row_forced_planes: dict[int, set[int]] = {}
    offender_hit_counts = {
        plane_key: 0
        for plane_key in TASK3_PLANE_KEYS
    }
    row_limit_fail_masks = {
        limit_key: np.zeros(n_rows, dtype=bool)
        for limit_key in detector_limit_keys
    }
    row_plane_limit_fail_masks = {
        limit_key: np.zeros(n_rows, dtype=bool)
        for limit_key in plane_limit_keys
    }
    row_detector_failure_any = np.zeros(n_rows, dtype=bool)
    row_plane_failure_any = np.zeros(n_rows, dtype=bool)
    selected_offender_count_by_row = np.zeros(n_rows, dtype=int)
    resolution_exact_by_row = np.ones(n_rows, dtype=bool)

    plane_q_dif_sum_abs = abs(float(plane_q_dif_sum_threshold))
    plane_t_dif_sum_abs = abs(float(plane_t_dif_sum_threshold))

    detector_q_sum_dif_abs = abs(float(detector_q_sum_dif_threshold))
    detector_q_dif_sum_abs = abs(float(detector_q_dif_sum_threshold))
    detector_q_dif_dif_abs = abs(float(detector_q_dif_dif_threshold))
    detector_t_sum_dif_abs = abs(float(detector_t_sum_dif_threshold))
    detector_t_dif_sum_abs = abs(float(detector_t_dif_sum_threshold))
    detector_t_dif_dif_abs = abs(float(detector_t_dif_dif_threshold))
    detector_y_dif_abs = abs(float(detector_y_dif_threshold))

    for plane_key in sorted(plane_map):
        cols = plane_map[plane_key]
        q_sum = pd.to_numeric(df_input[cols["Q_sum"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        q_dif = pd.to_numeric(df_input[cols["Q_dif"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        t_sum = pd.to_numeric(df_input[cols["T_sum"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        t_dif = pd.to_numeric(df_input[cols["T_dif"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        y = pd.to_numeric(df_input[cols["Y"]], errors="coerce").fillna(0).to_numpy(dtype=float)

        valid_q_sum = np.isfinite(q_sum) & (q_sum != 0)
        valid_q_dif = np.isfinite(q_dif) & (q_dif != 0)
        valid_t_sum = np.isfinite(t_sum) & (t_sum != 0)
        valid_t_dif = np.isfinite(t_dif) & (t_dif != 0)
        valid_y = np.isfinite(y) & (y != 0)

        fail_q_sum_sum_low = valid_q_sum & (q_sum < float(plane_q_sum_sum_left))
        fail_q_sum_sum_high = valid_q_sum & (q_sum > float(plane_q_sum_sum_right))
        fail_q_dif_sum_low = valid_q_dif & (q_dif < -plane_q_dif_sum_abs)
        fail_q_dif_sum_high = valid_q_dif & (q_dif > plane_q_dif_sum_abs)
        fail_t_sum_sum_low = valid_t_sum & (t_sum < float(plane_t_sum_sum_left))
        fail_t_sum_sum_high = valid_t_sum & (t_sum > float(plane_t_sum_sum_right))
        fail_t_dif_sum_low = valid_t_dif & (t_dif < -plane_t_dif_sum_abs)
        fail_t_dif_sum_high = valid_t_dif & (t_dif > plane_t_dif_sum_abs)
        fail_y_sum_low = valid_y & (y < float(plane_y_sum_left))
        fail_y_sum_high = valid_y & (y > float(plane_y_sum_right))

        summary["plane_candidate_observations"]["q_sum_sum"] += int(np.count_nonzero(valid_q_sum))
        summary["plane_candidate_observations"]["q_dif_sum"] += int(np.count_nonzero(valid_q_dif))
        summary["plane_candidate_observations"]["t_sum_sum"] += int(np.count_nonzero(valid_t_sum))
        summary["plane_candidate_observations"]["t_dif_sum"] += int(np.count_nonzero(valid_t_dif))
        summary["plane_candidate_observations"]["y_sum"] += int(np.count_nonzero(valid_y))

        plane_fail_masks_by_limit = {
            "q_sum_sum_low": fail_q_sum_sum_low,
            "q_sum_sum_high": fail_q_sum_sum_high,
            "q_dif_sum_low": fail_q_dif_sum_low,
            "q_dif_sum_high": fail_q_dif_sum_high,
            "t_sum_sum_low": fail_t_sum_sum_low,
            "t_sum_sum_high": fail_t_sum_sum_high,
            "t_dif_sum_low": fail_t_dif_sum_low,
            "t_dif_sum_high": fail_t_dif_sum_high,
            "y_sum_low": fail_y_sum_low,
            "y_sum_high": fail_y_sum_high,
        }
        fail_any = np.zeros(n_rows, dtype=bool)
        for limit_key, limit_fail_mask in plane_fail_masks_by_limit.items():
            summary["plane_failed_limits"][limit_key] += int(np.count_nonzero(limit_fail_mask))
            row_plane_limit_fail_masks[limit_key] |= limit_fail_mask
            fail_any |= limit_fail_mask
        row_plane_failure_any |= fail_any

        for row_pos in np.flatnonzero(fail_any):
            row_forced_planes.setdefault(int(row_pos), set()).add(plane_key)

    for plane_a, plane_b in combinations(sorted(plane_map), 2):
        cols_a = plane_map[plane_a]
        cols_b = plane_map[plane_b]
        q_sum_a = pd.to_numeric(df_input[cols_a["Q_sum"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        q_sum_b = pd.to_numeric(df_input[cols_b["Q_sum"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        q_dif_a = pd.to_numeric(df_input[cols_a["Q_dif"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        q_dif_b = pd.to_numeric(df_input[cols_b["Q_dif"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        t_sum_a = pd.to_numeric(df_input[cols_a["T_sum"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        t_sum_b = pd.to_numeric(df_input[cols_b["T_sum"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        t_dif_a = pd.to_numeric(df_input[cols_a["T_dif"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        t_dif_b = pd.to_numeric(df_input[cols_b["T_dif"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        y_a = pd.to_numeric(df_input[cols_a["Y"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        y_b = pd.to_numeric(df_input[cols_b["Y"]], errors="coerce").fillna(0).to_numpy(dtype=float)

        valid_mask = (
            np.isfinite(q_sum_a)
            & np.isfinite(q_sum_b)
            & np.isfinite(q_dif_a)
            & np.isfinite(q_dif_b)
            & np.isfinite(t_sum_a)
            & np.isfinite(t_sum_b)
            & np.isfinite(t_dif_a)
            & np.isfinite(t_dif_b)
            & np.isfinite(y_a)
            & np.isfinite(y_b)
            & (q_sum_a != 0)
            & (q_sum_b != 0)
            & (q_dif_a != 0)
            & (q_dif_b != 0)
            & (t_sum_a != 0)
            & (t_sum_b != 0)
            & (t_dif_a != 0)
            & (t_dif_b != 0)
            & (y_a != 0)
            & (y_b != 0)
        )
        if not np.any(valid_mask):
            continue

        summary["valid_pair_observations"] += int(np.count_nonzero(valid_mask))
        pair_q_sum_sum = 0.5 * (q_sum_a + q_sum_b)
        pair_q_sum_dif = 0.5 * (q_sum_a - q_sum_b)
        pair_q_dif_sum = 0.5 * (q_dif_a + q_dif_b)
        pair_q_dif_dif = 0.5 * (q_dif_a - q_dif_b)
        pair_t_sum_sum = 0.5 * (t_sum_a + t_sum_b)
        pair_t_sum_dif = 0.5 * (t_sum_a - t_sum_b)
        pair_t_dif_sum = 0.5 * (t_dif_a + t_dif_b)
        pair_t_dif_dif = 0.5 * (t_dif_a - t_dif_b)
        pair_y_sum = 0.5 * (y_a + y_b)
        pair_y_dif = 0.5 * (y_a - y_b)

        fail_q_sum_sum_low = valid_mask & (pair_q_sum_sum < float(detector_q_sum_sum_left))
        fail_q_sum_sum_high = valid_mask & (pair_q_sum_sum > float(detector_q_sum_sum_right))
        fail_q_sum_sum = fail_q_sum_sum_low | fail_q_sum_sum_high
        fail_q_sum_dif_low = valid_mask & (pair_q_sum_dif < -detector_q_sum_dif_abs)
        fail_q_sum_dif_high = valid_mask & (pair_q_sum_dif > detector_q_sum_dif_abs)
        fail_q_sum_dif = fail_q_sum_dif_low | fail_q_sum_dif_high
        fail_q_dif_sum_low = valid_mask & (pair_q_dif_sum < -detector_q_dif_sum_abs)
        fail_q_dif_sum_high = valid_mask & (pair_q_dif_sum > detector_q_dif_sum_abs)
        fail_q_dif_sum = fail_q_dif_sum_low | fail_q_dif_sum_high
        fail_q_dif_dif_low = valid_mask & (pair_q_dif_dif < -detector_q_dif_dif_abs)
        fail_q_dif_dif_high = valid_mask & (pair_q_dif_dif > detector_q_dif_dif_abs)
        fail_q_dif_dif = fail_q_dif_dif_low | fail_q_dif_dif_high
        fail_t_sum_sum_low = valid_mask & (pair_t_sum_sum < float(detector_t_sum_sum_left))
        fail_t_sum_sum_high = valid_mask & (pair_t_sum_sum > float(detector_t_sum_sum_right))
        fail_t_sum_sum = fail_t_sum_sum_low | fail_t_sum_sum_high
        fail_t_sum_dif_low = valid_mask & (pair_t_sum_dif < -detector_t_sum_dif_abs)
        fail_t_sum_dif_high = valid_mask & (pair_t_sum_dif > detector_t_sum_dif_abs)
        fail_t_sum_dif = fail_t_sum_dif_low | fail_t_sum_dif_high
        fail_t_dif_sum_low = valid_mask & (pair_t_dif_sum < -detector_t_dif_sum_abs)
        fail_t_dif_sum_high = valid_mask & (pair_t_dif_sum > detector_t_dif_sum_abs)
        fail_t_dif_sum = fail_t_dif_sum_low | fail_t_dif_sum_high
        fail_t_dif_dif_low = valid_mask & (pair_t_dif_dif < -detector_t_dif_dif_abs)
        fail_t_dif_dif_high = valid_mask & (pair_t_dif_dif > detector_t_dif_dif_abs)
        fail_t_dif_dif = fail_t_dif_dif_low | fail_t_dif_dif_high
        fail_y_sum_low = valid_mask & (pair_y_sum < float(detector_y_sum_left))
        fail_y_sum_high = valid_mask & (pair_y_sum > float(detector_y_sum_right))
        fail_y_sum = fail_y_sum_low | fail_y_sum_high
        fail_y_dif_low = valid_mask & (pair_y_dif < -detector_y_dif_abs)
        fail_y_dif_high = valid_mask & (pair_y_dif > detector_y_dif_abs)
        fail_y_dif = fail_y_dif_low | fail_y_dif_high

        fail_masks_by_limit = {
            "q_sum_sum_low": fail_q_sum_sum_low,
            "q_sum_sum_high": fail_q_sum_sum_high,
            "q_sum_dif_low": fail_q_sum_dif_low,
            "q_sum_dif_high": fail_q_sum_dif_high,
            "q_dif_sum_low": fail_q_dif_sum_low,
            "q_dif_sum_high": fail_q_dif_sum_high,
            "q_dif_dif_low": fail_q_dif_dif_low,
            "q_dif_dif_high": fail_q_dif_dif_high,
            "t_sum_sum_low": fail_t_sum_sum_low,
            "t_sum_sum_high": fail_t_sum_sum_high,
            "t_sum_dif_low": fail_t_sum_dif_low,
            "t_sum_dif_high": fail_t_sum_dif_high,
            "t_dif_sum_low": fail_t_dif_sum_low,
            "t_dif_sum_high": fail_t_dif_sum_high,
            "t_dif_dif_low": fail_t_dif_dif_low,
            "t_dif_dif_high": fail_t_dif_dif_high,
            "y_sum_low": fail_y_sum_low,
            "y_sum_high": fail_y_sum_high,
            "y_dif_low": fail_y_dif_low,
            "y_dif_high": fail_y_dif_high,
        }
        fail_any = (
            fail_q_sum_sum
            | fail_q_sum_dif
            | fail_q_dif_sum
            | fail_q_dif_dif
            | fail_t_sum_sum
            | fail_t_sum_dif
            | fail_t_dif_sum
            | fail_t_dif_dif
            | fail_y_sum
            | fail_y_dif
        )

        summary["failed_pair_q_sum_sum"] += int(np.count_nonzero(fail_q_sum_sum))
        summary["failed_pair_q_sum_dif"] += int(np.count_nonzero(fail_q_sum_dif))
        summary["failed_pair_q_dif_sum"] += int(np.count_nonzero(fail_q_dif_sum))
        summary["failed_pair_q_dif_dif"] += int(np.count_nonzero(fail_q_dif_dif))
        summary["failed_pair_t_sum_sum"] += int(np.count_nonzero(fail_t_sum_sum))
        summary["failed_pair_t_sum_dif"] += int(np.count_nonzero(fail_t_sum_dif))
        summary["failed_pair_t_dif_sum"] += int(np.count_nonzero(fail_t_dif_sum))
        summary["failed_pair_t_dif_dif"] += int(np.count_nonzero(fail_t_dif_dif))
        summary["failed_pair_y_sum"] += int(np.count_nonzero(fail_y_sum))
        summary["failed_pair_y_dif"] += int(np.count_nonzero(fail_y_dif))
        for limit_key, limit_fail_mask in fail_masks_by_limit.items():
            summary[f"failed_pair_{limit_key}"] += int(np.count_nonzero(limit_fail_mask))
            row_limit_fail_masks[limit_key] |= limit_fail_mask
        summary["failed_pair_any"] += int(np.count_nonzero(fail_any))
        row_detector_failure_any |= fail_any

        if np.any(fail_any):
            q_sum_sum_width = max(abs(float(detector_q_sum_sum_right) - float(detector_q_sum_sum_left)), 1e-9)
            q_sum_dif_scale = max(abs(float(detector_q_sum_dif_threshold)), 1e-9)
            q_dif_sum_scale = max(abs(float(detector_q_dif_sum_threshold)), 1e-9)
            q_dif_dif_scale = max(abs(float(detector_q_dif_dif_threshold)), 1e-9)
            t_sum_sum_width = max(abs(float(detector_t_sum_sum_right) - float(detector_t_sum_sum_left)), 1e-9)
            t_sum_dif_scale = max(abs(float(detector_t_sum_dif_threshold)), 1e-9)
            t_dif_sum_scale = max(abs(float(detector_t_dif_sum_threshold)), 1e-9)
            t_dif_dif_scale = max(abs(float(detector_t_dif_dif_threshold)), 1e-9)
            y_sum_width = max(abs(float(detector_y_sum_right) - float(detector_y_sum_left)), 1e-9)
            y_dif_scale = max(abs(float(detector_y_dif_threshold)), 1e-9)

            q_sum_sum_excess = np.maximum.reduce(
                [
                    np.zeros_like(pair_q_sum_sum, dtype=float),
                    float(detector_q_sum_sum_left) - pair_q_sum_sum,
                    pair_q_sum_sum - float(detector_q_sum_sum_right),
                ]
            ) / q_sum_sum_width
            q_sum_dif_excess = (
                np.maximum(np.abs(pair_q_sum_dif) - abs(float(detector_q_sum_dif_threshold)), 0.0)
                / q_sum_dif_scale
            )
            q_dif_sum_excess = (
                np.maximum(np.abs(pair_q_dif_sum) - abs(float(detector_q_dif_sum_threshold)), 0.0)
                / q_dif_sum_scale
            )
            q_dif_dif_excess = (
                np.maximum(np.abs(pair_q_dif_dif) - abs(float(detector_q_dif_dif_threshold)), 0.0)
                / q_dif_dif_scale
            )
            t_sum_sum_excess = np.maximum.reduce(
                [
                    np.zeros_like(pair_t_sum_sum, dtype=float),
                    float(detector_t_sum_sum_left) - pair_t_sum_sum,
                    pair_t_sum_sum - float(detector_t_sum_sum_right),
                ]
            ) / t_sum_sum_width
            t_sum_dif_excess = (
                np.maximum(np.abs(pair_t_sum_dif) - abs(float(detector_t_sum_dif_threshold)), 0.0)
                / t_sum_dif_scale
            )
            t_dif_sum_excess = (
                np.maximum(np.abs(pair_t_dif_sum) - abs(float(detector_t_dif_sum_threshold)), 0.0)
                / t_dif_sum_scale
            )
            t_dif_dif_excess = (
                np.maximum(np.abs(pair_t_dif_dif) - abs(float(detector_t_dif_dif_threshold)), 0.0)
                / t_dif_dif_scale
            )
            y_sum_excess = np.maximum.reduce(
                [
                    np.zeros_like(pair_y_sum, dtype=float),
                    float(detector_y_sum_left) - pair_y_sum,
                    pair_y_sum - float(detector_y_sum_right),
                ]
            ) / y_sum_width
            y_dif_excess = (
                np.maximum(np.abs(pair_y_dif) - abs(float(detector_y_dif_threshold)), 0.0)
                / y_dif_scale
            )
            pair_severity = (
                q_sum_sum_excess
                + q_sum_dif_excess
                + q_dif_sum_excess
                + q_dif_dif_excess
                + t_sum_sum_excess
                + t_sum_dif_excess
                + t_dif_sum_excess
                + t_dif_dif_excess
                + y_sum_excess
                + y_dif_excess
            )
            pair_severity = np.where(fail_any, pair_severity, 0.0)
            pair_severity = np.where(fail_any & (pair_severity <= 0), 1.0, pair_severity)
            for row_pos in np.flatnonzero(fail_any):
                row_failed_edges.setdefault(int(row_pos), []).append(
                    (plane_a, plane_b, float(pair_severity[row_pos]))
                )

    flagged_row_positions = sorted(set(row_failed_edges) | set(row_forced_planes))
    any_row_affected = np.zeros(n_rows, dtype=bool)
    summary["flagged_rows"] = len(flagged_row_positions)
    summary["plane_rows_affected"] = int(np.count_nonzero(row_plane_failure_any))
    summary["detector_rows_affected"] = int(np.count_nonzero(row_detector_failure_any))

    for row_pos in flagged_row_positions:
        forced_planes = sorted(
            row_forced_planes.get(row_pos, set()),
            key=_task3_plane_order_key,
        )
        edge_list = row_failed_edges.get(row_pos, [])
        uncovered_edges = [
            (plane_a, plane_b, severity)
            for plane_a, plane_b, severity in edge_list
            if plane_a not in forced_planes and plane_b not in forced_planes
        ]
        selected_planes = forced_planes + select_exact_minimum_vertex_cover(
            uncovered_edges,
            _task3_plane_order_key,
        )
        selected_plane_set = set(selected_planes)
        unresolved_edges = [
            (plane_a, plane_b, severity)
            for plane_a, plane_b, severity in edge_list
            if plane_a not in selected_plane_set and plane_b not in selected_plane_set
        ]
        resolution_exact_by_row[row_pos] = len(unresolved_edges) == 0

        summary["max_failed_pairs_in_row"] = max(
            summary["max_failed_pairs_in_row"],
            len(edge_list) + len(forced_planes),
        )
        summary["max_selected_offenders_in_row"] = max(
            summary["max_selected_offenders_in_row"],
            len(selected_planes),
        )
        summary["selected_offender_planes"] += len(selected_planes)
        if len(selected_planes) > 1:
            summary["rows_with_multiple_offenders"] += 1
        summary["selected_offender_cardinality_counts"][len(selected_planes)] = (
            int(summary["selected_offender_cardinality_counts"].get(len(selected_planes), 0)) + 1
        )
        selected_offender_count_by_row[row_pos] = len(selected_planes)
        for plane_key in selected_planes:
            plane_fail_masks[plane_key][row_pos] = True
            offender_hit_counts[plane_key] += 1

    summary["selected_offender_cardinality_counts"][0] = max(
        int(summary["input_rows"]) - int(summary["flagged_rows"]),
        0,
    )
    for limit_key, row_fail_mask in row_limit_fail_masks.items():
        summary[f"rows_failed_{limit_key}"] = int(np.count_nonzero(row_fail_mask))
    for limit_key, row_fail_mask in row_plane_limit_fail_masks.items():
        summary["plane_rows_failed_limits"][limit_key] = int(np.count_nonzero(row_fail_mask))

    for plane_key in plane_map:
        fail_mask = plane_fail_masks[plane_key]
        if not np.any(fail_mask):
            continue
        cols = plane_map[plane_key]
        for variable_name in ("T_sum", "T_dif", "Q_sum", "Q_dif", "Y"):
            values = pd.to_numeric(df_input[cols[variable_name]], errors="coerce").fillna(0)
            summary["values_zeroed"] += int((values[fail_mask] != 0).sum())
        any_row_affected |= fail_mask
        if apply_changes:
            # Legacy destructive mode only; final working_df calls use apply_changes=False.
            df_input.loc[fail_mask, list(cols.values())] = 0

    summary["rows_affected"] = int(np.count_nonzero(any_row_affected))
    top_offenders = sorted(
        (
            (plane_key, count)
            for plane_key, count in offender_hit_counts.items()
            if count > 0
        ),
        key=lambda item: (-item[1], *_task3_plane_order_key(item[0])),
    )[:8]
    if top_offenders:
        top_offenders_str = ", ".join(
            f"P{plane}:{count}"
            for plane, count in top_offenders
        )
        print(
            "[plane-combination-offenders] "
            f"flagged_rows={summary['flagged_rows']} "
            f"plane_rows={summary['plane_rows_affected']} "
            f"detector_rows={summary['detector_rows_affected']} "
            f"selected_offenders={summary['selected_offender_planes']} "
            f"multi_offender_rows={summary['rows_with_multiple_offenders']} "
            f"max_failed_pairs_in_row={summary['max_failed_pairs_in_row']} "
            f"top={top_offenders_str}"
        )

    summary["selected_offender_mask_by_plane"] = {
        plane_key: pd.Series(plane_fail_masks.get(plane_key, np.zeros(len(df_input), dtype=bool)), index=df_input.index, dtype=bool)
        for plane_key in TASK3_PLANE_KEYS
    }
    summary["selected_offender_counts"] = {
        plane_key: int(offender_hit_counts.get(plane_key, 0))
        for plane_key in TASK3_PLANE_KEYS
    }
    summary["selected_offender_count_by_row"] = pd.Series(
        selected_offender_count_by_row,
        index=df_input.index,
        dtype=int,
    )
    summary["resolution_exact_by_row"] = pd.Series(
        resolution_exact_by_row,
        index=df_input.index,
        dtype=bool,
    )
    return summary


def _task3_filter_tt_series(df: pd.DataFrame) -> pd.Series:
    for candidate in ("tt_task3_list", "tt_task2_cal", "tt_task1_clean", "tt_task0_raw"):
        if candidate in df.columns:
            return df[candidate].apply(normalize_tt_label).astype(str)
    return pd.Series(["0"] * len(df), index=df.index, dtype=str)

def collect_task3_plane_combination_histogram_payload(
    df_input: pd.DataFrame,
    tt_series: pd.Series,
    *,
    relation_type: str = "any",
) -> pd.DataFrame:
    relation_type = {
        "plane": "same_plane",
        "detector": "any",
        "same_plane": "same_plane",
        "self": "same_plane",
        "any": "any",
    }.get(relation_type, relation_type)
    payload_rows: list[pd.DataFrame] = []
    plane_map = collect_task3_plane_final_map(df_input)
    payload_columns = [
        "row_index",
        "tt",
        "combo",
        *[observable for observable, _ in TASK3_PLANE_COMBINATION_OBSERVABLES],
    ]
    if relation_type not in {"self", "same_plane", "any"}:
        raise ValueError(f"Unsupported Task 3 plane-combination relation type: {relation_type}")
    if relation_type in {"self", "same_plane"} and len(plane_map) < 1:
        return pd.DataFrame(columns=payload_columns)
    if relation_type == "any" and len(plane_map) < 2:
        return pd.DataFrame(columns=payload_columns)

    tt_series = tt_series.reindex(df_input.index).fillna("0").astype(str)
    if relation_type in {"self", "same_plane"}:
        for plane_key in sorted(plane_map):
            combo_label = f"P{plane_key}"
            cols = plane_map[plane_key]
            q_sum = pd.to_numeric(df_input[cols["Q_sum"]], errors="coerce").fillna(0).to_numpy(dtype=float)
            q_dif = pd.to_numeric(df_input[cols["Q_dif"]], errors="coerce").fillna(0).to_numpy(dtype=float)
            t_sum = pd.to_numeric(df_input[cols["T_sum"]], errors="coerce").fillna(0).to_numpy(dtype=float)
            t_dif = pd.to_numeric(df_input[cols["T_dif"]], errors="coerce").fillna(0).to_numpy(dtype=float)
            y_value = pd.to_numeric(df_input[cols["Y"]], errors="coerce").fillna(0).to_numpy(dtype=float)

            valid_mask = (
                np.isfinite(q_sum)
                & np.isfinite(q_dif)
                & np.isfinite(t_sum)
                & np.isfinite(t_dif)
                & np.isfinite(y_value)
                & (q_sum != 0)
                & (q_dif != 0)
                & (t_sum != 0)
                & (t_dif != 0)
                & (y_value != 0)
            )
            if not np.any(valid_mask):
                continue

            valid_index = df_input.index[valid_mask]
            zeros = np.zeros_like(q_sum, dtype=float)
            derived_values = {
                "q_sum_sum": q_sum,
                "q_sum_dif": zeros,
                "q_dif_sum": q_dif,
                "q_dif_dif": zeros,
                "t_sum_sum": t_sum,
                "t_sum_dif": zeros,
                "t_dif_sum": t_dif,
                "t_dif_dif": zeros,
                "y_sum": y_value,
                "y_dif": zeros,
            }
            payload_rows.append(
                pd.DataFrame(
                    {
                        "row_index": valid_index.to_numpy(dtype=int, copy=False),
                        "tt": tt_series.loc[valid_index].to_numpy(dtype=str),
                        "combo": combo_label,
                        **{
                            observable: values[valid_mask]
                            for observable, values in derived_values.items()
                        },
                    }
                )
            )
    else:
        for plane_a, plane_b in combinations(sorted(plane_map), 2):
            combo_label = f"{plane_a}{plane_b}"
            cols_a = plane_map[plane_a]
            cols_b = plane_map[plane_b]
            q_sum_a = pd.to_numeric(df_input[cols_a["Q_sum"]], errors="coerce").fillna(0).to_numpy(dtype=float)
            q_sum_b = pd.to_numeric(df_input[cols_b["Q_sum"]], errors="coerce").fillna(0).to_numpy(dtype=float)
            q_dif_a = pd.to_numeric(df_input[cols_a["Q_dif"]], errors="coerce").fillna(0).to_numpy(dtype=float)
            q_dif_b = pd.to_numeric(df_input[cols_b["Q_dif"]], errors="coerce").fillna(0).to_numpy(dtype=float)
            t_sum_a = pd.to_numeric(df_input[cols_a["T_sum"]], errors="coerce").fillna(0).to_numpy(dtype=float)
            t_sum_b = pd.to_numeric(df_input[cols_b["T_sum"]], errors="coerce").fillna(0).to_numpy(dtype=float)
            t_dif_a = pd.to_numeric(df_input[cols_a["T_dif"]], errors="coerce").fillna(0).to_numpy(dtype=float)
            t_dif_b = pd.to_numeric(df_input[cols_b["T_dif"]], errors="coerce").fillna(0).to_numpy(dtype=float)
            y_a = pd.to_numeric(df_input[cols_a["Y"]], errors="coerce").fillna(0).to_numpy(dtype=float)
            y_b = pd.to_numeric(df_input[cols_b["Y"]], errors="coerce").fillna(0).to_numpy(dtype=float)

            valid_mask = (
                np.isfinite(q_sum_a)
                & np.isfinite(q_sum_b)
                & np.isfinite(q_dif_a)
                & np.isfinite(q_dif_b)
                & np.isfinite(t_sum_a)
                & np.isfinite(t_sum_b)
                & np.isfinite(t_dif_a)
                & np.isfinite(t_dif_b)
                & np.isfinite(y_a)
                & np.isfinite(y_b)
                & (q_sum_a != 0)
                & (q_sum_b != 0)
                & (q_dif_a != 0)
                & (q_dif_b != 0)
                & (t_sum_a != 0)
                & (t_sum_b != 0)
                & (t_dif_a != 0)
                & (t_dif_b != 0)
                & (y_a != 0)
                & (y_b != 0)
            )
            if not np.any(valid_mask):
                continue

            valid_index = df_input.index[valid_mask]
            tt_values = tt_series.loc[valid_index].to_numpy(dtype=str)
            derived_values = {
                "q_sum_sum": 0.5 * (q_sum_a + q_sum_b),
                "q_sum_dif": 0.5 * (q_sum_a - q_sum_b),
                "q_dif_sum": 0.5 * (q_dif_a + q_dif_b),
                "q_dif_dif": 0.5 * (q_dif_a - q_dif_b),
                "t_sum_sum": 0.5 * (t_sum_a + t_sum_b),
                "t_sum_dif": 0.5 * (t_sum_a - t_sum_b),
                "t_dif_sum": 0.5 * (t_dif_a + t_dif_b),
                "t_dif_dif": 0.5 * (t_dif_a - t_dif_b),
                "y_sum": 0.5 * (y_a + y_b),
                "y_dif": 0.5 * (y_a - y_b),
            }
            payload_rows.append(
                pd.DataFrame(
                    {
                        "row_index": valid_index.to_numpy(dtype=int, copy=False),
                        "tt": tt_values,
                        "combo": combo_label,
                        **{
                            observable: values[valid_mask]
                            for observable, values in derived_values.items()
                        },
                    }
                )
            )

    if not payload_rows:
        return pd.DataFrame(columns=payload_columns)
    return pd.concat(payload_rows, ignore_index=True)

def subtract_task3_plane_combination_payload(
    left_payload: pd.DataFrame,
    right_payload: pd.DataFrame,
) -> pd.DataFrame:
    if left_payload.empty:
        return left_payload.copy()
    if right_payload.empty or not {"row_index", "combo"}.issubset(left_payload.columns) or not {"row_index", "combo"}.issubset(right_payload.columns):
        return left_payload.copy()

    reduced_right = right_payload.loc[:, ["row_index", "combo"]].drop_duplicates()
    removed_payload = left_payload.merge(
        reduced_right,
        on=["row_index", "combo"],
        how="left",
        indicator=True,
    )
    return removed_payload.loc[removed_payload["_merge"] == "left_only"].drop(columns="_merge")

def _task3_full_data_range(
    values: np.ndarray,
    limits: tuple[float | None, float | None],
) -> tuple[float, float]:
    finite_values = values[np.isfinite(values)]
    lower_limit, upper_limit = limits
    if finite_values.size:
        low = float(np.nanmin(finite_values))
        high = float(np.nanmax(finite_values))
    else:
        low, high = -1.0, 1.0
    if lower_limit is not None:
        low = min(low, float(lower_limit))
    if upper_limit is not None:
        high = max(high, float(upper_limit))
    if not np.isfinite(low) or not np.isfinite(high) or low == high:
        center = float(low if np.isfinite(low) else 0.0)
        low, high = center - 1.0, center + 1.0
    span = high - low
    padding = 0.05 * span if span > 0 else max(1.0, 0.05 * max(abs(low), abs(high), 1.0))
    return low - padding, high + padding

def _task3_hist_range(
    before_values: np.ndarray,
    after_values: np.ndarray,
    limits: tuple[float | None, float | None],
    *,
    boundary_expansion_factor: float = 1.5,
) -> tuple[float, float]:
    finite_values = np.concatenate(
        [
            before_values[np.isfinite(before_values)],
            after_values[np.isfinite(after_values)],
        ]
    )
    lower_limit, upper_limit = limits
    lower_limit = float(lower_limit) if lower_limit is not None and np.isfinite(lower_limit) else None
    upper_limit = float(upper_limit) if upper_limit is not None and np.isfinite(upper_limit) else None

    if finite_values.size:
        data_low = float(np.nanmin(finite_values))
        data_high = float(np.nanmax(finite_values))
    else:
        data_low, data_high = np.nan, np.nan

    if lower_limit is not None and upper_limit is not None and upper_limit > lower_limit:
        center = 0.5 * (lower_limit + upper_limit)
        half_span = 0.5 * (upper_limit - lower_limit)
        cap_low = center - boundary_expansion_factor * half_span
        cap_high = center + boundary_expansion_factor * half_span
    else:
        return _task3_full_data_range(finite_values, limits)

    low = lower_limit
    high = upper_limit
    if np.isfinite(data_low):
        low = min(low, data_low)
    if np.isfinite(data_high):
        high = max(high, data_high)

    low = max(low, cap_low)
    high = min(high, cap_high)

    if not np.isfinite(low) or not np.isfinite(high) or low >= high:
        low, high = cap_low, cap_high

    span = high - low
    padding = 0.04 * span if span > 0 else max(0.5, 0.04 * max(abs(low), abs(high), 1.0))
    return low - padding, high + padding

def _task3_population_color(label: str) -> tuple[float, float, float, float]:
    digest = hashlib.md5(label.encode("utf-8")).digest()
    color_pos = int.from_bytes(digest[:4], "big") / float(2**32 - 1)
    return plt.get_cmap("turbo")(0.08 + 0.84 * color_pos)

def plot_task3_plane_combination_filter_by_tt(
    original_payload: pd.DataFrame,
    before_payload: pd.DataFrame,
    after_payload: pd.DataFrame,
    basename_no_ext_value: str,
    fig_idx_value: int,
    base_dir: str,
    *,
    show_plots: bool,
    save_plots: bool,
    plot_list: list[str] | None,
    limits_by_observable: dict[str, tuple[float | None, float | None]],
    relation_label: str,
    observable_definitions: tuple[tuple[str, str], ...] | None = None,
) -> int:
    if observable_definitions is None:
        observable_definitions = TASK3_PLANE_COMBINATION_OBSERVABLES
    original_payload = original_payload.copy()
    before_payload = before_payload.copy()
    after_payload = after_payload.copy()
    removed_marker = str(config.get("removed_marker", "x"))
    removed_marker_size = int(config.get("removed_marker_size", 20))
    removed_marker_alpha = float(config.get("removed_marker_alpha", 0.9))
    tt_labels = []
    for payload in (original_payload, before_payload, after_payload):
        if "tt" in payload.columns:
            tt_labels.extend(payload["tt"].astype(str).tolist())
    ordered_tts = [
        tt_label for tt_label in TT_COLOR_LABELS
        if tt_label != "0" and tt_label in set(tt_labels)
    ]
    observable_names = [observable for observable, _ in observable_definitions]
    observable_labels = {observable: label for observable, label in observable_definitions}
    scatter_max_points = 5000
    prefilter_scatter_size = max(3, int(round(0.25 * removed_marker_size)))
    removed_scatter_marker_size = max(8, int(round(0.6 * removed_marker_size)))
    rng = np.random.default_rng(0)

    for tt_label in ordered_tts:
        original_tt_all = original_payload.loc[
            original_payload.get("tt", pd.Series(dtype=str)).astype(str) == tt_label
        ].copy()
        before_tt_all = before_payload.loc[
            before_payload.get("tt", pd.Series(dtype=str)).astype(str) == tt_label
        ].copy()
        after_tt_all = after_payload.loc[
            after_payload.get("tt", pd.Series(dtype=str)).astype(str) == tt_label
        ].copy()
        if original_tt_all.empty and before_tt_all.empty and after_tt_all.empty:
            continue

        reference_counts = before_tt_all.groupby("combo").size().sort_values(ascending=False)
        if reference_counts.empty:
            reference_counts = original_tt_all.groupby("combo").size().sort_values(ascending=False)
        if reference_counts.empty:
            reference_counts = after_tt_all.groupby("combo").size().sort_values(ascending=False)
        combo_labels = [label for label in reference_counts.index.tolist() if label and label != "nan"]
        if not combo_labels:
            continue

        original_tt_full = original_tt_all.loc[original_tt_all["combo"].isin(combo_labels)].copy()
        before_tt_full = before_tt_all.loc[before_tt_all["combo"].isin(combo_labels)].copy()
        after_tt_full = after_tt_all.loc[after_tt_all["combo"].isin(combo_labels)].copy()
        if original_tt_full.empty and before_tt_full.empty and after_tt_full.empty:
            continue

        prefilter_removed_tt_full = subtract_task3_plane_combination_payload(
            original_tt_full,
            before_tt_full,
        )
        removed_tt_full = subtract_task3_plane_combination_payload(
            before_tt_full,
            after_tt_full,
        )

        def _sample_scatter_payload(payload: pd.DataFrame) -> pd.DataFrame:
            if len(payload) <= scatter_max_points:
                return payload.copy()
            return payload.iloc[
                rng.choice(len(payload), size=scatter_max_points, replace=False)
            ].copy()

        after_tt = _sample_scatter_payload(after_tt_full)
        prefilter_removed_tt = _sample_scatter_payload(prefilter_removed_tt_full)
        removed_tt = _sample_scatter_payload(removed_tt_full)

        combo_color_map = {label: _task3_population_color(label) for label in combo_labels}
        after_combo_data = {
            label: {
                observable: pd.to_numeric(
                    after_tt_full.loc[after_tt_full["combo"] == label, observable],
                    errors="coerce",
                ).to_numpy(dtype=float)
                for observable in observable_names
            }
            for label in combo_labels
        }
        removed_combo_data = {
            label: {
                observable: pd.to_numeric(
                    removed_tt_full.loc[removed_tt_full["combo"] == label, observable],
                    errors="coerce",
                ).to_numpy(dtype=float)
                for observable in observable_names
            }
            for label in combo_labels
        }
        after_scatter_combo_data = {
            label: {
                observable: pd.to_numeric(
                    after_tt.loc[after_tt["combo"] == label, observable],
                    errors="coerce",
                ).to_numpy(dtype=float)
                for observable in observable_names
            }
            for label in combo_labels
        }
        removed_scatter_combo_data = {
            label: {
                observable: pd.to_numeric(
                    removed_tt.loc[removed_tt["combo"] == label, observable],
                    errors="coerce",
                ).to_numpy(dtype=float)
                for observable in observable_names
            }
            for label in combo_labels
        }

        n_obs = len(observable_names)
        fig, axes = plt.subplots(n_obs, n_obs, figsize=(2.15 * n_obs, 2.15 * n_obs), constrained_layout=True)
        any_panel_data = False

        axis_ranges: dict[str, tuple[float, float]] = {}
        for observable in observable_names:
            before_values = pd.to_numeric(
                original_tt_full.get(observable, pd.Series(dtype=float)),
                errors="coerce",
            ).dropna().to_numpy(dtype=float)
            after_values = pd.to_numeric(
                after_tt_full.get(observable, pd.Series(dtype=float)),
                errors="coerce",
            ).dropna().to_numpy(dtype=float)
            axis_ranges[observable] = _task3_hist_range(
                before_values,
                after_values,
                limits_by_observable.get(observable, (None, None)),
            )

        for row_idx, y_name in enumerate(observable_names):
            for col_idx, x_name in enumerate(observable_names):
                ax = axes[row_idx, col_idx]
                if col_idx > row_idx:
                    ax.set_axis_off()
                    continue

                after_x = pd.to_numeric(after_tt.get(x_name, pd.Series(dtype=float)), errors="coerce").to_numpy(dtype=float)
                after_y = pd.to_numeric(after_tt.get(y_name, pd.Series(dtype=float)), errors="coerce").to_numpy(dtype=float)

                if row_idx == col_idx:
                    original_values = pd.to_numeric(
                        original_tt_full.get(x_name, pd.Series(dtype=float)),
                        errors="coerce",
                    ).dropna().to_numpy(dtype=float)
                    after_values = after_x[np.isfinite(after_x)]
                    prefilter_removed_values = pd.to_numeric(
                        prefilter_removed_tt_full.get(x_name, pd.Series(dtype=float)),
                        errors="coerce",
                    ).dropna().to_numpy(dtype=float)
                    prefilter_removed_values = prefilter_removed_values[np.isfinite(prefilter_removed_values)]
                    if original_values.size == 0 and after_values.size == 0 and prefilter_removed_values.size == 0:
                        ax.set_axis_off()
                        continue
                    any_panel_data = True
                    x_low, x_high = axis_ranges[x_name]
                    bins = np.linspace(x_low, x_high, 60)
                    if prefilter_removed_values.size:
                        ax.hist(
                            prefilter_removed_values,
                            bins=bins,
                            histtype="step",
                            linestyle="--",
                            linewidth=1.0,
                            alpha=0.55,
                            color="lightgrey",
                        )
                    for combo_label in combo_labels:
                        combo_before = removed_combo_data[combo_label][x_name]
                        combo_after = after_combo_data[combo_label][x_name]
                        combo_before = combo_before[np.isfinite(combo_before)]
                        combo_after = combo_after[np.isfinite(combo_after)]
                        if combo_before.size:
                            ax.hist(
                                combo_before,
                                bins=bins,
                                histtype="step",
                                linestyle="--",
                                linewidth=0.95,
                                alpha=0.55,
                                color=combo_color_map[combo_label],
                            )
                        if combo_after.size:
                            ax.hist(
                                combo_after,
                                bins=bins,
                                histtype="step",
                                linestyle="-",
                                linewidth=1.35,
                                alpha=0.95,
                                color=combo_color_map[combo_label],
                            )
                    lower_limit, upper_limit = limits_by_observable.get(x_name, (None, None))
                    if lower_limit is not None:
                        ax.axvline(float(lower_limit), color="lightgrey", linestyle="--", linewidth=1.1)
                    if upper_limit is not None:
                        ax.axvline(float(upper_limit), color="lightgrey", linestyle="--", linewidth=1.1)
                    ax.set_xlim(x_low, x_high)
                    ax.set_yscale("log", nonpositive="clip")
                    ax.set_title(observable_labels[x_name], fontsize=9)
                else:
                    after_mask = np.isfinite(after_x) & np.isfinite(after_y)
                    prefilter_removed_x = pd.to_numeric(
                        prefilter_removed_tt.get(x_name, pd.Series(dtype=float)),
                        errors="coerce",
                    ).to_numpy(dtype=float)
                    prefilter_removed_y = pd.to_numeric(
                        prefilter_removed_tt.get(y_name, pd.Series(dtype=float)),
                        errors="coerce",
                    ).to_numpy(dtype=float)
                    removed_x = pd.to_numeric(
                        removed_tt.get(x_name, pd.Series(dtype=float)),
                        errors="coerce",
                    ).to_numpy(dtype=float)
                    removed_y = pd.to_numeric(
                        removed_tt.get(y_name, pd.Series(dtype=float)),
                        errors="coerce",
                    ).to_numpy(dtype=float)
                    prefilter_removed_mask = np.isfinite(prefilter_removed_x) & np.isfinite(prefilter_removed_y)
                    removed_mask = np.isfinite(removed_x) & np.isfinite(removed_y)
                    if not np.any(prefilter_removed_mask) and not np.any(removed_mask) and not np.any(after_mask):
                        ax.set_axis_off()
                        continue
                    any_panel_data = True
                    if np.any(prefilter_removed_mask):
                        ax.scatter(
                            prefilter_removed_x[prefilter_removed_mask],
                            prefilter_removed_y[prefilter_removed_mask],
                            s=prefilter_scatter_size,
                            alpha=0.08,
                            color="grey",
                            edgecolors="none",
                            rasterized=True,
                        )
                    for combo_label in combo_labels:
                        combo_after_x = after_scatter_combo_data[combo_label][x_name]
                        combo_after_y = after_scatter_combo_data[combo_label][y_name]
                        combo_removed_x = removed_scatter_combo_data[combo_label][x_name]
                        combo_removed_y = removed_scatter_combo_data[combo_label][y_name]
                        combo_after_mask = np.isfinite(combo_after_x) & np.isfinite(combo_after_y)
                        combo_removed_mask = np.isfinite(combo_removed_x) & np.isfinite(combo_removed_y)
                        if np.any(combo_after_mask):
                            ax.scatter(
                                combo_after_x[combo_after_mask],
                                combo_after_y[combo_after_mask],
                                s=6,
                                alpha=0.16,
                                color=combo_color_map[combo_label],
                                edgecolors="none",
                                rasterized=True,
                            )
                        if np.any(combo_removed_mask):
                            ax.scatter(
                                combo_removed_x[combo_removed_mask],
                                combo_removed_y[combo_removed_mask],
                                s=removed_scatter_marker_size,
                                marker=removed_marker,
                                alpha=removed_marker_alpha,
                                linewidths=1.0,
                                color=combo_color_map[combo_label],
                                rasterized=True,
                            )
                    x_low, x_high = axis_ranges[x_name]
                    y_low, y_high = axis_ranges[y_name]
                    ax.set_xlim(x_low, x_high)
                    ax.set_ylim(y_low, y_high)
                    x_limits = limits_by_observable.get(x_name, (None, None))
                    y_limits = limits_by_observable.get(y_name, (None, None))
                    if x_limits[0] is not None:
                        ax.axvline(float(x_limits[0]), color="lightgrey", linestyle="--", linewidth=0.9)
                    if x_limits[1] is not None:
                        ax.axvline(float(x_limits[1]), color="lightgrey", linestyle="--", linewidth=0.9)
                    if y_limits[0] is not None:
                        ax.axhline(float(y_limits[0]), color="lightgrey", linestyle="--", linewidth=0.9)
                    if y_limits[1] is not None:
                        ax.axhline(float(y_limits[1]), color="lightgrey", linestyle="--", linewidth=0.9)

                if row_idx == n_obs - 1:
                    ax.set_xlabel(observable_labels[x_name], fontsize=8)
                else:
                    ax.set_xticklabels([])
                if col_idx == 0 and row_idx != col_idx:
                    ax.set_ylabel(observable_labels[y_name], fontsize=8)
                elif col_idx != 0:
                    ax.set_yticklabels([])
                if row_idx == col_idx:
                    ax.set_ylabel("Counts", fontsize=8)
                ax.tick_params(labelsize=6)

        if not any_panel_data:
            plt.close(fig)
            continue

        relation_title = relation_label.replace("_", " ").title()
        style_handles = [
            mpl.lines.Line2D([0], [0], color="lightgrey", linestyle="--", linewidth=1.0, label="Removed Before Current Filter"),
            mpl.lines.Line2D([0], [0], color="black", linestyle="--", linewidth=1.0, label="Removed By Current Filter"),
            mpl.lines.Line2D([0], [0], color="black", linestyle="-", linewidth=1.4, label="Retained"),
            mpl.lines.Line2D(
                [0],
                [0],
                color="black",
                marker=removed_marker,
                linestyle="None",
                markersize=6,
                markerfacecolor="none",
                label=f"{relation_title} Filter Rejection",
            ),
        ]
        combo_handles = [
            mpl.lines.Line2D([0], [0], color=combo_color_map[label], linestyle="-", linewidth=1.6, label=label)
            for label in combo_labels
        ]
        fig.legend(
            handles=style_handles + combo_handles,
            loc="upper center",
            bbox_to_anchor=(0.5, 0.995),
            ncol=min(6, max(2, len(combo_handles) + 2)),
            fontsize=6,
            frameon=False,
            handlelength=1.8,
            columnspacing=0.8,
        )

        fig.suptitle(
            f"Task 3 {relation_title} plane-comparison filter by TT {tt_label}\n{basename_no_ext_value}",
            fontsize=11,
            y=0.94,
        )
        if save_plots:
            final_filename = f"{fig_idx_value}_plane_combination_filter_by_tt_{relation_label}_TT_{tt_label}.png"
            fig_idx_value += 1
            save_fig_path = os.path.join(base_dir, final_filename)
            if plot_list is not None:
                plot_list.append(save_fig_path)
            save_plot_figure(save_fig_path, fig=fig, format="png", dpi=150)
        if show_plots:
            plt.show()
        plt.close(fig)

    return fig_idx_value


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


def _zpos_from_conf(row):
    return np.array([row.get(f"P{i}", np.nan) for i in range(1, 5)])


# Legacy metadata key retained for compatibility: it now tracks the unified
# Task 3 plane-combination filter, with same-plane bounds coming from the
# `plane_combination_plane_*` configuration family.
def record_filter6_counts(df: pd.DataFrame, tag: str) -> None:
    for i_plane in range(1, 5):
        columns = {
            "T_sum": f"p{i_plane}_tsum",
            "T_diff": f"p{i_plane}_tdif",
            "Q_sum": f"p{i_plane}_qsum",
            "Q_diff": f"p{i_plane}_qdif",
            "Y": f"p{i_plane}_ypos",
        }
        for label, col in columns.items():
            if col in df:
                count = int((df[col] != 0).sum())
                global_variables[f"P{i_plane}_{label}_nonzero_{tag}"] = count


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
activation_metadata: dict[str, object] = {}
pattern_metadata: dict[str, object] = {}

STATION_CHOICES = ("0", "1", "2", "3", "4")
TASK3_PLOT_STATUSES: tuple[str, ...] = ("none", "debug", "usual", "essential")
TASK3_PLOT_ALIASES: tuple[str, ...] = (
    "acquisition_rate_vs_time_by_task_tt_with_histograms",
    "incoming_parquet_main_columns_debug",
    "active_strip_patterns_overview",
    "multi_strip_pair_diagnostics",
    "tdiff_pattern_spatial_scatter",
    "tdiff_pattern_charge_scatter",
    "tdiff_pattern_charge_scan_scatter",
    "tdiff_pattern_histograms",
    "tdiff_pattern_charge_slice_fits",
    "tdiff_pattern_sigma_vs_charge",
    "tdiff_pattern_sigma1_charge_surface",
    "tdiff_pattern_sigma2_charge_surface",
    "y_position_by_tt_task2_cal",
    "strip_variable_pairgrid",
    "self_trigger_strip_variable_pairgrid",
    "rpc_variables_hexbin",
    "rpc_variables_hexbin_per_plane_combination",
    "rpc_variables_hexbin_low_charge",
    "filter6_tsum_debug",
    "filter6_tdif_debug",
    "filter6_qsum_debug",
    "filter6_qdif_debug",
    "filter6_y_debug",
    "filtered_rpc_tsum_vs_qsum_scatter",
    "filtered_rpc_tsum_vs_qsum_scatter_per_combination",
    "filtered_rpc_tsum_vs_qsum_hexbin",
    "filtered_rpc_variables_hexbin",
    "prefilter_qsum_nonzero_debug",
    "prefilter_tt_task3_list_debug",
    "tt_task3_list_qsum_pairgrid",
    "all_events_charge_threshold_population",
    "source_tt_task3_list_charge_threshold_population",
    "tt_task3_list_transition_matrices",
    "tt_task3_list_retention_curves",
    "tt_task3_list_minimum_charge_distributions",
    "tt_task3_list_empirical_efficiency_vs_threshold",
    "full_topology_threshold_retention",
    "full_topology_exact_retention",
    "full_topology_class_fraction",
    "tsum_coincidence_window_histograms",
    "tsum_coincidence_window_vs_threshold",
    "plane_charge_fraction_vs_total_charge_threshold_scan",
    "charge_asymmetry_vs_threshold",
    "interplane_timing_correlation",
    "multiplicity_charge_landscape",
    "streamer_charge_histograms",
    "streamer_prevalence_by_plane",
    "streamer_multiplicity",
    "streamer_contagion_matrix",
    "streamer_contagion_matrix_strip",
    "streamer_efficiency_comparison",
    "fourplane_weakest_charge",
    "fourplane_weakest_plane_identity",
    "efficiency_anatomy_by_charge_band",
    "streamer_contagion_strip_by_tt",
    "signal_contagion_strip_by_tt",
    "streamer_to_signal_contagion_strip_by_tt",
    "streamer_to_highcharge_contagion_strip_by_tt",
    "strip_activation_matrix_before_after",
    "plane_combination_filter_by_tt",
    "charge_by_strip_multiplicity_adj",
    "charge_by_strip_multiplicity_dis",
    "tot_charge_calibration_order_comparison",
    "tot_charge_calibration_order_scatter",
)

TT_COUNT_VALUES: tuple[int, ...] = (
    0, 1, 2, 3, 4, 12, 13, 14, 23, 24, 34, 123, 124, 134, 234, 1234
)
TT_COLOR_LABELS: tuple[str, ...] = tuple(str(tt_value) for tt_value in TT_COUNT_VALUES)
_task3_tt_palette = sns.color_palette("tab10", n_colors=10)
TT_COLOR_MAP: dict[str, tuple[float, float, float, float]] = {}
_task3_multi_idx = 0
for tt_label in TT_COLOR_LABELS:
    if len(tt_label) == 1:
        TT_COLOR_MAP[tt_label] = (0.60, 0.60, 0.60, 1.0)
    else:
        rgb = _task3_tt_palette[_task3_multi_idx % len(_task3_tt_palette)]
        TT_COLOR_MAP[tt_label] = (float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0)
        _task3_multi_idx += 1
TT_COLOR_DEFAULT = (0.45, 0.45, 0.45, 1.0)

CLI_PARSER = build_step1_cli_parser("Run Stage 1 STEP_1 TASK_3 (CAL->LIST).", STATION_CHOICES)
CLI_ARGS = CLI_PARSER.parse_args()
validate_step1_input_file_args(CLI_PARSER, CLI_ARGS)

VERBOSE = bool(os.environ.get("DATAFLOW_VERBOSE")) or CLI_ARGS.verbose
print = build_step1_filtered_print(
    verbose=VERBOSE,
    debug_mode_getter=lambda: bool(globals().get("debug_mode", False)),
    raw_print=builtins.print,
)
FILTER_METRICS_LOGGING_ENABLED = step1_logging_enabled("filter_metrics")[0]
task3_plot_status_by_alias: dict[str, str] = {}
plot_mode = "none"
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
    include_filter_parameter_config=True,
    log_fn=print,
)
config_root = task_config_bundle["config_root"]
config_file_path = task_config_bundle["config_file_path"]
parameter_config_file_path = task_config_bundle["parameter_config_file_path"]
plot_parameter_config_file_path = task_config_bundle["plot_parameter_config_file_path"]
filter_parameter_config_file_path = task_config_bundle["filter_parameter_config_file_path"]
plot_catalog_file_path = task_config_bundle["plot_catalog_file_path"]
fallback_parameter_config_file_path = task_config_bundle["fallback_parameter_config_file_path"]
config = task_config_bundle["config"]
task3_plot_status_by_alias = load_task3_plot_catalog(plot_catalog_file_path)
debug_mode = False
home_path = str(resolve_home_path_from_config(config))

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
    filter_parameter_config_file_path=filter_parameter_config_file_path,
    log_fn=print,
)
config["_plot_station_id"] = station
config["_plot_task_number"] = task_number
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
        Path(user_file_path).name.replace("calibrated_", "").replace(".parquet", "")
    )
else:
    early_status_filename_base = f"__task{task_number}_startup_station_{station}__"
status_filename_base = early_status_filename_base
status_execution_date = initialize_status_row(
    early_status_csv_path,
    filename_base=status_filename_base,
    completion_fraction=0.0,
)
home_path = str(resolve_home_path_from_config(config))
REFERENCE_TABLES_DIR = get_repo_root() / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS" / "SUPPORT" / "CONFIG_FILES" / "METADATA_REPRISE" / "REFERENCE_TABLES"
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

not_use_q_semisum = False

stratos_save = config["stratos_save"]
fast_mode = False
debug_mode = False
last_file_test = config["last_file_test"]
keep_all_columns_output = _coerce_config_bool(
    config.get("keep_all_columns_output", False),
    default=False,
)

# Accessing all the variables from the configuration
(
    plot_mode,
    create_plots,
    create_essential_plots,
    save_plots,
    create_pdf,
    show_plots,
    create_debug_plots,
) = resolve_task3_plot_options(config)
limit_number = config.get("limit_number", None)
limit = limit_number is not None

# Charge calibration to fC

# Charge front-back

# Slewing correction

# Time filtering

# Time calibration

# Y position

# RPC variables
y_new_method = config["y_new_method"]
weighted_by_charge_for_plane_tsum_and_tdif = _coerce_config_bool(
    config.get("weighted_by_charge_for_plane_tsum_and_tdif", False),
    default=False,
)
streamer_high_charge_factor = float(config.get("streamer_high_charge_factor", 0.2))
streamer_charge_sum_threshold = _task3_optional_float(
    config.get("streamer_charge_sum_threshold", None)
)

# Alternative

# TimTrack

# Validation

complete_reanalysis = config["complete_reanalysis"]

limit_number = config.get("limit_number", None)
limit = limit_number is not None

# Pre-cal Front & Back
T_side_left_pre_cal_debug = config.get("T_side_left_pre_cal_debug", -500)
T_side_right_pre_cal_debug = config.get("T_side_right_pre_cal_debug", 500)

T_side_left_pre_cal_default = config.get("T_side_left_pre_cal_default", -200)
T_side_right_pre_cal_default = config.get("T_side_right_pre_cal_default", -100)

T_side_left_pre_cal_ST = config.get("T_side_left_pre_cal_ST", -200)
T_side_right_pre_cal_ST = config.get("T_side_right_pre_cal_ST", -50)

# Pre-cal Sum & Diff

# Post-calibration

# Once calculated the RPC variables. Legacy per-plane keys remain as optional
# compatibility aliases so old configs still load, but Task 3 can now run with
# only the plane_combination_* thresholds present.
T_sum_RPC_left = _task3_config_float(
    config,
    "T_sum_RPC_left",
    "plane_combination_plane_t_sum_sum_left",
    "plane_combination_same_plane_t_sum_sum_left",
    "plane_combination_self_t_sum_sum_left",
    default=-25.0,
)
T_sum_RPC_right = _task3_config_float(
    config,
    "T_sum_RPC_right",
    "plane_combination_plane_t_sum_sum_right",
    "plane_combination_same_plane_t_sum_sum_right",
    "plane_combination_self_t_sum_sum_right",
    default=25.0,
)
T_dif_RPC_abs = abs(
    _task3_config_float(
        config,
        "T_dif_RPC_abs",
        "T_dif_RPC_right",
        "plane_combination_plane_t_dif_sum_threshold",
        "plane_combination_same_plane_t_dif_sum_threshold",
        "plane_combination_self_t_dif_sum_threshold",
        default=0.8,
    )
)
T_dif_RPC_right = T_dif_RPC_abs
T_dif_RPC_left = -T_dif_RPC_abs
Q_RPC_left = _task3_config_float(
    config,
    "Q_RPC_left",
    "plane_combination_plane_q_sum_sum_left",
    "plane_combination_same_plane_q_sum_sum_left",
    "plane_combination_self_q_sum_sum_left",
    default=0.0,
)
Q_RPC_right = _task3_config_float(
    config,
    "Q_RPC_right",
    "plane_combination_plane_q_sum_sum_right",
    "plane_combination_same_plane_q_sum_sum_right",
    "plane_combination_self_q_sum_sum_right",
    default=800.0,
)
Q_dif_RPC_abs = abs(
    _task3_config_float(
        config,
        "Q_dif_RPC_abs",
        "Q_dif_RPC_right",
        "plane_combination_plane_q_dif_sum_threshold",
        "plane_combination_same_plane_q_dif_sum_threshold",
        "plane_combination_self_q_dif_sum_threshold",
        default=4.0,
    )
)
Q_dif_RPC_right = Q_dif_RPC_abs
Q_dif_RPC_left = -Q_dif_RPC_abs
Y_RPC_abs = abs(
    _task3_config_float(
        config,
        "Y_RPC_abs",
        "Y_RPC_right",
        "plane_combination_plane_y_sum_right",
        "plane_combination_same_plane_y_sum_right",
        "plane_combination_self_y_sum_right",
        default=200.0,
    )
)
Y_RPC_right = Y_RPC_abs
Y_RPC_left = -Y_RPC_abs
plane_combination_plane_q_sum_sum_left = float(
    config.get(
        "plane_combination_plane_q_sum_sum_left",
        Q_RPC_left,
    )
)
plane_combination_plane_q_sum_sum_right = float(
    config.get(
        "plane_combination_plane_q_sum_sum_right",
        Q_RPC_right,
    )
)
plane_combination_plane_q_dif_sum_threshold = abs(
    float(
        config.get(
            "plane_combination_plane_q_dif_sum_threshold",
            Q_dif_RPC_abs,
        )
    )
)
plane_combination_plane_t_sum_sum_left = float(
    config.get(
        "plane_combination_plane_t_sum_sum_left",
        T_sum_RPC_left,
    )
)
plane_combination_plane_t_sum_sum_right = float(
    config.get(
        "plane_combination_plane_t_sum_sum_right",
        T_sum_RPC_right,
    )
)
plane_combination_plane_t_dif_sum_threshold = abs(
    float(
        config.get(
            "plane_combination_plane_t_dif_sum_threshold",
            T_dif_RPC_abs,
        )
    )
)
plane_combination_plane_y_sum_left = float(
    config.get(
        "plane_combination_plane_y_sum_left",
        Y_RPC_left,
    )
)
plane_combination_plane_y_sum_right = float(
    config.get(
        "plane_combination_plane_y_sum_right",
        Y_RPC_right,
    )
)
plane_combination_detector_q_sum_sum_left = float(
    config.get(
        "plane_combination_detector_q_sum_sum_left",
        Q_RPC_left,
    )
)
plane_combination_detector_q_sum_sum_right = float(
    config.get(
        "plane_combination_detector_q_sum_sum_right",
        Q_RPC_right,
    )
)
plane_combination_detector_q_sum_dif_threshold = abs(
    float(
        config.get(
            "plane_combination_detector_q_sum_dif_threshold",
            Q_RPC_right,
        )
    )
)
plane_combination_detector_q_dif_sum_threshold = abs(
    float(
        config.get(
            "plane_combination_detector_q_dif_sum_threshold",
            Q_dif_RPC_abs,
        )
    )
)
plane_combination_detector_q_dif_dif_threshold = abs(
    float(
        config.get(
            "plane_combination_detector_q_dif_dif_threshold",
            Q_dif_RPC_abs,
        )
    )
)
plane_combination_detector_t_sum_sum_left = float(
    config.get(
        "plane_combination_detector_t_sum_sum_left",
        T_sum_RPC_left,
    )
)
plane_combination_detector_t_sum_sum_right = float(
    config.get(
        "plane_combination_detector_t_sum_sum_right",
        T_sum_RPC_right,
    )
)
plane_combination_detector_t_sum_dif_threshold = abs(
    float(
        config.get(
            "plane_combination_detector_t_sum_dif_threshold",
            max(abs(T_sum_RPC_left), abs(T_sum_RPC_right)),
        )
    )
)
plane_combination_detector_t_dif_sum_threshold = abs(
    float(
        config.get(
            "plane_combination_detector_t_dif_sum_threshold",
            T_dif_RPC_abs,
        )
    )
)
plane_combination_detector_t_dif_dif_threshold = abs(
    float(
        config.get(
            "plane_combination_detector_t_dif_dif_threshold",
            T_dif_RPC_abs,
        )
    )
)
plane_combination_detector_y_sum_left = float(
    config.get(
        "plane_combination_detector_y_sum_left",
        Y_RPC_left,
    )
)
plane_combination_detector_y_sum_right = float(
    config.get(
        "plane_combination_detector_y_sum_right",
        Y_RPC_right,
    )
)
plane_combination_detector_y_dif_threshold = abs(
    float(
        config.get(
            "plane_combination_detector_y_dif_threshold",
            Y_RPC_abs,
        )
    )
)
print(
    "Task 3 plane-combination bounds "
    f"(station {station}): same_plane q_sum=[{plane_combination_plane_q_sum_sum_left}, "
    f"{plane_combination_plane_q_sum_sum_right}], "
    f"same_plane t_sum=[{plane_combination_plane_t_sum_sum_left}, {plane_combination_plane_t_sum_sum_right}], "
    f"same_plane y_sum=[{plane_combination_plane_y_sum_left}, {plane_combination_plane_y_sum_right}], "
    f"detector q_sum=[{plane_combination_detector_q_sum_sum_left}, {plane_combination_detector_q_sum_sum_right}], "
    f"detector t_sum=[{plane_combination_detector_t_sum_sum_left}, {plane_combination_detector_t_sum_sum_right}], "
    f"detector y_sum=[{plane_combination_detector_y_sum_left}, {plane_combination_detector_y_sum_right}]"
)

# Alternative fitter filter
det_pos_filter = config.get("det_pos_filter", 800)
det_theta_left_filter = config.get("det_theta_left_filter", 0)
det_theta_right_filter = config.get("det_theta_right_filter", 1.5708)
det_phi_filter_abs = abs(float(config.get("det_phi_filter_abs", 3.141592)))
det_phi_right_filter = det_phi_filter_abs
det_phi_left_filter = -det_phi_filter_abs
det_slowness_filter_left = config.get("det_slowness_filter_left", -0.02)
det_slowness_filter_right = config.get("det_slowness_filter_right", 0.02)

# TimTrack filter

# Fitting comparison

# Calibrations

# Pedestal charge calibration

# Front-back charge

# Variables to modify
beta = config.get("beta", 1)
strip_speed_factor_of_c = config["strip_speed_factor_of_c"]

# X
strip_length = config.get("strip_length", 300)
narrow_strip = config["narrow_strip"]
wide_strip = config["wide_strip"]

# Timtrack parameters
anc_std = config["anc_std"]

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

# Time dif calibration (time_dif_reference)
time_dif_distance = 30
time_dif_reference = np.array([
    [-0.0573, 0.031275, 1.033875, 0.761475],
    [-0.914, -0.873975, -0.19815, 0.452025],
    [0.8769, 1.2008, 1.014, 2.43915],
    [1.508825, 2.086375, 1.6876, 3.023575]
])

# Charge sum pedestal (charge_sum_reference)
charge_sum_distance = 30
charge_sum_reference = np.array([
    [89.4319, 98.19605, 95.99055, 91.83875],
    [96.55775, 94.50385, 94.9254, 91.0775],
    [92.12985, 92.23395, 90.60545, 95.5214],
    [93.75635, 93.57425, 93.07055, 89.27305]
])

# Charge dif calibration (charge_dif_reference)
charge_dif_distance = 30
charge_dif_reference = np.array([
    [4.512, 0.58715, 1.3204, -1.3918],
    [-4.50885, 0.918, -3.39445, -0.12325],
    [-3.8931, -3.28515, 3.27295, 1.0554],
    [-2.29505, 0.012, 2.49045, -2.14565]
])

# Time sum calibration (time_sum_reference)
time_sum_distance = 30
time_sum_reference = np.array([
    [0.0, -0.3886308, -0.53020947, 0.33711737],
    [-0.80494094, -0.68836069, -2.01289387, -1.13481931],
    [-0.23899338, -0.51373738, 0.50845317, 0.11685095],
    [0.33586385, 1.08329847, 0.91410244, 0.58815813]
])



T_F_left_pre_cal = T_side_left_pre_cal_default  #-130
T_F_right_pre_cal = T_side_right_pre_cal_default

T_B_left_pre_cal = T_side_left_pre_cal_default
T_B_right_pre_cal = T_side_right_pre_cal_default

T_F_left_pre_cal_ST = T_side_left_pre_cal_ST  #-115
T_F_right_pre_cal_ST = T_side_right_pre_cal_ST
T_B_left_pre_cal_ST = T_side_left_pre_cal_ST
T_B_right_pre_cal_ST = T_side_right_pre_cal_ST

# Y ---------------------------------------------------------------------------

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

# the analysis mode indicates if it is a regular analysis or a repeated, careful analysis
# 0 -> regular analysis
# 1 -> repeated, careful analysis
global_variables = {}

TT_COUNT_VALUES: tuple[int, ...] = (
    0, 1, 2, 3, 4, 12, 13, 14, 23, 24, 34, 123, 124, 134, 234, 1234
)
TASK3_ACTIVE_STRIP_COLUMNS: tuple[str, ...] = tuple(f"active_strips_P{plane}" for plane in range(1, 5))
TASK3_SELECTED_OFFENDER_CARDINALITY_VALUES: tuple[int, ...] = tuple(range(0, 5))

FILTER_METRIC_NAMES: tuple[str, ...] = (
    "plane_combination_plane_rows_affected_pct",
    "plane_combination_filter_rows_affected_pct",
    "q_sum_all_zero_rows_removed_pct",
    "data_purity_percentage",
    "all_components_zero_rows_removed_pct",
    "tt_task3_list_lt_10_rows_removed_pct",
)
NOISE_CONTROL_RATE_DENOMINATOR_COLUMN = "count_rate_denominator_seconds"
TASK3_NOISE_CONTROL_METRIC_NAMES: tuple[str, ...] = tuple(
    f"plane_combination_filter_rows_with_{selected_count}_selected_offenders_rate_hz"
    for selected_count in TASK3_SELECTED_OFFENDER_CARDINALITY_VALUES
)
TASK3_NOISE_CONTROL_PERCENT_METRIC_NAMES: tuple[str, ...] = tuple(
    f"plane_combination_filter_rows_with_{selected_count}_selected_offenders_pct"
    for selected_count in TASK3_SELECTED_OFFENDER_CARDINALITY_VALUES
)
TASK3_THREE_TO_FOUR_MISSING_TRIGGER_BY_PLANE: dict[int, int] = {
    1: 234,
    2: 134,
    3: 124,
    4: 123,
}
FILTER6_NONZERO_COUNTER_NAMES: tuple[str, ...] = tuple(
    f"P{i_plane}_{label}_nonzero_{tag}"
    for tag in ("before_filter6", "after_filter6")
    for i_plane in range(1, 5)
    for label in ("T_sum", "T_diff", "Q_sum", "Q_diff", "Y")
)
FILTER6_NONZERO_RATE_NAMES: tuple[str, ...] = tuple(
    f"{name}_rate_hz" for name in FILTER6_NONZERO_COUNTER_NAMES
)
FILTER_METADATA_ALLOWED_COLUMNS = {
    "filename_base",
    "execution_timestamp",
    "param_hash",
    *FILTER_METRIC_NAMES,
}
TASK3_DEEP_FILTER_LEGACY_COLUMNS: tuple[str, ...] = (
    "plane_combination_self_rows_affected_pct",
    "plane_combination_same_plane_rows_affected_pct",
)

filter_metrics: dict[str, float] = {}
TASK3_PLANE_LABELS: tuple[str, ...] = tuple(f"P{plane}" for plane in range(1, 5))
TASK3_PLANE_KEYS: tuple[int, ...] = (1, 2, 3, 4)
TASK3_PLANE_COMBINATION_LIMIT_LABELS: dict[str, str] = {
    "q_sum_sum_low": "Q_sum semisum below lower limit",
    "q_sum_sum_high": "Q_sum semisum above upper limit",
    "q_sum_dif_low": "Q_sum semidifference below lower limit",
    "q_sum_dif_high": "Q_sum semidifference above upper limit",
    "q_dif_sum_low": "Q_dif semisum below lower limit",
    "q_dif_sum_high": "Q_dif semisum above upper limit",
    "q_dif_dif_low": "Q_dif semidifference below lower limit",
    "q_dif_dif_high": "Q_dif semidifference above upper limit",
    "t_sum_sum_low": "T_sum semisum below lower limit",
    "t_sum_sum_high": "T_sum semisum above upper limit",
    "t_sum_dif_low": "T_sum semidifference below lower limit",
    "t_sum_dif_high": "T_sum semidifference above upper limit",
    "t_dif_sum_low": "T_dif semisum below lower limit",
    "t_dif_sum_high": "T_dif semisum above upper limit",
    "t_dif_dif_low": "T_dif semidifference below lower limit",
    "t_dif_dif_high": "T_dif semidifference above upper limit",
    "y_sum_low": "Y semisum below lower limit",
    "y_sum_high": "Y semisum above upper limit",
    "y_dif_low": "Y semidifference below lower limit",
    "y_dif_high": "Y semidifference above upper limit",
}
TASK3_PLANE_COMBINATION_LIMIT_KEYS: tuple[str, ...] = tuple(
    TASK3_PLANE_COMBINATION_LIMIT_LABELS
)
TASK3_PLANE_SELF_LIMIT_LABELS: dict[str, str] = {
    "q_sum_sum_low": "Plane Q_sum below lower limit",
    "q_sum_sum_high": "Plane Q_sum above upper limit",
    "q_dif_sum_low": "Plane Q_dif below lower limit",
    "q_dif_sum_high": "Plane Q_dif above upper limit",
    "t_sum_sum_low": "Plane T_sum below lower limit",
    "t_sum_sum_high": "Plane T_sum above upper limit",
    "t_dif_sum_low": "Plane T_dif below lower limit",
    "t_dif_sum_high": "Plane T_dif above upper limit",
    "y_sum_low": "Plane Y below lower limit",
    "y_sum_high": "Plane Y above upper limit",
}
TASK3_PLANE_SELF_LIMIT_KEYS: tuple[str, ...] = tuple(
    TASK3_PLANE_SELF_LIMIT_LABELS
)
TASK3_PLANE_SELF_OBSERVABLE_LIMIT_KEYS: dict[str, tuple[str, str]] = {
    "q_sum_sum": ("q_sum_sum_low", "q_sum_sum_high"),
    "q_dif_sum": ("q_dif_sum_low", "q_dif_sum_high"),
    "t_sum_sum": ("t_sum_sum_low", "t_sum_sum_high"),
    "t_dif_sum": ("t_dif_sum_low", "t_dif_sum_high"),
    "y_sum": ("y_sum_low", "y_sum_high"),
}
_task3_noise_control_efficiency_max_raw = config.get(
    "noise_control_efficiency_max_selected_offenders",
    5,
)
try:
    task3_noise_control_efficiency_max_selected_offenders = int(
        _task3_noise_control_efficiency_max_raw
    )
except (TypeError, ValueError):
    task3_noise_control_efficiency_max_selected_offenders = 5
task3_noise_control_efficiency_max_selected_offenders = max(
    0,
    task3_noise_control_efficiency_max_selected_offenders,
)
task3_noise_control_efficiency_selected_offender_values: tuple[int, ...] = tuple(
    range(task3_noise_control_efficiency_max_selected_offenders + 1)
)
TASK3_PLANE_COMBINATION_OBSERVABLES: tuple[tuple[str, str], ...] = (
    ("q_sum_sum", "Q_sum semisum"),
    ("q_sum_dif", "Q_sum semidifference"),
    ("q_dif_sum", "Q_dif semisum"),
    ("q_dif_dif", "Q_dif semidifference"),
    ("t_sum_sum", "T_sum semisum"),
    ("t_sum_dif", "T_sum semidifference"),
    ("t_dif_sum", "T_dif semisum"),
    ("t_dif_dif", "T_dif semidifference"),
    ("y_sum", "Y semisum"),
    ("y_dif", "Y semidifference"),
)
TASK3_PLANE_COMBINATION_SELF_OBSERVABLES: tuple[tuple[str, str], ...] = (
    ("q_sum_sum", "Q_sum"),
    ("q_dif_sum", "Q_dif"),
    ("t_sum_sum", "T_sum"),
    ("t_dif_sum", "T_dif"),
    ("y_sum", "Y"),
)
reprocessing_parameters = pd.DataFrame()
# -----------------------------------------------------------------------------
# Input selection --------------------------------------------------------------
# -----------------------------------------------------------------------------

repo_root = get_repo_root()
station_directory = str(repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / f"MINGO0{station}")
config_file_directory = str(
    config_root
    / "STAGE_0"
    / "ONLINE_RUN_DICTIONARY"
    / f"STATION_{station}"
)

# Define input file path ------------------------------------------------------------------
input_file_config_path = os.path.join(config_file_directory, f"input_file_mingo0{station}.csv")

if os.path.exists(input_file_config_path):
    print("Searching input configuration file:", input_file_config_path)

    # It is a csv
    input_file = pd.read_csv(input_file_config_path, skiprows=1)

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
    default_z_positions = config.get("default_z_positions", [0, 150, 300, 450])
    if isinstance(default_z_positions, (list, tuple)) and len(default_z_positions) >= 4:
        z_1, z_2, z_3, z_4 = default_z_positions[:4]
    else:
        z_1, z_2, z_3, z_4 = 0, 150, 300, 450

self_trigger = False

print("Creating the necessary directories...")

date_execution = datetime.now().strftime("%y-%m-%d_%H.%M.%S")

# Define base working directory
home_directory = str(repo_root.parent)
station_directory = str(repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / f"MINGO0{station}")
base_directory = str(repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / f"MINGO0{station}" / "STAGE_1" / "EVENT_DATA")
raw_to_list_working_directory = os.path.join(base_directory, f"STEP_1/TASK_{task_number}")

metadata_directory = os.path.join(raw_to_list_working_directory, "METADATA")

if task_number == 1:
    raw_directory = "STAGE_0_TO_1"
    raw_working_directory = os.path.join(station_directory, raw_directory)

else:
    raw_directory = f"STEP_1/TASK_{task_number - 1}/OUTPUT_FILES"
    raw_working_directory = os.path.join(base_directory, raw_directory)

if task_number == 5:
    output_location = os.path.join(
        base_directory,
        "..",
        "..",
        "STAGE_1_PRODUCTS",
        "EVENT_DATA",
        "PARQUET_LAKE",
    )
else:
    output_location = os.path.join(raw_to_list_working_directory, "OUTPUT_FILES")

# Define directory paths relative to base_directory
base_directories = {
    "stratos_list_events_directory": os.path.join(home_directory, "STRATOS_XY_DIRECTORY"),

    "base_plots_directory": os.path.join(raw_to_list_working_directory, "PLOTS"),
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
debug_fig_idx = 1

EXPECTED_INPUT_PREFIX = "calibrated_"
EXPECTED_INPUT_EXTENSION = ".parquet"
csv_path = os.path.join(metadata_directory, f"task_{task_number}_metadata_execution.csv")
csv_path_specific = os.path.join(metadata_directory, f"task_{task_number}_metadata_specific.csv")
csv_path_pattern = os.path.join(metadata_directory, f"task_{task_number}_metadata_pattern.csv")
csv_path_rate_histogram = os.path.join(
    metadata_directory,
    f"task_{task_number}_metadata_rate_histogram.csv",
)
csv_path_activation = os.path.join(
    metadata_directory,
    f"task_{task_number}_metadata_activation.csv",
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
csv_path_noise_control = os.path.join(
    metadata_directory,
    f"task_{task_number}_metadata_noise_control.csv",
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

raw_files = set(_expected_input_files(os.listdir(raw_directory)))
unprocessed_files = set(_expected_input_files(os.listdir(unprocessed_directory)))
processing_files = set(_expected_input_files(os.listdir(processing_directory)))
completed_files = set(_expected_input_files(os.listdir(completed_directory)))

# -----------------------------------------------------------------------------
# Events per second metadata helpers ------------------------------------------
# -----------------------------------------------------------------------------

not_use_q_semisum = False

stratos_save = config["stratos_save"]
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
) = resolve_task3_plot_options(config)
limit_number = config.get("limit_number", None)
limit = limit_number is not None

# Charge calibration to fC

# Charge front-back

# Slewing correction

# Time filtering

# Time calibration

# Y position

# RPC variables
y_new_method = config["y_new_method"]

# Alternative

# TimTrack

# Validation

limit_number = config.get("limit_number", None)
limit = limit_number is not None

# Pre-cal Front & Back
T_side_left_pre_cal_debug = config.get("T_side_left_pre_cal_debug", -500)
T_side_right_pre_cal_debug = config.get("T_side_right_pre_cal_debug", 500)

T_side_left_pre_cal_default = config.get("T_side_left_pre_cal_default", -200)
T_side_right_pre_cal_default = config.get("T_side_right_pre_cal_default", -100)

T_side_left_pre_cal_ST = config.get("T_side_left_pre_cal_ST", -200)
T_side_right_pre_cal_ST = config.get("T_side_right_pre_cal_ST", -50)

# Pre-cal Sum & Diff

# Post-calibration

# Once calculated the RPC variables. Legacy per-plane keys remain as optional
# compatibility aliases so old configs still load, but Task 3 can now run with
# only the plane_combination_* thresholds present.
T_sum_RPC_left = _task3_config_float(
    config,
    "T_sum_RPC_left",
    "plane_combination_plane_t_sum_sum_left",
    "plane_combination_same_plane_t_sum_sum_left",
    "plane_combination_self_t_sum_sum_left",
    default=-25.0,
)
T_sum_RPC_right = _task3_config_float(
    config,
    "T_sum_RPC_right",
    "plane_combination_plane_t_sum_sum_right",
    "plane_combination_same_plane_t_sum_sum_right",
    "plane_combination_self_t_sum_sum_right",
    default=25.0,
)
T_dif_RPC_abs = abs(
    _task3_config_float(
        config,
        "T_dif_RPC_abs",
        "T_dif_RPC_right",
        "plane_combination_plane_t_dif_sum_threshold",
        "plane_combination_same_plane_t_dif_sum_threshold",
        "plane_combination_self_t_dif_sum_threshold",
        default=0.8,
    )
)
T_dif_RPC_right = T_dif_RPC_abs
T_dif_RPC_left = -T_dif_RPC_abs
Q_RPC_left = _task3_config_float(
    config,
    "Q_RPC_left",
    "plane_combination_plane_q_sum_sum_left",
    "plane_combination_same_plane_q_sum_sum_left",
    "plane_combination_self_q_sum_sum_left",
    default=0.0,
)
Q_RPC_right = _task3_config_float(
    config,
    "Q_RPC_right",
    "plane_combination_plane_q_sum_sum_right",
    "plane_combination_same_plane_q_sum_sum_right",
    "plane_combination_self_q_sum_sum_right",
    default=800.0,
)
Q_dif_RPC_abs = abs(
    _task3_config_float(
        config,
        "Q_dif_RPC_abs",
        "Q_dif_RPC_right",
        "plane_combination_plane_q_dif_sum_threshold",
        "plane_combination_same_plane_q_dif_sum_threshold",
        "plane_combination_self_q_dif_sum_threshold",
        default=4.0,
    )
)
Q_dif_RPC_right = Q_dif_RPC_abs
Q_dif_RPC_left = -Q_dif_RPC_abs
Y_RPC_abs = abs(
    _task3_config_float(
        config,
        "Y_RPC_abs",
        "Y_RPC_right",
        "plane_combination_plane_y_sum_right",
        "plane_combination_same_plane_y_sum_right",
        "plane_combination_self_y_sum_right",
        default=200.0,
    )
)
Y_RPC_right = Y_RPC_abs
Y_RPC_left = -Y_RPC_abs

# Alternative fitter filter
det_pos_filter = config.get("det_pos_filter", 800)
det_theta_left_filter = config.get("det_theta_left_filter", 0)
det_theta_right_filter = config.get("det_theta_right_filter", 1.5708)
det_phi_filter_abs = abs(float(config.get("det_phi_filter_abs", 3.141592)))
det_phi_right_filter = det_phi_filter_abs
det_phi_left_filter = -det_phi_filter_abs
det_slowness_filter_left = config.get("det_slowness_filter_left", -0.02)
det_slowness_filter_right = config.get("det_slowness_filter_right", 0.02)

# TimTrack filter

# Fitting comparison

# Calibrations

# Pedestal charge calibration

# Front-back charge

# Variables to modify
beta = config.get("beta", 1)
strip_speed_factor_of_c = config["strip_speed_factor_of_c"]

# X
strip_length = config.get("strip_length", 300)
narrow_strip = config["narrow_strip"]
wide_strip = config["wide_strip"]

# Timtrack parameters
anc_std = config["anc_std"]

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

# Time dif calibration (time_dif_reference)
time_dif_distance = 30
time_dif_reference = np.array([
    [-0.0573, 0.031275, 1.033875, 0.761475],
    [-0.914, -0.873975, -0.19815, 0.452025],
    [0.8769, 1.2008, 1.014, 2.43915],
    [1.508825, 2.086375, 1.6876, 3.023575]
])

# Charge sum pedestal (charge_sum_reference)
charge_sum_distance = 30
charge_sum_reference = np.array([
    [89.4319, 98.19605, 95.99055, 91.83875],
    [96.55775, 94.50385, 94.9254, 91.0775],
    [92.12985, 92.23395, 90.60545, 95.5214],
    [93.75635, 93.57425, 93.07055, 89.27305]
])

# Charge dif calibration (charge_dif_reference)
charge_dif_distance = 30
charge_dif_reference = np.array([
    [4.512, 0.58715, 1.3204, -1.3918],
    [-4.50885, 0.918, -3.39445, -0.12325],
    [-3.8931, -3.28515, 3.27295, 1.0554],
    [-2.29505, 0.012, 2.49045, -2.14565]
])

# Time sum calibration (time_sum_reference)
time_sum_distance = 30
time_sum_reference = np.array([
    [0.0, -0.3886308, -0.53020947, 0.33711737],
    [-0.80494094, -0.68836069, -2.01289387, -1.13481931],
    [-0.23899338, -0.51373738, 0.50845317, 0.11685095],
    [0.33586385, 1.08329847, 0.91410244, 0.58815813]
])



T_F_left_pre_cal = T_side_left_pre_cal_default  #-130
T_F_right_pre_cal = T_side_right_pre_cal_default

T_B_left_pre_cal = T_side_left_pre_cal_default
T_B_right_pre_cal = T_side_right_pre_cal_default

T_F_left_pre_cal_ST = T_side_left_pre_cal_ST  #-115
T_F_right_pre_cal_ST = T_side_right_pre_cal_ST
T_B_left_pre_cal_ST = T_side_left_pre_cal_ST
T_B_right_pre_cal_ST = T_side_right_pre_cal_ST

# Y ---------------------------------------------------------------------------

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

self_trigger = False

not_use_q_semisum = False

stratos_save = config["stratos_save"]
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
) = resolve_task3_plot_options(config)
limit_number = config.get("limit_number", None)
limit = limit_number is not None

# Charge calibration to fC

# Charge front-back

# Slewing correction

# Time filtering

# Time calibration

# Y position

# RPC variables
y_new_method = config["y_new_method"]

# Alternative

# TimTrack

# Validation

limit_number = config.get("limit_number", None)
limit = limit_number is not None

# Pre-cal Front & Back
T_side_left_pre_cal_debug = config.get("T_side_left_pre_cal_debug", -500)
T_side_right_pre_cal_debug = config.get("T_side_right_pre_cal_debug", 500)

T_side_left_pre_cal_default = config.get("T_side_left_pre_cal_default", -200)
T_side_right_pre_cal_default = config.get("T_side_right_pre_cal_default", -100)

T_side_left_pre_cal_ST = config.get("T_side_left_pre_cal_ST", -200)
T_side_right_pre_cal_ST = config.get("T_side_right_pre_cal_ST", -50)

# Pre-cal Sum & Diff

# Post-calibration

# Once calculated the RPC variables. Legacy per-plane keys remain as optional
# compatibility aliases so old configs still load, but Task 3 can now run with
# only the plane_combination_* thresholds present.
T_sum_RPC_left = _task3_config_float(
    config,
    "T_sum_RPC_left",
    "plane_combination_plane_t_sum_sum_left",
    "plane_combination_same_plane_t_sum_sum_left",
    "plane_combination_self_t_sum_sum_left",
    default=-25.0,
)
T_sum_RPC_right = _task3_config_float(
    config,
    "T_sum_RPC_right",
    "plane_combination_plane_t_sum_sum_right",
    "plane_combination_same_plane_t_sum_sum_right",
    "plane_combination_self_t_sum_sum_right",
    default=25.0,
)
T_dif_RPC_abs = abs(
    _task3_config_float(
        config,
        "T_dif_RPC_abs",
        "T_dif_RPC_right",
        "plane_combination_plane_t_dif_sum_threshold",
        "plane_combination_same_plane_t_dif_sum_threshold",
        "plane_combination_self_t_dif_sum_threshold",
        default=0.8,
    )
)
T_dif_RPC_right = T_dif_RPC_abs
T_dif_RPC_left = -T_dif_RPC_abs
Q_RPC_left = _task3_config_float(
    config,
    "Q_RPC_left",
    "plane_combination_plane_q_sum_sum_left",
    "plane_combination_same_plane_q_sum_sum_left",
    "plane_combination_self_q_sum_sum_left",
    default=0.0,
)
Q_RPC_right = _task3_config_float(
    config,
    "Q_RPC_right",
    "plane_combination_plane_q_sum_sum_right",
    "plane_combination_same_plane_q_sum_sum_right",
    "plane_combination_self_q_sum_sum_right",
    default=800.0,
)
Q_dif_RPC_abs = abs(
    _task3_config_float(
        config,
        "Q_dif_RPC_abs",
        "Q_dif_RPC_right",
        "plane_combination_plane_q_dif_sum_threshold",
        "plane_combination_same_plane_q_dif_sum_threshold",
        "plane_combination_self_q_dif_sum_threshold",
        default=4.0,
    )
)
Q_dif_RPC_right = Q_dif_RPC_abs
Q_dif_RPC_left = -Q_dif_RPC_abs
Y_RPC_abs = abs(
    _task3_config_float(
        config,
        "Y_RPC_abs",
        "Y_RPC_right",
        "plane_combination_plane_y_sum_right",
        "plane_combination_same_plane_y_sum_right",
        "plane_combination_self_y_sum_right",
        default=200.0,
    )
)
Y_RPC_right = Y_RPC_abs
Y_RPC_left = -Y_RPC_abs

# Alternative fitter filter
det_pos_filter = config.get("det_pos_filter", 800)
det_theta_left_filter = config.get("det_theta_left_filter", 0)
det_theta_right_filter = config.get("det_theta_right_filter", 1.5708)
det_phi_filter_abs = abs(float(config.get("det_phi_filter_abs", 3.141592)))
det_phi_right_filter = det_phi_filter_abs
det_phi_left_filter = -det_phi_filter_abs
det_slowness_filter_left = config.get("det_slowness_filter_left", -0.02)
det_slowness_filter_right = config.get("det_slowness_filter_right", 0.02)

# TimTrack filter

# Fitting comparison

# Calibrations

# Pedestal charge calibration

# Front-back charge

# Variables to modify
beta = config.get("beta", 1)
strip_speed_factor_of_c = config["strip_speed_factor_of_c"]

# X
strip_length = config.get("strip_length", 300)
narrow_strip = config["narrow_strip"]
wide_strip = config["wide_strip"]

# Timtrack parameters
anc_std = config["anc_std"]

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

charge_per_strip_plot_threshold = config["charge_per_strip_plot_threshold"]
charge_per_plane_plot_threshold = config["charge_per_plane_plot_threshold"]
tt_task3_list_qsum_pair_plot_mode = str(config.get("tt_task3_list_qsum_pair_plot_mode", "hexbin")).strip().lower()
if tt_task3_list_qsum_pair_plot_mode not in {"hexbin", "scatter"}:
    print(
        "Warning: invalid tt_task3_list_qsum_pair_plot_mode="
        f"{tt_task3_list_qsum_pair_plot_mode!r}; using 'hexbin'."
    )
    tt_task3_list_qsum_pair_plot_mode = "hexbin"
_plot_charge_cap_raw = config.get("tt_task3_list_qsum_pair_plot_charge_cap", None)
try:
    if _plot_charge_cap_raw in (None, ""):
        tt_task3_list_qsum_pair_plot_charge_cap = None
    else:
        tt_task3_list_qsum_pair_plot_charge_cap = float(_plot_charge_cap_raw)
except (TypeError, ValueError):
    print(
        "Warning: invalid tt_task3_list_qsum_pair_plot_charge_cap="
        f"{_plot_charge_cap_raw!r}; using automatic range."
    )
    tt_task3_list_qsum_pair_plot_charge_cap = None
if (
    tt_task3_list_qsum_pair_plot_charge_cap is not None
    and (not np.isfinite(tt_task3_list_qsum_pair_plot_charge_cap) or tt_task3_list_qsum_pair_plot_charge_cap <= 0)
):
    print(
        "Warning: non-positive tt_task3_list_qsum_pair_plot_charge_cap="
        f"{tt_task3_list_qsum_pair_plot_charge_cap!r}; using automatic range."
    )
    tt_task3_list_qsum_pair_plot_charge_cap = None

_global_charge_limit_raw = config.get("tt_task3_list_charge_limit", None)
try:
    if _global_charge_limit_raw in (None, ""):
        tt_task3_list_charge_limit = None
    else:
        tt_task3_list_charge_limit = float(_global_charge_limit_raw)
except (TypeError, ValueError):
    print(
        "Warning: invalid tt_task3_list_charge_limit="
        f"{_global_charge_limit_raw!r}; ignoring global charge limit."
    )
    tt_task3_list_charge_limit = None
if tt_task3_list_charge_limit is not None and (
    not np.isfinite(tt_task3_list_charge_limit) or tt_task3_list_charge_limit <= 0
):
    print(
        "Warning: non-positive tt_task3_list_charge_limit="
        f"{tt_task3_list_charge_limit!r}; ignoring global charge limit."
    )
    tt_task3_list_charge_limit = None

_station_charge_limits_raw = config.get("tt_task3_list_charge_limit_by_station", {})
tt_task3_list_charge_limit_station = None
if isinstance(_station_charge_limits_raw, dict):
    station_norm = str(station).strip()
    station_candidates = {
        station_norm.lower(),
        station_norm.zfill(2).lower(),
        f"mingo0{station_norm}".lower(),
        f"mingo{station_norm.zfill(2)}".lower(),
        f"station_{station_norm}".lower(),
        f"station_{station_norm.zfill(2)}".lower(),
    }
    for raw_key, raw_value in _station_charge_limits_raw.items():
        key_norm = str(raw_key).strip().lower()
        if key_norm not in station_candidates:
            continue
        try:
            parsed_limit = float(raw_value)
        except (TypeError, ValueError):
            print(
                "Warning: invalid station charge limit for "
                f"{raw_key!r}: {raw_value!r}; ignoring this entry."
            )
            continue
        if np.isfinite(parsed_limit) and parsed_limit > 0:
            tt_task3_list_charge_limit_station = parsed_limit
            break
        print(
            "Warning: non-positive station charge limit for "
            f"{raw_key!r}: {raw_value!r}; ignoring this entry."
        )
elif _station_charge_limits_raw not in (None, ""):
    print(
        "Warning: tt_task3_list_charge_limit_by_station must be a mapping; "
        f"got {_station_charge_limits_raw!r}."
    )

tt_task3_list_charge_limit_effective = tt_task3_list_charge_limit_station
if tt_task3_list_charge_limit_effective is None:
    tt_task3_list_charge_limit_effective = tt_task3_list_charge_limit

if tt_task3_list_qsum_pair_plot_charge_cap is not None and tt_task3_list_charge_limit_effective is not None:
    tt_task3_list_qsum_pair_plot_charge_cap = min(
        float(tt_task3_list_qsum_pair_plot_charge_cap),
        float(tt_task3_list_charge_limit_effective),
    )
elif tt_task3_list_qsum_pair_plot_charge_cap is None and tt_task3_list_charge_limit_effective is not None:
    tt_task3_list_qsum_pair_plot_charge_cap = float(tt_task3_list_charge_limit_effective)

if tt_task3_list_charge_limit_effective is not None:
    print(
        "Task 3: effective charge limit cap for station "
        f"{station} set to {float(tt_task3_list_charge_limit_effective):g}."
    )

_tt_task3_list_charge_thresholds_raw = config.get("tt_task3_list_charge_thresholds", [0, 5, 10, 20, 50])
if isinstance(_tt_task3_list_charge_thresholds_raw, (int, float, str)):
    _tt_task3_list_charge_thresholds_raw = [_tt_task3_list_charge_thresholds_raw]
tt_task3_list_charge_thresholds: list[float] = []
for raw_threshold in _tt_task3_list_charge_thresholds_raw:
    try:
        threshold_value = float(raw_threshold)
    except (TypeError, ValueError):
        print(f"Warning: invalid tt_task3_list_charge_thresholds entry {raw_threshold!r}; skipping.")
        continue
    if not np.isfinite(threshold_value) or threshold_value < 0:
        print(f"Warning: non-finite or negative tt_task3_list_charge_thresholds entry {raw_threshold!r}; skipping.")
        continue
    if threshold_value not in tt_task3_list_charge_thresholds:
        tt_task3_list_charge_thresholds.append(threshold_value)
if not tt_task3_list_charge_thresholds:
    tt_task3_list_charge_thresholds = [0.0, 5.0, 10.0, 20.0, 50.0]
manual_tt_task3_list_charge_thresholds = list(tt_task3_list_charge_thresholds)
tt_task3_list_charge_threshold_mode = str(config.get("tt_task3_list_charge_threshold_mode", "manual")).strip().lower()
if tt_task3_list_charge_threshold_mode not in {"manual", "auto", "quantile"}:
    print(
        "Warning: invalid tt_task3_list_charge_threshold_mode="
        f"{tt_task3_list_charge_threshold_mode!r}; using 'manual'."
    )
    tt_task3_list_charge_threshold_mode = "manual"

_auto_thr_quantile_raw = config.get("tt_task3_list_charge_threshold_auto_quantile", 95.0)
try:
    tt_task3_list_charge_threshold_auto_quantile = float(_auto_thr_quantile_raw)
except (TypeError, ValueError):
    tt_task3_list_charge_threshold_auto_quantile = 95.0
if not np.isfinite(tt_task3_list_charge_threshold_auto_quantile):
    tt_task3_list_charge_threshold_auto_quantile = 95.0
tt_task3_list_charge_threshold_auto_quantile = float(
    np.clip(tt_task3_list_charge_threshold_auto_quantile, 50.0, 99.999)
)

_auto_thr_steps_raw = config.get("tt_task3_list_charge_threshold_auto_steps", 10)
try:
    tt_task3_list_charge_threshold_auto_steps = int(_auto_thr_steps_raw)
except (TypeError, ValueError):
    tt_task3_list_charge_threshold_auto_steps = 10
tt_task3_list_charge_threshold_auto_steps = max(2, tt_task3_list_charge_threshold_auto_steps)

full_topology_min_baseline_count = int(config.get("full_topology_min_baseline_count", 30))
full_topology_min_baseline_count = max(1, full_topology_min_baseline_count)
full_topology_max_masks = int(config.get("full_topology_max_masks", 6))
full_topology_max_masks = max(1, full_topology_max_masks)
full_topology_max_patterns_per_mask = int(config.get("full_topology_max_patterns_per_mask", 8))
full_topology_max_patterns_per_mask = max(1, full_topology_max_patterns_per_mask)
tsum_window_hist_bins = int(config.get("tsum_window_hist_bins", 60))
tsum_window_hist_bins = max(20, tsum_window_hist_bins)
_tsum_window_percentiles_raw = config.get("tsum_window_percentiles", [50, 68, 90, 95])
if isinstance(_tsum_window_percentiles_raw, (int, float, str)):
    _tsum_window_percentiles_raw = [_tsum_window_percentiles_raw]
tsum_window_percentiles: list[float] = []
for _raw_pct in _tsum_window_percentiles_raw:
    try:
        _pct = float(_raw_pct)
    except (TypeError, ValueError):
        continue
    if 0 < _pct < 100 and _pct not in tsum_window_percentiles:
        tsum_window_percentiles.append(_pct)
if not tsum_window_percentiles:
    tsum_window_percentiles = [50.0, 68.0, 90.0, 95.0]
_tsum_window_reference_raw = config.get("tsum_window_reference_ns", 4.0)
try:
    tsum_window_reference_ns = float(_tsum_window_reference_raw)
except (TypeError, ValueError):
    tsum_window_reference_ns = 4.0
if not np.isfinite(tsum_window_reference_ns) or tsum_window_reference_ns <= 0:
    tsum_window_reference_ns = 4.0
_tsum_window_cut_values_raw = config.get("tsum_window_cut_values_ns", [2.0, 4.0, 6.0, 8.0])
if isinstance(_tsum_window_cut_values_raw, (int, float, str)):
    _tsum_window_cut_values_raw = [_tsum_window_cut_values_raw]
tsum_window_cut_values_ns: list[float] = []
for _raw_cut in _tsum_window_cut_values_raw:
    try:
        _cut = float(_raw_cut)
    except (TypeError, ValueError):
        continue
    if np.isfinite(_cut) and _cut > 0 and _cut not in tsum_window_cut_values_ns:
        tsum_window_cut_values_ns.append(_cut)
if not tsum_window_cut_values_ns:
    tsum_window_cut_values_ns = [2.0, 4.0, 6.0, 8.0]
tsum_window_max_plane_combinations = int(config.get("tsum_window_max_plane_combinations", 8))
tsum_window_max_plane_combinations = max(1, tsum_window_max_plane_combinations)
tsum_window_combo_min_count = int(config.get("tsum_window_combo_min_count", 120))
tsum_window_combo_min_count = max(10, tsum_window_combo_min_count)
plane_charge_fraction_max_panels = int(config.get("plane_charge_fraction_max_panels", 6))
plane_charge_fraction_max_panels = max(1, plane_charge_fraction_max_panels)
plane_charge_fraction_scatter_max_points = int(config.get("plane_charge_fraction_scatter_max_points", 120000))
plane_charge_fraction_scatter_max_points = max(2000, plane_charge_fraction_scatter_max_points)

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

# Time dif calibration (time_dif_reference)
time_dif_distance = 30
time_dif_reference = np.array([
    [-0.0573, 0.031275, 1.033875, 0.761475],
    [-0.914, -0.873975, -0.19815, 0.452025],
    [0.8769, 1.2008, 1.014, 2.43915],
    [1.508825, 2.086375, 1.6876, 3.023575]
])

# Charge sum pedestal (charge_sum_reference)
charge_sum_distance = 30
charge_sum_reference = np.array([
    [89.4319, 98.19605, 95.99055, 91.83875],
    [96.55775, 94.50385, 94.9254, 91.0775],
    [92.12985, 92.23395, 90.60545, 95.5214],
    [93.75635, 93.57425, 93.07055, 89.27305]
])

# Charge dif calibration (charge_dif_reference)
charge_dif_distance = 30
charge_dif_reference = np.array([
    [4.512, 0.58715, 1.3204, -1.3918],
    [-4.50885, 0.918, -3.39445, -0.12325],
    [-3.8931, -3.28515, 3.27295, 1.0554],
    [-2.29505, 0.012, 2.49045, -2.14565]
])

# Time sum calibration (time_sum_reference)
time_sum_distance = 30
time_sum_reference = np.array([
    [0.0, -0.3886308, -0.53020947, 0.33711737],
    [-0.80494094, -0.68836069, -2.01289387, -1.13481931],
    [-0.23899338, -0.51373738, 0.50845317, 0.11685095],
    [0.33586385, 1.08329847, 0.91410244, 0.58815813]
])



T_F_left_pre_cal = T_side_left_pre_cal_default  #-130
T_F_right_pre_cal = T_side_right_pre_cal_default

T_B_left_pre_cal = T_side_left_pre_cal_default
T_B_right_pre_cal = T_side_right_pre_cal_default

T_F_left_pre_cal_ST = T_side_left_pre_cal_ST  #-115
T_F_right_pre_cal_ST = T_side_right_pre_cal_ST
T_B_left_pre_cal_ST = T_side_left_pre_cal_ST
T_B_right_pre_cal_ST = T_side_right_pre_cal_ST

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

_t_sec = time.perf_counter()
print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")
print("----------------- Data reading and preprocessing ---------------------")
print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")

# Get lists of files in the directories
unprocessed_files = _expected_input_files(os.listdir(base_directories["unprocessed_directory"]))
processing_files = _expected_input_files(os.listdir(base_directories["processing_directory"]))
completed_files = _expected_input_files(os.listdir(base_directories["completed_directory"]))
# Create ALL directories if they don't already exist
# Create ALL directories if they don't already exist
for directory in base_directories.values():
    # Skip figure directories at startup; create lazily after selecting a file.
    if directory in (base_directories["base_figure_directory"], base_directories["figure_directory"]):
        continue
    os.makedirs(directory, exist_ok=True)

# status_csv_path = os.path.join(base_directory, "raw_to_list_status.csv")
# status_timestamp = append_status_row(status_csv_path)

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

raw_files = set(_expected_input_files(os.listdir(raw_directory)))
unprocessed_files = set(_expected_input_files(os.listdir(unprocessed_directory)))
processing_files = set(_expected_input_files(os.listdir(processing_directory)))
completed_files = set(_expected_input_files(os.listdir(completed_directory)))

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
                    _exit_without_status_row("Warning: No files to process in COMPLETED after normalization.")
            else:
                _exit_without_status_row(
                    "Warning: No files to process in UNPROCESSED or PROCESSING, and COMPLETED reanalysis is disabled."
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
                    "Warning: No files to process in UNPROCESSED or PROCESSING, and COMPLETED reanalysis is disabled."
                )

        else:
            _exit_without_status_row("Warning: No files to process in UNPROCESSED, PROCESSING, or COMPLETED.")

joined_input_records = [
    {
        "file_name": file_name,
        "processing_file_path": processing_file_path,
        "completed_file_path": completed_file_path if not user_file_selection else "",
        "basename_no_ext": file_name.replace("calibrated_", "").replace(".parquet", ""),
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
                "basename_no_ext": joined_file_name.replace("calibrated_", "").replace(".parquet", ""),
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
# Take basename of IN_PATH without extension and witouth the 'calibrated_' prefix
basename_no_ext = the_filename.replace("calibrated_", "").replace(".parquet", "")

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

simulated_z_positions, simulated_param_hash = resolve_simulated_z_positions(
    basename_no_ext,
    Path(base_directory),
    parquet_path=Path(file_path),
)

is_simulated_file = basename_no_ext.startswith("mi00")
if is_simulated_file:
    if simulated_param_hash:
        print(f"Simulated param_hash resolved: {simulated_param_hash}")
        global_variables["param_hash"] = simulated_param_hash
    else:
        print("Warning: Simulated param_hash missing; default z_positions will be used.")

reprocessing_values: dict[str, object] = {}

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
        param_hash=str(global_variables.get("param_hash", "")),
    )

left_limit_time = pd.to_datetime("1-1-2000", format='%d-%m-%Y')
right_limit_time = pd.to_datetime("1-1-2100", format='%d-%m-%Y')

if limit:
    print(f'Taking the first {limit_number} rows.')

# Read the data file into a DataFrame
KEY = "df"

# Load dataframe(s)
joined_source_file_column = "__task3_joined_source_file__"
joined_source_basename_column = "__task3_joined_source_basename__"
joined_frames: list[pd.DataFrame] = []
for joined_record in joined_input_records:
    joined_path = joined_record["processing_file_path"]
    joined_frame = pd.read_parquet(joined_path, engine="pyarrow")
    joined_frame = joined_frame.rename(columns=lambda col: col.replace("_diff_", "_dif_"))
    joined_frame = canonicalize_step1_columns(joined_frame)
    joined_frame = add_topology_task2_strip(joined_frame)
    if "event_id" not in joined_frame.columns:
        print(
            "Warning: 'event_id' missing in Task 3 input; reconstructing from "
            f"current row order for {joined_record['file_name']}."
        )
        joined_frame.insert(0, "event_id", np.arange(len(joined_frame), dtype=np.int64))
    joined_frame.loc[:, joined_source_file_column] = joined_record["file_name"]
    joined_frame.loc[:, joined_source_basename_column] = joined_record["basename_no_ext"]
    joined_frames.append(joined_frame)
    print(f"Calibrated dataframe reloaded from: {joined_path} rows={len(joined_frame)}")
if not joined_frames:
    sys.exit("No Task 3 input dataframes were loaded.")
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
global_variables["joined_analysis_files_requested"] = int(joined_analysis_files)
global_variables["joined_analysis_files_used"] = int(len(joined_input_records))
global_variables["joined_analysis_time_tolerance_hours"] = float(joined_analysis_time_tolerance_hours)
# Ensure param_hash is persisted for downstream tasks.
if "param_hash" not in working_df.columns:
    working_df["param_hash"] = str(simulated_param_hash) if simulated_param_hash else ""
elif simulated_param_hash:
    _ph_series = working_df["param_hash"]
    _ph_missing = _ph_series.isna()
    try:
        _ph_missing |= _ph_series.astype(str).str.strip().eq("")
    except Exception as exc:
        print(f"Warning: param_hash validation fallback used due to error: {exc}")
    if _ph_missing.any():
        working_df.loc[_ph_missing, "param_hash"] = str(simulated_param_hash)
if not simulated_param_hash and "param_hash" in working_df.columns:
    try:
        _recovered_param_hash_series = working_df["param_hash"].astype(str).str.strip()
        _recovered_param_hash_series = _recovered_param_hash_series[_recovered_param_hash_series.ne("")]
    except Exception as exc:
        print(f"Warning: unable to inspect parquet param_hash column after load: {exc}")
        _recovered_param_hash_series = pd.Series(dtype=str)
    if not _recovered_param_hash_series.empty:
        _recovered_param_hash = _recovered_param_hash_series.iloc[0]
        simulated_z_positions, simulated_param_hash = resolve_simulated_z_positions(
            basename_no_ext,
            Path(base_directory),
            param_hash=_recovered_param_hash,
        )
        if simulated_param_hash:
            global_variables["param_hash"] = simulated_param_hash
            print(f"Recovered simulated param_hash from parquet column: {simulated_param_hash}")
print(f"Cleaned dataframe reloaded from: {file_path}")
print("Columns loaded from parquet:")
for col in working_df.columns:
    print(f" - {col}")

if task3_plot_enabled("incoming_parquet_main_columns_debug"):
    incoming_patterns = [
        re.compile(r"^T\d+_T_(sum|dif)_\d+$"),
        re.compile(r"^Q\d+_Q_(sum|dif)_\d+$"),
        re.compile(r"^T\d+_[FB]_\d+$"),
        re.compile(r"^Q\d+_[FB]_\d+$"),
    ]
    main_cols = [
        col
        for col in working_df.columns
        if any(pattern.match(col) for pattern in incoming_patterns)
    ]
    main_cols.extend([col for col in ("tt_task0_raw", "tt_task1_clean", "tt_task2_cal") if col in working_df.columns])
    seen = set()
    main_cols = [col for col in main_cols if not (col in seen or seen.add(col))]
    if main_cols:
        debug_fig_idx = plot_debug_histograms(
            working_df,
            main_cols,
            thresholds=None,
            title=f"Task 3 incoming parquet: main columns [NON-TUNABLE] (station {station})",
            out_dir=debug_plot_directory,
            fig_idx=debug_fig_idx,
            max_cols_per_fig=20,
        )

tt_task2_cal_columns: dict[int, list[str]] = {}
for plane in range(1, 5):
    tt_task2_cal_columns[plane] = [
        (
            f"p{plane}_s{strip}_qsum_cal"
            if f"p{plane}_s{strip}_qsum_cal" in working_df.columns
            else f"p{plane}_s{strip}_qsum"
        )
        for strip in range(1, 5)
        if f"p{plane}_s{strip}_qsum_cal" in working_df.columns
        or f"p{plane}_s{strip}_qsum" in working_df.columns
    ]

# Keep tt_task2_cal from Task 2 when present; compute only if missing.
if "tt_task2_cal" not in working_df.columns:
    working_df = compute_tt(working_df, "tt_task2_cal", tt_task2_cal_columns)
else:
    working_df.loc[:, "tt_task2_cal"] = (
        pd.to_numeric(working_df["tt_task2_cal"], errors="coerce")
        .fillna(0)
        .astype(int)
    )
original_number_of_events = len(working_df)
print(f"Original number of events in the dataframe: {original_number_of_events}")
if status_execution_date is not None:
    update_status_progress(
        csv_path_status,
        filename_base=status_filename_base,
        execution_date=status_execution_date,
        completion_fraction=0.5,
        param_hash=str(global_variables.get("param_hash", "")),
    )

# --- Continue your calibration or analysis code here ---
# e.g.:
# run_calibration(working_df)

# Note that the middle between start and end time could also be taken. This is for calibration storage.
if "datetime" in working_df.columns:
    datetime_series = pd.to_datetime(working_df["datetime"], errors="coerce").dropna()
else:
    datetime_series = pd.Series(dtype="datetime64[ns]")
if datetime_series.empty:
    print(
        f"Warning: No valid datetime rows found in {file_name}; moving file to ERROR and skipping."
    )
    if not user_file_selection:
        for joined_record in joined_input_records:
            joined_processing_path = joined_record["processing_file_path"]
            error_file_path = os.path.join(base_directories["error_directory"], joined_record["file_name"])
            print(f"Moving file '{joined_record['file_name']}' to ERROR directory: {error_file_path}")
            if os.path.exists(joined_processing_path):
                process_file(joined_processing_path, error_file_path)
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

print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")
print(f"------------- Starting date is {save_filename_suffix} -------------------") # This is longer so it displays nicely
print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")

# Defining the directories that will store the data
save_full_filename = f"full_list_events_{save_filename_suffix}.txt"
save_filename = f"list_events_{save_filename_suffix}.txt"


# -------------------------------------------------------------------------------
# ------------ Input file and data managing to select configuration -------------
# -------------------------------------------------------------------------------

is_simulated_file = basename_no_ext.startswith("mi00")
used_input_file = False
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
        z_source = f"input_file_conf_{selected_conf.get('conf')}"
    else:
        print("Warning: Input configuration file has no valid selectable rows. Using default z_positions.")
        z_positions = np.array([0, 150, 300, 450])  # In mm
        z_source = "default_invalid_input_file"
else:
    print("Error: No input file. Using default z_positions.")
    z_positions = np.array([0, 150, 300, 450])  # In mm
    z_source = "default_no_input_file"
# If any z_positions is NaN or all zeros, find the closest non-zero configuration.
if np.isnan(z_positions).any() or np.all(z_positions == 0):
    if used_input_file:
        print("Warning: Invalid z_positions in selected configuration; searching for closest non-zero configuration.")
        selected_conf = select_closest_valid_z_configuration(
            input_file,
            reference_time=start_time,
        )
        if selected_conf is not None:
            print(f"Selected non-zero configuration: {selected_conf['conf']}")
            z_positions = _zpos_from_conf(selected_conf)
            z_source = f"input_file_nonzero_fallback_conf_{selected_conf.get('conf')}"
        else:
            print("Error: No non-zero z_positions available. Using default z_positions.")
            z_positions = np.array([0, 150, 300, 450])  # In mm
            z_source = "default_no_nonzero_z_available"
    else:
        print("Error: Invalid z_positions without config fallback. Using default z_positions.")
        z_positions = np.array([0, 150, 300, 450])  # In mm
        z_source = "default_invalid_without_input"

# Print the resulting z_positions
z_positions = z_positions - z_positions[0]
print(f"Z positions: {z_positions}")
z_vector_mm = [round(float(value), 3) for value in z_positions.tolist()]
print(
    f"[Z_TRACE] file={basename_no_ext} source={z_source} "
    f"param_hash={simulated_param_hash or 'NA'} z_vector_mm={z_vector_mm}",
    force=True,
)

# Persist plane z-values in the TASK_3 parquet so TASK_4 can reuse them
# without repeating configuration resolution.
for plane_index, z_value in enumerate(z_positions, start=1):
    z_col = f"z_P{plane_index}"
    z_float = float(z_value)
    working_df[z_col] = z_float
    global_variables[z_col] = z_float

_prof["s_data_read_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()
_t_topology_core = _t_sec
print("----------------------------------------------------------------------")
print("---------------- Binary topology of active strips --------------------")
print("----------------------------------------------------------------------")

def _task3_prefer_calibrated_strip_column(column_name: str) -> str:
    cal_column_name = f"{column_name}_cal"
    if cal_column_name in working_df.columns:
        return cal_column_name
    if column_name in working_df.columns:
        print(f"Warning: Task 3 using uncalibrated fallback column {column_name}; {cal_column_name} is missing.")
        return column_name
    return column_name

# Collect new columns in a dict first
active_strip_cols = {}

for plane_id in range(1, 5):
    cols = [_task3_prefer_calibrated_strip_column(f'p{plane_id}_s{i}_qsum') for i in range(1, 5)]
    Q_plane = (
        working_df[cols]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0)
        .to_numpy(dtype=float)
    )  # shape (N, 4)
    active_strips_binary = (Q_plane > 0).astype(int)
    binary_strings = [''.join(map(str, row)) for row in active_strips_binary]
    active_strip_cols[f'active_strips_P{plane_id}'] = binary_strings

# Concatenate all new columns at once (column-wise)
working_df = pd.concat([working_df, pd.DataFrame(active_strip_cols, index=working_df.index)], axis=1)

# Print check
print("Active strips per plane calculated.")
print(working_df[['active_strips_P1', 'active_strips_P2', 'active_strips_P3', 'active_strips_P4']].head())

# Store counts of each active strip pattern (per plane) into metadata
active_patterns = [
    "1000", "0100", "0010", "0001",
    "1100", "0110", "0011", "1010",
    "1001", "0101", "1110", "1011",
    "0111", "1101", "1111",
]
for plane_id in range(1, 5):
    col_name = f"active_strips_P{plane_id}"
    if col_name not in working_df.columns:
        continue
    counts = working_df[col_name].value_counts()
    for pattern in active_patterns:
        global_variables[f"{col_name}_{pattern}_count"] = int(counts.get(pattern, 0))

# ---------------------------------------------------------------------------
# Adj / Dis classification
# A plane pattern is DISPERSED when there is at least one inactive strip (0)
# between two active strips (1), i.e. the active bits are not contiguous.
# Method: strip leading/trailing 0s; if the result still contains a '0', the
# pattern is dispersed.  "0000" and all single-strip patterns are always adj.
# An event is classified "dis" if any plane carries a dispersed pattern;
# otherwise it is "adj".
# ---------------------------------------------------------------------------
_DISPERSED_STRIP_PATTERNS: frozenset[str] = frozenset(
    bits
    for val in range(16)
    for bits in [format(val, "04b")]
    if (
        (fi := bits.find("1")) != -1
        and (li := bits.rfind("1")) > fi
        and "0" in bits[fi : li + 1]
    )
)
# Sanity check (expected: {"0101","1001","1010","1011","1101"})
assert _DISPERSED_STRIP_PATTERNS == {"0101", "1001", "1010", "1011", "1101"}, (
    f"Unexpected dispersed set: {_DISPERSED_STRIP_PATTERNS}"
)

_adj_dis_flags = np.zeros(len(working_df), dtype=bool)  # True = dispersed
for _p in range(1, 5):
    _col = f"active_strips_P{_p}"
    if _col in working_df.columns:
        _adj_dis_flags |= working_df[_col].isin(_DISPERSED_STRIP_PATTERNS).to_numpy()

_adj_dis_label_series = pd.Series(
    np.where(_adj_dis_flags, "dis", "adj"),
    index=working_df.index,
    dtype="object",
)

_adj_dis_counts = _adj_dis_label_series.value_counts()
_n_adj = int(_adj_dis_counts.get("adj", 0))
_n_dis = int(_adj_dis_counts.get("dis", 0))
_n_total_adj_dis = _n_adj + _n_dis
global_variables["adj_count"] = _n_adj
global_variables["dis_count"] = _n_dis
global_variables["dis_fraction"] = round(_n_dis / _n_total_adj_dis, 6) if _n_total_adj_dis > 0 else 0.0
print(f"Task 3 adjacent/dispersed strip summary: adj={_n_adj:,}  dis={_n_dis:,}  dis_fraction={global_variables['dis_fraction']:.4f}")

cal_strip_patterns = build_task3_full_strip_pattern_series(working_df)
store_pattern_rates(pattern_metadata, cal_strip_patterns, "cal_strip_pattern", working_df)
_prof["s_topology_core_s"] = round(time.perf_counter() - _t_topology_core, 2)

if task3_plot_enabled("active_strip_patterns_overview"):

    fig, axes = plt.subplots(nrows=4, ncols=1, figsize=(10, 12), sharex=True, sharey=True)
    colors = ['tab:blue', 'tab:orange', 'tab:green', 'tab:red']
    y_max = 0

    # First pass to determine global y-axis limit
    event_counts_list = []
    for i in [1, 2, 3, 4]:
        counts = working_df[f'active_strips_P{i}'].value_counts()
        counts = counts[counts.index != '0000']
        event_counts_list.append(counts)
        if not counts.empty:
            y_max = max(y_max, counts.max())

    # Get global label order from P1 (or any consistent source)
    label_order = working_df['active_strips_P1'].value_counts().drop('0000', errors='ignore').index.tolist()

    # Second pass to plot
    for i, ax in zip([1, 2, 3, 4], axes):
        event_counts_filt = event_counts_list[i - 1]
        event_counts_filt = event_counts_filt.reindex(label_order, fill_value=0)

        # event_counts_filt.plot(kind='bar', ax=ax, color=colors[i - 1], alpha=0.7)
        event_counts_filt.plot(ax=ax, color=colors[i - 1], alpha=0.7)
        ax.set_title(f'Plane {i}', fontsize=12)
        ax.set_ylabel('Counts')
        ax.set_ylim(0, y_max * 1.05)
        ax.grid(axis='y', linestyle='--', alpha=0.5)
        ax.tick_params(axis='x', labelrotation=45)

    axes[-1].set_xlabel('Active Strip Pattern')
    plt.tight_layout()

    if save_plots:
        final_filename = f'{fig_idx}_filtered_active_strips_all_planes.png'
        fig_idx += 1
        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format='png')

    if show_plots:
        plt.show()
    plt.close()

_prof["s_topology_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()
print("----------------------------------------------------------------------")
print("----------------- Some more tests (multi-strip data) -----------------")
print("----------------------------------------------------------------------")

if task3_plot_enabled("multi_strip_pair_diagnostics"):

    # Build shared auto-limits for Q_diff/Q_sum-like panels across all planes/patterns.
    qsum_normdiff_x_all = []
    qsum_normdiff_y_all = []
    for i_plane in range(1, 5):
        active_col = f'active_strips_P{i_plane}'
        q_sum_cols_for_limits = [f'p{i_plane}_s{j+1}_qsum' for j in range(4)]
        patterns_for_limits = working_df[active_col].unique()
        multi_patterns_for_limits = [
            p for p in patterns_for_limits if p != '0000' and p.count('1') > 1
        ]

        for pattern in multi_patterns_for_limits:
            active_strips = [idx for idx, c in enumerate(pattern) if c == '1']
            if len(active_strips) != 2:
                continue

            mask = working_df[active_col] == pattern
            if mask.sum() == 0:
                continue

            for i_strip, j_strip in combinations(active_strips, 2):
                xi = pd.to_numeric(
                    working_df.loc[mask, q_sum_cols_for_limits[i_strip]],
                    errors='coerce',
                ).to_numpy(dtype=float)
                yi = pd.to_numeric(
                    working_df.loc[mask, q_sum_cols_for_limits[j_strip]],
                    errors='coerce',
                ).to_numpy(dtype=float)

                denom = (xi + yi) / 2.0
                valid = np.isfinite(xi) & np.isfinite(yi) & np.isfinite(denom) & (denom != 0)
                if not np.any(valid):
                    continue

                x_sum = denom[valid]
                y_norm_diff = (xi[valid] - yi[valid]) / (2.0 * x_sum)
                finite = np.isfinite(x_sum) & np.isfinite(y_norm_diff)
                if np.any(finite):
                    qsum_normdiff_x_all.append(x_sum[finite])
                    qsum_normdiff_y_all.append(y_norm_diff[finite])

    qsum_normdiff_shared_limits = None
    if qsum_normdiff_x_all and qsum_normdiff_y_all:
        x_all = np.concatenate(qsum_normdiff_x_all)
        y_all = np.concatenate(qsum_normdiff_y_all)
        x_left, x_right = np.nanpercentile(x_all, [0.5, 99.5])
        y_bottom, y_top = np.nanpercentile(y_all, [0.5, 99.5])

        if not np.isfinite(x_left) or not np.isfinite(x_right) or x_left == x_right:
            x_min = float(np.nanmin(x_all)) if x_all.size else 0.0
            x_max = float(np.nanmax(x_all)) if x_all.size else 1.0
            x_pad = max(1e-6, 0.05 * max(abs(x_min), abs(x_max), 1.0))
            x_left, x_right = x_min - x_pad, x_max + x_pad
        if not np.isfinite(y_bottom) or not np.isfinite(y_top) or y_bottom == y_top:
            y_min = float(np.nanmin(y_all)) if y_all.size else -1.0
            y_max = float(np.nanmax(y_all)) if y_all.size else 1.0
            y_pad = max(1e-6, 0.10 * max(abs(y_min), abs(y_max), 1.0))
            y_bottom, y_top = y_min - y_pad, y_max + y_pad

        qsum_normdiff_shared_limits = (
            float(x_left),
            float(x_right),
            float(y_bottom),
            float(y_top),
        )

    for i_plane in range(1, 5):
        active_col = f'active_strips_P{i_plane}'
        print(f"\n--- Plane {i_plane} ---")

        # Column names
        T_sum_cols = [f'p{i_plane}_s{j+1}_tsum' for j in range(4)]
        T_dif_cols = [f'p{i_plane}_s{j+1}_tdif' for j in range(4)]
        Q_sum_cols = [f'p{i_plane}_s{j+1}_qsum' for j in range(4)]
        Q_dif_cols = [f'p{i_plane}_s{j+1}_qdif' for j in range(4)]

        variable_sets = [
            ('T_sum', T_sum_cols),
            ('T_diff', T_dif_cols),
            ('Q_sum', Q_sum_cols),
            ('Q_dif', Q_dif_cols)
        ]

        patterns = working_df[active_col].unique()
        multi_patterns = [p for p in patterns if p != '0000' and p.count('1') > 1]

        for pattern in multi_patterns:
            active_strips = [i for i, c in enumerate(pattern) if c == '1']
            if len(active_strips) != 2:
                continue

            mask = working_df[active_col] == pattern
            n_events = mask.sum()
            if n_events == 0:
                continue

            print(f"Pattern {pattern} ({n_events} events):")

            for i, j in combinations(active_strips, 2):
                fig, axs = plt.subplots(2, 4, figsize=(20, 10), sharex=False, sharey=False)

                for col_idx, (var_label, cols) in enumerate(variable_sets):
                    xi = working_df.loc[mask, cols[i]].values
                    yi = working_df.loc[mask, cols[j]].values

                    # Row 0: xi vs yi
                    ax = axs[0, col_idx]
                    plot_label = var_label

                    if var_label == "T_sum":
                        lim_left = -125 # -125
                        lim_right = -100 # -100
                    elif var_label == "T_diff":
                        lim_left = -1
                        lim_right = 1

                        error = np.std(yi - xi)
                        plot_label += f', {error:.2f} ns'

                    elif var_label == "Q_sum":
                        lim_left = 0
                        lim_right = 60
                    elif var_label == "Q_dif":
                        lim_left = -1
                        lim_right = 1
                    else:
                        print(f"Unknown variable label: {var_label}")
                        continue

                    ax.scatter(xi, yi, alpha=0.5, s=10, label = plot_label)

                    ax.set_xlim(lim_left, lim_right)
                    ax.set_ylim(lim_left, lim_right)
                    ax.plot([lim_left, lim_right], [lim_left, lim_right], 'k--', lw=1, label='y = x')
                    ax.set_xlabel(f'{var_label} Strip {i+1}')
                    ax.set_ylabel(f'{var_label} Strip {j+1}')
                    ax.set_title(f'{var_label}: Strip {i+1} vs {j+1}')
                    ax.set_aspect('equal', adjustable='box')
                    ax.grid(True)
                    ax.legend()

                    # Row 1: (xi + yi) vs (xi - yi) / (xi + yi)
                    ax = axs[1, col_idx]
                    denom = ( xi + yi ) / 2
                    valid = denom != 0
                    x_sum = denom[valid]
                    y_norm_diff = (xi[valid] - yi[valid]) / x_sum / 2
                    if x_sum.size == 0:
                        continue

                    ax.scatter(x_sum, y_norm_diff, alpha=0.5, s=10)
                    if var_label == "Q_sum" and qsum_normdiff_shared_limits is not None:
                        x_left, x_right, y_bottom, y_top = qsum_normdiff_shared_limits
                        ax.set_xlim(x_left, x_right)
                        ax.set_ylim(y_bottom, y_top)
                    else:
                        ax.set_xlim(lim_left, lim_right)
                        ax.set_ylim(-1, 1)
                    ax.set_xlabel(f'{var_label}$_i$ + {var_label}$_j$ / 2')
                    ax.set_ylabel(f'({var_label}$_i$ - {var_label}$_j$) / ( 2 * sum )')
                    ax.set_title(f'{var_label}: Sum vs Norm. Diff')
                    ax.grid(True)

                fig.suptitle(f'Plane {i_plane}, Pattern {pattern}, Strips {i+1} & {j+1}', fontsize=16)
                fig.tight_layout(rect=[0, 0.03, 1, 0.95])

                if save_plots:
                    name_of_file = f'rpc_variables_2row_P{i_plane}_{pattern}_s{i+1}s{j+1}.png'
                    final_filename = f'{fig_idx}_{name_of_file}'
                    fig_idx += 1
                    save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
                    plot_list.append(save_fig_path)
                    save_plot_figure(save_fig_path, format='png')
                if show_plots:
                    plt.show()
                plt.close()

if task3_plot_enabled("tdiff_pattern_spatial_scatter"):

    patterns_of_interest = ['1100', '0110', '0011', '1001', '1010', '0101']
    fig, axs = plt.subplots(4, len(patterns_of_interest), figsize=(18, 12), sharex=True, sharey=False)

    for i_plane in range(1, 5):
        active_col = f'active_strips_P{i_plane}'
        T_dif_cols = [f'p{i_plane}_s{j+1}_tdif' for j in range(4)]

        for j_pattern, pattern in enumerate(patterns_of_interest):
            ax = axs[i_plane - 1, j_pattern]

            active_strips = [i for i, c in enumerate(pattern) if c == '1']
            if len(active_strips) != 2:
                ax.set_visible(False)
                continue

            i, j = active_strips
            mask = working_df[active_col] == pattern
            if mask.sum() == 0:
                ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes)
                continue

            xi = working_df.loc[mask, T_dif_cols[i]].values
            yi = working_df.loc[mask, T_dif_cols[j]].values
            diff = ( yi - xi ) * tdiff_to_x
            semi_suma = ( yi + xi ) / 2 * tdiff_to_x

            # ax.hist(diff, bins=40, color='blue', alpha=0.7)
            ax.scatter(semi_suma, diff, color='blue', alpha=0.6, s = 1)
            # ax.axvline(0, color='black', linestyle='--', linewidth=1)
            ax.set_xlim(-150, 150)
            ax.set_ylim(-2 * tdiff_to_x, 2 * tdiff_to_x)
            ax.set_title(f'Plane {i_plane}, Pattern {pattern}')
            ax.set_xlabel(f'X mean along the strip (mm)')
            ax.set_ylabel(f'X difference (mm)')
            ax.grid(True)

    fig.suptitle("Histograms of T_diff Differences for Different Patterns", fontsize=16)
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])
    if save_plots:
        name_of_file = 'tdiff_differences_hist_4x3.png'
        final_filename = f'{fig_idx}_{name_of_file}'
        fig_idx += 1
        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format='png')
    if show_plots:
        plt.show()
    plt.close()

if task3_plot_enabled("tdiff_pattern_charge_scatter"):

    patterns_of_interest = ['1100', '0110', '0011', '1001', '1010', '0101']
    fig, axs = plt.subplots(4, len(patterns_of_interest), figsize=(18, 12), sharex=True, sharey=False)

    for i_plane in range(1, 5):
        active_col = f'active_strips_P{i_plane}'
        T_dif_cols = [f'p{i_plane}_s{j+1}_tdif' for j in range(4)]
        Q_sum_cols = [f'p{i_plane}_s{j+1}_qsum' for j in range(4)]

        for j_pattern, pattern in enumerate(patterns_of_interest):
            ax = axs[i_plane - 1, j_pattern]

            active_strips = [i for i, c in enumerate(pattern) if c == '1']
            if len(active_strips) != 2:
                ax.set_visible(False)
                continue

            i, j = active_strips
            mask = working_df[active_col] == pattern
            if mask.sum() == 0:
                ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes)
                continue

            xi = working_df.loc[mask, T_dif_cols[i]].values
            yi = working_df.loc[mask, T_dif_cols[j]].values
            diff = ( yi - xi ) * tdiff_to_x
            semi_suma = ( yi + xi ) / 2 * tdiff_to_x
            qi = working_df.loc[mask, Q_sum_cols[i]].values
            qj = working_df.loc[mask, Q_sum_cols[j]].values
            q_semisum = ( qi + qj ) / 2
            q_semidiff = ( qi - qj ) / 2 / q_semisum

            # ax.hist(diff, bins=40, color='blue', alpha=0.7)
            ax.scatter(q_semisum, diff, color='blue', alpha=0.6, s = 1)
            # ax.axvline(0, color='black', linestyle='--', linewidth=1)
            ax.set_xlim(0, 50)
            ax.set_ylim(-2 * tdiff_to_x, 2 * tdiff_to_x)
            ax.set_title(f'Plane {i_plane}, Pattern {pattern}')
            ax.set_xlabel(f'Q mean (ns)')
            ax.set_ylabel(f'X difference (mm)')
            ax.grid(True)

    fig.suptitle("Histograms of T_diff Differences for Different Patterns", fontsize=16)
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])
    if save_plots:
        name_of_file = 'tdiff_differences_vs_q_sum_4x3.png'
        final_filename = f'{fig_idx}_{name_of_file}'
        fig_idx += 1
        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format='png')
    if show_plots:
        plt.show()
    plt.close()

if task3_plot_enabled("tdiff_pattern_charge_scan_scatter"):

    for charge_limit in np.linspace(5, 15, 3):

        patterns_of_interest = ['1100', '0110', '0011', '1001', '1010', '0101']
        fig, axs = plt.subplots(4, len(patterns_of_interest), figsize=(18, 12), sharex=True, sharey=False)

        for i_plane in range(1, 5):
            active_col = f'active_strips_P{i_plane}'
            T_dif_cols = [f'p{i_plane}_s{j+1}_tdif' for j in range(4)]
            Q_sum_cols = [f'p{i_plane}_s{j+1}_qsum' for j in range(4)]

            for j_pattern, pattern in enumerate(patterns_of_interest):
                ax = axs[i_plane - 1, j_pattern]

                active_strips = [i for i, c in enumerate(pattern) if c == '1']
                if len(active_strips) != 2:
                    ax.set_visible(False)
                    continue

                i, j = active_strips
                mask = working_df[active_col] == pattern
                if mask.sum() == 0:
                    ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes)
                    continue

                xi = working_df.loc[mask, T_dif_cols[i]].values
                yi = working_df.loc[mask, T_dif_cols[j]].values
                diff = ( yi - xi ) * tdiff_to_x
                semi_suma = ( yi + xi ) / 2 * tdiff_to_x

                qi = working_df.loc[mask, Q_sum_cols[i]].values
                qj = working_df.loc[mask, Q_sum_cols[j]].values
                charge_condition = (qi > charge_limit) & (qj > charge_limit)

                diff = diff[charge_condition]
                semi_suma = semi_suma[charge_condition]

                # ax.hist(diff, bins=40, color='blue', alpha=0.7)
                ax.scatter(semi_suma, diff, color='blue', alpha=0.6, s = 1)
                # ax.axvline(0, color='black', linestyle='--', linewidth=1)
                ax.set_xlim(-150, 150)
                ax.set_ylim(-2 * tdiff_to_x, 2 * tdiff_to_x)
                ax.set_title(f'Plane {i_plane}, Pattern {pattern}, Charge > {charge_limit} ns')
                ax.set_xlabel(f'X mean along the strip (mm)')
                ax.set_ylabel(f'X difference (mm)')
                ax.grid(True)

        fig.suptitle("Histograms of T_diff Differences for Different Patterns", fontsize=16)
        fig.tight_layout(rect=[0, 0.03, 1, 0.95])
        if save_plots:
            name_of_file = f'tdiff_differences_hist_4x3_charge_{charge_limit}.png'
            final_filename = f'{fig_idx}_{name_of_file}'
            fig_idx += 1
            save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
            plot_list.append(save_fig_path)
            save_plot_figure(save_fig_path, format='png')
        if show_plots:
            plt.show()
        plt.close()

if task3_plot_enabled("tdiff_pattern_histograms"):

    patterns_of_interest = ['1100', '0110', '0011', '1001', '1010', '0101']
    fig, axs = plt.subplots(4, len(patterns_of_interest), figsize=(18, 12), sharex=True, sharey=False)

    for i_plane in range(1, 5):
        active_col = f'active_strips_P{i_plane}'
        T_dif_cols = [f'p{i_plane}_s{j+1}_tdif' for j in range(4)]

        for j_pattern, pattern in enumerate(patterns_of_interest):
            ax = axs[i_plane - 1, j_pattern]

            active_strips = [i for i, c in enumerate(pattern) if c == '1']
            if len(active_strips) != 2:
                ax.set_visible(False)
                continue

            i, j = active_strips
            mask = working_df[active_col] == pattern
            if mask.sum() == 0:
                ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes)
                continue

            xi = working_df.loc[mask, T_dif_cols[i]].values
            yi = working_df.loc[mask, T_dif_cols[j]].values

            cond = (xi != 0) & (yi != 0) & (abs(xi) < 1) & (abs(yi) < 1)
            xi = xi[cond]
            yi = yi[cond]
            diff = ( yi - xi ) * tdiff_to_x

            ax.hist(diff, bins=40, color='blue', alpha=0.6)
            # ax.axvline(0, color='black', linestyle='--', linewidth=1)
            ax.set_xlim(-2 * tdiff_to_x, 2 * tdiff_to_x)
            ax.set_title(f'Plane {i_plane}, Pattern {pattern}')
            ax.set_xlabel(f'X difference (mm)')
            ax.set_ylabel('Counts')
            ax.grid(True)

    fig.suptitle("Histograms of T_diff Differences for Different Patterns", fontsize=16)
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])
    if save_plots:
        name_of_file = 'tdiff_differences_hist_4x3_only_adj.png'
        final_filename = f'{fig_idx}_{name_of_file}'
        fig_idx += 1
        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format='png')
    if show_plots:
        plt.show()
    plt.close()


    patterns_of_interest = ['1100', '0110', '0011']
    fig, axs = plt.subplots(4, len(patterns_of_interest), figsize=(24, 18), sharex=True, sharey=False)

    # Double Gaussian model
    def double_gaussian(x, A1, mu1, sigma1, A2, mu2, sigma2):
        g1 = A1 * np.exp(-0.5 * ((x - mu1) / sigma1)**2)
        g2 = A2 * np.exp(-0.5 * ((x - mu2) / sigma2)**2)
        return g1 + g2

    for i_plane in range(1, 5):
        active_col = f'active_strips_P{i_plane}'
        T_dif_cols = [f'p{i_plane}_s{j+1}_tdif' for j in range(4)]

        for j_pattern, pattern in enumerate(patterns_of_interest):
            ax = axs[i_plane - 1, j_pattern]

            active_strips = [i for i, c in enumerate(pattern) if c == '1']
            if len(active_strips) != 2:
                ax.set_visible(False)
                continue

            i, j = active_strips
            mask = working_df[active_col] == pattern
            if mask.sum() == 0:
                ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes)
                continue

            xi = working_df.loc[mask, T_dif_cols[i]].values
            yi = working_df.loc[mask, T_dif_cols[j]].values

            cond = (xi != 0) & (yi != 0) & (abs(xi) < 1) & (abs(yi) < 1)
            xi = xi[cond]
            yi = yi[cond]
            diff = ( yi - xi ) * tdiff_to_x

            cond_new = abs(diff) < 150
            diff = diff[cond_new]

            adjacent_nbins = 100

            # Histogram
            counts, bin_edges = np.histogram(diff, bins=adjacent_nbins, range=(-150, 150))
            bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])

            # Constraint bounds
            tolerance_in_pct = 100  # percent

            anc_std_in_mm = anc_std * tdiff_to_x

            sigma_small_left = anc_std_in_mm * (1 - tolerance_in_pct/100)
            sigma_small_right = anc_std_in_mm * (1 + tolerance_in_pct/100)

            print(f"Left and right limits in sigma: {sigma_small_left:.3f}, {sigma_small_right:.3f} mm")

            lower_bound = [0,     -100, sigma_small_left,  0,     -100, 0]
            upper_bound = [np.inf, 100, sigma_small_right, np.inf, 100, 1000]

            # Initial guesses
            p0 = [50, 0, anc_std_in_mm, 50, 0, 20]

            # Fit, if not fit, skip
            try:
                popt, _ = curve_fit(double_gaussian, bin_centers, counts, p0=p0, bounds=(lower_bound, upper_bound))
            except RuntimeError:
                print(f"Fit failed for Plane {i_plane}, Pattern {pattern}. Skipping.")
                ax.text(0.5, 0.5, 'Fit failed', ha='center', va='center', transform=ax.transAxes)
                continue

            # Extract fitted components
            A1, mu1, sigma1, A2, mu2, sigma2 = popt
            fit_x = np.linspace(-150, 150, 500)
            g1 = A1 * np.exp(-0.5 * ((fit_x - mu1) / sigma1)**2)
            g2 = A2 * np.exp(-0.5 * ((fit_x - mu2) / sigma2)**2)
            fit_total = g1 + g2

            ax.hist(diff, bins=adjacent_nbins, range=(-150, 150), color='blue', alpha=0.4, label='Data')
            ax.plot(fit_x, g1, '--', label=f'σ={sigma1:.1f}')
            ax.plot(fit_x, g2, '--', label=f'σ={sigma2:.1f}')

            ax.plot(fit_x, fit_total, '-', color='red', label='Total fit')

            ax.set_xlim(-150, 150)
            ax.set_title(f'Plane {i_plane}, Pattern {pattern}')
            ax.set_xlabel(f'X difference (mm)')
            ax.set_ylabel('Counts')
            ax.grid(True)
            ax.legend()

    fig.suptitle("Fit to the Histograms of T_diff Differences for Different Patterns", fontsize=16)
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])
    if save_plots:
        name_of_file = 'tdiff_differences_hist_4x3_fit.png'
        final_filename = f'{fig_idx}_{name_of_file}'
        fig_idx += 1
        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format='png')
    if show_plots:
        plt.show()
    plt.close()

calculate_sigmas_adjacent = False

if calculate_sigmas_adjacent:

    # Sigmas per charge limit storage, Save in each line the charge limit, the pattern and the sigmas for each plane
    sigma_results = {}
    all_results = {}

    charge_limits_to_test = np.linspace(0, 50, 50)
    for charge_limit in charge_limits_to_test:

        patterns_of_interest = ['1100', '0110', '0011']

        # Double Gaussian model
        def double_gaussian(x, A1, mu1, sigma1, A2, mu2, sigma2):
            g1 = A1 * np.exp(-0.5 * ((x - mu1) / sigma1)**2)
            g2 = A2 * np.exp(-0.5 * ((x - mu2) / sigma2)**2)
            return g1 + g2

        for i_plane in range(1, 5):
            active_col = f'active_strips_P{i_plane}'
            T_dif_cols = [f'p{i_plane}_s{j+1}_tdif' for j in range(4)]
            Q_sum_cols = [f'p{i_plane}_s{j+1}_qsum' for j in range(4)]

            for j_pattern, pattern in enumerate(patterns_of_interest):

                active_strips = [i for i, c in enumerate(pattern) if c == '1']

                i, j = active_strips
                mask = working_df[active_col] == pattern

                xi = working_df.loc[mask, T_dif_cols[i]].values
                yi = working_df.loc[mask, T_dif_cols[j]].values
                qi = working_df.loc[mask, Q_sum_cols[i]].values
                qj = working_df.loc[mask, Q_sum_cols[j]].values

                cond = (xi != 0) & (yi != 0) & (abs(xi) < 1) & (abs(yi) < 1)
                xi = xi[cond]
                yi = yi[cond]
                qi = qi[cond]
                qj = qj[cond]
                diff = ( yi - xi ) * tdiff_to_x

                # charge_condition = (qi > charge_limit) & (qj > charge_limit)
                radius = 2
                charge_condition = ( (qi + qj) > charge_limit - radius) & ( (qi + qj) < charge_limit + radius) & (qi > 1) & (qj > 1)
                # charge_condition = ( (qi + qj) > charge_limit)
                diff = diff[charge_condition]

                cond_new = abs(diff) < 150
                diff = diff[cond_new]

                adjacent_nbins = 100

                # Histogram
                counts, bin_edges = np.histogram(diff, bins=adjacent_nbins, range=(-150, 150))
                bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])

                # Constraint bounds
                tolerance_in_pct = 100  # percent

                anc_std_in_mm = anc_std * tdiff_to_x

                sigma_small_left = anc_std_in_mm * (1 - tolerance_in_pct/100)
                sigma_small_right = anc_std_in_mm * (1 + tolerance_in_pct/100)

                # print(f"Left and right limits in sigma_small: {sigma_small_left:.3f}, {sigma_small_right:.3f} mm")

                lower_bound = [0,     -10, sigma_small_left,  0,     -10, 0]
                upper_bound = [np.inf, 10, sigma_small_right, np.inf, 10, 1000]

                # Initial guesses
                p0 = [50, 0, anc_std_in_mm, 50, 0, 20]

                # Fit
                try:
                    popt, _ = curve_fit(double_gaussian, bin_centers, counts, p0=p0, bounds=(lower_bound, upper_bound))
                except RuntimeError:
                    print(f"Fit failed for Plane {i_plane}, Pattern {pattern}, Charge limit {charge_limit:.1f}. Skipping.")
                    continue

                # Extract fitted components
                A1, mu1, sigma1, A2, mu2, sigma2 = popt
                fit_x = np.linspace(-150, 150, 500)
                g1 = A1 * np.exp(-0.5 * ((fit_x - mu1) / sigma1)**2)
                g2 = A2 * np.exp(-0.5 * ((fit_x - mu2) / sigma2)**2)
                fit_total = g1 + g2

                # Store sigma1 result
                sigma_results[(f'Charge_{charge_limit:.1f}', f'Plane_{i_plane}', pattern)] = sigma1, sigma2
                all_results[(f'Charge_{charge_limit:.1f}', f'Plane_{i_plane}', pattern)] = popt


    if task3_plot_enabled("tdiff_pattern_charge_slice_fits"):
        for charge_limit in charge_limits_to_test:

            patterns_of_interest = ['1100', '0110', '0011']
            fig, axs = plt.subplots(4, len(patterns_of_interest), figsize=(24, 18), sharex=True, sharey=True)

            for i_plane in range(1, 5):
                active_col = f'active_strips_P{i_plane}'
                T_dif_cols = [f'p{i_plane}_s{j+1}_tdif' for j in range(4)]
                Q_sum_cols = [f'p{i_plane}_s{j+1}_qsum' for j in range(4)]

                for j_pattern, pattern in enumerate(patterns_of_interest):
                    ax = axs[i_plane - 1, j_pattern]

                    active_strips = [i for i, c in enumerate(pattern) if c == '1']
                    if len(active_strips) != 2:
                        ax.set_visible(False)
                        continue

                    i, j = active_strips
                    mask = working_df[active_col] == pattern
                    if mask.sum() == 0:
                        ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes)
                        continue

                    xi = working_df.loc[mask, T_dif_cols[i]].values
                    yi = working_df.loc[mask, T_dif_cols[j]].values
                    qi = working_df.loc[mask, Q_sum_cols[i]].values
                    qj = working_df.loc[mask, Q_sum_cols[j]].values

                    cond = (xi != 0) & (yi != 0) & (abs(xi) < 1) & (abs(yi) < 1)
                    xi = xi[cond]
                    yi = yi[cond]
                    qi = qi[cond]
                    qj = qj[cond]
                    diff = ( yi - xi ) * tdiff_to_x

                    # charge_condition = (qi > charge_limit) & (qj > charge_limit)
                    radius = 5
                    charge_condition = ( (qi + qj) > charge_limit - radius) & ( (qi + qj) < charge_limit + radius) & (qi > 1) & (qj > 1)
                    # charge_condition = (qi + qj > charge_limit)
                    diff = diff[charge_condition]

                    cond_new = abs(diff) < 150
                    diff = diff[cond_new]

                    adjacent_nbins = 100

                    # Histogram
                    counts, bin_edges = np.histogram(diff, bins=adjacent_nbins, range=(-150, 150))
                    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])

                    # Extract fitted components
                    popt = all_results.get((f'Charge_{charge_limit:.1f}', f'Plane_{i_plane}', pattern), None)

                    if popt is None:
                        print(f"No fit results for Plane {i_plane}, Pattern {pattern}, Charge limit {charge_limit:.1f}. Skipping.")
                        ax.text(0.5, 0.5, 'No fit results', ha='center', va='center', transform=ax.transAxes)
                        continue

                    A1, mu1, sigma1, A2, mu2, sigma2 = popt
                    fit_x = np.linspace(-150, 150, 500)
                    g1 = A1 * np.exp(-0.5 * ((fit_x - mu1) / sigma1)**2)
                    g2 = A2 * np.exp(-0.5 * ((fit_x - mu2) / sigma2)**2)
                    fit_total = g1 + g2

                    ax.hist(diff, bins=adjacent_nbins, range=(-150, 150), color='blue', alpha=0.4, label='Data')
                    ax.plot(fit_x, g1, '--', label=f'σ={sigma1:.1f}')
                    ax.plot(fit_x, g2, '--', label=f'σ={sigma2:.1f}')

                    ax.plot(fit_x, fit_total, '-', color='red', label='Total fit')

                    ax.set_xlim(-150, 150)
                    ax.set_title(f'Plane {i_plane}, Pattern {pattern}')
                    ax.set_xlabel(f'X difference (mm)')
                    ax.set_ylabel('Counts')
                    ax.grid(True)
                    ax.legend()

            fig.suptitle(f"Fit to the Histograms of T_diff Differences for Different Patterns, Charge limit: {charge_limit:.1f}", fontsize=16)
            fig.tight_layout(rect=[0, 0.03, 1, 0.95])
            if save_plots:
                name_of_file = f'tdiff_differences_hist_4x3_fit_{charge_limit:.1f}.png'
                final_filename = f'{fig_idx}_{name_of_file}'
                fig_idx += 1
                save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
                plot_list.append(save_fig_path)
                save_plot_figure(save_fig_path, format='png')
            if show_plots:
                plt.show()
            plt.close()



    if task3_plot_enabled("tdiff_pattern_sigma_vs_charge"):
        # Plot especifically the sigmas vs charge limit for each plane and pattern, one row per plane, one column per pattern
        fig, axs = plt.subplots(4, len(patterns_of_interest), figsize=(18, 24), sharex=True, sharey=True)
        for i_plane in range(1, 5):
            for j_pattern, pattern in enumerate(patterns_of_interest):
                ax = axs[i_plane - 1, j_pattern]

                charge_limits = []
                mu1_values = []
                mu2_values = []
                sigma1_values = []
                sigma2_values = []

                for charge_limit in charge_limits_to_test:
                    key = (f'Charge_{charge_limit:.1f}', f'Plane_{i_plane}', pattern)

                    if key in all_results:
                        A1, mu1, sigma1, A2, mu2, sigma2 = all_results[key]
                        charge_limits.append(charge_limit)
                        mu1_values.append(mu1)
                        sigma1_values.append(sigma1)
                        mu2_values.append(mu2)
                        sigma2_values.append(sigma2)

                ax.plot(charge_limits, mu1_values, marker='o', label='Mu 1')
                ax.fill_between(charge_limits, mu1_values - np.array(sigma1_values), mu1_values + np.array(sigma1_values), alpha=0.2)
                ax.plot(charge_limits, mu2_values, marker='s', label='Mu 2')
                ax.fill_between(charge_limits, mu2_values - np.array(sigma2_values), mu2_values + np.array(sigma2_values), alpha=0.2)

                ax.set_title(f'Plane {i_plane}, Pattern {pattern}')
                ax.set_xlabel('Charge Limit')
                ax.set_ylabel('Sigma (mm)')
                ax.grid(True)
                ax.legend()
        fig.suptitle("Fitted Sigmas vs Charge Limit for Different Patterns", fontsize=16)
        fig.tight_layout(rect=[0, 0.03, 1, 0.95])
        if save_plots:
            name_of_file = f'tdiff_fitted_sigmas_vs_charge_limit.png'
            final_filename = f'{fig_idx}_{name_of_file}'
            fig_idx += 1
            save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
            plot_list.append(save_fig_path)
            save_plot_figure(save_fig_path, format='png')
        if show_plots:
            plt.show()
        plt.close()


    loop_adjacent_strip_fit = False

    if loop_adjacent_strip_fit and task3_any_plot_enabled(
        "tdiff_pattern_sigma1_charge_surface",
        "tdiff_pattern_sigma2_charge_surface",
    ):
        # Sigmas per charge limit storage, Save in each line the charge limit, the pattern and the sigmas for each plane
        all_results_loop = {}

        charge_limits_to_loop = np.linspace(0, 10, 10)
        for charge_limit_1 in charge_limits_to_loop:
            for charge_limit_2 in charge_limits_to_loop:

                patterns_of_interest = ['1100', '0110', '0011']

                # Double Gaussian model
                def double_gaussian(x, A1, mu1, sigma1, A2, mu2, sigma2):
                    g1 = A1 * np.exp(-0.5 * ((x - mu1) / sigma1)**2)
                    g2 = A2 * np.exp(-0.5 * ((x - mu2) / sigma2)**2)
                    return g1 + g2

                for i_plane in range(1, 5):
                    active_col = f'active_strips_P{i_plane}'
                    T_dif_cols = [f'p{i_plane}_s{j+1}_tdif' for j in range(4)]
                    Q_sum_cols = [f'p{i_plane}_s{j+1}_qsum' for j in range(4)]

                    for j_pattern, pattern in enumerate(patterns_of_interest):

                        active_strips = [i for i, c in enumerate(pattern) if c == '1']

                        i, j = active_strips
                        mask = working_df[active_col] == pattern

                        xi = working_df.loc[mask, T_dif_cols[i]].values
                        yi = working_df.loc[mask, T_dif_cols[j]].values
                        qi = working_df.loc[mask, Q_sum_cols[i]].values
                        qj = working_df.loc[mask, Q_sum_cols[j]].values

                        cond = (xi != 0) & (yi != 0) & (abs(xi) < 1) & (abs(yi) < 1)
                        xi = xi[cond]
                        yi = yi[cond]
                        qi = qi[cond]
                        qj = qj[cond]
                        diff = ( yi - xi ) * tdiff_to_x

                        charge_condition = (qi > charge_limit_1) & (qj > charge_limit_2)
                        diff = diff[charge_condition]

                        cond_new = abs(diff) < 150
                        diff = diff[cond_new]

                        adjacent_nbins = 100

                        # Histogram
                        counts, bin_edges = np.histogram(diff, bins=adjacent_nbins, range=(-150, 150))
                        bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])

                        # Constraint bounds
                        tolerance_in_pct = 100  # percent

                        anc_std_in_mm = anc_std * tdiff_to_x

                        sigma_small_left = anc_std_in_mm * (1 - tolerance_in_pct/100)
                        sigma_small_right = anc_std_in_mm * (1 + tolerance_in_pct/100)

                        # print(f"Left and right limits in sigma: {sigma_small_left:.3f}, {sigma_small_right:.3f} mm")

                        lower_bound = [0,     -10, sigma_small_left,  0,     -10, 0]
                        upper_bound = [np.inf, 10, sigma_small_right, np.inf, 10, 1000]

                        # Initial guesses
                        p0 = [50, 0, anc_std_in_mm, 50, 0, 20]

                        # Fit
                        try:
                            popt, _ = curve_fit(double_gaussian, bin_centers, counts, p0=p0, bounds=(lower_bound, upper_bound))
                        except RuntimeError:
                            print(f"Fit failed for Plane {i_plane}, Pattern {pattern}, Charge limits {charge_limit_1:.1f}, {charge_limit_2:.1f}. Skipping.")
                            continue

                        # Extract fitted components
                        A1, mu1, sigma1, A2, mu2, sigma2 = popt
                        fit_x = np.linspace(-150, 150, 500)
                        g1 = A1 * np.exp(-0.5 * ((fit_x - mu1) / sigma1)**2)
                        g2 = A2 * np.exp(-0.5 * ((fit_x - mu2) / sigma2)**2)
                        fit_total = g1 + g2

                        # Store sigma1 result
                        all_results_loop[(f'Charge_1_{charge_limit_1:.1f}', f'Charge_2_{charge_limit_2:.1f}', f'Plane_{i_plane}', pattern)] = popt

        # Plot especifically the sigmas vs charge limit for each plane and pattern, one row per plane, one column per pattern

        if task3_plot_enabled("tdiff_pattern_sigma1_charge_surface"):
            fig, axs = plt.subplots(4, len(patterns_of_interest), figsize=(18, 24), sharex=True, sharey=True)
            for i_plane in range(1, 5):
                for j_pattern, pattern in enumerate(patterns_of_interest):
                    ax = axs[i_plane - 1, j_pattern]

                    charge_limits_1 = []
                    charge_limits_2 = []
                    mu1_values = []
                    mu2_values = []
                    sigma1_values = []
                    sigma2_values = []

                    for charge_limit_1 in charge_limits_to_loop:
                        for charge_limit_2 in charge_limits_to_loop:
                            key = (f'Charge_1_{charge_limit_1:.1f}', f'Charge_2_{charge_limit_2:.1f}', f'Plane_{i_plane}', pattern)

                            if key in all_results_loop:
                                A1, mu1, sigma1, A2, mu2, sigma2 = all_results_loop[key]
                                charge_limits_1.append(charge_limit_1)
                                charge_limits_2.append(charge_limit_2)
                                mu1_values.append(mu1)
                                sigma1_values.append(sigma1)
                                mu2_values.append(mu2)
                                sigma2_values.append(sigma2)

                    print(sigma1_values)

                    charge1_values = charge_limits_1
                    charge2_values = charge_limits_2

                    unique_c1 = np.array(sorted(set(charge1_values)))
                    unique_c2 = np.array(sorted(set(charge2_values)))
                    C1, C2 = np.meshgrid(unique_c1, unique_c2, indexing='xy')

                    sigma1_grid = np.full(C1.shape, np.nan, dtype=float)
                    sigma2_grid = np.full(C2.shape, np.nan, dtype=float)
                    idx_c1 = {c: j for j, c in enumerate(unique_c1)}
                    idx_c2 = {c: i for i, c in enumerate(unique_c2)}

                    for c1, c2, s1, s2 in zip(charge1_values, charge2_values, sigma1_values, sigma2_values):
                        i = idx_c2[c2]
                        j = idx_c1[c1]
                        sigma1_grid[i, j] = s1
                        sigma2_grid[i, j] = s2

                    Z = sigma1_grid
                    if np.all(np.isnan(Z)):
                        ax.set_title(f'Plane {i_plane}, Pattern {pattern}\n(no valid fits)')
                        ax.set_xticks([])
                        ax.set_yticks([])
                        continue

                    cs = ax.contourf(C1, C2, Z, levels=20)
                    fig.colorbar(cs, ax=ax)
                    ax.set_title(f'Plane {i_plane}, Pattern {pattern}')
                    ax.set_xlabel('Charge 1')
                    ax.set_ylabel('Charge 2')
                    ax.grid(True)

            fig.suptitle("Fitted Sigma 1 vs Charge Limit for Different Patterns", fontsize=16)
            fig.tight_layout(rect=[0, 0.03, 1, 0.95])
            if save_plots:
                name_of_file = 'tdiff_fitted_sigma_1_vs_charge_limit.png'
                final_filename = f'{fig_idx}_{name_of_file}'
                fig_idx += 1
                save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
                plot_list.append(save_fig_path)
                save_plot_figure(save_fig_path, format='png')
            if show_plots:
                plt.show()
            plt.close()

        if task3_plot_enabled("tdiff_pattern_sigma2_charge_surface"):
            fig, axs = plt.subplots(4, len(patterns_of_interest), figsize=(18, 24), sharex=True, sharey=True)
            for i_plane in range(1, 5):
                for j_pattern, pattern in enumerate(patterns_of_interest):
                    ax = axs[i_plane - 1, j_pattern]

                    charge_limits_1 = []
                    charge_limits_2 = []
                    mu1_values = []
                    mu2_values = []
                    sigma1_values = []
                    sigma2_values = []

                    for charge_limit_1 in charge_limits_to_loop:
                        for charge_limit_2 in charge_limits_to_loop:
                            key = (f'Charge_1_{charge_limit_1:.1f}', f'Charge_2_{charge_limit_2:.1f}', f'Plane_{i_plane}', pattern)

                            if key in all_results_loop:
                                A1, mu1, sigma1, A2, mu2, sigma2 = all_results_loop[key]
                                charge_limits_1.append(charge_limit_1)
                                charge_limits_2.append(charge_limit_2)
                                mu1_values.append(mu1)
                                sigma1_values.append(sigma1)
                                mu2_values.append(mu2)
                                sigma2_values.append(sigma2)

                    print(sigma1_values)

                    charge1_values = charge_limits_1
                    charge2_values = charge_limits_2

                    unique_c1 = np.array(sorted(set(charge1_values)))
                    unique_c2 = np.array(sorted(set(charge2_values)))
                    C1, C2 = np.meshgrid(unique_c1, unique_c2, indexing='xy')

                    sigma1_grid = np.full(C1.shape, np.nan, dtype=float)
                    sigma2_grid = np.full(C2.shape, np.nan, dtype=float)
                    idx_c1 = {c: j for j, c in enumerate(unique_c1)}
                    idx_c2 = {c: i for i, c in enumerate(unique_c2)}

                    for c1, c2, s1, s2 in zip(charge1_values, charge2_values, sigma1_values, sigma2_values):
                        i = idx_c2[c2]
                        j = idx_c1[c1]
                        sigma1_grid[i, j] = s1
                        sigma2_grid[i, j] = s2

                    Z = sigma2_grid
                    if np.all(np.isnan(Z)):
                        ax.set_title(f'Plane {i_plane}, Pattern {pattern}\n(no valid fits)')
                        ax.set_xticks([])
                        ax.set_yticks([])
                        continue

                    cs = ax.contourf(C1, C2, Z, levels=20)
                    fig.colorbar(cs, ax=ax)
                    ax.set_title(f'Plane {i_plane}, Pattern {pattern}')
                    ax.set_xlabel('Charge 1')
                    ax.set_ylabel('Charge 2')
                    ax.grid(True)

            fig.suptitle("Fitted Sigma 2 vs Charge Limit for Different Patterns", fontsize=16)
            fig.tight_layout(rect=[0, 0.03, 1, 0.95])
            if save_plots:
                name_of_file = 'tdiff_fitted_sigma_2_vs_charge_limit.png'
                final_filename = f'{fig_idx}_{name_of_file}'
                fig_idx += 1
                save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
                plot_list.append(save_fig_path)
                save_plot_figure(save_fig_path, format='png')
            if show_plots:
                plt.show()
            plt.close()

_prof["s_multi_strip_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()
_t_y_position_core = _t_sec
print("----------------------------------------------------------------------")
print("----------------------- Y position calculation -----------------------")
print("----------------------------------------------------------------------")

# Y ---------------------------------------------------------------------------
y_widths = [np.array([narrow_strip, narrow_strip, narrow_strip, wide_strip]),
            np.array([wide_strip, narrow_strip, narrow_strip, narrow_strip])]

y_pos_T = [y_pos(y_widths[0]), y_pos(y_widths[1])]
y_width_P1_and_P3 = y_widths[0]
y_width_P2_and_P4 = y_widths[1]
y_pos_P1_and_P3 = y_pos(y_width_P1_and_P3)
y_pos_P2_and_P4 = y_pos(y_width_P2_and_P4)
total_width = np.sum(y_width_P1_and_P3)

print("Total width:", total_width)

strip_boundaries_1_3 = np.cumsum(np.insert(y_widths[0], 0, 0)) - total_width / 2
strip_boundaries_2_4 = np.cumsum(np.insert(y_widths[1], 0, 0)) - total_width / 2

if y_new_method:
    y_columns = {}

    for plane_id in range(1, 5):
        # Decode binary strip activity per plane into shape (N_events, 4)
        topo_binary = np.array([
            list(map(int, s)) for s in working_df[f'active_strips_P{plane_id}']
        ])

        q_plane_cols = [
            _task3_prefer_calibrated_strip_column(f'p{plane_id}_s{i}_qsum')
            for i in range(1, 5)
        ]
        q_plane = (
            working_df[q_plane_cols]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0)
            .to_numpy(dtype=float)
        )  # shape (N, 4)

        # Take only active strips' charges
        q_active = topo_binary * q_plane

        # y-position vector by plane ID
        y_vec = y_pos_P1_and_P3 if plane_id in [1, 3] else y_pos_P2_and_P4

        # Initial weighted y estimate (default for multi-strip)
        weighted_y = q_active * y_vec
        active_counts = topo_binary.sum(axis=1)
        total_charge = q_active.sum(axis=1)
        total_charge_safe = np.where(total_charge == 0, 1, total_charge)

        y_position = weighted_y.sum(axis=1) / total_charge_safe
        y_position[active_counts == 0] = 0  # zero when no strips active

        # Apply uniform blur only to single-strip cases (vectorized)
        one_strip_mask = active_counts == 1

        if np.any(one_strip_mask):
            # Which row indices are single-strip?
            rows = np.where(one_strip_mask)[0]
            # For those rows, which strip is active? (use topo_binary or q_active)
            cols = topo_binary[one_strip_mask].argmax(axis=1)  # shape (n_single,)

            # Centers and widths for the selected strips
            y_vec = y_pos_P1_and_P3 if plane_id in [1, 3] else y_pos_P2_and_P4
            widths_vec = y_width_P1_and_P3 if plane_id in [1, 3] else y_width_P2_and_P4

            centers = y_vec[cols]
            widths  = widths_vec[cols]

            # Random uniform within the active strip
            y_position[rows] = np.random.uniform(centers - widths/2, centers + widths/2)

        # Store result
        y_columns[f'p{plane_id}_ypos'] = y_position

    # Insert all new Y_ columns at once
    working_df = pd.concat([working_df, pd.DataFrame(y_columns, index=working_df.index)], axis=1)
    _prof["s_y_position_core_s"] = round(time.perf_counter() - _t_y_position_core, 2)
else:
    y_columns = {}

    for plane_id in range(1, 5):
        q_plane_cols = [
            _task3_prefer_calibrated_strip_column(f'p{plane_id}_s{i}_qsum')
            for i in range(1, 5)
        ]
        q_plane = (
            working_df[q_plane_cols]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0)
            .to_numpy(dtype=float)
        )
        y_vec = y_pos_P1_and_P3 if plane_id in [1, 3] else y_pos_P2_and_P4
        widths_vec = y_width_P1_and_P3 if plane_id in [1, 3] else y_width_P2_and_P4

        positive_q_plane = np.where(np.isfinite(q_plane) & (q_plane > 0.0), q_plane, 0.0)
        total_charge = positive_q_plane.sum(axis=1)
        max_strip_idx = positive_q_plane.argmax(axis=1)
        y_position = np.zeros(len(working_df), dtype=float)

        nonzero_mask = total_charge > 0
        if np.any(nonzero_mask):
            rows = np.where(nonzero_mask)[0]
            cols = max_strip_idx[nonzero_mask]
            centers = y_vec[cols]
            widths = widths_vec[cols]
            y_position[rows] = np.random.uniform(centers - widths / 2, centers + widths / 2)

        y_columns[f'p{plane_id}_ypos'] = y_position

    working_df = pd.concat([working_df, pd.DataFrame(y_columns, index=working_df.index)], axis=1)
    _prof["s_y_position_core_s"] = round(time.perf_counter() - _t_y_position_core, 2)

for plane_id in range(1, 5):
    q_col = f"p{plane_id}_qsum"
    y_col = f"p{plane_id}_ypos"
    if q_col not in working_df.columns or y_col not in working_df.columns:
        continue
    active_plane = pd.to_numeric(working_df[q_col], errors="coerce").fillna(0.0).gt(0.0)
    zero_y_active = active_plane & pd.to_numeric(working_df[y_col], errors="coerce").fillna(0.0).eq(0.0)
    print(
        f"Task 3 Y diagnostic P{plane_id}: "
        f"active_qsum_rows={int(active_plane.sum())}, "
        f"active_rows_with_ypos_zero={int(zero_y_active.sum())}"
    )

# FINAL plot block moved out of the runtime flow: y_position_by_tt_task2_cal
pass

print("Y position calculated.")

_prof["s_y_pos_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()
print("----------------------------------------------------------------------")
print("------------ Last comprobation to the per-strip variables ------------")
print("----------------------------------------------------------------------")

# FINAL plot block moved out of the runtime flow: strip_variable_pairgrid
pass

# FINAL plot block moved out of the runtime flow: self_trigger_strip_variable_pairgrid
pass

_prof["s_last_comprobation_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()
_t_rpc_vars_core = _t_sec
print("----------------------------------------------------------------------")
print("----------------- Setting the variables of each RPC ------------------")
print("----------------------------------------------------------------------")
print(
    "Task 3 plane T_sum/T_dif aggregation: "
    + (
        "charge-weighted by active strip Q_sum"
        if weighted_by_charge_for_plane_tsum_and_tdif
        else "arithmetic mean over active strips"
    )
)

# Build the raw per-plane observables first. The filtering/zeroing path is
# applied immediately afterwards, one variable family at a time.
plane_raw_values: dict[int, dict[str, np.ndarray]] = {}
final_columns: dict[str, np.ndarray] = {}

for i_plane in range(1, 5):
    t_sum_cols = [_task3_prefer_calibrated_strip_column(f'p{i_plane}_s{i+1}_tsum') for i in range(4)]
    t_dif_cols = [_task3_prefer_calibrated_strip_column(f'p{i_plane}_s{i+1}_tdif') for i in range(4)]
    q_sum_cols = [_task3_prefer_calibrated_strip_column(f'p{i_plane}_s{i+1}_qsum') for i in range(4)]
    q_dif_cols = [_task3_prefer_calibrated_strip_column(f'p{i_plane}_s{i+1}_qdif') for i in range(4)]

    t_sums = working_df[t_sum_cols].astype(float).fillna(0).to_numpy(copy=False)
    t_difs = working_df[t_dif_cols].astype(float).fillna(0).to_numpy(copy=False)
    q_sums = working_df[q_sum_cols].astype(float).fillna(0).to_numpy(copy=False)
    q_difs = working_df[q_dif_cols].astype(float).fillna(0).to_numpy(copy=False)

    active_mask = np.array(
        [list(map(int, s)) for s in working_df[f'active_strips_P{i_plane}']],
        dtype=float,
    )
    n_active = active_mask.sum(axis=1)
    n_active_safe = np.where(n_active == 0, 1, n_active)

    t_sum_mean = (t_sums * active_mask).sum(axis=1) / n_active_safe
    t_dif_mean = (t_difs * active_mask).sum(axis=1) / n_active_safe
    if weighted_by_charge_for_plane_tsum_and_tdif:
        charge_weights = q_sums * active_mask
        charge_weight_sum = charge_weights.sum(axis=1)
        charge_weight_sum_safe = np.where(charge_weight_sum == 0, 1, charge_weight_sum)
        t_sum_weighted = (t_sums * charge_weights).sum(axis=1) / charge_weight_sum_safe
        t_dif_weighted = (t_difs * charge_weights).sum(axis=1) / charge_weight_sum_safe
        has_charge_weight = charge_weight_sum > 0
        t_sum_final = np.where(has_charge_weight, t_sum_weighted, t_sum_mean)
        t_dif_final = np.where(has_charge_weight, t_dif_weighted, t_dif_mean)
    else:
        t_sum_final = t_sum_mean
        t_dif_final = t_dif_mean
    q_sum_final = (q_sums * active_mask).sum(axis=1)
    q_dif_final = (q_difs * active_mask).sum(axis=1)

    t_sum_final[n_active == 0] = 0
    t_dif_final[n_active == 0] = 0
    q_sum_final[n_active == 0] = 0
    q_dif_final[n_active == 0] = 0

    plane_raw_values[i_plane] = {
        "T_sum": t_sum_final.copy(),
        "T_dif": t_dif_final.copy(),
        "Q_sum": q_sum_final.copy(),
        "Q_dif": q_dif_final.copy(),
    }
    final_columns[f'p{i_plane}_tsum'] = t_sum_final
    final_columns[f'p{i_plane}_tdif'] = t_dif_final
    final_columns[f'p{i_plane}_qsum'] = q_sum_final
    final_columns[f'p{i_plane}_qdif'] = q_dif_final

working_df = pd.concat([working_df, pd.DataFrame(final_columns, index=working_df.index)], axis=1)
task3_xpos_summary = ensure_plane_xpos_columns(
    working_df,
    tdiff_to_x,
    overwrite=True,
)
if task3_xpos_summary["source_columns_found"] != 4:
    raise RuntimeError(
        "Task 3 could not create all p1_xpos..p4_xpos columns: "
        f"{task3_xpos_summary}"
    )
print(
    "Task 3 stored final plane X positions: "
    f"columns_created={task3_xpos_summary['columns_created']} "
    f"scale_mm_per_ns={float(tdiff_to_x):.9g}"
)

tsum_cols = [f"p{plane}_tsum" for plane in range(1, 5)]
qsum_cols = [f"p{plane}_qsum" for plane in range(1, 5)]
if all(col in working_df.columns for col in [*tsum_cols, *qsum_cols]):
    tsum_values = working_df.loc[:, tsum_cols].apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy(dtype=float)
    qsum_values = working_df.loc[:, qsum_cols].apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy(dtype=float)
    positive_charge_mask = np.isfinite(qsum_values) & (qsum_values > 0)
    has_positive_charge = positive_charge_mask.any(axis=1)
    first_positive_plane_idx = np.where(has_positive_charge, positive_charge_mask.argmax(axis=1), 0)
    row_indices = np.arange(len(working_df))
    reference_tsum = np.zeros(len(working_df), dtype=float)
    reference_tsum[has_positive_charge] = tsum_values[
        row_indices[has_positive_charge],
        first_positive_plane_idx[has_positive_charge],
    ]
    tsum_relative = tsum_values.copy()
    tsum_relative[has_positive_charge] = (
        tsum_relative[has_positive_charge]
        - reference_tsum[has_positive_charge, np.newaxis]
        + 1.0
    )
    tsum_relative[~positive_charge_mask] = 0
    tsum_relative[~has_positive_charge] = 0
    working_df.loc[:, tsum_cols] = tsum_relative
    for i_plane in range(1, 5):
        plane_raw_values[i_plane]["T_sum"] = tsum_relative[:, i_plane - 1].copy()

_prof["s_rpc_vars_core_s"] = round(time.perf_counter() - _t_rpc_vars_core, 2)



# FINAL plot block moved out of the runtime flow: rpc_variables_hexbin
pass

# FINAL plot block moved out of the runtime flow: rpc_variables_hexbin_low_charge
pass

_prof["s_rpc_vars_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()
print("----------------------------------------------------------------------")
print("---- Tsum already referenced to first positive-charge plane -----------")
print("----------------------------------------------------------------------")

filter6_cols: list[str] = []
for i_plane in range(1, 5):
    filter6_cols.extend([
        f"p{i_plane}_ypos",
        f"p{i_plane}_tsum",
        f"p{i_plane}_tdif",
        f"p{i_plane}_qsum",
        f"p{i_plane}_qdif",
    ])
filter6_cols = [col for col in filter6_cols if col in working_df.columns]

if filter6_cols and task3_any_plot_enabled(
    "filter6_tsum_debug",
    "filter6_tdif_debug",
    "filter6_qsum_debug",
    "filter6_qdif_debug",
    "filter6_y_debug",
):
    t_sum_cols = [col for col in filter6_cols if "T_sum_final" in col]
    if t_sum_cols and task3_plot_enabled("filter6_tsum_debug"):
        debug_thresholds = {
            col: [plane_combination_plane_t_sum_sum_left, plane_combination_plane_t_sum_sum_right]
            for col in t_sum_cols
        }
        debug_fig_idx = plot_debug_histograms(
            working_df,
            t_sum_cols,
            debug_thresholds,
            title=(
                f"Task 3 same-plane T_sum bounds: plane_combination_plane_t_sum_sum_left/right "
                f"[tunable] (station {station})"
            ),
            out_dir=debug_plot_directory,
            fig_idx=debug_fig_idx,
        )

    t_dif_cols = [col for col in filter6_cols if "T_dif_final" in col]
    if t_dif_cols and task3_plot_enabled("filter6_tdif_debug"):
        debug_thresholds = {
            col: [
                -plane_combination_plane_t_dif_sum_threshold,
                plane_combination_plane_t_dif_sum_threshold,
            ]
            for col in t_dif_cols
        }
        debug_fig_idx = plot_debug_histograms(
            working_df,
            t_dif_cols,
            debug_thresholds,
            title=(
                f"Task 3 same-plane T_dif bounds: plane_combination_plane_t_dif_sum_threshold "
                f"[tunable] (station {station})"
            ),
            out_dir=debug_plot_directory,
            fig_idx=debug_fig_idx,
        )

    q_sum_cols = [col for col in filter6_cols if "Q_sum_final" in col]
    if q_sum_cols and task3_plot_enabled("filter6_qsum_debug"):
        debug_thresholds = {
            col: [plane_combination_plane_q_sum_sum_left, plane_combination_plane_q_sum_sum_right]
            for col in q_sum_cols
        }
        debug_fig_idx = plot_debug_histograms(
            working_df,
            q_sum_cols,
            debug_thresholds,
            title=(
                f"Task 3 same-plane Q_sum bounds: plane_combination_plane_q_sum_sum_left/right "
                f"[tunable] (station {station})"
            ),
            out_dir=debug_plot_directory,
            fig_idx=debug_fig_idx,
        )

    q_dif_cols = [col for col in filter6_cols if "Q_dif_final" in col]
    if q_dif_cols and task3_plot_enabled("filter6_qdif_debug"):
        debug_thresholds = {
            col: [
                -plane_combination_plane_q_dif_sum_threshold,
                plane_combination_plane_q_dif_sum_threshold,
            ]
            for col in q_dif_cols
        }
        debug_fig_idx = plot_debug_histograms(
            working_df,
            q_dif_cols,
            debug_thresholds,
            title=(
                f"Task 3 same-plane Q_dif bounds: plane_combination_plane_q_dif_sum_threshold "
                f"[tunable] (station {station})"
            ),
            out_dir=debug_plot_directory,
            fig_idx=debug_fig_idx,
        )

    y_cols = [col for col in filter6_cols if "Y_final" in col]
    if y_cols and task3_plot_enabled("filter6_y_debug"):
        debug_thresholds = {
            col: [plane_combination_plane_y_sum_left, plane_combination_plane_y_sum_right]
            for col in y_cols
        }
        debug_fig_idx = plot_debug_histograms(
            working_df,
            y_cols,
            debug_thresholds,
            title=(
                "Task 3 same-plane Y bounds: plane_combination_plane_y_sum_left/right "
                f"[tunable] (station {station})"
            ),
            out_dir=debug_plot_directory,
            fig_idx=debug_fig_idx,
        )

task3_pre_plane_block_summary = normalize_task3_plane_component_blocks(
    working_df,
    snapshot_originals=snapshot_original_columns_once,
    apply_changes=False,
)
print(
    "[task3-plane-block-normalization] "
    f"phase=pre-final-filter rows_affected={task3_pre_plane_block_summary['rows_affected']} "
    f"planes_affected={task3_pre_plane_block_summary['planes_affected']} "
    f"values_zeroed={task3_pre_plane_block_summary['values_zeroed']}"
)
record_filter6_counts(working_df, "before_filter6")

_plot_plane_combination_filter_by_tt = task3_plot_enabled("plane_combination_filter_by_tt")
if _plot_plane_combination_filter_by_tt:
    plane_combination_tt_original = _task3_filter_tt_series(working_df).copy()
    plane_combination_self_hist_original = collect_task3_plane_combination_histogram_payload(
        working_df,
        plane_combination_tt_original,
        relation_type="plane",
    )
    plane_combination_any_hist_original = collect_task3_plane_combination_histogram_payload(
        working_df,
        plane_combination_tt_original,
        relation_type="detector",
    )
else:
    plane_combination_tt_original = pd.Series(dtype=str)
    plane_combination_self_hist_original = pd.DataFrame()
    plane_combination_any_hist_original = pd.DataFrame()

_prof["s_tsum_ref_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()
print("-------------- Unified plane-combination offender filter -------------")

plane_combination_summary = apply_task3_plane_combination_filter(
    working_df,
    plane_q_sum_sum_left=plane_combination_plane_q_sum_sum_left,
    plane_q_sum_sum_right=plane_combination_plane_q_sum_sum_right,
    plane_q_dif_sum_threshold=plane_combination_plane_q_dif_sum_threshold,
    plane_t_sum_sum_left=plane_combination_plane_t_sum_sum_left,
    plane_t_sum_sum_right=plane_combination_plane_t_sum_sum_right,
    plane_t_dif_sum_threshold=plane_combination_plane_t_dif_sum_threshold,
    plane_y_sum_left=plane_combination_plane_y_sum_left,
    plane_y_sum_right=plane_combination_plane_y_sum_right,
    detector_q_sum_sum_left=plane_combination_detector_q_sum_sum_left,
    detector_q_sum_sum_right=plane_combination_detector_q_sum_sum_right,
    detector_q_sum_dif_threshold=plane_combination_detector_q_sum_dif_threshold,
    detector_q_dif_sum_threshold=plane_combination_detector_q_dif_sum_threshold,
    detector_q_dif_dif_threshold=plane_combination_detector_q_dif_dif_threshold,
    detector_t_sum_sum_left=plane_combination_detector_t_sum_sum_left,
    detector_t_sum_sum_right=plane_combination_detector_t_sum_sum_right,
    detector_t_sum_dif_threshold=plane_combination_detector_t_sum_dif_threshold,
    detector_t_dif_sum_threshold=plane_combination_detector_t_dif_sum_threshold,
    detector_t_dif_dif_threshold=plane_combination_detector_t_dif_dif_threshold,
    detector_y_sum_left=plane_combination_detector_y_sum_left,
    detector_y_sum_right=plane_combination_detector_y_sum_right,
    detector_y_dif_threshold=plane_combination_detector_y_dif_threshold,
    apply_changes=False,
)
passes_task_3 = np.full(len(working_df), np.uint8(0x0F), dtype=np.uint8)
plane_fail_masks = plane_combination_summary.get("selected_offender_mask_by_plane", {})
if isinstance(plane_fail_masks, dict):
    for bit_idx, plane_key in enumerate(TASK3_PLANE_KEYS):
        fail_series = plane_fail_masks.get(plane_key)
        if fail_series is None:
            continue
        fail_mask = fail_series.reindex(working_df.index, fill_value=False).to_numpy(dtype=bool)
        passes_task_3[fail_mask] &= np.uint8(~(1 << bit_idx) & 0x0F)
working_df.loc[:, "passes_task_3"] = passes_task_3

plane_metric_specs = (
    (
        "q_sum_sum",
        "plane_combination_plane_q_sum_sum",
        "Q_sum",
        plane_combination_plane_q_sum_sum_left,
        plane_combination_plane_q_sum_sum_right,
    ),
    (
        "q_dif_sum",
        "plane_combination_plane_q_dif_sum",
        "Q_dif",
        -abs(plane_combination_plane_q_dif_sum_threshold),
        abs(plane_combination_plane_q_dif_sum_threshold),
    ),
    (
        "t_sum_sum",
        "plane_combination_plane_t_sum_sum",
        "T_sum",
        plane_combination_plane_t_sum_sum_left,
        plane_combination_plane_t_sum_sum_right,
    ),
    (
        "t_dif_sum",
        "plane_combination_plane_t_dif_sum",
        "T_dif",
        -abs(plane_combination_plane_t_dif_sum_threshold),
        abs(plane_combination_plane_t_dif_sum_threshold),
    ),
    (
        "y_sum",
        "plane_combination_plane_y_sum",
        "Y",
        plane_combination_plane_y_sum_left,
        plane_combination_plane_y_sum_right,
    ),
)

record_filter_metric(
    "plane_combination_plane_rows_affected_pct",
    plane_combination_summary["plane_rows_affected"],
    len(working_df) if len(working_df) else 0,
)
for observable_key, metric_prefix, metric_label, left_limit, right_limit in plane_metric_specs:
    low_key, high_key = TASK3_PLANE_SELF_OBSERVABLE_LIMIT_KEYS[observable_key]
    candidate_count = int(
        plane_combination_summary["plane_candidate_observations"].get(observable_key, 0)
    )
    low_failed = int(plane_combination_summary["plane_failed_limits"].get(low_key, 0))
    high_failed = int(plane_combination_summary["plane_failed_limits"].get(high_key, 0))
    rows_failed_low = int(
        plane_combination_summary["plane_rows_failed_limits"].get(low_key, 0)
    )
    rows_failed_high = int(
        plane_combination_summary["plane_rows_failed_limits"].get(high_key, 0)
    )
    filter_metrics[f"{metric_prefix}_low_limit"] = round(float(left_limit), 6)
    filter_metrics[f"{metric_prefix}_high_limit"] = round(float(right_limit), 6)
    record_activity_metric(
        f"{metric_prefix}_low_failed_pct",
        low_failed,
        candidate_count,
        label=f"{metric_label} values below lower limit",
    )
    record_activity_metric(
        f"{metric_prefix}_high_failed_pct",
        high_failed,
        candidate_count,
        label=f"{metric_label} values above upper limit",
    )
    record_activity_metric(
        f"{metric_prefix}_failed_pct",
        low_failed + high_failed,
        candidate_count,
        label=f"{metric_label} values outside limits",
    )
    record_activity_metric(
        f"{metric_prefix}_low_rows_failed_pct",
        rows_failed_low,
        len(working_df) if len(working_df) else 0,
        label=f"rows with {metric_label} lower-limit failures",
    )
    record_activity_metric(
        f"{metric_prefix}_high_rows_failed_pct",
        rows_failed_high,
        len(working_df) if len(working_df) else 0,
        label=f"rows with {metric_label} upper-limit failures",
    )
    record_activity_metric(
        f"{metric_prefix}_rows_failed_pct",
        rows_failed_low + rows_failed_high,
        len(working_df) if len(working_df) else 0,
        label=f"rows with {metric_label} boundary failures",
    )

task3_post_plane_block_summary = normalize_task3_plane_component_blocks(
    working_df,
    snapshot_originals=snapshot_original_columns_once,
    apply_changes=False,
)
print(
    "[task3-plane-block-normalization] "
    f"phase=post-final-filter rows_affected={task3_post_plane_block_summary['rows_affected']} "
    f"planes_affected={task3_post_plane_block_summary['planes_affected']} "
    f"values_zeroed={task3_post_plane_block_summary['values_zeroed']}"
)
record_filter6_counts(working_df, "after_filter6")
_prof["s_filter6_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()

if _plot_plane_combination_filter_by_tt:
    plane_combination_self_hist_after = collect_task3_plane_combination_histogram_payload(
        working_df,
        plane_combination_tt_original,
        relation_type="plane",
    )
    plane_combination_any_hist_after = collect_task3_plane_combination_histogram_payload(
        working_df,
        plane_combination_tt_original,
        relation_type="detector",
    )
else:
    plane_combination_self_hist_after = pd.DataFrame()
    plane_combination_any_hist_after = pd.DataFrame()

print("----------------------------------------------------------------------")
print("----------- Unified detector and same-plane consistency --------------")
print("----------------------------------------------------------------------")

record_activity_metric(
    "plane_combination_filter_rows_affected_pct",
    plane_combination_summary["detector_rows_affected"],
    len(working_df) if len(working_df) else 0,
    label="rows with detector plane-combination failures",
)
record_activity_metric(
    "plane_combination_filter_values_zeroed_pct",
    plane_combination_summary["values_zeroed"],
    len(working_df) * (5 * plane_combination_summary["tracked_plane_count"])
    if (len(working_df) and plane_combination_summary["tracked_plane_count"])
    else 0,
    label="plane values zeroed by plane-combination filter",
)
record_activity_metric(
    "plane_combination_filter_detector_failed_pct",
    plane_combination_summary["failed_pair_any"],
    plane_combination_summary["valid_pair_observations"],
    label="failed detector comparisons",
)
record_activity_metric(
    "plane_combination_filter_any_failed_pct",
    plane_combination_summary["failed_pair_any"],
    plane_combination_summary["valid_pair_observations"],
    label="failed plane combinations",
)
record_activity_metric(
    "plane_combination_filter_q_sum_sum_failed_pct",
    plane_combination_summary["failed_pair_q_sum_sum"],
    plane_combination_summary["valid_pair_observations"],
    label="Q_sum semisum failed plane combinations",
)
record_activity_metric(
    "plane_combination_filter_q_sum_dif_failed_pct",
    plane_combination_summary["failed_pair_q_sum_dif"],
    plane_combination_summary["valid_pair_observations"],
    label="Q_sum semidifference failed plane combinations",
)
record_activity_metric(
    "plane_combination_filter_q_dif_sum_failed_pct",
    plane_combination_summary["failed_pair_q_dif_sum"],
    plane_combination_summary["valid_pair_observations"],
    label="Q_dif semisum failed plane combinations",
)
record_activity_metric(
    "plane_combination_filter_q_dif_dif_failed_pct",
    plane_combination_summary["failed_pair_q_dif_dif"],
    plane_combination_summary["valid_pair_observations"],
    label="Q_dif semidifference failed plane combinations",
)
record_activity_metric(
    "plane_combination_filter_t_sum_sum_failed_pct",
    plane_combination_summary["failed_pair_t_sum_sum"],
    plane_combination_summary["valid_pair_observations"],
    label="T_sum semisum failed plane combinations",
)
record_activity_metric(
    "plane_combination_filter_t_sum_dif_failed_pct",
    plane_combination_summary["failed_pair_t_sum_dif"],
    plane_combination_summary["valid_pair_observations"],
    label="T_sum semidifference failed plane combinations",
)
record_activity_metric(
    "plane_combination_filter_t_dif_sum_failed_pct",
    plane_combination_summary["failed_pair_t_dif_sum"],
    plane_combination_summary["valid_pair_observations"],
    label="T_dif semisum failed plane combinations",
)
record_activity_metric(
    "plane_combination_filter_t_dif_dif_failed_pct",
    plane_combination_summary["failed_pair_t_dif_dif"],
    plane_combination_summary["valid_pair_observations"],
    label="T_dif semidifference failed plane combinations",
)
record_activity_metric(
    "plane_combination_filter_y_sum_failed_pct",
    plane_combination_summary["failed_pair_y_sum"],
    plane_combination_summary["valid_pair_observations"],
    label="Y semisum failed plane combinations",
)
record_activity_metric(
    "plane_combination_filter_y_dif_failed_pct",
    plane_combination_summary["failed_pair_y_dif"],
    plane_combination_summary["valid_pair_observations"],
    label="Y semidifference failed plane combinations",
)
for limit_key, limit_label in TASK3_PLANE_COMBINATION_LIMIT_LABELS.items():
    record_activity_metric(
        f"plane_combination_filter_{limit_key}_failed_pct",
        plane_combination_summary.get(f"failed_pair_{limit_key}", 0),
        plane_combination_summary["valid_pair_observations"],
        label=f"{limit_label} failed plane combinations",
    )
    record_activity_metric(
        f"plane_combination_filter_{limit_key}_rows_failed_pct",
        plane_combination_summary.get(f"rows_failed_{limit_key}", 0),
        len(working_df) if len(working_df) else 0,
        label=f"rows with {limit_label} failures",
    )
print(
    "[plane-combination-filter] "
    f"valid_pair_obs={plane_combination_summary['valid_pair_observations']} "
    f"failed_any={plane_combination_summary['failed_pair_any']} "
    f"plane_rows={plane_combination_summary['plane_rows_affected']} "
    f"detector_rows={plane_combination_summary['detector_rows_affected']} "
    f"rows_affected={plane_combination_summary['rows_affected']} "
    f"flagged_rows={plane_combination_summary['flagged_rows']} "
    f"selected_offenders={plane_combination_summary['selected_offender_planes']}"
)
global_variables["plane_combination_filter_flagged_rows"] = int(
    plane_combination_summary["flagged_rows"]
)
global_variables["plane_combination_filter_input_rows"] = int(
    plane_combination_summary.get("input_rows", len(working_df))
)
global_variables["plane_combination_filter_selected_offender_planes"] = int(
    plane_combination_summary["selected_offender_planes"]
)
global_variables["plane_combination_filter_rows_with_multiple_offenders"] = int(
    plane_combination_summary["rows_with_multiple_offenders"]
)
global_variables["plane_combination_filter_max_failed_pairs_in_row"] = int(
    plane_combination_summary["max_failed_pairs_in_row"]
)
global_variables["plane_combination_filter_max_selected_offenders_in_row"] = int(
    plane_combination_summary["max_selected_offenders_in_row"]
)
for selected_count in TASK3_SELECTED_OFFENDER_CARDINALITY_VALUES:
    selected_rows = int(
        plane_combination_summary["selected_offender_cardinality_counts"].get(selected_count, 0)
    )
    global_variables[_task3_selected_offender_cardinality_metric_key(selected_count)] = selected_rows
for plane_key, offender_count in plane_combination_summary["selected_offender_counts"].items():
    global_variables[_task3_plane_offender_metric_key(plane_key)] = int(offender_count)
working_df.loc[:, "filter_task3_problematic_plane_count"] = (
    plane_combination_summary["selected_offender_count_by_row"]
    .reindex(working_df.index)
    .fillna(0)
    .astype(int)
    .to_numpy()
)
working_df.loc[:, "filter_task3_problematic_plane_exact"] = (
    plane_combination_summary["resolution_exact_by_row"]
    .reindex(working_df.index, fill_value=True)
    .astype(bool)
    .to_numpy()
)

filter_task1_problematic_channel_count = pd.to_numeric(
    working_df.get(
        "filter_task1_problematic_channel_count",
        pd.Series(index=working_df.index, dtype=float),
    ),
    errors="coerce",
).fillna(0).astype(int)
filter_task2_problematic_strip_count = pd.to_numeric(
    working_df.get(
        "filter_task2_problematic_strip_count",
        pd.Series(index=working_df.index, dtype=float),
    ),
    errors="coerce",
).fillna(0).astype(int)
filter_task3_problematic_plane_count_series = pd.to_numeric(
    working_df.get(
        "filter_task3_problematic_plane_count",
        pd.Series(index=working_df.index, dtype=float),
    ),
    errors="coerce",
).fillna(0).astype(int)
filter_total_problematic_offender_count = (
    filter_task1_problematic_channel_count
    + filter_task2_problematic_strip_count
    + filter_task3_problematic_plane_count_series
).astype(int)

working_df.loc[:, "filter_task1_problematic_channel_count"] = filter_task1_problematic_channel_count.to_numpy()
working_df.loc[:, "filter_task2_problematic_strip_count"] = filter_task2_problematic_strip_count.to_numpy()
working_df.loc[:, "filter_task3_problematic_plane_count"] = filter_task3_problematic_plane_count_series.to_numpy()
for exact_column in (
    "filter_task1_problematic_channel_exact",
    "filter_task2_problematic_strip_exact",
    "filter_task3_problematic_plane_exact",
):
    if exact_column in working_df.columns:
        working_df.loc[:, exact_column] = working_df[exact_column].astype(bool).to_numpy()
working_df.loc[:, "filter_total_problematic_offender_count"] = (
    filter_total_problematic_offender_count.to_numpy()
)

filter_total_problematic_offender_count_counts = (
    filter_total_problematic_offender_count.value_counts().sort_index()
)
global_variables["plane_combination_filter_max_selected_offenders_in_row"] = int(
    filter_total_problematic_offender_count.max() if len(filter_total_problematic_offender_count) else 0
)
for selected_count in TASK3_SELECTED_OFFENDER_CARDINALITY_VALUES:
    global_variables[_task3_selected_offender_cardinality_metric_key(selected_count)] = int(
        filter_total_problematic_offender_count_counts.get(selected_count, 0)
    )
if _plot_plane_combination_filter_by_tt:
    plane_combination_same_plane_limits = {
        "q_sum_sum": (plane_combination_plane_q_sum_sum_left, plane_combination_plane_q_sum_sum_right),
        "q_dif_sum": (-abs(plane_combination_plane_q_dif_sum_threshold), abs(plane_combination_plane_q_dif_sum_threshold)),
        "t_sum_sum": (plane_combination_plane_t_sum_sum_left, plane_combination_plane_t_sum_sum_right),
        "t_dif_sum": (-abs(plane_combination_plane_t_dif_sum_threshold), abs(plane_combination_plane_t_dif_sum_threshold)),
        "y_sum": (plane_combination_plane_y_sum_left, plane_combination_plane_y_sum_right),
    }
    plane_combination_any_limits = {
        "q_sum_sum": (plane_combination_detector_q_sum_sum_left, plane_combination_detector_q_sum_sum_right),
        "q_sum_dif": (-abs(plane_combination_detector_q_sum_dif_threshold), abs(plane_combination_detector_q_sum_dif_threshold)),
        "q_dif_sum": (-abs(plane_combination_detector_q_dif_sum_threshold), abs(plane_combination_detector_q_dif_sum_threshold)),
        "q_dif_dif": (-abs(plane_combination_detector_q_dif_dif_threshold), abs(plane_combination_detector_q_dif_dif_threshold)),
        "t_sum_sum": (plane_combination_detector_t_sum_sum_left, plane_combination_detector_t_sum_sum_right),
        "t_sum_dif": (-abs(plane_combination_detector_t_sum_dif_threshold), abs(plane_combination_detector_t_sum_dif_threshold)),
        "t_dif_sum": (-abs(plane_combination_detector_t_dif_sum_threshold), abs(plane_combination_detector_t_dif_sum_threshold)),
        "t_dif_dif": (-abs(plane_combination_detector_t_dif_dif_threshold), abs(plane_combination_detector_t_dif_dif_threshold)),
        "y_sum": (plane_combination_detector_y_sum_left, plane_combination_detector_y_sum_right),
        "y_dif": (-abs(plane_combination_detector_y_dif_threshold), abs(plane_combination_detector_y_dif_threshold)),
    }
    fig_idx = plot_task3_plane_combination_filter_by_tt(
        plane_combination_self_hist_original,
        plane_combination_self_hist_original,
        plane_combination_self_hist_after,
        basename_no_ext,
        fig_idx,
        base_directories["figure_directory"],
        show_plots=show_plots,
        save_plots=save_plots,
        plot_list=plot_list,
        limits_by_observable=plane_combination_same_plane_limits,
        relation_label="plane",
        observable_definitions=TASK3_PLANE_COMBINATION_SELF_OBSERVABLES,
    )
    fig_idx = plot_task3_plane_combination_filter_by_tt(
        plane_combination_any_hist_original,
        plane_combination_any_hist_original,
        plane_combination_any_hist_after,
        basename_no_ext,
        fig_idx,
        base_directories["figure_directory"],
        show_plots=show_plots,
        save_plots=save_plots,
        plot_list=plot_list,
        limits_by_observable=plane_combination_any_limits,
        relation_label="detector",
    )
_prof["s_plane_combination_filter_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()

# ----------------------------------------------------------------------------------------------------------------
# if stratos_save and station == 2:
if stratos_save:
    print("Saving X and Y for stratos.")

    # Select columns that start with "Y_" or match "T<number>_T_dif_final"
    filtered_columns = [col for col in working_df.columns if col.startswith("Y_") or "_T_dif_final" in col or 'datetime' in col]

    # Create a new DataFrame with the selected columns; copy is needed because
    # we rename and scale in-place below.
    filtered_stratos_df = working_df[filtered_columns].copy()

    # Rename "T<number>_T_dif_final" to "X_<number>" and multiply by 200
    filtered_stratos_df.rename(columns=lambda col: f'X_{col.split("_")[0][1:]}' if "_T_dif_final" in col else col, inplace=True)
    filtered_stratos_df.loc[:, filtered_stratos_df.columns.str.startswith("X_")] *= 200

    # Define the save path
    save_stratos = os.path.join(stratos_list_events_directory, f'stratos_data_{save_filename_suffix}.csv')

    # Save DataFrame to CSV (correcting the method name)
    filtered_stratos_df.to_csv(save_stratos, index=False, float_format="%.1f")
    del filtered_stratos_df
# ----------------------------------------------------------------------------------------------------------------

# Same for hexbin
# FINAL plot block moved out of the runtime flow: filtered_rpc_tsum_vs_qsum_scatter
pass

# FINAL plot block moved out of the runtime flow: filtered_rpc_tsum_vs_qsum_scatter_per_combination
pass

# FINAL plot block moved out of the runtime flow: filtered_rpc_tsum_vs_qsum_hexbin
pass

# FINAL plot block moved out of the runtime flow: filtered_rpc_variables_hexbin
pass

# Path to save the cleaned dataframe
# Create output directory if it does not exist.
os.makedirs(f"{output_directory}", exist_ok=True)
OUT_PATH = f"{output_directory}/listed_{basename_no_ext}.parquet"
KEY = "df"  # HDF5 key name

# Ensure output directory exists
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

# --- Example: your cleaned DataFrame is called working_df ---
# (Here, you would have your data cleaning code before saving)
# working_df = ...

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
        "Task 3 keep_all_columns_output enabled: "
        f"retaining {len(cols_to_remove)} strip-summary columns."
    )
else:
    working_df.drop(columns=cols_to_remove, inplace=True, errors='ignore')



# Pattern for P1_Q_sum_*, P2_Q_sum_*, P3_Q_sum_*, P4_Q_sum_*
Q_SUM_PATTERN = re.compile(r'^P[1-4]_Q_sum_.*$')

# Keep q_sum/all-zero checks as diagnostics only: do not drop rows here.
Q_cols = collect_columns(working_df.columns, Q_SUM_PATTERN)
if Q_cols and task3_plot_enabled("prefilter_qsum_nonzero_debug"):
    debug_thresholds = {col: [0] for col in Q_cols}
    debug_fig_idx = plot_debug_histograms(
        working_df,
        Q_cols,
        debug_thresholds,
        title=f"Task 3 pre-filter: Q_sum nonzero [NON-TUNABLE] (station {station})",
        out_dir=debug_plot_directory,
        fig_idx=debug_fig_idx,
    )
record_filter_metric(
    "q_sum_all_zero_rows_removed_pct",
    0,
    original_number_of_events if original_number_of_events else 0,
)

record_filter_metric(
    "all_components_zero_rows_removed_pct",
    0,
    len(working_df) if len(working_df) else 0,
)

print(f"Original number of events in the dataframe: {original_number_of_events}")
working_df = add_topology_task3_plane(working_df)
tt_task3_list_columns = {
    i_plane: [
        f"p{i_plane}_tsum",
        f"p{i_plane}_tdif",
        f"p{i_plane}_qsum",
        f"p{i_plane}_qdif",
        f"p{i_plane}_ypos",
    ]
    for i_plane in range(1, 5)
}
working_df = compute_tt(working_df, "tt_task3_list", tt_task3_list_columns)

# FINAL plot block moved out of the runtime flow: rpc_variables_hexbin_per_plane_combination
pass

task3_plane_activation_initial = store_task3_plane_activation_snapshot(
    activation_meta={},
    scalar_meta={},
    df=working_df,
    snapshot_label="initial",
    tt_series=pd.to_numeric(working_df["tt_task3_list"], errors="coerce"),
    streamer_high_charge_factor_value=streamer_high_charge_factor,
    streamer_threshold_override=streamer_charge_sum_threshold,
)
tt_task3_list_total = len(working_df)
if "tt_task3_list" in working_df.columns and task3_plot_enabled("prefilter_tt_task3_list_debug"):
    debug_fig_idx = plot_debug_histograms(
        working_df,
        ["tt_task3_list"],
        {"tt_task3_list": [10]},
        title=f"Task 3 pre-filter: tt_task3_list >= 10 [NON-TUNABLE] (station {station})",
        out_dir=debug_plot_directory,
        fig_idx=debug_fig_idx,
    )
tt_task3_list_mask = working_df["tt_task3_list"].notna() & (working_df["tt_task3_list"] >= 10)
working_df.loc[:, "filter_task3_tt_task3_list_pass"] = tt_task3_list_mask.to_numpy(dtype=bool)
working_df.loc[~tt_task3_list_mask, "passes_task_3"] = np.uint8(0)
record_filter_metric(
    "tt_task3_list_lt_10_rows_flagged_pct",
    tt_task3_list_total - int(tt_task3_list_mask.sum()),
    tt_task3_list_total if tt_task3_list_total else 0,
)
working_df.loc[:, "transferred_task3_cal_to_list"] = (
    pd.to_numeric(working_df["tt_task2_cal"], errors="coerce").fillna(0).astype(int).astype(str)
    + "_"
    + pd.to_numeric(working_df["tt_task3_list"], errors="coerce").fillna(0).astype(int).astype(str)
)
refresh_global_count_metadata(
    working_df,
    ("tt_task2_cal", "tt_task3_list", "transferred_task3_cal_to_list"),
)

task3_final_filter_dry_run_summary = apply_task3_plane_combination_filter(
    working_df,
    plane_q_sum_sum_left=plane_combination_plane_q_sum_sum_left,
    plane_q_sum_sum_right=plane_combination_plane_q_sum_sum_right,
    plane_q_dif_sum_threshold=plane_combination_plane_q_dif_sum_threshold,
    plane_t_sum_sum_left=plane_combination_plane_t_sum_sum_left,
    plane_t_sum_sum_right=plane_combination_plane_t_sum_sum_right,
    plane_t_dif_sum_threshold=plane_combination_plane_t_dif_sum_threshold,
    plane_y_sum_left=plane_combination_plane_y_sum_left,
    plane_y_sum_right=plane_combination_plane_y_sum_right,
    detector_q_sum_sum_left=plane_combination_detector_q_sum_sum_left,
    detector_q_sum_sum_right=plane_combination_detector_q_sum_sum_right,
    detector_q_sum_dif_threshold=plane_combination_detector_q_sum_dif_threshold,
    detector_q_dif_sum_threshold=plane_combination_detector_q_dif_sum_threshold,
    detector_q_dif_dif_threshold=plane_combination_detector_q_dif_dif_threshold,
    detector_t_sum_sum_left=plane_combination_detector_t_sum_sum_left,
    detector_t_sum_sum_right=plane_combination_detector_t_sum_sum_right,
    detector_t_sum_dif_threshold=plane_combination_detector_t_sum_dif_threshold,
    detector_t_dif_sum_threshold=plane_combination_detector_t_dif_sum_threshold,
    detector_t_dif_dif_threshold=plane_combination_detector_t_dif_dif_threshold,
    detector_y_sum_left=plane_combination_detector_y_sum_left,
    detector_y_sum_right=plane_combination_detector_y_sum_right,
    detector_y_dif_threshold=plane_combination_detector_y_dif_threshold,
    apply_changes=False,
)
task3_final_filter_dry_run_has_effect = int(
    (
        int(task3_final_filter_dry_run_summary.get("rows_affected", 0)) > 0
        or int(task3_final_filter_dry_run_summary.get("values_zeroed", 0)) > 0
        or int(task3_final_filter_dry_run_summary.get("failed_pair_any", 0)) > 0
    )
)
global_variables["plane_combination_filter_dry_run_has_effect"] = task3_final_filter_dry_run_has_effect
global_variables["plane_combination_filter_dry_run_input_rows"] = int(
    task3_final_filter_dry_run_summary.get("input_rows", len(working_df))
)
global_variables["plane_combination_filter_dry_run_rows_affected"] = int(
    task3_final_filter_dry_run_summary.get("rows_affected", 0)
)
global_variables["plane_combination_filter_dry_run_flagged_rows"] = int(
    task3_final_filter_dry_run_summary.get("flagged_rows", 0)
)
global_variables["plane_combination_filter_dry_run_values_zeroed"] = int(
    task3_final_filter_dry_run_summary.get("values_zeroed", 0)
)
global_variables["plane_combination_filter_dry_run_failed_pair_any"] = int(
    task3_final_filter_dry_run_summary.get("failed_pair_any", 0)
)
print(
    "[TASK3_FINAL_FILTER_DRY_RUN] "
    f"has_effect={'yes' if task3_final_filter_dry_run_has_effect else 'no'} "
    f"input_rows={global_variables['plane_combination_filter_dry_run_input_rows']} "
    f"flagged_rows={global_variables['plane_combination_filter_dry_run_flagged_rows']} "
    f"rows_affected={global_variables['plane_combination_filter_dry_run_rows_affected']} "
    f"values_zeroed={global_variables['plane_combination_filter_dry_run_values_zeroed']} "
    f"failed_pair_any={global_variables['plane_combination_filter_dry_run_failed_pair_any']}",
    force=True,
)

task3_plane_activation_filtered = store_task3_plane_activation_snapshot(
    activation_meta=activation_metadata,
    scalar_meta=global_variables,
    df=working_df,
    snapshot_label="filtered",
    tt_series=pd.to_numeric(working_df["tt_task3_list"], errors="coerce"),
    streamer_high_charge_factor_value=streamer_high_charge_factor,
    streamer_threshold_override=streamer_charge_sum_threshold,
)

task3_q_sum_final_cols = [
    f"p{i_plane}_qsum" for i_plane in range(1, 5) if f"p{i_plane}_qsum" in working_df.columns
]
task3_streamer_threshold, task3_streamer_threshold_source = select_task3_streamer_threshold(
    working_df,
    task3_q_sum_final_cols,
    streamer_charge_sum_threshold,
)
task3_topology_digits_by_plane: dict[int, np.ndarray] = {
    plane: np.zeros(len(working_df), dtype=np.int8) for plane in range(1, 5)
}
task3_topology_tt_streamer_as_avalanche = pd.Series(0, index=working_df.index, dtype="Int64")
task3_topology_tt_streamer_as_invalid = pd.Series(0, index=working_df.index, dtype="Int64")
task3_topology_tt_streamer_as_invalid_no_transference = pd.Series(0, index=working_df.index, dtype="Int64")
if task3_streamer_threshold is not None:
    (
        task3_topology_code_series,
        task3_topology_digits_by_plane,
    ) = compute_task3_charge_topology_codes(
        working_df,
        task3_streamer_threshold,
    )
    task3_topology_tt_streamer_as_avalanche = compute_task3_tt_from_topology_codes(
        task3_topology_digits_by_plane,
        streamers_count_as_active=True,
        index=working_df.index,
    )
    task3_topology_tt_streamer_as_invalid = compute_task3_tt_from_topology_codes(
        task3_topology_digits_by_plane,
        streamers_count_as_active=False,
        index=working_df.index,
    )
    task3_topology_tt_streamer_as_invalid_no_transference = compute_task3_tt_from_topology_codes(
        task3_topology_digits_by_plane,
        streamers_count_as_active=False,
        exclude_streamer_events=True,
        index=working_df.index,
    )
    working_df.loc[:, "topology_task2_strip"] = task3_topology_code_series
else:
    working_df.loc[:, "topology_task2_strip"] = "0000"

# FINAL plot block moved out of the runtime flow: all_events_charge_threshold_population, charge_asymmetry_vs_threshold, charge_by_strip_multiplicity_adj, charge_by_strip_multiplicity_dis, efficiency_anatomy_by_charge_band, fourplane_weakest_charge, fourplane_weakest_plane_identity, full_topology_class_fraction, full_topology_exact_retention, full_topology_threshold_retention, interplane_timing_correlation, multiplicity_charge_landscape, plane_charge_fraction_vs_total_charge_threshold_scan, source_tt_task3_list_charge_threshold_population, streamer_charge_histograms, streamer_contagion_matrix, streamer_efficiency_comparison, streamer_multiplicity, streamer_prevalence_by_plane, tsum_coincidence_window_histograms, tsum_coincidence_window_vs_threshold, tt_task3_list_empirical_efficiency_vs_threshold, tt_task3_list_minimum_charge_distributions, tt_task3_list_qsum_pairgrid, tt_task3_list_retention_curves, tt_task3_list_transition_matrices
pass

list_strip_patterns = build_task3_full_strip_pattern_series(working_df)
store_pattern_rates(pattern_metadata, list_strip_patterns, "list_strip_pattern", working_df)

if task3_plot_enabled("strip_activation_matrix_before_after"):
    fig_idx = plot_task3_plane_activation_before_after(
        task3_plane_activation_initial,
        task3_plane_activation_filtered,
        fig_idx,
    )

# Final task-rate plot from the same dataframe population saved by Task 3.
# FINAL plot block moved out of the runtime flow: acquisition_rate_vs_time_by_task_tt_with_histograms
pass

# Runtime figures are PNG-only; FINAL reporting is standalone.
_prof["s_pdf_finalize_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()
_finalize_stage_t0 = _t_sec

# Final number of events
final_number_of_events = len(working_df)
print(f"Final number of events in the dataframe: {final_number_of_events}")

print(
    f"Writing list parquet: rows={len(working_df)} cols={len(working_df.columns)} -> {OUT_PATH}"
)
if VERBOSE:
    print("Columns before saving calibrated->list parquet:")
    for col in working_df.columns:
        print(f" - {col}")

# Data purity
data_purity = final_number_of_events / original_number_of_events * 100

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
filter_events_per_second_meta = build_events_per_second_metadata(working_df)
try:
    filter_rate_denominator_seconds = int(
        filter_events_per_second_meta.get("events_per_second_total_seconds", 0) or 0
    )
except (TypeError, ValueError):
    filter_rate_denominator_seconds = 0
if filter_rate_denominator_seconds < 0:
    filter_rate_denominator_seconds = 0

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
    preferred_fieldnames=(
        "filename_base",
        "execution_timestamp",
        "param_hash",
        *FILTER_METRIC_NAMES,
    ),
    drop_field_predicate=lambda column_name: (
        column_name not in FILTER_METADATA_ALLOWED_COLUMNS
        or column_name in FILTER6_NONZERO_COUNTER_NAMES
        or column_name in FILTER6_NONZERO_RATE_NAMES
    ),
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
    drop_field_predicate=lambda column_name: (
        _task3_drop_legacy_deep_filter_field(column_name)
    ),
    replace_existing_basename=True,
)
print(f"Metadata (deep_fiter) CSV updated at: {metadata_deep_fiter_csv_path}")

noise_control_row = {
    "filename_base": filename_base,
    "execution_timestamp": execution_timestamp,
    "param_hash": param_hash_value,
    NOISE_CONTROL_RATE_DENOMINATOR_COLUMN: filter_rate_denominator_seconds,
}
for selected_count in TASK3_SELECTED_OFFENDER_CARDINALITY_VALUES:
    raw_count = global_variables.get(_task3_selected_offender_cardinality_metric_key(selected_count), 0)
    try:
        raw_count_value = float(raw_count)
    except (TypeError, ValueError):
        noise_control_row[_task3_selected_offender_cardinality_rate_metric_key(selected_count)] = ""
        noise_control_row[
            f"plane_combination_filter_rows_with_{selected_count}_selected_offenders_pct"
        ] = ""
        continue
    rate_value = raw_count_value / filter_rate_denominator_seconds if filter_rate_denominator_seconds > 0 else 0.0
    noise_control_row[_task3_selected_offender_cardinality_rate_metric_key(selected_count)] = round(
        rate_value,
        6,
    )
    input_rows_value = float(global_variables.get("plane_combination_filter_input_rows", 0) or 0)
    pct_value = 100.0 * raw_count_value / input_rows_value if input_rows_value > 0 else 0.0
    noise_control_row[
        f"plane_combination_filter_rows_with_{selected_count}_selected_offenders_pct"
    ] = round(pct_value, 4)

task3_noise_control_tt_task3_list = pd.to_numeric(
    working_df.get("tt_task3_list", pd.Series(index=working_df.index, dtype=float)),
    errors="coerce",
).fillna(0).astype(int)
task3_noise_control_selected_offenders = pd.to_numeric(
    working_df.get(
        "filter_total_problematic_offender_count",
        pd.Series(index=working_df.index, dtype=float),
    ),
    errors="coerce",
).fillna(0).astype(int)

for selected_count_threshold in task3_noise_control_efficiency_selected_offender_values:
    threshold_mask = task3_noise_control_selected_offenders <= selected_count_threshold
    threshold_tt_task3_list = task3_noise_control_tt_task3_list.loc[threshold_mask]
    four_plane_count = int((threshold_tt_task3_list == 1234).sum())
    for plane, missing_trigger in TASK3_THREE_TO_FOUR_MISSING_TRIGGER_BY_PLANE.items():
        metric_key = _task3_noise_control_efficiency_metric_key(
            plane,
            selected_count_threshold,
        )
        if four_plane_count <= 0:
            noise_control_row[metric_key] = ""
            continue
        missing_plane_count = int((threshold_tt_task3_list == missing_trigger).sum())
        noise_control_row[metric_key] = round(
            1.0 - (float(missing_plane_count) / float(four_plane_count)),
            6,
        )

metadata_noise_control_csv_path = save_metadata(
    csv_path_noise_control,
    noise_control_row,
    preferred_fieldnames=(
        "filename_base",
        "execution_timestamp",
        "param_hash",
        NOISE_CONTROL_RATE_DENOMINATOR_COLUMN,
        *TASK3_NOISE_CONTROL_METRIC_NAMES,
        *TASK3_NOISE_CONTROL_PERCENT_METRIC_NAMES,
        *_task3_noise_control_efficiency_metric_names(
            task3_noise_control_efficiency_selected_offender_values
        ),
    ),
)
print(f"Metadata (noise_control) CSV updated at: {metadata_noise_control_csv_path}")

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

activation_metadata["filename_base"] = filename_base
activation_metadata["execution_timestamp"] = execution_timestamp
activation_metadata["param_hash"] = param_hash_value
metadata_activation_csv_path = save_metadata(csv_path_activation, activation_metadata)
print(f"Metadata (activation) CSV updated at: {metadata_activation_csv_path}")

pattern_metadata["filename_base"] = filename_base
pattern_metadata["execution_timestamp"] = execution_timestamp
pattern_metadata["param_hash"] = param_hash_value
metadata_pattern_csv_path = save_metadata(
    csv_path_pattern,
    pattern_metadata,
    preferred_fieldnames=("filename_base", "execution_timestamp", "param_hash"),
)
print(f"Metadata (pattern) CSV updated at: {metadata_pattern_csv_path}")

# -------------------------------------------------------------------------------
# Specific metadata ------------------------------------------------------------
# -------------------------------------------------------------------------------

global_variables.update(build_events_per_second_metadata(working_df))
global_variables["charge_topology_code_column"] = "topology_task2_strip"
global_variables["charge_topology_streamer_threshold_source"] = task3_streamer_threshold_source
store_task3_charge_topology_metadata(
    global_variables,
    working_df,
    working_df["topology_task2_strip"].astype(str),
    task3_topology_digits_by_plane,
    pd.to_numeric(working_df["tt_task3_list"], errors="coerce").astype("Int64"),
    task3_topology_tt_streamer_as_avalanche,
    task3_topology_tt_streamer_as_invalid,
    task3_topology_tt_streamer_as_invalid_no_transference,
    task3_streamer_threshold,
)
ensure_global_count_keys(("tt_task2_cal", "tt_task3_list", "transferred_task3_cal_to_list"))
add_normalized_count_metadata(
    global_variables,
    global_variables.get("events_per_second_total_seconds", 0),
)
set_global_rate_from_tt_rates(
    global_variables,
    preferred_prefixes=("tt_task3_list", "tt_task2_cal"),
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
trigger_type_prefixes = ("tt_task2_cal", "tt_task3_list", "transferred_task3_cal_to_list")
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
    stage_tt_columns=("tt_task2_cal", "tt_task3_list"),
    denominator_seconds=trigger_type_variables["count_rate_denominator_seconds"],
)
metadata_trigger_type_csv_path = save_metadata(
    csv_path_trigger_type,
    trigger_type_variables,
    drop_field_predicate=lambda column_name: not is_trigger_type_file_column(
        column_name,
        trigger_type_prefixes,
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
        or column_name.startswith("cal_strip_pattern_")
        or column_name.startswith("list_strip_pattern_")
        or is_trigger_type_metadata_column(column_name, trigger_type_prefixes)
        or column_name in FILTER6_NONZERO_COUNTER_NAMES
    ),
)
print(f"Metadata (specific) CSV updated at: {metadata_specific_csv_path}")
_prof["s_metadata_write_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()

# Add charge-calibrated strip and plane sums only after every Task-3 filter and
# metadata calculation has finished. These columns cannot influence selection.
tot_charge_calibration = TotChargeCalibration.from_csv(
    default_tot_charge_calibration_path(get_repo_root())
)
task3_fc_strip_columns, task3_fc_plane_columns, task3_fc_source_columns = (
    add_task3_charge_fc_columns(working_df, tot_charge_calibration)
)
missing_task3_fc_sources = [
    f"p{plane}_s{strip}_qsum_cal/qsum"
    for plane in range(1, 5)
    for strip in range(1, 5)
    if not any(
        source in working_df.columns
        for source in (f"p{plane}_s{strip}_qsum_cal", f"p{plane}_s{strip}_qsum")
    )
]
if missing_task3_fc_sources:
    print(
        "WARNING: Task-3 ToT-to-fC columns unavailable for missing strip widths: "
        + ", ".join(missing_task3_fc_sources)
    )
print(
    "Task-3 ToT-to-fC outputs added after filters: "
    f"strip_columns={len(task3_fc_strip_columns)} "
    f"plane_sum_columns={len(task3_fc_plane_columns)} "
    f"source_columns={len(set(task3_fc_source_columns))}"
)

if task3_any_plot_enabled(
    "tot_charge_calibration_order_comparison",
    "tot_charge_calibration_order_scatter",
):
    task3_spectra = calibration_order_arrays(working_df, tot_charge_calibration)
    data_dates = pd.to_datetime(working_df.get("datetime"), errors="coerce").dropna()
    if data_dates.empty:
        try:
            data_date = datetime.strptime(basename_no_ext[-11:], "%y%j%H%M%S")
        except ValueError:
            data_date = datetime.now()
    else:
        data_date = data_dates.min().to_pydatetime()
    task3_plot_directory = os.path.join(
        base_directories["base_plots_directory"],
        "DEBUG_PLOTS",
        f"{data_date:%Y_%m_%d}_FIGURES_EXEC_ON_{date_execution}",
    )
    if task3_plot_enabled("tot_charge_calibration_order_comparison"):
        task3_figure = plot_calibration_order_comparison(
            task3_spectra,
            station=int(station),
            file_count=len(joined_input_records),
        )
        task3_plot_path = os.path.join(
            task3_plot_directory,
            f"{debug_fig_idx:02d}_task3_tot_charge_calibration_order_{basename_no_ext}.png",
        )
        save_plot_figure(task3_plot_path, fig=task3_figure, format="png", dpi=150)
        print(f"Task-3 ToT-to-fC order comparison saved: {task3_plot_path}")
        debug_fig_idx += 1
        plt.close(task3_figure)

    if task3_plot_enabled("tot_charge_calibration_order_scatter"):
        scatter_figure = plot_calibration_order_scatter(
            task3_spectra,
            station=int(station),
            file_count=len(joined_input_records),
        )
        scatter_path = os.path.join(
            task3_plot_directory,
            f"{debug_fig_idx:02d}_task3_tot_charge_calibration_order_scatter_{basename_no_ext}.png",
        )
        save_plot_figure(scatter_path, fig=scatter_figure, format="png", dpi=150)
        print(f"Task-3 ToT-to-fC order scatter saved: {scatter_path}")
        debug_fig_idx += 1
        plt.close(scatter_figure)

# Ensure no figure handles remain open before persistence/final move.
plt.close("all")

if joined_analysis_active and joined_source_file_column in working_df.columns:
    for joined_record in joined_input_records:
        joined_file_name = joined_record["file_name"]
        joined_basename = joined_record["basename_no_ext"]
        joined_out_path = os.path.join(output_directory, f"listed_{joined_basename}.parquet")
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
        print(f"Listed joined-analysis dataframe saved to: {joined_out_path} rows={len(joined_output_df)}")
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
    print(f"Listed dataframe saved to: {OUT_PATH}")
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
        csv_path_pattern,
        csv_path_rate_histogram,
        csv_path_activation,
        csv_path_trigger_type,
        csv_path_filter,
        csv_path_deep_fiter,
        csv_path_noise_control,
        csv_path_status,
        csv_path_profiling,
    ],
    primary_filename_base=filename_base,
    joined_input_records=joined_input_records,
    log_fn=print,
)
