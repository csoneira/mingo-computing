"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_SHARED/sim_utils_io.py
Purpose: Filesystem and dataframe I/O helpers for simulation steps.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_SHARED/sim_utils_io.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def param_mesh_lock_path(mesh_path: Path) -> Path:
    return mesh_path.with_name(".param_mesh.lock")


@contextmanager
def param_mesh_lock(mesh_path: Path):
    lock_path = param_mesh_lock_path(mesh_path)
    ensure_dir(lock_path.parent)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def write_csv_atomic(df: pd.DataFrame, path: Path, *, index: bool = False) -> None:
    ensure_dir(path.parent)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        df.to_csv(tmp_path, index=index)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def write_text_atomic(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    ensure_dir(path.parent)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        tmp_path.write_text(text, encoding=encoding)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def load_with_metadata(path: Path) -> Tuple[pd.DataFrame, Dict]:
    if path.suffix == ".pkl":
        df = pd.read_pickle(path)
        meta = df.attrs.get("metadata", {})
        meta_path = path.with_suffix(path.suffix + ".meta.json")
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
        return df, meta
    if path.suffix == ".csv":
        df = pd.read_csv(path)
        meta_path = path.with_suffix(path.suffix + ".meta.json")
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        return df, meta
    raise ValueError(f"Unsupported input format: {path.suffix}")


def iter_input_frames(path: Path, chunk_rows: Optional[int]) -> Tuple[Iterable[pd.DataFrame], Dict, bool]:
    if path.name.endswith(".chunks.json"):
        manifest_path = path
    else:
        manifest_path = path.with_suffix(".chunks.json")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        meta = manifest.get("metadata", {})
        chunk_paths = manifest.get("chunks", [])

        def _iter() -> Iterable[pd.DataFrame]:
            for chunk_path in chunk_paths:
                chunk_file = Path(chunk_path)
                try:
                    if chunk_file.suffix == ".csv":
                        yield pd.read_csv(chunk_file)
                    elif chunk_file.suffix == ".pkl":
                        yield pd.read_pickle(chunk_file)
                    else:
                        raise ValueError(f"Unsupported chunk format: {chunk_file.suffix}")
                except (FileNotFoundError, OSError) as exc:
                    # Transient cleanup/race conditions can remove chunks between
                    # manifest read and chunk open; skip and continue processing.
                    print(f"[WARN] Skipping missing/unreadable chunk {chunk_file}: {exc}")
                    continue

        return _iter(), meta, True

    if chunk_rows and path.suffix == ".csv":
        meta_path = path.with_suffix(path.suffix + ".meta.json")
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        return pd.read_csv(path, chunksize=int(chunk_rows)), meta, True

    df, meta = load_with_metadata(path)
    return [df], meta, False


def find_latest_data_path(root_dir: Path) -> Optional[Path]:
    """Return the most recently modified data file under root_dir."""
    candidates = list(root_dir.rglob("*.pkl"))
    if candidates:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    candidates = list(root_dir.rglob("*.csv"))
    if candidates:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    return None


def find_sim_run_dir(path: Path) -> Optional[Path]:
    """Return the nearest SIM_RUN_* parent directory for a given path."""
    for parent in path.parents:
        if parent.name.startswith("SIM_RUN_"):
            return parent
    return None


def write_chunked_output(
    df_iter: Iterable[pd.DataFrame],
    output_dir: Path,
    out_stem: str,
    output_format: str,
    chunk_rows: int,
    metadata: Dict,
) -> Tuple[Path, Optional[pd.DataFrame], int]:
    chunks_dir_name = out_stem if out_stem.endswith("_chunks") else f"{out_stem}_chunks"
    chunks_dir = output_dir / chunks_dir_name
    ensure_dir(chunks_dir)

    chunk_paths: List[str] = []
    buffer: List[pd.DataFrame] = []
    buffered_rows = 0
    full_chunks = 0
    last_chunk: Optional[pd.DataFrame] = None

    def flush_chunk(chunk_df: pd.DataFrame) -> None:
        nonlocal full_chunks, last_chunk
        chunk_path = chunks_dir / f"part_{full_chunks:04d}.{output_format}"
        if output_format == "csv":
            chunk_df.to_csv(chunk_path, index=False)
        elif output_format == "pkl":
            chunk_df.to_pickle(chunk_path)
        else:
            raise ValueError(f"Unsupported output_format: {output_format}")
        chunk_paths.append(str(chunk_path))
        full_chunks += 1
        last_chunk = chunk_df

    def maybe_flush_buffer() -> None:
        nonlocal buffer, buffered_rows
        while buffered_rows >= chunk_rows:
            chunk_df = pd.concat(buffer, ignore_index=True)
            out_df = chunk_df.iloc[:chunk_rows].copy()
            remainder = chunk_df.iloc[chunk_rows:].copy()
            flush_chunk(out_df)
            buffer = [remainder] if not remainder.empty else []
            buffered_rows = len(remainder)

    total_rows = 0
    for df in df_iter:
        if df.empty:
            continue
        total_rows += len(df)
        buffer.append(df)
        buffered_rows += len(df)
        maybe_flush_buffer()

    if buffered_rows > 0:
        flush_chunk(pd.concat(buffer, ignore_index=True))
        buffered_rows = 0
        buffer = []

    row_count = total_rows
    manifest = {
        "version": 1,
        "chunks": chunk_paths,
        "row_count": row_count,
        "metadata": metadata,
    }
    manifest_path = output_dir / f"{out_stem}.chunks.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest_path, last_chunk, row_count


def save_with_metadata(df: pd.DataFrame, path: Path, metadata: Dict, output_format: str) -> None:
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    meta_path.write_text(json.dumps(metadata, indent=2))
    if output_format == "pkl":
        df.attrs["metadata"] = metadata
        df.to_pickle(path)
    elif output_format == "csv":
        df.to_csv(path, index=False)
    else:
        raise ValueError(f"Unsupported output_format: {output_format}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    ensure_dir(path)
