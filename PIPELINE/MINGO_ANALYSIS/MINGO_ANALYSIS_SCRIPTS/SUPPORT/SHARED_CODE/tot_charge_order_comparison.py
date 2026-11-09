"""Task-3 strip-calibrated charge columns and calibration-order comparison."""

from __future__ import annotations

import math
from typing import Mapping

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.special import digamma, gammaln

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.tot_charge_calibration import (
    TotChargeCalibration,
)


def strip_tot_column(frame: pd.DataFrame, plane: int, strip: int) -> str | None:
    """Return the pedestal-calibrated ToT width when available."""
    calibrated = f"p{plane}_s{strip}_qsum_cal"
    raw = f"p{plane}_s{strip}_qsum"
    if calibrated in frame.columns:
        return calibrated
    if raw in frame.columns:
        return raw
    return None


def add_task3_charge_fc_columns(
    frame: pd.DataFrame,
    calibration: TotChargeCalibration,
) -> tuple[list[str], list[str], list[str]]:
    """Add calibrated charge per strip and the summed charge per plane.

    The source widths prefer Task-2's ``qsum_cal`` (ns) values. These
    diagnostic result columns are intended to be added after Task-3 filters;
    this helper itself does not alter or select rows.
    """
    strip_columns: list[str] = []
    source_columns: list[str] = []
    plane_columns: list[str] = []
    for plane in range(1, 5):
        plane_strips: list[str] = []
        for strip in range(1, 5):
            source = strip_tot_column(frame, plane, strip)
            output = f"p{plane}_s{strip}_qsum_fc"
            strip_columns.append(output)
            plane_strips.append(output)
            if source is None:
                frame.loc[:, output] = np.nan
                continue
            source_columns.append(source)
            widths = pd.to_numeric(frame[source], errors="coerce").to_numpy(dtype=float)
            frame.loc[:, output] = calibration.width_ns_to_charge_fc(widths)

        plane_output = f"p{plane}_qsum_fc"
        plane_columns.append(plane_output)
        frame.loc[:, plane_output] = frame.loc[:, plane_strips].sum(
            axis=1, min_count=1
        )

    return strip_columns, plane_columns, source_columns


def calibration_order_arrays(
    frame: pd.DataFrame,
    calibration: TotChargeCalibration,
) -> dict[int, dict[str, np.ndarray]]:
    """Build the three plane spectra used in the order-of-operations study.

    ``sum_ns`` is the sum of the four strip ToT widths in ns.
    ``calibrate_then_sum_fc`` sums four independently calibrated strip charges.
    ``sum_then_calibrate_fc`` applies the nonlinear ToT map once to ``sum_ns``.
    Existing Task-3 fC columns are preferred; older products are recalculated
    from their retained Task-2 ToT columns.
    """
    result: dict[int, dict[str, np.ndarray]] = {}
    for plane in range(1, 5):
        sources = [strip_tot_column(frame, plane, strip) for strip in range(1, 5)]
        available_sources = [column for column in sources if column is not None]
        if not available_sources:
            continue
        widths = frame.loc[:, available_sources].apply(
            pd.to_numeric, errors="coerce"
        ).clip(lower=0).fillna(0.0)
        sum_ns = widths.sum(axis=1).to_numpy(dtype=float)

        f_c_strips: list[np.ndarray] = []
        for strip, source in enumerate(sources, start=1):
            persisted = f"p{plane}_s{strip}_qsum_fc"
            if persisted in frame.columns:
                values = pd.to_numeric(frame[persisted], errors="coerce").to_numpy(dtype=float)
            elif source is not None:
                values = calibration.width_ns_to_charge_fc(
                    pd.to_numeric(frame[source], errors="coerce").to_numpy(dtype=float)
                )
            else:
                values = np.full(len(frame), np.nan, dtype=float)
            f_c_strips.append(values)

        persisted_plane = f"p{plane}_qsum_fc"
        if persisted_plane in frame.columns:
            calibrate_then_sum = pd.to_numeric(
                frame[persisted_plane], errors="coerce"
            ).to_numpy(dtype=float)
        else:
            calibrate_then_sum = np.nansum(np.vstack(f_c_strips), axis=0)
            all_missing = np.all(~np.isfinite(np.vstack(f_c_strips)), axis=0)
            calibrate_then_sum[all_missing] = np.nan

        result[plane] = {
            "sum_ns": sum_ns,
            "calibrate_then_sum_fc": calibrate_then_sum,
            "sum_then_calibrate_fc": calibration.width_ns_to_charge_fc(sum_ns),
        }
    return result


