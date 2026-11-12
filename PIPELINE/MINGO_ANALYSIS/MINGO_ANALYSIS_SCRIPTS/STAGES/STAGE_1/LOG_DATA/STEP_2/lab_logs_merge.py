#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Merge station laboratory logs into the analysis metadata."""

from __future__ import annotations

import argparse
import io
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import yaml

CURRENT_PATH = Path(__file__).resolve()
_SCRIPTS_ROOT = next(parent for parent in CURRENT_PATH.parents if parent.name == "MINGO_ANALYSIS_SCRIPTS")
_REPO_IMPORT_ROOT = _SCRIPTS_ROOT.parents[2]
if str(_REPO_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_IMPORT_ROOT))
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root
REPO_ROOT = get_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.execution_logger import set_station, start_timer
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import (
    get_master_config_root,
    get_repo_root,
    resolve_home_path_from_config,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.selection_config import (
    date_in_ranges as day_overlaps_date_ranges,
    datetime_in_ranges,
    effective_date_ranges_for_station,
    format_date_range_for_display,
    load_selection_for_paths,
    station_is_selected,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.status_csv import append_status_row, mark_status_complete

CREATE_NEW_CSV = True


@dataclass(frozen=True)
class LogSpec:
    name: str
    prefixes: Sequence[str]
    columns: Sequence[str]


LOG_SPECS: Sequence[LogSpec] = (
    LogSpec(
        name="hv",
        prefixes=("hv0_",),
        columns=(
            "Date",
            "Hour",
            "Unused1",
            "Unused2",
            "Unused3",
            "Unused4",
            "Unused5",
            "Unused6",
            "CurrentNeg",
            "CurrentPos",
            "HVneg",
            "HVpos",
            "Unused7",
            "Unused8",
            "Unused9",
            "Unused10",
            "Unused11",
            "Unused12",
            "Unused13",
            "Unused14",
            "Unused15",
        ),
    ),
    LogSpec(
        name="rates",
        prefixes=("rates_",),
        columns=(
            "Date",
            "Hour",
            "Asserted",
            "Edge",
            "Accepted",
            "Multiplexer1",
            "M2",
            "M3",
            "M4",
            "CM1",
            "CM2",
            "CM3",
            "CM4",
        ),
    ),
    LogSpec(
        name="sensors_ext",
        prefixes=("sensors_bus0_",),
        columns=(
            "Date",
            "Hour",
            "Unused1",
            "Unused2",
            "Unused3",
            "Unused4",
            "Temperature_ext",
            "RH_ext",
            "Pressure_ext",
        ),
    ),
    LogSpec(
        name="sensors_int",
        prefixes=("sensors_bus1_",),
        columns=(
            "Date",
            "Hour",
            "Unused1",
            "Unused2",
            "Unused3",
            "Unused4",
            "Temperature_int",
            "RH_int",
            "Pressure_int",
        ),
    ),
    LogSpec(
        name="odroid",
        prefixes=("Odroid_",),
        columns=(
            "Date",
            "Hour",
            "DiskFill1",
            "DiskFill2",
            "DiskFillX",
        ),
    ),
    LogSpec(
        name="flow",
        prefixes=("Flow",),
        columns=("Date", "Hour", "FlowRate1", "FlowRate2", "FlowRate3", "FlowRate4"),
    ),
)

MASTER_CONFIG_ROOT = get_master_config_root()
LAB_LOGS_CONFIG_SHARED = MASTER_CONFIG_ROOT / "STAGE_1" / "LOG_DATA" / "config_lab_logs.yaml"
LAB_LOGS_CONFIG_STEP2 = MASTER_CONFIG_ROOT / "STAGE_1" / "LOG_DATA" / "STEP_2" / "config_step_2.yaml"
LAB_LOGS_OUTLIER_CSV_STEP2 = MASTER_CONFIG_ROOT / "STAGE_1" / "LOG_DATA" / "STEP_2" / "config_step_2.csv"
FILENAME_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class BackupSeriesSpec:
    output_column: str
    schema_kind: str
    table: str


BACKUP_SERIES_SPECS: Sequence[BackupSeriesSpec] = (
    BackupSeriesSpec("sensors_ext_Temperature_ext", "station", "Temp"),
    BackupSeriesSpec("sensors_ext_RH_ext", "station", "HR"),
    BackupSeriesSpec("sensors_ext_Pressure_ext", "station", "Press"),
    BackupSeriesSpec("sensors_int_Temperature_int", "DAQ01", "Temp"),
    BackupSeriesSpec("sensors_int_RH_int", "DAQ01", "HR"),
    BackupSeriesSpec("sensors_int_Pressure_int", "DAQ01", "Press"),
)
LOCAL_LOG_BACKUP_LAYOUTS: Mapping[str, Mapping[str, int]] = {
    # Zero-based positions after the timestamp in each raw backup line.
    "hv": {
        "hv_CurrentNeg": 6, "hv_CurrentPos": 7,
        "hv_HVneg": 8, "hv_HVpos": 9,
    },
    "rates": {
        "rates_Asserted": 0, "rates_Edge": 1, "rates_Accepted": 2,
        "rates_Multiplexer1": 3, "rates_M2": 4, "rates_M3": 5,
        "rates_M4": 6, "rates_CM1": 7, "rates_CM2": 8,
        "rates_CM3": 9, "rates_CM4": 10,
    },
    "sensors_ext": {
        "sensors_ext_Temperature_ext": 4,
        "sensors_ext_RH_ext": 5,
        "sensors_ext_Pressure_ext": 6,
    },
    "sensors_int": {
        "sensors_int_Temperature_int": 4,
        "sensors_int_RH_int": 5,
        "sensors_int_Pressure_int": 6,
    },
    "odroid": {
        "odroid_DiskFill1": 0, "odroid_DiskFill2": 1,
        "odroid_DiskFillX": 2,
    },
    "flow": {
        "flow_FlowRate1": 0, "flow_FlowRate2": 1,
        "flow_FlowRate3": 2, "flow_FlowRate4": 3,
    },
}
LOCAL_LOG_BACKUP_REQUIRED_COLUMNS = frozenset(
    column for layout in LOCAL_LOG_BACKUP_LAYOUTS.values() for column in layout
)


def _load_yaml_mapping(path: Path) -> Mapping[str, object]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _parse_date_value(value: object) -> Optional[date]:
    if value in ("", None):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z") and "T" in text:
        text = text[:-1] + "+00:00"
    parsed: Optional[datetime] = None
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            if fmt is None:
                parsed = datetime.fromisoformat(text)
            else:
                parsed = datetime.strptime(text, fmt)
            break
        except Exception:
            parsed = None
    if parsed is None:
        return None
    return parsed.date()


def _collect_date_ranges(node: Mapping[str, object], ranges: List[Tuple[Optional[date], Optional[date]]]) -> None:
    if not isinstance(node, dict):
        return
    legacy = node.get("date_range")
    if isinstance(legacy, dict):
        start_val = _parse_date_value(legacy.get("start"))
        end_val = _parse_date_value(legacy.get("end"))
        if start_val is not None or end_val is not None:
            ranges.append((start_val, end_val))
    range_list = node.get("date_ranges")
    if isinstance(range_list, list):
        for item in range_list:
            if not isinstance(item, dict):
                continue
            start_val = _parse_date_value(item.get("start"))
            end_val = _parse_date_value(item.get("end"))
            if start_val is None and end_val is None:
                continue
            ranges.append((start_val, end_val))
    nested = node.get("lab_logs_date_selection")
    if isinstance(nested, dict):
        _collect_date_ranges(nested, ranges)


def load_lab_logs_date_ranges(
    station: Optional[int | str] = None,
) -> List[Tuple[Optional[datetime], Optional[datetime]]]:
    selection = load_selection_for_paths(
        [LAB_LOGS_CONFIG_SHARED, LAB_LOGS_CONFIG_STEP2],
        master_config_root=MASTER_CONFIG_ROOT,
    )
    if station is None:
        return list(selection.date_ranges)
    return list(effective_date_ranges_for_station(station, selection))


def extract_date_from_filename(path: Path) -> Optional[date]:
    match = FILENAME_DATE_RE.search(path.name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def date_in_ranges(day_value: date, ranges: Sequence[Tuple[Optional[date], Optional[date]]]) -> bool:
    for start_day, end_day in ranges:
        if start_day is not None and day_value < start_day:
            continue
        if end_day is not None and day_value > end_day:
            continue
        return True
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate cleaned lab log files into daily outputs."
    )
    parser.add_argument("station", help="Station identifier (e.g. 1, 2, 3, 4)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show actions without moving or writing files.",
    )
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Rebuild outputs using files already archived in COMPLETED.",
    )
    return parser.parse_args()


def load_outlier_limits() -> Dict[str, Sequence[float]]:
    config_file_path = LAB_LOGS_OUTLIER_CSV_STEP2
    try:
        config_df = pd.read_csv(config_file_path)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Outlier limits CSV not found: {config_file_path}"
        ) from exc

    if config_df.empty:
        return {}

    normalized_columns = {str(col).strip().lower(): col for col in config_df.columns}
    required = ("column", "lower", "upper")
    if not all(name in normalized_columns for name in required):
        raise ValueError(
            f"{config_file_path} must include the columns: column, lower, upper"
        )

    column_col = normalized_columns["column"]
    lower_col = normalized_columns["lower"]
    upper_col = normalized_columns["upper"]

    limits: Dict[str, Sequence[float]] = {}
    for index, row in config_df.iterrows():
        column_name = str(row[column_col]).strip()
        if not column_name or column_name.lower() == "nan":
            continue
        try:
            lower = float(row[lower_col])
            upper = float(row[upper_col])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid numeric bounds in {config_file_path} at row {index + 2}"
            ) from exc
        limits[column_name] = (lower, upper)

    return limits


