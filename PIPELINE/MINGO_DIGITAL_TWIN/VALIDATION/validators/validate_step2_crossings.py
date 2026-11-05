#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/validators/validate_step2_crossings.py
Purpose: Validator for STEP 2 plane crossing outputs.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/validators/validate_step2_crossings.py [options]
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


def _norm_tt(value: object) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    text = str(value).strip().replace(".0", "")
    if text in {"", "nan", "None", "<NA>"}:
        return ""
    return "".join(ch for ch in text if ch in "1234")


def _plot(df: pd.DataFrame, plot_dir: Path) -> None:
    plot_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8))

    counts = df["tt_crossing"].astype("string").fillna("").value_counts().sort_index()
    axes[0, 0].bar(counts.index.astype(str), counts.values, color="steelblue", alpha=0.8)
    axes[0, 0].set_title("tt_crossing")

    t_cols = [f"T_sum_{i}_ns" for i in range(1, 5) if f"T_sum_{i}_ns" in df.columns]
    vals = df[t_cols].to_numpy(dtype=float).ravel() if t_cols else np.array([])
    vals = vals[np.isfinite(vals)]
    axes[0, 1].hist(vals, bins=80, color="darkorange", alpha=0.8)
    axes[0, 1].set_title("T_sum_i_ns")

    x_cols = [f"X_gen_{i}" for i in range(1, 5) if f"X_gen_{i}" in df.columns]
    y_cols = [f"Y_gen_{i}" for i in range(1, 5) if f"Y_gen_{i}" in df.columns]
    xv = df[x_cols].to_numpy(dtype=float).ravel() if x_cols else np.array([])
    yv = df[y_cols].to_numpy(dtype=float).ravel() if y_cols else np.array([])
    mask = np.isfinite(xv) & np.isfinite(yv)
    axes[1, 0].scatter(xv[mask], yv[mask], s=1, alpha=0.2, rasterized=True)
    axes[1, 0].set_title("Crossing XY")

    mins = []
    for _, row in df.iterrows():
        ts = [row.get(f"T_sum_{i}_ns") for i in range(1, 5)]
        ts = [t for t in ts if pd.notna(t)]
        if ts:
            mins.append(min(ts))
    axes[1, 1].hist(mins, bins=80, color="seagreen", alpha=0.8)
    axes[1, 1].set_title("min T_sum per event")

    fig.tight_layout()
    fig.savefig(plot_dir / "step2_crossing_overview.png", dpi=140)
    plt.close(fig)


