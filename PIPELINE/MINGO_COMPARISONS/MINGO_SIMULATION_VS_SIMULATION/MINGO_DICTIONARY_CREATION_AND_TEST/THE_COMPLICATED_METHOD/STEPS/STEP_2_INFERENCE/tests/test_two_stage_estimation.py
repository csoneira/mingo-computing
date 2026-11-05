#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_INFERENCE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_INFERENCE_DIR))

from estimate_parameters import (
    _filter_efficiency_vector_payloads,
    _prepare_efficiency_vector_group_payloads,
    build_step15_runtime_inverse_mapping_cfg,
    build_efficiency_vector_local_linear_embedding,
    build_rate_histogram_local_linear_embedding,
    estimate_from_dataframes,
    _resolve_efficiency_vector_distance_cfg,
    _resolve_histogram_distance_cfg,
)


def _toy_dictionary() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "z_plane_1": [0.0, 0.0, 0.0],
            "z_plane_2": [65.0, 65.0, 65.0],
            "z_plane_3": [130.0, 130.0, 130.0],
            "z_plane_4": [195.0, 195.0, 195.0],
            "flux_cm2_min": [1.0, 1.8, 2.5],
            "cos_n": [2.0, 2.0, 2.0],
            "eff_sim_1": [0.90, 0.75, 0.60],
            "eff_sim_2": [0.89, 0.74, 0.59],
            "eff_sim_3": [0.88, 0.73, 0.58],
            "eff_sim_4": [0.87, 0.72, 0.57],
            "eff_empirical_1": [0.88, 0.73, 0.58],
            "eff_empirical_2": [0.87, 0.72, 0.57],
            "eff_empirical_3": [0.86, 0.71, 0.56],
            "eff_empirical_4": [0.85, 0.70, 0.55],
            "__derived_tt_global_rate_hz": [90.0, 100.0, 110.0],
            "events_per_second_0_rate_hz": [40.0, 55.0, 70.0],
            "events_per_second_1_rate_hz": [30.0, 26.0, 22.0],
            "events_per_second_2_rate_hz": [10.0, 19.0, 28.0],
            "efficiency_vector_p1_x_bin_000_center_mm": [50.0, 50.0, 50.0],
            "efficiency_vector_p1_x_bin_000_eff": [0.88, 0.72, 0.56],
            "efficiency_vector_p1_x_bin_000_unc": [0.03, 0.03, 0.03],
        }
    )


def test_two_stage_mode_populates_stage_diagnostics_and_flux() -> None:
    dict_df = _toy_dictionary()
    data_df = pd.DataFrame(
        {
            "z_plane_1": [0.0],
            "z_plane_2": [65.0],
            "z_plane_3": [130.0],
            "z_plane_4": [195.0],
            "eff_empirical_1": [0.79],
            "eff_empirical_2": [0.78],
            "eff_empirical_3": [0.77],
            "eff_empirical_4": [0.76],
            "__derived_tt_global_rate_hz": [103.0],
            "events_per_second_0_rate_hz": [56.0],
            "events_per_second_1_rate_hz": [25.0],
            "events_per_second_2_rate_hz": [19.0],
            "efficiency_vector_p1_x_bin_000_center_mm": [50.0],
            "efficiency_vector_p1_x_bin_000_eff": [0.73],
            "efficiency_vector_p1_x_bin_000_unc": [0.03],
            "flux_cm2_min": [1.8],
            "cos_n": [2.0],
            "eff_sim_1": [0.75],
            "eff_sim_2": [0.74],
            "eff_sim_3": [0.73],
            "eff_sim_4": [0.72],
        }
    )
    features = [
        "eff_empirical_1",
        "eff_empirical_2",
        "eff_empirical_3",
        "eff_empirical_4",
        "__derived_tt_global_rate_hz",
    ]

    out = estimate_from_dataframes(
        dict_df=dict_df,
        data_df=data_df,
        feature_columns=features,
        distance_metric="l2_zscore",
        interpolation_k=2,
        include_global_rate=False,
        exclude_same_file=False,
        inverse_mapping_cfg={
            "estimation_mode": "two_stage_eff_address_then_flux",
            "neighbor_selection": "knn",
            "neighbor_count": 2,
            "weighting": "inverse_distance",
            "aggregation": "weighted_mean",
            "stage2_efficiency_conditioning_weight": 1.0,
            "stage2_efficiency_gate_max": 0.20,
            "stage2_efficiency_gate_min_candidates": 1,
            "stage2_use_rate_histogram": True,
            "stage2_histogram_distance_weight": 1.0,
            "efficiency_vector_distance": {
                "enabled": True,
                "weight": 1.0,
                "blend_mode": "normalized",
                "stage2_enabled": True,
                "stage2_weight": 1.0,
                "uncertainty_floor": 0.02,
                "min_valid_bins_per_vector": 1,
                "fiducial": {"x_abs_max_mm": 100.0},
            },
        },
    )

    assert "estimation_mode_used" in out.columns
    assert str(out.loc[0, "estimation_mode_used"]) == "two_stage_eff_address_then_flux"
    assert int(out.loc[0, "n_neighbors_stage1"]) > 0
    assert int(out.loc[0, "n_neighbors_stage2"]) > 0
    assert int(out.loc[0, "stage2_candidates_before_gate"]) > 0
    assert int(out.loc[0, "stage2_candidates_after_gate"]) > 0
    assert int(out.loc[0, "stage2_candidates_after_gate"]) <= int(out.loc[0, "stage2_candidates_before_gate"])
    assert int(out.loc[0, "stage2_histogram_bins_used"]) >= 3
    assert int(out.loc[0, "efficiency_vector_groups_used"]) >= 1
    assert int(out.loc[0, "stage2_efficiency_vector_groups_used"]) >= 1
    assert np.isfinite(float(out.loc[0, "stage1_best_distance_eff"]))
    assert np.isfinite(float(out.loc[0, "stage2_best_distance_rate"]))
    assert np.isfinite(float(out.loc[0, "best_distance_efficiency_vector"]))
    flux_est = float(out.loc[0, "est_flux_cm2_min"])
    assert np.isfinite(flux_est)
    assert 1.0 <= flux_est <= 2.5


