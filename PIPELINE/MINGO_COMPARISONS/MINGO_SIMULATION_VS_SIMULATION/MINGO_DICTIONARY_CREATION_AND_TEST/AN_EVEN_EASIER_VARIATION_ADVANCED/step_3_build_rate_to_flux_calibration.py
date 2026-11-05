#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import (
    CANONICAL_EFF_COLUMNS,
    DEFAULT_CONFIG_PATH,
    PLOTS_DIR,
    cfg_path,
    ensure_output_dirs,
    load_config,
    resolve_path,
    write_json,
)

log = logging.getLogger("even_easier_advanced.step3")

ALL_TRIGGER_GROUP = "__all_triggers__"
MISSING_GEOMETRY_GROUP = "__missing_geometry__"
MISSING_TRIGGER_GROUP = "__missing_trigger__"


def _configure_logging() -> None:
    logging.basicConfig(format="[%(levelname)s] STEP_3 - %(message)s", level=logging.INFO, force=True)


def _path_from_config_or_default(config: dict[str, Any], path_key: str, default_relative_path: str) -> Path:
    paths = config.get("paths", {})
    if isinstance(paths, dict) and path_key in paths:
        return cfg_path(config, "paths", path_key)
    return resolve_path(config, default_relative_path)


def _pick_first_existing_column(columns: list[str], candidates: list[str]) -> str:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    raise ValueError("Missing required column. Tried: " + ", ".join(candidates))


def _resolve_reference_columns(config: dict[str, Any], available_columns: list[str]) -> list[str]:
    step2_config = config.get("step2", {})
    if not isinstance(step2_config, dict):
        step2_config = {}

    raw_planes = step2_config.get("efficiency_reference_planes", [1, 2, 3, 4])
    if isinstance(raw_planes, (int, float)) and not isinstance(raw_planes, bool):
        raw_planes = [int(raw_planes)]
    if not isinstance(raw_planes, list):
        raise ValueError("step2.efficiency_reference_planes must be a list of plane indices.")

    columns: list[str] = []
    for value in raw_planes:
        plane = int(value)
        if plane < 1 or plane > 4:
            raise ValueError("step2.efficiency_reference_planes must contain values in [1, 4].")
        column = f"eff_empirical_{plane}"
        if column in available_columns:
            columns.append(column)

    if columns:
        return columns

    fallback = [column for column in CANONICAL_EFF_COLUMNS if column in available_columns]
    if not fallback:
        raise ValueError("No empirical-efficiency columns were found in the Step 0 training dataframe.")
    return fallback


def _resolve_reference_mode(config: dict[str, Any]) -> str:
    step2_config = config.get("step2", {})
    if not isinstance(step2_config, dict):
        step2_config = {}

    raw_mode = str(step2_config.get("efficiency_reference_mode", "product")).strip().lower()
    aliases = {
        "prod": "product",
        "product": "product",
        "mean": "mean_power4",
        "avg": "mean_power4",
        "average": "mean_power4",
        "mean_power4": "mean_power4",
    }
    mode = aliases.get(raw_mode, raw_mode)
    if mode not in {"product", "mean_power4"}:
        raise ValueError("step2.efficiency_reference_mode must be 'product' or 'mean_power4'.")
    return mode


def _compute_reference_and_corrected_rate(
    dataframe: pd.DataFrame,
    *,
    reference_columns: list[str],
    reference_mode: str,
    rate_column: str,
) -> pd.DataFrame:
    work = dataframe.copy()
    reference_frame = work[reference_columns].apply(pd.to_numeric, errors="coerce")
    rate_numeric = pd.to_numeric(work[rate_column], errors="coerce")

    if reference_mode == "product":
        work["eff_reference_step3"] = reference_frame.prod(axis=1, min_count=len(reference_columns))
        work["scale_factor_step3"] = 1.0 / work["eff_reference_step3"]
    else:
        work["eff_reference_step3"] = reference_frame.mean(axis=1)
        work["scale_factor_step3"] = 1.0 / (work["eff_reference_step3"] ** 4)

    work["corrected_rate_hz_step3"] = rate_numeric * pd.to_numeric(work["scale_factor_step3"], errors="coerce")
    work["eff_mean_step3"] = reference_frame.mean(axis=1)
    return work


def _fit_line(x_values: np.ndarray, y_values: np.ndarray) -> tuple[float, float, float | None, str]:
    if len(x_values) == 0:
        return np.nan, np.nan, None, "empty"
    if len(x_values) == 1 or np.unique(np.round(x_values, 12)).size < 2:
        return 0.0, float(np.nanmean(y_values)), None, "constant"

    slope, intercept = np.polyfit(x_values, y_values, deg=1)
    y_fit = slope * x_values + intercept
    ss_tot = float(np.sum((y_values - np.mean(y_values)) ** 2))
    ss_res = float(np.sum((y_values - y_fit) ** 2))
    r_squared = np.nan if ss_tot <= 0.0 else 1.0 - ss_res / ss_tot
    return float(slope), float(intercept), None if not np.isfinite(r_squared) else float(r_squared), "linear"


