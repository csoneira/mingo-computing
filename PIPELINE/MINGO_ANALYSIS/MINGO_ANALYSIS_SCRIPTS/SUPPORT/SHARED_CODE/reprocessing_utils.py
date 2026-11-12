
"""Provide shared helpers for selecting and scheduling reprocessing inputs."""

from __future__ import annotations

"""Helpers for safely retrieving values from reprocessing parameter tables."""

from collections.abc import Mapping, MutableMapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.selection_config import parse_station_id


QA_REPROCESSING_METADATA_KEYS: tuple[str, ...] = (
    "qa_reprocessing_mode",
    "qa_reprocessing_selector_ids",
    "qa_reprocessing_failed_columns",
    "qa_reprocessing_failed_versions",
)
QA_REPROCESSING_FILENAME_PREFIXES: tuple[str, ...] = (
    "cleaned_",
    "calibrated_",
    "listed_",
    "fitted_",
    "postprocessed_",
    "corrected_",
    "post_",
)
QA_REPROCESSING_FILENAME_SUFFIXES: frozenset[str] = frozenset(
    {".parquet", ".csv", ".dat", ".txt", ".json", ".gz", ".bz2", ".xz", ".zip", ".tar"}
)


def _normalize_legacy_station_prefix(text: str) -> str:
    lowered = text.lower()
    if lowered.startswith("mini"):
        return "mi01" + text[4:]
    return text


def empty_qa_reprocessing_context() -> dict[str, object]:
    return {
        "qa_reprocessing_mode": 0,
        "qa_reprocessing_selector_ids": "",
        "qa_reprocessing_failed_columns": "",
        "qa_reprocessing_failed_versions": "",
    }


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _flatten_semicolon_tokens(values: pd.Series) -> list[str]:
    tokens: list[str] = []
    for raw_value in values.astype(str).tolist():
        for token in raw_value.split(";"):
            token_text = token.strip()
            if token_text:
                tokens.append(token_text)
    return _ordered_unique(tokens)


def canonical_processing_basename(filename: object) -> str:
    """Return the Stage 1 canonical basename for a file path or filename."""

    text = Path(str(filename)).name.strip()
    if not text:
        return ""

    changed = True
    while changed:
        changed = False
        for prefix in QA_REPROCESSING_FILENAME_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
                changed = True

    while True:
        suffix = Path(text).suffix.lower()
        if not suffix or suffix not in QA_REPROCESSING_FILENAME_SUFFIXES:
            break
        text = Path(text).stem.strip()

    return _normalize_legacy_station_prefix(text)


def infer_station_number_from_processing_name(filename: object) -> int | None:
    """Return station number parsed from a canonical processing basename."""

    basename = canonical_processing_basename(filename)
    lowered = basename.lower()
    if len(lowered) < 4 or not lowered.startswith("mi0"):
        return None
    try:
        return int(lowered[3])
    except ValueError:
        return None


@lru_cache(maxsize=None)
def _load_qa_retry_state_table(repo_root_text: str, station_num: int) -> pd.DataFrame:
    repo_root = Path(repo_root_text)
    state_path = (
        repo_root
        / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
        / f"MINGO{station_num:02d}"
        / "STAGE_0"
        / "REPROCESSING"
        / "STEP_0"
        / "METADATA"
        / f"qa_retry_state_{station_num}.csv"
    )
    if not state_path.exists() or state_path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        table_df = pd.read_csv(state_path, keep_default_na=False, dtype=str)
    except Exception:
        return pd.DataFrame()
    if "basename" not in table_df.columns:
        return pd.DataFrame()
    return table_df


def load_qa_reprocessing_context_for_file(
    station_id: object,
    basename: str,
    *,
    repo_root: str | Path | None = None,
) -> dict[str, object]:
    """Return active QA retry context for a basename, or an empty context."""

    context = empty_qa_reprocessing_context()
    station_num = parse_station_id(station_id)
    basename_text = str(basename).strip()
    if station_num is None or not basename_text:
        return context

    repo_root_path = Path(repo_root) if repo_root is not None else get_repo_root()
    table_df = _load_qa_retry_state_table(str(repo_root_path), station_num)
    if table_df.empty:
        return context

    matches = table_df[table_df["basename"].astype(str).str.strip() == basename_text].copy()
    if matches.empty:
        return context

    if "is_active" in matches.columns:
        is_active = matches["is_active"].astype(str).str.strip().str.lower()
        matches = matches[is_active.isin({"1", "true", "yes", "on"})].copy()
    if matches.empty:
        return context

    selector_ids = (
        _ordered_unique(matches["selector_id"].astype(str).tolist())
        if "selector_id" in matches.columns
        else []
    )
    failed_columns = (
        _flatten_semicolon_tokens(matches["failed_quality_columns"])
        if "failed_quality_columns" in matches.columns
        else []
    )
    failed_versions = (
        _flatten_semicolon_tokens(matches["failed_quality_versions"])
        if "failed_quality_versions" in matches.columns
        else []
    )

    context.update(
        {
            "qa_reprocessing_mode": 1,
            "qa_reprocessing_selector_ids": ";".join(selector_ids),
            "qa_reprocessing_failed_columns": ";".join(failed_columns),
            "qa_reprocessing_failed_versions": ";".join(failed_versions),
        }
    )
    return context