def move_step1_outputs_to_unprocessed(
    step1_output_dir: Path,
    unprocessed_root: Path,
    dry_run: bool,
) -> Dict[Path, Path]:
    planned_moves: Dict[Path, Path] = {}
    if not step1_output_dir.exists():
        return planned_moves

    files = sorted(path for path in step1_output_dir.glob("**/*") if path.is_file())
    if not dry_run:
        unprocessed_root.mkdir(parents=True, exist_ok=True)

    for source in files:
        relative = source.relative_to(step1_output_dir)
        destination = unprocessed_root / relative

        if dry_run:
            print(f"  [dry-run] move {source} -> {destination}")
            planned_moves[destination] = source
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.is_file():
                destination.unlink()
            else:
                shutil.rmtree(destination)
        shutil.move(str(source), str(destination))
        planned_moves[destination] = destination

    if not dry_run:
        _cleanup_empty_directories(step1_output_dir)

    return planned_moves


def _cleanup_empty_directories(root: Path) -> None:
    for directory in sorted(
        (path for path in root.glob("**/*") if path.is_dir()), reverse=True
    ):
        try:
            directory.rmdir()
        except OSError:
            break


def match_spec(file_name: str) -> LogSpec | None:
    for spec in LOG_SPECS:
        if any(file_name.startswith(prefix) for prefix in spec.prefixes):
            return spec
    return None


