from __future__ import annotations

import csv
import gzip
import importlib.util
import os
import sys
from datetime import datetime
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "file_flow_tracker.py"
SPEC = importlib.util.spec_from_file_location("file_flow_tracker", MODULE_PATH)
tracker = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = tracker
SPEC.loader.exec_module(tracker)


BASE = "mi0126001000000"


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def read_rows(path: Path) -> list[dict[str, str]]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def roots(tmp_path: Path):
    stations = tmp_path / "stations"
    runtime = tmp_path / "runtime"
    processed = tmp_path / "processed"
    station = stations / "MINGO01"
    station.mkdir(parents=True)
    return stations, runtime, processed, station


def lake_file(station: Path, valid: bool = True) -> Path:
    path = (
        station
        / "STAGE_1_PRODUCTS"
        / "EVENT_DATA"
        / "PARQUET_LAKE"
        / f"postprocessed_{BASE}.parquet"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"PAR1payloadPAR1" if valid else b"broken")
    return path


def task_path(station: Path, task: int, queue: str, prefix: str) -> Path:
    path = (
        station
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / f"TASK_{task}"
        / "INPUT_FILES"
        / queue
        / f"{prefix}_{BASE}.parquet"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"PAR1xPAR1")
    return path


def run_tracker(stations: Path, runtime: Path, processed: Path, **kwargs):
    return tracker.run(
        stations=[1],
        stations_root=stations,
        runtime_root=runtime,
        processed_root=processed,
        selection_ranges={1: [(datetime(2026, 1, 1), datetime(2026, 1, 2))]},
        disk_check_path=stations,
        max_repair_disk_percent=101,
        **kwargs,
    )


def test_valid_lake_is_only_processed_authority(tmp_path):
    stations, runtime, processed, station = roots(tmp_path)
    lake_file(station)
    write_csv(
        station / "STAGE_1/EVENT_DATA/STEP_1/TASK_5/METADATA/task_5_metadata_status.csv",
        ["filename_base", "execution_date", "completion_fraction"],
        [[BASE, "2026-01-01", "1"]],
    )
    run_tracker(stations, runtime, processed, apply=True)
    processed_rows = read_rows(processed / "MINGO01_processed_basenames.csv")
    assert len(processed_rows) == 1
    assert processed_rows[0]["basename"] == BASE
    assert processed_rows[0]["source_csv"].endswith(f"postprocessed_{BASE}.parquet")
    row = read_rows(runtime / "MINGO01_file_flow_latest.csv")[0]
    assert row["lifecycle_state"] == "archived"
    assert row["archive_valid"] == "1"


def test_metadata_only_missing_archive_clears_guards_with_audit(tmp_path):
    stations, runtime, processed, station = roots(tmp_path)
    meta = station / "STAGE_1/EVENT_DATA/STEP_1/TASK_5/METADATA/task_5_metadata_status.csv"
    guard = station / "STAGE_0/NEW_FILES/METADATA/raw_files_brought.csv"
    write_csv(meta, ["filename_base", "execution_date"], [[BASE, "2026-01-01"]])
    write_csv(guard, ["filename", "bring_timestamp"], [[f"{BASE}.dat", "2026-01-01"]])
    run_tracker(stations, runtime, processed, apply=True)
    assert read_rows(meta) == []
    assert read_rows(guard) == []
    audit = read_rows(runtime / "removed_metadata_rows.csv.gz")
    assert {row["csv_path"] for row in audit} == {str(meta), str(guard)}


def test_completed_task5_is_requeued_and_task5_metadata_pruned(tmp_path):
    stations, runtime, processed, station = roots(tmp_path)
    source = task_path(station, 5, "COMPLETED_DIRECTORY", "fitted")
    old = datetime(2020, 1, 1).timestamp()
    os.utime(source, (old, old))
    meta = station / "STAGE_1/EVENT_DATA/STEP_1/TASK_5/METADATA/task_5_metadata_status.csv"
    write_csv(meta, ["filename_base", "execution_date"], [[BASE, "2026-01-01"]])
    run_tracker(stations, runtime, processed, apply=True)
    destination = source.parents[1] / "UNPROCESSED_DIRECTORY" / source.name
    assert destination.exists()
    assert not source.exists()
    assert read_rows(meta) == []