def load_active_qa_retry_basenames(
    station_id: object,
    *,
    repo_root: str | Path | None = None,
) -> set[str]:
    """Return the active QA retry basenames for a station."""

    station_num = parse_station_id(station_id)
    if station_num is None:
        return set()

    repo_root_path = Path(repo_root) if repo_root is not None else get_repo_root()
    table_df = _load_qa_retry_state_table(str(repo_root_path), station_num)
    if table_df.empty:
        return set()

    active_df = table_df.copy()
    if "is_active" in active_df.columns:
        is_active = active_df["is_active"].astype(str).str.strip().str.lower()
        active_df = active_df[is_active.isin({"1", "true", "yes", "on"})].copy()
    if active_df.empty:
        return set()

    return {
        value.strip()
        for value in active_df["basename"].astype(str).tolist()
        if value and value.strip()
    }


def filter_filenames_by_qa_retry_basenames(
    file_names: list[str] | tuple[str, ...] | set[str],
    qa_basenames: set[str],
) -> list[str]:
    """Keep only filenames whose canonical basename is present in *qa_basenames*."""

    if not qa_basenames:
        return []
    return [
        str(file_name)
        for file_name in file_names
        if canonical_processing_basename(file_name) in qa_basenames
    ]


def filter_filenames_other_than_qa_retry_basenames(
    file_names: list[str] | tuple[str, ...] | set[str],
    qa_basenames: set[str],
) -> list[str]:
    """Keep only filenames whose canonical basename is not present in *qa_basenames*."""

    if not qa_basenames:
        return [str(file_name) for file_name in file_names]
    return [
        str(file_name)
        for file_name in file_names
        if canonical_processing_basename(file_name) not in qa_basenames
    ]


def apply_qa_reprocessing_context(
    target: MutableMapping[str, object],
    context: Mapping[str, object] | None,
) -> None:
    """Persist the QA retry awareness fields into a metadata/runtime mapping."""

    effective_context = empty_qa_reprocessing_context()
    if context:
        for key in QA_REPROCESSING_METADATA_KEYS:
            if key in context:
                effective_context[key] = context[key]
    target.update(effective_context)


def _component_column_values(
    params: pd.DataFrame | pd.Series | dict[str, object],
    key: str,
) -> list[Any] | None:
    prefix = f"{key}__"

    if isinstance(params, pd.DataFrame):
        component_columns = [col for col in params.columns if isinstance(col, str) and col.startswith(prefix)]
        row = params.iloc[0] if not params.empty else None
    elif isinstance(params, pd.Series):
        component_columns = [col for col in params.index if isinstance(col, str) and col.startswith(prefix)]
        row = params
    elif isinstance(params, dict):
        component_columns = [col for col in params.keys() if isinstance(col, str) and col.startswith(prefix)]
        row = params
    else:
        return None

    if not component_columns or row is None:
        return None

    indexed_columns: list[tuple[int, str]] = []
    for column_name in component_columns:
        suffix = column_name[len(prefix) :]
        if not suffix.isdigit():
            continue
        indexed_columns.append((int(suffix), column_name))
    if not indexed_columns:
        return None

    values: list[Any] = []
    for _, column_name in sorted(indexed_columns):
        value = row[column_name]
        try:
            missing = pd.isna(value)
        except TypeError:
            missing = False
        if isinstance(missing, (np.ndarray, pd.Series)):
            missing = bool(np.all(missing))
        values.append(None if missing else value)
    return values


def get_reprocessing_value(
    params: pd.DataFrame | pd.Series | dict[str, object] | None, key: str
) -> Any:
    """
    Return the scalar reprocessing value associated with *key*.

    The helper accepts the raw DataFrame produced by the metadata tables (one row
    per file), as well as already-extracted Series or dict representations. It
    guards against missing keys, all-NaN columns, and NumPy containers that would
    otherwise raise “ambiguous truth value” errors when inspected in conditionals.
    """

    if params is None:
        return None

    if isinstance(params, pd.DataFrame):
        if params.empty:
            return None
        if key in params.columns:
            value = params.iloc[0][key]
        else:
            component_values = _component_column_values(params, key)
            return component_values
    elif isinstance(params, pd.Series):
        if key in params.index:
            value = params[key]
        else:
            component_values = _component_column_values(params, key)
            return component_values
    elif isinstance(params, dict):
        if key in params:
            value = params.get(key)
        else:
            component_values = _component_column_values(params, key)
            return component_values
    else:
        return None

    if isinstance(value, pd.Series):
        if value.empty:
            return None
        value = value.squeeze()

    if isinstance(value, np.ndarray):
        if value.size == 0:
            return None

    try:
        missing = pd.isna(value)
    except TypeError:
        missing = False
    else:
        if isinstance(missing, (np.ndarray, pd.Series)):
            missing = bool(np.all(missing))

    if missing:
        return None

    return value
