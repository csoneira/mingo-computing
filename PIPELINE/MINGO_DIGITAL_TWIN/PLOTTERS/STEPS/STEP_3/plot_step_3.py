#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/STEPS/STEP_3/plot_step_3.py
Purpose: Plots for STEP 3 — adapted from MASTER_STEPS/STEP_3/step_3_crossing_to_hit.py.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/STEPS/STEP_3/plot_step_3.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

from pathlib import Path
import json
import pickle

import numpy as np
import pandas as pd
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def normalize_tt_series(series: pd.Series) -> pd.Series:
    """Normalize tt-style series to string-like tokens (copied from MASTER_STEP_3).

    Converts numeric-like values to strings, strips trailing ".0", and maps
    '0', '0.0', 'nan', '<NA>' to empty string so value_counts() behaves.
    """
    tt = series.astype("string").fillna("")
    tt = tt.str.strip()
    tt = tt.str.replace(r"\.0$", "", regex=True)
    tt = tt.replace({"0": "", "0.0": "", "nan": "", "<NA>": ""})
    return tt


def _theta_column(df: pd.DataFrame) -> str | None:
    for col in ("Theta_gen", "theta", "theta_rad"):
        if col in df.columns:
            return col
    return None


def plot_theta_efficiency(df: pd.DataFrame, pdf: PdfPages, n_bins: int = 10) -> None:
    theta_col = _theta_column(df)
    if theta_col is None or "tt_avalanche" not in df.columns:
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.axis("off")
        ax.text(
            0.5,
            0.5,
            "Theta-binned efficiency skipped (missing Theta_gen/theta or tt_avalanche).",
            ha="center",
            va="center",
            fontsize=11,
        )
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)
        return

    theta = df[theta_col].to_numpy(dtype=float)
    tt = normalize_tt_series(df["tt_avalanche"]).fillna("").astype(str).to_numpy()
    valid = np.isfinite(theta) & (tt != "")
    if not valid.any():
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.axis("off")
        ax.text(
            0.5,
            0.5,
            "Theta-binned efficiency skipped (no valid events with theta and tt_avalanche).",
            ha="center",
            va="center",
            fontsize=11,
        )
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)
        return

    theta_vals = theta[valid]
    tt_vals = tt[valid]
    theta_edges = np.linspace(0.0, np.pi / 2.0, int(n_bins) + 1)
    bin_idx = np.digitize(theta_vals, theta_edges, right=False) - 1
    in_range = (bin_idx >= 0) & (bin_idx < n_bins)
    bin_idx = bin_idx[in_range]
    tt_vals = tt_vals[in_range]

    n1234 = np.zeros(n_bins, dtype=int)
    n134 = np.zeros(n_bins, dtype=int)
    n124 = np.zeros(n_bins, dtype=int)
    for b in range(n_bins):
        in_bin = bin_idx == b
        if not in_bin.any():
            continue
        tt_bin = tt_vals[in_bin]
        n1234[b] = int(np.sum(tt_bin == "1234"))
        n134[b] = int(np.sum(tt_bin == "134"))
        n124[b] = int(np.sum(tt_bin == "124"))

    eff2 = np.full(n_bins, np.nan, dtype=float)
    eff3 = np.full(n_bins, np.nan, dtype=float)
    ok = n1234 > 0
    eff2[ok] = 1.0 - (n134[ok] / n1234[ok])
    eff3[ok] = 1.0 - (n124[ok] / n1234[ok])
    sigma_eff2 = np.full(n_bins, np.nan, dtype=float)
    sigma_eff3 = np.full(n_bins, np.nan, dtype=float)
    if ok.any():
        den = n1234[ok].astype(float)
        den_sigma = np.sqrt(np.maximum(den, 1.0))

        num2 = n134[ok].astype(float)
        num2_sigma = np.sqrt(np.maximum(num2, 1.0))
        sigma_eff2[ok] = np.sqrt((num2_sigma / den) ** 2 + ((num2 * den_sigma) / (den ** 2)) ** 2)

        num3 = n124[ok].astype(float)
        num3_sigma = np.sqrt(np.maximum(num3, 1.0))
        sigma_eff3[ok] = np.sqrt((num3_sigma / den) ** 2 + ((num3 * den_sigma) / (den ** 2)) ** 2)

    eff2_lo = np.clip(eff2 - sigma_eff2, 0.0, 1.05)
    eff2_hi = np.clip(eff2 + sigma_eff2, 0.0, 1.05)
    eff3_lo = np.clip(eff3 - sigma_eff3, 0.0, 1.05)
    eff3_hi = np.clip(eff3 + sigma_eff3, 0.0, 1.05)

    theta_centers_deg = np.degrees(0.5 * (theta_edges[:-1] + theta_edges[1:]))
    theta_edges_deg = np.degrees(theta_edges)
    width = 0.38 * (theta_edges_deg[1] - theta_edges_deg[0])

    fig, axes = plt.subplots(2, 1, figsize=(10, 10), sharex=True)

    ax2 = axes[0]
    ax2.bar(theta_centers_deg - width / 2.0, n1234, width=width, color="tab:blue", alpha=0.70, label="N1234")
    ax2.bar(theta_centers_deg + width / 2.0, n134, width=width, color="tab:orange", alpha=0.70, label="N134")
    ax2.set_ylabel("Counts")
    ax2.set_title("eff2(theta) = 1 - N134/N1234")
    ax2.grid(alpha=0.20)
    ax2_eff = ax2.twinx()
    ax2_eff.fill_between(
        theta_centers_deg,
        eff2_lo,
        eff2_hi,
        color="tab:red",
        alpha=0.20,
        linewidth=0,
        label="eff2 ±1σ (Poisson)",
    )
    ax2_eff.axhline(1.0, color="gray", linestyle="--", alpha=0.5, linewidth=1.2, label="eff=1 reference")
    ax2_eff.plot(theta_centers_deg, eff2, color="tab:red", marker="o", label="eff2")
    ax2_eff.set_ylabel("eff2")
    ax2_eff.set_ylim(0.5, 1.05)
    h1, l1 = ax2.get_legend_handles_labels()
    h2, l2 = ax2_eff.get_legend_handles_labels()
    ax2.legend(h1 + h2, l1 + l2, loc="upper right")

    ax3 = axes[1]
    ax3.bar(theta_centers_deg - width / 2.0, n1234, width=width, color="tab:blue", alpha=0.70, label="N1234")
    ax3.bar(theta_centers_deg + width / 2.0, n124, width=width, color="tab:green", alpha=0.70, label="N124")
    ax3.set_ylabel("Counts")
    ax3.set_xlabel("Theta (deg)")
    ax3.set_title("eff3(theta) = 1 - N124/N1234")
    ax3.grid(alpha=0.20)
    ax3_eff = ax3.twinx()
    ax3_eff.fill_between(
        theta_centers_deg,
        eff3_lo,
        eff3_hi,
        color="tab:red",
        alpha=0.20,
        linewidth=0,
        label="eff3 ±1σ (Poisson)",
    )
    ax3_eff.axhline(1.0, color="gray", linestyle="--", alpha=0.5, linewidth=1.2, label="eff=1 reference")
    ax3_eff.plot(theta_centers_deg, eff3, color="tab:red", marker="o", label="eff3")
    ax3_eff.set_ylabel("eff3")
    ax3_eff.set_ylim(0.5, 1.05)
    h1, l1 = ax3.get_legend_handles_labels()
    h2, l2 = ax3_eff.get_legend_handles_labels()
    ax3.legend(h1 + h2, l1 + l2, loc="upper right")

    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def plot_avalanche_gain_publication(df: pd.DataFrame, pdf: PdfPages) -> None:
    """Publication-style diagnostics for avalanche gain and per-plane efficiency."""
    theta_col = _theta_column(df)

    # 1) Gain spectrum: log10(avalanche_size / avalanche_ion)
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 8.5), sharex=True, sharey=True)
    drew_gain = False
    for plane_idx, ax in enumerate(axes.flatten(), start=1):
        size_col = f"avalanche_size_electrons_{plane_idx}"
        ion_col = f"avalanche_ion_{plane_idx}"
        if size_col not in df.columns or ion_col not in df.columns:
            ax.axis("off")
            continue
        size_vals = df[size_col].to_numpy(dtype=float)
        ion_vals = df[ion_col].to_numpy(dtype=float)
        mask = np.isfinite(size_vals) & np.isfinite(ion_vals) & (size_vals > 0.0) & (ion_vals > 0.0)
        if not np.any(mask):
            ax.axis("off")
            continue
        gain = size_vals[mask] / ion_vals[mask]
        gain = gain[gain > 0.0]
        if gain.size == 0:
            ax.axis("off")
            continue
        lg = np.log10(gain)
        lo, hi = np.quantile(lg, [0.01, 0.99])
        if not np.isfinite(lo) or not np.isfinite(hi) or lo >= hi:
            lo, hi = float(np.min(lg)), float(np.max(lg))
        ax.hist(lg, bins=90, range=(lo, hi), color="tab:purple", alpha=0.8)
        med = float(np.median(lg))
        ax.axvline(med, color="black", linestyle="--", linewidth=1.0)
        ax.set_title(f"Plane {plane_idx}: log10(gain)")
        ax.set_xlabel(r"$\log_{10}(N_e / N_{ion})$")
        ax.set_ylabel("Counts")
        ax.text(
            0.03,
            0.95,
            f"N={lg.size}\nmedian={med:.3f}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "alpha": 0.75, "edgecolor": "none"},
        )
        drew_gain = True
    if drew_gain:
        fig.suptitle("STEP 3 avalanche gain spectra by plane")
        fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
        pdf.savefig(fig, dpi=150)
    plt.close(fig)

    # 2) Gain vs theta (median + 16–84% band)
    if theta_col is not None:
        theta_vals_all = df[theta_col].to_numpy(dtype=float)
        theta_edges = np.linspace(0.0, np.pi / 2.0, 13)
        theta_centers_deg = np.degrees(0.5 * (theta_edges[1:] + theta_edges[:-1]))
        fig, ax = plt.subplots(figsize=(9.5, 5.5))
        drew_curve = False
        cmap = plt.get_cmap("tab10")
        for plane_idx in range(1, 5):
            size_col = f"avalanche_size_electrons_{plane_idx}"
            ion_col = f"avalanche_ion_{plane_idx}"
            if size_col not in df.columns or ion_col not in df.columns:
                continue
            size_vals = df[size_col].to_numpy(dtype=float)
            ion_vals = df[ion_col].to_numpy(dtype=float)
            valid = (
                np.isfinite(theta_vals_all)
                & np.isfinite(size_vals)
                & np.isfinite(ion_vals)
                & (size_vals > 0.0)
                & (ion_vals > 0.0)
                & (theta_vals_all >= 0.0)
                & (theta_vals_all <= np.pi / 2.0)
            )
            if not np.any(valid):
                continue
            theta = theta_vals_all[valid]
            gain = size_vals[valid] / ion_vals[valid]
            lg = np.log10(gain[gain > 0.0])
            theta = theta[gain > 0.0]
            if lg.size == 0:
                continue
            med = np.full(theta_centers_deg.size, np.nan, dtype=float)
            lo = np.full(theta_centers_deg.size, np.nan, dtype=float)
            hi = np.full(theta_centers_deg.size, np.nan, dtype=float)
            for b in range(theta_centers_deg.size):
                in_bin = (theta >= theta_edges[b]) & (theta < theta_edges[b + 1])
                if np.count_nonzero(in_bin) < 20:
                    continue
                vals = lg[in_bin]
                med[b] = float(np.median(vals))
                lo[b] = float(np.quantile(vals, 0.16))
                hi[b] = float(np.quantile(vals, 0.84))
            ok = np.isfinite(med)
            if not np.any(ok):
                continue
            color = cmap((plane_idx - 1) % cmap.N)
            ax.plot(theta_centers_deg[ok], med[ok], color=color, linewidth=1.8, marker="o", label=f"Plane {plane_idx}")
            ax.fill_between(theta_centers_deg[ok], lo[ok], hi[ok], color=color, alpha=0.2)
            drew_curve = True
        if drew_curve:
            ax.set_title("STEP 3 avalanche gain vs zenith angle")
            ax.set_xlabel("Theta (deg)")
            ax.set_ylabel(r"$\log_{10}(N_e / N_{ion})$")
            ax.grid(alpha=0.3)
            ax.legend(loc="best")
            fig.tight_layout()
            pdf.savefig(fig, dpi=150)
        plt.close(fig)

    # 3) Per-plane avalanche probability vs theta
    if theta_col is not None:
        theta_vals_all = df[theta_col].to_numpy(dtype=float)
        theta_edges = np.linspace(0.0, np.pi / 2.0, 13)
        theta_centers_deg = np.degrees(0.5 * (theta_edges[1:] + theta_edges[:-1]))
        fig, ax = plt.subplots(figsize=(9.5, 5.5))
        drew_eff = False
        cmap = plt.get_cmap("tab10")
        for plane_idx in range(1, 5):
            exists_col = f"avalanche_exists_{plane_idx}"
            if exists_col not in df.columns:
                continue
            exists_vals = df[exists_col].to_numpy(dtype=float)
            valid = np.isfinite(theta_vals_all) & np.isfinite(exists_vals) & (theta_vals_all >= 0.0) & (theta_vals_all <= np.pi / 2.0)
            if not np.any(valid):
                continue
            theta = theta_vals_all[valid]
            exists = exists_vals[valid] > 0.0
            eff = np.full(theta_centers_deg.size, np.nan, dtype=float)
            eff_err = np.full(theta_centers_deg.size, np.nan, dtype=float)
            for b in range(theta_centers_deg.size):
                in_bin = (theta >= theta_edges[b]) & (theta < theta_edges[b + 1])
                n = int(np.count_nonzero(in_bin))
                if n < 20:
                    continue
                k = int(np.count_nonzero(exists[in_bin]))
                p = k / n
                eff[b] = p
                eff_err[b] = math.sqrt(max(p * (1.0 - p) / n, 0.0))
            ok = np.isfinite(eff) & np.isfinite(eff_err)
            if not np.any(ok):
                continue
            color = cmap((plane_idx - 1) % cmap.N)
            ax.errorbar(
                theta_centers_deg[ok],
                eff[ok],
                yerr=eff_err[ok],
                fmt="o-",
                color=color,
                capsize=2,
                linewidth=1.4,
                markersize=4,
                label=f"Plane {plane_idx}",
            )
            drew_eff = True
        if drew_eff:
            ax.set_title("STEP 3 avalanche probability vs zenith angle")
            ax.set_xlabel("Theta (deg)")
            ax.set_ylabel("P(avalanche exists)")
            ax.set_ylim(0.0, 1.05)
            ax.grid(alpha=0.3)
            ax.legend(loc="best")
            fig.tight_layout()
            pdf.savefig(fig, dpi=150)
        plt.close(fig)


