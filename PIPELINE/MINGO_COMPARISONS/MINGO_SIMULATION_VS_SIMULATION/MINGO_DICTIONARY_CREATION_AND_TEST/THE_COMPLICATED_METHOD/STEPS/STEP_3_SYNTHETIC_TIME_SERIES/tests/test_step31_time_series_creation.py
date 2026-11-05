#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_STEP31_DIR = (
    Path(__file__).resolve().parent.parent / "STEP_3_1_TIME_SERIES_CREATION"
)
sys.path.insert(0, str(_STEP31_DIR))

from create_time_series import _apply_parameter_space_aliases
from create_time_series import _build_dataset_backed_curve, _normalize_curve_data_mode
from create_time_series import _resolve_parameter_curve_columns
from create_time_series import _select_dataset_curve_smooth_order


def test_normalize_curve_data_mode_supports_dataset_and_synthetic_aliases() -> None:
    assert _normalize_curve_data_mode("synthetic") == "synthetic_data_curve"
    assert _normalize_curve_data_mode("dataset") == "dataset_data_curve"
    assert _normalize_curve_data_mode(None) == "synthetic_data_curve"


def test_build_dataset_backed_curve_selects_actual_source_rows() -> None:
    source_df = pd.DataFrame(
        {
            "filename_base": ["a", "b", "c", "d"],
            "flux_cm2_min": [1.0, 1.2, 1.4, 1.6],
            "eff_sim_1": [0.70, 0.72, 0.74, 0.76],
            "eff_sim_2": [0.60, 0.62, 0.64, 0.66],
            "events_per_second_global_rate": [10.0, 10.0, 10.0, 10.0],
            "selected_rows": [100, 100, 100, 100],
        }
    )

    dense_df, file_df, info = _build_dataset_backed_curve(
        source_df=source_df,
        param_cols=["flux_cm2_min", "eff_sim_1", "eff_sim_2"],
        rate_col="events_per_second_global_rate",
        duration_seconds_target=20.0,
        events_per_file_fallback=100,
        start_time=pd.Timestamp("2026-01-01T00:00:00Z"),
    )

    assert info["mode"] == "dataset_data_curve"
    assert info["selected_source_rows"] == 2
    assert file_df["step31_curve_data_mode"].tolist() == ["dataset_data_curve", "dataset_data_curve"]
    assert file_df["step31_source_row_index"].tolist() == [0, 3]
    assert file_df["step31_source_filename_base"].tolist() == ["a", "d"]
    assert file_df["flux_cm2_min"].tolist() == [1.0, 1.6]
    assert dense_df["curve_index"].tolist() == [0, 1]


def test_parameter_curve_columns_accept_step1_aliases() -> None:
    rate_df = pd.DataFrame(
        {
            "flux_cm2_min": [1.0, 1.1],
            "eff_p1": [0.70, 0.72],
            "eff_p2": [0.60, 0.62],
            "eff_p3": [0.50, 0.52],
            "eff_p4": [0.40, 0.42],
        }
    )
    spec = {
        "parameter_space_column_aliases": {
            "eff_p1": "eff_sim_1",
            "eff_p2": "eff_sim_2",
            "eff_p3": "eff_sim_3",
            "eff_p4": "eff_sim_4",
        }
    }

    rate_df, added = _apply_parameter_space_aliases(rate_df, spec)
    resolved = _resolve_parameter_curve_columns(
        rate_df,
        {"parameter_curve_columns": ["flux_cm2_min", "eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4"]},
    )

    assert added == ["eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4"]
    assert resolved == ["flux_cm2_min", "eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4"]
    assert np.allclose(rate_df["eff_sim_3"], rate_df["eff_p3"])


def test_parameter_curve_columns_allow_single_dimension() -> None:
    rate_df = pd.DataFrame(
        {
            "flux_cm2_min": [1.0, 1.2, 1.4],
            "events_per_second_global_rate": [10.0, 12.0, 14.0],
        }
    )

    resolved = _resolve_parameter_curve_columns(
        rate_df,
        {"parameter_curve_columns": ["flux_cm2_min"]},
    )

    assert resolved == ["flux_cm2_min"]


def test_select_dataset_curve_smooth_order_avoids_large_midpoint_jump() -> None:
    param_matrix = pd.DataFrame(
        [
            [0.0, 0.0, 0.0],
            [1.0, 1.0, 1.0],
            [2.0, 0.0, 0.0],
            [3.0, 0.0, 0.0],
        ]
    )

    selected_order, info = _select_dataset_curve_smooth_order(param_matrix, n_target=3)

    selected = param_matrix.to_numpy(dtype=float)[selected_order]
    selected_jump = float(((selected[1:] - selected[:-1]) ** 2).sum(axis=1).sum())
    baseline = param_matrix.to_numpy(dtype=float)[[0, 1, 3]]
    baseline_jump = float(((baseline[1:] - baseline[:-1]) ** 2).sum(axis=1).sum())

    assert len(selected_order) == 3
    assert len(set(selected_order.tolist())) == 3
    assert selected_jump < baseline_jump
    assert info["ordering_mode"] == "pca1_windowed_continuity_path"


def test_select_dataset_curve_smooth_order_changes_with_seed_but_stays_smooth() -> None:
    param_matrix = np.column_stack(
        [
            np.linspace(0.0, 11.0, 12),
            np.sin(np.linspace(0.0, 2.0 * np.pi, 12)),
            np.cos(np.linspace(0.0, 2.0 * np.pi, 12)),
        ]
    )

    selected_a, info_a = _select_dataset_curve_smooth_order(
        param_matrix,
        n_target=5,
        rng=np.random.default_rng(13),
    )
    selected_b, info_b = _select_dataset_curve_smooth_order(
        param_matrix,
        n_target=5,
        rng=np.random.default_rng(101),
    )

    assert selected_a.tolist() != selected_b.tolist()
    assert len(set(selected_a.tolist())) == 5
    assert len(set(selected_b.tolist())) == 5
    assert info_a["selection_randomized"] is True
    assert info_b["selection_randomized"] is True

    for selected in (selected_a, selected_b):
        chosen = param_matrix[selected]
        jump_norm = np.linalg.norm(np.diff(chosen, axis=0), axis=1)
        assert float(np.max(jump_norm)) < 4.0
