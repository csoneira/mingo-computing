from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np
import pandas as pd

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.step1_shared import normalize_tt_label


def _coerce_nonnegative_int_tuple(raw_value: object, default: Iterable[int]) -> tuple[int, ...]:
    if raw_value is None:
        return tuple(int(x) for x in default)
    if isinstance(raw_value, (int, np.integer)):
        return (max(0, int(raw_value)),)
    if isinstance(raw_value, str):
        items = [chunk.strip() for chunk in raw_value.split(",") if chunk.strip()]
    elif isinstance(raw_value, (list, tuple, set, np.ndarray, pd.Series)):
        items = list(raw_value)
    else:
        return tuple(int(x) for x in default)

    parsed: list[int] = []
    for item in items:
        try:
            parsed.append(max(0, int(item)))
        except (TypeError, ValueError):
            continue
    if not parsed:
        return tuple(int(x) for x in default)
    return tuple(sorted(set(parsed)))


def _coerce_tt_label_tuple(raw_value: object, default: Iterable[object]) -> tuple[str, ...]:
    source = list(default) if raw_value is None else raw_value
    if isinstance(source, str):
        source = [chunk.strip() for chunk in source.split(",") if chunk.strip()]
    elif not isinstance(source, (list, tuple, set, np.ndarray, pd.Series)):
        source = list(default)

    labels: list[str] = []
    for item in source:
        label = normalize_tt_label(item, default="")
        if label and label != "0" and label not in labels:
            labels.append(label)
    if labels:
        return tuple(labels)
    return tuple(normalize_tt_label(item, default="0") for item in default)


def _coerce_probability_tuple(raw_value: object, default: Iterable[float]) -> tuple[float, ...]:
    source = list(default) if raw_value is None else raw_value
    if isinstance(source, str):
        source = [chunk.strip() for chunk in source.split(",") if chunk.strip()]
    elif not isinstance(source, (list, tuple, set, np.ndarray, pd.Series)):
        source = list(default)

    values: list[float] = []
    for item in source:
        try:
            value = float(item)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(value) or not (0.0 < value < 1.0):
            continue
        if not any(abs(value - existing) < 1e-12 for existing in values):
            values.append(value)
    if values:
        return tuple(sorted(values))
    return tuple(float(item) for item in default)


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
        if not key:
            continue
        if key in config_obj:
            return _task4_parse_optional_float(config_obj.get(key))
    return None


def _cfg_int_or_default(
    config_obj: Mapping[str, object],
    key: str,
    default_value: int,
    *,
    min_value: int = 1,
) -> int:
    raw = config_obj.get(key, default_value)
    try:
        if raw is None or str(raw).strip() == "":
            return int(default_value)
        value = int(float(raw))
    except (TypeError, ValueError):
        return int(default_value)
    return max(min_value, value)


def _cfg_float_or_default(
    config_obj: Mapping[str, object],
    key: str,
    default_value: float,
    *,
    min_value: float = 0.0,
) -> float:
    raw = config_obj.get(key, default_value)
    try:
        if raw is None or str(raw).strip() == "":
            return float(default_value)
        value = float(raw)
    except (TypeError, ValueError):
        return float(default_value)
    return max(min_value, value)


def _safe_cfg_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_cfg_float(value, default):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float(default)
    return float(out) if np.isfinite(out) else float(default)


def _safe_cfg_optional_float(value):
    if value in (None, "", "null", "None"):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return float(out) if np.isfinite(out) else None
