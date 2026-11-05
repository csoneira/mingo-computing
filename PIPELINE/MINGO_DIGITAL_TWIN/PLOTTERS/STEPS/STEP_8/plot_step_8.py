#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/STEPS/STEP_8/plot_step_8.py
Purpose: Plots for STEP 8 — adapted from MASTER_STEPS/STEP_8/step_8_uncalibrated_to_threshold.py.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/STEPS/STEP_8/plot_step_8.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

from pathlib import Path
import json
import math

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import LogNorm

# --- Read XY histogram config ---
import yaml

def load_xy_hist_config():
    config_path = Path(__file__).resolve().parent / "xy_hist_config.yaml"
    if config_path.exists():
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)
        lims = cfg.get("xy_hist_limits", {})
        x_min = lims.get("x_min", -1000)
        x_max = lims.get("x_max", 1000)
        y_min = lims.get("y_min", -1000)
        y_max = lims.get("y_max", 1000)
        return x_min, x_max, y_min, y_max
    return -1000, 1000, -1000, 1000


def plot_threshold_summary(
    df: pd.DataFrame,
    output_path: Path,
    threshold: float = 0.0,
    qfront_offsets: list[list[float]] | None = None,
    qback_offsets: list[list[float]] | None = None,
    sample_path: Path | None = None,
) -> None:
    if qfront_offsets is None:
        qfront_offsets = [[0.0] * 4 for _ in range(4)]
    if qback_offsets is None:
        qback_offsets = [[0.0] * 4 for _ in range(4)]

    with PdfPages(output_path) as pdf:
        tt_col = None
        for c in ("tt_trigger", "tt_hit", "tt_avalanche", "tt_crossing"):
            if c in df.columns:
                tt_col = c
                break
        if tt_col:
            fig, ax = plt.subplots(figsize=(8, 6))
            counts = df[tt_col].astype("string").fillna("").value_counts().sort_index()
            bars = ax.bar(counts.index.astype(str), counts.values, color="slateblue", alpha=0.8)
            for patch in bars:
                patch.set_rasterized(True)
            ax.set_title(f"{tt_col} counts")
            ax.set_xlabel(tt_col)
            ax.set_ylabel("Counts")
            fig.tight_layout()
            pdf.savefig(fig, dpi=150)
            plt.close(fig)

        # --- 2D X_gen / Y_gen histograms per tt_* (identical behaviour to STEP_10) ---
        plot_tt_xy_histograms(df, pdf)

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        qfront_cols = [c for c in df.columns if c.startswith("Q_front_")]
        qfront_vals = df[qfront_cols].to_numpy(dtype=float).ravel() if qfront_cols else np.array([])
        axes[0].hist(qfront_vals, bins=60, color="steelblue", alpha=0.8)
        axes[0].axvline(threshold, color="red", linestyle="--", linewidth=1)
        axes[0].set_title("Q_front (thresholded)")

        qback_cols = [c for c in df.columns if c.startswith("Q_back_")]
        qback_vals = df[qback_cols].to_numpy(dtype=float).ravel() if qback_cols else np.array([])
        axes[1].hist(qback_vals, bins=60, color="seagreen", alpha=0.8)
        axes[1].axvline(threshold, color="red", linestyle="--", linewidth=1)
        axes[1].set_title("Q_back (thresholded)")

        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

        plot_step8_cluster_topology(df, pdf)

        # --- Add per-plane 4x4 Q grids with offsets (copied from MASTER) ---
        fig, axes = plt.subplots(4, 4, figsize=(12, 10))
        for plane_idx in range(1, 5):
            for strip_idx in range(1, 5):
                ax = axes[plane_idx - 1, strip_idx - 1]
                qf_col = f"Q_front_{plane_idx}_s{strip_idx}"
                qb_col = f"Q_back_{plane_idx}_s{strip_idx}"
                if qf_col not in df.columns and qb_col not in df.columns:
                    ax.axis("off")
                    continue
                if qf_col in df.columns:
                    vals = df[qf_col].to_numpy(dtype=float)
                    mask = vals != 0
                    if mask.any():
                        vals = vals[mask] - float(qfront_offsets[plane_idx - 1][strip_idx - 1])
                        ax.hist(vals, bins=80, color="steelblue", alpha=0.6, label="front")
                if qb_col in df.columns:
                    vals = df[qb_col].to_numpy(dtype=float)
                    mask = vals != 0
                    if mask.any():
                        vals = vals[mask] - float(qback_offsets[plane_idx - 1][strip_idx - 1])
                        ax.hist(vals, bins=80, color="darkorange", alpha=0.6, label="back")
                ax.set_title(f"P{plane_idx} S{strip_idx}")
                ax.set_xlabel("a*x only")
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

        fig, axes = plt.subplots(4, 4, figsize=(12, 10))
        for plane_idx in range(1, 5):
            for strip_idx in range(1, 5):
                ax = axes[plane_idx - 1, strip_idx - 1]
                tf_col = f"T_front_{plane_idx}_s{strip_idx}"
                tb_col = f"T_back_{plane_idx}_s{strip_idx}"
                if tf_col not in df.columns and tb_col not in df.columns:
                    ax.axis("off")
                    continue
                if tf_col in df.columns:
                    vals = df[tf_col].to_numpy(dtype=float)
                    vals = vals[(~np.isnan(vals)) & (vals != 0)]
                    ax.hist(vals, bins=80, color="steelblue", alpha=0.6, label="front")
                if tb_col in df.columns:
                    vals = df[tb_col].to_numpy(dtype=float)
                    vals = vals[(~np.isnan(vals)) & (vals != 0)]
                    ax.hist(vals, bins=80, color="darkorange", alpha=0.6, label="back")
                ax.set_title(f"P{plane_idx} S{strip_idx}")
                ax.set_xlabel("time (ns)")
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

        # Per-strip charge grids
        fig, axes = plt.subplots(4, 4, figsize=(12, 10))
        for plane_idx in range(1, 5):
            for strip_idx in range(1, 5):
                ax = axes[plane_idx - 1, strip_idx - 1]
                qf_col = f"Q_front_{plane_idx}_s{strip_idx}"
                qb_col = f"Q_back_{plane_idx}_s{strip_idx}"
                if qf_col not in df.columns and qb_col not in df.columns:
                    ax.axis("off")
                    continue
                if qf_col in df.columns:
                    vals = df[qf_col].to_numpy(dtype=float)
                    vals = vals[vals != 0]
                    ax.hist(vals, bins=80, color="steelblue", alpha=0.6, label="front")
                if qb_col in df.columns:
                    vals = df[qb_col].to_numpy(dtype=float)
                    vals = vals[vals != 0]
                    ax.hist(vals, bins=80, color="darkorange", alpha=0.6, label="back")
                ax.set_title(f"P{plane_idx} S{strip_idx}")
                ax.set_xlabel("charge")
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

        # Publication-oriented diagnostics: front/back timing and charge asymmetry by plane.
        plot_frontback_asymmetry_diagnostics(df, pdf, stage_label="STEP 8")

        # --- Add muon differential flux vs zenith-angle (compute locally like STEP_1) ---
        try:
            added = _plot_muon_differential_flux_vs_angle_local(df, pdf, sample_path=sample_path)
            if not added:
                print('Step 8 plots: skipped muon differential flux plot (missing gen/time columns).')
        except Exception:
            print('Step 8 plots: muon differential flux page failed to generate (exception).')


