from __future__ import annotations

import hashlib

import matplotlib.pyplot as plt
import numpy as np


def _task1_population_color(label: str) -> tuple[float, float, float, float]:
    digest = hashlib.md5(label.encode("utf-8")).digest()
    color_pos = int.from_bytes(digest[:4], "big") / float(2**32 - 1)
    return plt.get_cmap("turbo")(0.08 + 0.84 * color_pos)


def _task1_full_data_range(
    values: np.ndarray,
    limits: tuple[float | None, float | None],
) -> tuple[float, float]:
    finite_values = values[np.isfinite(values)]
    lower_limit, upper_limit = limits
    if finite_values.size:
        low = float(np.nanmin(finite_values))
        high = float(np.nanmax(finite_values))
    else:
        low, high = -1.0, 1.0
    if lower_limit is not None:
        low = min(low, float(lower_limit))
    if upper_limit is not None:
        high = max(high, float(upper_limit))
    if not np.isfinite(low) or not np.isfinite(high) or low == high:
        center = float(low if np.isfinite(low) else 0.0)
        low, high = center - 1.0, center + 1.0
    span = high - low
    padding = 0.05 * span if span > 0 else max(1.0, 0.05 * max(abs(low), abs(high), 1.0))
    return low - padding, high + padding


def _task1_capped_plot_range(
    values: np.ndarray,
    limits: tuple[float | None, float | None],
    *,
    boundary_expansion_factor: float = 1.5,
) -> tuple[float, float]:
    finite_values = values[np.isfinite(values)]
    lower_limit, upper_limit = limits
    lower_limit = float(lower_limit) if lower_limit is not None and np.isfinite(lower_limit) else None
    upper_limit = float(upper_limit) if upper_limit is not None and np.isfinite(upper_limit) else None

    if finite_values.size:
        data_low = float(np.nanmin(finite_values))
        data_high = float(np.nanmax(finite_values))
    else:
        data_low, data_high = np.nan, np.nan

    if lower_limit is not None and upper_limit is not None and upper_limit > lower_limit:
        center = 0.5 * (lower_limit + upper_limit)
        half_span = 0.5 * (upper_limit - lower_limit)
        cap_low = center - boundary_expansion_factor * half_span
        cap_high = center + boundary_expansion_factor * half_span
    else:
        return _task1_full_data_range(values, limits)

    low = lower_limit
    high = upper_limit
    if np.isfinite(data_low):
        low = min(low, data_low)
    if np.isfinite(data_high):
        high = max(high, data_high)

    low = max(low, cap_low)
    high = min(high, cap_high)

    if not np.isfinite(low) or not np.isfinite(high) or low >= high:
        low, high = cap_low, cap_high

    span = high - low
    padding = 0.04 * span if span > 0 else max(0.5, 0.04 * max(abs(low), abs(high), 1.0))
    return low - padding, high + padding
