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

CLUSTER_SIZE_COLORS = {
    1: "#2b6cb0",
    2: "#2f855a",
    3: "#dd6b20",
    4: "#805ad5",
}


def plot_tot_charge_calibration_curve(calibration: TotChargeCalibration):
    """Plot the LUT spline and smooth origin-to-first-point transition."""
    widths = np.asarray(calibration.widths_ns, dtype=float)
    charges = np.asarray(calibration.charges_fc, dtype=float)
    first_width = float(widths[0])
    last_width = float(widths[-1])

    fig, (axis, near_zero) = plt.subplots(
        2, 1, figsize=(11, 8), gridspec_kw={"height_ratios": [3, 1.35]}
    )

    # Below the first LUT point the converter uses a smooth Hermite segment;
    # its slope is zero at the origin and matches the LUT spline at the knot.
    bridge_widths = np.linspace(0.0, first_width, 100)
    measured_range = np.linspace(first_width, last_width, 5000)
    high_range = np.linspace(last_width, last_width + 10.0, 250)
    axis.plot(
        bridge_widths,
        calibration._near_zero_to_charge(bridge_widths),
        color="#2f855a",
        linestyle="-",
        linewidth=1.8,
        label="Smooth Hermite transition from (0, 0) to first LUT point",
    )
    axis.plot(
        measured_range,
        calibration._width_to_charge(measured_range),
        color="#2457a7",
        linewidth=2.2,
        label="Cubic spline used between LUT points",
    )
    axis.plot(
        high_range,
        calibration._width_to_charge(high_range),
        color="#c53030",
        linestyle="--",
        linewidth=1.8,
        label="Spline extrapolation (above LUT)",
    )
    axis.scatter(widths, charges, s=20, color="#111827", zorder=3, label="Calibration LUT points")
    axis.scatter([0], [0], marker="x", s=70, color="#111827", zorder=4,
                 label="Converter maps width ≤ 0 to 0 fC")
    axis.set(xlim=(0, last_width + 10), xlabel="ToT width [ns]", ylabel="Fast charge [fC]",
             title="Task 3 ToT-to-charge calibration used for strip charge")
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8, ncol=2)

    # Resolve the zero-to-first-knot bridge in units of the first LUT width.
    bridge_zoom = np.linspace(0.0, 1.0, 100)
    near_zero.plot(
        bridge_zoom,
        calibration._near_zero_to_charge(bridge_zoom * first_width),
        color="#2f855a",
        linestyle="-",
        linewidth=1.8,
        label="Smooth Hermite transition (0 to first LUT point)",
    )
    spline_zoom = np.linspace(first_width, first_width * 2.0, 200)
    near_zero.plot(
        spline_zoom / first_width,
        calibration._width_to_charge(spline_zoom),
        color="#2457a7",
        linewidth=1.8,
        label="Cubic spline above first LUT point",
    )
    near_zero.scatter([1.0], [charges[0]], color="#111827", s=32, zorder=3,
                      label=f"First LUT point: {first_width:g} ns, {charges[0]:.2f} fC")
    near_zero.scatter([0.0], [0.0], marker="x", color="#111827", s=65, zorder=4,
                      label="width ≤ 0 → 0 fC")
    near_zero.set(xlim=(0, 2), xlabel=f"ToT width / first LUT width  (first width = {first_width:g} ns)",
                  ylabel="Fast charge [fC]", title="Near-zero behavior: smooth transition to (0, 0)")
    near_zero.grid(alpha=0.25)
    near_zero.legend(fontsize=8, ncol=3, loc="best")
    fig.tight_layout()
    return fig


