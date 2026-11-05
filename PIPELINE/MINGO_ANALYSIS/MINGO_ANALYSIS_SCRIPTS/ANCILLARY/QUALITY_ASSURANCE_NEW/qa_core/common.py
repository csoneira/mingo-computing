"""Shared helpers for the simplified QUALITY_ASSURANCE_NEW package."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.file_selection import extract_run_datetime_from_name

DEFAULT_DATE_RANGE_EXCLUDED_STATIONS = ["MINGO00"]
DEFAULT_TIME_COLUMNS_PRIORITY = ["execution_timestamp", "datetime"]


def normalize_station_name(station: Any) -> str:
    """Return normalized station folder names like MINGO01."""
    if isinstance(station, int):
        return f"MINGO{station:02d}"

    text = str(station).strip()
    if not text:
        raise ValueError("Empty station value.")

    if text.isdigit():
        return f"MINGO{int(text):02d}"

    upper = text.upper()
    if upper.startswith("MINGO"):
        suffix = upper.removeprefix("MINGO")
        if suffix.isdigit():
            return f"MINGO{int(suffix):02d}"
    raise ValueError(f"Invalid station value '{station}'.")


def load_yaml_mapping(config_path: Path, *, required: bool = False) -> dict[str, Any]:
    """Load a YAML mapping from disk."""
    if not config_path.exists():
        if required:
            raise FileNotFoundError(f"Config not found: {config_path}")
        return {}

    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Config must be a YAML mapping: {config_path}")
    return data


def deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge dictionaries."""
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = deep_merge_dicts(existing, value)
        else:
            merged[key] = value
    return merged


