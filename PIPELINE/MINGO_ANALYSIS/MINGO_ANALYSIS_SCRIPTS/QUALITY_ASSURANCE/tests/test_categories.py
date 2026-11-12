"""Test quality-assurance category selection and grouping."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.QUALITY_ASSURANCE.qa_core.categories import (
    build_column_manifest,
    manifest_plot_columns,
)  # noqa: E402


class CategoryTests(unittest.TestCase):

    def test_only_qb_and_qf_are_configured_for_quality(self) -> None:
        qa_root = Path(__file__).resolve().parents[1]
        configurations = []
        for columns_path in sorted((qa_root / "STEPS").glob("STEP_*/columns.yaml")):
            config = yaml.safe_load(columns_path.read_text(encoding="utf-8")) or {}
            configurations.append(config)
        self.assertGreater(len(configurations), 0)

        configured_quality_patterns = [
            pattern
            for config in configurations
            for pattern in [
                *(config.get("quality_and_plot", []) or []),
                *(config.get("quality_only", []) or []),
            ]
        ]
        self.assertEqual(configured_quality_patterns, ["*_Q_B", "*_Q_F"])
        quality_config = next(
            config for config in configurations
            if config.get("quality_and_plot") or config.get("quality_only")
        )
        manifest = build_column_manifest(
            pd.DataFrame({"P1_s1_Q_B": [1.0], "P1_s1_Q_F": [2.0], "P1_s1_T": [3.0]}),
            quality_config,
        ).set_index("column_name")
        self.assertEqual(manifest.loc["P1_s1_Q_B", "effective_quality"], 1)
        self.assertEqual(manifest.loc["P1_s1_Q_F", "effective_quality"], 1)
        self.assertEqual(manifest.loc["P1_s1_T", "effective_quality"], 0)

    def test_metadata_plots_use_unconnected_points(self) -> None:
        runner_source = (
            Path(__file__).resolve().parents[1] / "qa_core" / "runner.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("ax.plot(", runner_source)
        self.assertGreaterEqual(runner_source.count("ax.scatter("), 2)

    def test_default_is_plot_only_and_ignore_wins(self) -> None:
        df = pd.DataFrame(
            {
                "metric_a": [1.0, 2.0],
                "metric_b": [3.0, 4.0],
                "param_hash": ["x", "y"],
            }
        )

        manifest_df = build_column_manifest(
            df,
            {
                "quality_and_plot": ["metric_b"],
                "ignore": ["param_hash"],
            },
        )
        by_column = manifest_df.set_index("column_name")

        self.assertEqual(by_column.loc["metric_a", "requested_category"], "plot_only")
        self.assertEqual(int(by_column.loc["metric_a", "effective_plot"]), 1)
        self.assertEqual(int(by_column.loc["metric_a", "effective_quality"]), 0)

        self.assertEqual(by_column.loc["metric_b", "requested_category"], "quality_and_plot")
        self.assertEqual(int(by_column.loc["metric_b", "effective_plot"]), 1)
        self.assertEqual(int(by_column.loc["metric_b", "effective_quality"]), 1)

        self.assertEqual(by_column.loc["param_hash", "requested_category"], "ignore")
        self.assertEqual(int(by_column.loc["param_hash", "effective_plot"]), 0)
        self.assertEqual(int(by_column.loc["param_hash", "effective_quality"]), 0)

    def test_qa_plot_scope_excludes_plot_only_columns(self) -> None:
        manifest_df = build_column_manifest(
            pd.DataFrame({
                "q_offset": [1.0, 2.0],
                "diagnostic": [3.0, 4.0],
                "quality_table_only": [5.0, 6.0],
            }),
            {
                "quality_and_plot": ["q_offset"],
                "quality_only": ["quality_table_only"],
            },
        )

        self.assertEqual(
            manifest_plot_columns(manifest_df),
            ["diagnostic", "q_offset"],
        )
        self.assertEqual(
            manifest_plot_columns(manifest_df, quality_and_plot_only=True),
            ["q_offset"],
        )

    def test_non_numeric_columns_do_not_plot_or_enter_quality(self) -> None:
        df = pd.DataFrame(
            {
                "tt_loo_mode": ["leave_one_out", "full"],
                "correct_angle": [1, 0],
            }
        )

        manifest_df = build_column_manifest(
            df,
            {
                "quality_and_plot": ["*"],
            },
        )
        by_column = manifest_df.set_index("column_name")

        self.assertEqual(by_column.loc["tt_loo_mode", "requested_category"], "quality_and_plot")
        self.assertEqual(int(by_column.loc["tt_loo_mode", "effective_plot"]), 0)
        self.assertEqual(int(by_column.loc["tt_loo_mode", "effective_quality"]), 0)
        self.assertEqual(by_column.loc["tt_loo_mode", "note"], "non_numeric")

        self.assertEqual(int(by_column.loc["correct_angle", "effective_plot"]), 1)
        self.assertEqual(int(by_column.loc["correct_angle", "effective_quality"]), 1)

    def test_shorthand_quality_rule_promotes_matching_limit_column(self) -> None:
        df = pd.DataFrame(
            {
                "plane_combination_plane_q_dif_sum_low_limit": [1.0, 1.1],
                "plane_combination_plane_q_dif_sum_low_rows_failed_pct": [2.0, 3.0],
            }
        )

        manifest_df = build_column_manifest(
            df,
            {
                "quality_and_plot": ["q_dif_sum_low"],
                "plot_only": ["*_rows_failed_pct", "*_limit"],
            },
        )
        by_column = manifest_df.set_index("column_name")

        self.assertEqual(
            by_column.loc["plane_combination_plane_q_dif_sum_low_limit", "requested_category"],
            "quality_and_plot",
        )
        self.assertEqual(
            int(by_column.loc["plane_combination_plane_q_dif_sum_low_limit", "effective_quality"]),
            1,
        )
        self.assertEqual(
            by_column.loc["plane_combination_plane_q_dif_sum_low_rows_failed_pct", "requested_category"],
            "plot_only",
        )


if __name__ == "__main__":
    unittest.main()