def _collect_frontback_plane_arrays(df: pd.DataFrame, plane_idx: int) -> tuple[np.ndarray, np.ndarray]:
    tdiff_parts: list[np.ndarray] = []
    qasym_parts: list[np.ndarray] = []
    for strip_idx in range(1, 5):
        tf_col = f"T_front_{plane_idx}_s{strip_idx}"
        tb_col = f"T_back_{plane_idx}_s{strip_idx}"
        if tf_col in df.columns and tb_col in df.columns:
            tf = df[tf_col].to_numpy(dtype=float)
            tb = df[tb_col].to_numpy(dtype=float)
            mask_t = np.isfinite(tf) & np.isfinite(tb) & (tf != 0) & (tb != 0)
            if np.any(mask_t):
                tdiff_parts.append(tf[mask_t] - tb[mask_t])

        qf_col = f"Q_front_{plane_idx}_s{strip_idx}"
        qb_col = f"Q_back_{plane_idx}_s{strip_idx}"
        if qf_col in df.columns and qb_col in df.columns:
            qf = df[qf_col].to_numpy(dtype=float)
            qb = df[qb_col].to_numpy(dtype=float)
            den = qf + qb
            mask_q = np.isfinite(qf) & np.isfinite(qb) & (den > 0.0)
            if np.any(mask_q):
                qasym_parts.append((qf[mask_q] - qb[mask_q]) / den[mask_q])

    tdiff = np.concatenate(tdiff_parts) if tdiff_parts else np.array([], dtype=float)
    qasym = np.concatenate(qasym_parts) if qasym_parts else np.array([], dtype=float)
    return tdiff, qasym


