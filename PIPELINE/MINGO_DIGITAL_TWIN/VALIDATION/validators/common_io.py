#!/usr/bin/env python3

"""Read-only I/O helpers for validation workflows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

STEP_TO_INTERSTEP = {
    "1": "STEP_1_TO_2",
    "2": "STEP_2_TO_3",
    "3": "STEP_3_TO_4",
    "4": "STEP_4_TO_5",
    "5": "STEP_5_TO_6",
    "6": "STEP_6_TO_7",
    "7": "STEP_7_TO_8",
    "8": "STEP_8_TO_9",
    "9": "STEP_9_TO_10",
    "10": "STEP_10_TO_FINAL",
}


@dataclass
class StepArtifact:
    key: str
    step_name: str
    interstep_dir: Path
    run_dir: Path | None
    data_path: Path | None
    manifest_path: Path | None
    metadata: dict[str, Any]
    sim_run: str | None
    config_hash: str | None
    upstream_hash: str | None
    row_count: int | None

    @property
    def exists(self) -> bool:
        return self.data_path is not None and self.data_path.exists()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def resolve_manifest_chunk_path(raw_path: str, manifest_path: Path) -> Path:
    raw = Path(raw_path)
    if raw.exists():
        return raw.resolve()

    by_manifest_parent = (manifest_path.parent / raw).resolve()
    if by_manifest_parent.exists():
        return by_manifest_parent

    by_name_under_run = (manifest_path.parent / raw.name).resolve()
    if by_name_under_run.exists():
        return by_name_under_run

    return raw.resolve()


def list_sim_run_dirs(step_dir: Path) -> list[Path]:
    if not step_dir.exists():
        return []
    runs = [p for p in step_dir.iterdir() if p.is_dir() and p.name.startswith("SIM_RUN_")]
    return sorted(runs, key=lambda p: p.stat().st_mtime)


def choose_run_dir(run_dirs: list[Path], sim_run_filter: str | None) -> Path | None:
    if not run_dirs:
        return None
    if not sim_run_filter:
        return run_dirs[-1]

    exact = [p for p in run_dirs if p.name == sim_run_filter]
    if exact:
        return sorted(exact, key=lambda p: p.stat().st_mtime)[-1]

    contains = [p for p in run_dirs if sim_run_filter in p.name]
    if contains:
        return sorted(contains, key=lambda p: p.stat().st_mtime)[-1]

    return None


def _data_candidates(run_dir: Path) -> tuple[list[Path], list[Path]]:
    manifests = sorted(run_dir.glob("*.chunks.json"), key=lambda p: p.stat().st_mtime)
    files = sorted(
        [
            p
            for p in run_dir.glob("*")
            if p.is_file() and p.suffix in {".pkl", ".csv"} and not p.name.endswith(".meta.json")
        ],
        key=lambda p: p.stat().st_mtime,
    )
    return manifests, files


def find_dataset_in_run(run_dir: Path | None, step_key: str | None = None) -> tuple[Path | None, Path | None]:
    if run_dir is None or not run_dir.exists():
        return None, None

    manifests, files = _data_candidates(run_dir)
    if manifests:
        if step_key == "1":
            preferred = [p for p in manifests if p.name.startswith("muon_sample_")]
            if preferred:
                chosen = preferred[-1]
                return chosen, chosen
        if step_key in {"2", "3", "4", "5", "6", "7", "8", "9", "10"}:
            pref_token = f"step_{step_key}_chunks.chunks.json" if step_key != "10" else "step_10_chunks.chunks.json"
            preferred = [p for p in manifests if p.name == pref_token]
            if preferred:
                chosen = preferred[-1]
                return chosen, chosen
        chosen = manifests[-1]
        return chosen, chosen

    if files:
        return files[-1], None

    return None, None


def get_metadata_for_data_path(data_path: Path | None) -> dict[str, Any]:
    if data_path is None or not data_path.exists():
        return {}

    if data_path.name.endswith(".chunks.json"):
        manifest = read_json(data_path)
        return manifest.get("metadata", {})

    meta_path = data_path.with_suffix(data_path.suffix + ".meta.json")
    if meta_path.exists():
        return read_json(meta_path)

    return {}


def get_manifest_row_count(manifest_path: Path | None) -> int | None:
    if manifest_path is None or not manifest_path.exists():
        return None
    try:
        manifest = read_json(manifest_path)
    except Exception:
        return None
    row_count = manifest.get("row_count")
    if row_count is None:
        return None
    try:
        return int(row_count)
    except (TypeError, ValueError):
        return None


def load_registry(step_dir: Path) -> dict[str, Any]:
    reg = step_dir / "sim_run_registry.json"
    if not reg.exists():
        return {"version": 1, "runs": []}
    return read_json(reg)


def find_registry_entry(step_dir: Path, sim_run: str | None) -> dict[str, Any] | None:
    if not sim_run:
        return None
    registry = load_registry(step_dir)
    for entry in registry.get("runs", []):
        if entry.get("sim_run") == sim_run:
            return entry
    return None


def discover_step_artifacts(intersteps_dir: Path, sim_run_filter: str | None = None) -> dict[str, StepArtifact]:
    artifacts: dict[str, StepArtifact] = {}

    # STEP 0: parameter mesh
    step0_dir = intersteps_dir / "STEP_0_TO_1"
    mesh_path = step0_dir / "param_mesh.csv"
    mesh_meta_path = step0_dir / "param_mesh_metadata.json"
    mesh_meta = read_json(mesh_meta_path) if mesh_meta_path.exists() else {}
    artifacts["0"] = StepArtifact(
        key="0",
        step_name="STEP_0",
        interstep_dir=step0_dir,
        run_dir=None,
        data_path=mesh_path if mesh_path.exists() else None,
        manifest_path=None,
        metadata=mesh_meta,
        sim_run=None,
        config_hash=mesh_meta.get("config_hash"),
        upstream_hash=mesh_meta.get("upstream_hash"),
        row_count=None,
    )

    for step_key, inter_name in STEP_TO_INTERSTEP.items():
        step_dir = intersteps_dir / inter_name
        run_dirs = list_sim_run_dirs(step_dir)
        run_dir = choose_run_dir(run_dirs, sim_run_filter)
        data_path, manifest_path = find_dataset_in_run(run_dir, step_key)
        metadata = get_metadata_for_data_path(data_path)

        sim_run = run_dir.name if run_dir else None
        config_hash = metadata.get("config_hash")
        upstream_hash = metadata.get("upstream_hash")
        row_count = get_manifest_row_count(manifest_path)

        if (not config_hash or not upstream_hash) and sim_run:
            entry = find_registry_entry(step_dir, sim_run)
            if entry:
                config_hash = config_hash or entry.get("config_hash")
                upstream_hash = upstream_hash or entry.get("upstream_hash")

        artifacts[step_key] = StepArtifact(
            key=step_key,
            step_name=f"STEP_{step_key}",
            interstep_dir=step_dir,
            run_dir=run_dir,
            data_path=data_path,
            manifest_path=manifest_path,
            metadata=metadata,
            sim_run=sim_run,
            config_hash=config_hash,
            upstream_hash=upstream_hash,
            row_count=row_count,
        )

    return artifacts


def iter_frames(data_path: Path | None, columns: list[str] | None = None) -> Iterable[pd.DataFrame]:
    if data_path is None or not data_path.exists():
        return []

    if data_path.name.endswith(".chunks.json"):
        manifest = read_json(data_path)
        chunks = manifest.get("chunks", [])

        def _iter() -> Iterable[pd.DataFrame]:
            for raw_chunk in chunks:
                chunk_path = resolve_manifest_chunk_path(str(raw_chunk), data_path)
                if not chunk_path.exists():
                    continue
                if chunk_path.suffix == ".pkl":
                    df = pd.read_pickle(chunk_path)
                    if columns:
                        use_cols = [c for c in columns if c in df.columns]
                        df = df[use_cols].copy()
                    yield df
                elif chunk_path.suffix == ".csv":
                    if columns:
                        yield pd.read_csv(chunk_path, usecols=lambda c: c in set(columns))
                    else:
                        yield pd.read_csv(chunk_path)
                else:
                    continue

        return _iter()

    if data_path.suffix == ".pkl":
        df = pd.read_pickle(data_path)
        if columns:
            use_cols = [c for c in columns if c in df.columns]
            df = df[use_cols].copy()
        return [df]

    if data_path.suffix == ".csv":
        if columns:
            return [pd.read_csv(data_path, usecols=lambda c: c in set(columns))]
        return [pd.read_csv(data_path)]

    return []


def load_frame(
    data_path: Path | None,
    columns: list[str] | None = None,
    max_rows: int | None = None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    total = 0
    for frame in iter_frames(data_path, columns=columns):
        if frame is None or frame.empty:
            continue
        if max_rows is not None:
            remaining = max_rows - total
            if remaining <= 0:
                break
            if len(frame) > remaining:
                frame = frame.iloc[:remaining].copy()
        frames.append(frame)
        total += len(frame)
        if max_rows is not None and total >= max_rows:
            break

    if not frames:
        return pd.DataFrame(columns=columns or [])
    return pd.concat(frames, ignore_index=True)


def compute_exact_manifest_count(
    manifest_path: Path | None,
    *,
    max_rows_to_scan: int = 2_000_000,
) -> tuple[int | None, str]:
    """Return (count, note). count is None when skipped or unavailable."""
    if manifest_path is None or not manifest_path.exists():
        return None, "no_manifest"

    manifest = read_json(manifest_path)
    declared = manifest.get("row_count")
    chunks = manifest.get("chunks", [])
    if not chunks:
        return 0, "empty_chunks"

    if declared is not None:
        try:
            declared_int = int(declared)
        except (TypeError, ValueError):
            declared_int = None
    else:
        declared_int = None

    if declared_int is not None and declared_int > max_rows_to_scan:
        return None, "skipped_large_manifest"

    total = 0
    for raw_chunk in chunks:
        chunk_path = resolve_manifest_chunk_path(str(raw_chunk), manifest_path)
        if not chunk_path.exists():
            return None, f"missing_chunk:{chunk_path}"
        if chunk_path.suffix == ".pkl":
            total += len(pd.read_pickle(chunk_path))
        elif chunk_path.suffix == ".csv":
            with chunk_path.open("r", encoding="utf-8", errors="replace") as fh:
                line_count = sum(1 for _ in fh)
            total += max(line_count - 1, 0)
        else:
            return None, f"unsupported_chunk:{chunk_path.suffix}"

    return total, "exact_count"


def resolve_source_dataset_path(meta: dict[str, Any], base_dir: Path | None = None) -> Path | None:
    raw = meta.get("source_dataset")
    if raw is None:
        return None
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw is None:
        return None
    path = Path(str(raw))
    if path.exists():
        return path.resolve()
    if base_dir is not None:
        alt = (base_dir / path).resolve()
        if alt.exists():
            return alt
        alt2 = (base_dir / path.name).resolve()
        if alt2.exists():
            return alt2
    return path


def get_nested_upstream(meta: dict[str, Any], level: int = 1) -> dict[str, Any] | None:
    current = meta
    for _ in range(level):
        if not isinstance(current, dict):
            return None
        current = current.get("upstream")
    return current if isinstance(current, dict) else None


def find_config_in_chain(meta: dict[str, Any], step_name: str) -> dict[str, Any] | None:
    current = meta
    while isinstance(current, dict):
        if current.get("step") == step_name:
            cfg = current.get("config")
            return cfg if isinstance(cfg, dict) else None
        current = current.get("upstream")
    return None


def find_step_id_chain(meta: dict[str, Any]) -> list[str]:
    ids: dict[int, str] = {}
    current: Any = meta
    while isinstance(current, dict):
        for idx in range(1, 11):
            key = f"step_{idx}_id"
            if key in current and idx not in ids and current.get(key) not in (None, ""):
                ids[idx] = str(current.get(key))
        current = current.get("upstream")
    return [ids[i] for i in sorted(ids)]


def summarize_artifacts(artifacts: dict[str, StepArtifact]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, art in artifacts.items():
        out[key] = {
            "step_name": art.step_name,
            "interstep_dir": str(art.interstep_dir),
            "run_dir": str(art.run_dir) if art.run_dir else None,
            "data_path": str(art.data_path) if art.data_path else None,
            "manifest_path": str(art.manifest_path) if art.manifest_path else None,
            "sim_run": art.sim_run,
            "config_hash": art.config_hash,
            "upstream_hash": art.upstream_hash,
            "row_count": art.row_count,
            "has_metadata": bool(art.metadata),
        }
    return out


def list_dat_files(simulated_data_dir: Path, max_files: int | None = None) -> list[Path]:
    files: list[Path] = []
    seen_names: set[str] = set()
    candidate_dirs = [simulated_data_dir / "FILES", simulated_data_dir]
    for directory in candidate_dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("mi*.dat")):
            if not path.is_file():
                continue
            if path.name in seen_names:
                continue
            seen_names.add(path.name)
            files.append(path)
    files.sort(key=lambda p: p.stat().st_mtime)
    if max_files is None:
        return files
    return files[-max_files:]


def parse_dat_data_lines(dat_path: Path, max_rows: int | None = None) -> tuple[str | None, list[str]]:
    param_hash: str | None = None
    lines: list[str] = []
    with dat_path.open("r", encoding="ascii", errors="replace") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                if stripped.lower().startswith("# param_hash="):
                    param_hash = stripped.split("=", 1)[1].strip()
                continue
            lines.append(stripped)
            if max_rows is not None and len(lines) >= max_rows:
                break
    return param_hash, lines
