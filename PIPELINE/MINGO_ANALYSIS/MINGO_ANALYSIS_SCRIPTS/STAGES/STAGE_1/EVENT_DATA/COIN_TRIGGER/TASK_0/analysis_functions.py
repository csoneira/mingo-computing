"""Implement scientific calculations for coincidence Task 0."""

from __future__ import annotations

import re

import pandas as pd


RAW_CHANNEL_COLUMN_INDICES = {
    ("t", 1, "ef"): range(55, 59),
    ("t", 1, "eb"): range(59, 63),
    ("q", 1, "ef"): range(63, 67),
    ("q", 1, "eb"): range(67, 71),
    ("t", 2, "ef"): range(39, 43),
    ("t", 2, "eb"): range(43, 47),
    ("q", 2, "ef"): range(47, 51),
    ("q", 2, "eb"): range(51, 55),
    ("t", 3, "ef"): range(23, 27),
    ("t", 3, "eb"): range(27, 31),
    ("q", 3, "ef"): range(31, 35),
    ("q", 3, "eb"): range(35, 39),
    ("t", 4, "ef"): range(7, 11),
    ("t", 4, "eb"): range(11, 15),
    ("q", 4, "ef"): range(15, 19),
    ("q", 4, "eb"): range(19, 23),
}


def station_matches_file(file_name: str, station: str) -> bool:
    match = re.match(r"^mi0(?P<station>[0-9I]).*\.dat$", file_name, re.IGNORECASE)
    if match is None:
        return False
    label = match.group("station")
    file_station = "1" if label.upper() == "I" else label
    return int(file_station) == int(station)


def raw_channel_rename_map() -> dict[str, str]:
    rename_map: dict[str, str] = {}
    for (quantity, plane, end), idx_range in RAW_CHANNEL_COLUMN_INDICES.items():
        for strip, col_idx in enumerate(idx_range, start=1):
            rename_map[f"column_{col_idx}"] = f"p{plane}_s{strip}_{end}_{quantity}"
    return rename_map


def datetime_bounds(frame: pd.DataFrame) -> tuple[str, str]:
    if frame.empty or "datetime" not in frame.columns:
        return "", ""
    values = pd.to_datetime(frame["datetime"], errors="coerce").dropna()
    if values.empty:
        return "", ""
    return str(values.iloc[0]), str(values.iloc[-1])


def duration_seconds(frame: pd.DataFrame) -> int:
    if frame.empty or "datetime" not in frame.columns:
        return 0
    values = pd.to_datetime(frame["datetime"], errors="coerce").dropna()
    if values.empty:
        return 0
    return max(0, int((values.iloc[-1] - values.iloc[0]).total_seconds()))


def active_seconds(frame: pd.DataFrame) -> int:
    """Count distinct acquisition seconds represented by valid event rows."""
    if frame.empty or "datetime" not in frame.columns:
        return 0
    values = pd.to_datetime(frame["datetime"], errors="coerce").dropna()
    if values.empty:
        return 0
    return int(values.dt.floor("s").nunique())


def rate_hz(count: int, duration_seconds_value: int) -> float:
    if duration_seconds_value <= 0:
        return 0.0
    return round(float(count) / float(duration_seconds_value), 6)


def compute_tt_task0_acq(df: pd.DataFrame, column_name: str = "tt_task0_acq") -> pd.DataFrame:
    tt_str = pd.Series("", index=df.index, dtype="object")
    for plane in range(1, 5):
        charge_columns = [
            col
            for col in [
                f"p{plane}_s1_ef_q",
                f"p{plane}_s2_ef_q",
                f"p{plane}_s3_ef_q",
                f"p{plane}_s4_ef_q",
                f"p{plane}_s1_eb_q",
                f"p{plane}_s2_eb_q",
                f"p{plane}_s3_eb_q",
                f"p{plane}_s4_eb_q",
            ]
            if col in df.columns
        ]
        if charge_columns:
            has_charge = df.loc[:, charge_columns].ne(0).any(axis=1)
            tt_str = tt_str.where(~has_charge, tt_str + str(plane))
    df.loc[:, column_name] = tt_str.replace("", "0").astype(int)
    return df
