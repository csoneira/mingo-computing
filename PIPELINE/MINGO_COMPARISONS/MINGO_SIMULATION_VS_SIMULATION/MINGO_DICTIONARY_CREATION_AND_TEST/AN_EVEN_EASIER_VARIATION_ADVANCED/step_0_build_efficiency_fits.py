#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from advanced_support import (
    CANONICAL_Z_COLUMNS,
    build_efficiency_fit_table,
    load_mingo00_training_dataframe,
    load_online_schedule,
    parse_station_id,
    parse_time_bound,
    select_schedule_rows_for_window,
    z_vector_to_id,
)
from common import DEFAULT_CONFIG_PATH, PLOTS_DIR, cfg_path, ensure_output_dirs, load_config, write_json

log = logging.getLogger("even_easier_advanced.step0")


def _configure_logging() -> None:
    logging.basicConfig(format="[%(levelname)s] STEP_0 - %(message)s", level=logging.INFO, force=True)


def _resolve_polynomial_degree(config: dict) -> int:
    step0_config = config.get("step0", {})
    if not isinstance(step0_config, dict):
        step0_config = {}
    degree = int(step0_config.get("fit_polynomial_degree", 1))
    if degree < 0:
        raise ValueError("step0.fit_polynomial_degree must be >= 0.")
    return degree


def _padded_limits(
    values: pd.Series,
    *,
    include: list[float] | None = None,
    fallback: tuple[float, float] = (0.0, 1.0),
) -> tuple[float, float]:
    numeric = pd.to_numeric(values, errors="coerce")
    finite = numeric[np.isfinite(numeric.to_numpy(dtype=float))]
    value_list = finite.tolist()
    if include:
        value_list.extend(float(item) for item in include)
    if not value_list:
        return fallback

    lower = float(min(value_list))
    upper = float(max(value_list))
    span = upper - lower
    pad = 0.05 if span <= 0.0 else max(0.03, 0.06 * span)
    return lower - pad, upper + pad


def _write_fit_overview_plot(
    training_df: pd.DataFrame,
    fit_table: pd.DataFrame,
    output_path: Path,
) -> Path | None:
    if training_df.empty or fit_table.empty:
        return None

    fig, axes = plt.subplots(2, 2, figsize=(13, 10), constrained_layout=True)
    color_map = plt.get_cmap("tab10")
    geometries = fit_table["z_config_id"].astype(str).tolist()

    for plane_idx, ax in enumerate(axes.flat, start=1):
        x_col = f"eff_empirical_{plane_idx}"
        y_col = f"eff_p{plane_idx}"
        x_limits = _padded_limits(training_df[x_col], include=[0.0, 1.0], fallback=(-0.05, 1.05))
        for geom_idx, z_config_id in enumerate(geometries):
            subset = training_df.loc[training_df["z_config_id"] == z_config_id].copy()
            if subset.empty:
                continue
            color = color_map(geom_idx % 10)
            ax.scatter(
                pd.to_numeric(subset[x_col], errors="coerce"),
                pd.to_numeric(subset[y_col], errors="coerce"),
                s=10,
                alpha=0.18,
                color=color,
                edgecolors="none",
                label=z_config_id if plane_idx == 1 else None,
            )
            fit_row = fit_table.loc[fit_table["z_config_id"] == z_config_id]
            if fit_row.empty:
                continue
            coeffs = fit_row.iloc[0][f"plane_{plane_idx}"]
            coeff_list = [] if pd.isna(coeffs) else [float(value) for value in json.loads(str(coeffs))]
            if not coeff_list:
                continue
            x_values = pd.to_numeric(subset[x_col], errors="coerce").dropna()
            if x_values.empty:
                continue
            x_line = np.linspace(float(x_values.min()), float(x_values.max()), 200)
            y_line = np.polyval(np.asarray(coeff_list, dtype=float), x_line)
            ax.plot(x_line, y_line, linewidth=2.0, color=color, alpha=0.95)

        ax.set_title(f"Plane {plane_idx}: observed vs simulated efficiency")
        ax.set_xlabel(f"Observed efficiency plane {plane_idx}")
        ax.set_ylabel(f"Simulated efficiency plane {plane_idx}")
        ax.grid(alpha=0.25)
        ax.set_xlim(*x_limits)
        ax.set_ylim(0.0, 1.02)
        ax.axline((0.0, 0.0), (1.0, 1.0), linestyle=":", linewidth=1.0, color="black", alpha=0.7)

    handles, labels = axes.flat[0].get_legend_handles_labels()
    if handles:
        axes.flat[0].legend(handles, labels, fontsize=8, loc="lower right")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return output_path


