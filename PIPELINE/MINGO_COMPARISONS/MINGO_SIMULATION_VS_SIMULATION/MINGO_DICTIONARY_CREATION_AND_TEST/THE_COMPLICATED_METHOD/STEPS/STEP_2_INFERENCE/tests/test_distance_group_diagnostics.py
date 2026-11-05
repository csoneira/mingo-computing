#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_INFERENCE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_INFERENCE_DIR))

from estimate_parameters import estimate_from_dataframes


def _base_dictionary() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "z_plane_1": [0.0, 0.0, 0.0],
            "z_plane_2": [65.0, 65.0, 65.0],
            "z_plane_3": [130.0, 130.0, 130.0],
            "z_plane_4": [195.0, 195.0, 195.0],
            "flux_cm2_min": [0.9, 1.0, 1.1],
            "cos_n": [2.0, 2.0, 2.0],
            "eff_sim_1": [0.72, 0.80, 0.88],
            "eff_sim_2": [0.70, 0.79, 0.87],
            "eff_sim_3": [0.71, 0.81, 0.89],
            "eff_sim_4": [0.69, 0.78, 0.86],
            "eff_empirical_1": [0.68, 0.76, 0.84],
            "eff_empirical_2": [0.67, 0.75, 0.83],
            "eff_empirical_3": [0.66, 0.74, 0.82],
            "eff_empirical_4": [0.65, 0.73, 0.81],
            "post_tt_1234_rate_hz": [9.0, 11.0, 13.0],
            "__derived_tt_global_rate_hz": [14.0, 16.0, 18.0],
            "__derived_log_tt_rate_over_eff_product": [3.2, 3.4, 3.6],
        }
    )


def test_best_match_group_shares_are_present_and_sum_to_one() -> None:
    dict_df = _base_dictionary()
    data_df = pd.DataFrame(
        {
            "z_plane_1": [0.0],
            "z_plane_2": [65.0],
            "z_plane_3": [130.0],
            "z_plane_4": [195.0],
            "eff_empirical_1": [0.75],
            "eff_empirical_2": [0.74],
            "eff_empirical_3": [0.73],
            "eff_empirical_4": [0.72],
            "post_tt_1234_rate_hz": [10.5],
            "__derived_log_tt_rate_over_eff_product": [3.35],
            "flux_cm2_min": [1.0],
            "cos_n": [2.0],
            "eff_sim_1": [0.80],
            "eff_sim_2": [0.79],
            "eff_sim_3": [0.81],
            "eff_sim_4": [0.78],
        }
    )
    feature_cols = [
        "eff_empirical_1",
        "eff_empirical_2",
        "eff_empirical_3",
        "eff_empirical_4",
        "post_tt_1234_rate_hz",
        "__derived_log_tt_rate_over_eff_product",
    ]

    out = estimate_from_dataframes(
        dict_df=dict_df,
        data_df=data_df,
        feature_columns=feature_cols,
        distance_metric="l2_zscore",
        interpolation_k=None,
        include_global_rate=False,
        exclude_same_file=False,
        inverse_mapping_cfg={"neighbor_selection": "nearest"},
    )

    required = [
        "best_distance_base_l2",
        "best_distance_base_l2_eff_empirical",
        "best_distance_base_l2_tt_rates",
        "best_distance_base_l2_other",
        "best_distance_base_share_eff_empirical",
        "best_distance_base_share_tt_rates",
        "best_distance_base_share_other",
    ]
    for col in required:
        assert col in out.columns

    eff_share = float(out.loc[0, "best_distance_base_share_eff_empirical"])
    tt_share = float(out.loc[0, "best_distance_base_share_tt_rates"])
    other_share = float(out.loc[0, "best_distance_base_share_other"])
    total = eff_share + tt_share + other_share
    assert np.isfinite(total)
    assert abs(total - 1.0) < 1e-6
    assert 0.0 <= eff_share <= 1.0
    assert 0.0 <= tt_share <= 1.0
    assert 0.0 <= other_share <= 1.0
    term_shares = json.loads(str(out.loc[0, "best_distance_term_shares_json"]))
    assert term_shares == {"scalar_base": 1.0}
    assert str(out.loc[0, "best_distance_dominant_term"]) == "scalar_base"
    assert float(out.loc[0, "best_distance_dominant_term_share"]) == 1.0


def test_derived_tt_global_feature_is_not_counted_as_raw_tt_share() -> None:
    dict_df = _base_dictionary()
    data_df = pd.DataFrame(
        {
            "z_plane_1": [0.0],
            "z_plane_2": [65.0],
            "z_plane_3": [130.0],
            "z_plane_4": [195.0],
            "eff_empirical_1": [0.78],
            "eff_empirical_2": [0.77],
            "eff_empirical_3": [0.76],
            "eff_empirical_4": [0.75],
            "__derived_tt_global_rate_hz": [15.5],
            "flux_cm2_min": [1.0],
            "cos_n": [2.0],
            "eff_sim_1": [0.80],
            "eff_sim_2": [0.79],
            "eff_sim_3": [0.81],
            "eff_sim_4": [0.78],
        }
    )
    feature_cols = [
        "eff_empirical_1",
        "eff_empirical_2",
        "eff_empirical_3",
        "eff_empirical_4",
        "__derived_tt_global_rate_hz",
    ]

    out = estimate_from_dataframes(
        dict_df=dict_df,
        data_df=data_df,
        feature_columns=feature_cols,
        distance_metric="l2_zscore",
        interpolation_k=None,
        include_global_rate=False,
        exclude_same_file=False,
        inverse_mapping_cfg={"neighbor_selection": "nearest"},
    )

    tt_share = pd.to_numeric(out["best_distance_base_share_tt_rates"], errors="coerce")
    assert tt_share.notna().all()
    assert np.allclose(tt_share.to_numpy(dtype=float), 0.0)
