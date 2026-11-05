#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/STEP_1/TASK_4/script_4_list_to_fit.py
Purpose: !/usr/bin/env python3.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/STEP_1/TASK_4/script_4_list_to_fit.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

#%%

from __future__ import annotations

"""
Stage 1 Task 4 (LIST-->FIT) preparation workflow.

Ingests the LIST-format events from Task 3, assembles the inputs used by the
timing/charge fitting routines (feature engineering, binning, sanity checks),
executes the intermediate analyses that characterise detector response, and
writes the fit-ready artefacts. Execution metadata, diagnostic plots, and
directory bookkeeping are kept in sync so the pipeline can hand off cleanly to
the correction stage.
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
from collections import defaultdict
from typing import Iterable, Mapping

# Scientific Computing
import numpy as np
import pandas as pd
import scipy.linalg as linalg
from scipy.constants import c
from scipy.ndimage import gaussian_filter
from scipy.optimize import OptimizeWarning, curve_fit
from scipy.special import erf
from scipy.stats import norm, poisson

# Plotting
import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D
from matplotlib.patches import Ellipse
from mpl_toolkits.mplot3d import Axes3D

# Image Processing

# Progress Bar
from tqdm import tqdm

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
    filter_expected_artifact_names,
    file_name_in_any_date_range,
    load_date_ranges_from_config,
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
    filter_filenames_by_qa_retry_basenames,
    get_reprocessing_value,
    infer_station_number_from_processing_name,
    load_active_qa_retry_basenames,
    load_qa_reprocessing_context_for_file,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.simulated_data_utils import (
    load_simulated_efficiencies,
    resolve_simulated_z_positions,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.step1_shared import (
    add_normalized_count_metadata,
    add_trigger_type_total_offender_threshold_metadata,
    build_events_per_second_metadata,
    build_step1_cli_parser,
    build_step1_filtered_print,
    canonicalize_step1_columns,
    coerce_nonnegative_float_config,
    coerce_positive_int_config,
    extract_chi2_four_plane_metadata,
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
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.ANCILLARY.PLOTTERS.TASK_4.task4_chi2_four_plane_plotter import (
    render_task4_chi2_four_plane_histogram,
)
from analysis_functions import (
    _cfg_float_or_default,
    _cfg_int_or_default,
    _coerce_nonnegative_int_tuple,
    _coerce_probability_tuple,
    _coerce_tt_label_tuple,
    _safe_cfg_float,
    _safe_cfg_int,
    _safe_cfg_optional_float,
    _task4_get_optional_config_float,
    _task4_parse_optional_float,
)
from plotting_functions import (
    _format_task4_percent_label,
    _safe_hist_params,
)

task_number = 4
TASK4_PRIMARY_TT_COLUMN = "tt_task4_fit"
TASK4_EXTENSION_TT_COLUMNS: dict[int, list[str]] = {
    i_plane: [
        f"p{i_plane}_tsum",
        f"p{i_plane}_tdif",
        f"p{i_plane}_qsum",
        f"p{i_plane}_qdif",
        f"p{i_plane}_ypos",
    ]
    for i_plane in range(1, 5)
}
TASK4_EVENT_ATOMIC_COLUMNS: tuple[str, ...] = (
    "event_charge",
    "x",
    "y",
    "s",
    "theta",
    "phi",
)
TASK4_FINAL_FIT_TT_MIN = 10
TASK4_FINAL_FILTER_REMOVE_SMALL = False
TASK4_FINAL_FILTER_REMOVE_SMALL_EPS = 1e-7

try:
    import pyarrow as pa
except Exception:  # pragma: no cover - pyarrow is already required for parquet IO here.
    pa = None

def task4_plot_enabled(alias: str) -> bool:
    if not task4_plot_status_by_alias:
        return True
    return step1_task_plot_enabled(alias, task4_plot_status_by_alias, plot_mode)


def resolve_task4_plot_alias(save_path: str, alias: str | None = None) -> str | None:
    if alias is not None:
        return alias if alias in TASK4_PLOT_ALIASES else None

    stem = os.path.splitext(os.path.basename(str(save_path)))[0].lower()
    stem = re.sub(r"^\d+_", "", stem)
    if stem in TASK4_PLOT_ALIASES:
        return stem
    for prefix, mapped_alias in TASK4_PLOT_PREFIX_ALIASES:
        if stem.startswith(prefix):
            return mapped_alias
    return None

def apply_task4_plot_catalog_modes() -> None:
    global create_plots, create_essential_plots, create_debug_plots, save_plots, create_pdf
    if not task4_plot_status_by_alias:
        return
    create_plots = create_plots and task4_plot_enabled("usual_suite")
    create_essential_plots = create_essential_plots and task4_plot_enabled("essential_suite")
    create_debug_plots = create_debug_plots and task4_plot_enabled("debug_suite")
    save_plots = bool(create_plots or create_essential_plots or create_debug_plots)
    create_pdf = False  # Runtime plots are strictly PNG-only; FINAL PDFs are standalone.


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
    plot_alias = resolve_task4_plot_alias(save_path, alias=alias)
    if plot_alias is not None and not task4_plot_enabled(plot_alias):
        return
    target_fig = fig if fig is not None else plt.gcf()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    target_fig.savefig(save_path, **savefig_kwargs)



def _resolve_task4_total_event_charge_series(
    df: pd.DataFrame,
) -> tuple[pd.Series | None, str | None]:
    for charge_column in ("event_charge", "tim_event_charge"):
        if charge_column not in df.columns:
            continue
        candidate = pd.to_numeric(df[charge_column], errors="coerce")
        if candidate.notna().sum() > 0 and (candidate > 0).any():
            return candidate.astype(float), charge_column

    plane_sum_columns = [
        column_name
        for column_name in ("p1_qsum", "p2_qsum", "p3_qsum", "p4_qsum")
        if column_name in df.columns
    ]
    if plane_sum_columns:
        candidate = (
            df.loc[:, plane_sum_columns]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0.0)
            .sum(axis=1)
            .astype(float)
        )
        if candidate.notna().sum() > 0 and (candidate > 0).any():
            return candidate, "+".join(plane_sum_columns)

    strip_columns = [
        column_name
        for column_name in df.columns
        if re.fullmatch(r"p[1-4]_s[1-4]_qsum", str(column_name))
    ]
    if strip_columns:
        candidate = (
            df.loc[:, strip_columns]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0.0)
            .sum(axis=1)
            .astype(float)
        )
        if candidate.notna().sum() > 0 and (candidate > 0).any():
            return candidate, "+".join(strip_columns)

    return None, None


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

def _task4_config_float(
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


def _curve_fit_checked(*args, **kwargs):
    """Run curve_fit while suppressing known covariance-only warnings."""
    try:
        with warnings.catch_warnings():
            for message, category in _CURVE_FIT_WARNING_FILTERS:
                warnings.filterwarnings(
                    "ignore",
                    message=message,
                    category=category,
                )
            popt, pcov = curve_fit(*args, **kwargs)
    except (RuntimeError, ValueError, OverflowError, FloatingPointError, linalg.LinAlgError) as exc:
        raise RuntimeError(f"curve_fit failed: {exc}") from exc

    popt = np.asarray(popt, dtype=float)
    if popt.ndim != 1 or not np.all(np.isfinite(popt)):
        raise RuntimeError("curve_fit returned non-finite parameters")
    return popt, pcov


def plot_ts_with_side_hist(df, columns, time_col, title, width_ratios=(3, 1)):
    """Plot time series with side histograms for each column."""
    global fig_idx
    if df.empty:
        return
    n_vars = len(columns)
    fig, axes = plt.subplots(
        n_vars, 2, figsize=(14, 2.2 * n_vars),
        gridspec_kw={"width_ratios": width_ratios},
        sharex="col"
    )
    if n_vars == 1:
        axes = np.array([axes])
    for row_idx, col in enumerate(columns):
        ts_ax, hist_ax = axes[row_idx]
        if col not in df.columns:
            ts_ax.set_visible(False)
            hist_ax.set_visible(False)
            continue
        series = df[col].dropna()
        series = series[np.isfinite(series)]
        if series.empty:
            ts_ax.set_visible(False)
            hist_ax.set_visible(False)
            continue
        ts_ax.plot(df[time_col], df[col], ".", ms=1, alpha=0.8)
        ts_ax.set_ylabel(col)
        ts_ax.grid(True, alpha=0.3)
        bins, hist_range = _safe_hist_params(series, max_bins=50)
        if bins is None:
            hist_ax.set_visible(False)
            continue
        hist_ax.hist(
            series,
            bins=bins,
            range=hist_range,
            orientation="horizontal",
            color="C1",
            alpha=0.8,
        )
        # Let each histogram choose its own x-limits so peaks don't compress other panels
        hist_ax.set_autoscale_on(True)
        hist_ax.autoscale_view()
        hist_ax.set_xlabel("count")
        hist_ax.grid(True, alpha=0.2)
    axes[-1, 0].set_xlabel(time_col)
    plt.suptitle(title, fontsize=12)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    if save_plots:
        final_filename = f"{fig_idx}_{title.replace(' ', '_')}.png"
        fig_idx += 1
        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format="png")
    if show_plots:
        plt.show()
    plt.close()

# Reject-only histograms/scatters ------------------------------------------------
def plot_histograms_grid(df, columns, title_prefix, max_bins=60, cols_per_fig=16):
    """Plot histograms for many columns, chunked into multiple figures."""
    global fig_idx
    if df.empty:
        return
    if not columns:
        return
    cols_per_fig = max(1, int(cols_per_fig))
    ncols = min(4, cols_per_fig)
    for chunk_start in range(0, len(columns), cols_per_fig):
        chunk = columns[chunk_start:chunk_start + cols_per_fig]
        if not chunk:
            continue
        nrows = int(math.ceil(len(chunk) / ncols))
        fig, axes = plt.subplots(
            nrows,
            ncols,
            figsize=(4.0 * ncols, 3.0 * nrows),
            constrained_layout=True,
        )
        axes = np.atleast_1d(axes).ravel()
        last_idx = -1
        for idx, col in enumerate(chunk):
            ax = axes[idx]
            last_idx = idx
            if col not in df.columns:
                ax.set_visible(False)
                continue
            series = df[col].dropna()
            if series.empty:
                ax.set_visible(False)
                continue
            if pd.api.types.is_datetime64_any_dtype(series):
                ax.set_visible(False)
                continue
            if pd.api.types.is_bool_dtype(series):
                # Avoid matplotlib warning by coercing bools to ints.
                series = series.astype(np.int8)
                bins, hist_range = 2, (-0.5, 1.5)
            else:
                series = series[np.isfinite(series)]
                if series.empty:
                    ax.set_visible(False)
                    continue
                bins, hist_range = _safe_hist_params(series, max_bins=max_bins)
            if bins is None:
                ax.set_visible(False)
                continue
            ax.hist(series, bins=bins, range=hist_range, alpha=0.75, color="C0")
            ax.set_title(col, fontsize=9)
            ax.tick_params(axis="both", labelsize=8)
            ax.grid(True, alpha=0.2)
        for j in range(last_idx + 1, len(axes)):
            axes[j].set_visible(False)
        title = f"{title_prefix} histograms ({chunk_start + 1}-{chunk_start + len(chunk)})"
        plt.suptitle(title, fontsize=12)
        if save_plots:
            safe_title = re.sub(r"[\\\\/]+", "_", title).replace(" ", "_")
            if len(safe_title) > 180:
                safe_title = safe_title[:180]
            final_filename = f"{fig_idx}_{safe_title}.png"
            fig_idx += 1
            save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
            plot_list.append(save_fig_path)
            save_plot_figure(save_fig_path, format="png")
        if show_plots:
            plt.show()
        plt.close()

def plot_scatter_simple(df, x_col, y_col, title, max_points=200000):
    """Plot a simple scatter with optional downsampling."""
    global fig_idx
    if df.empty:
        return
    if x_col not in df.columns or y_col not in df.columns:
        return
    sub = df[[x_col, y_col]].dropna()
    if sub.empty:
        return
    sub = sub[np.isfinite(sub[x_col]) & np.isfinite(sub[y_col])]
    if sub.empty:
        return
    if len(sub) > max_points:
        sub = sub.sample(n=max_points, random_state=0)
    fig, ax = plt.subplots(figsize=(6.5, 6.0))
    ax.scatter(
        sub[x_col],
        sub[y_col],
        s=2,
        alpha=0.3,
        color="C0",
        edgecolors="none",
    )
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.set_title(title)
    ax.grid(True, alpha=0.2)
    if save_plots:
        safe_title = re.sub(r"[\\\\/]+", "_", title).replace(" ", "_")
        if len(safe_title) > 180:
            safe_title = safe_title[:180]
        final_filename = f"{fig_idx}_{safe_title}.png"
        fig_idx += 1
        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format="png")
    if show_plots:
        plt.show()
    plt.close()

def plot_reject_diagnostics(
    df,
    label,
    basename,
    hist_bins=60,
    cols_per_fig=16,
    scatter_max=200000,
):
    """Create histogram grids and key scatter plots for rejected events."""
    if df.empty:
        return
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if numeric_cols:
        plot_histograms_grid(
            df,
            numeric_cols,
            f"{label}_{basename}",
            max_bins=hist_bins,
            cols_per_fig=cols_per_fig,
        )
    if "theta" in df.columns and "phi" in df.columns:
        plot_scatter_simple(
            df,
            "theta",
            "phi",
            f"{label}_theta_phi_{basename}",
            max_points=scatter_max,
        )
    if "x" in df.columns and "y" in df.columns:
        plot_scatter_simple(
            df,
            "x",
            "y",
            f"{label}_x_y_{basename}",
            max_points=scatter_max,
        )
    elif "det_x" in df.columns and "det_y" in df.columns:
        plot_scatter_simple(
            df,
            "det_x",
            "det_y",
            f"{label}_det_x_det_y_{basename}",
            max_points=scatter_max,
        )

#%%

def plot_residuals_ts_hist(df, prefixes, time_col, title):
    """
    Plot residuals (usual and external variants) per plane with side histograms.
    *prefixes* is a list of (label, usual_prefix, ext_prefix) tuples.
    Each residual type gets its own column; rows are planes.
    """
    global fig_idx
    planes = [1, 2, 3, 4]
    n_cols = len(prefixes)
    fig, axes = plt.subplots(
        len(planes), n_cols * 2,
        figsize=(6 * n_cols, 2.0 * len(planes)),
        gridspec_kw={"width_ratios": sum([[3, 1] for _ in range(n_cols)], [])},
        sharex="col"
    )
    axes = np.atleast_2d(axes)
    axes = axes.reshape(len(planes), n_cols * 2)
    for row_idx, plane in enumerate(planes):
        for col_idx, (label, plane_prefix, ext_prefix) in enumerate(prefixes):
            ts_ax = axes[row_idx, col_idx * 2]
            hist_ax = axes[row_idx, col_idx * 2 + 1]
            col_usual = f"{plane_prefix}{plane}"
            col_ext = f"{ext_prefix}{plane}"
            if col_usual not in df.columns or col_ext not in df.columns:
                ts_ax.set_visible(False)
                hist_ax.set_visible(False)
                continue
            sub = df[[time_col, col_usual, col_ext]].dropna()
            # Drop rows where both residuals are zero (no data)
            sub = sub[(sub[col_usual] != 0) | (sub[col_ext] != 0)]
            if sub.empty:
                ts_ax.set_visible(False)
                hist_ax.set_visible(False)
                continue
            # Plot external first, then usual on top (usual narrower)
            ts_ax.plot(sub[time_col], sub[col_ext], ".", ms=1, label=f"{label}_ext", alpha=0.6)
            ts_ax.plot(sub[time_col], sub[col_usual], ".", ms=1, label=f"{label}", alpha=0.9)
            if col_idx == 0:
                ts_ax.set_ylabel(f"P{plane}")
            ts_ax.grid(True, alpha=0.3)
            ts_ax.legend(fontsize="x-small")
            ext_series = sub[col_ext][np.isfinite(sub[col_ext])]
            usual_series = sub[col_usual][np.isfinite(sub[col_usual])]
            ext_bins, ext_range = _safe_hist_params(ext_series, max_bins=50)
            usual_bins, usual_range = _safe_hist_params(usual_series, max_bins=50)
            if ext_bins is not None:
                hist_ax.hist(
                    ext_series,
                    bins=ext_bins,
                    range=ext_range,
                    orientation="horizontal",
                    alpha=0.5,
                    label=f"{label}_ext",
                )
            if usual_bins is not None:
                hist_ax.hist(
                    usual_series,
                    bins=usual_bins,
                    range=usual_range,
                    orientation="horizontal",
                    alpha=0.8,
                    label=f"{label}",
                )
            hist_ax.set_xlabel("count")
            hist_ax.grid(True, alpha=0.2)
    axes[-1, 0].set_xlabel(time_col)
    plt.suptitle(title, fontsize=12)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    if save_plots:
        final_filename = f"{fig_idx}_{title.replace(' ', '_')}.png"
        fig_idx += 1
        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format="png")
    if show_plots:
        plt.show()
    plt.close()


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


def ensure_global_count_keys(prefixes: Iterable[str]) -> None:
    for prefix in prefixes:
        for tt_value in TT_COUNT_VALUES:
            global_variables.setdefault(f"{prefix}_{tt_value}_count", 0)


def _task4_tt_charge_columns(columns: list[str]) -> list[str]:
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
                for strip in range(1, 5)
                for col in (f"p{plane}_s{strip}_ef_q", f"p{plane}_s{strip}_eb_q")
                if col in df.columns
            ]
        charge_columns = _task4_tt_charge_columns(charge_columns)
        if charge_columns:
            charge_values = df.loc[:, charge_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
            has_charge = charge_values.gt(0.0).any(axis=1)
            tt_str = tt_str.where(~has_charge, tt_str + str(plane))
    tt_values = tt_str.replace("", "0").astype(int)
    target_dtype = df[column_name].dtype if column_name in df.columns else None
    if target_dtype is not None and pd.api.types.is_integer_dtype(target_dtype):
        tt_values = np.asarray(tt_values, dtype=target_dtype)
    df.loc[:, column_name] = tt_values
    return df

def compute_tt_task4_fit_from_charge(df: pd.DataFrame) -> pd.Series:
    """
    Compute tt_task4_fit from observed plane activity, constrained by tt_task3_list.

    A plane can only be active in tt_task4_fit if it was already active in tt_task3_list
    (keep-or-diminish rule). Plane activity is then validated from charge-like
    observables; this intentionally avoids extension/projection-only occupancy.
    """
    charge_threshold = _task4_parse_optional_float(config.get("tt_task4_fit_plane_charge_threshold"))
    if charge_threshold is None:
        charge_threshold = 0.0

    tt_task3_list_series: pd.Series | None = None
    if "tt_task3_list" in df.columns:
        tt_task3_list_series = pd.to_numeric(df["tt_task3_list"], errors="coerce").fillna(0).astype(int)
    elif "tt_task3_list" in df.columns:
        tt_task3_list_series = pd.to_numeric(df["tt_task3_list"], errors="coerce").fillna(0).astype(int)

    if tt_task3_list_series is not None:
        tt_task3_list_labels = tt_task3_list_series.astype(str)
    else:
        tt_task3_list_labels = pd.Series("", index=df.index, dtype="object")

    tt_str = pd.Series("", index=df.index, dtype="object")
    for plane in range(1, 5):
        if tt_task3_list_series is not None:
            allowed_by_tt_task3_list = tt_task3_list_labels.str.contains(str(plane), regex=False)
        else:
            allowed_by_tt_task3_list = pd.Series(True, index=df.index)

        candidate_columns: list[str] = [
            col_name
            for col_name in (
                f"charge_{plane}",
                f"tim_charge_{plane}",
                f"p{plane}_qsum",
            )
            if col_name in df.columns
        ]
        if not candidate_columns:
            candidate_columns = [
                f"p{plane}_s{strip}_qsum" for strip in range(1, 5) if f"p{plane}_s{strip}_qsum" in df.columns
            ]
        if not candidate_columns:
            continue

        charge_values = (
            df.loc[:, candidate_columns]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0.0)
        )
        has_charge = charge_values.gt(float(charge_threshold)).any(axis=1)
        plane_active = allowed_by_tt_task3_list & has_charge
        tt_str = tt_str.where(~plane_active, tt_str + str(plane))
    return tt_str.replace("", "0").astype(int)


def get_task4_tt_column(df_input: pd.DataFrame, preferred: str | None = None) -> str | None:
    if preferred is None:
        preferred = TASK4_PRIMARY_TT_COLUMN
    if preferred in df_input.columns:
        return preferred
    return None

def get_task4_tt_series(df_input: pd.DataFrame, preferred: str | None = None) -> pd.Series:
    if preferred is None:
        preferred = TASK4_PRIMARY_TT_COLUMN
    tt_col = get_task4_tt_column(df_input, preferred=preferred)
    if tt_col is None:
        return pd.Series(0, index=df_input.index, dtype=int)
    return pd.to_numeric(df_input[tt_col], errors="coerce").fillna(0).astype(int)

def refresh_task4_trigger_columns(
    df_input: pd.DataFrame,
) -> pd.DataFrame:
    df_output = df_input.copy()
    if "tt_task3_list" not in df_output.columns:
        df_output = compute_tt(df_output, "tt_task3_list", TASK4_EXTENSION_TT_COLUMNS)
    else:
        target_dtype = df_output["tt_task3_list"].dtype
        tt_task3_values = (
            pd.to_numeric(df_output["tt_task3_list"], errors="coerce")
            .fillna(0)
            .astype(np.int32)
        )
        if pd.api.types.is_integer_dtype(target_dtype):
            tt_task3_values = np.asarray(tt_task3_values, dtype=target_dtype)
        df_output.loc[:, "tt_task3_list"] = (
            tt_task3_values
        )
    tt_task4_fit_series = compute_tt_task4_fit_from_charge(df_output)
    if TASK4_PRIMARY_TT_COLUMN in df_output.columns and pd.api.types.is_integer_dtype(df_output[TASK4_PRIMARY_TT_COLUMN].dtype):
        tt_task4_fit_series = np.asarray(tt_task4_fit_series, dtype=df_output[TASK4_PRIMARY_TT_COLUMN].dtype)
    df_output.loc[:, TASK4_PRIMARY_TT_COLUMN] = tt_task4_fit_series
    return df_output

def _resolve_task4_track_efficiency_fiducial_cfg(config_obj: Mapping[str, object]) -> dict[str, object]:
    return {
        "event_charge_left": _task4_get_optional_config_float(config_obj, "fiducial_event_charge_left"),
        "event_charge_right": _task4_get_optional_config_float(config_obj, "fiducial_event_charge_right"),
        # "x_left": _task4_get_optional_config_float(
        #     config_obj,
        #     "fiducial_x_left",
        #     "fiducial_x_plane_1_left",
        # ),
        # "x_right": _task4_get_optional_config_float(
        #     config_obj,
        #     "fiducial_x_right",
        #     "fiducial_x_plane_1_right",
        # ),
        "theta_left_deg": _task4_get_optional_config_float(config_obj, "fiducial_theta_left"),
        "theta_right_deg": _task4_get_optional_config_float(config_obj, "fiducial_theta_right"),
        "x_by_plane": {
            plane: {
                "left": _task4_get_optional_config_float(config_obj, f"fiducial_x_plane_{plane}_left"),
                "right": _task4_get_optional_config_float(config_obj, f"fiducial_x_plane_{plane}_right"),
            }
            for plane in range(1, 5)
        },
        "y_by_plane": {
            plane: {
                "left": _task4_get_optional_config_float(config_obj, f"fiducial_y_plane_{plane}_left"),
                "right": _task4_get_optional_config_float(config_obj, f"fiducial_y_plane_{plane}_right"),
            }
            for plane in range(1, 5)
        },
    }

def _task4_resolve_region_bounds(
    left_limit: float | None,
    right_limit: float | None,
    physical_left: float,
    physical_right: float,
) -> tuple[float, float]:
    left = float(left_limit) if left_limit is not None else float(physical_left)
    right = float(right_limit) if right_limit is not None else float(physical_right)
    left = max(float(physical_left), min(left, float(physical_right)))
    right = max(float(physical_left), min(right, float(physical_right)))
    if right <= left:
        return float(physical_left), float(physical_right)
    return left, right

def _task4_track_efficiency_fiducial_is_active(cfg_fiducial: Mapping[str, object]) -> bool:
    scalar_keys = (
        "event_charge_left",
        "event_charge_right",
        # "x_left",
        # "x_right",
        "theta_left_deg",
        "theta_right_deg",
    )
    for key in scalar_keys:
        if cfg_fiducial.get(key, None) is not None:
            return True
    x_by_plane = cfg_fiducial.get("x_by_plane", {})
    if isinstance(x_by_plane, Mapping):
        for plane_cfg in x_by_plane.values():
            if not isinstance(plane_cfg, Mapping):
                continue
            if plane_cfg.get("left", None) is not None or plane_cfg.get("right", None) is not None:
                return True
    y_by_plane = cfg_fiducial.get("y_by_plane", {})
    if isinstance(y_by_plane, Mapping):
        for plane_cfg in y_by_plane.values():
            if not isinstance(plane_cfg, Mapping):
                continue
            if plane_cfg.get("left", None) is not None or plane_cfg.get("right", None) is not None:
                return True
    return False

def _task4_resolve_efficiency_param_hash(
    explicit_param_hash: object,
    df_input: pd.DataFrame,
) -> str:
    if explicit_param_hash is not None:
        text = str(explicit_param_hash).strip()
        if text:
            return text
    if "param_hash" in df_input.columns:
        param_series = df_input["param_hash"].astype(str).str.strip()
        nonempty = param_series[(param_series != "") & (param_series.str.lower() != "nan")]
        if not nonempty.empty:
            return str(nonempty.iloc[0])
    return ""

def normalize_task4_event_component_blocks(
    df_input: pd.DataFrame,
    *,
    apply_changes: bool,
) -> dict[str, int]:
    """Zero the full Task 4 event block when any atomic event component is zero."""
    event_cols = [col for col in TASK4_EVENT_ATOMIC_COLUMNS if col in df_input.columns]
    if not event_cols:
        return {
            "rows_affected": 0,
            "values_zeroed": 0,
            "column_count": 0,
        }

    block_values = np.column_stack(
        [
            pd.to_numeric(df_input[col], errors="coerce").to_numpy(dtype=float, copy=True)
            for col in event_cols
        ]
    )
    any_zero = np.any(block_values == 0.0, axis=1)
    all_zero = np.all(block_values == 0.0, axis=1)
    partial_zero = any_zero & ~all_zero

    values_zeroed = 0
    for idx in range(len(event_cols)):
        if not np.any(partial_zero):
            break
        values_zeroed += int(np.count_nonzero(block_values[partial_zero, idx]))

    if apply_changes and np.any(any_zero):
        block_values[any_zero, :] = 0.0
        df_input.loc[:, event_cols] = block_values

    return {
        "rows_affected": int(np.count_nonzero(partial_zero)),
        "values_zeroed": int(values_zeroed),
        "column_count": len(event_cols),
    }


def load_iteration_settings(cfg):
    number_of_det_executions = max(1, int(cfg.get("number_of_det_executions", 1)))
    number_of_tt_executions = max(1, int(cfg.get("number_of_tt_executions", 1)))
    return (
        number_of_det_executions,
        cfg["fixed_speed"],
        cfg["res_ana_removing_planes"],
        number_of_tt_executions,
        cfg.get("complete_reanalysis", False),
        cfg.get("limit_number", None),
    )

def initialize_task4_runtime_context(
    cfg: dict[str, object],
    metadata_store: dict[str, object],
    namespace: dict[str, object],
    *,
    announce_fit_method: bool = False,
    announce_geometry: bool = False,
) -> dict[str, object]:
    runtime: dict[str, object] = {
        "fast_mode": False,
        "debug_mode": False,
        "last_file_test": cfg["last_file_test"],
        "crontab_execution": cfg["crontab_execution"],
    }

    (
        number_of_det_executions,
        fixed_speed,
        res_ana_removing_planes,
        number_of_tt_executions,
        complete_reanalysis,
        limit_number,
    ) = load_iteration_settings(cfg)
    runtime.update(
        {
            "number_of_det_executions": number_of_det_executions,
            "fixed_speed": fixed_speed,
            "res_ana_removing_planes": res_ana_removing_planes,
            "number_of_tt_executions": number_of_tt_executions,
            "complete_reanalysis": complete_reanalysis,
            "limit_number": limit_number,
            "limit": limit_number is not None,
        }
    )

    fit_method = str(cfg.get("fit_method", "both")).strip().lower()
    if fit_method not in {"detached", "timtrack", "both"}:
        print(f"Warning: Invalid fit_method='{fit_method}'. Falling back to 'both'.")
        fit_method = "both"
    runtime.update(
        {
            "fit_method": fit_method,
            "run_detached_fit": fit_method in {"detached", "both"},
            "run_timtrack_fit": fit_method in {"timtrack", "both"},
        }
    )
    if announce_fit_method:
        print(f"Fitting mode selected: fit_method='{fit_method}'")

    runtime.update(
        {
            "T_side_left_pre_cal_debug": cfg.get("T_side_left_pre_cal_debug", -500),
            "T_side_right_pre_cal_debug": cfg.get("T_side_right_pre_cal_debug", 500),
            "T_side_left_pre_cal_default": cfg.get("T_side_left_pre_cal_default", -200),
            "T_side_right_pre_cal_default": cfg.get("T_side_right_pre_cal_default", -100),
            "T_side_left_pre_cal_ST": cfg.get("T_side_left_pre_cal_ST", -200),
            "T_side_right_pre_cal_ST": cfg.get("T_side_right_pre_cal_ST", -50),
        }
    )

    runtime["T_sum_RPC_left"] = _task4_config_float(
        cfg,
        "T_sum_RPC_left",
        "plane_combination_plane_t_sum_sum_left",
        "plane_combination_same_plane_t_sum_sum_left",
        "plane_combination_self_t_sum_sum_left",
        default=-25.0,
    )
    runtime["T_sum_RPC_right"] = _task4_config_float(
        cfg,
        "T_sum_RPC_right",
        "plane_combination_plane_t_sum_sum_right",
        "plane_combination_same_plane_t_sum_sum_right",
        "plane_combination_self_t_sum_sum_right",
        default=25.0,
    )

    det_phi_filter_abs = abs(
        float(cfg.get("det_phi_filter_abs", cfg.get("det_phi_right_filter", 3.141592)))
    )
    runtime.update(
        {
            "det_pos_filter": cfg["det_pos_filter"],
            "det_theta_left_filter": cfg["det_theta_left_filter"],
            "det_theta_right_filter": cfg["det_theta_right_filter"],
            "det_phi_filter_abs": det_phi_filter_abs,
            "det_phi_right_filter": det_phi_filter_abs,
            "det_phi_left_filter": -det_phi_filter_abs,
            "det_slowness_filter_left": cfg["det_slowness_filter_left"],
            "det_slowness_filter_right": cfg["det_slowness_filter_right"],
            "det_res_ystr_filter": cfg["det_res_ystr_filter"],
            "det_res_tsum_filter": cfg["det_res_tsum_filter"],
            "det_res_tdif_filter": cfg["det_res_tdif_filter"],
            "det_ext_res_ystr_filter": cfg["det_ext_res_ystr_filter"],
            "det_ext_res_tsum_filter": cfg["det_ext_res_tsum_filter"],
            "det_ext_res_tdif_filter": cfg["det_ext_res_tdif_filter"],
            "proj_filter": cfg["proj_filter"],
            "res_ystr_filter": cfg["res_ystr_filter"],
            "res_tsum_filter": cfg["res_tsum_filter"],
            "res_tdif_filter": cfg["res_tdif_filter"],
            "ext_res_ystr_filter": cfg["ext_res_ystr_filter"],
            "ext_res_tsum_filter": cfg["ext_res_tsum_filter"],
            "ext_res_tdif_filter": cfg["ext_res_tdif_filter"],
            "event_s_err_left": cfg.get("event_s_err_left", -0.0003),
            "event_s_err_right": cfg.get("event_s_err_right", 0.0003),
            "coincidence_window_cal_ns": cfg["coincidence_window_cal_ns"],
            "coincidence_window_cal_number_of_points": cfg["coincidence_window_cal_number_of_points"],
            "beta": cfg["beta"],
            "strip_speed_factor_of_c": cfg["strip_speed_factor_of_c"],
            "strip_length": cfg["strip_length"],
            "narrow_strip": cfg["narrow_strip"],
            "wide_strip": cfg["wide_strip"],
            "d0": cfg["d0"],
            "cocut": cfg["cocut"],
            "iter_max": cfg["iter_max"],
            "anc_sy": cfg["anc_sy"],
            "anc_sts": cfg["anc_sts"],
            "anc_std": cfg["anc_std"],
            "anc_sz": cfg["anc_sz"],
            "n_planes_timtrack": cfg["n_planes_timtrack"],
            "T_clip_min_debug": cfg.get("T_clip_min_debug", -500),
            "T_clip_max_debug": cfg.get("T_clip_max_debug", 500),
            "Q_clip_min_debug": cfg.get("Q_clip_min_debug", -500),
            "Q_clip_max_debug": cfg.get("Q_clip_max_debug", 500),
            "num_bins_debug": cfg.get("num_bins_debug", 100),
            "T_clip_min_default": cfg.get("T_clip_min_default", -300),
            "T_clip_max_default": cfg.get("T_clip_max_default", 100),
            "Q_clip_min_default": cfg.get("Q_clip_min_default", 0),
            "Q_clip_max_default": cfg.get("Q_clip_max_default", 500),
            "num_bins_default": cfg.get("num_bins_default", 100),
            "T_clip_min_ST": cfg.get("T_clip_min_ST", -300),
            "T_clip_max_ST": cfg.get("T_clip_max_ST", 100),
            "Q_clip_min_ST": cfg.get("Q_clip_min_ST", 0),
            "Q_clip_max_ST": cfg.get("Q_clip_max_ST", 500),
            "time_window_fitting": cfg["time_window_fitting"],
            "charge_plot_limit_left": cfg["charge_plot_limit_left"],
            "charge_plot_limit_right": cfg["charge_plot_limit_right"],
            "charge_plot_event_limit_right": cfg.get("charge_plot_event_limit_right", 400),
            "Q_sum_color": "orange",
            "Q_dif_color": "red",
            "T_sum_color": "blue",
            "T_dif_color": "green",
        }
    )

    runtime["pos_filter"] = runtime["det_pos_filter"]
    runtime["t0_left_filter"] = runtime["T_sum_RPC_left"]
    runtime["t0_right_filter"] = runtime["T_sum_RPC_right"]
    runtime["slowness_filter_left"] = runtime["det_slowness_filter_left"]
    runtime["slowness_filter_right"] = runtime["det_slowness_filter_right"]
    runtime["theta_left_filter"] = runtime["det_theta_left_filter"]
    runtime["theta_right_filter"] = runtime["det_theta_right_filter"]
    runtime["phi_left_filter"] = runtime["det_phi_left_filter"]
    runtime["phi_right_filter"] = runtime["det_phi_right_filter"]

    fig_idx, plot_list = ensure_plot_state(namespace)
    runtime["fig_idx"] = fig_idx
    runtime["plot_list"] = plot_list

    runtime["time_dif_distance"] = 30
    runtime["time_dif_reference"] = np.array([
        [-0.0573, 0.031275, 1.033875, 0.761475],
        [-0.914, -0.873975, -0.19815, 0.452025],
        [0.8769, 1.2008, 1.014, 2.43915],
        [1.508825, 2.086375, 1.6876, 3.023575],
    ])
    runtime["charge_sum_distance"] = 30
    runtime["charge_sum_reference"] = np.array([
        [89.4319, 98.19605, 95.99055, 91.83875],
        [96.55775, 94.50385, 94.9254, 91.0775],
        [92.12985, 92.23395, 90.60545, 95.5214],
        [93.75635, 93.57425, 93.07055, 89.27305],
    ])
    runtime["charge_dif_distance"] = 30
    runtime["charge_dif_reference"] = np.array([
        [4.512, 0.58715, 1.3204, -1.3918],
        [-4.50885, 0.918, -3.39445, -0.12325],
        [-3.8931, -3.28515, 3.27295, 1.0554],
        [-2.29505, 0.012, 2.49045, -2.14565],
    ])
    runtime["time_sum_distance"] = 30
    runtime["time_sum_reference"] = np.array([
        [0.0, -0.3886308, -0.53020947, 0.33711737],
        [-0.80494094, -0.68836069, -2.01289387, -1.13481931],
        [-0.23899338, -0.51373738, 0.50845317, 0.11685095],
        [0.33586385, 1.08329847, 0.91410244, 0.58815813],
    ])

    runtime["T_F_left_pre_cal"] = runtime["T_side_left_pre_cal_default"]
    runtime["T_F_right_pre_cal"] = runtime["T_side_right_pre_cal_default"]
    runtime["T_B_left_pre_cal"] = runtime["T_side_left_pre_cal_default"]
    runtime["T_B_right_pre_cal"] = runtime["T_side_right_pre_cal_default"]
    runtime["T_F_left_pre_cal_ST"] = runtime["T_side_left_pre_cal_ST"]
    runtime["T_F_right_pre_cal_ST"] = runtime["T_side_right_pre_cal_ST"]
    runtime["T_B_left_pre_cal_ST"] = runtime["T_side_left_pre_cal_ST"]
    runtime["T_B_right_pre_cal_ST"] = runtime["T_side_right_pre_cal_ST"]

    y_widths = [
        np.array([runtime["wide_strip"], runtime["wide_strip"], runtime["wide_strip"], runtime["narrow_strip"]]),
        np.array([runtime["narrow_strip"], runtime["wide_strip"], runtime["wide_strip"], runtime["wide_strip"]]),
    ]
    runtime["y_widths"] = y_widths
    runtime["y_pos_T"] = [y_pos(y_widths[0]), y_pos(y_widths[1])]
    runtime["y_width_P1_and_P3"] = y_widths[0]
    runtime["y_width_P2_and_P4"] = y_widths[1]
    runtime["y_pos_P1_and_P3"] = y_pos(runtime["y_width_P1_and_P3"])
    runtime["y_pos_P2_and_P4"] = y_pos(runtime["y_width_P2_and_P4"])
    runtime["total_width"] = np.sum(runtime["y_width_P1_and_P3"])

    c_mm_ns = c / 1000000
    runtime["c_mm_ns"] = c_mm_ns
    if announce_geometry:
        print(c_mm_ns)

    runtime["muon_speed"] = runtime["beta"] * c_mm_ns
    runtime["strip_speed"] = runtime["strip_speed_factor_of_c"] * c_mm_ns
    runtime["tdiff_to_x"] = runtime["strip_speed"]
    runtime["vc"] = runtime["beta"] * c_mm_ns
    runtime["sc"] = 1 / runtime["vc"]
    runtime["ss"] = 1 / runtime["strip_speed"]
    runtime["nplan"] = runtime["n_planes_timtrack"]
    runtime["lenx"] = runtime["strip_length"]
    runtime["anc_sx"] = runtime["tdiff_to_x"] * runtime["anc_std"]

    runtime["T_clip_min"] = runtime["T_clip_min_default"]
    runtime["T_clip_max"] = runtime["T_clip_max_default"]
    runtime["Q_clip_min"] = runtime["Q_clip_min_default"]
    runtime["Q_clip_max"] = runtime["Q_clip_max_default"]
    runtime["num_bins"] = runtime["num_bins_default"]

    metadata_store["unc_y"] = runtime["anc_sy"]
    metadata_store["unc_tsum"] = runtime["anc_sts"]
    metadata_store["unc_tdif"] = runtime["anc_std"]
    return runtime


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

def _gaussian_model(x: np.ndarray, mu: float, sigma: float, amplitude: float) -> np.ndarray:
    sigma = np.abs(float(sigma))
    if sigma == 0:
        sigma = 1e-12
    return amplitude * np.exp(-((x - mu) ** 2) / (2 * sigma ** 2))

def _fit_gaussian_mu_sigma(series: pd.Series, quantile: float = 0.99) -> tuple[float, float]:
    """Return Gaussian (mu, sigma) using the same histogram-fit logic as the residual plots."""
    arr = np.asarray(series, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 10:
        return np.nan, np.nan

    hist_data, bin_edges = np.histogram(arr, bins=50)
    if hist_data.size == 0 or np.max(hist_data) <= 0:
        return np.nan, np.nan
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    try:
        lower_q, upper_q = np.quantile(arr, [1.0 - quantile, quantile])
        filt_data = arr[(arr >= lower_q) & (arr <= upper_q)]
        if filt_data.size < 2:
            filt_data = arr
        sigma0 = float(np.nanstd(filt_data))
        if not np.isfinite(sigma0) or sigma0 <= 0:
            sigma0 = float(np.nanstd(arr))
        if not np.isfinite(sigma0) or sigma0 <= 0:
            return np.nan, np.nan
        popt, _ = _curve_fit_checked(
            _gaussian_model,
            bin_centers,
            hist_data,
            p0=[float(np.nanmean(filt_data)), sigma0, float(np.max(hist_data))],
            maxfev=10000,
        )
        mu = float(popt[0])
        sigma = float(abs(popt[1]))
    except Exception:
        return np.nan, np.nan
    if not np.isfinite(mu) or not np.isfinite(sigma) or sigma <= 0:
        return np.nan, np.nan
    return mu, sigma

def _fit_gaussian_sigma(series: pd.Series, quantile: float = 0.99) -> float:
    """Return Gaussian sigma using the same histogram-fit logic as the residual plots."""
    _, sigma = _fit_gaussian_mu_sigma(series, quantile=quantile)
    return sigma

def compute_timtrack_gaussian_sigma_chi2(
    sigma_source_df: pd.DataFrame,
    target_df: pd.DataFrame,
    *,
    combo_tt: int = 1234,
    quantile: float = 0.99,
    output_col: str = "tim_th_chi_sigmafit_1234",
) -> None:
    """Build a 1234-only chi2 using Gaussian-fit residual sigmas from timtrack residual columns."""
    sigma_tt_col = get_task4_tt_column(sigma_source_df)
    target_tt_col = get_task4_tt_column(target_df)
    if sigma_tt_col is None or target_tt_col is None:
        target_df[output_col] = np.nan
        return

    residual_groups = (
        ("ystr", "tim_res_ystr"),
        ("tsum", "tim_res_tsum"),
        ("tdif", "tim_res_tdif"),
    )
    sigma_source_tt = pd.to_numeric(sigma_source_df[sigma_tt_col], errors="coerce")
    sigma_fit_df = sigma_source_df.loc[sigma_source_tt == float(combo_tt)]

    mu_vector = []
    sigma_vector = []
    sigma_labels = []
    for metric_name, prefix in residual_groups:
        for plane in range(1, 5):
            col = f"{prefix}_{plane}"
            if col in sigma_fit_df.columns:
                mu, sigma = _fit_gaussian_mu_sigma(sigma_fit_df[col], quantile=quantile)
            else:
                mu, sigma = np.nan, np.nan
            mu_vector.append(mu)
            sigma_vector.append(sigma)
            sigma_labels.append(col)
            global_variables[f"{col}_{combo_tt}_gauss_mu"] = mu
            global_variables[f"{col}_{combo_tt}_gauss_sigma"] = sigma

    mu_vector_arr = np.asarray(mu_vector, dtype=float)
    sigma_vector_arr = np.asarray(sigma_vector, dtype=float)
    target_df[output_col] = np.nan
    valid_sigma_mask = np.isfinite(sigma_vector_arr) & (sigma_vector_arr > 0)
    if not valid_sigma_mask.all():
        missing_cols = [label for label, ok in zip(sigma_labels, valid_sigma_mask) if not ok]
        print(
            f"[timtrack_sigmafit_chi2] unable to build {output_col}; missing/invalid sigma for: "
            f"{', '.join(missing_cols)}"
        )
        global_variables[f"{output_col}_valid_sigma_count"] = int(valid_sigma_mask.sum())
        return

    residual_cols = list(sigma_labels)
    residual_matrix = np.column_stack([
        pd.to_numeric(target_df[col], errors="coerce").to_numpy(dtype=float, copy=False)
        for col in residual_cols
    ])
    target_tt = pd.to_numeric(target_df[target_tt_col], errors="coerce").to_numpy(dtype=float, copy=False)
    valid_rows = (target_tt == float(combo_tt)) & np.isfinite(residual_matrix).all(axis=1)
    if np.any(valid_rows):
        scaled = (residual_matrix[valid_rows] - mu_vector_arr) / sigma_vector_arr
        target_df.loc[valid_rows, output_col] = np.sum(scaled ** 2, axis=1)

    mu_matrix = mu_vector_arr.reshape(3, 4)
    sigma_matrix = sigma_vector_arr.reshape(3, 4)
    global_variables[f"{output_col}_mu_matrix"] = np.array2string(mu_matrix, precision=6, suppress_small=False)
    global_variables[f"{output_col}_sigma_matrix"] = np.array2string(sigma_matrix, precision=6, suppress_small=False)
    print(
        f"[timtrack_sigmafit_chi2] built {output_col} for tt={combo_tt} | "
        f"valid_rows={int(valid_rows.sum())} | "
        f"mus(ystr/tsum/tdif)xplane={np.array2string(mu_matrix, precision=4, suppress_small=False)} | "
        f"sigmas(ystr/tsum/tdif)xplane={np.array2string(sigma_matrix, precision=4, suppress_small=False)}"
    )
    global_variables[f"{output_col}_valid_sigma_count"] = int(valid_sigma_mask.sum())
    global_variables[f"{output_col}_filled_rows"] = int(valid_rows.sum())


def record_filter_metric(name: str, removed: float, total: float) -> None:
    """Record percentage removed for a filter."""
    pct = 0.0 if total == 0 else 100.0 * float(removed) / float(total)
    filter_metrics[name] = round(pct, 4)
    _log_filter_metrics_message(
        f"[filter-metrics] {name}: removed {removed} of {total} ({pct:.2f}%)"
    )

def record_residual_sigmas(df: pd.DataFrame) -> None:
    """Fit Gaussian sigmas for residual columns per track combination and plane."""
    tt_col = "tt_task3_list" if "tt_task3_list" in df.columns else "tt_task3_list"
    if tt_col not in df.columns:
        return

    processed = df[tt_col].astype(str)
    for combo in TRACK_COMBINATIONS:
        combo_str = str(combo)
        combo_mask = processed == combo_str
        combo_df = df.loc[combo_mask]
        for plane in range(1, 5):
            if str(plane) not in combo_str:
                continue  # skip planes not present in the trigger combination
            for metric in RESIDUAL_SERIES:
                if metric.startswith("ext_") and len(combo_str) < 3:
                    continue  # external residuals need at least 3 planes
                col = f"{metric}_{plane}"
                key = f"{col}_{combo_str}_sigma"
                if col not in df.columns or combo_df.empty:
                    continue
                sigma = _fit_gaussian_sigma(combo_df[col])
                if np.isnan(sigma):
                    continue  # avoid recording meaningless NaNs
                global_variables[key] = sigma


def _zpos_from_conf(row):
    return np.array([row.get(f"P{i}", np.nan) for i in range(1, 5)])


# ---------------------------------------------------------------------------
# 1. Geometrical line fit (orthogonal-distance regression) ------------------
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ---------------------------- Loop starts here -----------------------------
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Vectorized replacement for the per-event detached fitting loop.
# Groups events by active-plane bitmask; within each group a single batched
# np.linalg.svd call replaces N individual calls. np.polyfit is replaced by
# the closed-form OLS formula so it can be applied across the batch in one go.
# Numerically identical to the original per-event loop.
# ---------------------------------------------------------------------------
def _detached_vectorized(
    det_Q, det_Tdif, det_Y, det_Tsum,
    z_positions, tdiff_to_x,
    anc_sx, anc_sy, anc_sz, anc_sts,
    n, nplan,
    fit_res, slow_res,
    ext_res_ystr, ext_res_tsum, ext_res_tdif,
):
    _sx2sy2sz2 = float(anc_sx**2 + anc_sy**2 + anc_sz**2)

    def _batch_line_fit(x_b, y_b, z_sel):
        """Batched SVD line fit. x_b, y_b: (n_g, n_pl); z_sel: (n_pl,)."""
        n_g, n_pl = x_b.shape
        z_br  = np.broadcast_to(z_sel, (n_g, n_pl))
        pts   = np.stack([x_b, y_b, z_br], axis=2)        # (n_g, n_pl, 3)
        c     = pts.mean(axis=1, keepdims=True)             # (n_g,  1,   3)
        pts_c = pts - c
        _, _, vt = np.linalg.svd(pts_c, full_matrices=False)
        d = vt[:, 0, :].copy()                              # (n_g, 3)
        d[d[:, 2] < 0] *= -1
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        c3  = c[:, 0, :]
        t0  = np.where(d[:, 2] != 0.0, -c3[:, 2] / d[:, 2], np.nan)
        xz0 = c3[:, 0] + t0 * d[:, 0]
        yz0 = c3[:, 1] + t0 * d[:, 1]
        pdot = np.einsum('npi,ni->np', pts_c, d)            # (n_g, n_pl)
        proj = pdot[:, :, np.newaxis] * d[:, np.newaxis, :] # (n_g, n_pl, 3)
        res  = pts_c - proj
        res_td = res[:, :, 0] / tdiff_to_x
        res_y  = res[:, :, 1]
        chi2   = np.einsum('npi,npi->n', res, res) / _sx2sy2sz2
        return d, xz0, yz0, chi2, res_td, res_y

    def _batch_slowness(xz0, yz0, d, z_sel, Tsum_g):
        """Vectorized polyfit(s_rel, t_rel, 1) for a batch of events."""
        n_g, n_pl = Tsum_g.shape
        x_fit = xz0[:, np.newaxis] + d[:, 0:1] * z_sel / d[:, 2:3]
        y_fit = yz0[:, np.newaxis] + d[:, 1:2] * z_sel / d[:, 2:3]
        pos   = np.stack([x_fit, y_fit, np.broadcast_to(z_sel, (n_g, n_pl))], axis=2)
        rdist = np.einsum('npi,ni->np', pos, d)             # (n_g, n_pl)
        s_rel = rdist - rdist[:, 0:1]
        t_rel = Tsum_g - Tsum_g[:, 0:1]
        s_m   = s_rel.mean(axis=1); t_m = t_rel.mean(axis=1)
        ss2   = np.sum(s_rel ** 2, axis=1)
        st    = np.sum(s_rel * t_rel, axis=1)
        denom = ss2 - n_pl * s_m ** 2
        k     = np.where(np.abs(denom) > 0.0, (st - n_pl * s_m * t_m) / denom, 0.0)
        b     = t_m - k * s_m
        t_fit = k[:, np.newaxis] * s_rel + b[:, np.newaxis]
        res   = t_rel - t_fit
        chi2  = np.sum((res / anc_sts) ** 2, axis=1)
        return k, b, chi2, res, rdist

    q_pos   = det_Q > 0                                              # (n, nplan) bool
    bitmask = (q_pos * (1 << np.arange(nplan))).sum(axis=1).astype(np.int32)

    for bm in np.unique(bitmask):
        if bm == 0:
            continue
        active_idx = np.array([p for p in range(nplan) if bm & (1 << p)], dtype=int)
        n_pl       = len(active_idx)
        if n_pl < 2:
            continue
        plane_ids = active_idx + 1                                    # 1-based
        g_idx     = np.where(bitmask == bm)[0]
        n_g       = len(g_idx)
        z_sel     = z_positions[active_idx]                           # (n_pl,)
        Tdif_g    = det_Tdif[np.ix_(g_idx, active_idx)]
        Y_g       = det_Y   [np.ix_(g_idx, active_idx)]
        Tsum_g    = det_Tsum[np.ix_(g_idx, active_idx)]
        x_g       = tdiff_to_x * Tdif_g
        y_g       = Y_g

        # --- Primary fit ---
        d, xz0, yz0, chi2, res_td, res_y = _batch_line_fit(x_g, y_g, z_sel)
        theta = np.arccos(np.clip(d[:, 2], -1.0, 1.0))
        phi   = np.arctan2(d[:, 1], d[:, 0])
        fit_res['det_x']    [g_idx] = xz0
        fit_res['det_y']    [g_idx] = yz0
        fit_res['det_theta'][g_idx] = theta
        fit_res['det_phi']  [g_idx] = phi
        fit_res['det_chi2_pos'] [g_idx] = chi2
        for k_pl, pid in enumerate(plane_ids):
            fit_res[f'det_res_tdif_{pid}'][g_idx] = res_td[:, k_pl]
            fit_res[f'det_res_ystr_{pid}'][g_idx] = res_y [:, k_pl]

        # --- Slowness ---
        k_slow, b_slow, chi2_slow, res_slow, _ = _batch_slowness(xz0, yz0, d, z_sel, Tsum_g)
        slow_res['det_s']         [g_idx] = k_slow
        slow_res['det_s_ordinate'][g_idx] = b_slow
        slow_res['det_chi2_tsum'] [g_idx] = chi2_slow
        for k_pl, pid in enumerate(plane_ids):
            slow_res[f'det_res_tsum_{pid}'][g_idx] = res_slow[:, k_pl]

        # --- Leave-one-out (requires ≥3 active planes) ---
        if n_pl < 3:
            continue
        for k_exc in range(n_pl):
            lo_k = [j for j in range(n_pl) if j != k_exc]
            if len(lo_k) < 2:
                continue
            pid_exc = int(plane_ids[k_exc])
            out_p   = pid_exc - 1                                     # 0-based output col
            z_lo    = z_sel[lo_k]
            x_lo    = x_g[:, lo_k]
            y_lo    = y_g[:, lo_k]
            ts_lo   = Tsum_g[:, lo_k]

            d_lo, xz0_lo, yz0_lo, _, _, _ = _batch_line_fit(x_lo, y_lo, z_lo)

            z_p    = float(z_sel[k_exc])
            x_pred = xz0_lo + d_lo[:, 0] * z_p / d_lo[:, 2]
            y_pred = yz0_lo + d_lo[:, 1] * z_p / d_lo[:, 2]

            ext_res_tdif[g_idx, out_p] = (x_g[:, k_exc] - x_pred) / tdiff_to_x
            ext_res_ystr[g_idx, out_p] = (y_g[:, k_exc] - y_pred)

            # Tsum external residual
            k_lo, b_lo, _, _, rdist_lo = _batch_slowness(xz0_lo, yz0_lo, d_lo, z_lo, ts_lo)
            pos_p  = np.stack([x_pred, y_pred, np.full(n_g, z_p)], axis=1)
            s_p    = np.einsum('ni,ni->n', pos_p, d_lo) - rdist_lo[:, 0]
            t_p    = Tsum_g[:, k_exc] - ts_lo[:, 0]
            ext_res_tsum[g_idx, out_p] = t_p - (k_lo * s_p + b_lo)


def plot_ts_err_with_hist(df, base_cols, time_col, title):
    """Plot combined data: data TS+hist and error TS+hist (4 columns per variable)."""
    global fig_idx
    if df.empty:
        return
    n_vars = len(base_cols)
    fig, axes = plt.subplots(
        n_vars, 4, figsize=(18, 2.2 * n_vars),
        gridspec_kw={"width_ratios": [3, 1, 3, 1]},
        sharex="col"
    )
    if n_vars == 1:
        axes = np.array([axes])
    for idx, col in enumerate(base_cols):
        ts_ax, hist_ax, ts_err_ax, hist_err_ax = axes[idx]
        if col not in df.columns:
            for ax in (ts_ax, hist_ax, ts_err_ax, hist_err_ax):
                ax.set_visible(False)
            continue
        value_mask = df[col].notna() & np.isfinite(df[col].to_numpy(dtype=float, copy=False))
        plot_df = df.loc[value_mask, [time_col, col]].copy()
        series = plot_df[col]
        if series.empty:
            for ax in (ts_ax, hist_ax, ts_err_ax, hist_err_ax):
                ax.set_visible(False)
            continue
        err_col = f"{col}_err"
        err_series = None
        yerr = None
        if err_col in df.columns:
            err_mask = df[err_col].notna() & np.isfinite(df[err_col].to_numpy(dtype=float, copy=False))
            err_plot_df = df.loc[value_mask & err_mask, [time_col, col, err_col]].copy()
            if not err_plot_df.empty:
                err_series = err_plot_df[err_col]
                yerr = err_series.abs()
                ts_ax.errorbar(err_plot_df[time_col], err_plot_df[col], yerr=yerr, fmt=".", ms=1, alpha=0.85)
            else:
                ts_ax.plot(plot_df[time_col], plot_df[col], ".", ms=1, alpha=0.85)
        else:
            ts_ax.plot(plot_df[time_col], plot_df[col], ".", ms=1, alpha=0.85)
        ts_ax.set_ylabel(col)
        ts_ax.grid(True, alpha=0.3)
        bins, hist_range = _safe_hist_params(series, max_bins=50)
        if bins is not None:
            hist_ax.hist(
                series,
                bins=bins,
                range=hist_range,
                orientation="horizontal",
                color="C2",
                alpha=0.8,
            )
        hist_ax.set_xlabel("count")
        hist_ax.grid(True, alpha=0.2)
        if err_series is not None and not err_series.empty:
            ts_err_ax.plot(err_plot_df[time_col], err_series, ".", ms=1, alpha=0.8, label=f"{col}_err")
            ts_err_ax.grid(True, alpha=0.3)
            ts_err_ax.legend(fontsize="x-small")
            err_bins, err_range = _safe_hist_params(err_series, max_bins=50)
            if err_bins is not None:
                hist_err_ax.hist(
                    err_series,
                    bins=err_bins,
                    range=err_range,
                    orientation="horizontal",
                    color="C4",
                    alpha=0.7,
                )
            hist_err_ax.set_autoscale_on(True)
            hist_err_ax.autoscale_view()
            hist_err_ax.set_xscale("log")
            hist_err_ax.set_xlabel("count")
            hist_err_ax.grid(True, alpha=0.2)
        else:
            ts_err_ax.set_visible(False)
            hist_err_ax.set_visible(False)
    axes[-1, 0].set_xlabel(time_col)
    axes[-1, 2].set_xlabel(time_col)
    plt.suptitle(title, fontsize=12)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    if save_plots:
        final_filename = f"{fig_idx}_{title.replace(' ', '_')}.png"
        fig_idx += 1
        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format="png")
    if show_plots:
        plt.show()
    plt.close()


def fmahd(npar, vin1, vin2, merr): # Mahalanobis distance
    merr_diag = np.diag(merr) if merr.ndim > 1 else merr
    acc = 0.0
    for i in range(npar):
        d = vin1[i] - vin2[i]
        m = merr_diag[i]
        if not np.isfinite(d) or not np.isfinite(m):
            return float("inf")
        if m > 0.0:
            acc += d * d / m
        elif m < 0.0:
            return float("inf")
    if not np.isfinite(acc):
        return float("inf")
    if acc < 0.0:
        if acc > -1e-12:
            acc = 0.0
        else:
            return float("inf")
    return math.sqrt(acc)

def solve_only(matrix, rhs):
    """Solve matrix @ x = rhs (fast path for code paths that do not need covariance)."""
    try:
        return np.linalg.solve(matrix, rhs)
    except np.linalg.LinAlgError:
        return np.linalg.pinv(matrix) @ rhs

def solve_and_covdiag(matrix, rhs):
    """Solve matrix @ x = rhs and return (x, diag(inv(matrix))) with one factorization.

    Fast path computes inverse once and reuses it for both the linear solve and
    covariance-diagonal extraction. Fallback uses pinv once.
    """
    try:
        inv_matrix = np.linalg.inv(matrix)
        sol = inv_matrix @ rhs
        inv_diag = np.diag(inv_matrix)
        return sol, inv_diag
    except np.linalg.LinAlgError:
        matrix_pinv = np.linalg.pinv(matrix)
        return matrix_pinv @ rhs, np.diag(matrix_pinv)

def _accumulate_mk_va(npar, vs, ydat, tsdat, tddat, zi, w_arr, ss, lenx, sc_val, fixed_speed_flag, mk, va):
    """In-place TimTrack accumulator: adds one plane contribution into mk and va.

    Avoids per-plane temporary (npar x npar) and (npar,) allocations from
    return-based helpers in the main fitting hot loop.
    """
    XP = vs[1]
    YP = vs[3]
    S0 = sc_val if fixed_speed_flag else vs[5]
    kz = math.sqrt(1.0 + XP * XP + YP * YP)
    kzi = 1.0 / kz

    w0 = w_arr[0]
    w1 = w_arr[1]
    w2 = w_arr[2]

    zi2 = zi * zi
    sszi = ss * zi
    th = 0.5 * lenx * ss

    # Non-zero entries of the 3 Jacobian rows (g0, g1, g2)
    g0_2 = 1.0
    g0_3 = zi

    g1_1 = kzi * S0 * XP * zi
    g1_3 = kzi * S0 * YP * zi
    g1_4 = 1.0

    g2_0 = ss
    g2_1 = sszi

    # vdmg terms simplify exactly for this linearised model
    vd0 = ydat
    vd1 = tsdat - th
    vd2 = tddat

    # g0 contribution (weight w0)
    mk[2, 2] += w0 * g0_2 * g0_2
    mk[2, 3] += w0 * g0_2 * g0_3
    mk[3, 2] += w0 * g0_3 * g0_2
    mk[3, 3] += w0 * g0_3 * g0_3
    va[2] += w0 * g0_2 * vd0
    va[3] += w0 * g0_3 * vd0

    # g2 contribution (weight w2)
    mk[0, 0] += w2 * g2_0 * g2_0
    mk[0, 1] += w2 * g2_0 * g2_1
    mk[1, 0] += w2 * g2_1 * g2_0
    mk[1, 1] += w2 * g2_1 * g2_1
    va[0] += w2 * g2_0 * vd2
    va[1] += w2 * g2_1 * vd2

    # g1 contribution (weight w1)
    mk[1, 1] += w1 * g1_1 * g1_1
    mk[1, 3] += w1 * g1_1 * g1_3
    mk[3, 1] += w1 * g1_3 * g1_1
    mk[1, 4] += w1 * g1_1 * g1_4
    mk[4, 1] += w1 * g1_4 * g1_1
    mk[3, 3] += w1 * g1_3 * g1_3
    mk[3, 4] += w1 * g1_3 * g1_4
    mk[4, 3] += w1 * g1_4 * g1_3
    mk[4, 4] += w1 * g1_4 * g1_4
    va[1] += w1 * g1_1 * vd1
    va[3] += w1 * g1_3 * vd1
    va[4] += w1 * g1_4 * vd1

    if not fixed_speed_flag:
        g1_5 = kz * zi
        mk[1, 5] += w1 * g1_1 * g1_5
        mk[5, 1] += w1 * g1_5 * g1_1
        mk[3, 5] += w1 * g1_3 * g1_5
        mk[5, 3] += w1 * g1_5 * g1_3
        mk[4, 5] += w1 * g1_4 * g1_5
        mk[5, 4] += w1 * g1_5 * g1_4
        mk[5, 5] += w1 * g1_5 * g1_5
        va[5] += w1 * g1_5 * vd1

def _build_mk_va_base(
    plane_idx_arr,
    y_row,
    td_row,
    z_pos_arr,
    w_arr,
    ss,
    mk_base,
    va_base,
):
    """Build per-event constant TimTrack terms (independent of current vs)."""
    mk_base.fill(0.0)
    va_base.fill(0.0)

    w0 = w_arr[0]
    w2 = w_arr[2]
    ss2 = ss * ss
    w2_ss = w2 * ss
    w2_ss2 = w2 * ss2

    for plane_idx in plane_idx_arr:
        zi = z_pos_arr[plane_idx]
        ydat = y_row[plane_idx]
        tddat = td_row[plane_idx]
        sszi = ss * zi
        zi2 = zi * zi

        # g0 contribution (weight w0)
        mk_base[2, 2] += w0
        mk_base[2, 3] += w0 * zi
        mk_base[3, 2] += w0 * zi
        mk_base[3, 3] += w0 * zi2
        va_base[2] += w0 * ydat
        va_base[3] += w0 * zi * ydat

        # g2 contribution (weight w2)
        mk_base[0, 0] += w2_ss2
        mk_base[0, 1] += w2_ss2 * zi
        mk_base[1, 0] += w2_ss2 * zi
        mk_base[1, 1] += w2 * sszi * sszi
        va_base[0] += w2_ss * tddat
        va_base[1] += w2 * sszi * tddat

def _accumulate_mk_va_dynamic_g1(
    vs,
    plane_idx_arr,
    ts_row,
    z_pos_arr,
    w1,
    half_lenx_ss,
    sc_val,
    fixed_speed_flag,
    mk,
    va,
):
    """Add per-iteration dynamic g1 terms (depend on current vs)."""
    XP = vs[1]
    YP = vs[3]
    S0 = sc_val if fixed_speed_flag else vs[5]
    kz = math.sqrt(1.0 + XP * XP + YP * YP)
    kzi = 1.0 / kz

    for plane_idx in plane_idx_arr:
        zi = z_pos_arr[plane_idx]
        vd1 = ts_row[plane_idx] - half_lenx_ss

        g1_1 = kzi * S0 * XP * zi
        g1_3 = kzi * S0 * YP * zi

        mk[1, 1] += w1 * g1_1 * g1_1
        mk[1, 3] += w1 * g1_1 * g1_3
        mk[3, 1] += w1 * g1_3 * g1_1
        mk[1, 4] += w1 * g1_1
        mk[4, 1] += w1 * g1_1
        mk[3, 3] += w1 * g1_3 * g1_3
        mk[3, 4] += w1 * g1_3
        mk[4, 3] += w1 * g1_3
        mk[4, 4] += w1
        va[1] += w1 * g1_1 * vd1
        va[3] += w1 * g1_3 * vd1
        va[4] += w1 * vd1

        if not fixed_speed_flag:
            g1_5 = kz * zi
            mk[1, 5] += w1 * g1_1 * g1_5
            mk[5, 1] += w1 * g1_5 * g1_1
            mk[3, 5] += w1 * g1_3 * g1_5
            mk[5, 3] += w1 * g1_5 * g1_3
            mk[4, 5] += w1 * g1_5
            mk[5, 4] += w1 * g1_5
            mk[5, 5] += w1 * g1_5 * g1_5
            va[5] += w1 * g1_5 * vd1

def _build_loo_single_step_system(
    vs,
    plane_idx_arr,
    plane_idx_ref,
    y_row,
    ts_row,
    td_row,
    z_pos_arr,
    w_arr,
    ss,
    half_lenx_ss,
    sc_val,
    fixed_speed_flag,
    mk,
    va,
):
    """Build LOO normal equations for one hidden plane in single-step mode.

    This is equivalent to repeated _accumulate_mk_va calls with shifted z, but
    avoids per-plane helper call overhead in the hottest residual-LOO path.
    """
    mk.fill(0.0)
    va.fill(0.0)

    XP = vs[1]
    YP = vs[3]
    S0 = sc_val if fixed_speed_flag else vs[5]
    kz = math.sqrt(1.0 + XP * XP + YP * YP)
    kzi = 1.0 / kz

    a1 = kzi * S0 * XP
    a3 = kzi * S0 * YP

    w0 = w_arr[0]
    w1 = w_arr[1]
    w2 = w_arr[2]
    w2_ss = w2 * ss
    w2_ss2 = w2_ss * ss

    z_ref = z_pos_arr[plane_idx_ref]

    for plane_idx in plane_idx_arr:
        if plane_idx == plane_idx_ref:
            continue

        zi = z_pos_arr[plane_idx] - z_ref
        zi2 = zi * zi
        sszi = ss * zi

        ydat = y_row[plane_idx]
        tsdat = ts_row[plane_idx]
        tddat = td_row[plane_idx]
        vd1 = tsdat - half_lenx_ss

        # g0 contribution (weight w0)
        mk[2, 2] += w0
        mk[2, 3] += w0 * zi
        mk[3, 2] += w0 * zi
        mk[3, 3] += w0 * zi2
        va[2] += w0 * ydat
        va[3] += w0 * zi * ydat

        # g2 contribution (weight w2)
        mk[0, 0] += w2_ss2
        mk[0, 1] += w2_ss2 * zi
        mk[1, 0] += w2_ss2 * zi
        mk[1, 1] += w2 * sszi * sszi
        va[0] += w2_ss * tddat
        va[1] += w2 * sszi * tddat

        # g1 contribution (weight w1)
        g1_1 = a1 * zi
        g1_3 = a3 * zi
        mk[1, 1] += w1 * g1_1 * g1_1
        mk[1, 3] += w1 * g1_1 * g1_3
        mk[3, 1] += w1 * g1_3 * g1_1
        mk[1, 4] += w1 * g1_1
        mk[4, 1] += w1 * g1_1
        mk[3, 3] += w1 * g1_3 * g1_3
        mk[3, 4] += w1 * g1_3
        mk[4, 3] += w1 * g1_3
        mk[4, 4] += w1
        va[1] += w1 * g1_1 * vd1
        va[3] += w1 * g1_3 * vd1
        va[4] += w1 * vd1

        if not fixed_speed_flag:
            g1_5 = kz * zi
            mk[1, 5] += w1 * g1_1 * g1_5
            mk[5, 1] += w1 * g1_5 * g1_1
            mk[3, 5] += w1 * g1_3 * g1_5
            mk[5, 3] += w1 * g1_5 * g1_3
            mk[4, 5] += w1 * g1_5
            mk[5, 4] += w1 * g1_5
            mk[5, 5] += w1 * g1_5 * g1_5
            va[5] += w1 * g1_5 * vd1


# Calculate angles -------------------------------------------------------------------
def calculate_angles(xproj, yproj):
    phi = np.arctan2(yproj, xproj)
    theta = np.arccos(1 / np.sqrt(xproj**2 + yproj**2 + 1))
    return theta, phi


def apply_task4_final_filter(
    df_input: pd.DataFrame,
    *,
    apply_changes: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int | float]]:
    input_rows = int(len(df_input))
    if input_rows == 0:
        return df_input.copy(), pd.DataFrame(), {
            "input_rows": 0,
            "rows_affected": 0,
            "values_zeroed": 0,
            "rows_failed_tt_task4_fit_min": 0,
            "rows_failed_nonzero_required": 0,
            "pre_event_rows_affected": 0,
            "pre_event_values_zeroed": 0,
            "post_event_rows_affected": 0,
            "post_event_values_zeroed": 0,
        }

    working = df_input.copy() if apply_changes else df_input
    summary: dict[str, int | float] = {
        "input_rows": input_rows,
        "rows_affected": 0,
        "values_zeroed": 0,
        "rows_failed_tt_task4_fit_min": 0,
        "rows_failed_nonzero_required": 0,
        "pre_event_rows_affected": 0,
        "pre_event_values_zeroed": 0,
        "post_event_rows_affected": 0,
        "post_event_values_zeroed": 0,
    }
    final_mask = np.ones(input_rows, dtype=bool)
    fail_reason_parts = np.empty(input_rows, dtype=object)
    fail_reason_parts.fill("")

    final_filter_remove_small = TASK4_FINAL_FILTER_REMOVE_SMALL
    final_filter_remove_small_eps = TASK4_FINAL_FILTER_REMOVE_SMALL_EPS
    if final_filter_remove_small:
        small_mask = working.map(
            lambda x: isinstance(x, (int, float)) and x != 0 and abs(x) < final_filter_remove_small_eps
        )
        nonzero_numeric_mask = working.map(lambda x: isinstance(x, (int, float)) and x != 0)
        total_nonzero = int(nonzero_numeric_mask.sum().sum())
        total_small = int(small_mask.sum().sum())
        rows_with_small = int(small_mask.any(axis=1).sum())
        summary["values_zeroed"] = total_small
        summary["rows_with_small_values"] = rows_with_small
        record_filter_metric(
            "small_values_zeroed_event_pct",
            rows_with_small,
            input_rows if input_rows else 0,
        )
        record_filter_metric(
            "small_values_zeroed_value_pct",
            total_small,
            total_nonzero if total_nonzero else 0,
        )
    else:
        record_filter_metric("small_values_zeroed_event_pct", 0, input_rows if input_rows else 0)
        record_filter_metric("small_values_zeroed_value_pct", 0, input_rows if input_rows else 0)

    task4_pre_event_block_summary = normalize_task4_event_component_blocks(
        working,
        apply_changes=False,
    )
    summary["pre_event_rows_affected"] = int(task4_pre_event_block_summary["rows_affected"])
    summary["pre_event_values_zeroed"] = int(task4_pre_event_block_summary["values_zeroed"])
    summary["event_block_column_count"] = int(task4_pre_event_block_summary["column_count"])
    summary["values_zeroed"] = int(summary["values_zeroed"]) + int(
        task4_pre_event_block_summary["values_zeroed"]
    )

    tt_task4_fit_min = TASK4_FINAL_FIT_TT_MIN
    tt_task4_fit_series = get_task4_tt_series(working, preferred=TASK4_PRIMARY_TT_COLUMN)
    tt_task4_fit_pass = tt_task4_fit_series >= tt_task4_fit_min
    tt_task4_fit_fail = ~tt_task4_fit_pass.to_numpy(dtype=bool, copy=False)
    summary["rows_failed_tt_task4_fit_min"] = int(tt_task4_fit_fail.sum())
    final_mask &= ~tt_task4_fit_fail
    fail_reason_parts[tt_task4_fit_fail] = np.where(
        fail_reason_parts[tt_task4_fit_fail] == "",
        f"tt_task4_fit<{tt_task4_fit_min}",
        fail_reason_parts[tt_task4_fit_fail] + f";tt_task4_fit<{tt_task4_fit_min}",
    )

    required_nonzero_cols = [col for col in TASK4_EVENT_ATOMIC_COLUMNS if col in working.columns]
    if required_nonzero_cols:
        nonzero_mask = np.ones(input_rows, dtype=bool)
        zero_count_per_row = np.zeros(input_rows, dtype=int)
        primary_zero_col = np.full(input_rows, "", dtype=object)
        for col in required_nonzero_cols:
            col_values = pd.to_numeric(working[col], errors="coerce").to_numpy(dtype=float, copy=False)
            finite_mask = np.isfinite(col_values)
            nonzero_col_mask = finite_mask & (col_values != 0.0)
            nonzero_mask &= nonzero_col_mask
            zero_or_invalid = ~nonzero_col_mask
            zero_count_per_row += zero_or_invalid.astype(int)
            primary_assign_mask = (primary_zero_col == "") & zero_or_invalid
            primary_zero_col[primary_assign_mask] = col
        nonzero_fail = ~nonzero_mask
        summary["rows_failed_nonzero_required"] = int(nonzero_fail.sum())
        summary["rows_failed_nonzero_single"] = int(np.count_nonzero(nonzero_fail & (zero_count_per_row == 1)))
        summary["rows_failed_nonzero_multi"] = int(np.count_nonzero(nonzero_fail & (zero_count_per_row >= 2)))
        final_mask &= ~nonzero_fail
        fail_reason_parts[nonzero_fail] = np.where(
            fail_reason_parts[nonzero_fail] == "",
            "required_nonzero_violation",
            fail_reason_parts[nonzero_fail] + ";required_nonzero_violation",
        )
        for col in required_nonzero_cols:
            summary[f"rows_failed_primary_zero_{col}"] = int(
                np.count_nonzero(nonzero_fail & (primary_zero_col == col))
            )
    else:
        zero_count_per_row = np.zeros(input_rows, dtype=int)
        primary_zero_col = np.full(input_rows, "", dtype=object)

    def _numeric_column_or_nan(column_name: str) -> np.ndarray:
        if column_name not in working.columns:
            return np.full(input_rows, np.nan, dtype=float)
        return pd.to_numeric(working[column_name], errors="coerce").to_numpy(dtype=float, copy=False)

    def _apply_numeric_range_filter(
        values: np.ndarray,
        *,
        left_limit: float | None,
        right_limit: float | None,
        summary_key: str,
        reason_key: str,
    ) -> None:
        nonlocal final_mask
        if left_limit is None and right_limit is None:
            return
        pass_mask = np.isfinite(values)
        if left_limit is not None:
            pass_mask &= values >= left_limit
        if right_limit is not None:
            pass_mask &= values <= right_limit
        fail_mask = ~pass_mask
        summary[f"rows_failed_{summary_key}"] = int(fail_mask.sum())
        final_mask &= ~fail_mask
        fail_reason_parts[fail_mask] = np.where(
            fail_reason_parts[fail_mask] == "",
            f"{reason_key}_out_of_range",
            fail_reason_parts[fail_mask] + f";{reason_key}_out_of_range",
        )

    det_pos_filter_abs = abs(_task4_config_float(config, "det_pos_filter", default=200.0))
    det_phi_filter_abs = abs(
        _task4_config_float(
            config,
            "det_phi_filter_abs",
            "det_phi_right_filter",
            default=3.141592,
        )
    )
    event_variable_specs = (
        (
            "event_charge",
            "event_combination_detector_event_charge_left",
            "event_combination_detector_event_charge_right",
            _task4_config_float(config, "charge_plot_limit_left", default=0.0),
            _task4_config_float(
                config,
                "charge_plot_event_limit_right",
                "charge_plot_limit_right",
                default=400.0,
            ),
        ),
        (
            "x",
            "event_combination_detector_x_left",
            "event_combination_detector_x_right",
            -det_pos_filter_abs,
            det_pos_filter_abs,
        ),
        (
            "y",
            "event_combination_detector_y_left",
            "event_combination_detector_y_right",
            -det_pos_filter_abs,
            det_pos_filter_abs,
        ),
        (
            "s",
            "event_combination_detector_s_left",
            "event_combination_detector_s_right",
            _task4_config_float(config, "det_slowness_filter_left", default=-0.02),
            _task4_config_float(config, "det_slowness_filter_right", default=0.03),
        ),
        (
            "theta",
            "event_combination_detector_theta_left",
            "event_combination_detector_theta_right",
            _task4_config_float(config, "det_theta_left_filter", default=0.0),
            _task4_config_float(config, "det_theta_right_filter", default=1.5708),
        ),
        (
            "phi",
            "event_combination_detector_phi_left",
            "event_combination_detector_phi_right",
            -det_phi_filter_abs,
            det_phi_filter_abs,
        ),
    )
    for (
        variable_name,
        left_key,
        right_key,
        default_left,
        default_right,
    ) in event_variable_specs:
        has_explicit_bounds = any(
            _task4_parse_optional_float(config.get(key)) is not None
            for key in (left_key, right_key)
        )
        if not has_explicit_bounds:
            continue
        left_limit = _task4_get_optional_config_float(
            config,
            left_key,
        )
        right_limit = _task4_get_optional_config_float(
            config,
            right_key,
        )
        if left_limit is None:
            left_limit = float(default_left)
        if right_limit is None:
            right_limit = float(default_right)
        _apply_numeric_range_filter(
            _numeric_column_or_nan(variable_name),
            left_limit=left_limit,
            right_limit=right_limit,
            summary_key=f"{variable_name}_range",
            reason_key=variable_name,
        )

    rows_affected = int((~final_mask).sum())
    summary["rows_affected"] = rows_affected
    summary["flagged_rows"] = rows_affected
    summary["failed_pair_any"] = rows_affected
    if not apply_changes:
        return df_input, pd.DataFrame(), summary

    rejected_df = working.loc[~final_mask].copy()
    working.loc[:, "passes_task_4"] = np.where(final_mask, np.uint8(1), np.uint8(0))
    working.loc[:, "filter_task4_final_pass"] = final_mask
    summary["post_event_rows_affected"] = 0
    summary["post_event_values_zeroed"] = 0
    if not rejected_df.empty:
        rejected_df["reject_stage"] = "final_filtering"
        rejected_df["reject_reason"] = fail_reason_parts[~final_mask]
        rejected_df["zero_count"] = zero_count_per_row[~final_mask]
        rejected_df["primary_zero_col"] = primary_zero_col[~final_mask]
    return working, rejected_df, summary


# -----------------------------------------------------------------------------
# -------------- Correlate trigger types in different stages ------------------
# -----------------------------------------------------------------------------



def _resolve_task4_efficiency_metadata_cfg(config_dict):
    raw = config_dict.get("efficiency_metadata", {})
    if not isinstance(raw, dict):
        raw = {}
    return {
        "x_bin_count": max(1, _safe_cfg_int(raw.get("x_bin_count", 15), 15)),
        "y_bin_count": max(1, _safe_cfg_int(raw.get("y_bin_count", 20), 20)),
        "theta_bin_count": max(1, _safe_cfg_int(raw.get("theta_bin_count", 20), 20)),
        "phi_bin_count": max(1, _safe_cfg_int(raw.get("phi_bin_count", 24), 24)),
        "x_min_mm": raw.get("x_min_mm", None),
        "x_max_mm": raw.get("x_max_mm", None),
        "y_min_mm": raw.get("y_min_mm", None),
        "y_max_mm": raw.get("y_max_mm", None),
        "theta_min_deg": raw.get("theta_min_deg", None),
        "theta_max_deg": raw.get("theta_max_deg", None),
        "phi_min_deg": raw.get("phi_min_deg", None),
        "phi_max_deg": raw.get("phi_max_deg", None),
        "min_pool_events": max(1, _safe_cfg_int(raw.get("min_pool_events", 20), 20)),
        "min_accepted_events": max(1, _safe_cfg_int(raw.get("min_accepted_events", 10), 10)),
        "summary_fiducial_x_abs_max_mm": _safe_cfg_optional_float(
            raw.get("summary_fiducial_x_abs_max_mm", None)
        ),
        "summary_fiducial_y_abs_max_mm": _safe_cfg_optional_float(
            raw.get("summary_fiducial_y_abs_max_mm", None)
        ),
        "summary_fiducial_theta_max_deg": _safe_cfg_optional_float(
            raw.get("summary_fiducial_theta_max_deg", None)
        ),
        "summary_fiducial_phi_abs_max_deg": _safe_cfg_optional_float(
            raw.get("summary_fiducial_phi_abs_max_deg", None)
        ),
    }

def _resolve_projection_ellipse_diagnostic_cfg(config_dict, default_half_range):
    raw = config_dict.get("projection_ellipse_diagnostic", {})
    if not isinstance(raw, dict):
        raw = {}

    default_half_range = float(default_half_range)
    x_min = _safe_cfg_optional_float(raw.get("x_min", None))
    x_max = _safe_cfg_optional_float(raw.get("x_max", None))
    y_min = _safe_cfg_optional_float(raw.get("y_min", None))
    y_max = _safe_cfg_optional_float(raw.get("y_max", None))
    if x_min is None:
        x_min = -default_half_range
    if x_max is None:
        x_max = default_half_range
    if y_min is None:
        y_min = -default_half_range
    if y_max is None:
        y_max = default_half_range
    if x_max <= x_min:
        x_min, x_max = -default_half_range, default_half_range
    if y_max <= y_min:
        y_min, y_max = -default_half_range, default_half_range

    smoothing_sigma_bins = raw.get("smoothing_sigma_bins", 1.0)
    try:
        smoothing_sigma_bins = float(smoothing_sigma_bins)
    except (TypeError, ValueError):
        smoothing_sigma_bins = 1.0
    if not np.isfinite(smoothing_sigma_bins) or smoothing_sigma_bins < 0.0:
        smoothing_sigma_bins = 1.0

    axis_quantile_min = _safe_cfg_optional_float(raw.get("axis_quantile_min", 0.01))
    axis_quantile_max = _safe_cfg_optional_float(raw.get("axis_quantile_max", 0.99))
    if axis_quantile_min is None:
        axis_quantile_min = 0.01
    if axis_quantile_max is None:
        axis_quantile_max = 0.99

    return {
        "bin_count": max(24, _safe_cfg_int(raw.get("bin_count", 140), 140)),
        "min_points": max(50, _safe_cfg_int(raw.get("min_points", 300), 300)),
        "smoothing_sigma_bins": smoothing_sigma_bins,
        "x_min": float(x_min),
        "x_max": float(x_max),
        "y_min": float(y_min),
        "y_max": float(y_max),
        "axis_quantile_min": min(max(float(axis_quantile_min), 0.0), 0.49),
        "axis_quantile_max": max(min(float(axis_quantile_max), 1.0), 0.51),
        "cmap": str(raw.get("cmap", "turbo")).strip() or "turbo",
        "contour_fractions": _coerce_probability_tuple(
            raw.get("contour_fractions", None),
            default=(0.25, 0.5, 0.75),
        ),
        "focus_definitive_tt": _coerce_tt_label_tuple(
            raw.get("focus_definitive_tt", None),
            default=OFFENDER_FOCUS_TTS_CFG,
        ),
    }

def _efficiency_center_field(axis_name):
    return "center_deg" if axis_name == "theta" else "center_mm"


def _make_efficiency_curve(values, fired, bins):
    vals = np.asarray(values, dtype=float)
    fire = np.asarray(fired, dtype=float)
    centers = 0.5 * (bins[:-1] + bins[1:])
    num, _ = np.histogram(vals[fire > 0.5], bins=bins)
    den, _ = np.histogram(vals, bins=bins)
    with np.errstate(invalid="ignore", divide="ignore"):
        eff = np.where(den > 0, num / den, np.nan)
        unc = np.where(
            den > 0,
            np.sqrt(np.maximum(eff * (1.0 - eff) / np.maximum(den, 1), 0.0)),
            np.nan,
        )
    return {
        "centers": centers.astype(float),
        "eff": np.asarray(eff, dtype=float),
        "unc": np.asarray(unc, dtype=float),
        "den": np.asarray(den, dtype=float),
    }

def _histogram_bin_indices(values, bins):
    vals = np.asarray(values, dtype=float)
    out = np.full(vals.shape, -1, dtype=np.int32)
    if vals.size == 0 or len(bins) < 2:
        return out

    valid = np.isfinite(vals) & (vals >= float(bins[0])) & (vals <= float(bins[-1]))
    if not np.any(valid):
        return out

    out[valid] = np.digitize(vals[valid], bins[1:-1], right=False).astype(np.int32)
    return out

def _compute_efficiency_summary_bin_mask(centers, eff_vals, den_vals, axis_name, cfg_eff):
    valid = np.isfinite(centers) & np.isfinite(eff_vals) & np.isfinite(den_vals) & (den_vals > 0)
    if axis_name == "x":
        limit = cfg_eff.get("summary_fiducial_x_abs_max_mm", None)
        if limit is not None:
            valid &= np.abs(centers) <= float(limit)
    elif axis_name == "y":
        limit = cfg_eff.get("summary_fiducial_y_abs_max_mm", None)
        if limit is not None:
            valid &= np.abs(centers) <= float(limit)
    elif axis_name == "theta":
        limit = cfg_eff.get("summary_fiducial_theta_max_deg", None)
        if limit is not None:
            valid &= centers <= float(limit)
    elif axis_name == "phi":
        limit = cfg_eff.get("summary_fiducial_phi_abs_max_deg", None)
        if limit is not None:
            valid &= np.abs(centers) <= float(limit)
    return valid

def _extract_efficiency_summary_arrays(axis_payload, axis_name, cfg_eff):
    centers = np.asarray(axis_payload.get("centers", []), dtype=float)
    eff_vals = np.asarray(axis_payload.get("eff", []), dtype=float)
    unc_vals = np.asarray(axis_payload.get("unc", []), dtype=float)
    den_vals = np.asarray(axis_payload.get("den", []), dtype=float)
    valid = _compute_efficiency_summary_bin_mask(
        centers,
        eff_vals,
        den_vals,
        axis_name,
        cfg_eff,
    )
    return centers, eff_vals, unc_vals, den_vals, valid

def _compute_robust_x_center_eff(axis_payload, cfg_eff):
    summary = _compute_efficiency_scalar_summary(axis_payload, "x", cfg_eff)
    eff = summary.get("eff", np.nan)
    return float(eff) if np.isfinite(eff) else np.nan

def _intersect_required_indices(*indices):
    if not indices or any(index is None for index in indices):
        return None
    intersection = pd.Index(indices[0])
    for index in indices[1:]:
        intersection = intersection.intersection(pd.Index(index), sort=False)
    return intersection

def _required_track_efficiency_hit_columns():
    return tuple(
        f"p{plane}_{suffix}"
        for plane in range(1, 5)
        for suffix in ("tdif", "ypos")
    )

def _extract_track_efficiency_hit_arrays(df_plot, tdiff_to_x):
    x_hits = np.column_stack(
        [
            pd.to_numeric(df_plot[f"p{plane}_tdif"], errors="coerce").to_numpy(dtype=float)
            * float(tdiff_to_x)
            for plane in range(1, 5)
        ]
    )
    y_hits = np.column_stack(
        [
            pd.to_numeric(df_plot[f"p{plane}_ypos"], errors="coerce").to_numpy(dtype=float)
            for plane in range(1, 5)
        ]
    )
    return x_hits, y_hits

def _fit_three_plane_telescope_projection(x_hits, y_hits, z_arr, test_plane_zero_idx):
    other_idx = [idx for idx in range(4) if idx != int(test_plane_zero_idx)]
    z_known = np.asarray(z_arr[other_idx], dtype=float)
    z_test = float(z_arr[int(test_plane_zero_idx)])
    z_mean = float(np.mean(z_known))
    z_delta = z_known - z_mean
    z_denom = float(np.sum(z_delta * z_delta))

    n_rows = int(x_hits.shape[0])
    out = {
        "x_pred": np.full(n_rows, np.nan, dtype=float),
        "y_pred": np.full(n_rows, np.nan, dtype=float),
        "theta_pred_deg": np.full(n_rows, np.nan, dtype=float),
        "phi_pred_deg": np.full(n_rows, np.nan, dtype=float),
        "valid": np.zeros(n_rows, dtype=bool),
    }
    if n_rows == 0 or not np.isfinite(z_denom) or z_denom <= 0.0:
        return out

    x_known = np.asarray(x_hits[:, other_idx], dtype=float)
    y_known = np.asarray(y_hits[:, other_idx], dtype=float)
    valid = np.isfinite(x_known).all(axis=1) & np.isfinite(y_known).all(axis=1)
    if not np.any(valid):
        return out

    x_fit = x_known[valid]
    y_fit = y_known[valid]
    x_mean = np.mean(x_fit, axis=1)
    y_mean = np.mean(y_fit, axis=1)
    slope_x = np.sum((x_fit - x_mean[:, None]) * z_delta[None, :], axis=1) / z_denom
    slope_y = np.sum((y_fit - y_mean[:, None]) * z_delta[None, :], axis=1) / z_denom
    intercept_x = x_mean - slope_x * z_mean
    intercept_y = y_mean - slope_y * z_mean

    out["x_pred"][valid] = intercept_x + slope_x * z_test
    out["y_pred"][valid] = intercept_y + slope_y * z_test
    out["theta_pred_deg"][valid] = np.degrees(np.arctan(np.hypot(slope_x, slope_y)))
    out["phi_pred_deg"][valid] = np.degrees(np.arctan2(slope_y, slope_x))
    out["valid"] = valid
    return out

def _select_robust_plateau_event_indices(
    axis_payload,
    *,
    cfg_eff,
    axis_values,
    bins,
    accepted_indices,
    axis_name="x",
    tolerance,
    center_eff=np.nan,
    fired=None,
    fired_only=False,
):
    centers = np.asarray(axis_payload.get("centers", []), dtype=float)
    eff_vals = np.asarray(axis_payload.get("eff", []), dtype=float)
    den_vals = np.asarray(axis_payload.get("den", []), dtype=float)
    valid_bins = _compute_efficiency_summary_bin_mask(
        centers,
        eff_vals,
        den_vals,
        axis_name,
        cfg_eff,
    )
    if not np.any(valid_bins):
        return None

    if eff_vals.shape[0] != len(bins) - 1:
        return None

    if not np.isfinite(center_eff):
        center_eff = _compute_efficiency_scalar_summary(axis_payload, axis_name, cfg_eff).get("eff", np.nan)
    if not np.isfinite(center_eff):
        return None

    plateau_bins = valid_bins & (np.abs(eff_vals - center_eff) <= float(tolerance))

    accepted_index = pd.Index(accepted_indices)
    bin_indices = _histogram_bin_indices(axis_values, bins)
    if len(accepted_index) != len(bin_indices):
        return None

    selected = bin_indices >= 0
    if fired_only:
        if fired is None:
            return None
        fired_arr = np.asarray(fired, dtype=float)
        if len(fired_arr) != len(bin_indices):
            return None
        selected &= fired_arr > 0.5
    if np.any(selected):
        in_plateau = np.zeros(selected.shape, dtype=bool)
        in_plateau[selected] = plateau_bins[bin_indices[selected]]
        selected &= in_plateau

    return accepted_index[selected]

def _select_efficiency_summary_event_indices(
    axis_payload,
    *,
    cfg_eff,
    axis_values,
    bins,
    accepted_indices,
    axis_name="x",
    fired=None,
    fired_only=False,
):
    centers = np.asarray(axis_payload.get("centers", []), dtype=float)
    eff_vals = np.asarray(axis_payload.get("eff", []), dtype=float)
    den_vals = np.asarray(axis_payload.get("den", []), dtype=float)
    valid_bins = _compute_efficiency_summary_bin_mask(
        centers,
        eff_vals,
        den_vals,
        axis_name,
        cfg_eff,
    )
    if not np.any(valid_bins):
        return None

    if eff_vals.shape[0] != len(bins) - 1:
        return None

    accepted_index = pd.Index(accepted_indices)
    bin_indices = _histogram_bin_indices(axis_values, bins)
    if len(accepted_index) != len(bin_indices):
        return None

    selected = bin_indices >= 0
    if fired_only:
        if fired is None:
            return None
        fired_arr = np.asarray(fired, dtype=float)
        if len(fired_arr) != len(bin_indices):
            return None
        selected &= fired_arr > 0.5
    if np.any(selected):
        in_summary = np.zeros(selected.shape, dtype=bool)
        in_summary[selected] = valid_bins[bin_indices[selected]]
        selected &= in_summary

    return accepted_index[selected]

def _compute_efficiency_scalar_summary(axis_payload, axis_name, cfg_eff):
    centers, eff_vals, unc_vals, den_vals, valid = _extract_efficiency_summary_arrays(
        axis_payload,
        axis_name,
        cfg_eff,
    )

    out = {
        "eff": np.nan,
        "unc": np.nan,
        "n_denom": 0,
        "n_bins_used": int(np.sum(valid)),
        "selected_center": np.nan,
    }
    if not np.any(valid):
        return out

    if axis_name == "theta":
        valid_idx = np.flatnonzero(valid)
        # The theta scalar summary is defined by the bin closest to normal incidence,
        # not by the maximum efficiency inside the fiducial theta band.
        best_local = valid_idx[np.nanargmin(np.abs(centers[valid_idx]))]
        out["eff"] = float(eff_vals[best_local])
        out["unc"] = float(unc_vals[best_local]) if best_local < len(unc_vals) else np.nan
        out["n_denom"] = int(den_vals[best_local]) if best_local < len(den_vals) else 0
        out["selected_center"] = float(centers[best_local])
        return out

    den_region = den_vals[valid]
    eff_region = eff_vals[valid]
    denom = float(np.sum(den_region))
    if not np.isfinite(denom) or denom <= 0.0:
        return out
    num = float(np.sum(den_region * eff_region))
    eff_mean = num / denom
    out["eff"] = float(eff_mean)
    out["unc"] = float(np.sqrt(max(eff_mean * (1.0 - eff_mean) / denom, 0.0)))
    out["n_denom"] = int(round(denom))
    return out

def _resolve_efficiency_edges(
    *,
    cfg_eff,
    strip_half,
    width_half,
    theta_left_filter,
    theta_right_filter,
    phi_left_filter,
    phi_right_filter,
):
    x_min = _safe_cfg_float(cfg_eff.get("x_min_mm", None), -float(strip_half))
    x_max = _safe_cfg_float(cfg_eff.get("x_max_mm", None), float(strip_half))
    y_min = _safe_cfg_float(cfg_eff.get("y_min_mm", None), -float(width_half))
    y_max = _safe_cfg_float(cfg_eff.get("y_max_mm", None), float(width_half))
    theta_min_deg = _safe_cfg_float(
        cfg_eff.get("theta_min_deg", None),
        float(np.degrees(theta_left_filter)),
    )
    theta_max_deg = _safe_cfg_float(
        cfg_eff.get("theta_max_deg", None),
        float(np.degrees(theta_right_filter)),
    )
    phi_min_deg = _safe_cfg_float(
        cfg_eff.get("phi_min_deg", None),
        float(np.degrees(phi_left_filter)),
    )
    phi_max_deg = _safe_cfg_float(
        cfg_eff.get("phi_max_deg", None),
        float(np.degrees(phi_right_filter)),
    )

    x_min = max(-float(strip_half), min(x_min, float(strip_half)))
    x_max = max(-float(strip_half), min(x_max, float(strip_half)))
    y_min = max(-float(width_half), min(y_min, float(width_half)))
    y_max = max(-float(width_half), min(y_max, float(width_half)))
    theta_min_deg = max(0.0, theta_min_deg)
    theta_max_deg = max(theta_min_deg + 1e-6, min(theta_max_deg, 90.0))
    phi_min_deg = max(-180.0, min(phi_min_deg, 180.0))
    phi_max_deg = max(-180.0, min(phi_max_deg, 180.0))

    if x_max <= x_min:
        x_min, x_max = -float(strip_half), float(strip_half)
    if y_max <= y_min:
        y_min, y_max = -float(width_half), float(width_half)
    if phi_max_deg <= phi_min_deg:
        phi_min_deg = float(np.degrees(phi_left_filter))
        phi_max_deg = float(np.degrees(phi_right_filter))
        if phi_max_deg <= phi_min_deg:
            phi_min_deg, phi_max_deg = -180.0, 180.0

    return {
        "x": np.linspace(x_min, x_max, int(cfg_eff["x_bin_count"]) + 1),
        "y": np.linspace(y_min, y_max, int(cfg_eff["y_bin_count"]) + 1),
        "theta": np.linspace(theta_min_deg, theta_max_deg, int(cfg_eff["theta_bin_count"]) + 1),
        "phi": np.linspace(phi_min_deg, phi_max_deg, int(cfg_eff["phi_bin_count"]) + 1),
    }

def _compute_track_based_efficiency_payload(
    df_plot,
    *,
    cfg_eff,
    cfg_fiducial,
    z_positions,
    tdiff_to_x,
    strip_half,
    width_half,
    theta_left_filter,
    theta_right_filter,
    phi_left_filter,
    phi_right_filter,
    y_pos_p13,
    y_pos_p24,
):
    edges = _resolve_efficiency_edges(
        cfg_eff=cfg_eff,
        strip_half=strip_half,
        width_half=width_half,
        theta_left_filter=theta_left_filter,
        theta_right_filter=theta_right_filter,
        phi_left_filter=phi_left_filter,
        phi_right_filter=phi_right_filter,
    )
    plane_pool_tt = {
        1: [234, 1234],
        2: [134, 1234],
        3: [124, 1234],
        4: [123, 1234],
    }
    payload = {
        "available": False,
        "reason": "",
        "config": dict(cfg_eff),
        "edges": edges,
        "plane_results": {},
        "trigger_source": "",
        "pool_source": "",
    }

    trigger_source = "tt_task4_fit"
    payload["trigger_source"] = trigger_source
    pool_source = trigger_source
    payload["pool_source"] = pool_source

    required = tuple(_required_track_efficiency_hit_columns()) + (trigger_source, pool_source)
    missing = [col for col in required if col not in df_plot.columns]
    if missing:
        if trigger_source in missing:
            payload["reason"] = "missing_tt_task4_fit"
        else:
            payload["reason"] = f"missing_required_columns:{','.join(missing)}"
        return payload

    z_arr = np.asarray(z_positions, dtype=float)
    x_hits_all, y_hits_all = _extract_track_efficiency_hit_arrays(df_plot, tdiff_to_x)
    dtt_all = (
        pd.to_numeric(df_plot[trigger_source], errors="coerce")
        .fillna(0)
        .to_numpy(dtype=np.int32)
    )
    pool_tt_all = (
        pd.to_numeric(df_plot[pool_source], errors="coerce")
        .fillna(0)
        .to_numpy(dtype=np.int32)
    )
    charge_series, _ = _resolve_task4_total_event_charge_series(df_plot)
    if charge_series is not None:
        charge_all = charge_series.to_numpy(dtype=float, copy=False)
    else:
        charge_all = np.full(len(df_plot), np.nan, dtype=float)

    any_plane_available = False
    for plane in range(1, 5):
        x_scalar_summary = _compute_efficiency_scalar_summary({}, "x", cfg_eff)
        y_reference = y_pos_p13 if (plane - 1) % 2 == 0 else y_pos_p24
        plane_result = {
            "plane": int(plane),
            "overall_eff": np.nan,
            "n_denom": 0,
            "y_reference": np.asarray(y_reference, dtype=float),
            "eff_2d": np.full(
                (len(edges["x"]) - 1, len(edges["y"]) - 1),
                np.nan,
                dtype=float,
            ),
            "x": _make_efficiency_curve(np.asarray([], dtype=float), np.asarray([], dtype=float), edges["x"]),
            "y": _make_efficiency_curve(np.asarray([], dtype=float), np.asarray([], dtype=float), edges["y"]),
            "theta": _make_efficiency_curve(
                np.asarray([], dtype=float),
                np.asarray([], dtype=float),
                edges["theta"],
            ),
            "phi": _make_efficiency_curve(
                np.asarray([], dtype=float),
                np.asarray([], dtype=float),
                edges["phi"],
            ),
            "eff_theta_phi": np.full(
                (len(edges["theta"]) - 1, len(edges["phi"]) - 1),
                np.nan,
                dtype=float,
            ),
            "scalar_summary": {
                "x": {
                    "eff": np.nan,
                    "unc": np.nan,
                    "n_denom": 0,
                    "n_bins_used": 0,
                    "selected_center": np.nan,
                },
                "y": {
                    "eff": np.nan,
                    "unc": np.nan,
                    "n_denom": 0,
                    "n_bins_used": 0,
                    "selected_center": np.nan,
                },
                "theta": {
                    "eff": np.nan,
                    "unc": np.nan,
                    "n_denom": 0,
                    "n_bins_used": 0,
                    "selected_center": np.nan,
                },
                "phi": {
                    "eff": np.nan,
                    "unc": np.nan,
                    "n_denom": 0,
                    "n_bins_used": 0,
                    "selected_center": np.nan,
                },
            },
            "accepted_indices": None,
            "robust_x_summary_accepted_indices": None,
            "robust_x_summary_fired_indices": None,
            "robust_x_plateau_accepted_indices": None,
            "robust_x_plateau_fired_indices": None,
            "robust_y_plateau_accepted_indices": None,
            "robust_y_plateau_fired_indices": None,
            "robust_phi_plateau_accepted_indices": None,
            "robust_phi_plateau_fired_indices": None,
            "robust_x_center_eff": np.nan,
            "robust_xyphi_accepted_indices": None,
            "robust_xyphi_fired_indices": None,
            "robust_xyphi_eff": np.nan,
        }

        projection = _fit_three_plane_telescope_projection(
            x_hits_all,
            y_hits_all,
            z_arr,
            plane - 1,
        )
        # Denominator/numerator are both defined from tt_task4_fit combinations:
        # pool in {3-plane,1234}, fired in {1234}.
        pool_mask = np.isin(pool_tt_all, plane_pool_tt[plane]) & projection["valid"]
        if int(np.sum(pool_mask)) < int(cfg_eff["min_pool_events"]):
            payload["plane_results"][plane] = plane_result
            continue

        x_pred = projection["x_pred"][pool_mask]
        y_pred = projection["y_pred"][pool_mask]
        theta_pred_deg = projection["theta_pred_deg"][pool_mask]
        phi_pred_deg = projection["phi_pred_deg"][pool_mask]
        charge_pred = charge_all[pool_mask]
        fired = (dtt_all[pool_mask] == 1234).astype(float)

        # x_left, x_right = _task4_resolve_region_bounds(
        #     cfg_fiducial.get("x_left", None),
        #     cfg_fiducial.get("x_right", None),
        #     -float(strip_half),
        #     float(strip_half),
        # )
        plane_x_cfg = cfg_fiducial.get("x_by_plane", {}).get(plane, {})
        x_left, x_right = _task4_resolve_region_bounds(
            plane_x_cfg.get("left", None),
            plane_x_cfg.get("right", None),
            -float(width_half),
            float(width_half),
        )
        plane_y_cfg = cfg_fiducial.get("y_by_plane", {}).get(plane, {})
        y_left, y_right = _task4_resolve_region_bounds(
            plane_y_cfg.get("left", None),
            plane_y_cfg.get("right", None),
            -float(width_half),
            float(width_half),
        )

        accepted_region = (
            np.isfinite(x_pred)
            & np.isfinite(y_pred)
            & (x_pred >= x_left)
            & (x_pred <= x_right)
            & (y_pred >= y_left)
            & (y_pred <= y_right)
        )
        charge_left = cfg_fiducial.get("event_charge_left", None)
        charge_right = cfg_fiducial.get("event_charge_right", None)
        if charge_left is not None or charge_right is not None:
            charge_pass = np.isfinite(charge_pred)
            if charge_left is not None:
                charge_pass &= charge_pred >= float(charge_left)
            if charge_right is not None:
                charge_pass &= charge_pred <= float(charge_right)
            accepted_region &= charge_pass

        theta_left_deg = cfg_fiducial.get("theta_left_deg", None)
        theta_right_deg = cfg_fiducial.get("theta_right_deg", None)
        if theta_left_deg is not None or theta_right_deg is not None:
            theta_pass = np.isfinite(theta_pred_deg)
            if theta_left_deg is not None:
                theta_pass &= theta_pred_deg >= float(theta_left_deg)
            if theta_right_deg is not None:
                theta_pass &= theta_pred_deg <= float(theta_right_deg)
            accepted_region &= theta_pass

        accepted_theta = accepted_region & np.isfinite(theta_pred_deg)
        accepted_phi = accepted_region & np.isfinite(phi_pred_deg)
        accepted_theta_phi = accepted_theta & np.isfinite(phi_pred_deg)

        x_acc = x_pred[accepted_region]
        y_acc = y_pred[accepted_region]
        fired_acc = fired[accepted_region]
        accepted_index = df_plot.index[pool_mask][accepted_region]
        theta_acc = theta_pred_deg[accepted_theta]
        fired_theta = fired[accepted_theta]
        phi_acc = phi_pred_deg[accepted_phi]
        fired_phi = fired[accepted_phi]
        theta_map_acc = theta_pred_deg[accepted_theta_phi]
        phi_map_acc = phi_pred_deg[accepted_theta_phi]
        fired_theta_phi = fired[accepted_theta_phi]

        plane_result["n_denom"] = int(len(fired_acc))
        plane_result["accepted_indices"] = pd.Index(accepted_index)
        if len(fired_acc) > 0:
            plane_result["overall_eff"] = float(np.mean(fired_acc) * 100.0)

        if len(fired_acc) >= int(cfg_eff["min_accepted_events"]):
            num_2d, _, _ = np.histogram2d(
                x_acc[fired_acc > 0.5],
                y_acc[fired_acc > 0.5],
                bins=[edges["x"], edges["y"]],
            )
            den_2d, _, _ = np.histogram2d(
                x_acc,
                y_acc,
                bins=[edges["x"], edges["y"]],
            )
            with np.errstate(invalid="ignore", divide="ignore"):
                plane_result["eff_2d"] = np.where(den_2d > 0, num_2d / den_2d, np.nan)

            plane_result["x"] = _make_efficiency_curve(x_acc, fired_acc, edges["x"])
            plane_result["y"] = _make_efficiency_curve(y_acc, fired_acc, edges["y"])
            x_scalar_summary = _compute_efficiency_scalar_summary(
                plane_result["x"],
                "x",
                cfg_eff,
            )
            plane_result["robust_x_center_eff"] = float(x_scalar_summary.get("eff", np.nan))
            plane_result["robust_x_summary_accepted_indices"] = _select_efficiency_summary_event_indices(
                plane_result["x"],
                cfg_eff=cfg_eff,
                axis_values=x_acc,
                bins=edges["x"],
                accepted_indices=accepted_index,
                axis_name="x",
            )
            plane_result["robust_x_summary_fired_indices"] = _select_efficiency_summary_event_indices(
                plane_result["x"],
                cfg_eff=cfg_eff,
                axis_values=x_acc,
                bins=edges["x"],
                accepted_indices=accepted_index,
                axis_name="x",
                fired=fired_acc,
                fired_only=True,
            )
            plane_result["robust_x_plateau_accepted_indices"] = _select_robust_plateau_event_indices(
                plane_result["x"],
                cfg_eff=cfg_eff,
                axis_values=x_acc,
                bins=edges["x"],
                accepted_indices=accepted_index,
                axis_name="x",
                tolerance=_ROBUST_EFFICIENCY_PLATEAU_TOLERANCE,
                center_eff=plane_result["robust_x_center_eff"],
            )
            plane_result["robust_x_plateau_fired_indices"] = _select_robust_plateau_event_indices(
                plane_result["x"],
                cfg_eff=cfg_eff,
                axis_values=x_acc,
                bins=edges["x"],
                accepted_indices=accepted_index,
                axis_name="x",
                tolerance=_ROBUST_EFFICIENCY_PLATEAU_TOLERANCE,
                center_eff=plane_result["robust_x_center_eff"],
                fired=fired_acc,
                fired_only=True,
            )
            any_plane_available = True

        if len(fired_theta) >= int(cfg_eff["min_accepted_events"]):
            plane_result["theta"] = _make_efficiency_curve(
                theta_acc,
                fired_theta,
                edges["theta"],
            )
            any_plane_available = True

        if len(fired_phi) >= int(cfg_eff["min_accepted_events"]):
            plane_result["phi"] = _make_efficiency_curve(
                phi_acc,
                fired_phi,
                edges["phi"],
            )
            any_plane_available = True

        if len(fired_theta_phi) >= int(cfg_eff["min_accepted_events"]):
            num_theta_phi, _, _ = np.histogram2d(
                theta_map_acc[fired_theta_phi > 0.5],
                phi_map_acc[fired_theta_phi > 0.5],
                bins=[edges["theta"], edges["phi"]],
            )
            den_theta_phi, _, _ = np.histogram2d(
                theta_map_acc,
                phi_map_acc,
                bins=[edges["theta"], edges["phi"]],
            )
            with np.errstate(invalid="ignore", divide="ignore"):
                plane_result["eff_theta_phi"] = np.where(
                    den_theta_phi > 0,
                    num_theta_phi / den_theta_phi,
                    np.nan,
                )
            any_plane_available = True

        y_scalar_summary = _compute_efficiency_scalar_summary(
            plane_result.get("y", {}),
            "y",
            cfg_eff,
        )
        theta_scalar_summary = _compute_efficiency_scalar_summary(
            plane_result.get("theta", {}),
            "theta",
            cfg_eff,
        )
        phi_scalar_summary = _compute_efficiency_scalar_summary(
            plane_result.get("phi", {}),
            "phi",
            cfg_eff,
        )
        plane_result["scalar_summary"] = {
            "x": x_scalar_summary,
            "y": y_scalar_summary,
            "theta": theta_scalar_summary,
            "phi": phi_scalar_summary,
        }
        plane_result["robust_x_center_eff"] = float(
            plane_result["scalar_summary"]["x"].get("eff", np.nan)
        )
        plane_result["robust_y_plateau_accepted_indices"] = _select_robust_plateau_event_indices(
            plane_result.get("y", {}),
            cfg_eff=cfg_eff,
            axis_values=y_acc,
            bins=edges["y"],
            accepted_indices=accepted_index,
            axis_name="y",
            tolerance=_ROBUST_EFFICIENCY_PLATEAU_TOLERANCE,
            center_eff=y_scalar_summary.get("eff", np.nan),
        )
        plane_result["robust_y_plateau_fired_indices"] = _select_robust_plateau_event_indices(
            plane_result.get("y", {}),
            cfg_eff=cfg_eff,
            axis_values=y_acc,
            bins=edges["y"],
            accepted_indices=accepted_index,
            axis_name="y",
            tolerance=_ROBUST_EFFICIENCY_PLATEAU_TOLERANCE,
            center_eff=y_scalar_summary.get("eff", np.nan),
            fired=fired_acc,
            fired_only=True,
        )
        plane_result["robust_phi_plateau_accepted_indices"] = _select_robust_plateau_event_indices(
            plane_result.get("phi", {}),
            cfg_eff=cfg_eff,
            axis_values=phi_acc,
            bins=edges["phi"],
            accepted_indices=pd.Index(df_plot.index[pool_mask][accepted_phi]),
            axis_name="phi",
            tolerance=_ROBUST_EFFICIENCY_PLATEAU_TOLERANCE,
            center_eff=phi_scalar_summary.get("eff", np.nan),
        )
        plane_result["robust_phi_plateau_fired_indices"] = _select_robust_plateau_event_indices(
            plane_result.get("phi", {}),
            cfg_eff=cfg_eff,
            axis_values=phi_acc,
            bins=edges["phi"],
            accepted_indices=pd.Index(df_plot.index[pool_mask][accepted_phi]),
            axis_name="phi",
            tolerance=_ROBUST_EFFICIENCY_PLATEAU_TOLERANCE,
            center_eff=phi_scalar_summary.get("eff", np.nan),
            fired=fired_phi,
            fired_only=True,
        )
        plane_result["robust_xyphi_accepted_indices"] = _intersect_required_indices(
            plane_result.get("robust_x_plateau_accepted_indices", None),
            plane_result.get("robust_y_plateau_accepted_indices", None),
            plane_result.get("robust_phi_plateau_accepted_indices", None),
        )
        plane_result["robust_xyphi_fired_indices"] = _intersect_required_indices(
            plane_result.get("robust_x_plateau_fired_indices", None),
            plane_result.get("robust_y_plateau_fired_indices", None),
            plane_result.get("robust_phi_plateau_fired_indices", None),
        )
        if plane_result["robust_xyphi_accepted_indices"] is not None:
            robust_xyphi_n_denom = int(len(plane_result["robust_xyphi_accepted_indices"]))
            robust_xyphi_fired_index = plane_result.get("robust_xyphi_fired_indices", None)
            robust_xyphi_n_num = int(len(robust_xyphi_fired_index)) if robust_xyphi_fired_index is not None else 0
            if robust_xyphi_n_denom > 0:
                plane_result["robust_xyphi_eff"] = float(robust_xyphi_n_num / robust_xyphi_n_denom)

        payload["plane_results"][plane] = plane_result

    payload["available"] = bool(any_plane_available)
    if not payload["available"] and not payload["reason"]:
        payload["reason"] = "no_planes_with_minimum_statistics"
    return payload

def _flatten_track_based_efficiency_metadata(
    payload,
    *,
    filename_base,
    execution_timestamp,
    param_hash,
):
    row = {
        "filename_base": filename_base,
        "execution_timestamp": execution_timestamp,
        "param_hash": param_hash,
        "efficiency_metadata_available": bool(isinstance(payload, dict) and payload.get("available", False)),
        "efficiency_metadata_reason": (
            str(payload.get("reason", "")) if isinstance(payload, dict) else "payload_missing"
        ),
    }
    if not isinstance(payload, dict):
        return row

    cfg_eff = payload.get("config", {})
    if isinstance(cfg_eff, dict):
        for key in (
            "x_bin_count",
            "y_bin_count",
            "theta_bin_count",
            "phi_bin_count",
            "min_pool_events",
            "min_accepted_events",
            "summary_fiducial_x_abs_max_mm",
            "summary_fiducial_y_abs_max_mm",
            "summary_fiducial_theta_max_deg",
            "summary_fiducial_phi_abs_max_deg",
            "phi_min_deg",
            "phi_max_deg",
        ):
            row[f"efficiency_metadata_{key}"] = cfg_eff.get(key, "")

    for plane in range(1, 5):
        plane_result = payload.get("plane_results", {}).get(plane, {})
        row[f"efficiency_vector_p{plane}_overall_eff_percent"] = plane_result.get("overall_eff", "")
        row[f"efficiency_vector_p{plane}_n_denom"] = plane_result.get("n_denom", "")
        scalar_summary = plane_result.get("scalar_summary", {})
        for axis_name in _EFFICIENCY_VECTOR_AXIS_ORDER:
            summary = scalar_summary.get(axis_name, {})
            row[f"efficiency_scalar_p{plane}_{axis_name}_fiducial_eff"] = summary.get("eff", "")
            row[f"efficiency_scalar_p{plane}_{axis_name}_fiducial_unc"] = summary.get("unc", "")
            row[f"efficiency_scalar_p{plane}_{axis_name}_fiducial_n_denom"] = summary.get("n_denom", "")
            row[f"efficiency_scalar_p{plane}_{axis_name}_fiducial_n_bins_used"] = summary.get("n_bins_used", "")
            if axis_name == "theta":
                row[f"efficiency_scalar_p{plane}_{axis_name}_fiducial_selected_center_deg"] = summary.get(
                    "selected_center", ""
                )

        for axis_name in _EFFICIENCY_VECTOR_AXIS_ORDER:
            axis_payload = plane_result.get(axis_name, {})
            centers = np.asarray(axis_payload.get("centers", []), dtype=float)
            eff_vals = np.asarray(axis_payload.get("eff", []), dtype=float)
            unc_vals = np.asarray(axis_payload.get("unc", []), dtype=float)
            center_field = _efficiency_center_field(axis_name)
            n_bins = max(len(centers), len(eff_vals), len(unc_vals))
            for idx in range(n_bins):
                prefix = f"efficiency_vector_p{plane}_{axis_name}_bin_{idx:03d}"
                center_val = centers[idx] if idx < len(centers) else np.nan
                eff_val = eff_vals[idx] if idx < len(eff_vals) else np.nan
                unc_val = unc_vals[idx] if idx < len(unc_vals) else np.nan
                row[f"{prefix}_{center_field}"] = center_val
                row[f"{prefix}_eff"] = eff_val
                row[f"{prefix}_unc"] = unc_val
    return row

def _format_task4_efficiency_vector_title_line(payload) -> str:
    if not isinstance(payload, dict):
        return "Track-based efficiency vector (3-plane -> 4-plane): unavailable"

    plane_results = payload.get("plane_results", {})
    if not isinstance(plane_results, dict):
        return "Track-based efficiency vector (3-plane -> 4-plane): unavailable"

    fragments: list[str] = []
    for plane in range(1, 5):
        plane_result = plane_results.get(plane, {})
        if not isinstance(plane_result, dict):
            fragments.append(f"P{plane}=n/a")
            continue
        overall_eff = plane_result.get("overall_eff", np.nan)
        n_denom = int(plane_result.get("n_denom", 0) or 0)
        if np.isfinite(overall_eff) and n_denom > 0:
            fragments.append(f"P{plane}={float(overall_eff):.1f}%")
        else:
            fragments.append(f"P{plane}=n/a")
    return "Track-based efficiency vector (3-plane -> 4-plane): " + ", ".join(fragments)

def _format_task4_simulated_efficiency_title_line(sim_efficiencies_percent) -> str:
    if not sim_efficiencies_percent:
        return "Simulation reference: unavailable"
    fragments: list[str] = []
    for plane in range(1, 5):
        if plane - 1 < len(sim_efficiencies_percent) and np.isfinite(sim_efficiencies_percent[plane - 1]):
            fragments.append(f"P{plane}={float(sim_efficiencies_percent[plane - 1]):.1f}%")
        else:
            fragments.append(f"P{plane}=n/a")
    return "Simulation reference: " + ", ".join(fragments)

def _resolve_track_efficiency_four_plane_fiducial_index(
    payload,
    *,
    tt_task4_fit_1234_index: pd.Index | None = None,
) -> pd.Index:
    if not isinstance(payload, dict):
        return pd.Index([])
    plane_results = payload.get("plane_results", {})
    if not isinstance(plane_results, dict):
        return pd.Index([])

    accepted_indices: list[pd.Index] = []
    for plane in range(1, 5):
        plane_result = plane_results.get(plane, {})
        if not isinstance(plane_result, dict):
            return pd.Index([])
        accepted = plane_result.get("accepted_indices", None)
        if accepted is None:
            return pd.Index([])
        accepted_indices.append(pd.Index(accepted))

    if not accepted_indices:
        return pd.Index([])

    fiducial_index = accepted_indices[0]
    for accepted_index in accepted_indices[1:]:
        fiducial_index = fiducial_index.intersection(accepted_index, sort=False)

    if tt_task4_fit_1234_index is not None:
        fiducial_index = fiducial_index.intersection(pd.Index(tt_task4_fit_1234_index), sort=False)
    return fiducial_index

def _resolve_track_efficiency_representative(plane_result):
    if not isinstance(plane_result, dict):
        return (np.nan, "fid representative", "missing", None, None)

    xyphi_eff = plane_result.get("robust_xyphi_eff", np.nan)
    xyphi_accepted = plane_result.get("robust_xyphi_accepted_indices", None)
    xyphi_fired = plane_result.get("robust_xyphi_fired_indices", None)
    if np.isfinite(xyphi_eff):
        return (
            float(xyphi_eff),
            "fid representative x/y/phi plateau",
            "xyphi_plateau",
            pd.Index(xyphi_accepted) if xyphi_accepted is not None else None,
            pd.Index(xyphi_fired) if xyphi_fired is not None else None,
        )

    x_summary_eff = plane_result.get("robust_x_center_eff", np.nan)
    x_summary_accepted = plane_result.get("robust_x_summary_accepted_indices", None)
    x_summary_fired = plane_result.get("robust_x_summary_fired_indices", None)
    if np.isfinite(x_summary_eff):
        return (
            float(x_summary_eff),
            "fid representative x-summary",
            "x_summary",
            pd.Index(x_summary_accepted) if x_summary_accepted is not None else None,
            pd.Index(x_summary_fired) if x_summary_fired is not None else None,
        )

    overall_eff_percent = plane_result.get("overall_eff", np.nan)
    if np.isfinite(overall_eff_percent):
        return (
            float(overall_eff_percent) / 100.0,
            "fid overall",
            "overall",
            None,
            None,
        )

    return (np.nan, "fid representative", "missing", None, None)


def _format_robust_efficiency_trace_line(row) -> str:
    def _fmt(value):
        try:
            out = float(value)
        except (TypeError, ValueError):
            out = np.nan
        return f"{out:.4f}" if np.isfinite(out) else "nan"

    fragments: list[str] = []
    for plane in range(1, 5):
        robust_eff = row.get(f"eff{plane}_robust", np.nan)
        robust_xyphi_eff = row.get(f"eff{plane}_robust_xyphi", np.nan)
        center_eff = row.get(f"eff{plane}_median_x", np.nan)
        robust_n_denom = row.get(f"eff{plane}_robust_n_denom", np.nan)
        plateau_eff = row.get(f"eff{plane}_plateau", np.nan)
        overall_eff = row.get(f"eff{plane}_overall", np.nan)
        n_bins = row.get(f"eff{plane}_n_valid_bins", 0)
        n_plateau_bins = row.get(f"eff{plane}_n_plateau_bins", 0)
        fragments.append(
            f"P{plane}(robust={_fmt(robust_eff)}, "
            f"xyphi={_fmt(robust_xyphi_eff)}, "
            f"median_x={_fmt(center_eff)}, "
            f"robust_n_denom={int(robust_n_denom) if np.isfinite(robust_n_denom) else 'nan'}, "
            f"plateau={_fmt(plateau_eff)}, "
            f"overall={_fmt(overall_eff)}, "
            f"bins={int(n_bins or 0)}, plateau_bins={int(n_plateau_bins or 0)})"
        )
    return (
        f"[ROBUST_EFF_TRACE] filename_base={row.get('filename_base', '')} "
        + " ".join(fragments)
    )

def _build_robust_efficiency_row(
    payload,
    *,
    df_events: pd.DataFrame,
    denominator_seconds: float,
    filename_base: str,
    execution_timestamp: str,
    param_hash: str,
):
    row = {
        "filename_base": filename_base,
        "execution_timestamp": execution_timestamp,
        "param_hash": param_hash,
        "robust_efficiency_trigger_source": (
            str(payload.get("trigger_source", "")) if isinstance(payload, dict) else ""
        ),
    }

    plane_results = payload.get("plane_results", {}) if isinstance(payload, dict) else {}
    cfg_eff = payload.get("config", {}) if isinstance(payload, dict) else {}
    plane_fiducial_accepted_indices: dict[int, pd.Index] = {}
    plane_plateau_indices: dict[int, pd.Index] = {}
    plane_plateau_accepted_indices: dict[int, pd.Index] = {}
    for plane in range(1, 5):
        plane_result = plane_results.get(plane, {}) if isinstance(plane_results, dict) else {}
        axis_payload = plane_result.get("x", {}) if isinstance(plane_result, dict) else {}
        accepted_indices = (
            plane_result.get("accepted_indices", None)
            if isinstance(plane_result, dict)
            else None
        )
        if accepted_indices is not None:
            plane_fiducial_accepted_indices[plane] = pd.Index(accepted_indices)
        _, eff_vals, _, _, valid = _extract_efficiency_summary_arrays(
            axis_payload,
            "x",
            cfg_eff,
        )
        center_eff = plane_result.get("robust_x_center_eff", np.nan)
        center_eff = float(center_eff) if np.isfinite(center_eff) else _compute_robust_x_center_eff(
            axis_payload,
            cfg_eff,
        )
        (
            representative_eff,
            _representative_label,
            representative_method,
            representative_accepted_index,
            representative_fired_index,
        ) = _resolve_track_efficiency_representative(plane_result)
        overall_eff_percent = plane_result.get("overall_eff", np.nan) if isinstance(plane_result, dict) else np.nan
        overall_eff_fraction = (
            float(overall_eff_percent) / 100.0
            if np.isfinite(overall_eff_percent)
            else np.nan
        )
        row[f"eff{plane}_n_valid_bins"] = int(np.sum(valid))
        if np.any(valid) and np.isfinite(center_eff):
            plateau_bins = valid & (
                np.abs(eff_vals - center_eff) <= _ROBUST_EFFICIENCY_PLATEAU_TOLERANCE
            )
            row[f"eff{plane}_n_plateau_bins"] = int(np.sum(plateau_bins))
        else:
            row[f"eff{plane}_n_plateau_bins"] = 0
        row[f"eff{plane}_robust_method"] = representative_method
        row[f"eff{plane}_robust"] = representative_eff
        row[f"eff{plane}_robust_xyphi"] = plane_result.get("robust_xyphi_eff", np.nan)
        row[f"eff{plane}_median_x"] = center_eff
        row[f"eff{plane}_overall"] = overall_eff_fraction
        row[f"eff{plane}"] = representative_eff if np.isfinite(representative_eff) else overall_eff_fraction

        robust_xyphi_accepted = (
            plane_result.get("robust_xyphi_accepted_indices", None) if isinstance(plane_result, dict) else None
        )
        if robust_xyphi_accepted is not None:
            row[f"eff{plane}_robust_xyphi_n_denom"] = int(len(pd.Index(robust_xyphi_accepted)))
        else:
            row[f"eff{plane}_robust_xyphi_n_denom"] = np.nan

        robust_xyphi_fired = (
            plane_result.get("robust_xyphi_fired_indices", None) if isinstance(plane_result, dict) else None
        )
        if robust_xyphi_fired is not None:
            row[f"eff{plane}_robust_xyphi_n_num"] = int(len(pd.Index(robust_xyphi_fired)))
        else:
            row[f"eff{plane}_robust_xyphi_n_num"] = np.nan

        if representative_accepted_index is not None:
            row[f"eff{plane}_robust_n_denom"] = int(len(representative_accepted_index))
        else:
            robust_scalar_summary = plane_result.get("scalar_summary", {}).get("x", {})
            robust_n_denom = robust_scalar_summary.get("n_denom", np.nan)
            row[f"eff{plane}_robust_n_denom"] = (
                int(robust_n_denom) if np.isfinite(robust_n_denom) else np.nan
            )

        if representative_fired_index is not None:
            row[f"eff{plane}_robust_n_num"] = int(len(representative_fired_index))
        else:
            if np.isfinite(representative_eff) and np.isfinite(row[f"eff{plane}_robust_n_denom"]):
                row[f"eff{plane}_robust_n_num"] = int(
                    round(float(representative_eff) * float(row[f"eff{plane}_robust_n_denom"]))
                )
            else:
                row[f"eff{plane}_robust_n_num"] = np.nan

        plateau_accepted = (
            plane_result.get("robust_x_plateau_accepted_indices", None)
            if isinstance(plane_result, dict)
            else None
        )
        if plateau_accepted is not None:
            plateau_accepted_index = pd.Index(plateau_accepted)
            plane_plateau_accepted_indices[plane] = plateau_accepted_index
            row[f"eff{plane}_plateau_n_denom"] = int(len(plateau_accepted_index))
        else:
            row[f"eff{plane}_plateau_n_denom"] = np.nan

        plateau_fired = (
            plane_result.get("robust_x_plateau_fired_indices", None)
            if isinstance(plane_result, dict)
            else None
        )
        if plateau_fired is None:
            row[f"eff{plane}_plateau_n_num"] = np.nan
            row[f"eff{plane}_plateau"] = overall_eff_fraction
            row[f"eff{plane}"] = overall_eff_fraction
            continue
        plateau_fired_index = pd.Index(plateau_fired)
        plane_plateau_indices[plane] = plateau_fired_index
        row[f"eff{plane}_plateau_n_num"] = int(len(plateau_fired_index))

        plateau_eff = np.nan
        if plane in plane_plateau_accepted_indices and len(plane_plateau_accepted_indices[plane]) > 0:
            plateau_eff = float(len(plateau_fired_index) / len(plane_plateau_accepted_indices[plane]))
        row[f"eff{plane}_plateau"] = plateau_eff

    tt_task4_fit_1234_index = None
    if "tt_task4_fit" in df_events.columns:
        tt_values = pd.to_numeric(df_events["tt_task4_fit"], errors="coerce").to_numpy(dtype=float)
        tt_task4_fit_1234_index = pd.Index(df_events.index[tt_values == 1234.0])
        n_events_1234 = int(len(tt_task4_fit_1234_index))
    else:
        n_events_1234 = None

    total_events = int(len(df_events))
    denom = float(denominator_seconds) if np.isfinite(denominator_seconds) else 0.0
    row["count_rate_denominator_seconds"] = int(round(denom)) if denom > 0.0 else 0
    row["four_plane_count"] = int(n_events_1234) if n_events_1234 is not None else np.nan
    row["total_count"] = int(total_events)
    if n_events_1234 is not None and denom > 0.0:
        row["rate_1234_hz"] = float(n_events_1234 / denom)
    else:
        row["rate_1234_hz"] = np.nan

    robust_union_index = None
    robust_intersection_index = None
    if tt_task4_fit_1234_index is not None and plane_fiducial_accepted_indices:
        robust_indices = [
            accepted_index.intersection(tt_task4_fit_1234_index, sort=False)
            for accepted_index in plane_fiducial_accepted_indices.values()
        ]
        robust_union_index = robust_indices[0]
        robust_intersection_index = robust_indices[0]
        for robust_index in robust_indices[1:]:
            robust_union_index = robust_union_index.union(robust_index, sort=False)
            robust_intersection_index = robust_intersection_index.intersection(robust_index, sort=False)

    if robust_union_index is not None:
        row["four_plane_robust_count_union"] = int(len(robust_union_index))
        row["four_plane_robust_hz_union"] = float(len(robust_union_index) / denom) if denom > 0.0 else np.nan
    else:
        row["four_plane_robust_count_union"] = np.nan
        row["four_plane_robust_hz_union"] = np.nan

    if robust_intersection_index is not None:
        row["four_plane_robust_count_intersection"] = int(len(robust_intersection_index))
        row["four_plane_robust_hz_intersection"] = (
            float(len(robust_intersection_index) / denom)
            if denom > 0.0
            else np.nan
        )
    else:
        row["four_plane_robust_count_intersection"] = np.nan
        row["four_plane_robust_hz_intersection"] = np.nan

    if tt_task4_fit_1234_index is not None and len(plane_fiducial_accepted_indices) == 4 and robust_intersection_index is not None:
        n_events_four_plane_robust = int(len(robust_intersection_index))
        row["four_plane_robust_count"] = n_events_four_plane_robust
        row["four_plane_robust_hz"] = float(n_events_four_plane_robust / denom) if denom > 0.0 else np.nan
    else:
        row["four_plane_robust_count"] = np.nan
        row["four_plane_robust_hz"] = np.nan

    if denom > 0.0:
        row["rate_total_hz"] = float(total_events / denom)
    else:
        row["rate_total_hz"] = np.nan

    if n_events_1234 is not None and int(n_events_1234) > 0:
        union_count = row.get("four_plane_robust_count_union", np.nan)
        intersection_count = row.get("four_plane_robust_count_intersection", np.nan)
        default_count = row.get("four_plane_robust_count", np.nan)
        row["four_plane_robust_efficiency_union"] = (
            float(union_count) / float(n_events_1234)
            if np.isfinite(union_count)
            else np.nan
        )
        row["four_plane_robust_efficiency_intersection"] = (
            float(intersection_count) / float(n_events_1234)
            if np.isfinite(intersection_count)
            else np.nan
        )
        row["four_plane_robust_efficiency"] = (
            float(default_count) / float(n_events_1234)
            if np.isfinite(default_count)
            else np.nan
        )
    else:
        row["four_plane_robust_efficiency_union"] = np.nan
        row["four_plane_robust_efficiency_intersection"] = np.nan
        row["four_plane_robust_efficiency"] = np.nan
    return row

def _extract_projection_arrays(df_input: pd.DataFrame) -> tuple[np.ndarray | None, np.ndarray | None, str]:
    if {"tim_xp", "tim_yp"}.issubset(df_input.columns):
        return (
            pd.to_numeric(df_input["tim_xp"], errors="coerce").to_numpy(dtype=float),
            pd.to_numeric(df_input["tim_yp"], errors="coerce").to_numpy(dtype=float),
            "tim_xp_tim_yp",
        )

    if {"xp", "yp"}.issubset(df_input.columns):
        return (
            pd.to_numeric(df_input["xp"], errors="coerce").to_numpy(dtype=float),
            pd.to_numeric(df_input["yp"], errors="coerce").to_numpy(dtype=float),
            "xp_yp",
        )

    if {"theta", "phi"}.issubset(df_input.columns):
        theta_vals = pd.to_numeric(df_input["theta"], errors="coerce").to_numpy(dtype=float)
        phi_vals = pd.to_numeric(df_input["phi"], errors="coerce").to_numpy(dtype=float)
        tan_theta_vals = np.tan(theta_vals)
        return (
            tan_theta_vals * np.cos(phi_vals),
            tan_theta_vals * np.sin(phi_vals),
            "theta_phi_backcalc",
        )

    return None, None, "missing"

def _ellipse_scale_for_peak_fraction(peak_fraction: float) -> float:
    try:
        value = float(peak_fraction)
    except (TypeError, ValueError):
        return float("nan")
    if not np.isfinite(value) or not (0.0 < value < 1.0):
        return float("nan")
    return float(np.sqrt(max(0.0, -2.0 * np.log(value))))

def _fit_elliptical_gaussian_to_density(
    density: np.ndarray,
    x_centers: np.ndarray,
    y_centers: np.ndarray,
) -> dict[str, object] | None:
    density = np.asarray(density, dtype=float)
    if density.ndim != 2 or density.size == 0:
        return None

    weights = np.where(np.isfinite(density) & (density > 0.0), density, 0.0)
    total_weight = float(weights.sum())
    if total_weight <= 0.0:
        return None

    xx, yy = np.meshgrid(np.asarray(x_centers, dtype=float), np.asarray(y_centers, dtype=float), indexing="ij")
    x_flat = xx.ravel()
    y_flat = yy.ravel()
    w_flat = weights.ravel()
    positive = w_flat > 0.0
    if int(np.count_nonzero(positive)) < 6:
        return None

    x_vals = x_flat[positive]
    y_vals = y_flat[positive]
    w_vals = w_flat[positive]

    center_x = float(np.average(x_vals, weights=w_vals))
    center_y = float(np.average(y_vals, weights=w_vals))
    dx = x_vals - center_x
    dy = y_vals - center_y
    cov_xx = float(np.average(dx * dx, weights=w_vals))
    cov_xy = float(np.average(dx * dy, weights=w_vals))
    cov_yy = float(np.average(dy * dy, weights=w_vals))
    cov = np.array([[cov_xx, cov_xy], [cov_xy, cov_yy]], dtype=float)
    if not np.all(np.isfinite(cov)):
        return None

    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    eigvals = np.asarray(eigvals[order], dtype=float)
    eigvecs = np.asarray(eigvecs[:, order], dtype=float)
    eigvals = np.clip(eigvals, 0.0, None)
    if eigvals.size < 2 or eigvals[1] <= 0.0:
        return None

    sigma_major = float(np.sqrt(eigvals[0]))
    sigma_minor = float(np.sqrt(eigvals[1]))
    if not (np.isfinite(sigma_major) and np.isfinite(sigma_minor) and sigma_minor > 0.0):
        return None

    major_vector = eigvecs[:, 0]
    minor_vector = eigvecs[:, 1]
    rotation_deg = float(np.degrees(np.arctan2(major_vector[1], major_vector[0])))
    while rotation_deg > 90.0:
        rotation_deg -= 180.0
    while rotation_deg <= -90.0:
        rotation_deg += 180.0

    return {
        "center_x": center_x,
        "center_y": center_y,
        "cov_xx": cov_xx,
        "cov_yy": cov_yy,
        "sigma_x": float(np.sqrt(max(cov_xx, 0.0))),
        "sigma_y": float(np.sqrt(max(cov_yy, 0.0))),
        "sigma_major": sigma_major,
        "sigma_minor": sigma_minor,
        "major_vector": major_vector.astype(float),
        "minor_vector": minor_vector.astype(float),
        "rotation_deg": rotation_deg,
        "covariance": cov,
    }

def _build_projection_ellipse_diagnostic_payload(
    df_input: pd.DataFrame,
    cfg: dict[str, object],
) -> dict[str, object]:
    tt_col = get_task4_tt_column(df_input, preferred=TASK4_PRIMARY_TT_COLUMN)
    if tt_col is None:
        return {
            "available": False,
            "reason": "missing_tt_task4_fit",
            "config": cfg,
            "projection_source": "missing",
            "tt_results": {},
        }

    xproj_all, yproj_all, projection_source = _extract_projection_arrays(df_input)
    if xproj_all is None or yproj_all is None:
        return {
            "available": False,
            "reason": "missing_projection_columns",
            "config": cfg,
            "projection_source": projection_source,
            "tt_results": {},
        }

    tt_all = pd.to_numeric(df_input[tt_col], errors="coerce").fillna(0).to_numpy(dtype=np.int32)
    x_min = float(cfg["x_min"])
    x_max = float(cfg["x_max"])
    y_min = float(cfg["y_min"])
    y_max = float(cfg["y_max"])
    axis_quantile_min = float(cfg["axis_quantile_min"])
    axis_quantile_max = float(cfg["axis_quantile_max"])
    if axis_quantile_max <= axis_quantile_min:
        axis_quantile_min = 0.01
        axis_quantile_max = 0.99
    bin_count = int(cfg["bin_count"])
    fwhm_scale = _ellipse_scale_for_peak_fraction(0.5)

    tt_results: dict[str, dict[str, object]] = {}
    available_any = False
    for tt_label in tuple(cfg.get("focus_definitive_tt", ())):
        tt_int = int(normalize_tt_label(tt_label, default="0") or 0)
        tt_mask = tt_all == tt_int
        x_tt = np.asarray(xproj_all[tt_mask], dtype=float)
        y_tt = np.asarray(yproj_all[tt_mask], dtype=float)
        valid = (
            np.isfinite(x_tt)
            & np.isfinite(y_tt)
            & (x_tt >= x_min)
            & (x_tt <= x_max)
            & (y_tt >= y_min)
            & (y_tt <= y_max)
        )
        x_sel = x_tt[valid]
        y_sel = y_tt[valid]

        result: dict[str, object] = {
            "available": False,
            "reason": "insufficient_points",
            "tt_label": tt_label,
            "n_points": int(x_sel.size),
            "projection_source": projection_source,
        }
        if x_sel.size < int(cfg["min_points"]):
            tt_results[str(tt_label)] = result
            continue

        x_q_lo, x_q_hi = np.quantile(x_sel, [axis_quantile_min, axis_quantile_max])
        y_q_lo, y_q_hi = np.quantile(y_sel, [axis_quantile_min, axis_quantile_max])
        x_mid = 0.5 * float(x_q_lo + x_q_hi)
        y_mid = 0.5 * float(y_q_lo + y_q_hi)
        half_span = 0.5 * max(float(x_q_hi - x_q_lo), float(y_q_hi - y_q_lo))
        min_half_span = 0.025 * max(float(x_max - x_min), float(y_max - y_min))
        half_span = max(half_span, min_half_span)
        plot_x_min = max(float(x_min), x_mid - half_span)
        plot_x_max = min(float(x_max), x_mid + half_span)
        plot_y_min = max(float(y_min), y_mid - half_span)
        plot_y_max = min(float(y_max), y_mid + half_span)
        x_edges = np.linspace(plot_x_min, plot_x_max, bin_count + 1)
        y_edges = np.linspace(plot_y_min, plot_y_max, bin_count + 1)
        x_centers = 0.5 * (x_edges[:-1] + x_edges[1:])
        y_centers = 0.5 * (y_edges[:-1] + y_edges[1:])

        hist, _, _ = np.histogram2d(x_sel, y_sel, bins=[x_edges, y_edges])
        density = np.asarray(hist, dtype=float)
        sigma_bins = float(cfg["smoothing_sigma_bins"])
        if sigma_bins > 0.0:
            density = gaussian_filter(density, sigma=sigma_bins, mode="nearest")

        peak_density = float(np.nanmax(density)) if density.size > 0 else 0.0
        if not np.isfinite(peak_density) or peak_density <= 0.0:
            result["reason"] = "zero_density"
            tt_results[str(tt_label)] = result
            continue

        ellipse_model = _fit_elliptical_gaussian_to_density(density, x_centers, y_centers)
        if ellipse_model is None:
            result["reason"] = "ellipse_fit_failed"
            tt_results[str(tt_label)] = result
            continue

        sigma_major = float(ellipse_model["sigma_major"])
        sigma_minor = float(ellipse_model["sigma_minor"])
        major_vector = np.asarray(ellipse_model["major_vector"], dtype=float)
        minor_vector = np.asarray(ellipse_model["minor_vector"], dtype=float)
        fwhm_semiaxis_major = sigma_major * fwhm_scale
        fwhm_semiaxis_minor = sigma_minor * fwhm_scale
        fwhm_halfwidth_x = float(
            np.sqrt(
                (fwhm_semiaxis_major * major_vector[0]) ** 2
                + (fwhm_semiaxis_minor * minor_vector[0]) ** 2
            )
        )
        fwhm_halfwidth_y = float(
            np.sqrt(
                (fwhm_semiaxis_major * major_vector[1]) ** 2
                + (fwhm_semiaxis_minor * minor_vector[1]) ** 2
            )
        )
        fwhm_axis_ratio = (
            float(fwhm_semiaxis_major / fwhm_semiaxis_minor)
            if fwhm_semiaxis_minor > 0.0
            else float("nan")
        )
        fwhm_halfwidth_x_over_y = (
            float(fwhm_halfwidth_x / fwhm_halfwidth_y)
            if fwhm_halfwidth_y > 0.0
            else float("nan")
        )

        result.update(
            {
                "available": True,
                "reason": "ok",
                "peak_density": peak_density,
                "density": density,
                "normalized_density": density / peak_density,
                "x_edges": x_edges,
                "y_edges": y_edges,
                "x_centers": x_centers,
                "y_centers": y_centers,
                "contour_fractions": np.asarray(cfg["contour_fractions"], dtype=float),
                "ellipse_model": ellipse_model,
                "plot_x_min": plot_x_min,
                "plot_x_max": plot_x_max,
                "plot_y_min": plot_y_min,
                "plot_y_max": plot_y_max,
                "fwhm_semiaxis_major": float(fwhm_semiaxis_major),
                "fwhm_semiaxis_minor": float(fwhm_semiaxis_minor),
                "fwhm_axis_ratio_major_over_minor": fwhm_axis_ratio,
                "fwhm_halfwidth_xproj": fwhm_halfwidth_x,
                "fwhm_halfwidth_yproj": fwhm_halfwidth_y,
                "fwhm_halfwidth_x_over_y": fwhm_halfwidth_x_over_y,
            }
        )
        tt_results[str(tt_label)] = result
        available_any = True

    return {
        "available": available_any,
        "reason": "ok" if available_any else "no_valid_tt_payloads",
        "config": cfg,
        "projection_source": projection_source,
        "tt_results": tt_results,
    }

def _append_projection_ellipse_metadata(payload: dict[str, object]) -> None:
    cfg = payload.get("config", {})
    tt_results = payload.get("tt_results", {})
    if not isinstance(cfg, dict):
        cfg = {}
    if not isinstance(tt_results, dict):
        tt_results = {}

    global_variables["timtrack_projection_ellipse_available"] = bool(payload.get("available", False))
    global_variables["timtrack_projection_ellipse_reason"] = str(payload.get("reason", ""))
    global_variables["timtrack_projection_ellipse_projection_source"] = str(
        payload.get("projection_source", "missing")
    )
    global_variables["timtrack_projection_ellipse_bin_count"] = int(cfg.get("bin_count", 0) or 0)
    global_variables["timtrack_projection_ellipse_min_points"] = int(cfg.get("min_points", 0) or 0)
    global_variables["timtrack_projection_ellipse_smoothing_sigma_bins"] = float(
        cfg.get("smoothing_sigma_bins", np.nan)
    )
    global_variables["timtrack_projection_ellipse_axis_quantile_min"] = float(
        cfg.get("axis_quantile_min", np.nan)
    )
    global_variables["timtrack_projection_ellipse_axis_quantile_max"] = float(
        cfg.get("axis_quantile_max", np.nan)
    )
    global_variables["timtrack_projection_ellipse_cmap"] = str(cfg.get("cmap", ""))
    global_variables["timtrack_projection_ellipse_contour_fractions"] = [
        float(value) for value in tuple(cfg.get("contour_fractions", ()))
    ]

    for tt_label in tuple(cfg.get("focus_definitive_tt", ())):
        result = tt_results.get(str(tt_label), {})
        prefix = f"timtrack_projection_ellipse_tt_{tt_label}"
        available = bool(isinstance(result, dict) and result.get("available", False))
        global_variables[f"{prefix}_available"] = available
        global_variables[f"{prefix}_reason"] = (
            str(result.get("reason", "")) if isinstance(result, dict) else "missing"
        )
        global_variables[f"{prefix}_n_points"] = int(result.get("n_points", 0) or 0)
        global_variables[f"{prefix}_peak_density"] = (
            float(result.get("peak_density", np.nan)) if available else np.nan
        )
        if not available:
            for suffix in (
                "center_xproj",
                "center_yproj",
                "plot_x_min",
                "plot_x_max",
                "plot_y_min",
                "plot_y_max",
                "xproj_scaling_factor_to_match_y",
                "rotation_deg",
                "sigma_x",
                "sigma_y",
                "fwhm_semiaxis_major",
                "fwhm_semiaxis_minor",
                "fwhm_axis_ratio_major_over_minor",
                "fwhm_halfwidth_xproj",
                "fwhm_halfwidth_yproj",
                "fwhm_halfwidth_x_over_y",
            ):
                global_variables[f"{prefix}_{suffix}"] = np.nan
            continue

        ellipse_model = result.get("ellipse_model", {})
        if not isinstance(ellipse_model, dict):
            ellipse_model = {}
        global_variables[f"{prefix}_center_xproj"] = float(ellipse_model.get("center_x", np.nan))
        global_variables[f"{prefix}_center_yproj"] = float(ellipse_model.get("center_y", np.nan))
        global_variables[f"{prefix}_plot_x_min"] = float(result.get("plot_x_min", np.nan))
        global_variables[f"{prefix}_plot_x_max"] = float(result.get("plot_x_max", np.nan))
        global_variables[f"{prefix}_plot_y_min"] = float(result.get("plot_y_min", np.nan))
        global_variables[f"{prefix}_plot_y_max"] = float(result.get("plot_y_max", np.nan))
        _scaling_factor = (
            float(result.get("fwhm_halfwidth_yproj", np.nan)) / float(result.get("fwhm_halfwidth_xproj", np.nan))
            if np.isfinite(float(result.get("fwhm_halfwidth_xproj", np.nan)))
            and float(result.get("fwhm_halfwidth_xproj", np.nan)) > 0.0
            and np.isfinite(float(result.get("fwhm_halfwidth_yproj", np.nan)))
            else np.nan
        )
        global_variables[f"{prefix}_xproj_scaling_factor_to_match_y"] = _scaling_factor
        global_variables[f"{prefix}_rotation_deg"] = float(ellipse_model.get("rotation_deg", np.nan))
        global_variables[f"{prefix}_sigma_x"] = float(ellipse_model.get("sigma_x", np.nan))
        global_variables[f"{prefix}_sigma_y"] = float(ellipse_model.get("sigma_y", np.nan))
        global_variables[f"{prefix}_fwhm_semiaxis_major"] = float(
            result.get("fwhm_semiaxis_major", np.nan)
        )
        global_variables[f"{prefix}_fwhm_semiaxis_minor"] = float(
            result.get("fwhm_semiaxis_minor", np.nan)
        )
        global_variables[f"{prefix}_fwhm_axis_ratio_major_over_minor"] = float(
            result.get("fwhm_axis_ratio_major_over_minor", np.nan)
        )
        global_variables[f"{prefix}_fwhm_halfwidth_xproj"] = float(
            result.get("fwhm_halfwidth_xproj", np.nan)
        )
        global_variables[f"{prefix}_fwhm_halfwidth_yproj"] = float(
            result.get("fwhm_halfwidth_yproj", np.nan)
        )
        global_variables[f"{prefix}_fwhm_halfwidth_x_over_y"] = float(
            result.get("fwhm_halfwidth_x_over_y", np.nan)
        )

def _select_projection_scaling_reference(
    payload: dict[str, object],
) -> tuple[str | None, dict[str, object] | None]:
    tt_results = payload.get("tt_results", {})
    if not isinstance(tt_results, dict):
        return None, None

    best_label: str | None = None
    best_result: dict[str, object] | None = None
    best_n = -1
    for tt_label, result in tt_results.items():
        if not isinstance(result, dict) or not bool(result.get("available", False)):
            continue
        n_points = int(result.get("n_points", 0) or 0)
        if n_points > best_n:
            best_label = str(tt_label)
            best_result = result
            best_n = n_points
    return best_label, best_result

def _summarize_projection_scaling(payload: dict[str, object]) -> dict[str, object]:
    tt_results = payload.get("tt_results", {})
    if not isinstance(tt_results, dict):
        return {
            "global_factor": np.nan,
            "global_method": "weighted_mean_by_n_points",
            "n_contributing_tts": 0,
            "total_weight": 0.0,
        }

    factors: list[float] = []
    weights: list[float] = []
    for result in tt_results.values():
        if not isinstance(result, dict) or not bool(result.get("available", False)):
            continue
        x_half = float(result.get("fwhm_halfwidth_xproj", np.nan))
        y_half = float(result.get("fwhm_halfwidth_yproj", np.nan))
        n_points = int(result.get("n_points", 0) or 0)
        if not (np.isfinite(x_half) and x_half > 0.0 and np.isfinite(y_half) and n_points > 0):
            continue
        factors.append(float(y_half / x_half))
        weights.append(float(n_points))

    if not factors:
        return {
            "global_factor": np.nan,
            "global_method": "weighted_mean_by_n_points",
            "n_contributing_tts": 0,
            "total_weight": 0.0,
        }

    factor_arr = np.asarray(factors, dtype=float)
    weight_arr = np.asarray(weights, dtype=float)
    global_factor = float(np.average(factor_arr, weights=weight_arr))
    return {
        "global_factor": global_factor,
        "global_method": "weighted_mean_by_n_points",
        "n_contributing_tts": int(len(factor_arr)),
        "total_weight": float(np.sum(weight_arr)),
    }


def _build_offender_tt_labels(values: pd.Series) -> np.ndarray:
    return np.asarray(
        [normalize_tt_label(value, default="0") for value in values],
        dtype=object,
    )

def _resolve_offender_focus_tts(tt_labels: np.ndarray) -> tuple[str, ...]:
    available = [tt_label for tt_label in _OFFENDER_FOCUS_TTS if np.any(tt_labels == tt_label)]
    if available:
        return tuple(available)
    fallback = sorted(
        {
            str(tt_label)
            for tt_label in tt_labels
            if str(tt_label) not in ("", "0", "nan", "None")
        },
        key=lambda tt_label: (len(tt_label), tt_label),
    )
    return tuple(fallback[: min(5, len(fallback))])

def _make_offender_hist_bins(
    values: np.ndarray,
    fallback: tuple[float, float],
    *,
    nbins: int = 55,
    clip_percentiles: tuple[float, float] = (0.5, 99.5),
    force_zero_left: bool = False,
) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        left, right = fallback
    else:
        left = float(np.nanpercentile(arr, clip_percentiles[0]))
        right = float(np.nanpercentile(arr, clip_percentiles[1]))
        if force_zero_left:
            left = 0.0
        if not np.isfinite(left) or not np.isfinite(right):
            left, right = fallback
    if not np.isfinite(left) or not np.isfinite(right):
        left, right = fallback
    if right <= left:
        span = float(abs(fallback[1] - fallback[0])) if np.isfinite(fallback[1] - fallback[0]) else 1.0
        if span <= 0:
            span = 1.0
        right = left + span
    return np.linspace(left, right, nbins)

def _resolve_total_offender_counts(df_input: pd.DataFrame) -> tuple[np.ndarray | None, str]:
    if "filter_total_problematic_offender_count" in df_input.columns:
        counts = pd.to_numeric(
            df_input["filter_total_problematic_offender_count"],
            errors="coerce",
        ).to_numpy(dtype=float)
        counts = np.clip(counts, 0.0, None)
        return counts, "filter_total_problematic_offender_count"

    component_columns = [
        column_name
        for column_name in (
            "filter_task1_problematic_channel_count",
            "filter_task2_problematic_strip_count",
            "filter_task3_problematic_plane_count",
        )
        if column_name in df_input.columns
    ]
    if not component_columns:
        return None, ""

    total_counts = np.zeros(len(df_input), dtype=float)
    finite_any = np.zeros(len(df_input), dtype=bool)
    for column_name in component_columns:
        raw_values = pd.to_numeric(df_input[column_name], errors="coerce").to_numpy(dtype=float)
        finite = np.isfinite(raw_values)
        finite_any |= finite
        safe_values = np.where(finite, raw_values, 0.0)
        total_counts += np.clip(safe_values, 0.0, None)

    total_counts[~finite_any] = np.nan
    source = " + ".join(component_columns)
    return total_counts, source



def _build_offender_zigzag_payload(
    df_input: pd.DataFrame,
    tt_labels: np.ndarray,
) -> dict[str, dict[str, np.ndarray]]:
    required = (
        "x",
        "y",
        "theta",
        "phi",
        "p1_tdif",
        "p2_tdif",
        "p3_tdif",
        "p4_tdif",
        "p1_ypos",
        "p2_ypos",
        "p3_ypos",
        "p4_ypos",
    )
    if not all(column_name in df_input.columns for column_name in required):
        return {}

    path_x_all = np.column_stack(
        [
            pd.to_numeric(df_input[f"p{plane}_tdif"], errors="coerce").to_numpy(dtype=float)
            for plane in range(1, 5)
        ]
    ) * float(tdiff_to_x)
    path_y_all = np.column_stack(
        [
            pd.to_numeric(df_input[f"p{plane}_ypos"], errors="coerce").to_numpy(dtype=float)
            for plane in range(1, 5)
        ]
    )
    x0_all = pd.to_numeric(df_input["x"], errors="coerce").to_numpy(dtype=float)
    y0_all = pd.to_numeric(df_input["y"], errors="coerce").to_numpy(dtype=float)
    theta_all = pd.to_numeric(df_input["theta"], errors="coerce").to_numpy(dtype=float)
    phi_all = pd.to_numeric(df_input["phi"], errors="coerce").to_numpy(dtype=float)
    tan_theta_all = np.tan(theta_all)
    xp_all = tan_theta_all * np.cos(phi_all)
    yp_all = tan_theta_all * np.sin(phi_all)
    z_all = np.asarray(z_positions, dtype=float)

    payload: dict[str, dict[str, np.ndarray]] = {}
    for tt_label in _resolve_offender_focus_tts(tt_labels):
        active_planes = [int(char) for char in str(tt_label) if char in "1234"]
        if len(active_planes) < 3:
            continue
        active_idx = np.asarray([plane - 1 for plane in active_planes], dtype=int)
        active_z = z_all[active_idx]
        z_order = np.argsort(active_z)
        active_idx = active_idx[z_order]
        active_z = active_z[z_order]

        path_x = path_x_all[:, active_idx]
        path_y = path_y_all[:, active_idx]
        path_dx = np.diff(path_x, axis=1)
        path_dy = np.diff(path_y, axis=1)
        path_dz = np.diff(active_z).astype(float)
        measured_path_all = np.sum(
            np.sqrt(path_dx ** 2 + path_dy ** 2 + path_dz[None, :] ** 2),
            axis=1,
        )

        z_first = float(active_z[0])
        z_last = float(active_z[-1])
        fit_x_first_all = x0_all + xp_all * z_first
        fit_y_first_all = y0_all + yp_all * z_first
        fit_x_last_all = x0_all + xp_all * z_last
        fit_y_last_all = y0_all + yp_all * z_last
        fit_length_all = np.sqrt(
            (fit_x_last_all - fit_x_first_all) ** 2
            + (fit_y_last_all - fit_y_first_all) ** 2
            + (z_last - z_first) ** 2
        )

        valid_mask = (
            (tt_labels == tt_label)
            & np.isfinite(path_x).all(axis=1)
            & np.isfinite(path_y).all(axis=1)
            & np.isfinite(x0_all)
            & np.isfinite(y0_all)
            & np.isfinite(theta_all)
            & np.isfinite(phi_all)
            & np.isfinite(xp_all)
            & np.isfinite(yp_all)
            & np.isfinite(measured_path_all)
            & np.isfinite(fit_length_all)
            & (measured_path_all > 0)
        )
        if int(np.count_nonzero(valid_mask)) < 5:
            continue

        theta_selected = theta_all[valid_mask]
        measured_path = measured_path_all[valid_mask]
        fit_length = fit_length_all[valid_mask]
        zigzag_ratio = fit_length / (measured_path + 1e-9)
        zigzag_excess = np.clip(measured_path - fit_length, 0.0, None)
        projected_excess = zigzag_excess * np.clip(np.cos(theta_selected), 1e-6, None)
        payload[tt_label] = {
            "row_mask": valid_mask,
            "theta_deg": np.degrees(theta_selected),
            "zigzag_ratio": zigzag_ratio,
            "projected_excess": projected_excess,
            "measured_path": measured_path,
            "fit_length": fit_length,
        }
    return payload


# Simulated-data truth comparison in slowness basis.
# Classic relative error: (s_cal - s_c) / s_c, with s_c = 1/c.
# Median excludes zero slowness entries (placeholders/non-fits).
def _store_slowness_relerr_to_sc(metadata_key: str, slowness_col: str) -> None:
    if not is_simulated_file or slowness_col not in working_df.columns:
        global_variables[metadata_key] = np.nan
        return

    slowness_arr = pd.to_numeric(working_df[slowness_col], errors="coerce").to_numpy(dtype=float)
    valid_slowness = slowness_arr[np.isfinite(slowness_arr) & (slowness_arr != 0.0)]
    if valid_slowness.size == 0:
        global_variables[metadata_key] = np.nan
        return

    relerr_arr = (valid_slowness - sc) / sc
    relerr_arr = relerr_arr[np.isfinite(relerr_arr)]
    global_variables[metadata_key] = float(np.median(relerr_arr)) if relerr_arr.size > 0 else np.nan


def round_array_to_significant_digits(values: np.ndarray, significant_digits: int = 4) -> np.ndarray:
    rounded = values.astype(float, copy=True)
    finite_nonzero = np.isfinite(rounded) & (rounded != 0)
    if np.any(finite_nonzero):
        magnitudes = np.floor(np.log10(np.abs(rounded[finite_nonzero]))).astype(int)
        scales = np.power(10.0, significant_digits - 1 - magnitudes)
        rounded[finite_nonzero] = np.round(rounded[finite_nonzero] * scales) / scales
    return rounded


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
TASK4_PLOT_ALIASES: tuple[str, ...] = (
    "debug_suite",
    "usual_suite",
    "essential_suite",
    "acquisition_rate_vs_time_by_task_tt_with_histograms",
    "flat_values_histogram",
    "detached_timeseries_combo",
    "detached_residuals_combo",
    "timtrack_timeseries_combo",
    "timtrack_residuals_combo",
    "combined_timeseries_combo",
    "combined_residuals_combo",
    "hist_core_errs_combined",
    "hist_core_errs_combined_with_fits",
    "stat_window_accumulation",
    "trigger_types_raw_and_list",
    "trigger_types_tracking_and_list",
    "trigger_types_tracking_and_raw",
    "trigger_types_definitive_tt_and_raw",
    "timtrack_results_hexbin_combination_projections",
    "timtrack_results_scatter_combination_projections",
    "theta_det_theta_zoom_tt_task4_fit",
    "polar_theta_phi_definitive_tt_2d",
    "polar_theta_phi_tt_task4_fit_2d",
    "events_per_second_by_plane_cardinality_double_row",
    "timtrack_residuals_gaussian",
    "tim_th_chi_sigmafit_1234_histogram",
    "external_residuals_gaussian",
    "all_channels_charge",
    "event_display_sample",
    "track_consistency_loo_residuals",
    "strip_hit_occupancy",
    "track_based_efficiency",
    "total_event_charge_histogram",
    "track_based_efficiency_tt_stability",
    "track_based_efficiency_vs_theta",
    "track_efficiency_large_plot",
    "timtrack_projection_ellipse_contours",
    "timtrack_projection_scaled_angle_comparison",
    "chi2_offender_populations",
    "offender_angle_populations",
    "offender_kinematics_populations",
    "offender_tt_balance",
    "offender_zigzag_populations",
    "chi2_charge_populations",
    "chi2_residuals_populations",
    "event_display_sample_3fold",
    "chi2_charge_populations_3fold",
    "chi2_residuals_populations_3fold",
)
task4_plot_status_by_alias: dict[str, str] = {}
_TRACK_EFF_REPRESENTATIVE_LINESTYLE = (0, (10, 3))
_TRACK_EFF_SIMULATION_LINESTYLE = (0, (3, 2))
TASK4_PLOT_PREFIX_ALIASES: tuple[tuple[str, str], ...] = (
    ("detached_timeseries_combo_", "detached_timeseries_combo"),
    ("detached_residuals_combo_", "detached_residuals_combo"),
    ("timtrack_timeseries_combo_", "timtrack_timeseries_combo"),
    ("timtrack_residuals_combo_", "timtrack_residuals_combo"),
    ("combined_timeseries_combo_", "combined_timeseries_combo"),
    ("combined_residuals_combo_", "combined_residuals_combo"),
    ("stat_window_accumulation_", "stat_window_accumulation"),
    ("timtrack_residuals_with_gaussian_for_processed_type_", "timtrack_residuals_gaussian"),
    ("external_residuals_with_gaussian_for_processed_type_", "external_residuals_gaussian"),
    ("all_channels_charge_mingo0", "all_channels_charge"),
)
CLI_PARSER = build_step1_cli_parser("Run Stage 1 STEP_1 TASK_4 (LIST->FIT).", STATION_CHOICES)
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
task4_plot_status_by_alias = load_step1_task_plot_catalog(
    plot_catalog_file_path,
    TASK4_PLOT_ALIASES,
    "Task 4",
    log_fn=print,
)
debug_mode = False

home_path = str(resolve_home_path_from_config(config))
REFERENCE_TABLES_DIR = get_repo_root() / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS" / "CONFIG_FILES" / "METADATA_REPRISE" / "REFERENCE_TABLES"
_offender_plot_settings = config.get("offender_plot_settings", {})
if not isinstance(_offender_plot_settings, dict):
    _offender_plot_settings = {}
OFFENDER_THETA_MIN_DEG = float(_offender_plot_settings.get("theta_min_deg", 0.0))
OFFENDER_THETA_MAX_DEG = float(_offender_plot_settings.get("theta_max_deg", 90.0))
if not np.isfinite(OFFENDER_THETA_MIN_DEG):
    OFFENDER_THETA_MIN_DEG = 0.0
if not np.isfinite(OFFENDER_THETA_MAX_DEG):
    OFFENDER_THETA_MAX_DEG = 90.0
if OFFENDER_THETA_MAX_DEG <= OFFENDER_THETA_MIN_DEG:
    OFFENDER_THETA_MIN_DEG = 0.0
    OFFENDER_THETA_MAX_DEG = 90.0
OFFENDER_FOCUS_TTS_CFG = _coerce_tt_label_tuple(
    _offender_plot_settings.get("focus_definitive_tt", None),
    default=("123", "124", "134", "234", "1234"),
)
OFFENDER_TASK1_CUMULATIVE_THRESHOLDS = _coerce_nonnegative_int_tuple(
    _offender_plot_settings.get("task1_cumulative_thresholds", None),
    default=tuple(range(0, 11)),
)
OFFENDER_TOTAL_CUMULATIVE_THRESHOLDS = _coerce_nonnegative_int_tuple(
    _offender_plot_settings.get(
        "total_cumulative_thresholds",
        _offender_plot_settings.get("task1_cumulative_thresholds", None),
    ),
    default=tuple(range(0, 11)),
)
if 0 not in OFFENDER_TOTAL_CUMULATIVE_THRESHOLDS:
    OFFENDER_TOTAL_CUMULATIVE_THRESHOLDS = tuple(
        sorted((0, *OFFENDER_TOTAL_CUMULATIVE_THRESHOLDS))
    )

_CURVE_FIT_WARNING_FILTERS: tuple[tuple[str, type[Warning]], ...] = (
    (r"Covariance of the parameters could not be estimated", OptimizeWarning),
    (r"overflow encountered in matmul", RuntimeWarning),
)
# Dedicated two-column plot for combined errors

#%%

# -----------------------------------------------------------------------------
# Stuff that could change between mingos --------------------------------------
# -----------------------------------------------------------------------------

if CLI_ARGS.station is None:
    CLI_PARSER.error("No station provided. Pass <station>.")
station = str(CLI_ARGS.station)
set_station(station)

use_filter_parameter_config = bool(config.get("use_filter_parameter_config", True))
config = resolve_step1_effective_task_config(
    config,
    station_id=station,
    task_number=task_number,
    config_root=config_root,
    parameter_config_file_path=parameter_config_file_path,
    fallback_parameter_config_file_path=fallback_parameter_config_file_path,
    plot_parameter_config_file_path=plot_parameter_config_file_path,
    filter_parameter_config_file_path=filter_parameter_config_file_path,
    use_filter_parameter_config=use_filter_parameter_config,
    warn_if_missing_filter=True,
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

# Cron job switch that decides if completed files can be revisited.
complete_reanalysis = config.get("complete_reanalysis", False)

selected_input_file = CLI_ARGS.input_file_flag or CLI_ARGS.input_file
if selected_input_file:
    user_file_path = selected_input_file
    user_file_selection = True
    print("User provided file path:", user_file_path)
else:
    user_file_selection = False

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
    early_status_filename_base = (
        Path(user_file_path).name.replace("listed_", "").replace(".parquet", "")
    )
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
    raw_directory = "STAGE_0_TO_1"
else:
    raw_directory = f"STEP_1/TASK_{task_number - 1}/OUTPUT_FILES"
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
raw_working_directory = os.path.join(base_directory, raw_directory)

# Example TASK_1 output directory under the current station.
raw_working_directory = os.path.join(base_directory, "STEP_1/TASK_3/OUTPUT_FILES")

raw_to_list_working_directory = os.path.join(base_directory, "STEP_1/TASK_4/")

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

EXPECTED_INPUT_PREFIX = "listed_"
EXPECTED_INPUT_EXTENSION = ".parquet"
# Accessing all the variables from the configuration
crontab_execution = config["crontab_execution"]
(
    plot_mode,
    create_plots,
    create_essential_plots,
    save_plots,
    create_pdf,
    show_plots,
    create_debug_plots,
) = resolve_step1_plot_options(config)
apply_task4_plot_catalog_modes()
save_rejected_rows = config.get("save_rejected_rows", False)
create_reject_plots = config.get("create_reject_plots", False)
if create_reject_plots:
    save_rejected_rows = True
print(
    f"Info: reject-plots config -> create_reject_plots={create_reject_plots} "
    f"save_rejected_rows={save_rejected_rows} save_plots={save_plots}"
)
reject_plot_hist_bins = int(config.get("reject_plot_hist_bins", 60))
reject_plot_hist_cols_per_fig = int(config.get("reject_plot_hist_cols_per_fig", 16))
reject_plot_scatter_max_points = int(config.get("reject_plot_scatter_max_points", 200000))

if (create_essential_plots or create_plots) and task4_plot_enabled("flat_values_histogram"):
    # When Task 4 plotting is enabled, force full plotting outputs for this task.
    create_essential_plots = True
    save_plots = True
    create_pdf = False  # Runtime plots are strictly PNG-only.

for directory in base_directories.values():
    # Skip figure directories at startup; create lazily after selecting a file.
    if directory in (base_directories["base_figure_directory"], base_directories["figure_directory"]):
        print("\n\nSKIPPING THE FIGURE DICTIONARY CREATION\n\n")
        continue
    print(f"Created {directory}")
    os.makedirs(directory, exist_ok=True)

debug_plot_directory = os.path.join(
    base_directories["base_plots_directory"],
    "DEBUG_PLOTS",
    f"FIGURES_EXEC_ON_{date_execution}",
)
debug_fig_idx = 1

csv_path = os.path.join(metadata_directory, f"task_{task_number}_metadata_execution.csv")
csv_path_specific = os.path.join(metadata_directory, f"task_{task_number}_metadata_specific.csv")
csv_path_rate_histogram = os.path.join(
    metadata_directory,
    f"task_{task_number}_metadata_rate_histogram.csv",
)
csv_path_chi2_four_plane = os.path.join(
    metadata_directory,
    f"task_{task_number}_metadata_chi2_four_plane.csv",
)
csv_path_efficiency = os.path.join(
    metadata_directory,
    f"task_{task_number}_metadata_efficiency.csv",
)
csv_path_robust_efficiency = os.path.join(
    metadata_directory,
    f"task_{task_number}_metadata_robust_efficiency.csv",
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

raw_files = set(_expected_input_files(os.listdir(raw_directory)))
unprocessed_files = set(_expected_input_files(os.listdir(unprocessed_directory)))
processing_files = set(_expected_input_files(os.listdir(processing_directory)))
completed_files = set(_expected_input_files(os.listdir(completed_directory)))

last_file_test = bool(config.get("last_file_test", False))
keep_all_columns_output = _coerce_config_bool(
    config.get("keep_all_columns_output", False),
    default=False,
)

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
        "basename_no_ext": file_name.replace("listed_", "").replace(".parquet", ""),
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
                "basename_no_ext": joined_file_name.replace("listed_", "").replace(".parquet", ""),
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
basename_no_ext = the_filename.replace("listed_", "").replace(".parquet", "")

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

global_variables = {}
if simulated_param_hash:
    global_variables["param_hash"] = simulated_param_hash

TT_COUNT_VALUES: tuple[int, ...] = (
    0, 1, 2, 3, 4, 12, 13, 14, 23, 24, 34, 123, 124, 134, 234, 1234
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
        param_hash=str(global_variables.get("param_hash", "")),
    )

left_limit_time = pd.to_datetime("1-1-2000", format='%d-%m-%Y')
right_limit_time = pd.to_datetime("1-1-2100", format='%d-%m-%Y')

# if limit:
#     print(f'Taking the first {limit_number} rows.')

# Read the data file into a DataFrame
KEY = "df"

# Load dataframe(s)
joined_source_file_column = "__task4_joined_source_file__"
joined_source_basename_column = "__task4_joined_source_basename__"
joined_frames: list[pd.DataFrame] = []
for joined_record in joined_input_records:
    joined_path = joined_record["processing_file_path"]
    joined_frame = pd.read_parquet(joined_path, engine="pyarrow")
    joined_frame = joined_frame.rename(columns=lambda col: col.replace("_diff_", "_dif_"))
    joined_frame = canonicalize_step1_columns(joined_frame)
    if "event_id" not in joined_frame.columns:
        print(
            "Warning: 'event_id' missing in Task 4 input; reconstructing from "
            f"current row order for {joined_record['file_name']}."
        )
        joined_frame.insert(0, "event_id", np.arange(len(joined_frame), dtype=np.int64))
    joined_frame.loc[:, joined_source_file_column] = joined_record["file_name"]
    joined_frame.loc[:, joined_source_basename_column] = joined_record["basename_no_ext"]
    joined_frames.append(joined_frame)
    print(f"Listed dataframe reloaded from: {joined_path} rows={len(joined_frame)}")
if not joined_frames:
    sys.exit("No Task 4 input dataframes were loaded.")
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
print(f"Listed dataframe reloaded from: {file_path}")
# print("Columns loaded from parquet:")
# for col in working_df.columns:
#     print(f" - {col}")
# Backward compatibility: if old original_tt exists but tt_task0_raw is missing, reuse it.
if "tt_task0_raw" not in working_df.columns and "original_tt" in working_df.columns:
    working_df = working_df.rename(columns={"original_tt": "tt_task0_raw"})
# Backward compatibility: if tt_task1_clean is missing but prett_task3_list exists, reuse it.
if "tt_task1_clean" not in working_df.columns and "prett_task3_list" in working_df.columns:
    working_df = working_df.rename(columns={"prett_task3_list": "tt_task1_clean"})

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
    main_cols.extend(["tt_task0_raw", "tt_task1_clean", "tt_task2_cal", "tt_task3_list"])
    main_cols = [col for col in main_cols if col in working_df.columns]
    if main_cols:
        debug_fig_idx = plot_debug_histograms(
            working_df,
            main_cols,
            thresholds=None,
            title=f"Task 4 incoming parquet: main columns [NON-TUNABLE] (station {station})",
            out_dir=debug_plot_directory,
            fig_idx=debug_fig_idx,
            max_cols_per_fig=20,
        )

# the analysis mode indicates if it is a regular analysis or a repeated, careful analysis
# 0 -> regular analysis
# 1 -> repeated, careful analysis

# Keep tt_task3_list from Task 3 when present; compute only if missing.
if "tt_task3_list" not in working_df.columns:
    working_df = compute_tt(working_df, "tt_task3_list", TASK4_EXTENSION_TT_COLUMNS)
else:
    working_df.loc[:, "tt_task3_list"] = (
        pd.to_numeric(working_df["tt_task3_list"], errors="coerce")
        .fillna(0)
        .astype(int)
    )
tt_task3_list_counts_initial = working_df["tt_task3_list"].value_counts()
for tt_value, count in tt_task3_list_counts_initial.items():
    tt_label = normalize_tt_label(tt_value)
    global_variables[f"tt_task3_list_{tt_label}_count"] = int(count)
working_df["tt_task3_list"] = working_df["tt_task3_list"].astype(int)

# Ensure tt_task2_cal is present for downstream correlations
if "tt_task2_cal" not in working_df.columns:
    working_df["tt_task2_cal"] = working_df["tt_task3_list"]

# List all names of columns

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
globals().update(
    initialize_task4_runtime_context(
        config,
        global_variables,
        globals(),
        announce_fit_method=True,
        announce_geometry=True,
    )
)
task4_xpos_summary = ensure_plane_xpos_columns(working_df, tdiff_to_x, overwrite=True)
if task4_xpos_summary["source_columns_found"] != 4:
    raise RuntimeError(
        "Task 4 input is missing one or more p#_tdif columns required for plane X: "
        f"{task4_xpos_summary}"
    )
print(f"Task 4 plane X persistence check: {task4_xpos_summary}")

TRACK_COMBINATIONS: tuple[str, ...] = (
    "12", "13", "14", "23", "24", "34",
    "123", "124", "134", "234", "1234",
)

RESIDUAL_SERIES: tuple[str, ...] = (
    "res_ystr",
    "res_tsum",
    "res_tdif",
    "ext_res_ystr",
    "ext_res_tsum",
    "ext_res_tdif",
)

FILTER_METRIC_NAMES: tuple[str, ...] = (
    "small_values_zeroed_event_pct",
    "small_values_zeroed_value_pct",
    "definitive_small_values_zeroed_event_pct",
    "definitive_small_values_zeroed_value_pct",
    "low_tt_zeroed_event_pct",
    "definitive_rows_removed_pct",
    "definitive_removed_single_zero_rows_pct",
    "definitive_removed_multi_zero_rows_pct",
    "definitive_removed_primary_x_zero_rows_pct",
    "definitive_removed_primary_y_zero_rows_pct",
    "definitive_removed_primary_s_zero_rows_pct",
    "definitive_removed_primary_t0_zero_rows_pct",
    "definitive_removed_primary_theta_zero_rows_pct",
    "definitive_removed_primary_phi_zero_rows_pct",
    "definitive_x_zero_rows_pct",
    "definitive_y_zero_rows_pct",
    "definitive_s_zero_rows_pct",
    "definitive_t0_zero_rows_pct",
    "definitive_theta_zero_rows_pct",
    "definitive_phi_zero_rows_pct",
    "final_filter_rows_removed_pct",
    "data_purity_percentage",
    "all_components_zero_rows_removed_pct",
    "tt_task4_fit_lt_10_rows_removed_pct",
)

reprocessing_parameters = pd.DataFrame()
filter_metrics: dict[str, float] = {}
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

self_trigger = bool(config.get("self_trigger", False))

globals().update(
    initialize_task4_runtime_context(
        config,
        global_variables,
        globals(),
    )
)

# Note that the middle between start and end time could also be taken. This is for calibration storage.
datetime_value = working_df['datetime'].iloc[0]
end_datetime_value = working_df['datetime'].iloc[-1]

if self_trigger:
    print(self_trigger_df)
    datetime_value_st = self_trigger_df['datetime'].iloc[0]
    end_datetime_value_st = self_trigger_df['datetime'].iloc[-1]
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
save_pdf_filename = f"mingo{str(station).zfill(2)}_task4_{basename_no_ext}_{date_execution}.pdf"

save_pdf_path = os.path.join(base_directories["pdf_directory"], save_pdf_filename)

# -------------------------------------------------------------------------------
# ------------ Input file and data managing to select configuration -------------
# -------------------------------------------------------------------------------

is_simulated_file = basename_no_ext.startswith("mi00")
used_input_file = False
z_source = "unset"
z_positions_from_task3 = None
z_columns = [f"z_P{i}" for i in range(1, 5)]
if all(col in working_df.columns for col in z_columns):
    z_frame = working_df[z_columns].apply(pd.to_numeric, errors="coerce")
    valid_z_rows = z_frame.dropna(how="any")
    if not valid_z_rows.empty:
        z_positions_from_task3 = valid_z_rows.iloc[0].to_numpy(dtype=float)
        if (valid_z_rows.nunique(dropna=True) > 1).any():
            print("Warning: Inconsistent z_P* values in TASK_3 parquet; using first valid row.")
    else:
        print("Warning: TASK_3 parquet has z_P* columns but no fully valid row.")

if z_positions_from_task3 is not None and not np.all(z_positions_from_task3 == 0):
    z_positions = z_positions_from_task3
    found_matching_conf = True
    z_source = "task3_parquet_z_columns"
    print("Using z_positions from TASK_3 parquet columns (z_p1..z_p4).")
elif simulated_z_positions is not None:
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

# Save the z_positions in the metadata file
global_variables['z_p1'] =  z_positions[0]
global_variables['z_p2'] =  z_positions[1]
global_variables['z_p3'] =  z_positions[2]
global_variables['z_p4'] =  z_positions[3]

globals().update(
    initialize_task4_runtime_context(
        config,
        global_variables,
        globals(),
    )
)

raw_data_len = len(working_df)
if raw_data_len == 0 and not self_trigger:
    print("No coincidence nor self-trigger events.")
    sys.exit(1)

#%%

_prof["s_data_read_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()
print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")
print("-------------- Detached angle and slowness fitting ----------------")
print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")
n = len(working_df)

# Angular definitions
fit_cols = (
    ['det_x', 'det_y', 'det_theta', 'det_phi', 'det_chi2_pos'] +
    [f'det_res_tdif_{p}' for p in range(1, 5)] +
    [f'det_res_ystr_{p}' for p in range(1, 5)]
)

# Slowness definitions
slow_cols = ['det_s', 'det_s_ordinate' , 'det_chi2_tsum'] + [f'det_res_tsum_{p}' for p in range(1, 5)]

# Pre-extract per-plane columns as contiguous numpy arrays (avoids per-event
# getattr overhead in the detached fitting loop below).
_det_Q    = np.column_stack([working_df[f'p{p}_qsum'].to_numpy(dtype=float) for p in range(1, nplan + 1)])
_det_Tdif = np.column_stack([working_df[f'p{p}_tdif'].to_numpy(dtype=float) for p in range(1, nplan + 1)])
_det_Y    = np.column_stack([working_df[f'p{p}_ypos'].to_numpy(dtype=float)     for p in range(1, nplan + 1)])
_det_Tsum = np.column_stack([working_df[f'p{p}_tsum'].to_numpy(dtype=float) for p in range(1, nplan + 1)])

# Alternative analysis starts -----------------------------------------------
if run_detached_fit:
    repeat = number_of_det_executions - 1
    for det_iteration in range(repeat + 1):
        fitted = 0
        if number_of_det_executions > 1:
            print(f"Alternative iteration {det_iteration+1} out of {number_of_det_executions}.")

        fit_res = {c: np.full(n, np.nan, dtype=float) for c in fit_cols}
        slow_res  = {c: np.full(n, np.nan, dtype=float) for c in slow_cols}
        det_ext_res_ystr_arr = np.full((n, 4), np.nan, dtype=float)
        det_ext_res_tsum_arr = np.full((n, 4), np.nan, dtype=float)
        det_ext_res_tdif_arr = np.full((n, 4), np.nan, dtype=float)
        det_tt_task3_list_arr = working_df.get("tt_task3_list", pd.Series([0]*n)).astype(int).to_numpy()

        _detached_vectorized(
            _det_Q, _det_Tdif, _det_Y, _det_Tsum,
            z_positions, tdiff_to_x,
            anc_sx, anc_sy, anc_sz, anc_sts,
            n, nplan,
            fit_res, slow_res,
            det_ext_res_ystr_arr, det_ext_res_tsum_arr, det_ext_res_tdif_arr,
        )

        # 4.  Assemble all results and join once
        all_res = {**fit_res, **slow_res}
        all_res['det_ext_res_ystr_1'] = det_ext_res_ystr_arr[:, 0]
        all_res['det_ext_res_ystr_2'] = det_ext_res_ystr_arr[:, 1]
        all_res['det_ext_res_ystr_3'] = det_ext_res_ystr_arr[:, 2]
        all_res['det_ext_res_ystr_4'] = det_ext_res_ystr_arr[:, 3]
        all_res['det_ext_res_tsum_1'] = det_ext_res_tsum_arr[:, 0]
        all_res['det_ext_res_tsum_2'] = det_ext_res_tsum_arr[:, 1]
        all_res['det_ext_res_tsum_3'] = det_ext_res_tsum_arr[:, 2]
        all_res['det_ext_res_tsum_4'] = det_ext_res_tsum_arr[:, 3]
        all_res['det_ext_res_tdif_1'] = det_ext_res_tdif_arr[:, 0]
        all_res['det_ext_res_tdif_2'] = det_ext_res_tdif_arr[:, 1]
        all_res['det_ext_res_tdif_3'] = det_ext_res_tdif_arr[:, 2]
        all_res['det_ext_res_tdif_4'] = det_ext_res_tdif_arr[:, 3]
        all_res['det_th_chi'] = all_res['det_chi2_pos'] + all_res['det_chi2_tsum']
        all_res['det_tt_task3_list'] = det_tt_task3_list_arr

        new_cols = pd.DataFrame(all_res, index=working_df.index)
        dupes = new_cols.columns.intersection(working_df.columns)
        working_df = working_df.drop(columns=dupes, errors='ignore')
        working_df = working_df.join(new_cols)
        working_df = working_df.copy()
else:
    print("Skipping detached fitting (fit_method excludes detached).")

# ---------------------------------------------------------------------------
# Put every value close to 0 to effectively 0 -------------------------------
# ---------------------------------------------------------------------------

# Filter controls used by final filtering block -----------------------------
print("Info: Task 4 consolidated final filtering uses event_combination_detector_* bounds.")
eps = TASK4_FINAL_FILTER_REMOVE_SMALL_EPS

if create_plots:

    # Flatten all numeric values except 0
    flat_values = working_df.select_dtypes(include=[np.number]).values.ravel()
    flat_values = flat_values[flat_values != 0]

    cond = abs(flat_values) < eps
    flat_values = flat_values[cond]

    # Plot histogram
    plt.figure(figsize=(8, 6))
    plt.hist(flat_values, bins=300, alpha=0.7)
    plt.xlabel('Value')
    plt.ylabel('Counts')
    plt.title('Histogram of All Nonzero Values in working_df')
    plt.yscale('log')  # Optional: log scale to reveal structure
    plt.grid(True)
    plt.tight_layout()
    if save_plots:
        name_of_file = 'flat_values_histogram'
        final_filename = f'{fig_idx}_{name_of_file}.png'
        fig_idx += 1
        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format='png', alias="flat_values_histogram")
    if show_plots:
        plt.show()
    plt.close()
# Deprecated legacy path intentionally does nothing now; all Task 4 row/value
# filtering is centralized in apply_task4_final_filter().

print("Alternative fitting done.")

#%%

# Build detached (independent) variables
working_df["det_x"] = working_df.get("det_x", np.nan)
working_df["det_y"] = working_df.get("det_y", np.nan)
working_df["det_theta"] = working_df.get("det_theta", np.nan)
working_df["det_phi"] = working_df.get("det_phi", np.nan)
working_df["det_s"] = working_df.get("det_s", np.nan)
working_df["det_t0"] = working_df.get("det_s_ordinate", np.nan)

for p in range(1, 5):
    working_df[f"det_res_ystr_{p}"] = working_df.get(f"det_res_ystr_{p}", np.nan)
    working_df[f"det_res_tsum_{p}"] = working_df.get(f"det_res_tsum_{p}", np.nan)
    working_df[f"det_res_tdif_{p}"] = working_df.get(f"det_res_tdif_{p}", np.nan)
    working_df[f"det_ext_res_ystr_{p}"] = working_df.get(f"det_ext_res_ystr_{p}", np.nan)
    working_df[f"det_ext_res_tsum_{p}"] = working_df.get(f"det_ext_res_tsum_{p}", np.nan)
    working_df[f"det_ext_res_tdif_{p}"] = working_df.get(f"det_ext_res_tdif_{p}", np.nan)

#%%

if create_plots:
    # Detached method plots (per combination)
    if "det_tt_task3_list" in working_df.columns and "datetime" in working_df.columns:
        for combo in TRACK_COMBINATIONS:
            try:
                combo_int = int(combo)
            except ValueError:
                continue
            subset = working_df[working_df["det_tt_task3_list"] == combo_int]
            if subset.empty:
                continue
            plot_ts_with_side_hist(
                subset,
                ["det_x", "det_y", "det_theta", "det_phi", "det_s", "det_t0"],
                "datetime",
                f"detached_timeseries_combo_{combo}",
            )
            # Only plot residuals when we have 3+ planes
            if len(str(combo_int)) >= 3:
                plot_residuals_ts_hist(
                    subset,
                    prefixes=[
                        ("ystr", "det_res_ystr_", "det_ext_res_ystr_"),
                        ("tsum", "det_res_tsum_", "det_ext_res_tsum_"),
                        ("tdif", "det_res_tdif_", "det_ext_res_tdif_"),
                    ],
                    time_col="datetime",
                    title=f"detached_residuals_combo_{combo}",
                )

#%%

_prof["s_detached_fitting_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()
print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")
print("------------------------- TimTrack fitting ---------------------------")
print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")

if fixed_speed:
    print("Fixed the slowness to 1 / speed of light.")
    npar = 5
else:
    print("Slowness not fixed.")
    npar = 6
nvar = 3
i = 0
ntrk  = len(working_df)
if limit and limit_number < ntrk: ntrk = limit_number
print("-----------------------------")
print(f"{ntrk} events to be fitted")

timtrack_results = [
    'tim_x', 'tim_xp', 'tim_y', 'tim_yp', 'tim_t0', 'tim_s',
    'tim_th_chi', 'tim_res_y', 'tim_res_ts', 'tim_res_td', 'tim_tt_task3_list',
    'tim_res_ystr_1', 'tim_res_ystr_2', 'tim_res_ystr_3', 'tim_res_ystr_4',
    'tim_res_tsum_1', 'tim_res_tsum_2', 'tim_res_tsum_3', 'tim_res_tsum_4',
    'tim_res_tdif_1', 'tim_res_tdif_2', 'tim_res_tdif_3', 'tim_res_tdif_4',
    'tim_ext_res_ystr_1', 'tim_ext_res_ystr_2', 'tim_ext_res_ystr_3', 'tim_ext_res_ystr_4',
    'tim_ext_res_tsum_1', 'tim_ext_res_tsum_2', 'tim_ext_res_tsum_3', 'tim_ext_res_tsum_4',
    'tim_ext_res_tdif_1', 'tim_ext_res_tdif_2', 'tim_ext_res_tdif_3', 'tim_ext_res_tdif_4',
    'tim_p1_qsum', 'tim_p2_qsum', 'tim_p3_qsum', 'tim_p4_qsum', 'tim_event_charge',
    "tim_timtrack_iterations", "tim_timtrack_conv_distance", 'tim_timtrack_converged'
]

missing_tim_cols = {col: 0.0 for col in timtrack_results if col not in working_df.columns}
if missing_tim_cols:
    working_df = pd.concat([working_df, pd.DataFrame(missing_tim_cols, index=working_df.index)], axis=1)

# Pre-extract per-plane columns for TimTrack (avoids per-event getattr overhead).
# _tt_vsig is constant for every plane/event so it is allocated once here.
_tt_Q    = np.column_stack([working_df[f'p{p}_qsum'].to_numpy(dtype=float) for p in range(1, nplan + 1)])
_tt_Tsum = np.column_stack([working_df[f'p{p}_tsum'].to_numpy(dtype=float) for p in range(1, nplan + 1)])
_tt_Tdif = np.column_stack([working_df[f'p{p}_tdif'].to_numpy(dtype=float) for p in range(1, nplan + 1)])
_tt_Y    = np.column_stack([working_df[f'p{p}_ypos'].to_numpy(dtype=float)     for p in range(1, nplan + 1)])
_tt_vsig = [anc_sy, anc_sts, anc_std]
# Pre-computed weight array for _fmk_and_va (constant for all events/planes/timtrack_iterations)
_w_arr  = np.array([1.0 / anc_sy**2, 1.0 / anc_sts**2, 1.0 / anc_std**2], dtype=float)
_sc_val = sc
_z_pos_arr = np.asarray(z_positions, dtype=float)
_half_lenx_ss = 0.5 * lenx * ss

tt_loo_every_n = _cfg_int_or_default(config, "tt_loo_every_n", 1, min_value=1)
tt_loo_iter_max = _cfg_int_or_default(config, "tt_loo_iter_max", int(iter_max), min_value=1)
tt_loo_cocut = _cfg_float_or_default(config, "tt_loo_cocut", float(cocut), min_value=0.0)
_tt_loo_mode_raw = str(config.get("tt_loo_mode", "single_step")).strip().lower()
if _tt_loo_mode_raw not in ("single_step", "iterative"):
    print(f"WARNING: unrecognised tt_loo_mode='{_tt_loo_mode_raw}', falling back to 'single_step'")
    _tt_loo_mode_raw = "single_step"
tt_loo_mode = _tt_loo_mode_raw
print(
    "TimTrack LOO settings: "
    f"every_n={tt_loo_every_n}, "
    f"iter_max={tt_loo_iter_max}, "
    f"cocut={tt_loo_cocut:g}, "
    f"mode={tt_loo_mode}"
)

_tt_seed_enabled = False
_tt_seed_slope_abs_max = float(config.get("tt_seed_slope_abs_max", 5.0))
if run_detached_fit and all(
    col in working_df.columns
    for col in ("det_x", "det_y", "det_theta", "det_phi", "det_t0", "det_s")
):
    _seed_x = working_df["det_x"].to_numpy(dtype=float)
    _seed_y = working_df["det_y"].to_numpy(dtype=float)
    _seed_theta = working_df["det_theta"].to_numpy(dtype=float)
    _seed_phi = working_df["det_phi"].to_numpy(dtype=float)
    _seed_t0 = working_df["det_t0"].to_numpy(dtype=float)
    _seed_s = working_df["det_s"].to_numpy(dtype=float)
    _tt_seed_enabled = True
    print("TimTrack warm-start enabled from detached fit columns.")
else:
    print("TimTrack warm-start disabled (detached seed columns unavailable).")

# TimTrack thin profiling breakdown (accumulated across all TT timtrack_iterations)
_tt_intro_s = 0.0
_tt_main_fit_s = 0.0
_tt_residual_s = 0.0
_tt_residual_loo_s = 0.0
_tt_writeback_s = 0.0

# TimTrack thin profiling counters (for deeper bottleneck diagnosis)
_tt_events_total = 0
_tt_events_with_2plus_planes = 0
_tt_events_loo_eligible = 0
_tt_events_loo_processed = 0
_tt_mainfit_timtrack_iterations_total = 0
_tt_loo_refits_total = 0
_tt_loo_timtrack_iterations_total = 0

# TimTrack starts ------------------------------------------------------
if not run_timtrack_fit:
    print("Skipping TimTrack fitting (fit_method excludes timtrack).")
repeat = number_of_tt_executions - 1 if run_timtrack_fit else -1
for iteration in range(repeat + 1):
    fitted = 0
    if number_of_tt_executions > 1:
        print(f"TimTrack iteration {iteration+1} out of {number_of_tt_executions}")

    n_rows = len(working_df)
    charge_arr = np.zeros((n_rows, 4), dtype=float)
    res_ystr_arr = np.full((n_rows, 4), np.nan, dtype=float)
    res_tsum_arr = np.full((n_rows, 4), np.nan, dtype=float)
    res_tdif_arr = np.full((n_rows, 4), np.nan, dtype=float)
    ext_res_ystr_arr = np.full((n_rows, 4), np.nan, dtype=float)
    ext_res_tsum_arr = np.full((n_rows, 4), np.nan, dtype=float)
    ext_res_tdif_arr = np.full((n_rows, 4), np.nan, dtype=float)

    event_charge_arr = np.zeros(n_rows, dtype=float)
    timtrack_iterations_arr = np.zeros(n_rows, dtype=np.int32)
    timtrack_conv_distance_arr = np.full(n_rows, np.nan, dtype=float)
    timtrack_converged_arr = np.zeros(n_rows, dtype=np.int8)
    if "tt_task3_list" in working_df.columns:
        tt_task3_list_arr = pd.to_numeric(
            working_df["tt_task3_list"],
            errors="coerce",
        ).fillna(0).to_numpy(dtype=np.int32)
    else:
        tt_task3_list_arr = np.zeros(n_rows, dtype=np.int32)

    th_chi_arr = np.full(n_rows, np.nan, dtype=float)
    x_arr = np.full(n_rows, np.nan, dtype=float)
    xp_arr = np.full(n_rows, np.nan, dtype=float)
    y_arr = np.full(n_rows, np.nan, dtype=float)
    yp_arr = np.full(n_rows, np.nan, dtype=float)
    t0_arr = np.full(n_rows, np.nan, dtype=float)
    s_arr = np.full(n_rows, np.nan, dtype=float)

    th_chi_ndf_arrays = {}

    iterator = range(n_rows)
    if not crontab_execution:
        iterator = tqdm(iterator, total=n_rows, desc="Processing events")

    _acc_fn = _accumulate_mk_va
    _build_base_fn = _build_mk_va_base
    _acc_g1_fn = _accumulate_mk_va_dynamic_g1
    _solve_fn = solve_and_covdiag
    _solve_only_fn = solve_only
    _fmahd_fn = fmahd
    _loo_build_single_fn = _build_loo_single_step_system
    _w1 = float(_w_arr[1])
    _iter_max_f = float(iter_max)
    _cocut_f = float(cocut)
    _tt_loo_iter_max_f = float(tt_loo_iter_max)
    _tt_loo_cocut_f = float(tt_loo_cocut)
    _tt_loo_mode_is_single_step = (tt_loo_mode == "single_step")

    _mk_buf = np.zeros([npar, npar])
    _va_buf = np.zeros(npar)
    _mk_base_buf = np.zeros([npar, npar])
    _va_base_buf = np.zeros(npar)
    _mk_loo_buf = np.zeros([npar, npar])
    _va_loo_buf = np.zeros(npar)

    for pos in iterator:
        _tt_events_total += 1
        _tt_t = time.perf_counter()

        # INTRODUCTION ------------------------------------------------------------------
        _q_row  = _tt_Q[pos]
        _ts_row = _tt_Tsum[pos]
        _td_row = _tt_Tdif[pos]
        _y_row  = _tt_Y[pos]
        _valid_plane_mask = (
            (_q_row > 0.0)
            & np.isfinite(_q_row)
            & np.isfinite(_ts_row)
            & np.isfinite(_td_row)
            & np.isfinite(_y_row)
        )
        plane_idx_arr = np.flatnonzero(_valid_plane_mask)
        if plane_idx_arr.size > 0:
            event_charge = float(np.sum(_q_row[plane_idx_arr], dtype=float))
            plane_idx_4 = plane_idx_arr[plane_idx_arr < 4]
            if plane_idx_4.size > 0:
                charge_arr[pos, plane_idx_4] = _q_row[plane_idx_4]
        else:
            event_charge = 0.0
        _tt_intro_s += time.perf_counter() - _tt_t
        event_charge_arr[pos] = event_charge

        # FITTING -----------------------------------------------------------------------
        if plane_idx_arr.size <= 1:
            x_arr[pos] = np.nan
            xp_arr[pos] = np.nan
            y_arr[pos] = np.nan
            yp_arr[pos] = np.nan
            t0_arr[pos] = np.nan
            s_arr[pos] = np.nan
            timtrack_conv_distance_arr[pos] = np.nan
            th_chi_arr[pos] = np.nan
            continue
        _tt_events_with_2plus_planes += 1
        _tt_t = time.perf_counter()

        if fixed_speed:
            vs = np.zeros(5, dtype=float)
        else:
            vs = np.zeros(6, dtype=float)
            vs[5] = sc

        if _tt_seed_enabled:
            sx = _seed_x[pos]
            sy = _seed_y[pos]
            stheta = _seed_theta[pos]
            sphi = _seed_phi[pos]
            st0 = _seed_t0[pos]
            if np.isfinite(sx) and np.isfinite(sy) and np.isfinite(stheta) and np.isfinite(sphi) and np.isfinite(st0):
                tan_theta = math.tan(stheta)
                xp_seed = tan_theta * math.cos(sphi)
                yp_seed = tan_theta * math.sin(sphi)
                if (
                    np.isfinite(xp_seed)
                    and np.isfinite(yp_seed)
                    and abs(xp_seed) <= _tt_seed_slope_abs_max
                    and abs(yp_seed) <= _tt_seed_slope_abs_max
                ):
                    vs[0] = sx
                    vs[1] = xp_seed
                    vs[2] = sy
                    vs[3] = yp_seed
                    vs[4] = st0
                    if not fixed_speed:
                        ss_seed = _seed_s[pos]
                        if np.isfinite(ss_seed) and ss_seed > 0:
                            vs[5] = ss_seed

        mk = _mk_buf
        va = _va_buf
        mk_base = _mk_base_buf
        va_base = _va_base_buf
        _build_base_fn(
            plane_idx_arr,
            _y_row,
            _td_row,
            _z_pos_arr,
            _w_arr,
            ss,
            mk_base,
            va_base,
        )
        istp = 0
        dist = d0
        while dist > _cocut_f and istp < _iter_max_f:
            mk[:, :] = mk_base
            va[:] = va_base
            _acc_g1_fn(
                vs,
                plane_idx_arr,
                _ts_row,
                _z_pos_arr,
                _w1,
                _half_lenx_ss,
                _sc_val,
                fixed_speed,
                mk,
                va,
            )
            istp += 1
            vs0 = vs
            vs, merr_diag = _solve_fn(mk, va)
            dist = _fmahd_fn(npar, vs, vs0, merr_diag)
        _tt_mainfit_timtrack_iterations_total += int(istp)
        _tt_main_fit_s += time.perf_counter() - _tt_t

        if istp >= _iter_max_f or dist >= _cocut_f:
            timtrack_converged_arr[pos] = 1
        timtrack_iterations_arr[pos] = istp
        timtrack_conv_distance_arr[pos] = dist
        if not np.isfinite(dist):
            timtrack_converged_arr[pos] = 1
            continue

        vsf = vs
        fitted += 1

        # RESIDUAL ANALYSIS -------------------------------------------------------------
        res_ystr = res_tsum = res_tdif = 0.0
        chi2_y = chi2_tsum = chi2_tdif = 0.0
        ndat = 0
        _tt_t = time.perf_counter()
        X0 = vsf[0]
        XP = vsf[1]
        Y0 = vsf[2]
        YP = vsf[3]
        T0 = vsf[4]
        S0 = _sc_val if fixed_speed else vsf[5]
        kz = math.sqrt(1.0 + XP * XP + YP * YP)
        ts_base = T0 + _half_lenx_ss
        for plane_idx in plane_idx_arr:
            ndat += nvar
            zi = _z_pos_arr[plane_idx]
            xfit = X0 + XP * zi
            yr = (Y0 + YP * zi) - _y_row[plane_idx]
            tsr = (ts_base + S0 * kz * zi) - _ts_row[plane_idx]
            tdr = (ss * xfit) - _td_row[plane_idx]

            res_ystr += yr
            res_tsum += tsr
            res_tdif += tdr
            chi2_y += (yr / anc_sy) ** 2
            chi2_tsum += (tsr / anc_sts) ** 2
            chi2_tdif += (tdr / anc_std) ** 2

            if plane_idx < 4:
                res_ystr_arr[pos, plane_idx] = yr
                res_tsum_arr[pos, plane_idx] = tsr
                res_tdif_arr[pos, plane_idx] = tdr

        ndf = ndat - npar
        chi2 = chi2_y + chi2_tsum + chi2_tdif
        th_chi_arr[pos] = chi2
        th_chi_ndf_arrays.setdefault(ndf, np.full(n_rows, np.nan, dtype=float))[pos] = chi2

        x_arr[pos] = vsf[0]
        xp_arr[pos] = vsf[1]
        y_arr[pos] = vsf[2]
        yp_arr[pos] = vsf[3]
        t0_arr[pos] = vsf[4]
        if fixed_speed:
            s_arr[pos] = sc
        else:
            s_arr[pos] = vsf[5]
        _tt_residual_s += time.perf_counter() - _tt_t

        # ---------------------------------------------------------------------------------------------
        # Residual analysis with 4-plane tracks (hide a plane and fit the 3 remaining planes)
        # ---------------------------------------------------------------------------------------------
        if plane_idx_arr.size >= 3 and res_ana_removing_planes:
            _tt_events_loo_eligible += 1
            if (pos % tt_loo_every_n) == 0:
                _tt_events_loo_processed += 1
                _tt_t = time.perf_counter()
                mk_loo = _mk_loo_buf
                va_loo = _va_loo_buf

                if _tt_loo_mode_is_single_step:
                    # --- Single-step LOO: one Newton-Raphson step from vsf ---
                    for plane_idx_ref in plane_idx_arr:
                        _loo_build_single_fn(
                            vsf,
                            plane_idx_arr,
                            plane_idx_ref,
                            _y_row,
                            _ts_row,
                            _td_row,
                            _z_pos_arr,
                            _w_arr,
                            ss,
                            _half_lenx_ss,
                            _sc_val,
                            fixed_speed,
                            mk_loo,
                            va_loo,
                        )
                        vs_loo = _solve_only_fn(mk_loo, va_loo)
                        _tt_loo_refits_total += 1
                        _tt_loo_timtrack_iterations_total += 1
                        y_res = vs_loo[2] - _y_row[plane_idx_ref]
                        ts_res = (vs_loo[4] + _half_lenx_ss) - _ts_row[plane_idx_ref]
                        td_res = (vs_loo[0] * ss) - _td_row[plane_idx_ref]

                        if plane_idx_ref < 4:
                            ext_res_ystr_arr[pos, plane_idx_ref] = y_res
                            ext_res_tsum_arr[pos, plane_idx_ref] = ts_res
                            ext_res_tdif_arr[pos, plane_idx_ref] = td_res
                else:
                    # --- Iterative LOO (legacy convergence loop) ---
                    for plane_idx_ref in plane_idx_arr:
                        z_ref = _z_pos_arr[plane_idx_ref]
                        y_ref = _y_row[plane_idx_ref]
                        ts_ref = _ts_row[plane_idx_ref]
                        td_ref = _td_row[plane_idx_ref]

                        vs = vsf
                        istp_loo = 0
                        dist_loo = d0
                        while dist_loo > _tt_loo_cocut_f and istp_loo < _tt_loo_iter_max_f:
                            mk_loo.fill(0.0)
                            va_loo.fill(0.0)
                            for plane_idx in plane_idx_arr:
                                if plane_idx == plane_idx_ref:
                                    continue
                                zi = _z_pos_arr[plane_idx] - z_ref
                                _acc_fn(
                                    npar,
                                    vs,
                                    _y_row[plane_idx],
                                    _ts_row[plane_idx],
                                    _td_row[plane_idx],
                                    zi,
                                    _w_arr,
                                    ss,
                                    lenx,
                                    _sc_val,
                                    fixed_speed,
                                    mk_loo,
                                    va_loo,
                                )
                            istp_loo += 1
                            vs0 = vs
                            vs, merr_diag = _solve_fn(mk_loo, va_loo)
                            dist_loo = _fmahd_fn(npar, vs, vs0, merr_diag)

                        _tt_loo_refits_total += 1
                        _tt_loo_timtrack_iterations_total += int(istp_loo)
                        if not np.isfinite(dist_loo):
                            continue
                        y_res = vs[2] - y_ref
                        ts_res = (vs[4] + _half_lenx_ss) - ts_ref
                        td_res = (vs[0] * ss) - td_ref

                        if plane_idx_ref < 4:
                            ext_res_ystr_arr[pos, plane_idx_ref] = y_res
                            ext_res_tsum_arr[pos, plane_idx_ref] = ts_res
                            ext_res_tdif_arr[pos, plane_idx_ref] = td_res
                _tt_residual_loo_s += time.perf_counter() - _tt_t

    # Push the accumulated results back to the DataFrame in a single shot ------
    _tt_t = time.perf_counter()
    for plane_idx in range(4):
        col_suffix = plane_idx + 1
        working_df[f'tim_charge_{col_suffix}'] = charge_arr[:, plane_idx]
        working_df[f'tim_res_ystr_{col_suffix}'] = res_ystr_arr[:, plane_idx]
        working_df[f'tim_res_tsum_{col_suffix}'] = res_tsum_arr[:, plane_idx]
        working_df[f'tim_res_tdif_{col_suffix}'] = res_tdif_arr[:, plane_idx]
        working_df[f'tim_ext_res_ystr_{col_suffix}'] = ext_res_ystr_arr[:, plane_idx]
        working_df[f'tim_ext_res_tsum_{col_suffix}'] = ext_res_tsum_arr[:, plane_idx]
        working_df[f'tim_ext_res_tdif_{col_suffix}'] = ext_res_tdif_arr[:, plane_idx]

    working_df['tim_event_charge'] = event_charge_arr
    working_df['tim_timtrack_iterations'] = timtrack_iterations_arr
    working_df['tim_timtrack_conv_distance'] = timtrack_conv_distance_arr
    working_df['tim_timtrack_converged'] = timtrack_converged_arr
    working_df['tim_tt_task3_list'] = tt_task3_list_arr

    working_df['tim_th_chi'] = th_chi_arr
    working_df['tim_x'] = x_arr
    working_df['tim_xp'] = xp_arr
    working_df['tim_y'] = y_arr
    working_df['tim_yp'] = yp_arr
    working_df['tim_t0'] = t0_arr
    working_df['tim_s'] = s_arr
    working_df[['tim_res_y', 'tim_res_ts', 'tim_res_td']] = np.nan

    possible_ndf = {nvar * planes - npar for planes in range(2, nplan + 1)}
    possible_ndf = {ndf for ndf in possible_ndf if ndf >= 0}
    for ndf in possible_ndf:
        working_df[f'th_chi_{ndf}'] = th_chi_ndf_arrays.get(ndf, np.full(n_rows, np.nan, dtype=float))
    _tt_writeback_s += time.perf_counter() - _tt_t

#%%

# ------------------------------------------------------------------------------------
# End of TimTrack loop ---------------------------------------------------------------
# ------------------------------------------------------------------------------------

# Set the label to integer -----------------------------------------------------------
working_df["tt_task3_list"] = working_df["tt_task3_list"].astype(np.int32, copy=False)
theta_vals, phi_vals = calculate_angles(working_df["tim_xp"], working_df["tim_yp"])

# TimTrack-prefixed variables already exist; just ensure angles are set.
working_df["tim_theta"] = theta_vals
working_df["tim_phi"] = phi_vals

# Preserve slope columns for downstream compatibility
if "xp" not in working_df.columns:
    working_df["xp"] = working_df["tim_xp"]
if "yp" not in working_df.columns:
    working_df["yp"] = working_df["tim_yp"]

# Backward compatibility: expose tim_* results under legacy column names when missing
for p in range(1, 5):
    if f"res_ystr_{p}" not in working_df.columns:
        working_df[f"res_ystr_{p}"] = working_df.get(f"tim_res_ystr_{p}", np.nan)
    if f"res_tsum_{p}" not in working_df.columns:
        working_df[f"res_tsum_{p}"] = working_df.get(f"tim_res_tsum_{p}", np.nan)
    if f"res_tdif_{p}" not in working_df.columns:
        working_df[f"res_tdif_{p}"] = working_df.get(f"tim_res_tdif_{p}", np.nan)
    if f"ext_res_ystr_{p}" not in working_df.columns:
        working_df[f"ext_res_ystr_{p}"] = working_df.get(f"tim_ext_res_ystr_{p}", np.nan)
    if f"ext_res_tsum_{p}" not in working_df.columns:
        working_df[f"ext_res_tsum_{p}"] = working_df.get(f"tim_ext_res_tsum_{p}", np.nan)
    if f"ext_res_tdif_{p}" not in working_df.columns:
        working_df[f"ext_res_tdif_{p}"] = working_df.get(f"tim_ext_res_tdif_{p}", np.nan)
    if f"charge_{p}" not in working_df.columns:
        working_df[f"charge_{p}"] = working_df.get(f"tim_charge_{p}", 0)

if "event_charge" not in working_df.columns:
    working_df["event_charge"] = working_df.get("tim_event_charge", 0)
if "timtrack_iterations" not in working_df.columns:
    working_df["timtrack_iterations"] = working_df.get("tim_timtrack_iterations", 0)
if "timtrack_conv_distance" not in working_df.columns:
    working_df["timtrack_conv_distance"] = working_df.get("tim_timtrack_conv_distance", 0)
if "timtrack_converged" not in working_df.columns:
    working_df["timtrack_converged"] = working_df.get("tim_timtrack_converged", 0)

for p in range(1, 5):
    if f"tim_res_ystr_{p}" not in working_df.columns:
        working_df[f"tim_res_ystr_{p}"] = working_df.get(f"res_ystr_{p}", np.nan)
    if f"tim_res_tsum_{p}" not in working_df.columns:
        working_df[f"tim_res_tsum_{p}"] = working_df.get(f"res_tsum_{p}", np.nan)
    if f"tim_res_tdif_{p}" not in working_df.columns:
        working_df[f"tim_res_tdif_{p}"] = working_df.get(f"res_tdif_{p}", np.nan)
    if f"tim_ext_res_ystr_{p}" not in working_df.columns:
        working_df[f"tim_ext_res_ystr_{p}"] = working_df.get(f"ext_res_ystr_{p}", np.nan)
    if f"tim_ext_res_tsum_{p}" not in working_df.columns:
        working_df[f"tim_ext_res_tsum_{p}"] = working_df.get(f"ext_res_tsum_{p}", np.nan)
    if f"tim_ext_res_tdif_{p}" not in working_df.columns:
        working_df[f"tim_ext_res_tdif_{p}"] = working_df.get(f"ext_res_tdif_{p}", np.nan)

#%%

if create_plots and "tt_task3_list" in working_df.columns and "datetime" in working_df.columns:
    print("In")
    for combo in TRACK_COMBINATIONS:
        try:
            combo_int = int(combo)
        except ValueError:
            continue
        subset = working_df[working_df["tt_task3_list"] == combo_int]
        if subset.empty:
            continue
        plot_ts_with_side_hist(
            subset,
            ["tim_x", "tim_y", "tim_theta", "tim_phi", "tim_s", "tim_t0"],
            "datetime",
            f"timtrack_timeseries_combo_{combo}",
        )
        plot_residuals_ts_hist(
            subset,
            prefixes=[
                ("ystr", "tim_res_ystr_", "tim_ext_res_ystr_"),
                ("tsum", "tim_res_tsum_", "tim_ext_res_tsum_"),
                ("tdif", "tim_res_tdif_", "tim_ext_res_tdif_"),
            ],
            time_col="datetime",
            title=f"timtrack_residuals_combo_{combo}",
        )

#%%

# Combine detached and TimTrack estimates ------------------------------------
combined_core_vars = ["x", "y", "theta", "phi", "s", "t0"]
combined_columns = {}
for base in combined_core_vars:
    det_col = f"det_{base}"
    tim_col = f"tim_{base}"
    det_vals = (
        pd.to_numeric(working_df[det_col], errors="coerce").to_numpy(dtype=float, copy=False)
        if det_col in working_df
        else np.full(len(working_df), np.nan, dtype=float)
    )
    tim_vals = (
        pd.to_numeric(working_df[tim_col], errors="coerce").to_numpy(dtype=float, copy=False)
        if tim_col in working_df
        else np.full(len(working_df), np.nan, dtype=float)
    )
    det_finite = np.isfinite(det_vals)
    tim_finite = np.isfinite(tim_vals)
    both_finite = det_finite & tim_finite
    if base == "phi":
        avg = np.full(len(working_df), np.nan, dtype=float)
        err = np.full(len(working_df), np.nan, dtype=float)
        # Handle angular wrap: diff in [-pi, pi], average with wrap-aware mid-point
        diff = np.angle(np.exp(1j * (det_vals - tim_vals)))
        avg[both_finite] = np.angle(np.exp(1j * (tim_vals[both_finite] + diff[both_finite] / 2.0)))
        err[both_finite] = diff[both_finite] / 2.0
        avg[det_finite & ~tim_finite] = det_vals[det_finite & ~tim_finite]
        avg[tim_finite & ~det_finite] = tim_vals[tim_finite & ~det_finite]
        combined_columns[base] = avg
        combined_columns[f"{base}_err"] = err
    else:
        combined_vals = np.full(len(working_df), np.nan, dtype=float)
        combined_errs = np.full(len(working_df), np.nan, dtype=float)
        combined_vals[both_finite] = 0.5 * (det_vals[both_finite] + tim_vals[both_finite])
        combined_errs[both_finite] = 0.5 * (det_vals[both_finite] - tim_vals[both_finite])
        combined_vals[det_finite & ~tim_finite] = det_vals[det_finite & ~tim_finite]
        combined_vals[tim_finite & ~det_finite] = tim_vals[tim_finite & ~det_finite]
        combined_columns[base] = combined_vals
        combined_columns[f"{base}_err"] = combined_errs

residual_sets = [
    ("res_ystr", "det_res_ystr_", "tim_res_ystr_"),
    ("res_tsum", "det_res_tsum_", "tim_res_tsum_"),
    ("res_tdif", "det_res_tdif_", "tim_res_tdif_"),
    ("ext_res_ystr", "det_ext_res_ystr_", "tim_ext_res_ystr_"),
    ("ext_res_tsum", "det_ext_res_tsum_", "tim_ext_res_tsum_"),
    ("ext_res_tdif", "det_ext_res_tdif_", "tim_ext_res_tdif_"),]
for base, det_prefix, tim_prefix in residual_sets:
    for p in range(1, 5):
        det_col = f"{det_prefix}{p}"
        tim_col = f"{tim_prefix}{p}"
        det_vals = (
            pd.to_numeric(working_df[det_col], errors="coerce").to_numpy(dtype=float, copy=False)
            if det_col in working_df
            else np.full(len(working_df), np.nan, dtype=float)
        )
        tim_vals = (
            pd.to_numeric(working_df[tim_col], errors="coerce").to_numpy(dtype=float, copy=False)
            if tim_col in working_df
            else np.full(len(working_df), np.nan, dtype=float)
        )
        det_finite = np.isfinite(det_vals)
        tim_finite = np.isfinite(tim_vals)
        both_finite = det_finite & tim_finite
        combined_vals = np.full(len(working_df), np.nan, dtype=float)
        combined_errs = np.full(len(working_df), np.nan, dtype=float)
        combined_vals[both_finite] = 0.5 * (det_vals[both_finite] + tim_vals[both_finite])
        combined_errs[both_finite] = 0.5 * (det_vals[both_finite] - tim_vals[both_finite])
        combined_vals[det_finite & ~tim_finite] = det_vals[det_finite & ~tim_finite]
        combined_vals[tim_finite & ~det_finite] = tim_vals[tim_finite & ~det_finite]
        combined_columns[f"{base}_{p}"] = combined_vals
        combined_columns[f"{base}_{p}_err"] = combined_errs

if combined_columns:
    combined_df = pd.DataFrame(combined_columns, index=working_df.index)
    overlap_cols = [col for col in combined_df.columns if col in working_df.columns]
    if overlap_cols:
        working_df.loc[:, overlap_cols] = combined_df[overlap_cols].to_numpy()
    new_cols = [col for col in combined_df.columns if col not in working_df.columns]
    if new_cols:
        working_df = pd.concat([working_df, combined_df[new_cols]], axis=1)

# Defrag after all combined-column writes are complete
working_df = working_df.copy()

if "event_s_err" not in working_df.columns:
    det_s_vals = pd.to_numeric(working_df.get("det_s"), errors="coerce") if "det_s" in working_df.columns else None
    tim_s_vals = pd.to_numeric(working_df.get("tim_s"), errors="coerce") if "tim_s" in working_df.columns else None
    combo_s_vals = pd.to_numeric(working_df.get("s"), errors="coerce") if "s" in working_df.columns else None
    if det_s_vals is not None and tim_s_vals is not None:
        working_df["event_s_err"] = det_s_vals - tim_s_vals
    elif det_s_vals is not None and combo_s_vals is not None:
        working_df["event_s_err"] = det_s_vals - combo_s_vals

if create_debug_plots:
    def _emit_param_debug(param_label, columns, thresholds, *, tag="tunable"):
        cols_present = [col for col in columns if col in working_df.columns]
        if not cols_present:
            return
        debug_thresholds = {col: thresholds for col in cols_present}
        title = f"Task 4 pre-filter: {param_label} [{tag}] (station {station})"
        cols_present.sort()
        global debug_fig_idx
        debug_fig_idx = plot_debug_histograms(
            working_df,
            cols_present,
            debug_thresholds,
            title=title,
            out_dir=debug_plot_directory,
            fig_idx=debug_fig_idx,
        )

    def _plane_cols(prefix):
        return [f"{prefix}{p}" for p in range(1, 5)]

    # Core kinematic filters
    _emit_param_debug(
        "det_pos_filter",
        ["det_x", "det_y", "x", "y"],
        [-det_pos_filter, det_pos_filter],
    )
    _emit_param_debug(
        "proj_filter",
        ["xp", "yp"],
        [-proj_filter, proj_filter],
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

    # Residual filters (timtrack + detached + combined)
    _emit_param_debug(
        "res_ystr_filter",
        _plane_cols("res_ystr_"),
        [-res_ystr_filter, res_ystr_filter],
    )
    _emit_param_debug(
        "res_tsum_filter",
        _plane_cols("res_tsum_"),
        [-res_tsum_filter, res_tsum_filter],
    )
    _emit_param_debug(
        "res_tdif_filter",
        _plane_cols("res_tdif_"),
        [-res_tdif_filter, res_tdif_filter],
    )
    _emit_param_debug(
        "ext_res_ystr_filter",
        _plane_cols("ext_res_ystr_"),
        [-ext_res_ystr_filter, ext_res_ystr_filter],
    )
    _emit_param_debug(
        "ext_res_tsum_filter",
        _plane_cols("ext_res_tsum_"),
        [-ext_res_tsum_filter, ext_res_tsum_filter],
    )
    _emit_param_debug(
        "ext_res_tdif_filter",
        _plane_cols("ext_res_tdif_"),
        [-ext_res_tdif_filter, ext_res_tdif_filter],
    )
    _emit_param_debug(
        "det_res_ystr_filter",
        _plane_cols("det_res_ystr_"),
        [-det_res_ystr_filter, det_res_ystr_filter],
    )
    _emit_param_debug(
        "det_res_tsum_filter",
        _plane_cols("det_res_tsum_"),
        [-det_res_tsum_filter, det_res_tsum_filter],
    )
    _emit_param_debug(
        "det_res_tdif_filter",
        _plane_cols("det_res_tdif_"),
        [-det_res_tdif_filter, det_res_tdif_filter],
    )
    _emit_param_debug(
        "det_ext_res_ystr_filter",
        _plane_cols("det_ext_res_ystr_"),
        [-det_ext_res_ystr_filter, det_ext_res_ystr_filter],
    )
    _emit_param_debug(
        "det_ext_res_tsum_filter",
        _plane_cols("det_ext_res_tsum_"),
        [-det_ext_res_tsum_filter, det_ext_res_tsum_filter],
    )
    _emit_param_debug(
        "det_ext_res_tdif_filter",
        _plane_cols("det_ext_res_tdif_"),
        [-det_ext_res_tdif_filter, det_ext_res_tdif_filter],
    )

# print("----------------------------------------------------------------------")
# print("-------------------------- New definitions ---------------------------")
# print("----------------------------------------------------------------------")

# Derive the runtime trigger labels once the fit observables exist.
working_df = refresh_task4_trigger_columns(working_df)

_task4_make_combined_timeseries = (
    (create_essential_plots or create_plots)
    and task4_plot_enabled("combined_timeseries_combo")
)
_task4_make_combined_residuals = (
    (create_essential_plots or create_plots)
    and task4_plot_enabled("combined_residuals_combo")
)
if (
    (_task4_make_combined_timeseries or _task4_make_combined_residuals)
    and "tt_task3_list" in working_df.columns
    and "datetime" in working_df.columns
):
    for combo in TRACK_COMBINATIONS:
        try:
            combo_int = int(combo)
        except ValueError:
            continue
        subset = working_df[working_df["tt_task3_list"] == combo_int]
        if subset.empty:
            continue
        if _task4_make_combined_timeseries:
            plot_ts_err_with_hist(
                subset,
                ["x", "y", "theta", "phi", "s", "t0"],
                "datetime",
                title=f"combined_timeseries_combo_{combo}",
            )
        if _task4_make_combined_residuals:
            plot_residuals_ts_hist(
                subset,
                prefixes=[
                    ("ystr", "res_ystr_", "ext_res_ystr_"),
                    ("tsum", "res_tsum_", "ext_res_tsum_"),
                    ("tdif", "res_tdif_", "ext_res_tdif_"),
                ],
                time_col="datetime",
                title=f"combined_residuals_combo_{combo}",
            )

#%%

# Time series and fittings

timeseries_and_fits = bool(config.get("timeseries_and_fits", False))
_task4_make_hist_core_errs_combined = (
    (create_essential_plots or create_plots)
    and task4_plot_enabled("hist_core_errs_combined")
)
_task4_make_hist_core_errs_combined_with_fits = (
    (create_essential_plots or create_plots)
    and task4_plot_enabled("hist_core_errs_combined_with_fits")
)
if timeseries_and_fits or _task4_make_hist_core_errs_combined or _task4_make_hist_core_errs_combined_with_fits:

    # Time series of core track variables (averaged and errors) ------------------
    if 'datetime' in working_df.columns:

        ts_core = working_df.copy()
        ts_core['datetime'] = pd.to_datetime(ts_core['datetime'])
        ts_core = ts_core.sort_values('datetime')

        # Combined error histograms across combinations (one figure) --------------------
        err_vars = ['x_err', 'y_err', 'theta_err', 'phi_err', 's_err', 't0_err']
        combo_subsets = []
        for combo in TRACK_COMBINATIONS:
            try:
                combo_int = int(combo)
            except ValueError:
                continue
            subset = ts_core[ts_core['tt_task3_list'] == combo_int]
            if subset.empty:
                continue
            combo_subsets.append((combo, subset))
        del ts_core  # free the sorted full-copy; subsets in combo_subsets are independent

        if combo_subsets:
            # Compute global quantile bounds per variable across all combos
            bounds_dict = {}
            for var in err_vars:
                lows = []
                highs = []
                for _, sub in combo_subsets:
                    if var not in sub.columns:
                        continue
                    data = sub[var].dropna()
                    if data.empty:
                        continue
                    q_low, q_high = data.quantile([0.0001, 0.99999])
                    lows.append(q_low)
                    highs.append(q_high)
                if lows and highs:
                    bounds_dict[var] = (min(lows), max(highs))
                else:
                    bounds_dict[var] = (0, 1)

            n_rows = len(combo_subsets)
            n_cols = len(err_vars)

            # Fit a Gaussian per combination/variable and store stats (always, even if plots are off)
            def _gauss(x, amp, mu, sigma):
                return amp * norm.pdf(x, mu, sigma)

            fit_results: dict[tuple[int, str], tuple[float, float, float]] = {}

            for combo, sub in combo_subsets:
                try:
                    combo_int = int(combo)
                except ValueError:
                    continue
                for var in err_vars:
                    if var not in sub.columns:
                        continue
                    series = sub[var].dropna()
                    if series.empty:
                        continue
                    q25, q75 = series.quantile([0.25, 0.75])
                    global_variables[f"{var}_{combo_int}_q25"] = float(q25)
                    global_variables[f"{var}_{combo_int}_q75"] = float(q75)
                    mirror_for_half = var == "theta_err"
                    series_fit = pd.concat([series, -series]) if mirror_for_half else series
                    q_low, q_high = series_fit.quantile([0.0001, 0.99999])
                    bin_edges = np.linspace(q_low, q_high, 161)
                    bin_width = bin_edges[1] - bin_edges[0]
                    counts, edges = np.histogram(series_fit, bins=bin_edges)
                    if not np.any(counts):
                        continue

                    # Suppress central spike: drop bins far above the typical height
                    nonzero = counts[counts > 0]
                    typical = np.median(nonzero) if len(nonzero) else 0
                    mask = counts > 0
                    if typical > 0:
                        mask &= counts < typical * 6  # keep more populated bins as well
                    centers = 0.5 * (edges[1:] + edges[:-1])
                    x_fit = centers[mask]
                    y_fit = counts[mask]
                    if y_fit.size < 5:
                        continue
                    try:
                        p0 = [y_fit.max(), float(series.mean()), float(max(series.std(), 1e-6))]
                        weights = np.maximum(y_fit, 1)
                        popt, _ = _curve_fit_checked(
                            _gauss,
                            x_fit,
                            y_fit,
                            p0=p0,
                            sigma=1.0 / weights,  # heavier weight for populous bins
                            absolute_sigma=False,
                            maxfev=4000,
                        )
                    except Exception:
                        continue
                    amp, mu, sigma = popt
                    if mirror_for_half:
                        amp *= 0.5  # adjust amplitude back to one-sided scale
                    fit_results[(combo_int, var)] = (float(amp), float(mu), float(sigma))
                    global_variables[f"{var}_{combo_int}_gauss1_amp"] = float(amp)
                    global_variables[f"{var}_{combo_int}_gauss1_mu"] = float(mu)
                    global_variables[f"{var}_{combo_int}_gauss1_sigma"] = float(sigma)

            # Only plot if requested
            if _task4_make_hist_core_errs_combined or _task4_make_hist_core_errs_combined_with_fits:
                if _task4_make_hist_core_errs_combined:
                    fig, axes = plt.subplots(n_rows, n_cols, figsize=(4 * n_cols, 3 * n_rows), sharex='col')
                    if n_rows == 1:
                        axes = np.array([axes])
                    for r, (combo, sub) in enumerate(combo_subsets):
                        for c, var in enumerate(err_vars):
                            ax = axes[r, c]
                            if var not in sub.columns:
                                ax.set_visible(False)
                                continue
                            data = sub[var].dropna()
                            if data.empty:
                                ax.set_visible(False)
                                continue
                            q_low, q_high = bounds_dict.get(var, (data.min(), data.max()))
                            bin_edges = np.linspace(q_low, q_high, 161)
                            ax.hist(data, bins=bin_edges, color='C0', alpha=0.7)
                            ax.set_yscale('log')
                            ax.set_xlim(q_low, q_high)
                            if r == 0:
                                ax.set_title(var)
                            if c == 0:
                                ax.set_ylabel(f'Comb {combo}')
                            ax.grid(True, alpha=0.3)
                    plt.suptitle('Error distributions per combination (data)', fontsize=12)
                    plt.tight_layout(rect=[0, 0, 1, 0.94])
                    if save_plots:
                        final_filename = f'{fig_idx}_hist_core_errs_combined.png'
                        fig_idx += 1
                        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
                        plot_list.append(save_fig_path)
                        save_plot_figure(save_fig_path, format='png', alias="hist_core_errs_combined")
                    if show_plots:
                        plt.show()
                    plt.close()

                if _task4_make_hist_core_errs_combined_with_fits:
                    # Redraw with overlays
                    fig, axes = plt.subplots(n_rows, n_cols, figsize=(4 * n_cols, 3 * n_rows), sharex='col')
                    if n_rows == 1:
                        axes = np.array([axes])
                    for r, (combo, sub) in enumerate(combo_subsets):
                        for c, var in enumerate(err_vars):
                            ax = axes[r, c]
                            if var not in sub.columns:
                                ax.set_visible(False)
                                continue
                            data = sub[var].dropna()
                            if data.empty:
                                ax.set_visible(False)
                                continue
                            q_low, q_high = bounds_dict.get(var, (data.min(), data.max()))
                            bin_edges = np.linspace(q_low, q_high, 161)
                            counts, edges, _ = ax.hist(data, bins=bin_edges, color='C0', alpha=0.6, label='data')
                            ax.set_yscale('log')
                            ax.set_xlim(q_low, q_high)
                            y_min, y_max = ax.get_ylim()

                            try:
                                combo_int = int(combo)
                            except ValueError:
                                combo_int = None
                            if combo_int is not None:
                                params = fit_results.get((combo_int, var))
                                if params:
                                    amp, mu, sigma = params
                                    x_grid = np.linspace(q_low, q_high, 400)
                                    g_vals = _gauss(x_grid, amp, mu, sigma)
                                    ax.plot(x_grid, g_vals, 'r-', lw=1.0, label='fit')
                            if r == 0:
                                ax.set_title(var)
                            if c == 0:
                                ax.set_ylabel(f'Comb {combo}')
                            ax.set_ylim(y_min, y_max)
                            ax.grid(True, alpha=0.3)
                    plt.suptitle('Error distributions per combination (fits)', fontsize=12)
                    plt.tight_layout(rect=[0, 0, 1, 0.94])
                    if save_plots:
                        final_filename = f'{fig_idx}_hist_core_errs_combined_with_fits.png'
                        fig_idx += 1
                        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
                        plot_list.append(save_fig_path)
                        save_plot_figure(save_fig_path, format='png', alias="hist_core_errs_combined_with_fits")
                    if show_plots:
                        plt.show()
                    plt.close()

_prof["s_timtrack_fitting_s"] = round(time.perf_counter() - _t_sec, 2)
_prof["s_tt_intro_s"] = round(_tt_intro_s, 2)
_prof["s_tt_main_fit_s"] = round(_tt_main_fit_s, 2)
_prof["s_tt_residual_s"] = round(_tt_residual_s, 2)
_prof["s_tt_residual_loo_s"] = round(_tt_residual_loo_s, 2)
_prof["s_tt_writeback_s"] = round(_tt_writeback_s, 2)
_prof["tt_events_total_n"] = int(_tt_events_total)
_prof["tt_events_with_2plus_planes_n"] = int(_tt_events_with_2plus_planes)
_prof["tt_events_loo_eligible_n"] = int(_tt_events_loo_eligible)
_prof["tt_events_loo_processed_n"] = int(_tt_events_loo_processed)
_prof["tt_mainfit_timtrack_iterations_total_n"] = int(_tt_mainfit_timtrack_iterations_total)
_prof["tt_loo_refits_total_n"] = int(_tt_loo_refits_total)
_prof["tt_loo_timtrack_iterations_total_n"] = int(_tt_loo_timtrack_iterations_total)
_prof["tt_mainfit_iter_per_event"] = (
    float(_tt_mainfit_timtrack_iterations_total) / float(_tt_events_with_2plus_planes)
    if _tt_events_with_2plus_planes > 0
    else np.nan
)
_prof["tt_loo_iter_per_refit"] = (
    float(_tt_loo_timtrack_iterations_total) / float(_tt_loo_refits_total)
    if _tt_loo_refits_total > 0
    else np.nan
)
_prof["tt_loo_every_n"] = int(tt_loo_every_n)
_prof["tt_loo_iter_max"] = int(tt_loo_iter_max)
_prof["tt_loo_cocut"] = float(tt_loo_cocut)
_prof["tt_loo_mode"] = str(tt_loo_mode)
_t_sec = time.perf_counter()
print("----------------------------------------------------------------------")
print("-------------------- Real tracking trigger type ----------------------")
print("----------------------------------------------------------------------")

# Required constants supplied by the DAQ geometry
strip_half  = strip_length / 2.0         # x acceptance  : [-strip_half , +strip_half ]
width_half  = total_width / 2.0          # y acceptance  : [-width_half , +width_half ]
z_planes    = np.asarray(z_positions)    # shape (nplan,)

# Precompute averages of the two independent fits --------------------------
# New fitting track columns combining timtrack and the alternative method
x0_avg = pd.to_numeric(working_df["x"], errors="coerce").to_numpy(dtype=float)
y0_avg = pd.to_numeric(working_df["y"], errors="coerce").to_numpy(dtype=float)
theta_av = pd.to_numeric(working_df["theta"], errors="coerce").to_numpy(dtype=float)
phi_av = pd.to_numeric(working_df["phi"], errors="coerce").to_numpy(dtype=float)

vx = np.sin(theta_av) * np.cos(phi_av)                   # direction cosines
vy = np.sin(theta_av) * np.sin(phi_av)
vz = np.cos(theta_av)

tracking_vals = np.zeros(len(working_df), dtype=np.int32)

valid_track = (
    np.isfinite(x0_avg)
    & np.isfinite(y0_avg)
    & np.isfinite(theta_av)
    & np.isfinite(phi_av)
    & np.isfinite(vx)
    & np.isfinite(vy)
    & np.isfinite(vz)
    & (vz > 0.0) # upward track => no planes
    & (x0_avg != 0.0)
    & (y0_avg != 0.0)
    & (theta_av != 0.0)
    & (phi_av != 0.0)
)

if np.any(valid_track):
    n_planes = int(len(z_planes))
    hits = np.zeros((len(working_df), n_planes), dtype=bool)
    for j, z_p in enumerate(z_planes):
        t = np.divide(
            z_p,
            vz,
            out=np.full(vz.shape, np.nan, dtype=float),
            where=vz != 0.0,
        )
        x_i = x0_avg + vx * t
        y_i = y0_avg + vy * t
        hits[:, j] = (
            np.isfinite(x_i)
            & np.isfinite(y_i)
            & (-strip_half <= x_i)
            & (x_i <= strip_half)
            & (-width_half <= y_i)
            & (y_i <= width_half)
        )
    hits &= valid_track[:, np.newaxis]

    if n_planes == 4:
        # Map 4-plane hit bitmask to concatenated plane code (e.g., 13, 234, 1234).
        bit_weights = np.array([1, 2, 4, 8], dtype=np.uint8)
        bitmask = (hits.astype(np.uint8) * bit_weights).sum(axis=1)
        bitmask_to_tt = np.array(
            [0, 1, 2, 12, 3, 13, 23, 123, 4, 14, 24, 124, 34, 134, 234, 1234],
            dtype=np.int32,
        )
        tracking_vals = bitmask_to_tt[bitmask]
    else:
        # Generic fallback for unexpected plane counts.
        for idx in np.flatnonzero(valid_track):
            planes_hit = [str(p + 1) for p in range(n_planes) if hits[idx, p]]
            if planes_hit:
                tracking_vals[idx] = int("".join(planes_hit))

tracking_df = pd.DataFrame({'tt_task4_projected': tracking_vals}, index=working_df.index)
working_df = working_df.drop(columns=tracking_df.columns.intersection(working_df.columns), errors='ignore')
working_df = working_df.join(tracking_df)
working_df = working_df.copy()

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# The noise determination, if everything goes well ----------------------------
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------

tt_task4_fit_values = [234, 123, 34, 1234, 23, 12, 124, 134, 24, 13, 14]
# Pre-seed metadata keys so CSVs always include all fit outputs, even if a
# specific combination has no data in this run.
for _tt in tt_task4_fit_values:
    global_variables.setdefault(f"sigmoid_width_{_tt}", np.nan)
    global_variables.setdefault(f"background_slope_{_tt}", np.nan)
    global_variables.setdefault(f"sigmoid_amplitude_{_tt}", np.nan)
    global_variables.setdefault(f"sigmoid_center_{_tt}", np.nan)
    global_variables.setdefault(f"fit_normalization_{_tt}", np.nan)

_prof["s_trigger_type_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()
if time_window_fitting:

    print("---------------------------- Fitting loop ----------------------------")
    time_window_fitting_start = time.perf_counter()
    widths = np.linspace(
        0.0,
        2.0 * coincidence_window_cal_ns,
        coincidence_window_cal_number_of_points,
        dtype=float,
    )
    half_widths = 0.5 * widths
    width_chunk_size = 32
    tt_task4_fit_arr = get_task4_tt_series(
        working_df,
        preferred=TASK4_PRIMARY_TT_COLUMN,
    ).to_numpy(dtype=np.int32, copy=False)
    t_sum_cols = [
        f"p{plane}_tsum"
        for plane in range(1, 5)
        if f"p{plane}_tsum" in working_df.columns
    ]
    q_sum_cols = [
        f"p{plane}_qsum"
        for plane in range(1, 5)
        if f"p{plane}_tsum" in working_df.columns and f"p{plane}_qsum" in working_df.columns
    ]
    if not t_sum_cols:
        t_sum_cols = [
            f"p{plane}_s{strip}_tsum"
            for plane in range(1, 5)
            for strip in range(1, 5)
            if f"p{plane}_s{strip}_tsum" in working_df.columns
        ]
        q_sum_cols = [
            f"p{plane}_s{strip}_qsum"
            for plane in range(1, 5)
            for strip in range(1, 5)
            if f"p{plane}_s{strip}_tsum" in working_df.columns
            and f"p{plane}_s{strip}_qsum" in working_df.columns
        ]
    t_sum_all = (
        working_df[t_sum_cols].to_numpy(dtype=float, copy=False)
        if t_sum_cols
        else np.empty((len(working_df), 0), dtype=float)
    )
    q_sum_all = (
        working_df[q_sum_cols].to_numpy(dtype=float, copy=False)
        if q_sum_cols and len(q_sum_cols) == len(t_sum_cols)
        else np.empty((len(working_df), 0), dtype=float)
    )
    if q_sum_all.shape[1] != t_sum_all.shape[1]:
        print(
            "Warning: Task 4 time-window fitting could not align Q_sum columns "
            "with T_sum columns; falling back to legacy T_sum != 0 activity."
        )

    for tt_task4_fit_value in tt_task4_fit_values:
        mask = tt_task4_fit_arr == tt_task4_fit_value
        n_selected = int(np.count_nonzero(mask))

        if n_selected > 0:
            print(f"\nProcessing tt_task4_fit: {tt_task4_fit_value} with {n_selected} events.")
        t_sum_data = t_sum_all[mask]
        q_sum_data = q_sum_all[mask] if q_sum_all.shape[1] == t_sum_all.shape[1] else np.empty((n_selected, 0), dtype=float)
        if t_sum_data.size == 0:
            print(f"\n[Warning] Skipping tt_task4_fit {tt_task4_fit_value}: no canonical tsum columns.")
            continue

        if q_sum_data.shape[1] == t_sum_data.shape[1]:
            active_mask = np.isfinite(q_sum_data) & (q_sum_data > 0)
        else:
            active_mask = np.isfinite(t_sum_data) & (t_sum_data != 0)
        active_rows = np.any(active_mask, axis=1)
        if not np.any(active_rows):
            print(f"\n[Warning] Skipping tt_task4_fit {tt_task4_fit_value}: no positive-charge T_sum data.")
            continue

        active_counts = active_mask.sum(axis=1, keepdims=True)
        active_sums = (t_sum_data * active_mask).sum(axis=1, keepdims=True)
        row_stat = np.divide(
            active_sums,
            active_counts,
            out=np.zeros_like(active_sums, dtype=float),
            where=active_counts > 0,
        )
        abs_dev = np.abs(t_sum_data - row_stat)
        counts_per_width = np.empty(half_widths.shape[0], dtype=float)

        for start in range(0, half_widths.shape[0], width_chunk_size):
            stop = min(start + width_chunk_size, half_widths.shape[0])
            half_chunk = half_widths[start:stop]
            in_window = active_mask[:, :, None] & (abs_dev[:, :, None] <= half_chunk[None, None, :])
            count_in_window = in_window.sum(axis=1)
            counts_per_width[start:stop] = count_in_window.mean(axis=0)

        # Safely compute a scalar denominator: use the maximum of counts_per_width if positive,
        # otherwise fall back to 1. This avoids passing a list mixing arrays and scalars to np.max,
        # which raises an error due to inhomogeneous shapes.

        if counts_per_width.size == 0:
            denom = 1.0
        else:
            denom = float(np.max(counts_per_width))
            if not np.isfinite(denom) or denom <= 0:
                denom = 1.0
        global_variables[f'fit_normalization_{tt_task4_fit_value}'] = denom
        counts_per_width_norm = counts_per_width / denom

        # # Define model function: signal (logistic) + linear background
        # def signal_plus_background(w, S, w0, tau, B):
        #     return S / (1 + np.exp(-(w - w0) / tau)) + B * w

        def signal_plus_background(w, S, w0, sigma, B):
            return 0.5 * S * (1 + erf((w - w0) / (np.sqrt(2) * sigma))) + B * w

        p0 = [1.0, 1.0, 0.5, 0.02]

        # Convert to NumPy arrays (if not already)
        widths = np.asarray(widths)
        counts_per_width_norm = np.asarray(counts_per_width_norm)

        # Create a mask for valid (finite) values
        valid_mask = np.isfinite(widths) & np.isfinite(counts_per_width_norm)

        # Apply mask to both x and y data
        widths_clean = widths[valid_mask]
        counts_clean = counts_per_width_norm[valid_mask]

        if len(counts_clean) == 0 or len(widths_clean) == 0:
            print(f"[Warning] Skipping tt_task4_fit {tt_task4_fit_value}: no valid data.")
            continue

        # Then fit
        try:
            popt, _ = _curve_fit_checked(
                signal_plus_background,
                widths_clean,
                counts_clean,
                p0=p0,
                maxfev=10000,
            )
        except RuntimeError as exc:
            print(f"[Warning] Fit failed for tt_task4_fit {tt_task4_fit_value}: {exc}")
            global_variables[f'sigmoid_width_{tt_task4_fit_value}'] = np.nan
            global_variables[f'background_slope_{tt_task4_fit_value}'] = np.nan
            global_variables[f'sigmoid_amplitude_{tt_task4_fit_value}'] = np.nan
            global_variables[f'sigmoid_center_{tt_task4_fit_value}'] = np.nan
            continue

        S_fit, w0_fit, tau_fit, B_fit = popt
        print(f"tt_task4_fit {tt_task4_fit_value} - Fit parameters:\n  Signal amplitude S = {S_fit:.4f}\n  Transition center w0 = {w0_fit:.4f} ns\n  Transition width τ = {tau_fit:.4f} ns\n  Background slope B = {B_fit:.6f} per ns")

        global_variables[f'sigmoid_width_{tt_task4_fit_value}'] = tau_fit
        global_variables[f'background_slope_{tt_task4_fit_value}'] = B_fit
        global_variables[f'sigmoid_amplitude_{tt_task4_fit_value}'] = S_fit
        global_variables[f'sigmoid_center_{tt_task4_fit_value}'] = w0_fit


        if create_plots:
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.scatter(widths, counts_per_width_norm, label='Normalized average count in window')
            ax.axvline(x=coincidence_window_cal_ns, color='red', linestyle='--', label='Time coincidence window')
            ax.set_xlabel("Window width (ns)")
            ax.set_ylabel("Normalized average # of T_sum values in window")
            ax.set_title("Fraction of hits within stat-centered window vs width")
            ax.grid(True)
            w_fit = np.linspace(min(widths), max(widths), 300)
            f_fit = signal_plus_background(w_fit, *popt)
            ax.plot(w_fit, f_fit, 'k--', label='Signal + background fit')
            ax.axhline(S_fit, color='green', linestyle=':', alpha=0.6, label=f'Signal plateau ≈ {S_fit:.2f}')
            s_vals = S_fit / (1 + np.exp(-(w_fit - w0_fit) / tau_fit))
            b_vals = B_fit * w_fit
            f_vals = s_vals + b_vals
            P_signal = s_vals / f_vals
            P_background = b_vals / f_vals
            fig = plt.figure(figsize=(10, 8))
            gs = GridSpec(2, 1, height_ratios=[1, 2], hspace=0.05)
            ax_fill = fig.add_subplot(gs[0])  # Top: signal vs. background fill
            ax_main = fig.add_subplot(gs[1], sharex=ax_fill)  # Bottom: your original plot
            ax_fill.fill_between(w_fit, 0, P_signal, color='green', alpha=0.4, label='Signal')
            ax_fill.fill_between(w_fit, P_signal, 1, color='red', alpha=0.4, label='Background')
            ax_fill.set_ylabel("Fraction")
            y_min = float(np.nanmin(P_signal))
            if not np.isfinite(y_min) or y_min >= 1.0 - np.finfo(float).eps:
                y_min = 0.0
            elif y_min < 0.0:
                y_min = 0.0
            ax_fill.set_ylim(y_min, 1)
            # ax_fill.set_yticks([0.25, 0.5, 0.75, 1.0])
            ax_fill.legend(loc="upper right")
            ax_fill.set_title(f"Estimated Signal and Background Fractions per Window Width, tt_task4_fit = {tt_task4_fit_value}")
            plt.setp(ax_fill.get_xticklabels(), visible=False)
            ax_main.scatter(widths, counts_per_width_norm, label='Normalized average count in window')
            ax_main.plot(w_fit, f_fit, 'k--', label='Signal + background fit')
            ax_main.axhline(S_fit, color='green', linestyle=':', alpha=0.6, label=f'Signal plateau ≈ {S_fit:.2f}')
            ax_main.set_xlabel("Window width (ns)")
            ax_main.set_ylabel("Normalized average # of T_sum values in window")
            ax_main.grid(True)
            fit_summary = (f"Fit: S = {S_fit:.3f}, w₀ = {w0_fit:.3f} ns, " f"τ = {tau_fit:.3f} ns, B = {B_fit:.4f}/ns")
            ax_main.plot([], [], ' ', label=fit_summary)  # invisible handle to add text
            ax_main.legend()

            if save_plots:
                name_of_file = f'stat_window_accumulation_{tt_task4_fit_value}'
                final_filename = f'{fig_idx}_{name_of_file}.png'
                fig_idx += 1
                save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
                plot_list.append(save_fig_path)
                save_plot_figure(save_fig_path, format='png')
            if show_plots:
                plt.show()
            plt.close()

    print(
        f"[PROFILE][TASK_4] time-window fitting section: {time.perf_counter() - time_window_fitting_start:.2f}s",
        force=True,
    )
# -----------------------------------------------------------------------------
# Last filterings -------------------------------------------------------------
# -----------------------------------------------------------------------------

task4_final_filter_dry_run_summary = apply_task4_final_filter(
    working_df,
    apply_changes=False,
)[2]
task4_final_filter_dry_run_has_effect = int(
    (
        int(task4_final_filter_dry_run_summary.get("rows_affected", 0)) > 0
        or int(task4_final_filter_dry_run_summary.get("values_zeroed", 0)) > 0
        or int(task4_final_filter_dry_run_summary.get("failed_pair_any", 0)) > 0
    )
)
global_variables["task4_final_filter_dry_run_has_effect"] = task4_final_filter_dry_run_has_effect
global_variables["task4_final_filter_dry_run_input_rows"] = int(
    task4_final_filter_dry_run_summary.get("input_rows", len(working_df))
)
global_variables["task4_final_filter_dry_run_rows_affected"] = int(
    task4_final_filter_dry_run_summary.get("rows_affected", 0)
)
global_variables["task4_final_filter_dry_run_flagged_rows"] = int(
    task4_final_filter_dry_run_summary.get("flagged_rows", 0)
)
global_variables["task4_final_filter_dry_run_values_zeroed"] = int(
    task4_final_filter_dry_run_summary.get("values_zeroed", 0)
)
global_variables["task4_final_filter_dry_run_failed_pair_any"] = int(
    task4_final_filter_dry_run_summary.get("failed_pair_any", 0)
)
print(
    "[TASK4_FINAL_FILTER_DRY_RUN] "
    f"has_effect={'yes' if task4_final_filter_dry_run_has_effect else 'no'} "
    f"input_rows={global_variables['task4_final_filter_dry_run_input_rows']} "
    f"flagged_rows={global_variables['task4_final_filter_dry_run_flagged_rows']} "
    f"rows_affected={global_variables['task4_final_filter_dry_run_rows_affected']} "
    f"values_zeroed={global_variables['task4_final_filter_dry_run_values_zeroed']} "
    f"failed_pair_any={global_variables['task4_final_filter_dry_run_failed_pair_any']}",
    force=True,
)

working_df, task4_final_filter_rejected_df, task4_final_filter_summary = apply_task4_final_filter(
    working_df,
    apply_changes=True,
)
task4_final_filter_applied = True

tt_task4_fit_total = int(task4_final_filter_summary.get("input_rows", len(working_df)))
tt_task4_fit_removed = int(task4_final_filter_summary.get("rows_failed_tt_task4_fit_min", 0))
baseline_events = original_number_of_events if original_number_of_events else tt_task4_fit_total
record_filter_metric(
    "tt_task4_fit_lt_10_rows_removed_pct",
    tt_task4_fit_removed,
    tt_task4_fit_total if tt_task4_fit_total else 0,
)
record_filter_metric(
    "final_filter_rows_removed_pct",
    int(task4_final_filter_summary.get("rows_affected", 0)),
    tt_task4_fit_total if tt_task4_fit_total else 0,
)
record_filter_metric(
    "low_tt_zeroed_event_pct",
    tt_task4_fit_removed,
    baseline_events if baseline_events else 0,
)
record_filter_metric(
    "definitive_rows_removed_pct",
    int(task4_final_filter_summary.get("rows_affected", 0)),
    baseline_events if baseline_events else 0,
)
record_filter_metric(
    "definitive_removed_single_zero_rows_pct",
    int(task4_final_filter_summary.get("rows_failed_nonzero_single", 0)),
    baseline_events if baseline_events else 0,
)
record_filter_metric(
    "definitive_removed_multi_zero_rows_pct",
    int(task4_final_filter_summary.get("rows_failed_nonzero_multi", 0)),
    baseline_events if baseline_events else 0,
)
required_nonzero_cols = list(TASK4_EVENT_ATOMIC_COLUMNS)
for col in required_nonzero_cols:
    rows_removed = int(task4_final_filter_summary.get(f"rows_failed_primary_zero_{col}", 0))
    record_filter_metric(
        f"definitive_removed_primary_{col}_zero_rows_pct",
        rows_removed,
        baseline_events if baseline_events else 0,
    )

task4_plot_tt_column = get_task4_tt_column(working_df) or TASK4_PRIMARY_TT_COLUMN

if save_rejected_rows and not task4_final_filter_rejected_df.empty:
    os.makedirs(rejected_files_directory, exist_ok=True)
    final_rejected_path = os.path.join(
        rejected_files_directory,
        f"rejected_final_filtering_{basename_no_ext}.parquet",
    )
    task4_final_filter_rejected_df.to_parquet(
        final_rejected_path,
        engine="pyarrow",
        compression="zstd",
        index=False,
    )
    print(f"Rejected rows (final filtering) saved to: {final_rejected_path}")

if create_reject_plots and not task4_final_filter_rejected_df.empty:
    save_plots = True
    reject_plot_directory = os.path.join(
        base_directories["ancillary_directory"],
        "REJECTED_FILES",
        "REJECTED_PLOTS",
        f"FIGURES_EXEC_ON_{date_execution}",
    )
    os.makedirs(reject_plot_directory, exist_ok=True)
    original_figure_dir = base_directories["figure_directory"]
    original_plot_list = plot_list if "plot_list" in globals() else []
    base_directories["figure_directory"] = reject_plot_directory
    plot_list = []
    fig_idx_backup = globals().get("fig_idx")

    if "datetime" in task4_final_filter_rejected_df.columns:
        cols = [c for c in ("x", "y", "theta", "phi", "s", "t0") if c in task4_final_filter_rejected_df.columns]
        if cols:
            plot_ts_with_side_hist(
                task4_final_filter_rejected_df,
                cols,
                "datetime",
                f"rejected_final_filtering_{basename_no_ext}",
            )

    plot_reject_diagnostics(
        task4_final_filter_rejected_df,
        "rejected_final_filtering",
        basename_no_ext,
        hist_bins=reject_plot_hist_bins,
        cols_per_fig=reject_plot_hist_cols_per_fig,
        scatter_max=reject_plot_scatter_max_points,
    )

    base_directories["figure_directory"] = original_figure_dir
    plot_list = original_plot_list
    if fig_idx_backup is not None:
        fig_idx = fig_idx_backup
# FINAL plot block moved out of the runtime flow: trigger_types_raw_and_list, trigger_types_tracking_and_list, trigger_types_tracking_and_raw
pass

# FINAL plot block moved out of the runtime flow: trigger_types_definitive_tt_and_raw
pass

print("----------------------------------------------------------------------")
for tt_col in ("tt_task0_raw", "tt_task1_clean", "tt_task2_cal", "tt_task3_list", "tt_task4_fit", "tt_task4_fit"):
    if tt_col in working_df.columns:
        try:
            print(f"Unique {tt_col} values:", sorted(working_df[tt_col].unique()))
        except Exception:
            print(f"Could not list unique values for {tt_col}")
print("----------------------------------------------------------------------")

print("----------------------------------------------------------------------")
print("----------------------- Calculating some stuff -----------------------")
print("----------------------------------------------------------------------")

base_cond = (
    (working_df["p1_qsum"] < charge_plot_limit_right)
    & (working_df["p2_qsum"] < charge_plot_limit_right)
    & (working_df["p3_qsum"] < charge_plot_limit_right)
    & (working_df["p4_qsum"] < charge_plot_limit_right)
    & (working_df["event_charge"] > charge_plot_limit_left)
)
df_plot_ancillary = working_df.loc[base_cond].copy()

compute_timtrack_gaussian_sigma_chi2(
    df_plot_ancillary,
    working_df,
    combo_tt=1234,
    quantile=0.99,
    output_col="tim_th_chi_sigmafit_1234",
)
chi1234_cond = base_cond & pd.to_numeric(
    working_df["tim_th_chi_sigmafit_1234"], errors="coerce"
).lt(100)
df_plot_ancillary_1234_chi = working_df.loc[chi1234_cond].copy()
print(
    "Task 4 plot ancillary rows: "
    f"all_tt={len(df_plot_ancillary)}, "
    f"tt1234_chi_lt_100={len(df_plot_ancillary_1234_chi)}"
)
# Efficiency diagnostics should use the full activity-based event table,
# not the chi2/charge-clipped ancillary subset used for other plots.
# Efficiency inputs come from the post-TimTrack, post-final-filter data frame.
# The track-efficiency fiducial cuts are only applied inside the telescope
# efficiency builder, not as additional event-level filters on working_df.
df_efficiency_source = working_df.copy()

# -----------------------------------------------------------------------------------------------------------------------------

# FINAL plot block moved out of the runtime flow: timtrack_residuals_gaussian
pass

# FINAL plot block moved out of the runtime flow: external_residuals_gaussian
pass

# -----------------------------------------------------------------------------------------------------------------------------

# FINAL plot block moved out of the runtime flow: polar_theta_phi_definitive_tt_2d
pass

# ---------------------------------------------------------------------------
# Track-consistency: sample 4-fold event displays — XZ and YZ projections
# Z on vertical axis; equal mm scale so real detector proportions are visible
# ---------------------------------------------------------------------------
# FINAL plot block moved out of the runtime flow: event_display_sample
pass

# ---------------------------------------------------------------------------
# Track-consistency: LOO (leave-one-out) residuals per plane (2D histograms)
# ---------------------------------------------------------------------------
# FINAL plot block moved out of the runtime flow: track_consistency_loo_residuals
pass

# ---------------------------------------------------------------------------
# Strip hit occupancy: 2D hit map per plane (X from T_dif, Y from Y_final)
# ---------------------------------------------------------------------------
# FINAL plot block moved out of the runtime flow: strip_hit_occupancy
pass

_EFFICIENCY_VECTOR_AXIS_ORDER = ("x", "y", "theta", "phi")
_ROBUST_EFFICIENCY_PLATEAU_TOLERANCE = 0.05
efficiency_metadata_cfg = _resolve_task4_efficiency_metadata_cfg(config)
track_efficiency_fiducial_cfg = _resolve_task4_track_efficiency_fiducial_cfg(config)
track_efficiency_fullplane_cfg = _resolve_task4_track_efficiency_fiducial_cfg({})
track_efficiency_fiducial_active = _task4_track_efficiency_fiducial_is_active(
    track_efficiency_fiducial_cfg
)
efficiency_metadata_payload = _compute_track_based_efficiency_payload(
    df_efficiency_source,
    cfg_eff=efficiency_metadata_cfg,
    cfg_fiducial=track_efficiency_fiducial_cfg,
    z_positions=z_positions,
    tdiff_to_x=tdiff_to_x,
    strip_half=strip_half,
    width_half=width_half,
    theta_left_filter=theta_left_filter,
    theta_right_filter=theta_right_filter,
    phi_left_filter=phi_left_filter,
    phi_right_filter=phi_right_filter,
    y_pos_p13=np.asarray(y_pos_P1_and_P3, dtype=float),
    y_pos_p24=np.asarray(y_pos_P2_and_P4, dtype=float),
)
efficiency_metadata_payload_fullplane = _compute_track_based_efficiency_payload(
    df_efficiency_source,
    cfg_eff=efficiency_metadata_cfg,
    cfg_fiducial=track_efficiency_fullplane_cfg,
    z_positions=z_positions,
    tdiff_to_x=tdiff_to_x,
    strip_half=strip_half,
    width_half=width_half,
    theta_left_filter=theta_left_filter,
    theta_right_filter=theta_right_filter,
    phi_left_filter=phi_left_filter,
    phi_right_filter=phi_right_filter,
    y_pos_p13=np.asarray(y_pos_P1_and_P3, dtype=float),
    y_pos_p24=np.asarray(y_pos_P2_and_P4, dtype=float),
)
track_efficiency_reference_param_hash = _task4_resolve_efficiency_param_hash(
    simulated_param_hash,
    df_efficiency_source,
)
track_efficiency_simulated_efficiencies_percent: list[float] = []
if is_simulated_file and track_efficiency_reference_param_hash:
    _sim_eff_values = load_simulated_efficiencies(track_efficiency_reference_param_hash)
    if _sim_eff_values:
        track_efficiency_simulated_efficiencies_percent = [
            100.0 * float(value) for value in _sim_eff_values[:4]
        ]
track_efficiency_four_plane_fiducial_index: pd.Index | None = None
if bool(efficiency_metadata_payload.get("available", False)) and task4_plot_tt_column in df_efficiency_source.columns:
    _tt_task4_fit_1234_index = pd.Index(
        df_efficiency_source.index[
            pd.to_numeric(df_efficiency_source[task4_plot_tt_column], errors="coerce")
            .fillna(0)
            .eq(1234.0)
        ]
    )
    track_efficiency_four_plane_fiducial_index = _resolve_track_efficiency_four_plane_fiducial_index(
        efficiency_metadata_payload,
        tt_task4_fit_1234_index=_tt_task4_fit_1234_index,
    )

# FINAL plot block moved out of the runtime flow: tim_th_chi_sigmafit_1234_histogram
pass
track_efficiency_simulation_title_line = _format_task4_simulated_efficiency_title_line(
    track_efficiency_simulated_efficiencies_percent
)
if {"tt_task4_fit", "tt_task3_list"}.issubset(df_efficiency_source.columns):
    _tt_task4_fit_counts = pd.to_numeric(df_efficiency_source["tt_task4_fit"], errors="coerce").fillna(0).astype(int).value_counts()
    _tt_task3_list_counts = pd.to_numeric(df_efficiency_source["tt_task3_list"], errors="coerce").fillna(0).astype(int).value_counts()
    global_variables["efficiency_source_tt_task4_fit_1234_count"] = int(_tt_task4_fit_counts.get(1234, 0))
    global_variables["efficiency_source_tt_task3_list_1234_count"] = int(_tt_task3_list_counts.get(1234, 0))
    print(
        "[track_based_efficiency] source counts: "
        f"tt_task4_fit_1234={int(_tt_task4_fit_counts.get(1234, 0))} "
        f"tt_task3_list_1234={int(_tt_task3_list_counts.get(1234, 0))}"
    )
if not bool(efficiency_metadata_payload.get("available", False)):
    print(
        "[track_based_efficiency] metadata payload unavailable: "
        f"{efficiency_metadata_payload.get('reason', 'unknown')}"
    )
if not bool(efficiency_metadata_payload_fullplane.get("available", False)):
    print(
        "[track_based_efficiency] full-plane reference payload unavailable: "
        f"{efficiency_metadata_payload_fullplane.get('reason', 'unknown')}"
    )
task4_efficiency_vector_title_line = _format_task4_efficiency_vector_title_line(
    efficiency_metadata_payload
)
projection_ellipse_cfg = _resolve_projection_ellipse_diagnostic_cfg(config, proj_filter)
projection_ellipse_payload = _build_projection_ellipse_diagnostic_payload(
    df_plot_ancillary,
    projection_ellipse_cfg,
)
_append_projection_ellipse_metadata(projection_ellipse_payload)
projection_scaling_reference_tt, projection_scaling_reference_result = _select_projection_scaling_reference(
    projection_ellipse_payload
)
projection_scaling_summary = _summarize_projection_scaling(projection_ellipse_payload)
global_variables["timtrack_projection_scaling_reference_tt"] = (
    projection_scaling_reference_tt if projection_scaling_reference_tt is not None else ""
)
if isinstance(projection_scaling_reference_result, dict) and bool(
    projection_scaling_reference_result.get("available", False)
):
    global_variables["timtrack_projection_scaling_reference_n_points"] = int(
        projection_scaling_reference_result.get("n_points", 0) or 0
    )
else:
    global_variables["timtrack_projection_scaling_reference_n_points"] = 0
global_variables["timtrack_projection_scaling_factor_xproj"] = float(
    projection_scaling_summary.get("global_factor", np.nan)
)
global_variables["timtrack_projection_scaling_factor_xproj_global"] = float(
    projection_scaling_summary.get("global_factor", np.nan)
)
global_variables["timtrack_projection_scaling_global_method"] = str(
    projection_scaling_summary.get("global_method", "")
)
global_variables["timtrack_projection_scaling_global_n_contributing_tts"] = int(
    projection_scaling_summary.get("n_contributing_tts", 0) or 0
)
global_variables["timtrack_projection_scaling_global_total_weight"] = float(
    projection_scaling_summary.get("total_weight", 0.0) or 0.0
)

# ---------------------------------------------------------------------------
# Track-based single-plane efficiency (telescope method)
# Use 3 planes as a telescope, project to the 4th, ask: did the 4th fire?
# ---------------------------------------------------------------------------
# FINAL plot block moved out of the runtime flow: track_based_efficiency
pass

# ---------------------------------------------------------------------------
# TimTrack projection contour diagnostic
# Elliptical-Gaussian fit on the (xp, yp) density, with contour families
# overlaid at fixed fractions of the local peak.
# ---------------------------------------------------------------------------
# FINAL plot block moved out of the runtime flow: timtrack_projection_ellipse_contours
pass

# ---------------------------------------------------------------------------
# TimTrack projection scaling comparison
# Compare the native projection/angle variables against a version where xp
# is rescaled so its width matches yp, using the per-definitive_tt ellipse fit.
# ---------------------------------------------------------------------------
# FINAL plot block moved out of the runtime flow: timtrack_projection_scaled_angle_comparison
pass

# ---------------------------------------------------------------------------
# Track-based efficiency: all events vs. tt-unchanged (tt_task0_raw == tt_task3_list)
# Same telescope method as above; 1D efficiency vs projected Y and X.
# Two curves per subplot: "all" and "unchanged" (tt_task0_raw == tt_task3_list).
# ---------------------------------------------------------------------------
# FINAL plot block moved out of the runtime flow: track_based_efficiency_tt_stability
pass

# ---------------------------------------------------------------------------
# Track-based efficiency vs theta — 4 planes on one figure
# Same telescope method; reveals angular efficiency dependence for
# comparison between real data and simulation.
# ---------------------------------------------------------------------------
# FINAL plot block moved out of the runtime flow: track_based_efficiency_vs_theta
pass

# ---------------------------------------------------------------------------
# Large combined track-efficiency diagnostic
# Rows: x/y map, eff(y), eff(x), eff(theta), eff(phi), theta/phi map.
# ---------------------------------------------------------------------------
# FINAL plot block moved out of the runtime flow: track_efficiency_large_plot
pass

# ── chi2 vs charge population diagnostic ─────────────────────────────────────
# 3 figures (one per charge metric): rows = missed / hit (separate panels),
# cols = 4 test planes.  Right marginal: chi2 histogram (horizontal, log count,
# shared Y).  Bottom marginal: charge histogram (log count, shared X per col).
# Hexbin (log-norm) per panel so density is visible even at large N.
# Adjacent/dispersed topology comparison removed with obsolete topology split column.

if create_plots and task4_plot_enabled("polar_theta_phi_tt_task4_fit_2d"):
    df_filtered = df_plot_ancillary
    # tt_values = sorted(df_filtered['definitive_tt'].dropna().unique(), key=lambda x: int(x))

    tt_values = [12, 23, 34, 123, 234, 1234]

    n_tt = len(tt_values)
    ncols = 3
    nrows = (n_tt + 1) // ncols

    fig, axes = plt.subplots(nrows, ncols, figsize=(7 * ncols, 7 * nrows), squeeze=False)
    phi_nbins = 40
    # theta_nbins = int(round(phi_nbins / 2) + 1)
    theta_nbins = 40
    theta_bins = np.linspace(theta_left_filter, theta_right_filter, theta_nbins )
    phi_bins = np.linspace(phi_left_filter, phi_right_filter, phi_nbins)
    colors = plt.cm.turbo

    # Select theta/phi range (optional filtering)
    theta_min, theta_max = theta_left_filter, theta_right_filter    # adjust as needed
    phi_min, phi_max     = phi_left_filter, phi_right_filter        # adjust as needed

    vmax_global = (
        df_filtered.groupby(task4_plot_tt_column)[['theta', 'phi']]
        .apply(
            lambda df: np.histogram2d(
                df['theta'],
                df['phi'],
                bins=[theta_bins, phi_bins],
            )[0].max()
        )
        .max()
    )

    for idx, tt_val in enumerate(tt_values):
        row_idx, col_idx = divmod(idx, ncols)
        ax = axes[row_idx][col_idx]

        df_tt = df_filtered[df_filtered['tt_task4_fit'] == tt_val]
        theta_vals = df_tt['theta'].dropna()
        phi_vals = df_tt['phi'].dropna()

        # Apply range filtering
        mask = (theta_vals >= theta_min) & (theta_vals <= theta_max) & \
               (phi_vals >= phi_min) & (phi_vals <= phi_max)
        theta_vals = theta_vals[mask]
        phi_vals   = phi_vals[mask]

        if len(theta_vals) < 10 or len(phi_vals) < 10:
            ax.set_visible(False)
            continue

        # Polar plot settings
        fig.delaxes(axes[row_idx][col_idx])  # remove the original non-polar Axes
        ax = fig.add_subplot(nrows, ncols, idx + 1, polar=True)  # add a polar Axes
        axes[row_idx][col_idx] = ax  # update reference for consistency

        ax.set_facecolor(colors(0.0))  # darkest background in colormap

        # 2D histogram: use phi as angle, theta as radius
        h, r_edges, phi_edges = np.histogram2d(theta_vals, phi_vals, bins=[theta_bins, phi_bins])
        r_centers = 0.5 * (r_edges[:-1] + r_edges[1:])
        phi_centers = 0.5 * (phi_edges[:-1] + phi_edges[1:])
        R, PHI = np.meshgrid(r_centers, phi_centers, indexing='ij')
        c = ax.pcolormesh(PHI, R, h, cmap='viridis', vmin=0, vmax=vmax_global)
        local_max = h.max()
        cb = fig.colorbar(c, ax=ax, pad=0.1)
        cb.ax.hlines(local_max, *cb.ax.get_xlim(), colors='white', linewidth=2, linestyles='dashed')

    plt.suptitle(r'2D Histogram of $\theta$ vs. $\phi$ for each tt_task4_fit Type', fontsize=16)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    if save_plots:
        final_filename = f'{fig_idx}_polar_theta_phi_tt_task4_fit_2D.png'
        fig_idx += 1
        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format='png')
    if show_plots:
        plt.show()
    plt.close()

# -----------------------------------------------------------------------------------------------------------------------------

# FINAL plot block moved out of the runtime flow: timtrack_results_hexbin_combination_projections, timtrack_results_scatter_combination_projections
pass

    # df_plot_ancillary_conv = df_plot_ancillary[df_plot_ancillary['timtrack_converged'] == 1].copy()
    # # Comparison with alternative fitting -------------------------------------------------------------------
    # plot_col = ['x', 'y', 'theta', 'phi', 'event_s_err']
    # for filters, title in df_cases_1:
    #     fig_idx = plot_hexbin_matrix(
    #         df_plot_ancillary,
    #         plot_col,
    #         filters,
    #         title,
    #         save_plots,
    #         show_plots,
    #         base_directories,
    #         fig_idx,
    #         plot_list
    #     )

    # df_plot_ancillary_conv = df_plot_ancillary[df_plot_ancillary['timtrack_converged'] == 0].copy()
    # # Comparison with alternative fitting -------------------------------------------------------------------
    # plot_col = ['x', 'y', 'theta', 'phi', 'event_s_err']
    # for filters, title in df_cases_1:
    #     fig_idx = plot_hexbin_matrix(
    #         df_plot_ancillary,
    #         plot_col,
    #         filters,
    #         title,
    #         save_plots,
    #         show_plots,
    #         base_directories,
    #         fig_idx,
    #         plot_list
    #     )

# ------------------------------------------------------------------------------------------------------

# if create_plots:
#     df_filtered = df_plot_ancillary.copy()
#     fig, axes = plt.subplots(2, 1, figsize=(7, 8), sharex=True)
#     colors = plt.cm.tab10.colors
#     bins = np.linspace(theta_left_filter, theta_right_filter, 150)
#     tt_values = sorted(df_filtered['definitive_tt'].dropna().unique(), key=lambda x: int(x))

#     for row_idx, (theta_col, row_label) in enumerate([('tim_theta', r'$\theta$'), ('det_theta', r'$\theta_{\mathrm{alt}}$')]):
#         ax = axes[row_idx]
#         for i, tt_val in enumerate(tt_values):
#             df_tt = df_filtered[df_filtered['definitive_tt'] == tt_val]
#             theta_vals = df_tt[theta_col].dropna()
#             if len(theta_vals) < 10:
#                 continue
#             label = f'{tt_val}'
#             ax.hist(theta_vals, bins=bins, histtype='step', linewidth=1,
#                     color=colors[i % len(colors)], label=label)
#         ax.set_xlim(theta_left_filter, theta_right_filter)
#         ax.set_xlabel(row_label + r' [rad]')
#         ax.set_ylabel('Counts')
#         ax.set_title(f'{row_label} — Zoom-in')
#         ax.grid(True)
#         if row_idx == 0:
#             ax.legend(title='definitive_tt', fontsize='small')

#     plt.suptitle(r'$\theta$ and $\theta_{\mathrm{alt}}$ (Zoom-in) by Definitive TT Type', fontsize=15)
#     plt.tight_layout(rect=[0, 0, 1, 0.95])
#     if save_plots:
#         final_filename = f'{fig_idx}_theta_det_theta_zoom_definitive_tt.png'
#         fig_idx += 1
#         save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
#         plot_list.append(save_fig_path)
#         save_plot_figure(save_fig_path, format='png')
#     if show_plots:
#         plt.show()
#     plt.close()

if create_plots:
    df_filtered = df_plot_ancillary
    fig, axes = plt.subplots(2, 1, figsize=(7, 8), sharex=True)
    colors = plt.cm.tab10.colors
    bins = np.linspace(theta_left_filter, theta_right_filter, 150)
    tt_values = sorted(df_filtered['tt_task4_fit'].dropna().unique(), key=lambda x: int(x))

    for row_idx, (theta_col, row_label) in enumerate([('tim_theta', r'$\theta$'), ('det_theta', r'$\theta_{\mathrm{alt}}$')]):
        ax = axes[row_idx]
        for i, tt_val in enumerate(tt_values):
            df_tt = df_filtered[df_filtered['tt_task4_fit'] == tt_val]
            theta_vals = df_tt[theta_col].dropna()
            if len(theta_vals) < 10:
                continue
            label = f'{tt_val}'
            ax.hist(theta_vals, bins=bins, histtype='step', linewidth=1,
                    color=colors[i % len(colors)], label=label)
        ax.set_xlim(theta_left_filter, theta_right_filter)
        ax.set_xlabel(row_label + r' [rad]')
        ax.set_ylabel('Counts')
        ax.set_title(f'{row_label} — Zoom-in')
        ax.grid(True)
        if row_idx == 0:
            ax.legend(title='tt_task4_fit', fontsize='small')

    plt.suptitle(r'$\theta$ and $\theta_{\mathrm{alt}}$ (Zoom-in) by Tracking TT Type', fontsize=15)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    if save_plots:
        final_filename = f'{fig_idx}_theta_det_theta_zoom_tt_task4_fit.png'
        fig_idx += 1
        save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
        plot_list.append(save_fig_path)
        save_plot_figure(save_fig_path, format='png')
    if show_plots:
        plt.show()
    plt.close()

del df_plot_ancillary
del df_plot_ancillary_1234_chi
gc.collect()

# FINAL plot block moved out of the runtime flow: events_per_second_by_plane_cardinality_double_row
pass

_prof["s_fitting_loop_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()
print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")
print("-------------------------- Save and finish ---------------------------")
print("----------------------------------------------------------------------")
print("----------------------------------------------------------------------")

# Save the data ---------------------------------------------------------------
# if save_full_data: # Save a full version of the data, for different studies and debugging
#     working_df.to_csv(save_full_path, index=False, sep=',', float_format='%.5g')
#     print(f"Datafile saved in {save_full_filename}.")

# Save the main columns, relevant for the posterior analysis ------------------
missing_charge_cols = []
for plane in ['1', '2', '3', '4']:
    for strip in range(1, 5):
        source_col = f'p{plane}_s{strip}_qsum'
        if source_col not in working_df.columns:
            working_df[source_col] = np.nan
            missing_charge_cols.append(source_col)

if missing_charge_cols:
    unique_missing = sorted(set(missing_charge_cols))
    print(
        "Warning: missing charge columns; created with NaN defaults: "
        + ", ".join(unique_missing)
    )

for i, plane in enumerate(['1', '2', '3', '4']):
    for j in range(4):
        strip = j + 1
        source_col = f'p{plane}_s{strip}_qsum'
        working_df[f'p{plane}_s{strip}_qsum'] = working_df[source_col]

if self_trigger:
    for i, plane in enumerate(['1', '2', '3', '4']):
        for j in range(4):
            strip = j + 1
            source_col = f'p{plane}_s{strip}_qsum'
            if source_col not in working_st_df.columns:
                working_st_df[source_col] = np.nan
                print(f"Warning: missing self-trigger charge column; created NaN: {source_col}")
            working_st_df[f'p{plane}_s{strip}_qsum'] = working_st_df[source_col]

# Charge checking --------------------------------------------------------------------------------------------------------
if self_trigger:
    if (create_essential_plots or create_plots) and task4_plot_enabled("all_channels_charge"):

        fig, axs = plt.subplots(4, 4, figsize=(18, 12))
        for i in range(1, 5):
            for j in range(1, 5):
                # Get the column name
                col_name = f"p{i}_s{j}_qsum"

                # Plot the histogram
                v = working_df[col_name]
                v = v[v != 0]

                counts_v, bins_v = np.histogram(v, bins=80, range=(0, 40))
                normalized_v = counts_v / max(counts_v)
                axs[i-1, j-1].stairs(normalized_v, bins_v, alpha=0.5, label='event', color='blue', fill=True)

                if self_trigger:
                    x = working_st_df[col_name]
                    x = x[x != 0]
                    counts_x, bins_x = np.histogram(x, bins=40, range=(0, 40))
                    normalized_x = counts_x / max(counts_x)
                    axs[i-1, j-1].stairs(normalized_x, bins_x, alpha=0.5, label='self-trigger', color='orange', fill=True)

                axs[i-1, j-1].set_title(col_name)
                axs[i-1, j-1].set_xlabel("Charge / ns")
                axs[i-1, j-1].set_ylabel("Frequency")
                axs[i-1, j-1].grid(True)

                if i == j == 4:
                    axs[i-1, j-1].legend(loc='upper right')

        plt.suptitle("Event and self trigger charge spectra comparison")
        plt.tight_layout()
        figure_name = f"all_channels_charge_mingo0{station}"
        if save_plots:
            name_of_file = figure_name
            final_filename = f'{fig_idx}_{name_of_file}.png'
            fig_idx += 1
            save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
            plot_list.append(save_fig_path)
            save_plot_figure(save_fig_path, format='png')
        if show_plots: plt.show()
        plt.close()

if self_trigger:
    if (create_essential_plots or create_plots) and task4_plot_enabled("all_channels_charge"):

        fig, axs = plt.subplots(4, 4, figsize=(18, 12))
        # Filter once outside the loop; read-only inside so no copy needed.
        plot_def_df = working_df.loc[pd.to_numeric(working_df[task4_plot_tt_column], errors="coerce") == 1234]
        for i in range(1, 5):
            for j in range(1, 5):
                # Get the column name
                col_name = f"p{i}_s{j}_qsum"

                # Plot the histogram
                v = plot_def_df[col_name]
                v = v[v != 0]

                counts_v, bins_v = np.histogram(v, bins=80, range=(0, 40))
                normalized_v = counts_v / max(counts_v)
                axs[i-1, j-1].stairs(normalized_v, bins_v, alpha=0.5, label='event', color='blue', fill=True)

                if self_trigger:
                    x = working_st_df[col_name]
                    x = x[x != 0]
                    counts_x, bins_x = np.histogram(x, bins=40, range=(0, 40))
                    normalized_x = counts_x / max(counts_x)
                    axs[i-1, j-1].stairs(normalized_x, bins_x, alpha=0.5, label='self-trigger', color='orange', fill=True)

                axs[i-1, j-1].set_title(col_name)
                axs[i-1, j-1].set_xlabel("Charge / ns")
                axs[i-1, j-1].set_ylabel("Frequency")
                axs[i-1, j-1].grid(True)

                if i == j == 4:
                    axs[i-1, j-1].legend(loc='upper right')

        plt.suptitle("Event (4-fold) and self trigger charge spectra comparison")
        plt.tight_layout()
        figure_name = f"all_channels_charge_mingo0{station}"
        if save_plots:
            name_of_file = figure_name
            final_filename = f'{fig_idx}_{name_of_file}.png'
            fig_idx += 1
            save_fig_path = os.path.join(base_directories["figure_directory"], final_filename)
            plot_list.append(save_fig_path)
            save_plot_figure(save_fig_path, format='png')
        if show_plots: plt.show()
        plt.close()
# ------------------------------------------------------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Create and save the PDF -----------------------------------------------------
# -----------------------------------------------------------------------------

# Ensure Task 4 plots and output use the same final charge-based trigger type.
working_df = refresh_task4_trigger_columns(working_df)

_task4_charge_series = None
_task4_charge_source = None
_task4_charge_series, _task4_charge_source = _resolve_task4_total_event_charge_series(working_df)
if _task4_charge_source is not None:
    print(f"TASK_4 event_charge source: {_task4_charge_source}")

if (
    _task4_charge_series is not None
    and (create_essential_plots or create_plots)
    and task4_plot_enabled("total_event_charge_histogram")
):
    _task4_charge_quantile = float(config.get("total_event_charge_histogram_upper_quantile", 0.5))
    if not np.isfinite(_task4_charge_quantile):
        _task4_charge_quantile = 0.5
    _task4_charge_quantile = min(max(_task4_charge_quantile, 0.01), 0.999)

    _task4_charge_plot_values = pd.to_numeric(_task4_charge_series, errors="coerce")
    _task4_charge_plot_values = _task4_charge_plot_values[
        np.isfinite(_task4_charge_plot_values.to_numpy(dtype=float, copy=False))
    ]
    _task4_charge_plot_values = _task4_charge_plot_values[_task4_charge_plot_values >= 0.0]

    _task4_tt_task4_fit_series = pd.to_numeric(
        working_df.get(task4_plot_tt_column, pd.Series(np.nan, index=working_df.index)),
        errors="coerce",
    )
    _task4_hist_panels = [
        ("Total", None),
        ("1234", 1234),
        ("123", 123),
        ("234", 234),
        ("124", 124),
        ("134", 134),
        ("12", 12),
        ("23", 23),
        ("34", 34),
    ]

    _task4_charge_upper = float(_task4_charge_plot_values.quantile(_task4_charge_quantile))
    if not np.isfinite(_task4_charge_upper) or _task4_charge_upper <= 0:
        _task4_charge_upper = 1.0
    _task4_charge_upper = max(_task4_charge_upper, 0.25)
    _task4_bin_width = 0.25
    _task4_bins = np.arange(0.0, _task4_charge_upper + _task4_bin_width, _task4_bin_width)
    if _task4_bins.size < 2:
        _task4_bins = np.array([0.0, max(_task4_charge_upper, _task4_bin_width)])

    _task4_fig, _task4_axes = plt.subplots(
        3,
        3,
        figsize=(12, 12),
        sharex=True,
        sharey=True,
    )
    _task4_axes = np.asarray(_task4_axes).reshape(3, 3)

    for _task4_ax, (_task4_title, _task4_tt_value) in zip(_task4_axes.flat, _task4_hist_panels):
        if _task4_tt_value is None:
            _task4_subset = _task4_charge_plot_values
        else:
            _task4_tt_mask = _task4_tt_task4_fit_series == _task4_tt_value
            _task4_subset = _task4_charge_series.loc[_task4_tt_mask]
            _task4_subset = pd.to_numeric(_task4_subset, errors="coerce")
            _task4_subset = _task4_subset[
                np.isfinite(_task4_subset.to_numpy(dtype=float, copy=False))
            ]
            _task4_subset = _task4_subset[_task4_subset >= 0.0]

        _task4_subset = _task4_subset[_task4_subset <= _task4_charge_upper]
        _task4_ax.hist(
            _task4_subset,
            bins=_task4_bins,
            color="C1",
            histtype="step",
            linewidth=1.0,
        )
        _task4_ax.set_title(_task4_title, fontsize=10)
        _task4_ax.set_yscale("log")
        _task4_ax.set_xlim(0, _task4_charge_upper)
        _task4_ax.grid(True, alpha=0.25)

    for _task4_ax in _task4_axes[-1, :]:
        _task4_ax.set_xlabel("Total event charge")
    for _task4_ax in _task4_axes[:, 0]:
        _task4_ax.set_ylabel("Count")

    _task4_fig.suptitle(
        f"Total event charge histograms up to q={_task4_charge_quantile:.2f}",
        fontsize=12,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.97])

    # FINAL plot block moved out of the runtime flow: total_event_charge_histogram
    pass
    if show_plots:
        plt.show()
    plt.close(_task4_fig)
elif _task4_charge_series is None:
    print("[WARN] TASK_4 total_event_charge_histogram skipped: no usable event_charge source.")

# Final task-rate plot included in the Task 4 PDF.
# FINAL plot block moved out of the runtime flow: acquisition_rate_vs_time_by_task_tt_with_histograms
pass

# Force PDF creation when Task 4 plotting is enabled.
if create_plots or create_essential_plots:
    create_pdf = False  # Runtime plots are strictly PNG-only.
_finalize_stage_t0 = _t_sec

figure_directory = base_directories["figure_directory"]

if os.path.exists(figure_directory):
    print("Removing figure directory...")
    shutil.rmtree(figure_directory)
_prof["s_pdf_finalize_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()

# Move the original datafile to COMPLETED -------------------------------------
print("Moving file to COMPLETED directory...")

if user_file_selection == False:
    if os.path.exists(file_path):
        safe_move(file_path, completed_file_path)
        now = time.time()
        os.utime(completed_file_path, (now, now))
        print("************************************************************")
        print(f"File moved from\n{file_path}\nto:\n{completed_file_path}")
        print("************************************************************")
    else:
        print(f"Input file already absent (maybe previously processed): {file_path}")
        print("Skipping move; fitted output stays in OUTPUT_FILES.")
_prof["s_file_move_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()

# Store the current time at the end
end_execution_time_counting = datetime.now()
time_taken = (end_execution_time_counting - start_execution_time_counting).total_seconds() / 60
print(f"Time taken for the whole execution: {time_taken:.2f} minutes")

# mark_status_complete(status_csv_path, status_timestamp)

print("----------------------------------------------------------------------")
print("------------------- Finished list_events creation --------------------")
print("----------------------------------------------------------------------\n\n\n")

record_residual_sigmas(working_df)

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
    if "passes_task_4" not in working_df.columns:
        working_df.loc[:, "passes_task_4"] = np.uint8(1)
    working_df.loc[all_zero_mask, "passes_task_4"] = np.uint8(0)
    working_df.loc[:, "filter_task4_all_components_nonzero_pass"] = ~all_zero_mask
    record_filter_metric(
        "all_components_zero_rows_flagged_pct",
        flagged_all_zero,
        len(working_df) if len(working_df) else 0,
    )

# Refresh the trigger columns after any late plane-component changes.
working_df = refresh_task4_trigger_columns(working_df)

# Store TimTrack convergence controls in specific metadata for later studies.
global_variables["timtrack_d0"] = float(d0)
global_variables["timtrack_cocut"] = float(cocut)
global_variables["timtrack_iter_max"] = int(iter_max)

# Store TimTrack convergence outcomes for runout-vs-cut studies.
timtrack_outcome_keys = (
    "timtrack_attempted_fit_n",
    "timtrack_itermax_reached_n",
    "timtrack_itermax_reached_ratio",
    "timtrack_itermax_runout_n",
    "timtrack_itermax_runout_ratio",
    "timtrack_timtrack_converged_on_cocut_n",
    "timtrack_timtrack_converged_on_cocut_ratio",
)

if run_timtrack_fit and {"tim_timtrack_iterations", "tim_timtrack_conv_distance"}.issubset(working_df.columns):
    tim_timtrack_iterations_arr = pd.to_numeric(
        working_df["tim_timtrack_iterations"],
        errors="coerce",
    ).to_numpy(dtype=float)
    tim_timtrack_conv_distance_arr = pd.to_numeric(
        working_df["tim_timtrack_conv_distance"],
        errors="coerce",
    ).to_numpy(dtype=float)

    attempted_mask = np.isfinite(tim_timtrack_iterations_arr) & (tim_timtrack_iterations_arr > 0)
    attempted_count = int(np.count_nonzero(attempted_mask))
    global_variables["timtrack_attempted_fit_n"] = attempted_count

    if attempted_count > 0:
        itermax_reached_mask = attempted_mask & (tim_timtrack_iterations_arr >= float(iter_max))
        timtrack_converged_on_cocut_mask = (
            attempted_mask
            & np.isfinite(tim_timtrack_conv_distance_arr)
            & (tim_timtrack_conv_distance_arr <= float(cocut))
        )
        itermax_runout_mask = itermax_reached_mask & (~timtrack_converged_on_cocut_mask)

        itermax_reached_count = int(np.count_nonzero(itermax_reached_mask))
        itermax_runout_count = int(np.count_nonzero(itermax_runout_mask))
        timtrack_converged_on_cocut_count = int(np.count_nonzero(timtrack_converged_on_cocut_mask))

        global_variables["timtrack_itermax_reached_n"] = itermax_reached_count
        global_variables["timtrack_itermax_reached_ratio"] = (
            itermax_reached_count / attempted_count
        )
        global_variables["timtrack_itermax_runout_n"] = itermax_runout_count
        global_variables["timtrack_itermax_runout_ratio"] = (
            itermax_runout_count / attempted_count
        )
        global_variables["timtrack_timtrack_converged_on_cocut_n"] = timtrack_converged_on_cocut_count
        global_variables["timtrack_timtrack_converged_on_cocut_ratio"] = (
            timtrack_converged_on_cocut_count / attempted_count
        )
    else:
        global_variables["timtrack_itermax_reached_n"] = 0
        global_variables["timtrack_itermax_reached_ratio"] = np.nan
        global_variables["timtrack_itermax_runout_n"] = 0
        global_variables["timtrack_itermax_runout_ratio"] = np.nan
        global_variables["timtrack_timtrack_converged_on_cocut_n"] = 0
        global_variables["timtrack_timtrack_converged_on_cocut_ratio"] = np.nan
else:
    for metadata_key in timtrack_outcome_keys:
        global_variables[metadata_key] = np.nan

# Detached vs TimTrack comparison metadata:
# median( 2 * abs(detached - timtrack) / (detached + timtrack) )
comparison_pairs = {
    "x": ("det_x", "tim_x"),
    "y": ("det_y", "tim_y"),
    "theta": ("det_theta", "tim_theta"),
    "phi": ("det_phi", "tim_phi"),
    "s": ("det_s", "tim_s"),
}

median_relerr_values = []
for metric_name, (det_col, tim_col) in comparison_pairs.items():
    metadata_key = f"fit_compare_median_relerr_{metric_name}"
    if run_detached_fit and run_timtrack_fit and det_col in working_df.columns and tim_col in working_df.columns:
        det_arr = pd.to_numeric(working_df[det_col], errors="coerce").to_numpy(dtype=float)
        tim_arr = pd.to_numeric(working_df[tim_col], errors="coerce").to_numpy(dtype=float)
        denom = det_arr + tim_arr
        relerr = np.divide(
            2.0 * np.abs(det_arr - tim_arr),
            denom,
            out=np.full(det_arr.shape, np.nan, dtype=float),
            where=denom != 0,
        )
        relerr = relerr[np.isfinite(relerr)]
        if relerr.size > 0:
            med_val = float(np.median(relerr))
            global_variables[metadata_key] = med_val
            median_relerr_values.append(med_val)
        else:
            global_variables[metadata_key] = np.nan
    else:
        global_variables[metadata_key] = np.nan

global_variables["fit_compare_mean_error"] = (
    float(np.mean(median_relerr_values)) if median_relerr_values else np.nan
)
if run_detached_fit:
    _store_slowness_relerr_to_sc("fit_compare_median_relerr_detached_s_to_1_over_c", "det_s")
else:
    global_variables["fit_compare_median_relerr_detached_s_to_1_over_c"] = np.nan

if run_timtrack_fit:
    _store_slowness_relerr_to_sc("fit_compare_median_relerr_timtrack_s_to_1_over_c", "tim_s")
else:
    global_variables["fit_compare_median_relerr_timtrack_s_to_1_over_c"] = np.nan

tt_columns_desired = [
    'event_id', 'datetime', 'tt_task0_raw', 'tt_task1_clean', 'tt_task2_cal',
    'tt_task3_list', 'tt_task4_fit', 'tt_task3_list', 'tt_task4_fit'
]
tt_columns_present = [col for col in tt_columns_desired if col in working_df.columns]
param_hash_cols = ["param_hash"] if "param_hash" in working_df.columns else []
upstream_offender_count_cols = [
    col_name
    for col_name in (
        "filter_task1_problematic_channel_count",
        "filter_task1_problematic_channel_exact",
        "filter_task2_problematic_strip_count",
        "filter_task2_problematic_strip_exact",
        "filter_task3_problematic_plane_count",
        "filter_task3_problematic_plane_exact",
    )
    if col_name in working_df.columns
]
task4_pass_filter_cols = [
    col_name
    for col_name in (
        "passes_task_1",
        "passes_task_2",
        "passes_task_3",
        "passes_task_4",
        "filter_task4_final_pass",
        "filter_task4_all_components_nonzero_pass",
    )
    if col_name in working_df.columns
]

columns_to_keep = (
    tt_columns_present
    + param_hash_cols
    + upstream_offender_count_cols
    + task4_pass_filter_cols
    + [
        # New definitions
        'x', 'x_err', 'y', 'y_err', 'theta', 'theta_err', 'phi', 'phi_err', 's', 's_err',
        'tim_th_chi_sigmafit_1234', 'xp', 'yp',

        # Final per-plane detector observables and hit positions
        *[
            f'p{p}_{suffix}'
            for p in range(1, 5)
            for suffix in ('tsum', 'tdif', 'qsum', 'qdif', 'xpos', 'ypos')
        ],

        # Charge

        # # Chisqs
        # 'chi_timtrack', 'chi_alternative',

        # Strip-level time and charge info (ordered by plane and strip)
        *[f'p{p}_s{s}_qsum' for p in range(1, 5) for s in range(1, 5)],

    ]
)

if keep_all_columns_output:
    print(
        "Task 4 keep_all_columns_output enabled: "
        f"retaining full dataframe with {len(working_df.columns)} columns."
    )
else:
    working_df = working_df.filter(items=columns_to_keep)

# Path to save the cleaned dataframe
# Create output directory if it does not exist.
os.makedirs(f"{output_directory}", exist_ok=True)
OUT_PATH = f"{output_directory}/fitted_{basename_no_ext}.parquet"
KEY = "df"  # HDF5 key name

# --- Example: your cleaned DataFrame is called working_df ---
# (Here, you would have your data cleaning code before saving)
# working_df = ...

if VERBOSE:
    print("Columns in the final dataframe:")
    for col in working_df.columns:
        print(f" - {col}")


# def collect_columns(columns: Iterable[str], pattern: re.Pattern[str]) -> list[str]:
#     """Return all column names that match *pattern*."""
#     return [name for name in columns if pattern.match(name)]

# # Pattern for P1_Q_sum_*, P2_Q_sum_*, P3_Q_sum_*, P4_Q_sum_*
# Q_SUM_PATTERN = re.compile(r'^P[1-4]_Q_sum_.*$')

print(f"Original number of events in the dataframe: {original_number_of_events}")
if not globals().get("task4_final_filter_applied", False):
    raise RuntimeError("Task 4 final filtering was not applied before the plotting/output stage.")

tt_task3_list_int = pd.to_numeric(working_df["tt_task3_list"], errors="coerce").fillna(0).to_numpy(dtype=np.int32)
tt_task4_fit_int = pd.to_numeric(working_df["tt_task4_fit"], errors="coerce").fillna(0).to_numpy(dtype=np.int32)

fit_vals, fit_counts = np.unique(tt_task4_fit_int, return_counts=True)
for tt_value, count in zip(fit_vals, fit_counts):
    tt_label = normalize_tt_label(tt_value)
    global_variables[f"tt_task4_fit_{tt_label}_count"] = int(count)

combo_pairs = np.column_stack((tt_task3_list_int, tt_task4_fit_int))
combo_vals, combo_counts = np.unique(combo_pairs, axis=0, return_counts=True)
for (tt_task3_list_value, tt_task4_fit_value), count in zip(combo_vals, combo_counts):
    combo_label = normalize_tt_label(f"{int(tt_task3_list_value)}_{int(tt_task4_fit_value)}")
    global_variables[f"list_to_tt_task4_fit_{combo_label}_count"] = int(count)

# Final number of events
final_number_of_events = len(working_df)
print(f"Final number of events in the dataframe: {final_number_of_events}")
_prof["s_post_fit_filtering_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()

print(
    f"Writing fit parquet: rows={len(working_df)} cols={len(working_df.columns)} -> {OUT_PATH}"
)
if VERBOSE:
    print("Columns before saving list->fit parquet:")
    for col in working_df.columns:
        print(f" - {col}")
# Task 4 uses ``s`` internally and canonicalizes it to ``event_s`` when the
# fitted parquet is written. Store scalar diagnostics under the canonical
# name so the specific metadata schema matches the persisted event variable.
event_s_source_column = next(
    (column_name for column_name in ("event_s", "s") if column_name in working_df.columns),
    None,
)
if event_s_source_column is None:
    event_s_values = np.asarray([], dtype=float)
else:
    event_s_values = pd.to_numeric(
        working_df[event_s_source_column],
        errors="coerce",
    ).to_numpy(dtype=float)
    event_s_values = event_s_values[
        np.isfinite(event_s_values) & (event_s_values != 0.0)
    ]

event_s_median = float(np.median(event_s_values)) if event_s_values.size else np.nan
event_s_std = float(np.std(event_s_values, ddof=0)) if event_s_values.size else np.nan
global_variables["event_s_median"] = event_s_median
global_variables["event_s_std"] = event_s_std
print(
    "Task 4 event_s metadata: "
    f"median={event_s_median:.6g}, "
    f"std={event_s_std:.6g}, "
    f"finite_nonzero_events={event_s_values.size}"
)

print("Rounding the final dataframe values.")
for col in working_df.select_dtypes(include=[np.floating]).columns:
    original_dtype = working_df[col].dtype
    column_values = working_df[col].to_numpy(dtype=float, copy=False)
    rounded_values = round_array_to_significant_digits(column_values, significant_digits=4)
    working_df.loc[:, col] = rounded_values.astype(original_dtype, copy=False)

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

# This line is a placeholder

# -------------------------------------------------------------------------------
# Filter metadata (ancillary) ----------------------------------------------------
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
ensure_global_count_keys(("tt_task3_list", "tt_task4_fit", "list_to_tt_task4_fit"))
chi2_four_plane_bins = np.linspace(0.0, 100.0, 100)
chi2_four_plane_values = np.array([], dtype=float)
if "tim_th_chi_sigmafit_1234" in working_df.columns:
    chi2_series = pd.to_numeric(
        working_df.loc[base_cond, "tim_th_chi_sigmafit_1234"],
        errors="coerce",
    ).to_numpy(dtype=float, copy=False)
    chi2_tt_series = None
    if task4_plot_tt_column in working_df.columns:
        chi2_tt_series = pd.to_numeric(
            working_df.loc[base_cond, task4_plot_tt_column],
            errors="coerce",
        ).to_numpy(dtype=float, copy=False)
    elif "tt_task4_fit" in working_df.columns:
        chi2_tt_series = pd.to_numeric(
            working_df.loc[base_cond, "tt_task4_fit"],
            errors="coerce",
        ).to_numpy(dtype=float, copy=False)
    if chi2_tt_series is not None:
        chi2_series = chi2_series[chi2_tt_series == 1234.0]
        chi2_four_plane_values = chi2_series[np.isfinite(chi2_series) & (chi2_series >= 0.0)]
chi2_four_plane_plot_values = chi2_four_plane_values[chi2_four_plane_values < 100.0]
chi2_four_plane_hist_counts, _ = np.histogram(chi2_four_plane_plot_values, bins=chi2_four_plane_bins)
global_variables["chi2_four_plane_ndf"] = int(global_variables.get("tim_th_chi_sigmafit_1234_ndf", 12))
global_variables["chi2_four_plane_hist_n"] = int(chi2_four_plane_values.size)
global_variables["chi2_four_plane_hist_plot_lt_100_n"] = int(chi2_four_plane_plot_values.size)
global_variables["chi2_four_plane_hist_min"] = float(chi2_four_plane_bins[0])
global_variables["chi2_four_plane_hist_max"] = float(chi2_four_plane_bins[-1])
global_variables["chi2_four_plane_hist_bin_count"] = int(chi2_four_plane_hist_counts.size)
for idx, bin_count in enumerate(chi2_four_plane_hist_counts):
    global_variables[f"chi2_four_plane_bin_{idx:03d}_count"] = int(bin_count)

_chi2_fit_metric_map = (
    ("tim_th_chi_sigmafit_1234_reference_fit_hi", "chi2_four_plane_reference_fit_hi"),
    ("tim_th_chi_sigmafit_1234_reference_fit_total", "chi2_four_plane_reference_fit_total"),
    ("tim_th_chi_sigmafit_1234_unexplained_events_0_12", "chi2_four_plane_unexplained_events_0_12"),
    ("tim_th_chi_sigmafit_1234_signed_difference_0_12", "chi2_four_plane_signed_difference_0_12"),
)
for source_key, target_key in _chi2_fit_metric_map:
    if source_key in global_variables:
        global_variables[target_key] = global_variables[source_key]

add_normalized_count_metadata(
    global_variables,
    global_variables.get("events_per_second_total_seconds", 0),
)
set_global_rate_from_tt_rates(
    global_variables,
    preferred_prefixes=("tt_task4_fit", "tt_task3_list"),
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

efficiency_metadata_row = _flatten_track_based_efficiency_metadata(
    efficiency_metadata_payload,
    filename_base=filename_base,
    execution_timestamp=execution_timestamp,
    param_hash=param_hash_value,
)
metadata_efficiency_csv_path = save_metadata(
    csv_path_efficiency,
    efficiency_metadata_row,
)
print(f"Metadata (efficiency) CSV updated at: {metadata_efficiency_csv_path}")

# Keep denominator available for both trigger_type and specific metadata outputs.
global_variables["count_rate_denominator_seconds"] = rate_histogram_variables.get(
    "count_rate_denominator_seconds",
    0,
)

chi2_four_plane_variables = extract_chi2_four_plane_metadata(
    global_variables,
    remove_from_source=True,
)
chi2_four_plane_variables["count_rate_denominator_seconds"] = rate_histogram_variables.get(
    "count_rate_denominator_seconds",
    0,
)
metadata_chi2_four_plane_csv_path = save_metadata(
    csv_path_chi2_four_plane,
    chi2_four_plane_variables,
)
print(f"Metadata (chi2_four_plane) CSV updated at: {metadata_chi2_four_plane_csv_path}")

prune_redundant_count_metadata(global_variables, log_fn=print)
trigger_type_prefixes = ("tt_task3_list", "tt_task4_fit", "list_to_tt_task4_fit")
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
    stage_tt_columns=("tt_task3_list", "tt_task4_fit"),
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
        (
            is_specific_metadata_excluded_column(column_name)
            and column_name != "count_rate_denominator_seconds"
        )
        or is_trigger_type_metadata_column(column_name, trigger_type_prefixes)
    ),
)
print(f"Metadata (specific) CSV updated at: {metadata_specific_csv_path}")

robust_efficiency_row = _build_robust_efficiency_row(
    efficiency_metadata_payload,
    df_events=working_df,
    denominator_seconds=float(global_variables.get("count_rate_denominator_seconds", 0) or 0),
    filename_base=filename_base,
    execution_timestamp=execution_timestamp,
    param_hash=param_hash_value,
)
print(_format_robust_efficiency_trace_line(robust_efficiency_row), force=True)
metadata_robust_efficiency_csv_path = save_metadata(
    csv_path_robust_efficiency,
    robust_efficiency_row,
    preferred_fieldnames=(
        "filename_base",
        "execution_timestamp",
        "param_hash",
        "robust_efficiency_trigger_source",
        "count_rate_denominator_seconds",
        "eff1",
        "eff1_robust",
        "eff1_robust_method",
        "eff1_robust_xyphi",
        "eff1_robust_xyphi_n_num",
        "eff1_robust_xyphi_n_denom",
        "eff1_plateau",
        "eff1_overall",
        "eff1_median_x",
        "eff1_robust_n_num",
        "eff1_robust_n_denom",
        "eff1_plateau_n_num",
        "eff1_plateau_n_denom",
        "eff1_n_valid_bins",
        "eff1_n_plateau_bins",
        "eff2",
        "eff2_robust",
        "eff2_robust_method",
        "eff2_robust_xyphi",
        "eff2_robust_xyphi_n_num",
        "eff2_robust_xyphi_n_denom",
        "eff2_plateau",
        "eff2_overall",
        "eff2_median_x",
        "eff2_robust_n_num",
        "eff2_robust_n_denom",
        "eff2_plateau_n_num",
        "eff2_plateau_n_denom",
        "eff2_n_valid_bins",
        "eff2_n_plateau_bins",
        "eff3",
        "eff3_robust",
        "eff3_robust_method",
        "eff3_robust_xyphi",
        "eff3_robust_xyphi_n_num",
        "eff3_robust_xyphi_n_denom",
        "eff3_plateau",
        "eff3_overall",
        "eff3_median_x",
        "eff3_robust_n_num",
        "eff3_robust_n_denom",
        "eff3_plateau_n_num",
        "eff3_plateau_n_denom",
        "eff3_n_valid_bins",
        "eff3_n_plateau_bins",
        "eff4",
        "eff4_robust",
        "eff4_robust_method",
        "eff4_robust_xyphi",
        "eff4_robust_xyphi_n_num",
        "eff4_robust_xyphi_n_denom",
        "eff4_plateau",
        "eff4_overall",
        "eff4_median_x",
        "eff4_robust_n_num",
        "eff4_robust_n_denom",
        "eff4_plateau_n_num",
        "eff4_plateau_n_denom",
        "eff4_n_valid_bins",
        "eff4_n_plateau_bins",
        "four_plane_count",
        "four_plane_robust_count",
        "four_plane_robust_count_union",
        "four_plane_robust_count_intersection",
        "total_count",
        "rate_1234_hz",
        "four_plane_robust_hz",
        "four_plane_robust_hz_union",
        "four_plane_robust_hz_intersection",
        "four_plane_robust_efficiency",
        "four_plane_robust_efficiency_union",
        "four_plane_robust_efficiency_intersection",
        "rate_total_hz",
    ),
    replace_existing_basename=True,
)
print(f"Metadata (robust_efficiency) CSV updated at: {metadata_robust_efficiency_csv_path}")
_prof["s_metadata_write_s"] = round(time.perf_counter() - _t_sec, 2)
_t_sec = time.perf_counter()

# Ensure the fitted parquet always carries an event-level total charge for
# downstream TASK_5 / STEP_2 aggregation.
if _task4_charge_series is None:
    _task4_charge_series, _task4_charge_source = _resolve_task4_total_event_charge_series(working_df)
    if _task4_charge_source is not None:
        print(f"TASK_4 event_charge source: {_task4_charge_source}")

if _task4_charge_series is not None:
    working_df["event_charge"] = _task4_charge_series.astype(float)
else:
    print("[WARN] TASK_4 could not persist a usable event_charge column.")

# Ensure no figure handles remain open before persistence/final move.
plt.close("all")

if joined_analysis_active and joined_source_file_column in working_df.columns:
    for joined_record in joined_input_records:
        joined_file_name = joined_record["file_name"]
        joined_basename = joined_record["basename_no_ext"]
        joined_out_path = os.path.join(output_directory, f"fitted_{joined_basename}.parquet")
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
        print(f"Fitted joined-analysis dataframe saved to: {joined_out_path} rows={len(joined_output_df)}")
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
    print(f"Fitted dataframe saved to: {OUT_PATH}")
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
            print(f"Input file already absent (maybe previously processed): {joined_processing_path}")
            print("Skipping move; fitted output stays in OUTPUT_FILES.")

if status_execution_date is not None:
    update_status_progress(
        csv_path_status,
        filename_base=status_filename_base,
        execution_date=status_execution_date,
        completion_fraction=1.0,
        param_hash=str(global_variables.get("param_hash", "")),
    )
_prof["s_save_finish_s"] = round(time.perf_counter() - _t_sec, 2)
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
        csv_path_chi2_four_plane,
        csv_path_efficiency,
        csv_path_robust_efficiency,
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
