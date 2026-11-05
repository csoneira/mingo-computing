"""Lifecycle helpers for active QA reprocessing requests."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

import pandas as pd


QA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = QA_ROOT.parents[4]
ACTIVE_REGISTRY = (
    REPO_ROOT / "CONTEXTUAL" / "OPERATIONS" / "OPERATIONS_RUNTIME" / "STATE"
    / "REPROCESS_BASENAMES" / "active_reprocessing.csv"
)
REGISTRY_COLUMNS = [
    "station", "basename", "start_task", "requested_at", "stage0_fallback"
]


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def reconcile_active_requests(
    registry_path: Path = ACTIVE_REGISTRY,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[int, int]:
    """Retire a request after its selected starting task executes again."""
    if not registry_path.is_file():
        return 0, 0
    active = pd.read_csv(registry_path, dtype=str).fillna("")
    kept: list[dict[str, str]] = []
    completed = 0
    cache: dict[tuple[str, int], pd.DataFrame] = {}
    for row in active.to_dict("records"):
        station = str(row.get("station", "")).strip()
        basename = str(row.get("basename", "")).strip()
        try:
            task = int(str(row.get("start_task", "")))
            requested_at = pd.Timestamp(str(row.get("requested_at", "")))
        except (TypeError, ValueError):
            kept.append(row)
            continue
        key = (station, task)
        if key not in cache:
            path = (
                repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / station
                / "STAGE_1" / "EVENT_DATA" / "STEP_1" / f"TASK_{task}"
                / "METADATA" / f"task_{task}_metadata_execution.csv"
            )
            if path.is_file():
                header = pd.read_csv(path, nrows=0).columns.tolist()
                if {"filename_base", "execution_timestamp"} <= set(header):
                    cache[key] = pd.read_csv(
                        path,
                        usecols=["filename_base", "execution_timestamp"],
                        low_memory=False,
                    )
                else:
                    cache[key] = pd.DataFrame()
            else:
                cache[key] = pd.DataFrame()
        executions = cache[key]
        if executions.empty:
            kept.append(row)
            continue
        matching = executions[
            executions["filename_base"].astype(str).str.strip().eq(basename)
        ]
        execution_times = pd.to_datetime(
            matching["execution_timestamp"],
            format="%Y-%m-%d_%H.%M.%S",
            errors="coerce",
        )
        if bool((execution_times > requested_at).any()):
            completed += 1
        else:
            kept.append(row)
    kept_frame = pd.DataFrame(kept, columns=REGISTRY_COLUMNS)
    _atomic_write(registry_path, kept_frame.to_csv(index=False))
    return completed, len(kept)
