#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/STEPS/STEP_10/plot_step_10.py
Purpose: Plots for STEP 10 — adapted from MASTER_STEPS/STEP_10/step_10_triggered_to_jitter.py.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/STEPS/STEP_10/plot_step_10.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import pandas as pd
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.backends.backend_pdf import PdfPages

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


def plot_tt_xy_histograms(df: pd.DataFrame, pdf: PdfPages) -> None:
    # Find all columns starting with 'tt_'
    tt_cols = [col for col in df.columns if col.startswith("tt_")]
    if "X_gen" not in df.columns or "Y_gen" not in df.columns:
        print("STEP_10: X_gen/Y_gen missing — skipping TT XY histograms.")
        return
    x_min, x_max, y_min, y_max = load_xy_hist_config()

    # Fallback: if there are no tt_* columns, produce a single overall 2D histogram
    if not tt_cols:
        print("STEP_10: no tt_* columns found — creating overall X_gen/Y_gen 2D histogram.")
        fig, ax = plt.subplots(figsize=(6, 6))
        x = df["X_gen"].to_numpy(dtype=float)
        y = df["Y_gen"].to_numpy(dtype=float)
        h = ax.hist2d(x, y, bins=80, range=[[x_min, x_max], [y_min, y_max]], cmap="turbo", norm=LogNorm(vmin=1))
        ax.set_title("2D Xgen/Ygen (all events — no tt_* columns present)")
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
        ax.set_title(f"2D Xgen/Ygen for {tt_col}")
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


def plot_rate_summary(df: pd.DataFrame, pdf: PdfPages) -> bool:
    if "T_thick_s" not in df.columns:
        return False
    t0_s = df["T_thick_s"].to_numpy(dtype=float)
    t0_s = t0_s[np.isfinite(t0_s)]
    if t0_s.size == 0:
        return False
    t0_s = np.sort(t0_s.astype(int))
    sec_min = int(t0_s[0])
    counts = np.bincount(t0_s - sec_min)
    seconds = np.arange(sec_min, sec_min + len(counts))
    if len(counts) > 1:
        counts = counts[1:]
        seconds = seconds[1:]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].plot(seconds, counts, linewidth=1.0, color="slateblue")
    axes[0].set_title("Counts per second (detector)")
    axes[0].set_xlabel("Second")
    axes[0].set_ylabel("Events")

    axes[1].hist(counts, bins=60, color="teal", alpha=0.8)
    axes[1].set_title("Histogram of counts per second")
    axes[1].set_xlabel("Events per second")
    axes[1].set_ylabel("Counts")

    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)
    return True


def pick_tt_column(df: pd.DataFrame) -> str | None:
    for col in ("tt_trigger", "tt_hit", "tt_avalanche", "tt_crossing"):
        if col in df.columns:
            return col
    return None


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


def plot_rate_by_tt(df: pd.DataFrame, pdf: PdfPages) -> bool:
    if "T_thick_s" not in df.columns:
        return False
    tt_col = pick_tt_column(df)
    if not tt_col:
        return False
    t0_s = df["T_thick_s"].to_numpy(dtype=float)
    tt_vals = df[tt_col].astype("string").fillna("")
    valid = np.isfinite(t0_s) & (tt_vals != "")
    if not valid.any():
        return False
    t0_s = t0_s[valid].astype(int)
    tt_vals = tt_vals[valid].to_numpy()
    minute_idx = (t0_s // 60).astype(int)
    minute_min = int(minute_idx.min())
    times = minute_idx - minute_min
    unique_tt = sorted(set(tt_vals))
    fig, ax = plt.subplots(figsize=(12, 4.5))
    for tt in unique_tt:
        mask = tt_vals == tt
        if not mask.any():
            continue
        counts = np.bincount(times[mask])
        minutes = np.arange(minute_min, minute_min + len(counts))
        if len(counts) > 1:
            counts = counts[1:]
            minutes = minutes[1:]
        ax.plot(minutes, counts, linewidth=1.0, label=str(tt))
    ax.set_title(f"Counts per minute by {tt_col}")
    ax.set_xlabel("Minute")
    ax.set_ylabel("Events")
    ax.legend(title=tt_col, ncol=3, fontsize=8)
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)
    return True


