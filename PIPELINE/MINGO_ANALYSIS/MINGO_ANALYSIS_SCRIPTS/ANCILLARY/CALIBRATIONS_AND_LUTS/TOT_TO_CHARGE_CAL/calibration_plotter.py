#!/usr/bin/env python3

"""Plot TOT-to-charge calibration curves and export them as PNG by default."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch, Rectangle


THIS_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = THIS_DIR / "tot_to_charge_calibration.csv"
DEFAULT_OUTPUT = THIS_DIR / "tot_to_charge_calibration_plot.png"


@dataclass
class CalibrationData:
    width: pd.Series
    charge: pd.Series


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to the TOT-to-charge calibration CSV.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Destination plot image file (PNG by default).",
    )
    parser.add_argument(
        "--title",
        default="FEE HADES TOT-to-Charge Calibration",
        help="Custom title for the plot.",
    )
    return parser.parse_args(argv)


def load_calibration_data(csv_path: Path) -> CalibrationData:
    if not csv_path.exists():
        raise FileNotFoundError(f"Calibration CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    required_columns = {"Width", "Fast_Charge"}
    if not required_columns.issubset(df.columns):
        raise ValueError(
            f"Expected columns {required_columns} in {csv_path}, found {set(df.columns)}"
        )

    df = df.copy()
    df["Width"] = pd.to_numeric(df["Width"], errors="coerce")
    df["Fast_Charge"] = pd.to_numeric(df["Fast_Charge"], errors="coerce")
    df = df.dropna(subset=["Width", "Fast_Charge"]).sort_values("Width")

    if df.empty:
        raise ValueError(f"No valid data points after cleaning {csv_path}")

    return CalibrationData(width=df["Width"], charge=df["Fast_Charge"])


def render_plot(data: CalibrationData, title: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    widths = data.width.to_numpy()
    charges = data.charge.to_numpy()

    fig, ax = plt.subplots(figsize=(8, 6))

    streamer_x = 100.0
    avalanche_color = "tab:green"
    streamer_color = "tab:red"

    # Calibration curve.
    ax.plot(
        widths,
        charges,
        color="tab:blue",
        linewidth=2.2,
        label="Calibration curve",
        zorder=3,
    )
    ax.scatter(
        widths,
        charges,
        color="white",
        edgecolor="tab:blue",
        s=30,
        linewidth=0.7,
        zorder=4,
        label="_nolegend_",
    )

    ax.set_title(title, fontsize=15)
    ax.set_xlabel("Time-over-Threshold Width (ns)", fontsize=12)
    ax.set_ylabel("Fast Charge (fC)", fontsize=12)
    ax.grid(True, which="both", linestyle="--", alpha=0.35)
    x_min_data = widths.min()
    x_max_data = widths.max()
    x_span = x_max_data - x_min_data
    if x_span <= 0:
        reference = float(abs(x_min_data) if len(widths) else 1.0)
        x_margin = 0.02 * max(reference, 1.0)
    else:
        x_margin = 0.02 * x_span
    x_axis_min = x_min_data - x_margin
    x_axis_max = x_max_data + x_margin
    ax.set_xlim(x_axis_min, x_axis_max)

    y_margin = 0.05 * (charges.max() - charges.min())
    y_bottom = charges.min() - y_margin
    y_top = charges.max() + y_margin
    ax.set_ylim(y_bottom, y_top)

    # Threshold guide lines and shaded operating zones.
    streamer_y = float(np.interp(streamer_x, widths, charges))

    streamer_x_plot = float(np.clip(streamer_x, x_axis_min, x_axis_max))
    streamer_y_plot = float(np.clip(streamer_y, y_bottom, y_top))

    streamer_right_rect = Rectangle(
        (streamer_x_plot, y_bottom),
        max(x_axis_max - streamer_x_plot, 0.0),
        max(y_top - y_bottom, 0.0),
        facecolor=streamer_color,
        alpha=0.08,
        edgecolor="none",
        zorder=0,
    )
    ax.add_patch(streamer_right_rect)

    streamer_top_rect = Rectangle(
        (x_axis_min, streamer_y_plot),
        max(streamer_x_plot - x_axis_min, 0.0),
        max(y_top - streamer_y_plot, 0.0),
        facecolor=streamer_color,
        alpha=0.08,
        edgecolor="none",
        zorder=0,
    )
    ax.add_patch(streamer_top_rect)

    avalanche_rect = Rectangle(
        (x_axis_min, y_bottom),
        max(streamer_x_plot - x_axis_min, 0.0),
        max(streamer_y_plot - y_bottom, 0.0),
        facecolor=avalanche_color,
        alpha=0.12,
        edgecolor="none",
        zorder=1,
    )
    ax.add_patch(avalanche_rect)

    ax.plot(
        [x_axis_min, streamer_x_plot],
        [streamer_y_plot, streamer_y_plot],
        color=streamer_color,
        linewidth=1.5,
        linestyle="--",
        label="Streamer threshold",
        zorder=3,
    )
    ax.plot(
        [streamer_x_plot, streamer_x_plot],
        [y_bottom, streamer_y_plot],
        color=streamer_color,
        linewidth=1.5,
        linestyle="--",
        zorder=3,
        label="_nolegend_",
    )

    ax.tick_params(axis="both", which="major", labelsize=10)
    handles, labels = ax.get_legend_handles_labels()
    filtered = [(h, l) for h, l in zip(handles, labels) if l and l != "_nolegend_"]
    if filtered:
        handles, labels = map(list, zip(*filtered))
    else:
        handles, labels = [], []
    handles.extend(
        [
            Patch(facecolor=avalanche_color, alpha=0.12, edgecolor="none", label="Avalanche region"),
            Patch(facecolor=streamer_color, alpha=0.08, edgecolor="none", label="Streamer region"),
        ]
    )
    labels.extend(["Avalanche region", "Streamer region"])
    ax.legend(handles, labels, loc="upper left", frameon=True, framealpha=0.92)

    plt.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    data = load_calibration_data(args.input)
    render_plot(data, args.title, args.output)
    print(f"Saved calibration plot to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
