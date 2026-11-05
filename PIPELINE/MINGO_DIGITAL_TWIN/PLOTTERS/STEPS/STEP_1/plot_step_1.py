#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/STEPS/STEP_1/plot_step_1.py
Purpose: Plots for STEP 1 — adapted from MASTER_STEPS/STEP_1/step_1_blank_to_generated.py.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/STEPS/STEP_1/plot_step_1.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import json
from pathlib import Path
import pickle
import sys

import numpy as np
import pandas as pd
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


# --- copied/adapted plotting functions (full parity with MASTER) -----------------

def plot_muon_sample(df: pd.DataFrame, pdf: PdfPages) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    _, _, patches = axes[0, 0].hist(df["X_gen"], bins=100, color="steelblue", alpha=0.8)
    for patch in patches:
        patch.set_rasterized(True)
    axes[0, 0].set_title("X_gen distribution")
    axes[0, 0].set_xlabel("X (mm)")
    axes[0, 0].set_ylabel("Counts")

    _, _, patches = axes[0, 1].hist(df["Y_gen"], bins=100, color="seagreen", alpha=0.8)
    for patch in patches:
        patch.set_rasterized(True)
    axes[0, 1].set_title("Y_gen distribution")
    axes[0, 1].set_xlabel("Y (mm)")

    _, _, patches = axes[1, 0].hist(df["Theta_gen"], bins=100, color="darkorange", alpha=0.8)
    for patch in patches:
        patch.set_rasterized(True)
    axes[1, 0].set_title("Theta_gen distribution")
    axes[1, 0].set_xlabel("Theta (rad)")

    _, _, patches = axes[1, 1].hist(df["Phi_gen"], bins=100, color="slateblue", alpha=0.8)
    for patch in patches:
        patch.set_rasterized(True)
    axes[1, 1].set_title("Phi_gen distribution")
    axes[1, 1].set_xlabel("Phi (rad)")

    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(df["Theta_gen"], df["Phi_gen"], s=1, alpha=0.2, rasterized=True)
    ax.set_title("Theta vs Phi")
    ax.set_xlabel("Theta (rad)")
    ax.set_ylabel("Phi (rad)")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def plot_step1_summary(df: pd.DataFrame, pdf: PdfPages) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    axes[0, 0].hist2d(df["X_gen"], df["Y_gen"], bins=60, cmap="viridis")
    axes[0, 0].set_title("X_gen vs Y_gen (density)")
    axes[0, 0].set_xlabel("X (mm)")
    axes[0, 0].set_ylabel("Y (mm)")

    h = axes[0, 1].hist2d(df["Theta_gen"], df["Phi_gen"], bins=60, cmap="magma")
    axes[0, 1].set_title("Theta_gen vs Phi_gen (density)")
    axes[0, 1].set_xlabel("Theta (rad)")
    axes[0, 1].set_ylabel("Phi (rad)")
    for quad in h[3].get_paths():
        quad._interpolation_steps = 1

    cos_theta = np.cos(df["Theta_gen"].to_numpy(dtype=float))
    axes[1, 0].hist(cos_theta, bins=80, color="darkorange", alpha=0.8)
    axes[1, 0].set_title("cos(Theta_gen)")
    axes[1, 0].set_xlabel("cos(theta)")

    r = np.hypot(df["X_gen"].to_numpy(dtype=float), df["Y_gen"].to_numpy(dtype=float))
    axes[1, 1].hist(r, bins=80, color="slateblue", alpha=0.8)
    axes[1, 1].set_title("Radial distance")
    axes[1, 1].set_xlabel("sqrt(X^2+Y^2) (mm)")

    for ax in axes.flatten():
        for patch in ax.patches:
            patch.set_rasterized(True)
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def plot_thick_time_summary(df: pd.DataFrame, pdf: PdfPages, rate_hz: float | None) -> bool:
    if "T_thick_s" not in df.columns:
        return False
    t0_s = df["T_thick_s"].to_numpy(dtype=float)
    t0_s = t0_s[np.isfinite(t0_s)]
    if t0_s.size < 2:
        return False
    t0_s = np.sort(t0_s.astype(int))
    if t0_s.size == 0:
        return False
    sec_min = int(t0_s[0])
    sec_max = int(t0_s[-1])
    counts = np.bincount(t0_s - sec_min)
    seconds = np.arange(sec_min, sec_min + len(counts))
    if len(counts) > 1:
        counts = counts[1:]
        seconds = seconds[1:]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].plot(seconds, counts, linewidth=1.0, color="slateblue")
    axes[0].set_title("Counts per second")
    axes[0].set_xlabel("Second")
    axes[0].set_ylabel("Events")

    axes[1].hist(counts, bins=60, color="teal", alpha=0.8)
    axes[1].set_title("Histogram of counts per second")
    axes[1].set_xlabel("Events per second")
    axes[1].set_ylabel("Counts")
    if rate_hz and rate_hz > 0:
        axes[1].axvline(rate_hz, color="black", linestyle="--", linewidth=1.0)

    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)
    return True


