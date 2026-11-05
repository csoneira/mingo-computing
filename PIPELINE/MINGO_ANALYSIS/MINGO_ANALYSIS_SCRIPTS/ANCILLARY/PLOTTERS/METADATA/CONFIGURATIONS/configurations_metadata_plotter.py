#!/usr/bin/env python3
from __future__ import annotations

import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent
REPO_ROOT = ROOT_DIR.parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.plot_utils import pdf_save_rasterized_page

log = logging.getLogger("configurations_metadata_plotter")

STATIONS = [1, 2, 3, 4]
PLANE_COLUMNS = ["P1_z", "P2_z", "P3_z", "P4_z"]
PLANE_COLORS = {
    "P1_z": "#d62728",
    "P2_z": "#ff7f0e",
    "P3_z": "#2ca02c",
    "P4_z": "#1f77b4",
}
FILE_TS_RE = re.compile(r"(\d{11})$")
ONLINE_RUN_ROOT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS" / "CONFIG_FILES" / "STAGE_0" / "ONLINE_RUN_DICTIONARY"
STATIONS_ROOT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
OUTPUT_DIR = ROOT_DIR / "PLOTS"
OUTPUT_PDF = OUTPUT_DIR / "configurations_metadata_report.pdf"


def _configure_logging() -> None:
    logging.basicConfig(format="[%(levelname)s] CONFIGURATIONS - %(message)s", level=logging.INFO, force=True)


def _parse_filename_base_timestamp(value: object) -> pd.Timestamp:
    text = str(value).strip().lower()
    if text.startswith("mini"):
        text = "mi01" + text[4:]
    match = FILE_TS_RE.search(text)
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
    return pd.Timestamp(dt)


def _parse_execution_timestamp(series: pd.Series) -> pd.Series:
    text = series.astype("string")
    parsed = pd.to_datetime(text, format="%Y-%m-%d_%H.%M.%S", errors="coerce")
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(text[missing], errors="coerce")
    return parsed


def _task3_metadata_path(station_id: int) -> Path:
    return (
        STATIONS_ROOT
        / f"MINGO{station_id:02d}"
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / "TASK_3"
        / "METADATA"
        / "task_3_metadata_specific.csv"
    )


def _online_run_dictionary_path(station_id: int) -> Path:
    return ONLINE_RUN_ROOT / f"STATION_{station_id}" / f"input_file_mingo0{station_id}.csv"


def _load_station_task3_trace(station_id: int) -> pd.DataFrame:
    path = _task3_metadata_path(station_id)
    if not path.exists():
        raise FileNotFoundError(f"Missing Task 3 specific metadata for station {station_id}: {path}")

    dataframe = pd.read_csv(
        path,
        usecols=["filename_base", "execution_timestamp", *PLANE_COLUMNS],
        low_memory=False,
    )
    dataframe["file_timestamp_utc"] = dataframe["filename_base"].map(_parse_filename_base_timestamp)
    dataframe["_exec_ts"] = _parse_execution_timestamp(dataframe["execution_timestamp"])
    for column in PLANE_COLUMNS:
        dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")
    dataframe = dataframe.dropna(subset=["file_timestamp_utc", *PLANE_COLUMNS], how="any")
    if dataframe.empty:
        return dataframe

    dataframe = (
        dataframe.sort_values(["filename_base", "_exec_ts"], na_position="last", kind="mergesort")
        .groupby("filename_base", as_index=False, sort=False)
        .tail(1)
        .sort_values("file_timestamp_utc", kind="mergesort")
        .reset_index(drop=True)
    )
    return dataframe


def _normalize_dictionary_z_positions(dataframe: pd.DataFrame) -> pd.DataFrame:
    work = dataframe.copy()
    for column in ["P1", "P2", "P3", "P4"]:
        work[column] = pd.to_numeric(work[column], errors="coerce")
    work = work.dropna(subset=["start", "end", "P1", "P2", "P3", "P4"], how="any")
    if work.empty:
        return work

    baseline = work["P1"].astype(float)
    work["P1_z"] = work["P1"].astype(float) - baseline
    work["P2_z"] = work["P2"].astype(float) - baseline
    work["P3_z"] = work["P3"].astype(float) - baseline
    work["P4_z"] = work["P4"].astype(float) - baseline
    return work


