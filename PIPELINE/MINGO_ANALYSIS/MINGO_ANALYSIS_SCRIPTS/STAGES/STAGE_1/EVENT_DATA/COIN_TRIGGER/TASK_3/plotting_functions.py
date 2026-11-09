from __future__ import annotations

import matplotlib as mpl
import numpy as np
import pandas as pd


def _task3_quantile_axis_limits(
    values: pd.Series | np.ndarray,
    low_q: float = 1.0,
    high_q: float = 99.0,
) -> tuple[float, float] | None:
    numeric = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    numeric = numeric[np.isfinite(numeric)]
    if numeric.size == 0:
        return None

    low = float(np.nanpercentile(numeric, low_q))
    high = float(np.nanpercentile(numeric, high_q))
    if not np.isfinite(low) or not np.isfinite(high) or low >= high:
        low = float(np.nanmin(numeric))
        high = float(np.nanmax(numeric))
    if not np.isfinite(low) or not np.isfinite(high):
        return None
    if low >= high:
        center = low
        pad = max(abs(center) * 0.05, 1.0)
        low = center - pad
        high = center + pad
    return low, high


def _task3_plot_quantile_hexbin(
    ax: mpl.axes.Axes,
    x: pd.Series | np.ndarray,
    y: pd.Series | np.ndarray,
    title: str,
    *,
    gridsize: int = 50,
    cmap: str = "turbo",
    low_q: float = 1.0,
    high_q: float = 99.0,
) -> None:
    x_vals = pd.to_numeric(pd.Series(x), errors="coerce").to_numpy(dtype=float)
    y_vals = pd.to_numeric(pd.Series(y), errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(x_vals) & np.isfinite(y_vals)
    ax.set_title(title)

    if not np.any(valid):
        ax.text(0.5, 0.5, "No valid data", ha="center", va="center", transform=ax.transAxes)
        return

    x_valid = x_vals[valid]
    y_valid = y_vals[valid]
    x_limits = _task3_quantile_axis_limits(x_valid, low_q=low_q, high_q=high_q)
    y_limits = _task3_quantile_axis_limits(y_valid, low_q=low_q, high_q=high_q)
    if x_limits is None or y_limits is None:
        ax.text(0.5, 0.5, "No finite data", ha="center", va="center", transform=ax.transAxes)
        return

    x_low, x_high = x_limits
    y_low, y_high = y_limits
    plot_mask = (
        valid
        & (x_vals >= x_low)
        & (x_vals <= x_high)
        & (y_vals >= y_low)
        & (y_vals <= y_high)
    )
    if not np.any(plot_mask):
        plot_mask = valid

    ax.hexbin(
        x_vals[plot_mask],
        y_vals[plot_mask],
        gridsize=gridsize,
        cmap=cmap,
        mincnt=1,
        extent=(x_low, x_high, y_low, y_high),
    )
    ax.set_xlim(x_low, x_high)
    ax.set_ylim(y_low, y_high)


def _task3_plot_quantile_scatter(
    ax: mpl.axes.Axes,
    x: pd.Series | np.ndarray,
    y: pd.Series | np.ndarray,
    title: str,
    *,
    low_q: float = 1.0,
    high_q: float = 99.0,
    color: str = "tab:blue",
    alpha: float = 0.18,
    size: float = 4.0,
) -> None:
    x_vals = pd.to_numeric(pd.Series(x), errors="coerce").to_numpy(dtype=float)
    y_vals = pd.to_numeric(pd.Series(y), errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(x_vals) & np.isfinite(y_vals)
    ax.set_title(title)

    if not np.any(valid):
        ax.text(0.5, 0.5, "No valid data", ha="center", va="center", transform=ax.transAxes)
        return

    x_valid = x_vals[valid]
    y_valid = y_vals[valid]
    x_limits = _task3_quantile_axis_limits(x_valid, low_q=low_q, high_q=high_q)
    y_limits = _task3_quantile_axis_limits(y_valid, low_q=low_q, high_q=high_q)
    if x_limits is None or y_limits is None:
        ax.text(0.5, 0.5, "No finite data", ha="center", va="center", transform=ax.transAxes)
        return

    x_low, x_high = x_limits
    y_low, y_high = y_limits
    plot_mask = (
        valid
        & (x_vals >= x_low)
        & (x_vals <= x_high)
        & (y_vals >= y_low)
        & (y_vals <= y_high)
    )
    if not np.any(plot_mask):
        plot_mask = valid

    ax.scatter(
        x_vals[plot_mask],
        y_vals[plot_mask],
        s=size,
        alpha=alpha,
        color=color,
        edgecolors="none",
        rasterized=True,
    )
    ax.set_xlim(x_low, x_high)
    ax.set_ylim(y_low, y_high)
