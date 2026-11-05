#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_STEP12_DIR = (
    Path(__file__).resolve().parent.parent / "STEP_1_2_TRANSFORM_FEATURE_SPACE"
)
sys.path.insert(0, str(_STEP12_DIR))

import transform_feature_space as step12  # noqa: E402
from transform_feature_space import (  # noqa: E402
    EFF_PLACEHOLDER_COL,
    RATE_HIST_PLACEHOLDER_COL,
    _build_required_passthrough_columns,
    _catalog_presence_against_columns,
    _filter_rows_with_complete_primary_feature_space,
    _merge_materialized_with_required_columns,
    _make_grouped_feature_space_summary_plot,
    _resolve_feature_matrix_plot_columns,
    _resolve_required_passthrough_columns,
    _resolve_feature_space_plot_suppression_patterns,
)


def test_grouped_feature_space_summary_plot_handles_hist_and_eff_vectors(
    tmp_path: Path,
) -> None:
    step12._FIGURE_COUNTER = 0
    df = pd.DataFrame(
        {
            "events_per_second_0_rate_hz": [0.60, 0.55, 0.50],
            "events_per_second_1_rate_hz": [0.40, 0.45, 0.50],
            "efficiency_vector_p1_x_bin_0_center_mm": [-50.0, -50.0, -50.0],
            "efficiency_vector_p1_x_bin_1_center_mm": [50.0, 50.0, 50.0],
            "efficiency_vector_p1_x_bin_0_eff": [0.82, 0.84, 0.86],
            "efficiency_vector_p1_x_bin_1_eff": [0.88, 0.89, 0.91],
            "efficiency_vector_p1_x_bin_0_unc": [0.03, 0.03, 0.03],
            "efficiency_vector_p1_x_bin_1_unc": [0.03, 0.03, 0.03],
        }
    )

    summary = _make_grouped_feature_space_summary_plot(
        df,
        selected_feature_cols=[
            "events_per_second_0_rate_hz",
            "events_per_second_1_rate_hz",
        ],
        out_path=tmp_path / "grouped_feature_summary.png",
    )

    written = list(tmp_path.glob("1_2_*_grouped_feature_summary.png"))
    assert written
    assert summary["status"] == "ok"
    assert int(summary["rate_histogram_bins_used"]) == 2
    assert int(summary["efficiency_vector_groups_used"]) == 1
    assert summary["efficiency_vector_axes_used"] == ["x"]


def test_catalog_presence_respects_transform_activation_flags() -> None:
    catalog = [
        {
            "column_pattern": "flux_proxy_rate_div_effprod",
            "source": "events_per_second_global_rate / efficiency_product_4planes",
            "generated_when": "transformations.derive_physics_helpers",
        }
    ]
    presence_disabled, unmatched_disabled = _catalog_presence_against_columns(
        catalog_entries=catalog,
        available_columns=["events_per_second_global_rate"],
        transform_options={"derive_physics_helpers": False},
    )
    assert unmatched_disabled == []
    assert bool(presence_disabled[0]["expected_active"]) is False

    _, unmatched_enabled = _catalog_presence_against_columns(
        catalog_entries=catalog,
        available_columns=["events_per_second_global_rate"],
        transform_options={"derive_physics_helpers": True},
    )
    assert unmatched_enabled == ["flux_proxy_rate_div_effprod"]


def test_required_passthrough_columns_are_flattened_and_merged() -> None:
    cfg = {
        "required_passthrough_columns": {
            "ids": ["filename_base", "task_id"],
            "support": {
                "rate": ["events_per_second_global_rate"],
                "vector_meta": ["efficiency_vector_p1_x_bin_000_center_mm"],
            },
        }
    }
    required = _resolve_required_passthrough_columns(cfg)
    assert required == [
        "filename_base",
        "task_id",
        "events_per_second_global_rate",
        "efficiency_vector_p1_x_bin_000_center_mm",
    ]

    merged, missing = _merge_materialized_with_required_columns(
        materialized_columns=["events_per_second_0_rate_hz", "events_per_second_1_rate_hz"],
        required_columns=required,
        available_columns=[
            "filename_base",
            "task_id",
            "events_per_second_global_rate",
            "events_per_second_0_rate_hz",
            "events_per_second_1_rate_hz",
        ],
    )
    assert merged == [
        "events_per_second_0_rate_hz",
        "events_per_second_1_rate_hz",
        "filename_base",
        "task_id",
        "events_per_second_global_rate",
    ]
    assert missing == ["efficiency_vector_p1_x_bin_000_center_mm"]


