#!/usr/bin/env python3
"""Compare Task-4 fitted yp distributions for one matched simulation/data pair."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[6]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.ANCILLARY.SIMULATION_VS_DATA_AND_VALIDATION.common.task4_scalar_metric_histograms import (
    parse_metric_args,
    run_metric_histogram_comparison,
)


THIS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = THIS_DIR / "yp_config.json"


def main() -> None:
    args = parse_metric_args(DEFAULT_CONFIG_PATH, "Match one Task-4 study file to one MINGO00 reference and compare yp histograms.")
    run_metric_histogram_comparison(
        args=args,
        metric_column="yp",
        metric_title="Task-4 yp distributions",
        summary_csv_name="task4_yp_summary.csv",
        plot_name="task4_yp_histograms.png",
        value_unit="a.u.",
    )


if __name__ == "__main__":
    main()