def plot_muon_differential_flux_vs_angle(df: pd.DataFrame, pdf: PdfPages, sample_path: Path | None = None) -> bool:
    if "Theta_gen" not in df.columns or "T_thick_s" not in df.columns:
        return False
    if "X_gen" not in df.columns or "Y_gen" not in df.columns:
        return False

    # drop the first and last recorded floor-seconds from the chunk (keep only inner seconds)
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

    # duration of the inner window (seconds)
    sec_min_inner = sec_min + 1
    sec_max_inner = sec_max - 1
    duration_s = float(sec_max_inner - sec_min_inner + 1)
    if not np.isfinite(duration_s) or duration_s <= 0.0:
        return False

    # use X/Y from the inner-window events to compute detector area
    x_all = df["X_gen"].to_numpy(dtype=float)
    y_all = df["Y_gen"].to_numpy(dtype=float)
    x_vals = x_all[np.isfinite(x_all) & inner_mask]
    y_vals = y_all[np.isfinite(y_all) & inner_mask]
    if x_vals.size < 2 or y_vals.size < 2:
        return False
    x_spread_mm = float(np.max(x_vals) - np.min(x_vals))
    y_spread_mm = float(np.max(y_vals) - np.min(y_vals))
    area_mm2 = x_spread_mm * y_spread_mm
    area_cm2 = area_mm2 / 100.0
    if not np.isfinite(area_cm2) or area_cm2 <= 0.0:
        return False

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
        if np.isfinite(den) and abs(den) > 1e-15 and np.isfinite(sw) and sw > 0.0:
            n_fit = (sw * sxy - sx * sy) / den
            ln_a_fit = (sy - n_fit * sx) / sw
            if np.isfinite(n_fit) and np.isfinite(ln_a_fit):
                a_fit = float(np.exp(ln_a_fit))
                n_fit_out = float(n_fit)
                i0_fit_out = float(a_fit)
                theta_curve = np.linspace(0.0, np.pi / 2.0 - 1e-4, 400)
                cos_curve = np.clip(np.cos(theta_curve), 1e-12, 1.0)
                model_curve = a_fit * np.power(cos_curve, n_fit)
                fit_label = (
                    r"Fit: $I(\theta)=I_0\cdot\cos^{n}(\theta)$"
                    + "\n"
                    + rf"$I_0={a_fit:.3e}$ min$^{{-1}}$ cm$^{{-2}}$ sr$^{{-1}}$, $n={n_fit:.2f}$"
                )
                # show fit (if present) in a distinct style — theoretical model will use the red color
                ax_top.plot(
                    np.degrees(theta_curve),
                    model_curve,
                    color="tab:orange",
                    linewidth=1.2,
                    linestyle="--",
                    label=fit_label,
                )

    # --- Theoretical model from param_mesh.csv (use closed-form I0 from n and integrated flux F) ---
    try:
        param_path = Path(__file__).resolve().parents[3] / "INTERSTEPS" / "STEP_0_TO_1" / "param_mesh.csv"
        cos_n = 2.0
        flux_F = None
        if param_path.exists():
            pm = pd.read_csv(param_path)
            step1_id = None
            # try to extract step_1_id from provided sample_path's metadata (if any)
            if sample_path is not None:
                try:
                    if sample_path.name.endswith('.chunks.json'):
                        meta = json.loads(sample_path.read_text()).get('metadata', {})
                    else:
                        meta_path = sample_path.with_suffix(sample_path.suffix + '.meta.json')
                        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
                except Exception:
                    meta = {}
                cfg = meta.get('config', {}) if isinstance(meta, dict) else {}
                step1_id = cfg.get('step_1_id') or meta.get('step_1_id')
            rows = pm[pm['step_1_id'].astype(str) == str(step1_id)] if step1_id is not None else pm
            if rows.empty:
                rows = pm
            row = rows.iloc[0]
            cos_n = float(row.get('cos_n', 2.0))
            flux_F = float(row.get('flux_cm2_min', float('nan')))
        if flux_F is None or not np.isfinite(flux_F):
            raise RuntimeError('param mesh flux not available')
        n_theory = float(cos_n)
        # interpret flux_F (from param_mesh.csv) as the total integrated flux
        # over solid angle (units: min^-1 cm^-2). For I(θ)=I0 cos^n(θ) one has
        #   flux = \int_Ω I(θ) dΩ = 2π * I0 / (n + 1)
        # => I0 = flux * (n + 1) / (2π)
        i0_theory = float(flux_F * (n_theory + 1.0) / (2.0 * math.pi))
        theta_curve = np.linspace(0.0, np.pi / 2.0 - 1e-4, 400)
        cos_curve = np.clip(np.cos(theta_curve), 1e-12, 1.0)
        theory_curve = i0_theory * np.power(cos_curve, n_theory)
        theory_label = (
            r"Theory: $I(\theta)=I_0\cdot\cos^{n}(\theta)$"
            + "\n"
            + rf"$I_0={i0_theory:.4g}$ min$^{{-1}}$ cm$^{{-2}}$ sr$^{{-1}}$, $n={n_theory:.2f}$"
        )
        ax_top.plot(np.degrees(theta_curve), theory_curve, color="crimson", linewidth=1.6, label=theory_label)
    except Exception:
        # if theory unavailable, keep behavior as before (no theoretical model)
        n_theory = None
        i0_theory = None
        theta_curve = np.linspace(0.0, np.pi / 2.0 - 1e-4, 400)
        cos_curve = np.clip(np.cos(theta_curve), 1e-12, 1.0)

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

    # dashed horizontal y-line for the flux value used by the generator
    if 'flux_F' in locals():
        try:
            flux_param = float(flux_F)
        except Exception:
            flux_param = None
        if flux_param is not None and np.isfinite(flux_param):
            ax_bottom.axhline(
                flux_param,
                color="crimson",
                linestyle="--",
                linewidth=1.2,
                label=f"F (flux_cm2_min) = {flux_param:.4g} min^-1 cm^-2",
            )

    # Plot theoretical cumulative (prefer theory values from param_mesh if available)
    try:
        if 'i0_theory' in locals() and i0_theory is not None and 'n_theory' in locals() and n_theory is not None:
            theta_curve = np.linspace(0.0, np.pi / 2.0 - 1e-4, 400)
            cum_model = (
                2.0
                * np.pi
                * i0_theory
                / (n_theory + 1.0)
                * (1.0 - np.power(np.clip(np.cos(theta_curve), 0.0, 1.0), n_theory + 1.0))
            )
            ax_bottom.plot(
                np.degrees(theta_curve),
                cum_model,
                color="crimson",
                linewidth=1.5,
                label="Theory cumulative from I0*cos^n(theta)",
            )
    except Exception:
        pass

    # If a fit was found, overlay its cumulative in a distinct style
    if n_fit_out is not None and i0_fit_out is not None:
        theta_curve = np.linspace(0.0, np.pi / 2.0 - 1e-4, 400)
        cum_model_fit = (
            2.0
            * np.pi
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
            label="Fit cumulative (dashed)",
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


# --- helpers: locate + load a chunk/sample from INTERSTEPS -----------------------

def find_any_chunk_for_step(step: int) -> Path | None:
    root = Path(__file__).resolve().parents[3] / "INTERSTEPS"

    # 1) prefer explicit step_N_chunks/part_*.pkl
    parts = sorted(root.glob(f"**/step_{step}_chunks/part_*.pkl"))
    if parts:
        return parts[0]

    # 2) accept `muon_sample_<N>/chunks/part_*.pkl` (STEP 1 commonly stored this way)
    parts = sorted(root.glob(f"**/muon_sample_*/chunks/part_*.pkl"))
    if parts:
        return parts[0]

    # 3) accept standalone muon_sample_*.pkl files
    parts = sorted(root.glob(f"**/muon_sample_*.pkl"))
    if parts:
        return parts[0]

    # 4) fall back to manifests for either form (step_*_chunks or muon_sample_*.chunks.json)
    manifests = sorted(root.rglob(f"*step_{step}_chunks.chunks.json")) + sorted(root.rglob("**/muon_sample_*.chunks.json"))
    for manifest in manifests:
        try:
            j = json.loads(manifest.read_text())
            parts_list = [p for p in j.get("parts", []) if p.endswith(".pkl")]
            if parts_list:
                return Path(parts_list[0])
        except Exception:
            return manifest
    return None


def plot_geant4_like_muons(df: pd.DataFrame, pdf: PdfPages) -> None:
    """
    Geant4-like 3D view showing:
      - a semitransparent XY plane (detector envelope),
      - four 300x300 mm detector planes at z = 0, 100, 200, 400 mm,
      - origin markers at (X_gen, Y_gen, Z_gen) when available,
      - arrows (thin, semi-transparent) showing direction from Theta_gen/Phi_gen.

    The arrow origins use `Z_gen` if present; vectors are drawn with `quiver`
    so arrowheads are visible and all arrows have the same visual length.
    """

    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 unused import

    # Prepare 2x2 subplot grid
    fig = plt.figure(figsize=(14, 12))
    axes = []
    for i in range(4):
        ax = fig.add_subplot(2, 2, i + 1, projection="3d")
        axes.append(ax)

    # detector / floor plane size
    base_plane = 300.0
    xx, yy = np.meshgrid(
        np.linspace(-base_plane / 2.0, base_plane / 2.0, 2),
        np.linspace(-base_plane / 2.0, base_plane / 2.0, 2),
    )
    det_z = [0.0, -100.0, -200.0, -400.0]
    corners_x = [-base_plane / 2.0, base_plane / 2.0, base_plane / 2.0, -base_plane / 2.0, -base_plane / 2.0]
    corners_y = [-base_plane / 2.0, -base_plane / 2.0, base_plane / 2.0, base_plane / 2.0, -base_plane / 2.0]

    # collect valid rows (must have X_gen, Y_gen, Theta_gen, Phi_gen, and |X_gen|,|Y_gen| < 1000)
    mask = (
        df["X_gen"].notna()
        & df["Y_gen"].notna()
        & df["Theta_gen"].notna()
        & df["Phi_gen"].notna()
        & (np.abs(df["X_gen"]) < 500)
        & (np.abs(df["Y_gen"]) < 500)
    )
    filtered_df = df[mask]
    sample_df = filtered_df.sample(50, random_state=42) if len(filtered_df) > 50 else filtered_df.copy()

    if sample_df.empty:
        for ax in axes:
            ax.text(0.5, 0.5, 0.5, "No valid muons to plot", transform=ax.transAxes)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)
        return

    # origins: use Z_gen if present, otherwise assume z=0
    if "Z_gen" in sample_df.columns:
        z0_arr = sample_df["Z_gen"].to_numpy(dtype=float)
    else:
        z0_arr = np.zeros(len(sample_df), dtype=float)
    x0_arr = sample_df["X_gen"].to_numpy(dtype=float)
    y0_arr = sample_df["Y_gen"].to_numpy(dtype=float)

    # directions (unit vectors) from theta/phi
    theta_arr = sample_df["Theta_gen"].to_numpy(dtype=float)
    phi_arr = sample_df["Phi_gen"].to_numpy(dtype=float)
    ux = np.sin(theta_arr) * np.cos(phi_arr)
    uy = np.sin(theta_arr) * np.sin(phi_arr)
    uz = -np.cos(theta_arr)  # inverted Z-axis for downward-going muons
    L = 200.0
    norms = np.sqrt(ux * ux + uy * uy + uz * uz)
    norms[norms == 0] = 1.0
    ux_unit = ux / norms
    uy_unit = uy / norms
    uz_unit = uz / norms

    # Set up the four views: (row, col):
    # (0,0): original (elev=20, azim=30)
    # (0,1): left (elev=20, azim=120)
    # (1,0): right (elev=20, azim=-60)
    # (1,1): top (elev=90, azim=0)
    views = [
        (20, 30, "3D view (default)"),
        (0, 0, "Left view (azim=120°)"),
        (0, 90, "Right view (azim=-60°)"),
        (90, 0, "Top view (elev=90°)")
    ]

    for ax, (elev, azim, title) in zip(axes, views):
        # semitransparent base plane at z = 0
        ax.plot_surface(xx, yy, np.zeros_like(xx), color="skyblue", alpha=0.12, zorder=1)
        # detector planes
        for z in det_z:
            ax.plot_surface(xx, yy, np.full_like(xx, z), color="lightgray", alpha=0.18, zorder=1)
            ax.plot(corners_x, corners_y, [z] * 5, color="k", linewidth=0.6, alpha=0.35)
        # Draw arrows (thin, semi-transparent) and origin markers
        ax.quiver(
            x0_arr,
            y0_arr,
            z0_arr,
            ux_unit,
            uy_unit,
            uz_unit,
            length=L,
            normalize=False,
            linewidth=0.6,
            arrow_length_ratio=0.12,
            color="crimson",
            alpha=0.65,
            zorder=4,
        )
        ax.scatter(x0_arr, y0_arr, z0_arr, color="navy", s=18, alpha=0.9, zorder=5)
        # autoscale XY axes to include sample + detector plane
        margin = 20.0
        max_xy = max(
            base_plane / 2.0,
            float(np.nanmax(np.abs(x0_arr))) if x0_arr.size else base_plane / 2.0,
            float(np.nanmax(np.abs(y0_arr))) if y0_arr.size else base_plane / 2.0,
        )
        lim = max_xy + margin
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        # Z limits — include muon endpoints and detector stack
        z_ends = z0_arr + uz_unit * L
        z_lower = float(np.nanmin(np.minimum(z_ends, z0_arr))) - 30.0
        z_upper = float(np.nanmax(np.maximum(z_ends, z0_arr))) + 30.0
        z_lower = min(z_lower, min(det_z) - 30.0)
        z_upper = max(z_upper, max(det_z) + 30.0)
        ax.set_zlim(z_lower, z_upper)
        try:
            ax.set_box_aspect([
                ax.get_xlim3d()[1] - ax.get_xlim3d()[0],
                ax.get_ylim3d()[1] - ax.get_ylim3d()[0],
                ax.get_zlim3d()[1] - ax.get_zlim3d()[0]
            ])
        except Exception:
            pass
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
        ax.set_zlabel("Z (mm)")
        ax.set_title(title)
        if elev == 20 and azim == 30:
            ax.text2D(
                0.02,
                0.94,
                "Origins = dots; arrows = direction from Theta_gen/Phi_gen",
                transform=ax.transAxes,
                fontsize=9,
                color="black",
                alpha=0.7,
            )
        ax.view_init(elev=elev, azim=azim)

    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

