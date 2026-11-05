#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


STEP22_DIR = (
    Path(__file__).resolve().parents[1]
    / "STEP_2_2_VALIDATION"
)
if str(STEP22_DIR) not in sys.path:
    sys.path.insert(0, str(STEP22_DIR))

from validate_solution import _rows_with_dictionary_parameter_set


def test_rows_with_dictionary_parameter_set_uses_physical_tuple_when_hashes_do_not_overlap() -> None:
    dict_df = pd.DataFrame(
        {
            "param_hash_x": ["dict_only_hash"],
            "flux_cm2_min": [1.2],
            "eff_sim_1": [0.81],
            "eff_sim_2": [0.82],
            "eff_sim_3": [0.83],
            "eff_sim_4": [0.84],
            "z_plane_1": [0.0],
            "z_plane_2": [1.0],
            "z_plane_3": [2.0],
            "z_plane_4": [3.0],
        }
    )
    data_df = pd.DataFrame(
        {
            "param_hash_x": ["dataset_only_hash"],
        }
    )
    val = pd.DataFrame(
        {
            "dataset_index": [0],
            "true_flux_cm2_min": [1.2],
            "true_eff_sim_1": [0.81],
            "true_eff_sim_2": [0.82],
            "true_eff_sim_3": [0.83],
            "true_eff_sim_4": [0.84],
            "true_z_plane_1": [0.0],
            "true_z_plane_2": [1.0],
            "true_z_plane_3": [2.0],
            "true_z_plane_4": [3.0],
        }
    )

    mask = _rows_with_dictionary_parameter_set(val, dict_df, data_df)

    assert mask.tolist() == [True]
