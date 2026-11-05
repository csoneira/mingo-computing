#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_STEP33_DIR = (
    Path(__file__).resolve().parent.parent / "STEP_3_3_CORRECTION"
)
sys.path.insert(0, str(_STEP33_DIR))

from correction_by_inference import (
    _build_parameter_diagnostic_panels,
    _resolve_estimation_parameter_columns,
    _resolve_selected_step12_feature_columns_strict,
    _resolve_tt_rate_breakdown_entries,
)


def test_resolve_tt_rate_breakdown_entries_prefers_tt_specific_rate_columns() -> None:
    df = pd.DataFrame(
        {
            "fit_to_post_tt_123_rate_hz": [9.9, 9.8],
            "fit_tt_123_rate_hz": [1.4, 1.3],
            "post_tt_123_rate_hz": [1.1, 1.0],
            "events_per_second_global_rate": [9.0, 8.5],
        }
    )

    entries = _resolve_tt_rate_breakdown_entries(df)
    entry_by_label = {label: (rate_col, rate_source) for label, rate_col, rate_source in entries}

    assert entry_by_label["123"] == ("post_tt_123_rate_hz", "tt_specific")


def test_resolve_tt_rate_breakdown_entries_does_not_fall_back_to_shared_global_rate() -> None:
    df = pd.DataFrame(
        {
            "events_per_second_global_rate": [9.0, 8.5],
        }
    )

    entries = _resolve_tt_rate_breakdown_entries(df)
    entry_by_label = {label: (rate_col, rate_source) for label, rate_col, rate_source in entries}

    assert "123" not in entry_by_label
    assert "34" not in entry_by_label


def test_resolve_tt_rate_breakdown_entries_supports_expanded_tt_labels() -> None:
    df = pd.DataFrame(
        {
            "post_tt_124_rate_hz": [1.2, 1.1],
            "post_tt_134_rate_hz": [0.9, 0.8],
            "post_tt_13_rate_hz": [0.5, 0.4],
            "post_tt_14_rate_hz": [0.4, 0.3],
            "post_tt_24_rate_hz": [0.6, 0.5],
        }
    )

    entries = _resolve_tt_rate_breakdown_entries(df)
    entry_by_label = {label: rate_col for label, rate_col, _rate_source in entries}

    assert entry_by_label["124"] == "post_tt_124_rate_hz"
    assert entry_by_label["134"] == "post_tt_134_rate_hz"
    assert entry_by_label["13"] == "post_tt_13_rate_hz"
    assert entry_by_label["14"] == "post_tt_14_rate_hz"
    assert entry_by_label["24"] == "post_tt_24_rate_hz"


def test_resolve_estimation_parameter_columns_uses_default_parameter_space_order() -> None:
    dictionary_df = pd.DataFrame(
        columns=["flux_only", "eff_sim_2", "cos_n", "other"]
    )

    resolved = _resolve_estimation_parameter_columns(
        dictionary_df=dictionary_df,
        configured_columns=None,
        default_columns=["flux_only", "missing_col", "eff_sim_2"],
    )

    assert resolved == ["flux_only", "eff_sim_2"]


def test_build_parameter_diagnostic_panels_supports_generic_parameter_names() -> None:
    df = pd.DataFrame(
        {
            "true_cos_n": [2.0, 2.0],
            "corrected_cos_n": [2.05, 1.95],
            "unc_cos_n_abs": [0.02, 0.03],
            "true_flux_only": [1.0, 2.0],
            "est_flux_only": [1.1, 2.2],
        }
    )

    panels = _build_parameter_diagnostic_panels(
        df,
        parameter_space_cols=["cos_n", "flux_only"],
    )

    panel_names = [name for name, *_rest in panels]
    assert panel_names == ["cos_n", "flux_only"]


def test_resolve_selected_step12_feature_columns_strict_rejects_feature_drift() -> None:
    dict_df = pd.DataFrame({"feature_a": [1.0], "feature_b": [2.0]})
    data_df = pd.DataFrame({"feature_a": [1.5]})

    try:
        _resolve_selected_step12_feature_columns_strict(
            ["feature_a", "feature_b"],
            dict_df=dict_df,
            data_df=data_df,
        )
    except ValueError as exc:
        assert "missing in dataset" in str(exc)
        assert "feature_b" in str(exc)
    else:
        raise AssertionError("Expected ValueError for selected-feature drift")
