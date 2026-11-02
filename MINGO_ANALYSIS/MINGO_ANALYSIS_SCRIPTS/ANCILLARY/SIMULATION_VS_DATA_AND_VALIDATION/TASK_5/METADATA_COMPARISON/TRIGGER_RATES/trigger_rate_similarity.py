#!/usr/bin/env python3
"""Compare trigger-type percentages or build simulated-only trigger-percentage plots."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D


THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "CONFIG" / "config_paths.yaml").is_file()),
    None,
)
if REPO_ROOT is None:
    raise RuntimeError(f"Could not locate repository root from {__file__}")
DEFAULT_CONFIG_PATH = THIS_DIR / "trigger_rate_similarity_config.json"
BASE = REPO_ROOT / "MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS"
DEFAULT_SIMULATED_DATA_ROOT = REPO_ROOT / "MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA"

EFF_COLS = [
    "P1_eff_robust_xyphi",
    "P2_eff_robust_xyphi",
    "P3_eff_robust_xyphi",
    "P4_eff_robust_xyphi",
]
SIM_EFF_COLS = [f"sim_eff_p{idx}" for idx in range(1, 5)]
SIM_Z_COLS = ["z_plane_1", "z_plane_2", "z_plane_3", "z_plane_4"]
SIM_OPTIONAL_FILTER_COLS = ["cos_n", "flux_cm2_min"]
Z_COLS = ["P1_z", "P2_z", "P3_z", "P4_z"]
EMPIRICAL_TRIGGER_FORMULAS = {
    "P1": ("fit_tt_234_rate_hz", "fit_tt_1234_rate_hz"),
    "P2": ("fit_tt_134_rate_hz", "fit_tt_1234_rate_hz"),
    "P3": ("fit_tt_124_rate_hz", "fit_tt_1234_rate_hz"),
    "P4": ("fit_tt_123_rate_hz", "fit_tt_1234_rate_hz"),
}
EXACT_FIT_RATE_PATTERN = re.compile(r"^fit_tt_(?:0|[1-4]|12|13|14|23|24|34|123|124|134|234|1234)_rate_hz$")
FILENAME_TIMESTAMP_PATTERN = re.compile(r"mi0\d(\d{11})$", re.IGNORECASE)
PLOTTED_TRIGGER_RATE_COLUMNS = [
    "fit_tt_12_rate_hz",
    "fit_tt_13_rate_hz",
    "fit_tt_14_rate_hz",
    "fit_tt_23_rate_hz",
    "fit_tt_24_rate_hz",
    "fit_tt_34_rate_hz",
    "fit_tt_123_rate_hz",
    "fit_tt_124_rate_hz",
    "fit_tt_134_rate_hz",
    "fit_tt_234_rate_hz",
    "fit_tt_1234_rate_hz",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Match study-station rows to MINGO00 or build a simulated-only trigger-percentage figure."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to JSON config file.")
    return parser.parse_args()


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["_config_path"] = str(config_path)
    config["_config_dir"] = str(config_path.parent)
    return config


def resolve_output_path(config: dict[str, Any], raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (Path(config["_config_dir"]) / path).resolve()


def parse_station_id(raw: object) -> int:
    text = str(raw).strip().upper()
    match = re.fullmatch(r"MINGO(\d{1,2})", text)
    if match is not None:
        return int(match.group(1))
    return int(text)


def format_station_label(station_id: int) -> str:
    return f"MINGO{int(station_id):02d}"


def station_root(station: int) -> Path:
    return BASE / f"MINGO{station:02d}" / "STAGE_1/EVENT_DATA/STEP_1"


def task4_metadata_file(station: int) -> Path:
    return station_root(station) / "TASK_4/METADATA/task_4_metadata_robust_efficiency.csv"


def task5_trigger_metadata_file(station: int) -> Path:
    return station_root(station) / "TASK_5/METADATA/task_5_metadata_trigger_type.csv"


def task5_specific_metadata_file(station: int) -> Path:
    return station_root(station) / "TASK_5/METADATA/task_5_metadata_specific.csv"


def simulation_params_csv_path(config: dict[str, Any]) -> Path:
    raw_csv = config.get("simulation_params_csv")
    if raw_csv not in (None, "", "null", "None"):
        return resolve_output_path(config, str(raw_csv))
    raw_root = config.get("simulated_data_root", str(DEFAULT_SIMULATED_DATA_ROOT))
    return resolve_output_path(config, str(raw_root)) / "step_final_simulation_params.csv"


def canonical_z(value: object) -> int | float:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        raise ValueError("NaN found in z column")
    numeric = float(numeric)
    return int(numeric) if numeric.is_integer() else numeric


def add_z_tuple(dataframe: pd.DataFrame) -> pd.DataFrame:
    out = dataframe.copy()
    for column in Z_COLS:
        out[column] = out[column].map(canonical_z)
    out["z_tuple"] = list(out[Z_COLS].itertuples(index=False, name=None))
    return out


def trigger_rate_columns(columns: list[str]) -> list[str]:
    matched = [column for column in columns if EXACT_FIT_RATE_PATTERN.match(column)]
    return sorted(matched, key=lambda column: (len(column), column))


def trigger_type_from_rate_column(column: str) -> str:
    return str(column).replace("fit_tt_", "").replace("_rate_hz", "")


def normalize_trigger_type(value: object) -> str:
    text = str(value).strip()
    if text.startswith("fit_tt_") and text.endswith("_rate_hz"):
        return text[len("fit_tt_") : -len("_rate_hz")]
    return text


def rate_column_for_trigger_type(trigger_type: object) -> str:
    return f"fit_tt_{normalize_trigger_type(trigger_type)}_rate_hz"


def parse_filename_base_timestamp(value: object) -> pd.Timestamp:
    text = str(value).strip().lower()
    if text.startswith("mini"):
        text = "mi01" + text[4:]
    match = FILENAME_TIMESTAMP_PATTERN.search(text)
    if match is None:
        return pd.NaT
    stamp = match.group(1)
    try:
        year = 2000 + int(stamp[0:2])
        day_of_year = int(stamp[2:5])
        hour = int(stamp[5:7])
        minute = int(stamp[7:9])
        second = int(stamp[9:11])
    except ValueError:
        return pd.NaT
    dt = datetime(year, 1, 1) + timedelta(
        days=day_of_year - 1,
        hours=hour,
        minutes=minute,
        seconds=second,
    )
    return pd.Timestamp(dt, tz="UTC")


def parse_execution_timestamp_series(series: pd.Series) -> pd.Series:
    text = series.astype("string")
    parsed = pd.to_datetime(text, format="%Y-%m-%d_%H.%M.%S", errors="coerce", utc=True)
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(text[missing], errors="coerce", utc=True)
    return parsed


def latest_by_filename_base(dataframe: pd.DataFrame) -> pd.DataFrame:
    if "filename_base" not in dataframe.columns:
        raise KeyError("Metadata file is missing required column 'filename_base'.")
    work = dataframe.copy()
    work["filename_base"] = work["filename_base"].astype(str)
    if "execution_timestamp" in work.columns:
        work["_exec_dt"] = parse_execution_timestamp_series(work["execution_timestamp"])
        work = work.sort_values(["filename_base", "_exec_dt"], na_position="last", kind="mergesort")
        work = work.groupby("filename_base", sort=False).tail(1).drop(columns=["_exec_dt"])
    return work.groupby("filename_base", sort=False).tail(1).reset_index(drop=True)


def parse_efficiency_vector(value: object) -> tuple[float, float, float, float] | None:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return None
    elif isinstance(value, (list, tuple, np.ndarray)):
        decoded = list(value)
    else:
        return None

    if len(decoded) != 4:
        return None
    try:
        return tuple(float(item) for item in decoded)
    except (TypeError, ValueError):
        return None


def parse_simulation_params_dataframe(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Simulation params CSV not found: {path}")

    dataframe = pd.read_csv(path, low_memory=False)
    required_columns = ["file_name", "efficiencies", *SIM_Z_COLS]
    missing_columns = [column for column in required_columns if column not in dataframe.columns]
    if missing_columns:
        raise ValueError(
            f"Simulation params CSV is missing required columns {missing_columns}: {path}"
        )

    work = dataframe.copy()
    work["filename_base"] = (
        work["file_name"]
        .astype(str)
        .str.strip()
        .str.replace(r"\.(dat|parquet)$", "", regex=True)
    )
    for column in [*SIM_Z_COLS, *[column for column in SIM_OPTIONAL_FILTER_COLS if column in work.columns]]:
        work[column] = pd.to_numeric(work[column], errors="coerce")

    work["_parsed_efficiencies"] = work["efficiencies"].map(parse_efficiency_vector)
    invalid_z_mask = work[SIM_Z_COLS].isna().any(axis=1)
    invalid_eff_mask = work["_parsed_efficiencies"].isna()
    invalid_filename_mask = work["filename_base"].eq("")
    drop_mask = invalid_z_mask | invalid_eff_mask | invalid_filename_mask
    dropped_rows = int(drop_mask.sum())
    if dropped_rows:
        work = work.loc[~drop_mask].copy()

    eff_frame = pd.DataFrame(
        work["_parsed_efficiencies"].tolist(),
        columns=SIM_EFF_COLS,
        index=work.index,
    )
    work = pd.concat([work.drop(columns=["_parsed_efficiencies"]), eff_frame], axis=1)
    work["z_tuple"] = [
        tuple(canonical_z(value) for value in row)
        for row in work[SIM_Z_COLS].to_numpy()
    ]
    for column in SIM_EFF_COLS:
        work[column] = pd.to_numeric(work[column], errors="coerce")

    metadata = {
        "simulation_params_csv": str(path),
        "rows_read": int(len(dataframe)),
        "rows_dropped_invalid": dropped_rows,
        "rows_retained": int(len(work)),
        "available_z_tuples": sorted(set(work["z_tuple"].tolist())),
    }
    return work, metadata


def compute_trigger_metrics(dataframe: pd.DataFrame, fit_rate_columns: list[str]) -> pd.DataFrame:
    out = dataframe.copy()
    for column in fit_rate_columns:
        out[column] = pd.to_numeric(out[column], errors="coerce")

    out["fit_tt_total_rate_hz"] = out[fit_rate_columns].sum(axis=1, min_count=1)
    for column in fit_rate_columns:
        pct_col = f"{column}__pct"
        ratio = np.divide(
            out[column].to_numpy(dtype=float),
            out["fit_tt_total_rate_hz"].to_numpy(dtype=float),
            out=np.full(len(out), np.nan, dtype=float),
            where=out["fit_tt_total_rate_hz"].to_numpy(dtype=float) > 0,
        )
        out[pct_col] = 100.0 * ratio

    for plane_label, (missing_col, full_col) in EMPIRICAL_TRIGGER_FORMULAS.items():
        numerator = pd.to_numeric(out[full_col], errors="coerce").to_numpy(dtype=float)
        denominator = numerator + pd.to_numeric(out[missing_col], errors="coerce").to_numpy(dtype=float)
        ratio = np.divide(
            numerator,
            denominator,
            out=np.full(len(out), np.nan, dtype=float),
            where=denominator > 0,
        )
        out[f"empirical_eff_trigger_{plane_label}_pct"] = 100.0 * ratio

    return out


def read_station_dataframe(station: int) -> pd.DataFrame:
    task4 = pd.read_csv(task4_metadata_file(station), low_memory=False)
    trigger = pd.read_csv(task5_trigger_metadata_file(station), low_memory=False)
    specific = pd.read_csv(task5_specific_metadata_file(station), low_memory=False)

    for dataframe in (task4, trigger, specific):
        dataframe["filename_base"] = dataframe["filename_base"].astype(str)

    specific = add_z_tuple(specific)
    fit_rate_cols = trigger_rate_columns(trigger.columns.tolist())
    if not fit_rate_cols:
        raise ValueError(f"No exact fit_tt_*_rate_hz columns were found for station {station}.")

    merged = task4.merge(trigger[["filename_base", *fit_rate_cols]], on="filename_base", how="inner")
    merged = merged.merge(specific[["filename_base", *Z_COLS, "z_tuple"]], on="filename_base", how="left")

    for column in EFF_COLS:
        merged[column] = pd.to_numeric(merged[column], errors="coerce")
    merged = merged.dropna(subset=EFF_COLS).copy()

    merged = compute_trigger_metrics(merged, fit_rate_cols)
    merged["station"] = station
    return merged


def read_simulated_trigger_dataframe(config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    station_id = parse_station_id(config.get("station", "MINGO00"))
    station_label = format_station_label(station_id)
    trigger_path = task5_trigger_metadata_file(station_id)
    if not trigger_path.exists():
        raise FileNotFoundError(f"Trigger metadata file not found for {station_label}: {trigger_path}")

    simulation_params_path = simulation_params_csv_path(config)
    sim_params_df, sim_meta = parse_simulation_params_dataframe(simulation_params_path)

    trigger_df = pd.read_csv(trigger_path, low_memory=False)
    trigger_df = latest_by_filename_base(trigger_df)
    fit_rate_cols = trigger_rate_columns(trigger_df.columns.tolist())
    if not fit_rate_cols:
        raise ValueError(f"No exact fit_tt_*_rate_hz columns were found in {trigger_path}")

    keep_columns = ["filename_base", "param_hash", *fit_rate_cols]
    trigger_df = trigger_df[[column for column in keep_columns if column in trigger_df.columns]].copy()

    optional_columns = [column for column in SIM_OPTIONAL_FILTER_COLS if column in sim_params_df.columns]
    merged = trigger_df.merge(
        sim_params_df[
            [
                "filename_base",
                "param_hash",
                *SIM_Z_COLS,
                *optional_columns,
                "z_tuple",
                *SIM_EFF_COLS,
            ]
        ],
        on="filename_base",
        how="inner",
        suffixes=("", "__sim"),
    )
    if merged.empty:
        raise ValueError(
            f"No rows remained after merging trigger metadata with simulation params on filename_base for {station_label}."
        )
    if "param_hash__sim" in merged.columns:
        mismatch_mask = merged["param_hash"].astype(str) != merged["param_hash__sim"].astype(str)
        if bool(mismatch_mask.any()):
            mismatch_count = int(mismatch_mask.sum())
            raise ValueError(
                f"Found {mismatch_count} filename_base rows where trigger metadata param_hash "
                f"did not match simulation params after merge for {station_label}."
            )
        merged = merged.drop(columns=["param_hash__sim"])

    merged = compute_trigger_metrics(merged, fit_rate_cols)
    merged["station"] = station_id

    metadata = {
        "station_id": station_id,
        "station_label": station_label,
        "trigger_metadata_csv": str(trigger_path),
        "simulation_params_csv": sim_meta["simulation_params_csv"],
        "rows_trigger_metadata_read": int(len(trigger_df)),
        "rows_after_merge": int(len(merged)),
        "simulation_rows_dropped_invalid": int(sim_meta["rows_dropped_invalid"]),
        "available_trigger_rate_columns": fit_rate_cols,
        "available_z_tuples": sim_meta["available_z_tuples"],
    }
    return merged, metadata


def resolve_selected_z_tuple(config: dict[str, Any]) -> tuple[int | float, int | float, int | float, int | float]:
    raw = config.get("selected_z_positions")
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        raise ValueError("Config key 'selected_z_positions' must be a four-element list.")
    return tuple(canonical_z(value) for value in raw)


def resolve_selected_trigger_types(config: dict[str, Any]) -> list[str]:
    raw = config.get("trigger_types")
    if not isinstance(raw, list) or not raw:
        raise ValueError("Config key 'trigger_types' must be a non-empty list.")
    return [normalize_trigger_type(value) for value in raw]


def resolve_simulated_filters(config: dict[str, Any]) -> dict[str, Any]:
    cos_n_raw = config.get("selected_cos_n")
    if cos_n_raw in (None, "", "null", "None"):
        cos_n_range = None
    elif isinstance(cos_n_raw, (list, tuple)):
        if len(cos_n_raw) != 2:
            raise ValueError("Config key 'selected_cos_n' must be a two-element list [min, max].")
        cos_n_min = float(cos_n_raw[0])
        cos_n_max = float(cos_n_raw[1])
        if cos_n_min > cos_n_max:
            raise ValueError("selected_cos_n must satisfy min <= max.")
        cos_n_range = (cos_n_min, cos_n_max)
    else:
        cos_n_value = float(cos_n_raw)
        cos_n_range = (cos_n_value, cos_n_value)

    flux_raw = config.get("selected_flux_cm2_min_range")
    if flux_raw in (None, "", "null", "None"):
        flux_range = None
    else:
        if not isinstance(flux_raw, (list, tuple)) or len(flux_raw) != 2:
            raise ValueError("Config key 'selected_flux_cm2_min_range' must be a two-element list [min, max].")
        flux_min = float(flux_raw[0])
        flux_max = float(flux_raw[1])
        if flux_min > flux_max:
            raise ValueError("selected_flux_cm2_min_range must satisfy min <= max.")
        flux_range = (flux_min, flux_max)

    return {
        "cos_n": cos_n_range,
        "flux_cm2_min_range": flux_range,
    }


def build_simulated_plot_long_dataframe(
    dataframe: pd.DataFrame,
    *,
    selected_z_tuple: tuple[int | float, int | float, int | float, int | float],
    trigger_types: list[str],
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for plane_idx in range(1, 5):
        eff_column = f"sim_eff_p{plane_idx}"
        for trigger_type in trigger_types:
            rate_column = rate_column_for_trigger_type(trigger_type)
            pct_column = f"{rate_column}__pct"
            part = dataframe[
                [
                    "filename_base",
                    "param_hash",
                    "fit_tt_total_rate_hz",
                    rate_column,
                    pct_column,
                    eff_column,
                    *[column for column in SIM_OPTIONAL_FILTER_COLS if column in dataframe.columns],
                    *SIM_Z_COLS,
                ]
            ].copy()
            part["plane"] = f"P{plane_idx}"
            part["plane_index"] = plane_idx
            part["plane_efficiency"] = pd.to_numeric(part[eff_column], errors="coerce")
            part["trigger_type"] = trigger_type
            part["trigger_rate_hz"] = pd.to_numeric(part[rate_column], errors="coerce")
            part["trigger_percentage"] = pd.to_numeric(part[pct_column], errors="coerce")
            part["selected_z_tuple"] = str(list(selected_z_tuple))
            parts.append(
                part[
                    [
                        "filename_base",
                        "param_hash",
                        "plane",
                        "plane_index",
                        "plane_efficiency",
                        "trigger_type",
                        "trigger_rate_hz",
                        "fit_tt_total_rate_hz",
                        "trigger_percentage",
                        *[column for column in SIM_OPTIONAL_FILTER_COLS if column in part.columns],
                        *SIM_Z_COLS,
                        "selected_z_tuple",
                    ]
                ]
            )
    return pd.concat(parts, ignore_index=True)


def make_simulated_only_figure(
    dataframe: pd.DataFrame,
    *,
    selected_z_tuple: tuple[int | float, int | float, int | float, int | float],
    trigger_types: list[str],
    output_path: Path,
    dpi: int,
) -> Path:
    fig, axes = plt.subplots(
        nrows=2,
        ncols=2,
        figsize=(14, 10),
        constrained_layout=True,
        sharex=True,
        sharey=True,
    )
    colors = plt.get_cmap("tab10")(np.linspace(0.0, 1.0, max(len(trigger_types), 1)))
    z_label = "[" + ", ".join(str(value) for value in selected_z_tuple) + "]"
    y_max = 0.0

    for plane_idx, ax in enumerate(axes.flat, start=1):
        eff_column = f"sim_eff_p{plane_idx}"

        for color, trigger_type in zip(colors, trigger_types):
            pct_column = f"{rate_column_for_trigger_type(trigger_type)}__pct"
            x = pd.to_numeric(dataframe[eff_column], errors="coerce")
            y = pd.to_numeric(dataframe[pct_column], errors="coerce")
            valid = x.notna() & y.notna()
            if valid.any():
                y_max = max(y_max, float(y.loc[valid].max()))
            ax.scatter(
                x.loc[valid],
                y.loc[valid],
                s=18,
                alpha=0.78,
                color=color,
                edgecolors="none",
                label=trigger_type,
            )

        ax.set_title(f"Plane P{plane_idx} | z = {z_label}")
        ax.set_xlabel(f"Simulated efficiency P{plane_idx} [fraction]")
        ax.set_ylabel("Trigger percentage of total simulated rate [%]")
        ax.axvline(1.0, color="0.35", linestyle="--", linewidth=1.0, alpha=0.9)
        ax.grid(alpha=0.25)

    y_upper = max(1.0, y_max * 1.05)
    x_left, _ = axes.flat[0].get_xlim()
    for ax in axes.flat:
        ax.set_xlim(left=x_left, right=1.05)
        ax.set_ylim(bottom=0.0, top=y_upper)

    handles, labels = axes.flat[0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 1.01), ncol=max(1, len(trigger_types)))
    fig.suptitle(
        "Simulated trigger percentages vs. simulated plane efficiencies",
        fontsize=13,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=int(dpi), bbox_inches="tight")
    plt.close(fig)
    return output_path


def nearest_match_dataframe(
    reference_df: pd.DataFrame,
    study_df: pd.DataFrame,
    *,
    require_same_z_geometry: bool,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    grouped_ref = {
        z_tuple: group.copy()
        for z_tuple, group in reference_df.groupby("z_tuple", dropna=False)
    }

    for _, study_row in study_df.iterrows():
        candidates = reference_df
        if require_same_z_geometry:
            z_tuple = study_row.get("z_tuple")
            if z_tuple not in grouped_ref:
                continue
            candidates = grouped_ref[z_tuple]
        candidate_eff = candidates[EFF_COLS].to_numpy(dtype=float)
        study_eff = study_row[EFF_COLS].to_numpy(dtype=float)
        distances = np.linalg.norm(candidate_eff - study_eff, axis=1)
        best_local_idx = int(np.argmin(distances))
        best_ref = candidates.iloc[best_local_idx]

        row: dict[str, Any] = {
            "station": int(study_row["station"]),
            "study_filename_base": str(study_row["filename_base"]),
            "ref_filename_base": str(best_ref["filename_base"]),
            "study_file_timestamp_utc": parse_filename_base_timestamp(study_row["filename_base"]),
            "z_tuple": study_row.get("z_tuple"),
            "eff_distance": float(distances[best_local_idx]),
        }

        for column in EFF_COLS:
            row[f"study_{column}"] = float(study_row[column])
            row[f"ref_{column}"] = float(best_ref[column])

        for column in study_df.columns:
            if column.endswith("__pct") or column.startswith("empirical_eff_trigger_") or column in ("fit_tt_total_rate_hz",):
                row[f"study_{column}"] = pd.to_numeric(study_row[column], errors="coerce")
                row[f"ref_{column}"] = pd.to_numeric(best_ref[column], errors="coerce")

        rows.append(row)

    return pd.DataFrame(rows)


def make_figure(
    matched_by_station: dict[int, pd.DataFrame],
    *,
    fit_pct_columns: list[str],
    output_path: Path,
    dpi: int,
) -> Path:
    stations = list(matched_by_station)
    nrows = len(stations)
    fig, axes = plt.subplots(
        nrows=nrows,
        ncols=3,
        figsize=(20, 4.6 * nrows),
        constrained_layout=True,
        squeeze=False,
        sharex="col",
        sharey="col",
    )

    trigger_labels = [column.replace("fit_tt_", "").replace("_rate_hz__pct", "").replace("_rate_hz", "") for column in fit_pct_columns]
    trigger_colors = plt.get_cmap("tab20")(np.linspace(0.0, 1.0, max(len(fit_pct_columns), 1)))
    emp_labels = list(EMPIRICAL_TRIGGER_FORMULAS)
    emp_columns = [f"empirical_eff_trigger_{label}_pct" for label in emp_labels]
    emp_colors = plt.get_cmap("Set1")(np.linspace(0.0, 1.0, len(emp_labels)))
    eff_labels = [f"P{idx}" for idx in range(1, len(EFF_COLS) + 1)]
    eff_colors = plt.get_cmap("Dark2")(np.linspace(0.0, 1.0, len(EFF_COLS)))

    left_handles: list[Line2D] = []
    right_handles: list[Line2D] = []
    eff_handles: list[Line2D] = []

    left_max = 0.0
    right_max = 0.0
    eff_max = 0.0
    for matched in matched_by_station.values():
        for column in fit_pct_columns:
            left_series = pd.concat(
                [
                    pd.to_numeric(matched[f"ref_{column}"], errors="coerce"),
                    pd.to_numeric(matched[f"study_{column}"], errors="coerce"),
                ],
                ignore_index=True,
            )
            if left_series.notna().any():
                left_max = max(left_max, float(left_series.max()))
        for column in emp_columns:
            right_series = pd.concat(
                [
                    pd.to_numeric(matched[f"ref_{column}"], errors="coerce"),
                    pd.to_numeric(matched[f"study_{column}"], errors="coerce"),
                ],
                ignore_index=True,
            )
            if right_series.notna().any():
                right_max = max(right_max, float(right_series.max()))
        for column in EFF_COLS:
            eff_series = pd.concat(
                [
                    pd.to_numeric(matched[f"ref_{column}"], errors="coerce"),
                    pd.to_numeric(matched[f"study_{column}"], errors="coerce"),
                ],
                ignore_index=True,
            )
            if eff_series.notna().any():
                eff_max = max(eff_max, float(eff_series.max()))

    left_upper = max(1.0, left_max * 1.03)
    right_upper = max(1.0, right_max * 1.03)
    eff_upper = max(1.0, eff_max * 1.03)

    for row_idx, station in enumerate(stations):
        matched = matched_by_station[station]
        ax_left = axes[row_idx, 0]
        ax_right = axes[row_idx, 1]
        ax_eff = axes[row_idx, 2]

        for color, column, label in zip(trigger_colors, fit_pct_columns, trigger_labels):
            x = pd.to_numeric(matched[f"ref_{column}"], errors="coerce")
            y = pd.to_numeric(matched[f"study_{column}"], errors="coerce")
            valid = x.notna() & y.notna()
            scatter = ax_left.scatter(
                x.loc[valid],
                y.loc[valid],
                s=14,
                alpha=0.75,
                color=color,
                edgecolors="none",
                label=label,
            )
            if row_idx == 0:
                left_handles.append(
                    Line2D(
                        [0],
                        [0],
                        marker="o",
                        linestyle="None",
                        markersize=6.5,
                        markerfacecolor=color,
                        markeredgecolor=color,
                        alpha=1.0,
                    )
                )

        for color, label, column in zip(emp_colors, emp_labels, emp_columns):
            x = pd.to_numeric(matched[f"ref_{column}"], errors="coerce")
            y = pd.to_numeric(matched[f"study_{column}"], errors="coerce")
            valid = x.notna() & y.notna()
            scatter = ax_right.scatter(
                x.loc[valid],
                y.loc[valid],
                s=18,
                alpha=0.82,
                color=color,
                edgecolors="none",
                label=label,
            )
            if row_idx == 0:
                right_handles.append(
                    Line2D(
                        [0],
                        [0],
                        marker="o",
                        linestyle="None",
                        markersize=7.0,
                        markerfacecolor=color,
                        markeredgecolor=color,
                        alpha=1.0,
                    )
                )

        for color, label, column in zip(eff_colors, eff_labels, EFF_COLS):
            x = pd.to_numeric(matched[f"ref_{column}"], errors="coerce")
            y = pd.to_numeric(matched[f"study_{column}"], errors="coerce")
            valid = x.notna() & y.notna()
            ax_eff.scatter(
                x.loc[valid],
                y.loc[valid],
                s=20,
                alpha=0.82,
                color=color,
                edgecolors="none",
                label=label,
            )
            if row_idx == 0:
                eff_handles.append(
                    Line2D(
                        [0],
                        [0],
                        marker="o",
                        linestyle="None",
                        markersize=7.0,
                        markerfacecolor=color,
                        markeredgecolor=color,
                        alpha=1.0,
                    )
                )

        mean_distance = float(pd.to_numeric(matched["eff_distance"], errors="coerce").mean())
        title_suffix = f"MINGO{station:02d} | matches={len(matched)} | mean d_eff={mean_distance:.5g}"

        for axis in (ax_left, ax_right, ax_eff):
            axis.set_aspect("equal", adjustable="box")
            axis.grid(alpha=0.25)

        ax_left.plot([0.0, left_upper], [0.0, left_upper], linestyle="--", color="black", alpha=0.6, linewidth=1.0)
        ax_left.set_xlim(left=0.0, right=left_upper)
        ax_left.set_ylim(bottom=0.0, top=left_upper)

        ax_left.set_title(f"Trigger-type percentages\n{title_suffix}", fontsize=10)
        ax_left.set_xlabel("MINGO00 [%]")
        ax_left.set_ylabel(f"MINGO{station:02d} [%]")

        ax_right.plot([0.0, right_upper], [0.0, right_upper], linestyle="--", color="black", alpha=0.6, linewidth=1.0)
        ax_right.set_xlim(left=0.0, right=right_upper)
        ax_right.set_ylim(bottom=0.0, top=right_upper)
        ax_right.set_title(f"Empirical efficiency by trigger rate\n{title_suffix}", fontsize=10)
        ax_right.set_xlabel("MINGO00 [%]")
        ax_right.set_ylabel(f"MINGO{station:02d} [%]")

        ax_eff.plot([0.0, eff_upper], [0.0, eff_upper], linestyle="--", color="black", alpha=0.6, linewidth=1.0)
        ax_eff.set_xlim(left=0.0, right=eff_upper)
        ax_eff.set_ylim(bottom=0.0, top=eff_upper)
        ax_eff.set_title(f"Robust efficiencies used for matching\n{title_suffix}", fontsize=10)
        ax_eff.set_xlabel("MINGO00 [fraction]")
        ax_eff.set_ylabel(f"MINGO{station:02d} [fraction]")

    if left_handles:
        fig.legend(left_handles, trigger_labels, loc="upper center", bbox_to_anchor=(0.18, 1.01), ncol=4, fontsize=8, frameon=True)
    if right_handles:
        fig.legend(right_handles, emp_labels, loc="upper center", bbox_to_anchor=(0.50, 1.01), ncol=4, fontsize=8, frameon=True)
    if eff_handles:
        fig.legend(eff_handles, eff_labels, loc="upper center", bbox_to_anchor=(0.84, 1.01), ncol=4, fontsize=8, frameon=True)

    fig.suptitle(
        "Trigger-rate similarity after nearest robust-efficiency matching to MINGO00",
        fontsize=13,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=int(dpi), bbox_inches="tight")
    plt.close(fig)
    return output_path


def make_station_time_series_figure(
    matched: pd.DataFrame,
    *,
    station: int,
    fit_pct_columns: list[str],
    output_path: Path,
    dpi: int,
) -> Path:
    plot_frame = matched.copy()
    plot_frame["study_file_timestamp_utc"] = pd.to_datetime(
        plot_frame["study_file_timestamp_utc"],
        errors="coerce",
        utc=True,
    )
    plot_frame = plot_frame.dropna(subset=["study_file_timestamp_utc"]).sort_values(
        "study_file_timestamp_utc",
        kind="mergesort",
    )
    if plot_frame.empty:
        raise ValueError(f"No valid basename timestamps found for MINGO{station:02d}.")

    nrows = len(fit_pct_columns)
    fig, axes = plt.subplots(
        nrows=nrows,
        ncols=1,
        figsize=(14, max(2.3 * nrows, 8.0)),
        constrained_layout=True,
        sharex=True,
        squeeze=False,
    )
    axes = axes.ravel()
    x_values = plot_frame["study_file_timestamp_utc"]
    study_color = "#1f77b4"
    ref_color = "#d62728"
    labels = [column.replace("fit_tt_", "").replace("_rate_hz__pct", "") for column in fit_pct_columns]

    for ax, column, label in zip(axes, fit_pct_columns, labels):
        ref_values = pd.to_numeric(plot_frame[f"ref_{column}"], errors="coerce")
        study_values = pd.to_numeric(plot_frame[f"study_{column}"], errors="coerce")
        y_max = np.nanmax(np.concatenate([ref_values.to_numpy(dtype=float), study_values.to_numpy(dtype=float)]))
        if not np.isfinite(y_max):
            y_max = 1.0
        y_upper = max(1.0, float(y_max) * 1.03)

        ax.plot(
            x_values,
            study_values,
            color=study_color,
            marker="o",
            markersize=2.6,
            linewidth=1.0,
            alpha=0.92,
            label=f"MINGO{station:02d} study",
        )
        ax.plot(
            x_values,
            ref_values,
            color=ref_color,
            marker="o",
            markersize=2.4,
            linewidth=0.95,
            alpha=0.90,
            label="MINGO00 matched",
        )
        ax.set_ylim(bottom=0.0, top=y_upper)
        ax.set_ylabel(f"{label} [%]")
        ax.grid(alpha=0.25)

    axes[0].legend(loc="upper right", fontsize=8, frameon=True)
    axes[0].set_title(
        f"MINGO{station:02d} trigger-type percentages over study-file basename time\n"
        "Study values and their matched MINGO00 reference values",
        fontsize=12,
    )
    axes[-1].set_xlabel("Data timestamp from filename_base [UTC]")
    fig.autofmt_xdate()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=int(dpi), bbox_inches="tight")
    plt.close(fig)
    return output_path


def run_simulated_only(config: dict[str, Any]) -> None:
    station_id = parse_station_id(config.get("station", "MINGO00"))
    station_label = format_station_label(station_id)
    selected_z_tuple = resolve_selected_z_tuple(config)
    trigger_types = resolve_selected_trigger_types(config)
    selected_filters = resolve_simulated_filters(config)
    figure_dpi = int(config.get("figure_dpi", 180))
    output_path = resolve_output_path(
        config,
        str(config.get("output_figure", "PLOTS/trigger_rate_similarity_simulated_only.png")),
    )
    output_csv_raw = config.get("output_csv")
    output_csv_path = (
        None
        if output_csv_raw in (None, "", "null", "None")
        else resolve_output_path(config, str(output_csv_raw))
    )

    simulated_df, meta = read_simulated_trigger_dataframe(config)
    available_z_tuples = sorted(set(simulated_df["z_tuple"].tolist()))
    if selected_z_tuple not in set(available_z_tuples):
        raise ValueError(
            "Selected z configuration was not found in the simulated rows for "
            f"{station_label}: {selected_z_tuple}. Available z tuples: {available_z_tuples}"
        )

    available_rate_columns = meta["available_trigger_rate_columns"]
    requested_rate_columns = [rate_column_for_trigger_type(trigger_type) for trigger_type in trigger_types]
    missing_triggers = [
        trigger_type
        for trigger_type, rate_column in zip(trigger_types, requested_rate_columns)
        if rate_column not in available_rate_columns
    ]
    if missing_triggers:
        raise ValueError(
            f"Requested trigger types are unavailable in {meta['trigger_metadata_csv']}: {missing_triggers}. "
            f"Available exact trigger columns: {[trigger_type_from_rate_column(column) for column in available_rate_columns]}"
        )

    filtered_df = simulated_df.copy()
    filter_mask = pd.Series(True, index=filtered_df.index, dtype=bool)
    selected_cos_n_range = selected_filters["cos_n"]
    if selected_cos_n_range is not None:
        if "cos_n" not in filtered_df.columns:
            raise ValueError(
                f"Config requested selected_cos_n={selected_cos_n_range}, but column 'cos_n' is missing from "
                f"{meta['simulation_params_csv']}."
            )
        cos_n_series = pd.to_numeric(filtered_df["cos_n"], errors="coerce")
        cos_n_min, cos_n_max = selected_cos_n_range
        filter_mask &= cos_n_series.notna() & (cos_n_series >= float(cos_n_min)) & (cos_n_series <= float(cos_n_max))

    selected_flux_range = selected_filters["flux_cm2_min_range"]
    if selected_flux_range is not None:
        if "flux_cm2_min" not in filtered_df.columns:
            raise ValueError(
                "Config requested selected_flux_cm2_min_range, but column 'flux_cm2_min' is missing from "
                f"{meta['simulation_params_csv']}."
            )
        flux_min, flux_max = selected_flux_range
        flux_series = pd.to_numeric(filtered_df["flux_cm2_min"], errors="coerce")
        filter_mask &= flux_series.notna() & (flux_series >= float(flux_min)) & (flux_series <= float(flux_max))

    rows_before_sim_filters = int(len(filtered_df))
    filtered_df = filtered_df.loc[filter_mask].copy()
    rows_removed_by_sim_filters = rows_before_sim_filters - int(len(filtered_df))
    if filtered_df.empty:
        raise ValueError(
            f"No simulated rows remained for {station_label} after applying selected_cos_n={selected_cos_n_range!r} "
            f"and selected_flux_cm2_min_range={selected_flux_range!r}."
        )

    geometry_df = filtered_df.loc[filtered_df["z_tuple"] == selected_z_tuple].copy()
    if geometry_df.empty:
        raise ValueError(
            f"No simulated rows remained after filtering to z tuple {selected_z_tuple} for {station_label}, "
            f"selected_cos_n={selected_cos_n_range!r}, selected_flux_cm2_min_range={selected_flux_range!r}."
        )

    required_columns = ["fit_tt_total_rate_hz", *SIM_EFF_COLS, *requested_rate_columns]
    required_pct_columns = [f"{column}__pct" for column in requested_rate_columns]
    invalid_mask = pd.Series(False, index=geometry_df.index, dtype=bool)
    for column in [*required_columns, *required_pct_columns]:
        invalid_mask |= pd.to_numeric(geometry_df[column], errors="coerce").isna()
    invalid_mask |= pd.to_numeric(geometry_df["fit_tt_total_rate_hz"], errors="coerce") <= 0
    invalid_rows_dropped = int(invalid_mask.sum())
    plot_df = geometry_df.loc[~invalid_mask].copy()
    if plot_df.empty:
        raise ValueError(
            f"All rows for z tuple {selected_z_tuple} became invalid after numeric filtering for {station_label}."
        )

    figure_path = make_simulated_only_figure(
        plot_df,
        selected_z_tuple=selected_z_tuple,
        trigger_types=trigger_types,
        output_path=output_path,
        dpi=figure_dpi,
    )

    plot_values_df = build_simulated_plot_long_dataframe(
        plot_df,
        selected_z_tuple=selected_z_tuple,
        trigger_types=trigger_types,
    )
    if output_csv_path is not None:
        output_csv_path.parent.mkdir(parents=True, exist_ok=True)
        plot_values_df.to_csv(output_csv_path, index=False)

    print("Mode: simulated_only")
    print(f"Station: {station_label}")
    print(f"Simulation params CSV: {meta['simulation_params_csv']}")
    print(f"Trigger metadata CSV: {meta['trigger_metadata_csv']}")
    print(f"Available exact trigger-rate columns found: {available_rate_columns}")
    print(f"Selected z tuple: {selected_z_tuple}")
    print(f"Selected trigger types: {trigger_types}")
    print(f"Selected cos_n range: {selected_cos_n_range}")
    print(f"Selected flux_cm2_min range: {selected_flux_range}")
    print(f"Simulation rows dropped before merge because of invalid z/efficiency data: {meta['simulation_rows_dropped_invalid']}")
    print(f"Rows after filename_base merge: {meta['rows_after_merge']}")
    print(f"Rows removed by cos_n/flux filters: {rows_removed_by_sim_filters}")
    print(f"Rows after cos_n/flux filters: {len(filtered_df)}")
    print(f"Rows matching selected z tuple before final numeric filtering: {len(geometry_df)}")
    print(f"Rows dropped after selected-z numeric filtering: {invalid_rows_dropped}")
    print(f"Number of simulated rows used: {len(plot_df)}")
    print(f"Saved figure: {figure_path}")
    if output_csv_path is not None:
        print(f"Saved plotted values CSV: {output_csv_path}")


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    mode = str(config.get("mode", "station_comparison")).strip().lower()
    if mode == "simulated_only":
        run_simulated_only(config)
        return

    study_stations = [int(value) for value in config.get("study_stations", [])]
    if not study_stations:
        raise ValueError("Config must define a non-empty study_stations list.")
    if len(study_stations) > 4:
        raise ValueError("Select at most 4 study stations.")

    require_same_z_geometry = bool(config.get("match_same_z_geometry", True))
    figure_dpi = int(config.get("figure_dpi", 180))
    output_path = resolve_output_path(config, str(config.get("output_figure", "PLOTS/trigger_rate_similarity_summary.png")))

    reference_df = read_station_dataframe(0)
    fit_rate_cols = trigger_rate_columns(reference_df.columns.tolist())
    fit_pct_columns = [
        f"{column}__pct"
        for column in fit_rate_cols
        if column in PLOTTED_TRIGGER_RATE_COLUMNS
    ]

    matched_by_station: dict[int, pd.DataFrame] = {}
    for station in study_stations:
        study_df = read_station_dataframe(station)
        matched = nearest_match_dataframe(
            reference_df,
            study_df,
            require_same_z_geometry=require_same_z_geometry,
        )
        matched_by_station[station] = matched
        print(
            f"MINGO{station:02d}: matched {len(matched)} rows | "
            f"mean d_eff={pd.to_numeric(matched['eff_distance'], errors='coerce').mean():.6g}"
        )

    figure_path = make_figure(
        matched_by_station,
        fit_pct_columns=fit_pct_columns,
        output_path=output_path,
        dpi=figure_dpi,
    )
    print(f"Saved figure: {figure_path}")

    output_dir = output_path.parent
    output_stem = output_path.stem
    for station, matched in matched_by_station.items():
        station_output = output_dir / f"{output_stem}__MINGO{station:02d}_timeseries.png"
        time_series_path = make_station_time_series_figure(
            matched,
            station=station,
            fit_pct_columns=fit_pct_columns,
            output_path=station_output,
            dpi=figure_dpi,
        )
        print(f"Saved time-series figure: {time_series_path}")


if __name__ == "__main__":
    main()
