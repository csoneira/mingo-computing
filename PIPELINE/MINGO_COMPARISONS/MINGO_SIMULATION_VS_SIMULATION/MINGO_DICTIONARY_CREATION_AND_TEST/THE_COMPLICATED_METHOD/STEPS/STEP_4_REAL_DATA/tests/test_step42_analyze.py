#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_STEP42_DIR = (
    Path(__file__).resolve().parent.parent / "STEP_4_2_ANALYZE"
)
sys.path.insert(0, str(_STEP42_DIR))

from analyze import (  # noqa: E402
    _compute_efficiency_vector_median_proxies,
    _load_eff_fit_lines,
    _mask_sim_eff_within_tolerance_band,
    _plot_distance_term_dominance,
    _plot_estimated_curve_flux_vs_eff,
    _plot_grouped_case_diagnostic_real,
    _plot_inverse_estimate_vs_k1_proxy_case,
    _plot_parameter_estimate_series,
    _plot_parameter_estimate_series_vs_k1,
    _resolve_efficiency_calibration_summary_path,
    _resolve_selected_step12_feature_columns_strict,
    _resolve_estimation_parameter_columns,
)


def test_resolve_estimation_parameter_columns_uses_default_parameter_space_order() -> None:
    dictionary_df = pd.DataFrame(columns=["flux_only", "cos_n", "eff_sim_3"])

    resolved = _resolve_estimation_parameter_columns(
        dictionary_df=dictionary_df,
        configured_columns=None,
        default_columns=["flux_only", "missing_col", "cos_n"],
    )

    assert resolved == ["flux_only", "cos_n"]


def test_mask_sim_eff_within_tolerance_band_uses_available_eff_columns() -> None:
    df = pd.DataFrame(
        {
            "eff_sim_1": [0.80, 0.80],
            "eff_sim_2": [0.81, 0.95],
            "eff_sim_3": [0.79, 0.96],
        }
    )

    mask = _mask_sim_eff_within_tolerance_band(df, tolerance_pct=5.0)

    assert mask.tolist() == [True, False]


def test_compute_efficiency_vector_median_proxies_returns_planewise_medians() -> None:
    df = pd.DataFrame(
        {
            "efficiency_vector_p1_x_bin_000_eff": [0.8, 0.6],
            "efficiency_vector_p1_x_bin_001_eff": [0.9, 0.7],
            "efficiency_vector_p2_x_bin_000_eff": [0.5, 0.4],
        }
    )

    proxies, meta = _compute_efficiency_vector_median_proxies(df)

    assert proxies[1].round(6).tolist() == [0.85, 0.65]
    assert proxies[2].round(6).tolist() == [0.5, 0.4]
    assert proxies[3].isna().all()
    assert int(meta[1]["columns_count"]) == 2
    assert "efficiency_vector_p1_x_bin_000_eff" in meta[1]["columns"]


