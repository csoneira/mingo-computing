#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simple_common import (
    CANONICAL_EFF_COLUMNS,
    DEFAULT_CONFIG_PATH,
    apply_lut_fallback_matches,
    ensure_output_dirs,
    ensure_rate_case_output_dirs,
    files_dir,
    load_config,
    ordered_plot_filename,
    quantize_efficiency_series,
    rate_case_files_dir,
    rate_case_plots_dir,
    resolve_rate_specs,
    resolve_time_axis,
    write_json,
)

log = logging.getLogger("definitive_method.step2")


def _configure_logging() -> None:
    logging.basicConfig(format="[%(levelname)s] STEP_2 - %(message)s", level=logging.INFO, force=True)


def _resolve_efficiency_plot_ylim(config: dict[str, Any]) -> tuple[float | None, float | None]:
    raw_ylim = config.get("plots", {}).get("efficiency_ylim", [None, 1.0])
    if not isinstance(raw_ylim, (list, tuple)) or len(raw_ylim) != 2:
        raise ValueError("plots.efficiency_ylim must be a two-element list like [null, 1.0].")
    low = None if raw_ylim[0] in (None, "", "null", "None") else float(raw_ylim[0])
    high = None if raw_ylim[1] in (None, "", "null", "None") else float(raw_ylim[1])
    if low is not None and high is not None and low >= high:
        raise ValueError("plots.efficiency_ylim must satisfy lower < upper when both are defined.")
    return low, high


def _resolve_scale_factor_smoothing(config: dict[str, Any]) -> dict[str, Any]:
    step2_config = config.get("step2", {})
    if not isinstance(step2_config, dict):
        step2_config = {}
    enabled = bool(step2_config.get("apply_scale_factor_smoothing", False))
    method = str(step2_config.get("scale_factor_smoothing_method", "moving_average")).strip().lower()
    kernel = int(step2_config.get("scale_factor_smoothing_kernel", 5))
    if method != "moving_average":
        raise ValueError("step2.scale_factor_smoothing_method currently supports only 'moving_average'.")
    if kernel < 1:
        raise ValueError("step2.scale_factor_smoothing_kernel must be >= 1.")
    return {
        "enabled": enabled,
        "method": method,
        "kernel": kernel,
    }


def _scale_factor_smoothing_label(settings: dict[str, Any]) -> str | None:
    if not bool(settings.get("enabled")):
        return None
    kernel = int(settings.get("kernel", 1))
    if kernel <= 1:
        return None
    return f"moving average n={kernel}"


def _apply_scale_factor_smoothing(dataframe: pd.DataFrame, settings: dict[str, Any]) -> pd.DataFrame:
    out = dataframe.copy()
    raw_scale = pd.to_numeric(out["lut_scale_factor"], errors="coerce")
    out["lut_scale_factor_raw"] = raw_scale
    if not bool(settings.get("enabled")) or int(settings.get("kernel", 1)) <= 1:
        out["lut_scale_factor_smoothed"] = raw_scale
        out["lut_scale_factor"] = raw_scale
        return out

    work = out.copy()
    work["_row_id"] = np.arange(len(work), dtype=int)
    ordered, _, _ = resolve_time_axis(work)
    ordered_raw = pd.to_numeric(ordered["lut_scale_factor_raw"], errors="coerce")
    ordered_smoothed = ordered_raw.rolling(
        window=int(settings["kernel"]),
        min_periods=1,
        center=True,
    ).mean()
    ordered_smoothed = ordered_smoothed.where(ordered_raw.notna(), np.nan)

    smoothed = pd.Series(np.nan, index=out.index, dtype=float)
    row_ids = ordered["_row_id"].to_numpy(dtype=int)
    smoothed.iloc[row_ids] = ordered_smoothed.to_numpy(dtype=float)
    out["lut_scale_factor_smoothed"] = smoothed
    out["lut_scale_factor"] = smoothed
    return out


