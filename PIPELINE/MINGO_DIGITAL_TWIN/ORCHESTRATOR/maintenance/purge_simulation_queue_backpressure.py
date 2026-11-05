#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/purge_simulation_queue_backpressure.py
Purpose: Purge the simulation queue when backpressure is already high.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-04-29
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/purge_simulation_queue_backpressure.py [options]
Inputs: Queue files, param_mesh.csv, and sim_main_pipeline_frequency.conf.
Outputs: Deleted queue files, reset param_mesh.csv, stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = ROOT_DIR.parents[1]
sys.path.append(str(ROOT_DIR))
sys.path.append(str(ROOT_DIR / "MASTER_STEPS"))
sys.path.append(str(REPO_ROOT))

from STEP_SHARED.sim_utils import param_mesh_lock, write_csv_atomic, write_text_atomic


ROOT_RUNTIME_DIR = REPO_ROOT / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME"
DEFAULT_FREQUENCY_CONFIG = (
    ROOT_DIR / "CONFIG_FILES" / "ORCHESTRATOR" / "sim_main_pipeline_frequency.conf"
)
DEFAULT_SIMULATED_DATA_DIR = ROOT_DIR / "SIMULATION_OUTPUTS" / "SIMULATED_DATA"
DEFAULT_SIMULATED_DATA_FILES_DIR = DEFAULT_SIMULATED_DATA_DIR / "FILES"
DEFAULT_STATIONS_STEP1_DIR = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / "MINGO00" / "STAGE_1" / "EVENT_DATA" / "STEP_1"
DEFAULT_PARAM_MESH_PATH = (
    ROOT_DIR / "SIMULATION_OUTPUTS" / "INTERSTEPS" / "STEP_0_TO_1" / "param_mesh.csv"
)
DEFAULT_PARAM_MESH_METADATA_PATH = (
    ROOT_DIR
    / "SIMULATION_OUTPUTS"
    / "INTERSTEPS"
    / "STEP_0_TO_1"
    / "param_mesh_metadata.json"
)
IGNORED_QUEUE_PREFIXES = ("removed_channel_values_", "removed_rows_")


def _log_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _log_info(message: str) -> None:
    print(f"[{_log_ts()}] [STEP_PURGE_QUEUE] {message}")


def _log_warn(message: str) -> None:
    print(f"[{_log_ts()}] [STEP_PURGE_QUEUE] [WARN] {message}")


def _parse_shell_int_assignment(config_path: Path, variable_name: str) -> int | None:
    if not config_path.exists():
        return None
    pattern = re.compile(rf"^\s*{re.escape(variable_name)}\s*=\s*(.+?)\s*$")
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = pattern.match(line)
        if not match:
            continue
        value_text = match.group(1).strip().strip('"').strip("'")
        try:
            return int(value_text)
        except ValueError:
            return None
    return None


def _resolve_backpressure_threshold(config_path: Path) -> int:
    env_value = os.environ.get("SIM_MAX_UNPROCESSED_FILES")
    if env_value is not None:
        try:
            return int(env_value)
        except ValueError:
            _log_warn(
                f"Invalid SIM_MAX_UNPROCESSED_FILES environment value {env_value!r}; "
                "falling back to config file."
            )

    parsed = _parse_shell_int_assignment(config_path, "SIM_MAX_UNPROCESSED_FILES")
    if parsed is None:
        raise ValueError(
            f"Could not resolve SIM_MAX_UNPROCESSED_FILES from {config_path}."
        )
    return parsed


def _countable_queue_file(path: Path) -> bool:
    return path.is_file() and not path.name.startswith(IGNORED_QUEUE_PREFIXES)


def _iter_step1_queue_files(step1_root: Path, queue_name: str) -> Iterable[Path]:
    marker = f"INPUT_FILES/{queue_name}/"
    if not step1_root.is_dir():
        return ()
    return (
        path
        for path in step1_root.rglob("*")
        if _countable_queue_file(path) and marker in str(path)
    )


