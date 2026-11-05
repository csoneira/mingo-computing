#!/usr/bin/env python3
"""Reusable FILEvFILE pairing logic for simulation-vs-data validation.

This module implements the common matching model described in the project
README:

1. Filter simulation rows from ``step_final_simulation_params.csv`` using:
   - range filters on ``cos_n`` and ``flux_cm2_min``
   - exact match on ``z_plane_1..4``
   - exact match on ``trigger_combinations``
   - range filter on the simulated efficiency vector
2. Join the filtered simulation rows to MINGO00 Task-4 robust-efficiency
   metadata through ``param_hash``.
3. Read the study-station Task-4 robust-efficiency metadata and its matching
   geometry metadata.
4. Restrict both stations to files that are actually present in the completed
   input directory corresponding to the requested task.
5. Build FILEvFILE candidates by nearest-neighbour matching in
   ``eff[1-4]_robust_xyphi`` space and keep only candidates below a configured
   Euclidean-distance threshold.

The output is one reproducible random pair that downstream scripts can analyse
file-by-file.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.path_config import get_repo_root


DATAFLOW_ROOT = get_repo_root()
STATIONS_BASE = DATAFLOW_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
SIMULATION_PARAMS_CSV = DATAFLOW_ROOT / "PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv"
EFF_COLS = [
    "P1_eff_robust_xyphi",
    "P2_eff_robust_xyphi",
    "P3_eff_robust_xyphi",
    "P4_eff_robust_xyphi",
]
SIM_EFF_COLS = ["eff_p1", "eff_p2", "eff_p3", "eff_p4"]
Z_COLS = ["P1_z", "P2_z", "P3_z", "P4_z"]
SIM_Z_COLS = ["z_plane_1", "z_plane_2", "z_plane_3", "z_plane_4"]
FILENAME_TIMESTAMP_PATTERN = re.compile(r"mi0\d(\d{11})$", re.IGNORECASE)


@dataclass(frozen=True)
class FilePairSelection:
    task_id: int
    station_of_study: int
    station_of_study_label: str
    study_filename_base: str
    reference_filename_base: str
    study_file_path: str
    reference_file_path: str
    z_tuple: tuple[int | float, int | float, int | float, int | float]
    eff_distance: float
    study_efficiencies: tuple[float, float, float, float]
    reference_efficiencies: tuple[float, float, float, float]
    reference_param_hash: str
    sim_cos_n: float | None
    sim_flux_cm2_min: float | None
    sim_trigger_combinations: list[str]
    sim_efficiencies: tuple[float, float, float, float]
    random_seed: int
    candidate_pair_count: int


def load_json_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["_config_path"] = str(config_path)
    config["_config_dir"] = str(config_path.parent)
    return config


def execution_output_timestamp(config: dict[str, Any]) -> str:
    stamp = config.get("_output_run_timestamp")
    if isinstance(stamp, str) and stamp:
        return stamp
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    config["_output_run_timestamp"] = stamp
    return stamp


def resolve_timestamped_pair_output_dir(config: dict[str, Any], selection: FilePairSelection) -> Path:
    raw = str(config.get("output_dir", "OUTPUTS"))
    base = Path(raw)
    if not base.is_absolute():
        base = (Path(config["_config_dir"]) / base).resolve()
    pair_dir = (
        f"{selection.station_of_study_label.lower()}_{execution_output_timestamp(config)}_"
        f"{selection.study_filename_base}__vs__{selection.reference_filename_base}"
    )
    out_dir = base / pair_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def station_root(station: int) -> Path:
    return STATIONS_BASE / f"MINGO{station:02d}" / "STAGE_1/EVENT_DATA/STEP_1"


def task4_metadata_file(station: int) -> Path:
    return station_root(station) / "TASK_4/METADATA/task_4_metadata_robust_efficiency.csv"


def task5_specific_metadata_file(station: int) -> Path:
    return station_root(station) / "TASK_5/METADATA/task_5_metadata_specific.csv"


def task_input_completed_directory(station: int, task_id: int) -> Path:
    return station_root(station) / f"TASK_{task_id + 1}/INPUT_FILES/COMPLETED_DIRECTORY"


def parse_station_id(raw: object) -> int:
    text = str(raw).strip().upper()
    match = re.fullmatch(r"MINGO(\d{1,2})", text)
    if match is not None:
        return int(match.group(1))
    return int(text)


def format_station_label(station_id: int) -> str:
    return f"MINGO{int(station_id):02d}"


def canonical_z(value: object) -> int | float:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        raise ValueError("NaN found in z position column")
    numeric = float(numeric)
    return int(numeric) if numeric.is_integer() else numeric


def parse_execution_timestamp_series(series: pd.Series) -> pd.Series:
    text = series.astype("string")
    parsed = pd.to_datetime(text, format="%Y-%m-%d_%H.%M.%S", errors="coerce", utc=True)
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(text[missing], errors="coerce", utc=True)
    return parsed


def latest_by_filename_base(dataframe: pd.DataFrame) -> pd.DataFrame:
    if "filename_base" not in dataframe.columns:
        raise KeyError("Metadata file is missing required column 'filename_base'.")
    work = dataframe.copy()
    work["filename_base"] = work["filename_base"].astype(str)
    if "execution_timestamp" in work.columns:
        work["_exec_dt"] = parse_execution_timestamp_series(work["execution_timestamp"])
        work = work.sort_values(["filename_base", "_exec_dt"], na_position="last", kind="mergesort")
        work = work.groupby("filename_base", sort=False).tail(1).drop(columns=["_exec_dt"])
    return work.groupby("filename_base", sort=False).tail(1).reset_index(drop=True)


def normalize_trigger_type(value: object) -> str:
    return str(value).strip()


def parse_trigger_combinations(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    decoded: object
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = [token for token in text.split(",") if token.strip()]
    elif isinstance(value, (list, tuple, np.ndarray)):
        decoded = list(value)
    else:
        return None
    if not isinstance(decoded, list):
        return None
    tokens = [normalize_trigger_type(token) for token in decoded if str(token).strip()]
    if not tokens:
        return None
    return tuple(sorted(tokens))


def parse_efficiency_vector(value: object) -> tuple[float, float, float, float] | None:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return None
    elif isinstance(value, (list, tuple, np.ndarray)):
        decoded = list(value)
    else:
        return None
    if len(decoded) != 4:
        return None
    try:
        return tuple(float(item) for item in decoded)
    except (TypeError, ValueError):
        return None


def parse_filename_base_timestamp(value: object) -> pd.Timestamp:
    text = str(value).strip().lower()
    if text.startswith("mini"):
        text = "mi01" + text[4:]
    match = FILENAME_TIMESTAMP_PATTERN.search(text)
    if match is None:
        return pd.NaT
    stamp = match.group(1)
    try:
        year = 2000 + int(stamp[0:2])
        day_of_year = int(stamp[2:5])
        hour = int(stamp[5:7])
        minute = int(stamp[7:9])
        second = int(stamp[9:11])
    except ValueError:
        return pd.NaT
    dt = datetime(year, 1, 1) + pd.Timedelta(
        days=day_of_year - 1,
        hours=hour,
        minutes=minute,
        seconds=second,
    )
    return pd.Timestamp(dt, tz="UTC")


def resolve_simulation_filters(config: dict[str, Any]) -> dict[str, Any]:
    sim_cfg = config.get("simulation_filters", {})
    if not isinstance(sim_cfg, dict):
        raise ValueError("Config key 'simulation_filters' must be an object.")

    def parse_range(raw: object, key: str) -> tuple[float, float] | None:
        if raw in (None, "", "null", "None"):
            return None
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            raise ValueError(f"Config key '{key}' must be a two-element list [min, max].")
        low = float(raw[0])
        high = float(raw[1])
        if low > high:
            raise ValueError(f"Config key '{key}' must satisfy min <= max.")
        return (low, high)

    z_positions_raw = sim_cfg.get("z_positions")
    if not isinstance(z_positions_raw, (list, tuple)) or len(z_positions_raw) != 4:
        raise ValueError("Config key 'simulation_filters.z_positions' must be a four-element list.")
    z_tuple = tuple(canonical_z(value) for value in z_positions_raw)

    trigger_combinations = parse_trigger_combinations(sim_cfg.get("trigger_combinations"))
    if trigger_combinations is None:
        raise ValueError("Config key 'simulation_filters.trigger_combinations' must be a non-empty list.")

    eff_range = parse_range(sim_cfg.get("efficiency_range"), "simulation_filters.efficiency_range")
    if eff_range is None:
        eff_range = (0.0, 1.0)

    return {
        "cos_n_range": parse_range(sim_cfg.get("cos_n_range"), "simulation_filters.cos_n_range"),
        "flux_cm2_min_range": parse_range(
            sim_cfg.get("flux_cm2_min_range"),
            "simulation_filters.flux_cm2_min_range",
        ),
        "z_tuple": z_tuple,
        "trigger_combinations": trigger_combinations,
        "efficiency_range": eff_range,
    }


def read_filtered_simulation_rows(config: dict[str, Any]) -> pd.DataFrame:
    if not SIMULATION_PARAMS_CSV.exists():
        raise FileNotFoundError(f"Simulation params CSV not found: {SIMULATION_PARAMS_CSV}")

    filters = resolve_simulation_filters(config)
    dataframe = pd.read_csv(SIMULATION_PARAMS_CSV, low_memory=False)
    required = ["file_name", "param_hash", "efficiencies", "trigger_combinations", *SIM_Z_COLS]
    missing = [column for column in required if column not in dataframe.columns]
    if missing:
        raise ValueError(f"Simulation params CSV is missing required columns {missing}.")

    work = dataframe.copy()
    work["filename_base"] = work["file_name"].astype(str).str.replace(r"\.(dat|parquet)$", "", regex=True)
    for column in [*SIM_Z_COLS, *[col for col in ("cos_n", "flux_cm2_min") if col in work.columns]]:
        work[column] = pd.to_numeric(work[column], errors="coerce")
    work["_eff_tuple"] = work["efficiencies"].map(parse_efficiency_vector)
    work["_trigger_tuple"] = work["trigger_combinations"].map(parse_trigger_combinations)
    valid_mask = work["_eff_tuple"].notna() & work["_trigger_tuple"].notna()
    valid_mask &= ~work["param_hash"].isna()
    for column in SIM_Z_COLS:
        valid_mask &= work[column].notna()
    work = work.loc[valid_mask].copy()
    if work.empty:
        raise ValueError("No valid simulation rows remained after base parsing.")

    eff_frame = pd.DataFrame(work["_eff_tuple"].tolist(), columns=SIM_EFF_COLS, index=work.index)
    work = pd.concat([work.drop(columns=["_eff_tuple"]), eff_frame], axis=1)
    work["z_tuple"] = [tuple(canonical_z(v) for v in row) for row in work[SIM_Z_COLS].to_numpy()]

    mask = pd.Series(True, index=work.index, dtype=bool)
    cos_range = filters["cos_n_range"]
    if cos_range is not None:
        if "cos_n" not in work.columns:
            raise ValueError("Simulation filter requested cos_n_range, but column 'cos_n' is missing.")
        low, high = cos_range
        mask &= work["cos_n"].between(low, high, inclusive="both")

    flux_range = filters["flux_cm2_min_range"]
    if flux_range is not None:
        if "flux_cm2_min" not in work.columns:
            raise ValueError("Simulation filter requested flux_cm2_min_range, but column 'flux_cm2_min' is missing.")
        low, high = flux_range
        mask &= work["flux_cm2_min"].between(low, high, inclusive="both")

    eff_low, eff_high = filters["efficiency_range"]
    for column in SIM_EFF_COLS:
        mask &= work[column].between(eff_low, eff_high, inclusive="both")

    mask &= work["z_tuple"].map(lambda value: value == filters["z_tuple"])
    mask &= work["_trigger_tuple"].map(lambda value: value == filters["trigger_combinations"])

    filtered = work.loc[mask].copy()
    if filtered.empty:
        raise ValueError("No simulation rows remained after applying the configured filters.")
    return filtered.reset_index(drop=True)


def read_station_task4_table(station: int) -> pd.DataFrame:
    eff_df = pd.read_csv(task4_metadata_file(station), low_memory=False)
    z_df = pd.read_csv(task5_specific_metadata_file(station), low_memory=False)
    eff_df = latest_by_filename_base(eff_df)
    z_df = latest_by_filename_base(z_df)
    eff_df["filename_base"] = eff_df["filename_base"].astype(str)
    z_df["filename_base"] = z_df["filename_base"].astype(str)
    merged = eff_df.merge(z_df[["filename_base", *Z_COLS]], on="filename_base", how="inner")
    for column in [*EFF_COLS, *Z_COLS]:
        merged[column] = pd.to_numeric(merged[column], errors="coerce")
    merged = merged.dropna(subset=EFF_COLS + Z_COLS).copy()
    merged["z_tuple"] = [tuple(canonical_z(v) for v in row) for row in merged[Z_COLS].to_numpy()]
    return merged.reset_index(drop=True)


def completed_files_by_base(station: int, task_id: int) -> dict[str, Path]:
    completed_dir = task_input_completed_directory(station, task_id)
    if not completed_dir.exists():
        raise FileNotFoundError(f"Completed input directory not found: {completed_dir}")
    mapping: dict[str, Path] = {}
    for path in sorted(completed_dir.glob("*.parquet")):
        base = path.stem
        for prefix in ("listed_", "fitted_", "post_", "cleaned_", "calibrated_"):
            if base.startswith(prefix):
                base = base[len(prefix) :]
                break
        mapping[base] = path
    return mapping


def restrict_to_completed_files(dataframe: pd.DataFrame, completed_map: dict[str, Path]) -> pd.DataFrame:
    out = dataframe.copy()
    out["completed_file_path"] = out["filename_base"].map(lambda base: str(completed_map[base]) if base in completed_map else pd.NA)
    return out.dropna(subset=["completed_file_path"]).copy()


def build_filevfile_pair(config: dict[str, Any]) -> FilePairSelection:
    station_id = parse_station_id(config.get("station_of_study", config.get("station", 2)))
    task_id = int(config.get("task_id", 3))
    random_seed = int(config.get("random_seed", 20260508))
    max_eff_distance = float(config.get("max_eff_distance", 0.08))
    filters = resolve_simulation_filters(config)

    sim_df = read_filtered_simulation_rows(config)
    ref_metadata = read_station_task4_table(0)
    study_metadata = read_station_task4_table(station_id)

    ref_candidates = ref_metadata.merge(
        sim_df[
            [
                "param_hash",
                "filename_base",
                "cos_n",
                "flux_cm2_min",
                "trigger_combinations",
                *SIM_EFF_COLS,
                "z_tuple",
            ]
        ].rename(columns={"filename_base": "sim_filename_base"}),
        on="param_hash",
        how="inner",
        suffixes=("", "__sim"),
    )
    if ref_candidates.empty:
        raise ValueError("No MINGO00 Task-4 metadata rows matched the filtered simulation rows through param_hash.")

    ref_completed = completed_files_by_base(0, task_id)
    study_completed = completed_files_by_base(station_id, task_id)
    ref_candidates = restrict_to_completed_files(ref_candidates, ref_completed)
    study_metadata = restrict_to_completed_files(study_metadata, study_completed)
    study_metadata = study_metadata.loc[study_metadata["z_tuple"].map(lambda value: value == filters["z_tuple"])].copy()

    if ref_candidates.empty:
        raise ValueError("No filtered MINGO00 reference rows have matching completed parquet files.")
    if study_metadata.empty:
        raise ValueError(
            f"No study-station Task-{task_id} rows remain after z filtering and completed-file filtering "
            f"for {format_station_label(station_id)}."
        )

    grouped_ref = {
        z_tuple: group.reset_index(drop=True).copy()
        for z_tuple, group in ref_candidates.groupby("z_tuple", dropna=False)
    }
    candidate_rows: list[dict[str, Any]] = []
    for _, study_row in study_metadata.iterrows():
        z_tuple = study_row["z_tuple"]
        if z_tuple not in grouped_ref:
            continue
        candidates = grouped_ref[z_tuple]
        ref_eff = candidates[EFF_COLS].to_numpy(dtype=float)
        study_eff = study_row[EFF_COLS].to_numpy(dtype=float)
        distances = np.linalg.norm(ref_eff - study_eff, axis=1)
        best_idx = int(np.argmin(distances))
        best_distance = float(distances[best_idx])
        if best_distance > max_eff_distance:
            continue
        ref_row = candidates.iloc[best_idx]
        candidate_rows.append(
            {
                "study_row": study_row.copy(),
                "ref_row": ref_row.copy(),
                "eff_distance": best_distance,
            }
        )

    if not candidate_rows:
        raise ValueError(
            f"No eligible FILEvFILE pairs were found for {format_station_label(station_id)} "
            f"with max_eff_distance={max_eff_distance:.6g}."
        )

    rng = np.random.default_rng(random_seed)
    selected = candidate_rows[int(rng.integers(0, len(candidate_rows)))]
    study_row = selected["study_row"]
    ref_row = selected["ref_row"]
    sim_trigger_tuple = parse_trigger_combinations(ref_row["trigger_combinations"]) or tuple()

    return FilePairSelection(
        task_id=task_id,
        station_of_study=station_id,
        station_of_study_label=format_station_label(station_id),
        study_filename_base=str(study_row["filename_base"]),
        reference_filename_base=str(ref_row["filename_base"]),
        study_file_path=str(study_row["completed_file_path"]),
        reference_file_path=str(ref_row["completed_file_path"]),
        z_tuple=tuple(ref_row["z_tuple"]),
        eff_distance=float(selected["eff_distance"]),
        study_efficiencies=tuple(float(study_row[column]) for column in EFF_COLS),
        reference_efficiencies=tuple(float(ref_row[column]) for column in EFF_COLS),
        reference_param_hash=str(ref_row["param_hash"]),
        sim_cos_n=None if pd.isna(ref_row.get("cos_n")) else float(ref_row["cos_n"]),
        sim_flux_cm2_min=None if pd.isna(ref_row.get("flux_cm2_min")) else float(ref_row["flux_cm2_min"]),
        sim_trigger_combinations=list(sim_trigger_tuple),
        sim_efficiencies=tuple(float(ref_row[column]) for column in SIM_EFF_COLS),
        random_seed=random_seed,
        candidate_pair_count=len(candidate_rows),
    )


def write_pair_summary(selection: FilePairSelection, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(selection), indent=2), encoding="utf-8")
    return path
