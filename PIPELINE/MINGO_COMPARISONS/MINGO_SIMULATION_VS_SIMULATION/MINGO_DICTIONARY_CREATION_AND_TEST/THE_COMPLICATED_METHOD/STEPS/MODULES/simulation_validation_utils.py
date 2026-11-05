#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/MODULES/simulation_validation_utils.py
Purpose: Shared utilities for the INFERENCE_DICTIONARY_VALIDATION pipeline.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/MODULES/simulation_validation_utils.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_LOG_FORMAT = "[%(levelname)s] %(name)s — %(message)s"


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a named logger with console handler. Idempotent."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


# ---------------------------------------------------------------------------
# Output directory helpers
# ---------------------------------------------------------------------------

def setup_output_dirs(base_dir: Path) -> tuple[Path, Path]:
    """Create and return (files_dir, plots_dir) under *base_dir*/OUTPUTS.

    Layout::

        base_dir/OUTPUTS/FILES/   ← CSVs, JSONs, markdown reports
        base_dir/OUTPUTS/PLOTS/   ← PNG figures

    Both directories are created if they do not exist.
    """
    files_dir = base_dir / "OUTPUTS" / "FILES"
    plots_dir = base_dir / "OUTPUTS" / "PLOTS"
    files_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)
    return files_dir, plots_dir


# ---------------------------------------------------------------------------
# Global plot style
# ---------------------------------------------------------------------------

def apply_clean_style() -> None:
    """Apply a clean, minimal matplotlib style for all pipeline plots."""
    import matplotlib as mpl
    mpl.rcParams.update({
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.constrained_layout.use": True,
        "figure.figsize": (7, 4.5),
    })


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def load_config(path: Path) -> dict:
    """Read a JSON config file; return empty dict when missing."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_param(cli_value, config: dict, key: str, default, cast=str):
    """Apply the CLI > config > default precedence rule for a parameter.

    Parameters
    ----------
    cli_value : Any
        Value from argparse (``None`` means *not provided*).
    config : dict
        Loaded config JSON.
    key : str
        Config key name.
    default : Any
        Hard-coded fallback.
    cast : callable
        Type coercion applied to the resolved value.
    """
    if cli_value is not None:
        return cast(cli_value)
    return cast(config.get(key, default))


def parse_list(value: object, cast=float) -> list:
    """Parse a value into a list of *cast* items.

    Accepts ``None``, a list/tuple, a JSON-style string (``"[1,2,3]"``), or a
    comma-separated string.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [cast(v) for v in value]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (list, tuple)):
                return [cast(v) for v in parsed]
        except (SyntaxError, ValueError):
            pass
    return [cast(v.strip()) for v in text.split(",") if v.strip()]


# ---------------------------------------------------------------------------
# Efficiency parsing and estimation
# ---------------------------------------------------------------------------

def parse_efficiencies(value: object) -> list[float]:
    """Parse a stringified ``[e1, e2, e3, e4]`` into four floats.

    Returns ``[nan, nan, nan, nan]`` when parsing fails.
    """
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        return [float(value[i]) for i in range(4)]
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return [np.nan] * 4
        if isinstance(parsed, (list, tuple)) and len(parsed) >= 4:
            return [float(parsed[i]) for i in range(4)]
    return [np.nan] * 4