def plot_muon_differential_flux_vs_angle(df: pd.DataFrame, pdf: PdfPages, sample_path: Path | None = None) -> bool:
    if "Theta_gen" not in df.columns or "T_thick_s" not in df.columns:
        return False
    if "X_gen" not in df.columns or "Y_gen" not in df.columns:
        return False

    # use only events whose T_thick_s lie strictly inside the chunk (drop first and last floor-second)
    t0_all = df["T_thick_s"].to_numpy(dtype=float)
    if not np.isfinite(t0_all).any():
        return False
    sec_min = int(np.floor(np.nanmin(t0_all)))
    sec_max = int(np.floor(np.nanmax(t0_all)))
    # require at least one full inner second
    if sec_max <= sec_min + 1:
        return False
    # mask for inner seconds (strictly greater than min second and strictly less than max second)
    inner_mask = (np.floor(t0_all).astype(int) > sec_min) & (np.floor(t0_all).astype(int) < sec_max) & np.isfinite(t0_all)

    theta_all = df["Theta_gen"].to_numpy(dtype=float)
    theta = theta_all[np.isfinite(theta_all) & (theta_all >= 0.0) & (theta_all <= np.pi / 2.0) & inner_mask]
    if theta.size < 20:
        return False

    # duration corresponds to the inner-second window
    sec_min_inner = sec_min + 1
    sec_max_inner = sec_max - 1
    duration_s = float(sec_max_inner - sec_min_inner + 1)
    if not np.isfinite(duration_s) or duration_s <= 0.0:
        return False

    # Prefer observed spread-based area; fall back to nominal 900 cm^2 if needed.
    area_cm2 = 900.0
    x_all = df["X_gen"].to_numpy(dtype=float)
    y_all = df["Y_gen"].to_numpy(dtype=float)
    x_vals = x_all[np.isfinite(x_all) & inner_mask]
    y_vals = y_all[np.isfinite(y_all) & inner_mask]
    if x_vals.size >= 2 and y_vals.size >= 2:
        area_mm2 = float(np.max(x_vals) - np.min(x_vals)) * float(np.max(y_vals) - np.min(y_vals))
        if np.isfinite(area_mm2) and area_mm2 > 0.0:
            area_cm2 = area_mm2 / 100.0

    theta_edges = np.linspace(0.0, np.pi / 2.0, 31)
    theta_centers = 0.5 * (theta_edges[1:] + theta_edges[:-1])
    counts, _ = np.histogram(theta, bins=theta_edges)
    delta_omega = 2.0 * np.pi * (np.cos(theta_edges[:-1]) - np.cos(theta_edges[1:]))

    valid = (counts > 0) & np.isfinite(delta_omega) & (delta_omega > 0.0)
    if not np.any(valid):
        return False

    duration_min = duration_s / 60.0
    if not np.isfinite(duration_min) or duration_min <= 0.0:
        return False

    theta_deg = np.degrees(theta_centers[valid])
    delta_omega_valid = delta_omega[valid]
    counts_valid = counts[valid].astype(float)
    dndt_dadomega = counts_valid / (duration_min * area_cm2 * delta_omega_valid)
    dndt_dadomega_err = np.sqrt(counts_valid) / (duration_min * area_cm2 * delta_omega_valid)

    fig, (ax_top, ax_bottom) = plt.subplots(
        2,
        1,
        figsize=(8.5, 8.8),
        sharex=True,
        gridspec_kw={"height_ratios": [2.0, 1.1]},
    )
    ax_top.errorbar(
        theta_deg,
        dndt_dadomega,
        yerr=dndt_dadomega_err,
        fmt="o",
        markersize=4,
        linewidth=1.0,
        color="black",
        ecolor="gray",
        capsize=2,
        label=(
            f"Sample (N={theta.size}, T={duration_min:.3f} min, "
            f"Axy={area_cm2:.2f} cm^2)"
        ),
    )

    # Weighted log-fit: ln(I) = ln(I0) + n ln(cos(theta))
    fit_theta = theta_centers[valid]
    fit_counts = counts_valid
    fit_flux = dndt_dadomega
    fit_cos = np.cos(fit_theta)
    fit_ok = (fit_counts > 0.0) & (fit_flux > 0.0) & (fit_cos > 0.0)
    n_fit_out: float | None = None
    i0_fit_out: float | None = None
    if np.count_nonzero(fit_ok) >= 3:
        x_fit = np.log(np.clip(fit_cos[fit_ok], 1e-12, 1.0))
        y_fit = np.log(fit_flux[fit_ok])
        w_fit = fit_counts[fit_ok]
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
                fit_curve = i0_fit_out * np.power(np.clip(np.cos(theta_curve), 1e-12, 1.0), n_fit_out)
                ax_top.plot(
                    np.degrees(theta_curve),
                    fit_curve,
                    color="tab:orange",
                    linewidth=1.4,
                    linestyle="--",
                    label=rf"Fit: $I_0\cos^n(\theta)$, $I_0={i0_fit_out:.3e}$, $n={n_fit_out:.2f}$",
                )

    # Theory overlay from STEP 0 mesh (same convention as STEP 1/8).
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
            theory_curve = i0_theory * np.power(np.clip(np.cos(theta_curve), 1e-12, 1.0), cos_n)
            ax_top.plot(
                np.degrees(theta_curve),
                theory_curve,
                color="crimson",
                linewidth=1.6,
                label=rf"Theory: $I_0\cos^n(\theta)$, $I_0={i0_theory:.4g}$, $n={cos_n:.2f}$",
            )
    except Exception:
        pass





    cumulative_flux = np.cumsum(dndt_dadomega * delta_omega_valid)
    cumulative_flux_err = np.sqrt(np.cumsum((dndt_dadomega_err * delta_omega_valid) ** 2))
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
        cum_model_fit = (
            2.0
            * math.pi
            * i0_fit_out
            / (n_fit_out + 1.0)
            * (1.0 - np.power(np.clip(np.cos(theta_curve), 0.0, 1.0), n_fit_out + 1.0))
        )
        ax_bottom.plot(
            np.degrees(theta_curve),
            cum_model_fit,
            color="tab:orange",
            linewidth=1.2,
            linestyle="--",
            label="Fit cumulative",
        )
    ax_top.set_title("Muon differential flux vs zenith angle (area-normalized)")
    ax_top.set_ylabel("I(theta) [min^-1 cm^-2 sr^-1]")
    ax_top.set_xlim(0.0, 90.0)
    ax_top.set_ylim(bottom=0.0)
    ax_top.grid(alpha=0.3)
    ax_top.legend(loc="upper right")

    ax_bottom.set_xlabel("Zenith angle theta (deg)")
    ax_bottom.set_ylabel("Accumulated flux\n[min^-1 cm^-2]")
    ax_bottom.set_xlim(0.0, 90.0)
    ax_bottom.set_ylim(bottom=0.0)
    ax_bottom.grid(alpha=0.3)
    ax_bottom.legend(loc="upper left")

    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)
    return True


