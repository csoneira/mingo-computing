#!/usr/bin/env python3
"""Generate STEP 1 event limits indexed by minimum configured plane efficiency."""

from __future__ import annotations

import argparse
import ast
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", "/tmp/dataflow_v3_matplotlib")
import matplotlib.pyplot as plt


DIGITAL_TWIN_ROOT = Path(__file__).resolve().parents[2]
GENERATOR_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = (
    DIGITAL_TWIN_ROOT
    / "SIMULATION_OUTPUTS"
    / "SIMULATED_DATA"
    / "step_final_simulation_params.csv"
)
DEFAULT_OUTPUT = GENERATOR_DIR / "event_limits_by_min_efficiency.csv"
DEFAULT_PLOT_PNG = GENERATOR_DIR / "event_limits_by_min_efficiency.png"
DEFAULT_PLOT_PDF = GENERATOR_DIR / "event_limits_by_min_efficiency.pdf"


def _parse_efficiencies(value: object) -> list[float]:
    if pd.isna(value):
        return []
    try:
        parsed = ast.literal_eval(str(value))
    except (SyntaxError, ValueError):
        return []
    if not isinstance(parsed, (list, tuple)) or len(parsed) != 4:
        return []
    try:
        return [float(item) for item in parsed]
    except (TypeError, ValueError):
        return []


def _minimum_efficiency(df: pd.DataFrame) -> pd.Series:
    plane_columns = [f"eff_p{plane}" for plane in range(1, 5)]
    if all(column in df.columns for column in plane_columns):
        values = df[plane_columns].apply(pd.to_numeric, errors="coerce")
        return values.min(axis=1, skipna=False)
    if "efficiencies" not in df.columns:
        raise ValueError(
            "Input must contain eff_p1..eff_p4 or the four-value efficiencies column."
        )
    return df["efficiencies"].apply(
        lambda value: min(parsed) if (parsed := _parse_efficiencies(value)) else np.nan
    )


