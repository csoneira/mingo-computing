#!/usr/bin/env python3
"""Standalone FINAL comparison plots for Task 1 self-trigger output.

Usage:
    python final_plots_task_1_selftrigger.py /path/to/selftrigger_cleaned_*.parquet

The supplied self-trigger parquet is paired with its matching Task 0
coincidence parquet for the configured charge and time spectrum comparisons.
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
        description="Generate Task 1 self-trigger FINAL spectra comparisons from its derived parquet."
    )
    parser.add_argument("parquet_path", help="Path to the selftrigger_cleaned_*.parquet file")
    args = parser.parse_args()
    config_path = (
        SCRIPTS_ROOT
        / "SUPPORT/CONFIG_FILES/STAGE_1/EVENT_DATA/STEP_1/TASK_1_SELFTRIGGER"
        / "config_final_plots_task_1_selftrigger.yaml"
    )
    run_final_plotter(
        task=1,
        expected_prefixes=("selftrigger_cleaned_",),
        parquet_path=args.parquet_path,
        config_path=config_path,
    )


if __name__ == "__main__":
    main()
