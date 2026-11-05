from __future__ import annotations

from pathlib import Path
import csv
import sys
from tempfile import TemporaryDirectory
import unittest


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.step1_shared import _normalize_metadata_row, normalize_metadata_file_schema  # noqa: E402


class Step1MetadataNormalizationTests(unittest.TestCase):
    def test_normalize_metadata_row_flattens_vectors_and_bools(self) -> None:
        row = _normalize_metadata_row(
            {
                "filename_base": "mi0124074013648",
                "P1_s1_Q_FB_coeffs": "[1.0, -2.5, 0.25]",
                "correct_angle": "True",
                "timtrack_projection_ellipse_tt_1234_available": False,
                "timtrack_projection_ellipse_contour_fractions": "0.25,0.50,0.75",
            }
        )

        self.assertNotIn("P1_s1_Q_FB_coeffs", row)
        self.assertEqual(row["P1_s1_Q_FB_coeffs__0"], 1.0)
        self.assertEqual(row["P1_s1_Q_FB_coeffs__1"], -2.5)
        self.assertEqual(row["P1_s1_Q_FB_coeffs__2"], 0.25)
        self.assertEqual(row["correct_angle"], 1)
        self.assertEqual(row["timtrack_projection_ellipse_tt_1234_available"], 0)
        self.assertEqual(row["timtrack_projection_ellipse_contour_fractions__0"], 0.25)
        self.assertEqual(row["timtrack_projection_ellipse_contour_fractions__1"], 0.50)
        self.assertEqual(row["timtrack_projection_ellipse_contour_fractions__2"], 0.75)

    def test_normalize_metadata_row_canonicalizes_lowercase_plane_prefix(self) -> None:
        row = _normalize_metadata_row({"p1_s1_ef_t_entries_original_rate_hz": 12})
        self.assertNotIn("p1_s1_ef_t_entries_original_rate_hz", row)
        self.assertEqual(row["P1_s1_ef_t_entries_original_rate_hz"], 12)

    def test_normalize_metadata_row_prefixes_legacy_plane_efficiency_fields(self) -> None:
        row = _normalize_metadata_row(
            {
                "eff1": 0.9,
                "eff2_robust": 0.8,
                "eff4_robust_xyphi": 0.7,
                "z_P3": 300,
                "streamer_P2": 4.5,
                "active_strips_P1_1000_rate_hz": 2.0,
                "charge_topology_plane_4_streamer_rate_hz": 0.3,
                "streamer_rate_plane_filtered_3": 0.2,
                "activation_plane_signal_to_signal_P1_to_P2": 12,
                "raw_channel_swap_plane4_3_4_applied": 1,
                "tt_task4_fit_1234_tim_outside_plane1_n": 6,
                "plane_combination_filter_offender_count_P1": 2,
            }
        )
        self.assertEqual(row["P1_eff"], 0.9)
        self.assertEqual(row["P2_eff_robust"], 0.8)
        self.assertEqual(row["P4_eff_robust_xyphi"], 0.7)
        self.assertEqual(row["P3_z"], 300)
        self.assertEqual(row["P2_streamer"], 4.5)
        self.assertEqual(row["P1_active_strips_1000_rate_hz"], 2.0)
        self.assertEqual(row["P4_charge_topology_streamer_rate_hz"], 0.3)
        self.assertEqual(row["P3_streamer_rate_filtered"], 0.2)
        self.assertEqual(row["P4_raw_channel_swap_s3_s4_applied"], 1)
        self.assertEqual(row["P1_tt_task4_fit_1234_tim_outside_n"], 6)
        self.assertEqual(row["P1_plane_combination_filter_offender_count"], 2)
        self.assertIn("activation_plane_signal_to_signal_P1_to_P2", row)

    def test_normalize_metadata_file_schema_rewrites_old_columns_in_place(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "task_2_metadata_calibration.csv"
            with csv_path.open("w", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(
                        "filename_base",
                        "execution_timestamp",
                        "P1_s1_Q_FB_coeffs",
                        "correct_angle",
                        "timtrack_projection_ellipse_contour_fractions",
                    ),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "filename_base": "mi0124074013648",
                        "execution_timestamp": "2026-04-17_14.50.27",
                        "P1_s1_Q_FB_coeffs": "[1.0, 2.0, 3.0]",
                        "correct_angle": "False",
                        "timtrack_projection_ellipse_contour_fractions": "0.25,0.50,0.75",
                    }
                )

            normalize_metadata_file_schema(csv_path)

            with csv_path.open("r", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertIsNotNone(reader.fieldnames)
                header = set(reader.fieldnames or [])
                self.assertNotIn("P1_s1_Q_FB_coeffs", header)
                self.assertNotIn("timtrack_projection_ellipse_contour_fractions", header)
                self.assertIn("P1_s1_Q_FB_coeffs__0", header)
                self.assertIn("P1_s1_Q_FB_coeffs__1", header)
                self.assertIn("P1_s1_Q_FB_coeffs__2", header)
                self.assertIn("timtrack_projection_ellipse_contour_fractions__2", header)
                row = next(reader)

            self.assertEqual(row["P1_s1_Q_FB_coeffs__0"], "1.0")
            self.assertEqual(row["P1_s1_Q_FB_coeffs__1"], "2.0")
            self.assertEqual(row["P1_s1_Q_FB_coeffs__2"], "3.0")
            self.assertEqual(row["correct_angle"], "0")
            self.assertEqual(row["timtrack_projection_ellipse_contour_fractions__0"], "0.25")
            self.assertEqual(row["timtrack_projection_ellipse_contour_fractions__1"], "0.5")
            self.assertEqual(row["timtrack_projection_ellipse_contour_fractions__2"], "0.75")

    def test_normalize_metadata_file_schema_renames_plane_strip_columns_and_keeps_values(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "task_1_metadata_specific.csv"
            with csv_path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("filename_base", "p1_s1_ef_t_entries_original_rate_hz"))
                writer.writeheader()
                writer.writerow({"filename_base": "run001", "p1_s1_ef_t_entries_original_rate_hz": "12"})

            normalize_metadata_file_schema(csv_path)

            with csv_path.open("r", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, ["filename_base", "P1_s1_ef_t_entries_original_rate_hz"])
                row = next(reader)
            self.assertEqual(row["P1_s1_ef_t_entries_original_rate_hz"], "12")

    def test_normalize_metadata_file_schema_renames_legacy_efficiency_columns(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "task_4_metadata_robust_efficiency.csv"
            with csv_path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("filename_base", "eff1", "eff1_robust"))
                writer.writeheader()
                writer.writerow({"filename_base": "run001", "eff1": "0.91", "eff1_robust": "0.89"})

            normalize_metadata_file_schema(csv_path)

            with csv_path.open("r", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, ["filename_base", "P1_eff", "P1_eff_robust"])
                row = next(reader)
            self.assertEqual(row["P1_eff"], "0.91")
            self.assertEqual(row["P1_eff_robust"], "0.89")


if __name__ == "__main__":
    unittest.main()
