"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_SHARED/sim_utils_registry.py
Purpose: SIM_RUN registry helpers and deterministic run selection utilities.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_SHARED/sim_utils_registry.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import sys
import tempfile
from typing import Dict, Optional, Tuple

import pandas as pd

from .sim_utils_io import now_iso


def _json_fingerprint(payload: Dict) -> str:
    payload_json = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _upstream_fingerprint(upstream_meta: Optional[Dict]) -> Optional[str]:
    if upstream_meta is None:
        return None
    if isinstance(upstream_meta, dict):
        return _json_fingerprint(
            {
                "step": upstream_meta.get("step"),
                "config_hash": upstream_meta.get("config_hash"),
                "upstream_hash": upstream_meta.get("upstream_hash"),
            }
        )
    return _json_fingerprint({"upstream_meta": upstream_meta})


def _recover_complete_registry_entries(text: str) -> list[Dict]:
    """Recover complete objects from a truncated top-level runs array."""
    runs_key = text.find('"runs"')
    array_start = text.find("[", runs_key)
    if runs_key < 0 or array_start < 0:
        return []

    decoder = json.JSONDecoder()
    entries: list[Dict] = []
    cursor = array_start + 1
    while cursor < len(text):
        while cursor < len(text) and (text[cursor].isspace() or text[cursor] == ","):
            cursor += 1
        if cursor >= len(text) or text[cursor] == "]":
            break
        try:
            entry, cursor = decoder.raw_decode(text, cursor)
        except json.JSONDecodeError:
            break
        if not isinstance(entry, dict):
            break
        entries.append(entry)
    return entries


def load_sim_run_registry(output_dir: Path) -> Dict:
    registry_path = output_dir / "sim_run_registry.json"
    if registry_path.exists():
        text = registry_path.read_text(encoding="utf-8")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            recovered_runs = _recover_complete_registry_entries(text)
            if not recovered_runs:
                raise
            stamp = now_iso().replace(":", "").replace("+", "_")
            quarantine_path = registry_path.with_name(
                f"{registry_path.name}.corrupt.{stamp}"
            )
            shutil.copy2(registry_path, quarantine_path)
            recovered = {"version": 1, "runs": recovered_runs}
            save_sim_run_registry(output_dir, recovered)
            print(
                "Recovered truncated simulation registry "
                f"{registry_path}: entries={len(recovered_runs)}, "
                f"backup={quarantine_path}, error={exc}",
                file=sys.stderr,
            )
            return recovered
    return {"version": 1, "runs": []}


def save_sim_run_registry(output_dir: Path, registry: Dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    registry_path = output_dir / "sim_run_registry.json"
    temporary_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output_dir,
            prefix=f".{registry_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(registry, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, registry_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def resolve_sim_run(
    output_dir: Path,
    step: str,
    config_path: Path,
    cfg: Dict,
    upstream_meta: Optional[Dict],
) -> Tuple[str, Path, str, Optional[str], Dict]:
    config_hash = _json_fingerprint(cfg)
    upstream_hash = _upstream_fingerprint(upstream_meta)
    registry = load_sim_run_registry(output_dir)

    for entry in registry.get("runs", []):
        if (
            entry.get("config_hash") == config_hash
            and entry.get("upstream_hash") == upstream_hash
        ):
            sim_run = entry["sim_run"]
            return sim_run, output_dir / sim_run, config_hash, upstream_hash, registry

    existing = [entry.get("sim_run", "") for entry in registry.get("runs", [])]
    max_id = 0
    for run_id in existing:
        if run_id.startswith("SIM_RUN_"):
            try:
                max_id = max(max_id, int(run_id.split("_")[-1]))
            except ValueError:
                continue
    next_id = max_id + 1
    sim_run = f"SIM_RUN_{next_id:04d}"
    registry.setdefault("runs", []).append(
        {
            "sim_run": sim_run,
            "created_at": now_iso(),
            "step": step,
            "config_path": str(config_path),
            "config_hash": config_hash,
            "upstream_hash": upstream_hash,
            "config": cfg,
        }
    )
    save_sim_run_registry(output_dir, registry)
    return sim_run, output_dir / sim_run, config_hash, upstream_hash, registry


