from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


MASTER_STEPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MASTER_STEPS))

from STEP_2.step_2_generated_to_crossing import calculate_intersections  # noqa: E402
from STEP_3.step_3_crossing_to_hit import prune_step3  # noqa: E402
from STEP_4.step_4_hit_to_measured import (  # noqa: E402
    prune_step4,
    select_step4_input_columns,
)
from STEP_5.step_5_measured_to_triggered import prune_step5  # noqa: E402
from STEP_6.step_6_triggered_to_timing import prune_step6  # noqa: E402
from STEP_7.step_7_timing_to_uncalibrated import prune_step7  # noqa: E402
from STEP_8.step_8_uncalibrated_to_threshold import prune_step8  # noqa: E402
from STEP_9.step_9_threshold_to_trigger import (  # noqa: E402
    CROSSING_COUNTER_COLUMN,
    UNIT_TRIGGER_COUNTER_COLUMN,
    GeometricRateCounter,
    apply_trigger,
    geometric_trigger_passes,
    prune_step9,
    trigger_plane_mask,
)
from STEP_10.step_10_triggered_to_jitter import prune_step10  # noqa: E402
from STEP_FINAL.step_final_daq_to_station_dat import (  # noqa: E402
    aligned_geometric_rates,
    build_sidecar_source_record,
    order_simulation_parameter_columns,
)
from STEP_SHARED.sim_utils import RectBounds  # noqa: E402


def test_step2_encodes_crossed_planes_as_four_bit_mask() -> None:
    frame = pd.DataFrame({
        "event_id": [0, 1],
        "T_thick_s": [0.0, 1.0],
        "X_gen": [0.0, 200.0],
        "Y_gen": [0.0, 0.0],
        "Z_gen": [0.0, 0.0],
        "Theta_gen": [0.0, 0.0],
        "Phi_gen": [0.0, 0.0],
    })
    crossed = calculate_intersections(
        frame,
        [0.0, 10.0, 20.0, 30.0],
        RectBounds(-100.0, 100.0, -100.0, 100.0),
        299.792458,
    )

    assert crossed["crossing_mask"].dtype == np.uint8
    assert crossed["crossing_mask"].tolist() == [15, 0]
    assert crossed["tt_crossing"].astype("string").tolist()[0] == "1234"
    assert pd.isna(crossed["tt_crossing"].iloc[1])


def test_step4_main_input_selection_preserves_crossing_mask() -> None:
    frame = pd.DataFrame({
        "event_id": [1],
        "crossing_mask": [15],
        "avalanche_size_electrons_1": [10.0],
        "unrelated": [99],
    })
    selected = select_step4_input_columns(frame)

    assert "crossing_mask" in selected.columns
    assert "unrelated" not in selected.columns


def test_crossing_mask_survives_steps_three_through_eight() -> None:
    frame = pd.DataFrame({"event_id": [1], "crossing_mask": [15]})
    for prune in (prune_step3, prune_step4, prune_step5, prune_step6, prune_step7, prune_step8):
        frame = prune(frame)
        assert frame["crossing_mask"].tolist() == [15]


def test_geometry_trigger_logic_matches_plane_combinations() -> None:
    assert trigger_plane_mask("12") == 0b0011
    assert trigger_plane_mask("34") == 0b1100
    assert trigger_plane_mask("13") == 0b0101
    assert trigger_plane_mask("15") is None

    masks = pd.Series([1, 3, 6, 12, 15], dtype=np.uint8)
    passed = geometric_trigger_passes(masks, ["12", "34"])
    assert passed.tolist() == [False, True, False, True, True]


def test_rate_counters_continue_across_chunks() -> None:
    counter = GeometricRateCounter()
    first = counter.annotate(
        pd.DataFrame({"crossing_mask": pd.Series([3, 1], dtype=np.uint8)}),
        ["12"],
    )
    second = counter.annotate(
        pd.DataFrame({"crossing_mask": pd.Series([15, 6], dtype=np.uint8)}),
        ["12"],
    )

    assert first[CROSSING_COUNTER_COLUMN].tolist() == [1, 2]
    assert first[UNIT_TRIGGER_COUNTER_COLUMN].tolist() == [1, 1]
    assert second[CROSSING_COUNTER_COLUMN].tolist() == [3, 4]
    assert second[UNIT_TRIGGER_COUNTER_COLUMN].tolist() == [2, 2]
    assert counter.summary() == {
        "version": 1,
        "status": "available",
        "reason": None,
        "crossing_rows": 4,
        "unit_efficiency_trigger_rows": 2,
        "actual_trigger_rows": 0,
    }


def test_actual_trigger_is_required_to_be_geometrically_possible() -> None:
    frame = pd.DataFrame({
        "crossing_mask": pd.Series([1], dtype=np.uint8),
        "Q_front_1_s1": [1.0],
        "Q_front_2_s1": [1.0],
    })
    try:
        apply_trigger(frame, ["12"], GeometricRateCounter())
    except ValueError as exc:
        assert "unit-efficiency geometrical trigger" in str(exc)
    else:
        raise AssertionError("A trigger inconsistent with the crossing mask was accepted")


