#!/usr/bin/env python3
"""Compare Task-4 fitted x vs y distributions for one matched simulation/data pair."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[6]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.ANCILLARY.SIMULATION_VS_DATA_AND_VALIDATION.common.task4_scalar_metric_scatter import (
    parse_scatter_args,
    run_metric_scatter_comparison,
)


THIS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = THIS_DIR / "X_VS_Y_config.json"


def main() -> None:
    args = parse_scatter_args(
        DEFAULT_CONFIG_PATH,
        "Match one Task-4 study file to one MINGO00 reference and compare x vs y scatters.",
    )
    run_metric_scatter_comparison(
        args=args,
        x_column="x",
        y_column="y",
        plot_title="Task-4 x vs y distributions",
        summary_csv_name="task4_x_vs_y_summary.csv",
        plot_name="task4_x_vs_y_scatter.png",
        x_unit="mm",
        y_unit="mm",
    )


if __name__ == "__main__":
    main()
