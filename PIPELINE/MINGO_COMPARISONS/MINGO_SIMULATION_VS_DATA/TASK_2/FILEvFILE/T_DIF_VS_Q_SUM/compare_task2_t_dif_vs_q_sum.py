#!/usr/bin/env python3
"""Compare Task-2 per-strip T_dif vs Q_sum scatter distributions for one matched pair."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[6]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.ANCILLARY.SIMULATION_VS_DATA_AND_VALIDATION.common.task2_strip_scatter_tdif_vs_qsum import (
    parse_scatter_args,
    run_tdif_vs_qsum_comparison,
)


THIS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = THIS_DIR / "T_dif_vs_q_sum_config.json"


def main() -> None:
    args = parse_scatter_args(
        DEFAULT_CONFIG_PATH,
        "Match one Task-2 study file to one MINGO00 reference and compare per-strip T_dif vs Q_sum scatters.",
    )
    run_tdif_vs_qsum_comparison(args)


if __name__ == "__main__":
    main()
