
"""Shared STEP_1 helpers for TASK_1..TASK_5 scripts."""

from __future__ import annotations

import argparse
from ast import literal_eval
import builtins
from array import array
from collections.abc import Mapping as MappingABC
import csv
from datetime import datetime
import fcntl
from functools import lru_cache
import math
import os
import re
from pathlib import Path
import stat
import tempfile
from typing import Callable, Dict, Iterable, List, Mapping, Sequence, Tuple, TypeVar

import numpy as np
import pandas as pd
import yaml

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.config_loader import (
    load_declared_parameter_names,
    load_parameter_overrides,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.file_selection import extract_run_datetime_from_name
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import (
    get_master_config_root,
    get_repo_root,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.reprocessing_utils import infer_station_number_from_processing_name
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.selection_config import load_yaml_mapping

def atomic_write_parquet(frame, destination, **kwargs):
    """Write a parquet beside its destination, then atomically replace it."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{destination.stem}.", suffix=destination.suffix or ".parquet",
        dir=destination.parent, delete=False,
    )
    temporary = Path(handle.name)
    handle.close()
    try:
        frame.to_parquet(temporary, **kwargs)
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def filter_unprocessed_with_existing_outputs(
    file_names: Iterable[str], output_directory: str | Path, *,
    input_prefix: str, output_prefix: str, force_reprocess: bool,
) -> list[str]:
    """Keep unprocessed inputs unless their identity already has an output."""
    names = list(file_names)
    if force_reprocess:
        return names
    output_root = Path(output_directory)
    eligible = []
    for name in names:
        if not name.startswith(input_prefix):
            eligible.append(name)
            continue
        output_name = output_prefix + name[len(input_prefix):]
        if not (output_root / output_name).exists():
            eligible.append(name)
    return eligible


def resolve_reprocessing_options(config: Mapping[str, object], *, log_fn=print) -> tuple[bool, bool]:
    """Resolve completed-input and forced-unprocessed modes independently."""
    legacy_present = "complete_reanalysis" in config
    completed = bool(config.get("reprocess_from_completed", config.get("complete_reanalysis", False)))
    forced = bool(config.get("reprocess_from_unprocessed", False))
    if legacy_present and "reprocess_from_completed" not in config:
        log_fn("[DEPRECATED_CONFIG] complete_reanalysis is deprecated; use reprocess_from_completed. It does not enable reprocess_from_unprocessed.")
    log_fn(f"[REPROCESSING_OPTIONS] reprocess_from_completed={completed}, reprocess_from_unprocessed={forced}")
    return completed, forced


DEFAULT_STATION_CHOICES: Tuple[str, ...] = ("0", "1", "2", "3", "4")
DEFAULT_IMPORTANT_KEYWORDS: Tuple[str, ...] = (
    "error",
    "warning",
    "failed",
    "exception",
    "traceback",
    "usage",
)
STEP1_MASTER_CONFIG_RELATIVE_PATH = Path("STAGE_1") / "EVENT_DATA" / "STEP_1" / "config_step_1.yaml"
STEP1_METADATA_OUTPUT_TYPES: Tuple[str, ...] = (
    "activation",
    "calibration",
    "chi2_four_plane",
    "deep_fiter",
    "efficiency",
    "execution",
    "filter",
    "gate_test",
    "noise_control",
    "pattern",
    "profiling",
    "rate_histogram",
    "specific",
    "status",
    "trigger_type",
)
STEP1_METADATA_OUTPUT_DEFAULTS: Dict[str, bool] = {
    metadata_type: True for metadata_type in STEP1_METADATA_OUTPUT_TYPES
}
STEP1_LOG_OUTPUT_TYPES: Tuple[str, ...] = (
    "filter_metrics",
)
STEP1_LOG_OUTPUT_DEFAULTS: Dict[str, bool] = {
    logging_type: True for logging_type in STEP1_LOG_OUTPUT_TYPES
}

EVENTS_PER_SECOND_MAX = 40
EVENTS_PER_SECOND_COLUMNS = [
    *(f"events_per_second_{idx}_count" for idx in range(EVENTS_PER_SECOND_MAX + 1)),
    "events_per_second_total_seconds",
    "events_per_second_global_rate",
]
EVENTS_PER_SECOND_COLUMN_SET = frozenset(EVENTS_PER_SECOND_COLUMNS)
TRACEABILITY_COLUMNS: Tuple[str, ...] = ("filename_base", "execution_timestamp", "param_hash")
CANONICAL_TT_LABEL_SEQUENCE: Tuple[str, ...] = (
    "0",
    "1",
    "2",
    "3",
    "4",
    "12",
    "13",
    "14",
    "23",
    "24",
    "34",
    "123",
    "124",
    "134",
    "234",
    "1234",
)
CANONICAL_TT_LABELS: frozenset[str] = frozenset(
    CANONICAL_TT_LABEL_SEQUENCE
)
TT_RATE_COLUMN_RE = re.compile(r"^(?P<prefix>.+_tt)_(?P<label>[^_]+)_rate_hz$")
METADATA_MAX_FULL_SCAN_BYTES = 128 * 1024 * 1024
VertexKeyT = TypeVar("VertexKeyT")
UPSTREAM_OFFENDER_COUNT_COLUMNS: Tuple[str, ...] = (
    "task1_problematic_channel_count",
    "task2_problematic_strip_count",
    "task3_problematic_plane_count",
)
DEFAULT_TRIGGER_TYPE_OFFENDER_THRESHOLDS: Tuple[int, ...] = (0, 1, 2, 3, 4, 5)
METADATA_COMPONENT_SUFFIX_RE = re.compile(r"^(?P<source>.+)__([0-9]+)$")
METADATA_VECTOR_STRING_COLUMNS: frozenset[str] = frozenset(
    {
        "timtrack_projection_ellipse_contour_fractions",
    }
)


def raw_end_column(plane: int, strip: int, end: str, quantity: str) -> str:
    clean_end = str(end).strip().lower()
    if clean_end in {"f", "front"}:
        clean_end = "ef"
    elif clean_end in {"b", "back"}:
        clean_end = "eb"
    return f"p{int(plane)}_s{int(strip)}_{clean_end}_{str(quantity).strip().lower()}"


def strip_quantity_column(plane: int, strip: int, quantity: str) -> str:
    return f"p{int(plane)}_s{int(strip)}_{str(quantity).strip().lower()}"


def plane_quantity_column(plane: int, quantity: str) -> str:
    return f"p{int(plane)}_{str(quantity).strip().lower()}"


def build_step1_legacy_column_rename_map() -> Dict[str, str]:
    rename_map: Dict[str, str] = {
        "acq_tt": "tt_task0_acq",
        "raw_tt": "tt_task0_raw",
        "clean_tt": "tt_task1_clean",
        "cal_tt": "tt_task2_cal",
        "list_tt": "tt_task3_list",
        "fit_tt": "tt_task4_fit",
        "post_tt": "tt_task5_post",
        "raw_to_clean_tt": "transferred_task1_raw_to_clean",
        "clean_to_cal_tt": "transferred_task2_clean_to_cal",
        "cal_to_list_tt": "transferred_task3_cal_to_list",
        "fit_to_post_tt": "transferred_task5_fit_to_post",
        "transferred_acq_to_raw": "transferred_task0_acq_to_raw",
        "transferred_raw_to_clean": "transferred_task1_raw_to_clean",
        "transferred_clean_to_cal": "transferred_task2_clean_to_cal",
        "transferred_cal_to_list": "transferred_task3_cal_to_list",
        "transferred_fit_to_post": "transferred_task5_fit_to_post",
        "event_projected_tt": "tt_task4_projected",
        "task1_problematic_channel_count": "filter_task1_problematic_channel_count",
        "task1_problematic_channel_resolution_exact": "filter_task1_problematic_channel_exact",
        "task2_problematic_strip_count": "filter_task2_problematic_strip_count",
        "task2_problematic_strip_resolution_exact": "filter_task2_problematic_strip_exact",
        "task3_problematic_plane_count": "filter_task3_problematic_plane_count",
        "task3_problematic_plane_resolution_exact": "filter_task3_problematic_plane_exact",
        "total_problematic_offender_count": "filter_total_problematic_offender_count",
        "plane_charge_topology_code": "topology_task2_strip",
        "charge_event": "event_charge",
        "delta_s": "event_s_err",
        "conv_distance": "timtrack_conv_distance",
        "converged": "timtrack_converged",
        "iterations": "timtrack_iterations",
        "Time": "datetime",
    }
    for plane in range(1, 5):
        rename_map[f"P{plane}_Q_total_uncal"] = plane_quantity_column(plane, "qsum_uncalibrated")
        rename_map[f"P{plane}_Q_dif_final"] = plane_quantity_column(plane, "qdif")
        rename_map[f"P{plane}_Q_sum_final"] = plane_quantity_column(plane, "qsum")
        rename_map[f"P{plane}_T_dif_final"] = plane_quantity_column(plane, "tdif")
        rename_map[f"P{plane}_T_sum_final"] = plane_quantity_column(plane, "tsum")
        rename_map[f"P{plane}_Y_final"] = plane_quantity_column(plane, "ypos")
        rename_map[f"z_P{plane}"] = f"z_p{plane}"
        rename_map[f"charge_{plane}"] = plane_quantity_column(plane, "qsum")
        rename_map[f"th_chi_{plane}"] = f"th_chisq_df_{plane}"
        rename_map[f"ext_res_tdif_{plane}"] = f"p{plane}_tdif_res_ext"
        rename_map[f"res_tdif_{plane}"] = f"p{plane}_tdif_res"
        rename_map[f"ext_res_tsum_{plane}"] = f"p{plane}_tsum_res_ext"
        rename_map[f"res_tsum_{plane}"] = f"p{plane}_tsum_res"
        rename_map[f"ext_res_ystr_{plane}"] = f"p{plane}_ystr_res_ext"
        rename_map[f"res_ystr_{plane}"] = f"p{plane}_ystr_res"
        rename_map[f"ext_res_tdif_{plane}_err"] = f"p{plane}_tdif_res_ext_err"
        rename_map[f"res_tdif_{plane}_err"] = f"p{plane}_tdif_res_err"
        rename_map[f"ext_res_tsum_{plane}_err"] = f"p{plane}_tsum_res_ext_err"
        rename_map[f"res_tsum_{plane}_err"] = f"p{plane}_tsum_res_err"
        rename_map[f"ext_res_ystr_{plane}_err"] = f"p{plane}_ystr_res_ext_err"
        rename_map[f"res_ystr_{plane}_err"] = f"p{plane}_ystr_res_err"
        for strip in range(1, 5):
            rename_map[f"Q{plane}_F_{strip}"] = raw_end_column(plane, strip, "ef", "q")
            rename_map[f"Q{plane}_B_{strip}"] = raw_end_column(plane, strip, "eb", "q")
            rename_map[f"T{plane}_F_{strip}"] = raw_end_column(plane, strip, "ef", "t")
            rename_map[f"T{plane}_B_{strip}"] = raw_end_column(plane, strip, "eb", "t")
            rename_map[f"Q{plane}_Q_sum_{strip}"] = strip_quantity_column(plane, strip, "qsum")
            rename_map[f"Q{plane}_Q_dif_{strip}"] = strip_quantity_column(plane, strip, "qdif")
            rename_map[f"T{plane}_T_sum_{strip}"] = strip_quantity_column(plane, strip, "tsum")
            rename_map[f"T{plane}_T_dif_{strip}"] = strip_quantity_column(plane, strip, "tdif")
            rename_map[f"Q_P{plane}s{strip}"] = strip_quantity_column(plane, strip, "qsum")
    for ndf in range(0, 16):
        rename_map[f"th_chi_{ndf}"] = f"th_chisq_df_{ndf}"
    for name in ("x", "y", "xp", "yp", "s", "t0", "theta", "phi"):
        rename_map[name] = f"event_{name}"
    for name in ("x_err", "y_err", "s_err", "t0_err", "theta_err", "phi_err"):
        rename_map[name] = f"event_{name}"
    return rename_map


STEP1_LEGACY_COLUMN_RENAME_MAP: Dict[str, str] = build_step1_legacy_column_rename_map()
STEP1_OBSOLETE_COLUMNS: frozenset[str] = frozenset(
    {
        "adj_dis",
        "Phi_pred",
        "Theta_pred",
        "region",
        "extension_tt",
        "processed_tt",
        "tracking_tt",
        "active_strips_P1",
        "active_strips_P2",
        "active_strips_P3",
        "active_strips_P4",
    }
)


def canonicalize_step1_columns(df: pd.DataFrame, *, drop_obsolete: bool = True) -> pd.DataFrame:
    """Normalize legacy STEP_1 column names once at dataframe boundaries."""
    rename_map = {
        old_name: new_name
        for old_name, new_name in STEP1_LEGACY_COLUMN_RENAME_MAP.items()
        if old_name in df.columns and new_name not in df.columns
    }
    for column_name in df.columns:
        if column_name.startswith("det_"):
            new_column_name = f"event_{column_name}"
            if new_column_name not in df.columns:
                rename_map.setdefault(column_name, new_column_name)
        elif column_name.startswith("tim_"):
            new_column_name = f"event_{column_name}"
            if new_column_name not in df.columns:
                rename_map.setdefault(column_name, new_column_name)
    if rename_map:
        df = df.rename(columns=rename_map)
    duplicate_legacy = [
        old_name
        for old_name, new_name in STEP1_LEGACY_COLUMN_RENAME_MAP.items()
        if old_name in df.columns and new_name in df.columns and old_name != new_name
    ]
    duplicate_legacy.extend(
        column_name
        for column_name in df.columns
        if (
            (column_name.startswith("det_") or column_name.startswith("tim_"))
            and f"event_{column_name}" in df.columns
        )
    )
    if duplicate_legacy:
        df = df.drop(columns=duplicate_legacy, errors="ignore")
    if df.columns.has_duplicates:
        df = df.loc[:, ~df.columns.duplicated()].copy()
    if drop_obsolete:
        obsolete_columns = [
            col
            for col in df.columns
            if col in STEP1_OBSOLETE_COLUMNS
            or col.endswith("_crstlk")
            or "_with_crstlk" in col
            or "_no_crstlk" in col
        ]
        if obsolete_columns:
            df = df.drop(columns=obsolete_columns, errors="ignore")
    return df


def add_topology_task1_channel(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        raw_end_column(plane, strip, end, "q")
        for plane in range(1, 5)
        for strip in range(1, 5)
        for end in ("ef", "eb")
    ]
    if not all(col in df.columns for col in columns):
        return df
    values = df.loc[:, columns].apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy(copy=False)
    df.loc[:, "topology_task1_channel"] = [
        "".join("1" if value != 0 else "0" for value in row)
        for row in values
    ]
    return df


def add_topology_task1_column(df: pd.DataFrame) -> pd.DataFrame:
    """Add one bit per plane/strip, active when either end has raw charge."""
    columns_by_strip = [
        [raw_end_column(plane, strip, end, "q") for end in ("ef", "eb")]
        for plane in range(1, 5)
        for strip in range(1, 5)
    ]
    if not all(column in df.columns for columns in columns_by_strip for column in columns):
        return df
    values = df.loc[:, [column for columns in columns_by_strip for column in columns]]
    values = values.apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy(copy=False)
    paired = values.reshape(len(df), 16, 2)
    active = np.any(paired != 0, axis=2)
    df.loc[:, "topology_task1_column"] = [
        "".join("1" if value else "0" for value in row) for row in active
    ]
    return df


def add_topology_task1_channel_qt(df: pd.DataFrame) -> pd.DataFrame:
    """Add one bit per end channel, active only when both Q and T are nonzero."""
    channel_columns = [
        (raw_end_column(plane, strip, end, "q"), raw_end_column(plane, strip, end, "t"))
        for plane in range(1, 5)
        for strip in range(1, 5)
        for end in ("ef", "eb")
    ]
    if not all(
        column in df.columns for pair in channel_columns for column in pair
    ):
        return df
    values = df.loc[:, [column for pair in channel_columns for column in pair]]
    values = values.apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy(copy=False)
    paired = values.reshape(len(df), 32, 2)
    active = (paired[:, :, 0] != 0) & (paired[:, :, 1] != 0)
    df.loc[:, "topology_task1_channel_qt"] = [
        "".join("1" if value else "0" for value in row) for row in active
    ]
    return df


def add_topology_task2_strip(
    df: pd.DataFrame,
    crosstalk_thresholds: dict[tuple[int, int], float] | None = None,
) -> pd.DataFrame:
    """Encode strip activity, optionally requiring charge above crosstalk width.

    ``crosstalk_thresholds`` is keyed by ``(plane, strip)``. When supplied, use
    calibrated qsum where available and mark a strip active only for
    ``qsum > threshold``. The default preserves the historical ``qsum > 0``
    rule for call sites that do not have Task-2 crosstalk calibration.
    """
    columns = []
    for plane in range(1, 5):
        for strip in range(1, 5):
            column = strip_quantity_column(plane, strip, "qsum")
            calibrated_column = f"{column}_cal"
            accepted_column = f"{column}_task2"
            if crosstalk_thresholds is not None and accepted_column in df.columns:
                column = accepted_column
            elif crosstalk_thresholds is not None and calibrated_column in df.columns:
                column = calibrated_column
            columns.append(column)
    if not all(col in df.columns for col in columns):
        return df
    values = df.loc[:, columns].apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy(copy=False)
    if crosstalk_thresholds is None:
        thresholds = np.zeros((1, 16), dtype=float)
    else:
        thresholds = np.asarray(
            [
                float(crosstalk_thresholds.get((plane, strip), 0.0) or 0.0)
                for plane in range(1, 5)
                for strip in range(1, 5)
            ],
            dtype=float,
        )[None, :]
    topology_values = [
        "".join(
            "1" if np.isfinite(value) and value > threshold else "0"
            for value, threshold in zip(row, thresholds[0])
        )
        for row in values
    ]
    if "topology_task2_strip" in df.columns:
        df = df.drop(columns=["topology_task2_strip"])
    return pd.concat(
        [df, pd.DataFrame({"topology_task2_strip": topology_values}, index=df.index)],
        axis=1,
    ).copy()


def add_topology_task3_plane(df: pd.DataFrame) -> pd.DataFrame:
    columns = [plane_quantity_column(plane, "qsum") for plane in range(1, 5)]
    if not all(col in df.columns for col in columns):
        return df
    values = df.loc[:, columns].apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy(copy=False)
    df.loc[:, "topology_task3_plane"] = [
        "".join("1" if np.isfinite(value) and value > 0 else "0" for value in row)
        for row in values
    ]
    return df


def _metadata_value_is_empty(value: object) -> bool:
    return value is None or value == "" or (isinstance(value, float) and math.isnan(value))


def split_metadata_component_column(column_name: str) -> tuple[str, int] | None:
    match = METADATA_COMPONENT_SUFFIX_RE.match(str(column_name))
    if match is None:
        return None
    try:
        return match.group("source"), int(match.group(2))
    except (TypeError, ValueError):
        return None


def _coerce_metadata_scalar(value: object) -> object:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return int(bool(value))
    return value


def _metadata_prefers_component_columns(key: str) -> bool:
    return key in METADATA_VECTOR_STRING_COLUMNS or key.endswith("_Q_FB_coeffs")


def _parse_metadata_string_container(key: str, value: str) -> object | None:
    text = str(value).strip()
    if not text:
        return None

    lowered = text.lower()
    if lowered == "true":
        return 1
    if lowered == "false":
        return 0

    if key in METADATA_VECTOR_STRING_COLUMNS:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if parts and all(re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", part) for part in parts):
            return [float(part) for part in parts]

    if text.startswith("[") or text.startswith("("):
        try:
            parsed = literal_eval(text)
        except Exception:
            return None
        if isinstance(parsed, (list, tuple)):
            return parsed

    if text.startswith("{"):
        try:
            parsed = literal_eval(text)
        except Exception:
            return None
        if isinstance(parsed, dict):
            return parsed

    return None


def _iter_normalized_metadata_items(key: str, value: object) -> Iterable[tuple[str, object]]:
    value = _coerce_metadata_scalar(value)
    if _metadata_value_is_empty(value):
        if _metadata_prefers_component_columns(str(key)):
            return
        yield key, value
        return

    if isinstance(value, str):
        parsed = _parse_metadata_string_container(key, value)
        if parsed is not None:
            yield from _iter_normalized_metadata_items(key, parsed)
            return
        yield key, value
        return

    if isinstance(value, np.ndarray):
        if value.ndim == 0:
            yield key, _coerce_metadata_scalar(value.item())
            return
        value = value.tolist()

    if isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            yield from _iter_normalized_metadata_items(f"{key}__{idx}", item)
        return

    if isinstance(value, MappingABC):
        for subkey, subvalue in value.items():
            subkey_text = str(subkey).strip()
            if not subkey_text:
                continue
            yield from _iter_normalized_metadata_items(f"{key}__{subkey_text}", subvalue)
        return

    yield key, value


def normalize_tt_label(value: object, default: str = "0") -> str:
    """Return canonical TT label text (e.g. 12.0 -> 12, 12.0_134.0 -> 12_134)."""
    if value is None:
        return default

    if isinstance(value, (np.integer, int)):
        return str(int(value))

    if isinstance(value, (np.floating, float)):
        if not np.isfinite(value):
            return default
        if float(value).is_integer():
            return str(int(value))
        return str(value)

    text = str(value).strip()
    if not text:
        return default

    if "_" in text:
        return "_".join(normalize_tt_label(part, default=default) for part in text.split("_"))

    try:
        numeric = float(text)
    except (TypeError, ValueError):
        return text

    if not np.isfinite(numeric):
        return default
    if numeric.is_integer():
        return str(int(numeric))
    return text


def select_exact_minimum_vertex_cover(
    weighted_edges: Sequence[tuple[VertexKeyT, VertexKeyT, float]],
    order_key_fn: Callable[[VertexKeyT], tuple],
) -> List[VertexKeyT]:
    """Return a deterministic exact minimum vertex cover for a weighted edge list.

    The primary objective is minimum cardinality. When multiple minimum-cardinality
    covers exist, ties are broken deterministically by preferring the cover whose
    selected vertices touch the largest number of failed pairs, then the largest
    summed failure severity, and finally the lexicographically-smallest vertex
    list under *order_key_fn*.
    """
    if not weighted_edges:
        return []

    vertex_keys = sorted(
        {
            vertex_key
            for edge in weighted_edges
            for vertex_key in edge[:2]
        },
        key=order_key_fn,
    )
    if not vertex_keys:
        return []

    index_by_vertex = {vertex_key: idx for idx, vertex_key in enumerate(vertex_keys)}
    n_vertices = len(vertex_keys)
    adjacency_masks = [0] * n_vertices
    severity_matrix = [[0.0] * n_vertices for _ in range(n_vertices)]
    incident_edge_counts = [0] * n_vertices
    incident_severity_sums = [0.0] * n_vertices

    for vertex_a, vertex_b, raw_severity in weighted_edges:
        idx_a = index_by_vertex[vertex_a]
        idx_b = index_by_vertex[vertex_b]
        if idx_a == idx_b:
            continue
        try:
            severity = float(raw_severity)
        except (TypeError, ValueError):
            severity = 1.0
        if not math.isfinite(severity) or severity <= 0:
            severity = 1.0

        adjacency_masks[idx_a] |= 1 << idx_b
        adjacency_masks[idx_b] |= 1 << idx_a
        severity_matrix[idx_a][idx_b] = severity
        severity_matrix[idx_b][idx_a] = severity
        incident_edge_counts[idx_a] += 1
        incident_edge_counts[idx_b] += 1
        incident_severity_sums[idx_a] += severity
        incident_severity_sums[idx_b] += severity

    full_mask = (1 << n_vertices) - 1

    def _iter_bits(mask: int):
        while mask:
            bit = mask & -mask
            yield bit.bit_length() - 1
            mask ^= bit

    @lru_cache(maxsize=None)
    def _vertex_remaining_score(active_mask: int, vertex_idx: int) -> tuple[int, float]:
        neighbors_mask = adjacency_masks[vertex_idx] & active_mask
        if neighbors_mask == 0:
            return (0, 0.0)
        severity_sum = 0.0
        temp_mask = neighbors_mask
        while temp_mask:
            bit = temp_mask & -temp_mask
            neighbor_idx = bit.bit_length() - 1
            severity_sum += severity_matrix[vertex_idx][neighbor_idx]
            temp_mask ^= bit
        return (neighbors_mask.bit_count(), severity_sum)

    @lru_cache(maxsize=None)
    def _pick_uncovered_edge(active_mask: int) -> tuple[int, int] | None:
        best_vertex = -1
        best_rank: tuple[int, float, int] | None = None
        for vertex_idx in _iter_bits(active_mask):
            degree_count, severity_sum = _vertex_remaining_score(active_mask, vertex_idx)
            if degree_count == 0:
                continue
            rank = (degree_count, severity_sum, -vertex_idx)
            if best_rank is None or rank > best_rank:
                best_rank = rank
                best_vertex = vertex_idx
        if best_vertex < 0:
            return None

        best_neighbor = -1
        best_neighbor_rank: tuple[int, float, int] | None = None
        for neighbor_idx in _iter_bits(adjacency_masks[best_vertex] & active_mask):
            degree_count, severity_sum = _vertex_remaining_score(active_mask, neighbor_idx)
            rank = (degree_count, severity_sum, -neighbor_idx)
            if best_neighbor_rank is None or rank > best_neighbor_rank:
                best_neighbor_rank = rank
                best_neighbor = neighbor_idx
        if best_neighbor < 0:
            return None
        return (best_vertex, best_neighbor)

    @lru_cache(maxsize=None)
    def _maximal_matching_lower_bound(active_mask: int) -> int:
        unmatched_mask = active_mask
        used_mask = 0
        matching_size = 0
        while unmatched_mask:
            bit = unmatched_mask & -unmatched_mask
            vertex_idx = bit.bit_length() - 1
            unmatched_mask ^= bit
            if used_mask & (1 << vertex_idx):
                continue
            neighbor_mask = adjacency_masks[vertex_idx] & active_mask & ~used_mask
            if neighbor_mask == 0:
                continue
            neighbor_bit = neighbor_mask & -neighbor_mask
            neighbor_idx = neighbor_bit.bit_length() - 1
            used_mask |= (1 << vertex_idx) | (1 << neighbor_idx)
            matching_size += 1
        return matching_size

    def _greedy_cover_mask(active_mask: int) -> int:
        selected_mask = 0
        working_mask = active_mask
        while True:
            uncovered_edge = _pick_uncovered_edge(working_mask)
            if uncovered_edge is None:
                return selected_mask

            best_vertex = -1
            best_rank: tuple[int, float, int] | None = None
            for vertex_idx in _iter_bits(working_mask):
                degree_count, severity_sum = _vertex_remaining_score(working_mask, vertex_idx)
                if degree_count == 0:
                    continue
                rank = (degree_count, severity_sum, -vertex_idx)
                if best_rank is None or rank > best_rank:
                    best_rank = rank
                    best_vertex = vertex_idx

            if best_vertex < 0:
                return selected_mask
            selected_mask |= 1 << best_vertex
            working_mask &= ~(1 << best_vertex)

    @lru_cache(maxsize=None)
    def _cover_rank(selected_mask: int) -> tuple[int, int, float, tuple[int, ...]]:
        selected_indices = tuple(_iter_bits(selected_mask))
        degree_sum = sum(incident_edge_counts[idx] for idx in selected_indices)
        severity_sum = sum(incident_severity_sums[idx] for idx in selected_indices)
        return (
            len(selected_indices),
            -degree_sum,
            -severity_sum,
            selected_indices,
        )

    @lru_cache(maxsize=None)
    def _can_cover(active_mask: int, remaining_budget: int) -> bool:
        if remaining_budget < 0:
            return False
        uncovered_edge = _pick_uncovered_edge(active_mask)
        if uncovered_edge is None:
            return True
        if _maximal_matching_lower_bound(active_mask) > remaining_budget:
            return False

        vertex_a, vertex_b = uncovered_edge
        return _can_cover(active_mask & ~(1 << vertex_a), remaining_budget - 1) or _can_cover(
            active_mask & ~(1 << vertex_b), remaining_budget - 1
        )

    @lru_cache(maxsize=None)
    def _best_cover(active_mask: int, remaining_budget: int) -> int | None:
        if remaining_budget < 0:
            return None
        uncovered_edge = _pick_uncovered_edge(active_mask)
        if uncovered_edge is None:
            return 0
        if _maximal_matching_lower_bound(active_mask) > remaining_budget:
            return None

        vertex_a, vertex_b = uncovered_edge
        branch_vertices = sorted(
            (vertex_a, vertex_b),
            key=lambda vertex_idx: (
                -_vertex_remaining_score(active_mask, vertex_idx)[0],
                -_vertex_remaining_score(active_mask, vertex_idx)[1],
                vertex_idx,
            ),
        )

        best_mask: int | None = None
        for vertex_idx in branch_vertices:
            next_mask = active_mask & ~(1 << vertex_idx)
            if not _can_cover(next_mask, remaining_budget - 1):
                continue
            submask = _best_cover(next_mask, remaining_budget - 1)
            if submask is None:
                continue
            candidate_mask = submask | (1 << vertex_idx)
            if best_mask is None or _cover_rank(candidate_mask) < _cover_rank(best_mask):
                best_mask = candidate_mask
        return best_mask

    greedy_mask = _greedy_cover_mask(full_mask)
    greedy_size = greedy_mask.bit_count()
    lower_bound = _maximal_matching_lower_bound(full_mask)
    optimum_size = greedy_size
    for candidate_size in range(lower_bound, greedy_size + 1):
        if _can_cover(full_mask, candidate_size):
            optimum_size = candidate_size
            break

    best_mask = _best_cover(full_mask, optimum_size)
    if best_mask is None:
        best_mask = greedy_mask

    return [vertex_keys[idx] for idx in _iter_bits(best_mask)]


def _normalize_metadata_tt_key(key: str) -> str:
    if "_tt_" not in key:
        return key

    suffix = ""
    for candidate in ("_count_rate_hz", "_count", "_fraction"):
        if key.endswith(candidate):
            suffix = candidate
            key = key[: -len(candidate)]
            break

    prefix, tt_fragment = key.rsplit("_tt_", 1)
    normalized_fragment = normalize_tt_label(tt_fragment, default="0")
    return f"{prefix}_tt_{normalized_fragment}{suffix}"


def _normalize_metadata_plane_key(key: str) -> str:
    """Canonicalize legacy plane-qualified metadata names as ``P<n>_*``."""
    patterns = (
        (r"^p([1-4])_s([1-4])_(.+)$", lambda m: f"P{m[1]}_s{m[2]}_{m[3]}"),
        (r"^eff([1-4])_(.+)$", lambda m: f"P{m[1]}_eff_{m[2]}"),
        (r"^eff([1-4])$", lambda m: f"P{m[1]}_eff"),
        (r"^z_P([1-4])$", lambda m: f"P{m[1]}_z"),
        (r"^streamer_P([1-4])$", lambda m: f"P{m[1]}_streamer"),
        (r"^active_strips_P([1-4])_(.+)$", lambda m: f"P{m[1]}_active_strips_{m[2]}"),
        (r"^charge_topology_plane_([1-4])_(.+)$", lambda m: f"P{m[1]}_charge_topology_{m[2]}"),
        (r"^streamer_rate_plane_filtered_([1-4])$", lambda m: f"P{m[1]}_streamer_rate_filtered"),
        (
            r"^raw_channel_swap_plane([1-4])_([1-4])_([1-4])_applied$",
            lambda m: f"P{m[1]}_raw_channel_swap_s{m[2]}_s{m[3]}_applied",
        ),
        (r"^tt_(.+)_outside_plane([1-4])_(.+)$", lambda m: f"P{m[2]}_tt_{m[1]}_outside_{m[3]}"),
        (r"^(.+)_P([1-4])$", lambda m: f"P{m[2]}_{m[1]}"),
    )
    for pattern, replacement in patterns:
        # Preserve pair-valued fields such as ``..._P1_to_P2``: the terminal
        # plane is part of a relationship, not a qualifier for the whole key.
        if pattern == r"^(.+)_P([1-4])$" and re.search(r"_P[1-4]_to_", key):
            continue
        match = re.match(pattern, key)
        if match:
            return replacement(match)
    return key


def _normalize_metadata_fieldnames(fieldnames: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    seen: set[str] = set()
    for raw_name in fieldnames:
        if raw_name is None:
            continue
        name = _normalize_metadata_plane_key(_normalize_metadata_tt_key(str(raw_name)))
        if name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    return normalized


def _is_entries_metric_key(key: str) -> bool:
    return key.endswith("_entries") or "_entries_" in key


RATE_HISTOGRAM_REQUIRED_COLUMNS = frozenset(
    {
        "count_rate_denominator_seconds",
        "events_per_second_total_seconds",
        "events_per_second_global_rate",
    }
)
EVENTS_PER_SECOND_RATE_HZ_RE = re.compile(r"^events_per_second_(\d+)_rate_hz$")


def is_rate_histogram_metadata_column(column_name: str) -> bool:
    if column_name in RATE_HISTOGRAM_REQUIRED_COLUMNS:
        return True
    match = EVENTS_PER_SECOND_RATE_HZ_RE.match(column_name)
    if match:
        return int(match.group(1)) <= EVENTS_PER_SECOND_MAX
    return False


def is_rate_histogram_file_column(column_name: str) -> bool:
    if column_name in TRACEABILITY_COLUMNS:
        return True
    return is_rate_histogram_metadata_column(column_name)


def is_chi2_four_plane_metadata_column(column_name: str) -> bool:
    if column_name == "count_rate_denominator_seconds":
        return True
    return column_name.startswith("chi2_four_plane_")


def is_chi2_four_plane_file_column(column_name: str) -> bool:
    if column_name in TRACEABILITY_COLUMNS:
        return True
    return is_chi2_four_plane_metadata_column(column_name)


def is_redundant_count_metadata_column(column_name: str) -> bool:
    if column_name == "count_rate_denominator_seconds":
        return False
    if column_name.endswith("_count"):
        return True
    if column_name.endswith("_fraction"):
        return True
    if _is_entries_metric_key(column_name) and not column_name.endswith("_rate_hz"):
        return True
    return False


def is_activation_metadata_column(column_name: str) -> bool:
    if column_name.startswith("activation_"):
        return True
    if column_name.startswith("streamer_contagion_"):
        return True
    if column_name.startswith("strip_activation_"):
        return True
    if column_name.startswith("streamer_rate_strip_"):
        return True
    if column_name.startswith("streamer_rate_plane_"):
        return True
    if column_name.startswith("streamer_threshold_selected"):
        return True
    if column_name.startswith("streamer_high_charge_threshold_selected"):
        return True
    if column_name == "streamer_high_charge_factor":
        return True
    return False


def is_specific_metadata_excluded_column(column_name: str) -> bool:
    if is_activation_metadata_column(column_name):
        return True
    return (
        is_redundant_count_metadata_column(column_name)
        or is_rate_histogram_metadata_column(column_name)
        or is_chi2_four_plane_metadata_column(column_name)
    )


def extract_rate_histogram_metadata(
    metadata: Dict[str, object],
    remove_from_source: bool = True,
) -> Dict[str, object]:
    extracted: Dict[str, object] = {}
    for key in TRACEABILITY_COLUMNS:
        if key in metadata:
            extracted[key] = metadata[key]

    for key in list(metadata.keys()):
        if not isinstance(key, str):
            continue
        if not is_rate_histogram_metadata_column(key):
            continue
        extracted[key] = metadata[key]
        if remove_from_source:
            metadata.pop(key, None)

    return extracted


def extract_chi2_four_plane_metadata(
    metadata: Dict[str, object],
    remove_from_source: bool = True,
) -> Dict[str, object]:
    extracted: Dict[str, object] = {}
    for key in TRACEABILITY_COLUMNS:
        if key in metadata:
            extracted[key] = metadata[key]

    for key in list(metadata.keys()):
        if not isinstance(key, str):
            continue
        if not is_chi2_four_plane_metadata_column(key):
            continue
        extracted[key] = metadata[key]
        if remove_from_source and key != "count_rate_denominator_seconds":
            metadata.pop(key, None)

    return extracted


def is_trigger_type_metadata_column(column_name: str, tt_prefixes: Iterable[str]) -> bool:
    for prefix in tt_prefixes:
        if column_name.startswith(f"{prefix}_"):
            return True
    return False


def is_trigger_type_file_column(column_name: str, tt_prefixes: Iterable[str]) -> bool:
    if column_name in TRACEABILITY_COLUMNS:
        return True
    if column_name == "count_rate_denominator_seconds":
        return True
    if is_trigger_type_metadata_column(column_name, tt_prefixes):
        if column_name.endswith("_rate_hz"):
            return True
        if "_total_offenders_le_" in column_name and column_name.endswith("_count"):
            return True
    return False


def extract_trigger_type_metadata(
    metadata: Dict[str, object],
    tt_prefixes: Iterable[str],
    remove_from_source: bool = True,
) -> Dict[str, object]:
    prefixes = tuple(str(prefix) for prefix in tt_prefixes)
    extracted: Dict[str, object] = {}

    for key in TRACEABILITY_COLUMNS:
        if key in metadata:
            extracted[key] = metadata[key]

    for key in list(metadata.keys()):
        if not isinstance(key, str):
            continue
        if not is_trigger_type_metadata_column(key, prefixes):
            continue
        extracted[key] = metadata[key]
        if remove_from_source:
            metadata.pop(key, None)

    return extracted


def _total_problematic_offender_series(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(0, index=df.index, dtype=int)

    if "total_problematic_offender_count" in df.columns:
        return (
            pd.to_numeric(df["total_problematic_offender_count"], errors="coerce")
            .fillna(0)
            .clip(lower=0)
            .astype(int)
        )

    total = pd.Series(0, index=df.index, dtype=int)
    for column_name in UPSTREAM_OFFENDER_COUNT_COLUMNS:
        if column_name not in df.columns:
            continue
        total = total.add(
            pd.to_numeric(df[column_name], errors="coerce").fillna(0).clip(lower=0).astype(int),
            fill_value=0,
        )
    return total.astype(int)


def add_trigger_type_total_offender_threshold_metadata(
    metadata: Dict[str, object],
    df: pd.DataFrame,
    stage_tt_columns: Sequence[str],
    denominator_seconds: float | int | None,
    thresholds: Sequence[int] = DEFAULT_TRIGGER_TYPE_OFFENDER_THRESHOLDS,
) -> None:
    if df is None:
        return

    stage_columns = tuple(
        _normalize_tt_prefix(column_name)
        for column_name in stage_tt_columns
        if _normalize_tt_prefix(column_name) in df.columns
    )
    if not stage_columns:
        return

    try:
        denominator_value = float(denominator_seconds)
    except (TypeError, ValueError):
        denominator_value = 0.0
    if not np.isfinite(denominator_value) or denominator_value <= 0:
        denominator_value = 0.0

    total_problematic_offender_count = _total_problematic_offender_series(df)
    normalized_thresholds = tuple(sorted({max(0, int(threshold)) for threshold in thresholds}))

    normalized_tt_by_stage: dict[str, pd.Series] = {}
    for stage_column in stage_columns:
        normalized_tt_by_stage[stage_column] = pd.Series(
            (
                normalize_tt_label(value, default="0")
                for value in df[stage_column].to_numpy(copy=False)
            ),
            index=df.index,
            dtype="object",
        )

    for threshold in normalized_thresholds:
        threshold_mask = total_problematic_offender_count <= threshold
        for stage_column, tt_labels in normalized_tt_by_stage.items():
            threshold_tt = tt_labels.loc[threshold_mask]
            tt_counts = threshold_tt.value_counts()
            for tt_label in CANONICAL_TT_LABEL_SEQUENCE:
                count_value = int(tt_counts.get(tt_label, 0))
                count_key = f"{stage_column}_total_offenders_le_{threshold}_{tt_label}_count"
                rate_key = f"{stage_column}_total_offenders_le_{threshold}_{tt_label}_rate_hz"
                metadata[count_key] = count_value
                metadata[rate_key] = (
                    round(float(count_value) / denominator_value, 6)
                    if denominator_value > 0
                    else ""
                )


def prune_redundant_count_metadata(
    metadata: Dict[str, object],
    log_fn: Callable[..., None] = builtins.print,
) -> int:
    dropped: list[str] = []
    for key in list(metadata.keys()):
        if not isinstance(key, str):
            continue
        if key == "count_rate_denominator_seconds":
            continue

        if key.endswith("_count"):
            rate_key = key[: -len("_count")] + "_rate_hz"
            if rate_key in metadata:
                dropped.append(key)
            continue

        if _is_entries_metric_key(key) and not key.endswith("_rate_hz"):
            rate_key = f"{key}_rate_hz"
            if rate_key in metadata:
                dropped.append(key)
            continue

        if key.endswith("_fraction"):
            dropped.append(key)

    for key in dropped:
        metadata.pop(key, None)

    if dropped:
        log_fn(f"[metadata] Dropped {len(dropped)} redundant count/fraction column(s).")
    return len(dropped)


def build_step1_cli_parser(
    description: str,
    station_choices: Sequence[str] = DEFAULT_STATION_CHOICES,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "station",
        nargs="?",
        choices=tuple(station_choices),
        help="Station identifier (0, 1, 2, 3, or 4).",
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        help="Optional input file path to process instead of auto-selecting.",
    )
    parser.add_argument(
        "--input-file",
        dest="input_file_flag",
        help="Optional input file path (named form).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose execution logging.",
    )
    return parser


def validate_step1_input_file_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.input_file and args.input_file_flag:
        parser.error("Use either positional input_file or --input-file, not both.")


ZERO_TOKEN_PATTERN = re.compile(r"0000\.0000")
LEADING_ZERO_PATTERN = re.compile(r"\b0+([0-9]+)")
MULTI_SPACE_PATTERN = re.compile(r" +")
XYEAR_PATTERN = re.compile(r"X(20\d{2})")
NEG_GAP_PATTERN = re.compile(r"(\w)-(\d)")
MALFORMED_NUMBER_PATTERN = re.compile(r"-?\d+\.\d+\.\d+")
VALID_YEARS = set(range(1999, 2201))


def process_step1_raw_line(line: str) -> str:
    line = ZERO_TOKEN_PATTERN.sub("0", line)
    line = LEADING_ZERO_PATTERN.sub(r"\1", line)
    line = MULTI_SPACE_PATTERN.sub(",", line.strip())
    line = XYEAR_PATTERN.sub(r"X\n\1", line)
    line = NEG_GAP_PATTERN.sub(r"\1 -\2", line)
    return line


def step1_raw_line_contains_malformed_numbers(line: str) -> bool:
    return bool(MALFORMED_NUMBER_PATTERN.search(line))


def step1_raw_values_have_valid_date(values: Sequence[object]) -> bool:
    try:
        year, month, day = int(values[0]), int(values[1]), int(values[2])
        return year in VALID_YEARS and 1 <= month <= 12 and 1 <= day <= 31
    except (IndexError, TypeError, ValueError):
        return False


def _normalize_step1_raw_line_for_numpy(line: str) -> str:
    normalized = line.strip()
    normalized = ZERO_TOKEN_PATTERN.sub("0", normalized)
    normalized = LEADING_ZERO_PATTERN.sub(r"\1", normalized)
    if "X20" in normalized:
        normalized = XYEAR_PATTERN.sub(r"X \1", normalized)
    if "-" in normalized:
        normalized = NEG_GAP_PATTERN.sub(r"\1 -\2", normalized)
    return normalized


def _parse_step1_raw_line_fast(line: str, expected_columns: int) -> np.ndarray | None:
    stripped = line.strip()
    try:
        values = np.fromstring(stripped, sep=" ", dtype=np.float64)
    except ValueError:
        values = None
    if values is not None and values.size == expected_columns and step1_raw_values_have_valid_date(values[:3]):
        return values
    normalized = _normalize_step1_raw_line_for_numpy(stripped)
    try:
        values = np.fromstring(normalized, sep=" ", dtype=np.float64)
    except ValueError:
        return None
    if values.size == expected_columns and step1_raw_values_have_valid_date(values[:3]):
        return values
    return None


def build_step1_raw_input_dataframe(
    source_path: str | Path,
    rejected_path: str | Path,
    expected_columns: int,
    limit_rows: int | None = None,
) -> tuple[pd.DataFrame, int, int]:
    """Parse a Stage 1 acquisition text file into the raw Task 1 dataframe shape."""
    read_lines = 0
    written_lines = 0
    stored_rows = 0
    flat_values = array("d")
    event_ids: list[int] = []

    with Path(source_path).open("r", encoding="utf-8", errors="replace") as infile, Path(
        rejected_path
    ).open("w", encoding="utf-8") as rejectfile:
        for i, line in enumerate(infile, start=1):
            if line.lstrip().startswith("#"):
                continue
            read_lines += 1

            parsed_values = _parse_step1_raw_line_fast(line, expected_columns)
            if parsed_values is None:
                cleaned_line = process_step1_raw_line(line)
                cleaned_values = cleaned_line.split(",")

                if len(cleaned_values) < 3 or not step1_raw_values_have_valid_date(cleaned_values[:3]):
                    rejectfile.write(f"Line {i} (Invalid date): {line.strip()}\n")
                    continue

                if step1_raw_line_contains_malformed_numbers(line):
                    rejectfile.write(f"Line {i} (Malformed number): {line.strip()}\n")
                    continue

                if len(cleaned_values) != expected_columns:
                    rejectfile.write(f"Line {i} (Wrong column count): {line.strip()}\n")
                    continue

                try:
                    parsed_values = np.fromstring(
                        cleaned_line.replace(",", " "),
                        sep=" ",
                        dtype=np.float64,
                    )
                except ValueError:
                    rejectfile.write(f"Line {i} (Malformed numeric data): {line.strip()}\n")
                    continue
                if parsed_values.size != expected_columns:
                    rejectfile.write(f"Line {i} (Wrong column count): {line.strip()}\n")
                    continue

            written_lines += 1
            if limit_rows is None or stored_rows < limit_rows:
                flat_values.extend(parsed_values)
                event_ids.append(i)
                stored_rows += 1

    if stored_rows == 0:
        return pd.DataFrame(), read_lines, written_lines

    raw_matrix = np.frombuffer(flat_values, dtype=np.float64).reshape(stored_rows, expected_columns)
    datetime_components = {
        "year": np.rint(raw_matrix[:, 0]).astype(np.int16, copy=False),
        "month": np.rint(raw_matrix[:, 1]).astype(np.int8, copy=False),
        "day": np.rint(raw_matrix[:, 2]).astype(np.int8, copy=False),
        "hour": np.rint(raw_matrix[:, 3]).astype(np.int8, copy=False),
        "minute": np.rint(raw_matrix[:, 4]).astype(np.int8, copy=False),
        "second": np.rint(raw_matrix[:, 5]).astype(np.int8, copy=False),
    }
    datetime_series = pd.to_datetime(datetime_components)

    value_columns = [f"column_{i}" for i in range(6, expected_columns)]
    value_data = raw_matrix[:, 6:].astype(np.float32, copy=False)
    read_df = pd.DataFrame(value_data, columns=value_columns, copy=False)
    read_df.insert(0, "event_id", np.asarray(event_ids, dtype=np.int64))
    read_df.insert(0, "datetime", datetime_series)
    read_df["column_6"] = np.rint(raw_matrix[:, 6]).astype(np.int8, copy=False)
    return read_df, read_lines, written_lines


def build_step1_filtered_print(
    verbose: bool,
    debug_mode_getter: Callable[[], bool],
    raw_print: Callable[..., None] = builtins.print,
    important_keywords: Sequence[str] = DEFAULT_IMPORTANT_KEYWORDS,
) -> Callable[..., None]:
    important = tuple(keyword.lower() for keyword in important_keywords)

    def is_important_message(message: str) -> bool:
        lowered = message.lower()
        if any(keyword in lowered for keyword in important):
            return True
        return "total execution time" in lowered or "data purity" in lowered

    def filtered_print(*args, **kwargs):
        force = kwargs.pop("force", False)
        if force or debug_mode_getter() or verbose:
            raw_print(*args, **kwargs)
            return
        message = " ".join(str(arg) for arg in args)
        if is_important_message(message):
            raw_print(*args, **kwargs)

    return filtered_print


def resolve_step1_station(
    cli_station: str | None,
    run_jupyter_notebook: bool,
    default_station: str,
    parser: argparse.ArgumentParser,
    station_choices: Sequence[str] = DEFAULT_STATION_CHOICES,
    config_hint: str = "TASK_<N>/config_task_<N>.yaml",
) -> str:
    if cli_station is not None:
        station = str(cli_station)
    elif run_jupyter_notebook:
        station = str(default_station)
    else:
        parser.error(
            f"No station provided. Pass <station> or enable run_jupyter_notebook in {config_hint}."
        )

    if station not in station_choices:
        parser.error("Invalid station. Choose one of: 0, 1, 2, 3, 4.")
    return station


def apply_step1_task_parameter_overrides(
    config_obj: dict,
    station_id: str,
    task_parameter_path: str | Path,
    fallback_parameter_path: str | Path,
    task_number: int,
    log_fn: Callable[..., None] = builtins.print,
    exclude_keys: Iterable[str] | None = None,
) -> dict:
    excluded = {str(key) for key in (exclude_keys or ()) if str(key)}

    def _apply_parameter_file(config_dict: dict, csv_path: Path) -> dict:
        overrides = load_parameter_overrides(csv_path, station_id)
        if excluded:
            overrides = {
                key: value for key, value in overrides.items() if key not in excluded
            }
        if overrides:
            config_dict.update(overrides)
        return config_dict

    task_path = Path(task_parameter_path)
    if task_path.exists():
        config_obj = _apply_parameter_file(config_obj, task_path)
        log_fn(f"Info: Loaded task parameters from {task_path}")
        return config_obj

    fallback_path = Path(fallback_parameter_path)
    if fallback_path.exists():
        log_fn(f"Warning: Task parameters file not found; falling back to {fallback_path}")
        config_obj = _apply_parameter_file(config_obj, fallback_path)
    else:
        log_fn(f"Warning: No parameters file found for task {task_number}")
    return config_obj


def apply_step1_optional_parameter_overrides(
    config_obj: dict,
    station_id: str,
    parameter_path: str | Path,
    *,
    label: str,
    log_fn: Callable[..., None] = builtins.print,
) -> dict:
    path = Path(parameter_path)
    if not path.exists():
        return config_obj

    overrides = load_parameter_overrides(path, station_id)
    if not overrides:
        return config_obj

    config_obj.update(overrides)
    log_fn(f"Info: Loaded {label} parameters from {path}")
    return config_obj


def load_step1_filter_parameter_state(
    filter_parameter_path: str | Path,
    station_id: str,
    *,
    enabled: bool = True,
    warn_if_missing: bool = False,
    log_fn: Callable[..., None] = builtins.print,
) -> tuple[set[str], dict[str, object], bool]:
    path = Path(filter_parameter_path)
    if not enabled:
        log_fn("Info: Skipping filter parameter config (use_filter_parameter_config=false).")
        return set(), {}, False

    if not path.exists():
        if warn_if_missing:
            log_fn(f"Warning: Requested filter parameter config not found: {path}")
        return set(), {}, False

    declared_keys = load_declared_parameter_names(path)
    overrides = load_parameter_overrides(path, station_id)
    return declared_keys, overrides, True


def build_step1_task_config_paths(
    task_number: int,
    *,
    master_config_root: str | Path | None = None,
) -> dict[str, Path]:
    root = (
        Path(master_config_root).expanduser()
        if master_config_root is not None
        else get_master_config_root()
    )
    step1_root = root / "STAGE_1" / "EVENT_DATA" / "STEP_1"
    task_root = step1_root / f"TASK_{task_number}"
    plot_catalog_path = task_root / f"config_plots_task_{task_number}.yaml"
    if not plot_catalog_path.is_file():
        plot_catalog_path = step1_root / "config_plots_task_default.yaml"
    return {
        "config_root": root,
        "step1_root": step1_root,
        "task_root": task_root,
        "config_file_path": task_root / f"config_task_{task_number}.yaml",
        "plot_catalog_file_path": plot_catalog_path,
        "parameter_config_file_path": task_root / f"config_parameters_task_{task_number}.csv",
        "plot_parameter_config_file_path": task_root / f"config_plot_parameters_task_{task_number}.csv",
        "filter_parameter_config_file_path": task_root / f"config_filter_parameters_task_{task_number}.csv",
        "fallback_parameter_config_file_path": step1_root / "config_parameters.csv",
    }


def load_step1_task_config_bundle(
    task_number: int,
    *,
    master_config_root: str | Path | None = None,
    include_filter_parameter_config: bool = True,
    log_fn: Callable[..., None] = builtins.print,
) -> dict[str, object]:
    task_config_paths = build_step1_task_config_paths(
        task_number,
        master_config_root=master_config_root,
    )
    config_file_path = Path(task_config_paths["config_file_path"])
    plot_catalog_file_path = Path(task_config_paths["plot_catalog_file_path"])
    plot_parameter_config_file_path = Path(task_config_paths["plot_parameter_config_file_path"])
    filter_parameter_config_file_path = Path(task_config_paths["filter_parameter_config_file_path"])

    log_fn(f"Using config file: {config_file_path}")
    log_fn(f"Using plot catalog file: {plot_catalog_file_path}")
    with config_file_path.open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file) or {}

    plot_parameter_config_file_path = plot_parameter_config_file_path.with_name(
        str(config.get("plot_parameter_config_csv", plot_parameter_config_file_path.name))
    )
    log_fn(f"Using plot parameter config file: {plot_parameter_config_file_path}")

    if include_filter_parameter_config:
        filter_parameter_config_file_path = filter_parameter_config_file_path.with_name(
            str(config.get("filter_parameter_config_csv", filter_parameter_config_file_path.name))
        )
        log_fn(f"Using filter parameter config file: {filter_parameter_config_file_path}")

    return {
        **task_config_paths,
        "config": config,
        "plot_parameter_config_file_path": plot_parameter_config_file_path,
        "filter_parameter_config_file_path": filter_parameter_config_file_path,
    }


def resolve_step1_effective_task_config(
    config_obj: Mapping[str, object],
    *,
    station_id: str,
    task_number: int,
    config_root: str | Path,
    parameter_config_file_path: str | Path,
    fallback_parameter_config_file_path: str | Path,
    plot_parameter_config_file_path: str | Path | None = None,
    filter_parameter_config_file_path: str | Path | None = None,
    use_filter_parameter_config: bool = True,
    warn_if_missing_filter: bool = False,
    log_fn: Callable[..., None] = builtins.print,
) -> dict:
    config = dict(config_obj)
    filter_parameter_declared_keys: set[str] = set()
    filter_parameter_overrides: dict[str, object] = {}
    filter_parameter_config_loaded = False

    if filter_parameter_config_file_path is not None:
        (
            filter_parameter_declared_keys,
            filter_parameter_overrides,
            filter_parameter_config_loaded,
        ) = load_step1_filter_parameter_state(
            filter_parameter_config_file_path,
            station_id,
            enabled=use_filter_parameter_config,
            warn_if_missing=warn_if_missing_filter,
            log_fn=log_fn,
        )

    config = apply_step1_task_parameter_overrides(
        config_obj=config,
        station_id=station_id,
        task_parameter_path=parameter_config_file_path,
        fallback_parameter_path=fallback_parameter_config_file_path,
        task_number=task_number,
        log_fn=log_fn,
        exclude_keys=filter_parameter_declared_keys,
    )
    if filter_parameter_config_loaded:
        config.update(filter_parameter_overrides)
        log_fn(f"Info: Loaded filter parameters from {Path(filter_parameter_config_file_path)}")
    if plot_parameter_config_file_path is not None:
        config = apply_step1_optional_parameter_overrides(
            config_obj=config,
            station_id=station_id,
            parameter_path=plot_parameter_config_file_path,
            label="plot",
            log_fn=log_fn,
        )
    return config


def coerce_positive_int_config(value: object, default: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 1 else default


def coerce_nonnegative_float_config(value: object, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def select_joined_analysis_file_names(
    selected_file_name: str,
    candidate_file_names: Iterable[str],
    *,
    station_id: str | int,
    max_files: int,
    tolerance_hours: float,
    selection_order: str = "latest",
    log_fn: Callable[..., None] | None = None,
) -> list[str]:
    """Return selected file plus nearby timestamp-compatible candidates.

    ``tolerance_hours`` is a window constraint relative to the selected file:
    for normal latest-first processing, extra files must be older than the
    selected file and no farther away than the configured tolerance; for
    oldest/FIFO processing, extra files must be newer and within the same
    tolerance. This keeps every joined file inside the configured time window.
    """
    if max_files <= 1:
        return [selected_file_name]
    selected_datetime = extract_run_datetime_from_name(selected_file_name)
    if selected_datetime is None:
        if log_fn is not None:
            log_fn(
                "Joined analysis disabled for this selection: could not parse "
                f"timestamp from {selected_file_name}."
            )
        return [selected_file_name]

    try:
        station_int = int(str(station_id))
    except (TypeError, ValueError):
        station_int = None
    tolerance = pd.Timedelta(hours=float(tolerance_hours))
    prefer_older = str(selection_order).strip().lower() not in {"oldest", "fifo", "first"}
    candidate_rows: list[tuple[pd.Timedelta, str]] = []
    for candidate_name in candidate_file_names:
        if candidate_name == selected_file_name:
            continue
        if station_int is not None and infer_station_number_from_processing_name(candidate_name) != station_int:
            continue
        candidate_datetime = extract_run_datetime_from_name(candidate_name)
        if candidate_datetime is None:
            continue
        delta = pd.Timestamp(selected_datetime) - pd.Timestamp(candidate_datetime)
        if prefer_older:
            if delta < pd.Timedelta(0) or delta > tolerance:
                continue
        else:
            if delta > pd.Timedelta(0) or abs(delta) > tolerance:
                continue
        candidate_rows.append((abs(delta), candidate_name))

    candidate_rows.sort(key=lambda item: item[0])
    selected_names = [selected_file_name, *[name for _delta, name in candidate_rows[: max_files - 1]]]
    selected_names.sort(key=lambda name: extract_run_datetime_from_name(name) or datetime.min)
    if log_fn is not None:
        log_fn(
            "Joined analysis file selection: "
            f"requested={max_files} selected={len(selected_names)} "
            f"tolerance_hours={float(tolerance_hours):g} files={selected_names}"
        )
    return selected_names


def replicate_joined_metadata_rows(
    metadata_paths: Iterable[str | Path],
    *,
    primary_filename_base: str,
    joined_input_records: Iterable[Mapping[str, object]],
    log_fn: Callable[..., None] | None = None,
) -> None:
    """Copy metadata rows from the primary joined file to each joined input.

    Joined analysis intentionally processes a bunch as one dataframe, so most
    scalar diagnostics are bunch-level values. The output files are still
    one-per-input; this helper preserves that same one-row-per-input shape in
    each metadata CSV by cloning the primary row and changing only
    ``filename_base``.
    """
    records = list(joined_input_records)
    if len(records) <= 1:
        return
    primary_base = str(primary_filename_base or "").strip()
    target_bases = []
    for record in records:
        basename = str(record.get("basename_no_ext", "") or "").strip()
        if basename and basename != primary_base and basename not in target_bases:
            target_bases.append(basename)
    if not primary_base or not target_bases:
        return

    for metadata_path in metadata_paths:
        path = Path(metadata_path)
        if not path.exists() or path.stat().st_size == 0:
            continue
        try:
            metadata_df = pd.read_csv(path, low_memory=False)
        except Exception as exc:
            if log_fn is not None:
                log_fn(f"Warning: unable to replicate joined metadata in {path}: {exc}")
            continue
        if "filename_base" not in metadata_df.columns:
            continue
        source_rows = metadata_df[
            metadata_df["filename_base"].astype(str).str.strip().eq(primary_base)
        ].copy()
        if source_rows.empty:
            continue

        timestamp_columns = [
            column_name
            for column_name in ("execution_timestamp", "execution_date")
            if column_name in metadata_df.columns and column_name in source_rows.columns
        ]
        rows_to_append: list[pd.DataFrame] = []
        for target_base in target_bases:
            target_rows = source_rows.copy()
            target_rows.loc[:, "filename_base"] = target_base
            for _, source_row in source_rows.iterrows():
                duplicate_mask = metadata_df["filename_base"].astype(str).str.strip().eq(target_base)
                for column_name in timestamp_columns:
                    duplicate_mask &= metadata_df[column_name].astype(str).eq(str(source_row[column_name]))
                metadata_df = metadata_df.loc[~duplicate_mask].copy()
            rows_to_append.append(target_rows)

        if rows_to_append:
            metadata_df = pd.concat([metadata_df, *rows_to_append], ignore_index=True, sort=False)
            metadata_df.to_csv(path, index=False)
            if log_fn is not None:
                log_fn(
                    "Replicated joined metadata rows: "
                    f"{path} primary={primary_base} targets={target_bases}"
                )


def _normalize_bool_setting(value: object, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)

    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    return default


@lru_cache(maxsize=None)
def load_step1_metadata_output_overrides(
    master_config_root: str | Path | None = None,
) -> tuple[Path, Dict[str, bool]]:
    root = (
        Path(master_config_root).expanduser()
        if master_config_root is not None
        else get_master_config_root()
    )
    config_path = root / STEP1_MASTER_CONFIG_RELATIVE_PATH
    loaded = load_yaml_mapping(config_path)

    output_node = loaded.get("metadata_outputs")
    if not isinstance(output_node, Mapping):
        output_node = loaded.get("step_1_metadata_outputs")
    if not isinstance(output_node, Mapping):
        output_node = {}

    resolved = dict(STEP1_METADATA_OUTPUT_DEFAULTS)
    for metadata_type in STEP1_METADATA_OUTPUT_TYPES:
        if metadata_type in output_node:
            resolved[metadata_type] = _normalize_bool_setting(output_node.get(metadata_type), True)
        else:
            legacy_key = f"write_metadata_{metadata_type}"
            if legacy_key in loaded:
                resolved[metadata_type] = _normalize_bool_setting(loaded.get(legacy_key), True)

    return config_path, resolved


@lru_cache(maxsize=None)
def load_step1_logging_output_overrides(
    master_config_root: str | Path | None = None,
) -> tuple[Path, Dict[str, bool]]:
    root = (
        Path(master_config_root).expanduser()
        if master_config_root is not None
        else get_master_config_root()
    )
    config_path = root / STEP1_MASTER_CONFIG_RELATIVE_PATH
    loaded = load_yaml_mapping(config_path)

    output_node = loaded.get("logging_outputs")
    if not isinstance(output_node, Mapping):
        output_node = loaded.get("step_1_logging_outputs")
    if not isinstance(output_node, Mapping):
        output_node = {}

    resolved = dict(STEP1_LOG_OUTPUT_DEFAULTS)
    for logging_type in STEP1_LOG_OUTPUT_TYPES:
        if logging_type in output_node:
            resolved[logging_type] = _normalize_bool_setting(output_node.get(logging_type), True)

    return config_path, resolved


def step1_logging_enabled(
    logging_type: str,
    *,
    master_config_root: str | Path | None = None,
) -> tuple[bool, Path]:
    config_path, resolved = load_step1_logging_output_overrides(
        master_config_root=master_config_root,
    )
    return resolved.get(logging_type, True), config_path


def infer_step1_metadata_type(metadata_path: str | Path) -> str | None:
    path = Path(metadata_path)
    path_text = path.as_posix()
    if "/STAGE_1/EVENT_DATA/STEP_1/" not in path_text or "/METADATA/" not in path_text:
        return None
    match = re.fullmatch(r"task_\d+_metadata_([a-z_]+)\.csv", path.name)
    if not match:
        return None
    metadata_type = match.group(1)
    if metadata_type not in STEP1_METADATA_OUTPUT_DEFAULTS:
        return None
    return metadata_type


def should_write_step1_metadata(
    metadata_path: str | Path,
    *,
    master_config_root: str | Path | None = None,
) -> tuple[bool, str | None, Path]:
    metadata_type = infer_step1_metadata_type(metadata_path)
    config_path, resolved = load_step1_metadata_output_overrides(
        master_config_root=master_config_root,
    )
    if metadata_type is None:
        return True, None, config_path
    return resolved.get(metadata_type, True), metadata_type, config_path


def normalize_analysis_mode_value(value: object) -> str:
    """Normalise analysis_mode to a non-negative integer string.

    analysis_mode is a prime-product composite that encodes per-calibration
    modes (charge_side × charge_front_back × time_calibration ×
    time_dif_calibration).  Any positive integer is valid; empty string is
    used when the value is absent.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if text == "":
        return ""
    # Strip trailing .0 produced by float-to-string conversion
    if text.endswith(".0"):
        text = text[:-2]
    # Accept any non-negative integer string
    if text.lstrip("-").isdigit() and not text.startswith("-"):
        return text
    return ""


def _normalize_plot_mode(raw_value: object) -> str:
    if raw_value is None:
        return "none"
    if isinstance(raw_value, bool):
        return "all" if raw_value else "none"

    mode = str(raw_value).strip().lower()
    if mode in {"", "none", "null", "false", "0", "off"}:
        return "none"
    if mode in {"debug"}:
        return "debug"
    if mode in {"usual", "standard", "normal"}:
        return "usual"
    if mode in {"essential"}:
        return "essential"
    if mode in {"all", "true", "1", "on"}:
        return "all"

    raise ValueError(
        "Invalid create_plots value. Use one of: null/none, debug, usual, essential, all."
    )


def resolve_step1_plot_options(
    config_obj: Dict[str, object],
) -> Tuple[str, bool, bool, bool, bool, bool, bool]:
    """Return normalized plotting mode and derived plotting toggles.

    Output tuple:
    (plot_mode, create_plots, create_essential_plots, save_plots,
     create_pdf, show_plots, create_debug_plots)
    """
    station_id = config_obj.get("_plot_station_id")
    task_number = config_obj.get("_plot_task_number")
    if station_id is not None and task_number is not None:
        apply_step1_periodic_plot_gate(
            config_obj, station_id=str(station_id), task_number=int(task_number)
        )
    plot_mode = _normalize_plot_mode(config_obj.get("create_plots", None))
    create_plots = plot_mode in {"usual", "all"}
    create_debug_plots = plot_mode in {"debug", "all"}
    create_essential_plots = plot_mode in {"usual", "essential", "all"}
    save_plots = plot_mode != "none"
    create_pdf = False  # Runtime STEP_1 plots are strictly PNG-only.
    show_plots = False
    return (
        plot_mode,
        create_plots,
        create_essential_plots,
        save_plots,
        create_pdf,
        show_plots,
        create_debug_plots,
    )


def apply_step1_periodic_plot_gate(
    config_obj: dict,
    *,
    station_id: str,
    task_number: int,
    log_fn: Callable[..., None] = builtins.print,
) -> bool:
    """Enable configured plots once per station/task interval.

    A positive periodic_plotting_interval_hours uses the alias catalog through
    the normal ``usual`` plot mode when create_plots is unset/none. Each due
    interval is coordinated across concurrent task processes with flock.
    """
    if config_obj.get("_periodic_plot_gate_applied"):
        return bool(config_obj.get("_periodic_plot_due", False))
    raw_interval = config_obj.get("periodic_plotting_interval_hours")
    if raw_interval in (None, "", False):
        return False
    try:
        interval_hours = float(raw_interval)
    except (TypeError, ValueError) as exc:
        raise ValueError("periodic_plotting_interval_hours must be a positive number or null") from exc
    if not math.isfinite(interval_hours) or interval_hours <= 0:
        raise ValueError("periodic_plotting_interval_hours must be a positive number or null")

    explicit_mode = _normalize_plot_mode(config_obj.get("create_plots"))
    if explicit_mode != "none":
        # Existing explicit plotting mode continues to control the selected plots;
        # the interval only limits how often that mode is run.
        pass
    else:
        explicit_mode = "usual"

    repo_root = get_repo_root()
    schedule_dir = repo_root / "CONTEXTUAL" / "OPERATIONS" / "OPERATIONS_RUNTIME" / "PLOT_SCHEDULE"
    schedule_dir.mkdir(parents=True, exist_ok=True)
    schedule_file = schedule_dir / f"stage1_station_{station_id}_task_{task_number}.timestamp"
    interval_seconds = interval_hours * 3600.0
    now = datetime.now().timestamp()
    with schedule_file.with_suffix(".lock").open("a+") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            try:
                last = float(schedule_file.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                last = 0.0
            due = now - last >= interval_seconds
            if due:
                schedule_file.write_text(f"{now:.6f}\n", encoding="utf-8")
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    if due:
        config_obj["create_plots"] = explicit_mode
        log_fn(
            f"Periodic plotting enabled for station {station_id} task {task_number} "
            f"(interval={interval_hours:g} h, mode={explicit_mode})."
        )
    else:
        config_obj["create_plots"] = "none"
    config_obj["_periodic_plot_gate_applied"] = True
    config_obj["_periodic_plot_due"] = due
    return due


STEP1_PLOT_STATUSES: Tuple[str, ...] = ("none", "debug", "usual", "essential")


def _normalize_step1_plot_catalog_status(raw_status: object) -> str:
    if raw_status is None:
        return "none"
    if isinstance(raw_status, bool):
        return "usual" if raw_status else "none"

    status = str(raw_status).strip().lower()
    if status in {"", "none", "null", "false", "0", "off"}:
        return "none"
    if status in {"true", "1", "on"}:
        return "usual"
    if status in {"debug", "usual", "essential"}:
        return status
    return status


def load_step1_task_plot_catalog(
    catalog_path: Path,
    plot_aliases: Sequence[str],
    task_label: str,
    log_fn: Callable[..., None] = builtins.print,
) -> Dict[str, str]:
    """Load and validate a STEP_1 task plot catalog YAML.

    Expected YAML shape is either the legacy ``plots`` mapping or explicit
    ``-plot`` / ``-not_plot`` alias lists.
    """
    if not catalog_path.exists():
        raise FileNotFoundError(f"{task_label} plot catalog not found: {catalog_path}")

    import yaml

    with catalog_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}

    if not isinstance(loaded, Mapping):
        raise ValueError(f"{task_label} plot catalog must be a mapping: {catalog_path}")

    if "-plot" in loaded or "-not_plot" in loaded:
        plotted = loaded.get("-plot", []) or []
        not_plotted = loaded.get("-not_plot", []) or []
        if not isinstance(plotted, list) or not isinstance(not_plotted, list):
            raise ValueError(f"'-plot' and '-not_plot' in {catalog_path} must be YAML lists.")
        plotted = [str(alias) for alias in plotted]
        not_plotted = [str(alias) for alias in not_plotted]
        overlap = sorted(set(plotted) & set(not_plotted))
        if overlap:
            raise ValueError(f"Aliases cannot appear in both '-plot' and '-not_plot': {overlap}")
        known = set(plot_aliases)
        unknown = sorted((set(plotted) | set(not_plotted)) - known)
        if unknown:
            log_fn(f"{task_label} plot catalog contains unknown aliases; ignoring: {unknown}")
        enabled = set(plotted) & known
        return {alias: ("usual" if alias in enabled else "none") for alias in plot_aliases}

    raw_plots = loaded.get("plots", {})
    if not isinstance(raw_plots, Mapping):
        raise ValueError(f"'plots' entry in {catalog_path} must be a mapping.")

    aliases_set = set(plot_aliases)
    catalog: Dict[str, str] = {}
    for alias, raw_status in raw_plots.items():
        alias_name = str(alias)
        status = _normalize_step1_plot_catalog_status(raw_status)
        if status not in STEP1_PLOT_STATUSES:
            raise ValueError(
                f"Invalid status {raw_status!r} for {task_label} plot alias {alias_name!r} in {catalog_path}."
            )
        if alias_name not in aliases_set:
            log_fn(
                f"{task_label} plot catalog entry {alias_name!r} is unknown and will be ignored.",
            )
            continue
        catalog[alias_name] = status

    for alias in plot_aliases:
        if alias not in catalog:
            # A known task alias absent from the runtime catalog is intentionally
            # not a runtime plot (it may live in config_final_plots_task_N.yaml).
            catalog[alias] = "none"

    return catalog


def step1_task_plot_enabled(
    alias: str,
    status_by_alias: Mapping[str, str],
    plot_mode: str,
) -> bool:
    """Return whether a task plot alias is enabled for the current mode."""
    if alias not in status_by_alias:
        raise KeyError(f"Unknown STEP_1 task plot alias: {alias}")

    status = status_by_alias[alias]

    if plot_mode == "none":
        return False
    if status == "none":
        return False
    if plot_mode == "all":
        return True
    if plot_mode == "debug":
        return status == "debug"
    if plot_mode == "usual":
        return status in {"usual", "essential"}
    if plot_mode == "essential":
        return status == "essential"
    return False


def sanitize_analysis_mode_rows(rows: List[Dict[str, object]]) -> int:
    fixed = 0
    for row in rows:
        if "analysis_mode" not in row:
            continue
        clean_value = normalize_analysis_mode_value(row.get("analysis_mode"))
        if row.get("analysis_mode") != clean_value:
            row["analysis_mode"] = clean_value
            fixed += 1
    return fixed


def repair_metadata_file(metadata_path: Path) -> int:
    original_limit = csv.field_size_limit()
    csv.field_size_limit(2**31 - 1)
    try:
        with metadata_path.open("r", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            rows = [dict(existing) for existing in reader]
    finally:
        csv.field_size_limit(original_limit)

    if not fieldnames:
        return 0

    fixed = sanitize_analysis_mode_rows(rows)
    if fixed:
        with metadata_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    return fixed


def _normalize_metadata_row(raw: Dict[str, object]) -> Dict[str, object]:
    normalized: Dict[str, object] = {}
    for key, value in raw.items():
        if key is None:
            continue
        out_key = (
            _normalize_metadata_plane_key(_normalize_metadata_tt_key(str(key)))
            if isinstance(key, str)
            else str(key)
        )
        for normalized_key, normalized_value in _iter_normalized_metadata_items(out_key, value):
            if normalized_key in normalized:
                if _metadata_value_is_empty(normalized[normalized_key]) and not _metadata_value_is_empty(
                    normalized_value
                ):
                    normalized[normalized_key] = normalized_value
                continue
            normalized[normalized_key] = normalized_value
    return normalized


def _load_existing_rows(metadata_path: Path) -> Tuple[List[str], List[Dict[str, object]]]:
    with metadata_path.open("r", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        existing_fields = _normalize_metadata_fieldnames(list(reader.fieldnames or []))
        existing_rows = [_normalize_metadata_row(dict(existing)) for existing in reader]
    return existing_fields, existing_rows


def _apply_preferred_field_order(
    fieldnames: List[str],
    preferred_fieldnames: Iterable[str] | None,
) -> List[str]:
    if preferred_fieldnames:
        seen = set(fieldnames)
        preferred = [name for name in preferred_fieldnames if name in seen]
        remainder = [name for name in fieldnames if name not in preferred]
        fieldnames = preferred + remainder
    identity_prefix = [name for name in TRACEABILITY_COLUMNS if name in fieldnames]
    if identity_prefix:
        fieldnames = identity_prefix + [name for name in fieldnames if name not in identity_prefix]
    if "data_purity_percentage" in fieldnames:
        fieldnames = [name for name in fieldnames if name != "data_purity_percentage"] + [
            "data_purity_percentage"
        ]
    return fieldnames


def _format_metadata_row(item: Dict[str, object], fieldnames: List[str]) -> Dict[str, object]:
    formatted: Dict[str, object] = {}
    for key in fieldnames:
        lookup_key = _normalize_metadata_tt_key(str(key)) if isinstance(key, str) else key
        if (
            lookup_key in EVENTS_PER_SECOND_COLUMN_SET
            or (
                isinstance(lookup_key, str)
                and (
                    lookup_key.startswith("events_per_second_")
                    or lookup_key == "analysis_mode"
                    or lookup_key.endswith("_count")
                    or lookup_key.endswith("_rate_hz")
                    or lookup_key.endswith("_fraction")
                )
            )
        ):
            value = item.get(lookup_key, item.get(key, 0))
            if _metadata_value_is_empty(value):
                formatted[key] = 0
            else:
                formatted[key] = value
            continue
        value = item.get(lookup_key, item.get(key, ""))
        if value is None or (isinstance(value, float) and math.isnan(value)):
            formatted[key] = ""
        elif isinstance(value, (bool, np.bool_)):
            formatted[key] = int(bool(value))
        elif isinstance(value, (list, dict, np.ndarray)):
            formatted[key] = str(value)
        else:
            formatted[key] = value
    return formatted


def _metadata_size_label(size_bytes: int) -> str:
    return f"{size_bytes / (1024 * 1024):.1f} MiB"


def _metadata_allows_full_scan(size_bytes: int) -> bool:
    return size_bytes <= METADATA_MAX_FULL_SCAN_BYTES


def _summarize_metadata_keys(keys: Iterable[str], *, max_items: int = 5) -> str:
    unique_keys = sorted({str(key) for key in keys if str(key).strip()})
    if not unique_keys:
        return "none"
    if len(unique_keys) <= max_items:
        return ", ".join(unique_keys)
    shown = ", ".join(unique_keys[:max_items])
    return f"{shown}, ... (+{len(unique_keys) - max_items} more)"


def _append_metadata_row(
    metadata_path: Path,
    row: Dict[str, object],
    fieldnames: List[str],
) -> None:
    if metadata_path.exists() and metadata_path.stat().st_size > 0:
        with metadata_path.open("rb+") as handle:
            handle.seek(-1, 2)
            if handle.read(1) not in (b"\n", b"\r"):
                handle.write(b"\n")
    with metadata_path.open("a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction="ignore")
        writer.writerow(_format_metadata_row(row, fieldnames))


def _append_metadata_row_with_warning(
    metadata_path: Path,
    row: Dict[str, object],
    raw_existing_fields: List[str],
    preferred_fieldnames: Iterable[str] | None,
    log_fn: Callable[..., None],
    *,
    reason: str,
    file_size_bytes: int,
) -> None:
    append_fields = list(raw_existing_fields)
    used_existing_header = bool(append_fields)
    if not append_fields:
        append_fields = _apply_preferred_field_order(list(row.keys()), preferred_fieldnames)

    append_lookup_keys = {
        _normalize_metadata_tt_key(name) if isinstance(name, str) else name
        for name in append_fields
    }
    dropped_keys = [
        key
        for key in row.keys()
        if key not in append_lookup_keys
    ]

    if used_existing_header:
        header_note = "existing header"
    else:
        header_note = "current row order because the on-disk header could not be trusted"

    log_fn(
        "[metadata] Warning: "
        f"{metadata_path.name} needs a full CSV scan ({reason}), but the file is "
        f"{_metadata_size_label(file_size_bytes)}. "
        f"Skipping repair/rewrite and appending with the {header_note}. "
        f"Dropped keys: {_summarize_metadata_keys(dropped_keys)}. "
        "Manual cleanup may be needed."
    )
    _append_metadata_row(metadata_path, row, append_fields)


def _stream_expand_metadata_schema(
    metadata_path: Path,
    row: Dict[str, object],
    existing_fields: List[str],
    preferred_fieldnames: Iterable[str] | None,
    drop_field_predicate: Callable[[str], bool] | None,
    *,
    replace_filename_base: str | None = None,
) -> bool:
    """Expand a large CSV header without loading its rows into memory.

    This path is used only when the existing header is already normalized and
    a new metadata key needs storage. The old file remains intact unless the
    complete streaming rewrite and append succeed.
    """
    fieldnames = [
        name
        for name in existing_fields
        if not (drop_field_predicate and drop_field_predicate(name))
    ]
    seen = set(fieldnames)
    for name in row:
        if name not in seen and not (drop_field_predicate and drop_field_predicate(name)):
            fieldnames.append(name)
            seen.add(name)
    fieldnames = _apply_preferred_field_order(fieldnames, preferred_fieldnames)
    replace_basename = str(replace_filename_base or "").strip()

    original_field_limit = csv.field_size_limit()
    csv.field_size_limit(2**31 - 1)
    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f".{metadata_path.name}.",
        suffix=".schema-tmp",
        dir=metadata_path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with metadata_path.open("r", newline="") as source, os.fdopen(
            temp_fd, "w", newline=""
        ) as destination:
            reader = csv.DictReader(source)
            if list(reader.fieldnames or []) != existing_fields:
                return False
            writer = csv.DictWriter(destination, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for old_row in reader:
                if None in old_row and old_row[None]:
                    return False
                if replace_basename and str(old_row.get("filename_base", "")).strip() == replace_basename:
                    continue
                writer.writerow({name: old_row.get(name, "") for name in fieldnames})
            writer.writerow(_format_metadata_row(row, fieldnames))
            destination.flush()
            os.fsync(destination.fileno())
        os.chmod(temp_path, stat.S_IMODE(metadata_path.stat().st_mode))
        os.replace(temp_path, metadata_path)
        return True
    except (csv.Error, OSError, ValueError):
        return False
    finally:
        csv.field_size_limit(original_field_limit)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _save_metadata_rewrite(
    metadata_path: Path,
    row: Dict[str, object],
    preferred_fieldnames: Iterable[str] | None,
    log_fn: Callable[..., None],
    drop_field_predicate: Callable[[str], bool] | None = None,
    replace_filename_base: str | None = None,
) -> None:
    rows: List[Dict[str, object]] = []
    fieldnames: List[str] = []
    row_filtered = {
        key: value
        for key, value in row.items()
        if not (
            drop_field_predicate
            and isinstance(key, str)
            and drop_field_predicate(key)
        )
    }

    if metadata_path.exists() and metadata_path.stat().st_size > 0:
        try:
            fieldnames, existing_rows = _load_existing_rows(metadata_path)
        except csv.Error as exc:
            if "field larger than field limit" in str(exc).lower():
                fixed = repair_metadata_file(metadata_path)
                log_fn(
                    f"Detected oversized analysis_mode entries in {metadata_path}; normalized {fixed} row(s)."
                )
                try:
                    fieldnames, existing_rows = _load_existing_rows(metadata_path)
                except csv.Error as err:
                    raise RuntimeError(
                        f"Failed to repair metadata file {metadata_path} after detecting oversized fields."
                    ) from err
            else:
                raise
        if drop_field_predicate:
            existing_rows = [
                {
                    key: value
                    for key, value in existing.items()
                    if not (
                        isinstance(key, str)
                        and drop_field_predicate(key)
                    )
                }
                for existing in existing_rows
            ]
            fieldnames = [
                key
                for key in fieldnames
                if not (
                    isinstance(key, str)
                    and drop_field_predicate(key)
                )
            ]
        replace_basename = str(replace_filename_base or "").strip()
        if replace_basename:
            existing_rows = [
                existing
                for existing in existing_rows
                if str(existing.get("filename_base", "")).strip() != replace_basename
            ]
        rows.extend(existing_rows)

    rows.append(row_filtered)
    fixed_during_rewrite = sanitize_analysis_mode_rows(rows)
    if fixed_during_rewrite:
        log_fn(f"Normalised analysis_mode in {fixed_during_rewrite} metadata row(s).")

    seen = set(fieldnames)
    for item in rows:
        for key in item.keys():
            if (
                drop_field_predicate
                and isinstance(key, str)
                and drop_field_predicate(key)
            ):
                continue
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)
    if not fieldnames:
        fieldnames = _normalize_metadata_fieldnames(raw_fieldnames)
        if effective_drop_field_predicate:
            fieldnames = [
                key
                for key in fieldnames
                if not (
                    isinstance(key, str)
                    and effective_drop_field_predicate(key)
                )
            ]
    fieldnames = _apply_preferred_field_order(fieldnames, preferred_fieldnames)

    with metadata_path.open("w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for item in rows:
            writer.writerow(_format_metadata_row(item, fieldnames))


def normalize_metadata_file_schema(
    metadata_path: str | Path,
    *,
    preferred_fieldnames: Iterable[str] | None = None,
    log_fn: Callable[..., None] = builtins.print,
    drop_field_predicate: Callable[[str], bool] | None = None,
) -> Path:
    metadata_path = Path(metadata_path)
    if not metadata_path.exists() or metadata_path.stat().st_size == 0:
        return metadata_path

    effective_drop_field_predicate = _compose_drop_field_predicate(
        metadata_path,
        drop_field_predicate,
    )
    original_limit = csv.field_size_limit()
    csv.field_size_limit(2**31 - 1)
    try:
        with metadata_path.open("r", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            raw_fieldnames = list(reader.fieldnames or [])
            rows: list[dict[str, object]] = []
            fieldnames: list[str] = []
            seen_fields: set[str] = set()
            for raw_row in reader:
                normalized_row = _normalize_metadata_row(dict(raw_row))
                if effective_drop_field_predicate:
                    normalized_row = {
                        key: value
                        for key, value in normalized_row.items()
                        if not (
                            isinstance(key, str)
                            and effective_drop_field_predicate(key)
                        )
                    }
                sanitize_analysis_mode_rows([normalized_row])
                rows.append(normalized_row)
                for key in normalized_row.keys():
                    if key in seen_fields:
                        continue
                    seen_fields.add(key)
                    fieldnames.append(key)
    finally:
        csv.field_size_limit(original_limit)

    fieldnames = _apply_preferred_field_order(fieldnames, preferred_fieldnames)
    temp_path = metadata_path.with_suffix(metadata_path.suffix + ".schema_tmp")
    with temp_path.open("w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(_format_metadata_row(row, fieldnames))
    temp_path.replace(metadata_path)
    _sync_filename_base_index_from_csv(metadata_path, log_fn)
    return metadata_path


def _metadata_operation_dir(metadata_path: Path) -> Path:
    return metadata_path.parent / "OPERATION"


def _metadata_lock_path(metadata_path: Path) -> Path:
    return _metadata_operation_dir(metadata_path) / f"{metadata_path.name}.lock"


def _legacy_filename_base_index_path(metadata_path: Path) -> Path:
    return metadata_path.with_suffix(metadata_path.suffix + ".filename_base.index")


def _filename_base_index_path(metadata_path: Path) -> Path:
    return _metadata_operation_dir(metadata_path) / f"{metadata_path.name}.filename_base.index"


def _load_filename_base_index(index_path: Path) -> set[str]:
    if not index_path.exists():
        return set()
    values: set[str] = set()
    with index_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            value = line.strip()
            if value:
                values.add(value)
    return values


def _write_filename_base_index(index_path: Path, values: Iterable[str]) -> None:
    unique_values = sorted({value.strip() for value in values if str(value).strip()})
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("w", encoding="utf-8", newline="") as handle:
        for value in unique_values:
            handle.write(f"{value}\n")


def _sync_filename_base_index_from_csv(
    metadata_path: Path,
    log_fn: Callable[..., None],
) -> set[str]:
    index_path = _filename_base_index_path(metadata_path)
    legacy_index_path = _legacy_filename_base_index_path(metadata_path)
    if not metadata_path.exists() or metadata_path.stat().st_size == 0:
        for candidate in (index_path, legacy_index_path):
            if candidate.exists():
                candidate.unlink()
        return set()

    try:
        with metadata_path.open("r", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            fieldnames = list(reader.fieldnames or [])
            if "filename_base" not in fieldnames:
                for candidate in (index_path, legacy_index_path):
                    if candidate.exists():
                        candidate.unlink()
                return set()
            values = {
                str(raw).strip()
                for raw in (row.get("filename_base") for row in reader)
                if str(raw).strip()
            }
    except csv.Error as exc:
        if "field larger than field limit" in str(exc).lower():
            fixed = repair_metadata_file(metadata_path)
            log_fn(
                f"Detected oversized analysis_mode entries in {metadata_path}; normalized {fixed} row(s)."
            )
            return _sync_filename_base_index_from_csv(metadata_path, log_fn)
        raise

    _write_filename_base_index(index_path, values)
    return values


def _load_or_build_filename_base_index(
    metadata_path: Path,
    log_fn: Callable[..., None],
    *,
    allow_csv_scan: bool = True,
) -> Tuple[Path, set[str], bool]:
    index_path = _filename_base_index_path(metadata_path)
    legacy_index_path = _legacy_filename_base_index_path(metadata_path)
    if index_path.exists():
        try:
            return index_path, _load_filename_base_index(index_path), True
        except OSError:
            # Fall back to rebuilding from the CSV below.
            pass

    if legacy_index_path.exists():
        try:
            legacy_values = _load_filename_base_index(legacy_index_path)
            _write_filename_base_index(index_path, legacy_values)
            try:
                legacy_index_path.unlink()
            except OSError:
                pass
            return index_path, legacy_values, True
        except OSError:
            # Fall back to rebuilding from CSV below.
            pass

    if not allow_csv_scan:
        return index_path, set(), False

    return index_path, _sync_filename_base_index_from_csv(metadata_path, log_fn), True


def _compose_drop_field_predicate(
    metadata_path: Path,
    drop_field_predicate: Callable[[str], bool] | None,
) -> Callable[[str], bool] | None:
    """Return effective drop predicate, enforcing per-file schema constraints."""
    if metadata_path.name.endswith("_metadata_rate_histogram.csv"):
        def _rate_histogram_drop(column_name: str) -> bool:
            return not is_rate_histogram_file_column(column_name)

        if drop_field_predicate is None:
            return _rate_histogram_drop

        return lambda column_name: (
            drop_field_predicate(column_name) or _rate_histogram_drop(column_name)
        )

    if metadata_path.name.endswith("_metadata_chi2_four_plane.csv"):
        def _chi2_four_plane_drop(column_name: str) -> bool:
            return not is_chi2_four_plane_file_column(column_name)

        if drop_field_predicate is None:
            return _chi2_four_plane_drop

        return lambda column_name: (
            drop_field_predicate(column_name) or _chi2_four_plane_drop(column_name)
        )

    return drop_field_predicate


def save_metadata(
    metadata_path: str | Path,
    row: Dict[str, object],
    preferred_fieldnames: Iterable[str] | None = None,
    log_fn: Callable[..., None] = builtins.print,
    drop_field_predicate: Callable[[str], bool] | None = None,
    replace_existing_basename: bool = False,
) -> Path:
    metadata_path = Path(metadata_path)
    metadata_write_enabled, metadata_type, metadata_config_path = should_write_step1_metadata(
        metadata_path,
    )
    if not metadata_write_enabled:
        log_fn(
            "[metadata] Skipping disabled metadata write: "
            f"{metadata_path.name} (type={metadata_type}) from {metadata_config_path}"
        )
        return metadata_path

    effective_drop_field_predicate = _compose_drop_field_predicate(
        metadata_path,
        drop_field_predicate,
    )
    row_data = _normalize_metadata_row(dict(row))
    if effective_drop_field_predicate:
        row_data = {
            key: value
            for key, value in row_data.items()
            if not (
                isinstance(key, str)
                and effective_drop_field_predicate(key)
            )
        }
    fixed_new_row = sanitize_analysis_mode_rows([row_data])
    if fixed_new_row:
        log_fn(f"Normalised analysis_mode in {fixed_new_row} metadata row(s).")

    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _metadata_lock_path(metadata_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)

        if not metadata_path.exists() or metadata_path.stat().st_size == 0:
            initial_fields = _apply_preferred_field_order(list(row_data.keys()), preferred_fieldnames)
            with metadata_path.open("w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=initial_fields)
                writer.writeheader()
                writer.writerow(_format_metadata_row(row_data, initial_fields))
            _sync_filename_base_index_from_csv(metadata_path, log_fn)
            return metadata_path

        metadata_file_size = metadata_path.stat().st_size
        try:
            with metadata_path.open("r", newline="") as csvfile:
                reader = csv.DictReader(csvfile)
                raw_existing_fields = list(reader.fieldnames or [])
                existing_fields = _normalize_metadata_fieldnames(raw_existing_fields)
        except csv.Error as exc:
            if "field larger than field limit" in str(exc).lower():
                if _metadata_allows_full_scan(metadata_file_size):
                    fixed = repair_metadata_file(metadata_path)
                    log_fn(
                        f"Detected oversized analysis_mode entries in {metadata_path}; normalized {fixed} row(s)."
                    )
                    _save_metadata_rewrite(
                        metadata_path,
                        row_data,
                        preferred_fieldnames,
                        log_fn,
                        drop_field_predicate=effective_drop_field_predicate,
                        replace_filename_base=(
                            str(row_data.get("filename_base", "")).strip() if replace_existing_basename else None
                        ),
                    )
                    _sync_filename_base_index_from_csv(metadata_path, log_fn)
                    return metadata_path
                _append_metadata_row_with_warning(
                    metadata_path,
                    row_data,
                    [],
                    preferred_fieldnames,
                    log_fn,
                    reason="oversized fields detected while opening the metadata file",
                    file_size_bytes=metadata_file_size,
                )
                return metadata_path
            raise

        existing_field_set = set(existing_fields)
        rewrite_reason = ""
        if not existing_fields:
            rewrite_reason = "missing or empty header"
        elif existing_fields != raw_existing_fields:
            rewrite_reason = "header normalization mismatch"
        elif effective_drop_field_predicate and any(
            isinstance(name, str) and effective_drop_field_predicate(name) for name in existing_fields
        ):
            rewrite_reason = "header contains columns that should now be dropped"
        else:
            new_keys = [key for key in row_data.keys() if key not in existing_field_set]
            if new_keys:
                rewrite_reason = (
                    "new columns not present in header: "
                    f"{_summarize_metadata_keys(new_keys)}"
                )

        if rewrite_reason:
            if _metadata_allows_full_scan(metadata_file_size):
                _save_metadata_rewrite(
                    metadata_path,
                    row_data,
                    preferred_fieldnames,
                    log_fn,
                    drop_field_predicate=effective_drop_field_predicate,
                    replace_filename_base=(
                        str(row_data.get("filename_base", "")).strip() if replace_existing_basename else None
                    ),
                )
                _sync_filename_base_index_from_csv(metadata_path, log_fn)
                return metadata_path
            if (
                rewrite_reason.startswith("new columns not present in header:")
                and raw_existing_fields == existing_fields
                and _stream_expand_metadata_schema(
                    metadata_path,
                    row_data,
                    raw_existing_fields,
                    preferred_fieldnames,
                    effective_drop_field_predicate,
                    replace_filename_base=(
                        str(row_data.get("filename_base", "")).strip()
                        if replace_existing_basename
                        else None
                    ),
                )
            ):
                log_fn(
                    f"[metadata] Expanded {metadata_path.name} schema by streaming the "
                    f"{_metadata_size_label(metadata_file_size)} CSV; new fields were preserved."
                )
                _sync_filename_base_index_from_csv(metadata_path, log_fn)
                return metadata_path
            _append_metadata_row_with_warning(
                metadata_path,
                row_data,
                raw_existing_fields,
                preferred_fieldnames,
                log_fn,
                reason=rewrite_reason,
                file_size_bytes=metadata_file_size,
            )
            return metadata_path

        basename = str(row_data.get("filename_base", "")).strip()
        index_path: Path | None = None
        index_values: set[str] = set()
        index_is_complete = False
        duplicate_basename = False
        if basename:
            index_path, index_values, index_is_complete = _load_or_build_filename_base_index(
                metadata_path,
                log_fn,
                allow_csv_scan=_metadata_allows_full_scan(metadata_file_size),
            )
            if not index_is_complete:
                log_fn(
                    "[metadata] Warning: "
                    f"{metadata_path.name} is {_metadata_size_label(metadata_file_size)} and its "
                    "filename_base index is missing. Skipping full CSV scan for duplicate detection."
                )
            duplicate_basename = basename in index_values
            if duplicate_basename:
                if replace_existing_basename and _metadata_allows_full_scan(metadata_file_size):
                    log_fn(
                        f"[metadata] filename_base={basename} already present in {metadata_path.name}; replacing existing row."
                    )
                    _save_metadata_rewrite(
                        metadata_path,
                        row_data,
                        preferred_fieldnames,
                        log_fn,
                        drop_field_predicate=effective_drop_field_predicate,
                        replace_filename_base=basename,
                    )
                    _sync_filename_base_index_from_csv(metadata_path, log_fn)
                    return metadata_path
                log_fn(
                    f"[metadata] filename_base={basename} already present in {metadata_path.name}; appending new row."
                )

        _append_metadata_row(metadata_path, row_data, raw_existing_fields or existing_fields)

        if basename and index_path is not None and index_is_complete and not duplicate_basename:
            with index_path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(f"{basename}\n")

    return metadata_path


def build_events_per_second_metadata(
    df: pd.DataFrame,
    time_columns: Tuple[str, ...] = ("datetime", "Time"),
) -> Dict[str, object]:
    metadata = {column: 0 for column in EVENTS_PER_SECOND_COLUMNS}
    if df is None or df.empty:
        return metadata

    time_col = next((col for col in time_columns if col in df.columns), None)
    if time_col is not None:
        times = pd.to_datetime(df[time_col], errors="coerce")
    elif isinstance(df.index, pd.DatetimeIndex):
        times = pd.Series(df.index)
    else:
        return metadata

    times = pd.Series(times).dropna()
    if times.empty:
        return metadata

    times = times.dt.floor("s")
    start_time = times.min()
    end_time = times.max()
    if pd.isna(start_time) or pd.isna(end_time):
        return metadata

    full_range = pd.date_range(start=start_time, end=end_time, freq="s")
    events_per_second = times.value_counts().reindex(full_range, fill_value=0).sort_index()

    total_seconds = int(events_per_second.size)
    total_events = int(events_per_second.sum())
    metadata["events_per_second_total_seconds"] = total_seconds
    metadata["events_per_second_global_rate"] = round(total_events / total_seconds, 6) if total_seconds > 0 else 0

    hist_counts = events_per_second.value_counts()
    for events_count, seconds_count in hist_counts.items():
        events_count_int = int(events_count)
        if 0 <= events_count_int <= EVENTS_PER_SECOND_MAX:
            metadata[f"events_per_second_{events_count_int}_count"] = int(seconds_count)

    return metadata


def add_normalized_count_metadata(
    metadata: Dict[str, object],
    denominator_seconds: object,
    log_fn: Callable[..., None] = builtins.print,
) -> None:
    try:
        denom = float(denominator_seconds) if denominator_seconds is not None else 0.0
    except (TypeError, ValueError):
        denom = 0.0

    metadata["count_rate_denominator_seconds"] = int(denom) if denom > 0 else 0

    if denom <= 0:
        log_fn("[count-rates] Denominator seconds is 0; skipping normalized count columns.")
        return

    for key, value in list(metadata.items()):
        if not isinstance(key, str):
            continue

        is_count = key.endswith("_count")
        is_entries = _is_entries_metric_key(key) and not key.endswith("_rate_hz")
        if not (is_count or is_entries):
            continue
        try:
            num = float(value)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(num):
            continue

        if is_count:
            out_key = key[: -len("_count")] + "_rate_hz"
        else:
            out_key = key + "_rate_hz"

        metadata[out_key] = round(num / denom, 6)


def _normalize_tt_prefix(prefix: object) -> str:
    text = str(prefix).strip()
    if text.endswith("_"):
        text = text[:-1]
    return text


def _extract_tt_rate_components(column_name: str) -> tuple[str, str] | None:
    match = TT_RATE_COLUMN_RE.match(column_name)
    if match is None:
        return None
    prefix = _normalize_tt_prefix(match.group("prefix"))
    label = normalize_tt_label(match.group("label"), default="")
    if not prefix or not label:
        return None
    return prefix, label


def compute_global_rate_from_tt_rates(
    metadata: Dict[str, object],
    preferred_prefixes: Iterable[str] | None = None,
) -> tuple[float | None, str | None]:
    by_prefix: dict[str, dict[str, float]] = {}

    for key, value in metadata.items():
        if not isinstance(key, str):
            continue
        parsed = _extract_tt_rate_components(key)
        if parsed is None:
            continue
        prefix, tt_label = parsed
        if tt_label not in CANONICAL_TT_LABELS:
            # Ignore transition-matrix keys like clean_to_cal_tt_12_34_rate_hz.
            continue
        try:
            rate_value = float(value)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(rate_value):
            continue
        by_prefix.setdefault(prefix, {})[tt_label] = rate_value

    if not by_prefix:
        return None, None

    selected_prefix: str | None = None
    if preferred_prefixes is not None:
        for raw_prefix in preferred_prefixes:
            normalized_prefix = _normalize_tt_prefix(raw_prefix)
            if normalized_prefix in by_prefix and by_prefix[normalized_prefix]:
                selected_prefix = normalized_prefix
                break

    if selected_prefix is None:
        selected_prefix = min(
            by_prefix.keys(),
            key=lambda prefix: (-len(by_prefix[prefix]), prefix),
        )

    total_rate = float(sum(by_prefix[selected_prefix].values()))
    return round(total_rate, 6), selected_prefix


def set_global_rate_from_tt_rates(
    metadata: Dict[str, object],
    preferred_prefixes: Iterable[str] | None = None,
    global_rate_key: str = "events_per_second_global_rate",
    log_fn: Callable[..., None] | None = None,
) -> bool:
    total_rate, selected_prefix = compute_global_rate_from_tt_rates(
        metadata,
        preferred_prefixes=preferred_prefixes,
    )
    if total_rate is None or selected_prefix is None:
        return False

    metadata[global_rate_key] = round(float(total_rate), 6)
    if log_fn is not None:
        log_fn(
            f"[global-rate] {global_rate_key} set as sum of {selected_prefix}_*_rate_hz."
        )
    return True


def load_itineraries_from_file(
    file_path: Path,
    required: bool = True,
    log_fn: Callable[..., None] = builtins.print,
    echo_entries: bool = True,
    header_suffix: str = ":",
) -> list[list[str]]:
    if not file_path.exists():
        if required:
            raise FileNotFoundError(f"Cannot find itineraries file: {file_path}")
        return []

    itineraries: list[list[str]] = []
    with file_path.open("r", encoding="utf-8") as itinerary_file:
        if log_fn is not None:
            log_fn(f"Loading itineraries from {file_path}{header_suffix}")
        for raw_line in itinerary_file:
            stripped_line = raw_line.strip()
            if not stripped_line or stripped_line.startswith("#"):
                continue
            segments = [segment.strip() for segment in stripped_line.split(",") if segment.strip()]
            if segments:
                itineraries.append(segments)
                if log_fn is not None and echo_entries:
                    log_fn(segments)

    if not itineraries and required:
        raise ValueError(f"Itineraries file {file_path} is empty.")
    return itineraries


def write_itineraries_to_file(file_path: Path, itineraries: Iterable[Iterable[str]]) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    unique_itineraries: dict[tuple[str, ...], None] = {}

    for itinerary in itineraries:
        itinerary_tuple = tuple(itinerary)
        if not itinerary_tuple:
            continue
        unique_itineraries.setdefault(itinerary_tuple, None)

    with file_path.open("w", encoding="utf-8") as itinerary_file:
        for itinerary_tuple in unique_itineraries:
            itinerary_file.write(",".join(itinerary_tuple) + "\n")


def ensure_plane_xpos_columns(
    dataframe: pd.DataFrame,
    tdif_to_x_mm_per_ns: float,
    *,
    overwrite: bool = False,
) -> dict[str, int]:
    """Create final per-plane X positions from T_dif, preserving zero sentinels.

    The detector convention used throughout STEP_1 is
    ``X [mm] = p#_tdif [ns] * strip propagation speed [mm/ns]``.
    New producer stages should use ``overwrite=True``; downstream stages use
    the default to backfill historical inputs without replacing stored data.
    """
    scale = float(tdif_to_x_mm_per_ns)
    if not np.isfinite(scale) or scale == 0:
        raise ValueError("tdif_to_x_mm_per_ns must be finite and nonzero")

    summary = {
        "source_columns_found": 0,
        "columns_created": 0,
        "values_backfilled": 0,
        "finite_mismatches": 0,
    }
    for plane in range(1, 5):
        source = f"p{plane}_tdif"
        target = f"p{plane}_xpos"
        if source not in dataframe.columns:
            continue
        summary["source_columns_found"] += 1
        expected = pd.to_numeric(dataframe[source], errors="coerce").astype(float) * scale
        if overwrite or target not in dataframe.columns:
            if target not in dataframe.columns:
                summary["columns_created"] += 1
            dataframe.loc[:, target] = expected
            continue

        stored = pd.to_numeric(dataframe[target], errors="coerce").astype(float)
        backfill_mask = stored.isna() & expected.notna()
        if bool(backfill_mask.any()):
            dataframe.loc[backfill_mask, target] = expected.loc[backfill_mask]
            summary["values_backfilled"] += int(backfill_mask.sum())
            stored = pd.to_numeric(dataframe[target], errors="coerce").astype(float)
        comparable = stored.notna() & expected.notna()
        mismatch = comparable & ~np.isclose(
            stored.to_numpy(dtype=float),
            expected.to_numpy(dtype=float),
            rtol=1e-9,
            atol=1e-9,
            equal_nan=True,
        )
        summary["finite_mismatches"] += int(mismatch.sum())
    return summary


def y_pos(y_width):
    return np.cumsum(y_width) - (np.sum(y_width) + y_width) / 2


def collect_columns(columns: Iterable[str], pattern) -> list[str]:
    return [column for column in columns if pattern.match(column)]
