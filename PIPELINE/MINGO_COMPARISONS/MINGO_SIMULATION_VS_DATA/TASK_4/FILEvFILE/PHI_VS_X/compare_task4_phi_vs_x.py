#!/usr/bin/env python3
"""Compare Task-4 fitted phi vs x distributions for one matched simulation/data pair."""

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
DEFAULT_CONFIG_PATH = THIS_DIR / "PHI_VS_X_config.json"


def main() -> None:
    args = parse_scatter_args(
        DEFAULT_CONFIG_PATH,
        "Match one Task-4 study file to one MINGO00 reference and compare phi vs x scatters.",
    )
    run_metric_scatter_comparison(
        args=args,
        x_column="phi",
        y_column="x",
        plot_title="Task-4 phi vs x distributions",
        summary_csv_name="task4_phi_vs_x_summary.csv",
        plot_name="task4_phi_vs_x_scatter.png",
        x_unit="rad",
        y_unit="mm",
    )


if __name__ == "__main__":
    main()
