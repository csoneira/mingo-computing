#!/usr/bin/env python3

"""Validator for STEP 0 parameter mesh."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .common_io import StepArtifact
from .common_report import RESULT_COLUMNS, ResultBuilder


def _maybe_plot(df: pd.DataFrame, plot_dir: Path) -> None:
    plot_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    if "cos_n" in df.columns:
        axes[0, 0].hist(df["cos_n"].astype(float), bins=40, color="steelblue", alpha=0.8)
        axes[0, 0].set_title("cos_n")
    if "flux_cm2_min" in df.columns:
        axes[0, 1].hist(df["flux_cm2_min"].astype(float), bins=40, color="seagreen", alpha=0.8)
        axes[0, 1].set_title("flux_cm2_min")

    eff_cols = [c for c in df.columns if c.startswith("eff_p")]
    if eff_cols:
        vals = df[eff_cols].to_numpy(dtype=float).ravel()
        vals = vals[np.isfinite(vals)]
        axes[1, 0].hist(vals, bins=40, color="darkorange", alpha=0.8)
        axes[1, 0].set_title("eff_p*")

    z_cols = [c for c in df.columns if c.startswith("z_p")]
    if z_cols:
        vals = df[z_cols].to_numpy(dtype=float).ravel()
        vals = vals[np.isfinite(vals)]
        axes[1, 1].hist(vals, bins=40, color="slateblue", alpha=0.8)
        axes[1, 1].set_title("z_p*")

    fig.tight_layout()
    fig.savefig(plot_dir / "step0_mesh_overview.png", dpi=140)
    plt.close(fig)


def run(
    artifacts: dict[str, StepArtifact],
    run_timestamp: str,
    output_dir: Path,
    make_plots: bool = False,
) -> pd.DataFrame:
    art = artifacts.get("0")
    rb = ResultBuilder(
        run_timestamp=run_timestamp,
        validator="validate_step0_mesh",
        step="0",
        sim_run=art.sim_run if art else None,
        config_hash=art.config_hash if art else None,
        upstream_hash=art.upstream_hash if art else None,
        n_rows_in=None,
        n_rows_out=None,
    )

    if art is None or art.data_path is None or not art.data_path.exists():
        rb.add(
            test_id="step0_mesh_exists",
            test_name="STEP 0 mesh exists",
            metric_name="mesh_exists",
            metric_value=0,
            status="SKIP",
            notes="param_mesh.csv not found",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    try:
        df = pd.read_csv(art.data_path)
    except Exception as exc:
        rb.add_exception(test_id="step0_mesh_read", test_name="Read param mesh", exc=exc)
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    rb.n_rows_in = len(df)
    rb.n_rows_out = len(df)

    required = {
        "done",
        "step_1_id",
        "step_2_id",
        "step_3_id",
        "step_4_id",
        "step_5_id",
        "step_6_id",
        "step_7_id",
        "step_8_id",
        "step_9_id",
        "step_10_id",
        "cos_n",
        "flux_cm2_min",
        "eff_p1",
        "eff_p2",
        "eff_p3",
        "eff_p4",
        "z_p1",
        "z_p2",
        "z_p3",
        "z_p4",
    }
    missing = sorted(required - set(df.columns))
    rb.add(
        test_id="step0_required_columns",
        test_name="Required STEP 0 columns",
        metric_name="missing_columns",
        metric_value=len(missing),
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if not missing else "FAIL",
        notes=", ".join(missing) if missing else "",
    )

    if "done" in df.columns:
        bad_done = int((~df["done"].isin([0, 1])).sum())
        rb.add(
            test_id="step0_done_binary",
            test_name="done column is binary",
            metric_name="bad_done_values",
            metric_value=bad_done,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if bad_done == 0 else "FAIL",
        )

    id_cols = [f"step_{idx}_id" for idx in range(1, 11) if f"step_{idx}_id" in df.columns]
    non_numeric_id = 0
    for col in id_cols:
        as_text = df[col].astype(str)
        non_numeric_id += int((~as_text.str.fullmatch(r"\d{1,}")).sum())
    rb.add(
        test_id="step0_step_ids_numeric",
        test_name="step IDs are numeric",
        metric_name="non_numeric_id_values",
        metric_value=non_numeric_id,
        expected_value=0,
        threshold_low=0,
        threshold_high=0,
        status="PASS" if non_numeric_id == 0 else "WARN",
    )

    if "done" in df.columns:
        done_numeric = pd.to_numeric(df["done"], errors="coerce")
        done_mask = done_numeric == 1
        if not done_mask.any():
            rb.add(
                test_id="step0_done_rows_have_step_ids",
                test_name="Rows with done=1 have all step IDs populated",
                metric_name="status",
                metric_value=np.nan,
                status="SKIP",
                notes="No rows with done=1",
            )
        else:
            invalid_done_ids = 0
            missing_id_cols = []
            for idx in range(1, 11):
                col = f"step_{idx}_id"
                if col not in df.columns:
                    missing_id_cols.append(col)
                    invalid_done_ids += int(done_mask.sum())
                    continue
                vals = pd.to_numeric(df.loc[done_mask, col], errors="coerce")
                invalid_done_ids += int(vals.isna().sum())
            rb.add(
                test_id="step0_done_rows_have_step_ids",
                test_name="Rows with done=1 have all step IDs populated",
                metric_name="invalid_done_rows",
                metric_value=invalid_done_ids,
                expected_value=0,
                threshold_low=0,
                threshold_high=0,
                status="PASS" if invalid_done_ids == 0 else "FAIL",
                notes=(
                    f"checked_rows={int(done_mask.sum())}; missing_columns={','.join(missing_id_cols)}"
                    if missing_id_cols
                    else f"checked_rows={int(done_mask.sum())}"
                ),
            )

    if id_cols:
        dup_count = int(df.duplicated(subset=id_cols, keep=False).sum())
        repeat_samples = int((art.metadata.get("config") or {}).get("repeat_samples", 1))
        allow_dup = repeat_samples > 1
        status = "PASS" if dup_count == 0 else ("WARN" if allow_dup else "FAIL")
        rb.add(
            test_id="step0_duplicate_step_id_rows",
            test_name="Duplicate rows by step-ID chain",
            metric_name="duplicate_rows",
            metric_value=dup_count,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status=status,
            notes="repeat_samples>1" if allow_dup and dup_count > 0 else "",
        )

    eff_cols = [c for c in ["eff_p1", "eff_p2", "eff_p3", "eff_p4"] if c in df.columns]
    if eff_cols:
        eff_vals = df[eff_cols].to_numpy(dtype=float)
        eff_bad = int(((eff_vals < 0) | (eff_vals > 1) | ~np.isfinite(eff_vals)).sum())
        rb.add(
            test_id="step0_efficiency_bounds",
            test_name="Efficiencies within [0,1]",
            metric_name="eff_out_of_bounds",
            metric_value=eff_bad,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if eff_bad == 0 else "FAIL",
        )

    z_cols = [c for c in ["z_p1", "z_p2", "z_p3", "z_p4"] if c in df.columns]
    if len(z_cols) == 4:
        z = df[z_cols].to_numpy(dtype=float)
        monotonic_bad = int((~((z[:, 0] < z[:, 1]) & (z[:, 1] < z[:, 2]) & (z[:, 2] < z[:, 3]))).sum())
        rb.add(
            test_id="step0_z_monotonic",
            test_name="z planes are strictly increasing",
            metric_name="non_monotonic_rows",
            metric_value=monotonic_bad,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if monotonic_bad == 0 else "WARN",
        )

    cfg = art.metadata.get("config") or {}
    if "cos_n" in df.columns and isinstance(cfg.get("cos_n"), list) and len(cfg["cos_n"]) == 2:
        lo, hi = float(cfg["cos_n"][0]), float(cfg["cos_n"][1])
        vals = df["cos_n"].astype(float)
        bad = int(((vals < lo) | (vals > hi)).sum())
        rb.add(
            test_id="step0_cos_range",
            test_name="cos_n in configured range",
            metric_name="out_of_range_rows",
            metric_value=bad,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if bad == 0 else "WARN",
            notes=f"configured [{lo}, {hi}]",
        )

    if "flux_cm2_min" in df.columns and isinstance(cfg.get("flux_cm2_min"), list) and len(cfg["flux_cm2_min"]) == 2:
        lo, hi = float(cfg["flux_cm2_min"][0]), float(cfg["flux_cm2_min"][1])
        vals = df["flux_cm2_min"].astype(float)
        bad = int(((vals < lo) | (vals > hi)).sum())
        rb.add(
            test_id="step0_flux_range",
            test_name="flux in configured range",
            metric_name="out_of_range_rows",
            metric_value=bad,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if bad == 0 else "WARN",
            notes=f"configured [{lo}, {hi}]",
        )

    if make_plots:
        _maybe_plot(df, output_dir / "plots" / "validate_step0_mesh")

    return rb.to_frame().reindex(columns=RESULT_COLUMNS)