def plot_timing_closure_summary(
    df6: pd.DataFrame | None,
    df7: pd.DataFrame | None,
    df8: pd.DataFrame | None,
    df9: pd.DataFrame | None,
    df10: pd.DataFrame | None,
    cfg7: dict,
    cfg10: dict,
    pdf: PdfPages,
) -> None:
    if df10 is None:
        return
    tfront_offsets = cfg7.get("tfront_offsets", [[0, 0, 0, 0]] * 4)
    tback_offsets = cfg7.get("tback_offsets", [[0, 0, 0, 0]] * 4)
    tdc_sigma = float(cfg10.get("tdc_sigma_ns", 0.0))
    jitter_width = float(cfg10.get("jitter_width_ns", 0.0))
    expected_tdc_rms = np.sqrt(tdc_sigma ** 2 + (jitter_width ** 2) / 12.0)

    def collect_residual(
        after: pd.DataFrame,
        before: pd.DataFrame,
        side: str,
        offsets: list[list[float]] | None = None,
    ) -> np.ndarray:
        residuals = []
        for plane_idx in range(1, 5):
            for strip_idx in range(1, 5):
                col = f"T_{side}_{plane_idx}_s{strip_idx}"
                if col not in after.columns or col not in before.columns:
                    continue
                a = after[col].to_numpy(dtype=float)
                b = before[col].to_numpy(dtype=float)
                n = min(len(a), len(b))
                if n == 0:
                    continue
                a = a[:n]
                b = b[:n]
                mask = np.isfinite(a) & np.isfinite(b) & (a != 0) & (b != 0)
                if not mask.any():
                    continue
                res = a[mask] - b[mask]
                if offsets is not None:
                    expected = float(offsets[plane_idx - 1][strip_idx - 1])
                    res = res - expected
                residuals.append(res)
        if not residuals:
            return np.array([])
        return np.concatenate(residuals)

    def plot_hist(ax: plt.Axes, data: np.ndarray, title: str, expected_rms: float | None = None) -> None:
        if data.size == 0:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(title)
            return
        ax.hist(data, bins=80, color="slateblue", alpha=0.8)
        ax.set_title(title)
        ax.set_xlabel("Residual (ns)")
        ax.set_ylabel("Counts")
        if expected_rms is not None and np.isfinite(expected_rms):
            ax.axvline(expected_rms, color="black", linestyle="--", linewidth=1.0)
            ax.axvline(-expected_rms, color="black", linestyle="--", linewidth=1.0)

    rms_summary: dict[str, dict[str, np.ndarray]] = {}

    if df6 is not None:
        residuals = []
        for plane_idx in range(1, 5):
            for strip_idx in range(1, 5):
                tf = f"T_front_{plane_idx}_s{strip_idx}"
                tb = f"T_back_{plane_idx}_s{strip_idx}"
                td = f"T_diff_{plane_idx}_s{strip_idx}"
                if tf not in df6.columns or tb not in df6.columns or td not in df6.columns:
                    continue
                front = df6[tf].to_numpy(dtype=float)
                back = df6[tb].to_numpy(dtype=float)
                tdiff = df6[td].to_numpy(dtype=float)
                mask = np.isfinite(front) & np.isfinite(back) & np.isfinite(tdiff)
                if not mask.any():
                    continue
                residuals.append((front[mask] - back[mask]) + 2.0 * tdiff[mask])
        fig, ax = plt.subplots(figsize=(8, 5))
        data = np.concatenate(residuals) if residuals else np.array([])
        plot_hist(ax, data, "STEP 6: (T_front - T_back) + 2*T_diff")
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

    if df7 is not None and df6 is not None:
        res_front = collect_residual(df7, df6, side="front", offsets=tfront_offsets)
        res_back = collect_residual(df7, df6, side="back", offsets=tback_offsets)
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        plot_hist(axes[0], res_front, "STEP 7: T_front delta - offset")
        plot_hist(axes[1], res_back, "STEP 7: T_back delta - offset")
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)
        rms_summary["STEP 7"] = {"front": res_front, "back": res_back}

    if df8 is not None and df7 is not None:
        res_front = collect_residual(df8, df7, side="front", offsets=None)
        res_back = collect_residual(df8, df7, side="back", offsets=None)
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        plot_hist(axes[0], res_front, "STEP 8: T_front delta (FEE noise)")
        plot_hist(axes[1], res_back, "STEP 8: T_back delta (FEE noise)")
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)
        rms_summary["STEP 8"] = {"front": res_front, "back": res_back}

    if df9 is not None and df10 is not None:
        res_front = collect_residual(df10, df9, side="front", offsets=None)
        res_back = collect_residual(df10, df9, side="back", offsets=None)
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        plot_hist(axes[0], res_front, "STEP 10: T_front delta (TDC + jitter)", expected_rms=expected_tdc_rms)
        plot_hist(axes[1], res_back, "STEP 10: T_back delta (TDC + jitter)", expected_rms=expected_tdc_rms)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)
        rms_summary["STEP 10"] = {"front": res_front, "back": res_back}

    if rms_summary:
        stage_order = ["STEP 7", "STEP 8", "STEP 10"]
        stage_labels = [s for s in stage_order if s in rms_summary]
        x = np.arange(len(stage_labels), dtype=float)
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), sharex=True)
        for ax, side in zip(axes, ("front", "back")):
            rms_vals = []
            rms_err = []
            for stage in stage_labels:
                arr = rms_summary[stage][side]
                if arr.size == 0:
                    rms_vals.append(np.nan)
                    rms_err.append(np.nan)
                    continue
                rms = float(np.std(arr))
                # Approximate uncertainty of sample sigma for near-Gaussian residuals.
                err = rms / np.sqrt(max(2.0 * (arr.size - 1), 1.0))
                rms_vals.append(rms)
                rms_err.append(err)
            y = np.array(rms_vals, dtype=float)
            ye = np.array(rms_err, dtype=float)
            ok = np.isfinite(y) & np.isfinite(ye)
            if np.any(ok):
                ax.errorbar(
                    x[ok],
                    y[ok],
                    yerr=ye[ok],
                    fmt="o-",
                    capsize=3,
                    linewidth=1.6,
                    color="tab:blue" if side == "front" else "tab:orange",
                    label="RMS ± SE",
                )
            if np.isfinite(expected_tdc_rms):
                ax.axhline(expected_tdc_rms, color="gray", linestyle="--", linewidth=1.0, label="Expected STEP 10 RMS")
            ax.set_title(f"{side.capitalize()} timing RMS progression")
            ax.set_ylabel("Residual RMS (ns)")
            ax.set_xticks(x)
            ax.set_xticklabels(stage_labels, rotation=0)
            ax.grid(alpha=0.25)
            ax.legend(loc="best", fontsize=8)
        fig.suptitle("Timing broadening across electronics stages")
        fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
        pdf.savefig(fig, dpi=150)
        plt.close(fig)


