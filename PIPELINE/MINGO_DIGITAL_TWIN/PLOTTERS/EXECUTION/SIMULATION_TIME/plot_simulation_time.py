#!/usr/bin/env python3

"""Plot per-step simulation execution-time histograms and time series."""

from __future__ import annotations

import yaml

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = BASE_DIR / "simulation_execution_times.csv"
# Default output: rasterized PDF (previously a PNG)
DEFAULT_OUTPUT = BASE_DIR / "simulation_execution_time_hist.pdf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot 10 step-wise execution-time histograms from CSV.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input CSV path (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output figure path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--date-from",
        default=None,
        help="Keep rows at/after this UTC datetime (e.g. 2026-02-10T14:00:00Z).",
    )
    parser.add_argument(
        "--date-to",
        default=None,
        help="Keep rows at/before this UTC datetime (e.g. 2026-02-10T20:00:00Z).",
    )
    parser.add_argument(
        "--last-n",
        type=int,
        default=0,
        help="Use only the last N rows after filters (default: 0 means all).",
    )
    parser.add_argument(
        "--min-seconds",
        type=float,
        default=None,
        help="Drop entries below this elapsed time.",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=None,
        help="Drop entries above this elapsed time.",
    )
    parser.add_argument(
        "--bins",
        type=int,
        default=0,
        help="Histogram bins (default: auto via Freedman-Diaconis rule).",
    )
    parser.add_argument(
        "--title",
        default="Simulation Step Execution Time Histograms",
        help="Plot title.",
    )
    return parser.parse_args()


def auto_bins(values: np.ndarray) -> int:
    n = values.size
    if n <= 1:
        return 1
    vmin = float(np.min(values))
    vmax = float(np.max(values))
    if np.isclose(vmin, vmax):
        return 1
    q1, q3 = np.percentile(values, [25, 75])
    iqr = float(q3 - q1)
    if iqr <= 0:
        return max(5, min(80, int(np.sqrt(n))))
    bin_width = 2.0 * iqr / np.cbrt(n)
    if bin_width <= 0:
        # fall back to rough heuristic; allow up to 240 bins for thinner default
        return max(5, min(240, int(np.sqrt(n))))
    bins = int(np.ceil((vmax - vmin) / bin_width))
    # cap at 240 (previously 120) to give a finer-grained default histogram
    return max(5, min(240, bins))


