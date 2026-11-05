#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/repair_param_mesh_step_ids.py
Purpose: Repair inconsistent parameter-mesh step IDs while preserving canonical parameter tuples.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/repair_param_mesh_step_ids.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT_DIR))
sys.path.append(str(ROOT_DIR / "MASTER_STEPS"))

from STEP_SHARED.sim_utils import normalize_param_mesh_ids, param_mesh_lock, write_csv_atomic


KEY_COLUMNS_BY_STEP = {
    "step_1_id": ["cos_n", "flux_cm2_min"],
    "step_2_id": ["z_p1", "z_p2", "z_p3", "z_p4"],
    "step_3_id": ["eff_p1", "eff_p2", "eff_p3", "eff_p4"],
}


def _parse_step_id(value: object) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _canonical_key(row: pd.Series, cols: list[str]) -> tuple[float, ...] | None:
    out: list[float] = []
    for col in cols:
        if col not in row.index:
            return None
        value = row[col]
        if value is None or pd.isna(value):
            return None
        try:
            out.append(round(float(value), 10))
        except (TypeError, ValueError):
            return None
    return tuple(out)


def _collect_row_keys(mesh: pd.DataFrame, cols: list[str]) -> list[tuple[float, ...] | None]:
    keys: list[tuple[float, ...] | None] = []
    for _, row in mesh.iterrows():
        keys.append(_canonical_key(row, cols))
    return keys


def _conflicting_id_count(mesh: pd.DataFrame, id_col: str, key_cols: list[str]) -> int:
    row_keys = _collect_row_keys(mesh, key_cols)
    id_to_keys: dict[int, set[tuple[float, ...]]] = defaultdict(set)
    for row_pos, key in enumerate(row_keys):
        if key is None:
            continue
        step_id = _parse_step_id(mesh.iloc[row_pos][id_col])
        if step_id is None:
            continue
        id_to_keys[step_id].add(key)
    return sum(1 for keys in id_to_keys.values() if len(keys) > 1)


def _reassign_step_ids(
    mesh: pd.DataFrame,
    *,
    id_col: str,
    key_cols: list[str],
) -> tuple[pd.DataFrame, int]:
    if id_col not in mesh.columns:
        mesh[id_col] = pd.NA

    repaired = mesh.copy()
    row_keys = _collect_row_keys(repaired, key_cols)
    key_to_rows: dict[tuple[float, ...], list[int]] = defaultdict(list)
    key_to_ids: dict[tuple[float, ...], set[int]] = defaultdict(set)
    id_to_keys: dict[int, set[tuple[float, ...]]] = defaultdict(set)
    existing_ids: list[int | None] = []

    for row_pos, key in enumerate(row_keys):
        step_id = _parse_step_id(repaired.iloc[row_pos][id_col])
        existing_ids.append(step_id)
        if key is None:
            continue
        key_to_rows[key].append(row_pos)
        if step_id is not None:
            key_to_ids[key].add(step_id)
            id_to_keys[step_id].add(key)

    if not key_to_rows:
        repaired[id_col] = repaired[id_col].astype("string")
        return repaired, 0

    assigned: dict[tuple[float, ...], int] = {}
    used_ids: set[int] = set()

    for key, ids in key_to_ids.items():
        exclusive = [sid for sid in sorted(ids) if id_to_keys.get(sid) == {key}]
        if exclusive:
            chosen = exclusive[0]
            assigned[key] = chosen
            used_ids.add(chosen)

    unresolved = [key for key in key_to_rows if key not in assigned]
    unresolved.sort(key=lambda key: (-len(key_to_rows[key]), min(key_to_rows[key])))
    max_existing = max(id_to_keys.keys(), default=0)
    next_id = max_existing + 1

    for key in unresolved:
        candidates = sorted(sid for sid in key_to_ids.get(key, set()) if sid not in used_ids)
        if candidates:
            chosen = candidates[0]
        else:
            while next_id in used_ids:
                next_id += 1
            chosen = next_id
            next_id += 1
        assigned[key] = chosen
        used_ids.add(chosen)

    repaired[id_col] = repaired[id_col].astype("string")
    changed_rows = 0
    for row_pos, key in enumerate(row_keys):
        if key is None:
            continue
        new_id = assigned[key]
        old_id = existing_ids[row_pos]
        if old_id != new_id:
            changed_rows += 1
        repaired.iat[row_pos, repaired.columns.get_loc(id_col)] = f"{new_id:03d}"

    repaired[id_col] = repaired[id_col].astype("string")
    return repaired, changed_rows


