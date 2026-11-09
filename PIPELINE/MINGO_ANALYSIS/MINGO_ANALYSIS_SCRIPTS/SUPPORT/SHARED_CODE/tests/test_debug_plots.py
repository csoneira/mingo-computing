from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import yaml

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.debug_plots import (
    _filter_numeric_histogram_values,
    plot_debug_histograms,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.step1_shared import (
    load_step1_task_plot_catalog,
    step1_task_plot_enabled,
)


class DebugHistogramTests(unittest.TestCase):
    def test_task0_numeric_window_omits_zeroes_and_strictly_outside_values(self) -> None:
        filtered, zero_count, outside_count = _filter_numeric_histogram_values(
            np.asarray([
                -100_001.0, -100_000.0, 0.0, 0.0,
                1.0, 100_000.0, 100_001.0, np.inf, np.nan,
            ]),
            exclude_zeros=True,
            absolute_limit=1e5,
        )

        np.testing.assert_array_equal(filtered, [-100_000.0, 1.0, 100_000.0])
        self.assertEqual(zero_count, 2)
        self.assertEqual(outside_count, 3)

    def test_omission_counts_are_written_in_each_numeric_subplot_title(self) -> None:
        frame = pd.DataFrame({"charge": [0.0, 2.0, 100_001.0]})
        with tempfile.TemporaryDirectory() as temporary:
            with patch("matplotlib.axes.Axes.set_title", autospec=True) as set_title:
                plot_debug_histograms(
                    frame,
                    ["charge"],
                    thresholds=None,
                    title="Task 0 filtered debug test",
                    out_dir=temporary,
                    exclude_zeros=True,
                    absolute_limit=1e5,
                    annotate_omissions=True,
                )

        titles = [str(call.args[1]) for call in set_title.call_args_list]
        self.assertTrue(any("0s=1" in title for title in titles))
        self.assertTrue(any("omitted=1" in title for title in titles))

    def test_task0_uses_explicit_plot_allow_and_deny_lists(self) -> None:
        repo_root = Path(__file__).resolve().parents[6]
        catalog_path = (
            repo_root
            / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS"
            / "SUPPORT" / "CONFIG_FILES" / "STAGE_1" / "EVENT_DATA" / "STEP_1"
            / "TASK_0" / "config_plots_task_0.yaml"
        )
        loaded = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
        self.assertEqual(set(loaded), {"-plot", "-not_plot"})
        self.assertEqual(loaded["-plot"], [])
        self.assertEqual(loaded["-not_plot"], [])
        catalog = load_step1_task_plot_catalog(
            catalog_path,
            (
                "debug_suite",
                "acquisition_rate_vs_time_by_trigger_type",
                "acquisition_rate_vs_time_by_task_tt_with_histograms",
            ),
            "Task 0",
        )
        self.assertFalse(step1_task_plot_enabled("debug_suite", catalog, "debug"))
        self.assertFalse(step1_task_plot_enabled("debug_suite", catalog, "all"))
        self.assertFalse(step1_task_plot_enabled("debug_suite", catalog, "usual"))

    def test_numeric_datetime_and_categorical_columns_share_one_debug_page(self) -> None:
        frame = pd.DataFrame({
            "numeric": [1.0, 2.0, 3.0, None],
            "datetime": pd.to_datetime([
                "2026-01-01 00:00:00",
                "2026-01-01 00:00:01",
                None,
                "2026-01-01 00:00:03",
            ]),
            "category": ["raw", "self-trigger", "raw", None],
        })
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            next_index = plot_debug_histograms(
                frame,
                list(frame.columns),
                thresholds=None,
                title="Task 0 all-column debug test",
                out_dir=str(output),
                fig_idx=1,
                max_cols_per_fig=20,
            )

            self.assertEqual(next_index, 2)
            plots = list(output.glob("*_debug_*.png"))
            self.assertEqual(len(plots), 1)
            self.assertGreater(plots[0].stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
