#!/usr/bin/env python3
"""Shared FILEvFILE histogram logic for Task-4 scalar fitted metrics."""

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
REAL_COLOR = "#1b9e77"
SIM_COLOR = "#d95f02"
VALID_PLOT_MODES = ("joined", "separated")


def parse_metric_args(default_config_path: Path, description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config", default=str(default_config_path), help="Path to the JSON config file.")
    return parser.parse_args()


def resolve_output_dir(config: dict[str, object], selection: FilePairSelection) -> Path:
    return resolve_timestamped_pair_output_dir(config, selection)


def load_pair_frames(selection: FilePairSelection, *, metric_column: str, case_column: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    sim_df = pd.read_parquet(selection.reference_file_path)
    real_df = pd.read_parquet(selection.study_file_path)
    if case_column and (case_column not in sim_df.columns or case_column not in real_df.columns):
        raise KeyError(f"Config mode='cases' requires column '{case_column}' in both parquets.")
    return sim_df, real_df


def has_metric_column(sim_df: pd.DataFrame, real_df: pd.DataFrame, metric_column: str) -> bool:
    return metric_column in sim_df.columns and metric_column in real_df.columns


def parse_plot_modes(raw: object) -> list[str]:
    if raw in (None, "", []):
        tokens = ["joined"]
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            tokens = ["joined"]
        else:
            if text.startswith("[") and text.endswith("]"):
                text = text[1:-1]
            tokens = [token.strip().strip("'\"") for token in text.split(",")]
    elif isinstance(raw, (list, tuple)):
        tokens = [str(token).strip() for token in raw]
    else:
        raise ValueError(
            "Config key 'plot_combined_mode' must be a string or a list containing "
            f"any of {list(VALID_PLOT_MODES)}."
        )

    modes: list[str] = []
    for token in tokens:
        if not token:
            continue
        mode = token.lower()
        if mode not in VALID_PLOT_MODES:
            raise ValueError(
                f"Unsupported plot_combined_mode '{token}'. Expected one of {list(VALID_PLOT_MODES)}."
            )
        if mode not in modes:
            modes.append(mode)
    if not modes:
        return ["joined"]
    return modes


def filtered_values(
    frame: pd.DataFrame,
    column: str,
    *,
    exclude_zero_values: bool,
    exclude_exact_values: Sequence[float],
    clip_max_value: float | None,
    apply_clip: bool = True,
) -> np.ndarray:
    values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    if exclude_zero_values:
        values = values[values != 0]
    for excluded in exclude_exact_values:
        values = values[values != float(excluded)]
    if apply_clip and clip_max_value is not None:
        values = np.minimum(values, float(clip_max_value))
    return values


def metric_histogram_edges(sim_values: np.ndarray, real_values: np.ndarray, *, bins: int) -> np.ndarray | None:
    both = np.concatenate([sim_values, real_values]) if sim_values.size or real_values.size else np.array([], dtype=float)
    if both.size == 0:
        return None
    lower = float(np.nanmin(both))
    upper = float(np.nanmax(both))
    if lower == upper:
        lower -= 0.5
        upper += 0.5
    return np.linspace(lower, upper, int(bins) + 1)


def apply_histogram_axes(
    ax: plt.Axes,
    *,
    x_label: str,
    y_label: str | None,
    edges: np.ndarray | None,
    y_axis_log_scale: bool,
    x_limit_line: float | None,
) -> None:
    if edges is not None:
        ax.set_xlim(float(edges[0]), float(edges[-1]))
    ax.set_xlabel(x_label)
    if y_label is not None:
        ax.set_ylabel(y_label)
    if y_axis_log_scale:
        ax.set_yscale("log", nonpositive="clip")
    if x_limit_line is not None:
        ax.axvline(float(x_limit_line), color="black", linestyle="--", linewidth=1.2, alpha=0.8)
    ax.grid(alpha=0.25)


def build_figure_title(
    selection: FilePairSelection,
    *,
    metric_title: str,
    case_column: str,
    case_label: str | None,
) -> str:
    return (
        f"{metric_title} | {selection.station_of_study_label} {selection.study_filename_base} "
        f"vs MINGO00 {selection.reference_filename_base}\n"
        f"{selection.station_of_study_label} robust eff={format_efficiency_vector(selection.study_efficiencies)} | "
        f"MINGO00 robust eff={format_efficiency_vector(selection.reference_efficiencies)}\n"
        f"{'' if case_label is None else f'{case_column}={case_label} | '}"
        f"z={list(selection.z_tuple)} | cos_n={selection.sim_cos_n} | flux={selection.sim_flux_cm2_min} | "
        f"trigger={selection.sim_trigger_combinations}"
    )


def mode_output_path(output_path: Path, plot_mode: str, *, total_modes: int) -> Path:
    if total_modes == 1 and plot_mode == "joined":
        return output_path
    return output_path.with_name(f"{output_path.stem}__{plot_mode}{output_path.suffix}")


def format_joined_threshold_text(
    *,
    sim_values_unclipped: np.ndarray,
    real_values_unclipped: np.ndarray,
    x_limit_line: float | None,
) -> str:
    if x_limit_line is None:
        return ""
    sim_pct_above = float(100.0 * np.mean(sim_values_unclipped > float(x_limit_line))) if sim_values_unclipped.size else np.nan
    real_pct_above = float(100.0 * np.mean(real_values_unclipped > float(x_limit_line))) if real_values_unclipped.size else np.nan
    return f" | > {float(x_limit_line):g}: sim={sim_pct_above:.1f}% data={real_pct_above:.1f}%"


def format_panel_threshold_text(values_unclipped: np.ndarray, x_limit_line: float | None) -> str:
    if x_limit_line is None:
        return ""
    pct_above = float(100.0 * np.mean(values_unclipped > float(x_limit_line))) if values_unclipped.size else np.nan
    return f" | > {float(x_limit_line):g}: {pct_above:.1f}%"


def build_summary_table(
    selection: FilePairSelection,
    sim_df: pd.DataFrame,
    real_df: pd.DataFrame,
    *,
    metric_column: str,
    exclude_zero_values: bool,
    exclude_exact_values: Sequence[float],
    clip_max_value: float | None,
    x_limit_line: float | None,
) -> pd.DataFrame:
    column_present = has_metric_column(sim_df, real_df, metric_column)
    if column_present:
        sim_values = filtered_values(
            sim_df,
            metric_column,
            exclude_zero_values=exclude_zero_values,
            exclude_exact_values=exclude_exact_values,
            clip_max_value=clip_max_value,
        )
        sim_values_unclipped = filtered_values(
            sim_df,
            metric_column,
            exclude_zero_values=exclude_zero_values,
            exclude_exact_values=exclude_exact_values,
            clip_max_value=clip_max_value,
            apply_clip=False,
        )
        real_values = filtered_values(
            real_df,
            metric_column,
            exclude_zero_values=exclude_zero_values,
            exclude_exact_values=exclude_exact_values,
            clip_max_value=clip_max_value,
        )
        real_values_unclipped = filtered_values(
            real_df,
            metric_column,
            exclude_zero_values=exclude_zero_values,
            exclude_exact_values=exclude_exact_values,
            clip_max_value=clip_max_value,
            apply_clip=False,
        )
    else:
        sim_values = np.array([], dtype=float)
        sim_values_unclipped = np.array([], dtype=float)
        real_values = np.array([], dtype=float)
        real_values_unclipped = np.array([], dtype=float)
    return pd.DataFrame(
        [
            {
                "metric_column": metric_column,
                "column_present_in_both_files": bool(column_present),
                "simulation_count": int(sim_values.size),
                "study_count": int(real_values.size),
                "simulation_mean": float(np.mean(sim_values)) if sim_values.size else np.nan,
                "study_mean": float(np.mean(real_values)) if real_values.size else np.nan,
                "simulation_std": float(np.std(sim_values)) if sim_values.size else np.nan,
                "study_std": float(np.std(real_values)) if real_values.size else np.nan,
                "x_limit_line": float(x_limit_line) if x_limit_line is not None else np.nan,
                "simulation_percent_above_x_limit": (
                    float(100.0 * np.mean(sim_values_unclipped > float(x_limit_line)))
                    if x_limit_line is not None and sim_values_unclipped.size
                    else np.nan
                ),
                "study_percent_above_x_limit": (
                    float(100.0 * np.mean(real_values_unclipped > float(x_limit_line)))
                    if x_limit_line is not None and real_values_unclipped.size
                    else np.nan
                ),
                "selection_eff_distance": float(selection.eff_distance),
                "study_filename_base": selection.study_filename_base,
                "reference_filename_base": selection.reference_filename_base,
            }
        ]
    )


def plot_joined_metric_histogram(
    selection: FilePairSelection,
    sim_values: np.ndarray,
    sim_values_unclipped: np.ndarray,
    real_values: np.ndarray,
    real_values_unclipped: np.ndarray,
    *,
    metric_title: str,
    x_label: str,
    bins: int,
    density: bool,
    y_axis_log_scale: bool,
    x_limit_line: float | None,
    case_column: str,
    case_label: str | None,
    output_path: Path,
) -> Path:
    edges = metric_histogram_edges(sim_values, real_values, bins=bins)
    fig, ax = plt.subplots(figsize=(10, 7), constrained_layout=True)
    if edges is None:
        ax.set_title("No finite values after filtering")
        ax.set_axis_off()
    else:
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
        apply_histogram_axes(
            ax,
            x_label=x_label,
            y_label="Density" if density else "Counts",
            edges=edges,
            y_axis_log_scale=y_axis_log_scale,
            x_limit_line=x_limit_line,
        )
        ax.legend(loc="best")
        ax.set_title(
            f"sim n={sim_values.size} | data n={real_values.size}"
            f"{format_joined_threshold_text(sim_values_unclipped=sim_values_unclipped, real_values_unclipped=real_values_unclipped, x_limit_line=x_limit_line)}"
        )

    fig.suptitle(
        build_figure_title(selection, metric_title=metric_title, case_column=case_column, case_label=case_label),
        fontsize=12,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_separated_metric_histogram(
    selection: FilePairSelection,
    sim_values: np.ndarray,
    sim_values_unclipped: np.ndarray,
    real_values: np.ndarray,
    real_values_unclipped: np.ndarray,
    *,
    metric_title: str,
    x_label: str,
    bins: int,
    density: bool,
    y_axis_log_scale: bool,
    x_limit_line: float | None,
    case_column: str,
    case_label: str | None,
    output_path: Path,
) -> Path:
    edges = metric_histogram_edges(sim_values, real_values, bins=bins)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6.5), sharex=True, sharey=True, constrained_layout=True)
    panels = [
        (axes[0], sim_values, sim_values_unclipped, SIM_LABEL, SIM_COLOR, "Density" if density else "Counts"),
        (axes[1], real_values, real_values_unclipped, selection.station_of_study_label, REAL_COLOR, None),
    ]
    for ax, values, values_unclipped, title, color, y_label in panels:
        if edges is None:
            ax.text(0.5, 0.5, "No finite values after filtering", transform=ax.transAxes, ha="center", va="center")
        else:
            ax.hist(values, bins=edges, density=density, histtype="step", linewidth=1.6, color=color)
        apply_histogram_axes(
            ax,
            x_label=x_label,
            y_label=y_label,
            edges=edges,
            y_axis_log_scale=y_axis_log_scale,
            x_limit_line=x_limit_line,
        )
        ax.set_title(f"{title} | n={values.size}{format_panel_threshold_text(values_unclipped, x_limit_line)}")

    fig.suptitle(
        build_figure_title(selection, metric_title=metric_title, case_column=case_column, case_label=case_label),
        fontsize=12,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_metric_histogram(
    selection: FilePairSelection,
    sim_df: pd.DataFrame,
    real_df: pd.DataFrame,
    *,
    metric_column: str,
    metric_title: str,
    value_unit: str,
    bins: int,
    density: bool,
    exclude_zero_values: bool,
    exclude_exact_values: Sequence[float],
    clip_max_value: float | None,
    y_axis_log_scale: bool,
    x_limit_line: float | None,
    case_column: str,
    case_label: str | None,
    output_path: Path,
    plot_mode: str,
) -> Path | None:
    if not has_metric_column(sim_df, real_df, metric_column):
        return None
    sim_values = filtered_values(
        sim_df,
        metric_column,
        exclude_zero_values=exclude_zero_values,
        exclude_exact_values=exclude_exact_values,
        clip_max_value=clip_max_value,
    )
    sim_values_unclipped = filtered_values(
        sim_df,
        metric_column,
        exclude_zero_values=exclude_zero_values,
        exclude_exact_values=exclude_exact_values,
        clip_max_value=clip_max_value,
        apply_clip=False,
    )
    real_values = filtered_values(
        real_df,
        metric_column,
        exclude_zero_values=exclude_zero_values,
        exclude_exact_values=exclude_exact_values,
        clip_max_value=clip_max_value,
    )
    real_values_unclipped = filtered_values(
        real_df,
        metric_column,
        exclude_zero_values=exclude_zero_values,
        exclude_exact_values=exclude_exact_values,
        clip_max_value=clip_max_value,
        apply_clip=False,
    )
    x_label = f"{metric_column} [{value_unit}]"
    if plot_mode == "joined":
        return plot_joined_metric_histogram(
            selection,
            sim_values,
            sim_values_unclipped,
            real_values,
            real_values_unclipped,
            metric_title=metric_title,
            x_label=x_label,
            bins=bins,
            density=density,
            y_axis_log_scale=y_axis_log_scale,
            x_limit_line=x_limit_line,
            case_column=case_column,
            case_label=case_label,
            output_path=output_path,
        )
    if plot_mode == "separated":
        return plot_separated_metric_histogram(
            selection,
            sim_values,
            sim_values_unclipped,
            real_values,
            real_values_unclipped,
            metric_title=metric_title,
            x_label=x_label,
            bins=bins,
            density=density,
            y_axis_log_scale=y_axis_log_scale,
            x_limit_line=x_limit_line,
            case_column=case_column,
            case_label=case_label,
            output_path=output_path,
        )
    raise ValueError(f"Unsupported plot mode '{plot_mode}'.")


def run_metric_histogram_comparison(
    *,
    args: argparse.Namespace,
    metric_column: str,
    metric_title: str,
    summary_csv_name: str,
    plot_name: str,
    value_unit: str,
) -> None:
    config = load_json_config(args.config)
    selection = build_filevfile_pair(config)
    case_column = str(config.get("case_column", "fit_tt"))
    out_dir = resolve_output_dir(config, selection)
    sim_df, real_df = load_pair_frames(selection, metric_column=metric_column, case_column=case_column)
    sim_rows_before_filters = len(sim_df)
    real_rows_before_filters = len(real_df)
    sim_df, real_df, resolved_value_filters = apply_config_value_filters(sim_df, real_df, config.get("value_filters"))
    exclude_zero_values = bool(config.get("exclude_zero_values", False))
    exclude_exact_values = [float(value) for value in config.get("exclude_exact_values", [])]
    clip_max_raw = config.get("clip_max_value")
    clip_max_value = None if clip_max_raw in (None, "", "null", "None") else float(clip_max_raw)
    x_limit_line_raw = config.get("x_limit_line")
    x_limit_line = None if x_limit_line_raw in (None, "", "null", "None") else float(x_limit_line_raw)
    y_axis_log_scale = bool(config.get("y_axis_log_scale", False))
    plot_modes = parse_plot_modes(config.get("plot_combined_mode", ["joined"]))
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
        metric_column=metric_column,
        exclude_zero_values=exclude_zero_values,
        exclude_exact_values=exclude_exact_values,
        clip_max_value=clip_max_value,
        x_limit_line=x_limit_line,
    )
    summary_table.to_csv(summary_csv_path, index=False)

    saved_plots: list[Path] = []
    common_kwargs = {
        "metric_column": metric_column,
        "metric_title": metric_title,
        "value_unit": value_unit,
        "bins": int(config.get("histogram_bins", 80)),
        "density": bool(config.get("density", True)),
        "exclude_zero_values": exclude_zero_values,
        "exclude_exact_values": exclude_exact_values,
        "clip_max_value": clip_max_value,
        "y_axis_log_scale": y_axis_log_scale,
        "x_limit_line": x_limit_line,
    }
    if mode == "total":
        for plot_mode in plot_modes:
            saved = plot_metric_histogram(
                selection,
                sim_df,
                real_df,
                case_column=case_column,
                case_label=None,
                output_path=mode_output_path(plot_path, plot_mode, total_modes=len(plot_modes)),
                plot_mode=plot_mode,
                **common_kwargs,
            )
            if saved is not None:
                saved_plots.append(saved)
    else:
        for value in case_values(sim_df, real_df, case_column=case_column):
            case_plot_path = plot_path.with_name(f"{plot_path.stem}__{case_column}_{case_suffix(value)}{plot_path.suffix}")
            for plot_mode in plot_modes:
                saved = plot_metric_histogram(
                    selection,
                    filter_frame_for_case(sim_df, case_column=case_column, case_value=value),
                    filter_frame_for_case(real_df, case_column=case_column, case_value=value),
                    case_column=case_column,
                    case_label=str(value),
                    output_path=mode_output_path(case_plot_path, plot_mode, total_modes=len(plot_modes)),
                    plot_mode=plot_mode,
                    **common_kwargs,
                )
                if saved is not None:
                    saved_plots.append(saved)

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
    print(f"Saved summary CSV: {summary_csv_path}")
    if saved_plots:
        for saved_plot in saved_plots:
            print(f"Saved plot: {saved_plot}")
    else:
        print(f"Metric column '{metric_column}' is not present in both files yet; no plot was written.")
