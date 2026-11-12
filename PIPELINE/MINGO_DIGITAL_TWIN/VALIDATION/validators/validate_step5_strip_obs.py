#!/usr/bin/env python3

"""Validator for STEP 5 strip observables (T_diff and q_diff)."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .common_io import StepArtifact, load_frame
from .common_report import RESULT_COLUMNS, ResultBuilder


def _find_c_mm_per_ns(meta: dict) -> float:
    current = meta
    while isinstance(current, dict):
        cfg = current.get("config")
        if isinstance(cfg, dict) and "c_mm_per_ns" in cfg:
            return float(cfg["c_mm_per_ns"])
        current = current.get("upstream")
    return 299.792458


def _plot(res_t: np.ndarray, norm_q: np.ndarray, plot_dir: Path) -> None:
    plot_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))

    if res_t.size:
        axes[0].hist(res_t, bins=80, color="steelblue", alpha=0.8)
    axes[0].set_title("T_diff residual (obs-pred)")

    if norm_q.size:
        clip = np.clip(norm_q, -6, 6)
        axes[1].hist(clip, bins=80, color="darkorange", alpha=0.8)
    axes[1].set_title("q_diff normalized (clipped)")

    fig.tight_layout()
    fig.savefig(plot_dir / "step5_observables.png", dpi=140)
    plt.close(fig)


def run(
    artifacts: dict[str, StepArtifact],
    run_timestamp: str,
    output_dir: Path,
    make_plots: bool = False,
) -> pd.DataFrame:
    art5 = artifacts.get("5")
    art4 = artifacts.get("4")
    rb = ResultBuilder(
        run_timestamp=run_timestamp,
        validator="validate_step5_strip_obs",
        step="5",
        sim_run=art5.sim_run if art5 else None,
        config_hash=art5.config_hash if art5 else None,
        upstream_hash=art5.upstream_hash if art5 else None,
        n_rows_in=art5.row_count if art5 else None,
        n_rows_out=art5.row_count if art5 else None,
    )

    if art5 is None or art5.data_path is None or not art5.data_path.exists():
        rb.add(
            test_id="step5_exists",
            test_name="STEP 5 output exists",
            metric_name="step5_exists",
            metric_value=0,
            status="SKIP",
            notes="No STEP 5 dataset found",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    cols5 = ["event_id"]
    for i in range(1, 5):
        for j in range(1, 5):
            cols5.extend([f"Y_mea_{i}_s{j}", f"T_diff_{i}_s{j}", f"q_diff_{i}_s{j}", f"T_sum_meas_{i}_s{j}"])

    try:
        df5 = load_frame(art5.data_path, columns=cols5)
    except Exception as exc:
        rb.add_exception(test_id="step5_read", test_name="Read STEP 5", exc=exc)
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    if df5.empty:
        rb.add(
            test_id="step5_non_empty",
            test_name="STEP 5 has rows",
            metric_name="rows",
            metric_value=0,
            status="FAIL",
            notes="No rows read from STEP 5",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    rb.add(
        test_id="step5_rows",
        test_name="STEP 5 row count",
        metric_name="rows",
        metric_value=len(df5),
        status="PASS",
    )

    cfg = art5.metadata.get("config") or {}
    qdiff_width_raw = cfg.get("qdiff_width")
    if qdiff_width_raw in (None, ""):
        rb.add(
            test_id="step5_qdiff_width_configured",
            test_name="STEP 5 qdiff_width configured",
            metric_name="qdiff_width_configured",
            metric_value=0,
            status="FAIL",
            notes="STEP 5 metadata is missing qdiff_width.",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)
    qdiff_width = float(qdiff_width_raw)
    c_mm_per_ns = _find_c_mm_per_ns(art5.metadata)
    x_to_time = 3.0 / (2.0 * c_mm_per_ns)

    zero_qdiff_viol = 0
    norm_q_list: list[np.ndarray] = []
    for i in range(1, 5):
        for j in range(1, 5):
            y_col = f"Y_mea_{i}_s{j}"
            q_col = f"q_diff_{i}_s{j}"
            if y_col not in df5.columns or q_col not in df5.columns:
                continue
            yv = df5[y_col].to_numpy(dtype=float)
            qv = df5[q_col].to_numpy(dtype=float)
            zero_qdiff_viol += int(((yv <= 0) & (np.abs(qv) > 1e-12)).sum())
            pos = yv > 0
            if pos.any() and qdiff_width > 0:
                denom = np.full(pos.sum(), qdiff_width, dtype=float)
                good = np.abs(denom) > 0
                if good.any():
                    norm_q = qv[pos][good] / denom[good]
                    norm_q = norm_q[np.isfinite(norm_q)]
                    if norm_q.size:
                        norm_q_list.append(norm_q)

    rb.add(
        test_id="step5_qdiff_zero_when_no_charge",
        test_name="q_diff is zero when Y_mea <= 0",
        metric_name="violations",
        metric_value=zero_qdiff_viol,
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if zero_qdiff_viol == 0 else "FAIL",
    )

    norm_q_all = np.concatenate(norm_q_list) if norm_q_list else np.array([])
    if norm_q_all.size > 100:
        mean_norm = float(np.mean(norm_q_all))
        std_norm = float(np.std(norm_q_all, ddof=1)) if norm_q_all.size > 1 else np.nan

        mean_status = "PASS" if abs(mean_norm) <= 0.05 else ("WARN" if abs(mean_norm) <= 0.1 else "FAIL")
        std_status = "PASS" if 0.9 <= std_norm <= 1.1 else ("WARN" if 0.7 <= std_norm <= 1.3 else "FAIL")

        rb.add(
            test_id="step5_qdiff_norm_mean",
            test_name="Normalized q_diff mean near 0",
            metric_name="mean",
            metric_value=mean_norm,
            expected_value=0.0,
            threshold_low=-0.05,
            threshold_high=0.05,
            status=mean_status,
            notes=f"N={norm_q_all.size}",
        )
        rb.add(
            test_id="step5_qdiff_norm_std",
            test_name="Normalized q_diff std near 1",
            metric_name="std",
            metric_value=std_norm,
            expected_value=1.0,
            threshold_low=0.9,
            threshold_high=1.1,
            status=std_status,
            notes=f"N={norm_q_all.size}",
        )

    # T_diff closure vs X_mea from STEP 4.
    residuals = np.array([])
    if art4 is None or art4.data_path is None or not art4.data_path.exists():
        rb.add(
            test_id="step5_tdiff_inputs",
            test_name="STEP 4 inputs available for T_diff closure",
            metric_name="step4_available",
            metric_value=0,
            status="SKIP",
            notes="STEP 4 dataset unavailable",
        )
    else:
        cols4 = ["event_id"] + [f"X_mea_{i}_s{j}" for i in range(1, 5) for j in range(1, 5)]
        try:
            df4 = load_frame(art4.data_path, columns=cols4)
            merged = df5.merge(df4, on="event_id", how="inner")
        except Exception as exc:
            rb.add_exception(test_id="step5_tdiff_merge", test_name="Merge STEP 5 with STEP 4", exc=exc)
            merged = pd.DataFrame()

        if merged.empty:
            rb.add(
                test_id="step5_tdiff_merge_empty",
                test_name="STEP 4/5 merge has rows",
                metric_name="merged_rows",
                metric_value=0,
                status="SKIP",
                notes="No common rows on event_id",
            )
        else:
            res_chunks: list[np.ndarray] = []
            for i in range(1, 5):
                for j in range(1, 5):
                    t_col = f"T_diff_{i}_s{j}"
                    x_col = f"X_mea_{i}_s{j}"
                    if t_col not in merged.columns or x_col not in merged.columns:
                        continue
                    tv = merged[t_col].to_numpy(dtype=float)
                    xv = merged[x_col].to_numpy(dtype=float)
                    pred = xv * x_to_time
                    mask = np.isfinite(tv) & np.isfinite(pred)
                    if mask.any():
                        res_chunks.append(tv[mask] - pred[mask])
            residuals = np.concatenate(res_chunks) if res_chunks else np.array([])

            if residuals.size:
                max_abs = float(np.max(np.abs(residuals)))
                rmse = float(np.sqrt(np.mean(residuals**2)))
                status = "PASS" if max_abs <= 1e-6 else ("WARN" if max_abs <= 1e-4 else "FAIL")
                rb.add(
                    test_id="step5_tdiff_identity",
                    test_name="T_diff equals X_mea * 3/(2c)",
                    metric_name="max_abs_residual_ns",
                    metric_value=max_abs,
                    expected_value=0.0,
                    threshold_low=0.0,
                    threshold_high=1e-6,
                    status=status,
                    notes=f"rmse={rmse:.3e}, N={residuals.size}",
                )

    if make_plots:
        _plot(residuals, norm_q_all, output_dir / "plots" / "validate_step5_strip_obs")

    return rb.to_frame().reindex(columns=RESULT_COLUMNS)
