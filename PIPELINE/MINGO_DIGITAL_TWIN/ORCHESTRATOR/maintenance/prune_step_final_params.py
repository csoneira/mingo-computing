#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/prune_step_final_params.py
Purpose: Prune step_final_simulation_params.csv using real file/metadata presence.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/prune_step_final_params.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import csv
import datetime
import pathlib
import sys
from collections import OrderedDict

ROOT = next(
    (parent for parent in pathlib.Path(__file__).resolve().parents if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()),
    None,
)
if ROOT is None:
    raise RuntimeError(f"Could not locate repository root from {__file__}")
STEP_FINAL_CSV = (
    ROOT
    / "PIPELINE" / "MINGO_DIGITAL_TWIN"
    / "SIMULATION_OUTPUTS"
    / "SIMULATED_DATA"
    / "step_final_simulation_params.csv"
)
REJECTED_CSV = (
    ROOT
    / "PIPELINE" / "MINGO_DIGITAL_TWIN"
    / "SIMULATION_OUTPUTS"
    / "SIMULATED_DATA"
    / "rejected_step_final_simulation_params.csv"
)
SIM_DATA_DIR = ROOT / "PIPELINE" / "MINGO_DIGITAL_TWIN" / "SIMULATION_OUTPUTS" / "SIMULATED_DATA"
SIM_DATA_FILES_DIR = SIM_DATA_DIR / "FILES"
STAGE0_SIM_DIR = ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / "MINGO00" / "STAGE_0" / "SIMULATION"
STAGE0_LIVE_CSV = STAGE0_SIM_DIR / "imported_basenames.csv"
STAGE0_HISTORY_CSV = STAGE0_SIM_DIR / "imported_basenames_history.csv"
STAGE0_TO_1_DIR = ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / "MINGO00" / "STAGE_0_TO_1"
STAGE1_STEP1_DIR = ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / "MINGO00" / "STAGE_1" / "EVENT_DATA" / "STEP_1"

REJECT_AUDIT_FIELDS = ("reject_reason", "rejected_at_utc", "rejected_by")
REJECTED_BY = "prune_step_final_params.py"

REASON_MISSING_NAME = "missing_file_name"
REASON_DUPLICATE_OLDER = "duplicate_file_name_older_row"
REASON_NOT_FOUND = "not_found_in_live_or_metadata"


