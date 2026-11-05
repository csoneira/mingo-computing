#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ast
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

REPO_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()),
    None,
)
if REPO_ROOT is None:
    raise RuntimeError(f"Could not locate repository root from {__file__}")

DEFAULT_INPUT = REPO_ROOT / "PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv"

OUTPUT_DIR = REPO_ROOT / "PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/ONLY_LUT/PLOTS"

OUTPUT_PNG = OUTPUT_DIR / "trigger_rate_over_flux_vs_mean_efficiency.png"


def parse_efficiencies(value: object) -> list[float]:
    """
    Parse the efficiencies column.

    Expected format:
        "[0.78, 0.79, 0.80, 0.81]"
    """
    if pd.isna(value):
        return []

    try:
        parsed = ast.literal_eval(str(value))
    except Exception:
        return []

    if not isinstance(parsed, (list, tuple)):
        return []

    try:
        return [float(x) for x in parsed]
    except Exception:
        return []


def load_data(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    required_columns = {
        "file_name",
        "flux_cm2_min",
        "efficiencies",
        "trigger_rate_hz",
    }

    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {csv_path}: {sorted(missing)}")

    df["eff_list"] = df["efficiencies"].apply(parse_efficiencies)

    df["mean_efficiency"] = df["eff_list"].apply(
        lambda xs: float(np.mean(xs)) if len(xs) > 0 else np.nan
    )

    df["trigger_rate_hz"] = pd.to_numeric(df["trigger_rate_hz"], errors="coerce")
    df["flux_cm2_min"] = pd.to_numeric(df["flux_cm2_min"], errors="coerce")

    # CSV flux units:
    #
    #   flux_cm2_min = cts min^-1 cm^-2
    #
    # Convert to:
    #
    #   flux_cm2_s = cts s^-1 cm^-2
    #
    # because trigger_rate_hz = cts s^-1.
    df["flux_cm2_s"] = df["flux_cm2_min"] / 60.0

    # Effective area:
    #
    #   A_eff = R_trigger / Phi
    #
    # Units:
    #
    #   (cts s^-1) / (cts s^-1 cm^-2) = cm^2
    #
    # Equivalently:
    #
    #   A_eff = 60 * trigger_rate_hz / flux_cm2_min
    #
    df["effective_area_cm2"] = df["trigger_rate_hz"] / df["flux_cm2_s"]

    df = df.replace([np.inf, -np.inf], np.nan)

    valid = (
        df["mean_efficiency"].notna()
        & df["trigger_rate_hz"].notna()
        & df["flux_cm2_min"].notna()
        & df["flux_cm2_s"].notna()
        & df["effective_area_cm2"].notna()
        & (df["flux_cm2_min"] > 0)
        & (df["flux_cm2_s"] > 0)
    )

    return df.loc[valid].copy()


def fit_extrapolation(
    mean_efficiency: np.ndarray,
    effective_area_cm2: np.ndarray,
    fit_degree: int,
) -> tuple[np.poly1d, float]:
    if len(mean_efficiency) < fit_degree + 1:
        raise ValueError(
            f"Cannot perform degree-{fit_degree} fit with only "
            f"{len(mean_efficiency)} valid points."
        )

    coeffs = np.polyfit(mean_efficiency, effective_area_cm2, deg=fit_degree)
    poly = np.poly1d(coeffs)

    effective_area_at_eff_1 = float(poly(1.0))

    if not np.isfinite(effective_area_at_eff_1) or effective_area_at_eff_1 <= 0:
        raise ValueError(
            "The extrapolated effective area at mean efficiency = 1 is not "
            f"positive and finite: {effective_area_at_eff_1}"
        )

    return poly, effective_area_at_eff_1


def make_plot(
    df: pd.DataFrame,
    output_png: Path,
    fit_degree: int,
) -> None:
    x = df["mean_efficiency"].to_numpy(dtype=float)
    y_area = df["effective_area_cm2"].to_numpy(dtype=float)

    poly_area, effective_area_at_eff_1 = fit_extrapolation(
        mean_efficiency=x,
        effective_area_cm2=y_area,
        fit_degree=fit_degree,
    )

    # Efficiency scale factor:
    #
    #   F(eff) = R_trigger / (Phi * A_eff,0)
    #
    # Since:
    #
    #   A_eff(eff) = R_trigger / Phi
    #
    # then:
    #
    #   F(eff) = A_eff(eff) / A_eff,0
    #
    # where A_eff,0 is the extrapolated ideal effective area at mean efficiency = 1.
    df["efficiency_scale_factor"] = (
        df["effective_area_cm2"] / effective_area_at_eff_1
    )

    y_factor = df["efficiency_scale_factor"].to_numpy(dtype=float)

    # Fit the dimensionless efficiency factor for visual guidance.
    poly_factor = np.poly1d(poly_area.coeffs / effective_area_at_eff_1)

    x_grid = np.linspace(min(float(np.min(x)), 1.0), 1.0, 300)
    y_area_grid = poly_area(x_grid)
    y_factor_grid = poly_factor(x_grid)

    fig, (ax_area, ax_factor) = plt.subplots(
        nrows=2,
        ncols=1,
        figsize=(8.5, 8.0),
        sharex=True,
    )

    # -------------------------------------------------------------------------
    # Panel 1: effective area
    # -------------------------------------------------------------------------
    ax_area.scatter(
        x,
        y_area,
        s=35,
        alpha=0.8,
        label="Simulation points",
    )

    ax_area.plot(
        x_grid,
        y_area_grid,
        linewidth=2,
        label=f"Degree-{fit_degree} extrapolation",
    )

    ax_area.scatter(
        [1.0],
        [effective_area_at_eff_1],
        marker="x",
        s=90,
        linewidths=2,
        label=(
            rf"$A_{{\mathrm{{eff}},0}}$"
            rf" = {effective_area_at_eff_1:.3g} cm$^2$"
        ),
    )

    ax_area.axvline(1.0, linestyle="--", linewidth=1)

    ax_area.set_ylabel(
        r"Effective area, $R_{\mathrm{trigger}} / \Phi$ [cm$^2$]"
    )
    ax_area.set_title("Effective area and efficiency scale factor")
    ax_area.grid(True, alpha=0.3)
    ax_area.legend()

    # -------------------------------------------------------------------------
    # Panel 2: efficiency scale factor F(eff)
    # -------------------------------------------------------------------------
    ax_factor.scatter(
        x,
        y_factor,
        s=35,
        alpha=0.8,
        label=r"Simulation points",
    )

    ax_factor.plot(
        x_grid,
        y_factor_grid,
        linewidth=2,
        label=rf"$F(\bar{{\epsilon}})$ fit",
    )

    ax_factor.scatter(
        [1.0],
        [1.0],
        marker="x",
        s=90,
        linewidths=2,
        label=rf"$F(\bar{{\epsilon}}=1)=1$",
    )

    ax_factor.axhline(1.0, linestyle="--", linewidth=1)
    ax_factor.axvline(1.0, linestyle="--", linewidth=1)

    ax_factor.set_xlabel(r"Mean detector efficiency, $\bar{\epsilon}$")
    ax_factor.set_ylabel(
        r"Efficiency scale factor, "
        r"$F(\bar{\epsilon}) = R_{\mathrm{trigger}} / "
        r"(\Phi A_{\mathrm{eff},0})$"
    )
    ax_factor.grid(True, alpha=0.3)
    ax_factor.legend()

    fig.tight_layout()
    fig.savefig(output_png, dpi=200)
    plt.close(fig)

    print("Extrapolated ideal effective area:")
    print(f"  A_eff,0 = {effective_area_at_eff_1:.8g} cm^2")
    print()
    print("Efficiency scale factor:")
    print("  F(eff) = R_trigger / (Phi * A_eff,0)")
    print("         = A_eff(eff) / A_eff,0")
    print()
    print("Saved plot:")
    print(f"  {output_png}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate trigger_rate_over_flux_vs_mean_efficiency.png "
            "from step_final_simulation_params.csv. The figure contains "
            "effective area in cm^2 and the dimensionless efficiency scale "
            "factor F(eff)."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input CSV path. Default: {DEFAULT_INPUT}",
    )

    parser.add_argument(
        "--fit-degree",
        type=int,
        default=2,
        help=(
            "Polynomial degree for extrapolation to mean efficiency = 1. "
            "Use 1 for linear or 2 for quadratic."
        ),
    )

    args = parser.parse_args()

    if args.fit_degree < 0:
        raise ValueError(
            "A fit is required because F(eff) needs A_eff,0 at "
            "mean efficiency = 1. Use --fit-degree 1 or --fit-degree 2."
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = load_data(args.input)

    if df.empty:
        raise RuntimeError(
            "No valid rows found. Check that trigger_rate_hz is filled, "
            "flux_cm2_min is positive, and efficiencies are parseable."
        )

    print(f"Input CSV: {args.input}")
    print(f"Valid rows: {len(df)}")
    print(f"Output PNG: {OUTPUT_PNG}")
    print()

    make_plot(
        df=df,
        output_png=OUTPUT_PNG,
        fit_degree=args.fit_degree,
    )


if __name__ == "__main__":
    main()
