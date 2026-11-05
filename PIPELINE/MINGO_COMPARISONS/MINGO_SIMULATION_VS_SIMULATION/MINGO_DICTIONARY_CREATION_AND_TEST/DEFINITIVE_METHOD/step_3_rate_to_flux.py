#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simple_common import (
    DEFAULT_CONFIG_PATH,
    apply_rate_to_flux_lines,
    ensure_output_dirs,
    ensure_rate_case_output_dirs,
    files_dir,
    load_config,
    ordered_plot_filename,
    plots_dir,
    prepare_plot_frame,
    rate_case_files_dir,
    rate_case_plots_dir,
    resolve_rate_specs,
    resolve_time_axis,
    write_json,
)

log = logging.getLogger("definitive_method.step3")


def _configure_logging() -> None:
    logging.basicConfig(format="[%(levelname)s] STEP_3 - %(message)s", level=logging.INFO, force=True)


def _resolve_plot_moving_average(config: dict) -> tuple[bool, int]:
    plots = config.get("plots", {})
    if not isinstance(plots, dict):
        plots = {}
    enabled = bool(plots.get("apply_moving_average", False))
    kernel = int(plots.get("moving_average_kernel", 5))
    if kernel < 1:
        raise ValueError("plots.moving_average_kernel must be >= 1.")
    return enabled, kernel


def _build_padded_fit_domain(x_values: pd.Series | np.ndarray, *, minimum_padding: float = 0.02) -> np.ndarray:
    finite_x = np.asarray(pd.to_numeric(x_values, errors="coerce"), dtype=float)
    finite_x = finite_x[np.isfinite(finite_x)]
    if finite_x.size == 0:
        return np.asarray([], dtype=float)
    x_min = float(np.min(finite_x))
    x_max = float(np.max(finite_x))
    spread = max(x_max - x_min, 0.0)
    padding = max(spread * 0.08, minimum_padding)
    return np.linspace(x_min - padding, x_max + padding, 240)


def _plot_rate_to_flux_calibration(
    reference_curve: pd.DataFrame,
    line_table: pd.DataFrame,
    output_path: Path,
    *,
    rate_column_name: str,
) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 8.5))
    x = pd.to_numeric(reference_curve["reference_rate_median"], errors="coerce")
    y = pd.to_numeric(reference_curve["flux_bin_center"], errors="coerce")
    ax.scatter(x, y, s=42, alpha=0.85, color="#1f77b4", label="Reference points")
    if not line_table.empty:
        line = line_table.iloc[0]
        x_dense = _build_padded_fit_domain(x)
        if x_dense.size:
            y_dense = float(line["slope"]) * x_dense + float(line["intercept"])
            ax.plot(
                x_dense,
                y_dense,
                color="#d62728",
                linewidth=1.8,
                label=(
                    f"{line.get('fit_method', 'linear_fit')} | "
                    f"slope={float(line['slope']):.4f}, intercept={float(line['intercept']):.4f}"
                ),
            )
    ax.set_title(f"Rate-to-flux calibration from the Step 1 reference curve\nrate column: {rate_column_name}")
    ax.set_xlabel("Reference corrected rate [Hz]")
    ax.set_ylabel("Simulated flux [cm^-2 min^-1]")
    ax.grid(alpha=0.25)
    ax.set_box_aspect(1.0)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _plot_flux_time_series(
    dataframe: pd.DataFrame,
    output_path: Path,
    *,
    apply_moving_average: bool,
    moving_average_kernel: int,
) -> str:
    ordered, x_values, x_label = resolve_time_axis(dataframe)
    ordered = prepare_plot_frame(
        ordered,
        ["corrected_flux_cm2_min"],
        apply_moving_average=apply_moving_average,
        moving_average_kernel=moving_average_kernel,
    )
    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.plot(
        x_values,
        ordered["corrected_flux_cm2_min"],
        marker="o",
        linewidth=0.8,
        markersize=2.8,
        color="#1f77b4",
    )
    ax.set_title(
        "Corrected flux over time"
        + (f" | moving average = {moving_average_kernel}" if apply_moving_average and moving_average_kernel > 1 else "")
    )
    ax.set_xlabel(x_label.replace("_", " "))
    ax.set_ylabel("Corrected flux [cm^-2 min^-1]")
    ax.grid(alpha=0.25)
    if pd.api.types.is_datetime64_any_dtype(x_values):
        fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return x_label


