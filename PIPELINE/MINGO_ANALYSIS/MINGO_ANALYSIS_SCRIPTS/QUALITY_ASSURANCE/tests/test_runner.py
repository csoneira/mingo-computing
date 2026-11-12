"""Test the quality-assurance runner and its configured checks."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.QUALITY_ASSURANCE.qa_core.common import (
    deduplicate_metadata_rows_with_report,
    metadata_path,
)  # noqa: E402
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.QUALITY_ASSURANCE.qa_core.runner import (  # noqa: E402
    _collect_step_outputs,
    _generate_station_plots,
    _quality_threshold_config_for_specs,
    _write_step_outputs,
    load_step_bundle,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.QUALITY_ASSURANCE.orchestrate_quality_assurance import rotate_previous_outputs
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.QUALITY_ASSURANCE.qa_core.thresholds import resolve_threshold_rule  # noqa: E402


class RunnerTests(unittest.TestCase):
    def test_deduplicate_metadata_rows_reports_overwritten_duplicate_basenames(self) -> None:
        meta_df = pd.DataFrame(
            {
                "filename_base": ["mi0124074013648", "mi0124074013648", "mi0124074030910"],
                "execution_timestamp": [
                    "2026-04-22_10.00.00",
                    "2026-04-22_10.05.00",
                    "2026-04-22_10.02.00",
                ],
                "metric": [1.0, 2.0, 3.0],
            }
        )

        deduped_df, overwritten_df = deduplicate_metadata_rows_with_report(meta_df)

        self.assertEqual(deduped_df["filename_base"].tolist(), ["mi0124074013648", "mi0124074030910"])
        self.assertEqual(deduped_df.loc[deduped_df["filename_base"] == "mi0124074013648", "metric"].iloc[0], 2.0)
        self.assertEqual(len(overwritten_df), 1)
        self.assertEqual(overwritten_df.loc[0, "overwritten_status"], "overwritten")
        self.assertEqual(overwritten_df.loc[0, "filename_base"], "mi0124074013648")
        self.assertEqual(int(overwritten_df.loc[0, "source_row_index"]), 0)
        self.assertEqual(int(overwritten_df.loc[0, "kept_source_row_index"]), 1)

    def test_collect_step_outputs_reads_task_id_from_task_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            step_dir = Path(tmp_dir) / "STEP_1_SAMPLE"
            files_dir = step_dir / "TASK_7" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / "MINGO01" / "OUTPUTS" / "FILES"
            files_dir.mkdir(parents=True, exist_ok=True)

            pd.DataFrame(
                {
                    "filename_base": ["mi0124074013648"],
                    "qa_status": ["pass"],
                    "qa_timestamp": ["2024-03-14 01:36:48"],
                }
            ).to_csv(files_dir / "MINGO01_task_7_sample_pass.csv", index=False)

            pd.DataFrame(
                {
                    "filename_base": ["mi0124074013648"],
                    "evaluation_column": ["metric_a"],
                    "status": ["pass"],
                    "reason": [""],
                }
            ).to_csv(files_dir / "sample_column_evaluations.csv", index=False)

            summary_df, eval_df = _collect_step_outputs(step_dir, "sample", "MINGO01")

            self.assertEqual(int(eval_df.loc[0, "task_id"]), 7)
            self.assertEqual(str(summary_df.loc[0, "step_name"]), "STEP_1_SAMPLE")
            self.assertEqual(str(summary_df.loc[0, "step_display_name"]), "sample")
            self.assertEqual(int(summary_df.loc[0, "qa_evaluated_columns"]), 1)

    def test_collect_step_outputs_ignores_stale_eval_when_manifest_has_no_quality(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            step_dir = Path(tmp_dir) / "STEP_1_SAMPLE"
            files_dir = step_dir / "TASK_7" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / "MINGO01" / "OUTPUTS" / "FILES"
            files_dir.mkdir(parents=True, exist_ok=True)

            pd.DataFrame(
                {
                    "filename_base": ["mi0124074013648"],
                    "sample_pass": [1.0],
                    "qa_timestamp": ["2024-03-14 01:36:48"],
                }
            ).to_csv(files_dir / "MINGO01_task_7_sample_pass.csv", index=False)

            pd.DataFrame(
                {
                    "filename_base": ["mi0124074013648"],
                    "evaluation_column": ["metric_a"],
                    "source_column": ["metric_a"],
                    "status": ["pass"],
                    "reason": [""],
                }
            ).to_csv(files_dir / "sample_column_evaluations.csv", index=False)

            pd.DataFrame(
                {
                    "column_name": ["metric_a"],
                    "requested_category": ["plot_only"],
                    "effective_plot": [1],
                    "effective_quality": [0],
                }
            ).to_csv(files_dir / "MINGO01_task_7_sample_column_manifest.csv", index=False)

            summary_df, eval_df = _collect_step_outputs(step_dir, "sample", "MINGO01")

            self.assertTrue(eval_df.empty)
            self.assertEqual(int(summary_df.loc[0, "qa_evaluated_columns"]), 0)
            self.assertTrue(pd.isna(summary_df.loc[0, "qa_pass_fraction"]))

    def test_write_step_outputs_uses_step_output_tree_not_step_stations_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            step_dir = Path(tmp_dir) / "STEP_1_SAMPLE"
            summary_df = pd.DataFrame(
                {
                    "filename_base": ["mi0124074013648"],
                    "qa_status": ["pass"],
                    "qa_evaluated_columns": [1],
                    "qa_passed_columns": [1],
                    "qa_failed_columns": [0],
                    "qa_warning_columns": [0],
                    "qa_pass_fraction": [1.0],
                    "step_name": ["STEP_1_SAMPLE"],
                    "step_display_name": ["sample"],
                }
            )
            eval_df = pd.DataFrame(
                {
                    "filename_base": ["mi0124074013648"],
                    "task_id": [7],
                    "source_column": ["metric_a"],
                    "evaluation_column": ["metric_a"],
                    "status": ["pass"],
                    "plot_timestamp": ["2024-03-14 01:36:48"],
                }
            )

            _write_step_outputs(step_dir, "sample", "MINGO01", summary_df, eval_df)

            self.assertTrue((step_dir / "OUTPUTS" / "MINGO01" / "FILES" / "MINGO01_sample_step_summary.csv").exists())
            self.assertFalse((step_dir / "STATIONS").exists())

    def test_generate_station_plots_special_group_applies_sharey_and_ylim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            task_output_dir = Path(tmp_dir) / "STEP_1_SAMPLE" / "TASK_1"
            analyzed_df = pd.DataFrame(
                {
                    "plot_x": [1, 2, 3],
                    "metric_a": [2.0, 4.0, 6.0],
                    "metric_b": [20.0, 40.0, 60.0],
                }
            )
            created_figures: dict[str, object] = {}

            def fake_savefig(fig: object, fname: str | Path, *args: object, **kwargs: object) -> None:
                created_figures[str(fname)] = fig
                Path(fname).touch()

            with patch("matplotlib.figure.Figure.savefig", new=fake_savefig):
                created_paths = _generate_station_plots(
                    task_output_dir=task_output_dir,
                    station_name="MINGO01",
                    task_id=1,
                    metadata_type="sample",
                    analyzed_df=analyzed_df,
                    plot_columns=["metric_a", "metric_b"],
                    config={
                        "x_axis": {"mode": "column", "column": "plot_x"},
                        "plots": {"format": "png"},
                    },
                    plot_config={
                        "default": {"default_ncols": 2},
                        "special": [
                            {
                                "name": "paired_metrics",
                                "mode": "columns",
                                "columns": ["metric_*"],
                                "ncols": 2,
                                "sharey": True,
                                "ylim": [0, 100],
                            }
                        ],
                    },
                )

            self.assertEqual(len(created_paths), 1)
            self.assertTrue(created_paths[0].exists())

            figure = created_figures[str(created_paths[0])]
            axes = figure.axes
            self.assertEqual(len(axes), 2)
            self.assertTrue(axes[0].get_shared_y_axes().joined(axes[0], axes[1]))
            self.assertEqual(tuple(round(value, 5) for value in axes[0].get_ylim()), (0.0, 100.0))
            self.assertEqual(tuple(round(value, 5) for value in axes[1].get_ylim()), (0.0, 100.0))

    def test_generate_station_plots_panels_group_overlays_explicit_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            task_output_dir = Path(tmp_dir) / "STEP_1_SAMPLE" / "TASK_1"
            analyzed_df = pd.DataFrame(
                {
                    "plot_x": [1, 2, 3],
                    "overall_metric": [2.0, 4.0, 6.0],
                    "self_metric": [1.0, 2.0, 3.0],
                    "overall_other": [5.0, 10.0, 15.0],
                    "self_other": [2.5, 5.0, 7.5],
                }
            )
            created_figures: dict[str, object] = {}

            def fake_savefig(fig: object, fname: str | Path, *args: object, **kwargs: object) -> None:
                created_figures[str(fname)] = fig
                Path(fname).touch()

            with patch("matplotlib.figure.Figure.savefig", new=fake_savefig):
                created_paths = _generate_station_plots(
                    task_output_dir=task_output_dir,
                    station_name="MINGO01",
                    task_id=1,
                    metadata_type="sample",
                    analyzed_df=analyzed_df,
                    plot_columns=[
                        "overall_metric",
                        "self_metric",
                        "overall_other",
                        "self_other",
                    ],
                    config={
                        "x_axis": {"mode": "column", "column": "plot_x"},
                        "plots": {"format": "png"},
                    },
                    plot_config={
                        "default": {"default_ncols": 2},
                        "special": [
                            {
                                "name": "explicit_panels",
                                "mode": "panels",
                                "ncols": 2,
                                "sharey": True,
                                "ylim": [0, 20],
                                "series_labels": ["overall", "self"],
                                "panels": [
                                    {
                                        "title": "metric",
                                        "columns": ["overall_metric", "self_metric"],
                                    },
                                    {
                                        "title": "other",
                                        "columns": ["overall_other", "self_other"],
                                    },
                                ],
                            }
                        ],
                    },
                )

            self.assertEqual(len(created_paths), 1)
            self.assertTrue(created_paths[0].exists())

            figure = created_figures[str(created_paths[0])]
            axes = figure.axes
            self.assertEqual(len(axes), 2)
            self.assertEqual(axes[0].get_title(), "metric")
            self.assertEqual(axes[1].get_title(), "other")
            self.assertTrue(axes[0].get_shared_y_axes().joined(axes[0], axes[1]))
            self.assertEqual(tuple(round(value, 5) for value in axes[0].get_ylim()), (0.0, 20.0))
            self.assertEqual(len(axes[0].lines), 0)
            self.assertEqual(len(axes[1].lines), 0)
            self.assertEqual(len(axes[0].collections), 2)
            self.assertEqual(len(axes[1].collections), 2)


    def test_quality_plot_draws_exact_persisted_passing_bands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            task_output_dir = Path(tmp_dir) / "STEP_1_SAMPLE" / "TASK_1"
            basenames = ["file_a", "file_b", "file_c"]
            analyzed_df = pd.DataFrame({
                "filename_base": basenames,
                "plot_x": [1, 2, 3],
                "metric_b": [2.0, 4.0, 6.0],
                "metric_f": [3.0, 5.0, 7.0],
            })
            evaluations = pd.DataFrame([
                {
                    "filename_base": basename,
                    "evaluation_column": column,
                    "lower_bound": lower,
                    "upper_bound": upper,
                }
                for basename in basenames
                for column, lower, upper in (
                    ("metric_b", 1.5, 6.5),
                    ("metric_f", 2.5, 7.5),
                )
            ])
            created_figures: dict[str, object] = {}

            def fake_savefig(fig: object, fname: str | Path, *args: object, **kwargs: object) -> None:
                created_figures[str(fname)] = fig
                Path(fname).touch()

            with patch("matplotlib.figure.Figure.savefig", new=fake_savefig):
                created_paths = _generate_station_plots(
                    task_output_dir=task_output_dir,
                    station_name="MINGO01",
                    task_id=1,
                    metadata_type="sample",
                    analyzed_df=analyzed_df,
                    plot_columns=["metric_b", "metric_f"],
                    config={
                        "x_axis": {"mode": "column", "column": "plot_x"},
                        "plots": {"format": "png"},
                    },
                    plot_config={
                        "special": [{
                            "name": "paired",
                            "mode": "panels",
                            "series_labels": ["B", "F"],
                            "panels": [{
                                "title": "metric",
                                "columns": ["metric_b", "metric_f"],
                            }],
                        }],
                    },
                    quality_evaluations=evaluations,
                )

            axis = created_figures[str(created_paths[0])].axes[0]
            self.assertEqual(len(axis.collections), 4)
            self.assertEqual(
                axis.get_legend_handles_labels()[1],
                ["B", "B passing range", "F", "F passing range"],
            )

    def test_quality_plot_marks_queued_and_in_flight_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            task_output_dir = Path(tmp_dir) / "STEP_1_SAMPLE" / "TASK_1"
            basenames = ["file_pass", "file_queued", "file_in_flight"]
            analyzed_df = pd.DataFrame({
                "filename_base": basenames,
                "plot_x": [1, 2, 3],
                "metric_b": [2.0, 9.0, 10.0],
                "metric_f": [3.0, 10.0, 11.0],
            })
            evaluations = pd.DataFrame([
                {
                    "filename_base": basename,
                    "evaluation_column": column,
                    "lower_bound": 1.0,
                    "upper_bound": 8.0,
                    "status": "pass" if basename == "file_pass" else "fail",
                }
                for basename in basenames
                for column in ("metric_b", "metric_f")
            ])
            retry_states = pd.DataFrame({
                "basename": ["file_queued", "file_in_flight"],
                "is_active": ["1", "1"],
                "admitted_at": ["", "2026-07-24 16:00:00"],
            })
            created_figures: dict[str, object] = {}

            def fake_savefig(fig: object, fname: str | Path, *args: object, **kwargs: object) -> None:
                created_figures[str(fname)] = fig
                Path(fname).touch()

            with (
                patch(
                    "PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.QUALITY_ASSURANCE.qa_core.runner._load_retry_plot_states",
                    return_value=retry_states,
                ),
                patch("matplotlib.figure.Figure.savefig", new=fake_savefig),
            ):
                created_paths = _generate_station_plots(
                    task_output_dir=task_output_dir,
                    station_name="MINGO01",
                    task_id=1,
                    metadata_type="sample",
                    analyzed_df=analyzed_df,
                    plot_columns=["metric_b", "metric_f"],
                    config={
                        "x_axis": {"mode": "column", "column": "plot_x"},
                        "plots": {"format": "png"},
                    },
                    plot_config={
                        "special": [{
                            "name": "paired",
                            "mode": "panels",
                            "series_labels": ["B", "F"],
                            "panels": [{
                                "title": "metric",
                                "columns": ["metric_b", "metric_f"],
                            }],
                        }],
                    },
                    quality_evaluations=evaluations,
                )

            axis = created_figures[str(created_paths[0])].axes[0]
            self.assertEqual(
                axis.get_legend_handles_labels()[1],
                [
                    "B", "QA fail: queued", "QA retry: in flight",
                    "B passing range", "F", "F passing range",
                ],
            )
            labels = [collection.get_label() for collection in axis.collections]
            self.assertIn("QA fail: queued", labels)
            self.assertIn("QA retry: in flight", labels)

    def test_calibration_yaml_uses_configured_median_percentage(self) -> None:
        qa_root = Path(__file__).resolve().parents[1]
        step_dir = qa_root / "STEPS" / "STEP_1_CALIBRATIONS"
        root_config = {
            "quality_defaults": {
                "center_method": "mean",
                "tolerance_mode": "zscore",
                "tolerance_value": 3.0,
            },
        }
        config, _, _ = load_step_bundle(step_dir, root_config)
        defaults, column_rules = _quality_threshold_config_for_specs(
            step_dir=step_dir,
            config=config,
            specs_df=pd.DataFrame([{
                "evaluation_column": "P1_s1_Q_B",
                "source_column": "P1_s1_Q_B",
            }]),
        )
        rule = resolve_threshold_rule(defaults, column_rules["P1_s1_Q_B"])

        self.assertEqual(rule.center_method, "median")
        self.assertEqual(rule.tolerance_mode, "relative_pct")
        self.assertAlmostEqual(rule.tolerance_value, 0.02)

    def test_metadata_path_is_lake_gated_product_metadata(self) -> None:
        path = metadata_path(
            Path("/repo"), "MINGO02", 2, "task_2_metadata_calibration.csv",
        )
        self.assertEqual(
            path,
            Path("/repo/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO02/")
            / "STAGE_1_PRODUCTS/EVENT_DATA/METADATA/TASK_2/"
            / "task_2_metadata_calibration.csv",
        )


class OutputRotationTests(unittest.TestCase):
    def test_plot_rotation_clears_active_outputs_and_centralizes_previous_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            qa_root = Path(temporary_directory)
            step_outputs = qa_root / "STEPS" / "STEP_1_SAMPLE" / "OUTPUTS"
            total_outputs = qa_root / "TOTAL_SUMMARY" / "OUTPUTS"
            (step_outputs / "MINGO01" / "FILES").mkdir(parents=True)
            (step_outputs / "LAST").mkdir()
            (step_outputs / "LAST" / "older.csv").write_text("older", encoding="utf-8")
            (step_outputs / "MINGO01" / "FILES" / "current.csv").write_text("current", encoding="utf-8")
            (total_outputs / "PLOTS").mkdir(parents=True)
            (total_outputs / "PLOTS" / "current.png").write_bytes(b"png")
            authority = (
                total_outputs / "FILES"
                / "qa_all_stations_reprocessing_quality.csv"
            )
            authority.parent.mkdir(parents=True)
            authority.write_text("quality_status\nfail\n", encoding="utf-8")

            rotated_dirs, moved_files, _ = rotate_previous_outputs(qa_root)

            self.assertEqual(rotated_dirs, 2)
            self.assertEqual(moved_files, 4)
            self.assertEqual(list(step_outputs.iterdir()), [])
            self.assertTrue(authority.exists())
            self.assertEqual(
                authority.read_text(encoding="utf-8"),
                "quality_status\nfail\n",
            )

            previous = qa_root / "ARCHIVED_RUN_OUTPUTS" / "PREVIOUS_RUN"
            archived_step = previous / "STEPS" / "STEP_1_SAMPLE" / "OUTPUTS"
            archived_total = previous / "TOTAL_SUMMARY" / "OUTPUTS"
            self.assertTrue(
                (archived_step / "MINGO01" / "FILES" / "current.csv").exists()
            )
            self.assertTrue((archived_step / "LAST" / "older.csv").exists())
            self.assertTrue((archived_total / "PLOTS" / "current.png").exists())
            self.assertTrue(
                (
                    archived_total / "FILES"
                    / "qa_all_stations_reprocessing_quality.csv"
                ).exists()
            )

            self.assertEqual(rotate_previous_outputs(qa_root), (0, 0, 0))
            self.assertTrue(
                (archived_step / "MINGO01" / "FILES" / "current.csv").exists()
            )



if __name__ == "__main__":
    unittest.main()
