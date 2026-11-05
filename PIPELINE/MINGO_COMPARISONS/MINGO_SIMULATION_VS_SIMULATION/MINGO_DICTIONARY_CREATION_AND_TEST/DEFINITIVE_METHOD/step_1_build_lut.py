#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import warnings
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simple_common import (
    CANONICAL_EFF_COLUMNS,
    DEFAULT_CONFIG_PATH,
    assign_efficiency_bins,
    assign_flux_bins,
    build_rate_to_flux_lines,
    ensure_output_dirs,
    ensure_rate_case_output_dirs,
    files_dir,
    load_config,
    ordered_plot_filename,
    q25,
    q75,
    rate_case_files_dir,
    rate_case_plots_dir,
    resolve_rate_specs,
    write_json,
)

log = logging.getLogger("definitive_method.step1")
SIMULATED_EFF_COLUMNS = [f"sim_eff_{idx}" for idx in range(1, 5)]
LUT_EFF_COLUMNS = [f"eff_lut_{idx}" for idx in range(1, 5)]
EMPIRICAL_SUPPORT_COLUMNS = [f"support_eff_empirical_{idx}" for idx in range(1, 5)]


def _configure_logging() -> None:
    logging.basicConfig(format="[%(levelname)s] STEP_1 - %(message)s", level=logging.INFO, force=True)


def _distance_to_perfect(dataframe: pd.DataFrame, eff_columns: list[str]) -> pd.Series:
    values = np.sqrt(np.sum((1.0 - dataframe[eff_columns].astype(float).to_numpy()) ** 2, axis=1))
    return pd.Series(values, index=dataframe.index)


def _aggregate_flux_cells(dataframe: pd.DataFrame, flux_bin_count: int) -> tuple[pd.DataFrame, np.ndarray]:
    work = dataframe.copy()
    work["flux_bin_index"], flux_edges = assign_flux_bins(work["sim_flux_cm2_min"], flux_bin_count)
    work = work.dropna(subset=["flux_bin_index"]).copy()
    work["flux_bin_index"] = work["flux_bin_index"].astype(int)

    aggregated = (
        work.groupby([*LUT_EFF_COLUMNS, "flux_bin_index"], dropna=False)
        .agg(
            support_rows=("rate_hz", "size"),
            rate_median=("rate_hz", "median"),
            rate_q25=("rate_hz", q25),
            rate_q75=("rate_hz", q75),
            flux_median=("sim_flux_cm2_min", "median"),
            flux_q25=("sim_flux_cm2_min", q25),
            flux_q75=("sim_flux_cm2_min", q75),
            eff_empirical_1=(CANONICAL_EFF_COLUMNS[0], "median"),
            eff_empirical_2=(CANONICAL_EFF_COLUMNS[1], "median"),
            eff_empirical_3=(CANONICAL_EFF_COLUMNS[2], "median"),
            eff_empirical_4=(CANONICAL_EFF_COLUMNS[3], "median"),
        )
        .reset_index()
    )
    aggregated["flux_bin_lo"] = aggregated["flux_bin_index"].map(lambda idx: float(flux_edges[int(idx)]))
    aggregated["flux_bin_hi"] = aggregated["flux_bin_index"].map(lambda idx: float(flux_edges[int(idx) + 1]))
    aggregated["flux_bin_center"] = 0.5 * (aggregated["flux_bin_lo"] + aggregated["flux_bin_hi"])
    aggregated["distance_to_perfect"] = _distance_to_perfect(aggregated, LUT_EFF_COLUMNS)
    aggregated["eff_mean"] = aggregated[LUT_EFF_COLUMNS].mean(axis=1)
    aggregated["eff_span"] = aggregated[LUT_EFF_COLUMNS].max(axis=1) - aggregated[LUT_EFF_COLUMNS].min(axis=1)
    return aggregated.sort_values([*LUT_EFF_COLUMNS, "flux_bin_center"]).reset_index(drop=True), flux_edges