def test_efficiency_vector_fiducial_controls_single_stage_match() -> None:
    dict_df = pd.DataFrame(
        {
            "z_plane_1": [0.0, 0.0],
            "z_plane_2": [65.0, 65.0],
            "z_plane_3": [130.0, 130.0],
            "z_plane_4": [195.0, 195.0],
            "flux_cm2_min": [1.0, 2.0],
            "eff_empirical_1": [0.80, 0.80],
            "efficiency_vector_p1_x_bin_000_center_mm": [50.0, 50.0],
            "efficiency_vector_p1_x_bin_000_eff": [0.70, 0.40],
            "efficiency_vector_p1_x_bin_000_unc": [0.02, 0.02],
            "efficiency_vector_p1_x_bin_001_center_mm": [150.0, 150.0],
            "efficiency_vector_p1_x_bin_001_eff": [0.30, 0.90],
            "efficiency_vector_p1_x_bin_001_unc": [0.02, 0.02],
        }
    )
    data_df = pd.DataFrame(
        {
            "z_plane_1": [0.0],
            "z_plane_2": [65.0],
            "z_plane_3": [130.0],
            "z_plane_4": [195.0],
            "eff_empirical_1": [0.80],
            "efficiency_vector_p1_x_bin_000_center_mm": [50.0],
            "efficiency_vector_p1_x_bin_000_eff": [0.70],
            "efficiency_vector_p1_x_bin_000_unc": [0.02],
            "efficiency_vector_p1_x_bin_001_center_mm": [150.0],
            "efficiency_vector_p1_x_bin_001_eff": [0.90],
            "efficiency_vector_p1_x_bin_001_unc": [0.02],
        }
    )

    no_fiducial = estimate_from_dataframes(
        dict_df=dict_df,
        data_df=data_df,
        feature_columns=["eff_empirical_1"],
        param_columns=["flux_cm2_min"],
        distance_metric="l2_zscore",
        interpolation_k=1,
        include_global_rate=False,
        exclude_same_file=False,
        inverse_mapping_cfg={
            "neighbor_selection": "nearest",
            "aggregation": "weighted_mean",
            "efficiency_vector_distance": {
                "enabled": True,
                "weight": 1.0,
                "blend_mode": "raw",
                "stage2_enabled": False,
                "uncertainty_floor": 0.01,
                "min_valid_bins_per_vector": 1,
                "fiducial": {
                    "x_abs_max_mm": None,
                },
            },
        },
    )
    with_fiducial = estimate_from_dataframes(
        dict_df=dict_df,
        data_df=data_df,
        feature_columns=["eff_empirical_1"],
        param_columns=["flux_cm2_min"],
        distance_metric="l2_zscore",
        interpolation_k=1,
        include_global_rate=False,
        exclude_same_file=False,
        inverse_mapping_cfg={
            "neighbor_selection": "nearest",
            "aggregation": "weighted_mean",
            "efficiency_vector_distance": {
                "enabled": True,
                "weight": 1.0,
                "blend_mode": "raw",
                "stage2_enabled": False,
                "uncertainty_floor": 0.01,
                "min_valid_bins_per_vector": 1,
                "fiducial": {
                    "x_abs_max_mm": 100.0,
                },
            },
        },
    )

    assert float(no_fiducial.loc[0, "est_flux_cm2_min"]) == 2.0
    assert float(with_fiducial.loc[0, "est_flux_cm2_min"]) == 1.0
    assert int(with_fiducial.loc[0, "efficiency_vector_groups_used"]) == 1
    assert np.isfinite(float(with_fiducial.loc[0, "best_distance_efficiency_vector"]))


