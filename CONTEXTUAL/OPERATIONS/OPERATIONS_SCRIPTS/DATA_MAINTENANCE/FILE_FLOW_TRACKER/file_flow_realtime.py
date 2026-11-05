#!/usr/bin/env python3
"""Build lightweight per-minute file-flow snapshots without scanning metadata.

The 15-minute ``file_flow_tracker.py`` pass remains the deep reconciliation
authority. This updater treats its station CSVs as a metadata cache and scans
only the live Stage 0/Stage 1 filesystem positions and Parquet Lake. It never
repairs, moves, or removes pipeline data.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import file_flow_tracker as deep


REALTIME_FIELDS = deep.TRACKING_FIELDS + (
    "snapshot_source",
    "deep_snapshot_observed_at_utc",
    "deep_snapshot_age_seconds",
)

REALTIME_SUMMARY_FIELDS = (
    "observed_at_utc",
    "station",
    "tracked_files",
    "valid_archives",
    "active_or_queued_files",
    "anomalous_files",
    "deep_snapshot_observed_at_utc",
    "deep_snapshot_age_seconds",
    "scan_seconds",
)


def _parse_iso_timestamp(value: str) -> float:
    text = (value or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _cached_observations(
    station: int,
    runtime_root: Path,
) -> tuple[dict[str, deep.FileObservation], str, float]:
    """Restore metadata facts from the last deep station snapshot."""
    snapshot = runtime_root / f"MINGO{station:02d}_file_flow_latest.csv"
    observations: dict[str, deep.FileObservation] = {}
    deep_observed_at = ""
    deep_observed_epoch = 0.0

    try:
        with snapshot.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                base = deep.basename_from_text(row.get("filename_base", ""))
                if base is None:
                    continue
                obs = deep.FileObservation(station=station, base=base)
                for raw_task in row.get("metadata_tasks", "").split("|"):
                    if raw_task.isdigit():
                        obs.metadata_tasks.add(int(raw_task))
                try:
                    metadata_count = max(
                        0, int(row.get("metadata_file_count", "0") or 0)
                    )
                except ValueError:
                    metadata_count = 0
                # classify() needs only truthiness. Keep the exact count as a
                # scalar instead of allocating many synthetic Path objects.
                if metadata_count:
                    obs.metadata_paths.add(Path("cached_metadata"))
                obs.cached_metadata_count = metadata_count
                obs.newest_metadata_timestamp = _parse_iso_timestamp(
                    row.get("newest_metadata_timestamp_utc", "")
                )
                observations[base] = obs

                row_observed = row.get("observed_at_utc", "")
                row_epoch = _parse_iso_timestamp(row_observed)
                if row_epoch >= deep_observed_epoch:
                    deep_observed_epoch = row_epoch
                    deep_observed_at = row_observed
    except (OSError, csv.Error, UnicodeError):
        pass

    return observations, deep_observed_at, deep_observed_epoch



def _get_observation(
    observations: dict[str, deep.FileObservation],
    station: int,
    base: str,
) -> deep.FileObservation:
    return observations.setdefault(
        base, deep.FileObservation(station=station, base=base)
    )


def _add_directory_artifacts(
    observations: dict[str, deep.FileObservation],
    station: int,
    directory: Path,
    *,
    kind: str,
    task: int | None,
    queue: str = "",
) -> None:
    for path in deep.iter_regular_files(directory):
        base = deep.basename_from_text(path.name)
        if base is None:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        _get_observation(observations, station, base).artifacts.append(
            deep.Artifact(path, kind, task, queue, mtime)
        )


def scan_live_artifacts(
    station: int,
    *,
    stations_root: Path = deep.STATIONS_ROOT,
    runtime_root: Path = deep.RUNTIME_ROOT,
    active_bases: set[str] | None = None,
) -> tuple[dict[str, deep.FileObservation], str, float]:
    """Scan pipeline artifacts using the deep CSV as the metadata cache."""
    observations, deep_observed_at, deep_observed_epoch = _cached_observations(
        station, runtime_root
    )
    station_root = stations_root / f"MINGO{station:02d}"

    _add_directory_artifacts(
        observations,
        station,
        station_root / "STAGE_0_TO_1",
        kind="stage0",
        task=None,
    )

    step = station_root / "STAGE_1" / "EVENT_DATA" / "STEP_1"
    for task in range(6):
        task_root = step / f"TASK_{task}"
        for queue in deep.QUEUE_NAMES:
            _add_directory_artifacts(
                observations,
                station,
                task_root / "INPUT_FILES" / queue,
                kind="input",
                task=task,
                queue=queue,
            )
        _add_directory_artifacts(
            observations,
            station,
            task_root / "OUTPUT_FILES",
            kind="output",
            task=task,
        )

    lake = station_root / "STAGE_1_PRODUCTS" / "EVENT_DATA" / "PARQUET_LAKE"
    for path in deep.iter_regular_files(lake):
        base = deep.basename_from_text(path.name)
        if base is None:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        valid = deep.is_valid_parquet(path)
        obs = _get_observation(observations, station, base)
        obs.archive_present = True
        obs.archive_valid = obs.archive_valid or valid
        obs.artifacts.append(
            deep.Artifact(
                path,
                "lake_valid" if valid else "lake_invalid",
                5,
                mtime=mtime,
            )
        )

    active = active_bases if active_bases is not None else deep.load_active_bases()
    for base in active:
        if base in observations:
            observations[base].active_reprocessing = True

    return observations, deep_observed_at, deep_observed_epoch


def run(
    *,
    stations: Sequence[int],
    stale_hours: float = 6.0,
    stations_root: Path = deep.STATIONS_ROOT,
    runtime_root: Path = deep.RUNTIME_ROOT,
    selection_ranges: dict[
        int, Sequence[tuple[datetime | None, datetime | None]]
    ]
    | None = None,
) -> dict[str, int | float]:
    """Refresh real-time CSVs without mutating pipeline artifacts or metadata."""
    started = time.monotonic()
    runtime_root.mkdir(parents=True, exist_ok=True)
    lock_path = runtime_root / "file_flow_realtime.lock"
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("another file_flow_realtime instance is already running")

        ranges_by_station = selection_ranges
        if ranges_by_station is None:
            try:
                ranges_by_station = deep.load_selection_ranges(stations)
            except Exception:
                ranges_by_station = {station: () for station in stations}

        active = deep.load_active_bases()
        observed_at = datetime.now(timezone.utc).isoformat()
        observed_epoch = datetime.now(timezone.utc).timestamp()
        summary_rows: list[dict[str, object]] = []
        totals: dict[str, int | float] = {
            "files": 0,
            "archived": 0,
            "anomalies": 0,
            "seconds": 0.0,
        }

        for station in stations:
            station_started = time.monotonic()
            observations, deep_observed_at, deep_observed_epoch = scan_live_artifacts(
                station,
                stations_root=stations_root,
                runtime_root=runtime_root,
                active_bases=active,
            )
            deep_age = (
                max(0.0, observed_epoch - deep_observed_epoch)
                if deep_observed_epoch
                else 0.0
            )
            ranges = ranges_by_station.get(station, ()) if ranges_by_station else ()
            rows: list[dict[str, object]] = []
            active_or_queued = 0
            station_anomalies = 0
            station_archived = 0

            for base, obs in sorted(observations.items()):
                obs.event_time = deep.event_time_from_base(base)
                obs.in_selected_range = deep.within_ranges(obs.event_time, ranges)
                state, recommended, highest = deep.classify(
                    obs, observed_epoch, stale_hours * 3600.0
                )
                row = deep.tracking_row(
                    obs,
                    observed_at=observed_at,
                    state=state,
                    recommended=recommended,
                    highest=highest,
                )
                row["metadata_file_count"] = getattr(
                    obs, "cached_metadata_count", len(obs.metadata_paths)
                )
                row.update(
                    {
                        "snapshot_source": "realtime_cached_metadata",
                        "deep_snapshot_observed_at_utc": deep_observed_at,
                        "deep_snapshot_age_seconds": round(deep_age, 3),
                    }
                )
                rows.append(row)
                station_archived += int(obs.archive_valid)
                station_anomalies += int(bool(obs.anomalies))
                active_or_queued += int(
                    state.startswith(
                        (
                            "processing_",
                            "queued_",
                            "stage0_",
                            "active_",
                            "in_flight_",
                            "stale_processing_",
                        )
                    )
                )

            deep.atomic_write_csv(
                runtime_root / f"MINGO{station:02d}_file_flow_realtime.csv",
                REALTIME_FIELDS,
                rows,
            )
            station_seconds = time.monotonic() - station_started
            summary_rows.append(
                {
                    "observed_at_utc": observed_at,
                    "station": f"MINGO{station:02d}",
                    "tracked_files": len(rows),
                    "valid_archives": station_archived,
                    "active_or_queued_files": active_or_queued,
                    "anomalous_files": station_anomalies,
                    "deep_snapshot_observed_at_utc": deep_observed_at,
                    "deep_snapshot_age_seconds": round(deep_age, 3),
                    "scan_seconds": round(station_seconds, 3),
                }
            )
            totals["files"] += len(rows)
            totals["archived"] += station_archived
            totals["anomalies"] += station_anomalies

        deep.atomic_write_csv(
            runtime_root / "realtime_summary.csv",
            REALTIME_SUMMARY_FIELDS,
            summary_rows,
        )
        totals["seconds"] = round(time.monotonic() - started, 3)
        return totals


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stations", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    parser.add_argument("--stale-hours", type=float, default=6.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        totals = run(stations=args.stations, stale_hours=args.stale_hours)
    except RuntimeError as exc:
        if "another file_flow_realtime instance" in str(exc):
            print(f"file-flow realtime: skipped ({exc})")
            return 0
        raise
    print(
        "file-flow realtime: "
        + ", ".join(f"{key}={value}" for key, value in totals.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