def _plot_real_rate_correction(
    dataframe: pd.DataFrame,
    output_path: Path,
    *,
    rate_column_name: str,
    efficiency_plot_ylim: tuple[float | None, float | None],
    scale_factor_smoothing_label: str | None,
) -> str:
    ordered, x_values, x_label = resolve_time_axis(dataframe)
    numeric_columns = ["rate_hz", "corrected_rate_to_perfect_hz", *CANONICAL_EFF_COLUMNS]
    ordered[numeric_columns] = ordered[numeric_columns].apply(pd.to_numeric, errors="coerce")
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True, height_ratios=[2.0, 1.2])
    axes[0].plot(x_values, ordered["rate_hz"], marker="o", linewidth=0.35, markersize=3.0, label="Observed rate")
    axes[0].plot(
        x_values,
        ordered["corrected_rate_to_perfect_hz"],
        marker="o",
        linewidth=0.35,
        markersize=3.0,
        label="LUT-corrected rate",
    )
    axes[0].set_ylabel("Rate [Hz]")
    axes[0].set_title(
        "Observed and corrected real-data rate\n"
        f"rate column: {rate_column_name}"
        + (
            f" | corrected with smoothed scale factor ({scale_factor_smoothing_label})"
            if scale_factor_smoothing_label
            else ""
        )
    )
    axes[0].grid(alpha=0.25)
    axes[0].legend()

    plane_colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    for idx, column in enumerate(CANONICAL_EFF_COLUMNS):
        axes[1].plot(
            x_values,
            ordered[column],
            marker="o",
            linewidth=0.45,
            markersize=2.8,
            color=plane_colors[idx],
            label=f"Plane {idx + 1} eff",
        )
    axes[1].set_xlabel(x_label.replace("_", " "))
    axes[1].set_ylabel("Empirical efficiency")
    axes[1].set_ylim(bottom=efficiency_plot_ylim[0], top=efficiency_plot_ylim[1])
    axes[1].grid(alpha=0.25)
    axes[1].legend(ncol=2)
    if pd.api.types.is_datetime64_any_dtype(x_values):
        fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return x_label


