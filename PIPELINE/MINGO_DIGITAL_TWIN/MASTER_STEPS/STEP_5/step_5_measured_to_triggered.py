#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_5/step_5_measured_to_triggered.py
Purpose: Step 5: derive per-strip time/charge differences from measured hits.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_5/step_5_measured_to_triggered.py [options]
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
sys.path.append(str(ROOT_DIR))
sys.path.append(str(ROOT_DIR / "MASTER_STEPS"))

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


def compute_tdiff_qdiff(
    df: pd.DataFrame,
    c_mm_per_ns: float,
    qdiff_width: float,
    rng: np.random.Generator,
) -> pd.DataFrame:
    out = df.copy()
    x_to_time_factor = 3.0 / (2.0 * c_mm_per_ns)

    for plane_idx in range(1, 5):
        for strip_idx in range(1, 5):
            x_col = f"X_mea_{plane_idx}_s{strip_idx}"
            qsum_col = f"Y_mea_{plane_idx}_s{strip_idx}"
            tsum_col = f"T_sum_meas_{plane_idx}_s{strip_idx}"
            if x_col not in out.columns or qsum_col not in out.columns:
                continue

            x_vals = out[x_col].to_numpy(dtype=float)
            qsum_vals = out[qsum_col].to_numpy(dtype=float)
            tdiff = x_vals * x_to_time_factor
            qdiff = np.zeros(len(out), dtype=float)
            hit_mask = qsum_vals > 0
            if hit_mask.any():
                qdiff_sigma = np.full(hit_mask.sum(), float(qdiff_width), dtype=float)
                qdiff[hit_mask] = rng.normal(0.0, qdiff_sigma, size=hit_mask.sum())

            out[f"T_diff_{plane_idx}_s{strip_idx}"] = tdiff
            out[f"q_diff_{plane_idx}_s{strip_idx}"] = qdiff

            if tsum_col in out.columns:
                out[tsum_col] = out[tsum_col]

    return out


def prune_step5(df: pd.DataFrame) -> pd.DataFrame:
    keep = {
        "event_id", "T_thick_s", "X_gen", "Y_gen", "Theta_gen", "Phi_gen",
        "crossing_mask",
    }
    for plane_idx in range(1, 5):
        for strip_idx in range(1, 5):
            keep.add(f"Y_mea_{plane_idx}_s{strip_idx}")
            keep.add(f"T_sum_meas_{plane_idx}_s{strip_idx}")
            keep.add(f"T_diff_{plane_idx}_s{strip_idx}")
            keep.add(f"q_diff_{plane_idx}_s{strip_idx}")
    keep_cols = [col for col in df.columns if col in keep]
    return df[keep_cols]


def pick_tt_column(df: pd.DataFrame) -> str | None:
    for col in ("tt_trigger", "tt_hit", "tt_avalanche", "tt_crossing"):
        if col in df.columns:
            return col
    return None


def plot_signal_summary(df: pd.DataFrame, output_path: Path) -> None:
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

        fig, axes = plt.subplots(2, 2, figsize=(12, 9))
        axes = axes.flatten()

        qsum_cols = [c for c in df.columns if c.startswith("Y_mea_") and "_s" in c]
        qsum_vals = df[qsum_cols].to_numpy(dtype=float).ravel() if qsum_cols else np.array([])
        qsum_vals = qsum_vals[qsum_vals > 0]
        axes[0].hist(qsum_vals, bins=60, color="steelblue", alpha=0.8)
        axes[0].set_title("qsum (all strips)")
        axes[0].set_xlabel("qsum")

        qdiff_cols = [c for c in df.columns if c.startswith("q_diff_")]
        qdiff_vals = df[qdiff_cols].to_numpy(dtype=float).ravel() if qdiff_cols else np.array([])
        qdiff_vals = qdiff_vals[qdiff_vals != 0]
        axes[1].hist(qdiff_vals, bins=60, color="seagreen", alpha=0.8)
        axes[1].set_title("q_diff (all strips)")
        axes[1].set_xlabel("q_diff")

        tdiff_cols = [c for c in df.columns if c.startswith("T_diff_")]
        tdiff_vals = df[tdiff_cols].to_numpy(dtype=float).ravel() if tdiff_cols else np.array([])
        tdiff_vals = tdiff_vals[~np.isnan(tdiff_vals)]
        axes[2].hist(tdiff_vals, bins=60, color="darkorange", alpha=0.8)
        axes[2].set_title("T_diff (all strips)")
        axes[2].set_xlabel("T_diff (ns)")

        tsum_cols = [c for c in df.columns if c.startswith("T_sum_meas_")]
        tsum_vals = df[tsum_cols].to_numpy(dtype=float).ravel() if tsum_cols else np.array([])
        tsum_vals = tsum_vals[~np.isnan(tsum_vals)]
        axes[3].hist(tsum_vals, bins=60, color="slateblue", alpha=0.8)
        axes[3].set_title("T_sum_meas (all strips)")
        axes[3].set_xlabel("T_sum_meas (ns)")

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
                col = f"T_diff_{plane_idx}_s{strip_idx}"
                if col not in df.columns:
                    ax.axis("off")
                    continue
                vals = df[col].to_numpy(dtype=float)
                vals = vals[~np.isnan(vals)]
                ax.hist(vals, bins=80, color="darkorange", alpha=0.8)
                ax.set_title(f"P{plane_idx} S{strip_idx}")
                ax.set_xlabel("T_diff (ns)")
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
                col = f"T_sum_meas_{plane_idx}_s{strip_idx}"
                if col not in df.columns:
                    ax.axis("off")
                    continue
                vals = df[col].to_numpy(dtype=float)
                vals = vals[~np.isnan(vals)]
                ax.hist(vals, bins=80, color="slateblue", alpha=0.8)
                ax.set_title(f"P{plane_idx} S{strip_idx}")
                ax.set_xlabel("T_sum_meas (ns)")
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
                col = f"Y_mea_{plane_idx}_s{strip_idx}"
                if col not in df.columns:
                    ax.axis("off")
                    continue
                vals = df[col].to_numpy(dtype=float)
                vals = vals[vals > 0]
                ax.hist(vals, bins=80, color="seagreen", alpha=0.8)
                ax.set_title(f"P{plane_idx} S{strip_idx}")
                ax.set_xlabel("qsum")
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
                col = f"q_diff_{plane_idx}_s{strip_idx}"
                if col not in df.columns:
                    ax.axis("off")
                    continue
                vals = df[col].to_numpy(dtype=float)
                vals = vals[vals != 0]
                ax.hist(vals, bins=80, color="steelblue", alpha=0.8)
                ax.set_title(f"P{plane_idx} S{strip_idx}")
                ax.set_xlabel("q_diff")
        for ax in axes.flatten():
            for patch in ax.patches:
                patch.set_rasterized(True)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
    plt.close(fig)


