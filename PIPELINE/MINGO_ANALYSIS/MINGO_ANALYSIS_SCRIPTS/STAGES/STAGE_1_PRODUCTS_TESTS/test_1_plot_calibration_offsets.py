#!/usr/bin/env python3
"""Plot Task 2 calibration offsets over an acquisition-date interval.

The input is the station's ``task_2_metadata_calibration.csv``.  Outputs are
written only below that station's temporary ``STAGE_1_PRODUCTS_TESTS`` area.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
from pathlib import Path
import re
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import yaml


ANALYSIS_ROOT = Path(__file__).resolve().parents[3]
STATIONS_ROOT = ANALYSIS_ROOT / "MINGO_ANALYSIS_STATIONS"
DEFAULT_CONFIG = Path(__file__).with_name("config_test_1_calibration_offsets.yaml")
TEST_OUTPUT_NAME = "TEST_1_CALIBRATION_OFFSETS"
PLANES = range(1, 5)
STRIPS = range(1, 5)
OFFSET_FAMILIES = ("Q_F", "Q_B", "Q_sum", "T_dif", "T_sum")
RUN_STAMP_RE = re.compile(r"(\d{11})$")
SLEWING_COLUMN_RE = re.compile(
    r"^P[1-4]_s[1-4]_T_slew_"
    r"(?:coeffs__\d+|basis_means__\d+|domain__[01]|degree|coordinate|residual_column)$"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"YAML configuration file (default: {DEFAULT_CONFIG.name})",
    )
    return parser.parse_args()


def normalize_station(value: Any) -> tuple[int, str]:
    text = str(value).strip().upper()
    if text.startswith("MINGO"):
        text = text[5:]
    try:
        number = int(text)
    except ValueError as exc:
        raise ValueError(f"Invalid station {value!r}; use 1, 01, or MINGO01") from exc
    if number < 0 or number > 99:
        raise ValueError(f"Station number is outside the supported range: {number}")
    return number, f"MINGO{number:02d}"


def parse_boundary(value: Any, *, end: bool) -> datetime:
    """Parse a YAML date/datetime, making a date-only end boundary inclusive."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        parsed = datetime.combine(value, time.min)
        return parsed + timedelta(days=1) - timedelta(microseconds=1) if end else parsed

    text = str(value).strip()
    if not text:
        raise ValueError("Date boundaries cannot be empty")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid ISO date/datetime: {value!r}") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    if end and re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        parsed += timedelta(days=1) - timedelta(microseconds=1)
    return parsed


def acquisition_datetime(filename_base: Any) -> pd.Timestamp:
    """Decode the DATAFLOW YYDDDHHMMSS suffix in a metadata basename."""
    match = RUN_STAMP_RE.search(str(filename_base).strip())
    if not match:
        return pd.NaT
    stamp = match.group(1)
    try:
        year = 2000 + int(stamp[0:2])
        day_of_year = int(stamp[2:5])
        hour = int(stamp[5:7])
        minute = int(stamp[7:9])
        second = int(stamp[9:11])
        if not 1 <= day_of_year <= 366:
            return pd.NaT
        result = datetime(year, 1, 1) + timedelta(
            days=day_of_year - 1,
            hours=hour,
            minutes=minute,
            seconds=second,
        )
    except (OverflowError, ValueError):
        return pd.NaT
    if result.year != year:
        return pd.NaT
    return pd.Timestamp(result)


def calibration_columns() -> list[str]:
    return [
        f"P{plane}_s{strip}_{family}"
        for plane in PLANES
        for strip in STRIPS
        for family in OFFSET_FAMILIES
    ]


def load_config(path: Path) -> tuple[str, datetime, datetime]:
    with path.expanduser().open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, dict):
        raise ValueError("The config root must be a YAML mapping")
    missing = [key for key in ("station", "start_date", "end_date") if key not in config]
    if missing:
        raise ValueError(f"Missing config field(s): {', '.join(missing)}")

    _, station_name = normalize_station(config["station"])
    start = parse_boundary(config["start_date"], end=False)
    end = parse_boundary(config["end_date"], end=True)
    if start > end:
        raise ValueError(f"start_date ({start}) is later than end_date ({end})")
    return station_name, start, end


