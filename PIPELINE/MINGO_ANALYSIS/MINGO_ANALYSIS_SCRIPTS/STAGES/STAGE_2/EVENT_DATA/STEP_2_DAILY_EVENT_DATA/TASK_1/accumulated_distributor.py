#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Distribute accumulated event files to the next processing step."""

from __future__ import annotations

import argparse
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd

_REPO_IMPORT_ROOT = Path(__file__).resolve().parents[8]
if str(_REPO_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_IMPORT_ROOT))
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root
REPO_ROOT = get_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Distribute accumulated_|*.csv files from STAGE_2/EVENT_DATA/ACCUMULATED_EVENTS into "
            "STEP_3/TASK_1_TO_2/<YEAR>/<MONTH>/<DAY>. "
            "Files spanning multiple days are split accordingly."
        )
    )
    parser.add_argument("station", help="Station identifier (e.g. 1, 2, 3, 4)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show actions without moving or writing files.",
    )
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Process files from STAGE_2/EVENT_DATA/ACCUMULATED_EVENTS and the archive directory.",
    )
    parser.add_argument(
        "--archive",
        default="INPUT_FILES",
        help="Directory name (under TASK_1) where processed originals are moved.",
    )
    return parser.parse_args()


def collect_header_lines(path: Path) -> List[str]:
    header_lines: List[str] = []
    with path.open("r", encoding="utf-8") as handle:
        while True:
            pos = handle.tell()
            line = handle.readline()
            if not line:
                break
            if line.startswith("#"):
                header_lines.append(line.rstrip("\n"))
            else:
                # rewind to the start of the first non-comment line
                handle.seek(pos)
                break
    return header_lines


def load_dataframe(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, comment="#")
    if "Time" not in df.columns:
        raise ValueError("Column 'Time' not present.")
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    if df["Time"].isna().all():
        raise ValueError("No valid timestamps in 'Time' column.")
    df = df.dropna(subset=["Time"]).sort_values("Time").reset_index(drop=True)
    return df


def ensure_directory(path: Path, dry_run: bool = False) -> None:
    if dry_run:
        if not path.exists():
            print(f"[dry-run] mkdir -p {path}")
        return
    path.mkdir(parents=True, exist_ok=True)


def write_split_file(
    header_lines: Iterable[str],
    dataframe: pd.DataFrame,
    destination: Path,
    dry_run: bool = False,
) -> None:
    ensure_directory(destination.parent, dry_run=dry_run)
    if dry_run:
        print(f"[dry-run] write {destination}")
        return
    with destination.open("w", encoding="utf-8", newline="") as handle:
        for line in header_lines:
            handle.write(line + "\n")
        dataframe.to_csv(handle, index=False)


def split_and_place_file(
    source_file: Path,
    destination_root: Path,
    archive_dir: Path,
    dry_run: bool = False,
) -> Tuple[List[Path], Path]:
    header_lines = collect_header_lines(source_file)
    df = load_dataframe(source_file)

    df["date_bucket"] = df["Time"].dt.date
    grouped = df.groupby("date_bucket", sort=True)

    base_name = source_file.name
    stripped_name = base_name.replace("accumulated_", "", 1)

    created_files: List[Path] = []
    for index, (date_bucket, group) in enumerate(grouped, start=1):
        year = f"{date_bucket:%Y}"
        month = f"{date_bucket:%m}"
        day = f"{date_bucket:%d}"

        target_dir = destination_root / year / month / day
        ensure_directory(target_dir, dry_run=dry_run)

        if len(grouped) == 1:
            target_name = base_name
        else:
            target_name = f"accumulated_{index}_{stripped_name}"


        destination_path = target_dir / target_name
        write_split_file(header_lines, group.drop(columns=["date_bucket"]), destination_path, dry_run=dry_run)
        created_files.append(destination_path)

    archive_path = archive_dir / base_name
    already_archived = source_file.parent == archive_dir

    if already_archived:
        if dry_run:
            print(f"[dry-run] source already archived at {archive_path}")
    else:
        if not dry_run:
            ensure_directory(archive_dir, dry_run=False)
            shutil.move(str(source_file), str(archive_path))
        else:
            print(f"[dry-run] move {source_file} -> {archive_path}")

    return created_files, archive_path


def main() -> int:
    args = parse_args()
    station = args.station

    station_dir = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / f"MINGO0{station}"
    step2_to_3_dir = station_dir / "STAGE_2" / "EVENT_DATA" / "ACCUMULATED_EVENTS"
    step3_root = station_dir / "STAGE_2" / "EVENT_DATA" / "STEP_2_DAILY_EVENT_DATA"
    task1_root = step3_root / "TASK_1"
    destination_root = step3_root / "TASK_1_TO_2"
    archive_dir = task1_root / args.archive

    if not step2_to_3_dir.exists():
        print(f"Source directory not found: {step2_to_3_dir}")
        return 1

    ensure_directory(destination_root, dry_run=args.dry_run)
    ensure_directory(archive_dir, dry_run=args.dry_run)

    step2_files = sorted(p for p in step2_to_3_dir.glob("accumulated_*.csv"))
    archive_files: List[Path] = []
    if args.all:
        archive_files = sorted(p for p in archive_dir.glob("accumulated_*.csv"))

    source_files = step2_files + archive_files

    if not source_files:
        print("No accumulated CSV files found to process.")
        return 0

    archive_note = ""
    if archive_files:
        archive_note = f" (including {len(archive_files)} from archive)"

    print(
        f"Processing {len(source_files)} accumulated CSV file(s) for station {station}{archive_note}..."
    )

    for csv_file in source_files:
        print(f"  > {csv_file.name}")
        try:
            created, archived = split_and_place_file(
                csv_file,
                destination_root,
                archive_dir,
                dry_run=args.dry_run,
            )
        except Exception as exc:
            print(f"    ! Failed to distribute {csv_file.name}: {exc}")
            continue

        already_archived = csv_file.parent == archive_dir

        if args.dry_run:
            for target in created:
                print(f"    [dry-run] would create: {target}")
        else:
            for target in created:
                print(f"    Created: {target}")
            if already_archived:
                print(f"    Source already archived at: {archived}")
            else:
                print(f"    Archived original to: {archived}")

    print("Distribution complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