def register_sim_run(
    output_dir: Path,
    step: str,
    config_path: Path,
    cfg: Dict,
    upstream_meta: Optional[Dict],
    sim_run: str,
) -> Tuple[str, Path, str, Optional[str], Dict]:
    config_hash = _json_fingerprint(cfg)
    upstream_hash = _upstream_fingerprint(upstream_meta)
    registry = load_sim_run_registry(output_dir)
    for entry in registry.get("runs", []):
        if entry.get("sim_run") == sim_run:
            return sim_run, output_dir / sim_run, config_hash, upstream_hash, registry
    registry.setdefault("runs", []).append(
        {
            "sim_run": sim_run,
            "created_at": now_iso(),
            "step": step,
            "config_path": str(config_path),
            "config_hash": config_hash,
            "upstream_hash": upstream_hash,
            "config": cfg,
        }
    )
    save_sim_run_registry(output_dir, registry)
    return sim_run, output_dir / sim_run, config_hash, upstream_hash, registry


def find_sim_run(output_dir: Path, cfg: Dict, upstream_meta: Optional[Dict]) -> Optional[str]:
    config_hash = _json_fingerprint(cfg)
    upstream_hash = _upstream_fingerprint(upstream_meta)
    registry = load_sim_run_registry(output_dir)
    for entry in registry.get("runs", []):
        if (
            entry.get("config_hash") == config_hash
            and entry.get("upstream_hash") == upstream_hash
        ):
            sim_run = entry.get("sim_run")
            if sim_run and (output_dir / sim_run).exists():
                return sim_run
    return None


def latest_sim_run(output_dir: Path) -> str:
    registry_path = output_dir / "sim_run_registry.json"
    if not registry_path.exists():
        raise FileNotFoundError("sim_run_registry.json not found in input_dir.")
    registry = json.loads(registry_path.read_text())
    runs = registry.get("runs", [])
    if not runs:
        raise FileNotFoundError("No SIM_RUN entries found in input_dir registry.")
    runs_sorted = sorted(runs, key=lambda r: r.get("created_at", ""))
    return runs_sorted[-1]["sim_run"]


def random_sim_run(output_dir: Path, seed: Optional[int] = None) -> str:
    registry_path = output_dir / "sim_run_registry.json"
    if not registry_path.exists():
        raise FileNotFoundError("sim_run_registry.json not found in input_dir.")
    registry = json.loads(registry_path.read_text())
    runs = [
        entry.get("sim_run")
        for entry in registry.get("runs", [])
        if entry.get("sim_run")
    ]
    if not runs:
        raise FileNotFoundError("No SIM_RUN entries found in input_dir registry.")
    runs_sorted = sorted(runs)
    rng = random.Random(seed)
    return rng.choice(runs_sorted)


def resolve_sim_run_name(base_dir: Path, sim_run: str, seed: Optional[int] = None) -> str:
    if sim_run == "latest":
        return latest_sim_run(base_dir)
    if sim_run == "random":
        return random_sim_run(base_dir, seed)
    return str(sim_run)


def load_parameter_mesh(
    base_dir: Path,
    sim_run: str,
    seed: Optional[int] = None,
) -> Tuple[pd.DataFrame, Path, str]:
    resolved_sim_run = resolve_sim_run_name(base_dir, sim_run, seed)
    mesh_dir = base_dir / resolved_sim_run
    mesh_path = mesh_dir / "param_mesh.csv"
    if not mesh_path.exists():
        alt_path = mesh_dir / "parameter_mesh.csv"
        if alt_path.exists():
            mesh_path = alt_path
        else:
            raise FileNotFoundError(f"param_mesh.csv not found in {mesh_dir}")
    mesh_df = pd.read_csv(mesh_path)
    return mesh_df, mesh_dir, resolved_sim_run
