#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import logging
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simple_common import (
    CANONICAL_EFF_COLUMNS,
    CANONICAL_Z_COLUMNS,
    DEFAULT_CONFIG_PATH,
    apply_observed_efficiency_limits,
    ensure_output_dirs,
    files_dir,
    ordered_plot_filename,
    parse_execution_timestamp,
    parse_filename_base_ts,
    parse_station_name,
    parse_time_bound,
    plots_dir,
    resolve_efficiency_spec,
    resolve_rate_specs,
    resolve_selected_z_vector,
    resolve_station_metadata_path,
    select_schedule_rows_for_window,
    load_config,
    load_online_schedule,
    online_z_tuple_for_timestamp,
    write_json,
)

log = logging.getLogger("definitive_method.step0")
SIMULATED_EFF_COLUMNS = [f"sim_eff_{idx}" for idx in range(1, 5)]
LUT_EFF_COLUMNS = [f"eff_lut_{idx}" for idx in range(1, 5)]


def _configure_logging() -> None:
    logging.basicConfig(format="[%(levelname)s] STEP_0 - %(message)s", level=logging.INFO, force=True)


def _parse_simulated_efficiencies(value: object) -> list[float]:
    if value in (None, "", "null", "None"):
        return [np.nan, np.nan, np.nan, np.nan]
    if isinstance(value, (list, tuple)):
        raw = list(value)
    else:
        try:
            raw = list(ast.literal_eval(str(value)))
        except (SyntaxError, ValueError):
            return [np.nan, np.nan, np.nan, np.nan]
    if len(raw) != 4:
        return [np.nan, np.nan, np.nan, np.nan]
    try:
        return [float(item) for item in raw]
    except (TypeError, ValueError):
        return [np.nan, np.nan, np.nan, np.nan]


def _read_header(path: Path) -> set[str]:
    return set(pd.read_csv(path, nrows=0).columns)


def _resolve_lut_efficiency_source(config: dict[str, Any]) -> str:
    source = str(config.get("lut_efficiency_source", "simulated")).strip().lower()
    if source == "metadata":
        source = "observed"
    if source not in {"simulated", "observed"}:
        raise ValueError("lut_efficiency_source must be 'simulated', 'observed', or 'metadata'.")
    return source


def _first_available_column(header: set[str], requested: str) -> str | None:
    candidates = [requested]
    if requested.startswith("rate_hz__"):
        candidates.append(requested.removeprefix("rate_hz__"))
    else:
        candidates.append(f"rate_hz__{requested}")
    return next((candidate for candidate in candidates if candidate in header), None)


def _aggregate_latest_per_key(dataframe: pd.DataFrame, key: str, timestamp_column: str) -> pd.DataFrame:
    work = dataframe.copy()
    if timestamp_column in work.columns:
        work["_exec_dt"] = parse_execution_timestamp(work[timestamp_column])
        work = work.sort_values([key, "_exec_dt"], na_position="last", kind="mergesort")
        work = work.groupby(key).tail(1).drop(columns=["_exec_dt"])
    return work.groupby(key, sort=False).tail(1).reset_index(drop=True)


def _load_metadata_slice(
    path: Path,
    *,
    join_key: str,
    required_columns: list[str],
    metadata_agg: str,
    timestamp_column: str,
) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Metadata file does not exist: {path}")
    header = _read_header(path)
    missing = [column for column in required_columns if column not in header]
    if missing:
        raise ValueError(f"Metadata file {path} is missing required columns: {', '.join(missing)}")
    usecols = list(dict.fromkeys(required_columns + ([timestamp_column] if timestamp_column in header else [])))
    dataframe = pd.read_csv(path, usecols=usecols, low_memory=False)
    if str(metadata_agg).strip().lower() == "latest":
        dataframe = _aggregate_latest_per_key(dataframe, join_key, timestamp_column)
    return dataframe


