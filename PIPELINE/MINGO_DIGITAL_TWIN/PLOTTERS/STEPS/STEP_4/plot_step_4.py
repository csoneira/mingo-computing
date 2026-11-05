#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/STEPS/STEP_4/plot_step_4.py
Purpose: Plots for STEP 4 — adapted from MASTER_STEPS/STEP_4/step_4_hit_to_measured.py.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/STEPS/STEP_4/plot_step_4.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

ROOT_DIR = Path(__file__).resolve().parents[3]
sys.path.append(str(ROOT_DIR))
sys.path.append(str(ROOT_DIR / "MASTER_STEPS"))

from STEP_4.step_4_hit_to_measured import (
    induce_signal as live_induce_signal,
    plot_hit_summary as live_plot_hit_summary,
    plot_step4_summary as live_plot_step4_summary,
)

Y_WIDTHS = [np.array([63, 63, 63, 98], dtype=float), np.array([98, 63, 63, 63], dtype=float)]


def normalize_tt(series: pd.Series) -> pd.Series:
    tt = series.astype("string").fillna("")
    tt = tt.str.strip()
    tt = tt.str.replace(r"\.0$", "", regex=True)
    tt = tt.replace({"0": "", "0.0": "", "nan": "", "<NA>": ""})
    return tt


def plot_hit_summary(df: pd.DataFrame, pdf: PdfPages) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))
    if "tt_hit" in df.columns:
        counts = df["tt_hit"].astype("string").fillna("").value_counts().sort_index()
        bars = ax.bar(counts.index, counts.values, color="steelblue", alpha=0.8)
        for patch in bars:
            patch.set_rasterized(True)
    ax.set_title("tt_hit counts")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def compute_mode_charge(values: np.ndarray) -> float:
    positive = values[np.isfinite(values) & (values > 0)]
    if positive.size == 0:
        return 1.0
    counts, edges = np.histogram(positive, bins="auto")
    if counts.size == 0 or edges.size < 2:
        median = float(np.nanmedian(positive))
        return max(1.0, median if np.isfinite(median) else 1.0)
    mode_idx = int(np.argmax(counts))
    mode_val = 0.5 * (edges[mode_idx] + edges[mode_idx + 1])
    if not np.isfinite(mode_val) or mode_val <= 0:
        median = float(np.nanmedian(positive))
        return max(1.0, median if np.isfinite(median) else 1.0)
    return float(max(1.0, mode_val))


def strip_edges_mm_for_plane(plane_idx: int) -> np.ndarray:
    widths = Y_WIDTHS[0] if plane_idx in (1, 3) else Y_WIDTHS[1]
    total_width = float(np.sum(widths))
    lower_edges = -total_width / 2.0 + np.cumsum(np.concatenate(([0.0], widths[:-1])))
    upper_edges = lower_edges + widths
    return np.unique(np.concatenate([lower_edges, upper_edges]))


def strip_centers_mm_for_plane(plane_idx: int) -> np.ndarray:
    widths = Y_WIDTHS[0] if plane_idx in (1, 3) else Y_WIDTHS[1]
    total_width = float(np.sum(widths))
    lower_edges = -total_width / 2.0 + np.cumsum(np.concatenate(([0.0], widths[:-1])))
    centers = lower_edges + 0.5 * widths
    return centers.astype(float)


