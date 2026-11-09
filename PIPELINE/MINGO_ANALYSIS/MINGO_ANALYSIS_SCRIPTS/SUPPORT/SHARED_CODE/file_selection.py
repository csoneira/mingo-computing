"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/SHARED_CODE/file_selection.py
Purpose: Utilities for selecting the newest DATAFLOW artifacts by basename.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/SHARED_CODE/file_selection.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import os
import re
import shutil
from typing import Callable, Iterable, Mapping, Optional

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.selection_config import (
    DateRange,
    datetime_in_ranges,
    effective_date_ranges_for_station,
    resolve_selection_from_configs,
)

_ORDER_SUFFIXES: tuple[str, ...] = (
    ".hld.tar.gz",
    ".hld-tar-gz",
    ".tar.gz",
    ".hld",
    ".parquet",
    ".dat",
    ".root",
    ".list",
    ".lis",
    ".fit",
    ".corr",
)


def _strip_order_suffixes(name: str) -> str:
    """Remove known multi-part extensions so comparisons focus on the basename."""
    lowered = name.lower()
    for suffix in _ORDER_SUFFIXES:
        if lowered.endswith(suffix):
            return _strip_order_suffixes(name[: -len(suffix)])
    return name


def _normalize_prefix(name: str) -> str:
    """Normalize minI* prefixes back to mi01* for comparisons."""
    lowered = name.lower()
    if lowered.startswith("mini"):
        return "mi01" + lowered[4:]
    return lowered


def _station_prefix(station: str) -> str:
    try:
        station_int = int(str(station))
    except (TypeError, ValueError):
        return f"mi0{station}".lower()
    return f"mi0{station_int}".lower()


def newest_order_key(file_name: str, station: str) -> str:
    """Compute a comparison key that ignores the mi0X prefix when possible."""
    base = _strip_order_suffixes(file_name)
    normalized = _normalize_prefix(base)
    prefix = _station_prefix(station)
    if normalized.startswith(prefix):
        return normalized[len(prefix):]
    match = re.search(r"(\d{11})$", normalized)
    if match:
        return match.group(1)
    return normalized


def select_latest_candidate(files: Iterable[str], station: str) -> Optional[str]:
    """Return candidate by configured order after normalizing its prefix.

    Order is controlled by env var ``DATAFLOW_STEP1_SELECTION_ORDER``:
    - ``latest`` (default): newest/lexicographically-last
    - ``oldest``: oldest/lexicographically-first
    """
    candidates = [name for name in files if name]
    if not candidates:
        return None
    order = os.environ.get("DATAFLOW_STEP1_SELECTION_ORDER", "latest").strip().lower()
    key_fn = lambda name: newest_order_key(name, station)
    if order in {"oldest", "fifo", "first"}:
        return min(candidates, key=key_fn)
    return max(candidates, key=key_fn)


def filter_expected_artifact_names(
    files: Iterable[str],
    *,
    prefix: str = "",
    extension: str = "",
) -> list[str]:
    """Keep only files matching the expected handoff naming pattern."""
    prefix_lower = prefix.lower()
    extension_lower = extension.lower()
    filtered: list[str] = []
    for name in files:
        if not name:
            continue
        lowered = name.lower()
        if prefix_lower and not lowered.startswith(prefix_lower):
            continue
        if extension_lower and not lowered.endswith(extension_lower):
            continue
        filtered.append(name)
    return filtered


def load_date_ranges_from_config(
    config: Mapping[str, object],
    *,
    station_id: int | str | None = None,
    master_config_root: str | os.PathLike[str] | None = None,
) -> list[DateRange]:
    """Load effective date ranges (master override > local config)."""
    selection = resolve_selection_from_configs(
        [config],
        master_config_root=master_config_root,
    )
    if station_id is None:
        return list(selection.date_ranges)
    return list(effective_date_ranges_for_station(station_id, selection))