def plot_calibrated_strip_charge_histograms(
    strip_charges: Mapping[tuple[int, int], np.ndarray],
    *,
    station: int,
    event_count: int,
    bins: int = 140,
):
    """Show the calibrated fC charge distribution for each plane/strip."""
    fig, axes = plt.subplots(4, 4, figsize=(15, 12), sharex=True, sharey=True)
    all_positive = [
        np.asarray(values, dtype=float)[
            np.isfinite(np.asarray(values, dtype=float))
            & (np.asarray(values, dtype=float) > 0)
        ]
        for values in strip_charges.values()
    ]
    all_positive = [values for values in all_positive if values.size]
    upper = float(np.quantile(np.concatenate(all_positive), 0.995)) if all_positive else 1.0
    if not np.isfinite(upper) or upper <= 0:
        upper = 1.0
    max_bin_count = 1

    for plane in range(1, 5):
        for strip in range(1, 5):
            axis = axes[plane - 1, strip - 1]
            values = np.asarray(strip_charges.get((plane, strip), []), dtype=float)
            values = values[np.isfinite(values) & (values > 0)]
            axis.set_title(f"P{plane} · strip {strip}")
            axis.grid(alpha=0.2)
            axis.set_xlim(0, upper)
            if values.size:
                counts, _, _ = axis.hist(
                    values,
                    bins=bins,
                    range=(0, upper),
                    histtype="step",
                    linewidth=1.4,
                    color="#2457a7",
                )
                max_bin_count = max(max_bin_count, int(np.max(counts)))
                axis.text(0.97, 0.92, f"N={values.size:,}", transform=axis.transAxes,
                          ha="right", va="top", fontsize=8)
            else:
                axis.text(0.5, 0.5, "No positive hits", transform=axis.transAxes,
                          ha="center", va="center", fontsize=8)
            if plane == 4:
                axis.set_xlabel("Calibrated strip charge [fC]")
            if strip == 1:
                axis.set_ylabel("Counts")

    for axis in axes.ravel():
        axis.set_yscale("log")
        axis.set_ylim(0.5, max_bin_count * 1.25)

    fig.suptitle(
        "Task 3 calibrated charge per strip · coincidence events\n"
        f"MINGO{station:02d} · {event_count:,} coincidence events · shared axes; zero-charge entries omitted",
        fontsize=14,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig


def plot_calibrated_strip_charge_by_cluster_size(
    strip_charges: Mapping[int, Mapping[tuple[int, int], np.ndarray]],
    *,
    station: int,
    event_counts: Mapping[int, int],
    plane_charges: Mapping[int, Mapping[int, np.ndarray]] | None = None,
    bins: int = 140,
):
    """Return one plane-by-strip charge figure for each plane cluster size.

    When ``plane_charges`` is provided, a fifth column shows the sum of the
    calibrated strip charges for that plane and cluster size.
    """
    pooled = [
        np.asarray(values, dtype=float)
        for size_values in strip_charges.values()
        for values in size_values.values()
    ]
    pooled_positive = [values[np.isfinite(values) & (values > 0)] for values in pooled]
    pooled_positive = [values for values in pooled_positive if values.size]
    strip_x_upper = (
        float(np.quantile(np.concatenate(pooled_positive), 0.995))
        if pooled_positive else 1.0
    )
    if not np.isfinite(strip_x_upper) or strip_x_upper <= 0:
        strip_x_upper = 1.0

    pooled_plane = []
    if plane_charges is not None:
        pooled_plane = [
            np.asarray(values, dtype=float)
            for size_values in plane_charges.values()
            for values in size_values.values()
        ]
    pooled_plane_positive = [
        values[np.isfinite(values) & (values > 0)] for values in pooled_plane
    ]
    pooled_plane_positive = [values for values in pooled_plane_positive if values.size]
    plane_x_upper = (
        float(np.quantile(np.concatenate(pooled_plane_positive), 0.995))
        if pooled_plane_positive else strip_x_upper
    )
    if not np.isfinite(plane_x_upper) or plane_x_upper <= 0:
        plane_x_upper = strip_x_upper

    figures = {}
    for cluster_size in range(1, 5):
        n_columns = 5 if plane_charges is not None else 4
        fig, axes = plt.subplots(
            4, n_columns, figsize=(18.5 if n_columns == 5 else 15, 12), sharey=True
        )
        if n_columns == 5:
            # Strip panels share their own charge range; the summed plane
            # population gets an independent X range so it remains legible.
            for row in range(4):
                for column in range(1, 4):
                    axes[row, column].sharex(axes[0, 0])
                if row > 0:
                    axes[row, 4].sharex(axes[0, 4])
        else:
            for row in range(4):
                for column in range(1, 4):
                    axes[row, column].sharex(axes[0, 0])
        max_bin_count = 1
        for plane in range(1, 5):
            for strip in range(1, 5):
                axis = axes[plane - 1, strip - 1]
                values = np.asarray(
                    strip_charges.get(cluster_size, {}).get((plane, strip), []),
                    dtype=float,
                )
                values = values[np.isfinite(values) & (values > 0)]
                axis.set_title(f"P{plane} · strip {strip}")
                axis.grid(alpha=0.2)
                axis.set_xlim(0, strip_x_upper)
                if values.size:
                    counts, _, _ = axis.hist(
                        values,
                        bins=bins,
                        range=(0, strip_x_upper),
                        histtype="step",
                        linewidth=1.4,
                        color="#2457a7",
                    )
                    max_bin_count = max(max_bin_count, int(np.max(counts)))
                    axis.text(0.97, 0.92, f"N={values.size:,}", transform=axis.transAxes,
                              ha="right", va="top", fontsize=8)
                else:
                    axis.text(0.5, 0.5, "No positive hits", transform=axis.transAxes,
                              ha="center", va="center", fontsize=8)
                if plane == 4:
                    axis.set_xlabel("Calibrated strip charge [fC]")
                if strip == 1:
                    axis.set_ylabel("Counts")

            if plane_charges is not None:
                axis = axes[plane - 1, 4]
                values = np.asarray(
                    plane_charges.get(cluster_size, {}).get(plane, []), dtype=float
                )
                values = values[np.isfinite(values) & (values > 0)]
                axis.set_title(f"P{plane} · total")
                axis.grid(alpha=0.2)
                axis.set_xlim(0, plane_x_upper)
                if values.size:
                    counts, _, _ = axis.hist(
                        values,
                        bins=bins,
                        range=(0, plane_x_upper),
                        histtype="step",
                        linewidth=1.6,
                        color="#b7791f",
                    )
                    max_bin_count = max(max_bin_count, int(np.max(counts)))
                    axis.text(0.97, 0.92, f"N={values.size:,}", transform=axis.transAxes,
                              ha="right", va="top", fontsize=8)
                else:
                    axis.text(0.5, 0.5, "No positive events", transform=axis.transAxes,
                              ha="center", va="center", fontsize=8)
                axis.set_xlabel("Total calibrated plane charge [fC]")

        for axis in axes.ravel():
            axis.set_yscale("log")
            axis.set_ylim(0.5, max_bin_count * 1.25)
        interpretation = (
            "single-strip cluster charge"
            if cluster_size == 1
            else "per-strip share within a multi-strip cluster"
        )
        fig.suptitle(
            f"Task 3 calibrated charge per strip and total plane charge · cluster size = {cluster_size}\n"
            f"MINGO{station:02d} · {event_counts.get(cluster_size, 0):,} plane-event entries · "
            f"{interpretation}; zero-charge entries omitted",
            fontsize=14,
        )
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        figures[cluster_size] = fig
    return figures


def strip_tot_column(frame: pd.DataFrame, plane: int, strip: int) -> str | None:
    """Return the Task-2 accepted pedestal-calibrated ToT width when available."""
    accepted = f"p{plane}_s{strip}_qsum_task2"
    calibrated = f"p{plane}_s{strip}_qsum_cal"
    raw = f"p{plane}_s{strip}_qsum"
    if accepted in frame.columns:
        return accepted
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
        strip_widths: list[np.ndarray] = []
        for source in sources:
            if source is None:
                strip_widths.append(np.zeros(len(frame), dtype=float))
            else:
                strip_widths.append(
                    pd.to_numeric(frame[source], errors="coerce")
                    .clip(lower=0)
                    .fillna(0.0)
                    .to_numpy(dtype=float)
                )
        width_matrix = np.column_stack(strip_widths)
        sum_ns = width_matrix.sum(axis=1)

        pattern_column = f"active_strips_P{plane}"
        cluster_size = (width_matrix > 0).sum(axis=1).astype(int)
        if pattern_column in frame.columns:
            patterns = frame[pattern_column].fillna("0000").astype(str).to_numpy()
            valid = np.fromiter(
                (len(pattern) == 4 and set(pattern) <= {"0", "1"} for pattern in patterns),
                dtype=bool,
                count=len(patterns),
            )
            if valid.all():
                cluster_size = np.fromiter(
                    (pattern.count("1") for pattern in patterns),
                    dtype=int,
                    count=len(patterns),
                )

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
            "cluster_size": cluster_size,
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
    upper_limit: float | None = None,
    linestyle: str = "-",
    fit_linestyle: str = ":",
) -> tuple[float, float] | None:
    sample = np.asarray(values, dtype=float)
    sample = sample[np.isfinite(sample) & (sample > 0)]
    if sample.size == 0:
        axis.text(0.5, 0.5, "No positive finite values", ha="center", va="center", transform=axis.transAxes)
        return None

    upper = float(upper_limit) if upper_limit is not None else float(np.quantile(sample, 0.995))
    if not math.isfinite(upper) or upper <= 0:
        upper = float(np.max(sample))
    upper = max(upper, float(np.max(sample)) * 1e-6)
    counts, edges, _ = axis.hist(
        sample,
        bins=bins,
        range=(0.0, upper),
        color=color,
        alpha=0.9,
        histtype="step",
        linewidth=1.2,
        linestyle=linestyle,
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
            linestyle=fit_linestyle,
            label="_nolegend_",
        )
    axis.set_xlim(0.0, upper)
    return fit


