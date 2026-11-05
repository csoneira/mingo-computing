#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/validators/validate_step8_fee.py
Purpose: Validator for STEP 8 front-end electronics behavior.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/validators/validate_step8_fee.py [options]
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


def _plot(delta_t: np.ndarray, expected_q: np.ndarray, observed_q: np.ndarray, plot_dir: Path) -> None:
    plot_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    if delta_t.size:
        axes[0].hist(delta_t, bins=100, color="steelblue", alpha=0.8)
    axes[0].set_title("STEP8-STEP7 time deltas")

    if expected_q.size and observed_q.size:
        n = min(expected_q.size, observed_q.size)
        take = min(n, 40000)
        idx = np.linspace(0, n - 1, take, dtype=int)
        axes[1].scatter(expected_q[idx], observed_q[idx], s=2, alpha=0.25, rasterized=True)
        minv = float(np.nanmin(expected_q[idx])) if take else 0.0
        maxv = float(np.nanmax(expected_q[idx])) if take else 1.0
        axes[1].plot([minv, maxv], [minv, maxv], color="black", linewidth=1)
    axes[1].set_title("Expected vs observed Q after FEE")
    axes[1].set_xlabel("expected")
    axes[1].set_ylabel("observed")

    fig.tight_layout()
    fig.savefig(plot_dir / "step8_fee_checks.png", dpi=140)
    plt.close(fig)


