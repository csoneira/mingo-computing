#!/usr/bin/env python3
"""
Build poster-ready LUT diagnostics from TASK_0 gate-test metadata.

Input metadata:

    TASK_0/METADATA/task_0_metadata_gate_test.csv

Expected gate-test columns:

    gate_test_q00_count
    gate_test_q00_rate_hz
    ...
    gate_test_q09_count
    gate_test_q09_rate_hz

The selected quantiles are controlled by:

    QUANTILES_TO_USE = [0, 1, 2, 4, 5, 6, 9]

For each selected gate quantile q:

    A_q = R_q / Phi

where:
    R_q is gate_test_qXX_rate_hz
    Phi is flux_cm2_s = flux_cm2_min / 60

Each gate quantile gets its own extrapolated top effective area:

    A_q,0 = A_q(mean_efficiency = 1)

The absolute correction factor is:

    C_q = Phi / R_q = 1 / A_q

This definition does NOT divide by A_q,0. Therefore the correction factor keeps
the effective-area scale and the efficiency dependence together.

Reference correction:

    A_ref_q(eff) = A_q,0 * eff1 * eff2 * eff3 * eff4
    C_ref_q(eff) = 1 / A_ref_q(eff)

Output figures:

    1. q00 trigger rate vs mean efficiency, coloured by flux.
    2. Effective area and absolute correction factor.

No legends are shown.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# User-controlled gate quantiles.
#
# q00 must be included because the first separate figure uses
# gate_test_q00_rate_hz.
#
# Example:
#   [0, 1, 2, 4, 5, 6, 9]
#
# means:
#   gate_test_q00_rate_hz
#   gate_test_q01_rate_hz
#   gate_test_q02_rate_hz
#   gate_test_q04_rate_hz
#   gate_test_q05_rate_hz
#   gate_test_q06_rate_hz
#   gate_test_q09_rate_hz
# ---------------------------------------------------------------------------
QUANTILES_TO_USE = [0, 1, 2, 3]


REPO_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()),
    None,
)
if REPO_ROOT is None:
    raise RuntimeError(f"Could not locate repository root from {__file__}")
DEFAULT_GATE_INPUT = REPO_ROOT / "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO00/STAGE_1/EVENT_DATA/STEP_1/TASK_0/METADATA/task_0_metadata_gate_test.csv"

DEFAULT_SIMULATION_INPUT = REPO_ROOT / "PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv"

OUTPUT_DIR = REPO_ROOT / "PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/ONLY_LUT_FINAL/PLOTS"

OUTPUT_PNG_RATE = OUTPUT_DIR / "poster_lut_gate_q00_rate_vs_mean_efficiency.png"
OUTPUT_PNG_LUT = OUTPUT_DIR / "poster_lut_gate_effective_area_and_correction.png"

PARAMETER_COLUMNS = ("flux_cm2_min", "efficiencies")
Z_POSITION_COLUMNS = ("z_plane_1", "z_plane_2", "z_plane_3", "z_plane_4")
SIMULATION_COLUMNS = PARAMETER_COLUMNS + Z_POSITION_COLUMNS
DEFAULT_POSTER_Z_POSITIONS = (0.0, 145.0, 290.0, 435.0)

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


def gate_label(q: int) -> str:
    return f"q{q:02d}"


def gate_rate_column(q: int) -> str:
    return f"gate_test_q{q:02d}_rate_hz"


def gate_count_column(q: int) -> str:
    return f"gate_test_q{q:02d}_count"


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
    gate_df: pd.DataFrame,
    gate_csv_path: Path,
    simulation_csv_path: Path,
) -> pd.DataFrame:
    """
    Ensure flux, efficiencies, and detector z positions are available.

    If they are absent from TASK_0 gate-test metadata, attach them from
    step_final_simulation_params.csv using stable common metadata keys.
    """
    missing_params = [c for c in SIMULATION_COLUMNS if c not in gate_df.columns]
    if not missing_params:
        return gate_df.copy()

    if not simulation_csv_path.exists():
        raise FileNotFoundError(
            "The gate-test metadata file does not contain "
            f"{missing_params}, and the simulation parameter file was not found: "
            f"{simulation_csv_path}"
        )

    sim_df = pd.read_csv(simulation_csv_path)
    require_columns(sim_df, SIMULATION_COLUMNS, simulation_csv_path)

    merge_keys = choose_merge_keys(gate_df, sim_df)
    if not merge_keys:
        raise ValueError(
            "Cannot attach flux/efficiencies because no common merge key was "
            f"found between {gate_csv_path} and {simulation_csv_path}. "
            f"Expected at least one of: {list(MERGE_KEY_CANDIDATES)}"
        )

    columns_to_take = merge_keys + list(missing_params)

    sim_subset = (
        sim_df[columns_to_take]
        .drop_duplicates(subset=merge_keys)
        .copy()
    )

    merged = gate_df.merge(
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

    unmatched = merged[list(SIMULATION_COLUMNS)].isna().any(axis=1).sum()
    if unmatched:
        print(
            "Warning: "
            f"{unmatched} rows could not be matched to flux/efficiency parameters "
            f"using keys {merge_keys}. These rows will be excluded."
        )

    return merged


def select_single_geometry(
    df: pd.DataFrame,
    requested_z_positions: tuple[float, float, float, float] | None,
) -> pd.DataFrame:
    """Select one exact detector geometry before constructing or fitting the LUT."""
    require_columns(df, Z_POSITION_COLUMNS, DEFAULT_SIMULATION_INPUT)

    geometry_rows = df.loc[:, Z_POSITION_COLUMNS].apply(
        pd.to_numeric,
        errors="coerce",
    )
    finite_geometry = np.isfinite(geometry_rows.to_numpy(dtype=float)).all(axis=1)
    df = df.loc[finite_geometry].copy()
    geometry_rows = geometry_rows.loc[finite_geometry]

    if df.empty:
        raise RuntimeError("No valid rows have four finite detector z positions.")

    geometry_counts = geometry_rows.value_counts(sort=True)
    if requested_z_positions is None:
        selected_geometry = tuple(float(value) for value in geometry_counts.index[0])
        selection_source = "most frequent valid geometry"
    else:
        selected_geometry = tuple(float(value) for value in requested_z_positions)
        selection_source = "explicit --z-positions"

    geometry_mask = np.ones(len(df), dtype=bool)
    for column, selected_value in zip(Z_POSITION_COLUMNS, selected_geometry):
        geometry_mask &= np.isclose(
            geometry_rows[column].to_numpy(dtype=float),
            selected_value,
            rtol=0.0,
            atol=1e-9,
        )

    selected_df = df.loc[geometry_mask].copy()
    if selected_df.empty:
        available = [
            tuple(float(value) for value in geometry)
            for geometry in geometry_counts.index.tolist()
        ]
        raise RuntimeError(
            f"No valid LUT rows match requested z positions {selected_geometry}. "
            f"Available geometries: {available}"
        )

    print("Detector geometry selection:")
    print(f"  source = {selection_source}")
    print(f"  selected z positions [mm] = {selected_geometry}")
    print(f"  selected rows = {len(selected_df)} / {len(df)}")
    print("  available valid geometries:")
    for geometry, count in geometry_counts.items():
        geometry_tuple = tuple(float(value) for value in geometry)
        print(f"    {geometry_tuple}: {int(count)} rows")
    print()

    return selected_df


def fit_extrapolation(
    mean_efficiency: np.ndarray,
    effective_area_cm2: np.ndarray,
    fit_degree: int,
    label: str,
) -> tuple[np.poly1d, float]:
    """Fit A(mean_efficiency) and evaluate at mean_efficiency = 1."""
    if len(mean_efficiency) < fit_degree + 1:
        raise ValueError(
            f"Cannot perform degree-{fit_degree} fit for {label} with only "
            f"{len(mean_efficiency)} valid points."
        )

    coeffs = np.polyfit(mean_efficiency, effective_area_cm2, deg=fit_degree)
    poly = np.poly1d(coeffs)
    effective_area_at_eff_1 = float(poly(1.0))

    if not np.isfinite(effective_area_at_eff_1) or effective_area_at_eff_1 <= 0:
        raise ValueError(
            f"The extrapolated effective area for {label} at mean efficiency = 1 "
            f"is not positive and finite: {effective_area_at_eff_1}"
        )

    return poly, effective_area_at_eff_1


def load_data(
    gate_csv_path: Path,
    simulation_csv_path: Path,
    quantiles_to_use: list[int],
    requested_z_positions: tuple[float, float, float, float] | None = None,
) -> pd.DataFrame:
    gate_df = pd.read_csv(gate_csv_path)

    selected_rate_columns = [gate_rate_column(q) for q in quantiles_to_use]
    require_columns(gate_df, selected_rate_columns, gate_csv_path)

    # q00 is required for the first figure.
    require_columns(gate_df, [gate_rate_column(0)], gate_csv_path)

    df = attach_simulation_parameters(
        gate_df=gate_df,
        gate_csv_path=gate_csv_path,
        simulation_csv_path=simulation_csv_path,
    )

    require_columns(df, SIMULATION_COLUMNS, gate_csv_path)

    df["eff_list"] = df["efficiencies"].apply(parse_efficiencies)

    df["eff1"] = df["eff_list"].apply(lambda xs: xs[0] if len(xs) == 4 else np.nan)
    df["eff2"] = df["eff_list"].apply(lambda xs: xs[1] if len(xs) == 4 else np.nan)
    df["eff3"] = df["eff_list"].apply(lambda xs: xs[2] if len(xs) == 4 else np.nan)
    df["eff4"] = df["eff_list"].apply(lambda xs: xs[3] if len(xs) == 4 else np.nan)

    df["mean_efficiency"] = df[["eff1", "eff2", "eff3", "eff4"]].mean(axis=1)

    df["reference_efficiency_1234"] = (
        df["eff1"] * df["eff2"] * df["eff3"] * df["eff4"]
    )

    df["flux_cm2_min"] = pd.to_numeric(df["flux_cm2_min"], errors="coerce")

    # CSV flux units:
    #   flux_cm2_min = cts min^-1 cm^-2
    # Convert to:
    #   flux_cm2_s = cts s^-1 cm^-2
    # because gate-test rates are in Hz = cts s^-1.
    df["flux_cm2_s"] = df["flux_cm2_min"] / 60.0

    for q in quantiles_to_use:
        q_label = gate_label(q)
        rate_col = gate_rate_column(q)

        df[f"rate_{q_label}_hz"] = pd.to_numeric(df[rate_col], errors="coerce")
        df[f"effective_area_{q_label}_cm2"] = (
            df[f"rate_{q_label}_hz"] / df["flux_cm2_s"]
        )

    # Ensure q00 exists even if the user later edits QUANTILES_TO_USE.
    if "rate_q00_hz" not in df.columns:
        df["rate_q00_hz"] = pd.to_numeric(
            df[gate_rate_column(0)],
            errors="coerce",
        )

    df = df.replace([np.inf, -np.inf], np.nan)

    required_numeric = [
        "mean_efficiency",
        "flux_cm2_min",
        "flux_cm2_s",
        "eff1",
        "eff2",
        "eff3",
        "eff4",
        "reference_efficiency_1234",
        "rate_q00_hz",
    ]

    for q in quantiles_to_use:
        q_label = gate_label(q)
        required_numeric.extend(
            [
                f"rate_{q_label}_hz",
                f"effective_area_{q_label}_cm2",
            ]
        )

    valid = df[required_numeric].notna().all(axis=1)
    valid &= df["flux_cm2_min"] > 0
    valid &= df["flux_cm2_s"] > 0
    valid &= df["reference_efficiency_1234"] > 0
    valid &= df["rate_q00_hz"] >= 0

    for q in quantiles_to_use:
        q_label = gate_label(q)
        valid &= df[f"rate_{q_label}_hz"] >= 0
        valid &= df[f"effective_area_{q_label}_cm2"] >= 0

    return select_single_geometry(
        df.loc[valid].copy(),
        requested_z_positions=requested_z_positions,
    )


def make_plot(
    df: pd.DataFrame,
    output_png_rate: Path,
    output_png_lut: Path,
    fit_degree: int,
    quantiles_to_use: list[int],
    highlight_recent: int,
) -> None:
    plot_timestamps = pd.to_datetime(
        df.get("execution_timestamp"),
        format="%Y-%m-%d_%H.%M.%S",
        errors="coerce",
    )
    recent_indices = set(
        plot_timestamps.dropna().sort_values().tail(max(highlight_recent, 0)).index
    )
    recent_mask = df.index.to_series().isin(recent_indices)
    newest_timestamp = (
        plot_timestamps.max().strftime("%Y-%m-%d %H:%M:%S")
        if plot_timestamps.notna().any()
        else "unknown"
    )
    subtitle = (
        f"\nn={len(df)} | newest={newest_timestamp}" if highlight_recent > 0 else ""
    )
    x_mean = df["mean_efficiency"].to_numpy(dtype=float)

    fit_results: dict[str, dict[str, object]] = {}
    valid_quantiles: list[int] = []

    for q in quantiles_to_use:
        q_label = gate_label(q)
        area_col = f"effective_area_{q_label}_cm2"

        fit_df = df[["mean_efficiency", area_col]].dropna().copy()
        fit_df = fit_df[fit_df[area_col] > 0]

        if len(fit_df) < fit_degree + 1:
            print(
                "Warning: "
                f"Skipping {q_label}; not enough positive effective-area points "
                f"for a degree-{fit_degree} fit."
            )
            continue

        try:
            poly, area_at_1 = fit_extrapolation(
                mean_efficiency=fit_df["mean_efficiency"].to_numpy(dtype=float),
                effective_area_cm2=fit_df[area_col].to_numpy(dtype=float),
                fit_degree=fit_degree,
                label=q_label,
            )
        except ValueError as exc:
            print(f"Warning: skipping {q_label}; {exc}")
            continue

        fit_results[q_label] = {
            "poly": poly,
            "area_at_1": area_at_1,
        }

        # Absolute correction:
        #   A_q = R_q / Phi
        #   C_q = Phi / R_q = 1 / A_q
        #
        # No division by A_q,0 is applied here.
        df[f"correction_factor_{q_label}"] = 1.0 / df[area_col]

        # Reference correction including both A_q,0 and efficiency:
        #   A_ref_q(eff) = A_q,0 * eff1 * eff2 * eff3 * eff4
        #   C_ref_q(eff) = 1 / A_ref_q(eff)
        df[f"reference_correction_{q_label}"] = (
            1.0 / (area_at_1 * df["reference_efficiency_1234"])
        )

        valid_quantiles.append(q)

    if not valid_quantiles:
        raise RuntimeError(
            "No selected quantile produced a valid positive effective-area fit. "
            "Check gate_test rates, selected quantiles, and fit degree."
        )

    df = df.replace([np.inf, -np.inf], np.nan)

    x_grid = np.linspace(min(float(np.min(x_mean)), 1.0), 1.0, 300)

    # Poster-style formatting.
    title_fontsize = 15
    label_fontsize = 13
    tick_fontsize = 11
    cbar_label_fontsize = 12

    scatter_size = 35
    extrapolated_marker_size = 90
    line_width = 2.0
    grid_alpha = 0.3

    colour_cycle = plt.rcParams["axes.prop_cycle"].by_key()["color"]

    # =========================================================================
    # FIGURE 1:
    # q00 trigger rate vs mean efficiency, coloured by flux.
    # =========================================================================
    fig_rate, ax_rate_eff = plt.subplots(
        nrows=1,
        ncols=1,
        figsize=(5, 4),
    )

    rate_eff_data = (
        df[
            [
                "mean_efficiency",
                "flux_cm2_min",
                "rate_q00_hz",
            ]
        ]
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
        .copy()
    )

    sc = ax_rate_eff.scatter(
        rate_eff_data["mean_efficiency"],
        rate_eff_data["rate_q00_hz"],
        c=rate_eff_data["flux_cm2_min"],
        cmap="plasma_r",
        s=scatter_size,
        alpha=0.8,
        edgecolors="0.20",
        linewidths=0.25,
    )
    recent_rate_data = df.loc[recent_mask, ["mean_efficiency", "rate_q00_hz"]].dropna()
    if not recent_rate_data.empty:
        ax_rate_eff.scatter(
            recent_rate_data["mean_efficiency"],
            recent_rate_data["rate_q00_hz"],
            marker="o",
            facecolors="none",
            edgecolors="black",
            linewidths=1.2,
            s=scatter_size * 1.8,
            label=f"Newest {len(recent_rate_data)} selected points",
        )
        ax_rate_eff.legend(fontsize=8)

    cbar = fig_rate.colorbar(sc, ax=ax_rate_eff)
    cbar.set_label(
        r"Flux, $\Phi$ [cts min$^{-1}$ cm$^{-2}$]",
        fontsize=cbar_label_fontsize,
    )
    cbar.ax.tick_params(labelsize=tick_fontsize)

    ax_rate_eff.set_ylim(bottom=0)
    ax_rate_eff.set_xlabel(
        r"Mean detector efficiency, $\bar{\epsilon}$",
        fontsize=label_fontsize,
    )
    ax_rate_eff.set_ylabel(
        r"Trigger rate [Hz]",
        fontsize=label_fontsize,
    )
    ax_rate_eff.set_title(
        "All-pass gate rate vs mean efficiency" + subtitle,
        fontsize=max(title_fontsize - 3, 9) if highlight_recent > 0 else title_fontsize,
    )
    ax_rate_eff.tick_params(axis="both", labelsize=tick_fontsize)
    ax_rate_eff.grid(True, alpha=grid_alpha)

    fig_rate.tight_layout()
    fig_rate.savefig(output_png_rate, dpi=300)
    plt.close(fig_rate)

    # =========================================================================
    # FIGURE 2:
    # Effective area and absolute correction factor.
    # =========================================================================
    fig_lut, (ax_area, ax_correction) = plt.subplots(
        nrows=2,
        ncols=1,
        figsize=(6.5, 8.0),
        sharex=True,
    )

    # -------------------------------------------------------------------------
    # Panel 1:
    # Effective area vs mean efficiency.
    #
    # y-axis is logarithmic. Therefore no lower limit of zero is imposed.
    # Only strictly positive points and strictly positive fit values are shown.
    # -------------------------------------------------------------------------
    for idx, q in enumerate(valid_quantiles):
        q_label = gate_label(q)
        colour = colour_cycle[idx % len(colour_cycle)]
        area_col = f"effective_area_{q_label}_cm2"

        data = df[["mean_efficiency", area_col]].dropna().sort_values(
            "mean_efficiency"
        )
        data = data[data[area_col] > 0]

        if data.empty:
            continue

        poly = fit_results[q_label]["poly"]
        area_at_1 = float(fit_results[q_label]["area_at_1"])
        y_fit_grid = poly(x_grid)

        valid_fit = y_fit_grid > 0

        ax_area.scatter(
            data["mean_efficiency"],
            data[area_col],
            s=scatter_size,
            alpha=0.8,
            color=colour,
        )
        recent_data = df.loc[recent_mask, ["mean_efficiency", area_col]].dropna()
        recent_data = recent_data[recent_data[area_col] > 0]
        if not recent_data.empty:
            ax_area.scatter(
                recent_data["mean_efficiency"],
                recent_data[area_col],
                marker="o",
                facecolors="none",
                edgecolors="black",
                linewidths=1.0,
                s=scatter_size * 1.7,
            )

        ax_area.plot(
            x_grid[valid_fit],
            y_fit_grid[valid_fit],
            linewidth=line_width,
            color=colour,
        )

        ax_area.scatter(
            [1.0],
            [area_at_1],
            marker="x",
            s=extrapolated_marker_size,
            linewidths=2,
            color=colour,
        )

    ax_area.axvline(1.0, linestyle="--", linewidth=1, color="black", alpha=0.7)
    ax_area.set_yscale("log")
    ax_area.set_ylabel(
        r"Effective area," "\n" r"$A_q=R_q/\Phi$ [cm$^2$]",
        fontsize=label_fontsize,
    )
    ax_area.set_title(
        "Gate-test effective area extrapolation" + subtitle,
        fontsize=max(title_fontsize - 3, 9) if highlight_recent > 0 else title_fontsize,
    )
    ax_area.tick_params(axis="both", labelsize=tick_fontsize)
    ax_area.grid(True, which="both", alpha=grid_alpha)

    # -------------------------------------------------------------------------
    # Panel 2:
    # Absolute correction factor vs mean efficiency.
    #
    #   C_q = Phi / R_q = 1 / A_q
    #
    # y-axis is logarithmic.
    # -------------------------------------------------------------------------
    for idx, q in enumerate(valid_quantiles):
        q_label = gate_label(q)
        colour = colour_cycle[idx % len(colour_cycle)]
        corr_col = f"correction_factor_{q_label}"
        ref_corr_col = f"reference_correction_{q_label}"

        data = df[["mean_efficiency", corr_col, ref_corr_col]].dropna().sort_values(
            "mean_efficiency"
        )
        data = data[(data[corr_col] > 0) & (data[ref_corr_col] > 0)]

        if data.empty:
            continue

        ax_correction.scatter(
            data["mean_efficiency"],
            data[corr_col],
            s=scatter_size,
            alpha=0.8,
            color=colour,
        )
        recent_data = df.loc[
            recent_mask, ["mean_efficiency", corr_col, ref_corr_col]
        ].dropna()
        recent_data = recent_data[
            (recent_data[corr_col] > 0) & (recent_data[ref_corr_col] > 0)
        ]
        if not recent_data.empty:
            ax_correction.scatter(
                recent_data["mean_efficiency"],
                recent_data[corr_col],
                marker="o",
                facecolors="none",
                edgecolors="black",
                linewidths=1.0,
                s=scatter_size * 1.7,
            )

        ax_correction.plot(
            data["mean_efficiency"],
            data[ref_corr_col],
            linestyle="--",
            linewidth=line_width,
            color=colour,
        )

    ax_correction.axvline(1.0, linestyle="--", linewidth=1, color="black", alpha=0.7)
    ax_correction.set_yscale("log")
    ax_correction.set_xlabel(
        r"Mean detector efficiency, $\bar{\epsilon}$",
        fontsize=label_fontsize,
    )
    ax_correction.set_ylabel(
        r"Absolute correction factor," "\n" r"$C_q=\Phi/R_q$ [cm$^{-2}$]",
        fontsize=label_fontsize,
    )
    ax_correction.set_title(
        r"Gate-test absolute correction factor",
        fontsize=title_fontsize,
    )
    ax_correction.tick_params(axis="both", labelsize=tick_fontsize)
    ax_correction.grid(True, which="both", alpha=grid_alpha)

    fig_lut.tight_layout()
    fig_lut.savefig(output_png_lut, dpi=300)
    plt.close(fig_lut)

    print("Selected gate quantiles:")
    print(f"  requested = {quantiles_to_use}")
    print(f"  plotted   = {valid_quantiles}")
    print(f"  selected geometry rows = {len(df)}")
    print(f"  newest selected point = {newest_timestamp}")
    print(f"  newest selected points highlighted = {len(recent_indices)}")

    print()
    print("Fitted top effective areas at mean efficiency = 1:")
    for q in valid_quantiles:
        q_label = gate_label(q)
        print(
            f"  A_{q_label},0 = "
            f"{float(fit_results[q_label]['area_at_1']):.8g} cm^2"
        )

    print()
    print("Correction factors:")
    for q in valid_quantiles:
        q_label = gate_label(q)
        print(f"  C_{q_label} = Phi / R_{q_label} = 1 / A_{q_label}")

    print()
    print("Reference correction:")
    print("  A_ref_q(eff) = A_q,0 * eff1 * eff2 * eff3 * eff4")
    print("  C_ref_q(eff) = 1 / A_ref_q(eff)")
    print("               = 1 / (A_q,0 * eff1 * eff2 * eff3 * eff4)")

    print()
    print("Poster figures:")
    print("  Figure 1: gate q00 rate vs mean efficiency, continuous colour = flux")
    print("  Figure 2: gate-test effective area and absolute correction factor")
    print()
    print("Saved plots:")
    print(f"  {output_png_rate}")
    print(f"  {output_png_lut}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate poster-ready LUT diagnostic plots from TASK_0 gate-test "
            "metadata. Each selected gate quantile gets its own effective area "
            "and absolute correction factor."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_GATE_INPUT,
        help=f"TASK_0 gate-test metadata CSV. Default: {DEFAULT_GATE_INPUT}",
    )

    parser.add_argument(
        "--simulation-input",
        type=Path,
        default=DEFAULT_SIMULATION_INPUT,
        help=(
            "Simulation parameter CSV used only if the input metadata does not "
            f"already contain {SIMULATION_COLUMNS}. Default: {DEFAULT_SIMULATION_INPUT}"
        ),
    )

    parser.add_argument(
        "--output-rate",
        type=Path,
        default=OUTPUT_PNG_RATE,
        help=f"Output PNG path for the q00 rate figure. Default: {OUTPUT_PNG_RATE}",
    )

    parser.add_argument(
        "--output-lut",
        type=Path,
        default=OUTPUT_PNG_LUT,
        help=f"Output PNG path for the LUT figure. Default: {OUTPUT_PNG_LUT}",
    )

    parser.add_argument(
        "--fit-degree",
        type=int,
        default=2,
        help=(
            "Polynomial degree for extrapolating each effective area to "
            "mean efficiency = 1. Default: 2."
        ),
    )
    parser.add_argument(
        "--highlight-recent",
        type=int,
        default=0,
        help=(
            "Outline this many newest points from the selected geometry. "
            "Default: 0, disabled for poster output."
        ),
    )

    parser.add_argument(
        "--z-positions",
        type=float,
        nargs=4,
        metavar=("Z1", "Z2", "Z3", "Z4"),
        default=DEFAULT_POSTER_Z_POSITIONS,
        help=(
            "Exact detector z positions in mm to use for the LUT. "
            f"Default: MINGO02 selected-period geometry {DEFAULT_POSTER_Z_POSITIONS}."
        ),
    )

    args = parser.parse_args()

    if args.fit_degree < 1:
        raise ValueError(
            "A fit is required because each gate needs A_q,0 at mean efficiency = 1. "
            "Use --fit-degree 1 or --fit-degree 2."
        )
    if args.highlight_recent < 0:
        raise ValueError("--highlight-recent must be >= 0.")

    if any(q < 0 or q > 9 for q in QUANTILES_TO_USE):
        raise ValueError(
            f"Invalid QUANTILES_TO_USE={QUANTILES_TO_USE}. "
            "Expected integer quantile indices from 0 to 9."
        )

    if 0 not in QUANTILES_TO_USE:
        raise ValueError(
            "QUANTILES_TO_USE must include 0 because the first poster figure "
            "uses gate_test_q00_rate_hz."
        )

    args.output_rate.parent.mkdir(parents=True, exist_ok=True)
    args.output_lut.parent.mkdir(parents=True, exist_ok=True)

    df = load_data(
        gate_csv_path=args.input,
        simulation_csv_path=args.simulation_input,
        quantiles_to_use=QUANTILES_TO_USE,
        requested_z_positions=(
            tuple(args.z_positions) if args.z_positions is not None else None
        ),
    )

    if df.empty:
        raise RuntimeError(
            "No valid rows found. Check that gate_test_qXX_rate_hz columns are "
            "filled, flux_cm2_min is positive, and efficiencies are parseable "
            "as four plane efficiencies."
        )

    print(f"Input CSV: {args.input}")
    print(f"Simulation CSV for parameter completion: {args.simulation_input}")
    print(f"Requested gate quantiles: {QUANTILES_TO_USE}")
    print(f"Valid rows: {len(df)}")
    print(f"Output rate PNG: {args.output_rate}")
    print(f"Output LUT PNG: {args.output_lut}")
    print()

    make_plot(
        df=df,
        output_png_rate=args.output_rate,
        output_png_lut=args.output_lut,
        fit_degree=args.fit_degree,
        quantiles_to_use=QUANTILES_TO_USE,
        highlight_recent=args.highlight_recent,
    )


if __name__ == "__main__":
    main()
