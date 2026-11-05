#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/OBSERVABILITY/AUDIT_PIPELINE_STATES/audit_pipeline_states.py
Purpose: !/usr/bin/env python3.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/OBSERVABILITY/AUDIT_PIPELINE_STATES/audit_pipeline_states.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


REPO_ROOT = Path(__file__).resolve().parents[5]
STATIONS_ROOT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
PROCESSED_ROOT = (
    REPO_ROOT
    / "CONTEXTUAL" / "OPERATIONS"
    / "OPERATIONS_SCRIPTS"
    / "DATA_MAINTENANCE"
    / "UPDATE_EXECUTION_CSVS"
    / "OUTPUT_FILES"
)

TASK_PREFIXES = ("cleaned_", "calibrated_", "listed_", "fitted_", "corrected_", "accumulated_")
SUFFIXES = (
    ".hld.tar.gz",
    ".hld-tar-gz",
    ".tar.gz",
    ".hld",
    ".dat",
    ".parquet",
    ".csv",
    ".gz",
)

ACCUMULATED_SPLIT_RE = re.compile(r"^\d+_mi0", re.IGNORECASE)
DATE_FORMATS = (
    "%Y-%m-%d_%H.%M.%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d_%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
)
STALE_HOURS_DEFAULT = 24.0

KNOWN_FLAGS = [
    "raw_brought",
    "imported",
    "reproc_hld_brought",
    "reproc_dat_unpacked",
    "processed_final",
    "stage0_to_1",
    "t1_unprocessed",
    "t1_processing",
    "t1_completed",
    "t1_error",
    "t1_output",
    "t1_status",
    "t2_unprocessed",
    "t2_processing",
    "t2_completed",
    "t2_error",
    "t2_output",
    "t2_status",
    "t3_unprocessed",
    "t3_processing",
    "t3_completed",
    "t3_error",
    "t3_output",
    "t3_status",
    "t4_unprocessed",
    "t4_processing",
    "t4_completed",
    "t4_error",
    "t4_output",
    "t4_status",
    "t5_unprocessed",
    "t5_processing",
    "t5_completed",
    "t5_error",
    "t5_output",
    "t5_status",
    "step1_to_2_output",
    "s2_unprocessed",
    "s2_processing",
    "s2_completed",
    "s2_error",
    "s2_rejected",
    "s2_output",
    "s3_task1_to_2",
    "s3_task1_archive",
]

STAGE_RANK = [
    ("processed_final", "Processed"),
    ("s3_task1_to_2", "Step 3 Split"),
    ("s2_output", "Step 2 Output"),
    ("step1_to_2_output", "Step 1 Output"),
    ("t5_output", "Task 5 Output"),
    ("t5_processing", "Task 5 Processing"),
    ("t5_unprocessed", "Task 5 Unprocessed"),
    ("t4_output", "Task 4 Output"),
    ("t4_processing", "Task 4 Processing"),
    ("t4_unprocessed", "Task 4 Unprocessed"),
    ("t3_output", "Task 3 Output"),
    ("t3_processing", "Task 3 Processing"),
    ("t3_unprocessed", "Task 3 Unprocessed"),
    ("t2_output", "Task 2 Output"),
    ("t2_processing", "Task 2 Processing"),
    ("t2_unprocessed", "Task 2 Unprocessed"),
    ("t1_output", "Task 1 Output"),
    ("t1_processing", "Task 1 Processing"),
    ("t1_unprocessed", "Task 1 Unprocessed"),
    ("stage0_to_1", "Stage0_to_1"),
    ("raw_brought", "Raw Brought"),
    ("reproc_hld_brought", "Reproc HLD Brought"),
    ("reproc_dat_unpacked", "Reproc Dat Unpacked"),
    ("imported", "Imported"),
]

STATION_ZERO = "0"
STATION_ZERO_DISABLED_FLAGS = {"reproc_hld_brought", "reproc_dat_unpacked"}
TURBO_DISCRETE_HEX = [
    "#30123b",
    "#3b2f80",
    "#434eba",
    "#466be3",
    "#4685fa",
    "#3ba0fd",
    "#28bceb",
    "#1ad2d2",
    "#1ae4b6",
    "#32f298",
    "#55fa76",
    "#80ff53",
    "#a4fc3c",
    "#bef434",
    "#d9e436",
    "#eecf3a",
    "#faba39",
    "#fe9e2f",
    "#fb7e21",
    "#f26014",
    "#e4450a",
    "#d02f05",
    "#b91e02",
    "#9b0f01",
    "#7a0403",
]


def build_stage_colors() -> Dict[str, str]:
    labels = [label for _flag, label in STAGE_RANK] + ["Unknown"]
    return {
        label: TURBO_DISCRETE_HEX[idx % len(TURBO_DISCRETE_HEX)]
        for idx, label in enumerate(labels)
    }


STAGE_COLORS = build_stage_colors()


def active_flags_for_station(station: str) -> List[str]:
    if station == STATION_ZERO:
        return [flag for flag in KNOWN_FLAGS if flag not in STATION_ZERO_DISABLED_FLAGS]
    return list(KNOWN_FLAGS)


