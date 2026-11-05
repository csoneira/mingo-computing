#!/usr/bin/env python3
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_INFERENCE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_INFERENCE_DIR))

import inference_runtime


def test_require_selected_feature_columns_present_rejects_feature_drift() -> None:
    dict_df = pd.DataFrame({"feature_a": [1.0], "feature_b": [2.0]})
    data_df = pd.DataFrame({"feature_a": [1.5]})

    try:
        inference_runtime.require_selected_feature_columns_present(
            ["feature_a", "feature_b"],
            dict_df=dict_df,
            data_df=data_df,
            context_label="STEP 4.2",
            right_label="real data",
        )
    except ValueError as exc:
        assert "missing in real data" in str(exc)
        assert "feature_b" in str(exc)
    else:
        raise AssertionError("Expected ValueError for selected-feature drift")


def test_resolve_runtime_distance_and_inverse_mapping_uses_matching_override(monkeypatch) -> None:
    override = {
        "feature_columns": ["feature_a", "feature_b"],
        "available": True,
        "selected_mode": "vector_only",
        "p_norm": 1.0,
        "optimal_k": 17,
        "optimal_lambda": 1.0,
        "weights": np.array([1.0, 0.0], dtype=float),
        "group_weights": {"rate_histogram": 0.25, "efficiency_vectors": 1.0},
    }

    monkeypatch.setattr(
        inference_runtime,
        "require_runtime_distance_definition",
        lambda dd, **_kwargs: dd,
    )
    monkeypatch.setattr(
        inference_runtime,
        "build_step15_runtime_inverse_mapping_cfg",
        lambda **kwargs: {
            "neighbor_selection": "knn",
            "neighbor_count": kwargs["interpolation_k"],
            "weighting": "inverse_distance",
            "inverse_distance_power": 2.0,
            "aggregation": "local_linear",
        },
    )

    dd, runtime_cfg, interpolation_k = inference_runtime.resolve_runtime_distance_and_inverse_mapping(
        feature_columns=["feature_a", "feature_b"],
        inverse_mapping_cfg={"aggregation": "local_linear"},
        interpolation_k=None,
        context_label="STEP 2.1",
        distance_definition_path=Path("/tmp/unused.json"),
        logger=logging.getLogger("test_inference_runtime"),
        distance_definition_override=override,
    )

    assert dd["selected_mode"] == "vector_only"
    assert interpolation_k == 17
    assert runtime_cfg["neighbor_selection"] == "knn"
    assert runtime_cfg["neighbor_count"] == 17


def test_resolve_estimation_parameter_columns_uses_default_priority() -> None:
    dictionary_df = pd.DataFrame(columns=["flux_only", "cos_n", "eff_sim_3"])

    resolved = inference_runtime.resolve_estimation_parameter_columns(
        dictionary_df=dictionary_df,
        configured_columns=None,
        default_columns=["flux_only", "missing_col", "cos_n"],
        default_priority=["flux_cm2_min", "cos_n"],
        parameter_predicate=lambda name: str(name).startswith("eff_") or name == "cos_n",
        logger=logging.getLogger("test_inference_runtime"),
    )

    assert resolved == ["flux_only", "cos_n"]
