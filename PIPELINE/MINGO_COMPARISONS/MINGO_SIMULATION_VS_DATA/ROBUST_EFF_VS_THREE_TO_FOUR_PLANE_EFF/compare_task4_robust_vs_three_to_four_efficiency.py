#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml


log = logging.getLogger("compare_task4_efficiency")


def _find_repo_root(script_path: Path) -> Path:
    for candidate in script_path.resolve().parents:
        if (candidate / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file() and (candidate / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repository root from {script_path}")


REPO_ROOT = _find_repo_root(Path(__file__))
MASTER_ROOT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS"

STATIONS_ROOT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
DEFAULT_CONFIG_PATH = (
    MASTER_ROOT
    / "SUPPORT" / "CONFIG_FILES"
    / "STAGE_1"
    / "EVENT_DATA"
    / "STEP_1"
    / "TASK_4"
    / "config_task_4.yaml"
)
DEFAULT_COMPARE_CONFIG_PATH = (
    Path(__file__).resolve().parent
    / "config_compare_task4_robust_vs_three_to_four_efficiency.yaml"
)
OUTPUT_DIR = Path(__file__).resolve().parent / "OUTPUTS" / "TASK_4_ROBUST_VS_THREE_TO_FOUR"

_FILE_TS_RE = re.compile(r"(\d{11})$")
_ROBUST_EFF_COLUMNS = {1: "P1_eff", 2: "P2_eff", 3: "P3_eff", 4: "P4_eff"}
_THREE_PLANE_NUMERATOR_COLUMNS = {
    1: "fit_tt_234_rate_hz",
    2: "fit_tt_134_rate_hz",
    3: "fit_tt_124_rate_hz",
    4: "fit_tt_123_rate_hz",
}
_FOUR_PLANE_COLUMN = "fit_tt_1234_rate_hz"
_PLANE_COLORS = {
    1: "#1f77b4",
    2: "#ff7f0e",
    3: "#2ca02c",
    4: "#d62728",
}


def _configure_logging() -> None:
    logging.basicConfig(format="[%(levelname)s] %(message)s", level=logging.INFO, force=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare Task 4 robust-efficiency metadata against efficiencies derived "
            "from fit_tt three-plane / four-plane trigger-type rates."
        )
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="YAML config path used to read selection.stations.",
    )
    parser.add_argument(
        "--stations",
        nargs="*",
        type=int,
        default=None,
        help="Optional explicit station ids. These are added to {0, 1} and config selection stations.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR),
        help="Directory where per-station figures will be written.",
    )
    parser.add_argument(
        "--compare-config",
        default=str(DEFAULT_COMPARE_CONFIG_PATH),
        help="Ancillary YAML config with optional per-station z-position filters.",
    )
    return parser.parse_args()


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a YAML object at top level in {path}")
    return payload


def _selected_station_ids(config_path: Path, cli_stations: list[int] | None) -> list[int]:
    selected: set[int] = {0, 1}
    config = _load_yaml(config_path)
    selection = config.get("selection", {})
    if isinstance(selection, dict):
        for value in selection.get("stations", []) or []:
            try:
                selected.add(int(value))
            except (TypeError, ValueError):
                continue
    for value in cli_stations or []:
        selected.add(int(value))
    return sorted(selected)


def _metadata_path(station_id: int, source_name: str) -> Path:
    return (
        STATIONS_ROOT
        / f"MINGO{station_id:02d}"
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / "TASK_4"
        / "METADATA"
        / f"task_4_metadata_{source_name}.csv"
    )


def _station_name(station_id: int) -> str:
    return f"MINGO{station_id:02d}"


def _station_z_filter(compare_config_path: Path, station_id: int) -> tuple[int, int, int, int] | None:
    if not compare_config_path.exists():
        return None
    config = _load_yaml(compare_config_path)
    raw_mapping = config.get("station_z_positions_mm", {})
    if not isinstance(raw_mapping, dict):
        return None
    raw_value = raw_mapping.get(_station_name(station_id))
    if not isinstance(raw_value, (list, tuple)) or len(raw_value) != 4:
        return None
    try:
        return tuple(int(float(value)) for value in raw_value)
    except (TypeError, ValueError):
        return None


def _parse_execution_timestamp(series: pd.Series) -> pd.Series:
    text = series.astype("string")
    parsed = pd.to_datetime(text, format="%Y-%m-%d_%H.%M.%S", errors="coerce", utc=True)
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(text[missing], errors="coerce", utc=True)
    return parsed


def _aggregate_latest_per_filename(dataframe: pd.DataFrame) -> pd.DataFrame:
    work = dataframe.copy()
    if "execution_timestamp" in work.columns:
        work["_exec_dt"] = _parse_execution_timestamp(work["execution_timestamp"])
        work = work.sort_values(["filename_base", "_exec_dt"], na_position="last", kind="mergesort")
        work = work.groupby("filename_base", sort=False).tail(1)
        work = work.drop(columns=["_exec_dt"], errors="ignore")
    return work.reset_index(drop=True)


def _parse_filename_timestamp(filename_base: object) -> pd.Timestamp:
    text = str(filename_base).strip().lower()
    if text.startswith("mini"):
        text = "mi01" + text[4:]
    match = _FILE_TS_RE.search(text)
    if match is None:
        return pd.NaT
    stamp = match.group(1)
    try:
        year = 2000 + int(stamp[0:2])
        day_of_year = int(stamp[2:5])
        hour = int(stamp[5:7])
        minute = int(stamp[7:9])
        second = int(stamp[9:11])
        dt = datetime(year, 1, 1) + timedelta(
            days=day_of_year - 1,
            hours=hour,
            minutes=minute,
            seconds=second,
        )
    except ValueError:
        return pd.NaT
    return pd.Timestamp(dt, tz="UTC")


def _load_station_comparison_dataframe(
    station_id: int,
    *,
    compare_config_path: Path,
) -> pd.DataFrame:
    robust_path = _metadata_path(station_id, "robust_efficiency")
    trigger_path = _metadata_path(station_id, "trigger_type")
    specific_path = _metadata_path(station_id, "specific")
    if not robust_path.exists():
        raise FileNotFoundError(f"Missing robust-efficiency metadata: {robust_path}")
    if not trigger_path.exists():
        raise FileNotFoundError(f"Missing trigger-type metadata: {trigger_path}")
    if not specific_path.exists():
        raise FileNotFoundError(f"Missing specific metadata: {specific_path}")

    robust_columns = ["filename_base", "execution_timestamp", *_ROBUST_EFF_COLUMNS.values()]
    trigger_columns = ["filename_base", "execution_timestamp", _FOUR_PLANE_COLUMN, *_THREE_PLANE_NUMERATOR_COLUMNS.values()]
    specific_columns = ["filename_base", "execution_timestamp", "P1_z", "P2_z", "P3_z", "P4_z"]

    robust_df = pd.read_csv(robust_path, usecols=robust_columns, low_memory=False)
    trigger_df = pd.read_csv(trigger_path, usecols=trigger_columns, low_memory=False)
    specific_df = pd.read_csv(specific_path, usecols=specific_columns, low_memory=False)

    robust_df = _aggregate_latest_per_filename(robust_df)
    trigger_df = _aggregate_latest_per_filename(trigger_df)
    specific_df = _aggregate_latest_per_filename(specific_df)

    merged = robust_df.merge(
        trigger_df,
        on="filename_base",
        how="inner",
        suffixes=("_robust", "_trigger"),
    )
    merged = merged.merge(
        specific_df[["filename_base", "P1_z", "P2_z", "P3_z", "P4_z"]],
        on="filename_base",
        how="inner",
    )
    if merged.empty:
        raise ValueError(f"No matching filename_base rows found for station {station_id:02d}")

    z_filter = _station_z_filter(compare_config_path, station_id)
    if z_filter is not None:
        for idx, column_name in enumerate(("P1_z", "P2_z", "P3_z", "P4_z")):
            merged[column_name] = pd.to_numeric(merged[column_name], errors="coerce")
        mask = np.ones(len(merged), dtype=bool)
        for idx, column_name in enumerate(("P1_z", "P2_z", "P3_z", "P4_z")):
            mask &= merged[column_name].round().astype("Int64") == int(z_filter[idx])
        merged = merged.loc[mask].copy()
        if merged.empty:
            raise ValueError(
                f"No rows found for station {station_id:02d} with z positions {z_filter}"
            )

    four_plane = pd.to_numeric(merged[_FOUR_PLANE_COLUMN], errors="coerce")
    valid_denominator = four_plane.where(four_plane > 0.0)
    for plane_idx, robust_column in _ROBUST_EFF_COLUMNS.items():
        derived_column = f"eff{plane_idx}_three_to_four"
        numerator = pd.to_numeric(merged[_THREE_PLANE_NUMERATOR_COLUMNS[plane_idx]], errors="coerce")
        merged[robust_column] = pd.to_numeric(merged[robust_column], errors="coerce")
        merged[derived_column] = valid_denominator / (valid_denominator + numerator)

    merged["file_time_utc"] = merged["filename_base"].map(_parse_filename_timestamp)
    if "execution_timestamp_robust" in merged.columns:
        merged["execution_time_utc"] = _parse_execution_timestamp(merged["execution_timestamp_robust"])
    else:
        merged["execution_time_utc"] = pd.NaT
    merged["plot_time_utc"] = merged["file_time_utc"]
    missing_plot_time = merged["plot_time_utc"].isna()
    if missing_plot_time.any():
        merged.loc[missing_plot_time, "plot_time_utc"] = merged.loc[missing_plot_time, "execution_time_utc"]

    merged = merged.sort_values(["plot_time_utc", "filename_base"], na_position="last", kind="mergesort").reset_index(drop=True)
    return merged


def _plot_station_comparison(dataframe: pd.DataFrame, station_id: int, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(16, 10), constrained_layout=True)
    grid = fig.add_gridspec(4, 2, width_ratios=[2.8, 1.2])
    time_axes = [fig.add_subplot(grid[row_idx, 0]) for row_idx in range(4)]
    scatter_ax = fig.add_subplot(grid[:, 1])

    plot_time = dataframe["plot_time_utc"]
    use_datetime = pd.api.types.is_datetime64_any_dtype(plot_time)
    if use_datetime:
        x_values = plot_time
    else:
        x_values = pd.Series(np.arange(len(dataframe)), index=dataframe.index, dtype=float)

    for plane_idx, axis in enumerate(time_axes, start=1):
        robust_column = _ROBUST_EFF_COLUMNS[plane_idx]
        derived_column = f"eff{plane_idx}_three_to_four"
        color = _PLANE_COLORS[plane_idx]

        axis.plot(
            x_values,
            dataframe[robust_column],
            color=color,
            linewidth=1.4,
            alpha=0.95,
            label="robust",
        )
        axis.plot(
            x_values,
            dataframe[derived_column],
            color=color,
            linewidth=1.2,
            linestyle="--",
            alpha=0.95,
            label="four_plane / (four_plane + three_plane)",
        )
        axis.set_ylim(0.0, 1.02)
        axis.set_ylabel(f"Eff P{plane_idx}")
        axis.grid(alpha=0.25)
        axis.set_title(f"Plane {plane_idx}", loc="left", fontsize=10)
        if plane_idx == 1:
            axis.legend(loc="upper right", ncol=2, fontsize=8, frameon=False)
        if plane_idx < 4:
            axis.tick_params(axis="x", labelbottom=False)

    if use_datetime:
        time_axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d\n%H:%M", tz=mdates.UTC))
        fig.autofmt_xdate()
        time_axes[-1].set_xlabel("File time [UTC]")
    else:
        time_axes[-1].set_xlabel("Matched row index")

    for plane_idx in range(1, 5):
        robust_column = _ROBUST_EFF_COLUMNS[plane_idx]
        derived_column = f"eff{plane_idx}_three_to_four"
        scatter_ax.scatter(
            dataframe[robust_column],
            dataframe[derived_column],
            s=14,
            alpha=0.65,
            color=_PLANE_COLORS[plane_idx],
            label=f"P{plane_idx}",
        )

    scatter_ax.plot([0.0, 1.0], [0.0, 1.0], color="black", linewidth=1.0, linestyle=":")
    scatter_ax.set_xlim(0.0, 1.0)
    scatter_ax.set_ylim(0.0, 1.0)
    scatter_ax.set_box_aspect(1.0)
    scatter_ax.set_xlabel("Robust efficiency")
    scatter_ax.set_ylabel("four_plane / (four_plane + three_plane)")
    scatter_ax.set_title("Robust vs three-to-four")
    scatter_ax.grid(alpha=0.25)
    scatter_ax.legend(loc="upper left", fontsize=8, frameon=False)

    station_name = _station_name(station_id)
    z_label = "unknown z"
    if {"P1_z", "P2_z", "P3_z", "P4_z"} <= set(dataframe.columns):
        z_values = [
            int(round(float(pd.to_numeric(dataframe.iloc[0][column_name], errors="coerce"))))
            for column_name in ("P1_z", "P2_z", "P3_z", "P4_z")
        ]
        z_label = "/".join(str(value) for value in z_values)
    fig.suptitle(
        f"{station_name} Task 4 efficiency comparison | z = {z_label} mm | matched rows = {len(dataframe)}",
        fontsize=14,
    )

    output_path = output_dir / f"{station_name}_task4_robust_vs_three_to_four_z_{z_label.replace('/', '_')}.png"
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return output_path


def main() -> None:
    _configure_logging()
    args = _parse_args()
    config_path = Path(args.config).expanduser().resolve()
    compare_config_path = Path(args.compare_config).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    station_ids = _selected_station_ids(config_path, args.stations)
    log.info("Stations requested: %s", station_ids)

    written = 0
    for station_id in station_ids:
        try:
            comparison_df = _load_station_comparison_dataframe(
                station_id,
                compare_config_path=compare_config_path,
            )
        except FileNotFoundError as exc:
            log.warning("%s", exc)
            continue
        except ValueError as exc:
            log.warning("%s", exc)
            continue

        output_path = _plot_station_comparison(comparison_df, station_id, output_dir)
        written += 1
        log.info("Wrote %s", output_path)

    if written == 0:
        raise SystemExit("No station figures were produced.")


if __name__ == "__main__":
    main()