def plot_jitter_summary(
    df: pd.DataFrame,
    output_path: Path,
    rate_df: pd.DataFrame | None = None,
    closure_dfs: dict | None = None,
    cfg7: dict | None = None,
    cfg10: dict | None = None,
    sample_path: Path | None = None,
) -> None:
    with PdfPages(output_path) as pdf:
        if rate_df is not None:
            added = plot_rate_summary(rate_df, pdf)
            if not added:
                print("Step 10 plots: skipped rate summary (T_thick_s missing).")
            added_tt = plot_rate_by_tt(rate_df, pdf)
            if not added_tt:
                print("Step 10 plots: skipped rate-by-TT summary (T_thick_s or tt column missing).")
        added_flux = plot_muon_differential_flux_vs_angle(df, pdf, sample_path=sample_path)
        if not added_flux:
            print("Step 10 plots: skipped muon differential flux plot (missing gen/time columns).")
        if closure_dfs and cfg7 is not None and cfg10 is not None:
            plot_timing_closure_summary(
                closure_dfs.get("step6"),
                closure_dfs.get("step7"),
                closure_dfs.get("step8"),
                closure_dfs.get("step9"),
                closure_dfs.get("step10"),
                cfg7,
                cfg10,
                pdf,
            )

        plot_frontback_asymmetry_diagnostics(df, pdf, stage_label="STEP 10")

        # --- 2D Xgen/Ygen histograms per tt_* ---
        plot_tt_xy_histograms(df, pdf)

        tt_col = pick_tt_column(df)
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
                    vals = vals[~np.isnan(vals)]
                    ax.hist(vals, bins=80, color="steelblue", alpha=0.6, label="front")
                if tb_col in df.columns:
                    vals = df[tb_col].to_numpy(dtype=float)
                    vals = vals[~np.isnan(vals)]
                    ax.hist(vals, bins=80, color="darkorange", alpha=0.6, label="back")
                ax.set_title(f"P{plane_idx} S{strip_idx}")
                ax.set_xlabel("time (ns)")
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

