#!/usr/bin/env python3
"""
Shared helpers to load and apply STEP 1.3 empirical-efficiency polynomial fits.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

EFF_PRODUCT_SUFFIX_TO_PLANES: dict[str, tuple[int, ...]] = {
    "4planes": (1, 2, 3, 4),
    "123": (1, 2, 3),
    "124": (1, 2, 4),
    "134": (1, 3, 4),
    "234": (2, 3, 4),
    "12": (1, 2),
    "13": (1, 3),
    "14": (1, 4),
    "23": (2, 3),
    "24": (2, 4),
    "34": (3, 4),
}

POLY_CORRECTED_EFF_COL_TEMPLATE = "eff_poly_corrected_{plane}"
POLY_CORRECTED_EFFPROD_COL_TEMPLATE = "efficiency_product_poly_corrected_{suffix}"


def _safe_float(value: object) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if np.isfinite(out):
        return float(out)
    return None


def _coerce_coefficients(raw: object) -> list[float] | None:
    if isinstance(raw, dict):
        raw = raw.get("coefficients_desc", raw.get("coefficients"))
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    coeffs: list[float] = []
    for value in raw:
        coeff = _safe_float(value)
        if coeff is None:
            return None
        coeffs.append(coeff)
    return coeffs if len(coeffs) >= 2 else None


def _normalize_fit_model(
    raw_model: object,
    *,
    plane: int,
) -> dict[str, object] | None:
    coeffs = _coerce_coefficients(raw_model)
    if coeffs is None:
        return None
    if isinstance(raw_model, dict):
        order_used_raw = raw_model.get("order_used", len(coeffs) - 1)
        try:
            order_used = int(order_used_raw)
        except (TypeError, ValueError):
            order_used = len(coeffs) - 1
        return {
            "plane": int(plane),
            "status": str(raw_model.get("status", "ok")),
            "coefficients_desc": coeffs,
            "order_used": int(order_used),
            "empirical_min": _safe_float(raw_model.get("empirical_min")),
            "empirical_max": _safe_float(raw_model.get("empirical_max")),
            "clip_fit_output": bool(raw_model.get("clip_fit_output", True)),
        }
    return {
        "plane": int(plane),
        "status": "ok",
        "coefficients_desc": coeffs,
        "order_used": int(len(coeffs) - 1),
        "empirical_min": None,
        "empirical_max": None,
        "clip_fit_output": True,
    }


def load_efficiency_fit_models(
    summary_path: Path,
) -> tuple[dict[int, dict[str, object]], str, dict]:
    """Load STEP 1.3 polynomial efficiency-fit metadata from build_summary.json."""
    if not summary_path.exists():
        return ({}, f"missing:{summary_path}", {})
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ({}, f"invalid_json:{exc}", {})

    out: dict[int, dict[str, object]] = {}
    efficiency_fit = payload.get("efficiency_fit", {})
    models_block = efficiency_fit.get("models", {}) if isinstance(efficiency_fit, dict) else {}

    if isinstance(models_block, dict):
        for plane in (1, 2, 3, 4):
            raw_model = models_block.get(f"plane_{plane}")
            model = _normalize_fit_model(raw_model, plane=plane)
            if model is not None:
                out[plane] = model

    if not out:
        for plane in (1, 2, 3, 4):
            raw_model = payload.get(f"fit_line_eff_{plane}")
            if raw_model is None:
                raw_model = payload.get(f"fit_poly_eff_{plane}")
            model = _normalize_fit_model(raw_model, plane=plane)
            if model is not None:
                out[plane] = model

    status = "ok" if out else "no_efficiency_fit_models"
    return (out, status, payload if isinstance(payload, dict) else {})


def append_polynomial_corrected_efficiency_columns(
    df: pd.DataFrame,
    fit_models_by_plane: Mapping[int, Mapping[str, object]],
    *,
    empirical_prefix: str = "eff_empirical_",
    output_eff_template: str = POLY_CORRECTED_EFF_COL_TEMPLATE,
    output_effprod_template: str = POLY_CORRECTED_EFFPROD_COL_TEMPLATE,
    clip_input_to_support: bool = True,
    clip_output_to_unit_interval: bool | None = None,
) -> dict[str, object]:
    """Append per-plane and per-combination polynomial-corrected efficiency columns."""
    info: dict[str, object] = {
        "status": "no_models",
        "planes_with_models": sorted(int(p) for p in fit_models_by_plane.keys()),
        "planes_applied": [],
        "efficiency_columns_created": [],
        "efficiency_product_columns_created": [],
        "clip_input_to_support": bool(clip_input_to_support),
        "clip_output_to_unit_interval": (
            None if clip_output_to_unit_interval is None else bool(clip_output_to_unit_interval)
        ),
    }
    if not fit_models_by_plane:
        return info

    corrected_cols_by_plane: dict[int, str] = {}
    for plane in (1, 2, 3, 4):
        model = fit_models_by_plane.get(plane)
        emp_col = f"{empirical_prefix}{plane}"
        if model is None or emp_col not in df.columns:
            continue
        coeffs = _coerce_coefficients(model.get("coefficients_desc"))
        if coeffs is None:
            continue

        raw = pd.to_numeric(df[emp_col], errors="coerce")
        raw_eval = raw.copy()
        if clip_input_to_support:
            lo = _safe_float(model.get("empirical_min"))
            hi = _safe_float(model.get("empirical_max"))
            if lo is not None and hi is not None:
                if hi < lo:
                    lo, hi = hi, lo
                raw_eval = raw_eval.clip(lower=float(lo), upper=float(hi))

        corrected = pd.Series(
            np.polyval(np.asarray(coeffs, dtype=float), raw_eval.to_numpy(dtype=float)),
            index=raw.index,
            dtype=float,
        ).where(raw.notna(), np.nan)

        use_clip_output = (
            bool(model.get("clip_fit_output", True))
            if clip_output_to_unit_interval is None
            else bool(clip_output_to_unit_interval)
        )
        if use_clip_output:
            corrected = corrected.clip(lower=0.0, upper=1.0)

        out_col = output_eff_template.format(plane=plane)
        df[out_col] = corrected
        corrected_cols_by_plane[plane] = out_col
        info["planes_applied"].append(int(plane))
        info["efficiency_columns_created"].append(out_col)

    for suffix, planes in EFF_PRODUCT_SUFFIX_TO_PLANES.items():
        component_cols = [corrected_cols_by_plane.get(int(plane)) for plane in planes]
        if any(col is None for col in component_cols):
            continue
        component_cols = [str(col) for col in component_cols]
        eff_frame = df[component_cols].apply(pd.to_numeric, errors="coerce")
        out_col = output_effprod_template.format(suffix=suffix)
        df[out_col] = eff_frame.prod(axis=1, min_count=len(component_cols))
        info["efficiency_product_columns_created"].append(out_col)

    if info["efficiency_columns_created"]:
        info["status"] = "ok"
    else:
        info["status"] = "no_matching_empirical_columns"
    return info