def extract_eff_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``eff_1..eff_4`` columns from the ``efficiencies`` column."""
    df = df.copy()
    if "efficiencies" not in df.columns:
        return df
    effs = df["efficiencies"].apply(parse_efficiencies)
    for i in range(1, 5):
        df[f"eff_{i}"] = effs.apply(lambda x, idx=i - 1: x[idx])
    return df


def compute_efficiency(
    n_four: pd.Series,
    n_three_missing: pd.Series,
    method: str,
) -> pd.Series:
    """Estimate single-plane efficiency from topology counts.

    Parameters
    ----------
    n_four : pd.Series
        Counts that triggered all four planes.
    n_three_missing : pd.Series
        Counts that missed one specific plane.
    method : str
        ``"four_over_three_plus_four"`` or ``"one_minus_three_over_four"``.
    """
    if method == "four_over_three_plus_four":
        return n_four / (n_four + n_three_missing)
    if method == "one_minus_three_over_four":
        return 1.0 - (n_three_missing / n_four.replace({0: np.nan}))
    raise ValueError(f"Unsupported efficiency method: {method}")


def normalize_tt_prefix(prefix: str) -> str:
    """Normalize trigger prefix so both 'raw' and 'raw_tt_' are accepted."""
    p = str(prefix).strip()
    if not p:
        raise ValueError("Trigger prefix cannot be empty.")
    if p.endswith("_tt_"):
        return p
    if p.endswith("_tt"):
        return f"{p}_"
    if p.endswith("_"):
        return f"{p}tt_"
    return f"{p}_tt_"


def build_empirical_eff(
    df: pd.DataFrame, prefix: str, eff_method: str
) -> pd.DataFrame:
    """Compute estimated per-plane efficiencies from topology count columns."""
    tt_prefix = normalize_tt_prefix(prefix)
    four_col = f"{tt_prefix}1234_count"
    miss_cols = {
        1: f"{tt_prefix}234_count",
        2: f"{tt_prefix}134_count",
        3: f"{tt_prefix}124_count",
        4: f"{tt_prefix}123_count",
    }
    needed = [four_col, *miss_cols.values()]
    missing = [col for col in needed if col not in df.columns]
    if missing:
        raise KeyError(f"Missing columns for empirical efficiency: {missing}")
    out = pd.DataFrame(index=df.index)
    for plane, miss_col in miss_cols.items():
        out[f"eff_est_p{plane}"] = compute_efficiency(
            df[four_col], df[miss_col], eff_method
        )
    return out


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def safe_numeric(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    """Coerce *columns* to numeric, ignoring errors."""
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def find_join_col(left: pd.DataFrame, right: pd.DataFrame) -> str | None:
    """Return the first shared join key (``file_name`` or ``filename_base``)."""
    for candidate in ("file_name", "filename_base"):
        if candidate in left.columns and candidate in right.columns:
            return candidate
    return None


def as_float(value: object) -> float:
    """Convert *value* to float; return ``nan`` on failure."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return np.nan
    return out if np.isfinite(out) else np.nan


def safe_rel_error_pct(delta: float, truth: float) -> float:
    """Relative error in percent, guarded against zero/nan."""
    if not np.isfinite(delta) or not np.isfinite(truth) or truth == 0:
        return np.nan
    return float(delta / truth * 100.0)


def coerce_bool_series(series: pd.Series) -> pd.Series:
    """Robust parser for boolean columns loaded from CSV text."""
    if series.dtype == bool:
        return series
    text = series.astype(str).str.strip().str.lower()
    true_vals = {"1", "true", "t", "yes", "y"}
    false_vals = {"0", "false", "f", "no", "n"}
    out = pd.Series(np.nan, index=series.index, dtype="object")
    out[text.isin(true_vals)] = True
    out[text.isin(false_vals)] = False
    return out


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def l2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Euclidean norm of residuals."""
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    if mask.sum() < 2:
        return np.nan
    diff = y_true[mask] - y_pred[mask]
    return float(np.sqrt(np.sum(diff ** 2)))


def chi2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Sum of squared residuals weighted by max(y_true, 1)."""
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    if mask.sum() < 2:
        return np.nan
    y_t = y_true[mask]
    y_p = y_pred[mask]
    # Poisson variance estimate: max(|observed|, 1) prevents division by zero
    variance_floor = np.maximum(np.abs(y_t), 1.0)
    return float(np.sum((y_t - y_p) ** 2 / variance_floor))


def poisson_deviance(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Poisson deviance–like score."""
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    if mask.sum() < 2:
        return np.nan
    y_t = np.maximum(y_true[mask], 0.0)
    y_p = np.maximum(y_pred[mask], 1e-12)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(y_t > 0, y_t / y_p, 1.0)
        term = np.where(y_t > 0, y_t * np.log(ratio) - (y_t - y_p), y_p)
    return float(2.0 * np.sum(term))


def r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Coefficient of determination (R²)."""
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    if mask.sum() < 2:
        return np.nan
    y_t = y_true[mask]
    y_p = y_pred[mask]
    denom = np.sum((y_t - y_t.mean()) ** 2)
    if denom == 0:
        return np.nan
    return 1.0 - float(np.sum((y_t - y_p) ** 2) / denom)


SCORE_FNS = {
    "l2": l2_score,
    "chi2": chi2_score,
    "poisson": poisson_deviance,
    "r2": r2_score,
}

#: Metrics where lower values indicate better matches.
LOWER_IS_BETTER = {"l2", "chi2", "poisson"}


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------

_DEFAULT_HIST_COLOR = "#4C78A8"
_DEFAULT_SCATTER_COLOR = "#F58518"


def maybe_log_x(ax: plt.Axes, values) -> None:
    """Switch *ax* to log-x scale when the data spans >= 2 decades."""
    vals = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    vals = vals[vals > 0]
    if vals.empty:
        return
    vmin, vmax = float(vals.min()), float(vals.max())
    if vmax / vmin >= 100.0:
        ax.set_xscale("log")


def plot_histogram(
    df: pd.DataFrame,
    column: str,
    plot_path: Path,
    *,
    bins: int = 40,
    color: str = _DEFAULT_HIST_COLOR,
    density: bool = False,
    log_y: bool = False,
    xlabel: str | None = None,
    ylabel: str | None = None,
    title: str | None = None,
) -> None:
    """Single-column histogram with sensible defaults."""
    series = pd.to_numeric(df.get(column), errors="coerce").dropna()
    if series.empty:
        return
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.hist(series, bins=bins, density=density, color=color, alpha=0.85, edgecolor="white")
    ax.set_xlabel(xlabel or column)
    ax.set_ylabel(ylabel or ("Density" if density else "Count"))
    ax.set_title(title or f"Distribution of {column}")
    if log_y:
        ax.set_yscale("log")
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=140)
    plt.close(fig)


