#!/usr/bin/env python3
"""Standalone Task 1 FINAL plotter.

Usage:
    python final_plots_task_1.py /path/to/cleaned_*.parquet

The parquet path is the only runtime argument. This script is outside the
Stage-1 processing flow: it reads an already-produced Task 1 parquet and
creates the configured FINAL PNG/PDF products.
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

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.final_plotting import run_final_plotter


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Task 1 FINAL plots from its derived parquet.")
    parser.add_argument("parquet_path", help="Path to the Task 1 derived parquet")
    args = parser.parse_args()
    config_path = (
        SCRIPTS_ROOT
        / "CONFIG_FILES/STAGE_1/EVENT_DATA/STEP_1/TASK_1"
        / "config_final_plots_task_1.yaml"
    )
    run_final_plotter(
        task=1,
        expected_prefixes=('cleaned_',),
        parquet_path=args.parquet_path,
        config_path=config_path,
    )


if __name__ == "__main__":
    main()