def is_valid_parquet(path: Path) -> bool:
    """Return whether a file has the leading and trailing Parquet magic."""
    try:
        if path.stat().st_size < 8:
            return False
        with path.open("rb") as handle:
            if handle.read(4) != b"PAR1":
                return False
            handle.seek(-4, 2)
            return handle.read(4) == b"PAR1"
    except OSError:
        return False


def valid_parquet_lake_basenames(station_root: Path) -> set[str]:
    """Return basenames backed by valid final Parquets in this station."""
    lake = station_root / "STAGE_1_PRODUCTS" / "EVENT_DATA" / "PARQUET_LAKE"
    return {
        path.stem.removeprefix("postprocessed_")
        for path in lake.glob("postprocessed_*.parquet")
        if is_valid_parquet(path)
    }


def select_metadata(
    path: Path,
    start: datetime,
    end: datetime,
    *,
    allowed_basenames: set[str] | None = None,
) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Task 2 calibration metadata not found: {path}")

    header = pd.read_csv(path, nrows=0).columns.tolist()
    required = ["filename_base", *calibration_columns()]
    missing = [column for column in required if column not in header]
    if missing:
        preview = ", ".join(missing[:8])
        raise ValueError(f"Calibration metadata is missing required columns: {preview}")
    slewing_columns = [column for column in header if SLEWING_COLUMN_RE.fullmatch(column)]
    usecols = required + slewing_columns
    if "execution_timestamp" in header:
        usecols.append("execution_timestamp")
    frame = pd.read_csv(path, usecols=usecols, low_memory=False)
    frame["filename_base"] = frame["filename_base"].astype(str).str.strip()
    if allowed_basenames is not None:
        allowed = {str(value).strip() for value in allowed_basenames}
        frame = frame.loc[frame["filename_base"].isin(allowed)].copy()
    frame["acquisition_datetime"] = frame["filename_base"].map(acquisition_datetime)

    invalid_count = int(frame["acquisition_datetime"].isna().sum())
    if invalid_count:
        print(f"Warning: ignored {invalid_count} row(s) with invalid acquisition basenames.")
    frame = frame.loc[frame["acquisition_datetime"].between(start, end, inclusive="both")].copy()
    if frame.empty:
        raise ValueError(
            "No lake-backed Task 2 calibration rows fall between "
            f"{start.isoformat()} and {end.isoformat()}"
        )

    # Reprocessing can append another calibration for the same acquisition.
    # Keep its most recent execution so each input file contributes one point.
    if "execution_timestamp" in frame:
        frame["_execution_datetime"] = pd.to_datetime(
            frame["execution_timestamp"], format="%Y-%m-%d_%H.%M.%S", errors="coerce"
        )
        frame = frame.sort_values(
            ["acquisition_datetime", "_execution_datetime"], na_position="first"
        )
    else:
        frame = frame.sort_values("acquisition_datetime")
    frame = frame.drop_duplicates("filename_base", keep="last")
    return frame.drop(columns=["_execution_datetime"], errors="ignore").reset_index(drop=True)


def format_time_axes(axes: Any) -> None:
    for axis in axes:
        locator = mdates.AutoDateLocator(minticks=3, maxticks=8)
        formatter = mdates.ConciseDateFormatter(locator)
        axis.xaxis.set_major_locator(locator)
        axis.xaxis.set_major_formatter(formatter)
        axis.grid(True, alpha=0.25)
        axis.tick_params(axis="x", labelrotation=20)


