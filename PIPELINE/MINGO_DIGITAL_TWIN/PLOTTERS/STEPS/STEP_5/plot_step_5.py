#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/STEPS/STEP_5/plot_step_5.py
Purpose: Plots for STEP 5 — adapted from MASTER_STEPS/STEP_5/step_5_measured_to_triggered.py.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/STEPS/STEP_5/plot_step_5.py [options]
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
from matplotlib.backends.backend_pdf import PdfPages


def pick_tt_column(df: pd.DataFrame) -> str | None:
    """Return the first tt-* column present in dataframe (if any)."""
    for col in ("tt_trigger", "tt_hit", "tt_avalanche", "tt_crossing"):
        if col in df.columns:
            return col
    return None


def plot_qdiff_tdiff_correlation(df: pd.DataFrame, pdf: PdfPages) -> None:
    """Plane-wise q_diff vs T_diff maps for time-walk style diagnostics."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    drew_any = False
    for plane_idx in range(1, 5):
        ax = axes[(plane_idx - 1) // 2, (plane_idx - 1) % 2]
        q_parts: list[np.ndarray] = []
        t_parts: list[np.ndarray] = []
        for strip_idx in range(1, 5):
            q_col = f"q_diff_{plane_idx}_s{strip_idx}"
            t_col = f"T_diff_{plane_idx}_s{strip_idx}"
            if q_col not in df.columns or t_col not in df.columns:
                continue
            q_vals = df[q_col].to_numpy(dtype=float)
            t_vals = df[t_col].to_numpy(dtype=float)
            mask = np.isfinite(q_vals) & np.isfinite(t_vals) & (q_vals != 0.0)
            if np.any(mask):
                q_parts.append(q_vals[mask])
                t_parts.append(t_vals[mask])
        if not q_parts:
            ax.axis("off")
            continue
        q_all = np.concatenate(q_parts)
        t_all = np.concatenate(t_parts)
        if q_all.size < 50:
            ax.axis("off")
            continue
        q_lo, q_hi = np.quantile(q_all, [0.01, 0.99])
        t_lo, t_hi = np.quantile(t_all, [0.01, 0.99])
        if not np.isfinite(q_lo) or not np.isfinite(q_hi) or q_lo >= q_hi:
            q_lo, q_hi = float(np.min(q_all)), float(np.max(q_all))
        if not np.isfinite(t_lo) or not np.isfinite(t_hi) or t_lo >= t_hi:
            t_lo, t_hi = float(np.min(t_all)), float(np.max(t_all))
        hb = ax.hexbin(
            q_all,
            t_all,
            gridsize=60,
            bins="log",
            cmap="viridis",
            extent=(q_lo, q_hi, t_lo, t_hi),
            mincnt=1,
        )
        corr = float(np.corrcoef(q_all, t_all)[0, 1]) if q_all.size > 1 else float("nan")
        ax.set_title(f"Plane {plane_idx}: q_diff vs T_diff")
        ax.set_xlabel("q_diff")
        ax.set_ylabel("T_diff (ns)")
        ax.text(
            0.03,
            0.95,
            f"N={q_all.size}\nr={corr:.3f}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
        )
        fig.colorbar(hb, ax=ax, label="log10(counts)")
        drew_any = True
    if drew_any:
        fig.suptitle("STEP 5 charge-time correlation maps by plane")
        fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.97))
        pdf.savefig(fig, dpi=150)
    plt.close(fig)


def plot_signal_summary(df: pd.DataFrame, output_path: Path, sample_path: Path | None = None) -> None:
    with PdfPages(output_path) as pdf:
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

        # Top-level summaries
        fig, axes = plt.subplots(2, 2, figsize=(12, 9))
        axes = axes.flatten()

        qsum_cols = [c for c in df.columns if c.startswith("Y_mea_") and "_s" in c]
        qsum_vals = df[qsum_cols].to_numpy(dtype=float).ravel() if qsum_cols else np.array([])
        qsum_vals = qsum_vals[qsum_vals > 0]
        axes[0].hist(qsum_vals, bins=60, color="steelblue", alpha=0.8)
        axes[0].set_title("qsum (all strips)")
        axes[0].set_xlabel("qsum")

        qdiff_cols = [c for c in df.columns if c.startswith("q_diff_")]
        qdiff_vals = df[qdiff_cols].to_numpy(dtype=float).ravel() if qdiff_cols else np.array([])
        qdiff_vals = qdiff_vals[qdiff_vals != 0]
        axes[1].hist(qdiff_vals, bins=60, color="seagreen", alpha=0.8)
        axes[1].set_title("q_diff (all strips)")
        axes[1].set_xlabel("q_diff")

        tdiff_cols = [c for c in df.columns if c.startswith("T_diff_")]
        tdiff_vals = df[tdiff_cols].to_numpy(dtype=float).ravel() if tdiff_cols else np.array([])
        tdiff_vals = tdiff_vals[~np.isnan(tdiff_vals)]
        axes[2].hist(tdiff_vals, bins=60, color="darkorange", alpha=0.8)
        axes[2].set_title("T_diff (all strips)")
        axes[2].set_xlabel("T_diff (ns)")

        tsum_cols = [c for c in df.columns if c.startswith("T_sum_meas_")]
        tsum_vals = df[tsum_cols].to_numpy(dtype=float).ravel() if tsum_cols else np.array([])
        tsum_vals = tsum_vals[~np.isnan(tsum_vals)]
        axes[3].hist(tsum_vals, bins=60, color="slateblue", alpha=0.8)
        axes[3].set_title("T_sum_meas (all strips)")
        axes[3].set_xlabel("T_sum_meas (ns)")

        for ax in axes:
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

        # 4x4 grids for T_diff per plane/strip
        fig, axes = plt.subplots(4, 4, figsize=(12, 10))
        for plane_idx in range(1, 5):
            for strip_idx in range(1, 5):
                ax = axes[plane_idx - 1, strip_idx - 1]
                col = f"T_diff_{plane_idx}_s{strip_idx}"
                if col not in df.columns:
                    ax.axis("off")
                    continue
                vals = df[col].to_numpy(dtype=float)
                vals = vals[~np.isnan(vals)]
                ax.hist(vals, bins=80, color="darkorange", alpha=0.8)
                ax.set_title(f"P{plane_idx} S{strip_idx}")
                ax.set_xlabel("T_diff (ns)")
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

        # 4x4 grids for T_sum_meas per plane/strip
        fig, axes = plt.subplots(4, 4, figsize=(12, 10))
        for plane_idx in range(1, 5):
            for strip_idx in range(1, 5):
                ax = axes[plane_idx - 1, strip_idx - 1]
                col = f"T_sum_meas_{plane_idx}_s{strip_idx}"
                if col not in df.columns:
                    ax.axis("off")
                    continue
                vals = df[col].to_numpy(dtype=float)
                vals = vals[~np.isnan(vals)]
                ax.hist(vals, bins=80, color="slateblue", alpha=0.8)
                ax.set_title(f"P{plane_idx} S{strip_idx}")
                ax.set_xlabel("T_sum_meas (ns)")
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

        # 4x4 grids for Y_mea (qsum) per plane/strip
        fig, axes = plt.subplots(4, 4, figsize=(12, 10))
        for plane_idx in range(1, 5):
            for strip_idx in range(1, 5):
                ax = axes[plane_idx - 1, strip_idx - 1]
                col = f"Y_mea_{plane_idx}_s{strip_idx}"
                if col not in df.columns:
                    ax.axis("off")
                    continue
                vals = df[col].to_numpy(dtype=float)
                vals = vals[vals > 0]
                ax.hist(vals, bins=80, color="seagreen", alpha=0.8)
                ax.set_title(f"P{plane_idx} S{strip_idx}")
                ax.set_xlabel("qsum")
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

        # 4x4 grids for q_diff per plane/strip
        fig, axes = plt.subplots(4, 4, figsize=(12, 10))
        for plane_idx in range(1, 5):
            for strip_idx in range(1, 5):
                ax = axes[plane_idx - 1, strip_idx - 1]
                col = f"q_diff_{plane_idx}_s{strip_idx}"
                if col not in df.columns:
                    ax.axis("off")
                    continue
                vals = df[col].to_numpy(dtype=float)
                vals = vals[vals != 0]
                ax.hist(vals, bins=80, color="steelblue", alpha=0.8)
                ax.set_title(f"P{plane_idx} S{strip_idx}")
                ax.set_xlabel("q_diff")
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

        # Publication-focused time-walk view.
        plot_qdiff_tdiff_correlation(df, pdf)

        # muon differential flux plot intentionally omitted from STEP 5 (use STEP_1/STEP_10 for generator/trigger diagnostics).

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


# muon differential flux plotting removed from STEP_5 — see STEP_1 / STEP_10 for canonical implementation
# (function intentionally deleted to avoid duplication and keep STEP_5 focused on measured/trigger diagnostics)


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


def main() -> None:
    step = 5
    sample = find_any_chunk_for_step(step)
    if sample is None:
        print("No sample chunk found for STEP 5; exiting.")
        return
    print(f"Using sample: {sample}")
    df = load_df(sample)
    out_dir = Path(__file__).resolve().parent / "PLOTS"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"step_{step}_sample_plots.pdf"
    plot_signal_summary(df, out_path, sample_path=sample)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
