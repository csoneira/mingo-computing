#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_2/step_2_generated_to_crossing.py
Purpose: Step 2: propagate muons through station geometry and compute plane crossings.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_2/step_2_generated_to_crossing.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Tuple

import numpy as np
import pandas as pd
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT_DIR))
sys.path.append(str(ROOT_DIR / "MASTER_STEPS"))

from STEP_SHARED.sim_utils import (
    GEOMETRY_SCHEMA_VERSION,
    RectBounds,
    rect_bounds_to_dict,
    resolve_active_area_bounds,
    ensure_dir,
    extract_param_set,
    extract_param_row_id,
    find_latest_data_path,
    find_sim_run,
    find_sim_run_dir,
    load_step_configs,
    latest_sim_run,
    random_sim_run,
    load_with_metadata,
    now_iso,
    build_sim_run_name,
    register_sim_run,
    resolve_param_mesh,
    resolve_sim_run,
    reset_dir,
    save_with_metadata,
    select_param_row,
)


def calculate_intersections(
    df: pd.DataFrame,
    z_positions: Iterable[float],
    active_area_bounds: RectBounds,
    c_mm_per_ns: float,
) -> pd.DataFrame:
    z_positions = list(z_positions)
    out = df.copy()
    crossing_array = np.full(len(out), "", dtype=object)
    crossing_mask = np.zeros(len(out), dtype=np.uint8)

    theta = out["Theta_gen"].to_numpy(dtype=float)
    tan_theta = np.tan(theta)
    cos_theta = np.cos(theta)
    cos_phi = np.cos(out["Phi_gen"].to_numpy(dtype=float))
    sin_phi = np.sin(out["Phi_gen"].to_numpy(dtype=float))

    for plane_idx, z in enumerate(z_positions, start=1):
        dz = z + out["Z_gen"].to_numpy(dtype=float)
        x_proj = out["X_gen"].to_numpy(dtype=float) + dz * tan_theta * cos_phi
        y_proj = out["Y_gen"].to_numpy(dtype=float) + dz * tan_theta * sin_phi
        t_sum = dz / (c_mm_per_ns * cos_theta)

        in_bounds = (
            (x_proj >= active_area_bounds.x_min)
            & (x_proj <= active_area_bounds.x_max)
            & (y_proj >= active_area_bounds.y_min)
            & (y_proj <= active_area_bounds.y_max)
        )

        out[f"X_gen_{plane_idx}"] = np.where(in_bounds, x_proj, np.nan)
        out[f"Y_gen_{plane_idx}"] = np.where(in_bounds, y_proj, np.nan)
        out[f"Z_gen_{plane_idx}"] = np.where(in_bounds, z, np.nan)
        out[f"T_sum_{plane_idx}_ns"] = np.where(in_bounds, t_sum, np.nan)

        crossing_array[in_bounds] = crossing_array[in_bounds] + str(plane_idx)
        crossing_mask[in_bounds] |= np.uint8(1 << (plane_idx - 1))

    t_sum_cols = [f"T_sum_{idx}_ns" for idx in range(1, len(z_positions) + 1)]
    t_sum_matrix = out[t_sum_cols].to_numpy(dtype=float)
    valid_mask = ~np.isnan(t_sum_matrix)
    min_tsum = np.where(valid_mask, t_sum_matrix, np.inf).min(axis=1)
    min_tsum[~np.isfinite(min_tsum)] = 0.0
    out[t_sum_cols] = t_sum_matrix - min_tsum[:, None]

    crossing_series = pd.Series(crossing_array, dtype="string")
    crossing_series = crossing_series.replace("", pd.NA)
    out["tt_crossing"] = crossing_series
    out["crossing_mask"] = crossing_mask
    return out


def prune_step2(df: pd.DataFrame) -> pd.DataFrame:
    keep = {
        "event_id", "T_thick_s", "X_gen", "Y_gen", "Theta_gen", "Phi_gen",
        "tt_crossing", "crossing_mask",
    }
    for plane_idx in range(1, 5):
        keep.add(f"X_gen_{plane_idx}")
        keep.add(f"Y_gen_{plane_idx}")
        keep.add(f"Z_gen_{plane_idx}")
        keep.add(f"T_sum_{plane_idx}_ns")
    keep_cols = [col for col in df.columns if col in keep]
    return df[keep_cols]


