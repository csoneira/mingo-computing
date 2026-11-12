#!/usr/bin/env python3

"""Step 1: generate primary muon parameters (x, y, z, theta, phi) in batch form."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

_TWIN_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_TWIN_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_TWIN_BOOTSTRAP_ROOT))
from ORCHESTRATOR.lib.paths import digital_twin_root, repository_root
ROOT_DIR = digital_twin_root()
sys.path.append(str(ROOT_DIR))
sys.path.append(str(ROOT_DIR / "MASTER_STEPS"))

from STEP_SHARED.sim_utils import (
    ensure_dir,
    find_sim_run,
    load_step_configs,
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


def build_time_rng(seed: Optional[int]) -> np.random.Generator:
    if seed is None:
        return np.random.default_rng()
    return np.random.default_rng(int(seed) + 1)


def generate_muon_sample(
    n_tracks: int,
    xlim: float,
    ylim: float,
    z_plane: float,
    cos_n: float,
    seed: Optional[int],
    thick_rate_hz: float | None = None,
    drop_last_second: bool = False,
    batch_size: int = 200_000,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    time_rng = build_time_rng(seed)
    exponent = 1.0 / (cos_n + 1.0)

    if thick_rate_hz and thick_rate_hz > 0:
        t_thick_s = generate_thick_times(n_tracks, float(thick_rate_hz), time_rng)
    else:
        t_thick_s = np.zeros(n_tracks, dtype=float)

    x_out = np.empty(n_tracks)
    y_out = np.empty(n_tracks)
    z_out = np.full(n_tracks, z_plane)
    phi_out = np.empty(n_tracks)
    theta_out = np.empty(n_tracks)

    filled = 0
    while filled < n_tracks:
        n_batch = min(batch_size, n_tracks - filled)
        print(f"Generating batch: {filled}/{n_tracks} -> {filled + n_batch}/{n_tracks}")
        rand = rng.random((n_batch, 5))
        x_out[filled:filled + n_batch] = (rand[:, 0] * 2 - 1) * xlim
        y_out[filled:filled + n_batch] = (rand[:, 1] * 2 - 1) * ylim
        phi_out[filled:filled + n_batch] = rand[:, 3] * (2 * np.pi) - np.pi
        theta_out[filled:filled + n_batch] = np.arccos(rand[:, 4] ** exponent)
        filled += n_batch

    df = pd.DataFrame({
        "event_id": np.arange(n_tracks, dtype=np.int64),
        "X_gen": x_out,
        "Y_gen": y_out,
        "Z_gen": z_out,
        "Theta_gen": theta_out,
        "Phi_gen": phi_out,
        "T0_ns": np.zeros(n_tracks, dtype=float),
        "T_thick_s": t_thick_s,
    })
    if drop_last_second and len(df) > 0:
        last_second = df["T_thick_s"].max()
        df = df[df["T_thick_s"] != last_second].reset_index(drop=True)
    return df


def generate_muon_batches(
    n_tracks: int,
    xlim: float,
    ylim: float,
    z_plane: float,
    cos_n: float,
    seed: Optional[int],
    thick_rate_hz: float | None,
    drop_last_second: bool,
    batch_size: int,
) -> Iterable[pd.DataFrame]:
    rng = np.random.default_rng(seed)
    time_rng = build_time_rng(seed)
    exponent = 1.0 / (cos_n + 1.0)

    thick_seq = ThickSecondSequencer(float(thick_rate_hz or 0.0), time_rng)

    filled = 0
    while filled < n_tracks:
        n_batch = min(batch_size, n_tracks - filled)
        print(f"Generating batch: {filled}/{n_tracks} -> {filled + n_batch}/{n_tracks}")
        rand = rng.random((n_batch, 5))
        x_out = (rand[:, 0] * 2 - 1) * xlim
        y_out = (rand[:, 1] * 2 - 1) * ylim
        phi_out = rand[:, 3] * (2 * np.pi) - np.pi
        theta_out = np.arccos(rand[:, 4] ** exponent)
        if thick_rate_hz and thick_rate_hz > 0:
            t_thick_s = thick_seq.next(n_batch)
        else:
            t_thick_s = np.zeros(n_batch, dtype=float)
        df = pd.DataFrame({
            "event_id": np.arange(filled, filled + n_batch, dtype=np.int64),
            "X_gen": x_out,
            "Y_gen": y_out,
            "Z_gen": np.full(n_batch, z_plane),
            "Theta_gen": theta_out,
            "Phi_gen": phi_out,
            "T0_ns": np.zeros(n_batch, dtype=float),
            "T_thick_s": t_thick_s,
        })
        if drop_last_second and filled + n_batch >= n_tracks and len(df) > 0:
            last_second = df["T_thick_s"].max()
            df = df[df["T_thick_s"] != last_second].reset_index(drop=True)
        yield df
        filled += n_batch


def prune_step1(df: pd.DataFrame) -> pd.DataFrame:
    keep = {
        "event_id",
        "X_gen",
        "Y_gen",
        "Z_gen",
        "Theta_gen",
        "Phi_gen",
        "T_thick_s",
    }
    keep_cols = [col for col in df.columns if col in keep]
    return df[keep_cols]


def plot_muon_sample(df: pd.DataFrame, pdf: PdfPages) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    _, _, patches = axes[0, 0].hist(df["X_gen"], bins=100, color="steelblue", alpha=0.8)
    for patch in patches:
        patch.set_rasterized(True)
    axes[0, 0].set_title("X_gen distribution")
    axes[0, 0].set_xlabel("X (mm)")
    axes[0, 0].set_ylabel("Counts")

    _, _, patches = axes[0, 1].hist(df["Y_gen"], bins=100, color="seagreen", alpha=0.8)
    for patch in patches:
        patch.set_rasterized(True)
    axes[0, 1].set_title("Y_gen distribution")
    axes[0, 1].set_xlabel("Y (mm)")

    _, _, patches = axes[1, 0].hist(df["Theta_gen"], bins=100, color="darkorange", alpha=0.8)
    for patch in patches:
        patch.set_rasterized(True)
    axes[1, 0].set_title("Theta_gen distribution")
    axes[1, 0].set_xlabel("Theta (rad)")

    _, _, patches = axes[1, 1].hist(df["Phi_gen"], bins=100, color="slateblue", alpha=0.8)
    for patch in patches:
        patch.set_rasterized(True)
    axes[1, 1].set_title("Phi_gen distribution")
    axes[1, 1].set_xlabel("Phi (rad)")

    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(df["Theta_gen"], df["Phi_gen"], s=1, alpha=0.2, rasterized=True)
    ax.set_title("Theta vs Phi")
    ax.set_xlabel("Theta (rad)")
    ax.set_ylabel("Phi (rad)")
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def plot_step1_summary(df: pd.DataFrame, pdf: PdfPages) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    axes[0, 0].hist2d(df["X_gen"], df["Y_gen"], bins=60, cmap="viridis")
    axes[0, 0].set_title("X_gen vs Y_gen (density)")
    axes[0, 0].set_xlabel("X (mm)")
    axes[0, 0].set_ylabel("Y (mm)")

    h = axes[0, 1].hist2d(df["Theta_gen"], df["Phi_gen"], bins=60, cmap="magma")
    axes[0, 1].set_title("Theta_gen vs Phi_gen (density)")
    axes[0, 1].set_xlabel("Theta (rad)")
    axes[0, 1].set_ylabel("Phi (rad)")
    for quad in h[3].get_paths():
        quad._interpolation_steps = 1

    cos_theta = np.cos(df["Theta_gen"].to_numpy(dtype=float))
    axes[1, 0].hist(cos_theta, bins=80, color="darkorange", alpha=0.8)
    axes[1, 0].set_title("cos(Theta_gen)")
    axes[1, 0].set_xlabel("cos(theta)")

    r = np.hypot(df["X_gen"].to_numpy(dtype=float), df["Y_gen"].to_numpy(dtype=float))
    axes[1, 1].hist(r, bins=80, color="slateblue", alpha=0.8)
    axes[1, 1].set_title("Radial distance")
    axes[1, 1].set_xlabel("sqrt(X^2+Y^2) (mm)")

    for ax in axes.flatten():
        for patch in ax.patches:
            patch.set_rasterized(True)
    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)


def plot_thick_time_summary(df: pd.DataFrame, pdf: PdfPages, rate_hz: float | None) -> bool:
    if "T_thick_s" not in df.columns:
        return False
    t0_s = df["T_thick_s"].to_numpy(dtype=float)
    t0_s = t0_s[np.isfinite(t0_s)]
    if t0_s.size < 2:
        return False
    t0_s = np.sort(t0_s.astype(int))
    if t0_s.size == 0:
        return False
    sec_min = int(t0_s[0])
    sec_max = int(t0_s[-1])
    counts = np.bincount(t0_s - sec_min)
    seconds = np.arange(sec_min, sec_min + len(counts))
    if len(counts) > 1:
        counts = counts[1:]
        seconds = seconds[1:]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].plot(seconds, counts, linewidth=1.0, color="slateblue")
    axes[0].set_title("Counts per second")
    axes[0].set_xlabel("Second")
    axes[0].set_ylabel("Events")

    axes[1].hist(counts, bins=60, color="teal", alpha=0.8)
    axes[1].set_title("Histogram of counts per second")
    axes[1].set_xlabel("Events per second")
    axes[1].set_ylabel("Counts")
    if rate_hz and rate_hz > 0:
        axes[1].axvline(rate_hz, color="black", linestyle="--", linewidth=1.0)

    fig.tight_layout()
    pdf.savefig(fig, dpi=150)
    plt.close(fig)
    return True


def normalize_flux_values(value: object) -> list[float]:
    if value is None:
        return [1.0]
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, list):
        if not value:
            return [1.0]
        if not all(isinstance(v, (int, float)) for v in value):
            raise ValueError("flux_cm2_min must be a number or list of numbers.")
        return [float(v) for v in value]
    raise ValueError("flux_cm2_min must be a number or list of numbers.")


def normalize_cos_values(value: object) -> list[float]:
    if value is None:
        return [2.0]
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, list):
        if not value:
            return [2.0]
        if not all(isinstance(v, (int, float)) for v in value):
            raise ValueError("cos_n must be a number or list of numbers.")
        return [float(v) for v in value]
    raise ValueError("cos_n must be a number or list of numbers.")


def is_random_value(value: object) -> bool:
    return isinstance(value, str) and value.lower() == "random"


def generate_thick_times(n_tracks: int, rate_hz: float, rng: np.random.Generator) -> np.ndarray:
    if n_tracks <= 0:
        return np.zeros(0, dtype=float)
    if rate_hz <= 0:
        return np.zeros(n_tracks, dtype=float)
    times: list[float] = []
    second = 0
    while len(times) < n_tracks:
        count = int(rng.poisson(rate_hz))
        if count <= 0:
            second += 1
            continue
        remaining = n_tracks - len(times)
        take = min(count, remaining)
        times.extend([float(second)] * take)
        second += 1
    return np.asarray(times, dtype=float)


class ThickSecondSequencer:
    def __init__(self, rate_hz: float, rng: np.random.Generator) -> None:
        self.rate_hz = rate_hz
        self.rng = rng
        self.current_second = 0
        self.remaining_in_second = 0

    def next(self, n: int) -> np.ndarray:
        if n <= 0:
            return np.zeros(0, dtype=float)
        if self.rate_hz <= 0:
            return np.zeros(n, dtype=float)
        out: list[float] = []
        while len(out) < n:
            if self.remaining_in_second <= 0:
                self.remaining_in_second = int(self.rng.poisson(self.rate_hz))
                if self.remaining_in_second <= 0:
                    self.current_second += 1
                    continue
            remaining = n - len(out)
            take = min(self.remaining_in_second, remaining)
            out.extend([float(self.current_second)] * take)
            self.remaining_in_second -= take
            if self.remaining_in_second <= 0:
                self.current_second += 1
        return np.asarray(out, dtype=float)


def main() -> None:
    print("\n-----\nStep 1 starting...\n-----")
    parser = argparse.ArgumentParser(description="Step 1: generate muon sample (x,y,z,theta,phi).")
    parser.add_argument("--config", default="config_step_1_physics.yaml", help="Path to step physics config YAML")
    parser.add_argument(
        "--runtime-config",
        default=None,
        help="Path to step runtime config YAML (defaults to *_runtime.yaml)",
    )
    parser.add_argument("--plot-only", action="store_true", help="Only generate plots from existing output")
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

    output_dir = Path(cfg["output_dir"])
    if not output_dir.is_absolute():
        output_dir = Path(__file__).resolve().parent / output_dir
    ensure_dir(output_dir)

    output_format = str(cfg.get("output_format", "pkl")).lower()
    chunk_rows = cfg.get("chunk_rows")
    plot_sample_rows = cfg.get("plot_sample_rows")
    output_base = cfg.get("output_basename", "muon_sample")
    rng = np.random.default_rng(cfg.get("seed"))
    param_row = None
    param_set_id = None
    param_date = None
    param_row_id = None
    param_mesh_path = None
    if is_random_value(cfg.get("flux_cm2_min")) or is_random_value(cfg.get("cos_n")):
        mesh_dir = Path(cfg.get("param_mesh_dir", "../../SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1"))
        if not mesh_dir.is_absolute():
            mesh_dir = Path(__file__).resolve().parent / mesh_dir
        mesh, mesh_path = resolve_param_mesh(mesh_dir, cfg.get("param_mesh_sim_run", "latest"), cfg.get("seed"))
        mesh = mesh.copy()
        mesh["done"] = mesh.get("done", 0).fillna(0).astype(int)
        candidates = mesh[mesh["done"] != 1].reset_index(drop=True)
        if candidates.empty:
            raise ValueError("No available rows in param_mesh.csv (all done).")
        start_idx = int(rng.integers(0, len(candidates)))
        order = list(range(start_idx, len(candidates))) + list(range(0, start_idx))
        param_row = None
        for idx in order:
            row = candidates.iloc[idx]
            step_1_id_candidate = str(row.get("step_1_id")) if "step_1_id" in row.index else None
            if not step_1_id_candidate:
                continue
            sim_run_candidate = build_sim_run_name([step_1_id_candidate])
            if not (output_dir / sim_run_candidate).exists():
                param_row = row
                break
        if param_row is None:
            print("Skipping STEP_1: all step_1_id combinations already exist.")
            return
        if "param_set_id" in param_row.index and pd.notna(param_row["param_set_id"]):
            param_set_id = int(param_row["param_set_id"])
        if "param_date" in param_row:
            param_date = str(param_row["param_date"])
        param_row_id = int(param_row.name)
        param_mesh_path = mesh_path

    flux_cfg = cfg.get("flux_cm2_min")
    if is_random_value(flux_cfg):
        if param_row is None or "flux_cm2_min" not in param_row:
            raise ValueError("flux_cm2_min is random but not found in param_mesh.csv.")
        flux_cm2_min = float(param_row["flux_cm2_min"])
        flux_idx = None
        flux_candidates = []
    else:
        flux_candidates = normalize_flux_values(flux_cfg)
        flux_idx = int(rng.integers(0, len(flux_candidates)))
        flux_cm2_min = float(flux_candidates[flux_idx])

    cos_cfg = cfg.get("cos_n")
    if is_random_value(cos_cfg):
        if param_row is None or "cos_n" not in param_row:
            raise ValueError("cos_n is random but not found in param_mesh.csv.")
        cos_n = float(param_row["cos_n"])
        cos_idx = None
        cos_candidates = []
    else:
        cos_candidates = normalize_cos_values(cos_cfg)
        cos_idx = int(rng.integers(0, len(cos_candidates)))
        cos_n = float(cos_candidates[cos_idx])

    n_tracks = int(cfg["n_tracks"])
    if param_row is not None and "n_tracks" in param_row.index and pd.notna(param_row["n_tracks"]):
        n_tracks = int(param_row["n_tracks"])
    if n_tracks <= 0:
        raise ValueError(f"n_tracks must be positive, got {n_tracks}.")
    cfg["n_tracks"] = n_tracks
    output_name = f"{cfg.get('output_basename', 'muon_sample')}_{n_tracks}.{output_format}"

    physics_cfg_run = dict(physics_cfg)
    physics_cfg_run["flux_cm2_min"] = flux_cm2_min
    physics_cfg_run["cos_n"] = cos_n
    step_1_id = None
    if param_row is not None and "step_1_id" in param_row.index:
        step_1_id = str(param_row["step_1_id"])
    physics_cfg_run["step_1_id"] = step_1_id
    if flux_candidates and len(flux_candidates) > 1:
        print(f"flux_cm2_min candidates: {len(flux_candidates)} (selected index {flux_idx})")
    if cos_candidates and len(cos_candidates) > 1:
        print(f"cos_n candidates: {len(cos_candidates)} (selected index {cos_idx})")
    if param_set_id is not None:
        print(f"param_set_id: {param_set_id} (date {param_date})")
    if args.plot_only:
        sim_run = find_sim_run(output_dir, physics_cfg_run, None)
        if sim_run is None:
            sim_run_dirs = sorted(
                output_dir.glob("SIM_RUN_*"),
                key=lambda p: p.stat().st_mtime,
            )
            if not sim_run_dirs:
                raise FileNotFoundError("No SIM_RUN directories found for plot-only.")
            sim_run_dir = sim_run_dirs[-1]
        else:
            sim_run_dir = output_dir / sim_run
        output_path = sim_run_dir / output_name
        config_hash = None
        upstream_hash = None
    else:
        if not step_1_id:
            raise ValueError("step_1_id is missing in param_mesh.csv.")
        sim_run = build_sim_run_name([step_1_id])
        sim_run_dir = output_dir / sim_run
        if not args.force and sim_run_dir.exists():
            print(f"SIM_RUN {sim_run} already exists; skipping (use --force to regenerate).")
            return
        sim_run, sim_run_dir, config_hash, upstream_hash, _ = register_sim_run(
            output_dir, "STEP_1", config_path, physics_cfg_run, None, sim_run
        )
        reset_dir(sim_run_dir)
        output_path = sim_run_dir / output_name
    print(
        f"Step 1 config: n_tracks={cfg['n_tracks']}, xlim={cfg['xlim_mm']}, "
        f"ylim={cfg['ylim_mm']}, z_plane={cfg['z_plane_mm']}, c={cfg.get('c_mm_per_ns', 299.792458)}"
    )
    flux_cm2_min = float(physics_cfg_run.get("flux_cm2_min", 1.0))
    area_cm2 = (2.0 * float(cfg["xlim_mm"])) * (2.0 * float(cfg["ylim_mm"])) / 100.0
    rate_per_min = flux_cm2_min * area_cm2
    rate_hz = rate_per_min / 60.0
    drop_last_second = True
    print(
        f"Step 1 timing: flux={flux_cm2_min} count/cm^2/min, area_cm2={area_cm2:.2f}, "
        f"rate_hz={rate_hz:.4f}"
    )
    if rate_hz > 0:
        total_time_s = float(cfg["n_tracks"]) / rate_hz
        print(f"Step 1 timing: estimated total time ~{total_time_s:.2f}s")
    if drop_last_second:
        print("Step 1 timing: dropping events from the last second.")
    if args.plot_only:
        if args.no_plots:
            print("Plot-only requested with --no-plots; skipping plots.")
            return
        plot_sample_rows = cfg.get("plot_sample_rows")
        def load_latest_from_dir(target_dir: Path) -> pd.DataFrame | None:
            chunk_dirs = sorted(
                target_dir.glob(f"{output_base}_*/chunks"),
                key=lambda p: p.stat().st_mtime,
            )
            if chunk_dirs:
                chunk_dir = chunk_dirs[-1]
                part_files = sorted(
                    list(chunk_dir.glob("part_*.pkl")) + list(chunk_dir.glob("part_*.csv")),
                    key=lambda p: p.stat().st_mtime,
                )
                if not part_files:
                    raise FileNotFoundError(f"No part files found in {chunk_dir}")
                for part_path in reversed(part_files):
                    try:
                        if part_path.suffix == ".csv":
                            df_local = pd.read_csv(part_path)
                        else:
                            df_local = pd.read_pickle(part_path)
                    except Exception:
                        continue
                    print(f"Plot-only: using chunk file {part_path.name}")
                    if plot_sample_rows:
                        sample_n = len(df_local) if plot_sample_rows is True else int(plot_sample_rows)
                        sample_n = min(sample_n, len(df_local))
                        df_local = df_local.sample(n=sample_n, random_state=0)
                    return df_local
            chunk_candidates = sorted(
                target_dir.glob(f"{output_base}_*.chunks.json"),
                key=lambda p: p.stat().st_mtime,
            )
            if chunk_candidates:
                chunk_manifest = chunk_candidates[-1]
                manifest = json.loads(chunk_manifest.read_text())
                chunks = manifest.get("chunks", [])
                if not chunks:
                    raise FileNotFoundError(f"No chunks listed in {chunk_manifest}")
                last_chunk = Path(chunks[-1])
                print(f"Plot-only: using chunk manifest {chunk_manifest.name}")
                if last_chunk.suffix == ".csv":
                    df_local = pd.read_csv(last_chunk)
                else:
                    df_local = pd.read_pickle(last_chunk)
                if plot_sample_rows:
                    sample_n = len(df_local) if plot_sample_rows is True else int(plot_sample_rows)
                    sample_n = min(sample_n, len(df_local))
                    df_local = df_local.sample(n=sample_n, random_state=0)
                return df_local
            data_candidates = []
            data_candidates.extend(target_dir.glob(f"{output_base}_*.pkl"))
            data_candidates.extend(target_dir.glob(f"{output_base}_*.csv"))
            data_candidates = sorted(data_candidates, key=lambda p: p.stat().st_mtime)
            if not data_candidates:
                return None
            output_path_local = data_candidates[-1]
            print(f"Plot-only: using output file {output_path_local.name}")
            df_local, _ = load_with_metadata(output_path_local)
            return df_local

        df = load_latest_from_dir(sim_run_dir)
        if df is None:
            sim_run_dirs = sorted(
                output_dir.glob("SIM_RUN_*"),
                key=lambda p: p.stat().st_mtime,
            )
            for candidate_dir in reversed(sim_run_dirs):
                df = load_latest_from_dir(candidate_dir)
                if df is not None:
                    sim_run_dir = candidate_dir
                    break
        if df is None:
            raise FileNotFoundError(
                f"No existing outputs found in {sim_run_dir} for plot-only."
            )
    else:
        stream_csv = bool(chunk_rows) and output_format == "csv"
        stream_pkl = bool(chunk_rows) and output_format == "pkl"
        metadata = {
            "created_at": now_iso(),
            "step": "STEP_1",
            "config": physics_cfg_run,
            "runtime_config": runtime_cfg,
            "sim_run": sim_run,
            "config_hash": config_hash,
            "upstream_hash": upstream_hash,
            "param_set_id": param_set_id,
            "param_date": param_date,
            "param_row_id": param_row_id,
            "step_1_id": step_1_id,
            "param_mesh_path": str(param_mesh_path) if param_mesh_path else None,
        }
        generated_rows = None
        generated_path = output_path
        if stream_csv:
            total_rows = 0
            header_written = False
            last_full_batch = None
            for batch in generate_muon_batches(
                n_tracks=int(cfg["n_tracks"]),
                xlim=float(cfg["xlim_mm"]),
                ylim=float(cfg["ylim_mm"]),
                z_plane=float(cfg["z_plane_mm"]),
                cos_n=cos_n,
                seed=cfg.get("seed"),
                thick_rate_hz=rate_hz,
                drop_last_second=drop_last_second,
                batch_size=int(chunk_rows),
            ):
                total_rows += len(batch)
                batch_out = prune_step1(batch)
                batch_out.to_csv(output_path, mode="a", index=False, header=not header_written)
                header_written = True
                last_full_batch = batch_out
            metadata["row_count"] = total_rows
            meta_path = output_path.with_suffix(output_path.suffix + ".meta.json")
            meta_path.write_text(json.dumps(metadata, indent=2))
            df = None
            generated_rows = total_rows
            if not args.no_plots:
                if plot_sample_rows and last_full_batch is not None:
                    sample_n = len(last_full_batch) if plot_sample_rows is True else int(plot_sample_rows)
                    sample_n = min(sample_n, len(last_full_batch))
                    sample_df = last_full_batch.sample(n=sample_n, random_state=0)
                    plot_dir = output_path.parent / "PLOTS"
                    ensure_dir(plot_dir)
                    plot_path = plot_dir / f"{output_path.stem}_plots.pdf"
                    with PdfPages(plot_path) as pdf:
                        plot_muon_sample(sample_df, pdf)
                        plot_step1_summary(sample_df, pdf)
                        added = plot_thick_time_summary(sample_df, pdf, rate_hz)
                    if added:
                        print("Step 1 plots: added thick-time summary page.")
                    else:
                        print("Step 1 plots: skipped thick-time summary page.")
                    print("Step 1 sample head:\n", sample_df.head())
                else:
                    print("Chunked CSV mode enabled; skipping plots to limit memory usage.")
        elif stream_pkl:
            chunks_dir = output_path.with_suffix("") / "chunks"
            ensure_dir(chunks_dir)
            chunks = []
            total_rows = 0
            last_full_batch = None
            for idx, batch in enumerate(
                generate_muon_batches(
                    n_tracks=int(cfg["n_tracks"]),
                    xlim=float(cfg["xlim_mm"]),
                    ylim=float(cfg["ylim_mm"]),
                    z_plane=float(cfg["z_plane_mm"]),
                    cos_n=cos_n,
                    seed=cfg.get("seed"),
                    thick_rate_hz=rate_hz,
                    drop_last_second=drop_last_second,
                    batch_size=int(chunk_rows),
                )
            ):
                chunk_path = chunks_dir / f"part_{idx:04d}.pkl"
                batch_out = prune_step1(batch)
                batch_out.to_pickle(chunk_path)
                chunks.append(str(chunk_path))
                total_rows += len(batch_out)
                last_full_batch = batch_out
            manifest = {
                "version": 1,
                "chunks": chunks,
                "row_count": total_rows,
                "metadata": metadata,
            }
            manifest_path = output_path.with_suffix(".chunks.json")
            manifest_path.write_text(json.dumps(manifest, indent=2))
            df = None
            metadata["row_count"] = total_rows
            generated_rows = total_rows
            generated_path = manifest_path
            if not args.no_plots:
                if plot_sample_rows and last_full_batch is not None:
                    sample_n = len(last_full_batch) if plot_sample_rows is True else int(plot_sample_rows)
                    sample_n = min(sample_n, len(last_full_batch))
                    sample_df = last_full_batch.sample(n=sample_n, random_state=0)
                    plot_dir = output_path.parent / "PLOTS"
                    ensure_dir(plot_dir)
                    plot_path = plot_dir / f"{output_path.stem}_plots.pdf"
                    with PdfPages(plot_path) as pdf:
                        plot_muon_sample(sample_df, pdf)
                        plot_step1_summary(sample_df, pdf)
                        added = plot_thick_time_summary(sample_df, pdf, rate_hz)
                    if added:
                        print("Step 1 plots: added thick-time summary page.")
                    else:
                        print("Step 1 plots: skipped thick-time summary page.")
                    print("Step 1 sample head:\n", sample_df.head())
                else:
                    print("Chunked PKL mode enabled; skipping plots to limit memory usage.")
        else:
            df = generate_muon_sample(
                n_tracks=int(cfg["n_tracks"]),
                xlim=float(cfg["xlim_mm"]),
                ylim=float(cfg["ylim_mm"]),
                z_plane=float(cfg["z_plane_mm"]),
                cos_n=cos_n,
                seed=cfg.get("seed"),
                thick_rate_hz=rate_hz,
                drop_last_second=drop_last_second,
            )
            df = prune_step1(df)
            save_with_metadata(df, output_path, metadata, output_format)
            generated_rows = len(df)

    if not args.no_plots and df is not None:
        plot_dir = output_path.parent / "PLOTS"
        ensure_dir(plot_dir)
        plot_path = plot_dir / f"{output_path.stem}_plots.pdf"
        with PdfPages(plot_path) as pdf:
            plot_muon_sample(df, pdf)
            plot_step1_summary(df, pdf)
            added = plot_thick_time_summary(df, pdf, rate_hz)
        if added:
            print("Step 1 plots: added thick-time summary page.")
        else:
            print("Step 1 plots: skipped thick-time summary page.")
        print("Step 1 sample head:\n", df.head())

    if args.plot_only and not args.no_plots:
        print(f"Plotted {output_path.stem} -> {plot_path}")
    else:
        if df is None:
            print(f"Generated {generated_rows or 0} muons -> {generated_path}")
        else:
            print(f"Generated {generated_rows or len(df)} muons -> {output_path}")


if __name__ == "__main__":
    main()
