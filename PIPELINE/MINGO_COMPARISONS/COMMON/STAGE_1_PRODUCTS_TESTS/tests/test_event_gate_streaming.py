from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from PIL import Image


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from event_gate_streaming import (  # noqa: E402
    StreamingChargeClusterHistograms,
    StreamingPlaneEfficiencyMaps,
    StreamingPlaneXYHistograms,
    efficiency_summary_frame,
    enabled_gate_comparison_frame,
    gate_rate_frame,
    gate_summary_frame,
)
from test_3_configurable_event_gates import (  # noqa: E402
    Gate,
    Product,
    _fit_gaussian,
    add_derived_topology_columns,
    assign_gates,
    plane_efficiency_map_setting,
    stream_events,
    write_charge_cluster_size_study,
    write_efficiency_time_series,
    write_enabled_gate_comparison,
    write_gate_summary,
    write_gate_time_series,
    write_plane_xy_histograms,
    write_plane_efficiency_maps,
)


def _gates() -> list[Gate]:
    return [
        Gate("1", 1, "x_below_five", {"column": "x", "op": "lt", "value": 5}, "X5"),
        Gate("2", 2, "y_is_one", {"column": "y", "op": "eq", "value": 1}, "Y1"),
    ]


def _events() -> pd.DataFrame:
    return pd.DataFrame({
        "datetime": pd.to_datetime([
            "2026-01-01 00:00:00.100",
            "2026-01-01 00:00:00.900",
            "2026-01-01 00:00:01",
            "2026-01-01 00:09:59",
            "2026-01-01 00:10:00",
            "2026-01-01 00:10:00.500",
            "2026-01-01 00:10:02",
            None,
        ], format="mixed"),
        # The NaN forces float storage, matching schema-drift cases such as 1234.0.
        "tt_task3_list": [1234, 234, 134, 124, 123, 1234, 234, np.nan],
        "x": [1, 7, 2, 9, 3, 8, 4, 1],
        "y": [0, 1, 1, 0, 0, 1, 1, 1],
    })