def plot_scatter(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    plot_path: Path,
    *,
    color: str = _DEFAULT_SCATTER_COLOR,
    size: float = 12,
    alpha: float = 0.6,
    title: str | None = None,
) -> None:
    """Two-column scatter plot."""
    x = pd.to_numeric(df.get(x_col), errors="coerce")
    y = pd.to_numeric(df.get(y_col), errors="coerce")
    mask = x.notna() & y.notna()
    if mask.sum() < 2:
        return
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(x[mask], y[mask], s=size, alpha=alpha, color=color)
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.set_title(title or f"{y_col} vs {x_col}")
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=140)
    plt.close(fig)


def plot_histogram_overlay(
    used_df: pd.DataFrame,
    unused_df: pd.DataFrame,
    column: str,
    plot_path: Path,
    title: str,
    *,
    bins: int = 40,
    log_y: bool = True,
) -> None:
    """Overlay histograms for *used* vs *unused* subsets."""
    used = pd.to_numeric(used_df.get(column), errors="coerce").dropna()
    unused = pd.to_numeric(unused_df.get(column), errors="coerce").dropna()
    if used.empty and unused.empty:
        return
    fig, ax = plt.subplots(figsize=(7, 5))
    if not used.empty:
        ax.hist(used, bins=bins, density=True, color="#54A24B", alpha=0.65, label="used")
    if not unused.empty:
        ax.hist(unused, bins=bins, density=True, color="#E45756", alpha=0.55, label="unused")
    ax.set_xlabel(column)
    ax.set_ylabel("Density")
    ax.set_title(title)
    if log_y:
        ax.set_yscale("log")
    ax.grid(True, alpha=0.2)
    ax.legend(frameon=True, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=140)
    plt.close(fig)


def plot_scatter_overlay(
    used_df: pd.DataFrame,
    unused_df: pd.DataFrame,
    x_col: str,
    y_col: str,
    plot_path: Path,
    title: str,
) -> None:
    """Scatter overlay for *used* vs *unused* subsets."""
    used_x = pd.to_numeric(used_df.get(x_col), errors="coerce")
    used_y = pd.to_numeric(used_df.get(y_col), errors="coerce")
    unused_x = pd.to_numeric(unused_df.get(x_col), errors="coerce")
    unused_y = pd.to_numeric(unused_df.get(y_col), errors="coerce")
    used_mask = used_x.notna() & used_y.notna()
    unused_mask = unused_x.notna() & unused_y.notna()
    if used_mask.sum() + unused_mask.sum() < 2:
        return
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(
        used_x[used_mask], used_y[used_mask],
        s=12, alpha=0.6, color="#54A24B", label="used",
    )
    ax.scatter(
        unused_x[unused_mask], unused_y[unused_mask],
        s=12, alpha=0.45, color="#E45756", label="unused",
    )
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.set_title(title)
    ax.grid(True, alpha=0.2)
    ax.legend(frameon=True, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=140)
    plt.close(fig)


def plot_bar_counts(
    labels: list[str],
    values: list[int],
    colors: list[str],
    title: str,
    plot_path: Path,
) -> None:
    """Simple bar chart of counts."""
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(labels, values, color=colors)
    ax.set_ylabel("Rows")
    ax.set_title(title)
    ax.grid(True, axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=140)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Geometry helpers (convex hull, nearest-neighbor)
# ---------------------------------------------------------------------------