def read_clean_log(path: Path, spec: LogSpec) -> pd.DataFrame:
    try:
        df = pd.read_csv(
            path,
            sep=r"\s+",
            header=None,
            engine="python",
            on_bad_lines="skip",
        )
    except FileNotFoundError:
        return pd.DataFrame()

    if df.empty:
        return df

    if len(df.columns) > len(spec.columns):
        df = df.iloc[:, : len(spec.columns)]
    elif len(df.columns) < len(spec.columns):
        for _ in range(len(spec.columns) - len(df.columns)):
            df[len(df.columns)] = pd.NA

    df.columns = spec.columns
    drop_columns = [col for col in df.columns if col.lower().startswith("unused")]
    df = df.drop(columns=drop_columns, errors="ignore")

    if "Date" in df.columns and "Hour" in df.columns:
        df["Time"] = pd.to_datetime(
            df["Date"].astype(str) + "T" + df["Hour"].astype(str), errors="coerce"
        )
        df = df.drop(columns=["Date", "Hour"])

    if "Time" not in df.columns:
        return pd.DataFrame()

    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df = df.dropna(subset=["Time"])

    value_columns = [col for col in df.columns if col != "Time"]
    if not value_columns:
        return pd.DataFrame()

    for column in value_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.set_index("Time").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df = df.rename(columns=lambda col: f"{spec.name}_{col}")

    return df


