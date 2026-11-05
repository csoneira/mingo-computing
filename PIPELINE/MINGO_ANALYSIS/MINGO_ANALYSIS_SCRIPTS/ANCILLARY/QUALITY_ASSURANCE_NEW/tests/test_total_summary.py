from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[6]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.ANCILLARY.QUALITY_ASSURANCE_NEW.qa_core.total_summary import _build_reprocessing_quality_table, build_total_summary  # noqa: E402


class TotalSummaryTests(unittest.TestCase):
    def test_warning_only_status_does_not_trigger_reprocessing(self) -> None:
        wide = pd.DataFrame({
            "station_name": ["MINGO01"],
            "filename_base": ["mi0124074013648"],
            "STEP_1_CALIBRATIONS::TASK_2::P1_s1_T_sum": ["insufficient_reference"],
        })
        result = _build_reprocessing_quality_table(wide)
        self.assertEqual(result.loc[0, "quality_status"], "pass")
        self.assertEqual(result.loc[0, "failed_quality_columns"], "")

    def test_total_summary_respects_root_date_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            qa_root = Path(tmp_dir)
            files_dir = qa_root / "STEPS" / "STEP_1_SAMPLE" / "OUTPUTS" / "MINGO01" / "FILES"
            files_dir.mkdir(parents=True, exist_ok=True)

            pd.DataFrame(
                {
                    "filename_base": ["mi0124074013648", "mi0124267001616"],
                    "qa_status": ["pass", "pass"],
                    "qa_timestamp": ["2024-03-14 01:36:48", "2024-09-23 00:16:16"],
                    "plot_timestamp": ["2024-03-14 01:36:48", "2024-09-23 00:16:16"],
                    "step_name": ["STEP_1_SAMPLE", "STEP_1_SAMPLE"],
                    "step_display_name": ["sample", "sample"],
                    "qa_evaluated_columns": [1, 1],
                    "qa_passed_columns": [1, 0],
                    "qa_failed_columns": [0, 1],
                    "qa_warning_columns": [0, 0],
                    "qa_pass_fraction": [1.0, 0.0],
                }
            ).to_csv(files_dir / "MINGO01_sample_step_summary.csv", index=False)

            pd.DataFrame(
                {
                    "filename_base": ["mi0124074013648", "mi0124267001616"],
                    "evaluation_column": ["metric_a", "metric_a"],
                    "source_column": ["metric_a", "metric_a"],
                    "status": ["pass", "fail"],
                    "reason": ["", "out_of_range"],
                    "task_id": [7, 7],
                    "step_name": ["STEP_1_SAMPLE", "STEP_1_SAMPLE"],
                    "step_display_name": ["sample", "sample"],
                    "plot_timestamp": ["2024-03-14 01:36:48", "2024-09-23 00:16:16"],
                }
            ).to_csv(files_dir / "MINGO01_sample_column_status.csv", index=False)

            build_total_summary(
                qa_root,
                root_config={
                    "stations": [1],
                    "date_range": {"start": "2024-02", "end": "2024-07"},
                    "date_range_excluded_stations": ["MINGO00"],
                },
                pipeline_steps=[
                    {
                        "step_name": "STEP_1_SAMPLE",
                        "display_name": "sample",
                        "enabled": True,
                    }
                ],
                stations_override=["MINGO01"],
            )

            station_files_dir = qa_root / "TOTAL_SUMMARY" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / "MINGO01" / "OUTPUTS" / "FILES"
            step_df = pd.read_csv(station_files_dir / "MINGO01_total_step_summary.csv")
            long_df = pd.read_csv(station_files_dir / "MINGO01_total_quality_long.csv")

            self.assertEqual(step_df["filename_base"].tolist(), ["mi0124074013648"])
            self.assertEqual(long_df["filename_base"].tolist(), ["mi0124074013648"])

            step_ts = pd.to_datetime(step_df["plot_timestamp"], errors="coerce")
            long_ts = pd.to_datetime(long_df["plot_timestamp"], errors="coerce")
            self.assertTrue((step_ts <= pd.Timestamp("2024-07-31 23:59:59.999999")).all())
            self.assertTrue((long_ts <= pd.Timestamp("2024-07-31 23:59:59.999999")).all())

    def test_total_summary_uses_step_outputs_not_task_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            qa_root = Path(tmp_dir)
            step_output_dir = qa_root / "STEPS" / "STEP_1_SAMPLE" / "OUTPUTS" / "MINGO01" / "FILES"
            task_output_dir = qa_root / "STEPS" / "STEP_1_SAMPLE" / "TASK_7" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / "MINGO01" / "OUTPUTS" / "FILES"
            step_output_dir.mkdir(parents=True, exist_ok=True)
            task_output_dir.mkdir(parents=True, exist_ok=True)

            pd.DataFrame(
                {
                    "filename_base": ["mi0124074013648"],
                    "qa_status": ["pass"],
                    "qa_timestamp": ["2024-03-14 01:36:48"],
                    "plot_timestamp": ["2024-03-14 01:36:48"],
                    "step_name": ["STEP_1_SAMPLE"],
                    "step_display_name": ["sample"],
                    "qa_evaluated_columns": [0],
                    "qa_passed_columns": [0],
                    "qa_failed_columns": [0],
                    "qa_warning_columns": [0],
                    "qa_pass_fraction": [pd.NA],
                }
            ).to_csv(step_output_dir / "MINGO01_sample_step_summary.csv", index=False)

            pd.DataFrame(
                {
                    "filename_base": ["mi0124267001616"],
                    "qa_status": ["pass"],
                    "qa_timestamp": ["2024-09-23 00:16:16"],
                }
            ).to_csv(task_output_dir / "MINGO01_task_7_sample_pass.csv", index=False)

            pd.DataFrame(
                {
                    "filename_base": ["mi0124267001616"],
                    "evaluation_column": ["metric_a"],
                    "source_column": ["metric_a"],
                    "status": ["fail"],
                    "reason": ["out_of_range"],
                }
            ).to_csv(task_output_dir / "sample_column_evaluations.csv", index=False)

            build_total_summary(
                qa_root,
                root_config={"stations": [1]},
                pipeline_steps=[
                    {
                        "step_name": "STEP_1_SAMPLE",
                        "display_name": "sample",
                        "enabled": True,
                    }
                ],
                stations_override=["MINGO01"],
            )

            station_files_dir = qa_root / "TOTAL_SUMMARY" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / "MINGO01" / "OUTPUTS" / "FILES"
            step_df = pd.read_csv(station_files_dir / "MINGO01_total_step_summary.csv")

            self.assertEqual(step_df["filename_base"].tolist(), ["mi0124074013648"])

    def test_total_summary_writes_reprocessing_quality_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            qa_root = Path(tmp_dir)
            step_output_dir = qa_root / "STEPS" / "STEP_1_SAMPLE" / "OUTPUTS" / "MINGO01" / "FILES"
            step_output_dir.mkdir(parents=True, exist_ok=True)

            pd.DataFrame(
                {
                    "filename_base": ["mi0124074013648", "mi0124074030910"],
                    "qa_status": ["fail", "pass"],
                    "qa_timestamp": ["2024-03-14 01:36:48", "2024-03-14 03:09:10"],
                    "plot_timestamp": ["2024-03-14 01:36:48", "2024-03-14 03:09:10"],
                    "step_name": ["STEP_1_SAMPLE", "STEP_1_SAMPLE"],
                    "step_display_name": ["sample", "sample"],
                    "qa_evaluated_columns": [2, 2],
                    "qa_passed_columns": [1, 2],
                    "qa_failed_columns": [1, 0],
                    "qa_warning_columns": [0, 0],
                    "qa_pass_fraction": [0.5, 1.0],
                }
            ).to_csv(step_output_dir / "MINGO01_sample_step_summary.csv", index=False)

            pd.DataFrame(
                {
                    "filename_base": ["mi0124074013648", "mi0124074013648", "mi0124074030910", "mi0124074030910"],
                    "evaluation_column": ["metric_a", "metric_b", "metric_a", "metric_b"],
                    "source_column": ["metric_a", "metric_b", "metric_a", "metric_b"],
                    "status": ["pass", "fail", "pass", "pass"],
                    "reason": ["", "out_of_range", "", ""],
                    "task_id": [7, 7, 7, 7],
                    "step_name": ["STEP_1_SAMPLE"] * 4,
                    "step_display_name": ["sample"] * 4,
                    "plot_timestamp": ["2024-03-14 01:36:48", "2024-03-14 01:36:48", "2024-03-14 03:09:10", "2024-03-14 03:09:10"],
                    "execution_timestamp": ["2026-04-22 10:00:00", "2026-04-22 10:00:00", "2026-04-22 10:05:00", "2026-04-22 10:05:00"],
                }
            ).to_csv(step_output_dir / "MINGO01_sample_column_status.csv", index=False)

            build_total_summary(
                qa_root,
                root_config={"stations": [1]},
                pipeline_steps=[
                    {
                        "step_name": "STEP_1_SAMPLE",
                        "display_name": "sample",
                        "enabled": True,
                    }
                ],
                stations_override=["MINGO01"],
            )

            global_files_dir = qa_root / "TOTAL_SUMMARY" / "OUTPUTS" / "FILES"
            reprocessing_df = pd.read_csv(global_files_dir / "qa_all_stations_reprocessing_quality.csv", keep_default_na=False)

            self.assertEqual(
                reprocessing_df.columns.tolist(),
                [
                    "station_name",
                    "filename_base",
                    "plot_timestamp",
                    "quality_status",
                    "failed_quality_columns",
                    "failed_quality_versions",
                ],
            )
            self.assertEqual(reprocessing_df.loc[0, "quality_status"], "fail")
            self.assertEqual(reprocessing_df.loc[0, "failed_quality_columns"], "STEP_1_SAMPLE::TASK_7::metric_b")
            self.assertEqual(
                reprocessing_df.loc[0, "failed_quality_versions"],
                "STEP_1_SAMPLE::TASK_7::metric_b@2026-04-22 10:00:00",
            )
            self.assertEqual(reprocessing_df.loc[1, "quality_status"], "pass")
            self.assertEqual(reprocessing_df.loc[1, "failed_quality_columns"], "")
            self.assertEqual(reprocessing_df.loc[1, "failed_quality_versions"], "")


if __name__ == "__main__":
    unittest.main()
