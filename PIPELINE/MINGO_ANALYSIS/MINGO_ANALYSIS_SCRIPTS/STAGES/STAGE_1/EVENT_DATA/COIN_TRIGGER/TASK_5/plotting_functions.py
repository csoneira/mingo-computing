from __future__ import annotations

import numpy as np


def _task5_channel_hist_range(
    values: np.ndarray,
    limits: tuple[float | None, float | None],
) -> tuple[float, float]:
    finite_values = values[np.isfinite(values)]
    lower_limit, upper_limit = limits
    if finite_values.size:
        low = float(np.nanpercentile(finite_values, 1))
        high = float(np.nanpercentile(finite_values, 99))
        if not np.isfinite(low) or not np.isfinite(high) or low == high:
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
    padding = 0.08 * span if span > 0 else 1.0
    return low - padding, high + padding