def load_df(path: Path) -> pd.DataFrame:
    if path is None:
        raise FileNotFoundError("No chunk file found for requested step.")
    if path.name.endswith(".chunks.json"):
        j = json.loads(path.read_text())
        parts = [p for p in j.get("parts", []) if p.endswith(".pkl")]
        if parts:
            path = Path(parts[0])
        else:
            raise FileNotFoundError(f"Manifest {path} contains no .pkl parts")
    if path.suffix == ".pkl":
        try:
            return pd.read_pickle(path)
        except Exception:
            with open(path, "rb") as fh:
                return pickle.load(fh)
    raise ValueError(f"Unsupported chunk file type: {path}")


def main() -> None:
    step = 1
    sample_path = find_any_chunk_for_step(step)
    if sample_path is None:
        print("No sample chunk found for STEP 1 under INTERSTEPS; exiting.")
        return
    print(f"Using sample: {sample_path}")
    try:
        df = load_df(sample_path)
    except Exception as exc:
        print(f"Failed to load sample chunk: {exc}")
        return

    out_dir = Path(__file__).resolve().parent / "PLOTS"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"step_{step}_sample_plots.pdf"
    with PdfPages(out_path) as pdf:
        plot_muon_sample(df, pdf)
        plot_step1_summary(df, pdf)
        plot_muon_differential_flux_vs_angle(df, pdf, sample_path=sample_path)
        plot_geant4_like_muons(df, pdf)
    print(f"Saved plots to {out_path}")


if __name__ == "__main__":
    main()