def _build_metadata_bundle(
    config: dict[str, Any],
    *,
    station_name: str,
    join_key: str,
    metadata_agg: str,
    timestamp_column: str,
    eff_spec: dict[str, Any],
    rate_specs: list[dict[str, Any]],
    require_efficiency_columns: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    path_requests: dict[Path, set[str]] = {}
    path_to_label: dict[Path, str] = {}

    eff_path = resolve_station_metadata_path(config, station_name, eff_spec["metadata_relative_path"])
    eff_header = _read_header(eff_path)
    available_eff_columns = [column for column in eff_spec["columns"] if column in eff_header]
    if require_efficiency_columns and not available_eff_columns:
        log.warning(
            "Configured empirical-efficiency columns are unavailable in %s; "
            "they will be derived from trigger-rate columns when possible.",
            eff_path,
        )
    path_requests.setdefault(eff_path, set()).update([join_key, *available_eff_columns])
    path_to_label[eff_path] = "efficiency"

    for rate_spec in rate_specs:
        rate_path = resolve_station_metadata_path(config, station_name, rate_spec["metadata_relative_path"])
        rate_header = _read_header(rate_path)
        source_rate_column = _first_available_column(rate_header, rate_spec["rate_column"])
        if source_rate_column is None:
            raise ValueError(
                f"Metadata file {rate_path} has neither {rate_spec['rate_column']!r} "
                f"nor its rate_hz__-prefixed alternative."
            )
        rate_spec["_resolved_source_rate_column"] = source_rate_column
        requested = [join_key, source_rate_column]
        path_requests.setdefault(rate_path, set()).update(requested)
        path_to_label.setdefault(rate_path, "rate")

    loaded: dict[Path, pd.DataFrame] = {}
    for path, columns in path_requests.items():
        loaded[path] = _load_metadata_slice(
            path,
            join_key=join_key,
            required_columns=sorted(columns),
            metadata_agg=metadata_agg,
            timestamp_column=timestamp_column,
        )

    eff_columns_to_keep = [join_key, *available_eff_columns]
    if timestamp_column in loaded[eff_path].columns:
        eff_columns_to_keep.append(timestamp_column)
    bundle = loaded[eff_path][eff_columns_to_keep].copy()
    for plane_idx, source_column in enumerate(eff_spec["columns"], start=1):
        if source_column in bundle.columns:
            bundle[CANONICAL_EFF_COLUMNS[plane_idx - 1]] = pd.to_numeric(bundle[source_column], errors="coerce")
        else:
            bundle[CANONICAL_EFF_COLUMNS[plane_idx - 1]] = np.nan
    bundle = bundle.drop(columns=available_eff_columns, errors="ignore")

    rate_sources_meta: list[dict[str, Any]] = []
    for rate_spec in rate_specs:
        rate_path = resolve_station_metadata_path(config, station_name, rate_spec["metadata_relative_path"])
        rate_df = loaded[rate_path].copy()
        rate_column_name = rate_spec["canonical_rate_column"]

        source_rate_column = rate_spec["_resolved_source_rate_column"]
        subset = rate_df[[join_key, source_rate_column]].copy()
        subset[rate_column_name] = pd.to_numeric(subset[source_rate_column], errors="coerce")
        subset = subset[[join_key, rate_column_name]]
        if timestamp_column not in bundle.columns and timestamp_column in rate_df.columns:
            subset[timestamp_column] = rate_df[timestamp_column]
        bundle = bundle.merge(subset, on=join_key, how="left")
        rate_sources_meta.append(
            {
                "name": rate_spec["name"],
                "slug": rate_spec["slug"],
                "metadata_file": str(rate_path),
                "rate_column": source_rate_column,
                "canonical_rate_column": rate_column_name,
            }
        )

    return bundle, {
        "efficiency_metadata_file": str(eff_path),
        "rate_sources": rate_sources_meta,
        "metadata_files_used": sorted(str(path) for path in loaded.keys()),
    }


def _fill_empirical_efficiencies(dataframe: pd.DataFrame, rate_specs: list[dict[str, Any]]) -> pd.DataFrame:
    result = dataframe.copy()
    for column in CANONICAL_EFF_COLUMNS:
        if column not in result.columns:
            result[column] = np.nan

    canonical_rate_by_unprefixed_name = {
        str(rate_spec["rate_column"]).removeprefix("rate_hz__"): rate_spec["canonical_rate_column"]
        for rate_spec in rate_specs
    }
    numerator_column = canonical_rate_by_unprefixed_name.get("tt_task5_post_1234_rate_hz")
    denominator_rate_names = [
        "tt_task5_post_234_rate_hz",
        "tt_task5_post_134_rate_hz",
        "tt_task5_post_124_rate_hz",
        "tt_task5_post_123_rate_hz",
    ]
    if numerator_column not in result.columns:
        return result

    numerator = pd.to_numeric(result[numerator_column], errors="coerce")
    for efficiency_column, missing_plane_rate_name in zip(CANONICAL_EFF_COLUMNS, denominator_rate_names):
        missing_plane_column = canonical_rate_by_unprefixed_name.get(missing_plane_rate_name)
        if missing_plane_column not in result.columns:
            continue
        missing_plane_rate = pd.to_numeric(result[missing_plane_column], errors="coerce")
        denominator = numerator + missing_plane_rate
        derived = numerator.div(denominator.where(denominator > 0))
        result[efficiency_column] = pd.to_numeric(result[efficiency_column], errors="coerce").fillna(derived)
    return result


def _resolve_observed_eff_limits(config: dict[str, Any]) -> tuple[dict[int, float], dict[int, float]]:
    filters = config.get("filters", {})
    if not isinstance(filters, dict):
        filters = {}
    lower = {}
    upper = {}
    for key, target in (("observed_efficiency_lower_limits", lower), ("observed_efficiency_upper_limits", upper)):
        raw = filters.get(key, {})
        if not isinstance(raw, dict):
            continue
        for plane_idx, value in raw.items():
            if value in (None, "", "null", "None"):
                continue
            target[int(str(plane_idx))] = float(value)
    return lower, upper


def _parameter_space_plot(training_df: pd.DataFrame, output_path: Path) -> str | None:
    plot_columns = ["sim_flux_cm2_min", *LUT_EFF_COLUMNS]
    plot_df = training_df.loc[:, plot_columns].copy()
    for column in plot_columns:
        plot_df[column] = pd.to_numeric(plot_df[column], errors="coerce")
    plot_df = plot_df.dropna(how="all", subset=plot_columns).reset_index(drop=True)
    if plot_df.empty:
        return None

    def limits(series: pd.Series) -> tuple[float, float] | None:
        numeric = pd.to_numeric(series, errors="coerce").dropna()
        if numeric.empty:
            return None
        low = float(numeric.min())
        high = float(numeric.max())
        if low == high:
            pad = max(abs(low) * 0.05, 0.05)
            return low - pad, high + pad
        pad = (high - low) * 0.04
        return low - pad, high + pad

    axis_limits = {column: limits(plot_df[column]) for column in plot_columns}
    n = len(plot_columns)
    fig, axes = plt.subplots(n, n, figsize=(2.45 * n + 1.2, 2.45 * n + 1.4), dpi=130)
    axes_arr = np.asarray(axes).reshape(n, n)
    color = "#4C78A8"

    def label(column: str) -> str:
        if column == "sim_flux_cm2_min":
            return "Flux [cm^-2 min^-1]"
        return column.replace("_", " ")

    for row_idx in range(n):
        for col_idx in range(n):
            ax = axes_arr[row_idx, col_idx]
            x_col = plot_columns[col_idx]
            y_col = plot_columns[row_idx]
            ax.grid(True, linestyle=":", linewidth=0.35, alpha=0.3)
            for spine in ax.spines.values():
                spine.set_linewidth(0.6)
            ax.set_box_aspect(1.0)
            if row_idx == col_idx:
                values = plot_df[y_col].dropna()
                if not values.empty:
                    ax.hist(values, bins=18, color=color, alpha=0.55, edgecolor="white", linewidth=0.45)
                ax.set_title(label(y_col), fontsize=9, pad=4)
                ax.set_xlim(axis_limits[y_col])
            elif row_idx > col_idx:
                subset = plot_df[[x_col, y_col]].dropna()
                if not subset.empty:
                    ax.scatter(subset[x_col], subset[y_col], s=16.0, alpha=0.68, color=color, edgecolors="none", rasterized=True)
                ax.set_xlim(axis_limits[x_col])
                ax.set_ylim(axis_limits[y_col])
            else:
                ax.axis("off")
            if row_idx < n - 1:
                ax.tick_params(axis="x", labelbottom=False)
            else:
                ax.set_xlabel(label(x_col), fontsize=8)
            if col_idx > 0:
                ax.tick_params(axis="y", labelleft=False)
            else:
                ax.set_ylabel(label(y_col), fontsize=8)
            ax.tick_params(axis="both", which="major", labelsize=7, width=0.75, length=2.6)

    fig.suptitle("Step 0 parameter-space overview", fontsize=11, y=0.98)
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.08, top=0.9, wspace=0.05, hspace=0.05)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=170)
    plt.close(fig)
    return str(output_path)


