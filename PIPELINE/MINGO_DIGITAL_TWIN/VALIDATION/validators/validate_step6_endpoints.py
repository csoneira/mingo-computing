#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/validators/validate_step6_endpoints.py
Purpose: Validator for STEP 6 front/back endpoint construction.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/validators/validate_step6_endpoints.py [options]
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


def _plot(residual_sets: dict[str, np.ndarray], plot_dir: Path) -> None:
    plot_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    keys = [
        "t_sum_closure",
        "t_diff_closure",
        "q_sum_closure",
        "q_diff_closure",
    ]
    titles = {
        "t_sum_closure": "(T_front+T_back)-2*T_sum",
        "t_diff_closure": "(T_back-T_front)-2*T_diff",
        "q_sum_closure": "(Q_front+Q_back)-2*Y",
        "q_diff_closure": "(Q_back-Q_front)-2*q_diff",
    }
    for ax, key in zip(axes.flatten(), keys):
        vals = residual_sets.get(key, np.array([]))
        if vals.size:
            ax.hist(vals, bins=80, color="steelblue", alpha=0.8)
        ax.set_title(titles[key])

    fig.tight_layout()
    fig.savefig(plot_dir / "step6_closure_residuals.png", dpi=140)
    plt.close(fig)


def _status_from_max_abs(max_abs: float) -> str:
    if max_abs <= 1e-6:
        return "PASS"
    if max_abs <= 1e-4:
        return "WARN"
    return "FAIL"


