#!/usr/bin/env python3

"""Utility helpers for recording execution timing information to a shared CSV log."""

from __future__ import annotations

import csv
import datetime as _dt
import os
import pathlib
import sys
import time
from contextlib import contextmanager
from typing import Iterator, Optional, Union

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root

__all__ = [
    "log_execution",
    "LOG_PATH",
    "start_timer",
    "set_station",
    "write_log_entry",
]

LOG_PATH = get_repo_root() / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / "python_execution_log.csv"
_CSV_HEADER = ("script_name", "station", "date_of_execution", "duration_seconds")

_timer_started = False
_timer_start_value: Optional[float] = None
_script_identifier: Optional[str] = None
_station_value: Optional[str] = None
_atexit_registered = False
_LOGGING_ENABLED = False


def _normalise_script_name(script: Union[str, os.PathLike[str]]) -> str:
    """Return a readable script identifier for logging."""
    script_path = pathlib.Path(script)
    try:
        # Resolve relative paths where possible for consistent reporting.
        script_path = script_path.resolve()
    except FileNotFoundError:
        pass
    return str(script_path)


# def _ensure_log_header(log_path: pathlib.Path) -> None:
#     if not log_path.exists():
#         log_path.parent.mkdir(parents=True, exist_ok=True)
#         with log_path.open("w", newline="") as handle:
#             writer = csv.writer(handle)
#             writer.writerow(_CSV_HEADER)


# @contextmanager
# def log_execution(script: Union[str, os.PathLike[str]], station: Optional[Union[str, int]] = None) -> Iterator[None]:
#     """
#     Context manager that records the execution duration for a script.

#     Parameters
#     ----------
#     script:
#         Path or name of the script being executed. If ``__file__`` is provided it
#         will be resolved to an absolute path where possible.
#     station:
#         Optional station identifier. When ``None`` the column is left blank.
#     """

#     start = time.perf_counter()
#     try:
#         yield
#     finally:
#         duration = time.perf_counter() - start
#         when = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         station_value = "" if station is None else str(station)
#         record = (_normalise_script_name(script), station_value, when, f"{duration:.3f}")

#         try:
#             _ensure_log_header(LOG_PATH)
#             with LOG_PATH.open("a", newline="") as handle:
#                 writer = csv.writer(handle)
#                 writer.writerow(record)
#         except Exception as exc:  # pragma: no cover - best-effort logging
#             print(f"[execution_logger] Failed to append log entry: {exc}", file=sys.stderr)


def start_timer(script: Union[str, os.PathLike[str]]) -> None:
    """Begin tracking execution time for the current process."""
    if not _LOGGING_ENABLED:
        return
    global _timer_started, _timer_start_value, _script_identifier, _atexit_registered
    _script_identifier = _normalise_script_name(script)
    _timer_start_value = time.perf_counter()
    _timer_started = True
    if not _atexit_registered:
        import atexit

        # atexit.register(write_log_entry)
        _atexit_registered = True


def set_station(station: Optional[Union[str, int]]) -> None:
    """Store the station identifier for the pending log entry."""
    if not _LOGGING_ENABLED:
        return
    global _station_value
    _station_value = None if station is None else str(station)


# def write_log_entry() -> None:
#     """Write a log entry using the last values provided to `start_timer` and `set_station`."""
#     global _timer_started, _timer_start_value, _script_identifier

#     if not _timer_started or _timer_start_value is None or _script_identifier is None:
#         return

#     duration = time.perf_counter() - _timer_start_value
#     when = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     station_value = "" if _station_value is None else _station_value
#     record = (_script_identifier, station_value, when, f"{duration:.3f}")

#     try:
#         _ensure_log_header(LOG_PATH)
#         with LOG_PATH.open("a", newline="") as handle:
#             writer = csv.writer(handle)
#             writer.writerow(record)
#     except Exception as exc:  # pragma: no cover - best-effort logging
#         print(f"[execution_logger] Failed to append log entry: {exc}", file=sys.stderr)
#     finally:
#         _timer_started = False
#         _timer_start_value = None
#         _script_identifier = None
