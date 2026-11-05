#!/usr/bin/env python3
"""Plot configurable event distributions from consecutive Stage 1 product files."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from fnmatch import fnmatchcase
from itertools import combinations
from pathlib import Path
import re
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import yaml

from calibration_context import generate_calibration_context
from mingo00_product_selection import (
    Mingo00Selection,
    select_mingo00_products,
    validate_close_parameters,
)

ANALYSIS_ROOT = Path(__file__).resolve().parents[3]
STATIONS_ROOT = ANALYSIS_ROOT / "MINGO_ANALYSIS_STATIONS"
DEFAULT_CONFIG = Path(__file__).with_name("config_test_2_event_distributions.yaml")
OUTPUT_NAME = "TEST_2_EVENT_DISTRIBUTIONS"
BASENAME_RE = re.compile(r"mi0[0-9]\d{11}")
PLANE_MATRIX_VARIABLES = (
    ("qsum", "Q_sum"),
    ("qdif", "Q_dif"),
    ("tsum", "T_sum"),
    ("x", "X [mm]"),
    ("y", "Y [mm]"),
)

@dataclass(frozen=True)
class Product:
    path: Path
    basename: str
    acquired: datetime

def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser.parse_args()

def station_name(value: Any) -> str:
    text = str(value).strip().upper().removeprefix("MINGO")
    try:
        number = int(text)
    except ValueError as exc:
        raise ValueError(f"Invalid station {value!r}; use 1, 01, or MINGO01") from exc
    if not 0 <= number <= 99:
        raise ValueError(f"Station number outside supported range: {number}")
    return f"MINGO{number:02d}"

def boundary(value: Any, *, is_end: bool) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        parsed = datetime.combine(value, time.min)
        return parsed + timedelta(days=1) - timedelta(microseconds=1) if is_end else parsed
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid ISO date/datetime: {value!r}") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    if is_end and re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        parsed += timedelta(days=1) - timedelta(microseconds=1)
    return parsed

def acquisition_time(basename: str) -> datetime | None:
    if not BASENAME_RE.fullmatch(basename):
        return None
    stamp = basename[4:]
    try:
        year = 2000 + int(stamp[:2])
        doy = int(stamp[2:5])
        if not 1 <= doy <= 366:
            return None
        parsed = datetime(year, 1, 1) + timedelta(
            days=doy - 1, hours=int(stamp[5:7]),
            minutes=int(stamp[7:9]), seconds=int(stamp[9:11]),
        )
    except (ValueError, OverflowError):
        return None
    return parsed if parsed.year == year else None

def parquet_basename(path: Path) -> str | None:
    name = path.stem
    for prefix in ("postprocessed_", "fitted_", "listed_", "calibrated_", "cleaned_", "raw_"):
        if name.startswith(prefix):
            name = name.removeprefix(prefix)
            break
    return name if BASENAME_RE.fullmatch(name) else None

def configuration(path: Path) -> dict[str, Any]:
    with path.expanduser().open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, dict):
        raise ValueError("Config root must be a YAML mapping")
    missing = [key for key in ("station", "max_datafiles") if key not in config]
    if missing:
        raise ValueError("Missing config fields: " + ", ".join(missing))
    resolved_station = station_name(config["station"])
    if resolved_station == "MINGO00":
        close_parameters = validate_close_parameters(config.get("mingo00_close_parameters"))
        # MINGO00 acquisition dates are synthetic and must not restrict candidates.
        start = datetime(2000, 1, 1)
        end = datetime(2100, 1, 1) - timedelta(microseconds=1)
    else:
        date_missing = [key for key in ("start_date", "end_date") if key not in config]
        if date_missing:
            raise ValueError("Missing config fields: " + ", ".join(date_missing))
        start = boundary(config["start_date"], is_end=False)
        end = boundary(config["end_date"], is_end=True)
        close_parameters = (
            validate_close_parameters(config["mingo00_close_parameters"])
            if "mingo00_close_parameters" in config
            else ()
        )
    maximum = int(config["max_datafiles"])
    if start > end or maximum < 1:
        raise ValueError("Require start_date <= end_date and max_datafiles >= 1")
    config.update(
        station_name=resolved_station,
        start=start,
        end=end,
        maximum=maximum,
        close_parameters=close_parameters,
    )
    return config

def discover(lake: Path, start: datetime, end: datetime) -> list[Product]:
    if not lake.is_dir():
        raise FileNotFoundError(f"Parquet lake not found: {lake}")
    found: list[Product] = []
    for path in lake.glob("*.parquet"):
        base = parquet_basename(path)
        acquired = acquisition_time(base) if base else None
        if base and acquired and start <= acquired <= end:
            found.append(Product(path, base, acquired))
    found.sort(key=lambda item: (item.acquired, item.basename))
    if not found:
        raise ValueError(f"No product files between {start.isoformat()} and {end.isoformat()}")
    return found

def tightest_block(files: list[Product], maximum: int) -> list[Product]:
    """Pick a contiguous chronological block with the smallest start-time span."""
    count = min(maximum, len(files))
    if count == len(files):
        return files
    index = min(
        range(len(files) - count + 1),
        key=lambda i: (files[i + count - 1].acquired - files[i].acquired, files[i].acquired),
    )
    return files[index:index + count]

def schemas(files: list[Product]) -> tuple[list[str], dict[str, set[str]]]:
    columns: list[str] = []
    types: dict[str, set[str]] = {}
    for product in files:
        for field in pq.read_schema(product.path):
            if field.name not in types:
                columns.append(field.name)
            types.setdefault(field.name, set()).add(str(field.type))
    return columns, types

def show_columns(columns: list[str], types: dict[str, set[str]]) -> None:
    print(f"\nAvailable columns in selected files ({len(columns)}):")
    for index, name in enumerate(columns, 1):
        type_text = " | ".join(sorted(types[name]))
        print(f"  {index:03d}. {name:<52} [{type_text}]")
    print()

def list_setting(config: dict[str, Any], key: str) -> list[Any]:
    value = config.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a YAML list")
    return value

def histogram_columns(config: dict[str, Any], available: list[str]) -> list[str]:
    resolved: list[str] = []
    for raw in list_setting(config, "histogram_columns"):
        pattern = str(raw).strip()
        matches = [name for name in available if fnmatchcase(name, pattern)]
        if not matches:
            raise ValueError(f"Histogram pattern matched no columns: {pattern!r}")
        resolved.extend(name for name in matches if name not in resolved)
    return resolved

def histogram_grids(config: dict[str, Any], available: list[str]) -> list[tuple[str, str, list[str]]]:
    resolved: list[tuple[str, str, list[str]]] = []
    for index, item in enumerate(list_setting(config, "histogram_grids"), 1):
        if not isinstance(item, dict) or "suffix" not in item:
            raise ValueError(f"histogram_grids item {index} needs suffix")
        suffix = str(item["suffix"]).strip()
        label = str(item.get("label", suffix)).strip()
        columns = [f"p{plane}_s{strip}_{suffix}" for plane in range(1, 5) for strip in range(1, 5)]
        missing = [name for name in columns if name not in available]
        if missing:
            raise ValueError(f"Histogram grid {suffix!r} is missing columns: " + ", ".join(missing))
        resolved.append((suffix, label, columns))
    return resolved

def scatter_pairs(config: dict[str, Any]) -> list[tuple[str, str]]:
    resolved: list[tuple[str, str]] = []
    for index, item in enumerate(list_setting(config, "scatter_pairs"), 1):
        if not isinstance(item, dict) or "x" not in item or "y" not in item:
            raise ValueError(f"scatter_pairs item {index} needs x and y")
        pair = str(item["x"]).strip(), str(item["y"]).strip()
        if pair not in resolved:
            resolved.append(pair)
    return resolved

def scatter_grids(
    config: dict[str, Any], available: list[str],
) -> list[tuple[str, str, str, str, list[str]]]:
    resolved: list[tuple[str, str, str, str, list[str]]] = []
    for index, item in enumerate(list_setting(config, "per_strip_scatter_pairs"), 1):
        if not isinstance(item, dict) or "x_suffix" not in item or "y_suffix" not in item:
            raise ValueError(f"per_strip_scatter_pairs item {index} needs x_suffix and y_suffix")
        x_suffix, y_suffix = str(item["x_suffix"]).strip(), str(item["y_suffix"]).strip()
        x_label = str(item.get("x_label", x_suffix)).strip()
        y_label = str(item.get("y_label", y_suffix)).strip()
        columns = [
            f"p{plane}_s{strip}_{suffix}"
            for plane in range(1, 5)
            for strip in range(1, 5)
            for suffix in (x_suffix, y_suffix)
        ]
        missing = [name for name in columns if name not in available]
        if missing:
            raise ValueError(
                f"Scatter grid {y_suffix!r} vs {x_suffix!r} is missing columns: "
                + ", ".join(missing)
            )
        spec = x_suffix, y_suffix, x_label, y_label, columns
        if spec not in resolved:
            resolved.append(spec)
    return resolved

def read_events(files: list[Product], columns: list[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for product in files:
        present = set(pq.read_schema(product.path).names)
        frame = pd.read_parquet(product.path, columns=[name for name in columns if name in present])
        for name in columns:
            if name not in frame:
                frame[name] = np.nan
        frame = frame[columns]
        frame["_source_basename"] = product.basename
        frames.append(frame)
        print(f"Loaded {len(frame):,} events from {product.basename}")
    return pd.concat(frames, ignore_index=True)

def apply_calibrated_limits(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, int]:
    """Set finite per-strip calibrated values outside configured bounds to zero."""
    raw_limits = config.get("calibrated_value_limits", {})
    if raw_limits is None:
        return {}
    if not isinstance(raw_limits, dict):
        raise ValueError("calibrated_value_limits must be a YAML mapping")
    replacement_counts: dict[str, int] = {}
    for raw_suffix, raw_bounds in raw_limits.items():
        suffix = str(raw_suffix).strip()
        if (
            not isinstance(raw_bounds, (list, tuple))
            or len(raw_bounds) != 2
        ):
            raise ValueError(
                f"calibrated_value_limits.{suffix} must be [minimum, maximum]"
            )
        lower, upper = float(raw_bounds[0]), float(raw_bounds[1])
        if not np.isfinite(lower) or not np.isfinite(upper) or lower > upper:
            raise ValueError(
                f"Invalid bounds for calibrated_value_limits.{suffix}: {raw_bounds!r}"
            )
        columns = [
            f"p{plane}_s{strip}_{suffix}"
            for plane in range(1, 5)
            for strip in range(1, 5)
            if f"p{plane}_s{strip}_{suffix}" in frame.columns
        ]
        if not columns:
            print(f"Warning: no loaded per-strip columns matched limit suffix {suffix!r}")
            replacement_counts[suffix] = 0
            continue
        family_count = 0
        for column in columns:
            numeric = pd.to_numeric(frame[column], errors="coerce")
            outside = numeric.notna() & numeric.ne(0) & ((numeric < lower) | (numeric > upper))
            count = int(outside.sum())
            if count:
                frame.loc[outside, column] = 0
            family_count += count
        replacement_counts[suffix] = family_count
        print(
            f"[CALIBRATED_LIMIT] {suffix}: inclusive [{lower:g}, {upper:g}], "
            f"set {family_count:,} out-of-range value(s) to 0 across {len(columns)} column(s)"
        )
    return replacement_counts


def plane_limit_columns(config: dict[str, Any], available: list[str]) -> list[str]:
    raw_limits = config.get("per_plane_value_limits", {})
    if raw_limits is None:
        return []
    if not isinstance(raw_limits, dict):
        raise ValueError("per_plane_value_limits must be a YAML mapping")
    return [
        f"p{plane}_{str(suffix).strip()}"
        for suffix in raw_limits
        for plane in range(1, 5)
        if f"p{plane}_{str(suffix).strip()}" in available
    ]

def apply_per_plane_limits(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, int]:
    """Set nonzero final per-plane values outside inclusive limits to zero."""
    raw_limits = config.get("per_plane_value_limits", {})
    if raw_limits is None:
        return {}
    if not isinstance(raw_limits, dict):
        raise ValueError("per_plane_value_limits must be a YAML mapping")
    replacement_counts: dict[str, int] = {}
    for raw_suffix, raw_bounds in raw_limits.items():
        suffix = str(raw_suffix).strip()
        if not isinstance(raw_bounds, (list, tuple)) or len(raw_bounds) != 2:
            raise ValueError(
                f"per_plane_value_limits.{suffix} must be [minimum, maximum]"
            )
        lower, upper = float(raw_bounds[0]), float(raw_bounds[1])
        if not np.isfinite(lower) or not np.isfinite(upper) or lower > upper:
            raise ValueError(
                f"Invalid bounds for per_plane_value_limits.{suffix}: {raw_bounds!r}"
            )
        columns = [
            f"p{plane}_{suffix}"
            for plane in range(1, 5)
            if f"p{plane}_{suffix}" in frame.columns
        ]
        if not columns:
            print(f"Warning: no loaded per-plane columns matched limit suffix {suffix!r}")
            replacement_counts[suffix] = 0
            continue
        family_count = 0
        for column in columns:
            numeric = pd.to_numeric(frame[column], errors="coerce")
            outside = numeric.notna() & numeric.ne(0) & (
                (numeric < lower) | (numeric > upper)
            )
            count = int(outside.sum())
            if count:
                frame.loc[outside, column] = 0
            family_count += count
        replacement_counts[suffix] = family_count
        print(
            f"[PLANE_LIMIT] {suffix}: inclusive [{lower:g}, {upper:g}], "
            f"set {family_count:,} out-of-range value(s) to 0 across "
            f"{len(columns)} column(s)"
        )
    return replacement_counts

def finite(series: pd.Series) -> np.ndarray:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    return values[np.isfinite(values)]

def nonzero_finite(series: pd.Series) -> np.ndarray:
    """Return finite numeric values after removing exact zero placeholders."""
    values = finite(series)
    return values[values != 0]

def clipped_range(values: np.ndarray, quantiles: tuple[float, float]) -> tuple[float, float] | None:
    if not values.size:
        return None
    low, high = np.quantile(values, quantiles)
    if low == high:
        pad = max(abs(float(low)) * 0.01, 1e-6)
        return float(low - pad), float(high + pad)
    return float(low), float(high)

def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")

def histogram(
    frame: pd.DataFrame, files: list[Product], column: str, output: Path,
    bins: int, quantiles: tuple[float, float], log_y: bool, title: str,
) -> bool:
    joined = nonzero_finite(frame[column])
    if not joined.size:
        print(f"Warning: {column} has no finite histogram values")
        return False
    value_range = clipped_range(joined, quantiles)
    fig, axis = plt.subplots(figsize=(10, 6), constrained_layout=True)
    axis.hist(joined, bins=bins, range=value_range, alpha=0.28, color="black", label="joined")
    colors = plt.get_cmap("tab10").colors
    for index, product in enumerate(files):
        values = nonzero_finite(frame.loc[frame["_source_basename"] == product.basename, column])
        if values.size:
            axis.hist(values, bins=bins, range=value_range, histtype="step", linewidth=1,
                      color=colors[index % len(colors)], label=product.basename)
    if log_y:
        axis.set_yscale("log")
    axis.set(xlabel=column, ylabel="Events", title=f"{title}\nHistogram: {column}")
    axis.grid(True, alpha=0.2)
    axis.legend(fontsize=7)
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return True

def histogram_grid(
    frame: pd.DataFrame, files: list[Product], suffix: str, label: str, output: Path,
    bins: int, quantiles: tuple[float, float], log_y: bool, title: str,
) -> bool:
    columns = [f"p{plane}_s{strip}_{suffix}" for plane in range(1, 5) for strip in range(1, 5)]
    family_values = [nonzero_finite(frame[column]) for column in columns]
    populated_values = [values for values in family_values if values.size]
    if not populated_values:
        print(f"Warning: {suffix} grid has no finite nonzero values")
        return False
    shared_range = clipped_range(np.concatenate(populated_values), quantiles)

    fig, axes = plt.subplots(
        4, 4, figsize=(18, 14), constrained_layout=True, sharex=True,
    )
    colors = plt.get_cmap("tab10").colors
    plotted = False
    legend_handles = None
    legend_labels = None
    for plane in range(1, 5):
        for strip in range(1, 5):
            axis = axes[plane - 1, strip - 1]
            column = f"p{plane}_s{strip}_{suffix}"
            joined = nonzero_finite(frame[column])
            axis.set_title(f"Plane {plane}, strip {strip}")
            axis.grid(True, alpha=0.2)
            if not joined.size:
                axis.text(0.5, 0.5, "No nonzero values", ha="center", va="center", transform=axis.transAxes)
                continue
            plotted = True
            axis.hist(joined, bins=bins, range=shared_range, alpha=0.28, color="black", label="joined")
            for index, product in enumerate(files):
                values = nonzero_finite(
                    frame.loc[frame["_source_basename"] == product.basename, column]
                )
                if values.size:
                    axis.hist(
                        values, bins=bins, range=shared_range, histtype="step", linewidth=1,
                        color=colors[index % len(colors)], label=product.basename,
                    )
            if log_y:
                axis.set_yscale("log")
            if plane == 4:
                axis.set_xlabel(label)
            if strip == 1:
                axis.set_ylabel(f"Plane {plane}\nEvents")
            if legend_handles is None:
                legend_handles, legend_labels = axis.get_legend_handles_labels()
    fig.suptitle(f"{title}\n{label}: nonzero per-strip histograms", fontsize=15)
    if legend_handles:
        fig.legend(legend_handles, legend_labels, loc="upper right", fontsize=7)
    if not plotted:
        plt.close(fig)
        print(f"Warning: skipped {suffix} grid; no finite nonzero values")
        return False
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return True

def scatter(
    frame: pd.DataFrame, files: list[Product], x_name: str, y_name: str, output: Path,
    maximum: int, quantiles: tuple[float, float], title: str,
) -> bool:
    fig, axis = plt.subplots(figsize=(10, 7), constrained_layout=True)
    colors = plt.get_cmap("tab10").colors
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    plotted = 0
    for index, product in enumerate(files):
        part = frame.loc[frame["_source_basename"] == product.basename, [x_name, y_name]]
        part = part.apply(pd.to_numeric, errors="coerce")
        part = part.loc[
            np.isfinite(part[x_name])
            & np.isfinite(part[y_name])
            & part[x_name].ne(0)
            & part[y_name].ne(0)
        ]
        if len(part) > maximum:
            part = part.sample(maximum, random_state=1701 + index)
        if part.empty:
            continue
        x_values, y_values = part[x_name].to_numpy(), part[y_name].to_numpy()
        xs.append(x_values); ys.append(y_values); plotted += len(part)
        axis.scatter(x_values, y_values, s=3, alpha=0.25, linewidths=0,
                     color=colors[index % len(colors)], label=product.basename, rasterized=True)
    if not xs:
        plt.close(fig)
        print(f"Warning: {x_name} vs {y_name} has no finite nonzero pairs")
        return False
    x_range, y_range = clipped_range(np.concatenate(xs), quantiles), clipped_range(np.concatenate(ys), quantiles)
    if x_range: axis.set_xlim(*x_range)
    if y_range: axis.set_ylim(*y_range)
    axis.set(xlabel=x_name, ylabel=y_name,
             title=f"{title}\nScatter: {y_name} versus {x_name} ({plotted:,} points)")
    axis.grid(True, alpha=0.2); axis.legend(fontsize=7)
    fig.savefig(output, dpi=160); plt.close(fig)
    return True

def scatter_grid(
    frame: pd.DataFrame, files: list[Product], x_suffix: str, y_suffix: str,
    x_label: str, y_label: str, output: Path, maximum: int,
    quantiles: tuple[float, float], title: str,
) -> bool:
    fig, axes = plt.subplots(
        4, 4, figsize=(18, 14), constrained_layout=True, sharex=True, sharey=True,
    )
    colors = plt.get_cmap("tab10").colors
    all_x: list[np.ndarray] = []
    all_y: list[np.ndarray] = []
    legend_handles = None
    legend_labels = None
    plotted = 0
    for plane in range(1, 5):
        for strip in range(1, 5):
            axis = axes[plane - 1, strip - 1]
            x_name = f"p{plane}_s{strip}_{x_suffix}"
            y_name = f"p{plane}_s{strip}_{y_suffix}"
            axis.set_title(f"Plane {plane}, strip {strip}")
            axis.grid(True, alpha=0.2)
            panel_points = 0
            for index, product in enumerate(files):
                part = frame.loc[
                    frame["_source_basename"] == product.basename, [x_name, y_name]
                ].apply(pd.to_numeric, errors="coerce")
                part = part.loc[
                    np.isfinite(part[x_name])
                    & np.isfinite(part[y_name])
                    & part[x_name].ne(0)
                    & part[y_name].ne(0)
                ]
                if len(part) > maximum:
                    part = part.sample(
                        maximum, random_state=1701 + index + 100 * plane + strip,
                    )
                if part.empty:
                    continue
                x_values = part[x_name].to_numpy()
                y_values = part[y_name].to_numpy()
                all_x.append(x_values)
                all_y.append(y_values)
                panel_points += len(part)
                plotted += len(part)
                axis.scatter(
                    x_values, y_values, s=3, alpha=0.25, linewidths=0,
                    color=colors[index % len(colors)], label=product.basename,
                    rasterized=True,
                )
            if not panel_points:
                axis.text(
                    0.5, 0.5, "No nonzero pairs", ha="center", va="center",
                    transform=axis.transAxes,
                )
            if plane == 4:
                axis.set_xlabel(x_label)
            if strip == 1:
                axis.set_ylabel(f"Plane {plane}\n{y_label}")
            if legend_handles is None and panel_points:
                legend_handles, legend_labels = axis.get_legend_handles_labels()
    if not all_x:
        plt.close(fig)
        print(f"Warning: skipped {y_suffix} vs {x_suffix} grid; no finite nonzero pairs")
        return False
    x_range = clipped_range(np.concatenate(all_x), quantiles)
    y_range = clipped_range(np.concatenate(all_y), quantiles)
    if x_range:
        axes[0, 0].set_xlim(*x_range)
    if y_range:
        axes[0, 0].set_ylim(*y_range)
    fig.suptitle(
        f"{title}\n{y_label} versus {x_label}: nonzero per-strip scatters "
        f"({plotted:,} points)", fontsize=15,
    )
    if legend_handles:
        fig.legend(legend_handles, legend_labels, loc="upper right", fontsize=7)
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return True

def plane_matrix_columns() -> list[str]:
    """Return source columns for the five final per-plane observables."""
    suffixes = ("qsum", "qdif", "tsum", "xpos", "ypos")
    return [f"p{plane}_{suffix}" for plane in range(1, 5) for suffix in suffixes]

def plane_matrix_series(
    frame: pd.DataFrame, plane: int, key: str,
) -> pd.Series:
    suffix = {"x": "xpos", "y": "ypos"}.get(key, key)
    return pd.to_numeric(frame[f"p{plane}_{suffix}"], errors="coerce")

def plane_pair_matrix(
    frame: pd.DataFrame, files: list[Product], output: Path, maximum: int,
    quantiles: tuple[float, float], title: str,
) -> bool:
    """Plot all unique pairs of final per-plane Q/T/X/Y observables."""
    variable_pairs = list(combinations(PLANE_MATRIX_VARIABLES, 2))
    n_columns = len(variable_pairs)
    fig, axes = plt.subplots(
        4, n_columns, figsize=(4.2 * n_columns, 15), constrained_layout=True,
        sharex="col", sharey="col", squeeze=False,
    )
    colors = plt.get_cmap("tab10").colors
    range_values = [{"x": [], "y": []} for _ in variable_pairs]
    legend_handles = None
    legend_labels = None
    total_points = 0

    for plane in range(1, 5):
        for pair_index, ((y_key, y_label), (x_key, x_label)) in enumerate(variable_pairs):
            axis = axes[plane - 1, pair_index]
            if plane == 1:
                axis.set_title(f"{y_label} vs {x_label}")
            axis.grid(True, alpha=0.2)
            panel_points = 0
            for file_index, product in enumerate(files):
                source_mask = frame["_source_basename"] == product.basename
                part = pd.DataFrame({
                    "x": plane_matrix_series(frame.loc[source_mask], plane, x_key),
                    "y": plane_matrix_series(frame.loc[source_mask], plane, y_key),
                })
                part = part.loc[
                    np.isfinite(part["x"])
                    & np.isfinite(part["y"])
                    & part["x"].ne(0)
                    & part["y"].ne(0)
                ]
                if len(part) > maximum:
                    part = part.sample(
                        maximum,
                        random_state=2903 + file_index + 100 * plane + pair_index,
                    )
                if part.empty:
                    continue
                x_values = part["x"].to_numpy()
                y_values = part["y"].to_numpy()
                range_values[pair_index]["x"].append(x_values)
                range_values[pair_index]["y"].append(y_values)
                panel_points += len(part)
                total_points += len(part)
                axis.scatter(
                    x_values, y_values, s=2, alpha=0.22, linewidths=0,
                    color=colors[file_index % len(colors)], label=product.basename,
                    rasterized=True,
                )
            if not panel_points:
                axis.text(
                    0.5, 0.5, "No nonzero pairs", ha="center", va="center",
                    transform=axis.transAxes,
                )
            if plane == 4:
                axis.set_xlabel(x_label)
            axis.set_ylabel(f"Plane {plane}\n{y_label}")
            if legend_handles is None and panel_points:
                legend_handles, legend_labels = axis.get_legend_handles_labels()

    if not total_points:
        plt.close(fig)
        print("Warning: skipped per-plane pair matrix; no finite nonzero pairs")
        return False
    for pair_index, values in enumerate(range_values):
        if values["x"]:
            axes[0, pair_index].set_xlim(
                *clipped_range(np.concatenate(values["x"]), quantiles)
            )
        if values["y"]:
            axes[0, pair_index].set_ylim(
                *clipped_range(np.concatenate(values["y"]), quantiles)
            )
    fig.suptitle(
        f"{title}\nFinal per-plane observable pair matrix: nonzero values "
        f"({total_points:,} plotted pairs)", fontsize=16,
    )
    if legend_handles:
        fig.legend(legend_handles, legend_labels, loc="upper right", fontsize=7)
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return True


def rate_timeseries_setting(
    config: dict[str, Any], available: list[str],
) -> dict[str, Any] | None:
    raw = config.get("rate_timeseries")
    if raw in (None, False):
        return None
    if raw is True:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("rate_timeseries must be a YAML mapping or false")
    if not bool(raw.get("enabled", True)):
        return None
    time_column = str(raw.get("time_column", "datetime")).strip()
    filter_columns = [str(value).strip() for value in raw.get("after_filter_columns", [])]
    if not filter_columns:
        raise ValueError("rate_timeseries.after_filter_columns cannot be empty")
    missing = [name for name in [time_column, *filter_columns] if name not in available]
    if missing:
        raise ValueError("Rate time-series columns absent from schema: " + ", ".join(missing))
    try:
        window = pd.Timedelta(str(raw.get("accumulation_timespan", "1min")))
    except ValueError as exc:
        raise ValueError("Invalid rate_timeseries.accumulation_timespan") from exc
    if window <= pd.Timedelta(0):
        raise ValueError("rate_timeseries.accumulation_timespan must be positive")
    return {
        "time_column": time_column,
        "filter_columns": filter_columns,
        "window": window,
    }

def boolean_pass_mask(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series.dtype):
        return series.fillna(False).astype(bool)
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().any():
        return numeric.fillna(0).ne(0)
    return series.astype("string").str.strip().str.lower().isin({"true", "yes", "y", "1"})

def event_rate_timeseries(
    frame: pd.DataFrame, setting: dict[str, Any], output_png: Path,
    output_csv: Path, title: str,
) -> bool:
    """Plot before/after Hz using only timestamp-seconds present in the input."""
    time_column = setting["time_column"]
    filter_columns = setting["filter_columns"]
    window: pd.Timedelta = setting["window"]
    timestamps = pd.to_datetime(frame[time_column], errors="coerce")
    valid_time = timestamps.notna()
    if not bool(valid_time.any()):
        print(f"Warning: {time_column} has no valid timestamps for rate plotting")
        return False

    after_pass = pd.Series(True, index=frame.index, dtype=bool)
    for column in filter_columns:
        after_pass &= boolean_pass_mask(frame[column])

    seconds = timestamps.loc[valid_time].dt.floor("s")
    per_event = pd.DataFrame({
        "second": seconds,
        "after_pass": after_pass.loc[valid_time].astype(np.int8),
    })
    per_second = per_event.groupby("second", sort=True).agg(
        events_before=("after_pass", "size"),
        events_after=("after_pass", "sum"),
    )
    per_second["window_start"] = per_second.index.floor(window)
    summary = per_second.groupby("window_start", sort=True).agg(
        observed_seconds=("events_before", "size"),
        events_before=("events_before", "sum"),
        events_after=("events_after", "sum"),
    )
    summary["hz_before"] = summary["events_before"] / summary["observed_seconds"]
    summary["hz_after"] = summary["events_after"] / summary["observed_seconds"]
    summary["window_end"] = summary.index + window
    summary = summary.reset_index()
    summary.to_csv(output_csv, index=False)

    fig, axis = plt.subplots(figsize=(14, 7), constrained_layout=True)
    axis.plot(
        summary["window_start"], summary["hz_before"], linewidth=1.2,
        marker=".", markersize=3, label="Before filter",
    )
    axis.plot(
        summary["window_start"], summary["hz_after"], linewidth=1.2,
        marker=".", markersize=3, label="After filter",
    )
    axis.set(
        xlabel="Time",
        ylabel="Event rate [Hz]",
        title=(
            f"{title}\nBefore/after filter event rate | accumulation={window} | "
            "denominator=observed seconds"
        ),
    )
    axis.grid(True, alpha=0.25)
    axis.legend()
    fig.autofmt_xdate()
    fig.savefig(output_png, dpi=160)
    plt.close(fig)
    observed_seconds = int(summary["observed_seconds"].sum())
    print(
        f"Rate time series: {len(summary)} window(s), "
        f"observed_seconds={observed_seconds:,}, "
        f"after_filter={' & '.join(filter_columns)}"
    )
    return True

def quantile_setting(config: dict[str, Any]) -> tuple[float, float]:
    value = config.get("plot_quantiles", [0.001, 0.999])
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("plot_quantiles needs exactly two values")
    low, high = float(value[0]), float(value[1])
    if not 0 <= low < high <= 1:
        raise ValueError("plot_quantiles must satisfy 0 <= low < high <= 1")
    return low, high

def main() -> int:
    config = configuration(arguments().config)
    root = STATIONS_ROOT / config["station_name"]
    lake = root / "STAGE_1_PRODUCTS" / "EVENT_DATA" / "PARQUET_LAKE"
    simulation_selection: Mingo00Selection | None = None
    if config["station_name"] == "MINGO00":
        simulation_selection = select_mingo00_products(
            lake,
            config["maximum"],
            config["close_parameters"],
            product_factory=Product,
            parquet_basename=parquet_basename,
            acquisition_time=acquisition_time,
        )
        files = simulation_selection.products
        print(
            f"Found {simulation_selection.candidate_count} MINGO00 products with simulation "
            f"metadata; selected tightest parameter cluster of {len(files)} using: "
            + ", ".join(simulation_selection.close_parameters)
        )
        print(f"Parameter-cluster center: {simulation_selection.center_basename}")
        for index, product in enumerate(files, 1):
            param_id = simulation_selection.param_set_id_by_basename[product.basename]
            distance = simulation_selection.distance_by_basename[product.basename]
            values = simulation_selection.values_by_basename[product.basename]
            print(
                f"  {index}. param_set_id={param_id} distance={distance:.6g} "
                f"{product.basename}  {values}"
            )
    else:
        candidates = discover(lake, config["start"], config["end"])
        files = tightest_block(candidates, config["maximum"])
        print(f"Found {len(candidates)} files in range; selected tightest consecutive block of {len(files)}:")
        for index, product in enumerate(files, 1):
            print(f"  {index}. {product.acquired}  {product.basename}")
        if len(files) > 1:
            print(f"Acquisition-start span: {files[-1].acquired - files[0].acquired}")
    available, types = schemas(files)
    show_columns(available, types)

    hist_names = histogram_columns(config, available)
    grids = histogram_grids(config, available)
    pairs = scatter_pairs(config)
    scatter_grid_specs = scatter_grids(config, available)
    rate_setting = rate_timeseries_setting(config, available)
    plane_matrix_enabled = bool(config.get("plane_pair_matrix", False))
    plane_columns = plane_matrix_columns() if plane_matrix_enabled else []
    missing_plane_columns = [name for name in plane_columns if name not in available]
    if missing_plane_columns:
        print(
            "Warning: skipping per-plane pair matrix because products predate "
            "plane-X persistence; reprocess from Task 3. Missing: "
            + ", ".join(missing_plane_columns)
        )
        plane_matrix_enabled = False
        plane_columns = []
    missing = list(dict.fromkeys(name for pair in pairs for name in pair if name not in available))
    if missing:
        raise ValueError("Scatter columns absent from schema: " + ", ".join(missing))
    if (
        not hist_names and not grids and not pairs and not scatter_grid_specs
        and not plane_matrix_enabled and rate_setting is None
    ):
        raise ValueError(
            "Configure at least one histogram, histogram grid, scatter, scatter grid, "
            "plane matrix, or rate time series"
        )
    print(
        f"Resolved {len(hist_names)} standalone histograms, {len(grids)} 4x4 grids, "
        f"{len(pairs)} standalone scatter pairs, {len(scatter_grid_specs)} 4x4 scatter grids, "
        f"{int(plane_matrix_enabled)} per-plane pair matrix, and "
        f"{int(rate_setting is not None)} rate time series"
    )
    for name in hist_names:
        print(f"  HIST {name}")
    for suffix, label, _columns in grids:
        print(f"  GRID suffix={suffix} label={label}")
    for x_name, y_name in pairs:
        print(f"  SCATTER x={x_name} y={y_name}")
    for x_suffix, y_suffix, _x_label, _y_label, _columns in scatter_grid_specs:
        print(f"  SCATTER GRID x_suffix={x_suffix} y_suffix={y_suffix}")
    if plane_matrix_enabled:
        print("  PLANE PAIR MATRIX variables=Q_sum,Q_dif,T_sum,X,Y (4x10)")
    if rate_setting is not None:
        print(
            f"  RATE SERIES accumulation={rate_setting['window']} "
            f"after={' & '.join(rate_setting['filter_columns'])}"
        )
    grid_columns = [name for _suffix, _label, columns in grids for name in columns]
    scatter_grid_columns = [
        name for _x, _y, _xl, _yl, columns in scatter_grid_specs for name in columns
    ]
    rate_columns = (
        [] if rate_setting is None
        else [rate_setting["time_column"], *rate_setting["filter_columns"]]
    )
    configured_plane_columns = plane_limit_columns(config, available)
    needed = list(dict.fromkeys([
        *hist_names, *grid_columns, *scatter_grid_columns, *plane_columns,
        *configured_plane_columns, *rate_columns,
        *(name for pair in pairs for name in pair),
    ]))
    frame = read_events(files, needed)
    apply_calibrated_limits(frame, config)
    apply_per_plane_limits(frame, config)

    bins = int(config.get("histogram_bins", 120))
    point_limit = int(config.get("scatter_max_points_per_file", 25000))
    if bins < 1 or point_limit < 1:
        raise ValueError("Histogram bins and scatter point limit must be positive")
    quantiles = quantile_setting(config)
    interval = (
        "PARAMETER_CLOSE"
        if simulation_selection is not None
        else "{}_{}".format(
            config["start"].strftime("%Y%m%d_%H%M%S"),
            config["end"].strftime("%Y%m%d_%H%M%S"),
        )
    )
    group = f"{files[0].basename}_{files[-1].basename}"
    output = root / "STAGE_1_PRODUCTS_TESTS" / OUTPUT_NAME / f"{interval}_{group}"
    hist_dir, scatter_dir = output / "HISTOGRAMS", output / "SCATTERS"
    rate_dir = output / "RATE_TIMESERIES"
    for directory in (hist_dir, scatter_dir, rate_dir):
        directory.mkdir(parents=True, exist_ok=True)
    # This test output is reproducible; remove obsolete plots when the config changes.
    for directory in (hist_dir, scatter_dir, rate_dir):
        for pattern in ("*.png", "*.csv"):
            for old_plot in directory.glob(pattern):
                old_plot.unlink()
    manifest = pd.DataFrame([
        {"selection_order": index, "station": config["station_name"],
         "filename_base": item.basename, "acquisition_datetime": item.acquired,
         "rows": pq.ParquetFile(item.path).metadata.num_rows, "path": str(item.path),
         **(
             simulation_selection.manifest_fields(item.basename)
             if simulation_selection is not None
             else {"selection_mode": "chronological_minimum_span"}
         )}
        for index, item in enumerate(files, 1)
    ])
    manifest_path = output / "selected_files.csv"; manifest.to_csv(manifest_path, index=False)
    if simulation_selection is not None:
        title = (
            f"{root.name} | {len(files)} simulation-parameter-close files | "
            f"center={simulation_selection.center_basename} | "
            f"parameters={','.join(simulation_selection.close_parameters)}"
        )
    else:
        title = (f"{root.name} | {len(files)} consecutive files | "
                 f"{files[0].acquired:%Y-%m-%d %H:%M:%S} to {files[-1].acquired:%Y-%m-%d %H:%M:%S}")
    selected_start = min(product.acquired for product in files)
    selected_end = max(product.acquired for product in files)
    calibration_paths = generate_calibration_context(
        root,
        selected_start if simulation_selection is not None else config["start"],
        selected_end if simulation_selection is not None else config["end"],
        output / "00_CALIBRATION_CONTEXT",
        title,
        {product.basename for product in files},
        context=config.get("context", "full"),
    )
    log_y = bool(config.get("histogram_log_y", False))
    nhist = sum(
        histogram(frame, files, name, hist_dir / f"hist_{slug(name)}.png",
                  bins, quantiles, log_y, title)
        for name in hist_names
    )
    ngrid = sum(
        histogram_grid(
            frame, files, suffix, label, hist_dir / f"grid_{slug(suffix)}.png",
            bins, quantiles, log_y, title,
        )
        for suffix, label, _columns in grids
    )
    nscatter = sum(scatter(frame, files, x_name, y_name,
                           scatter_dir / f"scatter_{slug(y_name)}_vs_{slug(x_name)}.png",
                           point_limit, quantiles, title) for x_name, y_name in pairs)
    nscatter_grid = sum(
        scatter_grid(
            frame, files, x_suffix, y_suffix, x_label, y_label,
            scatter_dir / f"grid_scatter_{slug(y_suffix)}_vs_{slug(x_suffix)}.png",
            point_limit, quantiles, title,
        )
        for x_suffix, y_suffix, x_label, y_label, _columns in scatter_grid_specs
    )
    nplane_matrix = 0
    if plane_matrix_enabled:
        nplane_matrix = int(plane_pair_matrix(
            frame, files, scatter_dir / "matrix_scatter_plane_observable_pairs.png",
            point_limit, quantiles, title,
        ))
    nrate = 0
    if rate_setting is not None:
        nrate = int(event_rate_timeseries(
            frame, rate_setting,
            rate_dir / "event_rate_before_after_filter.png",
            rate_dir / "event_rate_before_after_filter.csv",
            title,
        ))
    print(f"\nJoined {len(frame):,} event rows")
    print(
        f"Wrote {len(calibration_paths) - 1} calibration context plots, "
        f"{nhist} standalone histograms, {ngrid} histogram grids, "
        f"{nscatter} standalone scatter plots, {nscatter_grid} scatter grids, "
        f"{nplane_matrix} per-plane pair matrix, and {nrate} rate time series"
    )
    print(f"Selected-file manifest: {manifest_path}")
    print(f"Outputs: {output}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