def load_filtered_times(args: argparse.Namespace) -> pd.DataFrame:
    if not args.input.exists():
        raise FileNotFoundError(f"Input CSV does not exist: {args.input}")


    # First, clean the CSV by removing rows with inconsistent number of columns
    import csv
    expected_cols = None
    cleaned_rows = []
    with open(args.input, newline='') as csvfile:
        reader = csv.reader(csvfile)
        for i, row in enumerate(reader):
            if i == 0:
                expected_cols = len(row)
                cleaned_rows.append(row)
            elif len(row) == expected_cols:
                cleaned_rows.append(row)
    # Do not modify the source CSV on disk. Load cleaned rows into memory only
    # (skip malformed rows without creating a legacy/backup file).
    if not cleaned_rows or len(cleaned_rows) == 1:
        raise ValueError(f"Input CSV is empty or all rows malformed: {args.input}")
    # Support both headered CSVs and headerless legacy/runtime CSVs.
    first_row = [str(cell).strip() for cell in cleaned_rows[0]]
    expected = {"exec_time_s", "step", "timestamp_utc"}
    has_header = expected.issubset(set(first_row))

    if has_header:
        # First row is header; build DataFrame from remaining (clean) rows.
        df = pd.DataFrame(cleaned_rows[1:], columns=cleaned_rows[0])
    else:
        # Headerless format: exec_time_s,step,timestamp_utc
        if len(first_row) < 3:
            raise ValueError(
                "Headerless CSV must contain at least 3 columns: exec_time_s, step, timestamp_utc"
            )
        columns = ["exec_time_s", "step", "timestamp_utc"] + [f"extra_{i}" for i in range(3, len(first_row))]
        df = pd.DataFrame(cleaned_rows, columns=columns)
    if df.empty:
        raise ValueError(f"Input CSV contains no usable data after filtering malformed rows: {args.input}")

    if "exec_time_s" not in df.columns:
        if "elapsed_seconds" in df.columns:
            df["exec_time_s"] = pd.to_numeric(df["elapsed_seconds"], errors="coerce")
        else:
            raise ValueError("CSV missing required column: exec_time_s")

    if "step" not in df.columns:
        raise ValueError("CSV missing required column: step")

    if "timestamp_utc" not in df.columns:
        raise ValueError("CSV missing required column: timestamp_utc")

    df["exec_time_s"] = pd.to_numeric(df["exec_time_s"], errors="coerce")
    df["step"] = pd.to_numeric(df["step"], errors="coerce")
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True, errors="coerce")
    df = df[df["exec_time_s"].notna()]
    df = df[df["step"].notna()]
    df = df[df["timestamp_utc"].notna()]
    # Log-scale plots require strictly positive execution times.
    df = df[df["exec_time_s"] > 0]
    df["step"] = df["step"].astype(int)
    df = df[df["step"].between(1, 10)]

    if args.date_from or args.date_to:
        timestamps = df["timestamp_utc"]
        if args.date_from:
            date_from = pd.to_datetime(args.date_from, utc=True, errors="coerce")
            if pd.isna(date_from):
                raise ValueError(f"Invalid --date-from value: {args.date_from}")
            df = df[timestamps >= date_from]
            timestamps = timestamps.loc[df.index]
        if args.date_to:
            date_to = pd.to_datetime(args.date_to, utc=True, errors="coerce")
            if pd.isna(date_to):
                raise ValueError(f"Invalid --date-to value: {args.date_to}")
            df = df[timestamps <= date_to]

    if args.min_seconds is not None:
        df = df[df["exec_time_s"] >= args.min_seconds]
    if args.max_seconds is not None:
        df = df[df["exec_time_s"] <= args.max_seconds]

    if args.last_n and args.last_n > 0:
        df = df.tail(args.last_n)

    df = df.sort_values("timestamp_utc")

    if df.empty:
        raise ValueError("No rows left after filters.")

    return df