def _load_station_dictionary(station_id: int) -> pd.DataFrame:
    path = _online_run_dictionary_path(station_id)
    if not path.exists():
        raise FileNotFoundError(f"Missing online-run dictionary for station {station_id}: {path}")

    dataframe = pd.read_csv(path, skiprows=[0], low_memory=False)
    dataframe["start"] = pd.to_datetime(dataframe["start"], errors="coerce")
    dataframe["end"] = pd.to_datetime(dataframe["end"], errors="coerce")
    dataframe = _normalize_dictionary_z_positions(dataframe)
    dataframe = dataframe.sort_values("start", kind="mergesort").reset_index(drop=True)
    return dataframe


def _build_legend() -> tuple[list[Line2D], list[str]]:
    handles = []
    labels = []
    for plane_column in PLANE_COLUMNS:
        handles.append(
            Line2D(
                [0],
                [0],
                color=PLANE_COLORS[plane_column],
                lw=2.0,
                marker="o",
                markersize=4,
            )
        )
        labels.append(plane_column.replace("z_", "").replace("P", "P"))

    handles.append(Line2D([0], [0], color="#444444", lw=5.5, alpha=0.18))
    labels.append("Dictionary period reference")
    handles.append(Line2D([0], [0], color="#444444", lw=1.2, marker="o", markersize=0))
    labels.append("Task 3 metadata trace")
    return handles, labels


def _plot_station_axis(
    axis: plt.Axes,
    *,
    station_id: int,
    task3_df: pd.DataFrame,
    dictionary_df: pd.DataFrame,
) -> None:
    for _, row in dictionary_df.iterrows():
        start = row["start"]
        end = row["end"]
        if pd.isna(start) or pd.isna(end):
            continue
        for plane_column in PLANE_COLUMNS:
            axis.plot(
                [start, end],
                [row[plane_column], row[plane_column]],
                color=PLANE_COLORS[plane_column],
                linewidth=6.0,
                alpha=0.18,
                solid_capstyle="butt",
                zorder=1,
            )

    for plane_column in PLANE_COLUMNS:
        axis.plot(
            task3_df["file_timestamp_utc"],
            task3_df[plane_column],
            color=PLANE_COLORS[plane_column],
            linewidth=1.0,
            marker="o",
            markersize=2.2,
            alpha=0.9,
            zorder=3,
            rasterized=True,
        )

    unique_geometries = (
        task3_df[PLANE_COLUMNS]
        .drop_duplicates()
        .shape[0]
    )
    axis.set_title(
        f"MINGO{station_id:02d} | rows={len(task3_df)} | unique geometries={unique_geometries}",
        fontsize=11,
    )
    axis.set_ylabel("Normalized z [mm]")
    axis.invert_yaxis()
    axis.grid(True, linestyle=":", linewidth=0.6, alpha=0.35)


def build_report(output_path: Path = OUTPUT_PDF) -> Path:
    station_frames: dict[int, pd.DataFrame] = {}
    dictionary_frames: dict[int, pd.DataFrame] = {}
    for station_id in STATIONS:
        station_frames[station_id] = _load_station_task3_trace(station_id)
        dictionary_frames[station_id] = _load_station_dictionary(station_id)

    available_times = [
        pd.to_datetime(frame["file_timestamp_utc"], errors="coerce")
        for frame in station_frames.values()
        if not frame.empty
    ]
    if not available_times:
        raise ValueError("No Task 3 metadata rows with valid file timestamps were found.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(
        len(STATIONS),
        1,
        figsize=(16, 12),
        sharex=True,
        constrained_layout=True,
    )
    axes_arr = np.atleast_1d(axes)

    for axis, station_id in zip(axes_arr, STATIONS):
        _plot_station_axis(
            axis,
            station_id=station_id,
            task3_df=station_frames[station_id],
            dictionary_df=dictionary_frames[station_id],
        )

    axes_arr[-1].set_xlabel("File timestamp UTC")
    handles, labels = _build_legend()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.01))
    fig.suptitle(
        "Task 3 z-position evolution by station\n"
        "Thin traces: Task 3 metadata | Thick transparent bands: ONLINE_RUN_DICTIONARY reference",
        fontsize=14,
        y=1.02,
    )

    with PdfPages(output_path) as pdf:
        pdf_save_rasterized_page(pdf, fig, dpi=170)
    plt.close(fig)
    return output_path


def main() -> None:
    _configure_logging()
    output_path = build_report()
    log.info("Wrote configuration metadata report to %s", output_path)


if __name__ == "__main__":
    main()
