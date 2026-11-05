#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/STEPS/COMMON/ANGULAR_FLUX/angular_flux.py
Purpose: Compare angular flux (Theta/Phi) across STEP 1, 2, 9 and 10 for the same sim-run.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/STEPS/COMMON/ANGULAR_FLUX/angular_flux.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

from pathlib import Path
import json
import math
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def load_metadata(path: Path) -> dict:
    if path is None:
        return {}
    if path.name.endswith(".chunks.json"):
        try:
            return json.loads(path.read_text()).get("metadata", {})
        except Exception:
            return {}
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text())
        except Exception:
            return {}
    return {}


def find_any_chunk_for_step(step: int) -> Path | None:
    root = Path(__file__).resolve().parents[4] / "INTERSTEPS"
    # Use rglob to search recursively for part_*.pkl in step_{step}_chunks folders
    for pkl in root.rglob(f"step_{step}_chunks/part_*.pkl"):
        if pkl.exists():
            return pkl
    # Fallback: search for any step_{step}_chunks.chunks.json manifest recursively
    for manifest in root.rglob(f"step_{step}_chunks.chunks.json"):
        try:
            j = json.loads(manifest.read_text())
            parts_list = [p for p in j.get("chunks", []) if p.endswith(".pkl")]
            if not parts_list:
                parts_list = [p for p in j.get("parts", []) if p.endswith(".pkl")]
            if parts_list:
                p0 = Path(parts_list[0])
                if not p0.is_absolute():
                    p0 = manifest.parent / p0
                if p0.exists():
                    return p0
        except Exception:
            continue
    return None


def resolve_upstream_chain(start_path: Path) -> dict:
    """Walk metadata.source_dataset upstream and collect step chunk paths."""
    chain = { }
    p = start_path
    visited = set()
    while p is not None and str(p) not in visited:
        visited.add(str(p))
        m = load_metadata(p)
        step_name = (m.get("step") or "").upper()
        if step_name.startswith("STEP_"):
            try:
                step_num = int(step_name.split("_")[1])
                chain[step_num] = p
            except Exception:
                pass
        src = m.get("source_dataset")
        p = Path(src) if src else None
    return chain


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
        return pd.read_pickle(path)
    raise ValueError(f"Unsupported chunk file type: {path}")



def _compute_counts_per_theta_tt(df: pd.DataFrame, tt_col: str = "tt_crossing"):
    """
    Returns dict: {tt_label: (theta_deg, counts_per_min)} for all tt_* in df.
    No area or solid angle normalization, just counts per theta per minute.
    """
    if "Theta_gen" not in df.columns or "T_thick_s" not in df.columns or tt_col not in df.columns:
        return {}
    t0_all = df["T_thick_s"].to_numpy(dtype=float)
    if not np.isfinite(t0_all).any():
        return {}
    sec_min = int(np.floor(np.nanmin(t0_all)))
    sec_max = int(np.floor(np.nanmax(t0_all)))
    if sec_max <= sec_min + 1:
        return {}
    inner_mask = (np.floor(t0_all).astype(int) > sec_min) & (np.floor(t0_all).astype(int) < sec_max) & np.isfinite(t0_all)
    duration_s = float((sec_max - sec_min - 1))
    if not np.isfinite(duration_s) or duration_s <= 0.0:
        return {}
    duration_min = duration_s / 60.0
    theta_all = df["Theta_gen"].to_numpy(dtype=float)
    tt_ser = pd.Series(df[tt_col]).astype("string").fillna("")
    tt_labels = [str(v) for v in tt_ser.unique() if str(v) != ""]
    theta_edges = np.linspace(0.0, np.pi / 2.0, 31)
    theta_centers = 0.5 * (theta_edges[1:] + theta_edges[:-1])
    result = {}
    for tt_label in tt_labels:
        mask_tt = (tt_ser == tt_label).to_numpy(dtype=bool) & inner_mask
        theta_tt = theta_all[mask_tt & np.isfinite(theta_all) & (theta_all >= 0.0) & (theta_all <= np.pi / 2.0)]
        if theta_tt.size == 0:
            continue
        counts, _ = np.histogram(theta_tt, bins=theta_edges)
        valid = (counts > 0)
        theta_deg = np.degrees(theta_centers[valid])
        counts_per_min = counts[valid].astype(float) / duration_min
        result[tt_label] = (theta_deg, counts_per_min)
    return result


