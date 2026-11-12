#!/usr/bin/env python3

"""Persist snapshots of the main config files when they change."""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

import yaml

_REPO_IMPORT_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_IMPORT_ROOT))
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root
REPO_ROOT = get_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.execution_logger import start_timer
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_master_config_root, get_repo_root

start_timer(__file__)

REPO_ROOT = get_repo_root()
CONFIG_ROOT = get_master_config_root()
SNAPSHOT_ROOT = REPO_ROOT / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME" / "CONFIG_FILES"

YAML_CONFIG_TARGETS: Sequence[Tuple[Path, Path, str, str]] = (
    (
        REPO_ROOT / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml",
        SNAPSHOT_ROOT / "GLOBAL_PATHS",
        "config_paths.json",
        "global paths config",
    ),
    (
        CONFIG_ROOT / "STAGE_0" / "NEW_FILES" / "config_new_files.yaml",
        SNAPSHOT_ROOT / "STAGE_0_NEW_FILES",
        "config_new_files.json",
        "stage 0 new files config",
    ),
    (
        CONFIG_ROOT / "STAGE_0" / "REPROCESSING" / "config_reprocessing.yaml",
        SNAPSHOT_ROOT / "STAGE_0_REPROCESSING",
        "config_reprocessing.json",
        "stage 0 reprocessing config",
    ),
    (
        CONFIG_ROOT / "STAGE_1" / "COPERNICUS" / "config_copernicus.yaml",
        SNAPSHOT_ROOT / "STAGE_1_COPERNICUS",
        "config_copernicus.json",
        "stage 1 copernicus config",
    ),
    (
        CONFIG_ROOT / "STAGE_1" / "LOG_DATA" / "config_lab_logs.yaml",
        SNAPSHOT_ROOT / "STAGE_1_LOG_DATA",
        "config_lab_logs.json",
        "stage 1 log data config",
    ),
    (
        CONFIG_ROOT / "STAGE_1" / "EVENT_DATA" / "STEP_1" / "config_step_1.yaml",
        SNAPSHOT_ROOT / "STAGE_1_EVENT_DATA_STEP_1",
        "config_step_1.json",
        "stage 1 step 1 runtime config",
    ),
    (
        CONFIG_ROOT / "STAGE_1" / "EVENT_DATA" / "STEP_1" / "TASK_1" / "config_task_1.yaml",
        SNAPSHOT_ROOT / "STAGE_1_EVENT_DATA_STEP_1_TASK_1",
        "config_task_1.json",
        "stage 1 step 1 task 1 config",
    ),
    (
        CONFIG_ROOT / "STAGE_1" / "EVENT_DATA" / "STEP_1" / "TASK_2" / "config_task_2.yaml",
        SNAPSHOT_ROOT / "STAGE_1_EVENT_DATA_STEP_1_TASK_2",
        "config_task_2.json",
        "stage 1 step 1 task 2 config",
    ),
    (
        CONFIG_ROOT / "STAGE_1" / "EVENT_DATA" / "STEP_1" / "TASK_3" / "config_task_3.yaml",
        SNAPSHOT_ROOT / "STAGE_1_EVENT_DATA_STEP_1_TASK_3",
        "config_task_3.json",
        "stage 1 step 1 task 3 config",
    ),
    (
        CONFIG_ROOT / "STAGE_1" / "EVENT_DATA" / "STEP_1" / "TASK_4" / "config_task_4.yaml",
        SNAPSHOT_ROOT / "STAGE_1_EVENT_DATA_STEP_1_TASK_4",
        "config_task_4.json",
        "stage 1 step 1 task 4 config",
    ),
    (
        CONFIG_ROOT / "STAGE_1" / "EVENT_DATA" / "STEP_1" / "TASK_5" / "config_task_5.yaml",
        SNAPSHOT_ROOT / "STAGE_1_EVENT_DATA_STEP_1_TASK_5",
        "config_task_5.json",
        "stage 1 step 1 task 5 config",
    ),
    (
        CONFIG_ROOT / "STAGE_2" / "EVENT_DATA" / "STEP_1_ACCUMULATION" / "config_step_1_accumulation.yaml",
        SNAPSHOT_ROOT / "STAGE_2_EVENT_DATA_STEP_1_ACCUMULATION",
        "config_step_1_accumulation.json",
        "stage 2 event accumulation config",
    ),
    (
        CONFIG_ROOT / "STAGE_2" / "EVENT_DATA" / "STEP_2_DAILY_EVENT_DATA" / "config_step_2_daily_event_data.yaml",
        SNAPSHOT_ROOT / "STAGE_2_EVENT_DATA_STEP_2_DAILY_EVENT_DATA",
        "config_step_2_daily_event_data.json",
        "stage 2 daily event data config",
    ),
)

