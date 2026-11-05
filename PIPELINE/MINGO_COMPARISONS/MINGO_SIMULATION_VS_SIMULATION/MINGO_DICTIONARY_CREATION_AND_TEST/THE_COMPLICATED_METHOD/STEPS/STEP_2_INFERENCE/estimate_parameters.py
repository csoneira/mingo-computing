#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_2_INFERENCE/estimate_parameters.py
Purpose: Self-contained dictionary-based parameter estimation module.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_2_INFERENCE/estimate_parameters.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

from itertools import combinations
import json
import logging
from pathlib import Path
import re
import sys
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from feature_columns_config import parse_explicit_feature_columns

log = logging.getLogger("estimate_parameters")

# Default location of the STEP 1.5 distance-definition artifact,
# relative to the STEP_2_INFERENCE directory (i.e. this file's parent).
_INFERENCE_DIR = Path(__file__).resolve().parent
_PIPELINE_DIR = _INFERENCE_DIR.parent
MODULES_DIR = _PIPELINE_DIR / "MODULES"
if MODULES_DIR.exists() and str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from feature_space_transform_engine import filter_rows_with_complete_numeric_columns

DEFAULT_DISTANCE_DEFINITION_PATH = (
    _PIPELINE_DIR / "STEP_1_SETUP" / "STEP_1_5_TUNE_DISTANCE_DEFINITION"
    / "OUTPUTS" / "FILES" / "distance_definition.json"
)


def load_distance_definition(
    feature_columns: list[str],
    *,
    path: Path | str | None = None,
) -> dict:
    """Load the STEP 1.5 distance-definition artifact and validate against *feature_columns*.

    Returns a dict with keys:
      available       – bool
      center          – np.ndarray (only when available)
      scale           – np.ndarray
      weights         – np.ndarray
      p_norm          – float
      optimal_k       – int
      optimal_lambda  – float
      selected_mode   – str
      reason          – str (only when *not* available)
    """
    dd_path = Path(path) if path is not None else DEFAULT_DISTANCE_DEFINITION_PATH
    if not dd_path.exists():
        return {"available": False, "reason": f"file_not_found ({dd_path})"}

    dist_def = json.loads(dd_path.read_text(encoding="utf-8"))
    dd_cols_raw = dist_def.get("feature_columns", [])
    if isinstance(dd_cols_raw, Sequence) and not isinstance(dd_cols_raw, (str, bytes)):
        dd_cols = [str(col) for col in dd_cols_raw]
    else:
        dd_cols = []
    if not dd_cols:
        return {"available": False, "reason": "missing_feature_columns"}

    dd_center = np.asarray(dist_def.get("center", []), dtype=float)
    dd_scale = np.asarray(dist_def.get("scale", []), dtype=float)
    dd_weights = np.asarray(
        dist_def.get("weights", [1.0] * len(dd_cols)), dtype=float
    )
    if dd_center.size != len(dd_cols) or dd_scale.size != len(dd_cols):
        return {
            "available": False,
            "reason": (
                f"vector_length_mismatch:center={dd_center.size},"
                f"scale={dd_scale.size},features={len(dd_cols)}"
            ),
        }
    if dd_weights.size != len(dd_cols):
        return {
            "available": False,
            "reason": (
                f"weight_length_mismatch:{dd_weights.size}!={len(dd_cols)}"
            ),
        }

    requested_cols = [str(col) for col in feature_columns]
    requested_index = {name: idx for idx, name in enumerate(requested_cols)}
    missing_in_requested = [name for name in dd_cols if name not in requested_index]
    if missing_in_requested:
        return {
            "available": False,
            "reason": (
                f"feature_mismatch: artifact columns missing from requested "
                f"({len(missing_in_requested)})"
            ),
        }

    dd_center_aligned = np.zeros(len(requested_cols), dtype=float)
    dd_scale_aligned = np.ones(len(requested_cols), dtype=float)
    dd_weights_aligned = np.zeros(len(requested_cols), dtype=float)
    for dd_idx, col in enumerate(dd_cols):
        req_idx = requested_index[col]
        dd_center_aligned[req_idx] = float(dd_center[dd_idx])
        dd_scale_aligned[req_idx] = float(dd_scale[dd_idx])
        dd_weights_aligned[req_idx] = float(dd_weights[dd_idx])

    dd_cols_set = set(dd_cols)
    alignment_mode = (
        "exact"
        if (list(dd_cols) == list(requested_cols) and len(dd_cols) == len(requested_cols))
        else "projected_subset"
    )
    dropped_requested_cols = [name for name in requested_cols if name not in dd_cols_set]
    group_weights_raw = dist_def.get("group_weights", {})
    if not isinstance(group_weights_raw, Mapping):
        group_weights_raw = {}
    group_weights = {
        str(name): float(value)
        for name, value in group_weights_raw.items()
        if str(name).strip()
    }
    feature_groups_raw = dist_def.get("feature_groups", {})
    if not isinstance(feature_groups_raw, Mapping):
        feature_groups_raw = {}
    feature_groups = {
        str(name): value
        for name, value in feature_groups_raw.items()
        if str(name).strip()
    }
    scalar_feature_cols_raw = dist_def.get(
        "one_feature_vector_columns",
        dist_def.get("scalar_feature_columns", []),
    )
    if isinstance(scalar_feature_cols_raw, Sequence) and not isinstance(scalar_feature_cols_raw, (str, bytes)):
        scalar_feature_cols = [str(col) for col in scalar_feature_cols_raw if str(col) in requested_index]
    else:
        scalar_feature_cols = [str(col) for col in dd_cols if str(col) in requested_index]

    return {
        "available": True,
        "center": dd_center_aligned,
        "scale": dd_scale_aligned,
        "weights": dd_weights_aligned,
        "scalar_feature_columns": scalar_feature_cols,
        "group_weights": group_weights,
        "feature_groups": feature_groups,
        "p_norm": float(dist_def.get("p_norm", 2.0)),
        "optimal_aggregation": str(dist_def.get("optimal_aggregation", "weighted_mean")),
        "optimal_k": int(dist_def.get("optimal_k", 5)),
        "optimal_lambda": float(dist_def.get("optimal_lambda", 1e6)),
        "selected_mode": dist_def.get("selected_mode", "unknown"),
        "alignment_mode": alignment_mode,
        "artifact_feature_columns_count": int(len(dd_cols)),
        "requested_feature_columns_count": int(len(requested_cols)),
        "projected_out_requested_feature_columns": dropped_requested_cols,
    }


def active_feature_columns_from_distance_definition(
    feature_columns: Sequence[str],
    *,
    distance_definition: Mapping[str, object] | None = None,
    path: Path | str | None = None,
    min_weight: float = 0.0,
) -> tuple[list[str], dict[str, object]]:
    """Resolve the STEP 1.5-active feature subset.

    Downstream diagnostics should reflect the columns that actively contribute
    to the tuned distance, not the broader pre-STEP-1.5 candidate list.
    """
    feature_cols = [str(c) for c in feature_columns]
    if isinstance(distance_definition, Mapping):
        dd = dict(distance_definition)
    else:
        dd = load_distance_definition(feature_cols, path=path)

    info: dict[str, object] = {
        "distance_definition_available": bool(dd.get("available")),
        "distance_definition_reason": dd.get("reason"),
        "n_requested_features": int(len(feature_cols)),
        "n_active_features": int(len(feature_cols)),
        "used_active_weights": False,
        "n_active_feature_groups": 0,
    }
    if not dd.get("available"):
        return feature_cols, info

    weights = np.asarray(dd.get("weights", []), dtype=float)
    if weights.size != len(feature_cols):
        info["distance_definition_reason"] = (
            f"weight_length_mismatch:{weights.size}!={len(feature_cols)}"
        )
        return feature_cols, info

    threshold = max(float(min_weight), 0.0)
    active = [
        col
        for col, weight in zip(feature_cols, weights)
        if np.isfinite(weight) and float(weight) > threshold
    ]
    group_weights = dd.get("group_weights", {})
    feature_groups = dd.get("feature_groups", {})
    if isinstance(group_weights, Mapping) and isinstance(feature_groups, Mapping):
        for group_name, weight in group_weights.items():
            try:
                numeric_weight = float(weight)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(numeric_weight) or numeric_weight <= threshold:
                continue
            group_info = feature_groups.get(str(group_name), {})
            if not isinstance(group_info, Mapping):
                continue
            group_cols = group_info.get("feature_columns", [])
            if not isinstance(group_cols, Sequence):
                continue
            for col in group_cols:
                name = str(col)
                if name in feature_cols and name not in active:
                    active.append(name)
            info["n_active_feature_groups"] = int(info.get("n_active_feature_groups", 0)) + 1
    if not active:
        info["distance_definition_reason"] = "no_positive_weights"
        return feature_cols, info

    info["n_active_features"] = int(len(active))
    info["used_active_weights"] = True
    return active, info


def require_runtime_distance_definition(
    distance_definition: Mapping[str, object] | None,
    *,
    context_label: str,
    require_exact_alignment: bool = True,
) -> dict[str, object]:
    """Require a usable STEP 1.5 artifact for runtime estimation.

    The pipeline should not silently swap to a different distance definition
    at inference time. Callers must fail if STEP 1.5 is missing or if the
    tuned feature space no longer matches the requested runtime feature space.
    """
    dd = dict(distance_definition or {})
    if not bool(dd.get("available")):
        reason = str(dd.get("reason", "unknown"))
        raise ValueError(
            f"{context_label} requires a valid STEP 1.5 distance definition, "
            f"but it is unavailable: {reason}"
        )
    alignment_mode = str(dd.get("alignment_mode", "exact")).strip().lower() or "exact"
    if require_exact_alignment and alignment_mode != "exact":
        artifact_count = int(dd.get("artifact_feature_columns_count", 0))
        requested_count = int(dd.get("requested_feature_columns_count", 0))
        raise ValueError(
            f"{context_label} requires an exact STEP 1.5 feature-space match, "
            f"but got alignment_mode={alignment_mode} "
            f"(artifact_features={artifact_count}, requested_features={requested_count})"
        )
    return dd


def require_explicit_columns_present_in_both_frames(
    requested_columns: Sequence[object],
    *,
    left_columns: Sequence[object],
    right_columns: Sequence[object],
    left_label: str,
    right_label: str,
    context_label: str,
) -> list[str]:
    """Require explicit configured columns to exist in both compared tables."""
    requested = [str(col).strip() for col in requested_columns if str(col).strip()]
    if not requested:
        raise ValueError(f"{context_label} explicit feature column list is empty.")
    left = {str(col).strip() for col in left_columns if str(col).strip()}
    right = {str(col).strip() for col in right_columns if str(col).strip()}
    missing_left = [col for col in requested if col not in left]
    missing_right = [col for col in requested if col not in right]
    if missing_left or missing_right:
        details: list[str] = []
        if missing_left:
            details.append(
                f"missing in {left_label}: "
                + ", ".join(missing_left[:50])
                + (" ..." if len(missing_left) > 50 else "")
            )
        if missing_right:
            details.append(
                f"missing in {right_label}: "
                + ", ".join(missing_right[:50])
                + (" ..." if len(missing_right) > 50 else "")
            )
        raise ValueError(
            f"{context_label} explicit feature space does not match the provided tables; "
            + "; ".join(details)
        )
    return requested


def _require_columns_present(
    available_columns: Sequence[object],
    required_columns: Sequence[object],
    *,
    frame_label: str,
) -> list[str]:
    resolved = [str(col).strip() for col in required_columns if str(col).strip()]
    available = {str(col).strip() for col in available_columns if str(col).strip()}
    missing = [col for col in resolved if col not in available]
    if missing:
        raise ValueError(
            f"{frame_label} is missing required column(s): {missing}"
        )
    return resolved


def _build_complete_numeric_row_mask(
    df: pd.DataFrame,
    *,
    required_columns: Sequence[object],
    label: str,
) -> tuple[pd.DataFrame, np.ndarray, dict[str, object]]:
    resolved_required = _require_columns_present(
        df.columns,
        required_columns,
        frame_label=label,
    )
    if not resolved_required:
        return pd.DataFrame(index=df.index), np.ones(len(df), dtype=bool), {
            "enabled": False,
            "label": str(label),
            "input_rows": int(len(df)),
            "rows_kept": int(len(df)),
            "rows_removed": 0,
            "rows_removed_fraction": 0.0,
            "required_columns_checked": [],
            "required_columns_checked_count": 0,
            "row_missing_required_column_count_distribution": {"0": int(len(df))},
            "top_missing_required_columns": [],
        }

    numeric = (
        df[resolved_required]
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
    )
    _, completeness = filter_rows_with_complete_numeric_columns(
        numeric,
        required_columns=resolved_required,
    )
    valid_mask = numeric.notna().all(axis=1).to_numpy(dtype=bool)
    completeness = dict(completeness)
    completeness["label"] = str(label)
    return numeric, valid_mask, completeness


def _filter_dataframe_by_mask(
    df: pd.DataFrame,
    *,
    row_mask: np.ndarray,
) -> pd.DataFrame:
    mask = np.asarray(row_mask, dtype=bool)
    return df.loc[mask].copy().reset_index(drop=True)


def _log_unified_distance_term_list(
    *,
    feature_columns: Sequence[str],
    one_feature_vector_columns: Sequence[str],
    one_feature_weights: np.ndarray | None,
    feature_groups: Mapping[str, object] | None,
    group_weights: Mapping[str, float] | None,
    header: str,
) -> None:
    log.info("%s", header)
    feature_cols = [str(col) for col in feature_columns]
    one_feature_set = {str(col) for col in one_feature_vector_columns}
    weights = (
        np.asarray(one_feature_weights, dtype=float)
        if one_feature_weights is not None
        else np.asarray([], dtype=float)
    )
    for idx, name in enumerate(feature_cols):
        if name not in one_feature_set:
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


# =====================================================================
# Distance functions
# =====================================================================

def _l2(a: np.ndarray, b: np.ndarray) -> float:
    mask = np.isfinite(a) & np.isfinite(b)
    if mask.sum() < 2:
        return np.nan
    diff = a[mask] - b[mask]
    return float(np.sqrt(np.sum(diff ** 2)))


def _chi2(a: np.ndarray, b: np.ndarray) -> float:
    mask = np.isfinite(a) & np.isfinite(b)
    if mask.sum() < 2:
        return np.nan
    y_t, y_p = a[mask], b[mask]
    # Poisson variance estimate: max(|observed|, 1) prevents division by zero
    variance_floor = np.maximum(np.abs(y_t), 1.0)
    return float(np.sum((y_t - y_p) ** 2 / variance_floor))


def _poisson(a: np.ndarray, b: np.ndarray) -> float:
    mask = np.isfinite(a) & np.isfinite(b)
    if mask.sum() < 2:
        return np.nan
    y_t = np.maximum(a[mask], 0.0)
    y_p = np.maximum(b[mask], 1e-12)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(y_t > 0, y_t / y_p, 1.0)
        term = np.where(y_t > 0, y_t * np.log(ratio) - (y_t - y_p), y_p)
    return float(2.0 * np.sum(term))


def _l2_many(
    a: np.ndarray,
    b: np.ndarray,
    *,
    min_valid_dims: int = 2,
) -> np.ndarray:
    """Vectorized L2 distance from one sample vector to many candidate vectors."""
    mask = np.isfinite(a)[None, :] & np.isfinite(b)
    valid_counts = np.sum(mask, axis=1)
    diff = np.where(mask, b - a[None, :], 0.0)
    out = np.sqrt(np.sum(diff * diff, axis=1))
    out = out.astype(float, copy=False)
    min_dims = max(int(min_valid_dims), 1)
    out[valid_counts < min_dims] = np.nan
    return out


def _chi2_many(
    a: np.ndarray,
    b: np.ndarray,
    *,
    min_valid_dims: int = 2,
) -> np.ndarray:
    """Vectorized chi2-like distance from one sample to many candidates."""
    mask = np.isfinite(a)[None, :] & np.isfinite(b)
    valid_counts = np.sum(mask, axis=1)
    y_t = np.where(mask, a[None, :], 0.0)
    y_p = np.where(mask, b, 0.0)
    # Poisson variance estimate: max(|observed|, 1) prevents division by zero
    variance_floor = np.maximum(np.abs(y_t), 1.0)
    out = np.sum((y_t - y_p) ** 2 / variance_floor, axis=1).astype(float, copy=False)
    min_dims = max(int(min_valid_dims), 1)
    out[valid_counts < min_dims] = np.nan
    return out


