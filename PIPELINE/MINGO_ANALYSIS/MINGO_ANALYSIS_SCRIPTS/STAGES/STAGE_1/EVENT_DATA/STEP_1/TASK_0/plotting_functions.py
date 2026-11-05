from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.step1_rate_plots import create_rate_vs_time_by_task_tt_with_histograms


def _rate_series_by_window(frame: pd.DataFrame, mask: pd.Series, window_seconds: int) -> pd.Series:
    selected = frame.loc[mask, "elapsed_s"]
    if selected.empty:
        return pd.Series(dtype=float)
    window_index = (selected // window_seconds).astype(int)
    counts = window_index.groupby(window_index).size().sort_index()
    return counts.astype(float) / float(window_seconds)


def plot_acquisition_rate_vs_time_by_trigger_type(
    read_df: pd.DataFrame,
    output_path: str | Path,
    *,
    title: str,
    accumulation_window_seconds: int = 60,
) -> bool:
    trigger_column = "acquisition_type" if "acquisition_type" in read_df.columns else "column_6"
    if read_df.empty or "datetime" not in read_df.columns or trigger_column not in read_df.columns:
        return False

    datetimes = pd.to_datetime(read_df["datetime"], errors="coerce")
    valid_mask = datetimes.notna()
    if not valid_mask.any():
        return False

    accumulation_window_seconds = max(1, int(accumulation_window_seconds))
    frame = read_df.loc[valid_mask, [trigger_column]].copy()
    frame.loc[:, "elapsed_s"] = (
        datetimes.loc[valid_mask] - datetimes.loc[valid_mask].min()
    ).dt.total_seconds().astype(int)
    trigger_values = pd.to_numeric(frame[trigger_column], errors="coerce")

    series_by_label: list[tuple[str, pd.Series]] = [
        ("all valid", _rate_series_by_window(frame, pd.Series(True, index=frame.index), accumulation_window_seconds)),
        ("coincidence", _rate_series_by_window(frame, trigger_values.eq(1), accumulation_window_seconds)),
        ("self-trigger", _rate_series_by_window(frame, trigger_values.eq(2), accumulation_window_seconds)),
    ]
    other_mask = ~(trigger_values.eq(1) | trigger_values.eq(2))
    if other_mask.any():
        series_by_label.append(("other/unknown", _rate_series_by_window(frame, other_mask, accumulation_window_seconds)))

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 5))
    for label, counts in series_by_label:
        if counts.empty:
            continue
        ax.plot(counts.index.to_numpy() * accumulation_window_seconds, counts.to_numpy(), linewidth=1.2, label=label)

    ax.set_title(title)
    ax.set_xlabel("Seconds from first valid acquisition timestamp")
    ax.set_ylabel(f"Rate [Hz], {accumulation_window_seconds}s accumulation")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return True


def plot_acquisition_rate_vs_time_by_task_tt_with_histograms(
    read_df: pd.DataFrame,
    output_path: str | Path,
    *,
    title: str,
    tt_column: str = "tt_task0_acq",
    accumulation_window_seconds: int = 60,
    rate_histogram_bins: int = 80,
    y_limit_left: object = None,
    y_limit_right: object = None,
) -> bool:
    fig = create_rate_vs_time_by_task_tt_with_histograms(
        read_df,
        tt_column=tt_column,
        title=title,
        accumulation_window_seconds=accumulation_window_seconds,
        rate_histogram_bins=rate_histogram_bins,
        y_limit_left=y_limit_left,
        y_limit_right=y_limit_right,
    )
    if fig is None:
        return False

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return True