CSV_CONFIG_TARGETS: Sequence[Tuple[Path, Path, str, str]] = tuple(
    (
        CONFIG_ROOT / "STAGE_1" / "EVENT_DATA" / "STEP_1" / f"TASK_{task}" / f"config_parameters_task_{task}.csv",
        SNAPSHOT_ROOT / f"STAGE_1_EVENT_DATA_STEP_1_TASK_{task}",
        f"config_parameters_task_{task}.json",
        f"stage 1 step 1 task {task} parameters",
    )
    for task in range(6)
)


def extract_json_payload(snapshot_path: Path) -> str:
    """Return the JSON payload stored in *snapshot_path* (skip header)."""
    lines = snapshot_path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines) and lines[index].lstrip().startswith("#"):
        index += 1
    return "\n".join(lines[index:]).strip()


def latest_snapshot_payload(directory: Path, name_suffix: str) -> Optional[str]:
    """Return the JSON payload from the most recent snapshot with the given suffix, if any."""
    snapshots = sorted(directory.glob(f"*_{name_suffix}"))
    if not snapshots:
        return None
    return extract_json_payload(snapshots[-1])


def load_config_as_json(config_path: Path) -> str:
    """Load YAML config and return a stable JSON string representation."""
    try:
        config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Config file not found: {config_path}") from exc

    return json.dumps(config_data, indent=2, sort_keys=True, default=str)


def load_csv_as_json(config_path: Path) -> str:
    """Load CSV config and return a stable JSON string representation."""
    try:
        with config_path.open(mode="r", encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            rows = list(reader)
    except FileNotFoundError as exc:
        raise SystemExit(f"Config file not found: {config_path}") from exc

    return json.dumps(rows, indent=2, sort_keys=True)


def snapshot_if_changed(
    config_path: Path,
    snapshot_dir: Path,
    payload_loader: Callable[[Path], str],
    name_suffix: str,
    label: str,
) -> bool:
    """Create a snapshot when payload differs from the latest stored version."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    current_payload = payload_loader(config_path)
    previous_payload = latest_snapshot_payload(snapshot_dir, name_suffix)

    if previous_payload is not None and previous_payload == current_payload:
        return False

    timestamp = datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
    snapshot_path = snapshot_dir / f"{timestamp}_{name_suffix}"
    header = f"# Snapshot generated on {timestamp}\n"
    snapshot_path.write_text(f"{header}{current_payload}\n", encoding="utf-8")

    print(f"Saved new {label} snapshot: {snapshot_path}")
    return True


def main() -> int:
    for config_path, snapshot_dir, suffix, label in YAML_CONFIG_TARGETS:
        snapshot_if_changed(
            config_path,
            snapshot_dir,
            load_config_as_json,
            suffix,
            label,
        )

    for config_path, snapshot_dir, suffix, label in CSV_CONFIG_TARGETS:
        snapshot_if_changed(
            config_path,
            snapshot_dir,
            load_csv_as_json,
            suffix,
            label,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
