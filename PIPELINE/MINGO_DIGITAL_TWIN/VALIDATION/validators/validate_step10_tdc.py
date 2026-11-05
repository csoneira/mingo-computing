#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/validators/validate_step10_tdc.py
Purpose: Validator for STEP 10 TDC smear and DAQ jitter.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/validators/validate_step10_tdc.py [options]
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


def _plot(jitter: np.ndarray, noise: np.ndarray, delta_t: np.ndarray, plot_dir: Path) -> None:
    plot_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    if jitter.size:
        axes[0].hist(jitter, bins=80, color="steelblue", alpha=0.8)
    axes[0].set_title("daq_jitter_ns")

    if noise.size:
        axes[1].hist(noise, bins=80, color="darkorange", alpha=0.8)
    axes[1].set_title("(T10-T9)-jitter")

    if delta_t.size:
        axes[2].hist(delta_t, bins=80, color="seagreen", alpha=0.8)
    axes[2].set_title("T10-T9")

    fig.tight_layout()
    fig.savefig(plot_dir / "step10_jitter_and_smear.png", dpi=140)
    plt.close(fig)


def run(
    artifacts: dict[str, StepArtifact],
    run_timestamp: str,
    output_dir: Path,
    make_plots: bool = False,
) -> pd.DataFrame:
    art10 = artifacts.get("10")
    art9 = artifacts.get("9")
    rb = ResultBuilder(
        run_timestamp=run_timestamp,
        validator="validate_step10_tdc",
        step="10",
        sim_run=art10.sim_run if art10 else None,
        config_hash=art10.config_hash if art10 else None,
        upstream_hash=art10.upstream_hash if art10 else None,
        n_rows_in=art9.row_count if art9 else None,
        n_rows_out=art10.row_count if art10 else None,
    )

    if art10 is None or art10.data_path is None or not art10.data_path.exists():
        rb.add(
            test_id="step10_exists",
            test_name="STEP 10 output exists",
            metric_name="step10_exists",
            metric_value=0,
            status="SKIP",
            notes="No STEP 10 dataset found",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    if art9 is None or art9.data_path is None or not art9.data_path.exists():
        rb.add(
            test_id="step10_inputs",
            test_name="STEP 9 inputs available",
            metric_name="step9_available",
            metric_value=0,
            status="SKIP",
            notes="No STEP 9 dataset found",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    cols = ["event_id", "daq_jitter_ns"]
    for i in range(1, 5):
        for j in range(1, 5):
            cols.extend(
                [
                    f"T_front_{i}_s{j}",
                    f"T_back_{i}_s{j}",
                    f"Q_front_{i}_s{j}",
                    f"Q_back_{i}_s{j}",
                ]
            )

    try:
        df10 = load_frame(art10.data_path, columns=cols)
        cols9 = [c for c in cols if c != "daq_jitter_ns"]
        df9 = load_frame(art9.data_path, columns=cols9)
        merged = df10.merge(df9, on="event_id", how="inner", suffixes=("_10", "_9"))
    except Exception as exc:
        rb.add_exception(test_id="step10_read_merge", test_name="Read/merge STEP 9 and STEP 10", exc=exc)
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    if merged.empty:
        rb.add(
            test_id="step10_merge_non_empty",
            test_name="STEP 9/10 merge has rows",
            metric_name="merged_rows",
            metric_value=0,
            status="SKIP",
            notes="No common event_id rows",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    ids10 = set(df10["event_id"].astype(int).tolist())
    ids9 = set(df9["event_id"].astype(int).tolist())
    diff = len(ids10.symmetric_difference(ids9))
    rb.add(
        test_id="step10_event_id_conservation",
        test_name="event_id set preserved from STEP 9",
        metric_name="set_symmetric_diff",
        metric_value=diff,
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if diff == 0 else "FAIL",
    )

    cfg = art10.metadata.get("config") or {}
    jitter_width = float(cfg.get("jitter_width_ns", 10.0))
    tdc_sigma = float(cfg.get("tdc_sigma_ns", 0.016))

    if "daq_jitter_ns" not in df10.columns:
        rb.add(
            test_id="step10_jitter_column",
            test_name="daq_jitter_ns column exists",
            metric_name="column_exists",
            metric_value=0,
            status="FAIL",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    # Build active mask from STEP 9 charges.
    active = np.zeros(len(merged), dtype=bool)
    for i in range(1, 5):
        for j in range(1, 5):
            qf = f"Q_front_{i}_s{j}_9"
            qb = f"Q_back_{i}_s{j}_9"
            if qf in merged.columns:
                active |= merged[qf].to_numpy(dtype=float) > 0
            if qb in merged.columns:
                active |= merged[qb].to_numpy(dtype=float) > 0

    jitter = merged["daq_jitter_ns"].to_numpy(dtype=float)
    active_jitter = jitter[active]
    inactive_jitter = jitter[~active]

    if active_jitter.size:
        low = -jitter_width / 2.0
        high = jitter_width / 2.0
        out_of_range = int(((active_jitter < low - 1e-9) | (active_jitter > high + 1e-9)).sum())
        rb.add(
            test_id="step10_jitter_range",
            test_name="Active-event jitter within configured width",
            metric_name="out_of_range_values",
            metric_value=out_of_range,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if out_of_range == 0 else "FAIL",
            notes=f"range=[{low:.3f}, {high:.3f}]",
        )

    inactive_nonzero = int((np.abs(inactive_jitter) > 1e-12).sum()) if inactive_jitter.size else 0
    rb.add(
        test_id="step10_inactive_jitter_zero",
        test_name="Inactive events have zero daq_jitter_ns",
        metric_name="nonzero_values",
        metric_value=inactive_nonzero,
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if inactive_nonzero == 0 else "FAIL",
    )

    delta_t_list: list[np.ndarray] = []
    noise_list: list[np.ndarray] = []
    for i in range(1, 5):
        for j in range(1, 5):
            for side in ("front", "back"):
                c10 = f"T_{side}_{i}_s{j}_10"
                c9 = f"T_{side}_{i}_s{j}_9"
                if c10 not in merged.columns or c9 not in merged.columns:
                    continue
                t10 = merged[c10].to_numpy(dtype=float)
                t9 = merged[c9].to_numpy(dtype=float)
                mask = np.isfinite(t10) & np.isfinite(t9) & active
                if mask.any():
                    delta = t10[mask] - t9[mask]
                    delta_t_list.append(delta)
                    noise_list.append(delta - jitter[mask])

    delta_t = np.concatenate(delta_t_list) if delta_t_list else np.array([])
    noise = np.concatenate(noise_list) if noise_list else np.array([])

    if noise.size > 100:
        noise_std = float(np.std(noise, ddof=1))
        noise_mean = float(np.mean(noise))
        std_rel = abs(noise_std - tdc_sigma) / tdc_sigma if tdc_sigma > 0 else np.inf
        std_status = "PASS" if std_rel <= 0.25 else ("WARN" if std_rel <= 0.5 else "FAIL")
        mean_status = "PASS" if abs(noise_mean) <= max(3 * tdc_sigma / np.sqrt(noise.size), 1e-3) else "WARN"

        rb.add(
            test_id="step10_tdc_sigma_closure",
            test_name="(T10-T9-jitter) std matches tdc_sigma",
            metric_name="observed_std_ns",
            metric_value=noise_std,
            expected_value=tdc_sigma,
            threshold_low=tdc_sigma * 0.75,
            threshold_high=tdc_sigma * 1.25,
            status=std_status,
            notes=f"N={noise.size}",
        )

        rb.add(
            test_id="step10_tdc_noise_mean",
            test_name="(T10-T9-jitter) mean near zero",
            metric_name="observed_mean_ns",
            metric_value=noise_mean,
            expected_value=0.0,
            status=mean_status,
            notes=f"N={noise.size}",
        )

    if delta_t.size > 100:
        obs_std = float(np.std(delta_t, ddof=1))
        expected_std = float(np.sqrt(tdc_sigma**2 + (jitter_width**2) / 12.0))
        rel = abs(obs_std - expected_std) / expected_std if expected_std > 0 else np.inf
        status = "PASS" if rel <= 0.25 else ("WARN" if rel <= 0.5 else "FAIL")
        rb.add(
            test_id="step10_variance_addition",
            test_name="Total timing variance follows sigma^2 + width^2/12",
            metric_name="observed_std_ns",
            metric_value=obs_std,
            expected_value=expected_std,
            threshold_low=expected_std * 0.75,
            threshold_high=expected_std * 1.25,
            status=status,
            notes=f"N={delta_t.size}",
        )

    if make_plots:
        _plot(active_jitter, noise, delta_t, output_dir / "plots" / "validate_step10_tdc")

    return rb.to_frame().reindex(columns=RESULT_COLUMNS)
