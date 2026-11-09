from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from test_3_configurable_event_gates import (  # noqa: E402
    angular_values,
    assign_gates,
    condition_columns,
    combined_decimal_code_from_labels,
    efficiency_product_from_frame,
    efficiency_product_setting,
    enabled_gate_comparison_setting,
    environment_frequency_efficiency_setting,
    fit_projection_summary,
    fit_projection_time_series_setting,
    load_configuration,
    parse_gates,
    gate_from_short_label,
    streaming_fingerprint,
    streaming_parameters,
    write_enabled_gate_comparison,
)


CONFIG = SCRIPT_DIR / "config_test_3_event_gates.yaml"


def enabled_gates():
    config = load_configuration(CONFIG)
    return parse_gates(config["gates"])


def test_runtime_configuration_loads_relative_gate_file() -> None:
    config = load_configuration(CONFIG)

    assert "gates" in config
    assert config["gates_config_path"].name == (
        "config_test_3_gate_definitions.yaml"
    )
    assert config["config_paths"] == (
        CONFIG.resolve(),
        config["gates_config_path"],
    )


def test_streaming_fingerprint_includes_gate_configuration(
    tmp_path: Path,
) -> None:
    runtime_path = tmp_path / "runtime.yaml"
    gate_path = tmp_path / "gates.yaml"
    runtime_path.write_text("station: 2\n", encoding="utf-8")
    gate_path.write_text("gates: []\n", encoding="utf-8")
    layout = ("datetime", "tt_task3_list", pd.Timedelta("10min"))

    before = streaming_fingerprint(
        (runtime_path, gate_path), [], ["datetime"], layout,
    )
    gate_path.write_text("gates:\n  - changed\n", encoding="utf-8")
    after = streaming_fingerprint(
        (runtime_path, gate_path), [], ["datetime"], layout,
    )

    assert before != after