def load_observations(input_path: Path, *, bin_width: float) -> pd.DataFrame:
    df = pd.read_csv(input_path)
    required = {"original_rows", "requested_rows"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {input_path}: {sorted(missing)}")

    df["min_efficiency"] = _minimum_efficiency(df)
    df["original_rows"] = pd.to_numeric(df["original_rows"], errors="coerce")
    df["requested_rows"] = pd.to_numeric(df["requested_rows"], errors="coerce")
    df = df.loc[
        df["min_efficiency"].notna()
        & df["original_rows"].notna()
        & df["requested_rows"].notna()
        & (df["original_rows"] > 0)
        & (df["requested_rows"] > 0)
    ].copy()
    if df.empty:
        raise RuntimeError("No valid efficiency and row-count observations were found.")

    # This is the fraction of the current STEP 1 generation that would have
    # produced exactly requested_rows, assuming downstream yield remains stable.
    df["requested_over_original_ratio"] = df["requested_rows"] / df["original_rows"]
    df["efficiency_bin_lower"] = (
        np.floor(df["min_efficiency"] / bin_width) * bin_width
    ).round(10)
    return df


def build_lookup(
    observations: pd.DataFrame,
    *,
    base_n_tracks: int,
    bin_width: float,
    ratio_quantile: float,
    safety_factor: float,
    minimum_samples: int,
    round_to: int,
) -> pd.DataFrame:
    df = observations
    global_ratio = float(df["requested_over_original_ratio"].quantile(ratio_quantile))
    rows: list[dict[str, float | int]] = []
    for lower, group in df.groupby("efficiency_bin_lower", sort=True):
        observed_count = int(len(group))
        ratio = (
            float(group["requested_over_original_ratio"].quantile(ratio_quantile))
            if observed_count >= minimum_samples
            else global_ratio
        )
        generation_scale = max(ratio * safety_factor, 0.01)
        recommended = max(
            round_to,
            int(math.ceil(base_n_tracks * generation_scale / round_to) * round_to),
        )
        rows.append(
            {
                "min_efficiency_lower": float(lower),
                "min_efficiency_upper": float(lower + bin_width),
                "observations": observed_count,
                "requested_over_original_ratio_median": float(
                    group["requested_over_original_ratio"].median()
                ),
                "requested_over_original_ratio_quantile": ratio,
                "ratio_quantile": ratio_quantile,
                "safety_factor": safety_factor,
                "safety_margin_ratio": generation_scale - ratio,
                "generation_scale": generation_scale,
                "base_n_tracks": int(base_n_tracks),
                "recommended_n_tracks": recommended,
            }
        )
    return pd.DataFrame(rows)


def make_plot(
    observations: pd.DataFrame,
    lookup: pd.DataFrame,
    *,
    output_png: Path,
    output_pdf: Path,
) -> None:
    centers = (
        lookup["min_efficiency_lower"] + lookup["min_efficiency_upper"]
    ) / 2.0
    ratio_percent = 100.0 * observations["requested_over_original_ratio"]
    median_percent = 100.0 * lookup["requested_over_original_ratio_median"]
    quantile_percent = 100.0 * lookup["requested_over_original_ratio_quantile"]
    generation_percent = 100.0 * lookup["generation_scale"]

    fig, (ax_ratio, ax_tracks) = plt.subplots(
        2,
        1,
        figsize=(11, 10),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 2]},
    )

    ax_ratio.scatter(
        observations["min_efficiency"],
        ratio_percent,
        s=13,
        alpha=0.22,
        color="0.35",
        rasterized=True,
        label="Individual requested/original ratios",
    )
    ax_ratio.plot(
        centers,
        median_percent,
        marker="o",
        linewidth=1.8,
        label="Per-bin median ratio",
    )
    quantile_label = f"Selected quantile ({100 * lookup['ratio_quantile'].iloc[0]:.0f}%)"
    ax_ratio.plot(
        centers,
        quantile_percent,
        marker="s",
        linewidth=2,
        label=quantile_label,
    )
    ax_ratio.plot(
        centers,
        generation_percent,
        marker="^",
        linewidth=2,
        label="Generation scale including safety margin",
    )
    ax_ratio.fill_between(
        centers,
        quantile_percent,
        generation_percent,
        alpha=0.22,
        label=f"Safety margin ({lookup['safety_factor'].iloc[0]:.2f}x)",
    )
    ax_ratio.axhline(
        100,
        color="black",
        linestyle="--",
        linewidth=1,
        label="Current generation size",
    )
    ax_ratio.set_ylabel("Ratio / generation scale [%]")
    ax_ratio.set_title(
        "STEP 1 generation limit from minimum detector efficiency\n"
        "requested/original ratio with selected quantile and safety margin"
    )
    ax_ratio.grid(True, alpha=0.25)
    ax_ratio.legend(fontsize=9, ncols=2)

    ax_tracks.step(
        centers,
        lookup["recommended_n_tracks"] / 1_000_000,
        where="mid",
        linewidth=2.2,
        color="tab:blue",
        label="Recommended STEP 1 tracks",
    )
    ax_tracks.axhline(
        lookup["base_n_tracks"].iloc[0] / 1_000_000,
        color="black",
        linestyle="--",
        linewidth=1,
        label="Current base tracks",
    )
    ax_tracks.set_ylabel("Recommended tracks [million]")
    ax_tracks.set_xlabel("Minimum of eff_p1, eff_p2, eff_p3, eff_p4")
    ax_tracks.grid(True, alpha=0.25)

    ax_counts = ax_tracks.twinx()
    widths = lookup["min_efficiency_upper"] - lookup["min_efficiency_lower"]
    ax_counts.bar(
        centers,
        lookup["observations"],
        width=0.75 * widths,
        alpha=0.18,
        color="tab:orange",
        label="Observations per bin",
    )
    ax_counts.set_ylabel("Observations per bin")

    handles_left, labels_left = ax_tracks.get_legend_handles_labels()
    handles_right, labels_right = ax_counts.get_legend_handles_labels()
    ax_tracks.legend(handles_left + handles_right, labels_left + labels_right, fontsize=9)

    fig.tight_layout()
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=220)
    fig.savefig(output_pdf)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--plot-png", type=Path, default=DEFAULT_PLOT_PNG)
    parser.add_argument("--plot-pdf", type=Path, default=DEFAULT_PLOT_PDF)
    parser.add_argument("--base-n-tracks", type=int, default=11_250_000)
    parser.add_argument("--bin-width", type=float, default=0.05)
    parser.add_argument("--ratio-quantile", type=float, default=0.90)
    parser.add_argument("--safety-factor", type=float, default=1.10)
    parser.add_argument("--minimum-samples", type=int, default=8)
    parser.add_argument("--round-to", type=int, default=50_000)
    args = parser.parse_args()

    if args.base_n_tracks <= 0 or args.bin_width <= 0 or args.round_to <= 0:
        raise ValueError("base-n-tracks, bin-width, and round-to must be positive.")
    if not 0 < args.ratio_quantile <= 1:
        raise ValueError("ratio-quantile must be in (0, 1].")
    if args.safety_factor <= 0:
        raise ValueError("safety-factor must be positive.")

    observations = load_observations(args.input, bin_width=args.bin_width)
    lookup = build_lookup(
        observations,
        base_n_tracks=args.base_n_tracks,
        bin_width=args.bin_width,
        ratio_quantile=args.ratio_quantile,
        safety_factor=args.safety_factor,
        minimum_samples=args.minimum_samples,
        round_to=args.round_to,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    lookup.to_csv(args.output, index=False)
    make_plot(
        observations,
        lookup,
        output_png=args.plot_png,
        output_pdf=args.plot_pdf,
    )
    print(f"Input observations: {int(lookup['observations'].sum())}")
    print(f"Efficiency bins written: {len(lookup)}")
    print(f"Output: {args.output}")
    print(f"Plot PNG: {args.plot_png}")
    print(f"Plot PDF: {args.plot_pdf}")
    print(lookup.to_string(index=False))


if __name__ == "__main__":
    main()
