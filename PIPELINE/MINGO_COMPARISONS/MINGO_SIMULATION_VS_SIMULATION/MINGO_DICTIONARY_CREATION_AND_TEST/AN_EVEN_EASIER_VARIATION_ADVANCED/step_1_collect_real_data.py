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

from advanced_support import (
    CANONICAL_Z_COLUMNS,
    add_geometry_columns,
    aggregate_latest_by_key,
    apply_observed_efficiency_upper_limits,
    apply_fit_table,
    load_fit_table,
    load_metadata_csv_with_repair,
    load_online_schedule,
    online_z_tuple_for_timestamp,
    parse_execution_timestamp,
    parse_filename_base_ts,
    parse_station_id,
    parse_time_bound,
    resolve_observed_efficiency_lower_limits,
    resolve_observed_efficiency_upper_limits,
    select_schedule_rows_for_window,
)
from common import (
    CANONICAL_EFF_COLUMNS,
    DEFAULT_CONFIG_PATH,
    PLOTS_DIR,
    REPO_ROOT,
    cfg_path,
    derive_trigger_rate_features,
    ensure_output_dirs,
    get_trigger_type_selection,
    load_config,
    write_json,
)

ROOT_DIR = Path(__file__).resolve().parent
STATIONS_ROOT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"

log = logging.getLogger("even_easier_advanced.step1")


def _configure_logging() -> None:
    logging.basicConfig(format="[%(levelname)s] STEP_1 - %(message)s", level=logging.INFO, force=True)


def _task_metadata_dir(station_id: int, task_id: int) -> Path:
    station = f"MINGO{station_id:02d}"
    return STATIONS_ROOT / station / "STAGE_1" / "EVENT_DATA" / "STEP_1" / f"TASK_{task_id}" / "METADATA"


def _task_metadata_path(station_id: int, task_id: int, source_name: str) -> Path:
    return _task_metadata_dir(station_id, task_id) / f"task_{task_id}_metadata_{source_name}.csv"


def _load_task_metadata_source_csv(
    *,
    station_id: int,
    task_id: int,
    source_name: str,
    metadata_agg: str,
    timestamp_column: str,
) -> pd.DataFrame:
    source_path = _task_metadata_path(station_id, task_id, source_name)
    if not source_path.exists():
        raise FileNotFoundError(f"Missing required {source_name} metadata for task {task_id}: {source_path}")
    dataframe = load_metadata_csv_with_repair(source_path, low_memory=False)
    if "filename_base" not in dataframe.columns:
        raise KeyError(f"Task {task_id} {source_name} metadata has no 'filename_base' column: {source_path}")
    if str(metadata_agg).strip().lower() == "latest":
        dataframe = aggregate_latest_by_key(dataframe, "filename_base", timestamp_column)
    return dataframe


def _merge_sources(
    base_source: tuple[str, pd.DataFrame],
    extra_sources: list[tuple[str, pd.DataFrame]],
    *,
    how: str,
) -> pd.DataFrame:
    merged = base_source[1].copy()
    for source_name, source_df in extra_sources:
        overlap = sorted(set(merged.columns).intersection(set(source_df.columns)) - {"filename_base"})
        renamed = source_df.rename(columns={column: f"{source_name}__{column}" for column in overlap})
        merged = merged.merge(renamed, on="filename_base", how=how)
    return merged


def _normalize_task_ids(raw: object, fallback: list[int]) -> list[int]:
    if raw in (None, "", "null", "None"):
        return list(fallback)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return [int(raw)]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return list(fallback)
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = [piece.strip() for piece in text.split(",") if piece.strip()]
        raw = decoded
    if isinstance(raw, (list, tuple)):
        parsed = []
        for value in raw:
            try:
                parsed.append(int(value))
            except (TypeError, ValueError):
                continue
        return sorted(set(parsed)) or list(fallback)
    return list(fallback)


def _resolve_corrected_eff(config: dict[str, Any]) -> bool:
    def parse_flag(value: object) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    if "corrected_eff" in config:
        return parse_flag(config["corrected_eff"])
    step1_config = config.get("step1", {})
    if isinstance(step1_config, dict) and "corrected_eff" in step1_config:
        return parse_flag(step1_config["corrected_eff"])
    return False


