#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_INFERENCE_DIR = Path(__file__).resolve().parent.parent
_STEPS_DIR = _INFERENCE_DIR.parent
_STEP12_DIR = _STEPS_DIR / "STEP_1_SETUP" / "STEP_1_2_BUILD_DICTIONARY"
_STEP42_DIR = _STEPS_DIR / "STEP_4_REAL_DATA" / "STEP_4_2_ANALYZE"
sys.path.insert(0, str(_STEP12_DIR))
sys.path.insert(0, str(_STEP42_DIR))

from build_dictionary import _fit_isotonic_calibration
from analyze import _transform_efficiencies_isotonic


def _plane_series(values: list[float]) -> dict[int, pd.Series]:
    idx = pd.RangeIndex(len(values))
    base = pd.Series(values, index=idx, dtype=float)
    return {1: base.copy(), 2: base.copy(), 3: base.copy(), 4: base.copy()}


def test_isotonic_tail_slope_prevents_zero_high_boundary_slope() -> None:
    # Synthetic calibration sample with slight non-monotonic tail:
    # isotonic secant near x_max tends to flatten, but tail regression
    # should preserve a positive high-end derivative.
    x = np.linspace(0.04, 0.70, 500)
    y = 0.03 + 1.15 * x - 0.18 * x * x
    y[-80:] = np.maximum.accumulate(y[-80:])[::-1][::-1]  # flatten top tail
    df = pd.DataFrame({"eff_empirical_1": x, "eff_sim_1": y})

    iso = _fit_isotonic_calibration(df, plane=1, n_grid=300)
    assert iso is not None
    assert iso["slope_hi"] > 0.01
    assert iso["extrapolation_model"] == "asymptotic_monotonic"


def test_isotonic_asymptotic_extrapolation_above_support_is_not_flat() -> None:
    eff_by_plane = _plane_series([0.70, 0.72, 0.75, 0.80, 0.90])
    cal = {
        1: {
            "x_knots": np.array([0.10, 0.40, 0.70], dtype=float),
            "y_knots": np.array([0.20, 0.65, 0.96], dtype=float),
            "x_min": 0.10,
            "x_max": 0.70,
            "slope_lo": 0.9,
            "slope_hi": 1.2,
        },
        2: {
            "x_knots": np.array([0.10, 0.40, 0.70], dtype=float),
            "y_knots": np.array([0.20, 0.65, 0.96], dtype=float),
            "x_min": 0.10,
            "x_max": 0.70,
            "slope_lo": 0.9,
            "slope_hi": 1.2,
        },
        3: {
            "x_knots": np.array([0.10, 0.40, 0.70], dtype=float),
            "y_knots": np.array([0.20, 0.65, 0.96], dtype=float),
            "x_min": 0.10,
            "x_max": 0.70,
            "slope_lo": 0.9,
            "slope_hi": 1.2,
        },
        4: {
            "x_knots": np.array([0.10, 0.40, 0.70], dtype=float),
            "y_knots": np.array([0.20, 0.65, 0.96], dtype=float),
            "x_min": 0.10,
            "x_max": 0.70,
            "slope_lo": 0.9,
            "slope_hi": 1.2,
        },
    }

    transformed, _ = _transform_efficiencies_isotonic(eff_by_plane, cal)
    vals = transformed[1].to_numpy(dtype=float)

    assert np.all(np.isfinite(vals))
    assert np.all((vals >= 0.0) & (vals <= 1.0))
    assert vals[1] > vals[0]
    assert vals[2] > vals[1]
    assert vals[3] > vals[2]
    assert vals[-1] < 1.0
    assert not np.isclose(vals[1], vals[-1], atol=1e-10)


def test_isotonic_asymptotic_extrapolation_below_support_is_monotonic() -> None:
    eff_by_plane = _plane_series([0.02, 0.04, 0.07, 0.10, 0.15])
    cal = {
        1: {
            "x_knots": np.array([0.10, 0.40, 0.70], dtype=float),
            "y_knots": np.array([0.20, 0.65, 0.96], dtype=float),
            "x_min": 0.10,
            "x_max": 0.70,
            "slope_lo": 1.0,
            "slope_hi": 1.2,
        },
        2: {
            "x_knots": np.array([0.10, 0.40, 0.70], dtype=float),
            "y_knots": np.array([0.20, 0.65, 0.96], dtype=float),
            "x_min": 0.10,
            "x_max": 0.70,
            "slope_lo": 1.0,
            "slope_hi": 1.2,
        },
        3: {
            "x_knots": np.array([0.10, 0.40, 0.70], dtype=float),
            "y_knots": np.array([0.20, 0.65, 0.96], dtype=float),
            "x_min": 0.10,
            "x_max": 0.70,
            "slope_lo": 1.0,
            "slope_hi": 1.2,
        },
        4: {
            "x_knots": np.array([0.10, 0.40, 0.70], dtype=float),
            "y_knots": np.array([0.20, 0.65, 0.96], dtype=float),
            "x_min": 0.10,
            "x_max": 0.70,
            "slope_lo": 1.0,
            "slope_hi": 1.2,
        },
    }

    transformed, _ = _transform_efficiencies_isotonic(eff_by_plane, cal)
    vals = transformed[1].to_numpy(dtype=float)

    assert np.all(np.isfinite(vals))
    assert np.all((vals >= 0.0) & (vals <= 1.0))
    assert vals[0] < vals[1] < vals[2] < vals[3] < vals[4]
    assert vals[0] > 0.0