def convex_hull(points: np.ndarray) -> np.ndarray:
    """Andrew's monotone-chain convex hull (2-D points)."""
    if len(points) <= 1:
        return points.copy()
    pts = np.unique(points, axis=0)
    if len(pts) <= 1:
        return pts

    pts_list = sorted((float(x), float(y)) for x, y in pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts_list:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper: list[tuple[float, float]] = []
    for p in reversed(pts_list):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return np.array(lower[:-1] + upper[:-1], dtype=float)


def polygon_area(poly: np.ndarray) -> float:
    """Shoelace formula for a simple polygon."""
    if len(poly) < 3:
        return 0.0
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def nearest_neighbor_distances(
    points: np.ndarray, chunk_size: int = 512
) -> np.ndarray:
    """Per-point nearest-neighbor distances (brute force, chunked)."""
    n = len(points)
    if n < 2:
        return np.full(n, np.nan)
    out = np.full(n, np.nan, dtype=float)
    for start in range(0, n, chunk_size):
        end = min(n, start + chunk_size)
        block = points[start:end]
        diff = block[:, None, :] - points[None, :, :]
        dist2 = np.sum(diff * diff, axis=2)
        row_idx = np.arange(end - start)
        col_idx = np.arange(start, end)
        dist2[row_idx, col_idx] = np.inf
        out[start:end] = np.sqrt(np.min(dist2, axis=1))
    return out


def min_distance_to_points(
    queries: np.ndarray, points: np.ndarray, chunk_size: int = 1024
) -> np.ndarray:
    """For each query point, the distance to the nearest point in *points*."""
    if len(points) == 0:
        return np.full(len(queries), np.nan)
    out = np.full(len(queries), np.nan, dtype=float)
    for start in range(0, len(queries), chunk_size):
        end = min(len(queries), start + chunk_size)
        q = queries[start:end]
        diff = q[:, None, :] - points[None, :, :]
        dist2 = np.sum(diff * diff, axis=2)
        out[start:end] = np.sqrt(np.min(dist2, axis=1))
    return out


# ---------------------------------------------------------------------------
# Uncertainty table builder (used by STEP_3 and STEP_4)
# ---------------------------------------------------------------------------

def build_uncertainty_table(
    df: pd.DataFrame,
    n_bins: int = 10,
    min_bin_count: int = 1,
) -> pd.DataFrame:
    """Bin samples by event count and compute error quantiles per bin.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain ``sample_events_count``, ``abs_flux_rel_error_pct``,
        ``abs_eff_rel_error_pct``.
    n_bins : int
        Number of quantile-based event-count bins.
    min_bin_count : int
        Minimum samples per bin to include in the output.
    """
    cols = ["sample_events_count", "abs_flux_rel_error_pct", "abs_eff_rel_error_pct"]
    work = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    work = work[work["sample_events_count"] > 0]
    if len(work) < max(5, min_bin_count):
        return pd.DataFrame()

    quantiles = np.linspace(0.0, 1.0, max(2, n_bins) + 1)
    edges = np.unique(
        work["sample_events_count"].quantile(quantiles).to_numpy(dtype=float)
    )
    if len(edges) < 3:
        vmin = float(work["sample_events_count"].min())
        vmax = float(work["sample_events_count"].max())
        if vmax <= vmin:
            return pd.DataFrame()
        edges = np.linspace(vmin, vmax, min(6, max(3, n_bins)) + 1)

    work = work.copy()
    work["events_bin"] = pd.cut(
        work["sample_events_count"],
        bins=edges,
        include_lowest=True,
        duplicates="drop",
    )

    rows: list[dict[str, object]] = []
    grouped = work.groupby("events_bin", observed=True)
    for bin_key, part in grouped:
        if len(part) < min_bin_count:
            continue
        flux = part["abs_flux_rel_error_pct"].to_numpy(dtype=float)
        eff = part["abs_eff_rel_error_pct"].to_numpy(dtype=float)
        rows.append(
            {
                "events_bin": str(bin_key),
                "n_samples": int(len(part)),
                "events_min": float(part["sample_events_count"].min()),
                "events_max": float(part["sample_events_count"].max()),
                "events_median": float(part["sample_events_count"].median()),
                "flux_abs_rel_err_pct_median": float(np.nanmedian(flux)),
                "flux_abs_rel_err_pct_p50": float(np.nanpercentile(flux, 50)),
                "flux_abs_rel_err_pct_p68": float(np.nanpercentile(flux, 68)),
                "flux_abs_rel_err_pct_p90": float(np.nanpercentile(flux, 90)),
                "flux_abs_rel_err_pct_p95": float(np.nanpercentile(flux, 95)),
                "eff_abs_rel_err_pct_median": float(np.nanmedian(eff)),
                "eff_abs_rel_err_pct_p50": float(np.nanpercentile(eff, 50)),
                "eff_abs_rel_err_pct_p68": float(np.nanpercentile(eff, 68)),
                "eff_abs_rel_err_pct_p90": float(np.nanpercentile(eff, 90)),
                "eff_abs_rel_err_pct_p95": float(np.nanpercentile(eff, 95)),
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("events_min").reset_index(drop=True)


# ── validation-table builder (shared by STEP_2 and STEP_3) ─────────────

def build_validation_table(
    df: pd.DataFrame, prefix: str, eff_method: str
) -> pd.DataFrame:
    """Build a per-file validation table with estimated & simulated efficiencies.

    For each detector plane the function computes the estimated efficiency
    from four-fold / missing-plane counts and compares it to the simulated
    (true) efficiency embedded in the dictionary CSV.

    Parameters
    ----------
    df : DataFrame
        Dictionary CSV loaded as a DataFrame (must contain trigger counts,
        ``flux_cm2_min``, ``cos_n``, ``efficiencies``).
    prefix : str
        Trigger-column prefix (e.g. ``"raw"`` or ``"raw_tt_"``).
    eff_method : str
        Efficiency estimator name (``"four_over_three_plus_four"`` or
        ``"one_minus_three_over_four"``).

    Returns
    -------
    DataFrame with estimated/simulated efficiencies, residuals and
    relative errors for each plane.
    """
    tt_prefix = normalize_tt_prefix(prefix)
    four_col = f"{tt_prefix}1234_count"
    miss_cols = {
        1: f"{tt_prefix}234_count",
        2: f"{tt_prefix}134_count",
        3: f"{tt_prefix}124_count",
        4: f"{tt_prefix}123_count",
    }
    rate_cols = [
        col for col in df.columns
        if col.startswith(tt_prefix) and col.endswith("_rate_hz")
    ]

    needed = [four_col, *miss_cols.values(), "flux_cm2_min", "cos_n",
              "efficiencies"]
    missing = [col for col in needed if col not in df.columns]
    if missing:
        raise KeyError(
            "Dictionary CSV is missing required columns for validation: "
            + ", ".join(missing)
        )

    out = df.copy()

    # Normalise event-count column name
    event_count_candidates = [
        "generated_events_count", "total_events_generated",
        "n_events_generated", "num_events_generated",
        "event_count", "num_events", "selected_rows",
    ]
    source_event_col = next(
        (c for c in event_count_candidates if c in out.columns), None)
    if (source_event_col is not None
            and source_event_col != "generated_events_count"):
        log.info("Event count column resolved via fallback: '%s'.", source_event_col)
        out["generated_events_count"] = out[source_event_col]

    numeric_cols = [four_col, *miss_cols.values(), "flux_cm2_min", "cos_n",
                    *rate_cols, "generated_events_count"]
    out = safe_numeric(out, numeric_cols)

    sim_eff = (out["efficiencies"]
               .apply(parse_efficiencies)
               .apply(pd.Series))
    sim_eff.columns = [f"eff_sim_p{i}" for i in range(1, 5)]
    out = pd.concat([out, sim_eff], axis=1)

    for plane in range(1, 5):
        miss_col = miss_cols[plane]
        est_col  = f"eff_est_p{plane}"
        sim_col  = f"eff_sim_p{plane}"
        resid_col = f"eff_resid_p{plane}"
        rel_col  = f"eff_rel_err_p{plane}"
        out[est_col] = compute_efficiency(
            out[four_col], out[miss_col], eff_method)
        out[resid_col] = out[est_col] - out[sim_col]
        out[f"eff_abs_err_p{plane}"] = out[resid_col].abs()
        out[rel_col] = out[resid_col] / out[sim_col].replace({0: np.nan})

    if rate_cols:
        out["global_trigger_rate_hz"] = out[rate_cols].sum(
            axis=1, min_count=1)
    else:
        out["global_trigger_rate_hz"] = np.nan

    keep_cols = [
        "file_name", "filename_base", "param_set_id",
        "flux_cm2_min", "cos_n", "generated_events_count",
        four_col, *miss_cols.values(), "global_trigger_rate_hz",
    ]
    keep_cols += [f"eff_sim_p{i}" for i in range(1, 5)]
    keep_cols += [f"eff_est_p{i}" for i in range(1, 5)]
    keep_cols += [f"eff_resid_p{i}" for i in range(1, 5)]
    keep_cols += [f"eff_rel_err_p{i}" for i in range(1, 5)]
    keep_cols += [f"eff_abs_err_p{i}" for i in range(1, 5)]

    for col in keep_cols:
        if col not in out.columns:
            out[col] = np.nan
    return out[keep_cols].copy()