def parse_station_list(text: str) -> List[str]:
    cleaned = text.strip().lower()
    if not cleaned or cleaned in {"all", "*"}:
        stations = []
        for path in sorted(STATIONS_ROOT.glob("MINGO0*")):
            if path.is_dir() and path.name.startswith("MINGO0") and len(path.name) == 7:
                stations.append(path.name[-1])
        return stations
    values: List[str] = []
    for token in cleaned.replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        if not token.isdigit():
            raise ValueError(f"Invalid station value: {token}")
        number = int(token)
        if number < 0 or number > 9:
            raise ValueError(f"Station must be in [0, 9], got {number}")
        values.append(str(number))
    return sorted(set(values))


def strip_known_suffixes(name: str) -> str:
    value = name
    changed = True
    while changed:
        changed = False
        lower = value.lower()
        for suffix in SUFFIXES:
            if lower.endswith(suffix):
                value = value[: -len(suffix)]
                changed = True
                break
    return value


def normalize_basename(name: str) -> str:
    base = strip_known_suffixes(Path(name).name)
    for prefix in TASK_PREFIXES:
        if base.startswith(prefix):
            base = base[len(prefix):]
            if prefix == "accumulated_" and ACCUMULATED_SPLIT_RE.match(base):
                base = re.sub(r"^\d+_", "", base)
            break
    return base


