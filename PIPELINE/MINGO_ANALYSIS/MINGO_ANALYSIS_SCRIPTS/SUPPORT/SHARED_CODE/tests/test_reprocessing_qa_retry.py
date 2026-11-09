from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[6]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE import reprocessing_qa_retry  # noqa: E402
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.reprocessing_qa_retry import build_retry_manifest, mark_retry_admitted  # noqa: E402


class ReprocessingQARetryTests(unittest.TestCase):
    def test_relative_source_csv_resolves_from_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_path = root / "config.yaml"
            source_csv = root / "qa.csv"
            config_path.write_text(
                "qa_retry:\n  enabled: true\n  source_csv: qa.csv\n  selectors: []\n",
                encoding="utf-8",
            )
            pd.DataFrame(columns=["station_name", "filename_base", "plot_timestamp", "quality_status"]).to_csv(
                source_csv, index=False
            )
            with patch.object(reprocessing_qa_retry, "get_repo_root", return_value=root):
                summary = build_retry_manifest(
                    config_paths=[config_path],
                    station=1,
                    clean_csv=root / "clean.csv",
                    output_csv=root / "manifest.csv",
                    state_csv=root / "state.csv",
                    now_timestamp="2026-10-21 10:00:00",
                )
            self.assertEqual(summary["manifest_rows"], 0)

    def test_manifest_reopens_only_when_failed_versions_are_newer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_path = root / "config.yaml"
            source_csv = root / "qa.csv"
            clean_csv = root / "clean.csv"
            manifest_csv = root / "manifest.csv"
            state_csv = root / "state.csv"

            config_path.write_text(
                "\n".join(
                    [
                        "qa_retry:",
                        "  enabled: true",
                        f"  source_csv: {source_csv}",
                        "  selectors:",
                        "    - id: calibration_time",
                        "      target_stations: [1]",
                        "      qa_stations: [1]",
                        "      quality_statuses: [fail]",
                        "      failed_columns_any:",
                        "        - STEP_1_CALIBRATIONS::TASK_2::*_T_sum",
                    ]
                ),
                encoding="utf-8",
            )

            pd.DataFrame({"basename": ["mi0124074013648", "mi0124074030910"]}).to_csv(clean_csv, index=False)
            pd.DataFrame(
                {
                    "station_name": ["MINGO01"],
                    "filename_base": ["mi0124074013648"],
                    "plot_timestamp": ["2024-03-14 01:36:48"],
                    "quality_status": ["fail"],
                    "failed_quality_columns": ["STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum"],
                    "failed_quality_versions": ["STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum@2026-04-22 11:00:00"],
                }
            ).to_csv(source_csv, index=False)

            summary = build_retry_manifest(
                config_paths=[config_path],
                station=1,
                clean_csv=clean_csv,
                output_csv=manifest_csv,
                state_csv=state_csv,
                now_timestamp="2026-04-22 12:00:00",
            )
            self.assertEqual(summary["manifest_rows"], 1)

            manifest_df = pd.read_csv(manifest_csv, keep_default_na=False)
            self.assertEqual(manifest_df["basename"].tolist(), ["mi0124074013648"])

            admitted = mark_retry_admitted(
                state_csv=state_csv,
                basename="mi0124074013648",
                admitted_at="2026-04-22 12:10:00",
            )
            self.assertEqual(admitted["updated_rows"], 1)

            summary = build_retry_manifest(
                config_paths=[config_path],
                station=1,
                clean_csv=clean_csv,
                output_csv=manifest_csv,
                state_csv=state_csv,
                now_timestamp="2026-04-22 12:20:00",
            )
            self.assertEqual(summary["manifest_rows"], 0)

            pd.DataFrame(
                {
                    "station_name": ["MINGO01"],
                    "filename_base": ["mi0124074013648"],
                    "plot_timestamp": ["2024-03-14 01:36:48"],
                    "quality_status": ["fail"],
                    "failed_quality_columns": ["STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum"],
                    "failed_quality_versions": ["STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum@2026-04-22 11:00:00"],
                }
            ).to_csv(source_csv, index=False)

            summary = build_retry_manifest(
                config_paths=[config_path],
                station=1,
                clean_csv=clean_csv,
                output_csv=manifest_csv,
                state_csv=state_csv,
                now_timestamp="2026-04-22 12:30:00",
            )
            self.assertEqual(summary["manifest_rows"], 0)

            pd.DataFrame(
                {
                    "station_name": ["MINGO01"],
                    "filename_base": ["mi0124074013648"],
                    "plot_timestamp": ["2024-03-14 01:36:48"],
                    "quality_status": ["pass"],
                    "failed_quality_columns": [""],
                    "failed_quality_versions": [""],
                }
            ).to_csv(source_csv, index=False)

            pd.DataFrame(
                {
                    "station_name": ["MINGO01"],
                    "filename_base": ["mi0124074013648"],
                    "plot_timestamp": ["2024-03-14 01:36:48"],
                    "quality_status": ["fail"],
                    "failed_quality_columns": ["STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum"],
                    "failed_quality_versions": ["STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum@2026-04-22 12:35:00"],
                }
            ).to_csv(source_csv, index=False)

            summary = build_retry_manifest(
                config_paths=[config_path],
                station=1,
                clean_csv=clean_csv,
                output_csv=manifest_csv,
                state_csv=state_csv,
                now_timestamp="2026-04-22 12:40:00",
            )
            self.assertEqual(summary["manifest_rows"], 1)

    def test_manifest_reopens_when_failure_signature_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_path = root / "config.yaml"
            source_csv = root / "qa.csv"
            clean_csv = root / "clean.csv"
            manifest_csv = root / "manifest.csv"
            state_csv = root / "state.csv"

            config_path.write_text(
                "\n".join(
                    [
                        "qa_retry:",
                        "  enabled: true",
                        f"  source_csv: {source_csv}",
                        "  selectors:",
                        "    - id: any_fail",
                        "      target_stations: [1]",
                        "      qa_stations: [1]",
                        "      quality_statuses: [fail]",
                        "      failed_columns_any:",
                        "        - '*'",
                    ]
                ),
                encoding="utf-8",
            )

            pd.DataFrame({"basename": ["mi0124074013648"]}).to_csv(clean_csv, index=False)
            pd.DataFrame(
                {
                    "station_name": ["MINGO01"],
                    "filename_base": ["mi0124074013648"],
                    "plot_timestamp": ["2024-03-14 01:36:48"],
                    "quality_status": ["fail"],
                    "failed_quality_columns": ["STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum"],
                    "failed_quality_versions": ["STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum@2026-04-22 13:00:00"],
                }
            ).to_csv(source_csv, index=False)

            build_retry_manifest(
                config_paths=[config_path],
                station=1,
                clean_csv=clean_csv,
                output_csv=manifest_csv,
                state_csv=state_csv,
                now_timestamp="2026-04-22 13:00:00",
            )
            mark_retry_admitted(
                state_csv=state_csv,
                basename="mi0124074013648",
                admitted_at="2026-04-22 13:01:00",
            )

            pd.DataFrame(
                {
                    "station_name": ["MINGO01"],
                    "filename_base": ["mi0124074013648"],
                    "plot_timestamp": ["2024-03-14 01:36:48"],
                    "quality_status": ["fail"],
                    "failed_quality_columns": ["STEP_1_CALIBRATIONS::TASK_2::P4_s4_T_sum"],
                    "failed_quality_versions": ["STEP_1_CALIBRATIONS::TASK_2::P4_s4_T_sum@2026-04-22 13:10:00"],
                }
            ).to_csv(source_csv, index=False)

            summary = build_retry_manifest(
                config_paths=[config_path],
                station=1,
                clean_csv=clean_csv,
                output_csv=manifest_csv,
                state_csv=state_csv,
                now_timestamp="2026-04-22 13:10:00",
            )

            self.assertEqual(summary["manifest_rows"], 1)
            manifest_df = pd.read_csv(manifest_csv, keep_default_na=False)
            self.assertEqual(
                manifest_df.loc[0, "failed_quality_columns"],
                "STEP_1_CALIBRATIONS::TASK_2::P4_s4_T_sum",
            )

    def test_manifest_tolerates_malformed_state_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_path = root / "config.yaml"
            source_csv = root / "qa.csv"
            clean_csv = root / "clean.csv"
            manifest_csv = root / "manifest.csv"
            state_csv = root / "state.csv"

            config_path.write_text(
                "\n".join(
                    [
                        "qa_retry:",
                        "  enabled: true",
                        f"  source_csv: {source_csv}",
                        "  selectors:",
                        "    - id: any_fail",
                        "      target_stations: [1]",
                        "      qa_stations: [1]",
                        "      quality_statuses: [fail]",
                        "      failed_columns_any:",
                        "        - '*'",
                    ]
                ),
                encoding="utf-8",
            )

            pd.DataFrame({"basename": ["mi0124074013648"]}).to_csv(clean_csv, index=False)
            pd.DataFrame(
                {
                    "station_name": ["MINGO01"],
                    "filename_base": ["mi0124074013648"],
                    "plot_timestamp": ["2024-03-14 01:36:48"],
                    "quality_status": ["fail"],
                    "failed_quality_columns": ["STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum"],
                    "failed_quality_versions": ["STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum@2026-04-22 11:00:00"],
                }
            ).to_csv(source_csv, index=False)

            state_csv.write_text(
                "\n".join(
                    [
                        ",".join(
                            [
                                "basename",
                                "target_station",
                                "selector_id",
                                "qa_station",
                                "quality_status",
                                "plot_timestamp",
                                "failed_quality_columns",
                                "failed_quality_versions",
                                "first_seen_at",
                                "last_seen_at",
                                "admitted_at",
                                "is_active",
                            ]
                        ),
                        "mi0124074013648,MINGO01,any_fail,MINGO01,fail,2024-03-14 01:36:48,STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum,STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum@2026-04-22 11:00:00,2026-04-22 12:00:00,2026-04-22 12:05:00,,1",
                        "broken,row,with,too,many,columns,mi0124074013648,extra,data,that,should,be,ignored,entirely",
                    ]
                ),
                encoding="utf-8",
            )

            summary = build_retry_manifest(
                config_paths=[config_path],
                station=1,
                clean_csv=clean_csv,
                output_csv=manifest_csv,
                state_csv=state_csv,
                now_timestamp="2026-04-22 12:10:00",
            )

            self.assertEqual(summary["manifest_rows"], 1)
            manifest_df = pd.read_csv(manifest_csv, keep_default_na=False)
            self.assertEqual(manifest_df["basename"].tolist(), ["mi0124074013648"])

            rewritten_state = pd.read_csv(state_csv, keep_default_na=False)
            self.assertEqual(rewritten_state["basename"].tolist(), ["mi0124074013648"])


if __name__ == "__main__":
    unittest.main()
