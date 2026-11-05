#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_2_INFERENCE/STEP_2_3_UNCERTAINTY/build_uncertainty_lut.py
Purpose: STEP 2.3 — Build uncertainty LUT and essential diagnostics.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-12
Runtime: python3
Usage: python3 PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_2_INFERENCE/STEP_2_3_UNCERTAINTY/build_uncertainty_lut.py [options]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ── Paths ────────────────────────────────────────────────────────────────
STEP_DIR = Path(__file__).resolve().parent
INFERENCE_DIR = STEP_DIR.parent
PIPELINE_DIR = INFERENCE_DIR.parent
PROJECT_DIR = PIPELINE_DIR.parent
DEFAULT_CONFIG = (
    PIPELINE_DIR / "STEP_1_SETUP" / "STEP_1_1_COLLECT_DATA" / "INPUTS" / "config_step_1.1_method.json"
)

DEFAULT_VALIDATION = (
    INFERENCE_DIR / "STEP_2_2_VALIDATION" / "OUTPUTS" / "FILES" / "validation_results.csv"
)
DEFAULT_DICTIONARY = (
    PIPELINE_DIR
    / "STEP_1_SETUP"
    / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY"
    / "OUTPUTS"
    / "FILES"
    / "dictionary.csv"
)

FILES_DIR = STEP_DIR / "OUTPUTS" / "FILES"
PLOTS_DIR = STEP_DIR / "OUTPUTS" / "PLOTS"
FILES_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

_PLOT_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".pdf",
    ".eps",
    ".tif",
    ".tiff",
    ".bmp",
    ".gif",
    ".webp",
}

_FIGURE_COUNTER = 0
FIGURE_STEP_PREFIX = "2_3"

logging.basicConfig(format="[%(levelname)s] STEP_2.3 — %(message)s", level=logging.INFO)
log = logging.getLogger("STEP_2.3")


def _save_figure(fig: plt.Figure, path: Path, **kwargs) -> None:
    """Save figure with per-script sequential numeric prefix."""
    global _FIGURE_COUNTER
    _FIGURE_COUNTER += 1
    out = Path(path)
    out = out.with_name(f"{FIGURE_STEP_PREFIX}_{_FIGURE_COUNTER}_{out.name}")
    fig.savefig(out, **kwargs)


def _clear_plots_dir() -> None:
    removed = 0
    for candidate in PLOTS_DIR.iterdir():
        if candidate.is_file() and candidate.suffix.lower() in _PLOT_EXTENSIONS:
            try:
                candidate.unlink()
                removed += 1
            except OSError as exc:
                log.warning("Could not remove old plot file %s: %s", candidate, exc)
    log.info("Cleared %d plot file(s) from %s", removed, PLOTS_DIR)


def _load_config(path: Path) -> dict:
    def _merge(base: dict, override: dict) -> dict:
        out = dict(base)
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = _merge(out[k], v)
            else:
                out[k] = v
        return out

    cfg: dict = {}
    if path.exists():
        cfg = json.loads(path.read_text(encoding="utf-8"))
    else:
        log.warning("Config file not found: %s", path)

    plots_path = path.with_name("config_step_1.1_plots.json")
    if plots_path.exists() and plots_path != path:
        cfg = _merge(cfg, json.loads(plots_path.read_text(encoding="utf-8")))
        log.info("Loaded plot config: %s", plots_path)

    runtime_path = path.with_name("config_step_1.1_runtime.json")
    if runtime_path.exists():
        cfg = _merge(cfg, json.loads(runtime_path.read_text(encoding="utf-8")))
        log.info("Loaded runtime overrides: %s", runtime_path)

    return cfg


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _parse_relerr_filter(cfg_value: object) -> tuple[float, float]:
    default = (-5.0, 5.0)
    if not isinstance(cfg_value, (list, tuple)) or len(cfg_value) != 2:
        return default
    try:
        lo = float(cfg_value[0])
        hi = float(cfg_value[1])
    except (TypeError, ValueError):
        return default
    if not np.isfinite(lo) or not np.isfinite(hi):
        return default
    if lo > hi:
        lo, hi = hi, lo
    if lo == hi:
        lo -= 1.0
        hi += 1.0
    return (lo, hi)


def _parse_uncertainty_mode(cfg_value: object) -> str:
    raw = str(cfg_value).strip().lower()
    if raw in {"signed", "signed_relerr", "signed_rel_error", "legacy_signed"}:
        return "signed_relerr"
    return "abs_relerr"


