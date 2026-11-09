from __future__ import annotations

import numpy as np
import pandas as pd


def _optional_config_float(config_dict: dict, key: str) -> float | None:
    """Return a float config value, or None when the key is unset/blank/NaN."""
    raw_value = config_dict.get(key, None)
    if raw_value is None:
        return None
    if isinstance(raw_value, str) and not raw_value.strip():
        return None
    try:
        if pd.isna(raw_value):
            return None
    except TypeError:
        pass
    return float(raw_value)


def _optional_float(raw_value) -> float | None:
    """Return float(raw_value), or None when the value is unset/blank/NaN."""
    if raw_value is None:
        return None
    if isinstance(raw_value, str) and not raw_value.strip():
        return None
    try:
        if pd.isna(raw_value):
            return None
    except TypeError:
        pass
    return float(raw_value)


def _format_value_for_print(value: object) -> object:
    """Recursively convert NumPy scalars/arrays into native Python types."""
    if isinstance(value, (np.floating, np.integer)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.astype(float).tolist()
    if isinstance(value, (list, tuple)):
        return [_format_value_for_print(item) for item in value]
    if isinstance(value, dict):
        return {key: _format_value_for_print(val) for key, val in value.items()}
    return value


def _format_dict_for_print(data: dict) -> dict:
    """Return *data* with NumPy containers converted to native Python types."""
    return {key: _format_value_for_print(value) for key, value in data.items()}