def _poisson_many(
    a: np.ndarray,
    b: np.ndarray,
    *,
    min_valid_dims: int = 2,
) -> np.ndarray:
    """Vectorized Poisson deviance-like distance from one sample to many candidates."""
    mask = np.isfinite(a)[None, :] & np.isfinite(b)
    valid_counts = np.sum(mask, axis=1)
    y_t = np.where(mask, np.maximum(a[None, :], 0.0), 0.0)
    y_p = np.where(mask, np.maximum(b, 1e-12), 1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(y_t > 0.0, y_t / y_p, 1.0)
        term = np.where(y_t > 0.0, y_t * np.log(ratio) - (y_t - y_p), y_p)
    out = 2.0 * np.sum(np.where(mask, term, 0.0), axis=1)
    out = out.astype(float, copy=False)
    min_dims = max(int(min_valid_dims), 1)
    out[valid_counts < min_dims] = np.nan
    return out


DISTANCE_FNS = {
    "l2": _l2,
    "l2_zscore": _l2,
    "l2_raw": _l2,
    "chi2": _chi2,
    "poisson": _poisson,
}

DISTANCE_FNS_MANY = {
    "l2": _l2_many,
    "l2_zscore": _l2_many,
    "l2_raw": _l2_many,
    "chi2": _chi2_many,
    "poisson": _poisson_many,
}


def _weighted_lp_many(
    sample: np.ndarray,
    candidates: np.ndarray,
    *,
    weights: np.ndarray,
    p_norm: float,
    min_valid_dims: int = 2,
) -> np.ndarray:
    """Weighted Lp distance from one sample to many candidates.

    ``weights`` and ``p_norm`` come from the STEP 1.5 distance-definition
    artifact.  The formula is:

        d = (Σ_i  w_i · |x_i − y_i|^p )^(1/p)

    Features with zero weight are excluded.
    """
    mask = np.isfinite(sample)[None, :] & np.isfinite(candidates)
    w = np.asarray(weights, dtype=float)
    # Ignore features with zero weight
    mask &= (w > 0.0)[None, :]
    valid_counts = np.sum(mask, axis=1)
    diff_abs = np.where(mask, np.abs(candidates - sample[None, :]), 0.0)
    if p_norm == 1.0:
        out = np.sum(w[None, :] * diff_abs, axis=1)
    elif p_norm == 2.0:
        out = np.sqrt(np.sum(w[None, :] * diff_abs * diff_abs, axis=1))
    else:
        out = np.power(
            np.sum(w[None, :] * np.power(diff_abs, p_norm), axis=1),
            1.0 / p_norm,
        )
    out = out.astype(float, copy=False)
    min_dims = max(int(min_valid_dims), 1)
    out[valid_counts < min_dims] = np.nan
    return out


RATE_HISTOGRAM_BIN_RE = re.compile(r"^events_per_second_(?P<bin>\d+)_rate_hz")
EFFICIENCY_VECTOR_COL_RE = re.compile(
    r"^efficiency_vector_p(?P<plane>[1-4])_(?P<axis>x|y|theta)_bin_(?P<bin>\d+)_(?P<field>center_mm|center_deg|eff|unc)$"
)
_EFFICIENCY_VECTOR_AXIS_ORDER = ("x", "y", "theta")
_EFFICIENCY_VECTOR_CENTER_FIELD_BY_AXIS = {
    "x": "center_mm",
    "y": "center_mm",
    "theta": "center_deg",
}


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


def _resolve_feature_group_kind(
    group_name: str,
    group_cfg: Mapping[str, object] | None,
) -> str:
    cfg = group_cfg if isinstance(group_cfg, Mapping) else {}
    raw = cfg.get("group_type", cfg.get("kind", cfg.get("type", None)))
    if raw is not None:
        text = str(raw).strip().lower()
    else:
        text = ""
    aliases = {
        "hist": "rate_histogram",
        "histogram": "rate_histogram",
        "rate_hist": "rate_histogram",
        "rate_histogram": "rate_histogram",
        "efficiency_vector": "efficiency_vectors",
        "efficiency_vectors": "efficiency_vectors",
        "effvec": "efficiency_vectors",
        "ordered_vector": "ordered_vector",
        "ordered_vector_lp": "ordered_vector",
        "vector": "ordered_vector",
        "vector_lp": "ordered_vector",
        "grouped_vector": "ordered_vector",
    }
    if text in aliases:
        return aliases[text]
    name = str(group_name).strip()
    if name == "rate_histogram":
        return "rate_histogram"
    if name == "efficiency_vectors":
        return "efficiency_vectors"
    return "ordered_vector"


def _histogram_feature_indices(feature_cols: Sequence[str]) -> list[int]:
    indexed: list[tuple[int, int]] = []
    for idx, col in enumerate(feature_cols):
        match = RATE_HISTOGRAM_BIN_RE.match(str(col))
        if match is None:
            continue
        indexed.append((int(match.group("bin")), idx))
    indexed.sort(key=lambda x: x[0])
    return [idx for _, idx in indexed]


def _efficiency_vector_feature_indices(feature_cols: Sequence[str]) -> list[int]:
    indexed: list[tuple[int, int, int, str]] = []
    for idx, col in enumerate(feature_cols):
        match = EFFICIENCY_VECTOR_COL_RE.match(str(col))
        if match is None:
            continue
        indexed.append(
            (
                int(match.group("plane")),
                int(match.group("bin")),
                {"x": 0, "y": 1, "theta": 2}.get(str(match.group("axis")), 99),
                str(match.group("field")),
            )
        )
    indexed.sort()
    return [idx for _, _, _, _ in indexed]


def _normalize_efficiency_vector_fiducial(raw: object) -> dict[str, float | None]:
    if not isinstance(raw, Mapping):
        raw = {}
    return {
        "x_abs_max_mm": _safe_optional_float(raw.get("x_abs_max_mm")),
        "y_abs_max_mm": _safe_optional_float(raw.get("y_abs_max_mm")),
        "theta_max_deg": _safe_optional_float(raw.get("theta_max_deg")),
    }


def _efficiency_vector_bin_mask(
    *,
    centers: np.ndarray,
    axis_name: str,
    fiducial: Mapping[str, float | None],
) -> np.ndarray:
    center_vals = np.asarray(centers, dtype=float)
    mask = np.isfinite(center_vals)
    if axis_name == "x":
        limit = fiducial.get("x_abs_max_mm")
        if limit is not None and np.isfinite(float(limit)):
            mask &= np.abs(center_vals) <= float(limit)
    elif axis_name == "y":
        limit = fiducial.get("y_abs_max_mm")
        if limit is not None and np.isfinite(float(limit)):
            mask &= np.abs(center_vals) <= float(limit)
    elif axis_name == "theta":
        limit = fiducial.get("theta_max_deg")
        if limit is not None and np.isfinite(float(limit)):
            mask &= center_vals <= float(limit)
    return mask


def _shared_efficiency_vector_groups(
    dict_df: pd.DataFrame,
    data_df: pd.DataFrame,
) -> list[dict[str, object]]:
    dict_cols = {str(c) for c in dict_df.columns}
    data_cols = {str(c) for c in data_df.columns}
    groups: dict[tuple[int, str], dict[int, dict[str, object]]] = {}

    for name in sorted(dict_cols | data_cols):
        match = EFFICIENCY_VECTOR_COL_RE.match(name)
        if match is None:
            continue
        plane = int(match.group("plane"))
        axis_name = str(match.group("axis"))
        bin_idx = int(match.group("bin"))
        field = str(match.group("field"))
        info = groups.setdefault((plane, axis_name), {}).setdefault(bin_idx, {})
        info[f"{field}_dict"] = name if name in dict_cols else None
        info[f"{field}_data"] = name if name in data_cols else None

    resolved: list[dict[str, object]] = []
    for plane in range(1, 5):
        for axis_name in _EFFICIENCY_VECTOR_AXIS_ORDER:
            group_bins = groups.get((plane, axis_name), {})
            if not group_bins:
                continue
            center_field = _EFFICIENCY_VECTOR_CENTER_FIELD_BY_AXIS[axis_name]
            bin_specs: list[dict[str, object]] = []
            for bin_idx in sorted(group_bins):
                spec = group_bins[bin_idx]
                eff_dict = spec.get("eff_dict")
                eff_data = spec.get("eff_data")
                if not eff_dict or not eff_data:
                    continue
                bin_specs.append(
                    {
                        "bin_idx": int(bin_idx),
                        "eff_col": str(eff_dict),
                        "unc_col": (
                            str(spec[f"unc_dict"])
                            if spec.get("unc_dict") and spec.get("unc_data")
                            else None
                        ),
                        "center_col_dict": (
                            str(spec[f"{center_field}_dict"])
                            if spec.get(f"{center_field}_dict")
                            else None
                        ),
                        "center_col_data": (
                            str(spec[f"{center_field}_data"])
                            if spec.get(f"{center_field}_data")
                            else None
                        ),
                    }
                )
            if not bin_specs:
                continue
            resolved.append(
                {
                    "plane": int(plane),
                    "axis": axis_name,
                    "bin_specs": bin_specs,
                }
            )
    return resolved


def _prepare_efficiency_vector_group_payloads(
    *,
    dict_df: pd.DataFrame,
    data_df: pd.DataFrame,
) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for spec in _shared_efficiency_vector_groups(dict_df, data_df):
        axis_name = str(spec["axis"])
        bin_specs = list(spec["bin_specs"])
        eff_cols = [str(item["eff_col"]) for item in bin_specs]
        unc_cols = [item.get("unc_col") for item in bin_specs]
        dict_eff = (
            dict_df[eff_cols]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(dtype=float)
        )
        data_eff = (
            data_df[eff_cols]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(dtype=float)
        )
        dict_unc = np.full(dict_eff.shape, np.nan, dtype=float)
        data_unc = np.full(data_eff.shape, np.nan, dtype=float)
        for col_idx, unc_col in enumerate(unc_cols):
            if not unc_col:
                continue
            dict_unc[:, col_idx] = pd.to_numeric(
                dict_df[str(unc_col)], errors="coerce"
            ).to_numpy(dtype=float)
            data_unc[:, col_idx] = pd.to_numeric(
                data_df[str(unc_col)], errors="coerce"
            ).to_numpy(dtype=float)

        centers = np.full(len(bin_specs), np.nan, dtype=float)
        for col_idx, item in enumerate(bin_specs):
            center_series = None
            center_col_dict = item.get("center_col_dict")
            center_col_data = item.get("center_col_data")
            if center_col_dict:
                center_series = pd.to_numeric(
                    dict_df[str(center_col_dict)], errors="coerce"
                )
            if (center_series is None or not center_series.notna().any()) and center_col_data:
                center_series = pd.to_numeric(
                    data_df[str(center_col_data)], errors="coerce"
                )
            if center_series is not None:
                finite = center_series[np.isfinite(center_series.to_numpy(dtype=float))]
                if not finite.empty:
                    centers[col_idx] = float(finite.iloc[0])

        payloads.append(
            {
                "plane": int(spec["plane"]),
                "axis": axis_name,
                "label": f"p{int(spec['plane'])}_{axis_name}",
                "eff_cols": eff_cols,
                "centers": centers,
                "dict_eff": dict_eff,
                "data_eff": data_eff,
                "dict_unc": dict_unc,
                "data_unc": data_unc,
            }
        )
    return payloads


def _filter_efficiency_vector_payloads(
    payloads: Sequence[Mapping[str, object]],
    *,
    feature_groups_cfg: Mapping[str, object] | None = None,
    selected_feature_columns: Sequence[str] | None = None,
) -> list[dict[str, object]]:
    if not payloads:
        return []

    allowed_by_label: dict[str, set[str]] = {}
    if isinstance(feature_groups_cfg, Mapping):
        raw_groups = feature_groups_cfg.get("groups", [])
        if isinstance(raw_groups, Sequence):
            for item in raw_groups:
                if not isinstance(item, Mapping):
                    continue
                label = str(item.get("label", "")).strip()
                if not label:
                    continue
                cols = item.get("feature_columns", [])
                if isinstance(cols, Sequence):
                    allowed_by_label[label] = {
                        str(col).strip()
                        for col in cols
                        if str(col).strip()
                    }

    selected_eff_cols = {
        str(col).strip()
        for col in (selected_feature_columns or [])
        if EFFICIENCY_VECTOR_COL_RE.match(str(col))
        and str(col).endswith("_eff")
    }

    filtered: list[dict[str, object]] = []
    for payload_raw in payloads:
        payload = dict(payload_raw)
        eff_cols = [str(col) for col in payload.get("eff_cols", [])]
        label = str(payload.get("label", "")).strip()
        keep_mask = np.ones(len(eff_cols), dtype=bool)

        if selected_eff_cols:
            keep_mask &= np.asarray([col in selected_eff_cols for col in eff_cols], dtype=bool)
        if label and label in allowed_by_label and allowed_by_label[label]:
            keep_mask &= np.asarray([col in allowed_by_label[label] for col in eff_cols], dtype=bool)

        if keep_mask.size == 0 or not np.any(keep_mask):
            continue

        payload["eff_cols"] = [col for col, keep in zip(eff_cols, keep_mask) if keep]
        payload["centers"] = np.asarray(payload.get("centers", []), dtype=float)[keep_mask]
        payload["dict_eff"] = np.asarray(payload.get("dict_eff", []), dtype=float)[:, keep_mask]
        payload["data_eff"] = np.asarray(payload.get("data_eff", []), dtype=float)[:, keep_mask]
        payload["dict_unc"] = np.asarray(payload.get("dict_unc", []), dtype=float)[:, keep_mask]
        payload["data_unc"] = np.asarray(payload.get("data_unc", []), dtype=float)[:, keep_mask]
        filtered.append(payload)
    return filtered


def _shared_histogram_feature_columns(
    dict_cols: Sequence[object],
    data_cols: Sequence[object],
) -> list[str]:
    """Resolve shared histogram-bin rate columns ordered by bin index."""
    data_col_set = {str(c) for c in data_cols}
    by_bin: dict[int, str] = {}
    for col in dict_cols:
        name = str(col)
        match = RATE_HISTOGRAM_BIN_RE.match(name)
        if match is None or name not in data_col_set:
            continue
        by_bin.setdefault(int(match.group("bin")), name)
    return [by_bin[k] for k in sorted(by_bin)]


def _histogram_emd_many(sample_hist: np.ndarray, candidates_hist: np.ndarray) -> np.ndarray:
    return _histogram_distance_many(
        sample_hist,
        candidates_hist,
        distance="ordered_vector_lp",
        normalization="unit_sum",
        p_norm=1.0,
        amplitude_weight=0.0,
        shape_weight=0.0,
        slope_weight=0.0,
        cdf_weight=1.0,
        amplitude_stat="sum",
    )


def _coerce_nonnegative_float(value: object, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        out = float(default)
    if not np.isfinite(out):
        out = float(default)
    return max(out, 0.0)


def _resolve_vector_distance_common_cfg(
    raw_cfg: Mapping[str, object] | None,
    *,
    defaults: Mapping[str, object],
) -> dict[str, object]:
    cfg = raw_cfg if isinstance(raw_cfg, Mapping) else {}
    normalization = str(cfg.get("normalization", defaults.get("normalization", "none"))).strip().lower()
    if normalization not in {"none", "center", "zscore", "minmax", "unit_sum", "l2norm"}:
        normalization = str(defaults.get("normalization", "none"))

    amplitude_stat = str(cfg.get("amplitude_stat", defaults.get("amplitude_stat", "mean"))).strip().lower()
    if amplitude_stat not in {"mean", "sum"}:
        amplitude_stat = str(defaults.get("amplitude_stat", "mean"))

    p_norm = _coerce_nonnegative_float(cfg.get("p_norm", defaults.get("p_norm", 2.0)), float(defaults.get("p_norm", 2.0)))
    if p_norm <= 0.0:
        p_norm = float(defaults.get("p_norm", 2.0))

    out = {
        "distance": "ordered_vector_lp",
        "normalization": normalization,
        "p_norm": float(p_norm),
        "amplitude_weight": float(_coerce_nonnegative_float(cfg.get("amplitude_weight", defaults.get("amplitude_weight", 0.0)), float(defaults.get("amplitude_weight", 0.0)))),
        "shape_weight": float(_coerce_nonnegative_float(cfg.get("shape_weight", defaults.get("shape_weight", 1.0)), float(defaults.get("shape_weight", 1.0)))),
        "slope_weight": float(_coerce_nonnegative_float(cfg.get("slope_weight", defaults.get("slope_weight", 0.0)), float(defaults.get("slope_weight", 0.0)))),
        "cdf_weight": float(_coerce_nonnegative_float(cfg.get("cdf_weight", defaults.get("cdf_weight", 0.0)), float(defaults.get("cdf_weight", 0.0)))),
        "amplitude_stat": amplitude_stat,
    }
    out["mass_weight"] = float(out["amplitude_weight"])
    return out


def _resolve_ordered_vector_group_distance_cfg(
    raw_cfg: Mapping[str, object] | None,
) -> dict[str, object]:
    cfg = raw_cfg if isinstance(raw_cfg, Mapping) else {}
    defaults = {
        "normalization": "none",
        "p_norm": 2.0,
        "amplitude_weight": 0.0,
        "shape_weight": 1.0,
        "slope_weight": 0.0,
        "cdf_weight": 0.0,
        "amplitude_stat": "mean",
    }
    return _resolve_vector_distance_common_cfg(cfg, defaults=defaults)


def _relative_vector_amplitude_many(
    *,
    sample: np.ndarray,
    candidates: np.ndarray,
    valid: np.ndarray,
    weights: np.ndarray,
    stat: str,
) -> np.ndarray:
    sample_arr = np.asarray(sample, dtype=float)
    cand_arr = np.asarray(candidates, dtype=float)
    valid_mask = np.asarray(valid, dtype=bool)
    weight_arr = np.asarray(weights, dtype=float)
    out = np.full(cand_arr.shape[0], np.nan, dtype=float)
    if cand_arr.ndim != 2 or sample_arr.ndim != 1 or cand_arr.shape[1] != sample_arr.size:
        return out
    if stat == "sum":
        sample_stat = np.sum(np.where(valid_mask, sample_arr[None, :], 0.0), axis=1)
        cand_stat = np.sum(np.where(valid_mask, cand_arr, 0.0), axis=1)
    else:
        sum_w = np.sum(np.where(valid_mask, weight_arr, 0.0), axis=1)
        ok = sum_w > 0.0
        if not np.any(ok):
            return out
        sample_stat = np.full(cand_arr.shape[0], np.nan, dtype=float)
        cand_stat = np.full(cand_arr.shape[0], np.nan, dtype=float)
        sample_stat[ok] = np.sum(np.where(valid_mask[ok], weight_arr[ok] * sample_arr[None, :], 0.0), axis=1) / sum_w[ok]
        cand_stat[ok] = np.sum(np.where(valid_mask[ok], weight_arr[ok] * cand_arr[ok], 0.0), axis=1) / sum_w[ok]
    denom = np.maximum(np.maximum(np.abs(sample_stat), np.abs(cand_stat)), 1e-12)
    finite = np.isfinite(sample_stat) & np.isfinite(cand_stat) & np.isfinite(denom)
    out[finite] = np.abs(cand_stat[finite] - sample_stat[finite]) / denom[finite]
    return out


def _weighted_lp_from_arrays(
    *,
    sample: np.ndarray,
    candidates: np.ndarray,
    valid: np.ndarray,
    weights: np.ndarray,
    p_norm: float,
) -> np.ndarray:
    sample_arr = np.asarray(sample, dtype=float)
    cand_arr = np.asarray(candidates, dtype=float)
    valid_mask = np.asarray(valid, dtype=bool)
    weight_arr = np.asarray(weights, dtype=float)
    out = np.full(cand_arr.shape[0], np.nan, dtype=float)
    if cand_arr.ndim != 2 or sample_arr.ndim != 2 or cand_arr.shape != sample_arr.shape:
        return out
    sum_w = np.sum(np.where(valid_mask, weight_arr, 0.0), axis=1)
    ok = sum_w > 0.0
    if not np.any(ok):
        return out
    diff = np.where(valid_mask, np.abs(cand_arr - sample_arr), 0.0)
    power = max(float(p_norm), 1e-12)
    acc = np.full(cand_arr.shape[0], np.nan, dtype=float)
    acc_num = np.sum(np.where(valid_mask, weight_arr * np.power(diff, power), 0.0), axis=1)
    acc[ok] = acc_num[ok] / sum_w[ok]
    out[ok] = np.power(np.maximum(acc[ok], 0.0), 1.0 / power)
    return out


def _normalize_vectors_pairwise(
    *,
    sample: np.ndarray,
    candidates: np.ndarray,
    valid: np.ndarray,
    weights: np.ndarray,
    normalization: str,
) -> tuple[np.ndarray, np.ndarray]:
    sample_arr = np.asarray(sample, dtype=float)
    cand_arr = np.asarray(candidates, dtype=float)
    valid_mask = np.asarray(valid, dtype=bool)
    weight_arr = np.asarray(weights, dtype=float)
    sample_out = np.where(valid_mask, sample_arr, np.nan)
    cand_out = np.where(valid_mask, cand_arr, np.nan)
    mode = str(normalization).strip().lower()
    if mode == "none":
        return sample_out, cand_out

    if mode == "unit_sum":
        sample_pos = np.where(valid_mask, np.clip(sample_arr, 0.0, None), 0.0)
        cand_pos = np.where(valid_mask, np.clip(cand_arr, 0.0, None), 0.0)
        sample_scale = np.sum(sample_pos, axis=1)
        cand_scale = np.sum(cand_pos, axis=1)
        sample_scale = np.where(sample_scale > 1e-12, sample_scale, 1.0)
        cand_scale = np.where(cand_scale > 1e-12, cand_scale, 1.0)
        return sample_pos / sample_scale[:, None], cand_pos / cand_scale[:, None]

    sum_w = np.sum(np.where(valid_mask, weight_arr, 0.0), axis=1)
    ok = sum_w > 0.0
    if not np.any(ok):
        return sample_out, cand_out

    sample_mu = np.full(sample_arr.shape[0], 0.0, dtype=float)
    cand_mu = np.full(cand_arr.shape[0], 0.0, dtype=float)
    sample_mu[ok] = np.sum(np.where(valid_mask[ok], weight_arr[ok] * sample_arr[ok], 0.0), axis=1) / sum_w[ok]
    cand_mu[ok] = np.sum(np.where(valid_mask[ok], weight_arr[ok] * cand_arr[ok], 0.0), axis=1) / sum_w[ok]

    if mode == "center":
        return sample_arr - sample_mu[:, None], cand_arr - cand_mu[:, None]

    if mode == "zscore":
        sample_centered = sample_arr - sample_mu[:, None]
        cand_centered = cand_arr - cand_mu[:, None]
        sample_var = np.full(sample_arr.shape[0], 1.0, dtype=float)
        cand_var = np.full(cand_arr.shape[0], 1.0, dtype=float)
        sample_var[ok] = np.sum(np.where(valid_mask[ok], weight_arr[ok] * sample_centered[ok] * sample_centered[ok], 0.0), axis=1) / sum_w[ok]
        cand_var[ok] = np.sum(np.where(valid_mask[ok], weight_arr[ok] * cand_centered[ok] * cand_centered[ok], 0.0), axis=1) / sum_w[ok]
        sample_scale = np.where(sample_var > 1e-12, np.sqrt(sample_var), 1.0)
        cand_scale = np.where(cand_var > 1e-12, np.sqrt(cand_var), 1.0)
        return sample_centered / sample_scale[:, None], cand_centered / cand_scale[:, None]

    if mode == "minmax":
        sample_masked = np.where(valid_mask, sample_arr, np.nan)
        cand_masked = np.where(valid_mask, cand_arr, np.nan)
        sample_min = np.nanmin(sample_masked, axis=1)
        sample_max = np.nanmax(sample_masked, axis=1)
        cand_min = np.nanmin(cand_masked, axis=1)
        cand_max = np.nanmax(cand_masked, axis=1)
        sample_scale = np.where((sample_max - sample_min) > 1e-12, sample_max - sample_min, 1.0)
        cand_scale = np.where((cand_max - cand_min) > 1e-12, cand_max - cand_min, 1.0)
        return (sample_arr - sample_min[:, None]) / sample_scale[:, None], (cand_arr - cand_min[:, None]) / cand_scale[:, None]

    if mode == "l2norm":
        sample_scale = np.sqrt(np.sum(np.where(valid_mask, weight_arr * sample_arr * sample_arr, 0.0), axis=1) / np.maximum(sum_w, 1e-12))
        cand_scale = np.sqrt(np.sum(np.where(valid_mask, weight_arr * cand_arr * cand_arr, 0.0), axis=1) / np.maximum(sum_w, 1e-12))
        sample_scale = np.where(sample_scale > 1e-12, sample_scale, 1.0)
        cand_scale = np.where(cand_scale > 1e-12, cand_scale, 1.0)
        return sample_arr / sample_scale[:, None], cand_arr / cand_scale[:, None]

    return sample_out, cand_out


def _normalize_vector_rows(
    *,
    values: np.ndarray,
    valid: np.ndarray,
    weights: np.ndarray,
    normalization: str,
) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    valid_mask = np.asarray(valid, dtype=bool)
    weight_arr = np.asarray(weights, dtype=float)
    out = np.where(valid_mask, arr, np.nan)
    mode = str(normalization).strip().lower()
    if mode == "none":
        return out

    if mode == "unit_sum":
        arr_pos = np.where(valid_mask, np.clip(arr, 0.0, None), 0.0)
        scale = np.sum(arr_pos, axis=1)
        scale = np.where(scale > 1e-12, scale, 1.0)
        return arr_pos / scale[:, None]

    sum_w = np.sum(np.where(valid_mask, weight_arr, 0.0), axis=1)
    ok = sum_w > 0.0
    if not np.any(ok):
        return out

    mu = np.full(arr.shape[0], 0.0, dtype=float)
    mu[ok] = np.sum(np.where(valid_mask[ok], weight_arr[ok] * arr[ok], 0.0), axis=1) / sum_w[ok]

    if mode == "center":
        return np.where(valid_mask, arr - mu[:, None], np.nan)

    if mode == "zscore":
        centered = arr - mu[:, None]
        var = np.full(arr.shape[0], 1.0, dtype=float)
        var[ok] = np.sum(
            np.where(valid_mask[ok], weight_arr[ok] * centered[ok] * centered[ok], 0.0),
            axis=1,
        ) / sum_w[ok]
        scale = np.where(var > 1e-12, np.sqrt(var), 1.0)
        return np.where(valid_mask, centered / scale[:, None], np.nan)

    if mode == "minmax":
        masked = np.where(valid_mask, arr, np.nan)
        min_v = np.nanmin(masked, axis=1)
        max_v = np.nanmax(masked, axis=1)
        scale = np.where((max_v - min_v) > 1e-12, max_v - min_v, 1.0)
        return np.where(valid_mask, (arr - min_v[:, None]) / scale[:, None], np.nan)

    if mode == "l2norm":
        scale = np.sqrt(
            np.sum(np.where(valid_mask, weight_arr * arr * arr, 0.0), axis=1) / np.maximum(sum_w, 1e-12)
        )
        scale = np.where(scale > 1e-12, scale, 1.0)
        return np.where(valid_mask, arr / scale[:, None], np.nan)

    return out


def _fit_local_linear_embedding_standardization(
    raw_matrix: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    arr = np.asarray(raw_matrix, dtype=float)
    if arr.ndim != 2 or arr.shape[1] == 0:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)
    center = np.nanmedian(arr, axis=0)
    mad = np.nanmedian(np.abs(arr - center[None, :]), axis=0)
    std = np.nanstd(arr, axis=0)
    scale = np.where(np.isfinite(mad) & (mad > 1e-12), 1.4826 * mad, std)
    scale = np.where(np.isfinite(scale) & (scale > 1e-12), scale, 1.0)
    center = np.where(np.isfinite(center), center, 0.0)
    return center.astype(float), scale.astype(float)


def _apply_local_linear_embedding_standardization(
    raw_matrix: np.ndarray,
    *,
    center: np.ndarray,
    scale: np.ndarray,
) -> np.ndarray:
    arr = np.asarray(raw_matrix, dtype=float)
    if arr.ndim != 2 or arr.shape[1] == 0:
        return np.empty((arr.shape[0] if arr.ndim == 2 else 0, 0), dtype=float)
    center_arr = np.asarray(center, dtype=float)
    scale_arr = np.asarray(scale, dtype=float)
    if center_arr.shape[0] != arr.shape[1] or scale_arr.shape[0] != arr.shape[1]:
        return np.empty((arr.shape[0], 0), dtype=float)
    out = (arr - center_arr[None, :]) / scale_arr[None, :]
    return np.where(np.isfinite(out), out, 0.0)


def _ordered_vector_local_linear_embedding_raw(
    *,
    values: np.ndarray,
    feature_names: Sequence[str],
    centers: np.ndarray | None = None,
    axis_name: str | None = None,
    fiducial: Mapping[str, float | None] | None = None,
    uncertainties: np.ndarray | None = None,
    uncertainty_floor: float = 0.0,
    normalization: str = "none",
    amplitude_weight: float = 0.0,
    shape_weight: float = 1.0,
    slope_weight: float = 0.0,
    cdf_weight: float = 0.0,
    amplitude_stat: str = "mean",
    label_prefix: str = "",
) -> tuple[np.ndarray, list[str]]:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 2 or arr.shape[1] == 0:
        return np.empty((arr.shape[0] if arr.ndim == 2 else 0, 0), dtype=float), []
    if centers is None:
        center_vals = np.arange(arr.shape[1], dtype=float)
        center_mask = np.ones(arr.shape[1], dtype=bool)
    else:
        center_vals = np.asarray(centers, dtype=float)
        if center_vals.shape[0] != arr.shape[1]:
            return np.empty((arr.shape[0], 0), dtype=float), []
        center_mask = _efficiency_vector_bin_mask(
            centers=center_vals,
            axis_name=str(axis_name or ""),
            fiducial=fiducial or {},
        ) if fiducial is not None else np.isfinite(center_vals)
    if not np.any(center_mask):
        return np.empty((arr.shape[0], 0), dtype=float), []

    valid = center_mask[None, :] & np.isfinite(arr)
    if uncertainties is not None:
        unc_arr = np.asarray(uncertainties, dtype=float)
        if unc_arr.shape != arr.shape:
            unc_arr = None
    else:
        unc_arr = None
    floor_sq = max(float(uncertainty_floor), 0.0) ** 2
    if unc_arr is not None:
        var = np.where(np.isfinite(unc_arr), unc_arr * unc_arr, 0.0)
        denom = np.maximum(var + floor_sq, floor_sq if floor_sq > 0.0 else 1e-12)
        weights = np.where(valid, 1.0 / denom, 0.0)
    else:
        weights = np.where(valid, 1.0, 0.0)

    arr_norm = _normalize_vector_rows(
        values=arr,
        valid=valid,
        weights=weights,
        normalization=normalization,
    )

    parts: list[np.ndarray] = []
    labels: list[str] = []
    names = [str(name) for name in feature_names]
    prefix = f"{label_prefix}::" if label_prefix else ""

    if float(amplitude_weight) > 0.0:
        if str(amplitude_stat).strip().lower() == "sum":
            amp_vals = np.sum(np.where(valid, arr, 0.0), axis=1)
        else:
            sum_w = np.sum(np.where(valid, weights, 0.0), axis=1)
            amp_vals = np.zeros(arr.shape[0], dtype=float)
            ok = sum_w > 0.0
            amp_vals[ok] = np.sum(np.where(valid[ok], weights[ok] * arr[ok], 0.0), axis=1) / sum_w[ok]
        parts.append((float(amplitude_weight) * amp_vals)[:, None])
        labels.append(f"{prefix}amplitude")

    if float(shape_weight) > 0.0:
        shape_cols = np.where(valid, float(shape_weight) * arr_norm, np.nan)
        parts.append(shape_cols)
        labels.extend(f"{prefix}shape::{name}" for name in names)

    if float(slope_weight) > 0.0 and arr.shape[1] >= 2:
        delta = np.diff(center_vals)
        delta = np.where(np.isfinite(delta) & (np.abs(delta) > 1e-12), delta, 1.0)
        slope_valid = valid[:, 1:] & valid[:, :-1]
        slopes = np.where(
            slope_valid,
            float(slope_weight) * (arr_norm[:, 1:] - arr_norm[:, :-1]) / delta[None, :],
            np.nan,
        )
        parts.append(slopes)
        labels.extend(f"{prefix}slope::{names[idx+1]}" for idx in range(arr.shape[1] - 1))

    if float(cdf_weight) > 0.0:
        pos = np.where(valid, np.clip(arr_norm, 0.0, None), 0.0)
        sums = np.sum(pos, axis=1)
        cdf = np.full(arr.shape, np.nan, dtype=float)
        ok = sums > 1e-12
        if np.any(ok):
            cdf[ok] = np.cumsum(pos[ok] / sums[ok, None], axis=1)
        parts.append(float(cdf_weight) * cdf)
        labels.extend(f"{prefix}cdf::{name}" for name in names)

    if not parts:
        return np.empty((arr.shape[0], 0), dtype=float), []
    raw = np.concatenate(parts, axis=1)
    return raw.astype(float), labels


def build_rate_histogram_local_linear_embedding(
    *,
    hist_matrix: np.ndarray,
    feature_names: Sequence[str],
    hist_cfg: Mapping[str, object] | None,
    standardization: Mapping[str, object] | None = None,
) -> tuple[np.ndarray, dict[str, object]]:
    cfg = _resolve_histogram_distance_cfg(hist_cfg if isinstance(hist_cfg, Mapping) else {})
    raw, labels = _ordered_vector_local_linear_embedding_raw(
        values=np.asarray(hist_matrix, dtype=float),
        feature_names=feature_names,
        centers=np.arange(len(feature_names), dtype=float),
        axis_name="rate_histogram",
        normalization=str(cfg["normalization"]),
        amplitude_weight=float(cfg["amplitude_weight"]),
        shape_weight=float(cfg["shape_weight"]),
        slope_weight=float(cfg["slope_weight"]),
        cdf_weight=float(cfg["cdf_weight"]),
        amplitude_stat=str(cfg["amplitude_stat"]),
        label_prefix="rate_histogram",
    )
    if raw.shape[1] == 0:
        return np.empty((raw.shape[0], 0), dtype=float), {"labels": [], "center": [], "scale": []}
    if isinstance(standardization, Mapping):
        center = np.asarray(standardization.get("center", []), dtype=float)
        scale = np.asarray(standardization.get("scale", []), dtype=float)
        meta_labels = [str(item) for item in standardization.get("labels", [])]
        if center.shape[0] != raw.shape[1] or scale.shape[0] != raw.shape[1] or len(meta_labels) != raw.shape[1]:
            center, scale = _fit_local_linear_embedding_standardization(raw)
            meta_labels = list(labels)
    else:
        center, scale = _fit_local_linear_embedding_standardization(raw)
        meta_labels = list(labels)
    embedding = _apply_local_linear_embedding_standardization(raw, center=center, scale=scale)
    meta = {
        "labels": list(meta_labels),
        "center": center.astype(float).tolist(),
        "scale": scale.astype(float).tolist(),
    }
    return embedding, meta


def build_ordered_vector_group_local_linear_embedding(
    *,
    values: np.ndarray,
    feature_names: Sequence[str],
    group_cfg: Mapping[str, object] | None,
    label_prefix: str,
    standardization: Mapping[str, object] | None = None,
) -> tuple[np.ndarray, dict[str, object]]:
    cfg = _resolve_ordered_vector_group_distance_cfg(group_cfg if isinstance(group_cfg, Mapping) else {})
    raw, labels = _ordered_vector_local_linear_embedding_raw(
        values=np.asarray(values, dtype=float),
        feature_names=feature_names,
        centers=np.arange(len(feature_names), dtype=float),
        axis_name=str(label_prefix),
        normalization=str(cfg["normalization"]),
        amplitude_weight=float(cfg["amplitude_weight"]),
        shape_weight=float(cfg["shape_weight"]),
        slope_weight=float(cfg["slope_weight"]),
        cdf_weight=float(cfg["cdf_weight"]),
        amplitude_stat=str(cfg["amplitude_stat"]),
        label_prefix=str(label_prefix),
    )
    if raw.shape[1] == 0:
        return np.empty((raw.shape[0], 0), dtype=float), {"labels": [], "center": [], "scale": []}
    if isinstance(standardization, Mapping):
        center = np.asarray(standardization.get("center", []), dtype=float)
        scale = np.asarray(standardization.get("scale", []), dtype=float)
        meta_labels = [str(item) for item in standardization.get("labels", [])]
        if center.shape[0] != raw.shape[1] or scale.shape[0] != raw.shape[1] or len(meta_labels) != raw.shape[1]:
            center, scale = _fit_local_linear_embedding_standardization(raw)
            meta_labels = list(labels)
    else:
        center, scale = _fit_local_linear_embedding_standardization(raw)
        meta_labels = list(labels)
    embedding = _apply_local_linear_embedding_standardization(raw, center=center, scale=scale)
    meta = {
        "labels": list(meta_labels),
        "center": center.astype(float).tolist(),
        "scale": scale.astype(float).tolist(),
    }
    return embedding, meta


def build_efficiency_vector_local_linear_embedding(
    *,
    payloads: Sequence[Mapping[str, object]],
    eff_cfg: Mapping[str, object] | None,
    source: str,
    standardization: Mapping[str, object] | None = None,
) -> tuple[np.ndarray, dict[str, object]]:
    cfg = _resolve_efficiency_vector_distance_cfg(eff_cfg if isinstance(eff_cfg, Mapping) else {})
    raw_parts: list[np.ndarray] = []
    labels: list[str] = []
    for payload in payloads:
        label = str(payload.get("label", "")).strip()
        feature_names = [str(col) for col in payload.get("eff_cols", [])]
        if not feature_names:
            continue
        values = np.asarray(payload.get(f"{source}_eff", []), dtype=float)
        unc = np.asarray(payload.get(f"{source}_unc", []), dtype=float)
        if values.ndim != 2 or values.shape[1] != len(feature_names):
            continue
        raw, raw_labels = _ordered_vector_local_linear_embedding_raw(
            values=values,
            feature_names=feature_names,
            centers=np.asarray(payload.get("centers", []), dtype=float),
            axis_name=str(payload.get("axis", "")),
            fiducial=dict(cfg["fiducial"]),
            uncertainties=unc if unc.ndim == 2 and unc.shape == values.shape else None,
            uncertainty_floor=float(cfg["uncertainty_floor"]),
            normalization=str(cfg["normalization"]),
            amplitude_weight=float(cfg["amplitude_weight"]),
            shape_weight=float(cfg["shape_weight"]),
            slope_weight=float(cfg["slope_weight"]),
            cdf_weight=float(cfg["cdf_weight"]),
            amplitude_stat=str(cfg["amplitude_stat"]),
            label_prefix=f"efficiency_vectors::{label}" if label else "efficiency_vectors",
        )
        if raw.shape[1] == 0:
            continue
        raw_parts.append(raw)
        labels.extend(raw_labels)
    if not raw_parts:
        return np.empty((0, 0), dtype=float), {"labels": [], "center": [], "scale": []}
    raw_matrix = np.concatenate(raw_parts, axis=1)
    if isinstance(standardization, Mapping):
        center = np.asarray(standardization.get("center", []), dtype=float)
        scale = np.asarray(standardization.get("scale", []), dtype=float)
        meta_labels = [str(item) for item in standardization.get("labels", [])]
        if center.shape[0] != raw_matrix.shape[1] or scale.shape[0] != raw_matrix.shape[1] or len(meta_labels) != raw_matrix.shape[1]:
            center, scale = _fit_local_linear_embedding_standardization(raw_matrix)
            meta_labels = list(labels)
    else:
        center, scale = _fit_local_linear_embedding_standardization(raw_matrix)
        meta_labels = list(labels)
    embedding = _apply_local_linear_embedding_standardization(raw_matrix, center=center, scale=scale)
    meta = {
        "labels": list(meta_labels),
        "center": center.astype(float).tolist(),
        "scale": scale.astype(float).tolist(),
    }
    return embedding, meta


def _build_group_local_linear_feature_matrices(
    *,
    dict_feature_source: pd.DataFrame,
    data_feature_source: pd.DataFrame,
    feature_groups: Mapping[str, object] | None,
    selected_feature_columns: Sequence[str],
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    if not isinstance(feature_groups, Mapping):
        return {}, {}

    dict_group_features: dict[str, np.ndarray] = {}
    data_group_features: dict[str, np.ndarray] = {}

    for raw_group_name, raw_cfg in feature_groups.items():
        group_name = str(raw_group_name).strip()
        if not group_name or not isinstance(raw_cfg, Mapping):
            continue
        embed_meta = raw_cfg.get("local_linear_embedding", {})
        if not isinstance(embed_meta, Mapping):
            continue

        group_kind = _resolve_feature_group_kind(group_name, raw_cfg)
        if group_kind == "efficiency_vectors":
            payloads = _prepare_efficiency_vector_group_payloads(
                dict_df=dict_feature_source,
                data_df=data_feature_source,
            )
            payloads = _filter_efficiency_vector_payloads(
                payloads,
                feature_groups_cfg=raw_cfg,
                selected_feature_columns=selected_feature_columns,
            )
            if not payloads:
                continue
            dict_embed, _ = build_efficiency_vector_local_linear_embedding(
                payloads=payloads,
                eff_cfg=raw_cfg,
                source="dict",
                standardization=embed_meta,
            )
            data_embed, _ = build_efficiency_vector_local_linear_embedding(
                payloads=payloads,
                eff_cfg=raw_cfg,
                source="data",
                standardization=embed_meta,
            )
        else:
            group_cols = [
                str(col)
                for col in raw_cfg.get("feature_columns", [])
                if str(col) in dict_feature_source.columns and str(col) in data_feature_source.columns
            ]
            if not group_cols:
                continue
            dict_matrix = (
                dict_feature_source[group_cols]
                .apply(pd.to_numeric, errors="coerce")
                .to_numpy(dtype=float)
            )
            data_matrix = (
                data_feature_source[group_cols]
                .apply(pd.to_numeric, errors="coerce")
                .to_numpy(dtype=float)
            )
            if group_kind == "rate_histogram":
                dict_embed, _ = build_rate_histogram_local_linear_embedding(
                    hist_matrix=dict_matrix,
                    feature_names=group_cols,
                    hist_cfg=raw_cfg,
                    standardization=embed_meta,
                )
                data_embed, _ = build_rate_histogram_local_linear_embedding(
                    hist_matrix=data_matrix,
                    feature_names=group_cols,
                    hist_cfg=raw_cfg,
                    standardization=embed_meta,
                )
            else:
                dict_embed, _ = build_ordered_vector_group_local_linear_embedding(
                    values=dict_matrix,
                    feature_names=group_cols,
                    group_cfg=raw_cfg,
                    label_prefix=f"group::{group_name}",
                    standardization=embed_meta,
                )
                data_embed, _ = build_ordered_vector_group_local_linear_embedding(
                    values=data_matrix,
                    feature_names=group_cols,
                    group_cfg=raw_cfg,
                    label_prefix=f"group::{group_name}",
                    standardization=embed_meta,
                )
        if dict_embed.ndim == 2 and data_embed.ndim == 2 and dict_embed.shape[1] == data_embed.shape[1]:
            dict_group_features[group_name] = dict_embed
            data_group_features[group_name] = data_embed

    return dict_group_features, data_group_features


def _ordered_vector_distance_many(
    *,
    sample_vec: np.ndarray,
    candidates_vec: np.ndarray,
    sample_unc: np.ndarray | None = None,
    candidates_unc: np.ndarray | None = None,
    centers: np.ndarray | None = None,
    axis_name: str | None = None,
    fiducial: Mapping[str, float | None] | None = None,
    uncertainty_floor: float = 0.0,
    min_valid_bins: int = 1,
    normalization: str = "none",
    p_norm: float = 2.0,
    amplitude_weight: float = 0.0,
    shape_weight: float = 1.0,
    slope_weight: float = 0.0,
    cdf_weight: float = 0.0,
    amplitude_stat: str = "mean",
) -> np.ndarray:
    sample = np.asarray(sample_vec, dtype=float)
    candidates = np.asarray(candidates_vec, dtype=float)
    if sample.ndim != 1 or candidates.ndim != 2 or candidates.shape[1] != sample.size:
        return np.full(candidates.shape[0] if candidates.ndim == 2 else 0, np.nan, dtype=float)
    out = np.full(candidates.shape[0], np.nan, dtype=float)
    if candidates.shape[0] == 0:
        return out

    if centers is None:
        center_mask = np.ones(sample.shape[0], dtype=bool)
        center_vals = np.arange(sample.shape[0], dtype=float)
    else:
        center_vals = np.asarray(centers, dtype=float)
        if center_vals.shape[0] != sample.shape[0]:
            return out
        center_mask = _efficiency_vector_bin_mask(
            centers=center_vals,
            axis_name=str(axis_name or ""),
            fiducial=fiducial or {},
        ) if fiducial is not None else np.isfinite(center_vals)
    if not np.any(center_mask):
        return out

    if sample_unc is None:
        sample_unc_arr = np.zeros(sample.shape, dtype=float)
    else:
        sample_unc_arr = np.asarray(sample_unc, dtype=float)
    if candidates_unc is None:
        candidates_unc_arr = np.zeros(candidates.shape, dtype=float)
    else:
        candidates_unc_arr = np.asarray(candidates_unc, dtype=float)
    if sample_unc_arr.shape != sample.shape or candidates_unc_arr.shape != candidates.shape:
        return out

    valid = center_mask[None, :] & np.isfinite(sample)[None, :] & np.isfinite(candidates)
    valid_counts = np.sum(valid, axis=1)
    ok = valid_counts >= max(int(min_valid_bins), 1)
    if not np.any(ok):
        return out

    floor_sq = max(float(uncertainty_floor), 0.0) ** 2
    if np.any(np.isfinite(sample_unc_arr)) or np.any(np.isfinite(candidates_unc_arr)):
        sample_var = np.where(np.isfinite(sample_unc_arr), sample_unc_arr * sample_unc_arr, 0.0)
        cand_var = np.where(np.isfinite(candidates_unc_arr), candidates_unc_arr * candidates_unc_arr, 0.0)
        combined_var = floor_sq + sample_var[None, :] + cand_var
        weights = np.where(valid, 1.0 / np.maximum(combined_var, floor_sq if floor_sq > 0.0 else 1e-12), 0.0)
    else:
        weights = np.where(valid, 1.0, 0.0)

    sample_mat = np.broadcast_to(sample[None, :], candidates.shape)
    sample_norm, cand_norm = _normalize_vectors_pairwise(
        sample=sample_mat,
        candidates=candidates,
        valid=valid,
        weights=weights,
        normalization=normalization,
    )
    total = np.zeros(candidates.shape[0], dtype=float)

    if amplitude_weight > 0.0:
        amp = _relative_vector_amplitude_many(
            sample=sample,
            candidates=candidates,
            valid=valid,
            weights=weights,
            stat=amplitude_stat,
        )
        total += max(float(amplitude_weight), 0.0) * np.where(np.isfinite(amp), amp, 0.0)

    if shape_weight > 0.0:
        shape = _weighted_lp_from_arrays(
            sample=sample_norm,
            candidates=cand_norm,
            valid=valid,
            weights=weights,
            p_norm=float(p_norm),
        )
        total += max(float(shape_weight), 0.0) * np.where(np.isfinite(shape), shape, 0.0)

    if slope_weight > 0.0 and sample.size >= 2:
        delta = np.diff(center_vals)
        delta = np.where(np.isfinite(delta) & (np.abs(delta) > 1e-12), delta, 1.0)
        slope_valid = valid[:, 1:] & valid[:, :-1]
        slope_weights = 0.5 * (weights[:, 1:] + weights[:, :-1])
        sample_slope = (sample_norm[:, 1:] - sample_norm[:, :-1]) / delta[None, :]
        cand_slope = (cand_norm[:, 1:] - cand_norm[:, :-1]) / delta[None, :]
        slope = _weighted_lp_from_arrays(
            sample=sample_slope,
            candidates=cand_slope,
            valid=slope_valid,
            weights=slope_weights,
            p_norm=float(p_norm),
        )
        total += max(float(slope_weight), 0.0) * np.where(np.isfinite(slope), slope, 0.0)

    if cdf_weight > 0.0:
        sample_pos = np.where(valid, np.clip(sample_norm, 0.0, None), 0.0)
        cand_pos = np.where(valid, np.clip(cand_norm, 0.0, None), 0.0)
        sample_sum = np.sum(sample_pos, axis=1)
        cand_sum = np.sum(cand_pos, axis=1)
        cdf_ok = sample_sum > 1e-12
        cdf_valid = valid & cdf_ok[:, None] & (cand_sum > 1e-12)[:, None]
        sample_cdf = np.cumsum(sample_pos / np.maximum(sample_sum[:, None], 1e-12), axis=1)
        cand_cdf = np.cumsum(cand_pos / np.maximum(cand_sum[:, None], 1e-12), axis=1)
        cdf = _weighted_lp_from_arrays(
            sample=sample_cdf,
            candidates=cand_cdf,
            valid=cdf_valid,
            weights=weights,
            p_norm=float(p_norm),
        )
        total += max(float(cdf_weight), 0.0) * np.where(np.isfinite(cdf), cdf, 0.0)

    out[ok] = total[ok]
    return out


def _resolve_histogram_distance_cfg(raw_cfg: Mapping[str, object] | None) -> dict[str, object]:
    cfg = raw_cfg if isinstance(raw_cfg, Mapping) else {}
    raw_mode = str(cfg.get("distance", "histogram_emd")).strip().lower()
    defaults = {
        "normalization": "unit_sum",
        "p_norm": 1.0,
        "amplitude_weight": 0.0,
        "shape_weight": 0.0,
        "slope_weight": 0.0,
        "cdf_weight": 1.0,
        "amplitude_stat": "sum",
    }
    if raw_mode in {"histogram_emd", "emd"}:
        return _resolve_vector_distance_common_cfg(cfg, defaults=defaults)
    if raw_mode in {"histogram_shape_plus_mass", "histogram_emd_shape_plus_mass", "shape_plus_mass", "emd_plus_mass"}:
        hist_cfg = dict(cfg)
        hist_cfg["distance"] = "ordered_vector_lp"
        hist_cfg.setdefault("normalization", "unit_sum")
        hist_cfg.setdefault("p_norm", 1.0)
        hist_cfg.setdefault("shape_weight", 0.0)
        hist_cfg.setdefault("slope_weight", 0.0)
        hist_cfg.setdefault("cdf_weight", 1.0)
        hist_cfg.setdefault("amplitude_stat", "sum")
        hist_cfg.setdefault("amplitude_weight", cfg.get("mass_weight", 1.0))
        return _resolve_vector_distance_common_cfg(hist_cfg, defaults=defaults)
    if raw_mode in {"histogram_l1", "l1"}:
        hist_cfg = dict(cfg)
        hist_cfg.setdefault("distance", "ordered_vector_lp")
        hist_cfg.setdefault("normalization", "unit_sum")
        hist_cfg.setdefault("p_norm", 1.0)
        hist_cfg.setdefault("shape_weight", cfg.get("shape_weight", 1.0))
        hist_cfg.setdefault("amplitude_weight", cfg.get("mass_weight", 0.0))
        hist_cfg.setdefault("slope_weight", 0.0)
        hist_cfg.setdefault("cdf_weight", 0.0)
        hist_cfg.setdefault("amplitude_stat", "sum")
        return _resolve_vector_distance_common_cfg(hist_cfg, defaults=defaults)
    if raw_mode in {"histogram_l2", "l2"}:
        hist_cfg = dict(cfg)
        hist_cfg.setdefault("distance", "ordered_vector_lp")
        hist_cfg.setdefault("normalization", "unit_sum")
        hist_cfg.setdefault("p_norm", 2.0)
        hist_cfg.setdefault("shape_weight", cfg.get("shape_weight", 1.0))
        hist_cfg.setdefault("amplitude_weight", cfg.get("mass_weight", 0.0))
        hist_cfg.setdefault("slope_weight", 0.0)
        hist_cfg.setdefault("cdf_weight", 0.0)
        hist_cfg.setdefault("amplitude_stat", "sum")
        return _resolve_vector_distance_common_cfg(hist_cfg, defaults=defaults)
    if raw_mode in {"histogram_hellinger", "hellinger"}:
        hist_cfg = dict(cfg)
        hist_cfg.setdefault("distance", "ordered_vector_lp")
        hist_cfg.setdefault("normalization", "unit_sum")
        hist_cfg.setdefault("p_norm", 2.0)
        hist_cfg.setdefault("shape_weight", cfg.get("shape_weight", 1.0))
        hist_cfg.setdefault("amplitude_weight", cfg.get("mass_weight", 0.0))
        hist_cfg.setdefault("slope_weight", 0.0)
        hist_cfg.setdefault("cdf_weight", 0.0)
        hist_cfg.setdefault("amplitude_stat", "sum")
        return _resolve_vector_distance_common_cfg(hist_cfg, defaults=defaults)
    if raw_mode in {"histogram_jsd", "jsd"}:
        hist_cfg = dict(cfg)
        hist_cfg.setdefault("distance", "ordered_vector_lp")
        hist_cfg.setdefault("normalization", "unit_sum")
        hist_cfg.setdefault("p_norm", 1.0)
        hist_cfg.setdefault("shape_weight", cfg.get("shape_weight", 0.5))
        hist_cfg.setdefault("amplitude_weight", cfg.get("mass_weight", 0.0))
        hist_cfg.setdefault("slope_weight", 0.0)
        hist_cfg.setdefault("cdf_weight", cfg.get("cdf_weight", 0.5))
        hist_cfg.setdefault("amplitude_stat", "sum")
        return _resolve_vector_distance_common_cfg(hist_cfg, defaults=defaults)
    if raw_mode in {"ordered_vector_lp", "vector_curve_lp", "vector_lp", "lp"}:
        return _resolve_vector_distance_common_cfg(cfg, defaults=defaults)
    return _resolve_vector_distance_common_cfg(cfg, defaults=defaults)


def _histogram_distance_many(
    sample_hist: np.ndarray,
    candidates_hist: np.ndarray,
    *,
    distance: str,
    normalization: str = "unit_sum",
    p_norm: float = 1.0,
    amplitude_weight: float = 0.0,
    shape_weight: float = 0.0,
    slope_weight: float = 0.0,
    cdf_weight: float = 1.0,
    amplitude_stat: str = "sum",
) -> np.ndarray:
    hist_cfg = _resolve_histogram_distance_cfg(
        {
            "distance": distance,
            "normalization": normalization,
            "p_norm": p_norm,
            "amplitude_weight": amplitude_weight,
            "shape_weight": shape_weight,
            "slope_weight": slope_weight,
            "cdf_weight": cdf_weight,
            "amplitude_stat": amplitude_stat,
        }
    )
    return _ordered_vector_distance_many(
        sample_vec=np.asarray(sample_hist, dtype=float),
        candidates_vec=np.asarray(candidates_hist, dtype=float),
        normalization=str(hist_cfg["normalization"]),
        p_norm=float(hist_cfg["p_norm"]),
        amplitude_weight=float(hist_cfg["amplitude_weight"]),
        shape_weight=float(hist_cfg["shape_weight"]),
        slope_weight=float(hist_cfg["slope_weight"]),
        cdf_weight=float(hist_cfg["cdf_weight"]),
        amplitude_stat=str(hist_cfg["amplitude_stat"]),
    )


def _histogram_component_share_breakdown(
    *,
    sample_hist: np.ndarray,
    candidate_hist: np.ndarray,
    feature_names: Sequence[str],
    term_share_of_total: float,
    distance: str = "ordered_vector_lp",
    normalization: str = "unit_sum",
    p_norm: float = 1.0,
    amplitude_weight: float = 0.0,
    shape_weight: float = 0.0,
    slope_weight: float = 0.0,
    cdf_weight: float = 1.0,
    amplitude_stat: str = "sum",
) -> tuple[dict[str, float], dict[str, float]]:
    hist_cfg = _resolve_histogram_distance_cfg(
        {
            "distance": distance,
            "normalization": normalization,
            "p_norm": p_norm,
            "amplitude_weight": amplitude_weight,
            "shape_weight": shape_weight,
            "slope_weight": slope_weight,
            "cdf_weight": cdf_weight,
            "amplitude_stat": amplitude_stat,
        }
    )
    amp_scale = float(hist_cfg["amplitude_weight"])
    shape_scale = float(hist_cfg["shape_weight"])
    slope_scale = float(hist_cfg["slope_weight"])
    cdf_scale = float(hist_cfg["cdf_weight"])
    p_use = max(float(hist_cfg["p_norm"]), 1e-12)

    sample = np.asarray(sample_hist, dtype=float)
    candidate = np.asarray(candidate_hist, dtype=float)
    names = [str(name) for name in feature_names]
    if sample.ndim != 1 or candidate.ndim != 1 or sample.size != candidate.size or sample.size != len(names):
        return {}, {}

    valid_mask = np.isfinite(sample) & np.isfinite(candidate)
    if int(np.sum(valid_mask)) < 1:
        return {}, {}

    valid = valid_mask[None, :]
    weights = np.where(valid, 1.0, 0.0)
    sample_mat = np.broadcast_to(sample[None, :], (1, sample.size))
    candidate_mat = candidate[None, :]
    sample_norm, candidate_norm = _normalize_vectors_pairwise(
        sample=sample_mat,
        candidates=candidate_mat,
        valid=valid,
        weights=weights,
        normalization=str(hist_cfg["normalization"]),
    )

    bin_strengths = np.zeros(sample.size, dtype=float)
    global_strengths: dict[str, float] = {}

    if amp_scale > 0.0:
        amp = _relative_vector_amplitude_many(
            sample=sample,
            candidates=candidate_mat,
            valid=valid,
            weights=weights,
            stat=str(hist_cfg["amplitude_stat"]),
        )
        if amp.size and np.isfinite(amp[0]) and amp[0] > 0.0:
            global_strengths["rate_histogram::total_amplitude"] = float(amp_scale * amp[0])

    if shape_scale > 0.0:
        diff = np.zeros(sample.size, dtype=float)
        diff[valid_mask] = np.power(
            np.abs(candidate_norm[0, valid_mask] - sample_norm[0, valid_mask]),
            p_use,
        )
        bin_strengths += shape_scale * diff

    if slope_scale > 0.0 and sample.size >= 2:
        delta = np.ones(sample.size - 1, dtype=float)
        slope_valid = valid_mask[1:] & valid_mask[:-1]
        if np.any(slope_valid):
            sample_slope = (sample_norm[0, 1:] - sample_norm[0, :-1]) / delta
            cand_slope = (candidate_norm[0, 1:] - candidate_norm[0, :-1]) / delta
            seg_strength = np.zeros(sample.size - 1, dtype=float)
            seg_strength[slope_valid] = np.power(
                np.abs(cand_slope[slope_valid] - sample_slope[slope_valid]),
                p_use,
            )
            seg_strength *= slope_scale
            bin_strengths[:-1] += 0.5 * seg_strength
            bin_strengths[1:] += 0.5 * seg_strength

    if cdf_scale > 0.0:
        sample_pos = np.where(valid_mask, np.clip(sample_norm[0], 0.0, None), 0.0)
        cand_pos = np.where(valid_mask, np.clip(candidate_norm[0], 0.0, None), 0.0)
        sum_sample = float(np.sum(sample_pos))
        sum_cand = float(np.sum(cand_pos))
        if sum_sample > 1e-12 and sum_cand > 1e-12:
            sample_cdf = np.cumsum(sample_pos / sum_sample)
            cand_cdf = np.cumsum(cand_pos / sum_cand)
            cdf_strength = np.zeros(sample.size, dtype=float)
            cdf_strength[valid_mask] = np.power(
                np.abs(cand_cdf[valid_mask] - sample_cdf[valid_mask]),
                p_use,
            )
            bin_strengths += cdf_scale * cdf_strength

    strength_sum = float(np.sum(bin_strengths[valid_mask]) + sum(global_strengths.values()))
    if not np.isfinite(strength_sum) or strength_sum <= 0.0:
        return {}, {}

    within_term: dict[str, float] = {}
    total_share: dict[str, float] = {}
    scale = max(float(term_share_of_total), 0.0)
    for idx, name in enumerate(names):
        if not bool(valid_mask[idx]):
            continue
        value = float(bin_strengths[idx] / strength_sum)
        if not np.isfinite(value) or value <= 0.0:
            continue
        key = f"rate_histogram::{name}"
        within_term[key] = value
        total_share[key] = float(scale * value)
    for key, raw_value in global_strengths.items():
        value = float(raw_value / strength_sum)
        within_term[key] = value
        total_share[key] = float(scale * value)
    return total_share, within_term


def _efficiency_vector_group_distance_many(
    *,
    sample_eff: np.ndarray,
    candidates_eff: np.ndarray,
    sample_unc: np.ndarray | None,
    candidates_unc: np.ndarray | None,
    centers: np.ndarray,
    axis_name: str,
    fiducial: Mapping[str, float | None],
    uncertainty_floor: float,
    min_valid_bins: int,
    normalization: str = "none",
    p_norm: float = 2.0,
    amplitude_weight: float = 0.0,
    shape_weight: float = 1.0,
    slope_weight: float = 0.0,
    cdf_weight: float = 0.0,
    amplitude_stat: str = "mean",
) -> np.ndarray:
    return _ordered_vector_distance_many(
        sample_vec=np.asarray(sample_eff, dtype=float),
        candidates_vec=np.asarray(candidates_eff, dtype=float),
        sample_unc=None if sample_unc is None else np.asarray(sample_unc, dtype=float),
        candidates_unc=None if candidates_unc is None else np.asarray(candidates_unc, dtype=float),
        centers=np.asarray(centers, dtype=float),
        axis_name=str(axis_name),
        fiducial=fiducial,
        uncertainty_floor=float(uncertainty_floor),
        min_valid_bins=int(min_valid_bins),
        normalization=normalization,
        p_norm=float(p_norm),
        amplitude_weight=float(amplitude_weight),
        shape_weight=float(shape_weight),
        slope_weight=float(slope_weight),
        cdf_weight=float(cdf_weight),
        amplitude_stat=str(amplitude_stat),
    )


def _resolve_efficiency_vector_distance_cfg(raw_cfg: Mapping[str, object] | None) -> dict[str, object]:
    cfg = raw_cfg if isinstance(raw_cfg, Mapping) else {}
    raw_mode = str(cfg.get("distance", "uncertainty_weighted_vector_mean")).strip().lower()
    defaults = {
        "normalization": "none",
        "p_norm": 2.0,
        "amplitude_weight": 0.0,
        "shape_weight": 1.0,
        "slope_weight": 0.0,
        "cdf_weight": 0.0,
        "amplitude_stat": "mean",
    }
    group_reduction = "mean"
    mapped_cfg = dict(cfg)
    if raw_mode in {"uncertainty_weighted_vector_median", "uncertainty_weighted_rms_median"}:
        mapped_cfg.setdefault("p_norm", 2.0)
        group_reduction = "median"
    elif raw_mode in {"uncertainty_weighted_vector_rms"}:
        mapped_cfg.setdefault("p_norm", 2.0)
        group_reduction = "rms"
    elif raw_mode in {"uncertainty_weighted_vector_p75"}:
        mapped_cfg.setdefault("p_norm", 2.0)
        group_reduction = "p75"
    elif raw_mode in {"uncertainty_weighted_vector_l1_mean", "uncertainty_weighted_abs_mean"}:
        mapped_cfg.setdefault("p_norm", 1.0)
        group_reduction = "mean"
    elif raw_mode in {"uncertainty_weighted_vector_l1_median", "uncertainty_weighted_abs_median"}:
        mapped_cfg.setdefault("p_norm", 1.0)
        group_reduction = "median"
    elif raw_mode in {"uncertainty_weighted_vector_l1_rms"}:
        mapped_cfg.setdefault("p_norm", 1.0)
        group_reduction = "rms"
    elif raw_mode in {"uncertainty_weighted_vector_l1_p75"}:
        mapped_cfg.setdefault("p_norm", 1.0)
        group_reduction = "p75"
    elif raw_mode in {"uncertainty_weighted_vector_max", "uncertainty_weighted_rms_max"}:
        mapped_cfg.setdefault("p_norm", 2.0)
        group_reduction = "max"
    elif raw_mode in {"uncertainty_weighted_vector_l1_max"}:
        mapped_cfg.setdefault("p_norm", 1.0)
        group_reduction = "max"
    elif raw_mode in {"ordered_vector_lp", "vector_curve_lp", "vector_lp", "lp"}:
        group_reduction = str(cfg.get("group_reduction", "mean")).strip().lower()
    else:
        mapped_cfg.setdefault("p_norm", 2.0)
        group_reduction = str(cfg.get("group_reduction", "mean")).strip().lower()

    if group_reduction not in {"mean", "median", "max", "rms", "p75"}:
        group_reduction = "mean"

    vector_cfg = _resolve_vector_distance_common_cfg(mapped_cfg, defaults=defaults)
    uncertainty_floor = max(_safe_float(cfg.get("uncertainty_floor"), 0.02), 0.0)
    min_valid_bins = max(
        1,
        _safe_int(cfg.get("min_valid_bins_per_vector"), 3, minimum=1),
    )
    fiducial = _normalize_efficiency_vector_fiducial(cfg.get("fiducial", {}))
    vector_cfg.update(
        {
            "group_reduction": group_reduction,
            "uncertainty_floor": float(uncertainty_floor),
            "min_valid_bins_per_vector": int(min_valid_bins),
            "fiducial": fiducial,
        }
    )
    p_norm = float(vector_cfg.get("p_norm", 2.0))
    if np.isclose(p_norm, 1.0):
        vector_cfg["pointwise_loss"] = "l1"
    elif np.isclose(p_norm, 2.0):
        vector_cfg["pointwise_loss"] = "l2"
    else:
        vector_cfg["pointwise_loss"] = f"lp{p_norm:g}"
    return vector_cfg


def _reduce_efficiency_vector_group_stack(
    stacked: np.ndarray,
    *,
    group_reduction: str,
) -> np.ndarray:
    arr = np.asarray(stacked, dtype=float)
    if arr.ndim != 2:
        return np.asarray([], dtype=float)
    out = np.full(arr.shape[1], np.nan, dtype=float)
    finite = np.isfinite(arr)
    ok = np.sum(finite, axis=0) > 0
    if not np.any(ok):
        return out
    with np.errstate(invalid="ignore"):
        if str(group_reduction).strip().lower() == "median":
            out[ok] = np.nanmedian(arr[:, ok], axis=0)
        elif str(group_reduction).strip().lower() == "max":
            out[ok] = np.nanmax(arr[:, ok], axis=0)
        elif str(group_reduction).strip().lower() == "rms":
            out[ok] = np.sqrt(np.nanmean(arr[:, ok] * arr[:, ok], axis=0))
        elif str(group_reduction).strip().lower() == "p75":
            out[ok] = np.nanpercentile(arr[:, ok], 75.0, axis=0)
        else:
            out[ok] = np.nanmean(arr[:, ok], axis=0)
    return out


def _efficiency_vector_component_share_breakdown(
    *,
    payloads: Sequence[Mapping[str, object]],
    row_idx: int,
    candidate_idx: int,
    fiducial: Mapping[str, float | None],
    uncertainty_floor: float,
    min_valid_bins: int,
    term_share_of_total: float,
    normalization: str = "none",
    p_norm: float = 2.0,
    amplitude_weight: float = 0.0,
    shape_weight: float = 1.0,
    slope_weight: float = 0.0,
    cdf_weight: float = 0.0,
    amplitude_stat: str = "mean",
    group_reduction: str = "mean",
) -> tuple[dict[str, float], dict[str, float]]:
    if not payloads:
        return {}, {}

    group_values: dict[str, float] = {}
    for payload in payloads:
        label = str(payload.get("label", "")).strip()
        if not label:
            continue
        sample_eff = np.asarray(payload.get("data_eff", []), dtype=float)
        dict_eff = np.asarray(payload.get("dict_eff", []), dtype=float)
        if sample_eff.ndim != 2 or dict_eff.ndim != 2:
            continue
        if row_idx < 0 or row_idx >= sample_eff.shape[0] or candidate_idx < 0 or candidate_idx >= dict_eff.shape[0]:
            continue
        sample_unc = np.asarray(payload.get("data_unc", []), dtype=float)
        dict_unc = np.asarray(payload.get("dict_unc", []), dtype=float)
        group_dist = _efficiency_vector_group_distance_many(
            sample_eff=sample_eff[row_idx],
            candidates_eff=dict_eff[candidate_idx : candidate_idx + 1],
            sample_unc=sample_unc[row_idx] if sample_unc.ndim == 2 else None,
            candidates_unc=dict_unc[candidate_idx : candidate_idx + 1] if dict_unc.ndim == 2 else None,
            centers=np.asarray(payload.get("centers", []), dtype=float),
            axis_name=str(payload.get("axis", "")),
            fiducial=fiducial,
            uncertainty_floor=uncertainty_floor,
            min_valid_bins=min_valid_bins,
            normalization=normalization,
            p_norm=p_norm,
            amplitude_weight=amplitude_weight,
            shape_weight=shape_weight,
            slope_weight=slope_weight,
            cdf_weight=cdf_weight,
            amplitude_stat=amplitude_stat,
        )
        if group_dist is None or group_dist.size == 0:
            continue
        value = float(group_dist[0])
        if np.isfinite(value) and value > 0.0:
            group_values[f"efficiency_vectors::{label}"] = value

    if not group_values:
        return {}, {}

    reduction = str(group_reduction).strip().lower()
    if reduction == "max":
        max_key = max(group_values.items(), key=lambda item: float(item[1]))[0]
        strengths = {key: (1.0 if key == max_key else 0.0) for key in group_values}
    elif reduction == "rms":
        strengths = {key: float(value * value) for key, value in group_values.items()}
    else:
        strengths = {key: float(value) for key, value in group_values.items()}

    value_sum = float(sum(strengths.values()))
    if not np.isfinite(value_sum) or value_sum <= 0.0:
        return {}, {}

    within_term = {
        key: float(value / value_sum)
        for key, value in strengths.items()
    }
    scale = max(float(term_share_of_total), 0.0)
    total_share = {
        key: float(scale * share)
        for key, share in within_term.items()
    }
    return total_share, within_term


def _distance_many(
    sample_vec: np.ndarray | None,
    cand_mat: np.ndarray | None,
    *,
    distance_metric: str,
    min_valid_dims: int = 2,
) -> np.ndarray | None:
    if sample_vec is None or cand_mat is None:
        return None
    sample = np.asarray(sample_vec, dtype=float)
    candidates = np.asarray(cand_mat, dtype=float)
    if candidates.ndim != 2 or sample.ndim != 1:
        return None
    if candidates.shape[0] == 0:
        return np.asarray([], dtype=float)
    dist_many_fn = DISTANCE_FNS_MANY.get(distance_metric, None)
    if dist_many_fn is not None:
        return np.asarray(
            dist_many_fn(sample, candidates, min_valid_dims=max(int(min_valid_dims), 1)),
            dtype=float,
        )
    dist_fn = DISTANCE_FNS.get(distance_metric, _l2)
    return np.asarray([dist_fn(sample, candidates[j]) for j in range(candidates.shape[0])], dtype=float)


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


def _effective_atol(base_atol: float, value: float) -> float:
    """Absolute tolerance that scales with magnitude for |value| > 1."""
    return max(base_atol, base_atol * max(1.0, abs(value)))


def _combine_distance_terms(
    *,
    base_distances: np.ndarray | None,
    aux_terms: Sequence[tuple[np.ndarray | None, float, str]],
) -> np.ndarray:
    named_aux_terms = [
        (f"aux_{idx}", distances, weight, blend_mode)
        for idx, (distances, weight, blend_mode) in enumerate(aux_terms)
    ]
    total, _ = _combine_distance_terms_with_breakdown(
        base_distances=base_distances,
        aux_terms=named_aux_terms,
    )
    return total


def _combine_distance_terms_with_breakdown(
    *,
    base_distances: np.ndarray | None,
    aux_terms: Sequence[tuple[str, np.ndarray | None, float, str]],
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    base = None if base_distances is None else np.asarray(base_distances, dtype=float)
    present_aux: list[tuple[str, np.ndarray, float, str]] = []
    for name, distances, weight, blend_mode in aux_terms:
        if distances is None or float(weight) <= 0.0:
            continue
        label = str(name).strip() or f"aux_{len(present_aux)}"
        present_aux.append(
            (
                label,
                np.asarray(distances, dtype=float),
                float(weight),
                _normalize_hist_blend_mode(blend_mode),
            )
        )

    if base is None and not present_aux:
        return np.asarray([], dtype=float), {}
    if base is not None:
        ref_shape = base.shape
    else:
        ref_shape = present_aux[0][1].shape
    for _, distances, _, _ in present_aux:
        if distances.shape != ref_shape:
            return np.full(ref_shape[0], np.nan, dtype=float), {}

    term_arrays: dict[str, np.ndarray] = {}
    use_normalized_base = base is not None and any(mode == "normalized" for _, _, _, mode in present_aux)
    if base is None:
        out = np.full(ref_shape[0], np.nan, dtype=float)
    else:
        base_term = base / _robust_scale(base) if use_normalized_base else base
        out = np.asarray(base_term, dtype=float).copy()
        term_arrays["scalar_base"] = out.copy()

    for name, distances, weight, blend_mode in present_aux:
        term = distances / _robust_scale(distances) if blend_mode == "normalized" else distances
        term = float(weight) * np.asarray(term, dtype=float)
        term_arrays[name] = term.copy()
        term_finite = np.isfinite(term)
        if out.shape != term.shape:
            return np.full(ref_shape[0], np.nan, dtype=float), {}
        out_finite = np.isfinite(out)
        both_finite = out_finite & term_finite
        term_only = (~out_finite) & term_finite
        out[both_finite] = out[both_finite] + term[both_finite]
        out[term_only] = term[term_only]
    return out, term_arrays


def _compute_non_hist_base_distances(
    *,
    distance_metric: str,
    sample_scaled_non_hist: np.ndarray | None,
    candidates_scaled_non_hist: np.ndarray | None,
    min_valid_non_hist_dims: int = 2,
    dd_weights: np.ndarray | None = None,
    dd_p_norm: float | None = None,
) -> np.ndarray | None:
    if sample_scaled_non_hist is None or candidates_scaled_non_hist is None:
        return None
    if dd_weights is not None and dd_p_norm is not None:
        return _weighted_lp_many(
            sample_scaled_non_hist,
            candidates_scaled_non_hist,
            weights=dd_weights,
            p_norm=dd_p_norm,
            min_valid_dims=max(int(min_valid_non_hist_dims), 1),
        )
    return _distance_many(
        sample_scaled_non_hist,
        candidates_scaled_non_hist,
        distance_metric=distance_metric,
        min_valid_dims=max(int(min_valid_non_hist_dims), 1),
    )


def _scalar_feature_total_share_breakdown(
    *,
    feature_names: Sequence[str],
    sample_values: np.ndarray | None,
    candidate_values: np.ndarray | None,
    scalar_term_value: float,
    total_distance_value: float,
    distance_metric: str,
    dd_weights: np.ndarray | None = None,
    dd_p_norm: float | None = None,
) -> dict[str, float]:
    if sample_values is None or candidate_values is None:
        return {}
    scalar_term = float(scalar_term_value)
    total_distance = float(total_distance_value)
    if not np.isfinite(scalar_term) or scalar_term <= 0.0:
        return {}
    if not np.isfinite(total_distance) or total_distance <= 0.0:
        return {}

    sample = np.asarray(sample_values, dtype=float)
    candidate = np.asarray(candidate_values, dtype=float)
    if sample.shape != candidate.shape or sample.size != len(feature_names):
        return {}

    finite = np.isfinite(sample) & np.isfinite(candidate)
    strengths = np.zeros(sample.shape[0], dtype=float)
    if dd_weights is not None and dd_p_norm is not None:
        weights = np.asarray(dd_weights, dtype=float)
        if weights.shape != sample.shape:
            return {}
        finite &= weights > 0.0
        strengths[finite] = weights[finite] * np.power(np.abs(candidate[finite] - sample[finite]), float(dd_p_norm))
    else:
        delta = np.abs(candidate[finite] - sample[finite])
        metric = str(distance_metric).strip().lower()
        if metric in {"l2", "l2_zscore", "l2_raw"}:
            strengths[finite] = delta * delta
        else:
            strengths[finite] = delta

    strength_sum = float(np.sum(strengths[finite]))
    if not np.isfinite(strength_sum) or strength_sum <= 0.0:
        return {}

    scalar_share_of_total = scalar_term / total_distance
    out: dict[str, float] = {}
    for idx, name in enumerate(feature_names):
        if not finite[idx]:
            continue
        value = scalar_share_of_total * float(strengths[idx] / strength_sum)
        if np.isfinite(value) and value > 0.0:
            out[str(name)] = value
    return out


def compute_candidate_distances(
    *,
    distance_metric: str,
    sample_scaled_non_hist: np.ndarray | None,
    candidates_scaled_non_hist: np.ndarray | None,
    sample_hist_raw: np.ndarray | None,
    candidates_hist_raw: np.ndarray | None,
    histogram_distance_weight: float,
    histogram_distance_blend_mode: str,
    histogram_distance_mode: str = "ordered_vector_lp",
    histogram_normalization: str = "unit_sum",
    histogram_p_norm: float = 1.0,
    histogram_amplitude_weight: float = 0.0,
    histogram_shape_weight: float = 0.0,
    histogram_slope_weight: float = 0.0,
    histogram_cdf_weight: float = 1.0,
    histogram_amplitude_stat: str = "sum",
    min_valid_non_hist_dims: int = 2,
    dd_weights: np.ndarray | None = None,
    dd_p_norm: float | None = None,
) -> np.ndarray:
    """
    Compute candidate distances with the same feature+histogram composition used
    by the estimator.

    When *dd_weights* and *dd_p_norm* are supplied (from the STEP 1.5
    distance-definition artifact), the weighted Lp metric is used for the
    non-histogram features instead of the default ``distance_metric`` function.
    """
    base = _compute_non_hist_base_distances(
        distance_metric=distance_metric,
        sample_scaled_non_hist=sample_scaled_non_hist,
        candidates_scaled_non_hist=candidates_scaled_non_hist,
        min_valid_non_hist_dims=min_valid_non_hist_dims,
        dd_weights=dd_weights,
        dd_p_norm=dd_p_norm,
    )
    hist = None
    if sample_hist_raw is not None and candidates_hist_raw is not None:
        hist = _histogram_distance_many(
            np.asarray(sample_hist_raw, dtype=float),
            np.asarray(candidates_hist_raw, dtype=float),
            distance=histogram_distance_mode,
            normalization=histogram_normalization,
            p_norm=histogram_p_norm,
            amplitude_weight=histogram_amplitude_weight,
            shape_weight=histogram_shape_weight,
            slope_weight=histogram_slope_weight,
            cdf_weight=histogram_cdf_weight,
            amplitude_stat=histogram_amplitude_stat,
        )
    return _combine_distance_terms(
        base_distances=base,
        aux_terms=[
            (
                hist,
                max(float(histogram_distance_weight), 0.0),
                _normalize_hist_blend_mode(histogram_distance_blend_mode),
            )
        ],
    )


def _build_neighbor_weights(
    distances: np.ndarray,
    *,
    weighting_mode: str,
    idw_power: float,
    softmax_temperature: float,
    distance_floor: float,
) -> np.ndarray:
    d = np.asarray(distances, dtype=float)
    n = d.size
    if n == 0:
        return np.asarray([], dtype=float)
    mode = _normalize_weighting_mode(weighting_mode)
    finite = np.isfinite(d)
    out = np.zeros(n, dtype=float)
    if not np.any(finite):
        return out

    d_eff = np.clip(d[finite], 0.0, None)
    if mode == "uniform":
        out[finite] = 1.0
    elif mode == "softmax":
        temp = max(float(softmax_temperature), 1e-12)
        d_ref = d_eff - float(np.min(d_eff))
        out[finite] = np.exp(-d_ref / temp)
    else:
        power = max(float(idw_power), 0.0)
        eps = max(float(distance_floor), 1e-15)
        out[finite] = 1.0 / np.power(np.maximum(d_eff, eps), power)

    out = np.where(np.isfinite(out), out, 0.0)
    s = float(np.sum(out))
    if s > 0.0:
        out /= s
    return out


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
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


def _local_linear_estimate(
    values: np.ndarray,
    weights: np.ndarray,
    *,
    sample_features: np.ndarray | None,
    neighbor_features: np.ndarray | None,
    parameter_name: str | None = None,
    ridge_lambda: float = 1e-2,
) -> float:
    vals = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    if sample_features is None or neighbor_features is None:
        return float(np.sum(w * np.nan_to_num(vals)))

    x0 = np.asarray(sample_features, dtype=float)
    X = np.asarray(neighbor_features, dtype=float)
    if X.ndim != 2 or x0.ndim != 1 or X.shape[0] != vals.size:
        return float(np.sum(w * np.nan_to_num(vals)))
    if X.shape[1] == 0:
        return float(np.sum(w * np.nan_to_num(vals)))

    feat_mask = np.isfinite(x0)
    if not np.any(feat_mask):
        return float(np.sum(w * np.nan_to_num(vals)))

    X = X[:, feat_mask]
    x0 = x0[feat_mask]
    row_mask = (
        np.all(np.isfinite(X), axis=1)
        & np.isfinite(vals)
        & np.isfinite(w)
        & (w > 0.0)
    )
    if int(np.sum(row_mask)) < 3:
        return float(np.sum(w * np.nan_to_num(vals)))

    X_use = X[row_mask]
    y_use = vals[row_mask]
    w_use = w[row_mask]
    w_sum = float(np.sum(w_use))
    if not np.isfinite(w_sum) or w_sum <= 0.0:
        return float(np.sum(w * np.nan_to_num(vals)))
    w_use = w_use / w_sum
    weighted_mean_local = float(np.sum(w_use * y_use))
    if not np.isfinite(weighted_mean_local):
        weighted_mean_local = float(np.sum(w * np.nan_to_num(vals)))

    centered = X_use - x0[None, :]
    A = np.hstack([np.ones((centered.shape[0], 1), dtype=float), centered])
    sqrt_w = np.sqrt(np.clip(w_use, 1e-16, None))
    is_eff_param = False
    if parameter_name is not None:
        pname = str(parameter_name).strip().lower()
        is_eff_param = pname.startswith("eff_") or ("_eff_" in pname)

    y_fit = np.asarray(y_use, dtype=float)
    if is_eff_param:
        # Efficiency-like parameters are physically bounded in [0,1].
        # Fit local linear model in logit space to avoid hard clipping to
        # local neighbor ranges, which can cause artificial saturation.
        eps = 1e-6
        y_fit = np.clip(y_fit, eps, 1.0 - eps)
        y_fit = np.log(y_fit / (1.0 - y_fit))

    Aw = A * sqrt_w[:, None]
    yw = y_fit * sqrt_w

    try:
        # Use unbiased weighted least squares by default. Ridge penalties can
        # shrink slopes and introduce systematic intercept offsets.
        beta = np.linalg.lstsq(Aw, yw, rcond=None)[0]
    except np.linalg.LinAlgError:
        # Fallback: try a tiny ridge regularization only for ill-conditioned rows.
        n_coef = A.shape[1]
        reg = np.zeros((n_coef, n_coef), dtype=float)
        if n_coef > 1:
            reg[1:, 1:] = max(float(ridge_lambda), 0.0) * np.eye(n_coef - 1, dtype=float)
        try:
            beta = np.linalg.solve(Aw.T @ Aw + reg, Aw.T @ yw)
        except np.linalg.LinAlgError:
            pred_fallback = float(np.sum(w_use * y_use))
            if is_eff_param and np.isfinite(pred_fallback):
                return float(np.clip(pred_fallback, 1e-6, 1.0 - 1e-6))
            return pred_fallback

    pred = float(beta[0])
    if not np.isfinite(pred):
        return float(np.sum(w_use * y_use))
    if is_eff_param:
        # inverse-logit with numerical stability
        pred = float(1.0 / (1.0 + np.exp(-np.clip(pred, -40.0, 40.0))))
        y_min = float(np.nanmin(y_use))
        y_max = float(np.nanmax(y_use))
        if np.isfinite(y_min) and np.isfinite(y_max):
            # When the bounded local-linear fit extrapolates beyond the local
            # efficiency envelope, hard-clipping to the edge creates visible
            # plateaus in real-data estimates. Prefer the robust weighted
            # local mean in those cases.
            pred_clipped = float(np.clip(pred, y_min, y_max))
            if abs(pred - pred_clipped) > 1e-12 and np.isfinite(weighted_mean_local):
                pred = float(np.clip(weighted_mean_local, y_min, y_max))
            else:
                pred = pred_clipped
        pred = float(np.clip(pred, 1e-6, 1.0 - 1e-6))
    else:
        y_min = float(np.nanmin(y_use))
        y_max = float(np.nanmax(y_use))
        if np.isfinite(y_min) and np.isfinite(y_max):
            pred = float(np.clip(pred, y_min, y_max))
    return pred


# =====================================================================
# Feature selection helpers
# =====================================================================

TT_RATE_COLUMN_RE = re.compile(r"^(?P<prefix>.+?)_tt_(?P<label>[^_]+)_rate_hz$")
AUTO_TT_PREFIX_PRIORITY = [
    "post",
    "fit_to_post",
    "fit",
    "list_to_fit",
    "list",
    "cal",
    "clean",
    "raw_to_clean",
    "raw",
    "corr",
    "task5_to_corr",
    "fit_to_corr",
    "definitive",
]
PHYSICAL_TT_RATE_LABELS = (
    "1234",
    "123",
    "124",
    "134",
    "234",
    "12",
    "13",
    "14",
    "23",
    "24",
    "34",
)


def _normalize_tt_label(label: object) -> str:
    text = str(label).strip()
    if not text:
        return ""
    try:
        value = float(text)
    except (TypeError, ValueError):
        return text
    if not np.isfinite(value):
        return ""
    if float(value).is_integer():
        return str(int(value))
    return text


def _is_multi_plane_tt_label(label: object) -> bool:
    norm = _normalize_tt_label(label)
    if len(norm) < 2:
        return False
    if not all(ch in {"1", "2", "3", "4"} for ch in norm):
        return False
    return len(set(norm)) == len(norm)


def _prefix_rank(prefix: str) -> int:
    try:
        return AUTO_TT_PREFIX_PRIORITY.index(prefix)
    except ValueError:
        return len(AUTO_TT_PREFIX_PRIORITY)


def _auto_feature_columns(
    df: pd.DataFrame,
    include_global_rate: bool = True,
    global_rate_col: str = "events_per_second_global_rate",
) -> list[str]:
    """Select TT-rate features from the most advanced available task prefix."""
    by_prefix_physical: dict[str, list[str]] = {}
    by_prefix_transition: dict[str, list[str]] = {}
    fallback_non_tt_rate_cols: list[str] = []

    for col in df.columns:
        text = str(col)
        if not text.endswith("_rate_hz"):
            continue
        match = TT_RATE_COLUMN_RE.match(text)
        if match is None:
            fallback_non_tt_rate_cols.append(text)
            continue
        prefix = str(match.group("prefix")).strip()
        label = match.group("label")
        if not _is_multi_plane_tt_label(label):
            continue
        target = by_prefix_transition if "_to_" in prefix else by_prefix_physical
        target.setdefault(prefix, []).append(text)

    cols: list[str] = []
    by_prefix = by_prefix_physical or by_prefix_transition
    if by_prefix:
        selected_prefix = min(
            by_prefix.keys(),
            key=lambda p: (_prefix_rank(p), -len(by_prefix[p]), p),
        )
        cols = sorted(set(by_prefix[selected_prefix]))
    elif fallback_non_tt_rate_cols:
        cols = sorted(set(fallback_non_tt_rate_cols))

    return cols


def resolve_physical_tt_rate_columns(
    df: pd.DataFrame,
    *,
    tt_labels: Sequence[str] = PHYSICAL_TT_RATE_LABELS,
    prefix_selector: str = "last",
    include_to_tt_rate_hz: bool = False,
    require_numeric: bool = True,
) -> tuple[str | None, dict[str, str]]:
    """Resolve one consistent physical TT prefix and its rate columns by label."""
    labels: list[str] = []
    seen: set[str] = set()
    for raw in tt_labels:
        label = _normalize_tt_label(raw)
        if not _is_multi_plane_tt_label(label) or label in seen:
            continue
        labels.append(label)
        seen.add(label)

    selected_cols = _select_tt_rate_columns_for_prefix(
        df,
        prefix_selector=prefix_selector,
        trigger_type_allowlist=labels,
        include_to_tt_rate_hz=include_to_tt_rate_hz,
    )
    if not selected_cols:
        return None, {}

    selected_prefix: str | None = None
    by_label: dict[str, str] = {}
    for col in selected_cols:
        match = TT_RATE_COLUMN_RE.match(str(col).strip())
        if match is None:
            continue
        prefix = str(match.group("prefix")).strip()
        label = _normalize_tt_label(match.group("label"))
        if selected_prefix is None:
            selected_prefix = prefix
        if require_numeric:
            vals = pd.to_numeric(df[col], errors="coerce")
            if not vals.notna().any():
                continue
        if label in seen and label not in by_label:
            by_label[label] = str(col)

    ordered = {label: by_label[label] for label in labels if label in by_label}
    return selected_prefix, ordered


# ── Derived feature mode ─────────────────────────────────────────────
# Empirical efficiencies separate the efficiency signal from the flux
# signal, breaking the degeneracy that afflicts raw TT rates (which are
# all proportional to flux × f(efficiency)).  The global rate carries
# the overall flux scale once efficiencies are controlled for.
DERIVED_EFFICIENCY_COLUMNS = [
    "eff_empirical_1",
    "eff_empirical_2",
    "eff_empirical_3",
    "eff_empirical_4",
]
DERIVED_RATE_COLUMN = "events_per_second_global_rate"
DERIVED_TT_GLOBAL_RATE_COL = "__derived_tt_global_rate_hz"
DERIVED_EFF_PRODUCT_COL = "__derived_eff_emp_product"
DERIVED_LOG_RATE_OVER_EFF_PRODUCT_COL = "__derived_log_tt_rate_over_eff_product"
DERIVED_LOG_EFF_PAIR_SUM_COL = "__derived_log_eff_pair_sum"
DERIVED_LOG_EFF_TRIPLET_SUM_COL = "__derived_log_eff_triplet_sum"

_DERIVED_PHYSICS_FEATURE_ALIASES = {
    "eff_product": "eff_product",
    "emp_eff_product": "eff_product",
    "eff_emp_product": "eff_product",
    "eff_coincidence_moments": "eff_coincidence_moments",
    "eff_pair_triplet_products": "eff_coincidence_moments",
    "pair_triplet_eff_products": "eff_coincidence_moments",
    "eff_pair_triplet_sums": "eff_coincidence_moments",
    "coincidence_eff_moments": "eff_coincidence_moments",
    "log_rate_over_eff_product": "log_rate_over_eff_product",
    "log_tt_rate_over_eff_product": "log_rate_over_eff_product",
    "log_rate_div_eff_product": "log_rate_over_eff_product",
    "log_rate_over_effprod": "log_rate_over_eff_product",
}


def _normalize_prefix_selector(value: object) -> str:
    text = str(value).strip().lower()
    return text if text else "last"


def _normalize_trigger_type_allowlist(value: Sequence[str] | str | None) -> list[str]:
    raw = parse_explicit_feature_columns(value)
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        norm = _normalize_tt_label(item)
        if not norm or not _is_multi_plane_tt_label(norm):
            continue
        if norm in seen:
            continue
        out.append(norm)
        seen.add(norm)
    return out


def _select_tt_rate_columns_for_prefix(
    df: pd.DataFrame,
    *,
    prefix_selector: str = "last",
    trigger_type_allowlist: Sequence[str] | str | None = None,
    include_to_tt_rate_hz: bool = False,
) -> list[str]:
    by_prefix: dict[str, list[str]] = {}
    allowlist = set(_normalize_trigger_type_allowlist(trigger_type_allowlist))
    for col in df.columns:
        text = str(col).strip()
        match = TT_RATE_COLUMN_RE.match(text)
        if match is None:
            continue
        label = _normalize_tt_label(match.group("label"))
        if not _is_multi_plane_tt_label(label):
            continue
        if allowlist and label not in allowlist:
            continue
        prefix = str(match.group("prefix")).strip()
        if not include_to_tt_rate_hz and "_to_" in prefix:
            continue
        by_prefix.setdefault(prefix, []).append(text)

    if not by_prefix:
        return []

    prefix_mode = _normalize_prefix_selector(prefix_selector)
    if prefix_mode == "last":
        selected_prefix = min(
            by_prefix.keys(),
            key=lambda p: (_prefix_rank(p), -len(by_prefix[p]), p),
        )
        return sorted(set(by_prefix[selected_prefix]))
    return sorted(set(by_prefix.get(prefix_mode, [])))


def _common_tt_rate_columns(
    dict_df: pd.DataFrame,
    data_df: pd.DataFrame,
    *,
    prefix_selector: str = "last",
    trigger_type_allowlist: Sequence[str] | str | None = None,
    include_to_tt_rate_hz: bool = False,
) -> list[str]:
    from_dict = _select_tt_rate_columns_for_prefix(
        dict_df,
        prefix_selector=prefix_selector,
        trigger_type_allowlist=trigger_type_allowlist,
        include_to_tt_rate_hz=include_to_tt_rate_hz,
    )
    from_data = _select_tt_rate_columns_for_prefix(
        data_df,
        prefix_selector=prefix_selector,
        trigger_type_allowlist=trigger_type_allowlist,
        include_to_tt_rate_hz=include_to_tt_rate_hz,
    )
    return sorted(set(from_dict) & set(from_data))


def _append_derived_tt_global_rate_column(
    dict_df: pd.DataFrame,
    data_df: pd.DataFrame,
    *,
    prefix_selector: str = "last",
    trigger_type_allowlist: Sequence[str] | str | None = None,
    include_to_tt_rate_hz: bool = False,
    output_column: str = DERIVED_TT_GLOBAL_RATE_COL,
) -> tuple[pd.DataFrame, pd.DataFrame, str | None, list[str]]:
    """
    Build a derived global-rate feature from trigger-type sums.

    The derived column is added only when a common TT column set exists
    in dictionary and dataset.
    """
    common_tt = _common_tt_rate_columns(
        dict_df,
        data_df,
        prefix_selector=prefix_selector,
        trigger_type_allowlist=trigger_type_allowlist,
        include_to_tt_rate_hz=include_to_tt_rate_hz,
    )
    if not common_tt:
        return dict_df, data_df, None, []

    dict_out = dict_df.copy()
    data_out = data_df.copy()
    dict_out[output_column] = dict_out[common_tt].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)
    data_out[output_column] = data_out[common_tt].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)
    return dict_out, data_out, output_column, common_tt


def _rate_histogram_columns(df: pd.DataFrame) -> list[str]:
    cols: list[tuple[int, str]] = []
    for col in df.columns:
        text = str(col).strip()
        match = RATE_HISTOGRAM_BIN_RE.match(text)
        if match is None:
            continue
        cols.append((int(match.group("bin")), text))
    cols.sort(key=lambda x: x[0])
    return [name for _, name in cols]


def _normalize_derived_physics_features(value: Sequence[str] | str | bool | None) -> list[str]:
    if isinstance(value, bool):
        return ["log_rate_over_eff_product"] if value else []
    raw = parse_explicit_feature_columns(value)
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        key = str(item).strip().lower()
        if not key:
            continue
        normalized = _DERIVED_PHYSICS_FEATURE_ALIASES.get(key)
        if normalized is None or normalized in seen:
            continue
        out.append(normalized)
        seen.add(normalized)
    return out


def _append_derived_physics_feature_columns(
    dict_df: pd.DataFrame,
    data_df: pd.DataFrame,
    *,
    rate_column: str,
    physics_features: Sequence[str] | str | bool | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    selected = _normalize_derived_physics_features(physics_features)
    if not selected:
        return dict_df, data_df, []
    if rate_column not in dict_df.columns or rate_column not in data_df.columns:
        return dict_df, data_df, []

    eff_cols = [c for c in DERIVED_EFFICIENCY_COLUMNS if c in dict_df.columns and c in data_df.columns]
    if not eff_cols:
        return dict_df, data_df, []

    dict_out = dict_df.copy()
    data_out = data_df.copy()

    dict_eff = dict_out[eff_cols].apply(pd.to_numeric, errors="coerce")
    data_eff = data_out[eff_cols].apply(pd.to_numeric, errors="coerce")
    min_count = len(eff_cols)
    dict_eff_prod = dict_eff.prod(axis=1, min_count=min_count)
    data_eff_prod = data_eff.prod(axis=1, min_count=min_count)

    def _sum_eff_products(eff_frame: pd.DataFrame, order: int) -> pd.Series:
        arr = eff_frame.to_numpy(dtype=float)
        n_rows, n_eff = arr.shape
        out = np.full(n_rows, np.nan, dtype=float)
        if n_eff < order:
            return pd.Series(out, index=eff_frame.index)
        finite_all = np.isfinite(arr).all(axis=1)
        if not np.any(finite_all):
            return pd.Series(out, index=eff_frame.index)
        total = np.zeros(n_rows, dtype=float)
        for idxs in combinations(range(n_eff), order):
            term = np.ones(n_rows, dtype=float)
            for idx in idxs:
                term *= arr[:, idx]
            total += term
        out[finite_all] = total[finite_all]
        return pd.Series(out, index=eff_frame.index)

    added: list[str] = []
    if "eff_product" in selected:
        dict_out[DERIVED_EFF_PRODUCT_COL] = dict_eff_prod
        data_out[DERIVED_EFF_PRODUCT_COL] = data_eff_prod
        added.append(DERIVED_EFF_PRODUCT_COL)

    if "eff_coincidence_moments" in selected:
        dict_pair_sum = _sum_eff_products(dict_eff, order=2)
        data_pair_sum = _sum_eff_products(data_eff, order=2)
        dict_triplet_sum = _sum_eff_products(dict_eff, order=3)
        data_triplet_sum = _sum_eff_products(data_eff, order=3)

        dict_out[DERIVED_LOG_EFF_PAIR_SUM_COL] = np.log(
            np.where(dict_pair_sum > 1e-12, dict_pair_sum, np.nan)
        )
        data_out[DERIVED_LOG_EFF_PAIR_SUM_COL] = np.log(
            np.where(data_pair_sum > 1e-12, data_pair_sum, np.nan)
        )
        dict_out[DERIVED_LOG_EFF_TRIPLET_SUM_COL] = np.log(
            np.where(dict_triplet_sum > 1e-12, dict_triplet_sum, np.nan)
        )
        data_out[DERIVED_LOG_EFF_TRIPLET_SUM_COL] = np.log(
            np.where(data_triplet_sum > 1e-12, data_triplet_sum, np.nan)
        )
        added.extend([DERIVED_LOG_EFF_PAIR_SUM_COL, DERIVED_LOG_EFF_TRIPLET_SUM_COL])

    if "log_rate_over_eff_product" in selected:
        dict_rate = pd.to_numeric(dict_out[rate_column], errors="coerce")
        data_rate = pd.to_numeric(data_out[rate_column], errors="coerce")

        dict_den = dict_eff_prod.where(dict_eff_prod > 1e-8, np.nan)
        data_den = data_eff_prod.where(data_eff_prod > 1e-8, np.nan)

        dict_ratio = (dict_rate / dict_den).where(dict_rate > 0.0, np.nan)
        data_ratio = (data_rate / data_den).where(data_rate > 0.0, np.nan)

        dict_out[DERIVED_LOG_RATE_OVER_EFF_PRODUCT_COL] = np.log(
            np.where(np.isfinite(dict_ratio), dict_ratio, np.nan)
        )
        data_out[DERIVED_LOG_RATE_OVER_EFF_PRODUCT_COL] = np.log(
            np.where(np.isfinite(data_ratio), data_ratio, np.nan)
        )
        added.append(DERIVED_LOG_RATE_OVER_EFF_PRODUCT_COL)

    return dict_out, data_out, added


def _derived_feature_columns(
    df: pd.DataFrame,
    *,
    rate_column: str = DERIVED_TT_GLOBAL_RATE_COL,
    trigger_type_rate_columns: Sequence[str] | None = None,
    include_rate_histogram: bool = False,
    physics_feature_columns: Sequence[str] | None = None,
) -> list[str]:
    """Select derived features: empirical efficiencies + global-rate proxy.

    The preferred global-rate proxy is the derived TT trigger sum.
    `events_per_second_global_rate` remains supported as a fallback.
    """
    cols: list[str] = []
    for c in DERIVED_EFFICIENCY_COLUMNS:
        if c in df.columns:
            cols.append(c)
    if rate_column in df.columns:
        cols.append(rate_column)
    elif rate_column != DERIVED_RATE_COLUMN and DERIVED_RATE_COLUMN in df.columns:
        cols.append(DERIVED_RATE_COLUMN)
    if trigger_type_rate_columns:
        seen = set(cols)
        for c in trigger_type_rate_columns:
            name = str(c).strip()
            if not name or name in seen:
                continue
            if name in df.columns:
                cols.append(name)
                seen.add(name)
    if include_rate_histogram:
        cols.extend(_rate_histogram_columns(df))
    if physics_feature_columns:
        for c in physics_feature_columns:
            name = str(c).strip()
            if name and name in df.columns:
                cols.append(name)
    return cols


def _append_tt_global_sum_feature(
    dict_features: pd.DataFrame,
    data_features: pd.DataFrame,
    feature_cols: Sequence[str],
    include_global_rate: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], str | None, list[str]]:
    """
    Optionally append a derived global-rate-like feature as the sum of
    selected multi-plane TT rate columns.

    This intentionally does not rely on a literal `global_rate_col`.
    """
    out_cols = [str(c) for c in feature_cols]
    if not include_global_rate:
        return dict_features, data_features, out_cols, None, []

    tt_cols: list[str] = []
    for col in out_cols:
        match = TT_RATE_COLUMN_RE.match(str(col))
        if match is None:
            continue
        if not _is_multi_plane_tt_label(match.group("label")):
            continue
        tt_cols.append(str(col))

    if not tt_cols:
        return dict_features, data_features, out_cols, None, []

    alias = DERIVED_TT_GLOBAL_RATE_COL
    idx = 2
    while alias in dict_features.columns or alias in data_features.columns or alias in out_cols:
        alias = f"{DERIVED_TT_GLOBAL_RATE_COL}_{idx}"
        idx += 1

    dict_out = dict_features.copy()
    data_out = data_features.copy()
    dict_out[alias] = dict_out[tt_cols].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)
    data_out[alias] = data_out[tt_cols].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)
    out_cols.append(alias)
    return dict_out, data_out, out_cols, alias, tt_cols


