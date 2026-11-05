#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/run_validation.py
Purpose: Run MINGO digital twin validation suite and write CSV reports.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/run_validation.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from validators.common_io import discover_step_artifacts, summarize_artifacts
from validators.common_report import (
    RESULT_COLUMNS,
    SUMMARY_COLUMNS,
    build_history_row,
    summarize_results,
)
from validators import (
    validate_cross_step_lineage,
    validate_final_dat,
    validate_step0_mesh,
    validate_step1_muons,
    validate_step2_crossings,
    validate_step3_avalanche,
    validate_step4_induction,
    validate_step5_strip_obs,
    validate_step6_endpoints,
    validate_step7_offsets,
    validate_step8_fee,
    validate_step9_trigger,
    validate_step10_tdc,
)


def parse_steps(raw: str, *, valid_keys: set[str], default_order: list[str]) -> list[str]:
    if not raw or raw.strip().lower() == "all":
        return default_order.copy()

    out: list[str] = []
    aliases = {
        "lineage": "cross",
    }
    for token in raw.split(","):
        key = token.strip().lower()
        if not key:
            continue
        key = aliases.get(key, key)
        if key in valid_keys:
            out.append(key)
        else:
            raise ValueError(f"Unknown step selector: {token}")

    seen = set()
    unique = []
    for k in out:
        if k not in seen:
            unique.append(k)
            seen.add(k)
    return unique


