#!/usr/bin/env python3
"""Quick chi2-cut rate time-series plotter for Task 4 metadata.

Reads one Task-4 `task_4_metadata_chi2_four_plane.csv` file, reconstructs the
rate below several chi2 thresholds from the stored histogram-bin rates, and
plots all selected cuts together versus the data timestamp parsed from
`filename_base` (mi02YYDDDHHMMSS-style basename time, not execution time).

Usage:
  python3 chisq_rate_timeseries.py
  python3 chisq_rate_timeseries.py --config /path/to/chisq_rate_config.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


THIS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = THIS_DIR / "chisq_rate_config.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot Task-4 chi2-cut rates versus basename time.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to the JSON config file.")
    return parser.parse_args()


def load_config(config_path: str) -> dict[str, object]:
    path = Path(config_path).resolve()
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    config["_config_path"] = str(path)
    config["_config_dir"] = str(path.parent)
    return config


def resolve_output_path(config: dict[str, object]) -> Path:
    raw_dir = str(config.get("output_dir", "OUTPUTS"))
    output_dir = Path(raw_dir)
    if not output_dir.is_absolute():
        output_dir = (Path(config["_config_dir"]) / output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / str(config.get("output_plot_name", "chisq_rate_cuts_timeseries.png"))


def parse_filename_base_timestamp(filename_base: str) -> datetime:
    token = str(filename_base).strip()
    if not token.startswith("mi") or len(token) < 15:
        raise ValueError(f"Unsupported filename_base format: {filename_base!r}")
    yy = int(token[4:6])
    doy = int(token[6:9])
    hh = int(token[9:11])
    mm = int(token[11:13])
    ss = int(token[13:15])
    year = 2000 + yy
    return datetime(year, 1, 1) + timedelta(days=doy - 1, hours=hh, minutes=mm, seconds=ss)


def bin_rate_columns(bin_count: int) -> list[str]:
    return [f"chi2_four_plane_bin_{idx:03d}_rate_hz" for idx in range(int(bin_count))]


def rate_below_threshold(row: pd.Series, threshold: float | None) -> float:
    hist_min = float(row["chi2_four_plane_hist_min"])
    hist_max = float(row["chi2_four_plane_hist_max"])
    bin_count = int(row["chi2_four_plane_hist_bin_count"])
    columns = bin_rate_columns(bin_count)
    rates = pd.to_numeric(row[columns], errors="coerce").fillna(0.0).to_numpy(dtype=float)

    if threshold is None or threshold >= hist_max:
        return float(np.sum(rates))
    if threshold <= hist_min:
        return 0.0

    edges = np.linspace(hist_min, hist_max, bin_count + 1)
    lower_edges = edges[:-1]
    upper_edges = edges[1:]
    widths = upper_edges - lower_edges
    overlaps = np.clip(np.minimum(upper_edges, threshold) - lower_edges, 0.0, widths)
    fractions = np.divide(overlaps, widths, out=np.zeros_like(overlaps), where=widths > 0)
    return float(np.sum(rates * fractions))


def add_cut_rate_columns(df: pd.DataFrame, cuts: list[dict[str, object]]) -> pd.DataFrame:
    enriched = df.copy()
    for cut in cuts:
        label = str(cut["label"])
        threshold = cut.get("chi2_max")
        numeric_threshold = None if threshold in (None, "", "null", "None") else float(threshold)
        safe_name = (
            label.lower()
            .replace(" ", "_")
            .replace("<", "lt")
            .replace(">", "gt")
            .replace("=", "eq")
            .replace("/", "_")
        )
        column_name = f"rate_cut__{safe_name}"
        enriched[column_name] = enriched.apply(lambda row: rate_below_threshold(row, numeric_threshold), axis=1)
    return enriched


def plot_cut_rates(df: pd.DataFrame, cuts: list[dict[str, object]], output_path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(13, 6.5), constrained_layout=True)
    for cut in cuts:
        label = str(cut["label"])
        safe_name = (
            label.lower()
            .replace(" ", "_")
            .replace("<", "lt")
            .replace(">", "gt")
            .replace("=", "eq")
            .replace("/", "_")
        )
        column_name = f"rate_cut__{safe_name}"
        ax.plot(df["file_timestamp_utc"], df[column_name], marker="o", markersize=2.2, linewidth=1.1, label=label)

    ax.set_title("Task-4 chi2-cut rates vs basename time")
    ax.set_xlabel("file timestamp utc")
    ax.set_ylabel("Rate [Hz]")
    ax.grid(alpha=0.25)
    ax.legend(loc="best")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def add_removed_percent_columns(df: pd.DataFrame, cuts: list[dict[str, object]]) -> pd.DataFrame:
    enriched = df.copy()
    first_label = str(cuts[0]["label"])
    first_safe_name = (
        first_label.lower()
        .replace(" ", "_")
        .replace("<", "lt")
        .replace(">", "gt")
        .replace("=", "eq")
        .replace("/", "_")
    )
    total_rate_column = f"rate_cut__{first_safe_name}"
    total_rate = pd.to_numeric(enriched[total_rate_column], errors="coerce").to_numpy(dtype=float)
    for cut in cuts:
        label = str(cut["label"])
        safe_name = (
            label.lower()
            .replace(" ", "_")
            .replace("<", "lt")
            .replace(">", "gt")
            .replace("=", "eq")
            .replace("/", "_")
        )
        rate_column = f"rate_cut__{safe_name}"
        removed_column = f"removed_percent__{safe_name}"
        kept_rate = pd.to_numeric(enriched[rate_column], errors="coerce").to_numpy(dtype=float)
        enriched[removed_column] = np.where(total_rate > 0.0, 100.0 * (total_rate - kept_rate) / total_rate, np.nan)
    return enriched


def plot_removed_percents(df: pd.DataFrame, cuts: list[dict[str, object]], output_path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(13, 6.5), constrained_layout=True)
    for cut in cuts:
        label = str(cut["label"])
        safe_name = (
            label.lower()
            .replace(" ", "_")
            .replace("<", "lt")
            .replace(">", "gt")
            .replace("=", "eq")
            .replace("/", "_")
        )
        column_name = f"removed_percent__{safe_name}"
        ax.plot(df["file_timestamp_utc"], df[column_name], marker="o", markersize=2.2, linewidth=1.1, label=label)

    ax.set_title("Task-4 chi2-cut removed fraction vs basename time")
    ax.set_xlabel("file timestamp utc")
    ax.set_ylabel("Removed events [% of all]")
    ax.grid(alpha=0.25)
    ax.legend(loc="best")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    metadata_csv = Path(str(config["metadata_csv"])).resolve()
    output_path = resolve_output_path(config)
    removed_output_path = output_path.with_name(
        str(config.get("output_removed_percent_plot_name", "chisq_rate_removed_percent_timeseries.png"))
    )
    cuts = list(config.get("cuts", []))
    if not cuts:
        raise ValueError("Config must define at least one entry in 'cuts'.")

    df = pd.read_csv(metadata_csv, low_memory=False)
    df["file_timestamp_utc"] = df["filename_base"].map(parse_filename_base_timestamp)
    df = df.sort_values("file_timestamp_utc").reset_index(drop=True)
    df = add_cut_rate_columns(df, cuts)
    df = add_removed_percent_columns(df, cuts)
    saved = plot_cut_rates(df, cuts, output_path)
    saved_removed = plot_removed_percents(df, cuts, removed_output_path)

    print(f"Metadata rows: {len(df)}")
    print(f"Metadata source: {metadata_csv}")
    print(f"Saved plot: {saved}")
    print(f"Saved removed-percent plot: {saved_removed}")


if __name__ == "__main__":
    main()