def plot_avalanche_summary(df: pd.DataFrame, pdf: PdfPages) -> None:
    # tt_avalanche counts
    fig, ax = plt.subplots(figsize=(8, 6))
    counts = normalize_tt_series(df.get("tt_avalanche", pd.Series(dtype="string"))).value_counts().sort_index()
    bars = ax.bar(counts.index.astype(str), counts.values, color="steelblue", alpha=0.8)
    for patch in bars:
        patch.set_rasterized(True)
    ax.set_title("tt_avalanche counts")
    ax.set_xlabel("tt_avalanche")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    # Avalanche size per plane (log scale)
    fig, axes = plt.subplots(2, 2, figsize=(10, 8), sharex=True, sharey=True)
    for plane_idx, ax in enumerate(axes.flatten(), start=1):
        col = f"avalanche_size_electrons_{plane_idx}"
        if col not in df.columns:
            ax.axis("off")
            continue
        vals = df[col].to_numpy(dtype=float)
        vals = vals[vals > 0]
        ax.hist(vals, bins=120, color="darkorange", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} avalanche size")
        ax.set_xlim(left=0)
        ax.set_yscale("log")
        for patch in ax.patches:
            patch.set_rasterized(True)
    fig.suptitle("Avalanche size per plane (log scale)")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    # Ionizations per plane (log scale)
    fig, axes = plt.subplots(2, 2, figsize=(10, 8), sharex=True, sharey=True)
    for plane_idx, ax in enumerate(axes.flatten(), start=1):
        col = f"avalanche_ion_{plane_idx}"
        if col not in df.columns:
            ax.axis("off")
            continue
        vals = df[col].to_numpy(dtype=float)
        vals = vals[vals > 0]
        ax.hist(vals, bins=80, color="slateblue", alpha=0.8)
        ax.set_title(f"Plane {plane_idx} avalanche_ion")
        ax.set_xlim(left=0)
        ax.set_yscale("log")
        for patch in ax.patches:
            patch.set_rasterized(True)
    fig.suptitle("Ionizations per plane (log scale)")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    # Avalanche center positions (2D density)
    fig, axes = plt.subplots(2, 2, figsize=(10, 8), sharex=True, sharey=True)
    for plane_idx, ax in enumerate(axes.flatten(), start=1):
        x_col = f"avalanche_x_{plane_idx}"
        y_col = f"avalanche_y_{plane_idx}"
        if x_col not in df.columns or y_col not in df.columns:
            ax.axis("off")
            continue
        x_vals = df[x_col].to_numpy(dtype=float)
        y_vals = df[y_col].to_numpy(dtype=float)
        mask = ~np.isnan(x_vals) & ~np.isnan(y_vals)
        ax.hist2d(x_vals[mask], y_vals[mask], bins=60, cmap="viridis")
        ax.set_title(f"Plane {plane_idx} avalanche center")
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
    fig.suptitle("Avalanche center positions")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    # Avalanche size vs ionizations scatter
    fig, axes = plt.subplots(2, 2, figsize=(10, 8), sharex=True, sharey=True)
    for plane_idx, ax in enumerate(axes.flatten(), start=1):
        size_col = f"avalanche_size_electrons_{plane_idx}"
        ion_col = f"avalanche_ion_{plane_idx}"
        if size_col not in df.columns or ion_col not in df.columns:
            ax.axis("off")
            continue
        size_vals = df[size_col].to_numpy(dtype=float)
        ion_vals = df[ion_col].to_numpy(dtype=float)
        mask = (size_vals > 0) & (ion_vals > 0)
        ax.scatter(ion_vals[mask], size_vals[mask], s=2, alpha=0.2, rasterized=True)
        ax.set_title(f"Plane {plane_idx} size vs ion")
        ax.set_xlabel("ionizations")
        ax.set_ylabel("avalanche size")
        ax.set_xscale("linear")
        ax.set_yscale("linear")
    fig.suptitle("Avalanche size vs ionizations")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    # Publication-level avalanche diagnostics.
    plot_avalanche_gain_publication(df, pdf)

    # Angular behavior diagnostic from tt_avalanche multiplicity.
    plot_theta_efficiency(df, pdf, n_bins=10)

