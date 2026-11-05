#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_2_INFERENCE/STEP_2_1_ESTIMATE_PARAMS/estimate_and_plot.py
Purpose: STEP 2.1 — Inverse problem: estimate physics parameters from feature vectors.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-11
Runtime: python3
Usage: python3 .../estimate_and_plot.py [--config CONFIG] [--dictionary-csv PATH] [--dataset-csv PATH]
Inputs: dictionary.csv and dataset.csv from STEP 1.4, selected_feature_columns.json.
Outputs: estimated_params.csv, estimation_summary.json, diagnostic plots.
Notes: Simplified single-stage kNN with IDW in z-scored feature space.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Mapping

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.spatial import Delaunay

# ── Paths ────────────────────────────────────────────────────────────
STEP_DIR = Path(__file__).resolve().parent
INFERENCE_DIR = STEP_DIR.parent
PIPELINE_DIR = INFERENCE_DIR.parent
PROJECT_DIR = PIPELINE_DIR.parent
DEFAULT_CONFIG = (
    PIPELINE_DIR / "STEP_1_SETUP" / "STEP_1_1_COLLECT_DATA" / "INPUTS" / "config_step_1.1_method.json"
)

DEFAULT_DICTIONARY = (
    PIPELINE_DIR / "STEP_1_SETUP" / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY"
    / "OUTPUTS" / "FILES" / "dictionary.csv"
)
DEFAULT_DATASET = (
    PIPELINE_DIR / "STEP_1_SETUP" / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY"
    / "OUTPUTS" / "FILES" / "dataset.csv"
)
DEFAULT_FEATURE_COLUMNS = (
    PIPELINE_DIR / "STEP_1_SETUP" / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY"
    / "OUTPUTS" / "FILES" / "selected_feature_columns.json"
)
DEFAULT_DISTANCE_DEFINITION = (
    PIPELINE_DIR / "STEP_1_SETUP" / "STEP_1_5_TUNE_DISTANCE_DEFINITION"
    / "OUTPUTS" / "FILES" / "distance_definition.json"
)

FILES_DIR = STEP_DIR / "OUTPUTS" / "FILES"
PLOTS_DIR = STEP_DIR / "OUTPUTS" / "PLOTS"
FILES_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

PARAM_COLUMNS = ["flux_cm2_min", "eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4"]

logging.basicConfig(
    format="[%(levelname)s] STEP_2.1 — %(message)s", level=logging.INFO
)
log = logging.getLogger("STEP_2.1")

# ── Import shared estimation engine ──────────────────────────────────
sys.path.insert(0, str(INFERENCE_DIR))
try:
    from inference_runtime import (
        load_selected_feature_columns_artifact,
        log_runtime_inverse_mapping_summary,
        require_selected_feature_columns_present,
        resolve_runtime_distance_and_inverse_mapping,
    )
    from estimate_parameters import (
        _combine_distance_terms_with_breakdown,
        _efficiency_vector_group_distance_many,
        _filter_efficiency_vector_payloads,
        _histogram_distance_many,
        _prepare_efficiency_vector_group_payloads,
        _reduce_efficiency_vector_group_stack,
        _resolve_efficiency_vector_distance_cfg,
        _resolve_histogram_distance_cfg,
        _weighted_lp_many,
        estimate_from_dataframes,
    )
except Exception as exc:
    log.error("Failed to import estimate_parameters from %s: %s", INFERENCE_DIR, exc)
    raise

_FIGURE_COUNTER = 0
FIGURE_STEP_PREFIX = "2_1"

_PLOT_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".svg", ".pdf", ".eps",
    ".tif", ".tiff", ".bmp", ".gif", ".webp",
}


def _save_figure(fig: plt.Figure, path: Path, **kwargs) -> None:
    global _FIGURE_COUNTER
    _FIGURE_COUNTER += 1
    out_path = path.with_name(f"{FIGURE_STEP_PREFIX}_{_FIGURE_COUNTER}_{path.name}")
    fig.savefig(out_path, **kwargs)


def _clear_plots_dir() -> None:
    removed = 0
    for f in PLOTS_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in _PLOT_EXTENSIONS:
            f.unlink()
            removed += 1
    log.info("Cleared %d old plot(s) from %s", removed, PLOTS_DIR)


# =====================================================================
# Core estimation
# =====================================================================

def _load_feature_columns(path: Path) -> list[str]:
    """Load feature column list from the step 1.4 artifact."""
    return load_selected_feature_columns_artifact(path)


def _require_selected_feature_columns_present(
    feature_cols: list[str],
    *,
    dict_df: pd.DataFrame,
    data_df: pd.DataFrame,
) -> list[str]:
    return require_selected_feature_columns_present(
        feature_cols,
        dict_df=dict_df,
        data_df=data_df,
        context_label="STEP 2.1",
        right_label="dataset",
    )