def parse_datetime(value: str) -> Optional[datetime]:
    text = value.strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def format_datetime(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def load_csv_basenames(path: Path, columns: Iterable[str]) -> Set[str]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return set()
        basenames: Set[str] = set()
        for row in reader:
            value: Optional[str] = None
            for column in columns:
                candidate = row.get(column)
                if candidate:
                    value = candidate
                    break
            if value is None:
                # Fallback to the first non-empty column.
                for candidate in row.values():
                    if candidate:
                        value = candidate
                        break
            if not value:
                continue
            base = normalize_basename(value.strip())
            if base:
                basenames.add(base)
        return basenames


def load_csv_basename_events(
    path: Path,
    *,
    base_columns: Iterable[str],
    timestamp_columns: Iterable[str],
    fallback_to_mtime: bool = False,
) -> List[Tuple[str, Optional[datetime]]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    fallback_ts = None
    if fallback_to_mtime:
        try:
            fallback_ts = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            fallback_ts = None

    events: List[Tuple[str, Optional[datetime]]] = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return events
        for row in reader:
            value: Optional[str] = None
            for column in base_columns:
                candidate = row.get(column)
                if candidate:
                    value = candidate
                    break
            if value is None:
                for candidate in row.values():
                    if candidate:
                        value = candidate
                        break
            if not value:
                continue
            base = normalize_basename(value.strip())
            if not base:
                continue
            ts: Optional[datetime] = None
            for column in timestamp_columns:
                candidate = row.get(column)
                if candidate:
                    ts = parse_datetime(candidate)
                    if ts is not None:
                        break
            if ts is None and fallback_ts is not None:
                ts = fallback_ts
            events.append((base, ts))
    return events


def count_csv_rows(path: Path) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    try:
        with path.open(newline="") as handle:
            reader = csv.reader(handle)
            row_count = -1
            for row_count, _ in enumerate(reader):
                pass
        return max(0, row_count)
    except OSError:
        return 0


def collect_dir_basenames(path: Path, *, recursive: bool = False) -> Set[str]:
    if not path.exists() or not path.is_dir():
        return set()
    basenames: Set[str] = set()
    entries = path.rglob("*") if recursive else path.iterdir()
    for entry in entries:
        if not entry.is_file():
            continue
        base = normalize_basename(entry.name)
        if base:
            basenames.add(base)
    return basenames


def collect_dir_events(path: Path, *, recursive: bool = False) -> List[Tuple[str, Optional[datetime], Optional[str]]]:
    if not path.exists() or not path.is_dir():
        return []
    events: List[Tuple[str, Optional[datetime], Optional[str]]] = []
    entries = path.rglob("*") if recursive else path.iterdir()
    for entry in entries:
        if not entry.is_file():
            continue
        base = normalize_basename(entry.name)
        if not base:
            continue
        ts = None
        try:
            ts = datetime.fromtimestamp(entry.stat().st_mtime)
        except OSError:
            ts = None
        events.append((base, ts, str(entry)))
    return events


def count_dir_files(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    return sum(1 for entry in path.iterdir() if entry.is_file())


def count_dir_files_recursive(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    return sum(1 for entry in path.rglob("*") if entry.is_file())


def add_flag(states: Dict[str, Dict[str, bool]], basename: str, flag: str) -> None:
    if not basename:
        return
    states.setdefault(basename, {})[flag] = True


def update_last_seen(
    last_seen: Dict[str, datetime],
    last_seen_source: Dict[str, str],
    basename: str,
    ts: Optional[datetime],
    source: Optional[str],
) -> None:
    if not basename or ts is None:
        return
    existing = last_seen.get(basename)
    if existing is None or ts > existing:
        last_seen[basename] = ts
        if source:
            last_seen_source[basename] = source


def collect_task_dirs(task_root: Path) -> Dict[str, Path]:
    return {
        "unprocessed": task_root / "INPUT_FILES" / "UNPROCESSED_DIRECTORY",
        "processing": task_root / "INPUT_FILES" / "PROCESSING_DIRECTORY",
        "completed": task_root / "INPUT_FILES" / "COMPLETED_DIRECTORY",
        "error": task_root / "INPUT_FILES" / "ERROR_DIRECTORY",
        "output": task_root / "OUTPUT_FILES",
        "metadata": task_root / "METADATA",
    }


def station_inventory_entries(station: str) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    station_dir = STATIONS_ROOT / f"MINGO0{station}"
    base_event = station_dir / "STAGE_1" / "EVENT_DATA"

    def add_entry(kind: str, path: Path, note: str, source: str, count: int) -> None:
        entries.append(
            {
                "station": station,
                "kind": kind,
                "path": str(path),
                "exists": "yes" if path.exists() else "no",
                "count": str(count),
                "note": note,
                "source": source,
            }
        )

    raw_brought = station_dir / "STAGE_0" / "NEW_FILES" / "METADATA" / "raw_files_brought.csv"
    add_entry(
        "reject_list",
        raw_brought,
        "Already-brought raw .dat files (skipped by bring_data_and_config_files.sh).",
        "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/NEW_FILES/bring_data_and_config_files.sh",
        count_csv_rows(raw_brought),
    )

    imported = station_dir / "STAGE_0" / "imported_basenames.csv"
    add_entry(
        "import_list",
        imported,
        "Simulation Stage 0 imported basenames (station 0).",
        "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/SIMULATION/ingest_simulated_station_data.py",
        count_csv_rows(imported),
    )

    if station != STATION_ZERO:
        hld_brought = station_dir / "STAGE_0" / "REPROCESSING" / "STEP_1" / "METADATA" / "hld_files_brought.csv"
        add_entry(
            "reject_list",
            hld_brought,
            "Reprocessing Step 1: HLD basenames already brought.",
            "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/STEP_1/bring_reprocessing_files.sh",
            count_csv_rows(hld_brought),
        )

        dat_unpacked = station_dir / "STAGE_0" / "REPROCESSING" / "STEP_2" / "METADATA" / "dat_files_unpacked.csv"
        add_entry(
            "reject_list",
            dat_unpacked,
            "Reprocessing Step 2: dat files already unpacked.",
            "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/STEP_2/unpack_reprocessing_files.sh",
            count_csv_rows(dat_unpacked),
        )

    processed = PROCESSED_ROOT / f"MINGO0{station}_processed_basenames.csv"
    add_entry(
        "processed_list",
        processed,
        "Basenames backed by valid station Parquet Lake archives (used as reject list).",
        "CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/FILE_FLOW_TRACKER/file_flow_tracker.py",
        count_csv_rows(processed),
    )

    stage0_to_1 = station_dir / "STAGE_0_TO_1"
    add_entry(
        "queue_dir",
        stage0_to_1,
        "Raw .dat files ready for STEP_1/TASK_1.",
        "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/STEP_1/TASK_1/script_1_raw_to_clean.py",
        count_dir_files(stage0_to_1),
    )

    for task in range(1, 6):
        task_root = base_event / "STEP_1" / f"TASK_{task}"
        dirs = collect_task_dirs(task_root)
        for label, suffix in (
            ("queue_unprocessed", "unprocessed"),
            ("queue_processing", "processing"),
            ("queue_completed", "completed"),
            ("queue_error", "error"),
            ("output_dir", "output"),
        ):
            path = dirs[suffix]
            add_entry(
                label,
                path,
                f"STEP_1/TASK_{task} {suffix} files.",
                f"PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/STEP_1/TASK_{task}/script_{task}_*.py",
                count_dir_files(path),
            )
        for suffix, kind in (
            ("task_{task}_metadata_execution.csv", "metadata_execution"),
            ("task_{task}_metadata_specific.csv", "metadata_specific"),
            ("task_{task}_metadata_filter.csv", "metadata_filter"),
            ("task_{task}_metadata_status.csv", "metadata_status"),
        ):
            path = dirs["metadata"] / suffix.format(task=task)
            add_entry(
                kind,
                path,
                f"STEP_1/TASK_{task} metadata CSV.",
                f"PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/STEP_1/TASK_{task}/script_{task}_*.py",
                count_csv_rows(path),
            )

    step1_to_2 = station_dir / "STAGE_1_PRODUCTS" / "EVENT_DATA" / "PARQUET_LAKE"
    add_entry(
        "output_dir",
        step1_to_2,
        "Stage 1 event parquet lake (task 5 postprocessed products).",
        "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/STEP_1/TASK_5/script_5_fit_to_post.py",
        count_dir_files(step1_to_2),
    )

    step2_root = station_dir / "STAGE_2" / "EVENT_DATA" / "STEP_1_ACCUMULATION"
    for label in ("UNPROCESSED", "PROCESSING", "COMPLETED", "ERROR_DIRECTORY", "REJECTED"):
        path = step2_root / "INPUT_FILES" / label
        add_entry(
            f"step2_queue_{label.lower()}",
            path,
            f"STAGE_2 EVENT_DATA STEP_1_ACCUMULATION {label} files.",
            "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_2/EVENT_DATA/STEP_1_ACCUMULATION/corrected_to_accumulated.py",
            count_dir_files(path),
        )
    for name in ("step_2_metadata_execution.csv", "step_2_metadata_specific.csv"):
        path = step2_root / "METADATA" / name
        add_entry(
            "metadata_execution" if "execution" in name else "metadata_specific",
            path,
            "STAGE_2 EVENT_DATA STEP_1_ACCUMULATION metadata CSV.",
            "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_2/EVENT_DATA/STEP_1_ACCUMULATION/corrected_to_accumulated.py",
            count_csv_rows(path),
        )

    step2_to_3 = station_dir / "STAGE_2" / "EVENT_DATA" / "ACCUMULATED_EVENTS"
    add_entry(
        "output_dir",
        step2_to_3,
        "STAGE_2 EVENT_DATA STEP_1_ACCUMULATION accumulated outputs.",
        "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_2/EVENT_DATA/STEP_1_ACCUMULATION/corrected_to_accumulated.py",
        count_dir_files(step2_to_3),
    )

    step3_root = station_dir / "STAGE_2" / "EVENT_DATA" / "STEP_2_DAILY_EVENT_DATA"
    task1_to_2 = step3_root / "TASK_1_TO_2"
    add_entry(
        "output_dir",
        task1_to_2,
        "STAGE_2 EVENT_DATA STEP_2_DAILY_EVENT_DATA/TASK_1_TO_2 daily accumulated outputs.",
        "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_2/EVENT_DATA/STEP_2_DAILY_EVENT_DATA/TASK_1/accumulated_distributor.py",
        count_dir_files_recursive(task1_to_2),
    )
    task1_archive = step3_root / "TASK_1" / "INPUT_FILES"
    add_entry(
        "archive_dir",
        task1_archive,
        "STAGE_2 EVENT_DATA STEP_2_DAILY_EVENT_DATA/TASK_1 archive of accumulated files.",
        "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_2/EVENT_DATA/STEP_2_DAILY_EVENT_DATA/TASK_1/accumulated_distributor.py",
        count_dir_files(task1_archive),
    )
    task2_output = step3_root / "TASK_2" / "OUTPUT_FILES"
    add_entry(
        "output_dir",
        task2_output,
        "STAGE_2 EVENT_DATA STEP_2_DAILY_EVENT_DATA/TASK_2 joined outputs (event_data_YYYY_MM_DD.csv).",
        "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_2/EVENT_DATA/STEP_2_DAILY_EVENT_DATA/TASK_2/distributed_joiner.py",
        count_dir_files_recursive(task2_output),
    )

    return entries


def collect_station_states(
    station: str,
) -> Tuple[
    Dict[str, Dict[str, bool]],
    Dict[str, datetime],
    Dict[str, str],
    List[Dict[str, str]],
]:
    station_dir = STATIONS_ROOT / f"MINGO0{station}"
    base_event = station_dir / "STAGE_1" / "EVENT_DATA"

    states: Dict[str, Dict[str, bool]] = {}
    last_seen: Dict[str, datetime] = {}
    last_seen_source: Dict[str, str] = {}
    inventory = station_inventory_entries(station)

    def mark_set(values: Set[str], flag: str) -> None:
        for base in values:
            add_flag(states, base, flag)

    def mark_events(values: List[Tuple[str, Optional[datetime]]], flag: str, source: str) -> None:
        for base, ts in values:
            add_flag(states, base, flag)
            update_last_seen(last_seen, last_seen_source, base, ts, source)

    def mark_dir_events(values: List[Tuple[str, Optional[datetime], Optional[str]]], flag: str, default_source: str) -> None:
        for base, ts, source in values:
            add_flag(states, base, flag)
            update_last_seen(last_seen, last_seen_source, base, ts, source or default_source)

    # Stage 0 lists
    raw_brought_path = station_dir / "STAGE_0" / "NEW_FILES" / "METADATA" / "raw_files_brought.csv"
    raw_brought_events = load_csv_basename_events(
        raw_brought_path,
        base_columns=("filename", "basename", "hld_name", "dat_name"),
        timestamp_columns=("bring_timestamp", "timestamp", "execution_timestamp"),
    )
    mark_events(raw_brought_events, "raw_brought", str(raw_brought_path))

    imported_path = station_dir / "STAGE_0" / "imported_basenames.csv"
    imported_events = load_csv_basename_events(
        imported_path,
        base_columns=("basename",),
        timestamp_columns=(),
        fallback_to_mtime=True,
    )
    mark_events(imported_events, "imported", str(imported_path))

    if station != STATION_ZERO:
        hld_brought_path = (
            station_dir
            / "STAGE_0"
            / "REPROCESSING"
            / "STEP_1"
            / "METADATA"
            / "hld_files_brought.csv"
        )
        hld_brought_events = load_csv_basename_events(
            hld_brought_path,
            base_columns=("hld_name", "basename"),
            timestamp_columns=("bring_timesamp", "bring_timestamp", "timestamp"),
        )
        mark_events(hld_brought_events, "reproc_hld_brought", str(hld_brought_path))

        dat_unpacked_path = (
            station_dir
            / "STAGE_0"
            / "REPROCESSING"
            / "STEP_2"
            / "METADATA"
            / "dat_files_unpacked.csv"
        )
        dat_unpacked_events = load_csv_basename_events(
            dat_unpacked_path,
            base_columns=("dat_name", "basename"),
            timestamp_columns=("execution_timestamp", "timestamp"),
        )
        mark_events(dat_unpacked_events, "reproc_dat_unpacked", str(dat_unpacked_path))

    processed_path = PROCESSED_ROOT / f"MINGO0{station}_processed_basenames.csv"
    processed_events = load_csv_basename_events(
        processed_path,
        base_columns=("basename",),
        timestamp_columns=("execution_timestamp", "execution_date", "timestamp"),
    )
    mark_events(processed_events, "processed_final", str(processed_path))

    # Stage 0 to 1 queue
    stage0_to_1_dir = station_dir / "STAGE_0_TO_1"
    mark_dir_events(
        collect_dir_events(stage0_to_1_dir),
        "stage0_to_1",
        str(stage0_to_1_dir),
    )

    # STEP 1 tasks 1-5
    for task in range(1, 6):
        task_root = base_event / "STEP_1" / f"TASK_{task}"
        dirs = collect_task_dirs(task_root)
        mark_dir_events(
            collect_dir_events(dirs["unprocessed"]),
            f"t{task}_unprocessed",
            str(dirs["unprocessed"]),
        )
        mark_dir_events(
            collect_dir_events(dirs["processing"]),
            f"t{task}_processing",
            str(dirs["processing"]),
        )
        mark_dir_events(
            collect_dir_events(dirs["completed"]),
            f"t{task}_completed",
            str(dirs["completed"]),
        )
        mark_dir_events(
            collect_dir_events(dirs["error"]),
            f"t{task}_error",
            str(dirs["error"]),
        )

        if task == 5:
            output_dir = station_dir / "STAGE_1_PRODUCTS" / "EVENT_DATA" / "PARQUET_LAKE"
            mark_dir_events(
                collect_dir_events(output_dir),
                "step1_to_2_output",
                str(output_dir),
            )
            mark_dir_events(
                collect_dir_events(output_dir),
                f"t{task}_output",
                str(output_dir),
            )
        else:
            mark_dir_events(
                collect_dir_events(dirs["output"]),
                f"t{task}_output",
                str(dirs["output"]),
            )

        status_path = dirs["metadata"] / f"task_{task}_metadata_status.csv"
        status_events = load_csv_basename_events(
            status_path,
            base_columns=("filename_base", "basename"),
            timestamp_columns=("execution_date", "execution_timestamp", "timestamp"),
            fallback_to_mtime=True,
        )
        mark_events(status_events, f"t{task}_status", str(status_path))

    # STEP 2 queues + outputs
    step2_root = station_dir / "STAGE_2" / "EVENT_DATA" / "STEP_1_ACCUMULATION"
    mark_dir_events(
        collect_dir_events(step2_root / "INPUT_FILES" / "UNPROCESSED"),
        "s2_unprocessed",
        str(step2_root / "INPUT_FILES" / "UNPROCESSED"),
    )
    mark_dir_events(
        collect_dir_events(step2_root / "INPUT_FILES" / "PROCESSING"),
        "s2_processing",
        str(step2_root / "INPUT_FILES" / "PROCESSING"),
    )
    mark_dir_events(
        collect_dir_events(step2_root / "INPUT_FILES" / "COMPLETED"),
        "s2_completed",
        str(step2_root / "INPUT_FILES" / "COMPLETED"),
    )
    mark_dir_events(
        collect_dir_events(step2_root / "INPUT_FILES" / "ERROR_DIRECTORY"),
        "s2_error",
        str(step2_root / "INPUT_FILES" / "ERROR_DIRECTORY"),
    )
    mark_dir_events(
        collect_dir_events(step2_root / "INPUT_FILES" / "REJECTED"),
        "s2_rejected",
        str(step2_root / "INPUT_FILES" / "REJECTED"),
    )
    mark_dir_events(
        collect_dir_events(station_dir / "STAGE_2" / "EVENT_DATA" / "ACCUMULATED_EVENTS"),
        "s2_output",
        str(station_dir / "STAGE_2" / "EVENT_DATA" / "ACCUMULATED_EVENTS"),
    )

    # STEP 3 directories
    step3_root = station_dir / "STAGE_2" / "EVENT_DATA" / "STEP_2_DAILY_EVENT_DATA"
    mark_dir_events(
        collect_dir_events(step3_root / "TASK_1_TO_2", recursive=True),
        "s3_task1_to_2",
        str(step3_root / "TASK_1_TO_2"),
    )
    mark_dir_events(
        collect_dir_events(step3_root / "TASK_1" / "INPUT_FILES"),
        "s3_task1_archive",
        str(step3_root / "TASK_1" / "INPUT_FILES"),
    )

    return states, last_seen, last_seen_source, inventory


def summarize_counts(states: Dict[str, Dict[str, bool]]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for flags in states.values():
        for flag, enabled in flags.items():
            if enabled:
                counts[flag] += 1
    return dict(counts)


def determine_stage(flags: Dict[str, bool]) -> str:
    for flag, label in STAGE_RANK:
        if flags.get(flag):
            return label
    return "Unknown"


def build_reason(flags: Dict[str, bool]) -> str:
    reasons: List[str] = []
    if flags.get("processed_final"):
        reasons.append("marked processed")
    if flags.get("t1_error") or flags.get("t2_error") or flags.get("t3_error") or flags.get("t4_error") or flags.get("t5_error"):
        reasons.append("file in ERROR_DIRECTORY")
    if flags.get("s2_error"):
        reasons.append("STAGE_2 EVENT_DATA STEP_1_ACCUMULATION error directory")
    if flags.get("s2_rejected"):
        reasons.append("STAGE_2 EVENT_DATA STEP_1_ACCUMULATION rejected")
    if flags.get("raw_brought") and not any(flags.get(k) for k, _ in STAGE_RANK):
        reasons.append("only in raw_brought list")
    if flags.get("reproc_hld_brought") and not flags.get("reproc_dat_unpacked"):
        reasons.append("HLD brought but not unpacked")
    if flags.get("reproc_dat_unpacked") and not (flags.get("s2_output") or flags.get("processed_final")):
        reasons.append("dat unpacked but no downstream outputs")
    if not reasons:
        return ""
    return "; ".join(reasons)


def detect_anomalies(
    states: Dict[str, Dict[str, bool]],
    last_seen: Dict[str, datetime],
    last_seen_source: Dict[str, str],
    *,
    now: datetime,
    stale_hours: float,
) -> List[Dict[str, str]]:
    anomalies: List[Dict[str, str]] = []

    def has_any(flags: Dict[str, bool], prefix: str) -> bool:
        return any(flag.startswith(prefix) and enabled for flag, enabled in flags.items())

    for basename, flags in states.items():
        if flags.get("raw_brought") and not (
            flags.get("stage0_to_1")
            or flags.get("processed_final")
            or has_any(flags, "t1_")
            or has_any(flags, "t2_")
            or has_any(flags, "t3_")
            or has_any(flags, "t4_")
            or has_any(flags, "t5_")
            or flags.get("step1_to_2_output")
            or flags.get("s2_output")
        ):
            anomalies.append(
                {
                    "basename": basename,
                    "issue": "raw_brought_missing",
                    "details": "In raw_files_brought.csv but not found in queues or outputs.",
                    "last_seen": format_datetime(last_seen.get(basename)),
                    "age_hours": "",
                    "stage": determine_stage(flags),
                    "reason": build_reason(flags),
                    "last_seen_source": last_seen_source.get(basename, ""),
                }
            )

        if flags.get("processed_final") and (
            flags.get("t1_unprocessed")
            or flags.get("t1_processing")
            or flags.get("t2_unprocessed")
            or flags.get("t2_processing")
            or flags.get("t3_unprocessed")
            or flags.get("t3_processing")
            or flags.get("t4_unprocessed")
            or flags.get("t4_processing")
            or flags.get("t5_unprocessed")
            or flags.get("t5_processing")
            or flags.get("s2_unprocessed")
            or flags.get("s2_processing")
        ):
            anomalies.append(
                {
                    "basename": basename,
                    "issue": "processed_but_queued",
                    "details": "Basename appears in processed list but is still in a queue.",
                    "last_seen": format_datetime(last_seen.get(basename)),
                    "age_hours": "",
                    "stage": determine_stage(flags),
                    "reason": build_reason(flags),
                    "last_seen_source": last_seen_source.get(basename, ""),
                }
            )

        if flags.get("reproc_hld_brought") and not flags.get("reproc_dat_unpacked"):
            anomalies.append(
                {
                    "basename": basename,
                    "issue": "reproc_hld_not_unpacked",
                    "details": "HLD brought but not recorded as unpacked.",
                    "last_seen": format_datetime(last_seen.get(basename)),
                    "age_hours": "",
                    "stage": determine_stage(flags),
                    "reason": build_reason(flags),
                    "last_seen_source": last_seen_source.get(basename, ""),
                }
            )

        if flags.get("reproc_dat_unpacked") and not (
            flags.get("processed_final") or has_any(flags, "t1_") or flags.get("s2_output")
        ):
            anomalies.append(
                {
                    "basename": basename,
                    "issue": "dat_unpacked_not_seen",
                    "details": "dat_files_unpacked.csv entry not seen in pipeline outputs.",
                    "last_seen": format_datetime(last_seen.get(basename)),
                    "age_hours": "",
                    "stage": determine_stage(flags),
                    "reason": build_reason(flags),
                    "last_seen_source": last_seen_source.get(basename, ""),
                }
            )

        ts = last_seen.get(basename)
        if ts is not None and not flags.get("processed_final"):
            age = (now - ts).total_seconds() / 3600.0
            if age >= stale_hours:
                anomalies.append(
                    {
                        "basename": basename,
                        "issue": "stale",
                        "details": f"No newer activity in >= {stale_hours:.1f}h.",
                        "last_seen": format_datetime(ts),
                        "age_hours": f"{age:.2f}",
                        "stage": determine_stage(flags),
                        "reason": build_reason(flags),
                        "last_seen_source": last_seen_source.get(basename, ""),
                    }
                )

    return anomalies


def write_csv(path: Path, rows: Iterable[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def scan_logs_for_basenames(
    basenames: Set[str],
    log_roots: List[Path],
    *,
    max_matches: int = 1,
    max_bytes_per_file: int = 5_000_000,
) -> Dict[str, str]:
    if not basenames:
        return {}
    remaining = set(basenames)
    found: Dict[str, str] = {}

    for root in log_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.log"):
            if not remaining:
                break
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size <= 0:
                continue
            if size > max_bytes_per_file:
                # Read only the last max_bytes_per_file bytes for large logs.
                try:
                    with path.open("rb") as handle:
                        handle.seek(-max_bytes_per_file, 2)
                        content = handle.read().decode("utf-8", errors="ignore").splitlines()
                except OSError:
                    continue
            else:
                try:
                    with path.open("r", encoding="utf-8", errors="ignore") as handle:
                        content = handle.read().splitlines()
                except OSError:
                    continue

            for line in content:
                if not remaining:
                    break
                for base in list(remaining):
                    if base in line:
                        found[base] = f"{path}: {line.strip()}"
                        remaining.remove(base)
                        if len(found) >= max_matches and not remaining:
                            break
    return found


def _html_escape(value: object) -> str:
    text = str(value) if value is not None else ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def write_html_report(
    output_dir: Path,
    *,
    summary_rows: List[Dict[str, str]],
    anomalies: List[Dict[str, str]],
    stale_rows: List[Dict[str, str]],
    basenames: List[Dict[str, str]],
    max_rows: int,
) -> None:
    def stage_badge(stage: str) -> str:
        color = STAGE_COLORS.get(stage, STAGE_COLORS["Unknown"])
        return f'<span class="badge" style="background:{color}">{_html_escape(stage)}</span>'

    summary_by_station: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in summary_rows:
        summary_by_station[row.get("station", "")].append(row)

    html_parts: List[str] = []
    html_parts.append(
        """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>DATAFLOW Pipeline Audit</title>
<style>
body { font-family: Arial, sans-serif; margin: 24px; color: #222; }
h1,h2 { margin: 0 0 12px 0; }
.section { margin: 24px 0; }
.badge { color: #fff; padding: 2px 8px; border-radius: 12px; font-size: 12px; display: inline-block; }
table { border-collapse: collapse; width: 100%; font-size: 12px; }
th, td { border: 1px solid #ddd; padding: 6px 8px; vertical-align: top; }
th { background: #f4f4f4; text-align: left; }
.muted { color: #666; font-size: 12px; }
</style>
</head>
<body>
<h1>DATAFLOW Pipeline Audit</h1>
<p class="muted">Generated at: """
        + _html_escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        + """</p>
"""
    )

    html_parts.append('<div class="section">')
    html_parts.append("<h2>Summary Counts</h2>")
    for station, rows in sorted(summary_by_station.items()):
        html_parts.append(f"<h3>Station {_html_escape(station)}</h3>")
        html_parts.append("<table><thead><tr><th>Flag</th><th>Count</th></tr></thead><tbody>")
        for row in rows:
            html_parts.append(
                f"<tr><td>{_html_escape(row.get('flag',''))}</td><td>{_html_escape(row.get('count',''))}</td></tr>"
            )
        html_parts.append("</tbody></table>")
    html_parts.append("</div>")

    def render_table(title: str, rows: List[Dict[str, str]], columns: List[str]) -> None:
        html_parts.append('<div class="section">')
        html_parts.append(f"<h2>{_html_escape(title)}</h2>")
        if not rows:
            html_parts.append('<p class="muted">No rows.</p></div>')
            return
        html_parts.append("<table><thead><tr>")
        for col in columns:
            html_parts.append(f"<th>{_html_escape(col)}</th>")
        html_parts.append("</tr></thead><tbody>")
        for row in rows:
            html_parts.append("<tr>")
            for col in columns:
                value = row.get(col, "")
                if col == "stage":
                    html_parts.append(f"<td>{stage_badge(value)}</td>")
                else:
                    html_parts.append(f"<td>{_html_escape(value)}</td>")
            html_parts.append("</tr>")
        html_parts.append("</tbody></table></div>")

    render_table(
        "Anomalies",
        anomalies,
        [
            "station",
            "basename",
            "issue",
            "details",
            "stage",
            "last_seen",
            "age_hours",
            "reason",
            "last_seen_source",
            "log_hint",
        ],
    )
    render_table(
        "Stale Basenames",
        stale_rows,
        ["station", "basename", "stage", "last_seen", "age_hours", "reason", "last_seen_source", "log_hint"],
    )

    if basenames:
        sortable = []
        for row in basenames:
            try:
                age = float(row.get("age_hours", ""))
            except ValueError:
                age = -1.0
            sortable.append((age, row))
        sortable.sort(key=lambda item: item[0], reverse=True)
        limited = [row for _age, row in sortable[:max_rows]]
        html_parts.append('<div class="section">')
        html_parts.append(f"<h2>Basename States (top {len(limited)} by age)</h2>")
        html_parts.append("<table><thead><tr>")
        base_columns = ["station", "basename", "stage", "last_seen", "age_hours", "reason", "last_seen_source"]
        flag_columns = [
            flag
            for flag, _label in STAGE_RANK
            if flag in KNOWN_FLAGS and any(item.get(flag, "") for item in limited)
        ]
        for col in base_columns + flag_columns:
            html_parts.append(f"<th>{_html_escape(col)}</th>")
        html_parts.append("</tr></thead><tbody>")
        for row in limited:
            html_parts.append("<tr>")
            for col in base_columns + flag_columns:
                value = row.get(col, "")
                if col == "stage":
                    html_parts.append(f"<td>{stage_badge(value)}</td>")
                else:
                    html_parts.append(f"<td>{_html_escape(value)}</td>")
            html_parts.append("</tr>")
        html_parts.append("</tbody></table>")
        if len(basenames) > max_rows:
            html_parts.append(
                f'<p class="muted">Showing {max_rows} of {len(basenames)} basenames. Increase with --html-max-rows.</p>'
            )
        html_parts.append("</div>")

    html_parts.append("</body></html>")
    (output_dir / "report.html").write_text("\n".join(html_parts), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit DATAFLOW pipeline lists/queues and map basenames to pipeline states."
    )
    parser.add_argument(
        "--stations",
        default="all",
        help="Comma-separated station IDs (0-4) or 'all'. Default: all.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Directory to write outputs. Default: OUTPUT_FILES/<timestamp> under this script.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Only write summary and inventory (skip full basename_state.csv).",
    )
    parser.add_argument(
        "--stale-hours",
        type=float,
        default=STALE_HOURS_DEFAULT,
        help=f"Hours without activity before a basename is marked stale (default {STALE_HOURS_DEFAULT}).",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Skip generating the HTML report.",
    )
    parser.add_argument(
        "--html-max-rows",
        type=int,
        default=3000,
        help="Max rows in the HTML basename table (default 3000).",
    )
    parser.add_argument(
        "--scan-logs",
        action="store_true",
        help="Scan cron logs for basename mentions (can be slow).",
    )
    parser.add_argument(
        "--log-roots",
        default=str(REPO_ROOT / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME" / "CRON_LOGS" / "MAIN_ANALYSIS"),
        help="Comma-separated log roots to scan when --scan-logs is enabled.",
    )
    args = parser.parse_args(argv)

    try:
        stations = parse_station_list(args.stations)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not stations:
        print("No stations found.", file=sys.stderr)
        return 1

    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else Path(__file__).resolve().parent / "OUTPUT_FILES" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    inventory_rows: List[Dict[str, str]] = []
    summary_rows: List[Dict[str, str]] = []
    anomaly_rows: List[Dict[str, str]] = []
    basename_rows: List[Dict[str, str]] = []
    stale_rows: List[Dict[str, str]] = []

    all_flags: List[str] = list(KNOWN_FLAGS)

    for station in stations:
        states, last_seen, last_seen_source, inventory = collect_station_states(station)
        station_flags = active_flags_for_station(station)
        if station == STATION_ZERO:
            for flags in states.values():
                for disabled_flag in STATION_ZERO_DISABLED_FLAGS:
                    flags.pop(disabled_flag, None)
        inventory_rows.extend(inventory)
        counts = summarize_counts(states)
        for flag in station_flags:
            summary_rows.append(
                {"station": station, "flag": flag, "count": str(counts.get(flag, 0))}
            )

        anomalies = detect_anomalies(
            states,
            last_seen,
            last_seen_source,
            now=now,
            stale_hours=args.stale_hours,
        )
        for entry in anomalies:
            row = {"station": station, **entry}
            anomaly_rows.append(row)

        if not args.summary_only:
            for basename, flags in sorted(states.items()):
                row: Dict[str, str] = {"station": station, "basename": basename}
                for flag in all_flags:
                    row[flag] = "1" if flags.get(flag) else ""
                ts = last_seen.get(basename)
                if ts is not None:
                    age = (now - ts).total_seconds() / 3600.0
                    row["last_seen"] = format_datetime(ts)
                    row["age_hours"] = f"{age:.2f}"
                else:
                    row["last_seen"] = ""
                    row["age_hours"] = ""
                row["stage"] = determine_stage(flags)
                row["reason"] = build_reason(flags)
                row["last_seen_source"] = last_seen_source.get(basename, "")
                basename_rows.append(row)

        for basename, flags in states.items():
            ts = last_seen.get(basename)
            if ts is None or flags.get("processed_final"):
                continue
            age = (now - ts).total_seconds() / 3600.0
            if age < args.stale_hours:
                continue
            stale_rows.append(
                {
                    "station": station,
                    "basename": basename,
                    "stage": determine_stage(flags),
                    "last_seen": format_datetime(ts),
                    "age_hours": f"{age:.2f}",
                    "reason": build_reason(flags),
                    "last_seen_source": last_seen_source.get(basename, ""),
                }
            )

    log_hints: Dict[str, str] = {}
    if args.scan_logs:
        roots = [Path(p.strip()) for p in args.log_roots.split(",") if p.strip()]
        target_basenames = {row.get("basename", "") for row in anomaly_rows + stale_rows if row.get("basename")}
        log_hints = scan_logs_for_basenames(target_basenames, roots)

    for row in anomaly_rows:
        row["log_hint"] = log_hints.get(row.get("basename", ""), "")
    for row in stale_rows:
        row["log_hint"] = log_hints.get(row.get("basename", ""), "")

    inventory_fields = ["station", "kind", "path", "exists", "count", "note", "source"]
    write_csv(output_dir / "inventory_paths.csv", inventory_rows, inventory_fields)

    summary_fields = ["station", "flag", "count"]
    write_csv(output_dir / "summary_counts.csv", summary_rows, summary_fields)

    anomaly_fields = [
        "station",
        "basename",
        "issue",
        "details",
        "stage",
        "last_seen",
        "age_hours",
        "reason",
        "last_seen_source",
        "log_hint",
    ]
    write_csv(output_dir / "anomalies.csv", anomaly_rows, anomaly_fields)

    if not args.summary_only:
        basename_fields = [
            "station",
            "basename",
            *all_flags,
            "stage",
            "last_seen",
            "age_hours",
            "reason",
            "last_seen_source",
        ]
        write_csv(output_dir / "basename_state.csv", basename_rows, basename_fields)

    stale_fields = ["station", "basename", "stage", "last_seen", "age_hours", "reason", "last_seen_source", "log_hint"]
    write_csv(output_dir / "stale.csv", stale_rows, stale_fields)

    metadata = {
        "generated_at": timestamp,
        "stations": stations,
        "summary_only": args.summary_only,
        "output_dir": str(output_dir),
        "stale_hours": args.stale_hours,
    }
    (output_dir / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    if not args.no_html:
        write_html_report(
            output_dir,
            summary_rows=summary_rows,
            anomalies=anomaly_rows,
            stale_rows=stale_rows,
            basenames=basename_rows,
            max_rows=args.html_max_rows,
        )

    print(f"Wrote audit outputs to: {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