def _compute_counts_per_theta_total(df: pd.DataFrame):
    """Return (theta_deg, counts_per_min) for the whole dataframe (no tt split).
    Matches the same binning used by _compute_counts_per_theta_tt.
    """
    if "Theta_gen" not in df.columns or "T_thick_s" not in df.columns:
        return None
    t0_all = df["T_thick_s"].to_numpy(dtype=float)
    if not np.isfinite(t0_all).any():
        return None
    sec_min = int(np.floor(np.nanmin(t0_all)))
    sec_max = int(np.floor(np.nanmax(t0_all)))
    if sec_max <= sec_min + 1:
        return None
    inner_mask = (np.floor(t0_all).astype(int) > sec_min) & (np.floor(t0_all).astype(int) < sec_max) & np.isfinite(t0_all)
    duration_s = float((sec_max - sec_min - 1))
    if not np.isfinite(duration_s) or duration_s <= 0.0:
        return None
    duration_min = duration_s / 60.0
    theta_all = df["Theta_gen"].to_numpy(dtype=float)
    theta_inner = theta_all[np.isfinite(theta_all) & (theta_all >= 0.0) & (theta_all <= np.pi / 2.0) & inner_mask]
    if theta_inner.size == 0:
        return None
    theta_edges = np.linspace(0.0, np.pi / 2.0, 31)
    theta_centers = 0.5 * (theta_edges[1:] + theta_edges[:-1])
    counts, _ = np.histogram(theta_inner, bins=theta_edges)
    valid = (counts > 0)
    theta_deg = np.degrees(theta_centers[valid])
    counts_per_min = counts[valid].astype(float) / duration_min
    return theta_deg, counts_per_min

