#!/usr/bin/env python3

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd


HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


purge = load_module("reprocess_problematic_basenames", "reprocess_problematic_basenames.py")
problematic = load_module("build_problematic_basename_lists", "build_problematic_basename_lists.py")
orchestrator = load_module("orchestrate_quality_assurance", "orchestrate_quality_assurance.py")


class ProductMetadataPublicationTests(unittest.TestCase):
    def test_only_latest_rows_with_valid_lake_parquets_are_published(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            station = (
                root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / "MINGO01"
            )
            source = (
                station / "STAGE_1" / "EVENT_DATA" / "STEP_1" / "TASK_2"
                / "METADATA" / "task_2_metadata_calibration.csv"
            )
            source.parent.mkdir(parents=True)
            completed = "mi0126010101010"
            incomplete = "mi0126010102020"
            with source.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["filename_base", "execution_timestamp", "calibration"])
                writer.writerow([completed, "2026-01-01_10.00.00", "old"])
                writer.writerow([incomplete, "2026-01-01_11.00.00", "not-final"])
                writer.writerow([completed, "2026-01-01_12.00.00", "latest"])

            lake = station / "STAGE_1_PRODUCTS" / "EVENT_DATA" / "PARQUET_LAKE"
            lake.mkdir(parents=True)
            (lake / f"postprocessed_{completed}.parquet").write_bytes(b"PAR1payloadPAR1")
            (lake / f"postprocessed_{incomplete}.parquet").write_bytes(b"incomplete")

            orchestrator._publish_stage1_product_metadata(
                root, {"stations": [1]}, None
            )
            product = (
                station / "STAGE_1_PRODUCTS" / "EVENT_DATA" / "METADATA"
                / "TASK_2" / source.name
            )
            with product.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(
                rows,
                [
                    ["filename_base", "execution_timestamp", "calibration"],
                    [completed, "2026-01-01_12.00.00", "latest"],
                ],
            )

            # Removing the final archive removes the row on the next snapshot.
            (lake / f"postprocessed_{completed}.parquet").unlink()
            orchestrator._publish_stage1_product_metadata(
                root, {"stations": [1]}, None
            )
            with product.open(newline="", encoding="utf-8") as handle:
                self.assertEqual(
                    list(csv.reader(handle)),
                    [["filename_base", "execution_timestamp", "calibration"]],
                )


class PurgeTaskChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = "mi0124074013648"
        self.other = "mi0124074030910"
        self.step = (
            self.root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / "MINGO01"
            / "STAGE_1" / "EVENT_DATA" / "STEP_1"
        )
        for task in range(2, 6):
            task_root = self.step / f"TASK_{task}"
            (task_root / "INPUT_FILES" / "UNPROCESSED_DIRECTORY").mkdir(parents=True)
            (task_root / "INPUT_FILES" / "COMPLETED_DIRECTORY").mkdir(parents=True)
            (task_root / "OUTPUT_FILES").mkdir(parents=True)
            (task_root / "METADATA" / "OPERATION").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_metadata(self, task: int) -> Path:
        path = self.step / f"TASK_{task}" / "METADATA" / f"task_{task}_metadata_execution.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["filename_base", "value"])
            writer.writerow([self.base, "bad"])
            writer.writerow([self.other, "keep"])
        index = path.parent / "OPERATION" / f"{path.name}.filename_base.index"
        index.write_text(f"{self.base}\n{self.other}\n", encoding="utf-8")
        return path

    def test_apply_requeues_start_input_and_clears_downstream(self) -> None:
        source = (
            self.step / "TASK_2" / "INPUT_FILES" / "COMPLETED_DIRECTORY"
            / f"cleaned_{self.base}.parquet"
        )
        source.write_text("source", encoding="utf-8")
        task2_output = self.step / "TASK_2" / "OUTPUT_FILES" / f"calibrated_{self.base}.parquet"
        task3_output = self.step / "TASK_3" / "OUTPUT_FILES" / f"listed_{self.base}.parquet"
        task2_output.write_text("derived", encoding="utf-8")
        task3_output.write_text("derived", encoding="utf-8")
        metadata_paths = [self.write_metadata(task) for task in (2, 3)]

        result = purge.main([
            "--station", "1", "--task", "2", "--basename", self.base,
            "--repo-root", str(self.root), "--apply",
        ])
        self.assertEqual(result, 0)
        queued = (
            self.step / "TASK_2" / "INPUT_FILES" / "UNPROCESSED_DIRECTORY"
            / source.name
        )
        self.assertTrue(queued.is_file())
        self.assertFalse(source.exists())
        self.assertFalse(task2_output.exists())
        self.assertFalse(task3_output.exists())
        for metadata_path in metadata_paths:
            with metadata_path.open(encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows, [["filename_base", "value"], [self.other, "keep"]])
            index = metadata_path.parent / "OPERATION" / f"{metadata_path.name}.filename_base.index"
            self.assertEqual(index.read_text(encoding="utf-8"), f"{self.other}\n")

    def test_dry_run_changes_nothing(self) -> None:
        source = (
            self.step / "TASK_2" / "INPUT_FILES" / "COMPLETED_DIRECTORY"
            / f"cleaned_{self.base}.parquet"
        )
        source.write_text("source", encoding="utf-8")
        metadata_path = self.write_metadata(2)
        purge.main([
            "--station", "MINGO01", "--task", "2", "--basename-file",
            str(metadata_path), "--repo-root", str(self.root),
        ])
        self.assertTrue(source.exists())
        self.assertIn(self.base, metadata_path.read_text(encoding="utf-8"))


class ProblematicBasenameListTests(unittest.TestCase):
    def test_only_qa_failures_and_earliest_failed_task_are_selected(self) -> None:
        summary = pd.DataFrame([
            {
                "station_name": "MINGO01",
                "filename_base": "mi0124074013648",
                "quality_status": "fail",
                "failed_quality_columns": (
                    "STEP_3_DEEP_FILTER::TASK_3::q_dif_sum_low;"
                    "STEP_1_CALIBRATIONS::TASK_2::P1_s1_T_sum"
                ),
            },
            {
                "station_name": "MINGO01",
                "filename_base": "mi0124074030910",
                "quality_status": "pass",
                "failed_quality_columns": "",
            },
        ])
        manifest = problematic.build_problematic_manifest(summary)
        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest.loc[0, "basename"], "mi0124074013648")
        self.assertEqual(manifest.loc[0, "start_task"], 2)


if __name__ == "__main__":
    unittest.main()