def apply_outlier_filters(df: pd.DataFrame, limits: Mapping[str, Sequence[float]]) -> None:
    for column, (lower, upper) in limits.items():
        if column in df.columns:
            df[column] = df[column].where(
                (df[column] >= lower) & (df[column] <= upper), np.nan
            )


def archive_processed_files(
    processed_files: Iterable[Path],
    unprocessed_root: Path,
    completed_root: Path,
    dry_run: bool,
) -> None:
    for source in processed_files:
        try:
            relative = source.relative_to(unprocessed_root)
        except ValueError:
            continue

        destination = completed_root / relative
        if dry_run:
            print(f"  [dry-run] move {source} -> {destination}")
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.is_file():
                destination.unlink()
            else:
                shutil.rmtree(destination)
        shutil.move(str(source), str(destination))

    if not dry_run:
        _cleanup_empty_directories(unprocessed_root)


def rebuild_big_csv(
    output_root: Path,
    big_csv_path: Path,
    dry_run: bool,
) -> None:
    output_files = sorted(
        path for path in output_root.rglob("lab_logs_*.csv") if path.is_file()
    )
    if dry_run:
        if output_files:
            print(f"  [dry-run] would rebuild {big_csv_path}")
        return

    if not output_files:
        if big_csv_path.exists():
            big_csv_path.unlink()
        return

    frames: List[pd.DataFrame] = []
    for file_path in output_files:
        try:
            df = pd.read_csv(file_path, parse_dates=["Time"])
        except Exception as exc:  # pragma: no cover - best effort logging
            print(f"Warning: unable to load {file_path}: {exc}")
            continue
        frames.append(df)

    if not frames:
        return

    combined = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset="Time", keep="last")
        .sort_values("Time")
    )
    combined.to_csv(big_csv_path, index=False, float_format="%.5g")


def resolve_actual_path(path: Path, moves: Mapping[Path, Path]) -> Path:
    return moves.get(path, path)


def _coerce_station_id(station: int | str) -> Optional[int]:
    try:
        return int(str(station).strip())
    except Exception:
        return None


def _backup_schema_name(spec: BackupSeriesSpec, station_id: int) -> str:
    if spec.schema_kind == "station":
        return f"mingo0{station_id}"
    return spec.schema_kind


def _load_backup_restore_config() -> Mapping[str, object]:
    shared_config = _load_yaml_mapping(LAB_LOGS_CONFIG_SHARED)
    step2_config = _load_yaml_mapping(LAB_LOGS_CONFIG_STEP2)

    for config in (step2_config, shared_config):
        backup_config = config.get("backup_restore")
        if isinstance(backup_config, Mapping):
            return backup_config
    return {}


def _station_dump_path(
    backup_config: Mapping[str, object],
    station_id: int,
) -> Optional[str]:
    raw_paths = backup_config.get("station_dump_paths")
    if not isinstance(raw_paths, Mapping):
        return None

    for key in (station_id, str(station_id), f"MINGO0{station_id}", f"mingo0{station_id}"):
        value = raw_paths.get(key)
        if value:
            return str(value).strip()
    return None


def _local_log_backup_root(backup_config: Mapping[str, object]) -> Optional[Path]:
    raw_root = backup_config.get("local_log_backup_root")
    if not raw_root:
        return None
    root = Path(str(raw_root)).expanduser()
    if not root.is_absolute():
        root = get_repo_root() / root
    return root if root.exists() else None


def _local_log_backup_host_dir(
    backup_root: Path,
    station_id: int,
) -> Path:
    return backup_root / "hosts" / f"mingo{station_id:02d}" / "current"


