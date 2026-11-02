#!/usr/bin/env python3
"""
Scan Task 4-style fiducial regions for the freshest MINGO00 Task 5 input file.

This script:
- selects only the freshest parquet in the Task 5 completed directory,
- resolves the matching Task 4 listed parquet with the same basename,
- reconstructs the Task 4 efficiency-source event table by merging fitted
  track quantities with the per-plane hit columns,
- applies the same generic Task 4 final filter used before the efficiency
  metadata calculation,
- scans fiducial limits in theta and radius,
- computes the same track-based robust efficiency quantities used by Task 4,
- matches simulated efficiencies through param_hash,
- writes one CSV row per scan point,
- optionally renders one large track-efficiency diagnostic plot for a
  configured scan point.
"""

from __future__ import annotations

from datetime import datetime
from itertools import product
import math
from pathlib import Path
import re
import sys
from typing import Iterable, Mapping

import matplotlib
matplotlib.use("Agg")
from matplotlib import patheffects as path_effects
from matplotlib.patches import Circle
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.constants import c
from tqdm import tqdm
import yaml

CURRENT_PATH = Path(__file__).resolve()
REPO_ROOT = None
for parent in CURRENT_PATH.parents:
    if parent.name == "MINGO_ANALYSIS_SCRIPTS":
        REPO_ROOT = parent.parent.parent
        break
