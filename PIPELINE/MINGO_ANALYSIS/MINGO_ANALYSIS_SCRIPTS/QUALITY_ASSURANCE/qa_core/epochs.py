"""Helpers for loading and matching Stage 0 online-run configuration epochs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.file_selection import extract_run_datetime_from_name

from .common import normalize_station_name

_END_OF_DAY = pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
_COLUMN_RENAME_MAP = {
    "station": "station_number",
    "conf": "conf_number",
    "start": "start_date",
    "end": "end_date",
    "over_P1": "lead_over_p1_mm",
    "P1-P2": "lead_p1_p2_mm",
    "P2-P3": "lead_p2_p3_mm",
    "P3-P4": "lead_p3_p4_mm",
    "P1": "z_p1_mm",
    "P2": "z_p2_mm",
    "P3": "z_p3_mm",
    "P4": "z_p4_mm",
    "C1": "trigger_c1",
    "C2": "trigger_c2",
    "C3": "trigger_c3",
    "C4": "trigger_c4",
    "phi_north": "phi_north_deg",
    "city": "location",
    "comment": "comment",
}
_NUMERIC_COLUMNS = (
    "station_number",
    "conf_number",
    "lead_over_p1_mm",
    "lead_p1_p2_mm",
    "lead_p2_p3_mm",
    "lead_p3_p4_mm",
    "z_p1_mm",
    "z_p2_mm",
    "z_p3_mm",
    "z_p4_mm",
    "phi_north_deg",
)


def online_run_dictionary_path(repo_root: Path, station: str | int) -> Path:
    """Return the online-run dictionary CSV for a station."""
    station_name = normalize_station_name(station)
    station_number = int(station_name.removeprefix("MINGO"))
    return (
        repo_root
        / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS"
        / "SUPPORT" / "CONFIG_FILES"
        / "STAGE_0"
        / "ONLINE_RUN_DICTIONARY"
        / f"STATION_{station_number}"
        / f"input_file_mingo{station_number:02d}.csv"
    )


def _flatten_online_run_columns(columns: Any) -> list[str]:
    flattened: list[str] = []
    for column in columns:
        if isinstance(column, tuple):
            parts = [str(item).strip() for item in column if not pd.isna(item) and str(item).strip()]
            flattened.append(parts[-1] if parts else "")
        else:
            flattened.append(str(column).strip())
    return flattened


def _format_epoch_token(value: Any) -> str:
    if pd.isna(value):
        return "na"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y%m%d")
    return str(value)


def _build_epoch_id(row: pd.Series) -> str:
    station_name = row.get("station_name") or "UNKNOWN"
    conf = row.get("conf_number")
    conf_token = f"{int(conf):02d}" if pd.notna(conf) else "na"
    start_token = _format_epoch_token(row.get("start_date"))
    end_token = _format_epoch_token(row.get("end_date"))
    return f"{station_name}_conf_{conf_token}_{start_token}_{end_token}"


def _mark_boundary_overlaps(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["boundary_overlap"] = False
    if df.empty:
        return df

    for idx in range(len(df) - 1):
        current_end = df.loc[idx, "end_timestamp"]
        next_start = df.loc[idx + 1, "start_timestamp"]
        if pd.isna(current_end) or pd.isna(next_start):
            continue
        if current_end >= next_start:
            df.loc[idx, "boundary_overlap"] = True
            df.loc[idx + 1, "boundary_overlap"] = True
    return df


def load_online_run_dictionary(repo_root: Path, station: str | int) -> pd.DataFrame:
    """Load and normalize one station online-run dictionary."""
    path = online_run_dictionary_path(repo_root, station)
    if not path.exists():
        raise FileNotFoundError(f"Online-run dictionary not found: {path}")

    raw = pd.read_csv(path, header=[0, 1])
    raw.columns = _flatten_online_run_columns(raw.columns)
    df = raw.rename(columns=_COLUMN_RENAME_MAP).copy()

    missing = {"station_number", "conf_number", "start_date", "end_date"} - set(df.columns)
    if missing:
        raise ValueError(f"Online-run dictionary is missing required columns {sorted(missing)}: {path}")

    for column in _NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    for column in ("trigger_c1", "trigger_c2", "trigger_c3", "trigger_c4"):
        if column in df.columns:
            df[column] = df[column].astype("string").str.strip()

    for column in ("location", "comment"):
        if column in df.columns:
            df[column] = df[column].astype("string").str.strip()

    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce").dt.normalize()
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce").dt.normalize()
    df["start_timestamp"] = df["start_date"]
    df["end_timestamp"] = df["end_date"] + _END_OF_DAY

    requested_station = normalize_station_name(station)
    if df["station_number"].notna().any():
        df["station_name"] = df["station_number"].map(
            lambda value: normalize_station_name(int(value)) if pd.notna(value) else requested_station
        )
    else:
        df["station_name"] = requested_station

    df = df.sort_values(["start_timestamp", "conf_number"], kind="stable").reset_index(drop=True)
    df = _mark_boundary_overlaps(df)
    df["epoch_id"] = df.apply(_build_epoch_id, axis=1)
    df["source_csv"] = str(path)
    return df


def load_all_online_run_dictionaries(
    repo_root: Path, stations: Iterable[str | int] | None = None
) -> pd.DataFrame:
    """Load and concatenate online-run dictionaries for multiple stations."""
    if stations is None:
        root = repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS" / "SUPPORT" / "CONFIG_FILES" / "STAGE_0" / "ONLINE_RUN_DICTIONARY"
        stations = sorted(int(path.name.split("_", 1)[1]) for path in root.glob("STATION_*"))

    frames = [load_online_run_dictionary(repo_root, station) for station in stations]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def match_epoch(
    timestamp: Any,
    epochs_df: pd.DataFrame,
    *,
    allow_nearest: bool = False,
) -> pd.Series | None:
    """Match a timestamp against a normalized epoch table."""
    ts = pd.to_datetime(timestamp, errors="coerce")
    if pd.isna(ts):
        raise ValueError(f"Invalid timestamp '{timestamp}'.")

    candidates = epochs_df[
        epochs_df["start_timestamp"].notna()
        & (epochs_df["start_timestamp"] <= ts)
        & (epochs_df["end_timestamp"].isna() | (ts <= epochs_df["end_timestamp"]))
    ]
    if not candidates.empty:
        return candidates.sort_values(["start_timestamp", "conf_number"], kind="stable").iloc[-1]

    if not allow_nearest:
        return None

    with_distance = epochs_df.copy()
    with_distance["__distance__"] = pd.Series(
        pd.NaT, index=with_distance.index, dtype="timedelta64[ns]"
    )

    before_mask = with_distance["end_timestamp"].notna() & (ts > with_distance["end_timestamp"])
    after_mask = with_distance["start_timestamp"].notna() & (ts < with_distance["start_timestamp"])

    with_distance.loc[before_mask, "__distance__"] = ts - with_distance.loc[before_mask, "end_timestamp"]
    with_distance.loc[after_mask, "__distance__"] = with_distance.loc[after_mask, "start_timestamp"] - ts
    with_distance = with_distance[with_distance["__distance__"].notna()]
    if with_distance.empty:
        return None

    nearest = with_distance.sort_values(["__distance__", "start_timestamp", "conf_number"], kind="stable").iloc[0]
    return nearest.drop(labels="__distance__")


def match_epoch_for_run_name(
    run_name: str, epochs_df: pd.DataFrame, *, allow_nearest: bool = False
) -> pd.Series | None:
    """Match a run filename like mi0324359180521 to an epoch."""
    run_dt = extract_run_datetime_from_name(str(run_name).strip())
    if run_dt is None:
        raise ValueError(f"Could not extract a timestamp from run name '{run_name}'.")
    return match_epoch(run_dt, epochs_df, allow_nearest=allow_nearest)


def attach_epoch_ids(
    df: pd.DataFrame,
    timestamp_column: str,
    epochs_df: pd.DataFrame,
    *,
    output_column: str = "epoch_id",
    allow_nearest: bool = False,
) -> pd.DataFrame:
    """Attach epoch identifiers to a dataframe using a timestamp column."""
    if timestamp_column not in df.columns:
        raise KeyError(f"Timestamp column '{timestamp_column}' not found.")

    timestamps = pd.to_datetime(df[timestamp_column], errors="coerce")
    epoch_ids: list[str | None] = []
    for timestamp in timestamps:
        if pd.isna(timestamp):
            epoch_ids.append(None)
            continue
        match = match_epoch(timestamp, epochs_df, allow_nearest=allow_nearest)
        epoch_ids.append(None if match is None else str(match["epoch_id"]))

    out = df.copy()
    out[output_column] = pd.array(epoch_ids, dtype="string")
    return out