def _load_local_backup_log(
    path: Path,
    value_layout: Mapping[str, int],
) -> pd.DataFrame:
    """Parse one raw local-backup log without assuming a split date/time."""
    output_columns = tuple(value_layout)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return pd.DataFrame(columns=["Time", *output_columns])

    records: List[Dict[str, object]] = []
    for line in lines:
        tokens = [token for token in re.split(r"[;\s]+", line.strip()) if token]
        if not tokens:
            continue
        if (
            len(tokens) >= 2
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", tokens[0])
            and re.fullmatch(r"\d{2}:\d{2}:\d{2}(?:\.\d+)?", tokens[1])
        ):
            timestamp = f"{tokens[0]}T{tokens[1]}"
            raw_values = tokens[2:]
        else:
            timestamp = tokens[0]
            raw_values = tokens[1:]
        record: Dict[str, object] = {"Time": timestamp}
        for column, raw_index in value_layout.items():
            record[column] = (
                raw_values[raw_index] if raw_index < len(raw_values) else pd.NA
            )
        records.append(record)

    if not records:
        return pd.DataFrame(columns=["Time", *output_columns])
    df = pd.DataFrame.from_records(records, columns=["Time", *output_columns])
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df = df.dropna(subset=["Time"])
    for column in output_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return (
        df.loc[:, ["Time", *output_columns]]
        .drop_duplicates(subset=["Time"], keep="last")
        .sort_values("Time")
    )


def restore_outputs_from_local_log_backup(
    *,
    station: int | str,
    date_ranges: Sequence[Tuple[Optional[date], Optional[date]]],
    output_root: Path,
    dry_run: bool,
    force_rebuild: bool,
) -> bool:
    backup_config = _load_backup_restore_config()
    if not backup_config or not bool(backup_config.get("enabled", False)):
        return False

    backup_root = _local_log_backup_root(backup_config)
    if backup_root is None:
        return False

    station_id = _coerce_station_id(station)
    if station_id is None:
        print(f"Local LOG_BACKUP restore skipped: invalid station identifier {station!r}.")
        return False

    requested_days = _enumerate_bounded_days(date_ranges)
    if not requested_days:
        print("Local LOG_BACKUP restore skipped: selected date ranges are not fully bounded by day.")
        return False
    if not force_rebuild and _backup_outputs_already_exist(
        output_root, requested_days, LOCAL_LOG_BACKUP_REQUIRED_COLUMNS,
    ):
        print("Local LOG_BACKUP restore skipped: requested daily outputs already exist.")
        return True

    host_dir = _local_log_backup_host_dir(backup_root, station_id)
    if not host_dir.exists():
        print(f"Local LOG_BACKUP restore skipped: host directory not found: {host_dir}")
        return False

    day_count = 0
    for day_value in requested_days:
        frames: List[pd.DataFrame] = []
        for spec in LOG_SPECS:
            value_layout = LOCAL_LOG_BACKUP_LAYOUTS[spec.name]
            candidate_paths = tuple(
                candidate
                for directory in (host_dir / "done", host_dir)
                for prefix in spec.prefixes
                for candidate in sorted(
                    directory.glob(f"{prefix}*{day_value:%Y-%m-%d}.log")
                )
            )
            source_path = next((path for path in candidate_paths if path.exists()), None)
            if source_path is None:
                continue
            frame = _load_local_backup_log(source_path, value_layout)
            if not frame.empty:
                frames.append(frame)

        if not frames:
            continue

        merged = frames[0]
        for frame in frames[1:]:
            merged = merged.merge(frame, on="Time", how="outer")
        daily = (
            merged.set_index("Time")
            .sort_index()
            .resample("1min")
            .mean()
            .reset_index()
        )
        output_parent = output_root / f"{day_value:%Y}" / f"{day_value:%m}"
        output_path = output_parent / f"lab_logs_{day_value:%Y_%m_%d}.csv"
        if dry_run:
            print(f"  [dry-run] would restore {output_path} from local LOG_BACKUP")
            day_count += 1
            continue

        output_parent.mkdir(parents=True, exist_ok=True)
        daily.to_csv(output_path, index=False, float_format="%.5g")
        day_count += 1

    if day_count:
        print(f"Restored {day_count} LAB_LOGS daily file(s) from local LOG_BACKUP at {backup_root}.")
        return True

    print("Local LOG_BACKUP restore found no usable historical sensor files.")
    return False


