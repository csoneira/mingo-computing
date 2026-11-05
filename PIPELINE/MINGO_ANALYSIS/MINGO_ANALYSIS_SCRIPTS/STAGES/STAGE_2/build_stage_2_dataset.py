#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_2/build_stage_2_dataset.py
Purpose: Join Stage 1 event, lab-log, and Copernicus outputs into a final Stage 2 dataset.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_2/build_stage_2_dataset.py [options]
Inputs: Stage 1 daily CSV outputs and Stage 2 config.
Outputs: Daily Stage 2 CSV files plus one station-level combined CSV.
Notes: Event data drives the output cadence and schema.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import yaml


CURRENT_PATH = Path(__file__).resolve()
MASTER_ROOT = None
REPO_ROOT = None
for parent in CURRENT_PATH.parents:
    if parent.name == "MINGO_ANALYSIS_SCRIPTS":
        MASTER_ROOT = parent
        REPO_ROOT = parent.parent.parent
        break
if MASTER_ROOT is None:
    MASTER_ROOT = CURRENT_PATH.parents[-1]
if REPO_ROOT is None:
    REPO_ROOT = CURRENT_PATH.parents[-1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.execution_logger import set_station, start_timer
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.path_config import get_master_config_root, get_repo_root
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.selection_config import (
    date_in_ranges,
    effective_date_ranges_for_station,
    load_selection_for_paths,
    parse_station_id,
    station_is_selected,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.STAGES.STAGE_2.plot_joined_stage_groups import generate_joined_groups_plot


CONFIG_PATH = get_master_config_root() / "STAGE_2" / "config_stage_2.yaml"
PLOT_CONFIG_PATH = get_master_config_root() / "STAGE_2" / "plot_joined_stage_2_groups.yaml"
DAY_STEM_RE = re.compile(r"_(\d{4})_(\d{2})_(\d{2})$")
LEGACY_EVENT_SCHEMA_COLUMNS = {"1234_all", "events"}
LEGACY_EVENT_RATE_PREFIXES = ("four_plane_R", "three_plane_R")
DEFAULT_SOURCE_COLUMN_ALIASES: Dict[str, Tuple[str, ...]] = {
    # Stage 1 lab outputs may still expose the raw merged sensor names.
    "temp_lab": (
        "temp_lab",
        "sensors_ext_Temperature_ext",
        "sensors_int_Temperature_int",
    ),
    "pressure_lab": (
        "pressure_lab",
        "sensors_ext_Pressure_ext",
        "sensors_int_Pressure_int",
    ),
}


class IncompatibleEventSchemaError(RuntimeError):
    """Raised when the Stage 1 event output cannot be mapped to the Stage 2 schema."""


def load_yaml_mapping(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    return loaded if isinstance(loaded, dict) else {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the Stage 2 station dataset from Stage 1 outputs."
    )
    parser.add_argument("station", help="Station identifier (e.g. 1, 2, 3, 4)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the work to be done without writing files.",
    )
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Rebuild all daily outputs even when they already exist.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print additional details, including matched source columns.",
    )
    parser.add_argument(
        "--plot-only",
        action="store_true",
        help="Skip Stage 2 dataset rebuilding and only regenerate the joined Stage 2 plot from existing outputs.",
    )
    return parser.parse_args()


def parse_day_from_stem(path: Path, prefix: str) -> Optional[date]:
    if path.suffix.lower() != ".csv":
        return None
    stem = path.stem
    if not stem.startswith(f"{prefix}_"):
        return None
    match = DAY_STEM_RE.search(stem)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def iter_daily_files(root: Path, prefix: str) -> List[Tuple[date, Path]]:
    discovered: List[Tuple[date, Path]] = []
    if not root.exists():
        return discovered
    pattern = f"{prefix}_*.csv"
    for path in sorted(root.rglob(pattern)):
        day_value = parse_day_from_stem(path, prefix)
        if day_value is None:
            continue
        discovered.append((day_value, path))
    discovered.sort(key=lambda item: item[0])
    return discovered


def build_daily_file_path(root: Path, prefix: str, day_value: date) -> Path:
    return root / f"{day_value:%Y}" / f"{day_value:%m}" / f"{prefix}_{day_value:%Y_%m_%d}.csv"


def read_daily_csv(
    path: Path,
    *,
    time_column: str,
    comment_prefix: str,
) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=[time_column])

    dataframe = pd.read_csv(path, comment=comment_prefix)
    if dataframe.empty:
        return pd.DataFrame(columns=[time_column, *[col for col in dataframe.columns if col != time_column]])
    if time_column not in dataframe.columns:
        raise ValueError(f"Column {time_column!r} not present in {path}.")

    dataframe = dataframe.copy()
    dataframe[time_column] = pd.to_datetime(dataframe[time_column], errors="coerce")
    dataframe = dataframe.dropna(subset=[time_column])
    dataframe = dataframe.sort_values(time_column).drop_duplicates(subset=[time_column], keep="last")
    dataframe.reset_index(drop=True, inplace=True)
    return dataframe


def normalize_alternative_column_sets(raw_value: object) -> List[List[str]]:
    alternatives: List[List[str]] = []
    if isinstance(raw_value, str):
        cleaned = raw_value.strip()
        return [[cleaned]] if cleaned else []
    if isinstance(raw_value, Sequence) and not isinstance(raw_value, (str, bytes)):
        for item in raw_value:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    alternatives.append([cleaned])
                continue
            if isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
                candidate_set = [str(column).strip() for column in item if str(column).strip()]
                if candidate_set:
                    alternatives.append(candidate_set)
    return alternatives


def resolve_sum_series(
    dataframe: pd.DataFrame,
    alternatives: Sequence[Sequence[str]],
) -> Tuple[Optional[pd.Series], List[str]]:
    for candidate_set in alternatives:
        columns = [str(column).strip() for column in candidate_set if str(column).strip()]
        if not columns:
            continue
        if not all(column in dataframe.columns for column in columns):
            continue
        numeric = dataframe.loc[:, columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        return numeric.sum(axis=1).astype(float), columns
    return None, []


def resolve_first_present_series(
    dataframe: pd.DataFrame,
    candidates: Sequence[str],
) -> Tuple[pd.Series, Optional[str]]:
    for candidate in candidates:
        column = str(candidate).strip()
        if not column or column not in dataframe.columns:
            continue
        return pd.to_numeric(dataframe[column], errors="coerce"), column
    return pd.Series(np.nan, index=dataframe.index, dtype=float), None


def describe_event_schema(columns: Sequence[str]) -> str:
    column_set = set(columns)
    if column_set.intersection(LEGACY_EVENT_SCHEMA_COLUMNS):
        return "legacy count schema (1234_all/events)"
    if any(
        str(column).startswith(prefix)
        for column in columns
        for prefix in LEGACY_EVENT_RATE_PREFIXES
    ):
        return "legacy angular schema with the older ring layout"
    return "missing one or more required 13-sector angular-rate columns"


def normalize_event_dataframe(
    dataframe: pd.DataFrame,
    *,
    event_config: Mapping[str, object],
    output_config: Mapping[str, object],
) -> Tuple[pd.DataFrame, Dict[str, Sequence[str] | str]]:
    input_time_column = str(event_config.get("time_column", "Time")).strip() or "Time"
    output_time_column = str(output_config.get("time_column", "time")).strip() or "time"
    count_column = str(output_config.get("count_column", "count")).strip() or "count"
    q_event_mean_candidates = [
        str(column).strip()
        for column in (event_config.get("q_event_mean_candidates") or [])
        if str(column).strip()
    ]
    sector_sources_raw = event_config.get("angular_sector_sources") or {}
    if not isinstance(sector_sources_raw, Mapping):
        raise ValueError("event_data.angular_sector_sources must be a mapping.")

    if input_time_column not in dataframe.columns:
        raise ValueError(f"Column {input_time_column!r} not present in event dataframe.")

    source_dataframe = dataframe.copy()
    source_dataframe[input_time_column] = pd.to_datetime(
        source_dataframe[input_time_column],
        errors="coerce",
    )
    source_dataframe = source_dataframe.dropna(subset=[input_time_column]).reset_index(drop=True)

    normalized = pd.DataFrame(index=source_dataframe.index)
    normalized[output_time_column] = source_dataframe[input_time_column]
    matched_columns: Dict[str, Sequence[str] | str] = {}
    missing_sectors: List[str] = []

    for sector_name, raw_alternatives in sector_sources_raw.items():
        alternatives = normalize_alternative_column_sets(raw_alternatives)
        series, matched = resolve_sum_series(source_dataframe, alternatives)
        if series is None:
            missing_sectors.append(str(sector_name))
            continue
        normalized[str(sector_name)] = series
        matched_columns[str(sector_name)] = tuple(matched)

    if missing_sectors:
        raise IncompatibleEventSchemaError(
            "Incompatible event schema: "
            f"{describe_event_schema(source_dataframe.columns)}. "
            f"Missing sectors: {', '.join(missing_sectors)}."
        )

    q_event_series, q_event_source = resolve_first_present_series(
        source_dataframe,
        q_event_mean_candidates,
    )
    normalized["Q_event_mean"] = q_event_series.astype(float)
    if q_event_source is not None:
        matched_columns["Q_event_mean"] = q_event_source

    sector_columns = list(sector_sources_raw.keys())
    normalized[count_column] = normalized.loc[:, sector_columns].sum(axis=1).astype(float)
    normalized = normalized[
        [output_time_column, count_column, "Q_event_mean", *sector_columns]
    ].sort_values(output_time_column)
    normalized.reset_index(drop=True, inplace=True)
    return normalized, matched_columns


def map_source_columns(
    dataframe: pd.DataFrame,
    *,
    mapping_config: Mapping[str, object],
) -> Tuple[pd.DataFrame, Dict[str, Optional[str]]]:
    mapped = pd.DataFrame(index=dataframe.index)
    matches: Dict[str, Optional[str]] = {}

    for output_column, raw_candidates in mapping_config.items():
        candidates: List[str] = []
        seen_candidates: set[str] = set()

        def append_candidate(candidate: object) -> None:
            candidate_name = str(candidate).strip()
            if not candidate_name or candidate_name in seen_candidates:
                return
            seen_candidates.add(candidate_name)
            candidates.append(candidate_name)

        if isinstance(raw_candidates, str):
            append_candidate(raw_candidates)
        elif isinstance(raw_candidates, Sequence) and not isinstance(raw_candidates, (str, bytes)):
            for candidate in raw_candidates:
                if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)):
                    for nested_candidate in candidate:
                        append_candidate(nested_candidate)
                else:
                    append_candidate(candidate)

        for alias in DEFAULT_SOURCE_COLUMN_ALIASES.get(str(output_column), ()):
            append_candidate(alias)

        series, matched = resolve_first_present_series(dataframe, candidates)
        mapped[str(output_column)] = series.astype(float)
        matches[str(output_column)] = matched

    return mapped, matches


