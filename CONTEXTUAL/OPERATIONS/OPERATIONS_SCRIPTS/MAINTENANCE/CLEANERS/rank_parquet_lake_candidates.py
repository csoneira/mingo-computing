#!/usr/bin/env python3
"""Rank emergency PARQUET_LAKE deletion candidates by interest tier and age."""

from __future__ import annotations

from pathlib import Path
import re
import sys


def main() -> int:
    if len(sys.argv) < 4:
        print(
            "Usage: rank_parquet_lake_candidates.py DATAFLOW_ROOT CONFIG_ROOT LAKE_DIR...",
            file=sys.stderr,
        )
        return 2

    repo_root = Path(sys.argv[1]).resolve()
    config_root = Path(sys.argv[2]).resolve()
    lake_dirs = [Path(value) for value in sys.argv[3:]]
    sys.path.insert(0, str(repo_root))

    from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.file_selection import (
        file_name_in_any_date_range,
    )
    from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.selection_config import (
        effective_date_ranges_for_station,
        load_master_selection,
    )

    selection = load_master_selection(config_root)
    records: list[tuple[int, int, int, str]] = []
    for lake_dir in lake_dirs:
        station_match = re.search(r"/MINGO0([0-9])(?:/|$)", str(lake_dir))
        station_id = int(station_match.group(1)) if station_match else None
        ranges = (
            effective_date_ranges_for_station(station_id, selection)
            if station_id is not None
            else ()
        )
        try:
            candidates = lake_dir.glob("*.parquet")
            for path in candidates:
                try:
                    stat_result = path.stat()
                except (FileNotFoundError, OSError):
                    continue
                in_interest = file_name_in_any_date_range(path.name, ranges)
                priority = 1 if in_interest else 0
                records.append(
                    (priority, stat_result.st_mtime_ns, stat_result.st_size, str(path))
                )
        except OSError:
            continue

    # Tier 0 (outside interest) is exhausted first. Each tier is globally oldest-first.
    records.sort(key=lambda item: (item[0], item[1], item[3]))
    for priority, mtime_ns, size, path in records:
        record = f"{priority}\t{mtime_ns}\t{size}\t{path}".encode("utf-8")
        sys.stdout.buffer.write(record + b"\0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
