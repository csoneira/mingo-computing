#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_8/step_8_uncalibrated_to_threshold.py
Purpose: Step 8: apply front-end thresholding and charge-to-time conversion (uncalibration/decalibration).
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-05-08
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_8/step_8_uncalibrated_to_threshold.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

ROOT_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = ROOT_DIR.parents[1]
sys.path.append(str(ROOT_DIR))
sys.path.append(str(ROOT_DIR / "MASTER_STEPS"))
sys.path.append(str(REPO_ROOT))

from STEP_SHARED.sim_utils import (
    ensure_dir,
    find_latest_data_path,
    find_sim_run,
    find_sim_run_dir,
    iter_input_frames,
    latest_sim_run,
    random_sim_run,
    load_step_configs,
    load_with_metadata,
    now_iso,
    build_sim_run_name,
    register_sim_run,
    extract_step_id_chain,
    select_next_step_id,
    resolve_sim_run,
    reset_dir,
    save_with_metadata,
    write_chunked_output,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.tot_charge_calibration import (
    TotChargeCalibration,
    default_tot_charge_calibration_path,
)


def apply_fee(
    df: pd.DataFrame,
    t_fee_sigma_ns: float,
    q_fee_sigma_ns: float,
    charge_conversion_model: str,
    q_to_time_factor: float,
    charge_calibration: TotChargeCalibration | None,
    qfront_offsets: list[list[float]],
    qback_offsets: list[list[float]],
    rng: np.random.Generator,
) -> pd.DataFrame:
    out = df.copy()
    for plane_idx in range(1, 5):
        for strip_idx in range(1, 5):
            tf_col = f"T_front_{plane_idx}_s{strip_idx}"
            tb_col = f"T_back_{plane_idx}_s{strip_idx}"
            qf_col = f"Q_front_{plane_idx}_s{strip_idx}"
            qb_col = f"Q_back_{plane_idx}_s{strip_idx}"

            if tf_col in out.columns:
                vals = out[tf_col].to_numpy(dtype=float)
                mask = ~np.isnan(vals)
                if mask.any():
                    vals[mask] = vals[mask] + rng.normal(0.0, t_fee_sigma_ns, mask.sum())
                out[tf_col] = vals
            if tb_col in out.columns:
                vals = out[tb_col].to_numpy(dtype=float)
                mask = ~np.isnan(vals)
                if mask.any():
                    vals[mask] = vals[mask] + rng.normal(0.0, t_fee_sigma_ns, mask.sum())
                out[tb_col] = vals

            if qf_col in out.columns:
                vals = out[qf_col].to_numpy(dtype=float)
                mask = vals != 0
                if mask.any():
                    converted = (
                        charge_calibration.charge_fc_to_width_ns(vals[mask])
                        if charge_conversion_model == "tot_curve_inverse" and charge_calibration is not None
                        else vals[mask] * q_to_time_factor
                    )
                    if q_fee_sigma_ns > 0:
                        converted = converted + rng.normal(0.0, q_fee_sigma_ns, mask.sum())
                    vals[mask] = converted
                out[qf_col] = vals
            if qb_col in out.columns:
                vals = out[qb_col].to_numpy(dtype=float)
                mask = vals != 0
                if mask.any():
                    converted = (
                        charge_calibration.charge_fc_to_width_ns(vals[mask])
                        if charge_conversion_model == "tot_curve_inverse" and charge_calibration is not None
                        else vals[mask] * q_to_time_factor
                    )
                    if q_fee_sigma_ns > 0:
                        converted = converted + rng.normal(0.0, q_fee_sigma_ns, mask.sum())
                    vals[mask] = converted
                out[qb_col] = vals
    return out


def apply_threshold(df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    out = df.copy()
    for plane_idx in range(1, 5):
        for strip_idx in range(1, 5):
            for prefix in ("Q_front", "Q_back"):
                col = f"{prefix}_{plane_idx}_s{strip_idx}"
                if col not in out.columns:
                    continue
                vals = out[col].to_numpy(dtype=float)
                vals[vals < threshold] = 0.0
                out[col] = vals
    return out


def apply_charge_offsets(
    df: pd.DataFrame,
    qfront_offsets: list[list[float]],
    qback_offsets: list[list[float]],
) -> pd.DataFrame:
    out = df.copy()
    for plane_idx in range(1, 5):
        for strip_idx in range(1, 5):
            qf_col = f"Q_front_{plane_idx}_s{strip_idx}"
            qb_col = f"Q_back_{plane_idx}_s{strip_idx}"
            if qf_col in out.columns:
                vals = out[qf_col].to_numpy(dtype=float)
                mask = vals != 0
                if mask.any():
                    vals[mask] = vals[mask] + float(qfront_offsets[plane_idx - 1][strip_idx - 1])
                out[qf_col] = vals
            if qb_col in out.columns:
                vals = out[qb_col].to_numpy(dtype=float)
                mask = vals != 0
                if mask.any():
                    vals[mask] = vals[mask] + float(qback_offsets[plane_idx - 1][strip_idx - 1])
                out[qb_col] = vals
    return out


def prune_step8(df: pd.DataFrame) -> pd.DataFrame:
    keep = {
        "event_id", "T_thick_s", "X_gen", "Y_gen", "Theta_gen", "Phi_gen",
        "crossing_mask",
    }
    for plane_idx in range(1, 5):
        for strip_idx in range(1, 5):
            keep.add(f"T_front_{plane_idx}_s{strip_idx}")
            keep.add(f"T_back_{plane_idx}_s{strip_idx}")
            keep.add(f"Q_front_{plane_idx}_s{strip_idx}")
            keep.add(f"Q_back_{plane_idx}_s{strip_idx}")
    keep_cols = [col for col in df.columns if col in keep]
    return df[keep_cols]


def pick_tt_column(df: pd.DataFrame) -> str | None:
    for col in ("tt_trigger", "tt_hit", "tt_avalanche", "tt_crossing"):
        if col in df.columns:
            return col
    return None


def plot_threshold_summary(
    df: pd.DataFrame,
    output_path: Path,
    threshold: float,
    qfront_offsets: list[list[float]],
    qback_offsets: list[list[float]],
) -> None:
    with PdfPages(output_path) as pdf:
        tt_col = pick_tt_column(df)
        if tt_col:
            fig, ax = plt.subplots(figsize=(8, 6))
            counts = df[tt_col].astype("string").fillna("").value_counts().sort_index()
            bars = ax.bar(counts.index.astype(str), counts.values, color="slateblue", alpha=0.8)
            for patch in bars:
                patch.set_rasterized(True)
            ax.set_title(f"{tt_col} counts")
            ax.set_xlabel(tt_col)
            ax.set_ylabel("Counts")
            fig.tight_layout()
            pdf.savefig(fig, dpi=150)
            plt.close(fig)

        fig, axes = plt.subplots(4, 4, figsize=(12, 10))
        for plane_idx in range(1, 5):
            for strip_idx in range(1, 5):
                ax = axes[plane_idx - 1, strip_idx - 1]
                qf_col = f"Q_front_{plane_idx}_s{strip_idx}"
                qb_col = f"Q_back_{plane_idx}_s{strip_idx}"
                if qf_col not in df.columns and qb_col not in df.columns:
                    ax.axis("off")
                    continue
                if qf_col in df.columns:
                    vals = df[qf_col].to_numpy(dtype=float)
                    mask = vals != 0
                    if mask.any():
                        vals = vals[mask] - float(qfront_offsets[plane_idx - 1][strip_idx - 1])
                        ax.hist(vals, bins=80, color="steelblue", alpha=0.6, label="front")
                if qb_col in df.columns:
                    vals = df[qb_col].to_numpy(dtype=float)
                    mask = vals != 0
                    if mask.any():
                        vals = vals[mask] - float(qback_offsets[plane_idx - 1][strip_idx - 1])
                        ax.hist(vals, bins=80, color="darkorange", alpha=0.6, label="back")
                ax.set_title(f"P{plane_idx} S{strip_idx}")
                ax.set_xlabel("a*x only")
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        qfront_cols = [c for c in df.columns if c.startswith("Q_front_")]
        qfront_vals = df[qfront_cols].to_numpy(dtype=float).ravel() if qfront_cols else np.array([])
        axes[0].hist(qfront_vals, bins=60, color="steelblue", alpha=0.8)
        axes[0].axvline(threshold, color="red", linestyle="--", linewidth=1)
        axes[0].set_title("Q_front (thresholded)")
        axes[0].set_xlabel("Q_front")

        qback_cols = [c for c in df.columns if c.startswith("Q_back_")]
        qback_vals = df[qback_cols].to_numpy(dtype=float).ravel() if qback_cols else np.array([])
        axes[1].hist(qback_vals, bins=60, color="seagreen", alpha=0.8)
        axes[1].axvline(threshold, color="red", linestyle="--", linewidth=1)
        axes[1].set_title("Q_back (thresholded)")
        axes[1].set_xlabel("Q_back")

        for ax in axes:
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

        fig, axes = plt.subplots(4, 4, figsize=(12, 10))
        for plane_idx in range(1, 5):
            for strip_idx in range(1, 5):
                ax = axes[plane_idx - 1, strip_idx - 1]
                tf_col = f"T_front_{plane_idx}_s{strip_idx}"
                tb_col = f"T_back_{plane_idx}_s{strip_idx}"
                if tf_col not in df.columns and tb_col not in df.columns:
                    ax.axis("off")
                    continue
                if tf_col in df.columns:
                    vals = df[tf_col].to_numpy(dtype=float)
                    vals = vals[(~np.isnan(vals)) & (vals != 0)]
                    ax.hist(vals, bins=80, color="steelblue", alpha=0.6, label="front")
                if tb_col in df.columns:
                    vals = df[tb_col].to_numpy(dtype=float)
                    vals = vals[(~np.isnan(vals)) & (vals != 0)]
                    ax.hist(vals, bins=80, color="darkorange", alpha=0.6, label="back")
                ax.set_title(f"P{plane_idx} S{strip_idx}")
                ax.set_xlabel("time (ns)")
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

        fig, axes = plt.subplots(4, 4, figsize=(12, 10))
        for plane_idx in range(1, 5):
            for strip_idx in range(1, 5):
                ax = axes[plane_idx - 1, strip_idx - 1]
                qf_col = f"Q_front_{plane_idx}_s{strip_idx}"
                qb_col = f"Q_back_{plane_idx}_s{strip_idx}"
                if qf_col not in df.columns and qb_col not in df.columns:
                    ax.axis("off")
                    continue
                if qf_col in df.columns:
                    vals = df[qf_col].to_numpy(dtype=float)
                    vals = vals[vals != 0]
                    ax.hist(vals, bins=80, color="steelblue", alpha=0.6, label="front")
                if qb_col in df.columns:
                    vals = df[qb_col].to_numpy(dtype=float)
                    vals = vals[vals != 0]
                    ax.hist(vals, bins=80, color="darkorange", alpha=0.6, label="back")
                ax.set_title(f"P{plane_idx} S{strip_idx}")
                ax.set_xlabel("charge")
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 8: apply charge threshold.")
    parser.add_argument("--config", default="config_step_8_physics.yaml", help="Path to step physics config YAML")
    parser.add_argument(
        "--runtime-config",
        default=None,
        help="Path to step runtime config YAML (defaults to *_runtime.yaml)",
    )
    parser.add_argument("--plot-only", action="store_true", help="Only generate plots from existing outputs")
    parser.add_argument("--no-plots", action="store_true", help="Skip plot generation")
    parser.add_argument("--force", action="store_true", help="Recompute even if sim_run exists")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(__file__).resolve().parent / config_path
    runtime_path = Path(args.runtime_config) if args.runtime_config else None
    if runtime_path is not None and not runtime_path.is_absolute():
        runtime_path = Path(__file__).resolve().parent / runtime_path

    physics_cfg, runtime_cfg, cfg, runtime_path = load_step_configs(config_path, runtime_path)

    input_dir = Path(cfg["input_dir"])
    if not input_dir.is_absolute():
        input_dir = Path(__file__).resolve().parent / input_dir
    output_dir = Path(cfg["output_dir"])
    if not output_dir.is_absolute():
        output_dir = Path(__file__).resolve().parent / output_dir
    ensure_dir(output_dir)

    output_format = str(cfg.get("output_format", "pkl")).lower()
    chunk_rows = cfg.get("chunk_rows")
    plot_sample_rows = cfg.get("plot_sample_rows")
    threshold = float(cfg.get("charge_threshold", 0.01))
    t_fee_sigma_ns = float(cfg.get("t_fee_sigma_ns", 0.01))
    q_fee_sigma_ns = float(cfg.get("q_fee_sigma_ns", 0.0))
    q_to_time_factor = float(cfg.get("q_to_time_factor", 1.0e-5))
    charge_conversion_model = str(
        cfg.get("charge_conversion_model", "linear_q_to_time_factor")
    ).strip().lower()
    if charge_conversion_model not in {"linear_q_to_time_factor", "tot_curve_inverse"}:
        raise ValueError(
            "charge_conversion_model must be 'linear_q_to_time_factor' or 'tot_curve_inverse'."
        )
    charge_calibration = None
    calibration_path = None
    if charge_conversion_model == "tot_curve_inverse":
        calibration_path = cfg.get("tot_to_charge_calibration_path")
        if calibration_path is None:
            calibration_path = default_tot_charge_calibration_path(REPO_ROOT)
        else:
            calibration_path = Path(calibration_path)
            if not calibration_path.is_absolute():
                calibration_path = REPO_ROOT / calibration_path
        if calibration_path.is_file():
            charge_calibration = TotChargeCalibration.from_csv(calibration_path)
        else:
            # The recovery clone lacks this scientific input. The checked-in
            # q_to_time_factor is the documented fallback for that case.
            print(f"WARNING: TOT calibration missing at {calibration_path}; using linear_q_to_time_factor fallback")
            charge_conversion_model = "linear_q_to_time_factor"
    qfront_offsets = cfg.get("qfront_offsets", [[0, 0, 0, 0]] * 4)
    qback_offsets = cfg.get("qback_offsets", [[0, 0, 0, 0]] * 4)
    rng = np.random.default_rng(cfg.get("seed"))

    input_glob = cfg.get("input_glob", "**/step_7_chunks.chunks.json")
    input_sim_run = cfg.get("input_sim_run", "latest")

    print("\n-----\nStep 8 starting...\n-----")
    print(f"Input dir: {input_dir}")
    print(f"Output dir: {output_dir}")
    print(f"charge_threshold: {threshold}")
    print(f"charge_conversion_model: {charge_conversion_model}")
    print(f"q_fee_sigma_ns: {q_fee_sigma_ns}")
    print(f"q_to_time_factor: {q_to_time_factor}")
    if calibration_path is not None:
        print(f"tot_to_charge_calibration_path: {calibration_path}")

    if args.plot_only:
        if args.no_plots:
            print("Plot-only requested with --no-plots; skipping plots.")
            return
        latest_path = find_latest_data_path(output_dir)
        if latest_path is None:
            raise FileNotFoundError(f"No existing outputs found in {output_dir} for plot-only.")
        df, _ = load_with_metadata(latest_path)
        sim_run_dir = find_sim_run_dir(latest_path)
        plot_dir = (sim_run_dir or latest_path.parent) / "PLOTS"
        ensure_dir(plot_dir)
        plot_path = plot_dir / f"{latest_path.stem}_plots.pdf"
        plot_threshold_summary(df, plot_path, threshold, qfront_offsets, qback_offsets)
        print(f"Saved {plot_path}")
        return

    input_sim_run_mode = input_sim_run
    if "**" in input_glob:
        candidates = sorted(input_dir.rglob(input_glob.replace("**/", "")))
    else:
        candidates = sorted(input_dir.rglob(input_glob))
    if input_sim_run_mode not in ("latest", "random"):
        input_run_dir = input_dir / str(input_sim_run_mode)
        candidates = [path for path in candidates if input_run_dir in path.parents]
        if not candidates:
            raise FileNotFoundError(
                f"No inputs found for {input_glob} under {input_run_dir}."
            )
    def normalize_stem(path: Path) -> str:
        name = path.name
        if name.endswith(".chunks.json"):
            name = name[: -len(".chunks.json")]
        stem = Path(name).stem
        return stem.replace(".chunks", "")

    if not candidates:
        raise FileNotFoundError(f"No inputs found for {input_glob} under {input_dir}.")

    if input_sim_run_mode == "latest":
        candidates = sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)
    elif input_sim_run_mode == "random":
        rng.shuffle(candidates)

    input_iter = None
    upstream_meta = None
    chunked_input = False
    step_chain = None
    step_8_id = None
    input_path = None
    mesh_dir = Path(cfg.get("param_mesh_dir", "../../SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1"))
    if not mesh_dir.is_absolute():
        mesh_dir = Path(__file__).resolve().parent / mesh_dir

    for candidate in candidates:
        candidate_iter, candidate_meta, candidate_chunked = iter_input_frames(candidate, chunk_rows)
        candidate_chain = extract_step_id_chain(candidate_meta)
        if not candidate_chain:
            continue
        candidate_step_8_id = select_next_step_id(
            output_dir,
            mesh_dir,
            cfg.get("param_mesh_sim_run", "none"),
            "step_8_id",
            candidate_chain,
            cfg.get("seed"),
            physics_cfg.get("step_8_id"),
        )
        if candidate_step_8_id is None:
            continue
        input_path = candidate
        input_iter = candidate_iter
        upstream_meta = candidate_meta
        chunked_input = candidate_chunked
        step_chain = candidate_chain
        step_8_id = candidate_step_8_id
        break

    if input_path is None or input_iter is None or upstream_meta is None or step_chain is None or step_8_id is None:
        print("Skipping STEP_8: all step_8_id combinations already exist.")
        return

    normalized_stem = normalize_stem(input_path)
    print(f"Processing: {input_path}")
    sim_run = build_sim_run_name(step_chain + [step_8_id])
    sim_run_dir = output_dir / sim_run
    if not args.force and sim_run_dir.exists():
        print(f"SIM_RUN {sim_run} already exists; skipping (use --force to regenerate).")
        return

    physics_cfg["step_8_id"] = step_8_id
    sim_run, sim_run_dir, config_hash, upstream_hash, _ = register_sim_run(
        output_dir, "STEP_8", config_path, physics_cfg, upstream_meta, sim_run
    )
    reset_dir(sim_run_dir)

    out_stem_base = "step_8"
    out_stem = f"{out_stem_base}_chunks" if chunk_rows else out_stem_base
    metadata = {
        "created_at": now_iso(),
        "step": "STEP_8",
        "config": physics_cfg,
        "runtime_config": runtime_cfg,
        "sim_run": sim_run,
        "config_hash": config_hash,
        "upstream_hash": upstream_hash,
        "source_dataset": str(input_path),
        "upstream": upstream_meta,
        "step_8_id": step_8_id,
    }
    if chunk_rows:
        def _iter_out() -> Iterable[pd.DataFrame]:
            for chunk in input_iter:
                out_chunk = apply_fee(
                    chunk,
                    t_fee_sigma_ns,
                    q_fee_sigma_ns,
                    charge_conversion_model,
                    q_to_time_factor,
                    charge_calibration,
                    qfront_offsets,
                    qback_offsets,
                    rng,
                )
                out_chunk = apply_threshold(out_chunk, threshold)
                out_chunk = apply_charge_offsets(out_chunk, qfront_offsets, qback_offsets)
                yield prune_step8(out_chunk)

        manifest_path, last_chunk, row_count = write_chunked_output(
            _iter_out(),
            sim_run_dir,
            out_stem,
            output_format,
            int(chunk_rows),
            metadata,
        )
        plot_df = last_chunk
        if plot_sample_rows and plot_df is not None:
            sample_n = len(plot_df) if plot_sample_rows is True else int(plot_sample_rows)
            sample_n = min(sample_n, len(plot_df))
            plot_df = plot_df.sample(n=sample_n, random_state=cfg.get("seed"))
        if not args.no_plots and plot_df is not None:
            plot_dir = sim_run_dir / "PLOTS"
            ensure_dir(plot_dir)
            plot_path = plot_dir / f"{out_stem_base}_plots.pdf"
            plot_threshold_summary(plot_df, plot_path, threshold, qfront_offsets, qback_offsets)
        print(f"Saved {manifest_path}")
    else:
        df, upstream_meta = load_with_metadata(input_path)
        out = apply_fee(
            df,
            t_fee_sigma_ns,
            q_fee_sigma_ns,
            charge_conversion_model,
            q_to_time_factor,
            charge_calibration,
            qfront_offsets,
            qback_offsets,
            rng,
        )
        out = apply_threshold(out, threshold)
        out = apply_charge_offsets(out, qfront_offsets, qback_offsets)
        out = prune_step8(out)
        out_path = sim_run_dir / f"{out_stem}.{output_format}"
        save_with_metadata(out, out_path, metadata, output_format)
        if not args.no_plots:
            plot_dir = sim_run_dir / "PLOTS"
            ensure_dir(plot_dir)
            plot_path = plot_dir / f"{out_path.stem}_plots.pdf"
            plot_threshold_summary(out, plot_path, threshold, qfront_offsets, qback_offsets)
        print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