def load_date_range_from_config(
    config: Mapping[str, object],
    *,
    station_id: int | str | None = None,
    master_config_root: str | os.PathLike[str] | None = None,
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Compatibility helper returning the first effective date range only."""
    ranges = load_date_ranges_from_config(
        config,
        station_id=station_id,
        master_config_root=master_config_root,
    )
    if not ranges:
        return None, None
    return ranges[0]


def extract_run_datetime_from_name(file_name: str) -> Optional[datetime]:
    """Extract YYDDDHHMMSS timestamp from DATAFLOW artifact names."""
    base = _strip_order_suffixes(file_name)
    normalized = _normalize_prefix(base)
    match = re.search(r"(\d{11})$", normalized)
    if not match:
        return None

    stamp = match.group(1)
    try:
        yy = int(stamp[0:2])
        day_of_year = int(stamp[2:5])
        hour = int(stamp[5:7])
        minute = int(stamp[7:9])
        second = int(stamp[9:11])
    except ValueError:
        return None

    if not (1 <= day_of_year <= 366):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return None

    year = 2000 + yy
    try:
        return datetime(year, 1, 1) + timedelta(
            days=day_of_year - 1,
            hours=hour,
            minutes=minute,
            seconds=second,
        )
    except ValueError:
        return None


def file_name_in_date_range(
    file_name: str,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
) -> bool:
    """Return True when file timestamp is inside the single date interval."""
    return file_name_in_any_date_range(file_name, [(start_date, end_date)])


def file_name_in_any_date_range(
    file_name: str,
    date_ranges: Iterable[DateRange],
) -> bool:
    """Return True when file timestamp is inside any configured date range."""
    ranges = list(date_ranges)
    if not ranges:
        return True

    # Simulated MINGO00 artifacts must never be blocked by station date filters.
    # This covers both raw names ("mi00*.dat") and task-prefixed intermediates
    # such as "cleaned_mi00*.parquet".
    normalized = _normalize_prefix(_strip_order_suffixes(file_name))
    if re.search(r"(?:^|[_-])mi00\d{11}$", normalized):
        return True

    file_datetime = extract_run_datetime_from_name(file_name)
    if file_datetime is None:
        # Keep files with unparseable names to avoid accidental data loss.
        return True

    return datetime_in_ranges(file_datetime, ranges)


def sync_unprocessed_with_date_range(
    *,
    config: Mapping[str, object],
    unprocessed_directory: str,
    out_of_date_directory: str,
    log_fn: Callable[[str], None] = print,
    station_id: int | str | None = None,
    master_config_root: str | os.PathLike[str] | None = None,
) -> tuple[Optional[datetime], Optional[datetime]]:
    # Returns the first effective datetime range for compatibility with callers
    # that only inspect a single interval.
    """
    Move out-of-range files out of UNPROCESSED and restore in-range files when needed.
    """
    date_ranges = load_date_ranges_from_config(
        config,
        station_id=station_id,
        master_config_root=master_config_root,
    )

    os.makedirs(unprocessed_directory, exist_ok=True)
    os.makedirs(out_of_date_directory, exist_ok=True)

    if not date_ranges:
        return None, None

    moved_out = 0
    for file_name in sorted(os.listdir(unprocessed_directory)):
        src_path = os.path.join(unprocessed_directory, file_name)
        if not os.path.isfile(src_path):
            continue
        if file_name_in_any_date_range(file_name, date_ranges):
            continue

        dst_path = os.path.join(out_of_date_directory, file_name)
        if os.path.exists(dst_path):
            os.remove(dst_path)
        shutil.move(src_path, dst_path)
        moved_out += 1
        log_fn(
            f"[DATE_RANGE] Moved out-of-range file to OUT_OF_DATE_DIRECTORY: {file_name}"
        )

    remaining = [
        name
        for name in os.listdir(unprocessed_directory)
        if os.path.isfile(os.path.join(unprocessed_directory, name))
    ]
    if remaining:
        if moved_out:
            log_fn(
                f"[DATE_RANGE] Date filtering complete; kept {len(remaining)} file(s) in UNPROCESSED_DIRECTORY."
            )
        return date_ranges[0]

    log_fn(
        "[DATE_RANGE] UNPROCESSED_DIRECTORY is empty; checking OUT_OF_DATE_DIRECTORY for files in range."
    )
    restored = 0
    for file_name in sorted(os.listdir(out_of_date_directory)):
        src_path = os.path.join(out_of_date_directory, file_name)
        if not os.path.isfile(src_path):
            continue
        if not file_name_in_any_date_range(file_name, date_ranges):
            continue

        dst_path = os.path.join(unprocessed_directory, file_name)
        if os.path.exists(dst_path):
            os.remove(dst_path)
        shutil.move(src_path, dst_path)
        restored += 1
        log_fn(
            f"[DATE_RANGE] Restored in-range file to UNPROCESSED_DIRECTORY: {file_name}"
        )

    if restored == 0:
        log_fn("[DATE_RANGE] No in-range files found in OUT_OF_DATE_DIRECTORY.")

    return date_ranges[0]