def main() -> None:
    # Load config file if present
    config_path = BASE_DIR / "plot_simulation_time_config.yaml"
    config = {}
    if config_path.exists():
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    last_hours = config.get("last_hours", 2)
    plot_width_ratios = config.get("plot_width_ratios", [1.4, 1.0, 0.7])
    
    # If ratios are integers, use as-is, else fallback to previous default
    if isinstance(plot_width_ratios, list) and all(isinstance(x, (int, float)) for x in plot_width_ratios) and len(plot_width_ratios) == 3:
        width_ratios = plot_width_ratios
    else:
        width_ratios = [1.4, 1.0, 0.7]
    args = parse_args()
    df = load_filtered_times(args)
    values = df["exec_time_s"].to_numpy(dtype=float)


    # Determine log-spaced bins for histogram
    min_v = float(np.min(values))
    max_v = float(np.max(values))
    if args.bins and args.bins > 0:
        n_bins = args.bins
    else:
        n_bins = auto_bins(values)
    # Ensure min_v > 0 for logspace
    min_v = max(min_v, 1e-10)
    if min_v >= max_v:
        bin_edges = np.array([min_v, max_v])
    else:
        bin_edges = np.logspace(np.log10(min_v), np.log10(max_v), n_bins + 1)


    plt.style.use("seaborn-v0_8-whitegrid")
    import matplotlib.gridspec as gridspec
    size_y = 6
    size_x = 3/6 * size_y
    fig = plt.figure(figsize=(sum(width_ratios)*size_x, size_y))
    gs = gridspec.GridSpec(1, 3, width_ratios=width_ratios, wspace=0.10)
    ax_ts = fig.add_subplot(gs[0, 0])
    ax_ts_recent = fig.add_subplot(gs[0, 1], sharey=ax_ts)
    ax_hist = fig.add_subplot(gs[0, 2], sharey=ax_ts)
    cmap = plt.colormaps["tab10"]
    plotted_steps: list[int] = []
    for step in range(1, 11):
        step_vals = df.loc[df["step"] == step, "exec_time_s"].to_numpy(dtype=float)
        if step_vals.size == 0:
            continue
        plotted_steps.append(step)
        ax_hist.hist(
            step_vals,
            bins=bin_edges,
            histtype="step",
            linewidth=1.8,
            color=cmap(step - 1),
            label=f"Step {step} (n={step_vals.size})",
            orientation="horizontal",
        )

    if not plotted_steps:
        raise ValueError("No rows with valid steps (1-10) left after filters.")


    ax_hist.set_title(args.title, fontsize=12)
    ax_hist.set_ylabel("Execution time [s] (exec_time_s)")
    ax_hist.set_xlabel("Count")
    # Ensure histogram has no legend
    if ax_hist.get_legend() is not None:
        ax_hist.get_legend().remove()
    ax_hist.set_yscale("log")
    ax_hist.set_xscale("log")

    # Time series panel: timestamp_utc in x, exec_time_s in y (log-scale)

    # Plot full time series (left) — standard datetime x-axis (no recency transform)
    for step in plotted_steps:
        step_df = df.loc[df["step"] == step, ["timestamp_utc", "exec_time_s"]].sort_values(
            "timestamp_utc"
        )
        ax_ts.plot(
            step_df["timestamp_utc"].to_numpy(),
            step_df["exec_time_s"].to_numpy(dtype=float),
            linestyle="None",
            marker="o",
            markersize=4.5,
            linewidth=1.1,
            color=cmap(step - 1),
            label=f"Step {step}",
            alpha=0.9,
        )

    ax_ts.set_title("Execution Time Time-Series by Step", fontsize=12)
    ax_ts.set_xlabel("timestamp_utc (log-scaled by recency)")
    ax_ts.set_ylabel("Execution time [s] (exec_time_s)")
    ax_ts.set_yscale("log")
    # No legend in leftmost plot
    # Show only year-month-day on the leftmost x-axis (no HH:MM:SS)
    ax_ts.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d", tz=mdates.UTC))
    ax_ts.tick_params(axis="x", rotation=0)

    # Plot recent (last 2 hours) time series (middle)
    if not df.empty:
        last_time = df["timestamp_utc"].max()
        hours_ago = last_time - pd.Timedelta(hours=last_hours)
        df_recent = df[df["timestamp_utc"] >= hours_ago]
        for step in plotted_steps:
            step_df = df_recent.loc[df_recent["step"] == step, ["timestamp_utc", "exec_time_s"]].sort_values(
                "timestamp_utc"
            )
            # Plot lines connecting points
            ax_ts_recent.plot(
                mdates.date2num(step_df["timestamp_utc"].to_numpy()),
                step_df["exec_time_s"].to_numpy(dtype=float),
                linestyle="-",
                marker="o",
                markersize=4.5,
                linewidth=1.3,
                color=cmap(step - 1),
                label=f"Step {step}",
                alpha=0.9,
            )
        ax_ts_recent.set_title(f"Last {last_hours} Hours", fontsize=12)
        ax_ts_recent.set_xlabel("timestamp_utc")
        ax_ts_recent.set_yscale("log")
        ax_ts_recent.legend(loc="upper right", ncol=2, fontsize=9)
        # Show only hour and minute in x ticks
        ax_ts_recent.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=mdates.UTC))
        ax_ts_recent.tick_params(axis="x", rotation=0)

    now = pd.Timestamp.utcnow()
    ax_ts.axvline(now, color="red", linestyle="--", alpha=0.3, zorder=10)
    if not df.empty:
        ax_ts_recent.axvline(now, color="red", linestyle="--", alpha=0.3, zorder=10)

    # filter text removed (user request)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Reduce left/right whitespace and control spacing explicitly
    fig.subplots_adjust(left=0.03, right=0.99, top=0.95, bottom=0.10, wspace=0.06)

    # If saving to PDF, rasterize plotted axes so the output embeds raster images
    # (useful for many markers/large datasets while keeping overall layout in a PDF).
    if args.output.suffix.lower() == ".pdf":
        for _ax in (ax_ts, ax_ts_recent, ax_hist):
            _ax.set_rasterized(True)

    fig.savefig(args.output, dpi=180)
    plt.close(fig)

    print(f"Saved figure: {args.output}")
    print(f"N={values.size} min={min_v:.3f}s max={max_v:.3f}s bins={n_bins}")
    step_counts = df["step"].value_counts().sort_index()
    print("Rows per step:", ", ".join(f"{idx}:{cnt}" for idx, cnt in step_counts.items()))


if __name__ == "__main__":
    main()
