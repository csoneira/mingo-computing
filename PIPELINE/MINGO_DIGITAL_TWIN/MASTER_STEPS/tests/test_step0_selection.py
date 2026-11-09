#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/tests/test_step0_selection.py
Purpose: Regression tests for STEP_0 station/date-range geometry selection.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/tests/test_step0_selection.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.selection_config import extract_selection


def _load_step0_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "STEP_0" / "step_0_setup_to_blank.py"
    spec = importlib.util.spec_from_file_location("step0_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_station_config(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "ignored,ignored,ignored,ignored,ignored,ignored,ignored,ignored,"
        "ignored,ignored,ignored,ignored\n"
    )
    columns = "station,conf,start,end,P1,P2,P3,P4,C1,C2,C3,C4\n"
    payload = []
    for row in rows:
        payload.append(
            ",".join(
                str(row[col])
                for col in ("station", "conf", "start", "end", "P1", "P2", "P3", "P4", "C1", "C2", "C3", "C4")
            )
        )
    path.write_text(header + columns + "\n".join(payload) + "\n", encoding="utf-8")


def test_step0_geometry_adaptation_uses_station_specific_date_ranges(tmp_path: Path) -> None:
    step0 = _load_step0_module()
    station_root = tmp_path / "ONLINE_RUN_DICTIONARY"
    _write_station_config(
        station_root / "STATION_1" / "input_file_mingo01.csv",
        [
            {
                "station": 1,
                "conf": 12,
                "start": "2024-04-24",
                "end": "2024-09-16",
                "P1": 0,
                "P2": 100,
                "P3": 200,
                "P4": 400,
                "C1": 12,
                "C2": 23,
                "C3": 34,
                "C4": 13,
            },
            {
                "station": 1,
                "conf": 13,
                "start": "2024-09-16",
                "end": "2024-11-01",
                "P1": 0,
                "P2": 65,
                "P3": 130,
                "P4": 195,
                "C1": 12,
                "C2": 23,
                "C3": 34,
                "C4": 13,
            },
            {
                "station": 1,
                "conf": 14,
                "start": "2024-11-01",
                "end": "2025-02-17",
                "P1": 0,
                "P2": 145,
                "P3": 290,
                "P4": 435,
                "C1": 12,
                "C2": 23,
                "C3": 34,
                "C4": 13,
            },
        ],
    )

    station_files = step0.list_station_config_files(station_root)
    selection = extract_selection(
        {
            "selection": {
                "stations": [0, 1],
                "date_ranges": [
                    {
                        "stations": [1],
                        "start": "2024-09-17",
                        "end": "2024-10-05",
                    }
                ],
            }
        }
    )

    selected_station_ids = step0._selected_station_ids_for_z_adaptation(station_files, selection)
    geometry_rows = step0._collect_geometry_trigger_rows(
        station_files,
        selected_station_ids=selected_station_ids,
        selection=selection,
    )

    assert selected_station_ids == [1]
    assert geometry_rows.to_dict("records") == [
        {"P1": 0, "P2": 65, "P3": 130, "P4": 195, "C1": "12", "C2": "23", "C3": "34", "C4": "13"}
    ]