def _mask_out_of_support_efficiency_features(
    *,
    dict_features: pd.DataFrame,
    data_features: pd.DataFrame,
    feature_cols: Sequence[str],
    non_hist_feature_idx: Sequence[int],
    base_eff_feature_idx: np.ndarray,
    enabled: bool,
) -> tuple[pd.DataFrame, np.ndarray | None, dict]:
    """
    Mask empirical-efficiency feature values outside dictionary support.

    For inverse mapping, distances are only meaningful inside the dictionary
    feature support. Per-row masking avoids forcing boundary matches when real
    data falls outside support in some efficiency planes.
    """
    info: dict = {
        "enabled": bool(enabled),
        "n_eff_features_considered": int(base_eff_feature_idx.size),
        "n_rows_any_masked": 0,
        "fraction_rows_any_masked": 0.0,
        "mean_masked_eff_features_per_row": 0.0,
        "per_feature": {},
    }
    if not enabled or base_eff_feature_idx.size == 0:
        return data_features, None, info

    data_out = data_features.copy()
    n_data = len(data_out)
    if n_data == 0:
        return data_out, np.zeros((0, len(non_hist_feature_idx)), dtype=bool), info

    masked_non_hist = np.zeros((n_data, len(non_hist_feature_idx)), dtype=bool)
    for j_non_hist in base_eff_feature_idx:
        if j_non_hist < 0 or j_non_hist >= len(non_hist_feature_idx):
            continue
        full_idx = int(non_hist_feature_idx[int(j_non_hist)])
        if full_idx < 0 or full_idx >= len(feature_cols):
            continue
        col = str(feature_cols[full_idx])

        dvals = pd.to_numeric(dict_features[col], errors="coerce")
        finite_d = np.isfinite(dvals.to_numpy(dtype=float))
        if not np.any(finite_d):
            info["per_feature"][col] = {
                "dict_min": None,
                "dict_max": None,
                "rows_masked": 0,
                "fraction_rows_masked": 0.0,
                "reason": "no_finite_dictionary_values",
            }
            continue

        dict_min = float(np.nanmin(dvals.to_numpy(dtype=float)))
        dict_max = float(np.nanmax(dvals.to_numpy(dtype=float)))
        tol = max(1e-12, 1e-12 * max(1.0, abs(dict_min), abs(dict_max)))
        x = pd.to_numeric(data_out[col], errors="coerce")
        outside = x.notna() & ((x < (dict_min - tol)) | (x > (dict_max + tol)))
        n_mask = int(outside.sum())
        if n_mask > 0:
            data_out.loc[outside, col] = np.nan
            masked_non_hist[outside.to_numpy(dtype=bool), int(j_non_hist)] = True

        info["per_feature"][col] = {
            "dict_min": dict_min,
            "dict_max": dict_max,
            "rows_masked": n_mask,
            "fraction_rows_masked": float(n_mask / n_data),
        }

    if masked_non_hist.size:
        row_counts = np.sum(masked_non_hist, axis=1)
        rows_any = row_counts > 0
        info["n_rows_any_masked"] = int(np.sum(rows_any))
        info["fraction_rows_any_masked"] = float(np.mean(rows_any))
        info["mean_masked_eff_features_per_row"] = float(np.mean(row_counts))

    return data_out, masked_non_hist, info


