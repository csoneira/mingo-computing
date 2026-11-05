from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from test_1_plot_calibration_offsets import (  # noqa: E402
    calibration_columns,
    select_metadata,
    valid_parquet_lake_basenames,
)


BASE = "mi0126001000000"
OTHER = "mi0126001000100"


def calibration_row(base: str, execution: str, value: float) -> dict[str, object]:
    return {
        "filename_base": base,
        "execution_timestamp": execution,
        **{column: value for column in calibration_columns()},
    }


def test_selection_is_lake_filtered_and_keeps_latest_execution(tmp_path: Path) -> None:
    metadata = tmp_path / "task_2_metadata_calibration.csv"
    pd.DataFrame(
        [
            calibration_row(BASE, "2026-01-01_01.00.00", 1.0),
            calibration_row(OTHER, "2026-01-01_03.00.00", 50.0),
            calibration_row(BASE, "2026-01-01_02.00.00", 9.0),
        ]
    ).to_csv(metadata, index=False)

    selected = select_metadata(
        metadata,
        datetime(2026, 1, 1),
        datetime(2026, 1, 2),
        allowed_basenames={BASE},
    )

    assert selected["filename_base"].tolist() == [BASE]
    assert selected["execution_timestamp"].tolist() == ["2026-01-01_02.00.00"]
    assert selected["P1_s1_Q_F"].tolist() == [9.0]


def test_lake_membership_requires_valid_parquet_magic(tmp_path: Path) -> None:
    station = tmp_path / "MINGO01"
    lake = station / "STAGE_1_PRODUCTS" / "EVENT_DATA" / "PARQUET_LAKE"
    lake.mkdir(parents=True)
    (lake / f"postprocessed_{BASE}.parquet").write_bytes(b"PAR1payloadPAR1")
    (lake / f"postprocessed_{OTHER}.parquet").write_bytes(b"broken")

    assert valid_parquet_lake_basenames(station) == {BASE}


def test_empty_lake_membership_rejects_metadata_only_history(tmp_path: Path) -> None:
    metadata = tmp_path / "task_2_metadata_calibration.csv"
    pd.DataFrame(
        [calibration_row(BASE, "2026-01-01_01.00.00", 1.0)]
    ).to_csv(metadata, index=False)

    with pytest.raises(ValueError, match="No lake-backed Task 2 calibration rows"):
        select_metadata(
            metadata,
            datetime(2026, 1, 1),
            datetime(2026, 1, 2),
            allowed_basenames=set(),
        )