def plot_frontback_asymmetry_diagnostics(df: pd.DataFrame, pdf: PdfPages, stage_label: str) -> None:
    fig_t, axes_t = plt.subplots(2, 2, figsize=(11, 8))
    fig_q, axes_q = plt.subplots(2, 2, figsize=(11, 8))
    summary_rows: list[tuple[int, float, float, int, float, float, int]] = []

    for plane_idx in range(1, 5):
        ax_t = axes_t[(plane_idx - 1) // 2, (plane_idx - 1) % 2]
        ax_q = axes_q[(plane_idx - 1) // 2, (plane_idx - 1) % 2]
        tdiff, qasym = _collect_frontback_plane_arrays(df, plane_idx)

        if tdiff.size > 0:
            lo_t, hi_t = np.quantile(tdiff, [0.01, 0.99])
            if not np.isfinite(lo_t) or not np.isfinite(hi_t) or lo_t >= hi_t:
                lo_t, hi_t = float(np.min(tdiff)), float(np.max(tdiff))
            ax_t.hist(tdiff, bins=100, range=(lo_t, hi_t), color="tab:blue", alpha=0.8)
            mu_t = float(np.mean(tdiff))
            sig_t = float(np.std(tdiff))
            ax_t.axvline(mu_t, color="black", linestyle="--", linewidth=1.0)
            ax_t.set_title(f"Plane {plane_idx}: T_front - T_back")
            ax_t.set_xlabel("ns")
            ax_t.set_ylabel("Counts")
            ax_t.text(
                0.03,
                0.95,
                f"N={tdiff.size}\nμ={mu_t:.3f} ns\nσ={sig_t:.3f} ns",
                transform=ax_t.transAxes,
                ha="left",
                va="top",
                fontsize=9,
                bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
            )
        else:
            mu_t = float("nan")
            sig_t = float("nan")
            ax_t.axis("off")

        if qasym.size > 0:
            ax_q.hist(qasym, bins=80, range=(-1.0, 1.0), color="tab:orange", alpha=0.8)
            mu_q = float(np.mean(qasym))
            sig_q = float(np.std(qasym))
            ax_q.axvline(mu_q, color="black", linestyle="--", linewidth=1.0)
            ax_q.set_title(f"Plane {plane_idx}: (Qf-Qb)/(Qf+Qb)")
            ax_q.set_xlabel("Charge asymmetry")
            ax_q.set_ylabel("Counts")
            ax_q.text(
                0.03,
                0.95,
                f"N={qasym.size}\nμ={mu_q:.3f}\nσ={sig_q:.3f}",
                transform=ax_q.transAxes,
                ha="left",
                va="top",
                fontsize=9,
                bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
            )
        else:
            mu_q = float("nan")
            sig_q = float("nan")
            ax_q.axis("off")

        summary_rows.append((plane_idx, mu_t, sig_t, int(tdiff.size), mu_q, sig_q, int(qasym.size)))

    fig_t.suptitle(f"{stage_label}: front-back timing symmetry by plane")
    fig_t.tight_layout(rect=(0.0, 0.0, 1.0, 0.97))
    pdf.savefig(fig_t, dpi=150)
    plt.close(fig_t)

    fig_q.suptitle(f"{stage_label}: front-back charge asymmetry by plane")
    fig_q.tight_layout(rect=(0.0, 0.0, 1.0, 0.97))
    pdf.savefig(fig_q, dpi=150)
    plt.close(fig_q)

    x = np.array([r[0] for r in summary_rows], dtype=float)
    mu_t = np.array([r[1] for r in summary_rows], dtype=float)
    sig_t = np.array([r[2] for r in summary_rows], dtype=float)
    n_t = np.array([max(r[3], 1) for r in summary_rows], dtype=float)
    mu_q = np.array([r[4] for r in summary_rows], dtype=float)
    sig_q = np.array([r[5] for r in summary_rows], dtype=float)
    n_q = np.array([max(r[6], 1) for r in summary_rows], dtype=float)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    ok_t = np.isfinite(mu_t) & np.isfinite(sig_t)
    if np.any(ok_t):
        axes[0].errorbar(
            x[ok_t],
            mu_t[ok_t],
            yerr=sig_t[ok_t] / np.sqrt(n_t[ok_t]),
            fmt="o-",
            color="tab:blue",
            capsize=3,
            label="Mean ± SEM",
        )
        axes[0].axhline(0.0, color="gray", linestyle="--", linewidth=1.0)
        axes[0].set_ylabel("T_front - T_back (ns)")
        axes[0].set_title("Timing symmetry summary")
        axes[0].set_xticks([1, 2, 3, 4])
        axes[0].set_xlabel("Plane")
        axes[0].grid(alpha=0.25)
        axes[0].legend(loc="best", fontsize=9)
    else:
        axes[0].axis("off")

    ok_q = np.isfinite(mu_q) & np.isfinite(sig_q)
    if np.any(ok_q):
        axes[1].errorbar(
            x[ok_q],
            mu_q[ok_q],
            yerr=sig_q[ok_q] / np.sqrt(n_q[ok_q]),
            fmt="o-",
            color="tab:orange",
            capsize=3,
            label="Mean ± SEM",
        )
        axes[1].axhline(0.0, color="gray", linestyle="--", linewidth=1.0)
        axes[1].set_ylabel("(Qf-Qb)/(Qf+Qb)")
        axes[1].set_title("Charge asymmetry summary")
        axes[1].set_xticks([1, 2, 3, 4])
        axes[1].set_xlabel("Plane")
        axes[1].grid(alpha=0.25)
        axes[1].legend(loc="best", fontsize=9)
    else:
        axes[1].axis("off")

    fig.suptitle(f"{stage_label}: front/back summary metrics")
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def _plot_muon_differential_flux_vs_angle_local(df: pd.DataFrame, pdf: PdfPages, sample_path: Path | None = None) -> bool:
    """Self-contained muon differential flux plot (same logic as STEP_1)."""
    if "Theta_gen" not in df.columns or "T_thick_s" not in df.columns:
        return False
    if "X_gen" not in df.columns or "Y_gen" not in df.columns:
        return False

    t0_all = df["T_thick_s"].to_numpy(dtype=float)
    if not np.isfinite(t0_all).any():
        return False
    sec_min = int(np.floor(np.nanmin(t0_all)))
    sec_max = int(np.floor(np.nanmax(t0_all)))
    if sec_max <= sec_min + 1:
        return False
    inner_mask = (np.floor(t0_all).astype(int) > sec_min) & (np.floor(t0_all).astype(int) < sec_max) & np.isfinite(t0_all)

    theta_all = df["Theta_gen"].to_numpy(dtype=float)
    theta = theta_all[np.isfinite(theta_all) & (theta_all >= 0.0) & (theta_all <= np.pi / 2.0) & inner_mask]
    if theta.size < 20:
        return False

    sec_min_inner = sec_min + 1
    sec_max_inner = sec_max - 1
    duration_s = float(sec_max_inner - sec_min_inner + 1)
    if not np.isfinite(duration_s) or duration_s <= 0.0:
        return False
    duration_min = duration_s / 60.0

    x_all = df["X_gen"].to_numpy(dtype=float)
    y_all = df["Y_gen"].to_numpy(dtype=float)
    x_vals = x_all[np.isfinite(x_all) & inner_mask]
    y_vals = y_all[np.isfinite(y_all) & inner_mask]
    if x_vals.size < 2 or y_vals.size < 2:
        return False
    x_spread_mm = float(np.max(x_vals) - np.min(x_vals))
    y_spread_mm = float(np.max(y_vals) - np.min(y_vals))
    area_cm2 = (x_spread_mm * y_spread_mm) / 100.0
    if not np.isfinite(area_cm2) or area_cm2 <= 0.0:
        return False

    theta_edges = np.linspace(0.0, np.pi / 2.0, 31)
    theta_centers = 0.5 * (theta_edges[1:] + theta_edges[:-1])
    counts, _ = np.histogram(theta, bins=theta_edges)
    delta_omega = 2.0 * np.pi * (np.cos(theta_edges[:-1]) - np.cos(theta_edges[1:]))
    valid = (counts > 0) & np.isfinite(delta_omega) & (delta_omega > 0.0)
    if not np.any(valid):
        return False

    theta_deg = np.degrees(theta_centers[valid])
    delta_omega_valid = delta_omega[valid]
    counts_valid = counts[valid].astype(float)
    flux = counts_valid / (duration_min * area_cm2 * delta_omega_valid)
    flux_err = np.sqrt(counts_valid) / (duration_min * area_cm2 * delta_omega_valid)

    fig, (ax_top, ax_bottom) = plt.subplots(
        2,
        1,
        figsize=(8.5, 8.8),
        sharex=True,
        gridspec_kw={"height_ratios": [2.0, 1.1]},
    )
    ax_top.errorbar(
        theta_deg,
        flux,
        yerr=flux_err,
        fmt="o",
        markersize=4,
        linewidth=1.0,
        color="black",
        ecolor="gray",
        capsize=2,
        label=(f"Sample (N={theta.size}, T={duration_min:.3f} min, Axy={area_cm2:.2f} cm^2)"),
    )

    n_fit_out: float | None = None
    i0_fit_out: float | None = None
    fit_theta = theta_centers[valid]
    fit_cos = np.cos(fit_theta)
    fit_ok = (counts_valid > 0.0) & (flux > 0.0) & (fit_cos > 0.0)
    if np.count_nonzero(fit_ok) >= 3:
        x_fit = np.log(np.clip(fit_cos[fit_ok], 1e-12, 1.0))
        y_fit = np.log(flux[fit_ok])
        w_fit = counts_valid[fit_ok]
        sw = float(np.sum(w_fit))
        sx = float(np.sum(w_fit * x_fit))
        sy = float(np.sum(w_fit * y_fit))
        sxx = float(np.sum(w_fit * x_fit * x_fit))
        sxy = float(np.sum(w_fit * x_fit * y_fit))
        den = sw * sxx - sx * sx
        if np.isfinite(den) and abs(den) > 1e-15 and sw > 0.0:
            n_fit = (sw * sxy - sx * sy) / den
            ln_i0 = (sy - n_fit * sx) / sw
            if np.isfinite(n_fit) and np.isfinite(ln_i0):
                n_fit_out = float(n_fit)
                i0_fit_out = float(np.exp(ln_i0))
                theta_curve = np.linspace(0.0, np.pi / 2.0 - 1e-4, 400)
                curve = i0_fit_out * np.power(np.clip(np.cos(theta_curve), 1e-12, 1.0), n_fit_out)
                ax_top.plot(
                    np.degrees(theta_curve),
                    curve,
                    color="tab:orange",
                    linewidth=1.4,
                    linestyle="--",
                    label=rf"Fit: $I_0\cos^n(\theta)$, $I_0={i0_fit_out:.3e}$, $n={n_fit_out:.2f}$",
                )

    try:
        param_path = Path(__file__).resolve().parents[3] / "INTERSTEPS" / "STEP_0_TO_1" / "param_mesh.csv"
        cos_n = 2.0
        flux_F = float("nan")
        if param_path.exists():
            pm = pd.read_csv(param_path)
            step1_id = None
            if sample_path is not None:
                try:
                    if sample_path.name.endswith(".chunks.json"):
                        meta = json.loads(sample_path.read_text()).get("metadata", {})
                    else:
                        meta_path = sample_path.with_suffix(sample_path.suffix + ".meta.json")
                        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
                except Exception:
                    meta = {}
                cfg = meta.get("config", {}) if isinstance(meta, dict) else {}
                step1_id = cfg.get("step_1_id") or meta.get("step_1_id")
            rows = pm[pm["step_1_id"].astype(str) == str(step1_id)] if step1_id is not None else pm
            if rows.empty:
                rows = pm
            row = rows.iloc[0]
            cos_n = float(row.get("cos_n", 2.0))
            flux_F = float(row.get("flux_cm2_min", float("nan")))
        if np.isfinite(flux_F):
            i0_theory = float(flux_F * (cos_n + 1.0) / (2.0 * math.pi))
            theta_curve = np.linspace(0.0, np.pi / 2.0 - 1e-4, 400)
            model_curve = i0_theory * np.power(np.clip(np.cos(theta_curve), 1e-12, 1.0), cos_n)
            ax_top.plot(
                np.degrees(theta_curve),
                model_curve,
                color="crimson",
                linewidth=1.6,
                label=rf"Theory: $I_0\cos^n(\theta)$, $I_0={i0_theory:.4g}$, $n={cos_n:.2f}$",
            )
    except Exception:
        pass

    cumulative_flux = np.cumsum(flux * delta_omega_valid)
    cumulative_flux_err = np.sqrt(np.cumsum((flux_err * delta_omega_valid) ** 2))
    theta_upper_deg = np.degrees(theta_edges[1:])[valid]
    ax_bottom.step(
        theta_upper_deg,
        cumulative_flux,
        where="post",
        color="navy",
        linewidth=1.4,
        label=r"Data cumulative: $\int_0^\theta I(\theta')\,d\Omega$",
    )
    ax_bottom.fill_between(
        theta_upper_deg,
        np.maximum(0.0, cumulative_flux - cumulative_flux_err),
        cumulative_flux + cumulative_flux_err,
        step="post",
        color="steelblue",
        alpha=0.25,
        label="Data 1-sigma band",
    )

    if n_fit_out is not None and i0_fit_out is not None:
        theta_curve = np.linspace(0.0, np.pi / 2.0 - 1e-4, 400)
        cum_fit = (
            2.0
            * math.pi
            * i0_fit_out
            / (n_fit_out + 1.0)
            * (1.0 - np.power(np.clip(np.cos(theta_curve), 0.0, 1.0), n_fit_out + 1.0))
        )
        ax_bottom.plot(np.degrees(theta_curve), cum_fit, color="tab:orange", linestyle="--", linewidth=1.2, label="Fit cumulative")

    ax_top.set_title("Muon differential flux vs zenith angle (area-normalized)")
    ax_top.set_ylabel("I(theta) [min^-1 cm^-2 sr^-1]")
    ax_top.set_xlim(0.0, 90.0)
    ax_top.set_ylim(bottom=0.0)
    ax_top.grid(alpha=0.3)
    ax_top.legend(loc="upper right")

    ax_bottom.set_xlabel("Zenith angle (deg)")
    ax_bottom.set_ylabel("Accumulated flux\n[min^-1 cm^-2]")
    ax_bottom.set_xlim(0.0, 90.0)
    ax_bottom.set_ylim(bottom=0.0)
    ax_bottom.grid(alpha=0.3)
    ax_bottom.legend(loc="upper left")

    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)
    return True


def plot_tt_xy_histograms(df: pd.DataFrame, pdf: PdfPages) -> None:
    # Find all columns starting with 'tt_'
    tt_cols = [col for col in df.columns if col.startswith("tt_")]
    if "X_gen" not in df.columns or "Y_gen" not in df.columns:
        print("STEP_8: X_gen/Y_gen missing — skipping TT XY histograms.")
        return
    x_min, x_max, y_min, y_max = load_xy_hist_config()

    # Fallback: if there are no tt_* columns, produce a single overall 2D histogram
    if not tt_cols:
        print("STEP_8: no tt_* columns found — creating overall X_gen/Y_gen 2D histogram.")
        fig, ax = plt.subplots(figsize=(6, 6))
        x = df["X_gen"].to_numpy(dtype=float)
        y = df["Y_gen"].to_numpy(dtype=float)
        h = ax.hist2d(x, y, bins=80, range=[[x_min, x_max], [y_min, y_max]], cmap="turbo", norm=LogNorm(vmin=1))
        ax.set_title("2D X_gen/Y_gen (all events — no tt_* columns present)")
        ax.set_xlabel("X_gen")
        ax.set_ylabel("Y_gen")
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(y_min, y_max)
        ax.set_aspect('equal', adjustable='box')
        fig.colorbar(h[3], ax=ax)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)
        return

    n = len(tt_cols)
    ncols = min(n, 3)
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 5 * nrows), squeeze=False)
    for idx, tt_col in enumerate(tt_cols):
        ax = axes[idx // ncols][idx % ncols]
        mask = df[tt_col].notna() & (df[tt_col] != "")
        x = df.loc[mask, "X_gen"].to_numpy(dtype=float)
        y = df.loc[mask, "Y_gen"].to_numpy(dtype=float)
        h = ax.hist2d(x, y, bins=60, range=[[x_min, x_max], [y_min, y_max]], cmap="turbo", norm=LogNorm(vmin=1))
        ax.set_title(f"2D X_gen/Y_gen for {tt_col}")
        ax.set_xlabel("X_gen")
        ax.set_ylabel("Y_gen")
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(y_min, y_max)
        ax.set_aspect('equal', adjustable='box')
        fig.colorbar(h[3], ax=ax)
    # Hide unused axes
    for idx in range(n, nrows * ncols):
        axes[idx // ncols][idx % ncols].axis("off")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def plane_strip_activity_mask(df: pd.DataFrame, plane_idx: int) -> np.ndarray:
    masks: list[np.ndarray] = []
    for strip_idx in range(1, 5):
        qf_col = f"Q_front_{plane_idx}_s{strip_idx}"
        qb_col = f"Q_back_{plane_idx}_s{strip_idx}"
        qf = (
            df[qf_col].to_numpy(dtype=float)
            if qf_col in df.columns
            else np.zeros(len(df), dtype=float)
        )
        qb = (
            df[qb_col].to_numpy(dtype=float)
            if qb_col in df.columns
            else np.zeros(len(df), dtype=float)
        )
        masks.append((np.isfinite(qf) & (qf > 0)) | (np.isfinite(qb) & (qb > 0)))
    return np.column_stack(masks) if masks else np.zeros((len(df), 4), dtype=bool)


def plane_cluster_sizes(df: pd.DataFrame, plane_idx: int) -> np.ndarray:
    return plane_strip_activity_mask(df, plane_idx).sum(axis=1)


def plane_topology_patterns(df: pd.DataFrame, plane_idx: int) -> pd.Series:
    mask = plane_strip_activity_mask(df, plane_idx)
    patterns = np.array(
        ["".join("1" if bit else "0" for bit in row) for row in mask],
        dtype=object,
    )
    return pd.Series(patterns, dtype="string")


def plot_step8_cluster_topology(df: pd.DataFrame, pdf: PdfPages) -> None:
    fig_sizes, axes_sizes = plt.subplots(2, 2, figsize=(11, 8), sharey=True)
    for plane_idx, ax in enumerate(axes_sizes.flatten(), start=1):
        sizes = plane_cluster_sizes(df, plane_idx)
        counts = pd.Series(sizes).value_counts().sort_index()
        x = np.arange(5)
        y = np.array([int(counts.get(i, 0)) for i in x], dtype=int)
        ax.bar(x, y, color="tab:purple", alpha=0.8)
        ax.set_xticks(x)
        ax.set_xlabel("Cluster size")
        ax.set_title(f"Plane {plane_idx}")
        ax.grid(axis="y", alpha=0.2)
        if plane_idx in (1, 3):
            ax.set_ylabel("Rows")
        active = sizes[sizes > 0]
        mean_size = float(np.mean(active)) if active.size else float("nan")
        ax.text(
            0.03,
            0.95,
            f"active rows={int(active.size)}\nmean active size={mean_size:.3f}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
        )
    fig_sizes.suptitle("STEP 8 cluster-size distribution by plane")
    fig_sizes.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    pdf.savefig(fig_sizes, dpi=150)
    plt.close(fig_sizes)

    fig_pat, axes_pat = plt.subplots(2, 2, figsize=(12, 8))
    for plane_idx, ax in enumerate(axes_pat.flatten(), start=1):
        patterns = plane_topology_patterns(df, plane_idx)
        patterns = patterns[patterns != "0000"]
        if patterns.empty:
            ax.axis("off")
            continue
        counts = patterns.value_counts().sort_values(ascending=False).head(8)
        ax.bar(counts.index.astype(str), counts.to_numpy(dtype=int), color="tab:cyan", alpha=0.8)
        ax.set_title(f"Plane {plane_idx}")
        ax.set_xlabel("Active-strip pattern")
        if plane_idx in (1, 3):
            ax.set_ylabel("Rows")
        ax.tick_params(axis="x", labelrotation=45)
        ax.grid(axis="y", alpha=0.2)
    fig_pat.suptitle("STEP 8 dominant active-strip topologies by plane")
    fig_pat.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    pdf.savefig(fig_pat, dpi=150)
    plt.close(fig_pat)


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


def load_step8_config(sample_path: Path) -> dict:
    manifest = find_step_manifest_for_sample(sample_path, step=8)
    if manifest is None or not manifest.exists():
        return {}
    try:
        j = json.loads(manifest.read_text())
    except Exception:
        return {}
    metadata = j.get("metadata", {}) if isinstance(j, dict) else {}
    cfg = metadata.get("config", {}) if isinstance(metadata, dict) else {}
    return cfg if isinstance(cfg, dict) else {}


def find_any_chunk_for_step(step: int) -> Path | None:
    root = Path(__file__).resolve().parents[3] / "INTERSTEPS"
    manifests = list(root.rglob(f"*step_{step}_chunks.chunks.json"))
    if manifests:
        return max(manifests, key=lambda p: p.stat().st_mtime)
    parts = list(root.glob(f"**/step_{step}_chunks/part_*.pkl"))
    if parts:
        return max(parts, key=lambda p: p.stat().st_mtime)
    return None


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


def main() -> None:
    step = 8
    sample = find_any_chunk_for_step(step)
    if sample is None:
        print("No sample chunk found for STEP 8; exiting.")
        return
    print(f"Using sample: {sample}")
    df = load_df(sample)
    cfg = load_step8_config(sample)
    thresh = float(cfg.get("charge_threshold", cfg.get("threshold", 0.0)))
    qfront_offsets = cfg.get("qfront_offsets", [[0.0] * 4 for _ in range(4)])
    qback_offsets = cfg.get("qback_offsets", [[0.0] * 4 for _ in range(4)])

    out_dir = Path(__file__).resolve().parent / "PLOTS"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"step_{step}_sample_plots.pdf"
    plot_threshold_summary(
        df,
        out_path,
        threshold=thresh,
        qfront_offsets=qfront_offsets,
        qback_offsets=qback_offsets,
        sample_path=sample,
    )
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
