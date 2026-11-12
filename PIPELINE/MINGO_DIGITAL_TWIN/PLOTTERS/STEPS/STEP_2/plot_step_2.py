#!/usr/bin/env python3

"""Plots for STEP 2 — adapted from MASTER_STEPS/STEP_2/step_2_generated_to_crossing.py."""

from __future__ import annotations

from pathlib import Path
import json
import pickle
import sys

import numpy as np
import pandas as pd
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def plot_geometry_summary(df: pd.DataFrame, pdf: PdfPages, title: str = "Geometry") -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    plane_cols = [(f"X_gen_{i}", f"Y_gen_{i}") for i in range(1, 5)]
    for ax, (x_col, y_col) in zip(axes.flatten(), plane_cols):
        if x_col not in df or y_col not in df:
            ax.axis("off")
            continue
        x = df[x_col].to_numpy()
        y = df[y_col].to_numpy()
        mask = ~np.isnan(x) & ~np.isnan(y)
        ax.scatter(x[mask], y[mask], s=1, alpha=0.2, rasterized=True)
        ax.set_title(f"{x_col} vs {y_col}")
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
    fig.suptitle(title)
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    # Per-`tt_crossing` diagnostic pages (copied from MASTER STEP_2)
    # Only plot per-tt Theta/Phi pages when the angle columns are present.
    if "tt_crossing" in df.columns and "Theta_gen" in df.columns and "Phi_gen" in df.columns:
        crossing_values = pd.Series(df["tt_crossing"]).dropna().astype(str)
        for ct in sorted(crossing_values.unique()):
            ct_df = df[df["tt_crossing"] == ct]
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))
            axes[0].scatter(ct_df["Theta_gen"], ct_df["Phi_gen"], s=6, alpha=0.25, rasterized=True)
            axes[0].set_title(f"Theta vs Phi (tt_crossing={ct})")
            axes[0].set_xlabel("Theta (rad)")
            axes[0].set_ylabel("Phi (rad)")
            axes[0].set_xlim(0, np.pi / 2)
            axes[0].set_ylim(-np.pi, np.pi)

            axes[1].hist2d(ct_df["Theta_gen"], ct_df["Phi_gen"], bins=60, cmap="magma")
            axes[1].set_title(f"Theta vs Phi density (tt_crossing={ct})")
            axes[1].set_xlabel("Theta (rad)")
            axes[1].set_ylabel("Phi (rad)")
            axes[1].set_xlim(0, np.pi / 2)
            axes[1].set_ylim(-np.pi, np.pi)
            fig.tight_layout()
            pdf.savefig(fig, dpi=150)
            plt.close(fig)
    else:
        # angles not available in this chunk — skip per-tt Theta/Phi pages
        pass

