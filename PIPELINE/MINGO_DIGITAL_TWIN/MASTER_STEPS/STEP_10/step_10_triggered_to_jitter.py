#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_10/step_10_triggered_to_jitter.py
Purpose: Step 10: apply TDC smear and DAQ jitter to front/back times.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_10/step_10_triggered_to_jitter.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT_DIR))
sys.path.append(str(ROOT_DIR / "MASTER_STEPS"))

from STEP_SHARED.sim_utils import (
    ensure_dir,
    find_latest_data_path,
    find_sim_run,
    find_sim_run_dir,
    iter_input_frames,
    latest_sim_run,
    random_sim_run,
    load_step_configs,
    load_with_metadata,
    now_iso,
    build_sim_run_name,
    register_sim_run,
    extract_step_id_chain,
    select_next_step_id,
    resolve_sim_run,
    reset_dir,
    save_with_metadata,
    write_chunked_output,
)


def apply_jitter(
    df: pd.DataFrame,
    jitter_width_ns: float,
    tdc_sigma_ns: float,
    rng: np.random.Generator,
) -> pd.DataFrame:
    out = df.copy()
    n = len(out)
    jitter = rng.uniform(-jitter_width_ns / 2, jitter_width_ns / 2, size=n)

    active_mask = np.zeros(n, dtype=bool)
    for plane_idx in range(1, 5):
        for strip_idx in range(1, 5):
            qf_col = f"Q_front_{plane_idx}_s{strip_idx}"
            qb_col = f"Q_back_{plane_idx}_s{strip_idx}"
            if qf_col in out.columns:
                active_mask |= out[qf_col].to_numpy(dtype=float) > 0
            if qb_col in out.columns:
                active_mask |= out[qb_col].to_numpy(dtype=float) > 0

    for plane_idx in range(1, 5):
        for strip_idx in range(1, 5):
            for prefix in ("T_front", "T_back"):
                col = f"{prefix}_{plane_idx}_s{strip_idx}"
                if col not in out.columns:
                    continue
                vals = out[col].to_numpy(dtype=float)
                mask = active_mask & ~np.isnan(vals)
                if tdc_sigma_ns > 0 and mask.any():
                    vals[mask] = vals[mask] + rng.normal(0.0, tdc_sigma_ns, size=mask.sum())
                vals[mask] = vals[mask] + jitter[mask]
                out[col] = vals

    out["daq_jitter_ns"] = np.where(active_mask, jitter, 0.0)
    return out


def prune_step10(df: pd.DataFrame) -> pd.DataFrame:
    keep = {
        "event_id", "T_thick_s", "X_gen", "Y_gen", "Theta_gen", "Phi_gen",
        "daq_jitter_ns", "sim_crossing_cumulative_count",
        "sim_unit_efficiency_trigger_cumulative_count",
    }
    for plane_idx in range(1, 5):
        for strip_idx in range(1, 5):
            keep.add(f"T_front_{plane_idx}_s{strip_idx}")
            keep.add(f"T_back_{plane_idx}_s{strip_idx}")
            keep.add(f"Q_front_{plane_idx}_s{strip_idx}")
            keep.add(f"Q_back_{plane_idx}_s{strip_idx}")
    keep_cols = [col for col in df.columns if col in keep]
    return df[keep_cols]


def pick_tt_column(df: pd.DataFrame) -> str | None:
    for col in ("tt_trigger", "tt_hit", "tt_avalanche", "tt_crossing"):
        if col in df.columns:
            return col
    return None


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


