from __future__ import annotations

import math

import numpy as np
import pandas as pd

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.step1_shared import normalize_tt_label


def _task3_optional_float(raw_value: object) -> float | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, str) and raw_value.strip().lower() in {"", "none", "null"}:
        return None
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def _task3_config_float(
    config_obj: dict[str, object],
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
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid numeric configuration value for '{key}': {raw_value!r}") from exc
        if not np.isfinite(value):
            raise ValueError(f"Non-finite numeric configuration value for '{key}': {raw_value!r}")
        return value
    return float(default)


def _count_turns(strips: list[int]) -> int:
    if len(strips) < 3:
        return 0
    deltas = [strips[idx + 1] - strips[idx] for idx in range(len(strips) - 1)]
    signs = [int(np.sign(delta)) for delta in deltas if delta != 0]
    return int(sum(1 for idx in range(len(signs) - 1) if signs[idx] != signs[idx + 1]))


def tt_value_to_planes(tt_value: object) -> list[int]:
    label = normalize_tt_label(tt_value, default="0")
    return [int(char) for char in label if char in {"1", "2", "3", "4"}]


def compute_empirical_efficiency_from_tt_counts(
    tt_counts: pd.Series,
) -> dict[int, tuple[float, float, int, int]]:
    """Compute per-plane empirical efficiencies 1 - N(others)/N(1234)."""
    n_four = int(tt_counts.get(1234, 0))
    missing_plane_tt = {1: 234, 2: 134, 3: 124, 4: 123}
    results: dict[int, tuple[float, float, int, int]] = {}

    for plane, tt_value in missing_plane_tt.items():
        n_three = int(tt_counts.get(tt_value, 0))
        if n_four <= 0:
            results[plane] = (np.nan, np.nan, n_three, n_four)
            continue

        n_three_float = float(n_three)
        n_four_float = float(n_four)
        efficiency = 1.0 - (n_three_float / n_four_float)
        variance = (n_three_float / (n_four_float ** 2)) + ((n_three_float ** 2) / (n_four_float ** 3))
        error = math.sqrt(max(variance, 0.0))
        results[plane] = (efficiency, error, n_three, n_four)

    return results