def _parse_quantiles(cfg_value: object) -> list[float]:
    default = [0.50, 0.68, 0.90, 0.95]
    if not isinstance(cfg_value, (list, tuple)):
        return default
    out: list[float] = []
    for q in cfg_value:
        try:
            qf = float(q)
        except (TypeError, ValueError):
            continue
        if np.isfinite(qf) and 0.0 <= qf <= 1.0:
            out.append(qf)
    if not out:
        return default
    seen: set[int] = set()
    dedup: list[float] = []
    for q in out:
        q_label = int(round(q * 100.0))
        if q_label in seen:
            continue
        seen.add(q_label)
        dedup.append(q)
    return dedup if dedup else default


def _parse_bins_per_param(
    cfg_value: object,
    param_names: list[str],
    default_bins: int = 5,
) -> dict[str, int]:
    bins_map: dict[str, int] = {}

    if isinstance(cfg_value, dict):
        fallback = cfg_value.get("__default__", cfg_value.get("default", default_bins))
        try:
            fallback_n = max(1, int(fallback))
        except (TypeError, ValueError):
            fallback_n = max(1, int(default_bins))

        for pname in param_names:
            raw = cfg_value.get(pname, fallback_n)
            try:
                bins_map[pname] = max(1, int(raw))
            except (TypeError, ValueError):
                bins_map[pname] = fallback_n
        return bins_map

    try:
        n = max(1, int(cfg_value))
    except (TypeError, ValueError):
        n = max(1, int(default_bins))
    for pname in param_names:
        bins_map[pname] = n
    return bins_map


def _quantile_edges(series: pd.Series, n_bins: int) -> np.ndarray:
    """Create n_bins from quantiles; fallback to linear bins when needed."""
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return np.array([], dtype=float)

    n_bins = max(1, int(n_bins))
    if n_bins == 1:
        vmin = float(values.min())
        vmax = float(values.max())
        if not np.isfinite(vmin) or not np.isfinite(vmax):
            return np.array([], dtype=float)
        if vmax <= vmin:
            pad = max(1e-6, abs(vmin) * 1e-6)
            return np.array([vmin - pad, vmin + pad], dtype=float)
        return np.array([vmin, vmax], dtype=float)

    q = np.linspace(0.0, 1.0, n_bins + 1)
    edges = np.asarray(values.quantile(q).values, dtype=float)

    if np.any(~np.isfinite(edges)) or np.unique(edges).size != edges.size:
        vmin = float(values.min())
        vmax = float(values.max())
        if not np.isfinite(vmin) or not np.isfinite(vmax):
            return np.array([], dtype=float)
        if vmax <= vmin:
            pad = max(1e-6, abs(vmin) * 1e-6)
            vmin -= pad
            vmax += pad
        edges = np.linspace(vmin, vmax, n_bins + 1, dtype=float)

    for i in range(1, len(edges)):
        if not edges[i] > edges[i - 1]:
            edges[i] = np.nextafter(edges[i - 1], np.inf)
    return edges


def _build_dimension_edges(
    val_df: pd.DataFrame,
    param_names: list[str],
    bins_per_param: dict[str, int],
    n_bins_events: int,
) -> dict[str, np.ndarray]:
    edges: dict[str, np.ndarray] = {}
    dim_names = [f"est_{p}" for p in param_names] + ["n_events"]

    for dim in dim_names:
        if dim not in val_df.columns:
            continue
        series = pd.to_numeric(val_df[dim], errors="coerce").dropna()
        if series.empty:
            continue

        if dim == "n_events":
            n_bins = max(1, int(n_bins_events))
        else:
            pname = dim[len("est_") :]
            n_bins = max(1, int(bins_per_param.get(pname, 1)))

        dim_edges = _quantile_edges(series, n_bins)
        if dim_edges.size >= 2:
            edges[dim] = dim_edges

    return edges


def _assign_multidim_bins(val_df: pd.DataFrame, edges: dict[str, np.ndarray]) -> pd.DataFrame:
    work = val_df.copy()
    for dim, dim_edges in edges.items():
        work[f"_bin_{dim}"] = pd.cut(
            pd.to_numeric(work[dim], errors="coerce"),
            bins=dim_edges,
            include_lowest=True,
            labels=False,
        )

    bin_cols = [f"_bin_{dim}" for dim in edges]
    work = work.dropna(subset=bin_cols).copy()
    for bc in bin_cols:
        work[bc] = work[bc].astype(int)
    return work