def test_load_eff_fit_lines_supports_step13_nested_efficiency_fit_models(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "step13_build_summary.json"
    summary_path.write_text(
        """
        {
          "efficiency_fit": {
            "polynomial_order_requested": 4,
            "models": {
              "plane_2": {
                "coefficients_desc": [1.5, -0.2, 0.1],
                "order_used": 2
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )

    fit_lines, status, payload = _load_eff_fit_lines(summary_path)

    assert status == "ok"
    assert fit_lines[2] == [1.5, -0.2, 0.1]
    assert payload["efficiency_fit"]["polynomial_order_requested"] == 4


def test_resolve_efficiency_calibration_summary_path_falls_back_to_step13(
    tmp_path: Path,
) -> None:
    wrong_summary = tmp_path / "step14_build_summary.json"
    wrong_summary.write_text('{"continuity_validation": {"status": "ok"}}', encoding="utf-8")
    calibration_summary = tmp_path / "step13_build_summary.json"
    calibration_summary.write_text(
        """
        {
          "efficiency_fit": {
            "models": {
              "plane_1": {
                "coefficients_desc": [0.9, 0.1]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )

    resolved, reason, _ = _resolve_efficiency_calibration_summary_path(
        wrong_summary,
        fallback_path=calibration_summary,
    )

    assert resolved == calibration_summary
    assert reason == "fallback_contains_efficiency_calibration"


def test_plot_estimated_curve_flux_vs_eff_supports_generic_parameter_columns(
    tmp_path: Path,
) -> None:
    real_df = pd.DataFrame(
        {
            "est_flux_only": [1.0, 1.5, 2.0],
            "est_cos_n": [0.2, 0.4, 0.6],
        }
    )
    dict_df = pd.DataFrame(
        {
            "flux_only": [0.8, 1.4, 2.2],
            "cos_n": [0.1, 0.5, 0.7],
        }
    )
    out_path = tmp_path / "parameter_space_curve.png"

    n_real, n_dict = _plot_estimated_curve_flux_vs_eff(
        real_df=real_df,
        dict_df=dict_df,
        parameter_columns=["flux_only", "cos_n"],
        out_path=out_path,
    )

    assert n_real == 3
    assert n_dict == 3
    assert out_path.exists()


def test_plot_parameter_estimate_series_supports_generic_parameter_columns(
    tmp_path: Path,
) -> None:
    df = pd.DataFrame(
        {
            "est_flux_only": [1.0, 1.4, 1.8],
            "unc_flux_only_abs": [0.1, 0.1, 0.2],
            "est_cos_n": [2.0, 2.1, 1.9],
            "unc_cos_n_abs": [0.05, 0.04, 0.05],
        }
    )
    out_path = tmp_path / "parameter_series.png"

    n_panels = _plot_parameter_estimate_series(
        x=pd.Series([0.0, 1.0, 2.0]),
        has_time_axis=False,
        xlabel="Row index",
        df=df,
        parameter_columns=["flux_only", "cos_n"],
        out_path=out_path,
    )

    assert n_panels == 2
    assert out_path.exists()


def test_plot_parameter_estimate_series_vs_k1_supports_overlay(
    tmp_path: Path,
) -> None:
    df = pd.DataFrame(
        {
            "est_flux_only": [1.0, 1.4, 1.8],
            "k1_est_flux_only": [0.9, 1.5, 1.7],
            "unc_flux_only_abs": [0.1, 0.1, 0.2],
            "est_cos_n": [2.0, 2.1, 1.9],
            "k1_est_cos_n": [1.8, 2.0, 2.05],
            "unc_cos_n_abs": [0.05, 0.04, 0.05],
        }
    )
    out_path = tmp_path / "parameter_series_vs_k1.png"

    n_panels = _plot_parameter_estimate_series_vs_k1(
        x=pd.Series([0.0, 1.0, 2.0]),
        has_time_axis=False,
        xlabel="Row index",
        df=df,
        parameter_columns=["flux_only", "cos_n"],
        out_path=out_path,
    )

    assert n_panels == 2
    assert out_path.exists()


def test_plot_distance_term_dominance_supports_dynamic_terms_and_scalar_features(
    tmp_path: Path,
) -> None:
    df = pd.DataFrame(
        {
            "best_distance": [1.0, 1.2, 0.8],
            "best_distance_term_shares_json": [
                "{\"rate_histogram\": 0.7, \"efficiency_vectors\": 0.3}",
                "{\"scalar_base\": 0.2, \"rate_histogram\": 0.5, \"efficiency_vectors\": 0.3}",
                "{\"scalar_base\": 0.6, \"efficiency_vectors\": 0.4}",
            ],
            "best_distance_scalar_feature_shares_json": [
                None,
                "{\"post_tt_123_rate_hz\": 0.12, \"eff_empirical_2\": 0.08}",
                "{\"post_tt_123_rate_hz\": 0.35, \"eff_empirical_2\": 0.25}",
            ],
            "best_distance_group_component_shares_json": [
                "{\"rate_histogram::events_per_second_0_rate_hz\": 0.45, \"rate_histogram::events_per_second_1_rate_hz\": 0.25, \"efficiency_vectors::p1_x\": 0.30}",
                "{\"scalar_base\": 0.0, \"rate_histogram::events_per_second_0_rate_hz\": 0.20, \"efficiency_vectors::p1_y\": 0.30}",
                "{\"efficiency_vectors::p1_x\": 0.10, \"efficiency_vectors::p2_theta\": 0.30}",
            ],
            "best_distance_group_component_within_term_shares_json": [
                "{\"rate_histogram::events_per_second_0_rate_hz\": 0.64, \"rate_histogram::events_per_second_1_rate_hz\": 0.36, \"efficiency_vectors::p1_x\": 1.0}",
                "{\"rate_histogram::events_per_second_0_rate_hz\": 1.0, \"efficiency_vectors::p1_y\": 1.0}",
                "{\"efficiency_vectors::p1_x\": 0.25, \"efficiency_vectors::p2_theta\": 0.75}",
            ],
        }
    )
    out_path = tmp_path / "distance_term_dominance.png"

    summary = _plot_distance_term_dominance(
        x=pd.Series([0.0, 1.0, 2.0]),
        has_time_axis=False,
        xlabel="Row index",
        df=df,
        out_path=out_path,
    )

    assert out_path.exists()
    assert summary["plot_available"] is True
    assert int(summary["n_rows"]) == 3
    assert "rate_histogram" in summary["term_median_share"]
    assert "efficiency_vectors" in summary["term_dominant_fraction"]
    assert "post_tt_123_rate_hz" in summary["top_scalar_feature_median_share"]
    assert "rate_histogram::events_per_second_0_rate_hz" in summary["top_group_component_median_total_share"]
    assert "efficiency_vectors::p2_theta" in summary["top_group_component_median_within_term_share"]


def test_plot_grouped_case_diagnostic_real_writes_step42_outputs(
    tmp_path: Path,
) -> None:
    dict_df = pd.DataFrame(
        {
            "events_per_second_0_rate_hz": [10.0, 25.0, 40.0],
            "events_per_second_1_rate_hz": [12.0, 26.0, 39.0],
            "flux_cm2_min": [1.0, 2.0, 3.0],
            "filename_base": ["dict_a", "dict_b", "dict_c"],
        }
    )
    data_df = pd.DataFrame(
        {
            "events_per_second_0_rate_hz": [11.0, 38.0],
            "events_per_second_1_rate_hz": [13.0, 37.0],
        }
    )
    result_df = pd.DataFrame(
        {
            "dataset_index": [0, 1],
            "best_distance": [0.1, 0.8],
            "est_flux_cm2_min": [1.1, 2.8],
            "filename_base": ["real_a", "real_b"],
        }
    )
    distance_definition = {
        "available": True,
        "feature_groups": {
            "rate_histogram": {
                "feature_columns": [
                    "events_per_second_0_rate_hz",
                    "events_per_second_1_rate_hz",
                ]
            }
        },
        "group_weights": {"rate_histogram": 1.0},
        "center": [0.0, 0.0],
        "scale": [1.0, 1.0],
        "weights": [0.0, 0.0],
        "p_norm": 2.0,
        "scalar_feature_columns": [],
    }
    out_path = tmp_path / "STEP_4_2_9_grouped_case_top_matches.png"
    neighbors_path = tmp_path / "step_4_2_grouped_case_top_neighbors.csv"

    summary = _plot_grouped_case_diagnostic_real(
        dict_df=dict_df,
        data_df=data_df,
        result_df=result_df,
        param_cols=["flux_cm2_min"],
        feature_cols=[
            "events_per_second_0_rate_hz",
            "events_per_second_1_rate_hz",
        ],
        distance_definition=distance_definition,
        case_selector="largest_best_distance",
        top_k=2,
        out_path=out_path,
        neighbors_csv_path=neighbors_path,
    )

    assert summary["plot_available"] is True
    assert int(summary["dataset_index"]) == 1
    assert summary["filename_base"] == "real_b"
    assert summary["histogram_plotted"] is True
    assert out_path.exists()
    assert neighbors_path.exists()


def test_plot_inverse_estimate_vs_k1_proxy_case_writes_outputs(
    tmp_path: Path,
) -> None:
    dict_df = pd.DataFrame(
        {
            "flux_cm2_min": [1.0, 2.0, 3.0],
            "eff_sim_1": [0.80, 0.85, 0.90],
            "eff_sim_2": [0.78, 0.83, 0.88],
            "filename_base": ["dict_a", "dict_b", "dict_c"],
        }
    )
    result_df = pd.DataFrame(
        {
            "dataset_index": [0, 1],
            "best_distance": [0.1, 0.8],
            "est_flux_cm2_min": [1.1, 2.8],
            "est_eff_sim_1": [0.81, 0.89],
            "est_eff_sim_2": [0.79, 0.86],
            "filename_base": ["real_a", "real_b"],
        }
    )
    grouped_case_summary = {
        "plot_available": True,
        "row_position": 1,
        "dataset_index": 1,
        "filename_base": "real_b",
        "best_dictionary_index": 2,
        "best_dictionary_filename_base": "dict_c",
        "best_distance": 0.8,
    }
    out_path = tmp_path / "STEP_4_2_10_inverse_estimate_vs_k1_proxy.png"
    out_csv = tmp_path / "step_4_2_inverse_estimate_vs_k1_proxy.csv"

    summary = _plot_inverse_estimate_vs_k1_proxy_case(
        dict_df=dict_df,
        result_df=result_df,
        param_cols=["flux_cm2_min", "eff_sim_1", "eff_sim_2"],
        grouped_case_summary=grouped_case_summary,
        inverse_mapping_cfg={
            "aggregation": "weighted_median",
            "neighbor_selection": "knn",
            "neighbor_count": 15,
        },
        out_path=out_path,
        out_csv_path=out_csv,
    )

    assert summary["plot_available"] is True
    assert int(summary["dataset_index"]) == 1
    assert int(summary["best_dictionary_index"]) == 2
    assert out_path.exists()
    assert out_csv.exists()


def test_resolve_selected_step12_feature_columns_strict_rejects_feature_drift() -> None:
    dict_df = pd.DataFrame({"feature_a": [1.0], "feature_b": [2.0]})
    real_df = pd.DataFrame({"feature_a": [1.5]})

    try:
        _resolve_selected_step12_feature_columns_strict(
            ["feature_a", "feature_b"],
            dict_df=dict_df,
            real_df=real_df,
        )
    except ValueError as exc:
        assert "missing in real data" in str(exc)
        assert "feature_b" in str(exc)
    else:
        raise AssertionError("Expected ValueError for selected-feature drift")