def _copy_lines_from_pg_restore(
    ssh_host: str,
    dump_path: str,
    schema: str,
    table: str,
) -> List[str]:
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        ssh_host,
        "pg_restore",
        "-a",
        "-n",
        schema,
        "-t",
        table,
        "-f",
        "-",
        dump_path,
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(
            f"pg_restore failed for {schema}.{table} via {ssh_host}: {stderr or 'unknown error'}"
        )

    copy_lines: List[str] = []
    in_copy = False
    for line in result.stdout.splitlines():
        if line.startswith("COPY "):
            in_copy = True
            continue
        if not in_copy:
            continue
        if line == "\\.":
            break
        if line:
            copy_lines.append(line)
    return copy_lines


def _load_backup_series(
    ssh_host: str,
    dump_path: str,
    schema: str,
    table: str,
    output_column: str,
) -> pd.DataFrame:
    copy_lines = _copy_lines_from_pg_restore(ssh_host, dump_path, schema, table)
    if not copy_lines:
        return pd.DataFrame(columns=["Time", output_column])

    df = pd.read_csv(
        io.StringIO("\n".join(copy_lines)),
        sep="\t",
        header=None,
        names=["Time", output_column],
    )
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df[output_column] = pd.to_numeric(df[output_column], errors="coerce")
    df = df.dropna(subset=["Time"]).drop_duplicates(subset=["Time"], keep="last")
    return df.sort_values("Time")


def _enumerate_bounded_days(
    ranges: Sequence[Tuple[Optional[date], Optional[date]]],
) -> Optional[List[date]]:
    if not ranges:
        return None

    days: List[date] = []
    for start_day, end_day in ranges:
        if start_day is None or end_day is None:
            return None
        current = start_day
        while current <= end_day:
            days.append(current)
            current += timedelta(days=1)
    return sorted(set(days))


def _backup_outputs_already_exist(
    output_root: Path,
    requested_days: Sequence[date],
    required_columns: Iterable[str] = (),
) -> bool:
    """Check daily products and, when requested, their required schema."""
    required = set(required_columns)
    if not requested_days:
        return False
    for day_value in requested_days:
        output_path = (
            output_root / f"{day_value:%Y}" / f"{day_value:%m}"
            / f"lab_logs_{day_value:%Y_%m_%d}.csv"
        )
        if not output_path.exists():
            return False
        try:
            columns = set(pd.read_csv(output_path, nrows=0).columns)
        except Exception:
            return False
        if required and not required.issubset(columns):
            return False
    return True


