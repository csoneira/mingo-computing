#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_1_SETUP/STEP_1_1_COLLECT_DATA/collect_data.py
Purpose: STEP 1.1 — Collect simulated data results and match with simulation parameters.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-11
Runtime: python3
Usage: python3 PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_1_SETUP/STEP_1_1_COLLECT_DATA/collect_data.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

# ── Paths ────────────────────────────────────────────────────────────────
STEP_DIR = Path(__file__).resolve().parent
# Support both layouts:
#   - <pipeline>/STEP_1_SETUP/STEP_1_1_COLLECT_DATA
#   - <pipeline>/STEPS/STEP_1_SETUP/STEP_1_1_COLLECT_DATA
if STEP_DIR.parents[1].name == "STEPS":
    PIPELINE_DIR = STEP_DIR.parents[2]
else:
    PIPELINE_DIR = STEP_DIR.parents[1]
REPO_ROOT = PIPELINE_DIR.parent
STEP_ROOT = PIPELINE_DIR if (PIPELINE_DIR / "STEP_1_SETUP").exists() else PIPELINE_DIR / "STEPS"
DEFAULT_CONFIG = (
    STEP_ROOT / "STEP_1_SETUP" / "STEP_1_1_COLLECT_DATA" / "INPUTS" / "config_step_1.1_method.json"
)
DEFAULT_COLUMNS_CONFIG = (
    STEP_ROOT / "STEP_1_SETUP" / "STEP_1_1_COLLECT_DATA" / "INPUTS" / "config_step_1.1_columns.json"
)

FILES_DIR = STEP_DIR / "OUTPUTS" / "FILES"
PLOTS_DIR = STEP_DIR / "OUTPUTS" / "PLOTS"
FILES_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

_FIGURE_COUNTER = 0
FIGURE_STEP_PREFIX = "1_1"


def _save_figure(fig: plt.Figure, path: Path, **kwargs) -> Path:
    """Save figure with a per-script sequential numeric prefix."""
    global _FIGURE_COUNTER
    _FIGURE_COUNTER += 1
    out_path = Path(path)
    out_path = out_path.with_name(f"{FIGURE_STEP_PREFIX}_{_FIGURE_COUNTER}_{out_path.name}")
    fig.savefig(out_path, **kwargs)
    return out_path


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

def _clear_plots_dir() -> None:
    """Remove previously generated plot files from the plots directory."""
    removed = 0
    for candidate in PLOTS_DIR.iterdir():
        if candidate.is_file() and candidate.suffix.lower() in _PLOT_EXTENSIONS:
            try:
                candidate.unlink()
                removed += 1
            except OSError as exc:
                log.warning("Could not remove old plot file %s: %s", candidate, exc)
    log.info("Cleared %d plot file(s) from %s", removed, PLOTS_DIR)


def _parameter_display_label(column: str) -> str:
    labels = {
        "flux_cm2_min": "Flux [cm^-2 min^-1]",
        "cos_n": "cos(theta)",
        "eff_p1": "Plane 1 eff",
        "eff_p2": "Plane 2 eff",
        "eff_p3": "Plane 3 eff",
        "eff_p4": "Plane 4 eff",
        "eff_sim_1": "Plane 1 eff",
        "eff_sim_2": "Plane 2 eff",
        "eff_sim_3": "Plane 3 eff",
        "eff_sim_4": "Plane 4 eff",
    }
    return labels.get(column, column.replace("_", " "))


def _compute_axis_limits(series: pd.Series) -> tuple[float, float] | None:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    lower = float(numeric.min())
    upper = float(numeric.max())
    if not np.isfinite(lower) or not np.isfinite(upper):
        return None
    if lower == upper:
        pad = max(abs(lower) * 0.05, 0.05)
        return lower - pad, upper + pad
    pad = (upper - lower) * 0.04
    return lower - pad, upper + pad