def _rate_output_columns(rate_specs: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for rate_spec in rate_specs:
        columns.append(rate_spec["canonical_rate_column"])
    return columns


def _build_training_dataframe(
    config: dict[str, Any],
    *,
    eff_spec: dict[str, Any],
    rate_specs: list[dict[str, Any]],
    selected_z_vector: tuple[float, float, float, float],
    lower_limits: dict[int, float],
    upper_limits: dict[int, float],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    lut_efficiency_source = _resolve_lut_efficiency_source(config)
    training = config.get("training", {})
    if not isinstance(training, dict):
        training = {}
    station_name = parse_station_name(training.get("station", "MINGO00"))
    sim_params_path = Path(training.get("simulation_params_csv", "")).expanduser()
    if not sim_params_path.is_absolute():
        sim_params_path = Path(config["_config_dir"]) / sim_params_path
    sim_params_path = sim_params_path.resolve()

    z_columns = [str(value) for value in training.get("z_columns", ["z_plane_1", "z_plane_2", "z_plane_3", "z_plane_4"])]
    flux_column = str(training.get("simulated_flux_column", "flux_cm2_min"))
    num_events_column = str(training.get("num_events_column", "selected_rows"))
    simulated_efficiency_column = str(training.get("simulated_efficiency_column", "efficiencies"))
    sim_columns = ["param_hash", *z_columns, flux_column, num_events_column, simulated_efficiency_column]
    sim_df = pd.read_csv(sim_params_path, usecols=sim_columns, low_memory=False)
    rows_before_merge = int(len(sim_df))

    metadata_df, metadata_meta = _build_metadata_bundle(
        config,
        station_name=station_name,
        join_key="param_hash",
        metadata_agg=str(training.get("metadata_agg", "latest")),
        timestamp_column=str(training.get("timestamp_column", "execution_timestamp")),
        eff_spec=eff_spec,
        rate_specs=rate_specs,
        require_efficiency_columns=lut_efficiency_source == "observed",
    )
    dataframe = sim_df.merge(metadata_df, on="param_hash", how="inner")
    rows_after_merge = int(len(dataframe))
    if dataframe.empty:
        raise ValueError("Training param_hash merge produced no rows.")

    # Training geometry is authoritative in the simulation parameter table.
    for idx, column in enumerate(z_columns, start=1):
        dataframe[CANONICAL_Z_COLUMNS[idx - 1]] = pd.to_numeric(dataframe[column], errors="coerce")
    simulated_eff_frame = dataframe[simulated_efficiency_column].map(_parse_simulated_efficiencies).apply(pd.Series)
    simulated_eff_frame.columns = SIMULATED_EFF_COLUMNS
    dataframe[SIMULATED_EFF_COLUMNS] = simulated_eff_frame.apply(pd.to_numeric, errors="coerce")
    dataframe["sim_flux_cm2_min"] = pd.to_numeric(dataframe[flux_column], errors="coerce")
    dataframe["num_events"] = pd.to_numeric(dataframe[num_events_column], errors="coerce")

    dataframe = _fill_empirical_efficiencies(dataframe, rate_specs)
    coordinate_source_columns = SIMULATED_EFF_COLUMNS if lut_efficiency_source == "simulated" else CANONICAL_EFF_COLUMNS
    dataframe[LUT_EFF_COLUMNS] = dataframe[coordinate_source_columns].apply(pd.to_numeric, errors="coerce")

    valid = np.isfinite(dataframe["sim_flux_cm2_min"])
    valid &= np.isfinite(dataframe["num_events"])
    valid &= np.isfinite(dataframe[SIMULATED_EFF_COLUMNS].to_numpy()).all(axis=1)
    valid &= np.isfinite(dataframe[LUT_EFF_COLUMNS].to_numpy()).all(axis=1)
    valid &= np.isfinite(dataframe[CANONICAL_Z_COLUMNS].to_numpy()).all(axis=1)
    finite_z_rows = int(np.count_nonzero(np.isfinite(dataframe[CANONICAL_Z_COLUMNS].to_numpy()).all(axis=1)))
    selected_z_match = np.ones(len(dataframe), dtype=bool)
    for column, value in zip(CANONICAL_Z_COLUMNS, selected_z_vector):
        selected_z_match &= np.isclose(pd.to_numeric(dataframe[column], errors="coerce"), float(value), equal_nan=False)
    selected_z_match_rows = int(np.count_nonzero(selected_z_match))
    valid &= selected_z_match

    rate_positive_masks = []
    for rate_spec in rate_specs:
        rate_column = rate_spec["canonical_rate_column"]
        rate_values = pd.to_numeric(dataframe[rate_column], errors="coerce")
        rate_positive_masks.append(np.isfinite(rate_values) & (rate_values > 0.0))
    if rate_positive_masks:
        valid &= np.column_stack(rate_positive_masks).any(axis=1)
    dataframe = dataframe.loc[valid].copy()

    min_events = training.get("min_events")
    if min_events not in (None, "", "null", "None"):
        dataframe = dataframe.loc[dataframe["num_events"] >= float(min_events)].copy()

    if lut_efficiency_source == "observed":
        dataframe, eff_limit_meta = apply_observed_efficiency_limits(
            dataframe,
            lower_limits=lower_limits,
            upper_limits=upper_limits,
        )
    else:
        eff_limit_meta = {"applied": False, "reason": "lut_efficiency_source=simulated"}
    if dataframe.empty:
        raise ValueError("No training rows remain after filtering.")

    keep_columns = [
        "param_hash",
        *CANONICAL_Z_COLUMNS,
        *SIMULATED_EFF_COLUMNS,
        *CANONICAL_EFF_COLUMNS,
        *LUT_EFF_COLUMNS,
        *_rate_output_columns(rate_specs),
        "sim_flux_cm2_min",
        "num_events",
    ]
    dataframe = dataframe[keep_columns].sort_values([*LUT_EFF_COLUMNS, "sim_flux_cm2_min"], kind="mergesort").reset_index(drop=True)
    log.info(
        "Training selection: before_merge=%d after_merge=%d finite_z=%d "
        "selected_z_match=%d written=%d",
        rows_before_merge,
        rows_after_merge,
        finite_z_rows,
        selected_z_match_rows,
        len(dataframe),
    )
    return dataframe, {
        "station": station_name,
        "simulation_params_csv": str(sim_params_path),
        "simulation_efficiency_column": simulated_efficiency_column,
        **metadata_meta,
        "selected_z_positions": list(selected_z_vector),
        "lut_efficiency_source": lut_efficiency_source,
        "lut_coordinate_columns": LUT_EFF_COLUMNS,
        "rows_before_merge": rows_before_merge,
        "rows_after_merge": rows_after_merge,
        "rows_with_finite_z_positions": finite_z_rows,
        "rows_matching_selected_z_vector": selected_z_match_rows,
        "row_count": int(len(dataframe)),
        "observed_efficiency_limit_filter": eff_limit_meta,
    }


def _build_real_dataframe(
    config: dict[str, Any],
    *,
    eff_spec: dict[str, Any],
    rate_specs: list[dict[str, Any]],
    selected_z_vector: tuple[float, float, float, float],
    lower_limits: dict[int, float],
    upper_limits: dict[int, float],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    real = config.get("real", {})
    if not isinstance(real, dict):
        real = {}
    station_name = parse_station_name(real.get("station", "MINGO01"))
    station_id = int(station_name.replace("MINGO", ""))
    date_from = parse_time_bound(real.get("date_from"), end_of_day=False)
    date_to = parse_time_bound(real.get("date_to"), end_of_day=True)
    timestamp_column = str(real.get("timestamp_column", "execution_timestamp"))

    metadata_df, metadata_meta = _build_metadata_bundle(
        config,
        station_name=station_name,
        join_key="filename_base",
        metadata_agg=str(real.get("metadata_agg", "latest")),
        timestamp_column=timestamp_column,
        eff_spec=eff_spec,
        rate_specs=rate_specs,
        require_efficiency_columns=True,
    )
    if metadata_df.empty:
        raise ValueError("Real-data metadata merge produced no rows.")

    metadata_df["file_timestamp_utc"] = metadata_df["filename_base"].map(parse_filename_base_ts)
    if timestamp_column in metadata_df.columns:
        metadata_df["execution_timestamp_utc"] = parse_execution_timestamp(metadata_df[timestamp_column])
    else:
        metadata_df["execution_timestamp_utc"] = pd.NaT

    schedule_all, schedule_path = load_online_schedule(station_id)
    schedule_window = select_schedule_rows_for_window(schedule_all, date_from=date_from, date_to=date_to)
    if date_from is not None:
        metadata_df = metadata_df.loc[metadata_df["file_timestamp_utc"] >= date_from].copy()
    if date_to is not None:
        metadata_df = metadata_df.loc[metadata_df["file_timestamp_utc"] <= date_to].copy()
    if metadata_df.empty:
        raise ValueError("No real-data rows remain after date filtering.")

    online_z = metadata_df["file_timestamp_utc"].map(lambda ts: online_z_tuple_for_timestamp(ts, schedule_all))
    for plane_idx in range(1, 5):
        metadata_df[f"online_z_plane_{plane_idx}"] = [
            np.nan if value is None else float(value[plane_idx - 1])
            for value in online_z
        ]
        metadata_df[CANONICAL_Z_COLUMNS[plane_idx - 1]] = pd.to_numeric(
            metadata_df[f"online_z_plane_{plane_idx}"],
            errors="coerce",
        )

    selected_match = pd.Series(True, index=metadata_df.index, dtype=bool)
    for column, value in zip(CANONICAL_Z_COLUMNS, selected_z_vector):
        selected_match &= np.isclose(
            pd.to_numeric(metadata_df[column], errors="coerce"),
            float(value),
            equal_nan=False,
        )
    metadata_df["selected_z_vector_match"] = selected_match
    metadata_df = _fill_empirical_efficiencies(metadata_df, rate_specs)

    valid = metadata_df["selected_z_vector_match"].fillna(False).to_numpy(dtype=bool)
    valid &= np.isfinite(metadata_df[CANONICAL_EFF_COLUMNS].to_numpy()).all(axis=1)
    rate_positive_masks = []
    for rate_spec in rate_specs:
        rate_column = rate_spec["canonical_rate_column"]
        rate_values = pd.to_numeric(metadata_df[rate_column], errors="coerce")
        rate_positive_masks.append(np.isfinite(rate_values) & (rate_values > 0.0))
    if rate_positive_masks:
        valid &= np.column_stack(rate_positive_masks).any(axis=1)
    metadata_df = metadata_df.loc[valid].copy()

    metadata_df, eff_limit_meta = apply_observed_efficiency_limits(
        metadata_df,
        lower_limits=lower_limits,
        upper_limits=upper_limits,
    )
    if metadata_df.empty:
        raise ValueError("No real-data rows remain after filtering.")

    keep_columns = [
        "filename_base",
        "file_timestamp_utc",
        "execution_timestamp_utc",
        *CANONICAL_Z_COLUMNS,
        *CANONICAL_EFF_COLUMNS,
        *_rate_output_columns(rate_specs),
        "selected_z_vector_match",
    ]
    metadata_df = metadata_df[keep_columns].sort_values("file_timestamp_utc", kind="mergesort").reset_index(drop=True)
    return metadata_df, {
        "station": station_name,
        "station_id": station_id,
        **metadata_meta,
        "online_run_dictionary_csv": str(schedule_path),
        "online_schedule_rows_total": int(len(schedule_all)),
        "online_schedule_rows_in_requested_window": int(len(schedule_window)),
        "selected_z_positions": list(selected_z_vector),
        "date_from": str(date_from) if date_from is not None else None,
        "date_to": str(date_to) if date_to is not None else None,
        "row_count": int(len(metadata_df)),
        "observed_efficiency_limit_filter": eff_limit_meta,
    }


def _write_step0_meta(config: dict[str, Any], updates: dict[str, Any]) -> Path:
    meta_path = files_dir(config) / "step0_selected_inputs_meta.json"
    payload: dict[str, Any] = {}
    if meta_path.exists():
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
    payload.update(updates)
    write_json(meta_path, payload)
    return meta_path


def run_training_selection(config_path: str | Path | None = None) -> Path:
    _configure_logging()
    config = load_config(config_path)
    ensure_output_dirs(config)
    eff_spec = resolve_efficiency_spec(config)
    rate_specs = resolve_rate_specs(config)
    lower_limits, upper_limits = _resolve_observed_eff_limits(config)
    selected_z_vector, z_meta = resolve_selected_z_vector(config)
    training_df, training_meta = _build_training_dataframe(
        config,
        eff_spec=eff_spec,
        rate_specs=rate_specs,
        selected_z_vector=selected_z_vector,
        lower_limits=lower_limits,
        upper_limits=upper_limits,
    )
    training_path = files_dir(config) / "step0_training_selected.csv"
    plot_path = plots_dir(config) / ordered_plot_filename(0, 1, "parameter_space")
    training_df.to_csv(training_path, index=False)
    plot_output = _parameter_space_plot(training_df, plot_path)
    public_rate_specs = [{key: value for key, value in rate_spec.items() if not str(key).startswith("_")} for rate_spec in rate_specs]
    _write_step0_meta(
        config,
        {
            "case_name": config.get("case_name"),
            "selected_z_positions": list(selected_z_vector),
            "z_selection": z_meta,
            "efficiency": eff_spec,
            "lut_efficiency_source": _resolve_lut_efficiency_source(config),
            "lut_coordinate_columns": LUT_EFF_COLUMNS,
            "rates": public_rate_specs,
            "training": training_meta,
            "parameter_space_plot": plot_output,
            "training_output_csv": str(training_path),
        },
    )
    log.info("Selected LUT efficiency source: %s", _resolve_lut_efficiency_source(config))
    log.info("Selected LUT coordinate columns: %s", ", ".join(LUT_EFF_COLUMNS))
    log.info("Wrote training selection to %s", training_path)
    return training_path


def run_real_selection(config_path: str | Path | None = None) -> Path:
    _configure_logging()
    config = load_config(config_path)
    ensure_output_dirs(config)
    eff_spec = resolve_efficiency_spec(config)
    rate_specs = resolve_rate_specs(config)
    lower_limits, upper_limits = _resolve_observed_eff_limits(config)
    selected_z_vector, z_meta = resolve_selected_z_vector(config)
    real_df, real_meta = _build_real_dataframe(
        config,
        eff_spec=eff_spec,
        rate_specs=rate_specs,
        selected_z_vector=selected_z_vector,
        lower_limits=lower_limits,
        upper_limits=upper_limits,
    )
    real_path = files_dir(config) / "step0_real_selected.csv"
    real_df.to_csv(real_path, index=False)
    _write_step0_meta(
        config,
        {
            "case_name": config.get("case_name"),
            "selected_z_positions": list(selected_z_vector),
            "z_selection": z_meta,
            "real": real_meta,
            "real_output_csv": str(real_path),
        },
    )
    log.info("Wrote real-data selection to %s", real_path)
    return real_path


def run(config_path: str | Path | None = None) -> tuple[Path, Path]:
    training_path = run_training_selection(config_path)
    real_path = run_real_selection(config_path)
    return training_path, real_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 0: load and select training and/or real-data inputs.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to config JSON file.")
    parser.add_argument("--branch", choices=("all", "training", "real"), default="all")
    args = parser.parse_args()
    if args.branch == "training":
        run_training_selection(args.config)
    elif args.branch == "real":
        run_real_selection(args.config)
    else:
        run(args.config)


if __name__ == "__main__":
    main()