def save_charge_plot(frame: pd.DataFrame, destination: Path, title: str) -> None:
    fig, axes = plt.subplots(3, 4, figsize=(19, 11), sharex=True, constrained_layout=True)
    colors = plt.get_cmap("tab10").colors
    for row, family in enumerate(("Q_F", "Q_B", "Q_sum")):
        for plane in PLANES:
            axis = axes[row, plane - 1]
            for strip in STRIPS:
                column = f"P{plane}_s{strip}_{family}"
                axis.plot(
                    frame["acquisition_datetime"],
                    pd.to_numeric(frame[column], errors="coerce"),
                    marker=".",
                    markersize=2.5,
                    linewidth=0,
                    color=colors[strip - 1],
                    label=f"strip {strip}",
                )
            axis.set_title(f"Plane {plane} — {family}")
            if plane == 1:
                axis.set_ylabel("Charge offset")
            if row == 0 and plane == 4:
                axis.legend(ncol=2, fontsize=8)
    format_time_axes(axes.ravel())
    fig.suptitle(f"{title}\nCharge pedestal offsets (Q_sum is the applied average)", fontsize=15)
    fig.savefig(destination, dpi=160)
    plt.close(fig)


def save_time_plot(
    frame: pd.DataFrame, destination: Path, title: str, family: str, display_name: str
) -> None:
    fig, axes = plt.subplots(1, 4, figsize=(19, 5), sharex=True, constrained_layout=True)
    colors = plt.get_cmap("tab10").colors
    for plane in PLANES:
        axis = axes[plane - 1]
        for strip in STRIPS:
            column = f"P{plane}_s{strip}_{family}"
            axis.plot(
                frame["acquisition_datetime"],
                pd.to_numeric(frame[column], errors="coerce"),
                marker=".",
                markersize=2.5,
                linewidth=0,
                color=colors[strip - 1],
                label=f"strip {strip}",
            )
        axis.set_title(f"Plane {plane}")
        if plane == 1:
            axis.set_ylabel("Time offset")
        if plane == 4:
            axis.legend(ncol=2, fontsize=8)
    format_time_axes(axes)
    fig.suptitle(f"{title}\n{display_name} offsets", fontsize=15)
    fig.savefig(destination, dpi=160)
    plt.close(fig)


def slewing_power_indices(frame: pd.DataFrame, family: str) -> list[int]:
    pattern = re.compile(rf"^P[1-4]_s[1-4]_T_slew_{family}__(\d+)$")
    return sorted({
        int(match.group(1))
        for column in frame.columns
        if (match := pattern.fullmatch(column)) is not None
    })


def save_slewing_parameter_plot(
    frame: pd.DataFrame, destination: Path, title: str
) -> bool:
    coefficient_indices = slewing_power_indices(frame, "coeffs")
    mean_indices = slewing_power_indices(frame, "basis_means")
    if not coefficient_indices:
        print("Warning: no persisted slewing coefficient columns were found.")
        return False

    rows: list[tuple[str, str, int]] = []
    rows.extend((f"Coefficient for power {index + 1}", "coeffs", index) for index in coefficient_indices)
    rows.extend((f"Basis mean for power {index + 1}", "basis_means", index) for index in mean_indices)
    rows.extend((("Fit-domain minimum", "domain", 0), ("Fit-domain maximum", "domain", 1)))
    fig, axes = plt.subplots(
        len(rows), 4, figsize=(19, max(8, 2.8 * len(rows))),
        sharex=True, constrained_layout=True, squeeze=False,
    )
    colors = plt.get_cmap("tab10").colors
    for row_index, (row_label, family, value_index) in enumerate(rows):
        for plane in PLANES:
            axis = axes[row_index, plane - 1]
            for strip in STRIPS:
                column = f"P{plane}_s{strip}_T_slew_{family}__{value_index}"
                if column not in frame:
                    continue
                axis.plot(
                    frame["acquisition_datetime"],
                    pd.to_numeric(frame[column], errors="coerce"),
                    marker=".", markersize=2.5, linewidth=0,
                    color=colors[strip - 1], label=f"strip {strip}",
                )
            axis.set_title(f"Plane {plane} — {row_label}")
            if plane == 1:
                axis.set_ylabel(row_label)
            if row_index == 0 and plane == 4:
                axis.legend(ncol=2, fontsize=8)
    format_time_axes(axes.ravel())
    fig.suptitle(
        f"{title}\nPer-channel slewing model parameters (gaps mean no fitted model)",
        fontsize=15,
    )
    fig.savefig(destination, dpi=160)
    plt.close(fig)
    return True


