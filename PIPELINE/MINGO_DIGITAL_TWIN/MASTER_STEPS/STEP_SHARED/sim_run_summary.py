#!/usr/bin/env python3

"""Summarize SIM_RUN registries under INTERSTEPS and report row counts."""

import argparse
import json
from pathlib import Path


def summarize_step(step_dir: Path) -> list[dict]:
    registry_path = step_dir / "sim_run_registry.json"
    if not registry_path.exists():
        return []
    registry = json.loads(registry_path.read_text())
    entries = []
    for run in registry.get("runs", []):
        sim_run = run.get("sim_run")
        if not sim_run:
            continue
        run_dir = step_dir / sim_run
        total_rows = 0
        chunk_manifests = list(run_dir.glob("*.chunks.json"))
        if chunk_manifests:
            for manifest_path in chunk_manifests:
                manifest = json.loads(manifest_path.read_text())
                total_rows += int(manifest.get("row_count", 0))
        else:
            meta_files = list(run_dir.glob("*.meta.json"))
            for meta_path in meta_files:
                meta = json.loads(meta_path.read_text())
                row_count = meta.get("row_count")
                if row_count is None:
                    continue
                total_rows += int(row_count)
        entries.append(
            {
                "sim_run": sim_run,
                "rows": total_rows,
                "config_hash": run.get("config_hash"),
                "upstream_hash": run.get("upstream_hash"),
                "created_at": run.get("created_at"),
            }
        )
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize sim runs and row counts.")
    parser.add_argument(
        "--root",
        default=".",
        help="MINGO_DIGITAL_TWIN root directory",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    intersteps = root / "SIMULATION_OUTPUTS" / "INTERSTEPS"
    if not intersteps.exists():
        raise FileNotFoundError(f"INTERSTEPS not found under {root}")

    print("step,sim_run,rows,created_at,config_hash,upstream_hash")
    for step_dir in sorted(intersteps.glob("STEP_*_TO_*")):
        entries = summarize_step(step_dir)
        for entry in entries:
            print(
                f"{step_dir.name},{entry['sim_run']},{entry['rows']},"
                f"{entry.get('created_at','')},{entry.get('config_hash','')},"
                f"{entry.get('upstream_hash','')}"
            )


if __name__ == "__main__":
    main()