def plot_muon_flux_tt_comparison(pdf: PdfPages, sample_path: Path | None = None) -> bool:
    """
    For STEP 2, 8, 10: plot counts per theta per minute, split by all tt_crossing categories, one panel per step.
    """
    steps = [1, 2, 9, 10]
    labels = {1: "STEP 1 (original)", 2: "STEP 2", 9: "STEP 9", 10: "STEP 10"}
    chain = {}
    if sample_path is not None:
        chain = resolve_upstream_chain(sample_path)
    # fallback: just find any chunk for each step
    for s in steps:
        if s not in chain:
            p = find_any_chunk_for_step(s)
            if p is not None:
                chain[s] = p

    # if STEP 1 not found, attempt to locate a STEP 1 chunk by walking upstream
    # from any other found step (common-case: STEP_2 or STEP_9 point upstream to STEP_1)
    if 1 not in chain and chain:
        for p in list(chain.values()):
            upstream = resolve_upstream_chain(p)
            if 1 in upstream:
                chain[1] = upstream[1]
                break

    # as a last resort, look under SIMULATION_OUTPUTS/INTERSTEPS/STEP_1_TO_2 for any available STEP_1 chunks
    if 1 not in chain:
        step1_root = Path(__file__).resolve().parents[4] / "INTERSTEPS" / "STEP_1_TO_2"
        if step1_root.exists():
            for pkl in step1_root.rglob("**/chunks/part_*.pkl"):
                chain[1] = pkl
                break
    # quick diagnostic for which steps we actually found
    if chain:
        print(f"Found STEP data for: {sorted(chain.keys())}")
    else:
        print("No available STEP_1/2/9/10 data found; nothing plotted.")
        return False
    fig, axes = plt.subplots(4, 2, figsize=(18, 16), sharex='col')
    phase_titles = {
        1: "pre-crossing, pre-efficiency, pre-trigger",
        2: "post-crossing, pre-efficiency, pre-trigger",
        9: "post-crossing, post-efficiency, pre-trigger",
        10: "post-crossing, post-efficiency, post-trigger",
    }

    for idx, s in enumerate(steps):
        ax_theta = axes[idx][0]
        ax_phi = axes[idx][1]
        p = chain.get(s)
        if p is None:
            ax_theta.set_visible(False)
            ax_phi.set_visible(False)
            continue
        try:
            df = load_df(p)
        except Exception:
            ax_theta.set_visible(False)
            ax_phi.set_visible(False)
            continue

        # STEP 1: show normalized flux with theory overlay (reference panel)
        if s == 1:
            res = _compute_flux_step1(df)
            if res is None:
                ax_theta.set_visible(False)
                ax_phi.set_visible(False)
                continue
            theta_deg, flux, flux_err, duration_min, area_cm2, model_curve, theta_curve_deg, fit_label = res
            # plot as histogram (step) using raw Theta_gen values for an actual histogram
            theta_all = df["Theta_gen"].to_numpy(dtype=float)
            t0_all = df["T_thick_s"].to_numpy(dtype=float)
            sec_min = int(np.floor(np.nanmin(t0_all)))
            sec_max = int(np.floor(np.nanmax(t0_all)))
            inner_mask = (np.floor(t0_all).astype(int) > sec_min) & (np.floor(t0_all).astype(int) < sec_max) & np.isfinite(t0_all)
            theta_inner = theta_all[np.isfinite(theta_all) & (theta_all >= 0.0) & (theta_all <= np.pi / 2.0) & inner_mask]
            if theta_inner.size > 0:
                theta_edges = np.linspace(0.0, np.pi / 2.0, 31)
                theta_edges_deg = np.degrees(theta_edges)
                theta_inner_deg = np.degrees(theta_inner)
                weights = np.ones_like(theta_inner_deg) / (duration_min * area_cm2)
                ax_theta.hist(theta_inner_deg, bins=theta_edges_deg, histtype="step", linewidth=1.6, color="black", weights=weights, label=(f"STEP 1 sample (T={duration_min:.3f} min, Axy={area_cm2:.2f} cm^2)"))
            else:
                ax_theta.set_visible(False)
            if model_curve is not None and theta_curve_deg is not None:
                ax_theta.plot(theta_curve_deg, model_curve, color="tab:red", linestyle="--", linewidth=1.2, label=fit_label or "theory")
            ax_theta.set_ylabel("Counts per min (per cm^2 per θ-bin)")
            ax_theta.set_title(f"{labels.get(s, s)} — {phase_titles.get(s)} (Theta_gen)")
            ax_theta.grid(alpha=0.3)
            ax_theta.legend(loc="upper right", fontsize=9)

            # Phi_gen panel (right): identical logic, but for Phi_gen
            if "Phi_gen" in df.columns:
                phi_all = df["Phi_gen"].to_numpy(dtype=float)
                phi_edges = np.linspace(-np.pi, np.pi, 31)
                phi_centers = 0.5 * (phi_edges[1:] + phi_edges[:-1])
                t0_all = df["T_thick_s"].to_numpy(dtype=float)
                sec_min = int(np.floor(np.nanmin(t0_all)))
                sec_max = int(np.floor(np.nanmax(t0_all)))
                inner_mask = (np.floor(t0_all).astype(int) > sec_min) & (np.floor(t0_all).astype(int) < sec_max) & np.isfinite(t0_all)
                valid_phi = np.isfinite(phi_all) & inner_mask
                phi_inner = phi_all[valid_phi]
                counts_phi, _ = np.histogram(phi_inner, bins=phi_edges)
                valid = (counts_phi > 0)
                phi_deg = np.degrees(phi_centers[valid])
                counts_per_phi = counts_phi[valid].astype(float) / (duration_min * area_cm2)
                counts_per_phi_err = np.sqrt(counts_phi[valid]) / (duration_min * area_cm2)
                # plot phi as histogram (step) using raw phi values
                phi_edges_deg = np.degrees(phi_edges)
                phi_inner_deg = np.degrees(phi_inner)
                weights_phi = np.ones_like(phi_inner_deg) / (duration_min * area_cm2)
                ax_phi.hist(phi_inner_deg, bins=phi_edges_deg, histtype="step", linewidth=1.6, color="black", weights=weights_phi, label=(f"STEP 1 sample (T={duration_min:.3f} min, Axy={area_cm2:.2f} cm^2)"))
                # Do NOT draw theory on any Phi_gen panel (user-requested)
                ax_phi.set_ylabel("Counts per min (per cm^2 per φ-bin)")
                ax_phi.set_title(f"{labels.get(s, s)} — {phase_titles.get(s)} (Phi_gen)")
                ax_phi.grid(alpha=0.3)
                ax_phi.legend(loc="upper right", fontsize=9)
            else:
                ax_phi.set_visible(False)
            continue

        # Other STEPs: counts per theta per minute, split by tt_crossing
        tt_traces = _compute_counts_per_theta_tt(df)

        # If no tt_* categories present, plot the total counts-per-theta
        if not tt_traces:
            total = _compute_counts_per_theta_total(df)
            if total is None:
                ax_theta.set_visible(False)
                ax_phi.set_visible(False)
                continue
            theta_deg, counts_per_min = total
            # draw as histogram-step (centres -> step)
            ax_theta.step(theta_deg, counts_per_min, where='mid', color="black", linewidth=1.6, label="total")
            ax_theta.set_ylabel("Counts per min")
            ax_theta.set_title(f"{labels.get(s, s)} — {phase_titles.get(s)} (Theta_gen)")
            ax_theta.grid(alpha=0.3)
            ax_theta.legend(loc="upper right", fontsize=9)
            # For phi
            if "Phi_gen" in df.columns:
                phi_all = df["Phi_gen"].to_numpy(dtype=float)
                phi_edges = np.linspace(-np.pi, np.pi, 31)
                phi_centers = 0.5 * (phi_edges[1:] + phi_edges[:-1])
                t0_all = df["T_thick_s"].to_numpy(dtype=float)
                sec_min = int(np.floor(np.nanmin(t0_all)))
                sec_max = int(np.floor(np.nanmax(t0_all)))
                inner_mask = (np.floor(t0_all).astype(int) > sec_min) & (np.floor(t0_all).astype(int) < sec_max) & np.isfinite(t0_all)
                valid_phi = np.isfinite(phi_all) & inner_mask
                phi_inner = phi_all[valid_phi]
                counts_phi, _ = np.histogram(phi_inner, bins=phi_edges)
                valid = (counts_phi > 0)
                phi_deg = np.degrees(phi_centers[valid])
                duration_s = float((sec_max - sec_min - 1))
                duration_min = duration_s / 60.0 if duration_s > 0 else 1.0
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
                counts_per_phi = counts_phi[valid].astype(float) / (duration_min * area_cm2)
                counts_per_phi_err = np.sqrt(counts_phi[valid]) / (duration_min * area_cm2)
                # plot phi as histogram-step using raw values
                phi_edges_deg = np.degrees(phi_edges)
                phi_inner_deg = np.degrees(phi_inner)
                weights_phi = np.ones_like(phi_inner_deg) / (duration_min * area_cm2)
                ax_phi.hist(phi_inner_deg, bins=phi_edges_deg, histtype='step', linewidth=1.6, color='black', weights=weights_phi, label=(f"STEP {s} sample (T={duration_min:.3f} min, Axy={area_cm2:.2f} cm^2)"))
                # Do NOT draw theory on any Phi_gen panel (user-requested)
                ax_phi.set_ylabel("Counts per min (per cm^2 per φ-bin)")
                ax_phi.set_title(f"{labels.get(s, s)} — {phase_titles.get(s)} (Phi_gen)")
                ax_phi.grid(alpha=0.3)
                ax_phi.legend(loc="upper right", fontsize=9)
            else:
                ax_phi.set_visible(False)
            continue

        # plot individual tt traces
        cmap = plt.get_cmap("tab10")
        for i, (tt_label, (theta_deg, counts_per_min)) in enumerate(sorted(tt_traces.items())):
            color = cmap(i % cmap.N)
            # draw per-tt as histogram-step (centres -> step)
            ax_theta.step(theta_deg, counts_per_min, where='mid', color=color, linewidth=1.4, label=f"tt={tt_label}")
        # For phi (tt split)
        if "Phi_gen" in df.columns:
            phi_all = df["Phi_gen"].to_numpy(dtype=float)
            phi_edges = np.linspace(-np.pi, np.pi, 31)
            phi_centers = 0.5 * (phi_edges[1:] + phi_edges[:-1])
            t0_all = df["T_thick_s"].to_numpy(dtype=float)
            sec_min = int(np.floor(np.nanmin(t0_all)))
            sec_max = int(np.floor(np.nanmax(t0_all)))
            inner_mask = (np.floor(t0_all).astype(int) > sec_min) & (np.floor(t0_all).astype(int) < sec_max) & np.isfinite(t0_all)
            duration_s = float((sec_max - sec_min - 1))
            duration_min = duration_s / 60.0 if duration_s > 0 else 1.0
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
            tt_ser = pd.Series(df["tt_crossing"]).astype("string").fillna("")
            tt_labels = [str(v) for v in tt_ser.unique() if str(v) != ""]
            for i, tt_label in enumerate(tt_labels):
                mask_tt = (tt_ser == tt_label).to_numpy(dtype=bool) & inner_mask
                phi_tt = phi_all[mask_tt & np.isfinite(phi_all)]
                if phi_tt.size == 0:
                    continue
                counts, _ = np.histogram(phi_tt, bins=phi_edges)
                valid = (counts > 0)
                phi_deg = np.degrees(phi_centers[valid])
                counts_per_min = counts[valid].astype(float) / duration_min
                color = cmap(i % cmap.N)
                # draw per-tt phi as histogram-step
                ax_phi.step(phi_deg, counts_per_min, where='mid', color=color, linewidth=1.4, label=f"tt={tt_label}")
            # No theory overlay for Phi_gen panels (user-requested)
            ax_phi.set_ylabel("Counts per min (per φ-bin)")
            ax_phi.set_title(f"{labels.get(s, s)} — {phase_titles.get(s)} (Phi_gen)")
            ax_phi.grid(alpha=0.3)
            ax_phi.legend(loc="upper right", fontsize=9)
        else:
            ax_phi.set_visible(False)

        # STEP 2: add envelope = sum of all tt traces (user request)
        if s == 2:
            # re-create full theta centers used by the helper and sum aligned bins
            theta_edges = np.linspace(0.0, np.pi / 2.0, 31)
            theta_centers = 0.5 * (theta_edges[1:] + theta_edges[:-1])
            theta_deg_full = np.degrees(theta_centers)
            tot = np.zeros_like(theta_deg_full)
            for (_tt, (tdeg, cpm)) in tt_traces.items():
                for v, c in zip(tdeg, cpm):
                    # find matching index in full grid (exact match expected)
                    idx = np.where(np.isclose(theta_deg_full, v, atol=1e-6))[0]
                    if idx.size:
                        tot[idx[0]] += c
            valid = tot > 0.0
            if np.any(valid):
                # draw sum envelope as histogram-step
                ax_theta.step(theta_deg_full[valid], tot[valid], where='mid', color="black", linewidth=2.2, label="sum (all tt)")

        ax_theta.set_ylabel("Counts per min")
        ax_theta.set_title(f"{labels.get(s, s)} — {phase_titles.get(s)} (Theta_gen)")
        ax_theta.grid(alpha=0.3)
        ax_theta.legend(loc="upper right", fontsize=9)
    axes[-1][0].set_xlabel("Zenith angle θ (deg)")
    axes[-1][1].set_xlabel("Azimuthal angle φ (deg)")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)
    return True