def _plot_real_correction_diagnostics(
    dataframe: pd.DataFrame,
    output_path: Path,
    *,
    rate_column_name: str,
    scale_factor_smoothing_label: str | None,
) -> str:
    ordered, x_values, x_label = resolve_time_axis(dataframe)
    sequence = np.arange(len(ordered))
    ordered["lut_scale_factor_raw"] = pd.to_numeric(ordered["lut_scale_factor_raw"], errors="coerce")
    ordered["lut_scale_factor"] = pd.to_numeric(ordered["lut_scale_factor"], errors="coerce")
    ordered["lut_scale_factor_smoothed"] = pd.to_numeric(ordered["lut_scale_factor_smoothed"], errors="coerce")

    eff_values = ordered[CANONICAL_EFF_COLUMNS].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    lut_eff_values = ordered[[f"lut_{column}" for column in CANONICAL_EFF_COLUMNS]].apply(
        pd.to_numeric,
        errors="coerce",
    ).to_numpy(dtype=float)
    valid = np.isfinite(eff_values).all(axis=1) & np.isfinite(lut_eff_values).all(axis=1)
    lut_eff_distance = np.full(len(ordered), np.nan, dtype=float)
    if valid.any():
        lut_eff_distance[valid] = np.linalg.norm(eff_values[valid] - lut_eff_values[valid], axis=1)
    trust_score = np.clip(1.0 - (lut_eff_distance / 2.0), 0.0, 1.0)

    fig = plt.figure(figsize=(17, 9), constrained_layout=True)
    grid = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.15])
    observed_axis = fig.add_subplot(grid[0, 0])
    proximity_axis = fig.add_subplot(grid[0, 1])
    scale_axis = fig.add_subplot(grid[1, :])

    scatter = observed_axis.scatter(
        ordered["rate_hz"],
        ordered["corrected_rate_to_perfect_hz"],
        c=sequence,
        cmap="viridis",
        s=20,
        alpha=0.8,
    )
    finite_rates = pd.concat([ordered["rate_hz"], ordered["corrected_rate_to_perfect_hz"]], ignore_index=True).to_numpy(dtype=float)
    finite_rates = finite_rates[np.isfinite(finite_rates)]
    if finite_rates.size:
        low = float(np.min(finite_rates))
        high = float(np.max(finite_rates))
        observed_axis.plot([low, high], [low, high], linestyle="--", linewidth=1.2, color="black", alpha=0.7)
    observed_axis.set_title(f"Observed vs corrected rate\nrate column: {rate_column_name}")
    observed_axis.set_xlabel(f"Observed rate [Hz]\n({rate_column_name})")
    observed_axis.set_ylabel(f"Corrected rate [Hz]\n(from {rate_column_name})")
    observed_axis.grid(alpha=0.25)

    scale_axis.plot(
        x_values,
        ordered["lut_scale_factor_raw"],
        marker="o",
        linewidth=0.9,
        markersize=2.8,
        color="#8B1E3F",
        alpha=0.55,
        label="Raw LUT scale factor",
    )
    if scale_factor_smoothing_label:
        scale_axis.plot(
            x_values,
            ordered["lut_scale_factor_smoothed"],
            marker="o",
            linewidth=1.5,
            markersize=2.8,
            color="#111111",
            alpha=0.95,
            label=f"Smoothed scale factor ({scale_factor_smoothing_label})",
        )
    scale_axis.set_title(
        "Scale factor vs time"
        + (f" | {scale_factor_smoothing_label}" if scale_factor_smoothing_label else "")
    )
    scale_axis.set_xlabel(x_label.replace("_", " "))
    scale_axis.set_ylabel("Scale factor")
    scale_axis.grid(alpha=0.25)
    scale_axis.legend()

    proximity_axis.plot(
        x_values,
        lut_eff_distance,
        marker="o",
        linewidth=1.4,
        markersize=3.0,
        color="#1F6FEB",
        label="LUT efficiency distance",
    )
    proximity_axis.set_title(
        "LUT proximity / trust vs time"
    )
    proximity_axis.set_xlabel(x_label.replace("_", " "))
    proximity_axis.set_ylabel("Distance in eff space")
    proximity_axis.grid(alpha=0.25)

    trust_axis = proximity_axis.twinx()
    trust_axis.plot(
        x_values,
        trust_score,
        marker="s",
        linewidth=1.3,
        markersize=2.8,
        color="#E67E22",
        alpha=0.8,
        label="Trust score",
    )
    trust_axis.set_ylim(0.0, 1.05)
    trust_axis.set_ylabel("Trust [0-1]")
    lines, labels = proximity_axis.get_legend_handles_labels()
    extra_lines, extra_labels = trust_axis.get_legend_handles_labels()
    proximity_axis.legend(lines + extra_lines, labels + extra_labels, loc="upper right")

    if pd.api.types.is_datetime64_any_dtype(x_values):
        fig.autofmt_xdate()
    cbar = fig.colorbar(scatter, ax=[observed_axis, proximity_axis, scale_axis], shrink=0.92)
    cbar.set_label("Time-series order")
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return x_label