def run(
    artifacts: dict[str, StepArtifact],
    run_timestamp: str,
    output_dir: Path,
    make_plots: bool = False,
) -> pd.DataFrame:
    art8 = artifacts.get("8")
    art7 = artifacts.get("7")
    rb = ResultBuilder(
        run_timestamp=run_timestamp,
        validator="validate_step8_fee",
        step="8",
        sim_run=art8.sim_run if art8 else None,
        config_hash=art8.config_hash if art8 else None,
        upstream_hash=art8.upstream_hash if art8 else None,
        n_rows_in=art8.row_count if art8 else None,
        n_rows_out=art8.row_count if art8 else None,
    )

    if art8 is None or art8.data_path is None or not art8.data_path.exists():
        rb.add(
            test_id="step8_exists",
            test_name="STEP 8 output exists",
            metric_name="step8_exists",
            metric_value=0,
            status="SKIP",
            notes="No STEP 8 dataset found",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    if art7 is None or art7.data_path is None or not art7.data_path.exists():
        rb.add(
            test_id="step8_inputs",
            test_name="STEP 7 inputs available",
            metric_name="step7_available",
            metric_value=0,
            status="SKIP",
            notes="No STEP 7 dataset found",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    cols = ["event_id"]
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
        df8 = load_frame(art8.data_path, columns=cols)
        df7 = load_frame(art7.data_path, columns=cols)
        merged = df8.merge(df7, on="event_id", suffixes=("_8", "_7"), how="inner")
    except Exception as exc:
        rb.add_exception(test_id="step8_read_merge", test_name="Read/merge STEP 7 and STEP 8", exc=exc)
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    if merged.empty:
        rb.add(
            test_id="step8_merge_non_empty",
            test_name="STEP 7/8 merge has rows",
            metric_name="merged_rows",
            metric_value=0,
            status="SKIP",
            notes="No common event_id rows",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    cfg = art8.metadata.get("config") or {}
    threshold = float(cfg.get("charge_threshold", 0.01))
    t_fee_sigma = float(cfg.get("t_fee_sigma_ns", 0.03))
    q_to_time = float(cfg.get("q_to_time_factor", 1e-5))
    qfront_offsets = np.asarray(cfg.get("qfront_offsets", [[0] * 4] * 4), dtype=float)
    qback_offsets = np.asarray(cfg.get("qback_offsets", [[0] * 4] * 4), dtype=float)

    delta_t_list: list[np.ndarray] = []
    expected_q_collect: list[np.ndarray] = []
    observed_q_collect: list[np.ndarray] = []

    below_thr_not_zero = 0
    above_thr_mismatch = 0
    q_nonzero_below_thr = 0

    for i in range(1, 5):
        for j in range(1, 5):
            for side in ("front", "back"):
                t8 = f"T_{side}_{i}_s{j}_8"
                t7 = f"T_{side}_{i}_s{j}_7"
                q8 = f"Q_{side}_{i}_s{j}_8"
                q7 = f"Q_{side}_{i}_s{j}_7"
                if t8 in merged.columns and t7 in merged.columns:
                    v8 = merged[t8].to_numpy(dtype=float)
                    v7 = merged[t7].to_numpy(dtype=float)
                    mask = np.isfinite(v8) & np.isfinite(v7)
                    if mask.any():
                        delta_t_list.append(v8[mask] - v7[mask])

                if q8 not in merged.columns or q7 not in merged.columns:
                    continue

                q8v = merged[q8].to_numpy(dtype=float)
                q7v = merged[q7].to_numpy(dtype=float)
                nonzero_mask = q7v != 0
                if not nonzero_mask.any():
                    continue

                if side == "front" and qfront_offsets.shape == (4, 4):
                    offset = float(qfront_offsets[i - 1, j - 1])
                elif side == "back" and qback_offsets.shape == (4, 4):
                    offset = float(qback_offsets[i - 1, j - 1])
                else:
                    offset = 0.0

                expected = q7v[nonzero_mask] * q_to_time + offset
                observed = q8v[nonzero_mask]
                expected_q_collect.append(expected)
                observed_q_collect.append(observed)

                below = expected < threshold
                above = ~below
                if below.any():
                    below_thr_not_zero += int((np.abs(observed[below]) > 1e-12).sum())
                if above.any():
                    above_thr_mismatch += int((np.abs(observed[above] - expected[above]) > 1e-9).sum())

                q_nonzero_below_thr += int(((observed > 0) & (observed < threshold - 1e-12)).sum())

    delta_t = np.concatenate(delta_t_list) if delta_t_list else np.array([])
    expected_q = np.concatenate(expected_q_collect) if expected_q_collect else np.array([])
    observed_q = np.concatenate(observed_q_collect) if observed_q_collect else np.array([])

    rb.add(
        test_id="step8_threshold_below_to_zero",
        test_name="Expected sub-threshold charges are suppressed",
        metric_name="violations",
        metric_value=below_thr_not_zero,
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if below_thr_not_zero == 0 else "FAIL",
    )

    rb.add(
        test_id="step8_q_transform_above_threshold",
        test_name="Above-threshold charges match transformed expectation",
        metric_name="violations",
        metric_value=above_thr_mismatch,
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if above_thr_mismatch == 0 else "FAIL",
    )

    rb.add(
        test_id="step8_nonzero_q_meets_threshold",
        test_name="All nonzero Q values are >= threshold",
        metric_name="violations",
        metric_value=q_nonzero_below_thr,
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if q_nonzero_below_thr == 0 else "FAIL",
    )

    if delta_t.size > 100:
        obs_std = float(np.std(delta_t, ddof=1))
        rel = abs(obs_std - t_fee_sigma) / t_fee_sigma if t_fee_sigma > 0 else np.inf
        status = "PASS" if rel <= 0.2 else ("WARN" if rel <= 0.4 else "FAIL")
        rb.add(
            test_id="step8_timing_jitter_rms",
            test_name="Timing jitter RMS matches t_fee_sigma_ns",
            metric_name="observed_std_ns",
            metric_value=obs_std,
            expected_value=t_fee_sigma,
            threshold_low=t_fee_sigma * 0.8,
            threshold_high=t_fee_sigma * 1.2,
            status=status,
            notes=f"N={delta_t.size}",
        )

    if expected_q.size and observed_q.size:
        corr = float(np.corrcoef(expected_q, observed_q)[0, 1]) if expected_q.size > 2 else np.nan
        rb.add(
            test_id="step8_expected_observed_corr",
            test_name="Expected/observed FEE charge correlation",
            metric_name="pearson_r",
            metric_value=corr,
            expected_value=1.0,
            threshold_low=0.99,
            threshold_high=1.0,
            status="PASS" if np.isfinite(corr) and corr >= 0.999 else ("WARN" if np.isfinite(corr) and corr >= 0.99 else "FAIL"),
            notes=f"N={expected_q.size}",
        )

    if make_plots:
        _plot(delta_t, expected_q, observed_q, output_dir / "plots" / "validate_step8_fee")

    return rb.to_frame().reindex(columns=RESULT_COLUMNS)
