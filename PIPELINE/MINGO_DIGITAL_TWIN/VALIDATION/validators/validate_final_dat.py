#!/usr/bin/env python3

"""Validator for final station .dat outputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .common_io import StepArtifact, list_dat_files
from .common_report import RESULT_COLUMNS, ResultBuilder


@dataclass
class DatScan:
    file_name: str
    path: Path
    param_hash: str | None
    rows: int
    bad_field_count: int
    parse_errors: int
    non_monotonic_timestamps: int
    max_abs_payload: float
    first_payload_tokens: list[str] | None
    sampled_payload_values: np.ndarray


def _format_value(val: float) -> str:
    if not np.isfinite(val):
        val = 0.0
    if val < 0:
        return f"{val:.4f}"
    return f"{val:09.4f}"


def _scan_dat(path: Path, sample_lines: int = 5000) -> DatScan:
    param_hash: str | None = None
    rows = 0
    bad_field_count = 0
    parse_errors = 0
    non_monotonic = 0
    max_abs_payload = 0.0
    first_payload_tokens: list[str] | None = None
    sample_values: list[np.ndarray] = []

    prev_ts: tuple[int, int, int, int, int, int] | None = None

    with path.open("r", encoding="ascii", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                if line.lower().startswith("# param_hash="):
                    param_hash = line.split("=", 1)[1].strip()
                continue

            rows += 1
            parts = line.split()
            if len(parts) != 71:
                bad_field_count += 1
                continue

            try:
                y, m, d, hh, mm, ss, flag = [int(x) for x in parts[:7]]
                _ = flag  # fixed format field
                ts = (y, m, d, hh, mm, ss)
                if prev_ts is not None and ts < prev_ts:
                    non_monotonic += 1
                prev_ts = ts

                payload_tokens = parts[7:]
                payload = np.asarray([float(x) for x in payload_tokens], dtype=float)
                if payload.size != 64 or (~np.isfinite(payload)).any():
                    parse_errors += 1
                    continue

                if first_payload_tokens is None:
                    first_payload_tokens = payload_tokens

                local_max = float(np.max(np.abs(payload))) if payload.size else 0.0
                if local_max > max_abs_payload:
                    max_abs_payload = local_max

                if len(sample_values) < sample_lines:
                    sample_values.append(payload)

            except Exception:
                parse_errors += 1

    sampled_payload_values = np.concatenate(sample_values) if sample_values else np.array([])
    return DatScan(
        file_name=path.name,
        path=path,
        param_hash=param_hash,
        rows=rows,
        bad_field_count=bad_field_count,
        parse_errors=parse_errors,
        non_monotonic_timestamps=non_monotonic,
        max_abs_payload=max_abs_payload,
        first_payload_tokens=first_payload_tokens,
        sampled_payload_values=sampled_payload_values,
    )


def _plot(sample_values: np.ndarray, plot_dir: Path) -> None:
    plot_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    if sample_values.size:
        ax.hist(sample_values, bins=120, color="steelblue", alpha=0.8)
    ax.set_title("Final .dat payload values (sample)")
    ax.set_xlabel("Value")
    fig.tight_layout()
    fig.savefig(plot_dir / "final_dat_payload_distribution.png", dpi=140)
    plt.close(fig)


def _load_sim_params(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def run(
    artifacts: dict[str, StepArtifact],
    run_timestamp: str,
    output_dir: Path,
    make_plots: bool = False,
    max_files: int = 10,
) -> pd.DataFrame:
    any_art = next((a for a in artifacts.values() if a is not None), None)
    rb = ResultBuilder(
        run_timestamp=run_timestamp,
        validator="validate_final_dat",
        step="final",
        sim_run=artifacts.get("10").sim_run if artifacts.get("10") else None,
        config_hash=artifacts.get("10").config_hash if artifacts.get("10") else None,
        upstream_hash=artifacts.get("10").upstream_hash if artifacts.get("10") else None,
        n_rows_in=artifacts.get("10").row_count if artifacts.get("10") else None,
        n_rows_out=None,
    )

    if any_art is None:
        rb.add(
            test_id="final_context",
            test_name="Artifacts available",
            metric_name="artifacts_available",
            metric_value=0,
            status="SKIP",
            notes="No discovered artifacts",
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    twin_root = any_art.interstep_dir.parents[1]
    simulated_data = twin_root / "SIMULATED_DATA"
    simulated_dat_dir = simulated_data / "FILES"
    if not simulated_dat_dir.exists():
        simulated_dat_dir = simulated_data
    params_path = simulated_data / "step_final_simulation_params.csv"

    params_df = _load_sim_params(params_path)
    rb.add(
        test_id="final_sim_params_exists",
        test_name="step_final_simulation_params.csv exists",
        metric_name="exists",
        metric_value=int(params_path.exists()),
        status="PASS" if params_path.exists() else "WARN",
        notes=str(params_path),
    )

    dat_files = list_dat_files(simulated_data, max_files=max_files)
    if not dat_files:
        rb.add(
            test_id="final_dat_files_present",
            test_name="At least one .dat file exists",
            metric_name="n_dat_files",
            metric_value=0,
            status="FAIL",
            notes=str(simulated_dat_dir),
        )
        return rb.to_frame().reindex(columns=RESULT_COLUMNS)

    rb.add(
        test_id="final_dat_files_present",
        test_name="At least one .dat file exists",
        metric_name="n_dat_files",
        metric_value=len(dat_files),
        status="PASS",
        notes=f"validated_latest={len(dat_files)}",
    )

    sampled_payload_all: list[np.ndarray] = []

    for dat_path in dat_files:
        scan = _scan_dat(dat_path)
        if scan.sampled_payload_values.size:
            sampled_payload_all.append(scan.sampled_payload_values)

        base_id = f"final_{scan.file_name}"
        if not params_df.empty and "file_name" in params_df.columns:
            row = params_df[params_df["file_name"] == scan.file_name]
        else:
            row = pd.DataFrame()

        rb.add(
            test_id=f"{base_id}_field_count",
            test_name=f"{scan.file_name}: 71 fields per data line",
            metric_name="bad_field_count",
            metric_value=scan.bad_field_count,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if scan.bad_field_count == 0 else "FAIL",
        )

        rb.add(
            test_id=f"{base_id}_parse_errors",
            test_name=f"{scan.file_name}: parse errors",
            metric_name="parse_errors",
            metric_value=scan.parse_errors,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if scan.parse_errors == 0 else "FAIL",
        )

        rb.add(
            test_id=f"{base_id}_timestamp_monotonic",
            test_name=f"{scan.file_name}: timestamps monotonic",
            metric_name="non_monotonic_rows",
            metric_value=scan.non_monotonic_timestamps,
            expected_value=0,
            threshold_low=0,
            threshold_high=0,
            status="PASS" if scan.non_monotonic_timestamps == 0 else "WARN",
        )

        rb.add(
            test_id=f"{base_id}_payload_range",
            test_name=f"{scan.file_name}: payload magnitude sanity",
            metric_name="max_abs_payload",
            metric_value=scan.max_abs_payload,
            threshold_low=0,
            threshold_high=1e9,
            status="PASS" if scan.max_abs_payload < 1e9 else "FAIL",
        )

        if not row.empty and "selected_rows" in row.columns:
            try:
                expected_rows = int(row.iloc[0]["selected_rows"])
                status = "PASS" if scan.rows == expected_rows else "FAIL"
                rb.add(
                    test_id=f"{base_id}_row_count_match",
                    test_name=f"{scan.file_name}: rows match selected_rows",
                    metric_name="row_count",
                    metric_value=scan.rows,
                    expected_value=expected_rows,
                    status=status,
                )
            except Exception:
                rb.add(
                    test_id=f"{base_id}_row_count_match",
                    test_name=f"{scan.file_name}: rows match selected_rows",
                    metric_name="row_count",
                    metric_value=scan.rows,
                    status="WARN",
                    notes="selected_rows could not be parsed",
                )
        else:
            rb.add(
                test_id=f"{base_id}_row_count_match",
                test_name=f"{scan.file_name}: rows match selected_rows",
                metric_name="row_count",
                metric_value=scan.rows,
                status="SKIP",
                notes="No selected_rows metadata for file",
            )


        rate_columns = (
            "trigger_rate_hz",
            "trigger_rate_unit_efficiency_hz",
            "particle_crossing_rate_hz",
        )
        if not row.empty and all(column in row.columns for column in rate_columns):
            rate_values = pd.to_numeric(
                row.iloc[0].loc[list(rate_columns)], errors="coerce",
            )
            actual_rate = float(rate_values["trigger_rate_hz"])
            unit_rate = float(rate_values["trigger_rate_unit_efficiency_hz"])
            crossing_rate = float(rate_values["particle_crossing_rate_hz"])
            new_rates_finite = np.isfinite([unit_rate, crossing_rate])
            if new_rates_finite.all() and np.isfinite(actual_rate):
                ordered = (
                    0.0 <= actual_rate <= unit_rate + 1e-12
                    and unit_rate <= crossing_rate + 1e-12
                )
                rb.add(
                    test_id=f"{base_id}_rate_decomposition",
                    test_name=f"{scan.file_name}: trigger-rate decomposition is ordered",
                    metric_name="actual_le_unit_le_crossing",
                    metric_value=int(ordered),
                    expected_value=1,
                    status="PASS" if ordered else "FAIL",
                    notes=(
                        f"actual={actual_rate:.9g}, unit_efficiency={unit_rate:.9g}, "
                        f"crossing={crossing_rate:.9g}"
                    ),
                )
            else:
                available_new_rates = int(new_rates_finite.sum())
                rb.add(
                    test_id=f"{base_id}_rate_decomposition",
                    test_name=f"{scan.file_name}: trigger-rate decomposition is ordered",
                    metric_name="available_geometrical_rate_count",
                    metric_value=available_new_rates,
                    expected_value=2,
                    status="SKIP" if available_new_rates == 0 else "WARN",
                    notes="Historical or legacy input may not have geometrical counters.",
                )
        else:
            rb.add(
                test_id=f"{base_id}_rate_decomposition",
                test_name=f"{scan.file_name}: trigger-rate decomposition is ordered",
                metric_name="available_geometrical_rate_count",
                metric_value=0,
                expected_value=2,
                status="SKIP",
                notes="Rate-decomposition columns are absent.",
            )

        if not row.empty and "param_hash" in row.columns:
            expected_hash = str(row.iloc[0]["param_hash"]).strip()
            if scan.param_hash is None:
                rb.add(
                    test_id=f"{base_id}_param_hash_header",
                    test_name=f"{scan.file_name}: param_hash header present",
                    metric_name="header_present",
                    metric_value=0,
                    status="WARN",
                )
            else:
                match = int(scan.param_hash == expected_hash)
                rb.add(
                    test_id=f"{base_id}_param_hash_match",
                    test_name=f"{scan.file_name}: param_hash matches simulation params",
                    metric_name="hash_match",
                    metric_value=match,
                    expected_value=1,
                    threshold_low=1,
                    threshold_high=1,
                    status="PASS" if match == 1 else "FAIL",
                    notes=f"expected={expected_hash}, found={scan.param_hash}",
                )
        else:
            rb.add(
                test_id=f"{base_id}_param_hash_match",
                test_name=f"{scan.file_name}: param_hash matches simulation params",
                metric_name="status",
                metric_value=np.nan,
                status="SKIP",
                notes="File not found in step_final_simulation_params.csv",
            )

        if scan.first_payload_tokens:
            try:
                vals = [float(x) for x in scan.first_payload_tokens]
                fmt = [_format_value(v) for v in vals]
                mismatch = int(sum(a != b for a, b in zip(scan.first_payload_tokens, fmt)))
                rb.add(
                    test_id=f"{base_id}_roundtrip_format",
                    test_name=f"{scan.file_name}: payload format round-trip",
                    metric_name="token_mismatches",
                    metric_value=mismatch,
                    expected_value=0,
                    threshold_low=0,
                    threshold_high=0,
                    status="PASS" if mismatch == 0 else "WARN",
                )
            except Exception:
                rb.add(
                    test_id=f"{base_id}_roundtrip_format",
                    test_name=f"{scan.file_name}: payload format round-trip",
                    metric_name="status",
                    metric_value=np.nan,
                    status="WARN",
                    notes="Could not execute round-trip formatting check",
                )

    registry_path = simulated_data / "step_final_output_registry.json"
    if not registry_path.exists():
        rb.add(
            test_id="final_step10_exact_roundtrip",
            test_name="Exact step10-to-dat roundtrip availability",
            metric_name="registry_available",
            metric_value=0,
            status="SKIP",
            notes="step_final_output_registry.json missing; cannot map files to exact STEP 10 source rows",
        )

    if make_plots and sampled_payload_all:
        all_vals = np.concatenate(sampled_payload_all)
        _plot(all_vals, output_dir / "plots" / "validate_final_dat")

    return rb.to_frame().reindex(columns=RESULT_COLUMNS)