def align_nearest(
    target_times: pd.Series,
    source_time_series: pd.Series,
    source_values: pd.DataFrame,
    *,
    tolerance: str,
) -> pd.DataFrame:
    target_frame = pd.DataFrame({"__time__": pd.to_datetime(target_times, errors="coerce")})
    aligned = pd.DataFrame(index=target_frame.index)
    if source_values.empty or source_time_series.empty:
        for column in source_values.columns:
            aligned[column] = np.nan
        return aligned

    source_frame = pd.concat(
        [pd.to_datetime(source_time_series, errors="coerce").rename("__time__"), source_values],
        axis=1,
    )
    source_frame = source_frame.dropna(subset=["__time__"]).sort_values("__time__")
    source_frame = source_frame.drop_duplicates(subset=["__time__"], keep="last")
    if source_frame.empty:
        for column in source_values.columns:
            aligned[column] = np.nan
        return aligned

    merged = pd.merge_asof(
        target_frame.sort_values("__time__"),
        source_frame,
        on="__time__",
        direction="nearest",
        tolerance=pd.Timedelta(str(tolerance).strip() or "0s"),
    )
    merged = merged.sort_index()
    for column in source_values.columns:
        if column in merged.columns:
            aligned[column] = pd.to_numeric(merged[column], errors="coerce")
        else:
            aligned[column] = np.nan
    return aligned


