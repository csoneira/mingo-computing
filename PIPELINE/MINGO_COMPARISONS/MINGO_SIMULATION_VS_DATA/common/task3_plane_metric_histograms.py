#!/usr/bin/env python3
"""Shared FILEvFILE histogram logic for Task-3 per-plane metrics."""

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
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.ANCILLARY.SIMULATION_VS_DATA_AND_VALIDATION.common.value_filters import (  # noqa: E402
    apply_config_value_filters,
    format_resolved_value_filters,
)


SIM_LABEL = "MINGO00 simulation"
REAL_COLOR = "#1b9e77"
SIM_COLOR = "#d95f02"


def format_efficiency_vector(values: Sequence[float]) -> str:
    return "[" + ", ".join(f"{float(value):.4f}" for value in values) + "]"


def normalize_case_value(value: object) -> object:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if not pd.isna(numeric):
        numeric = float(numeric)
        return int(numeric) if numeric.is_integer() else numeric
    return str(value)


def list_tt_case_values(sim_df: pd.DataFrame, real_df: pd.DataFrame) -> list[object]:
    if "list_tt" not in sim_df.columns or "list_tt" not in real_df.columns:
        raise KeyError("Config mode='cases' requires column 'list_tt' in both parquets.")
    combined = pd.concat([sim_df["list_tt"], real_df["list_tt"]], ignore_index=True).dropna()
    if combined.empty:
        raise ValueError("Config mode='cases' requested case plots, but no non-null list_tt values were found.")
    normalized = [normalize_case_value(value) for value in combined.tolist()]
    numeric_values = [value for value in normalized if isinstance(value, (int, float, np.integer, np.floating))]
    if len(numeric_values) == len(normalized):
        return sorted(set(float(value) if isinstance(value, np.floating) else int(value) if float(value).is_integer() else float(value) for value in numeric_values))
    return sorted(set(str(value) for value in normalized))


def filter_frame_for_case(frame: pd.DataFrame, case_value: object) -> pd.DataFrame:
    if "list_tt" not in frame.columns:
        raise KeyError("Config mode='cases' requires column 'list_tt' in both parquets.")
    case_numeric = pd.to_numeric(pd.Series([case_value]), errors="coerce").iloc[0]
    if not pd.isna(case_numeric):
        series = pd.to_numeric(frame["list_tt"], errors="coerce")
        return frame.loc[series == float(case_numeric)].copy()
    return frame.loc[frame["list_tt"].astype(str) == str(case_value)].copy()


def case_suffix(case_value: object) -> str:
    text = str(case_value).replace(" ", "_")
    return text.replace("/", "_")


