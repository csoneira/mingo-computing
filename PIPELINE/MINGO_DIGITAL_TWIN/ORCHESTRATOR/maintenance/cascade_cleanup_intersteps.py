#!/usr/bin/env python3

"""Cascade cleanup for consumed INTERSTEPS SIM_RUN directories."""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path


def normalize_id(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    lower = text.lower()
    if lower in {"nan", "<na>", "none"}:
        return ""
    if text.endswith(".0"):
        text = text[:-2]
    try:
        return f"{int(float(text)):03d}"
    except (TypeError, ValueError):
        return text


def is_done(value: object) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    if text.lower() in {"nan", "<na>", "none"}:
        return False
    try:
        return int(float(text)) == 1
    except (TypeError, ValueError):
        return False


def parse_sim_run_ids(name: str) -> tuple[str, ...]:
    if not name.startswith("SIM_RUN_"):
        return tuple()
    raw = name[len("SIM_RUN_") :].split("_")
    out = []
    for item in raw:
        norm = normalize_id(item)
        if norm:
            out.append(norm)
    return tuple(out)


def output_dir_for_step(intersteps_dir: Path, step_num: int) -> Path:
    if step_num == 10:
        return intersteps_dir / "STEP_10_TO_FINAL"
    return intersteps_dir / f"STEP_{step_num}_TO_{step_num + 1}"


def load_pending_prefixes(mesh_path: Path) -> tuple[set[tuple[str]], set[tuple[str, str]]]:
    pending_step1: set[tuple[str]] = set()
    pending_step2: set[tuple[str, str]] = set()
    if not mesh_path.exists():
        return pending_step1, pending_step2

    with mesh_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if is_done(row.get("done")):
                continue
            step1_id = normalize_id(row.get("step_1_id"))
            step2_id = normalize_id(row.get("step_2_id"))
            if step1_id:
                pending_step1.add((step1_id,))
            if step1_id and step2_id:
                pending_step2.add((step1_id, step2_id))
    return pending_step1, pending_step2


def downstream_manifest_exists(step_num: int, sim_name: str, downstream_dir: Path) -> bool:
    manifest_name = f"step_{step_num + 1}_chunks.chunks.json"
    for candidate in downstream_dir.glob(f"{sim_name}_*"):
        if not candidate.is_dir():
            continue
        manifest = candidate / manifest_name
        if manifest.exists() and manifest.stat().st_size > 0:
            return True
    return False


def run_cleanup(intersteps_dir: Path, mesh_path: Path, dry_run: bool) -> dict[str, int]:
    pending_step1, pending_step2 = load_pending_prefixes(mesh_path)

    stats = {
        "checked": 0,
        "cleaned": 0,
        "skipped_pending": 0,
        "skipped_no_downstream": 0,
    }

    for step_num in range(1, 10):
        upstream_dir = output_dir_for_step(intersteps_dir, step_num)
        downstream_dir = output_dir_for_step(intersteps_dir, step_num + 1)
        if not upstream_dir.exists() or not downstream_dir.exists():
            continue

        for sim_dir in sorted(upstream_dir.glob("SIM_RUN_*")):
            if not sim_dir.is_dir():
                continue
            sim_name = sim_dir.name
            ids = parse_sim_run_ids(sim_name)
            if len(ids) < step_num:
                continue

            stats["checked"] += 1
            prefix = tuple(ids[:step_num])
            if step_num == 1 and prefix in pending_step1:
                stats["skipped_pending"] += 1
                continue
            if step_num == 2 and prefix in pending_step2:
                stats["skipped_pending"] += 1
                continue

            if not downstream_manifest_exists(step_num, sim_name, downstream_dir):
                stats["skipped_no_downstream"] += 1
                continue

            if not dry_run:
                shutil.rmtree(sim_dir, ignore_errors=False)
            stats["cleaned"] += 1

    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intersteps", required=True, type=Path)
    parser.add_argument("--mesh", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stats = run_cleanup(args.intersteps, args.mesh, args.dry_run)
    print(
        "checked={checked} cleaned={cleaned} skipped_pending={skipped_pending} "
        "skipped_no_downstream={skipped_no_downstream} dry_run={dry_run}".format(
            dry_run=int(args.dry_run),
            **stats,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