def _fit_gamma_zero_location(values: np.ndarray) -> tuple[float, float] | None:
    """Maximum-likelihood Gamma shape/scale with physical support x > 0."""
    sample = np.asarray(values, dtype=float)
    sample = sample[np.isfinite(sample) & (sample > 0)]
    if sample.size < 20:
        return None
    mean = float(sample.mean())
    if not math.isfinite(mean) or mean <= 0:
        return None
    statistic = math.log(mean) - float(np.log(sample).mean())
    if not math.isfinite(statistic) or statistic <= 0:
        return None

    def equation(shape: float) -> float:
        return math.log(shape) - float(digamma(shape)) - statistic

    low, high = 1e-8, 1.0
    while equation(high) > 0 and high < 1e14:
        high *= 10.0
    if equation(high) > 0:
        return None
    try:
        shape = float(brentq(equation, low, high, maxiter=200))
    except (ValueError, RuntimeError):
        return None
    return shape, mean / shape


def _draw_histogram_with_gamma(
    axis,
    values: np.ndarray,
    *,
    bins: int,
    color: str,
    label: str,
) -> tuple[float, float] | None:
    sample = np.asarray(values, dtype=float)
    sample = sample[np.isfinite(sample) & (sample > 0)]
    if sample.size == 0:
        axis.text(0.5, 0.5, "No positive finite values", ha="center", va="center", transform=axis.transAxes)
        return None

    upper = float(np.quantile(sample, 0.995))
    if not math.isfinite(upper) or upper <= 0:
        upper = float(np.max(sample))
    upper = max(upper, float(np.max(sample)) * 1e-6)
    counts, edges, _ = axis.hist(
        sample,
        bins=bins,
        range=(0.0, upper),
        color=color,
        alpha=0.32,
        label=f"{label} (N={sample.size:,})",
    )
    fit = _fit_gamma_zero_location(sample)
    if fit is not None:
        shape, scale = fit
        x = np.linspace(max(upper / bins / 4.0, np.finfo(float).tiny), upper, 300)
        log_pdf = (
            (shape - 1.0) * np.log(x)
            - x / scale
            - gammaln(shape)
            - shape * math.log(scale)
        )
        y = np.exp(log_pdf) * sample.size * (edges[1] - edges[0])
        axis.plot(
            x,
            y,
            color=color,
            linewidth=1.8,
            linestyle="--",
            label=f"Gamma fit: α={shape:.2f}, θ={scale:.2g}",
        )
    axis.set_xlim(0.0, upper)
    return fit


