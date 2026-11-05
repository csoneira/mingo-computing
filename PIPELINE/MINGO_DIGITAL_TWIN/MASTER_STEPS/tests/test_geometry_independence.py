"""Regression tests for independent active-area and readout geometry."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

MASTER_STEPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MASTER_STEPS))

from STEP_SHARED.sim_utils_geometry import (  # noqa: E402
    LEGACY_Y_WIDTHS,
    RectBounds,
    build_legacy_readout_geometry,
    build_plane_readout_geometry,
    build_readout_geometry,
    readout_geometry_to_dict,
    resolve_active_area_bounds,
)
from STEP_SHARED.sim_utils_registry import _json_fingerprint  # noqa: E402
from STEP_2.step_2_generated_to_crossing import calculate_intersections  # noqa: E402
from STEP_3.step_3_crossing_to_hit import build_avalanche  # noqa: E402
from STEP_4.step_4_hit_to_measured import (  # noqa: E402
    ELEMENTARY_CHARGE_FC,
    induce_signal,
    isotropic_lorentzian_rectangle_fraction,
)


def _generated_plane(
    *,
    x_min: float = -150.0,
    x_max: float = 150.0,
    y_min: float = -5.0,
    widths: list[float] | None = None,
    gap: float = 1.0,
) -> dict[str, object]:
    strip_widths = widths or [2.0, 2.0, 2.0, 2.0]
    return {
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "strip_widths_mm": strip_widths,
        "interstrip_gap_mm": gap,
        "y_max": y_min + sum(strip_widths) + 3.0 * gap,
    }


def _readout_config(**plane_kwargs: object) -> dict[str, object]:
    return {
        "readout_geometry_mm": {
            "planes": {str(i): _generated_plane(**plane_kwargs) for i in range(1, 5)}
        }
    }


def _muons(xs: list[float], ys: list[float] | None = None) -> pd.DataFrame:
    ys = ys or [0.0] * len(xs)
    return pd.DataFrame(
        {
            "event_id": np.arange(len(xs)),
            "X_gen": xs,
            "Y_gen": ys,
            "Z_gen": np.zeros(len(xs)),
            "Theta_gen": np.zeros(len(xs)),
            "Phi_gen": np.zeros(len(xs)),
        }
    )


def _avalanche_frame(x: float, y: float, electrons: float = 1.0e6) -> pd.DataFrame:
    data: dict[str, list[float]] = {"event_id": [1]}
    for plane in range(1, 5):
        data[f"avalanche_size_electrons_{plane}"] = [electrons]
        data[f"avalanche_x_{plane}"] = [x]
        data[f"avalanche_y_{plane}"] = [y]
        data[f"T_sum_{plane}_ns"] = [float(plane)]
    return pd.DataFrame(data)


def _induce(frame: pd.DataFrame, geometry: dict) -> pd.DataFrame:
    return induce_signal(
        frame,
        x_noise=0.0,
        time_sigma_ns=0.0,
        lorentzian_gamma_mm=0.08,
        induced_charge_fraction=1.0,
        readout_geometry=geometry,
        rng=np.random.default_rng(123),
        debug_event_index=None,
        debug_points=None,
    )


def _strip_rectangles(geometry: dict) -> tuple:
    return tuple(
        (s.x_min, s.x_max, s.y_min, s.y_max)
        for plane in range(1, 5)
        for s in geometry[plane].strips
    )


def test_independent_x_ranges_control_acceptance_and_integration():
    active = RectBounds(-100.0, 100.0, -20.0, 20.0)
    geometry, _ = build_readout_geometry(
        _readout_config(x_min=-150.0, x_max=150.0),
        legacy_active_area_bounds=active,
    )
    crossed = calculate_intersections(_muons([99.0, 120.0]), [0.0] * 4, active, 299.792458)
    assert crossed.loc[0, "tt_crossing"] == "1234"
    assert pd.isna(crossed.loc[1, "tt_crossing"])
    assert all(s.x_min == -150.0 and s.x_max == 150.0 for s in geometry[1].strips)

    changed_active = RectBounds(-50.0, 50.0, -20.0, 20.0)
    same_geometry, _ = build_readout_geometry(
        _readout_config(x_min=-150.0, x_max=150.0),
        legacy_active_area_bounds=changed_active,
    )
    assert _strip_rectangles(geometry) == _strip_rectangles(same_geometry)


def test_independent_y_ranges_are_not_clipped_to_active_area():
    active = RectBounds(-10.0, 10.0, -1.0, 1.0)
    geometry, _ = build_readout_geometry(
        _readout_config(y_min=-7.0, widths=[3.0, 3.0, 3.0, 3.0]),
        legacy_active_area_bounds=active,
    )
    assert geometry[1].y_min == -7.0
    assert geometry[1].y_max == 8.0
    assert geometry[1].y_min < active.y_min
    assert geometry[1].y_max > active.y_max


def test_one_mm_gaps_have_exact_boundaries_and_receive_no_strip_charge():
    geometry, _ = build_readout_geometry(
        _readout_config(x_min=-10.0, x_max=10.0, y_min=0.0, widths=[1.0] * 4, gap=1.0)
    )
    strips = geometry[1].strips
    assert [(s.y_min, s.y_max) for s in strips] == [
        (0.0, 1.0),
        (2.0, 3.0),
        (4.0, 5.0),
        (6.0, 7.0),
    ]
    result = _induce(_avalanche_frame(0.0, 1.5), geometry)
    assigned = float(result.loc[0, "readout_assigned_fraction_1"])
    gap = float(result.loc[0, "readout_gap_fraction_1"])
    bounding = float(result.loc[0, "readout_bounding_fraction_1"])
    qsum = sum(float(result.loc[0, f"Y_mea_1_s{i}"]) for i in range(1, 5))
    induced = float(result.loc[0, "induced_charge_total_fc_1"])
    assert gap > 0.5
    assert assigned < bounding
    assert qsum == pytest.approx(induced * assigned, rel=2e-6)
    assert qsum < induced * bounding


def test_translated_readout_coordinates_drive_charge_induction():
    centered, _ = build_readout_geometry(
        _readout_config(x_min=-10.0, x_max=10.0, y_min=-5.5)
    )
    translated, _ = build_readout_geometry(
        _readout_config(x_min=40.0, x_max=60.0, y_min=30.0)
    )
    avalanche = _avalanche_frame(0.0, 0.0)
    centered_result = _induce(avalanche, centered)
    translated_result = _induce(avalanche, translated)
    assert centered[1].strips[0].x_min == -10.0
    assert translated[1].strips[0].x_min == 40.0
    assert float(centered_result.loc[0, "readout_assigned_fraction_1"]) > float(
        translated_result.loc[0, "readout_assigned_fraction_1"]
    )


def test_odd_even_width_order_is_configuration_driven():
    config = _readout_config()
    planes = config["readout_geometry_mm"]["planes"]
    planes["1"] = _generated_plane(y_min=-4.5, widths=[1.0, 2.0, 3.0, 4.0], gap=0.0)
    planes["2"] = _generated_plane(y_min=-4.5, widths=[4.0, 3.0, 2.0, 1.0], gap=0.0)
    geometry, _ = build_readout_geometry(config)
    widths_1 = [s.y_max - s.y_min for s in geometry[1].strips]
    widths_2 = [s.y_max - s.y_min for s in geometry[2].strips]
    assert widths_1 == [1.0, 2.0, 3.0, 4.0]
    assert widths_2 == [4.0, 3.0, 2.0, 1.0]


def test_legacy_active_alias_and_readout_fallback_reproduce_old_geometry_and_charge():
    with pytest.warns(FutureWarning, match="bounds_mm is deprecated"):
        active, source = resolve_active_area_bounds(
            {"bounds_mm": {"x_min": -120, "x_max": 130, "y_min": -140, "y_max": 145}}
        )
    assert source == "legacy_bounds_mm"
    with pytest.warns(FutureWarning, match="legacy readout fallback"):
        fallback, fallback_source = build_readout_geometry({}, legacy_active_area_bounds=active)
    direct = build_legacy_readout_geometry(active)
    assert fallback_source == "legacy_fallback"
    assert _strip_rectangles(fallback) == _strip_rectangles(direct)
    assert [s.y_max - s.y_min for s in fallback[1].strips] == list(LEGACY_Y_WIDTHS[0])

    result = _induce(_avalanche_frame(0.0, 0.0), fallback)
    strip = fallback[1].strips[0]
    manual_fraction = isotropic_lorentzian_rectangle_fraction(
        np.array([0.0]), np.array([0.0]), np.array([0.08]),
        active.x_min, active.x_max, strip.y_min, strip.y_max,
    )[0]
    expected_charge = 1.0e6 * ELEMENTARY_CHARGE_FC * manual_fraction
    assert float(result.loc[0, "Y_mea_1_s1"]) == pytest.approx(expected_charge, rel=2e-6)


def test_explicit_boundaries_normalize_to_same_model():
    plane = build_plane_readout_geometry(
        1,
        {
            "x_min": 10.0,
            "x_max": 20.0,
            "strip_y_bounds_mm": [[5.0, 6.0], [7.0, 9.0], [10.0, 13.0], [14.0, 18.0]],
        },
    )
    assert plane.interstrip_gap_mm is None
    assert plane.interstrip_gaps_mm == (1.0, 1.0, 1.0)
    assert plane.strips[3].y_max == 18.0


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda planes: planes.pop("4"), "missing required plane"),
        (lambda planes: planes["1"].update(strip_widths_mm=[1.0, 1.0, 1.0]), "exactly four"),
        (lambda planes: planes["1"].update(interstrip_gap_mm=-1.0), "must be >= 0"),
        (lambda planes: planes["1"].update(x_min=5.0, x_max=5.0), "x_min < x_max"),
        (lambda planes: planes["1"].update(y_max=999.0), "does not agree"),
        (
            lambda planes: planes["1"].update(strip_y_bounds_mm=[[0, 1], [2, 3], [4, 5], [6, 7]]),
            "either strip_y_bounds_mm",
        ),
    ],
)
def test_invalid_generated_configurations_fail_clearly(mutation, message):
    config = _readout_config()
    planes = config["readout_geometry_mm"]["planes"]
    mutation(planes)
    with pytest.raises(ValueError, match=message):
        build_readout_geometry(config)


@pytest.mark.parametrize(
    ("explicit_bounds", "message"),
    [
        ([[0.0, 2.0], [1.0, 3.0], [4.0, 5.0], [6.0, 7.0]], "overlap"),
        ([[2.0, 3.0], [0.0, 1.0], [4.0, 5.0], [6.0, 7.0]], "sorted"),
        ([[0.0, 1.0], [2.0, 3.0], [4.0, np.inf], [6.0, 7.0]], "finite"),
        ([[0.0, 1.0], [2.0, 2.0], [4.0, 5.0], [6.0, 7.0]], "y_min < y_max"),
    ],
)
def test_invalid_explicit_boundaries_fail_clearly(explicit_bounds, message):
    with pytest.raises(ValueError, match=message):
        build_plane_readout_geometry(
            1,
            {"x_min": -1.0, "x_max": 1.0, "strip_y_bounds_mm": explicit_bounds},
        )


def test_physics_independence_in_both_directions_with_seeded_avalanche():
    readout_config = _readout_config(x_min=-20.0, x_max=20.0, y_min=-5.5)
    geometry_a, _ = build_readout_geometry(
        readout_config, legacy_active_area_bounds=RectBounds(-100, 100, -100, 100)
    )
    geometry_b, _ = build_readout_geometry(
        readout_config, legacy_active_area_bounds=RectBounds(-10, 10, -10, 10)
    )
    assert _strip_rectangles(geometry_a) == _strip_rectangles(geometry_b)

    muons = _muons([5.0, 50.0])
    broad = calculate_intersections(muons, [0.0] * 4, RectBounds(-100, 100, -100, 100), 299.792458)
    narrow = calculate_intersections(muons, [0.0] * 4, RectBounds(-10, 10, -10, 10), 299.792458)
    broad_avalanche = build_avalanche(broad, [0.999] * 4, 1.0, 1.0, 0.0, np.random.default_rng(7))
    narrow_avalanche = build_avalanche(narrow, [0.999] * 4, 1.0, 1.0, 0.0, np.random.default_rng(7))
    assert broad_avalanche["avalanche_exists_1"].sum() >= narrow_avalanche["avalanche_exists_1"].sum()
    assert not broad["tt_crossing"].equals(narrow["tt_crossing"])

    shifted_config = _readout_config(x_min=30.0, x_max=50.0, y_min=20.0)
    shifted_geometry, _ = build_readout_geometry(shifted_config)
    fixed_avalanche = _avalanche_frame(5.0, 0.0)
    q_a = _induce(fixed_avalanche, geometry_a)
    q_b = _induce(fixed_avalanche, shifted_geometry)
    assert float(q_a.loc[0, "readout_assigned_fraction_1"]) != pytest.approx(
        float(q_b.loc[0, "readout_assigned_fraction_1"])
    )
    # Readout-only changes never feed back into Step 2/3 production.
    pd.testing.assert_frame_equal(broad, broad.copy())
    pd.testing.assert_series_equal(
        broad_avalanche["avalanche_x_1"], broad_avalanche["X_gen_1"], check_names=False
    )


def test_normalized_readout_identity_changes_with_strip_coordinates():
    geometry_a, _ = build_readout_geometry(_readout_config(x_min=-10.0, x_max=10.0))
    geometry_b, _ = build_readout_geometry(_readout_config(x_min=-11.0, x_max=10.0))
    normalized_a = readout_geometry_to_dict(geometry_a, detailed=False)
    normalized_b = readout_geometry_to_dict(geometry_b, detailed=False)
    assert normalized_a != normalized_b
    assert _json_fingerprint({"readout_geometry_mm": normalized_a}) != _json_fingerprint(
        {"readout_geometry_mm": normalized_b}
    )


def test_new_active_key_precedes_legacy_alias_and_warns():
    config = {
        "active_area_bounds_mm": {"x_min": -1, "x_max": 1, "y_min": -2, "y_max": 2},
        "bounds_mm": {"x_min": -9, "x_max": 9, "y_min": -9, "y_max": 9},
    }
    with pytest.warns(FutureWarning, match="ignored"):
        active, source = resolve_active_area_bounds(config)
    assert active == RectBounds(-1.0, 1.0, -2.0, 2.0)
    assert source == "active_area_bounds_mm"
