#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent
REPO_ROOT = ROOT_DIR.parents[4]
#/home/mingo/DATAFLOW_v3/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/CONFIG_FILES/STAGE_0/ONLINE_RUN_DICTIONARY
ONLINE_RUN_DICTIONARY_ROOT = (
    REPO_ROOT
    / "PIPELINE" / "MINGO_ANALYSIS"
    / "MINGO_ANALYSIS_SCRIPTS"
    / "SUPPORT" / "CONFIG_FILES"
    / "STAGE_0"
    / "ONLINE_RUN_DICTIONARY"
)
DEFAULT_CONFIG_PATH = ROOT_DIR / "config.json"

CANONICAL_EFF_COLUMNS = [f"eff_empirical_{idx}" for idx in range(1, 5)]
CANONICAL_Z_COLUMNS = [f"z_pos_{idx}" for idx in range(1, 5)]

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FILE_TS_RE = re.compile(r"(\d{11})$")


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path or DEFAULT_CONFIG_PATH).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["_config_path"] = str(config_path)
    config["_config_dir"] = str(config_path.parent)
    return config


def resolve_path(config: dict[str, Any], raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (Path(config["_config_dir"]) / path).resolve()


def cfg_path(config: dict[str, Any], *keys: str) -> Path:
    value: Any = config
    for key in keys:
        value = value[key]
    return resolve_path(config, value)


def _slugify(text: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(text).strip())
    safe = safe.strip("._")
    return safe or "default_case"


def case_output_root(config: dict[str, Any]) -> Path:
    root = cfg_path(config, "paths", "output_root")
    case_name = _slugify(config.get("case_name", "default_case"))
    return root / case_name


def files_dir(config: dict[str, Any]) -> Path:
    return case_output_root(config) / "FILES"


def plots_dir(config: dict[str, Any]) -> Path:
    return case_output_root(config) / "PLOTS"


def ensure_output_dirs(config: dict[str, Any]) -> None:
    files_dir(config).mkdir(parents=True, exist_ok=True)
    plots_dir(config).mkdir(parents=True, exist_ok=True)


def rate_case_slug(rate_spec: dict[str, Any]) -> str:
    name = rate_spec.get("name", rate_spec.get("rate_column", "rate_case"))
    return _slugify(str(name))


def rate_case_root(config: dict[str, Any], rate_spec: dict[str, Any]) -> Path:
    return case_output_root(config) / "RATE_CASES" / rate_case_slug(rate_spec)


def rate_case_files_dir(config: dict[str, Any], rate_spec: dict[str, Any]) -> Path:
    return rate_case_root(config, rate_spec) / "FILES"


def rate_case_plots_dir(config: dict[str, Any], rate_spec: dict[str, Any]) -> Path:
    return rate_case_root(config, rate_spec) / "PLOTS"


def ensure_rate_case_output_dirs(config: dict[str, Any], rate_spec: dict[str, Any]) -> None:
    rate_case_files_dir(config, rate_spec).mkdir(parents=True, exist_ok=True)
    rate_case_plots_dir(config, rate_spec).mkdir(parents=True, exist_ok=True)


def resolve_efficiency_spec(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("efficiency", {})
    if not isinstance(raw, dict):
        raise ValueError("Config is missing the efficiency object.")
    metadata_relative_path = str(raw.get("metadata_relative_path", "")).strip()
    if not metadata_relative_path:
        raise ValueError("efficiency.metadata_relative_path must be provided.")
    columns = raw.get("columns")
    if not isinstance(columns, list) or len(columns) != 4:
        raise ValueError("efficiency.columns must be a four-element list.")
    return {
        "metadata_relative_path": metadata_relative_path,
        "columns": [str(value) for value in columns],
    }


def resolve_rate_specs(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw_rates = config.get("rates")
    if raw_rates is None:
        raise ValueError("Config is missing the rates list.")
    if not isinstance(raw_rates, list) or not raw_rates:
        raise ValueError("rates must be a non-empty list.")

    specs: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for item in raw_rates:
        if not isinstance(item, dict):
            raise ValueError("Each rates entry must be an object.")
        name = str(item.get("name", item.get("rate_column", ""))).strip()
        if not name:
            raise ValueError("Each rates entry must define name or rate_column.")
        metadata_relative_path = str(item.get("metadata_relative_path", "")).strip()
        if not metadata_relative_path:
            raise ValueError(f"rates[{name}].metadata_relative_path must be provided.")
        rate_column = str(item.get("rate_column", "")).strip()
        if not rate_column:
            raise ValueError(f"rates[{name}].rate_column must be provided.")
        slug = _slugify(name)
        if slug in seen_names:
            raise ValueError(f"Duplicate rates entry name after slugification: {name!r}")
        seen_names.add(slug)
        specs.append(
            {
                "name": name,
                "slug": slug,
                "metadata_relative_path": metadata_relative_path,
                "rate_column": rate_column,
                "canonical_rate_column": f"rate_hz__{slug}",
                "scale_factor_column": f"scale_factor__{slug}",
                "corrected_rate_column": f"corrected_rate_to_perfect__{slug}",
                "corrected_flux_column": f"corrected_flux_cm2_min__{slug}",
            }
        )
    return specs


def ordered_plot_filename(step_number: int, order: int, label: str, *, extension: str = "png") -> str:
    clean_label = str(label).strip().strip("_")
    return f"step{int(step_number)}_{int(order):02d}_{clean_label}.{extension}"


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_station_name(raw: object) -> str:
    if raw in (None, "", "null", "None"):
        raise ValueError("Station must not be empty.")
    text = str(raw).strip().upper()
    match = re.fullmatch(r"MINGO(\d{1,2})", text)
    if match is not None:
        return f"MINGO{int(match.group(1)):02d}"
    if text.isdigit():
        return f"MINGO{int(text):02d}"
    raise ValueError(f"Could not parse station name from {raw!r}")


def parse_station_id(raw: object) -> int:
    return int(parse_station_name(raw).replace("MINGO", ""))


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


def parse_execution_timestamp(series: pd.Series) -> pd.Series:
    text = series.astype("string")
    parsed = pd.to_datetime(text, format="%Y-%m-%d_%H.%M.%S", errors="coerce", utc=True)
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(text[missing], errors="coerce", utc=True)
    return parsed


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


def resolve_station_metadata_path(config: dict[str, Any], station_name: str, raw_path: str) -> Path:
    formatted = str(raw_path).format(station=station_name)
    path = Path(formatted)
    if path.is_absolute():
        return path
    stations_root = cfg_path(config, "paths", "stations_root")
    return (stations_root / station_name / path).resolve()


def load_online_schedule(station_id: int) -> tuple[pd.DataFrame, Path]:
    suffix = f"{int(station_id):02d}"
    candidates = [
        ONLINE_RUN_DICTIONARY_ROOT / f"STATION_{int(station_id)}" / f"input_file_mingo{suffix}.csv",
        ONLINE_RUN_DICTIONARY_ROOT / f"STATION_{suffix}" / f"input_file_mingo{suffix}.csv",
    ]
    for candidate in candidates:
        if candidate.exists():
            path = candidate
            break
    else:
        found = sorted(ONLINE_RUN_DICTIONARY_ROOT.glob(f"STATION_*/input_file_mingo{suffix}.csv"))
        if not found:
            raise FileNotFoundError(f"ONLINE_RUN_DICTIONARY CSV not found for station {station_id}")
        path = found[0]

    raw = pd.read_csv(path, header=[0, 1], low_memory=False)
    if isinstance(raw.columns, pd.MultiIndex):
        columns = []
        for column in raw.columns:
            top = str(column[0]).strip()
            sub = str(column[1]).strip()
            columns.append(sub if sub and not sub.lower().startswith("unnamed") else top)
        dataframe = raw.copy()
        dataframe.columns = columns
    else:
        dataframe = raw.copy()

    column_map = {str(column).strip().lower(): column for column in dataframe.columns}

    def pick(*names: str) -> str | None:
        for name in names:
            column = column_map.get(name.lower())
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
        lambda row: tuple(float(value) for value in row.values),
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


def resolve_selected_z_vector(config: dict[str, Any]) -> tuple[tuple[float, float, float, float], dict[str, Any]]:
    geometry_config = config.get("geometry", {})
    if not isinstance(geometry_config, dict):
        geometry_config = {}
    real_config = config.get("real", {})
    if not isinstance(real_config, dict):
        real_config = {}

    mode_raw = geometry_config.get("selection_mode", "real_window_latest")
    mode = str(mode_raw).strip().lower()
    configured_vector = geometry_config.get("z_positions")
    if mode in {"configured", "configured_vector", "fixed"}:
        if not isinstance(configured_vector, (list, tuple)) or len(configured_vector) != 4:
            raise ValueError("geometry.z_positions must be a four-element list when using configured_vector mode.")
        z_vector = tuple(float(value) for value in configured_vector)
        return z_vector, {
            "selection_mode": "configured_vector",
            "selected_z_positions": list(z_vector),
            "station_id": None,
            "online_run_dictionary_csv": None,
            "date_from": None,
            "date_to": None,
            "window_candidate_z_positions": [],
            "window_selected_reason": "configured z_positions from config",
        }

    if mode not in {"real_window_latest", "step5_window", "window"}:
        raise ValueError(
            "Unsupported geometry.selection_mode. Supported values are 'real_window_latest' and 'configured_vector'."
        )

    station_id = parse_station_id(real_config.get("station", "MINGO01"))
    date_from = parse_time_bound(real_config.get("date_from"), end_of_day=False)
    date_to = parse_time_bound(real_config.get("date_to"), end_of_day=True)
    schedule_all, schedule_path = load_online_schedule(station_id)
    schedule_window = select_schedule_rows_for_window(schedule_all, date_from=date_from, date_to=date_to)
    if schedule_window.empty:
        if isinstance(configured_vector, (list, tuple)) and len(configured_vector) == 4:
            z_vector = tuple(float(value) for value in configured_vector)
            return z_vector, {
                "selection_mode": "real_window_latest",
                "selected_z_positions": list(z_vector),
                "station_id": int(station_id),
                "online_run_dictionary_csv": str(schedule_path),
                "date_from": str(date_from) if date_from is not None else None,
                "date_to": str(date_to) if date_to is not None else None,
                "window_candidate_z_positions": [],
                "window_selected_reason": "fallback to configured z_positions because no schedule rows overlapped the window",
            }
        raise ValueError("No online schedule rows overlapped the requested real-data date window.")

    selected_row = schedule_window.sort_values(["start_utc", "end_utc"], kind="mergesort").tail(1).iloc[0]
    z_vector = tuple(float(value) for value in selected_row["z_tuple"])
    candidates = [list(value) for value in sorted(set(schedule_window["z_tuple"].tolist()))]
    return z_vector, {
        "selection_mode": "real_window_latest",
        "selected_z_positions": list(z_vector),
        "station_id": int(station_id),
        "online_run_dictionary_csv": str(schedule_path),
        "date_from": str(date_from) if date_from is not None else None,
        "date_to": str(date_to) if date_to is not None else None,
        "window_candidate_z_positions": candidates,
        "window_selected_reason": "latest active schedule row in the requested window, ordered by start_utc then end_utc",
        "window_selected_schedule_start_utc": str(selected_row["start_utc"]),
        "window_selected_schedule_end_utc": str(selected_row["end_utc"]),
    }


def online_z_tuple_for_timestamp(ts: pd.Timestamp, schedule_df: pd.DataFrame) -> tuple[float, float, float, float] | None:
    if pd.isna(ts) or schedule_df.empty:
        return None
    keep = schedule_df["start_utc"] <= ts
    keep &= schedule_df["end_utc"].isna() | (schedule_df["end_utc"] >= ts)
    active = schedule_df.loc[keep]
    if active.empty:
        return None
    row = active.sort_values(["start_utc", "end_utc"], kind="mergesort").tail(1).iloc[0]
    return tuple(float(value) for value in row["z_tuple"])


def resolve_observed_efficiency_limits(config: dict[str, Any], *, limit_key: str) -> dict[int, float]:
    raw = config.get("filters", {}).get(limit_key, {})
    if raw in (None, "", "null", "None"):
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"filters.{limit_key} must be an object keyed by plane index.")
    limits: dict[int, float] = {}
    for key, value in raw.items():
        if value in (None, "", "null", "None"):
            continue
        limits[int(str(key))] = float(value)
    return limits


def apply_observed_efficiency_limits(
    dataframe: pd.DataFrame,
    *,
    lower_limits: dict[int, float],
    upper_limits: dict[int, float],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    row_count_before = int(len(dataframe))
    if not lower_limits and not upper_limits:
        return dataframe.copy(), {
            "row_count_before": row_count_before,
            "row_count_after": row_count_before,
            "affected_rows_total": 0,
            "limits_by_plane": {},
        }

    work = dataframe.copy()
    union_mask = pd.Series(False, index=work.index, dtype=bool)
    counts_by_plane: dict[str, int] = {}
    for plane_idx in sorted(set(lower_limits).union(upper_limits)):
        column = f"eff_empirical_{plane_idx}"
        if column not in work.columns:
            continue
        numeric = pd.to_numeric(work[column], errors="coerce")
        below_mask = pd.Series(False, index=work.index, dtype=bool)
        above_mask = pd.Series(False, index=work.index, dtype=bool)
        if plane_idx in lower_limits:
            below_mask = numeric.notna() & (numeric < float(lower_limits[plane_idx]))
        if plane_idx in upper_limits:
            above_mask = numeric.notna() & (numeric > float(upper_limits[plane_idx]))
        outside_mask = below_mask | above_mask
        counts_by_plane[str(plane_idx)] = int(outside_mask.sum())
        union_mask |= outside_mask
        work[column] = numeric

    if bool(union_mask.any()):
        work = work.loc[~union_mask].copy()

    return work, {
        "row_count_before": row_count_before,
        "row_count_after": int(len(work)),
        "affected_rows_total": int(union_mask.sum()),
        "affected_rows_by_plane": counts_by_plane,
        "limits_by_plane": {
            str(plane_idx): {
                "lower": float(lower_limits[plane_idx]) if plane_idx in lower_limits else None,
                "upper": float(upper_limits[plane_idx]) if plane_idx in upper_limits else None,
            }
            for plane_idx in sorted(set(lower_limits).union(upper_limits))
        },
    }


def q25(series: pd.Series) -> float:
    return float(series.quantile(0.25))


def q75(series: pd.Series) -> float:
    return float(series.quantile(0.75))


def quantize_efficiency_series(series: pd.Series, bin_width: float | None) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    if bin_width is None or float(bin_width) <= 0:
        return pd.Series(np.round(values, 6), index=series.index)
    width = float(bin_width)
    binned = np.round(values / width) * width
    binned = np.clip(binned, 0.0, 1.0)
    return pd.Series(np.round(binned, 6), index=series.index)


def assign_efficiency_bins(
    dataframe: pd.DataFrame,
    eff_columns: list[str],
    bin_width: float | None,
    *,
    suffix: str = "_bin",
) -> pd.DataFrame:
    out = dataframe.copy()
    for column in eff_columns:
        out[f"{column}{suffix}"] = quantize_efficiency_series(out[column], bin_width)
    return out


def assign_flux_bins(series: pd.Series, bin_count: int) -> tuple[pd.Series, np.ndarray]:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        return pd.Series(pd.NA, index=series.index, dtype="Int64"), np.asarray([], dtype=float)

    requested_bins = max(1, int(bin_count))
    effective_bins = min(requested_bins, int(valid.nunique()))
    try:
        codes, edges = pd.qcut(valid, q=effective_bins, labels=False, retbins=True, duplicates="drop")
    except ValueError:
        codes, edges = pd.cut(valid, bins=effective_bins, labels=False, retbins=True, include_lowest=True, duplicates="drop")

    out = pd.Series(pd.NA, index=series.index, dtype="Int64")
    out.loc[valid.index] = pd.Series(codes, index=valid.index, dtype="Int64")
    return out, np.asarray(edges, dtype=float)


def apply_lut_fallback_matches(
    dataframe: pd.DataFrame,
    lut_dataframe: pd.DataFrame,
    *,
    query_columns: list[str],
    raw_columns: list[str],
    match_mode: str,
    interpolation_k: int | None,
    interpolation_power: float,
) -> pd.DataFrame:
    if lut_dataframe.empty:
        raise ValueError("The LUT is empty.")

    work = dataframe.copy()
    for column in CANONICAL_EFF_COLUMNS:
        lut_column = f"lut_{column}"
        if lut_column not in work.columns:
            work[lut_column] = np.nan

    for column in ["lut_neighbor_count", "lut_neighbor_min_distance", "lut_neighbor_max_distance"]:
        if column not in work.columns:
            work[column] = np.nan

    exact_mask = work["lut_scale_factor"].notna()
    work.loc[exact_mask, "lut_neighbor_count"] = 1.0
    work.loc[exact_mask, "lut_neighbor_min_distance"] = 0.0
    work.loc[exact_mask, "lut_neighbor_max_distance"] = 0.0

    missing_mask = work["lut_scale_factor"].isna()
    if not missing_mask.any():
        return work

    normalized_mode = str(match_mode).strip().lower()
    if normalized_mode not in {"nearest", "interpolate"}:
        raise ValueError(f"Unsupported LUT match mode: {match_mode!r}")

    lut_matrix = lut_dataframe[CANONICAL_EFF_COLUMNS].to_numpy(dtype=float)
    distance_columns = raw_columns if normalized_mode == "interpolate" else query_columns
    query_matrix = work.loc[missing_mask, distance_columns].to_numpy(dtype=float)
    distances = np.sqrt(((query_matrix[:, None, :] - lut_matrix[None, :, :]) ** 2).sum(axis=2))

    best_indices = np.argmin(distances, axis=1)
    best_distances = distances[np.arange(len(best_indices)), best_indices]
    anchor_rows = lut_dataframe.iloc[best_indices].reset_index(drop=True)

    if normalized_mode == "nearest":
        work.loc[missing_mask, "lut_scale_factor"] = anchor_rows["scale_factor"].to_numpy(dtype=float)
        work.loc[missing_mask, "lut_match_method"] = "nearest"
        work.loc[missing_mask, "lut_match_distance"] = best_distances
        work.loc[missing_mask, "lut_neighbor_count"] = 1.0
        work.loc[missing_mask, "lut_neighbor_min_distance"] = best_distances
        work.loc[missing_mask, "lut_neighbor_max_distance"] = best_distances
        for column in CANONICAL_EFF_COLUMNS:
            work.loc[missing_mask, f"lut_{column}"] = anchor_rows[column].to_numpy(dtype=float)
        return work

    neighbor_count = int(interpolation_k) if interpolation_k is not None else 8
    neighbor_count = max(1, min(neighbor_count, len(lut_dataframe)))
    if neighbor_count == 1:
        work.loc[missing_mask, "lut_scale_factor"] = anchor_rows["scale_factor"].to_numpy(dtype=float)
        work.loc[missing_mask, "lut_match_method"] = "nearest"
        work.loc[missing_mask, "lut_match_distance"] = best_distances
        work.loc[missing_mask, "lut_neighbor_count"] = 1.0
        work.loc[missing_mask, "lut_neighbor_min_distance"] = best_distances
        work.loc[missing_mask, "lut_neighbor_max_distance"] = best_distances
        for column in CANONICAL_EFF_COLUMNS:
            work.loc[missing_mask, f"lut_{column}"] = anchor_rows[column].to_numpy(dtype=float)
        return work

    if float(interpolation_power) <= 0.0:
        raise ValueError("interpolation_power must be positive.")
    scale_values = lut_dataframe["scale_factor"].to_numpy(dtype=float)
    neighbor_indices = np.argpartition(distances, kth=neighbor_count - 1, axis=1)[:, :neighbor_count]
    neighbor_distances = np.take_along_axis(distances, neighbor_indices, axis=1)
    ordering = np.argsort(neighbor_distances, axis=1)
    neighbor_indices = np.take_along_axis(neighbor_indices, ordering, axis=1)
    neighbor_distances = np.take_along_axis(neighbor_distances, ordering, axis=1)
    neighbor_scales = scale_values[neighbor_indices]
    weights = 1.0 / np.maximum(neighbor_distances, 1e-9) ** float(interpolation_power)
    interpolated_scale = (weights * neighbor_scales).sum(axis=1) / weights.sum(axis=1)

    work.loc[missing_mask, "lut_scale_factor"] = interpolated_scale
    work.loc[missing_mask, "lut_match_method"] = "interpolated"
    work.loc[missing_mask, "lut_match_distance"] = best_distances
    work.loc[missing_mask, "lut_neighbor_count"] = float(neighbor_count)
    work.loc[missing_mask, "lut_neighbor_min_distance"] = neighbor_distances[:, 0]
    work.loc[missing_mask, "lut_neighbor_max_distance"] = neighbor_distances[:, -1]
    for column in CANONICAL_EFF_COLUMNS:
        work.loc[missing_mask, f"lut_{column}"] = anchor_rows[column].to_numpy(dtype=float)
    return work


def build_rate_to_flux_lines(reference_table: pd.DataFrame) -> pd.DataFrame:
    if reference_table.empty:
        return pd.DataFrame()
    curve = (
        reference_table.groupby("flux_bin_index", dropna=False)
        .agg(
            reference_rate_median=("reference_rate_median", "median"),
            flux_bin_center=("flux_bin_center", "median"),
        )
        .dropna(subset=["reference_rate_median", "flux_bin_center"])
        .reset_index(drop=True)
        .sort_values("reference_rate_median")
        .reset_index(drop=True)
    )
    if curve.empty:
        return pd.DataFrame()

    x_values = curve["reference_rate_median"].to_numpy(dtype=float)
    y_values = curve["flux_bin_center"].to_numpy(dtype=float)
    if len(curve) == 1 or np.unique(np.round(x_values, decimals=12)).size < 2:
        slope = 0.0
        intercept = float(np.mean(y_values))
        fit_method = "constant_fit"
        r_squared = np.nan
    else:
        try:
            slope, intercept = np.polyfit(x_values, y_values, deg=1)
            y_fit = slope * x_values + intercept
            ss_tot = float(np.sum((y_values - np.mean(y_values)) ** 2))
            ss_res = float(np.sum((y_values - y_fit) ** 2))
            r_squared = np.nan if ss_tot <= 0.0 else 1.0 - ss_res / ss_tot
            fit_method = "linear_fit"
        except (np.linalg.LinAlgError, ValueError):
            slope = 0.0
            intercept = float(np.mean(y_values))
            fit_method = "constant_fit_fallback"
            r_squared = np.nan

    return pd.DataFrame(
        [
            {
                "slope": float(slope),
                "intercept": float(intercept),
                "fit_method": fit_method,
                "n_reference_points": int(len(curve)),
                "reference_rate_min": float(np.min(x_values)),
                "reference_rate_max": float(np.max(x_values)),
                "reference_flux_min": float(np.min(y_values)),
                "reference_flux_max": float(np.max(y_values)),
                "reference_rate_mean": float(np.mean(x_values)),
                "reference_flux_mean": float(np.mean(y_values)),
                "r_squared": None if not np.isfinite(r_squared) else float(r_squared),
            }
        ]
    )


def apply_rate_to_flux_lines(rate_values: pd.Series, line_table: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    rate_numeric = pd.to_numeric(rate_values, errors="coerce")
    mapped = pd.Series(np.nan, index=rate_numeric.index, dtype=float)
    method = pd.Series("missing_rate", index=rate_numeric.index, dtype="object")
    if line_table.empty:
        method.loc[rate_numeric.notna()] = "missing_rate_to_flux_line"
        return mapped, method

    line = line_table.iloc[0]
    valid = rate_numeric.notna()
    mapped.loc[valid] = float(line["slope"]) * rate_numeric.loc[valid] + float(line["intercept"])
    method.loc[valid] = str(line.get("fit_method", "linear_fit"))
    return mapped, method


def resolve_time_axis(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, str]:
    for candidate in ("file_timestamp_utc", "execution_timestamp_utc", "time_utc"):
        if candidate not in dataframe.columns:
            continue
        parsed = pd.to_datetime(dataframe[candidate], errors="coerce", utc=True)
        if parsed.notna().any():
            order = np.argsort(parsed.fillna(parsed.min()))
            ordered = dataframe.iloc[order].reset_index(drop=True)
            ordered_time = parsed.iloc[order].dt.tz_convert(None).reset_index(drop=True)
            return ordered, ordered_time, candidate
    ordered = dataframe.reset_index(drop=True).copy()
    return ordered, pd.Series(np.arange(len(ordered)), dtype=float), "row_index"


def prepare_plot_frame(
    dataframe: pd.DataFrame,
    numeric_columns: list[str],
    *,
    apply_moving_average: bool,
    moving_average_kernel: int,
) -> pd.DataFrame:
    plot_frame = dataframe.copy()
    available_columns = [column for column in numeric_columns if column in plot_frame.columns]
    if available_columns:
        plot_frame[available_columns] = plot_frame[available_columns].apply(pd.to_numeric, errors="coerce")
    if not apply_moving_average or moving_average_kernel <= 1 or not available_columns:
        return plot_frame
    plot_frame[available_columns] = plot_frame[available_columns].rolling(
        window=moving_average_kernel,
        min_periods=1,
        center=True,
    ).mean()
    return plot_frame
