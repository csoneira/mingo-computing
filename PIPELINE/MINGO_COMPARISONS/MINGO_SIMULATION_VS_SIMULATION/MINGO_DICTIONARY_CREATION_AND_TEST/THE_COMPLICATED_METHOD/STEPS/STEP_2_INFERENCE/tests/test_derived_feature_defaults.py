#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

_THIS_DIR = Path(__file__).resolve().parent
_STEP21_DIR = _THIS_DIR.parent / "STEP_2_1_ESTIMATE_PARAMS"
sys.path.insert(0, str(_STEP21_DIR))

import estimate_and_plot as step21  # noqa: E402


def _minimal_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "z_plane_1": [0.0, 0.0],
            "z_plane_2": [65.0, 65.0],
            "z_plane_3": [130.0, 130.0],
            "z_plane_4": [195.0, 195.0],
            "eff_empirical_1": [0.70, 0.72],
            "eff_empirical_2": [0.71, 0.73],
            "eff_empirical_3": [0.69, 0.71],
            "eff_empirical_4": [0.68, 0.70],
            "post_tt_1234_rate_hz": [9.5, 10.0],
            "post_tt_123_rate_hz": [1.1, 1.0],
            "post_tt_234_rate_hz": [1.0, 0.9],
            "post_tt_124_rate_hz": [0.9, 0.8],
            "post_tt_134_rate_hz": [1.2, 1.1],
            "post_tt_12_rate_hz": [0.6, 0.5],
            "post_tt_23_rate_hz": [0.5, 0.4],
            "post_tt_34_rate_hz": [0.4, 0.3],
            "flux_cm2_min": [1.0, 1.05],
            "cos_n": [2.0, 2.0],
            "eff_sim_1": [0.78, 0.79],
            "eff_sim_2": [0.77, 0.78],
            "eff_sim_3": [0.76, 0.77],
            "eff_sim_4": [0.75, 0.76],
        }
    )


def test_derived_feature_resolution_disables_raw_tt_rates_by_default() -> None:
    dict_df = _minimal_frame()
    data_df = _minimal_frame()

    selected, resolution = step21._resolve_step21_feature_columns(
        feature_cfg="derived",
        dict_df=dict_df,
        data_df=data_df,
        include_global_rate=False,
        global_rate_col="events_per_second_global_rate",
        catalog_path=step21.CONFIG_COLUMNS_PATH,
        derived_feature_cfg={},
    )

    raw_tt_re = re.compile(r"^post_tt_.*_rate_hz$")
    raw_tt_cols = [c for c in selected if raw_tt_re.match(str(c))]
    assert raw_tt_cols == []
    assert resolution.get("derived_options", {}).get("include_trigger_type_rates") is False


def test_step12_selected_feature_mode_uses_selected_artifact(tmp_path: Path) -> None:
    dict_df = _minimal_frame()
    data_df = _minimal_frame()
    selected_path = tmp_path / "selected_feature_columns.json"
    selected_payload = {
        "selected_feature_columns": [
            "eff_empirical_1",
            "eff_empirical_2",
            "post_tt_1234_rate_hz",
        ],
        "selection_strategy": "step_1_2_injectivity_selection_v1",
    }
    selected_path.write_text(json.dumps(selected_payload), encoding="utf-8")

    selected, resolution = step21._resolve_step21_feature_columns(
        feature_cfg="step12_selected",
        dict_df=dict_df,
        data_df=data_df,
        include_global_rate=False,
        global_rate_col="events_per_second_global_rate",
        catalog_path=step21.CONFIG_COLUMNS_PATH,
        step12_selected_path=selected_path,
        derived_feature_cfg={},
    )

    assert selected == [
        "eff_empirical_1",
        "eff_empirical_2",
        "post_tt_1234_rate_hz",
    ]
    assert resolution.get("strategy") == "step12_selected"
