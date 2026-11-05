#!/usr/bin/env python3
"""
Build the four-plane trigger-rate/flux LUT diagnostic plot.

This is the real-data analogue of ONLY_LUT/trigger_rate_vs_flux.py.  The
trigger rate is read from the TASK_0 trigger-type metadata column
`tt_task0_acq_1234_rate_hz` instead of from the simulation-parameter column
`trigger_rate_hz`.

The script needs, per row, the flux (`flux_cm2_min`), the detector efficiencies
(`efficiencies`), and the four-plane trigger rate.  If `flux_cm2_min` and
`efficiencies` are not present in the TASK_0 metadata file, they are joined from
`step_final_simulation_params.csv` through the available key columns.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()),
    None,
)
if REPO_ROOT is None:
    raise RuntimeError(f"Could not locate repository root from {__file__}")
DEFAULT_RATE_INPUT = REPO_ROOT / "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO00/STAGE_1/EVENT_DATA/STEP_1/TASK_0/METADATA/task_0_metadata_trigger_type.csv"

DEFAULT_SIMULATION_INPUT = REPO_ROOT / "PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv"

OUTPUT_DIR = REPO_ROOT / "PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/ONLY_LUT_FOUR_PLANE/PLOTS"
OUTPUT_PNG = OUTPUT_DIR / "four_plane_trigger_rate_over_flux_vs_mean_efficiency.png"

RATE_COLUMN = "tt_task0_acq_1234_rate_hz"
PARAMETER_COLUMNS = ("flux_cm2_min", "efficiencies")
MERGE_KEY_CANDIDATES = (
    "file_name",
    "param_hash",
    "param_set_id",
    "param_date",
    "execution_time",
    "cos_n",
    "z_plane_1",
    "z_plane_2",
    "z_plane_3",
    "z_plane_4",
)


def parse_efficiencies(value: object) -> list[float]:
    """Parse the efficiencies column, expected as a list-like string."""
    if pd.isna(value):
        return []

    try:
        parsed = ast.literal_eval(str(value))
    except (SyntaxError, ValueError):
        return []

    if not isinstance(parsed, (list, tuple)):
        return []

    try:
        return [float(x) for x in parsed]
    except (TypeError, ValueError):
        return []


def choose_merge_keys(left: pd.DataFrame, right: pd.DataFrame) -> list[str]:
    """Return stable metadata keys available in both tables."""
    return [c for c in MERGE_KEY_CANDIDATES if c in left.columns and c in right.columns]


def require_columns(df: pd.DataFrame, columns: Iterable[str], csv_path: Path) -> None:
    missing = set(columns) - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {csv_path}: {sorted(missing)}")


def attach_simulation_parameters(
    rate_df: pd.DataFrame,
    rate_csv_path: Path,
    simulation_csv_path: Path,
) -> pd.DataFrame:
    """
    Ensure `flux_cm2_min` and `efficiencies` are available.

    The TASK_0 metadata file may already contain these columns. Otherwise, they
    are attached from `step_final_simulation_params.csv` using all stable common
    metadata keys available in both files.
    """
    missing_params = [c for c in PARAMETER_COLUMNS if c not in rate_df.columns]
    if not missing_params:
        return rate_df.copy()

    if not simulation_csv_path.exists():
        raise FileNotFoundError(
            "The TASK_0 metadata file does not contain "
            f"{missing_params}, and the simulation parameter file was not found: "
            f"{simulation_csv_path}"
        )

    sim_df = pd.read_csv(simulation_csv_path)
    require_columns(sim_df, PARAMETER_COLUMNS, simulation_csv_path)

    merge_keys = choose_merge_keys(rate_df, sim_df)
    if not merge_keys:
        raise ValueError(
            "Cannot attach flux/efficiencies because no common merge key was "
            f"found between {rate_csv_path} and {simulation_csv_path}. "
            f"Expected at least one of: {list(MERGE_KEY_CANDIDATES)}"
        )

    # Only bring the parameter columns that are actually missing from rate_df.
    # This prevents pandas from creating *_x and *_y suffixed columns.
    columns_to_take = merge_keys + missing_params

    sim_subset = (
        sim_df[columns_to_take]
        .drop_duplicates(subset=merge_keys)
        .copy()
    )

    merged = rate_df.merge(
        sim_subset,
        on=merge_keys,
        how="left",
        validate="many_to_one",
    )

    missing_after_merge = [c for c in PARAMETER_COLUMNS if c not in merged.columns]
    if missing_after_merge:
        raise ValueError(
            "The following required parameter columns are still absent after "
            f"the merge: {missing_after_merge}. "
            f"Available columns are: {list(merged.columns)}"
        )

    unmatched = merged[list(PARAMETER_COLUMNS)].isna().any(axis=1).sum()
    if unmatched:
        print(
            "Warning: "
            f"{unmatched} rows could not be matched to flux/efficiency parameters "
            f"using keys {merge_keys}. These rows will be excluded."
        )

    return merged


def load_data(
    rate_csv_path: Path,
    simulation_csv_path: Path,
) -> pd.DataFrame:
    rate_df = pd.read_csv(rate_csv_path)
    require_columns(rate_df, [RATE_COLUMN], rate_csv_path)

    df = attach_simulation_parameters(
        rate_df=rate_df,
        rate_csv_path=rate_csv_path,
        simulation_csv_path=simulation_csv_path,
    )
    require_columns(df, [RATE_COLUMN, "flux_cm2_min", "efficiencies"], rate_csv_path)

    df["eff_list"] = df["efficiencies"].apply(parse_efficiencies)
    df["mean_efficiency"] = df["eff_list"].apply(
        lambda xs: float(np.mean(xs)) if len(xs) > 0 else np.nan
    )
    df["four_plane_trigger_rate_hz"] = pd.to_numeric(df[RATE_COLUMN], errors="coerce")
    df["flux_cm2_min"] = pd.to_numeric(df["flux_cm2_min"], errors="coerce")

    # CSV flux units:
    #   flux_cm2_min = cts min^-1 cm^-2
    # Convert to:
    #   flux_cm2_s = cts s^-1 cm^-2
    # because trigger rates are in Hz = cts s^-1.
    df["flux_cm2_s"] = df["flux_cm2_min"] / 60.0

    # Effective area:
    #   A_eff = R_trigger / Phi
    # Units:
    #   (cts s^-1) / (cts s^-1 cm^-2) = cm^2
    df["effective_area_cm2"] = df["four_plane_trigger_rate_hz"] / df["flux_cm2_s"]

    df = df.replace([np.inf, -np.inf], np.nan)
    valid = (
        df["mean_efficiency"].notna()
        & df["four_plane_trigger_rate_hz"].notna()
        & df["flux_cm2_min"].notna()
        & df["flux_cm2_s"].notna()
        & df["effective_area_cm2"].notna()
        & (df["flux_cm2_min"] > 0)
        & (df["flux_cm2_s"] > 0)
        & (df["four_plane_trigger_rate_hz"] >= 0)
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
    x_mean = df["mean_efficiency"].to_numpy(dtype=float)
    y_area = df["effective_area_cm2"].to_numpy(dtype=float)

    # Product of the four plane efficiencies:
    #   epsilon_prod = eff1 * eff2 * eff3 * eff4
    # This is the independent-efficiency expectation for a four-plane trigger.
    df["product_efficiency"] = df["eff_list"].apply(
        lambda xs: float(np.prod(xs)) if len(xs) == 4 else np.nan
    )

    poly_area, effective_area_at_eff_1 = fit_extrapolation(
        mean_efficiency=x_mean,
        effective_area_cm2=y_area,
        fit_degree=fit_degree,
    )

    # Efficiency scale factor:
    #   F(eff) = R_1234 / (Phi * A_eff,0)
    #          = A_eff(eff) / A_eff,0
    df["efficiency_scale_factor"] = (
        df["effective_area_cm2"] / effective_area_at_eff_1
    )

    # Correction factor:
    #   C(eff) = 1 / F(eff)
    # This is the multiplicative factor needed to correct the measured
    # four-plane rate to the ideal-efficiency rate.
    df["correction_factor"] = 1.0 / df["efficiency_scale_factor"]

    # Independent-plane correction reference:
    #   C_prod = 1 / (eff1 * eff2 * eff3 * eff4)
    df["product_correction_reference"] = 1.0 / df["product_efficiency"]

    df["correction_residual"] = (
        df["correction_factor"] - df["product_correction_reference"]
    )

    df["correction_ratio"] = (
        df["correction_factor"] / df["product_correction_reference"]
    )

    df = df.replace([np.inf, -np.inf], np.nan)

    y_factor = df["efficiency_scale_factor"].to_numpy(dtype=float)

    poly_factor = np.poly1d(poly_area.coeffs / effective_area_at_eff_1)
    x_grid = np.linspace(min(float(np.min(x_mean)), 1.0), 1.0, 300)
    y_area_grid = poly_area(x_grid)
    y_factor_grid = poly_factor(x_grid)

    diagnostic = (
        df[
            [
                "mean_efficiency",
                "product_efficiency",
                "effective_area_cm2",
                "efficiency_scale_factor",
                "correction_factor",
                "product_correction_reference",
                "correction_residual",
                "correction_ratio",
            ]
        ]
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
        .sort_values("product_efficiency")
    )

    if diagnostic.empty:
        raise RuntimeError(
            "No valid diagnostic rows found after computing product efficiency "
            "and correction factor."
        )

    correction_corr = diagnostic["correction_factor"].corr(
        diagnostic["product_correction_reference"]
    )

    residual_mean = float(diagnostic["correction_residual"].mean())
    residual_std = float(diagnostic["correction_residual"].std())
    ratio_median = float(diagnostic["correction_ratio"].median())
    ratio_std = float(diagnostic["correction_ratio"].std())

    fig, (ax_area, ax_factor_mean, ax_factor_product) = plt.subplots(
        nrows=3,
        ncols=1,
        figsize=(8.8, 11.5),
        sharex=False,
    )

    # -------------------------------------------------------------------------
    # Panel 1:
    # Effective area vs mean efficiency.
    # This preserves the original LUT/extrapolation diagnostic.
    # -------------------------------------------------------------------------
    ax_area.scatter(
        x_mean,
        y_area,
        s=35,
        alpha=0.8,
        label="TASK_0 four-plane points",
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
    ax_area.set_ylim(bottom=0)
    ax_area.set_ylabel(r"Effective area, $R_{1234}/\Phi$ [cm$^2$]")
    ax_area.set_title("Four-plane trigger LUT diagnostics")
    ax_area.grid(True, alpha=0.3)
    ax_area.legend(fontsize=8)

    # -------------------------------------------------------------------------
    # Panel 2:
    # Normalized scale factor vs mean efficiency.
    # -------------------------------------------------------------------------
    ax_factor_mean.scatter(
        x_mean,
        y_factor,
        s=35,
        alpha=0.8,
        label="Measured four-plane scale factor",
    )

    ax_factor_mean.plot(
        x_grid,
        y_factor_grid,
        linewidth=2,
        label=rf"$F(\bar{{\epsilon}})$ fit",
    )

    ax_factor_mean.scatter(
        [1.0],
        [1.0],
        marker="x",
        s=90,
        linewidths=2,
        label=rf"$F(\bar{{\epsilon}}=1)=1$",
    )

    ax_factor_mean.axhline(1.0, linestyle="--", linewidth=1)
    ax_factor_mean.axvline(1.0, linestyle="--", linewidth=1)
    ax_factor_mean.set_ylim(bottom=0)
    ax_factor_mean.set_xlabel(r"Mean detector efficiency, $\bar{\epsilon}$")
    ax_factor_mean.set_ylabel(
        r"Scale factor, $F = R_{1234}/(\Phi A_{\mathrm{eff},0})$"
    )
    ax_factor_mean.grid(True, alpha=0.3)
    ax_factor_mean.legend(fontsize=8)

        # -------------------------------------------------------------------------
    # Panel 3:
    # Correction factor vs mean efficiency.
    #
    # The correction factor is:
    #
    #   C = 1 / F
    #
    # where:
    #
    #   F = R_1234 / (Phi * A_eff,0)
    #
    # If the four planes behave independently:
    #
    #   F ~= eff1 * eff2 * eff3 * eff4
    #
    # therefore:
    #
    #   C ~= 1 / (eff1 * eff2 * eff3 * eff4)
    #
    # The reference is plotted against mean efficiency, not product efficiency.
    # -------------------------------------------------------------------------
    ax_factor_product.scatter(
        diagnostic["mean_efficiency"],
        diagnostic["correction_factor"],
        s=40,
        alpha=0.85,
        label=r"Measured correction, $C=1/F$",
    )

    ax_factor_product.plot(
        diagnostic["mean_efficiency"],
        diagnostic["product_correction_reference"],
        linestyle="--",
        linewidth=2.0,
        label=(
            r"Independent-plane reference: "
            r"$C=1/(\epsilon_1\epsilon_2\epsilon_3\epsilon_4)$"
        ),
    )

    ax_factor_product.axhline(1.0, linestyle="--", linewidth=1)
    ax_factor_product.axvline(1.0, linestyle="--", linewidth=1)
    ax_factor_product.set_xlim(left=min(float(np.min(x_mean)), 1.0), right=1.0)
    ax_factor_product.set_ylim(bottom=0)
    ax_factor_product.set_xlabel(r"Mean detector efficiency, $\bar{\epsilon}$")
    ax_factor_product.set_ylabel(r"Correction factor, $C=1/F$")
    ax_factor_product.grid(True, alpha=0.3)
    ax_factor_product.legend(fontsize=8)

    correction_corr = diagnostic["correction_factor"].corr(
        diagnostic["product_correction_reference"]
    )

    fig.tight_layout()
    fig.savefig(output_png, dpi=200)
    plt.close(fig)

    print("Extrapolated ideal four-plane effective area:")
    print(f"  A_eff,0 = {effective_area_at_eff_1:.8g} cm^2")
    print()
    print("Four-plane efficiency scale factor:")
    print("  F(eff) = R_1234 / (Phi * A_eff,0)")
    print("         = A_eff(eff) / A_eff,0")
    print()
    print("Correction-factor diagnostic:")
    print("  product_efficiency           = eff1 * eff2 * eff3 * eff4")
    print("  correction_factor            = 1 / F")
    print("  product_correction_reference = 1 / product_efficiency")
    print("  correction_residual          = correction_factor - product_correction_reference")
    print("  correction_ratio             = correction_factor / product_correction_reference")
    print()
    print("Diagnostic summary:")
    print(f"  corr(C, 1/product_efficiency) = {correction_corr:.8g}")
    print(f"  mean(correction_residual)     = {residual_mean:.8g}")
    print(f"  std(correction_residual)      = {residual_std:.8g}")
    print(f"  median(correction_ratio)      = {ratio_median:.8g}")
    print(f"  std(correction_ratio)         = {ratio_std:.8g}")
    print()
    print("Saved plot:")
    print(f"  {output_png}")
    


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a four-plane trigger-rate/flux LUT diagnostic plot from "
            "TASK_0 trigger-type metadata. The trigger rate is read from "
            f"{RATE_COLUMN}."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_RATE_INPUT,
        help=f"TASK_0 trigger-type metadata CSV. Default: {DEFAULT_RATE_INPUT}",
    )
    parser.add_argument(
        "--simulation-input",
        type=Path,
        default=DEFAULT_SIMULATION_INPUT,
        help=(
            "Simulation parameter CSV used only if the input metadata does not "
            f"already contain {PARAMETER_COLUMNS}. Default: {DEFAULT_SIMULATION_INPUT}"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PNG,
        help=f"Output PNG path. Default: {OUTPUT_PNG}",
    )
    parser.add_argument(
        "--fit-degree",
        type=int,
        default=2,
        help="Polynomial degree for extrapolation to mean efficiency = 2.",
    )

    args = parser.parse_args()

    if args.fit_degree < 0:
        raise ValueError(
            "A fit is required because F(eff) needs A_eff,0 at "
            "mean efficiency = 1. Use --fit-degree 1 or --fit-degree 2."
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)

    df = load_data(
        rate_csv_path=args.input,
        simulation_csv_path=args.simulation_input,
    )
    if df.empty:
        raise RuntimeError(
            "No valid rows found. Check that tt_task0_acq_1234_rate_hz is "
            "filled, flux_cm2_min is positive, and efficiencies are parseable."
        )

    print(f"Input CSV: {args.input}")
    print(f"Simulation CSV for parameter completion: {args.simulation_input}")
    print(f"Valid rows: {len(df)}")
    print(f"Output PNG: {args.output}")
    print()

    make_plot(
        df=df,
        output_png=args.output,
        fit_degree=args.fit_degree,
    )


if __name__ == "__main__":
    main()