def _iqr_outlier_mask(values: np.ndarray, factor: float) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return np.zeros(0, dtype=bool)

    finite = np.isfinite(values)
    if finite.sum() < 4:
        return ~finite

    core = values[finite]
    q1 = np.percentile(core, 25)
    q3 = np.percentile(core, 75)
    iqr = q3 - q1
    lo = q1 - factor * iqr
    hi = q3 + factor * iqr
    out = (values < lo) | (values > hi)
    out |= ~finite
    return out


def _safe_percentile(values: np.ndarray, pct: float) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return np.nan
    return float(np.percentile(arr, pct))


def _detect_param_names(val_df: pd.DataFrame) -> list[str]:
    names: list[str] = []
    for col in val_df.columns:
        if not col.startswith("relerr_") or not col.endswith("_pct"):
            continue
        pname = col[len("relerr_") : -len("_pct")]
        if f"est_{pname}" in val_df.columns:
            names.append(pname)
    # Stable unique order.
    return list(dict.fromkeys(names))


def build_uncertainty_lut(
    val_df: pd.DataFrame,
    param_names: list[str],
    edges: dict[str, np.ndarray],
    quantiles: list[float],
    min_bin_count: int,
    iqr_factor: float,
    relerr_filter_pct: tuple[float, float],
    uncertainty_mode: str,
) -> pd.DataFrame:
    """Build observed-sector LUT with per-parameter uncertainty summaries."""
    if not edges:
        return pd.DataFrame()

    work = _assign_multidim_bins(val_df, edges)
    if work.empty:
        return pd.DataFrame()

    dim_order = list(edges.keys())
    centres = {dim: 0.5 * (arr[:-1] + arr[1:]) for dim, arr in edges.items()}
    bin_cols = [f"_bin_{dim}" for dim in dim_order]

    relerr_min, relerr_max = relerr_filter_pct
    q_labels = [int(round(q * 100.0)) for q in quantiles]

    rows: list[dict[str, float | int]] = []
    grouped = work.groupby(bin_cols, observed=True, sort=True)

    for key, group in grouped:
        if not isinstance(key, tuple):
            key = (int(key),)

        row: dict[str, float | int] = {}
        for dim, bidx in zip(dim_order, key):
            bi = int(bidx)
            row[f"{dim}_bin_idx"] = bi
            c = centres[dim]
            row[f"{dim}_centre"] = float(c[bi]) if 0 <= bi < len(c) else np.nan

        for pname in param_names:
            err_col = f"relerr_{pname}_pct"
            std_col = f"sigma_{pname}_std"
            row[std_col] = np.nan
            row[f"n_samples_raw_{pname}"] = 0
            row[f"n_samples_{pname}"] = 0
            row[f"n_outliers_{pname}"] = 0
            for qlab in q_labels:
                row[f"sigma_{pname}_p{qlab}"] = np.nan

            if err_col not in group.columns:
                continue

            raw = pd.to_numeric(group[err_col], errors="coerce").to_numpy(dtype=float)
            raw = raw[np.isfinite(raw)]
            row[f"n_samples_raw_{pname}"] = int(raw.size)
            if raw.size == 0:
                continue

            in_window = raw[(raw >= relerr_min) & (raw <= relerr_max)]
            row[f"n_samples_{pname}"] = int(in_window.size)
            if in_window.size == 0:
                continue

            outlier_mask = _iqr_outlier_mask(in_window, iqr_factor)
            clean = in_window[~outlier_mask]
            row[f"n_outliers_{pname}"] = int(outlier_mask.sum())
            if clean.size < min_bin_count:
                continue

            if uncertainty_mode == "signed_relerr":
                sigma_source = clean
            else:
                sigma_source = np.abs(clean)

            row[std_col] = float(np.std(sigma_source, ddof=1)) if sigma_source.size > 1 else np.nan
            for q, qlab in zip(quantiles, q_labels):
                row[f"sigma_{pname}_p{qlab}"] = _safe_percentile(sigma_source, q * 100.0)

        rows.append(row)

    lut_df = pd.DataFrame(rows)
    if lut_df.empty:
        return lut_df

    sort_cols = [f"{dim}_bin_idx" for dim in dim_order if f"{dim}_bin_idx" in lut_df.columns]
    if sort_cols:
        lut_df = lut_df.sort_values(sort_cols).reset_index(drop=True)
    return lut_df