def align_interpolated(
    target_times: pd.Series,
    source_time_series: pd.Series,
    source_values: pd.DataFrame,
) -> pd.DataFrame:
    target_index = pd.DatetimeIndex(pd.to_datetime(target_times, errors="coerce"), name="__time__")
    aligned = pd.DataFrame(index=range(len(target_index)))
    if source_values.empty or source_time_series.empty:
        for column in source_values.columns:
            aligned[column] = np.nan
        return aligned

    source_frame = source_values.copy()
    source_frame.index = pd.DatetimeIndex(
        pd.to_datetime(source_time_series, errors="coerce"),
        name="__time__",
    )
    source_frame = source_frame[~source_frame.index.isna()]
    source_frame = source_frame.sort_index()
    source_frame = source_frame[~source_frame.index.duplicated(keep="last")]
    if source_frame.empty:
        for column in source_values.columns:
            aligned[column] = np.nan
        return aligned

    union_index = source_frame.index.union(target_index).sort_values()
    reindexed = source_frame.reindex(union_index)
    reindexed = reindexed.apply(pd.to_numeric, errors="coerce")
    reindexed = reindexed.interpolate(method="time", limit_direction="both")
    reindexed = reindexed.ffill().bfill()
    interpolated = reindexed.reindex(target_index)
    for column in source_values.columns:
        if column in interpolated.columns:
            aligned[column] = pd.to_numeric(interpolated[column], errors="coerce").to_numpy()
        else:
            aligned[column] = np.nan
    return aligned


