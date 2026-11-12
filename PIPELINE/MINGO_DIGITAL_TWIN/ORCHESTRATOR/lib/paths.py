#!/usr/bin/env python3
"""Central path resolution for the MINGO digital-twin orchestrator."""

from __future__ import annotations

from pathlib import Path
import sys

_REPOSITORY_IMPORT_ROOT = Path(__file__).resolve().parents[4]
if str(_REPOSITORY_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_IMPORT_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import (
    get_repo_root,
)


def digital_twin_root() -> Path:
    return get_repo_root() / "PIPELINE" / "MINGO_DIGITAL_TWIN"


def repository_root() -> Path:
    return get_repo_root()


def orchestrator_root() -> Path:
    return digital_twin_root() / "ORCHESTRATOR"


def intersteps_dir() -> Path:
    return digital_twin_root() / "SIMULATION_OUTPUTS" / "INTERSTEPS"


def simulated_data_dir() -> Path:
    return digital_twin_root() / "SIMULATION_OUTPUTS" / "SIMULATED_DATA"


def operations_runtime_dir() -> Path:
    return repository_root() / "CONTEXTUAL" / "OPERATIONS" / "OPERATIONS_RUNTIME"


def orchestrator_runtime_dir() -> Path:
    return operations_runtime_dir() / "SIMULATION" / "ORCHESTRATOR"


def maintenance_dir() -> Path:
    return orchestrator_root() / "maintenance"