def run(
    artifacts: dict[str, StepArtifact],
    run_timestamp: str,
    output_dir: Path,
    make_plots: bool = False,
) -> pd.DataFrame:
    art6 = artifacts.get("6")
    art5 = artifacts.get("5")
    rb = ResultBuilder(
        run_timestamp=run_timestamp,
        validator="validate_step6_endpoints",
        step="6",
        sim_run=art6.sim_run if art6 else None,
        config_hash=art6.config_hash if art6 else None,
        upstream_hash=art6.upstream_hash if art6 else None,
        n_rows_in=art6.row_count if art6 else None,
        n_rows_out=art6.row_count if art6 else None,
    )

    if art6 is None or art6.data_path is None or not art6.data_path.exists():
        rb.add(
            test_id="step6_exists",
            test_name="STEP 6 output exists",
            metric_name="step6_exists",
            metric_value=0,
            status="SKIP",
            notes="No STEP 6 dataset found",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    cols6 = ["event_id"]
    for i in range(1, 5):
        for j in range(1, 5):
            cols6.extend(
                [
                    f"T_front_{i}_s{j}",
                    f"T_back_{i}_s{j}",
                    f"Q_front_{i}_s{j}",
                    f"Q_back_{i}_s{j}",
                ]
            )

    try:
        df6 = load_frame(art6.data_path, columns=cols6)
    except Exception as exc:
        rb.add_exception(test_id="step6_read", test_name="Read STEP 6", exc=exc)
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    if df6.empty:
        rb.add(
            test_id="step6_non_empty",
            test_name="STEP 6 has rows",
            metric_name="rows",
            metric_value=0,
            status="FAIL",
            notes="No rows read from STEP 6",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    rb.add(
        test_id="step6_rows",
        test_name="STEP 6 row count",
        metric_name="rows",
        metric_value=len(df6),
        status="PASS",
    )

    if art5 is None or art5.data_path is None or not art5.data_path.exists():
        rb.add(
            test_id="step6_closure_inputs",
            test_name="STEP 5 inputs available for closure",
            metric_name="step5_available",
            metric_value=0,
            status="SKIP",
            notes="STEP 5 dataset unavailable",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    cols5 = ["event_id"]
    for i in range(1, 5):
        for j in range(1, 5):
            cols5.extend(
                [
                    f"T_sum_meas_{i}_s{j}",
                    f"T_diff_{i}_s{j}",
                    f"Y_mea_{i}_s{j}",
                    f"q_diff_{i}_s{j}",
                ]
            )

    try:
        df5 = load_frame(art5.data_path, columns=cols5)
        merged = df6.merge(df5, on="event_id", how="inner")
    except Exception as exc:
        rb.add_exception(test_id="step6_merge", test_name="Merge STEP 6 and STEP 5", exc=exc)
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    if merged.empty:
        rb.add(
            test_id="step6_merge_non_empty",
            test_name="STEP 6/5 merge has rows",
            metric_name="merged_rows",
            metric_value=0,
            status="SKIP",
            notes="No common event_id rows",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    residuals = {
        "t_sum_closure": [],
        "t_diff_closure": [],
        "q_sum_closure": [],
        "q_diff_closure": [],
    }

    nan_time_when_charge = 0

    for i in range(1, 5):
        for j in range(1, 5):
            tf = f"T_front_{i}_s{j}"
            tb = f"T_back_{i}_s{j}"
            qf = f"Q_front_{i}_s{j}"
            qb = f"Q_back_{i}_s{j}"
            tsum = f"T_sum_meas_{i}_s{j}"
            tdiff = f"T_diff_{i}_s{j}"
            y = f"Y_mea_{i}_s{j}"
            qdiff = f"q_diff_{i}_s{j}"

            needed = {tf, tb, qf, qb, tsum, tdiff, y, qdiff}
            if not needed.issubset(merged.columns):
                continue

            tf_v = merged[tf].to_numpy(dtype=float)
            tb_v = merged[tb].to_numpy(dtype=float)
            qf_v = merged[qf].to_numpy(dtype=float)
            qb_v = merged[qb].to_numpy(dtype=float)
            tsum_v = merged[tsum].to_numpy(dtype=float)
            tdiff_v = merged[tdiff].to_numpy(dtype=float)
            y_v = merged[y].to_numpy(dtype=float)
            qdiff_v = merged[qdiff].to_numpy(dtype=float)

            mask_t = np.isfinite(tf_v) & np.isfinite(tb_v) & np.isfinite(tsum_v) & np.isfinite(tdiff_v)
            if mask_t.any():
                residuals["t_sum_closure"].append((tf_v[mask_t] + tb_v[mask_t]) - 2.0 * tsum_v[mask_t])
                residuals["t_diff_closure"].append((tb_v[mask_t] - tf_v[mask_t]) - 2.0 * tdiff_v[mask_t])

            mask_q = np.isfinite(qf_v) & np.isfinite(qb_v) & np.isfinite(y_v) & np.isfinite(qdiff_v)
            if mask_q.any():
                residuals["q_sum_closure"].append((qf_v[mask_q] + qb_v[mask_q]) - 2.0 * y_v[mask_q])
                residuals["q_diff_closure"].append((qb_v[mask_q] - qf_v[mask_q]) - 2.0 * qdiff_v[mask_q])

            charge_pos = (qf_v > 0) | (qb_v > 0)
            nan_time_when_charge += int((charge_pos & (~np.isfinite(tf_v) | ~np.isfinite(tb_v))).sum())

    residual_arrays: dict[str, np.ndarray] = {}
    for key, chunks in residuals.items():
        residual_arrays[key] = np.concatenate(chunks) if chunks else np.array([])

    for key, values in residual_arrays.items():
        if values.size == 0:
            rb.add(
                test_id=f"step6_{key}",
                test_name=f"{key} identity",
                metric_name="n_values",
                metric_value=0,
                status="SKIP",
                notes="No finite values",
            )
            continue

        max_abs = float(np.max(np.abs(values)))
        rmse = float(np.sqrt(np.mean(values**2)))
        rb.add(
            test_id=f"step6_{key}",
            test_name=f"{key} identity",
            metric_name="max_abs_residual",
            metric_value=max_abs,
            expected_value=0.0,
            threshold_low=0.0,
            threshold_high=1e-6,
            status=_status_from_max_abs(max_abs),
            notes=f"rmse={rmse:.3e}, N={values.size}",
        )

    rb.add(
        test_id="step6_finite_times_for_active_channels",
        test_name="Finite times for channels with positive charge",
        metric_name="violations",
        metric_value=nan_time_when_charge,
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if nan_time_when_charge == 0 else "WARN",
    )

    if make_plots:
        _plot(residual_arrays, output_dir / "plots" / "validate_step6_endpoints")

    return rb.to_frame().reindex(columns=RESULT_COLUMNS)