def _resolve_step5_window_geometry_ids(config: dict) -> tuple[set[str], dict[str, object]]:
    step5_config = config.get("step5", {})
    if not isinstance(step5_config, dict):
        step5_config = {}

    station_id = parse_station_id(step5_config.get("station", "MINGO01"))
    date_from = parse_time_bound(step5_config.get("date_from"), end_of_day=False)
    date_to = parse_time_bound(step5_config.get("date_to"), end_of_day=True)

    schedule_all, schedule_path = load_online_schedule(station_id, config=config)
    schedule_window = select_schedule_rows_for_window(
        schedule_all,
        date_from=date_from,
        date_to=date_to,
    )
    z_tuples = (
        sorted(set(schedule_window["z_tuple"].dropna().tolist()))
        if not schedule_window.empty
        else []
    )
    geometry_ids = {z_vector_to_id(z_tuple) for z_tuple in z_tuples}
    metadata = {
        "station_id": int(station_id),
        "date_from": None if date_from is None else str(date_from),
        "date_to": None if date_to is None else str(date_to),
        "online_run_dictionary_csv": str(schedule_path),
        "online_schedule_rows_total": int(len(schedule_all)),
        "online_schedule_rows_in_requested_window": int(len(schedule_window)),
        "online_schedule_z_tuples_in_requested_window": [list(z_tuple) for z_tuple in z_tuples],
        "z_config_ids_in_requested_window": sorted(geometry_ids),
    }
    return geometry_ids, metadata


def run(config_path: str | Path | None = None) -> Path:
    _configure_logging()
    ensure_output_dirs()
    config = load_config(config_path)

    training_output_path = cfg_path(config, "paths", "step0_training_csv")
    fit_table_path = cfg_path(config, "paths", "step0_fit_table_csv")
    meta_path = cfg_path(config, "paths", "step0_meta_json")

    degree_requested = _resolve_polynomial_degree(config)
    training_df, source_meta = load_mingo00_training_dataframe(config)
    geometry_ids, geometry_window_meta = _resolve_step5_window_geometry_ids(config)
    if not geometry_ids:
        raise ValueError(
            "Step 0 found no z positions in ONLINE_RUN_DICTIONARY for the requested step5 station/date window."
        )

    rows_before_geometry_filter = int(len(training_df))
    training_df = training_df.loc[training_df["z_config_id"].isin(geometry_ids)].copy()
    if training_df.empty:
        raise ValueError(
            "Step 0 has no MINGO00 training rows matching the step5 station/date-window geometries."
        )

    fit_table = build_efficiency_fit_table(training_df, degree_requested=degree_requested)
    if fit_table.empty:
        raise ValueError("Step 0 could not build any geometry fit.")

    training_output_path.parent.mkdir(parents=True, exist_ok=True)
    training_df.to_csv(training_output_path, index=False)
    fit_table.to_csv(fit_table_path, index=False)

    plot_path = _write_fit_overview_plot(
        training_df,
        fit_table,
        PLOTS_DIR / "step0_01_efficiency_fit_overview.png",
    )

    metadata = {
        **source_meta,
        "fit_polynomial_degree_requested": degree_requested,
        "fit_table_csv": str(fit_table_path),
        "training_csv": str(training_output_path),
        "geometry_window_filter": {
            **geometry_window_meta,
            "rows_before_geometry_filter": rows_before_geometry_filter,
            "rows_after_geometry_filter": int(len(training_df)),
            "rows_removed_by_geometry_filter": rows_before_geometry_filter - int(len(training_df)),
        },
        "geometry_count": int(len(fit_table)),
        "geometries": fit_table[["z_config_id", *CANONICAL_Z_COLUMNS]].to_dict(orient="records"),
        "plot_path": None if plot_path is None else str(plot_path),
    }
    write_json(meta_path, metadata)

    log.info("Wrote Step 0 training merge with %d rows to %s", len(training_df), training_output_path)
    log.info("Wrote geometry fit table with %d rows to %s", len(fit_table), fit_table_path)
    observed_limit_meta = source_meta.get("observed_efficiency_upper_limit_filter", {})
    if int(observed_limit_meta.get("affected_rows_total", 0)) > 0:
        log.info(
            "Dropped training points outside observed-efficiency bounds %s. Affected rows by plane: %s",
            observed_limit_meta.get("limits_by_plane"),
            observed_limit_meta.get("affected_rows_by_plane"),
        )
    if plot_path is not None:
        log.info("Wrote efficiency-fit overview plot to %s", plot_path)
    return fit_table_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build per-geometry per-plane efficiency polynomial fits from MINGO00.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to config JSON file.")
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()
