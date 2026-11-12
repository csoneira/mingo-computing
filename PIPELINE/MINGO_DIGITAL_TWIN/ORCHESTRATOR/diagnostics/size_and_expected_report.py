#!/usr/bin/env python3

"""Report expected simulation combinations and current INTERSTEPS storage usage."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Iterable
import time
import subprocess

import numpy as np
import pandas as pd

_TWIN_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_TWIN_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_TWIN_BOOTSTRAP_ROOT))
from ORCHESTRATOR.lib.paths import digital_twin_root

DIGITAL_TWIN_ROOT = digital_twin_root()


def load_mesh(mesh_path: Path, include_done: bool) -> pd.DataFrame:
    mesh = pd.read_csv(mesh_path)
    if "done" in mesh.columns and not include_done:
        mesh = mesh[mesh["done"].fillna(0).astype(int) != 1]
    return mesh


def normalize_id(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    try:
        return f"{int(float(value)):03d}"
    except (TypeError, ValueError):
        return str(value)


def expected_counts_from_mesh(mesh: pd.DataFrame) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in range(1, 11):
        cols = [f"step_{idx}_id" for idx in range(1, step + 1)]
        if not all(col in mesh.columns for col in cols):
            counts[f"STEP_{step}_TO_{step + 1}"] = 0
            continue
        combos = mesh[cols].apply(lambda col: col.map(normalize_id)).drop_duplicates()
        counts[f"STEP_{step}_TO_{step + 1}"] = len(combos)
    return counts


def expected_all_zero(expected: dict[str, int]) -> bool:
    return all(int(expected.get(f"STEP_{step}_TO_{step + 1}", 0)) == 0 for step in range(1, 11))


def observed_counts_from_intersteps(intersteps_dir: Path) -> dict[str, int]:
    observed: dict[str, int] = {}
    for step in range(1, 11):
        step_name = f"STEP_{step}_TO_{step + 1}"
        step_dir = intersteps_dir / step_name
        if not step_dir.exists():
            observed[step_name] = 0
            continue
        observed[step_name] = len(list(step_dir.glob("SIM_RUN_*")))
    return observed


def available_inputs_for_step(step: int, intersteps_dir: Path, expected: dict[str, int]) -> int:
    if step == 1:
        return expected.get("STEP_1_TO_2", 0)
    input_dir = intersteps_dir / f"STEP_{step - 1}_TO_{step}"
    if not input_dir.exists():
        return 0
    return len(list(input_dir.glob("SIM_RUN_*")))


def count_dirs_and_size(step_dir: Path) -> tuple[int, int]:
    dirs = list(step_dir.glob("SIM_RUN_*"))
    total_bytes = 0
    for dir_path in dirs:
        for item in dir_path.rglob("*"):
            if item.is_file():
                total_bytes += item.stat().st_size
    return len(dirs), total_bytes


def count_files_and_size(
    dir_path: Path,
    pattern: str = "*",
    *,
    now_ts: float | None = None,
    recent_seconds: int | None = None,
) -> tuple[int, int, int | None, int]:
    if not dir_path.exists():
        return 0, 0, None, 0
    files = [p for p in dir_path.glob(pattern) if p.is_file()]
    total_bytes = 0
    newest_mtime: float | None = None
    recent_count = 0
    for file_path in files:
        stat = file_path.stat()
        total_bytes += stat.st_size
        if newest_mtime is None or stat.st_mtime > newest_mtime:
            newest_mtime = stat.st_mtime
        if now_ts is not None and recent_seconds is not None and (now_ts - stat.st_mtime) <= recent_seconds:
            recent_count += 1
    newest_age = int(max(0.0, now_ts - newest_mtime)) if now_ts is not None and newest_mtime is not None else None
    return len(files), total_bytes, newest_age, recent_count


def resolve_step_final_dat_dir(sim_data_dir: Path) -> Path:
    files_dir = sim_data_dir / "FILES"
    if files_dir.exists():
        return files_dir
    return sim_data_dir


def fmt_gb(size_bytes: int) -> str:
    return f"{size_bytes / (1024 ** 3):.3f}"


def estimate_one_line_bytes(
    dirs_now: int,
    size_now: int,
    exp_dirs: int,
    size_expected: int,
) -> int:
    if dirs_now > 0:
        return int(size_now / dirs_now)
    if exp_dirs > 0 and size_expected > 0:
        return int(size_expected / exp_dirs)
    return 0


def format_age(seconds: int) -> str:
    seconds = max(0, int(seconds))
    mins, sec = divmod(seconds, 60)
    hrs, mins = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs}h{mins:02d}m{sec:02d}s"
    if mins > 0:
        return f"{mins}m{sec:02d}s"
    return f"{sec}s"


def format_age_opt(seconds: int | None) -> str:
    if seconds is None:
        return "n/a"
    return format_age(seconds)


def newest_age_seconds(paths: Iterable[Path], now_ts: float) -> int | None:
    mtimes: list[float] = []
    for path in paths:
        if path.exists():
            mtimes.append(path.stat().st_mtime)
    if not mtimes:
        return None
    newest = max(mtimes)
    return int(max(0.0, now_ts - newest))


def tail_lines(path: Path, max_lines: int) -> list[str]:
    if not path.exists() or max_lines <= 0:
        return []
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = data.splitlines()
    if max_lines >= len(lines):
        return lines
    return lines[-max_lines:]


def health_snapshot(
    dataflow_root: Path,
    now_ts: float,
    tail_n: int,
) -> tuple[list[str], int, str | None]:
    logs_root = dataflow_root / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME" / "CRON_LOGS"
    step1_logs = sorted(
        (logs_root / "MAIN_ANALYSIS" / "STAGE_1" / "EVENT_DATA" / "STEP_1").glob("guide_raw_to_corrected_*.log")
    )
    # stale_after_seconds is tuned to each job cadence.
    log_groups: list[tuple[str, list[Path], int]] = [
        ("sim_cycle", [logs_root / "SIMULATION" / "RUN" / "sim_main_pipeline_cycle.log"], 180),
        ("step1_all", step1_logs, 180),
        ("step2_all", [logs_root / "MAIN_ANALYSIS" / "STAGE_1" / "EVENT_DATA" / "STEP_2" / "guide_corrected_to_accumulated_all.log"], 180),
        ("step3_all", [logs_root / "MAIN_ANALYSIS" / "STAGE_1" / "EVENT_DATA" / "STEP_3" / "guide_accumulated_to_joined_all.log"], 180),
        ("stale_locks", [logs_root / "ANCILLARY" / "OPERATIONS" / "SOLVE_STALE_LOCKS" / "solve_stale_locks.cron.log"], 420),
        ("watchdog", [logs_root / "ANCILLARY" / "OPERATIONS" / "WATCHDOG_PROCESS_COUNTS" / "watchdog_process_counts.log"], 420),
    ]

    lines: list[str] = []
    for label, paths, stale_after in log_groups:
        age = newest_age_seconds(paths, now_ts)
        if age is None:
            lines.append(f"  {label:<11}: missing")
            continue
        status = "OK" if age < stale_after else "STALE"
        lines.append(f"  {label:<11}: age={format_age(age):>8} status={status}")

    err_patterns = (
        "traceback",
        "exception",
        "error",
        "failed",
        "filenotfounderror",
        "no such file or directory",
    )
    error_hits = 0
    latest_error: str | None = None
    scan_paths: list[Path] = []
    for _, paths, _ in log_groups:
        scan_paths.extend(paths)
    seen: set[Path] = set()
    for path in scan_paths:
        if path in seen:
            continue
        seen.add(path)
        for raw in reversed(tail_lines(path, tail_n)):
            lowered = raw.lower()
            if any(token in lowered for token in err_patterns):
                error_hits += 1
                if latest_error is None:
                    latest_error = f"{path.name}: {raw.strip()}"

    return lines, error_hits, latest_error


def process_running(pattern: str) -> bool:
    try:
        out = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return out.returncode == 0 and bool(out.stdout.strip())


def step_final_status_label(
    pending_rows: int,
    step_final_running: bool,
    sim_params_age: int | None,
    newest_dat_age: int | None,
    sim_cycle_age: int | None,
) -> str:
    if pending_rows <= 0:
        return "DONE"
    ref_age = sim_params_age if sim_params_age is not None else newest_dat_age
    if step_final_running:
        if ref_age is None:
            return "RUNNING"
        if ref_age <= 120:
            return "ACTIVE"
        if ref_age <= 600:
            return "RUNNING_SLOW"
        return "RUNNING_STALE"
    if ref_age is not None and ref_age <= 120:
        return "BETWEEN_CYCLES"
    if sim_cycle_age is not None and sim_cycle_age <= 180:
        return "WAITING_CYCLE"
    return "STALE"


def main() -> None:
    parser = argparse.ArgumentParser(description="Combined size/expected SIM_RUN report.")
    parser.add_argument(
        "--intersteps-dir",
        default=str(DIGITAL_TWIN_ROOT / "SIMULATION_OUTPUTS/INTERSTEPS"),
        help="INTERSTEPS base directory.",
    )
    parser.add_argument(
        "--param-mesh",
        default=str(DIGITAL_TWIN_ROOT / "SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv"),
        help="Path to param_mesh.csv.",
    )
    parser.add_argument(
        "--include-done",
        dest="include_done",
        action="store_true",
        default=True,
        help="Include done rows in expected counts (default).",
    )
    parser.add_argument(
        "--exclude-done",
        dest="include_done",
        action="store_false",
        help="Exclude done rows from expected counts (pending-only view).",
    )
    parser.add_argument(
        "--z-positions",
        default=None,
        help=(
            "Comma-separated z positions to filter param_mesh (matches z_p1..z_pN). "
            "Provide 1–4 values; only the first N z_p columns are matched."
        ),
    )
    parser.add_argument(
        "--z-tol",
        type=float,
        default=1e-6,
        help="Absolute tolerance when matching z positions (used with --z-positions).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show progress and per-step timings.",
    )
    parser.add_argument(
        "--health-always",
        action="store_true",
        help="Print the log health snapshot on every run.",
    )
    parser.add_argument(
        "--health-interval-seconds",
        type=int,
        default=30,
        help=(
            "Print health snapshot only when epoch time is a multiple of this interval. "
            "Set 0 to disable periodic snapshots."
        ),
    )
    parser.add_argument(
        "--health-tail-lines",
        type=int,
        default=120,
        help="Number of tail lines per log to scan for recent error-like messages.",
    )
    args = parser.parse_args()

    intersteps_dir = Path(args.intersteps_dir).expanduser().resolve()
    mesh_path = Path(args.param_mesh).expanduser().resolve()
    if not intersteps_dir.exists():
        raise FileNotFoundError(f"INTERSTEPS dir not found: {intersteps_dir}")
    if not mesh_path.exists():
        raise FileNotFoundError(f"param_mesh.csv not found: {mesh_path}")

    now_ts = time.time()
    mesh = load_mesh(mesh_path, args.include_done)

    # load full param_mesh (always use for computing expected counts when z filter is used)
    full_mesh = pd.read_csv(mesh_path)
    full_mesh_for_progress = full_mesh.copy()

    # optional filter by z positions (matches z_p1..z_pN)
    if args.z_positions is not None:
        z_vals = [v.strip() for v in str(args.z_positions).split(",") if v.strip() != ""]
        try:
            z_vals = [float(v) for v in z_vals]
        except ValueError:
            raise ValueError("--z-positions must be comma-separated numeric values")
        z_cols = [c for c in ("z_p1", "z_p2", "z_p3", "z_p4") if c in full_mesh.columns]
        if len(z_vals) > len(z_cols):
            raise ValueError("More z values provided than z_p columns available in param_mesh.csv")

        def _z_mask(df: pd.DataFrame) -> pd.Series:
            m = pd.Series(True, index=df.index)
            for i, z in enumerate(z_vals):
                col = z_cols[i]
                m &= np.isclose(pd.to_numeric(df[col], errors="coerce").astype(float), float(z), atol=args.z_tol, rtol=0)
            return m

        full_mask = _z_mask(full_mesh)
        if args.verbose:
            print(f"Filtered full param_mesh by z positions ({', '.join(map(str, z_vals))}) -> {full_mask.sum()} rows match", flush=True)
        # expected counts should be computed from the full param_mesh subset (so %done is correct for that z set)
        expected = expected_counts_from_mesh(full_mesh[full_mask].copy())
        full_mesh_for_progress = full_mesh[full_mask].copy()

        # also restrict the working 'mesh' (which may already be filtered by done) to the same z subset
        mesh = mesh[_z_mask(mesh)].copy()
    else:
        # attempt simple auto-detection: if pending rows (not done) all share a single
        # fully-specified z_p1..z_pN combination, treat report as filtered for that z set
        expected = None
        z_cols = [c for c in ("z_p1", "z_p2", "z_p3", "z_p4") if c in mesh.columns]
        pending = mesh[mesh.get("done", pd.Series(0, index=mesh.index)) != 1]
        if not pending.empty and z_cols:
            # consider only rows with all z columns non-null
            pending_full_z = pending.dropna(subset=z_cols)
            if not pending_full_z.empty:
                unique_z = pending_full_z[z_cols].drop_duplicates()
                if len(unique_z) == 1:
                    # auto-apply this z selection to compute expected counts
                    z_vals = [float(unique_z.iloc[0][c]) for c in z_cols]
                    full_mask = pd.Series(True, index=full_mesh.index)
                    for i, z in enumerate(z_vals):
                        col = z_cols[i]
                        full_mask &= np.isclose(pd.to_numeric(full_mesh[col], errors="coerce").astype(float), z, atol=args.z_tol, rtol=0)
                    if args.verbose:
                        print(f"Auto-detected single active z configuration: {z_vals[:len(z_cols)]}; using it for expected counts", flush=True)
                    expected = expected_counts_from_mesh(full_mesh[full_mask].copy())
                    full_mesh_for_progress = full_mesh[full_mask].copy()
                    # restrict working mesh as well to same z subset
                    mesh_mask = full_mask.reindex(mesh.index, fill_value=False)
                    mesh = mesh[mesh_mask].copy()
        if expected is None:
            expected = expected_counts_from_mesh(mesh)

    expected_fallback_used = False
    if expected_all_zero(expected):
        observed = observed_counts_from_intersteps(intersteps_dir)
        if any(v > 0 for v in observed.values()):
            expected = {
                key: max(int(expected.get(key, 0)), int(observed.get(key, 0)))
                for key in observed
            }
            expected_fallback_used = True

    step_dirs = sorted(intersteps_dir.glob("STEP_*_TO_*"))

    rows = []
    total_dirs = 0
    total_expected_dirs = 0
    total_inputs = 0
    total_bytes = 0
    total_expected_bytes = 0
    total_one_line_bytes = 0

    for step_dir in step_dirs:
        step_name = step_dir.name

        # print(step_name)
        if "0_TO_1" in step_name or "10_TO_FINAL" in step_name:
            continue

        if args.verbose:
            print(f"Scanning {step_name} ...", flush=True)
            t0 = time.perf_counter()
        dirs_now, size_now = count_dirs_and_size(step_dir)
        if args.verbose:
            elapsed = time.perf_counter() - t0
            print(f"  {step_name}: scanned {dirs_now} dirs, {fmt_gb(size_now)} GB in {elapsed:.2f}s", flush=True)
        step_num = int(step_name.split("_")[1])
        exp_dirs = expected.get(step_name, 0)
        available_inputs = available_inputs_for_step(step_num, intersteps_dir, expected)
        if dirs_now > 0:
            avg_bytes = size_now / dirs_now
            size_expected = int(avg_bytes * exp_dirs)
        else:
            size_expected = 0
        one_line_bytes = estimate_one_line_bytes(dirs_now, size_now, exp_dirs, size_expected)
        pct = (dirs_now / exp_dirs * 100.0) if exp_dirs else 0.0
        rows.append(
            (
                step_name,
                dirs_now,
                exp_dirs,
                available_inputs,
                size_now,
                size_expected,
                one_line_bytes,
                pct,
            )
        )

        total_dirs += dirs_now
        total_expected_dirs += exp_dirs
        total_inputs += available_inputs
        total_bytes += size_now
        total_expected_bytes += size_expected
        total_one_line_bytes += one_line_bytes

    # Add STEP_FINAL progress/growth row so activity remains visible after STEP_1..STEP_9 reach 100%.
    sim_data_dir = intersteps_dir.parent / "SIMULATED_DATA"
    sim_dat_dir = resolve_step_final_dat_dir(sim_data_dir)
    step10_final_dir = intersteps_dir / "STEP_10_TO_FINAL"
    step10_inputs = len(list(step10_final_dir.glob("SIM_RUN_*"))) if step10_final_dir.exists() else 0
    step_final_files, step_final_size, step_final_latest_age, step_final_recent_5m = count_files_and_size(
        sim_dat_dir,
        "*.dat",
        now_ts=now_ts,
        recent_seconds=300,
    )
    sim_params_path = sim_data_dir / "step_final_simulation_params.csv"
    sim_params_age = newest_age_seconds([sim_params_path], now_ts)
    sim_cycle_log = (
        intersteps_dir.parent.parent
        / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME"
        / "CRON_LOGS"
        / "SIMULATION"
        / "RUN"
        / "sim_main_pipeline_cycle.log"
    )
    sim_cycle_age = newest_age_seconds([sim_cycle_log], now_ts)
    step_final_running = process_running("step_final_daq_to_station_dat.py")
    if "done" in full_mesh_for_progress.columns:
        done_series = pd.to_numeric(full_mesh_for_progress["done"], errors="coerce").fillna(0).astype(int)
        step_final_now = int((done_series == 1).sum())
    else:
        step_final_now = 0
    step_final_exp = max(int(len(full_mesh_for_progress)), int(step10_inputs))
    step_final_exp = max(step_final_exp, step_final_now)
    if step_final_now > 0:
        step_final_size_expected = int((step_final_size / step_final_now) * step_final_exp)
    else:
        step_final_size_expected = 0
    step_final_one_line = estimate_one_line_bytes(
        step_final_now,
        step_final_size,
        step_final_exp,
        step_final_size_expected,
    )
    step_final_pct = (step_final_now / step_final_exp * 100.0) if step_final_exp else 0.0
    rows.append(
        (
            "STEP_FINAL",
            step_final_now,
            step_final_exp,
            step10_inputs,
            step_final_size,
            step_final_size_expected,
            step_final_one_line,
            step_final_pct,
        )
    )
    total_dirs += step_final_now
    total_expected_dirs += step_final_exp
    total_inputs += step10_inputs
    total_bytes += step_final_size
    total_expected_bytes += step_final_size_expected
    total_one_line_bytes += step_final_one_line

    width_step = max(len(row[0]) for row in rows + [("TOTAL", 0, 0, 0, 0, 0, 0, 0.0)])
    width_dirs = max(
        len(f"{row[1]}/{row[2]}")
        for row in rows + [("TOTAL", total_dirs, total_expected_dirs, 0, 0, 0, 0, 0.0)]
    )
    width_inputs = max(
        len(str(row[3]))
        for row in rows + [("TOTAL", 0, 0, total_inputs, 0, 0, 0, 0.0)]
    )
    width_size = max(
        len(f"{fmt_gb(row[4])}/{fmt_gb(row[5])}")
        for row in rows + [("TOTAL", 0, 0, 0, total_bytes, total_expected_bytes, 0, 0.0)]
    )
    width_line = max(
        len(fmt_gb(row[6]))
        for row in rows + [("TOTAL", 0, 0, 0, 0, 0, total_one_line_bytes, 0.0)]
    )
    width_step = max(width_step, len("STEP"))
    width_dirs = max(width_dirs, len("DIRS NOW/EXP"))
    width_inputs = max(width_inputs, len("INPUTS"))
    width_size = max(width_size, len("SIZE GB NOW/EXP"))
    width_line = max(width_line, len("ONE LINE GB"))
    width_pct = max(7, len("% DONE"))

    header = (
        f"{'STEP':<{width_step}} | {'DIRS NOW/EXP':>{width_dirs}} | {'INPUTS':>{width_inputs}} | "
        f"{'SIZE GB NOW/EXP':>{width_size}} | {'ONE LINE GB':>{width_line}} | {'% DONE':>{width_pct}}"
    )
    sep = (
        f"{'-' * width_step}-+-{'-' * width_dirs}-+-{'-' * width_inputs}-+-{'-' * width_size}-+-{'-' * width_line}-+-{'-' * width_pct}"
    )

    # print("SIM_RUN utilization summary")
    print(sep)
    print(header)
    print(sep)
    for step_name, dirs_now, exp_dirs, available_inputs, size_now, size_expected, one_line_bytes, pct in rows:
        dirs_cell = f"{dirs_now}/{exp_dirs}"
        size_cell = f"{fmt_gb(size_now)}/{fmt_gb(size_expected)}"
        one_line_cell = fmt_gb(one_line_bytes)
        print(
            f"{step_name:<{width_step}} | {dirs_cell:>{width_dirs}} | {available_inputs:>{width_inputs}} | "
            f"{size_cell:>{width_size}} | {one_line_cell:>{width_line}} | {pct:>{width_pct}.1f}%"
        )
    total_pct = (total_dirs / total_expected_dirs * 100.0) if total_expected_dirs else 0.0
    total_dirs_cell = f"{total_dirs}/{total_expected_dirs}"
    total_size_cell = f"{fmt_gb(total_bytes)}/{fmt_gb(total_expected_bytes)}"
    total_line_cell = fmt_gb(total_one_line_bytes)
    print(sep)
    print(
        f"{'TOTAL':<{width_step}} | {total_dirs_cell:>{width_dirs}} | {total_inputs:>{width_inputs}} | "
        f"{total_size_cell:>{width_size}} | {total_line_cell:>{width_line}} | {total_pct:>{width_pct}.1f}%"
    )
    print(sep)

    pending_final = max(0, step_final_exp - step_final_now)
    step_final_state = step_final_status_label(
        pending_final,
        step_final_running,
        sim_params_age,
        step_final_latest_age,
        sim_cycle_age,
    )
    step_final_hint: str | None = None
    cycle_tail = tail_lines(sim_cycle_log, 200)
    auto_remap_hits = sum("auto-remapped pending row index" in line for line in cycle_tail)
    no_match_hits = sum("No matching param_mesh row found" in line for line in cycle_tail)
    if auto_remap_hits > 0:
        step_final_hint = f"auto_remapped_rows={auto_remap_hits}"
    elif no_match_hits > 0:
        step_final_hint = f"no_matching_param_mesh_rows={no_match_hits}"
    elif any("Sampling interrupted" in line for line in cycle_tail):
        step_final_hint = "sampling_interrupted_recently"
    elif any("stage=step_final status=start" in line for line in cycle_tail):
        step_final_hint = "step_final_started_recently"

    print()
    print(f"STEP_FINAL MONITOR @ {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now_ts))}")
    print(
        f"  status={step_final_state} process={'RUNNING' if step_final_running else 'IDLE'} "
        f"pending={pending_final}/{step_final_exp}"
    )
    print(
        f"  sim_params_age={format_age_opt(sim_params_age):>8} "
        f"newest_dat_age={format_age_opt(step_final_latest_age):>8} "
        f"new_dat_5m={step_final_recent_5m}"
    )
    print(
        f"  sim_cycle_log_age={format_age_opt(sim_cycle_age):>8} "
        f"step10_inputs={step10_inputs} "
        f"dat_files={step_final_files}"
    )
    if step_final_hint:
        print(f"  hint={step_final_hint}")
    if expected_fallback_used:
        print("  report_fallback=expected_counts_from_observed_step_dirs")

    show_health = args.health_always
    if args.health_interval_seconds > 0 and int(now_ts) % args.health_interval_seconds == 0:
        show_health = True
    if show_health:
        dataflow_root = intersteps_dir.parent.parent
        health_lines, error_hits, latest_error = health_snapshot(
            dataflow_root=dataflow_root,
            now_ts=now_ts,
            tail_n=args.health_tail_lines,
        )
        print()
        print(f"HEALTH SNAPSHOT @ {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now_ts))}")
        for line in health_lines:
            print(line)
        print(f"  recent_error_hits_in_tails={error_hits}")
        if latest_error:
            print(f"  latest_error_line={latest_error}")


if __name__ == "__main__":
    main()