def normalize_positions(z_positions: Tuple[float, float, float, float], normalize: bool) -> np.ndarray:
    z_array = np.array(z_positions, dtype=float)
    if normalize:
        z_array = z_array - z_array[0]
    return z_array


def _normalize_step_id(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return f"{int(float(value)):03d}"
    except (TypeError, ValueError):
        text = str(value).strip()
        return text or None


def plot_geometry_summary(
    df: pd.DataFrame,
    pdf: PdfPages,
    title: str,
    active_area_bounds: RectBounds,
) -> None:
    required = {"Theta_gen", "Phi_gen", "tt_crossing"}
    if not required.issubset(df.columns):
        missing = ", ".join(sorted(required - set(df.columns)))
        print(f"Skipping geometry summary plot (missing columns: {missing})")
        return
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    plane_cols = [(f"X_gen_{i}", f"Y_gen_{i}") for i in range(1, 5)]
    for ax, (x_col, y_col) in zip(axes.flatten(), plane_cols):
        if x_col not in df or y_col not in df:
            ax.axis("off")
            continue
        x = df[x_col].to_numpy()
        y = df[y_col].to_numpy()
        mask = ~np.isnan(x) & ~np.isnan(y)
        ax.scatter(x[mask], y[mask], s=1, alpha=0.2, rasterized=True)
        ax.add_patch(
            Rectangle(
                (active_area_bounds.x_min, active_area_bounds.y_min),
                active_area_bounds.x_max - active_area_bounds.x_min,
                active_area_bounds.y_max - active_area_bounds.y_min,
                fill=False,
                edgecolor="black",
                linewidth=1.2,
                label="active gas area",
            )
        )
        ax.set_xlim(active_area_bounds.x_min, active_area_bounds.x_max)
        ax.set_ylim(active_area_bounds.y_min, active_area_bounds.y_max)
        ax.set_title(f"{x_col} vs {y_col}")
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
    fig.suptitle(title)
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    crossing_values = pd.Series(df["tt_crossing"]).dropna().astype(str)
    for ct in sorted(crossing_values.unique()):
        ct_df = df[df["tt_crossing"] == ct]
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        axes[0].scatter(ct_df["Theta_gen"], ct_df["Phi_gen"], s=6, alpha=0.25, rasterized=True)
        axes[0].set_title(f"Theta vs Phi (tt_crossing={ct})")
        axes[0].set_xlabel("Theta (rad)")
        axes[0].set_ylabel("Phi (rad)")
        axes[0].set_xlim(0, np.pi / 2)
        axes[0].set_ylim(-np.pi, np.pi)

        axes[1].hist2d(ct_df["Theta_gen"], ct_df["Phi_gen"], bins=60, cmap="magma")
        axes[1].set_title(f"Theta vs Phi density (tt_crossing={ct})")
        axes[1].set_xlabel("Theta (rad)")
        axes[1].set_ylabel("Phi (rad)")
        axes[1].set_xlim(0, np.pi / 2)
        axes[1].set_ylim(-np.pi, np.pi)
        fig.tight_layout()
        pdf.savefig(fig, dpi=150)
        plt.close(fig)


def plot_step2_summary(df: pd.DataFrame, pdf: PdfPages) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    axes = axes.flatten()

    x_cols = [c for c in df.columns if c.startswith("X_gen_")]
    x_vals = df[x_cols].to_numpy(dtype=float).ravel() if x_cols else np.array([])
    x_vals = x_vals[~np.isnan(x_vals)]
    axes[0].hist(x_vals, bins=80, color="steelblue", alpha=0.8)
    axes[0].set_title("X_gen_i")

    y_cols = [c for c in df.columns if c.startswith("Y_gen_")]
    y_vals = df[y_cols].to_numpy(dtype=float).ravel() if y_cols else np.array([])
    y_vals = y_vals[~np.isnan(y_vals)]
    axes[1].hist(y_vals, bins=80, color="seagreen", alpha=0.8)
    axes[1].set_title("Y_gen_i")

    t_cols = [c for c in df.columns if c.startswith("T_sum_") and c.endswith("_ns")]
    t_vals = df[t_cols].to_numpy(dtype=float).ravel() if t_cols else np.array([])
    t_vals = t_vals[~np.isnan(t_vals)]
    t_vals = t_vals[t_vals != 0]
    axes[2].hist(t_vals, bins=80, color="darkorange", alpha=0.8)
    axes[2].set_title("T_sum_i_ns")

    counts = df["tt_crossing"].value_counts().sort_index()
    bars = axes[3].bar(counts.index.astype(str), counts.values, color="slateblue", alpha=0.8)
    for patch in bars:
        patch.set_rasterized(True)
    axes[3].set_title("tt_crossing")

    for ax in axes:
        for patch in ax.patches:
            patch.set_rasterized(True)
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def _resolve_input_path(run_dir: Path, input_basename: str | None) -> Path:
    if input_basename:
        input_path = run_dir / input_basename
        if input_path.exists():
            return input_path
        manifest_path = input_path.with_suffix(".chunks.json")
        if manifest_path.exists():
            print(f"Using chunk manifest: {manifest_path}")
            return manifest_path
        chunks_dir = input_path.with_suffix("") / "chunks"
        if chunks_dir.exists():
            manifest_path = chunks_dir.parent.with_suffix(".chunks.json")
            if manifest_path.exists():
                print(f"Using chunk manifest: {manifest_path}")
                return manifest_path
            raise FileNotFoundError(
                f"Found chunks in {chunks_dir} but missing manifest {manifest_path}; run is incomplete."
            )
    candidates = (
        sorted(run_dir.glob("muon_sample_*.chunks.json"))
        + sorted(run_dir.glob("muon_sample_*.pkl"))
        + sorted(run_dir.glob("muon_sample_*.csv"))
    )
    if len(candidates) == 1:
        return candidates[0]
    manifest_candidates = sorted(run_dir.glob("muon_sample_*.chunks.json"))
    if len(manifest_candidates) != 1:
        incomplete_chunks = []
        for chunks_dir in sorted(run_dir.glob("muon_sample_*/chunks")):
            manifest_path = chunks_dir.parent.with_suffix(".chunks.json")
            if not manifest_path.exists():
                incomplete_chunks.append(str(chunks_dir))
        if incomplete_chunks:
            raise FileNotFoundError(
                f"Found chunk directories without manifests in {run_dir}: {', '.join(incomplete_chunks)}."
            )
        raise FileNotFoundError(f"Expected 1 muon_sample file in {run_dir}, found {len(candidates)}.")
    manifest_path = manifest_candidates[0]
    return Path(str(manifest_path)[: -len(".chunks.json")] + ".pkl")


def _load_input_meta(path: Path) -> dict:
    if not path.exists():
        return {}
    if path.name.endswith(".chunks.json"):
        try:
            return json.loads(path.read_text()).get("metadata", {})
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[WARN] Failed to read manifest metadata from {path}: {exc}")
            return {}
    if path.is_dir() and path.name == "chunks":
        manifest_path = path.parent.with_suffix(".chunks.json")
        if manifest_path.exists():
            try:
                return json.loads(manifest_path.read_text()).get("metadata", {})
            except (OSError, json.JSONDecodeError) as exc:
                print(f"[WARN] Failed to read manifest metadata from {manifest_path}: {exc}")
                return {}
        return {}
    if path.is_dir():
        return {}
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[WARN] Failed to read sidecar metadata from {meta_path}: {exc}")
            return {}
    try:
        _, meta = load_with_metadata(path)
    except ValueError:
        return {}
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 2: expand muon sample for each station geometry.")
    parser.add_argument("--config", default="config_step_2_physics.yaml", help="Path to step physics config YAML")
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
    active_area_bounds, active_area_geometry_source = resolve_active_area_bounds(cfg)
    normalized_active_area = rect_bounds_to_dict(active_area_bounds)
    physics_cfg["active_area_bounds_mm"] = normalized_active_area
    cfg["active_area_bounds_mm"] = normalized_active_area

    output_dir = Path(cfg["output_dir"])
    if not output_dir.is_absolute():
        output_dir = Path(__file__).resolve().parent / output_dir
    ensure_dir(output_dir)

    output_format = str(cfg.get("output_format", "pkl")).lower()

    if args.plot_only:
        if args.no_plots:
            print("Plot-only requested with --no-plots; skipping plots.")
            return
        latest_path = find_latest_data_path(output_dir)
        if latest_path is None:
            raise FileNotFoundError(f"No existing outputs found in {output_dir} for plot-only.")
        print(f"Plot-only: {latest_path}")
        df, _ = load_with_metadata(latest_path)
        if "tt_crossing" in df.columns:
            df = df[df["tt_crossing"].notna()].reset_index(drop=True)
        sim_run_dir = find_sim_run_dir(latest_path)
        plot_dir = (sim_run_dir or latest_path.parent) / "PLOTS"
        ensure_dir(plot_dir)
        plot_path = plot_dir / f"{latest_path.stem}_plots.pdf"
        with PdfPages(plot_path) as pdf:
            plot_geometry_summary(df, pdf, latest_path.stem, active_area_bounds)
            plot_step2_summary(df, pdf)
        print(f"Saved {plot_path}")
        return

    input_path_cfg = cfg.get("input_muon_sample")
    input_candidates = []
    input_sim_run_mode = None
    if input_path_cfg:
        input_path = Path(input_path_cfg).expanduser()
        if not input_path.is_absolute():
            input_path = Path(__file__).resolve().parent / input_path
        input_candidates = [(input_path, None)]
    else:
        input_dir = Path(cfg["input_dir"])
        if not input_dir.is_absolute():
            input_dir = Path(__file__).resolve().parent / input_dir
        input_sim_run_mode = cfg.get("input_sim_run", "latest")
        input_basename = cfg.get("input_basename")
        sim_run_dirs = sorted(input_dir.glob("SIM_RUN_*"))
        if not sim_run_dirs:
            raise FileNotFoundError(f"No SIM_RUN_* directories found in {input_dir}.")
        if input_sim_run_mode == "latest":
            sim_run_dirs = sorted(sim_run_dirs, key=lambda path: path.stat().st_mtime, reverse=True)
        elif input_sim_run_mode == "random":
            mesh_dir = Path(cfg.get("param_mesh_dir", "../../SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1"))
            if not mesh_dir.is_absolute():
                mesh_dir = Path(__file__).resolve().parent / mesh_dir
            try:
                mesh, _ = resolve_param_mesh(mesh_dir, cfg.get("param_mesh_sim_run", "none"), cfg.get("seed"))
            except FileNotFoundError:
                mesh = None
            fully_done_step1 = set()
            if mesh is not None:
                tmp = mesh.copy()
                tmp["done"] = tmp.get("done", 0).fillna(0).astype(int)
                if "step_1_id" not in tmp.columns:
                    tmp["step_1_id"] = 1
                grouped = tmp.groupby("step_1_id")["done"].apply(lambda s: (s == 1).all())
                fully_done_step1 = set(int(val) for val in grouped[grouped].index.tolist())
            rng = np.random.default_rng(cfg.get("seed"))
            rng.shuffle(sim_run_dirs)
        else:
            sim_run_dirs = [input_dir / str(input_sim_run_mode)]
        for sim_run_dir in sim_run_dirs:
            try:
                candidate_path = _resolve_input_path(sim_run_dir, input_basename)
            except FileNotFoundError:
                continue
            if input_sim_run_mode == "random":
                meta = _load_input_meta(candidate_path)
                if not meta:
                    continue
                step1_id = meta.get("step_1_id")
                try:
                    step1_id_norm = int(float(step1_id))
                except (TypeError, ValueError):
                    step1_id_norm = None
                if step1_id_norm is not None and step1_id_norm in fully_done_step1:
                    continue
            input_candidates.append((candidate_path, sim_run_dir.name))
        if not input_candidates:
            if input_sim_run_mode == "random":
                raise ValueError("No available input SIM_RUNs with param_row_id not marked done.")
            raise FileNotFoundError(f"No inputs found under {input_dir}.")
    normalize = bool(runtime_cfg.get("normalize_to_first_plane", True))
    chunk_rows = cfg.get("chunk_rows")
    rng = np.random.default_rng(cfg.get("seed"))
    plot_sample_rows = cfg.get("plot_sample_rows")
    print("\n-----\nStep 2 starting...\n-----")
    print(f"Output dir: {output_dir}")
    if args.plot_only:
        if args.no_plots:
            print("Plot-only requested with --no-plots; skipping plots.")
            return
        latest_path = find_latest_data_path(output_dir)
        if latest_path is None:
            raise FileNotFoundError(f"No existing outputs found in {output_dir} for plot-only.")
        print(f"Plot-only: {latest_path}")
        df, _ = load_with_metadata(latest_path)
        if "tt_crossing" in df.columns:
            df = df[df["tt_crossing"].notna()].reset_index(drop=True)
        sim_run_dir = find_sim_run_dir(latest_path)
        plot_dir = (sim_run_dir or latest_path.parent) / "PLOTS"
        ensure_dir(plot_dir)
        plot_path = plot_dir / f"{latest_path.stem}_plots.pdf"
        with PdfPages(plot_path) as pdf:
            plot_geometry_summary(df, pdf, latest_path.stem, active_area_bounds)
            plot_step2_summary(df, pdf)
        print(f"Saved {plot_path}")
        return

    input_path = None
    upstream_meta = None
    manifest = None
    muon_df = None
    stream_csv = False
    stream_chunks = False
    chunk_manifest = None
    c_mm_per_ns = None
    param_row = None
    param_mesh_path = None
    param_set_id = None
    param_date = None
    param_row_id = None
    step_1_id = None
    step_2_id = None
    z_values = None

    for candidate_path, candidate_sim_run in input_candidates:
        stream_csv = bool(chunk_rows) and candidate_path.suffix == ".csv" and output_format == "csv"
        if candidate_path.name.endswith(".chunks.json"):
            chunk_manifest = candidate_path
        else:
            chunk_manifest = candidate_path.with_suffix(".chunks.json")
        stream_chunks = chunk_manifest.exists()

        if stream_csv:
            meta_path = candidate_path.with_suffix(candidate_path.suffix + ".meta.json")
            upstream_meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            manifest = None
            muon_df = None
        elif stream_chunks:
            try:
                manifest = json.loads(chunk_manifest.read_text())
            except (json.JSONDecodeError, OSError) as exc:
                print(f"[WARN] Skipping unreadable chunk manifest {chunk_manifest}: {exc}")
                continue
            chunk_list = manifest.get("chunks", [])
            if not isinstance(chunk_list, list) or not chunk_list:
                print(f"[WARN] Skipping empty chunk manifest {chunk_manifest}")
                continue
            upstream_meta = manifest.get("metadata", {})
            muon_df = None
        else:
            muon_df, upstream_meta = load_with_metadata(candidate_path)
            manifest = None

        if not args.force:
            existing = find_sim_run(output_dir, physics_cfg, upstream_meta)
            if existing:
                # If multiple input candidates exist, try the next candidate.
                if len(input_candidates) > 1:
                    print(f"[DEBUG] existing STEP_2 sim_run {existing} for this upstream input; trying next candidate")
                    continue
                # If there is only a single upstream input candidate, allow param_mesh-driven
                # selection to proceed so we can create additional STEP_2 outputs (different step_2_id)
                # for the same upstream input. The later existence checks (per sim_run_candidate)
                # will prevent creating duplicates.
                print(f"[DEBUG] Found existing STEP_2 sim_run {existing} for this upstream input — continuing to search param_mesh for missing step_2 outputs.")

        c_mm_per_ns = float(
            cfg.get("c_mm_per_ns", upstream_meta.get("config", {}).get("c_mm_per_ns", 299.792458))
        )
        z_positions_cfg = cfg.get("z_positions")
        param_set_id, param_date = extract_param_set(upstream_meta)
        param_row_id = extract_param_row_id(upstream_meta)
        step_1_id = _normalize_step_id(upstream_meta.get("step_1_id"))
        step_2_id = None
        param_mesh_path = None
        param_row = None
        if z_positions_cfg is None:
            raise ValueError("config z_positions is required for Step 2.")
        if isinstance(z_positions_cfg, str) and z_positions_cfg.lower() == "random":
            mesh_dir = Path(cfg.get("param_mesh_dir", "../../SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1"))
            if not mesh_dir.is_absolute():
                mesh_dir = Path(__file__).resolve().parent / mesh_dir
            mesh, mesh_path = resolve_param_mesh(
                mesh_dir, cfg.get("param_mesh_sim_run", "none"), cfg.get("seed")
            )
            mesh = mesh.copy()
            mesh["done"] = mesh.get("done", 0).fillna(0).astype(int)
            step_1_id_norm = None
            if step_1_id is not None:
                try:
                    step_1_id_norm = int(float(step_1_id))
                except (TypeError, ValueError):
                    step_1_id_norm = None
            if step_1_id_norm is not None and "step_1_id" in mesh.columns:
                mesh_candidates = mesh[
                    (mesh["step_1_id"].astype(int) == step_1_id_norm) & (mesh["done"] != 1)
                ]
            else:
                mesh_candidates = mesh[mesh["done"] != 1]
            if mesh_candidates.empty:
                continue
            mesh_candidates = mesh_candidates.reset_index(drop=True)
            start_idx = int(rng.integers(0, len(mesh_candidates)))
            order = list(range(start_idx, len(mesh_candidates))) + list(range(0, start_idx))
            for idx in order:
                row = mesh_candidates.iloc[idx]
                step_2_id_candidate = _normalize_step_id(row.get("step_2_id"))
                if not step_1_id or not step_2_id_candidate:
                    continue
                sim_run_candidate = build_sim_run_name([step_1_id, step_2_id_candidate])
                print(f"[DEBUG] mesh(random) check: sim_run_candidate={sim_run_candidate} exists={(output_dir / sim_run_candidate).exists()} (output_dir={output_dir})")
                if not (output_dir / sim_run_candidate).exists():
                    param_row = row
                    step_2_id = step_2_id_candidate
                    break
            if param_row is None:
                continue
            if not step_1_id and "step_1_id" in param_row.index:
                step_1_id = _normalize_step_id(param_row.get("step_1_id"))
            if "param_set_id" in param_row.index and pd.notna(param_row["param_set_id"]):
                param_set_id = int(param_row["param_set_id"])
            if "param_date" in param_row:
                param_date = str(param_row["param_date"])
            param_row_id = int(param_row.name)
            param_mesh_path = mesh_path
            required_cols = ["z_p1", "z_p2", "z_p3", "z_p4"]
            if not all(col in param_row.index for col in required_cols):
                raise ValueError("param_mesh.csv is missing z_p1..z_p4 required for geometry selection.")
            z_values = [float(param_row[col]) for col in required_cols]
            physics_cfg["z_positions"] = z_values
            cfg["z_positions"] = z_values
            print(f"Selected z_positions from mesh (param_set_id={param_set_id})")
        else:
            if isinstance(z_positions_cfg, (list, tuple)) and len(z_positions_cfg) == 4:
                z_values = [float(v) for v in z_positions_cfg]
                physics_cfg["z_positions"] = z_values
                cfg["z_positions"] = z_values
                param_set_id = None
                param_date = None
                mesh_dir = Path(cfg.get("param_mesh_dir", "../../SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1"))
                if not mesh_dir.is_absolute():
                    mesh_dir = Path(__file__).resolve().parent / mesh_dir
                mesh, mesh_path = resolve_param_mesh(
                    mesh_dir, cfg.get("param_mesh_sim_run", "none"), cfg.get("seed")
                )
                mesh = mesh.copy()
                mesh["done"] = mesh.get("done", 0).fillna(0).astype(int)
                param_mesh_path = mesh_path
                required_cols = ["z_p1", "z_p2", "z_p3", "z_p4"]
                if not all(col in mesh.columns for col in required_cols):
                    raise ValueError("param_mesh.csv is missing z_p1..z_p4 required for geometry selection.")

                z_frame = mesh[required_cols].apply(pd.to_numeric, errors="coerce")
                z_target = np.array(z_values, dtype=float)
                z_match = np.isclose(
                    z_frame.to_numpy(dtype=float),
                    z_target[np.newaxis, :],
                    rtol=0.0,
                    atol=1e-6,
                ).all(axis=1)

                if step_1_id and "step_1_id" in mesh.columns:
                    step1_match = mesh["step_1_id"].apply(_normalize_step_id) == step_1_id
                else:
                    step1_match = pd.Series(True, index=mesh.index)

                mesh_candidates = mesh[z_match & step1_match & (mesh["done"] != 1)]
                if mesh_candidates.empty:
                    mesh_candidates = mesh[z_match & step1_match]
                if mesh_candidates.empty and step_1_id and "step_1_id" in mesh.columns:
                    mesh_candidates = mesh[z_match & (mesh["done"] != 1)]
                    if mesh_candidates.empty:
                        mesh_candidates = mesh[z_match]
                if mesh_candidates.empty:
                    raise ValueError(
                        f"No param_mesh rows match fixed z_positions={z_values}."
                    )

                candidate_indices = mesh_candidates.index.tolist()
                start_idx = int(rng.integers(0, len(candidate_indices)))
                order = list(range(start_idx, len(candidate_indices))) + list(range(0, start_idx))
                for idx in order:
                    row_idx = candidate_indices[idx]
                    row = mesh.loc[row_idx]
                    step_1_candidate = step_1_id or _normalize_step_id(row.get("step_1_id"))
                    step_2_candidate = _normalize_step_id(row.get("step_2_id"))
                    if not step_1_candidate or not step_2_candidate:
                        continue
                    sim_run_candidate = build_sim_run_name([step_1_candidate, step_2_candidate])
                    print(f"[DEBUG] mesh(fixed) check: sim_run_candidate={sim_run_candidate} exists={(output_dir / sim_run_candidate).exists()} (output_dir={output_dir})")
                    if not (output_dir / sim_run_candidate).exists():
                        param_row = row
                        param_row_id = int(row_idx)
                        step_1_id = step_1_candidate
                        step_2_id = step_2_candidate
                        break
                if param_row is None:
                    continue
            else:
                raise ValueError("z_positions must be 'random' or a 4-value list [z1, z2, z3, z4].")

        if step_2_id is None and param_row is not None and "step_2_id" in param_row.index:
            step_2_id = _normalize_step_id(param_row.get("step_2_id"))
        if not step_1_id and param_row is not None and "step_1_id" in param_row.index:
            step_1_id = _normalize_step_id(param_row.get("step_1_id"))
        if not step_1_id or not step_2_id:
            raise ValueError("step_1_id or step_2_id missing; ensure param_mesh.csv has step IDs.")
        cfg["step_1_id"] = step_1_id
        cfg["step_2_id"] = step_2_id

        input_path = candidate_path
        if input_sim_run_mode == "random" and candidate_sim_run:
            print(f"Selected input SIM_RUN: {candidate_sim_run}")
        break

    if input_path is None:
        print("Skipping STEP_2: all step_2_id combinations already exist.")
        return

    print(f"Input: {input_path}")
    print(f"c_mm_per_ns: {c_mm_per_ns}")
    z_positions = normalize_positions(tuple(z_values), normalize)
    print(f"z_positions={z_positions.tolist()}")

    sim_run = build_sim_run_name([step_1_id, step_2_id])
    sim_run_dir = output_dir / sim_run
    if not args.force and sim_run_dir.exists():
        print(f"SIM_RUN {sim_run} already exists; skipping (use --force to regenerate).")
        return
    sim_run, sim_run_dir, config_hash, upstream_hash, _ = register_sim_run(
        output_dir, "STEP_2", config_path, cfg, upstream_meta, sim_run
    )
    reset_dir(sim_run_dir)
    out_stem_base = "step_2"
    out_name = f"{out_stem_base}.{output_format}"
    out_path = sim_run_dir / out_name
    metadata = {
        "created_at": now_iso(),
        "step": "STEP_2",
        "geometry_schema_version": GEOMETRY_SCHEMA_VERSION,
        "active_area_bounds_mm": normalized_active_area,
        "active_area_geometry_source": active_area_geometry_source,
        "config": physics_cfg,
        "runtime_config": runtime_cfg,
        "sim_run": sim_run,
        "config_hash": config_hash,
        "upstream_hash": upstream_hash,
        "z_positions_mm": [float(z) for z in z_positions],
        "z_positions_raw_mm": [float(v) for v in z_values],
        "param_set_id": param_set_id,
        "param_date": param_date,
        "param_row_id": param_row_id,
        "step_1_id": step_1_id,
        "step_2_id": step_2_id,
        "param_mesh_path": str(param_mesh_path) if param_mesh_path else None,
        "upstream": upstream_meta,
    }

    if stream_chunks or stream_csv:
        if output_format not in ("csv", "pkl"):
            raise ValueError("Chunked input requires output_format=csv or pkl.")

        out_stem = f"{out_stem_base}_chunks"
        chunks_dir = sim_run_dir / out_stem
        ensure_dir(chunks_dir)
        chunk_paths = []
        buffer = []
        buffered_rows = 0
        total_rows = 0
        full_chunks = 0
        last_full_chunk = None

        def flush_chunk(chunk_df: pd.DataFrame) -> None:
            nonlocal full_chunks, last_full_chunk
            chunk_path = chunks_dir / f"part_{full_chunks:04d}.{output_format}"
            if output_format == "csv":
                chunk_df.to_csv(chunk_path, index=False)
            else:
                chunk_df.to_pickle(chunk_path)
            chunk_paths.append(str(chunk_path))
            full_chunks += 1
            last_full_chunk = chunk_df

        def maybe_flush_buffer() -> None:
            nonlocal buffer, buffered_rows
            while buffered_rows >= int(chunk_rows):
                chunk_df = pd.concat(buffer, ignore_index=True)
                out_df = chunk_df.iloc[: int(chunk_rows)].copy()
                remainder = chunk_df.iloc[int(chunk_rows):].copy()
                flush_chunk(out_df)
                buffer = [remainder] if not remainder.empty else []
                buffered_rows = len(remainder)

        if stream_csv:
            chunk_iter = (pd.read_csv(input_path, chunksize=int(chunk_rows)), None)
        else:
            chunk_iter = (manifest.get("chunks", []), "pkl")

        processed_chunks = 0
        skipped_chunks = 0
        for item in chunk_iter[0]:
            processed_chunks += 1
            if chunk_iter[1] == "pkl":
                print(f"Processing chunk {processed_chunks}/{len(manifest.get('chunks', []))}")
            else:
                print(f"Processing chunk {processed_chunks}")
            if chunk_iter[1] == "pkl":
                chunk_path = Path(item)
                try:
                    chunk_df = pd.read_pickle(chunk_path)
                except (FileNotFoundError, OSError) as exc:
                    skipped_chunks += 1
                    print(f"[WARN] Skipping missing/unreadable chunk {chunk_path}: {exc}")
                    continue
            else:
                chunk_df = item
            geom_chunk = calculate_intersections(chunk_df, z_positions, active_area_bounds, c_mm_per_ns)
            if "tt_crossing" in geom_chunk.columns:
                geom_chunk = geom_chunk[geom_chunk["tt_crossing"].notna()].reset_index(drop=True)
            geom_chunk = prune_step2(geom_chunk)
            total_rows += len(geom_chunk)
            if not geom_chunk.empty:
                buffer.append(geom_chunk)
                buffered_rows += len(geom_chunk)
                maybe_flush_buffer()
            if processed_chunks % 10 == 0:
                print(f"Chunks processed: {processed_chunks}, rows kept so far: {total_rows:,}")
        if skipped_chunks:
            print(f"[WARN] STEP_2 skipped {skipped_chunks} missing/unreadable chunks.")

        if buffered_rows > 0:
            flush_chunk(pd.concat(buffer, ignore_index=True))
            buffered_rows = 0
            buffer = []

        metadata["row_count"] = total_rows
        manifest_out = {
            "version": 1,
            "chunks": chunk_paths,
            "row_count": metadata["row_count"],
            "metadata": metadata,
        }
        manifest_path = sim_run_dir / f"{out_stem}.chunks.json"
        manifest_path.write_text(json.dumps(manifest_out, indent=2))

        if not args.no_plots:
            if plot_sample_rows and last_full_chunk is not None:
                sample_n = len(last_full_chunk) if plot_sample_rows is True else int(plot_sample_rows)
                sample_n = min(sample_n, len(last_full_chunk))
                sample_df = last_full_chunk.sample(n=sample_n, random_state=0)
                plot_dir = sim_run_dir / "PLOTS"
                ensure_dir(plot_dir)
                plot_path = plot_dir / f"{out_stem_base}_plots.pdf"
                with PdfPages(plot_path) as pdf:
                    plot_geometry_summary(sample_df, pdf, f"Step 2 (sample)", active_area_bounds)
                    plot_step2_summary(sample_df, pdf)
            else:
                print("Chunked mode enabled; skipping plots to limit memory usage.")
    else:
        geom_df = calculate_intersections(muon_df, z_positions, active_area_bounds, c_mm_per_ns)
        if "tt_crossing" in geom_df.columns:
            geom_df = geom_df[geom_df["tt_crossing"].notna()].reset_index(drop=True)
        geom_df = prune_step2(geom_df)

        save_with_metadata(geom_df, out_path, metadata, output_format)
        if not args.no_plots:
            plot_dir = sim_run_dir / "PLOTS"
            ensure_dir(plot_dir)
            plot_path = plot_dir / f"{out_stem_base}_plots.pdf"
            with PdfPages(plot_path) as pdf:
                plot_geometry_summary(geom_df, pdf, "Step 2", active_area_bounds)
                plot_step2_summary(geom_df, pdf)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
