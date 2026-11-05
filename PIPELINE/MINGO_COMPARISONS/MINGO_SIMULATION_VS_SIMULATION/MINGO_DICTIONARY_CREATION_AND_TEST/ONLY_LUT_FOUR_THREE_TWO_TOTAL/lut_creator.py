#!/usr/bin/env python3
"""
Build TASK_0 aggregate trigger-rate/flux LUT diagnostic plots.

Aggregate channels:

    total:
        Sum of all TASK_0 trigger-type rate columns matching:
            tt_task0_acq_*_rate_hz
        Also accepts:
            tt_task0_acs_*_rate_hz
        for robustness.

    extense:
        1234 + 124 + 134

    mid_sup:
        123 + 13

    three_four:
        1234 + 123 + 234 + 124 + 134

Upper panel:
    Raw effective area:

        A_group = R_group / Phi

Lower panel:
    Normalized effective area:

        F_group = A_group / A_group,0

    where A_group,0 is the fitted effective area at mean efficiency = 1.
    If the fit gives a non-positive or non-finite value, the script falls back
    to the maximum observed effective area for that group, avoiding crashes.

Expected reference terms are computed from the trigger-combination name.
For example:

    1234 -> e1 * e2       * e3       * e4
    124  -> e1 * e2       * (1-e3)   * e4
    13   -> e1 * (1-e2)   * e3       * (1-e4)

Output:
    PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/ONLY_LUT_FOUR_THREE_TWO_TOTAL/PLOTS/
    aggregate_trigger_rate_over_flux_vs_mean_efficiency.png
"""

from __future__ import annotations

import argparse
import ast
import re
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

OUTPUT_DIR = REPO_ROOT / "PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/ONLY_LUT_FOUR_THREE_TWO_TOTAL/PLOTS"

OUTPUT_PNG = OUTPUT_DIR / "aggregate_trigger_rate_over_flux_vs_mean_efficiency.png"

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

RATE_COLUMN_PATTERN = re.compile(r"^tt_task0_ac[qs]_(\d+)_rate_hz$")

REQUIRED_COMBOS = ("1234", "124", "134", "123", "13", "234")

AGGREGATE_DEFINITIONS = {
    "extense": ("1234", "124", "134"),
    "mid_sup": ("123", "13"),
    "three_four": ("1234", "123", "234", "124", "134"),
}

AGGREGATE_NAMES = ("total", "extense", "mid_sup", "three_four")

PLOT_COLOURS = {
    "total": "tab:red",
    "extense": "tab:blue",
    "mid_sup": "tab:orange",
    "three_four": "tab:green",
}


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


def discover_rate_columns(df: pd.DataFrame) -> dict[str, str]:
    """
    Discover TASK_0 trigger-type rate columns.

    Accepts both:
        tt_task0_acq_*_rate_hz
        tt_task0_acs_*_rate_hz

    If both spellings exist for the same combination, acq is preferred.
    """
    found: dict[str, str] = {}

    for col in df.columns:
        match = RATE_COLUMN_PATTERN.match(col)
        if not match:
            continue

        combo = match.group(1)

        # Prefer acq if both acq and acs exist.
        if combo not in found:
            found[combo] = col
        elif "_acq_" in col and "_acs_" in found[combo]:
            found[combo] = col

    return found


def require_rate_combos(
    rate_columns: dict[str, str],
    required_combos: Iterable[str],
    csv_path: Path,
) -> None:
    missing = [combo for combo in required_combos if combo not in rate_columns]
    if missing:
        raise ValueError(
            f"Missing required TASK_0 trigger-rate combinations in {csv_path}: "
            f"{missing}. Available combinations are: {sorted(rate_columns)}"
        )


