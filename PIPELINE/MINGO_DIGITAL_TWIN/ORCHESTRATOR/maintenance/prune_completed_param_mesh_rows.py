#!/usr/bin/env python3

"""Prune completed rows from the simulation parameter mesh."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_TWIN_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_TWIN_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_TWIN_BOOTSTRAP_ROOT))
from ORCHESTRATOR.lib.paths import repository_root

ROOT_DIR = repository_root()
sys.path.append(str(ROOT_DIR))
sys.path.append(str(ROOT_DIR / "PIPELINE" / "MINGO_DIGITAL_TWIN" / "MASTER_STEPS"))

from STEP_SHARED.sim_utils import param_mesh_lock, write_csv_atomic


def prune_completed_rows(mesh_path: Path, *, dry_run: bool) -> tuple[int, int, int]:
    if not mesh_path.exists():
        raise FileNotFoundError(f"param_mesh.csv not found: {mesh_path}")

    with param_mesh_lock(mesh_path):
        try:
            mesh = pd.read_csv(mesh_path)
        except pd.errors.EmptyDataError:
            return 0, 0, 0

        before = len(mesh)
        if before == 0:
            return 0, 0, 0

        if "done" not in mesh.columns:
            return before, before, 0

        done_series = pd.to_numeric(mesh["done"], errors="coerce").fillna(0).astype(int)
        keep_mask = done_series != 1
        after_mesh = mesh.loc[keep_mask].copy()
        after = len(after_mesh)
        removed = before - after

        if removed > 0 and not dry_run:
            write_csv_atomic(after_mesh, mesh_path, index=False)

        return before, after, removed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove completed (done=1) rows from param_mesh.csv safely."
    )
    parser.add_argument(
        "--param-mesh",
        default=str(ROOT_DIR / "PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv"),
        help="Path to param_mesh.csv",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report how many rows would be removed without writing changes.",
    )
    args = parser.parse_args()

    mesh_path = Path(args.param_mesh).expanduser().resolve()
    before, after, removed = prune_completed_rows(mesh_path, dry_run=args.dry_run)

    action = "DRY-RUN" if args.dry_run else "APPLIED"
    print(
        f"{action}: pruned completed mesh rows at {mesh_path} "
        f"(before={before}, removed={removed}, after={after})"
    )


if __name__ == "__main__":
    main()
