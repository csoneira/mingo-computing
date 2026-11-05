#!/usr/bin/env python3
"""Central path resolution for the MINGO digital-twin orchestrator."""

from __future__ import annotations

from pathlib import Path


def digital_twin_root() -> Path:
    return Path(__file__).resolve().parents[2]


def repository_root() -> Path:
    return digital_twin_root().parent


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
