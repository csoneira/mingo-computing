#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/diagnostics/check_param_mesh_consistency.py
Purpose: Check param_mesh rows for missing upstream INTERSTEPS SIM_RUNs.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/diagnostics/check_param_mesh_consistency.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT_DIR))

from MASTER_STEPS.STEP_SHARED import sim_utils


def main(mesh: Path, intersteps: Path, step: int) -> int:
    mesh_dir = mesh if mesh.is_dir() else mesh.parent
    try:
        missing = sim_utils.check_param_mesh_upstream(mesh_dir, "none", intersteps, target_step=step)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not missing:
        print(f"OK: no missing upstream SIM_RUNs detected for target step={step}")
        return 0

    for entry in missing:
        idx = entry.get("param_row_index")
        prefix = ",".join(entry.get("prefix_ids", []))
        simrun = entry.get("expected_sim_run")
        path = entry.get("expected_path")
        print(f"MISSING_UPSTREAM: param_row_index={idx} prefix={prefix} expected_sim_run={simrun} expected_path={path}")
    return 2


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--mesh", required=False, default="SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv", help="param_mesh.csv file or directory")
    p.add_argument("--intersteps", required=False, default="SIMULATION_OUTPUTS/INTERSTEPS", help="INTERSTEPS root directory")
    p.add_argument("--step", required=False, type=int, default=3, help="target step to check (default: 3)")
    args = p.parse_args()
    mesh_path = Path(args.mesh)
    intersteps_path = Path(args.intersteps)
    rc = main(mesh_path, intersteps_path, args.step)
    sys.exit(rc)