def _select_plot_params(config: dict, cfg_23: dict, param_names: list[str]) -> list[str]:
    raw = config.get("plot_parameters", cfg_23.get("plot_parameters", param_names))
    if not isinstance(raw, (list, tuple)):
        return list(param_names)
    selected = [str(p) for p in raw if str(p) in param_names]
    return selected if selected else list(param_names)


def _plot_error_histograms(
    val_df: pd.DataFrame,
    param_names: list[str],
    quantiles: list[float],
    iqr_factor: float,
    relerr_filter_pct: tuple[float, float],
    uncertainty_mode: str,
) -> None:
    lo, hi = relerr_filter_pct
    bins = np.linspace(lo, hi, 61)

    for pname in param_names:
        err_col = f"relerr_{pname}_pct"
        if err_col not in val_df.columns:
            continue

        raw = pd.to_numeric(val_df[err_col], errors="coerce").to_numpy(dtype=float)
        raw = raw[np.isfinite(raw)]
        if raw.size == 0:
            continue

        in_window = raw[(raw >= lo) & (raw <= hi)]
        if in_window.size == 0:
            continue

        outlier_mask = _iqr_outlier_mask(in_window, iqr_factor)
        clean = in_window[~outlier_mask]

        fig, ax = plt.subplots(figsize=(7.2, 4.0))
        ax.hist(
            in_window,
            bins=bins,
            histtype="step",
            color="#4D4D4D",
            linewidth=1.4,
            label=f"Windowed (n={len(in_window)})",
        )
        if clean.size > 0:
            ax.hist(
                clean,
                bins=bins,
                color="#4C78A8",
                alpha=0.65,
                edgecolor="white",
                linewidth=0.3,
                label=f"Filtered (n={len(clean)})",
            )

        for q in quantiles:
            if uncertainty_mode == "signed_relerr":
                qv = _safe_percentile(clean, q * 100.0)
                if np.isfinite(qv):
                    ax.axvline(qv, linestyle="--", linewidth=1.0, color="#2A2A2A", alpha=0.85)
            else:
                qmag = _safe_percentile(np.abs(clean), q * 100.0)
                if np.isfinite(qmag):
                    ax.axvline(-qmag, linestyle="--", linewidth=1.0, color="#2A2A2A", alpha=0.75)
                    ax.axvline(+qmag, linestyle="--", linewidth=1.0, color="#2A2A2A", alpha=0.75)

        ax.set_title(f"{pname}: relative-error distribution")
        ax.set_xlabel("Relative error [%]")
        ax.set_ylabel("Count")
        ax.set_xlim(lo, hi)
        ax.grid(True, alpha=0.22)
        ax.legend(loc="best", fontsize=8)
        fig.tight_layout()
        _save_figure(fig, PLOTS_DIR / f"error_hist_{pname}.png", dpi=180)
        plt.close(fig)