def test_recent_processing_is_protected(tmp_path):
    stations, runtime, processed, station = roots(tmp_path)
    source = task_path(station, 3, "PROCESSING_DIRECTORY", "calibrated")
    run_tracker(stations, runtime, processed, apply=True, stale_hours=6)
    assert source.exists()
    assert not (source.parents[1] / "UNPROCESSED_DIRECTORY" / source.name).exists()


def test_stale_processing_is_requeued(tmp_path):
    stations, runtime, processed, station = roots(tmp_path)
    source = task_path(station, 3, "PROCESSING_DIRECTORY", "calibrated")
    old = datetime(2020, 1, 1).timestamp()
    os.utime(source, (old, old))
    run_tracker(stations, runtime, processed, apply=True, stale_hours=6)
    assert (source.parents[1] / "UNPROCESSED_DIRECTORY" / source.name).exists()


def test_invalid_lake_is_quarantined(tmp_path):
    stations, runtime, processed, station = roots(tmp_path)
    source = lake_file(station, valid=False)
    run_tracker(stations, runtime, processed, apply=True)
    assert not source.exists()
    assert (runtime / "QUARANTINE/MINGO01" / source.name).exists()
    assert read_rows(processed / "MINGO01_processed_basenames.csv") == []


def test_outside_selection_is_reported_but_not_mutated(tmp_path):
    stations, runtime, processed, station = roots(tmp_path)
    outside = "mi0126003000000"
    meta = station / "STAGE_1/EVENT_DATA/STEP_1/TASK_5/METADATA/task_5_metadata_status.csv"
    write_csv(meta, ["filename_base", "execution_date"], [[outside, "2026-01-03"]])
    run_tracker(stations, runtime, processed, apply=True)
    assert read_rows(meta)[0]["filename_base"] == outside


def test_multiple_metadata_only_rows_are_removed_in_one_station_pass(tmp_path):
    stations, runtime, processed, station = roots(tmp_path)
    second = "mi0126001000100"
    meta = station / "STAGE_1/EVENT_DATA/STEP_1/TASK_5/METADATA/task_5_metadata_status.csv"
    write_csv(
        meta,
        ["filename_base", "execution_date"],
        [[BASE, "2026-01-01"], [second, "2026-01-01"]],
    )
    run_tracker(stations, runtime, processed, apply=True)
    assert read_rows(meta) == []
    audit = read_rows(runtime / "removed_metadata_rows.csv.gz")
    assert {row["filename_base"] for row in audit} == {BASE, second}


def test_recent_metadata_without_archive_is_protected(tmp_path):
    stations, runtime, processed, station = roots(tmp_path)
    meta = station / "STAGE_1/EVENT_DATA/STEP_1/TASK_5/METADATA/task_5_metadata_status.csv"
    write_csv(
        meta,
        ["filename_base", "execution_date"],
        [[BASE, datetime.now().strftime("%Y-%m-%d %H:%M:%S")]],
    )
    run_tracker(stations, runtime, processed, apply=True, stale_hours=6)
    assert read_rows(meta)[0]["filename_base"] == BASE
    row = read_rows(runtime / "MINGO01_file_flow_latest.csv")[0]
    assert row["lifecycle_state"] == "recent_metadata_pending_archive"


def test_malformed_extra_csv_fields_are_audited_and_removed(tmp_path):
    stations, runtime, processed, station = roots(tmp_path)
    meta = station / "STAGE_1/EVENT_DATA/STEP_1/TASK_5/METADATA/task_5_metadata_status.csv"
    write_csv(
        meta,
        ["filename_base", "execution_date"],
        [[BASE, "2026-01-01", "unexpected-extra-field"]],
    )
    run_tracker(stations, runtime, processed, apply=True)
    assert read_rows(meta) == []
    audit = read_rows(runtime / "removed_metadata_rows.csv.gz")
    assert len(audit) == 1
    assert "__extra_fields__" in audit[0]["row_json"]
    assert "unexpected-extra-field" in audit[0]["row_json"]
