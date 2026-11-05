#!/usr/bin/env python3
"""
Shared runtime helpers for STEP 2/3/4 inference entrypoints.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from estimate_parameters import (
    build_step15_runtime_inverse_mapping_cfg,
    load_distance_definition,
    require_runtime_distance_definition,
)


def load_selected_feature_columns_artifact(path: str | Path) -> list[str]:
    """Load the strict selected-feature artifact produced upstream."""
    artifact_path = Path(path)
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    raw_cols = payload.get("selected_feature_columns", [])
    if not isinstance(raw_cols, list):
        raise ValueError(f"selected_feature_columns is not a list in {artifact_path}")
    selected = [str(col).strip() for col in raw_cols if str(col).strip()]
    if not selected:
        raise ValueError(f"No selected_feature_columns found in {artifact_path}")
    return selected


def require_selected_feature_columns_present(
    selected_feature_columns: list[str],
    *,
    dict_df: pd.DataFrame,
    data_df: pd.DataFrame,
    context_label: str,
    right_label: str = "dataset",
) -> list[str]:
    """Enforce exact selected-feature alignment between dictionary and runtime data."""
    if not selected_feature_columns:
        raise ValueError(f"{context_label} selected feature artifact is empty.")

    missing_in_dict = [str(col) for col in selected_feature_columns if str(col) not in dict_df.columns]
    missing_in_data = [str(col) for col in selected_feature_columns if str(col) not in data_df.columns]
    if missing_in_dict or missing_in_data:
        details: list[str] = []
        if missing_in_dict:
            details.append(
                "missing in dictionary: "
                + ", ".join(missing_in_dict[:50])
                + (" ..." if len(missing_in_dict) > 50 else "")
            )
        if missing_in_data:
            details.append(
                f"missing in {right_label}: "
                + ", ".join(missing_in_data[:50])
                + (" ..." if len(missing_in_data) > 50 else "")
            )
        raise ValueError(
            f"{context_label} selected feature space does not match the provided dictionary/{right_label} tables; "
            + "; ".join(details)
        )
    return [str(col) for col in selected_feature_columns]


def parse_column_spec(value: object) -> list[str]:
    """Parse config values that may represent a column list."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() == "auto":
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        return [part.strip() for part in text.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value).strip()
    return [text] if text and text.lower() != "auto" else []


def resolve_estimation_parameter_columns(
    *,
    dictionary_df: pd.DataFrame,
    configured_columns: object = None,
    default_columns: list[str] | None = None,
    default_priority: list[str] | None = None,
    parameter_predicate: Callable[[str], bool] | None = None,
    logger: logging.Logger | None = None,
) -> list[str]:
    """Resolve parameter columns explicitly first, then by dictionary fallback."""
    requested = parse_column_spec(configured_columns)
    if not requested and isinstance(default_columns, list):
        requested = [str(c).strip() for c in default_columns if str(c).strip()]
    if not requested and isinstance(default_priority, list):
        requested = [str(c).strip() for c in default_priority if str(c).strip()]

    resolved: list[str] = []
    missing: list[str] = []
    for col in requested:
        if col in dictionary_df.columns and col not in resolved:
            resolved.append(col)
        elif col not in missing:
            missing.append(col)
    if missing and logger is not None:
        logger.warning(
            "Ignoring estimated-parameter columns not present in the dictionary: %s",
            missing,
        )
    if resolved:
        return resolved

    fallback: list[str] = []
    predicate = parameter_predicate or (lambda _name: True)
    for col in sorted(dictionary_df.columns):
        if predicate(str(col)) and col not in fallback:
            fallback.append(str(col))
    return fallback


def resolve_runtime_distance_and_inverse_mapping(
    *,
    feature_columns: list[str],
    inverse_mapping_cfg: dict,
    interpolation_k: int | None,
    context_label: str,
    distance_definition_path: str | Path,
    logger: logging.Logger,
    distance_definition_override: object = None,
) -> tuple[dict, dict, int | None]:
    """Load the STEP 1.5 contract and derive the runtime inverse-map config."""
    dd = None
    override = distance_definition_override

    if isinstance(override, (str, Path)) and str(override).strip():
        try:
            dd = load_distance_definition(feature_columns, path=Path(override))
        except Exception:
            logger.warning("Failed to load distance_definition from path: %s", override)
            dd = None

    if isinstance(override, dict) and override:
        if list(override.get("feature_columns", [])) == list(feature_columns):
            dd = dict(override)
            dd["available"] = True
        else:
            logger.warning(
                "Config distance_definition.feature_columns does not match selected feature columns; ignoring override."
            )

    if dd is None:
        dd = load_distance_definition(feature_columns, path=Path(distance_definition_path))

    if dd.get("available"):
        n_active_groups = int(
            sum(float(v) > 0.0 for v in (dd.get("group_weights", {}) or {}).values())
        )
        logger.info(
            "%s distance definition loaded: %s (p=%.1f, k=%d, λ=%.2g, scalar_active=%d/%d, grouped_active=%d)",
            context_label,
            dd.get("selected_mode"),
            float(dd["p_norm"]),
            int(dd["optimal_k"]),
            float(dd["optimal_lambda"]),
            int(np.sum(dd["weights"] > 0)),
            len(feature_columns),
            n_active_groups,
        )
        if interpolation_k is None or interpolation_k != int(dd["optimal_k"]):
            logger.info(
                "Overriding interpolation_k %s → %d from distance definition.",
                interpolation_k,
                int(dd["optimal_k"]),
            )
            interpolation_k = int(dd["optimal_k"])
    else:
        logger.error("%s distance definition not available: %s", context_label, dd.get("reason"))

    dd = require_runtime_distance_definition(
        dd,
        context_label=context_label,
        require_exact_alignment=True,
    )

    runtime_inverse_mapping_cfg = build_step15_runtime_inverse_mapping_cfg(
        inverse_mapping_cfg=inverse_mapping_cfg,
        interpolation_k=interpolation_k,
        distance_definition=dd,
    )
    return dd, runtime_inverse_mapping_cfg, interpolation_k


def log_runtime_inverse_mapping_summary(
    logger: logging.Logger,
    inverse_mapping_cfg: dict,
    *,
    prefix: str = "STEP 1.5 runtime inverse mapping",
) -> None:
    """Log the runtime inverse-map contract with consistent formatting."""
    neighbor_count = inverse_mapping_cfg.get("neighbor_count")
    neighbor_count_text = "all" if neighbor_count is None else str(int(neighbor_count))
    logger.info(
        "%s: selection=%s k=%s weighting=%s idw_power=%.1f aggregation=%s",
        prefix,
        inverse_mapping_cfg.get("neighbor_selection"),
        neighbor_count_text,
        inverse_mapping_cfg.get("weighting"),
        float(inverse_mapping_cfg.get("inverse_distance_power", 2.0)),
        inverse_mapping_cfg.get("aggregation"),
    )