def restore_outputs_from_backup(
    *,
    station: int | str,
    date_ranges: Sequence[Tuple[Optional[date], Optional[date]]],
    output_root: Path,
    dry_run: bool,
    force_rebuild: bool,
) -> bool:
    backup_config = _load_backup_restore_config()
    if not backup_config:
        return False
    if not bool(backup_config.get("enabled", False)):
        return False

    station_id = _coerce_station_id(station)
    if station_id is None:
        print(f"Backup restore skipped: invalid station identifier {station!r}.")
        return False

    ssh_host = str(backup_config.get("ssh_host", "")).strip()
    dump_path = _station_dump_path(backup_config, station_id)
    if not ssh_host or not dump_path:
        print(f"Backup restore skipped: missing ssh_host or dump path for station {station_id}.")
        return False

    requested_days = _enumerate_bounded_days(date_ranges)
    if requested_days and not force_rebuild and _backup_outputs_already_exist(output_root, requested_days):
        print("LAB_LOGS backup restore skipped: requested daily outputs already exist.")
        return True

    frames: List[pd.DataFrame] = []
    for spec in BACKUP_SERIES_SPECS:
        schema = _backup_schema_name(spec, station_id)
        try:
            series_df = _load_backup_series(
                ssh_host=ssh_host,
                dump_path=dump_path,
                schema=schema,
                table=spec.table,
                output_column=spec.output_column,
            )
        except Exception as exc:
            print(f"Warning: backup restore could not load {schema}.{spec.table}: {exc}")
            continue
        if not series_df.empty:
            frames.append(series_df)

    if not frames:
        print("LAB_LOGS backup restore found no usable series.")
        return False

    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="Time", how="outer")

    merged["Time"] = pd.to_datetime(merged["Time"], errors="coerce")
    merged = merged.dropna(subset=["Time"]).sort_values("Time")
    merged = merged.drop_duplicates(subset=["Time"], keep="last")

    if date_ranges:
        mask = [datetime_in_ranges(ts.to_pydatetime(), date_ranges) for ts in merged["Time"]]
        merged = merged.loc[mask]
    if merged.empty:
        print("LAB_LOGS backup restore found no rows inside the selected date ranges.")
        return False

    for column in merged.columns:
        if column == "Time":
            continue
        merged[column] = pd.to_numeric(merged[column], errors="coerce")

    day_count = 0
    for day_key, day_frame in merged.groupby(merged["Time"].dt.date):
        daily = (
            day_frame.set_index("Time")
            .sort_index()
            .resample("1min")
            .mean()
            .reset_index()
        )
        output_parent = output_root / f"{day_key:%Y}" / f"{day_key:%m}"
        output_path = output_parent / f"lab_logs_{day_key:%Y_%m_%d}.csv"
        if dry_run:
            print(f"  [dry-run] would restore {output_path} from database backup")
            day_count += 1
            continue

        output_parent.mkdir(parents=True, exist_ok=True)
        daily.to_csv(output_path, index=False, float_format="%.5g")
        day_count += 1

    print(
        f"Restored {day_count} LAB_LOGS daily file(s) from backup {dump_path} via {ssh_host}."
    )
    return day_count > 0