def attach_simulation_parameters(
    rate_df: pd.DataFrame,
    rate_csv_path: Path,
    simulation_csv_path: Path,
) -> pd.DataFrame:
    """
    Ensure `flux_cm2_min` and `efficiencies` are available.

    If they are absent from TASK_0 metadata, attach them from
    step_final_simulation_params.csv using stable common metadata keys.
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


def expected_for_combo(df: pd.DataFrame, combo: str) -> pd.Series:
    """
    Compute the independent-efficiency expected term for a trigger combination.

    A digit present in the combination contributes eff_i.
    A digit absent from the combination contributes (1 - eff_i).
    """
    present = set(combo)

    term = pd.Series(1.0, index=df.index)

    for plane in ("1", "2", "3", "4"):
        eff_col = f"eff{plane}"
        if plane in present:
            term = term * df[eff_col]
        else:
            term = term * (1.0 - df[eff_col])

    return term


def fit_poly(
    mean_efficiency: np.ndarray,
    effective_area_cm2: np.ndarray,
    fit_degree: int,
    group_name: str,
) -> tuple[np.poly1d, float, str]:
    """
    Fit A_group(mean_efficiency) and obtain a normalization area.

    Preferred normalization:
        A_group,0 = fitted A_group at mean efficiency = 1

    Fallback:
        max observed A_group, if the extrapolated value is not positive/finite.
    """
    if len(mean_efficiency) < fit_degree + 1:
        raise ValueError(
            f"Cannot perform degree-{fit_degree} fit for {group_name} with only "
            f"{len(mean_efficiency)} valid points."
        )

    coeffs = np.polyfit(mean_efficiency, effective_area_cm2, deg=fit_degree)
    poly = np.poly1d(coeffs)
    area_at_1 = float(poly(1.0))

    if np.isfinite(area_at_1) and area_at_1 > 0:
        return poly, area_at_1, "fit_at_eff_1"

    fallback = float(np.nanmax(effective_area_cm2))

    if not np.isfinite(fallback) or fallback <= 0:
        raise ValueError(
            f"Cannot normalize {group_name}: fitted A(eff=1) = {area_at_1}, "
            f"and max observed effective area = {fallback}."
        )

    print(
        "Warning: "
        f"{group_name} fitted A(eff=1) is not positive/finite "
        f"({area_at_1:.8g}). Using max observed area instead: "
        f"{fallback:.8g} cm^2."
    )

    return poly, fallback, "max_observed_fallback"

def normalize_expected_for_plot(
    df: pd.DataFrame,
    group_name: str,
    measured_scale_col: str,
    expected_col: str,
    total_combos: tuple[str, ...],
) -> pd.Series:
    """
    Normalize expected curves for the lower panel.

    The expected value at perfect efficiency is evaluated as a scalar using a
    one-row DataFrame with eff1 = eff2 = eff3 = eff4 = 1.

    If expected(group) at perfect efficiency is positive, divide by that value.
    If it is zero, rescale the expected shape to the maximum measured normalized
    value. This keeps the curve visible without inventing a non-zero limit.
    """
    perfect_df = pd.DataFrame(
        {
            "eff1": [1.0],
            "eff2": [1.0],
            "eff3": [1.0],
            "eff4": [1.0],
        }
    )

    expected_at_1_series = expected_for_aggregate(
        df=perfect_df,
        group_name=group_name,
        total_combos=total_combos,
    )

    expected_at_1 = float(expected_at_1_series.iloc[0])

    expected = df[expected_col]

    if np.isfinite(expected_at_1) and expected_at_1 > 0:
        return expected / expected_at_1

    expected_max = float(expected.max())
    measured_max = float(df[measured_scale_col].max())

    if np.isfinite(expected_max) and expected_max > 0 and np.isfinite(measured_max):
        return expected / expected_max * measured_max

    return expected


def expected_for_aggregate(
    df: pd.DataFrame,
    group_name: str,
    total_combos: tuple[str, ...] | None,
) -> pd.Series | float:
    """
    Compute the expected term for an aggregate group.

    For total, use all discovered total_combos.
    For the named aggregates, use AGGREGATE_DEFINITIONS.
    """
    if group_name == "total":
        if total_combos is None:
            # Used only for perfect-efficiency scalar evaluation.
            # At perfect efficiency, only the 1234 term survives if present.
            return 1.0

        combos = total_combos
    else:
        combos = AGGREGATE_DEFINITIONS[group_name]

    if isinstance(df, pd.DataFrame):
        out = pd.Series(0.0, index=df.index)
        for combo in combos:
            out = out + expected_for_combo(df, combo)
        return out

    raise TypeError("df must be a pandas DataFrame")


def load_data(
    rate_csv_path: Path,
    simulation_csv_path: Path,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    rate_df = pd.read_csv(rate_csv_path)

    rate_columns = discover_rate_columns(rate_df)

    if not rate_columns:
        raise ValueError(
            f"No TASK_0 rate columns found in {rate_csv_path}. Expected names like "
            "tt_task0_acq_1234_rate_hz."
        )

    require_rate_combos(
        rate_columns=rate_columns,
        required_combos=REQUIRED_COMBOS,
        csv_path=rate_csv_path,
    )

    total_combos = tuple(sorted(rate_columns.keys(), key=lambda x: (len(x), x)))

    df = attach_simulation_parameters(
        rate_df=rate_df,
        rate_csv_path=rate_csv_path,
        simulation_csv_path=simulation_csv_path,
    )

    require_columns(df, ["flux_cm2_min", "efficiencies"], rate_csv_path)

    df["eff_list"] = df["efficiencies"].apply(parse_efficiencies)

    df["eff1"] = df["eff_list"].apply(lambda xs: xs[0] if len(xs) == 4 else np.nan)
    df["eff2"] = df["eff_list"].apply(lambda xs: xs[1] if len(xs) == 4 else np.nan)
    df["eff3"] = df["eff_list"].apply(lambda xs: xs[2] if len(xs) == 4 else np.nan)
    df["eff4"] = df["eff_list"].apply(lambda xs: xs[3] if len(xs) == 4 else np.nan)

    df["mean_efficiency"] = df[["eff1", "eff2", "eff3", "eff4"]].mean(axis=1)

    df["flux_cm2_min"] = pd.to_numeric(df["flux_cm2_min"], errors="coerce")

    # CSV flux units:
    #   flux_cm2_min = cts min^-1 cm^-2
    # Convert to:
    #   flux_cm2_s = cts s^-1 cm^-2
    # because trigger rates are in Hz = cts s^-1.
    df["flux_cm2_s"] = df["flux_cm2_min"] / 60.0

    # Load all individual rate columns discovered.
    for combo, col in rate_columns.items():
        df[f"rate_{combo}_hz"] = pd.to_numeric(df[col], errors="coerce")
        df[f"effective_area_{combo}_cm2"] = (
            df[f"rate_{combo}_hz"] / df["flux_cm2_s"]
        )
        df[f"expected_{combo}"] = expected_for_combo(df, combo)

    # Aggregate rates.
    df["rate_total_hz"] = sum(
        df[f"rate_{combo}_hz"] for combo in total_combos
    )

    df["rate_extense_hz"] = (
        df["rate_1234_hz"]
        + df["rate_124_hz"]
        + df["rate_134_hz"]
    )

    df["rate_mid_sup_hz"] = (
        df["rate_123_hz"]
        + df["rate_13_hz"]
    )

    df["rate_three_four_hz"] = (
        df["rate_1234_hz"]
        + df["rate_123_hz"]
        + df["rate_234_hz"]
        + df["rate_124_hz"]
        + df["rate_134_hz"]
    )

    # Aggregate effective areas.
    for group in AGGREGATE_NAMES:
        df[f"effective_area_{group}_cm2"] = (
            df[f"rate_{group}_hz"] / df["flux_cm2_s"]
        )

    # Aggregate expected terms.
    df["expected_total"] = expected_for_aggregate(
        df=df,
        group_name="total",
        total_combos=total_combos,
    )

    for group in ("extense", "mid_sup", "three_four"):
        df[f"expected_{group}"] = expected_for_aggregate(
            df=df,
            group_name=group,
            total_combos=total_combos,
        )

    df = df.replace([np.inf, -np.inf], np.nan)

    required_numeric = [
        "mean_efficiency",
        "flux_cm2_min",
        "flux_cm2_s",
    ]

    for combo in total_combos:
        required_numeric.extend(
            [
                f"rate_{combo}_hz",
                f"effective_area_{combo}_cm2",
                f"expected_{combo}",
            ]
        )

    for group in AGGREGATE_NAMES:
        required_numeric.extend(
            [
                f"rate_{group}_hz",
                f"effective_area_{group}_cm2",
                f"expected_{group}",
            ]
        )

    valid = df[required_numeric].notna().all(axis=1)
    valid &= df["flux_cm2_min"] > 0
    valid &= df["flux_cm2_s"] > 0

    for combo in total_combos:
        valid &= df[f"rate_{combo}_hz"] >= 0
        valid &= df[f"effective_area_{combo}_cm2"] >= 0

    for group in AGGREGATE_NAMES:
        valid &= df[f"rate_{group}_hz"] >= 0
        valid &= df[f"effective_area_{group}_cm2"] >= 0

    return df.loc[valid].copy(), total_combos


def make_plot(
    df: pd.DataFrame,
    output_png: Path,
    fit_degree: int,
    total_combos: tuple[str, ...],
) -> None:
    x = df["mean_efficiency"].to_numpy(dtype=float)

    fit_results: dict[str, dict[str, object]] = {}

    for group in AGGREGATE_NAMES:
        y_area = df[f"effective_area_{group}_cm2"].to_numpy(dtype=float)

        poly, norm_area, norm_mode = fit_poly(
            mean_efficiency=x,
            effective_area_cm2=y_area,
            fit_degree=fit_degree,
            group_name=group,
        )

        fit_results[group] = {
            "poly": poly,
            "norm_area": norm_area,
            "norm_mode": norm_mode,
        }

        df[f"scale_{group}"] = df[f"effective_area_{group}_cm2"] / norm_area

    x_grid = np.linspace(min(float(np.min(x)), 1.0), 1.0, 300)

    fig, (ax_area, ax_factor) = plt.subplots(
        nrows=2,
        ncols=1,
        figsize=(10.5, 9.0),
        sharex=True,
    )

    # -------------------------------------------------------------------------
    # Upper panel: raw effective areas.
    # -------------------------------------------------------------------------
    for group in AGGREGATE_NAMES:
        colour = PLOT_COLOURS[group]
        area_col = f"effective_area_{group}_cm2"

        data = df[["mean_efficiency", area_col]].dropna().sort_values(
            "mean_efficiency"
        )

        ax_area.scatter(
            data["mean_efficiency"],
            data[area_col],
            s=30,
            alpha=0.70,
            color=colour,
            label=rf"Measured {group}: $R/\Phi$",
        )

        poly = fit_results[group]["poly"]
        norm_area = float(fit_results[group]["norm_area"])
        norm_mode = str(fit_results[group]["norm_mode"])
        y_fit_grid = poly(x_grid)

        label = rf"Fit {group}, norm={norm_area:.3g} cm$^2$"
        if norm_mode != "fit_at_eff_1":
            label += " fallback"

        ax_area.plot(
            x_grid,
            y_fit_grid,
            linewidth=2.0,
            color=colour,
            alpha=0.95,
            label=label,
        )

        ax_area.scatter(
            [1.0],
            [float(poly(1.0))],
            marker="x",
            s=75,
            linewidths=2,
            color=colour,
        )

    ax_area.axvline(1.0, linestyle="--", linewidth=1, color="black", alpha=0.6)
    ax_area.set_ylim(bottom=0)
    ax_area.set_ylabel(r"Effective area, $R/\Phi$ [cm$^2$]")
    ax_area.set_title("TASK_0 aggregate trigger effective areas")
    ax_area.grid(True, alpha=0.3)
    ax_area.legend(fontsize=7, ncols=2)

        # -------------------------------------------------------------------------
    # Lower panel: normalized aggregate curves and expected references.
    # -------------------------------------------------------------------------
    for group in AGGREGATE_NAMES:
        colour = PLOT_COLOURS[group]
        scale_col = f"scale_{group}"
        expected_col = f"expected_{group}"
        expected_plot_col = f"expected_plot_{group}"

        # Compute the expected plotting curve here, immediately before use.
        df[expected_plot_col] = normalize_expected_for_plot(
            df=df,
            group_name=group,
            measured_scale_col=scale_col,
            expected_col=expected_col,
            total_combos=total_combos,
        )

        data = df[["mean_efficiency", scale_col, expected_plot_col]].dropna().sort_values(
            "mean_efficiency"
        )

        ax_factor.scatter(
            data["mean_efficiency"],
            data[scale_col],
            s=30,
            alpha=0.70,
            color=colour,
            label=rf"Measured {group}: $A/A_0$",
        )

        ax_factor.plot(
            data["mean_efficiency"],
            data[expected_plot_col],
            linestyle="--",
            linewidth=2.0,
            alpha=0.95,
            color=colour,
            label=rf"Expected {group}",
        )

    ax_factor.axhline(1.0, linestyle="--", linewidth=1, color="black", alpha=0.6)
    ax_factor.axvline(1.0, linestyle="--", linewidth=1, color="black", alpha=0.6)
    ax_factor.set_ylim(bottom=0)
    ax_factor.set_xlabel(r"Mean detector efficiency, $\bar{\epsilon}$")
    ax_factor.set_ylabel(r"Normalized effective area, $A/A_0$")
    ax_factor.grid(True, alpha=0.3)
    ax_factor.legend(fontsize=7, ncols=2)

    fig.tight_layout()
    fig.savefig(output_png, dpi=200)
    plt.close(fig)

    print("Discovered individual TASK_0 trigger-rate combinations used for total:")
    print(f"  {', '.join(total_combos)}")

    print()
    print("Aggregate definitions:")
    print("  total      = sum(all tt_task0_acq_*_rate_hz)")
    print("  extense    = 1234 + 124 + 134")
    print("  mid_sup    = 123 + 13")
    print("  three_four = 1234 + 123 + 234 + 124 + 134")

    print()
    print("Normalization effective areas:")
    for group in AGGREGATE_NAMES:
        norm_area = float(fit_results[group]["norm_area"])
        norm_mode = str(fit_results[group]["norm_mode"])
        print(f"  A_{group},0 = {norm_area:.8g} cm^2  [{norm_mode}]")

    print()
    print("Saved plot:")
    print(f"  {output_png}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate TASK_0 aggregate trigger-rate/flux LUT diagnostic plots. "
            "The defined aggregate channels are total, extense, mid_sup, and "
            "three_four. The output has two panels: raw effective area and "
            "normalized effective area."
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
        help=(
            "Polynomial degree for extrapolating aggregate effective areas to "
            "mean efficiency = 1. Default: 2."
        ),
    )

    args = parser.parse_args()

    if args.fit_degree < 1:
        raise ValueError(
            "A fit is required because the normalization needs an effective "
            "area scale. Use --fit-degree 1 or --fit-degree 2."
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)

    df, total_combos = load_data(
        rate_csv_path=args.input,
        simulation_csv_path=args.simulation_input,
    )

    if df.empty:
        raise RuntimeError(
            "No valid rows found. Check that the TASK_0 rate columns are filled, "
            "flux_cm2_min is positive, and efficiencies are parseable as four "
            "plane efficiencies."
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
        total_combos=total_combos,
    )


if __name__ == "__main__":
    main()