def align_source_dataframe(
    source_dataframe: pd.DataFrame,
    *,
    target_times: pd.Series,
    source_time_column: str,
    mapping_config: Mapping[str, object],
    alignment_method: str,
    nearest_tolerance: str = "0s",
) -> Tuple[pd.DataFrame, Dict[str, Optional[str]]]:
    mapped_values, matches = map_source_columns(
        source_dataframe,
        mapping_config=mapping_config,
    )
    if source_time_column not in source_dataframe.columns:
        out = pd.DataFrame(index=range(len(target_times)))
        for column in mapped_values.columns:
            out[column] = np.nan
        return out, matches

    if alignment_method == "interpolate":
        aligned = align_interpolated(
            target_times,
            source_dataframe[source_time_column],
            mapped_values,
        )
    else:
        aligned = align_nearest(
            target_times,
            source_dataframe[source_time_column],
            mapped_values,
            tolerance=nearest_tolerance,
        )
    return aligned.reset_index(drop=True), matches


def output_schema_matches(path: Path, expected_columns: Sequence[str]) -> bool:
    if not path.exists():
        return False
    try:
        header = pd.read_csv(path, nrows=0).columns.tolist()
    except Exception:
        return False
    return header == list(expected_columns)


def output_needs_rebuild(
    output_path: Path,
    *,
    input_paths: Sequence[Path],
    expected_columns: Sequence[str],
    force_rebuild: bool,
) -> bool:
    if force_rebuild or not output_path.exists():
        return True
    if not output_schema_matches(output_path, expected_columns):
        return True
    try:
        output_mtime = output_path.stat().st_mtime
    except FileNotFoundError:
        return True
    for path in input_paths:
        if not path.exists():
            continue
        try:
            if path.stat().st_mtime > output_mtime:
                return True
        except FileNotFoundError:
            continue
    return False