# =====================================================================
# Density-aware interpolation helpers
# =====================================================================

_DENSITY_CFG_DEFAULTS = {
    "density_correction_enabled": True,
    "density_correction_k_neighbors": 10,
}
_DENSITY_CORRECTION_EXPONENT = 1.0
_DENSITY_CORRECTION_CLIP_MIN = 0.25
_DENSITY_CORRECTION_CLIP_MAX = 4.0

_INVERSE_MAPPING_DEFAULTS = {
    "estimation_mode": "single_stage",
    "neighbor_selection": "knn",
    "neighbor_count": 5,
    "weighting": "inverse_distance",
    "inverse_distance_power": 2.0,
    "softmax_temperature": 1.0,
    "distance_floor": 1e-12,
    "aggregation": "weighted_mean",
    "local_linear_ridge_lambda": 1e-2,
    "stage2_efficiency_conditioning_weight": 1.0,
    "stage2_efficiency_gate_max": 0.20,
    "stage2_efficiency_gate_min_candidates": 24,
    "stage2_use_rate_histogram": True,
    "stage2_histogram_distance_weight": 1.0,
    "histogram_distance_weight": 1.0,
    "histogram_distance_blend_mode": "normalized",
    # When real-data empirical efficiencies lie outside dictionary support,
    # distance in those dimensions is not meaningful. Mask them per-row.
    "mask_out_of_support_eff_features": False,
    "efficiency_vector_distance": {
        "enabled": False,
        "weight": 1.0,
        "blend_mode": "normalized",
        "stage2_enabled": True,
        "stage2_weight": 1.0,
        "uncertainty_floor": 0.02,
        "min_valid_bins_per_vector": 3,
        "fiducial": {
            "x_abs_max_mm": None,
            "y_abs_max_mm": None,
            "theta_max_deg": None,
        },
    },
}


