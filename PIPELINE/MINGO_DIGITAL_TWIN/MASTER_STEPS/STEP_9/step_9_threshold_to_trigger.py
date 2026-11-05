#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_9/step_9_threshold_to_trigger.py
Purpose: Step 9: evaluate trigger combinations and retain passing events.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_9/step_9_threshold_to_trigger.py [options]
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
from typing import List

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
    extract_param_row_id,
    extract_param_set,
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
    resolve_param_mesh,
    extract_step_id_chain,
    select_param_row,
    select_next_step_id,
    resolve_sim_run,
    reset_dir,
    save_with_metadata,
    write_chunked_output,
)


def normalize_tt(series: pd.Series) -> pd.Series:
    tt = series.astype("string").fillna("")
    tt = tt.str.strip()
    tt = tt.str.replace(r"\.0$", "", regex=True)
    tt = tt.replace({"0": "", "0.0": "", "nan": "", "<NA>": ""})
    return tt


def _normalize_trigger_value(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "<na>"}:
        return None
    if text.endswith(".0"):
        text = text[:-2]
    text = "".join(ch for ch in text if ch.isdigit())
    if not text or set(text) == {"0"}:
        return None
    return text


def resolve_trigger_combinations_for_input(
    upstream_meta: dict,
    mesh_dir: Path,
    mesh_sim_run: str | None,
    seed: int | None,
    fallback_triggers: list[str],
) -> tuple[list[str], str]:
    param_row_id = extract_param_row_id(upstream_meta)
    param_set_id, _ = extract_param_set(upstream_meta)
    if param_row_id is None and param_set_id is None:
        return fallback_triggers, "config_fallback"
    try:
        mesh, _ = resolve_param_mesh(mesh_dir, mesh_sim_run, seed)
        param_row = select_param_row(mesh, np.random.default_rng(seed), param_set_id, param_row_id)
    except Exception:
        return fallback_triggers, "config_fallback"

    trigger_cols = ["trigger_c1", "trigger_c2", "trigger_c3", "trigger_c4"]
    if not all(col in param_row.index for col in trigger_cols):
        return fallback_triggers, "config_fallback"

    resolved: list[str] = []
    for col in trigger_cols:
        trig = _normalize_trigger_value(param_row.get(col))
        if trig and trig not in resolved:
            resolved.append(trig)
    if not resolved:
        return fallback_triggers, "config_fallback"
    return resolved, "param_mesh"


CROSSING_MASK_COLUMN = "crossing_mask"
CROSSING_COUNTER_COLUMN = "sim_crossing_cumulative_count"
UNIT_TRIGGER_COUNTER_COLUMN = "sim_unit_efficiency_trigger_cumulative_count"
_UNIT_TRIGGER_PASS_COLUMN = "_sim_unit_efficiency_trigger_pass"


def trigger_plane_mask(trigger: str) -> int | None:
    """Return the four-plane bitmask required by one trigger combination."""
    required = 0
    for character in str(trigger):
        if character not in "1234":
            return None
        required |= 1 << (int(character) - 1)
    return required or None


def geometric_trigger_passes(
    crossing_masks: pd.Series, triggers: List[str],
) -> pd.Series:
    """Evaluate the configured trigger using geometry only (unit efficiency)."""
    numeric = pd.to_numeric(crossing_masks, errors="coerce")
    if numeric.isna().any():
        raise ValueError("crossing_mask contains missing or non-numeric values")
    values = numeric.to_numpy(dtype=np.uint8)
    passes = np.zeros(len(values), dtype=bool)
    for trigger in triggers:
        required = trigger_plane_mask(trigger)
        if required is not None:
            passes |= (values & np.uint8(required)) == np.uint8(required)
    return pd.Series(passes, index=crossing_masks.index, dtype=bool)