def repair_param_mesh_step_ids(mesh_path: Path, *, apply: bool) -> dict[str, int]:
    if not mesh_path.exists():
        raise FileNotFoundError(f"param_mesh.csv not found: {mesh_path}")

    with param_mesh_lock(mesh_path):
        try:
            mesh = pd.read_csv(mesh_path)
        except pd.errors.EmptyDataError:
            return {
                "rows": 0,
                "step_1_id_changed_rows": 0,
                "step_2_id_changed_rows": 0,
                "step_3_id_changed_rows": 0,
                "conflicts_before": 0,
                "conflicts_after": 0,
                "applied": int(apply),
            }

        conflicts_before = sum(
            _conflicting_id_count(mesh, id_col, cols)
            for id_col, cols in KEY_COLUMNS_BY_STEP.items()
            if all(col in mesh.columns for col in cols)
        )

        changed: dict[str, int] = {}
        repaired = mesh.copy()
        for id_col, cols in KEY_COLUMNS_BY_STEP.items():
            if not all(col in repaired.columns for col in cols):
                changed[id_col] = 0
                continue
            repaired, changed_rows = _reassign_step_ids(repaired, id_col=id_col, key_cols=cols)
            changed[id_col] = changed_rows

        repaired = normalize_param_mesh_ids(repaired)
        conflicts_after = sum(
            _conflicting_id_count(repaired, id_col, cols)
            for id_col, cols in KEY_COLUMNS_BY_STEP.items()
            if all(col in repaired.columns for col in cols)
        )

        total_changed = sum(changed.values())
        if apply and total_changed > 0:
            write_csv_atomic(repaired, mesh_path, index=False)

        return {
            "rows": int(len(mesh)),
            "step_1_id_changed_rows": int(changed.get("step_1_id", 0)),
            "step_2_id_changed_rows": int(changed.get("step_2_id", 0)),
            "step_3_id_changed_rows": int(changed.get("step_3_id", 0)),
            "conflicts_before": int(conflicts_before),
            "conflicts_after": int(conflicts_after),
            "applied": int(apply and total_changed > 0),
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Repair param_mesh step IDs so each ID maps to exactly one parameter tuple "
            "(step_1_id: cos/flux, step_2_id: z planes, step_3_id: efficiencies)."
        )
    )
    parser.add_argument(
        "--param-mesh",
        default=str(next(parent for parent in Path(__file__).resolve().parents if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()) / "PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv"),
        help="Path to param_mesh.csv",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write repaired IDs to param_mesh.csv (default is dry-run).",
    )
    args = parser.parse_args()

    mesh_path = Path(args.param_mesh).expanduser().resolve()
    stats = repair_param_mesh_step_ids(mesh_path, apply=args.apply)
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(
        f"{mode}: repaired step IDs at {mesh_path} "
        f"(rows={stats['rows']}, "
        f"step_1_changed={stats['step_1_id_changed_rows']}, "
        f"step_2_changed={stats['step_2_id_changed_rows']}, "
        f"step_3_changed={stats['step_3_id_changed_rows']}, "
        f"conflicts_before={stats['conflicts_before']}, "
        f"conflicts_after={stats['conflicts_after']}, "
        f"written={stats['applied']})"
    )


if __name__ == "__main__":
    main()