if REPO_ROOT is None:
    REPO_ROOT = CURRENT_PATH.parents[-1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.path_config import get_master_config_root  # noqa: E402
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.reprocessing_utils import (  # noqa: E402
    canonical_processing_basename,
    infer_station_number_from_processing_name,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.simulated_data_utils import (  # noqa: E402
    extract_param_hash_from_parquet,
    load_simulated_efficiencies,
    resolve_simulated_z_positions,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.step1_shared import (  # noqa: E402
    apply_step1_master_overrides,
    apply_step1_task_parameter_overrides,
    build_events_per_second_metadata,
    load_step1_filter_parameter_state,
    y_pos,
)


SCRIPT_CONFIG_PATH = CURRENT_PATH.with_name("task4_fiducial_scan_table_config.yaml")

# Default fiducial scan values. Theta is in degrees. Radius is in mm.
# These defaults are only used if the YAML file is missing or incomplete.
DEFAULT_THETA_MAX_VALUES = [5.0, 10.0, 15.0]
DEFAULT_RADIUS_MAX_VALUES = [50.0, 100.0, 150.0]

TASK5_COMPLETED_DIRECTORY = (
    REPO_ROOT
    / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
    / "MINGO00"
    / "STAGE_1"
    / "EVENT_DATA"
    / "STEP_1"
    / "TASK_5"
    / "INPUT_FILES"
    / "COMPLETED_DIRECTORY"
)
TASK4_LISTED_DIRECTORY = (
    REPO_ROOT
    / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
    / "MINGO00"
    / "STAGE_1"
    / "EVENT_DATA"
    / "STEP_1"
    / "TASK_4"
    / "INPUT_FILES"
    / "COMPLETED_DIRECTORY"
)
SIMULATION_PARAMS_CSV = (
    REPO_ROOT
    / "MINGO_DIGITAL_TWIN"
    / "SIMULATED_DATA"
    / "step_final_simulation_params.csv"
)
OUTPUT_PARENT_DIRECTORY = (
    REPO_ROOT
    / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS"
    / "ANCILLARY"
    / "CALCULATIONS"
    / "TASK4_FIDUCIAL_SCAN"
)

TASK4_PRIMARY_TT_COLUMN = "fit_tt"
TASK4_COMPAT_TT_COLUMN = "definitive_tt"
_ROBUST_EFFICIENCY_PLATEAU_TOLERANCE = 0.05
OUTPUT_SCAN_COLUMNS = [
    "filename_base",
    "execution_timestamp",
    "param_hash",
    "theta_max",
    "r_max",
    "P1_eff_robust_xyphi",
    "P2_eff_robust_xyphi",
    "P3_eff_robust_xyphi",
    "P4_eff_robust_xyphi",
    "fiducial_1234_percent_of_total",
    "eff_p1",
    "eff_p2",
    "eff_p3",
    "eff_p4",
]


def get_task4_tt_column(df_input: pd.DataFrame, preferred: str = TASK4_PRIMARY_TT_COLUMN) -> str | None:
    if preferred in df_input.columns:
        return preferred
    if TASK4_COMPAT_TT_COLUMN in df_input.columns:
        return TASK4_COMPAT_TT_COLUMN
    return None


def get_task4_tt_series(df_input: pd.DataFrame, preferred: str = TASK4_PRIMARY_TT_COLUMN) -> pd.Series:
    tt_col = get_task4_tt_column(df_input, preferred=preferred)
    if tt_col is None:
        return pd.Series(0, index=df_input.index, dtype=int)
    return pd.to_numeric(df_input[tt_col], errors="coerce").fillna(0).astype(int)


def _coerce_config_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _normalize_scan_values(raw_value: object, default: list[float]) -> list[float]:
    if raw_value is None:
        source = list(default)
    elif isinstance(raw_value, (list, tuple, set, np.ndarray, pd.Series)):
        source = list(raw_value)
    else:
        raise ValueError(f"Expected a sequence of numeric scan values, got {type(raw_value).__name__}.")

    parsed: list[float] = []
    for item in source:
        try:
            value = float(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid scan value: {item!r}") from exc
        if not np.isfinite(value):
            raise ValueError(f"Non-finite scan value: {item!r}")
        if value < 0.0:
            raise ValueError(f"Scan values must be >= 0, got {value!r}")
        if not any(abs(value - existing) < 1e-12 for existing in parsed):
            parsed.append(value)
    if not parsed:
        return list(default)
    return parsed


def _expand_scan_axis_values(
    raw_value: object,
    *,
    default: list[float],
    axis_name: str,
) -> list[float]:
    if raw_value is None:
        return list(default)

    if isinstance(raw_value, dict):
        missing = [key for key in ("first", "last", "steps") if key not in raw_value]
        if missing:
            raise ValueError(
                f"Scan axis '{axis_name}' range config is missing keys: {missing}. "
                "Expected: first, last, steps."
            )
        try:
            first = float(raw_value["first"])
            last = float(raw_value["last"])
            steps = int(raw_value["steps"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid range specification for scan axis '{axis_name}': {raw_value!r}"
            ) from exc
        if not np.isfinite(first) or not np.isfinite(last):
            raise ValueError(f"Non-finite first/last values for scan axis '{axis_name}': {raw_value!r}")
        if first < 0.0 or last < 0.0:
            raise ValueError(f"Scan axis '{axis_name}' requires non-negative first/last values.")
        if steps <= 0:
            raise ValueError(f"Scan axis '{axis_name}' requires steps >= 1, got {steps}.")
        if steps == 1:
            return _normalize_scan_values([first], default)
        return _normalize_scan_values(np.linspace(first, last, steps).tolist(), default)

    return _normalize_scan_values(raw_value, default)


def _load_large_plot_config(loaded: Mapping[str, object]) -> dict[str, object]:
    raw_plot_cfg = loaded.get("track_efficiency_large_plot", {})
    if raw_plot_cfg is None:
        raw_plot_cfg = {}
    if not isinstance(raw_plot_cfg, Mapping):
        raise ValueError(
            f"Expected 'track_efficiency_large_plot' to be a mapping, got {type(raw_plot_cfg).__name__}."
        )

    enabled = _coerce_config_bool(raw_plot_cfg.get("enabled", False), default=False)
    theta_max_deg = raw_plot_cfg.get("theta_max_deg", None)
    radius_max_mm = raw_plot_cfg.get("radius_max_mm", None)
    theta_value = float(theta_max_deg) if theta_max_deg is not None else 30.0
    radius_value = float(radius_max_mm) if radius_max_mm is not None else 100.0
    if not np.isfinite(theta_value) or theta_value < 0.0:
        raise ValueError(f"Invalid track_efficiency_large_plot.theta_max_deg={theta_max_deg!r}")
    if not np.isfinite(radius_value) or radius_value < 0.0:
        raise ValueError(f"Invalid track_efficiency_large_plot.radius_max_mm={radius_max_mm!r}")
    return {
        "enabled": bool(enabled),
        "theta_max_deg": float(theta_value),
        "radius_max_mm": float(radius_value),
    }


def load_scan_grid_config(config_path: Path) -> dict[str, object]:
    loaded: dict[str, object] = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            parsed = yaml.safe_load(handle)
        if isinstance(parsed, dict):
            loaded = parsed

    return {
        # The theta/r sweep space is defined here through the YAML config.
        "theta_max_values_deg": _expand_scan_axis_values(
            loaded.get("theta_max_scan", loaded.get("theta_max_values_deg")),
            default=DEFAULT_THETA_MAX_VALUES,
            axis_name="theta_max",
        ),
        "radius_max_values_mm": _expand_scan_axis_values(
            loaded.get("radius_max_scan", loaded.get("radius_max_values_mm")),
            default=DEFAULT_RADIUS_MAX_VALUES,
            axis_name="radius_max",
        ),
        "track_efficiency_large_plot": _load_large_plot_config(loaded),
    }


def _task4_config_float(
    config_obj: Mapping[str, object],
    primary_key: str,
    *alias_keys: str,
    default: float,
) -> float:
    for key in (primary_key, *alias_keys):
        raw_value = config_obj.get(key)
        if raw_value is None:
            continue
        if isinstance(raw_value, str) and raw_value.strip().lower() in {"", "none", "null"}:
            continue
        value = float(raw_value)
        if not np.isfinite(value):
            raise ValueError(f"Non-finite numeric configuration value for '{key}': {raw_value!r}")
        return value
    return float(default)


def _task4_parse_optional_float(raw_value: object) -> float | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, str) and raw_value.strip().lower() in {"", "none", "null"}:
        return None
    try:
        parsed = float(raw_value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(parsed):
        return None
    return float(parsed)


def _task4_get_optional_config_float(config_obj: Mapping[str, object], *keys: str) -> float | None:
    for key in keys:
        if key and key in config_obj:
            return _task4_parse_optional_float(config_obj.get(key))
    return None


def _task4_parse_filter_columns(raw_value: object, default: Iterable[str]) -> list[str]:
    if raw_value is None:
        source = list(default)
    elif isinstance(raw_value, str):
        source = [chunk.strip() for chunk in re.split(r"[\s,;]+", raw_value) if chunk.strip()]
    elif isinstance(raw_value, (list, tuple, set, np.ndarray, pd.Series)):
        source = [str(item).strip() for item in raw_value if str(item).strip()]
    else:
        source = list(default)
    return list(dict.fromkeys(source))


def _resolve_task4_track_efficiency_fiducial_cfg(config_obj: Mapping[str, object]) -> dict[str, object]:
    return {
        "charge_event_left": _task4_get_optional_config_float(config_obj, "fiducial_charge_event_left"),
        "charge_event_right": _task4_get_optional_config_float(config_obj, "fiducial_charge_event_right"),
        "theta_left_deg": _task4_get_optional_config_float(config_obj, "fiducial_theta_left"),
        "theta_right_deg": _task4_get_optional_config_float(config_obj, "fiducial_theta_right"),
        "x_by_plane": {
            plane: {
                "left": _task4_get_optional_config_float(config_obj, f"fiducial_x_plane_{plane}_left"),
                "right": _task4_get_optional_config_float(config_obj, f"fiducial_x_plane_{plane}_right"),
            }
            for plane in range(1, 5)
        },
        "y_by_plane": {
            plane: {
                "left": _task4_get_optional_config_float(config_obj, f"fiducial_y_plane_{plane}_left"),
                "right": _task4_get_optional_config_float(config_obj, f"fiducial_y_plane_{plane}_right"),
            }
            for plane in range(1, 5)
        },
    }


def _task4_resolve_region_bounds(
    left_limit: float | None,
    right_limit: float | None,
    physical_left: float,
    physical_right: float,
) -> tuple[float, float]:
    left = float(left_limit) if left_limit is not None else float(physical_left)
    right = float(right_limit) if right_limit is not None else float(physical_right)
    left = max(float(physical_left), min(left, float(physical_right)))
    right = max(float(physical_left), min(right, float(physical_right)))
    if right <= left:
        return float(physical_left), float(physical_right)
    return left, right


def _task4_resolve_efficiency_param_hash(explicit_param_hash: object, df_input: pd.DataFrame) -> str:
    if explicit_param_hash is not None:
        text = str(explicit_param_hash).strip()
        if text:
            return text
    if "param_hash" in df_input.columns:
        param_series = df_input["param_hash"].astype(str).str.strip()
        nonempty = param_series[(param_series != "") & (param_series.str.lower() != "nan")]
        if not nonempty.empty:
            return str(nonempty.iloc[0])
    return ""


def _resolve_task4_total_event_charge_series(df: pd.DataFrame) -> tuple[pd.Series | None, str | None]:
    for charge_column in ("charge_event", "tim_charge_event"):
        if charge_column not in df.columns:
            continue
        candidate = pd.to_numeric(df[charge_column], errors="coerce")
        if candidate.notna().sum() > 0 and (candidate > 0).any():
            return candidate.astype(float), charge_column

    plane_sum_columns = [
        column_name
        for column_name in ("P1_Q_sum_final", "P2_Q_sum_final", "P3_Q_sum_final", "P4_Q_sum_final")
        if column_name in df.columns
    ]
    if plane_sum_columns:
        candidate = (
            df.loc[:, plane_sum_columns]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0.0)
            .sum(axis=1)
            .astype(float)
        )
        if candidate.notna().sum() > 0 and (candidate > 0).any():
            return candidate, "+".join(plane_sum_columns)

    strip_columns = [
        column_name
        for column_name in df.columns
        if re.fullmatch(r"Q_P[1-4]s[1-4]", str(column_name))
    ]
    if strip_columns:
        candidate = (
            df.loc[:, strip_columns]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0.0)
            .sum(axis=1)
            .astype(float)
        )
        if candidate.notna().sum() > 0 and (candidate > 0).any():
            return candidate, "+".join(strip_columns)

    return None, None


def _safe_cfg_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_cfg_float(value: object, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float(default)
    return float(out) if np.isfinite(out) else float(default)


def _safe_cfg_optional_float(value: object) -> float | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return float(out) if np.isfinite(out) else None


def _resolve_task4_efficiency_metadata_cfg(config_dict: Mapping[str, object]) -> dict[str, object]:
    raw = config_dict.get("efficiency_metadata", {})
    if not isinstance(raw, dict):
        raw = {}
    return {
        "x_bin_count": max(1, _safe_cfg_int(raw.get("x_bin_count", 15), 15)),
        "y_bin_count": max(1, _safe_cfg_int(raw.get("y_bin_count", 20), 20)),
        "theta_bin_count": max(1, _safe_cfg_int(raw.get("theta_bin_count", 20), 20)),
        "phi_bin_count": max(1, _safe_cfg_int(raw.get("phi_bin_count", 24), 24)),
        "x_min_mm": raw.get("x_min_mm", None),
        "x_max_mm": raw.get("x_max_mm", None),
        "y_min_mm": raw.get("y_min_mm", None),
        "y_max_mm": raw.get("y_max_mm", None),
        "theta_min_deg": raw.get("theta_min_deg", None),
        "theta_max_deg": raw.get("theta_max_deg", None),
        "phi_min_deg": raw.get("phi_min_deg", None),
        "phi_max_deg": raw.get("phi_max_deg", None),
        "min_pool_events": max(1, _safe_cfg_int(raw.get("min_pool_events", 20), 20)),
        "min_accepted_events": max(1, _safe_cfg_int(raw.get("min_accepted_events", 10), 10)),
        "summary_fiducial_x_abs_max_mm": _safe_cfg_optional_float(raw.get("summary_fiducial_x_abs_max_mm", None)),
        "summary_fiducial_y_abs_max_mm": _safe_cfg_optional_float(raw.get("summary_fiducial_y_abs_max_mm", None)),
        "summary_fiducial_theta_max_deg": _safe_cfg_optional_float(raw.get("summary_fiducial_theta_max_deg", None)),
        "summary_fiducial_phi_abs_max_deg": _safe_cfg_optional_float(raw.get("summary_fiducial_phi_abs_max_deg", None)),
    }


def apply_task4_final_filter(
    df_input: pd.DataFrame,
    *,
    config: Mapping[str, object],
    apply_changes: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int | float]]:
    input_rows = int(len(df_input))
    if input_rows == 0:
        return df_input.copy(), pd.DataFrame(), {
            "input_rows": 0,
            "rows_affected": 0,
            "values_zeroed": 0,
            "rows_failed_fit_tt_min": 0,
            "rows_failed_nonzero_required": 0,
        }

    working = df_input.copy() if apply_changes else df_input
    summary: dict[str, int | float] = {
        "input_rows": input_rows,
        "rows_affected": 0,
        "values_zeroed": 0,
        "rows_failed_fit_tt_min": 0,
        "rows_failed_nonzero_required": 0,
    }
    final_mask = np.ones(input_rows, dtype=bool)
    fail_reason_parts = np.empty(input_rows, dtype=object)
    fail_reason_parts.fill("")

    final_filter_remove_small = _coerce_config_bool(config.get("final_filter_remove_small", False), default=False)
    final_filter_remove_small_eps = _task4_config_float(
        config,
        "final_filter_remove_small_eps",
        default=1e-7,
    )
    if final_filter_remove_small:
        small_mask = working.map(
            lambda x: isinstance(x, (int, float)) and x != 0 and abs(x) < final_filter_remove_small_eps
        )
        total_small = int(small_mask.sum().sum())
        summary["values_zeroed"] = total_small
        if apply_changes and total_small > 0:
            working = working.mask(small_mask, 0)

    fit_tt_min = int(config.get("final_filter_fit_tt_min", 10))
    fit_tt_series = get_task4_tt_series(working, preferred=TASK4_PRIMARY_TT_COLUMN)
    fit_tt_fail = ~(fit_tt_series >= fit_tt_min).to_numpy(dtype=bool, copy=False)
    summary["rows_failed_fit_tt_min"] = int(fit_tt_fail.sum())
    final_mask &= ~fit_tt_fail
    fail_reason_parts[fit_tt_fail] = np.where(
        fail_reason_parts[fit_tt_fail] == "",
        f"fit_tt<{fit_tt_min}",
        fail_reason_parts[fit_tt_fail] + f";fit_tt<{fit_tt_min}",
    )

    required_nonzero_cols = _task4_parse_filter_columns(
        config.get("final_filter_nonzero_cols", ["x", "y", "s", "t0", "theta", "phi"]),
        default=("x", "y", "s", "t0", "theta", "phi"),
    )
    required_nonzero_cols = [col for col in required_nonzero_cols if col in working.columns]
    if required_nonzero_cols:
        nonzero_mask = np.ones(input_rows, dtype=bool)
        zero_count_per_row = np.zeros(input_rows, dtype=int)
        primary_zero_col = np.full(input_rows, "", dtype=object)
        for col in required_nonzero_cols:
            col_values = pd.to_numeric(working[col], errors="coerce").to_numpy(dtype=float, copy=False)
            finite_mask = np.isfinite(col_values)
            nonzero_col_mask = finite_mask & (col_values != 0.0)
            nonzero_mask &= nonzero_col_mask
            zero_or_invalid = ~nonzero_col_mask
            zero_count_per_row += zero_or_invalid.astype(int)
            primary_assign_mask = (primary_zero_col == "") & zero_or_invalid
            primary_zero_col[primary_assign_mask] = col
        nonzero_fail = ~nonzero_mask
        summary["rows_failed_nonzero_required"] = int(nonzero_fail.sum())
        final_mask &= ~nonzero_fail
        fail_reason_parts[nonzero_fail] = np.where(
            fail_reason_parts[nonzero_fail] == "",
            "required_nonzero_violation",
            fail_reason_parts[nonzero_fail] + ";required_nonzero_violation",
        )
    else:
        zero_count_per_row = np.zeros(input_rows, dtype=int)
        primary_zero_col = np.full(input_rows, "", dtype=object)

    def _numeric_column_or_nan(column_name: str) -> np.ndarray:
        if column_name not in working.columns:
            return np.full(input_rows, np.nan, dtype=float)
        return pd.to_numeric(working[column_name], errors="coerce").to_numpy(dtype=float, copy=False)

    def _apply_numeric_range_filter(
        values: np.ndarray,
        *,
        left_limit: float | None,
        right_limit: float | None,
        summary_key: str,
        reason_key: str,
    ) -> None:
        nonlocal final_mask
        if left_limit is None and right_limit is None:
            return
        pass_mask = np.isfinite(values)
        if left_limit is not None:
            pass_mask &= values >= left_limit
        if right_limit is not None:
            pass_mask &= values <= right_limit
        fail_mask = ~pass_mask
        summary[f"rows_failed_{summary_key}"] = int(fail_mask.sum())
        final_mask &= ~fail_mask
        fail_reason_parts[fail_mask] = np.where(
            fail_reason_parts[fail_mask] == "",
            f"{reason_key}_out_of_range",
            fail_reason_parts[fail_mask] + f";{reason_key}_out_of_range",
        )

    variable_specs = (
        ("x", "final_filter_x_min", "final_filter_x_max"),
        ("y", "final_filter_y_min", "final_filter_y_max"),
        ("s", "final_filter_s_min", "final_filter_s_max"),
        ("t0", "final_filter_t0_min", "final_filter_t0_max"),
        ("theta", "final_filter_theta_min", "final_filter_theta_max"),
        ("phi", "final_filter_phi_min", "final_filter_phi_max"),
    )
    for variable_name, left_key, right_key in variable_specs:
        _apply_numeric_range_filter(
            _numeric_column_or_nan(variable_name),
            left_limit=_task4_parse_optional_float(config.get(left_key)),
            right_limit=_task4_parse_optional_float(config.get(right_key)),
            summary_key=f"{variable_name}_range",
            reason_key=variable_name,
        )

    rows_affected = int((~final_mask).sum())
    summary["rows_affected"] = rows_affected
    summary["flagged_rows"] = rows_affected
    if not apply_changes:
        return df_input, pd.DataFrame(), summary

    filtered_df = working.loc[final_mask].copy()
    rejected_df = working.loc[~final_mask].copy()
    if not rejected_df.empty:
        rejected_df["reject_stage"] = "final_filtering"
        rejected_df["reject_reason"] = fail_reason_parts[~final_mask]
        rejected_df["zero_count"] = zero_count_per_row[~final_mask]
        rejected_df["primary_zero_col"] = primary_zero_col[~final_mask]
    return filtered_df, rejected_df, summary


def _make_efficiency_curve(values, fired, bins):
    vals = np.asarray(values, dtype=float)
    fire = np.asarray(fired, dtype=float)
    centers = 0.5 * (bins[:-1] + bins[1:])
    num, _ = np.histogram(vals[fire > 0.5], bins=bins)
    den, _ = np.histogram(vals, bins=bins)
    with np.errstate(invalid="ignore", divide="ignore"):
        eff = np.where(den > 0, num / den, np.nan)
        unc = np.where(
            den > 0,
            np.sqrt(np.maximum(eff * (1.0 - eff) / np.maximum(den, 1), 0.0)),
            np.nan,
        )
    return {
        "centers": centers.astype(float),
        "eff": np.asarray(eff, dtype=float),
        "unc": np.asarray(unc, dtype=float),
        "den": np.asarray(den, dtype=float),
    }


def _histogram_bin_indices(values, bins):
    vals = np.asarray(values, dtype=float)
    out = np.full(vals.shape, -1, dtype=np.int32)
    if vals.size == 0 or len(bins) < 2:
        return out
    valid = np.isfinite(vals) & (vals >= float(bins[0])) & (vals <= float(bins[-1]))
    if not np.any(valid):
        return out
    out[valid] = np.digitize(vals[valid], bins[1:-1], right=False).astype(np.int32)
    return out


def _compute_efficiency_summary_bin_mask(centers, eff_vals, den_vals, axis_name, cfg_eff):
    valid = np.isfinite(centers) & np.isfinite(eff_vals) & np.isfinite(den_vals) & (den_vals > 0)
    if axis_name == "x":
        limit = cfg_eff.get("summary_fiducial_x_abs_max_mm", None)
        if limit is not None:
            valid &= np.abs(centers) <= float(limit)
    elif axis_name == "y":
        limit = cfg_eff.get("summary_fiducial_y_abs_max_mm", None)
        if limit is not None:
            valid &= np.abs(centers) <= float(limit)
    elif axis_name == "theta":
        limit = cfg_eff.get("summary_fiducial_theta_max_deg", None)
        if limit is not None:
            valid &= centers <= float(limit)
    elif axis_name == "phi":
        limit = cfg_eff.get("summary_fiducial_phi_abs_max_deg", None)
        if limit is not None:
            valid &= np.abs(centers) <= float(limit)
    return valid


def _extract_efficiency_summary_arrays(axis_payload, axis_name, cfg_eff):
    centers = np.asarray(axis_payload.get("centers", []), dtype=float)
    eff_vals = np.asarray(axis_payload.get("eff", []), dtype=float)
    unc_vals = np.asarray(axis_payload.get("unc", []), dtype=float)
    den_vals = np.asarray(axis_payload.get("den", []), dtype=float)
    valid = _compute_efficiency_summary_bin_mask(centers, eff_vals, den_vals, axis_name, cfg_eff)
    return centers, eff_vals, unc_vals, den_vals, valid


def _compute_efficiency_scalar_summary(axis_payload, axis_name, cfg_eff):
    centers, eff_vals, unc_vals, den_vals, valid = _extract_efficiency_summary_arrays(axis_payload, axis_name, cfg_eff)
    if not np.any(valid):
        return {"eff": np.nan, "unc": np.nan, "n_denom": 0, "n_bins_used": 0, "selected_center": np.nan}
    valid_centers = centers[valid]
    if axis_name in {"x", "y", "phi"}:
        selected_idx = int(np.argmin(np.abs(valid_centers)))
    else:
        selected_idx = 0
    global_idx = np.flatnonzero(valid)[selected_idx]
    return {
        "eff": float(eff_vals[global_idx]) if np.isfinite(eff_vals[global_idx]) else np.nan,
        "unc": float(unc_vals[global_idx]) if np.isfinite(unc_vals[global_idx]) else np.nan,
        "n_denom": int(den_vals[global_idx]) if np.isfinite(den_vals[global_idx]) else 0,
        "n_bins_used": int(np.sum(valid)),
        "selected_center": float(centers[global_idx]) if np.isfinite(centers[global_idx]) else np.nan,
    }


def _compute_robust_x_center_eff(axis_payload, cfg_eff):
    summary = _compute_efficiency_scalar_summary(axis_payload, "x", cfg_eff)
    eff = summary.get("eff", np.nan)
    return float(eff) if np.isfinite(eff) else np.nan


def _intersect_required_indices(*indices):
    if not indices or any(index is None for index in indices):
        return None
    intersection = pd.Index(indices[0])
    for index in indices[1:]:
        intersection = intersection.intersection(pd.Index(index), sort=False)
    return intersection


def _required_track_efficiency_hit_columns():
    return tuple(
        f"P{plane}_{suffix}"
        for plane in range(1, 5)
        for suffix in ("T_dif_final", "Y_final")
    )


def _extract_track_efficiency_hit_arrays(df_plot, tdiff_to_x):
    x_hits = np.column_stack(
        [
            pd.to_numeric(df_plot[f"P{plane}_T_dif_final"], errors="coerce").to_numpy(dtype=float) * float(tdiff_to_x)
            for plane in range(1, 5)
        ]
    )
    y_hits = np.column_stack(
        [
            pd.to_numeric(df_plot[f"P{plane}_Y_final"], errors="coerce").to_numpy(dtype=float)
            for plane in range(1, 5)
        ]
    )
    return x_hits, y_hits


def _fit_three_plane_telescope_projection(x_hits, y_hits, z_arr, test_plane_zero_idx):
    other_idx = [idx for idx in range(4) if idx != int(test_plane_zero_idx)]
    z_known = np.asarray(z_arr[other_idx], dtype=float)
    z_test = float(z_arr[int(test_plane_zero_idx)])
    z_mean = float(np.mean(z_known))
    z_delta = z_known - z_mean
    z_denom = float(np.sum(z_delta * z_delta))

    n_rows = int(x_hits.shape[0])
    out = {
        "x_pred": np.full(n_rows, np.nan, dtype=float),
        "y_pred": np.full(n_rows, np.nan, dtype=float),
        "theta_pred_deg": np.full(n_rows, np.nan, dtype=float),
        "phi_pred_deg": np.full(n_rows, np.nan, dtype=float),
        "valid": np.zeros(n_rows, dtype=bool),
    }
    if n_rows == 0 or not np.isfinite(z_denom) or z_denom <= 0.0:
        return out

    x_known = np.asarray(x_hits[:, other_idx], dtype=float)
    y_known = np.asarray(y_hits[:, other_idx], dtype=float)
    valid = np.isfinite(x_known).all(axis=1) & np.isfinite(y_known).all(axis=1)
    if not np.any(valid):
        return out

    x_fit = x_known[valid]
    y_fit = y_known[valid]
    x_mean = np.mean(x_fit, axis=1)
    y_mean = np.mean(y_fit, axis=1)
    slope_x = np.sum((x_fit - x_mean[:, None]) * z_delta[None, :], axis=1) / z_denom
    slope_y = np.sum((y_fit - y_mean[:, None]) * z_delta[None, :], axis=1) / z_denom
    intercept_x = x_mean - slope_x * z_mean
    intercept_y = y_mean - slope_y * z_mean

    out["x_pred"][valid] = intercept_x + slope_x * z_test
    out["y_pred"][valid] = intercept_y + slope_y * z_test
    out["theta_pred_deg"][valid] = np.degrees(np.arctan(np.hypot(slope_x, slope_y)))
    out["phi_pred_deg"][valid] = np.degrees(np.arctan2(slope_y, slope_x))
    out["valid"] = valid
    return out


def _select_robust_plateau_event_indices(
    axis_payload,
    *,
    cfg_eff,
    axis_values,
    bins,
    accepted_indices,
    axis_name,
    tolerance,
    center_eff,
    fired=None,
    fired_only=False,
):
    centers, eff_vals, _, den_vals, valid = _extract_efficiency_summary_arrays(axis_payload, axis_name, cfg_eff)
    if not np.any(valid) or not np.isfinite(center_eff):
        return None
    plateau_bins = valid & (np.abs(eff_vals - center_eff) <= float(tolerance))
    if not np.any(plateau_bins):
        return None
    bin_ids = _histogram_bin_indices(axis_values, bins)
    selected_mask = np.isin(bin_ids, np.flatnonzero(plateau_bins))
    if fired_only and fired is not None:
        selected_mask &= np.asarray(fired, dtype=float) > 0.5
    selected_indices = pd.Index(accepted_indices[selected_mask])
    return selected_indices if len(selected_indices) > 0 else None


def _select_efficiency_summary_event_indices(
    axis_payload,
    *,
    cfg_eff,
    axis_values,
    bins,
    accepted_indices,
    axis_name,
    fired=None,
    fired_only=False,
):
    summary = _compute_efficiency_scalar_summary(axis_payload, axis_name, cfg_eff)
    selected_center = summary.get("selected_center", np.nan)
    if not np.isfinite(selected_center):
        return None
    centers = np.asarray(axis_payload.get("centers", []), dtype=float)
    if centers.size == 0:
        return None
    selected_bin = int(np.argmin(np.abs(centers - selected_center)))
    bin_ids = _histogram_bin_indices(axis_values, bins)
    selected_mask = bin_ids == selected_bin
    if fired_only and fired is not None:
        selected_mask &= np.asarray(fired, dtype=float) > 0.5
    selected_indices = pd.Index(accepted_indices[selected_mask])
    return selected_indices if len(selected_indices) > 0 else None


def _resolve_efficiency_edges(
    *,
    cfg_eff,
    strip_half,
    width_half,
    theta_left_filter,
    theta_right_filter,
    phi_left_filter,
    phi_right_filter,
):
    x_min = _safe_cfg_float(cfg_eff.get("x_min_mm", None), -float(strip_half))
    x_max = _safe_cfg_float(cfg_eff.get("x_max_mm", None), float(strip_half))
    y_min = _safe_cfg_float(cfg_eff.get("y_min_mm", None), -float(width_half))
    y_max = _safe_cfg_float(cfg_eff.get("y_max_mm", None), float(width_half))
    theta_min_deg = _safe_cfg_float(cfg_eff.get("theta_min_deg", None), float(np.degrees(theta_left_filter)))
    theta_max_deg = _safe_cfg_float(cfg_eff.get("theta_max_deg", None), float(np.degrees(theta_right_filter)))
    phi_min_deg = _safe_cfg_float(cfg_eff.get("phi_min_deg", None), float(np.degrees(phi_left_filter)))
    phi_max_deg = _safe_cfg_float(cfg_eff.get("phi_max_deg", None), float(np.degrees(phi_right_filter)))

    x_min = max(-float(strip_half), min(x_min, float(strip_half)))
    x_max = max(-float(strip_half), min(x_max, float(strip_half)))
    y_min = max(-float(width_half), min(y_min, float(width_half)))
    y_max = max(-float(width_half), min(y_max, float(width_half)))
    if x_max <= x_min:
        x_min, x_max = -float(strip_half), float(strip_half)
    if y_max <= y_min:
        y_min, y_max = -float(width_half), float(width_half)
    if theta_max_deg <= theta_min_deg:
        theta_min_deg = float(np.degrees(theta_left_filter))
        theta_max_deg = float(np.degrees(theta_right_filter))
    if phi_max_deg <= phi_min_deg:
        phi_min_deg = float(np.degrees(phi_left_filter))
        phi_max_deg = float(np.degrees(phi_right_filter))

    return {
        "x": np.linspace(x_min, x_max, int(cfg_eff["x_bin_count"]) + 1),
        "y": np.linspace(y_min, y_max, int(cfg_eff["y_bin_count"]) + 1),
        "theta": np.linspace(theta_min_deg, theta_max_deg, int(cfg_eff["theta_bin_count"]) + 1),
        "phi": np.linspace(phi_min_deg, phi_max_deg, int(cfg_eff["phi_bin_count"]) + 1),
    }


def _compute_track_based_efficiency_payload(
    df_plot,
    *,
    cfg_eff,
    cfg_fiducial,
    z_positions,
    tdiff_to_x,
    strip_half,
    width_half,
    theta_left_filter,
    theta_right_filter,
    phi_left_filter,
    phi_right_filter,
    y_pos_p13,
    y_pos_p24,
):
    edges = _resolve_efficiency_edges(
        cfg_eff=cfg_eff,
        strip_half=strip_half,
        width_half=width_half,
        theta_left_filter=theta_left_filter,
        theta_right_filter=theta_right_filter,
        phi_left_filter=phi_left_filter,
        phi_right_filter=phi_right_filter,
    )
    plane_pool_tt = {
        1: [234, 1234],
        2: [134, 1234],
        3: [124, 1234],
        4: [123, 1234],
    }
    payload = {
        "available": False,
        "reason": "",
        "config": dict(cfg_eff),
        "edges": edges,
        "plane_results": {},
        "trigger_source": "",
        "pool_source": "",
    }

    trigger_source = "fit_tt"
    payload["trigger_source"] = trigger_source
    pool_source = trigger_source
    payload["pool_source"] = pool_source

    required = tuple(_required_track_efficiency_hit_columns()) + (trigger_source, pool_source)
    missing = [col for col in required if col not in df_plot.columns]
    if missing:
        payload["reason"] = f"missing_required_columns:{','.join(missing)}"
        return payload

    z_arr = np.asarray(z_positions, dtype=float)
    x_hits_all, y_hits_all = _extract_track_efficiency_hit_arrays(df_plot, tdiff_to_x)
    dtt_all = pd.to_numeric(df_plot[trigger_source], errors="coerce").fillna(0).to_numpy(dtype=np.int32)
    pool_tt_all = pd.to_numeric(df_plot[pool_source], errors="coerce").fillna(0).to_numpy(dtype=np.int32)
    charge_series, _ = _resolve_task4_total_event_charge_series(df_plot)
    if charge_series is not None:
        charge_all = charge_series.to_numpy(dtype=float, copy=False)
    else:
        charge_all = np.full(len(df_plot), np.nan, dtype=float)

    any_plane_available = False
    for plane in range(1, 5):
        x_scalar_summary = _compute_efficiency_scalar_summary({}, "x", cfg_eff)
        y_reference = y_pos_p13 if (plane - 1) % 2 == 0 else y_pos_p24
        plane_result = {
            "plane": int(plane),
            "overall_eff": np.nan,
            "n_denom": 0,
            "y_reference": np.asarray(y_reference, dtype=float),
            "eff_2d": np.full((len(edges["x"]) - 1, len(edges["y"]) - 1), np.nan, dtype=float),
            "x": _make_efficiency_curve(np.asarray([], dtype=float), np.asarray([], dtype=float), edges["x"]),
            "y": _make_efficiency_curve(np.asarray([], dtype=float), np.asarray([], dtype=float), edges["y"]),
            "theta": _make_efficiency_curve(np.asarray([], dtype=float), np.asarray([], dtype=float), edges["theta"]),
            "phi": _make_efficiency_curve(np.asarray([], dtype=float), np.asarray([], dtype=float), edges["phi"]),
            "eff_theta_phi": np.full((len(edges["theta"]) - 1, len(edges["phi"]) - 1), np.nan, dtype=float),
            "scalar_summary": {
                "x": {"eff": np.nan, "unc": np.nan, "n_denom": 0, "n_bins_used": 0, "selected_center": np.nan},
                "y": {"eff": np.nan, "unc": np.nan, "n_denom": 0, "n_bins_used": 0, "selected_center": np.nan},
                "theta": {"eff": np.nan, "unc": np.nan, "n_denom": 0, "n_bins_used": 0, "selected_center": np.nan},
                "phi": {"eff": np.nan, "unc": np.nan, "n_denom": 0, "n_bins_used": 0, "selected_center": np.nan},
            },
            "accepted_indices": None,
            "robust_x_summary_accepted_indices": None,
            "robust_x_summary_fired_indices": None,
            "robust_x_plateau_accepted_indices": None,
            "robust_x_plateau_fired_indices": None,
            "robust_y_plateau_accepted_indices": None,
            "robust_y_plateau_fired_indices": None,
            "robust_phi_plateau_accepted_indices": None,
            "robust_phi_plateau_fired_indices": None,
            "robust_x_center_eff": np.nan,
            "robust_xyphi_accepted_indices": None,
            "robust_xyphi_fired_indices": None,
            "robust_xyphi_eff": np.nan,
        }

        projection = _fit_three_plane_telescope_projection(x_hits_all, y_hits_all, z_arr, plane - 1)
        pool_mask = np.isin(pool_tt_all, plane_pool_tt[plane]) & projection["valid"]
        if int(np.sum(pool_mask)) < int(cfg_eff["min_pool_events"]):
            payload["plane_results"][plane] = plane_result
            continue

        x_pred = projection["x_pred"][pool_mask]
        y_pred = projection["y_pred"][pool_mask]
        theta_pred_deg = projection["theta_pred_deg"][pool_mask]
        phi_pred_deg = projection["phi_pred_deg"][pool_mask]
        charge_pred = charge_all[pool_mask]
        fired = (dtt_all[pool_mask] == 1234).astype(float)

        accepted_region = (
            np.isfinite(x_pred)
            & np.isfinite(y_pred)
            & (x_pred >= -float(width_half))
            & (x_pred <= float(width_half))
            & (y_pred >= -float(width_half))
            & (y_pred <= float(width_half))
        )
        radius_max_mm = cfg_fiducial.get("radius_max_mm", None)
        if radius_max_mm is not None:
            accepted_region &= np.hypot(x_pred, y_pred) <= float(radius_max_mm)
        charge_left = cfg_fiducial.get("charge_event_left", None)
        charge_right = cfg_fiducial.get("charge_event_right", None)
        if charge_left is not None or charge_right is not None:
            charge_pass = np.isfinite(charge_pred)
            if charge_left is not None:
                charge_pass &= charge_pred >= float(charge_left)
            if charge_right is not None:
                charge_pass &= charge_pred <= float(charge_right)
            accepted_region &= charge_pass

        theta_left_deg = cfg_fiducial.get("theta_left_deg", None)
        theta_right_deg = cfg_fiducial.get("theta_right_deg", None)
        if theta_left_deg is not None or theta_right_deg is not None:
            theta_pass = np.isfinite(theta_pred_deg)
            if theta_left_deg is not None:
                theta_pass &= theta_pred_deg >= float(theta_left_deg)
            if theta_right_deg is not None:
                theta_pass &= theta_pred_deg <= float(theta_right_deg)
            accepted_region &= theta_pass

        accepted_theta = accepted_region & np.isfinite(theta_pred_deg)
        accepted_phi = accepted_region & np.isfinite(phi_pred_deg)
        accepted_theta_phi = accepted_theta & np.isfinite(phi_pred_deg)

        x_acc = x_pred[accepted_region]
        y_acc = y_pred[accepted_region]
        fired_acc = fired[accepted_region]
        accepted_index = df_plot.index[pool_mask][accepted_region]
        theta_acc = theta_pred_deg[accepted_theta]
        fired_theta = fired[accepted_theta]
        phi_acc = phi_pred_deg[accepted_phi]
        fired_phi = fired[accepted_phi]
        theta_map_acc = theta_pred_deg[accepted_theta_phi]
        phi_map_acc = phi_pred_deg[accepted_theta_phi]
        fired_theta_phi = fired[accepted_theta_phi]

        plane_result["n_denom"] = int(len(fired_acc))
        plane_result["accepted_indices"] = pd.Index(accepted_index)
        if len(fired_acc) > 0:
            plane_result["overall_eff"] = float(np.mean(fired_acc) * 100.0)

        if len(fired_acc) >= int(cfg_eff["min_accepted_events"]):
            num_2d, _, _ = np.histogram2d(
                x_acc[fired_acc > 0.5],
                y_acc[fired_acc > 0.5],
                bins=[edges["x"], edges["y"]],
            )
            den_2d, _, _ = np.histogram2d(x_acc, y_acc, bins=[edges["x"], edges["y"]])
            with np.errstate(invalid="ignore", divide="ignore"):
                plane_result["eff_2d"] = np.where(den_2d > 0, num_2d / den_2d, np.nan)

            plane_result["x"] = _make_efficiency_curve(x_acc, fired_acc, edges["x"])
            plane_result["y"] = _make_efficiency_curve(y_acc, fired_acc, edges["y"])
            x_scalar_summary = _compute_efficiency_scalar_summary(plane_result["x"], "x", cfg_eff)
            plane_result["robust_x_center_eff"] = float(x_scalar_summary.get("eff", np.nan))
            plane_result["robust_x_summary_accepted_indices"] = _select_efficiency_summary_event_indices(
                plane_result["x"],
                cfg_eff=cfg_eff,
                axis_values=x_acc,
                bins=edges["x"],
                accepted_indices=accepted_index,
                axis_name="x",
            )
            plane_result["robust_x_summary_fired_indices"] = _select_efficiency_summary_event_indices(
                plane_result["x"],
                cfg_eff=cfg_eff,
                axis_values=x_acc,
                bins=edges["x"],
                accepted_indices=accepted_index,
                axis_name="x",
                fired=fired_acc,
                fired_only=True,
            )
            plane_result["robust_x_plateau_accepted_indices"] = _select_robust_plateau_event_indices(
                plane_result["x"],
                cfg_eff=cfg_eff,
                axis_values=x_acc,
                bins=edges["x"],
                accepted_indices=accepted_index,
                axis_name="x",
                tolerance=_ROBUST_EFFICIENCY_PLATEAU_TOLERANCE,
                center_eff=plane_result["robust_x_center_eff"],
            )
            plane_result["robust_x_plateau_fired_indices"] = _select_robust_plateau_event_indices(
                plane_result["x"],
                cfg_eff=cfg_eff,
                axis_values=x_acc,
                bins=edges["x"],
                accepted_indices=accepted_index,
                axis_name="x",
                tolerance=_ROBUST_EFFICIENCY_PLATEAU_TOLERANCE,
                center_eff=plane_result["robust_x_center_eff"],
                fired=fired_acc,
                fired_only=True,
            )
            any_plane_available = True

        if len(fired_theta) >= int(cfg_eff["min_accepted_events"]):
            plane_result["theta"] = _make_efficiency_curve(theta_acc, fired_theta, edges["theta"])
            any_plane_available = True

        if len(fired_phi) >= int(cfg_eff["min_accepted_events"]):
            plane_result["phi"] = _make_efficiency_curve(phi_acc, fired_phi, edges["phi"])
            any_plane_available = True

        if len(fired_theta_phi) >= int(cfg_eff["min_accepted_events"]):
            num_theta_phi, _, _ = np.histogram2d(
                theta_map_acc[fired_theta_phi > 0.5],
                phi_map_acc[fired_theta_phi > 0.5],
                bins=[edges["theta"], edges["phi"]],
            )
            den_theta_phi, _, _ = np.histogram2d(
                theta_map_acc,
                phi_map_acc,
                bins=[edges["theta"], edges["phi"]],
            )
            with np.errstate(invalid="ignore", divide="ignore"):
                plane_result["eff_theta_phi"] = np.where(den_theta_phi > 0, num_theta_phi / den_theta_phi, np.nan)
            any_plane_available = True

        y_scalar_summary = _compute_efficiency_scalar_summary(plane_result.get("y", {}), "y", cfg_eff)
        theta_scalar_summary = _compute_efficiency_scalar_summary(plane_result.get("theta", {}), "theta", cfg_eff)
        phi_scalar_summary = _compute_efficiency_scalar_summary(plane_result.get("phi", {}), "phi", cfg_eff)
        plane_result["scalar_summary"] = {
            "x": x_scalar_summary,
            "y": y_scalar_summary,
            "theta": theta_scalar_summary,
            "phi": phi_scalar_summary,
        }
        plane_result["robust_x_center_eff"] = float(plane_result["scalar_summary"]["x"].get("eff", np.nan))
        plane_result["robust_y_plateau_accepted_indices"] = _select_robust_plateau_event_indices(
            plane_result.get("y", {}),
            cfg_eff=cfg_eff,
            axis_values=y_acc,
            bins=edges["y"],
            accepted_indices=accepted_index,
            axis_name="y",
            tolerance=_ROBUST_EFFICIENCY_PLATEAU_TOLERANCE,
            center_eff=y_scalar_summary.get("eff", np.nan),
        )
        plane_result["robust_y_plateau_fired_indices"] = _select_robust_plateau_event_indices(
            plane_result.get("y", {}),
            cfg_eff=cfg_eff,
            axis_values=y_acc,
            bins=edges["y"],
            accepted_indices=accepted_index,
            axis_name="y",
            tolerance=_ROBUST_EFFICIENCY_PLATEAU_TOLERANCE,
            center_eff=y_scalar_summary.get("eff", np.nan),
            fired=fired_acc,
            fired_only=True,
        )
        plane_result["robust_phi_plateau_accepted_indices"] = _select_robust_plateau_event_indices(
            plane_result.get("phi", {}),
            cfg_eff=cfg_eff,
            axis_values=phi_acc,
            bins=edges["phi"],
            accepted_indices=pd.Index(df_plot.index[pool_mask][accepted_phi]),
            axis_name="phi",
            tolerance=_ROBUST_EFFICIENCY_PLATEAU_TOLERANCE,
            center_eff=phi_scalar_summary.get("eff", np.nan),
        )
        plane_result["robust_phi_plateau_fired_indices"] = _select_robust_plateau_event_indices(
            plane_result.get("phi", {}),
            cfg_eff=cfg_eff,
            axis_values=phi_acc,
            bins=edges["phi"],
            accepted_indices=pd.Index(df_plot.index[pool_mask][accepted_phi]),
            axis_name="phi",
            tolerance=_ROBUST_EFFICIENCY_PLATEAU_TOLERANCE,
            center_eff=phi_scalar_summary.get("eff", np.nan),
            fired=fired_phi,
            fired_only=True,
        )
        plane_result["robust_xyphi_accepted_indices"] = _intersect_required_indices(
            plane_result.get("robust_x_plateau_accepted_indices", None),
            plane_result.get("robust_y_plateau_accepted_indices", None),
            plane_result.get("robust_phi_plateau_accepted_indices", None),
        )
        plane_result["robust_xyphi_fired_indices"] = _intersect_required_indices(
            plane_result.get("robust_x_plateau_fired_indices", None),
            plane_result.get("robust_y_plateau_fired_indices", None),
            plane_result.get("robust_phi_plateau_fired_indices", None),
        )
        if plane_result["robust_xyphi_accepted_indices"] is not None:
            robust_xyphi_n_denom = int(len(plane_result["robust_xyphi_accepted_indices"]))
            robust_xyphi_fired_index = plane_result.get("robust_xyphi_fired_indices", None)
            robust_xyphi_n_num = int(len(robust_xyphi_fired_index)) if robust_xyphi_fired_index is not None else 0
            if robust_xyphi_n_denom > 0:
                plane_result["robust_xyphi_eff"] = float(robust_xyphi_n_num / robust_xyphi_n_denom)

        payload["plane_results"][plane] = plane_result

    payload["available"] = bool(any_plane_available)
    if not payload["available"] and not payload["reason"]:
        payload["reason"] = "no_planes_with_minimum_statistics"
    return payload


def _resolve_track_efficiency_representative(plane_result):
    if not isinstance(plane_result, dict):
        return (np.nan, "missing", None, None)

    xyphi_eff = plane_result.get("robust_xyphi_eff", np.nan)
    xyphi_accepted = plane_result.get("robust_xyphi_accepted_indices", None)
    xyphi_fired = plane_result.get("robust_xyphi_fired_indices", None)
    if np.isfinite(xyphi_eff):
        return (
            float(xyphi_eff),
            "xyphi_plateau",
            pd.Index(xyphi_accepted) if xyphi_accepted is not None else None,
            pd.Index(xyphi_fired) if xyphi_fired is not None else None,
        )

    x_summary_eff = plane_result.get("robust_x_center_eff", np.nan)
    x_summary_accepted = plane_result.get("robust_x_summary_accepted_indices", None)
    x_summary_fired = plane_result.get("robust_x_summary_fired_indices", None)
    if np.isfinite(x_summary_eff):
        return (
            float(x_summary_eff),
            "x_summary",
            pd.Index(x_summary_accepted) if x_summary_accepted is not None else None,
            pd.Index(x_summary_fired) if x_summary_fired is not None else None,
        )

    overall_eff_percent = plane_result.get("overall_eff", np.nan)
    if np.isfinite(overall_eff_percent):
        return (float(overall_eff_percent) / 100.0, "overall", None, None)

    return (np.nan, "missing", None, None)


_TRACK_EFF_REPRESENTATIVE_LINESTYLE = (0, (10, 3))
_TRACK_EFF_SIMULATION_LINESTYLE = (0, (3, 2))


def _format_task4_percent_label(value: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = np.nan
    if not np.isfinite(numeric):
        return "n/a"
    if abs(numeric) <= 1.0:
        numeric *= 100.0
    return f"{numeric:.1f}%"


def _format_track_efficiency_representative_label(method: str) -> str:
    mapping = {
        "xyphi_plateau": "fid representative x/y/phi plateau",
        "x_summary": "fid representative x-summary",
        "overall": "fid overall",
        "missing": "fid representative",
    }
    return mapping.get(str(method), "fid representative")


def _plot_track_efficiency_curve_panel(
    axis,
    *,
    axis_payload,
    axis_payload_full,
    n_denom,
    n_denom_full,
    overall_eff,
    overall_eff_full,
    representative_eff,
    representative_label,
    sim_eff_percent,
    plane_color,
    xlabel,
    xlim,
    x_reference_values=(),
    label_fontsize=8,
    legend_fontsize=7,
):
    centers = np.asarray(axis_payload.get("centers", []), dtype=float)
    eff_vals = np.asarray(axis_payload.get("eff", []), dtype=float)
    unc_vals = np.asarray(axis_payload.get("unc", []), dtype=float)
    den_vals = np.asarray(axis_payload.get("den", []), dtype=float)
    valid = np.isfinite(eff_vals) & (den_vals > 0)

    centers_full = np.asarray(axis_payload_full.get("centers", []), dtype=float)
    eff_vals_full = np.asarray(axis_payload_full.get("eff", []), dtype=float)
    unc_vals_full = np.asarray(axis_payload_full.get("unc", []), dtype=float)
    den_vals_full = np.asarray(axis_payload_full.get("den", []), dtype=float)
    valid_full = np.isfinite(eff_vals_full) & (den_vals_full > 0)

    if np.any(valid_full):
        axis.errorbar(
            centers_full[valid_full],
            eff_vals_full[valid_full],
            yerr=unc_vals_full[valid_full],
            fmt="o--",
            ms=3.5,
            color="0.45",
            alpha=0.80,
            label=f"no fid  (n={int(n_denom_full)}, {_format_task4_percent_label(overall_eff_full)})",
        )
    if np.any(valid):
        axis.errorbar(
            centers[valid],
            eff_vals[valid],
            yerr=unc_vals[valid],
            fmt="o-",
            ms=4,
            color=plane_color,
            alpha=0.85,
            label=f"fiducial  (n={int(n_denom)}, {_format_task4_percent_label(overall_eff)})",
        )
    if np.isfinite(representative_eff):
        representative_line = axis.axhline(
            float(representative_eff),
            color=plane_color,
            lw=2.0,
            ls=_TRACK_EFF_REPRESENTATIVE_LINESTYLE,
            alpha=0.95,
            zorder=4,
            label=f"{representative_label}  {_format_task4_percent_label(representative_eff)}",
        )
        representative_line.set_path_effects(
            [
                path_effects.Stroke(linewidth=4.2, foreground="white", alpha=0.95),
                path_effects.Normal(),
            ]
        )
    for x_reference in x_reference_values:
        if np.isfinite(x_reference):
            axis.axvline(float(x_reference), color="lightgray", lw=0.9, ls="--", alpha=0.8)
    if np.isfinite(sim_eff_percent):
        axis.axhline(
            float(sim_eff_percent) / 100.0,
            color="black",
            lw=1.0,
            ls=_TRACK_EFF_SIMULATION_LINESTYLE,
            alpha=0.75,
            zorder=3,
            label=f"simulation  {_format_task4_percent_label(sim_eff_percent)}",
        )
    axis.set_ylim(0, 1.08)
    axis.set_xlim(*xlim)
    axis.set_xlabel(xlabel, fontsize=label_fontsize)
    axis.set_ylabel("Efficiency", fontsize=label_fontsize)
    axis.grid(True, alpha=0.3)
    handles, labels = axis.get_legend_handles_labels()
    if handles:
        axis.legend(fontsize=legend_fontsize)


def render_track_efficiency_large_plot(
    *,
    payload,
    payload_fullplane,
    cfg_fiducial,
    cfg_eff,
    strip_half,
    width_half,
    simulated_efficiencies,
    output_png: Path,
    filename_base: str,
    theta_max_deg: float,
    radius_max_mm: float,
) -> None:
    edges_eff = payload["edges"] if bool(payload.get("available", False)) else payload_fullplane["edges"]
    fig, axes = plt.subplots(6, 4, figsize=(20, 24), squeeze=False)
    sim_eff_percent_values = [
        float(value) * 100.0 if np.isfinite(value) else np.nan
        for value in list(simulated_efficiencies or [])
    ]
    fiducial_active = bool(np.isfinite(radius_max_mm) or np.isfinite(theta_max_deg))

    for plane_idx, plane in enumerate(range(1, 5)):
        plane_result = payload["plane_results"].get(plane, {})
        plane_result_full = payload_fullplane["plane_results"].get(plane, {})
        ax_xy = axes[0][plane_idx]
        ax_y = axes[1][plane_idx]
        ax_x = axes[2][plane_idx]
        ax_theta = axes[3][plane_idx]
        ax_phi = axes[4][plane_idx]
        ax_theta_phi = axes[5][plane_idx]

        n_denom = int(plane_result.get("n_denom", 0) or 0)
        n_denom_full = int(plane_result_full.get("n_denom", 0) or 0)
        if max(n_denom, n_denom_full) < int(cfg_eff["min_accepted_events"]):
            for axis in (ax_xy, ax_y, ax_x, ax_theta, ax_phi, ax_theta_phi):
                axis.set_visible(False)
            continue

        overall_eff = plane_result.get("overall_eff", np.nan)
        overall_eff_full = plane_result_full.get("overall_eff", np.nan)
        representative_eff, representative_method, _, _ = _resolve_track_efficiency_representative(plane_result)
        representative_label = _format_track_efficiency_representative_label(representative_method)
        sim_eff_percent = (
            float(sim_eff_percent_values[plane - 1])
            if plane - 1 < len(sim_eff_percent_values)
            else np.nan
        )
        plane_color = f"C{plane - 1}"
        y_reference = np.asarray(
            plane_result_full.get("y_reference", plane_result.get("y_reference", [])),
            dtype=float,
        )

        eff_xy = np.asarray(
            plane_result_full.get("eff_2d", plane_result.get("eff_2d", np.empty((0, 0)))),
            dtype=float,
        )
        im_xy = ax_xy.imshow(
            eff_xy.T,
            origin="lower",
            aspect="auto",
            extent=[
                float(edges_eff["x"][0]),
                float(edges_eff["x"][-1]),
                float(edges_eff["y"][0]),
                float(edges_eff["y"][-1]),
            ],
            vmin=0.0,
            vmax=1.0,
            cmap="RdYlGn",
        )
        fig.colorbar(im_xy, ax=ax_xy, label="efficiency", fraction=0.045, pad=0.02)
        for sy in y_reference:
            ax_xy.axhline(float(sy), color="cyan", lw=0.7, ls="--", alpha=0.7)
        if fiducial_active and np.isfinite(radius_max_mm) and radius_max_mm > 0.0:
            ax_xy.add_patch(
                Circle(
                    (0.0, 0.0),
                    float(radius_max_mm),
                    fill=False,
                    edgecolor="black",
                    linestyle="--",
                    linewidth=1.1,
                    alpha=0.85,
                )
            )
        ax_xy.set_xlabel("Projected X (mm)", fontsize=8)
        ax_xy.set_ylabel("Projected Y (mm)", fontsize=8)
        ax_xy.set_title(
            (
                f"Plane {plane}\n"
                f"fid={_format_task4_percent_label(overall_eff)}  "
                f"full={_format_task4_percent_label(overall_eff_full)}"
                + (f"  sim={_format_task4_percent_label(sim_eff_percent)}" if np.isfinite(sim_eff_percent) else "")
                + f"\n(n_fid={n_denom}, n_full={n_denom_full})"
            ),
            fontsize=9,
        )

        _plot_track_efficiency_curve_panel(
            ax_y,
            axis_payload=plane_result.get("y", {}),
            axis_payload_full=plane_result_full.get("y", {}),
            n_denom=n_denom,
            n_denom_full=n_denom_full,
            overall_eff=overall_eff,
            overall_eff_full=overall_eff_full,
            representative_eff=representative_eff,
            representative_label=representative_label,
            sim_eff_percent=sim_eff_percent,
            plane_color=plane_color,
            xlabel="Projected Y (mm)",
            xlim=(-float(width_half), float(width_half)),
            x_reference_values=y_reference,
        )
        _plot_track_efficiency_curve_panel(
            ax_x,
            axis_payload=plane_result.get("x", {}),
            axis_payload_full=plane_result_full.get("x", {}),
            n_denom=n_denom,
            n_denom_full=n_denom_full,
            overall_eff=overall_eff,
            overall_eff_full=overall_eff_full,
            representative_eff=representative_eff,
            representative_label=representative_label,
            sim_eff_percent=sim_eff_percent,
            plane_color=plane_color,
            xlabel="Projected X (mm)",
            xlim=(-float(strip_half), float(strip_half)),
        )
        _plot_track_efficiency_curve_panel(
            ax_theta,
            axis_payload=plane_result.get("theta", {}),
            axis_payload_full=plane_result_full.get("theta", {}),
            n_denom=n_denom,
            n_denom_full=n_denom_full,
            overall_eff=overall_eff,
            overall_eff_full=overall_eff_full,
            representative_eff=representative_eff,
            representative_label=representative_label,
            sim_eff_percent=sim_eff_percent,
            plane_color=plane_color,
            xlabel="theta (deg)",
            xlim=(float(edges_eff["theta"][0]), float(edges_eff["theta"][-1])),
        )
        _plot_track_efficiency_curve_panel(
            ax_phi,
            axis_payload=plane_result.get("phi", {}),
            axis_payload_full=plane_result_full.get("phi", {}),
            n_denom=n_denom,
            n_denom_full=n_denom_full,
            overall_eff=overall_eff,
            overall_eff_full=overall_eff_full,
            representative_eff=representative_eff,
            representative_label=representative_label,
            sim_eff_percent=sim_eff_percent,
            plane_color=plane_color,
            xlabel="phi (deg)",
            xlim=(float(edges_eff["phi"][0]), float(edges_eff["phi"][-1])),
        )

        eff_theta_phi = np.asarray(
            plane_result_full.get("eff_theta_phi", plane_result.get("eff_theta_phi", np.empty((0, 0)))),
            dtype=float,
        )
        im_theta_phi = ax_theta_phi.imshow(
            eff_theta_phi.T,
            origin="lower",
            aspect="auto",
            extent=[
                float(edges_eff["theta"][0]),
                float(edges_eff["theta"][-1]),
                float(edges_eff["phi"][0]),
                float(edges_eff["phi"][-1]),
            ],
            vmin=0.0,
            vmax=1.0,
            cmap="RdYlGn",
        )
        fig.colorbar(im_theta_phi, ax=ax_theta_phi, label="efficiency", fraction=0.045, pad=0.02)
        theta_left_deg = cfg_fiducial.get("theta_left_deg", None)
        theta_right_deg = cfg_fiducial.get("theta_right_deg", None)
        if theta_left_deg is not None:
            ax_theta_phi.axvline(float(theta_left_deg), color="black", lw=1.1, ls="--", alpha=0.85)
        if theta_right_deg is not None:
            ax_theta_phi.axvline(float(theta_right_deg), color="black", lw=1.1, ls="--", alpha=0.85)
        ax_theta_phi.set_xlabel("theta (deg)", fontsize=8)
        ax_theta_phi.set_ylabel("phi (deg)", fontsize=8)

    plt.suptitle(
        "Large track-based efficiency diagnostic (telescope method)\n"
        f"Rows: XY map, eff(Y), eff(X), eff(theta), eff(phi), theta-phi map\n"
        f"Selected scan point for {filename_base}: theta_max={theta_max_deg:.1f} deg, radius_max={radius_max_mm:.1f} mm\n"
        + (
            "Solid colour = active fiducial efficiency curve, dashed gray = no-fid/full-plane reference"
            if fiducial_active
            else "No fiducial cut is active: solid and dashed-gray references should overlap"
        )
        + "; dashed plane-colour = fid representative efficiency"
        + ("; dashed black = simulation overall reference" if sim_eff_percent_values else ""),
        fontsize=11,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=200)
    plt.close(fig)


def select_freshest_task5_file(directory: Path) -> Path:
    candidates = sorted(directory.glob("*.parquet"))
    if not candidates:
        raise FileNotFoundError(f"No parquet files found in {directory}")
    # Freshest follows the prompt convention: most recently modified file.
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


def load_task4_effective_config(station: str) -> dict[str, object]:
    config_root = get_master_config_root()
    config_file_path = (
        config_root
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / "TASK_4"
        / "config_task_4.yaml"
    )
    parameter_config_file_path = (
        config_root
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / "TASK_4"
        / "config_parameters_task_4.csv"
    )
    filter_parameter_config_file_path = (
        config_root
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / "TASK_4"
        / "config_filter_parameters_task_4.csv"
    )
    fallback_parameter_config_file_path = (
        config_root
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / "config_parameters.csv"
    )

    with config_file_path.open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    filter_parameter_config_file_path = filter_parameter_config_file_path.with_name(
        str(config.get("filter_parameter_config_csv", filter_parameter_config_file_path.name))
    )

    use_filter_parameter_config = bool(config.get("use_filter_parameter_config", True))
    (
        filter_parameter_declared_keys,
        filter_parameter_overrides,
        filter_parameter_config_loaded,
    ) = load_step1_filter_parameter_state(
        filter_parameter_config_file_path,
        station,
        enabled=use_filter_parameter_config,
        warn_if_missing=True,
        log_fn=lambda *args, **kwargs: None,
    )

    config = apply_step1_task_parameter_overrides(
        config_obj=config,
        station_id=station,
        task_parameter_path=str(parameter_config_file_path),
        fallback_parameter_path=str(fallback_parameter_config_file_path),
        task_number=4,
        log_fn=lambda *args, **kwargs: None,
        exclude_keys=filter_parameter_declared_keys,
    )
    config = apply_step1_master_overrides(
        config_obj=config,
        master_config_root=config_root,
        log_fn=lambda *args, **kwargs: None,
    )
    if filter_parameter_config_loaded:
        config.update(filter_parameter_overrides)
    return config


def build_task4_runtime_geometry(config: Mapping[str, object], z_positions: list[float]) -> dict[str, object]:
    det_phi_filter_abs = abs(float(config.get("det_phi_filter_abs", config.get("det_phi_right_filter", math.pi))))
    y_width_p13 = np.array(
        [
            float(config["wide_strip"]),
            float(config["wide_strip"]),
            float(config["wide_strip"]),
            float(config["narrow_strip"]),
        ],
        dtype=float,
    )
    y_width_p24 = np.array(
        [
            float(config["narrow_strip"]),
            float(config["wide_strip"]),
            float(config["wide_strip"]),
            float(config["wide_strip"]),
        ],
        dtype=float,
    )
    total_width = float(np.sum(y_width_p13))
    strip_speed = float(config["strip_speed_factor_of_c"]) * (c / 1_000_000.0)
    strip_length = float(config["strip_length"])
    return {
        "z_positions": np.asarray(z_positions, dtype=float),
        "tdiff_to_x": float(strip_speed),
        "strip_half": float(strip_length / 2.0),
        "width_half": float(total_width / 2.0),
        "theta_left_filter": float(config["det_theta_left_filter"]),
        "theta_right_filter": float(config["det_theta_right_filter"]),
        "phi_left_filter": float(-det_phi_filter_abs),
        "phi_right_filter": float(det_phi_filter_abs),
        "y_pos_p13": np.asarray(y_pos(y_width_p13), dtype=float),
        "y_pos_p24": np.asarray(y_pos(y_width_p24), dtype=float),
    }


def build_scan_fiducial_cfg(theta_max: float, r_max: float) -> dict[str, object]:
    return {
        "charge_event_left": None,
        "charge_event_right": None,
        "theta_left_deg": 0.0,
        "theta_right_deg": float(theta_max),
        # The scan-specific fiducial region is a circle in the x/y plane.
        "radius_max_mm": float(r_max),
    }


def build_fullplane_fiducial_cfg() -> dict[str, object]:
    return {
        "charge_event_left": None,
        "charge_event_right": None,
        "theta_left_deg": None,
        "theta_right_deg": None,
        "radius_max_mm": None,
    }


def build_scan_row(
    *,
    payload: Mapping[str, object],
    df_events: pd.DataFrame,
    denominator_seconds: float,
    filename_base: str,
    execution_timestamp: str,
    param_hash: str,
    theta_max: float,
    r_max: float,
    simulated_efficiencies: list[float] | None,
) -> dict[str, object]:
    plane_results = payload.get("plane_results", {}) if isinstance(payload, Mapping) else {}
    row: dict[str, object] = {
        "filename_base": filename_base,
        "execution_timestamp": execution_timestamp,
        "param_hash": param_hash,
        "theta_max": float(theta_max),
        "r_max": float(r_max),
    }

    plane_fiducial_accepted_indices: dict[int, pd.Index] = {}
    for plane in range(1, 5):
        plane_result = plane_results.get(plane, {}) if isinstance(plane_results, Mapping) else {}
        representative_eff, representative_method, representative_accepted_index, representative_fired_index = (
            _resolve_track_efficiency_representative(plane_result)
        )
        accepted_indices = plane_result.get("accepted_indices", None) if isinstance(plane_result, dict) else None
        if accepted_indices is not None:
            plane_fiducial_accepted_indices[plane] = pd.Index(accepted_indices)
        row[f"eff{plane}_robust"] = representative_eff
        row[f"eff{plane}_robust_method"] = representative_method
        # Keep the legacy output column name for compatibility, but store the
        # same representative efficiency that the large diagnostic plot shows
        # and that Task 4 would use as the fiducial robust reference.
        row[f"eff{plane}_robust_xyphi"] = representative_eff
        row[f"eff{plane}_median_x"] = plane_result.get("robust_x_center_eff", np.nan)
        row[f"eff{plane}_overall"] = (
            float(plane_result.get("overall_eff", np.nan)) / 100.0
            if np.isfinite(plane_result.get("overall_eff", np.nan))
            else np.nan
        )
        row[f"eff{plane}_robust_n_denom"] = (
            int(len(representative_accepted_index)) if representative_accepted_index is not None else np.nan
        )
        row[f"eff{plane}_robust_n_num"] = (
            int(len(representative_fired_index)) if representative_fired_index is not None else np.nan
        )
        robust_xyphi_accepted = plane_result.get("robust_xyphi_accepted_indices", None)
        robust_xyphi_fired = plane_result.get("robust_xyphi_fired_indices", None)
        row[f"eff{plane}_robust_xyphi_n_denom"] = (
            int(len(pd.Index(robust_xyphi_accepted))) if robust_xyphi_accepted is not None else np.nan
        )
        row[f"eff{plane}_robust_xyphi_n_num"] = (
            int(len(pd.Index(robust_xyphi_fired))) if robust_xyphi_fired is not None else np.nan
        )

    tt_series = pd.to_numeric(df_events["fit_tt"], errors="coerce") if "fit_tt" in df_events.columns else pd.Series(dtype=float)
    fit_tt_1234_index = pd.Index(df_events.index[tt_series.fillna(0).eq(1234.0)]) if not tt_series.empty else None
    n_events_1234 = int(len(fit_tt_1234_index)) if fit_tt_1234_index is not None else 0
    row["four_plane_count"] = int(n_events_1234) if fit_tt_1234_index is not None else np.nan
    row["total_count"] = int(len(df_events))
    row["rate_1234_hz"] = float(n_events_1234 / denominator_seconds) if denominator_seconds > 0 and n_events_1234 > 0 else np.nan

    robust_union_index = None
    robust_intersection_index = None
    if fit_tt_1234_index is not None and plane_fiducial_accepted_indices:
        robust_indices = [
            accepted_index.intersection(fit_tt_1234_index, sort=False)
            for accepted_index in plane_fiducial_accepted_indices.values()
        ]
        robust_union_index = robust_indices[0]
        robust_intersection_index = robust_indices[0]
        for robust_index in robust_indices[1:]:
            robust_union_index = robust_union_index.union(robust_index, sort=False)
            robust_intersection_index = robust_intersection_index.intersection(robust_index, sort=False)

    row["four_plane_robust_count_union"] = int(len(robust_union_index)) if robust_union_index is not None else np.nan
    row["four_plane_robust_hz_union"] = (
        float(len(robust_union_index) / denominator_seconds)
        if robust_union_index is not None and denominator_seconds > 0.0
        else np.nan
    )
    row["four_plane_robust_count_intersection"] = (
        int(len(robust_intersection_index)) if robust_intersection_index is not None else np.nan
    )
    row["four_plane_robust_hz_intersection"] = (
        float(len(robust_intersection_index) / denominator_seconds)
        if robust_intersection_index is not None and denominator_seconds > 0.0
        else np.nan
    )

    if fit_tt_1234_index is not None and len(plane_fiducial_accepted_indices) == 4 and robust_intersection_index is not None:
        four_plane_robust_count = int(len(robust_intersection_index))
        row["four_plane_robust_count"] = four_plane_robust_count
        row["four_plane_robust_hz"] = (
            float(four_plane_robust_count / denominator_seconds) if denominator_seconds > 0.0 else np.nan
        )
        row["four_plane_robust_efficiency"] = (
            float(four_plane_robust_count / n_events_1234) if n_events_1234 > 0 else np.nan
        )
    else:
        row["four_plane_robust_count"] = np.nan
        row["four_plane_robust_hz"] = np.nan
        row["four_plane_robust_efficiency"] = np.nan

    row["robust_efficiency_fiducial"] = row["four_plane_robust_efficiency"]
    row["rate_hz_fiducial_1234"] = row["four_plane_robust_hz"]
    if np.isfinite(row["rate_hz_fiducial_1234"]) and np.isfinite(row["rate_1234_hz"]) and float(row["rate_1234_hz"]) > 0.0:
        row["fiducial_1234_percent_of_total"] = (
            100.0 * float(row["rate_hz_fiducial_1234"]) / float(row["rate_1234_hz"])
        )
    else:
        row["fiducial_1234_percent_of_total"] = np.nan

    sim_effs = list(simulated_efficiencies or [])
    for plane in range(1, 5):
        row[f"eff_p{plane}"] = float(sim_effs[plane - 1]) if plane - 1 < len(sim_effs) else np.nan

    return row


def load_scan_source_tables(task5_file: Path, task4_listed_file: Path) -> pd.DataFrame:
    df_fit = pd.read_parquet(task5_file)
    df_listed = pd.read_parquet(task4_listed_file, columns=["event_id", *list(_required_track_efficiency_hit_columns())])
    return df_fit.merge(df_listed, on="event_id", how="left", validate="one_to_one")


def main() -> int:
    scan_grid_cfg = load_scan_grid_config(SCRIPT_CONFIG_PATH)
    theta_max_values = scan_grid_cfg["theta_max_values_deg"]
    radius_max_values = scan_grid_cfg["radius_max_values_mm"]
    large_plot_cfg = scan_grid_cfg["track_efficiency_large_plot"]

    freshest_task5_file = select_freshest_task5_file(TASK5_COMPLETED_DIRECTORY)
    filename_base = canonical_processing_basename(freshest_task5_file.name)
    station_number = infer_station_number_from_processing_name(filename_base)
    if station_number != 0:
        raise RuntimeError(f"Freshest file {freshest_task5_file.name} does not belong to MINGO00.")

    task4_listed_file = TASK4_LISTED_DIRECTORY / f"listed_{filename_base}.parquet"
    if not task4_listed_file.exists():
        raise FileNotFoundError(
            f"Matching Task 4 listed parquet not found for freshest Task 5 file: {task4_listed_file}"
        )

    # The freshest file is selected by Task 5 mtime, but the robust-efficiency
    # calculation itself needs both:
    # - the fitted event table from Task 5,
    # - the per-plane hit columns from the matching Task 4 listed parquet.
    df_merged = load_scan_source_tables(freshest_task5_file, task4_listed_file)

    task4_config = load_task4_effective_config("0")
    param_hash = _task4_resolve_efficiency_param_hash(extract_param_hash_from_parquet(freshest_task5_file), df_merged)
    z_positions, resolved_hash = resolve_simulated_z_positions(
        filename_base,
        REPO_ROOT / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / "MINGO00" / "STAGE_1" / "EVENT_DATA",
        sim_params_path=SIMULATION_PARAMS_CSV,
        parquet_path=freshest_task5_file,
        param_hash=param_hash,
    )
    if z_positions is None:
        raise RuntimeError(f"Could not resolve z positions for {filename_base} through param_hash.")
    if resolved_hash:
        param_hash = resolved_hash
    simulated_efficiencies = load_simulated_efficiencies(param_hash, sim_params_path=SIMULATION_PARAMS_CSV)

    runtime = build_task4_runtime_geometry(task4_config, z_positions)
    efficiency_metadata_cfg = _resolve_task4_efficiency_metadata_cfg(task4_config)

    # Reuse the same generic Task 4 event-level filter before building the
    # track-efficiency payload. The fiducial scan is applied later, inside the
    # efficiency payload itself, not as an extra event-level row filter.
    working_df, rejected_df, filter_summary = apply_task4_final_filter(
        df_merged,
        config=task4_config,
        apply_changes=True,
    )
    _ = rejected_df, filter_summary

    denominator_seconds = float(build_events_per_second_metadata(working_df).get("events_per_second_total_seconds", 0) or 0)
    execution_timestamp = datetime.now().strftime("%Y-%m-%d_%H.%M.%S")

    scan_points = list(product(theta_max_values, radius_max_values))
    rows: list[dict[str, object]] = []
    scan_progress = tqdm(
        scan_points,
        desc=f"Scanning fiducial grid ({filename_base})",
        unit="point",
        dynamic_ncols=True,
    )
    for theta_max, r_max in scan_progress:
        scan_progress.set_postfix(
            theta_max=theta_max,
            r_max=r_max,
        )
        fiducial_cfg = build_scan_fiducial_cfg(theta_max, r_max)
        payload = _compute_track_based_efficiency_payload(
            working_df,
            cfg_eff=efficiency_metadata_cfg,
            cfg_fiducial=fiducial_cfg,
            z_positions=runtime["z_positions"],
            tdiff_to_x=runtime["tdiff_to_x"],
            strip_half=runtime["strip_half"],
            width_half=runtime["width_half"],
            theta_left_filter=runtime["theta_left_filter"],
            theta_right_filter=runtime["theta_right_filter"],
            phi_left_filter=runtime["phi_left_filter"],
            phi_right_filter=runtime["phi_right_filter"],
            y_pos_p13=runtime["y_pos_p13"],
            y_pos_p24=runtime["y_pos_p24"],
        )
        rows.append(
            build_scan_row(
                payload=payload,
                df_events=working_df,
                denominator_seconds=denominator_seconds,
                filename_base=filename_base,
                execution_timestamp=execution_timestamp,
                param_hash=param_hash,
                theta_max=theta_max,
                r_max=r_max,
                simulated_efficiencies=simulated_efficiencies,
            )
        )
    scan_progress.close()

    output_directory = OUTPUT_PARENT_DIRECTORY / filename_base
    output_directory.mkdir(parents=True, exist_ok=True)
    output_csv = output_directory / "fiducial_scan_table.csv"
    output_df = pd.DataFrame(rows)
    missing_output_columns = [column for column in OUTPUT_SCAN_COLUMNS if column not in output_df.columns]
    if missing_output_columns:
        raise RuntimeError(f"Missing expected output columns: {missing_output_columns}")
    output_df = output_df.loc[:, OUTPUT_SCAN_COLUMNS].copy()
    output_df.to_csv(output_csv, index=False)

    if bool(large_plot_cfg.get("enabled", False)):
        plot_theta_max = float(large_plot_cfg["theta_max_deg"])
        plot_radius_max = float(large_plot_cfg["radius_max_mm"])
        plot_fiducial_cfg = build_scan_fiducial_cfg(plot_theta_max, plot_radius_max)
        plot_payload = _compute_track_based_efficiency_payload(
            working_df,
            cfg_eff=efficiency_metadata_cfg,
            cfg_fiducial=plot_fiducial_cfg,
            z_positions=runtime["z_positions"],
            tdiff_to_x=runtime["tdiff_to_x"],
            strip_half=runtime["strip_half"],
            width_half=runtime["width_half"],
            theta_left_filter=runtime["theta_left_filter"],
            theta_right_filter=runtime["theta_right_filter"],
            phi_left_filter=runtime["phi_left_filter"],
            phi_right_filter=runtime["phi_right_filter"],
            y_pos_p13=runtime["y_pos_p13"],
            y_pos_p24=runtime["y_pos_p24"],
        )
        plot_payload_fullplane = _compute_track_based_efficiency_payload(
            working_df,
            cfg_eff=efficiency_metadata_cfg,
            cfg_fiducial=build_fullplane_fiducial_cfg(),
            z_positions=runtime["z_positions"],
            tdiff_to_x=runtime["tdiff_to_x"],
            strip_half=runtime["strip_half"],
            width_half=runtime["width_half"],
            theta_left_filter=runtime["theta_left_filter"],
            theta_right_filter=runtime["theta_right_filter"],
            phi_left_filter=runtime["phi_left_filter"],
            phi_right_filter=runtime["phi_right_filter"],
            y_pos_p13=runtime["y_pos_p13"],
            y_pos_p24=runtime["y_pos_p24"],
        )
        plot_dir = output_directory / "plots"
        plot_filename = (
            f"track_efficiency_large_plot__theta_{plot_theta_max:g}__r_{plot_radius_max:g}.png"
        )
        plot_output_path = plot_dir / plot_filename
        render_track_efficiency_large_plot(
            payload=plot_payload,
            payload_fullplane=plot_payload_fullplane,
            cfg_fiducial=plot_fiducial_cfg,
            cfg_eff=efficiency_metadata_cfg,
            strip_half=runtime["strip_half"],
            width_half=runtime["width_half"],
            simulated_efficiencies=simulated_efficiencies,
            output_png=plot_output_path,
            filename_base=filename_base,
            theta_max_deg=plot_theta_max,
            radius_max_mm=plot_radius_max,
        )

    print(f"Freshest Task 5 parquet selected by mtime: {freshest_task5_file}")
    print(f"Matched Task 4 listed parquet used for hit columns: {task4_listed_file}")
    print(f"Scan grid config used: {SCRIPT_CONFIG_PATH}")
    print(f"theta_max_values_deg={theta_max_values}")
    print(f"radius_max_values_mm={radius_max_values}")
    print(f"track_efficiency_large_plot={large_plot_cfg}")
    print(f"Task 4-style generic final filter kept {len(working_df)} rows.")
    print(f"Track-efficiency denominator seconds: {int(denominator_seconds)}")
    print(f"Simulated efficiencies matched through param_hash={param_hash}: {simulated_efficiencies}")
    print(f"Fiducial scan table written to: {output_csv}")
    if bool(large_plot_cfg.get("enabled", False)):
        print(f"Track-efficiency large plot written to: {plot_output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
