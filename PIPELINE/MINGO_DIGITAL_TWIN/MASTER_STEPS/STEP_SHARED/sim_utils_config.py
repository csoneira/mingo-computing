"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_SHARED/sim_utils_config.py
Purpose: Configuration and station CSV helpers for simulation steps.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_SHARED/sim_utils_config.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple
import time

import pandas as pd
import yaml


def load_global_home_path() -> str:
    """Load home_path from the repository-wide CONTEXTUAL/CONFIG/config_paths.yaml."""
    config_file = Path(__file__).resolve().parents[4] / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml"
    if not config_file.exists():
        return str(Path.home())
    with config_file.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    home_path = config.get("home_path")
    if not home_path:
        return str(Path.home())
    return str(Path(home_path).expanduser())


def load_step_configs(
    physics_path: Path,
    runtime_path: Optional[Path] = None,
) -> Tuple[Dict, Dict, Dict, Path]:
    if not physics_path.exists():
        raise FileNotFoundError(f"Physics config not found: {physics_path}")
    if runtime_path is None:
        if physics_path.name.endswith("_physics.yaml"):
            runtime_path = physics_path.with_name(
                physics_path.name.replace("_physics.yaml", "_runtime.yaml")
            )
        else:
            raise ValueError(
                "Runtime config path not provided and cannot infer from physics config name."
            )
    if not runtime_path.exists():
        raise FileNotFoundError(f"Runtime config not found: {runtime_path}")

    with physics_path.open("r") as handle:
        physics_cfg = yaml.safe_load(handle) or {}
    with runtime_path.open("r") as handle:
        runtime_cfg = yaml.safe_load(handle) or {}

    if not isinstance(physics_cfg, dict) or not isinstance(runtime_cfg, dict):
        raise ValueError("Both physics and runtime configs must be YAML mappings.")

    overlap = set(physics_cfg.keys()) & set(runtime_cfg.keys())
    if overlap:
        overlap_list = ", ".join(sorted(overlap))
        raise ValueError(
            f"Config keys overlap between physics and runtime configs: {overlap_list}"
        )

    merged_cfg = dict(runtime_cfg)
    merged_cfg.update(physics_cfg)
    return physics_cfg, runtime_cfg, merged_cfg, runtime_path


def list_station_config_files(root_dir: Path) -> Dict[int, Path]:
    station_files: Dict[int, Path] = {}
    for station_dir in sorted(root_dir.glob("STATION_*")):
        if not station_dir.is_dir():
            continue
        station_id = int(station_dir.name.split("_")[-1])
        csv_files = list(station_dir.glob("input_file_mingo*.csv"))
        if not csv_files:
            continue
        station_files[station_id] = csv_files[0]
    return station_files


def read_station_config(csv_path: Path) -> pd.DataFrame:
    # Be tolerant of transient empty/truncated files (caused by concurrent updates).
    attempts = 3
    for attempt in range(attempts):
        try:
            df = pd.read_csv(csv_path, header=1, decimal=",", dtype=str)
            break
        except pd.errors.EmptyDataError:
            if attempt < attempts - 1:
                time.sleep(0.25)
                continue
            raise
    df.columns = [col.strip() for col in df.columns]
    for col in ["station", "conf", "P1", "P2", "P3", "P4"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df
