#!/usr/bin/env python3
"""Stable CLI for simulation-state maintenance commands."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from lib.paths import maintenance_dir


COMMAND_SCRIPTS = {
    "cascade-cleanup": "cascade_cleanup_intersteps.py",
    "close-unproductive-lines": "close_unproductive_fixed_z_lines.py",
    "ensure-hashes": "ensure_sim_hashes.py",
    "prune-final-params": "prune_step_final_params.py",
    "prune-mesh": "prune_completed_param_mesh_rows.py",
    "purge-backpressure-queue": "purge_simulation_queue_backpressure.py",
    "repair-mesh-step-ids": "repair_param_mesh_step_ids.py",
    "sanitize-runs": "sanitize_sim_runs.py",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one simulation maintenance operation through a stable command "
            "interface. Arguments after the command are passed to that operation."
        )
    )
    parser.add_argument("command", choices=sorted(COMMAND_SCRIPTS))
    parser.add_argument("operation_args", nargs=argparse.REMAINDER)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    script_path = maintenance_dir() / COMMAND_SCRIPTS[args.command]
    if not script_path.is_file():
        raise FileNotFoundError(
            f"Maintenance implementation for {args.command!r} was not found: "
            f"{script_path}"
        )
    completed = subprocess.run(
        [sys.executable, str(script_path), *args.operation_args],
        check=False,
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