def _plot_lut_vs_real_efficiency_coverage(
    merged: pd.DataFrame,
    lut_dataframe: pd.DataFrame,
    output_path: Path,
    *,
    rate_column_name: str,
) -> None:
    support_columns = [f"support_eff_empirical_{idx}" for idx in range(1, 5)]
    if all(column in lut_dataframe.columns for column in support_columns):
        lut_plot_data = (
            lut_dataframe[support_columns]
            .rename(columns=dict(zip(support_columns, CANONICAL_EFF_COLUMNS)))
            .apply(pd.to_numeric, errors="coerce")
        )
    else:
        lut_plot_data = lut_dataframe[CANONICAL_EFF_COLUMNS].apply(pd.to_numeric, errors="coerce")

    fig, axes = plt.subplots(3, 3, figsize=(13, 13), constrained_layout=True)
    pair_layout = [
        [(0, 1), None, None],
        [(0, 2), (1, 2), None],
        [(0, 3), (1, 3), (2, 3)],
    ]
    for row in range(3):
        for col in range(3):
            ax = axes[row, col]
            pair = pair_layout[row][col]
            if pair is None:
                ax.axis("off")
                continue
            x_idx, y_idx = pair
            x_col = CANONICAL_EFF_COLUMNS[x_idx]
            y_col = CANONICAL_EFF_COLUMNS[y_idx]
            ax.scatter(
                pd.to_numeric(lut_plot_data[x_col], errors="coerce"),
                pd.to_numeric(lut_plot_data[y_col], errors="coerce"),
                s=30,
                alpha=0.55,
                color="#2ca02c",
                label="LUT rows",
                edgecolors="none",
            )
            ax.scatter(
                pd.to_numeric(merged[x_col], errors="coerce"),
                pd.to_numeric(merged[y_col], errors="coerce"),
                s=22,
                alpha=0.65,
                color="#1f77b4",
                label="Real rows",
                edgecolors="none",
            )
            ax.grid(alpha=0.2)
            ax.set_xlabel(x_col)
            ax.set_ylabel(y_col)
            if row == 0 and col == 0:
                ax.legend(fontsize=8, loc="upper left")
    fig.suptitle(
        "LUT coverage vs real-data empirical efficiencies\n"
        f"rate column: {rate_column_name}",
        y=1.02,
    )
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_real_rate_vs_efficiencies_2x2(
    merged: pd.DataFrame,
    output_path: Path,
    *,
    rate_column_name: str,
    efficiency_plot_ylim: tuple[float | None, float | None],
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharex=True, sharey=True, constrained_layout=True)
    rate_original = pd.to_numeric(merged["rate_hz"], errors="coerce")
    rate_corrected = pd.to_numeric(merged["corrected_rate_to_perfect_hz"], errors="coerce")
    eff_x_min_cfg, eff_x_max_cfg = efficiency_plot_ylim
    x_line_end = float(eff_x_max_cfg) if eff_x_max_cfg is not None else 1.01

    def add_linear_trend(ax: plt.Axes, x_values: pd.Series, y_values: pd.Series, color: str, label: str) -> None:
        valid = x_values.notna() & y_values.notna()
        if int(valid.sum()) < 2:
            return
        x = x_values.loc[valid].to_numpy(dtype=float)
        y = y_values.loc[valid].to_numpy(dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        x_start = float(np.nanmin(x))
        x_line = np.linspace(x_start, x_line_end, 120)
        y_line = slope * x_line + intercept
        ax.plot(x_line, y_line, linestyle="--", linewidth=1.6, color=color, alpha=0.8, label=label)

    all_y = pd.concat([rate_original, rate_corrected], ignore_index=True)
    finite_y = all_y[np.isfinite(all_y)]
    y_min = float(np.nanmin(finite_y)) if finite_y.size else 0.0
    y_max = float(np.nanmax(finite_y)) if finite_y.size else 1.0
    y_pad = max((y_max - y_min) * 0.05, 0.1)

    for idx, ax in enumerate(axes.flat):
        eff_col = CANONICAL_EFF_COLUMNS[idx]
        x_values = pd.to_numeric(merged[eff_col], errors="coerce")
        ax.scatter(x_values, rate_original, s=24, alpha=0.65, color="#1f77b4", label="Original rate", edgecolors="none")
        ax.scatter(x_values, rate_corrected, s=24, alpha=0.65, color="#ff7f0e", label="Corrected rate", edgecolors="none")
        add_linear_trend(ax, x_values, rate_original, "#1f77b4", "Original trend")
        add_linear_trend(ax, x_values, rate_corrected, "#ff7f0e", "Corrected trend")
        ax.axvline(1.0, linestyle=":", linewidth=1.5, color="black", alpha=0.8)
        ax.set_title(f"Rate vs {eff_col}")
        ax.set_xlabel(eff_col)
        ax.set_ylabel("Rate [Hz]")
        ax.grid(alpha=0.25)
        ax.set_xlim(left=eff_x_min_cfg, right=eff_x_max_cfg if eff_x_max_cfg is not None else x_line_end)
        ax.set_ylim(y_min - y_pad, y_max + y_pad)
        if idx == 0:
            ax.legend()
    fig.suptitle(
        "Original and corrected rate vs empirical efficiencies\n"
        f"rate column: {rate_column_name}",
        y=1.02,
    )
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _prepare_case_real_dataframe(
    real_df: pd.DataFrame,
    rate_spec: dict[str, Any],
    *,
    efficiency_bin_width: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    work = real_df.copy()
    work["rate_hz"] = pd.to_numeric(work[rate_spec["canonical_rate_column"]], errors="coerce")
    work = work.loc[np.isfinite(work["rate_hz"]) & (work["rate_hz"] > 0.0)].copy()
    if work.empty:
        raise ValueError(f"No positive-rate real rows remain for {rate_spec['name']}.")

    for column in CANONICAL_EFF_COLUMNS:
        work[column] = pd.to_numeric(work[column], errors="coerce")
        work[f"{column}__bin"] = quantize_efficiency_series(work[column], efficiency_bin_width)

    return work, {
        "input_row_count": int(len(real_df)),
        "positive_rate_row_count": int(len(work)),
    }


def run(config_path: str | Path | None = None) -> Path:
    _configure_logging()
    config = load_config(config_path)
    ensure_output_dirs(config)

    real_path = files_dir(config) / "step0_real_selected.csv"
    meta1_path = files_dir(config) / "step1_lut_meta.json"
    real_df = pd.read_csv(real_path, low_memory=False)
    meta1 = {}
    if meta1_path.exists():
        meta1 = json.loads(meta1_path.read_text(encoding="utf-8"))

    rate_specs = resolve_rate_specs(config)
    lut_config = config.get("lut", {})
    if not isinstance(lut_config, dict):
        lut_config = {}
    efficiency_bin_width = float(lut_config.get("efficiency_bin_width", 0.025))
    interpolation_mode = str(lut_config.get("interpolation_mode", "interpolate"))
    interpolation_k = int(lut_config.get("interpolation_k", 5))
    interpolation_power = float(lut_config.get("interpolation_power", 2.0))
    efficiency_plot_ylim = _resolve_efficiency_plot_ylim(config)
    scale_factor_smoothing = _resolve_scale_factor_smoothing(config)
    scale_factor_smoothing_label = _scale_factor_smoothing_label(scale_factor_smoothing)

    summary: list[dict[str, Any]] = []
    last_output_path: Path | None = None

    for rate_spec in rate_specs:
        ensure_rate_case_output_dirs(config, rate_spec)
        case_files_dir = rate_case_files_dir(config, rate_spec)
        case_plots_dir = rate_case_plots_dir(config, rate_spec)
        case_lut_path = case_files_dir / "step1_scale_factor_lut_detailed.csv"
        if not case_lut_path.exists():
            raise FileNotFoundError(f"Per-rate LUT not found for {rate_spec['name']}: {case_lut_path}")
        case_lut = pd.read_csv(case_lut_path, low_memory=False)
        lut_coordinate_columns = [f"eff_lut_{idx}" for idx in range(1, 5)]
        matching_lut = case_lut.copy()
        if all(column in matching_lut.columns for column in lut_coordinate_columns):
            matching_lut[CANONICAL_EFF_COLUMNS] = matching_lut[lut_coordinate_columns].to_numpy()

        case_real, filter_meta = _prepare_case_real_dataframe(
            real_df,
            rate_spec,
            efficiency_bin_width=efficiency_bin_width,
        )
        query_columns = [f"{column}__bin" for column in CANONICAL_EFF_COLUMNS]
        exact_lut = matching_lut[CANONICAL_EFF_COLUMNS + ["scale_factor"]].rename(
            columns={column: f"{column}__bin" for column in CANONICAL_EFF_COLUMNS}
        )
        merged = case_real.merge(exact_lut, on=query_columns, how="left")
        merged = merged.rename(columns={"scale_factor": "lut_scale_factor"})
        merged["lut_match_method"] = np.where(merged["lut_scale_factor"].notna(), "exact", pd.NA)
        merged["lut_match_distance"] = np.where(merged["lut_scale_factor"].notna(), 0.0, np.nan)
        for column in CANONICAL_EFF_COLUMNS:
            merged[f"lut_{column}"] = np.where(
                merged["lut_scale_factor"].notna(),
                pd.to_numeric(merged[f"{column}__bin"], errors="coerce"),
                np.nan,
            )

        merged = apply_lut_fallback_matches(
            merged,
            matching_lut[CANONICAL_EFF_COLUMNS + ["scale_factor"]],
            query_columns=query_columns,
            raw_columns=CANONICAL_EFF_COLUMNS,
            match_mode=interpolation_mode,
            interpolation_k=interpolation_k,
            interpolation_power=interpolation_power,
        )
        merged = _apply_scale_factor_smoothing(merged, scale_factor_smoothing)
        merged["corrected_rate_to_perfect_hz"] = pd.to_numeric(merged["rate_hz"], errors="coerce") * pd.to_numeric(
            merged["lut_scale_factor"],
            errors="coerce",
        )
        output_path = case_files_dir / "step2_real_with_lut.csv"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(output_path, index=False)
        last_output_path = output_path

        plot_1 = case_plots_dir / ordered_plot_filename(2, 1, "real_rate_correction")
        plot_2 = case_plots_dir / ordered_plot_filename(2, 2, "real_correction_diagnostics")
        plot_3 = case_plots_dir / ordered_plot_filename(2, 3, "lut_real_efficiency_coverage")
        plot_4 = case_plots_dir / ordered_plot_filename(2, 4, "real_rate_vs_efficiencies_2x2")

        time_axis_used = _plot_real_rate_correction(
            merged,
            plot_1,
            rate_column_name=rate_spec["rate_column"],
            efficiency_plot_ylim=efficiency_plot_ylim,
            scale_factor_smoothing_label=scale_factor_smoothing_label,
        )
        _plot_real_correction_diagnostics(
            merged,
            plot_2,
            rate_column_name=rate_spec["rate_column"],
            scale_factor_smoothing_label=scale_factor_smoothing_label,
        )
        _plot_lut_vs_real_efficiency_coverage(
            merged,
            matching_lut,
            plot_3,
            rate_column_name=rate_spec["rate_column"],
        )
        _plot_real_rate_vs_efficiencies_2x2(
            merged,
            plot_4,
            rate_column_name=rate_spec["rate_column"],
            efficiency_plot_ylim=efficiency_plot_ylim,
        )

        exact_count = int((merged["lut_match_method"] == "exact").sum())
        meta_path = case_files_dir / "step2_real_application_meta.json"
        meta_payload = {
            "rate_name": rate_spec["name"],
            "rate_slug": rate_spec["slug"],
            "rate_column": rate_spec["rate_column"],
            "canonical_rate_column": rate_spec["canonical_rate_column"],
            "source_real_file": str(real_path),
            "source_lut_file": str(case_lut_path),
            "output_file": str(output_path),
            "row_count": int(len(merged)),
            "exact_match_rows": exact_count,
            "fallback_rows": int(len(merged) - exact_count),
            "match_method_counts": {
                str(key): int(value) for key, value in merged["lut_match_method"].value_counts(dropna=False).items()
            },
            "time_axis_column_used_for_plots": time_axis_used,
            "scale_factor_smoothing_enabled": bool(scale_factor_smoothing.get("enabled")),
            "scale_factor_smoothing_method": str(scale_factor_smoothing.get("method")),
            "scale_factor_smoothing_kernel": int(scale_factor_smoothing.get("kernel", 1)),
            "scale_factor_column_applied": "lut_scale_factor",
            "scale_factor_raw_column": "lut_scale_factor_raw",
            "scale_factor_smoothed_column": "lut_scale_factor_smoothed",
            "filtering": filter_meta,
            "step1_meta": meta1,
        }
        write_json(meta_path, meta_payload)
        summary.append(meta_payload)

    summary_path = files_dir(config) / "step2_application_summary.json"
    write_json(
        summary_path,
        {
            "case_name": config.get("case_name"),
            "rate_cases": summary,
        },
    )

    if last_output_path is None:
        raise ValueError("No Step 2 outputs were produced.")
    log.info("Wrote per-rate LUT applications under %s", last_output_path.parent.parent)
    return last_output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 2: apply one LUT per selected rate to real data.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to config JSON file.")
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()