def find_any_chunk_for_step(step: int) -> Path | None:
    root = Path(__file__).resolve().parents[3] / "INTERSTEPS"
    parts = sorted(root.glob(f"**/step_{step}_chunks/part_*.pkl"))
    if parts:
        return parts[0]
    manifests = sorted(root.rglob(f"*step_{step}_chunks.chunks.json"))
    if manifests:
        try:
            j = json.loads(manifests[0].read_text())
            parts_list = [p for p in (j.get("parts") or j.get("chunks") or []) if str(p).endswith(".pkl")]
            if parts_list:
                return Path(parts_list[0])
        except Exception:
            return manifests[0]
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
        try:
            return pd.read_pickle(path)
        except Exception:
            with open(path, "rb") as fh:
                import pickle
                return pickle.load(fh)
    raise ValueError("Unsupported chunk type")


def main() -> None:
    step = 3
    sample = find_any_chunk_for_step(step)
    if sample is None:
        print("No sample chunk found for STEP 3; exiting.")
        return
    print(f"Using sample: {sample}")
    df = load_df(sample)
    out_dir = Path(__file__).resolve().parent / "PLOTS"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"step_{step}_sample_plots.pdf"
    with PdfPages(out_path) as pdf:
        plot_avalanche_summary(df, pdf)

        # muon differential flux plot moved to STEP_8 — removed from STEP_3 to avoid duplication

        # combined comparison: STEP 1, 2, 3, 10 (centralized implementation)
        try:
            from COMMON.ANGULAR_FLUX.angular_flux import plot_muon_flux_tt_comparison
        except Exception:
            plot_muon_flux_tt_comparison = None
        if plot_muon_flux_tt_comparison:
            plot_muon_flux_tt_comparison(pdf, sample_path=sample)

    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
