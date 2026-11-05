from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from environment_context import (  # noqa: E402
    ENVIRONMENT_COLUMNS,
    REDUCED_FIELD_COLUMN,
    generate_environment_context,
    load_environment_data,
)
from calibration_context import (  # noqa: E402
    _qf_vs_qb_plot,
    generate_calibration_temperature_plots,
)


def _write_daily_product(station: Path) -> None:
    destination = (
        station / "STAGE_1_PRODUCTS" / "LOG_DATA" / "OUTPUT_FILES"
        / "2026" / "01" / "lab_logs_2026_01_31.csv"
    )
    destination.parent.mkdir(parents=True)
    rows = pd.DataFrame({
        "Time": pd.to_datetime(["2026-01-31 15:00:00", "2026-01-31 15:01:00"]),
        **{
            column: [float(index + 1), float(index + 2)]
            for index, column in enumerate(ENVIRONMENT_COLUMNS)
        },
    })
    rows["hv_HVneg"] = [5.4, 5.5]
    rows["hv_HVpos"] = [5.2, 5.3]
    rows["sensors_ext_Temperature_ext"] = [20.0, 21.0]
    rows["sensors_ext_Pressure_ext"] = [1000.0, 1001.0]
    rows.to_csv(destination, index=False)


def test_load_environment_data_keeps_schema_and_exact_reduced_field(tmp_path: Path) -> None:
    station = tmp_path / "MINGO01"
    _write_daily_product(station)

    frame, sources, left, right = load_environment_data(
        station,
        datetime(2026, 1, 31, 15, 0),
        datetime(2026, 1, 31, 15, 1),
        context_fraction=0.0,
    )

    assert len(sources) == 1
    assert left == pd.Timestamp("2026-01-31 15:00:00")
    assert right == pd.Timestamp("2026-01-31 15:01:00")
    assert set(ENVIRONMENT_COLUMNS).issubset(frame.columns)
    mean_voltage_v = ((5.4 + 5.2) / 2.0) * 1000.0
    expected = 0.13806 * mean_voltage_v * (20.0 + 273.15) / (1000.0 * 1.0)
    assert np.isclose(frame.iloc[0][REDUCED_FIELD_COLUMN], expected)


def test_generator_writes_environment_figures_and_source_csv(tmp_path: Path) -> None:
    station = tmp_path / "MINGO01"
    _write_daily_product(station)
    output = tmp_path / "context"

    paths = generate_environment_context(
        station,
        datetime(2026, 1, 31, 15, 0),
        datetime(2026, 1, 31, 15, 1),
        output,
        "Synthetic selection",
        context_fraction=0.0,
    )

    assert [path.name for path in paths] == [
        "00_environment_data.csv",
        "01_environment_overview.png",
        "02_rates_and_reduced_field.png",
        "03_odroid_disk_fill.png",
        "04_reduced_field_vs_multiplexer_rates.png",
    ]
    assert all(path.is_file() and path.stat().st_size > 0 for path in paths)


def test_calibration_offsets_are_plotted_against_synchronized_temperature(
    tmp_path: Path,
) -> None:
    calibration_path = tmp_path / "calibration.csv"
    environment_path = tmp_path / "environment.csv"
    calibration = pd.DataFrame({
        "filename_base": ["mi0226001000001", "mi0226001000101"],
        "acquisition_datetime": pd.to_datetime([
            "2026-01-01 00:00:00", "2026-01-01 00:01:00",
        ]),
    })
    for plane in range(1, 5):
        for strip in range(1, 5):
            calibration[f"P{plane}_s{strip}_T_sum"] = [strip, strip + 0.5]
            calibration[f"P{plane}_s{strip}_Q_F"] = [strip + 1, strip + 1.5]
            calibration[f"P{plane}_s{strip}_Q_B"] = [strip + 2, strip + 2.5]
    calibration.to_csv(calibration_path, index=False)
    pd.DataFrame({
        "Time": pd.to_datetime([
            "2026-01-01 00:00:10", "2026-01-01 00:01:10",
        ]),
        "sensors_int_Temperature_int": [20.0, 21.0],
    }).to_csv(environment_path, index=False)

    paths = generate_calibration_temperature_plots(
        calibration_path,
        environment_path,
        tmp_path,
        "Synthetic calibration",
        {"mi0226001000001", "mi0226001000101"},
    )

    assert len(paths) == 17
    assert paths[0].name == "06_tsum_p1_s1_offset_vs_temperature.png"
    assert paths[-2].name == "06_tsum_p4_s4_offset_vs_temperature.png"
    assert paths[-1].name == "07_qf_qb_offsets_vs_temperature.png"
    assert all(path.is_file() and path.stat().st_size > 0 for path in paths)


def test_qf_vs_qb_offset_scatter_is_written(tmp_path: Path) -> None:
    frame = pd.DataFrame(index=range(3))
    for plane in range(1, 5):
        for strip in range(1, 5):
            frame[f"P{plane}_s{strip}_Q_F"] = [strip, strip + 1, strip + 2]
            frame[f"P{plane}_s{strip}_Q_B"] = [
                strip + 0.5, strip + 1.5, strip + 2.5,
            ]
    destination = tmp_path / "08_qf_vs_qb_offsets.png"

    _qf_vs_qb_plot(
        frame,
        destination,
        "Synthetic calibration",
        pd.Series([True, False, True], index=frame.index),
    )

    assert destination.is_file()
    assert destination.stat().st_size > 0


def test_local_backup_parser_recovers_non_sensor_channels(tmp_path: Path) -> None:
    from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.STAGES.STAGE_1.LOG_DATA.STEP_2.lab_logs_merge import (
        LOCAL_LOG_BACKUP_LAYOUTS,
        _load_local_backup_log,
    )

    hv = tmp_path / "hv0_2026-01-31.log"
    hv.write_text(
        "2026-01-31T15:00:03 80 1F 12 59 F5 21 0.068 0.064 5.444 5.400 0\n",
        encoding="utf-8",
    )
    rates = tmp_path / "rates_2026-01-31.log"
    rates.write_text(
        "2026-01-31T15:00:53; 16.5 14.5 14.4 222.1 1158.6 80.7 118.4 7.0 3.6 6.3 7.0\n",
        encoding="utf-8",
    )

    hv_frame = _load_local_backup_log(hv, LOCAL_LOG_BACKUP_LAYOUTS["hv"])
    rate_frame = _load_local_backup_log(rates, LOCAL_LOG_BACKUP_LAYOUTS["rates"])

    assert hv_frame.iloc[0]["hv_HVneg"] == 5.444
    assert hv_frame.iloc[0]["hv_CurrentPos"] == 0.064
    assert rate_frame.iloc[0]["rates_Accepted"] == 14.4
    assert rate_frame.iloc[0]["rates_M4"] == 118.4


def test_context_margin_is_ten_percent_of_selected_timespan(tmp_path: Path) -> None:
    station = tmp_path / "MINGO01"
    start = datetime(2026, 1, 30, 12, 0)
    end = datetime(2026, 1, 31, 12, 0)

    _, _, left, right = load_environment_data(
        station, start, end, context_fraction=0.10,
    )

    assert left == pd.Timestamp("2026-01-30 09:36:00")
    assert right == pd.Timestamp("2026-01-31 14:24:00")
