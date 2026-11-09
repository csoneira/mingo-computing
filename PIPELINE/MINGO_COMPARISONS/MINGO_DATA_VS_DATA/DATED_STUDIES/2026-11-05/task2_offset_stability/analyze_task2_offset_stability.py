#!/usr/bin/env python3
"""Plot Task-2 charge-offset stability and the latest sigmoid-applied files."""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


REPOSITORY_ROOT = next(
    (
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()
        and (parent / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS").is_dir()
    ),
    None,
)
if REPOSITORY_ROOT is None:
    raise RuntimeError(f"Could not locate repository root from {__file__}")
sys.path.insert(
    0,
    str(
        REPOSITORY_ROOT
        / "PIPELINE"
        / "MINGO_COMPARISONS"
        / "COMMON"
        / "STAGE_1_PRODUCTS_TESTS"
    ),
)
from comparison_paths import STATIONS_ROOT  # noqa: E402

ROOT = REPOSITORY_ROOT
STATION = STATIONS_ROOT / "MINGO01"
METADATA = STATION / "STAGE_1/EVENT_DATA/STEP_1/TASK_2/METADATA/task_2_metadata_calibration.csv"
RUN_LOG = ROOT / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS/MAIN_ANALYSIS/STAGE_1/EVENT_DATA/STEP_1/task2_offset_stability_reanalysis_2026-11-05.log"
OUT = Path(__file__).resolve().parent

METHOD_COLUMNS = {
    "Legacy derivative": "Q_offset_legacy_derivative",
    "Gamma CDF": "Q_offset_gamma_cdf",
    "Three-strip sigmoid": "Q_offset_crosstalk_sigmoid_3strip",
}
WIDTH_COLUMN = "Q_width_crosstalk_sigmoid_3strip_10_90"


def acquisition_datetime(filename_base: str) -> datetime | None:
    match = re.search(r"(\d{11})$", filename_base)
    if not match:
        return None
    stamp = match.group(1)
    try:
        return datetime(2000 + int(stamp[:2]), 1, 1) + timedelta(
            days=int(stamp[2:5]) - 1,
            hours=int(stamp[5:7]),
            minutes=int(stamp[7:9]),
            seconds=int(stamp[9:11]),
        )
    except ValueError:
        return None


def processed_basenames() -> set[str]:
    pattern = re.compile(r"^\[\d+/\d+\] START .* cleaned_(mi01\d{11})\.parquet$")
    names: set[str] = set()
    for line in RUN_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        match = pattern.match(line)
        if match:
            names.add(match.group(1))
    return names


def main() -> None:
    metadata = pd.read_csv(METADATA, low_memory=False)
    selected = processed_basenames()
    applied_method_columns = [
        column for column in metadata.columns
        if "Q_offset_method_applied_" in column
    ]
    sigmoid_applied_rows = (
        metadata[applied_method_columns]
        .eq("three-strip minimum-charge crosstalk sigmoid")
        .any(axis=1)
        if applied_method_columns
        else pd.Series(False, index=metadata.index)
    )
    sigmoid_applied_names = set(
        metadata.loc[sigmoid_applied_rows, "filename_base"].astype(str)
    )
    selected |= sigmoid_applied_names
    if not selected:
        raise SystemExit(
            f"No completed input names found in {RUN_LOG} or sigmoid-applied metadata."
        )

    metadata = metadata[metadata["filename_base"].astype(str).isin(selected)].copy()
    applied_method_columns = [
        column for column in metadata.columns
        if "Q_offset_method_applied_" in column
    ]
    metadata["sigmoid_reprocessed"] = (
        metadata[applied_method_columns]
        .eq("three-strip minimum-charge crosstalk sigmoid")
        .any(axis=1)
        if applied_method_columns
        else False
    )
    metadata["execution_dt"] = pd.to_datetime(
        metadata["execution_timestamp"], format="%Y-%m-%d_%H.%M.%S", errors="coerce"
    )
    metadata = metadata.sort_values("execution_dt").drop_duplicates(
        "filename_base", keep="last"
    )
    metadata["acquisition_dt"] = metadata["filename_base"].astype(str).map(
        acquisition_datetime
    )
    metadata = metadata.dropna(subset=["acquisition_dt"]).sort_values("acquisition_dt")
    if metadata.empty:
        raise SystemExit("No matching Task-2 calibration metadata rows were found.")

    colors = {
        "Legacy derivative": "black",
        "Gamma CDF": "tab:blue",
        "Three-strip sigmoid": "crimson",
    }
    channel_rows: list[dict[str, object]] = []
    offset_fig, offset_axes = plt.subplots(
        4, 8, figsize=(26, 14), sharex=True, squeeze=False
    )
    width_fig, width_axes = plt.subplots(
        4, 8, figsize=(26, 14), sharex=True, squeeze=False
    )
    offset_legend = [
        Line2D([], [], color=colors[name], marker="o", linestyle="-", label=name)
        for name in METHOD_COLUMNS
    ]
    offset_legend.append(
        Patch(
            facecolor="crimson",
            edgecolor="none",
            alpha=0.18,
            label="Three-strip sigmoid center ± half 10–90% width",
        )
    )
    offset_legend.append(
        Line2D(
            [], [], marker="D", linestyle="none", markersize=5,
            markerfacecolor="white", markeredgecolor="black",
            label="Files reprocessed with sigmoid applied",
        )
    )
    width_legend = [
        Line2D([], [], color="darkorange", marker="o", linestyle="none",
               label="Three-strip sigmoid 10–90% width")
    ]

    for plane in range(1, 5):
        for strip in range(1, 5):
            for side_idx, side in enumerate(("front", "back")):
                col = (strip - 1) * 2 + side_idx
                ax = offset_axes[plane - 1, col]
                wax = width_axes[plane - 1, col]
                channel = f"P{plane}/S{strip}/{side[0].upper()}"
                ax.set_title(channel, fontsize=8)
                wax.set_title(channel, fontsize=8)
                for method, prefix in METHOD_COLUMNS.items():
                    column = f"P{plane}_s{strip}_{prefix}_{side}"
                    if column not in metadata:
                        continue
                    values = pd.to_numeric(metadata[column], errors="coerce")
                    valid = values.notna()
                    if not valid.any():
                        continue
                    times = metadata.loc[valid, "acquisition_dt"]
                    vals = values.loc[valid].astype(float)
                    ax.plot(
                        times,
                        vals,
                        marker="o",
                        markersize=2.4,
                        linewidth=0.8,
                        color=colors[method],
                        alpha=0.82,
                        zorder=3,
                    )
                    applied = valid & metadata["sigmoid_reprocessed"]
                    if applied.any():
                        ax.scatter(
                            metadata.loc[applied, "acquisition_dt"],
                            values.loc[applied].astype(float),
                            marker="D",
                            s=15,
                            facecolors="white",
                            edgecolors=colors[method],
                            linewidths=0.7,
                            zorder=5,
                        )
                    seconds = np.array([(time - times.min()).total_seconds() for time in times])
                    slope = float(np.polyfit(seconds / 86400.0, vals, 1)[0]) if len(vals) > 1 else np.nan
                    channel_rows.append({
                        "channel": channel,
                        "method": method,
                        "n": int(len(vals)),
                        "median_adc": float(vals.median()),
                        "std_adc": float(vals.std(ddof=1)) if len(vals) > 1 else 0.0,
                        "p05_adc": float(vals.quantile(0.05)),
                        "p95_adc": float(vals.quantile(0.95)),
                        "first_adc": float(vals.iloc[0]),
                        "last_adc": float(vals.iloc[-1]),
                        "last_minus_first_adc": float(vals.iloc[-1] - vals.iloc[0]),
                        "linear_slope_adc_per_day": slope,
                    })

                width_col = f"P{plane}_s{strip}_{WIDTH_COLUMN}_{side}"
                if width_col in metadata:
                    width = pd.to_numeric(metadata[width_col], errors="coerce")
                    center_col = (
                        f"P{plane}_s{strip}_"
                        f"{METHOD_COLUMNS['Three-strip sigmoid']}_{side}"
                    )
                    center = pd.to_numeric(metadata[center_col], errors="coerce")
                    valid = width.notna() & center.notna() & (width > 0)
                    if valid.any():
                        times = metadata.loc[valid, "acquisition_dt"]
                        vals = width.loc[valid].astype(float)
                        centers = center.loc[valid].astype(float)
                        ax.fill_between(
                            times,
                            centers - vals / 2,
                            centers + vals / 2,
                            color="crimson",
                            alpha=0.18,
                            linewidth=0,
                            zorder=1,
                        )
                        wax.scatter(times, vals, s=9, color="darkorange", alpha=0.75)
                        applied = valid & metadata["sigmoid_reprocessed"]
                        if applied.any():
                            wax.scatter(
                                metadata.loc[applied, "acquisition_dt"],
                                width.loc[applied].astype(float),
                                marker="D",
                                s=15,
                                facecolors="white",
                                edgecolors="darkorange",
                                linewidths=0.7,
                                zorder=5,
                            )
                        channel_rows.append({
                            "channel": channel,
                            "method": "Three-strip sigmoid 10–90% width",
                            "n": int(len(vals)),
                            "median_adc": float(vals.median()),
                            "std_adc": float(vals.std(ddof=1)) if len(vals) > 1 else 0.0,
                            "p05_adc": float(vals.quantile(0.05)),
                            "p95_adc": float(vals.quantile(0.95)),
                            "first_adc": float(vals.iloc[0]),
                            "last_adc": float(vals.iloc[-1]),
                            "last_minus_first_adc": float(vals.iloc[-1] - vals.iloc[0]),
                            "linear_slope_adc_per_day": np.nan,
                        })
                for target in (ax, wax):
                    target.grid(True, alpha=0.2)
                    target.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
                    target.tick_params(axis="x", labelsize=6, rotation=0)
                    if col == 0:
                        target.set_ylabel(f"P{plane}\nADC", fontsize=8)
                    if plane == 4:
                        target.set_xlabel("Acquisition time", fontsize=7)

    first_time = metadata["acquisition_dt"].min()
    last_time = metadata["acquisition_dt"].max()
    offset_fig.suptitle(
        f"MINGO01 Task-2 charge offsets by method · {len(metadata)} files\n"
        f"{first_time:%Y-%m-%d %H:%M} to {last_time:%Y-%m-%d %H:%M} acquisition time",
        fontsize=13,
    )
    offset_fig.legend(handles=offset_legend, loc="upper center", ncol=3,
                      bbox_to_anchor=(0.5, 0.94), frameon=False)
    offset_fig.tight_layout(rect=(0.02, 0.02, 0.99, 0.89))
    offset_path = OUT / "task2_offset_stability_by_channel.png"
    offset_fig.savefig(offset_path, dpi=160)
    plt.close(offset_fig)

    width_fig.suptitle(
        f"MINGO01 three-strip crosstalk sigmoid width · {len(metadata)} files\n"
        f"10–90% transition width by channel over acquisition time",
        fontsize=13,
    )
    width_fig.legend(handles=width_legend, loc="upper center", ncol=1,
                     bbox_to_anchor=(0.5, 0.94), frameon=False)
    width_fig.tight_layout(rect=(0.02, 0.02, 0.99, 0.89))
    width_path = OUT / "task2_crosstalk_sigmoid_width_stability_by_channel.png"
    width_fig.savefig(width_path, dpi=160)
    plt.close(width_fig)

    summary_path = OUT / "task2_offset_stability_summary.csv"
    pd.DataFrame(channel_rows).to_csv(summary_path, index=False, float_format="%.6g")
    metadata_path = OUT / "task2_offset_stability_metadata_subset.csv"
    metadata.drop(columns=["execution_dt"], errors="ignore").to_csv(
        metadata_path, index=False
    )
    report_path = OUT / "README.md"
    report_path.write_text(
        "# Task-2 charge-offset stability\n\n"
        f"Analyzed {len(metadata)} unique MINGO01 input files from {first_time:%Y-%m-%d %H:%M} "
        f"to {last_time:%Y-%m-%d %H:%M} acquisition time.\n\n"
        f"Included {int(metadata['sigmoid_reprocessed'].sum())} files whose latest calibration metadata "
        "records the three-strip sigmoid as the applied production offset; those points use hollow diamonds.\n\n"
        "The per-channel offset plot compares the legacy derivative pedestal estimate, "
        "gamma-CDF x0, and the three-strip crosstalk sigmoid center. The offset time series "
        "connects file-level points in acquisition order. Its crimson fill is the sigmoid "
        "center ± half of its measured 10–90% transition width; the separate second plot "
        "shows that full width over time. See the CSV for per-channel median, spread, "
        "endpoints, and linear slope.\n\n"
        f"Source metadata: `{METADATA}`\n\n"
        f"Reanalysis log: `{RUN_LOG}`\n",
        encoding="utf-8",
    )
    print(f"Unique files analyzed: {len(metadata)} / {len(selected)}")
    print(f"Acquisition interval: {first_time} .. {last_time}")
    print(f"Offsets figure: {offset_path}")
    print(f"Sigmoid-width figure: {width_path}")
    print(f"Summary CSV: {summary_path}")
    print(f"Metadata subset: {metadata_path}")
    print(f"Report: {report_path}")
    for method in (*METHOD_COLUMNS.keys(), "Three-strip sigmoid 10–90% width"):
        subset = pd.DataFrame(channel_rows)
        subset = subset[subset["method"] == method]
        print(
            f"{method}: n={int(subset['n'].sum()) if not subset.empty else 0}, "
            f"median(channel medians)="
            f"{subset['median_adc'].median():.4g}" if not subset.empty else f"{method}: no valid values"
        )


if __name__ == "__main__":
    main()
