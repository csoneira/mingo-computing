#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/FIX_METADATA_FILES/fix_event_metadata_files.py
Purpose: Repair Stage 1 event metadata CSVs by splitting embedded rows and removing malformed records.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-05-05
Runtime: python3
Usage: python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/FIX_METADATA_FILES/fix_event_metadata_files.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import fcntl
from io import StringIO
import re
import sys
from pathlib import Path
from typing import Iterable

CSV_FIELD_LIMIT = 131072
METADATA_GLOB = "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO0*/STAGE_1/EVENT_DATA/STEP_1/TASK_*/METADATA/task_*_metadata_*.csv"
EMBEDDED_ROW_START_RE = re.compile(r"(?<![\r\n])(mi\d{13},)")
STATUS_SENTINEL_BASENAME_RE = re.compile(r"^__task\d+_startup_station_\d+__$")
BASENAME_COLUMNS = ("filename_base", "basename")

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


@dataclass
class FileStats:
    rows_before: int = 0
    rows_after: int = 0
    embedded_row_start_repairs: int = 0
    field_mismatch_hits: int = 0
    nan_hits: int = 0
    basename_hits: int = 0
    oversized_hits: int = 0
    locked_skip_hits: int = 0

    @property
    def rows_removed(self) -> int:
        return max(0, self.rows_before - self.rows_after)

    @property
    def changed(self) -> bool:
        return self.rows_removed > 0 or self.embedded_row_start_repairs > 0

    def merge(self, other: "FileStats") -> None:
        self.rows_before += other.rows_before
        self.rows_after += other.rows_after
        self.embedded_row_start_repairs += other.embedded_row_start_repairs
        self.field_mismatch_hits += other.field_mismatch_hits
        self.nan_hits += other.nan_hits
        self.basename_hits += other.basename_hits
        self.oversized_hits += other.oversized_hits
        self.locked_skip_hits += other.locked_skip_hits