def plot_muon_flux_steps_comparison(pdf: PdfPages, sample_path: Path | None = None) -> bool:
    """Backward-compatible alias retained for older callers."""
    return plot_muon_flux_tt_comparison(pdf, sample_path=sample_path)

def _compute_flux_step1(df: pd.DataFrame):
    """
    Returns (theta_deg, flux, flux_err, duration_min, area_cm2, model_curve, theta_curve, fit_label)
    for STEP 1 reference panel (area and solid angle normalized, with theory overlay).
    """
    if "Theta_gen" not in df.columns or "T_thick_s" not in df.columns or "X_gen" not in df.columns or "Y_gen" not in df.columns:
        return None
    t0_all = df["T_thick_s"].to_numpy(dtype=float)
    if not np.isfinite(t0_all).any():
        return None
    sec_min = int(np.floor(np.nanmin(t0_all)))
    sec_max = int(np.floor(np.nanmax(t0_all)))
    if sec_max <= sec_min + 1:
        return None
    inner_mask = (np.floor(t0_all).astype(int) > sec_min) & (np.floor(t0_all).astype(int) < sec_max) & np.isfinite(t0_all)
    theta_all = df["Theta_gen"].to_numpy(dtype=float)
    theta = theta_all[np.isfinite(theta_all) & (theta_all >= 0.0) & (theta_all <= np.pi / 2.0) & inner_mask]
    if theta.size < 20:
        return None
    sec_min_inner = sec_min + 1
    sec_max_inner = sec_max - 1
    duration_s = float(sec_max_inner - sec_min_inner + 1)
    if not np.isfinite(duration_s) or duration_s <= 0.0:
        return None
    duration_min = duration_s / 60.0
    x_all = df["X_gen"].to_numpy(dtype=float)
    y_all = df["Y_gen"].to_numpy(dtype=float)
    x_vals = x_all[np.isfinite(x_all) & inner_mask]
    y_vals = y_all[np.isfinite(y_all) & inner_mask]
    if x_vals.size < 2 or y_vals.size < 2:
        return None
    area_cm2 = (float(np.max(x_vals)) - float(np.min(x_vals))) * (float(np.max(y_vals)) - float(np.min(y_vals))) / 100.0
    if not np.isfinite(area_cm2) or area_cm2 <= 0.0:
        return None
    theta_edges = np.linspace(0.0, np.pi / 2.0, 31)
    theta_centers = 0.5 * (theta_edges[1:] + theta_edges[:-1])
    counts, _ = np.histogram(theta, bins=theta_edges)
    # For STEP 1 we keep counts per theta-bin (do NOT divide by solid angle)
    valid = (counts > 0)
    if not np.any(valid):
        return None
    theta_deg = np.degrees(theta_centers[valid])
    counts_valid = counts[valid].astype(float)
    counts_per_theta = counts_valid / (duration_min * area_cm2)
    counts_per_theta_err = np.sqrt(counts_valid) / (duration_min * area_cm2)
    # Theory overlay (optional)
    try:
        param_path = Path(__file__).resolve().parents[4] / "INTERSTEPS" / "STEP_0_TO_1" / "param_mesh.csv"
        cos_n = 2.0
        flux_F = None
        if param_path.exists():
            pm = pd.read_csv(param_path)
            row = pm.iloc[0]
            cos_n = float(row.get('cos_n', 2.0))
            flux_F = float(row.get('flux_cm2_min', float('nan')))
        if flux_F is not None and np.isfinite(flux_F):
            n_theory = float(cos_n)
            i0_theory = float(flux_F * (n_theory + 1.0) / (2.0 * math.pi))
            theta_curve = np.linspace(0.0, np.pi / 2.0 - 1e-4, 400)
            cos_curve = np.clip(np.cos(theta_curve), 1e-12, 1.0)
            model_per_sr = i0_theory * np.power(cos_curve, n_theory)
            # Convert theory (per sr) to counts-per-theta-bin: model_counts(θ)=I(θ)*2π*sinθ*Δθ
            delta_theta = float(theta_edges[1] - theta_edges[0])
            model_curve_counts = model_per_sr * (2.0 * math.pi * np.sin(theta_curve) * delta_theta)
            fit_label = (
                r"Theory: $I(\theta)=I_0\cdot\cos^{n}(\theta)$ (converted to counts-per-θ-bin)"
                + "\n"
                + rf"$I_0={i0_theory:.4g}$ min$^{{-1}}$ cm$^{{-2}}$ sr$^{{-1}}$, $n={n_theory:.2f}$"
            )
            return theta_deg, counts_per_theta, counts_per_theta_err, duration_min, area_cm2, model_curve_counts, np.degrees(theta_curve), fit_label
    except Exception:
        pass
    return theta_deg, counts_per_theta, counts_per_theta_err, duration_min, area_cm2, None, None, None




def main() -> None:
    out_dir = Path(__file__).resolve().parent / "PLOTS"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "angular_flux_tt_comparison.pdf"
    sample10 = find_any_chunk_for_step(10)
    with PdfPages(out_path) as pdf:
        added = plot_muon_flux_tt_comparison(pdf, sample_path=sample10)
        if not added:
            print("No STEP 1/2/9/10 data available; nothing plotted.")
            sys.exit(2)
    print(f"Saved {out_path}")


if __name__ == '__main__':
    main()