def parse_boundary(value: Any, *, end_of_day_if_date_only: bool) -> pd.Timestamp | None:
    """Parse a date/datetime boundary into a pandas timestamp."""
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        boundary = pd.to_datetime(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        boundary = pd.to_datetime(text, errors="coerce")

    if pd.isna(boundary):
        raise ValueError(f"Invalid date boundary '{value}'.")

    if end_of_day_if_date_only and isinstance(value, str) and len(value.strip()) <= 10:
        boundary = boundary + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    return boundary


def parse_timestamp_series(series: pd.Series) -> pd.Series:
    """Parse timestamp strings using the formats used in Stage 1 metadata."""
    as_text = series.astype("string").fillna("").str.strip()
    parsed = pd.to_datetime(as_text, format="%Y-%m-%d_%H.%M.%S", errors="coerce")
    if parsed.notna().all():
        return parsed

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        remaining = parsed.isna()
        if not remaining.any():
            break
        parsed.loc[remaining] = pd.to_datetime(as_text.loc[remaining], format=fmt, errors="coerce")
    return parsed


def parse_filename_timestamp_series(series: pd.Series) -> pd.Series:
    """Parse run datetimes from filename_base-like values."""
    as_text = series.astype("string").fillna("").str.strip()
    parsed = as_text.map(lambda value: extract_run_datetime_from_name(value) if value else None)
    return pd.to_datetime(parsed, errors="coerce")


def x_axis_config(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("x_axis")
    if not isinstance(raw, dict):
        raw = {}
    return {
        "mode": str(raw.get("mode", "filename_timestamp")).strip().lower(),
        "filename_column": str(raw.get("filename_column", "filename_base")).strip() or "filename_base",
        "column": raw.get("column"),
    }


def pick_time_column(df: pd.DataFrame, config: dict[str, Any]) -> str:
    priority = config.get("time_columns_priority") or list(DEFAULT_TIME_COLUMNS_PRIORITY)
    for candidate in priority:
        if candidate in df.columns:
            return candidate
    raise KeyError(
        "No preferred timestamp column found. "
        f"Looked for: {priority}. Available columns: {list(df.columns)}"
    )


def resolve_filter_timestamp(df: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.Series, str]:
    axis_cfg = x_axis_config(config)
    filename_column = axis_cfg["filename_column"]
    if filename_column in df.columns:
        from_filename = parse_filename_timestamp_series(df[filename_column])
        if from_filename.notna().any():
            return from_filename, f"{filename_column} (miXXYYDDDHHMMSS)"

    time_col = pick_time_column(df, config)
    parsed_time = parse_timestamp_series(df[time_col])
    if parsed_time.notna().any():
        return parsed_time, time_col

    raise KeyError(
        "Could not resolve timestamp values for filtering. "
        f"Tried filename column '{filename_column}' and priority columns "
        f"{config.get('time_columns_priority') or list(DEFAULT_TIME_COLUMNS_PRIORITY)}."
    )


def resolve_plot_x_axis(df: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.Series, str, bool]:
    axis_cfg = x_axis_config(config)
    mode = axis_cfg["mode"]

    if mode == "filename_timestamp":
        filename_column = axis_cfg["filename_column"]
        if filename_column in df.columns:
            parsed = parse_filename_timestamp_series(df[filename_column])
            if parsed.notna().any():
                return parsed, filename_column, True
        return df["__timestamp__"], "__timestamp__", True

    if mode == "column":
        column = axis_cfg.get("column")
        if column is None:
            return df["__timestamp__"], "__timestamp__", True
        column_name = str(column).strip()
        if not column_name:
            return df["__timestamp__"], "__timestamp__", True
        if column_name not in df.columns:
            raise KeyError(f"x_axis.column='{column_name}' not present in metadata.")

        numeric = pd.to_numeric(df[column_name], errors="coerce")
        if numeric.notna().any():
            return numeric, column_name, False

        parsed = parse_timestamp_series(df[column_name])
        if parsed.notna().any():
            return parsed, column_name, True

        raise ValueError(f"x_axis.column='{column_name}' could not be parsed as numeric or datetime.")

    raise ValueError("Invalid x_axis.mode. Use one of: filename_timestamp, column.")


def apply_date_filter(df: pd.DataFrame, date_range: dict[str, Any] | None) -> pd.DataFrame:
    """Apply optional date filtering using the resolved __timestamp__ column."""
    if date_range is None:
        return df

    start = parse_boundary(date_range.get("start"), end_of_day_if_date_only=False)
    end = parse_boundary(date_range.get("end"), end_of_day_if_date_only=True)

    mask = pd.Series(True, index=df.index)
    if start is not None:
        mask &= df["__timestamp__"] >= start
    if end is not None:
        mask &= df["__timestamp__"] <= end
    return df.loc[mask].copy()


def get_station_date_range(config: dict[str, Any], station: Any) -> dict[str, Any] | None:
    """Return effective date range for a station, or None when disabled."""
    date_range = config.get("date_range")
    if not isinstance(date_range, dict):
        return None

    start = date_range.get("start")
    end = date_range.get("end")
    if start in (None, "") and end in (None, ""):
        return None

    excluded = config.get("date_range_excluded_stations", DEFAULT_DATE_RANGE_EXCLUDED_STATIONS)
    excluded_set = {normalize_station_name(value) for value in excluded if str(value).strip()}
    station_name = normalize_station_name(station)
    if station_name in excluded_set:
        return None
    return {"start": start, "end": end}


def metadata_path(repo_root: Path, station_name: str, task_id: int, metadata_csv_filename: str) -> Path:
    return (
        repo_root
        / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
        / station_name
        / "STAGE_1_PRODUCTS"
        / "EVENT_DATA"
        / "METADATA"
        / f"TASK_{task_id}"
        / metadata_csv_filename
    )


def ensure_station_tree(base_dir: Path, stations: list[Any]) -> None:
    for station in stations:
        station_name = normalize_station_name(station)
        (base_dir / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / station_name / "OUTPUTS" / "FILES").mkdir(parents=True, exist_ok=True)
        (base_dir / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / station_name / "OUTPUTS" / "PLOTS").mkdir(parents=True, exist_ok=True)


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path, low_memory=False)
    return pd.DataFrame()


OVERWRITTEN_REPORT_COLUMNS = [
    "filename_base",
    "overwritten_status",
    "overwritten_reason",
    "source_row_index",
    "kept_source_row_index",
    "duplicate_count",
    "dedupe_timestamp_column",
    "row_dedupe_timestamp",
    "kept_dedupe_timestamp",
]


def _metadata_dedupe_timestamp(df: pd.DataFrame) -> tuple[pd.Series, str]:
    for column_name in ("execution_timestamp", "execution_date", "datetime", "timestamp"):
        if column_name not in df.columns:
            continue
        parsed = parse_timestamp_series(df[column_name])
        missing = parsed.isna()
        if missing.any():
            parsed.loc[missing] = pd.to_datetime(df.loc[missing, column_name], errors="coerce")
        if parsed.notna().any():
            return parsed, column_name
    return pd.Series(pd.NaT, index=df.index), ""


def deduplicate_metadata_rows_with_report(meta_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep the latest metadata row per basename and report overwritten duplicates."""
    if meta_df.empty or "filename_base" not in meta_df.columns:
        return (
            pd.DataFrame(columns=["filename_base"]),
            pd.DataFrame(columns=OVERWRITTEN_REPORT_COLUMNS),
        )

    df = meta_df.copy()
    original_columns = list(df.columns)
    df["__qa_source_row_index"] = range(len(df))
    df["filename_base"] = df["filename_base"].astype("string").fillna("").str.strip()
    df = df[df["filename_base"] != ""].copy()
    if df.empty:
        return (
            pd.DataFrame(columns=["filename_base"]),
            pd.DataFrame(columns=OVERWRITTEN_REPORT_COLUMNS + [column for column in original_columns if column != "filename_base"]),
        )

    dedupe_timestamp, timestamp_column = _metadata_dedupe_timestamp(df)
    df["__qa_dedupe_timestamp"] = dedupe_timestamp
    df["__qa_dedupe_has_timestamp"] = df["__qa_dedupe_timestamp"].notna()

    sorted_df = df.sort_values(
        [
            "filename_base",
            "__qa_dedupe_has_timestamp",
            "__qa_dedupe_timestamp",
            "__qa_source_row_index",
        ],
        ascending=[True, True, True, True],
        na_position="first",
        kind="mergesort",
    )
    kept_df = sorted_df.drop_duplicates(subset=["filename_base"], keep="last").copy()

    duplicate_mask = sorted_df.duplicated(subset=["filename_base"], keep=False)
    duplicate_df = sorted_df.loc[duplicate_mask].copy()
    kept_lookup = kept_df[
        ["filename_base", "__qa_source_row_index", "__qa_dedupe_timestamp"]
    ].rename(
        columns={
            "__qa_source_row_index": "kept_source_row_index",
            "__qa_dedupe_timestamp": "kept_dedupe_timestamp",
        }
    )
    duplicate_df = duplicate_df.merge(kept_lookup, on="filename_base", how="left")
    overwritten_df = duplicate_df[
        duplicate_df["__qa_source_row_index"] != duplicate_df["kept_source_row_index"]
    ].copy()

    if overwritten_df.empty:
        report_df = pd.DataFrame(columns=OVERWRITTEN_REPORT_COLUMNS + [column for column in original_columns if column != "filename_base"])
    else:
        duplicate_counts = sorted_df.groupby("filename_base", dropna=False).size().rename("duplicate_count")
        overwritten_df = overwritten_df.merge(duplicate_counts, on="filename_base", how="left")
        report_df = overwritten_df[[column for column in original_columns if column != "filename_base"]].copy()
        report_df.insert(0, "kept_dedupe_timestamp", overwritten_df["kept_dedupe_timestamp"])
        report_df.insert(0, "row_dedupe_timestamp", overwritten_df["__qa_dedupe_timestamp"])
        report_df.insert(0, "dedupe_timestamp_column", timestamp_column)
        report_df.insert(0, "duplicate_count", overwritten_df["duplicate_count"].astype("Int64"))
        report_df.insert(0, "kept_source_row_index", overwritten_df["kept_source_row_index"].astype("Int64"))
        report_df.insert(0, "source_row_index", overwritten_df["__qa_source_row_index"].astype("Int64"))
        report_df.insert(0, "overwritten_reason", "newer_metadata_row_for_same_filename_base")
        report_df.insert(0, "overwritten_status", "overwritten")
        report_df.insert(0, "filename_base", overwritten_df["filename_base"].astype(str))

    deduped_df = kept_df[original_columns].copy()
    return deduped_df.reset_index(drop=True), report_df.reset_index(drop=True)


def deduplicate_metadata_rows(meta_df: pd.DataFrame) -> pd.DataFrame:
    """Keep the latest metadata row per basename when duplicates exist."""
    deduped_df, _ = deduplicate_metadata_rows_with_report(meta_df)
    return deduped_df
