from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


TASK_TT_COLOR_MAP: dict[int, str] = {
    1: "#1f77b4",
    2: "#ff7f0e",
    3: "#2ca02c",
    4: "#d62728",
    12: "#9467bd",
    13: "#8c564b",
    14: "#e377c2",
    23: "#7f7f7f",
    24: "#bcbd22",
    34: "#17becf",
    123: "#4e79a7",
    124: "#f28e2b",
    134: "#59a14f",
    234: "#e15759",
    1234: "#76b7b2",
}


def _positive_int(value: object, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        resolved = default
    resolved = max(minimum, resolved)
    if maximum is not None:
        resolved = min(maximum, resolved)
    return resolved


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(resolved):
        return None
    return resolved


def _task_tt_color(task_tt: int) -> str:
    if task_tt in TASK_TT_COLOR_MAP:
        return TASK_TT_COLOR_MAP[task_tt]
    palette = plt.get_cmap("tab20").colors
    index = abs(int(task_tt)) % len(palette)
    color = palette[index]
    return "#{:02x}{:02x}{:02x}".format(
        int(round(color[0] * 255)),
        int(round(color[1] * 255)),
        int(round(color[2] * 255)),
    )


def create_rate_vs_time_by_task_tt_with_histograms(
    dataframe: pd.DataFrame,
    *,
    tt_column: str,
    title: str,
    accumulation_window_seconds: int = 60,
    rate_histogram_bins: int = 80,
    y_limit_left: object = None,
    y_limit_right: object = None,
) -> plt.Figure | None:
    required_columns = {"datetime", tt_column}
    if dataframe.empty or not required_columns.issubset(dataframe.columns):
        return None

    datetimes = pd.to_datetime(dataframe["datetime"], errors="coerce")
    tt_values = pd.to_numeric(dataframe[tt_column], errors="coerce")
    valid_mask = datetimes.notna() & tt_values.notna()
    if not valid_mask.any():
        return None

    accumulation_window_seconds = _positive_int(
        accumulation_window_seconds,
        default=60,
        minimum=1,
    )
    frame = pd.DataFrame(
        {
            "elapsed_s": (
                datetimes.loc[valid_mask] - datetimes.loc[valid_mask].min()
            ).dt.total_seconds().astype(int),
            "task_tt": tt_values.loc[valid_mask].astype(int),
        }
    )
    if frame.empty:
        return None

    frame.loc[:, "window_index"] = (
        frame["elapsed_s"] // accumulation_window_seconds
    ).astype(int)
    full_windows = np.arange(
        int(frame["window_index"].min()),
        int(frame["window_index"].max()) + 1,
    )
    rates_by_tt = (
        frame.groupby(["window_index", "task_tt"])
        .size()
        .unstack(fill_value=0)
        .reindex(full_windows, fill_value=0)
        .sort_index(axis=1)
        .astype(float)
        / float(accumulation_window_seconds)
    )
    if rates_by_tt.empty:
        return None
    first_valid_datetime = datetimes.loc[valid_mask].min()
    window_datetimes = first_valid_datetime + pd.to_timedelta(
        rates_by_tt.index.to_numpy(dtype=int) * accumulation_window_seconds,
        unit="s",
    )

    fig, (ax_time, ax_hist) = plt.subplots(
        1,
        2,
        figsize=(14, 5),
        sharey=True,
        constrained_layout=True,
        gridspec_kw={"width_ratios": [4.5, 1.3], "wspace": 0.04},
    )
    all_rates = rates_by_tt.to_numpy(dtype=float).ravel()
    finite_rates = all_rates[np.isfinite(all_rates)]
    max_rate = float(finite_rates.max()) if finite_rates.size else 1.0
    y_min = _optional_float(y_limit_left)
    y_max = _optional_float(y_limit_right)
    if y_min is not None and y_max is not None and y_min >= y_max:
        y_min = None
        y_max = None
    bin_count = _positive_int(
        rate_histogram_bins,
        default=80,
        minimum=8,
        maximum=300,
    )
    hist_min = y_min if y_min is not None else 0.0
    hist_max = y_max if y_max is not None else max(max_rate, 1.0)
    bins = np.linspace(hist_min, max(hist_max, hist_min + 1.0), bin_count)
    if np.unique(bins).size < 2:
        bins = np.array([0.0, 1.0])

    for task_tt in rates_by_tt.columns:
        rates = rates_by_tt[task_tt].to_numpy(dtype=float)
        task_tt_int = int(task_tt)
        color = _task_tt_color(task_tt_int)
        label = f"{tt_column}={task_tt_int}"
        ax_time.plot(
            window_datetimes,
            rates,
            linewidth=1.1,
            label=label,
            color=color,
        )
        ax_hist.hist(
            rates[np.isfinite(rates)],
            bins=bins,
            orientation="horizontal",
            histtype="step",
            linewidth=1.2,
            color=color,
            label=label,
        )

    ax_time.set_title("Rate versus time")
    ax_time.set_xlabel("Time")
    ax_time.set_ylabel(f"Rate [Hz], {accumulation_window_seconds}s accumulation")
    ax_time.xaxis.set_major_formatter(mdates.DateFormatter("%y-%m-%d %H:%M:%S"))
    fig.autofmt_xdate(rotation=30, ha="right")
    if y_min is not None or y_max is not None:
        ax_time.set_ylim(y_min, y_max)
    ax_time.grid(True, alpha=0.25)
    ax_time.legend(loc="best", fontsize=8)

    ax_hist.set_title("Rate histogram")
    ax_hist.set_xlabel("Windows")
    ax_hist.grid(True, alpha=0.25, axis="y")
    ax_hist.tick_params(axis="y", labelleft=False)

    fig.suptitle(title)
    return fig
