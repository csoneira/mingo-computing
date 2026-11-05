#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/STEP_1/TASK_1/script_1_raw_to_clean.py
Purpose: !/usr/bin/env python3.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/STEP_1/TASK_1/script_1_raw_to_clean.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

#%%

from __future__ import annotations

"""
Stage 1 Task 1 (RAW-->CLEAN) driver.

The script pulls the next available Task 0 raw parquet, applies the full raw
cleaning chain (baseline removal, channel checks, derived quantities, and
pre-selection cuts), and persists the cleaned dataframe for downstream tasks.
Along the way it maintains the station staging directories, generates QA plots,
tracks execution metadata, and emits run-level summaries consumed by the rest
of the Stage 1 event workflow.
"""
# Standard Library
from array import array
import builtins
from datetime import datetime
import gc
import os
from pathlib import Path
import random
import re
import shutil
import sys
import time
import warnings
from typing import Iterable, Mapping

# Scientific Computing
import numpy as np
import pandas as pd
from scipy.constants import c
from scipy.stats import norm

# Plotting
import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import seaborn as sns

# Image Processing

# Resolve repo root for local imports
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

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.debug_plots import plot_debug_histograms
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.execution_logger import set_station, start_timer
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.file_selection import (
    file_name_in_any_date_range,
    load_date_ranges_from_config,
    newest_order_key,
    select_latest_candidate,
    sync_unprocessed_with_date_range,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.input_file_config import (
    select_closest_valid_z_configuration,
    select_input_file_configuration,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.path_config import (
    get_repo_root,
    resolve_home_path_from_config,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.plot_utils import ensure_plot_state
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.selection_config import load_selection_for_paths, station_is_selected
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.step1_rate_plots import create_rate_vs_time_by_task_tt_with_histograms
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.status_csv import (
    delete_status_row,
    initialize_status_row,
    rename_status_row,
    update_status_progress,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.reprocessing_utils import (
    QA_REPROCESSING_METADATA_KEYS,
    apply_qa_reprocessing_context,
    canonical_processing_basename,
    filter_filenames_other_than_qa_retry_basenames,
    filter_filenames_by_qa_retry_basenames,
    get_reprocessing_value,
    load_active_qa_retry_basenames,
    load_qa_reprocessing_context_for_file,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.simulated_data_utils import SIM_PARAMS_DEFAULT, resolve_simulated_z_positions
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.step1_activation import (
    compute_conditional_matrices_by_tt,
    store_activation_matrices_by_tt_metadata,
    store_activation_matrix_metadata,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.step1_shared import (
    add_normalized_count_metadata,
    add_topology_task1_channel,
    add_trigger_type_total_offender_threshold_metadata,
    build_step1_raw_input_dataframe,
    build_events_per_second_metadata,
    build_step1_cli_parser,
    build_step1_filtered_print,
    canonicalize_step1_columns,
    collect_columns,
    coerce_nonnegative_float_config,
    coerce_positive_int_config,
    extract_rate_histogram_metadata,
    extract_trigger_type_metadata,
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
    select_exact_minimum_vertex_cover,
    set_global_rate_from_tt_rates,
    resolve_step1_plot_options,
    step1_logging_enabled,
    step1_task_plot_enabled,
    validate_step1_input_file_args,
    y_pos,
)
from analysis_functions import (
    _as_bool,
    _iter_priority_vectors,
    _normalize_z_vector,
    _z_vector_matches_priority,
)
from plotting_functions import (
    _task1_capped_plot_range,
    _task1_population_color,
)

task_number = 1

# I want to chrono the execution time of the script
start_execution_time_counting = datetime.now()
_prof_t0 = time.perf_counter()
_prof = {}

STATION_CHOICES = ("0", "1", "2", "3", "4")
TASK1_PLOT_ALIASES: tuple[str, ...] = (
    "debug_suite",
    "usual_suite",
    "essential_suite",
    "acquisition_rate_vs_time_by_task_tt_with_histograms",
    "event_total_charge_raw",
    "tt_task0_raw_overview",
    "channel_histograms_raw",
    "tq_scatter_raw",
    "channel_histograms_filtered",
    "tq_scatter_filtered",
    "tsum_spread_diagnostics",
    "channel_contamination_matrix_32",
    "channel_contagion_by_tt",
    "channel_contamination_matrix_32_raw",
    "channel_contagion_by_tt_task0_raw",
    "tsum_spread_histograms_filtered_og",
    "tq_scatter_raw_by_tt",
    "tq_scatter_filtered_by_tt",
    "channel_tq_matrix_by_planepair",
    "channel_combination_filter_by_tt",
)
task1_plot_status_by_alias: dict[str, str] = {}

def apply_task1_plot_catalog_modes() -> None:
    global create_plots, create_essential_plots, create_debug_plots, save_plots, create_pdf
    if not task1_plot_status_by_alias:
        return
    create_plots = create_plots and task1_plot_enabled("usual_suite")
    create_essential_plots = create_essential_plots and task1_plot_enabled("essential_suite")
    create_debug_plots = create_debug_plots and task1_plot_enabled("debug_suite")
    save_plots = bool(create_plots or create_essential_plots or create_debug_plots)
    create_pdf = False  # Runtime plots are strictly PNG-only; FINAL PDFs are standalone.

def _coerce_config_bool(value: object, default: bool = False) -> bool:
    """Interpret common config boolean encodings without changing existing defaults."""
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

def _coerce_config_value(value: object, cast_fn, default):
    try:
        return cast_fn(value)
    except (TypeError, ValueError):
        return default

def _task1_load_channel_combination_relation_limits(
    config_dict: dict,
    *,
    base_q_sum_left: float,
    base_q_sum_right: float,
    base_q_dif_threshold: float,
    base_t_sum_left: float,
    base_t_sum_right: float,
    base_t_dif_threshold: float,
) -> dict[str, dict[str, float]]:
    base_limits = {
        "q_sum_left": float(base_q_sum_left),
        "q_sum_right": float(base_q_sum_right),
        "q_dif_threshold": float(base_q_dif_threshold),
        "t_sum_left": float(base_t_sum_left),
        "t_sum_right": float(base_t_sum_right),
        "t_dif_threshold": float(base_t_dif_threshold),
    }
    relation_limits: dict[str, dict[str, float]] = {}
    relation_types = ("self", "same_strip", "same_plane", "any")
    bound_suffixes = (
        "q_sum_left",
        "q_sum_right",
        "q_dif_threshold",
        "t_sum_left",
        "t_sum_right",
        "t_dif_threshold",
    )
    for relation_type in relation_types:
        relation_limits[relation_type] = {
            suffix: float(
                config_dict.get(
                    f"channel_combination_{relation_type}_{suffix}",
                    base_limits[suffix],
                )
            )
            for suffix in bound_suffixes
        }
    return relation_limits


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


def _task1_output_basename_from_input_stem(stem: str) -> str:
    return stem[4:] if stem.startswith("raw_") else stem


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


def _debug_plot_filter_group(
    df: pd.DataFrame,
    columns: Iterable[str],
    thresholds: Iterable[float] | float | None,
    label: str,
    *,
    tag: str = "tunable",
    max_cols_per_fig: int = 16,
) -> None:
    """Emit debug histograms for a filter group with threshold lines."""
    global debug_fig_idx
    if not create_debug_plots:
        return

    cols = [col for col in columns if col in df.columns]
    if not cols:
        return

    if thresholds is None:
        threshold_values: list[float] = []
    elif isinstance(thresholds, (list, tuple, np.ndarray)):
        threshold_values = [float(v) for v in thresholds if v is not None]
    else:
        threshold_values = [float(thresholds)]

    debug_thresholds = {col: threshold_values for col in cols}
    debug_fig_idx = plot_debug_histograms(
        df,
        cols,
        debug_thresholds,
        title=f"Task 1 pre-filter: {label} [{tag}] (station {station})",
        out_dir=debug_plot_directory,
        fig_idx=debug_fig_idx,
        max_cols_per_fig=max_cols_per_fig,
    )


def get_tt_color(tt_value: object) -> tuple[float, float, float, float]:
    """Return a stable color for a trigger-type label across all Task 1 plots."""
    return TT_COLOR_MAP.get(normalize_tt_label(tt_value), TT_COLOR_DEFAULT)

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


def _compute_channel_contagion_inputs(
    df: pd.DataFrame,
) -> tuple[list[str], np.ndarray] | None:
    """Return channel labels and active-mask matrix (rows=events, cols=channels)."""
    ch_labels: list[str] = []
    ch_cols: list[str] = []
    for _p, _s, _sd in TASK1_CHANNEL_PATTERN_ORDER:
        col = f"Q{_p}_{_sd}_{_s}"
        if col in df.columns:
            ch_labels.append(f"P{_p}S{_s}{_sd}")
            ch_cols.append(col)
    if not ch_cols:
        return None
    vals = df.loc[:, ch_cols].fillna(0).to_numpy(dtype=np.float32, copy=False)
    active = vals != 0
    return ch_labels, active

def _compute_channel_conditional_matrix_from_active(active: np.ndarray) -> np.ndarray:
    """Compute P(ch_j active | ch_i active) from boolean activity matrix."""
    co = active.T.astype(np.int64) @ active.astype(np.int64)
    diag = np.diag(co).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        cond = np.divide(
            co.astype(float),
            diag[:, None],
            out=np.full_like(co, np.nan, dtype=float),
            where=diag[:, None] > 0,
        )
    return cond

def _compute_channel_conditional_matrix(df: pd.DataFrame) -> tuple[list[str], np.ndarray] | None:
    """Compute full-table conditional channel activation matrix."""
    inputs = _compute_channel_contagion_inputs(df)
    if inputs is None:
        return None
    ch_labels, active = inputs
    return ch_labels, _compute_channel_conditional_matrix_from_active(active)

def _compute_channel_conditional_matrix_for_tt(
    df: pd.DataFrame,
    tt_column: str,
    tt_value: int,
) -> tuple[list[str], np.ndarray] | None:
    """Compute conditional channel activation matrix for a specific TT value."""
    if tt_column not in df.columns:
        return None
    inputs = _compute_channel_contagion_inputs(df)
    if inputs is None:
        return None
    ch_labels, active = inputs
    tt_s = pd.to_numeric(df[tt_column], errors="coerce").fillna(0).astype(int)
    mask_tt = (tt_s == int(tt_value)).to_numpy(dtype=bool)
    if not np.any(mask_tt):
        return None
    return ch_labels, _compute_channel_conditional_matrix_from_active(active[mask_tt])

def _summarize_channel_conditional_matrix(cond: np.ndarray) -> tuple[float, float, float]:
    """Return mean/max off-diagonal and mean off-diagonal inter-plane values."""
    n_ch = int(cond.shape[0])
    if n_ch <= 1:
        return (float("nan"), float("nan"), float("nan"))

    idx = np.arange(n_ch)
    offdiag_mask = idx[:, None] != idx[None, :]
    offdiag_vals = cond[offdiag_mask]
    offdiag_finite = offdiag_vals[np.isfinite(offdiag_vals)]
    mean_offdiag = float(np.mean(offdiag_finite)) if offdiag_finite.size else float("nan")
    max_offdiag = float(np.max(offdiag_finite)) if offdiag_finite.size else float("nan")

    plane_ids = idx // 8
    interplane_mask = offdiag_mask & (plane_ids[:, None] != plane_ids[None, :])
    inter_vals = cond[interplane_mask]
    inter_finite = inter_vals[np.isfinite(inter_vals)]
    mean_interplane = float(np.mean(inter_finite)) if inter_finite.size else float("nan")
    return (mean_offdiag, max_offdiag, mean_interplane)

def _store_channel_contagion_metrics_variant(
    variant: str,
    matrix_data: tuple[list[str], np.ndarray] | None,
) -> None:
    """Store global/by-TT channel contagion summary metrics for a variant."""
    key_mean = f"mean_off_diagonal_{variant}"
    key_max = f"max_off_diagonal_{variant}"
    key_inter = f"mean_off_diagonal_interplane_{variant}"
    if matrix_data is None:
        channel_contagion_metrics[key_mean] = float("nan")
        channel_contagion_metrics[key_max] = float("nan")
        channel_contagion_metrics[key_inter] = float("nan")
        return
    _, cond = matrix_data
    mean_offdiag, max_offdiag, mean_interplane = _summarize_channel_conditional_matrix(cond)
    channel_contagion_metrics[key_mean] = mean_offdiag
    channel_contagion_metrics[key_max] = max_offdiag
    channel_contagion_metrics[key_inter] = mean_interplane

def _plot_channel_contamination_global(
    df: pd.DataFrame,
    stage_label: str,
    fig_idx_val: int,
    base_dir: str,
    save: bool,
    show: bool,
    plist: list[str],
) -> int:
    """Plot a single 32×32 channel contamination heatmap."""
    matrix_data = _compute_channel_conditional_matrix(df)
    if matrix_data is None:
        return fig_idx_val
    ch_labels, cond = matrix_data
    fig, ax = plt.subplots(figsize=(13, 11))
    sns.heatmap(cond, vmin=0.0, vmax=1.0, cmap="viridis",
                xticklabels=ch_labels, yticklabels=ch_labels, ax=ax,
                cbar_kws={"label": "P(ch j active | ch i active)"})
    ax.set_title(f"Task 1 {stage_label} — 32-channel contamination matrix")
    ax.set_xlabel("Channel j")
    ax.set_ylabel("Channel i")
    ax.tick_params(axis="x", labelrotation=90, labelsize=7)
    ax.tick_params(axis="y", labelrotation=0, labelsize=7)
    fig.tight_layout()
    if save:
        fname = f"{fig_idx_val}_{stage_label.lower().replace(' ', '_')}_channel_contamination_matrix_32.png"
        fig_idx_val += 1
        spath = os.path.join(base_dir, fname)
        plist.append(spath)
        save_plot_figure(spath, fig=fig, format="png", dpi=150)
    if show:
        plt.show()
    plt.close(fig)
    return fig_idx_val

def _plot_channel_contagion_by_tt(
    df: pd.DataFrame,
    tt_column: str,
    stage_label: str,
    fig_idx_val: int,
    base_dir: str,
    save: bool,
    show: bool,
    plist: list[str],
    min_events: int = 30,
    max_tt_panels: int = 6,
) -> int:
    """Plot 32-channel contagion matrices split by TT."""
    required_tts: tuple[int, int] = (124, 134)
    inputs = _compute_channel_contagion_inputs(df)
    if inputs is None or tt_column not in df.columns:
        return fig_idx_val
    ch_labels_global, active = inputs
    n_ch = len(ch_labels_global)
    ch_labels = [lbl.replace("S", "") for lbl in ch_labels_global]
    tt_s = pd.to_numeric(df[tt_column], errors="coerce").fillna(0).astype(int)
    tt_cts = tt_s.value_counts()
    required_present = [tt for tt in required_tts if int(tt_cts.get(tt, 0)) > 0]
    optional_pool = [
        tt for tt, cnt in tt_cts.items()
        if tt >= 10 and cnt >= min_events and tt not in required_tts
    ]
    # Keep required TTs visible even when panel count is capped.
    sel_tts = required_present + optional_pool
    sel_tts = sel_tts[:max(max_tt_panels, len(required_present))]
    if not sel_tts:
        return fig_idx_val
    ncols_tt = len(sel_tts)
    fig_w = max(7, 6.0 * ncols_tt)
    fig, axes = plt.subplots(1, ncols_tt, figsize=(fig_w, 7.0 + 0.15 * n_ch), squeeze=False)
    _im = None
    for ci, tv in enumerate(sel_tts):
        ax = axes[0, ci]
        mtt = (tt_s == tv).to_numpy(dtype=bool)
        ntt = int(np.sum(mtt))
        cond = _compute_channel_conditional_matrix_from_active(active[mtt])
        _im = ax.imshow(cond, cmap="viridis", vmin=0, aspect="equal")
        ax.set_xticks(range(n_ch))
        ax.set_xticklabels(ch_labels, fontsize=4, rotation=90)
        ax.set_yticks(range(n_ch))
        ax.set_yticklabels(ch_labels, fontsize=4)
        for bnd in range(8, n_ch, 8):
            ax.axhline(bnd - 0.5, color="grey", linewidth=0.7, alpha=0.6)
            ax.axvline(bnd - 0.5, color="grey", linewidth=0.7, alpha=0.6)
        ax.set_title(f"TT {tv} (N={ntt})", fontsize=10)
    if _im is not None:
        fig.colorbar(_im, ax=axes[0, -1], label="P(ch j | ch i)", shrink=0.75, pad=0.02)
    fig.suptitle(
        f"Task 1 {stage_label} — channel contagion by TT\n"
        "P(channel j active | channel i active)",
        fontsize=13,
    )
    fig.tight_layout(rect=[0, 0, 0.97, 0.93])
    if save:
        fname = f"{fig_idx_val}_{stage_label.lower().replace(' ', '_')}_channel_contagion_by_tt.png"
        fig_idx_val += 1
        spath = os.path.join(base_dir, fname)
        plist.append(spath)
        save_plot_figure(spath, fig=fig, format="png", dpi=150)
    if show:
        plt.show()
    plt.close(fig)
    return fig_idx_val


def record_activity_metric(name: str, affected: float, total: float, label: str = "affected") -> None:
    """Record a generic percentage metric."""
    pct = 0.0 if total == 0 else 100.0 * float(affected) / float(total)
    filter_metrics[name] = round(pct, 4)
    _log_filter_metrics_message(
        f"[filter-metrics] {name}: {label} {affected} of {total} ({pct:.2f}%)"
    )

def record_filter_metric(name: str, removed: float, total: float) -> None:
    """Record percentage removed for a filter."""
    record_activity_metric(name, removed, total, label="removed")

def collect_task1_channel_qt_map(df_input: pd.DataFrame) -> dict[tuple[int, str, int], dict[str, str]]:
    """Return the per-channel Q/T column mapping for Task 1."""
    channel_map: dict[tuple[int, str, int], dict[str, str]] = {}
    for plane in range(1, 5):
        for side in ("F", "B"):
            endpoint = "ef" if side == "F" else "eb"
            for strip in range(1, 5):
                q_col = f"p{plane}_s{strip}_{endpoint}_q"
                t_col = f"p{plane}_s{strip}_{endpoint}_t"
                if q_col in df_input.columns and t_col in df_input.columns:
                    channel_map[(plane, side, strip)] = {"Q": q_col, "T": t_col}
    return channel_map


def _task1_channel_order_key(channel_key: tuple[int, str, int]) -> tuple[int, int, int]:
    plane, side, strip = channel_key
    side_rank = 0 if side == "F" else 1
    return plane, side_rank, strip

def _task1_channel_offender_metric_key(channel_key: tuple[int, str, int]) -> str:
    plane, side, strip = channel_key
    return f"plane_combination_filter_offender_count_P{plane}{side}{strip}"

def _task1_channel_noise_limit_metric_key(channel_key: tuple[int, str, int]) -> str:
    plane, side, strip = channel_key
    return f"plane_combination_noise_limit_P{plane}{side}{strip}"

def _task1_selected_offender_cardinality_metric_key(selected_count: int) -> str:
    return f"plane_combination_filter_rows_with_{selected_count}_selected_offenders"

def _task1_selected_offender_cardinality_rate_metric_key(selected_count: int) -> str:
    return f"{_task1_selected_offender_cardinality_metric_key(selected_count)}_rate_hz"

def _task1_selected_offender_cardinality_percent_metric_key(selected_count: int) -> str:
    return f"{_task1_selected_offender_cardinality_metric_key(selected_count)}_pct"

def _task1_noise_control_efficiency_metric_key(plane: int, selected_count_threshold: int) -> str:
    return (
        f"plane_combination_filter_eff_p{plane}_selected_offenders_le_"
        f"{selected_count_threshold}"
    )

def _task1_noise_control_efficiency_metric_names(
    selected_count_thresholds: Iterable[int],
) -> tuple[str, ...]:
    return tuple(
        _task1_noise_control_efficiency_metric_key(plane, selected_count_threshold)
        for selected_count_threshold in selected_count_thresholds
        for plane in sorted(TASK1_THREE_TO_FOUR_MISSING_TRIGGER_BY_PLANE)
    )


def _task1_channel_label(channel_key: tuple[int, str, int]) -> str:
    plane, side, strip = channel_key
    return f"P{plane}S{strip}{side}"

def _task1_channel_relation_type(
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

def _iter_task1_channel_relation_pairs(
    channel_map: dict[tuple[int, str, int], dict[str, str]],
) -> Iterable[tuple[tuple[int, str, int], tuple[int, str, int], str]]:
    ordered_channels = sorted(channel_map, key=_task1_channel_order_key)
    for idx, channel_a in enumerate(ordered_channels):
        yield channel_a, channel_a, "self"
        for channel_b in ordered_channels[idx + 1 :]:
            yield channel_a, channel_b, _task1_channel_relation_type(channel_a, channel_b)

def _empty_task1_removed_channel_values_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "row_index",
            "channel",
            "plane",
            "side",
            "strip",
            "Q",
            "T",
            "pass_label",
            "Q_zeroed",
            "T_zeroed",
        ]
    )

def _task1_build_removed_channel_values_frame(
    df_input: pd.DataFrame,
    channel_key: tuple[int, str, int],
    q_values: pd.Series,
    t_values: pd.Series,
    fail_mask: np.ndarray | pd.Series,
    pass_label: str,
) -> pd.DataFrame:
    aligned_mask = pd.Series(fail_mask, index=df_input.index, dtype=bool).reindex(df_input.index, fill_value=False)
    if not aligned_mask.any():
        return _empty_task1_removed_channel_values_frame()

    plane, side, strip = channel_key
    rows = pd.DataFrame(
        {
            "row_index": df_input.index[aligned_mask].to_numpy(),
            "channel": _task1_channel_label(channel_key),
            "plane": plane,
            "side": side,
            "strip": strip,
            "Q": pd.to_numeric(q_values.loc[aligned_mask], errors="coerce").to_numpy(dtype=float),
            "T": pd.to_numeric(t_values.loc[aligned_mask], errors="coerce").to_numpy(dtype=float),
            "pass_label": pass_label,
        }
    )
    return rows.reset_index(drop=True)

def collect_task1_zeroed_channel_values(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    *,
    pass_label: str,
) -> pd.DataFrame:
    if reference_df.empty or current_df.empty:
        return _empty_task1_removed_channel_values_frame()

    channel_map = collect_task1_channel_qt_map(reference_df)
    if not channel_map:
        return _empty_task1_removed_channel_values_frame()

    aligned_reference = reference_df.reindex(current_df.index, copy=False)
    current_index = current_df.index.to_numpy(copy=False)
    payload_frames: list[pd.DataFrame] = []
    for channel_key, cols in channel_map.items():
        if cols["Q"] not in current_df.columns or cols["T"] not in current_df.columns:
            continue
        ref_q = pd.to_numeric(aligned_reference[cols["Q"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        ref_t = pd.to_numeric(aligned_reference[cols["T"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        cur_q = pd.to_numeric(current_df[cols["Q"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        cur_t = pd.to_numeric(current_df[cols["T"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        q_zeroed = (ref_q != 0) & (cur_q == 0)
        t_zeroed = (ref_t != 0) & (cur_t == 0)
        zeroed_mask = q_zeroed | t_zeroed
        if not np.any(zeroed_mask):
            continue

        plane, side, strip = channel_key
        payload_frames.append(
            pd.DataFrame(
                {
                    "row_index": current_index[zeroed_mask],
                    "channel": _task1_channel_label(channel_key),
                    "plane": plane,
                    "side": side,
                    "strip": strip,
                    "Q": ref_q[zeroed_mask],
                    "T": ref_t[zeroed_mask],
                    "pass_label": pass_label,
                    "Q_zeroed": q_zeroed[zeroed_mask],
                    "T_zeroed": t_zeroed[zeroed_mask],
                }
            )
        )

    if not payload_frames:
        return _empty_task1_removed_channel_values_frame()
    return pd.concat(payload_frames, ignore_index=True)

def apply_task1_channel_qt_mismatch_filter(
    df_input: pd.DataFrame,
    *,
    snapshot_originals=None,
    apply_changes: bool = True,
) -> dict[str, object]:
    task1_channel_pairs: list[tuple[str, str]] = []
    for plane in range(1, 5):
        for side in ("F", "B"):
            endpoint = "ef" if side == "F" else "eb"
            for strip in range(1, 5):
                q_col = f"p{plane}_s{strip}_{endpoint}_q"
                t_col = f"p{plane}_s{strip}_{endpoint}_t"
                if q_col in df_input.columns and t_col in df_input.columns:
                    task1_channel_pairs.append((q_col, t_col))

    row_mismatch_mask = pd.Series(False, index=df_input.index)
    q_only_row_mask = pd.Series(False, index=df_input.index)
    t_only_row_mask = pd.Series(False, index=df_input.index)
    front_row_mask = pd.Series(False, index=df_input.index)
    back_row_mask = pd.Series(False, index=df_input.index)
    channel_qt_mismatch_channels = 0
    channel_qt_values_zeroed = 0
    mismatch_mask_by_channel: dict[tuple[int, str, int], pd.Series] = {}

    if task1_channel_pairs and not df_input.empty:
        for q_col, t_col in task1_channel_pairs:
            q_values = pd.to_numeric(df_input[q_col], errors="coerce").fillna(0)
            t_values = pd.to_numeric(df_input[t_col], errors="coerce").fillna(0)
            q_only_mask = (q_values != 0) & (t_values == 0)
            t_only_mask = (q_values == 0) & (t_values != 0)
            mismatch_mask = q_only_mask | t_only_mask
            if not mismatch_mask.any():
                continue
            if snapshot_originals is not None:
                snapshot_originals(df_input, [q_col, t_col])
            match = re.match(r"^p([1-4])_s([1-4])_(ef|eb)_q$", q_col)
            if match:
                plane = int(match.group(1))
                strip = int(match.group(2))
                side = "F" if match.group(3) == "ef" else "B"
                mismatch_mask_by_channel[(plane, side, strip)] = mismatch_mask
            row_mismatch_mask |= mismatch_mask
            q_only_row_mask |= q_only_mask
            t_only_row_mask |= t_only_mask
            if "_F_" in q_col:
                front_row_mask |= mismatch_mask
            elif "_B_" in q_col:
                back_row_mask |= mismatch_mask
            channel_qt_mismatch_channels += int(mismatch_mask.sum())
            channel_qt_values_zeroed += int((q_values[mismatch_mask] != 0).sum())
            channel_qt_values_zeroed += int((t_values[mismatch_mask] != 0).sum())
            if apply_changes:
                # Legacy destructive mode only; final working_df calls use apply_changes=False.
                df_input.loc[mismatch_mask, [q_col, t_col]] = 0

    return {
        "task1_channel_pairs": task1_channel_pairs,
        "row_mismatch_mask": row_mismatch_mask,
        "q_only_row_mask": q_only_row_mask,
        "t_only_row_mask": t_only_row_mask,
        "front_row_mask": front_row_mask,
        "back_row_mask": back_row_mask,
        "rows_affected": int(row_mismatch_mask.sum()),
        "values_zeroed": int(channel_qt_values_zeroed),
        "q_only_rows": int(q_only_row_mask.sum()),
        "t_only_rows": int(t_only_row_mask.sum()),
        "front_rows": int(front_row_mask.sum()),
        "back_rows": int(back_row_mask.sum()),
        "mismatch_channels": int(channel_qt_mismatch_channels),
        "mismatch_mask_by_channel": mismatch_mask_by_channel,
    }


def _task1_parse_combo_label(
    combo_label: str,
) -> tuple[tuple[int, str, int], tuple[int, str, int]] | None:
    match = _TASK1_COMBO_LABEL_PATTERN.match(str(combo_label))
    if match is None:
        return None
    return (
        (
            int(match.group("plane_a")),
            match.group("side_a"),
            int(match.group("strip_a")),
        ),
        (
            int(match.group("plane_b")),
            match.group("side_b"),
            int(match.group("strip_b")),
        ),
    )

def apply_task1_plane_combination_filter(
    df_input: pd.DataFrame,
    *,
    relation_limits_by_type: Mapping[str, Mapping[str, float]],
    snapshot_originals=None,
    apply_changes: bool = True,
    removed_value_pass_label: str | None = None,
) -> dict[str, object]:
    """
    Apply the Task 1 channel-combination filter directly from channel Q/T values.

    The filter is evaluated in one pass over four mutually-exclusive relation classes:
    ``self`` (channel with itself), ``same_strip`` (front/back of the same strip),
    ``same_plane`` (different strips within the same plane), and ``any`` (different
    planes). Each relation class has its own Q_sum, Q_dif, T_sum, and T_dif bounds.

    Failed self-relations become mandatory offending channels. Failed non-self
    relations are solved per event with the exact minimum-cardinality channel set
    that covers all failed edges.
    """
    channel_map = collect_task1_channel_qt_map(df_input)
    if not channel_map:
        return {
            "input_rows": len(df_input),
            "tracked_channel_count": len(channel_map),
            "valid_pair_observations": 0,
            "failed_pair_any": 0,
            "failed_pair_q_sum": 0,
            "failed_pair_q_dif": 0,
            "failed_pair_t_sum": 0,
            "failed_pair_t_dif": 0,
            "rows_affected": 0,
            "values_zeroed": 0,
            "flagged_rows": 0,
            "selected_offender_channels": 0,
            "rows_with_multiple_offenders": 0,
            "max_failed_pairs_in_row": 0,
            "max_selected_offenders_in_row": 0,
            "valid_pair_observations_by_relation": {
                relation_type: 0
                for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
            },
            "failed_pair_any_by_relation": {
                relation_type: 0
                for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
            },
            "failed_pair_q_sum_low_by_relation": {
                relation_type: 0
                for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
            },
            "failed_pair_q_sum_high_by_relation": {
                relation_type: 0
                for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
            },
            "failed_pair_q_dif_by_relation": {
                relation_type: 0
                for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
            },
            "failed_pair_t_sum_low_by_relation": {
                relation_type: 0
                for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
            },
            "failed_pair_t_sum_high_by_relation": {
                relation_type: 0
                for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
            },
            "failed_pair_t_dif_by_relation": {
                relation_type: 0
                for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
            },
            "rows_failed_q_sum_low": 0,
            "rows_failed_q_sum_high": 0,
            "rows_failed_q_dif": 0,
            "rows_failed_t_sum_low": 0,
            "rows_failed_t_sum_high": 0,
            "rows_failed_t_dif": 0,
            "rows_failed_q_sum_low_by_relation": {
                relation_type: 0
                for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
            },
            "rows_failed_q_sum_high_by_relation": {
                relation_type: 0
                for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
            },
            "rows_failed_q_dif_by_relation": {
                relation_type: 0
                for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
            },
            "rows_failed_t_sum_low_by_relation": {
                relation_type: 0
                for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
            },
            "rows_failed_t_sum_high_by_relation": {
                relation_type: 0
                for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
            },
            "rows_failed_t_dif_by_relation": {
                relation_type: 0
                for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
            },
            "rows_with_relation_failures": {
                relation_type: 0
                for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
            },
            "selected_offender_cardinality_counts": {
                selected_count: 0
                for selected_count in TASK1_SELECTED_OFFENDER_CARDINALITY_VALUES
            },
            "selected_offender_counts": {
                channel_key: 0 for channel_key in TASK1_CHANNEL_KEYS
            },
            "selected_offender_count_by_row": pd.Series(0, index=df_input.index, dtype=int),
            "resolution_exact_by_row": pd.Series(True, index=df_input.index, dtype=bool),
            "removed_channel_values": _empty_task1_removed_channel_values_frame(),
        }

    n_rows = len(df_input)
    summary = {
        "input_rows": n_rows,
        "tracked_channel_count": len(channel_map),
        "valid_pair_observations": 0,
        "failed_pair_any": 0,
        "failed_pair_q_sum": 0,
        "failed_pair_q_sum_low": 0,
        "failed_pair_q_sum_high": 0,
        "failed_pair_q_dif": 0,
        "failed_pair_t_sum": 0,
        "failed_pair_t_sum_low": 0,
        "failed_pair_t_sum_high": 0,
        "failed_pair_t_dif": 0,
        "rows_affected": 0,
        "values_zeroed": 0,
        "flagged_rows": 0,
        "selected_offender_channels": 0,
        "rows_with_multiple_offenders": 0,
        "max_failed_pairs_in_row": 0,
        "max_selected_offenders_in_row": 0,
        "valid_pair_observations_by_relation": {
            relation_type: 0
            for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
        },
        "failed_pair_any_by_relation": {
            relation_type: 0
            for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
        },
        "failed_pair_q_sum_low_by_relation": {
            relation_type: 0
            for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
        },
        "failed_pair_q_sum_high_by_relation": {
            relation_type: 0
            for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
        },
        "failed_pair_q_dif_by_relation": {
            relation_type: 0
            for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
        },
        "failed_pair_t_sum_low_by_relation": {
            relation_type: 0
            for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
        },
        "failed_pair_t_sum_high_by_relation": {
            relation_type: 0
            for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
        },
        "failed_pair_t_dif_by_relation": {
            relation_type: 0
            for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
        },
        "rows_failed_q_sum_low": 0,
        "rows_failed_q_sum_high": 0,
        "rows_failed_q_dif": 0,
        "rows_failed_t_sum_low": 0,
        "rows_failed_t_sum_high": 0,
        "rows_failed_t_dif": 0,
        "rows_failed_q_sum_low_by_relation": {
            relation_type: 0
            for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
        },
        "rows_failed_q_sum_high_by_relation": {
            relation_type: 0
            for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
        },
        "rows_failed_q_dif_by_relation": {
            relation_type: 0
            for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
        },
        "rows_failed_t_sum_low_by_relation": {
            relation_type: 0
            for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
        },
        "rows_failed_t_sum_high_by_relation": {
            relation_type: 0
            for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
        },
        "rows_failed_t_dif_by_relation": {
            relation_type: 0
            for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
        },
        "rows_with_relation_failures": {
            relation_type: 0
            for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
        },
        "selected_offender_cardinality_counts": {
            selected_count: 0
            for selected_count in TASK1_SELECTED_OFFENDER_CARDINALITY_VALUES
        },
    }
    row_failed_edges: dict[int, list[tuple[tuple[int, str, int], tuple[int, str, int], float]]] = {}
    row_forced_channels: dict[int, set[tuple[int, str, int]]] = {}
    row_failure_relations: dict[int, set[str]] = {}
    relation_metric_failed_rows = {
        relation_type: {
            component_key: set()
            for component_key, _ in TASK1_CHANNEL_COMBINATION_COMPONENT_LABELS
        }
        for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES
    }
    metric_failed_rows = {
        component_key: set()
        for component_key, _ in TASK1_CHANNEL_COMBINATION_COMPONENT_LABELS
    }
    channel_fail_masks = {
        channel_key: np.zeros(n_rows, dtype=bool)
        for channel_key in channel_map
    }
    offender_hit_counts = {
        channel_key: 0
        for channel_key in TASK1_CHANNEL_KEYS
    }
    selected_offender_count_by_row = np.zeros(n_rows, dtype=int)
    resolution_exact_by_row = np.ones(n_rows, dtype=bool)
    removed_value_frames: list[pd.DataFrame] = []

    for channel_a, channel_b, relation_type in _iter_task1_channel_relation_pairs(channel_map):
        relation_limits = relation_limits_by_type.get(relation_type) or relation_limits_by_type.get("any") or {}
        q_sum_left = float(relation_limits.get("q_sum_left", 0.0))
        q_sum_right = float(relation_limits.get("q_sum_right", 0.0))
        q_dif_threshold = float(relation_limits.get("q_dif_threshold", 0.0))
        t_sum_left = float(relation_limits.get("t_sum_left", 0.0))
        t_sum_right = float(relation_limits.get("t_sum_right", 0.0))
        t_dif_threshold = float(relation_limits.get("t_dif_threshold", 0.0))
        cols_a = channel_map[channel_a]
        cols_b = channel_map[channel_b]
        q_a = pd.to_numeric(df_input[cols_a["Q"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        q_b = pd.to_numeric(df_input[cols_b["Q"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        t_a = pd.to_numeric(df_input[cols_a["T"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        t_b = pd.to_numeric(df_input[cols_b["T"]], errors="coerce").fillna(0).to_numpy(dtype=float)

        if relation_type == "self":
            valid_mask = np.isfinite(q_a) & np.isfinite(t_a)
            pair_q_sum = q_a.copy()
            pair_q_dif = np.zeros_like(q_a, dtype=float)
            pair_t_sum = t_a.copy()
            pair_t_dif = np.zeros_like(t_a, dtype=float)
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
            pair_q_sum = 0.5 * (q_a + q_b)
            pair_q_dif = 0.5 * (q_a - q_b)
            pair_t_sum = 0.5 * (t_a + t_b)
            pair_t_dif = 0.5 * (t_a - t_b)
        if not np.any(valid_mask):
            continue

        valid_count = int(np.count_nonzero(valid_mask))
        summary["valid_pair_observations"] += valid_count
        summary["valid_pair_observations_by_relation"][relation_type] += valid_count

        q_metric_valid_mask = valid_mask & np.isfinite(pair_q_sum) & (pair_q_sum != 0)
        t_metric_valid_mask = valid_mask & np.isfinite(pair_t_sum) & (pair_t_sum != 0)
        q_dif_valid_mask = valid_mask & np.isfinite(pair_q_dif)
        t_dif_valid_mask = valid_mask & np.isfinite(pair_t_dif)
        if relation_type != "self":
            q_dif_valid_mask &= (pair_q_sum != 0)
            t_dif_valid_mask &= (pair_t_sum != 0)

        fail_q_sum_low = q_metric_valid_mask & (pair_q_sum < float(q_sum_left))
        fail_q_sum_high = q_metric_valid_mask & (pair_q_sum > float(q_sum_right))
        fail_q_sum = fail_q_sum_low | fail_q_sum_high
        fail_q_dif = q_dif_valid_mask & (np.abs(pair_q_dif) > abs(float(q_dif_threshold)))
        fail_t_sum_low = t_metric_valid_mask & (pair_t_sum < float(t_sum_left))
        fail_t_sum_high = t_metric_valid_mask & (pair_t_sum > float(t_sum_right))
        fail_t_sum = fail_t_sum_low | fail_t_sum_high
        fail_t_dif = t_dif_valid_mask & (np.abs(pair_t_dif) > abs(float(t_dif_threshold)))
        fail_any = fail_q_sum | fail_q_dif | fail_t_sum | fail_t_dif

        summary["failed_pair_q_sum"] += int(np.count_nonzero(fail_q_sum))
        summary["failed_pair_q_sum_low"] += int(np.count_nonzero(fail_q_sum_low))
        summary["failed_pair_q_sum_high"] += int(np.count_nonzero(fail_q_sum_high))
        summary["failed_pair_q_dif"] += int(np.count_nonzero(fail_q_dif))
        summary["failed_pair_t_sum"] += int(np.count_nonzero(fail_t_sum))
        summary["failed_pair_t_sum_low"] += int(np.count_nonzero(fail_t_sum_low))
        summary["failed_pair_t_sum_high"] += int(np.count_nonzero(fail_t_sum_high))
        summary["failed_pair_t_dif"] += int(np.count_nonzero(fail_t_dif))
        summary["failed_pair_any"] += int(np.count_nonzero(fail_any))
        summary["failed_pair_any_by_relation"][relation_type] += int(np.count_nonzero(fail_any))
        summary["failed_pair_q_sum_low_by_relation"][relation_type] += int(np.count_nonzero(fail_q_sum_low))
        summary["failed_pair_q_sum_high_by_relation"][relation_type] += int(np.count_nonzero(fail_q_sum_high))
        summary["failed_pair_q_dif_by_relation"][relation_type] += int(np.count_nonzero(fail_q_dif))
        summary["failed_pair_t_sum_low_by_relation"][relation_type] += int(np.count_nonzero(fail_t_sum_low))
        summary["failed_pair_t_sum_high_by_relation"][relation_type] += int(np.count_nonzero(fail_t_sum_high))
        summary["failed_pair_t_dif_by_relation"][relation_type] += int(np.count_nonzero(fail_t_dif))

        for component_key, fail_mask in (
            ("q_sum_low", fail_q_sum_low),
            ("q_sum_high", fail_q_sum_high),
            ("q_dif", fail_q_dif),
            ("t_sum_low", fail_t_sum_low),
            ("t_sum_high", fail_t_sum_high),
            ("t_dif", fail_t_dif),
        ):
            failed_rows = np.flatnonzero(fail_mask)
            if failed_rows.size == 0:
                continue
            relation_metric_failed_rows[relation_type][component_key].update(
                int(row_pos) for row_pos in failed_rows
            )
            metric_failed_rows[component_key].update(int(row_pos) for row_pos in failed_rows)

        if np.any(fail_any):
            q_sum_width = max(abs(float(q_sum_right) - float(q_sum_left)), 1e-9)
            t_sum_width = max(abs(float(t_sum_right) - float(t_sum_left)), 1e-9)
            q_dif_scale = max(abs(float(q_dif_threshold)), 1e-9)
            t_dif_scale = max(abs(float(t_dif_threshold)), 1e-9)
            q_sum_excess = np.maximum.reduce(
                [
                    np.zeros_like(pair_q_sum, dtype=float),
                    float(q_sum_left) - pair_q_sum,
                    pair_q_sum - float(q_sum_right),
                ]
            ) / q_sum_width
            q_dif_excess = np.maximum(np.abs(pair_q_dif) - abs(float(q_dif_threshold)), 0.0) / q_dif_scale
            t_sum_excess = np.maximum.reduce(
                [
                    np.zeros_like(pair_t_sum, dtype=float),
                    float(t_sum_left) - pair_t_sum,
                    pair_t_sum - float(t_sum_right),
                ]
            ) / t_sum_width
            t_dif_excess = np.maximum(np.abs(pair_t_dif) - abs(float(t_dif_threshold)), 0.0) / t_dif_scale
            pair_severity = q_sum_excess + q_dif_excess + t_sum_excess + t_dif_excess
            pair_severity = np.where(fail_any, pair_severity, 0.0)
            pair_severity = np.where(fail_any & (pair_severity <= 0), 1.0, pair_severity)
            for row_pos in np.flatnonzero(fail_any):
                row_pos_int = int(row_pos)
                row_failure_relations.setdefault(row_pos_int, set()).add(relation_type)
                if relation_type == "self":
                    row_forced_channels.setdefault(row_pos_int, set()).add(channel_a)
                else:
                    row_failed_edges.setdefault(row_pos_int, []).append(
                        (channel_a, channel_b, float(pair_severity[row_pos]))
                    )

    flagged_row_positions = sorted(set(row_failed_edges) | set(row_forced_channels))
    summary["flagged_rows"] = len(flagged_row_positions)
    for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES:
        summary["rows_with_relation_failures"][relation_type] = sum(
            1
            for relation_set in row_failure_relations.values()
            if relation_type in relation_set
        )
        for component_key, _ in TASK1_CHANNEL_COMBINATION_COMPONENT_LABELS:
            summary[f"rows_failed_{component_key}_by_relation"][relation_type] = len(
                relation_metric_failed_rows[relation_type][component_key]
            )

    for component_key, _ in TASK1_CHANNEL_COMBINATION_COMPONENT_LABELS:
        summary[f"rows_failed_{component_key}"] = len(metric_failed_rows[component_key])

    for row_pos in flagged_row_positions:
        forced_channels = sorted(
            row_forced_channels.get(row_pos, set()),
            key=_task1_channel_order_key,
        )
        edge_list = row_failed_edges.get(row_pos, [])
        uncovered_edges = [
            (channel_a, channel_b, severity)
            for channel_a, channel_b, severity in edge_list
            if channel_a not in forced_channels and channel_b not in forced_channels
        ]
        selected_channels = forced_channels + select_exact_minimum_vertex_cover(
            uncovered_edges,
            _task1_channel_order_key,
        )
        selected_channel_set = set(selected_channels)
        unresolved_edges = [
            (channel_a, channel_b, severity)
            for channel_a, channel_b, severity in edge_list
            if channel_a not in selected_channel_set and channel_b not in selected_channel_set
        ]
        resolution_exact_by_row[row_pos] = len(unresolved_edges) == 0

        summary["max_failed_pairs_in_row"] = max(
            summary["max_failed_pairs_in_row"],
            len(edge_list) + len(forced_channels),
        )
        summary["max_selected_offenders_in_row"] = max(
            summary["max_selected_offenders_in_row"],
            len(selected_channels),
        )
        summary["selected_offender_channels"] += len(selected_channels)
        if len(selected_channels) > 1:
            summary["rows_with_multiple_offenders"] += 1
        summary["selected_offender_cardinality_counts"][len(selected_channels)] = (
            int(summary["selected_offender_cardinality_counts"].get(len(selected_channels), 0)) + 1
        )
        selected_offender_count_by_row[row_pos] = len(selected_channels)
        for channel_key in selected_channels:
            channel_fail_masks[channel_key][row_pos] = True
            offender_hit_counts[channel_key] += 1

    changed_columns: list[str] = []
    any_row_affected = np.zeros(n_rows, dtype=bool)
    for channel_key, fail_mask in channel_fail_masks.items():
        if not np.any(fail_mask):
            continue
        cols = channel_map[channel_key]
        q_values = pd.to_numeric(df_input[cols["Q"]], errors="coerce").fillna(0)
        t_values = pd.to_numeric(df_input[cols["T"]], errors="coerce").fillna(0)
        summary["values_zeroed"] += int((q_values[fail_mask] != 0).sum())
        summary["values_zeroed"] += int((t_values[fail_mask] != 0).sum())
        any_row_affected |= fail_mask
        changed_columns.extend((cols["Q"], cols["T"]))
        if removed_value_pass_label is not None:
            removed_value_frames.append(
                _task1_build_removed_channel_values_frame(
                    df_input,
                    channel_key,
                    q_values,
                    t_values,
                    fail_mask,
                    removed_value_pass_label,
                )
            )

    summary["rows_affected"] = int(np.count_nonzero(any_row_affected))
    if apply_changes and changed_columns and snapshot_originals is not None:
        snapshot_originals(df_input, list(dict.fromkeys(changed_columns)))

    if apply_changes:
        for channel_key, fail_mask in channel_fail_masks.items():
            if not np.any(fail_mask):
                continue
            cols = channel_map[channel_key]
            # Legacy destructive mode only; final working_df calls use apply_changes=False.
            df_input.loc[fail_mask, [cols["Q"], cols["T"]]] = 0

    top_offenders = sorted(
        (
            (channel_key, count)
            for channel_key, count in offender_hit_counts.items()
            if count > 0
        ),
        key=lambda item: (-item[1], *_task1_channel_order_key(item[0])),
    )[:8]
    if top_offenders:
        top_offenders_str = ", ".join(
            f"P{plane}{side}{strip}:{count}"
            for (plane, side, strip), count in top_offenders
        )
        print(
            "[channel-combination-offenders] "
            f"flagged_rows={summary['flagged_rows']} "
            f"selected_offenders={summary['selected_offender_channels']} "
            f"multi_offender_rows={summary['rows_with_multiple_offenders']} "
            f"max_failed_pairs_in_row={summary['max_failed_pairs_in_row']} "
            f"top={top_offenders_str}"
        )

    summary["selected_offender_counts"] = {
        channel_key: int(offender_hit_counts.get(channel_key, 0))
        for channel_key in TASK1_CHANNEL_KEYS
    }
    summary["selected_offender_mask_by_channel"] = {
        channel_key: pd.Series(fail_mask, index=df_input.index, dtype=bool)
        for channel_key, fail_mask in channel_fail_masks.items()
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
    summary["rows_with_inexact_resolution"] = int(np.count_nonzero(~resolution_exact_by_row))
    summary["removed_channel_values"] = (
        pd.concat(removed_value_frames, ignore_index=True)
        if removed_value_frames
        else _empty_task1_removed_channel_values_frame()
    )
    return summary


def _task1_filter_tt_series(df_input: pd.DataFrame) -> pd.Series:
    for candidate in ("tt_task0_raw", "tt_task1_clean"):
        if candidate in df_input.columns:
            return df_input[candidate].apply(normalize_tt_label).astype(str)
    return pd.Series(["0"] * len(df_input), index=df_input.index, dtype=str)

def collect_task1_channel_combination_histogram_payload(
    df_input: pd.DataFrame,
    tt_series: pd.Series,
) -> pd.DataFrame:
    payload_rows: list[pd.DataFrame] = []
    channel_map = collect_task1_channel_qt_map(df_input)
    if not channel_map:
        return pd.DataFrame(
            columns=[
                "row_index",
                "tt",
                "combo",
                "relation_type",
                "same_strip",
                "q_sum",
                "q_dif",
                "t_sum",
                "t_dif",
            ]
        )

    tt_series = tt_series.reindex(df_input.index).fillna("0").astype(str)
    for channel_a, channel_b, relation_type in _iter_task1_channel_relation_pairs(channel_map):
        cols_a = channel_map[channel_a]
        cols_b = channel_map[channel_b]
        q_a = pd.to_numeric(df_input[cols_a["Q"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        q_b = pd.to_numeric(df_input[cols_b["Q"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        t_a = pd.to_numeric(df_input[cols_a["T"]], errors="coerce").fillna(0).to_numpy(dtype=float)
        t_b = pd.to_numeric(df_input[cols_b["T"]], errors="coerce").fillna(0).to_numpy(dtype=float)

        if relation_type == "self":
            valid_mask = (
                np.isfinite(q_a)
                & np.isfinite(t_a)
                & (q_a != 0)
                & (t_a != 0)
            )
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
                    "row_index": valid_index.to_numpy(),
                    "tt": tt_series.loc[valid_index].to_numpy(dtype=str),
                    "combo": f"P{channel_a[0]}S{channel_a[2]}{channel_a[1]}-P{channel_b[0]}S{channel_b[2]}{channel_b[1]}",
                    "relation_type": relation_type,
                    "same_strip": relation_type == "same_strip",
                    "q_sum": q_sum[valid_mask],
                    "q_dif": q_dif[valid_mask],
                    "t_sum": t_sum[valid_mask],
                    "t_dif": t_dif[valid_mask],
                }
            )
        )

    if not payload_rows:
        return pd.DataFrame(
            columns=[
                "row_index",
                "tt",
                "combo",
                "relation_type",
                "same_strip",
                "q_sum",
                "q_dif",
                "t_sum",
                "t_dif",
            ]
        )
    return pd.concat(payload_rows, ignore_index=True)

def subtract_task1_channel_combination_payload(
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

def plot_task1_channel_combination_filter_by_tt(
    original_payload: pd.DataFrame,
    before_payload: pd.DataFrame,
    after_payload: pd.DataFrame,
    basename_no_ext_value: str,
    fig_idx_value: int,
    *,
    show_plots: bool,
    save_plots: bool,
    plot_list: list[str] | None,
    limits_by_relation: dict[str, dict[str, tuple[float | None, float | None]]],
    q_left_limits_by_channel: dict[tuple[int, str, int], float] | None,
    top_n_by_relation: dict[str, int | None],
    include_same_strip_pairs: bool,
) -> int:
    observable_names = [observable for observable, _ in TASK1_CHANNEL_COMBINATION_OBSERVABLES]
    observable_labels = {observable: label for observable, label in TASK1_CHANNEL_COMBINATION_OBSERVABLES}
    scatter_max_points = 5000
    removed_scatter_marker_size = max(8, int(round(0.6 * removed_marker_size)))
    prefilter_scatter_size = max(3, int(round(0.25 * removed_marker_size)))
    noise_limit_line_kwargs = {
        "color": "red",
        "linestyle": "--",
        "linewidth": 1.4,
        "alpha": 0.85,
        "zorder": 6,
    }
    noise_limit_boundary_kwargs = {
        "color": "red",
        "linestyle": "--",
        "linewidth": 1.2,
        "alpha": 0.65,
        "zorder": 6,
    }
    rng = np.random.default_rng(0)
    q_left_limits_by_channel = q_left_limits_by_channel or {}

    original_payload = original_payload.copy()
    before_payload = before_payload.copy()
    after_payload = after_payload.copy()
    tt_labels = []
    for payload in (original_payload, before_payload, after_payload):
        if "tt" in payload.columns:
            tt_labels.extend(payload["tt"].astype(str).tolist())
    ordered_tts = [tt_label for tt_label in TT_COLOR_LABELS if tt_label != "0" and tt_label in set(tt_labels)]
    relation_label_map = {
        "self": "self",
        "same_strip": "same strip",
        "same_plane": "same plane",
        "any": "any",
    }

    for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES:
        relation_limits = limits_by_relation.get(relation_type, {})
        relation_top_n = top_n_by_relation.get(relation_type)
        for tt_label in ordered_tts:
            original_tt_all = original_payload.loc[
                (original_payload.get("tt", pd.Series(dtype=str)).astype(str) == tt_label)
                & (original_payload.get("relation_type", pd.Series(dtype=str)).astype(str) == relation_type)
            ].copy()
            before_tt_all = before_payload.loc[
                (before_payload.get("tt", pd.Series(dtype=str)).astype(str) == tt_label)
                & (before_payload.get("relation_type", pd.Series(dtype=str)).astype(str) == relation_type)
            ].copy()
            after_tt_all = after_payload.loc[
                (after_payload.get("tt", pd.Series(dtype=str)).astype(str) == tt_label)
                & (after_payload.get("relation_type", pd.Series(dtype=str)).astype(str) == relation_type)
            ].copy()
            if original_tt_all.empty and before_tt_all.empty and after_tt_all.empty:
                continue

            reference_counts = before_tt_all.groupby("combo").size().sort_values(ascending=False)
            if reference_counts.empty:
                reference_counts = original_tt_all.groupby("combo").size().sort_values(ascending=False)
            if reference_counts.empty:
                reference_counts = after_tt_all.groupby("combo").size().sort_values(ascending=False)
            combo_labels = (
                reference_counts.index.tolist()
                if relation_top_n is None
                else reference_counts.head(int(relation_top_n)).index.tolist()
            )
            if not combo_labels:
                continue

            original_tt_full = original_tt_all.loc[original_tt_all["combo"].isin(combo_labels)].copy()
            before_tt_full = before_tt_all.loc[before_tt_all["combo"].isin(combo_labels)].copy()
            after_tt_full = after_tt_all.loc[after_tt_all["combo"].isin(combo_labels)].copy()
            if original_tt_full.empty and before_tt_full.empty and after_tt_full.empty:
                continue

            prefilter_removed_tt_full = subtract_task1_channel_combination_payload(
                original_tt_full,
                before_tt_full,
            )
            removed_tt_full = subtract_task1_channel_combination_payload(
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

            combo_color_map = {label: _task1_population_color(label) for label in combo_labels}
            combo_q_boundaries: dict[str, dict[str, object]] = {}
            for combo_label in combo_labels:
                parsed_combo = _task1_parse_combo_label(combo_label)
                if parsed_combo is None:
                    continue
                channel_a, channel_b = parsed_combo
                q_left_a = q_left_limits_by_channel.get(channel_a)
                q_left_b = q_left_limits_by_channel.get(channel_b)
                combo_q_boundaries[combo_label] = {
                    "channel_a": channel_a,
                    "channel_b": channel_b,
                    "q_left_a": q_left_a,
                    "q_left_b": q_left_b,
                    "q_sum_left": (
                        0.5 * (float(q_left_a) + float(q_left_b))
                        if q_left_a is not None and q_left_b is not None
                        else None
                    ),
                }
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
            fig, axes = plt.subplots(n_obs, n_obs, figsize=(2.3 * n_obs, 2.3 * n_obs), constrained_layout=True)
            any_panel_data = False

            axis_ranges: dict[str, tuple[float, float]] = {}
            for observable in observable_names:
                full_values = pd.to_numeric(
                    original_tt_full.get(observable, pd.Series(dtype=float)),
                    errors="coerce",
                ).dropna().to_numpy(dtype=float)
                axis_ranges[observable] = _task1_capped_plot_range(
                    full_values,
                    relation_limits.get(observable, (None, None)),
                )

            for row_idx, y_name in enumerate(observable_names):
                for col_idx, x_name in enumerate(observable_names):
                    ax = axes[row_idx, col_idx]
                    if col_idx > row_idx:
                        ax.set_axis_off()
                        continue

                    if row_idx == col_idx:
                        before_values = pd.to_numeric(
                            before_tt_full.get(x_name, pd.Series(dtype=float)),
                            errors="coerce",
                        ).dropna().to_numpy(dtype=float)
                        after_values = pd.to_numeric(
                            after_tt_full.get(x_name, pd.Series(dtype=float)),
                            errors="coerce",
                        ).dropna().to_numpy(dtype=float)
                        prefilter_removed_values = pd.to_numeric(
                            prefilter_removed_tt_full.get(x_name, pd.Series(dtype=float)),
                            errors="coerce",
                        ).dropna().to_numpy(dtype=float)
                        prefilter_removed_values = prefilter_removed_values[np.isfinite(prefilter_removed_values)]
                        if (
                            before_values.size == 0
                            and after_values.size == 0
                            and prefilter_removed_values.size == 0
                        ):
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
                        lower_limit, upper_limit = relation_limits.get(x_name, (None, None))
                        if lower_limit is not None:
                            ax.axvline(float(lower_limit), color="lightgrey", linestyle="--", linewidth=1.1)
                        if upper_limit is not None:
                            ax.axvline(float(upper_limit), color="lightgrey", linestyle="--", linewidth=1.1)
                        if x_name == "q_sum":
                            for combo_label in combo_labels:
                                q_sum_noise_left = combo_q_boundaries.get(combo_label, {}).get("q_sum_left")
                                if q_sum_noise_left is None or not np.isfinite(q_sum_noise_left):
                                    continue
                                ax.axvline(
                                    float(q_sum_noise_left),
                                    **noise_limit_line_kwargs,
                                )
                        ax.set_xlim(x_low, x_high)
                        ax.set_yscale("log", nonpositive="clip")
                        ax.set_title(observable_labels[x_name], fontsize=9)
                    else:
                        after_x = pd.to_numeric(
                            after_tt.get(x_name, pd.Series(dtype=float)),
                            errors="coerce",
                        ).to_numpy(dtype=float)
                        after_y = pd.to_numeric(
                            after_tt.get(y_name, pd.Series(dtype=float)),
                            errors="coerce",
                        ).to_numpy(dtype=float)
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
                        after_mask = np.isfinite(after_x) & np.isfinite(after_y)
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
                        x_limits = relation_limits.get(x_name, (None, None))
                        y_limits = relation_limits.get(y_name, (None, None))
                        if x_limits[0] is not None:
                            ax.axvline(float(x_limits[0]), color="lightgrey", linestyle="--", linewidth=0.9)
                        if x_limits[1] is not None:
                            ax.axvline(float(x_limits[1]), color="lightgrey", linestyle="--", linewidth=0.9)
                        if y_limits[0] is not None:
                            ax.axhline(float(y_limits[0]), color="lightgrey", linestyle="--", linewidth=0.9)
                        if y_limits[1] is not None:
                            ax.axhline(float(y_limits[1]), color="lightgrey", linestyle="--", linewidth=0.9)
                        if x_name == "q_sum":
                            for combo_label in combo_labels:
                                q_sum_noise_left = combo_q_boundaries.get(combo_label, {}).get("q_sum_left")
                                if q_sum_noise_left is None or not np.isfinite(q_sum_noise_left):
                                    continue
                                ax.axvline(
                                    float(q_sum_noise_left),
                                    **noise_limit_line_kwargs,
                                )
                        if y_name == "q_sum":
                            for combo_label in combo_labels:
                                q_sum_noise_left = combo_q_boundaries.get(combo_label, {}).get("q_sum_left")
                                if q_sum_noise_left is None or not np.isfinite(q_sum_noise_left):
                                    continue
                                ax.axhline(
                                    float(q_sum_noise_left),
                                    **noise_limit_line_kwargs,
                                )
                        if x_name == "q_sum" and y_name == "q_dif":
                            q_sum_values = np.linspace(x_low, x_high, 200)
                            for combo_label in combo_labels:
                                combo_boundary = combo_q_boundaries.get(combo_label, {})
                                q_left_a = combo_boundary.get("q_left_a")
                                q_left_b = combo_boundary.get("q_left_b")
                                if q_left_a is not None and np.isfinite(q_left_a):
                                    ax.plot(
                                        q_sum_values,
                                        float(q_left_a) - q_sum_values,
                                        **noise_limit_boundary_kwargs,
                                    )
                                if q_left_b is not None and np.isfinite(q_left_b):
                                    ax.plot(
                                        q_sum_values,
                                        q_sum_values - float(q_left_b),
                                        **noise_limit_boundary_kwargs,
                                    )

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

            has_noise_limit_boundaries = any(
                combo_q_boundaries.get(label, {}).get("q_sum_left") is not None
                or combo_q_boundaries.get(label, {}).get("q_left_a") is not None
                or combo_q_boundaries.get(label, {}).get("q_left_b") is not None
                for label in combo_labels
            )
            style_handles = [
                mpl.lines.Line2D([0], [0], color="lightgrey", linestyle="--", linewidth=1.0, label="Removed Before Combination"),
                mpl.lines.Line2D([0], [0], color="black", linestyle="--", linewidth=1.0, label="Removed By Combination"),
                mpl.lines.Line2D([0], [0], color="black", linestyle="-", linewidth=1.4, label="Retained"),
                mpl.lines.Line2D(
                    [0],
                    [0],
                    color="black",
                    marker=removed_marker,
                    linestyle="None",
                    markersize=6,
                    markerfacecolor="none",
                    label="Combination Rejection",
                ),
            ]
            if has_noise_limit_boundaries:
                style_handles.append(
                    mpl.lines.Line2D(
                        [0],
                        [0],
                        color="red",
                        linestyle="--",
                        linewidth=1.4,
                        label="Noise Charge Limit",
                    )
                )
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
            combo_mode_label = "all pairs" if relation_top_n is None else f"top {int(relation_top_n)} pairs"
            fig.suptitle(
                f"Task 1 channel-combination filter by TT {tt_label}\n"
                f"{basename_no_ext_value} · {relation_label_map.get(relation_type, relation_type)} · {combo_mode_label}",
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
                save_plot_figure(save_fig_path, fig=fig, format="png", dpi=150)
            if show_plots:
                plt.show()
            plt.close(fig)

    return fig_idx_value

def build_task1_channel_pattern_series(df: pd.DataFrame) -> pd.Series:
    """Encode per-event front/back channel occupancy as a deterministic 32-bit string."""
    pattern_arrays: list[np.ndarray] = []
    for plane, strip, side in TASK1_CHANNEL_PATTERN_ORDER:
        endpoint = "ef" if str(side).upper() == "F" else "eb"
        col_name = f"p{plane}_s{strip}_{endpoint}_q"
        if col_name in df.columns:
            values = df[col_name].fillna(0).to_numpy(copy=False)
            bits = np.where(values != 0, "1", "0")
        else:
            print(f"Warning: missing channel column '{col_name}' while building TASK_1 patterns.")
            bits = np.full(len(df), "0", dtype="<U1")
        pattern_arrays.append(bits)

    if not pattern_arrays:
        return pd.Series(dtype="object", index=df.index)

    full_pattern = pattern_arrays[0].copy()
    for bits in pattern_arrays[1:]:
        full_pattern = np.char.add(full_pattern, bits)
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

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# Function definition ---------------------------------------------------------
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

def summary(vector):
    global coincidence_window_cal_ns
    quantile_left = CRT_gaussian_fit_quantile * 100
    quantile_right = 100 - CRT_gaussian_fit_quantile * 100

    vector = np.array(vector)  # Convert list to NumPy array
    cond = (vector > -coincidence_window_cal_ns) & (vector < coincidence_window_cal_ns)  # This should result in a boolean array
    vector = vector[cond]

    if len(vector) < 100:
        return np.nan
    try:
        percentile_left = np.percentile(vector, quantile_left)
        percentile_right = np.percentile(vector, quantile_right)
    except IndexError:
        print("Gave issue with:")
        print(vector)
        return np.nan
    vector = [x for x in vector if percentile_left <= x <= percentile_right]
    if len(vector) == 0:
        return np.nan
    mu, std = norm.fit(vector)
    return mu


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

def _load_task_1_z_priority_settings(config_obj: dict) -> dict[str, object]:
    settings: dict[str, object] = {
        "enabled": False,
        "simulated_only": True,
        "match_mode": "absolute",
        "source_csv": SIM_PARAMS_DEFAULT,
        "priority_abs": set(),
        "priority_norm": set(),
    }

    node = config_obj.get("task_1_z_position_priority")
    if not isinstance(node, dict):
        return settings

    settings["enabled"] = _as_bool(node.get("enabled"), False)
    settings["simulated_only"] = _as_bool(node.get("simulated_only"), True)

    match_mode = str(node.get("match_mode", "absolute")).strip().lower()
    if match_mode not in {"absolute", "normalized", "both"}:
        match_mode = "absolute"
    settings["match_mode"] = match_mode

    source_csv = node.get("source_csv")
    if source_csv:
        settings["source_csv"] = Path(os.path.expanduser(str(source_csv)))

    vectors = _iter_priority_vectors(node.get("vectors_mm"))
    settings["priority_abs"] = {tuple(round(value, 6) for value in vector) for vector in vectors}
    settings["priority_norm"] = {_normalize_z_vector(vector) for vector in vectors}

    if settings["enabled"] and not settings["priority_abs"]:
        print(
            "Warning: task_1_z_position_priority.enabled is true but vectors_mm is empty. "
            "Disabling z-priority for this run.",
            force=True,
        )
        settings["enabled"] = False

    return settings

def _load_simulated_z_lookup(
    csv_path: Path,
) -> dict[str, tuple[float, float, float, float]]:
    lookup: dict[str, tuple[float, float, float, float]] = {}
    if not csv_path.exists():
        print(
            f"Warning: z-priority lookup CSV not found: {csv_path}. "
            "Falling back to regular newest-file selection.",
            force=True,
        )
        return lookup

    required_cols = ["file_name", "z_plane_1", "z_plane_2", "z_plane_3", "z_plane_4"]
    try:
        sim_df = pd.read_csv(csv_path, usecols=required_cols)
    except Exception as exc:
        print(
            f"Warning: failed to load z-priority lookup CSV {csv_path}: {exc}. "
            "Falling back to regular newest-file selection.",
            force=True,
        )
        return lookup

    for file_name, z1, z2, z3, z4 in sim_df.itertuples(index=False, name=None):
        file_key = str(file_name).strip().lower()
        if not file_key:
            continue
        try:
            z_vector = (float(z1), float(z2), float(z3), float(z4))
        except (TypeError, ValueError):
            continue
        if not all(np.isfinite(value) for value in z_vector):
            continue
        lookup[file_key] = z_vector

    return lookup

def _select_latest_candidate_with_z_priority(
    files: Iterable[str],
    station: str,
    settings: dict[str, object],
    z_lookup: dict[str, tuple[float, float, float, float]],
    source_label: str,
    *,
    fallback_to_latest: bool = True,
) -> str | None:
    candidates = [name for name in files if isinstance(name, str) and name]
    if not candidates:
        return None

    if not settings.get("enabled", False):
        return select_latest_candidate(candidates, station) if fallback_to_latest else None

    prioritized: list[str] = []
    for name in candidates:
        key = name.lower()
        if settings.get("simulated_only", True) and not key.startswith("mi00"):
            continue
        z_vector = z_lookup.get(key)
        if z_vector is None:
            continue
        if _z_vector_matches_priority(z_vector, settings):
            prioritized.append(name)

    if prioritized:
        selected = max(prioritized, key=lambda name: newest_order_key(name, station))
        selected_z = z_lookup.get(selected.lower())
        print(
            f"[Z_PRIORITY] Selected prioritized file from {source_label}: {selected} "
            f"z={list(selected_z) if selected_z else 'NA'}",
            force=True,
        )
        return selected

    return select_latest_candidate(candidates, station) if fallback_to_latest else None


def _preferred_non_qa_or_all(
    file_names: list[str],
    preferred_non_qa_file_names: list[str],
) -> list[str]:
    if file_selection_mode == "qa" and preferred_non_qa_file_names:
        return preferred_non_qa_file_names
    if prioritize_other_than_qa_files and preferred_non_qa_file_names:
        return preferred_non_qa_file_names
    return file_names


# Function to process each line
def process_line(line):
    line = ZERO_TOKEN_PATTERN.sub('0', line)  # Replace '0000.0000' with '0'
    line = LEADING_ZERO_PATTERN.sub(r'\1', line)  # Remove leading zeros
    line = MULTI_SPACE_PATTERN.sub(',', line.strip())  # Replace multiple spaces with a comma
    line = XYEAR_PATTERN.sub(r'X\n\1', line)  # Replace XYYYY with X\nYYYY
    line = NEG_GAP_PATTERN.sub(r'\1 -\2', line)  # Ensure X-Y is properly spaced
    return line

# Function to check for malformed numbers (e.g., '-120.144.0')
def contains_malformed_numbers(line):
    return bool(MALFORMED_NUMBER_PATTERN.search(line))  # Detects multiple decimal points

# Function to validate year, month, and day
def is_valid_date(values):
    try:
        year, month, day = int(values[0]), int(values[1]), int(values[2])
        if year not in VALID_YEARS:  # Check valid years
            return False
        if not (1 <= month <= 12):  # Check valid month
            return False
        if not (1 <= day <= 31):  # Check valid day
            return False
        return True
    except ValueError:  # In case of non-numeric values
        return False

def _normalize_line_for_numpy(line: str) -> str:
    """Normalize raw text just enough for fast numeric parsing."""
    normalized = line.strip()
    normalized = ZERO_TOKEN_PATTERN.sub("0", normalized)
    normalized = LEADING_ZERO_PATTERN.sub(r"\1", normalized)
    if "X20" in normalized:
        normalized = XYEAR_PATTERN.sub(r"X \1", normalized)
    if "-" in normalized:
        normalized = NEG_GAP_PATTERN.sub(r"\1 -\2", normalized)
    return normalized

def _parse_raw_line_fast(line: str, expected_columns: int) -> np.ndarray | None:
    """Fast path for the common whitespace-only numeric rows."""
    stripped = line.strip()
    values = np.fromstring(stripped, sep=" ", dtype=np.float64)
    if values.size == expected_columns and is_valid_date(values[:3]):
        return values
    normalized = _normalize_line_for_numpy(stripped)
    values = np.fromstring(normalized, sep=" ", dtype=np.float64)
    if values.size == expected_columns and is_valid_date(values[:3]):
        return values
    return None

def _build_task1_input_dataframe(
    source_path: str,
    rejected_path: str,
    expected_columns: int,
    limit_rows: int | None = None,
) -> tuple[pd.DataFrame, int, int]:
    """Parse the raw .dat file in one pass and build the typed input dataframe."""
    return build_step1_raw_input_dataframe(source_path, rejected_path, expected_columns, limit_rows)
    read_lines = 0
    written_lines = 0
    stored_rows = 0
    flat_values = array("d")
    event_ids: list[int] = []

    with open(source_path, "r") as infile, open(rejected_path, "w") as rejectfile:
        for i, line in enumerate(infile, start=1):
            if line.lstrip().startswith("#"):
                continue
            read_lines += 1

            parsed_values = _parse_raw_line_fast(line, expected_columns)
            if parsed_values is None:
                cleaned_line = process_line(line)
                cleaned_values = cleaned_line.split(",")

                if len(cleaned_values) < 3 or not is_valid_date(cleaned_values[:3]):
                    rejectfile.write(f"Line {i} (Invalid date): {line.strip()}\n")
                    continue

                if contains_malformed_numbers(line):
                    rejectfile.write(f"Line {i} (Malformed number): {line.strip()}\n")
                    continue

                if len(cleaned_values) != expected_columns:
                    rejectfile.write(f"Line {i} (Wrong column count): {line.strip()}\n")
                    continue

                parsed_values = np.fromstring(
                    cleaned_line.replace(",", " "),
                    sep=" ",
                    dtype=np.float64,
                )
                if parsed_values.size != expected_columns:
                    rejectfile.write(f"Line {i} (Wrong column count): {line.strip()}\n")
                    continue

            written_lines += 1
            if limit_rows is None or stored_rows < limit_rows:
                flat_values.extend(parsed_values)
                event_ids.append(i)
                stored_rows += 1

    if stored_rows == 0:
        return pd.DataFrame(), read_lines, written_lines

    raw_matrix = np.frombuffer(flat_values, dtype=np.float64).reshape(stored_rows, expected_columns)
    datetime_components = {
        "year": np.rint(raw_matrix[:, 0]).astype(np.int16, copy=False),
        "month": np.rint(raw_matrix[:, 1]).astype(np.int8, copy=False),
        "day": np.rint(raw_matrix[:, 2]).astype(np.int8, copy=False),
        "hour": np.rint(raw_matrix[:, 3]).astype(np.int8, copy=False),
        "minute": np.rint(raw_matrix[:, 4]).astype(np.int8, copy=False),
        "second": np.rint(raw_matrix[:, 5]).astype(np.int8, copy=False),
    }
    datetime_series = pd.to_datetime(datetime_components)

    value_columns = [f"column_{i}" for i in range(6, expected_columns)]
    value_data = raw_matrix[:, 6:].astype(np.float32, copy=False)
    parsed_df = pd.DataFrame(value_data, columns=value_columns, copy=False)
    # Stable per-file event identity: raw file line number before any Task 1 filtering.
    parsed_df.insert(0, "event_id", np.asarray(event_ids, dtype=np.int64))
    parsed_df.insert(0, "datetime", datetime_series)
    parsed_df["column_6"] = np.rint(raw_matrix[:, 6]).astype(np.int8, copy=False)
    return parsed_df, read_lines, written_lines


def _zpos_from_conf(row):
    return np.array([row.get(f"P{i}", np.nan) for i in range(1, 5)])


def snapshot_original_columns_once(
    frame: pd.DataFrame,
    column_names: Iterable[str],
) -> None:
    """Store a column once, before its first in-place mutation, to keep original values."""
    if not track_removed_rows or frame is not working_df:
        return
    for col in column_names:
        if col in frame.columns and col not in original_columns_store:
            original_columns_store[col] = frame[col].copy()

def _restore_original_values(rows: pd.DataFrame) -> pd.DataFrame:
    if not track_removed_rows or rows.empty:
        return rows
    restored_rows = rows.copy()
    for col, original_series in original_columns_store.items():
        if col in restored_rows.columns:
            restored_rows.loc[:, col] = original_series.reindex(restored_rows.index)
    return restored_rows

def append_removed_rows(rows: pd.DataFrame) -> None:
    """Append fully removed rows with original index and pre-modification values preserved."""
    global diagnostic_removed_rows_df
    if not track_removed_rows or rows.empty:
        return
    rows_to_add = _restore_original_values(rows)
    if not diagnostic_removed_rows_df.empty:
        rows_to_add = rows_to_add.loc[~rows_to_add.index.isin(diagnostic_removed_rows_df.index)]
        if rows_to_add.empty:
            return
    diagnostic_removed_rows_df = pd.concat([diagnostic_removed_rows_df, rows_to_add], ignore_index=False, sort=False)

def append_removed_rows_from_mask(frame: pd.DataFrame, removed_mask: pd.Series) -> None:
    if not track_removed_rows or frame.empty:
        return
    aligned_mask = removed_mask.reindex(frame.index, fill_value=False)
    if aligned_mask.any():
        append_removed_rows(frame.loc[aligned_mask].copy())

def build_original_columns_frame() -> pd.DataFrame:
    if not track_removed_rows:
        return pd.DataFrame(index=tracking_base_index)
    if not original_columns_store:
        return pd.DataFrame(index=tracking_base_index)
    return pd.DataFrame(
        {col: series.reindex(tracking_base_index) for col, series in original_columns_store.items()},
        index=tracking_base_index,
    )

def build_task1_channel_filter_stage_frames(
    df_input: pd.DataFrame,
    *,
    original_reference_df: pd.DataFrame | None,
    relation_limits_by_type: Mapping[str, Mapping[str, float]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if df_input.empty:
        empty_df = df_input.iloc[0:0].copy()
        return empty_df, empty_df, empty_df

    if original_reference_df is None or original_reference_df.empty:
        original_df = df_input.copy()
    else:
        original_df = original_reference_df.reindex(df_input.index).copy()
        for col in df_input.columns:
            if col not in original_df.columns:
                original_df[col] = df_input[col]

    pre_combination_df = df_input.copy()
    final_df = pre_combination_df.copy()
    apply_task1_plane_combination_filter(
        final_df,
        relation_limits_by_type=relation_limits_by_type,
    )
    return original_df, pre_combination_df, final_df


# ----------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------
# Trigger type helpers -------------------------------------------------------------
# ----------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------

def compute_tt(df: pd.DataFrame, column_name: str, columns_map: dict[int, list[str]] | None = None) -> pd.DataFrame:
    """Compute trigger type based on planes with non-zero charge."""
    tt_str = pd.Series("", index=df.index, dtype="object")
    for plane in range(1, 5):
        if columns_map:
            charge_columns = [col for col in columns_map.get(plane, []) if col in df.columns]
        else:
            charge_columns = [
                col
                for strip in range(1, 5)
                for col in (f"p{plane}_s{strip}_ef_q", f"p{plane}_s{strip}_eb_q")
                if col in df.columns
            ]
        if charge_columns:
            has_charge = df.loc[:, charge_columns].ne(0).any(axis=1)
            tt_str = tt_str.where(~has_charge, tt_str + str(plane))
    df.loc[:, column_name] = tt_str.replace("", "0").astype(int)
    return df


def task1_plot_enabled(alias: str) -> bool:
    if not task1_plot_status_by_alias:
        return True
    return step1_task_plot_enabled(alias, task1_plot_status_by_alias, plot_mode)
CLI_PARSER = build_step1_cli_parser("Run Stage 1 STEP_1 TASK_1 (RAW->CLEAN).", STATION_CHOICES)
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
    include_filter_parameter_config=True,
    log_fn=print,
)
config_root = task_config_bundle["config_root"]
config_file_path = task_config_bundle["config_file_path"]
plot_catalog_file_path = task_config_bundle["plot_catalog_file_path"]
parameter_config_file_path = task_config_bundle["parameter_config_file_path"]
plot_parameter_config_file_path = task_config_bundle["plot_parameter_config_file_path"]
filter_parameter_config_file_path = task_config_bundle["filter_parameter_config_file_path"]
fallback_parameter_config_file_path = task_config_bundle["fallback_parameter_config_file_path"]
config = task_config_bundle["config"]
task1_plot_status_by_alias = load_step1_task_plot_catalog(
    plot_catalog_file_path,
    TASK1_PLOT_ALIASES,
    "Task 1",
    log_fn=print,
)
debug_mode = False

home_path = str(resolve_home_path_from_config(config))

# ~/DATAFLOW_v3/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/QUALITY_ASSURANCE
REFERENCE_TABLES_DIR = get_repo_root() / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS" / "ANCILLARY" / "QUALITY_ASSURANCE" / "REFERENCE_TABLES"

# -----------------------------------------------------------------------------

# Round execution time to seconds and format it in YYYY-MM-DD_HH.MM.SS
execution_time = str(start_execution_time_counting).split('.')[0]  # Remove microseconds
print("Execution time is:", execution_time)

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
    filter_parameter_config_file_path=filter_parameter_config_file_path,
    log_fn=print,
)
config["_plot_station_id"] = station
config["_plot_task_number"] = task_number
file_selection_mode = str(config.get("file_selection_mode", "new")).strip().lower()
process_only_qa_retry_files = bool(config.get("process_only_qa_retry_files", False))
prioritize_other_than_qa_files = bool(config.get("prioritize_other_than_qa_files", True))
save_removed_channel_values = _coerce_config_bool(
    config.get("save_removed_channel_values"),
    default=True,
)
joined_analysis_files = coerce_positive_int_config(config.get("joined_analysis_files"), default=1)
joined_analysis_time_tolerance_hours = coerce_nonnegative_float_config(
    config.get("joined_analysis_time_tolerance_hours"),
    default=5.0,
)
if process_only_qa_retry_files:
    print(
        "[QA_ONLY] Enabled by STEP_1 shared config: only files present in the active QA retry list will be processed."
    )
elif prioritize_other_than_qa_files:
    print(
        "[QA_PRIORITY] Enabled by STEP_1 shared config: non-QA files will be preferred over QA retry files."
    )

selection_config = load_selection_for_paths(
    [config_file_path],
    master_config_root=config_root,
)
if not station_is_selected(station, selection_config.stations):
    print(f"Station {station} skipped by selection.stations.", force=True)
    sys.exit(0)

selected_input_file = CLI_ARGS.input_file_flag or CLI_ARGS.input_file
if selected_input_file:
    user_file_path = selected_input_file
    user_file_selection = True
    print("User provided file path:", user_file_path)
else:
    user_file_selection = False

# -----------------------------------------------------------------------------

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
    early_status_filename_base = Path(user_file_path).stem
else:
    early_status_filename_base = f"__task{task_number}_startup_station_{station}__"
status_filename_base = early_status_filename_base
status_execution_date = initialize_status_row(
    early_status_csv_path,
    filename_base=status_filename_base,
    completion_fraction=0.0,
)
base_directory = str(repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / f"MINGO0{station}" / "STAGE_1" / "EVENT_DATA")
raw_to_list_working_directory = os.path.join(base_directory, f"STEP_1/TASK_{task_number}")

metadata_directory = os.path.join(raw_to_list_working_directory, "METADATA")

if task_number == 1:
    task0_output_directory = os.path.join(base_directory, "STEP_1/TASK_0/OUTPUT_FILES")
    user_selected_raw_parquet = bool(
        selected_input_file
        and Path(str(selected_input_file)).suffix.lower() == ".parquet"
        and Path(str(selected_input_file)).stem.startswith("raw_")
    )
    if selected_input_file and not user_selected_raw_parquet:
        raise SystemExit(
            "Task 1 now reads Task 0 raw parquet only. "
            f"Selected input is not raw_*.parquet: {selected_input_file}"
        )
    task1_raw_parquet_input = True
    raw_directory = "STEP_1/TASK_0/OUTPUT_FILES"
    raw_working_directory = task0_output_directory

else:
    task1_raw_parquet_input = False
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

    "pdf_directory": os.path.join(raw_to_list_working_directory, "PLOTS/PDF_DIRECTORY"),
    "base_figure_directory": os.path.join(raw_to_list_working_directory, "PLOTS/FIGURE_DIRECTORY"),
    "figure_directory": os.path.join(raw_to_list_working_directory, f"PLOTS/FIGURE_DIRECTORY/FIGURES_EXEC_ON_{date_execution}"),

    "ancillary_directory": os.path.join(raw_to_list_working_directory, "ANCILLARY"),

    "empty_files_directory": os.path.join(raw_to_list_working_directory, "ANCILLARY/EMPTY_FILES"),
    "rejected_files_directory": os.path.join(raw_to_list_working_directory, "ANCILLARY/REJECTED_FILES"),
    "temp_files_directory": os.path.join(raw_to_list_working_directory, "ANCILLARY/TEMP_FILES"),
    "removed_channel_values_directory": os.path.join(raw_to_list_working_directory, "ANCILLARY/REMOVED_CHANNEL_VALUES"),
    "tracking_directory": os.path.join(raw_to_list_working_directory, "ANCILLARY/TRACKING"),

    "unprocessed_directory": os.path.join(raw_to_list_working_directory, "INPUT_FILES/UNPROCESSED_DIRECTORY"),
    "out_of_date_directory": os.path.join(raw_to_list_working_directory, "INPUT_FILES/OUT_OF_DATE_DIRECTORY"),
    "error_directory": os.path.join(raw_to_list_working_directory, "INPUT_FILES/ERROR_DIRECTORY"),
    "processing_directory": os.path.join(raw_to_list_working_directory, "INPUT_FILES/PROCESSING_DIRECTORY"),
    "completed_directory": os.path.join(raw_to_list_working_directory, "INPUT_FILES/COMPLETED_DIRECTORY"),

    "output_directory": output_location,

    "raw_directory": os.path.join(raw_working_directory, "."),

    "metadata_directory": metadata_directory,
}

(
    plot_mode,
    create_plots,
    create_essential_plots,
    save_plots,
    create_pdf,
    show_plots,
    create_debug_plots,
) = resolve_step1_plot_options(config)
apply_task1_plot_catalog_modes()

debug_plot_directory = os.path.join(
    base_directories["base_plots_directory"],
    "DEBUG_PLOTS",
    f"FIGURES_EXEC_ON_{date_execution}",
)
debug_fig_idx = 1
# Create ALL directories if they don't already exist
# Create ALL directories if they don't already exist
for directory in base_directories.values():
    # Skip figure directories at startup; create lazily after selecting a file.
    if directory in (base_directories["base_figure_directory"], base_directories["figure_directory"]):
        continue
    os.makedirs(directory, exist_ok=True)

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

raw_files = set(os.listdir(raw_directory))
unprocessed_files = set(os.listdir(unprocessed_directory))
processing_files = set(os.listdir(processing_directory))
completed_files = set(os.listdir(completed_directory))

# Ordered list from highest to lowest priority
LEVELS = [
    completed_directory,
    processing_directory,
    unprocessed_directory,
    raw_directory,
]

station_re = re.compile(r'^raw_mi0(\d).*\.parquet$', re.IGNORECASE)

seen = set()
for d in LEVELS:
    d = Path(d)
    if not d.exists():
        continue

    current_files = {p.name for p in d.iterdir() if p.is_file()}

    # ────────────────────────────────────────────────────────────────
    # Remove raw parquet files whose prefix “raw_mi0X” does not match `station`
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

# Files to move: Task 0 raw parquet output not already in Task 1 staging.
raw_files = set(os.listdir(raw_directory))

raw_files = {
    f
    for f in raw_files
    if f.startswith("raw_") and f.lower().endswith(".parquet")
}
print("raw parquet files are:", raw_files)

unprocessed_files = set(os.listdir(unprocessed_directory))
processing_files = set(os.listdir(processing_directory))
completed_files = set(os.listdir(completed_directory))

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
print(input_file_config_path)

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
    z_1 = 0
    z_2 = 150
    z_3 = 300
    z_4 = 450

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
apply_task1_plot_catalog_modes()
limit_number = config.get("limit_number", None)
limit = last_file_test and limit_number is not None
force_replacement = config["force_replacement"]
article_format = config["article_format"]

# Charge calibration to fC

# Charge front-back

# Slewing correction

# Time filtering
time_window_filtering = config["time_window_filtering"]

# Time calibration

# Y position

# RPC variables

# Alternative

# TimTrack

# Validation

EXPECTED_COLUMNS_config = config["EXPECTED_COLUMNS_config"]

complete_reanalysis = config["complete_reanalysis"]

limit_number = config.get("limit_number", None)
limit = last_file_test and limit_number is not None

# Pre-cal Front & Back
T_side_left_pre_cal_debug = config["T_side_left_pre_cal_debug"]
T_side_right_pre_cal_debug = config["T_side_right_pre_cal_debug"]
Q_side_left_pre_cal_debug = config["Q_side_left_pre_cal_debug"]
Q_side_right_pre_cal_debug = config["Q_side_right_pre_cal_debug"]

T_side_left_pre_cal_default = config.get("T_side_left_pre_cal_default", -200)
T_side_right_pre_cal_default = config.get("T_side_right_pre_cal_default", -100)
Q_side_left_pre_cal_default = config.get("Q_side_left_pre_cal_default", 0)
Q_side_right_pre_cal_default = config.get("Q_side_right_pre_cal_default", 500)

T_side_left_pre_cal_ST = config["T_side_left_pre_cal_ST"]
T_side_right_pre_cal_ST = config["T_side_right_pre_cal_ST"]
Q_side_left_pre_cal_ST = config["Q_side_left_pre_cal_ST"]
Q_side_right_pre_cal_ST = config["Q_side_right_pre_cal_ST"]

# Pre-cal Sum & Diff
T_dif_pre_cal_threshold = config.get("T_dif_pre_cal_threshold", 20)
channel_combination_q_sum_left = float(config["channel_combination_q_sum_left"])
channel_combination_q_sum_right = float(config["channel_combination_q_sum_right"])
channel_combination_q_dif_threshold = float(config["channel_combination_q_dif_threshold"])
channel_combination_t_sum_left = float(config["channel_combination_t_sum_left"])
channel_combination_t_sum_right = float(config["channel_combination_t_sum_right"])
channel_combination_t_dif_threshold = float(config["channel_combination_t_dif_threshold"])
task1_channel_combination_limits_by_relation = _task1_load_channel_combination_relation_limits(
    config,
    base_q_sum_left=channel_combination_q_sum_left,
    base_q_sum_right=channel_combination_q_sum_right,
    base_q_dif_threshold=channel_combination_q_dif_threshold,
    base_t_sum_left=channel_combination_t_sum_left,
    base_t_sum_right=channel_combination_t_sum_right,
    base_t_dif_threshold=channel_combination_t_dif_threshold,
)
print(
    "Task 1 channel-combination relations: "
    + ", ".join(
        f"{relation_type}[Qsum={limits['q_sum_left']}..{limits['q_sum_right']}, "
        f"Qdif=+/-{limits['q_dif_threshold']}, "
        f"Tsum={limits['t_sum_left']}..{limits['t_sum_right']}, "
        f"Tdif=+/-{limits['t_dif_threshold']}]"
        for relation_type, limits in task1_channel_combination_limits_by_relation.items()
    )
)
recalculate_noise_charge_limit = _coerce_config_bool(
    config.get("recalculate_noise_charge_limit", True),
    default=True,
)
noise_charge_limit_by_channel_config = config.get("noise_charge_limit_by_channel", {}) or {}
manual_channel_noise_charge_limits: dict[tuple[int, str, int], float] = {}
if isinstance(noise_charge_limit_by_channel_config, dict):
    for channel_label, limit_value in noise_charge_limit_by_channel_config.items():
        match = re.fullmatch(r"P(?P<plane>\d+)S(?P<strip>\d+)(?P<side>[FB])", str(channel_label).strip())
        if match is None:
            continue
        if limit_value in (None, "", "null", "None"):
            continue
        try:
            parsed_limit = float(limit_value)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(parsed_limit):
            continue
        manual_channel_noise_charge_limits[
            (
                int(match.group("plane")),
                str(match.group("side")),
                int(match.group("strip")),
            )
        ] = parsed_limit
print(
    "Task 1 noise-charge-limit mode: inactive "
    f"(legacy config kept for reference; configured channels: {len(manual_channel_noise_charge_limits)})"
)
channel_noise_limit_hist_bins = max(
    24,
    _coerce_config_value(config.get("channel_noise_limit_hist_bins", 48), int, 48),
)
channel_noise_limit_min_total_values = max(
    20,
    _coerce_config_value(config.get("channel_noise_limit_min_total_values", 80), int, 80),
)
channel_noise_limit_min_removed_values = max(
    5,
    _coerce_config_value(config.get("channel_noise_limit_min_removed_values", 12), int, 12),
)
channel_noise_limit_min_class_count = max(
    5,
    _coerce_config_value(config.get("channel_noise_limit_min_class_count", 10), int, 10),
)
channel_noise_limit_min_removed_left_fraction = min(
    1.0,
    max(
        0.0,
        _coerce_config_value(
            config.get("channel_noise_limit_min_removed_left_fraction", 0.7),
            float,
            0.7,
        ),
    ),
)
channel_noise_limit_min_log_separation = max(
    0.0,
    _coerce_config_value(config.get("channel_noise_limit_min_log_separation", 0.12), float, 0.12),
)

# Post-calibration

# Once calculated the RPC variables
T_sum_RPC_left = config.get("T_sum_RPC_left", -7)
T_sum_RPC_right = config.get("T_sum_RPC_right", 7)

# TimTrack filter
res_ystr_filter = config.get("res_ystr_filter", 500)
res_tsum_filter = config.get("res_tsum_filter", 3.5)
res_tdif_filter = config.get("res_tdif_filter", 1.0)

# Fitting comparison

# Calibrations
CRT_gaussian_fit_quantile = config.get("CRT_gaussian_fit_quantile", 0.03)
coincidence_window_og_ns = config["coincidence_window_og_ns"]
coincidence_window_cal_ns = config.get("coincidence_window_cal_ns", 3)

# Pedestal charge calibration
pedestal_left = config.get("pedestal_left", -1)
pedestal_right = config.get("pedestal_right", 3)

# Front-back charge
distance_sum_charges_left_fit = config.get("distance_sum_charges_left_fit", -5)
distance_sum_charges_right_fit = config.get("distance_sum_charges_right_fit", 200)
distance_dif_charges_up_fit = config.get("distance_dif_charges_up_fit", 10)
distance_dif_charges_low_fit = config.get("distance_dif_charges_low_fit", -10)
distance_sum_charges_plot = config.get("distance_sum_charges_plot", 800)
front_back_fit_threshold = config.get("front_back_fit_threshold", 4)

# Variables to modify
beta = config.get("beta", 1)
strip_speed_factor_of_c = config.get("strip_speed_factor_of_c", 0.666666667)

degree_of_polynomial = config.get("degree_of_polynomial", 4)

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
Q_clip_max_debug = config.get("Q_clip_max_debug", 600)
num_bins_debug = config["num_bins_debug"]

T_clip_min_default = config.get("T_clip_min_default", -300)
T_clip_max_default = config.get("T_clip_max_default", 100)
Q_clip_min_default = config.get("Q_clip_min_default", 0)
Q_clip_max_default = config.get("Q_clip_max_default", 500)
num_bins_default = config["num_bins_default"]

T_clip_min_ST = config.get("T_clip_min_ST", -300)
T_clip_max_ST = config.get("T_clip_max_ST", 100)
Q_clip_min_ST = config.get("Q_clip_min_ST", 0)
Q_clip_max_ST = config.get("Q_clip_max_ST", 500)

log_scale = config["log_scale"]
track_removed_rows = _coerce_config_bool(config.get("track_removed_rows", False), default=False)
keep_all_columns_output = _coerce_config_bool(
    config.get("keep_all_columns_output", False),
    default=False,
)
removed_marker = str(config.get("removed_marker", "x"))
removed_marker_size = _coerce_config_value(config.get("removed_marker_size", 30), int, 30)
removed_marker_alpha = _coerce_config_value(config.get("removed_marker_alpha", 0.9), float, 0.9)
_channel_combination_plot_top_n_raw = config.get("channel_combination_plot_top_n", 10)
if _channel_combination_plot_top_n_raw in (None, "", "null", "None"):
    channel_combination_plot_top_n = None
else:
    channel_combination_plot_top_n = max(
        1,
        _coerce_config_value(_channel_combination_plot_top_n_raw, int, 10),
    )
channel_combination_plot_include_same_strip_pairs = _coerce_config_bool(
    config.get("channel_combination_plot_include_same_strip_pairs", True),
    default=True,
)
channel_combination_plot_top_n_by_relation: dict[str, int | None] = {}
for _relation_type in ("self", "same_strip", "same_plane", "any"):
    _relation_top_n_raw = config.get(
        f"channel_combination_plot_top_n_{_relation_type}",
        channel_combination_plot_top_n,
    )
    if _relation_top_n_raw in (None, "", "null", "None"):
        channel_combination_plot_top_n_by_relation[_relation_type] = None
    else:
        channel_combination_plot_top_n_by_relation[_relation_type] = max(
            1,
            _coerce_config_value(_relation_top_n_raw, int, 10),
        )
_channel_pair_plot_top_n_raw = config.get("channel_pair_plot_top_n", None)
if _channel_pair_plot_top_n_raw in (None, "", "null", "None"):
    channel_pair_plot_top_n = None
else:
    channel_pair_plot_top_n = max(
        1,
        _coerce_config_value(_channel_pair_plot_top_n_raw, int, 10),
    )
calibrate_strip_Q_pedestal_thr_factor = config.get("calibrate_strip_Q_pedestal_thr_factor", 31.62)
calibrate_strip_Q_pedestal_thr_factor_2 = config.get("calibrate_strip_Q_pedestal_thr_factor_2", 1.5)
calibrate_strip_Q_pedestal_translate_charge_cal = config.get("calibrate_strip_Q_pedestal_translate_charge_cal", 0.25)

calibrate_strip_Q_pedestal_percentile = config.get("calibrate_strip_Q_pedestal_percentile", 10)
calibrate_strip_Q_pedestal_rel_th = config.get("calibrate_strip_Q_pedestal_rel_th", 0.015)
calibrate_strip_Q_pedestal_rel_th_cal = config.get("calibrate_strip_Q_pedestal_rel_th_cal", 0.4)
calibrate_strip_Q_pedestal_abs_th = config.get("calibrate_strip_Q_pedestal_abs_th", 3)
calibrate_strip_Q_pedestal_q_quantile = config.get("calibrate_strip_Q_pedestal_q_quantile", 0.4)

scatter_2d_and_fit_new_xlim_left = config.get("scatter_2d_and_fit_new_xlim_left", -5)
scatter_2d_and_fit_new_xlim_right = config.get("scatter_2d_and_fit_new_xlim_right", 200)
scatter_2d_and_fit_new_ylim_abs = abs(float(config.get("scatter_2d_and_fit_new_ylim_abs", config.get("scatter_2d_and_fit_new_ylim_top", 11))))
scatter_2d_and_fit_new_ylim_top = scatter_2d_and_fit_new_ylim_abs
scatter_2d_and_fit_new_ylim_bottom = -scatter_2d_and_fit_new_ylim_abs

calibrate_strip_T_dif_T_rel_th = config.get("calibrate_strip_T_dif_T_rel_th", 0.1)
calibrate_strip_T_dif_T_abs_th = config.get("calibrate_strip_T_dif_T_abs_th", 1)

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

Q_F_left_pre_cal = Q_side_left_pre_cal_default
Q_F_right_pre_cal = Q_side_right_pre_cal_default

Q_B_left_pre_cal = Q_side_left_pre_cal_default
Q_B_right_pre_cal = Q_side_right_pre_cal_default

T_F_left_pre_cal_ST = T_side_left_pre_cal_ST  #-115
T_F_right_pre_cal_ST = T_side_right_pre_cal_ST
T_B_left_pre_cal_ST = T_side_left_pre_cal_ST
T_B_right_pre_cal_ST = T_side_right_pre_cal_ST
Q_F_left_pre_cal_ST = Q_side_left_pre_cal_ST
Q_F_right_pre_cal_ST = Q_side_right_pre_cal_ST
Q_B_left_pre_cal_ST = Q_side_left_pre_cal_ST
Q_B_right_pre_cal_ST = Q_side_right_pre_cal_ST

Q_left_side = Q_side_left_pre_cal_ST
Q_right_side = Q_side_right_pre_cal_ST

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

global_variables = {}

CHANNEL_CONTAGION_METADATA_FIELDS: tuple[str, ...] = (
    "mean_off_diagonal_global_raw",
    "max_off_diagonal_global_raw",
    "mean_off_diagonal_interplane_global_raw",
    "mean_off_diagonal_global_clean",
    "max_off_diagonal_global_clean",
    "mean_off_diagonal_interplane_global_clean",
    "mean_off_diagonal_by_tt_task0_raw",
    "max_off_diagonal_by_tt_task0_raw",
    "mean_off_diagonal_interplane_by_tt_task0_raw",
    "mean_off_diagonal_by_tt_clean",
    "max_off_diagonal_by_tt_clean",
    "mean_off_diagonal_interplane_by_tt_clean",
)
channel_contagion_metrics: dict[str, float] = {
    key: float("nan") for key in CHANNEL_CONTAGION_METADATA_FIELDS
}
activation_metadata: dict[str, object] = {}
pattern_metadata: dict[str, object] = {}

TT_COUNT_VALUES: tuple[int, ...] = (
    0, 1, 2, 3, 4, 12, 13, 14, 23, 24, 34, 123, 124, 134, 234, 1234
)
TT_COLOR_LABELS: tuple[str, ...] = tuple(str(tt_value) for tt_value in TT_COUNT_VALUES)
# Colour mapping for trigger-type labels.
# Single-plane labels ('1','2','3','4') are assigned a muted gray so the
# more informative multi-plane combinations receive the vivid palette colors.
TT_COLOR_CMAP = plt.get_cmap("tab10")
_palette = sns.color_palette("tab10", n_colors=10)
TT_COLOR_MAP: dict[str, tuple[float, float, float, float]] = {}
_multi_idx = 0
for tt_label in TT_COLOR_LABELS:
    if len(tt_label) == 1:
        # muted gray for single-plane events
        TT_COLOR_MAP[tt_label] = (0.60, 0.60, 0.60, 1.0)
    else:
        rgb = _palette[_multi_idx % len(_palette)]
        TT_COLOR_MAP[tt_label] = (float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0)
        _multi_idx += 1

# Fallback default color
TT_COLOR_DEFAULT = (0.45, 0.45, 0.45, 1.0)
TASK1_CHANNEL_PATTERN_ORDER: tuple[tuple[int, int, str], ...] = tuple(
    (plane, strip, side)
    for plane in range(1, 5)
    for strip in range(1, 5)
    for side in ("F", "B")
)
TASK1_SELECTED_OFFENDER_CARDINALITY_VALUES: tuple[int, ...] = tuple(range(0, 33))
TASK1_THREE_TO_FOUR_MISSING_TRIGGER_BY_PLANE: dict[int, int] = {
    1: 234,
    2: 134,
    3: 124,
    4: 123,
}
TASK1_CHANNEL_COMBINATION_RELATION_TYPES: tuple[str, ...] = (
    "self",
    "same_strip",
    "same_plane",
    "any",
)
TASK1_CHANNEL_COMBINATION_BOUND_SUFFIXES: tuple[str, ...] = (
    "q_sum_left",
    "q_sum_right",
    "q_dif_threshold",
    "t_sum_left",
    "t_sum_right",
    "t_dif_threshold",
)
TASK1_CHANNEL_COMBINATION_COMPONENT_LABELS: tuple[tuple[str, str], ...] = (
    ("q_sum_low", "q_sum lower-bound"),
    ("q_sum_high", "q_sum upper-bound"),
    ("q_dif", "q_dif threshold"),
    ("t_sum_low", "t_sum lower-bound"),
    ("t_sum_high", "t_sum upper-bound"),
    ("t_dif", "t_dif threshold"),
)

FILTER_METRIC_NAMES: tuple[str, ...] = (
    "plane_combination_filter_rows_affected_pct",
    "plane_combination_filter_rows_with_self_relation_failures_pct",
    "plane_combination_filter_rows_with_same_strip_relation_failures_pct",
    "plane_combination_filter_rows_with_same_plane_relation_failures_pct",
    "plane_combination_filter_rows_with_any_relation_failures_pct",
    "valid_lines_in_file_percentage",
    "data_purity_percentage",
    "tt_task1_clean_lt_10_rows_removed_pct",
)
NOISE_CONTROL_RATE_DENOMINATOR_COLUMN = "count_rate_denominator_seconds"
TASK1_NOISE_CONTROL_METRIC_NAMES: tuple[str, ...] = tuple(
    f"plane_combination_filter_rows_with_{selected_count}_selected_offenders_rate_hz"
    for selected_count in TASK1_SELECTED_OFFENDER_CARDINALITY_VALUES
)
TASK1_NOISE_CONTROL_PERCENT_METRIC_NAMES: tuple[str, ...] = tuple(
    f"plane_combination_filter_rows_with_{selected_count}_selected_offenders_pct"
    for selected_count in TASK1_SELECTED_OFFENDER_CARDINALITY_VALUES
)
FILTER_METADATA_ALLOWED_COLUMNS = {
    "filename_base",
    "execution_timestamp",
    "param_hash",
    *FILTER_METRIC_NAMES,
}

filter_metrics: dict[str, float] = {}
TASK1_CHANNEL_KEYS: tuple[tuple[int, str, int], ...] = tuple(
    (plane, side, strip)
    for plane in range(1, 5)
    for side in ("F", "B")
    for strip in range(1, 5)
)
task1_noise_control_efficiency_max_selected_offenders = min(
    TASK1_SELECTED_OFFENDER_CARDINALITY_VALUES[-1],
    max(
        0,
        _coerce_config_value(
            config.get("noise_control_efficiency_max_selected_offenders", 5),
            int,
            5,
        ),
    ),
)
task1_noise_control_efficiency_selected_offender_values: tuple[int, ...] = tuple(
    range(task1_noise_control_efficiency_max_selected_offenders + 1)
)
_TASK1_COMBO_LABEL_PATTERN = re.compile(
    r"^P(?P<plane_a>\d+)S(?P<strip_a>\d+)(?P<side_a>[FB])-P(?P<plane_b>\d+)S(?P<strip_b>\d+)(?P<side_b>[FB])$"
)
TASK1_CHANNEL_COMBINATION_OBSERVABLES: tuple[tuple[str, str], ...] = (
    ("q_sum", "Q semisum"),
    ("q_dif", "Q semidifference"),
    ("t_sum", "T semisum"),
    ("t_dif", "T semidifference"),
)
reprocessing_parameters = pd.DataFrame()
_t_sec = time.perf_counter()
print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")
print("----------------- Data reading and preprocessing ---------------------")
print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")

# Get lists of files in the directories
unprocessed_files = sorted(os.listdir(base_directories["unprocessed_directory"]))
processing_files = sorted(os.listdir(base_directories["processing_directory"]))
completed_files = sorted(os.listdir(base_directories["completed_directory"]))
# Create ALL directories if they don't already exist
for directory in base_directories.values():
    # Skip figure directories at startup; create lazily after selecting a file.
    if directory in (base_directories["base_figure_directory"], base_directories["figure_directory"]):
        continue
    os.makedirs(directory, exist_ok=True)

sync_unprocessed_with_date_range(
    config=config,
    unprocessed_directory=base_directories["unprocessed_directory"],
    out_of_date_directory=base_directories["out_of_date_directory"],
    log_fn=print,
    station_id=station,
    master_config_root=config_root,
)
unprocessed_files = os.listdir(base_directories["unprocessed_directory"])
processing_files = os.listdir(base_directories["processing_directory"])
completed_files = os.listdir(base_directories["completed_directory"])
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

if task1_raw_parquet_input:
    def _task1_raw_parquet_files(file_names: Iterable[str]) -> list[str]:
        return [
            name
            for name in file_names
            if name.startswith("raw_") and name.lower().endswith(".parquet")
        ]

    before_counts = (
        len(unprocessed_files),
        len(processing_files),
        len(completed_files),
    )
    unprocessed_files = _task1_raw_parquet_files(unprocessed_files)
    processing_files = _task1_raw_parquet_files(processing_files)
    completed_files = _task1_raw_parquet_files(completed_files)
    ignored_counts = (
        before_counts[0] - len(unprocessed_files),
        before_counts[1] - len(processing_files),
        before_counts[2] - len(completed_files),
    )
    if any(ignored_counts):
        print(
            "Task 1 ignores non-Task-0 raw parquet files in staging: "
            f"UNPROCESSED={ignored_counts[0]}, "
            f"PROCESSING={ignored_counts[1]}, "
            f"COMPLETED={ignored_counts[2]}."
        )

active_qa_retry_basenames: set[str] = set()
preferred_unprocessed_files: list[str] = []
preferred_processing_files: list[str] = []
preferred_completed_files: list[str] = []
if file_selection_mode == "qa":
    active_qa_retry_basenames = load_active_qa_retry_basenames(
        station,
        repo_root=repo_root,
    )
    preferred_unprocessed_files = filter_filenames_by_qa_retry_basenames(
        unprocessed_files, active_qa_retry_basenames
    )
    preferred_processing_files = filter_filenames_by_qa_retry_basenames(
        processing_files, active_qa_retry_basenames
    )
    preferred_completed_files = filter_filenames_by_qa_retry_basenames(
        completed_files, active_qa_retry_basenames
    )
    if preferred_unprocessed_files or preferred_processing_files or preferred_completed_files:
        unprocessed_files = preferred_unprocessed_files
        processing_files = preferred_processing_files
        completed_files = preferred_completed_files
    print(
        "[FILE_SELECTION] mode=qa QA-preferred candidates: "
        f"UNPROCESSED={len(preferred_unprocessed_files)} "
        f"PROCESSING={len(preferred_processing_files)} "
        f"COMPLETED={len(preferred_completed_files)}"
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
elif prioritize_other_than_qa_files:
    active_qa_retry_basenames = load_active_qa_retry_basenames(
        station,
        repo_root=repo_root,
    )
    preferred_unprocessed_files = filter_filenames_other_than_qa_retry_basenames(
        unprocessed_files,
        active_qa_retry_basenames,
    )
    preferred_processing_files = filter_filenames_other_than_qa_retry_basenames(
        processing_files,
        active_qa_retry_basenames,
    )
    preferred_completed_files = filter_filenames_other_than_qa_retry_basenames(
        completed_files,
        active_qa_retry_basenames,
    )
    if active_qa_retry_basenames:
        print(
            "[QA_PRIORITY] Active QA basenames="
            f"{len(active_qa_retry_basenames)} | preferred non-QA files: "
            f"UNPROCESSED={len(preferred_unprocessed_files)}/{len(unprocessed_files)} "
            f"PROCESSING={len(preferred_processing_files)}/{len(processing_files)} "
            f"COMPLETED={len(preferred_completed_files)}/{len(completed_files)}"
        )
task_1_z_priority_settings = _load_task_1_z_priority_settings(config)
simulated_z_lookup: dict[str, tuple[float, float, float, float]] = {}
if task_1_z_priority_settings.get("enabled", False):
    source_csv = Path(task_1_z_priority_settings.get("source_csv", SIM_PARAMS_DEFAULT))
    simulated_z_lookup = _load_simulated_z_lookup(source_csv)
    print(
        f"[Z_PRIORITY] Enabled with {len(task_1_z_priority_settings.get('priority_abs', set()))} "
        f"configured vector(s); lookup entries={len(simulated_z_lookup)}",
        force=True,
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
        latest_unprocessed = _select_latest_candidate_with_z_priority(
            _preferred_non_qa_or_all(unprocessed_files, preferred_unprocessed_files),
            station,
            task_1_z_priority_settings,
            simulated_z_lookup,
            "UNPROCESSED",
        )
        if latest_unprocessed:
            file_name = latest_unprocessed
            selected_file_source = "unprocessed"
            selected_source_candidates = list(_preferred_non_qa_or_all(unprocessed_files, preferred_unprocessed_files))
            unprocessed_file_path = os.path.join(base_directories["unprocessed_directory"], file_name)
            processing_file_path = os.path.join(base_directories["processing_directory"], file_name)
            completed_file_path = os.path.join(base_directories["completed_directory"], file_name)

            print(f"Processing the newest file in UNPROCESSED: {unprocessed_file_path}")
            print(f"Moving '{file_name}' to PROCESSING...")
            safe_move(unprocessed_file_path, processing_file_path)
            print(f"File moved to PROCESSING: {processing_file_path}")

        else:
            latest_processing = _select_latest_candidate_with_z_priority(
                _preferred_non_qa_or_all(processing_files, preferred_processing_files),
                station,
                task_1_z_priority_settings,
                simulated_z_lookup,
                "PROCESSING",
            )
            if latest_processing:
                file_name = latest_processing
                selected_file_source = "processing"
                selected_source_candidates = list(_preferred_non_qa_or_all(processing_files, preferred_processing_files))
                processing_file_path = os.path.join(base_directories["processing_directory"], file_name)
                completed_file_path = os.path.join(base_directories["completed_directory"], file_name)

                print(f"Processing the newest file already in PROCESSING:\n    {processing_file_path}")
                error_file_path = os.path.join(base_directories["error_directory"], file_name)
                print(f"File '{processing_file_path}' is already in PROCESSING. Moving it temporarily to ERROR for analysis...")
                safe_move(processing_file_path, error_file_path)
                processing_file_path = error_file_path
                print(f"File moved to ERROR: {processing_file_path}")

            else:
                latest_completed = _select_latest_candidate_with_z_priority(
                    _preferred_non_qa_or_all(completed_files, preferred_completed_files),
                    station,
                    task_1_z_priority_settings,
                    simulated_z_lookup,
                    "COMPLETED",
                )
                if latest_completed:
                    file_name = latest_completed
                    selected_file_source = "completed"
                    selected_source_candidates = list(_preferred_non_qa_or_all(completed_files, preferred_completed_files))
                    processing_file_path = os.path.join(base_directories["processing_directory"], file_name)
                    completed_file_path = os.path.join(base_directories["completed_directory"], file_name)

                    print(f"Reprocessing the newest file in COMPLETED: {completed_file_path}")
                    print(f"Moving '{completed_file_path}' to PROCESSING...")
                    safe_move(completed_file_path, processing_file_path)
                    print(f"File moved to PROCESSING: {processing_file_path}")
                else:
                    _exit_without_status_row("No files to process in UNPROCESSED, PROCESSING, or COMPLETED.")

    else:
        if unprocessed_files:
            priority_file = _select_latest_candidate_with_z_priority(
                _preferred_non_qa_or_all(unprocessed_files, preferred_unprocessed_files),
                station,
                task_1_z_priority_settings,
                simulated_z_lookup,
                "UNPROCESSED",
                fallback_to_latest=False,
            )
            if priority_file is not None:
                file_name = priority_file
                selected_file_source = "unprocessed"
                selected_source_candidates = list(_preferred_non_qa_or_all(unprocessed_files, preferred_unprocessed_files))
                unprocessed_file_path = os.path.join(base_directories["unprocessed_directory"], file_name)
                processing_file_path = os.path.join(base_directories["processing_directory"], file_name)
                completed_file_path = os.path.join(base_directories["completed_directory"], file_name)
                print(f"Moving prioritized '{file_name}' to PROCESSING...")
                safe_move(unprocessed_file_path, processing_file_path)
                print(f"File moved to PROCESSING: {processing_file_path}")
            else:
                print("Selecting a random file in UNPROCESSED...")
                selected_file_source = "unprocessed"
                selected_source_candidates = list(_preferred_non_qa_or_all(unprocessed_files, preferred_unprocessed_files))
                file_name = random.choice(selected_source_candidates)
                unprocessed_file_path = os.path.join(base_directories["unprocessed_directory"], file_name)
                processing_file_path = os.path.join(base_directories["processing_directory"], file_name)
                completed_file_path = os.path.join(base_directories["completed_directory"], file_name)

                print(f"Moving '{file_name}' to PROCESSING...")
                safe_move(unprocessed_file_path, processing_file_path)
                print(f"File moved to PROCESSING: {processing_file_path}")

        elif processing_files:
            priority_file = _select_latest_candidate_with_z_priority(
                _preferred_non_qa_or_all(processing_files, preferred_processing_files),
                station,
                task_1_z_priority_settings,
                simulated_z_lookup,
                "PROCESSING",
                fallback_to_latest=False,
            )
            if priority_file is not None:
                file_name = priority_file
                selected_file_source = "processing"
                selected_source_candidates = list(_preferred_non_qa_or_all(processing_files, preferred_processing_files))
                processing_file_path = os.path.join(base_directories["processing_directory"], file_name)
                completed_file_path = os.path.join(base_directories["completed_directory"], file_name)
                print(f"Processing prioritized file in PROCESSING: {processing_file_path}")
                error_file_path = os.path.join(base_directories["error_directory"], file_name)
                print(f"File '{processing_file_path}' is already in PROCESSING. Moving it temporarily to ERROR for analysis...")
                safe_move(processing_file_path, error_file_path)
                processing_file_path = error_file_path
                print(f"File moved to ERROR: {processing_file_path}")
            else:
                print("Selecting a random file in PROCESSING...")
                selected_file_source = "processing"
                selected_source_candidates = list(_preferred_non_qa_or_all(processing_files, preferred_processing_files))
                file_name = random.choice(selected_source_candidates)
                processing_file_path = os.path.join(base_directories["processing_directory"], file_name)
                completed_file_path = os.path.join(base_directories["completed_directory"], file_name)

                print(f"Processing file in PROCESSING: {processing_file_path}")
                error_file_path = os.path.join(base_directories["error_directory"], file_name)
                print(f"File '{processing_file_path}' is already in PROCESSING. Moving it temporarily to ERROR for analysis...")
                safe_move(processing_file_path, error_file_path)
                processing_file_path = error_file_path
                print(f"File moved to ERROR: {processing_file_path}")

        elif completed_files:
            if complete_reanalysis:
                priority_file = _select_latest_candidate_with_z_priority(
                    _preferred_non_qa_or_all(completed_files, preferred_completed_files),
                    station,
                    task_1_z_priority_settings,
                    simulated_z_lookup,
                    "COMPLETED",
                    fallback_to_latest=False,
                )
                if priority_file is not None:
                    file_name = priority_file
                    selected_file_source = "completed"
                    selected_source_candidates = list(_preferred_non_qa_or_all(completed_files, preferred_completed_files))
                    completed_file_path = os.path.join(base_directories["completed_directory"], file_name)
                    processing_file_path = os.path.join(base_directories["processing_directory"], file_name)
                    print(f"Moving prioritized '{file_name}' to PROCESSING...")
                    safe_move(completed_file_path, processing_file_path)
                    print(f"File moved to PROCESSING: {processing_file_path}")
                else:
                    print("Selecting a random file in COMPLETED...")
                    selected_file_source = "completed"
                    selected_source_candidates = list(_preferred_non_qa_or_all(completed_files, preferred_completed_files))
                    file_name = random.choice(selected_source_candidates)
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
        "basename_no_ext": _task1_output_basename_from_input_stem(os.path.splitext(file_name)[0]),
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
                "basename_no_ext": _task1_output_basename_from_input_stem(os.path.splitext(joined_file_name)[0]),
            }
        )
elif joined_analysis_files > 1:
    print(
        "Joined analysis not expanded for this selection "
        f"(source={selected_file_source or 'unknown'}, user_file_selection={user_file_selection})."
    )

# This is for all cases
file_path = processing_file_path
print(f"File to be processed, complete original path: {file_path}")
the_filename = os.path.basename(file_path)
print(f"File to process: {the_filename}")
basename_no_ext, file_extension = os.path.splitext(the_filename)
print(f"File basename (no extension): {basename_no_ext}")
basename_no_ext = _task1_output_basename_from_input_stem(basename_no_ext)
if basename_no_ext != os.path.splitext(the_filename)[0]:
    print(f"Task 1 output basename after raw_ prefix removal: {basename_no_ext}")
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

analysis_date = datetime.now().strftime("%Y-%m-%d")
# print(f"Analysis date and time: {analysis_date}")

# Modify the time of the processing file to the current time so it looks fresh
now = time.time()
os.utime(processing_file_path, (now, now))

# Check the station number in the datafile
# It might be that the data header is, instead of mi01: minI, which is the same, in that
# case consider minI as mi01
try:
    station_name_for_check = file_name[4:] if file_name.startswith("raw_") else file_name
    station_label = station_name_for_check[3]  # 4th character (index 3)
    print(f'File station number is: {station_label}')

    if station_label == "I":
        print("Station label is 'I', interpreting as station 1.")
        station_label = int(1)

    file_station_number = int(station_label)  # 4th character (index 3)
    if file_station_number != int(station):
        print(f'File station number is: {file_station_number}, it does not match.')
        # Move the file to the ERROR directory
        error_file_path = os.path.join(base_directories["error_directory"], file_name)
        print(f"Moving file '{file_name}' to ERROR directory: {error_file_path}")
        process_file(file_path, error_file_path)
        sys.exit(f"File '{file_name}' does not belong to station {station}. Exiting.")
except ValueError:
    sys.exit(f"Invalid station number in file '{file_name}'. Exiting.")

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

# ------------------------------------------------------------------------------------------------------

# Move rejected_file to the rejected file folder
rejected_file = os.path.join(base_directories["rejected_files_directory"], f"temp_file_{date_execution}.csv")

print(f"Rejected-row log is {rejected_file}")
EXPECTED_COLUMNS = EXPECTED_COLUMNS_config  # Expected number of columns

ZERO_TOKEN_PATTERN = re.compile(r"0000\.0000")
LEADING_ZERO_PATTERN = re.compile(r"\b0+([0-9]+)")
MULTI_SPACE_PATTERN = re.compile(r" +")
XYEAR_PATTERN = re.compile(r"X(20\d{2})")
NEG_GAP_PATTERN = re.compile(r"(\w)-(\d)")
MALFORMED_NUMBER_PATTERN = re.compile(r"-?\d+\.\d+\.\d+")
VALID_YEARS = set(range(1999, 2100))

T_FRONT_PATTERN = re.compile(r"^T\d+_F_\d+$")
T_BACK_PATTERN = re.compile(r"^T\d+_B_\d+$")
Q_FRONT_PATTERN = re.compile(r"^Q\d+_F_\d+$")
Q_BACK_PATTERN = re.compile(r"^Q\d+_B_\d+$")
# -----------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------
# TASK 1 start
# -----------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------------------

# Process the input file(s)
joined_source_file_column = "__task1_joined_source_file__"
joined_source_basename_column = "__task1_joined_source_basename__"
joined_frames: list[pd.DataFrame] = []
read_lines = 0
written_lines = 0
for joined_record in joined_input_records:
    joined_path = joined_record["processing_file_path"]
    joined_stem = Path(joined_path).stem
    joined_is_task0_raw_parquet = (
        Path(joined_path).suffix.lower() == ".parquet"
        and joined_stem.startswith("raw_")
    )
    if joined_is_task0_raw_parquet:
        joined_frame = pd.read_parquet(joined_path)
        joined_frame = canonicalize_step1_columns(joined_frame)
        joined_frame = add_topology_task1_channel(joined_frame)
        if limit:
            joined_frame = joined_frame.head(int(limit_number)).copy()
        if "datetime" in joined_frame.columns:
            joined_frame["datetime"] = pd.to_datetime(joined_frame["datetime"], errors="coerce")
        if "acquisition_type" not in joined_frame.columns:
            if "column_6" in joined_frame.columns:
                joined_frame = joined_frame.rename(columns={"column_6": "acquisition_type"})
            else:
                raise ValueError(f"Task 1 raw parquet is missing acquisition_type: {joined_path}")
        joined_read_lines = len(joined_frame)
        joined_written_lines = len(joined_frame)
    else:
        raise ValueError(
            "Task 1 now requires Task 0 raw parquet input; refusing non-raw-parquet file: "
            f"{joined_path}"
        )
    read_lines += int(joined_read_lines)
    written_lines += int(joined_written_lines)
    if not joined_frame.empty:
        joined_frame.loc[:, joined_source_file_column] = joined_record["file_name"]
        joined_frame.loc[:, joined_source_basename_column] = joined_record["basename_no_ext"]
        joined_frames.append(joined_frame)
    print(
        "Raw dataframe loaded for Task 1 joined analysis: "
        f"{joined_path} read_lines={joined_read_lines} valid_lines={joined_written_lines}"
    )
if joined_frames:
    working_df = pd.concat(joined_frames, ignore_index=True, sort=False)
else:
    working_df = pd.DataFrame()
joined_analysis_active = len(joined_input_records) > 1
if joined_analysis_active:
    print(
        "Joined analysis active: "
        f"files={len(joined_input_records)} total_rows={len(working_df)} primary={file_name}"
    )
global_variables["joined_analysis_files_requested"] = int(joined_analysis_files)
global_variables["joined_analysis_files_used"] = int(len(joined_input_records))
global_variables["joined_analysis_time_tolerance_hours"] = float(joined_analysis_time_tolerance_hours)

if written_lines == 0:
    print("No valid lines found after preprocessing; skipping file.")
    if user_file_selection == False:
        for joined_record in joined_input_records:
            joined_processing_path = joined_record["processing_file_path"]
            error_file_path = os.path.join(base_directories["error_directory"], joined_record["file_name"])
            if os.path.exists(joined_processing_path):
                process_file(joined_processing_path, error_file_path)
    sys.exit("Empty temp file generated; no valid data to process.")

# Print the number of rows in input
print(f"\nOriginal file has {read_lines} lines.")
print(f"Processed file has {written_lines} lines.")
if read_lines > 0:
    valid_lines_in_dat_file = written_lines / read_lines * 100
else:
    valid_lines_in_dat_file = 0.0
    print("Warning: input file has zero lines; setting valid line percentage to 0.0.")
print(f"--> A {valid_lines_in_dat_file:.2f}% of the lines were valid.\n")

global_variables['valid_lines_in_file_percentage'] =  valid_lines_in_dat_file

# FINAL plot block moved out of the runtime flow: event_total_charge_raw
pass

_prof["s_data_read_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()
_t_filter_date_select = _t_sec
print("----------------------------------------------------------------------")
print("-------------------------- Filter 1: by date -------------------------")
print("----------------------------------------------------------------------")

task1_datetime_in_range_mask = working_df["datetime"].between(left_limit_time, right_limit_time)
if str(station) == "0" and "param_hash" in working_df.columns:
    simulated_param_hash_mask = working_df["param_hash"].fillna("").astype(str).str.strip().ne("")
    task1_datetime_in_range_mask = task1_datetime_in_range_mask | simulated_param_hash_mask
working_df.loc[:, "filter_task1_datetime_in_range_pass"] = task1_datetime_in_range_mask.to_numpy(dtype=bool)
if not pd.api.types.is_datetime64_any_dtype(working_df["datetime"]):
    raise ValueError("The index is not a DatetimeIndex. Check 'datetime' column formatting.")

if working_df.empty:
    print("No valid rows found after reading Task 0 raw parquet input.")
    sys.exit(1)

if "acquisition_type" not in working_df.columns:
    raise ValueError(
        "Task 1 expected Task 0 raw parquet input with an acquisition_type column."
    )

bad_acquisition_type_mask = working_df["acquisition_type"] != 1
if bad_acquisition_type_mask.any():
    bad_counts = working_df.loc[
        bad_acquisition_type_mask, "acquisition_type"
    ].value_counts(dropna=False)
    raise ValueError(
        "Task 1 expected only coincidence rows from Task 0 raw_*.parquet input "
        "with acquisition_type == 1, but found non-1 acquisition_type values:\n"
        f"{bad_counts}"
    )

print(working_df["acquisition_type"].value_counts())

# Note that the middle between start and end time could also be taken. This is for calibration storage.
datetime_series = pd.to_datetime(working_df["datetime"], errors="coerce").dropna()
if datetime_series.empty:
    print(
        f"Warning: No valid datetime rows found in {file_name}; moving file to ERROR and skipping."
    )
    if not user_file_selection:
        error_file_path = os.path.join(base_directories["error_directory"], file_name)
        print(f"Moving file '{file_name}' to ERROR directory: {error_file_path}")
        process_file(file_path, error_file_path)
    sys.exit(0)
datetime_value = datetime_series.iloc[0]
end_datetime_value = datetime_series.iloc[-1]

start_time = datetime_value
end_time = end_datetime_value
datetime_str = str(datetime_value)
save_filename_suffix = datetime_str.replace(' ', "_").replace(':', ".").replace('-', ".")
_prof["s_filter_date_select_s"] = round(time.perf_counter() - _t_filter_date_select, 2)
_t_geometry_resolve = time.perf_counter()

# -------------------------------------------------------------------------------
# ------------ Input file and data managing to select configuration -------------
# -------------------------------------------------------------------------------

conf_value = None
z_source = "unset"
task1_processing_path = Path(file_path)
task1_processing_suffix = task1_processing_path.suffix.lower()
simulated_z_positions, simulated_param_hash = resolve_simulated_z_positions(
    basename_no_ext,
    Path(base_directory),
    dat_path=task1_processing_path if task1_processing_suffix == ".dat" else None,
    parquet_path=task1_processing_path if task1_processing_suffix == ".parquet" else None,
)
if simulated_param_hash:
    global_variables["param_hash"] = simulated_param_hash

is_simulated_file = basename_no_ext.startswith("mi00")
used_input_file = False

if is_simulated_file:
    if simulated_param_hash:
        print(f"Simulated param_hash resolved: {simulated_param_hash}")
    else:
        print("Warning: Simulated param_hash missing; default z_positions will be used.")

if is_simulated_file and simulated_z_positions is None:
    print("Warning: Simulated file missing param_hash; using default z_positions.")
    found_matching_conf = False
    z_positions = np.array([0, 150, 300, 450])  # In mm
    z_source = "simulated_default_missing_param_hash"
elif simulated_z_positions is not None:
    z_positions = np.array(simulated_z_positions, dtype=float)
    found_matching_conf = True
    print(f"Using simulated z_positions from param_hash={simulated_param_hash}")
    z_source = "simulated_param_hash"
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
        try:
            conf_value = float(selected_conf.get("conf"))
        except (TypeError, ValueError):
            conf_value = None
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
            try:
                conf_value = float(selected_conf.get("conf"))
            except (TypeError, ValueError):
                conf_value = None
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

print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")
print(f"------------- Starting date is {save_filename_suffix} -------------------") # This is longer so it displays nicely
print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")

# Defining the directories that will store the data
save_full_filename = f"full_list_events_{save_filename_suffix}.txt"
save_filename = f"list_events_{save_filename_suffix}.txt"
save_pdf_filename = f"mingo{str(station).zfill(2)}_task1_{basename_no_ext}_{date_execution}.pdf"

save_pdf_path = os.path.join(base_directories["pdf_directory"], save_pdf_filename)
_prof["s_geometry_resolve_s"] = round(time.perf_counter() - _t_geometry_resolve, 2)
_t_frame_init = time.perf_counter()

# Check if the file exists and its size
if os.path.exists(save_filename):
    if os.path.getsize(save_filename) >= 1 * 1024 * 1024: # Bigger than 1MB
        if force_replacement == False:
            print("Datafile found and it looks completed. Exiting...")
            sys.exit()  # Exit the script
        else:
            print("Datafile found and it is not empty, but 'force_replacement' is True, so it creates new datafiles anyway.")
    else:
        print("Datafile found, but empty.")

column_indices = {
    'T1_F': range(55, 59), 'T1_B': range(59, 63), 'Q1_F': range(63, 67), 'Q1_B': range(67, 71),
    'T2_F': range(39, 43), 'T2_B': range(43, 47), 'Q2_F': range(47, 51), 'Q2_B': range(51, 55),
    'T3_F': range(23, 27), 'T3_B': range(27, 31), 'Q3_F': range(31, 35), 'Q3_B': range(35, 39),
    'T4_F': range(7, 11), 'T4_B': range(11, 15), 'Q4_F': range(15, 19), 'Q4_B': range(19, 23)
}

channel_source_columns: list[str] = []
channel_rename_map: dict[str, str] = {}
named_channel_columns: list[str] = []
for key, idx_range in column_indices.items():
    quantity = "t" if key.startswith("T") else "q"
    plane = int(key[1])
    endpoint = "ef" if key.endswith("_F") else "eb"
    for i, col_idx in enumerate(idx_range, start=1):
        source_column = f"column_{col_idx}"
        target_column = f"p{plane}_s{i}_{endpoint}_{quantity}"
        channel_source_columns.append(source_column)
        channel_rename_map[source_column] = target_column
        named_channel_columns.append(target_column)

if all(column in working_df.columns for column in named_channel_columns):
    # Task 0 raw parquet already owns the detector channel naming.
    channel_source_columns = named_channel_columns
    channel_rename_map = {}
elif not all(column in working_df.columns for column in channel_source_columns):
    missing_named = [column for column in named_channel_columns if column not in working_df.columns]
    missing_legacy = [column for column in channel_source_columns if column not in working_df.columns]
    raise ValueError(
        "Task 1 input is missing detector channel columns. "
        f"missing_named={missing_named[:8]} missing_legacy={missing_legacy[:8]}"
    )

task1_join_source_columns = [
    col
    for col in (joined_source_file_column, joined_source_basename_column)
    if col in working_df.columns
]
task1_preserved_raw_columns = [
    col
    for col in ("tt_task0_acq", "tt_task0_raw", "param_hash", "acquisition_type", "filter_task1_datetime_in_range_pass")
    if col in working_df.columns
]
if keep_all_columns_output:
    working_df = working_df.copy()
else:
    working_df = working_df.filter(
        items=["event_id", "datetime", *task1_join_source_columns, *task1_preserved_raw_columns, *channel_source_columns],
    ).copy()
working_df = working_df.rename(columns=channel_rename_map)
# Track rows that later drop out of Task 1 so their original indexed values stay inspectable.
diagnostic_removed_rows_df = working_df.iloc[0:0].copy()
tracking_base_index = working_df.index.copy()
original_columns_store: dict[str, pd.Series] = {}
channel_pair_plot_reference_df = pd.DataFrame(index=working_df.index)
original_number_of_events = len(working_df)
if status_execution_date is not None:
    update_status_progress(
        csv_path_status,
        filename_base=status_filename_base,
        execution_date=status_execution_date,
        completion_fraction=0.5,
        param_hash=str(global_variables.get("param_hash", "")),
    )

snapshot_original_columns_once(working_df, ["datetime"])
working_df = working_df.rename(columns=lambda col: col.replace("_diff_", "_dif_"))

# print("Columns right after initial assignment (before tt_task0_raw computation):")
# for col in working_df.columns:
#     print(f" - {col}")

# ----------------------------------------------------------------------------------
# Count the number of non-zero entries per channel in the whole dataframe ----------
# ----------------------------------------------------------------------------------

# Count per each column the number of non-zero entries and save it in a column of
# global_variables called TX_F_Y_entries or TX_B_Y_entries

# Count for main dataframe (non-self-trigger)
for key, idx_range in column_indices.items():
    quantity = "t" if key.startswith("T") else "q"
    plane = int(key[1])
    endpoint = "ef" if key.endswith("_F") else "eb"
    for i in range(1, len(idx_range) + 1):
        colname = f"p{plane}_s{i}_{endpoint}_{quantity}"
        if colname not in working_df.columns:
            continue
        count = (working_df[colname] != 0).sum()
        global_var_name = f"{colname}_entries_original"
        global_variables[global_var_name] = count
_prof["s_frame_init_s"] = round(time.perf_counter() - _t_frame_init, 2)
_t_tt_task0_raw_overview = time.perf_counter()
if "tt_task0_raw" in working_df.columns:
    working_df.loc[:, "tt_task0_raw"] = pd.to_numeric(working_df["tt_task0_raw"], errors="coerce").fillna(0).astype(int)
    print("Task 1 using tt_task0_raw provided by Task 0 raw parquet.")
else:
    print("Warning: Task 1 input lacks tt_task0_raw; computing fallback tt_task0_raw for backward compatibility.")
    working_df = compute_tt(working_df, "tt_task0_raw")

tt_task0_raw_counts = working_df["tt_task0_raw"].value_counts()

raw_channel_patterns = build_task1_channel_pattern_series(working_df)
store_pattern_rates(pattern_metadata, raw_channel_patterns, "raw_channel_pattern", working_df)

# Always compute raw-stage channel contagion metrics for metadata.
raw_channel_matrix_data = _compute_channel_conditional_matrix(working_df)
_store_channel_contagion_metrics_variant(
    "global_raw",
    raw_channel_matrix_data,
)
raw_channel_by_tt_data = _compute_channel_conditional_matrix_for_tt(working_df, "tt_task0_raw", 1234)
_store_channel_contagion_metrics_variant(
    "by_tt_task0_raw",
    raw_channel_by_tt_data,
)

# Print the counts of each tt_task0_raw value and the percentage
total_events = len(working_df)
print("Raw TT counts and percentages:")
for tt_value, count in sorted(tt_task0_raw_counts.items()):
    percentage = (count / total_events) * 100
    print(f"  Raw TT {tt_value}: {count} events ({percentage:.2f}%)")

_task1_self_plot_limits = task1_channel_combination_limits_by_relation.get("self", {})
T_F_left_pre_cal = float(_task1_self_plot_limits.get("t_sum_left", channel_combination_t_sum_left))
T_F_right_pre_cal = float(_task1_self_plot_limits.get("t_sum_right", channel_combination_t_sum_right))
T_B_left_pre_cal = T_F_left_pre_cal
T_B_right_pre_cal = T_F_right_pre_cal
Q_F_left_pre_cal = float(_task1_self_plot_limits.get("q_sum_left", channel_combination_q_sum_left))
Q_F_right_pre_cal = float(_task1_self_plot_limits.get("q_sum_right", channel_combination_q_sum_right))
Q_B_left_pre_cal = Q_F_left_pre_cal
Q_B_right_pre_cal = Q_F_right_pre_cal
_prof["s_tt_task0_raw_overview_s"] = round(time.perf_counter() - _t_tt_task0_raw_overview, 2)

_debug_plot_filter_group(
    working_df,
    [col for col in working_df.columns if re.match(r"^[TQ][1-4]_[FB]_[1-4]$", col)] + ["tt_task0_raw"],
    None,
    "incoming parquet: main channels and tt_task0_raw",
    tag="NON-TUNABLE",
    max_cols_per_fig=20,
)

if task1_plot_enabled("tt_task0_raw_overview"):
    event_counts = working_df['tt_task0_raw'].value_counts()

    plt.figure(figsize=(10, 6))
    event_counts.plot(kind='bar', alpha=0.7)
    plt.title(f'Number of Events per Raw TT Label, {start_time}')
    plt.xlabel('Raw TT Label')
    plt.ylabel('Number of Events')
    plt.xticks(rotation=45)
    plt.tight_layout()
    if save_plots:
        final_filename = f'{fig_idx}_raw_TT.png'
        fig_idx += 1

        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format='png')

    if show_plots: plt.show()
    plt.close()

# --- Pre-filter (raw) channel contamination matrices ---
if task1_plot_enabled("channel_contamination_matrix_32_raw"):
    fig_idx = _plot_channel_contamination_global(
        working_df, "raw", fig_idx, base_directories["figure_directory"],
        save_plots, show_plots, plot_list,
    )

if task1_plot_enabled("channel_contagion_by_tt_task0_raw"):
    fig_idx = _plot_channel_contagion_by_tt(
        working_df, "tt_task0_raw", "raw", fig_idx, base_directories["figure_directory"],
        save_plots, show_plots, plot_list,
    )

if task1_plot_enabled("channel_histograms_raw"):
    # Create the grand figure for T values
    fig_T, axes_T = plt.subplots(4, 4, figsize=(20, 10))  # Adjust the layout as necessary
    axes_T = axes_T.flatten()

    for plane in range(1, 5):
        for strip in range(1, 5):
            panel_idx = (plane - 1) * 4 + (strip - 1)
            col_F = f'p{plane}_s{strip}_ef_t'
            col_B = f'p{plane}_s{strip}_eb_t'
            y_F = working_df[col_F]
            y_B = working_df[col_B]

            # Plot histograms with T-specific clipping and bins
            axes_T[panel_idx].hist(y_F[(y_F != 0) & (y_F > T_clip_min) & (y_F < T_clip_max)],
                                 bins=num_bins, alpha=0.5, label=f'{col_F} (F)')
            axes_T[panel_idx].hist(y_B[(y_B != 0) & (y_B > T_clip_min) & (y_B < T_clip_max)],
                                 bins=num_bins, alpha=0.5, label=f'{col_B} (B)')
            axes_T[panel_idx].axvline(x=T_F_left_pre_cal, color='red', linestyle='--', label='T_left_pre_cal')
            axes_T[panel_idx].axvline(x=T_F_right_pre_cal, color='blue', linestyle='--', label='T_right_pre_cal')
            axes_T[panel_idx].set_title(f'{col_F} vs {col_B}')
            axes_T[panel_idx].legend()

            if log_scale:
                axes_T[panel_idx].set_yscale('log')  # For T values

    plt.tight_layout()
    plt.subplots_adjust(top=0.9)
    plt.suptitle(f"Grand Figure for T values, mingo0{station}\n{start_time}", fontsize=16)

    if save_plots:
        final_filename = f'{fig_idx}_grand_figure_T.png'
        fig_idx += 1

        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format='png')

    if show_plots: plt.show()
    plt.close(fig_T)

    # Create the grand figure for Q values
    fig_Q, axes_Q = plt.subplots(4, 4, figsize=(20, 10))  # Adjust the layout as necessary
    axes_Q = axes_Q.flatten()

    for plane in range(1, 5):
        for strip in range(1, 5):
            panel_idx = (plane - 1) * 4 + (strip - 1)
            col_F = f'p{plane}_s{strip}_ef_q'
            col_B = f'p{plane}_s{strip}_eb_q'
            y_F = working_df[col_F]
            y_B = working_df[col_B]

            # Plot histograms with Q-specific clipping and bins
            axes_Q[panel_idx].hist(y_F[(y_F != 0) & (y_F > Q_clip_min) & (y_F < Q_clip_max)],
                                 bins=num_bins, alpha=0.5, label=f'{col_F} (F)')
            axes_Q[panel_idx].hist(y_B[(y_B != 0) & (y_B > Q_clip_min) & (y_B < Q_clip_max)],
                                 bins=num_bins, alpha=0.5, label=f'{col_B} (B)')
            axes_Q[panel_idx].axvline(x=Q_F_left_pre_cal, color='red', linestyle='--', label='Q_left_pre_cal')
            axes_Q[panel_idx].axvline(x=Q_F_right_pre_cal, color='blue', linestyle='--', label='Q_right_pre_cal')
            axes_Q[panel_idx].set_title(f'{col_F} vs {col_B}')
            axes_Q[panel_idx].legend()

            if log_scale:
                axes_Q[panel_idx].set_yscale('log')  # For Q values

    plt.tight_layout()
    plt.subplots_adjust(top=0.9)
    plt.suptitle(f"Grand Figure for Q values, mingo0{station}\n{start_time}", fontsize=16)

    if save_plots:
        final_filename = f'{fig_idx}_grand_figure_Q.png'
        fig_idx += 1

        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format='png')

    if show_plots: plt.show()
    plt.close(fig_Q)

if task1_plot_enabled("tq_scatter_raw"):
    # Initialize figure and axes for scatter plot of Time vs Charge
    fig_TQ, axes_TQ = plt.subplots(4, 4, figsize=(20, 10))  # Adjust the layout as necessary
    axes_TQ = axes_TQ.flatten()

    # Iterate over each plane (T1, T2, T3, T4)
    for plane in range(1, 5):
        for strip in range(1, 5):
            panel_idx = (plane - 1) * 4 + (strip - 1)
            col_F = f'p{plane}_s{strip}_ef_t'  # Time F column
            col_B = f'p{plane}_s{strip}_eb_t'  # Time B column

            y_F = working_df[col_F]  # Time values for front
            y_B = working_df[col_B]  # Time values for back

            charge_col_F = f'p{plane}_s{strip}_ef_q'  # Corresponding charge column for front
            charge_col_B = f'p{plane}_s{strip}_eb_q'  # Corresponding charge column for back

            charge_F = working_df[charge_col_F]  # Charge values for front
            charge_B = working_df[charge_col_B]  # Charge values for back

            # Apply clipping ranges to the data
            mask_F = (y_F != 0) & (y_F > T_clip_min) & (y_F < T_clip_max) & (charge_F > Q_clip_min) & (charge_F < Q_clip_max)
            mask_B = (y_B != 0) & (y_B > T_clip_min) & (y_B < T_clip_max) & (charge_B > Q_clip_min) & (charge_B < Q_clip_max)

            # Plot scatter plots for Time F vs Charge F and Time B vs Charge B
            axes_TQ[panel_idx].scatter(charge_F[mask_F], y_F[mask_F], alpha=0.5, label=f'{col_F} (F)', color='green', s=1)
            axes_TQ[panel_idx].scatter(charge_B[mask_B], y_B[mask_B], alpha=0.5, label=f'{col_B} (B)', color='orange', s=1)

            # Plot threshold lines for time and charge
            axes_TQ[panel_idx].axhline(y=T_F_left_pre_cal, color='red', linestyle='--', label='T_left_pre_cal')
            axes_TQ[panel_idx].axhline(y=T_F_right_pre_cal, color='blue', linestyle='--', label='T_right_pre_cal')
            axes_TQ[panel_idx].axvline(x=Q_F_left_pre_cal, color='red', linestyle='--', label='Q_left_pre_cal')
            axes_TQ[panel_idx].axvline(x=Q_F_right_pre_cal, color='blue', linestyle='--', label='Q_right_pre_cal')

            axes_TQ[panel_idx].set_title(f'{col_F} vs {col_B}')
            axes_TQ[panel_idx].legend()

    # Adjust the layout and title
    plt.tight_layout()
    plt.subplots_adjust(top=0.9)
    plt.suptitle(f"Scatter Plot for T vs Q values, mingo0{station}\n{start_time}", fontsize=16)

    # Save the plot
    if save_plots:
        final_filename = f'{fig_idx}_scatter_plot_TQ.png'
        fig_idx += 1
        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format='png')

    # Show the plot if requested
    if show_plots:
        plt.show()

    # Close the plot to avoid excessive memory usage
    plt.close(fig_TQ)

# FINAL plot block moved out of the runtime flow: tq_scatter_raw_by_tt
pass

# -----------------------------------------------------------------------------

_prof["s_filter_date_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()
print("----------------------------------------------------------------------")
print("------------------ Filter 1.1.1: uncalibrated data -------------------")
print("----------------------------------------------------------------------")

# FILTER 2: TF, TB, QF, QB PRECALIBRATED THRESHOLDS --> 0 if out --------------

snapshot_original_columns_once(
    working_df,
    [col for col in working_df.columns if working_df[col].isna().any()],
)
working_df.fillna(0, inplace=True)
T_F_cols = collect_columns(working_df.columns, T_FRONT_PATTERN)
T_B_cols = collect_columns(working_df.columns, T_BACK_PATTERN)
Q_F_cols = collect_columns(working_df.columns, Q_FRONT_PATTERN)
Q_B_cols = collect_columns(working_df.columns, Q_BACK_PATTERN)
channel_pair_plot_reference_columns = [
    col
    for col in ["tt_task0_raw", *T_F_cols, *T_B_cols, *Q_F_cols, *Q_B_cols]
    if col in working_df.columns
]
channel_pair_plot_reference_df = working_df.loc[:, channel_pair_plot_reference_columns].copy()

_debug_plot_filter_group(
    working_df,
    T_F_cols + T_B_cols,
    [T_F_left_pre_cal, T_F_right_pre_cal],
    "T_side_left/right_pre_cal",
)
_debug_plot_filter_group(
    working_df,
    Q_F_cols + Q_B_cols,
    [Q_F_left_pre_cal, Q_F_right_pre_cal],
    "Q_side_left/right_pre_cal",
)

if task1_plot_enabled("channel_histograms_filtered"):
    # Create the grand figure for T values
    fig_T, axes_T = plt.subplots(4, 4, figsize=(20, 10))  # Adjust the layout as necessary
    axes_T = axes_T.flatten()

    for plane in range(1, 5):
        for strip in range(1, 5):
            panel_idx = (plane - 1) * 4 + (strip - 1)
            col_F = f'p{plane}_s{strip}_ef_t'
            col_B = f'p{plane}_s{strip}_eb_t'
            y_F = working_df[col_F]
            y_B = working_df[col_B]

            # Plot histograms with T-specific clipping and bins
            axes_T[panel_idx].hist(y_F[(y_F != 0) & (y_F > T_clip_min) & (y_F < T_clip_max)],
                                 bins=num_bins, alpha=0.5, label=f'{col_F} (F)')
            axes_T[panel_idx].hist(y_B[(y_B != 0) & (y_B > T_clip_min) & (y_B < T_clip_max)],
                                 bins=num_bins, alpha=0.5, label=f'{col_B} (B)')
            axes_T[panel_idx].set_title(f'{col_F} vs {col_B}')
            axes_T[panel_idx].legend()

            if log_scale:
                axes_T[panel_idx].set_yscale('log')  # For T values

    plt.tight_layout()
    plt.subplots_adjust(top=0.9)
    plt.suptitle(f"Grand Figure for T values, mingo0{station}\n{start_time}", fontsize=16)

    if save_plots:
        final_filename = f'{fig_idx}_grand_figure_T.png'
        fig_idx += 1

        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format='png')

    if show_plots: plt.show()
    plt.close(fig_T)

    # Create the grand figure for Q values
    fig_Q, axes_Q = plt.subplots(4, 4, figsize=(20, 10))  # Adjust the layout as necessary
    axes_Q = axes_Q.flatten()

    for plane in range(1, 5):
        for strip in range(1, 5):
            panel_idx = (plane - 1) * 4 + (strip - 1)
            col_F = f'p{plane}_s{strip}_ef_q'
            col_B = f'p{plane}_s{strip}_eb_q'
            y_F = working_df[col_F]
            y_B = working_df[col_B]

            # Plot histograms with Q-specific clipping and bins
            axes_Q[panel_idx].hist(y_F[(y_F != 0) & (y_F > Q_clip_min) & (y_F < Q_clip_max)],
                                 bins=num_bins, alpha=0.5, label=f'{col_F} (F)')
            axes_Q[panel_idx].hist(y_B[(y_B != 0) & (y_B > Q_clip_min) & (y_B < Q_clip_max)],
                                 bins=num_bins, alpha=0.5, label=f'{col_B} (B)')
            axes_Q[panel_idx].set_title(f'{col_F} vs {col_B}')
            axes_Q[panel_idx].legend()

            if log_scale:
                axes_Q[panel_idx].set_yscale('log')  # For Q values

    plt.tight_layout()
    plt.subplots_adjust(top=0.9)
    plt.suptitle(f"Grand Figure for Q values, mingo0{station}\n{start_time}", fontsize=16)

    if save_plots:
        final_filename = f'{fig_idx}_grand_figure_Q.png'
        fig_idx += 1

        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format='png')

    if show_plots: plt.show()
    plt.close(fig_Q)

# Per trigger type
create_super_essential_plots = False

if create_plots or create_super_essential_plots:

    for tt_value in sorted(working_df['tt_task0_raw'].unique()):
        filtered_df = working_df[working_df['tt_task0_raw'] == tt_value]

        # Create the grand figure for T values
        fig_T, axes_T = plt.subplots(4, 4, figsize=(20, 10))  # Adjust the layout as necessary
        axes_T = axes_T.flatten()

        for plane in range(1, 5):
            for strip in range(1, 5):
                panel_idx = (plane - 1) * 4 + (strip - 1)
                col_F = f'p{plane}_s{strip}_ef_t'
                col_B = f'p{plane}_s{strip}_eb_t'
                y_F = filtered_df[col_F]
                y_B = filtered_df[col_B]

                # Plot histograms with T-specific clipping and bins
                axes_T[panel_idx].hist(y_F[(y_F != 0) & (y_F > T_clip_min) & (y_F < T_clip_max)],
                                    bins=num_bins, alpha=0.5, label=f'{col_F} (F)')
                axes_T[panel_idx].hist(y_B[(y_B != 0) & (y_B > T_clip_min) & (y_B < T_clip_max)],
                                    bins=num_bins, alpha=0.5, label=f'{col_B} (B)')
                axes_T[panel_idx].set_title(f'{col_F} vs {col_B}')
                axes_T[panel_idx].legend()

                if log_scale:
                    axes_T[panel_idx].set_yscale('log')  # For T values

        plt.tight_layout()
        plt.subplots_adjust(top=0.9)
        plt.suptitle(f"Grand Figure for T values, {tt_value}, mingo0{station}\n{start_time}", fontsize=16)

        if save_plots:
            final_filename = f'{fig_idx}_{tt_value}_grand_figure_T.png'
            fig_idx += 1

            save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
            plot_list.append(save_fig_path)
            save_plot_figure(save_fig_path, format='png')

        if show_plots: plt.show()
        plt.close(fig_T)

        # Create the grand figure for Q values
        fig_Q, axes_Q = plt.subplots(4, 4, figsize=(20, 10))  # Adjust the layout as necessary
        axes_Q = axes_Q.flatten()

        for plane in range(1, 5):
            for strip in range(1, 5):
                panel_idx = (plane - 1) * 4 + (strip - 1)
                col_F = f'p{plane}_s{strip}_ef_q'
                col_B = f'p{plane}_s{strip}_eb_q'
                y_F = filtered_df[col_F]
                y_B = filtered_df[col_B]

                # Plot histograms with Q-specific clipping and bins

                axes_Q[panel_idx].hist(y_F[(y_F != 0) & (y_F > Q_clip_min) & (y_F < Q_clip_max)],
                                    bins=num_bins, alpha=0.5, label=f'{col_F} (F)')
                axes_Q[panel_idx].hist(y_B[(y_B != 0) & (y_B > Q_clip_min) & (y_B < Q_clip_max)],
                                    bins=num_bins, alpha=0.5, label=f'{col_B} (B)')
                axes_Q[panel_idx].set_title(f'{col_F} vs {col_B}')
                axes_Q[panel_idx].legend()

                # if log_scale:
                #     axes_Q[panel_idx].set_yscale('log')  # For Q values

        plt.tight_layout()
        plt.subplots_adjust(top=0.9)
        plt.suptitle(f"Grand Figure for Q values, {tt_value}, mingo0{station}\n{start_time}", fontsize=16)

        if save_plots:
            final_filename = f'{fig_idx}_{tt_value}_grand_figure_Q.png'
            fig_idx += 1

            save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
            plot_list.append(save_fig_path)
            save_plot_figure(save_fig_path, format='png')

        if show_plots: plt.show()
        plt.close(fig_Q)

if task1_plot_enabled("tq_scatter_filtered"):
    # Initialize figure and axes for scatter plot of Time vs Charge
    fig_TQ, axes_TQ = plt.subplots(4, 4, figsize=(20, 10))  # Adjust the layout as necessary
    axes_TQ = axes_TQ.flatten()

    # Iterate over each plane (T1, T2, T3, T4)
    for plane in range(1, 5):
        for strip in range(1, 5):
            panel_idx = (plane - 1) * 4 + (strip - 1)
            col_F = f'p{plane}_s{strip}_ef_t'  # Time F column
            col_B = f'p{plane}_s{strip}_eb_t'  # Time B column

            y_F = working_df[col_F]  # Time values for front
            y_B = working_df[col_B]  # Time values for back

            charge_col_F = f'p{plane}_s{strip}_ef_q'  # Corresponding charge column for front
            charge_col_B = f'p{plane}_s{strip}_eb_q'  # Corresponding charge column for back

            charge_F = working_df[charge_col_F]  # Charge values for front
            charge_B = working_df[charge_col_B]  # Charge values for back

            # Apply clipping ranges to the data
            mask_F = (y_F != 0) & (y_F > T_clip_min) & (y_F < T_clip_max) & (charge_F > Q_clip_min) & (charge_F < Q_clip_max)
            mask_B = (y_B != 0) & (y_B > T_clip_min) & (y_B < T_clip_max) & (charge_B > Q_clip_min) & (charge_B < Q_clip_max)

            # Plot scatter plots for Time F vs Charge F and Time B vs Charge B
            axes_TQ[panel_idx].scatter(charge_F[mask_F], y_F[mask_F], alpha=0.5, label=f'{col_F} (F)', color='green', s=1)
            axes_TQ[panel_idx].scatter(charge_B[mask_B], y_B[mask_B], alpha=0.5, label=f'{col_B} (B)', color='orange', s=1)

            # Plot threshold lines for time and charge
            axes_TQ[panel_idx].axhline(y=T_F_left_pre_cal, color='red', linestyle='--', label='T_left_pre_cal')
            axes_TQ[panel_idx].axhline(y=T_F_right_pre_cal, color='blue', linestyle='--', label='T_right_pre_cal')
            axes_TQ[panel_idx].axvline(x=Q_F_left_pre_cal, color='red', linestyle='--', label='Q_left_pre_cal')
            axes_TQ[panel_idx].axvline(x=Q_F_right_pre_cal, color='blue', linestyle='--', label='Q_right_pre_cal')

            axes_TQ[panel_idx].set_title(f'{col_F} vs {col_B}')
            axes_TQ[panel_idx].legend()

    # Adjust the layout and title
    plt.tight_layout()
    plt.subplots_adjust(top=0.9)
    plt.suptitle(f"Scatter Plot for T vs Q values, mingo0{station}\n{start_time}", fontsize=16)

    # Save the plot
    if save_plots:
        final_filename = f'{fig_idx}_scatter_plot_TQ_filtered.png'
        fig_idx += 1
        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format='png')

    # Show the plot if requested
    if show_plots:
        plt.show()

    # Close the plot to avoid excessive memory usage
    plt.close(fig_TQ)

# FINAL plot block moved out of the runtime flow: tq_scatter_filtered_by_tt
pass

nonzero_counts = (working_df != 0).sum()

# Identify columns with fewer than 100 nonzero values
low_value_cols = nonzero_counts[nonzero_counts < 100].index.tolist()

if low_value_cols:
    print(f"Warning: The following columns contain fewer than 100 nonzero values and may require review: {low_value_cols}")
    print("Rejecting file due to insufficient data.")

    # Move the file to the error directory
    final_path = os.path.join(base_directories["error_directory"], file_name)
    print(f"Moving {file_path} to the error directory {final_path}...")
    safe_move(file_path, final_path)
    now = time.time()
    os.utime(final_path, (now, now))
    sys.exit(1)

print("Task 1 applies one unified channel-combination filter over self, same-strip, same-plane, and any-channel relations.")

_prof["s_filter_uncal_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()
if time_window_filtering:
    print("Task 1 coincidence-window filtering disabled; strip-coupled timing cleanup now belongs to Task 2.")
_prof["s_time_window_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()

# ─────────────────────────────────────────────────────────────────────────────
# 64×64 lower-triangular channel T/Q matrix, one figure per plane pair
# Variables: [T_F, T_B, Q_F, Q_B] × 4 planes × 4 strips = 64 variables
# Diagonal: histogram; lower triangle: scatter; upper triangle: hidden.
# ─────────────────────────────────────────────────────────────────────────────
channel_noise_limit_learning_removed_values = _empty_task1_removed_channel_values_frame()
task1_learned_channel_noise_limits: dict[tuple[int, str, int], float] = {}
task1_effective_channel_q_left_limits: dict[tuple[int, str, int], float] = {}
_plot_channel_tq_matrix_by_planepair = task1_plot_enabled("channel_tq_matrix_by_planepair")
_plot_channel_combination_filter_by_tt = task1_plot_enabled("channel_combination_filter_by_tt")
channel_plot_original_df = pd.DataFrame()
channel_plot_precombination_df = pd.DataFrame()
channel_plot_final_df = pd.DataFrame()
channel_combination_hist_original = pd.DataFrame()
channel_combination_hist_before = pd.DataFrame()
channel_combination_hist_after_preview = pd.DataFrame()
# FINAL plot block moved out of the runtime flow: channel_tq_matrix_by_planepair
pass
if _plot_channel_combination_filter_by_tt:
    channel_combination_hist_original = collect_task1_channel_combination_histogram_payload(
        channel_plot_original_df,
        _task1_filter_tt_series(channel_plot_original_df),
    )
    channel_combination_hist_before = collect_task1_channel_combination_histogram_payload(
        channel_plot_precombination_df,
        _task1_filter_tt_series(channel_plot_precombination_df),
    )
    channel_combination_hist_after_preview = collect_task1_channel_combination_histogram_payload(
        channel_plot_final_df,
        _task1_filter_tt_series(channel_plot_precombination_df),
    )

# FINAL plot block moved out of the runtime flow: channel_tq_matrix_by_planepair
pass

# Path to save the cleaned dataframe
# Create output directory if it does not exist.
os.makedirs(f"{output_directory}", exist_ok=True)
OUT_PATH = f"{output_directory}/cleaned_{basename_no_ext}.parquet"
KEY = "df"  # HDF5 key name

# Ensure output directory exists
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

# --- Example: your cleaned DataFrame is called working_df ---
# (Here, you would have your data cleaning code before saving)
# working_df = ...

# Task 1 now applies a single unified channel-combination filter. The legacy
# per-channel mismatch and learned/manual low-charge stages remain available in
# the codebase for backwards inspection, but they are inactive in the live path.
task1_channel_pairs = collect_task1_channel_qt_map(working_df)
row_mismatch_mask = pd.Series(False, index=working_df.index, dtype=bool)
channel_qt_rows_affected = 0
channel_qt_values_zeroed = 0
channel_qt_q_only_rows = 0
channel_qt_t_only_rows = 0
channel_qt_front_rows = 0
channel_qt_back_rows = 0
channel_qt_mismatch_channels = 0
channel_qt_removed_tt_task1_clean = 0
channel_qt_retained_final = 0
global_variables["plane_combination_noise_limit_learning_removed_values"] = 0
global_variables["plane_combination_noise_limit_learning_zeroed_values"] = 0
global_variables["plane_combination_noise_limit_learning_channels"] = 0
global_variables["plane_combination_noise_limit_mode"] = "inactive"
global_variables["plane_combination_noise_limit_configured_channels"] = int(
    len(manual_channel_noise_charge_limits)
)
global_variables["plane_combination_noise_limit_rows_affected"] = 0
global_variables["plane_combination_noise_limit_values_zeroed"] = 0
for channel_key in TASK1_CHANNEL_KEYS:
    global_variables[_task1_channel_noise_limit_metric_key(channel_key)] = ""

task1_pre_channel_qt_summary = apply_task1_channel_qt_mismatch_filter(
    working_df,
    snapshot_originals=snapshot_original_columns_once,
    apply_changes=False,
)
plane_combination_summary = apply_task1_plane_combination_filter(
    working_df,
    relation_limits_by_type=task1_channel_combination_limits_by_relation,
    snapshot_originals=snapshot_original_columns_once,
    removed_value_pass_label="plane_combination_filter",
    apply_changes=False,
)
for component_key, _component_label in TASK1_CHANNEL_COMBINATION_COMPONENT_LABELS:
    plane_combination_summary.setdefault(f"failed_pair_{component_key}", 0)
    plane_combination_summary.setdefault(f"rows_failed_{component_key}", 0)
    plane_combination_summary.setdefault(
        f"failed_pair_{component_key}_by_relation",
        {relation_type: 0 for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES},
    )
    plane_combination_summary.setdefault(
        f"rows_failed_{component_key}_by_relation",
        {relation_type: 0 for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES},
    )
task1_post_channel_qt_summary = apply_task1_channel_qt_mismatch_filter(
    working_df,
    snapshot_originals=snapshot_original_columns_once,
    apply_changes=False,
)
row_mismatch_mask = (
    task1_pre_channel_qt_summary["row_mismatch_mask"]
    | task1_post_channel_qt_summary["row_mismatch_mask"]
)
channel_qt_rows_affected = int(row_mismatch_mask.sum())
channel_qt_values_zeroed = int(
    task1_pre_channel_qt_summary["values_zeroed"]
    + task1_post_channel_qt_summary["values_zeroed"]
)
channel_qt_q_only_rows = int(
    (
        task1_pre_channel_qt_summary["q_only_row_mask"]
        | task1_post_channel_qt_summary["q_only_row_mask"]
    ).sum()
)
channel_qt_t_only_rows = int(
    (
        task1_pre_channel_qt_summary["t_only_row_mask"]
        | task1_post_channel_qt_summary["t_only_row_mask"]
    ).sum()
)
channel_qt_front_rows = int(
    (
        task1_pre_channel_qt_summary["front_row_mask"]
        | task1_post_channel_qt_summary["front_row_mask"]
    ).sum()
)
channel_qt_back_rows = int(
    (
        task1_pre_channel_qt_summary["back_row_mask"]
        | task1_post_channel_qt_summary["back_row_mask"]
    ).sum()
)
channel_qt_mismatch_channels = int(
    task1_pre_channel_qt_summary["mismatch_channels"]
    + task1_post_channel_qt_summary["mismatch_channels"]
)
print(
    "[task1-channel-qt-normalization] "
    f"pre_rows={task1_pre_channel_qt_summary['rows_affected']} "
    f"pre_values_zeroed={task1_pre_channel_qt_summary['values_zeroed']} "
    f"post_rows={task1_post_channel_qt_summary['rows_affected']} "
    f"post_values_zeroed={task1_post_channel_qt_summary['values_zeroed']}"
)
working_df.loc[:, "filter_task1_problematic_channel_count"] = (
    plane_combination_summary["selected_offender_count_by_row"]
    .reindex(working_df.index, fill_value=0)
    .astype(int)
    .to_numpy()
)
working_df.loc[:, "filter_task1_problematic_channel_exact"] = (
    plane_combination_summary["resolution_exact_by_row"]
    .reindex(working_df.index, fill_value=True)
    .astype(bool)
    .to_numpy()
)
filter_task1_problematic_channel_count_snapshot = working_df.loc[
    :,
    [col for col in ("datetime", "filter_task1_problematic_channel_count") if col in working_df.columns],
].copy()
filter_task1_problematic_channel_count_counts = (
    pd.to_numeric(
        filter_task1_problematic_channel_count_snapshot.get(
            "filter_task1_problematic_channel_count",
            pd.Series(dtype=float),
        ),
        errors="coerce",
    )
    .fillna(0)
    .astype(int)
    .value_counts()
    .to_dict()
)
record_activity_metric(
    "plane_combination_filter_rows_affected_pct",
    plane_combination_summary["rows_affected"],
    len(working_df) if len(working_df) else 0,
    label="rows with channel-combination failures",
)
record_activity_metric(
    "plane_combination_filter_values_zeroed_pct",
    plane_combination_summary["values_zeroed"],
    len(working_df) * (2 * plane_combination_summary["tracked_channel_count"])
    if (len(working_df) and plane_combination_summary["tracked_channel_count"])
    else 0,
    label="channel Q/T values zeroed by plane-combination filter",
)
for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES:
    valid_relation_observations = int(
        plane_combination_summary["valid_pair_observations_by_relation"].get(relation_type, 0)
    )
    failed_relation_observations = int(
        plane_combination_summary["failed_pair_any_by_relation"].get(relation_type, 0)
    )
    relation_failed_rows = int(
        plane_combination_summary["rows_with_relation_failures"].get(relation_type, 0)
    )
    record_activity_metric(
        f"plane_combination_filter_{relation_type}_relation_failed_pct",
        failed_relation_observations,
        valid_relation_observations if valid_relation_observations else 0,
        label=f"{relation_type} relation failures",
    )
    record_activity_metric(
        f"plane_combination_filter_rows_with_{relation_type}_relation_failures_pct",
        relation_failed_rows,
        len(working_df) if len(working_df) else 0,
        label=f"rows with {relation_type} relation failures",
    )
    for component_key, component_label in TASK1_CHANNEL_COMBINATION_COMPONENT_LABELS:
        record_activity_metric(
            f"plane_combination_filter_{relation_type}_{component_key}_failed_pct",
            plane_combination_summary[f"failed_pair_{component_key}_by_relation"].get(relation_type, 0),
            valid_relation_observations if valid_relation_observations else 0,
            label=f"{relation_type} {component_label} failures",
        )
        record_activity_metric(
            f"plane_combination_filter_{relation_type}_{component_key}_rows_failed_pct",
            plane_combination_summary[f"rows_failed_{component_key}_by_relation"].get(relation_type, 0),
            len(working_df) if len(working_df) else 0,
            label=f"rows with {relation_type} {component_label} failures",
        )
record_activity_metric(
    "plane_combination_filter_any_failed_pct",
    plane_combination_summary["failed_pair_any"],
    plane_combination_summary["valid_pair_observations"],
    label="failed channel plane combinations",
)
record_activity_metric(
    "plane_combination_filter_q_sum_failed_pct",
    plane_combination_summary["failed_pair_q_sum"],
    plane_combination_summary["valid_pair_observations"],
    label="Q_sum failed channel plane combinations",
)
record_activity_metric(
    "plane_combination_filter_q_sum_low_failed_pct",
    plane_combination_summary["failed_pair_q_sum_low"],
    plane_combination_summary["valid_pair_observations"],
    label="Q_sum low-bound failed channel plane combinations",
)
record_activity_metric(
    "plane_combination_filter_q_sum_high_failed_pct",
    plane_combination_summary["failed_pair_q_sum_high"],
    plane_combination_summary["valid_pair_observations"],
    label="Q_sum high-bound failed channel plane combinations",
)
record_activity_metric(
    "plane_combination_filter_q_dif_failed_pct",
    plane_combination_summary["failed_pair_q_dif"],
    plane_combination_summary["valid_pair_observations"],
    label="Q_dif failed channel plane combinations",
)
record_activity_metric(
    "plane_combination_filter_t_sum_failed_pct",
    plane_combination_summary["failed_pair_t_sum"],
    plane_combination_summary["valid_pair_observations"],
    label="T_sum failed channel plane combinations",
)
record_activity_metric(
    "plane_combination_filter_t_sum_low_failed_pct",
    plane_combination_summary["failed_pair_t_sum_low"],
    plane_combination_summary["valid_pair_observations"],
    label="T_sum low-bound failed channel plane combinations",
)
record_activity_metric(
    "plane_combination_filter_t_sum_high_failed_pct",
    plane_combination_summary["failed_pair_t_sum_high"],
    plane_combination_summary["valid_pair_observations"],
    label="T_sum high-bound failed channel plane combinations",
)
record_activity_metric(
    "plane_combination_filter_t_dif_failed_pct",
    plane_combination_summary["failed_pair_t_dif"],
    plane_combination_summary["valid_pair_observations"],
    label="T_dif failed channel plane combinations",
)
for component_key, component_label in TASK1_CHANNEL_COMBINATION_COMPONENT_LABELS:
    record_activity_metric(
        f"plane_combination_filter_{component_key}_rows_failed_pct",
        plane_combination_summary[f"rows_failed_{component_key}"],
        len(working_df) if len(working_df) else 0,
        label=f"rows with {component_label} failures",
    )
record_activity_metric(
    "plane_combination_filter_flagged_rows_pct",
    plane_combination_summary["flagged_rows"],
    len(working_df) if len(working_df) else 0,
    label="rows with at least one failed channel plane combination",
)
record_activity_metric(
    "plane_combination_filter_selected_offender_channels_pct",
    plane_combination_summary["selected_offender_channels"],
    len(working_df) * plane_combination_summary["tracked_channel_count"]
    if (len(working_df) and plane_combination_summary["tracked_channel_count"])
    else 0,
    label="selected offending channels",
)
record_activity_metric(
    "plane_combination_filter_multi_offender_rows_pct",
    plane_combination_summary["rows_with_multiple_offenders"],
    plane_combination_summary["flagged_rows"],
    label="flagged rows needing multiple offending channels",
)
global_variables["plane_combination_filter_flagged_rows"] = int(
    plane_combination_summary["flagged_rows"]
)
global_variables["plane_combination_filter_input_rows"] = int(
    plane_combination_summary.get("input_rows", len(working_df))
)
for relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES:
    global_variables[f"plane_combination_filter_{relation_type}_failed_observations"] = int(
        plane_combination_summary["failed_pair_any_by_relation"].get(relation_type, 0)
    )
    global_variables[f"plane_combination_filter_{relation_type}_q_sum_low_failed_observations"] = int(
        plane_combination_summary["failed_pair_q_sum_low_by_relation"].get(relation_type, 0)
    )
    global_variables[f"plane_combination_filter_{relation_type}_q_sum_high_failed_observations"] = int(
        plane_combination_summary["failed_pair_q_sum_high_by_relation"].get(relation_type, 0)
    )
    global_variables[f"plane_combination_filter_{relation_type}_t_sum_low_failed_observations"] = int(
        plane_combination_summary["failed_pair_t_sum_low_by_relation"].get(relation_type, 0)
    )
    global_variables[f"plane_combination_filter_{relation_type}_t_sum_high_failed_observations"] = int(
        plane_combination_summary["failed_pair_t_sum_high_by_relation"].get(relation_type, 0)
    )
    global_variables[f"plane_combination_filter_rows_with_{relation_type}_relation_failures"] = int(
        plane_combination_summary["rows_with_relation_failures"].get(relation_type, 0)
    )
global_variables["plane_combination_filter_q_sum_low_failed_observations"] = int(
    plane_combination_summary["failed_pair_q_sum_low"]
)
global_variables["plane_combination_filter_q_sum_high_failed_observations"] = int(
    plane_combination_summary["failed_pair_q_sum_high"]
)
global_variables["plane_combination_filter_t_sum_low_failed_observations"] = int(
    plane_combination_summary["failed_pair_t_sum_low"]
)
global_variables["plane_combination_filter_t_sum_high_failed_observations"] = int(
    plane_combination_summary["failed_pair_t_sum_high"]
)
global_variables["plane_combination_filter_selected_offender_channels"] = int(
    plane_combination_summary["selected_offender_channels"]
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
for selected_count in TASK1_SELECTED_OFFENDER_CARDINALITY_VALUES:
    selected_rows = int(filter_task1_problematic_channel_count_counts.get(selected_count, 0))
    global_variables[_task1_selected_offender_cardinality_metric_key(selected_count)] = selected_rows
for channel_key, offender_count in plane_combination_summary["selected_offender_counts"].items():
    global_variables[_task1_channel_offender_metric_key(channel_key)] = int(offender_count)
filter_metrics["plane_combination_filter_mean_failed_pairs_per_flagged_row"] = round(
    float(plane_combination_summary["failed_pair_any"]) / float(plane_combination_summary["flagged_rows"])
    if plane_combination_summary["flagged_rows"]
    else 0.0,
    4,
)
filter_metrics["plane_combination_filter_mean_selected_offenders_per_flagged_row"] = round(
    float(plane_combination_summary["selected_offender_channels"]) / float(plane_combination_summary["flagged_rows"])
    if plane_combination_summary["flagged_rows"]
    else 0.0,
    4,
)
filter_metrics["plane_combination_filter_max_failed_pairs_in_row"] = int(
    plane_combination_summary["max_failed_pairs_in_row"]
)
filter_metrics["plane_combination_filter_max_selected_offenders_in_row"] = int(
    plane_combination_summary["max_selected_offenders_in_row"]
)
task1_removed_channel_values_df = collect_task1_zeroed_channel_values(
    channel_pair_plot_reference_df if not channel_pair_plot_reference_df.empty else working_df,
    working_df,
    pass_label="final_zeroed_any_filter",
)
global_variables["task1_zeroed_channel_values"] = int(len(task1_removed_channel_values_df))
if _plot_channel_combination_filter_by_tt:
    channel_combination_limits_by_relation = {}
    for _relation_type in TASK1_CHANNEL_COMBINATION_RELATION_TYPES:
        _relation_limits = task1_channel_combination_limits_by_relation.get(_relation_type, {})
        channel_combination_limits_by_relation[_relation_type] = {
            "q_sum": (
                float(_relation_limits.get("q_sum_left", channel_combination_q_sum_left)),
                float(_relation_limits.get("q_sum_right", channel_combination_q_sum_right)),
            ),
            "q_dif": (
                -abs(float(_relation_limits.get("q_dif_threshold", channel_combination_q_dif_threshold))),
                abs(float(_relation_limits.get("q_dif_threshold", channel_combination_q_dif_threshold))),
            ),
            "t_sum": (
                float(_relation_limits.get("t_sum_left", channel_combination_t_sum_left)),
                float(_relation_limits.get("t_sum_right", channel_combination_t_sum_right)),
            ),
            "t_dif": (
                -abs(float(_relation_limits.get("t_dif_threshold", channel_combination_t_dif_threshold))),
                abs(float(_relation_limits.get("t_dif_threshold", channel_combination_t_dif_threshold))),
            ),
        }
    fig_idx = plot_task1_channel_combination_filter_by_tt(
        channel_combination_hist_original,
        channel_combination_hist_before,
        channel_combination_hist_after_preview,
        basename_no_ext,
        fig_idx,
        show_plots=show_plots,
        save_plots=save_plots,
        plot_list=plot_list,
        limits_by_relation=channel_combination_limits_by_relation,
        q_left_limits_by_channel=task1_effective_channel_q_left_limits,
        top_n_by_relation=channel_combination_plot_top_n_by_relation,
        include_same_strip_pairs=channel_combination_plot_include_same_strip_pairs,
    )

print(f"Original number of events in the dataframe: {original_number_of_events}")
# Task 1 channel pass bitmask. Bit 0 is the first TASK1_CHANNEL_KEYS entry,
# bit 31 is the last; 1 means the channel survived all Task 1 channel checks.
passes_task_1 = np.full(len(working_df), np.uint32(0xFFFFFFFF), dtype=np.uint32)
for bit_idx, channel_key in enumerate(TASK1_CHANNEL_KEYS):
    channel_fail_masks = plane_combination_summary.get("selected_offender_mask_by_channel", {})
    fail_series = channel_fail_masks.get(channel_key) if isinstance(channel_fail_masks, dict) else None
    if fail_series is None:
        fail_mask = np.zeros(len(working_df), dtype=bool)
    else:
        fail_mask = fail_series.reindex(working_df.index, fill_value=False).to_numpy(dtype=bool)
    for mismatch_summary in (task1_pre_channel_qt_summary, task1_post_channel_qt_summary):
        mismatch_masks = mismatch_summary.get("mismatch_mask_by_channel", {})
        mismatch_series = mismatch_masks.get(channel_key) if isinstance(mismatch_masks, dict) else None
        if mismatch_series is not None:
            fail_mask |= mismatch_series.reindex(working_df.index, fill_value=False).to_numpy(dtype=bool)
    if not np.any(fail_mask):
        continue
    passes_task_1[fail_mask] &= np.uint32(~(1 << bit_idx) & 0xFFFFFFFF)
working_df.loc[:, "passes_task_1"] = passes_task_1

# Compute clean trigger types after channel-only regularization. Keep every row
# and record the final trigger-condition failure instead of removing events.
working_df = compute_tt(working_df, "tt_task1_clean")
tt_task1_clean_total = len(working_df)
tt_task1_clean_mask = working_df["tt_task1_clean"].notna() & (working_df["tt_task1_clean"] >= 10)
channel_qt_removed_tt_task1_clean = int((~tt_task1_clean_mask & row_mismatch_mask.reindex(working_df.index, fill_value=False)).sum())
working_df.loc[:, "filter_task1_tt_task1_clean_pass"] = tt_task1_clean_mask.to_numpy(dtype=bool)
record_filter_metric(
    "tt_task1_clean_lt_10_rows_flagged_pct",
    tt_task1_clean_total - int(tt_task1_clean_mask.sum()),
    tt_task1_clean_total if tt_task1_clean_total else 0,
)
channel_qt_retained_final = int(row_mismatch_mask.reindex(working_df.index, fill_value=False).sum())
record_activity_metric(
    "channel_qt_mismatch_rows_removed_tt_task1_clean_of_mismatch_pct",
    channel_qt_removed_tt_task1_clean,
    channel_qt_rows_affected,
    label="mismatch-touched rows later removed by tt_task1_clean filter",
)
record_activity_metric(
    "channel_qt_mismatch_rows_retained_final_of_mismatch_pct",
    channel_qt_retained_final,
    channel_qt_rows_affected,
    label="mismatch-touched rows retained after Task 1",
)
working_df.loc[:, "transferred_task1_raw_to_clean"] = (
    pd.to_numeric(working_df["tt_task0_raw"], errors="coerce").fillna(0).astype(int).astype(str)
    + "_"
    + pd.to_numeric(working_df["tt_task1_clean"], errors="coerce").fillna(0).astype(int).astype(str)
)
refresh_global_count_metadata(
    working_df,
    ("tt_task0_raw", "tt_task1_clean", "transferred_task1_raw_to_clean"),
)

task1_final_filter_dry_run_summary = apply_task1_plane_combination_filter(
    working_df,
    relation_limits_by_type=task1_channel_combination_limits_by_relation,
    apply_changes=False,
)
task1_final_filter_dry_run_has_effect = int(
    (
        int(task1_final_filter_dry_run_summary.get("rows_affected", 0)) > 0
        or int(task1_final_filter_dry_run_summary.get("values_zeroed", 0)) > 0
        or int(task1_final_filter_dry_run_summary.get("failed_pair_any", 0)) > 0
    )
)
global_variables["plane_combination_filter_dry_run_has_effect"] = task1_final_filter_dry_run_has_effect
global_variables["plane_combination_filter_dry_run_input_rows"] = int(
    task1_final_filter_dry_run_summary.get("input_rows", len(working_df))
)
global_variables["plane_combination_filter_dry_run_rows_affected"] = int(
    task1_final_filter_dry_run_summary.get("rows_affected", 0)
)
global_variables["plane_combination_filter_dry_run_flagged_rows"] = int(
    task1_final_filter_dry_run_summary.get("flagged_rows", 0)
)
global_variables["plane_combination_filter_dry_run_values_zeroed"] = int(
    task1_final_filter_dry_run_summary.get("values_zeroed", 0)
)
global_variables["plane_combination_filter_dry_run_failed_pair_any"] = int(
    task1_final_filter_dry_run_summary.get("failed_pair_any", 0)
)
print(
    "[TASK1_FINAL_FILTER_DRY_RUN] "
    f"has_effect={'yes' if task1_final_filter_dry_run_has_effect else 'no'} "
    f"input_rows={global_variables['plane_combination_filter_dry_run_input_rows']} "
    f"flagged_rows={global_variables['plane_combination_filter_dry_run_flagged_rows']} "
    f"rows_affected={global_variables['plane_combination_filter_dry_run_rows_affected']} "
    f"values_zeroed={global_variables['plane_combination_filter_dry_run_values_zeroed']} "
    f"failed_pair_any={global_variables['plane_combination_filter_dry_run_failed_pair_any']}",
    force=True,
)

clean_channel_patterns = build_task1_channel_pattern_series(working_df)
store_pattern_rates(pattern_metadata, clean_channel_patterns, "clean_channel_pattern", working_df)

# Always compute clean-stage channel contagion metrics for metadata.
clean_channel_matrix_data = _compute_channel_conditional_matrix(working_df)
_store_channel_contagion_metrics_variant(
    "global_clean",
    clean_channel_matrix_data,
)
_store_channel_contagion_metrics_variant(
    "by_tt_clean",
    _compute_channel_conditional_matrix_for_tt(working_df, "tt_task1_clean", 1234),
)
clean_channel_inputs = _compute_channel_contagion_inputs(working_df)
if clean_channel_matrix_data is not None and clean_channel_inputs is not None:
    clean_channel_labels, clean_channel_active = clean_channel_inputs
    _, clean_channel_matrix = clean_channel_matrix_data
    clean_channel_given_counts = {
        label: int(clean_channel_active[:, idx].sum())
        for idx, label in enumerate(clean_channel_labels)
    }
    store_activation_matrix_metadata(
        activation_metadata,
        "activation_channel_signal_to_signal_filtered",
        clean_channel_labels,
        clean_channel_matrix,
        clean_channel_given_counts,
        group_ids=[idx // 8 for idx in range(len(clean_channel_labels))],
    )
    clean_selected_tts, tt_task1_clean_matrices, tt_task1_clean_given_counts, tt_task1_clean_event_counts = (
        compute_conditional_matrices_by_tt(
            pd.to_numeric(working_df["tt_task1_clean"], errors="coerce").fillna(0).astype(int),
            clean_channel_labels,
            [clean_channel_active[:, idx] for idx in range(clean_channel_active.shape[1])],
        )
    )
    store_activation_matrices_by_tt_metadata(
        activation_metadata,
        "activation_channel_signal_to_signal_filtered_by_tt",
        clean_channel_labels,
        clean_channel_labels,
        clean_selected_tts,
        tt_task1_clean_matrices,
        tt_task1_clean_given_counts,
        tt_task1_clean_event_counts,
    )
    del clean_channel_active
    del clean_channel_matrix
    del clean_selected_tts, tt_task1_clean_matrices, tt_task1_clean_given_counts, tt_task1_clean_event_counts
    gc.collect()

# --- Post-filter (clean) channel contamination matrices ---
if task1_plot_enabled("channel_contamination_matrix_32"):
    fig_idx = _plot_channel_contamination_global(
        working_df, "clean", fig_idx, base_directories["figure_directory"],
        save_plots, show_plots, plot_list,
    )

if task1_plot_enabled("channel_contagion_by_tt"):
    fig_idx = _plot_channel_contagion_by_tt(
        working_df, "tt_task1_clean", "clean", fig_idx, base_directories["figure_directory"],
        save_plots, show_plots, plot_list,
    )

_finalize_stage_t0 = _t_sec

# Final number of events
final_number_of_events = len(working_df)
print(f"Final number of events in the dataframe: {final_number_of_events}")

# ----------------------------------------------------------------------------------
# Count the number of non-zero entries per channel in the whole dataframe ----------
# ----------------------------------------------------------------------------------

# Count per each column the number of non-zero entries and save it in a column of
# global_variables called TX_F_Y_entries or TX_B_Y_entries

# Count for main dataframe (non-self-trigger)
final_entry_columns = [
    f"{key}_{i}"
    for key, idx_range in column_indices.items()
    for i in range(1, len(idx_range) + 1)
    if f"{key}_{i}" in working_df.columns
]
final_entry_counts = (
    working_df.loc[:, final_entry_columns].ne(0).sum(axis=0).astype(int).to_dict()
    if final_entry_columns
    else {}
)
for colname, count in final_entry_counts.items():
    global_variables[f"{colname}_entries_final"] = int(count)
_prof["s_final_counts_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()

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
filter_metrics["valid_lines_in_file_percentage"] = round(
    float(global_variables.get("valid_lines_in_file_percentage", 0.0)),
    4,
)
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
    drop_field_predicate=lambda column_name: column_name not in FILTER_METADATA_ALLOWED_COLUMNS,
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

events_per_second_meta = build_events_per_second_metadata(working_df)
try:
    noise_control_rate_denominator_seconds = int(
        events_per_second_meta.get("events_per_second_total_seconds", 0) or 0
    )
except (TypeError, ValueError):
    noise_control_rate_denominator_seconds = 0
if noise_control_rate_denominator_seconds < 0:
    noise_control_rate_denominator_seconds = 0

noise_control_row = {
    "filename_base": filename_base,
    "execution_timestamp": execution_timestamp,
    "param_hash": param_hash_value,
    NOISE_CONTROL_RATE_DENOMINATOR_COLUMN: noise_control_rate_denominator_seconds,
}
for selected_count in TASK1_SELECTED_OFFENDER_CARDINALITY_VALUES:
    raw_count = filter_task1_problematic_channel_count_counts.get(selected_count, 0)
    try:
        raw_count_value = float(raw_count)
    except (TypeError, ValueError):
        noise_control_row[_task1_selected_offender_cardinality_rate_metric_key(selected_count)] = ""
        noise_control_row[_task1_selected_offender_cardinality_percent_metric_key(selected_count)] = ""
        continue
    rate_value = (
        raw_count_value / noise_control_rate_denominator_seconds
        if noise_control_rate_denominator_seconds > 0
        else 0.0
    )
    noise_control_row[_task1_selected_offender_cardinality_rate_metric_key(selected_count)] = round(
        rate_value,
        6,
    )
    input_rows_value = float(len(filter_task1_problematic_channel_count_snapshot.index))
    pct_value = 100.0 * raw_count_value / input_rows_value if input_rows_value > 0 else 0.0
    noise_control_row[_task1_selected_offender_cardinality_percent_metric_key(selected_count)] = round(
        pct_value,
        4,
    )

task1_noise_control_tt_task1_clean = pd.to_numeric(
    working_df.get("tt_task1_clean", pd.Series(index=working_df.index, dtype=float)),
    errors="coerce",
).fillna(0).astype(int)
task1_noise_control_selected_offenders = pd.to_numeric(
    working_df.get(
        "filter_task1_problematic_channel_count",
        pd.Series(index=working_df.index, dtype=float),
    ),
    errors="coerce",
).fillna(0).astype(int)

for selected_count_threshold in task1_noise_control_efficiency_selected_offender_values:
    threshold_mask = task1_noise_control_selected_offenders <= selected_count_threshold
    threshold_tt_task1_clean = task1_noise_control_tt_task1_clean.loc[threshold_mask]
    four_plane_count = int((threshold_tt_task1_clean == 1234).sum())
    for plane, missing_trigger in TASK1_THREE_TO_FOUR_MISSING_TRIGGER_BY_PLANE.items():
        metric_key = _task1_noise_control_efficiency_metric_key(
            plane,
            selected_count_threshold,
        )
        if four_plane_count <= 0:
            noise_control_row[metric_key] = ""
            continue
        missing_plane_count = int((threshold_tt_task1_clean == missing_trigger).sum())
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
        *TASK1_NOISE_CONTROL_METRIC_NAMES,
        *TASK1_NOISE_CONTROL_PERCENT_METRIC_NAMES,
        *_task1_noise_control_efficiency_metric_names(
            task1_noise_control_efficiency_selected_offender_values
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

for _metric_name, _metric_value in channel_contagion_metrics.items():
    global_variables[_metric_name] = _metric_value

execution_metadata_row = {
    "filename_base": filename_base,
    "execution_timestamp": execution_timestamp,
    "param_hash": param_hash_value,
    "data_purity_percentage": round(float(data_purity_percentage), 4),
    "total_execution_time_minutes": round(float(total_execution_time_minutes), 4),
    "joined_analysis_files_used": int(len(joined_input_records)),
    **channel_contagion_metrics,
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
        *CHANNEL_CONTAGION_METADATA_FIELDS,
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

global_variables.update(events_per_second_meta)
ensure_global_count_keys(("tt_task0_raw", "tt_task1_clean", "transferred_task1_raw_to_clean"))
add_normalized_count_metadata(
    global_variables,
    global_variables.get("events_per_second_total_seconds", 0),
)
set_global_rate_from_tt_rates(
    global_variables,
    preferred_prefixes=("tt_task0_raw", "tt_task1_clean"),
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
trigger_type_prefixes = ("tt_task0_raw", "tt_task1_clean", "transferred_task1_raw_to_clean")
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
    stage_tt_columns=("tt_task0_raw", "tt_task1_clean"),
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
# if VERBOSE:
#     print("----------\nAll global variables to be saved:")
#     for key, value in global_variables.items():
#         print(f"{key}: {value}")
#     print("----------\n")

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
        or column_name.startswith("raw_channel_pattern_")
        or column_name.startswith("clean_channel_pattern_")
        or is_trigger_type_metadata_column(column_name, trigger_type_prefixes)
        or column_name == "valid_lines_in_file_percentage"
    ),
)
print(f"Metadata (specific) CSV updated at: {metadata_specific_csv_path}")
_prof["s_metadata_write_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()

print(
    f"Writing cleaned parquet: rows={len(working_df)} cols={len(working_df.columns)} -> {OUT_PATH}"
)
# if VERBOSE:
#     print("Columns before saving cleaned parquet:")
#     for col in working_df.columns:
#         print(f" - {col}")

# Ensure datetime column is stored with a pandas datetime64 dtype to satisfy pyarrow
if "datetime" in working_df.columns:
    snapshot_original_columns_once(working_df, ["datetime"])
    working_df["datetime"] = pd.to_datetime(working_df["datetime"], errors="coerce")
    if working_df["datetime"].dtype == object:
        working_df["datetime"] = pd.to_datetime(
            working_df["datetime"].astype(str), errors="coerce"
        )

# Persist simulated parameter hash as a constant column (string) for traceability.
if "param_hash" not in working_df.columns:
    working_df["param_hash"] = str(simulated_param_hash) if simulated_param_hash else ""

if save_removed_channel_values:
    channel_removed_values_output_directory = base_directories["removed_channel_values_directory"]
    os.makedirs(channel_removed_values_output_directory, exist_ok=True)
    channel_removed_values_base = os.path.join(
        channel_removed_values_output_directory,
        f"removed_channel_values_{basename_no_ext}",
    )
    if not task1_removed_channel_values_df.empty:
        task1_removed_channel_values_output_df = task1_removed_channel_values_df.assign(
            filename_base=filename_base
        )
        task1_removed_channel_values_output_df.to_parquet(
            f"{channel_removed_values_base}.parquet",
            engine="pyarrow",
            compression="zstd",
            index=False,
        )
        task1_removed_channel_values_output_df.to_csv(
            f"{channel_removed_values_base}.csv",
            index=False,
        )
        print(f"Removed channel-value parquet saved to: {channel_removed_values_base}.parquet")
        print(f"Removed channel-value CSV saved to: {channel_removed_values_base}.csv")
    else:
        print("Removed channel-value export skipped: no zeroed channel values recorded.")
else:
    print("Removed channel-value export skipped: save_removed_channel_values is false.")

if track_removed_rows and not diagnostic_removed_rows_df.empty:
    tracking_output_directory = base_directories["tracking_directory"]
    os.makedirs(tracking_output_directory, exist_ok=True)

    removed_rows_base = os.path.join(
        tracking_output_directory,
        f"removed_rows_{basename_no_ext}",
    )
    original_cols_base = os.path.join(
        tracking_output_directory,
        f"original_cols_{basename_no_ext}",
    )
    diagnostic_removed_rows_df.to_parquet(
        f"{removed_rows_base}.parquet",
        engine="pyarrow",
        compression="zstd",
        index=True,
    )
    diagnostic_removed_rows_df.to_csv(f"{removed_rows_base}.csv", index=True)
    print(f"Removed-row tracking parquet saved to: {removed_rows_base}.parquet")
    print(f"Removed-row tracking CSV saved to: {removed_rows_base}.csv")
    if original_columns_store:
        diagnostic_original_columns_df = build_original_columns_frame()
        diagnostic_original_columns_df.to_parquet(
            f"{original_cols_base}.parquet",
            engine="pyarrow",
            compression="zstd",
            index=True,
        )
        print(f"Original-column snapshot parquet saved to: {original_cols_base}.parquet")
elif track_removed_rows:
    print("Removed-row tracking export skipped: no rows were removed.")

# Final task-rate plot from the same dataframe population saved by Task 1.
# FINAL plot block moved out of the runtime flow: acquisition_rate_vs_time_by_task_tt_with_histograms
pass

# -----------------------------------------------------------------------------
# Create and save the PDF (deferred until all plots are generated) ------------
# -----------------------------------------------------------------------------
# Runtime figures are PNG-only; FINAL reporting is standalone.
_prof["s_pdf_finalize_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()

# Ensure no figure handles remain open before persistence/final move.
plt.close("all")

if joined_analysis_active and joined_source_file_column in working_df.columns:
    for joined_record in joined_input_records:
        joined_file_name = joined_record["file_name"]
        joined_basename = joined_record["basename_no_ext"]
        joined_out_path = os.path.join(output_directory, f"cleaned_{joined_basename}.parquet")
        joined_mask = working_df[joined_source_file_column].astype(str).eq(joined_file_name)
        joined_output_df = working_df.loc[joined_mask].drop(
            columns=[joined_source_file_column, joined_source_basename_column],
            errors="ignore",
        )
        joined_output_df = canonicalize_step1_columns(joined_output_df)
        joined_output_df.to_parquet(
            joined_out_path,
            engine="pyarrow",
            compression="zstd",
            index=False,
        )
        print(f"Cleaned joined-analysis dataframe saved to: {joined_out_path} rows={len(joined_output_df)}")
else:
    output_df = working_df.drop(
        columns=[joined_source_file_column, joined_source_basename_column],
        errors="ignore",
    )
    output_df = canonicalize_step1_columns(output_df)
    output_df.to_parquet(OUT_PATH, engine="pyarrow", compression="zstd", index=False)
    print(f"Cleaned dataframe saved to: {OUT_PATH}")
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