def detect_repo_root(start: Path) -> Path:
    """Ascend upwards until a directory containing PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/ is found."""
    for parent in [start] + list(start.parents):
        if (parent / "STATIONS").is_dir():
            return parent
    return start


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    default_root = detect_repo_root(script_dir)
    parser = argparse.ArgumentParser(
        description=(
            "Repair STAGE_1 EVENT_DATA metadata CSV files by splitting embedded "
            "filename_base rows and removing malformed records."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=default_root,
        help=f"Repository root containing PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/ (default: {default_root})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report what would change without modifying files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-file details even when no changes are required.",
    )
    parser.add_argument(
        "--quiet-if-clean",
        action="store_true",
        help="Suppress output when no file requires changes. Intended for cron usage.",
    )
    parser.add_argument(
        "--wait-for-locks",
        action="store_true",
        help="Block on active metadata locks instead of skipping busy files.",
    )
    return parser.parse_args()


def has_nan_value(row: Iterable[str]) -> bool:
    for value in row:
        if value is None:
            continue
        if str(value).strip().lower() == "nan":
            return True
    return False


def has_oversized_field(row: Iterable[str]) -> bool:
    for value in row:
        if value is None:
            continue
        if len(str(value)) >= CSV_FIELD_LIMIT:
            return True
    return False


def basename_invalid(path: Path, row: list[str], basename_idx: int | None) -> bool:
    if basename_idx is None or basename_idx >= len(row):
        return False
    value = row[basename_idx].strip()
    if not value:
        return True
    if path.name.endswith("_metadata_status.csv") and STATUS_SENTINEL_BASENAME_RE.fullmatch(value):
        return False
    return not value.lower().startswith("mi")


def _metadata_lock_path(path: Path) -> Path:
    return path.parent / "OPERATION" / f"{path.name}.lock"


def _basename_index(header: list[str]) -> int | None:
    for column_name in BASENAME_COLUMNS:
        try:
            return header.index(column_name)
        except ValueError:
            continue
    return None


def _read_rows_with_embedded_row_repairs(path: Path) -> tuple[list[list[str]], int]:
    repaired_text, repair_count = EMBEDDED_ROW_START_RE.subn(
        r"\n\1",
        path.read_text(encoding="utf-8", errors="replace"),
    )
    reader = csv.reader(StringIO(repaired_text))
    return [row for row in reader], repair_count


def write_rows(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerows(rows)


def process_file(path: Path, dry_run: bool, *, wait_for_locks: bool) -> FileStats:
    lock_path = _metadata_lock_path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a", encoding="utf-8") as lock_handle:
        lock_mode = fcntl.LOCK_EX if wait_for_locks else (fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            fcntl.flock(lock_handle.fileno(), lock_mode)
        except BlockingIOError:
            return FileStats(locked_skip_hits=1)

        rows, repair_count = _read_rows_with_embedded_row_repairs(path)
        if not rows:
            return FileStats()

        header = rows[0]
        expected_fields = len(header)
        basename_idx = _basename_index(header)

        stats = FileStats(rows_before=max(0, len(rows) - 1), embedded_row_start_repairs=repair_count)
        kept_rows = [header]

        for row in rows[1:]:
            remove = False
            if len(row) != expected_fields:
                remove = True
                stats.field_mismatch_hits += 1
            if has_nan_value(row):
                remove = True
                stats.nan_hits += 1
            if basename_invalid(path, row, basename_idx):
                remove = True
                stats.basename_hits += 1
            if has_oversized_field(row):
                remove = True
                stats.oversized_hits += 1
            if not remove:
                kept_rows.append(row)

        stats.rows_after = len(kept_rows) - 1
        if stats.changed and not dry_run:
            write_rows(path, kept_rows)
        return stats


def collect_metadata_files(root: Path) -> list[Path]:
    return sorted(candidate for candidate in root.glob(METADATA_GLOB) if candidate.is_file())


def main() -> int:
    args = parse_args()
    root = args.root.resolve()

    if not root.is_dir():
        print(f"Root directory {root} does not exist or is not a directory.", file=sys.stderr)
        return 1

    files = collect_metadata_files(root)
    if not files:
        print(f"No metadata CSV files matched under {root}.")
        return 0

    total_stats = FileStats()
    changed_files = 0

    for csv_path in files:
        file_stats = process_file(csv_path, args.dry_run, wait_for_locks=args.wait_for_locks)
        total_stats.merge(file_stats)
        if file_stats.changed:
            changed_files += 1
        if file_stats.locked_skip_hits > 0 and args.verbose:
            print(f"{csv_path}: skipped because its metadata lock is currently held.")
            continue
        if file_stats.changed or args.verbose:
            action = "would fix" if args.dry_run else "fixed"
            print(
                f"{csv_path}: {action} {file_stats.rows_removed} row(s) "
                f"(embedded_row_splits={file_stats.embedded_row_start_repairs}, "
                f"field_mismatch={file_stats.field_mismatch_hits}, "
                f"nan={file_stats.nan_hits}, "
                f"invalid_basename={file_stats.basename_hits}, "
                f"oversized_field={file_stats.oversized_hits})"
            )

    if not (
        args.quiet_if_clean
        and changed_files == 0
        and total_stats.locked_skip_hits == 0
        and not args.verbose
    ):
        summary_action = "Would fix" if args.dry_run else "Fixed"
        print(
            f"{summary_action} {total_stats.rows_removed} of {total_stats.rows_before} row(s) "
            f"across {changed_files} changed file(s) out of {len(files)} scanned. "
            f"(embedded_row_splits={total_stats.embedded_row_start_repairs}, "
            f"field_mismatch={total_stats.field_mismatch_hits}, "
            f"nan={total_stats.nan_hits}, "
            f"invalid_basenames={total_stats.basename_hits}, "
            f"oversized_field={total_stats.oversized_hits}, "
            f"locked_skips={total_stats.locked_skip_hits})"
        )
        if args.dry_run:
            print("Dry-run complete. Re-run without --dry-run to apply fixes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