def _build_efficiency_case_fits(
    training_df: pd.DataFrame,
    *,
    efficiency_case_bin_width: float,
    min_points_per_case: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = training_df.copy()
    numeric_columns = ["flux_step3", "corrected_rate_hz_step3", "eff_mean_step3"]
    for column in numeric_columns:
        work[column] = pd.to_numeric(work[column], errors="coerce")
        work.loc[np.isinf(work[column]), column] = np.nan
    work = work.dropna(subset=["flux_step3", "corrected_rate_hz_step3", "eff_mean_step3"]).copy()
    work = work.loc[work["corrected_rate_hz_step3"] > 0.0].copy()
    work = work.loc[work["flux_step3"] > 0.0].copy()
    if work.empty:
        raise ValueError("No valid rows are available to build Step 3 efficiency-case fits.")

    width = float(efficiency_case_bin_width)
    work["eff_case_bin_step3"] = np.clip(
        np.round(work["eff_mean_step3"].to_numpy(dtype=float) / width) * width,
        0.0,
        1.0,
    )
    work["eff_case_bin_step3"] = np.round(work["eff_case_bin_step3"], 6)

    rows: list[dict[str, Any]] = []
    for eff_case_bin, subset in work.groupby("eff_case_bin_step3", sort=True, dropna=False):
        subset = subset.copy()
        n_points = int(len(subset))
        if n_points < int(min_points_per_case):
            continue

        x = subset["corrected_rate_hz_step3"].to_numpy(dtype=float)
        y = subset["flux_step3"].to_numpy(dtype=float)
        slope, intercept, r_squared, fit_method = _fit_line(x, y)
        rows.append(
            {
                "eff_case_bin_step3": float(eff_case_bin),
                "eff_mean_step3": float(np.nanmedian(subset["eff_mean_step3"])),
                "n_points": n_points,
                "slope_flux_per_hz": slope,
                "intercept_flux": intercept,
                "r_squared": r_squared,
                "fit_method": fit_method,
                "corrected_rate_min_hz": float(np.nanmin(x)),
                "corrected_rate_max_hz": float(np.nanmax(x)),
                "flux_min_cm2_min": float(np.nanmin(y)),
                "flux_max_cm2_min": float(np.nanmax(y)),
            }
        )

    fit_table = pd.DataFrame(rows)
    if fit_table.empty:
        raise ValueError("No efficiency case has enough support to fit a Step 3 rate-to-flux line.")
    fit_table = fit_table.sort_values("eff_case_bin_step3").reset_index(drop=True)
    return fit_table, work


def _select_display_case_bins(fit_table: pd.DataFrame, max_curves: int) -> list[float]:
    bins = fit_table["eff_case_bin_step3"].astype(float).tolist()
    if len(bins) <= int(max_curves):
        return bins
    positions = np.linspace(0, len(bins) - 1, num=int(max_curves), dtype=int)
    selected = [bins[index] for index in np.unique(positions)]
    return [float(value) for value in selected]


def _filter_fit_cases_by_efficiency_window(
    fit_table: pd.DataFrame,
    *,
    efficiency_case_min: float,
    efficiency_case_max: float,
) -> pd.DataFrame:
    filtered = fit_table.loc[
        (fit_table["eff_mean_step3"].astype(float) >= float(efficiency_case_min))
        & (fit_table["eff_mean_step3"].astype(float) <= float(efficiency_case_max))
    ].copy()
    if filtered.empty:
        raise ValueError(
            "No Step 3 efficiency cases remain after applying efficiency_case_min/efficiency_case_max."
        )
    return filtered.sort_values("eff_case_bin_step3").reset_index(drop=True)


def _asymptotic_reference_line(
    fit_table: pd.DataFrame,
    *,
    top_k_cases: int,
) -> dict[str, Any]:
    ranked = fit_table.sort_values("eff_mean_step3", ascending=False).reset_index(drop=True)
    subset = ranked.head(max(int(top_k_cases), 1)).copy()
    weights = subset["n_points"].astype(float).to_numpy(dtype=float)
    if float(weights.sum()) <= 0.0:
        weights = np.ones(len(subset), dtype=float)

    slope_ref = float(np.average(subset["slope_flux_per_hz"].astype(float), weights=weights))
    intercept_ref = float(np.average(subset["intercept_flux"].astype(float), weights=weights))
    return {
        "slope_flux_per_hz": slope_ref,
        "intercept_flux": intercept_ref,
        "n_cases_used": int(len(subset)),
        "eff_mean_range_used": [
            float(subset["eff_mean_step3"].min()),
            float(subset["eff_mean_step3"].max()),
        ],
        "case_bins_used": [float(value) for value in subset["eff_case_bin_step3"].tolist()],
    }


def _normalize_group_text(value: Any, *, missing_value: str) -> str:
    if value is None:
        return missing_value
    try:
        if pd.isna(value):
            return missing_value
    except TypeError:
        pass

    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return missing_value

    if text.startswith("[") and text.endswith("]"):
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return text
        return json.dumps(decoded)
    return text


def _resolve_trigger_group_column(dataframe: pd.DataFrame) -> str | None:
    candidates = [
        "trigger_combinations",
        "trigger_group",
        "selected_trigger_group",
        "trigger_type",
        "robust_efficiency_trigger_source",
    ]
    for candidate in candidates:
        if candidate not in dataframe.columns:
            continue
        normalized = dataframe[candidate].map(
            lambda value: _normalize_group_text(value, missing_value=MISSING_TRIGGER_GROUP)
        )
        unique_values = sorted({value for value in normalized.tolist() if value != MISSING_TRIGGER_GROUP})
        if len(unique_values) > 1:
            return candidate
    return None


def _prepare_group_columns(
    dataframe: pd.DataFrame,
    *,
    trigger_group_column: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    work = dataframe.copy()

    if "z_config_id" in work.columns:
        work["group_z_config_id"] = work["z_config_id"].map(
            lambda value: _normalize_group_text(value, missing_value=MISSING_GEOMETRY_GROUP)
        )
    else:
        work["group_z_config_id"] = MISSING_GEOMETRY_GROUP

    if "z_config_label" in work.columns:
        labels = work["z_config_label"].map(
            lambda value: _normalize_group_text(value, missing_value=MISSING_GEOMETRY_GROUP)
        )
        work["group_z_config_label"] = labels.where(labels != MISSING_GEOMETRY_GROUP, work["group_z_config_id"])
    else:
        work["group_z_config_label"] = work["group_z_config_id"]

    chosen_trigger_column = trigger_group_column
    if chosen_trigger_column is None:
        chosen_trigger_column = _resolve_trigger_group_column(work)

    if chosen_trigger_column is not None and chosen_trigger_column in work.columns:
        work["group_trigger_group"] = work[chosen_trigger_column].map(
            lambda value: _normalize_group_text(value, missing_value=MISSING_TRIGGER_GROUP)
        )
        unique_trigger_groups = sorted(
            {value for value in work["group_trigger_group"].tolist() if value != MISSING_TRIGGER_GROUP}
        )
        if len(unique_trigger_groups) <= 1:
            chosen_trigger_column = None
            work["group_trigger_group"] = ALL_TRIGGER_GROUP
            unique_trigger_groups = [ALL_TRIGGER_GROUP]
    else:
        chosen_trigger_column = None
        work["group_trigger_group"] = ALL_TRIGGER_GROUP
        unique_trigger_groups = [ALL_TRIGGER_GROUP]

    metadata = {
        "geometry_group_column": "z_config_id" if "z_config_id" in dataframe.columns else None,
        "trigger_group_column": chosen_trigger_column,
        "geometry_groups_present": sorted(work["group_z_config_id"].astype(str).unique().tolist()),
        "trigger_groups_present": unique_trigger_groups,
    }
    return work, metadata


def _build_grouped_calibration_units(
    prepared_training_df: pd.DataFrame,
    *,
    efficiency_case_bin_width: float,
    min_points_per_case: int,
    display_case_count: int,
    efficiency_case_min: float,
    efficiency_case_max: float,
    asymptote_top_k_cases: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    grouped_training_df, grouping_meta = _prepare_group_columns(prepared_training_df)
    grouped_units: list[dict[str, Any]] = []
    skipped_groups: list[dict[str, Any]] = []

    for (z_config_id, trigger_group), subset in grouped_training_df.groupby(
        ["group_z_config_id", "group_trigger_group"],
        sort=True,
        dropna=False,
    ):
        subset = subset.copy()
        z_config_label = str(subset["group_z_config_label"].iloc[0])

        try:
            fit_table_all, fit_input = _build_efficiency_case_fits(
                subset,
                efficiency_case_bin_width=efficiency_case_bin_width,
                min_points_per_case=min_points_per_case,
            )
            fit_table_window = _filter_fit_cases_by_efficiency_window(
                fit_table_all,
                efficiency_case_min=efficiency_case_min,
                efficiency_case_max=efficiency_case_max,
            )
            selected_case_bins = _select_display_case_bins(fit_table_window, display_case_count)
            fit_table_selected = fit_table_window.loc[
                fit_table_window["eff_case_bin_step3"].isin(selected_case_bins)
            ].copy()
            fit_table_selected = fit_table_selected.sort_values("eff_mean_step3").reset_index(drop=True)
            if fit_table_selected.empty:
                raise ValueError("No Step 3 efficiency cases were selected for plotting/calibration.")
            reference_line = _asymptotic_reference_line(
                fit_table_selected,
                top_k_cases=min(asymptote_top_k_cases, len(fit_table_selected)),
            )
        except ValueError as exc:
            skipped_groups.append(
                {
                    "group_z_config_id": str(z_config_id),
                    "group_z_config_label": z_config_label,
                    "group_trigger_group": str(trigger_group),
                    "n_training_rows": int(len(subset)),
                    "reason": str(exc),
                }
            )
            log.warning(
                "Skipping Step 3 calibration group z=%s trigger=%s: %s",
                z_config_id,
                trigger_group,
                exc,
            )
            continue

        grouped_units.append(
            {
                "group_z_config_id": str(z_config_id),
                "group_z_config_label": z_config_label,
                "group_trigger_group": str(trigger_group),
                "n_training_rows": int(len(subset)),
                "fit_input": fit_input,
                "fit_table_all": fit_table_all,
                "fit_table_window": fit_table_window,
                "fit_table_selected": fit_table_selected,
                "reference_line": reference_line,
            }
        )

    grouped_units = sorted(
        grouped_units,
        key=lambda unit: (str(unit["group_z_config_id"]), str(unit["group_trigger_group"])),
    )
    if not grouped_units:
        raise ValueError("No Step 3 grouped calibration unit could be built from the training dataframe.")

    return grouped_units, grouping_meta, skipped_groups


def _build_geometry_pooled_units(
    prepared_training_df: pd.DataFrame,
    *,
    efficiency_case_bin_width: float,
    min_points_per_case: int,
    display_case_count: int,
    efficiency_case_min: float,
    efficiency_case_max: float,
    asymptote_top_k_cases: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped_training_df, _ = _prepare_group_columns(prepared_training_df)
    pooled_units: list[dict[str, Any]] = []
    skipped_groups: list[dict[str, Any]] = []

    for z_config_id, subset in grouped_training_df.groupby("group_z_config_id", sort=True, dropna=False):
        subset = subset.copy()
        z_config_label = str(subset["group_z_config_label"].iloc[0])

        try:
            fit_table_all, fit_input = _build_efficiency_case_fits(
                subset,
                efficiency_case_bin_width=efficiency_case_bin_width,
                min_points_per_case=min_points_per_case,
            )
            fit_table_window = _filter_fit_cases_by_efficiency_window(
                fit_table_all,
                efficiency_case_min=efficiency_case_min,
                efficiency_case_max=efficiency_case_max,
            )
            selected_case_bins = _select_display_case_bins(fit_table_window, display_case_count)
            fit_table_selected = fit_table_window.loc[
                fit_table_window["eff_case_bin_step3"].isin(selected_case_bins)
            ].copy()
            fit_table_selected = fit_table_selected.sort_values("eff_mean_step3").reset_index(drop=True)
            if fit_table_selected.empty:
                raise ValueError("No Step 3 efficiency cases were selected for geometry-pooled calibration.")
            reference_line = _asymptotic_reference_line(
                fit_table_selected,
                top_k_cases=min(asymptote_top_k_cases, len(fit_table_selected)),
            )
        except ValueError as exc:
            skipped_groups.append(
                {
                    "group_z_config_id": str(z_config_id),
                    "group_z_config_label": z_config_label,
                    "n_training_rows": int(len(subset)),
                    "reason": str(exc),
                }
            )
            log.warning("Skipping Step 3 geometry-pooled calibration group z=%s: %s", z_config_id, exc)
            continue

        pooled_units.append(
            {
                "group_z_config_id": str(z_config_id),
                "group_z_config_label": z_config_label,
                "group_trigger_group": ALL_TRIGGER_GROUP,
                "n_training_rows": int(len(subset)),
                "fit_input": fit_input,
                "fit_table_all": fit_table_all,
                "fit_table_window": fit_table_window,
                "fit_table_selected": fit_table_selected,
                "reference_line": reference_line,
            }
        )

    pooled_units = sorted(pooled_units, key=lambda unit: str(unit["group_z_config_id"]))
    if not pooled_units:
        raise ValueError("No Step 3 geometry-pooled calibration unit could be built from the training dataframe.")
    return pooled_units, skipped_groups


def _build_lines_table(grouped_units: list[dict[str, Any]]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for unit in grouped_units:
        frame = unit["fit_table_selected"].copy()
        frame.insert(0, "group_trigger_group", str(unit["group_trigger_group"]))
        frame.insert(0, "group_z_config_label", str(unit["group_z_config_label"]))
        frame.insert(0, "group_z_config_id", str(unit["group_z_config_id"]))
        frames.append(frame)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True).sort_values(
        ["group_z_config_id", "group_trigger_group", "eff_case_bin_step3"]
    ).reset_index(drop=True)


def _reference_rows_from_units(units: list[dict[str, Any]], *, reference_scope: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for unit in units:
        reference_line = unit["reference_line"]
        rows.append(
            {
                "group_z_config_id": str(unit["group_z_config_id"]),
                "group_z_config_label": str(unit["group_z_config_label"]),
                "group_trigger_group": str(unit["group_trigger_group"]),
                "reference_scope": reference_scope,
                "reference_slope_flux_per_hz": float(reference_line["slope_flux_per_hz"]),
                "reference_intercept_flux": float(reference_line["intercept_flux"]),
                "reference_n_cases_used": int(reference_line["n_cases_used"]),
                "reference_eff_mean_min": float(reference_line["eff_mean_range_used"][0]),
                "reference_eff_mean_max": float(reference_line["eff_mean_range_used"][1]),
                "reference_case_bins_used": json.dumps(
                    [float(value) for value in reference_line["case_bins_used"]]
                ),
                "n_training_rows": int(unit["n_training_rows"]),
                "n_fit_rows_used": int(len(unit["fit_input"])),
                "n_efficiency_cases_fitted_total": int(len(unit["fit_table_all"])),
                "n_efficiency_cases_in_window": int(len(unit["fit_table_window"])),
                "n_efficiency_cases_selected": int(len(unit["fit_table_selected"])),
                "selected_case_bins_plotted": json.dumps(
                    [
                        float(value)
                        for value in unit["fit_table_selected"]["eff_case_bin_step3"].astype(float).tolist()
                    ]
                ),
            }
        )
    return rows


def _build_reference_tables(
    exact_units: list[dict[str, Any]],
    geometry_pooled_units: list[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    exact_rows: list[dict[str, Any]] = []
    exact_rows.extend(_reference_rows_from_units(exact_units, reference_scope="geometry_and_trigger"))

    exact_reference_table = (
        pd.DataFrame(exact_rows)
        .sort_values(["group_z_config_id", "group_trigger_group"])
        .reset_index(drop=True)
    )

    geometry_rows = _reference_rows_from_units(
        geometry_pooled_units,
        reference_scope="geometry_only_pooled",
    )

    geometry_reference_table = (
        pd.DataFrame(geometry_rows)
        .sort_values(["group_z_config_id", "group_trigger_group"])
        .reset_index(drop=True)
    )

    combined_reference_table = (
        pd.concat([exact_reference_table, geometry_reference_table], ignore_index=True, sort=False)
        .sort_values(["group_z_config_id", "reference_scope", "group_trigger_group"])
        .reset_index(drop=True)
    )
    return exact_reference_table, geometry_reference_table, combined_reference_table


def _plot_step3_calibration_figure(
    grouped_units: list[dict[str, Any]],
    *,
    output_path: Path,
    rate_column_label: str,
) -> None:
    if not grouped_units:
        raise ValueError("No grouped Step 3 units were provided for plotting.")

    n_units = len(grouped_units)
    figure_height = max(8.5, 4.8 * n_units)
    fig = plt.figure(figsize=(16, figure_height))
    grid = fig.add_gridspec(
        2 * n_units,
        2,
        width_ratios=[2.2, 1.1],
        height_ratios=[1.0] * (2 * n_units),
        wspace=0.26,
        hspace=0.50,
    )

    for unit_index, unit in enumerate(grouped_units):
        fit_input = unit["fit_input"]
        fit_table = unit["fit_table_selected"]
        reference_line = unit["reference_line"]
        z_config_id = str(unit["group_z_config_id"])
        trigger_group = str(unit["group_trigger_group"])

        trigger_text = trigger_group if len(trigger_group) <= 66 else (trigger_group[:63] + "...")
        row_start = 2 * unit_index
        ax_main = fig.add_subplot(grid[row_start : row_start + 2, 0])
        ax_slope = fig.add_subplot(grid[row_start, 1])
        ax_intercept = fig.add_subplot(grid[row_start + 1, 1])

        scatter = ax_main.scatter(
            fit_input["corrected_rate_hz_step3"],
            fit_input["flux_step3"],
            c=fit_input["eff_mean_step3"],
            cmap="viridis",
            s=14,
            alpha=0.16,
            edgecolors="none",
        )

        all_fits = fit_table.sort_values("eff_mean_step3").reset_index(drop=True)
        cmap = plt.get_cmap("viridis")
        for idx, row in all_fits.iterrows():
            color = cmap(idx / max(len(all_fits) - 1, 1))
            x_line = np.linspace(float(row["corrected_rate_min_hz"]), float(row["corrected_rate_max_hz"]), 160)
            y_line = float(row["slope_flux_per_hz"]) * x_line + float(row["intercept_flux"])
            ax_main.plot(
                x_line,
                y_line,
                color=color,
                linewidth=2.2,
                label=f"mean eff ~ {float(row['eff_mean_step3']):.2f}",
            )

        x_global = np.linspace(
            float(np.nanmin(fit_input["corrected_rate_hz_step3"])),
            float(np.nanmax(fit_input["corrected_rate_hz_step3"])),
            220,
        )
        y_ref = float(reference_line["slope_flux_per_hz"]) * x_global + float(reference_line["intercept_flux"])
        ax_main.plot(
            x_global,
            y_ref,
            color="black",
            linestyle="--",
            linewidth=2.4,
            label=(
                "asymptotic reference: "
                f"flux = {float(reference_line['slope_flux_per_hz']):.4f} * rate "
                f"{float(reference_line['intercept_flux']):+.4f}"
            ),
        )
        ax_main.set_xlabel(f"Corrected rate from {rate_column_label} [Hz]")
        ax_main.set_ylabel("Simulated flux [cm^-2 min^-1]")
        ax_main.set_title(
            "Step 3: corrected-rate to simulated-flux calibration by efficiency case"
            f"\n{z_config_id} | trigger={trigger_text}"
        )
        ax_main.grid(alpha=0.25)
        ax_main.legend(fontsize=8, ncol=1, loc="best")
        cbar = fig.colorbar(scatter, ax=ax_main)
        cbar.set_label("Mean empirical efficiency (selected planes)")

        ax_slope.plot(
            all_fits["eff_mean_step3"],
            all_fits["slope_flux_per_hz"],
            marker="o",
            linewidth=1.7,
            color="#1f77b4",
        )
        ax_slope.axhline(
            float(reference_line["slope_flux_per_hz"]),
            color="black",
            linestyle="--",
            linewidth=1.4,
            label="asymptotic slope",
        )
        ax_slope.set_xlabel("Mean efficiency")
        ax_slope.set_ylabel("Slope [flux/Hz]")
        ax_slope.set_title("Slope vs efficiency mean")
        ax_slope.grid(alpha=0.25)
        ax_slope.legend(fontsize=8)

        ax_intercept.plot(
            all_fits["eff_mean_step3"],
            all_fits["intercept_flux"],
            marker="o",
            linewidth=1.7,
            color="#d62728",
        )
        ax_intercept.axhline(
            float(reference_line["intercept_flux"]),
            color="black",
            linestyle="--",
            linewidth=1.4,
            label="asymptotic intercept",
        )
        ax_intercept.set_xlabel("Mean efficiency")
        ax_intercept.set_ylabel("Intercept [flux]")
        ax_intercept.set_title("Y-intercept vs efficiency mean")
        ax_intercept.grid(alpha=0.25)
        ax_intercept.legend(fontsize=8)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _resolve_time_axis(dataframe: pd.DataFrame) -> tuple[pd.Series, str]:
    if "file_timestamp_utc" in dataframe.columns:
        parsed = pd.to_datetime(dataframe["file_timestamp_utc"], errors="coerce", utc=True)
        if parsed.notna().any():
            return parsed, "file_timestamp_utc"
    if "execution_timestamp_utc" in dataframe.columns:
        parsed = pd.to_datetime(dataframe["execution_timestamp_utc"], errors="coerce", utc=True)
        if parsed.notna().any():
            return parsed, "execution_timestamp_utc"
    return pd.Series(range(len(dataframe)), dtype=float), "row_index"


def _plot_real_flux_time_series(
    dataframe: pd.DataFrame,
    output_path: Path,
    *,
    flux_column: str,
) -> None:
    plot_frame = dataframe.copy()
    x_values, x_label = _resolve_time_axis(plot_frame)
    if x_label != "row_index":
        plot_frame["__plot_time_sort_key"] = x_values
        plot_frame = (
            plot_frame.sort_values("__plot_time_sort_key", na_position="last")
            .drop(columns="__plot_time_sort_key")
            .reset_index(drop=True)
        )
        x_values, x_label = _resolve_time_axis(plot_frame)

    flux_values = pd.to_numeric(plot_frame[flux_column], errors="coerce")
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(
        x_values,
        flux_values,
        marker="o",
        markersize=3,
        linewidth=1.4,
        color="#1f77b4",
        label="Calibrated flux",
    )
    ax.set_title("Step 3 calibrated flux time series")
    ax.set_xlabel(x_label.replace("_", " "))
    ax.set_ylabel("Flux [cm^-2 min^-1]")
    ax.grid(alpha=0.25)
    ax.legend()
    if pd.api.types.is_datetime64_any_dtype(x_values):
        fig.autofmt_xdate()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _apply_reference_lines_to_real_data(
    real_df: pd.DataFrame,
    *,
    real_rate_column: str,
    exact_reference_table: pd.DataFrame,
    geometry_reference_table: pd.DataFrame,
    trigger_group_column: str | None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    work, grouping_meta = _prepare_group_columns(real_df, trigger_group_column=trigger_group_column)

    exact_lookup = exact_reference_table[
        [
            "group_z_config_id",
            "group_trigger_group",
            "reference_slope_flux_per_hz",
            "reference_intercept_flux",
        ]
    ].rename(
        columns={
            "reference_slope_flux_per_hz": "__exact_reference_slope_flux_per_hz",
            "reference_intercept_flux": "__exact_reference_intercept_flux",
        }
    )
    geometry_lookup = geometry_reference_table[
        [
            "group_z_config_id",
            "reference_slope_flux_per_hz",
            "reference_intercept_flux",
        ]
    ].rename(
        columns={
            "reference_slope_flux_per_hz": "__geometry_reference_slope_flux_per_hz",
            "reference_intercept_flux": "__geometry_reference_intercept_flux",
        }
    )

    work = work.merge(exact_lookup, how="left", on=["group_z_config_id", "group_trigger_group"])
    work = work.merge(geometry_lookup, how="left", on=["group_z_config_id"])

    exact_match = (
        pd.to_numeric(work["__exact_reference_slope_flux_per_hz"], errors="coerce").notna()
        & pd.to_numeric(work["__exact_reference_intercept_flux"], errors="coerce").notna()
    )
    geometry_match = (
        pd.to_numeric(work["__geometry_reference_slope_flux_per_hz"], errors="coerce").notna()
        & pd.to_numeric(work["__geometry_reference_intercept_flux"], errors="coerce").notna()
    )

    selected_slope = pd.to_numeric(work["__geometry_reference_slope_flux_per_hz"], errors="coerce")
    selected_intercept = pd.to_numeric(work["__geometry_reference_intercept_flux"], errors="coerce")
    selected_slope.loc[exact_match] = pd.to_numeric(
        work.loc[exact_match, "__exact_reference_slope_flux_per_hz"],
        errors="coerce",
    )
    selected_intercept.loc[exact_match] = pd.to_numeric(
        work.loc[exact_match, "__exact_reference_intercept_flux"],
        errors="coerce",
    )

    reference_match_type = pd.Series("unmatched", index=work.index, dtype="object")
    reference_match_type.loc[geometry_match] = "geometry_only_pooled"
    reference_match_type.loc[exact_match] = "geometry_and_trigger"

    reference_trigger_group = pd.Series(pd.NA, index=work.index, dtype="object")
    reference_trigger_group.loc[geometry_match] = ALL_TRIGGER_GROUP
    reference_trigger_group.loc[exact_match] = work.loc[exact_match, "group_trigger_group"]

    work["step3_reference_match_type"] = reference_match_type
    work["step3_reference_group_z_config_id"] = work["group_z_config_id"]
    work["step3_reference_group_trigger_group"] = reference_trigger_group
    work["step3_reference_slope_flux_per_hz"] = selected_slope
    work["step3_reference_intercept_flux"] = selected_intercept

    rate_numeric = pd.to_numeric(work[real_rate_column], errors="coerce")
    work["flux_from_step3_reference_cm2_min"] = selected_slope * rate_numeric + selected_intercept
    work.loc[selected_slope.isna() | selected_intercept.isna(), "flux_from_step3_reference_cm2_min"] = np.nan

    match_counts = (
        work["step3_reference_match_type"]
        .value_counts(dropna=False)
        .sort_index()
        .to_dict()
    )
    metadata = {
        "grouping": grouping_meta,
        "rows_total": int(len(work)),
        "rows_with_assigned_reference": int(work["flux_from_step3_reference_cm2_min"].notna().sum()),
        "reference_match_counts": {str(key): int(value) for key, value in match_counts.items()},
    }

    return (
        work.drop(
            columns=[
                "group_z_config_id",
                "group_z_config_label",
                "group_trigger_group",
                "__exact_reference_slope_flux_per_hz",
                "__exact_reference_intercept_flux",
                "__geometry_reference_slope_flux_per_hz",
                "__geometry_reference_intercept_flux",
            ],
            errors="ignore",
        ),
        metadata,
    )


def run(config_path: str | Path | None = None) -> Path:
    _configure_logging()
    ensure_output_dirs()
    config = load_config(config_path)

    step0_training_path = cfg_path(config, "paths", "step0_training_csv")
    step2_scaled_path = cfg_path(config, "paths", "step2_scaled_output_csv")
    lines_csv_path = _path_from_config_or_default(
        config,
        "step3_efficiency_case_lines_csv",
        "OUTPUTS/FILES/step3_efficiency_case_rate_to_flux_lines.csv",
    )
    reference_csv_path = _path_from_config_or_default(
        config,
        "step3_reference_line_csv",
        "OUTPUTS/FILES/step3_reference_rate_to_flux_line.csv",
    )
    real_flux_csv_path = _path_from_config_or_default(
        config,
        "step3_real_flux_output_csv",
        "OUTPUTS/FILES/step3_real_data_with_flux.csv",
    )
    meta_path = _path_from_config_or_default(config, "step3_meta_json", "OUTPUTS/FILES/step3_meta.json")
    plot_path = _path_from_config_or_default(
        config,
        "step3_calibration_plot",
        str(PLOTS_DIR / "step3_01_rate_to_flux_calibration.png"),
    )
    real_flux_plot_path = _path_from_config_or_default(
        config,
        "step3_real_flux_plot",
        str(PLOTS_DIR / "step3_02_real_flux_time_series.png"),
    )

    step3_config = config.get("step3", {})
    if not isinstance(step3_config, dict):
        step3_config = {}
    efficiency_case_bin_width = float(step3_config.get("efficiency_case_bin_width", 0.05))
    min_points_per_case = int(step3_config.get("min_points_per_efficiency_case", 20))
    display_case_count = int(step3_config.get("display_efficiency_cases", step3_config.get("display_max_efficiency_cases", 6)))
    efficiency_case_min = float(step3_config.get("efficiency_case_min", 0.0))
    efficiency_case_max = float(step3_config.get("efficiency_case_max", 1.0))
    asymptote_top_k_cases = int(step3_config.get("asymptote_top_k_cases", 5))

    if efficiency_case_bin_width <= 0.0:
        raise ValueError("step3.efficiency_case_bin_width must be > 0.")
    if min_points_per_case < 2:
        raise ValueError("step3.min_points_per_efficiency_case must be >= 2.")
    if display_case_count < 1:
        raise ValueError("step3.display_efficiency_cases must be >= 1.")
    if efficiency_case_min < 0.0 or efficiency_case_max > 1.0 or efficiency_case_min > efficiency_case_max:
        raise ValueError("step3 efficiency case window must satisfy 0 <= efficiency_case_min <= efficiency_case_max <= 1.")
    if asymptote_top_k_cases < 1:
        raise ValueError("step3.asymptote_top_k_cases must be >= 1.")

    training_df = pd.read_csv(step0_training_path, low_memory=False)
    flux_column = _pick_first_existing_column(
        training_df.columns.tolist(),
        ["sim_flux_cm2_min", "flux_cm2_min"],
    )
    rate_column = _pick_first_existing_column(
        training_df.columns.tolist(),
        ["selected_rate_hz", "rate_hz", "rate_1234_hz", "four_plane_rate_hz", "four_plane_robust_hz"],
    )
    reference_columns = _resolve_reference_columns(config, training_df.columns.tolist())
    reference_mode = _resolve_reference_mode(config)

    prepared_training_df = _compute_reference_and_corrected_rate(
        training_df,
        reference_columns=reference_columns,
        reference_mode=reference_mode,
        rate_column=rate_column,
    )
    prepared_training_df["flux_step3"] = pd.to_numeric(prepared_training_df[flux_column], errors="coerce")

    grouped_units, grouping_meta, skipped_groups = _build_grouped_calibration_units(
        prepared_training_df,
        efficiency_case_bin_width=efficiency_case_bin_width,
        min_points_per_case=min_points_per_case,
        display_case_count=display_case_count,
        efficiency_case_min=efficiency_case_min,
        efficiency_case_max=efficiency_case_max,
        asymptote_top_k_cases=asymptote_top_k_cases,
    )
    geometry_pooled_units, geometry_pooled_skipped_groups = _build_geometry_pooled_units(
        prepared_training_df,
        efficiency_case_bin_width=efficiency_case_bin_width,
        min_points_per_case=min_points_per_case,
        display_case_count=display_case_count,
        efficiency_case_min=efficiency_case_min,
        efficiency_case_max=efficiency_case_max,
        asymptote_top_k_cases=asymptote_top_k_cases,
    )
    lines_table = _build_lines_table(grouped_units)
    exact_reference_table, geometry_reference_table, combined_reference_table = _build_reference_tables(
        grouped_units,
        geometry_pooled_units,
    )

    _plot_step3_calibration_figure(
        grouped_units,
        output_path=plot_path,
        rate_column_label=rate_column,
    )

    lines_csv_path.parent.mkdir(parents=True, exist_ok=True)
    reference_csv_path.parent.mkdir(parents=True, exist_ok=True)
    lines_table.to_csv(lines_csv_path, index=False)
    combined_reference_table.to_csv(reference_csv_path, index=False)

    real_df = pd.read_csv(step2_scaled_path, low_memory=False)
    real_rate_column = (
        "corrected_rate_hz"
        if "corrected_rate_hz" in real_df.columns
        else _pick_first_existing_column(real_df.columns.tolist(), ["selected_rate_hz", "rate_hz"])
    )
    real_df, real_application_meta = _apply_reference_lines_to_real_data(
        real_df,
        real_rate_column=real_rate_column,
        exact_reference_table=exact_reference_table,
        geometry_reference_table=geometry_reference_table,
        trigger_group_column=grouping_meta["trigger_group_column"],
    )
    real_flux_csv_path.parent.mkdir(parents=True, exist_ok=True)
    real_df.to_csv(real_flux_csv_path, index=False)
    _plot_real_flux_time_series(
        real_df,
        real_flux_plot_path,
        flux_column="flux_from_step3_reference_cm2_min",
    )

    metadata = {
        "step0_training_csv": str(step0_training_path),
        "step2_scaled_output_csv": str(step2_scaled_path),
        "flux_input_column": flux_column,
        "rate_input_column": rate_column,
        "real_rate_input_column": real_rate_column,
        "reference_efficiency_columns": reference_columns,
        "reference_mode": reference_mode,
        "efficiency_case_bin_width": efficiency_case_bin_width,
        "efficiency_case_min": efficiency_case_min,
        "efficiency_case_max": efficiency_case_max,
        "min_points_per_efficiency_case": min_points_per_case,
        "display_efficiency_cases": display_case_count,
        "asymptote_top_k_cases": asymptote_top_k_cases,
        "grouping": grouping_meta,
        "n_training_rows": int(len(training_df)),
        "n_grouped_units_built": int(len(grouped_units)),
        "n_grouped_units_skipped": int(len(skipped_groups)),
        "n_geometry_pooled_units_built": int(len(geometry_pooled_units)),
        "n_geometry_pooled_units_skipped": int(len(geometry_pooled_skipped_groups)),
        "n_fit_rows_used_total": int(sum(len(unit["fit_input"]) for unit in grouped_units)),
        "n_efficiency_cases_fitted_total": int(sum(len(unit["fit_table_all"]) for unit in grouped_units)),
        "n_efficiency_cases_in_window_total": int(sum(len(unit["fit_table_window"]) for unit in grouped_units)),
        "n_efficiency_cases_selected_total": int(sum(len(unit["fit_table_selected"]) for unit in grouped_units)),
        "grouped_units": [
            {
                "group_z_config_id": str(unit["group_z_config_id"]),
                "group_z_config_label": str(unit["group_z_config_label"]),
                "group_trigger_group": str(unit["group_trigger_group"]),
                "n_training_rows": int(unit["n_training_rows"]),
                "n_fit_rows_used": int(len(unit["fit_input"])),
                "n_efficiency_cases_fitted_total": int(len(unit["fit_table_all"])),
                "n_efficiency_cases_in_window": int(len(unit["fit_table_window"])),
                "n_efficiency_cases_selected": int(len(unit["fit_table_selected"])),
                "selected_case_bins_plotted": [
                    float(value)
                    for value in unit["fit_table_selected"]["eff_case_bin_step3"].astype(float).tolist()
                ],
                "reference_line": unit["reference_line"],
            }
            for unit in grouped_units
        ],
        "skipped_groups": skipped_groups,
        "geometry_pooled_units": [
            {
                "group_z_config_id": str(unit["group_z_config_id"]),
                "group_z_config_label": str(unit["group_z_config_label"]),
                "n_training_rows": int(unit["n_training_rows"]),
                "n_fit_rows_used": int(len(unit["fit_input"])),
                "n_efficiency_cases_fitted_total": int(len(unit["fit_table_all"])),
                "n_efficiency_cases_in_window": int(len(unit["fit_table_window"])),
                "n_efficiency_cases_selected": int(len(unit["fit_table_selected"])),
                "selected_case_bins_plotted": [
                    float(value)
                    for value in unit["fit_table_selected"]["eff_case_bin_step3"].astype(float).tolist()
                ],
                "reference_line": unit["reference_line"],
            }
            for unit in geometry_pooled_units
        ],
        "geometry_pooled_skipped_groups": geometry_pooled_skipped_groups,
        "reference_rate_to_flux_lines": exact_reference_table.to_dict(orient="records"),
        "geometry_pooled_reference_lines": geometry_reference_table.to_dict(orient="records"),
        "real_reference_application": real_application_meta,
        "outputs": {
            "step3_efficiency_case_lines_csv": str(lines_csv_path),
            "step3_reference_line_csv": str(reference_csv_path),
            "step3_real_flux_output_csv": str(real_flux_csv_path),
            "step3_real_flux_plot": str(real_flux_plot_path),
            "step3_meta_json": str(meta_path),
            "step3_calibration_plot": str(plot_path),
        },
    }
    write_json(meta_path, metadata)

    log.info("Wrote Step 3 efficiency-case lines for %d grouped units to %s", len(grouped_units), lines_csv_path)
    for reference_row in exact_reference_table.to_dict(orient="records"):
        log.info(
            "Reference line [%s | trigger=%s]: flux = %.6f * rate + %.6f",
            reference_row["group_z_config_id"],
            reference_row["group_trigger_group"],
            float(reference_row["reference_slope_flux_per_hz"]),
            float(reference_row["reference_intercept_flux"]),
        )
    for reference_row in geometry_reference_table.to_dict(orient="records"):
        log.info(
            "Geometry-pooled reference line [%s]: flux = %.6f * rate + %.6f",
            reference_row["group_z_config_id"],
            float(reference_row["reference_slope_flux_per_hz"]),
            float(reference_row["reference_intercept_flux"]),
        )
    log.info("Wrote Step 3 calibration figure to %s", plot_path)
    log.info("Wrote Step 3 real-data flux output to %s", real_flux_csv_path)
    log.info("Wrote Step 3 calibrated flux time-series plot to %s", real_flux_plot_path)
    return real_flux_csv_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build Step 3 rate-to-flux calibration from MINGO00 training data and "
            "apply the asymptotic reference line to Step 2 corrected rates."
        )
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to config JSON file.")
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# MINGO00-only validation plot:
#   original simulated flux from SIMULATED_DATA vs STEP_3 estimated flux
#
# This block must be pasted at the end of:
#   step_3_build_rate_to_flux_calibration.py
#
# It is intentionally strict:
#   - runs only for MINGO00
#   - merges only by param_hash
#   - takes the simulated/original flux only from flux_cm2_min in:
#       /home/mingo/DATAFLOW_v3/PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/
#       step_final_simulation_params.csv
# ---------------------------------------------------------------------------

_STEP3_ORIGINAL_RUN = run


def _step3_is_mingo00_config(config: dict[str, Any]) -> bool:
    candidates: list[Any] = []

    if "station" in config:
        candidates.append(config.get("station"))

    for section_name in ("step1", "step2", "step3", "step5", "trigger_type_selection"):
        section = config.get(section_name, {})
        if isinstance(section, dict) and "station" in section:
            candidates.append(section.get("station"))

    for value in candidates:
        normalized = str(value).strip().lower().replace("_", "").replace("-", "")
        if normalized in {"0", "00", "mingo0", "mingo00"}:
            return True

    return False


def _step3_repo_root() -> Path:
    # __file__:
    #   /home/mingo/DATAFLOW_v3/
    #   PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/
    #   AN_EVEN_EASIER_VARIATION_ADVANCED/
    #   step_3_build_rate_to_flux_calibration.py
    #
    return Path(__file__).resolve().parents[5]
    #   /home/mingo/DATAFLOW_v3
    return Path(__file__).resolve().parents[5]


def _step3_simulation_params_csv_path(config: dict[str, Any]) -> Path:
    step0_config = config.get("step0", {})
    if isinstance(step0_config, dict):
        configured = step0_config.get("simulation_params_csv")
        if configured not in (None, "", "null", "None"):
            return resolve_path(config, configured)

    return (
        _step3_repo_root()
        / "PIPELINE"
        / "MINGO_DIGITAL_TWIN"
        / "SIMULATION_OUTPUTS"
        / "SIMULATED_DATA"
        / "step_final_simulation_params.csv"
    )


def _step3_real_flux_csv_path(config: dict[str, Any]) -> Path:
    return _path_from_config_or_default(
        config,
        "step3_real_flux_output_csv",
        "OUTPUTS/FILES/step3_real_data_with_flux.csv",
    )


def _step3_sim_vs_est_output_csv_path(config: dict[str, Any]) -> Path:
    return _path_from_config_or_default(
        config,
        "step3_simulated_vs_estimated_flux_csv",
        "OUTPUTS/FILES/step3_simulated_vs_estimated_flux_by_param_hash.csv",
    )


def _step3_sim_vs_est_plot_path(config: dict[str, Any]) -> Path:
    return _path_from_config_or_default(
        config,
        "step3_simulated_vs_estimated_flux_plot",
        str(PLOTS_DIR / "step3_03_simulated_vs_estimated_flux_scatter.png"),
    )


def _step3_norm_param_hash(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def _step3_pick_estimated_flux_column(real_df: pd.DataFrame) -> str:
    candidates = [
        "flux_from_step3_reference_cm2_min",
        "estimated_flux_step3_cm2_min",
        "flux_estimated_cm2_min",
        "estimated_flux_cm2_min",
    ]

    for column in candidates:
        if column in real_df.columns:
            return column

    raise KeyError(
        "Could not find the STEP_3 estimated-flux column in the STEP_3 output. "
        f"Tried: {candidates}. Available columns: {list(real_df.columns)}"
    )


def _step3_add_param_hash_from_training_if_needed(
    real_df: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    if "param_hash" in real_df.columns:
        return real_df

    if "filename_base" not in real_df.columns:
        raise KeyError(
            "STEP_3 output has no param_hash and no filename_base. "
            "Cannot recover param_hash for the SIMULATED_DATA merge."
        )

    training_csv = cfg_path(config, "paths", "step0_training_csv")
    if not training_csv.exists():
        raise FileNotFoundError(
            "STEP_3 output has no param_hash, and the STEP_0 training CSV used "
            f"to recover param_hash does not exist: {training_csv}"
        )

    training_df = pd.read_csv(training_csv, low_memory=False)

    required_training_columns = {"filename_base", "param_hash"}
    missing = required_training_columns.difference(training_df.columns)
    if missing:
        raise KeyError(
            f"Cannot recover param_hash from {training_csv}; missing columns: {sorted(missing)}"
        )

    bridge = (
        training_df[["filename_base", "param_hash"]]
        .dropna(subset=["filename_base", "param_hash"])
        .drop_duplicates(subset=["filename_base"], keep="first")
        .copy()
    )

    out = real_df.copy()
    out["__filename_base_key"] = out["filename_base"].astype("string").str.strip()
    bridge["__filename_base_key"] = bridge["filename_base"].astype("string").str.strip()

    out = out.merge(
        bridge[["__filename_base_key", "param_hash"]],
        on="__filename_base_key",
        how="left",
        validate="many_to_one",
    )

    out = out.drop(columns=["__filename_base_key"], errors="ignore")

    recovered = int(out["param_hash"].notna().sum())
    log.info(
        "Recovered param_hash for %d/%d STEP_3 rows using %s",
        recovered,
        len(out),
        training_csv,
    )

    return out

def _step3_build_simulated_vs_estimated_flux_table(
    config: dict[str, Any],
    real_flux_csv_path: Path,
    simulation_params_csv_path: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    real_df = pd.read_csv(real_flux_csv_path, low_memory=False)
    sim_df = pd.read_csv(simulation_params_csv_path, low_memory=False)

    real_df = _step3_add_param_hash_from_training_if_needed(real_df, config)

    if "param_hash" not in real_df.columns:
        raise KeyError("STEP_3 output still has no param_hash after recovery attempt.")

    if "param_hash" not in sim_df.columns:
        raise KeyError(
            f"SIMULATED_DATA CSV has no param_hash column: {simulation_params_csv_path}"
        )

    if "flux_cm2_min" not in sim_df.columns:
        raise KeyError(
            f"SIMULATED_DATA CSV has no flux_cm2_min column: {simulation_params_csv_path}"
        )

    estimated_flux_col = _step3_pick_estimated_flux_column(real_df)

    real_work = real_df.copy()
    real_work["__param_hash_key"] = _step3_norm_param_hash(real_work["param_hash"]).str.lower()

    sim_work = sim_df.copy()
    sim_work["__param_hash_key"] = _step3_norm_param_hash(sim_work["param_hash"]).str.lower()

    sim_lookup = (
        sim_work[["__param_hash_key", "param_hash", "flux_cm2_min"]]
        .dropna(subset=["__param_hash_key"])
        .drop_duplicates(subset=["__param_hash_key"], keep="first")
        .rename(
            columns={
                "param_hash": "simulated_param_hash",
                "flux_cm2_min": "simulated_flux_original_cm2_min",
            }
        )
        .copy()
    )

    merged = real_work.merge(
        sim_lookup,
        on="__param_hash_key",
        how="left",
        validate="many_to_one",
    )

    merged["simulated_flux_original_cm2_min"] = pd.to_numeric(
        merged["simulated_flux_original_cm2_min"],
        errors="coerce",
    )

    n_direct_matches = int(merged["simulated_flux_original_cm2_min"].notna().sum())

    # -----------------------------------------------------------------------
    # Fallback:
    # If the current SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv has zero
    # overlap with the recovered real-data param_hash values, use the STEP_0
    # training merge. That file is the local product of the param_hash merge
    # between MINGO00 metadata and SIMULATED_DATA and normally preserves
    # flux_cm2_min for the same hashes that STEP_3 can recover.
    # -----------------------------------------------------------------------
    n_training_fallback_matches = 0
    fallback_used = False

    if n_direct_matches == 0:
        training_csv = cfg_path(config, "paths", "step0_training_csv")

        if training_csv.exists():
            training_df = pd.read_csv(training_csv, low_memory=False)

            if "param_hash" in training_df.columns and "flux_cm2_min" in training_df.columns:
                training_work = training_df.copy()
                training_work["__param_hash_key"] = (
                    _step3_norm_param_hash(training_work["param_hash"]).str.lower()
                )

                training_lookup = (
                    training_work[["__param_hash_key", "param_hash", "flux_cm2_min"]]
                    .dropna(subset=["__param_hash_key"])
                    .drop_duplicates(subset=["__param_hash_key"], keep="first")
                    .rename(
                        columns={
                            "param_hash": "training_param_hash",
                            "flux_cm2_min": "simulated_flux_original_cm2_min_from_step0_training",
                        }
                    )
                    .copy()
                )

                merged = merged.merge(
                    training_lookup,
                    on="__param_hash_key",
                    how="left",
                    validate="many_to_one",
                )

                merged["simulated_flux_original_cm2_min_from_step0_training"] = pd.to_numeric(
                    merged["simulated_flux_original_cm2_min_from_step0_training"],
                    errors="coerce",
                )

                missing_direct = merged["simulated_flux_original_cm2_min"].isna()
                merged.loc[missing_direct, "simulated_flux_original_cm2_min"] = merged.loc[
                    missing_direct,
                    "simulated_flux_original_cm2_min_from_step0_training",
                ]

                n_training_fallback_matches = int(
                    merged["simulated_flux_original_cm2_min_from_step0_training"].notna().sum()
                )
                fallback_used = n_training_fallback_matches > 0

                log.warning(
                    "No param_hash overlap between STEP_3 rows and current SIMULATED_DATA CSV. "
                    "Used STEP_0 training merge fallback: %s; matched flux rows from training=%d.",
                    training_csv,
                    n_training_fallback_matches,
                )
            else:
                log.warning(
                    "Could not use STEP_0 training fallback because %s lacks param_hash or flux_cm2_min.",
                    training_csv,
                )
        else:
            log.warning(
                "Could not use STEP_0 training fallback because file does not exist: %s",
                training_csv,
            )

    merged = merged.drop(columns=["__param_hash_key"], errors="ignore")

    merged["estimated_flux_step3_cm2_min"] = pd.to_numeric(
        merged[estimated_flux_col],
        errors="coerce",
    )

    n_real = int(len(real_work))
    n_sim = int(len(sim_work))
    n_real_with_param_hash = int(real_work["param_hash"].notna().sum())
    n_unique_real_param_hash = int(real_work["__param_hash_key"].dropna().nunique())
    n_unique_sim_param_hash = int(sim_work["__param_hash_key"].dropna().nunique())
    n_matched_sim_flux = int(merged["simulated_flux_original_cm2_min"].notna().sum())
    n_valid_pairs = int(
        (
            merged["simulated_flux_original_cm2_min"].notna()
            & merged["estimated_flux_step3_cm2_min"].notna()
        ).sum()
    )

    meta = {
        "real_flux_csv": str(real_flux_csv_path),
        "simulation_params_csv": str(simulation_params_csv_path),
        "join_key": "param_hash",
        "simulated_flux_column": "flux_cm2_min",
        "estimated_flux_column": estimated_flux_col,
        "n_real_rows": n_real,
        "n_simulation_rows": n_sim,
        "n_real_rows_with_param_hash": n_real_with_param_hash,
        "n_unique_real_param_hash": n_unique_real_param_hash,
        "n_unique_simulation_param_hash": n_unique_sim_param_hash,
        "n_direct_matches_from_simulation_params_csv": n_direct_matches,
        "n_training_fallback_matches": n_training_fallback_matches,
        "fallback_used_step0_training_csv": fallback_used,
        "n_rows_with_matched_simulated_flux": n_matched_sim_flux,
        "n_valid_simulated_estimated_pairs": n_valid_pairs,
    }

    log.info(
        "MINGO00 simulated-vs-estimated merge by param_hash: "
        "real_rows=%d, real_with_param_hash=%d, unique_real_hash=%d, "
        "unique_sim_hash=%d, direct_sim_matches=%d, training_fallback_matches=%d, "
        "valid_pairs=%d",
        n_real,
        n_real_with_param_hash,
        n_unique_real_param_hash,
        n_unique_sim_param_hash,
        n_direct_matches,
        n_training_fallback_matches,
        n_valid_pairs,
    )

    if n_valid_pairs == 0:
        real_hashes = set(real_work["__param_hash_key"].dropna().astype(str))
        sim_hashes = set(sim_work["__param_hash_key"].dropna().astype(str))
        overlap = real_hashes.intersection(sim_hashes)

        log.error(
            "No valid simulated-vs-estimated flux pairs after param_hash merge. "
            "Direct overlap between STEP_3 recovered hashes and current SIMULATED_DATA hashes: %d. "
            "This usually means the current step_final_simulation_params.csv is not the same "
            "simulation-parameter table used to build step0_mingo00_training_merge.csv.",
            len(overlap),
        )

        sample_cols = [
            column
            for column in [
                "param_hash",
                "simulated_param_hash",
                "training_param_hash",
                "simulated_flux_original_cm2_min",
                "simulated_flux_original_cm2_min_from_step0_training",
                estimated_flux_col,
                "estimated_flux_step3_cm2_min",
                "filename_base",
                "file_timestamp_utc",
            ]
            if column in merged.columns
        ]

        log.error(
            "Diagnostic sample:\n%s",
            merged[sample_cols].head(30).to_string(index=False),
        )

    return merged, meta


def _step3_plot_simulated_vs_estimated_flux(
    merged: pd.DataFrame,
    output_plot_path: Path,
) -> dict[str, Any]:
    valid = merged[
        merged["simulated_flux_original_cm2_min"].notna()
        & merged["estimated_flux_step3_cm2_min"].notna()
    ].copy()

    if valid.empty:
        raise ValueError(
            "No rows contain both simulated_flux_original_cm2_min and "
            "estimated_flux_step3_cm2_min after merging by param_hash."
        )

    x = valid["simulated_flux_original_cm2_min"].to_numpy(dtype=float)
    y = valid["estimated_flux_step3_cm2_min"].to_numpy(dtype=float)

    residual = y - x

    rmse = float(np.sqrt(np.mean(residual**2)))
    mae = float(np.mean(np.abs(residual)))
    bias = float(np.mean(residual))

    if len(valid) >= 2 and np.std(x) > 0.0 and np.std(y) > 0.0:
        pearson_r = float(np.corrcoef(x, y)[0, 1])
        r2 = float(pearson_r**2)
    else:
        pearson_r = float("nan")
        r2 = float("nan")

    lower = float(np.nanmin([np.nanmin(x), np.nanmin(y)]))
    upper = float(np.nanmax([np.nanmax(x), np.nanmax(y)]))
    span = upper - lower
    pad = 0.05 * span if span > 0.0 else 1.0

    plot_min = lower - pad
    plot_max = upper + pad

    fig, ax = plt.subplots(figsize=(8.5, 7.2))

    ax.scatter(
        x,
        y,
        s=26,
        alpha=0.70,
        edgecolors="none",
    )

    ax.plot(
        [plot_min, plot_max],
        [plot_min, plot_max],
        linestyle="--",
        linewidth=1.5,
        label="1:1 line",
    )

    ax.set_xlim(plot_min, plot_max)
    ax.set_ylim(plot_min, plot_max)

    ax.set_xlabel("Original simulated flux, flux_cm2_min [cm$^{-2}$ min$^{-1}$]")
    ax.set_ylabel("STEP_3 estimated flux [cm$^{-2}$ min$^{-1}$]")
    ax.set_title(
        "MINGO00: original simulated flux vs STEP_3 estimated flux\n"
        f"N={len(valid)} | RMSE={rmse:.4g} | MAE={mae:.4g} | "
        f"bias={bias:.4g} | R$^2$={r2:.4g}"
    )

    ax.grid(alpha=0.25)
    ax.legend(loc="best")

    output_plot_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_plot_path, dpi=180)
    plt.close(fig)

    return {
        "plot_path": str(output_plot_path),
        "n_points": int(len(valid)),
        "rmse_cm2_min": rmse,
        "mae_cm2_min": mae,
        "bias_estimated_minus_simulated_cm2_min": bias,
        "pearson_r": pearson_r,
        "r2": r2,
    }


def _step3_write_mingo00_simulated_vs_estimated_flux_products(
    config_path: str | Path | None = None,
    real_flux_csv_path: Path | None = None,
) -> None:
    config = load_config(config_path)

    if not _step3_is_mingo00_config(config):
        log.info(
            "Skipping simulated-vs-estimated flux validation plot: "
            "configured station is not MINGO00."
        )
        return

    if real_flux_csv_path is None:
        real_flux_csv_path = _step3_real_flux_csv_path(config)

    simulation_params_csv_path = _step3_simulation_params_csv_path(config)
    output_csv_path = _step3_sim_vs_est_output_csv_path(config)
    output_plot_path = _step3_sim_vs_est_plot_path(config)

    if not real_flux_csv_path.exists():
        raise FileNotFoundError(f"Missing STEP_3 real-flux CSV: {real_flux_csv_path}")

    if not simulation_params_csv_path.exists():
        raise FileNotFoundError(
            f"Missing SIMULATED_DATA simulation-params CSV: {simulation_params_csv_path}"
        )

    merged, merge_meta = _step3_build_simulated_vs_estimated_flux_table(
        config,
        real_flux_csv_path,
        simulation_params_csv_path,
    )

    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_csv_path, index=False)

    plot_meta = _step3_plot_simulated_vs_estimated_flux(
        merged,
        output_plot_path,
    )

    meta_path = _path_from_config_or_default(
        config,
        "step3_meta_json",
        "OUTPUTS/FILES/step3_meta.json",
    )

    if meta_path.exists():
        try:
            meta_payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta_payload = {}
    else:
        meta_payload = {}

    meta_payload.setdefault("outputs", {})
    meta_payload.setdefault("plots", {})

    meta_payload["outputs"]["simulated_vs_estimated_flux_csv"] = str(output_csv_path)
    meta_payload["plots"]["simulated_vs_estimated_flux"] = str(output_plot_path)
    meta_payload["mingo00_simulated_vs_estimated_flux"] = {
        "enabled": True,
        "merge": merge_meta,
        "plot": plot_meta,
    }

    write_json(meta_path, meta_payload)

    log.info("Wrote MINGO00 simulated-vs-estimated flux CSV to %s", output_csv_path)
    log.info("Wrote MINGO00 simulated-vs-estimated flux plot to %s", output_plot_path)


def run(config_path: str | Path | None = None) -> Path:
    real_flux_csv_path = _STEP3_ORIGINAL_RUN(config_path)

    try:
        _step3_write_mingo00_simulated_vs_estimated_flux_products(
            config_path=config_path,
            real_flux_csv_path=Path(real_flux_csv_path),
        )
    except Exception:
        log.exception(
            "Failed to create MINGO00 simulated-vs-estimated flux validation products."
        )

    return real_flux_csv_path


def _step3_config_path_from_argv_for_post_hook() -> str | Path | None:
    import sys

    args = sys.argv[1:]

    for idx, item in enumerate(args):
        if item == "--config" and idx + 1 < len(args):
            return args[idx + 1]
        if item.startswith("--config="):
            return item.split("=", 1)[1]

    return DEFAULT_CONFIG_PATH


if __name__ == "__main__":
    # When this script is executed directly, the original main() block above has
    # already run before this pasted post-hook. This call creates only the
    # MINGO00 validation CSV and scatter plot.
    try:
        _step3_write_mingo00_simulated_vs_estimated_flux_products(
            config_path=_step3_config_path_from_argv_for_post_hook(),
            real_flux_csv_path=None,
        )
    except Exception:
        log.exception(
            "Failed to create direct-run MINGO00 simulated-vs-estimated flux validation products."
        )