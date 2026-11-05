#!/usr/bin/env python3
"""Audit and conservatively reconcile Stage 0 through the Parquet Lake.

The Parquet Lake is the only final-completion authority.  The script always
writes a station CSV snapshot.  Mutations require ``--apply`` and are limited
to configured date ranges unless ``--all-dates`` is explicitly supplied.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import gzip
import json
import os
import re
import shutil
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[5]
PIPELINE_LOCK_ROOT = Path(
    os.environ.get(
        "FILE_FLOW_TRACKER_PIPELINE_LOCK_ROOT",
        REPO_ROOT / "CONTEXTUAL" / "OPERATIONS" / "OPERATIONS_RUNTIME" / "LOCKS" / "cron",
    )
)
STATIONS_ROOT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
RUNTIME_ROOT = REPO_ROOT / "CONTEXTUAL" / "OPERATIONS" / "OPERATIONS_RUNTIME" / "FILE_FLOW_TRACKER"
PROCESSED_ROOT = (
    REPO_ROOT
    / "CONTEXTUAL" / "OPERATIONS"
    / "OPERATIONS_SCRIPTS"
    / "DATA_MAINTENANCE"
    / "UPDATE_EXECUTION_CSVS"
    / "OUTPUT_FILES"
)
ACTIVE_REPROCESSING = (
    REPO_ROOT
    / "CONTEXTUAL" / "OPERATIONS"
    / "OPERATIONS_RUNTIME"
    / "STATE"
    / "REPROCESS_BASENAMES"
    / "active_reprocessing.csv"
)
BASE_RE = re.compile(r"(mi0[0-4]\d{11})", re.IGNORECASE)
QUEUE_NAMES = (
    "UNPROCESSED_DIRECTORY",
    "PROCESSING_DIRECTORY",
    "COMPLETED_DIRECTORY",
    "ERROR_DIRECTORY",
    "OUT_OF_DATE_DIRECTORY",
)
TRACKING_FIELDS = (
    "observed_at_utc",
    "station",
    "filename_base",
    "event_time_utc",
    "in_selected_range",
    "lifecycle_state",
    "highest_task_reached",
    "archive_present",
    "archive_valid",
    "metadata_tasks",
    "metadata_file_count",
    "newest_metadata_timestamp_utc",
    "stage0_present",
    "active_reprocessing",
    "task_0_state",
    "task_1_state",
    "task_2_state",
    "task_3_state",
    "task_4_state",
    "task_5_state",
    "pipeline_consistent",
    "needs_reprocessing",
    "anomaly_codes",
    "recommended_action",
    "artifact_count",
    "newest_artifact_mtime_utc",
    "current_paths",
)


@dataclass(frozen=True)
class Artifact:
    path: Path
    kind: str
    task: int | None
    queue: str = ""
    mtime: float = 0.0


@dataclass
class FileObservation:
    station: int
    base: str
    artifacts: list[Artifact] = field(default_factory=list)
    metadata_paths: set[Path] = field(default_factory=set)
    metadata_tasks: set[int] = field(default_factory=set)
    newest_metadata_timestamp: float = 0.0
    archive_present: bool = False
    archive_valid: bool = False
    active_reprocessing: bool = False
    in_selected_range: bool = False
    event_time: datetime | None = None
    action: str = "none"
    anomalies: list[str] = field(default_factory=list)


def basename_from_text(value: str) -> str | None:
    match = BASE_RE.search(value)
    return match.group(1).lower() if match else None


def event_time_from_base(base: str) -> datetime | None:
    """Parse ``miSSYYDDDhhmmss`` into a naive UTC datetime."""
    try:
        payload = base[4:]
        return datetime.strptime(payload, "%y%j%H%M%S")
    except (ValueError, IndexError):
        return None


def is_valid_parquet(path: Path) -> bool:
    try:
        if path.stat().st_size < 8:
            return False
        with path.open("rb") as handle:
            return handle.read(4) == b"PAR1" and (
                handle.seek(-4, os.SEEK_END) is not None
                and handle.read(4) == b"PAR1"
            )
    except OSError:
        return False


def iter_regular_files(directory: Path) -> Iterable[Path]:
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_file(follow_symlinks=False):
                    yield Path(entry.path)
    except (FileNotFoundError, PermissionError):
        return


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return list(reader.fieldnames or []), list(reader)
    except (OSError, csv.Error, UnicodeError):
        return [], []



def iter_csv_first_column(path: Path) -> Iterable[str]:
    """Stream only the basename column; wide metadata rows stay unallocated."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            for row in reader:
                if row:
                    yield row[0]
    except (OSError, csv.Error, UnicodeError):
        return



