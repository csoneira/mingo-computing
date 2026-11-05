from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.input_file_config import (
    select_closest_valid_z_configuration,
)


class ClosestValidZConfigurationTests(unittest.TestCase):
    def test_skips_incomplete_and_all_zero_rows(self) -> None:
        frame = pd.DataFrame([
            {"conf": 1, "start": "2026-07-01", "P1": 0, "P2": 0, "P3": 0, "P4": 0},
            {"conf": 2, "start": "2026-07-20", "P1": 45, "P2": 134, "P3": 237, "P4": 470},
            {"conf": 3, "start": "2026-07-24", "P1": np.nan, "P2": np.nan, "P3": np.nan, "P4": np.nan},
        ])

        selected = select_closest_valid_z_configuration(
            frame,
            reference_time="2026-07-25 15:39:20",
        )

        self.assertIsNotNone(selected)
        self.assertEqual(int(selected["conf"]), 2)
        self.assertEqual(
            [float(selected[f"P{plane}"]) for plane in range(1, 5)],
            [45.0, 134.0, 237.0, 470.0],
        )

    def test_equal_distance_prefers_most_recent_start(self) -> None:
        frame = pd.DataFrame([
            {"conf": 1, "start": "2026-07-20", "P1": 0, "P2": 100, "P3": 200, "P4": 300},
            {"conf": 2, "start": "2026-07-30", "P1": 0, "P2": 110, "P3": 220, "P4": 330},
        ])

        selected = select_closest_valid_z_configuration(
            frame,
            reference_time="2026-07-25",
        )

        self.assertIsNotNone(selected)
        self.assertEqual(int(selected["conf"]), 2)

    def test_returns_none_without_four_complete_positions(self) -> None:
        frame = pd.DataFrame([
            {"conf": 1, "start": "2026-07-24", "P1": 0, "P2": 100, "P3": np.nan, "P4": 300},
        ])

        selected = select_closest_valid_z_configuration(
            frame,
            reference_time="2026-07-25",
        )

        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()