def find_any_chunk_for_step(step: int) -> Path | None:
    root = Path(__file__).resolve().parents[3] / "INTERSTEPS"
    parts = sorted(root.glob(f"**/step_{step}_chunks/part_*.pkl"))
    if parts:
        return parts[0]
    manifests = sorted(root.rglob(f"*step_{step}_chunks.chunks.json"))
    if manifests:
        try:
            j = json.loads(manifests[0].read_text())
            parts_list = [p for p in j.get("parts", []) if p.endswith(".pkl")]
            if parts_list:
                return Path(parts_list[0])
        except Exception:
            return manifests[0]
    return None


def load_df(path: Path) -> pd.DataFrame:
    if path.name.endswith(".chunks.json"):
        j = json.loads(path.read_text())
        parts = [p for p in j.get("parts", []) if p.endswith(".pkl")]
        if parts:
            path = Path(parts[0])
        else:
            raise FileNotFoundError("Manifest contains no .pkl parts")
    if path.suffix == ".pkl":
        return pd.read_pickle(path)
    raise ValueError("Unsupported chunk type")


# --- helpers to inspect upstream/metadata so we can render closure/jitter pages ---
def load_metadata(path: Path) -> dict:
    if path.name.endswith(".chunks.json"):
        return json.loads(path.read_text()).get("metadata", {})
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text())
        except Exception:
            return {}
    return {}