def _fit_reference_polynomial(
    x: np.ndarray,
    y: np.ndarray,
    *,
    requested_degree: int,
) -> tuple[np.ndarray, int, float]:
    if len(x) == 0:
        raise ValueError("Cannot fit a reference polynomial with zero points.")
    requested_degree = int(requested_degree)
    if requested_degree == 2:
        used_degree = 2 if len(x) >= 2 else 0
    else:
        used_degree = max(0, min(requested_degree, len(x) - 1))
    if used_degree == 0:
        coeffs = np.asarray([float(np.nanmedian(y))], dtype=float)
    elif used_degree == 2:
        # For degree-2 fits, intentionally use only a*x^2 + c, with no linear term.
        z = np.asarray(x, dtype=float) ** 2
        design = np.column_stack([z, np.ones(len(x), dtype=float)])
        try:
            ac_coeffs, *_ = np.linalg.lstsq(design, y, rcond=None)
            quad_coeff = float(ac_coeffs[0])
            intercept = float(ac_coeffs[1])
            coeffs = np.asarray([quad_coeff, 0.0, intercept], dtype=float)
        except (np.linalg.LinAlgError, ValueError):
            coeffs = np.asarray([float(np.nanmedian(y))], dtype=float)
            used_degree = 0
    else:
        numpy_exceptions = getattr(np, "exceptions", None)
        rank_warning = getattr(numpy_exceptions, "RankWarning", RuntimeWarning)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", rank_warning)
            coeffs = np.asarray(np.polyfit(x, y, used_degree), dtype=float)
    reference_rate = float(np.polyval(coeffs, 0.0))
    if not np.isfinite(reference_rate):
        reference_rate = 0.0
    reference_rate = max(reference_rate, 0.0)
    return coeffs, used_degree, reference_rate


