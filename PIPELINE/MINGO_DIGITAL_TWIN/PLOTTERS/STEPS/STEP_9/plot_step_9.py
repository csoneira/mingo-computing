#!/usr/bin/env python3

"""Plots for STEP 9 — adapted from MASTER_STEPS/STEP_9/step_9_threshold_to_trigger.py."""

from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


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


def plot_trigger_summary(df: pd.DataFrame, output_path: Path) -> None:
    with PdfPages(output_path) as pdf:
        fig, ax = plt.subplots(figsize=(8, 6))
        if "tt_trigger" in df.columns:
            counts = df["tt_trigger"].astype("string").fillna("").value_counts().sort_index()
            bars = ax.bar(counts.index, counts.values, color="steelblue", alpha=0.8)
            for patch in bars:
                patch.set_rasterized(True)
        ax.set_title("tt_trigger counts")
        ax.set_xlabel("tt_trigger")
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
                    vals = vals[(~np.isnan(vals)) & (vals != 0)]
                    ax.hist(vals, bins=80, color="steelblue", alpha=0.6)
                if tb_col in df.columns:
                    vals = df[tb_col].to_numpy(dtype=float)
                    vals = vals[(~np.isnan(vals)) & (vals != 0)]
                    ax.hist(vals, bins=80, color="darkorange", alpha=0.6)
                ax.set_title(f"P{plane_idx} S{strip_idx}")
                ax.set_xlabel("time (ns)")
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

        plot_frontback_asymmetry_diagnostics(df, pdf, stage_label="STEP 9")

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
                    ax.hist(vals, bins=80, color="steelblue", alpha=0.6)
                if qb_col in df.columns:
                    vals = df[qb_col].to_numpy(dtype=float)
                    vals = vals[vals != 0]
                    ax.hist(vals, bins=80, color="darkorange", alpha=0.6)
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
        return pd.read_pickle(path)
    raise ValueError("Unsupported chunk type")


def main() -> None:
    step = 9
    sample = find_any_chunk_for_step(step)
    if sample is None:
        print("No sample chunk found for STEP 9; exiting.")
        return
    print(f"Using sample: {sample}")
    df = load_df(sample)
    out_dir = Path(__file__).resolve().parent / "PLOTS"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"step_{step}_sample_plots.pdf"
    plot_trigger_summary(df, out_path)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