def plot_step2_summary(df: pd.DataFrame, pdf: PdfPages) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    axes = axes.flatten()

    x_cols = [c for c in df.columns if c.startswith("X_gen_")]
    x_vals = df[x_cols].to_numpy(dtype=float).ravel() if x_cols else np.array([])
    x_vals = x_vals[~np.isnan(x_vals)]
    axes[0].hist(x_vals, bins=80, color="steelblue", alpha=0.8)
    axes[0].set_title("X_gen_i")

    y_cols = [c for c in df.columns if c.startswith("Y_gen_")]
    y_vals = df[y_cols].to_numpy(dtype=float).ravel() if y_cols else np.array([])
    y_vals = y_vals[~np.isnan(y_vals)]
    axes[1].hist(y_vals, bins=80, color="seagreen", alpha=0.8)
    axes[1].set_title("Y_gen_i")

    t_cols = [c for c in df.columns if c.startswith("T_sum_") and c.endswith("_ns")]
    t_vals = df[t_cols].to_numpy(dtype=float).ravel() if t_cols else np.array([])
    t_vals = t_vals[~np.isnan(t_vals)]
    t_vals = t_vals[t_vals != 0]
    axes[2].hist(t_vals, bins=80, color="darkorange", alpha=0.8)
    axes[2].set_title("T_sum_i_ns")

    counts = df.get("tt_crossing")
    if counts is not None:
        counts = pd.Series(counts).astype("string").fillna("")
        vc = counts.value_counts().sort_index()
        bars = axes[3].bar(vc.index.astype(str), vc.values, color="slateblue", alpha=0.8)
        for patch in bars:
            patch.set_rasterized(True)
        axes[3].set_title("tt_crossing")
    else:
        axes[3].axis("off")

    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def plot_muon_differential_flux_vs_angle(df: pd.DataFrame, pdf: PdfPages, sample_path: Path | None = None) -> bool:
    """Self-contained STEP-2 version — computes and divides by solid angle per bin.

    This intentionally implements the full logic locally (no cross-file calls)
    so the division by solid angle is explicit and auditable here.
    """
    # required columns
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
    duration_min = duration_s / 60.0
    print(f"[DIAG] Area calculation: sec_min={sec_min}, sec_max={sec_max}, duration_min={duration_min:.3f} min")

    # determine area: prefer X_gen/Y_gen spread if present, else fixed 900 cm^2
    area_cm2 = 900.0
    if "X_gen" in df.columns and "Y_gen" in df.columns:
        x_all = df["X_gen"].to_numpy(dtype=float)
        y_all = df["Y_gen"].to_numpy(dtype=float)
        x_vals = x_all[np.isfinite(x_all) & inner_mask]
        y_vals = y_all[np.isfinite(y_all) & inner_mask]
        if x_vals.size >= 2 and y_vals.size >= 2:
            area_mm2 = float(np.max(x_vals) - np.min(x_vals)) * float(np.max(y_vals) - np.min(y_vals))
            if area_mm2 > 0.0:
                area_cm2 = area_mm2 / 100.0
        print(f"[DIAG] Area: {area_cm2:.3f} cm^2 (from X_gen/Y_gen spread)")

    # bin the theta distribution and compute solid angle per bin explicitly
    theta_edges = np.linspace(0.0, np.pi / 2.0, 31)
    theta_centers = 0.5 * (theta_edges[1:] + theta_edges[:-1])
    counts, _ = np.histogram(theta, bins=theta_edges)

    # solid angle for each theta bin = 2π (cos(theta_i) - cos(theta_{i+1}))
    delta_omega = 2.0 * np.pi * (np.cos(theta_edges[:-1]) - np.cos(theta_edges[1:]))

    # keep only bins with counts and valid solid angle
    valid = (counts > 0) & np.isfinite(delta_omega) & (delta_omega > 0.0)
    if not np.any(valid):
        return False

    theta_deg = np.degrees(theta_centers[valid])
    delta_omega_valid = delta_omega[valid]
    counts_valid = counts[valid].astype(float)

    # IMPORTANT: divide by the per-bin solid angle (sr) — this yields I(θ) in [min^-1 cm^-2 sr^-1]
    dndt_dadomega = counts_valid / (duration_min * area_cm2 * delta_omega_valid)
    dndt_dadomega_err = np.sqrt(counts_valid) / (duration_min * area_cm2 * delta_omega_valid)

    # plotting (matching STEP_10 visuals)
    fig, (ax_top, ax_bottom) = plt.subplots(
        2,
        1,
        figsize=(8.5, 8.8),
        sharex=True,
        gridspec_kw={"height_ratios": [2.0, 1.1]},
    )
    # plot overall sample (kept as a faint reference) — we'll split by `tt_crossing` below
    ax_top.errorbar(
        theta_deg,
        dndt_dadomega,
        yerr=dndt_dadomega_err,
        fmt="o",
        markersize=3,
        linewidth=0.8,
        color="lightgray",
        ecolor="lightgray",
        capsize=1,
        label=(
            f"All events (N={theta.size})"
        ),
    )
    print(f"[DIAG] Overall: N_events={theta.size}, area_cm2={area_cm2:.3f}, duration_min={duration_min:.3f}")

    # --- Split differential flux by tt_crossing categories (STEP 2 specific) ---
    tt_values = []
    if "tt_crossing" in df.columns:
        tt_ser = pd.Series(df["tt_crossing"]).astype("string").fillna("")
        # order by frequency (most common first) but keep string labels
        vc = tt_ser.value_counts()
        tt_values = [str(v) for v in vc.index if str(v) != ""]

    category_traces = {}
    cmap = plt.get_cmap("tab10")
    for i, tt_label in enumerate(tt_values):
        # mask rows with this tt_crossing value and inside inner seconds
        mask_tt = (tt_ser == tt_label).to_numpy(dtype=bool) & inner_mask
        if not mask_tt.any():
            continue
        # Per-category duration and area
        t0_tt = t0_all[mask_tt & np.isfinite(t0_all)]
        if t0_tt.size == 0:
            continue
        sec_min_tt = int(np.floor(np.nanmin(t0_tt)))
        sec_max_tt = int(np.floor(np.nanmax(t0_tt)))
        sec_min_inner_tt = sec_min_tt + 1
        sec_max_inner_tt = sec_max_tt - 1
        duration_s_tt = float(sec_max_inner_tt - sec_min_inner_tt + 1)
        if not np.isfinite(duration_s_tt) or duration_s_tt <= 0.0:
            continue
        duration_min_tt = duration_s_tt / 60.0
        # Per-category area
        area_cm2_tt = 900.0
        if "X_gen" in df.columns and "Y_gen" in df.columns:
            x_tt = x_all[mask_tt & np.isfinite(x_all)]
            y_tt = y_all[mask_tt & np.isfinite(y_all)]
            if x_tt.size >= 2 and y_tt.size >= 2:
                area_mm2_tt = float(np.max(x_tt) - np.min(x_tt)) * float(np.max(y_tt) - np.min(y_tt))
                if area_mm2_tt > 0.0:
                    area_cm2_tt = area_mm2_tt / 100.0
        theta_tt = theta_all[mask_tt & np.isfinite(theta_all) & (theta_all >= 0.0) & (theta_all <= np.pi / 2.0)]
        if theta_tt.size == 0:
            continue
        counts_tt, _ = np.histogram(theta_tt, bins=theta_edges)
        counts_tt_valid = counts_tt[valid].astype(float)
        flux_tt = counts_tt_valid / (duration_min_tt * area_cm2_tt * delta_omega_valid)
        flux_tt_err = np.sqrt(counts_tt_valid) / (duration_min_tt * area_cm2_tt * delta_omega_valid)
        n_events_tt = int(counts_tt.sum())
        color = cmap(i % cmap.N)
        category_traces[tt_label] = {
            "theta_deg": theta_deg,
            "flux": flux_tt,
            "err": flux_tt_err,
            "counts": counts_tt_valid,
            "n": n_events_tt,
            "color": color,
        }
        ax_top.plot(theta_deg, flux_tt, marker="o", linestyle="-", color=color, linewidth=1.2, markersize=4, label=f"tt={tt_label} (N={n_events_tt})")
        print(f"[DIAG] tt_crossing={tt_label}: N_events={n_events_tt}, area_cm2={area_cm2_tt:.3f}, duration_min={duration_min_tt:.3f}")

    # --- Sum line: sum of categories with numeric tt_crossing > 10 ---
    sum_labels = [lbl for lbl in category_traces.keys() if lbl.isdigit() and int(lbl) > 10]
    if sum_labels:
        # For sum, use the union of all events in sum_labels for area/duration
        mask_sum = np.zeros_like(inner_mask, dtype=bool)
        for lbl in sum_labels:
            mask_sum |= (tt_ser == lbl).to_numpy(dtype=bool) & inner_mask
        t0_sum = t0_all[mask_sum & np.isfinite(t0_all)]
        sec_min_sum = int(np.floor(np.nanmin(t0_sum))) if t0_sum.size > 0 else sec_min
        sec_max_sum = int(np.floor(np.nanmax(t0_sum))) if t0_sum.size > 0 else sec_max
        sec_min_inner_sum = sec_min_sum + 1
        sec_max_inner_sum = sec_max_sum - 1
        duration_s_sum = float(sec_max_inner_sum - sec_min_inner_sum + 1)
        duration_min_sum = duration_s_sum / 60.0 if duration_s_sum > 0 else duration_min
        area_cm2_sum = 900.0
        if "X_gen" in df.columns and "Y_gen" in df.columns:
            x_sum = x_all[mask_sum & np.isfinite(x_all)]
            y_sum = y_all[mask_sum & np.isfinite(y_all)]
            if x_sum.size >= 2 and y_sum.size >= 2:
                area_mm2_sum = float(np.max(x_sum) - np.min(x_sum)) * float(np.max(y_sum) - np.min(y_sum))
                if area_mm2_sum > 0.0:
                    area_cm2_sum = area_mm2_sum / 100.0
        counts_sum = np.zeros_like(counts_valid)
        for lbl in sum_labels:
            counts_sum = counts_sum + category_traces[lbl]["counts"]
        flux_sum = counts_sum / (duration_min_sum * area_cm2_sum * delta_omega_valid)
        flux_sum_err = np.sqrt(counts_sum) / (duration_min_sum * area_cm2_sum * delta_omega_valid)
        ax_top.plot(theta_deg, flux_sum, color="magenta", linewidth=3.0, linestyle="-", label=f"Sum (tt>10): {', '.join(sum_labels)}")
        print(f"[DIAG] Sum (tt>10): N_events={int(counts_sum.sum())}, area_cm2={area_cm2_sum:.3f}, duration_min={duration_min_sum:.3f}")
        # Overlay sum on top of overall for debugging
        ax_top.plot(theta_deg, dndt_dadomega, color="gray", linewidth=1.0, linestyle=":", label="Overall (debug)")

    # --- also add per-category cumulative traces on the bottom panel ---
    for tt_label, tr in category_traces.items():
        cum_tt = np.cumsum(tr["flux"] * delta_omega_valid)
        ax_bottom.plot(tr["theta_deg"], cum_tt, color=tr["color"], linewidth=1.1, linestyle="--")
    if sum_labels:
        cum_sum = np.cumsum(flux_sum * delta_omega_valid)
        ax_bottom.plot(theta_deg, cum_sum, color="black", linewidth=2.0, linestyle="-")


    # theoretical model (I0 derived from param_mesh when available)
    try:
        param_path = Path(__file__).resolve().parents[3] / "INTERSTEPS" / "STEP_0_TO_1" / "param_mesh.csv"
        cos_n = 2.0
        flux_F = None
        if param_path.exists():
            pm = pd.read_csv(param_path)
            step1_id = None
            # attempt to extract step_1_id from provided sample metadata if present
            def _walk_for_step1_id(p: Path | None) -> str | None:
                while p is not None:
                    try:
                        j = json.loads(p.read_text()) if p.name.endswith('.chunks.json') else None
                        m = j.get('metadata', {}) if j else {}
                    except Exception:
                        m = {}
                    cfg = m.get('config', {}) if isinstance(m, dict) else {}
                    if 'step_1_id' in cfg:
                        return str(cfg.get('step_1_id'))
                    if 'step_1_id' in m:
                        return str(m.get('step_1_id'))
                    src = m.get('source_dataset')
                    p = Path(src) if src else None
                return None
            # ...existing code...
            if sample_path is not None:
                step1_id = _walk_for_step1_id(sample_path)
            rows = pm[pm['step_1_id'].astype(str) == str(step1_id)] if step1_id is not None else pm
            if not rows.empty:
                row = rows.iloc[0]
                cos_n = float(row.get('cos_n', 2.0))
                flux_F = float(row.get('flux_cm2_min', float('nan')))
        if flux_F is None or not np.isfinite(flux_F):
            flux_F = 0.4781
        n_fixed = float(cos_n)
        # interpret flux_F as total integrated flux over solid angle: I0 = flux*(n+1)/(2π)
        i0_fixed = float(flux_F * (n_fixed + 1.0) / (2.0 * math.pi))
    except Exception:
        n_fixed = 2.0
        i0_fixed = 0.4781

    theta_curve = np.linspace(0.0, np.pi / 2.0 - 1e-4, 400)
    cos_curve = np.clip(np.cos(theta_curve), 1e-12, 1.0)
    model_curve = i0_fixed * np.power(cos_curve, n_fixed)
    fit_label = (
        r"Theory: $I(\theta)=I_0\cdot\cos^{n}(\theta)$"
        + "\n"
        + rf"$I_0={i0_fixed:.4g}$ min$^{{-1}}$ cm$^{{-2}}$ sr$^{{-1}}$, $n={n_fixed:.2f}$"
    )
    ax_top.plot(np.degrees(theta_curve), model_curve, color="crimson", linewidth=1.6, label=fit_label)

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

    # dashed horizontal y-line for flux parameter (if available)
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

    # model cumulative for the legend/overlay
    cum_model = (
        2.0 * np.pi * i0_fixed / (n_fixed + 1.0) * (1.0 - np.power(np.clip(np.cos(theta_curve), 0.0, 1.0), n_fixed + 1.0))
    )
    ax_bottom.plot(np.degrees(theta_curve), cum_model, color="crimson", linewidth=1.5, label="Model cumulative from I0*cos^n(theta)")

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

# helpers to find/load a chunk from INTERSTEPS ---------------------------------


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
        try:
            return pd.read_pickle(path)
        except Exception:
            with open(path, "rb") as fh:
                return pickle.load(fh)
    raise ValueError("Unsupported chunk type")


def main() -> None:
    step = 2
    sample = find_any_chunk_for_step(step)
    if sample is None:
        print("No sample chunk found for STEP 2; exiting.")
        return
    print(f"Using sample: {sample}")
    df = load_df(sample)
    out_dir = Path(__file__).resolve().parent / "PLOTS"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"step_{step}_sample_plots.pdf"
    with PdfPages(out_path) as pdf:
        plot_geometry_summary(df, pdf, title=sample.stem)
        plot_step2_summary(df, pdf)
        # add STEP-10 style muon differential flux plot (pasted locally so it's identical)
        added = plot_muon_differential_flux_vs_angle(df, pdf, sample_path=sample)
        if not added:
            print('Step 2 plots: skipped muon differential flux plot (missing gen/time columns).')
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
