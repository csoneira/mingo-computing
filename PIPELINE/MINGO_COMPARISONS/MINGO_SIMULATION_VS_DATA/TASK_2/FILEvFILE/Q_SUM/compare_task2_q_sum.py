#!/usr/bin/env python3
"""Compare Task-2 per-strip Q_sum distributions for one matched simulation/data pair."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[6]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.ANCILLARY.SIMULATION_VS_DATA_AND_VALIDATION.common.task2_strip_metric_histograms import (
    parse_metric_args,
    run_metric_histogram_comparison,
)


THIS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = THIS_DIR / "Q_sum_config.json"
METRIC_COLUMNS = [f"Q{plane}_Q_sum_{strip}" for plane in range(1, 5) for strip in range(1, 5)]


def main() -> None:
    args = parse_metric_args(
        DEFAULT_CONFIG_PATH,
        "Match one Task-2 study file to one MINGO00 reference and compare per-strip Q_sum histograms.",
    )
    run_metric_histogram_comparison(
        args=args,
        metric_columns=METRIC_COLUMNS,
        metric_title="Task-2 Q_sum distributions",
        metric_group_name="Q_sum",
        summary_csv_name="task2_q_sum_summary.csv",
        plot_name="task2_q_sum_histograms.png",
        value_unit="a.u.",
    )


if __name__ == "__main__":
    main()
