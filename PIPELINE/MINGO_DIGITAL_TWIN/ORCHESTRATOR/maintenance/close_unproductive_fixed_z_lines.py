#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/close_unproductive_fixed_z_lines.py
Purpose: Mark open STEP_1 mesh lines done when they cannot satisfy fixed STEP_2 z positions.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/close_unproductive_fixed_z_lines.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import fcntl
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


def normalize_id(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    try:
        return f"{int(float(value)):03d}"
    except (TypeError, ValueError):
        text = str(value).strip()
        return "" if text.lower() in {"", "nan", "<na>"} else text


def parse_sim_run_ids(path: Path) -> tuple[str, ...] | None:
    name = path.name
    if not name.startswith("SIM_RUN_"):
        return None
    raw = name[len("SIM_RUN_") :].split("_")
    normalized: list[str] = []
    for item in raw:
        norm = normalize_id(item)
        if norm:
            normalized.append(norm)
    if not normalized:
        return None
    return tuple(normalized)


def write_csv_atomic(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        df.to_csv(tmp_path, index=False)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(prog="close_unproductive_fixed_z_lines.py")
    p.add_argument("--apply", action="store_true", help="Actually mark rows done in param_mesh.csv (destructive).")
    args = p.parse_args()

    dt = Path(__file__).resolve().parents[2]
    mesh_path = dt / "SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv"
    step2_cfg_path = dt / "MASTER_STEPS/STEP_2/config_step_2_physics.yaml"
    step1_to_2_dir = dt / "SIMULATION_OUTPUTS/INTERSTEPS/STEP_1_TO_2"

    if not mesh_path.exists():
        print("result changed=0 reason=missing_mesh")
        return 3
    if not step2_cfg_path.exists():
        print("result changed=0 reason=missing_step2_config")
        return 3

    with step2_cfg_path.open("r", encoding="utf-8") as handle:
        step2_cfg = yaml.safe_load(handle) or {}
    z_positions = step2_cfg.get("z_positions")
    if not (isinstance(z_positions, (list, tuple)) and len(z_positions) == 4):
        print("result changed=0 reason=non_fixed_z")
        return 3
    try:
        z_target = np.array([float(v) for v in z_positions], dtype=float)
    except (TypeError, ValueError):
        print("result changed=0 reason=invalid_fixed_z")
        return 3

    lock_path = mesh_path.with_name(".param_mesh.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            mesh = pd.read_csv(mesh_path)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    if "done" not in mesh.columns:
        mesh["done"] = 0
    mesh["done"] = mesh["done"].fillna(0).astype(int)

    for idx in range(1, 11):
        col = f"step_{idx}_id"
        if col not in mesh.columns:
            mesh[col] = ""
        mesh[col] = mesh[col].map(normalize_id)

    required_cols = {"z_p1", "z_p2", "z_p3", "z_p4", "step_1_id", "step_2_id", "done"}
    if not required_cols.issubset(mesh.columns):
        print("result changed=0 reason=missing_required_columns")
        return 3

    z_cols = ["z_p1", "z_p2", "z_p3", "z_p4"]
    z_frame = mesh[z_cols].apply(pd.to_numeric, errors="coerce")
    valid_z_mask = ~z_frame.isna().any(axis=1)
    z_match = np.zeros(len(mesh), dtype=bool)
    if valid_z_mask.any():
        z_match_valid = np.isclose(
            z_frame.loc[valid_z_mask].to_numpy(dtype=float),
            z_target[np.newaxis, :],
            rtol=0.0,
            atol=1e-6,
        ).all(axis=1)
        z_match[np.where(valid_z_mask.to_numpy())[0]] = z_match_valid

    fixed_step2_ids = sorted(
        {
            normalize_id(value)
            for value in mesh.loc[z_match, "step_2_id"].tolist()
            if normalize_id(value)
        }
    )
    if not fixed_step2_ids:
        print("result changed=0 reason=no_fixed_step2_ids")
        return 3
    fixed_step2_set = set(fixed_step2_ids)

    pending_mask = mesh["done"] != 1
    active_step1_ids = sorted(
        {normalize_id(value) for value in mesh.loc[pending_mask, "step_1_id"].tolist() if normalize_id(value)}
    )

    open_step1_ids: set[str] = set()
    if step1_to_2_dir.exists():
        for sim_dir in step1_to_2_dir.glob("SIM_RUN_*"):
            ids = parse_sim_run_ids(sim_dir)
            if ids and len(ids) >= 1:
                open_step1_ids.add(ids[0])

    active_open_step1_ids = [sid for sid in active_step1_ids if sid in open_step1_ids]
    rows_to_mark: list[int] = []
    dropped_lines: list[str] = []
    for step1_id in active_open_step1_ids:
        line_mask = pending_mask & (mesh["step_1_id"] == step1_id)
        pending_step2_ids = {
            normalize_id(value)
            for value in mesh.loc[line_mask, "step_2_id"].tolist()
            if normalize_id(value)
        }
        if pending_step2_ids and pending_step2_ids.isdisjoint(fixed_step2_set):
            dropped_lines.append(step1_id)
            rows_to_mark.extend(mesh.index[line_mask].tolist())

    rows_to_mark = sorted(set(rows_to_mark))

    # Non-destructive by default: only perform changes when --apply is passed.
    if rows_to_mark and args.apply:
        mesh.loc[rows_to_mark, "done"] = 1
        lock_path = mesh_path.with_name(".param_mesh.lock")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                # Re-read under lock to avoid clobbering concurrent updates.
                latest = pd.read_csv(mesh_path)
                if "done" not in latest.columns:
                    latest["done"] = 0
                latest["done"] = latest["done"].fillna(0).astype(int)
                for idx in rows_to_mark:
                    if 0 <= idx < len(latest):
                        latest.loc[idx, "done"] = 1
                write_csv_atomic(latest, mesh_path)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        changed_flag = 1
    else:
        # Dry-run / reporting mode (default): do NOT modify param_mesh.csv
        changed_flag = 0

    print(
        "result "
        f"changed={changed_flag} "
        f"would_mark={len(rows_to_mark)} "
        f"fixed_step2_ids={','.join(fixed_step2_ids) if fixed_step2_ids else '-'} "
        f"active_open_lines={','.join(active_open_step1_ids) if active_open_step1_ids else '-'} "
        f"dropped_lines={','.join(dropped_lines) if dropped_lines else '-'} "
        f"rows_marked={len(rows_to_mark) if changed_flag else 0}"
    )
    # Return 0 only when we actually modified the mesh; otherwise return 3 (no-change / dry-run)
    return 0 if (rows_to_mark and args.apply) else 3


if __name__ == "__main__":
    raise SystemExit(main())
