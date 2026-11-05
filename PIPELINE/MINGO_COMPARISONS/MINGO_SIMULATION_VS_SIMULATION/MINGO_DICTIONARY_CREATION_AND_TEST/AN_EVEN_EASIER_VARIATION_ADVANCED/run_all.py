#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from common import DEFAULT_CONFIG_PATH, load_config
from step_0_build_efficiency_fits import run as run_step_0
from step_1_collect_real_data import run as run_step_1
from step_2_apply_simplified_scale import run as run_step_2
from step_3_build_rate_to_flux_calibration import run as run_step_3


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the advanced simplified real-data scale workflow.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to config JSON file.")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    load_config(config_path)

    run_step_0(config_path)
    run_step_1(config_path)
    run_step_2(config_path)
    run_step_3(config_path)


if __name__ == "__main__":
    main()
