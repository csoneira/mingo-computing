#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from simple_common import DEFAULT_CONFIG_PATH
from step_0_load_inputs import run_real_selection, run_training_selection
from step_1_build_lut import run as run_step_1
from step_2_apply_lut import run as run_step_2
from step_3_rate_to_flux import run as run_step_3


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the definitive LUT, then optionally run real-data inference.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to config JSON file.")
    parser.add_argument("--strict", action="store_true", help="Fail if the real-data/inference branch fails.")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    training_path = run_training_selection(config_path)
    lut_path = run_step_1(config_path)
    print(f"LUT training selection created: {training_path}")
    print(f"LUT created successfully before real-data processing: {lut_path}")

    try:
        run_real_selection(config_path)
        run_step_2(config_path)
        run_step_3(config_path)
    except Exception as exc:
        print("WARNING: real-data selection/inference branch failed.")
        print(f"WARNING: {type(exc).__name__}: {exc}")
        print(f"WARNING: LUT was already created successfully and remains available at: {lut_path}")
        if args.strict:
            raise


if __name__ == "__main__":
    main()