def add_calibration_availability_columns(frame: pd.DataFrame) -> pd.DataFrame:
    enriched = frame.copy()
    tsum_columns = [f"P{plane}_s{strip}_T_sum" for plane in PLANES for strip in STRIPS]
    slew_columns = [
        f"P{plane}_s{strip}_T_slew_coeffs__0" for plane in PLANES for strip in STRIPS
    ]
    enriched["T_sum_nonzero_channels"] = (
        enriched[tsum_columns].apply(pd.to_numeric, errors="coerce").abs() > 1e-12
    ).sum(axis=1)
    present_slew_columns = [column for column in slew_columns if column in enriched]
    enriched["T_slew_fitted_channels"] = (
        enriched[present_slew_columns].notna().sum(axis=1) if present_slew_columns else 0
    )
    return enriched


def save_calibration_availability_plot(
    frame: pd.DataFrame, destination: Path, title: str
) -> None:
    fig, axis = plt.subplots(figsize=(16, 5), constrained_layout=True)
    axis.plot(
        frame["acquisition_datetime"], frame["T_sum_nonzero_channels"],
        marker=".", markersize=3, linewidth=0,
        label="nonzero T_sum offset channels",
    )
    axis.plot(
        frame["acquisition_datetime"], frame["T_slew_fitted_channels"],
        marker=".", markersize=3, linewidth=0,
        label="channels with slewing fit",
    )
    axis.axhline(15, color="tab:blue", linestyle=":", linewidth=1.0,
                 label="expected T_sum: 15 nonzero + 1 reference")
    axis.axhline(16, color="tab:orange", linestyle=":", linewidth=1.0,
                 label="expected slewing: all 16 fitted")
    axis.set_ylim(-0.5, 16.8)
    axis.set_ylabel("Available channels")
    axis.set_title(f"{title}\nT_sum and slewing calibration availability")
    axis.legend()
    format_time_axes([axis])
    fig.savefig(destination, dpi=160)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    station_name, start, end = load_config(args.config)
    station_root = STATIONS_ROOT / station_name
    metadata_path = (
        station_root
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / "TASK_2"
        / "METADATA"
        / "task_2_metadata_calibration.csv"
    )
    lake_basenames = valid_parquet_lake_basenames(station_root)
    frame = add_calibration_availability_columns(
        select_metadata(
            metadata_path, start, end, allowed_basenames=lake_basenames,
        )
    )

    output_dir = station_root / "STAGE_1_PRODUCTS_TESTS" / TEST_OUTPUT_NAME
    output_dir.mkdir(parents=True, exist_ok=True)
    interval_tag = f"{start:%Y%m%d}_{end:%Y%m%d}"
    file_prefix = f"{station_name}_{interval_tag}"
    title = f"{station_name} | {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M}"

    selected_csv = output_dir / f"{file_prefix}_selected_metadata.csv"
    charge_png = output_dir / f"{file_prefix}_charge_offsets.png"
    tdif_png = output_dir / f"{file_prefix}_tdif_offsets.png"
    tsum_png = output_dir / f"{file_prefix}_tsum_offsets.png"
    slewing_png = output_dir / f"{file_prefix}_slewing_parameters.png"
    availability_png = output_dir / f"{file_prefix}_calibration_availability.png"
    frame.to_csv(selected_csv, index=False)
    save_charge_plot(frame, charge_png, title)
    save_time_plot(frame, tdif_png, title, "T_dif", "T_dif")
    save_time_plot(frame, tsum_png, title, "T_sum", "T_sum")
    slewing_plot_written = save_slewing_parameter_plot(frame, slewing_png, title)
    save_calibration_availability_plot(frame, availability_png, title)

    print(f"Selected {len(frame)} unique acquisition file(s).")
    print(f"Acquisition span: {frame['acquisition_datetime'].min()} to {frame['acquisition_datetime'].max()}")
    print(f"Outputs: {output_dir}")
    output_paths = [charge_png, tdif_png, tsum_png, availability_png, selected_csv]
    if slewing_plot_written:
        output_paths.insert(3, slewing_png)
    for path in output_paths:
        print(f"  {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