def _ensure_columns(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=cols)
    return df.reindex(columns=cols)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run simulation validators and export CSV reports.")
    parser.add_argument("--sim-run", default=None, help="Optional SIM_RUN filter (exact or substring).")
    parser.add_argument(
        "--steps",
        default="all",
        help="Comma-separated subset: cross,0,1,2,3,4,5,6,7,8,9,10,final (default: all)",
    )
    parser.add_argument("-p", "--plot", action="store_true", help="Generate diagnostic plots.")
    parser.add_argument(
        "--max-step1-sample",
        type=int,
        default=300_000,
        help="Rows to sample from STEP 1 for validation statistics.",
    )
    parser.add_argument(
        "--max-final-files",
        type=int,
        default=10,
        help="How many latest .dat files to validate in FINAL checks.",
    )
    args = parser.parse_args()

    this_file = Path(__file__).resolve()
    validation_dir = this_file.parent
    twin_root = validation_dir.parent
    intersteps_dir = twin_root / "INTERSTEPS"
    output_root = validation_dir / "output"
    output_root.mkdir(parents=True, exist_ok=True)

    run_dt = datetime.now(timezone.utc)
    run_timestamp = run_dt.isoformat()
    run_name = f"validate_{run_dt.strftime('%Y%m%d_%H%M%S')}"
    run_dir = output_root / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    artifacts = discover_step_artifacts(intersteps_dir, sim_run_filter=args.sim_run)

    validators: dict[str, tuple[str, Callable[..., pd.DataFrame]]] = {
        "cross": ("validate_cross_step_lineage", validate_cross_step_lineage.run),
        "0": ("validate_step0_mesh", validate_step0_mesh.run),
        "1": ("validate_step1_muons", validate_step1_muons.run),
        "2": ("validate_step2_crossings", validate_step2_crossings.run),
        "3": ("validate_step3_avalanche", validate_step3_avalanche.run),
        "4": ("validate_step4_induction", validate_step4_induction.run),
        "5": ("validate_step5_strip_obs", validate_step5_strip_obs.run),
        "6": ("validate_step6_endpoints", validate_step6_endpoints.run),
        "7": ("validate_step7_offsets", validate_step7_offsets.run),
        "8": ("validate_step8_fee", validate_step8_fee.run),
        "9": ("validate_step9_trigger", validate_step9_trigger.run),
        "10": ("validate_step10_tdc", validate_step10_tdc.run),
        "final": ("validate_final_dat", validate_final_dat.run),
    }
    selected_steps = parse_steps(
        args.steps,
        valid_keys=set(validators.keys()),
        default_order=list(validators.keys()),
    )

    all_results: list[pd.DataFrame] = []
    executed: list[str] = []

    for step_key in selected_steps:
        name, fn = validators[step_key]
        executed.append(name)
        try:
            if step_key == "1":
                df = fn(
                    artifacts=artifacts,
                    run_timestamp=run_timestamp,
                    output_dir=run_dir,
                    make_plots=args.plot,
                    sample_rows=int(args.max_step1_sample),
                )
            elif step_key == "final":
                df = fn(
                    artifacts=artifacts,
                    run_timestamp=run_timestamp,
                    output_dir=run_dir,
                    make_plots=args.plot,
                    max_files=int(args.max_final_files),
                )
            else:
                df = fn(
                    artifacts=artifacts,
                    run_timestamp=run_timestamp,
                    output_dir=run_dir,
                    make_plots=args.plot,
                )
        except Exception as exc:
            df = pd.DataFrame(
                [
                    {
                        "run_timestamp": run_timestamp,
                        "validator": name,
                        "test_id": f"{name}_exception",
                        "test_name": f"{name} top-level exception",
                        "step": step_key,
                        "sim_run": None,
                        "config_hash": None,
                        "upstream_hash": None,
                        "n_rows_in": None,
                        "n_rows_out": None,
                        "metric_name": "exception",
                        "metric_value": type(exc).__name__,
                        "expected_value": None,
                        "threshold_low": None,
                        "threshold_high": None,
                        "status": "ERROR",
                        "notes": str(exc),
                    }
                ]
            )

        all_results.append(_ensure_columns(df, RESULT_COLUMNS))

    non_empty_results = [df.astype("object") for df in all_results if not df.empty]
    if non_empty_results:
        results_df = pd.concat(non_empty_results, ignore_index=True)
    else:
        results_df = pd.DataFrame(columns=RESULT_COLUMNS)

    results_df = _ensure_columns(results_df, RESULT_COLUMNS)
    summary_df = summarize_results(results_df)
    summary_df = _ensure_columns(summary_df, SUMMARY_COLUMNS)

    results_path = run_dir / "validation_results.csv"
    summary_path = run_dir / "validation_summary.csv"
    metadata_path = run_dir / "validation_run_metadata.json"

    results_df.to_csv(results_path, index=False)
    summary_df.to_csv(summary_path, index=False)

    run_meta = {
        "run_name": run_name,
        "run_timestamp": run_timestamp,
        "sim_run_filter": args.sim_run,
        "selected_steps": selected_steps,
        "executed_validators": executed,
        "plot_enabled": bool(args.plot),
        "paths": {
            "twin_root": str(twin_root),
            "intersteps_dir": str(intersteps_dir),
            "output_root": str(output_root),
            "run_dir": str(run_dir),
            "results_csv": str(results_path),
            "summary_csv": str(summary_path),
        },
        "artifacts": summarize_artifacts(artifacts),
    }
    metadata_path.write_text(json.dumps(run_meta, indent=2))

    history_path = output_root / "validation_history.csv"
    history_row = build_history_row(
        run_timestamp=run_timestamp,
        run_name=run_name,
        summary_df=summary_df,
        sim_run_filter=args.sim_run,
        selected_steps=",".join(selected_steps),
    )

    history_df = pd.DataFrame([history_row])
    if history_path.exists():
        try:
            old = pd.read_csv(history_path)
            history_df = pd.concat([old, history_df], ignore_index=True)
        except Exception as exc:
            print(f"WARNING: failed to append validation history from {history_path}: {exc}")
    history_df.to_csv(history_path, index=False)

    # Console summary for quick checks.
    print(f"Validation run: {run_name}")
    print(f"Results: {results_path}")
    print(f"Summary: {summary_path}")
    if summary_df.empty:
        print("No validators were executed.")
        return

    print("\nValidator summary:")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