def _safe_float(value: object, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float(default)
    if np.isfinite(out):
        return out
    return float(default)


def _safe_optional_float(value: object) -> float | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if np.isfinite(out):
        return float(out)
    return None


def _safe_int(value: object, default: int, minimum: int | None = None) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        out = int(default)
    if minimum is not None:
        out = max(int(minimum), out)
    return out


def _safe_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _safe_str(value: object, default: str) -> str:
    if value is None:
        return str(default)
    text = str(value).strip()
    return text if text else str(default)


def _normalize_column_spec(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        return [x.strip() for x in text.split(",") if x.strip()]
    if isinstance(value, Sequence):
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    text = str(value).strip()
    return [text] if text else []


def _normalize_neighbor_selection(value: object) -> str:
    text = str(value).strip().lower() if value is not None else ""
    if text in {"nearest", "nn", "1nn", "single"}:
        return "nearest"
    if text in {"all", "full", "global"}:
        return "all"
    if text in {"knn", "k", "k_nearest", "k-nearest"}:
        return "knn"
    return "knn"


def _normalize_weighting_mode(value: object) -> str:
    text = str(value).strip().lower() if value is not None else ""
    if text in {"uniform", "flat", "mean"}:
        return "uniform"
    if text in {"softmax", "exp", "exponential"}:
        return "softmax"
    if text in {"inverse_distance", "idw", "inverse", "invdist"}:
        return "inverse_distance"
    return "inverse_distance"


def _normalize_aggregation_mode(value: object) -> str:
    text = str(value).strip().lower() if value is not None else ""
    if text in {"weighted_median", "median"}:
        return "weighted_median"
    if text in {"local_linear", "local_linear_ridge", "llr"}:
        return "local_linear"
    return "weighted_mean"


def _normalize_hist_blend_mode(value: object) -> str:
    text = str(value).strip().lower() if value is not None else ""
    if text in {"raw", "add_raw", "legacy"}:
        return "raw"
    return "normalized"


def _normalize_estimation_mode(value: object) -> str:
    text = str(value).strip().lower() if value is not None else ""
    if text in {
        "two_stage_eff_address_then_flux",
        "two_stage_address",
        "two_stage_address_then_flux",
        "eff_address_then_flux",
        "2stage_address",
    }:
        return "two_stage_eff_address_then_flux"
    if text in {"two_stage", "two_stage_eff_then_flux", "eff_then_flux", "2stage"}:
        return "two_stage_eff_then_flux"
    return "single_stage"


def _legacy_neighbor_selection_from_interpolation_k(
    interpolation_k: int | None,
) -> tuple[str, int | None]:
    if interpolation_k is None:
        return ("all", None)
    k = max(1, int(interpolation_k))
    if k <= 1:
        return ("nearest", 1)
    return ("knn", k)


def resolve_inverse_mapping_cfg(
    *,
    inverse_mapping_cfg: Mapping[str, object] | None,
    interpolation_k: int | None = 5,
    histogram_distance_weight: float = 1.0,
    histogram_distance_blend_mode: str = "normalized",
) -> dict:
    """
    Resolve inverse-mapping behavior into a normalized configuration dict.

    Keeps backward compatibility with `interpolation_k` and legacy histogram
    distance arguments while allowing explicit control in `inverse_mapping_cfg`.
    """
    legacy_neighbor_selection, legacy_neighbor_count = _legacy_neighbor_selection_from_interpolation_k(
        interpolation_k
    )
    cfg = dict(_INVERSE_MAPPING_DEFAULTS)
    cfg["neighbor_selection"] = legacy_neighbor_selection
    cfg["neighbor_count"] = legacy_neighbor_count
    cfg["histogram_distance_weight"] = max(float(histogram_distance_weight), 0.0)
    cfg["histogram_distance_blend_mode"] = _normalize_hist_blend_mode(histogram_distance_blend_mode)
    cfg["efficiency_vector_distance"] = dict(_INVERSE_MAPPING_DEFAULTS["efficiency_vector_distance"])
    cfg["efficiency_vector_distance"]["fiducial"] = dict(
        _INVERSE_MAPPING_DEFAULTS["efficiency_vector_distance"]["fiducial"]
    )

    if isinstance(inverse_mapping_cfg, Mapping):
        for key in (
            "estimation_mode",
            "neighbor_selection",
            "neighbor_count",
            "weighting",
            "inverse_distance_power",
            "softmax_temperature",
            "distance_floor",
            "aggregation",
            "local_linear_ridge_lambda",
            "stage2_efficiency_conditioning_weight",
            "stage2_efficiency_gate_max",
            "stage2_efficiency_gate_min_candidates",
            "stage2_use_rate_histogram",
            "stage2_histogram_distance_weight",
            "histogram_distance_weight",
            "histogram_distance_blend_mode",
            "mask_out_of_support_eff_features",
        ):
            if key in inverse_mapping_cfg and inverse_mapping_cfg.get(key) is not None:
                cfg[key] = inverse_mapping_cfg.get(key)
        effvec_cfg_raw = inverse_mapping_cfg.get("efficiency_vector_distance")
        if isinstance(effvec_cfg_raw, Mapping):
            merged_effvec = dict(_INVERSE_MAPPING_DEFAULTS["efficiency_vector_distance"])
            merged_effvec["fiducial"] = dict(
                _INVERSE_MAPPING_DEFAULTS["efficiency_vector_distance"]["fiducial"]
            )
            for key, value in effvec_cfg_raw.items():
                if key == "fiducial" and isinstance(value, Mapping):
                    merged_effvec["fiducial"].update(dict(value))
                else:
                    merged_effvec[key] = value
            cfg["efficiency_vector_distance"] = merged_effvec

    cfg["estimation_mode"] = _normalize_estimation_mode(cfg.get("estimation_mode"))
    cfg["neighbor_selection"] = _normalize_neighbor_selection(cfg.get("neighbor_selection"))
    if cfg["neighbor_selection"] == "nearest":
        cfg["neighbor_count"] = 1
    elif cfg["neighbor_selection"] == "all":
        cfg["neighbor_count"] = None
    else:
        if cfg.get("neighbor_count") is None:
            cfg["neighbor_count"] = max(
                1, int(legacy_neighbor_count if legacy_neighbor_count is not None else _INVERSE_MAPPING_DEFAULTS["neighbor_count"])
            )
        else:
            cfg["neighbor_count"] = max(1, _safe_int(cfg.get("neighbor_count"), int(_INVERSE_MAPPING_DEFAULTS["neighbor_count"]), minimum=1))

    cfg["weighting"] = _normalize_weighting_mode(cfg.get("weighting"))
    cfg["inverse_distance_power"] = max(
        _safe_float(cfg.get("inverse_distance_power"), float(_INVERSE_MAPPING_DEFAULTS["inverse_distance_power"])),
        0.0,
    )
    cfg["softmax_temperature"] = max(
        _safe_float(cfg.get("softmax_temperature"), float(_INVERSE_MAPPING_DEFAULTS["softmax_temperature"])),
        1e-12,
    )
    cfg["distance_floor"] = max(
        _safe_float(cfg.get("distance_floor"), float(_INVERSE_MAPPING_DEFAULTS["distance_floor"])),
        1e-15,
    )
    cfg["aggregation"] = _normalize_aggregation_mode(cfg.get("aggregation"))
    cfg["local_linear_ridge_lambda"] = max(
        _safe_float(
            cfg.get("local_linear_ridge_lambda"),
            float(_INVERSE_MAPPING_DEFAULTS["local_linear_ridge_lambda"]),
        ),
        0.0,
    )
    cfg["stage2_efficiency_conditioning_weight"] = max(
        _safe_float(
            cfg.get("stage2_efficiency_conditioning_weight"),
            float(_INVERSE_MAPPING_DEFAULTS["stage2_efficiency_conditioning_weight"]),
        ),
        0.0,
    )
    cfg["stage2_efficiency_gate_max"] = max(
        _safe_float(
            cfg.get("stage2_efficiency_gate_max"),
            float(_INVERSE_MAPPING_DEFAULTS["stage2_efficiency_gate_max"]),
        ),
        0.0,
    )
    cfg["stage2_efficiency_gate_min_candidates"] = max(
        1,
        _safe_int(
            cfg.get("stage2_efficiency_gate_min_candidates"),
            int(_INVERSE_MAPPING_DEFAULTS["stage2_efficiency_gate_min_candidates"]),
            minimum=1,
        ),
    )
    cfg["stage2_use_rate_histogram"] = _safe_bool(
        cfg.get("stage2_use_rate_histogram"),
        bool(_INVERSE_MAPPING_DEFAULTS["stage2_use_rate_histogram"]),
    )
    cfg["stage2_histogram_distance_weight"] = max(
        _safe_float(
            cfg.get("stage2_histogram_distance_weight"),
            float(_INVERSE_MAPPING_DEFAULTS["stage2_histogram_distance_weight"]),
        ),
        0.0,
    )
    cfg["histogram_distance_weight"] = max(
        _safe_float(cfg.get("histogram_distance_weight"), float(_INVERSE_MAPPING_DEFAULTS["histogram_distance_weight"])),
        0.0,
    )
    cfg["histogram_distance_blend_mode"] = _normalize_hist_blend_mode(
        cfg.get("histogram_distance_blend_mode")
    )
    cfg["mask_out_of_support_eff_features"] = _safe_bool(
        cfg.get("mask_out_of_support_eff_features"),
        bool(_INVERSE_MAPPING_DEFAULTS["mask_out_of_support_eff_features"]),
    )
    effvec_cfg = cfg.get("efficiency_vector_distance", {})
    if not isinstance(effvec_cfg, Mapping):
        effvec_cfg = {}
    effvec_defaults = _INVERSE_MAPPING_DEFAULTS["efficiency_vector_distance"]
    cfg["efficiency_vector_distance"] = {
        "enabled": _safe_bool(
            effvec_cfg.get("enabled"),
            bool(effvec_defaults["enabled"]),
        ),
        "weight": max(
            _safe_float(effvec_cfg.get("weight"), float(effvec_defaults["weight"])),
            0.0,
        ),
        "blend_mode": _normalize_hist_blend_mode(
            effvec_cfg.get("blend_mode", effvec_defaults["blend_mode"])
        ),
        "stage2_enabled": _safe_bool(
            effvec_cfg.get("stage2_enabled"),
            bool(effvec_defaults["stage2_enabled"]),
        ),
        "stage2_weight": max(
            _safe_float(
                effvec_cfg.get("stage2_weight"),
                float(effvec_defaults["stage2_weight"]),
            ),
            0.0,
        ),
        "uncertainty_floor": max(
            _safe_float(
                effvec_cfg.get("uncertainty_floor"),
                float(effvec_defaults["uncertainty_floor"]),
            ),
            0.0,
        ),
        "min_valid_bins_per_vector": max(
            1,
            _safe_int(
                effvec_cfg.get("min_valid_bins_per_vector"),
                int(effvec_defaults["min_valid_bins_per_vector"]),
                minimum=1,
            ),
        ),
        "fiducial": _normalize_efficiency_vector_fiducial(
            effvec_cfg.get("fiducial", effvec_defaults["fiducial"])
        ),
    }
    return cfg


def build_step15_runtime_inverse_mapping_cfg(
    *,
    inverse_mapping_cfg: Mapping[str, object] | None,
    interpolation_k: int | None = 5,
    distance_definition: Mapping[str, object] | None = None,
) -> dict:
    """
    Build the post-STEP-1.5 runtime inverse-mapping config.

    STEP 1.5 only tunes the feature-space distance definition, neighbor count,
    and local-linear ridge scale. Downstream runtime estimation should therefore
    stay on the simple STEP 2.1 path: single-stage kNN with inverse-distance
    weighting and local-linear aggregation when the tuned lambda indicates it.

    Rate histograms and efficiency-vector profiles are consumed downstream as
    first-class grouped feature-space terms via the STEP 1.5 distance artifact.
    The legacy stage-2-only knobs are therefore disabled in the runtime config
    returned here to avoid reintroducing a different hierarchy after tuning.
    """
    requested = resolve_inverse_mapping_cfg(
        inverse_mapping_cfg=inverse_mapping_cfg,
        interpolation_k=interpolation_k,
    )

    neighbor_count = requested.get("neighbor_count")
    if isinstance(distance_definition, Mapping) and bool(distance_definition.get("available")):
        if distance_definition.get("optimal_k") is not None:
            neighbor_count = max(1, int(distance_definition["optimal_k"]))
        optimal_lambda = _safe_float(distance_definition.get("optimal_lambda"), 1e6)
    else:
        optimal_lambda = 1e6

    if neighbor_count is None:
        if interpolation_k is not None:
            neighbor_count = max(1, int(interpolation_k))
        else:
            neighbor_count = int(_INVERSE_MAPPING_DEFAULTS["neighbor_count"])

    selected_aggregation = None
    if isinstance(distance_definition, Mapping) and distance_definition.get("optimal_aggregation") is not None:
        selected_aggregation = _normalize_aggregation_mode(distance_definition.get("optimal_aggregation"))
    aggregation = (
        selected_aggregation
        if selected_aggregation is not None
        else ("local_linear" if optimal_lambda < 1e5 else "weighted_mean")
    )
    runtime_cfg = dict(requested)
    runtime_cfg.update(
        {
            "estimation_mode": "single_stage",
            "neighbor_selection": "knn",
            "neighbor_count": int(neighbor_count),
            "weighting": "inverse_distance",
            "inverse_distance_power": max(
                _safe_float(
                    requested.get("inverse_distance_power"),
                    float(_INVERSE_MAPPING_DEFAULTS["inverse_distance_power"]),
                ),
                0.0,
            ),
            "aggregation": aggregation,
            "local_linear_ridge_lambda": (
                max(float(optimal_lambda), 0.0)
                if aggregation == "local_linear"
                else max(
                    _safe_float(
                        requested.get("local_linear_ridge_lambda"),
                        float(_INVERSE_MAPPING_DEFAULTS["local_linear_ridge_lambda"]),
                    ),
                    0.0,
                )
            ),
        }
    )
    runtime_cfg["stage2_use_rate_histogram"] = False
    runtime_cfg["stage2_histogram_distance_weight"] = 0.0
    effvec_runtime_cfg = runtime_cfg.get("efficiency_vector_distance", {})
    if not isinstance(effvec_runtime_cfg, Mapping):
        effvec_runtime_cfg = {}
    effvec_runtime = dict(effvec_runtime_cfg)
    effvec_runtime["stage2_enabled"] = False
    effvec_runtime["stage2_weight"] = 0.0
    runtime_cfg["efficiency_vector_distance"] = effvec_runtime
    return runtime_cfg


def _resolve_shared_parameter_exclusion_mode(
    mode_value: object | None,
    legacy_flag: bool = False,
) -> str:
    """
    Normalize shared-parameter exclusion mode.

    Returns one of: "off", "full", "partial".
    """
    if mode_value is None:
        mode_value = legacy_flag

    if isinstance(mode_value, bool):
        return "partial" if mode_value else "off"

    text = str(mode_value).strip().lower()
    if text in {"", "off", "none", "false", "0", "no", "n"}:
        return "off"
    if text in {"full", "all", "exact"}:
        return "full"
    if text in {"partial", "any", "true", "1", "yes", "y", "on"}:
        return "partial"
    # Safe fallback keeps exclusion active when user provides an unknown
    # truthy-like value.
    return "partial"


def _default_parameter_columns_for_exclusion(df: pd.DataFrame) -> list[str]:
    cols: list[str] = []
    for c in [
        "flux_cm2_min",
        "cos_n",
        "eff_sim_1",
        "eff_sim_2",
        "eff_sim_3",
        "eff_sim_4",
        "eff_empirical_1",
        "eff_empirical_2",
        "eff_empirical_3",
        "eff_empirical_4",
    ]:
        if c in df.columns:
            cols.append(c)
    return cols


def build_shared_parameter_exclusion_mask(
    *,
    dict_df: pd.DataFrame,
    sample_row: pd.Series,
    initial_mask: np.ndarray | None = None,
    param_columns: Sequence[str] | None = None,
    shared_parameter_exclusion_mode: str | None = None,
    shared_parameter_exclusion_columns: Sequence[str] | str | None = None,
    shared_parameter_exclusion_ignore: Sequence[str] | str | None = ("cos_n",),
    shared_parameter_match_atol: float = 1e-12,
) -> tuple[np.ndarray, dict]:
    """
    Apply STEP 2 shared-parameter exclusion logic for one sample row.

    Returns:
      keep_mask (np.ndarray[bool]),
      info dict with counts/columns/mode.
    """
    n_rows = len(dict_df)
    if initial_mask is None:
        keep_mask = np.ones(n_rows, dtype=bool)
    else:
        keep_mask = np.asarray(initial_mask, dtype=bool).copy()
        if keep_mask.shape[0] != n_rows:
            keep_mask = np.ones(n_rows, dtype=bool)

    mode = _resolve_shared_parameter_exclusion_mode(shared_parameter_exclusion_mode, legacy_flag=False)
    info = {
        "mode": mode,
        "enabled": mode in {"partial", "full"},
        "columns": [],
        "n_before": int(np.sum(keep_mask)),
        "n_removed": 0,
        "reason": "disabled",
    }
    if not info["enabled"] or info["n_before"] <= 0:
        return keep_mask, info

    candidate_param_cols = list(param_columns) if param_columns is not None else _default_parameter_columns_for_exclusion(dict_df)
    raw_cols = _normalize_column_spec(shared_parameter_exclusion_columns)
    if not raw_cols or any(str(c).strip().lower() == "auto" for c in raw_cols):
        raw_cols = [str(c) for c in candidate_param_cols if not str(c).startswith("eff_empirical_")]

    ignore_cols = set(_normalize_column_spec(shared_parameter_exclusion_ignore))
    shared_cols: list[str] = []
    seen_cols: set[str] = set()
    for col in raw_cols:
        name = str(col).strip()
        if not name or name in seen_cols or name in ignore_cols:
            continue
        if name not in dict_df.columns or name not in sample_row.index:
            continue
        shared_cols.append(name)
        seen_cols.add(name)
    info["columns"] = shared_cols

    shared_match_atol = max(float(shared_parameter_match_atol), 0.0)
    remove_any = np.zeros(n_rows, dtype=bool)
    remove_full = np.ones(n_rows, dtype=bool)
    n_compared_cols = 0

    for col in shared_cols:
        sample_val = float(pd.to_numeric(pd.Series([sample_row.get(col)]), errors="coerce").iloc[0])
        if not np.isfinite(sample_val):
            continue
        n_compared_cols += 1
        dict_vals = pd.to_numeric(dict_df[col], errors="coerce").to_numpy(dtype=float)
        atol_eff = _effective_atol(shared_match_atol, sample_val)
        same_mask = np.isfinite(dict_vals) & np.isclose(
            dict_vals,
            sample_val,
            rtol=0.0,
            atol=atol_eff,
        )
        if np.any(same_mask):
            remove_any |= same_mask
        remove_full &= same_mask

    if mode == "full":
        remove_basis = remove_full if n_compared_cols > 0 else np.zeros(n_rows, dtype=bool)
    else:
        remove_basis = remove_any

    if (
        "param_set_id" in dict_df.columns
        and "param_set_id" in sample_row.index
        and "param_set_id" not in ignore_cols
    ):
        dict_param_set = pd.to_numeric(dict_df["param_set_id"], errors="coerce").to_numpy(dtype=float)
        sample_param_set = float(pd.to_numeric(pd.Series([sample_row.get("param_set_id")]), errors="coerce").iloc[0])
        if np.isfinite(sample_param_set):
            atol_eff = _effective_atol(shared_match_atol, sample_param_set)
            same_param_set = np.isfinite(dict_param_set) & np.isclose(
                dict_param_set,
                sample_param_set,
                rtol=0.0,
                atol=atol_eff,
            )
            if np.any(same_param_set):
                remove_basis |= same_param_set

    remove_in_candidates = keep_mask & remove_basis
    n_removed = int(np.sum(remove_in_candidates))
    if n_removed > 0:
        keep_mask[remove_in_candidates] = False
        info["reason"] = "removed"
    else:
        info["reason"] = "no_matches"
    info["n_removed"] = n_removed
    info["n_after"] = int(np.sum(keep_mask))
    return keep_mask, info


def _resolve_density_cfg(
    density_weighting_cfg: Mapping[str, object] | None,
) -> dict:
    if not isinstance(density_weighting_cfg, Mapping):
        return {
            **_DENSITY_CFG_DEFAULTS,
            "density_correction_enabled": False,
            "_reason": "not_configured",
        }

    merged = dict(_DENSITY_CFG_DEFAULTS)
    for key in _DENSITY_CFG_DEFAULTS:
        if key in density_weighting_cfg and density_weighting_cfg.get(key) is not None:
            merged[key] = density_weighting_cfg.get(key)
    for legacy_key in (
        "flux_column",
        "eff_column",
        "density_correction_space",
        "density_correction_exponent",
        "density_correction_clip_min",
        "density_correction_clip_max",
    ):
        if density_weighting_cfg.get(legacy_key) is not None:
            log.warning(
                "Deprecated density config key '%s' detected; ignored. "
                "Feature-space density correction now uses fixed exponent/clip constants.",
                legacy_key,
            )

    merged["density_correction_enabled"] = _safe_bool(
        merged.get("density_correction_enabled"), True
    )
    merged["density_correction_k_neighbors"] = _safe_int(
        merged.get("density_correction_k_neighbors"), 10, minimum=1
    )
    return merged


def _scale_from_local_radius(
    local_radius: np.ndarray,
    *,
    exponent: float,
    clip_min: float,
    clip_max: float,
) -> tuple[np.ndarray, dict]:
    rr = np.asarray(local_radius, dtype=float)
    n = len(rr)
    scale = np.ones(n, dtype=float)
    info = {"n_basis": int(n), "n_finite_radius": int(np.isfinite(rr).sum())}
    finite = np.isfinite(rr)
    if not np.any(finite):
        info["reason"] = "no_finite_radius"
        return scale, info

    exp = max(float(exponent), 0.0)
    rr_f = np.clip(rr[finite], 1e-12, None)
    scale_f = np.power(rr_f, exp)
    med = float(np.median(scale_f[np.isfinite(scale_f)])) if np.isfinite(scale_f).any() else 1.0
    if med <= 0.0 or not np.isfinite(med):
        med = 1.0
    scale_f = scale_f / med

    lo = max(float(clip_min), 1e-6)
    hi = max(float(clip_max), lo)
    scale_f = np.clip(scale_f, lo, hi)
    scale[finite] = scale_f

    info["scale_min"] = float(np.min(scale_f))
    info["scale_median"] = float(np.median(scale_f))
    info["scale_max"] = float(np.max(scale_f))
    return scale, info


def _z_signature_key(row: np.ndarray) -> tuple[object, ...]:
    vals = np.asarray(row, dtype=float).tolist()
    key: list[object] = []
    for val in vals:
        v = float(val)
        if np.isnan(v):
            key.append(("nan",))
        elif np.isposinf(v):
            key.append(("inf",))
        elif np.isneginf(v):
            key.append(("-inf",))
        else:
            key.append(round(v, 12))
    return tuple(key)


def _group_indices_by_z_signature(
    dict_z: np.ndarray | None,
    n_rows: int,
) -> list[np.ndarray]:
    if n_rows <= 0:
        return []
    if dict_z is None or len(dict_z) != n_rows:
        return [np.arange(n_rows, dtype=int)]

    groups: dict[tuple[object, ...], list[int]] = {}
    for idx in range(n_rows):
        key = _z_signature_key(dict_z[idx])
        groups.setdefault(key, []).append(idx)

    out = [np.asarray(v, dtype=int) for v in groups.values() if len(v) > 0]
    out.sort(key=lambda arr: int(arr[0]))
    return out


def _compute_inverse_density_scaling_feature_space(
    dict_feature_matrix: np.ndarray,
    *,
    distance_metric: str,
    z_groups: list[np.ndarray],
    k_neighbors: int,
    exponent: float,
    clip_min: float,
    clip_max: float,
) -> tuple[np.ndarray, dict]:
    X = np.asarray(dict_feature_matrix, dtype=float)
    n = len(X)
    info = {
        "enabled": True,
        "space": "feature",
        "distance_metric": str(distance_metric),
        "k_neighbors": int(k_neighbors),
        "exponent": float(exponent),
        "clip_min": float(clip_min),
        "clip_max": float(clip_max),
        "n_basis": int(n),
        "n_z_groups": int(len(z_groups)),
    }
    if n == 0:
        return np.array([], dtype=float), info
    if n == 1:
        return np.ones(1, dtype=float), info

    dist_many_fn = DISTANCE_FNS_MANY.get(distance_metric, None)
    dist_fn = DISTANCE_FNS.get(distance_metric, _l2)
    local_radius = np.full(n, np.nan, dtype=float)
    eff_k_values: list[int] = []
    groups_with_neighbors = 0

    for grp in z_groups:
        if len(grp) <= 1:
            continue

        groups_with_neighbors += 1
        k_eff = min(max(1, int(k_neighbors)), len(grp) - 1)
        eff_k_values.append(int(k_eff))
        Xg = X[grp]

        for local_i, global_i in enumerate(grp):
            if dist_many_fn is not None:
                d = np.asarray(dist_many_fn(Xg[local_i], Xg), dtype=float)
            else:
                d = np.asarray([dist_fn(Xg[local_i], Xg[j]) for j in range(len(grp))], dtype=float)

            if d.shape[0] != len(grp):
                continue

            d[local_i] = np.nan
            finite = np.isfinite(d)
            if not np.any(finite):
                continue
            vals = np.clip(d[finite], 0.0, None)
            if vals.size >= k_eff:
                local_radius[global_i] = float(np.partition(vals, k_eff - 1)[k_eff - 1])
            else:
                local_radius[global_i] = float(np.max(vals))

    scale, scale_info = _scale_from_local_radius(
        local_radius,
        exponent=float(exponent),
        clip_min=float(clip_min),
        clip_max=float(clip_max),
    )
    info.update(scale_info)
    info["n_groups_with_neighbors"] = int(groups_with_neighbors)
    if eff_k_values:
        info["effective_k_neighbors_min"] = int(np.min(eff_k_values))
        info["effective_k_neighbors_max"] = int(np.max(eff_k_values))
    finite_radius = np.isfinite(local_radius)
    if np.any(finite_radius):
        info["radius_min"] = float(np.min(local_radius[finite_radius]))
        info["radius_median"] = float(np.median(local_radius[finite_radius]))
        info["radius_max"] = float(np.max(local_radius[finite_radius]))
    return scale, info


def _build_density_scaling_for_dictionary(
    *,
    dict_df: pd.DataFrame,
    dict_feature_matrix: np.ndarray,
    distance_metric: str,
    dict_z: np.ndarray | None,
    density_weighting_cfg: Mapping[str, object] | None,
) -> tuple[np.ndarray | None, dict]:
    cfg = _resolve_density_cfg(density_weighting_cfg)
    if not cfg.get("density_correction_enabled", False):
        return None, {"enabled": False, "reason": str(cfg.get("_reason", "disabled"))}

    X = np.asarray(dict_feature_matrix, dtype=float)
    if X.ndim != 2 or X.shape[0] != len(dict_df):
        return None, {
            "enabled": False,
            "space": "feature",
            "reason": "invalid_feature_matrix",
            "n_rows": int(len(dict_df)),
            "matrix_shape": tuple(X.shape),
        }

    z_groups = _group_indices_by_z_signature(dict_z, len(dict_df))
    scaling, info = _compute_inverse_density_scaling_feature_space(
        dict_feature_matrix=X,
        distance_metric=distance_metric,
        z_groups=z_groups,
        k_neighbors=int(cfg["density_correction_k_neighbors"]),
        exponent=float(_DENSITY_CORRECTION_EXPONENT),
        clip_min=float(_DENSITY_CORRECTION_CLIP_MIN),
        clip_max=float(_DENSITY_CORRECTION_CLIP_MAX),
    )
    if info.get("n_finite_radius", 0) <= 0:
        return None, {
            "enabled": False,
            "space": "feature",
            "reason": "insufficient_valid_points",
            "n_basis": int(info.get("n_basis", len(dict_df))),
        }
    return scaling, info


# =====================================================================
# Main estimation function
# =====================================================================

def estimate_parameters(
    dictionary_path: str | Path,
    dataset_path: str | Path,
    *,
    feature_columns: str | list[str] = "auto",
    distance_metric: str = "l2_zscore",
    interpolation_k: int | None = 5,
    z_tol: float = 1e-6,
    include_global_rate: bool = True,
    global_rate_col: str = "events_per_second_global_rate",
    param_columns: list[str] | None = None,
    exclude_same_file: bool = True,
    exclude_candidates_sharing_parameter_values: bool = False,
    shared_parameter_exclusion_mode: str | None = None,
    shared_parameter_exclusion_columns: Sequence[str] | str | None = None,
    shared_parameter_exclusion_ignore: Sequence[str] | str | None = ("cos_n",),
    shared_parameter_match_atol: float = 1e-12,
    density_weighting_cfg: Mapping[str, object] | None = None,
    inverse_mapping_cfg: Mapping[str, object] | None = None,
    derived_tt_prefix: str = "last",
    derived_trigger_types: Sequence[str] | str | None = None,
    derived_include_to_tt_rate_hz: bool = False,
    derived_include_trigger_type_rates: bool = False,
    derived_include_rate_histogram: bool = False,
    derived_physics_features: Sequence[str] | str | bool | None = None,
    histogram_distance_weight: float = 1.0,
    histogram_distance_blend_mode: str = "normalized",
) -> pd.DataFrame:
    """Estimate physical parameters for each dataset entry using dictionary matching.

    Parameters
    ----------
    dictionary_path : path
        CSV with dictionary entries (must have z_plane_1..4, feature columns,
        and parameter columns like flux_cm2_min, cos_n, etc.).
    dataset_path : path
        CSV with dataset entries to estimate parameters for.
    feature_columns : "auto" or list of str
        Columns used to build the fingerprint vector. If "auto", uses
        the most advanced available *_tt_*_rate_hz prefix and only
        multi-plane topologies (2-, 3-, and 4-plane combinations).
    distance_metric : str
        One of "l2_zscore", "l2_raw", "chi2", "poisson".
    interpolation_k : int or None
        Number of nearest neighbouring dictionary entries for IDW
        interpolation (1 = nearest-only). If None, use all valid
        candidates.
    z_tol : float
        Tolerance for z-plane position matching.
    include_global_rate : bool
        If True, append a derived global-rate-like feature computed as
        the row-wise sum of selected multi-plane TT rate features.
    global_rate_col : str
        Legacy compatibility argument (not required for matching when
        include_global_rate=True).
    param_columns : list of str or None
        Parameter columns to estimate. If None, auto-detected from
        dictionary (flux_cm2_min, cos_n, eff_sim_1..4).
    exclude_same_file : bool
        If True, exclude dictionary entries with the same filename_base
        as the dataset row being estimated.
    exclude_candidates_sharing_parameter_values : bool
        If True, remove candidate dictionary rows that share any configured
        parameter value with the current dataset row (after same-file and
        z-compatibility filtering).
    shared_parameter_exclusion_mode : str | None
        Shared-value exclusion mode: "partial" removes candidates sharing
        any selected parameter; "full" removes only full coincidences
        across all selected parameters. None falls back to
        exclude_candidates_sharing_parameter_values.
    shared_parameter_exclusion_columns : list[str] | str | None
        Parameter columns used for shared-value exclusion. `None` or `"auto"`
        uses estimated parameter columns.
    shared_parameter_exclusion_ignore : list[str] | str | None
        Columns excluded from shared-value matching (default: cos_n).
    shared_parameter_match_atol : float
        Absolute tolerance for numeric equality checks in shared-parameter
        exclusion.
    density_weighting_cfg : dict or None
        Optional density-correction config. When provided and enabled,
        IDW interpolation weights are multiplied by inverse local-density
        scaling in feature space (same feature columns + distance metric
        as matching). Only `density_correction_enabled` and
        `density_correction_k_neighbors` are configurable.
    inverse_mapping_cfg : dict or None
        Optional controls for inverse mapping from feature-space neighbors
        to parameter estimates. Supported keys include:
        neighbor_selection (nearest|knn|all), neighbor_count, weighting
        (uniform|inverse_distance|softmax), inverse_distance_power,
        softmax_temperature, distance_floor, aggregation
        (weighted_mean|weighted_median|local_linear), histogram_distance_weight,
        histogram_distance_blend_mode (normalized|raw),
        mask_out_of_support_eff_features (bool; default True).
    derived_tt_prefix : str
        Prefix selector for derived mode TT-sum global rate:
        "last" (recommended) or explicit prefix name.
    derived_trigger_types : list[str] | str | None
        Optional TT label allowlist used in derived mode trigger-sum
        construction (e.g. "1234,123,234,124,134"). Empty/None uses all
        available multi-plane trigger types.
    derived_include_to_tt_rate_hz : bool
        If True, allow prefixes containing "_to_" when selecting TT
        columns for derived trigger-sum global rate.
    derived_include_trigger_type_rates : bool
        If True, append selected trigger-type rate columns to derived-mode
        features (in addition to empirical efficiencies and derived TT-sum
        global rate).
    derived_include_rate_histogram : bool
        If True, append `events_per_second_<bin>_rate_hz` histogram bins
        to derived-mode features.
    derived_physics_features : list[str] | str | bool | None
        Optional derived-mode physics transforms to append as features.
        Supported values: "log_rate_over_eff_product", "eff_product",
        "eff_coincidence_moments" (log-sum of pair/triplet efficiency products).
        A boolean True enables "log_rate_over_eff_product".
    histogram_distance_weight : float
        Legacy alias for `inverse_mapping_cfg.histogram_distance_weight`.
    histogram_distance_blend_mode : str
        Legacy alias for `inverse_mapping_cfg.histogram_distance_blend_mode`.

    Returns
    -------
    pd.DataFrame
        One row per dataset entry with columns:
        - dataset_index, filename_base
        - est_<param> for each estimated parameter
        - n_candidates, best_distance
        - all original dataset columns prefixed with data_
    """
    dict_df = pd.read_csv(dictionary_path, low_memory=False)
    data_df = pd.read_csv(dataset_path, low_memory=False)

    return estimate_from_dataframes(
        dict_df=dict_df,
        data_df=data_df,
        feature_columns=feature_columns,
        distance_metric=distance_metric,
        interpolation_k=interpolation_k,
        z_tol=z_tol,
        include_global_rate=include_global_rate,
        global_rate_col=global_rate_col,
        param_columns=param_columns,
        exclude_same_file=exclude_same_file,
        exclude_candidates_sharing_parameter_values=exclude_candidates_sharing_parameter_values,
        shared_parameter_exclusion_mode=shared_parameter_exclusion_mode,
        shared_parameter_exclusion_columns=shared_parameter_exclusion_columns,
        shared_parameter_exclusion_ignore=shared_parameter_exclusion_ignore,
        shared_parameter_match_atol=shared_parameter_match_atol,
        density_weighting_cfg=density_weighting_cfg,
        inverse_mapping_cfg=inverse_mapping_cfg,
        derived_tt_prefix=derived_tt_prefix,
        derived_trigger_types=derived_trigger_types,
        derived_include_to_tt_rate_hz=derived_include_to_tt_rate_hz,
        derived_include_trigger_type_rates=derived_include_trigger_type_rates,
        derived_include_rate_histogram=derived_include_rate_histogram,
        derived_physics_features=derived_physics_features,
        histogram_distance_weight=histogram_distance_weight,
        histogram_distance_blend_mode=histogram_distance_blend_mode,
    )


def estimate_from_dataframes(
    dict_df: pd.DataFrame,
    data_df: pd.DataFrame,
    *,
    feature_columns: str | list[str] = "auto",
    distance_metric: str = "l2_zscore",
    interpolation_k: int | None = 5,
    z_tol: float = 1e-6,
    include_global_rate: bool = True,
    global_rate_col: str = "events_per_second_global_rate",
    param_columns: list[str] | None = None,
    exclude_same_file: bool = True,
    exclude_candidates_sharing_parameter_values: bool = False,
    shared_parameter_exclusion_mode: str | None = None,
    shared_parameter_exclusion_columns: Sequence[str] | str | None = None,
    shared_parameter_exclusion_ignore: Sequence[str] | str | None = ("cos_n",),
    shared_parameter_match_atol: float = 1e-12,
    density_weighting_cfg: Mapping[str, object] | None = None,
    inverse_mapping_cfg: Mapping[str, object] | None = None,
    derived_tt_prefix: str = "last",
    derived_trigger_types: Sequence[str] | str | None = None,
    derived_include_to_tt_rate_hz: bool = False,
    derived_include_trigger_type_rates: bool = False,
    derived_include_rate_histogram: bool = False,
    derived_physics_features: Sequence[str] | str | bool | None = None,
    histogram_distance_weight: float = 1.0,
    histogram_distance_blend_mode: str = "normalized",
    distance_definition: dict | None = None,
) -> pd.DataFrame:
    """Same as estimate_parameters but accepts DataFrames directly."""

    z_cols = [c for c in ["z_plane_1", "z_plane_2", "z_plane_3", "z_plane_4"]
              if c in dict_df.columns and c in data_df.columns]

    # ── Auto-detect feature columns ──────────────────────────────────
    _feature_mode = (
        feature_columns.strip().lower()
        if isinstance(feature_columns, str) else ""
    )
    dict_feature_source = dict_df
    data_feature_source = data_df
    derived_rate_col_used: str | None = None
    derived_rate_sources: list[str] = []
    derived_physics_cols_used: list[str] = []
    if _feature_mode == "auto":
        feat_from_dict = _auto_feature_columns(dict_df, include_global_rate, global_rate_col)
        feat_from_data = _auto_feature_columns(data_df, include_global_rate, global_rate_col)
        feature_cols = sorted(set(feat_from_dict) & set(feat_from_data))
        if not feature_cols:
            raise ValueError("No common feature columns found between dictionary and dataset.")
    elif _feature_mode == "derived":
        (
            dict_feature_source,
            data_feature_source,
            derived_rate_col_used,
            derived_rate_sources,
        ) = _append_derived_tt_global_rate_column(
            dict_df=dict_df,
            data_df=data_df,
            prefix_selector=str(derived_tt_prefix),
            trigger_type_allowlist=derived_trigger_types,
            include_to_tt_rate_hz=_safe_bool(derived_include_to_tt_rate_hz, False),
            output_column=DERIVED_TT_GLOBAL_RATE_COL,
        )
        if (
            derived_rate_col_used is None
            and _safe_bool(include_global_rate, True)
            and global_rate_col in dict_df.columns
            and global_rate_col in data_df.columns
        ):
            derived_rate_col_used = str(global_rate_col)
        if derived_rate_col_used is None:
            raise ValueError(
                "No derived global-rate feature available for derived mode. "
                "Could not build TT-trigger sum and fallback literal global-rate "
                "use is disabled or unavailable."
            )
        (
            dict_feature_source,
            data_feature_source,
            derived_physics_cols_used,
        ) = _append_derived_physics_feature_columns(
            dict_df=dict_feature_source,
            data_df=data_feature_source,
            rate_column=derived_rate_col_used,
            physics_features=derived_physics_features,
        )
        feat_from_dict = _derived_feature_columns(
            dict_feature_source,
            rate_column=derived_rate_col_used,
            trigger_type_rate_columns=(
                derived_rate_sources
                if _safe_bool(derived_include_trigger_type_rates, False)
                else None
            ),
            include_rate_histogram=_safe_bool(derived_include_rate_histogram, False),
            physics_feature_columns=derived_physics_cols_used,
        )
        feat_from_data = _derived_feature_columns(
            data_feature_source,
            rate_column=derived_rate_col_used,
            trigger_type_rate_columns=(
                derived_rate_sources
                if _safe_bool(derived_include_trigger_type_rates, False)
                else None
            ),
            include_rate_histogram=_safe_bool(derived_include_rate_histogram, False),
            physics_feature_columns=derived_physics_cols_used,
        )
        feature_cols = sorted(set(feat_from_dict) & set(feat_from_data))
        if not feature_cols:
            raise ValueError(
                "No derived feature columns found in both dictionary and dataset. "
                "Expected eff_empirical_1..4 and a global-rate feature."
            )
        if derived_rate_col_used == DERIVED_TT_GLOBAL_RATE_COL:
            log.info(
                "Derived feature mode: using TT-sum global rate from %d trigger-rate column(s): %s",
                len(derived_rate_sources),
                derived_rate_sources,
            )
        else:
            log.info(
                "Derived feature mode: TT-sum unavailable, using fallback rate column '%s'.",
                derived_rate_col_used,
            )
        if _safe_bool(derived_include_rate_histogram, False):
            n_hist = sum(1 for c in feature_cols if RATE_HISTOGRAM_BIN_RE.match(str(c)))
            log.info("Derived feature mode: including %d rate-histogram bin feature(s).", n_hist)
        if _safe_bool(derived_include_trigger_type_rates, False):
            n_tt = sum(1 for c in feature_cols if TT_RATE_COLUMN_RE.match(str(c)))
            log.info("Derived feature mode: including %d trigger-type rate feature(s).", n_tt)
        if derived_physics_cols_used:
            log.info(
                "Derived feature mode: including physics transform feature(s): %s",
                derived_physics_cols_used,
            )
    else:
        requested_feature_cols = parse_explicit_feature_columns(feature_columns)
        if not requested_feature_cols:
            raise ValueError(
                "No explicit feature columns were provided."
            )
        missing_in_dict = [c for c in requested_feature_cols if c not in dict_df.columns]
        missing_in_data = [c for c in requested_feature_cols if c not in data_df.columns]
        if missing_in_dict or missing_in_data:
            parts: list[str] = []
            if missing_in_dict:
                parts.append(f"missing in dictionary: {missing_in_dict}")
            if missing_in_data:
                parts.append(f"missing in dataset: {missing_in_data}")
            raise ValueError(
                "Explicit feature columns must be present in both dictionary and dataset; "
                + "; ".join(parts)
            )
        feature_cols = list(requested_feature_cols)

    # ── Auto-detect parameter columns ────────────────────────────────
    feature_col_set = set(feature_cols)
    if param_columns is None:
        param_columns = []
        for c in ["flux_cm2_min", "cos_n",
                   "eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4",
                   "eff_empirical_1", "eff_empirical_2", "eff_empirical_3", "eff_empirical_4"]:
            if c in dict_df.columns and c not in feature_col_set:
                param_columns.append(c)
        if not param_columns:
            raise ValueError("No parameter columns found in dictionary.")
    param_columns = [str(col).strip() for col in param_columns if str(col).strip()]
    missing_param_columns = [col for col in param_columns if col not in dict_df.columns]
    if missing_param_columns:
        raise ValueError(
            f"Dictionary is missing required parameter column(s): {missing_param_columns}"
        )
    log.info("Parameter columns to estimate: %s", param_columns)

    # ── Coerce feature columns to numeric ────────────────────────────
    dict_features = dict_feature_source[feature_cols].apply(pd.to_numeric, errors="coerce")
    data_features = data_feature_source[feature_cols].apply(pd.to_numeric, errors="coerce")
    (
        dict_features,
        data_features,
        feature_cols,
        derived_global_col,
        derived_global_sources,
    ) = _append_tt_global_sum_feature(
        dict_features=dict_features,
        data_features=data_features,
        feature_cols=feature_cols,
        include_global_rate=_safe_bool(include_global_rate, True),
    )
    if derived_global_col is not None:
        log.info(
            "Feature columns (%d): %s + derived global '%s' as sum(%d TT cols)",
            len(feature_cols),
            [c for c in feature_cols if c != derived_global_col],
            derived_global_col,
            len(derived_global_sources),
        )
    else:
        log.info("Feature columns (%d): %s", len(feature_cols), feature_cols)

    dict_completeness_frame = dict_features.copy()
    for pc in param_columns:
        dict_completeness_frame[pc] = pd.to_numeric(dict_df[pc], errors="coerce")
    (
        _dict_completeness_numeric,
        dict_complete_mask,
        dictionary_feature_space_completeness,
    ) = _build_complete_numeric_row_mask(
        dict_completeness_frame,
        required_columns=[*feature_cols, *param_columns],
        label="dictionary_feature_and_parameter_space",
    )
    if not np.any(dict_complete_mask):
        raise ValueError(
            "Dictionary has no rows with complete feature and parameter space for estimation."
        )
    if not np.all(dict_complete_mask):
        log.warning(
            "Estimator dictionary completeness: removing %d incomplete row(s), keeping %d/%d complete rows.",
            int(np.size(dict_complete_mask) - np.sum(dict_complete_mask)),
            int(np.sum(dict_complete_mask)),
            int(len(dict_complete_mask)),
        )
        dict_df = _filter_dataframe_by_mask(dict_df, row_mask=dict_complete_mask)
        dict_feature_source = _filter_dataframe_by_mask(
            dict_feature_source,
            row_mask=dict_complete_mask,
        )
        dict_features = _filter_dataframe_by_mask(
            dict_features,
            row_mask=dict_complete_mask,
        )
    else:
        dict_df = dict_df.reset_index(drop=True)
        dict_feature_source = dict_feature_source.reset_index(drop=True)
        dict_features = dict_features.reset_index(drop=True)

    (
        _data_completeness_numeric,
        data_complete_mask,
        dataset_feature_space_completeness,
    ) = _build_complete_numeric_row_mask(
        data_features,
        required_columns=feature_cols,
        label="dataset_feature_space",
    )
    if not np.all(data_complete_mask):
        log.warning(
            "Estimator dataset completeness: %d incomplete row(s) will be kept in the output but skipped for estimation.",
            int(np.size(data_complete_mask) - np.sum(data_complete_mask)),
        )
    data_df = data_df.reset_index(drop=True)
    data_feature_source = data_feature_source.reset_index(drop=True)
    data_features = data_features.reset_index(drop=True)

    inverse_cfg = resolve_inverse_mapping_cfg(
        inverse_mapping_cfg=inverse_mapping_cfg,
        interpolation_k=interpolation_k,
        histogram_distance_weight=histogram_distance_weight,
        histogram_distance_blend_mode=histogram_distance_blend_mode,
    )
    estimation_mode = str(inverse_cfg.get("estimation_mode", "single_stage"))
    neighbor_selection = str(inverse_cfg["neighbor_selection"])
    neighbor_count = inverse_cfg.get("neighbor_count")
    neighbor_weighting = str(inverse_cfg["weighting"])
    inverse_distance_power = float(inverse_cfg["inverse_distance_power"])
    softmax_temperature = float(inverse_cfg["softmax_temperature"])
    distance_floor = float(inverse_cfg["distance_floor"])
    aggregation_mode = str(inverse_cfg["aggregation"])
    local_linear_ridge_lambda = float(
        inverse_cfg.get(
            "local_linear_ridge_lambda",
            _INVERSE_MAPPING_DEFAULTS["local_linear_ridge_lambda"],
        )
    )
    stage2_eff_conditioning_weight = float(
        inverse_cfg.get("stage2_efficiency_conditioning_weight", 1.0)
    )
    stage2_eff_gate_max = float(
        inverse_cfg.get(
            "stage2_efficiency_gate_max",
            _INVERSE_MAPPING_DEFAULTS["stage2_efficiency_gate_max"],
        )
    )
    stage2_eff_gate_min_candidates = int(
        inverse_cfg.get(
            "stage2_efficiency_gate_min_candidates",
            _INVERSE_MAPPING_DEFAULTS["stage2_efficiency_gate_min_candidates"],
        )
    )
    stage2_use_rate_histogram = bool(
        inverse_cfg.get(
            "stage2_use_rate_histogram",
            _INVERSE_MAPPING_DEFAULTS["stage2_use_rate_histogram"],
        )
    )
    stage2_hist_distance_weight = float(
        inverse_cfg.get(
            "stage2_histogram_distance_weight",
            _INVERSE_MAPPING_DEFAULTS["stage2_histogram_distance_weight"],
        )
    )
    hist_distance_weight = float(inverse_cfg["histogram_distance_weight"])
    hist_distance_blend_mode = str(inverse_cfg["histogram_distance_blend_mode"])
    hist_distance_cfg = _resolve_histogram_distance_cfg(
        inverse_cfg.get("histogram_distance")
    )
    hist_distance_mode = str(hist_distance_cfg["distance"])
    hist_normalization = str(hist_distance_cfg["normalization"])
    hist_p_norm = float(hist_distance_cfg["p_norm"])
    hist_amplitude_weight = float(hist_distance_cfg["amplitude_weight"])
    hist_shape_weight = float(hist_distance_cfg["shape_weight"])
    hist_slope_weight = float(hist_distance_cfg["slope_weight"])
    hist_cdf_weight = float(hist_distance_cfg["cdf_weight"])
    hist_amplitude_stat = str(hist_distance_cfg["amplitude_stat"])
    mask_out_of_support_eff_features = bool(
        inverse_cfg.get("mask_out_of_support_eff_features", True)
    )
    effvec_cfg = inverse_cfg.get("efficiency_vector_distance", {})
    if not isinstance(effvec_cfg, Mapping):
        effvec_cfg = {}
    effvec_distance_cfg = _resolve_efficiency_vector_distance_cfg(effvec_cfg)
    effvec_distance_enabled = bool(effvec_cfg.get("enabled", False))
    effvec_distance_weight = float(effvec_cfg.get("weight", 0.0))
    effvec_distance_blend_mode = str(
        effvec_cfg.get("blend_mode", _INVERSE_MAPPING_DEFAULTS["efficiency_vector_distance"]["blend_mode"])
    )
    effvec_stage2_enabled = bool(effvec_cfg.get("stage2_enabled", False))
    effvec_stage2_weight = float(effvec_cfg.get("stage2_weight", 0.0))
    effvec_uncertainty_floor = float(effvec_distance_cfg["uncertainty_floor"])
    effvec_min_valid_bins = int(effvec_distance_cfg["min_valid_bins_per_vector"])
    effvec_fiducial = dict(effvec_distance_cfg["fiducial"])
    effvec_normalization = str(effvec_distance_cfg["normalization"])
    effvec_p_norm = float(effvec_distance_cfg["p_norm"])
    effvec_amplitude_weight = float(effvec_distance_cfg["amplitude_weight"])
    effvec_shape_weight = float(effvec_distance_cfg["shape_weight"])
    effvec_slope_weight = float(effvec_distance_cfg["slope_weight"])
    effvec_cdf_weight = float(effvec_distance_cfg["cdf_weight"])
    effvec_amplitude_stat = str(effvec_distance_cfg["amplitude_stat"])
    effvec_group_reduction = str(effvec_distance_cfg["group_reduction"])

    hist_feature_idx = _histogram_feature_indices(feature_cols)
    hist_feature_set = set(hist_feature_idx)
    hist_feature_cols = [str(feature_cols[idx]) for idx in hist_feature_idx]
    effvec_feature_idx_candidate = _efficiency_vector_feature_indices(feature_cols)
    effvec_group_payloads = _prepare_efficiency_vector_group_payloads(
        dict_df=dict_feature_source,
        data_df=data_feature_source,
    )
    effvec_group_payloads = _filter_efficiency_vector_payloads(
        effvec_group_payloads,
        selected_feature_columns=feature_cols,
    )
    use_effvec_group_distance = bool(effvec_group_payloads) and (
        effvec_distance_enabled or effvec_stage2_enabled
    )
    if use_effvec_group_distance:
        effvec_feature_idx = effvec_feature_idx_candidate
    else:
        effvec_feature_idx = []
        if effvec_feature_idx_candidate and (effvec_distance_enabled or effvec_stage2_enabled):
            log.warning(
                "Efficiency-vector multi-feature distance requested, but no shared vector payloads were resolved. "
                "Selected efficiency-vector columns will remain one-feature vector terms."
            )
    effvec_feature_set = set(effvec_feature_idx)
    non_hist_feature_idx = [
        idx
        for idx in range(len(feature_cols))
        if idx not in hist_feature_set and idx not in effvec_feature_set
    ]
    non_hist_feature_cols = [str(feature_cols[idx]) for idx in non_hist_feature_idx]
    hist_feature_cols_for_distance = list(hist_feature_cols)

    def _is_raw_tt_rate_feature(name: str) -> bool:
        text = str(name).strip()
        if text.startswith(DERIVED_TT_GLOBAL_RATE_COL):
            return False
        return TT_RATE_COLUMN_RE.match(text) is not None

    base_eff_feature_idx = np.asarray(
        [
            j
            for j, name in enumerate(non_hist_feature_cols)
            if str(name).startswith("eff_empirical_")
        ],
        dtype=int,
    )
    base_tt_feature_idx = np.asarray(
        [j for j, name in enumerate(non_hist_feature_cols) if _is_raw_tt_rate_feature(name)],
        dtype=int,
    )
    base_other_feature_idx = np.asarray(
        [
            j
            for j in range(len(non_hist_feature_cols))
            if j not in set(base_eff_feature_idx.tolist() + base_tt_feature_idx.tolist())
        ],
        dtype=int,
    )
    log.info(
        "Inverse mapping: mode=%s selection=%s k=%s weighting=%s aggregation=%s",
        estimation_mode,
        neighbor_selection,
        ("all" if neighbor_count is None else str(neighbor_count)),
        neighbor_weighting,
        aggregation_mode,
    )
    if aggregation_mode == "local_linear":
        log.info("Inverse mapping local-linear ridge lambda: %.3g", local_linear_ridge_lambda)
    if estimation_mode == "two_stage_eff_address_then_flux":
        log.info(
            "Two-stage address mode: gate_max=%.3g gate_min_candidates=%d use_rate_histogram=%s stage2_hist_weight=%.3g use_efficiency_vectors=%s stage2_effvec_weight=%.3g",
            stage2_eff_gate_max,
            stage2_eff_gate_min_candidates,
            str(stage2_use_rate_histogram).lower(),
            stage2_hist_distance_weight,
            str(bool(effvec_stage2_enabled and use_effvec_group_distance)).lower(),
            effvec_stage2_weight,
        )

    data_features, out_of_support_eff_mask_non_hist, out_of_support_eff_info = (
        _mask_out_of_support_efficiency_features(
            dict_features=dict_features,
            data_features=data_features,
            feature_cols=feature_cols,
            non_hist_feature_idx=non_hist_feature_idx,
            base_eff_feature_idx=base_eff_feature_idx,
            enabled=mask_out_of_support_eff_features,
        )
    )
    if (
        out_of_support_eff_info.get("enabled")
        and out_of_support_eff_info.get("n_eff_features_considered", 0) > 0
    ):
        n_rows_any = int(out_of_support_eff_info.get("n_rows_any_masked", 0))
        frac_rows_any = float(out_of_support_eff_info.get("fraction_rows_any_masked", 0.0))
        mean_masked = float(
            out_of_support_eff_info.get("mean_masked_eff_features_per_row", 0.0)
        )
        per_feature = out_of_support_eff_info.get("per_feature", {})
        if n_rows_any > 0:
            details = []
            if isinstance(per_feature, Mapping):
                for name, stats in per_feature.items():
                    if not isinstance(stats, Mapping):
                        continue
                    frac = float(stats.get("fraction_rows_masked", 0.0))
                    if frac <= 0.0:
                        continue
                    details.append(f"{name}:{100.0 * frac:.1f}%")
            if details:
                log.warning(
                    "Out-of-support empirical-efficiency masking applied: rows_any=%d/%d (%.1f%%), mean_masked_per_row=%.3f; per-feature=%s",
                    n_rows_any,
                    len(data_features),
                    100.0 * frac_rows_any,
                    mean_masked,
                    ", ".join(details),
                )
            else:
                log.warning(
                    "Out-of-support empirical-efficiency masking applied: rows_any=%d/%d (%.1f%%), mean_masked_per_row=%.3f.",
                    n_rows_any,
                    len(data_features),
                    100.0 * frac_rows_any,
                    mean_masked,
                )
        else:
            log.info(
                "Out-of-support empirical-efficiency masking enabled: no rows outside support."
            )

    dict_feature_raw_np = dict_features.to_numpy(dtype=float)
    data_feature_raw_np = data_features.to_numpy(dtype=float)

    # ── Distance-definition artifact (STEP 1.5) ─────────────────────
    dd_center: np.ndarray | None = None
    dd_scale: np.ndarray | None = None
    dd_weights: np.ndarray | None = None
    dd_p_norm: float | None = None
    _dd_non_hist_weights: np.ndarray | None = None  # weights restricted to non-hist features
    dd_group_weights: dict[str, float] = {}
    dd_feature_groups: dict[str, object] = {}
    extra_group_terms: list[dict[str, object]] = []

    if distance_definition is not None and distance_definition.get("available"):
        dd_center = np.asarray(distance_definition["center"], dtype=float)
        dd_scale = np.asarray(distance_definition["scale"], dtype=float)
        dd_weights = np.asarray(distance_definition["weights"], dtype=float)
        dd_p_norm = float(distance_definition["p_norm"])
        raw_one_feature_vector_cols = distance_definition.get(
            "one_feature_vector_columns",
            distance_definition.get("scalar_feature_columns", feature_cols),
        )
        if isinstance(raw_one_feature_vector_cols, Sequence) and not isinstance(raw_one_feature_vector_cols, (str, bytes)):
            dd_one_feature_vector_cols = [
                str(col) for col in raw_one_feature_vector_cols if str(col) in feature_cols
            ]
        else:
            dd_one_feature_vector_cols = []
        if not dd_one_feature_vector_cols:
            dd_one_feature_vector_cols = [
                str(col)
                for col, w in zip(feature_cols, dd_weights)
                if np.isfinite(w) and float(w) > 0.0
            ]
        if isinstance(distance_definition.get("group_weights"), Mapping):
            dd_group_weights = {
                str(name): float(value)
                for name, value in distance_definition["group_weights"].items()
                if str(name).strip()
            }
        if isinstance(distance_definition.get("feature_groups"), Mapping):
            dd_feature_groups = {
                str(name): value
                for name, value in distance_definition["feature_groups"].items()
                if str(name).strip()
            }
        n_active = int(np.sum(dd_weights > 0))
        n_active_groups = int(sum(float(v) > 0.0 for v in dd_group_weights.values()))
        mode_name = distance_definition.get("selected_mode", "unknown")
        log.info(
            "Using STEP 1.5 distance definition: %s (p=%.1f, one_feature_vectors_active=%d/%d, multi_feature_vectors_active=%d)",
            mode_name, dd_p_norm, n_active, len(feature_cols), n_active_groups,
        )
        _log_unified_distance_term_list(
            feature_columns=feature_cols,
            one_feature_vector_columns=dd_one_feature_vector_cols,
            one_feature_weights=dd_weights,
            feature_groups=dd_feature_groups,
            group_weights=dd_group_weights,
            header="STEP 1.5 unified distance terms (X features --> 1 distance):",
        )
        if "rate_histogram" in dd_group_weights:
            hist_distance_weight = max(float(dd_group_weights["rate_histogram"]), 0.0)
            hist_group_cfg = dd_feature_groups.get("rate_histogram", {})
            if isinstance(hist_group_cfg, Mapping):
                hist_distance_blend_mode = _normalize_hist_blend_mode(
                    hist_group_cfg.get("blend_mode", hist_distance_blend_mode)
                )
                hist_distance_cfg = _resolve_histogram_distance_cfg(hist_group_cfg)
                hist_distance_mode = str(hist_distance_cfg["distance"])
                hist_normalization = str(hist_distance_cfg["normalization"])
                hist_p_norm = float(hist_distance_cfg["p_norm"])
                hist_amplitude_weight = float(hist_distance_cfg["amplitude_weight"])
                hist_shape_weight = float(hist_distance_cfg["shape_weight"])
                hist_slope_weight = float(hist_distance_cfg["slope_weight"])
                hist_cdf_weight = float(hist_distance_cfg["cdf_weight"])
                hist_amplitude_stat = str(hist_distance_cfg["amplitude_stat"])
        if "efficiency_vectors" in dd_group_weights:
            effvec_distance_enabled = True
            effvec_distance_weight = max(float(dd_group_weights["efficiency_vectors"]), 0.0)
            effvec_group_cfg = dd_feature_groups.get("efficiency_vectors", {})
            if isinstance(effvec_group_cfg, Mapping):
                effvec_distance_blend_mode = _normalize_hist_blend_mode(
                    effvec_group_cfg.get("blend_mode", effvec_distance_blend_mode)
                )
                effvec_distance_cfg = _resolve_efficiency_vector_distance_cfg(effvec_group_cfg)
                effvec_uncertainty_floor = float(effvec_distance_cfg["uncertainty_floor"])
                effvec_min_valid_bins = int(effvec_distance_cfg["min_valid_bins_per_vector"])
                effvec_fiducial = dict(effvec_distance_cfg["fiducial"])
                effvec_normalization = str(effvec_distance_cfg["normalization"])
                effvec_p_norm = float(effvec_distance_cfg["p_norm"])
                effvec_amplitude_weight = float(effvec_distance_cfg["amplitude_weight"])
                effvec_shape_weight = float(effvec_distance_cfg["shape_weight"])
                effvec_slope_weight = float(effvec_distance_cfg["slope_weight"])
                effvec_cdf_weight = float(effvec_distance_cfg["cdf_weight"])
                effvec_amplitude_stat = str(effvec_distance_cfg["amplitude_stat"])
                effvec_group_reduction = str(effvec_distance_cfg["group_reduction"])
                effvec_group_payloads = _filter_efficiency_vector_payloads(
                    effvec_group_payloads,
                    feature_groups_cfg=effvec_group_cfg,
                    selected_feature_columns=feature_cols,
                )
                use_effvec_group_distance = bool(effvec_group_payloads) and (
                    effvec_distance_enabled or effvec_stage2_enabled
                )
        if dd_group_weights:
            log.info(
                "Using STEP 1.5 multi-feature vector-term weights: %s",
                {k: round(float(v), 6) for k, v in dd_group_weights.items()},
            )

    dd_hist_group_cfg = dd_feature_groups.get("rate_histogram", {})
    if not isinstance(dd_hist_group_cfg, Mapping):
        dd_hist_group_cfg = {}
    dd_hist_feature_cols = [
        str(col)
        for col in dd_hist_group_cfg.get("feature_columns", [])
        if str(col) in dict_feature_source.columns and str(col) in data_feature_source.columns
    ]
    hist_feature_cols_for_distance = dd_hist_feature_cols or hist_feature_cols
    if hist_feature_cols_for_distance and not non_hist_feature_idx and hist_distance_weight <= 0.0:
        # Histogram-only feature sets need non-zero distance contribution.
        hist_distance_weight = 1.0
    if (
        use_effvec_group_distance
        and not non_hist_feature_idx
        and not hist_feature_cols_for_distance
        and effvec_distance_enabled
        and effvec_distance_weight <= 0.0
    ):
        effvec_distance_weight = 1.0
    if hist_feature_cols_for_distance:
        first_hist = hist_feature_cols_for_distance[0]
        last_hist = hist_feature_cols_for_distance[-1]
        log.info(
            "Histogram feature group detected: %d bins (%s .. %s), weight=%.3g blend=%s metric=%s norm=%s p=%.3g amp=%.3g shape=%.3g slope=%.3g cdf=%.3g stat=%s.",
            len(hist_feature_cols_for_distance),
            first_hist,
            last_hist,
            hist_distance_weight,
            hist_distance_blend_mode,
            hist_distance_mode,
            hist_normalization,
            hist_p_norm,
            hist_amplitude_weight,
            hist_shape_weight,
            hist_slope_weight,
            hist_cdf_weight,
            hist_amplitude_stat,
        )
    if use_effvec_group_distance and effvec_group_payloads:
        log.info(
            "Efficiency-vector groups detected: %d group(s), weight=%.3g blend=%s metric=%s norm=%s p=%.3g amp=%.3g shape=%.3g slope=%.3g cdf=%.3g reduction=%s stage2_enabled=%s stage2_weight=%.3g fiducial=%s.",
            len(effvec_group_payloads),
            effvec_distance_weight,
            effvec_distance_blend_mode,
            str(effvec_distance_cfg["distance"]),
            effvec_normalization,
            effvec_p_norm,
            effvec_amplitude_weight,
            effvec_shape_weight,
            effvec_slope_weight,
            effvec_cdf_weight,
            effvec_group_reduction,
            str(bool(effvec_stage2_enabled)).lower(),
            effvec_stage2_weight,
            dict(effvec_fiducial),
        )

    for group_name, raw_weight in dd_group_weights.items():
        name = str(group_name).strip()
        if not name or name in {"rate_histogram", "efficiency_vectors"}:
            continue
        try:
            weight = max(float(raw_weight), 0.0)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(weight) or weight <= 0.0:
            continue
        raw_cfg = dd_feature_groups.get(name, {})
        if not isinstance(raw_cfg, Mapping):
            raw_cfg = {}
        group_kind = _resolve_feature_group_kind(name, raw_cfg)
        if group_kind == "efficiency_vectors":
            log.warning(
                "Vector term '%s' resolved as efficiency_vectors but only canonical 'efficiency_vectors' is supported for payload distance; skipping term.",
                name,
            )
            continue
        group_cols = [
            str(col)
            for col in raw_cfg.get("feature_columns", [])
            if str(col) in dict_feature_source.columns and str(col) in data_feature_source.columns
        ]
        if not group_cols:
            log.warning(
                "Vector term '%s' has no shared feature columns in dictionary/data; skipping term.",
                name,
            )
            continue
        blend_mode = _normalize_hist_blend_mode(raw_cfg.get("blend_mode", "normalized"))
        if group_kind == "rate_histogram":
            distance_cfg = _resolve_histogram_distance_cfg(raw_cfg)
        else:
            distance_cfg = _resolve_ordered_vector_group_distance_cfg(raw_cfg)
        try:
            min_valid_bins = max(int(float(raw_cfg.get("min_valid_bins", 1))), 1)
        except (TypeError, ValueError):
            min_valid_bins = 1
        dict_matrix = (
            dict_feature_source[group_cols]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(dtype=float)
        )
        data_matrix = (
            data_feature_source[group_cols]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(dtype=float)
        )
        extra_group_terms.append(
            {
                "name": name,
                "kind": group_kind,
                "weight": float(weight),
                "blend_mode": str(blend_mode),
                "feature_columns": list(group_cols),
                "distance_cfg": dict(distance_cfg),
                "min_valid_bins": int(min_valid_bins),
                "dict_matrix": dict_matrix,
                "data_matrix": data_matrix,
            }
        )
        log.info(
            "Feature group detected: %s kind=%s dims=%d weight=%.3g blend=%s metric=%s norm=%s p=%.3g amp=%.3g shape=%.3g slope=%.3g cdf=%.3g.",
            name,
            group_kind,
            len(group_cols),
            float(weight),
            str(blend_mode),
            str(distance_cfg.get("distance", "ordered_vector_lp")),
            str(distance_cfg.get("normalization", "none")),
            float(distance_cfg.get("p_norm", 2.0)),
            float(distance_cfg.get("amplitude_weight", 0.0)),
            float(distance_cfg.get("shape_weight", 1.0)),
            float(distance_cfg.get("slope_weight", 0.0)),
            float(distance_cfg.get("cdf_weight", 0.0)),
        )

    # ── Scaling ──────────────────────────────────────────────────────
    if dd_center is not None and dd_scale is not None:
        # Use STEP 1.5 center/scale instead of auto z-score
        safe_scale = np.where(np.abs(dd_scale) > 1e-15, dd_scale, np.nan)
        dict_scaled = ((dict_feature_raw_np - dd_center) / safe_scale)
        data_scaled = ((data_feature_raw_np - dd_center) / safe_scale)
    elif distance_metric == "l2_zscore":
        # Compute means and stds from the DICTIONARY (reference distribution)
        means = dict_features.mean(axis=0, skipna=True)
        stds = dict_features.std(axis=0, skipna=True).replace({0.0: np.nan})
        zero_var_cols = list(stds.index[stds.isna()])
        if zero_var_cols:
            log.warning(
                "z-score scaling: %d zero-variance feature(s) will be masked "
                "out of distance computation: %s",
                len(zero_var_cols),
                ", ".join(str(c) for c in zero_var_cols),
            )
        dict_scaled = ((dict_features - means) / stds).to_numpy(dtype=float)
        data_scaled = ((data_features - means) / stds).to_numpy(dtype=float)
    else:
        dict_scaled = dict_features.to_numpy(dtype=float)
        data_scaled = data_features.to_numpy(dtype=float)

    if non_hist_feature_idx:
        dict_scaled_base = dict_scaled[:, non_hist_feature_idx]
        data_scaled_base = data_scaled[:, non_hist_feature_idx]
        if dd_weights is not None:
            _dd_non_hist_weights = dd_weights[non_hist_feature_idx]
    else:
        dict_scaled_base = np.empty((len(dict_df), 0), dtype=float)
        data_scaled_base = np.empty((len(data_df), 0), dtype=float)

    if hist_feature_cols_for_distance:
        dict_hist_matrix = (
            dict_feature_source[hist_feature_cols_for_distance]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(dtype=float)
        )
        data_hist_matrix = (
            data_feature_source[hist_feature_cols_for_distance]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(dtype=float)
        )
    else:
        dict_hist_matrix = None
        data_hist_matrix = None

    stage2_hist_cols: list[str] = []
    stage2_hist_matrix_dict: np.ndarray | None = None
    stage2_hist_matrix_data: np.ndarray | None = None
    if stage2_use_rate_histogram:
        stage2_hist_cols = _shared_histogram_feature_columns(dict_df.columns, data_df.columns)
        if stage2_hist_cols:
            stage2_hist_matrix_dict = (
                dict_df[stage2_hist_cols]
                .apply(pd.to_numeric, errors="coerce")
                .to_numpy(dtype=float)
            )
            stage2_hist_matrix_data = (
                data_df[stage2_hist_cols]
                .apply(pd.to_numeric, errors="coerce")
                .to_numpy(dtype=float)
            )
        elif hist_feature_cols_for_distance and dict_hist_matrix is not None and data_hist_matrix is not None:
            # Fallback to selected histogram features when explicit bins are not available.
            stage2_hist_matrix_dict = dict_hist_matrix
            stage2_hist_matrix_data = data_hist_matrix
    if estimation_mode == "two_stage_eff_address_then_flux":
        log.info(
            "Two-stage address mode histogram bins: %d",
            int(len(stage2_hist_cols))
            if stage2_hist_cols
            else (int(dict_hist_matrix.shape[1]) if dict_hist_matrix is not None else 0),
        )
        if stage2_hist_matrix_dict is None:
            log.warning(
                "Two-stage address mode: no rate-histogram bins resolved; stage 2 will use non-hist rate features only."
            )

    local_linear_group_features_dict: dict[str, np.ndarray] = {}
    local_linear_group_features_data: dict[str, np.ndarray] = {}
    if aggregation_mode == "local_linear" and isinstance(dd_feature_groups, Mapping) and dd_feature_groups:
        (
            local_linear_group_features_dict,
            local_linear_group_features_data,
        ) = _build_group_local_linear_feature_matrices(
            dict_feature_source=dict_feature_source,
            data_feature_source=data_feature_source,
            feature_groups=dd_feature_groups,
            selected_feature_columns=feature_cols,
        )

    def _concat_local_linear_feature_space(
        base_matrix: np.ndarray,
        group_features: Mapping[str, np.ndarray],
    ) -> np.ndarray | None:
        parts: list[np.ndarray] = []
        base_arr = np.asarray(base_matrix, dtype=float)
        if base_arr.ndim == 2 and base_arr.shape[1] > 0:
            parts.append(base_arr)
        for group_name in sorted(group_features.keys()):
            coords = np.asarray(group_features[group_name], dtype=float)
            if coords.ndim != 2 or coords.shape[0] != base_arr.shape[0] or coords.shape[1] == 0:
                continue
            parts.append(coords)
        if not parts:
            return None
        return np.concatenate(parts, axis=1)

    dict_local_linear_features = _concat_local_linear_feature_space(
        dict_scaled_base,
        local_linear_group_features_dict,
    )
    data_local_linear_features = _concat_local_linear_feature_space(
        data_scaled_base,
        local_linear_group_features_data,
    )
    if aggregation_mode == "local_linear":
        base_dim = int(dict_scaled_base.shape[1]) if dict_scaled_base.ndim == 2 else 0
        total_dim = (
            int(dict_local_linear_features.shape[1])
            if isinstance(dict_local_linear_features, np.ndarray) and dict_local_linear_features.ndim == 2
            else 0
        )
        grouped_dim = max(total_dim - base_dim, 0)
        if grouped_dim > 0:
            log.info(
                "Local-linear feature dimensions: one-feature vectors=%d, vector-term local coords=%d, total=%d.",
                base_dim,
                grouped_dim,
                total_dim,
            )
        else:
            log.info(
                "Local-linear feature dimensions: one-feature vectors=%d, vector-term local coords=0 (multi-feature vector terms kept as direct distance terms).",
                base_dim,
            )

    def _compute_efficiency_vector_candidate_distances(
        *,
        row_idx: int,
        cand_indices_local: np.ndarray,
    ) -> np.ndarray | None:
        if (not use_effvec_group_distance) or len(cand_indices_local) == 0 or (not effvec_group_payloads):
            return None
        group_distances: list[np.ndarray] = []
        for payload in effvec_group_payloads:
            sample_eff = np.asarray(payload["data_eff"], dtype=float)[row_idx]
            candidates_eff = np.asarray(payload["dict_eff"], dtype=float)[cand_indices_local]
            sample_unc = np.asarray(payload["data_unc"], dtype=float)[row_idx]
            candidates_unc = np.asarray(payload["dict_unc"], dtype=float)[cand_indices_local]
            group_dist = _efficiency_vector_group_distance_many(
                sample_eff=sample_eff,
                candidates_eff=candidates_eff,
                sample_unc=sample_unc,
                candidates_unc=candidates_unc,
                centers=np.asarray(payload["centers"], dtype=float),
                axis_name=str(payload["axis"]),
                fiducial=effvec_fiducial,
                uncertainty_floor=effvec_uncertainty_floor,
                min_valid_bins=effvec_min_valid_bins,
                normalization=effvec_normalization,
                p_norm=effvec_p_norm,
                amplitude_weight=effvec_amplitude_weight,
                shape_weight=effvec_shape_weight,
                slope_weight=effvec_slope_weight,
                cdf_weight=effvec_cdf_weight,
                amplitude_stat=effvec_amplitude_stat,
            )
            group_distances.append(group_dist)
        if not group_distances:
            return None
        stacked = np.vstack(group_distances)
        return _reduce_efficiency_vector_group_stack(
            stacked,
            group_reduction=effvec_group_reduction,
        )

    # ── z-position arrays for fast matching ──────────────────────────
    dict_z = dict_df[z_cols].to_numpy(dtype=float) if z_cols else None
    data_z = data_df[z_cols].to_numpy(dtype=float) if z_cols else None

    # ── File IDs for self-exclusion ──────────────────────────────────
    join_col = None
    for candidate in ("filename_base", "file_name"):
        if candidate in dict_df.columns and candidate in data_df.columns:
            join_col = candidate
            break
    dict_ids = dict_df[join_col].astype(str).tolist() if join_col else None
    data_ids = data_df[join_col].astype(str).tolist() if join_col else None
    dict_ids_arr = np.asarray(dict_ids, dtype=object) if dict_ids else None

    # ── Dict parameter values as arrays ──────────────────────────────
    dict_param_arrays = {}
    for pc in param_columns:
        dict_param_arrays[pc] = pd.to_numeric(
            dict_df[pc], errors="coerce"
        ).to_numpy(dtype=float)

    # ── Optional strict shared-parameter exclusion ──────────────────
    shared_param_cols: list[str] = []
    shared_param_ignore = set(_normalize_column_spec(shared_parameter_exclusion_ignore))
    shared_exclusion_mode = _resolve_shared_parameter_exclusion_mode(
        shared_parameter_exclusion_mode,
        legacy_flag=bool(exclude_candidates_sharing_parameter_values),
    )
    shared_exclusion_enabled = shared_exclusion_mode in {"partial", "full"}
    if shared_exclusion_enabled:
        raw_cols = _normalize_column_spec(shared_parameter_exclusion_columns)
        if not raw_cols or any(str(c).strip().lower() == "auto" for c in raw_cols):
            raw_cols = [
                str(c)
                for c in param_columns
                if not str(c).startswith("eff_empirical_")
            ]

        seen_cols: set[str] = set()
        for col in raw_cols:
            name = str(col).strip()
            if not name or name in seen_cols or name in shared_param_ignore:
                continue
            if name not in dict_df.columns or name not in data_df.columns:
                continue
            shared_param_cols.append(name)
            seen_cols.add(name)

        if shared_param_cols:
            log.info(
                "Shared-parameter exclusion enabled: mode=%s columns=%s (ignore=%s, atol=%.3g)",
                shared_exclusion_mode,
                shared_param_cols,
                sorted(shared_param_ignore),
                float(shared_parameter_match_atol),
            )
        else:
            log.warning(
                "Shared-parameter exclusion requested but no valid columns resolved; exclusion disabled."
            )
    dict_shared_param_arrays = {
        col: pd.to_numeric(dict_df[col], errors="coerce").to_numpy(dtype=float)
        for col in shared_param_cols
    }
    data_shared_param_arrays = {
        col: pd.to_numeric(data_df[col], errors="coerce").to_numpy(dtype=float)
        for col in shared_param_cols
    }
    param_set_guard_enabled = (
        shared_exclusion_enabled
        and
        "param_set_id" in dict_df.columns
        and "param_set_id" in data_df.columns
        and "param_set_id" not in shared_param_ignore
    )
    dict_param_set_array = (
        pd.to_numeric(dict_df["param_set_id"], errors="coerce").to_numpy(dtype=float)
        if param_set_guard_enabled else None
    )
    data_param_set_array = (
        pd.to_numeric(data_df["param_set_id"], errors="coerce").to_numpy(dtype=float)
        if param_set_guard_enabled else None
    )
    if param_set_guard_enabled:
        log.info("Shared-parameter exclusion guard enabled for 'param_set_id'.")

    density_scaling_all, density_info = _build_density_scaling_for_dictionary(
        dict_df=dict_df,
        dict_feature_matrix=dict_scaled,
        distance_metric=distance_metric,
        dict_z=dict_z,
        density_weighting_cfg=density_weighting_cfg,
    )
    if density_scaling_all is not None:
        density_space = str(density_info.get("space", "?"))
        log.info(
            "Density correction enabled: space=%s k=%d exp=%.3g clip=[%.3g, %.3g]",
            density_space,
            int(
                density_info.get(
                    "effective_k_neighbors",
                    density_info.get("effective_k_neighbors_max", density_info.get("k_neighbors", 0)),
                )
            ),
            float(density_info.get("exponent", np.nan)),
            float(density_info.get("clip_min", np.nan)),
            float(density_info.get("clip_max", np.nan)),
        )
        if density_space == "feature":
            log.info(
                "Density feature-space details: metric=%s z_groups=%s finite_radius=%s",
                density_info.get("distance_metric", distance_metric),
                density_info.get("n_z_groups", "?"),
                density_info.get("n_finite_radius", "?"),
            )
        else:
            log.info(
                "Density details: n_basis=%s finite_radius=%s",
                density_info.get("n_basis", "?"),
                density_info.get("n_finite_radius", "?"),
            )
    elif isinstance(density_weighting_cfg, Mapping):
        log.info("Density correction disabled for this run (%s).", density_info.get("reason", "disabled"))

    eff_sim_param_columns = [pc for pc in param_columns if str(pc).startswith("eff_sim_")]
    flux_param_columns = [pc for pc in param_columns if "flux" in str(pc).lower()]
    param_span_by_name: dict[str, float] = {}
    for pc in param_columns:
        arr = np.asarray(dict_param_arrays[pc], dtype=float)
        finite = arr[np.isfinite(arr)]
        if finite.size < 2:
            param_span_by_name[pc] = 1.0
            continue
        span = float(np.max(finite) - np.min(finite))
        param_span_by_name[pc] = span if np.isfinite(span) and span > 1e-12 else 1.0

    stage2_rate_feature_idx = np.asarray(
        [
            j
            for j, name in enumerate(non_hist_feature_cols)
            if (
                ("rate" in str(name).lower())
                and (not str(name).startswith("eff_empirical_"))
            )
        ],
        dtype=int,
    )
    if stage2_rate_feature_idx.size == 0:
        stage2_rate_feature_idx = np.asarray(base_other_feature_idx, dtype=int)
    is_two_stage_soft_mode = estimation_mode == "two_stage_eff_then_flux"
    is_two_stage_address_mode = estimation_mode == "two_stage_eff_address_then_flux"
    is_two_stage_mode = is_two_stage_soft_mode or is_two_stage_address_mode

    def _resolve_k_use(n_available: int) -> int:
        if n_available <= 0:
            return 0
        if neighbor_selection == "nearest":
            return 1
        if neighbor_selection == "all":
            return int(n_available)
        k_eff = int(neighbor_count) if neighbor_count is not None else int(n_available)
        return min(max(1, k_eff), int(n_available))

    def _select_top_neighbors(
        valid_indices_local: np.ndarray,
        valid_distances_local: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        if len(valid_indices_local) == 0:
            return (
                np.asarray([], dtype=int),
                np.asarray([], dtype=float),
            )
        order_local = np.argsort(valid_distances_local)
        sorted_idx = np.asarray(valid_indices_local[order_local], dtype=int)
        sorted_dist = np.asarray(valid_distances_local[order_local], dtype=float)
        k_use_local = _resolve_k_use(len(sorted_idx))
        return sorted_idx[:k_use_local], sorted_dist[:k_use_local]

    def _build_weights_for_top(
        top_indices_local: np.ndarray,
        top_distances_local: np.ndarray,
    ) -> np.ndarray:
        if len(top_indices_local) == 0:
            return np.asarray([], dtype=float)
        weights_local = _build_neighbor_weights(
            top_distances_local,
            weighting_mode=neighbor_weighting,
            idw_power=inverse_distance_power,
            softmax_temperature=softmax_temperature,
            distance_floor=distance_floor,
        )
        if density_scaling_all is not None:
            density_scaling_top = np.asarray(
                density_scaling_all[top_indices_local], dtype=float
            )
            density_scaling_top = np.where(
                np.isfinite(density_scaling_top), density_scaling_top, 0.0
            )
            weights_local = weights_local * density_scaling_top
        weights_local = np.where(np.isfinite(weights_local), weights_local, 0.0)
        sum_weights = float(np.sum(weights_local))
        if sum_weights > 0.0:
            weights_local /= sum_weights
        return weights_local

    def _aggregate_param_from_top(
        *,
        param_name: str,
        top_indices_local: np.ndarray,
        weights_local: np.ndarray,
        sample_features_local: np.ndarray | None,
        neighbor_features_local: np.ndarray | None,
    ) -> float:
        vals_local = np.asarray(dict_param_arrays[param_name][top_indices_local], dtype=float)
        finite_local = np.isfinite(vals_local)
        if np.sum(finite_local) == 0:
            return np.nan
        w_local = np.asarray(weights_local, dtype=float).copy()
        w_local[~finite_local] = 0.0
        w_sum_local = float(np.sum(w_local))
        if w_sum_local <= 0.0:
            return np.nan
        w_local /= w_sum_local
        if aggregation_mode == "weighted_median":
            return float(_weighted_median(vals_local, w_local))
        if aggregation_mode == "local_linear":
            return float(
                _local_linear_estimate(
                    vals_local,
                    w_local,
                    sample_features=sample_features_local,
                    neighbor_features=neighbor_features_local,
                    parameter_name=param_name,
                    ridge_lambda=local_linear_ridge_lambda,
                )
            )
        return float(np.sum(w_local * np.nan_to_num(vals_local)))

    def _compute_candidate_distances_subset(
        *,
        row_idx: int,
        cand_indices_local: np.ndarray,
        base_feature_idx_local: np.ndarray,
        include_hist: bool,
    ) -> np.ndarray:
        if len(cand_indices_local) == 0:
            return np.asarray([], dtype=float)
        sample_scaled_non_hist_local = (
            data_scaled_base[row_idx, base_feature_idx_local]
            if base_feature_idx_local.size > 0
            else None
        )
        candidates_scaled_non_hist_local = (
            dict_scaled_base[cand_indices_local][:, base_feature_idx_local]
            if base_feature_idx_local.size > 0
            else None
        )
        sample_hist_local = (
            data_hist_matrix[row_idx]
            if (
                include_hist
                and hist_feature_cols_for_distance
                and data_hist_matrix is not None
            )
            else None
        )
        candidates_hist_local = (
            dict_hist_matrix[cand_indices_local]
            if (
                include_hist
                and hist_feature_cols_for_distance
                and dict_hist_matrix is not None
            )
            else None
        )
        # Subset dd weights when using STEP 1.5 artifact
        local_dd_weights = None
        local_dd_p_norm = dd_p_norm
        if _dd_non_hist_weights is not None and base_feature_idx_local.size > 0:
            local_dd_weights = _dd_non_hist_weights[base_feature_idx_local]
        return compute_candidate_distances(
            distance_metric=distance_metric,
            sample_scaled_non_hist=sample_scaled_non_hist_local,
            candidates_scaled_non_hist=candidates_scaled_non_hist_local,
            sample_hist_raw=sample_hist_local,
            candidates_hist_raw=candidates_hist_local,
            histogram_distance_weight=hist_distance_weight,
            histogram_distance_blend_mode=hist_distance_blend_mode,
            histogram_distance_mode=hist_distance_mode,
            histogram_normalization=hist_normalization,
            histogram_p_norm=hist_p_norm,
            histogram_amplitude_weight=hist_amplitude_weight,
            histogram_shape_weight=hist_shape_weight,
            histogram_slope_weight=hist_slope_weight,
            histogram_cdf_weight=hist_cdf_weight,
            histogram_amplitude_stat=hist_amplitude_stat,
            min_valid_non_hist_dims=1,
            dd_weights=local_dd_weights,
            dd_p_norm=local_dd_p_norm,
        )

    def _compute_stage2_candidate_distances(
        *,
        row_idx: int,
        cand_indices_local: np.ndarray,
    ) -> np.ndarray:
        sample_scaled_non_hist_local = (
            data_scaled_base[row_idx, stage2_rate_feature_idx]
            if stage2_rate_feature_idx.size > 0
            else None
        )
        candidates_scaled_non_hist_local = (
            dict_scaled_base[cand_indices_local][:, stage2_rate_feature_idx]
            if stage2_rate_feature_idx.size > 0
            else None
        )

        sample_hist_local = None
        candidates_hist_local = None
        hist_weight_local = float(hist_distance_weight)
        if (
            stage2_use_rate_histogram
            and stage2_hist_matrix_dict is not None
            and stage2_hist_matrix_data is not None
        ):
            sample_hist_local = stage2_hist_matrix_data[row_idx]
            candidates_hist_local = stage2_hist_matrix_dict[cand_indices_local]
            hist_weight_local = float(stage2_hist_distance_weight)
        elif dict_hist_matrix is not None and data_hist_matrix is not None:
            sample_hist_local = data_hist_matrix[row_idx]
            candidates_hist_local = dict_hist_matrix[cand_indices_local]
            hist_weight_local = float(stage2_hist_distance_weight)

        if stage2_rate_feature_idx.size == 0 and sample_hist_local is None:
            return np.full(len(cand_indices_local), np.nan, dtype=float)

        # Stage 2 uses rate-feature weights from STEP 1.5 if available
        local_dd_weights_s2 = None
        local_dd_p_norm_s2 = dd_p_norm
        if _dd_non_hist_weights is not None and stage2_rate_feature_idx.size > 0:
            local_dd_weights_s2 = _dd_non_hist_weights[stage2_rate_feature_idx]
        base_stage2 = compute_candidate_distances(
            distance_metric=distance_metric,
            sample_scaled_non_hist=sample_scaled_non_hist_local,
            candidates_scaled_non_hist=candidates_scaled_non_hist_local,
            sample_hist_raw=sample_hist_local,
            candidates_hist_raw=candidates_hist_local,
            histogram_distance_weight=max(hist_weight_local, 0.0),
            histogram_distance_blend_mode=hist_distance_blend_mode,
            histogram_distance_mode=hist_distance_mode,
            histogram_normalization=hist_normalization,
            histogram_p_norm=hist_p_norm,
            histogram_amplitude_weight=hist_amplitude_weight,
            histogram_shape_weight=hist_shape_weight,
            histogram_slope_weight=hist_slope_weight,
            histogram_cdf_weight=hist_cdf_weight,
            histogram_amplitude_stat=hist_amplitude_stat,
            min_valid_non_hist_dims=1,
            dd_weights=local_dd_weights_s2,
            dd_p_norm=local_dd_p_norm_s2,
        )
        effvec_stage2 = None
        if effvec_stage2_enabled and use_effvec_group_distance:
            effvec_stage2 = _compute_efficiency_vector_candidate_distances(
                row_idx=row_idx,
                cand_indices_local=cand_indices_local,
            )
        return _combine_distance_terms(
            base_distances=base_stage2,
            aux_terms=[
                (
                    effvec_stage2,
                    max(effvec_stage2_weight, 0.0),
                    effvec_distance_blend_mode,
                )
            ],
        )

    # ── Estimate for each dataset entry ──────────────────────────────
    results = []
    n_data = len(data_df)
    shared_excl_rows_affected = 0
    shared_excl_removed_total = 0
    shared_excl_rows_empty = 0
    shared_match_atol = max(float(shared_parameter_match_atol), 0.0)

    for i in range(n_data):
        row_result: dict = {"dataset_index": i}
        if join_col and data_ids:
            row_result["filename_base"] = data_ids[i]
        row_result["feature_space_complete"] = bool(data_complete_mask[i]) if i < len(data_complete_mask) else False
        row_result["estimation_failure_reason"] = None
        row_result["estimation_mode_used"] = "single_stage"
        row_result["stage1_best_distance_eff"] = np.nan
        row_result["stage2_best_distance_rate"] = np.nan
        row_result["stage2_efficiency_conditioning_penalty"] = np.nan
        row_result["n_neighbors_stage1"] = 0
        row_result["n_neighbors_stage2"] = 0
        row_result["stage2_candidates_before_gate"] = 0
        row_result["stage2_candidates_after_gate"] = 0
        row_result["stage2_efficiency_gate_threshold"] = np.nan
        row_result["stage2_efficiency_gate_fallback"] = False
        row_result["efficiency_vector_groups_used"] = int(
            len(effvec_group_payloads) if use_effvec_group_distance else 0
        )
        row_result["stage2_efficiency_vector_groups_used"] = int(
            len(effvec_group_payloads) if (use_effvec_group_distance and effvec_stage2_enabled) else 0
        )
        row_result["stage2_histogram_bins_used"] = int(
            stage2_hist_matrix_dict.shape[1]
            if stage2_hist_matrix_dict is not None
            else (dict_hist_matrix.shape[1] if dict_hist_matrix is not None else 0)
        )
        row_result["best_distance_term_values_json"] = None
        row_result["best_distance_term_shares_json"] = None
        row_result["best_distance_scalar_feature_shares_json"] = None
        row_result["best_distance_group_component_shares_json"] = None
        row_result["best_distance_group_component_within_term_shares_json"] = None
        row_result["best_distance_dominant_term"] = None
        row_result["best_distance_dominant_term_share"] = np.nan
        row_result["best_distance_active_term_count"] = 0
        n_eff_masked = 0
        if out_of_support_eff_mask_non_hist is not None and i < out_of_support_eff_mask_non_hist.shape[0]:
            n_eff_masked = int(np.sum(out_of_support_eff_mask_non_hist[i]))
        row_result["n_eff_features_masked_out_of_support"] = n_eff_masked
        row_result["any_eff_feature_masked_out_of_support"] = bool(n_eff_masked > 0)

        if not row_result["feature_space_complete"]:
            row_result["n_candidates"] = 0
            row_result["n_neighbors_used"] = 0
            row_result["best_distance"] = np.nan
            row_result["estimation_failure_reason"] = "incomplete_feature_space"
            for pc in param_columns:
                row_result[f"est_{pc}"] = np.nan
            results.append(row_result)
            continue

        # Find z-compatible candidates
        if dict_z is not None and data_z is not None:
            z_mask = np.all(
                np.abs(dict_z - data_z[i]) < z_tol, axis=1
            )
        else:
            z_mask = np.ones(len(dict_df), dtype=bool)

        # Exclude same file
        if exclude_same_file and join_col and dict_ids_arr is not None and data_ids:
            same_file = dict_ids_arr == data_ids[i]
            z_mask &= ~same_file

        # Exclude dictionary candidates sharing any selected physical parameter value.
        n_before_shared_excl = int(z_mask.sum())
        n_removed_shared_excl = 0
        if (shared_param_cols or param_set_guard_enabled) and n_before_shared_excl > 0:
            remove_any = np.zeros(len(dict_df), dtype=bool)
            remove_full = np.ones(len(dict_df), dtype=bool)
            n_compared_cols = 0
            for col in shared_param_cols:
                sample_val = data_shared_param_arrays[col][i]
                if not np.isfinite(sample_val):
                    continue
                n_compared_cols += 1
                dict_vals = dict_shared_param_arrays[col]
                atol_eff = _effective_atol(shared_match_atol, float(sample_val))
                same_mask = np.isfinite(dict_vals) & np.isclose(
                    dict_vals,
                    float(sample_val),
                    rtol=0.0,
                    atol=atol_eff,
                )
                if np.any(same_mask):
                    remove_any |= same_mask
                remove_full &= same_mask

            if shared_exclusion_mode == "full":
                remove_basis = remove_full if n_compared_cols > 0 else np.zeros(len(dict_df), dtype=bool)
            else:
                remove_basis = remove_any

            if param_set_guard_enabled and dict_param_set_array is not None and data_param_set_array is not None:
                sample_param_set = data_param_set_array[i]
                if np.isfinite(sample_param_set):
                    atol_eff = _effective_atol(shared_match_atol, float(sample_param_set))
                    same_param_set_mask = np.isfinite(dict_param_set_array) & np.isclose(
                        dict_param_set_array,
                        float(sample_param_set),
                        rtol=0.0,
                        atol=atol_eff,
                    )
                    if np.any(same_param_set_mask):
                        remove_basis |= same_param_set_mask

            if np.any(remove_basis):
                remove_in_candidates = z_mask & remove_basis
                n_removed_shared_excl = int(np.sum(remove_in_candidates))
                if n_removed_shared_excl > 0:
                    z_mask[remove_in_candidates] = False
                    shared_excl_rows_affected += 1
                    shared_excl_removed_total += n_removed_shared_excl
                    if not np.any(z_mask):
                        shared_excl_rows_empty += 1

        if shared_param_cols or param_set_guard_enabled:
            row_result["n_candidates_before_shared_param_exclusion"] = n_before_shared_excl
            row_result["n_candidates_removed_shared_param_exclusion"] = n_removed_shared_excl

        cand_indices = np.where(z_mask)[0]
        row_result["n_candidates"] = len(cand_indices)

        if len(cand_indices) == 0:
            # No candidates — set all estimates to NaN
            for pc in param_columns:
                row_result[f"est_{pc}"] = np.nan
            row_result["best_distance"] = np.nan
            row_result["estimation_failure_reason"] = "no_candidates"
            results.append(row_result)
            continue

        # Compute feature-space distances (base features + optional histogram shape).
        sample_scaled_non_hist = data_scaled_base[i] if non_hist_feature_idx else None
        cand_scaled_non_hist = dict_scaled_base[cand_indices] if non_hist_feature_idx else None
        base_distances = _compute_non_hist_base_distances(
            distance_metric=distance_metric,
            sample_scaled_non_hist=sample_scaled_non_hist,
            candidates_scaled_non_hist=cand_scaled_non_hist,
            min_valid_non_hist_dims=1,
            dd_weights=_dd_non_hist_weights,
            dd_p_norm=dd_p_norm,
        )
        sample_hist_raw = (
            data_hist_matrix[i] if (hist_feature_cols_for_distance and data_hist_matrix is not None) else None
        )
        cand_hist_raw = (
            dict_hist_matrix[cand_indices] if (hist_feature_cols_for_distance and dict_hist_matrix is not None) else None
        )
        hist_distances = None
        if sample_hist_raw is not None and cand_hist_raw is not None:
            hist_distances = _histogram_distance_many(
                np.asarray(sample_hist_raw, dtype=float),
                np.asarray(cand_hist_raw, dtype=float),
                distance=hist_distance_mode,
                normalization=hist_normalization,
                p_norm=hist_p_norm,
                amplitude_weight=hist_amplitude_weight,
                shape_weight=hist_shape_weight,
                slope_weight=hist_slope_weight,
                cdf_weight=hist_cdf_weight,
                amplitude_stat=hist_amplitude_stat,
            )
        effvec_distances = None
        if effvec_distance_enabled and use_effvec_group_distance:
            effvec_distances = _compute_efficiency_vector_candidate_distances(
                row_idx=i,
                cand_indices_local=cand_indices,
            )
        extra_group_aux_terms: list[tuple[str, np.ndarray | None, float, str]] = []
        if extra_group_terms:
            for term in extra_group_terms:
                group_name = str(term.get("name", "")).strip()
                if not group_name:
                    continue
                group_kind = str(term.get("kind", "ordered_vector")).strip().lower()
                group_cfg = term.get("distance_cfg", {})
                if not isinstance(group_cfg, Mapping):
                    group_cfg = {}
                group_dict_matrix = np.asarray(term.get("dict_matrix", []), dtype=float)
                group_data_matrix = np.asarray(term.get("data_matrix", []), dtype=float)
                if (
                    group_dict_matrix.ndim != 2
                    or group_data_matrix.ndim != 2
                    or i >= group_data_matrix.shape[0]
                    or len(cand_indices) == 0
                    or np.max(cand_indices) >= group_dict_matrix.shape[0]
                ):
                    continue
                sample_vec = np.asarray(group_data_matrix[i], dtype=float)
                cand_vec = np.asarray(group_dict_matrix[cand_indices], dtype=float)
                if sample_vec.ndim != 1 or cand_vec.ndim != 2 or cand_vec.shape[1] != sample_vec.size:
                    continue
                if group_kind == "rate_histogram":
                    group_dist = _histogram_distance_many(
                        sample_vec,
                        cand_vec,
                        distance=str(group_cfg.get("distance", "ordered_vector_lp")),
                        normalization=str(group_cfg.get("normalization", "unit_sum")),
                        p_norm=float(group_cfg.get("p_norm", 1.0)),
                        amplitude_weight=float(group_cfg.get("amplitude_weight", 0.0)),
                        shape_weight=float(group_cfg.get("shape_weight", 0.0)),
                        slope_weight=float(group_cfg.get("slope_weight", 0.0)),
                        cdf_weight=float(group_cfg.get("cdf_weight", 1.0)),
                        amplitude_stat=str(group_cfg.get("amplitude_stat", "sum")),
                    )
                else:
                    group_dist = _ordered_vector_distance_many(
                        sample_vec=sample_vec,
                        candidates_vec=cand_vec,
                        normalization=str(group_cfg.get("normalization", "none")),
                        p_norm=float(group_cfg.get("p_norm", 2.0)),
                        amplitude_weight=float(group_cfg.get("amplitude_weight", 0.0)),
                        shape_weight=float(group_cfg.get("shape_weight", 1.0)),
                        slope_weight=float(group_cfg.get("slope_weight", 0.0)),
                        cdf_weight=float(group_cfg.get("cdf_weight", 0.0)),
                        amplitude_stat=str(group_cfg.get("amplitude_stat", "mean")),
                        min_valid_bins=max(int(term.get("min_valid_bins", 1)), 1),
                    )
                extra_group_aux_terms.append(
                    (
                        group_name,
                        np.asarray(group_dist, dtype=float),
                        float(term.get("weight", 0.0)),
                        str(term.get("blend_mode", "normalized")),
                    )
                )
        aux_terms_for_distance: list[tuple[str, np.ndarray | None, float, str]] = [
            (
                "rate_histogram",
                hist_distances,
                max(float(hist_distance_weight), 0.0),
                hist_distance_blend_mode,
            ),
            (
                "efficiency_vectors",
                effvec_distances,
                max(float(effvec_distance_weight), 0.0),
                effvec_distance_blend_mode,
            ),
        ]
        aux_terms_for_distance.extend(extra_group_aux_terms)
        distances, distance_term_arrays = _combine_distance_terms_with_breakdown(
            base_distances=base_distances,
            aux_terms=aux_terms_for_distance,
        )

        # Handle NaN distances
        valid = np.isfinite(distances)
        if valid.sum() == 0:
            for pc in param_columns:
                row_result[f"est_{pc}"] = np.nan
            row_result["best_distance"] = np.nan
            row_result["estimation_failure_reason"] = "no_finite_distances"
            results.append(row_result)
            continue

        valid_indices = cand_indices[valid]
        valid_distances = distances[valid]

        # Sort by distance (ascending = best first)
        order = np.argsort(valid_distances)
        valid_indices = valid_indices[order]
        valid_distances = valid_distances[order]

        best_j = int(valid_indices[0])
        row_result["best_distance"] = float(valid_distances[0])

        # Feature-group diagnostics at the best dictionary match.
        row_result["best_distance_base_l2"] = np.nan
        row_result["best_distance_base_l2_eff_empirical"] = np.nan
        row_result["best_distance_base_l2_tt_rates"] = np.nan
        row_result["best_distance_base_l2_other"] = np.nan
        row_result["best_distance_base_share_eff_empirical"] = np.nan
        row_result["best_distance_base_share_tt_rates"] = np.nan
        row_result["best_distance_base_share_other"] = np.nan
        row_result["best_distance_non_hist_finite_dims"] = 0
        row_result["best_distance_hist_emd"] = np.nan
        row_result["best_distance_rate_histogram"] = np.nan
        row_result["best_distance_efficiency_vector"] = np.nan

        if non_hist_feature_idx:
            sample_base_vec = np.asarray(data_scaled_base[i], dtype=float)
            best_base_vec = np.asarray(dict_scaled_base[best_j], dtype=float)
            finite_base = np.isfinite(sample_base_vec) & np.isfinite(best_base_vec)
            row_result["best_distance_non_hist_finite_dims"] = int(np.sum(finite_base))
            if np.any(finite_base):
                delta = np.zeros_like(sample_base_vec, dtype=float)
                delta[finite_base] = sample_base_vec[finite_base] - best_base_vec[finite_base]

                def _group_l2(group_idx: np.ndarray) -> float:
                    if group_idx.size == 0:
                        return 0.0
                    use = group_idx[finite_base[group_idx]]
                    if use.size == 0:
                        return np.nan
                    vals = delta[use]
                    return float(np.sqrt(np.sum(vals * vals)))

                base_l2 = float(np.sqrt(np.sum(delta[finite_base] * delta[finite_base])))
                eff_l2 = _group_l2(base_eff_feature_idx)
                tt_l2 = _group_l2(base_tt_feature_idx)
                other_l2 = _group_l2(base_other_feature_idx)

                row_result["best_distance_base_l2"] = base_l2
                row_result["best_distance_base_l2_eff_empirical"] = eff_l2
                row_result["best_distance_base_l2_tt_rates"] = tt_l2
                row_result["best_distance_base_l2_other"] = other_l2

                denom = base_l2 * base_l2
                if np.isfinite(denom) and denom > 0.0:
                    row_result["best_distance_base_share_eff_empirical"] = (
                        float(eff_l2 * eff_l2 / denom) if np.isfinite(eff_l2) else np.nan
                    )
                    row_result["best_distance_base_share_tt_rates"] = (
                        float(tt_l2 * tt_l2 / denom) if np.isfinite(tt_l2) else np.nan
                    )
                    row_result["best_distance_base_share_other"] = (
                        float(other_l2 * other_l2 / denom) if np.isfinite(other_l2) else np.nan
                    )

        if hist_feature_cols_for_distance and data_hist_matrix is not None and dict_hist_matrix is not None:
            hist_pair = _histogram_distance_many(
                np.asarray(data_hist_matrix[i], dtype=float),
                np.asarray(dict_hist_matrix[best_j : best_j + 1], dtype=float),
                distance=hist_distance_mode,
                normalization=hist_normalization,
                p_norm=hist_p_norm,
                amplitude_weight=hist_amplitude_weight,
                shape_weight=hist_shape_weight,
                slope_weight=hist_slope_weight,
                cdf_weight=hist_cdf_weight,
                amplitude_stat=hist_amplitude_stat,
            )
            if hist_pair.size:
                hist_value = float(hist_pair[0]) if np.isfinite(hist_pair[0]) else np.nan
                row_result["best_distance_hist_emd"] = hist_value
                row_result["best_distance_rate_histogram"] = hist_value
        if effvec_distance_enabled and use_effvec_group_distance:
            effvec_pair = _compute_efficiency_vector_candidate_distances(
                row_idx=i,
                cand_indices_local=np.asarray([best_j], dtype=int),
            )
            if effvec_pair is not None and effvec_pair.size:
                row_result["best_distance_efficiency_vector"] = (
                    float(effvec_pair[0]) if np.isfinite(effvec_pair[0]) else np.nan
                )

        best_term_values: dict[str, float] = {}
        for term_name, term_array in distance_term_arrays.items():
            values = np.asarray(term_array, dtype=float)
            if values.shape[0] != len(cand_indices):
                continue
            best_term = values[valid][order][0]
            if np.isfinite(best_term) and best_term >= 0.0:
                best_term_values[str(term_name)] = float(best_term)
        if best_term_values:
            total_term_value = float(sum(best_term_values.values()))
            if np.isfinite(total_term_value) and total_term_value > 0.0:
                best_term_shares = {
                    name: float(value / total_term_value)
                    for name, value in best_term_values.items()
                    if np.isfinite(value) and value >= 0.0
                }
                row_result["best_distance_term_values_json"] = json.dumps(
                    best_term_values,
                    sort_keys=True,
                )
                row_result["best_distance_term_shares_json"] = json.dumps(
                    best_term_shares,
                    sort_keys=True,
                )
                row_result["best_distance_active_term_count"] = int(len(best_term_shares))

                group_component_total_shares: dict[str, float] = {}
                group_component_within_term_shares: dict[str, float] = {}
                hist_term_share = float(best_term_shares.get("rate_histogram", 0.0))
                if (
                    hist_term_share > 0.0
                    and hist_feature_cols_for_distance
                    and data_hist_matrix is not None
                    and dict_hist_matrix is not None
                ):
                    hist_total, hist_within = _histogram_component_share_breakdown(
                        sample_hist=np.asarray(data_hist_matrix[i], dtype=float),
                        candidate_hist=np.asarray(dict_hist_matrix[best_j], dtype=float),
                        feature_names=hist_feature_cols_for_distance,
                        term_share_of_total=hist_term_share,
                        distance=hist_distance_mode,
                        normalization=hist_normalization,
                        p_norm=hist_p_norm,
                        amplitude_weight=hist_amplitude_weight,
                        shape_weight=hist_shape_weight,
                        slope_weight=hist_slope_weight,
                        cdf_weight=hist_cdf_weight,
                        amplitude_stat=hist_amplitude_stat,
                    )
                    group_component_total_shares.update(hist_total)
                    group_component_within_term_shares.update(hist_within)

                effvec_term_share = float(best_term_shares.get("efficiency_vectors", 0.0))
                if effvec_term_share > 0.0 and effvec_distance_enabled and use_effvec_group_distance:
                    eff_total, eff_within = _efficiency_vector_component_share_breakdown(
                        payloads=effvec_group_payloads,
                        row_idx=i,
                        candidate_idx=best_j,
                        fiducial=effvec_fiducial,
                        uncertainty_floor=effvec_uncertainty_floor,
                        min_valid_bins=effvec_min_valid_bins,
                        term_share_of_total=effvec_term_share,
                        normalization=effvec_normalization,
                        p_norm=effvec_p_norm,
                        amplitude_weight=effvec_amplitude_weight,
                        shape_weight=effvec_shape_weight,
                        slope_weight=effvec_slope_weight,
                        cdf_weight=effvec_cdf_weight,
                        amplitude_stat=effvec_amplitude_stat,
                        group_reduction=effvec_group_reduction,
                    )
                    group_component_total_shares.update(eff_total)
                    group_component_within_term_shares.update(eff_within)

                if group_component_total_shares:
                    row_result["best_distance_group_component_shares_json"] = json.dumps(
                        group_component_total_shares,
                        sort_keys=True,
                    )
                if group_component_within_term_shares:
                    row_result["best_distance_group_component_within_term_shares_json"] = json.dumps(
                        group_component_within_term_shares,
                        sort_keys=True,
                    )

                dominant_term, dominant_share = max(
                    best_term_shares.items(),
                    key=lambda item: (float(item[1]), str(item[0])),
                )
                row_result["best_distance_dominant_term"] = str(dominant_term)
                row_result["best_distance_dominant_term_share"] = float(dominant_share)

                scalar_term_value = float(best_term_values.get("scalar_base", np.nan))
                if np.isfinite(scalar_term_value) and scalar_term_value > 0.0 and non_hist_feature_idx:
                    scalar_feature_shares = _scalar_feature_total_share_breakdown(
                        feature_names=non_hist_feature_cols,
                        sample_values=sample_scaled_non_hist,
                        candidate_values=np.asarray(dict_scaled_base[best_j], dtype=float),
                        scalar_term_value=scalar_term_value,
                        total_distance_value=total_term_value,
                        distance_metric=distance_metric,
                        dd_weights=_dd_non_hist_weights,
                        dd_p_norm=dd_p_norm,
                    )
                    if scalar_feature_shares:
                        row_result["best_distance_scalar_feature_shares_json"] = json.dumps(
                            scalar_feature_shares,
                            sort_keys=True,
                        )

        # Select neighborhood according to inverse-mapping strategy.
        top_indices, top_distances = _select_top_neighbors(valid_indices, valid_distances)
        row_result["n_neighbors_used"] = int(len(top_indices))

        if len(top_indices) == 0:
            for pc in param_columns:
                row_result[f"est_{pc}"] = np.nan
            row_result["estimation_failure_reason"] = "no_neighbors_selected"
        elif len(top_indices) == 1 or top_distances[0] <= distance_floor:
            # Nearest-only (or exact match)
            best_j = top_indices[0]
            for pc in param_columns:
                row_result[f"est_{pc}"] = float(dict_param_arrays[pc][best_j])
        else:
            weights = _build_weights_for_top(top_indices, top_distances)
            sum_weights = float(np.sum(weights))
            if sum_weights <= 0.0:
                best_j = top_indices[0]
                for pc in param_columns:
                    row_result[f"est_{pc}"] = float(dict_param_arrays[pc][best_j])
                row_result["estimation_failure_reason"] = "invalid_neighbor_weights_fallback_to_nearest"
                results.append(row_result)
                if (i + 1) % 200 == 0 or i == n_data - 1:
                    log.info("  Estimated %d / %d", i + 1, n_data)
                continue
            sample_base_for_local = (
                data_local_linear_features[i]
                if data_local_linear_features is not None
                else (data_scaled_base[i] if non_hist_feature_idx else None)
            )
            top_base_for_local = (
                dict_local_linear_features[top_indices]
                if dict_local_linear_features is not None
                else (dict_scaled_base[top_indices] if non_hist_feature_idx else None)
            )

            for pc in param_columns:
                row_result[f"est_{pc}"] = _aggregate_param_from_top(
                    param_name=pc,
                    top_indices_local=top_indices,
                    weights_local=weights,
                    sample_features_local=sample_base_for_local,
                    neighbor_features_local=top_base_for_local,
                )

        if (
            is_two_stage_mode
            and len(eff_sim_param_columns) > 0
            and len(flux_param_columns) > 0
            and base_eff_feature_idx.size > 0
        ):
            stage1_eff_estimates: dict[str, float] = {}
            stage1_distances = _compute_candidate_distances_subset(
                row_idx=i,
                cand_indices_local=cand_indices,
                base_feature_idx_local=np.asarray(base_eff_feature_idx, dtype=int),
                include_hist=False,
            )
            valid_stage1 = np.isfinite(stage1_distances)
            if np.any(valid_stage1):
                stage1_indices = cand_indices[valid_stage1]
                stage1_dist = stage1_distances[valid_stage1]
                top1_indices, top1_distances = _select_top_neighbors(stage1_indices, stage1_dist)
                if len(top1_indices) > 0:
                    row_result["n_neighbors_stage1"] = int(len(top1_indices))
                    row_result["stage1_best_distance_eff"] = float(np.min(top1_distances))
                    if len(top1_indices) == 1 or top1_distances[0] <= distance_floor:
                        idx1 = int(top1_indices[0])
                        for pc in eff_sim_param_columns:
                            est_val = float(dict_param_arrays[pc][idx1])
                            row_result[f"est_{pc}"] = est_val
                            stage1_eff_estimates[pc] = est_val
                    else:
                        w1 = _build_weights_for_top(top1_indices, top1_distances)
                        if float(np.sum(w1)) > 0.0:
                            sample_eff_local = data_scaled_base[i, base_eff_feature_idx]
                            top_eff_local = dict_scaled_base[top1_indices][:, base_eff_feature_idx]
                            for pc in eff_sim_param_columns:
                                est_val = _aggregate_param_from_top(
                                    param_name=pc,
                                    top_indices_local=top1_indices,
                                    weights_local=w1,
                                    sample_features_local=sample_eff_local,
                                    neighbor_features_local=top_eff_local,
                                )
                                row_result[f"est_{pc}"] = est_val
                                if np.isfinite(est_val):
                                    stage1_eff_estimates[pc] = float(est_val)

            if stage1_eff_estimates:
                stage2_distances = _compute_stage2_candidate_distances(
                    row_idx=i,
                    cand_indices_local=cand_indices,
                )
                valid_stage2 = np.isfinite(stage2_distances)
                if np.any(valid_stage2):
                    stage2_indices = cand_indices[valid_stage2]
                    stage2_dist = stage2_distances[valid_stage2]
                    row_result["stage2_candidates_before_gate"] = int(len(stage2_indices))
                    stage2_penalty = np.zeros(len(stage2_indices), dtype=float)
                    n_eff_used = 0
                    for pc, est_val in stage1_eff_estimates.items():
                        if not np.isfinite(est_val):
                            continue
                        span = float(param_span_by_name.get(pc, 1.0))
                        span = span if np.isfinite(span) and span > 1e-12 else 1.0
                        cand_vals = np.asarray(dict_param_arrays[pc][stage2_indices], dtype=float)
                        finite_eff = np.isfinite(cand_vals)
                        if not np.any(finite_eff):
                            continue
                        comp = np.zeros(len(stage2_indices), dtype=float)
                        comp[finite_eff] = ((cand_vals[finite_eff] - float(est_val)) / span) ** 2
                        stage2_penalty += comp
                        n_eff_used += 1
                    if n_eff_used > 0:
                        stage2_penalty = np.sqrt(stage2_penalty / float(n_eff_used))
                    else:
                        stage2_penalty[:] = 0.0
                    row_result["stage2_efficiency_gate_threshold"] = (
                        float(stage2_eff_gate_max) if is_two_stage_address_mode else np.nan
                    )

                    if is_two_stage_address_mode and len(stage2_indices) > 0 and n_eff_used > 0:
                        gate_mask = np.isfinite(stage2_penalty) & (
                            stage2_penalty <= float(stage2_eff_gate_max)
                        )
                        min_keep = min(
                            max(1, int(stage2_eff_gate_min_candidates)),
                            int(len(stage2_indices)),
                        )
                        if int(np.sum(gate_mask)) < min_keep:
                            finite_pen = np.isfinite(stage2_penalty)
                            if np.any(finite_pen):
                                finite_pos = np.where(finite_pen)[0]
                                order_gate = np.argsort(stage2_penalty[finite_pos])
                                keep_pos = finite_pos[order_gate][:min_keep]
                            else:
                                keep_pos = np.arange(min_keep, dtype=int)
                            gate_mask = np.zeros(len(stage2_indices), dtype=bool)
                            gate_mask[keep_pos] = True
                            row_result["stage2_efficiency_gate_fallback"] = True
                        stage2_indices = stage2_indices[gate_mask]
                        stage2_dist = stage2_dist[gate_mask]
                        stage2_penalty = stage2_penalty[gate_mask]

                    row_result["stage2_candidates_after_gate"] = int(len(stage2_indices))
                    if len(stage2_indices) > 0:
                        stage2_dist_combined = stage2_dist + float(stage2_eff_conditioning_weight) * stage2_penalty
                        order2 = np.argsort(stage2_dist_combined)
                        stage2_indices = stage2_indices[order2]
                        stage2_dist_combined = stage2_dist_combined[order2]
                        stage2_penalty = stage2_penalty[order2]
                        top2_indices, top2_distances = _select_top_neighbors(stage2_indices, stage2_dist_combined)
                        if len(top2_indices) > 0:
                            row_result["estimation_mode_used"] = (
                                "two_stage_eff_address_then_flux"
                                if is_two_stage_address_mode
                                else "two_stage_eff_then_flux"
                            )
                            row_result["n_neighbors_stage2"] = int(len(top2_indices))
                            row_result["stage2_best_distance_rate"] = float(np.min(top2_distances))
                            row_result["stage2_efficiency_conditioning_penalty"] = float(stage2_penalty[0])
                            if len(top2_indices) == 1 or top2_distances[0] <= distance_floor:
                                idx2 = int(top2_indices[0])
                                for pc in flux_param_columns:
                                    row_result[f"est_{pc}"] = float(dict_param_arrays[pc][idx2])
                            else:
                                w2 = _build_weights_for_top(top2_indices, top2_distances)
                                if float(np.sum(w2)) > 0.0:
                                    sample_rate_local = (
                                        data_scaled_base[i, stage2_rate_feature_idx]
                                        if stage2_rate_feature_idx.size > 0
                                        else None
                                    )
                                    top_rate_local = (
                                        dict_scaled_base[top2_indices][:, stage2_rate_feature_idx]
                                        if stage2_rate_feature_idx.size > 0
                                        else None
                                    )
                                    for pc in flux_param_columns:
                                        row_result[f"est_{pc}"] = _aggregate_param_from_top(
                                            param_name=pc,
                                            top_indices_local=top2_indices,
                                            weights_local=w2,
                                            sample_features_local=sample_rate_local,
                                            neighbor_features_local=top_rate_local,
                                        )

        results.append(row_result)

        if (i + 1) % 200 == 0 or i == n_data - 1:
            log.info("  Estimated %d / %d", i + 1, n_data)

    if shared_param_cols or param_set_guard_enabled:
        log.info(
            "Shared-parameter exclusion summary: mode=%s rows_affected=%d/%d, removed_candidates_total=%d, rows_with_zero_candidates_after_exclusion=%d",
            shared_exclusion_mode,
            shared_excl_rows_affected,
            n_data,
            shared_excl_removed_total,
            shared_excl_rows_empty,
        )

    result_df = pd.DataFrame(results)
    result_df.attrs["efficiency_feature_out_of_support_masking"] = out_of_support_eff_info
    result_df.attrs["feature_space_completeness"] = {
        "dictionary": dictionary_feature_space_completeness,
        "dataset": dataset_feature_space_completeness,
    }

    log.info(
        "Estimator completeness summary: dictionary kept %d/%d complete rows; dataset incomplete rows skipped=%d/%d.",
        int(dictionary_feature_space_completeness.get("rows_kept", len(dict_df))),
        int(dictionary_feature_space_completeness.get("input_rows", len(dict_df))),
        int(dataset_feature_space_completeness.get("rows_removed", 0)),
        int(dataset_feature_space_completeness.get("input_rows", len(data_df))),
    )

    if "best_distance_base_share_tt_rates" in result_df.columns:
        tt_vals = pd.to_numeric(
            result_df["best_distance_base_share_tt_rates"], errors="coerce"
        ).to_numpy(dtype=float)
        eff_vals = pd.to_numeric(
            result_df["best_distance_base_share_eff_empirical"], errors="coerce"
        ).to_numpy(dtype=float)
        other_vals = pd.to_numeric(
            result_df["best_distance_base_share_other"], errors="coerce"
        ).to_numpy(dtype=float)
        finite_any = np.isfinite(tt_vals) | np.isfinite(eff_vals) | np.isfinite(other_vals)
        if np.any(finite_any):
            tt_med = float(np.nanmedian(tt_vals))
            eff_med = float(np.nanmedian(eff_vals))
            other_med = float(np.nanmedian(other_vals))
            log.info(
                "Best-match non-hist distance share medians: eff=%.3f tt=%.3f other=%.3f",
                eff_med,
                tt_med,
                other_med,
            )
            if tt_med > 0.60:
                log.warning(
                    "TT-rate features dominate non-hist best-match distance (median share=%.3f). "
                    "This can re-couple flux and efficiency in inverse mapping.",
                    tt_med,
                )

    return result_df