def _resolve_fit_clip_output(config: dict[str, Any]) -> bool:
    step0_config = config.get("step0", {})
    if not isinstance(step0_config, dict):
        step0_config = {}
    raw = step0_config.get("fit_clip_output", True)
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return bool(raw)


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


def _padded_limits(
    series_list: list[pd.Series],
    *,
    include: list[float] | None = None,
    fallback: tuple[float, float] = (0.0, 1.0),
) -> tuple[float, float]:
    values: list[float] = []
    for series in series_list:
        numeric = pd.to_numeric(series, errors="coerce")
        finite = numeric[np.isfinite(numeric.to_numpy(dtype=float))]
        values.extend(float(item) for item in finite.tolist())
    if include:
        values.extend(float(item) for item in include)
    if not values:
        return fallback

    lower = float(min(values))
    upper = float(max(values))
    span = upper - lower
    pad = 0.05 if span <= 0.0 else max(0.03, 0.06 * span)
    return lower - pad, upper + pad


def _plot_efficiency_time_series(
    dataframe: pd.DataFrame,
    output_path: Path,
    *,
    corrected_eff_enabled: bool,
) -> Path | None:
    if dataframe.empty:
        return None

    x_values, x_label = _resolve_time_axis(dataframe)
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), sharex=True, constrained_layout=True)
    raw_color = "#1f77b4"
    corrected_color = "#d62728"

    for plane_idx, ax in enumerate(axes.flat, start=1):
        raw_column = f"eff_empirical_raw_{plane_idx}"
        corrected_column = f"eff_empirical_corrected_{plane_idx}"
        y_limits = _padded_limits(
            [dataframe[raw_column], dataframe[corrected_column]],
            include=[0.0, 1.0],
            fallback=(-0.05, 1.05),
        )
        ax.plot(
            x_values,
            pd.to_numeric(dataframe[raw_column], errors="coerce"),
            marker="o",
            markersize=2.5,
            linewidth=0.7,
            color=raw_color,
            label="raw efficiency",
        )
        ax.plot(
            x_values,
            pd.to_numeric(dataframe[corrected_column], errors="coerce"),
            marker="o",
            markersize=2.5,
            linewidth=0.7,
            color=corrected_color,
            label=("corrected efficiency" if corrected_eff_enabled else "used efficiency"),
        )
        ax.set_title(f"Plane {plane_idx}")
        ax.set_xlabel(x_label.replace("_", " "))
        ax.set_ylabel("Efficiency")
        ax.set_ylim(*y_limits)
        ax.grid(alpha=0.25)
        if plane_idx == 1:
            ax.legend()

    fig.suptitle(
        "Step 1 efficiencies over time"
        + (" (geometry-corrected)" if corrected_eff_enabled else " (raw passthrough)"),
        y=1.02,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _plot_efficiency_correction_scatter(
    dataframe: pd.DataFrame,
    output_path: Path,
    *,
    corrected_eff_enabled: bool,
) -> Path | None:
    if dataframe.empty:
        return None

    fig, axes = plt.subplots(2, 2, figsize=(12, 10), constrained_layout=True)
    geometries = [value for value in dataframe["z_config_id"].dropna().astype(str).unique().tolist()]
    color_map = plt.get_cmap("tab10")

    for plane_idx, ax in enumerate(axes.flat, start=1):
        raw_column = f"eff_empirical_raw_{plane_idx}"
        corrected_column = f"eff_empirical_corrected_{plane_idx}"
        raw_values = pd.to_numeric(dataframe[raw_column], errors="coerce")
        corrected_values = pd.to_numeric(dataframe[corrected_column], errors="coerce")
        x_limits = _padded_limits([raw_values], include=[0.0, 1.0], fallback=(-0.05, 1.05))
        y_limits = _padded_limits([corrected_values], include=[0.0, 1.0], fallback=(-0.05, 1.05))
        if geometries:
            for geom_idx, geometry in enumerate(geometries):
                subset = dataframe.loc[dataframe["z_config_id"].astype("string") == geometry]
                if subset.empty:
                    continue
                ax.scatter(
                    pd.to_numeric(subset[raw_column], errors="coerce"),
                    pd.to_numeric(subset[corrected_column], errors="coerce"),
                    s=14,
                    alpha=0.55,
                    color=color_map(geom_idx % 10),
                    label=geometry if plane_idx == 1 else None,
                    edgecolors="none",
                )
        else:
            ax.scatter(
                pd.to_numeric(dataframe[raw_column], errors="coerce"),
                pd.to_numeric(dataframe[corrected_column], errors="coerce"),
                s=14,
                alpha=0.55,
                color="#1f77b4",
                edgecolors="none",
            )
        ax.axline((0.0, 0.0), (1.0, 1.0), linestyle=":", linewidth=1.0, color="black", alpha=0.7)
        ax.set_title(f"Plane {plane_idx}")
        ax.set_xlabel("Raw efficiency")
        ax.set_ylabel("Corrected efficiency" if corrected_eff_enabled else "Used efficiency")
        ax.set_xlim(*x_limits)
        ax.set_ylim(*y_limits)
        ax.grid(alpha=0.25)
        if plane_idx == 1 and geometries:
            ax.legend(fontsize=8, loc="lower right")

    fig.suptitle(
        "Step 1 efficiency correction map"
        + (" by geometry" if geometries else ""),
        y=1.02,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _collect_real_data_slice(
    *,
    config: dict[str, Any],
    station_id: int,
    date_from: pd.Timestamp | None,
    date_to: pd.Timestamp | None,
    min_events: float | None,
    metadata_agg: str,
    timestamp_column: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    trigger_selection = get_trigger_type_selection(config)
    metadata_source = str(trigger_selection.get("metadata_source", "trigger_type"))
    source_name = str(trigger_selection.get("source_name", "trigger_type"))
    if metadata_source == "robust_efficiency":
        task_ids = [int(trigger_selection.get("metadata_task_id", trigger_selection["task_id"]))]
    else:
        task_ids = _normalize_task_ids(
            config.get("step5", {}).get("task_ids"),
            [int(trigger_selection.get("metadata_task_id", trigger_selection["task_id"]))],
        )

    sources: list[tuple[str, pd.DataFrame]] = []
    for task_id in task_ids:
        task_df = _load_task_metadata_source_csv(
            station_id=station_id,
            task_id=task_id,
            source_name=source_name,
            metadata_agg=metadata_agg,
            timestamp_column=timestamp_column,
        )
        sources.append((f"task_{task_id}", task_df))

    merged = sources[0][1].copy()
    if len(sources) > 1:
        merged = _merge_sources(sources[0], sources[1:], how="outer")

    merged, trigger_info = derive_trigger_rate_features(merged, config, allow_plain_fallback=False)
    merged["file_timestamp_utc"] = merged["filename_base"].map(parse_filename_base_ts)
    if timestamp_column in merged.columns:
        merged["execution_timestamp_utc"] = parse_execution_timestamp(merged[timestamp_column])
    else:
        merged["execution_timestamp_utc"] = pd.NaT

    keep = merged["file_timestamp_utc"].notna()
    if date_from is not None:
        keep &= merged["file_timestamp_utc"] >= date_from
    if date_to is not None:
        keep &= merged["file_timestamp_utc"] <= date_to
    collected = merged.loc[keep].copy()
    if collected.empty:
        raise ValueError("No real rows were collected for the requested station/date window.")

    event_values = pd.to_numeric(collected.get("selected_rate_count"), errors="coerce")
    if event_values.notna().any():
        collected["n_events"] = event_values
    if min_events is not None and event_values.notna().any():
        collected = collected.loc[event_values >= float(min_events)].copy()
    if collected.empty:
        raise ValueError("No real rows remain after Step 1 event-count filtering.")

    schedule_all, schedule_path = load_online_schedule(station_id, config=config)
    schedule_window = select_schedule_rows_for_window(schedule_all, date_from=date_from, date_to=date_to)
    online_z = collected["file_timestamp_utc"].map(lambda ts: online_z_tuple_for_timestamp(ts, schedule_window))
    z_rows = [
        [np.nan, np.nan, np.nan, np.nan] if value is None else [float(item) for item in value]
        for value in online_z
    ]
    z_split = pd.DataFrame(z_rows, columns=CANONICAL_Z_COLUMNS, index=collected.index)
    collected = pd.concat([collected, z_split], axis=1)
    collected = add_geometry_columns(collected, source_z_columns=CANONICAL_Z_COLUMNS)

    sort_column = "file_timestamp_utc" if "file_timestamp_utc" in collected.columns else "execution_timestamp_utc"
    collected = collected.sort_values(sort_column, kind="mergesort").reset_index(drop=True)

    metadata = {
        "online_run_dictionary_csv": str(schedule_path),
        "online_schedule_rows_total": int(len(schedule_all)),
        "online_schedule_rows_in_requested_window": int(len(schedule_window)),
        "online_schedule_z_tuples_in_requested_window": [list(z_tuple) for z_tuple in sorted(set(schedule_window["z_tuple"].dropna().tolist()))] if not schedule_window.empty else [],
        "task_ids_used": task_ids,
        "trigger_selection": trigger_info,
        "rows_collected": int(len(collected)),
        "rows_with_geometry": int(collected["z_config_id"].notna().sum()),
        "rows_without_geometry": int(collected["z_config_id"].isna().sum()),
    }
    return collected, metadata


def _selected_output_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    robust_efficiency_source_columns = [
        column
        for column in [
            "robust_efficiency_trigger_source",
            *[
                candidate
                for plane_idx in range(1, 5)
                for candidate in (
                    f"eff{plane_idx}",
                    f"eff{plane_idx}_robust",
                    f"eff{plane_idx}_robust_method",
                    f"eff{plane_idx}_robust_xyphi",
                    f"eff{plane_idx}_robust_xyphi_n_num",
                    f"eff{plane_idx}_robust_xyphi_n_denom",
                    f"eff{plane_idx}_plateau",
                    f"eff{plane_idx}_overall",
                    f"eff{plane_idx}_median_x",
                )
            ],
        ]
        if column in dataframe.columns
    ]
    columns = [
        "filename_base",
        "file_timestamp_utc",
        "execution_timestamp_utc",
        "z_config_id",
        "z_config_label",
        *CANONICAL_Z_COLUMNS,
        "selected_rate_hz",
        "selected_rate_count",
        "count_rate_denominator_seconds",
        "four_plane_rate_hz",
        "four_plane_count",
        "four_plane_robust_hz",
        "four_plane_robust_count",
        "four_plane_robust_hz_union",
        "four_plane_robust_count_union",
        "four_plane_robust_hz_intersection",
        "four_plane_robust_count_intersection",
        "total_rate_hz",
        "total_count",
        *robust_efficiency_source_columns,
        *CANONICAL_EFF_COLUMNS,
        "eff_empirical_raw_1",
        "eff_empirical_raw_2",
        "eff_empirical_raw_3",
        "eff_empirical_raw_4",
        "eff_empirical_corrected_1",
        "eff_empirical_corrected_2",
        "eff_empirical_corrected_3",
        "eff_empirical_corrected_4",
    ]
    available = [column for column in columns if column in dataframe.columns]
    return dataframe[available].copy()


def run(config_path: str | Path | None = None) -> Path:
    _configure_logging()
    ensure_output_dirs()
    config = load_config(config_path)

    step5_config = config.get("step5", {})
    if not isinstance(step5_config, dict):
        step5_config = {}

    station_id = parse_station_id(step5_config.get("station", "MINGO01"))
    date_from = parse_time_bound(step5_config.get("date_from"), end_of_day=False)
    date_to = parse_time_bound(step5_config.get("date_to"), end_of_day=True)
    min_events_raw = step5_config.get("min_events")
    min_events = None if min_events_raw in (None, "", "null", "None") else float(min_events_raw)
    metadata_agg = str(step5_config.get("metadata_agg", "latest")).strip().lower()
    timestamp_column = str(step5_config.get("timestamp_column", "execution_timestamp"))

    corrected_eff_enabled = _resolve_corrected_eff(config)
    fit_clip_output = _resolve_fit_clip_output(config)

    trigger_selection = get_trigger_type_selection(config)
    output_path = cfg_path(config, "paths", "output_csv")
    meta_path = cfg_path(config, "paths", "step1_meta_json")
    fit_table_path = cfg_path(config, "paths", "step0_fit_table_csv")

    collected, collection_meta = _collect_real_data_slice(
        config=config,
        station_id=station_id,
        date_from=date_from,
        date_to=date_to,
        min_events=min_events,
        metadata_agg=metadata_agg,
        timestamp_column=timestamp_column,
    )

    if "selected_rate_hz" not in collected.columns:
        raise ValueError("Collected real data does not contain the selected rate column 'selected_rate_hz'.")

    expected = set(["selected_rate_hz", *CANONICAL_EFF_COLUMNS])
    missing_expected = sorted(column for column in expected if column not in collected.columns)
    if missing_expected:
        raise ValueError("Collected real data is missing required columns: " + ", ".join(missing_expected))

    observed_efficiency_upper_limits = resolve_observed_efficiency_upper_limits(config)
    observed_efficiency_lower_limits = resolve_observed_efficiency_lower_limits(config)
    prepared, observed_efficiency_limit_meta = apply_observed_efficiency_upper_limits(
        collected,
        observed_efficiency_upper_limits,
        lower_limits=observed_efficiency_lower_limits,
        mode="drop",
    )
    for plane_idx in range(1, 5):
        prepared[f"eff_empirical_raw_{plane_idx}"] = pd.to_numeric(prepared[f"eff_empirical_{plane_idx}"], errors="coerce")
        prepared[f"eff_empirical_corrected_{plane_idx}"] = prepared[f"eff_empirical_raw_{plane_idx}"]

    fit_application_meta = {
        "corrected_eff_enabled": corrected_eff_enabled,
        "fit_table_path": str(fit_table_path),
        "rows_with_geometry": int(prepared["z_config_id"].notna().sum()),
        "rows_without_geometry": int(prepared["z_config_id"].isna().sum()),
        "rows_without_matching_fit": 0,
        "geometries_with_fits": [],
    }
    if corrected_eff_enabled:
        fit_table = load_fit_table(fit_table_path)
        prepared, fit_application_meta = apply_fit_table(prepared, fit_table, clip_output=fit_clip_output)
        fit_application_meta["corrected_eff_enabled"] = True
        fit_application_meta["fit_table_path"] = str(fit_table_path)

    selected = _selected_output_dataframe(prepared)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(output_path, index=False)

    time_series_plot = _plot_efficiency_time_series(
        selected,
        PLOTS_DIR / "step1_01_efficiency_time_series.png",
        corrected_eff_enabled=corrected_eff_enabled,
    )
    scatter_plot = _plot_efficiency_correction_scatter(
        selected,
        PLOTS_DIR / "step1_02_efficiency_correction_scatter.png",
        corrected_eff_enabled=corrected_eff_enabled,
    )

    metadata = {
        "output_csv": str(output_path),
        "station_id": int(station_id),
        "date_from": str(date_from) if date_from is not None else None,
        "date_to": str(date_to) if date_to is not None else None,
        "metadata_agg": metadata_agg,
        "timestamp_column": timestamp_column,
        "trigger_selection": trigger_selection,
        "collection": collection_meta,
        "observed_efficiency_limit_filter": observed_efficiency_limit_meta,
        "observed_efficiency_upper_limit_filter": observed_efficiency_limit_meta,
        "fit_application": fit_application_meta,
        "plots": {
            "efficiency_time_series": None if time_series_plot is None else str(time_series_plot),
            "efficiency_correction_scatter": None if scatter_plot is None else str(scatter_plot),
        },
        "row_count": int(len(selected)),
    }
    write_json(meta_path, metadata)

    log.info("Wrote selected real-data file with %d rows to %s", len(selected), output_path)
    if corrected_eff_enabled:
        log.info(
            "Applied geometry-specific corrected efficiencies using %s. Rows without matching fit: %d",
            fit_table_path,
            fit_application_meta["rows_without_matching_fit"],
        )
    else:
        log.info("corrected_eff is disabled; raw empirical efficiencies were passed through unchanged.")
    if observed_efficiency_limit_meta["affected_rows_total"] > 0:
        log.info(
            "Dropped rows outside observed-efficiency bounds %s. Affected rows by plane: %s",
            observed_efficiency_limit_meta["limits_by_plane"],
            observed_efficiency_limit_meta["affected_rows_by_plane"],
        )
    if time_series_plot is not None:
        log.info("Wrote Step 1 efficiency time-series plot to %s", time_series_plot)
    if scatter_plot is not None:
        log.info("Wrote Step 1 efficiency-correction scatter plot to %s", scatter_plot)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect real station data and optionally apply geometry-specific efficiency corrections.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to config JSON file.")
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()
