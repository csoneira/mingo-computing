
"""Provide shared helpers for loading simulated event data."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Optional, Tuple, List

import pandas as pd

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root


DATAFLOW_ROOT = get_repo_root()

SIM_PARAMS_DEFAULT = DATAFLOW_ROOT / "PIPELINE" / "MINGO_DIGITAL_TWIN" / "SIMULATION_OUTPUTS" / "SIMULATED_DATA" / "step_final_simulation_params.csv"

SIM_DATA_DIR = DATAFLOW_ROOT / "PIPELINE" / "MINGO_DIGITAL_TWIN" / "SIMULATION_OUTPUTS" / "SIMULATED_DATA"
SIM_DATA_FILES_DIR = SIM_DATA_DIR / "FILES"


@lru_cache(maxsize=16)
def _read_sim_params_csv_cached(path_text: str, mtime_ns: int, size: int) -> pd.DataFrame:
    """Read simulation parameters CSV and cache by path + file identity."""
    return pd.read_csv(path_text)


def _load_sim_params_df(sim_params_path: Path) -> Optional[pd.DataFrame]:
    path = Path(sim_params_path)
    if not path.exists():
        return None
    stat = path.stat()
    return _read_sim_params_csv_cached(str(path), stat.st_mtime_ns, stat.st_size)


def _normalize_param_hash(value: object) -> Optional[str]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    return text or None


def extract_param_hash_from_dat(dat_path: Path) -> Optional[str]:
    try:
        with dat_path.open("r", encoding="ascii") as handle:
            first_line = handle.readline().strip()
    except FileNotFoundError:
        return None

    if not first_line.startswith("#"):
        return None
    if first_line.startswith("# param_hash="):
        value = first_line.split("=", 1)[1].strip()
        return value or None
    return None


def find_simulated_dat_path(basename_no_ext: str, base_directory: Path) -> Optional[Path]:
    filename = f"{basename_no_ext}.dat"
    candidate_dirs = [
        base_directory / "STEP_1" / "TASK_1" / "INPUT_FILES" / "COMPLETED_DIRECTORY",
        base_directory / "STEP_1" / "TASK_1" / "INPUT_FILES" / "PROCESSING_DIRECTORY",
        base_directory / "STEP_1" / "TASK_1" / "INPUT_FILES" / "UNPROCESSED_DIRECTORY",
        base_directory / "STAGE_0_TO_1",
        SIM_DATA_FILES_DIR,
        SIM_DATA_DIR,
    ]
    for directory in candidate_dirs:
        candidate = directory / filename
        if candidate.exists():
            return candidate
    return None


def extract_param_hash_from_parquet(parquet_path: Path) -> Optional[str]:
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return None
    try:
        parquet = pq.ParquetFile(parquet_path)
    except Exception:
        return None
    if parquet.metadata is None or parquet.metadata.num_row_groups == 0:
        return None
    if "param_hash" not in parquet.schema.names:
        return None
    for row_group in range(parquet.metadata.num_row_groups):
        try:
            table = parquet.read_row_group(row_group, columns=["param_hash"])
        except Exception:
            continue
        values = table.column("param_hash").to_pylist()
        for value in values:
            normalized = _normalize_param_hash(value)
            if normalized:
                return normalized
    return None


def load_simulated_z_positions(
    param_hash: str,
    sim_params_path: Path = SIM_PARAMS_DEFAULT,
) -> Optional[List[float]]:
    sim_params = _load_sim_params_df(sim_params_path)
    if sim_params is None:
        return None
    if "param_hash" not in sim_params.columns:
        return None
    matches = sim_params[sim_params["param_hash"] == param_hash]
    if matches.empty:
        return None
    row = matches.iloc[0]
    try:
        return [
            float(row["z_plane_1"]),
            float(row["z_plane_2"]),
            float(row["z_plane_3"]),
            float(row["z_plane_4"]),
        ]
    except (KeyError, TypeError, ValueError):
        return None


def load_simulated_efficiencies(
    param_hash: str,
    sim_params_path: Path = SIM_PARAMS_DEFAULT,
) -> Optional[List[float]]:
    sim_params = _load_sim_params_df(sim_params_path)
    if sim_params is None:
        return None
    if "param_hash" not in sim_params.columns or "efficiencies" not in sim_params.columns:
        return None
    matches = sim_params[sim_params["param_hash"] == param_hash]
    if matches.empty:
        return None
    row = matches.iloc[0]
    raw_efficiencies = row.get("efficiencies")
    if raw_efficiencies is None:
        return None
    if isinstance(raw_efficiencies, str):
        try:
            parsed = json.loads(raw_efficiencies)
        except json.JSONDecodeError:
            return None
    elif isinstance(raw_efficiencies, (list, tuple)):
        parsed = list(raw_efficiencies)
    else:
        return None
    if len(parsed) < 4:
        return None
    out: List[float] = []
    for value in parsed[:4]:
        try:
            out.append(float(value))
        except (TypeError, ValueError):
            return None
    return out


def load_simulated_z_positions_for_file(
    basename_no_ext: str,
    sim_params_path: Path = SIM_PARAMS_DEFAULT,
) -> Tuple[Optional[List[float]], Optional[str]]:
    sim_params = _load_sim_params_df(sim_params_path)
    if sim_params is None:
        return None, None
    if "file_name" not in sim_params.columns:
        return None, None
    file_name = basename_no_ext if basename_no_ext.endswith(".dat") else f"{basename_no_ext}.dat"
    matches = sim_params[sim_params["file_name"] == file_name]
    if matches.empty:
        return None, None
    row = matches.iloc[0]
    param_hash = _normalize_param_hash(row.get("param_hash"))
    try:
        z_positions = [
            float(row["z_plane_1"]),
            float(row["z_plane_2"]),
            float(row["z_plane_3"]),
            float(row["z_plane_4"]),
        ]
    except (KeyError, TypeError, ValueError):
        return None, param_hash
    return z_positions, param_hash


def resolve_simulated_z_positions(
    basename_no_ext: str,
    base_directory: Path,
    sim_params_path: Optional[Path] = None,
    dat_path: Optional[Path] = None,
    parquet_path: Optional[Path] = None,
    param_hash: Optional[str] = None,
) -> Tuple[Optional[List[float]], Optional[str]]:
    if not basename_no_ext.startswith("mi00"):
        return None, None
    if sim_params_path is None:
        sim_params_path = SIM_PARAMS_DEFAULT

    best_hash: Optional[str] = None

    param_hash = _normalize_param_hash(param_hash)
    if param_hash is None and parquet_path is not None:
        param_hash = extract_param_hash_from_parquet(parquet_path)

    if param_hash:
        best_hash = param_hash
        z_positions = load_simulated_z_positions(param_hash, sim_params_path)
        if z_positions is not None:
            return z_positions, param_hash
        # Hash found but no matching CSV row — fall through to file_name lookup.

    if best_hash is None:
        if dat_path is None:
            dat_path = find_simulated_dat_path(basename_no_ext, base_directory)
        if dat_path is not None:
            dat_hash = _normalize_param_hash(extract_param_hash_from_dat(dat_path))
            if dat_hash:
                best_hash = dat_hash
                z_positions = load_simulated_z_positions(dat_hash, sim_params_path)
                if z_positions is not None:
                    return z_positions, dat_hash
                # Hash found but no matching CSV row — fall through.

    # Fallback: look up by file_name in the simulation params CSV.
    z_positions, fallback_hash = load_simulated_z_positions_for_file(
        basename_no_ext,
        sim_params_path,
    )
    resolved_hash = best_hash or _normalize_param_hash(fallback_hash)
    if z_positions is not None:
        return z_positions, resolved_hash
    if resolved_hash:
        return None, resolved_hash
    return None, None