def _plot_parameter_space_overview(
    *,
    collected: pd.DataFrame,
    parameter_space_columns: list[str],
    z_config: list[float],
    cfg_11: dict,
) -> Path | None:
    if collected.empty or not parameter_space_columns:
        return None

    max_columns_raw = cfg_11.get("parameter_space_overview_max_columns", 6)
    max_rows_raw = cfg_11.get("parameter_space_overview_max_rows", 4000)
    point_size = float(cfg_11.get("parameter_space_overview_point_size", 16.0))
    alpha = float(cfg_11.get("parameter_space_overview_alpha", 0.65))
    hist_bins = max(8, int(cfg_11.get("parameter_space_overview_hist_bins", 18)))
    enabled = _as_bool(cfg_11.get("parameter_space_overview_enabled", True), True)
    if not enabled:
        return None

    try:
        max_columns = max(1, int(max_columns_raw))
    except (TypeError, ValueError):
        max_columns = 6
    try:
        max_rows = max(0, int(max_rows_raw))
    except (TypeError, ValueError):
        max_rows = 4000

    plot_columns = [column for column in parameter_space_columns if column in collected.columns][:max_columns]
    if not plot_columns:
        return None

    if len(parameter_space_columns) > len(plot_columns):
        log.info(
            "Parameter-space overview plot limited to first %d column(s): %s",
            len(plot_columns),
            plot_columns,
        )

    plot_df = collected.loc[:, plot_columns].copy()
    for column in plot_columns:
        plot_df[column] = pd.to_numeric(plot_df[column], errors="coerce")
    if "task_id" in collected.columns:
        plot_df["task_id"] = pd.to_numeric(collected["task_id"], errors="coerce").astype("Int64")
    plot_df = plot_df.dropna(how="all", subset=plot_columns).reset_index(drop=True)
    if plot_df.empty:
        return None

    if max_rows > 0 and len(plot_df) > max_rows:
        plot_df = plot_df.sample(n=max_rows, random_state=1234).sort_index().reset_index(drop=True)

    axis_limits = {
        column: _compute_axis_limits(plot_df[column])
        for column in plot_columns
    }
    plot_columns = [column for column in plot_columns if axis_limits.get(column) is not None]
    if not plot_columns:
        return None

    n = len(plot_columns)
    task_ids = []
    if "task_id" in plot_df.columns:
        task_ids = [
            int(task_id)
            for task_id in sorted(plot_df["task_id"].dropna().astype(int).unique().tolist())
        ]
    cmap = plt.get_cmap("tab10")
    task_colors = {
        task_id: cmap(idx % cmap.N)
        for idx, task_id in enumerate(task_ids)
    }
    single_color = "#4C78A8"

    fig, axes = plt.subplots(
        n,
        n,
        figsize=(2.45 * n + 1.8, 2.45 * n + 1.6),
        dpi=130,
    )
    axes_arr = np.asarray(axes).reshape(n, n)

    for row_idx in range(n):
        for col_idx in range(n):
            ax = axes_arr[row_idx, col_idx]
            x_col = plot_columns[col_idx]
            y_col = plot_columns[row_idx]

            ax.grid(True, linestyle=":", linewidth=0.35, alpha=0.3)
            for spine in ax.spines.values():
                spine.set_linewidth(0.6)
            ax.set_box_aspect(1.0)

            if row_idx == col_idx:
                for task_id in task_ids or [None]:
                    if task_id is None:
                        values = plot_df[y_col].dropna()
                        color = single_color
                        label = None
                    else:
                        values = plot_df.loc[plot_df["task_id"] == task_id, y_col].dropna()
                        color = task_colors[task_id]
                        label = f"Task {task_id}"
                    if values.empty:
                        continue
                    ax.hist(
                        values,
                        bins=hist_bins,
                        color=color,
                        alpha=0.45,
                        edgecolor="white",
                        linewidth=0.4,
                        label=label,
                    )
                ax.set_title(_parameter_display_label(y_col), fontsize=9, pad=4)
                ax.autoscale_view(scalex=False, scaley=True)
                ax.set_xlim(axis_limits[y_col])
            elif row_idx > col_idx:
                for task_id in task_ids or [None]:
                    if task_id is None:
                        subset = plot_df[[x_col, y_col]].dropna()
                        color = single_color
                    else:
                        subset = plot_df.loc[plot_df["task_id"] == task_id, [x_col, y_col]].dropna()
                        color = task_colors[task_id]
                    if subset.empty:
                        continue
                    ax.scatter(
                        subset[x_col],
                        subset[y_col],
                        s=point_size,
                        alpha=alpha,
                        color=color,
                        edgecolors="none",
                        rasterized=True,
                    )
                ax.set_xlim(axis_limits[x_col])
                ax.set_ylim(axis_limits[y_col])
            else:
                ax.axis("off")

            if row_idx < n - 1:
                ax.tick_params(axis="x", labelbottom=False)
            else:
                ax.set_xlabel(_parameter_display_label(x_col), fontsize=8)
            if col_idx > 0:
                ax.tick_params(axis="y", labelleft=False)
            else:
                ax.set_ylabel(_parameter_display_label(y_col), fontsize=8)
            ax.tick_params(axis="both", which="major", labelsize=7, width=0.75, length=2.6)

    z_text = ", ".join(f"{float(value):g}" for value in z_config)
    title = (
        "STEP 1.1 parameter-space overview\n"
        f"selected z = [{z_text}] | rows = {len(collected)}"
    )
    fig.suptitle(title, fontsize=11, y=0.98)

    if len(task_ids) > 1:
        handles = [
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="None",
                markersize=6,
                markerfacecolor=task_colors[task_id],
                markeredgecolor="none",
                label=f"Task {task_id}",
            )
            for task_id in task_ids
        ]
        fig.legend(
            handles=handles,
            loc="upper right",
            bbox_to_anchor=(0.98, 0.975),
            framealpha=0.9,
            fontsize=8,
            title="Collected task",
            title_fontsize=9,
        )
        fig.subplots_adjust(left=0.08, right=0.9, bottom=0.08, top=0.9, wspace=0.05, hspace=0.05)
    else:
        fig.subplots_adjust(left=0.08, right=0.98, bottom=0.08, top=0.9, wspace=0.05, hspace=0.05)

    out_path = _save_figure(fig, PLOTS_DIR / "parameter_space_overview.png", dpi=170)
    plt.close(fig)
    return out_path

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    format="[%(levelname)s] STEP_1.1 — %(message)s", level=logging.INFO
)
log = logging.getLogger("STEP_1.1")