def ts() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_csv_atomic(path: pathlib.Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _normalize_dat_name(value: str) -> str:
    text = str(value).strip()
    if not text:
        return ""
    stem = pathlib.Path(text).stem.strip().lower()
    if not stem.startswith("mi00"):
        return ""
    return f"{stem}.dat"


def _collect_csv_refs(
    csv_path: pathlib.Path,
    basename_columns: tuple[str, ...],
) -> tuple[set[str], int]:
    refs: set[str] = set()
    count = 0
    if not csv_path.exists():
        return refs, count

    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                raw_value = ""
                for col in basename_columns:
                    candidate = (row.get(col) or "").strip()
                    if candidate:
                        raw_value = candidate
                        break
                if not raw_value:
                    continue
                normalized = _normalize_dat_name(raw_value)
                if not normalized:
                    continue
                refs.add(normalized)
                count += 1
    except OSError as exc:
        print(
            f"{ts()} [PRUNE_FINAL] warn=read_error file={csv_path} err={exc}",
            file=sys.stderr,
        )

    return refs, count


def _read_csv_preserving_rows(path: pathlib.Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    return fieldnames, rows


def archive_removed_rows(
    removed_rows: list[tuple[dict[str, str], str]],
    source_fieldnames: list[str],
    dry_run: bool = False,
) -> int:
    if not removed_rows:
        return 0

    rejected_at = ts()
    archive_rows: list[dict[str, str]] = []
    for row, reason in removed_rows:
        payload = {name: row.get(name, "") for name in source_fieldnames}
        payload["reject_reason"] = reason
        payload["rejected_at_utc"] = rejected_at
        payload["rejected_by"] = REJECTED_BY
        archive_rows.append(payload)

    if dry_run:
        return len(archive_rows)

    existing_fieldnames, existing_rows = _read_csv_preserving_rows(REJECTED_CSV)
    merged_fieldnames = list(
        OrderedDict.fromkeys(existing_fieldnames + source_fieldnames + list(REJECT_AUDIT_FIELDS))
    )
    merged_rows = existing_rows + archive_rows
    _write_csv_atomic(REJECTED_CSV, merged_fieldnames, merged_rows)
    return len(archive_rows)


def collect_present_file_names() -> tuple[set[str], dict[str, int]]:
    """
    Collect live .dat file names from known simulation/downstream directories
    and metadata registries.

    Returns:
      - Set of lowercase .dat names currently present or referenced.
      - Per-source counters for observability.
    """
    present: set[str] = set()
    counters: dict[str, int] = {
        "sim_files_dir": 0,
        "sim_root_legacy": 0,
        "stage0_to_1": 0,
        "stage1_inputs": 0,
        "stage0_live_refs": 0,
        "stage0_history_refs": 0,
        "stage1_execution_refs": 0,
    }

    for path in SIM_DATA_FILES_DIR.glob("mi00*.dat"):
        if path.is_file():
            counters["sim_files_dir"] += 1
            present.add(path.name.strip().lower())

    for path in SIM_DATA_DIR.glob("mi00*.dat"):
        if path.is_file():
            counters["sim_root_legacy"] += 1
            present.add(path.name.strip().lower())

    for path in STAGE0_TO_1_DIR.glob("mi00*.dat"):
        if path.is_file():
            counters["stage0_to_1"] += 1
            present.add(path.name.strip().lower())

    for path in STAGE1_STEP1_DIR.glob("TASK_*/INPUT_FILES/*/*"):
        if not path.is_file():
            continue
        name = path.name.strip().lower()
        if not name.startswith("mi00") or not name.endswith(".dat"):
            continue
        counters["stage1_inputs"] += 1
        present.add(name)

    stage0_live_refs, stage0_live_count = _collect_csv_refs(
        STAGE0_LIVE_CSV,
        ("basename", "filename_base", "dat_name", "hld_name"),
    )
    counters["stage0_live_refs"] = stage0_live_count
    present.update(stage0_live_refs)

    stage0_history_refs, stage0_history_count = _collect_csv_refs(
        STAGE0_HISTORY_CSV,
        ("basename", "filename_base", "dat_name", "hld_name"),
    )
    counters["stage0_history_refs"] = stage0_history_count
    present.update(stage0_history_refs)

    for meta_csv in STAGE1_STEP1_DIR.glob("TASK_*/METADATA/task_*_metadata_execution.csv"):
        refs, count = _collect_csv_refs(
            meta_csv,
            ("filename_base", "basename", "dat_name", "hld_name", "file_name"),
        )
        counters["stage1_execution_refs"] += count
        present.update(refs)

    return present, counters


def prune(dry_run: bool = False) -> None:
    if not STEP_FINAL_CSV.exists():
        print(f"{ts()} [PRUNE_FINAL] status=no_csv path={STEP_FINAL_CSV}")
        return

    present_names, present_counters = collect_present_file_names()
    print(
        f"{ts()} [PRUNE_FINAL] present_files_unique={len(present_names)} "
        f"sim_files_dir={present_counters['sim_files_dir']} "
        f"sim_root_legacy={present_counters['sim_root_legacy']} "
        f"stage0_to_1={present_counters['stage0_to_1']} "
        f"stage1_inputs={present_counters['stage1_inputs']} "
        f"stage0_live_refs={present_counters['stage0_live_refs']} "
        f"stage0_history_refs={present_counters['stage0_history_refs']} "
        f"stage1_execution_refs={present_counters['stage1_execution_refs']}"
    )

    rows_total = 0
    fieldnames: list[str] = []
    all_seen_keys: set[str] = set()
    by_name: OrderedDict[str, dict[str, str]] = OrderedDict()
    removed_rows: list[tuple[dict[str, str], str]] = []

    with STEP_FINAL_CSV.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            rows_total += 1
            all_seen_keys.update(key for key in row.keys() if key)

            file_name = (row.get("file_name") or "").strip()
            if not file_name:
                removed_rows.append((row, REASON_MISSING_NAME))
                continue

            key = file_name.lower().strip()
            if key in by_name:
                removed_rows.append((by_name[key], REASON_DUPLICATE_OLDER))
                by_name.move_to_end(key)
            by_name[key] = row

    if not fieldnames:
        fieldnames = sorted(all_seen_keys)
    if not fieldnames:
        fieldnames = ["file_name"]

    kept: list[dict[str, str]] = []
    for row in by_name.values():
        file_name = (row.get("file_name") or "").strip().lower()
        if file_name in present_names:
            kept.append(row)
        else:
            removed_rows.append((row, REASON_NOT_FOUND))

    rows_removed = rows_total - len(kept)
    if rows_removed != len(removed_rows):
        print(
            f"{ts()} [PRUNE_FINAL] warn=removed_mismatch computed={rows_removed} tracked={len(removed_rows)}",
            file=sys.stderr,
        )

    reason_counts: dict[str, int] = {}
    for _, reason in removed_rows:
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    if not dry_run and rows_removed > 0:
        _write_csv_atomic(STEP_FINAL_CSV, fieldnames, kept)

    archived = archive_removed_rows(removed_rows, fieldnames, dry_run=dry_run)

    print(
        f"{ts()} [PRUNE_FINAL] status={'dry_run' if dry_run else 'done'}"
        f" total={rows_total} kept={len(kept)} removed={rows_removed}"
        f" removed_missing_name={reason_counts.get(REASON_MISSING_NAME, 0)}"
        f" removed_duplicates={reason_counts.get(REASON_DUPLICATE_OLDER, 0)}"
        f" removed_not_found_in_live_or_metadata={reason_counts.get(REASON_NOT_FOUND, 0)}"
        f" archived_to_rejected={archived}"
        f" rejected_csv={REJECTED_CSV}"
    )


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    prune(dry_run=dry_run)
