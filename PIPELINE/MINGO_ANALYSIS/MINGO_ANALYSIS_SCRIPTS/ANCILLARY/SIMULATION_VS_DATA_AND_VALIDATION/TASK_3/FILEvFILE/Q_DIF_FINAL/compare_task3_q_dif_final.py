#!/usr/bin/env python3
"""Compare Task-3 per-plane Q_dif distributions for one matched simulation/data pair."""

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
DEFAULT_CONFIG_PATH = THIS_DIR / "q_dif_final_config.json"
METRIC_COLUMNS = [f"P{idx}_Q_dif_final" for idx in range(1, 5)]


def main() -> None:
    args = parse_metric_args(
        DEFAULT_CONFIG_PATH,
        "Match one Task-3 study file to one MINGO00 reference and compare Q_dif histograms.",
    )
    run_metric_histogram_comparison(
        args=args,
        metric_columns=METRIC_COLUMNS,
        metric_title="Task-3 Q_dif final distributions",
        summary_column_name="q_dif_column",
        summary_csv_name="q_dif_final_summary.csv",
        plot_name="task3_q_dif_final_histograms.png",
        value_unit="a.u.",
    )


if __name__ == "__main__":
    main()