def plot_muon_differential_flux_vs_angle(df: pd.DataFrame, pdf: PdfPages) -> bool:
    if "Theta_gen" not in df.columns or "T_thick_s" not in df.columns:
        return False
    if "X_gen" not in df.columns or "Y_gen" not in df.columns:
        return False

    theta = df["Theta_gen"].to_numpy(dtype=float)
    theta = theta[np.isfinite(theta)]
    theta = theta[(theta >= 0.0) & (theta <= np.pi / 2.0)]
    if theta.size < 20:
        return False

    t0_s = df["T_thick_s"].to_numpy(dtype=float)
    t0_s = t0_s[np.isfinite(t0_s)]
    if t0_s.size == 0:
        return False
    sec_min = int(np.floor(np.min(t0_s)))
    sec_max = int(np.floor(np.max(t0_s)))
    duration_s = float(sec_max - sec_min + 1)
    if not np.isfinite(duration_s) or duration_s <= 0.0:
        return False

    x_vals = df["X_gen"].to_numpy(dtype=float)
    x_vals = x_vals[np.isfinite(x_vals)]
    y_vals = df["Y_gen"].to_numpy(dtype=float)
    y_vals = y_vals[np.isfinite(y_vals)]
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
                ax_top.plot(
                    np.degrees(theta_curve),
                    model_curve,
                    color="crimson",
                    linewidth=1.6,
                    label=fit_label,
                )

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
        cum_model = (
            2.0
            * np.pi
            * i0_fit_out
            / (n_fit_out + 1.0)
            * (1.0 - np.power(np.clip(np.cos(theta_curve), 0.0, 1.0), n_fit_out + 1.0))
        )
        ax_bottom.plot(
            np.degrees(theta_curve),
            cum_model,
            color="crimson",
            linewidth=1.5,
            label="Fit cumulative from I0*cos^n(theta)",
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


def load_sample_df(path: Path | None, max_rows: int, seed: int | None) -> pd.DataFrame | None:
    if path is None or path.name == "" or not path.exists():
        return None
    frames = []
    total = 0
    for df in iter_input_frames(path, None)[0]:
        if df.empty:
            continue
        frames.append(df)
        total += len(df)
        if total >= max_rows:
            break
    if not frames:
        return None
    out = pd.concat(frames, ignore_index=True)
    if len(out) > max_rows:
        out = out.sample(n=max_rows, random_state=seed)
    return out


def load_metadata(path: Path) -> dict:
    if path.name.endswith(".chunks.json"):
        return json.loads(path.read_text()).get("metadata", {})
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    return {}


def resolve_upstream_chain(start_path: Path) -> dict:
    chain = {}
    step9_path = start_path
    meta9 = load_metadata(step9_path)
    if meta9.get("step") == "STEP_10":
        src = meta9.get("source_dataset")
        if src:
            step9_path = Path(src)
    chain["step9"] = step9_path
    meta9 = load_metadata(step9_path)
    step8_path = meta9.get("source_dataset")
    if step8_path:
        chain["step8"] = Path(step8_path)
        meta8 = load_metadata(chain["step8"])
        step7_path = meta8.get("source_dataset")
        if step7_path:
            chain["step7"] = Path(step7_path)
            meta7 = load_metadata(chain["step7"])
            step6_path = meta7.get("source_dataset")
            if step6_path:
                chain["step6"] = Path(step6_path)
    return chain


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

    def collect_residual(after: pd.DataFrame, before: pd.DataFrame, offsets: list[list[float]] | None) -> np.ndarray:
        residuals = []
        for plane_idx in range(1, 5):
            for strip_idx in range(1, 5):
                for side, offset_map in (("front", offsets), ("back", offsets)):
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
                    if offset_map is not None:
                        expected = float(offset_map[plane_idx - 1][strip_idx - 1])
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
        res_front = collect_residual(df7, df6, tfront_offsets)
        res_back = collect_residual(df7, df6, tback_offsets)
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        plot_hist(axes[0], res_front, "STEP 7: T_front delta - offset")
        plot_hist(axes[1], res_back, "STEP 7: T_back delta - offset")
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

    if df8 is not None and df7 is not None:
        res_front = collect_residual(df8, df7, None)
        res_back = collect_residual(df8, df7, None)
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        plot_hist(axes[0], res_front, "STEP 8: T_front delta (FEE noise)")
        plot_hist(axes[1], res_back, "STEP 8: T_back delta (FEE noise)")
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

    if df9 is not None and df10 is not None:
        res_front = collect_residual(df10, df9, None)
        res_back = collect_residual(df10, df9, None)
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        plot_hist(axes[0], res_front, "STEP 10: T_front delta (TDC + jitter)", expected_rms=expected_tdc_rms)
        plot_hist(axes[1], res_back, "STEP 10: T_back delta (TDC + jitter)", expected_rms=expected_tdc_rms)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)