def topology_frame(patterns: list[tuple[str, str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame({
        f"p{plane}_strip_topology": [row[plane - 1] for row in patterns]
        for plane in range(1, 5)
    })


def test_gate_codes_follow_enabled_order_and_are_exposed_as_decimal() -> None:
    raw = [
        {
            "enabled": True, "name": "first", "short_label": "FIRST",
            "condition": {"column": "x", "op": "eq", "value": 1},
        },
        {
            "enabled": False, "name": "disabled", "short_label": "OFF",
            "condition": {"column": "x", "op": "eq", "value": 0},
        },
        {
            "enabled": True, "name": "second", "short_label": "SECOND",
            "condition": {"column": "y", "op": "eq", "value": 1},
        },
        {
            "enabled": True, "name": "third", "short_label": "THIRD",
            "condition": {"column": "z", "op": "eq", "value": 1},
        },
    ]
    gates = parse_gates(raw)

    assert [gate.binary_code for gate in gates] == ["1", "10", "100"]
    assert [gate.code for gate in gates] == ["1", "2", "4"]
    assert gate_from_short_label(
        gates, "SECOND", location="test"
    ).code == "2"
    assert combined_decimal_code_from_labels(
        gates, ["FIRST", "THIRD"], location="test"
    ) == "5"

    comparison = enabled_gate_comparison_setting(
        {
            "enabled_gate_comparison": {
                "time_column": "datetime",
                "topology_column": "topology",
                "accumulation_timespan": "10min",
                "corrected_to_all_ratio": {
                    "gate_label": "SECOND",
                    "all_gate_label": "FIRST",
                },
            },
        },
        {"datetime", "topology"},
        gates,
    )
    assert comparison is not None
    assert comparison["corrected_to_all_ratio"] == {
        "gate_code": "2", "gate_label": "SECOND",
        "all_gate_code": "1", "all_gate_label": "FIRST",
    }

    frame = pd.DataFrame({
        "x": [1, 1], "y": [1, 0], "z": [0, 1],
    })
    assign_gates(frame, gates, verbose=False)
    assert frame["gate_code"].tolist() == ["3", "5"]

    with_manual_code = [dict(raw[0], code="100000")]
    try:
        parse_gates(with_manual_code)
    except ValueError as exc:
        assert "assigned automatically" in str(exc)
    else:
        raise AssertionError("A manually configured gate code was accepted")


def test_mingo00_skips_environment_frequency_efficiency_correction() -> None:
    raw = {
        "enabled": True,
        "spectrum_smoothing_sigma_bins": 6.0,
    }
    assert environment_frequency_efficiency_setting({
        "station_name": "MINGO00",
        "environment_frequency_efficiency_correction": raw,
    }) is None
    assert environment_frequency_efficiency_setting({
        "station_name": "MINGO02",
        "environment_frequency_efficiency_correction": raw,
    }) is not None


def test_efficiency_product_plane_modes() -> None:
    frame = pd.DataFrame({
        "plane_1_efficiency": [0.5],
        "plane_2_efficiency": [0.8],
        "plane_3_efficiency": [0.9],
        "plane_4_efficiency": [0.6],
    })
    inner = efficiency_product_setting({
        "efficiency_product_planes": "planes_2_and_3",
    })
    all_planes = efficiency_product_setting({
        "efficiency_product_planes": "all_planes",
    })

    assert np.isclose(
        efficiency_product_from_frame(
            frame, inner["efficiency_product_planes"],
            column_template="plane_{plane}_efficiency",
        ).iloc[0],
        (0.8 * 0.9) ** 2,
    )
    assert np.isclose(
        efficiency_product_from_frame(
            frame, all_planes["efficiency_product_planes"],
            column_template="plane_{plane}_efficiency",
        ).iloc[0],
        0.5 * 0.8 * 0.9 * 0.6,
    )
    try:
        efficiency_product_setting({"efficiency_product_planes": "invalid"})
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid efficiency-product mode was accepted")


def test_signed_theta_flips_for_opposite_phi_directions() -> None:
    frame = pd.DataFrame({
        "event_theta": [0.4, 0.4, 0.7, 0.7],
        "event_phi": [0.2, 0.2 + np.pi, -1.0, -1.0 + np.pi],
    })

    values, unit = angular_values(
        frame,
        {
            "column": "event_theta",
            "sign_by_cosine_column": "event_phi",
        },
        convert_to_degrees=False,
    )

    assert unit == "radians"
    assert np.allclose(values, [0.4, -0.4, 0.7, -0.7])


def test_config_enables_requested_topology_gates() -> None:
    gates = enabled_gates()
    by_label = {gate.short_label: gate for gate in gates}

    assert {
        "0100_3of4", "0010_3of4", "MID_3of4", "CS01_3of4",
        "NG_CS02_3of4",
    }.issubset(by_label)

    frame = topology_frame([
        ("0100", "0100", "0100", "0100"),
        ("0100", "0000", "0100", "0100"),
        ("0100", "0000", "0000", "0100"),
        ("0010", "0010", "0010", "0010"),
        ("0010", "0010", "0000", "0010"),
        ("0100", "0110", "0000", "0010"),
        ("0100", "0110", "0010", "0001"),
    ])
    selected = [
        by_label["0100_3of4"],
        by_label["0010_3of4"],
        by_label["MID_3of4"],
    ]
    masks = assign_gates(frame, selected)

    assert masks[selected[0].code].tolist() == [True, True, False, False, False, False, False]
    assert masks[selected[1].code].tolist() == [False, False, False, True, True, False, False]
    assert masks[selected[2].code].tolist() == [True, True, False, True, True, True, False]


def test_cluster_size_zero_or_one_requires_three_or_four_planes() -> None:
    gate = next(
        gate for gate in enabled_gates() if gate.short_label == "CS01_3of4"
    )
    frame = pd.DataFrame(
        [
            (1, 1, 1, 1),
            (1, 1, 1, 0),
            (1, 1, 0, 1),
            (1, 0, 1, 1),
            (0, 1, 1, 1),
            (1, 1, 0, 0),
            (1, 0, 0, 0),
            (0, 0, 0, 0),
            (2, 1, 1, 1),
            (np.nan, 1, 1, 1),
        ],
        columns=[f"p{plane}_cluster_size" for plane in range(1, 5)],
    )

    mask = assign_gates(frame, [gate])[gate.code]

    assert mask.tolist() == [
        True, True, True, True, True,
        False, False, False, False, False,
    ]


def test_no_disjoint_cluster_size_zero_to_two_requires_three_or_four_planes() -> None:
    gate = next(
        gate for gate in enabled_gates() if gate.short_label == "NG_CS02_3of4"
    )
    topologies = [
        ("0100", "1100", "0110", "0011"),
        ("0100", "1100", "0011", "0000"),
        ("0100", "1100", "0000", "0000"),
        ("1010", "1100", "0011", "0000"),
        ("0100", "1100", "0011", "0000"),
    ]
    cluster_sizes = [
        (1, 2, 2, 2),
        (1, 2, 2, 0),
        (1, 2, 0, 0),
        (2, 2, 2, 0),
        (1, 3, 2, 0),
    ]
    frame = topology_frame(topologies)
    for plane in range(1, 5):
        frame[f"p{plane}_cluster_size"] = [
            row[plane - 1] for row in cluster_sizes
        ]

    mask = assign_gates(frame, [gate])[gate.code]

    assert mask.tolist() == [True, True, False, False, False]


def test_fiducial_track_gate_projects_crossings_to_all_four_planes() -> None:
    gate = next(
        gate for gate in enabled_gates() if gate.short_label == "FID_3of4"
    )
    frame = pd.DataFrame({
        "tt_task3_list": [123, 234, 1234, 12, 1234, 1234],
        "event_x": [0.0, 90.0, 0.0, 0.0, 101.0, 0.0],
        "event_y": [0.0] * 6,
        "event_xp": [0.0, 0.0, 0.20, 0.0, 0.0, np.nan],
        "event_yp": [0.0] * 6,
        "z_p1": [0.0] * 6,
        "z_p2": [100.0] * 6,
        "z_p3": [200.0] * 6,
        "z_p4": [300.0] * 6,
    })

    mask = assign_gates(frame, [gate])[gate.code]

    assert mask.tolist() == [True, True, True, False, False, False]
    assert condition_columns(gate.condition) == {
        "tt_task3_list", "event_x", "event_y", "event_xp", "event_yp",
        "z_p1", "z_p2", "z_p3", "z_p4",
    }


def test_uniform_radius_fiducial_gates() -> None:
    gates = {
        gate.short_label: gate
        for gate in enabled_gates()
        if gate.short_label in {"FID150_3of4", "FID100_3of4"}
    }
    frame = pd.DataFrame({
        "tt_task3_list": [123, 234, 1234, 1234, 12],
        "event_x": [140.0, 90.0, 0.0, 151.0, 0.0],
        "event_y": [0.0] * 5,
        "event_xp": [0.0, 0.0, 0.40, 0.0, 0.0],
        "event_yp": [0.0] * 5,
        "z_p1": [0.0] * 5,
        "z_p2": [100.0] * 5,
        "z_p3": [200.0] * 5,
        "z_p4": [300.0] * 5,
    })

    masks = assign_gates(frame, list(gates.values()))

    assert masks[gates["FID150_3of4"].code].tolist() == [True, True, True, False, False]
    assert masks[gates["FID100_3of4"].code].tolist() == [False, True, False, False, False]


def test_enabled_gate_comparison_writes_both_requested_figures(tmp_path: Path) -> None:
    requested_labels = {"0100_3of4", "0010_3of4", "MID_3of4"}
    gates = [gate for gate in enabled_gates() if gate.short_label in requested_labels]
    patterns = [
        ("0100", "0100", "0100", "0100"),
        ("0010", "0010", "0010", "0010"),
        ("0100", "0110", "0010", "0100"),
    ] * 5
    frame = topology_frame(patterns)
    frame["datetime"] = pd.date_range("2026-01-01", periods=len(frame), freq="s")
    frame["tt_task3_list"] = [1234, 234, 134, 124, 123] * 3
    masks = assign_gates(frame, gates)

    (
        efficiency_path,
        metrics_path,
        normalized_path,
        ratio_path,
        csv_path,
        plot_count,
    ) = write_enabled_gate_comparison(
        frame,
        gates,
        masks,
        {
            "time_column": "datetime",
            "topology_column": "tt_task3_list",
            "window": pd.Timedelta("10min"),
            "relative_corrected_rate_y_half_range": 0.5,
            "corrected_to_all_ratio": None,
        },
        tmp_path,
        "Synthetic gate comparison",
    )

    assert plot_count == 4
    assert efficiency_path.is_file()
    assert metrics_path.is_file()
    assert normalized_path.is_file()
    assert (tmp_path / "enabled_gate_rate_stability_histograms.png").is_file()
    assert ratio_path is None
    assert csv_path.is_file()
    summary = pd.read_csv(csv_path, dtype={"gate_code": str})
    assert set(summary["gate_code"]) == {gate.code for gate in gates}
    assert {
        "plane_1_efficiency",
        "plane_4_efficiency",
        "efficiency_product",
        "total_gate_rate_hz",
        "topology_1234_rate_hz",
        "corrected_1234_rate_hz",
    }.issubset(summary.columns)
    finite = summary.loc[summary["efficiency_product"].gt(0)].iloc[0]
    assert np.isclose(
        finite["corrected_1234_rate_hz"],
        finite["topology_1234_rate_hz"] / finite["efficiency_product"],
    )


def test_fit_projection_summary_uses_event_slopes_and_mad() -> None:
    gates = parse_gates([
        {
            "enabled": True,
            "name": "all",
            "short_label": "ALL",
            "condition": {"column": "keep", "op": "eq", "value": 1},
        },
    ])
    frame = pd.DataFrame({
        "datetime": pd.to_datetime([
            "2026-01-01 00:01:00",
            "2026-01-01 00:02:00",
            "2026-01-01 00:03:00",
            "2026-01-01 00:31:00",
        ]),
        "event_xp": [1.0, 3.0, 8.0, 10.0],
        "event_yp": [-4.0, 0.0, 2.0, np.nan],
        "keep": [1, 1, 1, 1],
    })
    masks = assign_gates(frame, gates, verbose=False)
    setting = fit_projection_time_series_setting(
        {
            "fit_projection_time_series": {
                "time_column": "datetime",
                "xproj_column": "event_xp",
                "yproj_column": "event_yp",
                "accumulation_timespan": "30min",
                "deviation": "mad",
            },
        },
        set(frame.columns),
    )
    assert setting is not None
    summary = fit_projection_summary(frame, gates, masks, setting)

    first = summary.iloc[0]
    assert first["event_count"] == 3
    assert first["xproj_count"] == 3
    assert first["xproj_median"] == 3.0
    assert first["xproj_mad"] == 2.0
    assert first["yproj_count"] == 3
    assert first["yproj_median"] == 0.0
    assert first["yproj_mad"] == 2.0
    second = summary.iloc[1]
    assert second["xproj_median"] == 10.0
    assert second["xproj_mad"] == 0.0
    assert second["yproj_count"] == 0
    assert np.isnan(second["yproj_median"])


def test_streaming_fallback_reports_blocking_analyses() -> None:
    issues: list[str] = []
    layout = streaming_parameters(
        {"column": "datetime", "window": pd.Timedelta("10min")},
        {},
        None,
        None,
        {},
        {},
        {},
        {},
        [{}],
        [{}],
        incompatibilities=issues,
    )

    assert layout is None
    assert {issue.split(":", 1)[0] for issue in issues} == {
        "one_second_burst_diagnostics",
        "plane_combinations",
        "fit_projection_time_series",
        "charge_calibration_comparison",
        "topology_charge_scatter",
        "topology_y_position",
    }
    assert all(issue.endswith("requires event-level data") for issue in issues)


def test_plane_efficiency_only_streaming_retains_topology_column() -> None:
    layout = streaming_parameters(
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        [],
        [],
        plane_efficiency_setting={"topology_column": "tt_task3_list"},
    )

    assert layout == ("", "tt_task3_list", pd.Timedelta("1h"))
