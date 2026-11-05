#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simple_common import DEFAULT_CONFIG_PATH, files_dir, load_config, plots_dir
from step_0_load_inputs import run_training_selection
from step_1_build_lut import run as run_step_1


def create_poster_plot(
    config_path: str | Path,
    *,
    target_column: str,
    variable_plane: int,
    eff_min: float,
    eff_max: float,
) -> tuple[Path, Path, Path]:
    config = load_config(config_path)
    lut_path = files_dir(config) / "step1_combined_scale_factor_lut.csv"
    lut = pd.read_csv(lut_path, low_memory=False)
    eff_columns = [f"eff_lut_{idx}" for idx in range(1, 5)]
    variable_column = eff_columns[variable_plane - 1]
    required = [*eff_columns, target_column]
    missing = [column for column in required if column not in lut.columns]
    if missing:
        raise ValueError(f"Combined LUT is missing poster columns: {missing}")

    data = lut.dropna(subset=required).copy()
    data[target_column] = pd.to_numeric(data[target_column], errors="coerce")
    nonpositive_scale_factor_count = int((data[target_column] <= 0).sum())
    data = data.loc[data[target_column] > 0].copy()
    data = data.loc[data[variable_column].between(eff_min, eff_max, inclusive="both")].copy()
    if data.empty:
        raise ValueError("No positive-scale-factor LUT rows remain in the requested poster efficiency range.")
    print(
        f"Poster plot excluded {nonpositive_scale_factor_count} nonpositive "
        f"{target_column} values; plotting {len(data)} supported LUT rows."
    )

    fixed_columns = [column for column in eff_columns if column != variable_column]
    data["fixed_plane_efficiency_mean"] = data[fixed_columns].mean(axis=1)
    variable_edges = np.linspace(eff_min, eff_max, 11)
    variable_centers = 0.5 * (variable_edges[:-1] + variable_edges[1:])
    fixed_efficiencies = np.linspace(eff_min, eff_max, 6)[:-1]
    fixed_band_half_width = max((eff_max - eff_min) / 20.0, 0.005)
    output_rows: list[dict[str, float | int]] = []

    fig, ax = plt.subplots(figsize=(7.4, 4.9), dpi=300)
    ax.scatter(data[variable_column], data[target_column], s=14, alpha=0.17, color="0.35", linewidths=0, label="LUT samples")
    colors = plt.cm.viridis(np.linspace(0.15, 0.88, len(fixed_efficiencies)))
    for fixed, color in zip(fixed_efficiencies, colors):
        band = data.loc[data["fixed_plane_efficiency_mean"].between(
            fixed - fixed_band_half_width,
            fixed + fixed_band_half_width,
            inclusive="left",
        )]
        x_values: list[float] = []
        medians: list[float] = []
        q25_values: list[float] = []
        q75_values: list[float] = []
        for bin_index, (left, right, center) in enumerate(
            zip(variable_edges[:-1], variable_edges[1:], variable_centers)
        ):
            inclusive = "both" if bin_index == len(variable_centers) - 1 else "left"
            subset = band.loc[band[variable_column].between(left, right, inclusive=inclusive), target_column]
            values = pd.to_numeric(subset, errors="coerce").dropna().to_numpy(dtype=float)
            if len(values) < 2:
                continue
            median = float(np.nanmedian(values))
            q25 = float(np.nanpercentile(values, 25))
            q75 = float(np.nanpercentile(values, 75))
            x_values.append(float(center))
            medians.append(median)
            q25_values.append(q25)
            q75_values.append(q75)
            output_rows.append({
                "fixed_plane_efficiency_mean": fixed,
                "variable_efficiency_bin_left": float(left),
                "variable_efficiency_bin_right": float(right),
                "variable_efficiency_bin_center": float(center),
                "median": median,
                "q25": q25,
                "q75": q75,
                "n_lut_points": int(len(values)),
            })
        if x_values:
            ax.plot(x_values, medians, marker="o", linewidth=2.2, color=color, label=f"other planes ~ {fixed:.2f}")
            ax.fill_between(x_values, q25_values, q75_values, color=color, alpha=0.13, linewidth=0)

    source = str(config.get("lut_efficiency_source", "simulated"))
    ax.set_xlabel(f"Plane-{variable_plane} LUT efficiency ({source})")
    ax.set_ylabel(target_column)
    ax.set_title(f"{target_column} vs plane-{variable_plane} efficiency")
    ax.set_xlim(eff_min, eff_max)
    visible = pd.to_numeric(data[target_column], errors="coerce").dropna().to_numpy(dtype=float)
    if visible.size:
        y_low = max(0.0, float(np.nanpercentile(visible, 2)) * 0.9)
        y_high = max(float(np.nanpercentile(visible, 98)) * 1.12, y_low + 0.1)
        ax.set_ylim(y_low, y_high)
    ax.grid(True, alpha=0.28)
    ax.legend(fontsize=8, loc="best")
    fig.tight_layout()

    stem = f"poster_{target_column}_vs_eff_lut_{variable_plane}"
    png_path = plots_dir(config) / f"{stem}.png"
    pdf_path = plots_dir(config) / f"{stem}.pdf"
    csv_path = files_dir(config) / f"{stem}_curves.csv"
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)
    pd.DataFrame(output_rows).to_csv(csv_path, index=False)
    return png_path, pdf_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the LUT and its poster plot without real-data processing.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--target-column", default="scale_factor__four_plane_robust_hz")
    parser.add_argument("--variable-plane", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--eff-min", type=float, default=0.9)
    parser.add_argument("--eff-max", type=float, default=1.0)
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    training_path = run_training_selection(config_path)
    lut_path = run_step_1(config_path)
    png_path, pdf_path, csv_path = create_poster_plot(
        config_path,
        target_column=args.target_column,
        variable_plane=args.variable_plane,
        eff_min=args.eff_min,
        eff_max=args.eff_max,
    )
    print(f"Training selection: {training_path}")
    print(f"Combined LUT: {lut_path}")
    print(f"Poster PNG: {png_path}")
    print(f"Poster PDF: {pdf_path}")
    print(f"Poster curves CSV: {csv_path}")


if __name__ == "__main__":
    main()
