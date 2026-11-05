#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_4_REAL_DATA/STEP_4_2_ANALYZE/analyze.py
Purpose: STEP 4.2 - Run inference on real data and attach LUT uncertainties.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_4_REAL_DATA/STEP_4_2_ANALYZE/analyze.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.tri import LinearTriInterpolator, Triangulation
import numpy as np
import pandas as pd

# -- Paths --------------------------------------------------------------------
STEP_DIR = Path(__file__).resolve().parent
# Support both layouts:
#   - <pipeline>/STEP_4_REAL_DATA/STEP_4_2_ANALYZE
#   - <pipeline>/STEPS/STEP_4_REAL_DATA/STEP_4_2_ANALYZE
if STEP_DIR.parents[2].name == "STEPS":
    PIPELINE_DIR = STEP_DIR.parents[3]
else:
    PIPELINE_DIR = STEP_DIR.parents[2]

if (PIPELINE_DIR / "STEP_1_SETUP").exists() and (PIPELINE_DIR / "STEP_2_INFERENCE").exists():
    STEP_ROOT = PIPELINE_DIR
else:
    STEP_ROOT = PIPELINE_DIR / "STEPS"
DEFAULT_CONFIG = (
    STEP_ROOT / "STEP_1_SETUP" / "STEP_1_1_COLLECT_DATA" / "INPUTS" / "config_step_1.1_method.json"
)
CONFIG_COLUMNS_PATH = (
    STEP_ROOT / "STEP_2_INFERENCE" / "STEP_2_1_ESTIMATE_PARAMS" / "INPUTS" / "config_step_2.1_columns.json"
)

INFERENCE_DIR = STEP_ROOT / "STEP_2_INFERENCE"
STEP21_DIR = INFERENCE_DIR / "STEP_2_1_ESTIMATE_PARAMS"

DEFAULT_REAL_COLLECTED = (
    STEP_DIR.parent
    / "STEP_4_1_COLLECT_REAL_DATA"
    / "OUTPUTS"
    / "FILES"
    / "real_collected_data.csv"
)
DEFAULT_DICTIONARY = (
    STEP_ROOT
    / "STEP_1_SETUP"
    / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY"
    / "OUTPUTS"
    / "FILES"
    / "dictionary.csv"
)
DEFAULT_LUT = (
    STEP_ROOT
    / "STEP_2_INFERENCE"
    / "STEP_2_3_UNCERTAINTY"
    / "OUTPUTS"
    / "FILES"
    / "uncertainty_lut.csv"
)
DEFAULT_LUT_META = (
    STEP_ROOT
    / "STEP_2_INFERENCE"
    / "STEP_2_3_UNCERTAINTY"
    / "OUTPUTS"
    / "FILES"
    / "uncertainty_lut_meta.json"
)
DEFAULT_BUILD_SUMMARY = (
    STEP_ROOT
    / "STEP_1_SETUP"
    / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY"
    / "OUTPUTS"
    / "FILES"
    / "build_summary.json"
)
DEFAULT_STEP13_BUILD_SUMMARY = (
    STEP_ROOT
    / "STEP_1_SETUP"
    / "STEP_1_3_BUILD_DICTIONARY"
    / "OUTPUTS"
    / "FILES"
    / "build_summary.json"
)
DEFAULT_STEP12_SELECTED_FEATURE_COLUMNS = (
    STEP_ROOT
    / "STEP_1_SETUP"
    / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY"
    / "OUTPUTS"
    / "FILES"
    / "selected_feature_columns.json"
)
DEFAULT_PARAMETER_SPACE_SPEC = (
    STEP_ROOT
    / "STEP_1_SETUP"
    / "STEP_1_1_COLLECT_DATA"
    / "OUTPUTS"
    / "FILES"
    / "parameter_space_columns.json"
)

FILES_DIR = STEP_DIR / "OUTPUTS" / "FILES"
PLOTS_DIR = STEP_DIR / "OUTPUTS" / "PLOTS"
FILES_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

PLOT_PARAMETER_SERIES = PLOTS_DIR / "STEP_4_2_5_parameter_estimate_series.png"
PLOT_EST_CURVE = PLOTS_DIR / "STEP_4_2_6_estimated_curve_flux_vs_eff.png"
PLOT_RECOVERY_STORY = PLOTS_DIR / "STEP_4_2_7_flux_recovery_vs_global_rate.png"
PLOT_DISTANCE_DOMINANCE = PLOTS_DIR / "STEP_4_2_8_feature_distance_dominance.png"
PLOT_GROUPED_CASE = PLOTS_DIR / "STEP_4_2_9_grouped_case_top_matches.png"
PLOT_INVERSE_PROXY_CASE = PLOTS_DIR / "STEP_4_2_10_inverse_estimate_vs_k1_proxy.png"
PLOT_PARAMETER_SERIES_VS_K1 = PLOTS_DIR / "STEP_4_2_11_parameter_estimate_series_vs_k1.png"
GROUPED_CASE_NEIGHBORS_CSV = FILES_DIR / "step_4_2_grouped_case_top_neighbors.csv"
INVERSE_PROXY_CASE_CSV = FILES_DIR / "step_4_2_inverse_estimate_vs_k1_proxy.csv"

_PLOT_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".pdf",
    ".eps",
    ".tif",
    ".tiff",
    ".bmp",
    ".gif",
    ".webp",
}

logging.basicConfig(format="[%(levelname)s] STEP_4.2 - %(message)s", level=logging.INFO)
log = logging.getLogger("STEP_4.2")

CANONICAL_FLUX_COLUMN = "flux_cm2_min"

MODULES_DIR = STEP_ROOT / "MODULES"
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

# Import estimator directly from STEP_2_INFERENCE.
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))
if str(STEP21_DIR) not in sys.path:
    sys.path.insert(0, str(STEP21_DIR))
try:
    from efficiency_fit_utils import load_efficiency_fit_models  # noqa: E402
    from inference_runtime import (  # noqa: E402
        log_runtime_inverse_mapping_summary,
        parse_column_spec as _shared_parse_column_spec,
        require_selected_feature_columns_present as _shared_require_selected_feature_columns_present,
        resolve_estimation_parameter_columns as _shared_resolve_estimation_parameter_columns,
        resolve_runtime_distance_and_inverse_mapping,
    )
    from uncertainty_lut import (  # noqa: E402
        detect_uncertainty_lut_param_names,
        interpolate_uncertainty_columns,
        load_uncertainty_lut_table,
    )
    from estimate_parameters import (  # noqa: E402
        DERIVED_LOG_RATE_OVER_EFF_PRODUCT_COL,
        _append_derived_physics_feature_columns,
        _append_derived_tt_global_rate_column,
        _derived_feature_columns as _shared_derived_feature_columns,
        _normalize_derived_physics_features,
        estimate_from_dataframes,
        require_explicit_columns_present_in_both_frames,
    )
    from estimate_and_plot import (  # noqa: E402
        _apply_fiducial_overlay,
        _build_grouped_case_payload,
        _select_grouped_diagnostic_case,
    )
    from feature_columns_config import (  # noqa: E402
        parse_explicit_feature_columns,
        resolve_feature_columns_from_catalog,
        sync_feature_column_catalog,
    )
except Exception as exc:
    log.error("Could not import estimate_from_dataframes from %s: %s", INFERENCE_DIR, exc)
    raise


def _clear_plots_dir() -> None:
    """Remove previously generated plot files from the plots directory."""
    removed = 0
    for candidate in PLOTS_DIR.iterdir():
        if candidate.is_file() and candidate.suffix.lower() in _PLOT_EXTENSIONS:
            try:
                candidate.unlink()
                removed += 1
            except OSError as exc:
                log.warning("Could not remove old plot file %s: %s", candidate, exc)
    log.info("Cleared %d plot file(s) from %s", removed, PLOTS_DIR)


def _save_figure(fig: plt.Figure, path: Path, **kwargs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, **kwargs)


