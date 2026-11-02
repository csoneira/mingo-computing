from __future__ import annotations

import re
from ast import literal_eval
from typing import List

import numpy as np
import pandas as pd


def _charge_series_is_usable(series: pd.Series) -> bool:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() == 0:
        return False
    return bool((numeric > 0).any())


TASK5_STRIP_CHARGE_COLUMNS = tuple(
    f"p{plane}_s{strip}_qsum"
    for plane in range(1, 5)
    for strip in range(1, 5)
)
TASK5_TOPOLOGY_GATE_COLUMNS = (
    "task5_gate_max_strips_per_plane",
    "task5_gate_all_planes_adjacent",
    "task5_gate_any_plane_nonadjacent",
)


def add_task5_strip_topology_gate_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Add temporary per-event strip-count/adjacency inputs for Task-5 gates.

    A strip is active when its calibrated strip Q_sum is finite and non-zero,
    matching the pipeline's existing topology convention. Each plane's active
    strips are contiguous when their strip indices form one uninterrupted run.
    """
    missing = [column for column in TASK5_STRIP_CHARGE_COLUMNS if column not in dataframe.columns]
    if missing:
        raise ValueError(
            "Task-5 strip-topology gates require all 16 strip Q_sum columns; "
            f"missing: {', '.join(missing)}"
        )

    charge = dataframe.loc[:, TASK5_STRIP_CHARGE_COLUMNS].apply(
        pd.to_numeric, errors="coerce"
    ).to_numpy(dtype=float).reshape(-1, 4, 4)
    active = np.isfinite(charge) & (charge != 0)
    counts = active.sum(axis=2)
    strip_indices = np.arange(4, dtype=int)[None, None, :]
    first_active = np.where(active, strip_indices, 4).min(axis=2)
    last_active = np.where(active, strip_indices, -1).max(axis=2)
    adjacent_by_plane = (counts <= 1) | ((last_active - first_active + 1) == counts)

    dataframe.loc[:, TASK5_TOPOLOGY_GATE_COLUMNS[0]] = counts.max(axis=1) if len(dataframe) else np.array([], dtype=int)
    dataframe.loc[:, TASK5_TOPOLOGY_GATE_COLUMNS[1]] = adjacent_by_plane.all(axis=1)
    dataframe.loc[:, TASK5_TOPOLOGY_GATE_COLUMNS[2]] = ((counts >= 2) & ~adjacent_by_plane).any(axis=1)
    return dataframe


def _coerce_numeric_sequence(raw_value, caster):
    """Return a list of numbers parsed from *raw_value*."""
    if isinstance(raw_value, (list, tuple, np.ndarray)):
        result: List[float] = []
        for item in raw_value:
            result.extend(_coerce_numeric_sequence(item, caster))
        return result
    if isinstance(raw_value, str):
        cleaned = raw_value.strip()
        if not cleaned:
            return []
        try:
            parsed = literal_eval(cleaned)
        except (ValueError, SyntaxError):
            cleaned = cleaned.replace("[", " ").replace("]", " ")
            tokens = [tok for tok in re.split(r"[;,\s]+", cleaned) if tok]
            result = []
            for tok in tokens:
                try:
                    result.append(caster(tok))
                except (ValueError, TypeError):
                    continue
            return result
        else:
            return _coerce_numeric_sequence(parsed, caster)
    if np.isscalar(raw_value):
        try:
            return [caster(raw_value)]
        except (ValueError, TypeError):
            return []
    return []


def _task5_parse_optional_top_n(raw_value: object, default: int | None) -> int | None:
    if raw_value in (None, "", "null", "None"):
        return None
    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        return default