def resolve_c_mm_per_ns(cfg: dict, upstream_meta: dict | None) -> float:
    cfg_value = cfg.get("c_mm_per_ns")
    if cfg_value is not None:
        return float(cfg_value)
    meta = upstream_meta or {}
    while isinstance(meta, dict):
        meta_cfg = meta.get("config", {})
        if "c_mm_per_ns" in meta_cfg:
            return float(meta_cfg["c_mm_per_ns"])
        meta = meta.get("upstream")
    return 299.792458


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 5: compute T_diff and q_diff.")
    parser.add_argument("--config", default="config_step_5_physics.yaml", help="Path to step physics config YAML")
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
    qdiff_width_raw = cfg.get("qdiff_width")
    if qdiff_width_raw in (None, ""):
        raise ValueError("qdiff_width must be set explicitly in config_step_5_physics.yaml.")
    qdiff_width = float(qdiff_width_raw)
    rng = np.random.default_rng(cfg.get("seed"))

    input_glob = cfg.get("input_glob", "**/step_4_chunks.chunks.json")
    input_sim_run = cfg.get("input_sim_run", "latest")

    print("\n-----\nStep 5 starting...\n-----")
    print(f"Input dir: {input_dir}")
    print(f"Output dir: {output_dir}")

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
        plot_signal_summary(df, plot_path)
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
    step_5_id = None
    mesh_dir = Path(cfg.get("param_mesh_dir", "../../SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1"))
    if not mesh_dir.is_absolute():
        mesh_dir = Path(__file__).resolve().parent / mesh_dir

    input_path = None
    for candidate in candidates:
        candidate_iter, candidate_meta, candidate_chunked = iter_input_frames(candidate, chunk_rows)
        candidate_chain = extract_step_id_chain(candidate_meta)
        if not candidate_chain:
            continue
        candidate_step_5_id = select_next_step_id(
            output_dir,
            mesh_dir,
            cfg.get("param_mesh_sim_run", "none"),
            "step_5_id",
            candidate_chain,
            cfg.get("seed"),
            physics_cfg.get("step_5_id"),
        )
        if candidate_step_5_id is None:
            continue
        input_path = candidate
        input_iter = candidate_iter
        upstream_meta = candidate_meta
        chunked_input = candidate_chunked
        step_chain = candidate_chain
        step_5_id = candidate_step_5_id
        break

    if input_path is None or input_iter is None or upstream_meta is None or step_chain is None:
        print("Skipping STEP_5: all step_5_id combinations already exist.")
        return

    normalized_stem = normalize_stem(input_path)
    print(f"Processing: {input_path}")
    sim_run = build_sim_run_name(step_chain + [step_5_id])
    sim_run_dir = output_dir / sim_run
    if not args.force and sim_run_dir.exists():
        print(f"SIM_RUN {sim_run} already exists; skipping (use --force to regenerate).")
        return
    c_mm_per_ns = resolve_c_mm_per_ns(cfg, upstream_meta)

    physics_cfg["step_5_id"] = step_5_id
    sim_run, sim_run_dir, config_hash, upstream_hash, _ = register_sim_run(
        output_dir, "STEP_5", config_path, physics_cfg, upstream_meta, sim_run
    )
    reset_dir(sim_run_dir)

    out_stem_base = "step_5"
    out_stem = f"{out_stem_base}_chunks" if chunk_rows else out_stem_base
    metadata = {
        "created_at": now_iso(),
        "step": "STEP_5",
        "config": physics_cfg,
        "runtime_config": runtime_cfg,
        "sim_run": sim_run,
        "config_hash": config_hash,
        "upstream_hash": upstream_hash,
        "source_dataset": str(input_path),
        "upstream": upstream_meta,
        "step_5_id": step_5_id,
    }
    if chunk_rows:
        def _iter_out() -> Iterable[pd.DataFrame]:
            for chunk in input_iter:
                yield prune_step5(compute_tdiff_qdiff(chunk, c_mm_per_ns, qdiff_width, rng))

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
            plot_signal_summary(plot_df, plot_path)
        print(f"Saved {manifest_path}")
    else:
        df, upstream_meta = load_with_metadata(input_path)
        out = prune_step5(compute_tdiff_qdiff(df, c_mm_per_ns, qdiff_width, rng))
        out_path = sim_run_dir / f"{out_stem}.{output_format}"
        save_with_metadata(out, out_path, metadata, output_format)
        if not args.no_plots:
            plot_dir = sim_run_dir / "PLOTS"
            ensure_dir(plot_dir)
            plot_path = plot_dir / f"{out_path.stem}_plots.pdf"
            plot_signal_summary(out, plot_path)
        print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
