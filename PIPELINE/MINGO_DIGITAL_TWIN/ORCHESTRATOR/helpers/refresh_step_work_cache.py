#!/usr/bin/env python3

"""Build run_step scheduler cache/state CSV snapshots."""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh_path", type=Path)
    parser.add_argument("intersteps_dir", type=Path)
    parser.add_argument("out_csv_path", type=Path)
    parser.add_argument("state_csv_path", type=Path)
    parser.add_argument("stuck_csv_path", type=Path)
    parser.add_argument("broken_csv_path", type=Path)
    parser.add_argument("strict_line_closure")
    parser.add_argument("step1_stuck_age_s")
    return parser.parse_args()


def normalize_id(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    try:
        return f"{int(float(value)):03d}"
    except (TypeError, ValueError):
        text = str(value).strip()
        return "" if text.lower() in {"", "nan", "<na>"} else text


def output_dir_for_step(intersteps_dir: Path, step_num: int) -> Path:
    if step_num == 10:
        return intersteps_dir / "STEP_10_TO_FINAL"
    return intersteps_dir / f"STEP_{step_num}_TO_{step_num + 1}"


def parse_sim_run_ids(path: Path) -> tuple[str, ...] | None:
    name = path.name
    if not name.startswith("SIM_RUN_"):
        return None
    raw = name[len("SIM_RUN_") :].split("_")
    if not raw:
        return None
    normalized = []
    for val in raw:
        norm = normalize_id(val)
        if norm:
            normalized.append(norm)
    return tuple(normalized)


def expected_output_patterns(step_num: int) -> tuple[str, ...]:
    if step_num == 1:
        return (
            "muon_sample_*.chunks.json",
            "muon_sample_*.pkl",
            "muon_sample_*.csv",
        )
    stem = f"step_{step_num}"
    return (
        f"{stem}_chunks.chunks.json",
        f"{stem}.pkl",
        f"{stem}.csv",
    )


def has_expected_output(step_num: int, sim_dir: Path) -> tuple[bool, str]:
    payload_paths: list[Path] = []
    for pattern in expected_output_patterns(step_num):
        payload_paths.extend(sim_dir.glob(pattern))
    if not payload_paths:
        return False, "missing_output_payload"

    manifest_paths = [path for path in payload_paths if path.name.endswith(".chunks.json")]
    for manifest_path in manifest_paths:
        try:
            manifest = json.loads(manifest_path.read_text())
        except (json.JSONDecodeError, OSError):
            return False, f"invalid_manifest:{manifest_path.name}"
        chunks = manifest.get("chunks", [])
        if chunks is None:
            chunks = []
        if not isinstance(chunks, list):
            return False, f"invalid_chunks_field:{manifest_path.name}"
        for chunk_raw in chunks:
            chunk_path = Path(str(chunk_raw))
            if not chunk_path.is_absolute():
                chunk_path = (manifest_path.parent / chunk_path).resolve()
            if not chunk_path.exists():
                return False, f"missing_manifest_chunk:{manifest_path.name}"

    return True, "ok"


def main() -> int:
    args = parse_args()
    strict_line_closure = str(args.strict_line_closure).strip() == "1"
    try:
        step1_stuck_age_s = int(float(args.step1_stuck_age_s))
    except (TypeError, ValueError):
        step1_stuck_age_s = 1800
    if step1_stuck_age_s < 0:
        step1_stuck_age_s = 0

    if not args.mesh_path.exists():
        raise FileNotFoundError(f"param_mesh.csv not found: {args.mesh_path}")

    mesh_all = pd.read_csv(args.mesh_path)
    if "done" not in mesh_all.columns:
        mesh_all["done"] = 0
    mesh_all["done"] = mesh_all["done"].fillna(0).astype(int)

    step_cols = [f"step_{idx}_id" for idx in range(1, 11)]
    for col in step_cols:
        if col not in mesh_all.columns:
            mesh_all[col] = ""
        mesh_all[col] = mesh_all[col].map(normalize_id)

    mesh = mesh_all[mesh_all["done"] != 1].copy()
    rows: list[tuple[int, int, int, int, int, int]] = []
    broken_count = 0
    broken_records: list[tuple[int, str, str, str]] = []
    max_broken_records = 2000

    # Scan each step output directory once per refresh. The scheduler previously
    # walked the same large INTERSTEPS directories repeatedly while calculating
    # produced outputs, upstream availability, open STEP_1 lines, and latest
    # activity. Reusing this snapshot preserves the same decisions while
    # avoiding redundant filesystem traversal.
    scanned_outputs: dict[int, list[tuple[Path, tuple[str, ...], float]]] = {}
    for step_num in range(1, 11):
        step_outputs: list[tuple[Path, tuple[str, ...], float]] = []
        for sim_dir in output_dir_for_step(args.intersteps_dir, step_num).glob("SIM_RUN_*"):
            ids = parse_sim_run_ids(sim_dir)
            if ids is None or len(ids) < step_num:
                continue
            try:
                mtime = sim_dir.stat().st_mtime
            except OSError:
                mtime = 0.0
            step_outputs.append((sim_dir, ids, mtime))
        scanned_outputs[step_num] = step_outputs

    for step_num in range(1, 11):
        prefix_cols = step_cols[: step_num - 1]
        current_col = step_cols[step_num - 1]
        needed_by_prefix: dict[tuple[str, ...], int] = {}
        needed_step1_ids: set[str] = set()

        if step_num == 1:
            needed_step1_ids = set(mesh.loc[mesh[current_col] != "", current_col].tolist())
            needed_by_prefix[tuple()] = len(needed_step1_ids)
        else:
            subset = mesh[prefix_cols + [current_col]].copy()
            valid = subset[current_col] != ""
            for col in prefix_cols:
                valid &= subset[col] != ""
            subset = subset[valid]
            if not subset.empty:
                grouped = subset.groupby(prefix_cols, dropna=False)[current_col].nunique()
                for key, count in grouped.items():
                    if not isinstance(key, tuple):
                        key = (key,)
                    needed_by_prefix[tuple(str(k) for k in key)] = int(count)

        produced_by_prefix: Counter[tuple[str, ...]] = Counter()
        produced_dirs = 0
        produced_step1_ids: set[str] = set()
        for sim_dir, ids, _mtime in scanned_outputs[step_num]:
            produced_dirs += 1
            if step_num == 1:
                produced_step1_ids.add(ids[0])
            else:
                produced_by_prefix[tuple(ids[: step_num - 1])] += 1
            ok, reason = has_expected_output(step_num, sim_dir)
            if not ok:
                broken_count += 1
                if len(broken_records) < max_broken_records:
                    broken_records.append((step_num, sim_dir.name, reason, str(sim_dir)))

        if step_num == 1:
            produced_by_prefix[tuple()] = len(produced_step1_ids & needed_step1_ids)

        available_prefixes: set[tuple[str, ...]] = set()
        if step_num == 1:
            available_prefixes.add(tuple())
        else:
            for _sim_dir, ids, _mtime in scanned_outputs[step_num - 1]:
                available_prefixes.add(tuple(ids[: step_num - 1]))

        pending_prefixes = 0
        for prefix in available_prefixes:
            needed = needed_by_prefix.get(prefix, 0)
            if needed <= 0:
                continue
            if produced_by_prefix.get(prefix, 0) < needed:
                pending_prefixes += 1

        has_work = 1 if pending_prefixes > 0 else 0
        expected_dirs = int(sum(needed_by_prefix.values()))
        rows.append(
            (
                step_num,
                has_work,
                pending_prefixes,
                len(available_prefixes),
                produced_dirs,
                expected_dirs,
            )
        )

    active_step1_ids = set(mesh.loc[mesh["step_1_id"] != "", "step_1_id"].unique().tolist())
    open_step1_ids = {ids[0] for _sim_dir, ids, _mtime in scanned_outputs[1]}

    latest_activity_by_step1: dict[str, float] = {}
    for step_num in range(1, 11):
        for _sim_dir, ids, mtime in scanned_outputs[step_num]:
            step1_id = ids[0]
            previous = latest_activity_by_step1.get(step1_id)
            if previous is None or mtime > previous:
                latest_activity_by_step1[step1_id] = mtime

    active_open_step1_ids = sorted(active_step1_ids & open_step1_ids)
    unopened_step1_ids = sorted(active_step1_ids - open_step1_ids)

    total_by_step1 = (
        mesh_all.loc[mesh_all["step_1_id"] != ""]
        .groupby("step_1_id", dropna=False)
        .size()
        .to_dict()
    )
    done_by_step1 = (
        mesh_all.loc[(mesh_all["step_1_id"] != "") & (mesh_all["done"] == 1)]
        .groupby("step_1_id", dropna=False)
        .size()
        .to_dict()
    )
    pending_by_step1 = (
        mesh.loc[mesh["step_1_id"] != ""]
        .groupby("step_1_id", dropna=False)
        .size()
        .to_dict()
    )

    now_ts = time.time()
    stuck_count = 0
    oldest_active_age_s = 0
    stuck_rows: list[tuple[str, int, int, int, str, int, str]] = []
    for step1_id in active_open_step1_ids:
        pending_rows = int(pending_by_step1.get(step1_id, 0))
        total_rows = int(total_by_step1.get(step1_id, pending_rows))
        done_rows = int(done_by_step1.get(step1_id, max(0, total_rows - pending_rows)))
        last_activity_ts = latest_activity_by_step1.get(step1_id)
        if last_activity_ts is None:
            age_s = -1
            status = "no_activity"
        else:
            age_s = max(0, int(now_ts - last_activity_ts))
            oldest_active_age_s = max(oldest_active_age_s, age_s)
            status = "stuck" if age_s >= step1_stuck_age_s else "active"
        if status in {"stuck", "no_activity"}:
            stuck_count += 1
        last_activity_utc = (
            datetime.fromtimestamp(last_activity_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if last_activity_ts is not None
            else ""
        )
        stuck_rows.append(
            (
                step1_id,
                pending_rows,
                done_rows,
                total_rows,
                last_activity_utc,
                age_s,
                status,
            )
        )

    step1_new_lines_allowed = 1
    if strict_line_closure and active_open_step1_ids:
        step1_new_lines_allowed = 0

    args.out_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "step",
                "has_work",
                "pending_prefixes",
                "available_prefixes",
                "produced_dirs",
                "expected_dirs",
            ]
        )
        writer.writerows(rows)

    args.state_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with args.state_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["key", "value"])
        writer.writerows(
            [
                ("strict_line_closure", int(strict_line_closure)),
                ("step1_stuck_age_s", step1_stuck_age_s),
                ("active_open_step1_lines", len(active_open_step1_ids)),
                ("unopened_step1_lines", len(unopened_step1_ids)),
                ("stuck_step1_lines", stuck_count),
                ("oldest_active_step1_age_s", oldest_active_age_s),
                ("broken_runs", broken_count),
                ("step1_new_lines_allowed", step1_new_lines_allowed),
            ]
        )

    args.stuck_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with args.stuck_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "step_1_id",
                "pending_rows",
                "done_rows",
                "total_rows",
                "last_activity_utc",
                "age_s",
                "status",
            ]
        )
        writer.writerows(stuck_rows)

    args.broken_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with args.broken_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["step", "sim_run", "reason", "path"])
        writer.writerows(sorted(broken_records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