def parse_metadata_timestamp(value: str) -> float:
    text = (value or "").strip()
    if not text:
        return 0.0
    for fmt in ("%Y-%m-%d_%H.%M.%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.timestamp()
    except ValueError:
        return 0.0


def iter_csv_first_two(path: Path) -> Iterable[tuple[str, str]]:
    """Stream basename and execution timestamp without materializing wide rows."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            for row in reader:
                if row:
                    yield row[0], row[1] if len(row) > 1 else ""
    except (OSError, csv.Error, UnicodeError):
        return
def atomic_write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def metadata_csvs(station_root: Path) -> Iterable[tuple[int, Path]]:
    step = station_root / "STAGE_1" / "EVENT_DATA" / "STEP_1"
    products = station_root / "STAGE_1_PRODUCTS" / "EVENT_DATA" / "METADATA"
    for task in range(6):
        for root in (step / f"TASK_{task}" / "METADATA", products / f"TASK_{task}"):
            if root.is_dir():
                for path in root.glob("*.csv"):
                    yield task, path


def guard_csvs(station_root: Path) -> tuple[Path, ...]:
    return (
        station_root / "STAGE_0" / "NEW_FILES" / "METADATA" / "raw_files_brought.csv",
        station_root
        / "STAGE_0"
        / "REPROCESSING"
        / "STEP_1"
        / "METADATA"
        / "hld_files_brought.csv",
        station_root
        / "STAGE_0"
        / "REPROCESSING"
        / "STEP_2"
        / "METADATA"
        / "dat_files_unpacked.csv",
    )


def load_active_bases(path: Path = ACTIVE_REPROCESSING) -> set[str]:
    _, rows = read_csv(path)
    result: set[str] = set()
    for row in rows:
        for value in row.values():
            base = basename_from_text(value or "")
            if base:
                result.add(base)
    return result


def load_previous_bases(path: Path) -> set[str]:
    _, rows = read_csv(path)
    return {
        base
        for row in rows
        if (base := basename_from_text(row.get("filename_base", "")))
    }


def scan_station(
    station: int,
    *,
    stations_root: Path = STATIONS_ROOT,
    runtime_root: Path = RUNTIME_ROOT,
    active_bases: set[str] | None = None,
) -> tuple[dict[str, FileObservation], dict[Path, tuple[list[str], list[dict[str, str]]]]]:
    station_root = stations_root / f"MINGO{station:02d}"
    observations: dict[str, FileObservation] = {}

    def get(base: str) -> FileObservation:
        return observations.setdefault(base, FileObservation(station=station, base=base))

    previous = runtime_root / f"MINGO{station:02d}_file_flow_latest.csv"
    for base in load_previous_bases(previous):
        get(base)

    stage0 = station_root / "STAGE_0_TO_1"
    for path in iter_regular_files(stage0):
        if base := basename_from_text(path.name):
            get(base).artifacts.append(
                Artifact(path, "stage0", None, mtime=path.stat().st_mtime)
            )

    step = station_root / "STAGE_1" / "EVENT_DATA" / "STEP_1"
    for task in range(6):
        task_root = step / f"TASK_{task}"
        for queue in QUEUE_NAMES:
            for path in iter_regular_files(task_root / "INPUT_FILES" / queue):
                if base := basename_from_text(path.name):
                    get(base).artifacts.append(
                        Artifact(path, "input", task, queue, path.stat().st_mtime)
                    )
        for path in iter_regular_files(task_root / "OUTPUT_FILES"):
            if base := basename_from_text(path.name):
                get(base).artifacts.append(
                    Artifact(path, "output", task, mtime=path.stat().st_mtime)
                )

    lake = station_root / "STAGE_1_PRODUCTS" / "EVENT_DATA" / "PARQUET_LAKE"
    for path in iter_regular_files(lake):
        if base := basename_from_text(path.name):
            obs = get(base)
            valid = is_valid_parquet(path)
            obs.archive_present = True
            obs.archive_valid = obs.archive_valid or valid
            obs.artifacts.append(
                Artifact(
                    path,
                    "lake_valid" if valid else "lake_invalid",
                    5,
                    mtime=path.stat().st_mtime,
                )
            )

    for task, path in metadata_csvs(station_root):
        for value, timestamp in iter_csv_first_two(path):
            if base := basename_from_text(value):
                obs = get(base)
                obs.metadata_paths.add(path)
                obs.metadata_tasks.add(task)
                obs.newest_metadata_timestamp = max(
                    obs.newest_metadata_timestamp, parse_metadata_timestamp(timestamp)
                )

    for path in guard_csvs(station_root):
        for value in iter_csv_first_column(path):
            if base := basename_from_text(value):
                get(base).metadata_paths.add(path)
    active = active_bases if active_bases is not None else load_active_bases()
    for base in active:
        if base in observations:
            observations[base].active_reprocessing = True
    return observations, {}


def within_ranges(value: datetime | None, ranges: Sequence[tuple[datetime | None, datetime | None]]) -> bool:
    if value is None:
        return False
    if not ranges:
        return False
    return any(
        (start is None or value >= start) and (end is None or value <= end)
        for start, end in ranges
    )


def queue_states(obs: FileObservation) -> dict[int, str]:
    result: dict[int, list[str]] = defaultdict(list)
    order = {name: index for index, name in enumerate(QUEUE_NAMES)}
    for artifact in obs.artifacts:
        if artifact.kind == "input" and artifact.task is not None:
            result[artifact.task].append(artifact.queue.removesuffix("_DIRECTORY").lower())
        elif artifact.kind == "output" and artifact.task is not None:
            result[artifact.task].append("output")
    return {
        task: "|".join(sorted(set(states), key=lambda item: order.get(item.upper() + "_DIRECTORY", 99)))
        for task, states in result.items()
    }


def classify(
    obs: FileObservation,
    now: float,
    stale_seconds: float,
    *,
    station_pipeline_busy: bool = False,
) -> tuple[str, str, int]:
    queues = queue_states(obs)
    highest = max(
        [artifact.task for artifact in obs.artifacts if artifact.task is not None] + [-1]
    )
    if obs.archive_valid:
        if 5 not in obs.metadata_tasks:
            obs.anomalies.append("archive_without_task5_metadata")
        return "archived", "none", highest
    if obs.archive_present:
        obs.anomalies.append("invalid_parquet_archive")
        return "archive_invalid", "quarantine_invalid_archive_and_resume", highest
    processing = [
        artifact
        for artifact in obs.artifacts
        if artifact.kind == "input" and artifact.queue == "PROCESSING_DIRECTORY"
    ]
    if obs.active_reprocessing:
        return "active_reprocessing", "wait", highest
    if processing and station_pipeline_busy:
        return f"processing_task_{max(a.task or 0 for a in processing)}", "wait", highest
    if processing and any(now - artifact.mtime < stale_seconds for artifact in processing):
        return f"processing_task_{max(a.task or 0 for a in processing)}", "wait", highest
    if processing:
        obs.anomalies.append("stale_processing_file")
        return f"stale_processing_task_{max(a.task or 0 for a in processing)}", "requeue_stale_processing", highest
    errors = [
        artifact for artifact in obs.artifacts
        if artifact.kind == "input" and artifact.queue in {"ERROR_DIRECTORY", "OUT_OF_DATE_DIRECTORY"}
    ]
    if errors:
        obs.anomalies.append("manual_review_queue")
        return f"manual_review_task_{max(a.task or 0 for a in errors)}", "manual_review", highest
    unprocessed = [
        artifact for artifact in obs.artifacts
        if artifact.kind == "input" and artifact.queue == "UNPROCESSED_DIRECTORY"
    ]
    if unprocessed:
        return f"queued_task_{max(a.task or 0 for a in unprocessed)}", "wait", highest
    if any(artifact.kind == "stage0" for artifact in obs.artifacts):
        return "stage0_ready", "wait", highest
    recoverable = [
        artifact for artifact in obs.artifacts
        if artifact.kind == "output"
        or (artifact.kind == "input" and artifact.queue == "COMPLETED_DIRECTORY")
    ]
    if recoverable and any(now - artifact.mtime < stale_seconds for artifact in recoverable):
        return f"in_flight_after_task_{highest}", "wait", highest
    if recoverable:
        obs.anomalies.append("stranded_intermediate")
        return "stranded_intermediate", "resume_from_highest_intermediate", highest
    if obs.metadata_paths:
        if (
            obs.newest_metadata_timestamp
            and now - obs.newest_metadata_timestamp < stale_seconds
        ):
            return "recent_metadata_pending_archive", "wait", highest
        obs.anomalies.append("processing_metadata_without_archive")
        obs.anomalies.append("metadata_or_guard_only")
        return "metadata_only_missing_archive", "clear_metadata_and_acquisition_guards", highest
    if obs.in_selected_range:
        return "awaiting_stage0_refetch", "wait", highest
    return "unknown", "none", highest


def choose_resume_artifact(obs: FileObservation) -> tuple[Artifact, int] | None:
    candidates: list[tuple[int, int, float, Artifact, int]] = []
    for artifact in obs.artifacts:
        if artifact.kind == "input" and artifact.queue in {
            "PROCESSING_DIRECTORY",
            "COMPLETED_DIRECTORY",
            "ERROR_DIRECTORY",
            "OUT_OF_DATE_DIRECTORY",
        }:
            target = int(artifact.task or 0)
            candidates.append((target, 2, artifact.mtime, artifact, target))
        elif artifact.kind == "output" and artifact.task is not None and artifact.task < 5:
            target = artifact.task + 1
            candidates.append((target, 1, artifact.mtime, artifact, target))
    if not candidates:
        return None
    _, _, _, artifact, target = max(candidates)
    return artifact, target


def append_audit(runtime_root: Path, rows: list[dict[str, object]]) -> None:
    """Append recoverable removed rows without rereading the historical ledger."""
    if not rows:
        return
    path = runtime_root / "removed_metadata_rows.csv.gz"
    fields = ("removed_at_utc", "station", "filename_base", "reason", "csv_path", "row_json")
    write_header = not path.exists() or path.stat().st_size == 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "at", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)



def json_safe_csv_row(row: dict[object, object]) -> str:
    """Serialize malformed rows too, including DictReader's None key."""
    normalized: dict[str, object] = {}
    for key, value in row.items():
        safe_key = "__extra_fields__" if key is None else str(key)
        if safe_key in normalized:
            safe_key = f"{safe_key}_{len(normalized)}"
        normalized[safe_key] = value
    return json.dumps(normalized, sort_keys=True)

def schedule_prune(
    pending: dict[Path, dict[str, tuple[int, str]]],
    path: Path,
    base: str,
    station: int,
    reason: str,
) -> None:
    pending.setdefault(path, {})[base] = (station, reason)


def apply_prune_batch(
    pending: dict[Path, dict[str, tuple[int, str]]],
    runtime_root: Path,
) -> int:
    """Remove requested basenames with one locked, recoverable rewrite per CSV."""
    removed = 0
    stamp = datetime.now(timezone.utc).isoformat()
    for path, requests in sorted(pending.items(), key=lambda item: str(item[0])):
        if not path.exists():
            continue
        lock_path = Path(f"{path}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+") as csv_lock:
            fcntl.flock(csv_lock, fcntl.LOCK_EX)
            header, rows = read_csv(path)
            if not header:
                continue
            key = "filename_base" if "filename_base" in header else header[0]
            kept: list[dict[str, str]] = []
            path_audit_rows: list[dict[str, object]] = []
            for row in rows:
                base = basename_from_text(row.get(key, ""))
                request = requests.get(base or "")
                if request is None:
                    kept.append(row)
                    continue
                station, reason = request
                removed += 1
                path_audit_rows.append(
                    {
                        "removed_at_utc": stamp,
                        "station": f"MINGO{station:02d}",
                        "filename_base": base,
                        "reason": reason,
                        "csv_path": str(path),
                        "row_json": json_safe_csv_row(row),
                    }
                )
            if path_audit_rows:
                # Journal first: interruption may over-report a still-present
                # row, but can never leave a removed row without recovery data.
                append_audit(runtime_root, path_audit_rows)
                atomic_write_csv(path, header, kept)
    return removed


def metadata_paths_from_task(station_root: Path, first_task: int) -> Iterable[Path]:
    for task, path in metadata_csvs(station_root):
        if task >= first_task:
            yield path


def repair_observation(
    obs: FileObservation,
    *,
    stations_root: Path,
    runtime_root: Path,
    retry_errors: bool,
    pending_prunes: dict[Path, dict[str, tuple[int, str]]],
) -> list[str]:
    station_root = stations_root / f"MINGO{obs.station:02d}"
    actions: list[str] = []
    if obs.archive_present and not obs.archive_valid:
        quarantine = runtime_root / "QUARANTINE" / f"MINGO{obs.station:02d}"
        quarantine.mkdir(parents=True, exist_ok=True)
        for artifact in obs.artifacts:
            if artifact.kind == "lake_invalid" and artifact.path.exists():
                destination = quarantine / artifact.path.name
                if destination.exists():
                    destination = quarantine / f"{artifact.path.stem}_{int(artifact.mtime)}{artifact.path.suffix}"
                shutil.move(str(artifact.path), destination)
                actions.append(f"quarantined:{artifact.path}")

    if obs.active_reprocessing or obs.archive_valid:
        return actions

    manual = [
        artifact for artifact in obs.artifacts
        if artifact.kind == "input" and artifact.queue in {"ERROR_DIRECTORY", "OUT_OF_DATE_DIRECTORY"}
    ]
    if manual and not retry_errors:
        return actions

    chosen = choose_resume_artifact(obs)
    if chosen:
        artifact, target_task = chosen
        destination_dir = (
            station_root
            / "STAGE_1"
            / "EVENT_DATA"
            / "STEP_1"
            / f"TASK_{target_task}"
            / "INPUT_FILES"
            / "UNPROCESSED_DIRECTORY"
        )
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / artifact.path.name
        if artifact.path.exists() and artifact.path != destination and not destination.exists():
            shutil.move(str(artifact.path), destination)
            actions.append(f"requeued_task_{target_task}:{artifact.path}")
        elif artifact.path.exists() and artifact.path != destination and destination.exists():
            quarantine = runtime_root / "DUPLICATE_INTERMEDIATES" / f"MINGO{obs.station:02d}"
            quarantine.mkdir(parents=True, exist_ok=True)
            duplicate = quarantine / f"{artifact.path.parent.name}_{artifact.path.name}"
            if duplicate.exists():
                duplicate = quarantine / f"{artifact.path.stem}_{int(artifact.mtime)}{artifact.path.suffix}"
            shutil.move(str(artifact.path), duplicate)
            actions.append(f"quarantined_duplicate:{artifact.path}")
        for path in metadata_paths_from_task(station_root, target_task):
            schedule_prune(
                pending_prunes,
                path,
                obs.base,
                obs.station,
                f"requeued_at_task_{target_task}_because_archive_missing",
            )
        actions.append(f"metadata_prune_scheduled_from_task_{target_task}")
        return actions

    # No recoverable payload exists. Remove every metadata/retrieval guard so
    # normal acquisition or selected reprocessing may obtain the source again.
    paths = [path for _, path in metadata_csvs(station_root)]
    paths.extend(guard_csvs(station_root))
    for path in paths:
        schedule_prune(
            pending_prunes,
            path,
            obs.base,
            obs.station,
            "no_archive_and_no_recoverable_intermediate",
        )
    actions.append("metadata_and_acquisition_guard_prune_scheduled")
    return actions


def rebuild_processed_list(station: int, observations: dict[str, FileObservation], root: Path) -> Path:
    """Write the legacy consumer format, sourced only from valid lake files."""
    path = root / f"MINGO{station:02d}_processed_basenames.csv"
    rows = []
    for base, obs in sorted(observations.items()):
        valid = [artifact for artifact in obs.artifacts if artifact.kind == "lake_valid"]
        if not valid:
            continue
        archive = max(valid, key=lambda artifact: artifact.mtime)
        rows.append(
            {
                "basename": base,
                "execution_timestamp": datetime.fromtimestamp(
                    archive.mtime, timezone.utc
                ).isoformat(),
                "source_csv": str(archive.path),
            }
        )
    atomic_write_csv(
        path, ("basename", "execution_timestamp", "source_csv"), rows
    )
    return path


def tracking_row(
    obs: FileObservation,
    *,
    observed_at: str,
    state: str,
    recommended: str,
    highest: int,
) -> dict[str, object]:
    states = queue_states(obs)
    newest = max((artifact.mtime for artifact in obs.artifacts), default=0.0)
    consistent = (
        obs.archive_valid
        or state.startswith(("processing_", "queued_", "stage0_", "active_", "in_flight_", "awaiting_"))
        or state == "manual_review"
    )
    return {
        "observed_at_utc": observed_at,
        "station": f"MINGO{obs.station:02d}",
        "filename_base": obs.base,
        "event_time_utc": obs.event_time.isoformat() if obs.event_time else "",
        "in_selected_range": int(obs.in_selected_range),
        "lifecycle_state": state,
        "highest_task_reached": highest,
        "archive_present": int(obs.archive_present),
        "archive_valid": int(obs.archive_valid),
        "metadata_tasks": "|".join(map(str, sorted(obs.metadata_tasks))),
        "metadata_file_count": len(obs.metadata_paths),
        "newest_metadata_timestamp_utc": (
            datetime.fromtimestamp(obs.newest_metadata_timestamp, timezone.utc).isoformat()
            if obs.newest_metadata_timestamp
            else ""
        ),
        "stage0_present": int(any(a.kind == "stage0" for a in obs.artifacts)),
        "active_reprocessing": int(obs.active_reprocessing),
        **{f"task_{task}_state": states.get(task, "") for task in range(6)},
        "pipeline_consistent": int(consistent),
        "needs_reprocessing": int(
            not obs.archive_valid and recommended not in {"none", "wait", "manual_review"}
        ),
        "anomaly_codes": "|".join(sorted(set(obs.anomalies))),
        "recommended_action": recommended,
        "artifact_count": len(obs.artifacts),
        "newest_artifact_mtime_utc": (
            datetime.fromtimestamp(newest, timezone.utc).isoformat() if newest else ""
        ),
        "current_paths": "|".join(sorted(str(a.path) for a in obs.artifacts)),
    }


def load_selection_ranges(stations: Sequence[int]) -> dict[int, Sequence[tuple[datetime | None, datetime | None]]]:
    sys.path.insert(0, str(REPO_ROOT))
    from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.selection_config import (
        effective_date_ranges_for_station,
        load_master_selection,
    )

    selection = load_master_selection()
    return {
        station: effective_date_ranges_for_station(station, selection)
        for station in stations
    }


def home_usage_percent(path: Path) -> float:
    usage = shutil.disk_usage(path)
    return 100.0 * usage.used / usage.total


def run(
    *,
    stations: Sequence[int],
    apply: bool = False,
    all_dates: bool = False,
    stale_hours: float = 6.0,
    retry_errors: bool = False,
    max_repair_disk_percent: float = 94.0,
    stations_root: Path = STATIONS_ROOT,
    runtime_root: Path = RUNTIME_ROOT,
    processed_root: Path = PROCESSED_ROOT,
    selection_ranges: dict[int, Sequence[tuple[datetime | None, datetime | None]]] | None = None,
    disk_check_path: Path = Path("/home"),
    processed_lists_only: bool = False,
) -> dict[str, int]:
    runtime_root.mkdir(parents=True, exist_ok=True)
    lock_path = runtime_root / "file_flow_tracker.lock"
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("another file_flow_tracker instance is already running")

        ranges_by_station = selection_ranges
        selection_ok = True
        if ranges_by_station is None:
            try:
                ranges_by_station = load_selection_ranges(stations)
            except Exception as exc:
                selection_ok = False
                ranges_by_station = {station: () for station in stations}
                print(f"WARNING: selection config could not be loaded: {exc}", file=sys.stderr)

        repair_disk_ok = home_usage_percent(disk_check_path) < max_repair_disk_percent
        observed_at = datetime.now(timezone.utc).isoformat()
        active = load_active_bases()
        summary_rows: list[dict[str, object]] = []
        action_rows: list[dict[str, object]] = []
        totals = {"files": 0, "archived": 0, "anomalies": 0, "actions": 0}

        for station in stations:
            station_lock_path = PIPELINE_LOCK_ROOT / f"guide_raw_to_corrected_s{station}.lock"
            station_lock_path.parent.mkdir(parents=True, exist_ok=True)
            station_lock = station_lock_path.open("a+")
            try:
                fcntl.flock(station_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                station_pipeline_busy = False
            except BlockingIOError:
                station_pipeline_busy = True
                station_lock.close()
            observations, _ = scan_station(
                station,
                stations_root=stations_root,
                runtime_root=runtime_root,
                active_bases=active,
            )
            rows: list[dict[str, object]] = []
            station_actions = 0
            pending_prunes: dict[Path, dict[str, tuple[int, str]]] = {}
            ranges = ranges_by_station.get(station, ()) if ranges_by_station else ()
            for base, obs in sorted(observations.items()):
                obs.event_time = event_time_from_base(base)
                obs.in_selected_range = all_dates or within_ranges(obs.event_time, ranges)
                state, recommended, highest = classify(
                    obs,
                    datetime.now(timezone.utc).timestamp(),
                    stale_hours * 3600.0,
                    station_pipeline_busy=station_pipeline_busy,
                )
                may_repair = (
                    apply
                    and not processed_lists_only
                    and not station_pipeline_busy
                    and repair_disk_ok
                    and (all_dates or selection_ok)
                    and obs.in_selected_range
                    and recommended not in {"none", "wait"}
                    and (recommended != "manual_review" or retry_errors)
                )
                if may_repair:
                    performed = repair_observation(
                        obs,
                        stations_root=stations_root,
                        runtime_root=runtime_root,
                        retry_errors=retry_errors,
                        pending_prunes=pending_prunes,
                    )
                    obs.action = ";".join(performed) if performed else "no_safe_mutation"
                    for action in performed:
                        action_rows.append(
                            {
                                "observed_at_utc": observed_at,
                                "station": f"MINGO{station:02d}",
                                "filename_base": base,
                                "action": action,
                            }
                        )
                    station_actions += len(performed)
                elif apply and recommended not in {"none", "wait", "manual_review"}:
                    if not repair_disk_ok:
                        obs.action = "deferred_high_disk_usage"
                    elif not obs.in_selected_range:
                        obs.action = "deferred_outside_selected_ranges"
                    elif not selection_ok:
                        obs.action = "deferred_selection_config_unavailable"
                rows.append(
                    tracking_row(
                        obs,
                        observed_at=observed_at,
                        state=state,
                        recommended=recommended,
                        highest=highest,
                    )
                )
                totals["files"] += 1
                totals["archived"] += int(obs.archive_valid)
                totals["anomalies"] += int(bool(obs.anomalies))

            apply_prune_batch(pending_prunes, runtime_root)
            atomic_write_csv(
                runtime_root / f"MINGO{station:02d}_file_flow_latest.csv",
                TRACKING_FIELDS,
                rows,
            )
            if apply or processed_lists_only:
                rebuild_processed_list(station, observations, processed_root)
            totals["actions"] += station_actions
            summary_rows.append(
                {
                    "observed_at_utc": observed_at,
                    "station": f"MINGO{station:02d}",
                    "tracked_files": len(rows),
                    "valid_archives": sum(int(row["archive_valid"]) for row in rows),
                    "anomalous_files": sum(bool(row["anomaly_codes"]) for row in rows),
                    "actions": station_actions,
                    "repair_enabled": int(apply),
                    "repair_disk_ok": int(repair_disk_ok),
                }
            )
            if not station_pipeline_busy:
                fcntl.flock(station_lock, fcntl.LOCK_UN)
                station_lock.close()

        atomic_write_csv(
            runtime_root / "summary_latest.csv",
            (
                "observed_at_utc",
                "station",
                "tracked_files",
                "valid_archives",
                "anomalous_files",
                "actions",
                "repair_enabled",
                "repair_disk_ok",
            ),
            summary_rows,
        )
        atomic_write_csv(
            runtime_root / "actions_latest.csv",
            ("observed_at_utc", "station", "filename_base", "action"),
            action_rows,
        )
        return totals


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="perform conservative repairs")
    parser.add_argument(
        "--processed-lists-only",
        action="store_true",
        help="only refresh lake-authoritative legacy processed lists",
    )
    parser.add_argument("--stations", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    parser.add_argument("--all-dates", action="store_true", help="allow repairs outside selected ranges")
    parser.add_argument("--stale-hours", type=float, default=6.0)
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--max-repair-disk-percent", type=float, default=94.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        totals = run(
            stations=args.stations,
            apply=args.apply,
            all_dates=args.all_dates,
            stale_hours=args.stale_hours,
            retry_errors=args.retry_errors,
            max_repair_disk_percent=args.max_repair_disk_percent,
            processed_lists_only=args.processed_lists_only,
        )
    except RuntimeError as exc:
        if "another file_flow_tracker instance" in str(exc):
            print(f"file-flow tracker: skipped ({exc})")
            return 0
        raise
    print(
        "file-flow tracker: "
        + ", ".join(f"{key}={value}" for key, value in totals.items())
        + (
            " (repairs enabled)"
            if args.apply
            else " (processed lists only)"
            if args.processed_lists_only
            else " (report only)"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