def _load_config(path: Path) -> dict:
    """Load and merge method + plots + runtime configs."""
    cfg: dict = {}
    if path.exists():
        cfg = json.loads(path.read_text(encoding="utf-8"))
    for extra_name in ("config_step_1.1_plots.json", "config_step_1.1_runtime.json"):
        extra = path.with_name(extra_name)
        if extra.exists() and extra != path:
            extra_cfg = json.loads(extra.read_text(encoding="utf-8"))
            cfg.update(extra_cfg)
    return cfg


# =====================================================================
# Diagnostic plots
# =====================================================================

def _plot_true_vs_estimated(result_df: pd.DataFrame, param_cols: list[str]) -> None:
    """Scatter plot of true vs estimated for each parameter, coloured by hull membership."""
    plot_cols = [pc for pc in param_cols
                 if f"est_{pc}" in result_df.columns and f"true_{pc}" in result_df.columns]
    if not plot_cols:
        return

    has_hull = "in_coverage" in result_df.columns
    if has_hull:
        in_hull = result_df["in_coverage"].astype(bool).values

    n = len(plot_cols)
    fig, axes = plt.subplots(n, 1, figsize=(5, 4.5 * n), squeeze=False)

    for i, pc in enumerate(plot_cols):
        ax = axes[i, 0]
        t = pd.to_numeric(result_df[f"true_{pc}"], errors="coerce").to_numpy(dtype=float)
        e = pd.to_numeric(result_df[f"est_{pc}"], errors="coerce").to_numpy(dtype=float)
        m = np.isfinite(t) & np.isfinite(e)
        if not np.any(m):
            ax.set_title(pc, fontsize=9)
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
            continue

        if has_hull:
            m_in = m & in_hull
            m_out = m & ~in_hull
            if np.any(m_in):
                ax.scatter(t[m_in], e[m_in], s=8, alpha=0.4, color="#59A14F",
                           edgecolors="none", label="In hull", zorder=1)
            if np.any(m_out):
                ax.scatter(t[m_out], e[m_out], s=12, alpha=0.7, color="#E15759",
                           marker="x", linewidths=0.8, label="Outside hull", zorder=2)
        else:
            ax.scatter(t[m], e[m], s=8, alpha=0.4, edgecolors="none")

        lo = min(float(np.nanmin(t[m])), float(np.nanmin(e[m])))
        hi = max(float(np.nanmax(t[m])), float(np.nanmax(e[m])))
        pad = 0.05 * (hi - lo) if hi > lo else 0.1
        ax.plot([lo - pad, hi + pad], [lo - pad, hi + pad], "k--", lw=0.8, alpha=0.5)
        ax.set_xlim(lo - pad, hi + pad)
        ax.set_ylim(lo - pad, hi + pad)
        ax.set_xlabel(f"True {pc}", fontsize=8)
        ax.set_ylabel(f"Estimated {pc}", fontsize=8)
        ax.set_title(pc, fontsize=9)
        ax.tick_params(labelsize=7)
        ax.set_aspect("equal", adjustable="box")
        ax.grid(True, alpha=0.15)

        # Compute and show RMSE and MAE
        rmse = float(np.sqrt(np.mean((t[m] - e[m]) ** 2)))
        mae = float(np.mean(np.abs(t[m] - e[m])))
        ax.text(0.03, 0.97, f"RMSE={rmse:.4g}\nMAE={mae:.4g}",
                transform=ax.transAxes, fontsize=7, va="top",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
        if has_hull and i == 0:
            ax.legend(fontsize=7, loc="lower right")

    fig.suptitle("True vs Estimated parameters", fontsize=11, y=1.0)
    fig.tight_layout()
    _save_figure(fig, PLOTS_DIR / "true_vs_estimated.png", dpi=150)
    plt.close(fig)


def _plot_distance_distribution(result_df: pd.DataFrame) -> None:
    """Histogram of best-match distances."""
    d = pd.to_numeric(result_df["best_distance"], errors="coerce").to_numpy(dtype=float)
    d = d[np.isfinite(d)]
    if len(d) < 2:
        return

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(d, bins=50, color="#4C78A8", edgecolor="none", alpha=0.7)
    ax.set_xlabel("Best-match distance (normalized feature space)", fontsize=9)
    ax.set_ylabel("Count", fontsize=9)
    ax.set_title("Distribution of best-match distances", fontsize=10)
    ax.tick_params(labelsize=7)
    ax.grid(True, alpha=0.15)

    med = float(np.median(d))
    ax.axvline(med, color="red", ls="--", lw=1, label=f"Median = {med:.3g}")
    ax.legend(fontsize=8)

    fig.tight_layout()
    _save_figure(fig, PLOTS_DIR / "distance_distribution.png", dpi=150)
    plt.close(fig)


def _plot_hull_coverage(
    dict_df: pd.DataFrame,
    data_df: pd.DataFrame,
    result_df: pd.DataFrame,
    param_cols: list[str],
) -> None:
    """Lower-triangular pairwise scatter of parameters showing dictionary,
    dataset-inside-hull, and dataset-outside-hull."""
    if "in_coverage" not in result_df.columns:
        return

    in_mask = result_df["in_coverage"].astype(bool).values
    out_mask = ~in_mask

    # Use one row per param_set_id for dataset to avoid overplotting
    data_plot = data_df.copy()
    data_plot["_in_cov"] = in_mask
    if "param_set_id" in data_plot.columns:
        data_plot = data_plot.groupby("param_set_id").first().reset_index()
        in_mask_plot = data_plot["_in_cov"].values
        out_mask_plot = ~in_mask_plot
    else:
        in_mask_plot = in_mask
        out_mask_plot = out_mask

    n = len(param_cols)
    fig, axes = plt.subplots(n - 1, n - 1, figsize=(3.2 * (n - 1), 3.2 * (n - 1)),
                             squeeze=False)

    # Hide upper triangle and diagonal
    for r in range(n - 1):
        for c in range(n - 1):
            if c >= r + 1:
                axes[r, c].set_visible(False)

    for r in range(1, n):
        for c in range(r):
            ax = axes[r - 1, c]
            yp = param_cols[r]
            xp = param_cols[c]
            # Dictionary
            dx = pd.to_numeric(dict_df[xp], errors="coerce").values
            dy = pd.to_numeric(dict_df[yp], errors="coerce").values
            ax.scatter(dx, dy, s=18, alpha=0.5, color="#4C78A8",
                       edgecolors="none", label="Dictionary", zorder=2)
            # Dataset inside hull
            sx_in = pd.to_numeric(data_plot.loc[in_mask_plot, xp], errors="coerce").values
            sy_in = pd.to_numeric(data_plot.loc[in_mask_plot, yp], errors="coerce").values
            ax.scatter(sx_in, sy_in, s=12, alpha=0.4, color="#59A14F",
                       edgecolors="none", label="Dataset (in hull)", zorder=1)
            # Dataset outside hull
            sx_out = pd.to_numeric(data_plot.loc[out_mask_plot, xp], errors="coerce").values
            sy_out = pd.to_numeric(data_plot.loc[out_mask_plot, yp], errors="coerce").values
            ax.scatter(sx_out, sy_out, s=20, alpha=0.8, color="#E15759",
                       marker="x", linewidths=1.0, label="Dataset (outside hull)", zorder=3)

            ax.tick_params(labelsize=6)
            ax.grid(True, alpha=0.12)
            if r == n - 1:
                ax.set_xlabel(xp.replace("_", " "), fontsize=7)
            else:
                ax.set_xticklabels([])
            if c == 0:
                ax.set_ylabel(yp.replace("_", " "), fontsize=7)
            else:
                ax.set_yticklabels([])

    # Single legend
    handles, labels = axes[n - 2, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", fontsize=8, framealpha=0.9)

    n_in = int(in_mask_plot.sum()) if "param_set_id" in data_df.columns else int(in_mask.sum())
    n_out = int(out_mask_plot.sum()) if "param_set_id" in data_df.columns else int(out_mask.sum())
    fig.suptitle(
        f"Parameter-space convex hull coverage\n"
        f"Dictionary: {len(dict_df)}, Dataset inside: {n_in}, outside: {n_out}",
        fontsize=10, y=1.02,
    )
    fig.tight_layout()
    _save_figure(fig, PLOTS_DIR / "hull_coverage_params.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def _plot_error_vs_distance(result_df: pd.DataFrame, param_cols: list[str]) -> None:
    """Scatter of estimation error vs best distance for each parameter, coloured by hull membership."""
    plot_cols = [pc for pc in param_cols
                 if f"est_{pc}" in result_df.columns and f"true_{pc}" in result_df.columns]
    if not plot_cols:
        return

    has_hull = "in_coverage" in result_df.columns
    if has_hull:
        in_hull = result_df["in_coverage"].astype(bool).values

    d = pd.to_numeric(result_df["best_distance"], errors="coerce").to_numpy(dtype=float)
    n = len(plot_cols)
    fig, axes = plt.subplots(n, 1, figsize=(6, 3.5 * n), squeeze=False)

    for i, pc in enumerate(plot_cols):
        ax = axes[i, 0]
        t = pd.to_numeric(result_df[f"true_{pc}"], errors="coerce").to_numpy(dtype=float)
        e = pd.to_numeric(result_df[f"est_{pc}"], errors="coerce").to_numpy(dtype=float)
        err = np.abs(t - e)
        m = np.isfinite(d) & np.isfinite(err)
        if not np.any(m):
            ax.set_title(pc, fontsize=9)
            continue

        if has_hull:
            m_in = m & in_hull
            m_out = m & ~in_hull
            if np.any(m_in):
                ax.scatter(d[m_in], err[m_in], s=8, alpha=0.4, color="#59A14F",
                           edgecolors="none", label="In hull", zorder=1)
            if np.any(m_out):
                ax.scatter(d[m_out], err[m_out], s=12, alpha=0.7, color="#E15759",
                           marker="x", linewidths=0.8, label="Outside hull", zorder=2)
        else:
            ax.scatter(d[m], err[m], s=8, alpha=0.4, edgecolors="none")

        ax.set_xlabel("Best-match distance", fontsize=8)
        ax.set_ylabel(f"|Error| in {pc}", fontsize=8)
        ax.set_title(pc, fontsize=9)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.15)
        if has_hull and i == 0:
            ax.legend(fontsize=7, loc="upper right")

    fig.suptitle("Estimation error vs best-match distance", fontsize=10, y=1.0)
    fig.tight_layout()
    _save_figure(fig, PLOTS_DIR / "error_vs_distance.png", dpi=150)
    plt.close(fig)


def _relative_error_pct(true_values: np.ndarray, est_values: np.ndarray) -> np.ndarray:
    true_arr = np.asarray(true_values, dtype=float)
    est_arr = np.asarray(est_values, dtype=float)
    denom = np.where(np.abs(true_arr) > 1e-12, np.abs(true_arr), np.nan)
    finite_true = true_arr[np.isfinite(true_arr)]
    fallback = max(float(np.ptp(finite_true)) if finite_true.size > 1 else 1.0, 1e-12)
    denom = np.where(np.isfinite(denom), denom, fallback)
    return np.abs(est_arr - true_arr) / denom * 100.0


def _select_grouped_diagnostic_case(
    result_df: pd.DataFrame,
    param_cols: list[str],
    *,
    selector: str = "worst_flux_relerr",
) -> int | None:
    if result_df.empty:
        return None

    mode = str(selector).strip().lower()
    if mode == "worst_flux_relerr" and "true_flux_cm2_min" in result_df.columns and "est_flux_cm2_min" in result_df.columns:
        rel = _relative_error_pct(
            pd.to_numeric(result_df["true_flux_cm2_min"], errors="coerce").to_numpy(dtype=float),
            pd.to_numeric(result_df["est_flux_cm2_min"], errors="coerce").to_numpy(dtype=float),
        )
        finite = np.isfinite(rel)
        if np.any(finite):
            return int(np.nanargmax(np.where(finite, rel, np.nan)))

    if mode == "worst_primary_param_relerr" and param_cols:
        primary = str(param_cols[0])
        true_col = f"true_{primary}"
        est_col = f"est_{primary}"
        if true_col in result_df.columns and est_col in result_df.columns:
            rel = _relative_error_pct(
                pd.to_numeric(result_df[true_col], errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(result_df[est_col], errors="coerce").to_numpy(dtype=float),
            )
            finite = np.isfinite(rel)
            if np.any(finite):
                return int(np.nanargmax(np.where(finite, rel, np.nan)))

    best_distance = pd.to_numeric(result_df.get("best_distance"), errors="coerce").to_numpy(dtype=float)
    finite = np.isfinite(best_distance)
    if np.any(finite):
        return int(np.nanargmax(np.where(finite, best_distance, np.nan)))
    return None


def _apply_fiducial_overlay(ax: plt.Axes, axis_name: str, fiducial: Mapping[str, object] | None) -> None:
    cfg = fiducial if isinstance(fiducial, Mapping) else {}
    if axis_name == "theta":
        limit = cfg.get("theta_max_deg")
    elif axis_name == "x":
        limit = cfg.get("x_abs_max_mm")
    elif axis_name == "y":
        limit = cfg.get("y_abs_max_mm")
    else:
        limit = None
    try:
        limit_val = float(limit) if limit is not None else np.nan
    except (TypeError, ValueError):
        limit_val = np.nan
    if not np.isfinite(limit_val) or limit_val <= 0.0:
        return
    ax.axvspan(-limit_val, limit_val, color="#59A14F", alpha=0.08, zorder=0)
    ax.axvline(-limit_val, color="#59A14F", ls="--", lw=0.8, alpha=0.7)
    ax.axvline(limit_val, color="#59A14F", ls="--", lw=0.8, alpha=0.7)


def _build_grouped_case_payload(
    *,
    dict_df: pd.DataFrame,
    data_df: pd.DataFrame,
    feature_cols: list[str],
    distance_definition: dict | None,
    row_idx: int,
    top_k: int,
) -> dict | None:
    if distance_definition is None or not distance_definition.get("available"):
        return None

    dd = distance_definition
    feature_groups = dd.get("feature_groups", {}) if isinstance(dd.get("feature_groups"), Mapping) else {}
    group_weights = dd.get("group_weights", {}) if isinstance(dd.get("group_weights"), Mapping) else {}

    center = np.asarray(dd.get("center", []), dtype=float)
    scale = np.asarray(dd.get("scale", []), dtype=float)
    weights = np.asarray(dd.get("weights", []), dtype=float)
    p_norm = float(dd.get("p_norm", 2.0))

    scalar_feature_cols = [
        str(col)
        for col in dd.get("scalar_feature_columns", [])
        if str(col) in dict_df.columns and str(col) in data_df.columns
    ]
    scalar_idx = [feature_cols.index(col) for col in scalar_feature_cols if col in feature_cols]

    base_distances = None
    if scalar_feature_cols and scalar_idx:
        dict_scalar = dict_df[scalar_feature_cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        sample_scalar = (
            data_df.iloc[[row_idx]][scalar_feature_cols]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(dtype=float)
            .reshape(-1)
        )
        safe_scale = np.where(np.abs(scale[scalar_idx]) > 1e-15, scale[scalar_idx], np.nan)
        dict_scalar = (dict_scalar - center[scalar_idx]) / safe_scale
        sample_scalar = (sample_scalar - center[scalar_idx]) / safe_scale
        base_distances = _weighted_lp_many(
            sample_scalar,
            dict_scalar,
            weights=weights[scalar_idx],
            p_norm=p_norm,
            min_valid_dims=1,
        )

    aux_terms: list[tuple[str, np.ndarray | None, float, str]] = []
    plot_payload: dict[str, object] = {
        "row_idx": int(row_idx),
        "top_k": int(max(top_k, 1)),
        "feature_groups": feature_groups,
    }

    hist_cfg = feature_groups.get("rate_histogram", {})
    hist_weight = float(group_weights.get("rate_histogram", 0.0))
    hist_cols = [
        str(col)
        for col in (hist_cfg.get("feature_columns", []) if isinstance(hist_cfg, Mapping) else [])
        if str(col) in dict_df.columns and str(col) in data_df.columns
    ]
    if hist_cols:
        hist_dist_cfg = _resolve_histogram_distance_cfg(hist_cfg if isinstance(hist_cfg, Mapping) else {})
        dict_hist = dict_df[hist_cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        sample_hist = (
            data_df.iloc[[row_idx]][hist_cols]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(dtype=float)
            .reshape(-1)
        )
        if hist_weight > 0.0:
            hist_dist = _histogram_distance_many(
                sample_hist,
                dict_hist,
                distance=str(hist_dist_cfg["distance"]),
                normalization=str(hist_dist_cfg["normalization"]),
                p_norm=float(hist_dist_cfg["p_norm"]),
                amplitude_weight=float(hist_dist_cfg["amplitude_weight"]),
                shape_weight=float(hist_dist_cfg["shape_weight"]),
                slope_weight=float(hist_dist_cfg["slope_weight"]),
                cdf_weight=float(hist_dist_cfg["cdf_weight"]),
                amplitude_stat=str(hist_dist_cfg["amplitude_stat"]),
            )
            aux_terms.append(
                (
                    "rate_histogram",
                    hist_dist,
                    hist_weight,
                    str(hist_cfg.get("blend_mode", "normalized")) if isinstance(hist_cfg, Mapping) else "normalized",
                )
            )
        plot_payload["histogram"] = {
            "columns": hist_cols,
            "sample": sample_hist,
            "dict_matrix": dict_hist,
            "weight": hist_weight,
            "active": bool(hist_weight > 0.0),
        }

    eff_cfg = feature_groups.get("efficiency_vectors", {})
    eff_weight = float(group_weights.get("efficiency_vectors", 0.0))
    eff_payloads = _prepare_efficiency_vector_group_payloads(
        dict_df=dict_df,
        data_df=data_df.iloc[[row_idx]].copy(),
    )
    eff_payloads = _filter_efficiency_vector_payloads(
        eff_payloads,
        feature_groups_cfg=eff_cfg if isinstance(eff_cfg, Mapping) else None,
        selected_feature_columns=feature_cols,
    )
    if eff_payloads:
        eff_dist_cfg = _resolve_efficiency_vector_distance_cfg(eff_cfg if isinstance(eff_cfg, Mapping) else {})
        if eff_weight > 0.0:
            group_distances: list[np.ndarray] = []
            for payload in eff_payloads:
                group_dist = _efficiency_vector_group_distance_many(
                    sample_eff=np.asarray(payload["data_eff"], dtype=float)[0],
                    candidates_eff=np.asarray(payload["dict_eff"], dtype=float),
                    sample_unc=np.asarray(payload["data_unc"], dtype=float)[0],
                    candidates_unc=np.asarray(payload["dict_unc"], dtype=float),
                    centers=np.asarray(payload["centers"], dtype=float),
                    axis_name=str(payload["axis"]),
                    fiducial=dict(eff_dist_cfg["fiducial"]),
                    uncertainty_floor=float(eff_dist_cfg["uncertainty_floor"]),
                    min_valid_bins=int(eff_dist_cfg["min_valid_bins_per_vector"]),
                    normalization=str(eff_dist_cfg["normalization"]),
                    p_norm=float(eff_dist_cfg["p_norm"]),
                    amplitude_weight=float(eff_dist_cfg["amplitude_weight"]),
                    shape_weight=float(eff_dist_cfg["shape_weight"]),
                    slope_weight=float(eff_dist_cfg["slope_weight"]),
                    cdf_weight=float(eff_dist_cfg["cdf_weight"]),
                    amplitude_stat=str(eff_dist_cfg["amplitude_stat"]),
                )
                group_distances.append(group_dist)
            if group_distances:
                aux_terms.append(
                    (
                        "efficiency_vectors",
                        _reduce_efficiency_vector_group_stack(
                            np.vstack(group_distances),
                            group_reduction=str(eff_dist_cfg["group_reduction"]),
                        ),
                        eff_weight,
                        str(eff_cfg.get("blend_mode", "normalized")) if isinstance(eff_cfg, Mapping) else "normalized",
                    )
                )
        plot_payload["efficiency_vectors"] = {
            "payloads": eff_payloads,
            "cfg": eff_dist_cfg,
            "weight": eff_weight,
            "active": bool(eff_weight > 0.0),
        }

    total_distances, _ = _combine_distance_terms_with_breakdown(
        base_distances=base_distances,
        aux_terms=aux_terms,
    )
    if total_distances.size == 0:
        return None

    valid = np.isfinite(total_distances)
    if not np.any(valid):
        return None
    order = np.argsort(total_distances[valid])
    valid_indices = np.flatnonzero(valid)[order]
    top_indices = valid_indices[: max(int(top_k), 1)]
    plot_payload["top_indices"] = top_indices
    plot_payload["top_distances"] = np.asarray(total_distances[top_indices], dtype=float)
    plot_payload["best_index"] = int(top_indices[0])
    return plot_payload


def _plot_grouped_case_diagnostic(
    *,
    dict_df: pd.DataFrame,
    data_df: pd.DataFrame,
    result_df: pd.DataFrame,
    param_cols: list[str],
    feature_cols: list[str],
    distance_definition: dict | None,
    case_selector: str,
    top_k: int,
) -> None:
    row_idx = _select_grouped_diagnostic_case(result_df, param_cols, selector=case_selector)
    if row_idx is None:
        return
    payload = _build_grouped_case_payload(
        dict_df=dict_df,
        data_df=data_df,
        feature_cols=feature_cols,
        distance_definition=distance_definition,
        row_idx=row_idx,
        top_k=top_k,
    )
    if not payload:
        return

    top_indices = np.asarray(payload["top_indices"], dtype=int)
    best_index = int(payload["best_index"])
    top_distances = np.asarray(payload["top_distances"], dtype=float)

    fig = plt.figure(figsize=(16, 18), constrained_layout=True)
    gs = fig.add_gridspec(5, 3, height_ratios=[1.2, 1.0, 1.0, 1.0, 1.0], hspace=0.35, wspace=0.25)

    hist_payload = payload.get("histogram")
    if isinstance(hist_payload, Mapping):
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
        ax_hist.plot(bins, sample_hist, color="black", lw=2.2, label="Sample row", zorder=4)
        hist_weight = float(hist_payload.get("weight", np.nan))
        hist_status = "active" if bool(hist_payload.get("active", False)) else "inactive"
        if np.isfinite(hist_weight):
            hist_title_suffix = f" [{hist_status}, weight={hist_weight:.3g}]"
        else:
            hist_title_suffix = f" [{hist_status}]"
        ax_hist.set_title(
            f"Rate histogram: sample vs best dictionary vs top-10 neighbors{hist_title_suffix}",
            fontsize=11,
        )
        ax_hist.set_xlabel("Histogram bin", fontsize=9)
        ax_hist.set_ylabel("Rate [Hz]", fontsize=9)
        ax_hist.grid(True, alpha=0.15)
        ax_hist.legend(fontsize=8, loc="upper right")

    eff_payload = payload.get("efficiency_vectors")
    if isinstance(eff_payload, Mapping):
        fiducial = eff_payload["cfg"].get("fiducial", {})
        eff_weight = float(eff_payload.get("weight", np.nan))
        eff_status = "active" if bool(eff_payload.get("active", False)) else "inactive"
        if np.isfinite(eff_weight):
            eff_title_suffix = f" [{eff_status}, weight={eff_weight:.3g}]"
        else:
            eff_title_suffix = f" [{eff_status}]"
        by_label = {
            str(item.get("label", "")): item
            for item in eff_payload["payloads"]
        }
        for plane in range(1, 5):
            for col_idx, axis_name in enumerate(("x", "y", "theta")):
                label = f"p{plane}_{axis_name}"
                ax = fig.add_subplot(gs[plane, col_idx])
                item = by_label.get(label)
                if not item:
                    ax.set_axis_off()
                    continue
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

    filename = str(result_df.iloc[row_idx].get("filename_base", f"row_{row_idx}"))
    true_flux = result_df.iloc[row_idx].get("true_flux_cm2_min")
    est_flux = result_df.iloc[row_idx].get("est_flux_cm2_min")
    flux_text = ""
    if pd.notna(true_flux) and pd.notna(est_flux):
        flux_text = f" | flux true={float(true_flux):.4g} est={float(est_flux):.4g} relerr={float(_relative_error_pct(np.asarray([true_flux]), np.asarray([est_flux]))[0]):.2f}%"
    fig.suptitle(
        f"Grouped feature diagnostic case: selector={case_selector} row={row_idx} file={filename}{flux_text}\n"
        f"Top {len(top_indices)} dictionary neighbors: best idx={best_index}, best distance={float(top_distances[0]):.4g}",
        fontsize=12,
        y=0.995,
    )
    _save_figure(fig, PLOTS_DIR / "grouped_case_top_matches.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    neighbor_rows = dict_df.iloc[top_indices].copy()
    neighbor_rows.insert(0, "rank", np.arange(1, len(top_indices) + 1, dtype=int))
    neighbor_rows.insert(1, "dictionary_index", top_indices.astype(int))
    neighbor_rows.insert(2, "distance", top_distances)
    keep_cols = ["rank", "dictionary_index", "distance"]
    if "filename_base" in neighbor_rows.columns:
        keep_cols.append("filename_base")
    keep_cols.extend([col for col in param_cols if col in neighbor_rows.columns])
    neighbor_rows[keep_cols].to_csv(
        FILES_DIR / "grouped_case_top_neighbors.csv",
        index=False,
    )


# =====================================================================
# Main
# =====================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step 2.1: Estimate parameters using dictionary matching."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--dictionary-csv", default=None)
    parser.add_argument("--dataset-csv", default=None)
    args = parser.parse_args()

    config = _load_config(Path(args.config))
    _clear_plots_dir()

    cfg_21 = config.get("step_2_1", {}) or {}

    # Resolve paths
    dict_path = Path(args.dictionary_csv) if args.dictionary_csv else DEFAULT_DICTIONARY
    data_path = Path(args.dataset_csv) if args.dataset_csv else DEFAULT_DATASET

    if not dict_path.exists():
        log.error("Dictionary not found: %s", dict_path)
        return 1
    if not data_path.exists():
        log.error("Dataset not found: %s", data_path)
        return 1

    # Load data
    dict_df = pd.read_csv(dict_path, low_memory=False)
    data_df = pd.read_csv(data_path, low_memory=False)

    # Backwards-compatibility: some upstream artifacts use `eff_p1..4` naming.
    # Ensure the estimator's expected `eff_sim_1..4` columns exist by copying
    # legacy columns when the `eff_sim_*` names are missing. This keeps the
    # rest of the estimation pipeline unchanged.
    for i in range(1, 5):
        legacy = f"eff_p{i}"
        target = f"eff_sim_{i}"
        if target not in dict_df.columns and legacy in dict_df.columns:
            dict_df[target] = dict_df[legacy]
        if target not in data_df.columns and legacy in data_df.columns:
            data_df[target] = data_df[legacy]

    if dict_df.empty:
        log.error("Dictionary is empty: %s", dict_path)
        return 1
    if data_df.empty:
        log.error("Dataset is empty: %s", data_path)
        return 1

    # Load feature columns from step 1.4 artifact
    if not DEFAULT_FEATURE_COLUMNS.exists():
        log.error("Feature columns artifact not found: %s", DEFAULT_FEATURE_COLUMNS)
        return 1
    try:
        feature_cols = _require_selected_feature_columns_present(
            _load_feature_columns(DEFAULT_FEATURE_COLUMNS),
            dict_df=dict_df,
            data_df=data_df,
        )
    except ValueError as exc:
        log.error("%s", exc)
        return 1

    # Detect parameter columns
    param_cols = [c for c in PARAM_COLUMNS if c in dict_df.columns]
    if not param_cols:
        log.error("No parameter columns found in dictionary.")
        return 1

    # Config knobs (with sensible defaults)
    inv_cfg = cfg_21.get("inverse_mapping", {})
    interpolation_k_requested = inv_cfg.get("neighbor_count", 10)
    if interpolation_k_requested in (None, "", "null", "None"):
        interpolation_k_requested = None
    else:
        interpolation_k_requested = int(interpolation_k_requested)
    # Load distance definition from step 1.5 artifact (shared function)
    # Allow overriding the distance definition from config (useful for
    # quick experiments that want to test a particular group combination,
    # e.g. rate_histogram + efficiency_vectors:x only).
    cfg_dd = cfg_21.get("distance_definition") or cfg_21.get("distance_definition_path")
    try:
        dd, runtime_inverse_mapping_cfg, _interpolation_k = resolve_runtime_distance_and_inverse_mapping(
            feature_columns=feature_cols,
            inverse_mapping_cfg=inv_cfg,
            interpolation_k=interpolation_k_requested,
            context_label="STEP 2.1",
            distance_definition_path=DEFAULT_DISTANCE_DEFINITION,
            logger=log,
            distance_definition_override=cfg_dd,
        )
    except ValueError as exc:
        log.error(str(exc))
        return 1

    log.info("Dictionary: %s (%d rows)", dict_path, len(dict_df))
    log.info("Dataset:    %s (%d rows)", data_path, len(data_df))
    log.info("Feature columns: %d", len(feature_cols))
    log.info("Parameter columns: %s", param_cols)
    log_runtime_inverse_mapping_summary(log, runtime_inverse_mapping_cfg)

    # ── Run estimation using the shared engine ─────────────────
    result_df = estimate_from_dataframes(
        dict_df=dict_df,
        data_df=data_df,
        feature_columns=feature_cols,
        distance_metric="l2_zscore",
        param_columns=param_cols,
        exclude_same_file=False,
        shared_parameter_exclusion_mode="full",
        shared_parameter_exclusion_columns=["param_set_id"],
        shared_parameter_exclusion_ignore=(),
        density_weighting_cfg=None,
        include_global_rate=False,
        inverse_mapping_cfg=runtime_inverse_mapping_cfg,
        distance_definition=dd,
    )

    # Flag entries outside dictionary convex hull in parameter space
    dict_params_hull = dict_df[param_cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    data_params_hull = data_df[param_cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    try:
        hull_delaunay = Delaunay(dict_params_hull)
        simplex_ids = hull_delaunay.find_simplex(data_params_hull)
        result_df["in_coverage"] = simplex_ids >= 0
        n_out = int((simplex_ids < 0).sum())
        if n_out > 0:
            log.info(
                "Coverage flag: %d / %d dataset entries are outside the dictionary convex hull in parameter space.",
                n_out, len(result_df),
            )
        else:
            log.info("All %d dataset entries are inside the dictionary convex hull.", len(result_df))
    except Exception as exc:
        log.warning("Convex hull computation failed (%s); skipping coverage flag.", exc)
        hull_delaunay = None

    # Attach truth columns for validation
    truth_cols = [
        "flux_cm2_min", "cos_n",
        "eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4",
        "n_events", "is_dictionary_entry",
        "param_hash_x", "param_set_id",
    ]
    for col in truth_cols:
        if col in data_df.columns:
            result_df[f"true_{col}"] = data_df[col].values[:len(result_df)]

    # Attach filename_base if available
    if "filename_base" in data_df.columns:
        result_df["filename_base"] = data_df["filename_base"].values[:len(result_df)]

    # ── Save ─────────────────────────────────────────────────────────
    out_path = FILES_DIR / "estimated_params.csv"
    result_df.to_csv(out_path, index=False)
    log.info("Wrote: %s (%d rows)", out_path, len(result_df))

    n_ok = int(result_df["best_distance"].notna().sum())
    n_fail = int(result_df["best_distance"].isna().sum())

    summary = {
        "dictionary": str(dict_path),
        "dataset": str(data_path),
        "distance_mode": dd.get("selected_mode", "unknown") if dd is not None else None,
        "distance_definition_used": dd is not None,
        "distance_definition_mode": dd.get("selected_mode") if dd is not None else None,
        "k": int(runtime_inverse_mapping_cfg["neighbor_count"]),
        "idw_power": float(runtime_inverse_mapping_cfg["inverse_distance_power"]),
        "aggregation": runtime_inverse_mapping_cfg["aggregation"],
        "inverse_mapping_runtime_applied": runtime_inverse_mapping_cfg,
        "feature_columns": feature_cols,
        "feature_columns_count": len(feature_cols),
        "parameter_columns": param_cols,
        "total_points": len(result_df),
        "successful_estimates": n_ok,
        "failed_estimates": n_fail,
    }
    with open(FILES_DIR / "estimation_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # ── Plots ────────────────────────────────────────────────────────
    _plot_true_vs_estimated(result_df, param_cols)
    _plot_distance_distribution(result_df)
    _plot_error_vs_distance(result_df, param_cols)
    _plot_hull_coverage(dict_df, data_df, result_df, param_cols)
    grouped_diag_cfg = cfg_21.get("grouped_feature_diagnostic", {}) or {}
    grouped_diag_enabled = bool(grouped_diag_cfg.get("enabled", True))
    grouped_diag_selector = str(grouped_diag_cfg.get("selector", "worst_flux_relerr"))
    grouped_diag_top_k = int(grouped_diag_cfg.get("top_k", 10) or 10)
    if grouped_diag_enabled and dd is not None and dd.get("feature_groups"):
        _plot_grouped_case_diagnostic(
            dict_df=dict_df,
            data_df=data_df,
            result_df=result_df,
            param_cols=param_cols,
            feature_cols=feature_cols,
            distance_definition=dd,
            case_selector=grouped_diag_selector,
            top_k=max(grouped_diag_top_k, 1),
        )

    log.info("Done. %d OK, %d failed.", n_ok, n_fail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