def _sort(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return frame.sort_values(columns).reset_index(drop=True)


def test_gaussian_rate_fit_returns_expected_population_sigma() -> None:
    values, mean, sigma = _fit_gaussian(pd.Series([1.0, 2.0, 3.0]))

    assert np.array_equal(values, [1.0, 2.0, 3.0])
    assert np.isclose(mean, 2.0)
    assert np.isclose(sigma, np.sqrt(2.0 / 3.0))


def test_charge_cluster_histograms_are_streamable_and_share_x(
    tmp_path: Path,
) -> None:
    histograms = StreamingChargeClusterHistograms(
        np.asarray([0.0, 10.0, 20.0, 30.0]),
    )
    frame = pd.DataFrame()
    for plane in range(1, 5):
        frame[f"p{plane}_qsum"] = [5.0, 15.0, 25.0, 35.0, -1.0, np.nan]
        frame[f"p{plane}_cluster_size"] = [1, 2, 3, 4, 1, 1]
    masks = {
        "1": pd.Series(True, index=frame.index),
        "2": pd.Series(
            [True, False, True, False, True, False], index=frame.index,
        ),
    }
    histograms.accumulate(
        frame.iloc[:3], {code: mask.iloc[:3] for code, mask in masks.items()},
    )
    histograms.accumulate(
        frame.iloc[3:], {code: mask.iloc[3:] for code, mask in masks.items()},
    )

    for plane in range(1, 5):
        assert np.array_equal(histograms.counts[("1", plane, 1)], [1, 0, 0])
        assert np.array_equal(histograms.counts[("1", plane, 2)], [0, 1, 0])
        assert np.array_equal(histograms.counts[("1", plane, 3)], [0, 0, 1])
        assert histograms.underflow[("1", plane, 1)] == 1
        assert histograms.overflow[("1", plane, 4)] == 1
        assert np.array_equal(histograms.counts[("2", plane, 1)], [1, 0, 0])
        assert np.array_equal(histograms.counts[("2", plane, 3)], [0, 0, 1])
        assert histograms.underflow[("2", plane, 1)] == 1
        assert histograms.overflow[("2", plane, 4)] == 0

    outputs = write_charge_cluster_size_study(
        histograms, _gates(),
        tmp_path / "CHARGE_CLUSTER_SIZE_STUDY", "synthetic",
    )
    assert len(outputs) == 2
    assert outputs[0][0].name.startswith("gate_1_")
    assert outputs[1][0].name.startswith("gate_2_")
    plot_path, csv_path = outputs[0]
    assert plot_path.is_file()
    assert csv_path.is_file()
    with Image.open(plot_path) as image:
        assert image.height / image.width >= 0.9
    exported = pd.read_csv(csv_path)
    assert len(exported) == 4 * 4 * 3
    assert exported["events"].sum() == 12


def test_plane_xy_histograms_are_streamable_per_gate_and_plane(
    tmp_path: Path,
) -> None:
    setting = {
        "x_column": "event_x",
        "y_column": "event_y",
        "x_slope_column": "event_xp",
        "y_slope_column": "event_yp",
        "z_columns": [f"z_p{plane}" for plane in range(1, 5)],
    }
    histograms = StreamingPlaneXYHistograms(
        setting,
        np.asarray([-10.0, 0.0, 10.0]),
        np.asarray([-10.0, 0.0, 10.0]),
    )
    frame = pd.DataFrame({
        "event_x": [-2.0, 2.0, 4.0, 100.0],
        "event_y": [-2.0, 2.0, 4.0, 100.0],
        "event_xp": [0.0, 0.0, 0.0, 0.0],
        "event_yp": [0.0, 0.0, 0.0, 0.0],
        **{f"z_p{plane}": [float(plane)] * 4 for plane in range(1, 5)},
    })
    masks = {
        "1": pd.Series([True, True, True, True]),
        "2": pd.Series([False, True, True, False]),
    }
    histograms.accumulate(
        frame.iloc[:2], {code: mask.iloc[:2] for code, mask in masks.items()},
    )
    histograms.accumulate(
        frame.iloc[2:], {code: mask.iloc[2:] for code, mask in masks.items()},
    )
    for plane in range(1, 5):
        assert histograms.counts[("1", plane)].sum() == 3
        assert histograms.outside[("1", plane)] == 1
        assert histograms.counts[("2", plane)].sum() == 2
        assert histograms.outside[("2", plane)] == 0

    outputs = write_plane_xy_histograms(
        histograms, _gates(), tmp_path / "PLANE_XY_HISTOGRAMS", "synthetic",
    )
    assert len(outputs) == 2
    for plot_path, csv_path in outputs:
        assert plot_path.is_file()
        assert csv_path.is_file()
        with Image.open(plot_path) as image:
            assert image.width > image.height


def test_plane_efficiency_maps_use_matching_missing_topologies(
    tmp_path: Path,
) -> None:
    setting = {
        "x_column": "event_x",
        "y_column": "event_y",
        "x_slope_column": "event_xp",
        "y_slope_column": "event_yp",
        "topology_column": "tt_task3_list",
        "z_columns": [f"z_p{plane}" for plane in range(1, 5)],
    }
    maps = StreamingPlaneEfficiencyMaps(
        setting,
        np.asarray([-10.0, 0.0, 10.0]),
        np.asarray([-10.0, 0.0, 10.0]),
    )
    frame = pd.DataFrame({
        "event_x": [2.0] * 5,
        "event_y": [2.0] * 5,
        "event_xp": [0.0] * 5,
        "event_yp": [0.0] * 5,
        "tt_task3_list": [1234, 234, 134, 124, 123],
        **{f"z_p{plane}": [float(plane)] * 5 for plane in range(1, 5)},
    })
    topologies = frame["tt_task3_list"].astype("string")
    masks = {
        "1": pd.Series(True, index=frame.index),
        "2": pd.Series([True, False, False, False, False]),
    }
    maps.accumulate(
        frame.iloc[:3],
        topologies.iloc[:3],
        {code: mask.iloc[:3] for code, mask in masks.items()},
    )
    maps.accumulate(
        frame.iloc[3:],
        topologies.iloc[3:],
        {code: mask.iloc[3:] for code, mask in masks.items()},
    )

    for plane in range(1, 5):
        assert maps.detected_counts[("1", plane)].sum() == 1
        assert maps.missing_counts[("1", plane)].sum() == 1
        assert maps.detected_counts[("2", plane)].sum() == 1
        assert maps.missing_counts[("2", plane)].sum() == 0

    outputs = write_plane_efficiency_maps(
        maps, _gates(), tmp_path / "EFFICIENCY_PLANE", "synthetic",
    )
    assert len(outputs) == 2
    for detected_path, missing_path, efficiency_path, csv_path in outputs:
        assert detected_path.is_file()
        assert missing_path.is_file()
        assert efficiency_path.is_file()
        assert csv_path.is_file()
    first_gate = pd.read_csv(outputs[0][3])
    populated = first_gate.loc[
        first_gate["topology_1234_count"].gt(0)
        & first_gate["missing_topology_count"].gt(0)
    ]
    assert len(populated) == 4
    assert np.allclose(populated["efficiency"], 0.5)


def test_plane_efficiency_setting_inherits_xy_histogram_layout() -> None:
    available = {
        "event_x", "event_y", "event_xp", "event_yp", "tt_task3_list",
        "z_p1", "z_p2", "z_p3", "z_p4",
    }
    setting = plane_efficiency_map_setting(
        {
            "plane_xy_histograms": {
                "bins": 80,
                "x_range": [-180, 180],
                "y_range": [-190, 190],
            },
            "efficiency_plane": {"enabled": True},
        },
        available,
    )

    assert setting is not None
    assert setting["bins"] == 80
    assert setting["x_range"] == (-180.0, 180.0)
    assert setting["y_range"] == (-190.0, 190.0)


def test_streamed_reductions_equal_in_memory_outputs(tmp_path: Path) -> None:
    events = _events()
    files: list[Product] = []
    for index, part in enumerate((events.iloc[:4], events.iloc[4:]), 1):
        path = tmp_path / f"part_{index}.parquet"
        part.to_parquet(path, index=False)
        files.append(Product(path, f"mi022600100000{index}", datetime(2026, 1, 1)))

    gates = _gates()
    topology_setting = {
        "enabled": False,
        "source_suffix": "qsum_cal",
        "active_when": "gt",
        "threshold": 0.0,
    }
    checkpoint_path = tmp_path / "checkpoint.pickle"
    aggregates = stream_events(
        files,
        ["datetime", "tt_task3_list", "x", "y"],
        gates,
        topology_setting,
        time_column="datetime",
        topology_column="tt_task3_list",
        window=pd.Timedelta("10min"),
        batch_size=3,
        checkpoint_path=checkpoint_path,
        fingerprint="synthetic-v1",
        checkpoint_every_files=1,
    )
    resumed = stream_events(
        files,
        ["datetime", "tt_task3_list", "x", "y"],
        gates,
        topology_setting,
        time_column="datetime",
        topology_column="tt_task3_list",
        window=pd.Timedelta("10min"),
        batch_size=3,
        checkpoint_path=checkpoint_path,
        fingerprint="synthetic-v1",
        checkpoint_every_files=1,
    )
    assert resumed.total_events == len(events)
    assert dict(resumed.combined_totals) == dict(aggregates.combined_totals)

    baseline = events.copy()
    add_derived_topology_columns(baseline, topology_setting)
    masks = assign_gates(baseline, gates)

    expected_summary = write_gate_summary(
        baseline, gates, masks, tmp_path / "expected_summary.csv",
    )
    actual_summary = gate_summary_frame(aggregates, gates)
    assert_frame_equal(
        _sort(actual_summary, ["kind", "gate_code"]),
        _sort(expected_summary, ["kind", "gate_code"]),
        check_dtype=False,
    )

    rate_setting = {
        "column": "datetime",
        "window": pd.Timedelta("10min"),
    }
    expected_rate_dir = tmp_path / "expected_rate"
    expected_rate_dir.mkdir()
    expected_rate_path, _ = write_gate_time_series(
        baseline, gates, masks, rate_setting, expected_rate_dir, "baseline",
    )
    expected_rates = pd.read_csv(expected_rate_path)
    actual_rates = gate_rate_frame(aggregates, gates)
    actual_rates["window_start"] = actual_rates["window_start"].astype(str)
    actual_rates["window_end"] = actual_rates["window_end"].astype(str)
    assert_frame_equal(actual_rates, expected_rates, check_dtype=False)
    assert actual_rates["observed_seconds"].tolist() == [3, 2]

    efficiency_setting = {
        "time_column": "datetime",
        "topology_column": "tt_task3_list",
        "window": pd.Timedelta("10min"),
        "selections": None,
        "include_combined_zero": False,
    }
    expected_efficiency_dir = tmp_path / "expected_efficiency"
    expected_efficiency_dir.mkdir()
    expected_efficiency_path, _ = write_efficiency_time_series(
        baseline, gates, masks, efficiency_setting,
        expected_efficiency_dir, "baseline",
    )
    expected_efficiency = pd.read_csv(
        expected_efficiency_path, dtype={"gate_code": str},
    )
    actual_efficiency = efficiency_summary_frame(
        aggregates, gates, efficiency_setting,
    )
    for column in ("window_start", "window_end"):
        actual_efficiency[column] = actual_efficiency[column].astype(str)
    assert_frame_equal(
        _sort(actual_efficiency, ["selection_kind", "gate_code", "window_start"]),
        _sort(expected_efficiency, ["selection_kind", "gate_code", "window_start"]),
        check_dtype=False,
    )

    expected_comparison_dir = tmp_path / "expected_comparison"
    expected_comparison_dir.mkdir()
    comparison_setting = {
        "time_column": "datetime",
        "topology_column": "tt_task3_list",
        "window": pd.Timedelta("10min"),
        "relative_corrected_rate_y_half_range": 0.5,
        "corrected_to_all_ratio": None,
    }
    (
        _,
        metrics_path,
        _,
        _,
        comparison_path,
        _,
    ) = write_enabled_gate_comparison(
        baseline, gates, masks, comparison_setting,
        expected_comparison_dir, "baseline", None,
    )
    with Image.open(metrics_path) as image:
        width, height = image.size
    assert height / width > 0.9
    stability_path = (
        expected_comparison_dir / "enabled_gate_rate_stability_histograms.png"
    )
    assert stability_path.is_file()
    with Image.open(stability_path) as image:
        assert image.width > image.height
    expected_comparison = pd.read_csv(comparison_path, dtype={"gate_code": str})
    relative_means = (
        expected_comparison.groupby("gate_code")["relative_corrected_1234_rate"]
        .mean()
        .dropna()
    )
    assert np.allclose(relative_means.to_numpy(dtype=float), 1.0)
    actual_comparison = enabled_gate_comparison_frame(aggregates, gates)
    comparable = list(actual_comparison.columns)
    for column in ("window_start", "window_end"):
        actual_comparison[column] = actual_comparison[column].astype(str)
    assert_frame_equal(
        _sort(actual_comparison, ["gate_code", "window_start"]),
        _sort(expected_comparison[comparable], ["gate_code", "window_start"]),
        check_dtype=False,
    )