def parse_metric_args(default_config_path: Path, description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config", default=str(default_config_path), help="Path to the JSON config file.")
    return parser.parse_args()


def resolve_output_dir(config: dict[str, object], selection: FilePairSelection) -> Path:
    return resolve_timestamped_pair_output_dir(config, selection)


def load_pair_frames(selection: FilePairSelection, metric_columns: Sequence[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    sim_df = pd.read_parquet(selection.reference_file_path)
    real_df = pd.read_parquet(selection.study_file_path)
    missing_sim = [column for column in metric_columns if column not in sim_df.columns]
    missing_real = [column for column in metric_columns if column not in real_df.columns]
    if missing_sim:
        raise KeyError(f"Reference parquet is missing required columns: {missing_sim}")
    if missing_real:
        raise KeyError(f"Study parquet is missing required columns: {missing_real}")
    return sim_df, real_df


def finite_values(frame: pd.DataFrame, column: str, *, exclude_zero_values: bool) -> np.ndarray:
    values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    if exclude_zero_values:
        values = values[values != 0]
    return values


def filtered_values(
    frame: pd.DataFrame,
    column: str,
    *,
    exclude_zero_values: bool,
    exclude_exact_values: Sequence[float],
    clip_max_value: float | None,
) -> np.ndarray:
    values = finite_values(frame, column, exclude_zero_values=exclude_zero_values)
    for excluded in exclude_exact_values:
        values = values[values != float(excluded)]
    if clip_max_value is not None:
        values = np.minimum(values, float(clip_max_value))
    return values


def histogram_edges_from_arrays(arrays: Sequence[np.ndarray], *, bins: int) -> np.ndarray | None:
    finite_arrays = [values for values in arrays if values.size]
    if not finite_arrays:
        return None
    combined = np.concatenate(finite_arrays)
    lower = float(np.nanmin(combined))
    upper = float(np.nanmax(combined))
    if lower == upper:
        lower -= 0.5
        upper += 0.5
    return np.linspace(lower, upper, int(bins) + 1)


def build_summary_table(
    selection: FilePairSelection,
    sim_df: pd.DataFrame,
    real_df: pd.DataFrame,
    *,
    metric_columns: Sequence[str],
    summary_column_name: str,
    exclude_zero_values: bool,
    exclude_exact_values: Sequence[float],
    clip_max_value: float | None,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for plane_idx, column in enumerate(metric_columns, start=1):
        sim_values = filtered_values(
            sim_df,
            column,
            exclude_zero_values=exclude_zero_values,
            exclude_exact_values=exclude_exact_values,
            clip_max_value=clip_max_value,
        )
        real_values = filtered_values(
            real_df,
            column,
            exclude_zero_values=exclude_zero_values,
            exclude_exact_values=exclude_exact_values,
            clip_max_value=clip_max_value,
        )
        rows.append(
            {
                "plane": plane_idx,
                summary_column_name: column,
                "simulation_count": int(sim_values.size),
                "study_count": int(real_values.size),
                "simulation_mean": float(np.mean(sim_values)) if sim_values.size else np.nan,
                "study_mean": float(np.mean(real_values)) if real_values.size else np.nan,
                "simulation_std": float(np.std(sim_values)) if sim_values.size else np.nan,
                "study_std": float(np.std(real_values)) if real_values.size else np.nan,
                "selection_eff_distance": float(selection.eff_distance),
                "study_filename_base": selection.study_filename_base,
                "reference_filename_base": selection.reference_filename_base,
            }
        )
    return pd.DataFrame(rows)


def plot_metric_histograms(
    selection: FilePairSelection,
    sim_df: pd.DataFrame,
    real_df: pd.DataFrame,
    *,
    metric_columns: Sequence[str],
    metric_title: str,
    value_unit: str,
    bins: int,
    density: bool,
    exclude_zero_values: bool,
    exclude_exact_values: Sequence[float],
    clip_max_value: float | None,
    y_axis_log_scale: bool,
    share_x_axis: bool,
    case_label: str | None,
    output_path: Path,
) -> Path:
    per_column_values: list[tuple[np.ndarray, np.ndarray]] = []
    for column in metric_columns:
        per_column_values.append(
            (
                filtered_values(
                    sim_df,
                    column,
                    exclude_zero_values=exclude_zero_values,
                    exclude_exact_values=exclude_exact_values,
                    clip_max_value=clip_max_value,
                ),
                filtered_values(
                    real_df,
                    column,
                    exclude_zero_values=exclude_zero_values,
                    exclude_exact_values=exclude_exact_values,
                    clip_max_value=clip_max_value,
                ),
            )
        )
    shared_edges = None
    if share_x_axis:
        shared_edges = histogram_edges_from_arrays(
            [values for pair in per_column_values for values in pair],
            bins=bins,
        )

    fig, axes = plt.subplots(2, 2, figsize=(13, 10), constrained_layout=True, sharex=share_x_axis)
    for plane_idx, ax in enumerate(axes.flat, start=1):
        column = metric_columns[plane_idx - 1]
        sim_values, real_values = per_column_values[plane_idx - 1]
        both = np.concatenate([sim_values, real_values]) if sim_values.size or real_values.size else np.array([], dtype=float)
        if both.size == 0:
            ax.set_title(f"Plane {plane_idx} | no finite values")
            ax.set_axis_off()
            continue
        edges = shared_edges
        if edges is None:
            edges = histogram_edges_from_arrays([sim_values, real_values], bins=bins)
        if edges is None:
            ax.set_title(f"Plane {plane_idx} | no finite values")
            ax.set_axis_off()
            continue
        ax.hist(sim_values, bins=edges, density=density, histtype="step", linewidth=1.6, color=SIM_COLOR, label=SIM_LABEL)
        ax.hist(
            real_values,
            bins=edges,
            density=density,
            histtype="step",
            linewidth=1.6,
            color=REAL_COLOR,
            label=selection.station_of_study_label,
        )
        ax.set_title(
            f"Plane {plane_idx} | d_eff={selection.eff_distance:.5f}\n"
            f"sim n={sim_values.size} | data n={real_values.size}"
        )
        ax.set_xlabel(f"{column} [{value_unit}]")
        ax.set_ylabel("Density" if density else "Counts")
        if y_axis_log_scale:
            ax.set_yscale("log", nonpositive="clip")
        ax.grid(alpha=0.25)
        ax.legend(loc="best")

    fig.suptitle(
        f"{metric_title} | {selection.station_of_study_label} {selection.study_filename_base} "
        f"vs MINGO00 {selection.reference_filename_base}\n"
        f"{selection.station_of_study_label} robust eff={format_efficiency_vector(selection.study_efficiencies)} | "
        f"MINGO00 robust eff={format_efficiency_vector(selection.reference_efficiencies)}\n"
        f"{'' if case_label is None else f'list_tt={case_label} | '}"
        f"z={list(selection.z_tuple)} | cos_n={selection.sim_cos_n} | flux={selection.sim_flux_cm2_min} | "
        f"trigger={selection.sim_trigger_combinations}",
        fontsize=12,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def run_metric_histogram_comparison(
    *,
    args: argparse.Namespace,
    metric_columns: Sequence[str],
    metric_title: str,
    summary_column_name: str,
    summary_csv_name: str,
    plot_name: str,
    value_unit: str,
) -> None:
    config = load_json_config(args.config)
    selection = build_filevfile_pair(config)
    out_dir = resolve_output_dir(config, selection)
    sim_df, real_df = load_pair_frames(selection, metric_columns)
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
    summary_csv_path = out_dir / summary_csv_name
    plot_path = out_dir / plot_name

    write_pair_summary(selection, summary_path)
    summary_table = build_summary_table(
        selection,
        sim_df,
        real_df,
        metric_columns=metric_columns,
        summary_column_name=summary_column_name,
        exclude_zero_values=exclude_zero_values,
        exclude_exact_values=exclude_exact_values,
        clip_max_value=clip_max_value,
    )
    summary_table.to_csv(summary_csv_path, index=False)
    saved_plots: list[Path] = []
    common_kwargs = {
        "metric_columns": metric_columns,
        "metric_title": metric_title,
        "value_unit": value_unit,
        "bins": int(config.get("histogram_bins", 80)),
        "density": bool(config.get("density", True)),
        "exclude_zero_values": exclude_zero_values,
        "exclude_exact_values": exclude_exact_values,
        "clip_max_value": clip_max_value,
        "y_axis_log_scale": y_axis_log_scale,
        "share_x_axis": bool(config.get("share_x_axis", False)),
    }
    if mode == "total":
        saved_plots.append(
            plot_metric_histograms(
                selection,
                sim_df,
                real_df,
                case_label=None,
                output_path=plot_path,
                **common_kwargs,
            )
        )
    else:
        for value in list_tt_case_values(sim_df, real_df):
            sim_case = filter_frame_for_case(sim_df, value)
            real_case = filter_frame_for_case(real_df, value)
            case_plot_path = plot_path.with_name(f"{plot_path.stem}__list_tt_{case_suffix(value)}{plot_path.suffix}")
            saved_plots.append(
                plot_metric_histograms(
                    selection,
                    sim_case,
                    real_case,
                    case_label=str(value),
                    output_path=case_plot_path,
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
    print(f"Saved per-plane summary CSV: {summary_csv_path}")
    for saved_plot in saved_plots:
        print(f"Saved plot: {saved_plot}")
