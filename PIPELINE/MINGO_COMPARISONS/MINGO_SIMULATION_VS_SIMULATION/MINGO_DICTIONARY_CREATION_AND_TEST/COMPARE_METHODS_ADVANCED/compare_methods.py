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

ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT_DIR / "OUTPUTS"
FILES_DIR = OUTPUT_DIR / "FILES"
PLOTS_DIR = OUTPUT_DIR / "PLOTS"
DEFAULT_CONFIG_PATH = ROOT_DIR / "config.json"

log = logging.getLogger("compare_methods_advanced")


def _configure_logging() -> None:
    logging.basicConfig(format="[%(levelname)s] COMPARE - %(message)s", level=logging.INFO, force=True)


def ensure_output_dirs() -> None:
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path or DEFAULT_CONFIG_PATH).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["_config_path"] = str(config_path)
    config["_config_dir"] = str(config_path.parent)
    return config


def resolve_path(config: dict[str, Any], raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (Path(config["_config_dir"]) / path).resolve()


def cfg_path(config: dict[str, Any], *keys: str) -> Path:
    value: Any = config
    for key in keys:
        value = value[key]
    return resolve_path(config, value)


def _normalize_join_keys(config: dict[str, Any]) -> list[str]:
    raw = config.get("comparison", {}).get("join_keys", ["filename_base", "file_timestamp_utc"])
    if not isinstance(raw, list) or not raw:
        raise ValueError("comparison.join_keys must be a non-empty JSON list.")
    return [str(value) for value in raw]


def _normalize_optional_str(value: Any) -> str | None:
    if value in (None, "", "null", "None"):
        return None
    text = str(value).strip()
    return text or None


def _normalize_scatter_axis_limits(config: dict[str, Any]) -> tuple[float, float] | None:
    raw = config.get("comparison", {}).get("scatter_axis_limits")
    if raw in (None, "", "null", "None"):
        return None
    if not isinstance(raw, list) or len(raw) != 2:
        raise ValueError("comparison.scatter_axis_limits must be a JSON list like [0.0, 4.0].")
    lower = float(raw[0])
    upper = float(raw[1])
    if not np.isfinite(lower) or not np.isfinite(upper) or upper <= lower:
        raise ValueError("comparison.scatter_axis_limits must satisfy finite upper > lower.")
    return lower, upper


def _normalize_histogram_bins(config: dict[str, Any]) -> int:
    return int(config.get("comparison", {}).get("delta_histogram_bins", 36))


def _normalize_histogram_zscore_limit(config: dict[str, Any]) -> float | None:
    raw = config.get("comparison", {}).get("delta_histogram_zscore_limit", 3.0)
    if raw in (None, "", "null", "None"):
        return None
    value = float(raw)
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError("comparison.delta_histogram_zscore_limit must be a positive number or null.")
    return value


def _prefixed_columns(
    dataframe: pd.DataFrame,
    *,
    prefix: str,
    preserve_columns: list[str],
) -> pd.DataFrame:
    rename_map = {
        column: f"{prefix}{column}"
        for column in dataframe.columns
        if column not in preserve_columns
    }
    return dataframe.rename(columns=rename_map)


def _normalize_time_join_column(dataframe: pd.DataFrame, column: str) -> pd.Series:
    parsed = pd.to_datetime(dataframe[column], errors="coerce", utc=True)
    if parsed.isna().any():
        raise ValueError(f"Could not parse all rows in join timestamp column {column!r}.")
    return parsed


def _add_normalized_join_columns(dataframe: pd.DataFrame, join_keys: list[str]) -> tuple[pd.DataFrame, list[str]]:
    work = dataframe.copy()
    normalized_join_keys: list[str] = []
    for column in join_keys:
        if column not in work.columns:
            raise ValueError(f"Join key {column!r} is missing from dataframe.")
        normalized_column = f"__join__{column}"
        if column.endswith("_timestamp_utc"):
            work[normalized_column] = _normalize_time_join_column(work, column)
        else:
            work[normalized_column] = work[column].astype(str)
        normalized_join_keys.append(normalized_column)
    return work, normalized_join_keys


def _check_duplicate_keys(dataframe: pd.DataFrame, join_key_columns: list[str], label: str) -> None:
    duplicated = dataframe.duplicated(subset=join_key_columns, keep=False)
    count = int(duplicated.sum())
    if count <= 0:
        return
    duplicates = dataframe.loc[duplicated, join_key_columns].head(10).to_dict(orient="records")
    raise ValueError(
        f"{label} contains {count} duplicated join-key rows. Examples: {duplicates}"
    )


def _load_method_frame(
    path: Path,
    *,
    required_columns: list[str],
    optional_columns: list[str],
    label: str,
) -> pd.DataFrame:
    header = list(pd.read_csv(path, nrows=0).columns)
    missing_required = [column for column in required_columns if column not in header]
    if missing_required:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing_required)}")
    selected_columns = required_columns + [column for column in optional_columns if column in header]
    selected_columns = list(dict.fromkeys(selected_columns))
    return pd.read_csv(path, usecols=selected_columns, low_memory=False)