def plot_multi_event_thrown_clouds(
    step4_df: pd.DataFrame,
    avalanche_source_df: pd.DataFrame,
    pdf: PdfPages,
    n_events: int,
    n_points: int,
    seed: int | None,
    avalanche_width_mm: float,
    width_scale_exponent: float,
    width_scale_max: float,
) -> None:
    if "tt_hit" not in step4_df.columns:
        return
    if avalanche_source_df is None or avalanche_source_df.empty:
        return

    required_cols: list[str] = []
    for plane_idx in range(1, 5):
        required_cols.extend(
            [
                f"avalanche_x_{plane_idx}",
                f"avalanche_y_{plane_idx}",
                f"avalanche_size_electrons_{plane_idx}",
            ]
        )
    if not all(col in avalanche_source_df.columns for col in required_cols):
        return

    n_common = min(len(step4_df), len(avalanche_source_df))
    if n_common == 0:
        return

    tt_hit_vals = normalize_tt(step4_df["tt_hit"].iloc[:n_common]).fillna("").astype(str).to_numpy()
    full_hit_mask = tt_hit_vals == "1234"

    x_vals: dict[int, np.ndarray] = {}
    y_vals: dict[int, np.ndarray] = {}
    q_vals: dict[int, np.ndarray] = {}
    mode_charge: dict[int, float] = {}
    valid_all_planes = np.ones(n_common, dtype=bool)
    for plane_idx in range(1, 5):
        x_arr = avalanche_source_df[f"avalanche_x_{plane_idx}"].iloc[:n_common].to_numpy(dtype=float)
        y_arr = avalanche_source_df[f"avalanche_y_{plane_idx}"].iloc[:n_common].to_numpy(dtype=float)
        q_arr = avalanche_source_df[f"avalanche_size_electrons_{plane_idx}"].iloc[:n_common].to_numpy(dtype=float)
        plane_valid = np.isfinite(x_arr) & np.isfinite(y_arr) & np.isfinite(q_arr) & (q_arr > 0)
        valid_all_planes &= plane_valid
        x_vals[plane_idx] = x_arr
        y_vals[plane_idx] = y_arr
        q_vals[plane_idx] = q_arr
        mode_charge[plane_idx] = compute_mode_charge(q_arr)

    candidates = np.where(full_hit_mask & valid_all_planes)[0]
    if candidates.size == 0:
        return

    rng = np.random.default_rng(seed if seed is not None else 1)
    n_pick = min(max(1, int(n_events)), candidates.size)
    selected = np.sort(rng.choice(candidates, size=n_pick, replace=False))
    colors = ["#d62728", "#ff7f0e", "#2ca02c", "#1f77b4", "#9467bd"]
    x_min, x_max = -150.0, 150.0
    y_min, y_max = -143.0, 143.0

    fig, axes = plt.subplots(2, 2, figsize=(11.0, 9.0))
    for plane_idx in range(1, 5):
        ax = axes[(plane_idx - 1) // 2, (plane_idx - 1) % 2]
        for edge in strip_edges_mm_for_plane(plane_idx):
            ax.axhline(edge, color="gray", linestyle="--", linewidth=0.8, alpha=0.4)

        for col_idx, event_idx in enumerate(selected):
            color = colors[col_idx % len(colors)]
            center_x = float(x_vals[plane_idx][event_idx])
            center_y = float(y_vals[plane_idx][event_idx])
            aval_q = float(q_vals[plane_idx][event_idx])
            mode_q = mode_charge[plane_idx]
            base_scale = aval_q / mode_q if mode_q > 0 else 0.0
            if base_scale > 0:
                width_scale = min(width_scale_max, base_scale ** width_scale_exponent)
            else:
                width_scale = 0.0
            sigma = max(1.0, float(avalanche_width_mm * width_scale))

            points_rng = np.random.default_rng(int(rng.integers(0, 2 ** 32 - 1)))
            x_pts = center_x + points_rng.normal(0.0, sigma, n_points)
            y_pts = center_y + points_rng.normal(0.0, sigma, n_points)

            ax.scatter(x_pts, y_pts, s=4, alpha=0.36, color=color, rasterized=True)
            ax.scatter([center_x], [center_y], s=26, color=color, marker="x")

        ax.set_xlim(x_min, x_max)
        ax.set_ylim(y_min, y_max)
        ax.set_aspect("equal", adjustable="box")
        ax.set_title(f"Plane {plane_idx} thrown points ({n_pick} events)")
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")

    fig.suptitle(f"Thrown-point clouds: {n_pick} full-hit events overlaid per plane (tt_hit=1234)")
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.965))
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def plot_position_resolution_vs_avalanche(
    step4_df: pd.DataFrame,
    avalanche_df: pd.DataFrame | None,
    pdf: PdfPages,
) -> None:
    """Compare reconstructed charge-weighted positions to STEP 3 avalanche centers."""
    if avalanche_df is None or avalanche_df.empty:
        return

    n_common = min(len(step4_df), len(avalanche_df))
    if n_common <= 0:
        return

    fig_x, axes_x = plt.subplots(2, 2, figsize=(10.5, 8.5), sharex=True, sharey=True)
    fig_y, axes_y = plt.subplots(2, 2, figsize=(10.5, 8.5), sharex=True, sharey=True)
    summary: list[tuple[int, float, float, int, float, float, int]] = []

    for plane_idx in range(1, 5):
        ax_x = axes_x[(plane_idx - 1) // 2, (plane_idx - 1) % 2]
        ax_y = axes_y[(plane_idx - 1) // 2, (plane_idx - 1) % 2]
        x_cols = [f"X_mea_{plane_idx}_s{s}" for s in range(1, 5)]
        q_cols = [f"Y_mea_{plane_idx}_s{s}" for s in range(1, 5)]
        aval_x_col = f"avalanche_x_{plane_idx}"
        aval_y_col = f"avalanche_y_{plane_idx}"
        if not all(c in step4_df.columns for c in x_cols + q_cols):
            ax_x.axis("off")
            ax_y.axis("off")
            summary.append((plane_idx, float("nan"), float("nan"), 0, float("nan"), float("nan"), 0))
            continue
        if aval_x_col not in avalanche_df.columns or aval_y_col not in avalanche_df.columns:
            ax_x.axis("off")
            ax_y.axis("off")
            summary.append((plane_idx, float("nan"), float("nan"), 0, float("nan"), float("nan"), 0))
            continue

        x_mat = step4_df[x_cols].to_numpy(dtype=float)[:n_common]
        q_mat = step4_df[q_cols].to_numpy(dtype=float)[:n_common]
        aval_x = avalanche_df[aval_x_col].to_numpy(dtype=float)[:n_common]
        aval_y = avalanche_df[aval_y_col].to_numpy(dtype=float)[:n_common]

        valid_x = np.isfinite(x_mat) & np.isfinite(q_mat) & (q_mat > 0.0)
        q_eff_x = np.where(valid_x, q_mat, 0.0)
        qsum_x = q_eff_x.sum(axis=1)
        reco_x = np.full(n_common, np.nan, dtype=float)
        ok_x = qsum_x > 0.0
        if np.any(ok_x):
            reco_x[ok_x] = (np.where(valid_x, x_mat, 0.0) * q_eff_x).sum(axis=1)[ok_x] / qsum_x[ok_x]

        centers = strip_centers_mm_for_plane(plane_idx)
        center_mat = np.tile(centers, (n_common, 1))
        valid_y = np.isfinite(q_mat) & (q_mat > 0.0)
        q_eff_y = np.where(valid_y, q_mat, 0.0)
        qsum_y = q_eff_y.sum(axis=1)
        reco_y = np.full(n_common, np.nan, dtype=float)
        ok_y = qsum_y > 0.0
        if np.any(ok_y):
            reco_y[ok_y] = (center_mat * q_eff_y).sum(axis=1)[ok_y] / qsum_y[ok_y]

        mask_dx = np.isfinite(reco_x) & np.isfinite(aval_x)
        dx = reco_x[mask_dx] - aval_x[mask_dx]
        mask_dy = np.isfinite(reco_y) & np.isfinite(aval_y)
        dy = reco_y[mask_dy] - aval_y[mask_dy]

        if dx.size > 0:
            lo_x, hi_x = np.quantile(dx, [0.01, 0.99])
            if not np.isfinite(lo_x) or not np.isfinite(hi_x) or lo_x >= hi_x:
                lo_x, hi_x = float(np.min(dx)), float(np.max(dx))
            ax_x.hist(dx, bins=100, range=(lo_x, hi_x), color="tab:blue", alpha=0.8)
            mu_x = float(np.mean(dx))
            sig_x = float(np.std(dx))
            ax_x.axvline(mu_x, color="black", linestyle="--", linewidth=1.0)
            ax_x.set_title(f"Plane {plane_idx}: X_reco - X_avalanche")
            ax_x.set_xlabel("Residual (mm)")
            ax_x.set_ylabel("Counts")
            ax_x.text(
                0.03,
                0.95,
                f"N={dx.size}\nμ={mu_x:.2f} mm\nσ={sig_x:.2f} mm",
                transform=ax_x.transAxes,
                ha="left",
                va="top",
                fontsize=9,
                bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
            )
        else:
            mu_x = float("nan")
            sig_x = float("nan")
            ax_x.axis("off")

        if dy.size > 0:
            lo_y, hi_y = np.quantile(dy, [0.01, 0.99])
            if not np.isfinite(lo_y) or not np.isfinite(hi_y) or lo_y >= hi_y:
                lo_y, hi_y = float(np.min(dy)), float(np.max(dy))
            ax_y.hist(dy, bins=100, range=(lo_y, hi_y), color="tab:orange", alpha=0.8)
            mu_y = float(np.mean(dy))
            sig_y = float(np.std(dy))
            ax_y.axvline(mu_y, color="black", linestyle="--", linewidth=1.0)
            ax_y.set_title(f"Plane {plane_idx}: Y_reco - Y_avalanche")
            ax_y.set_xlabel("Residual (mm)")
            ax_y.set_ylabel("Counts")
            ax_y.text(
                0.03,
                0.95,
                f"N={dy.size}\nμ={mu_y:.2f} mm\nσ={sig_y:.2f} mm",
                transform=ax_y.transAxes,
                ha="left",
                va="top",
                fontsize=9,
                bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
            )
        else:
            mu_y = float("nan")
            sig_y = float("nan")
            ax_y.axis("off")

        summary.append((plane_idx, mu_x, sig_x, int(dx.size), mu_y, sig_y, int(dy.size)))

    fig_x.suptitle("STEP 4 spatial residuals: reconstructed X vs avalanche truth")
    fig_x.tight_layout(rect=(0.0, 0.0, 1.0, 0.97))
    pdf.savefig(fig_x, dpi=150)
    plt.close(fig_x)

    fig_y.suptitle("STEP 4 spatial residuals: reconstructed Y vs avalanche truth")
    fig_y.tight_layout(rect=(0.0, 0.0, 1.0, 0.97))
    pdf.savefig(fig_y, dpi=150)
    plt.close(fig_y)

    x = np.array([row[0] for row in summary], dtype=float)
    mu_x = np.array([row[1] for row in summary], dtype=float)
    sig_x = np.array([row[2] for row in summary], dtype=float)
    n_x = np.array([max(row[3], 1) for row in summary], dtype=float)
    mu_y = np.array([row[4] for row in summary], dtype=float)
    sig_y = np.array([row[5] for row in summary], dtype=float)
    n_y = np.array([max(row[6], 1) for row in summary], dtype=float)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    ok_x = np.isfinite(mu_x) & np.isfinite(sig_x)
    if np.any(ok_x):
        axes[0].errorbar(
            x[ok_x],
            mu_x[ok_x],
            yerr=sig_x[ok_x] / np.sqrt(n_x[ok_x]),
            fmt="o-",
            color="tab:blue",
            capsize=3,
            label="Mean ± SEM",
        )
        axes[0].axhline(0.0, color="gray", linestyle="--", linewidth=1.0)
        axes[0].set_title("X residual mean by plane")
        axes[0].set_xlabel("Plane")
        axes[0].set_ylabel("mm")
        axes[0].set_xticks([1, 2, 3, 4])
        axes[0].grid(alpha=0.3)
        axes[0].legend(loc="best", fontsize=9)
    else:
        axes[0].axis("off")

    ok_y = np.isfinite(mu_y) & np.isfinite(sig_y)
    if np.any(ok_y):
        axes[1].errorbar(
            x[ok_y],
            mu_y[ok_y],
            yerr=sig_y[ok_y] / np.sqrt(n_y[ok_y]),
            fmt="o-",
            color="tab:orange",
            capsize=3,
            label="Mean ± SEM",
        )
        axes[1].axhline(0.0, color="gray", linestyle="--", linewidth=1.0)
        axes[1].set_title("Y residual mean by plane")
        axes[1].set_xlabel("Plane")
        axes[1].set_ylabel("mm")
        axes[1].set_xticks([1, 2, 3, 4])
        axes[1].grid(alpha=0.3)
        axes[1].legend(loc="best", fontsize=9)
    else:
        axes[1].axis("off")

    fig.suptitle("STEP 4 reconstructed-position bias summary")
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def plot_step4_summary(
    df: pd.DataFrame,
    pdf: PdfPages,
    include_thrown_points: bool = True,
    points_per_plane: int = 2000,
    point_seed: int | None = None,
    thrown_points: dict | None = None,
    examples_df: pd.DataFrame | None = None,
    avalanche_df: pd.DataFrame | None = None,
    avalanche_width_mm: float = 40.0,
    width_scale_exponent: float = 0.1,
    width_scale_max: float = 2.0,
    n_avalanche_events: int = 5,
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    axes = axes.flatten()

    counts = normalize_tt(df.get("tt_hit", pd.Series(dtype="string"))).value_counts().sort_index()
    bars = axes[0].bar(counts.index, counts.values, color="steelblue", alpha=0.8)
    for patch in bars:
        patch.set_rasterized(True)
    axes[0].set_title("tt_hit")

    qsum_cols = [c for c in df.columns if c.startswith("Y_mea_") and "_s" in c]
    qsum_vals = df[qsum_cols].to_numpy(dtype=float).ravel() if qsum_cols else np.array([])
    qsum_vals = qsum_vals[qsum_vals > 0]
    axes[1].hist(qsum_vals, bins=60, color="seagreen", alpha=0.8)
    axes[1].set_title("qsum (all strips)")

    x_cols = [c for c in df.columns if c.startswith("X_mea_") and "_s" in c]
    x_vals = df[x_cols].to_numpy(dtype=float).ravel() if x_cols else np.array([])
    x_vals = x_vals[~np.isnan(x_vals)]
    axes[2].hist(x_vals, bins=60, color="darkorange", alpha=0.8)
    axes[2].set_title("X_mea (all strips)")

    t_cols = [c for c in df.columns if c.startswith("T_sum_meas_") and "_s" in c]
    t_vals = df[t_cols].to_numpy(dtype=float).ravel() if t_cols else np.array([])
    t_vals = t_vals[~np.isnan(t_vals)]
    axes[3].hist(t_vals, bins=60, color="slateblue", alpha=0.8)
    axes[3].set_title("T_sum_meas (all strips)")

    for ax in axes:
        for patch in ax.patches:
            patch.set_rasterized(True)
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    # Per-tt example pages (use df itself as examples source if available)
    if "Theta_gen" in df.columns and "Phi_gen" in df.columns and "tt_hit" in df.columns:
        tt_series = normalize_tt(df["tt_hit"]).dropna().astype(str)
        for tt_value in sorted(tt_series.unique()):
            tt_df = df[df["tt_hit"] == tt_value]
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))
            axes[0].scatter(
                tt_df["Theta_gen"],
                tt_df["Phi_gen"],
                s=6,
                alpha=0.25,
                rasterized=True,
            )
            axes[0].set_title(f"Theta vs Phi (tt_hit={tt_value})")
            axes[0].set_xlabel("Theta (rad)")
            axes[0].set_ylabel("Phi (rad)")
            axes[0].set_xlim(0, np.pi / 2)
            axes[0].set_ylim(-np.pi, np.pi)

            axes[1].hist2d(tt_df["Theta_gen"], tt_df["Phi_gen"], bins=60, cmap="magma")
            axes[1].set_title(f"Theta vs Phi density (tt_hit={tt_value})")
            axes[1].set_xlabel("Theta (rad)")
            axes[1].set_ylabel("Phi (rad)")
            axes[1].set_xlim(0, np.pi / 2)
            axes[1].set_ylim(-np.pi, np.pi)
            fig.tight_layout()
            pdf.savefig(fig, dpi=150)
            plt.close(fig)

    strip_cols_all = [col for col in df.columns if col.startswith("Y_mea_") and "_s" in col]
    examples_source = examples_df if examples_df is not None else df
    if strip_cols_all and examples_source is not None and not examples_source.empty:
        rng = np.random.default_rng(0)
        fig, axes = plt.subplots(5, 3, figsize=(12, 14), sharex=True, sharey=False)
        strip_positions = np.arange(1, 5)
        for ax in axes.flatten():
            plane = int(rng.integers(1, 5))
            strip_cols = [f"Y_mea_{plane}_s{s}" for s in range(1, 5)]
            if not all(col in examples_source.columns for col in strip_cols):
                ax.axis("off")
                continue
            qsum_matrix = examples_source[strip_cols].to_numpy(dtype=float)
            aval_col = f"avalanche_size_electrons_{plane}"
            if aval_col in examples_source.columns:
                aval_mask = examples_source[aval_col].to_numpy(dtype=float) >= 1.0
            else:
                aval_mask = np.ones(len(examples_source), dtype=bool)
            if "tt_hit" in examples_source.columns:
                tt_series = normalize_tt(examples_source["tt_hit"]).astype(str)
                tt_mask = tt_series == "1234"
            else:
                tt_series = None
                tt_mask = np.ones(len(examples_source), dtype=bool)
            hit_mask = (qsum_matrix > 0).any(axis=1) & aval_mask & tt_mask
            hit_indices = np.where(hit_mask)[0]
            if len(hit_indices) == 0:
                ax.axis("off")
                continue
            idx = int(rng.choice(hit_indices))
            vals = examples_source.loc[idx, strip_cols].to_numpy(dtype=float)
            bars = ax.bar(strip_positions, vals, width=0.6, alpha=0.8)
            for patch in bars:
                patch.set_rasterized(True)
            tt_label = tt_series.iloc[idx] if tt_series is not None else ""
            ax.set_title(f"P{plane} row {idx} tt={tt_label}")
            ax.set_xticks(strip_positions)
            ax.set_xlabel("Strip")
        axes[0, 0].set_ylabel("qsum")
        fig.suptitle("Charge sharing examples (single plane per event)")
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

    avalanche_source = avalanche_df if avalanche_df is not None else df
    n_common = min(len(df), len(avalanche_source)) if avalanche_source is not None else len(df)
    n_points = int(points_per_plane) if points_per_plane and points_per_plane > 0 else 2000
    plot_multi_event_thrown_clouds(
        step4_df=df,
        avalanche_source_df=avalanche_source,
        pdf=pdf,
        n_events=n_avalanche_events,
        n_points=n_points,
        seed=point_seed,
        avalanche_width_mm=avalanche_width_mm,
        width_scale_exponent=width_scale_exponent,
        width_scale_max=width_scale_max,
    )
    plot_position_resolution_vs_avalanche(df, avalanche_source, pdf)

    fig, axes = plt.subplots(4, 1, figsize=(8, 10), sharex=True)
    drew_ratio = False
    for plane_idx, ax in enumerate(axes, start=1):
        aval_col = f"avalanche_size_electrons_{plane_idx}"
        strip_cols = [c for c in df.columns if c.startswith(f"Y_mea_{plane_idx}_s")]
        if aval_col not in avalanche_source.columns or not strip_cols or n_common <= 0:
            ax.axis("off")
            continue
        aval_vals = avalanche_source[aval_col].to_numpy(dtype=float)[:n_common]
        strip_vals = df[strip_cols].to_numpy(dtype=float)[:n_common]
        qsum_total = strip_vals.sum(axis=1)
        mask = (aval_vals > 0) & (qsum_total > 0)
        ratios = np.zeros_like(aval_vals)
        ratios[mask] = qsum_total[mask] / aval_vals[mask]
        ratios = ratios[ratios > 0]
        if len(ratios) == 0:
            ax.axis("off")
            continue
        ax.hist(ratios, bins=80, color="steelblue", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} qsum / avalanche size")
        ax.set_xlim(left=0)
        for patch in ax.patches:
            patch.set_rasterized(True)
        drew_ratio = True
    if drew_ratio:
        axes[-1].set_xlabel("qsum / avalanche size")
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 1, figsize=(8, 10), sharex=True)
    drew_qsum_vs_aval = False
    for plane_idx, ax in enumerate(axes, start=1):
        aval_col = f"avalanche_size_electrons_{plane_idx}"
        strip_cols = [c for c in df.columns if c.startswith(f"Y_mea_{plane_idx}_s")]
        if aval_col not in avalanche_source.columns or not strip_cols or n_common <= 0:
            ax.axis("off")
            continue
        aval_vals = avalanche_source[aval_col].to_numpy(dtype=float)[:n_common]
        strip_vals = df[strip_cols].to_numpy(dtype=float)[:n_common]
        qsum_total = strip_vals.sum(axis=1)
        mask = (aval_vals > 0) & (qsum_total > 0)
        qsum_total = qsum_total[mask]
        aval_vals = aval_vals[mask]
        if len(aval_vals) == 0:
            ax.axis("off")
            continue
        ax.hist(qsum_total, bins=120, color="seagreen", alpha=0.8, label="qsum total")
        ax.hist(aval_vals, bins=120, color="darkorange", alpha=0.5, label="avalanche size")
        ax.set_title(f"Plane {plane_idx} qsum total vs avalanche size")
        ax.set_xlim(left=0)
        ax.legend()
        for patch in ax.patches:
            patch.set_rasterized(True)
        drew_qsum_vs_aval = True
    if drew_qsum_vs_aval:
        axes[-1].set_xlabel("electrons")
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 1, figsize=(8, 10), sharex=True)
    drew_qsum_zoom = False
    for plane_idx, ax in enumerate(axes, start=1):
        strip_cols = [c for c in df.columns if c.startswith(f"Y_mea_{plane_idx}_s")]
        if not strip_cols:
            ax.axis("off")
            continue
        strip_vals = df[strip_cols].to_numpy(dtype=float)
        qsum_total = strip_vals.sum(axis=1)
        qsum_total = qsum_total[qsum_total > 0]
        if len(qsum_total) == 0:
            ax.axis("off")
            continue
        median_val = float(np.median(qsum_total))
        if not np.isfinite(median_val) or median_val <= 0:
            ax.axis("off")
            continue
        zoom_vals = qsum_total[qsum_total <= median_val]
        ax.hist(zoom_vals, bins=80, color="teal", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} qsum total (0 to median)")
        ax.set_xlim(0, median_val)
        for patch in ax.patches:
            patch.set_rasterized(True)
        drew_qsum_zoom = True
    if drew_qsum_zoom:
        axes[-1].set_xlabel("electrons")
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 1, figsize=(8, 10), sharex=True)
    drew_scatter = False
    for plane_idx, ax in enumerate(axes, start=1):
        aval_col = f"avalanche_size_electrons_{plane_idx}"
        strip_cols = [c for c in df.columns if c.startswith(f"Y_mea_{plane_idx}_s")]
        if aval_col not in avalanche_source.columns or not strip_cols or n_common <= 0:
            ax.axis("off")
            continue
        aval_vals = avalanche_source[aval_col].to_numpy(dtype=float)[:n_common]
        strip_vals = df[strip_cols].to_numpy(dtype=float)[:n_common]
        qsum_total = strip_vals.sum(axis=1)
        mask = (aval_vals > 0) & (qsum_total > 0)
        aval_vals = aval_vals[mask]
        qsum_total = qsum_total[mask]
        if len(aval_vals) == 0:
            ax.axis("off")
            continue
        ax.scatter(
            aval_vals,
            qsum_total,
            s=2,
            alpha=0.2,
            rasterized=True,
        )
        ax.set_title(f"Plane {plane_idx} qsum total vs avalanche size")
        ax.set_xlabel("avalanche size")
        ax.set_ylabel("qsum total")
        drew_scatter = True
    if drew_scatter:
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 1, figsize=(8, 10), sharex=True)
    drew_ion_scatter = False
    for plane_idx, ax in enumerate(axes, start=1):
        ion_col = f"avalanche_ion_{plane_idx}"
        strip_cols = [c for c in df.columns if c.startswith(f"Y_mea_{plane_idx}_s")]
        if ion_col not in avalanche_source.columns or not strip_cols or n_common <= 0:
            ax.axis("off")
            continue
        ion_vals = avalanche_source[ion_col].to_numpy(dtype=float)[:n_common]
        strip_vals = df[strip_cols].to_numpy(dtype=float)[:n_common]
        qsum_total = strip_vals.sum(axis=1)
        mask = (ion_vals > 0) & (qsum_total > 0)
        ion_vals = ion_vals[mask]
        qsum_total = qsum_total[mask]
        if len(ion_vals) == 0:
            ax.axis("off")
            continue
        ax.scatter(
            ion_vals,
            qsum_total,
            s=2,
            alpha=0.2,
            rasterized=True,
        )
        ax.set_title(f"Plane {plane_idx} ionization vs induced qsum")
        ax.set_xlabel("ionizations")
        ax.set_ylabel("qsum total")
        drew_ion_scatter = True
    if drew_ion_scatter:
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 1, figsize=(8, 10), sharex=True)
    drew_avalanche_size = False
    for plane_idx, ax in enumerate(axes, start=1):
        col = f"avalanche_size_electrons_{plane_idx}"
        if col not in avalanche_source.columns:
            ax.axis("off")
            continue
        vals = avalanche_source[col].to_numpy(dtype=float)
        vals = vals[vals > 0]
        if len(vals) == 0:
            ax.axis("off")
            continue
        ax.hist(vals, bins=80, color="darkorange", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} avalanche size")
        ax.set_xlim(left=0)
        for patch in ax.patches:
            patch.set_rasterized(True)
        drew_avalanche_size = True
    if drew_avalanche_size:
        axes[-1].set_xlabel("avalanche size (electrons)")
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 1, figsize=(8, 10), sharex=True)
    drew_width_scale = False
    for plane_idx, ax in enumerate(axes, start=1):
        col = f"avalanche_width_scale_{plane_idx}"
        if col in avalanche_source.columns:
            vals = avalanche_source[col].to_numpy(dtype=float)
            vals = vals[vals > 0]
        else:
            aval_col = f"avalanche_size_electrons_{plane_idx}"
            if aval_col not in avalanche_source.columns:
                ax.axis("off")
                continue
            aval_vals = avalanche_source[aval_col].to_numpy(dtype=float)
            mode_q = compute_mode_charge(aval_vals)
            base_scale = np.where(aval_vals > 0, aval_vals / mode_q, 0.0)
            vals = np.power(
                base_scale,
                width_scale_exponent,
                where=base_scale > 0,
                out=np.zeros_like(base_scale),
            )
            vals = np.minimum(vals, width_scale_max)
            vals = vals[vals > 0]
        if len(vals) == 0:
            ax.axis("off")
            continue
        ax.hist(vals, bins=80, color="seagreen", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} width scale")
        ax.set_xlim(left=0)
        for patch in ax.patches:
            patch.set_rasterized(True)
        drew_width_scale = True
    if drew_width_scale:
        axes[-1].set_xlabel("width scale (charge / mode charge)")
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 1, figsize=(8, 10), sharex=True)
    drew_scaled_width = False
    for plane_idx, ax in enumerate(axes, start=1):
        col = f"avalanche_scaled_width_{plane_idx}"
        if col in avalanche_source.columns:
            vals = avalanche_source[col].to_numpy(dtype=float)
            vals = vals[vals > 0]
        else:
            aval_col = f"avalanche_size_electrons_{plane_idx}"
            if aval_col not in avalanche_source.columns:
                ax.axis("off")
                continue
            aval_vals = avalanche_source[aval_col].to_numpy(dtype=float)
            mode_q = compute_mode_charge(aval_vals)
            base_scale = np.where(aval_vals > 0, aval_vals / mode_q, 0.0)
            width_scale = np.power(
                base_scale,
                width_scale_exponent,
                where=base_scale > 0,
                out=np.zeros_like(base_scale),
            )
            width_scale = np.minimum(width_scale, width_scale_max)
            vals = avalanche_width_mm * width_scale
            vals = vals[vals > 0]
        if len(vals) == 0:
            ax.axis("off")
            continue
        ax.hist(vals, bins=80, color="slateblue", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} scaled width")
        ax.set_xlim(left=0)
        for patch in ax.patches:
            patch.set_rasterized(True)
        drew_scaled_width = True
    if drew_scaled_width:
        axes[-1].set_xlabel("scaled width (mm)")
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    drew_qsum_plane = False
    for plane_idx, ax in enumerate(axes.flatten(), start=1):
        strip_cols = [c for c in df.columns if c.startswith(f"Y_mea_{plane_idx}_s")]
        if not strip_cols:
            ax.axis("off")
            continue
        vals = df[strip_cols].to_numpy(dtype=float).sum(axis=1)
        vals = vals[vals > 0]
        if len(vals) == 0:
            ax.axis("off")
            continue
        ax.hist(vals, bins=120, color="seagreen", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} qsum total")
        ax.set_xlabel("qsum total")
        drew_qsum_plane = True
    if drew_qsum_plane:
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 4, figsize=(12, 10))
    drew_y_grid = False
    for plane_idx in range(1, 5):
        for strip_idx in range(1, 5):
            ax = axes[plane_idx - 1, strip_idx - 1]
            col = f"Y_mea_{plane_idx}_s{strip_idx}"
            if col not in df.columns:
                ax.axis("off")
                continue
            vals = df[col].to_numpy(dtype=float)
            vals = vals[vals > 0]
            if len(vals) == 0:
                ax.axis("off")
                continue
            ax.hist(vals, bins=80, color="seagreen", alpha=0.8)
            ax.set_title(f"P{plane_idx} S{strip_idx}")
            ax.set_xlabel("qsum")
            drew_y_grid = True
    if drew_y_grid:
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    drew_x_plane = False
    for plane_idx, ax in enumerate(axes.flatten(), start=1):
        strip_cols = [c for c in df.columns if c.startswith(f"X_mea_{plane_idx}_s")]
        if not strip_cols:
            ax.axis("off")
            continue
        vals = df[strip_cols].to_numpy(dtype=float).ravel()
        vals = vals[~np.isnan(vals)]
        if len(vals) == 0:
            ax.axis("off")
            continue
        ax.hist(vals, bins=80, color="darkorange", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} X_mea")
        ax.set_xlabel("X_mea (mm)")
        drew_x_plane = True
    if drew_x_plane:
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 4, figsize=(12, 10))
    drew_x_grid = False
    for plane_idx in range(1, 5):
        for strip_idx in range(1, 5):
            ax = axes[plane_idx - 1, strip_idx - 1]
            col = f"X_mea_{plane_idx}_s{strip_idx}"
            if col not in df.columns:
                ax.axis("off")
                continue
            vals = df[col].to_numpy(dtype=float)
            vals = vals[~np.isnan(vals)]
            if len(vals) == 0:
                ax.axis("off")
                continue
            ax.hist(vals, bins=80, color="darkorange", alpha=0.8)
            ax.set_title(f"P{plane_idx} S{strip_idx}")
            ax.set_xlabel("X_mea (mm)")
            drew_x_grid = True
    if drew_x_grid:
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    drew_t_plane = False
    for plane_idx, ax in enumerate(axes.flatten(), start=1):
        strip_cols = [c for c in df.columns if c.startswith(f"T_sum_meas_{plane_idx}_s")]
        if not strip_cols:
            ax.axis("off")
            continue
        vals = df[strip_cols].to_numpy(dtype=float).ravel()
        vals = vals[~np.isnan(vals)]
        if len(vals) == 0:
            ax.axis("off")
            continue
        ax.hist(vals, bins=80, color="slateblue", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} T_sum_meas")
        ax.set_xlabel("T_sum_meas (ns)")
        drew_t_plane = True
    if drew_t_plane:
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(4, 4, figsize=(12, 10))
    drew_t_grid = False
    for plane_idx in range(1, 5):
        for strip_idx in range(1, 5):
            ax = axes[plane_idx - 1, strip_idx - 1]
            col = f"T_sum_meas_{plane_idx}_s{strip_idx}"
            if col not in df.columns:
                ax.axis("off")
                continue
            vals = df[col].to_numpy(dtype=float)
            vals = vals[~np.isnan(vals)]
            if len(vals) == 0:
                ax.axis("off")
                continue
            ax.hist(vals, bins=80, color="slateblue", alpha=0.8)
            ax.set_title(f"P{plane_idx} S{strip_idx}")
            ax.set_xlabel("T_sum_meas (ns)")
            drew_t_grid = True
    if drew_t_grid:
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
    plt.close(fig)

    if include_thrown_points and thrown_points:
        fig, axes = plt.subplots(2, 2, figsize=(10, 9))
        drew_any = False
        for plane_idx in range(1, 5):
            ax = axes[(plane_idx - 1) // 2, (plane_idx - 1) % 2]
            points = thrown_points.get(plane_idx)
            if not points:
                ax.axis("off")
                continue
            x_pts = np.asarray(points.get("x", []), dtype=float).ravel()
            y_pts = np.asarray(points.get("y", []), dtype=float).ravel()
            n_pts = min(x_pts.size, y_pts.size)
            if n_pts == 0:
                ax.axis("off")
                continue
            x_pts = x_pts[:n_pts]
            y_pts = y_pts[:n_pts]
            charge = points.get("charge")
            if charge is None:
                ax.scatter(x_pts, y_pts, s=6, alpha=0.72, color="#1f77b4", rasterized=True)
                ax.set_title(f"Plane {plane_idx} thrown points")
            else:
                charge_arr = np.asarray(charge, dtype=float).ravel()
                if charge_arr.size == 1:
                    q_value = float(charge_arr[0])
                    ax.scatter(
                        x_pts,
                        y_pts,
                        color="#1f77b4",
                        s=8,
                        alpha=0.72,
                        rasterized=True,
                    )
                    ax.set_title(f"Plane {plane_idx} thrown points (Q={q_value:,.0f})")
                elif charge_arr.size > 1:
                    c_vals = charge_arr[:n_pts] if charge_arr.size >= n_pts else np.resize(charge_arr, n_pts)
                    ax.scatter(x_pts, y_pts, c=c_vals, s=8, cmap="Blues", alpha=0.72, rasterized=True)
                    ax.set_title(f"Plane {plane_idx} thrown points (colored by charge)")
                else:
                    ax.scatter(x_pts, y_pts, s=6, alpha=0.72, color="#1f77b4", rasterized=True)
                    ax.set_title(f"Plane {plane_idx} thrown points")
            ax.set_xlabel("X (mm)")
            ax.set_ylabel("Y (mm)")
            ax.set_aspect("equal", adjustable="box")
            drew_any = True
        if drew_any:
            fig.tight_layout()
            pdf.savefig(fig, dpi=150)
        plt.close(fig)

# helpers to find/load chunk ---------------------------------------------------

def find_any_chunk_for_step(step: int) -> Path | None:
    root = Path(__file__).resolve().parents[3] / "INTERSTEPS"
    candidates = list(root.glob(f"**/step_{step}_chunks/part_*.pkl"))
    candidates.extend(root.rglob(f"*step_{step}_chunks.chunks.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def load_df(path: Path) -> pd.DataFrame:
    if path.name.endswith(".chunks.json"):
        j = json.loads(path.read_text())
        parts = [p for p in (j.get("parts") or j.get("chunks") or []) if str(p).endswith(".pkl")]
        if parts:
            path = Path(parts[0])
        else:
            raise FileNotFoundError("Manifest contains no .pkl parts")
    if path.suffix == ".pkl":
        return pd.read_pickle(path)
    raise ValueError("Unsupported chunk type")


def find_step_manifest_for_sample(sample_path: Path, step: int) -> Path | None:
    manifest_name = f"step_{step}_chunks.chunks.json"
    if sample_path.name == manifest_name:
        return sample_path
    if sample_path.parent.name == f"step_{step}_chunks":
        candidate = sample_path.parent.parent / manifest_name
        if candidate.exists():
            return candidate
    candidate = sample_path.parent / manifest_name
    if candidate.exists():
        return candidate
    return None


def load_step4_plot_context(sample_path: Path) -> tuple[pd.DataFrame | None, dict]:
    manifest_path = find_step_manifest_for_sample(sample_path, step=4)
    if manifest_path is None or not manifest_path.exists():
        return None, {}
    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception:
        return None, {}

    metadata = manifest.get("metadata", {}) if isinstance(manifest, dict) else {}
    cfg = metadata.get("config", {}) if isinstance(metadata, dict) else {}
    if not isinstance(cfg, dict):
        cfg = {}

    source_dataset = metadata.get("source_dataset") if isinstance(metadata, dict) else None
    if not source_dataset:
        return None, cfg

    source_path = Path(str(source_dataset))
    if not source_path.is_absolute():
        source_path = (manifest_path.parent / source_path).resolve()
    else:
        source_path = source_path.resolve()
    if not source_path.exists():
        return None, cfg
    try:
        return load_df(source_path), cfg
    except Exception:
        return None, cfg


def build_live_step4_plot_frame(
    avalanche_df: pd.DataFrame,
    step4_cfg: dict,
) -> tuple[pd.DataFrame, dict]:
    needed_cols = {"event_id", "T_thick_s", "X_gen", "Y_gen", "Theta_gen", "Phi_gen"}
    for plane_idx in range(1, 5):
        needed_cols.update(
            {
                f"avalanche_size_electrons_{plane_idx}",
                f"avalanche_x_{plane_idx}",
                f"avalanche_y_{plane_idx}",
                f"T_sum_{plane_idx}_ns",
            }
        )
    keep_cols = [col for col in avalanche_df.columns if col in needed_cols]
    input_df = avalanche_df[keep_cols].copy()

    x_noise = float(step4_cfg.get("x_noise_mm", 0.0))
    time_sigma_ns = float(step4_cfg.get("time_sigma_ns", 0.0))
    lorentzian_gamma_mm = step4_cfg.get("lorentzian_gamma_mm")
    if lorentzian_gamma_mm in (None, ""):
        legacy_fwhm = float(step4_cfg.get("avalanche_width_mm", 40.0))
        lorentzian_gamma_mm = 0.5 * legacy_fwhm
    lorentzian_gamma_mm = float(lorentzian_gamma_mm)
    induced_charge_fraction = float(step4_cfg.get("induced_charge_fraction", 1.0))
    seed = step4_cfg.get("seed")
    rng = np.random.default_rng(seed)

    required_cols = [f"avalanche_size_electrons_{plane_idx}" for plane_idx in range(1, 5)]
    debug_event_index = None
    if all(col in input_df.columns for col in required_cols):
        full_hit_mask = np.ones(len(input_df), dtype=bool)
        for col in required_cols:
            full_hit_mask &= input_df[col].to_numpy(dtype=float) > 0
        hit_indices = np.where(full_hit_mask)[0]
        if hit_indices.size > 0:
            chooser = np.random.default_rng(seed if seed is not None else 0)
            debug_event_index = int(chooser.choice(hit_indices))

    debug_points: dict = {}
    out_full = live_induce_signal(
        input_df,
        x_noise=x_noise,
        time_sigma_ns=time_sigma_ns,
        lorentzian_gamma_mm=lorentzian_gamma_mm,
        induced_charge_fraction=induced_charge_fraction,
        rng=rng,
        debug_event_index=debug_event_index,
        debug_points=debug_points if debug_event_index is not None else None,
    )
    plot_cols = [
        col
        for col in out_full.columns
        if col == "tt_hit"
        or col.startswith(("Y_mea_", "X_mea_", "T_sum_meas_"))
        or col.startswith(
            (
                "avalanche_size_electrons_",
                "avalanche_gap_charge_fc_",
                "induced_charge_total_fc_",
                "lorentzian_gamma_mm_",
                "avalanche_x_",
                "avalanche_y_",
            )
        )
    ]
    return out_full[plot_cols], debug_points


def main() -> None:
    step = 4
    sample = find_any_chunk_for_step(step)
    if sample is None:
        print("No sample chunk found for STEP 4; exiting.")
        return
    print(f"Using sample: {sample}")
    df = load_df(sample)
    avalanche_df, step4_cfg = load_step4_plot_context(sample)
    if avalanche_df is not None:
        print("Loaded upstream STEP 3 dataset for avalanche cloud plotting.")
        plot_df, debug_points = build_live_step4_plot_frame(avalanche_df, step4_cfg)
        print("Rebuilt STEP 4 plot frame with the live Lorentzian sharing model.")
    else:
        plot_df = df
        debug_points = {}
        print("Upstream STEP 3 dataset unavailable; plotting the saved STEP 4 sample directly.")

    out_dir = Path(__file__).resolve().parent / "PLOTS"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"step_{step}_sample_plots.pdf"
    with PdfPages(out_path) as pdf:
        live_plot_hit_summary(plot_df, pdf)
        live_plot_step4_summary(
            plot_df,
            pdf,
            include_thrown_points=bool(debug_points),
            thrown_points=debug_points or None,
            examples_df=plot_df,
        )
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
