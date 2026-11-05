#!/usr/bin/env python3
"""Shared FILEvFILE scatter logic for Task-4 fitted metric pairs."""

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
VALID_PLOT_MODES = ("joined", "separated_scatter", "separated_hexbin")


def parse_scatter_args(default_config_path: Path, description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config", default=str(default_config_path), help="Path to the JSON config file.")
    return parser.parse_args()


def resolve_output_dir(config: dict[str, object], selection: FilePairSelection) -> Path:
    return resolve_timestamped_pair_output_dir(config, selection)


def load_pair_frames(selection: FilePairSelection, *, x_column: str, y_column: str, case_column: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    sim_df = pd.read_parquet(selection.reference_file_path)
    real_df = pd.read_parquet(selection.study_file_path)
    if case_column and (case_column not in sim_df.columns or case_column not in real_df.columns):
        raise KeyError(f"Config mode='cases' requires column '{case_column}' in both parquets.")
    return sim_df, real_df


def has_metric_columns(sim_df: pd.DataFrame, real_df: pd.DataFrame, x_column: str, y_column: str) -> bool:
    return x_column in sim_df.columns and x_column in real_df.columns and y_column in sim_df.columns and y_column in real_df.columns


def filtered_pair_values(
    frame: pd.DataFrame,
    x_column: str,
    y_column: str,
    *,
    exclude_zero_values: bool,
    exclude_exact_values: Sequence[float],
    clip_x_max_value: float | None,
    clip_y_max_value: float | None,
    apply_clip: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    x = pd.to_numeric(frame[x_column], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(frame[y_column], errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]
    if exclude_zero_values:
        keep = (x != 0) & (y != 0)
        x = x[keep]
        y = y[keep]
    for excluded in exclude_exact_values:
        keep = (x != float(excluded)) & (y != float(excluded))
        x = x[keep]
        y = y[keep]
    if apply_clip:
        if clip_x_max_value is not None:
            x = np.minimum(x, float(clip_x_max_value))
        if clip_y_max_value is not None:
            y = np.minimum(y, float(clip_y_max_value))
    return x, y


def pair_correlation(x_values: np.ndarray, y_values: np.ndarray) -> float:
    if x_values.size < 2 or y_values.size < 2:
        return np.nan
    if np.allclose(x_values, x_values[0]) or np.allclose(y_values, y_values[0]):
        return np.nan
    return float(np.corrcoef(x_values, y_values)[0, 1])


def build_summary_table(
    selection: FilePairSelection,
    sim_df: pd.DataFrame,
    real_df: pd.DataFrame,
    *,
    x_column: str,
    y_column: str,
    exclude_zero_values: bool,
    exclude_exact_values: Sequence[float],
    clip_x_max_value: float | None,
    clip_y_max_value: float | None,
    x_limit_line: float | None,
    y_limit_line: float | None,
) -> pd.DataFrame:
    columns_present = has_metric_columns(sim_df, real_df, x_column, y_column)
    if columns_present:
        sim_x, sim_y = filtered_pair_values(
            sim_df,
            x_column,
            y_column,
            exclude_zero_values=exclude_zero_values,
            exclude_exact_values=exclude_exact_values,
            clip_x_max_value=clip_x_max_value,
            clip_y_max_value=clip_y_max_value,
        )
        sim_x_unclipped, sim_y_unclipped = filtered_pair_values(
            sim_df,
            x_column,
            y_column,
            exclude_zero_values=exclude_zero_values,
            exclude_exact_values=exclude_exact_values,
            clip_x_max_value=clip_x_max_value,
            clip_y_max_value=clip_y_max_value,
            apply_clip=False,
        )
        real_x, real_y = filtered_pair_values(
            real_df,
            x_column,
            y_column,
            exclude_zero_values=exclude_zero_values,
            exclude_exact_values=exclude_exact_values,
            clip_x_max_value=clip_x_max_value,
            clip_y_max_value=clip_y_max_value,
        )
        real_x_unclipped, real_y_unclipped = filtered_pair_values(
            real_df,
            x_column,
            y_column,
            exclude_zero_values=exclude_zero_values,
            exclude_exact_values=exclude_exact_values,
            clip_x_max_value=clip_x_max_value,
            clip_y_max_value=clip_y_max_value,
            apply_clip=False,
        )
    else:
        sim_x = np.array([], dtype=float)
        sim_y = np.array([], dtype=float)
        sim_x_unclipped = np.array([], dtype=float)
        sim_y_unclipped = np.array([], dtype=float)
        real_x = np.array([], dtype=float)
        real_y = np.array([], dtype=float)
        real_x_unclipped = np.array([], dtype=float)
        real_y_unclipped = np.array([], dtype=float)
    return pd.DataFrame(
        [
            {
                "x_column": x_column,
                "y_column": y_column,
                "columns_present_in_both_files": bool(columns_present),
                "simulation_count": int(sim_x.size),
                "study_count": int(real_x.size),
                "simulation_x_mean": float(np.mean(sim_x)) if sim_x.size else np.nan,
                "study_x_mean": float(np.mean(real_x)) if real_x.size else np.nan,
                "simulation_x_std": float(np.std(sim_x)) if sim_x.size else np.nan,
                "study_x_std": float(np.std(real_x)) if real_x.size else np.nan,
                "simulation_y_mean": float(np.mean(sim_y)) if sim_y.size else np.nan,
                "study_y_mean": float(np.mean(real_y)) if real_y.size else np.nan,
                "simulation_y_std": float(np.std(sim_y)) if sim_y.size else np.nan,
                "study_y_std": float(np.std(real_y)) if real_y.size else np.nan,
                "simulation_xy_correlation": pair_correlation(sim_x, sim_y),
                "study_xy_correlation": pair_correlation(real_x, real_y),
                "x_limit_line": float(x_limit_line) if x_limit_line is not None else np.nan,
                "y_limit_line": float(y_limit_line) if y_limit_line is not None else np.nan,
                "simulation_percent_above_x_limit": (
                    float(100.0 * np.mean(sim_x_unclipped > float(x_limit_line)))
                    if x_limit_line is not None and sim_x_unclipped.size
                    else np.nan
                ),
                "study_percent_above_x_limit": (
                    float(100.0 * np.mean(real_x_unclipped > float(x_limit_line)))
                    if x_limit_line is not None and real_x_unclipped.size
                    else np.nan
                ),
                "simulation_percent_above_y_limit": (
                    float(100.0 * np.mean(sim_y_unclipped > float(y_limit_line)))
                    if y_limit_line is not None and sim_y_unclipped.size
                    else np.nan
                ),
                "study_percent_above_y_limit": (
                    float(100.0 * np.mean(real_y_unclipped > float(y_limit_line)))
                    if y_limit_line is not None and real_y_unclipped.size
                    else np.nan
                ),
                "selection_eff_distance": float(selection.eff_distance),
                "study_filename_base": selection.study_filename_base,
                "reference_filename_base": selection.reference_filename_base,
            }
        ]
    )


def format_limit_text(
    *,
    sim_x: np.ndarray,
    sim_y: np.ndarray,
    real_x: np.ndarray,
    real_y: np.ndarray,
    x_limit_line: float | None,
    y_limit_line: float | None,
) -> str:
    parts: list[str] = []
    if x_limit_line is not None:
        sim_pct = float(100.0 * np.mean(sim_x > float(x_limit_line))) if sim_x.size else np.nan
        real_pct = float(100.0 * np.mean(real_x > float(x_limit_line))) if real_x.size else np.nan
        parts.append(f"{x_limit_line:g} on x: sim={sim_pct:.1f}% data={real_pct:.1f}%")
    if y_limit_line is not None:
        sim_pct = float(100.0 * np.mean(sim_y > float(y_limit_line))) if sim_y.size else np.nan
        real_pct = float(100.0 * np.mean(real_y > float(y_limit_line))) if real_y.size else np.nan
        parts.append(f"{y_limit_line:g} on y: sim={sim_pct:.1f}% data={real_pct:.1f}%")
    if not parts:
        return ""
    return " | " + " | ".join(parts)


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


def metric_axis_limits(sim_x: np.ndarray, sim_y: np.ndarray, real_x: np.ndarray, real_y: np.ndarray) -> tuple[float, float, float, float] | None:
    both_x = np.concatenate([sim_x, real_x]) if sim_x.size or real_x.size else np.array([], dtype=float)
    both_y = np.concatenate([sim_y, real_y]) if sim_y.size or real_y.size else np.array([], dtype=float)
    if both_x.size == 0 or both_y.size == 0:
        return None
    x_lower = float(np.nanmin(both_x))
    x_upper = float(np.nanmax(both_x))
    y_lower = float(np.nanmin(both_y))
    y_upper = float(np.nanmax(both_y))
    if x_lower == x_upper:
        x_lower -= 0.5
        x_upper += 0.5
    if y_lower == y_upper:
        y_lower -= 0.5
        y_upper += 0.5
    return (x_lower, x_upper, y_lower, y_upper)


def apply_common_axes(
    ax: plt.Axes,
    *,
    x_label: str,
    y_label: str | None,
    axis_limits: tuple[float, float, float, float] | None,
    x_axis_log_scale: bool,
    y_axis_log_scale: bool,
    x_limit_line: float | None,
    y_limit_line: float | None,
) -> None:
    if axis_limits is not None:
        x_lower, x_upper, y_lower, y_upper = axis_limits
        ax.set_xlim(x_lower, x_upper)
        ax.set_ylim(y_lower, y_upper)
    ax.set_xlabel(x_label)
    if y_label is not None:
        ax.set_ylabel(y_label)
    if x_axis_log_scale:
        ax.set_xscale("log")
    if y_axis_log_scale:
        ax.set_yscale("log")
    if x_limit_line is not None:
        ax.axvline(float(x_limit_line), color="black", linestyle="--", linewidth=1.2, alpha=0.8)
    if y_limit_line is not None:
        ax.axhline(float(y_limit_line), color="black", linestyle="--", linewidth=1.2, alpha=0.8)
    ax.grid(alpha=0.25)


def build_figure_title(
    selection: FilePairSelection,
    *,
    plot_title: str,
    case_column: str,
    case_label: str | None,
) -> str:
    return (
        f"{plot_title} | {selection.station_of_study_label} {selection.study_filename_base} "
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


def plot_joined_scatter(
    selection: FilePairSelection,
    sim_x: np.ndarray,
    sim_y: np.ndarray,
    real_x: np.ndarray,
    real_y: np.ndarray,
    *,
    plot_title: str,
    x_label: str,
    y_label: str,
    x_axis_log_scale: bool,
    y_axis_log_scale: bool,
    x_limit_line: float | None,
    y_limit_line: float | None,
    marker_size: float,
    marker_alpha: float,
    case_column: str,
    case_label: str | None,
    output_path: Path,
) -> Path:
    axis_limits = metric_axis_limits(sim_x, sim_y, real_x, real_y)
    fig, ax = plt.subplots(figsize=(10, 8), constrained_layout=True)
    if axis_limits is None:
        ax.set_title("No finite values after filtering")
        ax.set_axis_off()
    else:
        ax.scatter(sim_x, sim_y, s=marker_size, alpha=marker_alpha, color=SIM_COLOR, edgecolors="none", label=SIM_LABEL)
        ax.scatter(
            real_x,
            real_y,
            s=marker_size,
            alpha=marker_alpha,
            color=REAL_COLOR,
            edgecolors="none",
            label=selection.station_of_study_label,
        )
        apply_common_axes(
            ax,
            x_label=x_label,
            y_label=y_label,
            axis_limits=axis_limits,
            x_axis_log_scale=x_axis_log_scale,
            y_axis_log_scale=y_axis_log_scale,
            x_limit_line=x_limit_line,
            y_limit_line=y_limit_line,
        )
        ax.legend(loc="best")
        ax.set_title(
            f"sim n={sim_x.size} | data n={real_x.size}"
            f"{format_limit_text(sim_x=sim_x, sim_y=sim_y, real_x=real_x, real_y=real_y, x_limit_line=x_limit_line, y_limit_line=y_limit_line)}"
        )

    fig.suptitle(build_figure_title(selection, plot_title=plot_title, case_column=case_column, case_label=case_label), fontsize=12)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_separated_scatter(
    selection: FilePairSelection,
    sim_x: np.ndarray,
    sim_y: np.ndarray,
    real_x: np.ndarray,
    real_y: np.ndarray,
    *,
    plot_title: str,
    x_label: str,
    y_label: str,
    x_axis_log_scale: bool,
    y_axis_log_scale: bool,
    x_limit_line: float | None,
    y_limit_line: float | None,
    marker_size: float,
    marker_alpha: float,
    case_column: str,
    case_label: str | None,
    output_path: Path,
) -> Path:
    axis_limits = metric_axis_limits(sim_x, sim_y, real_x, real_y)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6.5), sharex=True, sharey=True, constrained_layout=True)
    panels = [
        (axes[0], sim_x, sim_y, SIM_LABEL, SIM_COLOR, y_label),
        (axes[1], real_x, real_y, selection.station_of_study_label, REAL_COLOR, None),
    ]
    for ax, x_values, y_values, title, color, panel_y_label in panels:
        if x_values.size == 0 or y_values.size == 0:
            ax.text(0.5, 0.5, "No finite values after filtering", transform=ax.transAxes, ha="center", va="center")
        else:
            ax.scatter(x_values, y_values, s=marker_size, alpha=marker_alpha, color=color, edgecolors="none")
        apply_common_axes(
            ax,
            x_label=x_label,
            y_label=panel_y_label,
            axis_limits=axis_limits,
            x_axis_log_scale=x_axis_log_scale,
            y_axis_log_scale=y_axis_log_scale,
            x_limit_line=x_limit_line,
            y_limit_line=y_limit_line,
        )
        ax.set_title(f"{title} | n={x_values.size}")

    fig.suptitle(build_figure_title(selection, plot_title=plot_title, case_column=case_column, case_label=case_label), fontsize=12)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_separated_hexbin(
    selection: FilePairSelection,
    sim_x: np.ndarray,
    sim_y: np.ndarray,
    real_x: np.ndarray,
    real_y: np.ndarray,
    *,
    plot_title: str,
    x_label: str,
    y_label: str,
    x_axis_log_scale: bool,
    y_axis_log_scale: bool,
    x_limit_line: float | None,
    y_limit_line: float | None,
    case_column: str,
    case_label: str | None,
    output_path: Path,
    density: bool,
    hexbin_grid_size: int,
    hexbin_min_count: int,
    hexbin_cmap: str,
) -> Path:
    axis_limits = metric_axis_limits(sim_x, sim_y, real_x, real_y)
    fig, axes = plt.subplots(1, 2, figsize=(15.5, 6.5), sharex=True, sharey=True, constrained_layout=True)
    panels = [
        (axes[0], sim_x, sim_y, SIM_LABEL, y_label),
        (axes[1], real_x, real_y, selection.station_of_study_label, None),
    ]
    collections: list[matplotlib.collections.PolyCollection] = []
    max_count = 0.0
    extent = None if axis_limits is None else (axis_limits[0], axis_limits[1], axis_limits[2], axis_limits[3])

    for ax, x_values, y_values, title, panel_y_label in panels:
        if x_values.size == 0 or y_values.size == 0:
            ax.text(0.5, 0.5, "No finite values after filtering", transform=ax.transAxes, ha="center", va="center")
        else:
            hexbin_kwargs = {
                "gridsize": int(hexbin_grid_size),
                "mincnt": int(hexbin_min_count),
                "extent": extent,
                "cmap": hexbin_cmap,
                "linewidths": 0.0,
            }
            if density:
                weights = np.full(x_values.size, 1.0 / float(x_values.size), dtype=float)
                collection = ax.hexbin(
                    x_values,
                    y_values,
                    C=weights,
                    reduce_C_function=np.sum,
                    **hexbin_kwargs,
                )
            else:
                collection = ax.hexbin(x_values, y_values, **hexbin_kwargs)
            collections.append(collection)
            if collection.get_array().size:
                max_count = max(max_count, float(np.nanmax(collection.get_array())))
        apply_common_axes(
            ax,
            x_label=x_label,
            y_label=panel_y_label,
            axis_limits=axis_limits,
            x_axis_log_scale=x_axis_log_scale,
            y_axis_log_scale=y_axis_log_scale,
            x_limit_line=x_limit_line,
            y_limit_line=y_limit_line,
        )
        ax.set_title(f"{title} | n={x_values.size}")

    if collections and max_count > 0:
        vmin = 0.0 if density else float(max(hexbin_min_count, 1))
        for collection in collections:
            collection.set_clim(vmin=vmin, vmax=max_count)
        colorbar_label = "Fraction of events per hexbin" if density else "Counts per hexbin"
        fig.colorbar(collections[0], ax=axes, shrink=0.9, label=colorbar_label)

    fig.suptitle(build_figure_title(selection, plot_title=plot_title, case_column=case_column, case_label=case_label), fontsize=12)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_metric_scatter(
    selection: FilePairSelection,
    sim_df: pd.DataFrame,
    real_df: pd.DataFrame,
    *,
    x_column: str,
    y_column: str,
    plot_title: str,
    x_unit: str,
    y_unit: str,
    exclude_zero_values: bool,
    exclude_exact_values: Sequence[float],
    clip_x_max_value: float | None,
    clip_y_max_value: float | None,
    x_axis_log_scale: bool,
    y_axis_log_scale: bool,
    x_limit_line: float | None,
    y_limit_line: float | None,
    marker_size: float,
    marker_alpha: float,
    density: bool,
    case_column: str,
    case_label: str | None,
    output_path: Path,
    plot_mode: str,
    hexbin_grid_size: int,
    hexbin_min_count: int,
    hexbin_cmap: str,
) -> Path | None:
    if not has_metric_columns(sim_df, real_df, x_column, y_column):
        return None
    sim_x, sim_y = filtered_pair_values(
        sim_df,
        x_column,
        y_column,
        exclude_zero_values=exclude_zero_values,
        exclude_exact_values=exclude_exact_values,
        clip_x_max_value=clip_x_max_value,
        clip_y_max_value=clip_y_max_value,
    )
    real_x, real_y = filtered_pair_values(
        real_df,
        x_column,
        y_column,
        exclude_zero_values=exclude_zero_values,
        exclude_exact_values=exclude_exact_values,
        clip_x_max_value=clip_x_max_value,
        clip_y_max_value=clip_y_max_value,
    )
    x_label = f"{x_column} [{x_unit}]"
    y_label = f"{y_column} [{y_unit}]"

    if plot_mode == "joined":
        return plot_joined_scatter(
            selection,
            sim_x,
            sim_y,
            real_x,
            real_y,
            plot_title=plot_title,
            x_label=x_label,
            y_label=y_label,
            x_axis_log_scale=x_axis_log_scale,
            y_axis_log_scale=y_axis_log_scale,
            x_limit_line=x_limit_line,
            y_limit_line=y_limit_line,
            marker_size=marker_size,
            marker_alpha=marker_alpha,
            case_column=case_column,
            case_label=case_label,
            output_path=output_path,
        )
    if plot_mode == "separated_scatter":
        return plot_separated_scatter(
            selection,
            sim_x,
            sim_y,
            real_x,
            real_y,
            plot_title=plot_title,
            x_label=x_label,
            y_label=y_label,
            x_axis_log_scale=x_axis_log_scale,
            y_axis_log_scale=y_axis_log_scale,
            x_limit_line=x_limit_line,
            y_limit_line=y_limit_line,
            marker_size=marker_size,
            marker_alpha=marker_alpha,
            case_column=case_column,
            case_label=case_label,
            output_path=output_path,
        )
    if plot_mode == "separated_hexbin":
        return plot_separated_hexbin(
            selection,
            sim_x,
            sim_y,
            real_x,
            real_y,
            plot_title=plot_title,
            x_label=x_label,
            y_label=y_label,
            x_axis_log_scale=x_axis_log_scale,
            y_axis_log_scale=y_axis_log_scale,
            x_limit_line=x_limit_line,
            y_limit_line=y_limit_line,
            case_column=case_column,
            case_label=case_label,
            output_path=output_path,
            density=density,
            hexbin_grid_size=hexbin_grid_size,
            hexbin_min_count=hexbin_min_count,
            hexbin_cmap=hexbin_cmap,
        )
    raise ValueError(f"Unsupported plot mode '{plot_mode}'.")


def run_metric_scatter_comparison(
    *,
    args: argparse.Namespace,
    x_column: str,
    y_column: str,
    plot_title: str,
    summary_csv_name: str,
    plot_name: str,
    x_unit: str,
    y_unit: str,
) -> None:
    config = load_json_config(args.config)
    selection = build_filevfile_pair(config)
    case_column = str(config.get("case_column", "fit_tt"))
    out_dir = resolve_output_dir(config, selection)
    sim_df, real_df = load_pair_frames(selection, x_column=x_column, y_column=y_column, case_column=case_column)
    sim_rows_before_filters = len(sim_df)
    real_rows_before_filters = len(real_df)
    sim_df, real_df, resolved_value_filters = apply_config_value_filters(sim_df, real_df, config.get("value_filters"))
    exclude_zero_values = bool(config.get("exclude_zero_values", False))
    exclude_exact_values = [float(value) for value in config.get("exclude_exact_values", [])]
    clip_x_max_raw = config.get("clip_x_max_value")
    clip_x_max_value = None if clip_x_max_raw in (None, "", "null", "None") else float(clip_x_max_raw)
    clip_y_max_raw = config.get("clip_y_max_value")
    clip_y_max_value = None if clip_y_max_raw in (None, "", "null", "None") else float(clip_y_max_raw)
    x_limit_line_raw = config.get("x_limit_line")
    x_limit_line = None if x_limit_line_raw in (None, "", "null", "None") else float(x_limit_line_raw)
    y_limit_line_raw = config.get("y_limit_line")
    y_limit_line = None if y_limit_line_raw in (None, "", "null", "None") else float(y_limit_line_raw)
    x_axis_log_scale = bool(config.get("x_axis_log_scale", False))
    y_axis_log_scale = bool(config.get("y_axis_log_scale", False))
    marker_size = float(config.get("marker_size", 5.0))
    marker_alpha = float(config.get("marker_alpha", 0.20))
    density = bool(config.get("density", False))
    plot_modes = parse_plot_modes(config.get("plot_combined_mode", ["joined"]))
    hexbin_grid_size = int(config.get("hexbin_grid_size", 45))
    hexbin_min_count = int(config.get("hexbin_min_count", 1))
    hexbin_cmap = str(config.get("hexbin_cmap", "viridis"))
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
        x_column=x_column,
        y_column=y_column,
        exclude_zero_values=exclude_zero_values,
        exclude_exact_values=exclude_exact_values,
        clip_x_max_value=clip_x_max_value,
        clip_y_max_value=clip_y_max_value,
        x_limit_line=x_limit_line,
        y_limit_line=y_limit_line,
    )
    summary_table.to_csv(summary_csv_path, index=False)

    saved_plots: list[Path] = []
    common_kwargs = {
        "x_column": x_column,
        "y_column": y_column,
        "plot_title": plot_title,
        "x_unit": x_unit,
        "y_unit": y_unit,
        "exclude_zero_values": exclude_zero_values,
        "exclude_exact_values": exclude_exact_values,
        "clip_x_max_value": clip_x_max_value,
        "clip_y_max_value": clip_y_max_value,
        "x_axis_log_scale": x_axis_log_scale,
        "y_axis_log_scale": y_axis_log_scale,
        "x_limit_line": x_limit_line,
        "y_limit_line": y_limit_line,
        "marker_size": marker_size,
        "marker_alpha": marker_alpha,
        "density": density,
        "hexbin_grid_size": hexbin_grid_size,
        "hexbin_min_count": hexbin_min_count,
        "hexbin_cmap": hexbin_cmap,
    }
    if mode == "total":
        for plot_mode in plot_modes:
            saved = plot_metric_scatter(
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
                saved = plot_metric_scatter(
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
        print(
            f"Metric columns '{x_column}' and '{y_column}' are not present in both files yet; "
            "no plot was written."
        )