def test_histogram_and_efficiency_group_metric_resolvers_support_expanded_modes() -> None:
    hist_cfg = _resolve_histogram_distance_cfg(
        {
            "distance": "histogram_jsd",
            "shape_weight": 2.0,
            "mass_weight": 0.25,
        }
    )
    assert hist_cfg["distance"] == "ordered_vector_lp"
    assert hist_cfg["normalization"] == "unit_sum"
    assert float(hist_cfg["p_norm"]) == 1.0
    assert float(hist_cfg["shape_weight"]) == 2.0
    assert float(hist_cfg["cdf_weight"]) == 0.5
    assert float(hist_cfg["amplitude_weight"]) == 0.25
    assert float(hist_cfg["mass_weight"]) == 0.25

    eff_cfg = _resolve_efficiency_vector_distance_cfg(
        {
            "distance": "uncertainty_weighted_vector_l1_rms",
            "uncertainty_floor": 0.05,
            "min_valid_bins_per_vector": 4,
        }
    )
    assert eff_cfg["distance"] == "ordered_vector_lp"
    assert float(eff_cfg["p_norm"]) == 1.0
    assert eff_cfg["pointwise_loss"] == "l1"
    assert eff_cfg["group_reduction"] == "rms"
    assert float(eff_cfg["uncertainty_floor"]) == 0.05
    assert int(eff_cfg["min_valid_bins_per_vector"]) == 4


def test_distance_definition_group_weights_drive_histogram_group_distance() -> None:
    dict_df = pd.DataFrame(
        {
            "z_plane_1": [0.0, 0.0],
            "z_plane_2": [65.0, 65.0],
            "z_plane_3": [130.0, 130.0],
            "z_plane_4": [195.0, 195.0],
            "flux_cm2_min": [1.0, 2.0],
            "events_per_second_0_rate_hz": [0.90, 0.10],
            "events_per_second_1_rate_hz": [0.10, 0.90],
        }
    )
    data_df = pd.DataFrame(
        {
            "z_plane_1": [0.0],
            "z_plane_2": [65.0],
            "z_plane_3": [130.0],
            "z_plane_4": [195.0],
            "events_per_second_0_rate_hz": [0.85],
            "events_per_second_1_rate_hz": [0.15],
        }
    )

    out = estimate_from_dataframes(
        dict_df=dict_df,
        data_df=data_df,
        feature_columns=[
            "events_per_second_0_rate_hz",
            "events_per_second_1_rate_hz",
        ],
        param_columns=["flux_cm2_min"],
        distance_metric="l2_zscore",
        interpolation_k=1,
        include_global_rate=False,
        exclude_same_file=False,
        inverse_mapping_cfg={
            "neighbor_selection": "nearest",
            "histogram_distance_weight": 0.0,
            "stage2_use_rate_histogram": False,
        },
        distance_definition={
            "available": True,
            "center": np.asarray([0.0, 0.0], dtype=float),
            "scale": np.asarray([1.0, 1.0], dtype=float),
            "weights": np.asarray([0.0, 0.0], dtype=float),
            "p_norm": 1.0,
            "optimal_k": 1,
            "optimal_lambda": 1e6,
            "selected_mode": "test_grouped_hist",
            "group_weights": {"rate_histogram": 1.0},
            "feature_groups": {
                "rate_histogram": {
                    "feature_columns": [
                        "events_per_second_0_rate_hz",
                        "events_per_second_1_rate_hz",
                    ],
                    "blend_mode": "raw",
                }
            },
        },
    )

    assert float(out.loc[0, "est_flux_cm2_min"]) == 1.0
    assert np.isfinite(float(out.loc[0, "best_distance_hist_emd"]))
    term_shares = json.loads(str(out.loc[0, "best_distance_term_shares_json"]))
    assert "rate_histogram" in term_shares
    assert float(term_shares["rate_histogram"]) > 0.0
    assert str(out.loc[0, "best_distance_dominant_term"]) == "rate_histogram"
    comp_total = json.loads(str(out.loc[0, "best_distance_group_component_shares_json"]))
    comp_within = json.loads(str(out.loc[0, "best_distance_group_component_within_term_shares_json"]))
    assert "rate_histogram::events_per_second_0_rate_hz" in comp_total
    assert abs(sum(value for key, value in comp_within.items() if key.startswith("rate_histogram::")) - 1.0) < 1e-6


