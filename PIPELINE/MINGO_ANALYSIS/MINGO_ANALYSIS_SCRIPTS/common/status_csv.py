"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/common/status_csv.py
Purpose: Utility helpers for tracking script execution status via CSV files.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/common/status_csv.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.execution_logger import start_timer
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.step1_shared import should_write_step1_metadata

start_timer(__file__)

STATUS_FIELDNAMES = ("filename_base", "execution_date", "param_hash", "completion_fraction")


def _clamp_completion(completion: object) -> float:
    try:
        value = float(completion)
    except (TypeError, ValueError):
        value = 0.0
    if value == -1.0:
        return -1.0
    return max(0.0, min(1.0, value))


def _format_completion(completion: object) -> str:
    value = _clamp_completion(completion)
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def _load_status_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []

    rows: list[dict[str, str]] = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            filename_base = str(raw.get("filename_base", raw.get("basename", "")) or "")
            execution_date = str(
                raw.get(
                    "execution_date",
                    raw.get("execution_timestamp", raw.get("timestamp", "")),
                )
                or ""
            )
            completion = raw.get(
                "completion_fraction",
                raw.get("completion", raw.get("status", "0")),
            )
            param_hash = str(raw.get("param_hash", "") or "")
            rows.append(
                {
                    "filename_base": filename_base,
                    "execution_date": execution_date,
                    "param_hash": param_hash,
                    "completion_fraction": _format_completion(completion),
                }
            )
    return rows


def _write_status_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=STATUS_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def initialize_status_row(
    status_csv_path: Path | str,
    filename_base: str,
    execution_date: str | None = None,
    param_hash: str = "",
    completion_fraction: float = 0.0,
) -> str:
    """Append a status row and return the execution date key used for updates."""

    path = Path(status_csv_path)
    if execution_date is None:
        execution_date = datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
    metadata_write_enabled, _, _ = should_write_step1_metadata(path)
    if not metadata_write_enabled:
        return execution_date

    rows = _load_status_rows(path)
    rows.append(
        {
            "filename_base": str(filename_base),
            "execution_date": execution_date,
            "param_hash": str(param_hash or ""),
            "completion_fraction": _format_completion(completion_fraction),
        }
    )
    _write_status_rows(path, rows)
    return execution_date


def update_status_progress(
    status_csv_path: Path | str,
    filename_base: str,
    execution_date: str,
    completion_fraction: float,
    param_hash: str | None = None,
) -> bool:
    """Update completion for the matching ``filename_base`` + ``execution_date`` row."""

    path = Path(status_csv_path)
    metadata_write_enabled, _, _ = should_write_step1_metadata(path)
    if not metadata_write_enabled:
        return True
    if not path.exists():
        return False

    rows = _load_status_rows(path)
    for row in reversed(rows):
        if (
            row.get("filename_base") == str(filename_base)
            and row.get("execution_date") == execution_date
        ):
            row["completion_fraction"] = _format_completion(completion_fraction)
            if param_hash is not None:
                row["param_hash"] = str(param_hash or "")
            _write_status_rows(path, rows)
            return True
    return False


def rename_status_row(
    status_csv_path: Path | str,
    filename_base: str,
    execution_date: str,
    new_filename_base: str,
) -> bool:
    """Rename the matching status row without changing its execution key."""

    path = Path(status_csv_path)
    metadata_write_enabled, _, _ = should_write_step1_metadata(path)
    if not metadata_write_enabled:
        return True
    if not path.exists():
        return False

    rows = _load_status_rows(path)
    for row in reversed(rows):
        if (
            row.get("filename_base") == str(filename_base)
            and row.get("execution_date") == execution_date
        ):
            row["filename_base"] = str(new_filename_base)
            _write_status_rows(path, rows)
            return True
    return False


def delete_status_row(
    status_csv_path: Path | str,
    filename_base: str,
    execution_date: str,
) -> bool:
    """Delete the matching status row."""

    path = Path(status_csv_path)
    metadata_write_enabled, _, _ = should_write_step1_metadata(path)
    if not metadata_write_enabled:
        return True
    if not path.exists():
        return False

    rows = _load_status_rows(path)
    kept_rows = [
        row
        for row in rows
        if not (
            row.get("filename_base") == str(filename_base)
            and row.get("execution_date") == execution_date
        )
    ]
    if len(kept_rows) == len(rows):
        return False
    _write_status_rows(path, kept_rows)
    return True


def append_status_row(status_csv_path: Path | str) -> str:
    """Append a new row marking the start of an execution.

    Returns the timestamp string written to the CSV so the caller can later
    mark this particular run as complete.
    """

    path = Path(status_csv_path)
    metadata_write_enabled, _, _ = should_write_step1_metadata(path)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not metadata_write_enabled:
        return timestamp
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="") as handle:
        writer = csv.writer(handle)
        if not file_exists:
            writer.writerow(["timestamp", "status"])
        writer.writerow([timestamp, "0"])
    return timestamp


def mark_status_complete(status_csv_path: Path | str, timestamp: str) -> bool:
    """Mark the row created for *timestamp* as completed.

    Returns ``True`` if a matching pending row was updated, ``False``
    otherwise (for example if the CSV was deleted in the meantime).
    """

    path = Path(status_csv_path)
    metadata_write_enabled, _, _ = should_write_step1_metadata(path)
    if not metadata_write_enabled:
        return True
    if not path.exists():
        return False

    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        rows = [row for row in reader]

    if rows and rows[0][:2] == ["timestamp", "status"]:
        updated = False
        for row in rows[1:]:
            if len(row) >= 2 and row[0] == timestamp and row[1] == "0":
                row[1] = "1"
                updated = True
                break
        if not updated:
            return False
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerows(rows)
        return True

    # Fallback for status files in the new schema.
    normalized_rows = _load_status_rows(path)
    for row in reversed(normalized_rows):
        if row.get("execution_date") == timestamp and row.get("completion_fraction") != "1":
            row["completion_fraction"] = "1"
            _write_status_rows(path, normalized_rows)
            return True
    return False


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage status CSV files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    append_parser = subparsers.add_parser("append", help="append a pending row")
    append_parser.add_argument("status_csv", type=Path)

    complete_parser = subparsers.add_parser(
        "complete", help="mark a previously appended row as complete"
    )
    complete_parser.add_argument("status_csv", type=Path)
    complete_parser.add_argument("timestamp")

    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)

    if args.command == "append":
        timestamp = append_status_row(args.status_csv)
        print(timestamp)
        return 0

    if args.command == "complete":
        if not mark_status_complete(args.status_csv, args.timestamp):
            print(
                "Warning: could not update status row; entry not found or already marked.",
                file=sys.stderr,
            )
            return 1
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