def _queue_files_by_bucket(
    simulated_data_dir: Path,
    simulated_data_files_dir: Path,
    step1_root: Path,
) -> dict[str, list[Path]]:
    return {
        "simulated_root": sorted(
            [
                path
                for path in simulated_data_dir.glob("mi*.dat")
                if path.is_file()
            ]
        )
        if simulated_data_dir.is_dir()
        else [],
        "simulated_files": sorted(
            [
                path
                for path in simulated_data_files_dir.glob("mi*.dat")
                if path.is_file()
            ]
        )
        if simulated_data_files_dir.is_dir()
        else [],
        "unprocessed": sorted(_iter_step1_queue_files(step1_root, "UNPROCESSED_DIRECTORY")),
        "processing": sorted(_iter_step1_queue_files(step1_root, "PROCESSING_DIRECTORY")),
    }


def _count_mesh_undone_rows(mesh_path: Path) -> int:
    if not mesh_path.exists():
        return 0
    try:
        mesh = pd.read_csv(mesh_path)
    except pd.errors.EmptyDataError:
        return 0
    if mesh.empty:
        return 0
    if "done" not in mesh.columns:
        return int(len(mesh))
    done_series = pd.to_numeric(mesh["done"], errors="coerce").fillna(0).astype(int)
    return int((done_series != 1).sum())


def _purge_queue_files(files_by_bucket: dict[str, list[Path]], *, dry_run: bool) -> dict[str, int]:
    deleted_counts: dict[str, int] = {}
    for bucket, paths in files_by_bucket.items():
        deleted = 0
        for path in paths:
            if dry_run:
                deleted += 1
                continue
            try:
                path.unlink()
                deleted += 1
            except FileNotFoundError:
                continue
        deleted_counts[bucket] = deleted
    return deleted_counts


def _clear_param_mesh(
    mesh_path: Path,
    mesh_metadata_path: Path,
    *,
    dry_run: bool,
) -> tuple[int, int]:
    if not mesh_path.exists():
        return 0, 0

    with param_mesh_lock(mesh_path):
        try:
            mesh = pd.read_csv(mesh_path)
        except pd.errors.EmptyDataError:
            mesh = pd.DataFrame()

        before = int(len(mesh))
        if dry_run:
            return before, before

        emptied = mesh.iloc[0:0].copy()
        write_csv_atomic(emptied, mesh_path, index=False)
        meta = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "row_count": 0,
            "step": "STEP_0",
            "maintenance_action": "purge_simulation_queue_backpressure",
        }
        write_text_atomic(mesh_metadata_path, json.dumps(meta, indent=2))
        return before, 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Delete the whole simulation queue only when the current backpressure "
            "already exceeds a configurable fraction of the established limit."
        )
    )
    parser.add_argument(
        "--frequency-config",
        default=str(DEFAULT_FREQUENCY_CONFIG),
        help="Path to sim_main_pipeline_frequency.conf",
    )
    parser.add_argument(
        "--simulated-data-dir",
        default=str(DEFAULT_SIMULATED_DATA_DIR),
        help="Path to PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA",
    )
    parser.add_argument(
        "--simulated-data-files-dir",
        default=str(DEFAULT_SIMULATED_DATA_FILES_DIR),
        help="Path to PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/FILES",
    )
    parser.add_argument(
        "--stations-step1-dir",
        default=str(DEFAULT_STATIONS_STEP1_DIR),
        help="Path to PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO00/STAGE_1/EVENT_DATA/STEP_1",
    )
    parser.add_argument(
        "--param-mesh",
        default=str(DEFAULT_PARAM_MESH_PATH),
        help="Path to SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv",
    )
    parser.add_argument(
        "--param-mesh-metadata",
        default=str(DEFAULT_PARAM_MESH_METADATA_PATH),
        help="Path to SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh_metadata.json",
    )
    parser.add_argument(
        "--fraction-of-limit",
        type=float,
        default=0.5,
        help="Only purge when current pending_total exceeds this fraction of the backpressure limit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be deleted without deleting anything.",
    )
    args = parser.parse_args()

    if not (0.0 < float(args.fraction_of_limit) <= 1.0):
        raise ValueError("--fraction-of-limit must be in (0, 1].")

    frequency_config = Path(args.frequency_config).expanduser().resolve()
    simulated_data_dir = Path(args.simulated_data_dir).expanduser().resolve()
    simulated_data_files_dir = Path(args.simulated_data_files_dir).expanduser().resolve()
    stations_step1_dir = Path(args.stations_step1_dir).expanduser().resolve()
    param_mesh_path = Path(args.param_mesh).expanduser().resolve()
    param_mesh_metadata_path = Path(args.param_mesh_metadata).expanduser().resolve()

    threshold = _resolve_backpressure_threshold(frequency_config)
    if threshold <= 0:
        raise ValueError(
            f"SIM_MAX_UNPROCESSED_FILES must be > 0 for this maintenance action; got {threshold}."
        )

    files_by_bucket = _queue_files_by_bucket(
        simulated_data_dir=simulated_data_dir,
        simulated_data_files_dir=simulated_data_files_dir,
        step1_root=stations_step1_dir,
    )
    counts_before = {bucket: len(paths) for bucket, paths in files_by_bucket.items()}
    pending_total = int(sum(counts_before.values()))
    mesh_undone_before = _count_mesh_undone_rows(param_mesh_path)
    trigger_level = float(threshold) * float(args.fraction_of_limit)

    _log_info(
        "Queue snapshot before purge "
        f"(threshold={threshold}, fraction={float(args.fraction_of_limit):.2f}, trigger_level={trigger_level:.1f}, "
        f"pending_total={pending_total}, simulated_root={counts_before['simulated_root']}, "
        f"simulated_files={counts_before['simulated_files']}, unprocessed={counts_before['unprocessed']}, "
        f"processing={counts_before['processing']}, mesh_undone_rows={mesh_undone_before})"
    )

    if pending_total <= trigger_level:
        action = "DRY-RUN" if args.dry_run else "SKIPPED"
        _log_info(
            f"{action}: pending_total={pending_total} does not exceed "
            f"{float(args.fraction_of_limit):.2f} * threshold ({trigger_level:.1f}); queue left untouched."
        )
        return

    deleted_counts = _purge_queue_files(files_by_bucket, dry_run=args.dry_run)
    mesh_before, mesh_after = _clear_param_mesh(
        param_mesh_path,
        param_mesh_metadata_path,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        _log_info(
            "DRY-RUN: would purge simulation queue "
            f"(deleted_simulated_root={deleted_counts['simulated_root']}, "
            f"deleted_simulated_files={deleted_counts['simulated_files']}, "
            f"deleted_unprocessed={deleted_counts['unprocessed']}, "
            f"deleted_processing={deleted_counts['processing']}, "
            f"param_mesh_rows_cleared={mesh_before})"
        )
        return

    files_after = _queue_files_by_bucket(
        simulated_data_dir=simulated_data_dir,
        simulated_data_files_dir=simulated_data_files_dir,
        step1_root=stations_step1_dir,
    )
    counts_after = {bucket: len(paths) for bucket, paths in files_after.items()}
    pending_after = int(sum(counts_after.values()))
    mesh_undone_after = _count_mesh_undone_rows(param_mesh_path)

    _log_info(
        "APPLIED: simulation queue purged "
        f"(deleted_simulated_root={deleted_counts['simulated_root']}, "
        f"deleted_simulated_files={deleted_counts['simulated_files']}, "
        f"deleted_unprocessed={deleted_counts['unprocessed']}, "
        f"deleted_processing={deleted_counts['processing']}, "
        f"param_mesh_rows_before={mesh_before}, param_mesh_rows_after={mesh_after})"
    )
    _log_info(
        "Queue snapshot after purge "
        f"(pending_total={pending_after}, simulated_root={counts_after['simulated_root']}, "
        f"simulated_files={counts_after['simulated_files']}, unprocessed={counts_after['unprocessed']}, "
        f"processing={counts_after['processing']}, mesh_undone_rows={mesh_undone_after})"
    )


if __name__ == "__main__":
    main()
