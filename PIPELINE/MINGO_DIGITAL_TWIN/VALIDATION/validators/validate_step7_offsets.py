#!/usr/bin/env python3

"""Validator for STEP 7 cable/offset application."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .common_io import StepArtifact, load_frame
from .common_report import RESULT_COLUMNS, ResultBuilder


def _plot(front_means: np.ndarray, back_means: np.ndarray, plot_dir: Path) -> None:
    plot_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    im0 = axes[0].imshow(front_means, cmap="coolwarm", aspect="auto")
    axes[0].set_title("Observed front offsets")
    axes[0].set_xlabel("Strip")
    axes[0].set_ylabel("Plane")
    fig.colorbar(im0, ax=axes[0], fraction=0.046)

    im1 = axes[1].imshow(back_means, cmap="coolwarm", aspect="auto")
    axes[1].set_title("Observed back offsets")
    axes[1].set_xlabel("Strip")
    axes[1].set_ylabel("Plane")
    fig.colorbar(im1, ax=axes[1], fraction=0.046)

    fig.tight_layout()
    fig.savefig(plot_dir / "step7_observed_offsets.png", dpi=140)
    plt.close(fig)


def run(
    artifacts: dict[str, StepArtifact],
    run_timestamp: str,
    output_dir: Path,
    make_plots: bool = False,
) -> pd.DataFrame:
    art7 = artifacts.get("7")
    art6 = artifacts.get("6")
    rb = ResultBuilder(
        run_timestamp=run_timestamp,
        validator="validate_step7_offsets",
        step="7",
        sim_run=art7.sim_run if art7 else None,
        config_hash=art7.config_hash if art7 else None,
        upstream_hash=art7.upstream_hash if art7 else None,
        n_rows_in=art7.row_count if art7 else None,
        n_rows_out=art7.row_count if art7 else None,
    )

    if art7 is None or art7.data_path is None or not art7.data_path.exists():
        rb.add(
            test_id="step7_exists",
            test_name="STEP 7 output exists",
            metric_name="step7_exists",
            metric_value=0,
            status="SKIP",
            notes="No STEP 7 dataset found",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    if art6 is None or art6.data_path is None or not art6.data_path.exists():
        rb.add(
            test_id="step7_inputs",
            test_name="STEP 6 inputs available",
            metric_name="step6_available",
            metric_value=0,
            status="SKIP",
            notes="No STEP 6 dataset found",
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
        df7 = load_frame(art7.data_path, columns=cols)
        df6 = load_frame(art6.data_path, columns=cols)
        merged = df7.merge(df6, on="event_id", suffixes=("_7", "_6"), how="inner")
    except Exception as exc:
        rb.add_exception(test_id="step7_read_merge", test_name="Read/merge STEP 6 and STEP 7", exc=exc)
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    if merged.empty:
        rb.add(
            test_id="step7_merge_non_empty",
            test_name="STEP 6/7 merge has rows",
            metric_name="merged_rows",
            metric_value=0,
            status="SKIP",
            notes="No common event_id rows",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    cfg = art7.metadata.get("config") or {}
    tfront_offsets = np.asarray(cfg.get("tfront_offsets", [[0] * 4] * 4), dtype=float)
    tback_offsets = np.asarray(cfg.get("tback_offsets", [[0] * 4] * 4), dtype=float)

    charge_diffs = []
    front_abs_err = []
    back_abs_err = []
    front_std = []
    back_std = []
    front_means = np.full((4, 4), np.nan, dtype=float)
    back_means = np.full((4, 4), np.nan, dtype=float)

    for i in range(1, 5):
        for j in range(1, 5):
            # Charge invariance.
            for prefix in ("Q_front", "Q_back"):
                c7 = f"{prefix}_{i}_s{j}_7"
                c6 = f"{prefix}_{i}_s{j}_6"
                if c7 in merged.columns and c6 in merged.columns:
                    q7 = merged[c7].to_numpy(dtype=float)
                    q6 = merged[c6].to_numpy(dtype=float)
                    mask = np.isfinite(q7) & np.isfinite(q6)
                    if mask.any():
                        charge_diffs.append(q7[mask] - q6[mask])

            tf7 = f"T_front_{i}_s{j}_7"
            tf6 = f"T_front_{i}_s{j}_6"
            tb7 = f"T_back_{i}_s{j}_7"
            tb6 = f"T_back_{i}_s{j}_6"

            if tf7 in merged.columns and tf6 in merged.columns:
                v7 = merged[tf7].to_numpy(dtype=float)
                v6 = merged[tf6].to_numpy(dtype=float)
                mask = np.isfinite(v7) & np.isfinite(v6)
                if mask.any():
                    delta = v7[mask] - v6[mask]
                    exp = float(tfront_offsets[i - 1, j - 1]) if tfront_offsets.shape == (4, 4) else 0.0
                    front_abs_err.append(np.abs(delta - exp))
                    front_std.append(np.std(delta))
                    front_means[i - 1, j - 1] = float(np.mean(delta))

            if tb7 in merged.columns and tb6 in merged.columns:
                v7 = merged[tb7].to_numpy(dtype=float)
                v6 = merged[tb6].to_numpy(dtype=float)
                mask = np.isfinite(v7) & np.isfinite(v6)
                if mask.any():
                    delta = v7[mask] - v6[mask]
                    exp = float(tback_offsets[i - 1, j - 1]) if tback_offsets.shape == (4, 4) else 0.0
                    back_abs_err.append(np.abs(delta - exp))
                    back_std.append(np.std(delta))
                    back_means[i - 1, j - 1] = float(np.mean(delta))

    if charge_diffs:
        qdiff = np.concatenate(charge_diffs)
        max_abs_q = float(np.max(np.abs(qdiff)))
        rb.add(
            test_id="step7_charge_invariance",
            test_name="Charges unchanged from STEP 6",
            metric_name="max_abs_difference",
            metric_value=max_abs_q,
            expected_value=0.0,
            threshold_low=0.0,
            threshold_high=1e-9,
            status="PASS" if max_abs_q <= 1e-9 else "FAIL",
        )
    else:
        rb.add(
            test_id="step7_charge_invariance",
            test_name="Charges unchanged from STEP 6",
            metric_name="status",
            metric_value=np.nan,
            status="SKIP",
            notes="No finite charge values",
        )

    if front_abs_err:
        f_err = np.concatenate(front_abs_err)
        max_abs = float(np.max(f_err))
        status = "PASS" if max_abs <= 1e-6 else ("WARN" if max_abs <= 1e-4 else "FAIL")
        rb.add(
            test_id="step7_front_offset_match",
            test_name="Front timing offsets match config",
            metric_name="max_abs_error_ns",
            metric_value=max_abs,
            expected_value=0.0,
            threshold_low=0.0,
            threshold_high=1e-6,
            status=status,
        )

    if back_abs_err:
        b_err = np.concatenate(back_abs_err)
        max_abs = float(np.max(b_err))
        status = "PASS" if max_abs <= 1e-6 else ("WARN" if max_abs <= 1e-4 else "FAIL")
        rb.add(
            test_id="step7_back_offset_match",
            test_name="Back timing offsets match config",
            metric_name="max_abs_error_ns",
            metric_value=max_abs,
            expected_value=0.0,
            threshold_low=0.0,
            threshold_high=1e-6,
            status=status,
        )

    if front_std:
        max_std = float(np.max(front_std))
        rb.add(
            test_id="step7_front_offset_stationarity",
            test_name="Front offsets are stationary per channel",
            metric_name="max_channel_std_ns",
            metric_value=max_std,
            expected_value=0.0,
            threshold_low=0.0,
            threshold_high=1e-6,
            status="PASS" if max_std <= 1e-6 else "WARN",
        )

    if back_std:
        max_std = float(np.max(back_std))
        rb.add(
            test_id="step7_back_offset_stationarity",
            test_name="Back offsets are stationary per channel",
            metric_name="max_channel_std_ns",
            metric_value=max_std,
            expected_value=0.0,
            threshold_low=0.0,
            threshold_high=1e-6,
            status="PASS" if max_std <= 1e-6 else "WARN",
        )

    if make_plots:
        _plot(front_means, back_means, output_dir / "plots" / "validate_step7_offsets")

    return rb.to_frame().reindex(columns=RESULT_COLUMNS)