# ── Helpers ──────────────────────────────────────────────────────────────

DEFAULT_PARAMETER_SPACE_COLUMNS = (
    "flux_cm2_min",
    "eff_p1",
    "eff_p2",
    "eff_p3",
    "eff_p4",
    "cos_n",
)

def _task_metadata_dir(station_id: int, task_id: int) -> Path:
    """Return the task metadata directory."""
    station = f"MINGO{station_id:02d}"
    return (
        REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / station / "STAGE_1" / "EVENT_DATA"
        / "STEP_1" / f"TASK_{task_id}" / "METADATA"
    )


def _discover_all_task_ids(station_id: int) -> list[int]:
    """Discover all TASK_<id> folders available for the selected station."""
    station = f"MINGO{station_id:02d}"
    base = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / station / "STAGE_1" / "EVENT_DATA" / "STEP_1"
    if not base.exists():
        return []
    out: list[int] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        match = re.match(r"^TASK_(\d+)$", child.name)
        if match is None:
            continue
        out.append(int(match.group(1)))
    return sorted(set(out))


def _task_specific_metadata_path(station_id: int, task_id: int) -> Path:
    return _task_metadata_dir(station_id, task_id) / f"task_{task_id}_metadata_specific.csv"


def _task_trigger_type_metadata_path(station_id: int, task_id: int) -> Path:
    return _task_metadata_dir(station_id, task_id) / f"task_{task_id}_metadata_trigger_type.csv"


def _task_rate_histogram_metadata_path(station_id: int, task_id: int) -> Path:
    return _task_metadata_dir(station_id, task_id) / f"task_{task_id}_metadata_rate_histogram.csv"


def _task_efficiency_metadata_path(station_id: int, task_id: int) -> Path:
    return _task_metadata_dir(station_id, task_id) / f"task_{task_id}_metadata_efficiency.csv"


def _load_config(path: Path) -> dict:
    def _merge_dicts(base: dict, override: dict) -> dict:
        out = dict(base)
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = _merge_dicts(out[k], v)
            else:
                out[k] = v
        return out

    cfg: dict = {}
    if path.exists():
        cfg = json.loads(path.read_text(encoding="utf-8"))
    else:
        log.warning("Config file not found: %s", path)

    columns_path = path.with_name("config_step_1.1_columns.json")
    if columns_path != path and columns_path.exists():
        columns_cfg = json.loads(columns_path.read_text(encoding="utf-8"))
        cfg = _merge_dicts(cfg, columns_cfg)
        log.info("Loaded column-role config: %s", columns_path)

    plots_path = path.with_name("config_step_1.1_plots.json")
    if plots_path != path and plots_path.exists():
        plots_cfg = json.loads(plots_path.read_text(encoding="utf-8"))
        cfg = _merge_dicts(cfg, plots_cfg)
        log.info("Loaded plot config: %s", plots_path)

    runtime_path = path.with_name("config_step_1.1_runtime.json")
    if runtime_path.exists():
        runtime_cfg = json.loads(runtime_path.read_text(encoding="utf-8"))
        cfg = _merge_dicts(cfg, runtime_cfg)
        log.info("Loaded runtime overrides: %s", runtime_path)
    return cfg


def _resolve_input_path(path_like: str | Path) -> Path:
    path = Path(path_like).expanduser()
    if path.is_absolute():
        return path
    candidate_pipeline = PIPELINE_DIR / path
    if candidate_pipeline.exists():
        return candidate_pipeline
    candidate_step = STEP_DIR / path
    if candidate_step.exists():
        return candidate_step
    return candidate_pipeline