def test_legacy_step9_inputs_continue_without_rate_counters() -> None:
    frame = pd.DataFrame({
        "event_id": [1],
        "Q_front_1_s1": [1.0],
        "Q_front_2_s1": [1.0],
    })
    counter = GeometricRateCounter()
    filtered = apply_trigger(frame, ["12"], counter)

    assert len(filtered) == 1
    assert CROSSING_COUNTER_COLUMN not in filtered
    assert counter.summary()["status"] == "unavailable"
    assert "legacy input" in str(counter.summary()["reason"])


def test_step10_and_sidecar_preserve_counter_provenance() -> None:
    frame = pd.DataFrame({
        "event_id": [7],
        "T_thick_s": [12.0],
        CROSSING_COUNTER_COLUMN: [101],
        UNIT_TRIGGER_COUNTER_COLUMN: [44],
    })
    kept = prune_step10(frame)
    assert kept[CROSSING_COUNTER_COLUMN].tolist() == [101]
    assert kept[UNIT_TRIGGER_COUNTER_COLUMN].tolist() == [44]

    record = build_sidecar_source_record(kept.iloc[0].to_dict(), 0)
    assert record[CROSSING_COUNTER_COLUMN] == 101
    assert record[UNIT_TRIGGER_COUNTER_COLUMN] == 44



def test_synthetic_trigger_block_produces_ordered_interval_rates() -> None:
    frame = pd.DataFrame({
        "event_id": [0, 1, 2, 3],
        "T_thick_s": [0.0, 2.0, 6.0, 10.0],
        "crossing_mask": pd.Series([3, 3, 3, 15], dtype=np.uint8),
        "Q_front_1_s1": [1.0, 0.0, 1.0, 1.0],
        "Q_front_2_s1": [1.0, 0.0, 1.0, 1.0],
    })
    filtered = prune_step9(
        apply_trigger(frame, ["12"], GeometricRateCounter()),
    )
    assert filtered["event_id"].tolist() == [0, 2, 3]

    crossing_rate, unit_rate, status = aligned_geometric_rates(
        filtered,
        rows_written=len(filtered),
        elapsed_seconds=10.0,
        payload_sampling="sequential_random_start",
    )
    actual_rate = (len(filtered) - 1) / 10.0

    assert status == "available"
    assert np.isclose(crossing_rate, 0.3)
    assert np.isclose(unit_rate, 0.3)
    assert 0.0 <= actual_rate <= unit_rate <= crossing_rate


def test_aligned_rates_share_the_final_file_interval() -> None:
    selected = pd.DataFrame({
        CROSSING_COUNTER_COLUMN: [10, 14, 20],
        UNIT_TRIGGER_COUNTER_COLUMN: [3, 5, 8],
    })
    crossing_rate, unit_rate, status = aligned_geometric_rates(
        selected,
        rows_written=3,
        elapsed_seconds=10.0,
        payload_sampling="sequential_random_start",
    )

    assert status == "available"
    assert np.isclose(crossing_rate, 1.0)
    assert np.isclose(unit_rate, 0.5)
    actual_trigger_rate = (3 - 1) / 10.0
    geometric_efficiency = unit_rate / crossing_rate
    conditional_efficiency = actual_trigger_rate / unit_rate
    assert np.isclose(
        actual_trigger_rate / crossing_rate,
        geometric_efficiency * conditional_efficiency,
    )


def test_new_rate_columns_are_nullable_for_legacy_csv_rows() -> None:
    legacy = pd.DataFrame([{
        "file_name": "old.dat",
        "original_rows": 100,
        "requested_rows": 50,
        "selected_rows": 50,
        "trigger_rate_hz": 2.0,
        "sample_start_index": 3,
    }])
    new = pd.DataFrame([{
        "file_name": "new.dat",
        "original_rows": 100,
        "requested_rows": 50,
        "selected_rows": 50,
        "particle_crossing_rate_hz": 10.0,
        "trigger_rate_unit_efficiency_hz": 5.0,
        "trigger_rate_hz": 2.0,
        "sample_start_index": 4,
    }])
    combined = order_simulation_parameter_columns(
        pd.concat([legacy, new], ignore_index=True),
    )

    selected_index = combined.columns.get_loc("selected_rows")
    assert combined.columns[selected_index + 1:selected_index + 4].tolist() == [
        "particle_crossing_rate_hz",
        "trigger_rate_unit_efficiency_hz",
        "trigger_rate_hz",
    ]
    assert np.isnan(combined.loc[0, "particle_crossing_rate_hz"])
    assert np.isnan(combined.loc[0, "trigger_rate_unit_efficiency_hz"])
    assert combined.loc[0, "trigger_rate_hz"] == 2.0


def test_aligned_rates_are_nullable_for_legacy_or_random_inputs() -> None:
    legacy = pd.DataFrame({"event_id": [1, 2]})
    crossing_rate, unit_rate, status = aligned_geometric_rates(
        legacy, 2, 1.0, "sequential_random_start",
    )
    assert np.isnan(crossing_rate)
    assert np.isnan(unit_rate)
    assert "legacy input" in status

    selected = pd.DataFrame({
        CROSSING_COUNTER_COLUMN: [1, 2],
        UNIT_TRIGGER_COUNTER_COLUMN: [1, 2],
    })
    crossing_rate, unit_rate, status = aligned_geometric_rates(
        selected, 2, 1.0, "random",
    )
    assert np.isnan(crossing_rate)
    assert np.isnan(unit_rate)
    assert "sequential_random_start" in status
