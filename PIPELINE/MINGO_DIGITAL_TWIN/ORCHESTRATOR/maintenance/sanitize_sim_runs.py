#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/sanitize_sim_runs.py
Purpose: Remove completed, broken, or stale INTERSTEPS SIM_RUN directories under explicit safeguards.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/sanitize_sim_runs.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import fcntl
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT_DIR))
sys.path.append(str(ROOT_DIR / "MASTER_STEPS"))

from STEP_SHARED.sim_utils import extract_step_id_chain


def _log_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _log_info(message: str) -> None:
    print(f"[{_log_ts()}] [STEP_SANITIZE] {message}")


def _log_warn(message: str) -> None:
    print(f"[{_log_ts()}] [STEP_SANITIZE] [WARN] {message}")


def expected_payload_patterns(step_index: int) -> tuple[str, ...]:
    if step_index == 1:
        return (
            "muon_sample_*.chunks.json",
            "muon_sample_*.pkl",
            "muon_sample_*.csv",
        )
    stem = f"step_{step_index}"
    return (
        f"{stem}_chunks.chunks.json",
        f"{stem}.pkl",
        f"{stem}.csv",
    )


def detect_broken_sim_run(sim_run_dir: Path, step_index: int) -> str | None:
    # Empty directories are always trash.
    has_file = any(path.is_file() for path in sim_run_dir.rglob("*"))
    if not has_file:
        return "empty_directory"

    payload_paths: list[Path] = []
    for pattern in expected_payload_patterns(step_index):
        payload_paths.extend(sim_run_dir.glob(pattern))
    if not payload_paths:
        return "missing_output_payload"

    manifest_paths = [path for path in payload_paths if path.name.endswith(".chunks.json")]
    for manifest_path in manifest_paths:
        try:
            manifest = json.loads(manifest_path.read_text())
        except (json.JSONDecodeError, OSError):
            return f"invalid_manifest:{manifest_path.name}"

        chunks = manifest.get("chunks", [])
        if chunks is None:
            chunks = []
        if not isinstance(chunks, list):
            return f"invalid_chunks_field:{manifest_path.name}"
        if not chunks:
            return f"empty_manifest:{manifest_path.name}"

        for chunk_raw in chunks:
            chunk_path = Path(str(chunk_raw))
            if not chunk_path.is_absolute():
                chunk_path = (manifest_path.parent / chunk_path).resolve()
            if not chunk_path.exists():
                return f"missing_chunk:{manifest_path.name}"
            try:
                if chunk_path.stat().st_size <= 0:
                    return f"empty_chunk:{chunk_path.name}"
            except OSError:
                return f"unreadable_chunk:{chunk_path.name}"

    return None


def parse_step_index(step_dir: Path) -> int | None:
    match = re.match(r"STEP_(\d+)_TO_", step_dir.name)
    if not match:
        return None
    return int(match.group(1))


def normalize_step_id(value: object) -> str:
    try:
        num = int(float(value))
        return f"{num:03d}"
    except (TypeError, ValueError):
        return str(value)


def combo_done_in_mesh(mesh: pd.DataFrame, step_ids: list[str], step_index: int) -> bool | None:
    if "done" not in mesh.columns:
        return None
    if step_index <= 0:
        return None
    if len(step_ids) < step_index:
        return None
    step_cols = [f"step_{idx}_id" for idx in range(1, step_index + 1)]
    for col in step_cols:
        if col not in mesh.columns:
            return None
    mask = pd.Series(True, index=mesh.index)
    normalized_mesh = {col: mesh[col].map(normalize_step_id) for col in step_cols}
    for col, value in zip(step_cols, step_ids[:step_index]):
        mask &= normalized_mesh[col] == normalize_step_id(value)
    matched = mesh[mask]
    if matched.empty:
        return None
    done_flags = matched["done"].fillna(0).astype(int)
    return bool((done_flags == 1).all())


def find_metadata(sim_run_dir: Path) -> dict | None:
    preferred = sorted(sim_run_dir.glob("step_*_chunks.chunks.json"))
    candidates = preferred or sorted(sim_run_dir.glob("*.chunks.json"))
    for path in candidates:
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        meta = data.get("metadata")
        if isinstance(meta, dict):
            return meta
    return None


def step_ids_from_sim_run_dir(sim_run_dir: Path, step_index: int) -> list[str] | None:
    name = sim_run_dir.name
    if not name.startswith("SIM_RUN_"):
        return None
    parts = name.removeprefix("SIM_RUN_").split("_")
    if len(parts) < step_index:
        return None
    return parts[:step_index]


def iter_step_dirs(intersteps_dir: Path) -> list[Path]:
    step_dirs = sorted(intersteps_dir.glob("STEP_*_TO_*"))
    return [path for path in step_dirs if path.name != "STEP_0_TO_1"]


