#!/usr/bin/env python3
"""Prune remote-log backup history outside selected analysis date windows."""

from __future__ import annotations

import argparse
import calendar
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()),
    None,
)
if REPO_ROOT is None:
    raise RuntimeError(f"Could not locate repository root from {__file__}")

DEFAULT_ROOT = REPO_ROOT / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/REMOTE_LOG_BACKUP"
DEFAULT_SELECTION_CONFIG = REPO_ROOT / "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/CONFIG_FILES/config_selection.yaml"
HOST_PATTERN = re.compile(r"^mingo(\d{2})$")
DATED_NAME_PATTERN = re.compile(
    r"(?<!\d)(?P<year>20\d{2})[-_](?P<month>\d{2})[-_](?P<day>\d{2})(?!\d)"
)


@dataclass(frozen=True)
class DateWindow:
    start: datetime
    end: datetime


@dataclass
class PruneStats:
    scanned_files: int = 0
    kept_files: int = 0
    removed_files: int = 0
    removed_bytes: int = 0


def _parse_datetime(value: object, *, is_end: bool) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.max if is_end else time.min)
    else:
        text = str(value).strip()
        if not text:
            raise ValueError("empty date boundary")
        parsed = datetime.fromisoformat(text)

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    if is_end and parsed.time() == time.min and len(str(value).strip()) <= 10:
        parsed = datetime.combine(parsed.date(), time.max)
    return parsed


def _shift_months(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 + months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _merge_windows(windows: Iterable[DateWindow]) -> list[DateWindow]:
    ordered = sorted(windows, key=lambda item: (item.start, item.end))
    merged: list[DateWindow] = []
    for window in ordered:
        if not merged or window.start > merged[-1].end:
            merged.append(window)
            continue
        merged[-1] = DateWindow(merged[-1].start, max(merged[-1].end, window.end))
    return merged


def load_station_windows(config_path: Path, context_months: int) -> dict[int, list[DateWindow]]:
    with config_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}

    selection = loaded.get("selection")
    if not isinstance(selection, dict):
        raise ValueError("selection mapping is missing")
    raw_ranges = selection.get("date_ranges")
    if not isinstance(raw_ranges, list) or not raw_ranges:
        raise ValueError("selection.date_ranges is missing or empty")

    station_windows: dict[int, list[DateWindow]] = {}
    all_station_windows: list[DateWindow] = []
    for index, raw_range in enumerate(raw_ranges, start=1):
        if not isinstance(raw_range, dict):
            raise ValueError(f"date_ranges entry #{index} is not a mapping")
        if raw_range.get("start") is None or raw_range.get("end") is None:
            raise ValueError(f"date_ranges entry #{index} requires start and end")
        start = _parse_datetime(raw_range["start"], is_end=False)
        end = _parse_datetime(raw_range["end"], is_end=True)
        if end < start:
            start, end = end, start
        window = DateWindow(
            _shift_months(start, -context_months),
            _shift_months(end, context_months),
        )

        raw_stations = raw_range.get("stations")
        if raw_stations is None:
            all_station_windows.append(window)
            continue
        if not isinstance(raw_stations, list):
            raise ValueError(f"date_ranges entry #{index} stations must be a list")
        for raw_station in raw_stations:
            station_windows.setdefault(int(raw_station), []).append(window)

    configured_stations = selection.get("stations")
    station_ids = (
        {int(item) for item in configured_stations}
        if isinstance(configured_stations, list)
        else set(station_windows)
    )
    station_ids.update(station_windows)
    return {
        station_id: _merge_windows(
            [*all_station_windows, *station_windows.get(station_id, [])]
        )
        for station_id in station_ids
    }


def timestamp_for_history_file(path: Path, snapshot_dir: Path) -> datetime:
    relative_text = path.relative_to(snapshot_dir).as_posix()
    match = DATED_NAME_PATTERN.search(relative_text)
    if match:
        try:
            return datetime(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
                12,
            )
        except ValueError:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime)


def timestamp_is_retained(value: datetime, windows: Iterable[DateWindow]) -> bool:
    return any(window.start <= value <= window.end for window in windows)


def prune_host_history(
    history_root: Path, windows: list[DateWindow], *, apply: bool
) -> PruneStats:
    stats = PruneStats()
    if not history_root.is_dir():
        return stats

    snapshot_dirs = sorted(path for path in history_root.iterdir() if path.is_dir())
    for snapshot_dir in snapshot_dirs:
        for path in snapshot_dir.rglob("*"):
            if not path.is_file():
                continue
            stats.scanned_files += 1
            if timestamp_is_retained(
                timestamp_for_history_file(path, snapshot_dir), windows
            ):
                stats.kept_files += 1
                continue
            try:
                file_size = path.stat().st_size
            except FileNotFoundError:
                continue
            stats.removed_files += 1
            stats.removed_bytes += file_size
            if apply:
                path.unlink(missing_ok=True)

        if apply:
            for directory in sorted(
                (path for path in snapshot_dir.rglob("*") if path.is_dir()),
                key=lambda item: len(item.parts),
                reverse=True,
            ):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            try:
                snapshot_dir.rmdir()
            except OSError:
                pass
    return stats


def format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024.0 or unit == units[-1]:
            return f"{amount:.2f} {unit}"
        amount /= 1024.0
    raise AssertionError("unreachable")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Keep remote-log history only inside config_selection.yaml date_ranges, "
            "expanded by calendar-month context."
        )
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_SELECTION_CONFIG)
    parser.add_argument("--context-months", type=int, default=1)
    parser.add_argument("--host", action="append", default=[])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete files outside retention windows. Otherwise report only.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.context_months < 0:
        print("ERROR: --context-months must be non-negative", file=sys.stderr)
        return 2
    try:
        station_windows = load_station_windows(args.config.expanduser(), args.context_months)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        print(
            f"ERROR: retention configuration is unusable; history left untouched: {exc}",
            file=sys.stderr,
        )
        return 2

    root = args.root.expanduser()
    host_names = args.host or [
        path.name
        for path in sorted((root / "hosts").glob("mingo[0-9][0-9]"))
        if path.is_dir()
    ]
    total = PruneStats()
    for host_name in host_names:
        host_match = HOST_PATTERN.fullmatch(host_name)
        if not host_match:
            print(f"ERROR: invalid host name: {host_name}", file=sys.stderr)
            return 2
        station_id = int(host_match.group(1))
        windows = station_windows.get(station_id, [])
        stats = prune_host_history(
            root / "hosts" / host_name / "history", windows, apply=args.apply
        )
        total.scanned_files += stats.scanned_files
        total.kept_files += stats.kept_files
        total.removed_files += stats.removed_files
        total.removed_bytes += stats.removed_bytes
        action = "removed" if args.apply else "would_remove"
        print(
            f"{host_name}: windows={len(windows)} scanned={stats.scanned_files} "
            f"kept={stats.kept_files} {action}={stats.removed_files} "
            f"bytes={stats.removed_bytes}"
        )

    action = "removed" if args.apply else "would_remove"
    print(
        f"TOTAL: scanned={total.scanned_files} kept={total.kept_files} "
        f"{action}={total.removed_files} bytes={total.removed_bytes} "
        f"size={format_bytes(total.removed_bytes)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