def _load_sources(config: dict[str, Any], join_keys: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    even_path = cfg_path(config, "paths", "even_method_csv")
    definitive_path = cfg_path(config, "paths", "definitive_method_csv")
    if not even_path.exists():
        raise FileNotFoundError(f"Missing even-method CSV: {even_path}")
    if not definitive_path.exists():
        raise FileNotFoundError(f"Missing definitive-method CSV: {definitive_path}")

    even_required = [*join_keys, "eff_reference", "scale_factor", "selected_rate_hz", "corrected_rate_hz"]
    even_optional = [
        "execution_timestamp_utc",
        "eff_reference_mode",
        "z_config_id",
        "z_config_label",
        "four_plane_robust_hz",
        "selected_rate_count",
        *[f"eff_empirical_{idx}" for idx in range(1, 5)],
        *[f"eff_empirical_raw_{idx}" for idx in range(1, 5)],
        *[f"eff_empirical_corrected_{idx}" for idx in range(1, 5)],
    ]
    even_frame = _load_method_frame(
        even_path,
        required_columns=even_required,
        optional_columns=even_optional,
        label="AN_EVEN_EASIER_VARIATION_ADVANCED output",
    )

    definitive_required = [*join_keys, "lut_scale_factor", "rate_hz", "corrected_rate_to_perfect_hz"]
    definitive_optional = [
        "execution_timestamp_utc",
        "lut_match_method",
        "lut_match_distance",
        "selected_z_vector_match",
        "rate_hz__four_plane_robust_hz",
        *[f"eff_empirical_{idx}" for idx in range(1, 5)],
    ]
    definitive_frame = _load_method_frame(
        definitive_path,
        required_columns=definitive_required,
        optional_columns=definitive_optional,
        label="DEFINITIVE_METHOD four_plane_robust_hz output",
    )

    return even_frame, definitive_frame, {
        "even_path": str(even_path),
        "definitive_path": str(definitive_path),
    }


def _merge_method_outputs(
    even_frame: pd.DataFrame,
    definitive_frame: pd.DataFrame,
    *,
    join_keys: list[str],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    even_joined, even_join_columns = _add_normalized_join_columns(even_frame, join_keys)
    definitive_joined, definitive_join_columns = _add_normalized_join_columns(definitive_frame, join_keys)

    _check_duplicate_keys(even_joined, even_join_columns, "AN_EVEN_EASIER_VARIATION_ADVANCED")
    _check_duplicate_keys(definitive_joined, definitive_join_columns, "DEFINITIVE_METHOD")

    even_prefixed = _prefixed_columns(even_joined, prefix="even_", preserve_columns=[*join_keys, *even_join_columns])
    definitive_prefixed = _prefixed_columns(
        definitive_joined,
        prefix="definitive_",
        preserve_columns=definitive_join_columns,
    )

    outer = even_prefixed.merge(
        definitive_prefixed,
        how="outer",
        on=even_join_columns,
        indicator=True,
    )
    merge_stats = {
        "rows_even": int(len(even_frame)),
        "rows_definitive": int(len(definitive_frame)),
        "rows_inner": int((outer["_merge"] == "both").sum()),
        "rows_even_only": int((outer["_merge"] == "left_only").sum()),
        "rows_definitive_only": int((outer["_merge"] == "right_only").sum()),
    }

    inner = outer.loc[outer["_merge"] == "both"].copy()
    inner = inner.drop(columns=["_merge"])
    if inner.empty:
        raise ValueError("The method outputs have no overlapping rows under the configured join_keys.")

    if "file_timestamp_utc" in inner.columns:
        inner["file_timestamp_utc"] = pd.to_datetime(inner["file_timestamp_utc"], errors="coerce", utc=True)
    if "even_execution_timestamp_utc" in inner.columns:
        inner["even_execution_timestamp_utc"] = pd.to_datetime(
            inner["even_execution_timestamp_utc"], errors="coerce", utc=True
        )
    if "definitive_execution_timestamp_utc" in inner.columns:
        inner["definitive_execution_timestamp_utc"] = pd.to_datetime(
            inner["definitive_execution_timestamp_utc"], errors="coerce", utc=True
        )
    return inner.reset_index(drop=True), merge_stats


def _derive_comparison_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    work = dataframe.copy()
    work["even_eff_reference"] = pd.to_numeric(work["even_eff_reference"], errors="coerce")
    work["even_scale_factor"] = pd.to_numeric(work["even_scale_factor"], errors="coerce")
    work["definitive_lut_scale_factor"] = pd.to_numeric(work["definitive_lut_scale_factor"], errors="coerce")
    work["even_selected_rate_hz"] = pd.to_numeric(work["even_selected_rate_hz"], errors="coerce")
    work["definitive_rate_hz"] = pd.to_numeric(work["definitive_rate_hz"], errors="coerce")
    work["even_corrected_rate_hz"] = pd.to_numeric(work["even_corrected_rate_hz"], errors="coerce")
    work["definitive_corrected_rate_to_perfect_hz"] = pd.to_numeric(
        work["definitive_corrected_rate_to_perfect_hz"],
        errors="coerce",
    )

    work["even_inv_eff_reference"] = 1.0 / work["even_eff_reference"]
    work["scale_factor_delta"] = work["definitive_lut_scale_factor"] - work["even_inv_eff_reference"]
    work["scale_factor_ratio"] = work["definitive_lut_scale_factor"] / work["even_inv_eff_reference"]
    work["corrected_rate_delta_hz"] = (
        work["definitive_corrected_rate_to_perfect_hz"] - work["even_corrected_rate_hz"]
    )
    work["selected_rate_delta_hz"] = work["definitive_rate_hz"] - work["even_selected_rate_hz"]
    work["abs_scale_factor_delta"] = work["scale_factor_delta"].abs()

    if "file_timestamp_utc" in work.columns and pd.api.types.is_datetime64_any_dtype(work["file_timestamp_utc"]):
        work = work.sort_values("file_timestamp_utc", na_position="last").reset_index(drop=True)
    else:
        work = work.reset_index(drop=True)
    work["sequence_order"] = np.arange(len(work), dtype=int)
    return work


def _summary_stats(dataframe: pd.DataFrame) -> dict[str, Any]:
    valid = dataframe[["even_inv_eff_reference", "definitive_lut_scale_factor"]].dropna()
    corr = float(valid.corr().iloc[0, 1]) if len(valid) >= 2 else None
    return {
        "matched_rows": int(len(dataframe)),
        "valid_scale_rows": int(len(valid)),
        "inverse_eff_reference_min": float(dataframe["even_inv_eff_reference"].min()),
        "inverse_eff_reference_max": float(dataframe["even_inv_eff_reference"].max()),
        "lut_scale_factor_min": float(dataframe["definitive_lut_scale_factor"].min()),
        "lut_scale_factor_max": float(dataframe["definitive_lut_scale_factor"].max()),
        "scale_factor_delta_median": float(dataframe["scale_factor_delta"].median()),
        "scale_factor_delta_abs_median": float(dataframe["abs_scale_factor_delta"].median()),
        "scale_factor_ratio_median": float(dataframe["scale_factor_ratio"].median()),
        "scale_factor_ratio_mean": float(dataframe["scale_factor_ratio"].mean()),
        "selected_rate_delta_abs_max_hz": float(dataframe["selected_rate_delta_hz"].abs().max()),
        "corrected_rate_delta_abs_median_hz": float(dataframe["corrected_rate_delta_hz"].abs().median()),
        "pearson_corr_inverse_eff_vs_lut_scale": corr,
    }


def _pairwise_numeric_alignment_check(
    dataframe: pd.DataFrame,
    left_column: str,
    right_column: str,
) -> dict[str, Any]:
    if left_column not in dataframe.columns or right_column not in dataframe.columns:
        return {
            "left_column": left_column,
            "right_column": right_column,
            "available": False,
        }
    left = pd.to_numeric(dataframe[left_column], errors="coerce")
    right = pd.to_numeric(dataframe[right_column], errors="coerce")
    valid = left.notna() & right.notna()
    if not bool(valid.any()):
        return {
            "left_column": left_column,
            "right_column": right_column,
            "available": True,
            "valid_rows": 0,
            "allclose": False,
            "max_abs_diff": None,
            "median_abs_diff": None,
        }
    delta = (left.loc[valid] - right.loc[valid]).abs()
    return {
        "left_column": left_column,
        "right_column": right_column,
        "available": True,
        "valid_rows": int(valid.sum()),
        "allclose": bool(np.allclose(left.loc[valid], right.loc[valid], rtol=0.0, atol=1e-12)),
        "max_abs_diff": float(delta.max()),
        "median_abs_diff": float(delta.median()),
    }


def _build_alignment_checks(dataframe: pd.DataFrame) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "selected_rate_hz_even_vs_rate_hz_definitive": _pairwise_numeric_alignment_check(
            dataframe,
            "even_selected_rate_hz",
            "definitive_rate_hz",
        ),
        "selected_rate_hz_even_vs_rate_hz__four_plane_robust_hz_definitive": _pairwise_numeric_alignment_check(
            dataframe,
            "even_selected_rate_hz",
            "definitive_rate_hz__four_plane_robust_hz",
        ),
        "four_plane_robust_hz_even_vs_definitive_rate_hz__four_plane_robust_hz": _pairwise_numeric_alignment_check(
            dataframe,
            "even_four_plane_robust_hz",
            "definitive_rate_hz__four_plane_robust_hz",
        ),
    }
    for plane_idx in range(1, 5):
        checks[f"eff_empirical_{plane_idx}_even_vs_definitive"] = _pairwise_numeric_alignment_check(
            dataframe,
            f"even_eff_empirical_{plane_idx}",
            f"definitive_eff_empirical_{plane_idx}",
        )
        checks[f"eff_empirical_raw_{plane_idx}_even_vs_definitive"] = _pairwise_numeric_alignment_check(
            dataframe,
            f"even_eff_empirical_raw_{plane_idx}",
            f"definitive_eff_empirical_{plane_idx}",
        )
        checks[f"eff_empirical_corrected_{plane_idx}_even_vs_even_eff_empirical_{plane_idx}"] = (
            _pairwise_numeric_alignment_check(
                dataframe,
                f"even_eff_empirical_corrected_{plane_idx}",
                f"even_eff_empirical_{plane_idx}",
            )
        )
    return checks


def _load_source_config_summaries(config: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label, path_key in (
        ("even_method", "even_method_config"),
        ("definitive_method", "definitive_method_config"),
    ):
        raw_path = config.get("paths", {}).get(path_key)
        if raw_path in (None, "", "null", "None"):
            continue
        path = resolve_path(config, raw_path)
        if not path.exists():
            out[label] = {"config_path": str(path), "exists": False}
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if label == "even_method":
            out[label] = {
                "config_path": str(path),
                "exists": True,
                "metadata_source": payload.get("trigger_type_selection", {}).get("metadata_source"),
                "rate_family": payload.get("trigger_type_selection", {}).get("rate_family"),
                "selected_display_label": payload.get("trigger_type_selection", {}).get("selected_display_label"),
                "robust_efficiency_variant": payload.get("trigger_type_selection", {}).get("robust_efficiency_variant"),
                "corrected_eff": payload.get("corrected_eff"),
                "even_efficiency_reference_mode": payload.get("step2", {}).get("efficiency_reference_mode"),
                "even_efficiency_reference_planes": payload.get("step2", {}).get("efficiency_reference_planes"),
            }
            continue
        definitive_csv_path = cfg_path(config, "paths", "definitive_method_csv")
        selected_rate_case = definitive_csv_path.parent.parent.name
        selected_rate_spec = next(
            (spec for spec in payload.get("rates", []) if str(spec.get("name")) == selected_rate_case),
            None,
        )
        out[label] = {
            "config_path": str(path),
            "exists": True,
            "efficiency_metadata_relative_path": payload.get("efficiency", {}).get("metadata_relative_path"),
            "efficiency_columns": payload.get("efficiency", {}).get("columns"),
            "selected_rate_case": selected_rate_case,
            "selected_rate_spec": selected_rate_spec,
            "lut_flux_bin_count": payload.get("lut", {}).get("flux_bin_count"),
            "lut_reference_curve_mode": payload.get("lut", {}).get("reference_curve_mode"),
            "lut_reference_top_k_per_flux_bin": payload.get("lut", {}).get("reference_top_k_per_flux_bin"),
            "lut_interpolation_mode": payload.get("lut", {}).get("interpolation_mode"),
        }
    return out


def _build_outlier_table(dataframe: pd.DataFrame, top_n: int) -> list[dict[str, Any]]:
    if top_n <= 0:
        return []
    selected_columns = [
        "filename_base",
        "file_timestamp_utc",
        "even_inv_eff_reference",
        "definitive_lut_scale_factor",
        "scale_factor_delta",
        "scale_factor_ratio",
    ]
    outliers = dataframe.sort_values("abs_scale_factor_delta", ascending=False).head(int(top_n)).copy()
    if "file_timestamp_utc" in outliers.columns and pd.api.types.is_datetime64_any_dtype(outliers["file_timestamp_utc"]):
        outliers["file_timestamp_utc"] = outliers["file_timestamp_utc"].dt.strftime("%Y-%m-%d %H:%M:%S%z")
    return outliers[selected_columns].to_dict(orient="records")


def _plot_scatter(
    dataframe: pd.DataFrame,
    output_path: Path,
    *,
    point_size: float,
    point_alpha: float,
    color_by: str,
    annotate_top_n: int,
    axis_limits: tuple[float, float] | None,
) -> None:
    plot_frame = dataframe.dropna(subset=["even_inv_eff_reference", "definitive_lut_scale_factor"]).copy()
    fig, ax = plt.subplots(figsize=(11, 8))

    if color_by == "sequence":
        color_values = plot_frame["sequence_order"].to_numpy(dtype=float)
        color_label = "Time-series order"
    else:
        color_values = pd.to_numeric(plot_frame["scale_factor_ratio"], errors="coerce").to_numpy(dtype=float)
        color_label = "LUT / inverse-eff ratio"

    scatter = None
    clipped_mask = pd.Series(False, index=plot_frame.index, dtype=bool)
    x_values = pd.to_numeric(plot_frame["even_inv_eff_reference"], errors="coerce")
    y_values = pd.to_numeric(plot_frame["definitive_lut_scale_factor"], errors="coerce")
    plot_x = x_values.copy()
    plot_y = y_values.copy()
    if axis_limits is not None:
        lower, upper = axis_limits
        clipped_mask = (x_values < lower) | (x_values > upper) | (y_values < lower) | (y_values > upper)
        plot_x = x_values.clip(lower=lower, upper=upper)
        plot_y = y_values.clip(lower=lower, upper=upper)

    in_range_mask = ~clipped_mask
    if bool(in_range_mask.any()):
        scatter = ax.scatter(
            plot_x.loc[in_range_mask],
            plot_y.loc[in_range_mask],
            c=color_values[in_range_mask.to_numpy()],
            cmap="viridis",
            s=float(point_size),
            alpha=float(point_alpha),
            edgecolors="none",
        )
    if bool(clipped_mask.any()):
        ax.scatter(
            plot_x.loc[clipped_mask],
            plot_y.loc[clipped_mask],
            color="#9a9a9a",
            s=float(point_size) * 1.15,
            alpha=0.95,
            edgecolors="none",
            label=f"Clipped to plot limits (n={int(clipped_mask.sum())})",
        )

    line_values = pd.concat(
        [plot_frame["even_inv_eff_reference"], plot_frame["definitive_lut_scale_factor"]],
        ignore_index=True,
    )
    line_values = pd.to_numeric(line_values, errors="coerce")
    line_values = line_values[np.isfinite(line_values)]
    if len(line_values) > 0:
        if axis_limits is not None:
            line_min, line_max = axis_limits
        else:
            line_min = float(line_values.min())
            line_max = float(line_values.max())
        ax.plot(
            [line_min, line_max],
            [line_min, line_max],
            linestyle="--",
            linewidth=1.3,
            color="black",
            alpha=0.7,
            label="y = x",
        )

    corr = None
    valid = plot_frame[["even_inv_eff_reference", "definitive_lut_scale_factor"]].dropna()
    if len(valid) >= 2:
        corr = float(valid.corr().iloc[0, 1])
    ratio_median = float(plot_frame["scale_factor_ratio"].median())
    delta_abs_median = float(plot_frame["abs_scale_factor_delta"].median())
    stats_text = (
        f"rows = {len(plot_frame)}\n"
        f"corr = {corr:.3f}\n"
        f"median(LUT / inverse-eff) = {ratio_median:.3f}\n"
        f"median |delta| = {delta_abs_median:.3f}"
    )
    if axis_limits is not None and bool(clipped_mask.any()):
        stats_text += f"\nclipped to [{axis_limits[0]:.1f}, {axis_limits[1]:.1f}] = {int(clipped_mask.sum())}"
    ax.text(
        0.02,
        0.98,
        stats_text,
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        bbox={
            "boxstyle": "round,pad=0.25",
            "facecolor": "white",
            "edgecolor": "#999999",
            "alpha": 0.85,
        },
    )

    if annotate_top_n > 0:
        top_outliers = plot_frame.sort_values("abs_scale_factor_delta", ascending=False).head(int(annotate_top_n))
        for _, row in top_outliers.iterrows():
            x_value = float(row["even_inv_eff_reference"])
            y_value = float(row["definitive_lut_scale_factor"])
            if axis_limits is not None:
                x_value = float(np.clip(x_value, axis_limits[0], axis_limits[1]))
                y_value = float(np.clip(y_value, axis_limits[0], axis_limits[1]))
            ax.annotate(
                str(row["filename_base"]),
                (x_value, y_value),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=7,
                alpha=0.9,
            )

    ax.set_title(
        "Method comparison: inverse eff_reference vs LUT scale factor\n"
        "AN_EVEN_EASIER_VARIATION_ADVANCED vs DEFINITIVE_METHOD four_plane_robust_hz"
    )
    ax.set_xlabel("AN_EVEN: 1 / eff_reference")
    ax.set_ylabel("DEFINITIVE: lut_scale_factor")
    if axis_limits is not None:
        ax.set_xlim(*axis_limits)
        ax.set_ylim(*axis_limits)
    ax.grid(alpha=0.25)
    ax.legend(loc="lower right")
    if scatter is not None:
        cbar = fig.colorbar(scatter, ax=ax)
        cbar.set_label(color_label)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _plot_time_series_comparison(
    dataframe: pd.DataFrame,
    output_path: Path,
    *,
    histogram_bins: int,
    histogram_zscore_limit: float | None,
) -> None:
    plot_frame = dataframe.copy()
    if "file_timestamp_utc" in plot_frame.columns and pd.api.types.is_datetime64_any_dtype(plot_frame["file_timestamp_utc"]):
        x_values = plot_frame["file_timestamp_utc"]
        x_label = "file timestamp utc"
    else:
        x_values = plot_frame["sequence_order"]
        x_label = "sequence order"

    fig = plt.figure(figsize=(15, 10), constrained_layout=True)
    grid = fig.add_gridspec(2, 2, height_ratios=[2.0, 1.0], width_ratios=[2.4, 1.1])
    top_ax = fig.add_subplot(grid[0, :])
    bottom_ax = fig.add_subplot(grid[1, 0], sharex=top_ax)
    hist_ax = fig.add_subplot(grid[1, 1])

    top_ax.plot(
        x_values,
        plot_frame["even_inv_eff_reference"],
        marker="o",
        markersize=3,
        linewidth=1.5,
        color="#6a3d9a",
        label="AN_EVEN: 1 / eff_reference",
    )
    top_ax.plot(
        x_values,
        plot_frame["definitive_lut_scale_factor"],
        marker="o",
        markersize=3,
        linewidth=1.5,
        color="#8B1E3F",
        label="DEFINITIVE: lut_scale_factor",
    )
    top_ax.set_title("Scale-factor comparison over time")
    top_ax.set_ylabel("Scale-like value")
    top_ax.grid(alpha=0.25)
    top_ax.legend()

    bottom_ax.plot(
        x_values,
        plot_frame["scale_factor_delta"],
        marker="o",
        markersize=2.8,
        linewidth=1.2,
        color="#1F6FEB",
        label="DEFINITIVE - AN_EVEN",
    )
    bottom_ax.axhline(0.0, linestyle="--", linewidth=1.0, color="black", alpha=0.7)
    bottom_ax.set_xlabel(x_label)
    bottom_ax.set_ylabel("Delta")
    bottom_ax.grid(alpha=0.25)
    bottom_ax.legend()

    delta_values = pd.to_numeric(plot_frame["scale_factor_delta"], errors="coerce").dropna()
    hist_values = delta_values.copy()
    clipped_outliers = 0
    if histogram_zscore_limit is not None and len(delta_values) >= 2:
        delta_std = float(delta_values.std(ddof=0))
        if np.isfinite(delta_std) and delta_std > 0.0:
            delta_mean = float(delta_values.mean())
            z_scores = (delta_values - delta_mean) / delta_std
            keep_mask = z_scores.abs() <= float(histogram_zscore_limit)
            clipped_outliers = int((~keep_mask).sum())
            if int(keep_mask.sum()) > 0:
                hist_values = delta_values.loc[keep_mask]

    hist_ax.hist(
        hist_values,
        bins=int(histogram_bins),
        color="#4C78A8",
        alpha=0.80,
        edgecolor="white",
        linewidth=0.6,
    )
    hist_ax.axvline(0.0, linestyle="--", linewidth=1.0, color="black", alpha=0.8, label="0")
    hist_ax.axvline(
        float(delta_values.median()),
        linestyle="-",
        linewidth=1.2,
        color="#B22222",
        alpha=0.9,
        label=f"median = {float(delta_values.median()):.3f}",
    )
    hist_title = "Delta histogram"
    if histogram_zscore_limit is not None:
        hist_title += f"\n|z| <= {histogram_zscore_limit:g}"
    hist_ax.set_title(hist_title)
    hist_ax.set_xlabel("Delta")
    hist_ax.set_ylabel("Count")
    hist_ax.grid(alpha=0.20)
    hist_ax.legend(fontsize=8)
    if clipped_outliers > 0:
        hist_ax.text(
            0.98,
            0.98,
            f"outliers clipped = {clipped_outliers}",
            transform=hist_ax.transAxes,
            ha="right",
            va="top",
            fontsize=8,
            bbox={
                "boxstyle": "round,pad=0.2",
                "facecolor": "white",
                "edgecolor": "#999999",
                "alpha": 0.85,
            },
        )

    if pd.api.types.is_datetime64_any_dtype(x_values):
        fig.autofmt_xdate()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def run(config_path: str | Path | None = None) -> Path:
    _configure_logging()
    ensure_output_dirs()
    config = load_config(config_path)

    join_keys = _normalize_join_keys(config)
    annotate_top_n = int(config.get("comparison", {}).get("annotate_top_n_abs_delta", 6))
    color_by = str(config.get("comparison", {}).get("scatter_color_by", "sequence"))
    point_alpha = float(config.get("comparison", {}).get("scatter_alpha", 0.85))
    point_size = float(config.get("comparison", {}).get("scatter_size", 28))
    scatter_axis_limits = _normalize_scatter_axis_limits(config)
    histogram_bins = _normalize_histogram_bins(config)
    histogram_zscore_limit = _normalize_histogram_zscore_limit(config)

    merged_output_path = cfg_path(config, "paths", "merged_output_csv")
    meta_path = cfg_path(config, "paths", "meta_json")
    scatter_plot_path = cfg_path(config, "paths", "scatter_plot")
    timeseries_plot_path = cfg_path(config, "paths", "timeseries_plot")

    even_frame, definitive_frame, source_paths = _load_sources(config, join_keys)
    merged, merge_stats = _merge_method_outputs(even_frame, definitive_frame, join_keys=join_keys)
    merged = _derive_comparison_columns(merged)

    merged_output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(merged_output_path, index=False)

    _plot_scatter(
        merged,
        scatter_plot_path,
        point_size=point_size,
        point_alpha=point_alpha,
        color_by=color_by,
        annotate_top_n=annotate_top_n,
        axis_limits=scatter_axis_limits,
    )
    _plot_time_series_comparison(
        merged,
        timeseries_plot_path,
        histogram_bins=histogram_bins,
        histogram_zscore_limit=histogram_zscore_limit,
    )

    summary = _summary_stats(merged)
    outliers = _build_outlier_table(merged, annotate_top_n)
    alignment_checks = _build_alignment_checks(merged)
    source_config_summaries = _load_source_config_summaries(config)
    metadata = {
        "source_paths": source_paths,
        "source_config_summaries": source_config_summaries,
        "join_keys": join_keys,
        "scatter_axis_limits": list(scatter_axis_limits) if scatter_axis_limits is not None else None,
        "delta_histogram_bins": histogram_bins,
        "delta_histogram_zscore_limit": histogram_zscore_limit,
        "merge_stats": merge_stats,
        "summary": summary,
        "alignment_checks": alignment_checks,
        "largest_abs_delta_rows": outliers,
        "output_files": {
            "merged_csv": str(merged_output_path),
            "meta_json": str(meta_path),
            "scatter_plot": str(scatter_plot_path),
            "timeseries_plot": str(timeseries_plot_path),
        },
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    log.info("Wrote merged comparison CSV with %d rows to %s", len(merged), merged_output_path)
    log.info("Wrote scatter plot to %s", scatter_plot_path)
    log.info("Wrote time-series comparison plot to %s", timeseries_plot_path)
    return merged_output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare AN_EVEN_EASIER_VARIATION_ADVANCED against DEFINITIVE_METHOD four_plane_robust_hz.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to config JSON file.")
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()
