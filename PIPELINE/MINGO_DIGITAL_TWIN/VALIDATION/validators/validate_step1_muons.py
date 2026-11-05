#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/validators/validate_step1_muons.py
Purpose: Validator for STEP 1 muon generation outputs.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/validators/validate_step1_muons.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .common_io import StepArtifact, load_frame
from .common_report import RESULT_COLUMNS, ResultBuilder


def _safe_std(values: np.ndarray) -> float:
    if values.size <= 1:
        return float("nan")
    return float(np.std(values, ddof=1))


def _plot(df: pd.DataFrame, plot_dir: Path) -> None:
    plot_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))

    axes[0, 0].hist(df["X_gen"].to_numpy(dtype=float), bins=80, color="steelblue", alpha=0.8)
    axes[0, 0].set_title("X_gen")

    axes[0, 1].hist(df["Y_gen"].to_numpy(dtype=float), bins=80, color="seagreen", alpha=0.8)
    axes[0, 1].set_title("Y_gen")

    axes[1, 0].hist(df["Theta_gen"].to_numpy(dtype=float), bins=80, color="darkorange", alpha=0.8)
    axes[1, 0].set_title("Theta_gen")

    axes[1, 1].hist(df["Phi_gen"].to_numpy(dtype=float), bins=80, color="slateblue", alpha=0.8)
    axes[1, 1].set_title("Phi_gen")

    fig.tight_layout()
    fig.savefig(plot_dir / "step1_core_distributions.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 6))
    u = np.cos(df["Theta_gen"].to_numpy(dtype=float))
    u = u[np.isfinite(u)]
    ax.hist(u, bins=80, color="teal", alpha=0.8)
    ax.set_title("cos(theta)")
    fig.tight_layout()
    fig.savefig(plot_dir / "step1_cos_theta.png", dpi=140)
    plt.close(fig)


def run(
    artifacts: dict[str, StepArtifact],
    run_timestamp: str,
    output_dir: Path,
    make_plots: bool = False,
    sample_rows: int = 300_000,
) -> pd.DataFrame:
    art = artifacts.get("1")
    rb = ResultBuilder(
        run_timestamp=run_timestamp,
        validator="validate_step1_muons",
        step="1",
        sim_run=art.sim_run if art else None,
        config_hash=art.config_hash if art else None,
        upstream_hash=art.upstream_hash if art else None,
        n_rows_in=art.row_count if art else None,
        n_rows_out=art.row_count if art else None,
    )

    if art is None or art.data_path is None or not art.data_path.exists():
        rb.add(
            test_id="step1_exists",
            test_name="STEP 1 output exists",
            metric_name="step1_exists",
            metric_value=0,
            status="SKIP",
            notes="No STEP 1 dataset found",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    cols = ["event_id", "X_gen", "Y_gen", "Z_gen", "Theta_gen", "Phi_gen", "T_thick_s"]
    try:
        df = load_frame(art.data_path, columns=cols, max_rows=sample_rows)
    except Exception as exc:
        rb.add_exception(test_id="step1_read", test_name="Read STEP 1 sample", exc=exc)
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    if df.empty:
        rb.add(
            test_id="step1_non_empty",
            test_name="STEP 1 has rows",
            metric_name="sample_rows",
            metric_value=0,
            status="FAIL",
            notes="Sample read returned no rows",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    rb.add(
        test_id="step1_sample_loaded",
        test_name="STEP 1 sample loaded",
        metric_name="sample_rows",
        metric_value=len(df),
        status="PASS",
        notes=f"sampled first {len(df)} rows",
    )

    missing = [c for c in cols if c not in df.columns]
    rb.add(
        test_id="step1_required_columns",
        test_name="Required STEP 1 columns",
        metric_name="missing_columns",
        metric_value=len(missing),
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if not missing else "FAIL",
        notes=", ".join(missing),
    )

    cfg = art.metadata.get("config") or {}
    xlim = float(cfg.get("xlim_mm", np.nan))
    ylim = float(cfg.get("ylim_mm", np.nan))
    z_plane = float(cfg.get("z_plane_mm", np.nan))
    cos_n = float(cfg.get("cos_n", np.nan))

    x = df["X_gen"].to_numpy(dtype=float)
    y = df["Y_gen"].to_numpy(dtype=float)
    z = df["Z_gen"].to_numpy(dtype=float)
    th = df["Theta_gen"].to_numpy(dtype=float)
    ph = df["Phi_gen"].to_numpy(dtype=float)

    if np.isfinite(xlim):
        x_bad = int((np.abs(x) > (xlim + 1e-9)).sum())
        rb.add(
            test_id="step1_x_bounds",
            test_name="X_gen inside configured bounds",
            metric_name="out_of_bounds_rows",
            metric_value=x_bad,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if x_bad == 0 else "FAIL",
            notes=f"xlim={xlim}",
        )

    if np.isfinite(ylim):
        y_bad = int((np.abs(y) > (ylim + 1e-9)).sum())
        rb.add(
            test_id="step1_y_bounds",
            test_name="Y_gen inside configured bounds",
            metric_name="out_of_bounds_rows",
            metric_value=y_bad,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if y_bad == 0 else "FAIL",
            notes=f"ylim={ylim}",
        )

    if np.isfinite(z_plane):
        z_dev = float(np.nanmax(np.abs(z - z_plane)))
        rb.add(
            test_id="step1_z_plane",
            test_name="Z_gen matches configured plane",
            metric_name="max_abs_residual_mm",
            metric_value=z_dev,
            expected_value=0.0,
            threshold_low=0.0,
            threshold_high=1e-9,
            status="PASS" if z_dev <= 1e-9 else "FAIL",
            notes=f"z_plane={z_plane}",
        )

    theta_bad = int(((th < -1e-9) | (th > (np.pi / 2 + 1e-6)) | ~np.isfinite(th)).sum())
    rb.add(
        test_id="step1_theta_range",
        test_name="Theta_gen in [0, pi/2]",
        metric_name="out_of_range_rows",
        metric_value=theta_bad,
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if theta_bad == 0 else "FAIL",
    )

    phi_bad = int(((ph < -np.pi - 1e-6) | (ph > np.pi + 1e-6) | ~np.isfinite(ph)).sum())
    rb.add(
        test_id="step1_phi_range",
        test_name="Phi_gen in [-pi, pi]",
        metric_name="out_of_range_rows",
        metric_value=phi_bad,
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if phi_bad == 0 else "FAIL",
    )

    n = len(df)
    x_mean = float(np.nanmean(x))
    y_mean = float(np.nanmean(y))
    if np.isfinite(xlim) and n > 10:
        sigma_mean_x = xlim / np.sqrt(3.0 * n)
        zx = abs(x_mean) / sigma_mean_x if sigma_mean_x > 0 else np.inf
        status = "PASS" if zx <= 3 else ("WARN" if zx <= 5 else "FAIL")
        rb.add(
            test_id="step1_x_symmetry",
            test_name="X_gen mean close to zero",
            metric_name="zscore_mean",
            metric_value=zx,
            expected_value=0,
            threshold_low=0,
            threshold_high=3,
            status=status,
            notes=f"mean={x_mean:.6f}",
        )

    if np.isfinite(ylim) and n > 10:
        sigma_mean_y = ylim / np.sqrt(3.0 * n)
        zy = abs(y_mean) / sigma_mean_y if sigma_mean_y > 0 else np.inf
        status = "PASS" if zy <= 3 else ("WARN" if zy <= 5 else "FAIL")
        rb.add(
            test_id="step1_y_symmetry",
            test_name="Y_gen mean close to zero",
            metric_name="zscore_mean",
            metric_value=zy,
            expected_value=0,
            threshold_low=0,
            threshold_high=3,
            status=status,
            notes=f"mean={y_mean:.6f}",
        )

    if np.isfinite(cos_n):
        u = np.cos(th)
        u = u[np.isfinite(u)]
        if u.size > 100:
            obs_mean = float(np.mean(u))
            exp_mean = (cos_n + 1.0) / (cos_n + 2.0)
            exp_second = (cos_n + 1.0) / (cos_n + 3.0)
            exp_var = max(exp_second - exp_mean * exp_mean, 0.0)
            stderr = np.sqrt(exp_var / u.size) if exp_var > 0 else np.nan
            zscore = abs(obs_mean - exp_mean) / stderr if stderr and np.isfinite(stderr) and stderr > 0 else np.inf
            status = "PASS" if zscore <= 3 else ("WARN" if zscore <= 5 else "FAIL")
            rb.add(
                test_id="step1_cos_theta_closure",
                test_name="cos(theta) mean closure vs cos_n",
                metric_name="zscore_mean",
                metric_value=zscore,
                expected_value=0,
                threshold_low=0,
                threshold_high=3,
                status=status,
                notes=f"obs={obs_mean:.6f}, exp={exp_mean:.6f}, N={u.size}",
            )

    # Uniform phi sanity via mean unit vector length.
    if len(ph) > 100:
        mean_sin = float(np.nanmean(np.sin(ph)))
        mean_cos = float(np.nanmean(np.cos(ph)))
        r = np.sqrt(mean_sin**2 + mean_cos**2)
        thr = 5.0 / np.sqrt(len(ph))
        status = "PASS" if r <= thr else "WARN"
        rb.add(
            test_id="step1_phi_uniformity",
            test_name="Phi uniformity (mean unit vector)",
            metric_name="mean_resultant",
            metric_value=r,
            expected_value=0,
            threshold_low=0,
            threshold_high=thr,
            status=status,
        )

    if "T_thick_s" in df.columns:
        t = df["T_thick_s"].to_numpy(dtype=float)
        finite_t = t[np.isfinite(t)]
        neg = int((finite_t < 0).sum())
        rb.add(
            test_id="step1_t_thick_nonnegative",
            test_name="T_thick_s is non-negative",
            metric_name="negative_rows",
            metric_value=neg,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if neg == 0 else "FAIL",
        )

        # For sequentially loaded chunks, this should be non-decreasing.
        if finite_t.size > 1:
            desc = int((np.diff(finite_t) < 0).sum())
            rb.add(
                test_id="step1_t_thick_monotonic_sample",
                test_name="T_thick_s monotonic in sampled order",
                metric_name="descending_diffs",
                metric_value=desc,
                expected_value=0,
                threshold_low=0,
                threshold_high=0,
                status="PASS" if desc == 0 else "WARN",
                notes="sample-order check only",
            )

    if art.row_count is not None:
        rb.add(
            test_id="step1_manifest_row_count",
            test_name="STEP 1 manifest row_count available",
            metric_name="row_count",
            metric_value=int(art.row_count),
            status="PASS" if art.row_count > 0 else "FAIL",
        )

    if make_plots:
        _plot(df, output_dir / "plots" / "validate_step1_muons")

    return rb.to_frame().reindex(columns=RESULT_COLUMNS)
