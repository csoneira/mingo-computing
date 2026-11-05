#!/usr/bin/env python3
"""Shared FILEvFILE scatter logic for Task-2 T_dif vs Q_sum comparisons."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.ANCILLARY.SIMULATION_VS_DATA_AND_VALIDATION.common.file_pairing import (  # noqa: E402
    FilePairSelection,
    build_filevfile_pair,
    load_json_config,
    resolve_timestamped_pair_output_dir,
    write_pair_summary,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.ANCILLARY.SIMULATION_VS_DATA_AND_VALIDATION.common.task2_strip_metric_histograms import (  # noqa: E402
    case_suffix,
    case_values,
    filter_frame_for_case,
    format_efficiency_vector,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.ANCILLARY.SIMULATION_VS_DATA_AND_VALIDATION.common.value_filters import (  # noqa: E402
    apply_config_value_filters,
    format_resolved_value_filters,
)


SIM_LABEL = "MINGO00 simulation"
REAL_LABEL = "Data"
REAL_COLOR = "#1b9e77"
SIM_COLOR = "#d95f02"


def parse_scatter_args(default_config_path: Path, description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config", default=str(default_config_path), help="Path to the JSON config file.")
    return parser.parse_args()


def resolve_output_dir(config: dict[str, object], selection: FilePairSelection) -> Path:
    return resolve_timestamped_pair_output_dir(config, selection)


def load_pair_frames(selection: FilePairSelection, *, x_columns: Sequence[str], y_columns: Sequence[str], case_column: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    required_columns = list(x_columns) + list(y_columns)
    if case_column:
        required_columns.append(case_column)
    sim_df = pd.read_parquet(selection.reference_file_path)
    real_df = pd.read_parquet(selection.study_file_path)
    missing_sim = [column for column in required_columns if column not in sim_df.columns]
    missing_real = [column for column in required_columns if column not in real_df.columns]
    if missing_sim:
        raise KeyError(f"Reference parquet is missing required columns: {missing_sim}")
    if missing_real:
        raise KeyError(f"Study parquet is missing required columns: {missing_real}")
    return sim_df, real_df


def filtered_pair_values(
    frame: pd.DataFrame,
    x_column: str,
    y_column: str,
    *,
    exclude_zero_values: bool,
    exclude_exact_values: Sequence[float],
    clip_max_value: float | None,
) -> tuple[np.ndarray, np.ndarray]:
    x = pd.to_numeric(frame[x_column], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(frame[y_column], errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]
    if exclude_zero_values:
        nonzero = (x != 0) & (y != 0)
        x = x[nonzero]
        y = y[nonzero]
    for excluded in exclude_exact_values:
        keep = (x != float(excluded)) & (y != float(excluded))
        x = x[keep]
        y = y[keep]
    if clip_max_value is not None:
        y = np.minimum(y, float(clip_max_value))
    return x, y


def build_summary_table(
    selection: FilePairSelection,
    sim_df: pd.DataFrame,
    real_df: pd.DataFrame,
    *,
    x_columns: Sequence[str],
    y_columns: Sequence[str],
    exclude_zero_values: bool,
    exclude_exact_values: Sequence[float],
    clip_max_value: float | None,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for x_column, y_column in zip(x_columns, y_columns):
        plane = int(x_column[1])
        strip = int(x_column.rsplit("_", 1)[1])
        sim_x, sim_y = filtered_pair_values(
            sim_df,
            x_column,
            y_column,
            exclude_zero_values=exclude_zero_values,
            exclude_exact_values=exclude_exact_values,
            clip_max_value=clip_max_value,
        )
        real_x, real_y = filtered_pair_values(
            real_df,
            x_column,
            y_column,
            exclude_zero_values=exclude_zero_values,
            exclude_exact_values=exclude_exact_values,
            clip_max_value=clip_max_value,
        )
        rows.append(
            {
                "plane": plane,
                "strip": strip,
                "x_column": x_column,
                "y_column": y_column,
                "simulation_count": int(sim_x.size),
                "study_count": int(real_x.size),
                "simulation_x_mean": float(np.mean(sim_x)) if sim_x.size else np.nan,
                "study_x_mean": float(np.mean(real_x)) if real_x.size else np.nan,
                "simulation_y_mean": float(np.mean(sim_y)) if sim_y.size else np.nan,
                "study_y_mean": float(np.mean(real_y)) if real_y.size else np.nan,
                "selection_eff_distance": float(selection.eff_distance),
                "study_filename_base": selection.study_filename_base,
                "reference_filename_base": selection.reference_filename_base,
            }
        )
    return pd.DataFrame(rows)


def plot_tdif_vs_qsum(
    selection: FilePairSelection,
    sim_df: pd.DataFrame,
    real_df: pd.DataFrame,
    *,
    x_columns: Sequence[str],
    y_columns: Sequence[str],
    bins: int,
    exclude_zero_values: bool,
    exclude_exact_values: Sequence[float],
    clip_max_value: float | None,
    y_axis_log_scale: bool,
    case_label: str | None,
    output_path: Path,
) -> Path:
    fig, axes = plt.subplots(4, 4, figsize=(18, 16), constrained_layout=True)
    _ = bins
    for x_column, y_column in zip(x_columns, y_columns):
        plane = int(x_column[1])
        strip = int(x_column.rsplit("_", 1)[1])
        ax = axes[plane - 1, strip - 1]
        sim_x, sim_y = filtered_pair_values(
            sim_df,
            x_column,
            y_column,
            exclude_zero_values=exclude_zero_values,
            exclude_exact_values=exclude_exact_values,
            clip_max_value=clip_max_value,
        )
        real_x, real_y = filtered_pair_values(
            real_df,
            x_column,
            y_column,
            exclude_zero_values=exclude_zero_values,
            exclude_exact_values=exclude_exact_values,
            clip_max_value=clip_max_value,
        )
        if sim_x.size == 0 and real_x.size == 0:
            ax.set_title(f"P{plane} S{strip} | no finite values")
            ax.set_axis_off()
            continue
        ax.scatter(sim_x, sim_y, s=5, alpha=0.20, color=SIM_COLOR, edgecolors="none", label=SIM_LABEL)
        ax.scatter(real_x, real_y, s=5, alpha=0.20, color=REAL_COLOR, edgecolors="none", label=selection.station_of_study_label)
        ax.set_title(f"P{plane} S{strip}\nsim n={sim_x.size} | data n={real_x.size}")
        ax.set_xlabel(f"{x_column} [ns]")
        ax.set_ylabel(f"{y_column} [a.u.]")
        if y_axis_log_scale:
            ax.set_yscale("log", nonpositive="clip")
        ax.grid(alpha=0.25)
        ax.legend(loc="best", fontsize=8)

    fig.suptitle(
        f"Task-2 T_dif vs Q_sum | {selection.station_of_study_label} {selection.study_filename_base} "
        f"vs MINGO00 {selection.reference_filename_base}\n"
        f"{selection.station_of_study_label} robust eff={format_efficiency_vector(selection.study_efficiencies)} | "
        f"MINGO00 robust eff={format_efficiency_vector(selection.reference_efficiencies)}\n"
        f"{'' if case_label is None else f'case={case_label} | '}"
        f"z={list(selection.z_tuple)} | cos_n={selection.sim_cos_n} | flux={selection.sim_flux_cm2_min} | "
        f"trigger={selection.sim_trigger_combinations}",
        fontsize=13,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def run_tdif_vs_qsum_comparison(args: argparse.Namespace) -> None:
    config = load_json_config(args.config)
    selection = build_filevfile_pair(config)
    case_column = str(config.get("case_column", "cal_tt"))
    x_columns = [f"T{plane}_T_dif_{strip}" for plane in range(1, 5) for strip in range(1, 5)]
    y_columns = [f"Q{plane}_Q_sum_{strip}" for plane in range(1, 5) for strip in range(1, 5)]
    out_dir = resolve_output_dir(config, selection)
    sim_df, real_df = load_pair_frames(selection, x_columns=x_columns, y_columns=y_columns, case_column=case_column)
    sim_rows_before_filters = len(sim_df)
    real_rows_before_filters = len(real_df)
    sim_df, real_df, resolved_value_filters = apply_config_value_filters(sim_df, real_df, config.get("value_filters"))
    exclude_zero_values = bool(config.get("exclude_zero_values", True))
    exclude_exact_values = [float(value) for value in config.get("exclude_exact_values", [])]
    clip_max_raw = config.get("clip_max_value")
    clip_max_value = None if clip_max_raw in (None, "", "null", "None") else float(clip_max_raw)
    y_axis_log_scale = bool(config.get("y_axis_log_scale", False))
    mode = str(config.get("mode", "total")).strip().lower()
    if mode not in {"total", "cases"}:
        raise ValueError("Config key 'mode' must be 'total' or 'cases'.")

    summary_path = out_dir / "selected_pair_summary.json"
    summary_csv_path = out_dir / "task2_t_dif_vs_q_sum_summary.csv"
    plot_path = out_dir / "task2_t_dif_vs_q_sum_scatter.png"

    write_pair_summary(selection, summary_path)
    summary_table = build_summary_table(
        selection,
        sim_df,
        real_df,
        x_columns=x_columns,
        y_columns=y_columns,
        exclude_zero_values=exclude_zero_values,
        exclude_exact_values=exclude_exact_values,
        clip_max_value=clip_max_value,
    )
    summary_table.to_csv(summary_csv_path, index=False)

    saved_plots: list[Path] = []
    common_kwargs = {
        "x_columns": x_columns,
        "y_columns": y_columns,
        "bins": int(config.get("histogram_bins", 80)),
        "exclude_zero_values": exclude_zero_values,
        "exclude_exact_values": exclude_exact_values,
        "clip_max_value": clip_max_value,
        "y_axis_log_scale": y_axis_log_scale,
    }
    if mode == "total":
        saved_plots.append(
            plot_tdif_vs_qsum(
                selection,
                sim_df,
                real_df,
                case_label=None,
                output_path=plot_path,
                **common_kwargs,
            )
        )
    else:
        for value in case_values(sim_df, real_df, case_column=case_column):
            saved_plots.append(
                plot_tdif_vs_qsum(
                    selection,
                    filter_frame_for_case(sim_df, case_column=case_column, case_value=value),
                    filter_frame_for_case(real_df, case_column=case_column, case_value=value),
                    case_label=str(value),
                    output_path=plot_path.with_name(f"{plot_path.stem}__{case_column}_{case_suffix(value)}{plot_path.suffix}"),
                    **common_kwargs,
                )
            )

    print(f"Selected pair count in candidate pool: {selection.candidate_pair_count}")
    print(f"Study file: {selection.study_file_path}")
    print(f"Reference file: {selection.reference_file_path}")
    print(f"Efficiency distance: {selection.eff_distance:.6f}")
    if resolved_value_filters:
        print(f"Applied value filters: {format_resolved_value_filters(resolved_value_filters)}")
        print(
            f"Rows after value filters: simulation={len(sim_df)}/{sim_rows_before_filters} | "
            f"study={len(real_df)}/{real_rows_before_filters}"
        )
    print(f"Saved pair summary: {summary_path}")
    print(f"Saved per-strip summary CSV: {summary_csv_path}")
    for saved_plot in saved_plots:
        print(f"Saved plot: {saved_plot}")