def _plot_grouped_case_diagnostic_real(
    *,
    dict_df: pd.DataFrame,
    data_df: pd.DataFrame,
    result_df: pd.DataFrame,
    param_cols: list[str],
    feature_cols: list[str],
    distance_definition: dict | None,
    case_selector: str,
    top_k: int,
    out_path: Path,
    neighbors_csv_path: Path,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "plot_available": False,
        "selector": str(case_selector),
        "row_position": None,
        "dataset_index": None,
        "filename_base": None,
        "top_k": int(max(top_k, 1)),
        "top_neighbor_count": 0,
        "best_distance": None,
        "best_dictionary_index": None,
        "best_dictionary_filename_base": None,
        "histogram_plotted": False,
        "efficiency_vectors_plotted": False,
        "plot_path": str(out_path),
        "neighbors_csv_path": str(neighbors_csv_path),
    }
    if distance_definition is None or not distance_definition.get("feature_groups"):
        return summary

    row_position = _select_grouped_diagnostic_case(
        result_df,
        param_cols,
        selector=case_selector,
    )
    if row_position is None or row_position < 0 or row_position >= len(result_df):
        return summary

    dataset_index_value = pd.to_numeric(
        pd.Series([result_df.iloc[row_position].get("dataset_index")]),
        errors="coerce",
    ).iloc[0]
    data_row_idx = int(dataset_index_value) if pd.notna(dataset_index_value) else int(row_position)
    if data_row_idx < 0 or data_row_idx >= len(data_df):
        return summary

    payload = _build_grouped_case_payload(
        dict_df=dict_df,
        data_df=data_df,
        feature_cols=feature_cols,
        distance_definition=distance_definition,
        row_idx=data_row_idx,
        top_k=max(top_k, 1),
    )
    if not payload:
        return summary

    top_indices = np.asarray(payload["top_indices"], dtype=int)
    if top_indices.size == 0:
        return summary
    best_index = int(payload["best_index"])
    top_distances = np.asarray(payload["top_distances"], dtype=float)

    fig = plt.figure(figsize=(16, 18), constrained_layout=True)
    gs = fig.add_gridspec(5, 3, height_ratios=[1.2, 1.0, 1.0, 1.0, 1.0], hspace=0.35, wspace=0.25)

    hist_payload = payload.get("histogram")
    if isinstance(hist_payload, dict):
        ax_hist = fig.add_subplot(gs[0, :])
        hist_cols = [str(col) for col in hist_payload["columns"]]
        bins = np.asarray([int(col.split("_")[3]) for col in hist_cols], dtype=float)
        sample_hist = np.asarray(hist_payload["sample"], dtype=float)
        dict_hist = np.asarray(hist_payload["dict_matrix"], dtype=float)
        top_hist = dict_hist[top_indices]
        if top_hist.size:
            for curve in top_hist:
                ax_hist.plot(bins, curve, color="0.75", alpha=0.35, lw=0.8, zorder=1)
            if np.isfinite(top_hist).any():
                q10 = np.nanpercentile(top_hist, 10.0, axis=0)
                q90 = np.nanpercentile(top_hist, 90.0, axis=0)
                ax_hist.fill_between(bins, q10, q90, color="0.85", alpha=0.4, zorder=0)
        ax_hist.plot(bins, dict_hist[best_index], color="#E15759", lw=2.0, label="Best dictionary", zorder=3)
        ax_hist.plot(bins, sample_hist, color="black", lw=2.2, label="Real-data row", zorder=4)
        hist_weight = float(hist_payload.get("weight", np.nan))
        hist_status = "active" if bool(hist_payload.get("active", False)) else "inactive"
        hist_title_suffix = (
            f" [{hist_status}, weight={hist_weight:.3g}]"
            if np.isfinite(hist_weight)
            else f" [{hist_status}]"
        )
        ax_hist.set_title(
            f"Rate histogram: real row vs best dictionary vs top-{len(top_indices)} neighbors{hist_title_suffix}",
            fontsize=11,
        )
        ax_hist.set_xlabel("Histogram bin", fontsize=9)
        ax_hist.set_ylabel("Rate [Hz]", fontsize=9)
        ax_hist.grid(True, alpha=0.15)
        ax_hist.legend(fontsize=8, loc="upper right")
        summary["histogram_plotted"] = True

    eff_payload = payload.get("efficiency_vectors")
    if isinstance(eff_payload, dict):
        fiducial = eff_payload["cfg"].get("fiducial", {})
        eff_weight = float(eff_payload.get("weight", np.nan))
        eff_status = "active" if bool(eff_payload.get("active", False)) else "inactive"
        eff_title_suffix = (
            f" [{eff_status}, weight={eff_weight:.3g}]"
            if np.isfinite(eff_weight)
            else f" [{eff_status}]"
        )
        by_label = {str(item.get("label", "")): item for item in eff_payload["payloads"]}
        any_eff_panel = False
        for plane in range(1, 5):
            for col_idx, axis_name in enumerate(("x", "y", "theta")):
                label = f"p{plane}_{axis_name}"
                ax = fig.add_subplot(gs[plane, col_idx])
                item = by_label.get(label)
                if not item:
                    ax.set_axis_off()
                    continue
                any_eff_panel = True
                centers = np.asarray(item["centers"], dtype=float)
                sample_eff = np.asarray(item["data_eff"], dtype=float)[0]
                sample_unc = np.asarray(item["data_unc"], dtype=float)[0]
                dict_eff = np.asarray(item["dict_eff"], dtype=float)[top_indices]
                dict_unc = np.asarray(item["dict_unc"], dtype=float)[top_indices]
                _apply_fiducial_overlay(ax, axis_name, fiducial)
                if dict_eff.size:
                    for curve in dict_eff:
                        ax.plot(centers, curve, color="0.75", alpha=0.35, lw=0.8, zorder=1)
                    if np.isfinite(dict_eff).any():
                        q10 = np.nanpercentile(dict_eff, 10.0, axis=0)
                        q90 = np.nanpercentile(dict_eff, 90.0, axis=0)
                        ax.fill_between(centers, q10, q90, color="0.85", alpha=0.4, zorder=0)
                        best_eff = dict_eff[0]
                        best_unc = dict_unc[0] if dict_unc.ndim == 2 else None
                        ax.plot(centers, best_eff, color="#E15759", lw=1.8, zorder=3)
                        if best_unc is not None:
                            ax.fill_between(
                                centers,
                                np.clip(best_eff - best_unc, 0.0, 1.0),
                                np.clip(best_eff + best_unc, 0.0, 1.0),
                                color="#E15759",
                                alpha=0.12,
                                zorder=2,
                            )
                ax.plot(centers, sample_eff, color="black", lw=2.0, zorder=4)
                ax.fill_between(
                    centers,
                    np.clip(sample_eff - sample_unc, 0.0, 1.0),
                    np.clip(sample_eff + sample_unc, 0.0, 1.0),
                    color="black",
                    alpha=0.10,
                    zorder=3,
                )
                ax.set_title(f"Plane {plane} vs {axis_name}{eff_title_suffix}", fontsize=9)
                ax.set_ylim(0.0, 1.05)
                ax.grid(True, alpha=0.15)
                if plane == 4:
                    ax.set_xlabel("mm" if axis_name in {"x", "y"} else "deg", fontsize=8)
                if col_idx == 0:
                    ax.set_ylabel("Efficiency", fontsize=8)
                ax.tick_params(labelsize=7)
        summary["efficiency_vectors_plotted"] = any_eff_panel

    result_row = result_df.iloc[row_position]
    filename = str(result_row.get("filename_base", f"row_{data_row_idx}"))
    best_distance = pd.to_numeric(pd.Series([result_row.get("best_distance")]), errors="coerce").iloc[0]
    flux_est = pd.to_numeric(pd.Series([result_row.get("est_flux_cm2_min")]), errors="coerce").iloc[0]
    flux_text = f" | flux est={float(flux_est):.4g}" if pd.notna(flux_est) else ""
    distance_text = f"{float(top_distances[0]):.4g}" if top_distances.size else "nan"
    fig.suptitle(
        f"Grouped feature diagnostic case: selector={case_selector} row={row_position} dataset_index={data_row_idx} file={filename}{flux_text}\n"
        f"Top {len(top_indices)} dictionary neighbors: best idx={best_index}, best distance={distance_text}",
        fontsize=12,
        y=0.995,
    )
    _save_figure(fig, out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    neighbor_rows = dict_df.iloc[top_indices].copy()
    neighbor_rows.insert(0, "rank", np.arange(1, len(top_indices) + 1, dtype=int))
    neighbor_rows.insert(1, "dictionary_index", top_indices.astype(int))
    neighbor_rows.insert(2, "distance", top_distances)
    keep_cols = ["rank", "dictionary_index", "distance"]
    if "filename_base" in neighbor_rows.columns:
        keep_cols.append("filename_base")
    keep_cols.extend([col for col in param_cols if col in neighbor_rows.columns])
    neighbor_rows[keep_cols].to_csv(neighbors_csv_path, index=False)

    summary.update(
        {
            "plot_available": True,
            "row_position": int(row_position),
            "dataset_index": int(data_row_idx),
            "filename_base": filename,
            "top_neighbor_count": int(len(top_indices)),
            "best_distance": float(best_distance) if pd.notna(best_distance) else None,
            "best_dictionary_index": int(best_index),
            "best_dictionary_filename_base": (
                str(dict_df.iloc[best_index].get("filename_base"))
                if "filename_base" in dict_df.columns
                else None
            ),
        }
    )
    return summary


def _plot_inverse_estimate_vs_k1_proxy_case(
    *,
    dict_df: pd.DataFrame,
    result_df: pd.DataFrame,
    param_cols: list[str],
    grouped_case_summary: dict[str, object],
    inverse_mapping_cfg: dict[str, object] | None,
    out_path: Path,
    out_csv_path: Path,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "plot_available": False,
        "row_position": None,
        "dataset_index": None,
        "filename_base": None,
        "best_dictionary_index": None,
        "best_dictionary_filename_base": None,
        "plot_path": str(out_path),
        "csv_path": str(out_csv_path),
        "parameter_count": 0,
        "parameters_compared": [],
    }
    if not grouped_case_summary.get("plot_available", False):
        return summary

    row_position = grouped_case_summary.get("row_position")
    best_dictionary_index = grouped_case_summary.get("best_dictionary_index")
    if row_position is None or best_dictionary_index is None:
        return summary
    row_position = int(row_position)
    best_dictionary_index = int(best_dictionary_index)
    if row_position < 0 or row_position >= len(result_df):
        return summary
    if best_dictionary_index < 0 or best_dictionary_index >= len(dict_df):
        return summary

    result_row = result_df.iloc[row_position]
    dict_row = dict_df.iloc[best_dictionary_index]

    comparison_rows: list[dict[str, object]] = []
    for param_name in param_cols:
        est_col = f"est_{param_name}"
        if est_col not in result_row.index or param_name not in dict_row.index:
            continue
        method_value = pd.to_numeric(pd.Series([result_row.get(est_col)]), errors="coerce").iloc[0]
        k1_value = pd.to_numeric(pd.Series([dict_row.get(param_name)]), errors="coerce").iloc[0]
        if pd.isna(method_value) and pd.isna(k1_value):
            continue
        abs_delta = np.nan
        rel_delta_pct = np.nan
        if pd.notna(method_value) and pd.notna(k1_value):
            abs_delta = float(method_value) - float(k1_value)
            denom = max(abs(float(k1_value)), 1e-12)
            rel_delta_pct = 100.0 * abs_delta / denom
        comparison_rows.append(
            {
                "parameter": str(param_name),
                "method_estimate": float(method_value) if pd.notna(method_value) else np.nan,
                "k1_nearest_dictionary_value": float(k1_value) if pd.notna(k1_value) else np.nan,
                "abs_delta_method_minus_k1": abs_delta,
                "rel_delta_method_minus_k1_pct": rel_delta_pct,
            }
        )

    if not comparison_rows:
        return summary

    comparison_df = pd.DataFrame(comparison_rows)
    comparison_df.insert(0, "dataset_index", int(grouped_case_summary.get("dataset_index", row_position)))
    comparison_df.insert(1, "row_position", int(row_position))
    comparison_df.insert(2, "filename_base", str(grouped_case_summary.get("filename_base", f"row_{row_position}")))
    comparison_df.insert(3, "best_dictionary_index", int(best_dictionary_index))
    comparison_df.insert(
        4,
        "best_dictionary_filename_base",
        grouped_case_summary.get("best_dictionary_filename_base"),
    )
    comparison_df.insert(
        5,
        "best_distance",
        float(grouped_case_summary["best_distance"])
        if grouped_case_summary.get("best_distance") is not None
        else np.nan,
    )
    comparison_df.to_csv(out_csv_path, index=False)

    flux_mask = comparison_df["parameter"].astype(str).str.contains("flux", case=False, regex=False)
    eff_mask = comparison_df["parameter"].astype(str).str.contains("eff", case=False, regex=False)
    other_mask = ~(flux_mask | eff_mask)

    panel_specs: list[tuple[str, pd.DataFrame]] = []
    if flux_mask.any():
        panel_specs.append(("Flux", comparison_df.loc[flux_mask].copy()))
    if eff_mask.any():
        panel_specs.append(("Efficiencies", comparison_df.loc[eff_mask].copy()))
    if other_mask.any():
        panel_specs.append(("Other Parameters", comparison_df.loc[other_mask].copy()))
    if not panel_specs:
        panel_specs.append(("Parameters", comparison_df.copy()))

    fig_height = max(4.5, 2.2 * len(panel_specs) + 0.7 * len(comparison_df))
    fig, axes = plt.subplots(
        len(panel_specs),
        1,
        figsize=(11, fig_height),
        constrained_layout=True,
    )
    axes_arr = np.atleast_1d(axes)

    for ax, (title, panel_df) in zip(axes_arr, panel_specs):
        panel_df = panel_df.reset_index(drop=True)
        y = np.arange(len(panel_df), dtype=float)
        method_vals = pd.to_numeric(panel_df["method_estimate"], errors="coerce").to_numpy(dtype=float)
        k1_vals = pd.to_numeric(panel_df["k1_nearest_dictionary_value"], errors="coerce").to_numpy(dtype=float)
        labels = panel_df["parameter"].astype(str).tolist()
        for yi, mv, kv in zip(y, method_vals, k1_vals):
            if np.isfinite(mv) and np.isfinite(kv):
                ax.plot([kv, mv], [yi, yi], color="0.75", lw=1.6, zorder=1)
        ax.scatter(k1_vals, y, color="#E15759", s=60, label="k=1 nearest dictionary", zorder=3)
        ax.scatter(method_vals, y, color="black", s=60, label="Current inverse estimate", zorder=4)
        for yi, (_, row) in zip(y, panel_df.iterrows()):
            rel = pd.to_numeric(pd.Series([row.get("rel_delta_method_minus_k1_pct")]), errors="coerce").iloc[0]
            if pd.notna(rel):
                x_text = max(
                    pd.to_numeric(pd.Series([row.get("method_estimate")]), errors="coerce").iloc[0],
                    pd.to_numeric(pd.Series([row.get("k1_nearest_dictionary_value")]), errors="coerce").iloc[0],
                )
                ax.text(
                    float(x_text),
                    float(yi) + 0.12,
                    f"Δ={float(rel):+.2f}%",
                    fontsize=8,
                    ha="left",
                    va="bottom",
                    color="0.35",
                )
        ax.set_yticks(y, labels)
        ax.set_title(title, fontsize=10)
        ax.grid(True, axis="x", alpha=0.18)
        ax.tick_params(labelsize=8)
        ax.invert_yaxis()
        ax.set_xlabel("Estimated parameter value", fontsize=9)
        if title == panel_specs[0][0]:
            ax.legend(fontsize=8, loc="best")

    agg_label = str((inverse_mapping_cfg or {}).get("aggregation", "unknown"))
    neigh_sel = str((inverse_mapping_cfg or {}).get("neighbor_selection", "unknown"))
    neigh_count = (inverse_mapping_cfg or {}).get("neighbor_count")
    neigh_label = "all" if neigh_sel == "all" or neigh_count is None else str(neigh_count)
    fig.suptitle(
        "Inverse-estimation sanity check for grouped diagnostic case\n"
        f"file={comparison_df['filename_base'].iloc[0]} | best dictionary idx={best_dictionary_index} | "
        f"runtime={agg_label}, selection={neigh_sel}, k={neigh_label}",
        fontsize=12,
        y=1.02,
    )
    _save_figure(fig, out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    summary.update(
        {
            "plot_available": True,
            "row_position": int(row_position),
            "dataset_index": int(comparison_df["dataset_index"].iloc[0]),
            "filename_base": str(comparison_df["filename_base"].iloc[0]),
            "best_dictionary_index": int(best_dictionary_index),
            "best_dictionary_filename_base": comparison_df["best_dictionary_filename_base"].iloc[0],
            "parameter_count": int(len(comparison_df)),
            "parameters_compared": comparison_df["parameter"].astype(str).tolist(),
        }
    )
    return summary


def _load_config(path: Path) -> dict:
    def _merge_dicts(base: dict, override: dict) -> dict:
        out = dict(base)
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = _merge_dicts(out[k], v)
            else:
                out[k] = v
        return out

    cfg: dict = {}
    if path.exists():
        cfg = json.loads(path.read_text(encoding="utf-8"))
    else:
        log.warning("Config file not found: %s", path)

    plots_path = path.with_name("config_step_1.1_plots.json")
    if plots_path != path and plots_path.exists():
        plots_cfg = json.loads(plots_path.read_text(encoding="utf-8"))
        cfg = _merge_dicts(cfg, plots_cfg)
        log.info("Loaded plot config: %s", plots_path)

    runtime_path = path.with_name("config_step_1.1_runtime.json")
    if runtime_path.exists():
        runtime_cfg = json.loads(runtime_path.read_text(encoding="utf-8"))
        cfg = _merge_dicts(cfg, runtime_cfg)
        log.info("Loaded runtime overrides: %s", runtime_path)
    return cfg

def _safe_float(value: object, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float(default)
    if np.isfinite(out):
        return out
    return float(default)


def _safe_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


COMMON_FEATURE_SPACE_KEYS = (
    "feature_columns",
    "derived_features",
    "include_global_rate",
    "global_rate_col",
)


def _merge_common_feature_space_cfg(
    config: dict,
    cfg_21: dict | None = None,
) -> tuple[dict, dict]:
    """Merge top-level common feature-space config with STEP 2.1 overrides."""
    merged: dict = {}
    source_info: dict = {
        "common_keys": [],
        "step_2_1_override_keys": [],
        "has_common_feature_space": False,
    }
    common_cfg = config.get("common_feature_space", {}) if isinstance(config, dict) else {}
    if isinstance(common_cfg, dict):
        source_info["has_common_feature_space"] = True
        for key in COMMON_FEATURE_SPACE_KEYS:
            if key in common_cfg and common_cfg.get(key) is not None:
                merged[key] = common_cfg.get(key)
                source_info["common_keys"].append(key)
    cfg_21_local = cfg_21 if isinstance(cfg_21, dict) else {}
    for key in COMMON_FEATURE_SPACE_KEYS:
        if key in cfg_21_local and cfg_21_local.get(key) is not None:
            merged[key] = cfg_21_local.get(key)
            source_info["step_2_1_override_keys"].append(key)
    cfg_merged = dict(cfg_21_local)
    cfg_merged.update(merged)
    return cfg_merged, source_info


def _safe_int(value: object, default: int, *, minimum: int | None = None) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        out = int(default)
    if minimum is not None:
        out = max(int(minimum), out)
    return out


def _safe_task_ids(raw: object) -> list[int]:
    if raw is None:
        return [1]
    if isinstance(raw, (int, float)):
        return [int(raw)]
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return [1]
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = [x.strip() for x in stripped.split(",") if x.strip()]
        raw = parsed
    out: list[int] = []
    if isinstance(raw, (list, tuple)):
        for value in raw:
            try:
                out.append(int(value))
            except (TypeError, ValueError):
                continue
    return sorted(set(out)) or [1]


def _preferred_tt_prefixes_for_task_ids(task_ids: list[int]) -> list[str]:
    """Preferred TT-rate prefixes for efficiency extraction by most advanced task."""
    max_task_id = max(task_ids) if task_ids else 1
    if max_task_id <= 1:
        return ["raw"]
    if max_task_id == 2:
        return ["clean", "raw_to_clean", "raw"]
    if max_task_id == 3:
        return ["cal", "clean", "raw_to_clean", "raw"]
    if max_task_id == 4:
        return ["list", "list_to_fit", "cal", "clean", "raw_to_clean", "raw"]
    return [
        "corr",
        "task5_to_corr",
        "fit_to_corr",
        "definitive",
        "fit",
        "list_to_fit",
        "list",
        "cal",
        "clean",
        "raw_to_clean",
        "raw",
    ]


def _preferred_feature_prefixes_for_task_ids(task_ids: list[int]) -> list[str]:
    """Preferred TT-rate prefixes for STEP 4.2 auto feature selection."""
    max_task_id = max(task_ids) if task_ids else 1
    if max_task_id <= 1:
        return ["raw", "clean"]
    if max_task_id == 2:
        return ["clean", "raw_to_clean", "raw"]
    if max_task_id == 3:
        return ["cal", "clean", "raw_to_clean", "raw"]
    if max_task_id == 4:
        return ["fit", "list_to_fit", "list", "cal", "clean", "raw_to_clean", "raw"]
    return [
        "post",
        "fit_to_post",
        "fit",
        "list_to_fit",
        "list",
        "cal",
        "clean",
        "raw_to_clean",
        "raw",
        "corr",
        "task5_to_corr",
        "fit_to_corr",
        "definitive",
    ]


def _coalesce(primary: object, fallback: object) -> object:
    if primary in (None, "", "null", "None"):
        return fallback
    return primary


def _resolve_input_path(path_like: str | Path) -> Path:
    p = Path(path_like).expanduser()
    if p.is_absolute():
        return p
    candidate_pipeline = PIPELINE_DIR / p
    if candidate_pipeline.exists():
        return candidate_pipeline
    candidate_step = STEP_DIR / p
    if candidate_step.exists():
        return candidate_step
    return candidate_pipeline


def _load_step12_selected_feature_columns(path: Path) -> tuple[list[str], dict]:
    """Load selected feature-column artifact generated by STEP 1.2."""
    info: dict = {"path": str(path), "exists": bool(path.exists())}
    if not path.exists():
        return [], info
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        info["error"] = str(exc)
        return [], info
    raw_cols = payload.get("selected_feature_columns", [])
    if not isinstance(raw_cols, list):
        info["error"] = "selected_feature_columns_not_list"
        return [], info
    selected = [str(c).strip() for c in raw_cols if str(c).strip()]
    info["selected_count"] = int(len(selected))
    info["selection_strategy"] = payload.get("selection_strategy", None)
    return selected, info


def _resolve_selected_step12_feature_columns_strict(
    selected_feature_columns: list[str],
    *,
    dict_df: pd.DataFrame,
    real_df: pd.DataFrame,
) -> list[str]:
    return _shared_require_selected_feature_columns_present(
        selected_feature_columns,
        dict_df=dict_df,
        data_df=real_df,
        context_label="STEP 4.2",
        right_label="real data",
    )


def _load_parameter_space_spec(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not load parameter-space spec %s: %s", path, exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_parameter_space_columns(path: Path) -> list[str]:
    payload = _load_parameter_space_spec(path)
    if not payload:
        return []
    candidates: list[object] = [
        payload.get("parameter_space_columns_downstream_preferred"),
        payload.get("selected_parameter_space_columns_downstream_preferred"),
        payload.get("selected_parameter_space_columns"),
        payload.get("parameter_space_columns"),
    ]
    out: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        if not isinstance(raw, list):
            continue
        for col in raw:
            if not isinstance(col, str):
                continue
            text = col.strip()
            if not text or text in seen:
                continue
            out.append(text)
            seen.add(text)
        if out:
            break
    return out


def _apply_parameter_space_aliases(df: pd.DataFrame, spec: dict) -> tuple[pd.DataFrame, list[str]]:
    if df.empty or not isinstance(spec, dict):
        return df, []

    raw_aliases = spec.get("parameter_space_column_aliases", {})
    aliases = raw_aliases if isinstance(raw_aliases, dict) else {}
    to_add: dict[str, pd.Series] = {}

    for source_col_raw, target_col_raw in aliases.items():
        source_col = str(source_col_raw).strip()
        target_col = str(target_col_raw).strip()
        if not source_col or not target_col or source_col == target_col:
            continue
        if target_col in df.columns or source_col not in df.columns or target_col in to_add:
            continue
        to_add[target_col] = df[source_col].copy()

    if not to_add:
        return df, []

    alias_df = pd.DataFrame(to_add, index=df.index)
    out = pd.concat([df, alias_df], axis=1)
    return out, sorted(alias_df.columns.tolist())


DEFAULT_PARAMETER_SPACE_PRIORITY = [
    "flux_cm2_min",
    "cos_n",
    "eff_sim_1",
    "eff_sim_2",
    "eff_sim_3",
    "eff_sim_4",
    "eff_empirical_1",
    "eff_empirical_2",
    "eff_empirical_3",
    "eff_empirical_4",
]


def _is_parameter_space_column(name: str) -> bool:
    col = str(name).strip()
    if not col:
        return False
    if col in {"flux_cm2_min", "cos_n"}:
        return True
    if col.startswith("eff_sim_") or col.startswith("eff_empirical_"):
        return True
    return False


def _parse_column_spec(value: object) -> list[str]:
    return _shared_parse_column_spec(value)


def _resolve_estimation_parameter_columns(
    *,
    dictionary_df: pd.DataFrame,
    configured_columns: object = None,
    default_columns: list[str] | None = None,
) -> list[str]:
    return _shared_resolve_estimation_parameter_columns(
        dictionary_df=dictionary_df,
        configured_columns=configured_columns,
        default_columns=default_columns,
        default_priority=DEFAULT_PARAMETER_SPACE_PRIORITY,
        parameter_predicate=_is_parameter_space_column,
        logger=log,
    )


def _find_estimated_parameter_column(df: pd.DataFrame, pname: str) -> str | None:
    for candidate in (f"corrected_{pname}", f"est_{pname}"):
        if candidate in df.columns:
            return candidate
    return None


def _is_efficiency_parameter_column(name: str) -> bool:
    text = str(name).strip().lower()
    return text.startswith("eff_") or "_eff_" in text or text.endswith("_eff") or text.startswith("eff")


def _series_median_or_none(values: object) -> float | None:
    if values is None:
        return None
    series = pd.to_numeric(values, errors="coerce")
    if isinstance(series, pd.Series):
        if not series.notna().any():
            return None
        return float(series.median())
    arr = np.asarray(series, dtype=float)
    if not np.isfinite(arr).any():
        return None
    return float(np.nanmedian(arr))


def _parse_ts(series: pd.Series) -> pd.Series:
    s = series.astype("string")
    parsed = pd.to_datetime(s, format="%Y-%m-%d_%H.%M.%S", errors="coerce", utc=True)
    missing = parsed.isna()
    if missing.any():
        parsed_fallback = pd.to_datetime(s[missing], errors="coerce", utc=True)
        parsed.loc[missing] = parsed_fallback
    return parsed


def _extract_tt_parts(col: str) -> tuple[str, str] | None:
    match = re.match(r"^(?P<prefix>.+?)_tt_(?P<rest>.+)_rate_hz$", col)
    if match is None:
        return None
    rest = match.group("rest")
    # Some task outputs use names like tt_1234.0_rate_hz; normalize to tt_1234_rate_hz.
    rest = re.sub(r"\.0$", "", rest)
    return (match.group("prefix"), f"tt_{rest}_rate_hz")


def _tt_rate_columns(df: pd.DataFrame) -> list[str]:
    return sorted([c for c in df.columns if re.search(r"_tt_.+_rate_hz$", c)])


def _prefix_rank(prefix: str) -> int:
    order = [
        "post",
        "fit",
        "list",
        "cal",
        "clean",
        "raw",
        "corr",
        "definitive",
        "fit_to_post",
        "list_to_fit",
        "raw_to_clean",
        "fit_to_corr",
        "task5_to_corr",
    ]
    try:
        return order.index(prefix)
    except ValueError:
        return len(order)


def _choose_best_col(columns: list[str], df: pd.DataFrame | None = None) -> str:
    scored_physical: list[tuple[int, int, str]] = []
    scored_transition: list[tuple[int, int, str]] = []
    for col in sorted(set(columns)):
        parts = _extract_tt_parts(col)
        rank = _prefix_rank(parts[0]) if parts is not None else 999
        finite_rank = 0
        if df is not None and col in df.columns:
            finite_count = int(pd.to_numeric(df[col], errors="coerce").notna().sum())
            finite_rank = -finite_count
        prefix = parts[0] if parts is not None else ""
        target = scored_transition if "_to_" in prefix else scored_physical
        target.append((finite_rank, rank, col))
    scored = scored_physical or scored_transition
    scored.sort(key=lambda x: (x[0], x[1], x[2]))
    return scored[0][2]


def _count_rows_with_min_finite_features(df: pd.DataFrame, features: list[str], min_finite: int = 2) -> int:
    if not features:
        return 0
    usable_min = min(max(1, int(min_finite)), len(features))
    vals = df[features].apply(pd.to_numeric, errors="coerce")
    return int((vals.notna().sum(axis=1) >= usable_min).sum())


def _resolve_feature_columns_auto(
    dict_df: pd.DataFrame,
    real_df: pd.DataFrame,
    include_global_rate: bool,
    global_rate_col: str,
    preferred_prefixes: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], str, list[dict[str, str]]]:
    """Build a robust feature set even when task prefixes differ."""
    dict_tt = _tt_rate_columns(dict_df)
    real_tt = _tt_rate_columns(real_df)

    feature_mapping: list[dict[str, str]] = []

    # 1) Prefer same-prefix direct intersections (mirrors STEP 2.1 behavior).
    prefixes = [str(p).strip() for p in (preferred_prefixes or []) if str(p).strip()]
    if not prefixes:
        prefixes = ["post", "fit", "list", "cal", "clean", "raw", "corr", "definitive"]
    for prefix in prefixes:
        common = sorted(
            [c for c in dict_tt if c.startswith(f"{prefix}_tt_") and c in set(real_tt)]
        )
        if common:
            features = common.copy()
            if (
                include_global_rate
                and global_rate_col in dict_df.columns
                and global_rate_col in real_df.columns
                and global_rate_col not in features
            ):
                features.append(global_rate_col)
            min_finite = 2 if len(features) >= 2 else 1
            dict_rows_usable = _count_rows_with_min_finite_features(
                dict_df, features, min_finite=min_finite
            )
            real_rows_usable = _count_rows_with_min_finite_features(
                real_df, features, min_finite=min_finite
            )
            if dict_rows_usable <= 0 or real_rows_usable <= 0:
                log.info(
                    "Skipping direct_prefix:%s (usable rows with >=%d finite features: dict=%d, real=%d).",
                    prefix,
                    min_finite,
                    dict_rows_usable,
                    real_rows_usable,
                )
                continue
            log.info(
                "Selected direct_prefix:%s with %d features (usable rows: dict=%d, real=%d).",
                prefix,
                len(features),
                dict_rows_usable,
                real_rows_usable,
            )
            return (
                dict_df,
                real_df,
                features,
                f"direct_prefix:{prefix}",
                feature_mapping,
            )

    # 2) Any exact common tt-rate columns.
    exact_common = sorted(set(dict_tt) & set(real_tt))
    if exact_common:
        features = exact_common.copy()
        if (
            include_global_rate
            and global_rate_col in dict_df.columns
            and global_rate_col in real_df.columns
            and global_rate_col not in features
        ):
            features.append(global_rate_col)
        min_finite = 2 if len(features) >= 2 else 1
        dict_rows_usable = _count_rows_with_min_finite_features(
            dict_df, features, min_finite=min_finite
        )
        real_rows_usable = _count_rows_with_min_finite_features(
            real_df, features, min_finite=min_finite
        )
        if dict_rows_usable > 0 and real_rows_usable > 0:
            log.info(
                "Selected direct_exact with %d features (usable rows: dict=%d, real=%d).",
                len(features),
                dict_rows_usable,
                real_rows_usable,
            )
            return (dict_df, real_df, features, "direct_exact", feature_mapping)
        log.info(
            "Skipping direct_exact (usable rows with >=%d finite features: dict=%d, real=%d).",
            min_finite,
            dict_rows_usable,
            real_rows_usable,
        )

    # 3) Align by tt topology key and create temporary aliases.
    dict_key_to_cols: dict[str, list[str]] = {}
    real_key_to_cols: dict[str, list[str]] = {}

    for col in dict_tt:
        parts = _extract_tt_parts(col)
        if parts is None:
            continue
        key = parts[1]
        dict_key_to_cols.setdefault(key, []).append(col)

    for col in real_tt:
        parts = _extract_tt_parts(col)
        if parts is None:
            continue
        key = parts[1]
        real_key_to_cols.setdefault(key, []).append(col)

    common_keys = sorted(set(dict_key_to_cols) & set(real_key_to_cols))
    if not common_keys:
        raise ValueError(
            "No compatible *_tt_*_rate_hz features found between dictionary and real data."
        )

    dict_work = dict_df.copy()
    real_work = real_df.copy()
    features: list[str] = []
    for idx, key in enumerate(common_keys):
        dcol = _choose_best_col(dict_key_to_cols[key], dict_df)
        rcol = _choose_best_col(real_key_to_cols[key], real_df)
        dvals = pd.to_numeric(dict_df[dcol], errors="coerce")
        rvals = pd.to_numeric(real_df[rcol], errors="coerce")
        if int(dvals.notna().sum()) <= 0 or int(rvals.notna().sum()) <= 0:
            continue
        alias = f"tt_feature_{idx:03d}_rate_hz"
        dict_work[alias] = dvals
        real_work[alias] = rvals
        features.append(alias)
        feature_mapping.append(
            {
                "feature_alias": alias,
                "dictionary_column": dcol,
                "real_column": rcol,
                "tt_key": key,
            }
        )

    if include_global_rate and global_rate_col in dict_df.columns and global_rate_col in real_df.columns:
        alias = "global_rate_feature_hz"
        dict_work[alias] = pd.to_numeric(dict_work[global_rate_col], errors="coerce")
        real_work[alias] = pd.to_numeric(real_work[global_rate_col], errors="coerce")
        features.append(alias)
        feature_mapping.append(
            {
                "feature_alias": alias,
                "dictionary_column": global_rate_col,
                "real_column": global_rate_col,
                "tt_key": "global_rate",
            }
        )

    if not features:
        raise ValueError(
            "No usable aligned tt-rate features found between dictionary and real data."
        )

    min_finite = 2 if len(features) >= 2 else 1
    dict_rows_usable = _count_rows_with_min_finite_features(
        dict_work, features, min_finite=min_finite
    )
    real_rows_usable = _count_rows_with_min_finite_features(
        real_work, features, min_finite=min_finite
    )
    if dict_rows_usable <= 0 or real_rows_usable <= 0:
        raise ValueError(
            "Aligned tt-rate features are not usable: "
            f"dict rows with >={min_finite} finite features={dict_rows_usable}, "
            f"real rows with >={min_finite} finite features={real_rows_usable}."
        )
    log.info(
        "Selected aligned_by_tt_key with %d features (usable rows: dict=%d, real=%d).",
        len(features),
        dict_rows_usable,
        real_rows_usable,
    )

    return (dict_work, real_work, features, "aligned_by_tt_key", feature_mapping)


def _pick_n_events_column(df: pd.DataFrame) -> str | None:
    priority = [
        "n_events",
        "selected_rows",
        "requested_rows",
        "raw_tt_1234_count",
        "clean_tt_1234_count",
        "list_tt_1234_count",
        "fit_tt_1234_count",
        "corr_tt_1234_count",
        "definitive_tt_1234_count",
        "events_per_second_total_seconds",
    ]
    for col in priority:
        if col in df.columns:
            values = pd.to_numeric(df[col], errors="coerce")
            if values.notna().any():
                return col

    patt = re.compile(r"_tt_1234(?:\.0)?_count$")
    for col in sorted([c for c in df.columns if patt.search(c)]):
        values = pd.to_numeric(df[col], errors="coerce")
        if values.notna().any():
            return col
    return None


def _normalize_tt_label(label: object) -> str:
    text = str(label).strip()
    if not text:
        return ""
    try:
        value = float(text)
    except (TypeError, ValueError):
        return text
    if not np.isfinite(value):
        return ""
    if float(value).is_integer():
        return str(int(value))
    return text


def _derive_global_rate_from_tt_sum(
    df: pd.DataFrame,
    *,
    target_col: str = "events_per_second_global_rate",
) -> str | None:
    canonical_labels = {
        "0",
        "1",
        "2",
        "3",
        "4",
        "12",
        "13",
        "14",
        "23",
        "24",
        "34",
        "123",
        "124",
        "134",
        "234",
        "1234",
    }
    by_prefix: dict[str, list[str]] = {}
    for col in df.columns:
        match = re.match(r"^(?P<prefix>.+_tt)_(?P<label>[^_]+)_rate_hz$", str(col))
        if match is None:
            continue
        prefix = str(match.group("prefix")).strip()
        label = _normalize_tt_label(match.group("label"))
        if label not in canonical_labels:
            continue
        by_prefix.setdefault(prefix, []).append(col)

    if not by_prefix:
        return None

    selected_prefix = min(
        by_prefix.keys(),
        key=lambda p: (-len(by_prefix[p]), _prefix_rank(p.replace("_tt", "")), p),
    )
    cols = sorted(set(by_prefix[selected_prefix]))
    if not cols:
        return None

    summed = pd.Series(0.0, index=df.index, dtype=float)
    valid_any = pd.Series(False, index=df.index)
    for col in cols:
        numeric = pd.to_numeric(df[col], errors="coerce")
        summed = summed + numeric.fillna(0.0)
        valid_any = valid_any | numeric.notna()

    df[target_col] = summed.where(valid_any, np.nan)
    return target_col


def _pick_global_rate_column(df: pd.DataFrame, preferred: str = "events_per_second_global_rate") -> str | None:
    if preferred in df.columns:
        vals = pd.to_numeric(df[preferred], errors="coerce")
        if vals.notna().any():
            return preferred

    candidates = []
    for c in df.columns:
        cl = c.lower()
        if "global_rate" in cl and ("hz" in cl or cl.endswith("_rate")):
            candidates.append(c)
    for c in sorted(candidates):
        vals = pd.to_numeric(df[c], errors="coerce")
        if vals.notna().any():
            return c
    return _derive_global_rate_from_tt_sum(df, target_col="events_per_second_global_rate")


def _find_tt_rate_column(
    df: pd.DataFrame,
    tt_code: str,
    preferred_prefixes: list[str] | None = None,
) -> str | None:
    pattern = re.compile(rf"_tt_{re.escape(tt_code)}(?:\.0)?_rate_hz$")
    candidates = [c for c in df.columns if pattern.search(c)]
    if not candidates:
        return None
    preferred_order: dict[str, int] = {}
    if preferred_prefixes:
        preferred_order = {str(p): i for i, p in enumerate(preferred_prefixes)}

    def _sort_key(col: str) -> tuple[int, int, str]:
        parts = _extract_tt_parts(col)
        prefix = parts[0] if parts is not None else ""
        pref_rank = preferred_order.get(prefix, len(preferred_order) + 100)
        base_rank = _prefix_rank(prefix) if parts is not None else 999
        return (pref_rank, base_rank, col)

    candidates = sorted(candidates, key=_sort_key)
    for c in candidates:
        vals = pd.to_numeric(df[c], errors="coerce")
        if vals.notna().any():
            return c
    return candidates[0]


def _compute_eff_from_rates(
    df: pd.DataFrame,
    *,
    col_missing_rate: str | None,
    col_1234_rate: str | None,
) -> tuple[pd.Series, str]:
    if col_missing_rate is None or col_1234_rate is None:
        return (pd.Series(np.nan, index=df.index), "missing_rate_columns")

    r_miss = pd.to_numeric(df[col_missing_rate], errors="coerce")
    r_1234 = pd.to_numeric(df[col_1234_rate], errors="coerce")
    # Empirical efficiency definition consistent with STEP 1.2 dictionary:
    #   eff = N(1234) / ( N(1234) + N(three-plane-missing-i) )
    # This keeps efficiencies bounded in [0, 1] for non-negative rates.
    denom = (r_1234 + r_miss).replace({0.0: np.nan})
    eff = r_1234 / denom
    eff = eff.where(np.isfinite(eff), np.nan)
    return (eff, f"{col_1234_rate}/({col_1234_rate} + {col_missing_rate})")


def _compute_empirical_efficiencies_from_rates(
    df: pd.DataFrame,
) -> tuple[dict[int, pd.Series], dict[int, str], dict[int, dict[str, str | None]], str | None]:
    """Compute plane efficiencies from four/(four+three-missing) using TT rates."""
    preferred_prefixes: list[str] | None = None
    if isinstance(df.attrs.get("preferred_tt_prefixes"), list):
        preferred_prefixes = [str(v) for v in df.attrs.get("preferred_tt_prefixes", [])]

    four_col = _find_tt_rate_column(df, "1234", preferred_prefixes=preferred_prefixes)
    miss_by_plane = {1: "234", 2: "134", 3: "124", 4: "123"}

    selected_prefix: str | None = None
    four_parts = _extract_tt_parts(four_col) if four_col is not None else None
    if four_parts is not None:
        selected_prefix = four_parts[0]

    eff_by_plane: dict[int, pd.Series] = {}
    formula_by_plane: dict[int, str] = {}
    cols_by_plane: dict[int, dict[str, str | None]] = {}
    for plane, miss_code in miss_by_plane.items():
        miss_col = _find_tt_rate_column(df, miss_code, preferred_prefixes=preferred_prefixes)
        eff, formula = _compute_eff_from_rates(
            df,
            col_missing_rate=miss_col,
            col_1234_rate=four_col,
        )
        eff_by_plane[plane] = eff
        formula_by_plane[plane] = formula
        cols_by_plane[plane] = {
            "three_plane_col": miss_col,
            "four_plane_col": four_col,
        }
    return (eff_by_plane, formula_by_plane, cols_by_plane, selected_prefix)


def _compute_efficiency_vector_median_proxies(
    df: pd.DataFrame,
) -> tuple[dict[int, pd.Series], dict[int, dict[str, object]]]:
    """Per-plane median over available efficiency-vector bins as a proxy only."""
    by_plane: dict[int, list[str]] = {1: [], 2: [], 3: [], 4: []}
    pattern = re.compile(r"^efficiency_vector_p(?P<plane>\d+)_[^_]+_bin_\d+_eff$")
    for col in df.columns:
        match = pattern.match(str(col))
        if match is None:
            continue
        plane = int(match.group("plane"))
        if plane in by_plane:
            by_plane[plane].append(str(col))

    proxy_by_plane: dict[int, pd.Series] = {}
    meta_by_plane: dict[int, dict[str, object]] = {}
    for plane in (1, 2, 3, 4):
        cols = sorted(by_plane.get(plane, []))
        if cols:
            numeric = df[cols].apply(pd.to_numeric, errors="coerce")
            proxy_by_plane[plane] = numeric.median(axis=1, skipna=True)
        else:
            proxy_by_plane[plane] = pd.Series(np.nan, index=df.index, dtype=float)
        meta_by_plane[plane] = {
            "proxy_kind": "median_over_available_efficiency_vector_bins",
            "columns": cols,
            "columns_count": int(len(cols)),
        }
    return (proxy_by_plane, meta_by_plane)


def _format_polynomial_expr(
    coeffs: np.ndarray | list[float] | tuple[float, ...],
    *,
    variable: str = "x",
    precision: int = 6,
) -> str:
    """Return compact polynomial expression from highest to lowest degree."""
    arr = np.asarray(coeffs, dtype=float)
    if arr.size == 0 or not np.isfinite(arr).all():
        return "invalid"
    degree = arr.size - 1
    parts: list[tuple[str, str]] = []
    for idx, coef in enumerate(arr):
        if abs(float(coef)) < 1e-14:
            continue
        power = degree - idx
        mag = f"{abs(float(coef)):.{precision}g}"
        if power == 0:
            term = mag
        elif power == 1:
            term = variable if np.isclose(abs(float(coef)), 1.0) else f"{mag}{variable}"
        else:
            term = f"{variable}^{power}" if np.isclose(abs(float(coef)), 1.0) else f"{mag}{variable}^{power}"
        sign = "-" if coef < 0 else "+"
        parts.append((sign, term))
    if not parts:
        return "0"
    first_sign, first_term = parts[0]
    expr = f"-{first_term}" if first_sign == "-" else first_term
    for sign, term in parts[1:]:
        expr += f" {sign} {term}"
    return expr


def _invert_polynomial_values(
    y_values: pd.Series,
    coeffs: np.ndarray,
) -> pd.Series:
    """Solve P(x)=y row-wise with physical-root preference and smooth fallback.

    Prefer real roots within [0, 1] (efficiency domain). When no physical root
    exists, fall back to nearby real roots instead of hard clipping to bounds.
    """
    y = pd.to_numeric(y_values, errors="coerce").to_numpy(dtype=float)
    out = np.full(y.shape, np.nan, dtype=float)
    degree = int(len(coeffs) - 1)

    x_grid = np.linspace(-0.5, 1.5, 8001, dtype=float)
    y_grid = np.polyval(coeffs, x_grid)

    def _distance_to_unit_interval(values: np.ndarray) -> np.ndarray:
        vals = np.asarray(values, dtype=float)
        return np.where(vals < 0.0, -vals, np.where(vals > 1.0, vals - 1.0, 0.0))

    if degree == 1:
        a, b = float(coeffs[0]), float(coeffs[1])
        if np.isfinite(a) and abs(a) >= 1e-12:
            out = (y - b) / a
            out[~np.isfinite(out)] = np.nan
        return pd.Series(out, index=y_values.index)

    for idx, target in enumerate(y):
        if not np.isfinite(target):
            continue
        coeff_eq = coeffs.copy()
        coeff_eq[-1] -= float(target)
        try:
            roots = np.roots(coeff_eq)
        except Exception:
            continue
        if roots.size == 0:
            continue
        real_mask = np.isfinite(roots.real) & np.isfinite(roots.imag) & (np.abs(roots.imag) < 1e-8)
        real_roots = roots.real[real_mask]
        if real_roots.size == 0:
            idx_best = int(np.argmin(np.abs(y_grid - target)))
            out[idx] = float(x_grid[idx_best])
            continue
        physical_roots = real_roots[(real_roots >= 0.0) & (real_roots <= 1.0)]
        if physical_roots.size > 0:
            clipped_target = float(np.clip(target, 0.0, 1.0))
            order = np.lexsort(
                (
                    np.abs(physical_roots - 0.5),
                    np.abs(physical_roots - clipped_target),
                )
            )
            out[idx] = float(physical_roots[int(order[0])])
            continue
        # No physical root: keep transformation behavior via nearest real root
        # to the physical interval, instead of forcing boundary clipping.
        dist = _distance_to_unit_interval(real_roots)
        order = np.lexsort((np.abs(real_roots), np.abs(real_roots - 0.5), dist))
        out[idx] = float(real_roots[int(order[0])])
    return pd.Series(out, index=y_values.index)


def _load_eff_fit_lines(summary_path: Path) -> tuple[dict[int, list[float]], str, dict]:
    """Load efficiency-fit coefficients from STEP 1.3/legacy summary structures."""
    fit_models, fit_status, payload = load_efficiency_fit_models(summary_path)
    out: dict[int, list[float]] = {}
    for plane, model in fit_models.items():
        raw = model.get("coefficients_desc")
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        coeffs: list[float] = []
        valid = True
        for value in raw:
            c = _safe_float(value, np.nan)
            if not np.isfinite(c):
                valid = False
                break
            coeffs.append(float(c))
        if valid:
            out[int(plane)] = coeffs
    status = "ok" if out else fit_status
    return (out, status, payload if isinstance(payload, dict) else {})


def _summary_has_efficiency_calibration(payload: dict | object) -> bool:
    if not isinstance(payload, dict):
        return False
    efficiency_fit = payload.get("efficiency_fit", {})
    if isinstance(efficiency_fit, dict):
        models = efficiency_fit.get("models", {})
        if isinstance(models, dict) and any(models.get(f"plane_{plane}") for plane in (1, 2, 3, 4)):
            return True
    for plane in (1, 2, 3, 4):
        if payload.get(f"fit_line_eff_{plane}") is not None:
            return True
        if payload.get(f"fit_poly_eff_{plane}") is not None:
            return True
        if payload.get(f"isotonic_calibration_eff_{plane}") is not None:
            return True
    return False


def _resolve_efficiency_calibration_summary_path(
    preferred_path: Path,
    *,
    fallback_path: Path | None = None,
) -> tuple[Path, str, dict]:
    """Choose the summary artifact that actually carries efficiency calibration metadata."""
    candidate_paths: list[Path] = [preferred_path]
    if fallback_path is not None and fallback_path != preferred_path:
        candidate_paths.append(fallback_path)

    last_payload: dict = {}
    for idx, path in enumerate(candidate_paths):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        last_payload = payload if isinstance(payload, dict) else {}
        if _summary_has_efficiency_calibration(last_payload):
            reason = "preferred_contains_efficiency_calibration" if idx == 0 else "fallback_contains_efficiency_calibration"
            return path, reason, last_payload

    return preferred_path, "no_summary_with_efficiency_calibration", last_payload


def _load_isotonic_calibration(
    summary_path: Path,
) -> tuple[dict[int, dict], str]:
    """Load isotonic calibration knots from STEP 1.2 build_summary.json."""
    if not summary_path.exists():
        return ({}, f"missing:{summary_path}")
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ({}, f"invalid_json:{exc}")

    out: dict[int, dict] = {}
    for plane in (1, 2, 3, 4):
        raw = payload.get(f"isotonic_calibration_eff_{plane}")
        if not isinstance(raw, dict):
            continue
        x_knots = raw.get("x_knots")
        y_knots = raw.get("y_knots")
        if (
            not isinstance(x_knots, list)
            or not isinstance(y_knots, list)
            or len(x_knots) < 2
            or len(x_knots) != len(y_knots)
        ):
            continue
        try:
            xk = np.array(x_knots, dtype=float)
            yk = np.array(y_knots, dtype=float)
        except (TypeError, ValueError):
            continue
        if not (np.all(np.isfinite(xk)) and np.all(np.isfinite(yk))):
            continue
        out[plane] = {
            "x_knots": xk,
            "y_knots": yk,
            "slope_lo": _safe_float(raw.get("slope_lo"), 1.0),
            "slope_hi": _safe_float(raw.get("slope_hi"), 1.0),
            "x_min": _safe_float(raw.get("x_min"), float(xk[0])),
            "x_max": _safe_float(raw.get("x_max"), float(xk[-1])),
        }
    status = "ok" if out else "no_isotonic_data"
    return (out, status)


def _transform_efficiencies_isotonic(
    eff_by_plane: dict[int, pd.Series],
    isotonic_by_plane: dict[int, dict],
) -> tuple[dict[int, pd.Series], dict[int, str]]:
    """Apply isotonic (piecewise-linear monotonic) calibration per plane.

    For values within the calibration support, uses np.interp on the stored knots.
    For values outside the support, uses monotonic asymptotic extrapolation with
    boundary-matched derivatives, which avoids hard boundary pile-up artifacts.
    """
    transformed: dict[int, pd.Series] = {}
    formula: dict[int, str] = {}
    for plane in (1, 2, 3, 4):
        raw = pd.to_numeric(eff_by_plane.get(plane), errors="coerce")
        if plane not in isotonic_by_plane:
            transformed[plane] = pd.Series(np.nan, index=raw.index)
            formula[plane] = "missing_isotonic_calibration"
            continue
        cal = isotonic_by_plane[plane]
        xk = cal["x_knots"]
        yk = cal["y_knots"]
        x_min = cal["x_min"]
        x_max = cal["x_max"]
        slope_lo = cal["slope_lo"]
        slope_hi = cal["slope_hi"]

        x = raw.to_numpy(dtype=float)
        y = np.full_like(x, np.nan, dtype=float)
        finite = np.isfinite(x)

        # Interior: piecewise-linear interpolation
        interior = finite & (x >= x_min) & (x <= x_max)
        if np.any(interior):
            y[interior] = np.interp(x[interior], xk, yk)

        y_lo = float(yk[0])
        y_hi = float(yk[-1])

        # Extrapolation below support: monotonic asymptote toward 0 with
        # derivative matched to boundary slope.
        below = finite & (x < x_min)
        if np.any(below):
            if slope_lo > 0.0 and y_lo > 1e-8:
                k_lo = slope_lo / max(y_lo, 1e-8)
                y[below] = y_lo * np.exp(k_lo * (x[below] - x_min))
            else:
                y[below] = y_lo

        # Extrapolation above support: monotonic asymptote toward 1 with
        # derivative matched to boundary slope.
        above = finite & (x > x_max)
        if np.any(above):
            headroom = max(1.0 - y_hi, 1e-8)
            if slope_hi > 0.0 and headroom > 1e-8:
                k_hi = slope_hi / headroom
                y[above] = 1.0 - headroom * np.exp(-k_hi * (x[above] - x_max))
            else:
                y[above] = y_hi

        # Soft physical bound: clip to [0, 1]
        y = np.clip(y, 0.0, 1.0)

        transformed[plane] = pd.Series(y, index=raw.index)
        n_knots = len(xk)
        formula[plane] = (
            f"isotonic_piecewise_linear({n_knots} knots), "
            f"domain=[{x_min:.6g},{x_max:.6g}], "
            f"range=[{float(yk[0]):.6g},{float(yk[-1]):.6g}], "
            f"extrap_slope=[{slope_lo:.4g},{slope_hi:.4g}], "
            "extrap=asymptotic_monotonic"
        )
    return (transformed, formula)


def _resolve_eff_transform_mode(
    requested_mode: str,
    fit_summary_payload: dict,
) -> tuple[str, str]:
    """Resolve transform mode from config request and STEP 1.2 fit relation metadata."""
    mode = str(requested_mode).strip().lower()
    if mode in {"inverse", "forward"}:
        return (mode, f"config:{mode}")
    if mode != "auto":
        mode = "auto"

    relation_raw = str(fit_summary_payload.get("fit_polynomial_relation", "")).strip()
    relation_norm = re.sub(r"\s+", "", relation_raw.lower())
    x_var = str(fit_summary_payload.get("fit_polynomial_x_variable", "")).strip().lower()
    y_var = str(fit_summary_payload.get("fit_polynomial_y_variable", "")).strip().lower()

    if "simulated=p(empirical)" in relation_norm:
        return ("forward", "summary_relation:simulated=P(empirical)")
    if "empirical=p(simulated)" in relation_norm:
        return ("inverse", "summary_relation:empirical=P(simulated)")
    if "empirical" in x_var and "simulated" in y_var:
        return ("forward", "summary_axes:x=empirical,y=simulated")
    if "simulated" in x_var and "empirical" in y_var:
        return ("inverse", "summary_axes:x=simulated,y=empirical")

    # Legacy STEP 1.2 summaries did not store relation metadata.
    return ("inverse", "fallback_legacy_inverse(no_relation_metadata)")


def _read_fit_order_info(summary_path: Path) -> tuple[int | None, dict[str, int]]:
    if not summary_path.exists():
        return (None, {})
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return (None, {})
    efficiency_fit = payload.get("efficiency_fit", {}) if isinstance(payload, dict) else {}
    requested_raw = payload.get("fit_polynomial_order_requested")
    if requested_raw is None and isinstance(efficiency_fit, dict):
        requested_raw = efficiency_fit.get("polynomial_order_requested")
    requested: int | None = None
    try:
        if requested_raw is not None:
            requested = int(requested_raw)
    except (TypeError, ValueError):
        requested = None

    used_by_plane: dict[str, int] = {}
    raw_used = payload.get("fit_polynomial_order_by_plane", {})
    if (not isinstance(raw_used, dict) or not raw_used) and isinstance(efficiency_fit, dict):
        models = efficiency_fit.get("models", {})
        if isinstance(models, dict):
            raw_used = {
                str(plane): model.get("order_used")
                for plane, model in (
                    (str(k).replace("plane_", ""), v)
                    for k, v in models.items()
                    if isinstance(v, dict)
                )
            }
    if isinstance(raw_used, dict):
        for k, v in raw_used.items():
            try:
                used_by_plane[str(k)] = int(v)
            except (TypeError, ValueError):
                continue
    return (requested, used_by_plane)


def _transform_efficiencies_with_fits(
    eff_by_plane: dict[int, pd.Series],
    fit_by_plane: dict[int, list[float]],
    *,
    mode: str = "forward",
    input_domain_by_plane: dict[int, tuple[float, float]] | None = None,
    clip_output_to_unit_interval: bool = False,
) -> tuple[dict[int, pd.Series], dict[int, str]]:
    """Apply polynomial fit transform per plane.

    Fits are from STEP 1.2 and can represent either:
    - empirical = P(simulated)  -> use mode='inverse'
    - simulated = P(empirical)  -> use mode='forward'
    """
    transformed: dict[int, pd.Series] = {}
    formula: dict[int, str] = {}
    use_inverse = str(mode).strip().lower() != "forward"
    for plane in (1, 2, 3, 4):
        raw = pd.to_numeric(eff_by_plane.get(plane), errors="coerce")
        raw_eval = raw.copy()
        domain_note = ""
        if input_domain_by_plane is not None and plane in input_domain_by_plane:
            dom_raw = input_domain_by_plane.get(plane)
            if isinstance(dom_raw, (list, tuple)) and len(dom_raw) == 2:
                lo = _safe_float(dom_raw[0], np.nan)
                hi = _safe_float(dom_raw[1], np.nan)
                if np.isfinite(lo) and np.isfinite(hi):
                    if hi < lo:
                        lo, hi = hi, lo
                    raw_eval = raw_eval.clip(lower=float(lo), upper=float(hi))
                    domain_note = f"; x_clipped_to_[{float(lo):.6g},{float(hi):.6g}]"
        if plane not in fit_by_plane:
            transformed[plane] = pd.Series(np.nan, index=raw.index)
            formula[plane] = "missing_fit_polynomial"
            continue
        coeffs = np.asarray(fit_by_plane[plane], dtype=float)
        if coeffs.ndim != 1 or coeffs.size < 2 or not np.isfinite(coeffs).all():
            transformed[plane] = pd.Series(np.nan, index=raw.index)
            formula[plane] = "invalid_fit_polynomial"
            continue
        degree = int(coeffs.size - 1)
        poly_expr = _format_polynomial_expr(coeffs, variable="x", precision=8)
        if use_inverse:
            corr = _invert_polynomial_values(raw_eval, coeffs)
            formula[plane] = (
                f"inverse_root(P(x)=eff_raw_empirical), deg={degree}, P(x)={poly_expr}{domain_note}"
            )
        else:
            corr = pd.Series(np.polyval(coeffs, raw_eval.to_numpy(dtype=float)), index=raw.index)
            formula[plane] = f"P(eff_raw_empirical), deg={degree}, P(x)={poly_expr}{domain_note}"
        corr = corr.where(np.isfinite(corr), np.nan)
        if clip_output_to_unit_interval:
            corr = corr.clip(lower=0.0, upper=1.0)
            formula[plane] = f"{formula[plane]}; y_clipped_to_[0,1]"
        transformed[plane] = corr
    return (transformed, formula)


def _fraction_in_closed_interval(series: pd.Series, lo: float, hi: float) -> float:
    """Fraction of finite values inside [lo, hi]. Returns 0 when no finite values."""
    s = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    m = np.isfinite(s)
    if not np.any(m):
        return 0.0
    vals = s[m]
    return float(np.mean((vals >= float(lo)) & (vals <= float(hi))))


def _boundary_fraction_metrics(
    series: pd.Series,
    *,
    near_tol: float = 0.01,
    atol: float = 1e-10,
) -> dict[str, float]:
    """Compact boundary/saturation diagnostics for a numeric series."""
    s = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    m = np.isfinite(s)
    if not np.any(m):
        return {
            "near_low_fraction": 0.0,
            "near_high_fraction": 0.0,
            "exact_min_fraction": 0.0,
            "exact_max_fraction": 0.0,
            "n_unique_rounded_1e6": 0.0,
        }
    vals = s[m]
    vmin = float(np.nanmin(vals))
    vmax = float(np.nanmax(vals))
    return {
        "near_low_fraction": float(np.mean(vals <= float(near_tol))),
        "near_high_fraction": float(np.mean(vals >= 1.0 - float(near_tol))),
        "exact_min_fraction": float(np.mean(np.isclose(vals, vmin, atol=atol))),
        "exact_max_fraction": float(np.mean(np.isclose(vals, vmax, atol=atol))),
        "n_unique_rounded_1e6": float(len(np.unique(np.round(vals, 6)))),
    }


def _build_rate_model(
    *,
    flux: pd.Series,
    eff: pd.Series,
    rate: pd.Series,
) -> dict | None:
    x = pd.to_numeric(flux, errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(eff, errors="coerce").to_numpy(dtype=float)
    z = pd.to_numeric(rate, errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    if int(mask.sum()) < 1:
        return None
    x = x[mask]
    y = y[mask]
    z = z[mask]
    tri = None
    interp = None
    try:
        tri = Triangulation(x, y)
        interp = LinearTriInterpolator(tri, z)
    except Exception:
        tri = None
        interp = None
    return {
        "x": x,
        "y": y,
        "z": z,
        "tri": tri,
        "interp": interp,
        "flux_min": float(np.nanmin(x)),
        "flux_max": float(np.nanmax(x)),
        "eff_min": float(np.nanmin(y)),
        "eff_max": float(np.nanmax(y)),
    }


def _predict_rate(
    model: dict,
    flux_values: np.ndarray,
    eff_values: np.ndarray,
) -> np.ndarray:
    xq = np.asarray(flux_values, dtype=float)
    yq = np.asarray(eff_values, dtype=float)
    qx = xq.ravel()
    qy = yq.ravel()
    zq = np.full_like(qx, np.nan, dtype=float)

    interp = model.get("interp")
    if interp is not None:
        zi = interp(qx, qy)
        zq = np.asarray(np.ma.filled(zi, np.nan), dtype=float)

    missing = ~np.isfinite(zq)
    if missing.any():
        x = np.asarray(model["x"], dtype=float)
        y = np.asarray(model["y"], dtype=float)
        z = np.asarray(model["z"], dtype=float)
        qx_m = qx[missing]
        qy_m = qy[missing]
        out = np.empty(len(qx_m), dtype=float)
        chunk = 4096
        for s in range(0, len(qx_m), chunk):
            e = min(len(qx_m), s + chunk)
            dx = qx_m[s:e, None] - x[None, :]
            dy = qy_m[s:e, None] - y[None, :]
            idx = np.argmin(dx * dx + dy * dy, axis=1)
            out[s:e] = z[idx]
        zq[missing] = out
    return zq.reshape(xq.shape)


def _ordered_row_indices(df: pd.DataFrame, valid_mask: pd.Series) -> np.ndarray:
    valid_idx = np.where(valid_mask.to_numpy(dtype=bool))[0]
    if len(valid_idx) == 0:
        return valid_idx
    if "file_timestamp_utc" in df.columns:
        ts = pd.to_datetime(df.loc[valid_mask, "file_timestamp_utc"], errors="coerce", utc=True)
        if ts.notna().any():
            ts_ns = ts.astype("int64").to_numpy(dtype=np.int64, copy=False)
            ts_ns = np.where(ts.notna().to_numpy(), ts_ns, np.iinfo(np.int64).max)
            return valid_idx[np.argsort(ts_ns)]
    if "execution_timestamp_utc" in df.columns:
        ts = pd.to_datetime(df.loc[valid_mask, "execution_timestamp_utc"], errors="coerce", utc=True)
        if ts.notna().any():
            ts_ns = ts.astype("int64").to_numpy(dtype=np.int64, copy=False)
            ts_ns = np.where(ts.notna().to_numpy(), ts_ns, np.iinfo(np.int64).max)
            return valid_idx[np.argsort(ts_ns)]
    return valid_idx


def _pick_estimated_eff_col_for_plane(df: pd.DataFrame, plane: int = 2) -> str | None:
    preferred = f"est_eff_sim_{int(plane)}"
    if preferred in df.columns and pd.to_numeric(df[preferred], errors="coerce").notna().any():
        return preferred
    return _choose_primary_eff_est_col(df)


def _pick_dictionary_eff_col_for_plane(df: pd.DataFrame, plane: int = 2) -> str | None:
    preferred = f"eff_sim_{int(plane)}"
    if preferred in df.columns and pd.to_numeric(df[preferred], errors="coerce").notna().any():
        return preferred
    for c in sorted(
        [col for col in df.columns if re.match(r"^eff_sim_\d+$", str(col))]
    ):
        if c in df.columns and pd.to_numeric(df[c], errors="coerce").notna().any():
            return c
    return None


def _mask_sim_eff_within_tolerance_band(
    df: pd.DataFrame,
    tolerance_pct: float,
) -> np.ndarray:
    """Rows where all available eff_sim_* columns are finite and inside one tolerance band."""
    n_rows = len(df)
    if n_rows == 0:
        return np.zeros(0, dtype=bool)
    eff_cols = sorted([c for c in df.columns if re.match(r"^eff_sim_\d+$", str(c))])
    if len(eff_cols) < 2:
        return np.zeros(n_rows, dtype=bool)

    tol_pct = float(tolerance_pct)
    if not np.isfinite(tol_pct):
        tol_pct = 10.0
    tol_pct = max(0.0, tol_pct)
    tol_abs = tol_pct / 100.0

    eff_mat = np.column_stack(
        [pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float) for col in eff_cols]
    )
    finite = np.isfinite(eff_mat).all(axis=1)
    if not np.any(finite):
        return np.zeros(n_rows, dtype=bool)
    span = np.full(n_rows, np.nan, dtype=float)
    eff_finite = eff_mat[finite]
    span[finite] = np.max(eff_finite, axis=1) - np.min(eff_finite, axis=1)
    return finite & (span <= (tol_abs + 1e-12))


def _choose_primary_eff_est_col(df: pd.DataFrame) -> str | None:
    preferred = sorted([c for c in df.columns if re.match(r"^est_eff_sim_\d+$", str(c))])
    if preferred:
        return preferred[0]
    generic = [c for c in df.columns if c.startswith("est_eff_")]
    return sorted(generic)[0] if generic else None


def _time_axis(df: pd.DataFrame) -> tuple[pd.Series, str, bool]:
    if "file_timestamp_utc" in df.columns:
        ts = _parse_ts(df["file_timestamp_utc"])
        if ts.notna().any():
            return (ts.dt.tz_convert(None), "Data time from filename_base [UTC]", True)
    if "execution_timestamp_utc" in df.columns:
        ts = _parse_ts(df["execution_timestamp_utc"])
        if ts.notna().any():
            return (ts.dt.tz_convert(None), "Execution time [UTC]", True)
    if "execution_timestamp" in df.columns:
        ts = _parse_ts(df["execution_timestamp"])
        if ts.notna().any():
            return (ts.dt.tz_convert(None), "Execution time [UTC]", True)
    return (pd.Series(np.arange(len(df), dtype=float), index=df.index), "Row index", False)


def _plot_placeholder(path: Path, title: str, message: str) -> None:
    fig, ax = plt.subplots(figsize=(10.0, 4.7))
    ax.axis("off")
    ax.text(0.5, 0.6, title, ha="center", va="center", fontsize=13, fontweight="bold")
    ax.text(0.5, 0.42, message, ha="center", va="center", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _plot_series_with_uncertainty(
    *,
    x: pd.Series,
    has_time_axis: bool,
    y: pd.Series,
    y_unc: pd.Series | None,
    title: str,
    ylabel: str,
    xlabel: str,
    out_path: Path,
) -> None:
    yv = pd.to_numeric(y, errors="coerce")
    if yv.notna().sum() == 0:
        _plot_placeholder(out_path, title, f"No finite values found for '{ylabel}'.")
        return

    fig, ax = plt.subplots(figsize=(10.4, 4.9))
    x_values = x.to_numpy()
    y_values = yv.to_numpy(dtype=float)

    ax.plot(x_values, y_values, color="#1F77B4", linewidth=1.2, alpha=0.9, marker="o", markersize=2.4)

    if y_unc is not None:
        uv = pd.to_numeric(y_unc, errors="coerce").to_numpy(dtype=float)
        finite = np.isfinite(y_values) & np.isfinite(uv)
        if finite.any():
            lower = y_values[finite] - np.abs(uv[finite])
            upper = y_values[finite] + np.abs(uv[finite])
            ax.fill_between(
                x_values[finite],
                lower,
                upper,
                color="#1F77B4",
                alpha=0.16,
                linewidth=0.0,
                label="Estimate +/- uncertainty",
            )
            ax.legend(loc="best", frameon=True, fontsize=9)

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.22)
    if not has_time_axis:
        ax.set_xlim(float(np.nanmin(x_values)), float(np.nanmax(x_values)) if len(x_values) > 1 else 1.0)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_parameter_estimate_series(
    *,
    x: pd.Series,
    has_time_axis: bool,
    xlabel: str,
    df: pd.DataFrame,
    parameter_columns: list[str],
    out_path: Path,
) -> int:
    """Plot estimated parameter time series with uncertainty for all resolved dimensions."""
    panels: list[tuple[str, np.ndarray, np.ndarray, np.ndarray | None]] = []
    x_values = x.to_numpy()

    for pname in parameter_columns:
        est_col = _find_estimated_parameter_column(df, pname)
        if est_col is None:
            continue
        y = pd.to_numeric(df.get(est_col), errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(y).any():
            continue
        unc_col = f"unc_{pname}_abs" if f"unc_{pname}_abs" in df.columns else None
        unc = (
            pd.to_numeric(df.get(unc_col), errors="coerce").to_numpy(dtype=float)
            if unc_col is not None
            else None
        )
        panels.append((pname, x_values, y, unc))

    if not panels:
        _plot_placeholder(
            out_path,
            "Estimated parameters vs time",
            "No finite estimated parameter series are available.",
        )
        return 0

    n_rows = len(panels)
    fig, axes = plt.subplots(
        n_rows,
        1,
        figsize=(11.0, max(3.0 * n_rows, 4.8)),
        sharex=True,
        squeeze=False,
    )

    for row, (pname, xv, yv, unc) in enumerate(panels):
        ax = axes[row, 0]
        mask = np.isfinite(xv) & np.isfinite(yv)
        if np.any(mask):
            xs = xv[mask]
            ys = yv[mask]
            order = np.argsort(xs)
            xs = xs[order]
            ys = ys[order]
            ax.plot(
                xs,
                ys,
                color="#1F77B4",
                linewidth=1.25,
                alpha=0.92,
                marker="o",
                markersize=2.6,
            )
            if unc is not None and len(unc) == len(xv):
                us = np.abs(np.asarray(unc, dtype=float)[mask][order])
                valid_u = np.isfinite(us)
                if np.any(valid_u):
                    ax.fill_between(
                        xs[valid_u],
                        ys[valid_u] - us[valid_u],
                        ys[valid_u] + us[valid_u],
                        color="#1F77B4",
                        alpha=0.14,
                        linewidth=0.0,
                        label="Estimate +/- uncertainty",
                    )
                    ax.legend(loc="best", fontsize=8, framealpha=0.92)
        else:
            ax.text(0.5, 0.5, f"No finite estimates for {pname}", ha="center", va="center", transform=ax.transAxes)
        ax.set_ylabel(pname)
        ax.grid(True, alpha=0.22)

    axes[-1, 0].set_xlabel(xlabel)
    if not has_time_axis and len(x_values) > 0:
        xmin = float(np.nanmin(x_values))
        xmax = float(np.nanmax(x_values)) if len(x_values) > 1 else xmin + 1.0
        axes[-1, 0].set_xlim(xmin, xmax)
    fig.suptitle("Estimated parameter time series", fontsize=12)
    fig.tight_layout(rect=[0.0, 0.0, 1.0, 0.98])
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return n_rows


def _plot_parameter_estimate_series_vs_k1(
    *,
    x: pd.Series,
    has_time_axis: bool,
    xlabel: str,
    df: pd.DataFrame,
    parameter_columns: list[str],
    out_path: Path,
) -> int:
    """Plot current runtime estimates against a full k=1 nearest-neighbor proxy series."""
    panels: list[tuple[str, np.ndarray, np.ndarray, np.ndarray, np.ndarray | None]] = []
    x_values = x.to_numpy()

    for pname in parameter_columns:
        est_col = _find_estimated_parameter_column(df, pname)
        k1_col = f"k1_est_{pname}"
        if est_col is None or k1_col not in df.columns:
            continue
        y_runtime = pd.to_numeric(df.get(est_col), errors="coerce").to_numpy(dtype=float)
        y_k1 = pd.to_numeric(df.get(k1_col), errors="coerce").to_numpy(dtype=float)
        if not (np.isfinite(y_runtime).any() or np.isfinite(y_k1).any()):
            continue
        unc_col = f"unc_{pname}_abs" if f"unc_{pname}_abs" in df.columns else None
        unc = (
            pd.to_numeric(df.get(unc_col), errors="coerce").to_numpy(dtype=float)
            if unc_col is not None
            else None
        )
        panels.append((pname, x_values, y_runtime, y_k1, unc))

    if not panels:
        _plot_placeholder(
            out_path,
            "Estimated parameter time series vs k=1 proxy",
            "No finite runtime/k=1 comparison series are available.",
        )
        return 0

    n_rows = len(panels)
    fig, axes = plt.subplots(
        n_rows,
        1,
        figsize=(11.0, max(3.0 * n_rows, 4.8)),
        sharex=True,
        squeeze=False,
    )

    for row, (pname, xv, y_runtime, y_k1, unc) in enumerate(panels):
        ax = axes[row, 0]
        mask_runtime = np.isfinite(xv) & np.isfinite(y_runtime)
        mask_k1 = np.isfinite(xv) & np.isfinite(y_k1)
        if np.any(mask_runtime):
            xs = xv[mask_runtime]
            ys = y_runtime[mask_runtime]
            order = np.argsort(xs)
            xs = xs[order]
            ys = ys[order]
            ax.plot(
                xs,
                ys,
                color="#1F77B4",
                linewidth=1.35,
                alpha=0.95,
                marker="o",
                markersize=2.5,
                label="Runtime inverse",
            )
            if unc is not None and len(unc) == len(xv):
                us = np.abs(np.asarray(unc, dtype=float)[mask_runtime][order])
                valid_u = np.isfinite(us)
                if np.any(valid_u):
                    ax.fill_between(
                        xs[valid_u],
                        ys[valid_u] - us[valid_u],
                        ys[valid_u] + us[valid_u],
                        color="#1F77B4",
                        alpha=0.12,
                        linewidth=0.0,
                    )
        if np.any(mask_k1):
            xs = xv[mask_k1]
            ys = y_k1[mask_k1]
            order = np.argsort(xs)
            xs = xs[order]
            ys = ys[order]
            ax.plot(
                xs,
                ys,
                color="#E15759",
                linewidth=1.15,
                alpha=0.92,
                linestyle="--",
                marker="s",
                markersize=2.2,
                label="k=1 nearest dictionary",
            )
        if not np.any(mask_runtime) and not np.any(mask_k1):
            ax.text(
                0.5,
                0.5,
                f"No finite runtime/k=1 values for {pname}",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
        ax.set_ylabel(pname)
        ax.grid(True, alpha=0.22)
        ax.legend(loc="best", fontsize=8, framealpha=0.92)

    axes[-1, 0].set_xlabel(xlabel)
    if not has_time_axis and len(x_values) > 0:
        xmin = float(np.nanmin(x_values))
        xmax = float(np.nanmax(x_values)) if len(x_values) > 1 else xmin + 1.0
        axes[-1, 0].set_xlim(xmin, xmax)
    fig.suptitle("Estimated parameter time series: runtime inverse vs k=1 proxy", fontsize=12)
    fig.tight_layout(rect=[0.0, 0.0, 1.0, 0.98])
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return n_rows


def _parse_named_float_dict(value: object) -> dict[str, float]:
    if value in (None, "", "null", "None"):
        return {}
    payload = value
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return {}
    if not isinstance(payload, dict):
        return {}
    out: dict[str, float] = {}
    for raw_key, raw_val in payload.items():
        key = str(raw_key).strip()
        if not key:
            continue
        try:
            num = float(raw_val)
        except (TypeError, ValueError):
            continue
        if np.isfinite(num) and num >= 0.0:
            out[key] = num
    return out


def _format_distance_term_label(name: str) -> str:
    text = str(name).strip()
    if text == "scalar_base":
        return "Scalar features"
    if text == "rate_histogram":
        return "Rate histogram"
    if text == "efficiency_vectors":
        return "Efficiency vs X/Y/theta"
    return text.replace("_", " ")


def _split_group_component_name(name: str) -> tuple[str, str]:
    text = str(name).strip()
    if "::" not in text:
        return "", text
    parent, child = text.split("::", 1)
    return str(parent).strip(), str(child).strip()


def _format_group_component_label(name: str) -> str:
    parent, child = _split_group_component_name(name)
    if parent == "rate_histogram":
        match = re.match(r"^events_per_second_(?P<bin>\d+)_rate_hz$", child)
        if match is not None:
            return f"Hist bin {int(match.group('bin'))}"
        return child or "Rate-hist component"
    if parent == "efficiency_vectors":
        match = re.match(r"^p(?P<plane>\d+)_(?P<axis>x|y|theta)$", child)
        if match is not None:
            axis = str(match.group("axis"))
            axis_label = {"x": "X", "y": "Y", "theta": "theta"}.get(axis, axis)
            return f"Eff p{int(match.group('plane'))} {axis_label}"
        return child or "Efficiency-vector component"
    return child or name


def _distance_term_color(name: str) -> str:
    fixed = {
        "scalar_base": "#4C78A8",
        "rate_histogram": "#F58518",
        "efficiency_vectors": "#54A24B",
    }
    if name in fixed:
        return fixed[name]
    palette = plt.get_cmap("tab20").colors
    return palette[abs(hash(name)) % len(palette)]


def _plot_distance_term_dominance(
    *,
    x: pd.Series,
    has_time_axis: bool,
    xlabel: str,
    df: pd.DataFrame,
    out_path: Path,
) -> dict[str, object]:
    term_rows: list[dict[str, float]] = []
    scalar_rows: list[dict[str, float]] = []
    group_component_rows: list[dict[str, float]] = []
    group_component_within_rows: list[dict[str, float]] = []
    keep_idx: list[int] = []

    distance_vals = pd.to_numeric(df.get("best_distance"), errors="coerce")
    for idx in range(len(df)):
        if idx >= len(distance_vals) or not np.isfinite(float(distance_vals.iloc[idx])):
            continue
        term_payload = _parse_named_float_dict(df.iloc[idx].get("best_distance_term_shares_json"))
        if not term_payload:
            continue
        total = float(sum(term_payload.values()))
        if not np.isfinite(total) or total <= 0.0:
            continue
        if abs(total - 1.0) > 1e-9:
            term_payload = {k: float(v / total) for k, v in term_payload.items() if np.isfinite(v) and v >= 0.0}
        term_rows.append(term_payload)
        scalar_rows.append(_parse_named_float_dict(df.iloc[idx].get("best_distance_scalar_feature_shares_json")))
        group_component_rows.append(_parse_named_float_dict(df.iloc[idx].get("best_distance_group_component_shares_json")))
        group_component_within_rows.append(
            _parse_named_float_dict(df.iloc[idx].get("best_distance_group_component_within_term_shares_json"))
        )
        keep_idx.append(idx)

    if not term_rows:
        _plot_placeholder(
            out_path,
            "Feature-space distance dominance",
            "No exact distance-term breakdowns are available for successful rows.",
        )
        return {
            "plot_available": False,
            "n_rows": 0,
            "term_median_share": {},
            "term_dominant_fraction": {},
            "top_scalar_feature_median_share": {},
            "top_group_component_median_total_share": {},
            "top_group_component_median_within_term_share": {},
        }

    term_df = pd.DataFrame(term_rows).fillna(0.0)
    x_used = x.iloc[keep_idx].reset_index(drop=True)

    term_order = (
        term_df.median(axis=0, skipna=True)
        .sort_values(ascending=False)
        .index.tolist()
    )
    term_df = term_df[term_order]
    term_medians = {
        name: float(term_df[name].median(skipna=True))
        for name in term_order
    }

    row_sums = term_df.sum(axis=1)
    dominant_labels: list[str] = []
    for row_idx in range(len(term_df)):
        if not np.isfinite(float(row_sums.iloc[row_idx])) or float(row_sums.iloc[row_idx]) <= 0.0:
            continue
        dominant_labels.append(str(term_df.iloc[row_idx].idxmax()))
    dominant_fraction = {
        name: float(np.mean([label == name for label in dominant_labels]))
        for name in term_order
    }

    scalar_df = pd.DataFrame(scalar_rows).fillna(0.0) if scalar_rows else pd.DataFrame()
    scalar_medians: dict[str, float] = {}
    scalar_order: list[str] = []
    if not scalar_df.empty:
        scalar_medians = {
            name: float(val)
            for name, val in scalar_df.median(axis=0, skipna=True).sort_values(ascending=False).items()
            if np.isfinite(float(val)) and float(val) > 0.0
        }
        scalar_order = list(scalar_medians.keys())[:10]

    component_total_df = pd.DataFrame(group_component_rows).fillna(0.0) if group_component_rows else pd.DataFrame()
    component_within_df = (
        pd.DataFrame(group_component_within_rows).fillna(0.0) if group_component_within_rows else pd.DataFrame()
    )
    component_total_medians: dict[str, float] = {}
    component_total_order: list[str] = []
    if not component_total_df.empty:
        component_total_medians = {
            name: float(val)
            for name, val in component_total_df.median(axis=0, skipna=True).sort_values(ascending=False).items()
            if np.isfinite(float(val)) and float(val) > 0.0
        }
        component_total_order = list(component_total_medians.keys())[:12]
    component_within_medians: dict[str, float] = {}
    component_within_order: list[str] = []
    if not component_within_df.empty:
        for name in component_within_df.columns:
            series = pd.to_numeric(component_within_df[name], errors="coerce")
            active = series[np.isfinite(series.to_numpy(dtype=float)) & (series > 0.0)]
            if active.empty:
                continue
            value = float(active.median(skipna=True))
            if np.isfinite(value) and value > 0.0:
                component_within_medians[str(name)] = value
        component_within_medians = dict(
            sorted(component_within_medians.items(), key=lambda item: (-float(item[1]), str(item[0])))
        )
        component_within_order = list(component_within_medians.keys())[:12]

    has_component_breakdown = bool(component_total_order or component_within_order)
    height_ratios = [2.4, 1.2]
    if has_component_breakdown:
        height_ratios.append(1.5)
    if scalar_order:
        height_ratios.append(1.2)
    n_rows = len(height_ratios)
    fig = plt.figure(figsize=(12.8, 11.4 if has_component_breakdown and scalar_order else (9.8 if has_component_breakdown else (10.0 if scalar_order else 8.2))))
    gs = fig.add_gridspec(n_rows, 2, height_ratios=height_ratios)
    ax_stack = fig.add_subplot(gs[0, :])
    ax_median = fig.add_subplot(gs[1, 0])
    ax_dom = fig.add_subplot(gs[1, 1])
    component_row_idx = 2 if has_component_breakdown else None
    ax_component_total = fig.add_subplot(gs[component_row_idx, 0]) if has_component_breakdown else None
    ax_component_within = fig.add_subplot(gs[component_row_idx, 1]) if has_component_breakdown else None
    scalar_row_idx = (3 if has_component_breakdown else 2) if scalar_order else None
    ax_scalar = fig.add_subplot(gs[scalar_row_idx, :]) if scalar_order else None

    x_numeric: np.ndarray
    if has_time_axis:
        x_dt = pd.to_datetime(x_used, errors="coerce")
        x_numeric = mdates.date2num(x_dt.to_numpy())
    else:
        x_numeric = pd.to_numeric(x_used, errors="coerce").to_numpy(dtype=float)
    finite_x = np.isfinite(x_numeric)
    if not np.any(finite_x):
        x_numeric = np.arange(len(term_df), dtype=float)
        finite_x = np.ones(len(term_df), dtype=bool)
    order = np.argsort(x_numeric[finite_x])
    xs = x_numeric[finite_x][order]
    ys_df = term_df.loc[finite_x].reset_index(drop=True).iloc[order]
    bottom = np.zeros(len(ys_df), dtype=float)
    for term_name in term_order:
        vals = np.clip(pd.to_numeric(ys_df[term_name], errors="coerce").to_numpy(dtype=float), 0.0, 1.0)
        ax_stack.fill_between(
            xs,
            bottom,
            bottom + vals,
            color=_distance_term_color(term_name),
            alpha=0.88,
            linewidth=0.0,
            label=_format_distance_term_label(term_name),
        )
        bottom = bottom + vals
    ax_stack.set_ylim(0.0, 1.0)
    ax_stack.set_ylabel("Share of best-match distance")
    ax_stack.set_title("Feature-space distance dominance by active term")
    ax_stack.grid(True, alpha=0.2)
    ax_stack.legend(loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=max(1, min(len(term_order), 3)), fontsize=9)
    if has_time_axis:
        ax_stack.xaxis_date()
        locator = mdates.AutoDateLocator()
        ax_stack.xaxis.set_major_locator(locator)
        ax_stack.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    else:
        ax_stack.set_xlabel(xlabel)

    y_pos = np.arange(len(term_order), dtype=float)
    ax_median.barh(
        y_pos,
        [term_medians[name] for name in term_order],
        color=[_distance_term_color(name) for name in term_order],
        alpha=0.9,
    )
    ax_median.set_yticks(y_pos, labels=[_format_distance_term_label(name) for name in term_order])
    ax_median.set_xlim(0.0, 1.0)
    ax_median.set_xlabel("Median share")
    ax_median.set_title("Median contribution")
    ax_median.grid(True, axis="x", alpha=0.2)

    ax_dom.barh(
        y_pos,
        [dominant_fraction.get(name, 0.0) for name in term_order],
        color=[_distance_term_color(name) for name in term_order],
        alpha=0.9,
    )
    ax_dom.set_yticks(y_pos, labels=[_format_distance_term_label(name) for name in term_order])
    ax_dom.set_xlim(0.0, 1.0)
    ax_dom.set_xlabel("Fraction of rows dominant")
    ax_dom.set_title("Dominant-term frequency")
    ax_dom.grid(True, axis="x", alpha=0.2)

    if ax_component_total is not None and ax_component_within is not None:
        if component_total_order:
            comp_y = np.arange(len(component_total_order), dtype=float)
            comp_colors = [
                _distance_term_color(_split_group_component_name(name)[0] or name)
                for name in component_total_order
            ]
            ax_component_total.barh(
                comp_y,
                [component_total_medians[name] for name in component_total_order],
                color=comp_colors,
                alpha=0.9,
            )
            ax_component_total.set_yticks(
                comp_y,
                labels=[_format_group_component_label(name) for name in component_total_order],
            )
            ax_component_total.set_xlim(0.0, max(max(component_total_medians.values()) * 1.15, 0.05))
            ax_component_total.set_xlabel("Median total-distance share")
            ax_component_total.set_title("Top grouped components by total share")
            ax_component_total.grid(True, axis="x", alpha=0.2)
        else:
            ax_component_total.axis("off")
            ax_component_total.text(
                0.5,
                0.5,
                "No grouped-component total-share diagnostics",
                ha="center",
                va="center",
                fontsize=10,
                transform=ax_component_total.transAxes,
            )

        if component_within_order:
            comp_y = np.arange(len(component_within_order), dtype=float)
            comp_colors = [
                _distance_term_color(_split_group_component_name(name)[0] or name)
                for name in component_within_order
            ]
            ax_component_within.barh(
                comp_y,
                [component_within_medians[name] for name in component_within_order],
                color=comp_colors,
                alpha=0.9,
            )
            ax_component_within.set_yticks(
                comp_y,
                labels=[_format_group_component_label(name) for name in component_within_order],
            )
            ax_component_within.set_xlim(0.0, 1.0)
            ax_component_within.set_xlabel("Median share within parent term (when active)")
            ax_component_within.set_title("Top grouped components inside their term")
            ax_component_within.grid(True, axis="x", alpha=0.2)
        else:
            ax_component_within.axis("off")
            ax_component_within.text(
                0.5,
                0.5,
                "No grouped-component within-term diagnostics",
                ha="center",
                va="center",
                fontsize=10,
                transform=ax_component_within.transAxes,
            )

    if ax_scalar is not None:
        ax_scalar.barh(
            np.arange(len(scalar_order), dtype=float),
            [scalar_medians[name] for name in scalar_order],
            color="#4C78A8",
            alpha=0.9,
        )
        ax_scalar.set_yticks(np.arange(len(scalar_order), dtype=float), labels=scalar_order)
        ax_scalar.set_xlim(0.0, max(max(scalar_medians.values()) * 1.15, 0.05))
        ax_scalar.set_xlabel("Median total-distance share")
        ax_scalar.set_title("Top scalar features by median share")
        ax_scalar.grid(True, axis="x", alpha=0.2)

    if has_time_axis:
        ax_dom.set_xlabel("Fraction of rows dominant")
        if ax_scalar is not None:
            ax_scalar.set_xlabel("Median total-distance share")
    else:
        ax_stack.set_xlabel(xlabel)

    fig.tight_layout(rect=[0.0, 0.0, 1.0, 0.98])
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return {
        "plot_available": True,
        "n_rows": int(len(term_df)),
        "term_median_share": term_medians,
        "term_dominant_fraction": dominant_fraction,
        "top_scalar_feature_median_share": {
            name: float(scalar_medians[name])
            for name in scalar_order
        },
        "top_group_component_median_total_share": {
            name: float(component_total_medians[name])
            for name in component_total_order
        },
        "top_group_component_median_within_term_share": {
            name: float(component_within_medians[name])
            for name in component_within_order
        },
    }


def _plot_flux_recovery_story_real(
    *,
    x: pd.Series,
    has_time_axis: bool,
    xlabel: str,
    distance_series: pd.Series | None,
    distance_label: str,
    eff_series: pd.Series,
    eff_label: str,
    eff_series_map: dict[str, pd.Series] | None,
    global_rate_series: pd.Series,
    global_rate_label: str,
    flux_est_series: pd.Series,
    flux_unc_series: pd.Series | None,
    flux_reference_series: pd.Series | None,
    flux_reference_label: str,
    out_path: Path,
) -> None:
    """Match STEP 3.3 diagnostics scheme for real data (no simulated/reference curves)."""

    def _apply_striped_background(ax: plt.Axes, y_vals: np.ndarray) -> None:
        y_min, y_max = ax.get_ylim()
        if not (np.isfinite(y_min) and np.isfinite(y_max)):
            return
        span = y_max - y_min
        if span <= 0.0:
            return

        valid = np.isfinite(y_vals)
        if not np.any(valid):
            return
        mean_val = float(np.mean(y_vals[valid]))
        band = abs(mean_val) * 0.01
        if not np.isfinite(band) or band <= 0.0:
            band = span * 0.01
        if band <= 0.0:
            return

        ax.set_facecolor("#FFFFFF")
        idx = int(np.floor((y_min - mean_val) / band))
        y0 = mean_val + idx * band
        while y0 < y_max:
            y1 = y0 + band
            lo = max(y0, y_min)
            hi = min(y1, y_max)
            color = "#FFFFFF" if (idx % 2 == 0) else "#D8DDE4"
            if hi > lo:
                ax.axhspan(lo, hi, facecolor=color, alpha=1.0, linewidth=0.0, zorder=0)
            y0 = y1
            idx += 1
        ax.set_ylim(y_min, y_max)

    from matplotlib.ticker import FuncFormatter, MaxNLocator

    def _eff_display_name(col: str) -> str:
        text = str(col).strip()
        for prefix in ("est_", "corrected_", "true_"):
            if text.startswith(prefix):
                text = text[len(prefix):]
        match = re.match(r"^eff_sim_(\d+)$", text)
        if match is not None:
            return f"Eff {match.group(1)}"
        return text.replace("_", " ")

    # Kept in signature for backward compatibility; intentionally not used in real-data story.
    del flux_reference_series, flux_reference_label

    xv = x.to_numpy()
    distance = (
        pd.to_numeric(distance_series, errors="coerce").to_numpy(dtype=float)
        if distance_series is not None
        else np.full(len(xv), np.nan, dtype=float)
    )
    eff_curves: list[tuple[str, np.ndarray]] = []
    if eff_series_map:
        for label, series in eff_series_map.items():
            vals = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
            if len(vals) == len(xv):
                eff_curves.append((str(label), vals))
    if not eff_curves:
        eff_curves = [(str(eff_label), pd.to_numeric(eff_series, errors="coerce").to_numpy(dtype=float))]

    eff_any_finite = any(np.isfinite(vals).any() for _, vals in eff_curves)
    eff_all_finite = [vals[np.isfinite(vals)] for _, vals in eff_curves if np.isfinite(vals).any()]
    eff_bg = np.concatenate(eff_all_finite) if eff_all_finite else np.array([], dtype=float)
    rate = pd.to_numeric(global_rate_series, errors="coerce").to_numpy(dtype=float)
    flux_est = pd.to_numeric(flux_est_series, errors="coerce").to_numpy(dtype=float)
    flux_unc = (
        pd.to_numeric(flux_unc_series, errors="coerce").to_numpy(dtype=float)
        if flux_unc_series is not None
        else None
    )

    valid_any = (
        np.isfinite(distance).any()
        or eff_any_finite
        or np.isfinite(rate).any()
        or np.isfinite(flux_est).any()
    )
    if not valid_any:
        _plot_placeholder(
            out_path,
            "Flux-recovery style real-data story",
            "No finite series available for best_distance / estimated efficiency / global rate / estimated flux.",
        )
        return

    fig, axes = plt.subplots(
        4,
        1,
        figsize=(11.6, 10.6),
        sharex=True,
        gridspec_kw={"height_ratios": [0.85, 1.0, 1.05, 1.25]},
    )
    for ax in axes:
        ax.set_facecolor("#FFFFFF")
        ax.grid(True, alpha=0.24)

    # 1) Feature-space distance quality metric.
    m_dist = np.isfinite(xv) & np.isfinite(distance)
    if np.any(m_dist):
        order = np.argsort(xv[m_dist])
        xd = xv[m_dist][order]
        yd = distance[m_dist][order]
        axes[0].plot(
            xd,
            yd,
            color="#6A3D9A",
            linewidth=2.1,
            alpha=0.95,
            solid_capstyle="round",
            label=(distance_label if str(distance_label).strip() else "distance"),
        )
        _apply_striped_background(axes[0], yd)
        axes[0].legend(loc="best", fontsize=8, framealpha=0.92, facecolor="white")
    else:
        axes[0].text(0.5, 0.5, "No finite distance values", ha="center", va="center")
    axes[0].set_ylabel("Distance")
    axes[0].set_title(
        f"Feature-space distance (quality) [{distance_label}]"
        if str(distance_label).strip()
        else "Feature-space distance (quality)"
    )

    # 2) Global rate.
    rate_bg: list[np.ndarray] = []
    m_rate = np.isfinite(xv) & np.isfinite(rate)
    if np.any(m_rate):
        order = np.argsort(xv[m_rate])
        xr = xv[m_rate][order]
        yr = rate[m_rate][order]
        rate_bg.append(yr)
        axes[1].plot(
            xr,
            yr,
            color="#2E8B57",
            linewidth=2.6,
            alpha=0.95,
            solid_capstyle="round",
            label=f"Global rate ({global_rate_label})",
        )
    else:
        axes[1].text(0.5, 0.5, f"No finite values for {global_rate_label}", ha="center", va="center")
    axes[1].set_ylabel("Global rate [Hz]")
    axes[1].set_title("Global rate time series")
    if rate_bg:
        _apply_striped_background(axes[1], np.concatenate(rate_bg))
    axes[1].yaxis.set_major_locator(MaxNLocator(integer=True))
    axes[1].yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{int(np.rint(v))}"))
    _legend_if_labeled(axes[1], loc="best", fontsize=8, framealpha=0.92, facecolor="white")

    # 3) Efficiencies: estimated (all available planes).
    eff_palette = ["#1F77B4", "#FF7F0E", "#2CA02C", "#9467BD", "#8C564B", "#17BECF"]
    eff_bg: list[np.ndarray] = []
    for idx, (eff_col, eff_vals) in enumerate(eff_curves):
        color = eff_palette[idx % len(eff_palette)]
        eff_name = _eff_display_name(eff_col)
        m_est = np.isfinite(xv) & np.isfinite(eff_vals)
        if not np.any(m_est):
            continue
        order = np.argsort(xv[m_est])
        xs = xv[m_est][order]
        ys = eff_vals[m_est][order]
        eff_bg.append(ys)
        axes[2].plot(
            xs,
            ys,
            color=color,
            linewidth=1.9,
            linestyle="-",
            alpha=0.97,
            marker="o",
            markersize=2.7,
            markerfacecolor=color,
            markeredgecolor="white",
            markeredgewidth=0.35,
            label=f"{eff_name} est",
        )
    axes[2].set_ylabel("Efficiency")
    axes[2].set_title("Efficiencies: estimated")
    if eff_bg:
        _apply_striped_background(axes[2], np.concatenate(eff_bg))
    _legend_if_labeled(
        axes[2],
        loc="best",
        fontsize=7,
        ncol=4,
        framealpha=0.92,
        facecolor="white",
        columnspacing=1.1,
        handlelength=2.2,
    )

    # 4) Flux: estimated.
    flux_color = "#D62728"
    m_est_flux = np.isfinite(xv) & np.isfinite(flux_est)
    flux_bg: list[np.ndarray] = [flux_est]
    if np.any(m_est_flux):
        order = np.argsort(xv[m_est_flux])
        xe = xv[m_est_flux][order]
        ye = flux_est[m_est_flux][order]
        axes[3].plot(
            xe,
            ye,
            color=flux_color,
            linewidth=2.8,
            marker="o",
            markersize=4.4,
            markerfacecolor=flux_color,
            markeredgecolor="white",
            markeredgewidth=0.45,
            alpha=0.99,
            label="Estimated flux",
            zorder=3,
        )
        if flux_unc is not None and len(flux_unc) == len(xv):
            ue = np.abs(np.asarray(flux_unc, dtype=float)[m_est_flux][order])
            valid_ue = np.isfinite(ue)
            if np.any(valid_ue):
                axes[3].fill_between(
                    xe[valid_ue],
                    ye[valid_ue] - ue[valid_ue],
                    ye[valid_ue] + ue[valid_ue],
                    color=flux_color,
                    alpha=0.14,
                    linewidth=0.0,
                    label="Estimated ± uncertainty",
                    zorder=2,
                )
    else:
        axes[3].text(0.5, 0.5, "No finite estimated flux values", ha="center", va="center")

    axes[3].set_ylabel("Flux")
    axes[3].set_xlabel(xlabel)
    axes[3].set_title("Flux: estimated")
    if any(np.isfinite(arr).any() for arr in flux_bg):
        _apply_striped_background(axes[3], np.concatenate([arr[np.isfinite(arr)] for arr in flux_bg if arr.size > 0]))
    _legend_if_labeled(axes[3], loc="best", fontsize=8, framealpha=0.92, facecolor="white")

    if not has_time_axis and len(xv) > 0:
        xmin = float(np.nanmin(xv))
        xmax = float(np.nanmax(xv)) if len(xv) > 1 else xmin + 1.0
        for ax in axes:
            ax.set_xlim(xmin, xmax)

    fig.suptitle(
        "Feature-space quality and reconstruction diagnostics",
        fontsize=11,
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=170)
    plt.close(fig)


def _legend_if_labeled(ax: plt.Axes, **legend_kwargs: object) -> None:
    handles, labels = ax.get_legend_handles_labels()
    has_labeled = any(str(lbl).strip() and not str(lbl).startswith("_") for lbl in labels)
    if has_labeled and len(handles) > 0:
        ax.legend(**legend_kwargs)


def _plot_eff2_vs_global_rate(
    *,
    real_df: pd.DataFrame,
    dict_df: pd.DataFrame,
    real_eff2_col: str,
    real_rate_col: str,
    dict_eff2_col: str,
    dict_rate_col: str,
    out_path: Path,
) -> tuple[int, int]:
    """Plot real-data plane-2 efficiency proxy trajectory in the (global_rate, proxy) plane."""
    real_eff = pd.to_numeric(real_df[real_eff2_col], errors="coerce")
    real_rate = pd.to_numeric(real_df[real_rate_col], errors="coerce")
    dict_eff = pd.to_numeric(dict_df[dict_eff2_col], errors="coerce")
    dict_rate = pd.to_numeric(dict_df[dict_rate_col], errors="coerce")

    dict_valid = dict_eff.notna() & dict_rate.notna()
    real_valid = real_eff.notna() & real_rate.notna()
    n_dict = int(dict_valid.sum())
    n_real = int(real_valid.sum())

    if n_real == 0:
        _plot_placeholder(
            out_path,
            "Plane-2 efficiency proxy vs global rate",
            "No finite real points available for plane-2 proxy/global-rate trajectory.",
        )
        return (n_real, n_dict)

    x_real = real_rate[real_valid].to_numpy(dtype=float)
    y_real = real_eff[real_valid].to_numpy(dtype=float)
    x_dict = dict_rate[dict_valid].to_numpy(dtype=float)
    y_dict = dict_eff[dict_valid].to_numpy(dtype=float)

    x_all = np.concatenate([x_real, x_dict]) if x_dict.size else x_real
    y_all = np.concatenate([y_real, y_dict]) if y_dict.size else y_real
    x_lo = float(np.nanmin(x_all))
    x_hi = float(np.nanmax(x_all))
    y_lo = float(np.nanmin(y_all))
    y_hi = float(np.nanmax(y_all))
    x_span = max(x_hi - x_lo, 1e-9)
    y_span = max(y_hi - y_lo, 1e-9)
    x_pad = max(0.03 * x_span, 1e-6)
    y_pad = max(0.03 * y_span, 1e-6)
    x_lo -= x_pad
    x_hi += x_pad
    y_lo -= y_pad
    y_hi += y_pad

    fig, ax = plt.subplots(figsize=(9.2, 7.1))
    if n_dict > 0:
        ax.scatter(
            x_dict,
            y_dict,
            s=11,
            alpha=0.20,
            color="#606060",
            edgecolors="none",
            zorder=1,
            label="Dictionary points",
        )

    ordered_idx = _ordered_row_indices(real_df, real_valid)
    x_ord = real_df.iloc[ordered_idx][real_rate_col].to_numpy(dtype=float)
    y_ord = real_df.iloc[ordered_idx][real_eff2_col].to_numpy(dtype=float)
    finite_ord = np.isfinite(x_ord) & np.isfinite(y_ord)
    x_ord = x_ord[finite_ord]
    y_ord = y_ord[finite_ord]

    ax.plot(
        x_ord,
        y_ord,
        linewidth=1.8,
        color="#1F77B4",
        alpha=0.92,
        zorder=3,
        label="Real-data trajectory",
    )
    ax.scatter(
        x_ord,
        y_ord,
        s=24,
        facecolor="white",
        edgecolor="black",
        linewidth=0.6,
        zorder=4,
        label="Real-data points",
    )

    ax.scatter([x_ord[0]], [y_ord[0]], color="#2CA02C", marker="o", s=82, edgecolor="black", linewidth=0.8, zorder=5, label="Start")
    ax.scatter([x_ord[-1]], [y_ord[-1]], color="#D62728", marker="X", s=95, edgecolor="black", linewidth=0.8, zorder=5, label="End")

    if len(x_ord) >= 3:
        i = min(len(x_ord) - 2, max(0, int(0.85 * len(x_ord))))
        ax.annotate(
            "",
            xy=(x_ord[i + 1], y_ord[i + 1]),
            xytext=(x_ord[i], y_ord[i]),
            arrowprops={"arrowstyle": "->", "color": "black", "lw": 1.2},
            zorder=5,
        )

    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)
    ax.set_xlabel("Global rate [Hz]")
    ax.set_ylabel("Efficiency proxy (plane 2)")
    ax.set_title(
        "Real-data plane-2 efficiency proxy vs global rate\n"
        f"real_y={real_eff2_col} | dict_y={dict_eff2_col}"
    )
    ax.grid(True, alpha=0.2)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return (n_real, n_dict)


def _plot_estimated_curve_flux_vs_eff(
    *,
    real_df: pd.DataFrame,
    dict_df: pd.DataFrame,
    parameter_columns: list[str],
    out_path: Path,
) -> tuple[int, int]:
    """Lower-triangle matrix: estimated real-data parameter curve vs dictionary."""
    param_specs: list[tuple[str, str, str]] = []
    seen_labels: set[str] = set()
    for pname in parameter_columns:
        dict_col = str(pname).strip()
        real_col = _find_estimated_parameter_column(real_df, dict_col)
        if not dict_col or dict_col in seen_labels:
            continue
        if real_col is None or dict_col not in dict_df.columns:
            continue
        if not pd.to_numeric(real_df[real_col], errors="coerce").notna().any():
            continue
        if not pd.to_numeric(dict_df[dict_col], errors="coerce").notna().any():
            continue
        param_specs.append((dict_col, real_col, dict_col))
        seen_labels.add(dict_col)

    if len(param_specs) < 2:
        _plot_placeholder(
            out_path,
            "Estimated curve in parameter space",
            (
                "Not enough estimated parameter dimensions to build a lower-triangle matrix. "
                f"Resolved dimensions: {parameter_columns}"
            ),
        )
        return (0, 0)

    # Point-count summary uses primary pair (flux + first efficiency-like axis).
    x0_name, x0_real, x0_dict = param_specs[0]
    y0_name, y0_real, y0_dict = param_specs[1]
    del x0_name, y0_name
    real_primary = pd.to_numeric(real_df[x0_real], errors="coerce").notna() & pd.to_numeric(real_df[y0_real], errors="coerce").notna()
    dict_primary = pd.to_numeric(dict_df[x0_dict], errors="coerce").notna() & pd.to_numeric(dict_df[y0_dict], errors="coerce").notna()
    n_real = int(real_primary.sum())
    n_dict = int(dict_primary.sum())

    n = len(param_specs)
    fig, axes = plt.subplots(n, n, figsize=(3.1 * n, 3.1 * n), squeeze=False)

    for i, (y_name, y_real_col, y_dict_col) in enumerate(param_specs):
        for j, (x_name, x_real_col, x_dict_col) in enumerate(param_specs):
            ax = axes[i, j]
            if i < j:
                ax.axis("off")
                continue

            bx = pd.to_numeric(dict_df.get(x_dict_col), errors="coerce")
            by = pd.to_numeric(dict_df.get(y_dict_col), errors="coerce")
            rx = pd.to_numeric(real_df.get(x_real_col), errors="coerce")
            ry = pd.to_numeric(real_df.get(y_real_col), errors="coerce")

            if i == j:
                b = bx.dropna()
                r = rx.dropna()
                if not b.empty:
                    ax.hist(b, bins=34, color="#808080", alpha=0.34, label="Dictionary")
                if not r.empty:
                    ax.hist(r, bins=34, color="#D62728", alpha=0.30, label="Estimated curve")
                if i == 0 and j == 0:
                    ax.legend(loc="best", fontsize=7)
                ax.set_ylabel("count")
            else:
                m_basis = bx.notna() & by.notna()
                if m_basis.any():
                    ax.scatter(
                        bx[m_basis],
                        by[m_basis],
                        s=6,
                        color="#7A7A7A",
                        alpha=0.16,
                        linewidths=0,
                        label=("Dictionary" if (i == 1 and j == 0) else None),
                        zorder=1,
                    )

                m_real = rx.notna() & ry.notna()
                if m_real.any():
                    order_idx = _ordered_row_indices(real_df, m_real)
                    xr = real_df.iloc[order_idx][x_real_col].to_numpy(dtype=float)
                    yr = real_df.iloc[order_idx][y_real_col].to_numpy(dtype=float)
                    finite_ord = np.isfinite(xr) & np.isfinite(yr)
                    xr = xr[finite_ord]
                    yr = yr[finite_ord]
                    if len(xr) > 0:
                        ax.plot(
                            xr,
                            yr,
                            color="#D62728",
                            lw=1.05,
                            alpha=0.92,
                            linestyle="-",
                            label=("Estimated curve" if (i == 1 and j == 0) else None),
                            zorder=3,
                        )
                        ax.scatter(
                            xr,
                            yr,
                            s=14,
                            facecolor="white",
                            edgecolor="black",
                            linewidth=0.5,
                            label=("Estimated points" if (i == 1 and j == 0) else None),
                            zorder=4,
                        )
                        ax.scatter(
                            [xr[0]],
                            [yr[0]],
                            color="#2CA02C",
                            marker="o",
                            s=40,
                            edgecolor="black",
                            linewidth=0.6,
                            zorder=5,
                            label=("Start" if (i == 1 and j == 0) else None),
                        )
                        ax.scatter(
                            [xr[-1]],
                            [yr[-1]],
                            color="#D62728",
                            marker="X",
                            s=46,
                            edgecolor="black",
                            linewidth=0.6,
                            zorder=5,
                            label=("End" if (i == 1 and j == 0) else None),
                        )

            ax.grid(True, alpha=0.20)
            if i == n - 1:
                ax.set_xlabel(x_name)
            else:
                ax.set_xticklabels([])
            if j == 0 and i > 0:
                ax.set_ylabel(y_name)
            elif i > 0:
                ax.set_yticklabels([])

    if n >= 2:
        handles, labels = axes[1, 0].get_legend_handles_labels()
        if handles:
            fig.legend(handles, labels, loc="upper right", fontsize=8, framealpha=0.90)

    fig.suptitle("STEP 4.2 estimated curve in parameter space (lower triangle)", fontsize=12)
    fig.tight_layout(rect=[0.0, 0.0, 1.0, 0.98])
    fig.savefig(out_path, dpi=170)
    plt.close(fig)
    return (n_real, n_dict)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step 4.2: Infer real-data parameters and attach uncertainty LUT."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--real-csv", default=None)
    parser.add_argument("--dictionary-csv", default=None)
    parser.add_argument("--lut-csv", default=None)
    parser.add_argument("--lut-meta-json", default=None)
    args = parser.parse_args()

    config = _load_config(Path(args.config))
    cfg_21_raw = config.get("step_2_1", {})
    if not isinstance(cfg_21_raw, dict):
        cfg_21_raw = {}
    cfg_21, feature_cfg_sources = _merge_common_feature_space_cfg(config, cfg_21_raw)
    cfg_41 = config.get("step_4_1", {})
    cfg_42 = config.get("step_4_2", {})
    _clear_plots_dir()

    real_csv_cfg = cfg_42.get("real_collected_csv", None)
    dictionary_csv_cfg = cfg_42.get("dictionary_csv", None)
    lut_csv_cfg = cfg_42.get("uncertainty_lut_csv", None)
    lut_meta_cfg = cfg_42.get("uncertainty_lut_meta_json", None)
    build_summary_cfg = cfg_42.get("build_summary_json", None)
    efficiency_calibration_summary_cfg = cfg_42.get("efficiency_calibration_summary_json", None)
    parameter_space_spec_cfg = cfg_42.get("parameter_space_columns_json", None)

    real_path = _resolve_input_path(args.real_csv or real_csv_cfg or DEFAULT_REAL_COLLECTED)
    dict_path = _resolve_input_path(args.dictionary_csv or dictionary_csv_cfg or DEFAULT_DICTIONARY)
    lut_path = _resolve_input_path(args.lut_csv or lut_csv_cfg or DEFAULT_LUT)
    lut_meta_path = _resolve_input_path(args.lut_meta_json or lut_meta_cfg or DEFAULT_LUT_META)
    build_summary_path = _resolve_input_path(build_summary_cfg or DEFAULT_BUILD_SUMMARY)
    efficiency_calibration_summary_requested = _resolve_input_path(
        efficiency_calibration_summary_cfg or build_summary_path
    )
    efficiency_calibration_summary_path, efficiency_calibration_summary_resolution, _ = (
        _resolve_efficiency_calibration_summary_path(
            efficiency_calibration_summary_requested,
            fallback_path=DEFAULT_STEP13_BUILD_SUMMARY,
        )
    )
    parameter_space_spec_path = _resolve_input_path(parameter_space_spec_cfg or DEFAULT_PARAMETER_SPACE_SPEC)

    for label, path in (
        ("Real collected CSV", real_path),
        ("Dictionary CSV", dict_path),
        ("Uncertainty LUT CSV", lut_path),
    ):
        if not path.exists():
            log.error("%s not found: %s", label, path)
            return 1

    # STEP 4.2 always inherits matching criteria from STEP 2.1 to avoid duplicate/overriding knobs.
    ignored_step42_criteria_keys = [
        "feature_columns",
        "distance_metric",
        "interpolation_k",
        "inverse_mapping",
        "histogram_distance_weight",
        "histogram_distance_blend_mode",
        "include_global_rate",
        "global_rate_col",
    ]
    for key in ignored_step42_criteria_keys:
        if cfg_42.get(key, None) not in (None, "", "null", "None"):
            log.info("Ignoring step_4_2.%s; using step_2_1.%s instead.", key, key)

    feature_columns_cfg = cfg_21.get("feature_columns", "auto")
    selected_feature_columns_path_cfg = cfg_21.get("selected_feature_columns_path", None)
    step12_selected_path = (
        _resolve_input_path(selected_feature_columns_path_cfg)
        if selected_feature_columns_path_cfg
        else DEFAULT_STEP12_SELECTED_FEATURE_COLUMNS
    )
    distance_metric = str(cfg_21.get("distance_metric", "l2_zscore"))
    interpolation_k_raw = cfg_21.get("interpolation_k", None)
    if interpolation_k_raw in (None, "", "null", "None"):
        interpolation_k: int | None = None
    else:
        interpolation_k = int(interpolation_k_raw)
    inverse_mapping_cfg_requested = cfg_21.get("inverse_mapping", {})
    include_global_rate = _safe_bool(cfg_21.get("include_global_rate", True), True)
    global_rate_col = str(cfg_21.get("global_rate_col", "events_per_second_global_rate"))
    exclude_same_file = _safe_bool(cfg_42.get("exclude_same_file", False), False)
    shared_parameter_exclusion_ignore_cfg = _parse_column_spec(
        cfg_42.get("shared_parameter_exclusion_ignore", None)
    )
    uncertainty_quantile = _safe_float(cfg_42.get("uncertainty_quantile", 0.68), 0.68)
    uncertainty_quantile = float(np.clip(uncertainty_quantile, 0.0, 1.0))
    contour_eff_band_tolerance_pct = max(
        0.0,
        _safe_float(
            cfg_42.get(
                "iso_rate_efficiency_band_tolerance_pct",
                config.get("iso_rate_efficiency_band_tolerance_pct", 10.0),
            ),
            10.0,
        ),
    )
    if feature_cfg_sources.get("has_common_feature_space"):
        log.info(
            "Feature config source: common_feature_space keys=%s; step_2_1 overrides=%s",
            feature_cfg_sources.get("common_keys", []),
            feature_cfg_sources.get("step_2_1_override_keys", []),
        )
    inherit_step_2_1_method = _safe_bool(
        cfg_42.get("inherit_step_2_1_method", True),
        True,
    )
    n_events_column_cfg = cfg_42.get("n_events_column", "auto")
    derived_feature_subset_mode_requested = str(
        cfg_42.get("derived_feature_subset", "full")
    ).strip().lower()
    if derived_feature_subset_mode_requested not in {
        "full",
        "tt_only",
        "tt_plus_global",
        "tt_plus_global_log",
        "tt_plus_global_eff",
    }:
        log.warning(
            "Invalid step_4_2.derived_feature_subset=%r; using 'full'.",
            derived_feature_subset_mode_requested,
        )
        derived_feature_subset_mode_requested = "full"
    derived_feature_subset_mode = derived_feature_subset_mode_requested
    derived_tt_only_neighbor_count = _safe_int(
        cfg_42.get("derived_tt_only_neighbor_count", 120),
        120,
        minimum=1,
    )
    derived_tt_only_neighbor_selection = str(
        cfg_42.get("derived_tt_only_neighbor_selection", "knn")
    ).strip().lower()
    if derived_tt_only_neighbor_selection not in {"nearest", "knn", "all"}:
        log.warning(
            "Invalid step_4_2.derived_tt_only_neighbor_selection=%r; using 'knn'.",
            derived_tt_only_neighbor_selection,
        )
        derived_tt_only_neighbor_selection = "knn"
    derived_tt_only_weighting = str(
        cfg_42.get("derived_tt_only_weighting", "uniform")
    ).strip().lower()
    if derived_tt_only_weighting not in {"uniform", "inverse_distance", "softmax"}:
        log.warning(
            "Invalid step_4_2.derived_tt_only_weighting=%r; using 'uniform'.",
            derived_tt_only_weighting,
        )
        derived_tt_only_weighting = "uniform"
    derived_tt_only_aggregation = str(
        cfg_42.get("derived_tt_only_aggregation", "local_linear")
    ).strip().lower()
    if derived_tt_only_aggregation not in {"weighted_mean", "weighted_median", "local_linear"}:
        log.warning(
            "Invalid step_4_2.derived_tt_only_aggregation=%r; using 'local_linear'.",
            derived_tt_only_aggregation,
        )
        derived_tt_only_aggregation = "local_linear"
    efficiency_source_prefix_mode = str(
        cfg_42.get("efficiency_source_prefix_mode", "feature_consistent")
    ).strip().lower()
    if efficiency_source_prefix_mode not in {"feature_consistent", "task_chain"}:
        log.warning(
            "Invalid step_4_2.efficiency_source_prefix_mode=%r; using 'feature_consistent'.",
            efficiency_source_prefix_mode,
        )
        efficiency_source_prefix_mode = "feature_consistent"
    task_ids_cfg = cfg_41.get("task_ids", config.get("task_ids", [1]))
    selected_task_ids = _safe_task_ids(task_ids_cfg)
    preferred_tt_prefixes = _preferred_tt_prefixes_for_task_ids(selected_task_ids)
    preferred_feature_prefixes = _preferred_feature_prefixes_for_task_ids(selected_task_ids)
    eff_transform_mode_requested = str(cfg_42.get("eff_transform_mode", "auto")).strip().lower()
    if eff_transform_mode_requested not in {"auto", "inverse", "forward"}:
        eff_transform_mode_requested = "auto"
    eff_transform_clip_input_to_dictionary_domain = _safe_bool(
        cfg_42.get("eff_transform_clip_input_to_dictionary_domain", True),
        True,
    )
    eff_transform_clip_output_to_unit_interval = _safe_bool(
        cfg_42.get("eff_transform_clip_output_to_unit_interval", True),
        True,
    )

    log.info("Real collected: %s", real_path)
    log.info("Dictionary:     %s", dict_path)
    log.info("LUT:            %s", lut_path)
    log.info("Fit summary:    %s", build_summary_path)
    log.info(
        "Efficiency calibration summary: requested=%s used=%s (%s)",
        efficiency_calibration_summary_requested,
        efficiency_calibration_summary_path,
        efficiency_calibration_summary_resolution,
    )
    log.info("Task IDs used for efficiency source: %s", selected_task_ids)
    log.info("Preferred TT prefix order for efficiencies: %s", preferred_tt_prefixes)
    log.info("Preferred TT prefix order for auto features: %s", preferred_feature_prefixes)
    log.info(
        "Method inheritance from STEP 2.1: %s",
        "enabled" if inherit_step_2_1_method else "disabled (legacy STEP 4.2 overrides allowed)",
    )
    log.info("Metric=%s, k=%s, uncertainty_quantile=%.3f", distance_metric, interpolation_k, uncertainty_quantile)

    real_df = pd.read_csv(real_path, low_memory=False)
    dict_df = pd.read_csv(dict_path, low_memory=False)
    if real_df.empty:
        log.error("Real collected table is empty: %s", real_path)
        return 1
    if dict_df.empty:
        log.error("Dictionary table is empty: %s", dict_path)
        return 1
    parameter_space_spec = _load_parameter_space_spec(parameter_space_spec_path)
    default_parameter_space_columns = _load_parameter_space_columns(parameter_space_spec_path)
    real_df, real_alias_cols = _apply_parameter_space_aliases(real_df, parameter_space_spec)
    dict_df, dict_alias_cols = _apply_parameter_space_aliases(dict_df, parameter_space_spec)
    if real_alias_cols or dict_alias_cols:
        log.info(
            "Applied STEP 1 parameter-space aliases: real=%s dictionary=%s",
            real_alias_cols,
            dict_alias_cols,
        )

    # Prepare per-plane empirical efficiencies before feature resolution so
    # derived mode can use efficiency coordinates (same method domain as STEP 2.1).
    # Use the same prefix preference as feature matching (post/fit/...) to keep
    # rate-space and efficiency-space internally consistent.
    feature_eff_source_prefix: dict[str, str | None] = {}
    feature_eff_source_formula: dict[str, dict[str, str]] = {}
    feature_eff_finite_count: dict[str, dict[str, int]] = {}
    for label, source_frame in (("real", real_df), ("dictionary", dict_df)):
        frame = source_frame.copy()
        frame.attrs["preferred_tt_prefixes"] = preferred_feature_prefixes
        eff_feature_by_plane, eff_feature_formula_by_plane, _, source_prefix = _compute_empirical_efficiencies_from_rates(frame)
        feature_eff_source_prefix[label] = source_prefix
        feature_eff_source_formula[label] = {
            f"eff{plane}": str(eff_feature_formula_by_plane.get(plane, "missing_rate_columns"))
            for plane in (1, 2, 3, 4)
        }
        counts_by_plane: dict[str, int] = {}
        injected_cols: dict[str, pd.Series] = {}
        for plane in (1, 2, 3, 4):
            col = f"eff_empirical_{plane}"
            derived_vals = pd.to_numeric(eff_feature_by_plane.get(plane), errors="coerce")
            if col in frame.columns:
                existing = pd.to_numeric(frame[col], errors="coerce")
                injected_cols[col] = existing.where(existing.notna(), derived_vals)
            else:
                injected_cols[col] = derived_vals
            counts_by_plane[f"eff{plane}"] = int(pd.to_numeric(injected_cols[col], errors="coerce").notna().sum())
        if injected_cols:
            frame[list(injected_cols.keys())] = pd.DataFrame(injected_cols, index=frame.index)
        feature_eff_finite_count[label] = counts_by_plane
        if label == "real":
            real_df = frame
        else:
            dict_df = frame
    log.info(
        "Feature empirical efficiencies injected: real_prefix=%s dict_prefix=%s (finite counts real=%s dict=%s)",
        feature_eff_source_prefix.get("real"),
        feature_eff_source_prefix.get("dictionary"),
        feature_eff_finite_count.get("real"),
        feature_eff_finite_count.get("dictionary"),
    )

    feature_mode = str(feature_columns_cfg).strip().lower() if isinstance(feature_columns_cfg, str) else ""
    selected_feature_modes = {
        "step12_selected",
        "step_1_2_selected",
        "selected_from_step12",
        "selected_from_step_1_2",
    }
    auto_resolution_error: str | None = None
    if feature_mode in {"derived", *selected_feature_modes}:
        dict_auto, real_auto = dict_df, real_df
        auto_feature_columns = []
        auto_feature_strategy = "auto_skipped_for_derived"
        auto_feature_mapping = []
    else:
        try:
            dict_auto, real_auto, auto_feature_columns, auto_feature_strategy, auto_feature_mapping = _resolve_feature_columns_auto(
                dict_df=dict_df,
                real_df=real_df,
                include_global_rate=include_global_rate,
                global_rate_col=global_rate_col,
                preferred_prefixes=preferred_feature_prefixes,
            )
        except ValueError as exc:
            auto_resolution_error = str(exc)
            dict_auto, real_auto = dict_df, real_df
            auto_feature_columns = []
            auto_feature_strategy = "auto_unavailable"
            auto_feature_mapping = []
    catalog = sync_feature_column_catalog(
        catalog_path=CONFIG_COLUMNS_PATH,
        dict_df=dict_df,
        default_enabled_columns=auto_feature_columns,
    )
    derived_cfg_raw = cfg_21.get("derived_features", {})
    if not isinstance(derived_cfg_raw, dict):
        derived_cfg_raw = {}
    categories = catalog.get("categories", {})
    if not isinstance(categories, dict):
        categories = {}
    trigger_cfg = categories.get("trigger_type", {})
    if not isinstance(trigger_cfg, dict):
        trigger_cfg = {}
    rate_hist_cfg = categories.get("rate_histogram", {})
    if not isinstance(rate_hist_cfg, dict):
        rate_hist_cfg = {}

    derived_tt_prefix = str(
        derived_cfg_raw.get("prefix", catalog.get("prefix", "last"))
    ).strip() or "last"
    derived_trigger_types = parse_explicit_feature_columns(
        derived_cfg_raw.get("trigger_types", trigger_cfg.get("trigger_types", []))
    )
    derived_trigger_types_override_requested = parse_explicit_feature_columns(
        cfg_42.get("derived_trigger_types_override", None)
    )
    derived_trigger_types_override_applied = False
    if inherit_step_2_1_method:
        if (
            derived_feature_subset_mode_requested != "full"
            or bool(derived_trigger_types_override_requested)
            or any(
                key in cfg_42
                for key in (
                    "derived_tt_only_neighbor_selection",
                    "derived_tt_only_neighbor_count",
                    "derived_tt_only_weighting",
                    "derived_tt_only_aggregation",
                )
            )
        ):
            log.info(
                "STEP 4.2 inherit_step_2_1_method=true: ignoring step_4_2 method overrides "
                "(derived_feature_subset, derived_trigger_types_override, derived_tt_only_*)."
            )
        derived_feature_subset_mode = "full"
    elif derived_trigger_types_override_requested:
        derived_trigger_types = derived_trigger_types_override_requested
        derived_trigger_types_override_applied = True
        log.info(
            "Applied STEP 4.2 trigger-type override for derived features: %s",
            derived_trigger_types,
        )
    derived_include_to_tt = _safe_bool(
        derived_cfg_raw.get(
            "include_to_tt_rate_hz",
            derived_cfg_raw.get(
                "include_to_prefix_rates",
                catalog.get("*_to_*_tt_*_rate_hz", False),
            ),
        ),
        bool(catalog.get("*_to_*_tt_*_rate_hz", False)),
    )
    derived_include_trigger_rates = _safe_bool(
        derived_cfg_raw.get("include_trigger_type_rates", False),
        False,
    )
    derived_include_hist = _safe_bool(
        derived_cfg_raw.get(
            "include_rate_histogram",
            rate_hist_cfg.get("enabled", catalog.get("*_*_rate_hz", False)),
        ),
        bool(rate_hist_cfg.get("enabled", catalog.get("*_*_rate_hz", False))),
    )
    derived_physics_features = _normalize_derived_physics_features(
        derived_cfg_raw.get("physics_features", [])
    )

    def _materialize_derived_feature_space(
        dict_in: pd.DataFrame,
        real_in: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame, str | None, list[str], list[str]]:
        (
            dict_out,
            real_out,
            derived_rate_col_local,
            derived_rate_sources_local,
        ) = _append_derived_tt_global_rate_column(
            dict_df=dict_in,
            data_df=real_in,
            prefix_selector=derived_tt_prefix,
            trigger_type_allowlist=derived_trigger_types,
            include_to_tt_rate_hz=bool(derived_include_to_tt),
        )
        if (
            derived_rate_col_local is None
            and include_global_rate
            and global_rate_col in dict_in.columns
            and global_rate_col in real_in.columns
        ):
            derived_rate_col_local = str(global_rate_col)
        if derived_rate_col_local is None:
            return dict_out, real_out, None, [], []
        (
            dict_out,
            real_out,
            derived_physics_cols_local,
        ) = _append_derived_physics_feature_columns(
            dict_df=dict_out,
            data_df=real_out,
            rate_column=derived_rate_col_local,
            physics_features=derived_physics_features,
        )
        return (
            dict_out,
            real_out,
            str(derived_rate_col_local),
            [str(c) for c in derived_rate_sources_local],
            [str(c) for c in derived_physics_cols_local],
        )
    use_step12_selected = False
    if feature_mode in selected_feature_modes:
        selected_from_step12, selected_info = _load_step12_selected_feature_columns(step12_selected_path)
        dict_selected, real_selected, _, _, _ = _materialize_derived_feature_space(dict_df, real_df)
        try:
            selected = _resolve_selected_step12_feature_columns_strict(
                selected_from_step12,
                dict_df=dict_selected,
                real_df=real_selected,
            )
        except ValueError as exc:
            if selected_info.get("error"):
                log.error(
                    "STEP 1.2 selected features at %s are invalid (%s): %s",
                    step12_selected_path,
                    selected_info.get("error"),
                    exc,
                )
            else:
                log.error("%s", exc)
            return 1
        dict_work, real_work = dict_selected, real_selected
        feature_columns = selected
        feature_strategy = "step12_selected"
        feature_mapping = []
        use_step12_selected = True
        log.info(
            "Using STEP 1.2 selected features (%d) from %s.",
            len(feature_columns),
            step12_selected_path,
        )

    if use_step12_selected:
        pass
    elif feature_mode == "auto":
        if auto_resolution_error is not None:
            log.error("%s", auto_resolution_error)
            return 1
        dict_work, real_work = dict_auto, real_auto
        feature_columns = auto_feature_columns
        feature_strategy = auto_feature_strategy
        feature_mapping = auto_feature_mapping
    elif feature_mode == "derived":
        (
            dict_work,
            real_work,
            derived_rate_col,
            derived_rate_sources,
            derived_physics_cols,
        ) = _materialize_derived_feature_space(dict_df, real_df)
        if derived_rate_col is None:
            log.error(
                "No derived feature global-rate source available. "
                "TT trigger-type sum could not be built and fallback global-rate column is missing."
            )
            return 1
        feat_dict = _shared_derived_feature_columns(
            dict_work,
            rate_column=derived_rate_col,
            trigger_type_rate_columns=(
                derived_rate_sources
                if bool(derived_include_trigger_rates)
                else None
            ),
            include_rate_histogram=bool(derived_include_hist),
            physics_feature_columns=derived_physics_cols,
        )
        feat_real = _shared_derived_feature_columns(
            real_work,
            rate_column=derived_rate_col,
            trigger_type_rate_columns=(
                derived_rate_sources
                if bool(derived_include_trigger_rates)
                else None
            ),
            include_rate_histogram=bool(derived_include_hist),
            physics_feature_columns=derived_physics_cols,
        )
        feature_columns = sorted(set(feat_dict) & set(feat_real))
        if derived_feature_subset_mode != "full":
            subset_cols: list[str] = []
            if derived_feature_subset_mode in {"tt_only", "tt_plus_global", "tt_plus_global_log", "tt_plus_global_eff"}:
                subset_cols.extend([c for c in derived_rate_sources if c in feature_columns])
            if derived_feature_subset_mode in {"tt_plus_global", "tt_plus_global_log", "tt_plus_global_eff"}:
                if derived_rate_col in feature_columns:
                    subset_cols.append(derived_rate_col)
            if derived_feature_subset_mode in {"tt_plus_global_log"}:
                if DERIVED_LOG_RATE_OVER_EFF_PRODUCT_COL in feature_columns:
                    subset_cols.append(DERIVED_LOG_RATE_OVER_EFF_PRODUCT_COL)
            if derived_feature_subset_mode in {"tt_plus_global_eff"}:
                subset_cols.extend(
                    [
                        c
                        for c in ("eff_empirical_1", "eff_empirical_2", "eff_empirical_3", "eff_empirical_4")
                        if c in feature_columns
                    ]
                )
            feature_columns = list(dict.fromkeys(subset_cols))
        if not feature_columns:
            log.error(
                "No derived feature columns found in dictionary/real-data intersection."
            )
            return 1
        feature_strategy = "derived"
        feature_mapping = []
        log.info(
            "Derived features: prefix=%s trigger_types=%s include_hist=%s "
            "include_trigger_rates=%s physics=%s rate_feature=%s rate_sources=%s subset=%s",
            derived_tt_prefix,
            derived_trigger_types,
            bool(derived_include_hist),
            bool(derived_include_trigger_rates),
            derived_physics_features,
            derived_rate_col,
            derived_rate_sources,
            derived_feature_subset_mode,
        )
    elif feature_mode in {"config_columns", "catalog", "config_columns_json"}:
        selected, catalog_info = resolve_feature_columns_from_catalog(
            catalog=catalog,
            available_columns=sorted(set(dict_df.columns) & set(real_df.columns)),
        )
        if catalog_info.get("invalid_include_patterns"):
            log.warning(
                "Ignoring invalid include pattern(s) in %s: %s",
                CONFIG_COLUMNS_PATH,
                catalog_info.get("invalid_include_patterns"),
            )
        if catalog_info.get("invalid_exclude_patterns"):
            log.warning(
                "Ignoring invalid exclude pattern(s) in %s: %s",
                CONFIG_COLUMNS_PATH,
                catalog_info.get("invalid_exclude_patterns"),
            )
        if not selected:
            log.error(
                "No features selected by config_columns catalog. Refusing to fall back to auto, "
                "because that would silently change the STEP 4.2 feature space."
            )
            return 1
        else:
            dict_work, real_work = dict_df, real_df
            feature_columns = selected
            feature_strategy = "config_columns"
            feature_mapping = []
    else:
        explicit_features = parse_explicit_feature_columns(feature_columns_cfg)
        try:
            feature_columns = require_explicit_columns_present_in_both_frames(
                explicit_features,
                left_columns=dict_df.columns,
                right_columns=real_df.columns,
                left_label="dictionary",
                right_label="real data",
                context_label="STEP 4.2",
            )
        except ValueError as exc:
            log.error(str(exc))
            return 1
        if include_global_rate and global_rate_col in dict_df.columns and global_rate_col in real_df.columns:
            if global_rate_col not in feature_columns:
                feature_columns.append(global_rate_col)
        dict_work, real_work = dict_df, real_df
        feature_strategy = "explicit"
        feature_mapping = []

    if not feature_columns:
        log.error("Feature column set is empty after resolution.")
        return 1
    log.info("Using %d features (%s).", len(feature_columns), feature_strategy)
    if feature_strategy == "step12_selected":
        log.info("STEP 1.2 selected-feature artifact: %s", step12_selected_path)

    try:
        dd, inverse_mapping_cfg_runtime, interpolation_k = resolve_runtime_distance_and_inverse_mapping(
            feature_columns=feature_columns,
            inverse_mapping_cfg=inverse_mapping_cfg_requested,
            interpolation_k=interpolation_k,
            context_label="STEP 4.2",
            distance_definition_path=STEP_ROOT / "STEP_1_SETUP" / "STEP_1_5_TUNE_DISTANCE_DEFINITION" / "OUTPUTS" / "FILES" / "distance_definition.json",
            logger=log,
        )
    except ValueError as exc:
        log.error(str(exc))
        return 1
    if (
        not inherit_step_2_1_method
        and feature_mode == "derived"
        and derived_feature_subset_mode == "tt_only"
    ):
        inverse_mapping_cfg_runtime["neighbor_selection"] = str(derived_tt_only_neighbor_selection)
        if derived_tt_only_neighbor_selection == "knn":
            inverse_mapping_cfg_runtime["neighbor_count"] = int(derived_tt_only_neighbor_count)
        else:
            inverse_mapping_cfg_runtime["neighbor_count"] = None
        inverse_mapping_cfg_runtime["weighting"] = str(derived_tt_only_weighting)
        inverse_mapping_cfg_runtime["aggregation"] = str(derived_tt_only_aggregation)
        k_disp = (
            int(derived_tt_only_neighbor_count)
            if derived_tt_only_neighbor_selection == "knn"
            else "all"
        )
        log.info(
            "Applied STEP 4.2 tt_only runtime override: selection=%s k=%s weighting=%s aggregation=%s.",
            str(derived_tt_only_neighbor_selection),
            str(k_disp),
            str(derived_tt_only_weighting),
            str(derived_tt_only_aggregation),
        )
    else:
        if inherit_step_2_1_method and exclude_same_file:
            log.info(
                "Ignoring step_4_2.exclude_same_file=%s; using STEP 2.1 runtime behavior (exclude_same_file=false).",
                exclude_same_file,
            )
        log_runtime_inverse_mapping_summary(log, inverse_mapping_cfg_runtime)

    parameter_space_cfg = cfg_42.get("parameter_space_columns", None)
    param_columns = _resolve_estimation_parameter_columns(
        dictionary_df=dict_work,
        configured_columns=parameter_space_cfg,
        default_columns=default_parameter_space_columns,
    )
    if not param_columns:
        log.error(
            "No parameter-space columns available for STEP 4.2 estimation (spec=%s).",
            parameter_space_spec_path,
        )
        return 1
    log.info("Parameter-space columns used for STEP 4.2 estimation: %s", param_columns)
    est_df = estimate_from_dataframes(
        dict_df=dict_work,
        data_df=real_work,
        feature_columns=feature_columns,
        distance_metric=distance_metric,
        interpolation_k=interpolation_k,
        param_columns=param_columns,
        include_global_rate=False,
        global_rate_col=global_rate_col,
        exclude_same_file=False if inherit_step_2_1_method else exclude_same_file,
        shared_parameter_exclusion_mode="full" if inherit_step_2_1_method else None,
        shared_parameter_exclusion_columns=["param_set_id"] if inherit_step_2_1_method else None,
        shared_parameter_exclusion_ignore=(
            ()
            if inherit_step_2_1_method
            else tuple(shared_parameter_exclusion_ignore_cfg)
        ),
        density_weighting_cfg=None,
        inverse_mapping_cfg=inverse_mapping_cfg_runtime,
        distance_definition=dd,
    )
    inverse_mapping_cfg_k1 = dict(inverse_mapping_cfg_runtime)
    inverse_mapping_cfg_k1["neighbor_selection"] = "knn"
    inverse_mapping_cfg_k1["neighbor_count"] = 1
    est_df_k1 = estimate_from_dataframes(
        dict_df=dict_work,
        data_df=real_work,
        feature_columns=feature_columns,
        distance_metric=distance_metric,
        interpolation_k=interpolation_k,
        param_columns=param_columns,
        include_global_rate=False,
        global_rate_col=global_rate_col,
        exclude_same_file=False if inherit_step_2_1_method else exclude_same_file,
        shared_parameter_exclusion_mode="full" if inherit_step_2_1_method else None,
        shared_parameter_exclusion_columns=["param_set_id"] if inherit_step_2_1_method else None,
        shared_parameter_exclusion_ignore=(
            ()
            if inherit_step_2_1_method
            else tuple(shared_parameter_exclusion_ignore_cfg)
        ),
        density_weighting_cfg=None,
        inverse_mapping_cfg=inverse_mapping_cfg_k1,
        distance_definition=dd,
    )
    eff_oos_masking_summary = est_df.attrs.get(
        "efficiency_feature_out_of_support_masking"
    )

    real_with_idx = real_df.copy()
    real_with_idx["dataset_index"] = np.arange(len(real_with_idx), dtype=int)
    merged = pd.merge(est_df, real_with_idx, on="dataset_index", how="left", suffixes=("", "_real"))
    k1_keep_cols = ["dataset_index"]
    k1_rename_map = {
        "best_distance": "k1_best_distance",
        "n_neighbors_used": "k1_n_neighbors_used",
        "estimation_failure_reason": "k1_estimation_failure_reason",
    }
    for pname in param_columns:
        src = f"est_{pname}"
        if src in est_df_k1.columns:
            k1_keep_cols.append(src)
            k1_rename_map[src] = f"k1_est_{pname}"
    for src in ("best_distance", "n_neighbors_used", "estimation_failure_reason"):
        if src in est_df_k1.columns:
            k1_keep_cols.append(src)
    est_df_k1 = est_df_k1.loc[:, [col for col in k1_keep_cols if col in est_df_k1.columns]].rename(
        columns=k1_rename_map
    )
    merged = pd.merge(merged, est_df_k1, on="dataset_index", how="left")

    if n_events_column_cfg == "auto":
        n_events_col_used = _pick_n_events_column(merged)
    else:
        n_events_col_used = str(n_events_column_cfg) if str(n_events_column_cfg) in merged.columns else None
    if n_events_col_used is not None:
        merged["n_events"] = pd.to_numeric(merged[n_events_col_used], errors="coerce")
    elif "n_events" not in merged.columns:
        merged["n_events"] = np.nan

    # Real-data efficiencies for diagnostics/plots:
    # by default, keep prefix basis consistent with inference features.
    efficiency_source_prefix_order = (
        preferred_feature_prefixes
        if efficiency_source_prefix_mode == "feature_consistent"
        else preferred_tt_prefixes
    )
    merged.attrs["preferred_tt_prefixes"] = efficiency_source_prefix_order
    raw_eff_by_plane, raw_eff_formula_by_plane, raw_eff_cols_by_plane, raw_eff_selected_prefix = _compute_empirical_efficiencies_from_rates(merged)
    for plane in (1, 2, 3, 4):
        merged[f"eff{plane}_raw_from_data"] = raw_eff_by_plane[plane]
        merged[f"eff{plane}_empirical_proxy"] = raw_eff_by_plane[plane]
    eff2_formula = raw_eff_formula_by_plane.get(2, "missing_rate_columns")

    # Dictionary-side efficiencies from rates with the same definition.
    dict_df_plot = dict_df.copy()
    dict_df_plot.attrs["preferred_tt_prefixes"] = efficiency_source_prefix_order
    dict_eff_by_plane, _, dict_eff_cols_by_plane, dict_eff_selected_prefix = _compute_empirical_efficiencies_from_rates(dict_df_plot)
    for plane in (1, 2, 3, 4):
        dict_df_plot[f"dict_eff{plane}_raw_from_rates"] = dict_eff_by_plane[plane]
        dict_df_plot[f"dict_eff{plane}_empirical_proxy"] = dict_eff_by_plane[plane]
    dict_eff2_col = "dict_eff2_empirical_proxy"

    vector_proxy_by_plane_real, vector_proxy_meta_real = _compute_efficiency_vector_median_proxies(merged)
    vector_proxy_by_plane_dict, vector_proxy_meta_dict = _compute_efficiency_vector_median_proxies(dict_df_plot)
    for plane in (1, 2, 3, 4):
        merged[f"eff{plane}_vector_median_proxy"] = vector_proxy_by_plane_real[plane]
        dict_df_plot[f"dict_eff{plane}_vector_median_proxy"] = vector_proxy_by_plane_dict[plane]

    fit_input_domain_by_plane: dict[int, tuple[float, float]] = {}
    for plane in (1, 2, 3, 4):
        vals = pd.to_numeric(dict_eff_by_plane.get(plane), errors="coerce").to_numpy(dtype=float)
        m = np.isfinite(vals)
        if np.any(m):
            lo = float(np.nanmin(vals[m]))
            hi = float(np.nanmax(vals[m]))
            if np.isfinite(lo) and np.isfinite(hi):
                if hi < lo:
                    lo, hi = hi, lo
                fit_input_domain_by_plane[plane] = (lo, hi)

    real_raw_eff_outside_domain_fraction: dict[str, float] = {}
    for plane in (1, 2, 3, 4):
        vals = pd.to_numeric(raw_eff_by_plane.get(plane), errors="coerce").to_numpy(dtype=float)
        m = np.isfinite(vals)
        frac = np.nan
        dom = fit_input_domain_by_plane.get(plane)
        if dom is not None and np.any(m):
            lo, hi = dom
            frac = float(np.mean((vals[m] < lo) | (vals[m] > hi)))
            if eff_transform_clip_input_to_dictionary_domain and frac > 0.0:
                log.warning(
                    "Plane %d: %.1f%% of raw empirical efficiencies lie outside dictionary calibration support [%.4f, %.4f].",
                    plane,
                    100.0 * frac,
                    lo,
                    hi,
                )
        real_raw_eff_outside_domain_fraction[f"eff{plane}"] = frac

    # Preferred global-rate columns for real and dictionary data.
    real_global_rate_col = _pick_global_rate_column(merged, preferred=global_rate_col)
    dict_global_rate_col = _pick_global_rate_column(dict_df_plot, preferred=global_rate_col)

    # Efficiency calibration: load both polynomial and isotonic from STEP 1.2 summary.
    fit_models_by_plane, fit_status, fit_summary_payload = _load_eff_fit_lines(
        efficiency_calibration_summary_path
    )
    isotonic_models_by_plane, isotonic_status = _load_isotonic_calibration(
        efficiency_calibration_summary_path
    )
    eff_calibration_method = str(cfg_42.get("eff_calibration_method", "isotonic")).strip().lower()
    if eff_calibration_method not in {"isotonic", "polynomial"}:
        eff_calibration_method = "isotonic"
    eff_transform_mode, eff_transform_mode_reason = _resolve_eff_transform_mode(
        eff_transform_mode_requested,
        fit_summary_payload,
    )
    fit_order_requested, fit_order_by_plane_from_summary = _read_fit_order_info(
        efficiency_calibration_summary_path
    )

    # Choose calibration method: prefer isotonic, fall back to polynomial.
    use_isotonic = (
        eff_calibration_method == "isotonic"
        and isotonic_status == "ok"
        and len(isotonic_models_by_plane) > 0
    )
    if use_isotonic:
        log.info(
            "Efficiency calibration: isotonic (piecewise-linear monotonic) for %d plane(s).",
            len(isotonic_models_by_plane),
        )
        transformed_eff_by_plane, transformed_eff_formula_by_plane = _transform_efficiencies_isotonic(
            raw_eff_by_plane,
            isotonic_models_by_plane,
        )
        dict_transformed_eff_by_plane, dict_transformed_eff_formula_by_plane = _transform_efficiencies_isotonic(
            dict_eff_by_plane,
            isotonic_models_by_plane,
        )
    else:
        if eff_calibration_method == "isotonic" and isotonic_status != "ok":
            log.warning(
                "Isotonic calibration unavailable (%s); falling back to polynomial transform.",
                isotonic_status,
            )
        log.info(
            "Efficiency transform mode: request=%s -> using=%s (%s)",
            eff_transform_mode_requested,
            eff_transform_mode,
            eff_transform_mode_reason,
        )
        transformed_eff_by_plane, transformed_eff_formula_by_plane = _transform_efficiencies_with_fits(
            raw_eff_by_plane,
            fit_models_by_plane,
            mode=eff_transform_mode,
            input_domain_by_plane=(
                fit_input_domain_by_plane if eff_transform_clip_input_to_dictionary_domain else None
            ),
            clip_output_to_unit_interval=eff_transform_clip_output_to_unit_interval,
        )
        dict_transformed_eff_by_plane, dict_transformed_eff_formula_by_plane = _transform_efficiencies_with_fits(
            dict_eff_by_plane,
            fit_models_by_plane,
            mode=eff_transform_mode,
            input_domain_by_plane=(
                fit_input_domain_by_plane if eff_transform_clip_input_to_dictionary_domain else None
            ),
            clip_output_to_unit_interval=eff_transform_clip_output_to_unit_interval,
        )
    for plane in (1, 2, 3, 4):
        merged[f"eff{plane}_transformed"] = transformed_eff_by_plane[plane]
    for plane in (1, 2, 3, 4):
        dict_df_plot[f"dict_eff{plane}_transformed_from_rates"] = dict_transformed_eff_by_plane[plane]

    dict_rows_total = int(len(dict_df_plot))
    dict_contour_mask = _mask_sim_eff_within_tolerance_band(
        dict_df_plot,
        contour_eff_band_tolerance_pct,
    )
    dict_rows_for_contours = int(np.count_nonzero(dict_contour_mask))
    dict_df_contours = dict_df_plot.loc[dict_contour_mask].copy()
    if dict_rows_for_contours == 0:
        log.warning(
            "No dictionary rows satisfy 4-eff band tolerance (<= %.3f%%); "
            "contour backgrounds will be unavailable.",
            contour_eff_band_tolerance_pct,
        )
    else:
        log.info(
            "Contour-background dictionary rows: %d/%d (4-eff band <= %.3f%%).",
            dict_rows_for_contours,
            dict_rows_total,
            contour_eff_band_tolerance_pct,
        )

    lut_df = load_uncertainty_lut_table(lut_path)
    lut_params = detect_uncertainty_lut_param_names(
        lut_df,
        lut_meta_path if lut_meta_path.exists() else None,
    )
    lut_params = [p for p in lut_params if f"est_{p}" in merged.columns]

    if not lut_params:
        log.warning("No matching LUT parameters found in inference output. Uncertainty columns will be NaN.")

    unc_df = interpolate_uncertainty_columns(
        query_df=merged,
        lut_df=lut_df,
        param_names=lut_params,
        quantile=uncertainty_quantile,
    )
    merged = pd.concat([merged, unc_df], axis=1)

    for pname in lut_params:
        est_col = f"est_{pname}"
        unc_pct_col = f"unc_{pname}_pct"
        unc_abs_col = f"unc_{pname}_abs"
        if est_col in merged.columns and unc_pct_col in merged.columns:
            est_v = pd.to_numeric(merged[est_col], errors="coerce").to_numpy(dtype=float)
            up = pd.to_numeric(merged[unc_pct_col], errors="coerce").to_numpy(dtype=float)
            abs_unc = np.abs(est_v) * np.abs(up) / 100.0
            merged[unc_abs_col] = np.where(np.isfinite(abs_unc), abs_unc, np.nan)
        else:
            merged[unc_abs_col] = np.nan

    flux_param = next((c for c in param_columns if "flux" in str(c).lower()), None)
    flux_est_col = _find_estimated_parameter_column(merged, flux_param) if flux_param else None
    eff_est_col = _choose_primary_eff_est_col(merged)
    distance_col = "best_distance" if "best_distance" in merged.columns else None

    if flux_est_col is None:
        fallback_flux = [c for c in merged.columns if c.startswith("est_") and "flux" in c]
        if fallback_flux:
            flux_est_col = sorted(fallback_flux)[0]
    if distance_col is None:
        log.error("Inference output has no 'best_distance' column.")
        return 1

    success = pd.to_numeric(merged[distance_col], errors="coerce").notna()
    if flux_est_col is not None:
        success &= pd.to_numeric(merged[flux_est_col], errors="coerce").notna()
    if eff_est_col is not None:
        success &= pd.to_numeric(merged[eff_est_col], errors="coerce").notna()
    merged["inference_success"] = success.astype(int)
    n_success = int(merged["inference_success"].sum())
    if n_success == 0:
        n_total = int(len(merged))
        finite_best_distance = int(pd.to_numeric(merged[distance_col], errors="coerce").notna().sum())
        finite_flux = (
            int(pd.to_numeric(merged[flux_est_col], errors="coerce").notna().sum())
            if flux_est_col is not None
            else 0
        )
        finite_eff = (
            int(pd.to_numeric(merged[eff_est_col], errors="coerce").notna().sum())
            if eff_est_col is not None
            else 0
        )
        no_candidate_rows = 0
        if "n_candidates" in merged.columns:
            no_candidate_rows = int(
                (pd.to_numeric(merged["n_candidates"], errors="coerce").fillna(0.0) <= 0.0).sum()
            )
        dict_feature_counts = ", ".join(
            f"{col}={int(pd.to_numeric(dict_work[col], errors='coerce').notna().sum())}"
            for col in feature_columns[:6]
            if col in dict_work.columns
        )
        real_feature_counts = ", ".join(
            f"{col}={int(pd.to_numeric(real_work[col], errors='coerce').notna().sum())}"
            for col in feature_columns[:6]
            if col in real_work.columns
        )
        if len(feature_columns) > 6:
            dict_feature_counts += ", ..."
            real_feature_counts += ", ..."
        log.warning(
            "Inference produced 0/%d successful rows (best_distance finite=%d, flux finite=%d, eff finite=%d, no-candidate rows=%d). "
            "Feature finite counts (dict): %s | (real): %s",
            n_total,
            finite_best_distance,
            finite_flux,
            finite_eff,
            no_candidate_rows,
            dict_feature_counts or "n/a",
            real_feature_counts or "n/a",
        )

    x, x_label, has_time_axis = _time_axis(merged)
    if has_time_axis:
        merged = merged.assign(execution_time_for_plot=x)

    n_parameter_series_panels = _plot_parameter_estimate_series(
        x=x,
        has_time_axis=has_time_axis,
        xlabel=x_label,
        df=merged,
        parameter_columns=param_columns,
        out_path=PLOT_PARAMETER_SERIES,
    )
    n_parameter_series_vs_k1_panels = _plot_parameter_estimate_series_vs_k1(
        x=x,
        has_time_axis=has_time_axis,
        xlabel=x_label,
        df=merged,
        parameter_columns=param_columns,
        out_path=PLOT_PARAMETER_SERIES_VS_K1,
    )
    distance_term_dominance_summary = _plot_distance_term_dominance(
        x=x,
        has_time_axis=has_time_axis,
        xlabel=x_label,
        df=merged,
        out_path=PLOT_DISTANCE_DOMINANCE,
    )
    grouped_diag_cfg = cfg_42.get("grouped_feature_diagnostic", {}) or {}
    grouped_diag_enabled = bool(grouped_diag_cfg.get("enabled", True))
    grouped_diag_selector = str(grouped_diag_cfg.get("selector", "largest_best_distance"))
    grouped_diag_top_k = int(grouped_diag_cfg.get("top_k", 10) or 10)
    grouped_case_summary = _plot_grouped_case_diagnostic_real(
        dict_df=dict_work,
        data_df=real_work,
        result_df=merged,
        param_cols=param_columns,
        feature_cols=feature_columns,
        distance_definition=dd,
        case_selector=grouped_diag_selector,
        top_k=max(grouped_diag_top_k, 1),
        out_path=PLOT_GROUPED_CASE,
        neighbors_csv_path=GROUPED_CASE_NEIGHBORS_CSV,
    ) if grouped_diag_enabled else {
        "plot_available": False,
        "selector": grouped_diag_selector,
        "plot_path": str(PLOT_GROUPED_CASE),
        "neighbors_csv_path": str(GROUPED_CASE_NEIGHBORS_CSV),
    }
    inverse_proxy_case_summary = _plot_inverse_estimate_vs_k1_proxy_case(
        dict_df=dict_work,
        result_df=merged,
        param_cols=param_columns,
        grouped_case_summary=grouped_case_summary,
        inverse_mapping_cfg=inverse_mapping_cfg_runtime,
        out_path=PLOT_INVERSE_PROXY_CASE,
        out_csv_path=INVERSE_PROXY_CASE_CSV,
    ) if grouped_diag_enabled else {
        "plot_available": False,
        "plot_path": str(PLOT_INVERSE_PROXY_CASE),
        "csv_path": str(INVERSE_PROXY_CASE_CSV),
    }

    k1_proxy_delta_summary: dict[str, float | None] = {}
    for pname in param_columns:
        est_col = _find_estimated_parameter_column(merged, pname)
        k1_col = f"k1_est_{pname}"
        if est_col is None or k1_col not in merged.columns:
            continue
        est_vals = pd.to_numeric(merged.get(est_col), errors="coerce").to_numpy(dtype=float)
        k1_vals = pd.to_numeric(merged.get(k1_col), errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(est_vals) & np.isfinite(k1_vals)
        if not np.any(valid):
            k1_proxy_delta_summary[pname] = None
            continue
        denom = np.maximum(np.abs(k1_vals[valid]), 1e-12)
        delta_pct = 100.0 * np.abs(est_vals[valid] - k1_vals[valid]) / denom
        k1_proxy_delta_summary[pname] = float(np.median(delta_pct)) if np.isfinite(delta_pct).any() else None

    out_csv = FILES_DIR / "real_results.csv"
    merged.to_csv(out_csv, index=False)
    log.info("Wrote real results: %s (%d rows)", out_csv, len(merged))

    flux_unc_abs_col = None
    eff_unc_abs_col = None
    if flux_est_col is not None:
        flux_param = flux_est_col.replace("est_", "", 1)
        candidate = f"unc_{flux_param}_abs"
        if candidate in merged.columns:
            flux_unc_abs_col = candidate
    if eff_est_col is not None:
        eff_param = eff_est_col.replace("est_", "", 1)
        candidate = f"unc_{eff_param}_abs"
        if candidate in merged.columns:
            eff_unc_abs_col = candidate

    eff2_plot_source_cfg = str(cfg_42.get("eff2_global_rate_eff_source", "auto")).strip().lower()
    proxy_source_aliases = {
        "raw": "empirical_proxy",
        "empirical": "empirical_proxy",
        "empirical_proxy": "empirical_proxy",
        "transformed": "transformed_proxy",
        "transformed_proxy": "transformed_proxy",
        "vector_median": "vector_median_proxy",
        "vector_median_proxy": "vector_median_proxy",
        "auto": "auto",
    }
    eff2_plot_source_cfg = proxy_source_aliases.get(eff2_plot_source_cfg, eff2_plot_source_cfg)
    if eff2_plot_source_cfg not in {"auto", "empirical_proxy", "transformed_proxy", "vector_median_proxy"}:
        log.warning(
            "Invalid step_4_2.eff2_global_rate_eff_source=%r; using 'auto'.",
            eff2_plot_source_cfg,
        )
        eff2_plot_source_cfg = "auto"

    has_real_eff2_trans = (
        "eff2_transformed" in merged.columns
        and pd.to_numeric(merged["eff2_transformed"], errors="coerce").notna().any()
    )
    has_dict_eff2_trans = (
        "dict_eff2_transformed_from_rates" in dict_df_plot.columns
        and pd.to_numeric(dict_df_plot["dict_eff2_transformed_from_rates"], errors="coerce").notna().any()
    )
    has_real_eff2_vector_proxy = (
        "eff2_vector_median_proxy" in merged.columns
        and pd.to_numeric(merged["eff2_vector_median_proxy"], errors="coerce").notna().any()
    )
    has_dict_eff2_vector_proxy = (
        "dict_eff2_vector_median_proxy" in dict_df_plot.columns
        and pd.to_numeric(dict_df_plot["dict_eff2_vector_median_proxy"], errors="coerce").notna().any()
    )
    transformed_available = has_real_eff2_trans and has_dict_eff2_trans
    vector_proxy_available = has_real_eff2_vector_proxy and has_dict_eff2_vector_proxy
    real_eff2_trans_frac_physical = (
        _fraction_in_closed_interval(merged["eff2_transformed"], 0.0, 1.0)
        if has_real_eff2_trans
        else 0.0
    )
    dict_eff2_trans_frac_physical = (
        _fraction_in_closed_interval(dict_df_plot["dict_eff2_transformed_from_rates"], 0.0, 1.0)
        if has_dict_eff2_trans
        else 0.0
    )
    transformed_eff_frac_physical_real: dict[str, float] = {}
    transformed_eff_frac_physical_dict: dict[str, float] = {}
    transformed_eff_boundary_metrics_real: dict[str, dict[str, float]] = {}
    transformed_eff_boundary_metrics_dict: dict[str, dict[str, float]] = {}
    for plane in (1, 2, 3, 4):
        real_col = f"eff{plane}_transformed"
        dict_col = f"dict_eff{plane}_transformed_from_rates"
        transformed_eff_frac_physical_real[f"eff{plane}"] = (
            _fraction_in_closed_interval(merged[real_col], 0.0, 1.0)
            if real_col in merged.columns
            else 0.0
        )
        transformed_eff_frac_physical_dict[f"eff{plane}"] = (
            _fraction_in_closed_interval(dict_df_plot[dict_col], 0.0, 1.0)
            if dict_col in dict_df_plot.columns
            else 0.0
        )
        transformed_eff_boundary_metrics_real[f"eff{plane}"] = (
            _boundary_fraction_metrics(merged[real_col])
            if real_col in merged.columns
            else _boundary_fraction_metrics(pd.Series(dtype=float))
        )
        transformed_eff_boundary_metrics_dict[f"eff{plane}"] = (
            _boundary_fraction_metrics(dict_df_plot[dict_col])
            if dict_col in dict_df_plot.columns
            else _boundary_fraction_metrics(pd.Series(dtype=float))
        )

    eff2_proxy_source_used = "empirical_proxy"
    if eff2_plot_source_cfg == "empirical_proxy":
        eff2_proxy_source_used = "empirical_proxy"
    elif eff2_plot_source_cfg == "vector_median_proxy":
        if vector_proxy_available:
            eff2_proxy_source_used = "vector_median_proxy"
        else:
            log.warning(
                "Requested plane-2 vector-median proxy is unavailable; falling back to empirical proxy."
            )
    elif eff2_plot_source_cfg == "transformed_proxy":
        if transformed_available:
            eff2_proxy_source_used = "transformed_proxy"
        else:
            log.warning(
                "Requested plane-2 transformed proxy is unavailable; falling back to empirical proxy."
            )
    else:
        # Auto: only trust transformed proxies when both real and dictionary are
        # predominantly within physical bounds; otherwise use direct empirical proxy.
        use_transformed_eff2_for_plane_plot = (
            transformed_available
            and real_eff2_trans_frac_physical >= 0.95
            and dict_eff2_trans_frac_physical >= 0.95
        )
        if transformed_available and not use_transformed_eff2_for_plane_plot:
            log.warning(
                "Fallback to empirical plane-2 proxy: transformed physical fractions "
                "(real=%.3f, dict=%.3f) below threshold 0.95.",
                real_eff2_trans_frac_physical,
                dict_eff2_trans_frac_physical,
            )
        if use_transformed_eff2_for_plane_plot:
            eff2_proxy_source_used = "transformed_proxy"

    if eff2_proxy_source_used == "transformed_proxy":
        eff2_real_col_for_plane_plot = "eff2_transformed"
        dict_eff2_col_for_plane_plot = "dict_eff2_transformed_from_rates"
    elif eff2_proxy_source_used == "vector_median_proxy":
        eff2_real_col_for_plane_plot = "eff2_vector_median_proxy"
        dict_eff2_col_for_plane_plot = "dict_eff2_vector_median_proxy"
    else:
        eff2_real_col_for_plane_plot = "eff2_empirical_proxy"
        dict_eff2_col_for_plane_plot = "dict_eff2_empirical_proxy"

    if eff2_proxy_source_used == "transformed_proxy":
        eff2_real_proxy_formula = transformed_eff_formula_by_plane.get(2)
        dict_eff2_proxy_formula = dict_transformed_eff_formula_by_plane.get(2)
    elif eff2_proxy_source_used == "vector_median_proxy":
        eff2_real_proxy_formula = (
            "median(" + ", ".join(vector_proxy_meta_real.get(2, {}).get("columns", [])) + ")"
            if vector_proxy_meta_real.get(2, {}).get("columns")
            else "missing_efficiency_vector_bins"
        )
        dict_eff2_proxy_formula = (
            "median(" + ", ".join(vector_proxy_meta_dict.get(2, {}).get("columns", [])) + ")"
            if vector_proxy_meta_dict.get(2, {}).get("columns")
            else "missing_efficiency_vector_bins"
        )
    else:
        eff2_real_proxy_formula = eff2_formula
        dict_eff2_proxy_formula = "raw_from_rates"

    log.info(
        "Plane-2 global-rate diagnostic proxy: source=%s real_y=%s dict_y=%s",
        eff2_proxy_source_used,
        eff2_real_col_for_plane_plot,
        dict_eff2_col_for_plane_plot,
    )

    n_est_curve_real = 0
    n_est_curve_dict = 0
    est_curve_eff_col = _pick_estimated_eff_col_for_plane(merged, plane=2)
    dict_curve_eff_col = _pick_dictionary_eff_col_for_plane(dict_df_plot, plane=2)
    if len(param_columns) >= 2:
        n_est_curve_real, n_est_curve_dict = _plot_estimated_curve_flux_vs_eff(
            real_df=merged,
            dict_df=dict_df_contours,
            parameter_columns=param_columns,
            out_path=PLOT_EST_CURVE,
        )
    else:
        missing = []
        if len(param_columns) < 2:
            missing.append("at least two resolved parameter-space dimensions")
        _plot_placeholder(
            PLOT_EST_CURVE,
            "Estimated curve in parameter space",
            "Cannot build plot: missing " + ", ".join(missing) + ".",
        )

    story_eff_col = eff_est_col if eff_est_col is not None else est_curve_eff_col
    story_eff_series_map: dict[str, pd.Series] = {}
    for plane in (1, 2, 3, 4):
        col = f"est_eff_sim_{plane}"
        if col in merged.columns and pd.to_numeric(merged[col], errors="coerce").notna().any():
            story_eff_series_map[col] = merged[col]
    if not story_eff_series_map and story_eff_col is not None and story_eff_col in merged.columns:
        story_eff_series_map[story_eff_col] = merged[story_eff_col]

    if flux_est_col is not None and story_eff_col is not None and real_global_rate_col is not None:
        _plot_flux_recovery_story_real(
            x=x,
            has_time_axis=has_time_axis,
            xlabel=x_label,
            distance_series=merged[distance_col],
            distance_label=distance_col,
            eff_series=merged[story_eff_col],
            eff_label=story_eff_col,
            eff_series_map=story_eff_series_map,
            global_rate_series=merged[real_global_rate_col],
            global_rate_label=real_global_rate_col,
            flux_est_series=merged[flux_est_col],
            flux_unc_series=merged[flux_unc_abs_col] if flux_unc_abs_col is not None else None,
            flux_reference_series=None,
            flux_reference_label="Reference flux",
            out_path=PLOT_RECOVERY_STORY,
        )
    else:
        missing = []
        if flux_est_col is None:
            missing.append("estimated flux column")
        if story_eff_col is None:
            missing.append("estimated efficiency column")
        if real_global_rate_col is None:
            missing.append("real global_rate column")
        _plot_placeholder(
            PLOT_RECOVERY_STORY,
            "Real-data recovery story",
            "Cannot build plot: missing " + ", ".join(missing) + ".",
        )

    estimated_eff_boundary_metrics: dict[str, dict[str, float]] = {}
    for plane in (1, 2, 3, 4):
        est_col = f"est_eff_sim_{plane}"
        if est_col in merged.columns:
            estimated_eff_boundary_metrics[f"eff{plane}"] = _boundary_fraction_metrics(merged[est_col])

    distance_group_summary: dict[str, dict[str, float] | None] = {}
    for label, col in (
        ("eff_empirical", "best_distance_base_share_eff_empirical"),
        ("tt_rates", "best_distance_base_share_tt_rates"),
        ("other", "best_distance_base_share_other"),
    ):
        if col not in merged.columns:
            distance_group_summary[label] = None
            continue
        vals = pd.to_numeric(merged[col], errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(vals).any():
            distance_group_summary[label] = None
            continue
        distance_group_summary[label] = {
            "median": float(np.nanmedian(vals)),
            "p90": float(np.nanpercentile(vals, 90)),
        }

    ts_valid = pd.Series([], dtype="datetime64[ns]")
    if has_time_axis:
        ts_valid = pd.to_datetime(x, errors="coerce").dropna()

    summary = {
        "real_collected_csv": str(real_path),
        "dictionary_csv": str(dict_path),
        "uncertainty_lut_csv": str(lut_path),
        "matching_criteria_source": "step_2_1",
        "parameter_space_spec_json": str(parameter_space_spec_path),
        "parameter_space_spec_columns_default": default_parameter_space_columns,
        "parameter_space_columns_config": parameter_space_cfg,
        "parameter_space_columns_used": param_columns,
        "parameter_series_plot": str(PLOT_PARAMETER_SERIES),
        "parameter_series_plot_panels": int(n_parameter_series_panels),
        "parameter_series_vs_k1_plot": str(PLOT_PARAMETER_SERIES_VS_K1),
        "parameter_series_vs_k1_plot_panels": int(n_parameter_series_vs_k1_panels),
        "distance_term_dominance_plot": str(PLOT_DISTANCE_DOMINANCE),
        "distance_term_dominance_summary": distance_term_dominance_summary,
        "parameter_estimate_columns": {
            pname: _find_estimated_parameter_column(merged, pname)
            for pname in param_columns
            if _find_estimated_parameter_column(merged, pname) is not None
        },
        "distance_metric": distance_metric,
        "distance_definition_used": dd is not None,
        "distance_definition_mode": dd["selected_mode"] if dd is not None else None,
        "interpolation_k": interpolation_k,
        "inverse_mapping": inverse_mapping_cfg_requested,
        "inverse_mapping_runtime_applied": inverse_mapping_cfg_runtime,
        "k1_proxy_inverse_mapping_runtime": inverse_mapping_cfg_k1,
        "inherit_step_2_1_method": bool(inherit_step_2_1_method),
        "shared_parameter_exclusion_ignore": shared_parameter_exclusion_ignore_cfg,
        "feature_strategy": feature_strategy,
        "derived_feature_subset_mode_requested": derived_feature_subset_mode_requested,
        "derived_feature_subset_mode": derived_feature_subset_mode,
        "derived_trigger_types_used": derived_trigger_types,
        "derived_trigger_types_override_applied": bool(derived_trigger_types_override_applied),
        "n_features_used": int(len(feature_columns)),
        "feature_columns_used": feature_columns,
        "n_rows": int(len(merged)),
        "n_successful_rows": int(merged["inference_success"].sum()),
        "coverage_fraction": float(merged["inference_success"].mean()),
        "n_successful_parameter_estimates": {
            pname: int(pd.to_numeric(merged.get(_find_estimated_parameter_column(merged, pname)), errors="coerce").notna().sum())
            for pname in param_columns
            if _find_estimated_parameter_column(merged, pname) is not None
        },
        "flux_estimate_column": flux_est_col,
        "eff_estimate_column": eff_est_col,
        "distance_column": distance_col,
        "n_events_column_used": n_events_col_used,
        "real_global_rate_column_used": real_global_rate_col,
        "dictionary_global_rate_column_used": dict_global_rate_col,
        "iso_rate_efficiency_band_tolerance_pct": float(contour_eff_band_tolerance_pct),
        "dictionary_rows_total_for_iso_rate_contours": int(dict_rows_total),
        "dictionary_rows_for_iso_rate_contours": int(dict_rows_for_contours),
        "dictionary_rows_excluded_iso_rate_eff_band": int(dict_rows_total - dict_rows_for_contours),
        "build_summary_json_used": str(build_summary_path),
        "efficiency_calibration_summary_json_requested": str(
            efficiency_calibration_summary_requested
        ),
        "efficiency_calibration_summary_json_used": str(
            efficiency_calibration_summary_path
        ),
        "efficiency_calibration_summary_resolution": efficiency_calibration_summary_resolution,
        "fit_lines_load_status": fit_status,
        "fit_polynomial_relation_from_summary": fit_summary_payload.get("fit_polynomial_relation"),
        "fit_polynomial_x_variable_from_summary": fit_summary_payload.get("fit_polynomial_x_variable"),
        "fit_polynomial_y_variable_from_summary": fit_summary_payload.get("fit_polynomial_y_variable"),
        "fit_polynomial_order_requested": fit_order_requested,
        "fit_polynomial_order_by_plane": fit_order_by_plane_from_summary,
        "fit_lines_by_plane": {
            str(k): {"a": float(v[0]), "b": float(v[1])}
            for k, v in fit_models_by_plane.items()
            if len(v) == 2
        },
        "fit_polynomials_by_plane": {
            str(k): {
                "order": int(len(v) - 1),
                "coefficients": [float(c) for c in v],
            }
            for k, v in fit_models_by_plane.items()
        },
        "eff_calibration_method_requested": eff_calibration_method,
        "eff_calibration_method_used": "isotonic" if use_isotonic else "polynomial",
        "isotonic_calibration_status": isotonic_status,
        "eff_transform_mode_requested": eff_transform_mode_requested,
        "eff_transform_mode": eff_transform_mode,
        "eff_transform_mode_resolution_reason": eff_transform_mode_reason,
        "eff_transform_clip_input_to_dictionary_domain": bool(
            eff_transform_clip_input_to_dictionary_domain
        ),
        "eff_transform_clip_output_to_unit_interval": bool(
            eff_transform_clip_output_to_unit_interval
        ),
        "eff_transform_input_domain_by_plane": {
            f"eff{p}": {
                "min": (
                    float(fit_input_domain_by_plane[p][0])
                    if p in fit_input_domain_by_plane
                    else None
                ),
                "max": (
                    float(fit_input_domain_by_plane[p][1])
                    if p in fit_input_domain_by_plane
                    else None
                ),
            }
            for p in (1, 2, 3, 4)
        },
        "real_raw_efficiency_fraction_outside_fit_domain_by_plane": {
            f"eff{p}": (
                float(real_raw_eff_outside_domain_fraction.get(f"eff{p}"))
                if np.isfinite(real_raw_eff_outside_domain_fraction.get(f"eff{p}", np.nan))
                else None
            )
            for p in (1, 2, 3, 4)
        },
        "raw_efficiency_columns": {
            "eff1": "eff1_raw_from_data",
            "eff2": "eff2_raw_from_data",
            "eff3": "eff3_raw_from_data",
            "eff4": "eff4_raw_from_data",
        },
        "empirical_efficiency_proxy_columns": {
            "eff1": "eff1_empirical_proxy",
            "eff2": "eff2_empirical_proxy",
            "eff3": "eff3_empirical_proxy",
            "eff4": "eff4_empirical_proxy",
        },
        "vector_median_efficiency_proxy_columns": {
            "eff1": "eff1_vector_median_proxy",
            "eff2": "eff2_vector_median_proxy",
            "eff3": "eff3_vector_median_proxy",
            "eff4": "eff4_vector_median_proxy",
        },
        "vector_median_efficiency_proxy_metadata_real": {
            f"eff{p}": vector_proxy_meta_real.get(p, {})
            for p in (1, 2, 3, 4)
        },
        "vector_median_efficiency_proxy_metadata_dictionary": {
            f"eff{p}": vector_proxy_meta_dict.get(p, {})
            for p in (1, 2, 3, 4)
        },
        "efficiency_source_task_ids": selected_task_ids,
        "efficiency_source_most_advanced_task_id": int(max(selected_task_ids)) if selected_task_ids else 1,
        "efficiency_source_prefix_mode": efficiency_source_prefix_mode,
        "efficiency_source_preferred_prefix_order": efficiency_source_prefix_order,
        "efficiency_source_prefix_used_real": raw_eff_selected_prefix,
        "efficiency_source_prefix_used_dictionary": dict_eff_selected_prefix,
        "feature_empirical_efficiency_preferred_prefix_order": preferred_feature_prefixes,
        "feature_empirical_efficiency_prefix_used_real": feature_eff_source_prefix.get("real"),
        "feature_empirical_efficiency_prefix_used_dictionary": feature_eff_source_prefix.get("dictionary"),
        "feature_empirical_efficiency_finite_counts": feature_eff_finite_count,
        "feature_empirical_efficiency_formulas": feature_eff_source_formula,
        "raw_efficiency_formulas": {f"eff{p}": raw_eff_formula_by_plane.get(p) for p in (1, 2, 3, 4)},
        "raw_efficiency_rate_columns": {
            f"eff{p}": raw_eff_cols_by_plane.get(p, {})
            for p in (1, 2, 3, 4)
        },
        "transformed_efficiency_proxy_columns": {
            "eff1": "eff1_transformed",
            "eff2": "eff2_transformed",
            "eff3": "eff3_transformed",
            "eff4": "eff4_transformed",
        },
        "transformed_efficiency_proxy_formulas": {
            f"eff{p}": transformed_eff_formula_by_plane.get(p)
            for p in (1, 2, 3, 4)
        },
        "eff2_proxy_column": eff2_real_col_for_plane_plot,
        "eff2_real_column": eff2_real_col_for_plane_plot,
        "eff2_global_rate_proxy_source_requested": eff2_plot_source_cfg,
        "eff2_global_rate_eff_source_requested": eff2_plot_source_cfg,
        "eff2_global_rate_proxy_source_used": eff2_proxy_source_used,
        "eff2_global_rate_eff_source_used": eff2_proxy_source_used,
        "eff2_global_rate_transformed_fraction_in_0_1": {
            "real": float(real_eff2_trans_frac_physical),
            "dictionary": float(dict_eff2_trans_frac_physical),
        },
        "transformed_efficiency_fraction_in_0_1_by_plane": {
            "real": transformed_eff_frac_physical_real,
            "dictionary": transformed_eff_frac_physical_dict,
        },
        "transformed_efficiency_boundary_metrics_by_plane": {
            "real": transformed_eff_boundary_metrics_real,
            "dictionary": transformed_eff_boundary_metrics_dict,
        },
        "estimated_efficiency_boundary_metrics_by_plane": estimated_eff_boundary_metrics,
        "best_match_non_hist_distance_share": distance_group_summary,
        "efficiency_feature_out_of_support_masking": (
            eff_oos_masking_summary if isinstance(eff_oos_masking_summary, dict) else None
        ),
        "eff2_proxy_formula": eff2_real_proxy_formula,
        "eff2_formula": eff2_real_proxy_formula,
        "eff2_raw_formula": eff2_formula,
        "eff2_transformed_formula": transformed_eff_formula_by_plane.get(2),
        "eff2_real_rate_columns": raw_eff_cols_by_plane.get(2, {}),
        "eff2_dictionary_proxy_column": dict_eff2_col_for_plane_plot,
        "eff2_dictionary_eff_column": dict_eff2_col_for_plane_plot,
        "eff2_dictionary_proxy_formula": dict_eff2_proxy_formula,
        "eff2_dictionary_eff_formula": dict_eff2_proxy_formula,
        "eff2_dictionary_rate_columns": {
            "three_plane_col": dict_eff_cols_by_plane.get(2, {}).get("three_plane_col"),
            "four_plane_col": dict_eff_cols_by_plane.get(2, {}).get("four_plane_col"),
        },
        "estimated_curve_eff_column": est_curve_eff_col,
        "dictionary_curve_eff_column": dict_curve_eff_col,
        "n_estimated_curve_points": int(n_est_curve_real),
        "n_dictionary_curve_background_points": int(n_est_curve_dict),
        "estimated_curve_plot": str(PLOT_EST_CURVE),
        "recovery_story_plot": str(PLOT_RECOVERY_STORY),
        "recovery_story_eff_column": story_eff_col,
        "recovery_story_global_rate_column": real_global_rate_col,
        "recovery_story_flux_column": flux_est_col,
        "grouped_case_diagnostic": grouped_case_summary,
        "inverse_proxy_case_diagnostic": inverse_proxy_case_summary,
        "k1_proxy_parameter_median_abs_relative_delta_pct": k1_proxy_delta_summary,
        "parameter_space_estimate_uncertainty_medians_pct": {
            pname: _series_median_or_none(merged.get(f"unc_{pname}_pct"))
            for pname in param_columns
            if f"unc_{pname}_pct" in merged.columns
        },
        "lut_param_names_used": lut_params,
        "uncertainty_quantile": uncertainty_quantile,
        "has_time_axis": bool(has_time_axis),
        "time_min_utc": str(ts_valid.min()) if len(ts_valid) else None,
        "time_max_utc": str(ts_valid.max()) if len(ts_valid) else None,
        "feature_mapping_preview": feature_mapping[:25],
    }
    out_summary = FILES_DIR / "real_analysis_summary.json"
    out_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log.info("Wrote summary: %s", out_summary)
    log.info("Wrote plots in: %s", PLOTS_DIR)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
