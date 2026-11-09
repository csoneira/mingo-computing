"""Lake-backed, latest-execution Task-2 calibration context for product tests."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from test_1_plot_calibration_offsets import (
    PLANES,
    STRIPS,
    acquisition_datetime,
    add_calibration_availability_columns,
    select_metadata,
    slewing_power_indices,
    valid_parquet_lake_basenames,
)


def _context_bounds(
    context: Any,
    selected_basenames: set[str],
    fallback_start: datetime,
    fallback_end: datetime,
) -> tuple[datetime, datetime, str]:
    """Resolve the calibration-history window independently of file selection."""
    text = str(context if context is not None else "full").strip().lower()
    if text == "full":
        return datetime(2000, 1, 1), datetime(2100, 1, 1), "full metadata history"

    compact = re.sub(r"\s+", "", text)
    week = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(?:weeks?|w)", compact)
    try:
        duration = (
            pd.Timedelta(weeks=float(week.group(1)))
            if week else pd.Timedelta(compact)
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"Invalid calibration context {context!r}; use full or a duration "
            "such as 1week, 3days, or 12h."
        ) from error
    if duration <= pd.Timedelta(0):
        raise ValueError("Calibration context duration must be positive.")

    selected_times = [acquisition_datetime(name) for name in selected_basenames]
    selected_times = [value for value in selected_times if value is not None]
    if selected_times:
        left = pd.Timestamp(min(selected_times)) - duration
        right = pd.Timestamp(max(selected_times)) + duration
    else:
        left = pd.Timestamp(fallback_start) - duration
        right = pd.Timestamp(fallback_end) + duration
    return left.to_pydatetime(), right.to_pydatetime(), f"selected block ± {text}"


def _selected_mask(frame: pd.DataFrame, basenames: set[str]) -> pd.Series:
    return frame["filename_base"].astype(str).str.strip().isin(basenames)


def _shade(axis: Any, frame: pd.DataFrame, mask: pd.Series, *, label: bool) -> None:
    times = frame.loc[mask, "acquisition_datetime"].dropna()
    if times.empty:
        return
    left, right = times.min(), times.max()
    if left == right:
        left -= pd.Timedelta(minutes=5)
        right += pd.Timedelta(minutes=5)
    axis.axvspan(
        left, right, color="gold", alpha=0.17, linewidth=0, zorder=0,
        label="selected acquisition block" if label else None,
    )


def _series(
    axis: Any,
    frame: pd.DataFrame,
    column: str,
    color: Any,
    line_label: str,
    mask: pd.Series,
    *,
    highlight_label: bool,
) -> None:
    values = pd.to_numeric(frame[column], errors="coerce")
    axis.plot(
        frame["acquisition_datetime"], values, marker=".", markersize=2.5,
        linewidth=0, color=color, label=line_label,
    )
    if bool(mask.any()):
        axis.scatter(
            frame.loc[mask, "acquisition_datetime"], values.loc[mask],
            s=30, marker="o", facecolor="crimson", edgecolor="white",
            linewidth=0.45, zorder=5,
            label="selected files" if highlight_label else None,
        )


def _format_axes(axes: Any) -> None:
    for axis in axes:
        locator = mdates.AutoDateLocator(minticks=3, maxticks=8)
        axis.xaxis.set_major_locator(locator)
        axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        axis.grid(True, alpha=0.25)
        axis.tick_params(axis="x", labelrotation=20)


def _charge_plot(
    frame: pd.DataFrame, destination: Path, title: str, mask: pd.Series,
) -> None:
    charge_families = ("Q_F", "Q_B")
    fig, axes = plt.subplots(
        len(charge_families), 4, figsize=(19, 8),
        sharex=True, constrained_layout=True,
    )
    colors = plt.get_cmap("tab10").colors
    for row, family in enumerate(charge_families):
        for plane in PLANES:
            axis = axes[row, plane - 1]
            legend_axis = row == 0 and plane == 4
            _shade(axis, frame, mask, label=legend_axis)
            for strip in STRIPS:
                _series(
                    axis, frame, f"P{plane}_s{strip}_{family}", colors[strip - 1],
                    f"strip {strip}", mask,
                    highlight_label=legend_axis and strip == 1,
                )
            axis.set_title(f"Plane {plane} — {family}")
            if plane == 1:
                axis.set_ylabel("Charge offset")
            if legend_axis:
                axis.legend(ncols=2, fontsize=8)
    _format_axes(axes.ravel())
    fig.suptitle(f"{title}\nCharge pedestal offsets (selected files in crimson)", fontsize=15)
    fig.savefig(destination, dpi=160)
    plt.close(fig)


def _time_plot(
    frame: pd.DataFrame,
    destination: Path,
    title: str,
    family: str,
    mask: pd.Series,
) -> None:
    fig, axes = plt.subplots(1, 4, figsize=(19, 5), sharex=True, constrained_layout=True)
    colors = plt.get_cmap("tab10").colors
    for plane in PLANES:
        axis = axes[plane - 1]
        legend_axis = plane == 4
        _shade(axis, frame, mask, label=legend_axis)
        for strip in STRIPS:
            _series(
                axis, frame, f"P{plane}_s{strip}_{family}", colors[strip - 1],
                f"strip {strip}", mask,
                highlight_label=legend_axis and strip == 1,
            )
        axis.set_title(f"Plane {plane}")
        if plane == 1:
            axis.set_ylabel("Time offset")
        if legend_axis:
            axis.legend(ncols=2, fontsize=8)
    _format_axes(axes)
    fig.suptitle(f"{title}\n{family} offsets (selected files in crimson)", fontsize=15)
    fig.savefig(destination, dpi=160)
    plt.close(fig)


def _qf_vs_qb_plot(
    frame: pd.DataFrame,
    destination: Path,
    title: str,
    mask: pd.Series,
) -> None:
    """Plot paired front/back charge pedestal offsets for every channel."""
    fig, axes = plt.subplots(
        1, 4, figsize=(19, 5), constrained_layout=True,
    )
    colors = plt.get_cmap("tab10").colors
    for plane in PLANES:
        axis = axes[plane - 1]
        plotted_values: list[pd.Series] = []
        for strip in STRIPS:
            qf = pd.to_numeric(
                frame[f"P{plane}_s{strip}_Q_F"], errors="coerce",
            )
            qb = pd.to_numeric(
                frame[f"P{plane}_s{strip}_Q_B"], errors="coerce",
            )
            valid = qf.notna() & qb.notna()
            axis.scatter(
                qf.loc[valid],
                qb.loc[valid],
                s=7,
                alpha=0.50,
                color=colors[strip - 1],
                label=f"strip {strip}",
            )
            highlighted = valid & mask
            if bool(highlighted.any()):
                axis.scatter(
                    qf.loc[highlighted],
                    qb.loc[highlighted],
                    s=14,
                    facecolors="none",
                    edgecolors="crimson",
                    linewidths=0.6,
                    zorder=5,
                )
            plotted_values.extend((qf.loc[valid], qb.loc[valid]))
        finite_values = pd.concat(plotted_values, ignore_index=True).dropna()
        if not finite_values.empty:
            lower, upper = float(finite_values.min()), float(finite_values.max())
            if lower == upper:
                lower -= 0.5
                upper += 0.5
            axis.plot(
                [lower, upper], [lower, upper],
                color="0.35", linestyle="--", linewidth=0.9,
                label="Q_F = Q_B",
            )
        axis.set(
            xlabel="Q_F calibration offset",
            ylabel="Q_B calibration offset",
            title=f"Plane {plane}",
        )
        axis.grid(True, alpha=0.25)
        if plane == 4:
            axis.legend(ncols=2, fontsize=8)
    fig.suptitle(
        f"{title}\nPaired Q_F versus Q_B calibration offsets "
        "(selected files outlined in crimson)",
        fontsize=15,
    )
    fig.savefig(destination, dpi=160)
    plt.close(fig)


def _slewing_plot(
    frame: pd.DataFrame, destination: Path, title: str, mask: pd.Series,
) -> bool:
    coefficients = slewing_power_indices(frame, "coeffs")
    means = slewing_power_indices(frame, "basis_means")
    if not coefficients:
        print("Warning: no persisted slewing coefficient columns were found.")
        return False
    rows: list[tuple[str, str, int]] = []
    rows.extend((f"Coefficient for power {index + 1}", "coeffs", index) for index in coefficients)
    rows.extend((f"Basis mean for power {index + 1}", "basis_means", index) for index in means)
    rows.extend((("Fit-domain minimum", "domain", 0), ("Fit-domain maximum", "domain", 1)))
    fig, axes = plt.subplots(
        len(rows), 4, figsize=(19, max(8, 2.8 * len(rows))), sharex=True,
        constrained_layout=True, squeeze=False,
    )
    colors = plt.get_cmap("tab10").colors
    for row_index, (row_label, family, value_index) in enumerate(rows):
        for plane in PLANES:
            axis = axes[row_index, plane - 1]
            legend_axis = row_index == 0 and plane == 4
            _shade(axis, frame, mask, label=legend_axis)
            for strip in STRIPS:
                column = f"P{plane}_s{strip}_T_slew_{family}__{value_index}"
                if column not in frame:
                    continue
                _series(
                    axis, frame, column, colors[strip - 1], f"strip {strip}", mask,
                    highlight_label=legend_axis and strip == 1,
                )
            axis.set_title(f"Plane {plane} — {row_label}")
            if plane == 1:
                axis.set_ylabel(row_label)
            if legend_axis:
                axis.legend(ncols=2, fontsize=8)
    _format_axes(axes.ravel())
    fig.suptitle(
        f"{title}\nPer-channel slewing parameters (selected files in crimson)", fontsize=15,
    )
    fig.savefig(destination, dpi=160)
    plt.close(fig)
    return True


def _availability_plot(
    frame: pd.DataFrame, destination: Path, title: str, mask: pd.Series,
) -> None:
    fig, axis = plt.subplots(figsize=(16, 5), constrained_layout=True)
    _shade(axis, frame, mask, label=True)
    axis.plot(
        frame["acquisition_datetime"], frame["T_sum_nonzero_channels"],
        marker=".", markersize=3, linewidth=0, label="nonzero T_sum offset channels",
    )
    axis.plot(
        frame["acquisition_datetime"], frame["T_slew_fitted_channels"],
        marker=".", markersize=3, linewidth=0, label="channels with slewing fit",
    )
    if bool(mask.any()):
        axis.scatter(
            frame.loc[mask, "acquisition_datetime"],
            frame.loc[mask, "T_sum_nonzero_channels"],
            s=32, color="crimson", edgecolor="white", linewidth=0.45, zorder=5,
            label="selected files",
        )
        axis.scatter(
            frame.loc[mask, "acquisition_datetime"],
            frame.loc[mask, "T_slew_fitted_channels"],
            s=32, color="crimson", edgecolor="white", linewidth=0.45, zorder=5,
        )
    axis.axhline(15, color="tab:blue", linestyle=":", linewidth=1,
                 label="expected T_sum: 15 nonzero + 1 reference")
    axis.axhline(16, color="tab:orange", linestyle=":", linewidth=1,
                 label="expected slewing: all 16 fitted")
    axis.set_ylim(-0.5, 16.8)
    axis.set_ylabel("Available channels")
    axis.set_title(f"{title}\nT_sum and slewing calibration availability")
    axis.legend()
    _format_axes([axis])
    fig.savefig(destination, dpi=160)
    plt.close(fig)


def generate_calibration_context(
    station_root: Path,
    start: datetime,
    end: datetime,
    output_dir: Path,
    title: str,
    selected_basenames: set[str],
    context: Any = "full",
) -> list[Path]:
    metadata_path = (
        station_root / "STAGE_1" / "EVENT_DATA" / "STEP_1" / "TASK_2"
        / "METADATA" / "task_2_metadata_calibration.csv"
    )
    context_start, context_end, context_label = _context_bounds(
        context, selected_basenames, start, end,
    )
    lake_basenames = valid_parquet_lake_basenames(station_root)
    frame = add_calibration_availability_columns(
        select_metadata(
            metadata_path, context_start, context_end,
            allowed_basenames=lake_basenames,
        )
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    for pattern in ("*.png", "*.csv"):
        for obsolete in output_dir.glob(pattern):
            obsolete.unlink()
    selected = {str(value).strip() for value in selected_basenames}
    mask = _selected_mask(frame, selected)
    matched = set(frame.loc[mask, "filename_base"].astype(str).str.strip())
    if missing := sorted(selected - matched):
        print("Warning: selected files absent from calibration metadata: " + ", ".join(missing))
    paths = [
        output_dir / "00_calibration_metadata.csv",
        output_dir / "01_charge_offsets.png",
        output_dir / "02_tdif_offsets.png",
        output_dir / "03_tsum_offsets.png",
        output_dir / "04_slewing_parameters.png",
        output_dir / "05_calibration_availability.png",
        output_dir / "08_qf_vs_qb_offsets.png",
    ]
    frame.to_csv(paths[0], index=False)
    plot_title = f"{title}\nCalibration context: {context_label}"
    _charge_plot(frame, paths[1], plot_title, mask)
    _time_plot(frame, paths[2], plot_title, "T_dif", mask)
    _time_plot(frame, paths[3], plot_title, "T_sum", mask)
    slewing_written = _slewing_plot(frame, paths[4], plot_title, mask)
    _availability_plot(frame, paths[5], plot_title, mask)
    _qf_vs_qb_plot(frame, paths[6], plot_title, mask)
    written = paths if slewing_written else [*paths[:4], *paths[5:]]
    print(
        f"Calibration context: {len(frame)} metadata point(s), "
        f"filtered to {len(lake_basenames)} valid Parquet Lake file(s); "
        f"{len(matched)}/{len(selected)} selected file(s) highlighted; "
        f"window={context_label} ({context_start:%Y-%m-%d %H:%M:%S} to "
        f"{context_end:%Y-%m-%d %H:%M:%S}) -> {output_dir}"
    )
    return written


def generate_calibration_temperature_plots(
    calibration_data_path: Path,
    environment_data_path: Path,
    output_dir: Path,
    title: str,
    selected_basenames: set[str],
    *,
    temperature_column: str = "sensors_int_Temperature_int",
    synchronization_tolerance: pd.Timedelta = pd.Timedelta("30min"),
) -> list[Path]:
    """Relate persisted calibration offsets to synchronized detector temperature."""
    calibration = pd.read_csv(calibration_data_path, low_memory=False)
    environment = pd.read_csv(environment_data_path, low_memory=False)
    if (
        "acquisition_datetime" not in calibration
        or "Time" not in environment
        or temperature_column not in environment
    ):
        print(
            "Warning: calibration-temperature plots skipped because synchronized "
            "calibration or temperature columns are unavailable."
        )
        return []
    calibration["acquisition_datetime"] = pd.to_datetime(
        calibration["acquisition_datetime"], errors="coerce",
    )
    environment["Time"] = pd.to_datetime(environment["Time"], errors="coerce")
    environment["temperature_c"] = pd.to_numeric(
        environment[temperature_column], errors="coerce",
    )
    calibration = calibration.dropna(subset=["acquisition_datetime"]).sort_values(
        "acquisition_datetime",
    )
    environment = environment.dropna(subset=["Time", "temperature_c"]).sort_values(
        "Time",
    )
    if calibration.empty or environment.empty:
        print("Warning: no synchronized calibration/temperature points to plot.")
        return []
    synchronized = pd.merge_asof(
        calibration,
        environment.loc[:, ["Time", "temperature_c"]],
        left_on="acquisition_datetime",
        right_on="Time",
        direction="nearest",
        tolerance=synchronization_tolerance,
    )
    synchronized = synchronized.dropna(subset=["temperature_c"])
    if synchronized.empty:
        print(
            "Warning: no calibration points have an internal-temperature sample "
            f"within {synchronization_tolerance}."
        )
        return []

    selected = {
        str(value).strip() for value in selected_basenames
    }
    selected_mask = synchronized["filename_base"].astype(str).str.strip().isin(
        selected,
    )
    colors = plt.get_cmap("tab10").colors

    def scatter_charge_families(
        destination: Path,
    ) -> None:
        fig, axes = plt.subplots(
            2, 4, figsize=(19, 9.2), sharex=True,
            constrained_layout=True, squeeze=False,
        )
        for row, current_family in enumerate(("Q_F", "Q_B")):
            for plane in PLANES:
                axis = axes[row, plane - 1]
                for strip in STRIPS:
                    column = f"P{plane}_s{strip}_{current_family}"
                    if column not in synchronized:
                        continue
                    values = pd.to_numeric(
                        synchronized[column], errors="coerce",
                    )
                    valid = values.notna()
                    axis.scatter(
                        synchronized.loc[valid, "temperature_c"],
                        values.loc[valid],
                        s=7,
                        alpha=0.48,
                        color=colors[strip - 1],
                        label=f"strip {strip}",
                    )
                    highlighted = valid & selected_mask
                    if bool(highlighted.any()):
                        axis.scatter(
                            synchronized.loc[highlighted, "temperature_c"],
                            values.loc[highlighted],
                            s=14,
                            facecolors="none",
                            edgecolors="crimson",
                            linewidths=0.65,
                            zorder=5,
                        )
                axis.set_title(
                    f"Plane {plane} — {current_family}"
                )
                axis.grid(True, alpha=0.25)
                if plane == 1:
                    axis.set_ylabel("Charge calibration offset")
                if row == 0 and plane == 4:
                    axis.legend(ncols=2, fontsize=8)
        for axis in axes[-1, :]:
            axis.set_xlabel("Internal temperature (°C)")
        fig.suptitle(
            f"{title}\nQ_F and Q_B calibration offsets versus synchronized "
            "internal temperature "
            f"(nearest within {synchronization_tolerance})",
            fontsize=15,
        )
        fig.savefig(destination, dpi=160)
        plt.close(fig)

    tsum_paths: list[Path] = []
    for plane in PLANES:
        for strip in STRIPS:
            column = f"P{plane}_s{strip}_T_sum"
            if column not in synchronized:
                continue
            values = pd.to_numeric(synchronized[column], errors="coerce")
            valid = values.notna()
            destination = (
                output_dir
                / f"06_tsum_p{plane}_s{strip}_offset_vs_temperature.png"
            )
            fig, axis = plt.subplots(
                figsize=(8, 6), constrained_layout=True,
            )
            axis.scatter(
                synchronized.loc[valid, "temperature_c"],
                values.loc[valid],
                s=7,
                alpha=0.50,
                color=colors[strip - 1],
                label="calibration points",
            )
            highlighted = valid & selected_mask
            if bool(highlighted.any()):
                axis.scatter(
                    synchronized.loc[highlighted, "temperature_c"],
                    values.loc[highlighted],
                    s=14,
                    facecolors="none",
                    edgecolors="crimson",
                    linewidths=0.6,
                    label="selected files",
                    zorder=5,
                )
            axis.set(
                xlabel="Internal temperature (°C)",
                ylabel="T_sum calibration offset",
                title=(
                    f"{title}\nPlane {plane}, strip {strip} T_sum offset "
                    "versus synchronized internal temperature"
                ),
            )
            axis.grid(True, alpha=0.25)
            axis.legend(fontsize=8)
            fig.savefig(destination, dpi=160)
            plt.close(fig)
            tsum_paths.append(destination)

    charge_path = output_dir / "07_qf_qb_offsets_vs_temperature.png"
    scatter_charge_families(charge_path)
    print(
        f"Calibration-temperature relationships: {len(synchronized):,} "
        f"synchronized calibration point(s) -> {output_dir}"
    )
    return [*tsum_paths, charge_path]
