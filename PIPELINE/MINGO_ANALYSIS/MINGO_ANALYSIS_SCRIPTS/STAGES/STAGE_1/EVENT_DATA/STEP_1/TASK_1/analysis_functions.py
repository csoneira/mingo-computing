from __future__ import annotations

import numpy as np


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _coerce_z_vector(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple, np.ndarray)) or len(value) != 4:
        return None
    try:
        vector = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if not all(np.isfinite(item) for item in vector):
        return None
    return vector


def _normalize_z_vector(
    z_vector: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    base = float(z_vector[0])
    return tuple(round(float(value) - base, 6) for value in z_vector)


def _iter_priority_vectors(value: object) -> list[tuple[float, float, float, float]]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, np.ndarray)):
        single = _coerce_z_vector(value)
        if single is not None:
            return [single]
        vectors: list[tuple[float, float, float, float]] = []
        for entry in value:
            coerced = _coerce_z_vector(entry)
            if coerced is not None:
                vectors.append(coerced)
        return vectors
    return []


def _z_vector_matches_priority(
    z_vector: tuple[float, float, float, float],
    settings: dict[str, object],
) -> bool:
    abs_vector = tuple(round(float(value), 6) for value in z_vector)
    norm_vector = _normalize_z_vector(abs_vector)
    priority_abs = settings.get("priority_abs", set())
    priority_norm = settings.get("priority_norm", set())
    match_mode = settings.get("match_mode", "absolute")

    if match_mode == "normalized":
        return norm_vector in priority_norm
    if match_mode == "both":
        return abs_vector in priority_abs or norm_vector in priority_norm
    return abs_vector in priority_abs