def _plot_all_rate_case_summary(
    case_payloads: list[dict[str, object]],
    output_path: Path,
    *,
    apply_moving_average: bool,
    moving_average_kernel: int,
) -> str | None:
    if not case_payloads:
        return None

    colors = plt.get_cmap("tab10")(np.linspace(0.0, 1.0, max(len(case_payloads), 1)))
    fig = plt.figure(figsize=(19, 11), constrained_layout=True)
    grid = fig.add_gridspec(3, 2, width_ratios=[1.55, 1.45], height_ratios=[1.0, 1.0, 1.0])
    scale_axis = fig.add_subplot(grid[0, 0])
    rate_axis = fig.add_subplot(grid[1, 0], sharex=scale_axis)
    flux_axis = fig.add_subplot(grid[2, 0], sharex=scale_axis)
    calibration_axis = fig.add_subplot(grid[:, 1])

    used_time_axis_label: str | None = None

    for color, payload in zip(colors, case_payloads):
        label = str(payload["rate_name"])
        step2_df = pd.read_csv(str(payload["step2_output_file"]), low_memory=False)
        step3_df = pd.read_csv(str(payload["step3_output_file"]), low_memory=False)
        reference_curve = pd.read_csv(str(payload["reference_curve_file"]), low_memory=False)
        line_table = pd.read_csv(str(payload["line_table_file"]), low_memory=False)

        ordered_step2, x_values, x_label = resolve_time_axis(step2_df)
        ordered_step2 = prepare_plot_frame(
            ordered_step2,
            ["corrected_rate_to_perfect_hz", "lut_scale_factor"],
            apply_moving_average=apply_moving_average,
            moving_average_kernel=moving_average_kernel,
        )
        ordered_step3, _, _ = resolve_time_axis(step3_df)
        ordered_step3 = prepare_plot_frame(
            ordered_step3,
            ["corrected_flux_cm2_min"],
            apply_moving_average=apply_moving_average,
            moving_average_kernel=moving_average_kernel,
        )
        used_time_axis_label = x_label

        scale_axis.plot(
            x_values,
            pd.to_numeric(ordered_step2["lut_scale_factor"], errors="coerce"),
            color=color,
            linewidth=1.2,
            marker="o",
            markersize=2.3,
            alpha=0.9,
            label=label,
        )
        rate_axis.plot(
            x_values,
            pd.to_numeric(ordered_step2["corrected_rate_to_perfect_hz"], errors="coerce"),
            color=color,
            linewidth=1.2,
            marker="o",
            markersize=2.3,
            alpha=0.9,
            label=label,
        )
        flux_axis.plot(
            x_values,
            pd.to_numeric(ordered_step3["corrected_flux_cm2_min"], errors="coerce"),
            color=color,
            linewidth=1.2,
            marker="o",
            markersize=2.3,
            alpha=0.9,
            label=label,
        )

        cal_x = pd.to_numeric(reference_curve["reference_rate_median"], errors="coerce")
        cal_y = pd.to_numeric(reference_curve["flux_bin_center"], errors="coerce")
        calibration_axis.scatter(
            cal_x,
            cal_y,
            color=color,
            alpha=0.5,
            s=28,
            edgecolors="none",
        )
        if not line_table.empty:
            line = line_table.iloc[0]
            x_dense = _build_padded_fit_domain(cal_x)
            if x_dense.size:
                y_dense = float(line["slope"]) * x_dense + float(line["intercept"])
                calibration_axis.plot(
                    x_dense,
                    y_dense,
                    color=color,
                    linewidth=1.8,
                    label=label,
                )

    scale_axis.set_title("LUT scale factor vs time")
    scale_axis.set_ylabel("Scale factor")
    scale_axis.grid(alpha=0.25)
    scale_axis.legend(fontsize=8, ncol=1, loc="best")

    rate_axis.set_title("Corrected rate to perfect vs time")
    rate_axis.set_ylabel("Corrected rate [Hz]")
    rate_axis.grid(alpha=0.25)

    flux_axis.set_title("Corrected flux vs time")
    flux_axis.set_ylabel("Corrected flux [cm^-2 min^-1]")
    flux_axis.set_xlabel((used_time_axis_label or "time").replace("_", " "))
    flux_axis.grid(alpha=0.25)

    calibration_axis.set_title("Rate-to-flux calibrations by rate case")
    calibration_axis.set_xlabel("Reference corrected rate [Hz]")
    calibration_axis.set_ylabel("Simulated flux [cm^-2 min^-1]")
    calibration_axis.grid(alpha=0.25)
    calibration_axis.set_box_aspect(1.0)
    calibration_axis.legend(fontsize=8, loc="best")

    if used_time_axis_label is not None:
        scale_axis.tick_params(axis="x", labelbottom=False)
        rate_axis.tick_params(axis="x", labelbottom=False)
        if pd.api.types.is_datetime64_any_dtype(x_values):
            fig.autofmt_xdate()

    fig.suptitle(
        "All rate-case summary"
        + (f" | moving average = {moving_average_kernel}" if apply_moving_average and moving_average_kernel > 1 else ""),
        fontsize=13,
    )
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return used_time_axis_label