def resolve_upstream_chain(start_path: Path) -> dict:
    chain = {}
    # Keep the provided STEP 10 sample path as STEP 10.
    step10_path = start_path.resolve()
    chain["step10"] = step10_path

    # walk upstream via metadata.source_dataset
    def _src(path: Path) -> Path | None:
        m = load_metadata(path)
        src = m.get("source_dataset")
        if not src:
            return None
        src_path = Path(str(src))
        if not src_path.is_absolute():
            src_path = (path.parent / src_path).resolve()
        else:
            src_path = src_path.resolve()
        return src_path if src_path.exists() else None

    step9 = _src(step10_path)
    if step9:
        chain["step9"] = step9
        step8 = _src(step9)
        if step8:
            chain["step8"] = step8
            step7 = _src(step8)
            if step7:
                chain["step7"] = step7
                step6 = _src(step7)
                if step6:
                    chain["step6"] = step6
    return chain


def main() -> None:
    step = 10
    sample = find_any_chunk_for_step(step)
    if sample is None:
        print("No sample chunk found for STEP 10; exiting.")
        return
    print(f"Using sample: {sample}")

    # load the primary dataframe for STEP 10
    df = load_df(sample)

    # attempt to resolve upstream sample files and configs for closure plots
    chain = resolve_upstream_chain(sample)
    closure_dfs: dict = {}
    cfg7 = {}
    cfg10 = {}
    for sname in ("step6", "step7", "step8", "step9", "step10"):
        p = chain.get(sname)
        if p and p.exists():
            try:
                closure_dfs[sname] = load_df(p)
            except Exception:
                closure_dfs[sname] = None
    # try to load cfg7/cfg10 from metadata if available
    if "step7" in chain:
        cfg7 = load_metadata(chain["step7"]).get("config", {}) or {}
    if "step10" in chain:
        cfg10 = load_metadata(chain["step10"]).get("config", {}) or {}

    out_dir = Path(__file__).resolve().parent / "PLOTS"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"step_{step}_sample_plots.pdf"

    # produce the full STEP_10 PDF (rate + rate_by_tt + closure/jitter pages)
    plot_jitter_summary(
        df,
        out_path,
        rate_df=df,
        closure_dfs=closure_dfs,
        cfg7=cfg7,
        cfg10=cfg10,
        sample_path=sample,
    )
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
