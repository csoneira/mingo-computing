#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_INFERENCE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_INFERENCE_DIR))

from estimate_parameters import estimate_from_dataframes, resolve_inverse_mapping_cfg


def _dict_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "z_plane_1": [0.0, 0.0, 0.0],
            "z_plane_2": [65.0, 65.0, 65.0],
            "z_plane_3": [130.0, 130.0, 130.0],
            "z_plane_4": [195.0, 195.0, 195.0],
            "flux_cm2_min": [0.90, 1.00, 1.10],
            "cos_n": [2.0, 2.0, 2.0],
            "eff_sim_1": [0.72, 0.80, 0.88],
            "eff_sim_2": [0.70, 0.79, 0.87],
            "eff_sim_3": [0.71, 0.81, 0.89],
            "eff_sim_4": [0.69, 0.78, 0.86],
            "eff_empirical_1": [0.68, 0.76, 0.84],
            "eff_empirical_2": [0.67, 0.75, 0.83],
            "eff_empirical_3": [0.66, 0.74, 0.82],
            "eff_empirical_4": [0.65, 0.73, 0.81],
            "__derived_tt_global_rate_hz": [14.0, 16.0, 18.0],
        }
    )


def _data_frame(outside_eff1: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "z_plane_1": [0.0],
            "z_plane_2": [65.0],
            "z_plane_3": [130.0],
            "z_plane_4": [195.0],
            "flux_cm2_min": [1.0],
            "cos_n": [2.0],
            "eff_sim_1": [0.80],
            "eff_sim_2": [0.79],
            "eff_sim_3": [0.81],
            "eff_sim_4": [0.78],
            "eff_empirical_1": [outside_eff1],
            "eff_empirical_2": [0.76],
            "eff_empirical_3": [0.75],
            "eff_empirical_4": [0.74],
            "__derived_tt_global_rate_hz": [16.2],
        }
    )


def test_inverse_mapping_cfg_defaults_keep_eff_support_masking_disabled() -> None:
    cfg = resolve_inverse_mapping_cfg(inverse_mapping_cfg=None)
    assert cfg["mask_out_of_support_eff_features"] is False


def test_out_of_support_eff_feature_is_masked_when_enabled() -> None:
    dict_df = _dict_frame()
    data_df = _data_frame(outside_eff1=0.95)  # outside dictionary support for eff_empirical_1
    feature_cols = [
        "__derived_tt_global_rate_hz",
        "eff_empirical_1",
        "eff_empirical_2",
        "eff_empirical_3",
        "eff_empirical_4",
    ]

    out = estimate_from_dataframes(
        dict_df=dict_df,
        data_df=data_df,
        feature_columns=feature_cols,
        distance_metric="l2_zscore",
        include_global_rate=False,
        exclude_same_file=False,
        inverse_mapping_cfg={
            "neighbor_selection": "nearest",
            "mask_out_of_support_eff_features": True,
        },
    )

    assert int(out.loc[0, "n_eff_features_masked_out_of_support"]) == 1
    assert bool(out.loc[0, "any_eff_feature_masked_out_of_support"]) is True
    summary = out.attrs.get("efficiency_feature_out_of_support_masking", {})
    assert int(summary.get("n_rows_any_masked", 0)) == 1
    per_feature = summary.get("per_feature", {})
    assert "eff_empirical_1" in per_feature
    assert int(per_feature["eff_empirical_1"].get("rows_masked", 0)) == 1


def test_support_masking_can_be_disabled() -> None:
    dict_df = _dict_frame()
    data_df = _data_frame(outside_eff1=0.95)
    feature_cols = [
        "__derived_tt_global_rate_hz",
        "eff_empirical_1",
        "eff_empirical_2",
        "eff_empirical_3",
        "eff_empirical_4",
    ]

    out = estimate_from_dataframes(
        dict_df=dict_df,
        data_df=data_df,
        feature_columns=feature_cols,
        distance_metric="l2_zscore",
        include_global_rate=False,
        exclude_same_file=False,
        inverse_mapping_cfg={
            "neighbor_selection": "nearest",
            "mask_out_of_support_eff_features": False,
        },
    )

    assert int(out.loc[0, "n_eff_features_masked_out_of_support"]) == 0
    assert bool(out.loc[0, "any_eff_feature_masked_out_of_support"]) is False
