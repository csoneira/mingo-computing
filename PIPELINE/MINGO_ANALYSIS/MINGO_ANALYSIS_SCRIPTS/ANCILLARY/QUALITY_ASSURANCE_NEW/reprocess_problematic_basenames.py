#!/usr/bin/env python3
"""Safely clear QA-failed basenames from their first failed task onward.

The starting task input is preserved and returned to its UNPROCESSED directory.
Everything derived from that input in the starting task through Task 5 is
removed, including matching metadata rows and filename-base indexes.

The default is a dry run. Pass --apply to perform the planned changes.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import fcntl
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Iterable


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[5]
QA_ROOT = SCRIPT_PATH.parent
DEFAULT_MANIFEST = QA_ROOT / "PROBLEMATIC_BASENAMES" / "problematic_basenames.csv"
STATIONS_ROOT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
RUNTIME_ROOT = REPO_ROOT / "CONTEXTUAL" / "OPERATIONS" / "OPERATIONS_RUNTIME"
KNOWN_SUFFIXES = (
    ".hld.tar.gz", ".hld-tar-gz", ".tar.gz", ".parquet", ".csv.gz",
    ".dat.gz", ".hld", ".parquet", ".csv", ".dat", ".root", ".list",
    ".lis", ".fit", ".corr", ".pdf", ".png",
)
CANONICAL_RE = re.compile(r"(?i)(mi0\d|minI)(\d{11})")
UNPROCESSED_NAMES = ("UNPROCESSED_DIRECTORY", "UNPROCESSED")
ACTIVE_REGISTRY_RELATIVE = (
    Path("CONTEXTUAL") / "OPERATIONS" / "OPERATIONS_RUNTIME" / "STATE"
    / "REPROCESS_BASENAMES" / "active_reprocessing.csv"
)
SOURCE_STATE_NAMES = {
    "COMPLETED_DIRECTORY", "COMPLETED", "PROCESSING_DIRECTORY", "PROCESSING",
    "ERROR_DIRECTORY", "ERROR", "OUT_OF_DATE_DIRECTORY", "OUT_OF_DATE",
}


@dataclass(frozen=True)
class FileAction:
    kind: str
    source: Path
    destination: Path | None = None


@dataclass(frozen=True)
class MetadataChange:
    path: Path
    kept_rows: tuple[tuple[str, ...], ...]
    removed_count: int
    basename_column: int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, help="Process a generated QA manifest.")
    parser.add_argument("--station", help="Station: 1, 01, or MINGO01")
    parser.add_argument(
        "--task", choices=("all", "0", "1", "2", "3", "4", "5"),
        help="First task to clear; all is equivalent to starting at Task 0.",
    )
    parser.add_argument(
        "--basename", action="append", default=[],
        help="One basename. May be supplied repeatedly.",
    )
    parser.add_argument(
        "--basename-file", action="append", type=Path, default=[],
        help="Text/CSV file whose first field contains one basename per line.",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Perform changes. Without this flag, only print the plan.",
    )
    parser.add_argument(
        "--repo-root", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)
    manual = bool(args.station or args.task or args.basename or args.basename_file)
    if manual and (not args.station or args.task is None or not (args.basename or args.basename_file)):
        parser.error("manual mode requires --station, --task, and a basename input")
    if manual and args.manifest:
        parser.error("--manifest cannot be combined with manual mode")
    if not manual:
        args.manifest = args.manifest or DEFAULT_MANIFEST
    return args


def load_manifest_requests(path: Path) -> dict[tuple[str, int], list[str]]:
    if not path.is_file():
        raise FileNotFoundError(
            f"QA manifest not found: {path}. Run build_problematic_basename_lists.py first."
        )
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = set(reader.fieldnames or [])
        rows = list(reader)
    required = {"station", "basename", "start_task"}
    if not required <= header:
        missing = ", ".join(sorted(required - header))
        raise ValueError(f"Manifest lacks columns: {missing}")
    requests: dict[tuple[str, int], set[str]] = {}
    for row in rows:
        station_number, station_name = normalize_station(row.get("station", ""))
        raw_task = row.get("start_task", "")
        try:
            start_task = int(str(raw_task))
        except ValueError as exc:
            raise ValueError(f"Invalid manifest start_task: {raw_task}") from exc
        if not 0 <= start_task <= 5:
            raise ValueError(f"Manifest start_task outside 0..5: {start_task}")
        basename = canonicalize_basename(row.get("basename", ""), station_number)
        requests.setdefault((station_name, start_task), set()).add(basename)
    return {key: sorted(values) for key, values in sorted(requests.items())}


def normalize_station(raw: str) -> tuple[int, str]:
    text = str(raw).strip().upper()
    if text.startswith("MINGO"):
        text = text[5:]
    try:
        number = int(text)
    except ValueError as exc:
        raise ValueError(f"Invalid station {raw!r}") from exc
    if not 0 <= number <= 99:
        raise ValueError(f"Station is outside the supported range: {number}")
    return number, f"MINGO{number:02d}"


def canonicalize_basename(raw: str, station_number: int) -> str:
    text = str(raw).strip()
    if not text or text.startswith("#"):
        return ""
    text = text.split(",", 1)[0].strip()
    match = CANONICAL_RE.search(Path(text).name)
    if not match:
        stripped = Path(text).name
        lowered = stripped.lower()
        changed = True
        while changed:
            changed = False
            for suffix in KNOWN_SUFFIXES:
                if lowered.endswith(suffix):
                    stripped = stripped[: -len(suffix)]
                    lowered = stripped.lower()
                    changed = True
                    break
        match = CANONICAL_RE.fullmatch(stripped)
    if not match:
        raise ValueError(f"Cannot extract a DATAFLOW basename from {raw!r}")
    prefix, stamp = match.groups()
    prefix_lower = prefix.lower()
    found_station = 1 if prefix_lower == "mini" else int(prefix_lower[3])
    if found_station != station_number:
        raise ValueError(
            f"Basename {raw!r} belongs to station {found_station}, not {station_number}"
        )
    return f"mi0{station_number}{stamp}"


def load_basenames(
    direct: Iterable[str], files: Iterable[Path], station_number: int
) -> list[str]:
    raw_values = list(direct)
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(f"Basename file not found: {path}")
        raw_values.extend(path.read_text(encoding="utf-8").splitlines())
    values: set[str] = set()
    for raw in raw_values:
        if not str(raw).strip() or str(raw).lstrip().startswith("#"):
            continue
        try:
            value = canonicalize_basename(raw, station_number)
        except ValueError:
            first_field = str(raw).split(",", 1)[0].strip().lower()
            if first_field in {"basename", "filename_base"}:
                continue
            raise
        if value:
            values.add(value)
    if not values:
        raise ValueError("No valid basenames were supplied")
    return sorted(values)


def filename_matches(path: Path, basenames: set[str]) -> bool:
    name = path.name.lower().replace("mini", "mi01")
    return any(base in name for base in basenames)


def metadata_value_matches(value: str, basenames: set[str]) -> bool:
    text = str(value).strip().lower().replace("mini", "mi01")
    return text in basenames


def read_metadata_change(path: Path, basenames: set[str]) -> MetadataChange | None:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise RuntimeError(f"Unable to read metadata CSV {path}: {exc}") from exc
    if not rows:
        return None
    header = rows[0]
    basename_column = -1
    for candidate in ("filename_base", "basename"):
        if candidate in header:
            basename_column = header.index(candidate)
            break
    if basename_column < 0:
        return None
    kept: list[tuple[str, ...]] = [tuple(header)]
    removed = 0
    for row in rows[1:]:
        value = row[basename_column] if basename_column < len(row) else ""
        if metadata_value_matches(value, basenames):
            removed += 1
        else:
            kept.append(tuple(row))
    if not removed:
        return None
    return MetadataChange(path, tuple(kept), removed, basename_column)


def find_unprocessed_directory(input_root: Path) -> Path:
    for name in UNPROCESSED_NAMES:
        candidate = input_root / name
        if candidate.is_dir():
            return candidate
    return input_root / "UNPROCESSED_DIRECTORY"


def plan_artifact_actions(
    task_roots: list[Path], start_task: int, basenames: set[str]
) -> tuple[list[FileAction], int]:
    actions: list[FileAction] = []
    queued_inputs = 0
    start_root = task_roots[0]
    input_root = start_root / "INPUT_FILES"
    unprocessed_root = find_unprocessed_directory(input_root)
    destination_names: set[str] = set()

    for task_index, task_root in enumerate(task_roots, start=start_task):
        if not task_root.is_dir():
            continue
        for path in sorted(task_root.rglob("*")):
            if not path.is_file() or "METADATA" in path.parts:
                continue
            if not filename_matches(path, basenames):
                continue
            if task_index == start_task and input_root in path.parents:
                state_name = path.parent.name
                if state_name in UNPROCESSED_NAMES:
                    actions.append(FileAction("keep-queued", path))
                    queued_inputs += 1
                    continue
                if state_name in SOURCE_STATE_NAMES:
                    destination = unprocessed_root / path.name
                    if destination.exists() or destination.name in destination_names:
                        actions.append(FileAction("delete-duplicate-input", path))
                    else:
                        actions.append(FileAction("requeue", path, destination))
                        destination_names.add(destination.name)
                        queued_inputs += 1
                    continue
            actions.append(FileAction("delete", path))
    return actions, queued_inputs


def plan_metadata_changes(
    task_roots: Iterable[Path], basenames: set[str]
) -> list[MetadataChange]:
    changes: list[MetadataChange] = []
    for task_root in task_roots:
        metadata_root = task_root / "METADATA"
        if not metadata_root.is_dir():
            continue
        for csv_path in sorted(metadata_root.glob("*.csv")):
            change = read_metadata_change(csv_path, basenames)
            if change is not None:
                changes.append(change)
    return changes


def atomic_write_rows(path: Path, rows: tuple[tuple[str, ...], ...]) -> None:
    mode = path.stat().st_mode
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        temp_path = Path(handle.name)
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temp_path, mode)
    os.replace(temp_path, path)


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def register_active_requests(
    repo_root: Path,
    station_name: str,
    basenames: Iterable[str],
    start_task: int,
    stage0_fallback_basenames: set[str],
) -> Path:
    path = repo_root / ACTIVE_REGISTRY_RELATIVE
    header = [
        "station", "basename", "start_task", "requested_at", "stage0_fallback"
    ]
    existing: list[dict[str, str]] = []
    if path.is_file():
        with path.open("r", encoding="utf-8", newline="") as handle:
            existing = list(csv.DictReader(handle))
    replacement_keys = {(station_name, basename) for basename in basenames}
    rows = [
        row for row in existing
        if (str(row.get("station", "")), str(row.get("basename", "")))
        not in replacement_keys
    ]
    requested_at = datetime.now().isoformat(timespec="seconds")
    rows.extend({
        "station": station_name,
        "basename": basename,
        "start_task": str(start_task),
        "requested_at": requested_at,
        "stage0_fallback": "1" if basename in stage0_fallback_basenames else "0",
    } for basename in basenames)
    content_lines = [",".join(header)]
    content_lines.extend(
        ",".join(str(row.get(column, "")) for column in header)
        for row in sorted(
            rows,
            key=lambda row: (row.get("station", ""), row.get("basename", "")),
        )
    )
    atomic_write_text(path, "\n".join(content_lines) + "\n")
    return path


def rebuild_metadata_indexes(change: MetadataChange) -> None:
    values = sorted({
        row[change.basename_column].strip()
        for row in change.kept_rows[1:]
        if change.basename_column < len(row) and row[change.basename_column].strip()
    })
    content = "".join(f"{value}\n" for value in values)
    operation_index = (
        change.path.parent / "OPERATION" / f"{change.path.name}.filename_base.index"
    )
    atomic_write_text(operation_index, content)
    legacy_index = change.path.with_suffix(change.path.suffix + ".filename_base.index")
    if legacy_index.exists():
        atomic_write_text(legacy_index, content)


def print_plan(
    station_name: str,
    start_task: int,
    basenames: list[str],
    actions: list[FileAction],
    metadata_changes: list[MetadataChange],
    stage0_fallback_basenames: set[str],
    apply: bool,
) -> None:
    print(f"Mode: {'APPLY' if apply else 'DRY RUN'}")
    print(f"Station: {station_name}; tasks: {start_task}..5")
    print(f"Basenames ({len(basenames)}):")
    for basename in basenames:
        print(f"  {basename}")
    print("Artifact actions:")
    for action in actions:
        if action.destination is None:
            print(f"  {action.kind}: {action.source}")
        else:
            print(f"  {action.kind}: {action.source} -> {action.destination}")
    print("Metadata changes:")
    for change in metadata_changes:
        print(f"  remove {change.removed_count} row(s): {change.path}")
    if stage0_fallback_basenames:
        print(
            "Stage 0 fallback (no starting-task input): "
            + ", ".join(sorted(stage0_fallback_basenames))
        )


def apply_actions(
    actions: list[FileAction], metadata_changes: list[MetadataChange]
) -> tuple[int, int, int]:
    moved = deleted = metadata_rows = 0
    for action in actions:
        if action.kind == "keep-queued":
            continue
        if action.kind == "requeue":
            assert action.destination is not None
            action.destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(action.source), str(action.destination))
            moved += 1
        elif action.kind in {"delete", "delete-duplicate-input"}:
            action.source.unlink(missing_ok=True)
            deleted += 1
    for change in metadata_changes:
        atomic_write_rows(change.path, change.kept_rows)
        rebuild_metadata_indexes(change)
        metadata_rows += change.removed_count
    return moved, deleted, metadata_rows


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.manifest is not None:
        manifest_path = args.manifest.expanduser().resolve()
        requests = load_manifest_requests(manifest_path)
        print(f"QA manifest: {manifest_path}; request groups: {len(requests)}")
        if not requests:
            print("No problematic basenames to reprocess.")
            return 0
        for (station_name, start_task), basenames in requests.items():
            nested_args = [
                "--station", station_name,
                "--task", str(start_task),
                "--repo-root", str(args.repo_root),
            ]
            for basename in basenames:
                nested_args.extend(["--basename", basename])
            if args.apply:
                nested_args.append("--apply")
            result = main(nested_args)
            if result:
                return result
        return 0
    station_number, station_name = normalize_station(args.station)
    basenames = load_basenames(args.basename, args.basename_file, station_number)
    basename_set = set(basenames)
    start_task = 0 if args.task == "all" else int(args.task)
    repo_root = args.repo_root.resolve()
    station_root = (
        repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / station_name
    )
    step_root = station_root / "STAGE_1" / "EVENT_DATA" / "STEP_1"
    if not step_root.is_dir():
        raise FileNotFoundError(f"Stage 1 task root not found: {step_root}")
    task_roots = [step_root / f"TASK_{task}" for task in range(start_task, 6)]

    lock_handle = None
    if args.apply:
        lock_path = (
            repo_root / "CONTEXTUAL" / "OPERATIONS" / "OPERATIONS_RUNTIME" / "LOCKS" / "cron"
            / f"guide_raw_to_corrected_s{station_number}.lock"
        )
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_handle = lock_path.open("a+")
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                f"Station {station_name} pipeline is running; lock is busy: {lock_path}"
            ) from exc

    actions, queued_inputs = plan_artifact_actions(
        task_roots, start_task, basename_set
    )
    locally_queued = {
        basename
        for basename in basenames
        if any(
            action.kind in {"keep-queued", "requeue"}
            and filename_matches(action.source, {basename})
            for action in actions
        )
    }
    stage0_fallback_basenames = basename_set - locally_queued
    metadata_changes = plan_metadata_changes(task_roots, basename_set)
    print_plan(
        station_name, start_task, basenames, actions, metadata_changes,
        stage0_fallback_basenames, args.apply,
    )
    if not args.apply:
        print("Dry run complete. Re-run with --apply to perform these changes.")
        return 0
    moved, deleted, metadata_rows = apply_actions(actions, metadata_changes)
    registry_path = register_active_requests(
        repo_root, station_name, basenames, start_task, stage0_fallback_basenames
    )
    print(
        f"Applied: requeued_inputs={moved}, deleted_artifacts={deleted}, "
        f"deleted_metadata_rows={metadata_rows}."
    )
    print(f"Active reprocessing requests: {registry_path}")
    if stage0_fallback_basenames:
        print(
            "Stage 0 fallback requested for: "
            + ", ".join(sorted(stage0_fallback_basenames))
        )
    if lock_handle is not None:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