class GeometricRateCounter:
    """Attach chunk-continuous crossing and ideal-trigger cumulative counters."""

    def __init__(self) -> None:
        self.available: bool | None = None
        self.crossing_total = 0
        self.unit_trigger_total = 0
        self.actual_trigger_total = 0
        self.reason: str | None = None

    def annotate(self, frame: pd.DataFrame, triggers: List[str]) -> pd.DataFrame:
        has_mask = CROSSING_MASK_COLUMN in frame.columns
        if self.available is None:
            self.available = has_mask
        elif self.available != has_mask:
            raise ValueError(
                "Inconsistent crossing_mask presence across STEP 9 input chunks"
            )
        if not has_mask:
            self.reason = "legacy input has no crossing_mask"
            return frame

        out = frame.copy()
        masks = pd.to_numeric(out[CROSSING_MASK_COLUMN], errors="coerce")
        if (
            masks.isna().any()
            or (~masks.between(1, 15)).any()
            or ((masks % 1) != 0).any()
        ):
            raise ValueError("crossing_mask must contain integer values from 1 to 15")
        ideal = geometric_trigger_passes(masks, triggers)
        row_count = len(out)
        out[CROSSING_COUNTER_COLUMN] = np.arange(
            self.crossing_total + 1,
            self.crossing_total + row_count + 1,
            dtype=np.int64,
        )
        out[UNIT_TRIGGER_COUNTER_COLUMN] = (
            ideal.to_numpy(dtype=np.int64).cumsum() + self.unit_trigger_total
        )
        out[_UNIT_TRIGGER_PASS_COLUMN] = ideal.to_numpy(dtype=bool)
        self.crossing_total += row_count
        self.unit_trigger_total += int(ideal.sum())
        return out

    def record_actual(self, count: int) -> None:
        self.actual_trigger_total += int(count)

    def summary(self) -> dict[str, object]:
        return {
            "version": 1,
            "status": "available" if self.available else "unavailable",
            "reason": self.reason,
            "crossing_rows": int(self.crossing_total),
            "unit_efficiency_trigger_rows": int(self.unit_trigger_total),
            "actual_trigger_rows": int(self.actual_trigger_total),
        }


def passes_trigger(tt_value: str, triggers: List[str]) -> bool:
    for trig in triggers:
        if all(ch in tt_value for ch in trig):
            return True
    return False


def apply_trigger(
    df: pd.DataFrame,
    triggers: List[str],
    rate_counter: GeometricRateCounter | None = None,
) -> pd.DataFrame:
    out = df.copy()
    if rate_counter is not None:
        out = rate_counter.annotate(out, triggers)
    n = len(out)
    tt_array = ["" for _ in range(n)]

    for plane_idx in range(1, 5):
        plane_active = pd.Series(False, index=out.index)
        for strip_idx in range(1, 5):
            qf = out.get(f"Q_front_{plane_idx}_s{strip_idx}")
            qb = out.get(f"Q_back_{plane_idx}_s{strip_idx}")
            if qf is None and qb is None:
                continue
            active = pd.Series(False, index=out.index)
            if qf is not None:
                active |= qf.to_numpy(dtype=float) > 0
            if qb is not None:
                active |= qb.to_numpy(dtype=float) > 0
            plane_active |= active
        tt_array = [tt + str(plane_idx) if active else tt for tt, active in zip(tt_array, plane_active)]

    tt_series = normalize_tt(pd.Series(tt_array, index=out.index))
    keep_mask = tt_series.apply(lambda val: passes_trigger(val, triggers))
    if _UNIT_TRIGGER_PASS_COLUMN in out.columns:
        incompatible = keep_mask & ~out[_UNIT_TRIGGER_PASS_COLUMN]
        if incompatible.any():
            raise ValueError(
                "Actual STEP 9 trigger accepted events that do not satisfy the "
                "unit-efficiency geometrical trigger"
            )
    filtered = out[keep_mask].copy()
    filtered["tt_trigger"] = tt_series[keep_mask].values
    filtered = filtered.drop(columns=[_UNIT_TRIGGER_PASS_COLUMN], errors="ignore")
    if rate_counter is not None:
        rate_counter.record_actual(len(filtered))
    return filtered


def prune_step9(df: pd.DataFrame) -> pd.DataFrame:
    keep = {
        "event_id", "T_thick_s", "X_gen", "Y_gen", "Theta_gen", "Phi_gen",
        "tt_trigger", CROSSING_COUNTER_COLUMN, UNIT_TRIGGER_COUNTER_COLUMN,
    }
    for plane_idx in range(1, 5):
        for strip_idx in range(1, 5):
            keep.add(f"T_front_{plane_idx}_s{strip_idx}")
            keep.add(f"T_back_{plane_idx}_s{strip_idx}")
            keep.add(f"Q_front_{plane_idx}_s{strip_idx}")
            keep.add(f"Q_back_{plane_idx}_s{strip_idx}")
    keep_cols = [col for col in df.columns if col in keep]
    return df[keep_cols]


