#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

_MODULES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_MODULES_DIR))

from uncertainty_lut import (  # noqa: E402
    detect_uncertainty_lut_param_names,
    interpolate_uncertainty_columns,
)


def test_detect_uncertainty_lut_param_names_prefers_metadata(tmp_path: Path) -> None:
    lut_df = pd.DataFrame(
        {
            "est_flux_cm2_min_centre": [1.0],
            "est_eff_sim_1_centre": [0.9],
            "n_events_centre": [1000.0],
            "sigma_flux_cm2_min_p68": [2.0],
        }
    )
    meta_path = tmp_path / "uncertainty_lut_meta.json"
    meta_path.write_text(
        json.dumps({"param_names": ["flux_cm2_min", "eff_sim_1"]}),
        encoding="utf-8",
    )

    resolved = detect_uncertainty_lut_param_names(lut_df, meta_path)

    assert resolved == ["flux_cm2_min", "eff_sim_1"]


def test_interpolate_uncertainty_columns_returns_exact_match() -> None:
    lut_df = pd.DataFrame(
        {
            "est_flux_cm2_min_centre": [1.0, 2.0],
            "est_eff_sim_1_centre": [0.8, 0.8],
            "n_events_centre": [1000.0, 1000.0],
            "sigma_flux_cm2_min_p68": [5.0, 15.0],
        }
    )
    query_df = pd.DataFrame(
        {
            "est_flux_cm2_min": [2.0],
            "est_eff_sim_1": [0.8],
            "n_events": [1000.0],
        }
    )

    out = interpolate_uncertainty_columns(
        query_df,
        lut_df,
        param_names=["flux_cm2_min"],
        quantile=0.68,
    )

    assert float(out.loc[0, "unc_flux_cm2_min_pct_raw"]) == 15.0
    assert float(out.loc[0, "unc_flux_cm2_min_pct"]) == 15.0


def test_interpolate_uncertainty_columns_smooths_between_lut_rows() -> None:
    lut_df = pd.DataFrame(
        {
            "est_flux_cm2_min_centre": [0.0, 1.0, 2.0, 3.0],
            "est_eff_sim_1_centre": [0.8, 0.8, 0.8, 0.8],
            "n_events_centre": [1000.0, 1000.0, 1000.0, 1000.0],
            "sigma_flux_cm2_min_p68": [10.0, 20.0, 30.0, 40.0],
        }
    )
    query_df = pd.DataFrame(
        {
            "est_flux_cm2_min": [0.25],
            "est_eff_sim_1": [0.8],
            "n_events": [1000.0],
        }
    )

    out = interpolate_uncertainty_columns(
        query_df,
        lut_df,
        param_names=["flux_cm2_min"],
        quantile=0.68,
        neighbor_count=4,
    )

    interpolated = float(out.loc[0, "unc_flux_cm2_min_pct_raw"])
    assert 10.0 < interpolated < 20.0
    assert round(interpolated, 6) != 10.0
