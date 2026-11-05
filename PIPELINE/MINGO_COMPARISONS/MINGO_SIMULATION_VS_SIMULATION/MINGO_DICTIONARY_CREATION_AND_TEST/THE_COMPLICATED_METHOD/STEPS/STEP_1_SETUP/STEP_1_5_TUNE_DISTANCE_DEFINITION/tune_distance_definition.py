#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_1_SETUP/STEP_1_5_TUNE_DISTANCE_DEFINITION/tune_distance_definition.py
Purpose: STEP 1.5 — Auto-tune the feature-space distance definition for downstream estimation.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-11
Runtime: python3
Usage: python3 .../tune_distance_definition.py [--config CONFIG]
Inputs: dictionary.csv and selected_feature_columns.json from STEP 1.4.
Outputs: distance_definition.json artifact for STEP 2.1.
Notes: Trains a weighted Lp distance via LOO on dictionary entries
       (grid search over normalization × p, then coordinate descent on per-feature weights).
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
from pathlib import Path
import sys
from typing import Callable, Mapping, Sequence

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import re

# ── Paths ────────────────────────────────────────────────────────────
STEP_DIR = Path(__file__).resolve().parent
if STEP_DIR.parents[1].name == "STEPS":
    PIPELINE_DIR = STEP_DIR.parents[2]
else:
    PIPELINE_DIR = STEP_DIR.parents[1]
STEP_ROOT = PIPELINE_DIR if (PIPELINE_DIR / "STEP_1_SETUP").exists() else PIPELINE_DIR / "STEPS"
DEFAULT_CONFIG = (
    STEP_ROOT / "STEP_1_SETUP" / "STEP_1_1_COLLECT_DATA" / "INPUTS" / "config_step_1.1_method.json"
)
DEFAULT_DICTIONARY = (
    STEP_DIR.parent / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY"
    / "OUTPUTS" / "FILES" / "dictionary.csv"
)
DEFAULT_SELECTED_FEATURES = (
    STEP_DIR.parent / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY"
    / "OUTPUTS" / "FILES" / "selected_feature_columns.json"
)
DEFAULT_DATASET = (
    STEP_DIR.parent / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY"
    / "OUTPUTS" / "FILES" / "dataset.csv"
)
DEFAULT_PARAMETER_SPACE = (
    STEP_DIR.parent / "STEP_1_1_COLLECT_DATA"
    / "OUTPUTS" / "FILES" / "parameter_space_columns.json"
)

FILES_DIR = STEP_DIR / "OUTPUTS" / "FILES"
PLOTS_DIR = STEP_DIR / "OUTPUTS" / "PLOTS"
FILES_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

FIGURE_STEP_PREFIX = "1_5"
_FIGURE_COUNTER = 0

logging.basicConfig(format="[%(levelname)s] STEP_1.5 — %(message)s", level=logging.INFO)
log = logging.getLogger("STEP_1.5")

MODULES_DIR = (
    PIPELINE_DIR / "STEPS" / "MODULES"
    if (PIPELINE_DIR / "STEPS" / "MODULES").exists()
    else PIPELINE_DIR / "MODULES"
)
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))
from feature_space_config import (  # noqa: E402
    load_feature_space_config,
    resolve_feature_group_config_path,
    resolve_feature_space_group_definitions,
)
from feature_space_transform_engine import (  # noqa: E402
    filter_rows_with_complete_numeric_columns,
)

STEP2_INFERENCE_DIR = (
    PIPELINE_DIR / "STEPS" / "STEP_2_INFERENCE"
    if (PIPELINE_DIR / "STEPS" / "STEP_2_INFERENCE").exists()
    else PIPELINE_DIR / "STEP_2_INFERENCE"
)
if str(STEP2_INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(STEP2_INFERENCE_DIR))
from estimate_parameters import (  # noqa: E402
    EFFICIENCY_VECTOR_COL_RE,
    RATE_HISTOGRAM_BIN_RE,
    build_efficiency_vector_local_linear_embedding,
    build_ordered_vector_group_local_linear_embedding,
    build_rate_histogram_local_linear_embedding,
    _efficiency_vector_group_distance_many,
    _filter_efficiency_vector_payloads,
    _histogram_distance_many,
    _normalize_aggregation_mode,
    _normalize_efficiency_vector_fiducial,
    _ordered_vector_distance_many,
    _prepare_efficiency_vector_group_payloads,
    _reduce_efficiency_vector_group_stack,
    _resolve_efficiency_vector_distance_cfg,
    _resolve_feature_group_kind,
    _resolve_histogram_distance_cfg,
    _resolve_ordered_vector_group_distance_cfg,
    estimate_from_dataframes,
    resolve_inverse_mapping_cfg,
)

# ── Tuning constants ─────────────────────────────────────────────────
MIN_FEATURE_NON_NULL_FRACTION = 0.50

_NORM_GRID = ["robust_zscore", "standard_zscore", "none"]
_P_GRID = [0.5, 1.0, 1.5, 2.0, 3.0]
_WEIGHT_CANDIDATES = [0.0, 0.25, 0.5, 1.0, 2.0, 4.0]
_MAX_WEIGHT_ROUNDS = 3
_K_GRID = [3, 5, 7, 10, 15, 20, 30, 50, 80, 120]
_LAMBDA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1e6]  # 1e6 ≈ pure IDW fallback
_AGGREGATION_GRID = ["weighted_mean", "weighted_median", "local_linear"]
_MAX_GROUP_OPTION_COMBINATIONS = 256
_DISTANCE_SELECTION_HOLDOUT_TOP_N = 4

# Legacy name → (p, normalization) for backward compat with forced modes.
_LEGACY_MODES: dict[str, tuple[float, str]] = {
    "l2_robust_zscore": (2.0, "robust_zscore"),
    "l2_standard_zscore": (2.0, "standard_zscore"),
    "l2_raw": (2.0, "none"),
    "l1_robust_zscore": (1.0, "robust_zscore"),
    "l1_standard_zscore": (1.0, "standard_zscore"),
    "l1_raw": (1.0, "none"),
    "l2_zscore": (2.0, "robust_zscore"),
    "l1_zscore": (1.0, "robust_zscore"),
}


# ── Helpers ──────────────────────────────────────────────────────────