def plot_trigger_summary(df: pd.DataFrame, output_path: Path) -> None:
    with PdfPages(output_path) as pdf:
        fig, ax = plt.subplots(figsize=(8, 6))
        counts = normalize_tt(df["tt_trigger"]).value_counts().sort_index()
        bars = ax.bar(counts.index, counts.values, color="steelblue", alpha=0.8)
        for patch in bars:
            patch.set_rasterized(True)
        ax.set_title("tt_trigger counts")
        ax.set_xlabel("tt_trigger")
        ax.set_ylabel("Counts")
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
    parser = argparse.ArgumentParser(description="Step 9: apply trigger combinations based on channel activity.")
    parser.add_argument("--config", default="config_step_9_physics.yaml", help="Path to step physics config YAML")
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
    rng = np.random.default_rng(cfg.get("seed"))
    configured_triggers = [str(t) for t in cfg.get("trigger_combinations", [])]

    input_glob = cfg.get("input_glob", "**/step_8_chunks.chunks.json")
    input_sim_run = cfg.get("input_sim_run", "latest")

    print("\n-----\nStep 9 starting...\n-----")
    print(f"Input dir: {input_dir}")
    print(f"Output dir: {output_dir}")
    print(f"Configured triggers: {configured_triggers}")

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
        plot_trigger_summary(df, plot_path)
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
    step_9_id = None
    input_path = None
    mesh_dir = Path(cfg.get("param_mesh_dir", "../../SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1"))
    if not mesh_dir.is_absolute():
        mesh_dir = Path(__file__).resolve().parent / mesh_dir

    for candidate in candidates:
        candidate_iter, candidate_meta, candidate_chunked = iter_input_frames(candidate, chunk_rows)
        candidate_chain = extract_step_id_chain(candidate_meta)
        if not candidate_chain:
            continue
        candidate_step_9_id = select_next_step_id(
            output_dir,
            mesh_dir,
            cfg.get("param_mesh_sim_run", "none"),
            "step_9_id",
            candidate_chain,
            cfg.get("seed"),
            physics_cfg.get("step_9_id"),
        )
        if candidate_step_9_id is None:
            continue
        input_path = candidate
        input_iter = candidate_iter
        upstream_meta = candidate_meta
        chunked_input = candidate_chunked
        step_chain = candidate_chain
        step_9_id = candidate_step_9_id
        break

    if input_path is None or input_iter is None or upstream_meta is None or step_chain is None or step_9_id is None:
        print("Skipping STEP_9: all step_9_id combinations already exist.")
        return

    triggers, trigger_source = resolve_trigger_combinations_for_input(
        upstream_meta,
        mesh_dir,
        cfg.get("param_mesh_sim_run", "none"),
        cfg.get("seed"),
        configured_triggers,
    )
    normalized_stem = normalize_stem(input_path)
    print(f"Processing: {input_path}")
    print(f"Resolved triggers ({trigger_source}): {triggers}")
    sim_run = build_sim_run_name(step_chain + [step_9_id])
    sim_run_dir = output_dir / sim_run
    if not args.force and sim_run_dir.exists():
        print(f"SIM_RUN {sim_run} already exists; skipping (use --force to regenerate).")
        return

    physics_cfg["step_9_id"] = step_9_id
    physics_cfg["trigger_combinations"] = triggers
    sim_run, sim_run_dir, config_hash, upstream_hash, _ = register_sim_run(
        output_dir, "STEP_9", config_path, physics_cfg, upstream_meta, sim_run
    )
    reset_dir(sim_run_dir)

    out_stem_base = "step_9"
    out_stem = f"{out_stem_base}_chunks" if chunk_rows else out_stem_base
    metadata = {
        "created_at": now_iso(),
        "step": "STEP_9",
        "config": physics_cfg,
        "runtime_config": runtime_cfg,
        "sim_run": sim_run,
        "config_hash": config_hash,
        "upstream_hash": upstream_hash,
        "source_dataset": str(input_path),
        "upstream": upstream_meta,
        "step_9_id": step_9_id,
        "trigger_combinations": triggers,
        "trigger_source": trigger_source,
    }
    rate_counter = GeometricRateCounter()
    if chunk_rows:
        def _iter_out() -> Iterable[pd.DataFrame]:
            for chunk in input_iter:
                yield prune_step9(apply_trigger(chunk, triggers, rate_counter))
            metadata["geometric_rate_counters"] = rate_counter.summary()

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
            plot_trigger_summary(plot_df, plot_path)
        print(f"Saved {manifest_path}")
    else:
        df, upstream_meta = load_with_metadata(input_path)
        filtered = prune_step9(apply_trigger(df, triggers, rate_counter))
        metadata["geometric_rate_counters"] = rate_counter.summary()
        out_path = sim_run_dir / f"{out_stem}.{output_format}"
        save_with_metadata(filtered, out_path, metadata, output_format)
        if not args.no_plots:
            plot_dir = sim_run_dir / "PLOTS"
            ensure_dir(plot_dir)
            plot_path = plot_dir / f"{out_path.stem}_plots.pdf"
            plot_trigger_summary(filtered, plot_path)
        print(f"Saved {out_path} (kept {len(filtered):,}/{len(df):,})")


if __name__ == "__main__":
    main()