def rebuild_big_output(
    output_root: Path,
    *,
    daily_prefix: str,
    big_output_path: Path,
    time_column: str,
) -> None:
    daily_files = [path for _, path in iter_daily_files(output_root, daily_prefix)]
    if not daily_files:
        if big_output_path.exists():
            big_output_path.unlink()
        return

    frames: List[pd.DataFrame] = []
    for path in daily_files:
        try:
            dataframe = pd.read_csv(path, parse_dates=[time_column])
        except Exception as exc:
            print(f"Warning: unable to load {path}: {exc}")
            continue
        frames.append(dataframe)

    if not frames:
        return

    combined = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=[time_column], keep="last")
        .sort_values(time_column)
    )
    combined.to_csv(big_output_path, index=False, float_format="%.10g")


def generate_station_stage2_plot(
    *,
    stage2_root: Path,
    output_root: Path,
    daily_prefix: str,
    big_output_path: Path,
    output_time_column: str,
    count_column_name: str,
    dry_run: bool,
) -> int:
    if not big_output_path.exists():
        rebuild_big_output(
            output_root,
            daily_prefix=daily_prefix,
            big_output_path=big_output_path,
            time_column=output_time_column,
        )
        if not big_output_path.exists():
            print(
                "No joined Stage 2 CSV is available for plotting. "
                f"Expected {big_output_path} or existing daily files under {output_root}."
            )
            return 1
        print(f"Rebuilt {big_output_path}")

    plot_output_path = stage2_root / "joined_stage_2_groups.png"
    if dry_run:
        print(f"[dry-run] would generate {plot_output_path} from {big_output_path}")
        return 0

    generate_joined_groups_plot(
        big_output_path,
        plot_output_path,
        PLOT_CONFIG_PATH,
        rate_column=count_column_name,
        rate_title="Count",
        rate_ylabel="Count",
    )
    print(f"Generated {plot_output_path}")
    return 0


def print_mapping_summary(label: str, matches: Mapping[str, object]) -> None:
    if not matches:
        print(f"  {label}: no mapped columns")
        return
    rendered: List[str] = []
    for output_name, source in matches.items():
        if source is None:
            rendered.append(f"{output_name}=<missing>")
            continue
        if isinstance(source, (list, tuple)):
            rendered.append(f"{output_name}={'+'.join(str(item) for item in source)}")
            continue
        rendered.append(f"{output_name}={source}")
    print(f"  {label}: " + ", ".join(rendered))


