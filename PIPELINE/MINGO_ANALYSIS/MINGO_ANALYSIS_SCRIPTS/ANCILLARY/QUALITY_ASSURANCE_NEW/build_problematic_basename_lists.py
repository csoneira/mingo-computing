#!/usr/bin/env python3
"""Build purge-ready basename lists from the QUALITY_ASSURANCE_NEW summary."""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import tempfile

import pandas as pd

try:
    from .qa_core.reprocessing_state import reconcile_active_requests
except ImportError:
    from qa_core.reprocessing_state import reconcile_active_requests


QA_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = (
    QA_ROOT / "TOTAL_SUMMARY" / "OUTPUTS" / "FILES"
    / "qa_all_stations_reprocessing_quality.csv"
)
DEFAULT_OUTPUT = QA_ROOT / "PROBLEMATIC_BASENAMES"
TASK_RE = re.compile(r"::TASK_([0-5])::")
BASENAME_RE = re.compile(r"^mi0([0-9])(\d{11})$", re.IGNORECASE)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--stations", nargs="*", help="Optional station filter, e.g. 1 MINGO02"
    )
    return parser.parse_args(argv)


def normalize_station(value: object) -> str:
    text = str(value).strip().upper()
    if text.startswith("MINGO"):
        text = text[5:]
    number = int(text)
    if not 0 <= number <= 99:
        raise ValueError(f"Invalid station: {value!r}")
    return f"MINGO{number:02d}"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def build_problematic_manifest(
    summary: pd.DataFrame,
    *,
    stations: set[str] | None = None,
) -> pd.DataFrame:
    required = {
        "station_name", "filename_base", "quality_status",
        "failed_quality_columns",
    }
    missing = sorted(required - set(summary.columns))
    if missing:
        raise ValueError(f"QA summary is missing columns: {', '.join(missing)}")

    working = summary.copy()
    working["station"] = working["station_name"].map(normalize_station)
    working["basename"] = (
        working["filename_base"].astype("string").fillna("").str.strip().str.lower()
    )
    working = working[
        working["quality_status"].astype(str).str.strip().str.lower().eq("fail")
    ].copy()
    if stations is not None:
        working = working[working["station"].isin(stations)].copy()

    def earliest_task(value: object) -> int | None:
        tasks = [int(match) for match in TASK_RE.findall(str(value))]
        return min(tasks) if tasks else None

    working["start_task"] = working["failed_quality_columns"].map(earliest_task)
    valid_basename = working["basename"].str.fullmatch(BASENAME_RE)
    matching_station = working.apply(
        lambda row: bool(BASENAME_RE.fullmatch(str(row["basename"])))
        and f"MINGO0{BASENAME_RE.fullmatch(str(row['basename'])).group(1)}"
        == row["station"],
        axis=1,
    )
    invalid = working[
        working["start_task"].isna() | ~valid_basename | ~matching_station
    ]
    if not invalid.empty:
        examples = ", ".join(invalid["basename"].astype(str).head(5))
        raise ValueError(
            f"{len(invalid)} failed QA row(s) lack a valid basename/task mapping: {examples}"
        )

    working["start_task"] = working["start_task"].astype(int)
    if "failed_quality_versions" not in working:
        working["failed_quality_versions"] = ""
    if "plot_timestamp" not in working:
        working["plot_timestamp"] = ""
    working["generated_at"] = datetime.now().isoformat(timespec="seconds")
    columns = [
        "station", "basename", "start_task", "quality_status",
        "failed_quality_columns", "failed_quality_versions", "plot_timestamp",
        "generated_at",
    ]
    return (
        working[columns]
        .drop_duplicates(subset=["station", "basename"], keep="last")
        .sort_values(["station", "start_task", "basename"])
        .reset_index(drop=True)
    )


def write_problematic_outputs(manifest: pd.DataFrame, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "problematic_basenames.csv"
    _atomic_write(manifest_path, manifest.to_csv(index=False))

    expected: set[Path] = {manifest_path}
    for station, station_rows in manifest.groupby("station", sort=True):
        station_path = output_dir / f"{station}_problematic_basenames.txt"
        _atomic_write(
            station_path,
            "".join(f"{value}\n" for value in station_rows["basename"]),
        )
        expected.add(station_path)
        for task, task_rows in station_rows.groupby("start_task", sort=True):
            task_path = output_dir / f"{station}_task_{int(task)}_problematic_basenames.txt"
            _atomic_write(
                task_path,
                "".join(f"{value}\n" for value in task_rows["basename"]),
            )
            expected.add(task_path)

    for stale in output_dir.glob("MINGO*_problematic_basenames.txt"):
        if stale not in expected:
            stale.unlink()
    for stale in output_dir.glob("MINGO*_task_*_problematic_basenames.txt"):
        if stale not in expected:
            stale.unlink()
    return manifest_path


def build_from_file(
    input_path: Path = DEFAULT_INPUT,
    output_dir: Path = DEFAULT_OUTPUT,
    *,
    stations: set[str] | None = None,
) -> tuple[Path, pd.DataFrame]:
    if not input_path.is_file():
        raise FileNotFoundError(f"QA reprocessing summary not found: {input_path}")
    summary = pd.read_csv(input_path, low_memory=False)
    manifest = build_problematic_manifest(summary, stations=stations)
    manifest_path = write_problematic_outputs(manifest, output_dir)
    completed, active = reconcile_active_requests()
    print(f"Active reprocessing requests: completed={completed}, remaining={active}")
    return manifest_path, manifest


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stations = (
        {normalize_station(value) for value in args.stations}
        if args.stations else None
    )
    output, manifest = build_from_file(
        args.input.expanduser().resolve(),
        args.output_dir.expanduser().resolve(),
        stations=stations,
    )
    print(f"Problematic basenames: {len(manifest)}")
    for station, count in manifest.groupby("station").size().items():
        print(f"  {station}: {count}")
    print(f"Manifest: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(2)
