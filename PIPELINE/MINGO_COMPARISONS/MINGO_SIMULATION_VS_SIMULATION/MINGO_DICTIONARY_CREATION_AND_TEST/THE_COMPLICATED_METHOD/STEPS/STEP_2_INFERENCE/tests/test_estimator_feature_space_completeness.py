#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_INFERENCE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_INFERENCE_DIR))

from estimate_parameters import estimate_from_dataframes
from estimate_parameters import _local_linear_estimate
from estimate_parameters import require_explicit_columns_present_in_both_frames
from estimate_parameters import require_runtime_distance_definition


def _base_dictionary() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "z_plane_1": [0.0, 0.0, 0.0],
            "z_plane_2": [65.0, 65.0, 65.0],
            "z_plane_3": [130.0, 130.0, 130.0],
            "z_plane_4": [195.0, 195.0, 195.0],
            "flux_cm2_min": [1.0, 3.0, 4.0],
            "cos_n": [2.0, 2.0, 2.0],
            "eff_sim_1": [0.80, 0.81, 0.82],
            "eff_sim_2": [0.79, 0.80, 0.81],
            "eff_sim_3": [0.78, 0.79, 0.80],
            "eff_sim_4": [0.77, 0.78, 0.79],
            "feature_a": [0.0, 2.0, 3.0],
            "feature_b": [0.0, 2.0, 3.0],
        }
    )


def test_explicit_feature_columns_must_exist_in_both_inputs() -> None:
    dict_df = _base_dictionary()
    data_df = pd.DataFrame(
        {
            "z_plane_1": [0.0],
            "z_plane_2": [65.0],
            "z_plane_3": [130.0],
            "z_plane_4": [195.0],
            "feature_a": [1.5],
        }
    )

    with pytest.raises(ValueError, match="missing in dataset"):
        estimate_from_dataframes(
            dict_df=dict_df,
            data_df=data_df,
            feature_columns=["feature_a", "feature_b"],
            include_global_rate=False,
            exclude_same_file=False,
            inverse_mapping_cfg={"neighbor_selection": "nearest"},
        )


def test_incomplete_dictionary_rows_are_removed_before_estimation() -> None:
    dict_df = _base_dictionary()
    dict_df.loc[1, "flux_cm2_min"] = np.nan
    data_df = pd.DataFrame(
        {
            "z_plane_1": [0.0],
            "z_plane_2": [65.0],
            "z_plane_3": [130.0],
            "z_plane_4": [195.0],
            "feature_a": [2.05],
            "feature_b": [2.05],
        }
    )

    out = estimate_from_dataframes(
        dict_df=dict_df,
        data_df=data_df,
        feature_columns=["feature_a", "feature_b"],
        include_global_rate=False,
        exclude_same_file=False,
        inverse_mapping_cfg={"neighbor_selection": "nearest"},
    )

    completeness = out.attrs.get("feature_space_completeness", {})
    dict_info = completeness.get("dictionary", {})
    assert int(dict_info.get("rows_removed", 0)) == 1
    assert float(out.loc[0, "est_flux_cm2_min"]) == pytest.approx(4.0)
    assert pd.isna(out.loc[0, "estimation_failure_reason"])


def test_incomplete_dataset_rows_are_preserved_but_not_estimated() -> None:
    dict_df = _base_dictionary()
    data_df = pd.DataFrame(
        {
            "z_plane_1": [0.0, 0.0],
            "z_plane_2": [65.0, 65.0],
            "z_plane_3": [130.0, 130.0],
            "z_plane_4": [195.0, 195.0],
            "feature_a": [2.9, 2.9],
            "feature_b": [2.9, np.nan],
        }
    )

    out = estimate_from_dataframes(
        dict_df=dict_df,
        data_df=data_df,
        feature_columns=["feature_a", "feature_b"],
        include_global_rate=False,
        exclude_same_file=False,
        inverse_mapping_cfg={"neighbor_selection": "nearest"},
    )

    completeness = out.attrs.get("feature_space_completeness", {})
    data_info = completeness.get("dataset", {})
    assert int(data_info.get("rows_removed", 0)) == 1
    assert len(out) == 2
    assert bool(out.loc[0, "feature_space_complete"]) is True
    assert np.isfinite(float(out.loc[0, "est_flux_cm2_min"]))
    assert bool(out.loc[1, "feature_space_complete"]) is False
    assert str(out.loc[1, "estimation_failure_reason"]) == "incomplete_feature_space"
    assert pd.isna(out.loc[1, "est_flux_cm2_min"])


def test_local_linear_efficiency_estimate_stays_within_local_neighbor_range() -> None:
    values = np.array([0.88, 0.95, 0.99], dtype=float)
    weights = np.array([1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0], dtype=float)
    sample_features = np.array([0.0], dtype=float)
    neighbor_features = np.array([[1.0], [2.0], [3.0]], dtype=float)

    pred = _local_linear_estimate(
        values,
        weights,
        sample_features=sample_features,
        neighbor_features=neighbor_features,
        parameter_name="eff_sim_1",
        ridge_lambda=1.0,
    )

    assert float(pred) >= float(values.min())
    assert float(pred) <= float(values.max())


def test_local_linear_efficiency_extrapolation_falls_back_to_weighted_mean() -> None:
    values = np.array([0.88, 0.95, 0.99], dtype=float)
    weights = np.array([0.2, 0.3, 0.5], dtype=float)
    sample_features = np.array([0.0], dtype=float)
    neighbor_features = np.array([[1.0], [2.0], [3.0]], dtype=float)

    pred = _local_linear_estimate(
        values,
        weights,
        sample_features=sample_features,
        neighbor_features=neighbor_features,
        parameter_name="eff_sim_1",
        ridge_lambda=1.0,
    )

    expected = float(np.sum(weights * values) / np.sum(weights))
    assert float(pred) == pytest.approx(expected, abs=1e-6)
    assert float(pred) < float(values.max())


def test_require_runtime_distance_definition_rejects_missing_artifact() -> None:
    with pytest.raises(ValueError, match="STEP 2.1 requires a valid STEP 1.5 distance definition"):
        require_runtime_distance_definition(
            {"available": False, "reason": "file_not_found"},
            context_label="STEP 2.1",
        )


def test_require_runtime_distance_definition_rejects_projected_subset() -> None:
    with pytest.raises(ValueError, match="alignment_mode=projected_subset"):
        require_runtime_distance_definition(
            {
                "available": True,
                "alignment_mode": "projected_subset",
                "artifact_feature_columns_count": 3,
                "requested_feature_columns_count": 5,
            },
            context_label="STEP 4.2",
        )


def test_require_explicit_columns_present_in_both_frames_rejects_partial_match() -> None:
    with pytest.raises(ValueError, match="missing in real data: feature_b"):
        require_explicit_columns_present_in_both_frames(
            ["feature_a", "feature_b"],
            left_columns=["feature_a", "feature_b"],
            right_columns=["feature_a"],
            left_label="dictionary",
            right_label="real data",
            context_label="STEP 4.2",
        )