def test_grouped_histogram_distance_works_without_scalar_histogram_features() -> None:
    dict_df = pd.DataFrame(
        {
            "z_plane_1": [0.0, 0.0],
            "z_plane_2": [65.0, 65.0],
            "z_plane_3": [130.0, 130.0],
            "z_plane_4": [195.0, 195.0],
            "flux_cm2_min": [1.0, 2.0],
            "eff_empirical_2": [0.7, 0.7],
            "events_per_second_0_rate_hz": [0.90, 0.10],
            "events_per_second_1_rate_hz": [0.10, 0.90],
        }
    )
    data_df = pd.DataFrame(
        {
            "z_plane_1": [0.0],
            "z_plane_2": [65.0],
            "z_plane_3": [130.0],
            "z_plane_4": [195.0],
            "eff_empirical_2": [0.7],
            "events_per_second_0_rate_hz": [0.85],
            "events_per_second_1_rate_hz": [0.15],
        }
    )

    out = estimate_from_dataframes(
        dict_df=dict_df,
        data_df=data_df,
        feature_columns=["eff_empirical_2"],
        param_columns=["flux_cm2_min"],
        distance_metric="l2_zscore",
        interpolation_k=1,
        include_global_rate=False,
        exclude_same_file=False,
        inverse_mapping_cfg={
            "neighbor_selection": "nearest",
            "histogram_distance_weight": 0.0,
            "stage2_use_rate_histogram": False,
        },
        distance_definition={
            "available": True,
            "center": np.asarray([0.0], dtype=float),
            "scale": np.asarray([1.0], dtype=float),
            "weights": np.asarray([0.0], dtype=float),
            "p_norm": 1.0,
            "optimal_k": 1,
            "optimal_lambda": 1e6,
            "selected_mode": "test_grouped_hist_only",
            "group_weights": {"rate_histogram": 1.0},
            "feature_groups": {
                "rate_histogram": {
                    "feature_columns": [
                        "events_per_second_0_rate_hz",
                        "events_per_second_1_rate_hz",
                    ],
                    "blend_mode": "raw",
                }
            },
        },
    )

    assert float(out.loc[0, "est_flux_cm2_min"]) == 1.0
    assert np.isfinite(float(out.loc[0, "best_distance_hist_emd"]))
    term_shares = json.loads(str(out.loc[0, "best_distance_term_shares_json"]))
    assert term_shares == {"rate_histogram": 1.0}
    comp_total = json.loads(str(out.loc[0, "best_distance_group_component_shares_json"]))
    assert set(comp_total) == {"rate_histogram::events_per_second_0_rate_hz"}


