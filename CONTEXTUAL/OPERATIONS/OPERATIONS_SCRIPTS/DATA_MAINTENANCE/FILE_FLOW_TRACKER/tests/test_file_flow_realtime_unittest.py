from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


SCRIPT_ROOT = Path(__file__).parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


deep = load_module("file_flow_tracker", SCRIPT_ROOT / "file_flow_tracker.py")
realtime = load_module("file_flow_realtime", SCRIPT_ROOT / "file_flow_realtime.py")


class FileFlowRealtimeTests(unittest.TestCase):
    def test_uses_cached_metadata_and_current_artifacts_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stations_root = root / "stations"
            runtime_root = root / "runtime"
            station = stations_root / "MINGO01"
            runtime_root.mkdir()
            base = "mi0126001000000"

            cached = {field: "" for field in deep.TRACKING_FIELDS}
            cached.update(
                {
                    "observed_at_utc": "2026-01-01T00:00:00+00:00",
                    "station": "MINGO01",
                    "filename_base": base,
                    "metadata_tasks": "0|1|2",
                    "metadata_file_count": "3",
                    "newest_metadata_timestamp_utc": (
                        "2026-01-01T00:00:00+00:00"
                    ),
                }
            )
            deep.atomic_write_csv(
                runtime_root / "MINGO01_file_flow_latest.csv",
                deep.TRACKING_FIELDS,
                [cached],
            )

            live_metadata = (
                station
                / "STAGE_1"
                / "EVENT_DATA"
                / "STEP_1"
                / "TASK_2"
                / "METADATA"
                / "task_2_metadata_execution.csv"
            )
            live_metadata.parent.mkdir(parents=True)
            live_metadata.write_text("do-not-read-or-change\n", encoding="utf-8")

            queued = (
                station
                / "STAGE_1"
                / "EVENT_DATA"
                / "STEP_1"
                / "TASK_2"
                / "INPUT_FILES"
                / "UNPROCESSED_DIRECTORY"
                / f"cleaned_{base}.parquet"
            )
            queued.parent.mkdir(parents=True)
            queued.write_bytes(b"PAR1payloadPAR1")

            ranges = {
                1: [(datetime(2026, 1, 1), datetime(2026, 1, 2))]
            }
            realtime.run(
                stations=[1],
                stations_root=stations_root,
                runtime_root=runtime_root,
                selection_ranges=ranges,
            )
            with (
                runtime_root / "MINGO01_file_flow_realtime.csv"
            ).open(newline="", encoding="utf-8") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["lifecycle_state"], "queued_task_2")
            self.assertEqual(row["metadata_tasks"], "0|1|2")
            self.assertEqual(row["metadata_file_count"], "3")
            self.assertEqual(row["snapshot_source"], "realtime_cached_metadata")

            queued.unlink()
            lake = (
                station
                / "STAGE_1_PRODUCTS"
                / "EVENT_DATA"
                / "PARQUET_LAKE"
                / f"postprocessed_{base}.parquet"
            )
            lake.parent.mkdir(parents=True)
            lake.write_bytes(b"PAR1payloadPAR1")
            realtime.run(
                stations=[1],
                stations_root=stations_root,
                runtime_root=runtime_root,
                selection_ranges=ranges,
            )
            with (
                runtime_root / "MINGO01_file_flow_realtime.csv"
            ).open(newline="", encoding="utf-8") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["lifecycle_state"], "archived")
            self.assertEqual(row["archive_valid"], "1")
            self.assertEqual(
                live_metadata.read_text(encoding="utf-8"),
                "do-not-read-or-change\n",
            )


if __name__ == "__main__":
    unittest.main()
