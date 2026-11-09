#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/TASK_4/task4_chi2_four_plane_plotter.py
Purpose: Task 4 chi2 histogram helper + metadata report generator.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-05-05
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/TASK_4/task4_chi2_four_plane_plotter.py [options]
Inputs: Task 4 chi2 metadata CSV files.
Outputs: PDF report and in-pipeline figure rendering.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
import os
from pathlib import Path
import re
import sys
from typing import Dict, List, Optional, Sequence, Set, Tuple

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import LogNorm
from scipy.stats import chi2 as chi2_dist


SCRIPT_PATH = Path(__file__).resolve()


def detect_repo_root() -> Path:
    for parent in SCRIPT_PATH.parents:
        if (parent / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS").is_dir() and (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file():
            return parent
    raise RuntimeError(f"Could not locate repository root from {SCRIPT_PATH}")


REPO_ROOT = detect_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.plot_utils import pdf_save_rasterized_page  # noqa: E402


STATIONS_ROOT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
PLOTTER_DIR = SCRIPT_PATH.parent
PLOTS_DIR = PLOTTER_DIR / "PLOTS"
DEFAULT_CONFIG_PATH = PLOTTER_DIR / "task4_chi2_four_plane_config.json"
DEFAULT_OUTPUT_FILENAME = "task4_chi2_four_plane_report.pdf"
DEFAULT_HISTOGRAM_COLOR = "#1f77b4"
DEFAULT_FIT_COLOR = "#d62728"
DEFAULT_FIT_LINESTYLE = "--"
DEFAULT_FIT_LINEWIDTH = 1.8
DEFAULT_HIST_ALPHA = 0.85
DEFAULT_VERTICAL_ALPHA = 0.85
DEFAULT_LEGEND_LOC = "upper right"
DEFAULT_PANEL_YLIM = (0.0, 0.22)
DEFAULT_PANEL_XLIM = (0.0, 40.0)
DEFAULT_PANEL_GRID_ALPHA = 0.2
DEFAULT_PANEL_TITLE = "TIM-TH 1234"
DEFAULT_TAIL_ROWS = 0
DEFAULT_MAX_BIN_GAP_HOURS = 3.0

FILENAME_TIMESTAMP_PATTERN = re.compile(r"mi0\d(\d{11})$", re.IGNORECASE)
BIN_COUNT_PATTERN = re.compile(r"^chi2_four_plane_bin_(\d{3})_count$")
BIN_RATE_PATTERN = re.compile(r"^chi2_four_plane_bin_(\d{3})_rate_hz$")
DENOMINATOR_COLUMNS = (
    "count_rate_denominator_seconds",
    "chi2_four_plane_hist_bin_count_rate_denominator_seconds",
)


def configure_matplotlib_style() -> None:
    plt.style.use("default")


def normalize_station_token(token: str) -> Optional[str]:
    cleaned = token.strip().upper()
    if not cleaned:
        return None
    if cleaned.startswith("MINGO"):
        cleaned = cleaned[5:]
    digits = "".join(ch for ch in cleaned if ch.isdigit())
    if not digits:
        return None
    return f"MINGO{int(digits):02d}"


def list_available_stations() -> List[str]:
    if not STATIONS_ROOT.exists():
        return []
    stations: List[str] = []
    for entry in STATIONS_ROOT.iterdir():
        if entry.is_dir() and re.fullmatch(r"MINGO\d{2}", entry.name.upper()):
            stations.append(entry.name.upper())
    stations.sort()
    return stations


def resolve_station_selection(tokens: Sequence[str]) -> List[str]:
    available = list_available_stations()
    if not tokens:
        return available

    selected: List[str] = []
    invalid: List[str] = []
    for token in tokens:
        station = normalize_station_token(str(token))
        if station is None or station not in available:
            invalid.append(str(token))
            continue
        selected.append(station)

    if invalid:
        print(
            "[task4_chi2_four_plane_plotter] Ignoring unknown station(s): "
            + ", ".join(invalid),
            file=sys.stderr,
        )

    return sorted(dict.fromkeys(selected))


def normalize_existing_station_tokens(tokens: Sequence[object]) -> List[str]:
    available = set(list_available_stations())
    selected: List[str] = []
    for token in tokens:
        station = normalize_station_token(str(token))
        if station is None or station not in available:
            continue
        selected.append(station)
    return sorted(dict.fromkeys(selected))


def normalize_basename(value: object) -> str:
    text = str(value).strip()
    if not text:
        return ""
    return Path(text).stem.strip()


def extract_timestamp_from_basename(value: str) -> Optional[datetime]:
    if not value:
        return None

    stem = Path(value).stem.strip()
    if not stem:
        return None

    try:
        return datetime.strptime(stem, "%Y-%m-%d_%H.%M.%S")
    except ValueError:
        pass

    match = FILENAME_TIMESTAMP_PATTERN.search(stem)
    if match:
        digits = match.group(1)
    else:
        digits = "".join(ch for ch in stem if ch.isdigit())
        if len(digits) < 11:
            return None
        digits = digits[-11:]

    try:
        year = 2000 + int(digits[0:2])
        day_of_year = int(digits[2:5])
        hour = int(digits[5:7])
        minute = int(digits[7:9])
        second = int(digits[9:11])
    except ValueError:
        return None

    if not (1 <= day_of_year <= 366):
        return None
    if not (0 <= hour <= 23):
        return None
    if not (0 <= minute <= 59):
        return None
    if not (0 <= second <= 59):
        return None

    base = datetime(year, 1, 1)
    return base + timedelta(
        days=day_of_year - 1,
        hours=hour,
        minutes=minute,
        seconds=second,
    )


def parse_execution_series(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    parsed = pd.to_datetime(text, format="%Y-%m-%d_%H.%M.%S", errors="coerce")
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(text[missing], errors="coerce")
    return parsed


def station_metadata_path(station: str) -> Path:
    candidates = (
        STATIONS_ROOT
        / station
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / "TASK_4"
        / "METADATA"
        / "task_4_metadata_chi2_four_plane.csv",
        STATIONS_ROOT
        / station
        / "FIRST_STAGE"
        / "EVENT_DATA"
        / "STEP_1"
        / "TASK_4"
        / "METADATA"
        / "task_4_metadata_chi2_four_plane.csv",
    )
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _select_bin_columns(columns: Sequence[str], rate_hz: bool) -> List[str]:
    pattern = BIN_RATE_PATTERN if rate_hz else BIN_COUNT_PATTERN
    indexed: List[Tuple[int, str]] = []
    for column in columns:
        match = pattern.match(str(column))
        if not match:
            continue
        indexed.append((int(match.group(1)), str(column)))
    indexed.sort(key=lambda item: item[0])
    return [column for _, column in indexed]


def _load_station_metadata(station: str, tail_rows: int) -> pd.DataFrame:
    path = station_metadata_path(station)
    if not path.exists():
        return pd.DataFrame()

    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        print(
            f"[task4_chi2_four_plane_plotter] Failed to read {path}: {exc}",
            file=sys.stderr,
        )
        return pd.DataFrame()

    if frame.empty:
        return frame

    if "filename_base" in frame.columns:
        frame["basename"] = frame["filename_base"].map(normalize_basename)
        frame["plot_timestamp"] = frame["basename"].map(
            lambda value: extract_timestamp_from_basename(normalize_basename(value))
        )
        frame["plot_timestamp"] = pd.to_datetime(frame["plot_timestamp"], errors="coerce")
    else:
        frame["plot_timestamp"] = pd.NaT

    frame = frame.sort_values("plot_timestamp", na_position="last").reset_index(drop=True)
    if tail_rows > 0:
        frame = frame.tail(tail_rows).copy()

    return frame


def compute_time_edges(times_num: np.ndarray, fallback_seconds: float = 60.0) -> np.ndarray:
    if times_num.size == 1:
        half = max(fallback_seconds / 86400.0 / 2.0, 1.0 / 1440.0)
        return np.array([times_num[0] - half, times_num[0] + half])

    diffs = np.diff(times_num)
    positive = diffs[diffs > 0]
    if positive.size == 0:
        delta = max(fallback_seconds / 86400.0, 1.0 / 1440.0)
    else:
        delta = float(np.median(positive))

    edges = np.empty(times_num.size + 1, dtype=float)
    edges[1:-1] = (times_num[:-1] + times_num[1:]) / 2.0
    edges[0] = times_num[0] - delta / 2.0
    edges[-1] = times_num[-1] + delta / 2.0
    return edges


def build_intervalized_hist_matrix(
    times_num: np.ndarray,
    freq_matrix: np.ndarray,
    max_bin_gap_hours: float,
    fallback_seconds: float,
) -> Tuple[np.ndarray, np.ndarray]:
    if times_num.size == 0:
        return np.array([], dtype=float), np.empty((freq_matrix.shape[0], 0), dtype=float)

    fallback_days = max(float(fallback_seconds), 1.0) / 86400.0
    diffs = np.diff(times_num)
    positive_diffs = diffs[diffs > 0]
    if positive_diffs.size > 0:
        tail_days = float(np.median(positive_diffs))
    else:
        tail_days = fallback_days

    if np.isfinite(max_bin_gap_hours):
        max_gap_days = max(float(max_bin_gap_hours), 1.0 / 3600.0) / 24.0
        tail_days = min(tail_days, max_gap_days)
    else:
        max_gap_days = np.inf

    intervals: List[Tuple[float, float, Optional[int]]] = []
    for idx, start in enumerate(times_num):
        start_v = float(start)
        if idx < times_num.size - 1:
            next_v = float(times_num[idx + 1])
            if np.isfinite(max_gap_days):
                end_v = min(next_v, start_v + max_gap_days)
            else:
                end_v = next_v
        else:
            end_v = start_v + max(tail_days, fallback_days / 2.0)

        if end_v <= start_v:
            end_v = start_v + fallback_days / 2.0

        intervals.append((start_v, end_v, idx))

        if idx < times_num.size - 1:
            next_v = float(times_num[idx + 1])
            if end_v < next_v:
                intervals.append((end_v, next_v, None))

    x_edges = np.empty(len(intervals) + 1, dtype=float)
    plot_matrix = np.empty((freq_matrix.shape[0], len(intervals)), dtype=float)
    x_edges[0] = intervals[0][0]

    for col_idx, (_start_v, end_v, src_col) in enumerate(intervals):
        x_edges[col_idx + 1] = end_v
        if src_col is None:
            plot_matrix[:, col_idx] = np.nan
        else:
            plot_matrix[:, col_idx] = freq_matrix[:, src_col]

    return x_edges, plot_matrix


def _resolve_panel_value(config: Dict[str, object], key: str, default: float) -> float:
    raw = config.get(key, default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _select_existing_column(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    available = {str(column) for column in columns}
    for candidate in candidates:
        if candidate in available:
            return candidate
    return None


def render_task4_chi2_four_plane_histogram_to_pdf(
    *,
    sigmafit_df: pd.DataFrame,
    tt_column: str,
    value_column: str,
    output_path: Path,
    title: str = "Task 4 Chi2 Four-Plane Histogram (TIM-TH 1234)",
    x_label: str = "Chi2",
    y_label: str = "Density",
    x_limit: Tuple[float, float] = DEFAULT_PANEL_XLIM,
    y_limit: Tuple[float, float] = DEFAULT_PANEL_YLIM,
    histogram_color: str = DEFAULT_HISTOGRAM_COLOR,
    fit_color: str = DEFAULT_FIT_COLOR,
    fit_linestyle: str = DEFAULT_FIT_LINESTYLE,
    fit_linewidth: float = DEFAULT_FIT_LINEWIDTH,
    histogram_alpha: float = DEFAULT_HIST_ALPHA,
    vertical_alpha: float = DEFAULT_VERTICAL_ALPHA,
    legend_location: str = DEFAULT_LEGEND_LOC,
    grid_alpha: float = DEFAULT_PANEL_GRID_ALPHA,
    expected_ndf: int = 12,
    bin_count: int = 100,
    value_max: float = 100.0,
    reference_fit_hi: float = 6.0,
    reference_fit_total: float = 300.0,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sigmafit_tt = pd.to_numeric(sigmafit_df[tt_column], errors="coerce")

    four_plane_values = sigmafit_df.loc[sigmafit_tt == 1234.0, value_column]
    four_plane_values = pd.to_numeric(four_plane_values, errors="coerce")
    four_plane_values = four_plane_values[four_plane_values < float(value_max)]
    four_plane_values = four_plane_values.dropna().to_numpy(dtype=float)

    if four_plane_values.size == 0:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.text(0.5, 0.5, "No TIM-TH 1234 chi2 values available.", ha="center", va="center")
        ax.axis("off")
        pdf = PdfPages(output_path)
        pdf_save_rasterized_page(pdf, fig)
        pdf.close()
        plt.close(fig)
        return

    bins = np.linspace(0.0, float(value_max), int(bin_count))
    with PdfPages(output_path) as pdf:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(
            four_plane_values,
            bins=bins,
            density=True,
            alpha=float(histogram_alpha),
            color=histogram_color,
            edgecolor="black",
            linewidth=0.5,
            label="Measured",
        )

        fit_x = np.linspace(0.0, float(value_max), 400)
        fit_y = chi2_dist.pdf(fit_x, df=int(expected_ndf))
        ax.plot(
            fit_x,
            fit_y,
            color=fit_color,
            linestyle=fit_linestyle,
            linewidth=float(fit_linewidth),
            label=f"chi2 PDF (ndf={int(expected_ndf)})",
        )

        try:
            fit_hi_numeric = float(reference_fit_hi)
        except (TypeError, ValueError):
            fit_hi_numeric = float("nan")
        if np.isfinite(fit_hi_numeric):
            ax.axvline(
                fit_hi_numeric,
                color=fit_color,
                linestyle=":",
                linewidth=1.2,
                alpha=float(vertical_alpha),
                label=f"Reference fit hi ({fit_hi_numeric:g})",
            )

        ax.set_xlim(*x_limit)
        ax.set_ylim(*y_limit)
        ax.set_title(title)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        ax.grid(True, alpha=float(grid_alpha))
        ax.legend(loc=legend_location)

        # Scale in Y
        ax.set_yscale("log")

        pdf_save_rasterized_page(pdf, fig)
        plt.close(fig)


def render_task4_chi2_four_plane_histogram(
    *,
    working_df: pd.DataFrame,
    base_cond: pd.Series,
    tt_column: str,
    global_variables: Dict[str, object],
    fiducial_pass_index: Optional[pd.Index] = None,
    fig_idx: int,
    figure_directory: str,
    save_plot_figure,
    save_plots: bool = False,
    show_plots: bool = False,
    plot_list: Optional[List[str]] = None,
) -> int:
    if tt_column not in working_df.columns or "tim_th_chi_sigmafit_1234" not in working_df.columns:
        return fig_idx

    tt_numeric = pd.to_numeric(working_df[tt_column], errors="coerce")
    chi2_numeric = pd.to_numeric(working_df["tim_th_chi_sigmafit_1234"], errors="coerce")
    selection = base_cond & tt_numeric.eq(1234.0) & chi2_numeric.ge(0.0) & chi2_numeric.le(40.0)
    selected_values = chi2_numeric.loc[selection].dropna()
    values = selected_values.to_numpy(dtype=float)
    if values.size == 0:
        return fig_idx

    fiducial_values = np.array([], dtype=float)
    nonfiducial_values = np.array([], dtype=float)
    if fiducial_pass_index is not None:
        selected_index = selected_values.index
        in_fiducial = selected_index.isin(fiducial_pass_index)
        fiducial_values = selected_values.loc[in_fiducial].to_numpy(dtype=float)
        nonfiducial_values = selected_values.loc[~in_fiducial].to_numpy(dtype=float)

    title = str(global_variables.get("tim_th_chi_sigmafit_1234_title", DEFAULT_PANEL_TITLE))
    bins = np.linspace(0.0, 40.0, 100)

    fig, ax = plt.subplots(figsize=(8, 5))
    if fiducial_pass_index is not None:
        if fiducial_values.size > 0:
            ax.hist(
                fiducial_values,
                bins=bins,
                histtype="step",
                linewidth=1.8,
                color="#1f77b4",
                label=f"Inside track-eff fiducial (n={fiducial_values.size:,})",
            )
        if nonfiducial_values.size > 0:
            ax.hist(
                nonfiducial_values,
                bins=bins,
                histtype="step",
                linewidth=1.8,
                color="#d62728",
                label=f"Outside track-eff fiducial (n={nonfiducial_values.size:,})",
            )
    else:
        ax.hist(
            values,
            bins=bins,
            histtype="step",
            linewidth=1.8,
            color=DEFAULT_HISTOGRAM_COLOR,
            label="Measured",
        )
    ax.set_xlim(*DEFAULT_PANEL_XLIM)
    # ax.set_yscale("log", nonpositive="clip")
    ax.set_ylim(bottom=0.8)
    ax.set_title(title)
    ax.set_xlabel("Chi2")
    ax.set_ylabel("Counts")
    ax.grid(True, alpha=DEFAULT_PANEL_GRID_ALPHA)
    ax.legend(loc=DEFAULT_LEGEND_LOC)
    plt.tight_layout()

    if save_plots:
        final_filename = f"{fig_idx}_tim_th_chi_sigmafit_1234_histogram.png"
        save_fig_path = os.path.join(figure_directory, final_filename)
        if plot_list is not None:
            plot_list.append(save_fig_path)
        save_plot_figure(
            save_fig_path,
            fig=fig,
            format="png",
            alias="tim_th_chi_sigmafit_1234_histogram",
        )
    if show_plots:
        plt.show()
    plt.close(fig)

    return fig_idx + 1


def _plot_station_page(
    station: str,
    frame: pd.DataFrame,
    pdf: PdfPages,
    max_bin_gap_hours: float,
) -> None:
    fig = plt.figure(figsize=(16, 9))
    grid = fig.add_gridspec(nrows=2, ncols=1, height_ratios=(1.0, 4.0))
    ax_summary = fig.add_subplot(grid[0, 0])
    ax_hist = fig.add_subplot(grid[1, 0])

    if frame.empty:
        ax_summary.axis("off")
        ax_hist.axis("off")
        ax_summary.text(
            0.5,
            0.5,
            f"{station}\nNo task_4_metadata_chi2_four_plane.csv data found.",
            ha="center",
            va="center",
            fontsize=12,
        )
        pdf_save_rasterized_page(pdf, fig, bbox_inches="tight")
        plt.close(fig)
        return

    numeric_frame = frame.copy()
    denominator_column = _select_existing_column(numeric_frame.columns, DENOMINATOR_COLUMNS)
    for column in (
        "chi2_four_plane_hist_n",
        "chi2_four_plane_hist_plot_lt_100_n",
        "chi2_four_plane_hist_min",
        "chi2_four_plane_hist_max",
    ):
        if column in numeric_frame.columns:
            numeric_frame[column] = pd.to_numeric(numeric_frame[column], errors="coerce")
    if denominator_column is not None:
        numeric_frame[denominator_column] = pd.to_numeric(
            numeric_frame[denominator_column], errors="coerce"
        )

    timestamps = pd.to_datetime(numeric_frame["plot_timestamp"], errors="coerce")
    has_timestamps = timestamps.notna()
    count_columns = _select_bin_columns(frame.columns, rate_hz=False)
    rate_columns = _select_bin_columns(frame.columns, rate_hz=True)
    bin_columns: List[str]
    plotted_unit_label: str
    source_label: str
    display_label: str
    if count_columns and denominator_column is not None:
        bin_columns = count_columns
        source_label = "chi2_four_plane_bin_*_count"
        display_label = "chi2_four_plane_bin_*_count / count_rate_denominator_seconds"
        plotted_unit_label = "Hz / bin"
    elif rate_columns:
        bin_columns = rate_columns
        source_label = "chi2_four_plane_bin_*_rate_hz"
        display_label = "stored chi2_four_plane_bin_*_rate_hz"
        plotted_unit_label = "Hz / bin"
    else:
        bin_columns = count_columns
        source_label = "chi2_four_plane_bin_*_count"
        display_label = "raw chi2_four_plane_bin_*_count (no denominator available)"
        plotted_unit_label = "counts / bin"

    ax_summary.axis("off")
    details: List[str] = [f"station: {station}", f"rows: {len(frame)}"]
    if has_timestamps.any():
        first_ts = pd.Timestamp(timestamps[has_timestamps].min())
        last_ts = pd.Timestamp(timestamps[has_timestamps].max())
        details.append(f"time range: {first_ts} -> {last_ts}")
    details.append(f"source bins: {source_label}")
    details.append(f"display bins: {display_label}")
    details.append(f"bin columns: {len(bin_columns)}")
    ax_summary.text(
        0.02,
        0.98,
        "\n".join(details),
        ha="left",
        va="top",
        family="monospace",
        fontsize=9,
    )

    if not bin_columns:
        ax_hist.axis("off")
        ax_hist.text(0.5, 0.5, "No chi2 histogram bin columns found.", ha="center", va="center")
        pdf_save_rasterized_page(pdf, fig, bbox_inches="tight")
        plt.close(fig)
        return

    if not has_timestamps.any():
        ax_hist.axis("off")
        ax_hist.text(
            0.5,
            0.5,
            "No valid basename timestamps found in filename_base.",
            ha="center",
            va="center",
        )
        pdf_save_rasterized_page(pdf, fig, bbox_inches="tight")
        plt.close(fig)
        return

    plot_frame = numeric_frame.loc[has_timestamps].copy()
    plot_frame["plot_timestamp"] = pd.to_datetime(plot_frame["plot_timestamp"], errors="coerce")
    time_nums = mdates.date2num(plot_frame["plot_timestamp"].to_numpy())
    sort_idx = np.argsort(time_nums)
    time_nums = time_nums[sort_idx]

    freq_matrix = (
        plot_frame[bin_columns]
        .fillna(0)
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0)
        .to_numpy(dtype=float)
        .T
    )
    freq_matrix = freq_matrix[:, sort_idx]

    if denominator_column is not None:
        denominator_seconds = pd.to_numeric(
            plot_frame[denominator_column], errors="coerce"
        ).to_numpy(dtype=float)
    else:
        denominator_seconds = np.array([], dtype=float)
    denominator_seconds = denominator_seconds[sort_idx] if denominator_seconds.size else denominator_seconds
    fallback_seconds = (
        float(np.nanmedian(denominator_seconds))
        if denominator_seconds.size and np.isfinite(np.nanmedian(denominator_seconds))
        else 60.0
    )
    if not np.isfinite(fallback_seconds) or fallback_seconds <= 0:
        fallback_seconds = 60.0

    if count_columns and denominator_column is not None:
        valid_denominator = np.isfinite(denominator_seconds) & (denominator_seconds > 0)
        normalized_matrix = np.full(freq_matrix.shape, np.nan, dtype=float)
        if np.any(valid_denominator):
            normalized_matrix[:, valid_denominator] = (
                freq_matrix[:, valid_denominator] / denominator_seconds[valid_denominator]
            )
        freq_matrix = normalized_matrix

    station_max_gap = np.inf if station == "MINGO00" else max_bin_gap_hours
    x_edges, plot_matrix = build_intervalized_hist_matrix(
        times_num=time_nums,
        freq_matrix=freq_matrix,
        max_bin_gap_hours=station_max_gap,
        fallback_seconds=fallback_seconds,
    )

    n_bins = len(bin_columns)
    if "chi2_four_plane_hist_min" in plot_frame.columns:
        hist_min_series = pd.to_numeric(plot_frame["chi2_four_plane_hist_min"], errors="coerce")
        hist_min = float(hist_min_series.median())
    else:
        hist_min = 0.0
    if "chi2_four_plane_hist_max" in plot_frame.columns:
        hist_max_series = pd.to_numeric(plot_frame["chi2_four_plane_hist_max"], errors="coerce")
        hist_max = float(hist_max_series.median())
    else:
        hist_max = 100.0
    if not np.isfinite(hist_max) or hist_max <= hist_min:
        hist_min = 0.0
        hist_max = 100.0

    y_edges = np.linspace(hist_min, hist_max, n_bins + 1)
    masked = np.ma.masked_where(~np.isfinite(plot_matrix) | (plot_matrix <= 0), plot_matrix)
    positive_values = plot_matrix[np.isfinite(plot_matrix) & (plot_matrix > 0)]
    norm = None
    if positive_values.size:
        vmin = float(np.nanmin(positive_values))
        vmax = float(np.nanmax(positive_values))
        # if np.isfinite(vmin) and np.isfinite(vmax) and vmax > 0:
        #     if vmax <= vmin:
        #         vmin = max(vmax * 0.5, 1e-12)
        #     norm = LogNorm(vmin=max(vmin, 1e-12), vmax=vmax)

    ax_hist.set_facecolor(plt.get_cmap("viridis")(0.0))
    mesh = ax_hist.pcolormesh(
        x_edges,
        y_edges,
        masked,
        cmap="viridis",
        norm=norm,
        shading="auto",
    )
    colorbar = fig.colorbar(mesh, ax=ax_hist, pad=0.01)
    colorbar.set_label(f"{plotted_unit_label} (log color)")

    ax_hist.set_title(f"{station} | Chi2 four-plane histogram rate over file time")
    ax_hist.set_xlabel("Basename timestamp")
    ax_hist.set_ylabel("Chi2 bin")
    ax_hist.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d\n%H:%M"))
    ax_hist.grid(False)

    pdf_save_rasterized_page(pdf, fig, bbox_inches="tight")
    plt.close(fig)


def _load_json_config(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    if path.stat().st_size == 0:
        return {}
    with path.open("r", encoding="utf-8") as handle:
        try:
            loaded = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON config: {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Config file must contain a JSON object: {path}")
    return loaded


def _resolve_output_path(raw_output: Optional[str], config_path: Path) -> Path:
    if not raw_output:
        return (PLOTS_DIR / DEFAULT_OUTPUT_FILENAME).resolve()
    candidate = Path(str(raw_output)).expanduser()
    if candidate.is_absolute():
        return candidate
    return (config_path.parent / candidate).resolve()


def _resolve_runtime_options(
    args: argparse.Namespace,
) -> Tuple[Path, List[str], int, float]:
    config_path = Path(args.config).expanduser().resolve()
    config = _load_json_config(config_path)

    if args.stations is not None:
        stations = resolve_station_selection(args.stations)
    else:
        stations = resolve_station_selection(normalize_existing_station_tokens(config.get("stations", [])))

    output_raw = args.output
    if output_raw is None:
        raw = config.get("output")
        output_raw = str(raw) if raw is not None else None
    output_path = _resolve_output_path(output_raw, config_path)

    if args.tail_rows is not None:
        tail_rows = int(args.tail_rows)
    else:
        try:
            tail_rows = int(config.get("tail_rows", DEFAULT_TAIL_ROWS))
        except (TypeError, ValueError):
            tail_rows = DEFAULT_TAIL_ROWS
    tail_rows = max(0, tail_rows)

    if args.max_bin_gap_hours is not None:
        max_bin_gap_hours = float(args.max_bin_gap_hours)
    else:
        try:
            max_bin_gap_hours = float(
                config.get("max_bin_gap_hours", DEFAULT_MAX_BIN_GAP_HOURS)
            )
        except (TypeError, ValueError):
            max_bin_gap_hours = DEFAULT_MAX_BIN_GAP_HOURS
    if max_bin_gap_hours <= 0:
        raise ValueError("'max_bin_gap_hours' must be > 0")

    return output_path, stations, tail_rows, max_bin_gap_hours


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate Task 4 chi2 four-plane metadata PDF report."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Path to JSON config (default: {DEFAULT_CONFIG_PATH}).",
    )
    parser.add_argument(
        "--stations",
        nargs="+",
        default=None,
        help="Station override (e.g. MINGO00 MINGO01).",
    )
    parser.add_argument(
        "--tail-rows",
        type=int,
        default=None,
        help="If set, only use the last N metadata rows per station.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output PDF path override (absolute or config-relative).",
    )
    parser.add_argument(
        "--max-bin-gap-hours",
        type=float,
        default=None,
        help="Max histogram-bin duration to next file timestamp (hours). Ignored for MINGO00.",
    )
    return parser


def main() -> None:
    configure_matplotlib_style()
    args = _build_parser().parse_args()
    output_path, stations, tail_rows, max_bin_gap_hours = _resolve_runtime_options(args)
    if not stations:
        raise RuntimeError("No stations selected or discovered.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(output_path) as pdf:
        for station in stations:
            frame = _load_station_metadata(station, tail_rows=tail_rows)
            _plot_station_page(
                station=station,
                frame=frame,
                pdf=pdf,
                max_bin_gap_hours=max_bin_gap_hours,
            )

    print(f"Saved Task 4 chi2 report: {output_path}")


if __name__ == "__main__":
    main()