def main() -> int:
    args = parse_args()

    station = args.station
    selection = load_selection_for_paths(
        [LAB_LOGS_CONFIG_SHARED, LAB_LOGS_CONFIG_STEP2],
        master_config_root=MASTER_CONFIG_ROOT,
    )
    if not station_is_selected(station, selection.stations):
        print(f"Station {station} skipped by selection.stations.")
        return 0

    set_station(station)
    start_timer(__file__)

    station_dir = get_repo_root() / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / f"MINGO0{station}"
    lab_logs_root = station_dir / "STAGE_1" / "LOG_DATA"

    step1_root = lab_logs_root / "STEP_1"
    step1_output_dir = step1_root / "OUTPUT_FILES"

    step2_root = lab_logs_root / "STEP_2"
    input_root = step2_root / "INPUT_FILES"
    unprocessed_root = input_root / "UNPROCESSED"
    completed_root = input_root / "COMPLETED"
    output_root = station_dir / "STAGE_1_PRODUCTS" / "LOG_DATA" / "OUTPUT_FILES"

    # status_csv_path = step2_root / "log_aggregate_and_join_status.csv"
    # status_timestamp = append_status_row(status_csv_path)

    outlier_limits = load_outlier_limits()
    date_ranges = list(effective_date_ranges_for_station(station, selection))
    if date_ranges:
        human_ranges = [
            format_date_range_for_display(start_value, end_value)
            for start_value, end_value in date_ranges
        ]
        print(
            "Date range filtering enabled for LAB_LOGS STEP_2: "
            + "; ".join(human_ranges)
        )

    if not args.dry_run:
        unprocessed_root.mkdir(parents=True, exist_ok=True)
        completed_root.mkdir(parents=True, exist_ok=True)
        output_root.mkdir(parents=True, exist_ok=True)

    planned_moves = move_step1_outputs_to_unprocessed(
        step1_output_dir,
        unprocessed_root,
        args.dry_run,
    )

    candidate_files = sorted(
        path for path in unprocessed_root.glob("**/*") if path.is_file()
    )
    if args.dry_run:
        candidate_files = sorted(set(candidate_files).union(planned_moves))

    if args.all and completed_root.exists():
        candidate_files.extend(
            sorted(path for path in completed_root.glob("**/*") if path.is_file())
        )

    if date_ranges:
        filtered_candidates: List[Path] = []
        for file_path in candidate_files:
            day_value = extract_date_from_filename(file_path)
            if day_value is None:
                continue
            if day_overlaps_date_ranges(day_value, date_ranges):
                filtered_candidates.append(file_path)
        candidate_files = filtered_candidates

    if not candidate_files:
        print("No cleaned lab log files found to process. Trying local LOG_BACKUP restore.")
        restored = restore_outputs_from_local_log_backup(
            station=station,
            date_ranges=date_ranges,
            output_root=output_root,
            dry_run=args.dry_run,
            force_rebuild=args.all,
        )
        if not restored:
            print("Local LOG_BACKUP restore did not produce data. Trying configured database backup restore.")
            restored = restore_outputs_from_backup(
            station=station,
            date_ranges=date_ranges,
            output_root=output_root,
            dry_run=args.dry_run,
            force_rebuild=args.all,
            )
        if not restored:
            print("No LAB_LOGS backup data could be restored.")
        return 0

    day_data: Dict[date, Dict[str, pd.DataFrame]] = defaultdict(dict)
    processed_sources: List[Path] = []

    for file_path in candidate_files:
        spec = match_spec(file_path.name)
        if spec is None:
            print(f"Skipping {file_path.name}: unknown log prefix.")
            continue

        actual_path = resolve_actual_path(file_path, planned_moves)
        df = read_clean_log(actual_path, spec)
        if df.empty:
            continue

        file_had_data = False

        for day_key, day_frame in df.groupby(df.index.date):
            if day_frame.empty:
                continue
            if date_ranges:
                in_range_mask = [
                    datetime_in_ranges(ts.to_pydatetime(), date_ranges)
                    for ts in day_frame.index
                ]
                day_frame = day_frame.loc[in_range_mask]
                if day_frame.empty:
                    continue
            resampled = day_frame.resample("1min").mean()
            if resampled.empty:
                continue

            existing = day_data[day_key].get(spec.name)
            if existing is not None:
                combined = (
                    pd.concat([existing, resampled])
                    .groupby(level=0)
                    .last()
                    .sort_index()
                )
                day_data[day_key][spec.name] = combined
            else:
                day_data[day_key][spec.name] = resampled.sort_index()

            file_had_data = True

        if file_had_data and file_path.is_relative_to(unprocessed_root):
            processed_sources.append(file_path)

    if not day_data:
        print("No log data found to merge.")
        # rebuild_big_csv(output_root, lab_logs_root / "big_log_lab_data.csv", args.dry_run)
        # mark_status_complete(status_csv_path, status_timestamp)
        return 0

    for day_key in sorted(day_data.keys()):
        frames = [frame for frame in day_data[day_key].values()]
        merged = pd.concat(frames, axis=1).sort_index()

        apply_outlier_filters(merged, outlier_limits)

        output_parent = output_root / f"{day_key:%Y}" / f"{day_key:%m}"
        output_path = output_parent / f"lab_logs_{day_key:%Y_%m_%d}.csv"

        if output_path.exists():
            try:
                existing = pd.read_csv(output_path, parse_dates=["Time"]).set_index(
                    "Time"
                )
            except Exception as exc:  # pragma: no cover - best effort logging
                print(f"Warning: unable to load existing {output_path}: {exc}")
                existing = pd.DataFrame()
            merged = (
                pd.concat([existing, merged])
                .groupby(level=0)
                .last()
                .sort_index()
            )

        if args.dry_run:
            print(f"  [dry-run] would write {output_path}")
        elif CREATE_NEW_CSV:
            output_parent.mkdir(parents=True, exist_ok=True)
            merged.reset_index().to_csv(output_path, index=False, float_format="%.5g")
            print(f"  Wrote {output_path}")

    archive_processed_files(
        processed_sources,
        unprocessed_root,
        completed_root,
        args.dry_run,
    )

    # rebuild_big_csv(output_root, lab_logs_root / "big_log_lab_data.csv", args.dry_run)

    # mark_status_complete(status_csv_path, status_timestamp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