def _plot_lut_heatmaps(
    lut_df: pd.DataFrame,
    edges: dict[str, np.ndarray],
    param_names: list[str],
    quantile: float,
) -> None:
    if lut_df.empty:
        return

    dim_names = list(edges.keys())
    if "n_events" not in dim_names:
        return

    flux_dim = "est_flux_cm2_min" if "est_flux_cm2_min" in dim_names else None
    if flux_dim is None:
        flux_candidates = [d for d in dim_names if d.startswith("est_")]
        flux_dim = flux_candidates[0] if flux_candidates else None

    eff_dim = None
    for p in param_names:
        d = f"est_{p}"
        if d == flux_dim:
            continue
        if p.startswith("eff_") and d in dim_names:
            eff_dim = d
            break
    if eff_dim is None:
        for d in dim_names:
            if d.startswith("est_") and d != flux_dim:
                eff_dim = d
                break

    if flux_dim is None or eff_dim is None:
        return

    flux_edges = edges.get(flux_dim)
    eff_edges = edges.get(eff_dim)
    events_edges = edges.get("n_events")
    if flux_edges is None or eff_edges is None or events_edges is None:
        return

    x_idx_col = f"{flux_dim}_bin_idx"
    y_idx_col = f"{eff_dim}_bin_idx"
    e_idx_col = "n_events_bin_idx"
    if not {x_idx_col, y_idx_col, e_idx_col}.issubset(set(lut_df.columns)):
        return

    n_x = len(flux_edges) - 1
    n_y = len(eff_edges) - 1
    n_e = len(events_edges) - 1
    q_label = int(round(float(quantile) * 100.0))

    for pname in param_names:
        sigma_col = f"sigma_{pname}_p{q_label}"
        if sigma_col not in lut_df.columns:
            continue

        fig, axes = plt.subplots(1, n_e, figsize=(4.8 * n_e, 4.0), squeeze=False, constrained_layout=True)
        row_axes = axes[0]

        x_bin = pd.to_numeric(lut_df[x_idx_col], errors="coerce")
        y_bin = pd.to_numeric(lut_df[y_idx_col], errors="coerce")
        e_bin = pd.to_numeric(lut_df[e_idx_col], errors="coerce")
        sigma = pd.to_numeric(lut_df[sigma_col], errors="coerce")

        finite = x_bin.notna() & y_bin.notna() & e_bin.notna() & sigma.notna()
        vals = sigma[finite].to_numpy(dtype=float)
        if vals.size == 0:
            plt.close(fig)
            continue

        vmin = float(np.nanpercentile(vals, 5))
        vmax = float(np.nanpercentile(vals, 95))
        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin >= vmax:
            vmin = float(np.nanmin(vals))
            vmax = float(np.nanmax(vals))
            if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin >= vmax:
                vmin, vmax = 0.0, 1.0

        last_mesh = None
        for ei in range(n_e):
            ax = row_axes[ei]
            use = finite & (e_bin.astype("Int64") == ei)
            z = np.full((n_y, n_x), np.nan, dtype=float)
            if use.any():
                tmp = pd.DataFrame(
                    {
                        "xb": x_bin[use].astype(int),
                        "yb": y_bin[use].astype(int),
                        "z": sigma[use].astype(float),
                    }
                )
                med = tmp.groupby(["yb", "xb"], observed=True)["z"].median()
                for (yb, xb), zv in med.items():
                    if 0 <= int(yb) < n_y and 0 <= int(xb) < n_x:
                        z[int(yb), int(xb)] = float(zv)

            mesh = ax.pcolormesh(
                flux_edges,
                eff_edges,
                np.ma.masked_invalid(z),
                cmap="YlOrRd",
                shading="flat",
                vmin=vmin,
                vmax=vmax,
            )
            last_mesh = mesh
            lo = float(events_edges[ei])
            hi = float(events_edges[ei + 1])
            ax.set_title(f"n_events [{lo:.0f}, {hi:.0f}]")
            ax.set_xlabel(flux_dim[len("est_") :] if flux_dim.startswith("est_") else flux_dim)
            if ei == 0:
                ax.set_ylabel(eff_dim[len("est_") :] if eff_dim.startswith("est_") else eff_dim)
            ax.grid(True, alpha=0.18)

        if last_mesh is not None:
            fig.colorbar(last_mesh, ax=list(row_axes), label=f"sigma {pname} p{q_label} [%]")

        fig.suptitle(f"LUT heatmap for {pname} (p{q_label})", fontsize=11)
        _save_figure(fig, PLOTS_DIR / f"lut_heatmap_{pname}.png", dpi=170)
        plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="Step 2.3: Build uncertainty LUT from validation results.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--validation-csv", default=None)
    parser.add_argument("--dictionary-csv", default=None)
    args = parser.parse_args()

    _clear_plots_dir()
    cfg = _load_config(Path(args.config))
    cfg_23 = cfg.get("step_2_3", cfg.get("step_3_1", {}))

    val_path = Path(args.validation_csv) if args.validation_csv else DEFAULT_VALIDATION
    dict_path = Path(args.dictionary_csv) if args.dictionary_csv else DEFAULT_DICTIONARY

    if not val_path.exists():
        log.error("Validation CSV not found: %s", val_path)
        return 1

    quantiles = _parse_quantiles(cfg_23.get("quantiles", [0.50, 0.68, 0.90, 0.95]))
    uncertainty_mode = _parse_uncertainty_mode(cfg_23.get("uncertainty_mode", "abs_relerr"))
    relerr_filter_pct = _parse_relerr_filter(cfg_23.get("relerr_filter_pct", [-5.0, 5.0]))
    min_bin_count = max(1, int(cfg_23.get("min_bin_count", 10)))
    iqr_factor = float(cfg_23.get("outlier_iqr_factor", 2.5))
    n_bins_events = max(1, int(cfg_23.get("n_bins_events", 5)))
    exclude_dictionary_entries = _as_bool(cfg_23.get("exclude_dictionary_entries", True))

    val_df = pd.read_csv(val_path, low_memory=False)
    if val_df.empty:
        log.error("Validation CSV is empty: %s", val_path)
        return 1

    param_names = _detect_param_names(val_df)
    if not param_names:
        log.error("No parameter names detected from relerr_<param>_pct + est_<param> columns.")
        return 1

    if exclude_dictionary_entries and "true_is_dictionary_entry" in val_df.columns:
        mask = val_df["true_is_dictionary_entry"].map(_as_bool).fillna(False)
        n_excluded = int(mask.sum())
        val_df = val_df.loc[~mask].copy()
        log.info(
            "Excluded %d dictionary-entry validation rows; using %d rows.",
            n_excluded,
            len(val_df),
        )
    else:
        n_excluded = 0

    if val_df.empty:
        log.error("No validation rows available after filtering.")
        return 1

    bins_per_param = _parse_bins_per_param(cfg_23.get("n_bins_per_param", 5), param_names, default_bins=5)
    edges = _build_dimension_edges(
        val_df=val_df,
        param_names=param_names,
        bins_per_param=bins_per_param,
        n_bins_events=n_bins_events,
    )
    if not edges:
        log.error("No valid bin edges could be built.")
        return 1

    lut_df = build_uncertainty_lut(
        val_df=val_df,
        param_names=param_names,
        edges=edges,
        quantiles=quantiles,
        min_bin_count=min_bin_count,
        iqr_factor=iqr_factor,
        relerr_filter_pct=relerr_filter_pct,
        uncertainty_mode=uncertainty_mode,
    )
    if lut_df.empty:
        log.error("LUT is empty after processing. Adjust bins/min_bin_count/filter settings.")
        return 1

    # Remove stale non-essential legacy side output.
    stale_summary = FILES_DIR / "uncertainty_summary.json"
    if stale_summary.exists():
        try:
            stale_summary.unlink()
        except OSError as exc:
            log.warning("Could not remove stale summary file %s: %s", stale_summary, exc)

    q_labels = [int(round(q * 100.0)) for q in quantiles]
    lut_path = FILES_DIR / "uncertainty_lut.csv"
    header = (
        "# Uncertainty LUT generated from STEP 2.2 validation results\n"
        f"# validation_csv: {val_path}\n"
        f"# dictionary_csv: {dict_path}\n"
        f"# param_names: {param_names}\n"
        f"# quantiles: {quantiles} (labels={q_labels})\n"
        f"# uncertainty_mode: {uncertainty_mode}\n"
        f"# relerr_filter_pct: [{relerr_filter_pct[0]}, {relerr_filter_pct[1]}]\n"
        f"# n_bins_per_param: {bins_per_param}\n"
        f"# n_bins_events: {n_bins_events}\n"
        f"# min_bin_count: {min_bin_count}\n"
        f"# iqr_factor: {iqr_factor}\n"
    )
    with open(lut_path, "w", encoding="utf-8") as f:
        f.write(header)
        lut_df.to_csv(f, index=False)

    meta = {
        "validation_csv": str(val_path),
        "dictionary": str(dict_path),
        "param_names": param_names,
        "quantiles": quantiles,
        "quantile_labels": q_labels,
        "uncertainty_mode": uncertainty_mode,
        "relerr_filter_pct": [relerr_filter_pct[0], relerr_filter_pct[1]],
        "n_bins_param": bins_per_param,
        "n_bins_events": n_bins_events,
        "min_bin_count": min_bin_count,
        "iqr_factor": iqr_factor,
        "exclude_dictionary_entries": bool(exclude_dictionary_entries),
        "excluded_dictionary_rows": int(n_excluded),
        "dimension_bins": {dim: int(len(dim_edges) - 1) for dim, dim_edges in edges.items()},
        "lut_rows": int(len(lut_df)),
    }
    meta_path = FILES_DIR / "uncertainty_lut_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    plot_params = _select_plot_params(cfg, cfg_23, param_names)
    _plot_error_histograms(
        val_df=val_df,
        param_names=plot_params,
        quantiles=quantiles,
        iqr_factor=iqr_factor,
        relerr_filter_pct=relerr_filter_pct,
        uncertainty_mode=uncertainty_mode,
    )
    q_for_heatmap = 0.68 if any(int(round(q * 100.0)) == 68 for q in quantiles) else quantiles[0]
    _plot_lut_heatmaps(
        lut_df=lut_df,
        edges=edges,
        param_names=plot_params,
        quantile=q_for_heatmap,
    )

    log.info("Wrote LUT: %s (%d rows)", lut_path, len(lut_df))
    log.info("Wrote LUT metadata: %s", meta_path)
    log.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