def run(config_path: str | Path | None = None) -> Path:
    _configure_logging()
    config = load_config(config_path)
    ensure_output_dirs(config)
    rate_specs = resolve_rate_specs(config)
    apply_plot_moving_average, moving_average_kernel = _resolve_plot_moving_average(config)

    summary: list[dict[str, object]] = []
    aggregate_plot_inputs: list[dict[str, object]] = []
    last_output_path: Path | None = None

    for rate_spec in rate_specs:
        ensure_rate_case_output_dirs(config, rate_spec)
        case_files_dir = rate_case_files_dir(config, rate_spec)
        case_plots_dir = rate_case_plots_dir(config, rate_spec)

        step2_path = case_files_dir / "step2_real_with_lut.csv"
        reference_curve_path = case_files_dir / "step1_reference_curve.csv"
        line_path = case_files_dir / "step1_rate_to_flux_lines.csv"
        meta1_path = case_files_dir / "step1_lut_meta.json"
        output_path = case_files_dir / "step3_real_with_flux.csv"
        meta_path = case_files_dir / "step3_flux_meta.json"

        required_inputs = [step2_path, reference_curve_path, line_path]
        missing_inputs = [str(path) for path in required_inputs if not path.exists()]
        if missing_inputs:
            log.warning(
                "Skipping rate case %s because required inputs are missing: %s",
                rate_spec["name"],
                ", ".join(missing_inputs),
            )
            continue

        dataframe = pd.read_csv(step2_path, low_memory=False)
        if "corrected_rate_to_perfect_hz" not in dataframe.columns:
            raise ValueError(f"Step 3 requires corrected_rate_to_perfect_hz in {step2_path}.")
        reference_curve = pd.read_csv(reference_curve_path, low_memory=False)
        line_table = pd.read_csv(line_path, low_memory=False)

        dataframe["corrected_flux_cm2_min"], dataframe["corrected_flux_assignment_method"] = apply_rate_to_flux_lines(
            pd.to_numeric(dataframe["corrected_rate_to_perfect_hz"], errors="coerce"),
            line_table,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        dataframe.to_csv(output_path, index=False)
        last_output_path = output_path

        _plot_rate_to_flux_calibration(
            reference_curve,
            line_table,
            case_plots_dir / ordered_plot_filename(3, 1, "rate_to_flux_calibration"),
            rate_column_name=rate_spec["rate_column"],
        )
        time_axis_column_used = _plot_flux_time_series(
            dataframe,
            case_plots_dir / ordered_plot_filename(3, 2, "corrected_flux_time_series"),
            apply_moving_average=apply_plot_moving_average,
            moving_average_kernel=moving_average_kernel,
        )

        meta1 = {}
        if meta1_path.exists():
            meta1 = json.loads(meta1_path.read_text(encoding="utf-8"))
        payload = {
            "rate_name": rate_spec["name"],
            "rate_slug": rate_spec["slug"],
            "rate_input_column": rate_spec["rate_column"],
            "source_step2_file": str(step2_path),
            "source_reference_curve_file": str(reference_curve_path),
            "rate_to_flux_lines_file": str(line_path),
            "output_file": str(output_path),
            "row_count": int(len(dataframe)),
            "time_axis_column_used_for_plots": time_axis_column_used,
            "plot_apply_moving_average": apply_plot_moving_average,
            "plot_moving_average_kernel": moving_average_kernel,
            "line_table_rows": int(len(line_table)),
            "flux_assignment_method_counts": {
                str(key): int(value)
                for key, value in dataframe["corrected_flux_assignment_method"].value_counts(dropna=False).items()
            },
            "step1_meta": meta1,
        }
        write_json(meta_path, payload)
        summary.append(payload)
        aggregate_plot_inputs.append(
            {
                "rate_name": rate_spec["name"],
                "rate_slug": rate_spec["slug"],
                "step2_output_file": str(step2_path),
                "step3_output_file": str(output_path),
                "reference_curve_file": str(reference_curve_path),
                "line_table_file": str(line_path),
            }
        )

    aggregate_plot_path = plots_dir(config) / ordered_plot_filename(3, 3, "all_rate_case_summary")
    aggregate_time_axis_label = _plot_all_rate_case_summary(
        aggregate_plot_inputs,
        aggregate_plot_path,
        apply_moving_average=apply_plot_moving_average,
        moving_average_kernel=moving_average_kernel,
    )

    summary_path = files_dir(config) / "step3_flux_summary.json"
    write_json(
        summary_path,
        {
            "case_name": config.get("case_name"),
            "rate_cases": summary,
            "aggregate_plot_file": str(aggregate_plot_path),
            "aggregate_plot_time_axis_column": aggregate_time_axis_label,
        },
    )

    if last_output_path is None:
        raise ValueError("No Step 3 outputs were produced.")
    log.info("Wrote per-rate flux outputs under %s", last_output_path.parent.parent)
    return last_output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 3: convert each corrected rate case into corrected flux.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to config JSON file.")
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()
