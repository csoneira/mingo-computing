#!/usr/bin/env python3

"""Join distributed event files into daily analysis products."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple

import numpy as np
import pandas as pd
import yaml


CURRENT_PATH = Path(__file__).resolve()
_SCRIPTS_ROOT = next(parent for parent in CURRENT_PATH.parents if parent.name == "MINGO_ANALYSIS_SCRIPTS")
_REPO_IMPORT_ROOT = _SCRIPTS_ROOT.parents[2]
if str(_REPO_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_IMPORT_ROOT))
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root
MASTER_ROOT = _SCRIPTS_ROOT
REPO_ROOT = get_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.event_output_schema import (
    canonicalize_output_dataframe,
    resolve_output_schema,
)


COMMENT_PREFIX = "#"
LEGACY_VALUE_COLUMNS = {"1234_all", "events"}
Q_EVENT_SUM_COLUMN = "Q_event_sum"
Q_EVENT_COUNT_COLUMN = "Q_event_count"
Q_EVENT_MEAN_COLUMN = "Q_event_mean"
INTERNAL_BIN_LIVE_SECONDS_COLUMN = "__bin_live_seconds"
INTERNAL_COUNT_COLUMN_PREFIX = "__count__"
INTERNAL_SOURCE_START_COLUMN = "__source_start_time"
INTERNAL_TRANSPORT_INFERRED_COLUMN = "__transport_inferred"
STEP2_CONFIG_PATH = (
    MASTER_ROOT / "SUPPORT" / "CONFIG_FILES" / "STAGE_2" / "EVENT_DATA" / "STEP_1_ACCUMULATION" / "config_step_1_accumulation.yaml"
)
STEP3_CONFIG_PATH = (
    MASTER_ROOT / "SUPPORT" / "CONFIG_FILES" / "STAGE_2" / "EVENT_DATA" / "STEP_2_DAILY_EVENT_DATA" / "config_step_2_daily_event_data.yaml"
)


def load_yaml_config(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def load_output_schema() -> Dict[str, object]:
    step3_config = load_yaml_config(STEP3_CONFIG_PATH)
    if bool(step3_config.get("inherit_step_2_output_schema", True)):
        merged_config = load_yaml_config(STEP2_CONFIG_PATH)
    else:
        merged_config = {}
    merged_config.update(step3_config)
    return resolve_output_schema(merged_config)


def split_metadata_values(raw_value: str | None) -> List[str]:
    if not raw_value:
        return []
    normalized = raw_value.replace(";", ",")
    return [value.strip() for value in normalized.split(",") if value.strip()]


def internal_count_column(output_column: str) -> str:
    return f"{INTERNAL_COUNT_COLUMN_PREFIX}{str(output_column).strip()}"


def extract_datetime_from_basename(name: str) -> pd.Timestamp | pd.NaT:
    stem = Path(str(name)).stem
    for prefix in (
        "cleaned_",
        "calibrated_",
        "fitted_",
        "postprocessed_",
        "corrected_",
        "accumulated_",
        "listed_",
    ):
        if stem.startswith(prefix):
            stem = stem[len(prefix) :]
            break

    try:
        parts = stem.split("_")
        if len(parts) >= 4:
            parsed = pd.to_datetime(parts[-2] + "_" + parts[-1], format="%Y.%m.%d_%H.%M.%S", errors="coerce")
            if pd.notna(parsed):
                return parsed
    except Exception:
        pass

    if len(stem) >= 15 and stem[:4].lower().startswith("mi0") and stem[-11:].isdigit():
        digits = stem[-11:]
        try:
            year = 2000 + int(digits[0:2])
            day_of_year = int(digits[2:5])
            hour = int(digits[5:7])
            minute = int(digits[7:9])
            second = int(digits[9:11])
            parsed = datetime(year, 1, 1) + pd.Timedelta(days=day_of_year - 1)
            return pd.Timestamp(parsed).replace(hour=hour, minute=minute, second=second)
        except ValueError:
            return pd.NaT

    return pd.NaT


def estimate_transport_columns(
    dataframe: pd.DataFrame,
    *,
    basenames: Sequence[str],
    value_columns: Sequence[str],
) -> pd.DataFrame:
    if dataframe.empty:
        dataframe[INTERNAL_SOURCE_START_COLUMN] = pd.NaT
        dataframe[INTERNAL_TRANSPORT_INFERRED_COLUMN] = False
        return dataframe

    dataframe = dataframe.copy()
    parsed_starts = [
        parsed
        for parsed in (extract_datetime_from_basename(name) for name in basenames)
        if pd.notna(parsed)
    ]
    source_start = min(parsed_starts) if parsed_starts else pd.NaT
    dataframe[INTERNAL_SOURCE_START_COLUMN] = [source_start] * len(dataframe)

    inferred_transport = False
    for output_column in value_columns:
        count_column = internal_count_column(output_column)
        if count_column in dataframe.columns:
            dataframe[count_column] = pd.to_numeric(dataframe[count_column], errors="coerce").fillna(0.0)
            continue
        if output_column in dataframe.columns:
            dataframe[count_column] = (
                pd.to_numeric(dataframe[output_column], errors="coerce").fillna(0.0) * 60.0
            )
        else:
            dataframe[count_column] = 0.0
        inferred_transport = True

    if INTERNAL_BIN_LIVE_SECONDS_COLUMN in dataframe.columns:
        dataframe[INTERNAL_BIN_LIVE_SECONDS_COLUMN] = (
            pd.to_numeric(dataframe[INTERNAL_BIN_LIVE_SECONDS_COLUMN], errors="coerce")
            .fillna(60.0)
            .clip(lower=1.0)
        )
    else:
        dataframe[INTERNAL_BIN_LIVE_SECONDS_COLUMN] = 60.0
        inferred_transport = True

        if pd.notna(source_start):
            first_index = dataframe["Time"].idxmin()
            first_minute = pd.Timestamp(dataframe.loc[first_index, "Time"])
            if source_start.floor("min") == first_minute:
                start_offset = (source_start - first_minute).total_seconds()
                if 0.0 <= start_offset < 60.0:
                    dataframe.loc[first_index, INTERNAL_BIN_LIVE_SECONDS_COLUMN] = max(
                        1.0,
                        60.0 - start_offset,
                    )

    dataframe[INTERNAL_TRANSPORT_INFERRED_COLUMN] = inferred_transport
    return dataframe


def adjust_group_transport_estimates(group: pd.DataFrame) -> pd.DataFrame:
    if (
        len(group) <= 1
        or INTERNAL_TRANSPORT_INFERRED_COLUMN not in group.columns
        or INTERNAL_SOURCE_START_COLUMN not in group.columns
        or INTERNAL_BIN_LIVE_SECONDS_COLUMN not in group.columns
    ):
        return group

    adjusted = group.copy()
    minute_start = pd.Timestamp(adjusted["Time"].iloc[0])
    start_entries: List[Tuple[int, float]] = []

    for idx, row in adjusted.iterrows():
        source_start = row.get(INTERNAL_SOURCE_START_COLUMN)
        if pd.isna(source_start):
            continue
        source_start_ts = pd.Timestamp(source_start)
        if source_start_ts.floor("min") != minute_start:
            continue
        offset = (source_start_ts - minute_start).total_seconds()
        if 0.0 <= offset < 60.0:
            start_entries.append((idx, float(offset)))

    if not start_entries:
        return adjusted

    start_entries.sort(key=lambda item: item[1])
    start_indices = {idx for idx, _ in start_entries}
    predecessor_candidates = [idx for idx in adjusted.index if idx not in start_indices]

    if predecessor_candidates:
        predecessor_idx = min(
            predecessor_candidates,
            key=lambda idx: pd.Timestamp(adjusted.at[idx, INTERNAL_SOURCE_START_COLUMN])
            if pd.notna(adjusted.at[idx, INTERNAL_SOURCE_START_COLUMN])
            else pd.Timestamp.min,
        )
        if bool(adjusted.at[predecessor_idx, INTERNAL_TRANSPORT_INFERRED_COLUMN]):
            adjusted.at[predecessor_idx, INTERNAL_BIN_LIVE_SECONDS_COLUMN] = max(
                1.0,
                start_entries[0][1],
            )

    for position, (idx, offset) in enumerate(start_entries):
        next_offset = 60.0
        if position + 1 < len(start_entries):
            next_offset = start_entries[position + 1][1]
        if bool(adjusted.at[idx, INTERNAL_TRANSPORT_INFERRED_COLUMN]):
            adjusted.at[idx, INTERNAL_BIN_LIVE_SECONDS_COLUMN] = max(
                1.0,
                next_offset - offset,
            )

    return adjusted


def extract_basenames_from_metadata(metadata: Dict[str, str], fallback: str) -> Set[str]:
    raw_value = metadata.get("source_basenames")
    if not raw_value:
        return {fallback}
    parsed = set(split_metadata_values(raw_value))
    return parsed or {fallback}


def collect_day_basenames(csv_files: Sequence[Path]) -> Set[str]:
    basenames: Set[str] = set()
    for csv_file in csv_files:
        metadata = parse_metadata(csv_file)
        basenames.update(extract_basenames_from_metadata(metadata, csv_file.stem))
    return basenames


def existing_output_basenames(output_path: Path) -> Set[str]:
    if not output_path.exists():
        return set()
    metadata = parse_metadata(output_path)
    return extract_basenames_from_metadata(metadata, output_path.stem)


def output_schema_matches(
    output_path: Path,
    *,
    time_column: str,
    value_columns: Sequence[str],
    extra_columns: Sequence[str],
) -> bool:
    if not output_path.exists():
        return False
    try:
        header = pd.read_csv(output_path, comment=COMMENT_PREFIX, nrows=0).columns.tolist()
    except Exception:
        return False
    return header == [time_column, *value_columns, *extra_columns]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Merge STEP_3/TASK_1_TO_2 daily accumulated CSV files into consolidated "
            "event_data_YYYY_MM_DD.csv outputs for TASK_2."
        )
    )
    parser.add_argument("station", help="Station identifier (e.g. 1, 2, 3, 4)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show actions without writing joined CSV files.",
    )
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Rebuild outputs for all days even if the existing file is up to date.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-day skip reasons (default: only a summary).",
    )
    return parser.parse_args()


def parse_metadata(path: Path) -> Dict[str, str]:
    metadata: Dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        while True:
            position = handle.tell()
            line = handle.readline()
            if not line:
                break
            if line.startswith(COMMENT_PREFIX):
                content = line[len(COMMENT_PREFIX) :].strip()
                if "=" in content:
                    key, value = content.split("=", 1)
                    metadata[key.strip()] = value.strip()
            else:
                # rewind to the start of the first non-comment line
                handle.seek(position)
                break
    return metadata


def read_with_metadata(path: Path, value_columns: Sequence[str]) -> pd.DataFrame:
    metadata = parse_metadata(path)
    dataframe = pd.read_csv(path, comment=COMMENT_PREFIX)
    if dataframe.empty:
        return dataframe

    if "Time" not in dataframe.columns:
        raise ValueError(f"Column 'Time' not present in {path}.")

    dataframe["Time"] = pd.to_datetime(dataframe["Time"], errors="coerce")
    dataframe = dataframe.dropna(subset=["Time"]).reset_index(drop=True)

    raw_basenames = metadata.get("source_basenames")
    if raw_basenames:
        basenames = tuple(split_metadata_values(raw_basenames))
    else:
        basenames = (path.stem,)

    exec_str = metadata.get("execution_date")
    execution_dt = pd.NaT
    if exec_str:
        exec_values = split_metadata_values(exec_str)
        parsed_exec_dates: List[pd.Timestamp] = []
        for value in exec_values:
            parsed = pd.to_datetime(value, errors="coerce")
            if isinstance(parsed, pd.Timestamp) and pd.notna(parsed):
                if parsed.tzinfo is not None:
                    parsed = parsed.tz_convert("UTC").tz_localize(None)
                parsed_exec_dates.append(parsed)
        if parsed_exec_dates:
            execution_dt = max(parsed_exec_dates)

    dataframe["source_basenames"] = [basenames] * len(dataframe)
    dataframe["execution_date"] = [execution_dt] * len(dataframe)
    dataframe = estimate_transport_columns(
        dataframe,
        basenames=basenames,
        value_columns=value_columns,
    )

    numeric_columns = [
        column
        for column in dataframe.columns
        if column
        not in {
            "Time",
            "source_basenames",
            "execution_date",
            INTERNAL_SOURCE_START_COLUMN,
            INTERNAL_TRANSPORT_INFERRED_COLUMN,
        }
    ]
    dataframe[numeric_columns] = dataframe[numeric_columns].apply(
        pd.to_numeric, errors="coerce"
    )

    return dataframe


def iter_day_directories(root: Path) -> List[Tuple[date, Path]]:
    day_directories: List[Tuple[date, Path]] = []
    for potential in sorted(root.rglob("*")):
        if not potential.is_dir():
            continue

        csv_files = list(potential.glob("*.csv"))
        if not csv_files:
            continue

        try:
            relative = potential.relative_to(root)
        except ValueError:
            continue

        parts = relative.parts
        if len(parts) < 3:
            continue

        candidate = parts[-3:]
        try:
            day = datetime.strptime("-".join(candidate), "%Y-%m-%d").date()
        except ValueError:
            continue

        day_directories.append((day, potential))

    day_directories.sort(key=lambda item: item[0])
    return day_directories


def resolve_time_group(group: pd.DataFrame, value_columns: Sequence[str]) -> List[pd.Series]:
    if len(group) == 1:
        return [group.iloc[0].copy()]

    basename_sets: List[Set[str]] = [set(entry) for entry in group["source_basenames"]]
    adjacency = {index: set() for index in range(len(group))}

    for idx in range(len(group)):
        for jdx in range(idx + 1, len(group)):
            if basename_sets[idx].intersection(basename_sets[jdx]):
                adjacency[idx].add(jdx)
                adjacency[jdx].add(idx)

    components: List[List[int]] = []
    visited: Set[int] = set()

    for idx in range(len(group)):
        if idx in visited:
            continue
        stack = [idx]
        component: List[int] = []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            stack.extend(adjacency[current] - visited)
        components.append(component)

    if all(len(component) == 1 for component in components) and len(components) > 1:
        group = adjust_group_transport_estimates(group)
        numeric = (
            group.loc[:, value_columns]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0)
            .sum()
        )
        aggregate = group.iloc[0].copy()
        for column, value in numeric.items():
            aggregate[column] = value
        aggregate["source_basenames"] = tuple(
            sorted({name for names in basename_sets for name in names})
        )
        exec_dates = group["execution_date"]
        if exec_dates.notna().any():
            aggregate["execution_date"] = exec_dates.max()
        return [aggregate]

    resolved_rows: List[pd.Series] = []
    for component in components:
        if len(component) == 1:
            resolved_rows.append(group.iloc[component[0]].copy())
            continue

        component_frame = group.iloc[component].copy()
        component_frame = component_frame.sort_values(
            "execution_date", ascending=False, na_position="last"
        )
        resolved_rows.append(component_frame.iloc[0].copy())

    return resolved_rows


def merge_day_files(csv_files: Sequence[Path]) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    output_schema = load_output_schema()
    output_value_columns = list(output_schema["value_columns"])
    for csv_file in sorted(csv_files):
        dataframe = read_with_metadata(csv_file, output_value_columns)
        if dataframe.empty:
            continue
        frames.append(dataframe)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.dropna(subset=["Time"]).sort_values("Time").reset_index(
        drop=True
    )

    value_columns = [
        column
        for column in combined.columns
        if column
        not in {
            "Time",
            "source_basenames",
            "execution_date",
            INTERNAL_SOURCE_START_COLUMN,
            INTERNAL_TRANSPORT_INFERRED_COLUMN,
        }
    ]
    combined[value_columns] = combined[value_columns].apply(
        pd.to_numeric, errors="coerce"
    )

    merged_rows: List[pd.Series] = []
    for _, group in combined.groupby("Time", sort=True):
        merged_rows.extend(resolve_time_group(group, value_columns))

    if not merged_rows:
        return pd.DataFrame(columns=["Time", *value_columns])

    merged = pd.DataFrame(merged_rows)

    for column in value_columns:
        if column not in merged.columns:
            merged[column] = 0

    merged = merged[
        [
            "Time",
            *value_columns,
            "source_basenames",
            "execution_date",
            INTERNAL_SOURCE_START_COLUMN,
            INTERNAL_TRANSPORT_INFERRED_COLUMN,
        ]
    ].sort_values("Time")

    merged.reset_index(drop=True, inplace=True)
    return merged


def format_header_values(values: Iterable[str]) -> str:
    return ",".join(sorted(dict.fromkeys(values)))


def main() -> int:
    args = parse_args()
    station = args.station
    output_schema = load_output_schema()
    output_time_column = str(output_schema["time_column"])
    output_value_columns = list(output_schema["value_columns"])
    output_extra_columns = list(output_schema["extra_columns"])

    station_dir = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / f"MINGO0{station}"
    stage2_event_data = station_dir / "STAGE_2" / "EVENT_DATA" / "STEP_2_DAILY_EVENT_DATA"
    task1_to_2_root = stage2_event_data / "TASK_1_TO_2"
    task2_output_root = stage2_event_data / "TASK_2" / "OUTPUT_FILES"

    if not task1_to_2_root.exists():
        print(f"No input directory found: {task1_to_2_root}")
        return 0

    day_directories = iter_day_directories(task1_to_2_root)
    if not day_directories:
        print("No daily directories with CSV files found to merge.")
        return 0

    if not args.dry_run:
        task2_output_root.mkdir(parents=True, exist_ok=True)

    total_days = 0
    processed_days = 0
    skipped_up_to_date = 0
    skipped_empty_merge = 0
    skipped_legacy_inputs = 0

    for day, day_dir in day_directories:
        csv_files = sorted(day_dir.glob("*.csv"))
        if not csv_files:
            continue
        total_days += 1

        year = f"{day:%Y}"
        month = f"{day:%m}"

        output_filename = f"event_data_{day:%Y_%m_%d}.csv"
        output_parent = task2_output_root / year / month
        output_path = output_parent / output_filename
        day_basenames = collect_day_basenames(csv_files)
        existing_basenames = existing_output_basenames(output_path)
        schema_is_current = output_schema_matches(
            output_path,
            time_column=output_time_column,
            value_columns=output_value_columns,
            extra_columns=output_extra_columns,
        )

        needs_merge = (
            args.all
            or not output_path.exists()
            or day_basenames != existing_basenames
            or not schema_is_current
        )

        if not needs_merge:
            skipped_up_to_date += 1
            if args.verbose:
                print(f"Skipping {day:%Y-%m-%d}: output already up to date ({output_path}).")
            continue

        print(
            f"Processing {day_dir} ({day:%Y-%m-%d}) with {len(csv_files)} file(s)..."
        )

        merged = merge_day_files(csv_files)

        if merged.empty:
            skipped_empty_merge += 1
            if args.verbose:
                print("  ! Skipped: nothing to merge.")
            continue

        basenames: List[str] = []
        exec_dates: List[str] = []

        for entry in merged["source_basenames"]:
            basenames.extend(entry)

        for exec_dt in merged["execution_date"]:
            if pd.isna(exec_dt):
                continue
            if isinstance(exec_dt, pd.Timestamp):
                exec_dates.append(exec_dt.strftime("%Y-%m-%d %H:%M:%S"))
            else:
                exec_dates.append(str(exec_dt))

        raw_output_dataframe = merged.drop(
            columns=[
                "source_basenames",
                "execution_date",
                INTERNAL_SOURCE_START_COLUMN,
                INTERNAL_TRANSPORT_INFERRED_COLUMN,
            ],
            errors="ignore",
        )
        raw_value_columns = [
            column for column in raw_output_dataframe.columns if column != output_time_column
        ]
        if INTERNAL_BIN_LIVE_SECONDS_COLUMN in raw_output_dataframe.columns:
            live_seconds = pd.to_numeric(
                raw_output_dataframe[INTERNAL_BIN_LIVE_SECONDS_COLUMN],
                errors="coerce",
            )
            valid_live_seconds = live_seconds.where(live_seconds > 0)
            for output_column in output_value_columns:
                count_column = internal_count_column(output_column)
                if count_column not in raw_output_dataframe.columns:
                    continue
                raw_counts = pd.to_numeric(
                    raw_output_dataframe[count_column],
                    errors="coerce",
                ).fillna(0.0)
                raw_output_dataframe[output_column] = np.where(
                    valid_live_seconds.notna(),
                    raw_counts / valid_live_seconds,
                    np.nan,
                )
        legacy_columns_present = [
            column for column in raw_value_columns if column in LEGACY_VALUE_COLUMNS
        ]
        if legacy_columns_present:
            skipped_legacy_inputs += 1
            print(
                "  ! Skipped: legacy STEP_2 columns detected in the day inputs "
                f"({', '.join(sorted(legacy_columns_present))}). Re-run STEP_2 and TASK_1 "
                "distribution for this day before rebuilding TASK_2."
            )
            continue

        output_dataframe = canonicalize_output_dataframe(
            raw_output_dataframe,
            time_column=output_time_column,
            value_columns=output_value_columns,
        )
        output_dataframe = output_dataframe.copy()

        for extra_column in output_extra_columns:
            if extra_column == Q_EVENT_MEAN_COLUMN:
                if (
                    Q_EVENT_SUM_COLUMN in raw_output_dataframe.columns
                    and Q_EVENT_COUNT_COLUMN in raw_output_dataframe.columns
                ):
                    q_sum = pd.to_numeric(
                        raw_output_dataframe[Q_EVENT_SUM_COLUMN], errors="coerce"
                    )
                    q_count = pd.to_numeric(
                        raw_output_dataframe[Q_EVENT_COUNT_COLUMN], errors="coerce"
                    )
                    output_dataframe[extra_column] = np.where(
                        q_count > 0,
                        q_sum / q_count,
                        np.nan,
                    )
                elif extra_column in raw_output_dataframe.columns:
                    output_dataframe[extra_column] = pd.to_numeric(
                        raw_output_dataframe[extra_column],
                        errors="coerce",
                    )
                else:
                    output_dataframe[extra_column] = np.nan
                continue

            if extra_column in raw_output_dataframe.columns:
                output_dataframe[extra_column] = pd.to_numeric(
                    raw_output_dataframe[extra_column],
                    errors="coerce",
                )
            else:
                output_dataframe[extra_column] = np.nan

        output_dataframe = output_dataframe[
            [output_time_column, *output_value_columns, *output_extra_columns]
        ]
        output_dataframe[output_time_column] = output_dataframe[output_time_column].dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        basename_header = format_header_values(basenames)
        exec_date_header = format_header_values(exec_dates)

        if args.dry_run:
            print(f"  [dry-run] would write {output_path}")
            print(f"           # source_basenames={basename_header}")
            print(f"           # execution_date={exec_date_header}")
            continue

        output_parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(f"# source_basenames={basename_header}\n")
            handle.write(f"# execution_date={exec_date_header}\n")
            output_dataframe.to_csv(handle, index=False)

        print(f"  Wrote {output_path}")
        processed_days += 1

    print(
        "Join summary: "
        f"days_seen={total_days}, processed={processed_days}, "
        f"skipped_up_to_date={skipped_up_to_date}, skipped_empty_merge={skipped_empty_merge}, "
        f"skipped_legacy_inputs={skipped_legacy_inputs}"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
