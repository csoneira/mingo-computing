"""
DATAFLOW_v3 Script Header v1
Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/common/debug_plots.py
Purpose: Debug plots.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/common/debug_plots.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import math
import os
import re
from typing import Iterable, Mapping, Sequence

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", text.strip())
    return cleaned.strip("_") or "debug"


def _normalize_thresholds(value) -> list[float]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, np.ndarray)):
        return [float(v) for v in value if v is not None]
    return [float(value)]


def _histogram_values(series) -> tuple[np.ndarray, list[str] | None, str]:
    """Return finite plottable values for numeric, datetime, or categorical data."""
    raw = np.asarray(series)
    if np.issubdtype(raw.dtype, np.datetime64):
        nanoseconds = raw.astype("datetime64[ns]").astype(np.int64)
        missing = nanoseconds == np.iinfo(np.int64).min
        values = nanoseconds.astype(float) / 1_000_000_000.0
        values[missing] = np.nan
        return values[np.isfinite(values)], None, "Unix time [s]"

    try:
        values = np.asarray(series, dtype=float)
        return values, None, "value"
    except (TypeError, ValueError):
        categories: list[str] = []
        category_index: dict[str, int] = {}
        encoded: list[float] = []
        for value in raw:
            if value is None:
                continue
            try:
                if bool(np.asarray(value != value).item()):
                    continue
            except (TypeError, ValueError):
                pass
            label = str(value)
            if label not in category_index:
                category_index[label] = len(categories)
                categories.append(label)
            encoded.append(float(category_index[label]))
        return np.asarray(encoded, dtype=float), categories, "category"


def _filter_numeric_histogram_values(
    values: np.ndarray,
    *,
    exclude_zeros: bool,
    absolute_limit: float | None,
) -> tuple[np.ndarray, int, int]:
    """Filter finite numeric values and return distinct omission counts."""
    zero_mask = values == 0 if exclude_zeros else np.zeros(values.size, dtype=bool)
    outside_mask = (
        np.abs(values) > absolute_limit
        if absolute_limit is not None
        else np.zeros(values.size, dtype=bool)
    )
    keep = np.isfinite(values) & ~(zero_mask | outside_mask)
    return values[keep], int(np.count_nonzero(zero_mask)), int(np.count_nonzero(outside_mask))


def _histogram_axis_family(column: str) -> str | None:
    """Identify channel charge/time columns that can share a physical x axis."""
    name = str(column).lower()
    if re.search(r"date|datetime|timestamp|epoch", name):
        return None
    if "charge" in name:
        return "charge"
    if "time" in name or re.search(r"(?:^|_)(?:tdif|tsum|delta_tsum)(?:_|$)", name):
        return "time"

    # Stage-1 channel fields use both p1_s1_ef_q and P1_s1_Q_sum forms.
    # Match terminal observables only, avoiding coefficients such as T_slew
    # and calibration parameters that happen to contain Q or T in their name.
    channel_match = re.match(r"^p?\d+_s\d+_(.+)$", name)
    if channel_match is None:
        return None
    field = channel_match.group(1)
    if re.search(r"(?:^|_)(?:ef|eb)_q$|(?:^|_)(?:qf|qb|qsum|qdif)(?:_|$)|(?:^|_)q(?:_sum|_f|_b)$", field):
        return "charge"
    if re.search(r"(?:^|_)(?:ef|eb)_t$|(?:^|_)t(?:_sum|_dif)$|(?:^|_)(?:tdif|tsum)(?:_|$)", field):
        return "time"
    return None


def plot_debug_histograms(
    df,
    columns: Sequence[str],
    thresholds: Mapping[str, Iterable[float]] | None,
    title: str,
    out_dir: str,
    fig_idx: int = 1,
    *,
    bins: int = 80,
    max_cols_per_fig: int = 12,
    show: bool = False,
    y_scale: str = "log",
    exclude_zeros: bool = True,
    absolute_limit: float | None = None,
    clip_ranges: Mapping[str, tuple[float, float]] | None = None,
    annotate_omissions: bool = False,
) -> int:
    """Save debug histogram grids for *columns*, with optional threshold lines."""
    if df is None or not columns:
        return fig_idx

    if thresholds is None:
        thresholds = {}
    if clip_ranges is None:
        clip_ranges = {}

    os.makedirs(out_dir, exist_ok=True)

    # Chunk columns to keep figures readable.
    for start in range(0, len(columns), max_cols_per_fig):
        chunk = columns[start : start + max_cols_per_fig]
        ncols = 3
        nrows = max(1, math.ceil(len(chunk) / ncols))
        fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 4 * nrows))
        axes = np.atleast_1d(axes).ravel()

        first_axis_by_family = {}
        for ax, col in zip(axes, chunk):
            family = _histogram_axis_family(col)
            if family is None:
                continue
            if family in first_axis_by_family:
                ax.sharex(first_axis_by_family[family])
            else:
                first_axis_by_family[family] = ax

        for ax, col in zip(axes, chunk):
            if col not in df.columns:
                ax.axis("off")
                continue
            values, category_labels, xlabel = _histogram_values(df[col])
            zeros_not_plotted = 0
            outside_window_not_plotted = 0
            clipped_count = 0
            clip_range = None
            if category_labels is None and xlabel == "value":
                (
                    values,
                    zeros_not_plotted,
                    outside_window_not_plotted,
                ) = _filter_numeric_histogram_values(
                    values,
                    exclude_zeros=exclude_zeros,
                    absolute_limit=absolute_limit,
                )
                clip_range = clip_ranges.get(col)
                if clip_range is not None:
                    lower, upper = map(float, clip_range)
                    clipped_count = int(np.count_nonzero((values < lower) | (values > upper)))
                    values = np.clip(values, lower, upper)
            title_text = col
            if annotate_omissions:
                title_text = (
                    f"{col}\n0s={zeros_not_plotted}; omitted={outside_window_not_plotted}"
                )
                if clip_range is not None:
                    title_text += f"; clipped={clipped_count}"
            if values.size == 0:
                ax.text(0.5, 0.5, "No plottable data", ha="center", va="center")
                ax.set_title(title_text)
                if annotate_omissions:
                    ax.set_xticks([])
                    ax.set_yticks([])
                    for spine in ax.spines.values():
                        spine.set_visible(False)
                else:
                    ax.axis("off")
                continue

            if category_labels is not None:
                histogram_bins = np.arange(-0.5, len(category_labels) + 0.5, 1.0)
                density = False
            else:
                finite_values = np.asarray(values, dtype=float)
                finite_values = finite_values[np.isfinite(finite_values)]
                histogram_bins = np.unique(
                    np.quantile(finite_values, np.linspace(0.0, 1.0, max(1, int(bins)) + 1))
                )
                if histogram_bins.size < 2:
                    center = float(finite_values[0])
                    half_width = max(abs(center) * 1e-6, 0.5)
                    histogram_bins = np.array([center - half_width, center + half_width])
                density = True
                xlabel = f"{xlabel} (quantile-width bins)"
            # Histogram limits follow the retained/clipped observations. A
            # configured clip range changes values, not the displayed axis span.
            # Numeric debug histograms use quantile edges, so bin widths adapt
            # to the local data density instead of staying uniform.
            ax.hist(values, bins=histogram_bins, color="C0", alpha=0.7, density=density)
            if y_scale in {"linear", "log"}:
                ax.set_yscale(y_scale)
            else:
                ax.set_yscale("log")
            ax.set_title(title_text)
            ax.set_xlabel(xlabel)
            ax.set_ylabel("probability density" if density else "count")
            if category_labels is not None and len(category_labels) <= 20:
                ax.set_xticks(range(len(category_labels)))
                ax.set_xticklabels(category_labels, rotation=45, ha="right", fontsize=7)

            line_values = _normalize_thresholds(thresholds.get(col))
            if line_values:
                ymin, ymax = ax.get_ylim()
                for value in line_values:
                    ax.axvline(value, color="red", linestyle="--", linewidth=1)
                    ax.text(
                        value,
                        ymax * 0.95,
                        f"{value:g}",
                        rotation=90,
                        color="red",
                        va="top",
                        ha="right",
                        fontsize=8,
                    )
        # Hide any unused axes.
        for ax in axes[len(chunk) :]:
            ax.axis("off")

        fig.suptitle(title, fontsize=12)
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        filename = f"{fig_idx}_debug_{_slugify(title)}.png"
        fig.savefig(os.path.join(out_dir, filename), dpi=150)
        if show:
            plt.show()
        plt.close(fig)
        fig_idx += 1

    return fig_idx


def plot_debug_histogram_binning_comparison(
    df,
    columns: Sequence[str],
    clip_ranges: Mapping[str, tuple[float, float]],
    title: str,
    out_path: str,
    *,
    fixed_bins: int = 80,
) -> bool:
    """Compare fixed-width and equal-count adaptive bins for a focused debug page."""
    available = [column for column in columns if column in df.columns]
    if not available:
        return False

    fig, axes = plt.subplots(len(available), 4, figsize=(25, 3.0 * len(available)), squeeze=False)
    # Keep charge and time on independent shared scales. The width-distribution
    # column is shared within each group too, since charge-bin widths and
    # time-bin widths have different units.
    first_row_by_kind: dict[str, int] = {}
    for row, column in enumerate(available):
        kind = "charge" if column.lower().endswith("_q") else "time"
        if kind in first_row_by_kind:
            reference_row = first_row_by_kind[kind]
            for col_idx in range(4):
                axes[row, col_idx].sharex(axes[reference_row, col_idx])
        else:
            first_row_by_kind[kind] = row

    for row, column in enumerate(available):
        try:
            values = df[column].to_numpy(dtype=float, na_value=np.nan)
        except TypeError:
            values = np.asarray(df[column], dtype=float)
        values = values[np.isfinite(values) & (values != 0)]
        lower, upper = map(float, clip_ranges[column])
        clipped = int(np.count_nonzero((values < lower) | (values > upper)))
        values = np.clip(values, lower, upper)

        fixed_ax, adaptive_ax, width_ax, narrow_ax = axes[row]
        if values.size:
            fixed_ax.hist(
                values,
                bins=fixed_bins,
                density=True,
                color="C0",
                alpha=0.75,
            )
            edges = np.unique(np.quantile(values, np.linspace(0, 1, fixed_bins + 1)))
            if len(edges) < 2:
                edges = np.linspace(lower, upper, fixed_bins + 1)
            adaptive_ax.hist(values, bins=edges, density=True, color="C1", alpha=0.75)
            adaptive_title = f"Adaptive quantile ({len(edges) - 1}/{fixed_bins} bins)"
            quantile_widths = np.diff(edges)
            quantile_widths = quantile_widths[np.isfinite(quantile_widths) & (quantile_widths > 0)]
            if quantile_widths.size:
                width_ax.hist(quantile_widths, bins=20, color="C2", alpha=0.75)
                width_ax.set_xscale("log")
            else:
                width_ax.text(
                    0.5,
                    0.5,
                    "No distinct quantile widths",
                    ha="center",
                    va="center",
                    transform=width_ax.transAxes,
                )
            all_widths = np.diff(edges)
            all_counts, _ = np.histogram(values, bins=edges)
            narrow_mask = np.isfinite(all_widths) & (all_widths > 0) & (all_widths < 20)
            if narrow_mask.any():
                density = all_counts[narrow_mask] / (values.size * all_widths[narrow_mask])
                narrow_ax.bar(
                    edges[:-1][narrow_mask],
                    density,
                    width=all_widths[narrow_mask],
                    align="edge",
                    color="C3",
                    alpha=0.75,
                )
                selected_bin_count = int(narrow_mask.sum())
            else:
                narrow_ax.text(
                    0.5,
                    0.5,
                    "No bins narrower than 20",
                    ha="center",
                    va="center",
                    transform=narrow_ax.transAxes,
                )
                selected_bin_count = 0
        else:
            for ax in (fixed_ax, adaptive_ax, width_ax, narrow_ax):
                ax.text(0.5, 0.5, "No nonzero plottable data", ha="center", va="center", transform=ax.transAxes)
            adaptive_title = "Adaptive quantile"
            selected_bin_count = 0

        fixed_ax.set_title(f"{column}: fixed ({fixed_bins} bins); clipped={clipped}")
        adaptive_ax.set_title(f"{column}: {adaptive_title}; clipped={clipped}")
        width_ax.set_title(f"{column}: Δ quantile-edge widths")
        width_ax.set_xlabel("Bin width (log scale)")
        width_ax.set_ylabel("Number of bins")
        width_ax.grid(alpha=0.2)
        narrow_ax.set_title(f"{column}: adaptive bins with width <20 ({selected_bin_count})")
        narrow_ax.set_xlabel("value")
        narrow_ax.set_ylabel("Probability density")
        narrow_ax.set_yscale("log")
        narrow_ax.grid(alpha=0.2)
        for ax in (fixed_ax, adaptive_ax):
            ax.set_yscale("log")
            ax.set_ylabel("Probability density")
            ax.set_xlabel("value")
            ax.grid(alpha=0.2)

    fig.suptitle(title, fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return True
