"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_SHARED/sim_utils_mesh.py
Purpose: param_mesh utilities and scheduler selection helpers.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_SHARED/sim_utils_mesh.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

import numpy as np
import pandas as pd

from .sim_utils_io import param_mesh_lock, write_csv_atomic
from .sim_utils_metadata import build_sim_run_name
from .sim_utils_registry import latest_sim_run, random_sim_run


def resolve_param_mesh(
    mesh_dir: Path,
    mesh_sim_run: Optional[str],
    seed: Optional[int],
) -> Tuple[pd.DataFrame, Path]:
    direct_tokens = {None, "", "none", "direct"}
    if mesh_sim_run in direct_tokens:
        mesh_path = mesh_dir / "param_mesh.csv"
    else:
        if mesh_sim_run == "latest":
            mesh_sim_run = latest_sim_run(mesh_dir)
        elif mesh_sim_run == "random":
            mesh_sim_run = random_sim_run(mesh_dir, seed)
        mesh_path = mesh_dir / str(mesh_sim_run) / "param_mesh.csv"
        if not mesh_path.exists():
            fallback = mesh_dir / "param_mesh.csv"
            if fallback.exists():
                mesh_path = fallback
    if not mesh_path.exists():
        raise FileNotFoundError(f"param_mesh.csv not found in {mesh_path.parent}")
    with param_mesh_lock(mesh_path):
        mesh = pd.read_csv(mesh_path)
        mesh = normalize_param_mesh_ids(mesh)
        if _mesh_ids_changed(mesh, mesh_path):
            write_csv_atomic(mesh, mesh_path, index=False)
    return mesh, mesh_path


def check_param_mesh_upstream(
    mesh_dir: Path,
    mesh_sim_run: Optional[str],
    intersteps_dir: Path,
    target_step: int = 3,
    seed: Optional[int] = None,
) -> list[dict]:
    """Return missing upstream SIM_RUNs required by pending rows in param_mesh.csv.

    - mesh_dir: directory that contains `param_mesh.csv`.
    - mesh_sim_run: pass-through to `resolve_param_mesh` (e.g. 'none', 'latest', 'random').
    - intersteps_dir: path to INTERSTEPS root (used to locate upstream STEP_* directories).
    - target_step: the consumer step that expects upstream outputs (e.g. 3 -> check STEP_2_TO_3).

    Returns list[dict] with keys: param_row_index, prefix_ids, expected_sim_run, expected_path
    """
    if target_step <= 1:
        return []
    mesh, _ = resolve_param_mesh(mesh_dir, mesh_sim_run, seed)
    if "done" not in mesh.columns:
        mesh = mesh.copy()
        mesh["done"] = 0
    pending = mesh[mesh["done"] != 1].copy()

    upstream_step = target_step - 1
    upstream_dir = intersteps_dir / f"STEP_{upstream_step}_TO_{upstream_step + 1}"

    missing: list[dict] = []
    for idx, row in pending.iterrows():
        prefix_ids: list[str] = []
        skip = False
        for i in range(1, upstream_step + 1):
            col = f"step_{i}_id"
            val = row.get(col, "")
            if pd.isna(val) or str(val).strip() == "":
                skip = True
                break
            prefix_ids.append(str(val))
        if skip:
            continue
        sim_run_name = build_sim_run_name(prefix_ids)
        expected_path = upstream_dir / sim_run_name
        if not expected_path.exists():
            missing.append(
                {
                    "param_row_index": int(idx),
                    "prefix_ids": tuple(prefix_ids),
                    "expected_sim_run": sim_run_name,
                    "expected_path": str(expected_path),
                }
            )
    return missing


def normalize_param_mesh_ids(mesh: pd.DataFrame, width: int = 3) -> pd.DataFrame:
    normalized = mesh.copy()
    for idx in range(1, 11):
        col = f"step_{idx}_id"
        if col not in normalized.columns:
            continue

        def _fmt(value: object) -> object:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                return pd.NA
            try:
                num = int(float(value))
                return f"{num:0{width}d}"
            except (TypeError, ValueError):
                return str(value)

        normalized[col] = normalized[col].apply(_fmt).astype("string")
    return normalized


def _mesh_ids_changed(mesh: pd.DataFrame, mesh_path: Path) -> bool:
    try:
        original = pd.read_csv(mesh_path)
    except OSError:
        return True
    for idx in range(1, 11):
        col = f"step_{idx}_id"
        if col not in mesh.columns and col not in original.columns:
            continue
        left = mesh.get(col, pd.Series(dtype="object")).fillna("").astype(str)
        right = original.get(col, pd.Series(dtype="object")).fillna("").astype(str)
        if not left.equals(right):
            return True
    return False


def select_param_row(
    mesh: pd.DataFrame,
    rng: np.random.Generator,
    param_set_id: Optional[int],
    param_row_id: Optional[int] = None,
) -> pd.Series:
    if "done" not in mesh.columns:
        mesh = mesh.copy()
        mesh["done"] = 0
    if param_row_id is not None:
        try:
            row = mesh.loc[int(param_row_id)]
        except (KeyError, ValueError, TypeError):
            raise ValueError(f"param_row_id {param_row_id} not found in param_mesh.csv")
        return row
    if param_set_id is not None:
        if "param_set_id" not in mesh.columns:
            raise ValueError("param_set_id is not available in param_mesh.csv")
        match = mesh[mesh["param_set_id"] == int(param_set_id)]
        if match.empty:
            raise ValueError(f"param_set_id {param_set_id} not found in param_mesh.csv")
        if int(match.iloc[0].get("done", 0)) == 1:
            raise ValueError(f"param_set_id {param_set_id} is marked done in param_mesh.csv")
        return match.iloc[0]
    available = mesh[mesh["done"] != 1]
    if "param_set_id" in available.columns:
        available = available[available["param_set_id"].isna()]
    if available.empty:
        raise ValueError("No available param_set rows; all are marked done or already assigned.")
    idx = int(rng.integers(0, len(available)))
    return available.iloc[idx]


def select_next_step_id(
    output_dir: Path,
    mesh_dir: Path,
    mesh_sim_run: Optional[str],
    step_col: str,
    prefix_ids: Iterable[str],
    seed: Optional[int],
    override_id: Optional[str] = None,
) -> Optional[str]:
    def _normalize_step_id(value: object) -> str:
        if value is None or value == "":
            return ""
        try:
            return f"{int(float(value)):03d}"
        except (TypeError, ValueError):
            return str(value)

    if override_id not in (None, "", "auto"):
        candidates = [str(override_id)]
    else:
        try:
            mesh, _ = resolve_param_mesh(mesh_dir, mesh_sim_run, seed)
        except FileNotFoundError:
            mesh = pd.DataFrame()
        if step_col in mesh.columns:
            filtered = mesh
            prefix_list = list(prefix_ids)
            for idx, prefix_val in enumerate(prefix_list):
                col = f"step_{idx + 1}_id"
                if col not in filtered.columns:
                    break
                prefix_norm = _normalize_step_id(prefix_val)
                if not prefix_norm:
                    continue
                filtered = filtered[filtered[col].astype(str) == prefix_norm]
            candidates = sorted(filtered[step_col].dropna().astype(str).unique().tolist())
        else:
            candidates = ["001"]
    if not candidates:
        return None
    rng = np.random.default_rng(seed)
    start_idx = int(rng.integers(0, len(candidates)))
    order = list(range(start_idx, len(candidates))) + list(range(0, start_idx))
    for idx in order:
        step_id = candidates[idx]
        sim_run = build_sim_run_name(list(prefix_ids) + [step_id])
        if not (output_dir / sim_run).exists():
            return step_id
    return None


def mark_param_set_done(mesh_path: Path, param_set_id: int) -> None:
    if not mesh_path.exists():
        raise FileNotFoundError(f"param_mesh.csv not found at {mesh_path}")
    with param_mesh_lock(mesh_path):
        mesh = pd.read_csv(mesh_path)
        if "done" not in mesh.columns:
            mesh["done"] = 0
        match = mesh["param_set_id"] == int(param_set_id)
        if not match.any():
            raise ValueError(f"param_set_id {param_set_id} not found in param_mesh.csv")
        mesh.loc[match, "done"] = 1
        z_cols = ["z_p1", "z_p2", "z_p3", "z_p4"]
        head_cols = ["done", "param_set_id", "param_date"]
        ordered_cols = [c for c in head_cols if c in mesh.columns] + [
            c for c in mesh.columns if c not in head_cols and c not in z_cols
        ] + [c for c in z_cols if c in mesh.columns]
        mesh = mesh[ordered_cols]
        write_csv_atomic(mesh, mesh_path, index=False)