def main() -> int:
    args = parse_args()
    station_id = parse_station_id(args.station)
    if station_id is None:
        print(f"Invalid station identifier: {args.station}")
        return 1

    config = load_yaml_mapping(CONFIG_PATH)
    if not config:
        print(f"Missing or invalid config file: {CONFIG_PATH}")
        return 1

    selection = load_selection_for_paths([CONFIG_PATH], master_config_root=get_master_config_root())
    if not station_is_selected(station_id, selection.stations):
        print(f"Station {station_id} skipped by selection.stations.")
        return 0

    set_station(station_id)
    start_timer(__file__)

    station_dir = get_repo_root() / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / f"MINGO0{station_id}"

    event_config = config.get("event_data") or {}
    lab_config = config.get("lab_logs") or {}
    copernicus_config = config.get("copernicus") or {}
    output_config = config.get("output") or {}
    if not all(isinstance(item, Mapping) for item in (event_config, lab_config, copernicus_config, output_config)):
        print(f"Invalid Stage 2 config structure in {CONFIG_PATH}")
        return 1

    comment_prefix = str(config.get("comment_prefix", "#"))
    output_time_column = str(output_config.get("time_column", "time")).strip() or "time"
    output_columns = [
        str(column).strip()
        for column in (output_config.get("output_columns") or [])
        if str(column).strip()
    ]
    if not output_columns:
        print(f"No output.output_columns configured in {CONFIG_PATH}")
        return 1

    event_root = station_dir / str(event_config.get("input_subdir", "STAGE_2/EVENT_DATA/STEP_2_DAILY_EVENT_DATA/TASK_2/OUTPUT_FILES"))
    lab_root = station_dir / str(lab_config.get("input_subdir", "STAGE_1_PRODUCTS/LOG_DATA/OUTPUT_FILES"))
    copernicus_root = station_dir / str(copernicus_config.get("input_subdir", "STAGE_1_PRODUCTS/COPERNICUS/OUTPUT_FILES"))

    stage2_root = station_dir / str(output_config.get("stage_subdir", "STAGE_2/JOINED_DATA"))
    output_root = stage2_root / str(output_config.get("output_subdir", "OUTPUT_FILES"))
    daily_prefix = str(output_config.get("daily_file_prefix", "stage_2")).strip() or "stage_2"
    big_output_path = stage2_root / str(output_config.get("big_output_filename", "joined_stage_2.csv"))

    event_prefix = str(event_config.get("file_prefix", "event_data")).strip() or "event_data"
    lab_prefix = str(lab_config.get("file_prefix", "lab_logs")).strip() or "lab_logs"
    copernicus_prefix = str(copernicus_config.get("file_prefix", "copernicus")).strip() or "copernicus"

    event_time_column = str(event_config.get("time_column", "Time")).strip() or "Time"
    lab_time_column = str(lab_config.get("time_column", "Time")).strip() or "Time"
    copernicus_time_column = str(copernicus_config.get("time_column", "Time")).strip() or "Time"

    effective_ranges = effective_date_ranges_for_station(station_id, selection)
    count_column_name = str(output_config.get("count_column", "count")).strip() or "count"

    event_days = [
        (day_value, path)
        for day_value, path in iter_daily_files(event_root, event_prefix)
        if date_in_ranges(day_value, effective_ranges)
    ]
    if args.plot_only:
        return generate_station_stage2_plot(
            stage2_root=stage2_root,
            output_root=output_root,
            daily_prefix=daily_prefix,
            big_output_path=big_output_path,
            output_time_column=output_time_column,
            count_column_name=count_column_name,
            dry_run=args.dry_run,
        )

    if not event_days:
        print(f"No event daily files found in {event_root}")
        return 0

    if not args.dry_run:
        output_root.mkdir(parents=True, exist_ok=True)
        stage2_root.mkdir(parents=True, exist_ok=True)

    processed_days = 0
    skipped_up_to_date = 0
    skipped_incompatible_event = 0

    for day_value, event_path in event_days:
        lab_path = build_daily_file_path(lab_root, lab_prefix, day_value)
        copernicus_path = build_daily_file_path(copernicus_root, copernicus_prefix, day_value)
        output_path = build_daily_file_path(output_root, daily_prefix, day_value)
        input_paths = [event_path, lab_path, copernicus_path]

        if not output_needs_rebuild(
            output_path,
            input_paths=input_paths,
            expected_columns=output_columns,
            force_rebuild=args.all,
        ):
            skipped_up_to_date += 1
            if args.verbose:
                print(f"Skipping {day_value:%Y-%m-%d}: output already up to date.")
            continue

        print(f"Processing {day_value:%Y-%m-%d}")

        event_dataframe = read_daily_csv(
            event_path,
            time_column=event_time_column,
            comment_prefix=comment_prefix,
        )
        try:
            event_normalized, event_matches = normalize_event_dataframe(
                event_dataframe,
                event_config=event_config,
                output_config=output_config,
            )
        except IncompatibleEventSchemaError as exc:
            skipped_incompatible_event += 1
            print(f"  ! Skipped: {exc}")
            continue

        target_times = event_normalized[output_time_column]

        lab_dataframe = read_daily_csv(
            lab_path,
            time_column=lab_time_column,
            comment_prefix=comment_prefix,
        )
        lab_aligned, lab_matches = align_source_dataframe(
            lab_dataframe,
            target_times=target_times,
            source_time_column=lab_time_column,
            mapping_config=lab_config.get("column_candidates") or {},
            alignment_method=str(lab_config.get("alignment_method", "nearest")).strip().lower(),
            nearest_tolerance=str(lab_config.get("nearest_tolerance", "0s")).strip() or "0s",
        )

        copernicus_dataframe = read_daily_csv(
            copernicus_path,
            time_column=copernicus_time_column,
            comment_prefix=comment_prefix,
        )
        copernicus_aligned, copernicus_matches = align_source_dataframe(
            copernicus_dataframe,
            target_times=target_times,
            source_time_column=copernicus_time_column,
            mapping_config=copernicus_config.get("column_candidates") or {},
            alignment_method=str(copernicus_config.get("alignment_method", "interpolate")).strip().lower(),
            nearest_tolerance=str(copernicus_config.get("nearest_tolerance", "0s")).strip() or "0s",
        )

        joined = pd.DataFrame(index=event_normalized.index)
        joined[output_time_column] = target_times

        for column in (count_column_name, "Q_event_mean"):
            if column in event_normalized.columns:
                joined[column] = pd.to_numeric(event_normalized[column], errors="coerce")

        for column in lab_aligned.columns:
            joined[column] = pd.to_numeric(lab_aligned[column], errors="coerce")

        for column in copernicus_aligned.columns:
            joined[column] = pd.to_numeric(copernicus_aligned[column], errors="coerce")

        sector_columns = [
            column
            for column in event_normalized.columns
            if column not in {output_time_column, "count", "Q_event_mean"}
        ]
        for column in sector_columns:
            joined[column] = pd.to_numeric(event_normalized[column], errors="coerce")

        for column in output_columns:
            if column not in joined.columns:
                joined[column] = np.nan

        joined = joined.loc[:, output_columns].sort_values(output_time_column)
        joined[output_time_column] = joined[output_time_column].dt.strftime("%Y-%m-%d %H:%M:%S")

        if args.verbose:
            print_mapping_summary("event", event_matches)
            print_mapping_summary("lab", lab_matches)
            print_mapping_summary("copernicus", copernicus_matches)

        if args.dry_run:
            processed_days += 1
            print(f"  [dry-run] would write {output_path}")
            continue

        output_path.parent.mkdir(parents=True, exist_ok=True)
        joined.to_csv(output_path, index=False, float_format="%.10g")
        processed_days += 1
        print(f"  Wrote {output_path}")

    if args.dry_run:
        print("Dry-run complete.")
        print(
            "Join summary: "
            f"processed={processed_days}, skipped_up_to_date={skipped_up_to_date}, "
            f"skipped_incompatible_event={skipped_incompatible_event}"
        )
        return 0

    rebuild_big_output(
        output_root,
        daily_prefix=daily_prefix,
        big_output_path=big_output_path,
        time_column=output_time_column,
    )
    print(f"Rebuilt {big_output_path}")
    try:
        generate_station_stage2_plot(
            stage2_root=stage2_root,
            output_root=output_root,
            daily_prefix=daily_prefix,
            big_output_path=big_output_path,
            output_time_column=output_time_column,
            count_column_name=count_column_name,
            dry_run=False,
        )
    except Exception as exc:
        print(f"Warning: unable to generate grouped Stage 2 plot: {exc}")
    print(
        "Join summary: "
        f"processed={processed_days}, skipped_up_to_date={skipped_up_to_date}, "
        f"skipped_incompatible_event={skipped_incompatible_event}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