def _filter_complete_tuning_rows(
    df: pd.DataFrame,
    *,
    feature_cols: Sequence[str],
    param_cols: Sequence[str],
    label: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    missing_feature_cols = [str(col) for col in feature_cols if str(col) not in df.columns]
    missing_param_cols = [str(col) for col in param_cols if str(col) not in df.columns]
    missing_cols = [*missing_feature_cols, *missing_param_cols]
    if missing_cols:
        raise ValueError(
            f"STEP 1.5 {label} is missing required tuning columns: "
            + ", ".join(missing_cols[:50])
            + (" ..." if len(missing_cols) > 50 else "")
        )

    filtered, completeness = filter_rows_with_complete_numeric_columns(
        df,
        required_columns=[*feature_cols, *param_cols],
    )
    completeness = dict(completeness)
    completeness["label"] = str(label)
    completeness["feature_columns_checked"] = [str(col) for col in feature_cols]
    completeness["parameter_columns_checked"] = [str(col) for col in param_cols]
    return filtered, completeness


def _exclude_holdout_rows_with_dictionary_parameter_overlap(
    dictionary_df: pd.DataFrame,
    dataset_df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Remove holdout rows whose physical parameter vector already exists in dictionary."""
    if dataset_df.empty:
        return dataset_df.copy(), {
            "enabled": True,
            "input_rows": 0,
            "rows_kept": 0,
            "rows_removed": 0,
            "rows_removed_fraction": 0.0,
            "overlap_via_hash_count": 0,
            "overlap_via_physical_tuple_count": 0,
            "tuple_columns_used": [],
        }

    hash_mask = pd.Series(False, index=dataset_df.index, dtype=bool)
    if "param_hash_x" in dictionary_df.columns and "param_hash_x" in dataset_df.columns:
        dict_keys = set(dictionary_df["param_hash_x"].astype(str).dropna().tolist())
        hash_mask = dataset_df["param_hash_x"].astype(str).isin(dict_keys).fillna(False)

    base_cols = [
        "flux_cm2_min",
        "cos_n",
        "eff_sim_1",
        "eff_sim_2",
        "eff_sim_3",
        "eff_sim_4",
        "z_plane_1",
        "z_plane_2",
        "z_plane_3",
        "z_plane_4",
    ]
    tuple_cols = [
        str(col)
        for col in base_cols
        if str(col) in dictionary_df.columns and str(col) in dataset_df.columns
    ]
    tuple_mask = pd.Series(False, index=dataset_df.index, dtype=bool)
    if tuple_cols:
        dict_num = dictionary_df[tuple_cols].apply(pd.to_numeric, errors="coerce")
        data_num = dataset_df[tuple_cols].apply(pd.to_numeric, errors="coerce")
        dict_keys = {
            tuple(np.round(row, 12))
            for row in dict_num.to_numpy(dtype=float)
            if np.all(np.isfinite(row))
        }
        if dict_keys:
            tuple_mask = pd.Series(
                [
                    tuple(np.round(row, 12)) in dict_keys if np.all(np.isfinite(row)) else False
                    for row in data_num.to_numpy(dtype=float)
                ],
                index=dataset_df.index,
                dtype=bool,
            )

    overlap_mask = (hash_mask | tuple_mask).fillna(False)
    filtered = dataset_df.loc[~overlap_mask].copy()
    input_rows = int(len(dataset_df))
    rows_removed = int(overlap_mask.sum())
    rows_kept = int(len(filtered))
    return filtered, {
        "enabled": True,
        "input_rows": input_rows,
        "rows_kept": rows_kept,
        "rows_removed": rows_removed,
        "rows_removed_fraction": (float(rows_removed) / float(input_rows)) if input_rows > 0 else 0.0,
        "overlap_via_hash_count": int(hash_mask.sum()),
        "overlap_via_physical_tuple_count": int(tuple_mask.sum()),
        "tuple_columns_used": list(tuple_cols),
    }


def _load_config(path: Path) -> dict:
    cfg: dict = {}
    if path.exists():
        cfg = json.loads(path.read_text(encoding="utf-8"))
    else:
        log.warning("Config file not found: %s", path)
    runtime_path = path.with_name("config_step_1.1_runtime.json")
    if runtime_path.exists():
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        cfg.update(runtime)
        log.info("Loaded runtime overrides: %s", runtime_path)
    return cfg


def _load_selected_features(path: Path) -> list[str]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    cols = payload.get("selected_feature_columns", []) if isinstance(payload, dict) else []
    return [c for c in cols if isinstance(c, str) and c.strip()]


def _coerce_nonnegative_float(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        out = float(default)
    if not np.isfinite(out):
        out = float(default)
    return max(float(out), 0.0)


def _group_min_weight(
    feature_groups: Mapping[str, object] | None,
    group_name: str,
) -> float:
    if not isinstance(feature_groups, Mapping):
        return 0.0
    raw_cfg = feature_groups.get(group_name, {})
    if not isinstance(raw_cfg, Mapping):
        return 0.0
    return _coerce_nonnegative_float(raw_cfg.get("min_weight"), 0.0)


def _resolve_group_weight_candidates(
    *,
    feature_groups: Mapping[str, object] | None,
    group_name: str,
    raw_candidates: Sequence[object],
) -> list[float]:
    min_weight = _group_min_weight(feature_groups, group_name)
    candidates = sorted(
        {
            max(_coerce_nonnegative_float(value, 0.0), min_weight)
            for value in raw_candidates
        }
    )
    if not candidates:
        candidates = [float(min_weight)]
    return [float(value) for value in candidates]


def _apply_group_weight_floors(
    group_weights: Mapping[str, object] | None,
    *,
    feature_groups: Mapping[str, object] | None,
) -> dict[str, float]:
    out: dict[str, float] = {}
    if not isinstance(group_weights, Mapping):
        return out
    for raw_name, raw_weight in group_weights.items():
        name = str(raw_name)
        out[name] = max(
            _coerce_nonnegative_float(raw_weight, 0.0),
            _group_min_weight(feature_groups, name),
        )
    return out


def _load_parameter_space_columns(
    path: Path,
    *,
    available_columns: Sequence[str] | None = None,
) -> list[str]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return []
    available_set = (
        {str(col).strip() for col in available_columns if str(col).strip()}
        if available_columns is not None
        else None
    )
    alias_map_raw = payload.get("parameter_space_column_aliases", {})
    alias_map = (
        {
            str(k).strip(): str(v).strip()
            for k, v in alias_map_raw.items()
            if str(k).strip() and str(v).strip()
        }
        if isinstance(alias_map_raw, Mapping)
        else {}
    )

    candidates = [
        payload.get("parameter_space_columns_downstream_preferred"),
        payload.get("selected_parameter_space_columns_downstream_preferred"),
        payload.get("selected_parameter_space_columns"),
        payload.get("parameter_space_columns"),
    ]

    def _resolve_name(name: str) -> str | None:
        if not name:
            return None
        if available_set is None:
            return name
        if name in available_set:
            return name
        candidate_names: list[str] = []
        canonical = alias_map.get(name, name)
        for cand in (name, canonical):
            text = str(cand).strip()
            if text and text not in candidate_names:
                candidate_names.append(text)
        # reverse alias lookup (e.g. resolve eff_sim_i -> eff_pi when only eff_pi exists)
        for src, dst in alias_map.items():
            if dst == name or dst == canonical:
                if src not in candidate_names:
                    candidate_names.append(src)
        # deterministic fallback for common efficiency naming pairs
        if name.startswith("eff_sim_"):
            suffix = name[len("eff_sim_") :]
            candidate_names.append(f"eff_p{suffix}")
        if name.startswith("eff_p"):
            suffix = name[len("eff_p") :]
            candidate_names.append(f"eff_sim_{suffix}")
        for cand in candidate_names:
            if cand in available_set:
                return cand
        return None

    for raw in candidates:
        if not isinstance(raw, list):
            continue
        out: list[str] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, str):
                continue
            resolved = _resolve_name(item.strip())
            if not resolved:
                continue
            if resolved in seen:
                continue
            out.append(resolved)
            seen.add(resolved)
        if out:
            return out
    return []


def _grid_boundary_detail(
    *,
    axis_name: str,
    best_value: object,
    tested_values: list[object],
) -> dict[str, object]:
    values = list(tested_values)
    if not values:
        return {
            "axis": axis_name,
            "tested_values": [],
            "selected_value": best_value,
            "grid_size": 0,
            "on_lower_boundary": False,
            "on_upper_boundary": False,
            "is_boundary": False,
        }

    lower = values[0]
    upper = values[-1]
    if isinstance(best_value, (float, int, np.floating, np.integer)) and isinstance(lower, (float, int, np.floating, np.integer)):
        on_lower = bool(np.isclose(float(best_value), float(lower)))
        on_upper = bool(np.isclose(float(best_value), float(upper)))
    else:
        on_lower = best_value == lower
        on_upper = best_value == upper

    if len(values) <= 1:
        on_lower = False
        on_upper = False

    return {
        "axis": axis_name,
        "tested_values": values,
        "selected_value": best_value,
        "grid_size": int(len(values)),
        "lower_boundary_value": lower,
        "upper_boundary_value": upper,
        "on_lower_boundary": bool(on_lower),
        "on_upper_boundary": bool(on_upper),
        "is_boundary": bool(on_lower or on_upper),
    }


def _resolve_step15_search_cfg(cfg_15: Mapping[str, object] | None) -> dict[str, object]:
    cfg = cfg_15 if isinstance(cfg_15, Mapping) else {}

    def _numeric_grid(
        key: str,
        default: Sequence[float],
        *,
        minimum: float | None = None,
        integer: bool = False,
    ) -> list[float] | list[int]:
        raw = cfg.get(key, default)
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raw = default
        out: list[float | int] = []
        for item in raw:
            try:
                value = int(item) if integer else float(item)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(float(value)):
                continue
            if minimum is not None and float(value) < float(minimum):
                continue
            out.append(int(value) if integer else float(value))
        if not out:
            out = [int(v) if integer else float(v) for v in default]
        out = sorted(set(out))
        return out

    raw_norm = cfg.get("normalization_grid", _NORM_GRID)
    if not isinstance(raw_norm, Sequence) or isinstance(raw_norm, (str, bytes)):
        raw_norm = _NORM_GRID
    normalization_grid = [
        str(item).strip()
        for item in raw_norm
        if str(item).strip() in {"robust_zscore", "standard_zscore", "none"}
    ]
    if not normalization_grid:
        normalization_grid = list(_NORM_GRID)

    raw_agg = cfg.get("aggregation_grid", _AGGREGATION_GRID)
    if not isinstance(raw_agg, Sequence) or isinstance(raw_agg, (str, bytes)):
        raw_agg = _AGGREGATION_GRID
    aggregation_grid: list[str] = []
    for item in raw_agg:
        mode = _normalize_aggregation_mode(item)
        if mode not in aggregation_grid:
            aggregation_grid.append(mode)
    if not aggregation_grid:
        aggregation_grid = list(_AGGREGATION_GRID)

    return {
        "normalization_grid": normalization_grid,
        "p_grid": _numeric_grid("p_grid", _P_GRID, minimum=0.1, integer=False),
        "aggregation_grid": aggregation_grid,
        "weight_candidates": _numeric_grid("weight_candidates", _WEIGHT_CANDIDATES, minimum=0.0, integer=False),
        "k_grid": _numeric_grid("k_grid", _K_GRID, minimum=1, integer=True),
        "lambda_grid": _numeric_grid("lambda_grid", _LAMBDA_GRID, minimum=0.0, integer=False),
        "max_weight_rounds": int(max(float(cfg.get("max_weight_rounds", _MAX_WEIGHT_ROUNDS)), 1.0)),
        "max_group_option_combinations": int(max(float(cfg.get("max_group_option_combinations", _MAX_GROUP_OPTION_COMBINATIONS)), 1.0)),
        "distance_selection_objective": str(
            cfg.get("distance_selection_objective", "dictionary_loo")
        ).strip().lower(),
        "distance_selection_holdout_top_n": int(
            max(float(cfg.get("distance_selection_holdout_top_n", _DISTANCE_SELECTION_HOLDOUT_TOP_N)), 1.0)
        ),
        "inverse_mapping_selection_objective": str(
            cfg.get("inverse_mapping_selection_objective", "dictionary_loo")
        ).strip().lower(),
    }


def _log_unified_distance_term_list(
    *,
    feature_columns: Sequence[str],
    scalar_feature_columns: Sequence[str],
    scalar_weights: np.ndarray | None,
    feature_groups: Mapping[str, object] | None,
    group_weights: Mapping[str, float] | None,
    header: str,
) -> None:
    log.info("%s", header)
    feature_cols = [str(col) for col in feature_columns]
    scalar_set = {str(col) for col in scalar_feature_columns}
    weights = np.asarray(scalar_weights, dtype=float) if scalar_weights is not None else np.asarray([], dtype=float)
    for idx, name in enumerate(feature_cols):
        if name not in scalar_set:
            continue
        w = float(weights[idx]) if idx < weights.size and np.isfinite(weights[idx]) else 0.0
        log.info("    %s: 1 feature --> 1 distance (weight=%.3g)", name, w)
    if not isinstance(feature_groups, Mapping):
        return
    group_w = dict(group_weights or {})
    for raw_group_name, raw_cfg in feature_groups.items():
        group_name = str(raw_group_name).strip()
        if not group_name or not isinstance(raw_cfg, Mapping):
            continue
        cols = [str(col) for col in raw_cfg.get("feature_columns", []) if str(col).strip()]
        n_features = int(len(cols))
        raw_weight = group_w.get(group_name, 0.0)
        try:
            w = float(raw_weight)
        except (TypeError, ValueError):
            w = 0.0
        if not np.isfinite(w):
            w = 0.0
        expands = _coerce_bool(raw_cfg.get("expand_components_as_scalar", False), default=False)
        if expands:
            log.info(
                "    %s: %d features --> tied 1D vector distances (shared weight=%.3g)",
                group_name,
                n_features,
                w,
            )
        else:
            log.info(
                "    %s: %d features --> 1 distance (weight=%.3g)",
                group_name,
                n_features,
                w,
            )


# ── Tuning functions ─────────────────────────────────────────────────

def _compute_normalization_params(
    x_raw: np.ndarray, normalization: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (center, scale) arrays for a normalization mode."""
    if normalization == "robust_zscore":
        center = np.nanmedian(x_raw, axis=0)
        mad = np.nanmedian(np.abs(x_raw - center), axis=0)
        scale = np.where(mad > 1e-12, 1.4826 * mad, np.nanstd(x_raw, axis=0))
        scale = np.where(scale > 1e-12, scale, 1.0)
    elif normalization == "standard_zscore":
        center = np.nanmean(x_raw, axis=0)
        scale = np.nanstd(x_raw, axis=0)
        scale = np.where(scale > 1e-12, scale, 1.0)
    else:  # "none"
        center = np.zeros(x_raw.shape[1], dtype=float)
        scale = np.ones(x_raw.shape[1], dtype=float)
    return center.astype(float), scale.astype(float)


def _weighted_lp_pairwise(
    z: np.ndarray, p: float, weights: np.ndarray,
) -> np.ndarray:
    """Pairwise weighted Lp distance matrix.

    d(i,k) = (sum_j w_j |z_i_j - z_k_j|^p )^(1/p)
    """
    diff = np.abs(z[:, np.newaxis, :] - z[np.newaxis, :, :])
    if p == 1.0:
        comp = diff
    elif p == 2.0:
        comp = diff * diff
    else:
        comp = np.power(diff, p)
    dist_p = np.einsum("ijk,k->ij", comp, weights)
    if p == 1.0:
        return dist_p
    if p == 2.0:
        return np.sqrt(dist_p)
    return np.power(np.maximum(dist_p, 0.0), 1.0 / p)


def _robust_scale(values: np.ndarray) -> float:
    vals = np.asarray(values, dtype=float)
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return 1.0
    med = float(np.median(np.abs(vals)))
    if np.isfinite(med) and med > 1e-15:
        return med
    vmax = float(np.max(np.abs(vals)))
    if np.isfinite(vmax) and vmax > 1e-15:
        return vmax
    return 1.0


def _combine_pairwise_distance_terms(
    *,
    base_distances: np.ndarray | None,
    aux_terms: list[tuple[np.ndarray | None, float, str]],
) -> np.ndarray:
    base = None if base_distances is None else np.asarray(base_distances, dtype=float)
    present_aux: list[tuple[np.ndarray, float, str]] = []
    for distances, weight, blend_mode in aux_terms:
        if distances is None or float(weight) <= 0.0:
            continue
        present_aux.append((np.asarray(distances, dtype=float), float(weight), str(blend_mode)))

    if base is None and not present_aux:
        return np.asarray([], dtype=float)
    ref_shape = base.shape if base is not None else present_aux[0][0].shape
    for distances, _, _ in present_aux:
        if distances.shape != ref_shape:
            return np.full(ref_shape, np.nan, dtype=float)

    use_normalized_base = base is not None and any(mode == "normalized" for _, _, mode in present_aux)
    if base is None:
        out = np.full(ref_shape, np.nan, dtype=float)
    else:
        base_term = base / _robust_scale(base) if use_normalized_base else base
        out = np.asarray(base_term, dtype=float).copy()

    for distances, weight, blend_mode in present_aux:
        term = distances / _robust_scale(distances) if blend_mode == "normalized" else distances
        term = np.asarray(term, dtype=float)
        out_finite = np.isfinite(out)
        term_finite = np.isfinite(term)
        both = out_finite & term_finite
        term_only = (~out_finite) & term_finite
        out[both] = out[both] + weight * term[both]
        out[term_only] = weight * term[term_only]
    return out


def _pairwise_histogram_distance_matrix(
    hist_matrix: np.ndarray,
    *,
    distance: str,
    normalization: str,
    p_norm: float,
    amplitude_weight: float,
    shape_weight: float,
    slope_weight: float,
    cdf_weight: float,
    amplitude_stat: str,
) -> np.ndarray:
    mat = np.asarray(hist_matrix, dtype=float)
    if mat.ndim != 2 or mat.shape[0] == 0:
        return np.empty((0, 0), dtype=float)
    out = np.full((mat.shape[0], mat.shape[0]), np.nan, dtype=float)
    for idx in range(mat.shape[0]):
        out[idx] = _histogram_distance_many(
            mat[idx],
            mat,
            distance=distance,
            normalization=normalization,
            p_norm=p_norm,
            amplitude_weight=amplitude_weight,
            shape_weight=shape_weight,
            slope_weight=slope_weight,
            cdf_weight=cdf_weight,
            amplitude_stat=amplitude_stat,
        )
    np.fill_diagonal(out, 0.0)
    return out


def _coerce_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _ordered_vector_option_label(cfg: Mapping[str, object]) -> str:
    vec_cfg = _resolve_ordered_vector_group_distance_cfg(cfg)
    label = str(vec_cfg["distance"])
    if str(vec_cfg.get("normalization", "none")) != "none":
        label += f":norm={vec_cfg['normalization']}"
    label += f":p={float(vec_cfg.get('p_norm', 2.0)):g}"
    if float(vec_cfg["amplitude_weight"]) > 0.0:
        label += f":amp={float(vec_cfg['amplitude_weight']):g}"
    if float(vec_cfg["shape_weight"]) != 1.0:
        label += f":shape={float(vec_cfg['shape_weight']):g}"
    if float(vec_cfg.get("slope_weight", 0.0)) > 0.0:
        label += f":slope={float(vec_cfg['slope_weight']):g}"
    if float(vec_cfg.get("cdf_weight", 0.0)) > 0.0:
        label += f":cdf={float(vec_cfg['cdf_weight']):g}"
    return label


def _pairwise_ordered_vector_distance_matrix(
    vector_matrix: np.ndarray,
    *,
    normalization: str,
    p_norm: float,
    amplitude_weight: float,
    shape_weight: float,
    slope_weight: float,
    cdf_weight: float,
    amplitude_stat: str,
    min_valid_bins: int = 1,
) -> np.ndarray:
    mat = np.asarray(vector_matrix, dtype=float)
    if mat.ndim != 2 or mat.shape[0] == 0:
        return np.empty((0, 0), dtype=float)
    out = np.full((mat.shape[0], mat.shape[0]), np.nan, dtype=float)
    min_bins = max(int(min_valid_bins), 1)
    for idx in range(mat.shape[0]):
        out[idx] = _ordered_vector_distance_many(
            sample_vec=mat[idx],
            candidates_vec=mat,
            normalization=normalization,
            p_norm=p_norm,
            amplitude_weight=amplitude_weight,
            shape_weight=shape_weight,
            slope_weight=slope_weight,
            cdf_weight=cdf_weight,
            amplitude_stat=amplitude_stat,
            min_valid_bins=min_bins,
        )
    np.fill_diagonal(out, 0.0)
    return out


def _pairwise_efficiency_vector_distance_matrix(
    payloads: list[dict[str, object]],
    *,
    fiducial: dict[str, float | None],
    uncertainty_floor: float,
    min_valid_bins_per_vector: int,
    normalization: str,
    p_norm: float,
    amplitude_weight: float,
    shape_weight: float,
    slope_weight: float,
    cdf_weight: float,
    amplitude_stat: str,
    group_reduction: str,
) -> np.ndarray:
    if not payloads:
        return np.empty((0, 0), dtype=float)
    n_rows = int(np.asarray(payloads[0]["dict_eff"], dtype=float).shape[0])
    group_stack: list[np.ndarray] = []
    for payload in payloads:
        eff_mat = np.asarray(payload["dict_eff"], dtype=float)
        unc_mat = np.asarray(payload["dict_unc"], dtype=float)
        centers = np.asarray(payload["centers"], dtype=float)
        axis_name = str(payload["axis"])
        group_dm = np.full((n_rows, n_rows), np.nan, dtype=float)
        for idx in range(n_rows):
            group_dm[idx] = _efficiency_vector_group_distance_many(
                sample_eff=eff_mat[idx],
                candidates_eff=eff_mat,
                sample_unc=unc_mat[idx],
                candidates_unc=unc_mat,
                centers=centers,
                axis_name=axis_name,
                fiducial=fiducial,
                uncertainty_floor=uncertainty_floor,
                min_valid_bins=min_valid_bins_per_vector,
                normalization=normalization,
                p_norm=p_norm,
                amplitude_weight=amplitude_weight,
                shape_weight=shape_weight,
                slope_weight=slope_weight,
                cdf_weight=cdf_weight,
                amplitude_stat=amplitude_stat,
            )
        np.fill_diagonal(group_dm, 0.0)
        group_stack.append(group_dm)
    stacked = np.stack(group_stack, axis=0)
    out = _reduce_efficiency_vector_group_stack(
        stacked.reshape(stacked.shape[0], -1),
        group_reduction=group_reduction,
    ).reshape(n_rows, n_rows)
    np.fill_diagonal(out, 0.0)
    return out


def _normalize_joint_weights(
    scalar_weights: np.ndarray,
    group_weights: dict[str, float],
) -> tuple[np.ndarray, dict[str, float]]:
    scalar = np.asarray(scalar_weights, dtype=float).copy()
    groups = {str(name): float(value) for name, value in group_weights.items()}
    active_values = [float(v) for v in scalar[np.isfinite(scalar) & (scalar > 0.0)]]
    active_values.extend(
        float(v)
        for v in groups.values()
        if np.isfinite(float(v)) and float(v) > 0.0
    )
    if not active_values:
        return scalar, groups
    norm = float(np.mean(active_values))
    if not np.isfinite(norm) or norm <= 0.0:
        return scalar, groups
    scalar /= norm
    for name in list(groups.keys()):
        groups[name] = float(groups[name]) / norm
    return scalar, groups


def _group_tuning_candidate_specs(base_cfg: Mapping[str, object] | None) -> list[dict[str, object]]:
    cfg = dict(base_cfg or {})
    raw_candidates = cfg.pop("tuning_candidates", [])
    candidates: list[dict[str, object]] = [dict(cfg)]
    if isinstance(raw_candidates, Mapping):
        raw_iterable = [raw_candidates]
    elif isinstance(raw_candidates, Sequence) and not isinstance(raw_candidates, (str, bytes)):
        raw_iterable = list(raw_candidates)
    else:
        raw_iterable = []
    for raw in raw_iterable:
        if not isinstance(raw, Mapping):
            continue
        merged = dict(cfg)
        merged.update({str(k): v for k, v in raw.items()})
        merged.pop("tuning_candidates", None)
        candidates.append(merged)
    return candidates


def _histogram_option_label(cfg: Mapping[str, object]) -> str:
    hist_cfg = _resolve_histogram_distance_cfg(cfg)
    label = str(hist_cfg["distance"])
    if str(hist_cfg.get("normalization", "none")) != "none":
        label += f":norm={hist_cfg['normalization']}"
    label += f":p={float(hist_cfg.get('p_norm', 1.0)):g}"
    if float(hist_cfg["amplitude_weight"]) > 0.0:
        label += f":amp={float(hist_cfg['amplitude_weight']):g}"
    if float(hist_cfg["shape_weight"]) != 1.0:
        label += f":shape={float(hist_cfg['shape_weight']):g}"
    if float(hist_cfg.get("slope_weight", 0.0)) > 0.0:
        label += f":slope={float(hist_cfg['slope_weight']):g}"
    if float(hist_cfg.get("cdf_weight", 0.0)) > 0.0:
        label += f":cdf={float(hist_cfg['cdf_weight']):g}"
    return label


def _efficiency_vector_option_label(cfg: Mapping[str, object]) -> str:
    eff_cfg = _resolve_efficiency_vector_distance_cfg(cfg)
    return (
        f"{eff_cfg['distance']}:norm={eff_cfg['normalization']}:p={float(eff_cfg['p_norm']):g}:"
        f"amp={float(eff_cfg['amplitude_weight']):g}:shape={float(eff_cfg['shape_weight']):g}:"
        f"slope={float(eff_cfg['slope_weight']):g}:cdf={float(eff_cfg['cdf_weight']):g}:"
        f"red={eff_cfg['group_reduction']}:floor={float(eff_cfg['uncertainty_floor']):g}:"
        f"minbins={int(eff_cfg['min_valid_bins_per_vector'])}"
    )


def _enumerate_group_option_combinations(
    *,
    group_tuning_options: Mapping[str, list[dict[str, object]]],
    base_group_distance_mats: Mapping[str, np.ndarray],
    base_feature_groups: Mapping[str, object],
    max_combinations: int = _MAX_GROUP_OPTION_COMBINATIONS,
) -> list[dict[str, object]]:
    active_names = [
        str(name)
        for name, options in group_tuning_options.items()
        if isinstance(options, list) and len(options) > 0
    ]
    if not active_names:
        return [
            {
                "selected_idx": {},
                "group_distance_mats": dict(base_group_distance_mats),
                "feature_groups": {
                    str(name): (dict(value) if isinstance(value, Mapping) else value)
                    for name, value in base_feature_groups.items()
                },
                "key": "default",
                "label": "default",
            }
        ]

    total = 1
    for name in active_names:
        total *= max(len(group_tuning_options.get(name, [])), 1)
    if total > max(int(max_combinations), 1):
        log.warning(
            "Vector-term metric candidate cartesian product has %d combinations, exceeding max_group_option_combinations=%d. "
            "Falling back to default vector-term metric options plus local coordinate refinement.",
            total,
            int(max_combinations),
        )
        return [
            {
                "selected_idx": {name: 0 for name in active_names},
                "group_distance_mats": dict(base_group_distance_mats),
                "feature_groups": {
                    str(name): (dict(value) if isinstance(value, Mapping) else value)
                    for name, value in base_feature_groups.items()
                },
                "key": "default",
                "label": "default",
            }
        ]

    combos: list[dict[str, object]] = []
    option_ranges = [range(len(group_tuning_options[name])) for name in active_names]
    for raw_indices in itertools.product(*option_ranges):
        selected_idx = {name: int(idx) for name, idx in zip(active_names, raw_indices)}
        mats = dict(base_group_distance_mats)
        features = {
            str(name): (dict(value) if isinstance(value, Mapping) else value)
            for name, value in base_feature_groups.items()
        }
        key_parts: list[str] = []
        label_parts: list[str] = []
        for name, idx in selected_idx.items():
            option = group_tuning_options[name][idx]
            mats[name] = np.asarray(option["distance_matrix"], dtype=float)
            features[name] = dict(option["config"])
            key_parts.append(f"{name}:{idx}")
            label_parts.append(f"{name}={option.get('label', idx)}")
        combos.append(
            {
                "selected_idx": selected_idx,
                "group_distance_mats": mats,
                "feature_groups": features,
                "key": "|".join(key_parts),
                "label": " ; ".join(label_parts),
            }
        )
    return combos


def _build_feature_group_inputs(
    *,
    dictionary_df: pd.DataFrame,
    feature_cols: list[str],
    inverse_cfg: dict,
    feature_group_defs: dict[str, dict[str, object]] | None = None,
) -> tuple[
    list[str],
    dict[str, np.ndarray],
    dict[str, np.ndarray],
    dict[str, object],
    dict[str, float],
    dict[str, list[dict[str, object]]],
]:
    scalar_feature_cols = [str(col) for col in feature_cols]
    group_distance_mats: dict[str, np.ndarray] = {}
    group_coord_mats: dict[str, np.ndarray] = {}
    feature_groups: dict[str, object] = {}
    group_weights: dict[str, float] = {}
    group_tuning_options: dict[str, list[dict[str, object]]] = {}
    feature_group_defs = dict(feature_group_defs or {})

    # -----------------------------------------------------------------
    # Canonical histogram grouped term (backward compatible)
    # -----------------------------------------------------------------
    hist_cfg = feature_group_defs.get("rate_histogram", {})
    if not isinstance(hist_cfg, dict):
        hist_cfg = {}
    hist_cols: list[str] = []
    if bool(hist_cfg.get("enabled", True)):
        hist_cols = [
            str(col)
            for col in hist_cfg.get("feature_columns", [])
            if str(col) in dictionary_df.columns
        ]
    if not hist_cols:
        hist_cols = [str(col) for col in feature_cols if RATE_HISTOGRAM_BIN_RE.match(str(col))]
    if hist_cols:
        expand_as_scalar = _coerce_bool(hist_cfg.get("expand_components_as_scalar", False), default=False)
        if not expand_as_scalar:
            scalar_feature_cols = [col for col in scalar_feature_cols if col not in hist_cols]
        hist_matrix = (
            dictionary_df[hist_cols]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(dtype=float)
        )
        hist_blend_mode = str(
            hist_cfg.get("blend_mode", inverse_cfg.get("histogram_distance_blend_mode", "normalized"))
        )
        hist_options: list[dict[str, object]] = []
        for cand_cfg in _group_tuning_candidate_specs(hist_cfg):
            hist_dist_cfg = _resolve_histogram_distance_cfg(cand_cfg)
            hist_option_cfg = {
                "distance": str(hist_dist_cfg["distance"]),
                "blend_mode": hist_blend_mode,
                "min_weight": _coerce_nonnegative_float(hist_cfg.get("min_weight"), 0.0),
                "normalization": str(hist_dist_cfg["normalization"]),
                "p_norm": float(hist_dist_cfg["p_norm"]),
                "amplitude_weight": float(hist_dist_cfg["amplitude_weight"]),
                "shape_weight": float(hist_dist_cfg["shape_weight"]),
                "slope_weight": float(hist_dist_cfg["slope_weight"]),
                "cdf_weight": float(hist_dist_cfg["cdf_weight"]),
                "amplitude_stat": str(hist_dist_cfg["amplitude_stat"]),
                "feature_columns": hist_cols,
                "tuning_label": _histogram_option_label(cand_cfg),
                "expand_components_as_scalar": bool(expand_as_scalar),
                "group_type": "rate_histogram",
            }
            hist_coord_matrix, hist_coord_meta = build_rate_histogram_local_linear_embedding(
                hist_matrix=hist_matrix,
                feature_names=hist_cols,
                hist_cfg=hist_option_cfg,
            )
            hist_option_cfg["local_linear_embedding"] = dict(hist_coord_meta)
            hist_options.append(
                {
                    "config": hist_option_cfg,
                    "distance_matrix": _pairwise_histogram_distance_matrix(
                        hist_matrix,
                        distance=str(hist_dist_cfg["distance"]),
                        normalization=str(hist_dist_cfg["normalization"]),
                        p_norm=float(hist_dist_cfg["p_norm"]),
                        amplitude_weight=float(hist_dist_cfg["amplitude_weight"]),
                        shape_weight=float(hist_dist_cfg["shape_weight"]),
                        slope_weight=float(hist_dist_cfg["slope_weight"]),
                        cdf_weight=float(hist_dist_cfg["cdf_weight"]),
                        amplitude_stat=str(hist_dist_cfg["amplitude_stat"]),
                    ),
                    "coord_matrix": np.asarray(hist_coord_matrix, dtype=float),
                    "label": str(hist_option_cfg["tuning_label"]),
                }
            )
        if hist_options:
            if not expand_as_scalar:
                group_tuning_options["rate_histogram"] = hist_options
                group_distance_mats["rate_histogram"] = np.asarray(
                    hist_options[0]["distance_matrix"], dtype=float
                )
            group_coord_mats["rate_histogram"] = np.asarray(
                hist_options[0].get("coord_matrix", np.empty((len(dictionary_df), 0), dtype=float)),
                dtype=float,
            )
            feature_groups["rate_histogram"] = dict(hist_options[0]["config"])
        group_weights["rate_histogram"] = 1.0

    # -----------------------------------------------------------------
    # Canonical efficiency-vector grouped term (backward compatible)
    # -----------------------------------------------------------------
    eff_group_cfg = feature_group_defs.get("efficiency_vectors", {})
    if not isinstance(eff_group_cfg, dict):
        eff_group_cfg = {}
    effvec_payloads = _prepare_efficiency_vector_group_payloads(
        dict_df=dictionary_df,
        data_df=dictionary_df,
    )
    eff_selected_cols: list[str] = []
    if bool(eff_group_cfg.get("enabled", True)):
        eff_selected_cols = [
            str(col)
            for col in eff_group_cfg.get("feature_columns", [])
            if str(col).strip()
        ]
    effvec_payloads = _filter_efficiency_vector_payloads(
        effvec_payloads,
        feature_groups_cfg=eff_group_cfg if eff_group_cfg else None,
        selected_feature_columns=eff_selected_cols or feature_cols,
    )
    if effvec_payloads:
        effvec_cols = [
            col
            for payload in effvec_payloads
            for col in payload.get("eff_cols", [])
        ]
        # Optionally expand vector components as scalar feature dims (tied weights per group).
        expand_as_scalar = _coerce_bool(eff_group_cfg.get("expand_components_as_scalar", False), default=False)
        if not expand_as_scalar:
            scalar_feature_cols = [col for col in scalar_feature_cols if col not in set(effvec_cols)]
        effvec_cfg_base = eff_group_cfg or inverse_cfg.get("efficiency_vector_distance", {})
        if not isinstance(effvec_cfg_base, dict):
            effvec_cfg_base = {}
        eff_blend_mode = str(effvec_cfg_base.get("blend_mode", "normalized"))
        eff_options: list[dict[str, object]] = []
        for cand_cfg in _group_tuning_candidate_specs(effvec_cfg_base):
            eff_dist_cfg = _resolve_efficiency_vector_distance_cfg(cand_cfg)
            eff_option_cfg = {
                "distance": str(eff_dist_cfg["distance"]),
                "blend_mode": eff_blend_mode,
                "min_weight": _coerce_nonnegative_float(effvec_cfg_base.get("min_weight"), 0.0),
                "normalization": str(eff_dist_cfg["normalization"]),
                "p_norm": float(eff_dist_cfg["p_norm"]),
                "amplitude_weight": float(eff_dist_cfg["amplitude_weight"]),
                "group_reduction": str(eff_dist_cfg["group_reduction"]),
                "shape_weight": float(eff_dist_cfg["shape_weight"]),
                "slope_weight": float(eff_dist_cfg["slope_weight"]),
                "cdf_weight": float(eff_dist_cfg["cdf_weight"]),
                "amplitude_stat": str(eff_dist_cfg["amplitude_stat"]),
                "uncertainty_floor": float(eff_dist_cfg["uncertainty_floor"]),
                "min_valid_bins_per_vector": int(eff_dist_cfg["min_valid_bins_per_vector"]),
                "fiducial": dict(eff_dist_cfg["fiducial"]),
                "feature_columns": sorted(set(effvec_cols)),
                "groups": [
                    {
                        "label": str(payload.get("label", "")),
                        "plane": int(payload.get("plane", 0)),
                        "axis": str(payload.get("axis", "")),
                        "feature_columns": list(payload.get("eff_cols", [])),
                    }
                    for payload in effvec_payloads
                ],
                "tuning_label": _efficiency_vector_option_label(cand_cfg),
                "expand_components_as_scalar": bool(expand_as_scalar),
                "group_type": "efficiency_vectors",
            }
            eff_coord_matrix, eff_coord_meta = build_efficiency_vector_local_linear_embedding(
                payloads=effvec_payloads,
                eff_cfg=eff_option_cfg,
                source="dict",
            )
            eff_option_cfg["local_linear_embedding"] = dict(eff_coord_meta)
            eff_options.append(
                {
                    "config": eff_option_cfg,
                    "distance_matrix": _pairwise_efficiency_vector_distance_matrix(
                        effvec_payloads,
                        fiducial=dict(eff_dist_cfg["fiducial"]),
                        uncertainty_floor=float(eff_dist_cfg["uncertainty_floor"]),
                        min_valid_bins_per_vector=int(eff_dist_cfg["min_valid_bins_per_vector"]),
                        normalization=str(eff_dist_cfg["normalization"]),
                        p_norm=float(eff_dist_cfg["p_norm"]),
                        amplitude_weight=float(eff_dist_cfg["amplitude_weight"]),
                        shape_weight=float(eff_dist_cfg["shape_weight"]),
                        slope_weight=float(eff_dist_cfg["slope_weight"]),
                        cdf_weight=float(eff_dist_cfg["cdf_weight"]),
                        amplitude_stat=str(eff_dist_cfg["amplitude_stat"]),
                        group_reduction=str(eff_dist_cfg["group_reduction"]),
                    ),
                    "coord_matrix": np.asarray(eff_coord_matrix, dtype=float),
                    "label": str(eff_option_cfg["tuning_label"]),
                }
            )
        if eff_options:
            if not expand_as_scalar:
                group_tuning_options["efficiency_vectors"] = eff_options
                group_distance_mats["efficiency_vectors"] = np.asarray(
                    eff_options[0]["distance_matrix"], dtype=float
                )
            group_coord_mats["efficiency_vectors"] = np.asarray(
                eff_options[0].get("coord_matrix", np.empty((len(dictionary_df), 0), dtype=float)),
                dtype=float,
            )
            fg = dict(eff_options[0]["config"])
            feature_groups["efficiency_vectors"] = fg
        group_weights["efficiency_vectors"] = 1.0

    # -----------------------------------------------------------------
    # Generic vector terms from config_feature_space.feature_groups
    # -----------------------------------------------------------------
    for raw_group_name, raw_group_cfg in feature_group_defs.items():
        group_name = str(raw_group_name).strip()
        if not group_name or group_name in {"rate_histogram", "efficiency_vectors"}:
            continue
        if not isinstance(raw_group_cfg, Mapping):
            continue
        if not _coerce_bool(raw_group_cfg.get("enabled", True), default=True):
            continue

        group_cfg = dict(raw_group_cfg)
        group_kind = _resolve_feature_group_kind(group_name, group_cfg)
        if group_kind == "efficiency_vectors":
            log.warning(
                "Feature group '%s' resolves to efficiency_vectors. Only the canonical 'efficiency_vectors' group name is currently supported in STEP 1.5 vector-term tuning; skipping.",
                group_name,
            )
            continue

        group_cols = [
            str(col)
            for col in group_cfg.get("feature_columns", [])
            if str(col) in dictionary_df.columns
        ]
        if not group_cols:
            continue
        expand_as_scalar = _coerce_bool(group_cfg.get("expand_components_as_scalar", False), default=False)
        if not expand_as_scalar:
            scalar_feature_cols = [col for col in scalar_feature_cols if col not in set(group_cols)]
        group_matrix = (
            dictionary_df[group_cols]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(dtype=float)
        )
        group_blend_mode = str(group_cfg.get("blend_mode", "normalized"))
        raw_min_valid_bins = group_cfg.get("min_valid_bins", 1)
        try:
            min_valid_bins = max(int(float(raw_min_valid_bins)), 1)
        except (TypeError, ValueError):
            min_valid_bins = 1
        options: list[dict[str, object]] = []
        for cand_cfg in _group_tuning_candidate_specs(group_cfg):
            if group_kind == "rate_histogram":
                resolved_cfg = _resolve_histogram_distance_cfg(cand_cfg)
                option_cfg = {
                    "distance": str(resolved_cfg["distance"]),
                    "blend_mode": group_blend_mode,
                    "min_weight": _coerce_nonnegative_float(group_cfg.get("min_weight"), 0.0),
                    "normalization": str(resolved_cfg["normalization"]),
                    "p_norm": float(resolved_cfg["p_norm"]),
                    "amplitude_weight": float(resolved_cfg["amplitude_weight"]),
                    "shape_weight": float(resolved_cfg["shape_weight"]),
                    "slope_weight": float(resolved_cfg["slope_weight"]),
                    "cdf_weight": float(resolved_cfg["cdf_weight"]),
                    "amplitude_stat": str(resolved_cfg["amplitude_stat"]),
                    "feature_columns": list(group_cols),
                    "tuning_label": _histogram_option_label(cand_cfg),
                    "expand_components_as_scalar": bool(expand_as_scalar),
                    "group_type": "rate_histogram",
                }
                coord_matrix, coord_meta = build_rate_histogram_local_linear_embedding(
                    hist_matrix=group_matrix,
                    feature_names=group_cols,
                    hist_cfg=option_cfg,
                )
                distance_matrix = _pairwise_histogram_distance_matrix(
                    group_matrix,
                    distance=str(resolved_cfg["distance"]),
                    normalization=str(resolved_cfg["normalization"]),
                    p_norm=float(resolved_cfg["p_norm"]),
                    amplitude_weight=float(resolved_cfg["amplitude_weight"]),
                    shape_weight=float(resolved_cfg["shape_weight"]),
                    slope_weight=float(resolved_cfg["slope_weight"]),
                    cdf_weight=float(resolved_cfg["cdf_weight"]),
                    amplitude_stat=str(resolved_cfg["amplitude_stat"]),
                )
            else:
                resolved_cfg = _resolve_ordered_vector_group_distance_cfg(cand_cfg)
                option_cfg = {
                    "distance": str(resolved_cfg["distance"]),
                    "blend_mode": group_blend_mode,
                    "min_weight": _coerce_nonnegative_float(group_cfg.get("min_weight"), 0.0),
                    "normalization": str(resolved_cfg["normalization"]),
                    "p_norm": float(resolved_cfg["p_norm"]),
                    "amplitude_weight": float(resolved_cfg["amplitude_weight"]),
                    "shape_weight": float(resolved_cfg["shape_weight"]),
                    "slope_weight": float(resolved_cfg["slope_weight"]),
                    "cdf_weight": float(resolved_cfg["cdf_weight"]),
                    "amplitude_stat": str(resolved_cfg["amplitude_stat"]),
                    "feature_columns": list(group_cols),
                    "min_valid_bins": int(min_valid_bins),
                    "tuning_label": _ordered_vector_option_label(cand_cfg),
                    "expand_components_as_scalar": bool(expand_as_scalar),
                    "group_type": "ordered_vector",
                }
                coord_matrix, coord_meta = build_ordered_vector_group_local_linear_embedding(
                    values=group_matrix,
                    feature_names=group_cols,
                    group_cfg=option_cfg,
                    label_prefix=f"group::{group_name}",
                )
                distance_matrix = _pairwise_ordered_vector_distance_matrix(
                    group_matrix,
                    normalization=str(resolved_cfg["normalization"]),
                    p_norm=float(resolved_cfg["p_norm"]),
                    amplitude_weight=float(resolved_cfg["amplitude_weight"]),
                    shape_weight=float(resolved_cfg["shape_weight"]),
                    slope_weight=float(resolved_cfg["slope_weight"]),
                    cdf_weight=float(resolved_cfg["cdf_weight"]),
                    amplitude_stat=str(resolved_cfg["amplitude_stat"]),
                    min_valid_bins=int(min_valid_bins),
                )
            option_cfg["local_linear_embedding"] = dict(coord_meta)
            options.append(
                {
                    "config": option_cfg,
                    "distance_matrix": np.asarray(distance_matrix, dtype=float),
                    "coord_matrix": np.asarray(coord_matrix, dtype=float),
                    "label": str(option_cfg["tuning_label"]),
                }
            )
        if not options:
            continue
        if not expand_as_scalar:
            group_tuning_options[group_name] = options
            group_distance_mats[group_name] = np.asarray(
                options[0]["distance_matrix"], dtype=float
            )
        group_coord_mats[group_name] = np.asarray(
            options[0].get("coord_matrix", np.empty((len(dictionary_df), 0), dtype=float)),
            dtype=float,
        )
        feature_groups[group_name] = dict(options[0]["config"])
        group_weights[group_name] = 1.0

    return (
        scalar_feature_cols,
        group_distance_mats,
        group_coord_mats,
        feature_groups,
        group_weights,
        group_tuning_options,
    )


def _weighted_median_1d(values: np.ndarray, weights: np.ndarray) -> float:
    vals = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    mask = np.isfinite(vals) & np.isfinite(w) & (w > 0.0)
    if not np.any(mask):
        return np.nan
    vals = vals[mask]
    w = w[mask]
    order = np.argsort(vals)
    vals = vals[order]
    w = w[order]
    s = float(np.sum(w))
    if not np.isfinite(s) or s <= 0.0:
        return np.nan
    cdf = np.cumsum(w) / s
    idx = int(np.searchsorted(cdf, 0.5, side="left"))
    idx = min(max(idx, 0), len(vals) - 1)
    return float(vals[idx])


def _loo_knn_error(
    dist_mat: np.ndarray, y_param: np.ndarray, k: int,
    z_feat: np.ndarray | None = None, ridge_lambda: float = 1e6,
    aggregation_mode: str = "weighted_mean",
) -> float:
    """LOO kNN estimation error from a precomputed distance matrix.

    When z_feat is provided and ridge_lambda < 1e5, uses locally weighted
    linear regression with ridge on slopes (free intercept).
    Otherwise falls back to IDW² weighted mean.

    Returns mean across parameters of median |relative error| %.
    """
    n = dist_mat.shape[0]
    n_params = y_param.shape[1]
    dm = dist_mat.copy()
    np.fill_diagonal(dm, np.inf)
    nn_idx = np.argpartition(dm, k, axis=1)[:, :k]
    nn_dist = np.take_along_axis(dm, nn_idx, axis=1)

    eps = 1e-12
    w = 1.0 / np.maximum(nn_dist, eps) ** 2  # (n, k)

    agg_mode = _normalize_aggregation_mode(aggregation_mode)
    use_local_linear = (agg_mode == "local_linear") and (z_feat is not None) and (ridge_lambda < 1e5)
    use_weighted_median = agg_mode == "weighted_median"

    if not use_local_linear and not use_weighted_median:
        # Vectorized IDW² weighted mean
        w_norm = w / np.maximum(w.sum(axis=1, keepdims=True), eps)
        all_estimated = np.stack(
            [np.sum(w_norm * y_param[nn_idx, j], axis=1) for j in range(n_params)],
            axis=1,
        )
    elif use_weighted_median:
        all_estimated = np.empty((n, n_params), dtype=float)
        for i in range(n):
            wi = w[i]
            w_sum = float(np.sum(wi))
            if not np.isfinite(w_sum) or w_sum <= eps:
                all_estimated[i, :] = np.nan
                continue
            wi = wi / w_sum
            yi = y_param[nn_idx[i]]
            for j in range(n_params):
                all_estimated[i, j] = _weighted_median_1d(yi[:, j], wi)
    else:
        # Local-linear ridge: design matrix [1, x-x₀], ridge only on slopes
        d = z_feat.shape[1]
        all_estimated = np.empty((n, n_params), dtype=float)
        reg = np.zeros(d + 1)
        reg[1:] = ridge_lambda
        reg_diag = np.diag(reg)
        all_neigh_params = y_param[nn_idx]  # (n, k, n_params)

        for i in range(n):
            wi = w[i]                                     # (k,)
            xi = z_feat[nn_idx[i]] - z_feat[i]            # (k, d)
            yi = all_neigh_params[i]                       # (k, n_params)
            Z = np.column_stack([np.ones(k), xi])          # (k, d+1)
            ZtW = Z.T * wi[np.newaxis, :]                  # (d+1, k)
            A = ZtW @ Z + reg_diag                         # (d+1, d+1)
            B = ZtW @ yi                                   # (d+1, n_params)
            try:
                Theta = np.linalg.solve(A, B)              # (d+1, n_params)
                all_estimated[i] = Theta[0]                # intercept row
            except np.linalg.LinAlgError:
                w_sum = max(float(np.sum(wi)), eps)
                all_estimated[i] = np.dot(wi, yi) / w_sum

    param_errs: list[float] = []
    for j in range(n_params):
        true_vals = y_param[:, j]
        estimated = all_estimated[:, j]
        abs_err = np.abs(estimated - true_vals)
        prange = max(float(np.ptp(true_vals)), 1e-12)
        denom = np.where(np.abs(true_vals) > 1e-12, np.abs(true_vals), prange)
        rel_pct = abs_err / denom * 100.0
        param_errs.append(float(np.nanmedian(rel_pct)))
    return float(np.mean(param_errs))


def _loo_knn_predictions(
    dist_mat: np.ndarray, y_param: np.ndarray, k: int,
    z_feat: np.ndarray | None = None, ridge_lambda: float = 1e6,
    aggregation_mode: str = "weighted_mean",
) -> np.ndarray:
    """Compute LOO kNN predictions for all dictionary entries.

    Returns (n, n_params) array of estimated values.
    Same logic as _loo_knn_error but returns estimates instead of scalar.
    """
    n = dist_mat.shape[0]
    n_params = y_param.shape[1]
    dm = dist_mat.copy()
    np.fill_diagonal(dm, np.inf)
    nn_idx = np.argpartition(dm, k, axis=1)[:, :k]
    nn_dist = np.take_along_axis(dm, nn_idx, axis=1)

    eps = 1e-12
    w = 1.0 / np.maximum(nn_dist, eps) ** 2

    agg_mode = _normalize_aggregation_mode(aggregation_mode)
    use_local_linear = (agg_mode == "local_linear") and (z_feat is not None) and (ridge_lambda < 1e5)
    use_weighted_median = agg_mode == "weighted_median"

    if not use_local_linear and not use_weighted_median:
        w_norm = w / np.maximum(w.sum(axis=1, keepdims=True), eps)
        return np.stack(
            [np.sum(w_norm * y_param[nn_idx, j], axis=1) for j in range(n_params)],
            axis=1,
        )
    if use_weighted_median:
        all_estimated = np.empty((n, n_params), dtype=float)
        for i in range(n):
            wi = w[i]
            w_sum = float(np.sum(wi))
            if not np.isfinite(w_sum) or w_sum <= eps:
                all_estimated[i, :] = np.nan
                continue
            wi = wi / w_sum
            yi = y_param[nn_idx[i]]
            for j in range(n_params):
                all_estimated[i, j] = _weighted_median_1d(yi[:, j], wi)
        return all_estimated

    d = z_feat.shape[1]
    all_estimated = np.empty((n, n_params), dtype=float)
    reg = np.zeros(d + 1)
    reg[1:] = ridge_lambda
    reg_diag = np.diag(reg)
    all_neigh_params = y_param[nn_idx]

    for i in range(n):
        wi = w[i]
        xi = z_feat[nn_idx[i]] - z_feat[i]
        yi = all_neigh_params[i]
        Z = np.column_stack([np.ones(k), xi])
        ZtW = Z.T * wi[np.newaxis, :]
        A = ZtW @ Z + reg_diag
        B = ZtW @ yi
        try:
            Theta = np.linalg.solve(A, B)
            all_estimated[i] = Theta[0]
        except np.linalg.LinAlgError:
            w_sum = max(float(np.sum(wi)), eps)
            all_estimated[i] = np.dot(wi, yi) / w_sum
    return all_estimated


def _plot_loo_true_vs_estimated(
    y_true: np.ndarray,
    y_est: np.ndarray,
    param_cols: list[str],
) -> None:
    """Plot LOO true vs estimated for each parameter (step 1.5 validation)."""
    n_params = y_true.shape[1]
    fig, axes = plt.subplots(n_params, 1, figsize=(5, 4.5 * n_params), squeeze=False)

    for j, pc in enumerate(param_cols):
        ax = axes[j, 0]
        t = y_true[:, j]
        e = y_est[:, j]
        m = np.isfinite(t) & np.isfinite(e)
        if not np.any(m):
            ax.set_title(pc, fontsize=9)
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
            continue

        ax.scatter(t[m], e[m], s=14, alpha=0.6, edgecolors="none", color="#4C78A8")
        lo = min(float(np.nanmin(t[m])), float(np.nanmin(e[m])))
        hi = max(float(np.nanmax(t[m])), float(np.nanmax(e[m])))
        pad = 0.05 * (hi - lo) if hi > lo else 0.1
        ax.plot([lo - pad, hi + pad], [lo - pad, hi + pad], "k--", lw=0.8, alpha=0.5)
        ax.set_xlim(lo - pad, hi + pad)
        ax.set_ylim(lo - pad, hi + pad)
        ax.set_xlabel(f"True {pc}", fontsize=8)
        ax.set_ylabel(f"LOO Estimated {pc}", fontsize=8)
        ax.set_title(pc, fontsize=9)
        ax.tick_params(labelsize=7)
        ax.set_aspect("equal", adjustable="box")
        ax.grid(True, alpha=0.15)

        rmse = float(np.sqrt(np.mean((t[m] - e[m]) ** 2)))
        mae = float(np.mean(np.abs(t[m] - e[m])))
        denom = np.where(np.abs(t[m]) > 1e-12, np.abs(t[m]),
                         max(float(np.ptp(t[m])), 1e-12))
        med_rel = float(np.median(np.abs(t[m] - e[m]) / denom * 100.0))
        ax.text(0.03, 0.97,
                f"RMSE={rmse:.4g}\nMAE={mae:.4g}\nMed.rel.err={med_rel:.2f}%",
                transform=ax.transAxes, fontsize=7, va="top",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

    fig.suptitle("LOO validation: True vs Estimated (dictionary entries)", fontsize=11, y=1.0)
    fig.tight_layout()
    path = PLOTS_DIR / "1_5_1_loo_true_vs_estimated.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info("Saved LOO true-vs-estimated plot: %s", path)


def _plot_loo_relative_error_histograms(
    y_true: np.ndarray,
    y_est: np.ndarray,
    param_cols: list[str],
) -> None:
    """Histogram of LOO relative errors for each parameter."""
    n_params = y_true.shape[1]
    fig, axes = plt.subplots(n_params, 1, figsize=(5, 3.5 * n_params), squeeze=False)

    for j, pc in enumerate(param_cols):
        ax = axes[j, 0]
        t = y_true[:, j]
        e = y_est[:, j]
        m = np.isfinite(t) & np.isfinite(e)
        if not np.any(m):
            ax.set_title(pc, fontsize=9)
            continue

        denom = np.where(np.abs(t[m]) > 1e-12, np.abs(t[m]),
                         max(float(np.ptp(t[m])), 1e-12))
        rel_pct = (e[m] - t[m]) / denom * 100.0

        ax.hist(rel_pct, bins=40, histtype="stepfilled",
                color="#4C78A8", alpha=0.6, edgecolor="#2a5080")
        ax.axvline(0, color="k", ls="--", lw=0.7, alpha=0.5)
        med = float(np.median(rel_pct))
        ax.axvline(med, color="red", ls="-", lw=0.9, alpha=0.7,
                   label=f"Median = {med:.2f}%")
        ax.set_xlabel(f"Rel. error {pc} [%]", fontsize=8)
        ax.set_ylabel("Count", fontsize=8)
        ax.set_title(pc, fontsize=9)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.15)
        ax.legend(fontsize=7)

    fig.suptitle("LOO validation: relative error distributions (dictionary)", fontsize=11, y=1.0)
    fig.tight_layout()
    path = PLOTS_DIR / "1_5_2_loo_relative_error_histograms.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info("Saved LOO relative-error histogram plot: %s", path)


def _holdout_inverse_mapping_score(
    *,
    dictionary_df: pd.DataFrame,
    dataset_df: pd.DataFrame,
    feature_cols: list[str],
    param_cols: list[str],
    distance_definition: dict[str, object],
    aggregation_mode: str,
    neighbor_count: int,
    ridge_lambda: float,
    use_in_coverage_only: bool = True,
) -> float:
    out = estimate_from_dataframes(
        dict_df=dictionary_df,
        data_df=dataset_df,
        feature_columns=feature_cols,
        param_columns=param_cols,
        include_global_rate=False,
        exclude_same_file=False,
        inverse_mapping_cfg={
            "neighbor_selection": "knn",
            "neighbor_count": int(neighbor_count),
            "weighting": "inverse_distance",
            "aggregation": str(aggregation_mode),
            "local_linear_ridge_lambda": float(ridge_lambda),
        },
        distance_definition={"available": True, **distance_definition},
    )
    if out.empty:
        return np.inf
    mask = np.ones(len(out), dtype=bool)
    if use_in_coverage_only and "in_coverage" in out.columns:
        mask &= out["in_coverage"].astype(bool).to_numpy()
    scores: list[float] = []
    for param_name in param_cols:
        est_col = f"est_{param_name}"
        if est_col not in out.columns or param_name not in dataset_df.columns:
            continue
        true_vals = pd.to_numeric(dataset_df[param_name], errors="coerce").to_numpy(dtype=float)
        est_vals = pd.to_numeric(out[est_col], errors="coerce").to_numpy(dtype=float)
        abs_err = np.abs(est_vals - true_vals)
        prange = max(float(np.ptp(true_vals[np.isfinite(true_vals)])), 1e-12)
        denom = np.where(np.abs(true_vals) > 1e-12, np.abs(true_vals), prange)
        rel_pct = abs_err / denom * 100.0
        rel_pct = rel_pct[np.isfinite(rel_pct) & mask]
        if rel_pct.size:
            scores.append(float(np.nanmedian(rel_pct)))
    if not scores:
        return np.inf
    return float(np.mean(scores))


def _select_holdout_inverse_mapping_configuration(
    *,
    dictionary_df: pd.DataFrame,
    dataset_df: pd.DataFrame,
    feature_cols: list[str],
    param_cols: list[str],
    base_distance_definition: dict[str, object],
    aggregation_candidates: Sequence[str],
    k_candidates: Sequence[int],
    lambda_grid: Sequence[float],
    default_k: int,
    default_lambda: float,
    use_in_coverage_only: bool = True,
) -> tuple[str, int, float, float, list[dict[str, object]]]:
    """Select the inverse-map runtime on the holdout dataset."""
    holdout_scores: list[dict[str, object]] = []
    best_aggregation = str(aggregation_candidates[0])
    best_k = int(default_k)
    best_lambda = float(default_lambda)
    best_score = np.inf

    for neighbor_count in k_candidates:
        for aggregation_mode in aggregation_candidates:
            lambda_candidates = (
                [float(v) for v in lambda_grid]
                if str(aggregation_mode) == "local_linear"
                else [1e6]
            )
            for ridge_lambda in lambda_candidates:
                score = _holdout_inverse_mapping_score(
                    dictionary_df=dictionary_df,
                    dataset_df=dataset_df,
                    feature_cols=feature_cols,
                    param_cols=param_cols,
                    distance_definition={
                        **base_distance_definition,
                        "optimal_aggregation": str(aggregation_mode),
                        "optimal_lambda": float(ridge_lambda),
                    },
                    aggregation_mode=str(aggregation_mode),
                    neighbor_count=int(neighbor_count),
                    ridge_lambda=float(ridge_lambda),
                    use_in_coverage_only=use_in_coverage_only,
                )
                holdout_scores.append(
                    {
                        "aggregation": str(aggregation_mode),
                        "neighbor_count": int(neighbor_count),
                        "ridge_lambda": float(ridge_lambda),
                        "score": round(float(score), 6),
                        "selected": False,
                    }
                )
                if score < best_score:
                    best_score = float(score)
                    best_aggregation = str(aggregation_mode)
                    best_k = int(neighbor_count)
                    best_lambda = float(ridge_lambda)

    for row in holdout_scores:
        row["selected"] = (
            row["aggregation"] == best_aggregation
            and int(row["neighbor_count"]) == best_k
            and float(row["ridge_lambda"]) == best_lambda
        )
    return best_aggregation, best_k, best_lambda, best_score, holdout_scores


def _rerank_distance_candidates_on_holdout(
    candidates: Sequence[Mapping[str, object]],
    *,
    top_n: int,
    scorer: Callable[[Mapping[str, object]], tuple[float, str, int, float]],
) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    """Re-rank the best dictionary candidates on the holdout dataset."""
    if not candidates:
        return None, []

    shortlist = sorted(
        candidates,
        key=lambda row: (
            float(row.get("dictionary_score", np.inf)),
            str(row.get("label", "")),
        ),
    )[: max(int(top_n), 1)]

    diagnostics: list[dict[str, object]] = []
    best_row: dict[str, object] | None = None
    best_score = np.inf
    for rank, candidate in enumerate(shortlist, start=1):
        holdout_score, holdout_agg, holdout_k, holdout_lambda = scorer(candidate)
        row = dict(candidate)
        row["shortlist_rank"] = int(rank)
        row["holdout_score"] = float(holdout_score)
        row["holdout_selected_aggregation"] = str(holdout_agg)
        row["holdout_selected_k"] = int(holdout_k)
        row["holdout_selected_lambda"] = float(holdout_lambda)
        row["selected"] = False
        diagnostics.append(row)
        if float(holdout_score) < best_score:
            best_score = float(holdout_score)
            best_row = row

    if best_row is not None:
        for row in diagnostics:
            row["selected"] = row is best_row
            row["holdout_delta_vs_selected"] = (
                float(row["holdout_score"]) - float(best_row["holdout_score"])
            )
    return best_row, diagnostics


def _auto_tune_distance(
    x_raw: np.ndarray,
    y_param: np.ndarray,
    param_cols: list[str],
    feature_cols: list[str],
    *,
    forced_mode: str | None = None,
    dictionary_df: pd.DataFrame | None = None,
    dataset_df: pd.DataFrame | None = None,
    inverse_cfg: dict | None = None,
    feature_group_defs: dict[str, dict[str, object]] | None = None,
    search_cfg: Mapping[str, object] | None = None,
) -> dict:
    """Auto-tune the feature-space distance definition on dictionary entries.

    Phase 1 — joint grid search over normalization × p × k × λ with uniform weights.
    Phase 2 — coordinate descent on per-feature weights at the best (norm, p, k, λ).
    """
    n = x_raw.shape[0]
    d_full = x_raw.shape[1]
    inverse_cfg = dict(inverse_cfg or {})
    resolved_search_cfg = _resolve_step15_search_cfg(search_cfg)
    normalization_grid = [str(v) for v in resolved_search_cfg["normalization_grid"]]
    p_grid = [float(v) for v in resolved_search_cfg["p_grid"]]
    aggregation_grid = [str(v) for v in resolved_search_cfg["aggregation_grid"]]
    weight_candidates = [float(v) for v in resolved_search_cfg["weight_candidates"]]
    k_candidates = [int(k) for k in resolved_search_cfg["k_grid"] if int(k) < n]
    lambda_grid = [float(v) for v in resolved_search_cfg["lambda_grid"]]
    distance_selection_objective = str(
        resolved_search_cfg.get("distance_selection_objective", "dictionary_loo")
    ).strip().lower()
    distance_selection_holdout_top_n = int(
        resolved_search_cfg.get("distance_selection_holdout_top_n", _DISTANCE_SELECTION_HOLDOUT_TOP_N)
    )
    inverse_mapping_selection_objective = str(
        resolved_search_cfg.get("inverse_mapping_selection_objective", "dictionary_loo")
    ).strip().lower()
    max_weight_rounds = int(resolved_search_cfg["max_weight_rounds"])
    max_group_option_combinations = int(resolved_search_cfg["max_group_option_combinations"])
    if not k_candidates:
        k_candidates = [min(max(n - 1, 1), _K_GRID[0])]

    scalar_feature_cols = list(feature_cols)
    group_distance_mats: dict[str, np.ndarray] = {}
    group_coord_mats: dict[str, np.ndarray] = {}
    feature_groups: dict[str, object] = {}
    group_weights_template: dict[str, float] = {}
    group_tuning_options: dict[str, list[dict[str, object]]] = {}
    if isinstance(dictionary_df, pd.DataFrame):
        (
            scalar_feature_cols,
            group_distance_mats,
            group_coord_mats,
            feature_groups,
            group_weights_template,
            group_tuning_options,
        ) = _build_feature_group_inputs(
            dictionary_df=dictionary_df,
            feature_cols=feature_cols,
            inverse_cfg=inverse_cfg,
            feature_group_defs=feature_group_defs,
        )
    scalar_feature_set = set(scalar_feature_cols)
    scalar_feature_indices = np.asarray(
        [idx for idx, col in enumerate(feature_cols) if col in scalar_feature_set],
        dtype=int,
    )
    x_raw_scalar = (
        x_raw[:, scalar_feature_indices]
        if scalar_feature_indices.size > 0
        else np.empty((n, 0), dtype=float)
    )
    d_scalar = x_raw_scalar.shape[1]
    active_group_distance_mats = dict(group_distance_mats)
    active_group_coord_mats = {
        str(name): np.asarray(value, dtype=float)
        for name, value in group_coord_mats.items()
    }
    active_feature_groups = {
        str(name): (dict(value) if isinstance(value, Mapping) else value)
        for name, value in feature_groups.items()
    }
    group_selected_option_idx = {
        str(name): 0
        for name, options in group_tuning_options.items()
        if options
    }
    total_group_metric_candidates = int(
        sum(max(len(options) - 1, 0) for options in group_tuning_options.values())
    )
    if total_group_metric_candidates > 0:
        log.info(
            "  STEP 1.5 vector-term metric tuning: %d multi-feature vector term(s), %d candidate override(s); selection is folded into the main grid loop.",
            len(group_tuning_options),
            total_group_metric_candidates,
        )
    initial_scalar_weights_full = np.zeros(len(feature_cols), dtype=float)
    for full_idx in scalar_feature_indices.tolist():
        initial_scalar_weights_full[int(full_idx)] = 1.0
    _log_unified_distance_term_list(
        feature_columns=feature_cols,
        scalar_feature_columns=scalar_feature_cols,
        scalar_weights=initial_scalar_weights_full,
        feature_groups=active_feature_groups,
        group_weights=group_weights_template,
        header="  Unified distance terms (X features --> 1 distance):",
    )
    scalar_grid_inactive = d_scalar == 0
    base_local_linear_dim = int(
        d_scalar
        + sum(
            int(mat.shape[1])
            for mat in active_group_coord_mats.values()
            if isinstance(mat, np.ndarray) and mat.ndim == 2
        )
    )
    aggregation_candidates = list(aggregation_grid)
    if base_local_linear_dim == 0:
        aggregation_candidates = [mode for mode in aggregation_candidates if mode != "local_linear"]
        if not aggregation_candidates:
            aggregation_candidates = ["weighted_mean", "weighted_median"]
    if scalar_grid_inactive:
        log.info(
            "  Vector-only tuning detected: 0 active 1-feature vector term(s). "
            "Normalization/p grid for 1-feature terms is inactive; tuning will vary multi-feature vector metrics, inverse-map aggregation, k, and term weights."
        )
    if base_local_linear_dim == 0:
        log.info("  Local-linear inverse mapping disabled for this run: no explicit local coordinate dimensions were resolved.")

    def _build_distance_matrix(
        *,
        z_scalar: np.ndarray,
        p_norm: float,
        scalar_weights: np.ndarray,
        group_weights: dict[str, float],
        group_distance_mats_local: dict[str, np.ndarray],
        feature_groups_local: dict[str, object],
    ) -> np.ndarray:
        if z_scalar.shape[1] > 0:
            base_dm = _weighted_lp_pairwise(z_scalar, p_norm, scalar_weights)
        else:
            base_dm = np.zeros((n, n), dtype=float)
        dm = _combine_pairwise_distance_terms(
            base_distances=base_dm,
            aux_terms=[
                (
                    group_distance_mats_local.get(name),
                    group_weights.get(name, 0.0),
                    str(feature_groups_local.get(name, {}).get("blend_mode", "normalized"))
                    if isinstance(feature_groups_local.get(name, {}), dict)
                    else "normalized",
                )
                for name in group_distance_mats_local.keys()
            ],
        )
        if dm.ndim == 2 and dm.shape[0] == dm.shape[1]:
            np.fill_diagonal(dm, 0.0)
        return dm

    def _build_local_linear_feature_matrix(
        *,
        z_scalar: np.ndarray,
        group_coord_mats_local: Mapping[str, np.ndarray],
    ) -> np.ndarray:
        parts: list[np.ndarray] = []
        if z_scalar.ndim == 2 and z_scalar.shape[1] > 0:
            parts.append(np.asarray(z_scalar, dtype=float))
        for group_name in sorted(group_coord_mats_local.keys()):
            coords = np.asarray(group_coord_mats_local[group_name], dtype=float)
            if coords.ndim != 2 or coords.shape[0] != n or coords.shape[1] == 0:
                continue
            parts.append(coords)
        if not parts:
            return np.empty((n, 0), dtype=float)
        return np.concatenate(parts, axis=1)

    def _has_active_dimensions(
        scalar_weights: np.ndarray,
        group_weights: dict[str, float],
    ) -> bool:
        if np.any(np.asarray(scalar_weights, dtype=float) > 0.0):
            return True
        return any(float(v) > 0.0 for v in group_weights.values())

    def _best_k_lambda_score(
        dm: np.ndarray,
        *,
        z_feat: np.ndarray,
        forced_k: int | None = None,
        forced_lambda: float | None = None,
        forced_aggregation: str | None = None,
    ) -> tuple[float, int, float, str]:
        best_local_score = np.inf
        best_local_k = int(forced_k if forced_k is not None else k_candidates[0])
        best_local_lambda = float(forced_lambda if forced_lambda is not None else lambda_grid[-1])
        best_local_aggregation = str(
            forced_aggregation if forced_aggregation is not None else aggregation_candidates[0]
        )
        k_iter = [int(forced_k)] if forced_k is not None else k_candidates
        aggregation_iter = (
            [str(forced_aggregation)]
            if forced_aggregation is not None
            else aggregation_candidates
        )
        for k in k_iter:
            for aggregation_mode in aggregation_iter:
                if aggregation_mode == "local_linear" and z_feat.shape[1] > 0:
                    lambda_iter = [float(forced_lambda)] if forced_lambda is not None else lambda_grid
                else:
                    lambda_iter = [1e6]
                for lam in lambda_iter:
                    score = _loo_knn_error(
                        dm,
                        y_param,
                        k,
                        z_feat=z_feat,
                        ridge_lambda=lam,
                        aggregation_mode=aggregation_mode,
                    )
                    if score < best_local_score:
                        best_local_score = score
                        best_local_k = int(k)
                        best_local_lambda = float(lam)
                        best_local_aggregation = str(aggregation_mode)
        return (
            float(best_local_score),
            int(best_local_k),
            float(best_local_lambda),
            str(best_local_aggregation),
        )

    # ── Phase 1: joint grid search  normalization × p × k ────────────
    if scalar_grid_inactive:
        norms_to_try = ["none"]
        ps_to_try = [1.0]
        forced_mode = None
    elif forced_mode is not None and forced_mode in _LEGACY_MODES:
        forced_p, forced_norm = _LEGACY_MODES[forced_mode]
        norms_to_try = [forced_norm]
        ps_to_try = [forced_p]
        log.info("  Forced mode '%s' → norm=%s, p=%.1f (skipping grid, tuning weights only)",
                 forced_mode, forced_norm, forced_p)
    elif forced_mode is not None:
        log.warning("Unknown forced mode '%s'; falling back to full auto-tune.", forced_mode)
        forced_mode = None
        norms_to_try = normalization_grid
        ps_to_try = p_grid
    else:
        norms_to_try = normalization_grid
        ps_to_try = p_grid

    uniform_scalar_w = np.ones(d_scalar, dtype=float)
    uniform_scalar_weights_full = np.zeros(len(feature_cols), dtype=float)
    for full_idx in scalar_feature_indices.tolist():
        uniform_scalar_weights_full[int(full_idx)] = 1.0

    def _rebuild_grid_candidate(
        *,
        norm: str,
        p_norm: float,
        selected_option_idx: Mapping[str, int],
    ) -> tuple[
        np.ndarray,
        np.ndarray,
        np.ndarray,
        dict[str, np.ndarray],
        dict[str, np.ndarray],
        dict[str, object],
        np.ndarray,
        np.ndarray,
    ]:
        center, scale = _compute_normalization_params(x_raw, norm)
        z_full = (x_raw - center) / scale
        z_scalar = (
            z_full[:, scalar_feature_indices]
            if scalar_feature_indices.size > 0
            else np.empty((n, 0), dtype=float)
        )
        combo_group_distance_mats = dict(group_distance_mats)
        combo_group_coord_mats = dict(group_coord_mats)
        combo_feature_groups = {
            str(name): (dict(value) if isinstance(value, Mapping) else value)
            for name, value in feature_groups.items()
        }
        for group_name, raw_idx in selected_option_idx.items():
            option_sets = group_tuning_options.get(str(group_name), [])
            if not option_sets:
                continue
            idx = int(np.clip(int(raw_idx), 0, len(option_sets) - 1))
            option = option_sets[idx]
            combo_group_distance_mats[str(group_name)] = np.asarray(
                option["distance_matrix"], dtype=float
            )
            combo_group_coord_mats[str(group_name)] = np.asarray(
                option.get("coord_matrix", np.empty((n, 0), dtype=float)),
                dtype=float,
            )
            combo_feature_groups[str(group_name)] = dict(option["config"])
        dm = _build_distance_matrix(
            z_scalar=z_scalar,
            p_norm=p_norm,
            scalar_weights=uniform_scalar_w,
            group_weights=group_weights_template,
            group_distance_mats_local=combo_group_distance_mats,
            feature_groups_local=combo_feature_groups,
        )
        z_feat = _build_local_linear_feature_matrix(
            z_scalar=z_scalar,
            group_coord_mats_local=combo_group_coord_mats,
        )
        return (
            center,
            scale,
            z_scalar,
            combo_group_distance_mats,
            combo_group_coord_mats,
            combo_feature_groups,
            dm,
            z_feat,
        )

    grid_results: dict[str, float] = {}
    grid_candidate_specs: list[dict[str, object]] = []
    best_score = np.inf
    best_norm = norms_to_try[0]
    best_p = ps_to_try[0]
    best_k = k_candidates[0]
    best_lambda = lambda_grid[-1]  # default to high λ (≈ IDW)
    best_aggregation = aggregation_candidates[0]
    best_center = np.zeros(d_full, dtype=float)
    best_scale = np.ones(d_full, dtype=float)
    best_group_weights = dict(group_weights_template)
    best_group_distance_mats = dict(active_group_distance_mats)
    best_group_coord_mats = dict(active_group_coord_mats)
    best_feature_groups = {
        str(name): (dict(value) if isinstance(value, Mapping) else value)
        for name, value in active_feature_groups.items()
    }
    best_group_selected_option_idx = dict(group_selected_option_idx)
    best_group_combo_label = "default"

    for norm in norms_to_try:
        center, scale = _compute_normalization_params(x_raw, norm)
        z_full = (x_raw - center) / scale
        z_scalar = (
            z_full[:, scalar_feature_indices]
            if scalar_feature_indices.size > 0
            else np.empty((n, 0), dtype=float)
        )
        for p in ps_to_try:
            combo_group_distance_mats = dict(group_distance_mats)
            combo_group_coord_mats = dict(group_coord_mats)
            combo_feature_groups = {
                str(name): (dict(value) if isinstance(value, Mapping) else value)
                for name, value in feature_groups.items()
            }
            combo_selected_option_idx = {
                str(name): 0
                for name, options in group_tuning_options.items()
                if options
            }

            baseline_dm = _build_distance_matrix(
                z_scalar=z_scalar,
                p_norm=p,
                scalar_weights=uniform_scalar_w,
                group_weights=group_weights_template,
                group_distance_mats_local=combo_group_distance_mats,
                feature_groups_local=combo_feature_groups,
            )
            baseline_z_feat = _build_local_linear_feature_matrix(
                z_scalar=z_scalar,
                group_coord_mats_local=combo_group_coord_mats,
            )
            combo_best_score, combo_best_k, combo_best_lambda, combo_best_aggregation = _best_k_lambda_score(
                baseline_dm,
                z_feat=baseline_z_feat,
            )

            if group_tuning_options:
                for _ in range(2):
                    changed = False
                    for group_name, option_sets in group_tuning_options.items():
                        current_idx = int(combo_selected_option_idx.get(group_name, 0))
                        best_idx = current_idx
                        best_idx_score = combo_best_score
                        for cand_idx, option in enumerate(option_sets):
                            if cand_idx == current_idx:
                                continue
                            trial_group_distance_mats = dict(combo_group_distance_mats)
                            trial_group_distance_mats[group_name] = np.asarray(
                                option["distance_matrix"], dtype=float
                            )
                            trial_group_coord_mats = dict(combo_group_coord_mats)
                            trial_group_coord_mats[group_name] = np.asarray(
                                option.get("coord_matrix", np.empty((n, 0), dtype=float)),
                                dtype=float,
                            )
                            trial_feature_groups = dict(combo_feature_groups)
                            trial_feature_groups[group_name] = dict(option["config"])
                            trial_dm = _build_distance_matrix(
                                z_scalar=z_scalar,
                                p_norm=p,
                                scalar_weights=uniform_scalar_w,
                                group_weights=group_weights_template,
                                group_distance_mats_local=trial_group_distance_mats,
                                feature_groups_local=trial_feature_groups,
                            )
                            trial_z_feat = _build_local_linear_feature_matrix(
                                z_scalar=z_scalar,
                                group_coord_mats_local=trial_group_coord_mats,
                            )
                            trial_score, _, _, _ = _best_k_lambda_score(
                                trial_dm,
                                z_feat=trial_z_feat,
                                forced_k=combo_best_k,
                                forced_lambda=combo_best_lambda,
                                forced_aggregation=combo_best_aggregation,
                            )
                            if trial_score < best_idx_score:
                                best_idx_score = trial_score
                                best_idx = cand_idx
                        if best_idx != current_idx:
                            option = option_sets[best_idx]
                            combo_selected_option_idx[group_name] = int(best_idx)
                            combo_group_distance_mats[group_name] = np.asarray(
                                option["distance_matrix"], dtype=float
                            )
                            combo_group_coord_mats[group_name] = np.asarray(
                                option.get("coord_matrix", np.empty((n, 0), dtype=float)),
                                dtype=float,
                            )
                            combo_feature_groups[group_name] = dict(option["config"])
                            combo_best_score = float(best_idx_score)
                            changed = True
                    if not changed:
                        break
                    tuned_dm = _build_distance_matrix(
                        z_scalar=z_scalar,
                        p_norm=p,
                        scalar_weights=uniform_scalar_w,
                        group_weights=group_weights_template,
                        group_distance_mats_local=combo_group_distance_mats,
                        feature_groups_local=combo_feature_groups,
                    )
                    tuned_z_feat = _build_local_linear_feature_matrix(
                        z_scalar=z_scalar,
                        group_coord_mats_local=combo_group_coord_mats,
                    )
                    combo_best_score, combo_best_k, combo_best_lambda, combo_best_aggregation = _best_k_lambda_score(
                        tuned_dm,
                        z_feat=tuned_z_feat,
                    )

            combo_label = "default"
            if combo_selected_option_idx:
                combo_label = " ; ".join(
                    f"{name}={group_tuning_options[name][idx].get('label', idx)}"
                    for name, idx in combo_selected_option_idx.items()
                    if name in group_tuning_options and group_tuning_options[name]
                )
            if scalar_grid_inactive:
                label = (
                    f"vector_only_agg={combo_best_aggregation}_vec={combo_label}"
                    f"_k={combo_best_k}_lam={combo_best_lambda:.0e}"
                )
            else:
                label = (
                    f"p={p:.1f}_{norm}_agg={combo_best_aggregation}_vec={combo_label}"
                    f"_k={combo_best_k}_lam={combo_best_lambda:.0e}"
                )
            grid_results[label] = round(combo_best_score, 4)
            grid_candidate_specs.append(
                {
                    "label": str(label),
                    "dictionary_score": float(combo_best_score),
                    "normalization": str(norm),
                    "p_norm": float(p),
                    "dictionary_selected_aggregation": str(combo_best_aggregation),
                    "dictionary_selected_k": int(combo_best_k),
                    "dictionary_selected_lambda": float(combo_best_lambda),
                    "group_metric_combo": str(combo_label),
                    "group_selected_option_idx": {
                        str(name): int(idx)
                        for name, idx in combo_selected_option_idx.items()
                    },
                }
            )
            if combo_best_score < best_score:
                best_score = combo_best_score
                best_norm = norm
                best_p = p
                best_k = combo_best_k
                best_lambda = combo_best_lambda
                best_aggregation = str(combo_best_aggregation)
                best_center = center.copy()
                best_scale = scale.copy()
                best_group_weights = dict(group_weights_template)
                best_group_distance_mats = dict(combo_group_distance_mats)
                best_group_coord_mats = dict(combo_group_coord_mats)
                best_feature_groups = {
                    str(name): (dict(value) if isinstance(value, Mapping) else value)
                    for name, value in combo_feature_groups.items()
                }
                best_group_selected_option_idx = {
                    str(name): int(idx)
                    for name, idx in combo_selected_option_idx.items()
                }
                best_group_combo_label = str(combo_label)
            if scalar_grid_inactive:
                log.info(
                    "  Vector-only grid best: %-30s → %7.3f %%",
                    label.split("vector_only_")[1],
                    combo_best_score,
                )
            else:
                log.info(
                    "  Grid  %-25s best: %-30s → %7.3f %%",
                    f"p={p:.1f}_{norm}",
                    label.split(f"{norm}_")[1],
                    combo_best_score,
                )

    if scalar_grid_inactive:
        log.info("  Best vector-only grid: agg=%s, k=%d, λ=%.0e (error %.3f %%)",
                 best_aggregation, best_k, best_lambda, best_score)
    else:
        log.info("  Best grid: norm=%s, p=%.1f, agg=%s, k=%d, λ=%.0e (error %.3f %%)",
                 best_norm, best_p, best_aggregation, best_k, best_lambda, best_score)
    if best_group_combo_label:
        log.info("  Best multi-feature vector-term metric combo at grid point: %s", best_group_combo_label)

    holdout_distance_selection: dict[str, object] | None = None
    if (
        distance_selection_objective == "holdout_dataset"
        and isinstance(dictionary_df, pd.DataFrame)
        and isinstance(dataset_df, pd.DataFrame)
        and not dataset_df.empty
        and grid_candidate_specs
    ):
        def _score_grid_candidate_on_holdout(
            candidate: Mapping[str, object],
        ) -> tuple[float, str, int, float]:
            (
                cand_center,
                cand_scale,
                _cand_z_scalar,
                _cand_group_distance_mats,
                _cand_group_coord_mats,
                cand_feature_groups,
                _cand_dm,
                _cand_z_feat,
            ) = _rebuild_grid_candidate(
                norm=str(candidate["normalization"]),
                p_norm=float(candidate["p_norm"]),
                selected_option_idx={
                    str(name): int(idx)
                    for name, idx in dict(candidate.get("group_selected_option_idx", {})).items()
                },
            )
            base_distance_definition = {
                "feature_columns": list(feature_cols),
                "scalar_feature_columns": list(scalar_feature_cols),
                "center": cand_center.tolist(),
                "scale": cand_scale.tolist(),
                "weights": uniform_scalar_weights_full.tolist(),
                "group_weights": {str(name): float(value) for name, value in group_weights_template.items()},
                "feature_groups": cand_feature_groups,
                "p_norm": float(candidate["p_norm"]),
                "optimal_k": int(candidate["dictionary_selected_k"]),
            }
            best_holdout_agg, best_holdout_k, best_holdout_lambda, best_holdout_score, _ = (
                _select_holdout_inverse_mapping_configuration(
                    dictionary_df=dictionary_df,
                    dataset_df=dataset_df,
                    feature_cols=feature_cols,
                    param_cols=param_cols,
                    base_distance_definition=base_distance_definition,
                    aggregation_candidates=aggregation_candidates,
                    k_candidates=k_candidates,
                    lambda_grid=lambda_grid,
                    default_k=int(candidate["dictionary_selected_k"]),
                    default_lambda=float(candidate["dictionary_selected_lambda"]),
                    use_in_coverage_only=True,
                )
            )
            return (
                float(best_holdout_score),
                str(best_holdout_agg),
                int(best_holdout_k),
                float(best_holdout_lambda),
            )

        selected_candidate, holdout_distance_diagnostics = _rerank_distance_candidates_on_holdout(
            grid_candidate_specs,
            top_n=distance_selection_holdout_top_n,
            scorer=_score_grid_candidate_on_holdout,
        )
        if selected_candidate is not None:
            holdout_distance_selection = {
                "objective": "holdout_dataset",
                "top_n_from_dictionary_grid": int(distance_selection_holdout_top_n),
                "selected_label": str(selected_candidate["label"]),
                "selected_dictionary_score": round(float(selected_candidate["dictionary_score"]), 6),
                "selected_holdout_score": round(float(selected_candidate["holdout_score"]), 6),
                "selected_aggregation": str(selected_candidate["holdout_selected_aggregation"]),
                "selected_k": int(selected_candidate["holdout_selected_k"]),
                "selected_lambda": float(selected_candidate["holdout_selected_lambda"]),
                "scores": holdout_distance_diagnostics,
            }
            best_norm = str(selected_candidate["normalization"])
            best_p = float(selected_candidate["p_norm"])
            best_k = int(selected_candidate["holdout_selected_k"])
            best_lambda = float(selected_candidate["holdout_selected_lambda"])
            best_aggregation = str(selected_candidate["holdout_selected_aggregation"])
            best_group_combo_label = str(selected_candidate.get("group_metric_combo", "default"))
            best_group_selected_option_idx = {
                str(name): int(idx)
                for name, idx in dict(selected_candidate.get("group_selected_option_idx", {})).items()
            }
            (
                best_center,
                best_scale,
                _best_z_scalar,
                best_group_distance_mats,
                best_group_coord_mats,
                best_feature_groups,
                _best_dm,
                _best_z_feat,
            ) = _rebuild_grid_candidate(
                norm=best_norm,
                p_norm=best_p,
                selected_option_idx=best_group_selected_option_idx,
            )
            best_group_weights = dict(group_weights_template)
            best_score = float(selected_candidate["dictionary_score"])
            log.info(
                "  Holdout distance re-ranking selected: %s (dictionary %.3f %% → holdout %.3f %%, agg=%s, k=%d, λ=%.2g)",
                str(selected_candidate["label"]),
                float(selected_candidate["dictionary_score"]),
                float(selected_candidate["holdout_score"]),
                best_aggregation,
                best_k,
                best_lambda,
            )

    grid_boundary_details = {
        "k": _grid_boundary_detail(
            axis_name="k",
            best_value=int(best_k),
            tested_values=[int(v) for v in k_candidates],
        ),
        "aggregation": _grid_boundary_detail(
            axis_name="aggregation",
            best_value=str(best_aggregation),
            tested_values=list(aggregation_candidates),
        ),
    }
    if best_aggregation == "local_linear":
        grid_boundary_details["lambda"] = _grid_boundary_detail(
            axis_name="lambda",
            best_value=float(best_lambda),
            tested_values=[float(v) for v in lambda_grid],
        )
    if not scalar_grid_inactive:
        grid_boundary_details["normalization"] = _grid_boundary_detail(
            axis_name="normalization",
            best_value=best_norm,
            tested_values=norms_to_try,
        )
        grid_boundary_details["p_norm"] = _grid_boundary_detail(
            axis_name="p_norm",
            best_value=float(best_p),
            tested_values=[float(v) for v in ps_to_try],
        )
    grid_boundary_axes = [
        axis_name
        for axis_name, detail in grid_boundary_details.items()
        if bool(detail.get("is_boundary"))
    ]
    grid_boundary_warning = bool(grid_boundary_axes) and forced_mode is None
    if grid_boundary_warning:
        parts: list[str] = []
        for axis_name in grid_boundary_axes:
            detail = grid_boundary_details[axis_name]
            side = "lower" if detail.get("on_lower_boundary") else "upper"
            parts.append(
                f"{axis_name}={detail.get('selected_value')} ({side} tested edge)"
            )
        log.warning(
            "Selected STEP 1.5 optimum lies on tested-grid boundary for %s. "
            "This suggests the current search grid may still be truncating a better solution.",
            ", ".join(parts),
        )

    # ── Phase 2: coordinate descent on per-feature weights (at best k) ──
    center = best_center
    scale = best_scale
    z_full = (x_raw - center) / scale
    z_scalar = (
        z_full[:, scalar_feature_indices]
        if scalar_feature_indices.size > 0
        else np.empty((n, 0), dtype=float)
    )
    active_group_distance_mats = dict(best_group_distance_mats)
    active_group_coord_mats = dict(best_group_coord_mats)
    active_feature_groups = {
        str(name): (dict(value) if isinstance(value, Mapping) else value)
        for name, value in best_feature_groups.items()
    }
    group_selected_option_idx = dict(best_group_selected_option_idx)
    local_linear_lambda = float(best_lambda)
    current_aggregation = str(best_aggregation)
    current_lambda = float(local_linear_lambda if current_aggregation == "local_linear" else 1e6)

    weights_scalar = np.ones(d_scalar, dtype=float)
    group_weights = _apply_group_weight_floors(
        best_group_weights,
        feature_groups=active_feature_groups,
    )
    current_score = best_score
    log.info(
        "  Starting weight tuning at the selected grid point: %d one-feature vector term(s), %d multi-feature vector term(s), up to %d round(s), %d candidate weight(s) per term.",
        d_scalar,
        len(group_weights),
        max_weight_rounds,
        max(len(weight_candidates) - 1, 0),
    )

    # Build mapping of tied scalar-local indices for groups expanded-as-scalar
    tied_group_local_indices: dict[str, list[int]] = {}
    for gname, gcfg in active_feature_groups.items():
        try:
            if bool(gcfg.get("expand_components_as_scalar", False)):
                cols: list[str] = []
                if isinstance(gcfg.get("groups"), list) and gcfg.get("groups"):
                    for gg in gcfg.get("groups", []):
                        cols.extend(list(gg.get("feature_columns", [])))
                elif isinstance(gcfg.get("feature_columns"), list):
                    cols = list(gcfg.get("feature_columns"))
                local_idxs: list[int] = []
                for col in cols:
                    if col in feature_cols:
                        full_idx = feature_cols.index(col)
                        # find local index in scalar_feature_indices
                        matches = np.where(scalar_feature_indices == full_idx)[0]
                        if matches.size:
                            local_idxs.append(int(matches[0]))
                if local_idxs:
                    tied_group_local_indices[str(gname)] = sorted(set(local_idxs))
        except Exception:
            continue

    for rnd in range(1, max_weight_rounds + 1):
        log.info("  Weight round %d/%d: evaluating feature weights...", rnd, max_weight_rounds)
        improved_count = 0
        # Tune untied scalar features first
        tied_local_flat = set(i for lst in tied_group_local_indices.values() for i in lst)
        untied_local_indices = [i for i in range(d_scalar) if i not in tied_local_flat]
        for idx_i, j in enumerate(untied_local_indices):
            # log progress occasionally
            if idx_i == 0 or (idx_i + 1) == len(untied_local_indices) or ((idx_i + 1) % 10 == 0):
                log.info("    Weight round %d progress: one-feature vector term %d/%d", rnd, idx_i + 1, len(untied_local_indices))
            w_orig = weights_scalar[j]
            best_wj = w_orig
            best_wj_score = current_score
            for wc in weight_candidates:
                if wc == w_orig:
                    continue
                trial_weights = weights_scalar.copy()
                trial_weights[j] = wc
                if not _has_active_dimensions(trial_weights, group_weights):
                    continue
                dm = _build_distance_matrix(
                    z_scalar=z_scalar,
                    p_norm=best_p,
                    scalar_weights=trial_weights,
                    group_weights=group_weights,
                    group_distance_mats_local=active_group_distance_mats,
                    feature_groups_local=active_feature_groups,
                )
                trial_z_feat = _build_local_linear_feature_matrix(
                    z_scalar=z_scalar,
                    group_coord_mats_local=active_group_coord_mats,
                )
                s = _loo_knn_error(
                    dm,
                    y_param,
                    best_k,
                    z_feat=trial_z_feat,
                    ridge_lambda=current_lambda,
                    aggregation_mode=current_aggregation,
                )
                if s < best_wj_score:
                    best_wj_score = s
                    best_wj = wc
            weights_scalar[j] = best_wj
            if best_wj != w_orig:
                current_score = best_wj_score
                improved_count += 1

        best_aggregation_round = current_aggregation
        best_aggregation_score = current_score
        for aggregation_mode in aggregation_candidates:
            if aggregation_mode == current_aggregation:
                continue
            trial_lambda = float(local_linear_lambda if aggregation_mode == "local_linear" else 1e6)
            dm = _build_distance_matrix(
                z_scalar=z_scalar,
                p_norm=best_p,
                scalar_weights=weights_scalar,
                group_weights=group_weights,
                group_distance_mats_local=active_group_distance_mats,
                feature_groups_local=active_feature_groups,
            )
            trial_z_feat = _build_local_linear_feature_matrix(
                z_scalar=z_scalar,
                group_coord_mats_local=active_group_coord_mats,
            )
            s = _loo_knn_error(
                dm,
                y_param,
                best_k,
                z_feat=trial_z_feat,
                ridge_lambda=trial_lambda,
                aggregation_mode=aggregation_mode,
            )
            if s < best_aggregation_score:
                best_aggregation_score = s
                best_aggregation_round = str(aggregation_mode)
        if best_aggregation_round != current_aggregation:
            current_aggregation = str(best_aggregation_round)
            current_lambda = float(local_linear_lambda if current_aggregation == "local_linear" else 1e6)
            current_score = best_aggregation_score
            improved_count += 1

        for group_idx, group_name in enumerate(group_weights.keys()):
            if group_idx == 0 or (group_idx + 1) == len(group_weights):
                log.info(
                    "    Weight round %d progress: multi-feature vector term %d/%d (%s)",
                    rnd,
                    group_idx + 1,
                    len(group_weights),
                    group_name,
                )
            option_sets = group_tuning_options.get(group_name, [])
            if len(option_sets) > 1:
                current_idx = int(group_selected_option_idx.get(group_name, 0))
                best_idx = current_idx
                best_idx_score = current_score
                for cand_idx, option in enumerate(option_sets):
                    if cand_idx == current_idx:
                        continue
                    trial_group_distance_mats = dict(active_group_distance_mats)
                    trial_group_distance_mats[group_name] = np.asarray(
                        option["distance_matrix"], dtype=float
                    )
                    trial_group_coord_mats = dict(active_group_coord_mats)
                    trial_group_coord_mats[group_name] = np.asarray(
                        option.get("coord_matrix", np.empty((n, 0), dtype=float)),
                        dtype=float,
                    )
                    trial_feature_groups = dict(active_feature_groups)
                    trial_feature_groups[group_name] = dict(option["config"])
                    dm = _build_distance_matrix(
                        z_scalar=z_scalar,
                        p_norm=best_p,
                        scalar_weights=weights_scalar,
                        group_weights=group_weights,
                        group_distance_mats_local=trial_group_distance_mats,
                        feature_groups_local=trial_feature_groups,
                    )
                    trial_z_feat = _build_local_linear_feature_matrix(
                        z_scalar=z_scalar,
                        group_coord_mats_local=trial_group_coord_mats,
                    )
                    s = _loo_knn_error(
                        dm,
                        y_param,
                        best_k,
                        z_feat=trial_z_feat,
                        ridge_lambda=current_lambda,
                        aggregation_mode=current_aggregation,
                    )
                    if s < best_idx_score:
                        best_idx_score = s
                        best_idx = cand_idx
                if best_idx != current_idx:
                    option = option_sets[best_idx]
                    group_selected_option_idx[group_name] = int(best_idx)
                    active_group_distance_mats[group_name] = np.asarray(
                        option["distance_matrix"], dtype=float
                    )
                    active_group_coord_mats[group_name] = np.asarray(
                        option.get("coord_matrix", np.empty((n, 0), dtype=float)),
                        dtype=float,
                    )
                    active_feature_groups[group_name] = dict(option["config"])
                    current_score = best_idx_score
                    improved_count += 1
            # If this group was expanded-as-scalar, tune a single tied scalar weight
            if group_name in tied_group_local_indices:
                local_idxs = tied_group_local_indices[group_name]
                # use first component as representative for current value
                w_orig = float(weights_scalar[local_idxs[0]]) if local_idxs else float(group_weights[group_name])
                best_wg = w_orig
                best_wg_score = current_score
                for wc in weight_candidates:
                    if float(wc) == w_orig:
                        continue
                    trial_weights = weights_scalar.copy()
                    for li in local_idxs:
                        trial_weights[li] = float(wc)
                    if not _has_active_dimensions(trial_weights, group_weights):
                        continue
                    dm = _build_distance_matrix(
                        z_scalar=z_scalar,
                        p_norm=best_p,
                        scalar_weights=trial_weights,
                        group_weights=group_weights,
                        group_distance_mats_local=active_group_distance_mats,
                        feature_groups_local=active_feature_groups,
                    )
                    trial_z_feat = _build_local_linear_feature_matrix(
                        z_scalar=z_scalar,
                        group_coord_mats_local=active_group_coord_mats,
                    )
                    s = _loo_knn_error(
                        dm,
                        y_param,
                        best_k,
                        z_feat=trial_z_feat,
                        ridge_lambda=current_lambda,
                        aggregation_mode=current_aggregation,
                    )
                    if s < best_wg_score:
                        best_wg_score = s
                        best_wg = float(wc)
                # apply tied weight to all components
                for li in local_idxs:
                    weights_scalar[li] = float(best_wg)
                if best_wg != w_orig:
                    current_score = best_wg_score
                    improved_count += 1
            else:
                min_group_weight = _group_min_weight(active_feature_groups, group_name)
                w_orig = max(float(group_weights[group_name]), min_group_weight)
                best_wg = w_orig
                best_wg_score = current_score
                candidate_group_weights = _resolve_group_weight_candidates(
                    feature_groups=active_feature_groups,
                    group_name=group_name,
                    raw_candidates=weight_candidates,
                )
                for wc in candidate_group_weights:
                    if float(wc) == w_orig:
                        continue
                    trial_group_weights = dict(group_weights)
                    trial_group_weights[group_name] = float(wc)
                    if not _has_active_dimensions(weights_scalar, trial_group_weights):
                        continue
                    dm = _build_distance_matrix(
                        z_scalar=z_scalar,
                        p_norm=best_p,
                        scalar_weights=weights_scalar,
                        group_weights=trial_group_weights,
                        group_distance_mats_local=active_group_distance_mats,
                        feature_groups_local=active_feature_groups,
                    )
                    trial_z_feat = _build_local_linear_feature_matrix(
                        z_scalar=z_scalar,
                        group_coord_mats_local=active_group_coord_mats,
                    )
                    s = _loo_knn_error(
                        dm,
                        y_param,
                        best_k,
                        z_feat=trial_z_feat,
                        ridge_lambda=current_lambda,
                        aggregation_mode=current_aggregation,
                    )
                    if s < best_wg_score:
                        best_wg_score = s
                        best_wg = float(wc)
                group_weights[group_name] = max(float(best_wg), min_group_weight)
                if best_wg != w_orig:
                    current_score = best_wg_score
                    improved_count += 1

        if not group_weights:
            nz = weights_scalar[weights_scalar > 0]
            if len(nz) > 0:
                weights_scalar = weights_scalar / float(np.mean(nz))
        n_active_scalar = int(np.sum(weights_scalar > 0))
        n_zero_scalar = d_scalar - n_active_scalar
        n_active_groups = int(sum(float(v) > 0.0 for v in group_weights.values()))
        log.info(
            "  Weight round %d: error %.3f %%, changed %d term(s), one-feature vectors active=%d/%d, multi-feature vectors active=%d/%d",
            rnd,
            current_score,
            improved_count,
            n_active_scalar,
            d_scalar,
            n_active_groups,
            len(group_weights),
        )
        if improved_count == 0:
            break

    weight_tuned_score = current_score
    weights_full = np.zeros(len(feature_cols), dtype=float)
    for local_idx, full_idx in enumerate(scalar_feature_indices.tolist()):
        weights_full[full_idx] = float(weights_scalar[local_idx])
    holdout_inverse_mapping_selection: dict[str, object] | None = None
    if (
        inverse_mapping_selection_objective == "holdout_dataset"
        and isinstance(dictionary_df, pd.DataFrame)
        and isinstance(dataset_df, pd.DataFrame)
        and not dataset_df.empty
    ):
        base_distance_definition = {
            "feature_columns": list(feature_cols),
            "scalar_feature_columns": list(scalar_feature_cols),
            "center": center.tolist(),
            "scale": scale.tolist(),
            "weights": weights_full.tolist() if 'weights_full' in locals() else [],
            "group_weights": {str(name): float(value) for name, value in group_weights.items()},
            "feature_groups": active_feature_groups,
            "p_norm": float(best_p),
            "optimal_k": int(best_k),
        }
        (
            best_holdout_agg,
            best_holdout_k,
            best_holdout_lambda,
            best_holdout_score,
            holdout_scores,
        ) = _select_holdout_inverse_mapping_configuration(
            dictionary_df=dictionary_df,
            dataset_df=dataset_df,
            feature_cols=feature_cols,
            param_cols=param_cols,
            base_distance_definition=base_distance_definition,
            aggregation_candidates=aggregation_candidates,
            k_candidates=k_candidates,
            lambda_grid=lambda_grid,
            default_k=int(best_k),
            default_lambda=float(local_linear_lambda),
            use_in_coverage_only=True,
        )
        holdout_inverse_mapping_selection = {
            "objective": "holdout_dataset",
            "neighbor_count": int(best_holdout_k),
            "scores": holdout_scores,
            "selected_aggregation": str(best_holdout_agg),
            "selected_lambda": float(best_holdout_lambda),
            "selected_score": round(float(best_holdout_score), 6),
        }
        current_aggregation = str(best_holdout_agg)
        best_k = int(best_holdout_k)
        current_lambda = float(best_holdout_lambda if current_aggregation == "local_linear" else 1e6)
        log.info(
            "  Holdout inverse-map selection: agg=%s at k=%d λ=%.2g (mean median-relerr %.3f %%)",
            current_aggregation,
            best_k,
            current_lambda,
            best_holdout_score,
        )

    mode_label = "vector_only" if scalar_grid_inactive else f"p{best_p:.1f}_{best_norm}"
    log.info(
        "Selected distance: %s, agg=%s, k=%d, λ=%.0e, weights tuned (grid %.3f %% → tuned %.3f %%)",
        mode_label, current_aggregation, best_k, current_lambda, best_score, weight_tuned_score,
    )
    if group_weights:
        final_group_parts: list[str] = []
        for group_name, group_weight in group_weights.items():
            selected_idx = int(group_selected_option_idx.get(group_name, 0))
            selected_label = ""
            if group_tuning_options.get(group_name):
                selected_label = str(
                    group_tuning_options[group_name][selected_idx].get("label", "")
                )
            if not selected_label:
                selected_label = str(
                    active_feature_groups.get(group_name, {}).get("distance", "default")
                )
            final_group_parts.append(
                f"{group_name}={selected_label} (weight={float(group_weight):g})"
            )
        log.info("  Final multi-feature vector-term metric selection after weight tuning: %s", " ; ".join(final_group_parts))
    _log_unified_distance_term_list(
        feature_columns=feature_cols,
        scalar_feature_columns=scalar_feature_cols,
        scalar_weights=weights_full,
        feature_groups=active_feature_groups,
        group_weights=group_weights,
        header="  Final unified distance terms (X features --> 1 distance):",
    )

    # Compute dictionary internal 1st-NN distances for coverage threshold.
    # Step 2.1 reports best_distance = 1st NN, so the threshold must match.
    dm_final = _build_distance_matrix(
        z_scalar=z_scalar,
        p_norm=best_p,
        scalar_weights=weights_scalar,
        group_weights=group_weights,
        group_distance_mats_local=active_group_distance_mats,
        feature_groups_local=active_feature_groups,
    )
    np.fill_diagonal(dm_final, np.inf)
    nn1_dists = np.min(dm_final, axis=1)
    loo_dist_p95 = float(np.percentile(nn1_dists, 95))
    loo_dist_max = float(np.max(nn1_dists))
    log.info(
        "  Dictionary internal 1st-NN distances: median=%.2f, p95=%.2f, max=%.2f",
        float(np.median(nn1_dists)), loo_dist_p95, loo_dist_max,
    )

    group_candidate_score_diagnostics: dict[str, list[dict[str, object]]] = {}
    if group_tuning_options:
        for group_name, option_sets in group_tuning_options.items():
            diag_rows: list[dict[str, object]] = []
            selected_idx = int(group_selected_option_idx.get(group_name, 0))
            selected_score: float | None = None
            for cand_idx, option in enumerate(option_sets):
                trial_group_distance_mats = dict(active_group_distance_mats)
                trial_group_distance_mats[group_name] = np.asarray(
                    option["distance_matrix"], dtype=float
                )
                trial_group_coord_mats = dict(active_group_coord_mats)
                trial_group_coord_mats[group_name] = np.asarray(
                    option.get("coord_matrix", np.empty((n, 0), dtype=float)),
                    dtype=float,
                )
                trial_feature_groups = dict(active_feature_groups)
                trial_feature_groups[group_name] = dict(option["config"])
                dm = _build_distance_matrix(
                    z_scalar=z_scalar,
                    p_norm=best_p,
                    scalar_weights=weights_scalar,
                    group_weights=group_weights,
                    group_distance_mats_local=trial_group_distance_mats,
                    feature_groups_local=trial_feature_groups,
                )
                trial_z_feat = _build_local_linear_feature_matrix(
                    z_scalar=z_scalar,
                    group_coord_mats_local=trial_group_coord_mats,
                )
                score = _loo_knn_error(
                    dm,
                    y_param,
                    best_k,
                    z_feat=trial_z_feat,
                    ridge_lambda=current_lambda,
                    aggregation_mode=current_aggregation,
                )
                if cand_idx == selected_idx:
                    selected_score = float(score)
                diag_rows.append(
                    {
                        "candidate_index": int(cand_idx),
                        "label": str(option.get("label", cand_idx)),
                        "score": round(float(score), 6),
                        "selected": bool(cand_idx == selected_idx),
                    }
                )
            if selected_score is None:
                selected_score = float(weight_tuned_score)
            for row in diag_rows:
                row["delta_vs_selected"] = round(float(row["score"]) - float(selected_score), 6)
            diag_rows.sort(key=lambda item: (float(item["score"]), int(item["candidate_index"])))
            group_candidate_score_diagnostics[str(group_name)] = diag_rows
            score_min = min(float(row["score"]) for row in diag_rows)
            score_max = max(float(row["score"]) for row in diag_rows)
            log.info(
                "  Multi-feature vector-term candidate scores (%s): best=%.3f %%, selected=%.3f %%, spread=%.3f %%, n=%d",
                group_name,
                score_min,
                float(selected_score),
                score_max - score_min,
                len(diag_rows),
            )

    return {
        "selected_mode": mode_label,
        "parameter_columns": list(param_cols),
        "p_norm": float(best_p),
        "normalization": best_norm,
        "optimal_aggregation": str(current_aggregation),
        "optimal_k": best_k,
        "optimal_lambda": current_lambda,
        "feature_columns": list(feature_cols),
        "scalar_feature_columns": list(scalar_feature_cols),
        "one_feature_vector_columns": list(scalar_feature_cols),
        "center": center.tolist(),
        "scale": scale.tolist(),
        "weights": weights_full.tolist(),
        "group_weights": {str(name): float(value) for name, value in group_weights.items()},
        "feature_groups": active_feature_groups,
        "feature_group_tuning_selection": {
            str(name): {
                "selected_index": int(group_selected_option_idx.get(name, 0)),
                "selected_label": str(
                    group_tuning_options.get(name, [{}])[int(group_selected_option_idx.get(name, 0))].get("label", "")
                )
                if group_tuning_options.get(name)
                else "",
                "n_candidates": int(len(group_tuning_options.get(name, []))),
            }
            for name in group_weights.keys()
        },
        "grid_results": grid_results,
        "grid_best_score": round(best_score, 4),
        "grid_best_group_metric_combo": str(best_group_combo_label),
        "scalar_grid_inactive": bool(scalar_grid_inactive),
        "one_feature_vector_grid_inactive": bool(scalar_grid_inactive),
        "distance_selection_objective": distance_selection_objective,
        "holdout_distance_selection": holdout_distance_selection,
        "_grid_boundary_warning_comment": (
            "If grid_boundary_warning is true, the selected STEP 1.5 optimum "
            "touched at least one boundary of the tested search grid. "
            "That suggests there may be room for improvement by expanding the grid."
        ),
        "grid_boundary_warning": grid_boundary_warning,
        "grid_boundary_axes": grid_boundary_axes,
        "grid_boundary_details": grid_boundary_details,
        "weight_tuned_score": round(weight_tuned_score, 4),
        "inverse_mapping_selection_objective": inverse_mapping_selection_objective,
        "holdout_inverse_mapping_selection": holdout_inverse_mapping_selection,
        "group_candidate_score_diagnostics": group_candidate_score_diagnostics,
        "n_active_features": int(np.sum(weights_full > 0)),
        "n_zeroed_features": int(np.sum(weights_full == 0)),
        "n_active_feature_groups": int(sum(float(v) > 0.0 for v in group_weights.values())),
        "n_active_total_dimensions": int(np.sum(weights_full > 0))
        + int(sum(float(v) > 0.0 for v in group_weights.values())),
        "local_linear_feature_dim": int(
            z_scalar.shape[1]
            + sum(
                int(mat.shape[1])
                for mat in active_group_coord_mats.values()
                if isinstance(mat, np.ndarray) and mat.ndim == 2
            )
        ),
        "tuning_metric": "median_relative_error_pct",
        "loo_distance_p95": round(loo_dist_p95, 4),
        "loo_distance_max": round(loo_dist_max, 4),
    }


# ── Main ─────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="STEP 1.5: Auto-tune feature-space distance definition for downstream estimation.",
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--dictionary-csv", default=None)
    args = parser.parse_args()

    config = _load_config(Path(args.config))
    cfg_15 = config.get("step_1_5", {}) or {}
    cfg_12 = config.get("step_1_2", {}) or {}

    # ── Locate inputs ────────────────────────────────────────────────
    dict_cfg = cfg_15.get("dictionary_csv")
    if args.dictionary_csv:
        dictionary_path = Path(args.dictionary_csv).expanduser()
    elif dict_cfg not in (None, "", "null", "None"):
        dictionary_path = Path(str(dict_cfg)).expanduser()
    else:
        dictionary_path = DEFAULT_DICTIONARY

    if not dictionary_path.exists():
        log.error("Dictionary CSV not found: %s", dictionary_path)
        return 1

    # Load dictionary
    dictionary = pd.read_csv(dictionary_path, low_memory=False)
    if dictionary.empty:
        log.error("Input dictionary is empty: %s", dictionary_path)
        return 1
    log.info("Loaded dictionary: %s (%d rows)", dictionary_path, len(dictionary))

    # Feature columns
    feat_path = cfg_15.get("selected_feature_columns_json")
    if feat_path and Path(feat_path).exists():
        selected_features_path = Path(feat_path)
    else:
        selected_features_path = DEFAULT_SELECTED_FEATURES

    feature_cols = _load_selected_features(selected_features_path)
    if not feature_cols:
        log.error("No feature columns loaded from %s", selected_features_path)
        return 1
    feature_cols = [c for c in feature_cols if c in dictionary.columns]
    if not feature_cols:
        log.error("No feature columns found in dictionary.")
        return 1

    feature_group_config_path = resolve_feature_group_config_path(
        PIPELINE_DIR,
        config=config,
        step_cfg=cfg_15 if isinstance(cfg_15, dict) else {},
    )
    feature_group_all = load_feature_space_config(feature_group_config_path)
    if isinstance(feature_group_all.get("step_1_5", {}), dict):
        feature_space_cfg = feature_group_all.get("step_1_5", {})
    elif isinstance(feature_group_all.get("step_1_2", {}), dict):
        feature_space_cfg = feature_group_all.get("step_1_2", {})
    else:
        feature_space_cfg = feature_group_all if isinstance(feature_group_all, dict) else {}
    feature_group_defs, feature_group_info = resolve_feature_space_group_definitions(
        available_columns=dictionary.columns,
        feature_space_cfg=feature_space_cfg,
    )
    if feature_group_defs:
        log.info(
            "Feature-group config from %s: %s",
            feature_group_config_path,
            {
                name: len(cfg.get("feature_columns", []))
                for name, cfg in feature_group_defs.items()
                if isinstance(cfg, dict)
            },
        )

    # Parameter columns
    param_cols_loaded = _load_parameter_space_columns(
        DEFAULT_PARAMETER_SPACE,
        available_columns=dictionary.columns,
    )
    param_cols = param_cols_loaded or ["flux_cm2_min", "eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4"]
    param_cols = [c for c in param_cols if c in dictionary.columns]
    if not param_cols:
        log.error("No parameter columns found in dictionary.")
        return 1

    log.info("Feature columns: %d", len(feature_cols))
    log.info("Parameter columns: %s", param_cols)

    # ── Prepare numeric matrices ─────────────────────────────────────
    try:
        dictionary_valid, tuning_feature_space_completeness = _filter_complete_tuning_rows(
            dictionary,
            feature_cols=feature_cols,
            param_cols=param_cols,
            label="dictionary",
        )
    except ValueError as exc:
        log.error("%s", exc)
        return 1
    if int(tuning_feature_space_completeness.get("rows_removed", 0)) > 0:
        log.info(
            "Dropped %d dictionary row(s) with incomplete tuning feature/parameter space; kept %d/%d rows.",
            int(tuning_feature_space_completeness.get("rows_removed", 0)),
            int(tuning_feature_space_completeness.get("rows_kept", 0)),
            int(tuning_feature_space_completeness.get("input_rows", len(dictionary))),
        )
    if len(dictionary_valid) < 3:
        log.error("Not enough valid rows for tuning (need >=3, got %d).", len(dictionary_valid))
        return 1

    feat_num = (
        dictionary_valid[feature_cols]
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
    )
    par_num = (
        dictionary_valid[param_cols]
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
    )

    x_raw = feat_num.to_numpy(dtype=float)
    y_param = par_num.to_numpy(dtype=float)
    log.info("Valid dictionary rows for tuning: %d, feature dims: %d", len(dictionary_valid), x_raw.shape[1])

    dataset_valid: pd.DataFrame | None = None
    holdout_feature_space_completeness: dict[str, object] | None = None
    holdout_overlap_exclusion: dict[str, object] | None = None
    distance_selection_objective_cfg = str(
        cfg_15.get("distance_selection_objective", "dictionary_loo")
    ).strip().lower()
    inverse_mapping_selection_objective_cfg = str(
        cfg_15.get("inverse_mapping_selection_objective", "dictionary_loo")
    ).strip().lower()
    holdout_objectives = {
        distance_selection_objective_cfg,
        inverse_mapping_selection_objective_cfg,
    }
    if "holdout_dataset" in holdout_objectives:
        dataset_cfg = cfg_15.get("dataset_csv")
        if dataset_cfg not in (None, "", "null", "None"):
            dataset_path = Path(str(dataset_cfg)).expanduser()
        else:
            dataset_path = DEFAULT_DATASET
        if dataset_path.exists():
            dataset_loaded = pd.read_csv(dataset_path, low_memory=False)
            if not dataset_loaded.empty:
                try:
                    dataset_valid, holdout_feature_space_completeness = _filter_complete_tuning_rows(
                        dataset_loaded.reset_index(drop=True),
                        feature_cols=feature_cols,
                        param_cols=param_cols,
                        label="holdout_dataset",
                    )
                except ValueError as exc:
                    log.error("%s", exc)
                    return 1
                if int(holdout_feature_space_completeness.get("rows_removed", 0)) > 0:
                    log.info(
                        "Dropped %d holdout row(s) with incomplete tuning feature/parameter space; kept %d/%d rows.",
                        int(holdout_feature_space_completeness.get("rows_removed", 0)),
                        int(holdout_feature_space_completeness.get("rows_kept", 0)),
                        int(holdout_feature_space_completeness.get("input_rows", len(dataset_loaded))),
                    )
                dataset_valid, holdout_overlap_exclusion = _exclude_holdout_rows_with_dictionary_parameter_overlap(
                    dictionary_valid,
                    dataset_valid,
                )
                if int(holdout_overlap_exclusion.get("rows_removed", 0)) > 0:
                    log.info(
                        "Dropped %d holdout row(s) whose physical parameter vector already exists in dictionary; kept %d/%d rows.",
                        int(holdout_overlap_exclusion.get("rows_removed", 0)),
                        int(holdout_overlap_exclusion.get("rows_kept", 0)),
                        int(holdout_overlap_exclusion.get("input_rows", len(dataset_valid))),
                    )
                if dataset_valid.empty:
                    log.warning(
                        "Holdout dataset became empty after completeness and dictionary-overlap filtering; STEP 1.5 will fall back to dictionary-only selection."
                    )
                log.info("Loaded holdout dataset for inverse-map selection: %s (%d rows)", dataset_path, len(dataset_valid))
        else:
            log.warning("Requested holdout inverse-map selection, but dataset CSV not found: %s", dataset_path)

    # ── Run distance tuning ──────────────────────────────────────────
    cfg_distance = str(cfg_15.get("feature_distance_definition", "auto")).strip().lower()
    forced_mode = None if cfg_distance == "auto" else cfg_distance
    log.info("Distance-mode selection: %s", "auto-tune" if forced_mode is None else f"forced={forced_mode}")
    step21_cfg = config.get("step_2_1", {}) or {}
    inverse_cfg = resolve_inverse_mapping_cfg(
        inverse_mapping_cfg=step21_cfg.get("inverse_mapping", {}) if isinstance(step21_cfg, dict) else {},
        interpolation_k=None,
    )

    tune_result = _auto_tune_distance(
        x_raw, y_param, param_cols, feature_cols,
        forced_mode=forced_mode,
        dictionary_df=dictionary_valid,
        dataset_df=dataset_valid,
        inverse_cfg=inverse_cfg,
        feature_group_defs=feature_group_defs,
        search_cfg=cfg_15 if isinstance(cfg_15, dict) else {},
    )
    tune_result["feature_space_group_selection"] = feature_group_info
    tune_result["feature_space_config_path"] = str(feature_group_config_path)
    tune_result["feature_group_config_path"] = str(feature_group_config_path)
    tune_result["tuning_feature_space_completeness"] = tuning_feature_space_completeness
    tune_result["holdout_feature_space_completeness"] = holdout_feature_space_completeness
    tune_result["holdout_overlap_exclusion"] = holdout_overlap_exclusion

    # ── Save artifact ────────────────────────────────────────────────
    out_path = FILES_DIR / "distance_definition.json"
    out_path.write_text(json.dumps(tune_result, indent=2), encoding="utf-8")
    log.info("Wrote distance definition artifact: %s", out_path)
    diag_rows: list[dict[str, object]] = []
    diag_map = tune_result.get("group_candidate_score_diagnostics", {})
    if isinstance(diag_map, Mapping):
        for group_name, rows in diag_map.items():
            if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
                continue
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                diag_rows.append(
                    {
                        "group_name": str(group_name),
                        "candidate_index": int(row.get("candidate_index", -1)),
                        "label": str(row.get("label", "")),
                        "score": float(row.get("score", np.nan)),
                        "delta_vs_selected": float(row.get("delta_vs_selected", np.nan)),
                        "selected": bool(row.get("selected", False)),
                    }
                )
    if diag_rows:
        diag_df = pd.DataFrame(diag_rows)
        diag_csv = FILES_DIR / "group_candidate_score_diagnostics.csv"
        diag_df.to_csv(diag_csv, index=False)
        log.info("Wrote vector-term candidate-score diagnostics: %s", diag_csv)

    # ── LOO validation plots ─────────────────────────────────────────
    log.info("Starting final LOO validation predictions for STEP 1.5 plots...")
    center = np.asarray(tune_result["center"])
    scale = np.asarray(tune_result["scale"])
    weights_arr = np.asarray(tune_result["weights"])
    group_weights = tune_result.get("group_weights", {})
    feature_groups = tune_result.get("feature_groups", {})
    z_tuned = (x_raw - center) / scale
    scalar_feature_cols = [
        str(col)
        for col in tune_result.get("scalar_feature_columns", [])
        if str(col) in feature_cols
    ]
    scalar_idx = np.asarray(
        [idx for idx, col in enumerate(feature_cols) if str(col) in set(scalar_feature_cols)],
        dtype=int,
    )
    z_tuned_scalar = (
        z_tuned[:, scalar_idx]
        if scalar_idx.size > 0
        else np.empty((len(z_tuned), 0), dtype=float)
    )
    scalar_weights = weights_arr[scalar_idx] if scalar_idx.size > 0 else np.asarray([], dtype=float)
    local_linear_parts: list[np.ndarray] = []
    if z_tuned_scalar.ndim == 2 and z_tuned_scalar.shape[1] > 0:
        local_linear_parts.append(z_tuned_scalar)
    aux_terms: list[tuple[np.ndarray | None, float, str]] = []
    if isinstance(group_weights, dict) and isinstance(feature_groups, dict):
        for raw_group_name, raw_weight in group_weights.items():
            group_name = str(raw_group_name).strip()
            if not group_name:
                continue
            try:
                group_weight = float(raw_weight)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(group_weight) or group_weight <= 0.0:
                continue
            group_cfg = feature_groups.get(group_name, {})
            if not isinstance(group_cfg, Mapping):
                continue
            expand_as_scalar = _coerce_bool(group_cfg.get("expand_components_as_scalar", False), default=False)
            group_kind = _resolve_feature_group_kind(group_name, group_cfg)
            blend_mode = str(group_cfg.get("blend_mode", "normalized"))

            if group_kind == "efficiency_vectors":
                eff_payloads = _prepare_efficiency_vector_group_payloads(
                    dict_df=dictionary_valid,
                    data_df=dictionary_valid,
                )
                eff_payloads = _filter_efficiency_vector_payloads(
                    eff_payloads,
                    feature_groups_cfg=group_cfg if isinstance(group_cfg, dict) else None,
                    selected_feature_columns=feature_cols,
                )
                if not eff_payloads:
                    continue
                eff_dist_cfg = _resolve_efficiency_vector_distance_cfg(
                    group_cfg if isinstance(group_cfg, dict) else {}
                )
                if not expand_as_scalar:
                    aux_terms.append(
                        (
                            _pairwise_efficiency_vector_distance_matrix(
                                eff_payloads,
                                fiducial=dict(eff_dist_cfg["fiducial"]),
                                uncertainty_floor=float(eff_dist_cfg["uncertainty_floor"]),
                                min_valid_bins_per_vector=int(eff_dist_cfg["min_valid_bins_per_vector"]),
                                normalization=str(eff_dist_cfg["normalization"]),
                                p_norm=float(eff_dist_cfg["p_norm"]),
                                amplitude_weight=float(eff_dist_cfg["amplitude_weight"]),
                                shape_weight=float(eff_dist_cfg["shape_weight"]),
                                slope_weight=float(eff_dist_cfg["slope_weight"]),
                                cdf_weight=float(eff_dist_cfg["cdf_weight"]),
                                amplitude_stat=str(eff_dist_cfg["amplitude_stat"]),
                                group_reduction=str(eff_dist_cfg["group_reduction"]),
                            ),
                            float(group_weight),
                            blend_mode,
                        )
                    )
                eff_embed_meta = (
                    group_cfg.get("local_linear_embedding", {})
                    if isinstance(group_cfg, Mapping)
                    else {}
                )
                eff_embed, _ = build_efficiency_vector_local_linear_embedding(
                    payloads=eff_payloads,
                    eff_cfg=group_cfg if isinstance(group_cfg, Mapping) else {},
                    source="dict",
                    standardization=eff_embed_meta if isinstance(eff_embed_meta, Mapping) else None,
                )
                if eff_embed.ndim == 2 and eff_embed.shape[0] == len(z_tuned):
                    local_linear_parts.append(eff_embed)
                continue

            group_cols = [
                str(col)
                for col in group_cfg.get("feature_columns", [])
                if str(col) in dictionary_valid.columns
            ]
            if not group_cols:
                continue
            group_matrix = (
                dictionary_valid[group_cols]
                .apply(pd.to_numeric, errors="coerce")
                .to_numpy(dtype=float)
            )
            if group_kind == "rate_histogram":
                hist_dist_cfg = _resolve_histogram_distance_cfg(group_cfg)
                if not expand_as_scalar:
                    aux_terms.append(
                        (
                            _pairwise_histogram_distance_matrix(
                                group_matrix,
                                distance=str(hist_dist_cfg["distance"]),
                                normalization=str(hist_dist_cfg["normalization"]),
                                p_norm=float(hist_dist_cfg["p_norm"]),
                                amplitude_weight=float(hist_dist_cfg["amplitude_weight"]),
                                shape_weight=float(hist_dist_cfg["shape_weight"]),
                                slope_weight=float(hist_dist_cfg["slope_weight"]),
                                cdf_weight=float(hist_dist_cfg["cdf_weight"]),
                                amplitude_stat=str(hist_dist_cfg["amplitude_stat"]),
                            ),
                            float(group_weight),
                            blend_mode,
                        )
                    )
                hist_embed_meta = (
                    group_cfg.get("local_linear_embedding", {})
                    if isinstance(group_cfg, Mapping)
                    else {}
                )
                hist_embed, _ = build_rate_histogram_local_linear_embedding(
                    hist_matrix=group_matrix,
                    feature_names=group_cols,
                    hist_cfg=group_cfg if isinstance(group_cfg, Mapping) else {},
                    standardization=hist_embed_meta if isinstance(hist_embed_meta, Mapping) else None,
                )
                if hist_embed.ndim == 2 and hist_embed.shape[0] == len(z_tuned):
                    local_linear_parts.append(hist_embed)
                continue

            vector_dist_cfg = _resolve_ordered_vector_group_distance_cfg(group_cfg)
            try:
                min_valid_bins = max(int(float(group_cfg.get("min_valid_bins", 1))), 1)
            except (TypeError, ValueError):
                min_valid_bins = 1
            if not expand_as_scalar:
                aux_terms.append(
                    (
                        _pairwise_ordered_vector_distance_matrix(
                            group_matrix,
                            normalization=str(vector_dist_cfg["normalization"]),
                            p_norm=float(vector_dist_cfg["p_norm"]),
                            amplitude_weight=float(vector_dist_cfg["amplitude_weight"]),
                            shape_weight=float(vector_dist_cfg["shape_weight"]),
                            slope_weight=float(vector_dist_cfg["slope_weight"]),
                            cdf_weight=float(vector_dist_cfg["cdf_weight"]),
                            amplitude_stat=str(vector_dist_cfg["amplitude_stat"]),
                            min_valid_bins=int(min_valid_bins),
                        ),
                        float(group_weight),
                        blend_mode,
                    )
                )
            group_embed_meta = (
                group_cfg.get("local_linear_embedding", {})
                if isinstance(group_cfg, Mapping)
                else {}
            )
            group_embed, _ = build_ordered_vector_group_local_linear_embedding(
                values=group_matrix,
                feature_names=group_cols,
                group_cfg=group_cfg if isinstance(group_cfg, Mapping) else {},
                label_prefix=f"group::{group_name}",
                standardization=group_embed_meta if isinstance(group_embed_meta, Mapping) else None,
            )
            if group_embed.ndim == 2 and group_embed.shape[0] == len(z_tuned):
                local_linear_parts.append(group_embed)
    z_tuned_local = (
        np.concatenate(local_linear_parts, axis=1)
        if local_linear_parts
        else np.empty((len(z_tuned), 0), dtype=float)
    )
    base_dm_final = (
        _weighted_lp_pairwise(z_tuned_scalar, tune_result["p_norm"], scalar_weights)
        if scalar_idx.size > 0
        else np.zeros((len(z_tuned), len(z_tuned)), dtype=float)
    )
    dm_final = _combine_pairwise_distance_terms(
        base_distances=base_dm_final,
        aux_terms=aux_terms,
    )
    y_loo = _loo_knn_predictions(
        dm_final, y_param, tune_result["optimal_k"],
        z_feat=z_tuned_local,
        ridge_lambda=tune_result["optimal_lambda"],
        aggregation_mode=str(tune_result.get("optimal_aggregation", "weighted_mean")),
    )
    log.info("Generating STEP 1.5 validation plots...")
    _plot_loo_true_vs_estimated(y_param, y_loo, param_cols)
    _plot_loo_relative_error_histograms(y_param, y_loo, param_cols)
    log.info(
        "Result: %s (p=%.1f, norm=%s, agg=%s, k=%d, λ=%.0e, %d/%d active features, "
        "grid %.3f%% → tuned %.3f%%)",
        tune_result["selected_mode"],
        tune_result["p_norm"],
        tune_result["normalization"],
        tune_result.get("optimal_aggregation", "weighted_mean"),
        tune_result["optimal_k"],
        tune_result["optimal_lambda"],
        tune_result["n_active_features"],
        len(feature_cols),
        tune_result["grid_best_score"],
        tune_result["weight_tuned_score"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
