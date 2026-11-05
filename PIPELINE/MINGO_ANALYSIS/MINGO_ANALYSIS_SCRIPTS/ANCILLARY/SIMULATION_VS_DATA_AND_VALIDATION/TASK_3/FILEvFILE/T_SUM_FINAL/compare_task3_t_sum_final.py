#!/usr/bin/env python3
"""Compare Task-3 per-plane T_sum distributions for one matched simulation/data pair."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[6]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.ANCILLARY.SIMULATION_VS_DATA_AND_VALIDATION.common.task3_plane_metric_histograms import (
    parse_metric_args,
    run_metric_histogram_comparison,
)


THIS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = THIS_DIR / "t_sum_final_config.json"
METRIC_COLUMNS = [f"P{idx}_T_sum_final" for idx in range(1, 5)]


def main() -> None:
    args = parse_metric_args(
        DEFAULT_CONFIG_PATH,
        "Match one Task-3 study file to one MINGO00 reference and compare T_sum histograms.",
    )
    run_metric_histogram_comparison(
        args=args,
        metric_columns=METRIC_COLUMNS,
        metric_title="Task-3 T_sum final distributions",
        summary_column_name="t_sum_column",
        summary_csv_name="t_sum_final_summary.csv",
        plot_name="task3_t_sum_final_histograms.png",
        value_unit="ns",
    )


if __name__ == "__main__":
    main()