def test_distance_definition_generic_ordered_vector_group_is_supported() -> None:
    dict_df = pd.DataFrame(
        {
            "z_plane_1": [0.0, 0.0],
            "z_plane_2": [65.0, 65.0],
            "z_plane_3": [130.0, 130.0],
            "z_plane_4": [195.0, 195.0],
            "flux_cm2_min": [1.0, 2.0],
            "post_tt_12_rate_hz": [10.0, 20.0],
            "post_tt_23_rate_hz": [20.0, 10.0],
        }
    )
    data_df = pd.DataFrame(
        {
            "z_plane_1": [0.0],
            "z_plane_2": [65.0],
            "z_plane_3": [130.0],
            "z_plane_4": [195.0],
            "post_tt_12_rate_hz": [11.0],
            "post_tt_23_rate_hz": [19.0],
        }
    )

    out = estimate_from_dataframes(
        dict_df=dict_df,
        data_df=data_df,
        feature_columns=["post_tt_12_rate_hz", "post_tt_23_rate_hz"],
        param_columns=["flux_cm2_min"],
        distance_metric="l2_zscore",
        interpolation_k=1,
        include_global_rate=False,
        exclude_same_file=False,
        inverse_mapping_cfg={"neighbor_selection": "nearest"},
        distance_definition={
            "available": True,
            "center": np.asarray([0.0, 0.0], dtype=float),
            "scale": np.asarray([1.0, 1.0], dtype=float),
            "weights": np.asarray([0.0, 0.0], dtype=float),
            "p_norm": 2.0,
            "optimal_k": 1,
            "optimal_lambda": 1e6,
            "selected_mode": "test_generic_group",
            "group_weights": {"tt_rates_group": 1.0},
            "feature_groups": {
                "tt_rates_group": {
                    "group_type": "ordered_vector",
                    "feature_columns": [
                        "post_tt_12_rate_hz",
                        "post_tt_23_rate_hz",
                    ],
                    "blend_mode": "raw",
                    "normalization": "none",
                    "p_norm": 2.0,
                    "amplitude_weight": 0.0,
                    "shape_weight": 1.0,
                    "slope_weight": 0.0,
                    "cdf_weight": 0.0,
                    "amplitude_stat": "mean",
                }
            },
        },
    )

    assert float(out.loc[0, "est_flux_cm2_min"]) == 1.0
    term_shares = json.loads(str(out.loc[0, "best_distance_term_shares_json"]))
    assert term_shares == {"tt_rates_group": 1.0}
    assert str(out.loc[0, "best_distance_dominant_term"]) == "tt_rates_group"


def test_build_step15_runtime_cfg_disables_legacy_stage2_group_knobs() -> None:
    cfg = build_step15_runtime_inverse_mapping_cfg(
        inverse_mapping_cfg={
            "estimation_mode": "two_stage_eff_address_then_flux",
            "stage2_use_rate_histogram": True,
            "stage2_histogram_distance_weight": 2.5,
            "histogram_distance_weight": 1.7,
            "local_linear_ridge_lambda": 3.0,
            "efficiency_vector_distance": {
                "enabled": True,
                "weight": 1.3,
                "stage2_enabled": True,
                "stage2_weight": 4.2,
            },
        },
        interpolation_k=7,
        distance_definition={
            "available": True,
            "optimal_k": 11,
            "optimal_lambda": 1e6,
            "optimal_aggregation": "weighted_median",
        },
    )

    assert cfg["estimation_mode"] == "single_stage"
    assert cfg["neighbor_selection"] == "knn"
    assert int(cfg["neighbor_count"]) == 11
    assert cfg["aggregation"] == "weighted_median"
    assert float(cfg["local_linear_ridge_lambda"]) == 3.0
    assert cfg["stage2_use_rate_histogram"] is False
    assert float(cfg["stage2_histogram_distance_weight"]) == 0.0
    assert float(cfg["histogram_distance_weight"]) == 1.7
    assert bool(cfg["efficiency_vector_distance"]["enabled"]) is True
    assert float(cfg["efficiency_vector_distance"]["weight"]) == 1.3
    assert bool(cfg["efficiency_vector_distance"]["stage2_enabled"]) is False
    assert float(cfg["efficiency_vector_distance"]["stage2_weight"]) == 0.0


def test_build_step15_runtime_cfg_uses_tuned_local_linear_lambda() -> None:
    cfg = build_step15_runtime_inverse_mapping_cfg(
        inverse_mapping_cfg={
            "neighbor_selection": "knn",
            "neighbor_count": 5,
            "aggregation": "weighted_mean",
            "local_linear_ridge_lambda": 9.0,
        },
        interpolation_k=5,
        distance_definition={
            "available": True,
            "optimal_k": 13,
            "optimal_lambda": 0.25,
            "optimal_aggregation": "local_linear",
        },
    )

    assert cfg["aggregation"] == "local_linear"
    assert int(cfg["neighbor_count"]) == 13
    assert float(cfg["local_linear_ridge_lambda"]) == 0.25


