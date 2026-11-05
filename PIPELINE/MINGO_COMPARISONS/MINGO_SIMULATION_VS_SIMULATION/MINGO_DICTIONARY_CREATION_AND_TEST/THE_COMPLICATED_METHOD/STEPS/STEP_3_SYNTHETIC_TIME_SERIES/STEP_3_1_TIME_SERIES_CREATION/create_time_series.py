#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_3_SYNTHETIC_TIME_SERIES/STEP_3_1_TIME_SERIES_CREATION/create_time_series.py
Purpose: STEP 3.1 — Generate smooth parameter-space trajectory and event-discretized time series.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-12
Runtime: python3
Usage: python3 PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_3_SYNTHETIC_TIME_SERIES/STEP_3_1_TIME_SERIES_CREATION/create_time_series.py [options]
"""

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


# ── Paths ────────────────────────────────────────────────────────────────
STEP_DIR = Path(__file__).resolve().parent
if STEP_DIR.parents[1].name == "STEPS":
    PIPELINE_DIR = STEP_DIR.parents[2]
else:
    PIPELINE_DIR = STEP_DIR.parents[1]

if (PIPELINE_DIR / "STEP_1_SETUP").exists() and (PIPELINE_DIR / "STEP_2_INFERENCE").exists():
    STEP_ROOT = PIPELINE_DIR
else:
    STEP_ROOT = PIPELINE_DIR / "STEPS"

DEFAULT_CONFIG = (
    STEP_ROOT / "STEP_1_SETUP" / "STEP_1_1_COLLECT_DATA" / "INPUTS" / "config_step_1.1_method.json"
)
DEFAULT_DATASET = (
    STEP_ROOT
    / "STEP_1_SETUP"
    / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY"
    / "OUTPUTS"
    / "FILES"
    / "dataset.csv"
)
DEFAULT_DICTIONARY = (
    STEP_ROOT
    / "STEP_1_SETUP"
    / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY"
    / "OUTPUTS"
    / "FILES"
    / "dictionary.csv"
)
DEFAULT_PARAMETER_SPACE_SPEC = (
    STEP_ROOT
    / "STEP_1_SETUP"
    / "STEP_1_1_COLLECT_DATA"
    / "OUTPUTS"
    / "FILES"
    / "parameter_space_columns.json"
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
FIGURE_STEP_PREFIX = "3_1"

logging.basicConfig(format="[%(levelname)s] STEP_3.1 — %(message)s", level=logging.INFO)
log = logging.getLogger("STEP_3.1")

CANONICAL_FLUX_COLUMN = "flux_cm2_min"
CANONICAL_EFF_COLUMN = "eff_sim_1"
DEFAULT_PARAM_CURVE_COLS = [
    "flux_cm2_min",
    "eff_sim_1",
    "eff_sim_2",
    "eff_sim_3",
    "eff_sim_4",
]


def _normalize_curve_data_mode(value: object) -> str:
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_") if value is not None else ""
    if text in {
        "",
        "synthetic",
        "synthetic_curve",
        "synthetic_data_curve",
        "parameter_curve",
        "parameter_space_curve",
    }:
        return "synthetic_data_curve"
    if text in {
        "dataset",
        "dataset_curve",
        "dataset_data_curve",
        "dataset_entries",
        "real_entries",
        "real_data_curve",
        "control",
    }:
        return "dataset_data_curve"
    return "synthetic_data_curve"


def _save_figure(fig: plt.Figure, path: Path, **kwargs) -> None:
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


def _safe_float(value: object, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float(default)
    return out if np.isfinite(out) else float(default)


def _safe_int(value: object, default: int, minimum: int | None = None) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        out = int(default)
    if minimum is not None:
        out = max(int(minimum), out)
    return out


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _resolve_input_path(path_like: str | Path) -> Path:
    p = Path(path_like).expanduser()
    if p.is_absolute():
        return p
    candidate_pipeline = PIPELINE_DIR / p
    if candidate_pipeline.exists():
        return candidate_pipeline
    candidate_step = STEP_DIR / p
    if candidate_step.exists():
        return candidate_step
    return candidate_pipeline


def _load_parameter_space_spec(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not load parameter-space spec %s: %s", path, exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def _apply_parameter_space_aliases(df: pd.DataFrame, spec: dict) -> tuple[pd.DataFrame, list[str]]:
    if df.empty or not isinstance(spec, dict):
        return df, []

    raw_aliases = spec.get("parameter_space_column_aliases", {})
    aliases = raw_aliases if isinstance(raw_aliases, dict) else {}
    to_add: dict[str, pd.Series] = {}

    for source_col_raw, target_col_raw in aliases.items():
        source_col = str(source_col_raw).strip()
        target_col = str(target_col_raw).strip()
        if not source_col or not target_col or source_col == target_col:
            continue
        if target_col in df.columns or source_col not in df.columns or target_col in to_add:
            continue
        to_add[target_col] = df[source_col].copy()

    if not to_add:
        return df, []

    alias_df = pd.DataFrame(to_add, index=df.index)
    out = pd.concat([df, alias_df], axis=1)
    return out, sorted(alias_df.columns.tolist())


def _choose_eff_column(df: pd.DataFrame, preferred: str) -> str:
    if preferred in df.columns:
        return preferred
    for c in (
        "eff_sim_1",
        "eff_sim_2",
        "eff_sim_3",
        "eff_sim_4",
        "eff_empirical_1",
        "eff_empirical_2",
        "eff_empirical_3",
        "eff_empirical_4",
    ):
        if c in df.columns:
            return c
    raise KeyError("No efficiency column found in table.")


def _pick_rate_column(df: pd.DataFrame, preferred: str) -> str | None:
    candidates: list[str] = []
    preferred_clean = str(preferred).strip()
    if preferred_clean:
        candidates.append(preferred_clean)
    candidates.extend([
        "events_per_second_global_rate",
        "global_rate_hz_mean",
        "global_rate_hz",
    ])

    seen: set[str] = set()
    ordered: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered.append(c)

    for c in ordered:
        if c not in df.columns:
            continue
        vals = pd.to_numeric(df[c], errors="coerce")
        if vals.notna().any():
            return c

    tt_cols = [
        c
        for c in df.columns
        if "_tt_" in str(c).lower() and str(c).lower().endswith("_rate_hz")
    ]
    if tt_cols:
        summed = pd.Series(0.0, index=df.index, dtype=float)
        valid_any = pd.Series(False, index=df.index)
        for c in sorted(tt_cols):
            v = pd.to_numeric(df[c], errors="coerce")
            summed = summed + v.fillna(0.0)
            valid_any = valid_any | v.notna()
        derived_col = "events_per_second_global_rate"
        df[derived_col] = summed.where(valid_any, np.nan)
        if pd.to_numeric(df[derived_col], errors="coerce").notna().any():
            log.info("Derived global rate from %d TT rate columns.", len(tt_cols))
            return derived_col

    return None


def _resolve_numeric_range(
    cfg_value: object,
    fallback_min: float,
    fallback_max: float,
) -> tuple[float, float]:
    lo = float(fallback_min)
    hi = float(fallback_max)
    if isinstance(cfg_value, (list, tuple)) and len(cfg_value) == 2:
        lo = _safe_float(cfg_value[0], lo)
        hi = _safe_float(cfg_value[1], hi)
    if lo > hi:
        lo, hi = hi, lo
    return (float(lo), float(hi))


def _normalised_axis(n_points: int) -> np.ndarray:
    n = max(2, int(n_points))
    return np.linspace(0.0, 1.0, n, endpoint=False, dtype=float)


def _moving_average(values: np.ndarray, window_points: int) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    w = max(1, int(window_points))
    if w % 2 == 0:
        w += 1
    if w <= 1:
        return arr.copy()
    pad = w // 2
    padded = np.pad(arr, (pad, pad), mode="edge")
    kernel = np.ones(w, dtype=float) / float(w)
    return np.convolve(padded, kernel, mode="valid")


def _random_smooth_unit_series(
    u: np.ndarray,
    rng: np.random.Generator,
    n_harmonics: int,
    roughness: float,
    smoothing_window_points: int,
    smoothing_passes: int,
) -> np.ndarray:
    y = np.zeros_like(u, dtype=float)
    two_pi = 2.0 * np.pi

    n_h = max(1, int(n_harmonics))
    rough = max(0.1, float(roughness))

    for k in range(1, n_h + 1):
        amp = rng.uniform(0.3, 1.0) / (k ** rough)
        fs = max(0.15, float(k) + rng.uniform(-0.35, 0.35))
        fc = max(0.15, float(k) + rng.uniform(-0.35, 0.35))
        ps = rng.uniform(0.0, two_pi)
        pc = rng.uniform(0.0, two_pi)
        y += amp * np.sin(two_pi * fs * u + ps)
        y += 0.5 * amp * np.cos(two_pi * fc * u + pc)

    # Non-periodic drift.
    du = u - 0.5
    y += rng.normal(0.0, 0.8) * du
    y += rng.normal(0.0, 0.4) * du * du

    for _ in range(max(0, int(smoothing_passes))):
        y = _moving_average(y, smoothing_window_points)

    y_min = float(np.nanmin(y))
    y_max = float(np.nanmax(y))
    span = y_max - y_min
    if not np.isfinite(span) or span <= 1e-12:
        unit = np.full_like(y, 0.5, dtype=float)
    else:
        unit = (y - y_min) / span

    # Avoid near-closure between first and last values.
    if len(unit) >= 2 and abs(float(unit[-1]) - float(unit[0])) < 0.03:
        delta = (0.03 - abs(float(unit[-1]) - float(unit[0])))
        if rng.random() < 0.5:
            delta *= -1.0
        unit = unit + np.linspace(0.0, delta, len(unit), dtype=float)
        umin = float(np.nanmin(unit))
        umax = float(np.nanmax(unit))
        uspan = umax - umin
        if np.isfinite(uspan) and uspan > 1e-12:
            unit = (unit - umin) / uspan
        else:
            unit = np.full_like(unit, 0.5, dtype=float)

    return np.clip(unit, 0.0, 1.0)


def _map_unit_to_range(unit: np.ndarray, value_range: tuple[float, float]) -> np.ndarray:
    lo, hi = float(value_range[0]), float(value_range[1])
    if np.isclose(lo, hi, atol=0.0):
        return np.full_like(unit, lo, dtype=float)
    return lo + (hi - lo) * np.asarray(unit, dtype=float)


def _resolve_parameter_curve_columns(rate_df: pd.DataFrame, cfg_31: dict) -> list[str]:
    raw = cfg_31.get("parameter_curve_columns", DEFAULT_PARAM_CURVE_COLS)
    if not isinstance(raw, (list, tuple)):
        raw = DEFAULT_PARAM_CURVE_COLS

    cols = [str(c) for c in raw if str(c) in rate_df.columns]
    cols = list(dict.fromkeys(cols))

    if not cols:
        raise ValueError("No valid parameter_curve_columns found in rate dictionary.")

    return cols


def _resolve_parameter_ranges(
    param_cols: list[str],
    source_df: pd.DataFrame,
    rate_df: pd.DataFrame,
    cfg_31: dict,
) -> dict[str, tuple[float, float]]:
    ranges: dict[str, tuple[float, float]] = {}

    ranges_cfg_raw = cfg_31.get("parameter_ranges", {})
    ranges_cfg = ranges_cfg_raw if isinstance(ranges_cfg_raw, dict) else {}

    flux_range_cfg = cfg_31.get("flux_range", None)
    eff_range_cfg = cfg_31.get("eff_range", None)

    for col in param_cols:
        if col in source_df.columns:
            base_series = pd.to_numeric(source_df[col], errors="coerce")
        else:
            base_series = pd.to_numeric(rate_df.get(col), errors="coerce")

        base_series = base_series.dropna()
        if base_series.empty:
            raise ValueError(f"Cannot resolve value range for parameter '{col}' (no finite values).")

        lo = float(base_series.min())
        hi = float(base_series.max())

        if col in ranges_cfg and isinstance(ranges_cfg[col], (list, tuple)) and len(ranges_cfg[col]) == 2:
            lo, hi = _resolve_numeric_range(ranges_cfg[col], lo, hi)
        elif col == CANONICAL_FLUX_COLUMN and flux_range_cfg is not None:
            lo, hi = _resolve_numeric_range(flux_range_cfg, lo, hi)
        elif col.startswith("eff_sim_") and eff_range_cfg is not None:
            lo, hi = _resolve_numeric_range(eff_range_cfg, lo, hi)

        ranges[col] = (lo, hi)

    return ranges


def _resolve_dataset_curve_event_counts(
    source_df: pd.DataFrame,
    *,
    fallback_events_per_row: int,
) -> tuple[pd.Series, str]:
    for col in ("n_events", "selected_rows", "requested_rows"):
        if col not in source_df.columns:
            continue
        vals = pd.to_numeric(source_df[col], errors="coerce")
        if vals.notna().any():
            return vals, col
    return (
        pd.Series(np.full(len(source_df), float(fallback_events_per_row), dtype=float), index=source_df.index),
        "config_events_per_file_fallback",
    )


def _resolve_dataset_curve_durations(
    source_df: pd.DataFrame,
    *,
    rate_series: pd.Series,
    events_series: pd.Series,
    fallback_events_per_row: int,
) -> tuple[pd.Series, str]:
    for col in ("duration_seconds", "count_rate_denominator_seconds", "events_per_second_total_seconds"):
        if col not in source_df.columns:
            continue
        vals = pd.to_numeric(source_df[col], errors="coerce")
        valid = vals.notna() & (vals > 0.0)
        if valid.any():
            return vals, col

    rate = pd.to_numeric(rate_series, errors="coerce")
    events = pd.to_numeric(events_series, errors="coerce")
    duration_from_rate = pd.Series(np.nan, index=source_df.index, dtype=float)
    valid = rate.notna() & (rate > 0.0) & events.notna() & (events > 0.0)
    duration_from_rate.loc[valid] = events.loc[valid] / rate.loc[valid]
    if duration_from_rate.notna().any():
        return duration_from_rate, "events_over_rate"

    fallback = pd.Series(np.nan, index=source_df.index, dtype=float)
    valid_rate = rate.notna() & (rate > 0.0)
    fallback.loc[valid_rate] = float(fallback_events_per_row) / rate.loc[valid_rate]
    return fallback, "config_events_per_file_over_rate"


def _standardize_param_matrix(param_matrix: np.ndarray) -> np.ndarray:
    x = np.asarray(param_matrix, dtype=float)
    if x.ndim != 2 or x.shape[0] == 0:
        return np.zeros((0, 0), dtype=float)
    center = np.nanmean(x, axis=0)
    scale = np.nanstd(x, axis=0)
    scale = np.where(np.isfinite(scale) & (scale > 1e-12), scale, 1.0)
    x_std = (x - center) / scale
    return np.where(np.isfinite(x_std), x_std, 0.0)


def _dataset_curve_order_scores(param_matrix: np.ndarray) -> np.ndarray:
    x_std = _standardize_param_matrix(param_matrix)
    if x_std.ndim != 2 or x_std.shape[0] == 0:
        return np.zeros(0, dtype=float)
    if x_std.shape[0] == 1:
        return np.zeros(1, dtype=float)

    try:
        _, _, vh = np.linalg.svd(x_std, full_matrices=False)
        if vh.ndim == 2 and vh.shape[0] > 0:
            return np.asarray(x_std @ vh[0], dtype=float)
    except np.linalg.LinAlgError:
        pass
    return np.asarray(x_std[:, 0], dtype=float)


def _select_dataset_curve_positions(n_available: int, n_target: int) -> np.ndarray:
    if n_available <= 0:
        return np.zeros(0, dtype=int)
    n_take = max(1, int(n_target))
    if n_take <= n_available:
        return np.floor(np.linspace(0.0, float(n_available) - 1e-9, n_take)).astype(int)

    cycles = n_take // n_available
    remainder = n_take % n_available
    parts = [np.arange(n_available, dtype=int) for _ in range(cycles)]
    if remainder > 0:
        parts.append(np.floor(np.linspace(0.0, float(n_available) - 1e-9, remainder)).astype(int))
    return np.concatenate(parts) if parts else np.zeros(0, dtype=int)


def _select_dataset_curve_smooth_order(
    param_matrix: np.ndarray,
    n_target: int,
    *,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, dict[str, object]]:
    x_std = _standardize_param_matrix(param_matrix)
    n_available = int(x_std.shape[0])
    if n_available <= 0:
        return np.zeros(0, dtype=int), {
            "ordering_mode": "empty",
            "selection_window_radius": 0,
            "selection_anchor_weight": 0.0,
            "selection_cost": "none",
        }

    order_scores = _dataset_curve_order_scores(param_matrix)
    order = np.argsort(order_scores, kind="mergesort")
    n_take = max(1, int(n_target))
    if n_available == 1 or n_take == 1:
        center_pos = int(np.clip(np.rint(0.5 * (n_available - 1)), 0, n_available - 1))
        return order[[center_pos]], {
            "ordering_mode": "pca1_windowed_continuity_path",
            "selection_window_radius": 0,
            "selection_anchor_weight": 0.35,
            "selection_cost": "squared_standardized_jump",
        }

    if n_take >= n_available:
        repeated = _select_dataset_curve_positions(n_available, n_take)
        return order[repeated], {
            "ordering_mode": "pca1_sorted_with_repeats",
            "selection_window_radius": 0,
            "selection_anchor_weight": 0.0,
            "selection_cost": "pca1_sorted_repeat_cycle",
        }

    x_sorted = x_std[order]
    centers = np.linspace(0.0, float(n_available - 1), n_take, dtype=float)
    nominal_step = float(n_available - 1) / max(n_take - 1, 1)
    window_radius = max(3, int(np.ceil(0.8 * nominal_step)))
    anchor_weight = 0.35
    center_jitter_scale = 0.45 * min(window_radius, max(1.0, nominal_step))
    phase_offset = 0.0

    if rng is not None and n_take > 2 and center_jitter_scale > 0.0:
        phase_offset = float(rng.uniform(-0.5, 0.5) * center_jitter_scale)
        local_jitter = rng.normal(0.0, 0.6 * center_jitter_scale, size=n_take - 2)
        if local_jitter.size > 1:
            local_jitter = _moving_average(local_jitter, min(local_jitter.size, 5))
        centers[1:-1] = centers[1:-1] + phase_offset + local_jitter
        centers[1:-1] = np.clip(centers[1:-1], 1.0, float(n_available - 2))
        centers[1:-1] = np.maximum.accumulate(centers[1:-1])
        for idx in range(n_take - 3, -1, -1):
            centers[idx + 1] = min(centers[idx + 1], centers[idx + 2] - 1e-6)
        centers[1:-1] = np.clip(centers[1:-1], 1.0, float(n_available - 2))

    candidate_positions: list[np.ndarray] = []
    anchor_costs: list[np.ndarray] = []
    for idx, center in enumerate(centers):
        if idx == 0:
            candidate_positions.append(np.array([0], dtype=int))
            anchor_costs.append(np.zeros(1, dtype=float))
            continue
        if idx == n_take - 1:
            candidate_positions.append(np.array([n_available - 1], dtype=int))
            anchor_costs.append(np.zeros(1, dtype=float))
            continue
        lo = max(0, int(np.floor(center)) - window_radius)
        hi = min(n_available - 1, int(np.ceil(center)) + window_radius)
        positions = np.arange(lo, hi + 1, dtype=int)
        if positions.size == 0:
            positions = np.array([int(np.clip(np.rint(center), 0, n_available - 1))], dtype=int)
        candidate_positions.append(positions)
        anchor_cost = anchor_weight * np.abs(positions.astype(float) - center) / max(window_radius, 1)
        if rng is not None:
            anchor_cost = anchor_cost + rng.uniform(0.0, 0.03, size=positions.size)
        anchor_costs.append(anchor_cost)

    dp = anchor_costs[0].copy()
    backrefs: list[np.ndarray] = []
    for idx in range(1, n_take):
        prev_pos = candidate_positions[idx - 1]
        curr_pos = candidate_positions[idx]
        jump_cost = np.sum(
            (x_sorted[prev_pos][:, None, :] - x_sorted[curr_pos][None, :, :]) ** 2,
            axis=2,
        )
        valid_transitions = curr_pos[None, :] > prev_pos[:, None]
        total_cost = dp[:, None] + np.where(valid_transitions, jump_cost, np.inf) + anchor_costs[idx][None, :]
        best_prev = np.argmin(total_cost, axis=0)
        best_cost = total_cost[best_prev, np.arange(total_cost.shape[1])]
        backrefs.append(best_prev.astype(int))
        dp = best_cost

    if not np.isfinite(dp).any():
        fallback = _select_dataset_curve_positions(n_available, n_take)
        return order[fallback], {
            "ordering_mode": "pca1_sorted_fallback",
            "selection_window_radius": window_radius,
            "selection_anchor_weight": anchor_weight,
            "selection_cost": "pca1_even_spacing_fallback",
        }

    cursor = int(np.nanargmin(dp))
    chosen_candidate_indices = [cursor]
    for stage in range(n_take - 2, -1, -1):
        cursor = int(backrefs[stage][cursor])
        chosen_candidate_indices.append(cursor)
    chosen_candidate_indices.reverse()

    sorted_positions = np.array(
        [candidate_positions[idx][chosen_candidate_indices[idx]] for idx in range(n_take)],
        dtype=int,
    )
    return order[sorted_positions], {
        "ordering_mode": "pca1_windowed_continuity_path",
        "selection_window_radius": window_radius,
        "selection_anchor_weight": anchor_weight,
        "selection_cost": "squared_standardized_jump",
        "selection_randomized": bool(rng is not None),
        "selection_center_jitter_scale": float(center_jitter_scale),
        "selection_phase_offset": float(phase_offset),
    }


def _build_dataset_backed_curve(
    *,
    source_df: pd.DataFrame,
    param_cols: list[str],
    rate_col: str,
    duration_seconds_target: float,
    events_per_file_fallback: int,
    start_time: pd.Timestamp,
    rng: np.random.Generator | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    if source_df.empty:
        raise ValueError("Dataset-backed curve requires a non-empty source table.")
    if rate_col not in source_df.columns:
        raise ValueError(f"Dataset-backed curve source must contain rate column '{rate_col}'.")

    param_df = source_df[param_cols].apply(pd.to_numeric, errors="coerce")
    rate_series = pd.to_numeric(source_df[rate_col], errors="coerce")
    event_counts, event_count_source = _resolve_dataset_curve_event_counts(
        source_df,
        fallback_events_per_row=events_per_file_fallback,
    )
    durations, duration_source = _resolve_dataset_curve_durations(
        source_df,
        rate_series=rate_series,
        events_series=event_counts,
        fallback_events_per_row=events_per_file_fallback,
    )

    valid = (
        param_df.notna().all(axis=1)
        & rate_series.notna()
        & (rate_series > 0.0)
        & pd.to_numeric(durations, errors="coerce").notna()
        & (pd.to_numeric(durations, errors="coerce") > 0.0)
    )
    if not valid.any():
        raise ValueError(
            "Dataset-backed curve could not find any source rows with finite parameter columns, rate, and duration."
        )

    valid_source = source_df.loc[valid].copy().reset_index(drop=True)
    valid_param = param_df.loc[valid].reset_index(drop=True)
    valid_rate = rate_series.loc[valid].reset_index(drop=True)
    valid_events = pd.to_numeric(event_counts.loc[valid], errors="coerce").reset_index(drop=True)
    valid_duration = pd.to_numeric(durations.loc[valid], errors="coerce").reset_index(drop=True)
    fill_events = valid_events.isna() | (valid_events <= 0.0)
    if fill_events.any():
        valid_events.loc[fill_events] = (
            valid_rate.loc[fill_events].to_numpy(dtype=float)
            * valid_duration.loc[fill_events].to_numpy(dtype=float)
        )
    source_row_positions = np.flatnonzero(valid.to_numpy())

    finite_durations = valid_duration[np.isfinite(valid_duration) & (valid_duration > 0.0)]
    median_duration = float(np.median(finite_durations)) if not finite_durations.empty else 0.0
    if not np.isfinite(median_duration) or median_duration <= 0.0:
        median_duration = max(float(duration_seconds_target), 1.0)
    n_target_rows = max(1, int(np.round(float(duration_seconds_target) / median_duration)))

    selected_order, selection_info = _select_dataset_curve_smooth_order(
        valid_param.to_numpy(dtype=float),
        n_target_rows,
        rng=rng,
    )
    chosen = valid_source.iloc[selected_order].reset_index(drop=True)
    chosen_rate = pd.to_numeric(valid_rate.iloc[selected_order], errors="coerce").reset_index(drop=True)
    chosen_events = pd.to_numeric(valid_events.iloc[selected_order], errors="coerce").reset_index(drop=True)
    chosen_duration = pd.to_numeric(valid_duration.iloc[selected_order], errors="coerce").reset_index(drop=True)
    chosen_row_positions = source_row_positions[selected_order]

    elapsed_end = np.cumsum(chosen_duration.to_numpy(dtype=float))
    elapsed_start = elapsed_end - chosen_duration.to_numpy(dtype=float)
    elapsed_mid = 0.5 * (elapsed_start + elapsed_end)

    file_df = pd.DataFrame(
        {
            "file_index": np.arange(1, len(chosen) + 1, dtype=int),
            "elapsed_seconds_start": elapsed_start,
            "elapsed_seconds_end": elapsed_end,
            "elapsed_seconds": elapsed_mid,
            "elapsed_hours_start": elapsed_start / 3600.0,
            "elapsed_hours_end": elapsed_end / 3600.0,
            "elapsed_hours": elapsed_mid / 3600.0,
            "duration_seconds": chosen_duration.to_numpy(dtype=float),
            "n_events_expected": chosen_events.to_numpy(dtype=float),
            "n_events": np.rint(chosen_events.to_numpy(dtype=float)).astype(int),
            "target_events_per_file": np.rint(chosen_events.to_numpy(dtype=float)).astype(int),
            "global_rate_hz_mid": chosen_rate.to_numpy(dtype=float),
            "global_rate_hz_mean": chosen_rate.to_numpy(dtype=float),
            "step31_curve_data_mode": np.full(len(chosen), "dataset_data_curve", dtype=object),
            "step31_source_row_index": chosen_row_positions.astype(int),
        }
    )
    for col in param_cols:
        file_df[col] = pd.to_numeric(chosen[col], errors="coerce").to_numpy(dtype=float)

    if "filename_base" in chosen.columns:
        file_df["step31_source_filename_base"] = chosen["filename_base"].astype(str).to_numpy(dtype=object)
    if "param_hash_x" in chosen.columns:
        file_df["step31_source_param_hash_x"] = chosen["param_hash_x"].astype(str).to_numpy(dtype=object)

    dense_df = file_df.copy()
    dense_df.insert(0, "curve_index", np.arange(len(dense_df), dtype=int))
    dense_time = start_time + pd.to_timedelta(dense_df["elapsed_seconds"], unit="s")
    dense_df["time_utc"] = dense_time.dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    info = {
        "mode": "dataset_data_curve",
        "ordering_mode": selection_info.get("ordering_mode"),
        "n_reference_points": int(len(valid_source)),
        "n_anchor_points": None,
        "anchor_indices_in_valid_reference": [],
        "event_count_source_column": event_count_source,
        "duration_source_column": duration_source,
        "selected_source_rows": int(len(chosen)),
        "selected_source_row_indices": chosen_row_positions.astype(int).tolist(),
        "selected_source_unique_rows": int(np.unique(chosen_row_positions).size),
    }
    info.update(selection_info)
    return dense_df, file_df, info


def _build_parameter_curve(
    u: np.ndarray,
    param_cols: list[str],
    param_ranges: dict[str, tuple[float, float]],
    rng: np.random.Generator,
    cfg_31: dict,
    identical_efficiencies: bool,
    reference_df: pd.DataFrame | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, object]]:
    n_harmonics = _safe_int(cfg_31.get("n_harmonics", 4), 4, minimum=1)
    roughness = _safe_float(cfg_31.get("roughness", 1.6), 1.6)
    smoothing_window_points = _safe_int(cfg_31.get("smoothing_window_points", 11), 11, minimum=1)
    smoothing_passes = _safe_int(cfg_31.get("smoothing_passes", 2), 2, minimum=0)

    mode_raw = str(cfg_31.get("curve_generation_mode", "convex_hull")).strip().lower()
    use_convex_hull = mode_raw in {"convex_hull", "convex", "hull", "dictionary_convex_hull"}

    # Recommended mode: smooth convex combinations of dictionary points.
    if use_convex_hull and reference_df is not None and not reference_df.empty:
        ref_df = reference_df[param_cols].apply(pd.to_numeric, errors="coerce")
        valid = ref_df.notna().all(axis=1)
        ref_vals = ref_df.loc[valid].to_numpy(dtype=float)
        if ref_vals.size > 0:
            n_ref = int(ref_vals.shape[0])
            n_anchor_default = min(12, n_ref)
            n_anchors = _safe_int(
                cfg_31.get("convex_hull_n_anchors", n_anchor_default),
                n_anchor_default,
                minimum=1,
            )
            n_anchors = max(1, min(n_anchors, n_ref))

            if n_anchors == n_ref:
                anchor_idx = np.arange(n_ref, dtype=int)
            else:
                anchor_idx = np.sort(rng.choice(n_ref, size=n_anchors, replace=False).astype(int))
            anchors = ref_vals[anchor_idx, :]

            raw_w = np.zeros((len(u), n_anchors), dtype=float)
            for j in range(n_anchors):
                unit = _random_smooth_unit_series(
                    u=u,
                    rng=rng,
                    n_harmonics=n_harmonics,
                    roughness=roughness,
                    smoothing_window_points=smoothing_window_points,
                    smoothing_passes=smoothing_passes,
                )
                raw_w[:, j] = np.clip(unit, 0.0, 1.0)

            weight_floor = max(0.0, _safe_float(cfg_31.get("convex_hull_weight_floor", 1e-3), 1e-3))
            raw_w = np.where(np.isfinite(raw_w), raw_w, 0.0) + weight_floor
            w_sum = raw_w.sum(axis=1, keepdims=True)
            w = np.divide(
                raw_w,
                w_sum,
                out=np.full_like(raw_w, 1.0 / float(n_anchors)),
                where=w_sum > 0.0,
            )
            curve_matrix = w @ anchors

            curve = {
                col: np.asarray(curve_matrix[:, i], dtype=float)
                for i, col in enumerate(param_cols)
            }

            if identical_efficiencies:
                eff_cols = [c for c in param_cols if c.startswith("eff_sim_")]
                if eff_cols:
                    base_col = "eff_sim_1" if "eff_sim_1" in curve else eff_cols[0]
                    base_values = curve[base_col].copy()
                    for col in eff_cols:
                        curve[col] = base_values.copy()

            info = {
                "mode": "convex_hull",
                "n_reference_points": n_ref,
                "n_anchor_points": int(n_anchors),
                "anchor_indices_in_valid_reference": anchor_idx.tolist(),
            }
            return curve, info

    # Fallback mode: independent smooth per-parameter trajectories in configured ranges.
    curve = {}
    for col in param_cols:
        unit = _random_smooth_unit_series(
            u=u,
            rng=rng,
            n_harmonics=n_harmonics,
            roughness=roughness,
            smoothing_window_points=smoothing_window_points,
            smoothing_passes=smoothing_passes,
        )
        curve[col] = _map_unit_to_range(unit, param_ranges[col]).astype(float)

    if identical_efficiencies:
        eff_cols = [c for c in param_cols if c.startswith("eff_sim_")]
        if eff_cols:
            base_col = "eff_sim_1" if "eff_sim_1" in curve else eff_cols[0]
            base_values = curve[base_col].copy()
            for col in eff_cols:
                curve[col] = base_values.copy()

    info = {
        "mode": "independent_ranges_fallback",
        "n_reference_points": None,
        "n_anchor_points": None,
        "anchor_indices_in_valid_reference": [],
    }
    return curve, info


def _normalize_to_unit_interval(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    out = np.full(arr.shape, 0.5, dtype=float)
    finite = np.isfinite(arr)
    if not np.any(finite):
        return out
    lo = float(np.nanmin(arr[finite]))
    hi = float(np.nanmax(arr[finite]))
    span = hi - lo
    if np.isfinite(span) and span > 1e-12:
        out[finite] = (arr[finite] - lo) / span
    return np.clip(out, 0.0, 1.0)


def _resolve_global_rate_range_hz(
    rate_df: pd.DataFrame,
    rate_col: str,
    cfg_31: dict,
) -> tuple[float, float]:
    rate_vals = pd.to_numeric(rate_df.get(rate_col), errors="coerce").dropna()
    if rate_vals.empty:
        raise ValueError(f"Rate column '{rate_col}' has no finite values.")
    lo_default = float(rate_vals.min())
    hi_default = float(rate_vals.max())
    return _resolve_numeric_range(
        cfg_31.get("global_rate_range_hz", cfg_31.get("rate_range_hz", None)),
        lo_default,
        hi_default,
    )


def _build_global_rate_curve_from_parameters(
    curve: dict[str, np.ndarray],
    param_cols: list[str],
    cfg_31: dict,
    rate_range_hz: tuple[float, float],
) -> np.ndarray:
    n_points = len(next(iter(curve.values()))) if curve else 0
    if n_points <= 0:
        return np.zeros(0, dtype=float)

    flux = np.asarray(curve.get(CANONICAL_FLUX_COLUMN, np.full(n_points, np.nan, dtype=float)), dtype=float)
    flux_unit = _normalize_to_unit_interval(flux)

    eff_cols = [c for c in param_cols if c.startswith("eff_sim_") and c in curve]
    if eff_cols:
        eff_matrix = np.column_stack([np.asarray(curve[c], dtype=float) for c in eff_cols])
        eff_mean = np.nanmean(eff_matrix, axis=1)
        eff_unit = _normalize_to_unit_interval(eff_mean)
    else:
        eff_unit = np.full(n_points, 0.5, dtype=float)

    flux_weight = _safe_float(cfg_31.get("rate_from_flux_weight", 0.70), 0.70)
    flux_weight = min(1.0, max(0.0, flux_weight))
    proxy = flux_weight * flux_unit + (1.0 - flux_weight) * eff_unit

    smooth_window = _safe_int(cfg_31.get("rate_smoothing_window_points", 15), 15, minimum=1)
    smooth_passes = _safe_int(cfg_31.get("rate_smoothing_passes", 1), 1, minimum=0)
    for _ in range(smooth_passes):
        proxy = _moving_average(proxy, smooth_window)

    rate_unit = _normalize_to_unit_interval(proxy)
    rate_hz = _map_unit_to_range(rate_unit, rate_range_hz)
    rate_hz = np.maximum(np.asarray(rate_hz, dtype=float), 1e-6)
    return rate_hz


def _cumulative_events(dense_time_s: np.ndarray, dense_rate_hz: np.ndarray) -> np.ndarray:
    dt = np.diff(dense_time_s)
    seg_events = 0.5 * (dense_rate_hz[:-1] + dense_rate_hz[1:]) * dt
    seg_events = np.clip(seg_events, 0.0, None)
    return np.concatenate([[0.0], np.cumsum(seg_events)])


def _discretize_curve_by_events(
    dense_time_s: np.ndarray,
    dense_rate_hz: np.ndarray,
    dense_tracks: dict[str, np.ndarray],
    events_per_file: int,
    include_partial_last_file: bool,
) -> tuple[pd.DataFrame, float]:
    cum_events = _cumulative_events(dense_time_s, dense_rate_hz)
    total_events = float(cum_events[-1])
    if total_events <= 0.0:
        raise ValueError("Total expected events is zero; cannot discretize trajectory.")

    thresholds = [0.0]
    full_files = int(total_events // float(events_per_file))
    for k in range(1, full_files + 1):
        thresholds.append(float(k * events_per_file))

    remainder = total_events - thresholds[-1]
    if include_partial_last_file and remainder > 1e-9:
        thresholds.append(total_events)
    elif len(thresholds) == 1:
        thresholds.append(total_events)

    thr = np.asarray(thresholds, dtype=float)
    idx = np.searchsorted(cum_events, thr, side="right") - 1
    idx = np.clip(idx, 0, len(dense_time_s) - 2)

    e0 = cum_events[idx]
    e1 = cum_events[idx + 1]
    frac = np.divide(thr - e0, e1 - e0, out=np.zeros_like(thr, dtype=float), where=(e1 - e0) > 0)

    t_b = dense_time_s[idx] + frac * (dense_time_s[idx + 1] - dense_time_s[idx])

    t_start = t_b[:-1]
    t_end = t_b[1:]
    duration_s = np.maximum(t_end - t_start, 1e-12)
    events_expected = thr[1:] - thr[:-1]
    t_mid = 0.5 * (t_start + t_end)

    out = pd.DataFrame(
        {
            "file_index": np.arange(1, len(t_mid) + 1, dtype=int),
            "elapsed_seconds_start": t_start,
            "elapsed_seconds_end": t_end,
            "elapsed_seconds": t_mid,
            "elapsed_hours_start": t_start / 3600.0,
            "elapsed_hours_end": t_end / 3600.0,
            "elapsed_hours": t_mid / 3600.0,
            "duration_seconds": duration_s,
            "n_events_expected": events_expected,
            "n_events": np.rint(events_expected).astype(int),
            "target_events_per_file": int(events_per_file),
            "global_rate_hz_mid": np.interp(t_mid, dense_time_s, dense_rate_hz),
            "global_rate_hz_mean": events_expected / duration_s,
        }
    )

    for col, values in dense_tracks.items():
        arr = np.asarray(values, dtype=float)
        out[col] = np.interp(t_mid, dense_time_s, arr)

    return out, total_events


def _plot_time_series(dense_df: pd.DataFrame, file_df: pd.DataFrame, path: Path) -> None:
    x_dense = pd.to_numeric(dense_df.get("elapsed_hours"), errors="coerce").to_numpy(dtype=float)
    x_disc = pd.to_numeric(file_df.get("elapsed_hours"), errors="coerce").to_numpy(dtype=float)

    fig, axes = plt.subplots(2, 1, figsize=(10.0, 6.4), sharex=True)

    axes[0].plot(
        x_dense,
        pd.to_numeric(dense_df.get("flux"), errors="coerce"),
        color="#1f77b4",
        lw=1.2,
        alpha=0.85,
        label="Complete",
    )
    axes[0].scatter(
        x_disc,
        pd.to_numeric(file_df.get("flux"), errors="coerce"),
        s=22,
        facecolor="white",
        edgecolor="#1f77b4",
        lw=0.7,
        label="Discretized",
    )
    axes[0].set_ylabel("flux_cm2_min")
    axes[0].set_title("Flux")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(loc="best", fontsize=8)

    eff_cols = [f"eff_sim_{i}" for i in range(1, 5)]
    eff_cols_present = [
        col
        for col in eff_cols
        if (
            col in dense_df.columns
            and np.isfinite(pd.to_numeric(dense_df.get(col), errors="coerce")).any()
        )
        or (
            col in file_df.columns
            and np.isfinite(pd.to_numeric(file_df.get(col), errors="coerce")).any()
        )
    ]
    eff_palette = ["#ff7f0e", "#d62728", "#9467bd", "#8c564b"]

    if eff_cols_present:
        for idx, col in enumerate(eff_cols_present):
            color = eff_palette[idx % len(eff_palette)]
            dense_eff = pd.to_numeric(dense_df.get(col), errors="coerce")
            file_eff = pd.to_numeric(file_df.get(col), errors="coerce")
            axes[1].plot(
                x_dense,
                dense_eff,
                color=color,
                lw=1.2,
                alpha=0.9,
                label=f"{col} (Complete)",
            )
            axes[1].scatter(
                x_disc,
                file_eff,
                s=20,
                facecolor="white",
                edgecolor=color,
                lw=0.7,
                label=f"{col} (Discretized)",
            )
        axes[1].set_ylabel("efficiency")
        axes[1].set_title("Efficiencies")
    else:
        axes[1].plot(
            x_dense,
            pd.to_numeric(dense_df.get("eff"), errors="coerce"),
            color="#ff7f0e",
            lw=1.2,
            alpha=0.85,
            label="Complete",
        )
        axes[1].scatter(
            x_disc,
            pd.to_numeric(file_df.get("eff"), errors="coerce"),
            s=22,
            facecolor="white",
            edgecolor="#ff7f0e",
            lw=0.7,
            label="Discretized",
        )
        axes[1].set_ylabel("eff_sim_1")
        axes[1].set_title("Efficiency")

    axes[1].grid(True, alpha=0.25)
    axes[1].legend(loc="best", fontsize=7, ncol=2)

    axes[1].set_xlabel("Elapsed time [hours]")

    fig.tight_layout()
    _save_figure(fig, path, dpi=160)
    plt.close(fig)


def _plot_parameter_space_lower_triangle(
    reference_df: pd.DataFrame,
    dense_df: pd.DataFrame,
    file_df: pd.DataFrame,
    param_cols: list[str],
    path: Path,
) -> None:
    n = len(param_cols)
    fig, axes = plt.subplots(n, n, figsize=(3.0 * n, 3.0 * n), squeeze=False)

    for i, y_col in enumerate(param_cols):
        for j, x_col in enumerate(param_cols):
            ax = axes[i, j]

            if i < j:
                ax.axis("off")
                continue

            x_ref = pd.to_numeric(reference_df.get(x_col), errors="coerce")
            y_ref = pd.to_numeric(reference_df.get(y_col), errors="coerce")
            x_dense = pd.to_numeric(dense_df.get(x_col), errors="coerce")
            y_dense = pd.to_numeric(dense_df.get(y_col), errors="coerce")
            x_file = pd.to_numeric(file_df.get(x_col), errors="coerce")
            y_file = pd.to_numeric(file_df.get(y_col), errors="coerce")

            if i == j:
                xr = x_ref.dropna()
                xd = x_dense.dropna()
                if not xr.empty:
                    ax.hist(xr, bins=35, color="#808080", alpha=0.33, label="Dictionary")
                if not xd.empty:
                    ax.hist(xd, bins=35, color="#1f77b4", alpha=0.35, label="Curve")
                if i == 0 and j == 0:
                    ax.legend(loc="best", fontsize=7)
                ax.set_ylabel("count")
            else:
                mask_ref = x_ref.notna() & y_ref.notna()
                if mask_ref.any():
                    ax.scatter(
                        x_ref[mask_ref],
                        y_ref[mask_ref],
                        s=6,
                        color="#7a7a7a",
                        alpha=0.15,
                        linewidths=0,
                        zorder=1,
                    )
                mask_dense = x_dense.notna() & y_dense.notna()
                if mask_dense.any():
                    ax.plot(
                        x_dense[mask_dense],
                        y_dense[mask_dense],
                        color="#1f77b4",
                        lw=1.2,
                        alpha=0.9,
                        zorder=2,
                    )
                mask_file = x_file.notna() & y_file.notna()
                if mask_file.any():
                    ax.scatter(
                        x_file[mask_file],
                        y_file[mask_file],
                        s=16,
                        facecolor="white",
                        edgecolor="black",
                        linewidth=0.5,
                        zorder=3,
                    )

            ax.grid(True, alpha=0.20)
            if i == n - 1:
                ax.set_xlabel(x_col)
            if j == 0 and i > 0:
                ax.set_ylabel(y_col)

    fig.suptitle("STEP 3.1 parameter-space trajectory (lower triangular)", fontsize=12)
    fig.tight_layout(rect=[0.0, 0.0, 1.0, 0.98])
    _save_figure(fig, path, dpi=170)
    plt.close(fig)


def _resolve_seed(cfg_31: dict) -> int:
    raw = cfg_31.get("random_seed", None)
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    return int(np.random.default_rng().integers(0, 2**32 - 1))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step 3.1: Create complete and discretized parameter-space time series."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--source-csv", default=None)
    args = parser.parse_args()

    _clear_plots_dir()
    config = _load_config(Path(args.config))
    cfg_31 = config.get("step_3_1", {})
    curve_data_mode = _normalize_curve_data_mode(cfg_31.get("curve_data_mode", "synthetic_data_curve"))
    deprecated_weighting_keys = (
        "weighted_feature_columns",
        "weighting_top_k",
        "weighting_power",
    )
    for key in deprecated_weighting_keys:
        if cfg_31.get(key) is not None:
            log.warning(
                "Deprecated key step_3_1.%s is ignored. STEP 3.2 owns dictionary weighting.",
                key,
            )

    source_table = str(cfg_31.get("source_table", "dataset")).strip().lower()
    if args.source_csv:
        source_path = _resolve_input_path(args.source_csv)
    elif cfg_31.get("source_csv"):
        source_path = _resolve_input_path(str(cfg_31.get("source_csv")))
    elif curve_data_mode == "dataset_data_curve":
        source_path = DEFAULT_DATASET
    elif source_table == "dictionary":
        source_path = DEFAULT_DICTIONARY
    else:
        source_path = DEFAULT_DATASET

    if not source_path.exists():
        log.error("Source CSV not found: %s", source_path)
        return 1

    source_df = pd.read_csv(source_path, low_memory=False)
    if source_df.empty:
        log.error("Source CSV is empty: %s", source_path)
        return 1
    if curve_data_mode == "dataset_data_curve" and source_table != "dataset" and not (args.source_csv or cfg_31.get("source_csv")):
        log.info(
            "STEP 3.1 dataset_data_curve forces dataset source rows; source_table=%s is ignored.",
            source_table,
        )

    if cfg_31.get("rate_dictionary_csv"):
        rate_path = _resolve_input_path(str(cfg_31.get("rate_dictionary_csv")))
    else:
        rate_path = DEFAULT_DICTIONARY

    if not rate_path.exists():
        log.error("Rate dictionary CSV not found: %s", rate_path)
        return 1

    rate_df = pd.read_csv(rate_path, low_memory=False)
    if rate_df.empty:
        log.error("Rate dictionary CSV is empty: %s", rate_path)
        return 1

    parameter_space_spec = _load_parameter_space_spec(DEFAULT_PARAMETER_SPACE_SPEC)
    source_df, source_alias_cols = _apply_parameter_space_aliases(source_df, parameter_space_spec)
    rate_df, rate_alias_cols = _apply_parameter_space_aliases(rate_df, parameter_space_spec)
    if source_alias_cols:
        log.info("Materialized STEP 1 parameter-space aliases in source table: %s", source_alias_cols)
    if rate_alias_cols:
        log.info("Materialized STEP 1 parameter-space aliases in rate dictionary: %s", rate_alias_cols)

    # Resolve canonical columns and rate source.
    if CANONICAL_FLUX_COLUMN not in rate_df.columns:
        log.error("Rate dictionary must contain '%s'.", CANONICAL_FLUX_COLUMN)
        return 1

    rate_col_requested = str(cfg_31.get("rate_column", "events_per_second_global_rate"))
    rate_col = _pick_rate_column(rate_df, rate_col_requested)
    if rate_col is None:
        log.error("Could not find/derive rate column in rate dictionary (requested='%s').", rate_col_requested)
        return 1
    source_rate_col = rate_col
    if curve_data_mode == "dataset_data_curve":
        source_rate_col = _pick_rate_column(source_df, rate_col_requested)
        if source_rate_col is None:
            log.error("Could not find/derive rate column in source table (requested='%s').", rate_col_requested)
            return 1
    try:
        rate_range_hz = _resolve_global_rate_range_hz(
            rate_df=rate_df,
            rate_col=rate_col,
            cfg_31=cfg_31,
        )
    except ValueError as exc:
        log.error("%s", exc)
        return 1

    # Parameter-space curve configuration.
    try:
        param_cols = _resolve_parameter_curve_columns(rate_df, cfg_31)
    except ValueError as exc:
        log.error("%s", exc)
        return 1

    try:
        param_ranges = _resolve_parameter_ranges(param_cols, source_df, rate_df, cfg_31)
    except ValueError as exc:
        log.error("%s", exc)
        return 1

    identical_efficiencies = _as_bool(cfg_31.get("identical_efficiencies", False), default=False)
    eff_spread_raw = cfg_31.get("efficiency_spread", cfg_31.get("eff_spread", None))
    eff_spread_requested: float | None = None
    if eff_spread_raw not in (None, "", "null", "None"):
        eff_spread_requested = max(0.0, _safe_float(eff_spread_raw, 0.0))
    if identical_efficiencies and eff_spread_requested is not None and eff_spread_requested > 0.0:
        log.warning(
            "step_3_1.efficiency_spread=%.4g ignored because identical_efficiencies=true.",
            eff_spread_requested,
        )
    elif eff_spread_requested is not None and eff_spread_requested > 0.0:
        log.warning(
            "step_3_1.efficiency_spread=%.4g is currently ignored. "
            "STEP 3.1 now keeps curve generation inside dictionary convex hull.",
            eff_spread_requested,
        )
    eff_cols_cfg = [c for c in param_cols if c.startswith("eff_sim_")]
    curve_generation_mode = str(cfg_31.get("curve_generation_mode", "convex_hull")).strip().lower()
    if eff_cols_cfg and curve_data_mode == "synthetic_data_curve":
        eff_ranges_used = {c: [float(param_ranges[c][0]), float(param_ranges[c][1])] for c in eff_cols_cfg}
        log.info(
            "Efficiency ranges: %s | spread requested (ignored): %s | curve_generation_mode=%s",
            eff_ranges_used,
            ("None" if eff_spread_requested is None else f"{eff_spread_requested:.6g}"),
            curve_generation_mode,
        )

    # Time/discretization configuration.
    default_events_per_file = 50000
    if "n_events" in source_df.columns:
        med = pd.to_numeric(source_df["n_events"], errors="coerce").dropna()
        if not med.empty:
            default_events_per_file = int(max(1.0, float(med.median())))

    events_per_file = _safe_int(
        cfg_31.get("events_per_file", default_events_per_file),
        default_events_per_file,
        minimum=1,
    )
    include_partial_last_file = _as_bool(cfg_31.get("include_partial_last_file", True), default=True)

    duration_hours = max(1e-6, _safe_float(cfg_31.get("duration_hours", 72.0), 72.0))
    duration_seconds = duration_hours * 3600.0

    dense_default = 4000
    if "n_points" in cfg_31:
        dense_default = max(dense_default, 20 * _safe_int(cfg_31.get("n_points"), 240, minimum=2))
    dense_points = _safe_int(cfg_31.get("dense_points", dense_default), dense_default, minimum=200)

    start_time_raw = str(cfg_31.get("start_time_utc", "2026-01-01T00:00:00Z"))
    start_time = pd.to_datetime(start_time_raw, utc=True, errors="coerce")
    if pd.isna(start_time):
        log.warning("Invalid start_time_utc '%s'; using 2026-01-01T00:00:00Z", start_time_raw)
        start_time = pd.Timestamp("2026-01-01T00:00:00Z")

    seed = _resolve_seed(cfg_31)
    rng = np.random.default_rng(seed)
    log.info("Using random seed: %d", seed)

    # Keep only valid dictionary rows for parameter-space reference plotting.
    dict_param_df = rate_df[param_cols].apply(pd.to_numeric, errors="coerce")
    valid_dict = dict_param_df.notna().all(axis=1)
    rate_work = rate_df.loc[valid_dict].reset_index(drop=True)
    if rate_work.empty:
        log.error("No valid dictionary rows in parameter-space columns: %s", param_cols)
        return 1

    if curve_data_mode == "dataset_data_curve":
        try:
            dense_df, file_df, curve_build_info = _build_dataset_backed_curve(
                source_df=source_df,
                param_cols=param_cols,
                rate_col=source_rate_col,
                duration_seconds_target=duration_seconds,
                events_per_file_fallback=events_per_file,
                start_time=start_time,
                rng=rng,
            )
        except ValueError as exc:
            log.error("%s", exc)
            return 1
        total_events = float(pd.to_numeric(file_df["n_events_expected"], errors="coerce").sum())
        plot_reference_df = source_df[param_cols].apply(pd.to_numeric, errors="coerce")
    else:
        # Build dense parameter-space trajectory.
        u = _normalised_axis(dense_points)
        curve, curve_build_info = _build_parameter_curve(
            u=u,
            param_cols=param_cols,
            param_ranges=param_ranges,
            rng=rng,
            cfg_31=cfg_31,
            identical_efficiencies=identical_efficiencies,
            reference_df=rate_work[param_cols],
        )

        dense_rate_hz = _build_global_rate_curve_from_parameters(
            curve=curve,
            param_cols=param_cols,
            cfg_31=cfg_31,
            rate_range_hz=rate_range_hz,
        )

        dense_time_s = np.linspace(0.0, duration_seconds, dense_points, dtype=float)
        dense_time = start_time + pd.to_timedelta(dense_time_s, unit="s")

        dense_df = pd.DataFrame(
            {
                "curve_index": np.arange(len(dense_time_s), dtype=int),
                "time_utc": dense_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "elapsed_seconds": dense_time_s,
                "elapsed_hours": dense_time_s / 3600.0,
            }
        )

        for col in param_cols:
            dense_df[col] = np.asarray(curve[col], dtype=float)

        dense_tracks: dict[str, np.ndarray] = {}
        for col in [*param_cols]:
            if col in dense_df.columns and col not in dense_tracks:
                dense_tracks[col] = pd.to_numeric(dense_df[col], errors="coerce").to_numpy(dtype=float)

        try:
            file_df, total_events = _discretize_curve_by_events(
                dense_time_s=dense_time_s,
                dense_rate_hz=dense_rate_hz,
                dense_tracks=dense_tracks,
                events_per_file=events_per_file,
                include_partial_last_file=include_partial_last_file,
            )
        except ValueError as exc:
            log.error("%s", exc)
            return 1
        plot_reference_df = rate_work[param_cols]

    log.info(
        "Curve generation: data_mode=%s, mode=%s, reference_points=%s, anchors=%s",
        curve_data_mode,
        curve_build_info.get("mode"),
        curve_build_info.get("n_reference_points"),
        curve_build_info.get("n_anchor_points"),
    )

    if "step31_curve_data_mode" not in dense_df.columns:
        dense_df["step31_curve_data_mode"] = curve_data_mode

    # Canonical aliases expected by downstream tooling/plots.
    if CANONICAL_FLUX_COLUMN in dense_df.columns:
        dense_df["flux"] = pd.to_numeric(dense_df[CANONICAL_FLUX_COLUMN], errors="coerce")
    elif "flux" not in dense_df.columns:
        dense_df["flux"] = pd.to_numeric(dense_df[param_cols[0]], errors="coerce")

    if CANONICAL_EFF_COLUMN in dense_df.columns:
        dense_df["eff"] = pd.to_numeric(dense_df[CANONICAL_EFF_COLUMN], errors="coerce")
    else:
        eff_cols = [c for c in param_cols if c.startswith("eff_sim_")]
        if eff_cols:
            dense_df["eff"] = pd.to_numeric(dense_df[eff_cols[0]], errors="coerce")
        else:
            dense_df["eff"] = np.nan

    out_dense_csv = FILES_DIR / "complete_curve_time_series.csv"
    dense_df.to_csv(out_dense_csv, index=False)
    log.info("Wrote complete curve CSV: %s (%d rows)", out_dense_csv, len(dense_df))

    if len(file_df) < 3:
        log.warning(
            "Only %d synthetic file(s) produced; consider increasing duration_hours or decreasing events_per_file.",
            len(file_df),
        )

    # Canonical aliases.
    if CANONICAL_FLUX_COLUMN in file_df.columns:
        file_df["flux"] = pd.to_numeric(file_df[CANONICAL_FLUX_COLUMN], errors="coerce")
    elif "flux" not in file_df.columns and param_cols:
        file_df["flux"] = pd.to_numeric(file_df[param_cols[0]], errors="coerce")

    if CANONICAL_EFF_COLUMN in file_df.columns:
        file_df["eff"] = pd.to_numeric(file_df[CANONICAL_EFF_COLUMN], errors="coerce")
    elif "eff" not in file_df.columns:
        eff_cols = [c for c in param_cols if c.startswith("eff_sim_")]
        if eff_cols:
            file_df["eff"] = pd.to_numeric(file_df[eff_cols[0]], errors="coerce")
        else:
            file_df["eff"] = np.nan

    if "step31_curve_data_mode" not in file_df.columns:
        file_df["step31_curve_data_mode"] = curve_data_mode

    time_start = start_time + pd.to_timedelta(file_df["elapsed_seconds_start"], unit="s")
    time_end = start_time + pd.to_timedelta(file_df["elapsed_seconds_end"], unit="s")
    time_mid = start_time + pd.to_timedelta(file_df["elapsed_seconds"], unit="s")

    file_df["time_start_utc"] = time_start.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    file_df["time_end_utc"] = time_end.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    file_df["time_utc"] = time_mid.dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    base_cols = [
        "file_index",
        "time_start_utc",
        "time_end_utc",
        "time_utc",
        "elapsed_hours_start",
        "elapsed_hours_end",
        "elapsed_hours",
        "duration_seconds",
        "target_events_per_file",
        "n_events_expected",
        "n_events",
        "flux",
        "eff",
        "flux_cm2_min",
        "eff_sim_1",
        "step31_curve_data_mode",
        "step31_source_row_index",
        "step31_source_filename_base",
        "step31_source_param_hash_x",
    ]

    extra_param_cols = [
        c
        for c in param_cols
        if c not in {"flux", "eff", "flux_cm2_min", "eff_sim_1"}
    ]
    extra_cols = [c for c in extra_param_cols if c in file_df.columns]

    out_cols = [c for c in base_cols if c in file_df.columns] + extra_cols
    out_cols = list(dict.fromkeys(out_cols))

    out_df = file_df[out_cols].copy()
    out_csv = FILES_DIR / "time_series.csv"
    out_df.to_csv(out_csv, index=False)
    log.info("Wrote time series CSV: %s (%d rows)", out_csv, len(out_df))

    dense_eff_spread_stats: dict[str, float] = {}
    file_eff_spread_stats: dict[str, float] = {}
    eff_cols_for_stats = [
        c for c in param_cols
        if c.startswith("eff_sim_") and c in dense_df.columns and c in out_df.columns
    ]
    if len(eff_cols_for_stats) >= 2:
        dense_eff_matrix = dense_df[eff_cols_for_stats].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        dense_spread = np.nanmax(dense_eff_matrix, axis=1) - np.nanmin(dense_eff_matrix, axis=1)
        dense_spread = dense_spread[np.isfinite(dense_spread)]
        if dense_spread.size > 0:
            dense_eff_spread_stats = {
                "dense_eff_spread_min": float(np.min(dense_spread)),
                "dense_eff_spread_median": float(np.median(dense_spread)),
                "dense_eff_spread_max": float(np.max(dense_spread)),
            }

        file_eff_matrix = out_df[eff_cols_for_stats].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        file_spread = np.nanmax(file_eff_matrix, axis=1) - np.nanmin(file_eff_matrix, axis=1)
        file_spread = file_spread[np.isfinite(file_spread)]
        if file_spread.size > 0:
            file_eff_spread_stats = {
                "file_eff_spread_min": float(np.min(file_spread)),
                "file_eff_spread_median": float(np.median(file_spread)),
                "file_eff_spread_max": float(np.max(file_spread)),
            }

    summary = {
        "source_csv": str(source_path),
        "rate_dictionary_csv": str(rate_path),
        "parameter_space_spec_json": str(DEFAULT_PARAMETER_SPACE_SPEC),
        "parameter_space_alias_columns_added_source": source_alias_cols,
        "parameter_space_alias_columns_added_rate_dictionary": rate_alias_cols,
        "curve_data_mode_requested": curve_data_mode,
        "curve_data_mode_used": curve_data_mode,
        "source_rate_column_used": source_rate_col,
        "rate_dictionary_rate_column_used": rate_col,
        "parameter_curve_columns": param_cols,
        "parameter_ranges_used": {k: [float(v[0]), float(v[1])] for k, v in param_ranges.items()},
        "identical_efficiencies": bool(identical_efficiencies),
        "efficiency_spread_requested": eff_spread_requested,
        "curve_generation_mode_requested": curve_generation_mode,
        "curve_generation_mode_used": curve_build_info.get("mode"),
        "curve_generation_reference_points": curve_build_info.get("n_reference_points"),
        "curve_generation_anchor_points": curve_build_info.get("n_anchor_points"),
        "random_seed": int(seed),
        "duration_hours": float(duration_hours),
        "dense_points": int(dense_points),
        "events_per_file": int(events_per_file),
        "include_partial_last_file": bool(include_partial_last_file),
        "n_files": int(len(out_df)),
        "total_expected_events": float(total_events),
        "start_time_utc": str(out_df["time_start_utc"].iloc[0]),
        "end_time_utc": str(out_df["time_end_utc"].iloc[-1]),
        "mean_file_duration_seconds": float(out_df["duration_seconds"].mean()),
    }
    for key in (
        "ordering_mode",
        "event_count_source_column",
        "duration_source_column",
        "selected_source_rows",
        "selected_source_unique_rows",
        "selection_randomized",
        "selection_center_jitter_scale",
        "selection_phase_offset",
    ):
        if key in curve_build_info:
            summary[key] = curve_build_info.get(key)
    summary.update(dense_eff_spread_stats)
    summary.update(file_eff_spread_stats)
    out_summary = FILES_DIR / "time_series_summary.json"
    with open(out_summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    log.info("Wrote summary JSON: %s", out_summary)

    _plot_time_series(dense_df, out_df, PLOTS_DIR / "time_series_flux_eff.png")
    _plot_parameter_space_lower_triangle(
        reference_df=plot_reference_df,
        dense_df=dense_df,
        file_df=out_df,
        param_cols=param_cols,
        path=PLOTS_DIR / "parameter_space_lower_triangle.png",
    )

    log.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
