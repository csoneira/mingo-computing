#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from common import REPO_ROOT, derive_trigger_rate_features, get_trigger_type_selection, resolve_path

CANONICAL_Z_COLUMNS = ["z_pos_1", "z_pos_2", "z_pos_3", "z_pos_4"]
SIM_Z_COLUMNS = ["z_plane_1", "z_plane_2", "z_plane_3", "z_plane_4"]
DEFAULT_SIM_EFF_COLUMNS = ["eff_p1", "eff_p2", "eff_p3", "eff_p4"]
DEFAULT_SIM_PARAMS_CSV = (
    REPO_ROOT / "PIPELINE" / "MINGO_DIGITAL_TWIN" / "SIMULATION_OUTPUTS" / "SIMULATED_DATA" / "step_final_simulation_params.csv"
)
DEFAULT_MINGO00_METADATA_ROOT = (
    REPO_ROOT
    / "PIPELINE" / "MINGO_ANALYSIS"
    / "MINGO_ANALYSIS_STATIONS"
    / "MINGO00"
    / "STAGE_1"
    / "EVENT_DATA"
    / "STEP_1"
)
ONLINE_RUN_DICTIONARY_ROOT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS" / "SUPPORT" / "CONFIG_FILES" / "STAGE_0" / "ONLINE_RUN_DICTIONARY"
DEFAULT_STATION0_Z_VECTOR = (0.0, 100.0, 200.0, 400.0)

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FILE_TS_RE = re.compile(r"(\d{11})$")
_EMBEDDED_METADATA_ROW_START_RE = re.compile(r"(?<![\r\n])(mi\d{13},)")

log = logging.getLogger("even_easier_advanced.metadata")


def load_metadata_csv_with_repair(csv_path: str | Path, *, low_memory: bool = False) -> pd.DataFrame:
    path = Path(csv_path)
    try:
        return pd.read_csv(path, low_memory=low_memory)
    except pd.errors.ParserError as exc:
        repaired_text, repair_count = _EMBEDDED_METADATA_ROW_START_RE.subn(
            r"\n\1",
            path.read_text(encoding="utf-8", errors="replace"),
        )
        if repair_count == 0:
            raise
        try:
            dataframe = pd.read_csv(StringIO(repaired_text), low_memory=low_memory)
        except pd.errors.ParserError as repair_exc:
            raise pd.errors.ParserError(f"Unable to repair malformed metadata CSV {path}: {repair_exc}") from exc
        log.warning(
            "Repaired %d embedded metadata row-start(s) while reading %s.",
            repair_count,
            path,
        )
        return dataframe


def _resolve_observed_efficiency_limits(
    config: dict[str, Any],
    *,
    config_key: str,
) -> dict[int, float]:
    step0_config = config.get("step0", {})
    if not isinstance(step0_config, dict):
        step0_config = {}

    raw = step0_config.get(config_key, {})
    if raw in (None, "", "null", "None"):
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"step0.{config_key} must be a JSON object keyed by plane index.")

    limits: dict[int, float] = {}
    for key, value in raw.items():
        text = str(key).strip().lower()
        if text.startswith("plane_"):
            text = text[6:]
        plane_idx = int(text)
        if plane_idx < 1 or plane_idx > 4:
            raise ValueError(f"Invalid plane index in step0.{config_key}: {key!r}")
        if value in (None, "", "null", "None"):
            continue
        limit = float(value)
        limits[plane_idx] = limit
    return limits


def resolve_observed_efficiency_upper_limits(config: dict[str, Any]) -> dict[int, float]:
    return _resolve_observed_efficiency_limits(
        config,
        config_key="observed_efficiency_upper_limits",
    )


def resolve_observed_efficiency_lower_limits(config: dict[str, Any]) -> dict[int, float]:
    return _resolve_observed_efficiency_limits(
        config,
        config_key="observed_efficiency_lower_limits",
    )