def plot_jitter_summary(
    df: pd.DataFrame,
    output_path: Path,
    rate_df: pd.DataFrame | None = None,
    closure_dfs: dict | None = None,
    cfg7: dict | None = None,
    cfg10: dict | None = None,
) -> None:
    with PdfPages(output_path) as pdf:
        if rate_df is not None:
            added = plot_rate_summary(rate_df, pdf)
            if not added:
                print("Step 10 plots: skipped rate summary (T_thick_s missing).")
            added_tt = plot_rate_by_tt(rate_df, pdf)
            if not added_tt:
                print("Step 10 plots: skipped rate-by-TT summary (T_thick_s or tt column missing).")
        added_flux = plot_muon_differential_flux_vs_angle(df, pdf)
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 10: apply DAQ jitter to T_front/T_back.")
    parser.add_argument("--config", default="config_step_10_physics.yaml", help="Path to step physics config YAML")
    parser.add_argument(
        "--runtime-config",
        default=None,
        help="Path to step runtime config YAML (defaults to *_runtime.yaml)",
    )
    parser.add_argument("--plot-only", action="store_true", help="Only generate plots from existing outputs")
    parser.add_argument("--no-plots", action="store_true", help="Skip plot generation")
    parser.add_argument("--force", action="store_true", help="Recompute even if sim_run exists")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(__file__).resolve().parent / config_path
    runtime_path = Path(args.runtime_config) if args.runtime_config else None
    if runtime_path is not None and not runtime_path.is_absolute():
        runtime_path = Path(__file__).resolve().parent / runtime_path

    physics_cfg, runtime_cfg, cfg, runtime_path = load_step_configs(config_path, runtime_path)

    input_dir = Path(cfg["input_dir"])
    if not input_dir.is_absolute():
        input_dir = Path(__file__).resolve().parent / input_dir
    output_dir = Path(cfg["output_dir"])
    if not output_dir.is_absolute():
        output_dir = Path(__file__).resolve().parent / output_dir
    ensure_dir(output_dir)

    output_format = str(cfg.get("output_format", "pkl")).lower()
    chunk_rows = cfg.get("chunk_rows")
    plot_sample_rows = cfg.get("plot_sample_rows")
    jitter_width_ns = float(cfg.get("jitter_width_ns", 10.0))
    tdc_sigma_ns = float(cfg.get("tdc_sigma_ns", 0.016))
    rng = np.random.default_rng(cfg.get("seed"))

    input_glob = cfg.get("input_glob", "**/step_9_chunks.chunks.json")
    input_sim_run = cfg.get("input_sim_run", "latest")

    print("\n-----\nStep 10 starting...\n-----")
    print(f"Input dir: {input_dir}")
    print(f"Output dir: {output_dir}")
    print(f"jitter_width_ns: {jitter_width_ns}")
    print(f"tdc_sigma_ns: {tdc_sigma_ns}")

    if args.plot_only:
        if args.no_plots:
            print("Plot-only requested with --no-plots; skipping plots.")
            return
        latest_path = find_latest_data_path(output_dir)
        if latest_path is None:
            raise FileNotFoundError(f"No existing outputs found in {output_dir} for plot-only.")
        df, _ = load_with_metadata(latest_path)
        sim_run_dir = find_sim_run_dir(latest_path)
        sim_run = sim_run_dir.name if sim_run_dir else "latest"
        plot_dir = (sim_run_dir or latest_path.parent) / "PLOTS"
        ensure_dir(plot_dir)
        plot_path = plot_dir / f"{latest_path.stem}_plots.pdf"
        closure_dfs = None
        cfg7 = yaml.safe_load((ROOT_DIR / "MASTER_STEPS/STEP_7/config_step_7_physics.yaml").read_text())
        cfg10 = physics_cfg
        max_rows = int(plot_sample_rows) if plot_sample_rows else 200000
        chain = resolve_upstream_chain(latest_path)
        closure_dfs = {
            "step6": load_sample_df(chain.get("step6", Path("")), max_rows, cfg.get("seed")),
            "step7": load_sample_df(chain.get("step7", Path("")), max_rows, cfg.get("seed")),
            "step8": load_sample_df(chain.get("step8", Path("")), max_rows, cfg.get("seed")),
            "step9": load_sample_df(chain.get("step9", Path("")), max_rows, cfg.get("seed")),
            "step10": df,
        }
        plot_jitter_summary(df, plot_path, rate_df=df, closure_dfs=closure_dfs, cfg7=cfg7, cfg10=cfg10)
        print(f"Saved {plot_path}")
        return

    input_sim_run_mode = input_sim_run
    if "**" in input_glob:
        candidates = sorted(input_dir.rglob(input_glob.replace("**/", "")))
    else:
        candidates = sorted(input_dir.rglob(input_glob))
    if input_sim_run_mode not in ("latest", "random"):
        input_run_dir = input_dir / str(input_sim_run_mode)
        candidates = [path for path in candidates if input_run_dir in path.parents]
        if not candidates:
            raise FileNotFoundError(
                f"No inputs found for {input_glob} under {input_run_dir}."
            )
    def normalize_stem(path: Path) -> str:
        name = path.name
        if name.endswith(".chunks.json"):
            name = name[: -len(".chunks.json")]
        stem = Path(name).stem
        return stem.replace(".chunks", "")

    if not candidates:
        raise FileNotFoundError(f"No inputs found for {input_glob} under {input_dir}.")

    if input_sim_run_mode == "latest":
        candidates = sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)
    elif input_sim_run_mode == "random":
        rng.shuffle(candidates)

    input_iter = None
    upstream_meta = None
    chunked_input = False
    step_chain = None
    step_10_id = None
    input_path = None
    mesh_dir = Path(cfg.get("param_mesh_dir", "../../SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1"))
    if not mesh_dir.is_absolute():
        mesh_dir = Path(__file__).resolve().parent / mesh_dir

    for candidate in candidates:
        candidate_iter, candidate_meta, candidate_chunked = iter_input_frames(candidate, chunk_rows)
        candidate_chain = extract_step_id_chain(candidate_meta)
        if not candidate_chain:
            continue
        candidate_step_10_id = select_next_step_id(
            output_dir,
            mesh_dir,
            cfg.get("param_mesh_sim_run", "none"),
            "step_10_id",
            candidate_chain,
            cfg.get("seed"),
            physics_cfg.get("step_10_id"),
        )
        if candidate_step_10_id is None:
            continue
        input_path = candidate
        input_iter = candidate_iter
        upstream_meta = candidate_meta
        chunked_input = candidate_chunked
        step_chain = candidate_chain
        step_10_id = candidate_step_10_id
        break

    if input_path is None or input_iter is None or upstream_meta is None or step_chain is None or step_10_id is None:
        print("Skipping STEP_10: all step_10_id combinations already exist.")
        return

    normalized_stem = normalize_stem(input_path)
    print(f"Processing: {input_path}")
    sim_run = build_sim_run_name(step_chain + [step_10_id])
    sim_run_dir = output_dir / sim_run
    if not args.force and sim_run_dir.exists():
        print(f"SIM_RUN {sim_run} already exists; skipping (use --force to regenerate).")
        return

    physics_cfg["step_10_id"] = step_10_id
    sim_run, sim_run_dir, config_hash, upstream_hash, _ = register_sim_run(
        output_dir, "STEP_10", config_path, physics_cfg, upstream_meta, sim_run
    )
    reset_dir(sim_run_dir)

    out_stem_base = "step_10"
    out_stem = f"{out_stem_base}_chunks" if chunk_rows else out_stem_base
    metadata = {
        "created_at": now_iso(),
        "step": "STEP_10",
        "config": physics_cfg,
        "runtime_config": runtime_cfg,
        "sim_run": sim_run,
        "config_hash": config_hash,
        "upstream_hash": upstream_hash,
        "source_dataset": str(input_path),
        "upstream": upstream_meta,
        "step_10_id": step_10_id,
    }
    cfg7 = yaml.safe_load((ROOT_DIR / "MASTER_STEPS/STEP_7/config_step_7_physics.yaml").read_text())
    cfg10 = physics_cfg
    if chunk_rows:
        def _iter_out() -> Iterable[pd.DataFrame]:
            for chunk in input_iter:
                yield prune_step10(apply_jitter(chunk, jitter_width_ns, tdc_sigma_ns, rng))

        manifest_path, last_chunk, row_count = write_chunked_output(
            _iter_out(),
            sim_run_dir,
            out_stem,
            output_format,
            int(chunk_rows),
            metadata,
        )
        plot_df = last_chunk
        rate_df = last_chunk
        closure_dfs = None
        max_rows = int(plot_sample_rows) if plot_sample_rows else 200000
        chain = resolve_upstream_chain(input_path)
        closure_dfs = {
            "step6": load_sample_df(chain.get("step6", Path("")), max_rows, cfg.get("seed")),
            "step7": load_sample_df(chain.get("step7", Path("")), max_rows, cfg.get("seed")),
            "step8": load_sample_df(chain.get("step8", Path("")), max_rows, cfg.get("seed")),
            "step9": load_sample_df(chain.get("step9", Path("")), max_rows, cfg.get("seed")),
            "step10": plot_df,
        }
        if plot_sample_rows and plot_df is not None:
            sample_n = len(plot_df) if plot_sample_rows is True else int(plot_sample_rows)
            sample_n = min(sample_n, len(plot_df))
            plot_df = plot_df.sample(n=sample_n, random_state=cfg.get("seed"))
        if not args.no_plots and plot_df is not None:
            plot_dir = sim_run_dir / "PLOTS"
            ensure_dir(plot_dir)
            plot_path = plot_dir / f"{out_stem_base}_plots.pdf"
            plot_jitter_summary(plot_df, plot_path, rate_df=rate_df, closure_dfs=closure_dfs, cfg7=cfg7, cfg10=cfg10)
        print(f"Saved {manifest_path}")
    else:
        df, upstream_meta = load_with_metadata(input_path)
        out = prune_step10(apply_jitter(df, jitter_width_ns, tdc_sigma_ns, rng))
        out_path = sim_run_dir / f"{out_stem}.{output_format}"
        save_with_metadata(out, out_path, metadata, output_format)
        if not args.no_plots:
            plot_dir = sim_run_dir / "PLOTS"
            ensure_dir(plot_dir)
            plot_path = plot_dir / f"{out_path.stem}_plots.pdf"
            closure_dfs = None
            max_rows = int(plot_sample_rows) if plot_sample_rows else 200000
            chain = resolve_upstream_chain(input_path)
            closure_dfs = {
                "step6": load_sample_df(chain.get("step6", Path("")), max_rows, cfg.get("seed")),
                "step7": load_sample_df(chain.get("step7", Path("")), max_rows, cfg.get("seed")),
                "step8": load_sample_df(chain.get("step8", Path("")), max_rows, cfg.get("seed")),
                "step9": load_sample_df(chain.get("step9", Path("")), max_rows, cfg.get("seed")),
                "step10": out,
            }
            plot_jitter_summary(out, plot_path, rate_df=out, closure_dfs=closure_dfs, cfg7=cfg7, cfg10=cfg10)
        print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
