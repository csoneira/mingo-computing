#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_STEP41_DIR = (
    Path(__file__).resolve().parent.parent / "STEP_4_1_COLLECT_REAL_DATA"
)
sys.path.insert(0, str(_STEP41_DIR))

import collect_real_data as step41  # noqa: E402
from collect_real_data import (  # noqa: E402
    _enforce_complete_estimation_feature_space,
    _make_grouped_feature_space_comparison_plot,
    _nonobservable_efficiency_columns,
    _resolve_tt_rate_breakdown_entries,
    _sim_efficiency_columns,
)


def test_sim_efficiency_columns_uses_regex_ordering() -> None:
    df = pd.DataFrame(
        {
            "eff_sim_10": [0.8],
            "eff_sim_2": [0.7],
            "eff_sim_1": [0.6],
            "other": [1.0],
        }
    )

    assert _sim_efficiency_columns(df) == ["eff_sim_1", "eff_sim_2", "eff_sim_10"]


def test_nonobservable_efficiency_columns_includes_eff_p_and_eff_sim() -> None:
    df = pd.DataFrame(
        {
            "eff_p2": [0.7],
            "eff_sim_3": [0.8],
            "eff_p1": [0.6],
            "eff_sim_1": [0.5],
            "keep_me": [1.0],
        }
    )

    assert _nonobservable_efficiency_columns(df) == [
        "eff_p1",
        "eff_p2",
        "eff_sim_1",
        "eff_sim_3",
    ]


def test_resolve_tt_rate_breakdown_entries_prefers_physical_post_columns() -> None:
    df = pd.DataFrame(
        {
            "fit_to_post_tt_123_rate_hz": [9.9],
            "fit_tt_123_rate_hz": [1.4],
            "post_tt_123_rate_hz": [1.1],
            "events_per_second_global_rate": [8.0],
        }
    )

    assert _resolve_tt_rate_breakdown_entries(df) == [("123", "post_tt_123_rate_hz")]


def test_resolve_tt_rate_breakdown_entries_supports_expanded_tt_labels() -> None:
    df = pd.DataFrame(
        {
            "post_tt_124_rate_hz": [1.2],
            "post_tt_134_rate_hz": [0.9],
            "post_tt_13_rate_hz": [0.5],
            "post_tt_14_rate_hz": [0.4],
            "post_tt_24_rate_hz": [0.6],
        }
    )

    assert _resolve_tt_rate_breakdown_entries(df) == [
        ("124", "post_tt_124_rate_hz"),
        ("134", "post_tt_134_rate_hz"),
        ("13", "post_tt_13_rate_hz"),
        ("14", "post_tt_14_rate_hz"),
        ("24", "post_tt_24_rate_hz"),
    ]


def test_grouped_feature_space_comparison_plot_handles_hist_and_eff_vectors(
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "grouped_feature_comparison.png"
    step41.PLOT_FEATURE_MATRIX = out_path
    real_df = pd.DataFrame(
        {
            "events_per_second_0_rate_hz": [0.6, 0.5],
            "events_per_second_1_rate_hz": [0.4, 0.5],
            "efficiency_vector_p1_x_bin_0_center_mm": [-50.0, -50.0],
            "efficiency_vector_p1_x_bin_1_center_mm": [50.0, 50.0],
            "efficiency_vector_p1_x_bin_0_eff": [0.82, 0.84],
            "efficiency_vector_p1_x_bin_1_eff": [0.88, 0.90],
            "efficiency_vector_p1_x_bin_0_unc": [0.03, 0.03],
            "efficiency_vector_p1_x_bin_1_unc": [0.03, 0.03],
        }
    )
    dict_df = pd.DataFrame(
        {
            "events_per_second_0_rate_hz": [0.7, 0.68, 0.66],
            "events_per_second_1_rate_hz": [0.3, 0.32, 0.34],
            "efficiency_vector_p1_x_bin_0_center_mm": [-50.0, -50.0, -50.0],
            "efficiency_vector_p1_x_bin_1_center_mm": [50.0, 50.0, 50.0],
            "efficiency_vector_p1_x_bin_0_eff": [0.80, 0.81, 0.82],
            "efficiency_vector_p1_x_bin_1_eff": [0.86, 0.87, 0.88],
            "efficiency_vector_p1_x_bin_0_unc": [0.02, 0.02, 0.02],
            "efficiency_vector_p1_x_bin_1_unc": [0.02, 0.02, 0.02],
        }
    )

    summary = _make_grouped_feature_space_comparison_plot(
        real_df,
        dict_df,
        selected_feature_cols=[
            "events_per_second_0_rate_hz",
            "events_per_second_1_rate_hz",
        ],
    )

    assert out_path.exists()
    assert summary["status"] == "ok"
    assert int(summary["rate_histogram_bins_used"]) == 2
    assert int(summary["efficiency_vector_groups_used"]) == 1


def test_enforce_complete_estimation_feature_space_drops_incomplete_rows() -> None:
    df = pd.DataFrame(
        {
            "feature_a": [1.0, 2.0, None],
            "feature_b": [3.0, None, 5.0],
            "other": [10, 11, 12],
        }
    )

    filtered, info = _enforce_complete_estimation_feature_space(
        df,
        selected_feature_columns=["feature_a", "feature_b"],
        feature_manifest=None,
    )

    assert filtered.to_dict(orient="list") == {
        "feature_a": [1.0],
        "feature_b": [3.0],
        "other": [10],
    }
    assert info["feature_columns_source"] == "step_1_4.selected_feature_columns"
    assert int(info["rows_removed"]) == 2
    assert int(info["rows_kept"]) == 1


def test_enforce_complete_estimation_feature_space_requires_all_selected_columns() -> None:
    df = pd.DataFrame(
        {
            "feature_a": [1.0, 2.0],
            "other": [10, 11],
        }
    )

    try:
        _enforce_complete_estimation_feature_space(
            df,
            selected_feature_columns=["feature_a", "feature_b"],
            feature_manifest=None,
        )
    except ValueError as exc:
        assert "feature_b" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing selected feature columns")
