#!/usr/bin/env python3
"""Refresh the rolling MINGO01 plots served by the analysis Telegram bot."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
ANALYSIS_ROOT = SCRIPT_DIR.parents[2]
BASE_DIR = ANALYSIS_ROOT.parent
STATION_ROOT = ANALYSIS_ROOT / "MINGO_ANALYSIS_STATIONS" / "MINGO01"

sys.path.insert(0, str(SCRIPT_DIR))

from calibration_context import generate_calibration_context  # noqa: E402
from environment_context import generate_environment_context  # noqa: E402
from test_1_plot_calibration_offsets import (  # noqa: E402
    select_metadata,
    valid_parquet_lake_basenames,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=float, default=7.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.days <= 0:
        parser.error("--days must be greater than zero")

    end = datetime.now()
    start = end - timedelta(days=args.days)
    period = f"{start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M}"
    title = f"MINGO01 | rolling {args.days:g}-day view | {period}"

    metadata_path = (
        STATION_ROOT / "STAGE_1" / "EVENT_DATA" / "STEP_1" / "TASK_2"
        / "METADATA" / "task_2_metadata_calibration.csv"
    )
    selected = select_metadata(
        metadata_path,
        start,
        end,
        allowed_basenames=valid_parquet_lake_basenames(STATION_ROOT),
    )
    generate_calibration_context(
        STATION_ROOT,
        start,
        end,
        args.output_dir / "calibration",
        title,
        set(selected["filename_base"].astype(str)),
        context="full",
    )
    generate_environment_context(
        STATION_ROOT,
        start,
        end,
        args.output_dir / "environment",
        title,
        context_fraction=0.0,
    )
    print(f"Refreshed MINGO01 Telegram plots for {period} in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