def apply_observed_efficiency_upper_limits(
    dataframe: pd.DataFrame,
    limits: dict[int, float],
    *,
    lower_limits: dict[int, float] | None = None,
    mode: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if mode not in {"clip", "drop"}:
        raise ValueError("Observed-efficiency limit mode must be 'clip' or 'drop'.")

    work = dataframe.copy()
    row_count_before = int(len(work))
    lower_limits = dict(lower_limits or {})
    counts_by_plane: dict[str, int] = {}
    counts_above_by_plane: dict[str, int] = {}
    counts_below_by_plane: dict[str, int] = {}
    outside_union_mask = pd.Series(False, index=work.index, dtype=bool)
    all_planes = sorted(set(limits).union(lower_limits))
    for plane_idx in all_planes:
        column = f"eff_empirical_{plane_idx}"
        if column not in work.columns:
            continue
        numeric = pd.to_numeric(work[column], errors="coerce")
        below_mask = pd.Series(False, index=work.index, dtype=bool)
        above_mask = pd.Series(False, index=work.index, dtype=bool)
        lower_limit = lower_limits.get(plane_idx, None)
        upper_limit = limits.get(plane_idx, None)
        if lower_limit is not None:
            below_mask = numeric.notna() & (numeric < float(lower_limit))
            counts_below_by_plane[str(plane_idx)] = int(below_mask.sum())
        if upper_limit is not None:
            above_mask = numeric.notna() & (numeric > float(upper_limit))
            counts_above_by_plane[str(plane_idx)] = int(above_mask.sum())
        outside_mask = below_mask | above_mask
        counts_by_plane[str(plane_idx)] = int(outside_mask.sum())
        outside_union_mask = outside_union_mask | outside_mask
        if mode == "clip":
            if lower_limit is not None:
                numeric.loc[below_mask] = float(lower_limit)
            if upper_limit is not None:
                numeric.loc[above_mask] = float(upper_limit)
        work[column] = numeric
    if mode == "drop" and bool(outside_union_mask.any()):
        work = work.loc[~outside_union_mask].copy()

    metadata = {
        "mode": mode,
        "limits_by_plane": {
            str(plane_idx): {
                "lower": (
                    float(lower_limits[plane_idx]) if plane_idx in lower_limits else None
                ),
                "upper": (
                    float(limits[plane_idx]) if plane_idx in limits else None
                ),
            }
            for plane_idx in all_planes
        },
        "upper_limits_by_plane": {str(key): float(value) for key, value in sorted(limits.items())},
        "lower_limits_by_plane": {str(key): float(value) for key, value in sorted(lower_limits.items())},
        "affected_rows_by_plane": counts_by_plane,
        "affected_rows_above_upper_by_plane": counts_above_by_plane,
        "affected_rows_below_lower_by_plane": counts_below_by_plane,
        "affected_rows_total": int(outside_union_mask.sum()),
        "row_count_before": row_count_before,
        "row_count_after": int(len(work)),
    }
    return work, metadata


def normalize_z_vector(values: Any) -> tuple[float, float, float, float]:
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError(f"Expected four z positions, got: {values!r}")
    return tuple(float(value) for value in values)


def format_z_vector(z_vector: tuple[float, float, float, float]) -> str:
    return "[" + ", ".join(f"{float(value):g}" for value in z_vector) + "]"


def z_vector_to_id(z_vector: tuple[float, float, float, float]) -> str:
    pieces: list[str] = []
    for value in z_vector:
        text = f"{float(value):.3f}".rstrip("0").rstrip(".")
        text = text.replace("-", "m").replace(".", "p")
        pieces.append(text or "0")
    return "z_" + "__".join(pieces)


def parse_station_id(raw: object) -> int:
    if raw in (None, "", "null", "None"):
        raise ValueError("step5.station must not be empty.")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return int(raw)
    text = str(raw).strip()
    match = re.fullmatch(r"(?i)MINGO(\d{1,2})", text)
    if match is not None:
        return int(match.group(1))
    return int(text)


def parse_time_bound(value: object, *, end_of_day: bool) -> pd.Timestamp | None:
    if value in (None, "", "null", "None"):
        return None
    text = str(value).strip()
    parsed = pd.to_datetime(text, errors="coerce", utc=True)
    if pd.isna(parsed):
        raise ValueError(f"Could not parse datetime bound: {value!r}")
    if end_of_day and _DATE_ONLY_RE.fullmatch(text):
        parsed = parsed + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return pd.Timestamp(parsed)


def parse_filename_base_ts(value: object) -> pd.Timestamp:
    text = str(value).strip().lower()
    if text.startswith("mini"):
        text = "mi01" + text[4:]
    match = _FILE_TS_RE.search(text)
    if match is None:
        return pd.NaT
    stamp = match.group(1)
    try:
        year = 2000 + int(stamp[0:2])
        day_of_year = int(stamp[2:5])
        hour = int(stamp[5:7])
        minute = int(stamp[7:9])
        second = int(stamp[9:11])
        dt = datetime(year, 1, 1) + timedelta(
            days=day_of_year - 1,
            hours=hour,
            minutes=minute,
            seconds=second,
        )
    except ValueError:
        return pd.NaT
    return pd.Timestamp(dt, tz="UTC")


def parse_execution_timestamp(series: pd.Series) -> pd.Series:
    text = series.astype("string")
    parsed = pd.to_datetime(text, format="%Y-%m-%d_%H.%M.%S", errors="coerce", utc=True)
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(text[missing], errors="coerce", utc=True)
    return parsed


def aggregate_latest_by_key(dataframe: pd.DataFrame, key_column: str, timestamp_column: str) -> pd.DataFrame:
    work = dataframe.copy()
    if timestamp_column in work.columns:
        work["_exec_dt"] = parse_execution_timestamp(work[timestamp_column])
        work = work.sort_values([key_column, "_exec_dt"], na_position="last", kind="mergesort")
        work = work.groupby(key_column).tail(1).drop(columns=["_exec_dt"])
    return work.groupby(key_column, sort=False).tail(1).reset_index(drop=True)


def add_geometry_columns(
    dataframe: pd.DataFrame,
    *,
    source_z_columns: list[str] | None = None,
) -> pd.DataFrame:
    columns = list(source_z_columns or CANONICAL_Z_COLUMNS)
    work = dataframe.copy()
    z_numeric = work[columns].apply(pd.to_numeric, errors="coerce")

    config_ids: list[str | None] = []
    labels: list[str | None] = []
    normalized_rows: list[list[float | None]] = []
    for row in z_numeric.itertuples(index=False, name=None):
        if any(pd.isna(value) for value in row):
            config_ids.append(None)
            labels.append(None)
            normalized_rows.append([None, None, None, None])
            continue
        z_vector = normalize_z_vector(list(row))
        config_ids.append(z_vector_to_id(z_vector))
        labels.append(format_z_vector(z_vector))
        normalized_rows.append([float(value) for value in z_vector])

    for idx, column in enumerate(CANONICAL_Z_COLUMNS):
        work[column] = pd.Series([row[idx] for row in normalized_rows], index=work.index, dtype="float64")
    work["z_config_id"] = pd.Series(config_ids, index=work.index, dtype="object")
    work["z_config_label"] = pd.Series(labels, index=work.index, dtype="object")
    return work


def unique_z_vectors(
    dataframe: pd.DataFrame,
    *,
    z_columns: list[str] | None = None,
) -> list[tuple[float, float, float, float]]:
    columns = list(z_columns or CANONICAL_Z_COLUMNS)
    z_numeric = dataframe[columns].apply(pd.to_numeric, errors="coerce").dropna()
    if z_numeric.empty:
        return []
    return [
        normalize_z_vector(list(row))
        for row in z_numeric.drop_duplicates().itertuples(index=False, name=None)
    ]


def z_mask_for_vector(
    dataframe: pd.DataFrame,
    z_vector: tuple[float, float, float, float],
    *,
    z_columns: list[str] | None = None,
) -> pd.Series:
    columns = list(z_columns or CANONICAL_Z_COLUMNS)
    mask = np.ones(len(dataframe), dtype=bool)
    for column, value in zip(columns, z_vector):
        mask &= np.isclose(pd.to_numeric(dataframe[column], errors="coerce"), float(value), equal_nan=False)
    return pd.Series(mask, index=dataframe.index)


def load_simulation_params_with_efficiencies(config: dict[str, Any]) -> tuple[pd.DataFrame, Path]:
    step0_config = config.get("step0", {})
    if not isinstance(step0_config, dict):
        step0_config = {}

    sim_params_path = Path(step0_config.get("simulation_params_csv", str(DEFAULT_SIM_PARAMS_CSV))).expanduser()
    if not sim_params_path.is_absolute():
        sim_params_path = resolve_path(config, sim_params_path)
    if not sim_params_path.exists():
        raise FileNotFoundError(f"Simulation-params CSV does not exist: {sim_params_path}")

    dataframe = pd.read_csv(sim_params_path, low_memory=False)
    if "param_hash" not in dataframe.columns:
        raise ValueError("Simulation-params CSV must contain param_hash.")

    if "efficiencies" in dataframe.columns and not all(column in dataframe.columns for column in DEFAULT_SIM_EFF_COLUMNS):
        parsed = dataframe["efficiencies"].astype(str).str.strip()
        parsed = parsed.str.replace("(", "[", regex=False).str.replace(")", "]", regex=False)
        eff_vectors = parsed.map(lambda text: json.loads(text) if text.startswith("[") and text.endswith("]") else None)
        for idx, column in enumerate(DEFAULT_SIM_EFF_COLUMNS):
            dataframe[column] = eff_vectors.map(
                lambda vec, i=idx: np.nan if not isinstance(vec, list) or len(vec) != 4 else float(vec[i])
            )

    missing_eff_columns = [column for column in DEFAULT_SIM_EFF_COLUMNS if column not in dataframe.columns]
    if missing_eff_columns:
        raise ValueError(
            "Simulation-params CSV must contain simulated efficiencies either as eff_p1..eff_p4 "
            "or as a parseable efficiencies vector. Missing: "
            + ", ".join(missing_eff_columns)
        )

    for column in [*SIM_Z_COLUMNS, *DEFAULT_SIM_EFF_COLUMNS]:
        if column in dataframe.columns:
            dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

    return dataframe, sim_params_path


def _resolve_simulation_params_path(config: dict[str, Any] | None = None) -> Path:
    if not isinstance(config, dict):
        return DEFAULT_SIM_PARAMS_CSV

    step0_config = config.get("step0", {})
    if not isinstance(step0_config, dict):
        step0_config = {}

    raw_path = step0_config.get("simulation_params_csv")
    if raw_path in (None, "", "null", "None"):
        return DEFAULT_SIM_PARAMS_CSV

    sim_params_path = Path(str(raw_path)).expanduser()
    if not sim_params_path.is_absolute():
        sim_params_path = resolve_path(config, sim_params_path)
    return sim_params_path


def _resolve_station0_z_vector(config: dict[str, Any] | None = None) -> tuple[tuple[float, float, float, float], Path]:
    geometry_config = config.get("geometry", {}) if isinstance(config, dict) else {}
    if not isinstance(geometry_config, dict):
        geometry_config = {}

    raw_z_vector = geometry_config.get("station0_z_positions", DEFAULT_STATION0_Z_VECTOR)
    z_vector = normalize_z_vector(raw_z_vector)
    sim_params_path = _resolve_simulation_params_path(config)
    if not sim_params_path.exists():
        raise FileNotFoundError(
            f"Station 0 synthetic schedule requires the simulation params CSV, but it was not found: {sim_params_path}"
        )

    try:
        available_df = pd.read_csv(sim_params_path, usecols=SIM_Z_COLUMNS, low_memory=False)
    except ValueError as exc:
        raise ValueError(f"Simulation params CSV is missing required z-plane columns: {sim_params_path}") from exc

    available_vectors = {
        normalize_z_vector([row[column] for column in SIM_Z_COLUMNS])
        for _, row in available_df.dropna(subset=SIM_Z_COLUMNS).drop_duplicates().iterrows()
    }
    if z_vector not in available_vectors:
        available_text = ", ".join(format_z_vector(vector) for vector in sorted(available_vectors))
        raise ValueError(
            "Configured geometry.station0_z_positions "
            f"{format_z_vector(z_vector)} was not found in {sim_params_path}. "
            f"Available simulated vectors: {available_text}"
        )
    return z_vector, sim_params_path


def _load_station0_simulated_schedule(
    config: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, Path]:
    z_vector, sim_params_path = _resolve_station0_z_vector(config)
    log.info(
        "Using synthetic station-0 schedule from %s with fixed z positions %s.",
        sim_params_path,
        format_z_vector(z_vector),
    )
    schedule_df = pd.DataFrame({"z_tuple": [z_vector]})
    schedule_df["start_utc"] = pd.Series([pd.Timestamp("1970-01-01", tz="UTC")], dtype="datetime64[ns, UTC]")
    schedule_df["end_utc"] = pd.Series([pd.NaT], dtype="datetime64[ns, UTC]")
    return schedule_df, sim_params_path


def _mingo00_metadata_path(config: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    step0_config = config.get("step0", {})
    if not isinstance(step0_config, dict):
        step0_config = {}

    metadata_root = Path(step0_config.get("mingo00_metadata_root", str(DEFAULT_MINGO00_METADATA_ROOT))).expanduser()
    if not metadata_root.is_absolute():
        metadata_root = resolve_path(config, metadata_root)

    selection = get_trigger_type_selection(config)
    task_id = int(selection.get("metadata_task_id", selection["task_id"]))
    source_name = str(selection.get("source_name", "trigger_type"))
    metadata_path = metadata_root / f"TASK_{task_id}" / "METADATA" / f"task_{task_id}_metadata_{source_name}.csv"
    return metadata_path, selection


def load_mingo00_training_dataframe(config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    sim_params_df, sim_params_path = load_simulation_params_with_efficiencies(config)
    metadata_path, selection = _mingo00_metadata_path(config)
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing required MINGO00 metadata file: {metadata_path}")

    metadata_df = load_metadata_csv_with_repair(metadata_path, low_memory=False)
    if "param_hash" not in metadata_df.columns:
        raise ValueError(f"MINGO00 metadata has no param_hash column: {metadata_path}")
    metadata_df = aggregate_latest_by_key(metadata_df, "param_hash", "execution_timestamp")

    merged = sim_params_df.merge(metadata_df, on="param_hash", how="inner")
    if merged.empty:
        raise ValueError("MINGO00 param-hash merge produced no rows.")
    rows_after_param_hash_merge = int(len(merged))

    merged, trigger_info = derive_trigger_rate_features(merged, config, allow_plain_fallback=False)
    observed_efficiency_upper_limits = resolve_observed_efficiency_upper_limits(config)
    observed_efficiency_lower_limits = resolve_observed_efficiency_lower_limits(config)
    merged, observed_efficiency_limit_meta = apply_observed_efficiency_upper_limits(
        merged,
        observed_efficiency_upper_limits,
        lower_limits=observed_efficiency_lower_limits,
        mode="drop",
    )
    merged = add_geometry_columns(merged, source_z_columns=SIM_Z_COLUMNS)

    metadata = {
        "simulation_params_csv": str(sim_params_path),
        "mingo00_metadata_csv": str(metadata_path),
        "rows_simulation_params": int(len(sim_params_df)),
        "rows_mingo00_metadata": int(len(metadata_df)),
        "rows_after_param_hash_merge": rows_after_param_hash_merge,
        "rows_after_observed_efficiency_limit_filter": int(len(merged)),
        "rows_after_observed_efficiency_upper_limit_filter": int(len(merged)),
        "trigger_selection": trigger_info,
        "observed_efficiency_limit_filter": observed_efficiency_limit_meta,
        "observed_efficiency_upper_limit_filter": observed_efficiency_limit_meta,
    }
    return merged, metadata


def fit_polynomial_coefficients(
    x_values: pd.Series,
    y_values: pd.Series,
    *,
    degree_requested: int,
) -> tuple[list[float], dict[str, Any]]:
    x_numeric = pd.to_numeric(x_values, errors="coerce")
    y_numeric = pd.to_numeric(y_values, errors="coerce")
    valid = x_numeric.notna() & y_numeric.notna()
    x = x_numeric.loc[valid].to_numpy(dtype=float)
    y = y_numeric.loc[valid].to_numpy(dtype=float)
    if len(x) == 0:
        return [], {"n_fit_points": 0, "degree_used": None, "r_squared": None}

    if degree_requested < 0:
        raise ValueError("step0.fit_polynomial_degree must be >= 0.")

    unique_x = np.unique(np.round(x, 12))
    max_degree = max(0, min(int(degree_requested), len(x) - 1, len(unique_x) - 1))
    if max_degree == 0:
        coeffs = np.array([float(np.mean(y))], dtype=float)
        r_squared = np.nan
    else:
        coeffs = np.polyfit(x, y, deg=max_degree)
        y_fit = np.polyval(coeffs, x)
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        ss_res = float(np.sum((y - y_fit) ** 2))
        r_squared = np.nan if ss_tot <= 0.0 else 1.0 - ss_res / ss_tot

    return [float(value) for value in coeffs.tolist()], {
        "n_fit_points": int(len(x)),
        "degree_used": int(max_degree),
        "r_squared": None if not np.isfinite(r_squared) else float(r_squared),
    }


def parse_coefficients_cell(value: object) -> list[float]:
    if value in (None, "", "null", "None"):
        return []
    if isinstance(value, list):
        return [float(item) for item in value]
    text = str(value).strip()
    if not text:
        return []
    decoded = json.loads(text)
    if not isinstance(decoded, list):
        raise ValueError(f"Expected a JSON list of polynomial coefficients, got: {value!r}")
    return [float(item) for item in decoded]


def apply_polynomial_coefficients(
    values: pd.Series,
    coefficients: list[float],
    *,
    clip_output: bool,
) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    if not coefficients:
        return numeric
    predicted = pd.Series(np.polyval(np.asarray(coefficients, dtype=float), numeric.to_numpy(dtype=float)), index=values.index)
    if clip_output:
        predicted = predicted.clip(lower=0.0, upper=1.0)
    return predicted


def build_efficiency_fit_table(
    training_dataframe: pd.DataFrame,
    *,
    degree_requested: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if training_dataframe.empty:
        return pd.DataFrame()

    for z_config_id, subset in training_dataframe.groupby("z_config_id", dropna=False, sort=True):
        if not isinstance(z_config_id, str) or subset.empty:
            continue
        row = {
            "z_config_id": z_config_id,
            "z_config_label": subset["z_config_label"].iloc[0],
            "n_geometry_rows": int(len(subset)),
        }
        for column in CANONICAL_Z_COLUMNS:
            row[column] = float(subset[column].iloc[0])
        for plane_idx in range(1, 5):
            coeffs, meta = fit_polynomial_coefficients(
                subset[f"eff_empirical_{plane_idx}"],
                subset[f"eff_p{plane_idx}"],
                degree_requested=degree_requested,
            )
            row[f"plane_{plane_idx}"] = json.dumps(coeffs)
            row[f"plane_{plane_idx}_degree_used"] = meta["degree_used"]
            row[f"plane_{plane_idx}_fit_points"] = meta["n_fit_points"]
            row[f"plane_{plane_idx}_r_squared"] = meta["r_squared"]
        rows.append(row)

    return pd.DataFrame(rows).sort_values("z_config_id").reset_index(drop=True)


def load_fit_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Efficiency-fit table not found: {path}")
    dataframe = pd.read_csv(path, low_memory=False)
    required = ["z_config_id", "plane_1", "plane_2", "plane_3", "plane_4"]
    missing = [column for column in required if column not in dataframe.columns]
    if missing:
        raise ValueError("Efficiency-fit table is missing required columns: " + ", ".join(missing))
    return dataframe


def apply_fit_table(
    dataframe: pd.DataFrame,
    fit_table: pd.DataFrame,
    *,
    clip_output: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    work = dataframe.copy()
    for plane_idx in range(1, 5):
        raw_column = f"eff_empirical_raw_{plane_idx}"
        corrected_column = f"eff_empirical_corrected_{plane_idx}"
        source_column = f"eff_empirical_{plane_idx}"
        work[raw_column] = pd.to_numeric(work[source_column], errors="coerce")
        work[corrected_column] = work[raw_column]

    geometries_with_fits: list[str] = []
    for fit_row in fit_table.to_dict(orient="records"):
        z_config_id = str(fit_row["z_config_id"])
        geometries_with_fits.append(z_config_id)
        geometry_mask = work["z_config_id"].astype("string") == z_config_id
        if not bool(geometry_mask.any()):
            continue
        for plane_idx in range(1, 5):
            coeffs = parse_coefficients_cell(fit_row.get(f"plane_{plane_idx}"))
            raw_column = f"eff_empirical_raw_{plane_idx}"
            corrected_column = f"eff_empirical_corrected_{plane_idx}"
            work.loc[geometry_mask, corrected_column] = apply_polynomial_coefficients(
                work.loc[geometry_mask, raw_column],
                coeffs,
                clip_output=clip_output,
            )

    for plane_idx in range(1, 5):
        work[f"eff_empirical_{plane_idx}"] = work[f"eff_empirical_corrected_{plane_idx}"]

    missing_geometry_rows = work["z_config_id"].notna() & ~work["z_config_id"].isin(geometries_with_fits)
    for plane_idx in range(1, 5):
        corrected_column = f"eff_empirical_corrected_{plane_idx}"
        raw_column = f"eff_empirical_raw_{plane_idx}"
        work.loc[missing_geometry_rows, corrected_column] = work.loc[missing_geometry_rows, raw_column]
        work.loc[missing_geometry_rows, f"eff_empirical_{plane_idx}"] = work.loc[missing_geometry_rows, raw_column]

    metadata = {
        "rows_with_geometry": int(work["z_config_id"].notna().sum()),
        "rows_missing_geometry": int(work["z_config_id"].isna().sum()),
        "rows_without_matching_fit": int(missing_geometry_rows.sum()),
        "geometries_with_fits": sorted(set(geometries_with_fits)),
    }
    return work, metadata


def online_run_dictionary_path(station_id: int) -> Path:
    suffix = f"{int(station_id):02d}"
    candidates = [
        ONLINE_RUN_DICTIONARY_ROOT / f"STATION_{int(station_id)}" / f"input_file_mingo{suffix}.csv",
        ONLINE_RUN_DICTIONARY_ROOT / f"STATION_{suffix}" / f"input_file_mingo{suffix}.csv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    found = sorted(ONLINE_RUN_DICTIONARY_ROOT.glob(f"STATION_*/input_file_mingo{suffix}.csv"))
    if found:
        return found[0]
    raise FileNotFoundError(f"ONLINE_RUN_DICTIONARY CSV not found for station {station_id}")


def load_online_schedule(
    station_id: int,
    config: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, Path]:
    if int(station_id) == 0:
        return _load_station0_simulated_schedule(config)

    path = online_run_dictionary_path(station_id)
    raw = pd.read_csv(path, header=[0, 1], low_memory=False)
    if isinstance(raw.columns, pd.MultiIndex):
        columns = []
        for col in raw.columns:
            top = str(col[0]).strip()
            sub = str(col[1]).strip()
            columns.append(sub if sub and not sub.lower().startswith("unnamed") else top)
        dataframe = raw.copy()
        dataframe.columns = columns
    else:
        dataframe = raw.copy()

    col_by_lower = {str(column).strip().lower(): column for column in dataframe.columns}

    def pick(*names: str) -> str | None:
        for name in names:
            column = col_by_lower.get(name.lower())
            if column is not None:
                return str(column)
        return None

    station_col = pick("station", "detector")
    start_col = pick("start", "date_start")
    end_col = pick("end", "date_end")
    p1_col = pick("p1")
    p2_col = pick("p2")
    p3_col = pick("p3")
    p4_col = pick("p4")

    required = [start_col, p1_col, p2_col, p3_col, p4_col]
    if any(column is None for column in required):
        raise ValueError(f"Could not parse ONLINE_RUN_DICTIONARY schema in {path}")

    work = pd.DataFrame(index=dataframe.index)
    if station_col is not None:
        station_series = pd.to_numeric(dataframe[station_col], errors="coerce")
        work = work.loc[station_series == int(station_id)].copy()

    work["start_utc"] = pd.to_datetime(dataframe[start_col], errors="coerce", utc=True)
    work["end_utc"] = pd.to_datetime(dataframe[end_col], errors="coerce", utc=True) if end_col is not None else pd.NaT
    work["z_tuple"] = dataframe[[p1_col, p2_col, p3_col, p4_col]].apply(
        lambda row: normalize_z_vector(list(row.values)),
        axis=1,
    )
    work = work.dropna(subset=["start_utc"]).sort_values(["start_utc", "end_utc"], kind="mergesort")
    return work.reset_index(drop=True), path


def select_schedule_rows_for_window(
    schedule_df: pd.DataFrame,
    *,
    date_from: pd.Timestamp | None,
    date_to: pd.Timestamp | None,
) -> pd.DataFrame:
    if schedule_df.empty:
        return schedule_df.copy()
    keep = pd.Series(True, index=schedule_df.index)
    far_future = pd.Timestamp("2100-01-01", tz="UTC")
    if date_from is not None:
        keep &= schedule_df["end_utc"].fillna(far_future) >= date_from
    if date_to is not None:
        keep &= schedule_df["start_utc"] <= date_to
    return schedule_df.loc[keep].copy()


def online_z_tuple_for_timestamp(ts: pd.Timestamp, schedule_df: pd.DataFrame) -> tuple[float, float, float, float] | None:
    if pd.isna(ts) or schedule_df.empty:
        return None
    keep = (schedule_df["start_utc"] <= ts) & (schedule_df["end_utc"].isna() | (ts < schedule_df["end_utc"]))
    candidates = schedule_df.loc[keep]
    if candidates.empty:
        return None
    row = candidates.sort_values("start_utc", kind="mergesort").iloc[-1]
    return normalize_z_vector(list(row["z_tuple"]))
