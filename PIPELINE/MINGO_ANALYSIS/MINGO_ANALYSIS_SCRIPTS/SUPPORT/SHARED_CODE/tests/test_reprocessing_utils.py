"""Test helpers that select and stage files for reprocessing."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[6]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.reprocessing_utils import (  # noqa: E402
    apply_qa_reprocessing_context,
    canonical_processing_basename,
    empty_qa_reprocessing_context,
    filter_filenames_by_qa_retry_basenames,
    get_reprocessing_value,
    infer_station_number_from_processing_name,
    load_active_qa_retry_basenames,
    load_qa_reprocessing_context_for_file,
)


class ReprocessingUtilsTests(unittest.TestCase):
    def test_canonical_processing_basename_normalizes_legacy_mini_prefix(self) -> None:
        self.assertEqual(
            canonical_processing_basename("cleaned_minI24049012732.parquet"),
            "mi0124049012732",
        )

    def test_infer_station_number_from_processing_name_supports_legacy_mini_prefix(self) -> None:
        self.assertEqual(
            infer_station_number_from_processing_name("cleaned_minI24049012732.parquet"),
            1,
        )

    def test_get_reprocessing_value_reads_component_columns_as_vector(self) -> None:
        params = pd.DataFrame(
            {
                "P1_s1_Q_FB_coeffs__0": [0.1],
                "P1_s1_Q_FB_coeffs__1": [-0.2],
                "P1_s1_Q_FB_coeffs__2": [0.03],
            }
        )

        value = get_reprocessing_value(params, "P1_s1_Q_FB_coeffs")

        self.assertEqual(value, [0.1, -0.2, 0.03])

    def test_load_qa_reprocessing_context_for_file_reads_active_state_rows(self) -> None:
        with self.subTest("active row"):
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as tmp_dir:
                repo_root = Path(tmp_dir)
                state_path = (
                    repo_root
                    / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
                    / "MINGO01"
                    / "STAGE_0"
                    / "REPROCESSING"
                    / "STEP_0"
                    / "METADATA"
                    / "qa_retry_state_1.csv"
                )
                state_path.parent.mkdir(parents=True, exist_ok=True)
                pd.DataFrame(
                    [
                        {
                            "basename": "mi0124074013648",
                            "selector_id": "all_quality_failures",
                            "failed_quality_columns": (
                                "STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum;"
                                "STEP_1_CALIBRATIONS::TASK_2::P4_s4_T_sum"
                            ),
                            "failed_quality_versions": (
                                "STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum@2026-04-20_18.53.34;"
                                "STEP_1_CALIBRATIONS::TASK_2::P4_s4_T_sum@2026-04-20_18.53.34"
                            ),
                            "is_active": "1",
                        },
                        {
                            "basename": "mi0124074013648",
                            "selector_id": "timing_failures",
                            "failed_quality_columns": "STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum",
                            "failed_quality_versions": "STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum@2026-04-20_18.53.34",
                            "is_active": "1",
                        },
                        {
                            "basename": "mi0124074999999",
                            "selector_id": "all_quality_failures",
                            "failed_quality_columns": "STEP_1_CALIBRATIONS::TASK_2::P1_s1_Q_B",
                            "failed_quality_versions": "STEP_1_CALIBRATIONS::TASK_2::P1_s1_Q_B@2026-04-20_18.53.34",
                            "is_active": "0",
                        },
                    ]
                ).to_csv(state_path, index=False)

                context = load_qa_reprocessing_context_for_file(
                    "1",
                    "mi0124074013648",
                    repo_root=repo_root,
                )

                self.assertEqual(context["qa_reprocessing_mode"], 1)
                self.assertEqual(
                    context["qa_reprocessing_selector_ids"],
                    "all_quality_failures;timing_failures",
                )
                self.assertEqual(
                    context["qa_reprocessing_failed_columns"],
                    (
                        "STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum;"
                        "STEP_1_CALIBRATIONS::TASK_2::P4_s4_T_sum"
                    ),
                )
                self.assertEqual(
                    context["qa_reprocessing_failed_versions"],
                    (
                        "STEP_1_CALIBRATIONS::TASK_2::P2_s4_T_sum@2026-04-20_18.53.34;"
                        "STEP_1_CALIBRATIONS::TASK_2::P4_s4_T_sum@2026-04-20_18.53.34"
                    ),
                )

    def test_apply_qa_reprocessing_context_populates_default_empty_values(self) -> None:
        target = {"filename_base": "mi0124074013648"}

        apply_qa_reprocessing_context(target, empty_qa_reprocessing_context())

        self.assertEqual(target["qa_reprocessing_mode"], 0)
        self.assertEqual(target["qa_reprocessing_selector_ids"], "")
        self.assertEqual(target["qa_reprocessing_failed_columns"], "")
        self.assertEqual(target["qa_reprocessing_failed_versions"], "")

    def test_canonical_processing_basename_strips_stage_prefixes_and_extensions(self) -> None:
        self.assertEqual(
            canonical_processing_basename("/tmp/calibrated_mi0124074013648.parquet"),
            "mi0124074013648",
        )
        self.assertEqual(
            canonical_processing_basename("cleaned_mi0124074013648.dat.gz"),
            "mi0124074013648",
        )

    def test_load_active_qa_retry_basenames_and_filter_filenames(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            state_path = (
                repo_root
                / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
                / "MINGO01"
                / "STAGE_0"
                / "REPROCESSING"
                / "STEP_0"
                / "METADATA"
                / "qa_retry_state_1.csv"
            )
            state_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    {
                        "basename": "mi0124074013648",
                        "selector_id": "all_quality_failures",
                        "is_active": "1",
                    },
                    {
                        "basename": "mi0124074999999",
                        "selector_id": "all_quality_failures",
                        "is_active": "0",
                    },
                ]
            ).to_csv(state_path, index=False)

            active = load_active_qa_retry_basenames("1", repo_root=repo_root)
            filtered = filter_filenames_by_qa_retry_basenames(
                [
                    "cleaned_mi0124074013648.parquet",
                    "cleaned_mi0124074999999.parquet",
                    "cleaned_mi0124074888888.parquet",
                ],
                active,
            )

            self.assertEqual(active, {"mi0124074013648"})
            self.assertEqual(filtered, ["cleaned_mi0124074013648.parquet"])


if __name__ == "__main__":
    unittest.main()