def plot_calibration_order_comparison(
    spectra: Mapping[int, Mapping[str, np.ndarray]],
    *,
    station: int,
    file_count: int,
    bins: int = 70,
):
    """Create four plane rows: ns sum+fit, then both fC ordering cases+fits."""
    fig, axes = plt.subplots(4, 2, figsize=(15, 15), sharey="row")
    axes = np.asarray(axes)
    axes[0, 0].set_title("Sum strip ToT widths, then gamma fit (ns)")
    axes[0, 1].set_title("Charge spectra (fC): calibrate per strip vs after summing")

    for plane in range(1, 5):
        left, right = axes[plane - 1]
        series = spectra.get(plane)
        left.set_ylabel(f"Plane {plane}\nCounts")
        if not series:
            left.text(0.5, 0.5, "Required Task-3 columns unavailable", ha="center", va="center", transform=left.transAxes)
            right.text(0.5, 0.5, "Required Task-3 columns unavailable", ha="center", va="center", transform=right.transAxes)
            continue

        _draw_histogram_with_gamma(
            left,
            series["sum_ns"],
            bins=bins,
            color="#2c5282",
            label="Plane sum in ns",
        )
        left.set_xlabel("Summed ToT width [ns]")
        left.grid(alpha=0.2)
        left.legend(fontsize=8)

        _draw_histogram_with_gamma(
            right,
            series["calibrate_then_sum_fc"],
            bins=bins,
            color="#16856b",
            label="Calibrate each strip, then sum",
        )
        _draw_histogram_with_gamma(
            right,
            series["sum_then_calibrate_fc"],
            bins=bins,
            color="#c05621",
            label="Sum ns, then calibrate",
        )
        right.set_xlabel("Summed charge [fC]")
        right.grid(alpha=0.2)
        right.legend(fontsize=8)

    fig.suptitle(
        "Task 3 ToT-to-charge calibration order comparison\n"
        f"MINGO{station:02d} · {file_count:,} Task-5-completed files · positive values fitted with Gamma(α, θ), loc=0",
        fontsize=14,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return fig


def plot_calibration_order_scatter(
    spectra: Mapping[int, Mapping[str, np.ndarray]],
    *,
    station: int,
    file_count: int,
):
    """Compare per-event plane charge from the two calibration orders."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 11), sharex=True, sharey=True)
    axes = np.asarray(axes).ravel()
    paired: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    all_values: list[np.ndarray] = []
    for plane in range(1, 5):
        series = spectra.get(plane)
        if not series:
            continue
        x = np.asarray(series["calibrate_then_sum_fc"], dtype=float)
        y = np.asarray(series["sum_then_calibrate_fc"], dtype=float)
        finite = np.isfinite(x) & np.isfinite(y)
        x, y = x[finite], y[finite]
        if x.size:
            paired[plane] = (x, y)
            all_values.extend((x, y))

    if all_values:
        pooled = np.concatenate(all_values)
        lower, upper = np.quantile(pooled, [0.005, 0.995])
        if not np.isfinite(lower) or not np.isfinite(upper) or upper <= lower:
            lower, upper = float(np.min(pooled)), float(np.max(pooled))
        if upper <= lower:
            upper = lower + 1.0
    else:
        lower, upper = 0.0, 1.0

    for plane, axis in enumerate(axes, start=1):
        series = spectra.get(plane)
        axis.set_title(f"Plane {plane}")
        axis.set_xlabel("Sum strip-calibrated charges [fC]")
        axis.set_ylabel("Calibrate summed ToT [fC]")
        axis.grid(alpha=0.2)
        if not series:
            axis.text(0.5, 0.5, "Required Task-3 columns unavailable", ha="center", va="center", transform=axis.transAxes)
            continue

        if plane not in paired:
            axis.text(0.5, 0.5, "No paired finite values", ha="center", va="center", transform=axis.transAxes)
            continue
        x, y = paired[plane]
        axis.scatter(x, y, s=5, alpha=0.18, linewidths=0, rasterized=True)
        axis.plot([lower, upper], [lower, upper], color="#c53030", linestyle="--", linewidth=1.4, label="Equal result")
        axis.set_xlim(lower, upper)
        axis.set_ylim(lower, upper)
        axis.set_aspect("equal", adjustable="box")
        axis.text(
            0.03,
            0.97,
            f"N={len(x):,}\nshared view: 0.5–99.5%",
            transform=axis.transAxes,
            va="top",
            fontsize=8,
        )
        axis.legend(fontsize=8, loc="lower right")

    fig.suptitle(
        "Task 3 charge by calibration order · per-event comparison\n"
        f"MINGO{station:02d} · {file_count:,} consecutive Task-5-completed files",
        fontsize=14,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig
