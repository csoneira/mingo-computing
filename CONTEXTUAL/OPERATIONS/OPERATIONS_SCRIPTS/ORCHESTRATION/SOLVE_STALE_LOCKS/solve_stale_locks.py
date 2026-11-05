#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/ORCHESTRATION/SOLVE_STALE_LOCKS/solve_stale_locks.py
Purpose: Check for stale STEP_1 and unpacker lock files.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/ORCHESTRATION/SOLVE_STALE_LOCKS/solve_stale_locks.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable


REPO_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()),
    None,
)
if REPO_ROOT is None:
    raise RuntimeError(f"Could not locate repository root from {__file__}")
DEFAULT_LOCK_DIR = REPO_ROOT / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS"
UNPACK_LOCK_NAME = ".unpack_shared.lock"
DEFAULT_LOG_FILE = (
    REPO_ROOT / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS/solve_stale_locks.log"
)
# Task-level locks should clear faster so the pipeline does not get stuck if a task died
# before releasing its lock.
TASK_LOCK_MAX_AGE = dt.timedelta(minutes=5)
RUN_STEP_CONTINUOUS_LOCK_DIR = Path("/tmp/mingo_digital_twin_run_step_continuous.lock")
RUN_STEP_CONTINUOUS_PID_FILE = RUN_STEP_CONTINUOUS_LOCK_DIR / "pid"
RUN_STEP_LOCK_RACE_GRACE = dt.timedelta(minutes=2)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Detect STEP_1 station locks that look stale and delete them so"
            " the cron-driven pipelines can resume."
        )
    )
    parser.add_argument(
        "--lock-dir",
        type=Path,
        default=DEFAULT_LOCK_DIR,
        help=f"Directory that stores lock files (default: {DEFAULT_LOCK_DIR})",
    )
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=15,
        help="Minimum age (in minutes) before a lock can be considered stale",
    )
    parser.add_argument(
        "--force-age-minutes",
        type=int,
        default=15,
        help="Force-delete locks older than this age even if processes appear to be running (default: 15)",
    )
    parser.add_argument(
        "--kill-stale-processes",
        action="store_true",
        help="Kill guide_raw_to_corrected.sh processes older than the force age when removing stale locks",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=DEFAULT_LOG_FILE,
        help=f"Where to append audit messages (default: {DEFAULT_LOG_FILE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be cleaned up but do not remove files",
    )
    return parser.parse_args(argv)


def log_message(message: str, *, logfile: Path) -> None:
    timestamp = _now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    formatted = f"[{timestamp}] {message}"
    print(formatted)
    # cron_run_logged.sh already captures stdout in CRON_LOG_PATH. Avoid a
    # second independently managed log at the legacy default location.
    if os.environ.get("CRON_LOG_PATH"):
        return
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with logfile.open("a", encoding="utf-8") as handle:
        handle.write(formatted + "\n")


def pipeline_info_from_lock_name(path: Path) -> tuple[str, str | None] | None:
    """Return (station, task_id|None) for pipeline locks."""
    match = re.fullmatch(r"step1_station_(\d+)(?:_task_(\d+))?\.lock", path.name)
    if match:
        station = match.group(1)
        task_id = match.group(2)
        return station, task_id
    return None


def station_from_lock_name(path: Path) -> str | None:
    info = pipeline_info_from_lock_name(path)
    return info[0] if info else None


def task_info_from_lock_name(path: Path) -> tuple[str, str] | None:
    """Return (task_base, station) for task lock names task_<task>_station_<station>.lock"""
    match = re.fullmatch(r"task_(.+)_station_(\d+)\.lock", path.name)
    if match:
        return match.group(1), match.group(2)
    return None


def pipeline_running(station: str, task: str | None = None) -> bool:
    pattern = rf"guide_raw_to_corrected.sh.*--station\s+{station}"
    if task:
        pattern = rf"{pattern}.*(--task|-t)\s+{task}"
    try:
        result = subprocess.run(
            ["pgrep", "-af", pattern],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        # Fall back to assuming a process is running to avoid false positives.
        return True
    return result.returncode == 0 and result.stdout.strip() != ""


def task_running(task_base: str, station: str) -> bool:
    pattern = f"{task_base}.py {station}"
    try:
        result = subprocess.run(
            ["pgrep", "-af", pattern],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and result.stdout.strip() != ""


def pipeline_max_age(station: str, task: str | None = None) -> int | None:
    """Return the maximum elapsed time (seconds) among running pipeline procs for the station/task."""
    pattern = rf"guide_raw_to_corrected.sh.*--station\s+{station}"
    if task:
        pattern = rf"{pattern}.*(--task|-t)\s+{task}"
    try:
        ps_out = subprocess.run(
            ["pgrep", "-af", pattern],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if ps_out.returncode != 0 or not ps_out.stdout.strip():
        return None
    max_age = None
    for line in ps_out.stdout.strip().splitlines():
        pid = line.split()[0]
        ps_detail = subprocess.run(
            ["ps", "-o", "etimes=", "-p", pid],
            capture_output=True,
            text=True,
            check=False,
        )
        if ps_detail.returncode != 0 or not ps_detail.stdout.strip():
            continue
        try:
            et = int(ps_detail.stdout.strip())
            max_age = et if max_age is None else max(max_age, et)
        except ValueError:
            continue
    return max_age


def unpacker_running() -> bool:
    pattern = "unpack_reprocessing_files.sh"
    try:
        result = subprocess.run(
            ["pgrep", "-af", pattern],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return True
    return result.returncode == 0 and result.stdout.strip() != ""


def pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def cleanup_dead_run_step_continuous_lock(*, dry_run: bool, logfile: Path) -> bool:
    """Remove stale /tmp lock used by run_step.sh continuous mode."""
    lock_dir = RUN_STEP_CONTINUOUS_LOCK_DIR
    pid_file = RUN_STEP_CONTINUOUS_PID_FILE
    if not lock_dir.exists():
        return False

    try:
        mtime = dt.datetime.fromtimestamp(lock_dir.stat().st_mtime, tz=dt.timezone.utc)
    except FileNotFoundError:
        return False
    age = _now() - mtime

    pid_text = ""
    if pid_file.exists():
        try:
            pid_text = pid_file.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            pid_text = ""
    elif age < RUN_STEP_LOCK_RACE_GRACE:
        # Avoid racing with run_step between mkdir and pid write.
        return False

    reason = "missing_pid"
    if pid_text:
        if pid_text.isdigit():
            pid = int(pid_text)
            if pid_is_alive(pid):
                return False
            reason = f"dead_pid={pid}"
        else:
            if age < RUN_STEP_LOCK_RACE_GRACE:
                return False
            reason = f"invalid_pid={pid_text}"

    action = "DRY-RUN would delete" if dry_run else "Deleting"
    log_message(
        f"{action} stale run_step continuous lock {lock_dir}: {reason}; age {age}",
        logfile=logfile,
    )
    if dry_run:
        return True

    try:
        if pid_file.exists():
            pid_file.unlink()
    except OSError as exc:
        log_message(f"Failed to remove pid file {pid_file}: {exc}", logfile=logfile)
    try:
        lock_dir.rmdir()
    except OSError:
        try:
            shutil.rmtree(lock_dir)
        except OSError as exc:
            log_message(f"Failed to delete stale lock dir {lock_dir}: {exc}", logfile=logfile)
            return False
    return True


def kill_station_processes(station: str, *, min_age: dt.timedelta, logfile: Path, task: str | None = None) -> None:
    """Kill guide_raw_to_corrected.sh processes older than min_age for a station (optionally task-scoped)."""
    pattern = rf"guide_raw_to_corrected.sh.*--station\s+{station}"
    if task:
        pattern = rf"{pattern}.*(--task|-t)\s+{task}"
    try:
        ps_out = subprocess.run(
            ["pgrep", "-af", pattern],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return
    if ps_out.returncode != 0 or not ps_out.stdout.strip():
        return
    lines = ps_out.stdout.strip().splitlines()
    now_ts = dt.datetime.now(dt.timezone.utc).timestamp()
    for line in lines:
        parts = line.strip().split()
        if not parts:
            continue
        pid = parts[0]
        try:
            ps_detail = subprocess.run(
                ["ps", "-o", "pid,etimes,cmd", "-p", pid],
                capture_output=True,
                text=True,
                check=False,
            )
            if ps_detail.returncode != 0:
                continue
            detail_lines = ps_detail.stdout.strip().splitlines()
            if len(detail_lines) < 2:
                continue
            fields = detail_lines[1].split(None, 2)
            if len(fields) < 2:
                continue
            etimes = int(fields[1])
        except Exception:
            continue
        if etimes >= min_age.total_seconds():
            try:
                subprocess.run(["kill", "-9", pid], check=False)
                suffix = f"station {station}"
                if task:
                    suffix += f" task {task}"
                log_message(f"Killed stale guide_raw_to_corrected.sh {suffix} pid {pid} (age {etimes}s)", logfile=logfile)
            except Exception as exc:  # noqa: BLE001
                log_message(f"Failed to kill pid {pid} for station {station}: {exc}", logfile=logfile)


def lock_is_stale(lock_path: Path, *, max_age: dt.timedelta, force_age: dt.timedelta | None = None) -> tuple[bool, str]:
    try:
        mtime = dt.datetime.fromtimestamp(lock_path.stat().st_mtime, tz=dt.timezone.utc)
    except FileNotFoundError:
        return False, "lock disappeared before inspection"

    age = _now() - mtime
    pipeline_info = pipeline_info_from_lock_name(lock_path)
    station = pipeline_info[0] if pipeline_info else None
    task = pipeline_info[1] if pipeline_info else None
    if station and pipeline_running(station, task):
        if force_age is not None:
            proc_age = pipeline_max_age(station, task)
            if proc_age is not None and proc_age >= force_age.total_seconds():
                detail = f"station {station}"
                if task:
                    detail += f" task {task}"
                return True, f"{detail} pipeline age {proc_age}s exceeds forced threshold {force_age}"
        # If process running and not over forced age, use lock age check
        if age < max_age:
            detail = f"station {station}"
            if task:
                detail += f" task {task}"
            return False, f"{detail} pipeline still running; age {age} < threshold"
    else:
        if force_age is not None and age >= force_age:
            return True, f"age {age} exceeds forced threshold {force_age}"
        if age < max_age:
            return False, f"age {age} is newer than threshold"

    if lock_path.name == UNPACK_LOCK_NAME:
        if unpacker_running():
            return False, "unpacker still running"
        details = f"age {age} exceeds threshold; no unpacker process found"
        return True, details

    details = f"age {age} exceeds threshold"
    if station:
        details += f"; no pipeline process found for station {station}"
        if task:
            details += f" task {task}"
    else:
        details += "; station unknown"
    return True, details


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    threshold = dt.timedelta(minutes=args.max_age_minutes)
    force_threshold = dt.timedelta(minutes=args.force_age_minutes) if getattr(args, "force_age_minutes", None) else None
    lock_dir = args.lock_dir
    log_path = args.log_file

    stale_found = cleanup_dead_run_step_continuous_lock(dry_run=args.dry_run, logfile=log_path)

    if not lock_dir.exists():
        if not stale_found:
            log_message(f"Lock directory {lock_dir} does not exist; nothing to do", logfile=log_path)
        return 0

    for lock_file in sorted(lock_dir.glob("*.lock")):
        task_info = task_info_from_lock_name(lock_file)
        if task_info:
            task_base, task_station = task_info
            try:
                age = _now() - dt.datetime.fromtimestamp(lock_file.stat().st_mtime, tz=dt.timezone.utc)
            except FileNotFoundError:
                continue
            if age < TASK_LOCK_MAX_AGE:
                continue
            if task_running(task_base, task_station):
                continue
            stale_found = True
            action = "DRY-RUN would delete" if args.dry_run else "Deleting"
            reason = f"task lock {task_base} station {task_station} idle; age {age} >= {TASK_LOCK_MAX_AGE}"
            log_message(f"{action} stale lock {lock_file}: {reason}", logfile=log_path)
            if args.dry_run:
                continue
            try:
                lock_file.unlink()
            except FileNotFoundError:
                log_message(f"Lock {lock_file} vanished before removal", logfile=log_path)
            except OSError as exc:
                log_message(f"Failed to delete {lock_file}: {exc}", logfile=log_path)
            continue

        is_stale, reason = lock_is_stale(lock_file, max_age=threshold, force_age=force_threshold)
        if not is_stale:
            continue
        stale_found = True
        action = "DRY-RUN would delete" if args.dry_run else "Deleting"
        log_message(f"{action} stale lock {lock_file}: {reason}", logfile=log_path)
        if args.dry_run:
            continue
        pipeline_info = pipeline_info_from_lock_name(lock_file)
        if args.kill_stale_processes and pipeline_info and force_threshold:
            station, task = pipeline_info
            kill_station_processes(station, min_age=force_threshold, logfile=log_path, task=task)
        try:
            lock_file.unlink()
        except FileNotFoundError:
            log_message(f"Lock {lock_file} vanished before removal", logfile=log_path)
        except OSError as exc:
            log_message(f"Failed to delete {lock_file}: {exc}", logfile=log_path)

    if not stale_found:
        log_message("No stale locks detected", logfile=log_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