def plot_calibration_order_comparison(
    spectra: Mapping[int, Mapping[str, np.ndarray]],
    *,
    station: int,
    file_count: int,
    bins: int = 140,
    trigger_combo: str | None = None,
):
    """Show ToT/fC spectra split by per-plane active-strip cluster size."""
    fig, axes = plt.subplots(4, 2, figsize=(15, 15), sharey="row")
    axes = np.asarray(axes)
    axes[0, 0].set_title("Summed strip ToT by cluster size (ns)")
    axes[0, 1].set_title("Plane charge by calibration order and cluster size (fC)")

    for plane in range(1, 5):
        left, right = axes[plane - 1]
        series = spectra.get(plane)
        left.set_ylabel(f"Plane {plane}\nCounts")
        if not series:
            left.text(0.5, 0.5, "Required Task-3 columns unavailable", ha="center", va="center", transform=left.transAxes)
            right.text(0.5, 0.5, "Required Task-3 columns unavailable", ha="center", va="center", transform=right.transAxes)
            continue

        cluster_sizes = np.asarray(series["cluster_size"], dtype=int)
        ns_values = np.asarray(series["sum_ns"], dtype=float)
        ns_valid = np.isfinite(ns_values) & (ns_values > 0)
        ns_upper = float(np.quantile(ns_values[ns_valid], 0.995)) if ns_valid.any() else 1.0
        fc_parts = [
            np.asarray(series[name], dtype=float)
            for name in ("calibrate_then_sum_fc", "sum_then_calibrate_fc")
        ]
        fc_valid_parts = [values[np.isfinite(values) & (values > 0)] for values in fc_parts]
        fc_pooled = np.concatenate([values for values in fc_valid_parts if values.size]) if any(
            values.size for values in fc_valid_parts
        ) else np.array([], dtype=float)
        fc_upper = float(np.quantile(fc_pooled, 0.995)) if fc_pooled.size else 1.0
        for cluster_size, color in CLUSTER_SIZE_COLORS.items():
            mask = cluster_sizes == cluster_size
            if not mask.any():
                continue
            _draw_histogram_with_gamma(
                left,
                ns_values[mask],
                bins=bins,
                color=color,
                label=f"{cluster_size} strip{'s' if cluster_size != 1 else ''}",
                upper_limit=ns_upper,
            )
        left.set_xlabel("Summed ToT width [ns]")
        left.set_yscale("log")
        left.set_ylim(bottom=0.5)
        left.grid(alpha=0.2)
        if left.get_legend_handles_labels()[0]:
            left.legend(fontsize=7, loc="upper right")

        for cluster_size, color in CLUSTER_SIZE_COLORS.items():
            mask = cluster_sizes == cluster_size
            if not mask.any():
                continue
            _draw_histogram_with_gamma(
                right,
                fc_parts[0][mask],
                bins=bins,
                color=color,
                label=f"{cluster_size} strips · calibrate then sum",
                upper_limit=fc_upper,
                linestyle="-",
                fit_linestyle=":",
            )
            _draw_histogram_with_gamma(
                right,
                fc_parts[1][mask],
                bins=bins,
                color=color,
                label=f"{cluster_size} strips · sum then calibrate",
                upper_limit=fc_upper,
                linestyle="--",
                fit_linestyle="-.",
            )
        right.set_xlabel("Summed charge [fC]")
        right.set_yscale("log")
        right.set_ylim(bottom=0.5)
        right.grid(alpha=0.2)
        if right.get_legend_handles_labels()[0]:
            right.legend(fontsize=6, loc="upper right", ncol=2)

    fig.suptitle(
        "Task 3 ToT-to-charge calibration order comparison\n"
        f"MINGO{station:02d} · acquisition TT {trigger_combo or 'all'} · {file_count:,} Task-5-completed files · cluster size = active strips per plane; dotted curves are Gamma fits",
        fontsize=14,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return fig


def plot_calibration_order_scatter(
    spectra: Mapping[int, Mapping[str, np.ndarray]],
    *,
    station: int,
    file_count: int,
    trigger_combo: str | None = None,
):
    """Compare per-event plane charge from the two calibration orders."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 11), sharex=True, sharey=True)
    axes = np.asarray(axes).ravel()
    paired: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    all_values: list[np.ndarray] = []
    for plane in range(1, 5):
        series = spectra.get(plane)
        if not series:
            continue
        x = np.asarray(series["calibrate_then_sum_fc"], dtype=float)
        y = np.asarray(series["sum_then_calibrate_fc"], dtype=float)
        cluster_size = np.asarray(series["cluster_size"], dtype=int)
        finite = np.isfinite(x) & np.isfinite(y) & (cluster_size > 0)
        x, y, cluster_size = x[finite], y[finite], cluster_size[finite]
        if x.size:
            paired[plane] = (x, y, cluster_size)
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
        x, y, cluster_size = paired[plane]
        for size, color in CLUSTER_SIZE_COLORS.items():
            mask = cluster_size == size
            if mask.any():
                axis.scatter(
                    x[mask],
                    y[mask],
                    s=6,
                    alpha=0.24,
                    linewidths=0,
                    color=color,
                    label=f"{size} strip{'s' if size != 1 else ''} (N={int(mask.sum()):,})",
                    rasterized=True,
                )
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
        axis.legend(fontsize=7, loc="lower right", ncol=2)

    fig.suptitle(
        "Task 3 charge by calibration order · per-event comparison by cluster size\n"
        f"MINGO{station:02d} · acquisition TT {trigger_combo or 'all'} · {file_count:,} consecutive Task-5-completed files",
        fontsize=14,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig


def plot_plane_charge_by_cluster_size(
    spectra: Mapping[int, Mapping[str, np.ndarray]],
    *,
    station: int,
    file_count: int,
    bins: int = 140,
    trigger_combo: str | None = None,
):
    """Histogram total per-plane charge, colored by active-strip cluster size."""
    fig, axes = plt.subplots(4, 1, figsize=(11, 15), sharey=True)
    for plane, axis in enumerate(np.asarray(axes).ravel(), start=1):
        series = spectra.get(plane)
        axis.set_title(f"Plane {plane}")
        axis.set_ylabel("Counts")
        axis.grid(alpha=0.2)
        if not series:
            axis.text(0.5, 0.5, "Required Task-3 columns unavailable", ha="center", va="center", transform=axis.transAxes)
            axis.set_yscale("log")
            axis.set_ylim(bottom=0.5)
            continue
        values = np.asarray(series["calibrate_then_sum_fc"], dtype=float)
        cluster_sizes = np.asarray(series["cluster_size"], dtype=int)
        valid = np.isfinite(values) & (values > 0)
        upper = float(np.quantile(values[valid], 0.995)) if valid.any() else 1.0
        for size, color in CLUSTER_SIZE_COLORS.items():
            mask = valid & (cluster_sizes == size)
            if not mask.any():
                continue
            axis.hist(
                values[mask],
                bins=bins,
                range=(0.0, upper),
                histtype="step",
                linewidth=1.4,
                color=color,
                label=f"{size} strip{'s' if size != 1 else ''} (N={int(mask.sum()):,})",
            )
        if axis.get_legend_handles_labels()[0]:
            axis.legend(fontsize=8, loc="upper right", ncol=2)
        axis.set_yscale("log")
        axis.set_ylim(bottom=0.5)
    for axis in axes:
        axis.set_xlabel("Total plane charge · strip-calibrated then summed [fC]")
    fig.suptitle(
        "Task 3 total plane charge by active-strip cluster size\n"
        f"MINGO{station:02d} · acquisition TT {trigger_combo or 'all'} · {file_count:,} Task-5-completed files · zero-strip events excluded",
        fontsize=14,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig
