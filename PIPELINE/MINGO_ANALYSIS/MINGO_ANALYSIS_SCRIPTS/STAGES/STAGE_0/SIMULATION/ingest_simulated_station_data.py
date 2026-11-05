#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/SIMULATION/ingest_simulated_station_data.py
Purpose: !/usr/bin/env python3.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/SIMULATION/ingest_simulated_station_data.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
import sys

REPO_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()),
    None,
)
if REPO_ROOT is None:
    raise RuntimeError(f"Could not locate repository root from {__file__}")
sys.path.insert(0, str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.path_config import get_repo_root

DEFAULT_SIM_SOURCE_DIR = get_repo_root() / "PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/FILES"
REGISTRY_FIELDS = ["basename", "execution_timestamp"]
LIVE_REGISTRY_FILENAME = "imported_basenames.csv"
HISTORY_REGISTRY_FILENAME = "imported_basenames_history.csv"
LOCK_FILENAME = ".ingest_simulated_station_data.lock"


def now_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def write_registry_rows_atomic(registry_path: Path, rows: list[dict[str, str]]) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{registry_path.name}.",
        suffix=".tmp",
        dir=str(registry_path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REGISTRY_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        tmp_path.replace(registry_path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def acquire_lock_or_exit(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("w", encoding="ascii")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        print(f"Another ingest run is active (lock: {lock_path}); skipping this run.")
        raise SystemExit(0)
    return handle


def load_imported_basenames(registry_path: Path) -> set[str]:
    imported: set[str] = set()
    if not registry_path.exists():
        return imported
    with registry_path.open("r", encoding="ascii", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            basename = (row.get("basename") or "").strip()
            if basename:
                imported.add(basename)
    return imported


def normalize_registry_schema(registry_path: Path) -> int:
    if not registry_path.exists() or registry_path.stat().st_size == 0:
        return 0

    placeholder_timestamp = now_timestamp()
    normalized_rows: list[dict[str, str]] = []
    needs_rewrite = False

    with registry_path.open("r", encoding="ascii", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        has_basename = "basename" in fieldnames
        has_execution_timestamp = "execution_timestamp" in fieldnames
        if not has_basename or not has_execution_timestamp:
            needs_rewrite = True

        for row in reader:
            basename = (row.get("basename") or "").strip()
            if not basename:
                continue
            execution_timestamp = (row.get("execution_timestamp") or "").strip() if has_execution_timestamp else ""
            if not execution_timestamp:
                execution_timestamp = placeholder_timestamp
                needs_rewrite = True
            normalized_rows.append(
                {
                    "basename": basename,
                    "execution_timestamp": execution_timestamp,
                }
            )

    if not needs_rewrite:
        return 0

    write_registry_rows_atomic(registry_path, normalized_rows)
    return len(normalized_rows)


def load_simulation_param_basenames(sim_params_path: Path) -> set[str]:
    basenames: set[str] = set()
    if not sim_params_path.exists():
        return basenames
    with sim_params_path.open("r", encoding="ascii", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        file_name_column = "file_name" if "file_name" in fieldnames else None
        basename_column = "basename" if "basename" in fieldnames else None
        for row in reader:
            raw_name = (row.get(file_name_column) or "").strip() if file_name_column else ""
            if raw_name:
                basenames.add(Path(raw_name).stem)
                continue
            raw_basename = (row.get(basename_column) or "").strip() if basename_column else ""
            if raw_basename:
                basenames.add(Path(raw_basename).stem if raw_basename.endswith(".dat") else raw_basename)
    return basenames


def append_registry_basenames(registry_path: Path, basenames: list[str]) -> None:
    if not basenames:
        return
    write_header = (not registry_path.exists()) or registry_path.stat().st_size == 0
    execution_timestamp = now_timestamp()
    with registry_path.open("a", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerows(
            {
                "basename": basename,
                "execution_timestamp": execution_timestamp,
            }
            for basename in basenames
        )


def load_task_metadata_basenames(station_root: Path) -> set[str]:
    basenames: set[str] = set()
    step1_root = station_root / "STAGE_1" / "EVENT_DATA" / "STEP_1"
    for task_id in range(1, 6):
        metadata_csv = (
            step1_root
            / f"TASK_{task_id}"
            / "METADATA"
            / f"task_{task_id}_metadata_execution.csv"
        )
        if not metadata_csv.exists():
            continue
        with metadata_csv.open("r", encoding="ascii", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            base_col = None
            for candidate in ("filename_base", "basename", "dat_name", "hld_name"):
                if candidate in fieldnames:
                    base_col = candidate
                    break
            if base_col is None:
                continue
            for row in reader:
                raw = (row.get(base_col) or "").strip()
                if not raw:
                    continue
                basename = Path(raw).stem
                if basename.startswith("mi00"):
                    basenames.add(basename)
    return basenames


def find_ground_truth_basenames(station_root: Path) -> set[str]:
    """Return basenames found in the station downstream file structure.

    Searches the two fixed locations described in the prompt and returns
    a set of filename stems that start with ``mi00``. The caller is
    responsible for filtering the prefix and for any further use.
    """
    truth: set[str] = set()

    # first location: STAGE_0_TO_1/**/*. any file under that tree
    stage01 = station_root / "STAGE_0_TO_1"
    for p in stage01.rglob("*"):
        if p.is_file():
            truth.add(p.stem)

    # second location: STAGE_1/EVENT_DATA/STEP_1/TASK_*/INPUT_FILES/*/*
    step1 = station_root / "STAGE_1" / "EVENT_DATA" / "STEP_1"
    for task in step1.glob("TASK_*"):
        input_base = task / "INPUT_FILES"
        for subdir in input_base.glob("*"):
            if not subdir.is_dir():
                continue
            for f in subdir.glob("*"):
                if f.is_file():
                    truth.add(f.stem)

    # filter by prefix
    return {b for b in truth if b.startswith("mi00")}


def sync_registry_with_ground_truth(registry_path: Path, station_root: Path) -> tuple[int, int]:
    """Ensure ``registry_path`` matches the ground truth set.

    Returns a pair ``(added, removed)`` counts.  The CSV is rewritten
    atomically; existing ``execution_timestamp`` values are preserved for
    basenames that remain, and a fresh timestamp is assigned to new entries.
    """
    truth = find_ground_truth_basenames(station_root)

    existing: dict[str, str] = {}
    if registry_path.exists():
        with registry_path.open("r", encoding="ascii", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                b = (row.get("basename") or "").strip()
                if not b:
                    continue
                ts = (row.get("execution_timestamp") or "").strip()
                existing[b] = ts or now_timestamp()

    truth_set = set(truth)
    existing_set = set(existing.keys())

    to_add = sorted(truth_set - existing_set)
    to_remove = sorted(existing_set - truth_set)

    if to_add or to_remove:
        # build new row list preserving timestamps where available
        new_rows: list[dict[str, str]] = []
        timestamp_now = now_timestamp()
        for b in sorted(truth_set):
            new_rows.append(
                {
                    "basename": b,
                    "execution_timestamp": existing.get(b, timestamp_now),
                }
            )
        write_registry_rows_atomic(registry_path, new_rows)

    return len(to_add), len(to_remove)


def relocate_legacy_root_dat_files(source_dir: Path) -> int:
    if source_dir.name != "FILES":
        return 0
    legacy_root = source_dir.parent
    if legacy_root == source_dir:
        return 0
    moved = 0
    for legacy_dat in sorted(legacy_root.glob("mi0*.dat")):
        if not legacy_dat.is_file():
            continue
        destination = source_dir / legacy_dat.name
        if destination.exists():
            continue
        shutil.move(legacy_dat, destination)
        moved += 1
    return moved



def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 0 simulation: move .dat files into station buffers.")
    parser.add_argument(
        "--source-dir",
        default=DEFAULT_SIM_SOURCE_DIR,
        help="Directory containing simulated .dat files.",
    )
    args = parser.parse_args()

    current_path = Path(__file__).resolve()
    master_dir = next(
        (p for p in current_path.parents if p.name == "MINGO_ANALYSIS_SCRIPTS"),
        None,
    )
    if master_dir is None:
        raise RuntimeError(f"Unable to resolve MASTER directory from {current_path}")
    repo_root = get_repo_root()
    source_dir = Path(args.source_dir).expanduser().resolve()
    source_dir.mkdir(parents=True, exist_ok=True)
    if not source_dir.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {source_dir}")

    station_root = repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / "MINGO00"
    stage0_sim_dir = station_root / "STAGE_0" / "SIMULATION"
    stage01_dir = station_root / "STAGE_0_TO_1"
    stage0_sim_dir.mkdir(parents=True, exist_ok=True)
    stage01_dir.mkdir(parents=True, exist_ok=True)
    lock_handle = acquire_lock_or_exit(stage0_sim_dir / LOCK_FILENAME)
    try:
        relocated = relocate_legacy_root_dat_files(source_dir)

        live_registry_path = stage0_sim_dir / LIVE_REGISTRY_FILENAME
        history_registry_path = stage0_sim_dir / HISTORY_REGISTRY_FILENAME
        sim_params_path = (
            repo_root
            / "PIPELINE" / "MINGO_DIGITAL_TWIN"
            / "SIMULATION_OUTPUTS"
            / "SIMULATED_DATA"
            / "step_final_simulation_params.csv"
        )

        normalized_live_rows = normalize_registry_schema(live_registry_path)
        normalized_history_rows = normalize_registry_schema(history_registry_path)

        imported_history = load_imported_basenames(history_registry_path)
        imported_live = load_imported_basenames(live_registry_path)

        # Bootstrap history from any existing live registry entries.
        history_bootstrap_from_live = sorted(imported_live - imported_history)
        append_registry_basenames(history_registry_path, history_bootstrap_from_live)
        if history_bootstrap_from_live:
            imported_history.update(history_bootstrap_from_live)

        # Recover prior continuity from TASK metadata (historical evidence that
        # files passed through Stage 1).
        metadata_basenames = load_task_metadata_basenames(station_root)
        history_recovered_from_tasks = sorted(metadata_basenames - imported_history)
        append_registry_basenames(history_registry_path, history_recovered_from_tasks)
        if history_recovered_from_tasks:
            imported_history.update(history_recovered_from_tasks)

        moved = 0
        skipped_already_in_history = 0
        history_new_from_ingest: list[str] = []
        for dat_file in sorted(source_dir.glob("*.dat")):
            name = dat_file.name
            if not name.startswith("mi00"):
                continue
            basename = dat_file.stem
            if basename in imported_history:
                skipped_already_in_history += 1
                continue
            dest_path = stage01_dir / dat_file.name
            shutil.move(dat_file, dest_path)
            imported_history.add(basename)
            history_new_from_ingest.append(basename)
            moved += 1

        append_registry_basenames(history_registry_path, history_new_from_ingest)

        # Keep the live registry aligned with files currently in Stage 0/Task 1
        # input locations. This is operational state, not historical continuity.
        added_count, removed_count = sync_registry_with_ground_truth(live_registry_path, station_root)
        live_truth = find_ground_truth_basenames(station_root)
        imported_live_after = load_imported_basenames(live_registry_path)

        # Defensive: ensure live entries also exist in history.
        history_recovered_from_live = sorted(imported_live_after - imported_history)
        append_registry_basenames(history_registry_path, history_recovered_from_live)
        if history_recovered_from_live:
            imported_history.update(history_recovered_from_live)

        sim_param_basenames = load_simulation_param_basenames(sim_params_path)
        sim_params_missing_from_history = len(sim_param_basenames - imported_history)
        source_remaining = len(
            [entry for entry in source_dir.glob("mi00*.dat") if entry.is_file()]
        )

        print(
            f"Moved {moved} .dat files from {source_dir} into {stage01_dir}; "
            f"relocated {relocated} legacy root .dat files into {source_dir}; "
            f"normalized live/history rows={normalized_live_rows}/{normalized_history_rows}; "
            f"history bootstrap_from_live={len(history_bootstrap_from_live)}; "
            f"history recovered_from_tasks={len(history_recovered_from_tasks)}; "
            f"history new_from_ingest={len(history_new_from_ingest)}; "
            f"history recovered_from_live={len(history_recovered_from_live)}; "
            f"source skipped_already_in_history={skipped_already_in_history}; "
            f"live sync added {added_count}, removed {removed_count}, live count={len(live_truth)}; "
            f"history count={len(imported_history)}; "
            f"sim_params_total={len(sim_param_basenames)}, sim_params_missing_from_history={sim_params_missing_from_history}; "
            f"source_remaining={source_remaining}"
        )
    finally:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()


if __name__ == "__main__":
    main()