def _aggregate_latest(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only the latest execution per filename_base."""
    if "execution_timestamp" in df.columns:
        dt = pd.to_datetime(
            df["execution_timestamp"], format="%Y-%m-%d_%H.%M.%S", errors="coerce"
        )
        df = df.assign(_exec_dt=dt)
        df = df.sort_values(
            ["filename_base", "_exec_dt"], na_position="last", kind="mergesort"
        )
        df = df.groupby("filename_base").tail(1)
        df = df.drop(columns=["_exec_dt"])
    else:
        df = df.groupby("filename_base").tail(1)
    return df


def _safe_task_ids(raw: object) -> list[int]:
    if raw is None:
        return [1]
    if isinstance(raw, (int, float)):
        return [int(raw)]
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return [1]
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = [x.strip() for x in stripped.split(",") if x.strip()]
        raw = parsed
    out: list[int] = []
    if isinstance(raw, (list, tuple)):
        for value in raw:
            try:
                out.append(int(value))
            except (TypeError, ValueError):
                continue
    return sorted(set(out)) or [1]


def _resolve_efficiency_metadata_source_task_id(raw: object, *, default_task_id: int) -> int:
    if raw in (None, "", "null", "None", "same"):
        return int(default_task_id)
    try:
        return int(raw)
    except (TypeError, ValueError):
        log.warning(
            "Invalid step_1_1.efficiency_metadata_source_task_id=%r; using task %d.",
            raw,
            int(default_task_id),
        )
        return int(default_task_id)


def _normalize_string_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, (list, tuple)):
        out: list[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
        return out
    return []


def _as_bool(raw: object, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        text = raw.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return bool(default)


def _resolve_parameter_space_selection(
    params_df: pd.DataFrame,
    *,
    cfg_11: dict,
) -> tuple[list[str], dict]:
    available = list(params_df.columns)
    available_set = set(available)
    auto_candidates = [c for c in DEFAULT_PARAMETER_SPACE_COLUMNS if c in available_set]

    raw_selected = cfg_11.get("parameter_columns", cfg_11.get("parameter_space_columns", "auto"))
    requested: list[str]
    requested_unmatched: list[str] = []
    selection_mode = "auto_default"
    if isinstance(raw_selected, str) and raw_selected.strip().lower() == "auto":
        requested = auto_candidates.copy()
    else:
        requested_raw = _normalize_string_list(raw_selected)
        requested = [c for c in requested_raw if c in available_set]
        requested_unmatched = [c for c in requested_raw if c not in available_set]
        selection_mode = "configured_list"

    excluded = set(_normalize_string_list(cfg_11.get("parameter_space_exclude_columns")))
    drop_constant = _as_bool(
        cfg_11.get("parameter_space_drop_constant_columns", True),
        default=True,
    )
    drop_unselected = _as_bool(
        cfg_11.get("drop_unselected_parameter_columns_from_dataset", True),
        default=True,
    )

    selected: list[str] = []
    excluded_by_config: list[str] = []
    constant_removed: list[str] = []
    for col in requested:
        if col in excluded:
            excluded_by_config.append(col)
            continue
        if drop_constant:
            vals = pd.to_numeric(params_df[col], errors="coerce")
            nunique = int(vals.dropna().nunique())
            if nunique <= 1:
                constant_removed.append(col)
                continue
        selected.append(col)

    selected = list(dict.fromkeys(selected))
    if not selected and auto_candidates:
        fallback = [c for c in auto_candidates if c not in excluded]
        if drop_constant:
            fallback = [
                c
                for c in fallback
                if int(pd.to_numeric(params_df[c], errors="coerce").dropna().nunique()) > 1
            ]
        selected = list(dict.fromkeys(fallback))

    alias_map: dict[str, str] = {}
    for i in range(1, 5):
        pcol = f"eff_p{i}"
        sim_col = f"eff_sim_{i}"
        alias_map[pcol] = sim_col
        alias_map[sim_col] = sim_col
    downstream_preferred: list[str] = []
    for col in selected:
        mapped = alias_map.get(col, col)
        if mapped not in downstream_preferred:
            downstream_preferred.append(mapped)

    columns_removed_from_dataset = []
    if drop_unselected:
        candidate_pool = list(dict.fromkeys(auto_candidates + _normalize_string_list(raw_selected)))
        columns_removed_from_dataset = [
            c for c in candidate_pool if c in available_set and c not in selected
        ]

    info = {
        "selection_mode": selection_mode,
        "parameter_space_columns_requested_raw": raw_selected,
        "parameter_space_columns_available_auto": auto_candidates,
        "parameter_space_columns_requested_unmatched": requested_unmatched,
        "parameter_space_columns_excluded_by_config": excluded_by_config,
        "parameter_space_columns_removed_as_constant": constant_removed,
        "parameter_space_columns_selected": selected,
        "parameter_space_columns_downstream_preferred": downstream_preferred,
        "parameter_space_column_aliases": alias_map,
        "drop_unselected_parameter_columns_from_dataset": bool(drop_unselected),
        "parameter_space_columns_removed_from_dataset": columns_removed_from_dataset,
    }
    return selected, info


def _resolve_event_count_column(df: pd.DataFrame) -> str | None:
    """Return preferred event-count column name if available."""
    base_candidates = (
        "selected_rows",
        "requested_rows",
        "generated_events_count",
        "num_events",
        "event_count",
    )
    for candidate in base_candidates:
        if candidate in df.columns:
            return candidate
    for source in ("trigger_type", "rate_histogram", "specific"):
        for candidate in base_candidates:
            source_col = f"{source}__{candidate}"
            if source_col in df.columns:
                return source_col
    return None


def _load_task_metadata_csv(
    *,
    station_id: int,
    task_id: int,
    source_name: str,
    path: Path,
    metadata_agg: str,
) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing required {source_name} metadata for task {task_id}: {path}"
        )
    log.info("Loading metadata (%s) for task %d: %s", source_name, task_id, path)
    meta_df = pd.read_csv(path, low_memory=False)
    if "filename_base" not in meta_df.columns:
        raise KeyError(
            f"Metadata source '{source_name}' for task {task_id} has no 'filename_base' column."
        )
    if metadata_agg == "latest":
        meta_df = _aggregate_latest(meta_df)
    meta_df = meta_df.groupby("filename_base", sort=False).tail(1).reset_index(drop=True)
    log.info(
        "  %s rows (after aggregation): %d, columns=%d",
        source_name,
        len(meta_df),
        len(meta_df.columns),
    )
    return meta_df


def _merge_metadata_sources_equal_level(
    *,
    task_id: int,
    ordered_sources: list[tuple[str, pd.DataFrame]],
) -> tuple[pd.DataFrame, dict]:
    if not ordered_sources:
        raise ValueError(f"No metadata sources were provided for task {task_id}.")
    merged = ordered_sources[0][1].copy()
    info: dict = {
        "task_id": int(task_id),
        "source_names": [name for name, _ in ordered_sources],
        "rows_per_source_before_merge": {
            name: int(len(df)) for name, df in ordered_sources
        },
        "renamed_overlap_columns": {},
    }

    for source_name, source_df in ordered_sources[1:]:
        overlap = sorted(
            set(merged.columns).intersection(set(source_df.columns)) - {"filename_base"}
        )
        renamed = {}
        if overlap:
            renamed = {col: f"{source_name}__{col}" for col in overlap}
            source_df = source_df.rename(columns=renamed)
        merged = merged.merge(source_df, on="filename_base", how="inner")
        info["renamed_overlap_columns"][source_name] = renamed
        info[f"rows_after_merge_with_{source_name}"] = int(len(merged))
    return merged, info


def _merge_optional_metadata_sources_left(
    *,
    merged: pd.DataFrame,
    info: dict,
    optional_sources: list[tuple[str, pd.DataFrame]],
) -> tuple[pd.DataFrame, dict]:
    out = merged.copy()
    for source_name, source_df in optional_sources:
        overlap = sorted(
            set(out.columns).intersection(set(source_df.columns)) - {"filename_base"}
        )
        renamed = {}
        if overlap:
            renamed = {col: f"{source_name}__{col}" for col in overlap}
            source_df = source_df.rename(columns=renamed)
        out = out.merge(source_df, on="filename_base", how="left")
        info["renamed_overlap_columns"][source_name] = renamed
        info[f"rows_after_left_merge_with_{source_name}"] = int(len(out))
    return out, info


def _normalize_metadata_agg(raw: object) -> str:
    """STEP 1.1 uses a single aggregation policy for determinism."""
    value = str(raw).strip().lower() if raw is not None else "latest"
    if value != "latest":
        log.warning(
            "STEP 1.1 supports only metadata_agg='latest' in simplified mode; got %r, using 'latest'.",
            raw,
        )
    return "latest"


def _select_deterministic_z_config(
    params_df: pd.DataFrame,
    *,
    z_cols: list[str],
) -> tuple[list[float], int]:
    """Select the most populated z configuration (stable deterministic tie-break)."""
    counts = (
        params_df.groupby(z_cols, dropna=False)
        .size()
        .reset_index(name="_n_rows")
        .sort_values(
            ["_n_rows", *z_cols],
            ascending=[False, True, True, True, True],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )
    if counts.empty:
        raise ValueError("No z configurations available in simulation parameters.")
    row = counts.iloc[0]
    z_cfg = [float(row[col]) for col in z_cols]
    return z_cfg, int(row["_n_rows"])


def _parse_efficiency_vector(raw: object) -> tuple[float, float, float, float] | None:
    value = raw
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            try:
                value = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    out: list[float] = []
    for item in value:
        try:
            num = float(item)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(num):
            return None
        out.append(num)
    return (out[0], out[1], out[2], out[3])


def _ensure_efficiency_columns(
    df: pd.DataFrame,
    *,
    source_col: str = "efficiencies",
) -> pd.DataFrame:
    eff_cols = ["eff_p1", "eff_p2", "eff_p3", "eff_p4"]
    if all(col in df.columns for col in eff_cols):
        return df
    if source_col not in df.columns:
        return df

    out = df.copy()
    parsed = out[source_col].map(_parse_efficiency_vector)
    for idx, col in enumerate(eff_cols):
        if col in out.columns:
            continue
        out[col] = parsed.map(lambda v, i=idx: np.nan if v is None else float(v[i]))
    return out


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step 1.1: Collect simulated data and match with simulation parameters."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()

    config = _load_config(Path(args.config))
    _clear_plots_dir()

    station_id = int(config.get("station_id", 0))
    configured_task_ids = _safe_task_ids(config.get("task_ids", [1]))
    discovered_task_ids = _discover_all_task_ids(station_id)
    if not discovered_task_ids:
        log.error(
            "No TASK_<id> directories found for station %d. Cannot collect metadata.",
            station_id,
        )
        return 1
    task_ids = sorted(set(configured_task_ids) & set(discovered_task_ids))
    if not task_ids:
        log.error(
            "None of the configured task_ids=%s exist on disk (discovered=%s).",
            configured_task_ids,
            discovered_task_ids,
        )
        return 1
    ignored = sorted(set(discovered_task_ids) - set(task_ids))
    if ignored:
        log.info(
            "Respecting configured task_ids=%s. Skipping discovered tasks: %s.",
            task_ids,
            ignored,
        )
    cfg_11 = config.get("step_1_1", {})
    efficiency_metadata_source_task_raw = cfg_11.get("efficiency_metadata_source_task_id", None)
    min_rows_raw = cfg_11.get("min_rows_for_dataset", 0)
    try:
        min_rows_for_dataset = max(0, int(min_rows_raw))
    except (TypeError, ValueError):
        log.warning(
            "Invalid step_1_1.min_rows_for_dataset=%r; using 0 (disabled).",
            min_rows_raw,
        )
        min_rows_for_dataset = 0
    default_sim_params_path = (
        REPO_ROOT
        / "PIPELINE" / "MINGO_DIGITAL_TWIN"
        / "SIMULATION_OUTPUTS"
        / "SIMULATED_DATA"
        / "step_final_simulation_params.csv"
    )
    sim_params_path = default_sim_params_path
    sim_params_cfg = config.get("simulation_params_csv", None)
    if sim_params_cfg not in (None, "", "null", "None"):
        sim_params_path = _resolve_input_path(str(sim_params_cfg))
        log.info(
            "Using simulation_params_csv override for STEP 1.1: %s",
            sim_params_path,
        )
    param_mesh_cfg = config.get("param_mesh_csv", None)
    if param_mesh_cfg not in (None, "", "null", "None"):
        log.warning(
            "Ignoring param_mesh_csv (%r). STEP 1.1 no longer applies mesh-support filtering.",
            param_mesh_cfg,
        )
    z_config = config.get("z_position_config", None)
    metadata_agg = _normalize_metadata_agg(config.get("metadata_agg", "latest"))

    # ── Load simulation parameters ───────────────────────────────────
    if not sim_params_path.exists():
        log.error("Simulation params CSV not found: %s", sim_params_path)
        return 1

    log.info("Loading simulation parameters: %s", sim_params_path)
    params_df = pd.read_csv(sim_params_path, low_memory=False)
    params_df["filename_base"] = (
        params_df["file_name"].astype(str).str.replace(r"\.[^.]+$", "", regex=True)
    )
    # Drop the file_name column (user request)
    params_df = params_df.drop(columns=["file_name"], errors="ignore")
    params_df = _ensure_efficiency_columns(params_df)
    log.info("  Simulation params rows: %d", len(params_df))
    log.info(
        "Using step_final_simulation_params.csv as STEP 1.1 source of truth (no mesh filter)."
    )

    # ── Determine z-position configuration ───────────────────────────
    z_cols = ["z_plane_1", "z_plane_2", "z_plane_3", "z_plane_4"]
    unique_z = params_df[z_cols].drop_duplicates().reset_index(drop=True)
    log.info("  Available z configurations (%d):", len(unique_z))
    for i, row in unique_z.iterrows():
        log.info("    [%d] %s", i, list(row.values))

    z_config_selection_seed: int | None = None
    z_config_seed_from_config = False
    z_config_selected_index: int | None = None

    if z_config is not None:
        z_config = [float(v) for v in z_config]
        log.info("  Selecting z config from config: %s", z_config)
    else:
        z_config, n_rows_for_cfg = _select_deterministic_z_config(
            params_df,
            z_cols=z_cols,
        )
        z_match = (
            unique_z[z_cols]
            .apply(
                lambda row: all(
                    np.isclose(float(row[col]), float(val), atol=1e-9)
                    for col, val in zip(z_cols, z_config)
                ),
                axis=1,
            )
        )
        if bool(z_match.any()):
            z_config_selected_index = int(z_match[z_match].index[0])
        log.info(
            "  No z config specified — selected most populated z config (%d rows): %s",
            n_rows_for_cfg,
            z_config,
        )

    # Apply z-position cut
    z_mask = np.ones(len(params_df), dtype=bool)
    for col, val in zip(z_cols, z_config):
        z_mask &= np.isclose(params_df[col].astype(float), val, atol=1e-6)
    params_df = params_df.loc[z_mask].reset_index(drop=True)
    log.info("  Rows after z-position cut: %d", len(params_df))

    if params_df.empty:
        log.error("No rows remain after z-position cut. Check your z_position_config.")
        return 1

    parameter_space_columns, parameter_space_info = _resolve_parameter_space_selection(
        params_df,
        cfg_11=cfg_11,
    )
    if not parameter_space_columns:
        log.error(
            "No parameter-space columns were selected for STEP 1.1. "
            "Set step_1_1.parameter_space_columns to a non-empty list."
        )
        return 1

    drop_unselected = bool(parameter_space_info.get("drop_unselected_parameter_columns_from_dataset", True))
    removed_parameter_columns: list[str] = []
    if drop_unselected:
        to_drop = [
            c
            for c in parameter_space_info.get("parameter_space_columns_removed_from_dataset", [])
            if c in params_df.columns and c != "filename_base"
        ]
        if to_drop:
            params_df = params_df.drop(columns=to_drop, errors="ignore")
            removed_parameter_columns = to_drop
    parameter_space_info["parameter_space_columns_removed_from_dataset"] = removed_parameter_columns

    log.info("Parameter-space columns selected: %s", parameter_space_columns)
    if removed_parameter_columns:
        log.info(
            "Removed non-selected parameter columns from STEP 1.1 dataset: %s",
            removed_parameter_columns,
        )

    # ── Collect metadata for each task and merge ─────────────────────
    all_merged: list[pd.DataFrame] = []

    for task_id in task_ids:
        specific_path = _task_specific_metadata_path(station_id, task_id)
        trigger_path = _task_trigger_type_metadata_path(station_id, task_id)
        rate_hist_path = _task_rate_histogram_metadata_path(station_id, task_id)
        efficiency_source_task_id = _resolve_efficiency_metadata_source_task_id(
            efficiency_metadata_source_task_raw,
            default_task_id=task_id,
        )
        efficiency_path = _task_efficiency_metadata_path(station_id, efficiency_source_task_id)
        try:
            trigger_df = _load_task_metadata_csv(
                station_id=station_id,
                task_id=task_id,
                source_name="trigger_type",
                path=trigger_path,
                metadata_agg=metadata_agg,
            )
            rate_hist_df = _load_task_metadata_csv(
                station_id=station_id,
                task_id=task_id,
                source_name="rate_histogram",
                path=rate_hist_path,
                metadata_agg=metadata_agg,
            )
            specific_df = _load_task_metadata_csv(
                station_id=station_id,
                task_id=task_id,
                source_name="specific",
                path=specific_path,
                metadata_agg=metadata_agg,
            )
        except (FileNotFoundError, KeyError) as exc:
            log.error("%s", exc)
            return 1

        optional_sources: list[tuple[str, pd.DataFrame]] = []
        if efficiency_path.exists():
            try:
                efficiency_df = _load_task_metadata_csv(
                    station_id=station_id,
                    task_id=efficiency_source_task_id,
                    source_name="efficiency",
                    path=efficiency_path,
                    metadata_agg=metadata_agg,
                )
            except (FileNotFoundError, KeyError) as exc:
                log.error("%s", exc)
                return 1
            if not efficiency_df.empty:
                optional_sources.append(("efficiency", efficiency_df))
            else:
                log.warning(
                    "Optional efficiency metadata is empty for task %d (source task %d): %s",
                    task_id,
                    efficiency_source_task_id,
                    efficiency_path,
                )
        else:
            log.warning(
                "Optional efficiency metadata missing for task %d (source task %d): %s",
                task_id,
                efficiency_source_task_id,
                efficiency_path,
            )

        meta_df, merge_info = _merge_metadata_sources_equal_level(
            task_id=task_id,
            ordered_sources=[
                ("trigger_type", trigger_df),
                ("rate_histogram", rate_hist_df),
                ("specific", specific_df),
            ],
        )
        if optional_sources:
            meta_df, merge_info = _merge_optional_metadata_sources_left(
                merged=meta_df,
                info=merge_info,
                optional_sources=optional_sources,
            )
        log.info(
            "  Metadata merged at equal level for task %d: rows=%d, columns=%d.",
            task_id,
            len(meta_df),
            len(meta_df.columns),
        )
        if merge_info.get("renamed_overlap_columns"):
            overlap_counts = {
                key: int(len(val))
                for key, val in merge_info["renamed_overlap_columns"].items()
                if isinstance(val, dict)
            }
            log.info("  Metadata overlap columns renamed by source: %s", overlap_counts)

        # Inner join on filename_base: only keep rows present in BOTH
        merged = params_df.merge(meta_df, on="filename_base", how="inner")
        log.info("  Merged rows (task %d): %d", task_id, len(merged))

        if not merged.empty:
            merged["task_id"] = task_id
            all_merged.append(merged)

    if not all_merged:
        log.error("No data collected from any task. Check paths and data.")
        return 1

    collected = pd.concat(all_merged, ignore_index=True)
    log.info("Total collected rows (all tasks): %d", len(collected))

    ev_col = _resolve_event_count_column(collected)
    removed_below_min_rows = 0
    if min_rows_for_dataset > 0:
        if ev_col is None:
            log.warning(
                "step_1_1.min_rows_for_dataset=%d configured, but no event-count column is available; skipping row filter.",
                min_rows_for_dataset,
            )
        else:
            ev_vals = pd.to_numeric(collected[ev_col], errors="coerce")
            keep_mask = ev_vals >= float(min_rows_for_dataset)
            removed_below_min_rows = int(np.count_nonzero(~keep_mask))
            collected = collected.loc[keep_mask].reset_index(drop=True)
            log.info(
                "Applied minimum event rows filter (%s >= %d): removed %d row(s), %d remain.",
                ev_col,
                min_rows_for_dataset,
                removed_below_min_rows,
                len(collected),
            )
            if collected.empty:
                log.error(
                    "No rows remain after applying step_1_1.min_rows_for_dataset=%d on column %s.",
                    min_rows_for_dataset,
                    ev_col,
                )
                return 1

    # ── Save ─────────────────────────────────────────────────────────
    out_path = FILES_DIR / "collected_data.csv"
    collected.to_csv(out_path, index=False)
    log.info("Wrote collected data: %s", out_path)

    parameter_space_path = FILES_DIR / "parameter_space_columns.json"
    parameter_space_payload = {
        "parameter_space_columns": parameter_space_columns,
        "selected_parameter_space_columns": parameter_space_columns,
        "parameter_space_columns_downstream_preferred": parameter_space_info.get(
            "parameter_space_columns_downstream_preferred",
            parameter_space_columns,
        ),
        "parameter_space_column_aliases": parameter_space_info.get(
            "parameter_space_column_aliases", {}
        ),
        "selection": parameter_space_info,
    }
    parameter_space_path.write_text(
        json.dumps(parameter_space_payload, indent=2),
        encoding="utf-8",
    )
    log.info("Wrote parameter-space selection: %s", parameter_space_path)

    parameter_space_plot_path = _plot_parameter_space_overview(
        collected=collected,
        parameter_space_columns=parameter_space_columns,
        z_config=z_config,
        cfg_11=cfg_11,
    )
    if parameter_space_plot_path is not None:
        log.info("Wrote plot: %s", parameter_space_plot_path)

    # Save the selected z configuration for downstream steps
    z_info = {
        "z_position_config": z_config,
        "z_config_selected_index": z_config_selected_index,
        "z_config_selection_seed": z_config_selection_seed,
        "z_config_seed_from_config": z_config_seed_from_config,
        "total_rows": len(collected),
        "task_ids_used": task_ids,
        "task_ids_discovered": discovered_task_ids,
        "task_ids_configured": configured_task_ids,
        "station_id": station_id,
        "simulation_params_source": str(sim_params_path),
        "mesh_support_filter_mode": "disabled",
        "rows_removed_outside_mesh_support": 0,
        "metadata_sources_required": ["trigger_type", "rate_histogram", "specific"],
        "metadata_sources_optional": ["efficiency"],
        "efficiency_metadata_source_task_id": (
            None if efficiency_metadata_source_task_raw in (None, "", "null", "None", "same")
            else int(_resolve_efficiency_metadata_source_task_id(
                efficiency_metadata_source_task_raw,
                default_task_id=task_ids[0],
            ))
        ),
        "min_rows_for_dataset": int(min_rows_for_dataset),
        "event_count_column_used": ev_col,
        "rows_removed_below_min_rows": int(removed_below_min_rows),
        "has_flux_proxy_rate_div_effprod": False,
        "parameter_space_columns": parameter_space_columns,
        "parameter_space_columns_downstream_preferred": parameter_space_payload.get(
            "parameter_space_columns_downstream_preferred", parameter_space_columns
        ),
        "parameter_space_columns_json": str(parameter_space_path),
        "parameter_space_plot": (
            None if parameter_space_plot_path is None else str(parameter_space_plot_path)
        ),
        "parameter_space_selection": parameter_space_info,
    }
    z_info_path = FILES_DIR / "z_config_selected.json"
    with open(z_info_path, "w", encoding="utf-8") as f:
        json.dump(z_info, f, indent=2)
    log.info("Wrote z config info: %s", z_info_path)

    # ── Plot: event count histogram ──────────────────────────────────
    if ev_col is not None and ev_col in collected.columns:
        ev = pd.to_numeric(collected[ev_col], errors="coerce").dropna()
        if not ev.empty:
            fig, ax = plt.subplots(figsize=(7, 4.5))
            # Match the blue histogram alpha used elsewhere (was 0.8 here)
            ax.hist(ev, bins=40, alpha=0.5, color="#4C78A8", edgecolor="white")
            # Removed median vertical line / legend for a cleaner presentation
            ax.set_xlabel(f"Event count ({ev_col})")
            ax.set_ylabel("Number of files")
            ax.set_title(f"Event count distribution — {len(ev)} collected files")
            ax.grid(True, alpha=0.2)
            fig.tight_layout()
            histogram_path = _save_figure(fig, PLOTS_DIR / "event_count_histogram.png", dpi=150)
            plt.close(fig)
            log.info("Wrote plot: %s", histogram_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
