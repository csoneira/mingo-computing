from __future__ import annotations

import numpy as np


def _safe_hist_params(series, max_bins=50):
    """Return (bins, range) for hist; avoid zero-range/invalid bins."""
    finite_series = series[np.isfinite(series)]
    if getattr(finite_series, "size", 0) == 0:
        return None, None
    vmin = finite_series.min()
    vmax = finite_series.max()
    if not np.isfinite(vmin) or not np.isfinite(vmax):
        return None, None
    if vmin == vmax:
        pad = 0.5 if vmin == 0 else 0.05 * abs(vmin)
        return 1, (vmin - pad, vmax + pad)
    bins = int(min(max_bins, max(1, len(np.unique(finite_series)))))
    return bins, (vmin, vmax)


def _format_task4_percent_label(value: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = np.nan
    if not np.isfinite(numeric):
        return "n/a"
    if abs(numeric) <= 1.0:
        numeric *= 100.0
    return f"{numeric:.1f}%"