def run(
    artifacts: dict[str, StepArtifact],
    run_timestamp: str,
    output_dir: Path,
    make_plots: bool = False,
) -> pd.DataFrame:
    art = artifacts.get("2")
    rb = ResultBuilder(
        run_timestamp=run_timestamp,
        validator="validate_step2_crossings",
        step="2",
        sim_run=art.sim_run if art else None,
        config_hash=art.config_hash if art else None,
        upstream_hash=art.upstream_hash if art else None,
        n_rows_in=art.row_count if art else None,
        n_rows_out=art.row_count if art else None,
    )

    if art is None or art.data_path is None or not art.data_path.exists():
        rb.add(
            test_id="step2_exists",
            test_name="STEP 2 output exists",
            metric_name="step2_exists",
            metric_value=0,
            status="SKIP",
            notes="No STEP 2 dataset found",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    cols = ["event_id", "tt_crossing", "crossing_mask"]
    for i in range(1, 5):
        cols.extend([f"X_gen_{i}", f"Y_gen_{i}", f"Z_gen_{i}", f"T_sum_{i}_ns"])

    try:
        df = load_frame(art.data_path, columns=cols)
    except Exception as exc:
        rb.add_exception(test_id="step2_read", test_name="Read STEP 2", exc=exc)
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    if df.empty:
        rb.add(
            test_id="step2_non_empty",
            test_name="STEP 2 has rows",
            metric_name="rows",
            metric_value=0,
            status="FAIL",
            notes="No rows read from STEP 2",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    rb.add(
        test_id="step2_rows",
        test_name="STEP 2 row count",
        metric_name="rows",
        metric_value=len(df),
        status="PASS",
    )

    required = set(cols) - {"crossing_mask"}
    missing = sorted(required - set(df.columns))
    rb.add(
        test_id="step2_required_columns",
        test_name="Required STEP 2 columns",
        metric_name="missing_columns",
        metric_value=len(missing),
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if not missing else "FAIL",
        notes=", ".join(missing),
    )

    cfg = art.metadata.get("config") or {}
    active_area_bounds = (
        art.metadata.get("active_area_bounds_mm")
        or cfg.get("active_area_bounds_mm")
        or cfg.get("bounds_mm")
        or {}
    )
    z_positions = cfg.get("z_positions") or cfg.get("z_positions_mm") or cfg.get("z_positions_raw_mm")
    c_mm_per_ns = float((cfg.get("c_mm_per_ns") or 299.792458))

    # tt_crossing consistency with valid planes.
    mismatch = 0
    crossing_mask_mismatch = 0
    min_t_nonzero = 0
    neg_dt = 0
    superluminal = 0
    for _, row in df.iterrows():
        valid_planes: list[int] = []
        zs: list[float] = []
        ts: list[float] = []
        for i in range(1, 5):
            x = row.get(f"X_gen_{i}")
            y = row.get(f"Y_gen_{i}")
            z = row.get(f"Z_gen_{i}")
            t = row.get(f"T_sum_{i}_ns")
            if pd.notna(x) and pd.notna(y):
                valid_planes.append(i)
            if pd.notna(z) and pd.notna(t):
                zs.append(float(z))
                ts.append(float(t))
        expected_tt = "".join(str(i) for i in valid_planes)
        actual_tt = _norm_tt(row.get("tt_crossing"))
        if expected_tt != actual_tt:
            mismatch += 1
        if "crossing_mask" in df.columns:
            expected_mask = sum(1 << (plane - 1) for plane in valid_planes)
            actual_mask = pd.to_numeric(
                pd.Series([row.get("crossing_mask")]), errors="coerce",
            ).iloc[0]
            if pd.isna(actual_mask) or int(actual_mask) != expected_mask:
                crossing_mask_mismatch += 1

        if ts:
            min_t = float(np.min(ts))
            if abs(min_t) > 1e-6:
                min_t_nonzero += 1

        if len(zs) >= 2:
            order = np.argsort(zs)
            z_arr = np.asarray(zs)[order]
            t_arr = np.asarray(ts)[order]
            dz = np.diff(z_arr)
            dt = np.diff(t_arr)
            neg_dt += int(((dz > 0) & (dt < -1e-6)).sum())
            valid_speed = (dz > 0) & (dt > 0)
            if valid_speed.any():
                speed = dz[valid_speed] / dt[valid_speed]
                superluminal += int((speed > c_mm_per_ns * 1.05).sum())

    rb.add(
        test_id="step2_tt_consistency",
        test_name="tt_crossing matches valid planes",
        metric_name="mismatch_rows",
        metric_value=mismatch,
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if mismatch == 0 else "FAIL",
    )

    rb.add(
        test_id="step2_crossing_mask_consistency",
        test_name="crossing_mask matches valid planes",
        metric_name="mismatch_rows",
        metric_value=crossing_mask_mismatch if "crossing_mask" in df.columns else np.nan,
        expected_value=0,
        status=(
            "PASS" if "crossing_mask" in df.columns and crossing_mask_mismatch == 0
            else "FAIL" if "crossing_mask" in df.columns
            else "SKIP"
        ),
        notes="Legacy STEP 2 outputs may not contain crossing_mask.",
    )

    rb.add(
        test_id="step2_tsum_min_zero",
        test_name="T_sum min is zero (per event)",
        metric_name="rows_with_nonzero_min",
        metric_value=min_t_nonzero,
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if min_t_nonzero == 0 else "WARN",
    )

    rb.add(
        test_id="step2_time_monotonic",
        test_name="Times increase with z",
        metric_name="negative_dt_segments",
        metric_value=neg_dt,
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if neg_dt == 0 else "FAIL",
    )

    rb.add(
        test_id="step2_speed_limit",
        test_name="No superluminal segment speeds",
        metric_name="superluminal_segments",
        metric_value=superluminal,
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if superluminal == 0 else "FAIL",
        notes=f"c={c_mm_per_ns:.6f} mm/ns",
    )

    if active_area_bounds:
        x_min = float(active_area_bounds.get("x_min", -np.inf))
        x_max = float(active_area_bounds.get("x_max", np.inf))
        y_min = float(active_area_bounds.get("y_min", -np.inf))
        y_max = float(active_area_bounds.get("y_max", np.inf))
        x_bad = 0
        y_bad = 0
        for i in range(1, 5):
            xv = df[f"X_gen_{i}"].to_numpy(dtype=float)
            yv = df[f"Y_gen_{i}"].to_numpy(dtype=float)
            x_bad += int(((xv < x_min) | (xv > x_max)).sum())
            y_bad += int(((yv < y_min) | (yv > y_max)).sum())
        rb.add(
            test_id="step2_bounds_x",
            test_name="X crossings inside active area",
            metric_name="out_of_bounds_values",
            metric_value=x_bad,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if x_bad == 0 else "FAIL",
            notes=f"[{x_min}, {x_max}]",
        )
        rb.add(
            test_id="step2_bounds_y",
            test_name="Y crossings inside active area",
            metric_name="out_of_bounds_values",
            metric_value=y_bad,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if y_bad == 0 else "FAIL",
            notes=f"[{y_min}, {y_max}]",
        )

    if isinstance(z_positions, list) and len(z_positions) == 4:
        z_bad = 0
        max_res = 0.0
        for i in range(1, 5):
            z_expected = float(z_positions[i - 1])
            zv = df[f"Z_gen_{i}"].to_numpy(dtype=float)
            mask = np.isfinite(zv)
            if mask.any():
                res = np.abs(zv[mask] - z_expected)
                max_res = max(max_res, float(np.max(res)))
                z_bad += int((res > 1e-9).sum())
        rb.add(
            test_id="step2_z_plane_residual",
            test_name="Z_gen matches configured z positions",
            metric_name="bad_z_values",
            metric_value=z_bad,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if z_bad == 0 else "FAIL",
            notes=f"max_abs_residual={max_res:.3e} mm",
        )

    if make_plots:
        _plot(df, output_dir / "plots" / "validate_step2_crossings")

    return rb.to_frame().reindex(columns=RESULT_COLUMNS)