def test_primary_feature_space_filter_drops_rows_with_partial_vectors() -> None:
    df = pd.DataFrame(
        {
            "events_per_second_0_rate_hz": [0.60, 0.55, 0.50],
            "events_per_second_1_rate_hz": [0.40, 0.45, 0.50],
            "efficiency_vector_p1_x_bin_0_eff": [0.82, None, 0.86],
            "efficiency_vector_p1_x_bin_1_eff": [0.88, None, 0.91],
            "filename_base": ["a", "b", "c"],
        }
    )

    filtered, info = _filter_rows_with_complete_primary_feature_space(
        df,
        primary_feature_columns=[
            "events_per_second_0_rate_hz",
            "events_per_second_1_rate_hz",
            "efficiency_vector_p1_x_bin_0_eff",
            "efficiency_vector_p1_x_bin_1_eff",
        ],
    )

    assert filtered["filename_base"].tolist() == ["a", "c"]
    assert info["rows_kept"] == 2
    assert info["rows_removed"] == 1
    assert info["row_missing_primary_feature_count_distribution"] == {"0": 2, "2": 1}
    assert sorted(
        info["top_missing_primary_feature_columns"],
        key=lambda item: item["column"],
    ) == [
        {"column": "efficiency_vector_p1_x_bin_0_eff", "missing_rows": 1},
        {"column": "efficiency_vector_p1_x_bin_1_eff", "missing_rows": 1},
    ]


def test_required_passthrough_columns_use_step11_roles_and_parameter_artifact(
    tmp_path: Path,
) -> None:
    parameter_space_path = tmp_path / "parameter_space_columns.json"
    parameter_space_path.write_text(
        """{
  "selected_parameter_space_columns": ["flux_cm2_min", "eff_p1", "eff_p2"],
  "parameter_space_columns_downstream_preferred": ["flux_cm2_min", "eff_sim_1", "eff_sim_2"]
}""",
        encoding="utf-8",
    )

    required, info = _build_required_passthrough_columns(
        config={
            "step_1_1": {
                "general_columns": {
                    "ids": ["filename_base", "task_id"],
                    "geometry": ["z_plane_1", "z_plane_2"],
                }
            }
        },
        cfg_12={},
        parameter_space_path=parameter_space_path,
    )

    assert required == [
        "filename_base",
        "task_id",
        "z_plane_1",
        "z_plane_2",
        "flux_cm2_min",
        "eff_p1",
        "eff_p2",
        "eff_sim_1",
        "eff_sim_2",
    ]
    assert info["general_columns"] == [
        "filename_base",
        "task_id",
        "z_plane_1",
        "z_plane_2",
    ]
    assert info["parameter_columns"] == [
        "flux_cm2_min",
        "eff_p1",
        "eff_p2",
        "eff_sim_1",
        "eff_sim_2",
    ]


def test_feature_space_plot_suppression_patterns_drive_group_placeholders() -> None:
    feature_cols = [
        "events_per_second_0_rate_hz",
        "events_per_second_1_rate_hz",
        "efficiency_vector_p1_x_bin_0_eff",
        "efficiency_vector_p1_x_bin_1_eff",
        "post_tt_two_plane_total_rate_hz",
    ]
    patterns = _resolve_feature_space_plot_suppression_patterns(
        {"feature_space_lower_triangle_suppressed_patterns": ["events_per_second_*", "efficiency_vector_*"]}
    )

    plot_cols, hist_cols, eff_cols, hist_placeholder_added, eff_placeholder_added = (
        _resolve_feature_matrix_plot_columns(
            feature_cols,
            include_rate_histogram=True,
            include_efficiency_vectors=True,
            suppressed_patterns=patterns,
        )
    )

    assert patterns == ["events_per_second_*", "efficiency_vector_*"]
    assert plot_cols == [
        "post_tt_two_plane_total_rate_hz",
        RATE_HIST_PLACEHOLDER_COL,
        EFF_PLACEHOLDER_COL,
    ]
    assert hist_cols == [
        "events_per_second_0_rate_hz",
        "events_per_second_1_rate_hz",
    ]
    assert eff_cols == [
        "efficiency_vector_p1_x_bin_0_eff",
        "efficiency_vector_p1_x_bin_1_eff",
    ]
    assert hist_placeholder_added is True
    assert eff_placeholder_added is True