def _is_lock_busy(lock_path: Path) -> bool:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        finally:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Remove SIM_RUN directories when all mesh rows sharing the same step-id combination "
            "for that step are marked done in param_mesh.csv."
        )
    )
    parser.add_argument(
        "--intersteps-dir",
        default=str(next(parent for parent in Path(__file__).resolve().parents if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()) / "PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS"),
        help="Base INTERSTEPS directory.",
    )
    parser.add_argument(
        "--param-mesh",
        default=str(next(parent for parent in Path(__file__).resolve().parents if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()) / "PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv"),
        help="Path to param_mesh.csv.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete directories (default is dry-run).",
    )
    parser.add_argument(
        "--min-age-seconds",
        type=int,
        default=900,
        help=(
            "Only delete SIM_RUN dirs older than this many seconds. "
            "Helps avoid deleting directories while downstream steps are still reading them."
        ),
    )
    parser.add_argument(
        "--step-final-lock",
        default=str(next(parent for parent in Path(__file__).resolve().parents if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()) / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS/cron/sim_final.lock"),
        help=(
            "Lock file used by STEP_FINAL cron. If locked, STEP_10_TO_FINAL cleanup is skipped "
            "to avoid deleting active inputs."
        ),
    )
    parser.add_argument(
        "--delete-no-mesh-match",
        action="store_true",
        help=(
            "Also delete stale SIM_RUN directories whose step-id chain does not match any row "
            "in param_mesh.csv (typically leftovers from previous mesh generations)."
        ),
    )
    args = parser.parse_args()

    intersteps_dir = Path(args.intersteps_dir).expanduser().resolve()
    mesh_path = Path(args.param_mesh).expanduser().resolve()
    step_final_lock = Path(args.step_final_lock).expanduser().resolve()
    min_age_seconds = max(0, int(args.min_age_seconds))
    if not intersteps_dir.exists():
        raise FileNotFoundError(f"INTERSTEPS dir not found: {intersteps_dir}")
    if not mesh_path.exists():
        raise FileNotFoundError(f"param_mesh.csv not found: {mesh_path}")

    _log_info(f"Intersteps dir: {intersteps_dir}")
    _log_info(f"Param mesh: {mesh_path}")
    _log_info(f"Min age (s): {min_age_seconds}")
    _log_info(f"STEP_FINAL lock: {step_final_lock}")

    # Recommended workflow:
    # 1) Generate a batch of mesh rows (STEP_0) with shared columns.
    # 2) Run STEP_1/2 once, then reuse those runs for STEP_3+.
    # 3) Mark mesh rows done in STEP_FINAL.
    # 4) Run this script to remove SIM_RUNs whose step IDs are no longer present in active rows.
    mesh = pd.read_csv(mesh_path)
    if "done" not in mesh.columns:
        _log_warn("No done column found; nothing to delete.")
        return

    _log_info(f"Loaded mesh rows: {len(mesh)}")

    removed = 0
    removed_broken = 0
    removed_no_mesh_match = 0
    skipped = 0
    skipped_recent = 0
    skipped_locked = 0
    unknown = 0
    now_ts = datetime.now(timezone.utc).timestamp()
    step_final_busy = _is_lock_busy(step_final_lock)
    if step_final_busy:
        _log_info("STEP_FINAL lock is busy; STEP_10_TO_FINAL cleanup will be skipped this run.")
    for step_dir in iter_step_dirs(intersteps_dir):
        step_index = parse_step_index(step_dir)
        if step_index is None:
            unknown += 1
            _log_warn(f"SKIP (unrecognized step dir): {step_dir}")
            continue
        if step_dir.name == "STEP_10_TO_FINAL" and step_final_busy:
            skipped_locked += 1
            continue
        for sim_run_dir in sorted(step_dir.glob("SIM_RUN_*")):
            try:
                age_s = now_ts - sim_run_dir.stat().st_mtime
            except OSError:
                unknown += 1
                _log_warn(f"SKIP (cannot stat): {sim_run_dir}")
                continue
            if age_s < min_age_seconds:
                skipped_recent += 1
                continue

            broken_reason = detect_broken_sim_run(sim_run_dir, step_index)
            if broken_reason is not None:
                if args.apply:
                    shutil.rmtree(sim_run_dir)
                    removed += 1
                    removed_broken += 1
                    _log_info(f"DELETED_BROKEN ({broken_reason}): {sim_run_dir}")
                else:
                    _log_info(f"DRY-RUN DELETE_BROKEN ({broken_reason}): {sim_run_dir}")
                continue

            step_chain: list[str] | None = None
            meta = find_metadata(sim_run_dir)
            if meta:
                chain = extract_step_id_chain(meta)
                if chain:
                    step_chain = chain[:step_index]
            if not step_chain:
                # Fallback for old/partial runs where chunks metadata got removed.
                step_chain = step_ids_from_sim_run_dir(sim_run_dir, step_index)
            if not step_chain:
                unknown += 1
                _log_warn(f"SKIP (cannot infer step ids): {sim_run_dir}")
                continue
            combo_done = combo_done_in_mesh(mesh, step_chain, step_index)
            if combo_done is None:
                if args.delete_no_mesh_match:
                    if args.apply:
                        shutil.rmtree(sim_run_dir)
                        removed += 1
                        removed_no_mesh_match += 1
                        _log_info(f"DELETED_NO_MESH_MATCH: {sim_run_dir}")
                    else:
                        _log_info(f"DRY-RUN DELETE_NO_MESH_MATCH: {sim_run_dir}")
                else:
                    unknown += 1
                    _log_warn(f"SKIP (no mesh match): {sim_run_dir}")
                continue
            if not combo_done:
                skipped += 1
                continue
            if args.apply:
                shutil.rmtree(sim_run_dir)
                removed += 1
                _log_info(f"DELETED: {sim_run_dir}")
            else:
                _log_info(f"DRY-RUN DELETE: {sim_run_dir}")

    _log_info(
        "Summary: "
        f"removed={removed}, "
        f"removed_broken={removed_broken}, "
        f"removed_no_mesh_match={removed_no_mesh_match}, "
        f"skipped={skipped}, "
        f"skipped_recent={skipped_recent}, "
        f"skipped_locked={skipped_locked}, "
        f"unknown={unknown}"
    )


if __name__ == "__main__":
    main()