def _build_reference_curve(
    aggregated_cells: pd.DataFrame,
    *,
    reference_curve_mode: str,
    top_k_closest_bins: int,
    asymptote_polynomial_degree: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    mode = str(reference_curve_mode).strip().lower()
    if mode not in {"median_top_k_closest", "distance_asymptote"}:
        raise ValueError("lut.reference_curve_mode must be 'median_top_k_closest' or 'distance_asymptote'.")

    reference_cells = (
        aggregated_cells.sort_values(
            ["flux_bin_index", "distance_to_perfect", "eff_span", "eff_mean"],
            ascending=[True, True, True, False],
        )
        .groupby("flux_bin_index", dropna=False)
        .head(int(top_k_closest_bins))
        .copy()
    )

    if mode == "median_top_k_closest":
        reference_curve = (
            reference_cells.groupby("flux_bin_index", dropna=False)
            .agg(
                flux_bin_center=("flux_bin_center", "median"),
                reference_rate_median=("rate_median", "median"),
                reference_rate_q25=("rate_median", q25),
                reference_rate_q75=("rate_median", q75),
                reference_cell_count=("rate_median", "size"),
                reference_distance_to_perfect=("distance_to_perfect", "median"),
            )
            .reset_index()
            .sort_values("flux_bin_index")
            .reset_index(drop=True)
        )
        return reference_cells, reference_curve

    reference_rows: list[dict[str, float]] = []
    for flux_bin_index, subset in reference_cells.groupby("flux_bin_index", dropna=False):
        subset = subset.copy().sort_values("distance_to_perfect")
        x = pd.to_numeric(subset["distance_to_perfect"], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(subset["rate_median"], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(x) & np.isfinite(y)
        x = x[valid]
        y = y[valid]
        if len(x) == 0:
            continue
        coefficients, used_degree, reference_rate = _fit_reference_polynomial(
            x,
            y,
            requested_degree=asymptote_polynomial_degree,
        )
        linear_slope = np.nan
        linear_intercept = np.nan
        if used_degree == 1 and len(coefficients) == 2:
            linear_slope = float(coefficients[0])
            linear_intercept = float(coefficients[1])
        elif used_degree == 0 and len(coefficients) == 1:
            linear_intercept = float(coefficients[0])
        reference_rows.append(
            {
                "flux_bin_index": int(flux_bin_index),
                "flux_bin_center": float(pd.to_numeric(subset["flux_bin_center"], errors="coerce").median()),
                "reference_rate_median": float(reference_rate),
                "reference_rate_q25": float(pd.to_numeric(subset["rate_median"], errors="coerce").quantile(0.25)),
                "reference_rate_q75": float(pd.to_numeric(subset["rate_median"], errors="coerce").quantile(0.75)),
                "reference_cell_count": int(len(subset)),
                "reference_distance_to_perfect": float(
                    pd.to_numeric(subset["distance_to_perfect"], errors="coerce").median()
                ),
                "reference_fit_degree_requested": int(asymptote_polynomial_degree),
                "reference_fit_degree_used": int(used_degree),
                "reference_fit_coefficients_json": json.dumps([float(value) for value in coefficients.tolist()]),
                "reference_fit_slope": linear_slope,
                "reference_fit_intercept": linear_intercept,
            }
        )

    reference_curve = pd.DataFrame(reference_rows).sort_values("flux_bin_index").reset_index(drop=True)
    return reference_cells, reference_curve


def _build_lut_table(
    aggregated_cells: pd.DataFrame,
    reference_curve: pd.DataFrame,
    *,
    min_flux_bins_per_lut_entry: int,
    efficiency_bin_width: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    merged = aggregated_cells.merge(
        reference_curve[["flux_bin_index", "reference_rate_median"]],
        on="flux_bin_index",
        how="inner",
    )
    if merged.empty:
        raise ValueError("Reference-curve merge produced no supported flux cells.")
    merged["cell_scale_factor"] = pd.to_numeric(merged["reference_rate_median"], errors="coerce") / pd.to_numeric(
        merged["rate_median"], errors="coerce"
    )
    empirical_grouped = assign_efficiency_bins(merged, LUT_EFF_COLUMNS, efficiency_bin_width, suffix="__lookup")
    lookup_group_columns = [f"{column}__lookup" for column in LUT_EFF_COLUMNS]
    lut = (
        empirical_grouped.groupby(lookup_group_columns, dropna=False)
        .agg(
            scale_factor=("cell_scale_factor", "median"),
            scale_factor_q25=("cell_scale_factor", q25),
            scale_factor_q75=("cell_scale_factor", q75),
            support_rows=("support_rows", "sum"),
            n_flux_bins=("flux_bin_index", "nunique"),
            distance_to_perfect=("distance_to_perfect", "median"),
            eff_mean=("eff_mean", "median"),
            support_eff_empirical_1=(CANONICAL_EFF_COLUMNS[0], "median"),
            support_eff_empirical_2=(CANONICAL_EFF_COLUMNS[1], "median"),
            support_eff_empirical_3=(CANONICAL_EFF_COLUMNS[2], "median"),
            support_eff_empirical_4=(CANONICAL_EFF_COLUMNS[3], "median"),
        )
        .reset_index()
        .rename(columns={f"{column}__lookup": column for column in LUT_EFF_COLUMNS})
        .sort_values(LUT_EFF_COLUMNS)
        .reset_index(drop=True)
    )
    lut = lut.loc[lut["n_flux_bins"] >= int(min_flux_bins_per_lut_entry)].copy()
    if lut.empty:
        raise ValueError("No LUT rows remain after min_flux_bins_per_lut_entry filtering.")
    return merged, lut


def _plot_reference_asymptote(
    reference_cells: pd.DataFrame,
    reference_curve: pd.DataFrame,
    output_path: Path,
    *,
    rate_column_name: str,
    reference_curve_mode: str,
) -> None:
    if reference_cells.empty or reference_curve.empty:
        return

    mode = str(reference_curve_mode).strip().lower()
    grouped = list(reference_cells.groupby("flux_bin_index", dropna=False, sort=True))
    column_count = min(3, len(grouped))
    row_count = int(np.ceil(len(grouped) / column_count))
    fig, axes = plt.subplots(row_count, column_count, figsize=(5.1 * column_count, 4.1 * row_count), constrained_layout=True)
    axes_array = np.atleast_1d(axes).reshape(row_count, column_count)

    for ax, (flux_bin_index, subset) in zip(axes_array.flat, grouped):
        subset = subset.copy().sort_values("distance_to_perfect")
        ref_match = reference_curve.loc[reference_curve["flux_bin_index"] == flux_bin_index]
        if ref_match.empty:
            ax.set_visible(False)
            continue
        ref_row = ref_match.iloc[0]
        x = pd.to_numeric(subset["distance_to_perfect"], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(subset["rate_median"], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(x) & np.isfinite(y)
        x = x[valid]
        y = y[valid]
        if len(x) == 0:
            ax.set_visible(False)
            continue
        order = np.argsort(x)
        x = x[order]
        y = y[order]
        x_max = max(float(np.nanmax(x)) * 1.08, 0.02)

        ax.scatter(x, y, s=38, color="#4C78A8", alpha=0.85, label="selected cells")
        ax.plot(x, y, color="#4C78A8", linewidth=1.1, alpha=0.7)
        ax.axvline(0.0, color="0.5", linewidth=0.8, linestyle=":", alpha=0.7)

        selected_reference = float(ref_row["reference_rate_median"])
        if mode == "distance_asymptote":
            coefficients_raw = ref_row.get("reference_fit_coefficients_json", None)
            coefficients: list[float] = []
            if isinstance(coefficients_raw, str) and coefficients_raw.strip():
                try:
                    coefficients = [float(value) for value in json.loads(coefficients_raw)]
                except (TypeError, ValueError, json.JSONDecodeError):
                    coefficients = []
            fit_degree_used = int(ref_row.get("reference_fit_degree_used", max(len(coefficients) - 1, 0)))
            if coefficients:
                x_fit = np.linspace(0.0, x_max, 200)
                y_fit = np.polyval(np.asarray(coefficients, dtype=float), x_fit)
                ax.plot(
                    x_fit,
                    y_fit,
                    color="#D62728",
                    linestyle="--",
                    linewidth=1.6,
                    label=f"poly deg {fit_degree_used} fit to x=0",
                )
            else:
                ax.axhline(selected_reference, color="#D62728", linestyle="--", linewidth=1.6, label="selected asymptote")
        else:
            ax.axhline(selected_reference, color="#D62728", linestyle="--", linewidth=1.6, label="selected reference")

        ax.scatter(
            [0.0],
            [selected_reference],
            s=135,
            color="#F2B701",
            edgecolors="black",
            linewidths=0.5,
            marker="*",
            zorder=4,
            label=f"chosen R(0) = {selected_reference:.4f} Hz",
        )
        ax.set_title(
            f"Flux bin {int(flux_bin_index)}\n"
            f"center ~ {float(ref_row['flux_bin_center']):.3f}, cells = {int(ref_row['reference_cell_count'])}"
        )
        ax.set_xlabel("Distance to perfect (selected LUT efficiency space)")
        ax.set_ylabel("Rate [Hz]")
        ax.set_xlim(-0.01, x_max)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8, loc="best")

    for ax in axes_array.flat[len(grouped):]:
        ax.set_visible(False)

    fig.suptitle(f"Reference-curve diagnostics\nrate column: {rate_column_name}", y=1.02)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _build_case_inputs(training_df: pd.DataFrame, rate_spec: dict[str, Any], efficiency_bin_width: float) -> pd.DataFrame:
    case_df = training_df.copy()
    case_df["rate_hz"] = pd.to_numeric(case_df[rate_spec["canonical_rate_column"]], errors="coerce")
    case_df = case_df.loc[np.isfinite(case_df["rate_hz"]) & (case_df["rate_hz"] > 0.0)].copy()
    if case_df.empty:
        raise ValueError(f"No positive-rate training rows remain for {rate_spec['name']}.")
    case_df = assign_efficiency_bins(case_df, LUT_EFF_COLUMNS, efficiency_bin_width, suffix="")
    return case_df


def run(config_path: str | Path | None = None) -> Path:
    _configure_logging()
    config = load_config(config_path)
    ensure_output_dirs(config)

    training_path = files_dir(config) / "step0_training_selected.csv"
    meta0_path = files_dir(config) / "step0_selected_inputs_meta.json"
    combined_lut_path = files_dir(config) / "step1_combined_scale_factor_lut.csv"
    meta_path = files_dir(config) / "step1_lut_meta.json"

    training_df = pd.read_csv(training_path, low_memory=False)
    efficiency_source = str(config.get("lut_efficiency_source", "simulated")).strip().lower()
    if efficiency_source == "metadata":
        efficiency_source = "observed"
    if efficiency_source not in {"simulated", "observed"}:
        raise ValueError("lut_efficiency_source must be 'simulated', 'observed', or 'metadata'.")
    source_columns = SIMULATED_EFF_COLUMNS if efficiency_source == "simulated" else CANONICAL_EFF_COLUMNS
    missing_source_columns = [column for column in source_columns if column not in training_df.columns]
    if missing_source_columns:
        raise ValueError(f"Training data is missing LUT efficiency source columns: {missing_source_columns}")
    training_df[LUT_EFF_COLUMNS] = training_df[source_columns].apply(pd.to_numeric, errors="coerce")
    log.info("Selected LUT efficiency source: %s", efficiency_source)
    log.info("Selected LUT coordinate columns: %s", ", ".join(LUT_EFF_COLUMNS))
    log.info("Rows entering LUT: %d", len(training_df))
    meta0 = {}
    if meta0_path.exists():
        meta0 = json.loads(meta0_path.read_text(encoding="utf-8"))

    rate_specs = resolve_rate_specs(config)
    lut_config = config.get("lut", {})
    if not isinstance(lut_config, dict):
        lut_config = {}
    efficiency_bin_width = float(lut_config.get("efficiency_bin_width", 0.025))
    flux_bin_count = int(lut_config.get("flux_bin_count", 5))
    reference_curve_mode = str(lut_config.get("reference_curve_mode", "distance_asymptote"))
    reference_asymptote_polynomial_degree = int(lut_config.get("reference_asymptote_polynomial_degree", 1))
    reference_top_k_per_flux_bin = int(lut_config.get("reference_top_k_per_flux_bin", 5))
    min_flux_bins_per_lut_entry = int(lut_config.get("min_flux_bins_per_lut_entry", 1))

    combined_lut: pd.DataFrame | None = None
    case_meta_rows: list[dict[str, Any]] = []

    for rate_spec in rate_specs:
        ensure_rate_case_output_dirs(config, rate_spec)
        case_files_dir = rate_case_files_dir(config, rate_spec)
        case_plots_dir = rate_case_plots_dir(config, rate_spec)
        plot_path = case_plots_dir / ordered_plot_filename(1, 1, "reference_asymptote")

        case_training = _build_case_inputs(training_df, rate_spec, efficiency_bin_width)
        aggregated_cells, flux_edges = _aggregate_flux_cells(case_training, flux_bin_count)
        reference_cells, reference_curve = _build_reference_curve(
            aggregated_cells,
            reference_curve_mode=reference_curve_mode,
            top_k_closest_bins=reference_top_k_per_flux_bin,
            asymptote_polynomial_degree=reference_asymptote_polynomial_degree,
        )
        if reference_curve.empty:
            raise ValueError(f"Could not build a reference curve for {rate_spec['name']}.")
        flux_cells, lut_df = _build_lut_table(
            aggregated_cells,
            reference_curve,
            min_flux_bins_per_lut_entry=min_flux_bins_per_lut_entry,
            efficiency_bin_width=efficiency_bin_width,
        )
        line_table = build_rate_to_flux_lines(reference_curve)

        flux_cells_path = case_files_dir / "step1_flux_cells.csv"
        reference_curve_path = case_files_dir / "step1_reference_curve.csv"
        detailed_lut_path = case_files_dir / "step1_scale_factor_lut_detailed.csv"
        simple_lut_path = case_files_dir / "step1_scale_factor_lut.csv"
        line_table_path = case_files_dir / "step1_rate_to_flux_lines.csv"
        case_meta_path = case_files_dir / "step1_lut_meta.json"

        flux_cells.to_csv(flux_cells_path, index=False)
        reference_curve.to_csv(reference_curve_path, index=False)
        lut_df.to_csv(detailed_lut_path, index=False)
        line_table.to_csv(line_table_path, index=False)
        simple_case_lut = lut_df[LUT_EFF_COLUMNS + ["scale_factor"]].rename(
            columns={"scale_factor": rate_spec["scale_factor_column"]}
        )
        simple_case_lut.to_csv(simple_lut_path, index=False)

        _plot_reference_asymptote(
            reference_cells,
            reference_curve,
            plot_path,
            rate_column_name=rate_spec["rate_column"],
            reference_curve_mode=reference_curve_mode,
        )

        case_meta = {
            "rate_name": rate_spec["name"],
            "rate_slug": rate_spec["slug"],
            "rate_column": rate_spec["rate_column"],
                "canonical_rate_column": rate_spec["canonical_rate_column"],
                "training_rows_used": int(len(case_training)),
                "reference_efficiency_space": efficiency_source,
                "lookup_efficiency_space": efficiency_source,
                "lut_coordinate_columns": LUT_EFF_COLUMNS,
                "aggregated_flux_cells_rows": int(len(aggregated_cells)),
            "reference_cells_rows": int(len(reference_cells)),
            "reference_curve_rows": int(len(reference_curve)),
            "lut_rows": int(len(lut_df)),
            "flux_bin_edges": flux_edges.tolist(),
            "efficiency_bin_width": efficiency_bin_width,
            "flux_bin_count": flux_bin_count,
            "reference_curve_mode": reference_curve_mode,
            "reference_asymptote_polynomial_degree": reference_asymptote_polynomial_degree,
            "reference_top_k_per_flux_bin": reference_top_k_per_flux_bin,
            "min_flux_bins_per_lut_entry": min_flux_bins_per_lut_entry,
            "plot_file": str(plot_path),
            "flux_cells_file": str(flux_cells_path),
            "reference_curve_file": str(reference_curve_path),
            "detailed_lut_file": str(detailed_lut_path),
            "simple_lut_file": str(simple_lut_path),
            "rate_to_flux_lines_file": str(line_table_path),
        }
        write_json(case_meta_path, case_meta)
        case_meta_rows.append(case_meta)

        if combined_lut is None:
            combined_lut = simple_case_lut.copy()
        else:
            combined_lut = combined_lut.merge(simple_case_lut, on=LUT_EFF_COLUMNS, how="outer")

    if combined_lut is None or combined_lut.empty:
        raise ValueError("No LUT rows were produced for any rate case.")

    combined_lut = combined_lut.sort_values(LUT_EFF_COLUMNS, kind="mergesort").reset_index(drop=True)
    four_plane_source = "scale_factor__tt_task5_post_1234_rate_hz"
    if four_plane_source in combined_lut.columns and "scale_factor__four_plane_robust_hz" not in combined_lut.columns:
        combined_lut["scale_factor__four_plane_robust_hz"] = combined_lut[four_plane_source]
    combined_lut.to_csv(combined_lut_path, index=False)

    write_json(
        meta_path,
        {
            "case_name": config.get("case_name"),
            "source_training_file": str(training_path),
            "combined_lut_file": str(combined_lut_path),
            "combined_lut_row_count": int(len(combined_lut)),
            "lut_efficiency_source": efficiency_source,
            "lut_coordinate_columns": LUT_EFF_COLUMNS,
            "combined_lut_rate_columns": [rate_spec["scale_factor_column"] for rate_spec in rate_specs],
            "rate_cases": case_meta_rows,
            "step0_meta": meta0,
        },
    )

    log.info("Wrote combined multi-rate LUT to %s", combined_lut_path)
    log.info("Rows written to combined LUT: %d", len(combined_lut))
    return combined_lut_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 1: build one LUT scale-factor column per selected rate.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to config JSON file.")
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()