def test_grouped_only_local_linear_uses_group_embeddings() -> None:
    dict_df = _toy_dictionary()
    data_df = pd.DataFrame(
        {
            "z_plane_1": [0.0],
            "z_plane_2": [65.0],
            "z_plane_3": [130.0],
            "z_plane_4": [195.0],
            "events_per_second_0_rate_hz": [57.0],
            "events_per_second_1_rate_hz": [24.0],
            "events_per_second_2_rate_hz": [19.0],
            "efficiency_vector_p1_x_bin_000_center_mm": [50.0],
            "efficiency_vector_p1_x_bin_000_eff": [0.74],
            "efficiency_vector_p1_x_bin_000_unc": [0.03],
            "flux_cm2_min": [1.8],
            "cos_n": [2.0],
            "eff_sim_1": [0.75],
            "eff_sim_2": [0.74],
            "eff_sim_3": [0.73],
            "eff_sim_4": [0.72],
        }
    )
    feature_cols = [
        "events_per_second_0_rate_hz",
        "events_per_second_1_rate_hz",
        "events_per_second_2_rate_hz",
        "efficiency_vector_p1_x_bin_000_eff",
    ]

    hist_cfg = {
        "feature_columns": feature_cols[:3],
        "distance": "ordered_vector_lp",
        "normalization": "unit_sum",
        "p_norm": 1.0,
        "amplitude_weight": 1.0,
        "shape_weight": 0.5,
        "slope_weight": 0.0,
        "cdf_weight": 1.0,
        "amplitude_stat": "sum",
    }
    _, hist_meta = build_rate_histogram_local_linear_embedding(
        hist_matrix=dict_df[feature_cols[:3]].to_numpy(dtype=float),
        feature_names=feature_cols[:3],
        hist_cfg=hist_cfg,
    )
    hist_cfg["local_linear_embedding"] = hist_meta

    eff_cfg = {
        "feature_columns": [feature_cols[3]],
        "distance": "ordered_vector_lp",
        "normalization": "none",
        "p_norm": 1.0,
        "amplitude_weight": 1.0,
        "shape_weight": 1.0,
        "slope_weight": 0.0,
        "cdf_weight": 0.0,
        "amplitude_stat": "mean",
        "uncertainty_floor": 0.02,
        "min_valid_bins_per_vector": 1,
        "group_reduction": "mean",
        "fiducial": {"x_abs_max_mm": 100.0},
    }
    eff_payloads = _prepare_efficiency_vector_group_payloads(
        dict_df=dict_df,
        data_df=data_df,
    )
    eff_payloads = _filter_efficiency_vector_payloads(
        eff_payloads,
        feature_groups_cfg=eff_cfg,
        selected_feature_columns=feature_cols,
    )
    _, eff_meta = build_efficiency_vector_local_linear_embedding(
        payloads=eff_payloads,
        eff_cfg=eff_cfg,
        source="dict",
    )
    eff_cfg["local_linear_embedding"] = eff_meta

    out = estimate_from_dataframes(
        dict_df=dict_df,
        data_df=data_df,
        feature_columns=feature_cols,
        param_columns=["flux_cm2_min", "eff_sim_1"],
        include_global_rate=False,
        exclude_same_file=False,
        inverse_mapping_cfg={
            "neighbor_selection": "knn",
            "neighbor_count": 2,
            "weighting": "inverse_distance",
            "aggregation": "local_linear",
            "local_linear_ridge_lambda": 0.01,
        },
        distance_definition={
            "available": True,
            "feature_columns": feature_cols,
            "center": [0.0] * len(feature_cols),
            "scale": [1.0] * len(feature_cols),
            "weights": [0.0] * len(feature_cols),
            "group_weights": {"rate_histogram": 1.0, "efficiency_vectors": 1.0},
            "feature_groups": {
                "rate_histogram": hist_cfg,
                "efficiency_vectors": eff_cfg,
            },
            "p_norm": 1.0,
            "optimal_k": 2,
            "optimal_lambda": 0.01,
            "optimal_aggregation": "local_linear",
            "selected_mode": "grouped_only",
        },
    )

    assert np.isfinite(float(out.loc[0, "est_flux_cm2_min"]))
    assert np.isfinite(float(out.loc[0, "est_eff_sim_1"]))
