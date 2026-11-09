#!/usr/bin/env python3
"""Standalone FINAL plots for self-trigger Task 2.

Usage: python final_plots_task_2_selftrigger.py /path/to/selftrigger_calibrated_*.parquet
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

CURRENT = Path(__file__).resolve()
SCRIPTS_ROOT = next(parent for parent in CURRENT.parents if parent.name == "MINGO_ANALYSIS_SCRIPTS")
REPO_ROOT = SCRIPTS_ROOT.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.final_plotting import run_final_plotter


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Task 2 self-trigger FINAL plots from its calibrated parquet."
    )
    parser.add_argument("parquet_path", help="Path to a selftrigger_calibrated_*.parquet file")
    args = parser.parse_args()
    config_path = (
        SCRIPTS_ROOT
        / "SUPPORT/CONFIG_FILES/STAGE_1/EVENT_DATA/STEP_1/TASK_2_SELFTRIGGER"
        / "config_final_plots_task_2_selftrigger.yaml"
    )
    run_final_plotter(
        task=2,
        expected_prefixes=("selftrigger_calibrated_",),
        parquet_path=args.parquet_path,
        config_path=config_path,
    )


if __name__ == "__main__":
    main()
